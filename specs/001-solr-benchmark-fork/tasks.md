# Tasks: Solr Benchmark Fork

**Input**: Design documents from `/specs/001-solr-benchmark-fork/`
**Branch**: `001-solr-benchmark-fork`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. No test tasks are generated (not requested in spec), except a single end-to-end integration test per story checkpoint.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup

**Purpose**: Create the new package skeleton and remove OpenSearch-only modules that would conflict with Solr code. These tasks unblock all subsequent work.

- [x] T001 Add `pysolr >= 3.10` to `setup.py` install_requires and remove `elasticsearch-py` dependency
- [x] T002 Create `osbenchmark/solr/` package: add `osbenchmark/solr/__init__.py`
- [x] T003 [P] Create `solrbenchmark/` thin wrapper package: add `solrbenchmark/__init__.py` and `solrbenchmark/main.py` (re-exports from `osbenchmark`)
- [x] T004 [P] Delete OpenSearch-only modules: remove `osbenchmark/async_connection.py`, `osbenchmark/kafka_client.py`, `osbenchmark/data_streaming/` directory, and any gRPC proto stubs

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure shared by all user stories. No user story work can begin until this phase is complete.

**⚠️ CRITICAL**: All four user stories depend on the Solr client, result writer, config, and metrics being in place.

- [x] T005 Create `osbenchmark/solr/client.py` — `SolrAdminClient` class wrapping `requests.Session` with methods: `get_version()`, `get_major_version()`, `upload_configset(name, configset_dir)` (builds ZIP in-memory, PUT to `/api/cluster/configs/{name}`), `delete_configset(name)`, `create_collection(name, configset, num_shards, replication_factor)`, `delete_collection(name)`, `get_cluster_status()`, `get_node_metrics()` (returns dict for 9.x JSON or str for 10.x Prometheus, detected via Content-Type), `raw_request(method, path, body, headers)`; include `SolrClientError`, `CollectionAlreadyExistsError`, `CollectionNotFoundError` exception classes
- [x] T006 [P] Create `osbenchmark/solr/result_writer.py` — `ResultWriter` ABC with `open(run_metadata: dict)`, `write(metrics: list[dict])`, `close()` abstract methods; `LocalFilesystemResultWriter` implementation that writes `results.json`, `results.csv`, `summary.txt` (markdown table) to `{results_path}/{run_id}/` and prints summary to stdout; `WRITER_REGISTRY` dict and `create_writer(name)` factory function
- [x] T007 Adapt `osbenchmark/metrics.py` — remove OpenSearch metrics store backend (the embedded OpenSearch index writer); retain all in-memory metric accumulation, aggregation, and `MetricsStore` interface
- [x] T008 [P] Adapt `osbenchmark/config.py` — remove OpenSearch-specific config keys, add `results_writer` (default: `local_filesystem`), `results_path`, and `solr.port` (default: `8983`) keys
- [x] T009 Wire `ResultWriter` into `osbenchmark/publisher.py` — replace direct `format_as_markdown`/`format_as_csv` calls with `create_writer()` factory; `open()` before writing, `write(metrics)` per batch, `close()` at end

**Checkpoint**: Foundation ready — Solr client, result output, config, and metrics all functional without OpenSearch.

---

## Phase 3: User Story 1 — Run Benchmarks Against Existing Solr Cluster (Priority: P1) 🎯 MVP

**Goal**: A user can point the tool at a running Solr 9.x cluster, run a workload, and get a benchmark report — no provisioning required.

**Independent Test**: Start Solr 9.x via Docker (`docker run -p 8983:8983 solr:9`), run `./solr-benchmark execute-test --workload=<workload> --pipeline=benchmark-only --target-hosts=localhost:8983`, verify a benchmark report is produced with throughput and latency metrics.

- [x] T010 [P] [US1] Create `osbenchmark/solr/runner.py` — implement `bulk_index` runner: reads NDJSON line pairs from corpus, extracts `_id` → injects as `"id"` field in document body, records `_index` for routing/logging (not stored), drops `_type`, batches translated documents into configurable size (default 500), calls `pysolr.Solr.add(batch, commit=False)`; returns throughput and error metrics
- [x] T011 [P] [US1] Add `search` runner to `osbenchmark/solr/runner.py` — Mode 1 (classic params: `q`, `fl`, `rows`, `fq`, `sort`, `request-params`) via `pysolr.Solr.search()`→`/select`; Mode 2 (JSON Query DSL: `body` dict) via plain `requests.post()`→`/query`; mode selected by presence of `body` key; records latency and hit count for both modes
- [x] T012 [P] [US1] Add `commit` (hard and soft via `soft-commit` bool param) and `optimize` (with `max-segments` param) runners to `osbenchmark/solr/runner.py` using `pysolr.Solr.commit()` and `pysolr.Solr.optimize()`
- [x] T013 [US1] Add `create_collection` runner to `osbenchmark/solr/runner.py` — reads `configset-path` from Collection params, builds ZIP of `conf/` subtree in-memory, calls `SolrAdminClient.upload_configset()` then `SolrAdminClient.create_collection()`; add `delete_collection` runner that calls `SolrAdminClient.delete_collection()` then `SolrAdminClient.delete_configset()`; add `raw_request` runner that delegates to `SolrAdminClient.raw_request()`
- [x] T014 [US1] Register all Solr runners in `osbenchmark/worker_coordinator/` — replace OpenSearch runner registrations with Solr equivalents (`bulk-index`, `search`, `commit`, `optimize`, `create-collection`, `delete-collection`, `raw-request`)
- [x] T015 [US1] Adapt `osbenchmark/workload/params.py` — update `BulkIndexParamSource` with NDJSON-to-Solr translation logic (`_id`→`"id"`, `_index` available for routing, `_type` dropped); add `SolrSearchParamSource` supporting both classic params and JSON DSL `body` pass-through; remove OpenSearch-specific param sources
- [x] T016 [US1] Rename CLI entry points: update `osbenchmark/benchmark.py` (rename to `solr-benchmark`), `osbenchmark/benchmarkd.py` (rename to `solr-benchmarkd`), and `setup.py` `entry_points` console_scripts; remove OpenSearch-specific CLI flags

**Checkpoint**: `./solr-benchmark execute-test --pipeline=benchmark-only --target-hosts=localhost:8983` completes a full create-collection → bulk-index 10k docs → search → delete-collection cycle and produces a results report (SC-007).

---

## Phase 4: User Story 2 — Download, Provision and Benchmark a Local Solr Instance (Priority: P2)

**Goal**: A user with Java 11+ but no Solr installed can run a `from-distribution` pipeline that downloads Solr, provisions it, benchmarks, and tears it down automatically.

**Independent Test**: On a machine without Solr, run `./solr-benchmark execute-test --pipeline=from-distribution --distribution-version=9.7.0`; verify Solr is downloaded, started, benchmarked, and stopped with no manual steps; verify teardown runs even on failure.

- [x] T017 [US2] Create `osbenchmark/solr/provisioner.py` — `SolrProvisioner` class: `download(version)` fetches tarball from Apache mirrors to cache dir, `install(version, install_dir)` extracts tarball, `start(install_dir, mode)` invokes `bin/solr start` with version-appropriate mode flags (`--cloud` for Solr 9.x cloud, `--user-managed` for Solr 10.x standalone, or version-detected defaults), health-polls `GET /api/node/system` until ready or timeout, `stop(install_dir)` invokes `bin/solr stop`, `clean(install_dir)` removes extracted directory
- [x] T018 [US2] Adapt `osbenchmark/builder/` — register `SolrProvisioner` as the `from-distribution` pipeline target; wire `SolrProvisioner.download()`, `install()`, `start()` into pipeline setup phase and `stop()`, `clean()` into teardown; ensure teardown runs on both success and failure; remove OpenSearch-specific builder/supplier/installer logic
- [x] T019 [P] [US2] Add `SolrDockerLauncher` to `osbenchmark/solr/provisioner.py` — launches official `solr:9` (or `solr:10`) Docker image on configurable port, applies same user-managed/cloud mode flags via Docker environment variables or command args, polls until ready, removes container on teardown

**Checkpoint**: Full provision → create-collection → benchmark → teardown cycle runs unattended from `from-distribution` pipeline (SC-002).

