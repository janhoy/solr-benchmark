# OSB → Apache Solr Benchmark: Refactor Analysis

**Diff base:** `92982c56fa212ab6287225fb5a9bff7b96f7041b` (last OSB upstream commit)
**Diff head:** current HEAD
**Analysis date:** 2026-04-18

---

## 1. Structural Changes: Folders / Modules Removed, Renamed, or Added

### Removed modules (entire directories / packages)

| Path | Reason |
|---|---|
| `osbenchmark/kafka_client.py` | Kafka ingestion not in scope for Solr Benchmark |
| `osbenchmark/data_streaming/` (except `__init__.py`) | Kafka/streaming data producer removed |
| `osbenchmark/worker_coordinator/proto_helpers/` | gRPC proto helpers removed (Solr does not use gRPC) |
| `osbenchmark/resources/cluster_configs/*/plugins/` | Plugin provisioning removed (Solr uses modules, not plugins) |
| `osbenchmark/resources/cluster_configs/*/cluster_configs/v1/basic-license.ini` | OpenSearch-only licensing concept |
| `osbenchmark/resources/cluster_configs/*/cluster_configs/v1/trial-license.ini` | OpenSearch-only licensing concept |
| `osbenchmark/resources/cluster_configs/*/cluster_configs/v1/unpooled/` | OpenSearch-specific cluster config |
| `osbenchmark/resources/cluster_configs/*/cluster_configs/v1/vanilla/templates/config/opensearch.yml` | Replaced by Solr config files |
| `osbenchmark/builder/installers/preparers/plugin_preparer.py` | Plugin installation removed |
| `osbenchmark/builder/downloaders/external_plugin_source_downloader.py` | Plugin support removed |
| `osbenchmark/builder/downloaders/plugin_distribution_downloader.py` | Plugin support removed |
| `scripts/terraform/` | OpenSearch-specific cloud terraform scripts removed |
| `samples/ccr/` | Cross-Cluster Replication samples removed (OS-only feature) |
| `.github/workflows/backport.yml` | OS-specific backport automation |
| `.github/workflows/add-untriaged.yml` | OS-specific triage automation |
| `.github/workflows/docker-push-release.yml` | OS-specific Docker publish workflow |
| `.github/workflows/publish-release.yml` | OS-specific release publish workflow |
| `.github/workflows/integ-test.yml` | Replaced by tox-based integration tests |
| `.whitesource` | WhiteSource security scanning (replaced by FOSSA) |

### Added modules (new directories / packages)

| Path | Purpose |
|---|---|
| `osbenchmark/solr/` | New Solr-specific implementation package |
| `osbenchmark/solr/client.py` | `SolrAdminClient` — HTTP client for Solr Collections API, metrics, configsets |
| `osbenchmark/solr/runner.py` | Solr operation runners (BulkIndex, Search, CreateCollection, etc.) |
| `osbenchmark/solr/telemetry.py` | Solr-native telemetry devices (JVM, node, collection, query, indexing, cache stats) |
| `osbenchmark/solr/provisioner.py` | Solr provisioner and Docker launcher for benchmarks |
| `osbenchmark/solr/result_writer.py` | JSON/CSV result writer for Solr benchmark results |
| `osbenchmark/solr/schema_generator.py` | Utility to generate Solr schema from field definitions |
| `osbenchmark/solr/conversion/` | Workload conversion sub-package |
| `osbenchmark/solr/conversion/detector.py` | Detects whether a workload is in OpenSearch Benchmark format |
| `osbenchmark/solr/conversion/field.py` | Field name normalization (ES dot-notation → Solr underscore convention) |
| `osbenchmark/solr/conversion/query.py` | Query translation (OpenSearch Query DSL → Solr syntax) |
| `osbenchmark/solr/conversion/schema.py` | Schema/mapping translation (ES mappings → Solr schema) |
| `osbenchmark/solr/conversion/workload_converter.py` | Orchestrates full OSB workload → Solr workload conversion |
| `osbenchmark/tools/` | New top-level tools package (replaces `data_streaming/__init__.py`) |
| `osbenchmark/tools/migrate_workload.py` | CLI tool for OSB → Solr workload migration |
| `solrbenchmark/` | Thin re-export wrapper package for entry points |
| `docs/` | Entirely new Jekyll documentation site (replaces old OSB API docs) |
| `.github/workflows/docs.yml` | GitHub Actions workflow to publish docs to GitHub Pages |

