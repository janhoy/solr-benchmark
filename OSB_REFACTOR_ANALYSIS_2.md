# OSB to Apache Solr Benchmark: Refactor Analysis

**Base commit (upstream OSB):** `92982c56fa212ab6287225fb5a9bff7b96f7041b`
**Branch analysed:** `purer-refactor` (HEAD `7059af89`)
**Analysis date:** 2026-04-19

---

## 1. Executive Summary

The Apache Solr Benchmark (ASB) fork has made substantial, purposeful changes to
OpenSearch Benchmark (OSB). The fork correctly replaces the core client stack
(opensearch-py → pysolr + requests), introduces a new `osbenchmark/solr/`
sub-package with Solr-native implementations for runners, telemetry, provisioning,
and workload conversion, and removes the OpenSearch-specific infrastructure
(plugin system, proto helpers, Kafka streaming, Terraform provisioning, etc.).

The refactor is largely coherent, but several issues remain:
- Multiple dead OSB telemetry classes (OpenSearch-specific `IndexStats`,
  `JvmStatsSummary`, `ExternalEnvironmentInfo`, `MlBucketProcessingTime`) are still
  present in `osbenchmark/telemetry.py` without being wired up or marked for removal.
- The `workload_generator` still calls `client.info()` and logs "Connected to
  OpenSearch cluster", which will produce a runtime `AttributeError` against Solr.
- `wait_for_cluster_ready` is proxied from `SolrClient` but not implemented in
  `SolrAdminClient`, causing an `AttributeError` at runtime if that path is reached.
- Eleven modified files in `osbenchmark/builder/` lack the required ASF modification
  notice in their license headers.
- Two inline comments in `runner.py` still say "only pass the default ES client"
  and "pass all ES clients".
- `ArchitectureTypes` in the builder still exposes an `opensearch_name` attribute.

Overall, the refactor is on the right track. The strategy — retain the OSB
orchestration/actor framework and workload system intact, and replace only the
client/runner/telemetry/provisioner layers — is appropriate for a macrobenchmark
fork. The new `osbenchmark/solr/` package follows good separation-of-concerns
principles.

---

## 2. Architecture Overview (for new Solr developers)

### What ASB does

ASB is a **macrobenchmarking framework** for Apache Solr. It measures end-to-end
throughput and latency for Solr workloads (bulk indexing, searches, commits,
optimizations). It can provision a local Solr cluster (bare metal, Docker, or
from a downloaded tarball), run a test procedure from a workload definition, collect
telemetry, and write results to local JSON/CSV files.

### How it works

**Pipeline stages** (controlled by `test_run_orchestrator.py`):

1. **Prepare** — Load workload definition from a local path or git repository;
   configure the metrics store.
2. **Build** (optional) — Download a Solr distribution tarball or Docker image
   via `osbenchmark/solr/provisioner.py`, install and start it.
3. **Run** — A Thespian actor (`WorkerCoordinatorActor`) spawns multiple
   `Worker` actors, each running an `AsyncExecutor` that calls the registered
   runner for each operation type. All runners are async Python coroutines that
   delegate actual HTTP to `SolrClient` (via pysolr / requests).
4. **Publish** — Write metrics to `~/.solr-benchmark/` as JSON/CSV; print
   summary report.

**Workload system** — Workloads are JSON/YAML files specifying:
- `collections` — Solr collections with configset paths
- `corpora` — data files (NDJSON, gzip, etc.)
- `operations` — typed operations (bulk-index, search, commit, ...)
- `test_procedures` — sequences of tasks with scheduling targets

**Actor model** — Thespian actors communicate via message passing. The
`WorkerCoordinatorActor` owns all `Worker` actors and a `FeedbackActor`. Workers
run the asyncio event loop for their task allocations. This design enables both
single-node and multi-node distributed load generation.

### Key modules

