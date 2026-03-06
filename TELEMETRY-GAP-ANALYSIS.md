# Solr Telemetry Gap Analysis

## Executive Summary

**Current Status**: Solr telemetry has 6 devices covering ~40% of OpenSearch telemetry capabilities.

**Goal**: Achieve feature parity with OpenSearch telemetry to enable comprehensive performance analysis.

---

## Current Implementation

### Solr Telemetry Devices (6 total):

1. **SolrJvmStats** - JVM heap and GC metrics
   - ✅ jvm_heap_used_bytes
   - ✅ jvm_heap_max_bytes
   - ✅ jvm_gc_count
   - ✅ jvm_gc_time_ms

2. **SolrNodeStats** - OS and query handler metrics
   - ✅ cpu_usage_percent
   - ✅ os_memory_free_bytes
   - ✅ query_handler_requests_total
   - ✅ query_handler_errors_total

3. **SolrCollectionStats** - Collection-level metrics
   - ✅ num_docs (per collection)
   - ✅ index_size_bytes (per collection)
   - ✅ segment_count (per collection)

4. **SolrQueryStats** - Query performance metrics
   - ✅ query latency percentiles (p50, p75, p95, p99)
   - ✅ per-handler request/error counts
   - ✅ query result cache stats

5. **SolrIndexingStats** - Indexing performance metrics
   - ✅ indexing rate (docs/sec)
   - ✅ update handler errors
   - ✅ merge statistics

6. **SolrCacheStats** - Cache hit/miss metrics
   - ✅ query cache, filter cache, document cache
   - ✅ hit/miss rates and eviction counts
   - ✅ memory usage per cache

---

## OpenSearch Telemetry Devices (14 total)

### ✅ Implemented in Solr:
1. **SolrNodeStats** - CPU, memory, query handler metrics
2. **SolrJvmStats** - JVM heap and GC metrics
3. **SolrCollectionStats** - Doc counts, index size, segment count
4. **SolrQueryStats** - Query latency percentiles, per-handler counts
5. **SolrIndexingStats** - Indexing rate, merge stats, errors
6. **SolrCacheStats** - Cache hit/miss/eviction stats

### ❌ Not Yet Implemented:
7. **FlightRecorder** - Java Flight Recorder profiling
8. **JitCompiler** - JIT compilation stats
9. **Gc** - Advanced per-collector GC analysis
10. **Heapdump** - Heap dump on demand
11. **SolrSegmentStats** - Detailed Lucene segment breakdown
12. **SolrShardStats** - Per-shard metrics
13. **SolrReplicationStats** - SolrCloud replication lag
14. **StartupTime** - Startup duration tracking
15. **DiskIo** - OS-level disk I/O statistics
16. **ClusterEnvironmentInfo** - Cluster metadata

### N/A for Solr:
- **CcrStats** - Solr uses SolrCloud replication instead
- **TransformStats** - No equivalent in Solr
- **SearchableSnapshotsStats** - Different mechanism in Solr

---

## Detailed Gap Analysis

### Category 1: JVM & Process Metrics

| Metric | OpenSearch | Solr | Gap | Solr API |
|--------|-----------|------|-----|----------|
| **JVM Heap** | ✅ Full details | ✅ Basic (used/max) | ⚠️ Missing pools breakdown | `/admin/metrics` → `solr.jvm` |
| **JVM GC** | ✅ Per-collector details | ✅ Aggregated only | ⚠️ Missing per-collector | `/admin/metrics` → `solr.jvm.gc.*` |
| **JVM Threads** | ✅ Thread pools | ❌ None | ❌ Missing entirely | `/admin/metrics` → `solr.jvm.threads.*` |
| **JVM Buffer Pools** | ✅ Direct/mapped | ❌ None | ❌ Missing | `/admin/metrics` → `solr.jvm.buffers.*` |
| **Process CPU** | ✅ Detailed | ✅ Basic | ⚠️ Missing time breakdown | `/api/node/system` |
| **File Descriptors** | ✅ Open/max | ❌ None | ❌ Missing | `/admin/metrics` → `solr.node.*` |

### Category 2: Index & Segment Metrics

| Metric | OpenSearch | Solr | Gap | Solr API |
|--------|-----------|------|-----|----------|
| **Segment Count** | ✅ Per-index | ✅ Per-collection | ✅ Covered | CLUSTERSTATUS |
| **Segment Size** | ✅ Detailed | ⚠️ Aggregate only | ⚠️ Missing breakdown | `/admin/luke` per-core |
| **Segment Memory** | ✅ Detailed | ❌ None | ❌ Missing | `/admin/luke` → `index.sizeInBytes` |
| **Doc Count** | ✅ Per-index | ✅ Per-collection | ✅ Covered | CLUSTERSTATUS |
| **Deleted Docs** | ✅ Tracked | ❌ None | ❌ Missing | `/admin/luke` → `index.numDocs` vs `index.maxDoc` |
| **Index Size** | ✅ Detailed | ✅ Basic | ⚠️ Missing breakdown | CLUSTERSTATUS |

