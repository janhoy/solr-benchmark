# Implementation Plan: Solr Benchmark Fork

**Branch**: `001-solr-benchmark-fork` | **Date**: 2026-02-19 | **Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md) | **Data Model**: [data-model.md](./data-model.md)

## Summary

Fork OpenSearch Benchmark (OSB) into a standalone Apache Solr benchmarking tool. Retain the generic actor-based execution framework (~75% of code), replace the OpenSearch client and runners with Solr equivalents (using pysolr for data ops + plain HTTP V2 API for admin), port telemetry to Solr's metrics endpoints, replace the OpenSearch metrics store with a pluggable result writer (filesystem default), add Solr-native provisioning, and comply with ASF licensing requirements.

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**:
- `pysolr` ≥ 3.10 — Solr data operations (indexing, search, commit, optimize)
- `requests` — V2 API admin HTTP calls (already a transitive dependency)
- `aiohttp` — retained for any async HTTP needs in the framework layer
- `thespian` — actor system (retained unchanged)
- `tabulate` — result table formatting (retained)
- `jinja2` — workload templating (retained)
- `elasticsearch-py` — **REMOVED** (replaced by pysolr + requests)

**Storage**: Local filesystem (JSON + CSV result files, configurable path). No external store required.

**Testing**: `pytest` + `tox` (retained). Unit tests mock pysolr and the HTTP client. Integration tests require a live Solr 9.x instance.

**Target Platform**: Linux (primary), macOS (development). Java 11+ required on target host for Solr provisioning.

**Project Type**: Single Python package (CLI tool)

**Performance Goals**: Match or exceed the throughput measurement capability of OSB; overhead of NDJSON action-line translation (extract `_id` → `"id"`, discard `_index`) ≤ 5% of indexing time.

**Constraints**: 75% code retention by line count (SC-003). No runtime dependency on OpenSearch. ASF license compliance required before PMC contribution.

**Scale/Scope**: Single Solr node to multi-node SolrCloud; 1M–100M document corpora; workloads with up to hundreds of operations.

## Constitution Check

*Standard gates for a well-scoped fork of an existing tool:*

- [x] No new database or external service dependency introduced (filesystem result writer is default)
- [x] Existing test infrastructure (pytest/tox) preserved
- [x] No gratuitous abstraction layers — pysolr chosen specifically to reduce custom HTTP code
- [x] Scope bounded: Solr 9.x primary, 10.x secondary, 8.x out of scope

## Project Structure

### Documentation (this feature)

```text
specs/001-solr-benchmark-fork/
├── plan.md              ← This file
├── research.md          ← Phase 0: decisions on API, licensing, structure
├── data-model.md        ← Phase 1: key entities and field shapes
├── quickstart.md        ← Phase 1: developer setup guide
├── contracts/
│   ├── result-writer.md ← ResultWriter ABC interface contract
│   └── solr-client.md  ← SolrAdminClient interface contract
└── tasks.md             ← Phase 2 output (created by /speckit.tasks)
```

### Source Code Layout

```text
osbenchmark/                    ← Retained (implementation package)
├── solr/                       ← NEW: all Solr-specific code
│   ├── __init__.py
│   ├── client.py               ← SolrAdminClient (V2 API via requests)
│   ├── runner.py               ← Solr operation runners (bulk-index, search, commit, optimize, create/delete-collection)
│   ├── telemetry.py            ← Solr telemetry devices (JVM, collection stats, node stats)
│   ├── provisioner.py          ← Solr download/extract/start/stop + Docker support
│   └── result_writer.py        ← ResultWriter ABC + LocalFilesystemResultWriter + registry
├── tools/
│   └── migrate_workload.py     ← NEW: OSB→Solr workload migration utility
├── workload/                   ← Adapted: Solr-native terminology, remove OS-specific params
│   ├── workload.py             ← Rename index→collection, mapping→configset throughout
│   ├── params.py               ← Solr bulk-index params, remove ES-specific params
│   └── loader.py               ← Retained (workload loading logic unchanged)
├── publisher.py                ← Adapted: wire in ResultWriter instead of direct format calls
├── metrics.py                  ← Adapted: remove OpenSearch metrics store backend; retain in-memory aggregation
├── config.py                   ← Adapted: add results_writer key, remove OS-specific keys
├── benchmark.py                ← Adapted: CLI renamed, remove OpenSearch-specific flags
├── benchmarkd.py               ← Adapted: branding only
├── client.py                   ← REPLACED by osbenchmark/solr/client.py (delete original)
├── async_connection.py         ← DELETED (OpenSearch async client)
├── kafka_client.py             ← DELETED (out of scope)
├── data_streaming/             ← DELETED (out of scope)
├── actor.py                    ← RETAINED unchanged
├── aggregator.py               ← RETAINED unchanged
├── worker_coordinator/         ← RETAINED (adapted for Solr runner registration)
└── builder/                    ← ADAPTED: replace OS builder with Solr provisioner hooks

solrbenchmark/                  ← NEW: thin wrapper package (entry point / branding)
├── __init__.py
└── main.py                     ← `solr-benchmark` CLI entry point (re-exports from osbenchmark)

tests/
├── unit/
│   └── solr/                   ← New unit tests for Solr-specific modules
└── integration/
    └── solr/                   ← Integration tests requiring live Solr 9.x

NOTICE                          ← UPDATED: Apache Solr project copyright + OSB + Elasticsearch/Rally attribution chain
LICENSE                         ← UPDATED: reflect Solr PMC identity
```

