---
title: Quickstart
nav_order: 2
---

# Quickstart

This guide walks you through installing Apache Solr Benchmark and running your first benchmark against an [Apache Solr](https://solr.apache.org) cluster.

## Prerequisites

- Python 3.10 or later
- A running Apache Solr cluster (or use the `docker` pipeline to start one automatically)
- Docker (only required for the `docker` pipeline)

## Installation

Clone the repository and install locally:

```bash
git clone https://github.com/janhoy/solr-benchmark.git
cd solr-benchmark
pip install -e .
```

Verify the installation:

```bash
solr-benchmark --version
```

{: .note }
Apache Solr Benchmark is not yet published on PyPI. A `pip install solr-benchmark` release is planned for the future.

## Running your first benchmark

### Using an existing Solr cluster (benchmark-only pipeline)

If you already have a Solr cluster running at `localhost:8983`, run the built-in `nyc_taxis` workload in test mode:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --test-mode
```

### Using the Docker pipeline

To let Apache Solr Benchmark start a Solr cluster for you:

```bash
solr-benchmark run \
  --pipeline docker \
  --distribution-version 9.10.1 \
  --workload nyc_taxis \
  --test-mode
```

## Understanding the output

After the run completes, a summary table is printed to the console:

```
-------------------------------
         Results Summary
-------------------------------
Test Execution ID: 20240115T120000Z

| Task        | 50th  | 90th  | 99th  |
|-------------|-------|-------|-------|
| bulk-index  | 12 ms | 18 ms | 25 ms |
| search      |  5 ms |  9 ms | 15 ms |

Throughput (docs/s):
  bulk-index: 4,500

Error rate:
  bulk-index: 0.00%
  search: 0.00%
```

Results are also saved as JSON and CSV files to `~/.solr-benchmark/results/`.

## Workloads

Pre-built workloads for Apache Solr Benchmark are available at [https://github.com/janhoy/solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads).

To list available workloads:

```bash
solr-benchmark list workloads
```

## Next steps

- [User Guide](user-guide/) — understand workloads, pipelines, and results
- [Converter Tool](converter/) — convert an existing OpenSearch Benchmark workload to Solr format
- [Reference](reference/) — complete CLI and workload format reference
