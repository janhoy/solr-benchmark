# Implementation Plan: Solr Benchmark Fork

**Branch**: `001-solr-benchmark-fork` | **Date**: 2026-02-24 | **Spec**: `specs/001-solr-benchmark-fork/spec.md`
**Input**: Feature specification from `/specs/001-solr-benchmark-fork/spec.md`

## Summary

Fork OpenSearch Benchmark into a standalone Apache Solr benchmarking tool (`solr-benchmark`). The fork retains >75% of the original framework code (actor-based concurrency, scheduling engine, metrics aggregation, report generation) while replacing all OpenSearch-specific components with Solr equivalents: HTTP client via pysolr/requests, Solr V2 API admin operations, Solr-native runners (bulk-index, search, commit, optimize, create/delete-collection), Solr telemetry probes, a local filesystem result writer, and a Solr provisioner for both distribution-based and Docker-based workflows.

**Current state (as of 2026-02-24)**: The original 39-task implementation is complete and the tool runs end-to-end against Solr 9.x. The remaining work focuses on three directives from the 2026-02-24 spec update:

1. **No auto-conversion at run time**: Replace `_maybe_auto_convert_workload()` with detection → hard error
2. **Isolated conversion module**: Verify `osbenchmark/solr/conversion/` has no circular imports from the run path; remove bridge runners
3. **Workload repository URL**: Fix `benchmark.ini` `default.url` → `https://github.com/janhoy/solr-benchmark-workloads`

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: pysolr 3.x (data operations), requests (admin HTTP), thespian (actor model), pytest (tests), tabulate (console tables)
**Storage**: Local filesystem — JSON/CSV result files at `~/.solr-benchmark/`, SQLite test-runs store
**Testing**: pytest (`tests/unit/solr/`); run: `python -m pytest tests/unit/solr/ -q`
**Target Platform**: Linux/macOS server with Python 3.10+, Java 21 for provisioning
**Project Type**: Single Python package (`osbenchmark/` + thin `solrbenchmark/` entry-point wrapper)
**Performance Goals**: Support indexing 10k–165M document corpora; benchmark throughput measured in docs/s and ops/s
**Constraints**: macOS fork-safety (`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`; `session.trust_env = False` in all post-fork sessions); no external metrics store
**Scale/Scope**: Single-node and SolrCloud topologies; Solr 9.x primary, Solr 10.x secondary

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No constitution file has been configured for this project. All design decisions are governed by the spec clarifications. The following gates are applied from the spec:

| Gate | Status |
|------|--------|
| ASF licensing compliance | ✓ PASS — NOTICE, LICENSE, per-file headers completed |
| No OpenSearch branding in user-facing output | ✓ PASS — all CLI, banners, help text updated |
| ≥75% original code retained | ✓ PASS — only Solr-incompatible modules replaced |
| Generic framework (actor, scheduling, metrics agg) unchanged | ✓ PASS — `worker_coordinator`, `metrics.py` framework code retained |
| Conversion code isolated from run path | ⚠ IN PROGRESS — bridge runners still exist in `runner.py`; `_maybe_auto_convert_workload` still does auto-convert |
| `benchmark.ini` default.url points to Solr workloads repo | ✗ FAIL — still points to opensearch-project repo |

## Project Structure

### Documentation (this feature)

