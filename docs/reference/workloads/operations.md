---
title: operations
parent: Workload Reference
grand_parent: Reference
nav_order: 100
---

# operations

Operations define the actions performed during a test procedure. They are referenced from test procedure schedules.

## Syntax

Operations can be defined inline in a schedule or in a top-level `"operations"` section:

```json
{
  "operations": [
    {
      "name": "my-search",
      "operation-type": "search",
      "body": {
        "query": "*:*",
        "rows": 10
      }
    }
  ]
}
```

## Built-in operation types

### bulk-index

```json
{
  "operation-type": "bulk-index",
  "bulk-size": 500,
  "collection": "my_collection"
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `bulk-size` | `500` | Number of documents per batch |
| `collection` | (first collection in workload) | Target collection |
| `corpora` | (all corpora) | Corpus name to index from |

### search

```json
{
  "operation-type": "search",
  "body": {
    "query": "*:*",
    "rows": 10,
    "fl": "id,title"
  },
  "collection": "my_collection"
}
```

The `body` is passed directly as a Solr JSON query body. Use standard [Solr JSON Request API](https://solr.apache.org/guide/solr/latest/query-guide/json-request-api.html) syntax.

### commit

```json
{ "operation-type": "commit" }
```

Issues a hard commit to Solr. Optional `collection` parameter.

### optimize

```json
{ "operation-type": "optimize", "max-segments": 1 }
```

Issues a force-merge (optimize) to reduce the segment count to `max-segments` (default: 1).

### create-collection

```json
{
  "operation-type": "create-collection",
  "collection": "my_collection",
  "configset-path": "configsets/my_schema",
  "num-shards": 1,
  "replication-factor": 1
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `collection` | (required) | Collection name |
| `configset-path` | (none) | Path to local configset directory (relative to workload dir) |
| `num-shards` | `1` | Number of shards |
| `replication-factor` | `1` | Number of NRT replicas per shard |
| `tlog-replicas` | `0` | Number of TLOG replicas per shard |
| `pull-replicas` | `0` | Number of pull replicas per shard |

### delete-collection

```json
{
  "operation-type": "delete-collection",
  "collection": "my_collection"
}
```

### raw-request

```json
{
  "operation-type": "raw-request",
  "path": "/api/collections/my_collection/config",
  "method": "POST",
  "body": {
    "set-property": {
      "updateHandler.autoSoftCommit.maxTime": "5000"
    }
  }
}
```

Executes an arbitrary HTTP request against the Solr Admin API (`/api/...` V2 endpoints).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `path` | (required) | API path, e.g. `/api/collections/my_coll/config` |
| `method` | `GET` | HTTP method: `GET`, `POST`, `DELETE` |
| `body` | (none) | Request body (JSON object) |