**Structure Decision**: Retain `osbenchmark/` as the implementation package to meet the 75% code reuse goal. Add `osbenchmark/solr/` as a new subpackage for all Solr-specific code. A thin `solrbenchmark/` wrapper provides the renamed CLI entry point. This is the minimum change needed to rename branding without touching all imports.

## Implementation Phases

### Phase A — Foundation (Unblock all other phases)

**Goal**: Get a working Solr connection, basic indexing, and result output with no OpenSearch dependency.

1. **Delete OpenSearch-only modules**: `async_connection.py`, `kafka_client.py`, `data_streaming/`, gRPC proto stubs
2. **Create `osbenchmark/solr/client.py`**: `SolrAdminClient` wrapping `requests.Session` for V2 API calls. Methods: `get_version()`, `upload_configset(name, configset_dir)` (zips `conf/` in-memory, PUT to `/api/cluster/configs/{name}`), `delete_configset(name)`, `create_collection()`, `delete_collection()`, `get_cluster_status()`, `get_node_metrics()`.
3. **Create `osbenchmark/solr/result_writer.py`**: `ResultWriter` ABC + `LocalFilesystemResultWriter` + `WRITER_REGISTRY` dict + `create_writer()` factory. Wire into `publisher.py`.
4. **Create `osbenchmark/solr/runner.py`**: Implement `bulk_index` (using pysolr), `search` (two modes: classic params via pysolr `search()` → `/select`, or JSON Query DSL via plain POST → `/query` when `body` param is present), `commit` (pysolr), `optimize` (pysolr), `create_collection` (SolrAdminClient — two steps: upload configset ZIP then call collections API), `delete_collection` (SolrAdminClient — also deletes the associated configset), `raw_request`.
5. **Adapt `metrics.py`**: Strip OpenSearch metrics store backend. Retain in-memory metric accumulation and aggregation.
6. **Adapt `config.py`**: Remove OpenSearch keys, add `results_writer`, `results_path`, `solr.port` (default 8983).
7. **Rename CLI**: `benchmark` → `solr-benchmark`, `benchmarkd` → `solr-benchmarkd`. Update `setup.py` entry points.

### Phase B — Telemetry

**Goal**: Collect Solr-specific metrics during benchmark runs.

1. **Create `osbenchmark/solr/telemetry.py`**: Port `NodeStats` and `JvmStatsSampler` devices. Implement `SolrJvmStats` (JVM heap, GC), `SolrNodeStats` (CPU, memory, query handler rates), `SolrCollectionStats` (doc count, index size, segments). Support both Solr 9.x JSON format and Solr 10.x Prometheus format (detected by `Content-Type` of metrics response).
2. **Delete OpenSearch-only telemetry devices**: CCR, Transform, Searchable Snapshots, ML Commons, Segment Replication, gRPC stats.
3. **Wire telemetry**: Register new devices in the telemetry device registry.

### Phase C — Provisioning

**Goal**: `from-distribution` pipeline can download, start, and stop Solr.

1. **Create `osbenchmark/solr/provisioner.py`**: Download Solr tarball from Apache mirrors, extract, invoke `bin/solr start` with correct mode flags (`--cloud` for Solr 9.x cloud mode, `--user-managed` for Solr 10.x standalone mode, or defaults per version). Health-poll until ready. `stop()` calls `bin/solr stop`.
2. **Adapt `builder/`**: Register Solr provisioner as a `from-distribution` pipeline target. Remove OpenSearch-specific builder logic.
3. **Docker pipeline**: Add `SolrDockerLauncher` using the official `solr:9` image with the same mode flags.

### Phase D — Workload Layer

**Goal**: Solr-native workload format, NDJSON translation, migration utility.