```text
specs/001-solr-benchmark-fork/
├── plan.md              # This file
├── research.md          # Phase 0 output (see below)
├── data-model.md        # Phase 1 output (see below)
├── quickstart.md        # Phase 1 output (see below)
├── contracts/           # Phase 1 output (see below)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
osbenchmark/
├── benchmark.py                    # CLI entry point — convert-workload subcommand, run subcommand
├── test_run_orchestrator.py        # Run pipeline — _maybe_auto_convert_workload() → replace with detection+error
├── resources/
│   └── benchmark.ini               # default.url — MUST be updated to Solr workloads repo
├── solr/
│   ├── __init__.py
│   ├── client.py                   # SolrAdminClient + SolrClientShim
│   ├── runner.py                   # Solr runners — bridge runners to be REMOVED
│   ├── provisioner.py              # SolrProvisioner + SolrDockerLauncher
│   ├── telemetry.py                # SolrJvmStats, SolrNodeStats, SolrCollectionStats
│   ├── result_writer.py            # ResultWriter ABC + LocalFilesystemResultWriter
│   ├── schema_generator.py         # Auto-schema generation (convenience fallback)
│   └── conversion/                 # ISOLATED conversion utility — no imports from run path
│       ├── __init__.py
│       ├── detector.py             # OSB vs Solr workload format detection
│       ├── query.py                # OpenSearch DSL → Solr JSON Query translation
│       ├── schema.py               # OpenSearch mapping → Solr schema.xml
│       ├── field.py                # Field type mapping helpers
│       └── workload_converter.py   # Top-level converter orchestrating the above
└── tools/
    └── migrate_workload.py         # Legacy migration helper (distinct from conversion/)

solrbenchmark/
├── __init__.py
└── main.py                         # Thin entry-point wrapper

tests/unit/solr/
├── test_client.py
├── test_runner.py
├── test_telemetry.py
├── test_result_writer.py
├── test_provisioner.py
├── test_schema_generator.py
└── conversion/
    ├── test_detector.py
    ├── test_query.py
    └── test_workload_converter.py
```

**Structure Decision**: Single Python project. The `osbenchmark/solr/conversion/` sub-package is the sole home of workload conversion logic — it is a standalone utility that the `convert-workload` CLI subcommand calls directly. It MUST NOT be imported from the benchmark run path (other than `detector.py` which is used for format detection → error).

## Phase 0: Research

All foundational research is complete (original 39 tasks). The remaining research applies only to the three pending directives:

### R-01: Isolation boundary for conversion module

**Finding**: `osbenchmark/solr/conversion/` already exists as a standalone module. The problematic coupling is in `test_run_orchestrator.py` where `_maybe_auto_convert_workload()` imports from `workload_converter` (full conversion). Per FR-018b, only `detector.py` may be imported from the run path — and only to detect the format and abort with an error.

**Decision**: Replace `_maybe_auto_convert_workload()` body with:
1. Load workload path from config
2. Call `detector.is_opensearch_workload_path(workload_path)` (new function in `detector.py`)
3. If True → print ERROR message with `convert-workload` command → raise `exceptions.SystemSetupError`
4. If False → no-op

### R-02: Bridge runners to remove

**Finding**: The following bridge runner classes in `osbenchmark/solr/runner.py` map OpenSearch operation types at runtime — violating FR-018g which mandates that all operation type mapping happens at workload conversion time:

| Class | Maps | Remove? |
|-------|------|---------|
| `SolrRefreshBridge` | `refresh` → commit | YES |
| `SolrNoOpBridge` | various OS ops → no-op | YES |
| `SolrDeleteIndexBridge` | `delete-index` → delete-collection | YES |
| `SolrCreateIndexBridge` | `create-index` → create-collection | YES |
| `SolrBulkBridge` | `bulk` (OS NDJSON) → bulk-index | YES |

**Decision**: Remove all five bridge classes and their `register_runner()` calls. Solr-native workloads use `bulk-index`, `create-collection`, `delete-collection` directly.

### R-03: Search runner OpenSearch DSL error (FR-018f)

**Finding**: The current `SolrSearch.__call__()` accepts Mode 3 (OpenSearch DSL body where `body["query"]` is a dict) and auto-translates it at runtime. Per FR-018f, this should now raise an error — the workload should never reach the runner in OSB DSL format because FR-018b aborts at load time.

**Decision**: In `SolrSearch.__call__()`, when `body["query"]` is a `dict`, raise `exceptions.BenchmarkAssertionError` with a clear message: "Query body contains OpenSearch DSL (query is a dict). Convert this workload first using `solr-benchmark convert-workload`."

### R-04: detector.py file-path entry point

**Finding**: The current `detector.py` exports `is_opensearch_workload(workload)` which takes a loaded workload object. `test_run_orchestrator.py` needs to detect format before loading (to abort early). `workload_converter.py` has `detect_workload_format_from_file(path)` but this lives in the converter (wrong boundary).

**Decision**: Add `is_opensearch_workload_path(workload_path: str) -> bool` to `detector.py` that reads the workload JSON file from disk and checks for `"indices"` vs `"collections"` key. This function may be imported by `test_run_orchestrator.py` without pulling in any conversion code.

