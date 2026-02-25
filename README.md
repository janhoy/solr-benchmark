# Apache Solr Benchmark

Apache Solr Benchmark is a macrobenchmarking framework for [Apache Solr](https://solr.apache.org/).

It is a fork of [OpenSearch Benchmark](https://github.com/opensearch-project/opensearch-benchmark),
itself derived from [Elastic Rally](https://github.com/elastic/rally).

**DISCLAIMER**: Work in progress

**NOTE**: This is a pure Solr benchmarking tool. It does NOT support benchmarking OpenSearch or Elasticsearch clusters. OpenSearch compatibility is limited to workload import — you can convert existing OpenSearch Benchmark workloads to Solr format using the included `convert-workload` command.

## Documentation

Full documentation is available at **[https://janhoy.github.io/solr-benchmark/](https://janhoy.github.io/solr-benchmark/)**.

The documentation source lives in the [`docs/`](docs/) folder of this repository.

## What is Apache Solr Benchmark?

If you are looking to performance test Apache Solr, this tool can help you with:

* Running performance benchmarks and recording results
* Setting up and tearing down Solr clusters for benchmarking (local distribution, build-from-source or Docker, including nightly builds)
* Managing benchmark workloads (collections, configsets, search operations)
* Run same workload against multiple Solr versions or multiple cluster-configurations (heap size, GC settings, etc.)
* Collecting JVM, node, and collection metrics via telemetry devices
* Output results for each run in JSON format, suitable for analysis and dashboarding
* Assist in converting existing OpenSearch Benchmark workloads to Solr format

## Quick Start

### Install

**NOTE**: We do not offer the tool as a python package yet

```bash
pip install -e .
```

### Run a benchmark against a Solr version in Docker

```bash
solr-benchmark run \
  --pipeline=docker \
  --distribution-version=9.10.1 \
  --workload=geonames \
  --test-mode
```

**Note**: Defaults to cloud mode (SolrCloud with embedded ZooKeeper).

### Provision Solr locally, then benchmark

```bash
solr-benchmark run \
  --pipeline=from-distribution \
  --distribution-version=9.7.0 \
  --workload=geonames \
  --test-mode
```

**Note**: Always uses cloud mode (SolrCloud with embedded ZooKeeper).

### Provision Solr via Docker, then benchmark

```bash
solr-benchmark run \
  --pipeline=docker \
  --distribution-version=9.7.0 \
  --workload=geonames \
  --test-mode
```

### Convert an existing OSB workload to Solr format

```bash
solr-benchmark convert-workload \
  --workload-path /path/to/osb-workload \
  --output-path /path/to/solr-workload
```

See the [Converter Tool documentation](https://janhoy.github.io/solr-benchmark/converter/) for details on what is converted automatically and what requires manual review.

## Workload format

See [Workload Reference](https://janhoy.github.io/solr-benchmark/reference/workloads/) in the documentation for the full `workload.json` format, including `collections`, `corpora`, `operations`, and `test-procedures`.

Pre-built workloads are available at [https://github.com/janhoy/solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads).

## Telemetry devices

| Device | Metrics collected |
|---|---|
| `solr-jvm-stats` | JVM heap used/max, GC count/time |
| `solr-node-stats` | CPU load, free OS memory, query handler counts |
| `solr-collection-stats` | Document count, index size, segment count per collection |

See [Telemetry Devices](https://janhoy.github.io/solr-benchmark/reference/telemetry) for full device documentation.

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
