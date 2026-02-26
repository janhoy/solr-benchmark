---
title: Telemetry Devices
parent: Reference
nav_order: 45
---

# Telemetry Devices

Apache Solr Benchmark includes six telemetry devices for collecting server-side metrics. All devices are enabled automatically during a benchmark run. Enable specific devices with `--telemetry` at run time.

Both Solr 9.x (JSON format) and Solr 10.x (Prometheus text format) are supported. Format detection is automatic via the HTTP `Content-Type` header.

---

## solr-jvm-stats

Collects JVM statistics from each Solr node via the Solr metrics API.

**Enable:**
```bash
solr-benchmark run --telemetry solr-jvm-stats ...
```

**Metrics collected:**

| Metric | Unit | Description |
|--------|------|-------------|
| `jvm_heap_used_bytes` | bytes | JVM heap memory currently used |
| `jvm_heap_max_bytes` | bytes | Maximum JVM heap size |
| `jvm_gc_count` | count | Total GC collections across all collectors |
| `jvm_gc_time_ms` | ms | Total GC wall time across all collectors |
| `jvm_gc_young_count` | count | Young-generation GC collection count |
| `jvm_gc_young_time_ms` | ms | Young-generation GC wall time |
| `jvm_gc_old_count` | count | Old-generation GC collection count |
| `jvm_gc_old_time_ms` | ms | Old-generation GC wall time |
| `jvm_thread_count` | count | Current JVM thread count |
| `jvm_thread_peak_count` | count | Peak JVM thread count since startup |
| `jvm_buffer_pool_direct_bytes` | bytes | Direct byte buffer pool memory used |
| `jvm_buffer_pool_mapped_bytes` | bytes | Memory-mapped buffer pool memory used |

---

## solr-node-stats

Collects Solr node-level and OS statistics.

**Enable:**
```bash
solr-benchmark run --telemetry solr-node-stats ...
```

**Metrics collected:**

| Metric | Unit | Description |
|--------|------|-------------|
| `cpu_usage_percent` | % | Process CPU load (0–100) |
| `os_memory_free_bytes` | bytes | Free physical OS memory |
| `node_file_descriptors_open` | count | Currently open file descriptors |
| `node_file_descriptors_max` | count | Maximum allowed file descriptors |
| `node_http_requests_total` | count | Total HTTP requests processed by Jetty |
| `query_handler_requests_total` | count | Total `/select` query handler requests |
| `query_handler_errors_total` | count | Total `/select` query handler errors |
| `query_handler_avg_latency_ms` | ms | Rolling average `/select` request latency |

---

## solr-collection-stats

Collects per-collection document count, segment count, and deleted doc count.

**Enable:**
```bash
solr-benchmark run --telemetry solr-collection-stats ...
```

**Metrics collected** (all tagged with `collection` metadata):

| Metric | Unit | Description |
|--------|------|-------------|
| `num_docs` | docs | Current document count |
| `num_deleted_docs` | docs | Number of deleted (soft-deleted) documents |
| `segment_count` | count | Number of Lucene segments |
| `index_size_bytes` | bytes | Total index size on disk |

**Notes:** Collection stats are polled every 30 seconds (configurable). Uses both the Collections API and the Luke request handler (`/admin/luke`) for full statistics.

---

## solr-query-stats

Collects query latency percentiles and filter cache hit ratio.

**Enable:**
```bash
solr-benchmark run --telemetry solr-query-stats ...
```

**Metrics collected:**

| Metric | Unit | Description |
|--------|------|-------------|
| `query_latency_p50_ms` | ms | 50th percentile `/select` request latency |
| `query_latency_p99_ms` | ms | 99th percentile `/select` request latency |
| `query_latency_p999_ms` | ms | 99.9th percentile `/select` request latency |
| `query_requests_total` | count | Total `/select` handler request count |
| `query_errors_total` | count | Total `/select` handler error count |
| `query_cache_hit_ratio` | ratio | Filter cache hit ratio (0.0–1.0) |

---

## solr-indexing-stats

Collects update handler and merge metrics.

**Enable:**
```bash
solr-benchmark run --telemetry solr-indexing-stats ...
```

**Metrics collected:**

| Metric | Unit | Description |
|--------|------|-------------|
| `indexing_requests_total` | count | Total `/update` handler requests |
| `indexing_errors_total` | count | Total `/update` handler errors |
| `indexing_avg_time_ms` | ms | Rolling average `/update` request time |
| `index_merge_major_running` | count | Currently running major merges |
| `index_merge_minor_running` | count | Currently running minor merges |

---

## solr-cache-stats

Collects hit/miss/eviction and memory statistics for the three primary Solr caches.

**Enable:**
```bash
solr-benchmark run --telemetry solr-cache-stats ...
```

**Metrics collected** (all tagged with `cache` metadata: `queryResultCache`, `filterCache`, `documentCache`):

| Metric | Unit | Description |
|--------|------|-------------|
| `cache_hits_total` | count | Cache hits since Solr start |
| `cache_inserts_total` | count | Cache inserts since Solr start |
| `cache_evictions_total` | count | Cache evictions since Solr start |
| `cache_memory_bytes` | bytes | RAM used by this cache |
| `cache_hit_ratio` | ratio | Hit ratio (0.0–1.0) |

---

## Using multiple devices

```bash
solr-benchmark run \
  --telemetry solr-jvm-stats,solr-node-stats,solr-collection-stats,solr-query-stats,solr-indexing-stats,solr-cache-stats \
  ...
```

## Telemetry output location

Telemetry metrics are written to the same `results.json` file as workload metrics, under a `"telemetry"` key alongside the standard per-task metrics.
