# Apache Solr Benchmark

Apache Solr Benchmark is a macrobenchmarking framework for [Apache Solr](https://solr.apache.org/).

It is a fork of [OpenSearch Benchmark](https://github.com/opensearch-project/opensearch-benchmark),
itself derived from [Elastic Rally](https://github.com/elastic/rally).

**DISCLAIMER**: Work in progress

**NOTE**: This is a pure Solr benchmarking tool. It does NOT support benchmarking OpenSearch or Elasticsearch clusters. OpenSearch compatibility is limited to workload import — you can convert existing OpenSearch Benchmark workloads to Solr format using the included migration utility.

## What is Apache Solr Benchmark?

If you are looking to performance test Apache Solr, this tool can help you with:

* Running performance benchmarks and recording results
* Setting up and tearing down Solr clusters for benchmarking (local distribution or Docker)
* Managing benchmark workloads (collections, configsets, search operations)
* Collecting JVM, node, and collection metrics via telemetry devices
* Track performance regressions over time
* Run some existing OSB/Rally workloads on Solr through auto conversion

## Quick Start

### Install

```bash
pip install -e .
```

**NOTE**: We do not offer the tool as a python package yet 

### Run a benchmark against a Solr version in Docker

```bash
solr-benchmark execute-test \
  --pipeline=docker \
  --distribution-version=9.10.1 \
  --workload=<your-workload> \
  --challenge=<challenge-name>
```

**Note**: Defaults to cloud mode (SolrCloud with embedded ZooKeeper).

### Provision Solr locally, then benchmark

```bash
solr-benchmark execute-test \
  --pipeline=from-distribution \
  --distribution-version=9.7.0 \
  --workload=<your-workload>
```

**Note**: Defaults to cloud mode (SolrCloud with embedded ZooKeeper).

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

Results are written to timestamped directories under `~/.solr-benchmark/results/` by default.

Each benchmark run creates a directory named `YYYYMMDD_HHMMSS_<run-id-prefix>/` containing:

- **test_run.json** — Complete canonical record of the benchmark run including:
  - Benchmark metadata (version, environment, pipeline, user tags)
  - Workload and test procedure information
  - Cluster configuration specification (heap size, GC settings, all variables)
  - Distribution version and flavor
  - Detailed operation metrics (throughput, latency, error rates)
  - System metrics (GC times, merge times, segment counts, etc.)
- **results.csv** — Flattened CSV export of key metrics for spreadsheet analysis
- **summary.txt** — Human-readable markdown table (also printed to console)

### Time-Series Analysis

The `test_run.json` file includes complete cluster-config specification, making it easy to:
- Compare performance across different configurations (4GB heap vs 8GB heap)
- Filter and group results by configuration in a results portal/dashboard
- Correlate configuration changes with performance changes
- Track performance trends over time with custom user tags (`--user-tag "key:value"`)

### Example: Analyzing Results

```bash
# Run benchmark with specific config and tag
solr-benchmark run --cluster-config 4gheap --user-tag "baseline:true" \
  --workload nyc_taxis --test-mode

# Results stored in ~/.solr-benchmark/results/20260222_143052_a34ff090/
# Inspect complete metadata:
cat ~/.solr-benchmark/results/20260222_143052_a34ff090/test_run.json | jq .

# Extract cluster-config specification:
cat ~/.solr-benchmark/results/20260222_143052_a34ff090/test_run.json | \
  jq '."cluster-config-spec"'

# Extract throughput metrics:
cat ~/.solr-benchmark/results/20260222_143052_a34ff090/test_run.json | \
  jq '.results.op_metrics[] | {task, throughput}'
```

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
