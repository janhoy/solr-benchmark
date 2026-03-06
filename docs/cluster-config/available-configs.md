---
title: Available Configs
parent: Cluster Config
nav_order: 2
---

# Available Cluster Configs

## defaults

No overrides applied. Solr uses its built-in default settings.

```
SOLR_HEAP: (Solr default, typically 512m)
```

**Usage:**
```bash
solr-benchmark run --cluster-config defaults ...
```

---

## 1gheap

Sets the Solr JVM heap to 1 GB. Suitable for small workloads and testing.

```
SOLR_HEAP: 1g
```

**Usage:**
```bash
solr-benchmark run --cluster-config 1gheap ...
```

---

## 4gheap

Sets the Solr JVM heap to 4 GB. Suitable for larger workloads.

```
SOLR_HEAP: 4g
```

**Usage:**
```bash
solr-benchmark run --cluster-config 4gheap ...
```

---

## g1gc

Enables the G1 garbage collector with tuned settings and a 4 GB heap. Recommended for latency-sensitive benchmarks.

```
SOLR_HEAP: 4g
GC_TUNE: -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:G1ReservePercent=15 \
         -XX:InitiatingHeapOccupancyPercent=75
```

**Usage:**
```bash
solr-benchmark run --cluster-config g1gc ...
```

---

## parallelgc

Enables the Parallel (throughput-optimized) garbage collector with a 4 GB heap.

```
SOLR_HEAP: 4g
GC_TUNE: -XX:+UseParallelGC -XX:MaxGCPauseMillis=200
```

**Usage:**
```bash
solr-benchmark run --cluster-config parallelgc ...
```

---

## Comparing configs

To compare G1GC vs Parallel GC on the same workload:

```bash
# Run 1: G1GC
solr-benchmark run \
  --pipeline docker \
  --distribution-version 9.10.1 \
  --workload nyc_taxis \
  --cluster-config g1gc

# Run 2: Parallel GC
solr-benchmark run \
  --pipeline docker \
  --distribution-version 9.10.1 \
  --workload nyc_taxis \
  --cluster-config parallelgc

# Compare results
solr-benchmark compare \
  --baseline <g1gc-run-id> \
  --contender <parallelgc-run-id>
```