### Renamed modules (file renamed, content partially changed)

| Old path | New path | Similarity | Notes |
|---|---|---|---|
| `osbenchmark/builder/downloaders/opensearch_distribution_downloader.py` | `osbenchmark/builder/downloaders/distribution_downloader.py` | 71% | Download logic adapted from OpenSearch to Solr URLs |
| `osbenchmark/builder/downloaders/opensearch_source_downloader.py` | `osbenchmark/builder/downloaders/source_downloader.py` | 72% | Adapted for Solr source repository |
| `osbenchmark/builder/downloaders/repositories/opensearch_distribution_repository_provider.py` | `osbenchmark/builder/downloaders/repositories/distribution_repository_provider.py` | 68% | URL template adapted |
| `osbenchmark/builder/installers/preparers/opensearch_preparer.py` | `osbenchmark/builder/installers/preparers/solr_preparer.py` | 90% | Adapted for Solr directory structure, tarball extraction |
| `osbenchmark/data_streaming/__init__.py` | `osbenchmark/tools/__init__.py` | 100% | Empty `__init__.py` moved to new package |
| `tests/builder/downloaders/opensearch_distribution_downloader_test.py` | `tests/builder/downloaders/distribution_downloader_test.py` | 81% | Tests adapted |
| `tests/builder/downloaders/opensearch_source_downloader_test.py` | `tests/builder/downloaders/source_downloader_test.py` | 79% | Tests adapted |
| `tests/builder/downloaders/repositories/opensearch_distribution_repository_provider_test.py` | `tests/builder/downloaders/repositories/distribution_repository_provider_test.py` | 54% | Tests adapted |
| `tests/builder/installers/preparers/opensearch_preparer_test.py` | `tests/builder/installers/preparers/solr_preparer_test.py` | 79% | Tests adapted |
| `docs/user-guides/index.md` | `tests/unit/__init__.py` | 100% | Misuse of git rename tracking — unrelated files |

---

## 2. Files Renamed but Not Changed

| Old path | New path |
|---|---|
| `osbenchmark/data_streaming/__init__.py` | `osbenchmark/tools/__init__.py` |

---

## 3. Files Added, Removed, or Changed

### Added files

#### `osbenchmark/solr/client.py`
`SolrAdminClient` wraps `requests.Session` for Solr V2 Collection API operations. Provides version detection (`get_major_version()`), configset upload/delete (via V1 API, since V2 is not available in Solr 9.x), collection create/delete, cluster status, and metrics polling. Includes custom exceptions (`SolrClientError`, `CollectionAlreadyExistsError`, `CollectionNotFoundError`) and fork-safe lazy session initialization. This is the shared client reusable across all Solr-specific modules.

#### `osbenchmark/solr/runner.py`
Full suite of Solr operation runners registered with the framework via `register_solr_runners()`. Key operations: `BulkIndex` (translates NDJSON/OSB bulk format to pysolr documents), `Search` (with optional OpenSearch Query DSL translation), `ScrollSearch`, `Optimize`, `CreateCollection`, `DeleteCollection`, `CommitAndOptimize`, and several others. Error translation from pysolr/requests exceptions to framework `BenchmarkTransportError`. Supports both streaming and batch NDJSON modes.

#### `osbenchmark/solr/telemetry.py`
Six new Solr-specific telemetry devices: `SolrJvmStats`, `SolrNodeStats`, `SolrCollectionStats`, `SolrQueryStats`, `SolrIndexingStats`, `SolrCacheStats`. All poll `/solr/admin/metrics`. Detects Solr version and switches between JSON (Solr 9.x) and Prometheus text format (Solr 10.x).

#### `osbenchmark/solr/provisioner.py`
`SolrProvisioner` handles download, installation, configuration, start, stop, and cleanup of a local Solr instance (tarball-based). `SolrDockerLauncher` manages a Solr Docker container lifecycle. Both support SolrCloud mode (embedded ZooKeeper). Used by the new pipeline functions in `test_run_orchestrator.py`.

