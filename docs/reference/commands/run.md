---
title: run
parent: Command Reference
grand_parent: Reference
nav_order: 90
---

# run

Runs a benchmark workload.

## Syntax

```bash
solr-benchmark run [OPTIONS]
```

## Workload selection

| Option | Description |
|--------|-------------|
| `--workload` | Named workload from the workloads repository |
| `--workload-path` | Path to a local workload directory |
| `--workload-repository` | Git URL for the workloads repository (default: the configured repository) |
| `--workload-revision` | Git revision (branch, tag, or commit) of the workloads repository |
| `--workload-params` | Override workload Jinja2 parameters (comma-separated `key:value` pairs) |
| `--challenge` | Challenge (test procedure) to run (default: the workload's default challenge) |
| `--include-tasks` | Comma-separated list of task names to run; all other tasks are skipped |
| `--exclude-tasks` | Comma-separated list of task names to skip |
| `--enable-assertions` | Enable task-level assertions defined in the workload |

## Cluster and pipeline

| Option | Description |
|--------|-------------|
| `--pipeline` | Pipeline to use: `benchmark-only`, `docker`, `from-distribution`, `from-sources` (default: `benchmark-only`) |
| `--target-hosts` | Comma-separated list of Solr `host:port` targets |
| `--distribution-version` | Solr version (e.g., `9.10.1`) for `docker`/`from-distribution` pipelines |
| `--cluster-config` | Cluster configuration preset for `docker`/`from-distribution`/`from-sources` pipelines |

## Distributed load generation

| Option | Description |
|--------|-------------|
| `--worker-ips` | Comma-separated IP addresses of worker coordinator machines for distributed load generation (default: `localhost`) |

## Telemetry

| Option | Description |
|--------|-------------|
| `--telemetry` | Comma-separated list of telemetry devices to enable |
| `--telemetry-params` | Key-value parameters for telemetry devices |

## Result output

| Option | Description |
|--------|-------------|
| `--test-execution-id` | Custom unique ID for this run (auto-generated if omitted); used with `compare` |
| `--user-tag` | Comma-separated `key:value` metadata attached to the run (e.g., `intention:baseline,heap:4g`) |
| `--results-format` | Output format: `markdown` (default) or `csv` |
| `--results-number-align` | Column alignment in the summary table: `right` (default), `left`, or `center` |
| `--results-file` | Write the summary table to a file in addition to the default location |
| `--show-in-results` | Which values to include in output: `available` (default), `all-percentiles`, or `all` |

## General

| Option | Description |
|--------|-------------|
| `--test-mode` | Run a shortened version of the workload (≤1,000 docs) for quick validation |
| `--on-error` | Error handling: `continue` (default), `abort` |
| `--quiet` | Suppress console output |

## Examples

```bash
# Benchmark an existing cluster
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --test-mode

# Docker pipeline with Solr 9.10.1
solr-benchmark run \
  --pipeline docker \
  --distribution-version 9.10.1 \
  --workload nyc_taxis

# Custom workload with parameter overrides
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload-path /path/to/my-workload \
  --workload-params "bulk_size:1000,clients:8"

# With telemetry
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --telemetry solr-jvm-stats,solr-node-stats
```

## See also

- [Pipelines overview](../../user-guide/concepts.md#pipelines)
- [Cluster Config](../../cluster-config/)
