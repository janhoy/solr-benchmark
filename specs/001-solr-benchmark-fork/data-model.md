# Data Model: Solr Benchmark Fork

**Feature**: 001-solr-benchmark-fork
**Date**: 2026-02-19

---

## Overview

This document defines the key entities in the Solr Benchmark fork, their fields, and the relationships between them. It focuses on entities that differ from OpenSearch Benchmark (OSB) or are newly introduced.

---

## 1. Workload

A workload is a Solr-native benchmark definition stored as a directory of JSON/YAML files. It is **not** back-compatible with OSB workloads.

```
workload/
├── workload.json         ← top-level workload descriptor
├── operations/
│   └── default.json      ← operation definitions
└── challenges/
    └── default.json      ← challenge (scheduling/test procedure) definitions
```

### `workload.json` fields

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique workload name (kebab-case) |
| `description` | string | Human-readable description |
| `collections` | list[Collection] | Collections used by this workload |
| `corpora` | list[Corpus] | Dataset corpora |
| `operations` | list[Operation] \| ref | Inline or path to operation defs |
| `challenges` | list[Challenge] \| ref | Inline or path to challenge definitions |

---

## 2. Collection (replaces OSB `Index`)

A Solr collection definition used in workload setup/teardown.

```json
{
  "name": "my-collection",
  "configset": "my-configset",
  "configset-path": "workloads/geonames/configset",
  "num-shards": 1,
  "replication-factor": 1,
  "tlog-replicas": 0,
  "pull-replicas": 0
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | yes | — | Solr collection name |
| `configset` | string | no | (collection name) | Configset name on the cluster |
| `configset-path` | string | no | — | Path to the local configset directory (`conf/schema.xml`, `conf/solrconfig.xml`). If provided, the tool zips and uploads it before creating the collection. |
| `num-shards` | int | no | 1 | Number of shards (`numShards` in Solr V2 API) |
| `replication-factor` | int | no | 1 | NRT (Near-Real-Time) replicas per shard (`nrtReplicas` in Solr V2 API). In SolrCloud, `replication-factor` has always meant NRT replicas; this mapping is semantically identical. |
| `tlog-replicas` | int | no | 0 | TLOG replicas per shard (`tlogReplicas`). Used in SolrCloud for transaction-log-based recovery. |
| `pull-replicas` | int | no | 0 | Pull replicas per shard (`pullReplicas`). Read-only replicas that do not participate in indexing. |

**Collection creation is a two-step API sequence**: (1) `POST /solr/admin/configs?action=UPLOAD&name={configset}` with ZIP body (V1 API, works on Solr 9.x), then (2) `POST /api/collections` referencing the configset name (V2 API). Teardown deletes both.

**Replaces**: OSB `Index` entity (which had `name`, `body` for mappings, `auto_managed_index`)

**Note on replica types**: Total replicas per shard = `replication-factor + tlog-replicas + pull-replicas`. For single-node benchmarks, keep defaults (1 NRT replica, 0 others).

---

## 3. Corpus

Unchanged from OSB structure; refers to dataset files (NDJSON). The bulk-index runner processes action lines at index time: `_id` is extracted and added to the document as the `"id"` field; `_index` is available for routing/logging but not stored as a document field.

```json
{
  "name": "my-corpus",
  "documents": [
    {
      "source-file": "documents.json.bz2",
      "document-count": 1000000,
      "compressed-bytes": 50000000,
      "uncompressed-bytes": 500000000
    }
  ]
}
```

---

## 4. Operation

A benchmark operation targeting Solr. All operations use Solr-native terminology.

### Common fields (all operations)

| Field | Type | Description |
|---|---|---|
| `name` | string | Operation instance name |
| `operation-type` | string | One of the supported operation types (see below) |
| `param-source` | string | (optional) Custom parameter source class |

### Supported operation types

| `operation-type` | Description | Key params |
|---|---|---|
| `bulk-index` | Index documents from a corpus into a collection. Extracts `_id` from action lines → Solr `"id"` field; `_index` available for routing. | `collection`, `batch-size` (default: 500), `commit-after` |
| `search` | Send a query to Solr. Supports two modes: classic params (`q`, `fl`, etc.) via GET/POST to `/solr/{collection}/select`, or JSON Query DSL via POST to `/solr/{collection}/query`. Mode is selected by presence of `body` param. | See search modes below |
| `commit` | Trigger a hard or soft commit | `collection`, `soft-commit` (bool, default: false) |
| `optimize` | Trigger segment optimize/merge | `collection`, `max-segments` (default: 1) |
| `create-collection` | Upload configset ZIP then create a Solr collection via V2 API (two-step). | `collection` (Collection object incl. `configset-path`), `wait-for-active-shards` |
| `delete-collection` | Delete a Solr collection and its associated configset via V2 API. | `collection` |
| `raw-request` | Send arbitrary HTTP request to any Solr endpoint | `method`, `path`, `body`, `headers` |

### Search Operation: Two Modes

The `search` operation supports two mutually exclusive query styles. The runner detects which mode to use based on whether a `body` key is present.

---

#### Mode 1 — Classic Solr Query Params

Sends a GET (or POST with form params) to `/solr/{collection}/select`.

| Param | Type | Description |
|---|---|---|
| `collection` | string | Target collection name |
| `q` | string | Main query string (Lucene/Solr syntax, e.g. `"*:*"`, `"name:Paris"`) |
| `fl` | string | Field list (comma-separated, e.g. `"id,name,score"`) |
| `rows` | int | Max results to return (default: 10) |
| `fq` | string \| list[string] | Filter query/queries |
| `sort` | string | Sort expression (e.g. `"score desc, id asc"`) |
| `request-params` | dict | Any additional Solr request handler params passed through verbatim |

Example:
```json
{
  "name": "default-search",
  "operation-type": "search",
  "collection": "my-collection",
  "q": "*:*",
  "fl": "id,title",
  "rows": 10
}
```

---

#### Mode 2 — JSON Query DSL

Posts a JSON body to `/solr/{collection}/query`. Solr's JSON Query DSL is structurally similar to OpenSearch's query DSL but less comprehensively documented. It is the preferred path for complex queries (boolean logic, JSON faceting, nested queries).

| Param | Type | Description |
|---|---|---|
| `collection` | string | Target collection name |
| `body` | dict | Full JSON query body sent as-is to `/query` |

The `body` dict is posted verbatim, giving workload authors full control. Known top-level keys:

| JSON key | Description |
|---|---|
| `query` | Main query — string (Solr syntax) or query object |
| `filter` | Filter queries — string or list of strings/objects |
| `fields` | Field list — list of field names |
| `limit` | Max results (equivalent to `rows`) |
| `offset` | Starting offset (equivalent to `start`) |
| `sort` | Sort expression string |
| `facet` | JSON Facet API object (terms, range, query facets) |
| `params` | Additional legacy request params passed through |

Example — simple JSON DSL query:
```json
{
  "name": "json-dsl-search",
  "operation-type": "search",
  "collection": "my-collection",
  "body": {
    "query": "*:*",
    "fields": ["id", "title", "score"],
    "limit": 10,
    "sort": "score desc"
  }
}
```

Example — JSON DSL with filter and facet:
```json
{
  "name": "faceted-search",
  "operation-type": "search",
  "collection": "geonames",
  "body": {
    "query": "name:Paris",
    "filter": "population:[1000000 TO *]",
    "fields": ["id", "name", "country", "population"],
    "limit": 10,
    "facet": {
      "countries": {
        "type": "terms",
        "field": "country",
        "limit": 5
      }
    }
  }
}
```

> **Note**: Solr's JSON Query DSL is not fully documented. The `body` is passed through verbatim, so workload authors may need to consult Solr source code or community resources for advanced query object syntax. The runner records latency and result hit count regardless of which mode is used.

---

## 5. Challenge

Unchanged from OSB — the `challenge` entity and its workload file key are retained as-is. Contains a list of `tasks` referencing operations.

---

## 6. SolrNode (runtime entity, not workload)

Represents a connected Solr node. Created at benchmark start from target host configuration.

| Field | Type | Description |
|---|---|---|
| `host` | string | Hostname or IP |
| `port` | int | Port (default: 8983) |
| `version` | string | Detected from `/api/node/system` (e.g., `"9.7.0"`) |
| `major_version` | int | 9 or 10, determines metrics format and provisioner flags |
| `base_url` | string | `http://{host}:{port}` |
| `solr_url` | string | `http://{host}:{port}/solr` (for pysolr) |
| `api_url` | string | `http://{host}:{port}/api` (for V2 admin calls) |