| Path | Role |
|---|---|
| `osbenchmark/benchmark.py` | CLI entry point; subcommands: run, list, info, create-workload, convert-workload, compare |
| `osbenchmark/test_run_orchestrator.py` | Pipeline definitions; cluster bring-up/tear-down |
| `osbenchmark/worker_coordinator/worker_coordinator.py` | Actor-model orchestration of workers and tasks |
| `osbenchmark/worker_coordinator/runner.py` | Base `Runner` class; registers all operation runners; delegates to Solr runners |
| `osbenchmark/solr/runner.py` | **Solr-native runners** (SolrBulkIndex, SolrSearch, SolrCommit, etc.) |
| `osbenchmark/solr/client.py` | `SolrAdminClient` — thin requests wrapper for V2 API admin ops |
| `osbenchmark/client.py` | `SolrClient` — unified client (wraps SolrAdminClient + pysolr) |
| `osbenchmark/solr/telemetry.py` | **Solr-native telemetry devices** (JVM, node stats, collection stats, cache stats) |
| `osbenchmark/solr/provisioner.py` | Download, install, start/stop local Solr; `SolrDockerLauncher` |
| `osbenchmark/solr/conversion/` | Detect and convert OpenSearch workloads to Solr format |
| `osbenchmark/workload/` | Workload loading, parameter sources, schemas |
| `osbenchmark/metrics.py` | Metrics collection; local filesystem JSON/CSV store |
| `osbenchmark/telemetry.py` | Base `TelemetryDevice` class; optional REST/JVM devices; dead OSB-specific classes |

---

## 3. Fork Strategy Assessment

### What the correct strategy is

For a long-lived fork of an open-source benchmark tool:

- **Minimal surface area**: Only modify files that must change for Solr. Leave OSB
  orchestration, actor model, workload system, metrics store, and CLI framework
  largely intact.
- **Additive placement**: Add Solr-specific code in clearly-named sub-packages
  (`osbenchmark/solr/`) rather than overwriting OSB's files.
- **Extension points**: Use OSB's existing registration hooks (e.g.,
  `register_runner()`, `TelemetryDevice` base class) rather than forking
  core abstractions.
- **License hygiene**: ASF modification notice on every modified file; full ASF
  header on every new file.
- **No dead code**: Remove or stub out code that no longer works rather than
  leaving it silently broken.

### How well this fork follows that strategy

The fork **follows this strategy well** at a structural level:
- A dedicated `osbenchmark/solr/` package holds all Solr-specific code.
- The actor model, scheduler, workload loader, and metrics store are untouched
  at an architectural level.
- `register_solr_runners()` is called from `register_default_runners()`, using the
  intended extension hook.
- Solr telemetry devices extend `TelemetryDevice`, the intended base class.

Where it **falls short**:
- Several dead OSB-specific classes remain in `osbenchmark/telemetry.py` (see §5.3).
- Two runtime bugs exist in untested code paths (`client.info()`, `wait_for_cluster_ready`).
- License headers are incomplete on 11 modified files.
- A handful of code comments still reference ES/OSB concepts.

---

## 4. File-Level Changes

### 4.1 Files Removed (99 total)

**Rightfully removed (no Solr equivalent):**
- `osbenchmark/async_connection.py` — OpenSearch async transport
- `osbenchmark/kafka_client.py` — Kafka data streaming (OSB-specific)
- `osbenchmark/data_streaming/data_producer.py` — Kafka producer
- `osbenchmark/builder/downloaders/core_plugin_source_downloader.py`
- `osbenchmark/builder/downloaders/external_plugin_source_downloader.py`
- `osbenchmark/builder/downloaders/plugin_distribution_downloader.py`
- `osbenchmark/builder/installers/preparers/plugin_preparer.py`
- `osbenchmark/worker_coordinator/proto_helpers/` — gRPC proto bulk/query helpers
- `osbenchmark/resources/cluster_configs/*/plugins/` — plugin configuration templates
- `osbenchmark/resources/cluster_configs/*/vanilla/templates/config/opensearch.yml`
- `osbenchmark/resources/cluster_configs/*/unpooled/` — OpenSearch-specific configs
- `samples/ccr/` — Cross-cluster replication samples
- `scripts/terraform/` — Terraform provisioning for OpenSearch
- Various GitHub workflow files (CODEOWNERS, backport, integ-test, publish-release)
- Community files (AUTHORS, MAINTAINERS.md, MAINTAINERS_GUIDE.md, RELEASE_GUIDE.md,
  TRIAGE.md, .whitesource)

