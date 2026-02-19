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
            run_metadata: dict containing at minimum:
                - "run_id": str   — unique run identifier (ISO timestamp)
                - "workload": str — workload name
                - "challenge": str — challenge name
                - "solr_version": str — detected Solr version string
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
{results_path}/{run_id}/
├── results.json   ← all metrics as JSON
├── results.csv    ← flattened CSV
└── summary.txt    ← markdown table (also printed to stdout)
```

Behaviour:
- `open()`: creates the run directory
- `write()`: appends metrics to the in-memory accumulator
- `close()`: writes `results.json`, `results.csv`, `summary.txt`; prints summary to stdout

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