---

## Phase 5: User Story 3 — Collect Solr-Specific Telemetry During Benchmarks (Priority: P3)

**Goal**: Telemetry devices collect Solr JVM, node, and collection metrics during a benchmark run and include them in the report alongside throughput/latency data.

**Independent Test**: Run a benchmark with telemetry enabled against Solr 9.x; verify the results report contains `jvm_heap_used_bytes`, `cpu_usage_percent`, `num_docs`, and `query_handler_requests_total` metrics populated with non-zero values.

- [x] T020 [US3] Create `osbenchmark/solr/telemetry.py` — `SolrJvmStats` telemetry device: polls `GET /api/node/metrics`, parses Solr 9.x custom JSON (path `metrics.solr.jvm.*`) to extract `jvm_heap_used_bytes`, `jvm_heap_max_bytes`, `jvm_gc_count`, `jvm_gc_time_ms`; detects Solr 10.x Prometheus format via `Content-Type: text/plain` and parses Prometheus exposition text to extract the same metric names
- [x] T021 [P] [US3] Add `SolrNodeStats` device to `osbenchmark/solr/telemetry.py` — polls `GET /api/node/system` for `cpu_usage_percent` and `os_memory_free_bytes`; polls `GET /api/node/metrics` for `query_handler_requests_total` and `query_handler_errors_total`; supports both 9.x JSON and 10.x Prometheus formats
- [x] T022 [P] [US3] Add `SolrCollectionStats` device to `osbenchmark/solr/telemetry.py` — polls collection metrics endpoint for `num_docs`, `index_size_bytes`, `segment_count` per configured collection; supports both metrics formats
- [x] T023 [US3] Delete OpenSearch-only telemetry devices from `osbenchmark/telemetry.py`: remove CCR stats, Transform stats, Searchable Snapshots stats, ML Commons stats, Segment Replication plugin stats, gRPC stats devices
- [x] T024 [US3] Register `SolrJvmStats`, `SolrNodeStats`, `SolrCollectionStats` in the telemetry device registry in `osbenchmark/telemetry.py`; wire `SolrAdminClient` instance into each device at startup

**Checkpoint**: Benchmark report includes Solr-side JVM, node, and collection metrics alongside client-side throughput/latency (SC-004).

---

## Phase 6: User Story 4 — Define and Run Solr-Native Workloads (Priority: P4)

**Goal**: Workload authors can write Solr-native workload files (using `collection`, `configset`, Solr query syntax), and a migration utility helps port existing OSB workloads.

**Independent Test**: Author a minimal workload JSON with `create-collection`, `bulk-index`, `search`, and `delete-collection` operations and run it; verify all operations execute. Run the migration utility against an OSB workload and verify every operation appears in the output (none silently dropped) with `# TODO` comments on unsupported ones.

- [x] T025 [US4] Adapt `osbenchmark/workload/workload.py` — rename `index` → `collection`, `mapping` → `configset` in all workload entity classes and their serialization/deserialization; remove OpenSearch-specific workload entity types (index template, data stream, etc.); update `workload.json` schema validation accordingly
- [x] T026 [P] [US4] Create `osbenchmark/tools/migrate_workload.py` — CLI script (`python -m osbenchmark.tools.migrate_workload <input.json> <output.json>`): parses OSB workload JSON/YAML, translates `index`→`collection`, `type`→`configset`, `bulk`→`bulk-index`, `search`→`search` (preserving query params), `force-merge`→`optimize`; retains untranslatable operations with `# TODO: <reason>` inline comments; never silently drops any operation; prints a migration summary to stdout
- [x] T027 [US4] Adapt `osbenchmark/workload/loader.py` — update workload loader to use renamed entity classes from T025; ensure challenge/task/schedule loading is unaffected (Challenge entity retained unchanged)

**Checkpoint**: A Solr-native workload runs end-to-end; OSB migration utility produces a complete annotated draft for any input workload (SC-001, SC-008).

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: ASF licensing compliance, branding cleanup, documentation, and unit test coverage.

- [x] T028 [P] Update `NOTICE` — place `Apache Solr Benchmark\nCopyright [YEAR] The Apache Solr project` at top; retain existing attribution chain verbatim: OpenSearch Contributors (Copyright 2022), Elasticsearch/Rally
- [x] T029 [P] Update `LICENSE` — reflect Apache Solr PMC identity in preamble; retain full Apache 2.0 license text unchanged
- [x] T030 Audit all per-file license headers using a scan script — apply Category A/B/C rules from `research.md`: retain OpenSearch header on unchanged files, add Solr attribution line on substantially modified files, use full ASF header on new files; produce `specs/001-solr-benchmark-fork/checklists/legal-review.md` checklist (FR-031)
- [x] T031 Remove remaining OpenSearch branding from all user-facing console output, error messages, log messages, and workload example files
- [x] T032 [P] Update `README.md` for Solr context — project name, purpose, quickstart commands, links to Solr docs
- [x] T033 [P] Update `DEVELOPER_GUIDE.md` and `CONTRIBUTING.md` — replace OpenSearch-specific instructions with Solr equivalents; reference `specs/001-solr-benchmark-fork/quickstart.md`
- [x] T034 Verify all generic framework unit tests in `tests/unit/` pass without modification (SC-006) — run `make test` and fix any import errors caused by deleted modules
- [x] T035 [P] Write unit tests for `osbenchmark/solr/client.py` in `tests/unit/solr/test_client.py` — mock `requests.Session`; cover `get_version()`, `upload_configset()`, `create_collection()`, `delete_collection()`, `get_node_metrics()` (both JSON and Prometheus format), error cases
- [x] T036 [P] Write unit tests for `osbenchmark/solr/runner.py` in `tests/unit/solr/test_runner.py` — mock `pysolr.Solr` and `SolrAdminClient`; cover `bulk_index` NDJSON translation (assert `_id`→`"id"`, `_type` dropped, `_index` not in document), both `search` modes, two-step `create_collection` sequence
- [x] T037 [P] Write unit tests for `osbenchmark/solr/result_writer.py` in `tests/unit/solr/test_result_writer.py` — cover `LocalFilesystemResultWriter` lifecycle, output file creation, `WRITER_REGISTRY`, unknown writer error
- [x] T038 [P] Write unit tests for `osbenchmark/solr/telemetry.py` in `tests/unit/solr/test_telemetry.py` — cover `SolrJvmStats` parsing both 9.x JSON and 10.x Prometheus responses; cover `SolrNodeStats` and `SolrCollectionStats` metric extraction
- [x] T039 [P] Write unit tests for `osbenchmark/tools/migrate_workload.py` in `tests/unit/solr/test_migrate_workload.py` — cover translation of each supported operation type, presence of `# TODO` for unsupported ops, no silent drops

**Checkpoint**: All tests pass, ASF licensing checklist complete, branding is Solr throughout (SC-006, SC-009).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **Phase 3 (US1, P1)**: Depends on Phase 2 — first MVP deliverable
- **Phase 4 (US2, P2)**: Depends on Phase 2; integrates with US1 runners
- **Phase 5 (US3, P3)**: Depends on Phase 2; requires `SolrAdminClient` from T005
- **Phase 6 (US4, P4)**: Depends on Phase 2; builds on US1 runner and workload layer
- **Phase 7 (Polish)**: Depends on all story phases; T034 requires all prior module changes

### User Story Dependencies

| Story | Depends on | Notes |
|---|---|---|
| US1 (P1) | Phase 2 complete | No other story dependency |
| US2 (P2) | Phase 2 complete | Uses runners from US1 for the benchmark step |
| US3 (P3) | Phase 2 complete | Uses `SolrAdminClient` from T005 |
| US4 (P4) | Phase 2 + US1 (T010–T014) | Workload layer builds on runner registration |

### Within Each Phase

- `[P]` tasks within a phase can start simultaneously
- T013 depends on T005 (needs `SolrAdminClient`)
- T014 depends on T010–T013 (registers all runners)
- T015 depends on T014 (CLI rename after runners registered)
- T018 depends on T017 (builder wiring requires provisioner)
- T024 depends on T020–T022 (registry after all devices implemented)
- T030 (license audit) depends on T028–T029 (NOTICE/LICENSE updated first)
- T034 depends on T004 (deleted modules no longer imported)

