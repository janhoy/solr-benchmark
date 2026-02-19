# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Solr benchmark runners.

All runners are async (required by the OSB worker coordinator framework) but
delegate to synchronous pysolr/requests calls.  Long-running operations are
offloaded to a thread-pool executor so they do not block the event loop.
"""

import asyncio
import json
import logging
import time

import pysolr
import requests

from osbenchmark import exceptions as benchmark_exceptions
from osbenchmark.solr.client import SolrAdminClient, CollectionAlreadyExistsError, CollectionNotFoundError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error translation helpers
# ---------------------------------------------------------------------------

def _translate_solr_error(e):
    """Translate a pysolr or requests exception to a BenchmarkTransportError.

    This ensures that worker_coordinator's generic error handler can record
    proper error metadata (http-status, error-description) for Solr runs
    without needing opensearchpy to be installed.
    """
    if isinstance(e, requests.exceptions.ConnectionError):
        return benchmark_exceptions.BenchmarkConnectionError(str(e), cause=e)
    if isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectTimeout)):
        return benchmark_exceptions.BenchmarkConnectionTimeout(str(e), cause=e)
    if isinstance(e, requests.exceptions.HTTPError):
        status_code = e.response.status_code if e.response is not None else None
        if status_code == 404:
            return benchmark_exceptions.BenchmarkNotFoundError(str(e), cause=e)
        return benchmark_exceptions.BenchmarkTransportError(
            str(e), cause=e, status_code=status_code,
            error=f"HTTP {status_code}", info=str(e))
    if isinstance(e, pysolr.SolrError):
        # pysolr.SolrError message often contains the HTTP status in its string
        msg = str(e)
        status_code = None
        # Extract status code from messages like "[Reason: None]\n\t400 request error"
        for part in msg.split():
            if part.isdigit():
                code = int(part)
                if 100 <= code < 600:
                    status_code = code
                    break
        return benchmark_exceptions.BenchmarkTransportError(
            msg, cause=e, status_code=status_code, error="SolrError", info=msg)
    # Fallback: wrap any other exception as a generic transport error
    return benchmark_exceptions.BenchmarkTransportError(str(e), cause=e, error=type(e).__name__, info=str(e))


def solr_runner(fn):
    """Decorator that translates pysolr/requests exceptions to BenchmarkTransportError."""
    import functools

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except benchmark_exceptions.BenchmarkTransportError:
            raise
        except (pysolr.SolrError, requests.exceptions.RequestException) as e:
            raise _translate_solr_error(e) from e
    return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solr_client(params):
    """
    Build a pysolr.Solr instance from runner params.

    Expected params keys:
      - ``host``       — Solr host (default: "localhost")
      - ``port``       — Solr port (default: 8983)
      - ``collection`` — collection name
      - ``username``   — optional
      - ``password``   — optional
      - ``tls``        — bool (default: False)
      - ``timeout``    — request timeout seconds (default: 30)
    """
    host = params.get("host", "localhost")
    port = params.get("port", 8983)
    collection = params["collection"]
    tls = params.get("tls", False)
    timeout = params.get("timeout", 30)
    scheme = "https" if tls else "http"
    url = f"{scheme}://{host}:{port}/solr/{collection}"

    auth = None
    username = params.get("username")
    password = params.get("password")
    if username and password:
        auth = requests.auth.HTTPBasicAuth(username, password)

    # Disable automatic proxy detection (trust_env=False) to avoid hanging on macOS
    # after fork() — CFNetwork proxy detection is not fork-safe.
    session = requests.Session()
    session.trust_env = False
    if auth:
        session.auth = auth

    return pysolr.Solr(url, timeout=timeout, always_commit=False, session=session)


def _admin_client(params):
    """Build a SolrAdminClient from runner params."""
    return SolrAdminClient(
        host=params.get("host", "localhost"),
        port=params.get("port", 8983),
        username=params.get("username"),
        password=params.get("password"),
        tls=params.get("tls", False),
        timeout=params.get("timeout", 30),
    )


async def _run_in_executor(func, *args, **kwargs):
    """Run a blocking call in the default thread-pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _translate_ndjson_batch(lines):
    """
    Translate NDJSON action/document pairs to a list of Solr document dicts.

    For each pair:
      - Action line ``{"index": {"_id": "<id>", "_index": "<coll>", ...}}``
      - Document line ``{field: value, ...}``

    Translation rules:
      - ``_id`` from action line  → ``"id"`` field in document
      - ``_index`` from action line → available for routing/logging (not stored in doc)
      - ``_type`` from action line → dropped
      - All document fields are preserved as-is.
    """
    docs = []
    it = iter(lines)
    for action_line in it:
        action_line = action_line.strip()
        if not action_line:
            continue
        doc_line = next(it, None)
        if doc_line is None:
            break
        doc_line = doc_line.strip()
        if not doc_line:
            continue
        try:
            action = json.loads(action_line)
            doc = json.loads(doc_line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed NDJSON pair: %s", exc)
            continue

        # Extract action metadata (typically under "index" or "create" key)
        meta = {}
        for key in ("index", "create", "update", "delete"):
            if key in action:
                meta = action[key]
                break

        doc_id = meta.get("_id")
        if doc_id is not None:
            doc["id"] = doc_id

        # _index is available for routing; log it but do not store in document
        routing_collection = meta.get("_index")
        if routing_collection:
            logger.debug("NDJSON _index='%s' (routing only, not stored)", routing_collection)

        docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# Base runner with automatic error translation
# ---------------------------------------------------------------------------

class SolrRunner:
    """Base class for all Solr runners.

    Wraps ``__call__`` so that pysolr and requests exceptions are automatically
    translated to ``BenchmarkTransportError`` subclasses before they reach the
    worker_coordinator framework.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "__call__" in cls.__dict__:
            cls.__call__ = solr_runner(cls.__call__)


# ---------------------------------------------------------------------------
# Runner: bulk-index
# ---------------------------------------------------------------------------

class SolrBulkIndex(SolrRunner):
    """
    Index documents from an NDJSON corpus into Solr.

    Params:
      - ``host``, ``port``, ``collection``, ``username``, ``password``, ``tls``, ``timeout``
      - ``bulk-size`` — number of docs per batch (default: 500)
      - ``corpus``    — iterable of NDJSON line pairs (action + document)
      - ``commit``    — if True, hard-commit after all batches (default: False)
    """

    async def __call__(self, solr_not_used, params):
        corpus_lines = params.get("corpus", [])
        batch_size = params.get("bulk-size", 500)
        do_commit = params.get("commit", False)

        client = _solr_client(params)

        docs = _translate_ndjson_batch(corpus_lines)
        total_docs = len(docs)
        errors = 0

        start = time.perf_counter()
        for i in range(0, max(total_docs, 1), batch_size):
            batch = docs[i: i + batch_size]
            if not batch:
                break
            try:
                await _run_in_executor(client.add, batch, commit=False)
            except pysolr.SolrError as exc:
                logger.error("Bulk index error on batch starting at %d: %s", i, exc)
                errors += len(batch)

        if do_commit:
            await _run_in_executor(client.commit)

        elapsed = time.perf_counter() - start
        weight = total_docs - errors

        return {
            "weight": weight,
            "unit": "docs",
            "bulk-size": total_docs,
            "success": errors == 0,
            "error-count": errors,
            "took": elapsed,
        }

    def __str__(self):
        return "solr-bulk-index"


# ---------------------------------------------------------------------------
# Runner: search
# ---------------------------------------------------------------------------

class SolrSearch(SolrRunner):
    """
    Execute a Solr search query.

    Mode 1 — Classic params (default): uses pysolr.Solr.search()
      Params: ``q``, ``fl``, ``rows``, ``fq``, ``sort``, ``request-params``

    Mode 2 — JSON Query DSL: triggered by presence of ``body`` key
      Sends ``body`` dict as JSON to ``/query`` endpoint via requests.post()

    Common params:
      - ``host``, ``port``, ``collection``, ``username``, ``password``, ``tls``, ``timeout``
      - ``cache`` — include in cache (ignored for Solr, kept for API compat)
    """

    async def __call__(self, solr_not_used, params):
        host = params.get("host", "localhost")
        port = params.get("port", 8983)
        collection = params["collection"]
        tls = params.get("tls", False)
        timeout = params.get("timeout", 30)
        scheme = "https" if tls else "http"

        start = time.perf_counter()

        if "body" in params:
            # Mode 2: JSON Query DSL → POST /solr/{collection}/query
            url = f"{scheme}://{host}:{port}/solr/{collection}/query"
            req_headers = {"Content-Type": "application/json"}
            username = params.get("username")
            password = params.get("password")
            auth = (username, password) if username and password else None

            def _do_json_search():
                resp = requests.post(url, json=params["body"],
                                     headers=req_headers, auth=auth,
                                     timeout=timeout)
                resp.raise_for_status()
                return resp.json()

            result = await _run_in_executor(_do_json_search)
            num_hits = result.get("response", {}).get("numFound", 0)
        else:
            # Mode 1: Classic params → pysolr.Solr.search()
            client = _solr_client(params)
            q = params.get("q", "*:*")
            kwargs = {}
            for key in ("fl", "rows", "fq", "sort"):
                if key in params:
                    kwargs[key] = params[key]
            extra = params.get("request-params", {})
            kwargs.update(extra)

            results = await _run_in_executor(client.search, q, **kwargs)
            num_hits = results.hits

        elapsed = time.perf_counter() - start

        return {
            "weight": 1,
            "unit": "ops",
            "hits": num_hits,
            "took": elapsed,
        }

    def __str__(self):
        return "solr-search"


# ---------------------------------------------------------------------------
# Runner: commit
# ---------------------------------------------------------------------------

class SolrCommit(SolrRunner):
    """
    Commit pending changes in Solr.

    Params:
      - ``host``, ``port``, ``collection``, ``username``, ``password``, ``tls``, ``timeout``
      - ``soft-commit`` — bool; if True performs a soft commit (default: False)
    """

    async def __call__(self, solr_not_used, params):
        client = _solr_client(params)
        soft = params.get("soft-commit", False)

        start = time.perf_counter()
        if soft:
            await _run_in_executor(client.commit, softCommit=True)
        else:
            await _run_in_executor(client.commit)
        elapsed = time.perf_counter() - start

        return {"weight": 1, "unit": "ops", "took": elapsed}

    def __str__(self):
        return "solr-commit"


# ---------------------------------------------------------------------------
# Runner: optimize
# ---------------------------------------------------------------------------

class SolrOptimize(SolrRunner):
    """
    Force-merge Solr segments (optimize).

    Params:
      - ``host``, ``port``, ``collection``, ``username``, ``password``, ``tls``, ``timeout``
      - ``max-segments`` — int; target max segment count (default: 1)
    """

    async def __call__(self, solr_not_used, params):
        client = _solr_client(params)
        max_segments = params.get("max-segments", 1)

        start = time.perf_counter()
        await _run_in_executor(client.optimize, maxSegments=max_segments)
        elapsed = time.perf_counter() - start

        return {"weight": 1, "unit": "ops", "took": elapsed}

    def __str__(self):
        return "solr-optimize"


# ---------------------------------------------------------------------------
# Runner: create-collection (two-step: upload configset, then create)
# ---------------------------------------------------------------------------

class SolrCreateCollection(SolrRunner):
    """
    Collection creation — optionally with configset upload.

    Two-step mode (default when ``configset-path`` is provided):
      1. Upload configset ZIP to /api/cluster/configs/{configset-name}
      2. Create collection referencing that configset

    Single-step mode (when ``configset`` names an existing server-side configset
    such as ``_default``, and ``configset-path`` is omitted):
      - Only creates the collection; no upload step.

    Params:
      - ``host``, ``port``, ``username``, ``password``, ``tls``, ``timeout``
      - ``collection``         — collection name to create
      - ``configset``          — configset name (default: collection name).
                                 If a built-in configset like ``_default`` is
                                 specified, omit ``configset-path`` to skip upload.
      - ``configset-path``     — local directory with conf/schema.xml etc.
                                 Omit to use an already-existing server configset.
      - ``num-shards``         — int (default: 1)
      - ``replication-factor`` — int (default: 1)
      - ``delete-configset-on-error`` — bool (default: True, ignored when no upload)
    """

    async def __call__(self, solr_not_used, params):
        admin = _admin_client(params)
        collection = params["collection"]
        configset = params.get("configset", collection)
        configset_path = params.get("configset-path")
        num_shards = params.get("num-shards", 1)
        replication_factor = params.get("replication-factor", 1)

        start = time.perf_counter()

        # Step 1: upload configset (only if a local path is supplied)
        if configset_path:
            await _run_in_executor(admin.upload_configset, configset, configset_path)
            logger.info("Uploaded configset '%s' from '%s'", configset, configset_path)

        # Step 2: create collection
        try:
            await _run_in_executor(
                admin.create_collection,
                collection,
                configset,
                num_shards,
                replication_factor,
            )
        except CollectionAlreadyExistsError:
            logger.warning("Collection '%s' already exists, skipping creation.", collection)
        except Exception:
            if configset_path and params.get("delete-configset-on-error", True):
                try:
                    await _run_in_executor(admin.delete_configset, configset)
                except Exception as cleanup_exc:
                    logger.warning("Failed to clean up configset '%s': %s", configset, cleanup_exc)
            raise

        elapsed = time.perf_counter() - start
        return {"weight": 1, "unit": "ops", "took": elapsed}

    def __str__(self):
        return "solr-create-collection"


# ---------------------------------------------------------------------------
# Runner: delete-collection
# ---------------------------------------------------------------------------

class SolrDeleteCollection(SolrRunner):
    """
    Delete a Solr collection, optionally deleting its configset too.

    Params:
      - ``host``, ``port``, ``username``, ``password``, ``tls``, ``timeout``
      - ``collection``       — collection name
      - ``configset``        — configset name to delete (defaults to collection name)
      - ``delete-configset`` — bool; delete the configset after the collection
                               (default: True). Set to False when using a shared
                               or built-in configset such as ``_default``.
      - ``ignore-missing``   — bool; if True, do not raise on 404 (default: True)
    """

    async def __call__(self, solr_not_used, params):
        admin = _admin_client(params)
        collection = params["collection"]
        configset = params.get("configset", collection)
        ignore_missing = params.get("ignore-missing", True)
        delete_configset = params.get("delete-configset", True)

        start = time.perf_counter()
        try:
            await _run_in_executor(admin.delete_collection, collection)
        except CollectionNotFoundError:
            if not ignore_missing:
                raise
            logger.info("Collection '%s' not found, skipping delete.", collection)

        if delete_configset:
            try:
                await _run_in_executor(admin.delete_configset, configset)
            except Exception as exc:
                logger.warning("Could not delete configset '%s': %s", configset, exc)

        elapsed = time.perf_counter() - start
        return {"weight": 1, "unit": "ops", "took": elapsed}

    def __str__(self):
        return "solr-delete-collection"


# ---------------------------------------------------------------------------
# Runner: raw-request
# ---------------------------------------------------------------------------

class SolrRawRequest(SolrRunner):
    """
    Send an arbitrary HTTP request to any Solr endpoint.

    Params:
      - ``host``, ``port``, ``username``, ``password``, ``tls``, ``timeout``
      - ``method``  — HTTP method (default: "GET")
      - ``path``    — URL path relative to http://{host}:{port}/
      - ``body``    — dict (serialized as JSON) or str
      - ``headers`` — dict of additional request headers
    """

    async def __call__(self, solr_not_used, params):
        admin = _admin_client(params)
        method = params.get("method", "GET")
        path = params["path"]
        body = params.get("body")
        headers = params.get("headers", {})

        start = time.perf_counter()
        resp = await _run_in_executor(admin.raw_request, method, path, body, headers)
        elapsed = time.perf_counter() - start

        return {
            "weight": 1,
            "unit": "ops",
            "http-status": resp.status_code,
            "took": elapsed,
        }

    def __str__(self):
        return "solr-raw-request"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_solr_runners(register_runner):
    """
    Register all Solr runners with the worker coordinator.

    Call this from osbenchmark/worker_coordinator/runner.py's
    register_default_runners() after importing this module.

    Args:
        register_runner: the register_runner function from the worker_coordinator.
    """
    register_runner("bulk-index", SolrBulkIndex(), async_runner=True)
    register_runner("search", SolrSearch(), async_runner=True)
    register_runner("commit", SolrCommit(), async_runner=True)
    register_runner("optimize", SolrOptimize(), async_runner=True)
    register_runner("create-collection", SolrCreateCollection(), async_runner=True)
    register_runner("delete-collection", SolrDeleteCollection(), async_runner=True)
    register_runner("raw-request", SolrRawRequest(), async_runner=True)
