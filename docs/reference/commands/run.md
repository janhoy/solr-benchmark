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

## Common options

| Option | Description |
|--------|-------------|
| `--pipeline` | Pipeline to use: `benchmark-only`, `docker`, `from-distribution`, `from-sources` (default: `benchmark-only`) |
| `--target-hosts` | Comma-separated list of Solr `host:port` targets |
| `--workload` | Named workload from the workloads repository |
| `--workload-path` | Path to a local workload directory |
| `--challenge` | Challenge (test procedure) to run (default: the workload's default challenge) |
| `--test-mode` | Run a shortened version of the workload (≤1,000 docs) |
| `--workload-params` | Override workload parameters (comma-separated `key:value` pairs) |
| `--distribution-version` | Solr version (e.g., `9.10.1`) for `docker`/`from-distribution` pipelines |
| `--cluster-config` | Cluster configuration preset for `docker`/`from-distribution`/`from-sources` pipelines |
| `--telemetry` | Comma-separated list of telemetry devices to enable |
| `--telemetry-params` | Parameters for telemetry devices |
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
