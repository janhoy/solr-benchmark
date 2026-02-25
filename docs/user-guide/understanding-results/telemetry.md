---
title: Enabling Telemetry
parent: Understanding Results
grand_parent: User Guide
nav_order: 30
---

# Enabling Telemetry

Apache Solr Benchmark can collect server-side metrics from your Solr cluster during a benchmark run using *telemetry devices*. These devices capture JVM, node, and collection-level statistics.

## Enabling telemetry devices

Pass `--telemetry` with a comma-separated list of device names:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --telemetry solr-jvm-stats,solr-node-stats
```

## Available devices

| Device | Description |
|--------|-------------|
| `solr-jvm-stats` | JVM heap usage, GC pause times, GC counts |
| `solr-node-stats` | Request rates, cache hit ratios, CPU load |
| `solr-collection-stats` | Per-collection document counts, segment counts, index size |

See [Telemetry Devices](../../reference/telemetry.html) for full device documentation.

## Telemetry output

Telemetry metrics are included in the `results.json` file alongside the workload operation metrics. They are also printed as additional rows in the console summary table.

## Telemetry and the benchmark-only pipeline

Telemetry devices query the Solr metrics API on the target host(s). They work with all pipelines, including `benchmark-only`, as long as the target hosts are reachable and the Solr metrics API is enabled (it is enabled by default).

Solr 9.x and 10.x use different metrics API formats; Apache Solr Benchmark auto-detects the version at runtime.