## Phase 1: Design & Contracts

### Data Model (unchanged from original design)

No data model changes. The `Workload` entity already has `collections` (Solr) vs `indices` (OSB) as the discriminator.

### API Contracts (updated)

#### `osbenchmark/solr/conversion/detector.py` (updated interface)

```python
def is_opensearch_workload_path(workload_path: str) -> bool:
    """
    Read the workload JSON from disk and return True if it is an OpenSearch workload.
    Raises no exceptions — returns False for missing/unparseable files (not OSB).
    """

def is_opensearch_workload(workload) -> bool:
    """Existing: takes loaded workload object."""
```

#### `osbenchmark/test_run_orchestrator.py` (updated method)

```python
def _check_workload_is_solr_native(self):
    """
    Detect workload format. If OpenSearch format detected, abort with clear error.
    DOES NOT perform conversion. DOES NOT import workload_converter.
    """
```

#### `osbenchmark/solr/runner.py` (updated SolrSearch)

```python
# In SolrSearch.__call__(): Mode 3 detection
if isinstance(body.get("query"), dict):
    raise exceptions.BenchmarkAssertionError(
        "Query body contains OpenSearch DSL. Convert this workload first: "
        "`solr-benchmark convert-workload --workload-path <src> --output-path <dest>`"
    )
```

#### `osbenchmark/resources/benchmark.ini` (updated URL)

```ini
[workloads]
default.url = https://github.com/janhoy/solr-benchmark-workloads
```

### Quickstart

**To run a Solr-native benchmark:**
```bash
# Against a running Solr instance
solr-benchmark run --pipeline=benchmark-only \
  --target-hosts=localhost:8983 \
  --workload-path=/path/to/solr-workload

# If you have an OpenSearch workload, convert first:
solr-benchmark convert-workload \
  --workload-path=/path/to/osb-workload \
  --output-path=/path/to/solr-workload

# Then run the converted workload
solr-benchmark run --pipeline=benchmark-only \
  --target-hosts=localhost:8983 \
  --workload-path=/path/to/solr-workload
```

**Error message shown when OSB workload is detected at run time:**
```
[ERROR] This workload is in OpenSearch Benchmark format.
        Run `solr-benchmark convert-workload --workload-path <src> --output-path <dest>` to convert it to Solr format first.
```

## Remaining Implementation Tasks

The following tasks remain from the updated spec (all original 39 tasks are complete):

### Task A: Fix benchmark.ini default.url (1 line)
- **File**: `osbenchmark/resources/benchmark.ini`
- **Change**: `default.url = https://github.com/janhoy/solr-benchmark-workloads`

### Task B: Add `is_opensearch_workload_path()` to detector.py
- **File**: `osbenchmark/solr/conversion/detector.py`
- **Change**: New function that reads workload JSON from disk and checks for OSB format markers

### Task C: Replace auto-convert with detection+error in test_run_orchestrator.py
- **File**: `osbenchmark/test_run_orchestrator.py`
- **Change**: Replace `_maybe_auto_convert_workload()` body — detect OSB format → raise error with helpful message; rename method to `_check_workload_is_solr_native()` or update in-place

### Task D: Remove bridge runners from runner.py
- **File**: `osbenchmark/solr/runner.py`
- **Change**: Remove `SolrRefreshBridge`, `SolrNoOpBridge`, `SolrDeleteIndexBridge`, `SolrCreateIndexBridge`, `SolrBulkBridge` classes and their `register_runner()` calls

### Task E: Update SolrSearch to error on OpenSearch DSL (FR-018f)
- **File**: `osbenchmark/solr/runner.py` — `SolrSearch.__call__()`
- **Change**: Detect `body["query"]` is dict → raise `BenchmarkAssertionError` with convert-workload hint

### Task F: Update/add unit tests
- **Files**: `tests/unit/solr/conversion/test_detector.py`, `tests/unit/solr/test_runner.py`
- **Change**: Test new `is_opensearch_workload_path()`, test error path in SolrSearch, test removal of bridge runners

## Complexity Tracking

No constitution violations. The conversion module isolation is a simplification (removing code), not an addition.
