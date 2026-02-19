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
