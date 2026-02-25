---
title: Anatomy of a Workload
parent: Understanding Workloads
grand_parent: User Guide
nav_order: 15
---

# Anatomy of a Workload

A workload is a directory containing a `workload.json` file (the main descriptor) and supporting files such as data files, operation templates, and configsets.

## Workload directory structure

```
my-workload/
├── workload.json                  # Main descriptor
├── operations/
│   └── default.json               # Operation definitions
├── challenges/
│   └── default.json               # Challenge (test procedure) definitions
├── files/
│   └── data.json.gz               # Corpus data (compressed NDJSON)
└── configsets/
    └── my-schema/
        ├── schema.xml
        └── solrconfig.xml
```

## workload.json structure

```json
{
  "description": "NYC taxi ride benchmark for Apache Solr",
  "collections": [
    {
      "name": "nyc_taxis",
      "configset-path": "configsets/nyc_taxis",
      "shards": 1,
      "nrt_replicas": 1
    }
  ],
  "corpora": [
    {
      "name": "nyc_taxis",
      "documents": [
        {
          "source-file": "files/data.json.gz",
          "document-count": 165346692,
          "compressed-bytes": 4917851637,
          "uncompressed-bytes": 74818096036
        }
      ]
    }
  ],
  "schedule": [
    {
      "operation": "bulk-index",
      "warmup-time-period": 120,
      "clients": 8
    },
    {
      "operation": "commit"
    },
    {
      "operation": "search",
      "clients": 1,
      "iterations": 200,
      "target-throughput": 10
    }
  ]
}
```

## Key workload.json keys

### `collections`

Defines the Solr collections to create before benchmarking.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Collection name |
| `configset-path` | string | Path (relative to workload dir) to a configset directory |
| `shards` | integer | Number of shards (default: 1) |
| `nrt_replicas` | integer | NRT replicas per shard (default: 1) |
| `tlog_replicas` | integer | TLOG replicas per shard (default: 0) |
| `pull_replicas` | integer | Pull replicas per shard (default: 0) |

### `corpora`

Defines the datasets to index. Each corpus references one or more document files in gzip-compressed NDJSON format.

### `schedule`

Defines the sequence of operations in the default challenge. Each entry references an operation by name and may override parameters such as `clients`, `iterations`, and `target-throughput`.

### `operations` (optional section)

Named operations can be defined in a top-level `"operations"` array and referenced by name in schedules. Complex workloads often move operations to a separate `operations/default.json` file (referenced via Jinja2 include).

### `test-procedures` (optional section)

Defines multiple named challenges. See [test-procedures Reference](../../reference/workloads/test-procedures.html).

## Jinja2 templating

Workload files are processed as [Jinja2](https://jinja.palletsprojects.com/) templates before being parsed as JSON. This allows parameter substitution:

{% raw %}
```json
{
  "operation-type": "bulk-index",
  "bulk-size": {{ bulk_size | default(500) }}
}
```
{% endraw %}

Override at runtime with `--workload-params "bulk_size:1000"`.