1. **Adapt `workload/workload.py`**: Rename `index` → `collection`, `mapping` → `configset` in all workload entity classes. Remove OpenSearch-specific operation types.
2. **Adapt `workload/params.py`**: `BulkIndexParamSource` processes NDJSON line pairs at iteration time — extracts `_id` from the action line and injects it as `"id"` into the document body; `_index` is available for routing/logging but not stored as a document field; `_type` is dropped. Batches translated documents into configurable-size arrays for `pysolr.add()`. Add `SolrSearchParamSource` (Solr query params).
3. **Create `osbenchmark/tools/migrate_workload.py`**: Parse OSB workload JSON/YAML, translate common operations to Solr equivalents, emit annotated draft with `# TODO` comments for unsupported ops. CLI usage: `python -m osbenchmark.tools.migrate_workload input.json output.json`.

### Phase E — ASF Licensing

**Goal**: Comply with ASF policy before any PMC contribution.

1. **Update `NOTICE`**: "Apache Solr Benchmark / Copyright [YEAR] The Apache Solr project" at top; retain the full existing attribution chain (OpenSearch Contributors, Elasticsearch/Rally) — none may be removed.
2. **Update `LICENSE`**: Reflect Apache Solr PMC identity.
3. **Audit per-file headers**: Apply Category A/B/C rules from `research.md`. Automate scan with a script.
4. **Produce legal review checklist** (FR-031): Document each ASF licensing requirement and how it is addressed.

### Phase F — Cleanup and Tests

1. Remove all remaining OpenSearch branding from user-facing output, docs, and workload examples.
2. Ensure all generic framework unit tests pass without modification (SC-006).
3. Write unit tests for all new Solr modules (`tests/unit/solr/`).
4. Write integration test for full cycle: create-collection → bulk-index → search → delete-collection (SC-007).
5. Update `README.md`, `DEVELOPER_GUIDE.md`, and `CONTRIBUTING.md` for Solr context.

## Post-Implementation Review: The Dual-Mode Mistake

### What Was Implemented (Incorrectly)

After completing all 39 tasks in the original plan, a fundamental architectural misunderstanding was discovered:

**The implementation created a dual-mode tool** with:
- `mode` parameter throughout configuration and client initialization
- Shim classes (`SolrClientShim`) to bridge between OpenSearch-style interfaces and Solr operations
- Conditional logic (`if mode == "solr"`) in provisioners, builders, and runners
- Both OpenSearch and Solr code paths existing side-by-side
- OpenSearch client connections still available alongside Solr connections
- Builder classes with names like `solr-from-distribution` (instead of just `from-distribution`)

**Why this happened**: The specification language was ambiguous in places:
- "The tool will no longer support or benchmark OpenSearch clusters" could be read as "disable OpenSearch mode" rather than "remove OpenSearch code"
- The 75% code retention goal was misinterpreted as "keep all OpenSearch code and add Solr alongside it"
- The migration utility's existence suggested OSB compatibility at runtime, not just at conversion time

### What Should Have Been Implemented

**A pure Solr tool** with:
- Single code path: Solr-native client, runners, provisioners, telemetry
- No mode parameter anywhere
- OpenSearch code completely removed except for workload import/conversion utilities
- Direct replacement: `client.py` becomes Solr client, not a shim
- Pipelines named generically (`from-distribution`, not `solr-from-distribution`)
- Only OpenSearch compatibility: workload file parsing and corpus format translation

### Impact Assessment

**What works correctly**:
- All Solr operations execute successfully (indexing, search, commit, optimize, collection management)
- Telemetry collects Solr metrics correctly
- Result output works (filesystem writer)
- Workload migration utility converts OSB workloads correctly
- End-to-end benchmarks complete successfully

**What needs correction**:
- Remove dual-mode architecture (mode parameter, conditional logic, shims)
- Replace shim classes with direct Solr implementations
- Rename pipelines to remove `solr-` prefix
- Remove OpenSearch client connections entirely
- Simplify configuration (no mode selection)
- Remove unused OpenSearch builder/provisioner code paths
- Replace `OsClient` terminology with `Client` or `SolrClient` throughout

**Why the completed work is still valuable**:
- The Solr-specific implementations (runners, telemetry, provisioner) are correct
- The workload migration logic works correctly
- The schema auto-generation works correctly
- All bug fixes (NDJSON translation, date formats, geo-points, file I/O) are solid
- Test coverage is comprehensive

The correction phase (Phase 8 below) will remove the dual-mode architecture without discarding the working Solr implementations.

---

## Phase 8: Architectural Corrections (Post-Implementation)

**Goal**: Transform the dual-mode implementation into a pure Solr tool by removing mode parameters, shim classes, and OpenSearch code paths while preserving all working Solr functionality.

**Approach**: Systematic removal rather than rewrite — the Solr code works correctly, we just need to remove the OpenSearch scaffolding around it.

This phase is documented in detail in the updated `tasks.md` file (tasks T040-T050+).

---

## Complexity Tracking

No constitution violations. All complexity is inherent to the fork scope.
