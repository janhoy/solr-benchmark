# Contract: ResultWriter Interface

**Feature**: 001-solr-benchmark-fork
**Date**: 2026-02-19
**Module**: `osbenchmark/solr/result_writer.py`

---

## Purpose

`ResultWriter` is the abstract base class for all benchmark result output destinations. Implementations write completed benchmark results to a specific backend (filesystem, S3, database, etc.).

The local filesystem writer is the default and ships with the tool. Additional writers can be added by subclassing `ResultWriter` and registering them in `WRITER_REGISTRY`.

---

## Abstract Interface

```python
from abc import ABC, abstractmethod

class ResultWriter(ABC):

    @abstractmethod
    def open(self, run_metadata: dict) -> None:
        """
        Called once before any metrics are written.

        Args:
            run_metadata: dict containing benchmark run metadata including:
                - "run_id": str              — unique run identifier (ISO timestamp)
                - "timestamp": float         — Unix epoch seconds when run started
                - "workload": str            — workload name
                - "test_procedure": str      — test procedure (challenge) name
                - "pipeline": str            — pipeline used (e.g., "docker", "from-distribution")
                - "distribution-version": str — Solr version string (in cluster metadata)
                - "user-tags": dict          — user-provided tags/labels for custom annotations
                - "cluster-config-instance": list — cluster-config name(s) used (e.g., ["4gheap"])
                - "cluster-config-spec": dict — complete cluster configuration specification:
                    - "variables": dict           — all config variables (heap_size, GC settings, etc.)
                    - "base_configs": list        — chain of base configs (e.g., ["vanilla"])
                    - "template_paths": list      — paths to config templates used
                    - "effective_settings": dict  — resolved configuration values after template rendering

        Note: This metadata supports time-series analysis by enabling comparison
        of benchmark runs across different cluster configurations, versions, and settings.
        The cluster-config-spec is critical for result portal display, allowing users to
        filter/group results by configuration (e.g., "all 4GB heap runs" vs "all 8GB heap runs").
        """

    @abstractmethod
    def write(self, metrics: list[dict]) -> None:
        """
        Write a batch of metric records.

        Called one or more times after open(). Each call receives a list of
        metric record dicts. A single run may produce multiple write() calls.

        Each metric dict contains:
            - "name": str          — metric name (e.g., "bulk_indexing_throughput")
            - "value": float       — numeric value
            - "unit": str          — unit string (e.g., "docs/s", "ms", "bytes")
            - "task": str          — operation name
            - "operation_type": str — operation type
            - "sample_type": str   — "normal" or "warmup"
            - "timestamp": float   — Unix epoch seconds
            - "meta": dict         — optional additional labels (may be empty)
        """

    @abstractmethod
    def close(self) -> None:
        """
        Flush and close. Called once after all metrics have been written.
        Must be safe to call even if open() or write() raised an exception
        (i.e., implement as a no-op if not opened).
        """
```

---

## Contract Rules

1. `open()` is always called before the first `write()`.
2. `write()` may be called zero or more times between `open()` and `close()`.
3. `close()` is always called exactly once, even if a previous method raised.
4. Implementations MUST be idempotent on `close()` — calling it twice must not raise.
5. Implementations MUST NOT suppress exceptions from `open()` or `write()` — let them propagate so the benchmark framework can handle them.
6. `write()` receives non-empty lists only — the framework will not call it with an empty list.

---

## Registry and Factory

```python
# In result_writer.py

WRITER_REGISTRY: dict[str, type[ResultWriter]] = {
    "local_filesystem": LocalFilesystemResultWriter,
}

def create_writer(name: str) -> ResultWriter:
    if name not in WRITER_REGISTRY:
        raise exceptions.SystemSetupError(
            f"Unknown results_writer '{name}'. "
            f"Available: {', '.join(WRITER_REGISTRY)}"
        )
    return WRITER_REGISTRY[name]()
```

Selected via `benchmark.ini`:
```ini
[reporting]
results_writer = local_filesystem
results_path = ~/.solr-benchmark/results
```

---

## Default Implementation: `LocalFilesystemResultWriter`

Writes results to the path configured in `results_path`:

```
{results_path}/YYYYMMDD_HHMMSS_<run-id-prefix>/
├── test_run.json  ← complete benchmark metadata + results (copied from test-runs store)
├── results.csv    ← flattened CSV of key metrics
└── summary.txt    ← markdown table (also printed to stdout)
```

Behaviour:
- `open()`: creates the timestamped run directory (e.g., `20260222_143052_a34ff090/`)
- `write()`: appends metrics to the in-memory accumulator
- `close()`: copies `test_run.json` from the test-runs store, generates `results.csv` and `summary.txt`, prints summary to stdout

**Primary Result Format: test_run.json**

The `test_run.json` file (copied from `~/.solr-benchmark/benchmarks/test-runs/<run-id>/test_run.json`) is the complete canonical record of the benchmark run. It contains:
- Benchmark version and revision
- Environment name
- Test run ID and timestamp (ISO 8601)
- Pipeline type (docker, from-distribution, benchmark-only, etc.)
- **User tags** (custom labels via `--user-tag`)
- Workload name and revision
- Test procedure (challenge) name
- **Cluster configuration name** (e.g., "4gheap", "external")
- **Cluster configuration specification** (all variables, heap_size, GC settings, template paths, effective configuration values)
- Distribution version and flavor
- **Complete results**: operation metrics, correctness metrics, profile metrics, system metrics (GC, merge times, segment counts, etc.)

**Rationale for Using test_run.json**:
The tool already creates this comprehensive file in the test-runs store. Rather than duplicating data by creating a separate custom format, the result writer copies this single source of truth into each results directory. This ensures:
- No format duplication or metadata drift
- All metadata needed for time-series analysis is present (including complete cluster-config specification)
- Single canonical record per benchmark run
- Result portal can filter/group runs by cluster configuration (e.g., all 4GB heap runs)
- Users can correlate performance changes with configuration changes
- CSV and summary.txt remain available as convenience formats

---

## Testing Guidance

To test code that depends on a `ResultWriter`, use a `Mock(spec=ResultWriter)`:

```python
from unittest.mock import Mock
from osbenchmark.solr.result_writer import ResultWriter

mock_writer = Mock(spec=ResultWriter)
# Inject into the system under test
# Assert calls:
mock_writer.open.assert_called_once_with(...)
mock_writer.write.assert_called()
mock_writer.close.assert_called_once()
```

To test a concrete implementation, call `open()` → `write([...])` → `close()` in sequence and assert on output.
