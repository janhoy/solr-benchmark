# Plan: Remove `opensearchpy` Hard Dependency

## Problem

`opensearchpy` is the OpenSearch Python client. The fork retains many OSB modules
that import it. Currently these are wrapped in `try/except ImportError` as a stopgap,
but:

1. The core benchmark execution loop (`worker_coordinator.py`) imports it at runtime
   (inside a function) and catches its exception hierarchy — so Solr benchmark runs
   will break when an error occurs, even without opensearchpy installed.
2. `opts.py` calls `_normalize_hosts` from opensearchpy internals to parse
   `--target-hosts` arguments — so even host parsing fails without the package.
3. Future contributors will be confused about which modules still require opensearchpy.

## Goal

`opensearchpy` becomes a **fully optional** dependency — required only when
benchmarking an actual OpenSearch cluster. All Solr code paths must work without it.

---

## Affected Files (by category)

### Category A — Easy replacement (no opensearchpy needed at all)

| File | What to fix |
|------|-------------|
| `osbenchmark/utils/opts.py` | Replace `_normalize_hosts` with inline stdlib impl |
| `osbenchmark/worker_coordinator/runner.py` | Replace dummy `ConnectionTimeout`/`NotFoundError` fallbacks with proper custom exceptions from `osbenchmark/exceptions.py` |

### Category B — Core: decouple from opensearchpy exception hierarchy

| File | What to fix |
|------|-------------|
| `osbenchmark/worker_coordinator/worker_coordinator.py` | `_run_and_measure()` catches `opensearchpy.TransportError` and its subclasses; replace with abstract exceptions |

### Category C — OpenSearch-only modules (keep, but make cleanly optional)

These modules are 100% OpenSearch-specific. They should remain but must be clearly
marked as optional, only loaded when opensearchpy is present:

| File | Status |
|------|--------|
| `osbenchmark/telemetry.py` (OS parts) | Already conditional; keep as-is |
| `osbenchmark/metrics.py` | Already conditional; keep as-is |
| `osbenchmark/cloud_provider/vendors/aws.py` | Already conditional; keep as-is |
| `osbenchmark/builder/builder.py` | Already conditional; keep as-is |
| `osbenchmark/workload_generator/extractors.py` | Already conditional; keep as-is |

---

## Implementation Tasks

### Task 1 — Add abstract network exceptions to `osbenchmark/exceptions.py`

Add three new exception classes to the common exceptions module so all backends
(OpenSearch, Solr, future targets) can signal the same error conditions:

```python
class BenchmarkTransportError(BenchmarkError):
    """HTTP/transport-level error from any benchmark target."""
    def __init__(self, message="", status_code=None, error=None, info=None):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.info = info

class BenchmarkConnectionError(BenchmarkTransportError):
    """Connection refused / target unreachable."""

class BenchmarkConnectionTimeout(BenchmarkTransportError):
    """Connection timed out."""
```

### Task 2 — Fix `opts.py`: remove `_normalize_hosts` dependency

`_normalize_hosts` parses strings like `"localhost:9200"` or
`"host1:9200,host2:9200"` into `[{"host": "localhost", "port": 9200}]`.
Replace with a stdlib implementation using `urllib.parse`:

```python
def _parse_host_string(arg):
    """Parse comma-separated host[:port] strings into list of dicts."""
    results = []
    for item in str(arg).split(","):
        item = item.strip()
        if not item:
            continue
        # Handle scheme://host:port or host:port
        if "://" not in item:
            item = "http://" + item
        parsed = urllib.parse.urlparse(item)
        entry = {"host": parsed.hostname or "localhost"}
        if parsed.port:
            entry["port"] = parsed.port
        if parsed.scheme and parsed.scheme != "http":
            entry["scheme"] = parsed.scheme
        results.append(entry)
    return results
```

### Task 3 — Fix `worker_coordinator.py`: decouple from opensearchpy exceptions

