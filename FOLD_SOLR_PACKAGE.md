# Refactor: Fold `osbenchmark/solr/` into original OSB file locations

## Why

OSB (OpenSearch Benchmark) was a monolithic, single-backend framework — there was **never** an
`osbenchmark/opensearch/` package. All backend logic lived inline: telemetry in
`osbenchmark/telemetry.py`, runners in `osbenchmark/worker_coordinator/runner.py`, the client in
`osbenchmark/client.py`, etc.

The ASB fork created a new `osbenchmark/solr/` sub-package to hold Solr-specific code. This was
unnecessary because there is no plugin boundary to respect and the framework was always
single-backend. The purer port replaces OSB code **in-place**, exactly as OSB itself was structured.

The one exception is `conversion/`, which is genuinely new code (no OSB counterpart). It moves up
to `osbenchmark/conversion/` rather than disappearing.

---

## File Movements

| Source | Destination | Action |
|--------|-------------|--------|
| `osbenchmark/solr/client.py` | `osbenchmark/client.py` | Merge inline |
| `osbenchmark/solr/runner.py` | `osbenchmark/worker_coordinator/runner.py` | Merge inline |
| `osbenchmark/solr/telemetry.py` | `osbenchmark/telemetry.py` | Merge inline |
| `osbenchmark/solr/provisioner.py` | `osbenchmark/builder/solr_provisioner.py` | Move |
| `osbenchmark/solr/result_writer.py` | `osbenchmark/result_writer.py` | Move |
| `osbenchmark/solr/conversion/` | `osbenchmark/conversion/` | Move whole package |
| `osbenchmark/solr/schema_generator.py` | *(deleted)* | Deprecated shim |
| `osbenchmark/solr/__init__.py` + dir | *(deleted)* | Empty after moves |

---

## Step-by-Step

### Commit A — Merge client + runner + telemetry

**Step 1: `solr/client.py` → `osbenchmark/client.py`**
- Add module-level imports: `import io`, `import zipfile`, `from pathlib import Path`
- Copy `SolrClientError`, `CollectionAlreadyExistsError`, `CollectionNotFoundError`, and full
  `SolrAdminClient` class into `client.py` **above** `SolrClient`
- Remove the lazy `from osbenchmark.solr.client import SolrAdminClient` inside `SolrClient.__init__`
- Update `tests/unit/solr/test_client.py` imports

**Step 2: `solr/runner.py` → `osbenchmark/worker_coordinator/runner.py`**
- Remove `from osbenchmark.solr import runner as solr_runner`
- Add `import pysolr`; add `from osbenchmark.client import CollectionAlreadyExistsError, CollectionNotFoundError`
- Temporarily copy `_parse_prometheus_text` (replaced by import in Step 3)
- Copy all helpers, `SolrRunner` base, and 8 runner classes into runner.py
- In `register_default_runners()`: replace `solr_runner.register_solr_runners(register_runner)` with
  the inlined registration calls; delete `register_solr_runners()` function
- Update `tests/unit/solr/test_runner.py` imports

**Step 3: `solr/telemetry.py` → `osbenchmark/telemetry.py`**
- Add `import re` and `from abc import abstractmethod` at top
- Remove lazy import in `list_telemetry()`, change `solr_telemetry.SolrXxx` → `SolrXxx`
- Copy `_parse_prometheus_text`, `SolrTelemetryDevice` base, and 6 concrete devices into telemetry.py
  (removing their `from osbenchmark.telemetry import TelemetryDevice` import — same file now)
- In `worker_coordinator/worker_coordinator.py`: remove lazy `from osbenchmark.solr import telemetry
  as solr_telemetry`; replace `solr_telemetry.Xxx` with `telemetry.Xxx`
- In `runner.py`: replace temporary `_parse_prometheus_text` copy with
  `from osbenchmark.telemetry import _parse_prometheus_text`
- Update `tests/unit/solr/test_telemetry.py` imports

### Commit B — Move provisioner + result_writer

**Step 4: `solr/provisioner.py` → `osbenchmark/builder/solr_provisioner.py`**
- Single flat file (SolrProvisioner + SolrDockerLauncher together)
- Update `osbenchmark/test_run_orchestrator.py`:
  `from osbenchmark.solr.provisioner import ...` → `from osbenchmark.builder.solr_provisioner import ...`
- Update `tests/unit/solr/test_provisioner.py`

**Step 5: `solr/result_writer.py` → `osbenchmark/result_writer.py`**
- Update `osbenchmark/publisher.py`:
  `from osbenchmark.solr import result_writer as solr_result_writer` → `from osbenchmark import result_writer`
- Update `tests/unit/solr/test_result_writer.py`

### Commit C — Move conversion package

**Step 6: `solr/conversion/` → `osbenchmark/conversion/`**
- Move 6 files; create `osbenchmark/conversion/__init__.py`
- Update `osbenchmark/benchmark.py`: `from osbenchmark.solr.conversion import workload_converter`
  → `from osbenchmark.conversion import workload_converter`
- Update `osbenchmark/test_run_orchestrator.py`: `from osbenchmark.solr.conversion.detector import ...`
  → `from osbenchmark.conversion.detector import ...`
- Update all `tests/unit/solr/` test imports for `osbenchmark.solr.conversion.*`

### Commit D — Delete deprecated shim + empty package

**Step 7**: Delete `osbenchmark/solr/schema_generator.py` (deprecated shim)
  — update `tests/unit/solr/test_schema_generator.py` to import from `osbenchmark.conversion.schema`

**Step 8**: Delete `osbenchmark/solr/__init__.py` and remove the now-empty `osbenchmark/solr/` directory

---

## Circular Import Resolution

| Was | After |
|-----|-------|
| `telemetry.py` lazy-imports `solr/telemetry.py` to avoid A→B→A cycle | Resolved: `TelemetryDevice` and `SolrJvmStats` etc. live in the same file |
| `runner.py` imports `solr/runner.py` which imports `solr/client.py` | Resolved: all in same files after Steps 1–2 |
| `runner.py` imports `_parse_prometheus_text` from `telemetry.py` | Acceptable one-way dependency |

---

## Verification

After each commit group:
```bash
python -m py_compile osbenchmark/client.py osbenchmark/telemetry.py \
  osbenchmark/worker_coordinator/runner.py \
  osbenchmark/worker_coordinator/worker_coordinator.py \
  osbenchmark/publisher.py osbenchmark/test_run_orchestrator.py \
  osbenchmark/benchmark.py

make test
python -m osbenchmark.benchmark --help
```

Final check — zero residual references to `osbenchmark.solr`:
```bash
grep -r "osbenchmark\.solr" osbenchmark/ tests/ --include="*.py"
```