**Tests removed alongside deleted source:**
- `tests/data_streaming/`, `tests/kafka_client_test.py`, `tests/test_async_connection.py`
- `tests/worker_coordinator/proto_bulk_helper_test.py`, `proto_query_helper_test.py`
- `tests/workload_generator/corpus_test.py`, `index_test.py`
- `tests/telemetry_test.py` (replaced by new `tests/unit/test_telemetry.py`)

### 4.2 Files Added (92 total)

**Core Solr implementation:**
- `osbenchmark/solr/__init__.py`
- `osbenchmark/solr/client.py` — `SolrAdminClient` (Solr V1/V2 API admin operations)
- `osbenchmark/solr/runner.py` — Solr runners: `SolrBulkIndex`, `SolrSearch`,
  `SolrCommit`, `SolrOptimize`, `SolrWaitForMerges`, `SolrCreateCollection`,
  `SolrDeleteCollection`, `SolrRawRequest`
- `osbenchmark/solr/telemetry.py` — Six Solr telemetry devices; supports both
  Solr 9.x JSON and Solr 10.x Prometheus text format from `/admin/metrics`
- `osbenchmark/solr/provisioner.py` — `SolrProvisioner` + `SolrDockerLauncher`
- `osbenchmark/solr/result_writer.py` — Abstract `ResultWriter` + CSV/JSON implementations
- `osbenchmark/solr/schema_generator.py` — Translate OpenSearch mappings to Solr schema.xml
- `osbenchmark/solr/conversion/detector.py` — Detect OpenSearch vs Solr workload format
- `osbenchmark/solr/conversion/field.py` — Field name normalisation
- `osbenchmark/solr/conversion/query.py` — Translate OpenSearch Query DSL to Solr `q=`
- `osbenchmark/solr/conversion/schema.py` — Generate Solr schema.xml from OS mappings
- `osbenchmark/solr/conversion/workload_converter.py` — Full workload file converter
- `osbenchmark/tools/migrate_workload.py` — CLI tool for OSB→ASB workload migration
- `osbenchmark/min-version.txt` — Replaces `min-os-version.txt`
- `solrbenchmark/__init__.py`, `solrbenchmark/main.py` — Thin re-export wrapper

**Documentation:**
- Complete Jekyll-based docs site in `docs/` with 40+ pages covering quickstart,
  concepts, reference, user guides
- `TODO.md`, `TELEMETRY-GAP-ANALYSIS.md`, `CLAUDE.md`
- `it/README.md`

**Tests for new Solr code:**
- `tests/unit/solr/` — 12 test files covering client, runner, telemetry, provisioner,
  schema generator, workload converter, result writer, migrate workload, etc.
- `tests/unit/test_telemetry.py` — Replacement telemetry tests (OSB-independent)

### 4.3 Files Renamed (10 total)

All are straightforward rename+content updates:

| Old path | New path | Similarity |
|---|---|---|
| `downloaders/opensearch_distribution_downloader.py` | `downloaders/distribution_downloader.py` | 58% |
| `downloaders/repositories/opensearch_distribution_repository_provider.py` | `repositories/distribution_repository_provider.py` | 51% |
| `downloaders/opensearch_source_downloader.py` | `downloaders/source_downloader.py` | 57% |
| `installers/preparers/opensearch_preparer.py` | `installers/preparers/solr_preparer.py` | 77% |
| `data_streaming/__init__.py` | `tools/__init__.py` | 100% (pure rename) |
| `docs/user-guides/index.md` | `tests/unit/__init__.py` | 100% (misuse: a docs file renamed to a test init — clearly mechanical, not intentional) |