#### `osbenchmark/solr/result_writer.py`
Factory-pattern result writers (`JsonResultWriter`, `CsvResultWriter`) hooked into `publisher.py`. Writes structured benchmark results to filesystem with metadata (run ID, timestamp).

#### `osbenchmark/solr/schema_generator.py`
Minimal stub for generating Solr schema from field definitions. Not yet fully implemented.

#### `osbenchmark/solr/conversion/detector.py`
Detects whether a workload directory contains an OpenSearch Benchmark workload (by inspecting `workload.json` for `"indices"` or `"data-streams"` keys). Used in `test_run_orchestrator.py` to abort early with a clear message.

#### `osbenchmark/solr/conversion/field.py`
Normalizes OpenSearch field names (dot-notation multi-fields like `country.raw`) to Solr underscore convention (`country_raw`).

#### `osbenchmark/solr/conversion/query.py`
Translates OpenSearch Query DSL (match, term, range, bool, match_all, etc.) to Solr query syntax. Also converts ES aggregations to Solr JSON Facet API format.

#### `osbenchmark/solr/conversion/schema.py`
Maps OpenSearch/ES mapping types to Solr field types. Generates Solr schema additions from an ES mapping body.

#### `osbenchmark/solr/conversion/workload_converter.py`
Orchestrates full workload conversion: reads OSB `workload.json` and operation files, converts indices → collections, translates query bodies, emits Solr-native workload files.

#### `osbenchmark/tools/migrate_workload.py`
CLI tool (`solr-benchmark convert-workload`) that wraps the conversion package. Marks unsupported operations (snapshot, transforms, data streams, pipelines) with `_migration_todo` for manual handling.

#### `solrbenchmark/main.py`
Thin re-export wrapper. Re-exports `benchmark_main` and `benchmarkd_main` from the `osbenchmark` package for any tooling that imports from `solrbenchmark`.

---

### Removed files (with reason)

| File | Reason |
|---|---|
| `osbenchmark/kafka_client.py` | Kafka ingestion not in scope |
| `osbenchmark/data_streaming/data_producer.py` | Kafka producer removed with Kafka support |
| `osbenchmark/async_connection.py` | OpenSearch async HTTP transport removed |
| `osbenchmark/worker_coordinator/proto_helpers/ProtoBulkHelper.py` | gRPC bulk helper removed |
| `osbenchmark/worker_coordinator/proto_helpers/ProtoQueryHelper.py` | gRPC query helper removed |
| `osbenchmark/builder/installers/preparers/plugin_preparer.py` | Plugin installation removed |
| `osbenchmark/builder/downloaders/external_plugin_source_downloader.py` | Plugin support removed |
| `osbenchmark/builder/downloaders/plugin_distribution_downloader.py` | Plugin support removed |
| `osbenchmark/resources/cluster_configs/*/plugins/` | Entire plugin configs directory tree removed |
| `osbenchmark/resources/cluster_configs/*/cluster_configs/v1/vanilla/templates/config/opensearch.yml` | Replaced by Solr config |
| `tests/data_streaming/` | Tests for removed Kafka producer |
| `tests/kafka_client_test.py` | Tests for removed Kafka client |
| `tests/telemetry_test.py` | Legacy OS telemetry tests (replaced by `tests/unit/test_telemetry.py`) |
| `tests/test_async_connection.py` | Tests for removed async_connection module |
| `tests/worker_coordinator/proto_bulk_helper_test.py` | Tests for removed proto helpers |
| `tests/worker_coordinator/proto_query_helper_test.py` | Tests for removed proto helpers |
| `tests/workload_generator/corpus_test.py` | Removed (reason unclear) |
| `tests/workload_generator/index_test.py` | Removed as Index concept replaced by Collection |
| `tests/builder/downloaders/core_plugin_source_downloader_test.py` | Tests for removed plugin downloader |
| `tests/builder/downloaders/external_plugin_source_downloader_test.py` | Tests for removed plugin downloader |
| `tests/builder/installers/preparers/plugin_preparer_test.py` | Tests for removed plugin preparer |

---

### Modified files with logical changes

