# Apache Solr Benchmark

Apache Solr Benchmark is a macrobenchmarking framework for [Apache Solr](https://solr.apache.org/).

It is a fork of [OpenSearch Benchmark](https://github.com/opensearch-project/opensearch-benchmark),
itself derived from [Elastic Rally](https://github.com/elastic/rally).

**DISCLAIMER**: Work in progress

## What is Apache Solr Benchmark?

If you are looking to performance test Apache Solr, this tool can help you with:

* Running performance benchmarks and recording results
* Setting up and tearing down Solr clusters for benchmarking (local distribution or Docker)
* Managing benchmark workloads (collections, configsets, search operations)
* Collecting JVM, node, and collection metrics via telemetry devices
* Migrating existing OSB/Rally workloads to Solr format

## Quick Start

### Install

```bash
pip install -e .
```

**NOTE**: We do not offer the tool as a python package yet 

### Run a benchmark against an already-running Solr instance

```bash
solr-benchmark execute-test \
  --pipeline=benchmark-only \
  --workload=<your-workload> \
  --challenge=<challenge-name> \
  --target-host=localhost:8983
```

### Provision Solr locally, then benchmark

```bash
solr-benchmark execute-test \
  --pipeline=solr-from-distribution \
  --distribution-version=9.7.0 \
  --workload=<your-workload>
```

### Provision Solr via Docker, then benchmark

```bash
solr-benchmark execute-test \
  --pipeline=solr-docker \
  --distribution-version=9.7.0 \
  --workload=<your-workload>
```

### Migrate an existing OSB workload to Solr format

```bash
solr-migrate-workload --input workload.json --output solr-workload.json
```

## Workload format

A Solr workload is a JSON file with the following top-level keys:

```json
{
  "name": "my-workload",
  "description": "...",
  "collections": [
    {
      "name": "my-collection",
      "configset": "my-configset",
      "configset-path": "/path/to/configset/dir",
      "num-shards": 1,
      "replication-factor": 1
    }
  ],
  "challenges": [
    {
      "name": "default",
      "schedule": [
        {"operation": {"operation-type": "create-collection"}},
        {"operation": {"operation-type": "bulk-index", "bulk-size": 500}},
        {"operation": {"operation-type": "search", "q": "*:*", "rows": 10}},
        {"operation": {"operation-type": "optimize"}},
        {"operation": {"operation-type": "delete-collection"}}
      ]
    }
  ]
}
```

### Supported operation types

| Operation type | Description |
|---|---|
| `bulk-index` | Index documents from an NDJSON corpus |
| `search` | Run a Solr search (classic params or JSON DSL `body`) |
| `commit` | Issue a hard or soft commit |
| `optimize` | Merge segments (`/update?optimize=true`) |
| `create-collection` | Upload a configset then create a collection |
| `delete-collection` | Delete a collection (and optionally its configset) |
| `raw-request` | Issue an arbitrary HTTP request to the Solr V2 API |

## Telemetry devices

| Device | Metrics collected |
|---|---|
| `solr-jvm` | JVM heap used/max, GC count/time |
| `solr-node` | CPU load, free OS memory, query handler counts |
| `solr-collection` | Document count per collection |

## Result output

Results are written as JSON, CSV, and a plain-text summary under
`~/.solr-benchmark/results/<run-id>/` by default.

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[develop]"

# Run Solr-specific unit tests
python -m pytest tests/unit/solr/ -v
```

## License

Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.

This product includes software developed by the OpenSearch Contributors, and
prior to that by Elasticsearch (Rally). Full attribution is in [NOTICE](NOTICE).
