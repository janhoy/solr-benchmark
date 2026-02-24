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
from datetime import datetime
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
    proper error metadata (http-status, error-description) for Solr runs.
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

def _fetch_first_collection(host: str, port: int, tls: bool = False) -> str:
    """
    Query Solr admin API and return the first available collection name.

    Used as a fallback when a param source returns ``index: None`` (common in
    standard OSB workloads designed for OpenSearch where the index is resolved
    from the document routing, not the request URL).

    Returns None if no collections exist or the request fails.
    """
    scheme = "https" if tls else "http"
    try:
        session = requests.Session()
        session.trust_env = False
        resp = session.get(
            f"{scheme}://{host}:{port}/solr/admin/collections",
            params={"action": "LIST"},
            timeout=5
        )
        if resp.ok:
            cols = resp.json().get("collections", [])
            if cols:
                return sorted(cols)[0]   # deterministic: alphabetically first
    except Exception as exc:
        logger.warning("Could not fetch collection list from Solr (%s:%s): %s", host, port, exc)
    return None


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
    collection = params.get("collection") or params.get("index") or None
    tls = params.get("tls", False)
    if not collection:
        collection = _fetch_first_collection(host, port, tls)
    if not collection:
        raise KeyError("collection")
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
    Translate NDJSON to a list of Solr document dicts.

    Supports two formats:

    1. OpenSearch bulk format (action/document pairs):
       {"index": {"_id": "1", "_index": "coll"}}
       {"field": "value"}
       → Extracts _id from action line and sets it as "id" field in document

    2. Simple NDJSON (one document per line):
       {"field": "value"}
       {"field2": "value2"}
       → Each line is a document; no stable IDs unless "id" field is present

    Auto-detects format by checking if lines contain bulk action keys
    (index, create, update, delete).
    """
    docs = []
    it = iter(lines)

    # Peek at first line to detect format
    first_line = None
    for line in it:
        line = line.strip()
        if line:
            first_line = line
            break

    if not first_line:
        return docs

    try:
        first_obj = json.loads(first_line)
    except json.JSONDecodeError:
        logger.warning("Skipping malformed first line: %s", first_line)
        return docs

    # Detect format: if first object has bulk action keys, it's action/doc pairs
    has_action_keys = isinstance(first_obj, dict) and any(
        k in first_obj for k in ("index", "create", "update", "delete")
    )

    if has_action_keys:
        # OpenSearch bulk format: action/doc pairs
        docs = _parse_bulk_pairs(first_line, it)
    else:
        # Simple NDJSON format: each line is a document
        if isinstance(first_obj, dict):
            docs.append(first_obj)
        for line in it:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    docs.append(obj)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed NDJSON line: %s", exc)

    return docs


def _translate_ndjson_stream(lines):
    """
    Stream-translate NDJSON to Solr documents (generator version).

    Yields documents one at a time instead of loading all into memory.
    Supports both OpenSearch bulk format and simple NDJSON.
    """
    it = iter(lines)

    # Peek at first line to detect format
    first_line = None
    for line in it:
        line = line.strip()
        if line:
            first_line = line
            break

    if not first_line:
        return

    try:
        first_obj = json.loads(first_line)
    except json.JSONDecodeError:
        logger.warning("Skipping malformed first line: %s", first_line)
        return

    # Detect format
    has_action_keys = isinstance(first_obj, dict) and any(
        k in first_obj for k in ("index", "create", "update", "delete")
    )

    if has_action_keys:
        # OpenSearch bulk format: action/doc pairs
        yield from _stream_bulk_pairs(first_line, it)
    else:
        # Simple NDJSON: each line is a document
        if isinstance(first_obj, dict):
            # Generate ID for first doc if missing
            if "id" not in first_obj:
                first_obj["id"] = str(hash(json.dumps(first_obj, sort_keys=True)))
            yield first_obj
        for line in it:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    # Generate ID if missing
                    if "id" not in obj:
                        obj["id"] = str(hash(json.dumps(obj, sort_keys=True)))

                    # Convert geo_point arrays to Solr format
                    for key, value in list(obj.items()):
                        if isinstance(value, list) and len(value) == 2:
                            if all(isinstance(v, (int, float)) for v in value):
                                obj[key] = f"{value[1]},{value[0]}"

                    yield obj
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed NDJSON line: %s", exc)


def _stream_bulk_pairs(first_action_line, lines_iter):
    """Stream-parse OpenSearch bulk format (generator version)."""
    action_line = first_action_line

    while action_line:
        doc_line = next(lines_iter, None)
        if doc_line is None:
            break
        doc_line = doc_line.strip()
        if not doc_line:
            action_line = next(lines_iter, "").strip()
            continue

        try:
            action = json.loads(action_line)
            doc = json.loads(doc_line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed NDJSON pair: %s", exc)
            action_line = next(lines_iter, "").strip()
            continue

        if not isinstance(action, dict) or not isinstance(doc, dict):
            logger.warning("Skipping non-dict action/doc pair")
            action_line = next(lines_iter, "").strip()
            continue

        # Extract _id from action metadata and set as "id" field
        id_found = False
        for key in ("index", "create", "update", "delete"):
            if key in action:
                meta = action[key]
                if isinstance(meta, dict) and "_id" in meta:
                    doc["id"] = meta["_id"]
                    id_found = True
                break

        if not id_found:
            # Generate ID if not found in action metadata
            doc["id"] = str(abs(hash(json.dumps(doc, sort_keys=True))))

        # Convert geo_point arrays and date formats for Solr compatibility
        for key, value in list(doc.items()):
            # Geo-point: [lon, lat] → "lat,lon" string
            if isinstance(value, list) and len(value) == 2:
                if all(isinstance(v, (int, float)) for v in value):
                    doc[key] = f"{value[1]},{value[0]}"
            # Date: "YYYY-MM-DD HH:MM:SS" → "YYYY-MM-DDTHH:MM:SSZ" (ISO 8601)
            elif isinstance(value, str) and len(value) == 19 and value[10] == ' ':
                # Check if it looks like a date: YYYY-MM-DD HH:MM:SS
                if value[4] == '-' and value[7] == '-' and value[13] == ':' and value[16] == ':':
                    doc[key] = value.replace(' ', 'T') + 'Z'

        yield doc
        action_line = next(lines_iter, "").strip()


def _parse_bulk_pairs(first_action_line, lines_iter):
    """Parse OpenSearch bulk format (alternating action/doc pairs)."""
    docs = []
    action_line = first_action_line

    while action_line:
        doc_line = next(lines_iter, None)
        if doc_line is None:
            break
        doc_line = doc_line.strip()
        if not doc_line:
            # Try next action
            action_line = next(lines_iter, "").strip()
            continue

        try:
            action = json.loads(action_line)
            doc = json.loads(doc_line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed NDJSON pair: %s", exc)
            action_line = next(lines_iter, "").strip()
            continue

        if not isinstance(action, dict) or not isinstance(doc, dict):
            logger.warning("Skipping non-dict action/doc pair")
            action_line = next(lines_iter, "").strip()
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
        action_line = next(lines_iter, "").strip()

    return docs


# ---------------------------------------------------------------------------
# OpenSearch → Solr conversion is now in osbenchmark.solr.conversion package
# These helpers are imported on-demand only when processing OpenSearch workloads
# ---------------------------------------------------------------------------


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

        # Use streaming translation to avoid loading all documents into memory
        doc_stream = _translate_ndjson_stream(corpus_lines)
        total_docs = 0
        errors = 0

        start = time.perf_counter()

        # Collect documents in batches and send to Solr
        batch = []
        for doc in doc_stream:
            batch.append(doc)
            if len(batch) >= batch_size:
                try:
                    # Use commitWithin=1000ms to make docs visible quickly without explicit commits
                    await _run_in_executor(client.add, batch, commit=False, commitWithin=1000)
                    total_docs += len(batch)
                except pysolr.SolrError as exc:
                    logger.error("Bulk index error on batch: %s", exc)
                    errors += len(batch)
                batch = []

        # Send remaining documents
        if batch:
            try:
                await _run_in_executor(client.add, batch, commit=False, commitWithin=1000)
                total_docs += len(batch)
            except pysolr.SolrError as exc:
                logger.error("Bulk index error on final batch: %s", exc)
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

    Handles three input formats so that both Solr-native workloads and standard
    OSB workloads (which provide OpenSearch query DSL) work transparently:

    Mode 1 — Classic Solr params (default): uses pysolr.Solr.search()
      Params: ``q``, ``fl``, ``rows``, ``fq``, ``sort``, ``request-params``

    Mode 2 — Solr JSON Query DSL: triggered when ``body`` is present and
      ``body["query"]`` is a **string** (native Solr JSON DSL).
      POSTs ``body`` as JSON to ``/solr/{collection}/query``.

    Mode 3 — OpenSearch query DSL: triggered when ``body`` is present and
      ``body["query"]`` is a **dict** (standard OSB workload format).
      Translates the OpenSearch DSL to a Solr ``q`` string and uses
      pysolr.Solr.search().  Aggregations are silently ignored.
      The ``index`` param is accepted as an alias for ``collection``.

    Common params:
      - ``host``, ``port``, ``collection`` (or ``index``), ``username``,
        ``password``, ``tls``, ``timeout``
      - ``cache`` — kept for API compat, ignored in Solr
    """

    async def __call__(self, solr_not_used, params):
        host = params.get("host", "localhost")
        port = params.get("port", 8983)
        tls = params.get("tls", False)
        # Accept 'index' as alias for 'collection' (standard OSB workload format).
        # When a param source returns index=None (OSB workloads that rely on OpenSearch
        # routing), fall back to the first available Solr collection.
        collection = params.get("collection") or params.get("index") or None
        if not collection:
            collection = _fetch_first_collection(host, port, tls)
            if collection:
                logger.debug("No collection in params; using first Solr collection: %s", collection)
            else:
                collection = "default"
        timeout = params.get("timeout", 30)
        scheme = "https" if tls else "http"

        start = time.perf_counter()

        body = params.get("body")
        if body is not None:
            if isinstance(body, dict) and isinstance(body.get("query"), dict):
                # Defensive warning: un-converted OpenSearch DSL body detected.
                # This should not happen if the workload was properly converted.
                # The auto-conversion in BenchmarkCoordinator.setup() will have
                # translated these bodies to Solr JSON DSL before the run.
                op_name = params.get("name", params.get("operation-type", "unknown"))
                logger.warning(
                    "Task '%s' has an un-converted OpenSearch query DSL body (body['query'] is a dict). "
                    "Run 'solr-benchmark convert-workload --workload-path <path>' to convert the workload, "
                    "or use a local workload path to trigger auto-conversion. "
                    "Returning 0 hits for this task.",
                    op_name,
                )
                elapsed = time.perf_counter() - start
                return {"weight": 0, "unit": "ops", "hits": 0, "hits-total": 0, "took": elapsed}
            else:
                # Mode 2: Solr JSON Query DSL → POST /solr/{collection}/query
                url = f"{scheme}://{host}:{port}/solr/{collection}/query"
                req_headers = {"Content-Type": "application/json"}
                username = params.get("username")
                password = params.get("password")
                auth = (username, password) if username and password else None

                def _do_json_search():
                    session = requests.Session()
                    session.trust_env = False  # prevent macOS proxy detection (fork-safety)
                    resp = session.post(url, json=body,
                                        headers=req_headers, auth=auth,
                                        timeout=timeout)
                    resp.raise_for_status()
                    return resp.json()

                result = await _run_in_executor(_do_json_search)
                num_hits = result.get("response", {}).get("numFound", 0)
        else:
            # Mode 1: Classic Solr params → pysolr.Solr.search()
            solr_params = dict(params)
            solr_params["collection"] = collection
            client = _solr_client(solr_params)
            q = params.get("q", "*:*")
            kwargs = {}
            for key in ("fl", "rows", "fq", "sort"):
                if key in params:
                    kwargs[key] = params[key]
            kwargs.update(params.get("request-params", {}))

            results = await _run_in_executor(client.search, q, **kwargs)
            num_hits = results.hits

        elapsed = time.perf_counter() - start

        return {
            "weight": 1,
            "unit": "ops",
            "hits": num_hits,
            "hits-total": num_hits,
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


class SolrRefreshBridge(SolrRunner):
    """
    Bridge: maps OSB 'refresh' operation to Solr commit.

    Translates the `index` parameter from OSB to `collection` for Solr.
    If no index is specified, commits are skipped (returns success).
    """

    async def __call__(self, solr_not_used, params):
        # Map index to collection if not already set
        index = params.get("index")
        collection = params.get("collection")

        # If neither index nor collection is specified, skip the commit
        if not index and not collection:
            logger.info("Refresh operation has no index/collection specified - skipping commit")
            return {"weight": 0, "unit": "ops", "took": 0}

        solr_params = dict(params)
        if not collection:
            solr_params["collection"] = index

        client = _solr_client(solr_params)
        soft = params.get("soft-commit", False)

        start = time.perf_counter()
        if soft:
            await _run_in_executor(client.commit, softCommit=True)
        else:
            await _run_in_executor(client.commit)
        elapsed = time.perf_counter() - start

        return {"weight": 1, "unit": "ops", "took": elapsed}

    def __str__(self):
        return "refresh"


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


class SolrNoOpBridge(SolrRunner):
    """
    Silently skips OpenSearch-specific operations that have no Solr equivalent
    (e.g. cluster-health, refresh, force-merge, put-pipeline).
    """

    def __init__(self, op_name):
        self._op_name = op_name

    async def __call__(self, solr_not_used, params):
        logger.debug("Skipping OpenSearch-specific operation '%s' in Solr mode.", self._op_name)
        return {"weight": 0, "unit": "ops", "success": True}

    def __str__(self):
        return self._op_name


# ---------------------------------------------------------------------------
# Bridge runners: map OSB index operations to Solr collection operations
# ---------------------------------------------------------------------------

class SolrDeleteIndexBridge(SolrRunner):
    """
    Bridge: maps OSB 'delete-index' operation to Solr delete-collection.

    Accepts params from DeleteIndexParamSource:
      - ``indices``       — list of collection names to delete
      - ``only-if-exists``— bool (default: True); ignore missing collections
    """

    async def __call__(self, solr_not_used, params):
        admin = _admin_client(params)
        indices = params.get("indices", [])
        only_if_exists = params.get("only-if-exists", True)

        start = time.perf_counter()
        for name in indices:
            try:
                await _run_in_executor(admin.delete_collection, name)
            except CollectionNotFoundError:
                if not only_if_exists:
                    raise
                logger.info("Collection '%s' not found, skipping delete.", name)
            try:
                await _run_in_executor(admin.delete_configset, name)
            except Exception as exc:
                logger.debug("Could not delete configset '%s': %s", name, exc)

        elapsed = time.perf_counter() - start
        return {"weight": max(1, len(indices)), "unit": "ops", "took": elapsed}

    def __str__(self):
        return "solr-delete-index-bridge"


class SolrCreateIndexBridge(SolrRunner):
    """
    Bridge: maps OSB 'create-index' operation to Solr create-collection.

    Accepts params from CreateIndexParamSource (Solr path):
      - ``indices`` — list of ``(name, configset_path)`` tuples
      - ``num-shards``, ``replication-factor``
    """

    async def __call__(self, solr_not_used, params):
        admin = _admin_client(params)
        indices = params.get("indices", [])
        num_shards = params.get("num-shards", 1)
        replication_factor = params.get("replication-factor", 1)

        start = time.perf_counter()
        for entry in indices:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                col_name, configset_path = entry[0], entry[1]
            elif isinstance(entry, (list, tuple)):
                col_name, configset_path = entry[0], None
            else:
                col_name, configset_path = str(entry), None

            configset = col_name  # configset name == collection name

            if configset_path and os.path.isdir(configset_path):
                await _run_in_executor(admin.upload_configset, configset, configset_path)
                logger.info("Uploaded configset '%s' from '%s'", configset, configset_path)

            try:
                await _run_in_executor(
                    admin.create_collection, col_name, configset, num_shards, replication_factor
                )
            except CollectionAlreadyExistsError:
                logger.warning("Collection '%s' already exists, skipping creation.", col_name)
            except Exception:
                if configset_path:
                    try:
                        await _run_in_executor(admin.delete_configset, configset)
                    except Exception as cleanup_exc:
                        logger.warning("Failed to clean up configset '%s': %s", configset, cleanup_exc)
                raise

        elapsed = time.perf_counter() - start
        return {"weight": max(1, len(indices)), "unit": "ops", "took": elapsed}

    def __str__(self):
        return "solr-create-index-bridge"


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

    # paginated-search and scroll-search → same runner as search
    _search_runner = SolrSearch()
    register_runner("paginated-search", _search_runner, async_runner=True)
    register_runner("scroll-search", _search_runner, async_runner=True)

    # refresh → commit (reuse SolrCommit runner)
    register_runner("refresh", SolrRefreshBridge(), async_runner=True)

    # No-op bridges for OpenSearch-specific operations that have no Solr equivalent.
    # Covering every OperationType from workload.py so that any standard OSB
    # workload can be run against Solr without raising "unknown operation" errors.
    for _op in (
        # Index/shard admin — no direct Solr equivalent
        "cluster-health",
        "force-merge",
        "index-stats",
        "node-stats",
        "put-settings",
        "shrink-index",
        "wait-for-recovery",
        # Ingest pipelines (Solr has no concept of ingest pipelines)
        "put-pipeline",
        "delete-pipeline",
        # Index/data-stream templates
        "create-index-template",
        "delete-index-template",
        "create-composable-template",
        "delete-composable-template",
        "create-component-template",
        "delete-component-template",
        "create-data-stream",
        "delete-data-stream",
        # Snapshot / restore
        "create-snapshot-repository",
        "delete-snapshot-repository",
        "create-snapshot",
        "restore-snapshot",
        "wait-for-snapshot-create",
        # Transforms
        "create-transform",
        "start-transform",
        "wait-for-transform",
        "delete-transform",
        # Async search (Solr has no async search API)
        "submit-async-search",
        "get-async-search",
        "delete-async-search",
        # Point-in-time (Solr has no PIT concept)
        "create-point-in-time",
        "delete-point-in-time",
        "list-all-point-in-time",
        # Search pipeline (OpenSearch-specific)
        "create-search-pipeline",
        # Vector / KNN (Solr has its own dense-vector support but separate ops)
        "vector-search",
        "bulk-vector-data-set",
        "train-knn-model",
        "delete-knn-model",
        # ML model operations (OpenSearch ML Commons — no Solr equivalent)
        "register-ml-model",
        "deploy-ml-model",
        "delete-ml-model",
        "create-ml-connector",
        "register-remote-ml-model",
        "delete-ml-connector",
        # Streaming ingestion (Kafka-based, not applicable to Solr)
        "produce-stream-message",
        # Concurrent segment search settings
        "update-concurrent-segment-search-settings",
    ):
        register_runner(_op, SolrNoOpBridge(_op), async_runner=True)