### Category 3: Query & Indexing Performance

| Metric | OpenSearch | Solr | Gap | Solr API |
|--------|-----------|------|-----|----------|
| **Query Requests** | ✅ Per-node | ✅ Per-handler | ✅ Covered | `/admin/metrics` → `QUERY.*` |
| **Query Errors** | ✅ Tracked | ✅ Per-handler | ✅ Covered | `/admin/metrics` → `QUERY.*.errors` |
| **Query Latency** | ✅ Percentiles | ✅ Percentiles (p50/p99) | ✅ Covered | `/admin/metrics` → `QUERY.*.requestTimes.*` |
| **Indexing Rate** | ✅ Detailed | ✅ Basic | ⚠️ Missing detailed breakdown | `/admin/metrics` → `UPDATE.*` |
| **Indexing Errors** | ✅ Tracked | ✅ Tracked | ✅ Covered | `/admin/metrics` → `UPDATE.*.errors` |
| **Merge Stats** | ✅ Detailed | ✅ Basic | ⚠️ Missing detailed breakdown | `/admin/metrics` → `INDEX.merge.*` |
| **Refresh Stats** | ✅ Tracked | ❌ None | ❌ Missing | `/admin/mbeans` |

### Category 4: Memory & Cache

| Metric | OpenSearch | Solr | Gap | Solr API |
|--------|-----------|------|-----|----------|
| **Query Cache** | ✅ Hit/miss/size | ✅ Hit/miss/eviction | ⚠️ Missing size bytes | `/admin/metrics` → `CACHE.queryResultCache.*` |
| **Filter Cache** | ✅ Hit/miss/size | ✅ Hit/miss/eviction | ⚠️ Missing size bytes | `/admin/metrics` → `CACHE.filterCache.*` |
| **Document Cache** | ✅ Tracked | ✅ Hit/miss/eviction | ⚠️ Missing size bytes | `/admin/metrics` → `CACHE.documentCache.*` |
| **Circuit Breakers** | ✅ Trip counts | N/A | N/A | Solr doesn't have circuit breakers |
| **Fielddata** | ✅ Size/evictions | N/A | N/A | Solr uses docValues differently |

### Category 5: Network & Transport

| Metric | OpenSearch | Solr | Gap | Solr API |
|--------|-----------|------|-----|----------|
| **HTTP Requests** | ✅ Count/size | ⚠️ Query only | ⚠️ Missing admin/update | `/admin/metrics` → Jetty metrics |
| **Network RX/TX** | ✅ Bytes | ❌ None | ❌ Missing | `/api/node/system` → `systemLoadAverage` (indirect) |
| **Connection Count** | ✅ Tracked | ❌ None | ❌ Missing | Jetty metrics via `/admin/metrics` |

### Category 6: Shard & Replication

| Metric | OpenSearch | Solr | Gap | Solr API |
|--------|-----------|------|-----|----------|
| **Shard State** | ✅ Per-shard | ❌ None | ❌ Missing | CLUSTERSTATUS → `shards` |
| **Recovery Progress** | ✅ Tracked | ❌ None | ❌ Missing | REQUESTRECOVERYSTATUS |
| **Replication Lag** | ✅ Tracked | ❌ None | ❌ Missing | REPLICATIONDETAILS per-replica |
| **Leader Election** | ✅ Events | ❌ None | ❌ Missing | CLUSTERSTATUS + live_nodes |

---

## Solr API Endpoints for Telemetry

### Primary APIs:

1. **`/admin/metrics`** (Solr 9.x JSON / Solr 10.x Prometheus)
   - JVM metrics (heap, GC, threads, buffers)
   - Query handler metrics (requests, errors, latency)
   - Update handler metrics
   - Cache metrics (query cache, filter cache, document cache)
   - Index metrics (merge stats, segment stats)

2. **`/api/node/system`** (V2 API)
   - OS metrics (CPU, memory, swap)
   - File descriptors
   - System load

3. **`/solr/admin/collections?action=CLUSTERSTATUS`**
   - Collection list and states
   - Shard distribution
   - Replica states
   - Live nodes

4. **`/solr/<collection>/admin/luke`** (per-core)
   - Detailed segment info
   - Index statistics
   - Field information

5. **`/solr/<collection>/admin/mbeans?cat=CACHE`**
   - Cache statistics details
   - Hit/miss rates
   - Eviction counts

6. **`/solr/admin/info/system`**
   - Solr version
   - JVM info
   - System properties

### Solr-Specific APIs (not in OpenSearch):

- **`/solr/admin/collections?action=REPLICATIONDETAILS`** - Replication lag
- **`/solr/admin/collections?action=REQUESTRECOVERYSTATUS`** - Recovery tracking
- **`/solr/<collection>/replication?command=details`** - Per-replica replication

---

## Implementation Priority

### Phase 1: Core Metrics — ✅ COMPLETE

All Phase 1 devices are implemented in `osbenchmark/solr/telemetry.py`:

1. ✅ **SolrJvmStats** - JVM heap (used/max) and GC (count/time)
2. ✅ **SolrNodeStats** - CPU, OS memory, query handler request/error counts
3. ✅ **SolrCollectionStats** - Doc counts, index size, segment count per collection
4. ✅ **SolrQueryStats** - Query latency percentiles (p50/p75/p95/p99), per-handler counts
5. ✅ **SolrIndexingStats** - Indexing rate, update handler errors, merge statistics
6. ✅ **SolrCacheStats** - Query/filter/document cache hit rates, eviction counts, memory usage

### Phase 2: Advanced Metrics (Medium Priority)

7. **Shard-Level Stats** - Per-shard doc counts, sizes, states
   - API: CLUSTERSTATUS + per-core APIs
   - Effort: High (requires per-shard iteration)

8. **Segment Details** - Detailed segment breakdown (deleted docs, memory usage)
   - API: `/admin/luke` per core
   - Effort: Medium

9. **Replication Lag** - Track leader/replica sync
   - API: REPLICATIONDETAILS
   - Effort: Medium

10. **Enhanced JVM Stats** - Thread pools, buffer pools, per-collector GC
    - API: `/admin/metrics` → `solr.jvm.*`
    - Effort: Medium

### Phase 3: Operational Tools (Lower Priority)

11. **StartupTime** - Internal device (no API changes)
    - Effort: Low (framework already exists)

12. **DiskIo** - Internal device (OS-level stats)
    - Effort: Low (framework already exists)

13. **Heapdump** - On-demand heap dumps
    - Effort: Medium (requires JMX or custom endpoint)

### Out of Scope (N/A for Solr):

- **CCR Stats** - Solr doesn't have CCR (uses SolrCloud replication)
- **Transform Stats** - No equivalent in Solr
- **Circuit Breakers** - Solr doesn't have circuit breakers (uses different backpressure)

---

## Implementation Strategy

### 1. Extend Existing Devices (Phase 2)

**SolrNodeStats** → Could add:
- Thread pool metrics
- Buffer pool metrics
- Detailed GC stats (per collector)
- File descriptor counts

**SolrCollectionStats** → Could add:
- Deleted document counts (via `/admin/luke`)
- Segment memory usage
- Per-shard breakdown (optional)

### 2. New Devices to Create (Phase 2)

**SolrShardStats** (optional, high cost):
- Per-shard document counts
- Per-shard index sizes
- Replica sync status

**SolrReplicationStats** (optional):
- Leader-replica lag
- Replication errors
- Recovery progress

### 3. Implemented Devices (Phase 1 — Complete)

All 6 devices are in `osbenchmark/solr/telemetry.py`:

```python
class SolrJvmStats     # JVM heap and GC metrics
class SolrNodeStats    # OS CPU, memory, query handler counts
class SolrCollectionStats  # Doc counts, index size, segment count
class SolrQueryStats   # Query latency percentiles, per-handler counts
class SolrIndexingStats    # Indexing rate, merge stats, errors
class SolrCacheStats   # Query/filter/document cache hit rates
```

### 4. Testing Strategy

- Unit tests for metric parsing (JSON vs Prometheus) — **pending** (see TODO.md)
- Integration tests with live Solr 9.x and 10.x
- Verify metric names match OpenSearch conventions
- Test with multi-node SolrCloud clusters

---

## Compatibility Notes

### Solr Version Differences:

- **Solr 9.x**: `/admin/metrics` returns custom JSON
- **Solr 10.x**: `/admin/metrics` returns Prometheus text format
- **Solution**: Dual parsers (already implemented in base class)

### SolrCloud vs Standalone:

- Some metrics (replication, shards) only apply to SolrCloud
- Devices should gracefully handle standalone mode
- Use capability detection (check CLUSTERSTATUS response)

---

## Open Questions

1. **Metric Naming**: Should we use Solr-native names or translate to OpenSearch conventions?
   - **Recommendation**: Translate to OpenSearch names for consistency

2. **Sampling Strategy**: Should we poll all cores or sample?
   - **Recommendation**: Sample for large clusters, make configurable

3. **Per-Core vs Per-Collection**: Should we aggregate or report per-core?
   - **Recommendation**: Per-collection by default, per-core optional

4. **Backward Compatibility**: Support Solr versions < 9.x?
   - **Recommendation**: Solr 9.x+ only (matches current implementation)

---

## Next Steps

1. ✅ Complete gap analysis (this document)
2. ✅ Implement Phase 1 devices (SolrQueryStats, SolrIndexingStats, SolrCacheStats)
3. ⬜ Add unit tests for all 6 telemetry devices
4. ⬜ Test with NYC taxis workload + telemetry enabled on multi-node cluster
5. ⬜ Document telemetry usage in DEVELOPER_GUIDE.md
6. ⬜ Consider Phase 2 implementation based on user feedback

---

## References

- Solr Metrics API: https://solr.apache.org/guide/metrics-reporting.html
- Solr Admin APIs: https://solr.apache.org/guide/collections-api.html
- OpenSearch Benchmark Telemetry: https://opensearch.org/docs/latest/benchmark/
