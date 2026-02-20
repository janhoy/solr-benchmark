# Solr Telemetry Gap Analysis

## Executive Summary

**Current Status**: Solr telemetry has 3 basic devices covering ~15% of OpenSearch telemetry capabilities.

**Goal**: Achieve feature parity with OpenSearch telemetry to enable comprehensive performance analysis.

---

## Current Implementation

### Solr Telemetry Devices (3 total):

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

---

## OpenSearch Telemetry Devices (14 total)

### ✅ Implemented in Solr (partial):
1. **NodeStats** - Partial (basic CPU/memory only)
2. **JVM Stats** - Partial (basic heap/GC only)

### ❌ Missing from Solr:
3. **FlightRecorder** - Java Flight Recorder profiling
4. **JitCompiler** - JIT compilation stats
5. **Gc** - Advanced garbage collection analysis
6. **Heapdump** - Heap dump on demand
7. **SegmentStats** - Lucene segment details
8. **CcrStats** - Cross-cluster replication (N/A for Solr)
9. **RecoveryStats** - Shard recovery tracking
10. **ShardStats** - Per-shard metrics
11. **TransformStats** - Data transforms (N/A for Solr)
12. **SearchableSnapshotsStats** - Snapshot stats (different in Solr)
13. **StartupTime** - Startup duration tracking
14. **DiskIo** - Disk I/O statistics
15. **ClusterEnvironmentInfo** - Cluster metadata

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
| **Query Requests** | ✅ Per-node | ✅ Aggregate | ⚠️ Missing per-handler | `/admin/metrics` → `QUERY.*` |
| **Query Errors** | ✅ Tracked | ✅ Aggregate | ⚠️ Missing per-handler | `/admin/metrics` → `QUERY.*.errors` |
| **Query Latency** | ✅ Percentiles | ❌ None | ❌ Missing | `/admin/metrics` → `QUERY.*.requestTimes.*` |
| **Indexing Rate** | ✅ Detailed | ❌ None | ❌ Missing | `/admin/metrics` → `UPDATE.*` |
| **Indexing Errors** | ✅ Tracked | ❌ None | ❌ Missing | `/admin/metrics` → `UPDATE.*.errors` |
| **Merge Stats** | ✅ Detailed | ❌ None | ❌ Missing | `/admin/metrics` → `INDEX.merge.*` |
| **Refresh Stats** | ✅ Tracked | ❌ None | ❌ Missing | `/admin/mbeans` |

### Category 4: Memory & Cache