The last entry (`docs/user-guides/index.md` → `tests/unit/__init__.py`) is a Git
rename artefact from the `R100` similarity marker. The `tests/unit/__init__.py`
is a proper empty Python init file; the docs file was deleted. No functional issue.

### 4.4 Files Modified (substantive changes)

**`osbenchmark/benchmark.py`** — Added `convert-workload` subcommand; renamed
`supported_os_version()` → uses `minimum_solr_version()`; updated all help strings
to reference Solr. Line 77: function name `supported_os_version` is a mild naming
inconsistency (still has "os" in name after rename at line 80).

**`osbenchmark/client.py`** — Completely replaced: was OpenSearch client wrappers,
now houses `SolrClient` (unified Solr client) and `ClientFactory`.

**`osbenchmark/worker_coordinator/runner.py`** — Stripped down from ~7000 to ~811
lines. Removed all OSB-specific runners (bulk indexing, cluster management, ML, etc.).
Retained: `Runner`, `Sleep`, `RawRequest`, `Composite`, `Retry`, backup stubs.
Added `register_solr_runners()` call. Two stale comments at lines 202–207 still
say "only pass the default ES client" / "pass all ES clients".

**`osbenchmark/worker_coordinator/worker_coordinator.py`** — Key change: `create_clients()`
now returns `SolrClient` instances. Solr telemetry devices are wired in via
`_create_solr_telemetry_devices()`. `FeedbackActor._check_cpu_usage()` correctly
raises `SystemSetupError` with a Solr-specific message.

**`osbenchmark/telemetry.py`** — `list_telemetry()` now delegates to Solr-native
devices. `Telemetry`, `TelemetryDevice`, base infrastructure, `FlightRecorder`,
`Gc`, `JitCompiler`, `Heapdump`, `SegmentStats`, `ShardStats`, `DiskIo`,
`StartupTime` are kept (valid for Solr). Dead OSB-specific classes
`ExternalEnvironmentInfo`, `JvmStatsSummary`, `IndexStats`, `MlBucketProcessingTime`
remain (see §5.3).

**`osbenchmark/test_run_orchestrator.py`** — Imports and uses `SolrProvisioner`,
`SolrDockerLauncher`; calls `is_opensearch_workload_path()` to auto-detect and warn
about workloads needing conversion.

**`osbenchmark/workload_generator/workload_generator.py`** — Unchanged except
for minimal formatting. Still uses `client.info()` (OpenSearch API) and logs
"Connected to OpenSearch cluster" — a live runtime bug (line 42).

**`osbenchmark/metrics.py`** — `CompositeTestRunStore` marked as placeholder
(not wired). Minor OSB reference in docstring (lines 47, 51).

**`osbenchmark/builder/utils/artifact_variables_provider.py`** — Parameter name
`opensearch_version` and attribute `.opensearch_name` remain (see §5.1).

---

## 5. Issues Found

### 5.1 Remaining OpenSearch Trademarks / References

Non-trivial (not in purely contextual/documentary text):

