---
title: Common Operations
parent: Understanding Workloads
grand_parent: User Guide
nav_order: 16
---

# Common Operations

Apache Solr Benchmark provides the following built-in operation types.

## bulk-index

Indexes documents from a corpus into a Solr collection in batches.

```json
{
  "name": "bulk-index",
  "operation-type": "bulk-index",
  "bulk-size": 500,
  "collection": "nyc_taxis"
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `bulk-size` | `500` | Number of documents per batch |
| `collection` | (first collection in workload) | Target collection |

## search

Executes a Solr query and measures latency and throughput.

```json
{
  "name": "match-all",
  "operation-type": "search",
  "body": {
    "query": "*:*",
    "rows": 10,
    "fl": "id"
  }
}
```

For Solr JSON DSL queries using structured query syntax:

```json
{
  "name": "range-query",
  "operation-type": "search",
  "body": {
    "query": {
      "range": "pickup_datetime:[2015-01-01T00:00:00Z TO 2015-02-01T00:00:00Z]"
    }
  }
}
```

The `body` is passed directly as the Solr JSON query body. Use standard [Solr JSON Request API](https://solr.apache.org/guide/solr/latest/query-guide/json-request-api.html) syntax.

## commit

Issues a hard commit to flush all pending documents.

```json
{
  "name": "commit",
  "operation-type": "commit"
}
```

## optimize

Issues an optimize (force-merge) command to reduce the number of index segments.

```json
{
  "name": "optimize",
  "operation-type": "optimize",
  "max-num-segments": 1
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max-num-segments` | `1` | Target segment count after optimization |

## create-collection

Creates a Solr collection.

```json
{
  "name": "create-collection",
  "operation-type": "create-collection",
  "collection": "my_collection",
  "configset-path": "configsets/my_schema",
  "shards": 1,
  "nrt_replicas": 1
}
```

## delete-collection

Deletes a Solr collection.

```json
{
  "name": "delete-collection",
  "operation-type": "delete-collection",
  "collection": "my_collection"
}
```

## raw-request

Executes a raw HTTP request against the Solr Admin API. Useful for custom operations not covered by built-in types.

```json
{
  "name": "my-custom-op",
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