| Metric | OpenSearch | Solr | Gap | Solr API |
|--------|-----------|------|-----|----------|
| **Query Cache** | ✅ Hit/miss/size | ❌ None | ❌ Missing | `/admin/metrics` → `CACHE.*.stats` |
| **Filter Cache** | ✅ Hit/miss/size | ❌ None | ❌ Missing | `/admin/metrics` → `CACHE.filterCache.*` |
| **Doc Values Cache** | ✅ Tracked | ❌ None | ❌ Missing | `/admin/metrics` → `CACHE.*` |
| **Circuit Breakers** | ✅ Trip counts | ❌ None | ❌ Missing | N/A (Solr doesn't have equivalent) |
| **Fielddata** | ✅ Size/evictions | ❌ None | ❌ Missing | `/admin/metrics` → `CACHE.*` |

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

### Phase 1: Critical Gaps (High Priority)
**Goal**: Expand NodeStats to match OpenSearch parity

1. **Enhanced JVM Stats** - Thread pools, buffer pools, detailed GC
   - API: `/admin/metrics` → `solr.jvm.*`
   - Effort: Medium (parsing existing API)

2. **Query Latency Metrics** - Percentiles (p50, p99, p999)
   - API: `/admin/metrics` → `QUERY.*.requestTimes.*`
   - Effort: Medium (histogram parsing)

3. **Indexing Metrics** - Rate, errors, merge stats
   - API: `/admin/metrics` → `UPDATE.*`, `INDEX.merge.*`
   - Effort: Medium

4. **Cache Metrics** - Hit/miss rates, sizes, evictions
   - API: `/admin/metrics` → `CACHE.*`
   - Effort: Low

### Phase 2: Advanced Metrics (Medium Priority)

5. **Shard-Level Stats** - Per-shard doc counts, sizes, states
   - API: CLUSTERSTATUS + per-core APIs
   - Effort: High (requires per-shard iteration)

6. **Segment Details** - Detailed segment breakdown
   - API: `/admin/luke` per core
   - Effort: Medium

7. **Replication Lag** - Track leader/replica sync
   - API: REPLICATIONDETAILS
   - Effort: Medium

8. **HTTP/Network Stats** - Request counts, sizes
   - API: Jetty metrics via `/admin/metrics`
   - Effort: Low

### Phase 3: Operational Tools (Lower Priority)

9. **StartupTime** - Internal device (no API changes)
   - Effort: Low (framework already exists)

10. **DiskIo** - Internal device (OS-level stats)
    - Effort: Low (framework already exists)

11. **Heapdump** - On-demand heap dumps
    - Effort: Medium (requires JMX or custom endpoint)

### Out of Scope (N/A for Solr):

- **CCR Stats** - Solr doesn't have CCR (uses SolrCloud replication)
- **Transform Stats** - No equivalent in Solr
- **Circuit Breakers** - Solr doesn't have circuit breakers (uses different backpressure)

---

## Implementation Strategy

### 1. Extend Existing Devices

**SolrNodeStats** → Add:
- Thread pool metrics
- Buffer pool metrics
- Detailed GC stats (per collector)
- File descriptor counts
- Network transport stats

**SolrCollectionStats** → Add:
- Deleted document counts
- Segment memory usage
- Per-shard breakdown (optional)

### 2. New Devices to Create

**SolrQueryStats**:
- Query latency percentiles
- Per-handler request/error counts
- Query result cache hit rates

**SolrIndexingStats**:
- Indexing rate (docs/sec)
- Update handler errors
- Merge statistics
- Refresh statistics

**SolrCacheStats**:
- Query cache, filter cache, document cache
- Hit/miss rates
- Eviction counts
- Memory usage

**SolrShardStats** (optional, high cost):
- Per-shard document counts
- Per-shard index sizes
- Replica sync status

**SolrReplicationStats** (optional):
- Leader-replica lag
- Replication errors
- Recovery progress

### 3. Code Structure

```python
# osbenchmark/solr/telemetry.py

class SolrQueryStats(SolrTelemetryDevice):
    """Query performance metrics (latency, throughput, errors)"""

class SolrIndexingStats(SolrTelemetryDevice):
    """Indexing performance metrics (rate, merges, refreshes)"""

class SolrCacheStats(SolrTelemetryDevice):
    """Cache hit rates and memory usage"""

class SolrShardStats(SolrTelemetryDevice):
    """Per-shard statistics (optional, expensive)"""

class SolrReplicationStats(SolrTelemetryDevice):
    """Replication lag and recovery tracking"""
```

### 4. Testing Strategy

- Unit tests for metric parsing (JSON vs Prometheus)
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
2. ⬜ Implement Phase 1 devices (SolrQueryStats, SolrIndexingStats, SolrCacheStats)
3. ⬜ Add unit tests for new telemetry devices
4. ⬜ Test with NYC taxis workload + telemetry enabled
5. ⬜ Document telemetry usage in DEVELOPER_GUIDE.md
6. ⬜ Consider Phase 2 implementation based on user feedback

---

## References

- Solr Metrics API: https://solr.apache.org/guide/metrics-reporting.html
- Solr Admin APIs: https://solr.apache.org/guide/collections-api.html
- OpenSearch Benchmark Telemetry: https://opensearch.org/docs/latest/benchmark/