| File | Line | Issue |
|---|---|---|
| `osbenchmark/workload_generator/workload_generator.py` | 42 | `console.info(f"Connected to OpenSearch cluster ...")` — will display wrong brand and uses `info['name']`/`info['version']['number']` which `SolrClient` does not provide (runtime bug, see §5.5) |
| `osbenchmark/builder/utils/artifact_variables_provider.py` | 8–21 | Parameter named `opensearch_version`; `.opensearch_name` attribute on `ArchitectureTypes`; variable `"VERSION": opensearch_version` in returned dict |
| `osbenchmark/builder/models/architecture_types.py` | 9–14 | Docstring and attribute `opensearch_name` reference OpenSearch naming |
| `osbenchmark/worker_coordinator/runner.py` | 202, 207 | Comments "only pass the default ES client" / "pass all ES clients" |
| `osbenchmark/telemetry.py` | 765 | Class docstring: "Gathers statistics via the OpenSearch index stats API" |
| `osbenchmark/telemetry.py` | 522 | "CPU-based redline feedback requires an external OpenSearch metrics store" — acceptable (explains the restriction, uses the term accurately) |
| `osbenchmark/utils/modules.py` | 38 | "install hooks for OpenSearch plugins" in docstring |
| `osbenchmark/worker_coordinator/worker_coordinator.py` | 65, 83, 138 | Docstring comments `:param config: OSB internal configuration object.` |
| `benchmark` (entry script) | 27 | Comment "this script will stay in the OSB git root directory" |
| `benchmarkd` (entry script) | 27 | Same comment as above |
| `osbenchmark/paths.py` | 61 | Docstring: "OSB's log file" |
| `osbenchmark/synthetic_data_generator/strategies/mapping_strategy.py` | 282–383 | Multiple references to OpenSearch mappings and `cosinesimil space_type in OpenSearch` — acceptable in context (the SDG is OpenSearch-mapping-based) |

### 5.2 License Header Issues

**Modified files missing the ASF modification notice** (should have
"Modifications Copyright OpenSearch Contributors" or equivalent ASF change notice
in addition to the original Elasticsearch/OSB header):

- `osbenchmark/builder/downloaders/downloader.py`
- `osbenchmark/builder/installers/bare_installer.py`
- `osbenchmark/builder/installers/docker_installer.py`
- `osbenchmark/builder/installers/installer.py`
- `osbenchmark/builder/launchers/launcher.py`
- `osbenchmark/builder/launchers/local_process_launcher.py`
- `osbenchmark/builder/utils/binary_keys.py`
- `osbenchmark/builder/utils/config_applier.py`
- `osbenchmark/builder/utils/java_home_resolver.py`
- `osbenchmark/visualizations/benchmark_report_renderer.py`
- `osbenchmark/worker_coordinator/errors.py`

All of the above start with the bare `from abc import ABC, abstractmethod` or
similar import lines — they have no SPDX header at all. Since they are modified
(not new) files from the OSB upstream, they need at minimum the original OSB/ES
license header preserved.

**New files with correct ASF headers** (compliant): All files in
`osbenchmark/solr/`, `osbenchmark/tools/`, `solrbenchmark/` have full ASF
Apache-2.0 headers.

### 5.3 Dead Code

**Dead OSB-specific telemetry classes** in `osbenchmark/telemetry.py` — these
classes use OpenSearch client APIs (`self.client.nodes.stats()`,
`self.client.indices.stats()`, `self.client.search()`) that do not exist on
`SolrClient`. They are not instantiated anywhere in the current codebase:

| Class | Lines | Issue |
|---|---|---|
| `ExternalEnvironmentInfo` | 630–670 | Calls `self.client.nodes.stats()` and `self.client.nodes.info()` — OpenSearch-only APIs |
| `JvmStatsSummary` | 673–760 | Calls `self.client.nodes.stats(metric="_all")` — OpenSearch-only API |
| `IndexStats` | 763–888 | Calls `self.client.indices.stats()` — OpenSearch-only API; docstring still says "OpenSearch index stats API" |
| `MlBucketProcessingTime` | 891–949 | Calls `self.client.search(index=".ml-anomalies-*", ...)` — OpenSearch ML plugin API |

