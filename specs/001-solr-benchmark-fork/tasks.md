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

- [ ] T028 [P] Update `NOTICE` — place `Apache Solr Benchmark\nCopyright [YEAR] The Apache Solr project` at top; retain existing attribution chain verbatim: OpenSearch Contributors (Copyright 2022), Elasticsearch/Rally
- [ ] T029 [P] Update `LICENSE` — reflect Apache Solr PMC identity in preamble; retain full Apache 2.0 license text unchanged
- [ ] T030 Audit all per-file license headers using a scan script — apply Category A/B/C rules from `research.md`: retain OpenSearch header on unchanged files, add Solr attribution line on substantially modified files, use full ASF header on new files; produce `specs/001-solr-benchmark-fork/checklists/legal-review.md` checklist (FR-031)
- [ ] T031 Remove remaining OpenSearch branding from all user-facing console output, error messages, log messages, and workload example files
- [ ] T032 [P] Update `README.md` for Solr context — project name, purpose, quickstart commands, links to Solr docs
- [ ] T033 [P] Update `DEVELOPER_GUIDE.md` and `CONTRIBUTING.md` — replace OpenSearch-specific instructions with Solr equivalents; reference `specs/001-solr-benchmark-fork/quickstart.md`
- [ ] T034 Verify all generic framework unit tests in `tests/unit/` pass without modification (SC-006) — run `make test` and fix any import errors caused by deleted modules
- [ ] T035 [P] Write unit tests for `osbenchmark/solr/client.py` in `tests/unit/solr/test_client.py` — mock `requests.Session`; cover `get_version()`, `upload_configset()`, `create_collection()`, `delete_collection()`, `get_node_metrics()` (both JSON and Prometheus format), error cases
- [ ] T036 [P] Write unit tests for `osbenchmark/solr/runner.py` in `tests/unit/solr/test_runner.py` — mock `pysolr.Solr` and `SolrAdminClient`; cover `bulk_index` NDJSON translation (assert `_id`→`"id"`, `_type` dropped, `_index` not in document), both `search` modes, two-step `create_collection` sequence
- [ ] T037 [P] Write unit tests for `osbenchmark/solr/result_writer.py` in `tests/unit/solr/test_result_writer.py` — cover `LocalFilesystemResultWriter` lifecycle, output file creation, `WRITER_REGISTRY`, unknown writer error
- [ ] T038 [P] Write unit tests for `osbenchmark/solr/telemetry.py` in `tests/unit/solr/test_telemetry.py` — cover `SolrJvmStats` parsing both 9.x JSON and 10.x Prometheus responses; cover `SolrNodeStats` and `SolrCollectionStats` metric extraction
- [ ] T039 [P] Write unit tests for `osbenchmark/tools/migrate_workload.py` in `tests/unit/solr/test_migrate_workload.py` — cover translation of each supported operation type, presence of `# TODO` for unsupported ops, no silent drops

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
| **Total** | **39 tasks** | **22 parallelizable** | |