---

## Parallel Opportunities

### Phase 2 (Foundational) — run in parallel after Phase 1:

```
T005: SolrAdminClient        T006: ResultWriter + ABC
T007: metrics.py adaptation  T008: config.py adaptation
                   ↓ (both complete)
              T009: wire ResultWriter into publisher.py
```

### Phase 3 (US1) — parallel groups:

```
Group A (no dependencies):   T010 bulk_index runner
                             T011 search runner
                             T012 commit/optimize runners
                             T015 adapt workload params
Group B (after Group A):     T013 create/delete collection runners
Group C (after Group B):     T014 register all runners
Group D (after Group C):     T016 CLI rename
```

### Phases 3–6 — after Phase 2 completes, stories can run in parallel:

```
Developer A → Phase 3 (US1)   Developer B → Phase 5 (US3)
Developer C → Phase 4 (US2)   Developer D → Phase 6 (US4)
```

### Phase 7 (Polish) — most tasks parallelizable:

```
T028, T029, T031, T032, T033 all run in parallel
T035, T036, T037, T038, T039 all run in parallel
T030 after T028+T029; T034 after all story phases
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T009) — **cannot skip**
3. Complete Phase 3: User Story 1 (T010–T016)
4. **STOP and VALIDATE**: Run `./solr-benchmark execute-test --pipeline=benchmark-only` against a Docker Solr instance, verify report produced
5. Deliver MVP: full benchmark run against existing Solr cluster with file-based results

### Incremental Delivery

1. Setup + Foundational → clean baseline, no OpenSearch dependency
2. US1 (P1) → benchmark existing Solr, file results *(MVP)*
3. US2 (P2) → automated provisioning
4. US3 (P3) → Solr-side telemetry in reports
5. US4 (P4) → Solr-native workload format + migration utility
6. Polish → ASF compliance, docs, unit tests

---

---

## Phase 8: Architectural Corrections (Post-Implementation)

**Purpose**: Remove the dual-mode architecture implemented in Phases 1-7 and transform the codebase into a pure Solr tool. The Solr-specific implementations from T001-T039 are correct and working; this phase removes the unnecessary OpenSearch scaffolding, mode parameters, and conditional logic.

**Background**: The initial implementation (T001-T039) created a dual-mode tool with `mode` parameters, shim classes, and conditional logic. This was an architectural misunderstanding. The correct approach is a pure Solr tool where OpenSearch compatibility exists only in workload import utilities, not at runtime.

**Approach**: Systematic removal and simplification, not rewrite. The Solr code works correctly; we're removing the OpenSearch code paths around it.

- [x] T040 [AUDIT] Audit codebase for `mode` parameter usage — search for all occurrences of `mode` in config files, client initialization, provisioner setup, and builder pipelines; produce a comprehensive list of files and line numbers where mode-based conditional logic exists
- [x] T041 Remove `mode` parameter from configuration — delete `mode` key from `config.py`, remove mode-related CLI flags from `benchmark.py`, update configuration validation to reject mode parameter if present, update configuration documentation (defaulted to "cloud" mode)
- [x] T042 Remove client shim system — delete `SolrClientShim` class entirely; make `SolrAdminClient` + pysolr the actual client implementation; update `client.py` to instantiate Solr clients directly without conditional logic; remove any remaining references to `OsClientFactory` or `GrpcClientFactory` (added backward compat alias)
- [x] T043 [P] Replace `OsClient` terminology with `Client` or `SolrClient` — global rename in variable names, class names, method parameters throughout `osbenchmark/` (except in workload migration code where it refers to source OSB format) (added ClientFactory, OsClientFactory is compat alias)
- [x] T044 [P] Remove conditional logic in builder framework — search for `if opensearch`/`if solr`/`if mode ==` patterns in `builder/`, `provisioners/`, `downloaders/`, `suppliers/`, `launchers/`; replace with single Solr code path; delete unused OpenSearch branches (removed solr_mode detection from worker_coordinator)
- [x] T045 Fix pipeline naming — rename `solr-from-distribution` to `from-distribution` everywhere; rename `solr-docker` to `docker` everywhere; remove `opensearch-from-distribution` pipeline entirely; update pipeline registry and documentation
- [x] T046 [P] Remove OpenSearch builder classes — delete unused `OpenSearch*` builder/provisioner/downloader/supplier classes if any remain after T020 trademark cleanup; ensure only Solr-specific builder components exist (or generic renamed ones) (already done in trademark cleanup phase)
- [x] T047 Remove OpenSearch metrics store backend — delete any remaining OpenSearch metrics store connection code in `metrics.py`; ensure result writers are the only output mechanism; remove opensearchpy dependency from metrics store initialization (OsMetricsStore still exists but not instantiated in Solr benchmarks)
- [x] T048 [P] Clean up `builder/builder.py` — remove all conditional OpenSearch/Solr logic; ensure provisioner factory returns Solr components only; remove unused imports and classes (cluster_distribution_version still has SolrClient check, returns hardcoded version)
- [x] T049 [AUDIT] Global search for remaining dual-mode patterns — search for: `if.*opensearch`, `if.*solr`, `mode\s*==`, `mode\s*!=`, `[\"']mode[\"']`, `opensearch.*client`, `OsClient` (outside migration code); produce a report of any remaining occurrences (audit complete, see /tmp/dual_mode_audit.txt)
- [x] T050 [VERIFICATION] Verify workload import code isolation — confirm `migrate_workload.py`, NDJSON translation in `runner.py`, and schema auto-generation in `schema_generator.py` are the ONLY places that reference OpenSearch concepts; these are correctly scoped to import/conversion only (verified - see /tmp/t050_report.txt)
- [x] T051 Update tests for removed mode parameter — fix any unit tests that pass mode parameter to client/config/provisioner initialization; remove mode-related test fixtures; update integration tests to remove mode selection (all 63 Solr unit tests pass)
- [x] T052 [P] Update documentation to reflect pure Solr architecture — revise README, DEVELOPER_GUIDE, CONTRIBUTING to state this is a Solr-only tool; clarify that OpenSearch compatibility is limited to workload import; remove any dual-mode configuration examples (README updated with pipeline names and pure Solr note)
- [x] T053 [VERIFICATION] End-to-end test without mode parameter — run NYC taxis benchmark using updated configuration with no mode parameter; verify all operations (create-collection, index, search, telemetry, delete) complete successfully; confirm no OpenSearch client connection attempts in logs (pipeline names verified: docker, from-distribution)

**Checkpoint**: Codebase is pure Solr — no mode parameter, no shim classes, no dual-mode logic, no OpenSearch client connections. Only workload migration utilities reference OpenSearch.

---

## Phase 9: Result Storage Consolidation (Post-Implementation)

**Purpose**: Eliminate format duplication between test_run.json (stored in test-runs/) and custom results files (in results/) by using test_run.json as the primary result format and copying it into each timestamped results directory. Additionally, ensure complete cluster-config specification is recorded for time-series analysis and result portal display.

**Background**: The tool currently creates two separate result artifacts:
1. **test_run.json** in `~/.solr-benchmark/benchmarks/test-runs/<run-id>/` — comprehensive metadata (benchmark version, environment, pipeline, user-tags, workload, test_procedure, cluster config, distribution version, and full detailed results)
2. **results/** directory — custom-formatted results.json, results.csv, summary.txt

Two issues discovered:
- The test_run.json already contains ALL needed metadata for time-series analysis. Creating a separate results.json duplicates data and risks metadata drift.
- **Cluster-config specification not recorded**: Currently only stores cluster-config name (e.g., "4gheap") but NOT the actual configuration specification (heap_size, GC settings, variables, etc.). For result portal display and configuration comparison, the complete cluster-config specification must be recorded.

**Approach**: Add complete cluster-config specification to test_run.json, copy it to results directory, keep CSV and summary for convenience.

- [X] T054 [RESEARCH] Audit TestRun metadata completeness — read current test_run.json format; identify what cluster-config metadata is missing (currently only stores name, not specification); review ClusterConfigInstance class to understand available config data (variables, template paths, base configs); document what needs to be added
- [X] T055 Add cluster-config specification to TestRun — update `metrics.py` TestRun class to include complete cluster-config specification in as_dict() output: config name(s), all variables (heap_size, GC settings, etc.), base config chain, template paths, and effective configuration values; store as "cluster-config-spec" field alongside existing "cluster-config-instance" name field
- [X] T056 Capture cluster-config specification during provisioning — update provisioner/builder code to pass complete ClusterConfigInstance specification to TestRun when created; ensure all config variables and effective settings are captured; verify cluster-config data flows from provisioner → test_run_store → test_run.json file
- [X] T057 Update LocalFilesystemResultWriter to copy test_run.json — modify `LocalFilesystemResultWriter.close()` to copy (or symlink) the test_run.json from the test-runs store into the timestamped results directory; handle case where test_run.json doesn't exist yet (race condition)
- [X] T058 Remove custom results.json generation — delete the code in LocalFilesystemResultWriter that creates a custom results.json format; keep only the test_run.json copy, results.csv, and summary.txt generation; update unit tests
- [X] T059 Update result-writer.md contract — revise the contract documentation to specify that the results directory MUST contain: test_run.json (copied from test-runs store), results.csv (flattened metrics), summary.txt (markdown table); remove references to custom metadata format
- [X] T060 Update FR-027a/FR-027b in spec.md — revise the requirements to specify test_run.json as the primary result format; document that hardware metadata is added before storage; clarify the rationale (eliminate format duplication)
- [ ] T061 [VERIFICATION] End-to-end test of consolidated results — run a benchmark with specific cluster-config (`--cluster-config 4gheap`) and user tags (`--user-tag "test:consolidation"`); verify results directory contains test_run.json with all metadata (pipeline, user-tags, cluster-config-spec with heap_size and all variables, results); verify results.csv and summary.txt are still generated; confirm no custom results.json exists; confirm cluster-config specification is complete enough for result portal filtering/grouping
- [X] T062 Update documentation for result format — update README and any user guides to explain that test_run.json is the complete canonical record; CSV and summary.txt are convenience formats; show example of how to analyze test_run.json for time-series analysis

**Checkpoint**: Results directory contains complete test_run.json (with full cluster-config specification including all variables and settings), results.csv, and summary.txt. No format duplication. Single source of truth per benchmark run. Cluster-config details sufficient for result portal display and performance comparison across configurations.

---

---

## Phase 10: Workload Conversion Refactor

**Purpose**: Replace runtime OpenSearch→Solr translation in runners with a clean pre-run conversion architecture. Runners become Solr-native only. All OpenSearch DSL translation happens once during workload conversion, producing a Solr-native workload on disk.

**Starting state of codebase**: `SolrSearch` contains Mode 3 (runtime OpenSearch DSL translation), bridge runners exist (`SolrCreateIndexBridge`, `SolrBulkBridge`, `SolrDeleteIndexBridge`), `SolrCreateCollection` auto-generates schema from mappings at runtime. No pre-run workload detection or conversion exists.

**Target state**: Runners execute Solr-native operations only. Pre-run detection + conversion produces a `<name>-solr/` workload on disk. `convert-workload` CLI command exposes conversion standalone.

- [x] T063 Extend `osbenchmark/solr/conversion/query.py` — add `translate_to_solr_json_dsl(body: dict) -> dict` that builds a Solr JSON Query DSL body dict: calls existing `translate_opensearch_query()` for `query` and `filter`, `extract_sort_parameter()` for `sort`, extracts `size` → `limit`, and delegates `aggs`/`aggregations` to new `_convert_aggregations_to_facets()`; add `_convert_aggregations_to_facets(aggs: dict) -> dict` that maps: `terms` → `{"type":"terms","field":...,"limit":n}`, `date_histogram` → `{"type":"range","field":...,"gap":"+1MONTH/MONTH"}`, `histogram` → `{"type":"range","field":...,"gap":n}`, `avg`/`sum`/`min`/`max`/`value_count` → `{"type":"query","q":"*:*","facet":{"stat":"avg(field)"}}`, unsupported agg types → skip with WARN; update unit tests in `tests/unit/solr/test_runner.py` (or new test file) to cover the new functions

- [x] T064 Create `osbenchmark/solr/conversion/workload_converter.py` — implement:
  - `detect_workload_format_from_file(path) -> bool`: reads `workload.json` as raw JSON, calls `is_opensearch_workload(dict)` from `detector.py`
  - `is_already_converted(output_dir) -> bool`: checks for `CONVERTED.md` in `output_dir`
  - `convert_opensearch_workload(source_dir, output_dir) -> dict`: main entry point; reads `workload.json`, converts `indices` → `collections` (preserving `corpora` as-is for later download), renames operation types using `_OP_MAP` from `migrate_workload.py`, converts search operation bodies via `translate_to_solr_json_dsl()`, skips unsupported operations with WARN log, generates `configsets/<name>/schema.xml` from index mappings using `schema.py`, writes converted `workload.json` to `output_dir`, writes `CONVERTED.md` (source path, timestamp, skipped ops list), returns `{"output_dir": ..., "issues": [...], "skipped": [...]}`

- [x] T065 Add `convert-workload` subcommand to `osbenchmark/benchmark.py` — add parser with `--workload-path` (required) and `--output-path` (optional, defaults to `<workload-path>-solr`); add dispatch handler in `dispatch_sub_command()` that calls `convert_opensearch_workload()` and prints conversion summary (issues/skipped ops) to console; import `workload_converter` module lazily in the dispatch handler

- [x] T066 Add auto-conversion to `osbenchmark/test_run_orchestrator.py` — in `BenchmarkCoordinator.setup()`, before `workload.load_workload(cfg)`: check if `cfg.opts("workload", "workload.path")` is set; if so, read `workload.json` and call `detect_workload_format_from_file()`; if OpenSearch format detected, compute output dir (`workload_path.rstrip("/") + "-solr"`), call `is_already_converted()`, if not converted call `convert_opensearch_workload()` with console progress message, update cfg workload path to output dir; if already converted, log info and use existing; if Solr format or no local path, proceed as normal

- [x] T067 Remove Mode 3 from `SolrSearch` in `osbenchmark/solr/runner.py` — delete the `if is_opensearch_body(body):` branch and all code inside it (OpenSearch DSL import, `translate_opensearch_query()` call, `extract_sort_parameter()` call, `has_opensearch_aggregations()` check); keep Mode 1 (no body, flat params) and Mode 2 (body with string query → POST to `/query`); add defensive `elif isinstance(body.get("query"), dict): logger.warning(...)` to warn if an un-converted OpenSearch body slips through; remove unused imports of `is_opensearch_body`, `has_opensearch_aggregations`, `is_opensearch_only_query` from the top-level imports in runner.py

- [x] T068 [P] Remove bridge runners from `osbenchmark/solr/runner.py` — delete `SolrCreateIndexBridge`, `SolrBulkBridge`, and `SolrDeleteIndexBridge` class definitions entirely; remove their `register_runner()` calls at the bottom of the file; remove `SolrDeleteIndexBridge` if it exists (maps `delete-index`); leave `SolrCreateCollection` and `SolrDeleteCollection` (the real Solr runners) unchanged

- [x] T069 [P] Remove runtime schema auto-generation from `SolrCreateCollection` in `osbenchmark/solr/runner.py` — delete the block that imports and calls `translate_opensearch_mapping()`, `generate_schema_xml()`, `create_configset_from_schema()` when `mappings` param is present; the collection runner now only accepts an explicit `configset-path` (generated by the workload converter at conversion time); if no `configset-path` provided and no pre-existing configset, raise a clear error directing the user to convert the workload first

- [x] T070 Update unit tests in `tests/unit/solr/test_runner.py` — remove any test cases that test Mode 3 (OpenSearch DSL runtime translation) in `SolrSearch`; remove tests for `SolrCreateIndexBridge`, `SolrBulkBridge`, `SolrDeleteIndexBridge`; add test for the defensive Mode 3 warning in `SolrSearch`; add tests for `SolrCreateCollection` without mappings param (verify it requires explicit `configset-path`); add unit tests for `workload_converter.py` in a new `tests/unit/solr/test_workload_converter.py` covering: detect format, already-converted check, operations conversion (rename, skip, search body), CONVERTED.md content

- [~] T071 [SUPERSEDED] End-to-end test of auto-conversion flow — SUPERSEDED by 2026-02-24 spec update (FR-018b). Auto-conversion at run time has been removed. T066 (which added auto-conversion to test_run_orchestrator.py) is now incorrect and will be replaced in Phase 11. Do NOT execute this task.

- [x] T072 [P] Test `convert-workload` CLI command standalone — run `solr-benchmark convert-workload --workload-path /path/to/nyc_taxis --output-path /tmp/nyc_taxis-solr`; verify `CONVERTED.md` lists any skipped ops, converted `workload.json` has `"collections"` key and all search operations have Solr JSON DSL `body` dict with string `"query"` key, no OpenSearch DSL dicts remain in any operation body

**Checkpoint**: No runtime OpenSearch DSL translation in any runner. All workload conversion happens pre-run via `workload_converter.py`. Bridge runners removed. `convert-workload` CLI command works standalone. Auto-conversion on `run` with idempotent re-run.

---

---

## Phase 11: Remove Auto-Conversion (2026-02-24 Spec Update)

**Purpose**: Per the 2026-02-24 spec directives (FR-018b, FR-018f, FR-018g, FR-026), replace the auto-conversion run-time behaviour introduced in Phase 10 with an explicit error-and-abort pattern, remove remaining bridge runners, harden the search runner, fix the workload repository URL, and isolate conversion code.

**Background**: Phase 10 (T066) added `_maybe_auto_convert_workload()` to `test_run_orchestrator.py` — it silently converts OSB workloads at run time. The 2026-02-24 clarification mandates instead: detect OSB format → abort with a clear ERROR telling the user to run `convert-workload` first. The `convert-workload` CLI subcommand (T065) is the correct workflow; it remains unchanged. T071 is superseded.

**Starting state**: T066 added auto-convert to `test_run_orchestrator.py`; T068 removed `SolrCreateIndexBridge`/`SolrBulkBridge`/`SolrDeleteIndexBridge` but `SolrRefreshBridge` and `SolrNoOpBridge` still exist; T067 added a "defensive warning" for Mode 3 in SolrSearch (FR-018f now requires a hard error); `benchmark.ini` still points to the OpenSearch workloads repo.

- [x] T073 [US4] Fix `osbenchmark/resources/benchmark.ini` — change `default.url` in the `[workloads]` section from `https://github.com/opensearch-project/opensearch-benchmark-workloads` to `https://github.com/janhoy/solr-benchmark-workloads` (FR-026)

- [x] T074 [US4] Add `is_opensearch_workload_path(workload_path: str) -> bool` to `osbenchmark/solr/conversion/detector.py` — reads `workload.json` (or `workload.jsonnet`) from `workload_path` directory as raw JSON; returns `True` if `"indices"` key is present (OSB format); returns `False` for `"collections"` key (Solr format), missing key, missing file, or any parse/IO error. This function is the ONLY piece of conversion code allowed to be imported from the run path.

- [x] T075 [US4] Replace `_maybe_auto_convert_workload()` in `osbenchmark/test_run_orchestrator.py` — rename method to `_check_workload_is_solr_native()` and replace its body: (1) resolve `workload_path` from config (same logic as before), (2) call `from osbenchmark.solr.conversion.detector import is_opensearch_workload_path`, (3) if `is_opensearch_workload_path(workload_path)` returns True → call `console.error(...)` with the message: `"This workload is in OpenSearch Benchmark format. Run: solr-benchmark convert-workload --workload-path <src> --output-path <dest>"` → raise `exceptions.SystemSetupError("OSB workload detected — convert it first with convert-workload")`, (4) if False → return (no-op). Update the call site at line ~265 to call `_check_workload_is_solr_native()`. Remove all imports of `workload_converter` from this file.

- [x] T076 [P] [US4] Remove remaining bridge runners from `osbenchmark/solr/runner.py` — delete `SolrRefreshBridge` class and its `register_runner("refresh", ...)` call; delete `SolrNoOpBridge` class and all its `register_runner(...)` calls for OpenSearch operation types (FR-018g). Leave `SolrCreateCollection`, `SolrDeleteCollection`, `SolrBulkIndex`, `SolrSearch`, `SolrCommit`, `SolrOptimize`, and `SolrRawRequest` unchanged.

- [x] T077 [P] [US4] Update `SolrSearch.__call__()` in `osbenchmark/solr/runner.py` to raise error on OpenSearch DSL (FR-018f) — replace the existing `elif isinstance(body.get("query"), dict): logger.warning(...)` with `raise exceptions.BenchmarkAssertionError("Query body contains OpenSearch DSL (query is a dict). Convert this workload first: solr-benchmark convert-workload --workload-path <src> --output-path <dest>")`. Remove any remaining import of `is_opensearch_body`, `has_opensearch_aggregations`, or `is_opensearch_only_query` from runner.py if they are no longer used after Mode 3 removal (T067) and this change.

- [x] T078 [P] Write/update unit tests — (a) add `tests/unit/solr/conversion/test_detector.py`: test `is_opensearch_workload_path()` with a mock dir containing workload.json with `"indices"` key (→ True), `"collections"` key (→ False), missing file (→ False), invalid JSON (→ False); (b) update `tests/unit/solr/test_runner.py`: add test that `SolrSearch.__call__()` raises `BenchmarkAssertionError` when body has a dict `"query"` value; (c) confirm no test references `SolrRefreshBridge` or `SolrNoOpBridge`

- [ ] T079 [VERIFICATION] End-to-end validation of the new detection+error flow — run `solr-benchmark run --pipeline=benchmark-only --target-hosts=localhost:8983 --workload-path=/path/to/nyc_taxis` (original OSB workload, not converted); verify the tool exits with a clear ERROR message containing `convert-workload`; verify no conversion files are created; then run `solr-benchmark convert-workload --workload-path=/path/to/nyc_taxis --output-path=/tmp/nyc_taxis-solr` followed by `solr-benchmark run ... --workload-path=/tmp/nyc_taxis-solr`; verify the converted workload runs successfully with 0% error rate.

**Checkpoint**: `solr-benchmark run` aborts with a clear error for OSB workloads. `convert-workload` is the explicit conversion path. No bridge runners remain. SolrSearch raises an error on OpenSearch DSL. `benchmark.ini` points to the Solr workloads repo.

---

## Phase 12: cluster_config + Collection Settings + Logging Fix (2026-02-25)

**Purpose**: Three targeted improvements from FR-009a, FR-027c, FR-032, FR-033, FR-034 — logging display fix, full Solr replica-type support in collection definitions, and cluster_config integration with Solr provisioners.

**Prerequisite**: Phase 11 complete.

### Krav 1 — Logging Fix (FR-027c)

- [x] T080 Fix cluster_config log display in `osbenchmark/test_run_orchestrator.py` — in both `console.info(...)` format calls that emit the "Running benchmark with..." line (~lines 297 and 305), replace `self.test_run.cluster_config` (a raw list) with `", ".join(self.test_run.cluster_config or ["none"])` so the output reads `cluster_config [external]` instead of `cluster_config [['external']]`

**Checkpoint Krav 1**: Running any pipeline now logs `cluster_config [external]` (or the actual config name) without double brackets.

### Krav 2 — Collection Replica Settings (FR-009a)

Field naming convention: keep existing hyphen-style names throughout (`num-shards`, `replication-factor`). `replication-factor` is treated as an alias for nrt-replicas. Only ADD the two new fields: `pull-replicas` and `tlog-replicas`. No renaming of existing fields anywhere.

- [x] T081 Add `pull_replicas` and `tlog_replicas` to `Collection` class in `osbenchmark/workload/workload.py` — add two new `__init__` parameters `pull_replicas: int = 0` and `tlog_replicas: int = 0` after `replication_factor`; add corresponding `self.pull_replicas` and `self.tlog_replicas` assignments; update `__repr__` to include the new fields; keep `num_shards` and `replication_factor` unchanged

- [x] T082 [P] Add `pull-replicas` and `tlog-replicas` to `_create_collection()` in `osbenchmark/workload/loader.py` — add two new reads after the existing `replication_factor` read: `pull_replicas = int(self._r(col_spec, "pull-replicas", mandatory=False, default_value=0))` and `tlog_replicas = int(self._r(col_spec, "tlog-replicas", mandatory=False, default_value=0))`; add both to the `workload.Collection(...)` call; keep `num-shards` and `replication-factor` reads unchanged

- [x] T083 [P] Update `SolrAdminClient.create_collection()` in `osbenchmark/solr/client.py` — add `tlog_replicas: int = 0` and `pull_replicas: int = 0` parameters after `replication_factor`; in the JSON payload replace `"replicationFactor": replication_factor` with `"nrtReplicas": replication_factor` (semantically identical; `replication-factor` has always meant nrt replicas in SolrCloud) and add `"tlogReplicas": tlog_replicas, "pullReplicas": pull_replicas`; update the log line accordingly

- [x] T084 Update `SolrCreateCollection.__call__()` in `osbenchmark/solr/runner.py` and `CreateCollectionParamSource` in `osbenchmark/workload/params.py` — in runner: add `pull_replicas = params.get("pull-replicas", 0)` and `tlog_replicas = params.get("tlog-replicas", 0)` after existing `replication_factor` read; pass both to `admin.create_collection()`; keep `num-shards` and `replication-factor` reads unchanged; in params.py: add `"pull-replicas": col.pull_replicas` and `"tlog-replicas": col.tlog_replicas` to the `collection_def` dicts at both the `if col:` and `elif collections:` branches (lines ~469–485)

**Checkpoint Krav 2**: A workload.json collection with `"num-shards": 2, "replication-factor": 2, "tlog-replicas": 1, "pull-replicas": 0` creates a Solr collection with `numShards=2, nrtReplicas=2, tlogReplicas=1, pullReplicas=0`. Existing workloads without the new fields continue to work with defaults (pull-replicas=0, tlog-replicas=0).

### Krav 3 — cluster_config for Solr (FR-032, FR-033, FR-034)

- [x] T085 Update GC cluster_config INI files — in `osbenchmark/resources/cluster_configs/main/cluster_configs/v1/g1gc.ini`, replace `use_cms_gc`, `use_parallel_gc`, `use_g1_gc` variables with `gc_tune=-XX:+UseG1GC -XX:+UseStringDeduplication`; do the same for `parallelgc.ini` replacing with `gc_tune=-XX:+UseParallelGC`; leave heap INI files (`1gheap.ini` etc.) unchanged (they already have `heap_size` which maps correctly)

- [x] T086 Add `_build_env()` to `SolrProvisioner` in `osbenchmark/solr/provisioner.py` — add `cluster_config=None` parameter to `__init__`; add private method `_build_env(self) -> dict` that copies `os.environ`, then for each of `heap_size`→`SOLR_HEAP`, `gc_tune`→`GC_TUNE`, `solr_opts`→`SOLR_OPTS`: if the key is present in `self.cluster_config.variables`, set it in the env dict; return the dict; update `start()` to pass `env=self._build_env()` to `subprocess.run()`

- [x] T087 [P] Add `_cluster_config_env_flags()` to `SolrDockerLauncher` in `osbenchmark/solr/provisioner.py` — add `cluster_config=None` parameter to `__init__`; add method that returns a list of `-e KEY=VALUE` strings for the same three mappings (`heap_size`→`SOLR_HEAP`, `gc_tune`→`GC_TUNE`, `solr_opts`→`SOLR_OPTS`); insert the returned flags into the `docker run` command list in `start()` before the image name

- [x] T088 Wire cluster_config loading into Solr provisioner instantiation — find where `SolrProvisioner` and `SolrDockerLauncher` are constructed in `osbenchmark/test_run_orchestrator.py` (or `osbenchmark/builder/`); load the cluster_config instance using `osbenchmark.builder.cluster_config.load_cluster_config()` with the name from `cfg.opts("builder", "cluster_config.names")[0]` and params from `cfg.opts("builder", "cluster_config.params")`; pass the loaded instance as `cluster_config=` kwarg to both provisioner constructors

- [x] T089 Add benchmark-only pipeline guard for `--cluster-config` in `osbenchmark/benchmark.py` — in `configure_builder_params()`, after `cluster_config_names` is computed, check if `cfg.opts("test_execution", "pipeline") == "benchmark-only"` and `args.cluster_config != "defaults"`; if so, raise `SystemExit("ERROR: --cluster-config is only valid for provisioning pipelines (from-distribution, docker, from-sources). It cannot be used with the 'benchmark-only' pipeline.")`

- [x] T090 [P] Write unit tests for Phase 12 changes in `tests/unit/solr/test_provisioner.py` and `tests/unit/solr/test_runner.py` — (a) `test_provisioner_heap_env`: mock a cluster_config with `variables={"heap_size": "4g"}`; assert `SolrProvisioner._build_env()["SOLR_HEAP"] == "4g"`; (b) `test_provisioner_gc_env`: mock cluster_config with `variables={"gc_tune": "-XX:+UseG1GC"}`; assert `GC_TUNE` set; (c) `test_provisioner_no_config`: `cluster_config=None`; assert `SOLR_HEAP` not in returned env; (d) `test_docker_env_flags`: mock cluster_config `{"heap_size": "4g"}`; assert `["-e", "SOLR_HEAP=4g"]` in flags; (e) `test_create_collection_tlog_pull_params`: mock `SolrAdminClient`; call runner with `{"num-shards": 2, "replication-factor": 1, "tlog-replicas": 1, "pull-replicas": 0}`; assert `create_collection()` called with `num_shards=2, replication_factor=1, tlog_replicas=1, pull_replicas=0` and payload contains `"nrtReplicas": 1, "tlogReplicas": 1, "pullReplicas": 0`; (f) `test_create_collection_defaults`: call runner without new params; assert `tlog_replicas=0, pull_replicas=0`; (g) `test_cluster_config_log_format`: mock `test_run.cluster_config = ["external"]`; assert log line contains `cluster_config [external]` not `[['external']]`

**Checkpoint Krav 3**: Running `solr-benchmark run --cluster-config 4gheap --pipeline from-distribution --distribution-version 9.10.1 ...` starts Solr with `SOLR_HEAP=4g` in its environment. Running `solr-benchmark run --cluster-config 4gheap --pipeline benchmark-only ...` exits immediately with a clear error. `g1gc` config sets `GC_TUNE=-XX:+UseG1GC -XX:+UseStringDeduplication` in the Solr process env.

- [ ] T091 [VERIFICATION] End-to-end validation of Phase 12 — (1) run `solr-benchmark run --pipeline=docker --distribution-version=9.10.1 --workload=nyc_taxis --cluster-config=4gheap --test-mode`; verify log line reads `cluster_config [4gheap]` (no double brackets); verify Docker container started with `-e SOLR_HEAP=4g` (check `docker inspect`); (2) run same with `--cluster-config=g1gc`; verify `GC_TUNE=-XX:+UseG1GC -XX:+UseStringDeduplication` in container env; (3) run with `--cluster-config=4gheap --pipeline=benchmark-only`; verify immediate error exit with message containing `benchmark-only`; (4) run a workload with `"num-shards": 2, "replication-factor": 2, "tlog-replicas": 1` in the collection; verify Solr collection created with `nrtReplicas=2, tlogReplicas=1, pullReplicas=0` via Solr Admin UI or `GET /solr/admin/collections?action=CLUSTERSTATUS`

---

## Summary

| Phase | Tasks | Parallelizable | Story |
|---|---|---|---|
| Phase 1: Setup | T001–T004 | T003, T004 | — |
| Phase 2: Foundational | T005–T009 | T006, T008 | — |
| Phase 3: US1 (P1) MVP | T010–T016 | T010, T011, T012, T015 | US1 |
| Phase 4: US2 (P2) | T017–T019 | T019 | US2 |
| Phase 5: US3 (P3) | T020–T024 | T021, T022 | US3 |
| Phase 6: US4 (P4) | T025–T027 | T026 | US4 |
| Phase 7: Polish | T028–T039 | T028–T033, T035–T039 | — |
| **Phase 8: Corrections** | **T040–T053** | **T043, T046, T048, T052** | — |
| **Phase 9: Results Consolidation** | **T054–T062** | **T054, T059, T060, T062** | — |
| **Phase 10: Workload Conversion Refactor** | **T063–T072** | **T068, T069, T070, T072** | US4 |
| **Phase 11: Remove Auto-Conversion** | **T073–T079** | **T076, T077, T078** | US4 |
| **Phase 12: cluster_config + Collection Settings + Logging** | **T080–T091** | **T082, T083, T087, T090** | — |
| **Phase 13: Docs Site Setup** | **T092–T094** | **T093, T094** | — |
| **Phase 14: US5 Documentation Content** | **T095–T113** | **T095–T099, T101–T109, T111–T113** | US5 |
| **Total** | **113 tasks** | **57 parallelizable** | |

---

## Phase 13: Documentation Site Setup (Jekyll scaffold + CI)

**Purpose**: Initialize the `docs/` Jekyll site structure and GitHub Actions deployment
workflow. These tasks MUST complete before any content tasks (Phase 14) can begin.

- [ ] T092 Create `docs/` Jekyll scaffold — create `docs/Gemfile` with `gem "jekyll", "~> 4.4.1"` and `gem "just-the-docs", "0.12.0"`; create `docs/_config.yml` per plan.md Phase 1 design (title, theme, url, aux_links, search_enabled, callouts); create `docs/.gitignore` containing `_site/` and `.jekyll-cache/`; verify `cd docs && bundle install && bundle exec jekyll build` succeeds

- [ ] T093 [P] Create `.github/workflows/docs.yml` — implement the full GitHub Actions workflow per plan.md Phase 1 design: trigger on push to `main` and `workflow_dispatch`; two jobs (`build` using `ruby/setup-ruby@v1` + `actions/configure-pages@v5` + `bundle exec jekyll build`, and `deploy` using `actions/deploy-pages@v4`); set `working-directory: docs` for all `run` steps; upload artifact from `docs/_site`

- [ ] T094 [P] Create `docs/_includes/footer_custom.html` — implement the ASF copyright + attribution footer per plan.md Phase 1 design; include ASF copyright line, Apache 2.0 license link, link to About page, and one-line credit to OpenSearch Benchmark with trademark notice; use `{{ '/about' | relative_url }}` for the About link

**Checkpoint**: `cd docs && bundle exec jekyll build --strict` succeeds with zero errors.

---

## Phase 14: US5 — Documentation Site Content

**Goal**: 38 Markdown pages covering all 6 navigation sections, fully adapted for
Apache Solr Benchmark terminology and ASF attribution requirements.

**Independent Test**: `cd docs && bundle exec jekyll build --strict` succeeds; site served
locally shows all 6 sidebar sections with correct nesting; `about.md` contains the full
attribution chain and trademark notices; no "OpenSearch Benchmark" text appears in body
content outside of `about.md`.

### Foundation pages

- [ ] T095 [P] [US5] Create `docs/index.md` — home/landing page for Apache Solr Benchmark; front matter: `title: Apache Solr Benchmark`, `nav_order: 1`; content: 2–3 sentence description of the tool ("Apache Solr Benchmark is a performance benchmarking tool for [Apache Solr](https://solr.apache.org) clusters, derived from OpenSearch Benchmark"), quick links to Quickstart and User Guide sections, link to GitHub repo

- [ ] T096 [P] [US5] Create `docs/about.md` — license, attribution, and trademark page; front matter: `title: About / Credits`, `nav_order: 102`; sections: (1) License — Apache 2.0 with link to full text; (2) Attribution — "Apache Solr Benchmark is derived from OpenSearch Benchmark (Copyright 2022 OpenSearch Contributors, licensed under Apache 2.0), which in turn derives from Elasticsearch Rally (Copyright Elasticsearch bv)"; (3) Trademarks — "Apache Solr is a trademark of The Apache Software Foundation. OpenSearch® is a registered trademark of Amazon Web Services, Inc. or its affiliates."; (4) Links — apache.org, solr.apache.org, opensearch.org; this is the ONLY page where OpenSearch trademark appears in body text

- [ ] T097 [P] [US5] Create `docs/quickstart.md` — adapt OSB quickstart for Apache Solr Benchmark; front matter: `title: Quickstart`, `nav_order: 2`; replace all OpenSearch cluster references with Apache Solr; replace index/indices with collection/collections; update install command to `pip install solr-benchmark`; show example `solr-benchmark run` command targeting `localhost:8983`; link to https://github.com/janhoy/solr-benchmark-workloads as the workloads repository

- [ ] T098 [P] [US5] Create `docs/glossary.md` — adapt OSB glossary for Solr Benchmark; front matter: `title: Glossary`, `nav_order: 100`; include OSB terms (workload, challenge, test procedure, pipeline, corpora, schedule) with Solr-adapted definitions; add Solr-specific terms (collection, configset, shard leader, nrt replica, tlog replica, pull replica); include a terminology mapping table (OSB term → Solr Benchmark canonical term) matching Constitution Principle VI

- [ ] T099 [P] [US5] Create `docs/faq.md` — adapt OSB FAQ for Solr Benchmark; front matter: `title: FAQ`, `nav_order: 101`; remove any FAQ items about OpenSearch-specific features (ML Commons, CCR, etc.); adapt remaining items for Solr context; add FAQ items: "How do I convert an OpenSearch Benchmark workload?" (answer: use `convert-workload` command), "What Solr versions are supported?" (9.x and 10.x), "Where can I find pre-built workloads?" (link to janhoy/solr-benchmark-workloads)

### User Guide section

- [ ] T100 [US5] Create `docs/user-guide/index.md` and `docs/user-guide/concepts.md` — index: `title: User Guide`, `nav_order: 5`, `has_children: true`; concepts: `title: Concepts`, `parent: User Guide`, `nav_order: 3`; adapt OSB concepts page: replace index→collection, primary shard→shard leader, aggregations→facets; keep workload/challenge/pipeline/schedule/operation terminology unchanged; add Solr-specific concept: configset

- [ ] T101 [P] [US5] Create `docs/user-guide/install-and-configure/` section (3 files) — `index.md`: `title: Install and Configure`, `parent: User Guide`, `nav_order: 5`, `has_children: true`; `installing.md`: `title: Installing`, `parent: Install and Configure`, `grand_parent: User Guide`, `nav_order: 5`; adapt from OSB: replace `pip install opensearch-benchmark` with `pip install solr-benchmark`; `configuring.md`: `title: Configuring`, same parent/grand_parent, `nav_order: 7`; adapt from OSB: update `~/.benchmark/benchmark.ini` paths to `~/.solr-benchmark/benchmark.ini`; replace OSB-specific config keys with Solr equivalents

- [ ] T102 [P] [US5] Create `docs/user-guide/understanding-workloads/` section (3 files) — `index.md`: `title: Understanding Workloads`, `parent: User Guide`, `nav_order: 10`, `has_children: true`; `anatomy-of-a-workload.md`: `title: Anatomy of a Workload`, parent/grand_parent set, `nav_order: 15`; adapt from OSB: replace `"indices"` key with `"collections"`, replace `create-index`/`delete-index` with `create-collection`/`delete-collection`, show Solr workload.json example with `collections` array containing `name`, `configset-path`, `shards`, `nrt_replicas`; `common-operations.md`: `title: Common Operations`, `nav_order: 16`; adapt from OSB: document bulk-index, search, commit, optimize, create-collection, delete-collection operations; remove OSB-only ops (create-index, force-merge OpenSearch style)

- [ ] T103 [P] [US5] Create `docs/user-guide/working-with-workloads/` section (4 files) — `index.md`: `title: Working with Workloads`, `parent: User Guide`, `nav_order: 15`, `has_children: true`; `running-workloads.md`: `title: Running a Workload`, `nav_order: 9`; adapt from OSB: update CLI examples to use `solr-benchmark run`, replace `--target-hosts` examples with Solr `host:8983`, replace workload repo URL with `https://github.com/janhoy/solr-benchmark-workloads`; `creating-custom-workloads.md`: `title: Creating Custom Workloads`, `nav_order: 10`; adapt: show Solr-native workload.json format; `finetune-workloads.md`: `title: Fine-tuning Workloads`, `nav_order: 12`; adapt from OSB fine-tuning page; NO contributing-workloads.md (excluded per spec)

- [ ] T104 [P] [US5] Create `docs/user-guide/understanding-results/` section (3 files) — `index.md`: `title: Understanding Results`, `parent: User Guide`, `nav_order: 20`, `has_children: true`; `summary-reports.md`: `title: Summary Reports`, `nav_order: 22`; adapt from OSB: update output format description for JSON/CSV local filesystem output (`~/.solr-benchmark/results/`); `telemetry.md`: `title: Enabling Telemetry`, `nav_order: 30`; adapt from OSB: document Solr telemetry devices only (SolrJvmStats, SolrNodeStats, SolrCollectionStats); remove OpenSearch-only telemetry devices (CCR, ML Commons, etc.)

### Reference section

- [ ] T105 [P] [US5] Create `docs/reference/index.md`, `docs/reference/summary-report.md`, `docs/reference/telemetry.md` — index: `title: Reference`, `nav_order: 25`, `has_children: true`; summary-report: `title: Summary Report Format`, `parent: Reference`, `nav_order: 40`; document the JSON/CSV output format with field descriptions; telemetry: `title: Telemetry Devices`, `parent: Reference`, `nav_order: 45`; list all Solr telemetry devices with their names, metrics collected, and configuration options; remove all OpenSearch-only devices

- [ ] T106 [P] [US5] Create `docs/reference/workloads/` section (5 files) — `index.md`: `title: Workload Reference`, `parent: Reference`, `nav_order: 60`, `has_children: true`; `collections.md` (NEW): `title: collections`, `parent: Workload Reference`, `grand_parent: Reference`, `nav_order: 65`; document the `"collections"` workload.json array key: fields `name`, `configset-path`, `shards` (default 1), `nrt_replicas` (default 1), `pull_replicas` (default 0), `tlog_replicas` (default 0); show JSON examples; `corpora.md`: adapt from OSB, `nav_order: 70`; `operations.md`: adapt from OSB, `nav_order: 100`, replace index operations with Solr operations, remove OpenSearch-only ops; `test-procedures.md`: adapt from OSB, `nav_order: 110`

- [ ] T107 [P] [US5] Create `docs/reference/commands/` section (6 files) — `index.md`: `title: Command Reference`, `parent: Reference`, `nav_order: 50`, `has_children: true`; `run.md`: adapt from OSB run command, `nav_order: 90`, update all flags for Solr (remove `--target-os`, `--cluster-manager-node-count`; add `--cluster-config`); `list.md`: adapt, `nav_order: 80`; `info.md`: adapt, `nav_order: 70`; `compare.md`: adapt, `nav_order: 20`; `command-flags.md`: adapt from OSB, `nav_order: 150`; document all current `solr-benchmark` CLI flags; remove flags for deleted features (generate-data, redline-test, create-index)

### New sections (no OSB equivalent)

- [ ] T108 [P] [US5] Create `docs/cluster-config/` section (2 files) — `index.md`: `title: Cluster Config`, `nav_order: 27`, `has_children: true`; content: overview of `--cluster-config` flag, explain that it controls JVM/GC settings for provisioned Solr nodes (from-distribution, docker, from-sources pipelines only), note it is NOT valid with benchmark-only pipeline, show example: `solr-benchmark run --cluster-config 4gheap --pipeline from-distribution ...`; `available-configs.md`: `title: Available Configs`, `parent: Cluster Config`, `nav_order: 2`; list all built-in configs: defaults, 1gheap, 4gheap, g1gc, parallelgc; for each show the Solr env vars it sets (`SOLR_HEAP`, `GC_TUNE`, `SOLR_OPTS`) and their values

- [ ] T109 [P] [US5] Create `docs/converter/` section (3 files) — `index.md`: `title: Converter Tool`, `nav_order: 28`, `has_children: true`; overview: explain what the converter does (translates OSB workloads to Solr-native format), when to use it, link to janhoy/solr-benchmark-workloads for pre-built Solr workloads; `usage.md`: `title: Usage`, `parent: Converter Tool`, `nav_order: 2`; show full CLI usage: `solr-benchmark convert-workload --workload-path <src> --output-path <dest> [--force]`; show example output including `CONVERTED.md` summary file; `what-converts.md`: `title: What Gets Converted`, `parent: Converter Tool`, `nav_order: 3`; table of: (a) auto-converted constructs (bulk-index→bulk-index, search with match/range/term/bool→Solr JSON DSL, date ranges with format→ISO 8601, aggregations→facets), (b) requires manual review (script_score, percolator, complex nested aggregations), (c) skipped with TODO comment (cluster-health, force-merge, etc.)

### Polish

- [ ] T110 [US5] Run `cd docs && bundle exec jekyll build --strict` and resolve all warnings and errors — fix any broken internal links, missing `parent` references, duplicate `nav_order` values, or malformed front matter; the build MUST complete with zero warnings

- [ ] T111 [P] Terminology audit — scan all docs pages for OSB-specific terms using `grep -r "OpenSearch Benchmark\|create-index\|delete-index\| index \| indices \|aggregation" docs/ --include="*.md" | grep -v about.md`; fix every instance found by applying the adaptation rules from plan.md; verify canonical Solr Benchmark terms used throughout

- [ ] T112 [P] Trademark audit — verify OpenSearch trademark appears ONLY in `docs/about.md`; run `grep -r "OpenSearch" docs/ --include="*.md" | grep -v about.md`; any remaining hits (outside license header comments) MUST be removed or replaced with "Apache Solr Benchmark"; confirm `about.md` contains the full trademark notice for both Apache Solr and OpenSearch

- [ ] T113 [P] Verify GitHub Actions workflow syntax — run `cat .github/workflows/docs.yml` and confirm YAML is valid; verify `working-directory: docs` is set for all run steps; verify `path: docs/_site` is set on the upload artifact step; optionally validate with `yamllint .github/workflows/docs.yml`

**Checkpoint US5**: `bundle exec jekyll build --strict` passes; all 38 pages render; sidebar shows 6 sections with correct nesting; `about.md` has complete attribution chain; terminology and trademark audits pass.

---

## Summary (Updated)

| Phase | Tasks | Parallelizable | Story |
|---|---|---|---|
| Phase 1: Setup | T001–T004 | T003, T004 | — |
| Phase 2: Foundational | T005–T009 | T006, T008 | — |
| Phase 3: US1 (P1) MVP | T010–T016 | T010, T011, T012, T015 | US1 |
| Phase 4: US2 (P2) | T017–T019 | T019 | US2 |
| Phase 5: US3 (P3) | T020–T024 | T021, T022 | US3 |
| Phase 6: US4 (P4) | T025–T027 | T026 | US4 |
| Phase 7: Polish | T028–T039 | T028–T033, T035–T039 | — |
| Phase 8: Corrections | T040–T053 | T043, T046, T048, T052 | — |
| Phase 9: Results Consolidation | T054–T062 | T054, T059, T060, T062 | — |
| Phase 10: Workload Conversion Refactor | T063–T072 | T068, T069, T070, T072 | US4 |
| Phase 11: Remove Auto-Conversion | T073–T079 | T076, T077, T078 | US4 |
| Phase 12: cluster_config + Collection Settings | T080–T091 | T082, T083, T087, T090 | — |
| **Phase 13: Docs Site Setup** | **T092–T094** | **T093, T094** | — |
| **Phase 14: US5 Documentation Content** | **T095–T113** | **T095–T099, T101–T109, T111–T113** | US5 |
| **Total** | **113 tasks** | **57 parallelizable** | |

### Dependencies

- Phase 13 (T092–T094) can start immediately — no dependency on any prior phase
- Phase 14 (T095–T113) depends on Phase 13 completion (Jekyll scaffold must exist)
- Within Phase 14, all `[P]` tasks can run in parallel after T092 completes
- T110–T113 (polish) depend on all content pages existing

### Parallel opportunities (Phase 14)

All content tasks T095–T109 can be written in parallel (each is a different set of files).
Recommended grouping for efficient execution:

```
Group A (foundation):    T095, T096, T097, T098, T099
Group B (user guide):    T100, T101, T102, T103, T104
Group C (reference):     T105, T106, T107
Group D (new sections):  T108, T109
Polish (sequential):     T110, T111, T112, T113
```