#### `osbenchmark/benchmark.py`
- Renamed CLI entry point from `osb` to `solr-benchmark`.
- Added `convert-workload` subcommand wiring to `migrate_workload.py`.
- Removed `--target-os` / `--target-arch` flags (no longer needed without multi-arch build support).
- Default port changed from 39200 to 38983.
- Added macOS fork-safety workaround (`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`) before Thespian actor system import.
- Plugin-related CLI flags removed.
- Help text updated to reference Solr instead of OpenSearch.

#### `osbenchmark/test_run_orchestrator.py`
- Pipeline functions completely rewritten for Solr:
  - `from_sources` → `solr_from_sources`: clones Solr git repo, builds with Gradle, extracts tarball, starts via `SolrProvisioner`.
  - `from_distribution` → `solr_from_distribution`: downloads Solr tarball, installs, starts via `SolrProvisioner`.
  - `docker` → `solr_docker`: starts Solr via `SolrDockerLauncher`, runs benchmark, tears down.
- Added `_check_workload_is_solr_native()`: detects OSB-format workloads and aborts with a clear migration message.
- Added `_load_cluster_config()`: loads JVM/GC cluster config from INI repository for tuning.
- Actor system restart logic added to handle timeouts after long Gradle builds.
- Console info messages now include pipeline name and handle unknown distribution versions.
- The `benchmark-only` pipeline retained as-is (connects to external Solr).

#### `osbenchmark/worker_coordinator/runner.py`
- Removed all OpenSearch-specific operation runners (~600 lines): BulkIndex, ForceMerge, IndexStats, NodeStats, Search, VectorSearch, PaginatedSearch, ScrollSearch, CreatePointInTime, DeletePointInTime, SubmitAsyncSearch, GetAsyncSearch, DeleteAsyncSearch, CreateSnapshot/Restore, all index template/component/composable template operations, data stream operations, transforms, ML operations.
- Retained framework-level runners only: `Sleep`, `RawRequest`, `Composite`, plus backup stubs.
- Added call to `solr_runner.register_solr_runners(register_runner)` to wire Solr operations.
- Backup runners (`CreateBackup`, `RestoreBackup`, `DeleteBackupRepository`, `CreateBackupRepository`, `WaitForBackupCreate`) are renamed and have TODOs but still contain OpenSearch `client.snapshot.*` API calls — they will fail if invoked.
- `Composite` runner's `supported_op_types` list still contains OpenSearch-specific operations (`create-point-in-time`, `delete-point-in-time`, `submit-async-search`, `get-async-search`, `delete-async-search`).

#### `osbenchmark/workload/workload.py`
- Removed classes: `Index`, `DataStream`, `IndexTemplate`, `IndexCodec`, `ComponentTemplate`, `ComposableTemplate`.
- Added `Collection` class with Solr-specific fields: `name`, `configset`, `configset_path`, `num_shards`, `replication_factor`, `pull_replicas`, `tlog_replicas`.
- `Workload` class: replaced `indices`, `data_streams`, `templates`, `composable_templates`, `component_templates` with `collections`.
- `OperationType` enum: stripped to framework-only types (Sleep, RawRequest, Composite) plus Solr-relevant backup types (CreateBackup, RestoreBackup, etc.).

#### `osbenchmark/workload/loader.py`
- Removed loading logic for `indices`, `data-streams`, `templates`, `composable-templates`, `component-templates`.
- Added `_create_collection()` to load Solr collection specs from workload JSON.
- `_create_corpora()` now accepts `collections` instead of `indices`/`data_streams`.
- Comment in range query builder updated from "OpenSearch range query" to generic "range query".

#### `osbenchmark/workload/params.py`
- Removed all OpenSearch-specific param sources: CreateIndexParamSource, DeleteIndexParamSource, CreateDataStreamParamSource, PutSettingsParamSource, all template param sources, all snapshot/restore param sources, all transform param sources, CreateSearchPipelineParamSource, all point-in-time param sources, etc.
- Added `DeleteCollectionParamSource` (reads collection from `workload.collections`).
- Param source registry now handles both enum-based and name-based lookups.