These four classes occupy ~300 lines and are completely inert. They should either
be deleted or have a clear `# NOT USED — pending Solr port` comment at the class
level (the `IndexStats` docstring at line 765 reads "Gathers statistics via the
OpenSearch index stats API" which is actively misleading).

**Commented-out debug logging** in `osbenchmark/telemetry.py` lines 789–790:
```python
# import json
# self.logger.debug("Returned indices stats:\n%s", json.dumps(index_stats, indent=2))
```
These are inside the dead `IndexStats.on_benchmark_stop()` method and should be
removed together with the class.

**`CompositeTestRunStore`** in `osbenchmark/metrics.py` lines 1053–1070 — correctly
marked as "not wired into any active code path" at line 1050, but the note could
be elevated to a class-level `# NOT USED` comment so tools like pylint can verify
it is intentionally unreferenced.

### 5.4 TODOs

Outstanding TODOs in source code (not in documentation):

| File | Lines | TODO |
|---|---|---|
| `osbenchmark/worker_coordinator/runner.py` | 48, 480–549 | 5 backup runner stubs: DeleteBackupRepository, CreateBackupRepository, CreateBackup, WaitForBackupCreate, RestoreBackup — all raise `BenchmarkError`. Need port to Solr Backup V2 API. |
| `osbenchmark/worker_coordinator/runner.py` | 735–736 | `Retry` class: "Allow to use this from (selected) regular runners" and "add meta-data on how many retries there were" — inherited from OSB |
| `osbenchmark/worker_coordinator/worker_coordinator.py` | 1690 | "This could be misleading given that one worker could execute more than one task" |
| `osbenchmark/worker_coordinator/worker_coordinator.py` | 2809 | "Can we offload the parameter source execution to a different thread?" |
| `osbenchmark/workload/workload.py` | 378, 386, 398 | `# TODO #341: Improve API` (inherited OSB issue numbers) |
| `osbenchmark/workload/loader.py` | 944, 1122 | OSB issue #341 references |
| `osbenchmark/builder/builder.py` | 166, 370 | Minor orchestration TODOs |
| `TODO.md` | — | 20+ tracked items including: missing Solr metrics store, no multi-node integration tests, StartupTime/DiskIo devices not ported |

### 5.5 Architectural Deviations / Runtime Bugs

**Bug 1 — `client.info()` does not exist on `SolrClient`**

`osbenchmark/workload_generator/workload_generator.py` line 41–42:
```python
info = client.info()
console.info(f"Connected to OpenSearch cluster [{info['name']}] ...")
```
`SolrClient` has no `info()` method. This will raise `AttributeError` whenever
`create-workload` is invoked. The `create-workload` command extracts an existing
index from an OpenSearch/Elasticsearch cluster and generates a workload from it —
the entire command is OpenSearch-specific and currently broken against Solr.

**Bug 2 — `wait_for_cluster_ready()` not implemented in `SolrAdminClient`**

`osbenchmark/client.py` line 99–100 proxies `wait_for_cluster_ready(**kwargs)` to
`self._admin.wait_for_cluster_ready(**kwargs)`, but `SolrAdminClient`
(`osbenchmark/solr/client.py`) has no such method. Any code path that calls
`client.wait_for_cluster_ready()` will raise `AttributeError`.

**Bug 3 — `RawRequest` base runner uses OpenSearch transport API**

`osbenchmark/worker_coordinator/runner.py` line 451:
```python
await client.transport.perform_request(method=..., url=..., body=...)
```
The base `RawRequest` runner calls `client.transport.perform_request()`, which is
the OpenSearch transport API. This is correctly overridden by `SolrRawRequest` in
`register_default_runners()` (Solr's runner is registered last and wins), but the
base `RawRequest` class is misleadingly retained. If a user calls `register_runner`
to replace `SolrRawRequest` with the base `RawRequest`, the benchmark will fail.
The `RawRequest` base class should be removed or replaced with a Solr-aware default.

**`create-workload` command is entirely broken**

The `create-workload` subcommand calls `create_workload()` in
`osbenchmark/workload_generator/workload_generator.py`, which:
- Calls `ClientFactory(...).create()` (returns a `SolrClient`) then `client.info()`
  (does not exist) at line 41
- Passes the `SolrClient` to `IndexExtractor` and `SequentialCorpusExtractor`
  which are designed for OpenSearch REST APIs

The workload generator is fundamentally OpenSearch-specific (extracts mappings from
indices, extracts corpora via scroll). It needs either removal, a clear "not
supported for Solr" error at entry, or a full Solr rewrite.

**`SegmentStats` device called with `SolrClient`**

`osbenchmark/worker_coordinator/worker_coordinator.py` line 937:
```python
telemetry.SegmentStats(log_root, sc),
```
`SegmentStats` (in `osbenchmark/telemetry.py` line 305) calls
`self.admin_client.indices.segments()` at line 334 — an OpenSearch API call. It
appears this class was adapted in the recent `F6` commit but may still call an
OpenSearch-specific path. Verify against `SolrClient`'s interface.

### 5.6 Missed Opportunities

**Conversion of OpenSearch DSL in `SolrSearch` (Mode 3)** is documented in the
class docstring (runner.py line 477–480) but not implemented in the actual
`__call__` method. The implementation at line 495–514 only handles Mode 1 (classic
Solr params) and Mode 2 (Solr JSON DSL). Mode 3 (translate OpenSearch body dict)
falls through to Mode 2 silently. The docstring should either be removed or the
feature implemented.

**`create-workload` → should be disabled for Solr** with a clear error message
rather than failing at runtime with `AttributeError`.

**`ArtifactVariablesProvider.opensearch_name`** — the renaming work in other files
did not reach this helper. The parameter should be renamed to `version` and the
attribute to `arch_name` to remove the last semantic OpenSearch reference in the
builder layer.

---

## 6. Summary and Recommendations

### Summary

The fork is structurally sound. The new `osbenchmark/solr/` package is well-organised
and follows OSB's extension patterns. The actor model, workload system, scheduler,
and metrics infrastructure have been left intact (the right call). The Solr client
stack (pysolr + requests replacing opensearch-py) is properly isolated. The six
Solr telemetry devices cover JVM, OS, collection, query, indexing, and cache metrics
with dual-format support (Solr 9 JSON / Solr 10 Prometheus).

The main risks are:
1. Two runtime bugs that will crash specific workflows (`create-workload`, and any
   code path that calls `client.wait_for_cluster_ready()`).
2. Dead OSB telemetry classes (~300 lines) in `telemetry.py` that use OpenSearch APIs
   and will crash if ever instantiated.
3. Missing license headers on 11 modified `builder/` files.

### Recommendations (priority order)

1. **Fix Bug 1 and Bug 2 immediately.** Either implement `wait_for_cluster_ready()`
   in `SolrAdminClient` (as a health-check poll on `/api/cluster`) or remove the proxy.
   Add a "not yet supported for Solr" error to the `create-workload` command entry
   point in `benchmark.py` before it calls `create_workload()`.

2. **Remove or clearly flag the four dead OSB telemetry classes** from
   `osbenchmark/telemetry.py`: `ExternalEnvironmentInfo`, `JvmStatsSummary`,
   `IndexStats`, `MlBucketProcessingTime`. If they cannot be deleted yet, add a
   module-level `# NOT WIRED — OpenSearch-only, pending Solr port` comment above
   each class.

3. **Add missing license headers** to the 11 modified files in
   `osbenchmark/builder/` that currently have no SPDX header at all.

4. **Rename `opensearch_name` / `opensearch_version`** in
   `osbenchmark/builder/models/architecture_types.py` and
   `osbenchmark/builder/utils/artifact_variables_provider.py`.

5. **Fix the stale `Mode 3` docstring** in `SolrSearch` — either implement
   OpenSearch DSL translation or remove the claim that it is supported.

6. **Fix the two stale "ES client" comments** in `runner.py` lines 202 and 207.

7. **Verify `SegmentStats`** against the `SolrClient` interface to confirm it
   does not call `self.admin_client.indices.segments()`.

8. **Prioritise the 5 backup runner stubs** (tracked in `TODO.md`) — the current
   approach (raise `BenchmarkError`) is acceptable, but workloads using snapshot
   operations will fail at runtime rather than being skipped gracefully.

9. Consider whether `create-workload` can be replaced by a Solr-specific variant that
   extracts index schema and a sample corpus from a running Solr instance.
