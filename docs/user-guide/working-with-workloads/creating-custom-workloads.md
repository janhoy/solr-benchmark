---
title: Creating Custom Workloads
parent: Working with Workloads
grand_parent: User Guide
nav_order: 10
---

# Creating Custom Workloads

To create a workload tailored for your Solr data and queries, create a directory with the structure described in [Anatomy of a Workload](../understanding-workloads/anatomy-of-a-workload.html).

## Minimal workload example

```
my-benchmark/
├── workload.json
├── configsets/
│   └── my_schema/
│       ├── schema.xml
│       └── solrconfig.xml
└── files/
    └── my_data.json.gz
```

**workload.json:**

```json
{
  "description": "My custom Solr benchmark",
  "collections": [
    {
      "name": "my_collection",
      "configset-path": "configsets/my_schema",
      "shards": 1,
      "nrt_replicas": 1
    }
  ],
  "corpora": [
    {
      "name": "my_data",
      "documents": [
        {
          "source-file": "files/my_data.json.gz",
          "document-count": 100000,
          "compressed-bytes": 50000000,
          "uncompressed-bytes": 200000000
        }
      ]
    }
  ],
  "schedule": [
    {
      "operation": {
        "operation-type": "bulk-index",
        "bulk-size": 500
      },
      "warmup-time-period": 60,
      "clients": 4
    },
    { "operation": "commit" },
    {
      "operation": {
        "name": "my-search",
        "operation-type": "search",
        "body": { "query": "*:*", "rows": 10 }
      },
      "clients": 1,
      "iterations": 100
    }
  ]
}
```

## Preparing corpus data

Corpus data must be in gzip-compressed NDJSON (Newline-Delimited JSON) format, where each line is a JSON document to index. Documents should include an `id` field matching your Solr schema's unique key field.

```json
{"id": "1", "title": "My document", "timestamp": "2024-01-01T00:00:00Z"}
{"id": "2", "title": "Another document", "timestamp": "2024-01-02T00:00:00Z"}
```

Compress the file:

```bash
gzip my_data.json
```

## Defining a configset

A configset directory must contain at minimum:
- `schema.xml` — field definitions and types
- `solrconfig.xml` — request handler and cache configuration

See the [Apache Solr Reference Guide: Configsets](https://solr.apache.org/guide/solr/latest/configuration-guide/configsets.html) for full documentation.

## Using Jinja2 parameters

Workload files are Jinja2 templates. Add parameters to allow runtime overrides:

{% raw %}
```json
{
  "operation-type": "bulk-index",
  "bulk-size": {{ bulk_size | default(500) }},
  "clients": {{ index_clients | default(4) }}
}
```
{% endraw %}

Then override at runtime:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload-path my-benchmark \
  --workload-params "bulk_size:1000,index_clients:8"
```

## Splitting operations into separate files

For complex workloads, define operations and challenges in separate files and reference them from `workload.json` using Jinja2 include tags:

{% raw %}
```json
"operations": [
  {% include "operations/default.json" %}
],
"test-procedures": [
  {% include "challenges/default.json" %}
]
```
{% endraw %}
