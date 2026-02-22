# Feature Specification: Solr Benchmark Fork

**Feature Branch**: `001-solr-benchmark-fork`
**Created**: 2026-02-18
**Status**: Draft
**Input**: User description: "Convert this project into a solr-benchmark fork. Make a good plan for how we can keep as much of the original code as possible, while developing functionality that makes this fork able to fetch, install, run, index and query Apache Solr 9.x instead. We'll also need to port various telemetry probes to query solr instead of opensearch."

## Clarifications

### Session 2026-02-18

- Q: Should workload file formats and dataset corpora be compatible with OpenSearch Benchmark so existing datasets can be imported? → A: Workload back-compat is NOT a goal. Workloads use Solr-native terminology throughout (collection, configset, etc.). A separate migration script will be provided to help port OSB workloads to the Solr format. Generic framework file formats (benchmark.ini, scheduling config) are preserved where there is no reason to change them.
- Q: Where do benchmark results get stored, given the metrics backend depended on OpenSearch? → A: File-based output — results written as JSON/CSV files on disk plus a console summary table. No external metrics store dependency.
- Q: How should the bulk-index runner translate OSB corpus documents (NDJSON bulk format) for Solr? → A: Transform at index time — strip OSB action lines, POST document content as a JSON array to Solr's `/update` endpoint. No pre-conversion of corpus files required.
- Q: Which Solr deployment mode must the `from-distribution` provisioning pipeline support? → A: Both standalone (user-managed) and cloud (embedded ZooKeeper) modes, selectable via a pipeline parameter. Solr 9.x defaults to user-managed mode (`--cloud` flag enables cloud mode); Solr 10.x defaults to cloud mode (`--user-managed` flag enables standalone). The provisioner must handle this version-dependent default correctly.
- Q: What authentication and transport security scope is required? → A: Plain HTTP without authentication is the default and assumed baseline (Solr does not ship with SSL or Basic Auth enabled out of the box). Basic Auth and TLS/SSL are optional and may be supported for completeness but are not required for initial benchmarking use cases.
- Q: What should the migration utility produce? → A: An annotated draft workload file — converts what it can automatically, and inserts `# TODO` comments for unsupported or ambiguous operations that require manual review. No silent omissions.
- Directive: Admin commands MUST use Solr's V2 API (available since Solr 8, stable in 9.x). The V2 API OpenAPI spec is published in Solr's download directory and should be used as the authoritative reference for endpoint shapes.
- Directive: The telemetry layer MUST support two metrics response formats: Solr 9.x uses a custom JSON format from the V2 metrics endpoint; Solr 10.x uses Prometheus exposition format from the same endpoint. The tool detects the active Solr version and parses accordingly.
- Directive: FR-027 revised — benchmark result output MUST use a pluggable result writer architecture. The local filesystem writer (JSON + CSV files) is the default implementation. The plugin interface must be designed so that additional writers (S3, Solr collection, database, etc.) can be added without modifying core code.
- Directive: ASF Licensing compliance — the fork is intended to be contributed as a subproject of the Apache Solr PMC. All licensing and attribution MUST comply with ASF policy: (1) the NOTICE file MUST list Apache Solr copyright at the top, followed by attribution to OpenSearch Contributors ("This product includes software developed by OpenSearch Contributors, Copyright 2022"); (2) per-file license headers MUST be updated per ASF source header policy (research https://www.apache.org/legal/src-headers.html for the correct approach to modified vs. retained headers); (3) the LICENSE file MUST reflect the fork's identity as an Apache-licensed project under the Solr PMC.

### Session 2026-02-22

- Q: How should OpenSearch workloads be handled at benchmark run time? → A: The tool MUST auto-detect the workload format at run start. If an OpenSearch Benchmark workload is detected, the tool converts it ONCE to a Solr-native workload on disk (written as `<name>-solr/` adjacent to the source), then runs the converted version. On subsequent runs, if `CONVERTED.md` exists in the output directory, conversion is skipped and the existing converted workload is used.
- Q: Where should OpenSearch-to-Solr query translation happen? → A: At workload conversion time only — NOT at query execution time. The search runner must execute Solr-native operations only. All OpenSearch DSL translation happens once during workload conversion.
- Q: What format should converted search operations use? → A: Solr JSON Query DSL (`body` dict with `"query"` as a Lucene string, `"filter"`, `"limit"`, `"sort"`, and `"facet"` keys). This is superior to flat params because it supports Solr JSON facets (translating OpenSearch aggregations) and nested bool queries in a maintainable format. The converted workload uses Mode 2 of the search runner (POST body to `/solr/{collection}/query`).
- Q: Should bridge runners that map OpenSearch operation types at runtime be kept? → A: No. All operation type mapping happens at workload conversion time. Bridge runner classes must be removed for a clean architecture.
- Q: What should happen to operations that cannot be converted to Solr format? → A: They MUST be skipped (omitted from the converted workload) with a WARN log message per skipped operation. A `CONVERTED.md` file MUST be written to the output directory listing all skipped operations with their reasons. Silent omission is not acceptable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Benchmarks Against Existing Solr Cluster (Priority: P1)

A performance engineer has an existing Apache Solr 9.x cluster and wants to run standard benchmarks against it to measure indexing throughput, query latency, and system resource usage.

**Why this priority**: This is the most common use case and delivers immediate value. It requires only the client layer, runners, and telemetry to work — no provisioning needed. It is the prerequisite for all other stories.

**Independent Test**: Can be fully tested by pointing the tool at a live Solr 9 instance and running a bulk indexing + search workload, verifying metrics are collected and a benchmark report is generated.

**Acceptance Scenarios**:

1. **Given** a running Solr 9.x cluster at a known host:port, **When** the user runs `solr-benchmark run --workload my-workload --target-hosts solr-host:8983`, **Then** the tool connects to Solr, indexes documents, runs search queries, and produces a benchmark report with throughput and latency metrics.
2. **Given** a Solr cluster running over plain HTTP with no authentication (the default out-of-the-box configuration), **When** the user runs a benchmark, **Then** the tool connects and operates without requiring any credentials or TLS configuration.
3. **Given** a Solr cluster, **When** telemetry collection is enabled, **Then** the tool gathers JVM stats, CPU/memory usage, and Solr-specific collection and node statistics during the benchmark run.
4. **Given** a benchmark has completed, **When** the user reviews the output, **Then** they see latency percentiles, throughput, and error rate metrics in the same report format as the original tool.

---

### User Story 2 - Download, Provision and Benchmark a Local Solr Instance (Priority: P2)

A developer wants to provision a fresh Solr 9.x node from an official release archive, have the tool configure and start it, run a benchmark, and tear it down — without needing to manually install Solr.

**Why this priority**: Enables fully automated, reproducible benchmarks from a clean state. Critical for CI/CD performance regression testing. Depends on Story 1 being complete.

**Independent Test**: Can be tested by running the tool on a machine without Solr installed, having it download the distribution, start a single-node cluster, execute a benchmark, and confirm the instance is cleaned up afterwards.

**Acceptance Scenarios**:

1. **Given** a machine with Java 11+ but no Solr installed, **When** the user runs with a `from-distribution` pipeline specifying a Solr 9.x version, **Then** the tool downloads the official Solr release, extracts it, configures it, starts it, runs the benchmark, and stops it.
2. **Given** a Solr distribution has been provisioned, **When** the tool starts the benchmark phase, **Then** it creates a Solr collection with a configurable configset before indexing begins.
3. **Given** the benchmark completes (success or failure), **When** the teardown phase runs, **Then** Solr is stopped and temporary files are cleaned up.
4. **Given** a Docker environment, **When** the user uses the Docker-based pipeline, **Then** the tool launches Solr 9 in a container, benchmarks it, and removes the container after completion.

---

### User Story 3 - Collect Solr-Specific Telemetry During Benchmarks (Priority: P3)

A Solr operator wants the benchmark tool to collect fine-grained Solr-specific performance metrics during runs — including collection statistics, segment info, query handler stats, and JVM garbage collection data — and include these in the benchmark report.

**Why this priority**: Without proper telemetry, users get only client-side throughput/latency data. Solr-side metrics are essential for diagnosing bottlenecks. Depends on Story 1.

**Independent Test**: Can be tested by running a benchmark with telemetry enabled and verifying that Solr-specific metrics (collection size, query handler stats, JVM heap) appear in the results alongside standard latency metrics.

**Acceptance Scenarios**:

1. **Given** telemetry is enabled, **When** a benchmark runs, **Then** the tool collects JVM heap usage, GC pause times, and thread counts from Solr's metrics API.
2. **Given** telemetry is enabled during indexing, **When** the benchmark completes, **Then** the report includes collection segment counts and index size growth recorded during the run.
3. **Given** a Solr cluster node, **When** node stats telemetry runs, **Then** the tool retrieves CPU usage, memory usage, and Solr query handler throughput/error counts from the admin API.
4. **Given** OpenSearch-only telemetry devices (CCR stats, ML model stats, Transform stats, async search stats, gRPC stats), **When** the tool starts, **Then** these devices are absent and produce no errors or warnings.

---

### User Story 4 - Define and Run Solr-Native Workloads (Priority: P4)

A benchmark author wants to define workloads using Solr-native concepts — collections, configsets, Solr query syntax, commits, and optimizes — in a workload file format designed specifically for this tool. A separate migration utility helps authors port existing OSB workload definitions to the Solr format.

**Why this priority**: Custom workloads allow the tool to be adapted for diverse benchmarking needs. Solr-native terminology reduces confusion for Solr practitioners. A migration utility lowers the barrier for teams coming from OSB. Depends on Stories 1 and 3.

**Independent Test**: Can be tested by authoring a minimal Solr workload JSON file with create-collection, bulk-index, search, and delete-collection operations, running it against a Solr cluster, and confirming all operations execute and report results.

**Acceptance Scenarios**:

1. **Given** a workload file with a `bulk-index` operation targeting a named collection, **When** run against Solr, **Then** documents are submitted to Solr's update endpoint and indexed into the target collection.
2. **Given** a workload file with a `search` operation using Solr query syntax, **When** run, **Then** queries are sent to the Solr select handler and latency is recorded.
3. **Given** a workload file with `create-collection` and `delete-collection` operations, **When** run, **Then** the collection is created before and deleted after the benchmark phase.
4. **Given** a workload file with a `commit` operation, **When** run, **Then** Solr performs a hard commit and the tool waits for acknowledgment before proceeding.
5. **Given** an OSB workload file, **When** the user runs the migration utility against it, **Then** the utility produces an annotated draft Solr workload file — compatible constructs translated automatically, unsupported operations present with `# TODO` comments — and no operations are silently omitted.
6. **Given** an OpenSearch Benchmark workload directory, **When** the user runs `solr-benchmark run --workload-path /path/to/os-workload`, **Then** the tool automatically detects the format, converts it to a Solr-native workload at `<name>-solr/` on disk, and runs the benchmark against the converted workload — no manual conversion step required.
7. **Given** an OpenSearch workload has been previously auto-converted (`CONVERTED.md` exists in `<name>-solr/`), **When** the user runs the benchmark again, **Then** no re-conversion occurs and the existing converted workload is used immediately.
8. **Given** an OpenSearch workload with aggregations, **When** auto-converted, **Then** the converted search operations contain a Solr JSON Query DSL `body` with `"facet"` definitions mapping the OpenSearch aggregations to Solr JSON facets — the benchmark executes real facet queries against Solr, not stub queries.
9. **Given** an OpenSearch workload containing operations with no Solr equivalent (e.g., `script_score` queries, `cluster-health`), **When** auto-converted, **Then** those operations are omitted from the converted workload with WARN log messages, and a `CONVERTED.md` file in the output directory lists every skipped operation with its reason.
10. **Given** the `convert-workload` CLI subcommand, **When** a user runs `solr-benchmark convert-workload --workload-path <src> --output-path <dest>`, **Then** the Solr-native converted workload is written to `<dest>`, a `CONVERTED.md` summary is included, and any skipped operations are printed to the console.

---

### Edge Cases

- What happens when the Solr admin API is unavailable but queries still work (partial cluster health)?
- How does the bulk-index runner handle NDJSON corpus records that contain OpenSearch-specific metadata fields (e.g., `_index`, `_type`) that Solr does not accept — are they silently stripped or flagged?
- How does the provisioner detect Solr version to determine the correct default mode flag (`--cloud` vs `--user-managed`)?
- What should happen if a V2 API endpoint returns a 404 (e.g., on an older Solr build where V2 support is incomplete) — should the tool fall back to V1 or fail with a clear error?
- What should happen if the tool detects Solr 9.x but receives a Prometheus-format response from the metrics endpoint (or vice versa for 10.x)?
- What if the target collection does not exist when a benchmark tries to index into it?
- How does bulk indexing behave if Solr returns partial errors in a batch update response?
- What happens if the provisioned Solr node takes longer than the configured timeout to start?
- What should happen if a Solr version other than 9.x is provisioned (e.g., 8.x or 10.x)?

## Requirements *(mandatory)*

### Functional Requirements

**Client and Connectivity:**
- **FR-001**: The tool MUST connect to Solr 9.x clusters over plain HTTP, replacing the OpenSearch Python client with a Solr-compatible HTTP client. Plain HTTP without authentication is the assumed default, matching Solr's out-of-the-box configuration.
- **FR-002**: The tool SHOULD support HTTP Basic Authentication and TLS/SSL connections for environments where Solr has been secured, but these are not required for the initial benchmarking use case.
- **FR-003**: The tool MUST remove all gRPC/protobuf operation support, as Solr has no gRPC interface.
- **FR-004**: The tool MUST use Solr's default port (8983) as the default when no port is specified.

**Provisioning:**
- **FR-006**: The tool MUST be able to download official Apache Solr 9.x release archives from the Apache distribution mirrors.
- **FR-007**: The tool MUST be able to unpack, configure, and start a Solr instance in either user-managed (standalone) or cloud (embedded ZooKeeper) mode, selectable via a pipeline parameter. For Solr 9.x, user-managed is the default and cloud mode is enabled via `--cloud`; for Solr 10.x, cloud is the default and user-managed is enabled via `--user-managed`. The provisioner MUST apply the correct flag based on the detected Solr version.
- **FR-008**: The tool MUST support launching Solr 9.x in a Docker container as part of a Docker-based pipeline, with the same user-managed/cloud mode selection as the local provisioner.
- **FR-009**: The tool MUST create a Solr collection before benchmarking begins when provisioning is managed by the tool. Collection creation is a two-step process: (1) upload the configset as a ZIP archive (`PUT /api/cluster/configs/{name}`) containing at minimum `conf/schema.xml` and `conf/solrconfig.xml`, then (2) create the collection referencing that configset name (`POST /api/collections`). The workload definition must specify the path to the configset directory; the tool builds the ZIP at setup time. The configset must be deleted as part of teardown.
- **FR-010**: The tool MUST stop and clean up any Solr instances it provisioned after the benchmark completes, whether it succeeded or failed.

**Workload Operations:**
- **FR-011**: The tool MUST support a `bulk-index` operation that reads corpus documents from NDJSON files (OSB format), strips action-line metadata at index time, and POSTs document content as JSON arrays to Solr's `/update` endpoint in configurable batch sizes.
- **FR-012**: The tool MUST support a `search` operation that sends queries to Solr's `/select` handler and measures latency and result count.
- **FR-013**: The tool MUST support a `commit` operation that triggers a hard or soft commit on a Solr collection.
- **FR-014**: The tool MUST support an `optimize` operation that triggers a Solr segment merge/optimize and waits for completion.
- **FR-015**: The tool MUST support `upload-configset`, `create-collection`, `delete-collection`, and `delete-configset` operations using the Solr V2 API. `create-collection` MUST be preceded by `upload-configset` (the two operations may be combined into a single `create-collection` runner that handles both steps internally when a configset path is provided).
- **FR-015a**: All admin operations (collection management, cluster status, node stats, telemetry queries) MUST use the Solr V2 API by default. The V2 API OpenAPI specification, published in Solr's download directory, is the authoritative reference for endpoint paths and request/response shapes. The legacy V1 API (`/solr/admin/...`) MUST NOT be used for newly implemented operations.
- **FR-016**: The tool MUST support a `raw-request` operation for arbitrary HTTP calls to any Solr endpoint, allowing users to target V2 or V1 paths explicitly.
- **FR-017**: The workload file format MUST use Solr-native terminology throughout: `collection` (not `index`), `configset` (not `mapping` or `template`), and Solr-specific operation names.
- **FR-018**: The tool MUST include a migration utility (Python script) that reads an OSB workload file and produces an annotated draft Solr-format workload. Compatible constructs are translated automatically; unsupported or ambiguous operations are retained with `# TODO` inline comments explaining what manual action is needed. The utility MUST NOT silently drop any operations.
- **FR-018a**: When loading a workload for benchmarking, the tool MUST automatically detect whether the workload is in OpenSearch Benchmark format (`"indices"` key present, uses `create-index`/`delete-index` operation types, etc.) or in Solr-native format (`"collections"` key present, uses Solr-native operations). Detection logic lives in `osbenchmark/solr/conversion/detector.py`.
- **FR-018b**: If an OpenSearch Benchmark workload is detected at run time, the tool MUST convert it to a Solr-native workload stored on disk at `<original-workload-name>-solr/` adjacent to the original directory, then run the converted version. If `CONVERTED.md` already exists in that directory, the tool MUST skip re-conversion and use the existing converted workload. The benchmark runs only against Solr-native workloads.
- **FR-018c**: The tool MUST provide a `convert-workload` CLI subcommand accepting `--workload-path <source-dir>` and optionally `--output-path <dest-dir>`. It converts the OpenSearch workload to Solr-native format, writes the result to the output directory, and reports any skipped operations to the console.
- **FR-018d**: During workload conversion, operations that have no Solr equivalent MUST be skipped (omitted from the output) with a WARN-level log message stating the operation name and reason. A `CONVERTED.md` file MUST be written to the output directory recording: the source workload path, conversion timestamp, and a list of all skipped operations with their reasons.
- **FR-018e**: Converted search operations MUST use Solr JSON Query DSL format (a `"body"` dict with `"query"` as a Lucene string, `"filter"` list, `"limit"`, `"sort"`, and `"facet"` keys). OpenSearch aggregations MUST be translated to Solr JSON facets where possible (terms → terms facet, date_histogram → range facet, stats → stat facets). The converted body is POSTed to `/solr/{collection}/query`. This is superior to flat query params because it preserves facet semantics and supports nested bool queries.
- **FR-018f**: The search runner MUST NOT perform any OpenSearch DSL translation at query execution time. All translation happens at workload conversion time (pre-run). The runner accepts only: (a) no body — classic Solr params (`q`, `fq`, `sort`, `rows`), or (b) a body with a `"query"` key whose value is a string — Solr JSON Query DSL POSTed to `/query`. If `body["query"]` is a dict (OpenSearch DSL), the runner MUST log a warning that the workload was not pre-converted; it does NOT attempt translation.
- **FR-018g**: The bridge runner classes that mapped OpenSearch operation types at runtime (`SolrCreateIndexBridge`, `SolrBulkBridge`, `SolrDeleteIndexBridge`) MUST be removed. All operation type mapping (`create-index`→`create-collection`, `bulk`→`bulk-index`, etc.) happens exclusively at workload conversion time.

**Telemetry:**
- **FR-019**: The tool MUST collect JVM metrics (heap usage, GC pause times, thread counts), collection statistics (document count, index size, segment count), node-level system metrics (CPU, memory, disk), and query handler statistics (request count, error count, average response time) from Solr nodes via the V2 metrics API during benchmarks.
- **FR-019a**: The telemetry layer MUST support two response formats for the V2 metrics endpoint, selected automatically based on detected Solr version:
  - **Solr 9.x**: custom JSON format returned by the V2 metrics API.
  - **Solr 10.x+**: Prometheus exposition format (text-based) returned by the same endpoint.
  The tool MUST parse whichever format the connected Solr version returns and map the result to the same internal metric names regardless of source format.
- **FR-023**: The tool MUST NOT include telemetry devices for OpenSearch-only features (CCR replication, Transform, Searchable Snapshots, ML Commons, Segment Replication plugin stats).

**ASF Licensing and Attribution:**
- **FR-028**: The NOTICE file MUST be updated to place "Apache Solr Benchmark / Copyright [YEAR] The Apache Solr project" at the top, followed by the full attribution chain — retaining all existing attributions in order: OpenSearch Contributors (Copyright 2022), and Elasticsearch bv (Rally source code). No existing attribution may be removed.
- **FR-029**: All source file license headers MUST be reviewed and updated in compliance with ASF source header policy (https://www.apache.org/legal/src-headers.html). Files substantially retained from the original codebase MUST carry appropriate attribution; files substantially rewritten for this fork MUST carry the Apache Solr project header.
- **FR-030**: The LICENSE file MUST reflect the fork's Apache 2.0 licensing under the Apache Solr PMC. No incompatible license dependencies may be introduced.
- **FR-031**: A legal review checklist MUST be produced as part of the fork, documenting how each ASF licensing requirement has been addressed, to support eventual contribution to the Solr PMC.

**Naming and Identity:**
- **FR-024**: The tool MUST rename its CLI entry points, top-level package, and all branding to reflect Solr (e.g., `solr-benchmark` / `solr-benchmarkd`). No OpenSearch branding should remain in user-facing output.
- **FR-025**: The actor-based distributed execution model, scheduling engine, and metrics aggregation/reporting pipeline MUST be retained as the core framework, since these are not search-engine-specific.
- **FR-026**: Generic framework configuration files (benchmark.ini structure, tox.ini, test runner config) MUST be preserved unless there is a concrete functional reason to change them.
- **FR-027**: Benchmark result output MUST use a pluggable result writer architecture. The tool MUST ship with a local filesystem writer as the default implementation, which writes results to a timestamped directory and prints a summary table to the console. The result writer interface MUST be defined so that additional writers (e.g., S3, Solr collection, relational database) can be implemented and registered without modifying core tool code. The active writer MUST be selectable via configuration.
- **FR-027a**: The local filesystem result writer MUST create a timestamped results directory under the configured results path (e.g., `~/.solr-benchmark/results/YYYYMMDD_HHMMSS_<run-id-prefix>/`) containing:
  - **test_run.json**: Complete benchmark run metadata and detailed results (copied from the test-runs store). This file already contains all metadata needed for time-series analysis: run_id, timestamp, pipeline, user-tags, workload, test_procedure, cluster configuration, distribution version, and full operation metrics.
  - **results.csv**: Flattened CSV export of key metrics (throughput, latency, error rate) for spreadsheet analysis.
  - **summary.txt**: Human-readable markdown table of key metrics (also printed to console).

  **Rationale**: The tool already creates a complete `test_run.json` file in `~/.solr-benchmark/benchmarks/test-runs/<run-id>/` that contains comprehensive metadata (benchmark version, environment, pipeline, user-tags, cluster config, results). Rather than inventing a new result format, the result writer MUST copy or symlink this file into the timestamped results directory. This ensures users have a single, complete record of each benchmark run without format duplication or metadata drift.
- **FR-027b**: Cluster configuration specification MUST be recorded in the test_run.json file before it is stored or copied to results. This includes not only the cluster-config name (e.g., "4gheap") but the complete configuration specification: all variables (heap_size, GC settings, etc.), template paths, and effective configuration values used for the benchmark run. This metadata is critical for time-series analysis and result comparison, enabling users to:
  - Compare performance across different cluster configurations (e.g., 4GB heap vs 8GB heap)
  - Correlate configuration changes with performance changes
  - Filter and group results by configuration in a results portal/dashboard
  - Reproduce benchmark runs with identical cluster settings

### Key Entities

- **Solr Collection**: The primary data container in Solr. Has a name, configset, shard/replica topology, and is the target of all indexing and query operations.
- **Configset**: A reusable Solr configuration bundle (solrconfig.xml + schema.xml) referenced when creating a collection. Required for collection creation during provisioning.
- **Solr Node**: A running Solr process in standalone or SolrCloud mode. Exposes the admin API for health checks, metrics retrieval, and management operations.
- **Workload**: A Solr-native benchmark definition describing operations (bulk-index, search, commit, etc.), their parameters, scheduling, and challenges. Not back-compatible with OSB workloads; use the migration utility to convert.
- **Telemetry Device**: A probe that periodically queries Solr admin APIs during a benchmark run and records named metrics into the time-series results store.
- **Benchmark Runner**: A component mapping a workload operation definition to a Solr HTTP API call, measuring its execution time and outcome.
- **Migration Utility**: A Python script that reads an OSB workload file and produces an annotated draft Solr-format workload. Compatible constructs are translated automatically; unsupported or ambiguous operations are kept with `# TODO` inline comments indicating required manual action. No operations are silently dropped.
- **Result Writer**: A pluggable output component that receives completed benchmark results and persists them to a destination. The tool ships with a local filesystem writer (default). Additional writers (S3, Solr collection, database) can be implemented against the defined interface and selected via configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can benchmark a Solr 9.x cluster using Solr-native terminology throughout (collections, configsets, commit, optimize) — no OpenSearch concepts appear in user-facing commands, workload files, or output.
- **SC-002**: The `from-distribution` pipeline completes a full provision → collection create → benchmark → teardown cycle for Solr 9.x without manual intervention.
- **SC-003**: At least 75% of the original source code (by line count) is retained in the fork — either unchanged (generic framework code) or with Solr-specific adaptations — rather than being rewritten from scratch.
- **SC-004**: All ported Solr telemetry devices produce populated metrics in the benchmark report alongside standard throughput and latency measurements.
- **SC-005**: The tool correctly handles bulk indexing partial errors from Solr (non-200 responses or error fields in the update response) and records them as error metrics rather than crashing.
- **SC-006**: All existing unit tests covering the generic framework (actor system, scheduling, metrics aggregation, report generation) continue to pass without modification.
- **SC-007**: A complete Solr workload cycle (create collection → bulk index 10k docs → run 100 searches → delete collection) can be executed end-to-end in a single benchmark run.
- **SC-008**: The migration utility produces an annotated draft Solr workload from any OSB workload file — structural and scheduling constructs are translated automatically, and every unsupported operation appears in the output with a `# TODO` comment. No operations are silently dropped.
- **SC-009**: The fork's NOTICE file, LICENSE file, and per-file source headers comply with ASF policy, as confirmed by a completed legal review checklist. The NOTICE file correctly attributes both Apache Solr and OpenSearch Contributors.

## Architecture Clarification: Pure Solr Tool (Not Dual-Mode)

**CRITICAL**: This is a pure Solr benchmarking tool, NOT a dual-mode tool that supports both OpenSearch and Solr.

### What This Means

**95% of code = Solr-only**:
- The tool **ONLY** connects to, provisions, and benchmarks Apache Solr clusters
- No runtime mode parameter, no conditional logic (`if mode == "solr"`), no shim classes
- Client layer is pure Solr (pysolr + requests for admin API)
- Runners execute Solr operations only
- Telemetry collects Solr metrics only
- Provisioner downloads/starts/stops Solr only
- Result writers store Solr benchmark results only

**5% of code = OpenSearch compatibility (workload conversion ONLY)**:
- `osbenchmark/solr/conversion/` — workload detection, query DSL → Solr JSON DSL translation, aggregations → Solr facets, schema mapping. Called at workload conversion time, never at runner execution time.
- `osbenchmark/tools/migrate_workload.py` — standalone CLI migration utility for manual conversion
- NDJSON bulk format translation in `SolrBulkIndex` — strips action-line metadata, translates doc field formats (dates, geo-points) at index time (data is too large to pre-convert)
- `osbenchmark/test_run_orchestrator.py` — invokes conversion module once at run start if OpenSearch workload detected; then runs the converted Solr workload

**The key principle**: Runners execute **Solr-native operations only**. The conversion module is a pre-processing layer, not a runtime translation layer. After conversion, the tool is operating entirely in Solr-native mode.

**What must NOT exist**:
- No `mode` parameter anywhere in configuration, client, runners, or provisioners
- No OpenSearch client connections (opensearchpy fully removed)
- No OpenSearch metrics store backend
- No OpenSearch-specific pipelines (`opensearch-from-distribution`, etc.)
- No conditional logic switching between OpenSearch and Solr code paths
- No shim/bridge classes that wrap one client to look like another
- No runtime OpenSearch DSL translation in the search runner (Mode 3 is removed)

### Architectural Intent

This fork **replaces** the OpenSearch-specific code in the OSB framework with Solr-specific code. The generic actor-based execution framework, scheduling engine, and metrics aggregation are retained because they are search-engine-agnostic. But the client layer, runners, telemetry, and provisioning are 100% Solr-native.

Users coming from OSB can convert their workloads using the migration utility, but the tool itself does not connect to or benchmark OpenSearch clusters at runtime.

## Assumptions

- This is a standalone fork intended for contribution as a subproject of the Apache Solr PMC. The tool will no longer support or benchmark OpenSearch clusters; all OpenSearch-specific execution code is replaced.
- The fork inherits the Apache 2.0 license from the original codebase. ASF licensing and attribution rules apply: NOTICE and LICENSE files must be updated, and per-file headers must comply with ASF source header policy before any PMC contribution.
- Workload back-compatibility with OSB is NOT a goal. Workloads use Solr-native terminology and structure. A migration utility is provided to assist porting existing OSB workloads.
- Generic framework configuration formats (benchmark.ini structure, scheduling/test runner config) are preserved where there is no functional reason to change them.
- Apache Solr 9.x is the primary target. Solr 10.x is a supported secondary target, required because of its different deployment mode defaults and Prometheus-format metrics endpoint; Solr 8.x is out of scope.
- Both user-managed (standalone) and cloud (embedded ZooKeeper) deployment modes are supported and selectable. The provisioner handles the version-dependent flag difference automatically: Solr 9.x uses `--cloud` to enable cloud mode; Solr 10.x uses `--user-managed` to enable standalone mode.
- Solr collection schemas will be supplied as pre-existing configsets; automatic schema inference or generation from data is out of scope.
- The OpenSearch Python client is fully replaced with a Solr-compatible HTTP client.
- The metrics storage backend previously used an embedded OpenSearch instance. In this fork it is replaced with a pluggable result writer, defaulting to local filesystem output (JSON + CSV files, console summary). No external store dependency is required out of the box; additional writers can be added via the plugin interface.
- JVM-level telemetry (GC logs, JFR flight recorder, heap dumps) continues to work unchanged since Solr is also a Java application.
