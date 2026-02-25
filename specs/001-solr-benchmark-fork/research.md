# Research: Solr Benchmark Fork

**Feature**: 001-solr-benchmark-fork
**Date**: 2026-02-19
**Phase**: 0 — Unknowns resolved

---

## 1. Solr Client Strategy

### Decision
Use a **hybrid client approach**:
- **`pysolr`** (https://pypi.org/project/pysolr/) for standard data operations: indexing, search, commit, optimize, delete. pysolr handles the HTTP transport, response parsing, and error handling for these high-frequency operations.
- **Plain HTTP via `requests`** for admin/management operations not covered by pysolr: collection management, telemetry/metrics, version detection, cluster status. These use the Solr V2 API at base path `/api/`.

Workers run inside Thespian actor processes (one process per worker), so pysolr's synchronous `requests`-based transport is compatible — each process blocks independently without competing with an event loop.

### OpenAPI Reference
The V2 API OpenAPI spec is published in Solr's release tarball (see https://solr.apache.org/downloads.html). File is named `server/solr-openapi-*.json` inside the tarball. Use this as the authoritative source for endpoint shapes and request/response contracts during implementation.

### Operations Handled by pysolr

| Operation | pysolr call |
|---|---|
| Bulk index documents | `solr.add(docs, commit=False)` |
| Search/select query | `solr.search(q, **kwargs)` |
| Hard commit | `solr.commit()` |
| Soft commit | `solr.commit(softCommit=True)` |
| Optimize | `solr.optimize()` |
| Delete by query | `solr.delete(q=query)` |

### Operations via Plain HTTP (V2 API)

| Operation | V2 Path | Method |
|---|---|---|
| Upload configset | `/api/cluster/configs/{configset-name}` | PUT |
| Delete configset | `/api/cluster/configs/{configset-name}` | DELETE |
| List configsets | `/api/cluster/configs` | GET |
| Create collection | `/api/collections` | POST |
| Delete collection | `/api/collections/{name}` | DELETE |
| Cluster status | `/api/cluster` | GET |
| Collection aliases | `/api/aliases` | GET/POST |
| Node metrics (9.x) | `/api/node/metrics` | GET |
| Node metrics (10.x, Prometheus) | `/api/node/metrics` | GET (Accept: text/plain) |
| System info | `/api/node/system` | GET |

### Configset Upload Protocol

Creating a collection requires a configset to already exist on the cluster. The two-step sequence is:

**Step 1 — Upload configset** (must happen before collection creation):
```
PUT /api/cluster/configs/{configset-name}
Content-Type: application/zip
Body: ZIP archive containing at minimum:
  conf/schema.xml      (or conf/managed-schema)
  conf/solrconfig.xml
```

**Step 2 — Create collection** referencing the uploaded configset:
```json
POST /api/collections
{
  "name": "my-collection",
  "config": "my-configset-name",
  "numShards": 1,
  "replicationFactor": 1
}
```

The configset ZIP is produced by the workload at benchmark setup time. The workload definition must specify the path to the configset directory (containing `conf/`); the tool zips it in-memory and uploads it before calling the collection API. The configset should be deleted as part of teardown alongside the collection.

### Metrics Format Split
- **Solr 9.x**: `GET /api/node/metrics` → custom JSON: `{"metrics": {"solr.jvm": {...}, "solr.node": {...}}}`
- **Solr 10.x**: Same endpoint → Prometheus text exposition format (detected via `Content-Type: text/plain; version=0.0.4`)

### Version Detection
- `GET /api/node/system` → JSON response includes `"lucene": {"solr-spec-version": "9.7.0", ...}`
- Parse major version from `solr-spec-version` to determine metrics format and provisioning mode flags

### Rationale
pysolr reduces boilerplate for the high-frequency data path (indexing and querying), where it is well-tested and reliable. The V2 API via plain HTTP is used for admin operations where pysolr has no coverage. V1 (`/solr/admin/...`) is deprecated and MUST NOT be used for new code.

---

## 2. ASF Licensing and Attribution

### Decision
Follow ASF source header policy. Three categories of files require different treatment.

### File Header Rules

**Category A — Files retained substantially unchanged from OSB:**
Keep the existing OpenSearch Contributors header verbatim. No modification needed.
```python
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
# Modifications Copyright OpenSearch Contributors. See
# GitHub history for details.
```

**Category B — Files substantially modified for Solr:**
Add an Apache Solr attribution line after the existing header:
```python
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
# Modifications Copyright OpenSearch Contributors. See
# GitHub history for details.
#
# Modifications for Apache Solr Benchmark
# Copyright The Apache Software Foundation
```

**Category C — New files written for the Solr fork:**
```python
# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
```

### NOTICE File Rules
The NOTICE file must be updated with the fork's project name at the top, followed by the full attribution chain. All existing attributions must be retained — none may be dropped.
```
Apache Solr Benchmark
Copyright [YEAR] The Apache Solr project

This product includes software originally developed as
OpenSearch Benchmark by OpenSearch Contributors.
Copyright 2022 OpenSearch Contributors.

This product includes software, including Rally source code,
developed by Elasticsearch (http://www.elastic.co).
```

### LICENSE File
The `LICENSE` file retains the full Apache 2.0 license text. Third-party dependency notices (Category A/B from ASF resolved.html) are appended.

### Dependency License Categories (ASF)
- **Category A** (safe to bundle): MIT, BSD 2/3-clause, Apache 2.0, ISC, W3C — no NOTICE required
- **Category B** (allowed with constraints): LGPL, MPL, EPL — cannot be bundled in binary, only linked
- **Category C** (forbidden): GPL, AGPL, CDDL — must not be included

### Rationale
ASF policy requires proper attribution of derived works. Since this fork is intended for the Solr PMC, compliance is mandatory before any PMC contribution.

---

## 3. Pluggable Result Writer Architecture

### Decision
Use Abstract Base Class (ABC) pattern, consistent with the existing codebase's `DataProducer` / `S3DataProducer` pattern. Writer selected via `results_destination` config key.

### Existing Pattern in Codebase
`osbenchmark/data_streaming/data_producer.py` defines `DataProducer(ABC)` with `generate_chunked_data()`.
`osbenchmark/cloud_provider/vendors/s3_data_producer.py` implements `S3DataProducer(DataProducer)`.

The existing `osbenchmark/publisher.py` already writes markdown/CSV via `write_single_results()` using a format-string approach. The pluggable writer wraps and extends this.

### Proposed Interface
```python
class ResultWriter(ABC):
    @abstractmethod
    def open(self, run_metadata: dict) -> None:
        """Called once before writing begins."""

    @abstractmethod
    def write(self, metrics: list[dict]) -> None:
        """Write a batch of metric records."""

    @abstractmethod
    def close(self) -> None:
        """Flush and close. Called once after all metrics written."""
```

### Default Implementation
`LocalFilesystemResultWriter` — writes JSON + CSV to a configurable `results_path`, prints markdown summary table to console. Replaces the current OpenSearch-backed metrics store.

### Writer Selection
Via `benchmark.ini` key `results_writer = local_filesystem` (default). Future writers register by subclassing `ResultWriter` and are selected by name.

### Rationale
ABC pattern is already established in the codebase. No entry_points overhead needed for initial version — direct subclass + registry dict is sufficient and matches existing patterns.

---

## 4. NDJSON to Solr JSON Translation

### Decision
Process action lines at index time in the `bulk-index` runner — extract `_id` and `_index` from the action line and merge them into the document body before posting to Solr. Post document JSON arrays to `/solr/{collection}/update` via pysolr.

### Translation Logic
OSB corpus NDJSON format (two lines per document):
```json
{"index": {"_index": "my-index", "_id": "1"}}
{"field1": "value1", "field2": "value2"}
```

Solr update format (batch array):
```json
[
  {"id": "1", "field1": "value1", "field2": "value2"},
  {"id": "2", "field1": "value2", "field2": "value3"}
]
```

Rules:
1. Read NDJSON line pairs: action line (odd) + document body (even).
2. From the action line, extract:
   - `_id` → set as `"id"` field on the document body (Solr's required unique key field). If `_id` is absent, omit `"id"` and let Solr auto-generate one.
   - `_index` → the source index/collection name. This can be used for routing or logging but is not added to the document.
3. Strip any remaining OpenSearch metadata fields (`_type`) from the document body if present.
4. Do **not** add `_index` as a document field — it is routing metadata, not a document attribute.
5. Batch translated documents into configurable size (default: 500 documents per `solr.add()` call).
6. POST with `commit=False`; commits are triggered separately by a `commit` operation.

### Example

Input NDJSON:
```
{"index": {"_index": "geonames", "_id": "2988507"}}
{"name": "Paris", "country": "FR", "population": 2138551}
```

Resulting Solr document sent via `solr.add()`:
```python
{"id": "2988507", "name": "Paris", "country": "FR", "population": 2138551}
```

### Rationale
Solr requires a unique key field (conventionally `"id"`) on every document. Discarding `_id` would cause Solr to generate random UUIDs, breaking idempotent re-indexing and making it impossible to update or delete specific documents. Extracting `_id` → `"id"` preserves document identity at zero extra cost. The `_index` value is available for logging/validation if needed but is not a document field in Solr.

---

## 5. Source Code Structure

### Decision
Retain existing `osbenchmark/` package structure. Rename only the package entrypoint and branding. Create a new `solrbenchmark/` thin wrapper package that re-exports from adapted `osbenchmark/` modules where renaming is needed.

**Alternative considered**: Rename `osbenchmark/` entirely to `solrbenchmark/`. Rejected — would break 75% reuse target and require updating every import across the entire codebase.

**Chosen approach**: Keep `osbenchmark/` as the implementation package. The `solrbenchmark/` package (or renamed entrypoints) is the user-facing shell. This is the same pattern as many Apache project forks.

### New modules to create
- `osbenchmark/solr/client.py` — Solr HTTP client (replaces client.py/async_connection.py)
- `osbenchmark/solr/runner.py` — Solr-specific operation runners
- `osbenchmark/solr/telemetry.py` — Solr telemetry devices
- `osbenchmark/solr/provisioner.py` — Solr download/install/launch
- `osbenchmark/solr/result_writer.py` — ResultWriter ABC + LocalFilesystemResultWriter
- `osbenchmark/tools/migrate_workload.py` — OSB → Solr workload migration utility

### Modules to delete
- `osbenchmark/async_connection.py` — replaced by `osbenchmark/solr/client.py`
- `osbenchmark/kafka_client.py` — Kafka streaming out of scope for fork
- `osbenchmark/data_streaming/` — out of scope
- All gRPC proto files and stubs

---

## 6. Lessons Learned: The Dual-Mode Mistake

### What Happened

After completing all 39 implementation tasks (T001-T039), a fundamental architectural misunderstanding was discovered: **the implementation created a dual-mode tool instead of a pure Solr tool**.

### The Mistake

**What was implemented**:
- `mode` parameter in configuration and client initialization
- Shim classes (`SolrClientShim`) bridging OpenSearch-style interfaces to Solr operations
- Conditional logic (`if mode == "solr"`) in provisioners, builders, runners
- Both OpenSearch and Solr code paths existing side-by-side
- OpenSearch client connections still available alongside Solr
- Pipelines named `solr-from-distribution` (instead of just `from-distribution`)

**What should have been implemented**:
- Pure Solr tool with single code path
- No mode parameter anywhere
- OpenSearch code removed except for workload import/conversion utilities
- Direct replacement: `client.py` becomes pure Solr client
- Pipelines named generically (`from-distribution`)
- Only OpenSearch compatibility: workload file parsing and corpus format translation

### Why It Happened

**Specification ambiguity**:
- "The tool will no longer support or benchmark OpenSearch clusters" could be read as "disable OpenSearch mode" rather than "remove OpenSearch code"
- The 75% code retention goal was misinterpreted as "keep all OpenSearch code and add Solr alongside it" rather than "retain the generic framework, replace the OpenSearch-specific parts"
- The migration utility's existence suggested runtime OSB compatibility, not just conversion-time

**Implementer assumptions**:
- "Fork" was interpreted as "make compatible with both systems" rather than "replace one system with another"
- The shim pattern seemed like a low-risk way to preserve OpenSearch code while adding Solr
- Mode-based conditional logic felt safer than deleting OpenSearch code paths

### How to Avoid This in Future

**Specification clarity**:
1. **Be explicit about what gets removed**: List modules/classes/functions to delete, not just "replace X with Y"
2. **Distinguish reuse from compatibility**: "Retain the actor framework (code reuse)" vs "Support both engines (runtime compatibility)"
3. **Use architecture diagrams**: A single diagram showing "pure Solr" vs "dual-mode" would have prevented this
4. **Specify what OpenSearch references are acceptable**: "Only in `tools/migrate_workload.py` and corpus format parsing" is clearer than "workload compatibility only"

**Task definition improvements**:
1. **Add explicit deletion tasks**: "T004: Delete OpenSearch client (`client.py`, `async_connection.py`)" not just "Delete OpenSearch-only modules"
2. **Add verification tasks earlier**: "T015: Verify no `mode` parameter exists in configuration" catches mistakes before they compound
3. **Include negative requirements**: "MUST NOT: Add mode parameter, create shim classes, use conditional logic"

**Review checkpoints**:
1. **Architectural review after Phase 2**: Before starting user stories, verify no dual-mode patterns exist
2. **Cross-reference with spec**: Each phase completion should confirm alignment with "pure Solr tool" intent
3. **Grep-based sanity checks**: "If I search for 'mode ==', 'opensearch.*client', or 'OsClient', what should I find?"

### The Silver Lining

**What worked correctly despite the architectural mistake**:
- All Solr operations execute successfully (indexing, search, commit, optimize, collection management)
- Telemetry collects Solr metrics correctly
- Workload migration utility converts OSB workloads correctly
- Schema auto-generation from OpenSearch mappings works
- All bug fixes (NDJSON translation, date formats, geo-points, file I/O) are solid
- Test coverage is comprehensive
- The Solr-specific implementations are correct and production-ready

**Why the correction is straightforward**:
- The Solr code is correct — we just need to remove the OpenSearch scaffolding
- The dual-mode architecture is localized (client initialization, builder factory, provisioner selection)
- Systematic removal (Phase 8 tasks T040-T053) can fix this without rewriting working code

### Key Insight

**Architectural clarity must be stronger than implementation convenience.** When a fork specification says "replace X with Y," that should always mean:
1. Remove X's code paths (except utilities that convert X's data to Y's format)
2. Install Y's code as the direct replacement (not via shims or conditionals)
3. No runtime mode selection between X and Y

If both X and Y are meant to be supported at runtime, that's not a fork — it's a multi-backend tool, and the specification should say so explicitly with different architecture, design patterns, and task breakdown.

---

## Update 2026-02-24: No Auto-Conversion at Run Time

The following research covers the three directives added in the 2026-02-24 spec session.

### R-01: Auto-Conversion Removal (FR-018b)

**Decision**: Replace `_maybe_auto_convert_workload()` in `test_run_orchestrator.py` with `_check_workload_is_solr_native()` that detects OSB format → aborts with a clear error. No conversion logic called from the run path.

**Rationale**: Auto-conversion at runtime is silent, triggers unexpected disk writes, and hides an important user decision. Forcing explicit `convert-workload` makes the process transparent and auditable.

**Implementation boundary**: Only `detector.is_opensearch_workload_path(path)` may be imported from `test_run_orchestrator.py`. The full `workload_converter` MUST NOT be imported from the run path.

**New function needed in `detector.py`**:
```python
def is_opensearch_workload_path(workload_path: str) -> bool:
    """
    Reads workload.json from disk. Returns True if it contains 'indices' key (OSB format).
    Returns False for 'collections' key (Solr), missing key, or any parse error.
    """
```

### R-02: Bridge Runner Removal (FR-018g)

**Decision**: Remove these five bridge runner classes from `runner.py`:
`SolrRefreshBridge`, `SolrNoOpBridge`, `SolrDeleteIndexBridge`, `SolrCreateIndexBridge`, `SolrBulkBridge`.

**Rationale**: Bridge runners allowed OSB workloads to run against Solr at runtime. With the new "error-and-abort" policy at workload load time, runtime bridging is never reached. Removing bridges enforces the clean architecture: conversion = `convert-workload` CLI only.

### R-03: Search Runner Hardening (FR-018f)

**Decision**: In `SolrSearch.__call__()`: detect `body["query"]` is a `dict` (OpenSearch DSL) → raise `BenchmarkAssertionError` with message pointing to `convert-workload`.

**Note**: Check whether `_translate_query_node()` helpers in `runner.py` are now fully duplicated by `conversion/query.py` — if so, remove them from `runner.py`.

### R-04: benchmark.ini URL Fix (FR-026)

**Decision**: `osbenchmark/resources/benchmark.ini` line 28: `default.url = https://github.com/janhoy/solr-benchmark-workloads`

---

## Update 2026-02-25: cluster_config + Collection Settings + Logging Fix

### R-05: cluster_config Mechanism (Krav 3)

**Decision**: Reuse the existing `ClusterConfigInstanceLoader` in `osbenchmark/builder/cluster_config.py`. Solr uses only the `[variables]` section from INI files. The Solr provisioner reads `cluster_config.variables` and translates three keys to Solr environment variables: `heap_size` → `SOLR_HEAP`, `gc_tune` → `GC_TUNE`, `solr_opts` → `SOLR_OPTS`. These are passed as subprocess env overrides to `bin/solr start` (local) or `-e KEY=VALUE` flags to `docker run`.

**Existing INI files**: `osbenchmark/resources/cluster_configs/main/cluster_configs/v1/` — files `1gheap.ini`, `4gheap.ini`, `g1gc.ini`, etc. already exist. They need their variables aligned to the Solr naming: `heap_size` (already correct) + add `gc_tune` to the GC configs.

**No template file rendering needed**: Unlike OSB's OpenSearch provisioner which renders `jvm.options.j2` to a file, Solr reads JVM settings from environment variables (`SOLR_HEAP`, `GC_TUNE`). The `config_paths` / `_apply_config()` mechanism is OSB's OpenSearch-specific path and must NOT be called for Solr provisioning.

**cluster_config.names storage**: Stored as a list (from `opts.csv_to_list()`). Currently `test_run_orchestrator.py` renders this list directly in a format string producing `[['external']]`. Fix: use `", ".join(cluster_config_names)` before formatting.

**benchmark-only validation**: In `benchmark.py` `configure_builder_params()`, when `pipeline == "benchmark-only"`, check if `args.cluster_config != "defaults"` and raise `SystemExit` with message: `"--cluster-config is only valid for provisioning pipelines (from-distribution, docker, from-sources). It cannot be used with the 'benchmark-only' pipeline."`.

### R-06: Collection Replica Types (Krav 2)

**Current state**: `Collection` class has `num_shards` (from `num-shards`) and `replication_factor` (from `replication-factor`). `SolrAdminClient.create_collection()` sends `numShards` + `replicationFactor` to Solr V2 API.

**Required additions**: The Solr V2 Collections API (`POST /api/collections`) natively supports three replica type counts: `nrtReplicas`, `tlogReplicas`, `pullReplicas`. Total replicas = sum of all three. The `replicationFactor` param is a shortcut that sets `nrtReplicas` only.

**Migration**: Replace `replication-factor` with `nrt-replicas` in workload.json (with backward-compat fallback). Rename field in `Collection` class. Add `pull_replicas` and `tlog_replicas`.

**Workload.json new field names** (snake_case as specified in FR-009a):
- `shards` (int, default=1) — replaces `num-shards`
- `nrt_replicas` (int, default=1) — replaces `replication-factor`
- `pull_replicas` (int, default=0) — new
- `tlog_replicas` (int, default=0) — new

**Backward compat**: Loader reads `shards` first, falls back to `num-shards`; reads `nrt_replicas` first, falls back to `replication-factor`.

**`create_collection()` API payload** (new):
```json
{
  "name": "my-coll",
  "config": "my-cfg",
  "numShards": 2,
  "nrtReplicas": 1,
  "tlogReplicas": 0,
  "pullReplicas": 0,
  "waitForFinalState": true
}
```

### R-07: Logging Bug (Krav 1)

**Root cause**: `self.test_run.cluster_config` is a Python list `['external']`. The format string `"cluster_config [{}]"` renders it as `[['external']]`.

**Fix location**: `osbenchmark/test_run_orchestrator.py` — two `console.info(...)` call sites (lines ~297 and ~305). Change `self.test_run.cluster_config` to `", ".join(self.test_run.cluster_config or ["none"])` in both format calls.

**Expected output after fix**: `cluster_config [external]`

---

## Phase 0 Addendum: Documentation Site (US5) — 2026-02-25

### Decision D-DOC-1: Jekyll Theme

**Decision**: `just-the-docs` gem version 0.12.0

**Rationale**: The OSB docs use a similar sidebar-nav documentation theme. `just-the-docs`
provides built-in Lunr.js search (client-side, no backend), clean sidebar navigation with
3-level nesting (`parent` / `grand_parent` front matter), responsive layout, callout blocks,
and native GitHub Pages compatibility. It is actively maintained and widely used for
technical reference documentation.

**Alternatives considered**:
- `minimal-mistakes` — more blog-oriented, heavier config, less suited for deep reference nav.
- `minima` (default) — too plain; no sidebar navigation or built-in search.
- Custom theme — unnecessary complexity; `just-the-docs` meets all requirements.

### Decision D-DOC-2: Deployment Method

**Decision**: GitHub Actions workflow (`docs.yml`) deploying to GitHub Pages from `docs/`.

**Rationale**: Modern GitHub Pages approach (Settings → Pages → Source: "GitHub Actions")
gives full control over build environment (Ruby 3.3, Jekyll 4.4.1). The workflow uses
`actions/configure-pages` to inject the correct `baseurl` automatically. The legacy
`github-pages` gem pins Jekyll 3.x and is incompatible with `just-the-docs` 0.12.0.

### Decision D-DOC-3: OSB Pages Included vs Excluded

**Included (~35 pages)**: All user-guide pages except contributing-workloads; all reference
pages except generate-data and redline-test commands; indices.md replaced by collections.md;
quickstart, glossary, faq — all adapted for Solr.

**Excluded (8 pages)**:
- `features/synthetic-data-generation/` (entire section) — feature deleted
- `reference/commands/generate-data.md` — command deleted
- `reference/commands/redline-test.md` — not ported
- `reference/workloads/indices.md` — replaced by `collections.md`
- `workloads/vectorsearch.md` — OSB-only workload
- `user-guide/working-with-workloads/contributing-workloads.md` — OSB contribution workflow
- `migration-assistance.md` — OSB-specific Rally migration
- `version-history.md` — deferred (will be created when releases are tagged)

**New pages (7)**:
`reference/workloads/collections.md`, `cluster-config/index.md`,
`cluster-config/available-configs.md`, `converter/index.md`, `converter/usage.md`,
`converter/what-converts.md`, `about.md`

### Decision D-DOC-4: Copyright & Attribution Approach

**Decision**: Shared ASF footer include + dedicated `about.md` page.

**Rationale**: Per Constitution Principles I–III — individual Markdown pages do NOT carry
per-file license headers (HTML comments in Markdown are non-standard across renderers).
The `_includes/footer_custom.html` is the correct mechanism for a Jekyll site. The
`about.md` page is the single authoritative location for the full attribution chain
(OpenSearch Contributors, Elasticsearch bv/Rally) and trademark notices.

OpenSearch trademark notice (where referenced): "OpenSearch® is a registered trademark of the OpenSearch Software Foundation."
Apache Solr trademark notice: "Apache Solr is a trademark of The Apache Software Foundation."