The `_run_and_measure()` function (around line 2540) does an inline
`import opensearchpy` and catches `opensearchpy.TransportError` and subclasses.
The fix has two parts:

**Part A** — In `runner.py`, wrap Solr runners so that `pysolr.SolrError` and
`requests` exceptions are translated to `BenchmarkTransportError` / subclasses.
This can be done in `osbenchmark/solr/runner.py` with a decorator or base class.

**Part B** — In `worker_coordinator.py`, replace:

```python
import opensearchpy
...
except opensearchpy.TransportError as e:
    if type(e) is opensearchpy.ConnectionError: ...
    if isinstance(e, opensearchpy.ConnectionTimeout): ...
    if isinstance(e.status_code, int): ...
```

with:

```python
from osbenchmark.exceptions import BenchmarkTransportError, BenchmarkConnectionError, BenchmarkConnectionTimeout

# Also catch opensearchpy exceptions if opensearchpy is available, translating them
try:
    import opensearchpy as _opensearchpy
except ImportError:
    _opensearchpy = None
...
except BenchmarkTransportError as e:
    if isinstance(e, BenchmarkConnectionError):
        fatal_error = True
    ...
    if isinstance(e, BenchmarkConnectionTimeout):
        request_meta_data["error-description"] = "network connection timed out"
    ...
# If opensearchpy is installed, also catch its exceptions and convert
except Exception as e:
    if _opensearchpy and isinstance(e, _opensearchpy.TransportError):
        # Convert to BenchmarkTransportError and re-handle
        ...
```

The cleanest approach: add a **translation shim** in `client.py` that wraps all
opensearchpy exceptions at the client level so they never escape as opensearchpy
types. The runner only ever sees `BenchmarkTransportError`.

### Task 4 — Update `runner.py` dummy fallbacks

The current pattern in `runner.py` defines throwaway fallback classes:

```python
try:
    from opensearchpy import ConnectionTimeout, NotFoundError
except ImportError:
    class ConnectionTimeout(Exception): pass
    class NotFoundError(Exception): pass
```

Replace with:

```python
try:
    from opensearchpy import ConnectionTimeout, NotFoundError
except ImportError:
    from osbenchmark.exceptions import BenchmarkConnectionTimeout as ConnectionTimeout
    from osbenchmark.exceptions import BenchmarkNotFoundError as NotFoundError
```

(Add `BenchmarkNotFoundError` to `exceptions.py`.)

---

## Recommended Implementation Order

1. **exceptions.py** — add abstract exceptions (no risk, pure addition)
2. **opts.py** — replace `_normalize_hosts` (self-contained, testable)
3. **runner.py** — swap dummy classes for real exceptions
4. **solr/runner.py** — translate pysolr/requests errors to Benchmark exceptions
5. **worker_coordinator.py** — switch exception catching to abstract types + translation shim

Each step is independently testable. Steps 1–3 can be done in one commit. Steps 4–5
are the main payoff: after them, a complete Solr benchmark run with network errors
will produce correct metrics (error-type, http-status, error-description) in the
same way as OpenSearch runs.

---

## What Does NOT Need to Change

The following retain opensearchpy imports (guarded) and are fine as optional:
- `telemetry.py` (OS telemetry collectors)
- `metrics.py` (OS metrics datastore)
- `builder.py` (OS node provisioner)
- `aws.py` (AWS auth for OS)
- `extractors.py` (workload generation from OS clusters)
- `client.py` (OS REST client factory — still needed when benchmarking OS)

These will silently no-op when opensearchpy is not installed. A Solr user who never
benchmarks OpenSearch will never encounter them.

---

## Success Criteria

After implementing:
- `pip install solr-benchmark` (no opensearchpy in install_requires) works
- `solr-benchmark run --pipeline=benchmark-only ...` against a live Solr cluster
  completes a full benchmark run and records correct error metadata when requests fail
- All 60 existing unit tests still pass
- `pip install solr-benchmark[opensearch]` (extras_require) installs opensearchpy
  and enables OS benchmarking features