#### `osbenchmark/telemetry.py`
- `list_telemetry()` completely rewritten: now shows Solr-native always-on devices (from `osbenchmark.solr.telemetry`), optional REST devices (SegmentStats, ShardStats, ClusterEnvironmentInfo), and optional JVM/process devices (FlightRecorder, Gc, JitCompiler, Heapdump).
- JVM flags updated: `OPENSEARCH_JAVA_OPTS` → `SOLR_JAVA_OPTS`, `OPENSEARCH_JAVA_HOME` → `JAVA_HOME`.
- `Gc.java_opts()`: removed Java 8 and 9 support (only `–Xlog:` format now).
- `SegmentStats`: rewritten to use Solr Luke API (`/solr/{collection}/admin/luke`) instead of OpenSearch CAT segments API.
- `ShardStats`: rewritten to use Solr CLUSTERSTATUS API instead of OpenSearch `/_cat/shards`.
- Old OS-specific telemetry classes (`CcrStats`, `RecoveryStats`, `NodeStats`, `SearchableSnapshotsStats`, `SegmentReplicationStats`, `TransformStats`) are **retained in the file** but are not registered in any device list and are not instantiated by the worker coordinator.
- `Heapdump`: added `docker_container` parameter for Docker scenarios.
- `FlightRecorder`: removed commercial JDK warning.

#### `osbenchmark/client.py`
- Removed entirely: `OsClientFactory` (300+ lines), `GrpcClientFactory`, `MessageProducerFactory`, `wait_for_rest_layer()`.
- Added `SolrClient`: minimal stub inheriting `RequestContextHolder`; contains only a `_NoOpTransport` with async `close()`. No actual HTTP methods — runners use `pysolr.Solr` directly.
- `ClientFactory`: always returns a `SolrClient`.
- `UnifiedClient`: simplified to bare `__getattr__` delegation.

#### `osbenchmark/metrics.py`
- Removed `OsClient` and `OsClientFactory` (OpenSearch-backed metrics store client).
- Removed `IndexTemplateProvider` (OpenSearch metrics index templates).
- `CompositeTestRunStore` is retained in the file with a comment that it is not wired into any active code path.
- Core metrics recording (FileSystemMetricsStore, InMemoryMetricsStore, MetaInfoScope, Sample, etc.) is unchanged.

#### `osbenchmark/publisher.py`
- Added optional `_result_writer` support: if `reporting.results_writer` config key is set, results are also written via the Solr result writer (JSON or CSV).
- `SummaryResultsPublisher` now opens writer, writes per-metric-record, and closes writer around the publish cycle.

#### `osbenchmark/config.py`
- Default `node.http.port` changed from 39200 to 38983.
- Added Solr defaults: `solr.port = 8983`, `reporting.datastore.type = "in-memory"`.

#### `osbenchmark/worker_coordinator/worker_coordinator.py`
- `create_os_clients()` → `create_clients()`, `os_client_factory` → `client_factory`.
- `FeedbackActor.os_client` is set to `None` (redline CPU-feedback not supported without external metrics store).
- Removed REST API health check (`wait_for_rest_layer()` / `wait_for_rest_api()`).
- Added `_create_solr_telemetry_devices()`: creates Solr telemetry devices from target-hosts config.
- `prepare_telemetry()` now delegates to Solr telemetry device factory.
- The dead `os_client.search()` call at line 559 is still present and will `AttributeError` if the redline code path is ever reached.

#### `osbenchmark/builder/supplier.py`
- `OpenSearchSourceSupplier` → `SourceSupplier`, `OpenSearchDistributionSupplier` → `DistributionSupplier`, `OpenSearchFileNameResolver` → `FileNameResolver`.
- Removed all plugin-related classes and logic.
- Removed `SupportedOS` enum and OS/architecture detection.
- `TemplateRenderer` simplified: only `{{VERSION}}` template variable supported now.
- `create()` function signature changed: `plugins` parameter removed.

#### `osbenchmark/builder/launchers/local_process_launcher.py`
- Binary path changed from `opensearch` to `solr` with `start` subcommand.
- Added `--cloud` flag for SolrCloud mode.
- PID file location changed to `{binary_path}/bin/solr-{port}.pid`.
- `OPENSEARCH_JAVA_OPTS` → `SOLR_JAVA_OPTS`, `OPENSEARCH_JAVA_HOME` → `JAVA_HOME`.
- Removed bundled JDK detection logic.

