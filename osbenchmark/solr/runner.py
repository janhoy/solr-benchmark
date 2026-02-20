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
# OpenSearch → Solr query translation helpers
#
# Best-effort translation of common OpenSearch query DSL patterns to Solr
# query syntax.  Complex or unknown query structures fall back to q=*:*.
# ---------------------------------------------------------------------------

def _solr_escape(value):
    """Escape special Lucene/Solr query characters in a field value."""
    special = r'+-&&||!(){}[]^"~*?:\/'
    result = []
    for char in str(value):
        if char in special:
            result.append('\\' + char)
        else:
            result.append(char)
    return ''.join(result)


def _convert_os_date_to_solr(date_str, os_format=None):
    """
    Convert an OpenSearch date string to Solr ISO 8601 format.

    Args:
        date_str: Date string from OpenSearch query (e.g., "01/01/2015")
        os_format: OpenSearch format string (e.g., "dd/MM/yyyy") or None

    Returns:
        ISO 8601 date string for Solr (e.g., "2015-01-01T00:00:00Z")

    If the date is already in ISO format or conversion fails, returns the
    original string unchanged.
    """
    if not isinstance(date_str, str) or date_str in ("*", "now"):
        return date_str

    # Map OpenSearch date format patterns to Python strptime format
    OS_TO_PYTHON_FORMAT = {
        "dd/MM/yyyy": "%d/%m/%Y",
        "MM/dd/yyyy": "%m/%d/%Y",
        "yyyy-MM-dd": "%Y-%m-%d",
        "yyyy/MM/dd": "%Y/%m/%d",
        "dd-MM-yyyy": "%d-%m-%Y",
        "MM-dd-yyyy": "%m-%d-%Y",
        # Add more as needed
    }

    # If format is provided, use it to parse the date
    if os_format:
        python_fmt = OS_TO_PYTHON_FORMAT.get(os_format)
        if python_fmt:
            try:
                dt = datetime.strptime(date_str, python_fmt)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                logger.warning(f"Failed to parse date '{date_str}' with format '{os_format}'")
                return date_str
        else:
            logger.warning(f"Unknown OpenSearch date format: '{os_format}'")

    # Try common patterns if no format specified
    for python_fmt in OS_TO_PYTHON_FORMAT.values():
        try:
            dt = datetime.strptime(date_str, python_fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    # If it's already in ISO-like format, return as-is
    # (handles cases like "2015-01-01T00:00:00Z" or partial ISO)
    if "T" in date_str or len(date_str) == 10:  # YYYY-MM-DD
        return date_str

    logger.warning(f"Could not parse date '{date_str}', using as-is")
    return date_str


def _os_query_to_solr_q(body):
    """
    Translate an OpenSearch query DSL dict to a Solr ``q`` string.

    Supported patterns:
      - ``match_all``             → ``*:*``
      - ``term``                  → ``field:value``
      - ``terms``                 → ``field:(v1 v2 v3)``
      - ``match`` / ``match_phrase`` → ``field:value``
      - ``range``                 → ``field:[lo TO hi]``
      - ``exists``                → ``field:[* TO *]``
      - ``bool`` (must/filter/should/must_not) → recursive translation
      - ``ids``                   → ``id:(id1 id2 ...)``

    Falls back to ``*:*`` for unrecognised patterns (logs at DEBUG level).
    """
    if not body or not isinstance(body, dict):
        return "*:*"
    query = body.get("query", {})
    return _translate_query_node(query)


def _translate_query_node(node):
    """Recursively translate a single OpenSearch query node."""
    if not node or not isinstance(node, dict):
        return "*:*"

    if "match_all" in node:
        return "*:*"

    if "match_none" in node:
        return "-*:*"

    if "term" in node:
        for field, value in node["term"].items():
            v = value.get("value", value) if isinstance(value, dict) else value
            return f"{field}:{_solr_escape(v)}"

    if "terms" in node:
        for field, values in node["terms"].items():
            if field.startswith("_"):
                continue
            escaped = " ".join(_solr_escape(v) for v in values)
            return f"{field}:({escaped})"

    if "match" in node or "match_phrase" in node:
        sub = node.get("match") or node.get("match_phrase")
        for field, value in sub.items():
            v = value.get("query", value) if isinstance(value, dict) else value
            return f"{field}:{_solr_escape(v)}"

    if "range" in node:
        for field, bounds in node["range"].items():
            lo = bounds.get("gte", bounds.get("gt", "*"))
            hi = bounds.get("lte", bounds.get("lt", "*"))
            # Convert dates if format is specified (common for date fields)
            os_format = bounds.get("format")
            lo = _convert_os_date_to_solr(lo, os_format)
            hi = _convert_os_date_to_solr(hi, os_format)
            return f"{field}:[{lo} TO {hi}]"

    if "exists" in node:
        field = node["exists"].get("field", "*")
        return f"{field}:[* TO *]"

    if "ids" in node:
        values = node["ids"].get("values", [])
        if values:
            escaped = " ".join(_solr_escape(v) for v in values)
            return f"id:({escaped})"
        return "*:*"

    if "bool" in node:
        bool_q = node["bool"]
        parts = []

        def _add(clauses, prefix):
            if not clauses:
                return
            if isinstance(clauses, dict):
                clauses = [clauses]
            for clause in clauses:
                sub = _translate_query_node(clause)
                if sub and sub != "*:*":
                    parts.append(f"{prefix}({sub})")

        _add(bool_q.get("must"), "+")
        _add(bool_q.get("filter"), "+")
        _add(bool_q.get("must_not"), "-")

        shoulds = bool_q.get("should", [])
        if isinstance(shoulds, dict):
            shoulds = [shoulds]
        should_parts = [_translate_query_node(s) for s in shoulds]
        should_parts = [s for s in should_parts if s and s != "*:*"]
        if should_parts:
            parts.append("(" + " ".join(should_parts) + ")")

        return " ".join(parts) if parts else "*:*"

    # Unknown / untranslatable query node
    logger.warning(
        "Cannot translate OpenSearch query type '%s' to Solr syntax. "
        "Falling back to q=*:* (results may not match workload intent). "
        "Consider rewriting this operation as a native Solr workload task.",
        list(node.keys()),
    )
    return "*:*"


def _extract_sort_param(body):
    """Extract a Solr sort string from an OpenSearch sort clause."""
    if not isinstance(body, dict) or "sort" not in body:
        return None
    sort_clauses = body["sort"]
    if isinstance(sort_clauses, dict):
        sort_clauses = [sort_clauses]
    solr_sorts = []
    for clause in sort_clauses:
        if isinstance(clause, str):
            solr_sorts.append(clause)
        elif isinstance(clause, dict):
            for field, order_info in clause.items():
                if field == "_score":
                    continue
                if isinstance(order_info, dict):
                    order = order_info.get("order", "asc")
                elif isinstance(order_info, str):
                    order = order_info
                else:
                    order = "asc"
                solr_sorts.append(f"{field} {order}")
    return ", ".join(solr_sorts) if solr_sorts else None


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
        logger.info("🔵 SolrBulkIndex.__call__() ENTRY")
        corpus_lines = params.get("corpus", [])
        batch_size = params.get("bulk-size", 500)
        do_commit = params.get("commit", False)

        logger.info(f"🔵 corpus_lines type: {type(corpus_lines)}, batch_size: {batch_size}")

        client = _solr_client(params)

        # Use streaming translation to avoid loading all documents into memory
        doc_stream = _translate_ndjson_stream(corpus_lines)
        logger.info("🔵 Created doc_stream generator")
        total_docs = 0
        errors = 0

        start = time.perf_counter()

        # Collect documents in batches and send to Solr
        batch = []
        doc_count = 0
        for doc in doc_stream:
            batch.append(doc)
            doc_count += 1
            if doc_count == 1:
                logger.info(f"🔵 First document received: {doc}")
            if len(batch) >= batch_size:
                logger.info(f"🔵 Sending batch of {len(batch)} documents to Solr")
                try:
                    # Use commitWithin=1000ms to make docs visible quickly without explicit commits
                    await _run_in_executor(client.add, batch, commit=False, commitWithin=1000)
                    total_docs += len(batch)
                    logger.info(f"🔵 Batch indexed successfully, total so far: {total_docs}")
                except pysolr.SolrError as exc:
                    logger.error("Bulk index error on batch: %s", exc)
                    errors += len(batch)
                batch = []

        # Send remaining documents
        logger.info(f"🔵 Doc stream exhausted. doc_count={doc_count}, remaining batch size: {len(batch)}")
        if batch:
            logger.info(f"🔵 Sending final batch of {len(batch)} documents")
            try:
                await _run_in_executor(client.add, batch, commit=False, commitWithin=1000)
                total_docs += len(batch)
                logger.info(f"🔵 Final batch indexed successfully")
            except pysolr.SolrError as exc:
                logger.error("Bulk index error on final batch: %s", exc)
                errors += len(batch)

        if do_commit:
            logger.info("🔵 Performing explicit commit")
            await _run_in_executor(client.commit)

        elapsed = time.perf_counter() - start
        weight = total_docs - errors
        logger.info(f"🔵 SolrBulkIndex COMPLETE: total_docs={total_docs}, errors={errors}, weight={weight}, elapsed={elapsed:.2f}s")

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
        # Accept 'index' as alias for 'collection' (standard OSB workload format)
        collection = params.get("collection") or params.get("index", "default")
        tls = params.get("tls", False)
        timeout = params.get("timeout", 30)
        scheme = "https" if tls else "http"

        start = time.perf_counter()

        body = params.get("body")
        if body is not None:
            query_val = body.get("query") if isinstance(body, dict) else None

            if isinstance(query_val, dict):
                # Mode 3: OpenSearch query DSL → translate to Solr classic params
                if "aggs" in body or "aggregations" in body:
                    logger.warning(
                        "OpenSearch aggregations are not supported in Solr mode and will be "
                        "ignored (collection=%s). Consider rewriting as a native Solr facet query.",
                        collection,
                    )
                q = _os_query_to_solr_q(body)
                rows = body.get("size", 10) if isinstance(body, dict) else 10
                sort_param = _extract_sort_param(body)

                solr_params = dict(params)
                solr_params["collection"] = collection
                client = _solr_client(solr_params)
                kwargs = {"rows": rows}
                if sort_param:
                    kwargs["sort"] = sort_param
                # OSB uses "request_params" (underscore), Solr workloads use "request-params" (hyphen)
                kwargs.update(params.get("request_params", params.get("request-params", {})))

                results = await _run_in_executor(client.search, q, **kwargs)
                num_hits = results.hits
            else:
                # Mode 2: Solr JSON Query DSL → POST /solr/{collection}/query
                url = f"{scheme}://{host}:{port}/solr/{collection}/query"
                req_headers = {"Content-Type": "application/json"}
                username = params.get("username")
                password = params.get("password")
                auth = (username, password) if username and password else None

                def _do_json_search():
                    resp = requests.post(url, json=body,
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

        # Auto-generate schema from OpenSearch mappings (fallback convenience)
        auto_generated_configset = None
        mappings = params.get("mappings")

        if mappings and not configset_path:
            logger.info(
                "Auto-generating Solr schema from OpenSearch mappings "
                "(convenience fallback - native Solr workloads are recommended)"
            )
            try:
                from osbenchmark.solr.schema_generator import (
                    translate_opensearch_mapping,
                    generate_schema_xml,
                    create_configset_from_schema,
                )

                # Extract field definitions from mappings
                properties = mappings.get("properties", {})
                if properties:
                    # Translate OpenSearch types to Solr types
                    field_defs = translate_opensearch_mapping(properties)

                    # Generate schema.xml
                    schema_xml = generate_schema_xml(field_defs, unique_key="id")

                    # Create temporary configset directory
                    auto_generated_configset = create_configset_from_schema(
                        schema_xml, configset_name=collection
                    )
                    configset_path = auto_generated_configset
                    logger.info("Generated temporary configset at: %s", configset_path)
                else:
                    logger.warning("Mappings present but no properties found, using default configset")

            except Exception as e:
                logger.warning(
                    "Failed to auto-generate schema from mappings: %s. "
                    "Falling back to _default configset.", e
                )
                configset = "_default"

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
        finally:
            # Clean up auto-generated configset
            if auto_generated_configset:
                from osbenchmark.solr.schema_generator import cleanup_configset
                cleanup_configset(auto_generated_configset)

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
# Bridge runners: map standard OSB operation types to Solr equivalents
#
# These are registered in register_solr_runners() to override the default
# OpenSearch-specific runners, allowing standard OSB workloads (e.g. nyc_taxis)
# to run against Solr without modification.
# ---------------------------------------------------------------------------

def _normalize_bulk_body(body):
    """Convert bulk body items (string or dict) to JSON strings (generator)."""
    for item in body:
        if isinstance(item, dict):
            yield json.dumps(item)
        elif isinstance(item, bytes):
            yield item.decode('utf-8')  # Decode bytes to string
        elif item:
            yield str(item)


class SolrDeleteIndexBridge(SolrRunner):
    """
    Bridge: maps OSB 'delete-index' to Solr collection deletion.

    Accepts the same params as the standard delete-index operation:
      - ``indices`` — list of index/collection names to delete
      - ``only-if-exists`` — bool (default: False); errors are always silenced
    Plus Solr connection params (``host``, ``port``, ...) defaulting to localhost:8983.
    """

    async def __call__(self, solr_not_used, params):
        admin = _admin_client(params)
        indices = params.get("indices", [])

        ops = 0
        for name in indices:
            try:
                await _run_in_executor(admin.delete_collection, name)
                ops += 1
            except CollectionNotFoundError:
                pass  # silently skip missing collections (mirrors ES behaviour)

        return {"weight": ops, "unit": "ops", "success": True}

    def __str__(self):
        return "delete-index"


class SolrCreateIndexBridge(SolrRunner):
    """
    Bridge: maps OSB 'create-index' to Solr collection creation.

    For convenience, automatically generates Solr schema.xml from OpenSearch
    mappings when present in the index body. This is a fallback mechanism;
    native Solr workloads with explicit configset-path are recommended.

    Params:
      - ``indices``           — list of (name, body) tuples from the workload
      - ``configset``         — Solr configset name (default: auto-generated from mappings
                                or ``_default`` if no mappings)
      - ``num-shards``        — int (default: 1)
      - ``replication-factor``— int (default: 1)
    Plus Solr connection params (``host``, ``port``, ...) defaulting to localhost:8983.
    """

    async def __call__(self, solr_not_used, params):
        indices = params.get("indices", [])
        base_configset = params.get("configset", "_default")
        num_shards = params.get("num-shards", 1)
        replication_factor = params.get("replication-factor", 1)

        ops = 0
        for entry in indices:
            # indices is a list of (name, body) tuples
            if isinstance(entry, (list, tuple)):
                name = entry[0]
                body = entry[1] if len(entry) > 1 else None
            else:
                name = entry
                body = None

            # Extract mappings from body (if present)
            mappings = None
            if body and isinstance(body, dict):
                mappings = body.get("mappings")

            # If we have mappings and will auto-generate schema, use a unique configset name
            # (not _default, which is a built-in and can't be uploaded)
            if mappings and mappings.get("properties"):
                configset_for_collection = name  # Use collection name as configset name
            else:
                configset_for_collection = base_configset

            # Delegate to SolrCreateCollection with mappings
            collection_params = {
                "collection": name,
                "configset": configset_for_collection,
                "num-shards": num_shards,
                "replication-factor": replication_factor,
                "mappings": mappings,  # Pass mappings for auto-schema generation
            }
            # Preserve connection params
            for key in ("host", "port", "username", "password", "tls", "timeout"):
                if key in params:
                    collection_params[key] = params[key]

            # Call SolrCreateCollection
            create_runner = SolrCreateCollection()
            try:
                await create_runner(solr_not_used, collection_params)
                ops += 1
            except CollectionAlreadyExistsError:
                logger.warning("Collection '%s' already exists, skipping creation.", name)
                ops += 1

        return {"weight": ops, "unit": "ops", "success": True}

    def __str__(self):
        return "create-index"


class SolrBulkBridge(SolrRunner):
    """
    Bridge: maps OSB 'bulk' to Solr document indexing.

    Translates the NDJSON ``body`` from the standard bulk operation into Solr
    documents and indexes them. The target collection is derived from:
      1. ``params["collection"]`` if explicitly set
      2. ``params["index"]`` (standard OSB bulk param)
      3. The ``_index`` field in the first action-metadata line

    Params mirror the standard OSB bulk operation (``body``, ``index``,
    ``bulk-size``, ``unit``, ``action-metadata-present``) plus Solr connection
    params (``host``, ``port``, ...) defaulting to localhost:8983.
    """

    async def __call__(self, solr_not_used, params):
        body = params.get("body", [])
        index = params.get("index", "")
        bulk_size = params.get("bulk-size", 0)
        unit = params.get("unit", "docs")
        batch_size = 500

        # Handle different body formats:
        # - bytes/str: NDJSON data as single blob (split into lines)
        # - list/iterator: already split lines
        if isinstance(body, bytes):
            # Split bytes NDJSON into lines
            lines = body.split(b'\n')
            lines = [line for line in lines if line.strip()]  # Remove empty lines
        elif isinstance(body, str):
            # Split string NDJSON into lines
            lines = body.split('\n')
            lines = [line for line in lines if line.strip()]
        else:
            # Assume it's already an iterable of lines
            lines = body

        if not lines:
            return {"weight": 0, "unit": unit, "success": True, "error-count": 0}

        # Build Solr client params — inject collection from index if not set
        solr_params = dict(params)
        if not solr_params.get("collection"):
            solr_params["collection"] = index or "default"

        client = _solr_client(solr_params)

        # lines is already prepared above (split from bytes/str or passed as iterable)
        # Now normalize each line (convert dicts to JSON strings, etc.)
        normalized_lines = _normalize_bulk_body(lines)

        # Stream-process documents in batches to avoid loading all into memory
        total_docs = 0
        errors = 0
        start = time.perf_counter()

        logger.info("SolrBulkBridge starting - processing %d lines, bulk_size=%d", len(lines) if hasattr(lines, '__len__') else -1, bulk_size)

        batch = []
        doc_count = 0

        for doc in _translate_ndjson_stream(normalized_lines):
            batch.append(doc)
            doc_count += 1
            if len(batch) >= batch_size:
                try:
                    # Use commitWithin=1000ms to make docs visible quickly without explicit commits
                    await _run_in_executor(client.add, batch, commit=False, commitWithin=1000)
                    total_docs += len(batch)
                    if total_docs % 5000 == 0:
                        logger.info("SolrBulkBridge: indexed %d docs so far", total_docs)
                except pysolr.SolrError as exc:
                    logger.error("Bulk bridge error on batch: %s", exc)
                    errors += len(batch)
                batch = []

        # Index remaining documents in partial batch
        if batch:
            try:
                await _run_in_executor(client.add, batch, commit=False, commitWithin=1000)
                total_docs += len(batch)
            except pysolr.SolrError as exc:
                logger.error("Bulk bridge error on final batch: %s", exc)
                errors += len(batch)

        elapsed = time.perf_counter() - start
        weight = total_docs - errors

        return {
            "weight": weight,
            "unit": unit,
            "bulk-size": bulk_size or total_docs,
            "success": errors == 0,
            "error-count": errors,
            "took": elapsed,
        }

    def __str__(self):
        return "bulk"


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

    # Bridge runners: override OSB's default OpenSearch runners so that standard
    # workloads (e.g. nyc_taxis) work against Solr without modification.
    # create-index == create-collection, delete-index == delete-collection, etc.
    register_runner("delete-index", SolrDeleteIndexBridge(), async_runner=True)
    register_runner("create-index", SolrCreateIndexBridge(), async_runner=True)
    register_runner("bulk", SolrBulkBridge(), async_runner=True)

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