---

## 7. MetricRecord (runtime entity)

One measurement recorded during a benchmark run. Aggregated into the final report by the existing `aggregator.py`.

| Field | Type | Description |
|---|---|---|
| `name` | string | Metric name (e.g., `"bulk_indexing_throughput"`) |
| `value` | float | Numeric value |
| `unit` | string | Unit (e.g., `"docs/s"`, `"ms"`, `"MB"`) |
| `task` | string | Operation name that produced this metric |
| `operation_type` | string | Operation type |
| `sample_type` | string | `"normal"` or `"warmup"` |
| `timestamp` | float | Unix epoch seconds |
| `meta` | dict | Optional extra labels (e.g., `shard`, `node`) |

---

## 8. ResultWriter (output entity)

Controls where benchmark results are persisted. Configured via `benchmark.ini` key `results_writer`.

### `LocalFilesystemResultWriter` output

```
{results_path}/
├── {run_id}/
│   ├── results.json    ← all MetricRecords as JSON array
│   ├── results.csv     ← flattened CSV for spreadsheet import
│   └── summary.txt     ← markdown summary table (also printed to console)
```

### `results.json` record shape

```json
{
  "run_id": "20260219T143022Z",
  "workload": "my-workload",
  "challenge": "default",
  "solr_version": "9.7.0",
  "metrics": [
    {
      "name": "bulk_indexing_throughput",
      "value": 45000.5,
      "unit": "docs/s",
      "task": "bulk-index",
      "operation_type": "bulk-index",
      "sample_type": "normal",
      "timestamp": 1739967022.4
    }
  ]
}
```