#### `osbenchmark/builder/installers/preparers/solr_preparer.py` (renamed from `opensearch_preparer.py`)
- Adapted to extract Solr tarball (was opensearch tarball).
- Uses glob to find extracted `solr*` directory.
- Sets data path to `{binary_path}/data`.
- Deletes pre-bundled Solr config files to allow user-provided configsets.

#### `osbenchmark/builder/downloaders/distribution_downloader.py` (renamed)
- URL template and filename resolution adapted for Solr distribution URLs.

#### `osbenchmark/version.py`
- `minimum_os_version()` docstring updated: "minimum version of Solr" but reads from `min-os-version.txt` (file not renamed, currently contains `1.0.0`).
- `revision()` docstring still says "OSB is installed in development mode".
- Comments refer to "OSB" throughout.

#### `osbenchmark/workload_generator/extractors.py` / `workload_generator.py`
- References to `Index`, `DataStream`, `IndexTemplate` replaced with `Collection`.
- Workload generator adapted to emit Solr collection specs instead of OpenSearch index mappings.

#### `osbenchmark/visualizations/benchmark_report_renderer.py`
- HTML title and heading updated from "OpenSearch Benchmark Report" to "Solr Benchmark Report".
- Variable names `osb_ver` and `osb_rev` retained internally (not changed).
- Report table still displays "OSB Version" and "OSB Revision (git)" labels.

#### `setup.py`
- Removed dependencies: `opensearch-py[async]`, `aiokafka`, `opensearch-protobufs`.
- Added dependencies: `pysolr>=3.10.0`, `requests>=2.28.0`, `pandas>=1.4.3`, `PyYAML>=5.4`.
- Entry points: `opensearch-benchmark` / `osb` → `solr-benchmark` / `sb`, `solr-benchmarkd` / `sbd`.

#### `osbenchmark/resources/workload-schema.json`
- One occurrence: "depends on the benchmark candidate settings and OpenSearch version" → "Solr version".

#### `osbenchmark/resources/benchmark.ini`
- Default configuration updated with Solr-specific paths and settings.

#### `osbenchmark/resources/docker-compose.yml.j2`
- OpenSearch image references replaced with Solr image references.

#### `osbenchmark/resources/default-test-procedures.json.j2` / `custom-test-procedures.json.j2`
- Default operation types updated from OpenSearch-specific to Solr-specific operations.

---

## 4. Findings

The following are likely errors, oversights, or violations of the refactor goals.

---

### F1 — Missing ASF License Headers (4 files)

The following new or renamed source files are missing the ASF Apache-2.0 license header that all other files in the project carry:

- `osbenchmark/builder/installers/preparers/solr_preparer.py` (105 lines)
- `osbenchmark/builder/downloaders/distribution_downloader.py` (62 lines)
- `osbenchmark/builder/downloaders/source_downloader.py` (53 lines)
- `osbenchmark/builder/downloaders/repositories/distribution_repository_provider.py` (25 lines)

All other new files in `osbenchmark/solr/` and `osbenchmark/tools/` have correct headers. The above four are the renamed survivors from the `opensearch_*` files where the header was not carried over.

---

### F2 — Dead Code: Backup Runners Use OpenSearch-Specific API

`osbenchmark/worker_coordinator/runner.py` contains five registered runners that call OpenSearch-specific `client.snapshot.*` methods:

- `DeleteBackupRepository` — calls `client.snapshot.delete_repository()`
- `CreateBackupRepository` — calls `client.snapshot.create_repository()`
- `CreateBackup` — calls `client.snapshot.create()`
- `WaitForBackupCreate` — calls `client.snapshot.status()`
- `RestoreBackup` — calls `client.snapshot.restore()`

All five are registered via `register_default_runners()` and are callable from workloads. If invoked against Solr, they will raise `AttributeError` because the `SolrClient` stub has no `snapshot` attribute. The TODOs reference the correct Solr Backup V2 API but the old code was not removed or disabled. These runners should either be removed from `register_default_runners()` until ported, or raise a `NotImplementedError` with a helpful message.

