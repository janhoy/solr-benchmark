---
title: collections
parent: Workload Reference
grand_parent: Reference
nav_order: 65
---

# collections

The `"collections"` array in `workload.json` defines the Solr collections to create before the benchmark starts.

## Syntax

```json
{
  "collections": [
    {
      "name": "<collection-name>",
      "configset-path": "<path>",
      "shards": 1,
      "nrt_replicas": 1,
      "tlog_replicas": 0,
      "pull_replicas": 0
    }
  ]
}
```

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | The collection name. Must be a valid Solr collection name. |
| `configset-path` | string | Yes | — | Path relative to the workload directory pointing to a configset directory containing `schema.xml` and `solrconfig.xml`. |
| `shards` | integer | No | `1` | Number of shards for the collection. |
| `nrt_replicas` | integer | No | `1` | Number of NRT (near-real-time) replicas per shard. NRT replicas participate in leader elections. |
| `tlog_replicas` | integer | No | `0` | Number of TLOG replicas per shard. TLOG replicas buffer updates in a transaction log. |
| `pull_replicas` | integer | No | `0` | Number of Pull replicas per shard. Pull replicas are read-only and receive index segments from the leader. |

## Example

```json
{
  "collections": [
    {
      "name": "nyc_taxis",
      "configset-path": "configsets/nyc_taxis",
      "shards": 2,
      "nrt_replicas": 1,
      "tlog_replicas": 1,
      "pull_replicas": 0
    }
  ]
}
```

## Notes

- The `configset-path` directory must contain at minimum `schema.xml` and `solrconfig.xml`.
- For SolrCloud, the configset is uploaded to ZooKeeper before the collection is created.
- If the collection already exists when the benchmark starts, it is deleted and recreated so that benchmarks are repeatable.
- See the [Apache Solr Reference Guide: Collections API](https://solr.apache.org/guide/solr/latest/deployment-guide/collections-api.html) for background.
