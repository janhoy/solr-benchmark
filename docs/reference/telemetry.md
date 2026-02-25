---
title: Telemetry Devices
parent: Reference
nav_order: 45
---

# Telemetry Devices

Apache Solr Benchmark includes the following telemetry devices for collecting server-side metrics. Enable them with `--telemetry` at run time.

## solr-jvm-stats

Collects JVM statistics from each Solr node via the Solr metrics API.

**Enable:**
```bash
solr-benchmark run --telemetry solr-jvm-stats ...
```

**Metrics collected:**
- Heap memory used and max (bytes)
- GC pause time (ms) per collector (G1 Young Generation, G1 Old Generation, etc.)
- GC collection count

**Notes:** Compatible with both Solr 9.x and Solr 10.x.

---

## solr-node-stats

Collects Solr node-level statistics from the Solr metrics API.

**Enable:**
```bash
solr-benchmark run --telemetry solr-node-stats ...
```

**Metrics collected:**
- HTTP request rate (requests/s)
- HTTP request latency percentiles (ms)
- Query cache hit ratio
- Filter cache hit ratio
- Document cache hit ratio
- System CPU load

**Notes:** Queries the `/solr/admin/metrics` (Solr 9.x) or `/api/node/metrics` (Solr 10.x) endpoint. The correct endpoint is auto-detected at runtime.

---

## solr-collection-stats

Collects per-collection statistics.

**Enable:**
```bash
solr-benchmark run --telemetry solr-collection-stats ...
```

**Metrics collected:**
- Document count per collection
- Index size in bytes
- Number of Lucene segments
- Shard and replica distribution

**Notes:** Queries the Solr Collections API for collection state information.

---

## Using multiple devices

```bash
solr-benchmark run \
  --telemetry solr-jvm-stats,solr-node-stats,solr-collection-stats \
  ...
```

## Telemetry output location

Telemetry metrics are written to the same `results.json` file as workload metrics, under a `"telemetry"` key alongside the standard per-task metrics.