---

### F3 — Dead Code: Composite Runner Allows OpenSearch-Only Operations

`osbenchmark/worker_coordinator/runner.py:674–685`, the `Composite` runner's `supported_op_types` list still includes:

```python
"create-point-in-time",
"delete-point-in-time",
"list-all-point-in-time",
"submit-async-search",
"get-async-search",
"delete-async-search"
```

These are all OpenSearch-specific concepts (Point-in-Time API, Async Search API) with no Solr equivalent. They are registered as allowed operation types, but their corresponding runners were deleted. If a workload references them inside a `composite` operation, the framework will accept the op-type but `runner_for()` will fail at runtime with an unknown operation type.

---

### F4 — Dead Code: `os_client.search()` Call in FeedbackActor

`osbenchmark/worker_coordinator/worker_coordinator.py:559` contains:

```python
resp = self.os_client.search(index=self.metrics_index, body=body)
```

`self.os_client` is always set to `None` (line 314 and 358). If the redline CPU-feedback code path is ever executed, this will raise `AttributeError: 'NoneType' object has no attribute 'search'`. The redline feature is partially wired (config keys still read, redline logic still runs in `worker_coordinator.py:1037–1122`), so this is a latent crash, not truly unreachable.

---

### F5 — Dead Code: Obsolete OS Telemetry Classes Still in `telemetry.py`

The following OS-specific telemetry classes remain in `osbenchmark/telemetry.py` but are not registered in any device list and not instantiated anywhere:

- `CcrStats` / `CcrStatsRecorder` — Cross-Cluster Replication (OpenSearch-only feature)
- `RecoveryStats` / `RecoveryStatsRecorder` — Shard recovery stats (ES/OS API)
- `NodeStats` / `NodeStatsRecorder` — OpenSearch `_nodes/stats` endpoint
- `SearchableSnapshotsStats` — OpenSearch searchable snapshots (OS-only)
- `TransformStats` / `TransformStatsRecorder` — OpenSearch transforms (OS-only)
- `SegmentReplicationStats` / `SegmentReplicationStatsRecorder` — OpenSearch segment replication (OS-only)

These ~800 lines of dead code will never execute against Solr and cannot be enabled via `--telemetry`. They should be removed.

---

### F6 — Dead Code: `CompositeTestRunStore` in `metrics.py`

`osbenchmark/metrics.py:1047–1180` retains `CompositeTestRunStore` — an OpenSearch-backed test-run store — with the comment "retained from the upstream OpenSearch Benchmark codebase but are not wired into any active code path." This is deliberate, but it is still dead code that will never run. If not needed, it should be removed. If retained for future use, it should at minimum be marked clearly so `make lint` rules don't flag it as unused.

---

### F7 — OpenSearch Branding in `osbenchmark/version.py`

The `version.py` module has not been updated:

- `minimum_os_version()` docstring: *"minimum version of Solr"* but still reads from `min-os-version.txt` (filename not updated).
- `revision()` docstring: *"OSB is installed in development mode"*.
- Comments throughout use "OSB".
- `min-os-version.txt` contains `1.0.0`, which is an OSB version number, not a valid Solr version. The minimum supported Solr version (likely 9.0.0) has not been set.

---

### F8 — `SolrClient` Is a Non-Functional Stub, But Runners Bypass It

`osbenchmark/client.py` defines `SolrClient` which inherits `RequestContextHolder` and contains a no-op transport. The framework creates one `SolrClient` per worker and passes it as `client` to every runner's `__call__(self, client, params)`.

The Solr runners in `osbenchmark/solr/runner.py` entirely ignore this `client` argument and instead create their own `pysolr.Solr` instances from params directly (e.g., `_solr_client(params)` creates a fresh `pysolr.Solr` on each call). This means:

- The `RequestContextHolder` timing context on `SolrClient` is bypassed for all Solr operations.
- Connection pooling, authentication, and SSL config are not centralized.
- Each operation creates its own HTTP connection without lifecycle management.
- The `client` parameter in runner signatures is misleading — it appears to be the shared client but is never used.

