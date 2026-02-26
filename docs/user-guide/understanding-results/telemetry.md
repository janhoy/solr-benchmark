---
title: Enabling Telemetry
parent: Understanding Results
grand_parent: User Guide
nav_order: 30
---

# Enabling Telemetry

Apache Solr Benchmark can collect server-side metrics from your Solr cluster during a benchmark run using *telemetry devices*. These devices capture JVM, node, query, indexing, cache, and collection-level statistics.

## Enabling telemetry devices

Pass `--telemetry` with a comma-separated list of device names:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --telemetry solr-jvm-stats,solr-node-stats,solr-query-stats
```

All six devices are enabled by default during a benchmark run (no flag required).

## Available devices

| Device | Description |
|--------|-------------|
| `solr-jvm-stats` | JVM heap, GC pause times, GC counts, threads, buffer pools |
| `solr-node-stats` | CPU, OS memory, file descriptors, HTTP requests, query handler metrics |
| `solr-collection-stats` | Per-collection document counts, deleted docs, segment counts, index size |
| `solr-query-stats` | Query latency percentiles (p50/p99/p99.9), request counts, cache hit ratios |
| `solr-indexing-stats` | Indexing throughput, error counts, merge activity |
| `solr-cache-stats` | Per-cache hit/miss/eviction counts and memory usage |

See [Telemetry Devices](../../reference/telemetry.html) for full device documentation and all metric names.

## Telemetry output

Telemetry metrics are included in the `results.json` file alongside the workload operation metrics. They are also printed as additional rows in the console summary table.

## Telemetry and the benchmark-only pipeline

Telemetry devices query the Solr metrics API on the target host(s). They work with all pipelines, including `benchmark-only`, as long as the target hosts are reachable and the Solr metrics API is enabled (it is enabled by default).

## Solr version compatibility

Both Solr 9.x and Solr 10.x expose metrics at `/solr/admin/metrics`. The response format differs: Solr 9.x returns custom JSON, Solr 10.x returns Prometheus text format. Apache Solr Benchmark auto-detects the format via the HTTP `Content-Type` header at runtime. No configuration is required.