---

## 9. Telemetry Device (Solr-specific)

Three new telemetry devices replace the OpenSearch-specific ones.

### `SolrJvmStats`

Polls `GET /api/node/metrics` during benchmark. Recorded metrics:

| Metric name | Unit | Source (9.x JSON path) |
|---|---|---|
| `jvm_heap_used_bytes` | bytes | `metrics.solr.jvm.memory.heap.used` |
| `jvm_heap_max_bytes` | bytes | `metrics.solr.jvm.memory.heap.max` |
| `jvm_gc_count` | count | `metrics.solr.jvm.gc.G1-Young-Generation.count` |
| `jvm_gc_time_ms` | ms | `metrics.solr.jvm.gc.G1-Young-Generation.time` |

### `SolrNodeStats`

| Metric name | Unit | Description |
|---|---|---|
| `cpu_usage_percent` | percent | OS CPU load from `/api/node/system` |
| `os_memory_free_bytes` | bytes | Free memory |
| `query_handler_requests_total` | count | Cumulative query handler requests |
| `query_handler_errors_total` | count | Cumulative query handler errors |

### `SolrCollectionStats`

Polls `GET /api/collections/{collection}/metrics` (or cluster metrics) per collection.

| Metric name | Unit | Description |
|---|---|---|
| `num_docs` | count | Live document count |
| `index_size_bytes` | bytes | On-disk index size |
| `segment_count` | count | Lucene segment count |

---

## 10. ClusterConfig (provisioning entity)

A named configuration that sets Solr JVM and GC parameters before a provisioned Solr node starts. Applicable only to provisioning pipelines (`from-distribution`, `docker`, `from-sources`). **Not applicable to `benchmark-only` pipeline** — specifying `--cluster-config` with `benchmark-only` is a hard error.

### INI file format (stored in `osbenchmark/resources/cluster_configs/main/cluster_configs/v1/`)

```ini
[meta]
description=Sets the Java heap to 4GB

[config]
base=vanilla

[variables]
heap_size=4g
```

### Variable → Solr env var mapping

| INI variable | Solr env var | Description | Example value |
|---|---|---|---|
| `heap_size` | `SOLR_HEAP` | JVM heap size (Xms and Xmx) | `4g` |
| `gc_tune` | `GC_TUNE` | GC algorithm flags | `-XX:+UseG1GC -XX:+UseStringDeduplication` |
| `solr_opts` | `SOLR_OPTS` | Additional JVM options | `-XX:+PrintGCDetails` |

All variables are optional. Variables not present in the INI are not set in the subprocess env (Solr uses its defaults).

### Built-in presets

| Name | heap_size | gc_tune |
|---|---|---|
| `defaults` | (Solr default) | (Solr default) |
| `1gheap` | `1g` | — |
| `2gheap` | `2g` | — |
| `4gheap` | `4g` | — |
| `8gheap` | `8g` | — |
| `16gheap` | `16g` | — |
| `24gheap` | `24g` | — |
| `g1gc` | — | `-XX:+UseG1GC -XX:+UseStringDeduplication` |
| `parallelgc` | — | `-XX:+UseParallelGC` |

Configs can be combined with `+` separator, e.g. `--cluster-config 4gheap+g1gc`.

### Application method

- **`SolrProvisioner` (local)**: Sets env vars in `subprocess.run(..., env={...})` before calling `bin/solr start`.
- **`SolrDockerLauncher` (Docker)**: Passes `-e SOLR_HEAP=4g -e GC_TUNE=...` flags in `docker run`.

---

## Entity Relationships

```
Workload
  ├── has many → Collection (setup/teardown targets)
  ├── has many → Corpus (data sources)
  └── has many → Challenge
                    └── has many → Task → references → Operation

Operation → (at runtime) → SolrNode
SolrNode → (telemetry) → MetricRecord[]
Operation → (result) → MetricRecord[]
MetricRecord[] → (aggregated by aggregator.py) → ResultWriter → output files
```