The preferred approach per the refactor goals would be to make `SolrClient` a proper wrapper around `pysolr.Solr` and `SolrAdminClient`, so the framework's client lifecycle and timing context work correctly.

---

### F9 — `SolrAdminClient` Not Used by Renamed Builder Modules

The renamed downloader files (`distribution_downloader.py`, `source_downloader.py`, `distribution_repository_provider.py`) use direct `urllib.request` or `subprocess` calls for HTTP operations. They do not use the new `SolrAdminClient` (from `osbenchmark/solr/client.py`), which is the established shared client module. This is somewhat expected since the downloader operates before Solr is running, but version probing during download resolution (if needed) would duplicate HTTP logic that already exists in `SolrAdminClient`.

---

### F10 — `osbenchmark/telemetry.py:SegmentStats` Uses Direct HTTP Instead of `SolrAdminClient`

`SegmentStats` (rewritten for Solr) makes direct `requests.get()` calls to the Solr Luke API instead of going through `SolrAdminClient`. This violates the established pattern where all Solr admin HTTP calls should go through the shared client. It also means SegmentStats has its own independent connection setup with no pooling or consistent auth handling.

---

### F11 — `visualizations/benchmark_report_renderer.py` Retains "OSB" Labels

The report renderer was partially updated (title and heading changed to "Solr Benchmark Report") but:

- Variable names `osb_ver` and `osb_rev` are still used internally.
- The report table still displays **"OSB Version"** and **"OSB Revision (git)"** as row labels visible to end users.

---

### F12 — `osbenchmark/workload/params.py` Removed Without Full Solr Replacement

The file lost all OpenSearch-specific param sources but only gained `DeleteCollectionParamSource`. There are no Solr equivalents for several param sources that have Solr counterparts (e.g., no `CreateCollectionParamSource` in `params.py` — create-collection params are handled inline in `solr/runner.py`). This means collection creation parameters are not validated at workload load time, only at execution time, which is inconsistent with how the framework handles other operations.

---

### F13 — `osbenchmark/resources/workload-schema.json` Has Residual "OSB" Reference

The workload JSON schema's description for the `cache` parameter still contains:

> "By default, OSB will define no value thus the default depends on the benchmark candidate settings and Solr version."

The "OSB" abbreviation in user-facing schema documentation should be replaced with "ASB" or "solr-benchmark".

---

### F14 — Git Rename Tracking Artifact: `docs/user-guides/index.md` → `tests/unit/__init__.py`

Git detected a 100% similarity rename between the old `docs/user-guides/index.md` (deleted) and the new `tests/unit/__init__.py` (empty file added). This is a false positive from git rename detection — the two files are completely unrelated. While not a code bug, it indicates both files were empty and git confused them. No action needed but worth noting.

---

### Summary Table

| # | Category | Severity | Description |
|---|---|---|---|
| F1 | Missing license header | Medium | 4 renamed builder files missing ASF header |
| F2 | Dead code / wrong API | High | Backup runners call OpenSearch `client.snapshot.*` — will crash |
| F3 | Dead code / wrong ops | Medium | Composite runner allows removed OS-only operations |
| F4 | Dead code / latent crash | High | `os_client.search()` call on `None` in redline path |
| F5 | Dead code | Medium | ~800 lines of obsolete OS telemetry classes never invoked |
| F6 | Dead code | Low | `CompositeTestRunStore` deliberately retained but inert |
| F7 | Branding remnant | Low | `version.py` still says OSB; `min-os-version.txt` has wrong version |
| F8 | Architectural gap | High | `SolrClient` stub bypassed; runners create own connections |
| F9 | API consistency | Low | Downloader modules don't use shared `SolrAdminClient` |
| F10 | API consistency | Medium | `SegmentStats` bypasses `SolrAdminClient` with direct `requests.get()` |
| F11 | Branding remnant | Low | Report table shows "OSB Version / OSB Revision" to users |
| F12 | Incomplete refactor | Medium | No `CreateCollectionParamSource` in `params.py`; validation deferred to runtime |
| F13 | Branding remnant | Low | Workload schema still says "OSB" in user-facing description |
| F14 | Git artifact | Info | False-positive rename: old doc → new empty `__init__.py` |
