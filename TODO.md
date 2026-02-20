# Solr Benchmark TODO List

## High Priority

### Telemetry Parity
See [TELEMETRY-GAP-ANALYSIS.md](./TELEMETRY-GAP-ANALYSIS.md) for detailed plan.

- [ ] Implement Phase 1 telemetry devices:
  - [ ] SolrQueryStats (query latency percentiles, per-handler metrics)
  - [ ] SolrIndexingStats (indexing rate, merge stats, refresh stats)
  - [ ] SolrCacheStats (cache hit rates, memory usage)
  - [ ] Enhanced SolrJvmStats (thread pools, buffer pools, detailed GC)
  - [ ] Enhanced SolrNodeStats (file descriptors, network stats)

- [ ] Add unit tests for all telemetry devices
- [ ] Test telemetry with multi-node SolrCloud clusters
- [ ] Document telemetry usage and configuration

### Code Quality
- [ ] Add unit tests for date format conversion helpers
- [ ] Document the SolrClient pattern in DEVELOPER_GUIDE.md
- [ ] Add integration tests for full workload execution

---

## Medium Priority

### Telemetry Phase 2
- [ ] SolrShardStats (per-shard statistics)
- [ ] SolrReplicationStats (replication lag tracking)
- [ ] SolrSegmentStats (detailed segment breakdown)
- [ ] StartupTime device (internal, framework already exists)
- [ ] DiskIo device (internal, OS-level stats)

### Workload Compatibility
- [ ] Test with more OpenSearch workloads (geonames, geopoint, http_logs, etc.)
- [ ] Add more native Solr workloads
- [ ] Improve schema auto-generation for complex field types
- [ ] Support for nested documents (child docs in Solr)

### Performance
- [ ] Benchmark large corpus indexing (100M+ docs)
- [ ] Optimize bulk indexing batch sizes
- [ ] Profile memory usage with large workloads

---

## Low Priority

### Documentation
- [ ] Create user guide for running Solr benchmarks
- [ ] Add examples of custom Solr workloads
- [ ] Document differences between Solr and OpenSearch workload formats
- [ ] Create troubleshooting guide

### Nice to Have
- [ ] Heapdump on demand (telemetry device)
- [ ] Support for Solr's streaming expressions
- [ ] Faceting/aggregation result validation
- [ ] Support for Solr SQL queries

---

## Future Architectural Changes

### Remove OpenSearch Mode (Long-term Goal)

**Context**: This codebase is a fork of OpenSearch Benchmark specifically for Solr benchmarking. The OpenSearch-specific code paths are vestigial remains from the original codebase.

**Current State**:
- ✅ Solr code has ZERO opensearchpy dependencies
- ✅ Clean separation: Solr mode vs OpenSearch mode
- ⚠️ OpenSearch mode still exists in framework (metrics store, telemetry, workload generation)

**Why Remove It**:
1. **Maintenance burden**: Supporting two execution paths increases complexity
2. **Code clarity**: A pure Solr benchmark tool is easier to understand and maintain
3. **Reduced dependencies**: Can remove opensearchpy entirely from setup.py
4. **Focused development**: All effort goes into Solr features, not maintaining OpenSearch compatibility

**What Needs to Be Addressed**:

1. **Metrics Storage**:
   - Current: Can store benchmark results in OpenSearch cluster
   - Solution: Implement alternative storage backends (JSON files, InfluxDB, Prometheus, Solr itself)
   - Files affected: `osbenchmark/metrics.py`

2. **Workload Generation**:
   - Current: Can extract workloads from OpenSearch indices
   - Solution: Implement Solr-specific workload generator (extract from Solr collections)
   - Files affected: `osbenchmark/workload_generator/extractors.py`

3. **Telemetry Devices**:
   - Current: OpenSearch-specific telemetry devices exist
   - Solution: Already isolated - just remove unused devices
   - Files affected: `osbenchmark/telemetry.py`

4. **Cloud Providers**:
   - Current: AWS OpenSearch service integration exists
   - Solution: Remove or replace with Solr Cloud integrations
   - Files affected: `osbenchmark/cloud_provider/vendors/aws.py`

5. **Client Factory**:
   - Current: `OsClientFactory` always returns `SolrClient` but name is misleading
   - Solution: Rename to `SolrClientFactory`, remove OpenSearch client code
   - Files affected: `osbenchmark/client.py`

**Implementation Plan**:

Phase 1 - Metrics Storage Alternatives:
- [ ] Implement local filesystem metrics storage (JSON/CSV)
- [ ] Document how to export metrics to external systems
- [ ] Make OpenSearch metrics store optional

Phase 2 - Workload Generation:
- [ ] Implement Solr-based workload extractor
- [ ] Document workload creation from Solr collections
- [ ] Make OpenSearch extractor optional

Phase 3 - Code Cleanup:
- [ ] Remove unused OpenSearch telemetry devices
- [ ] Remove AWS OpenSearch integration
- [ ] Remove conditional opensearchpy imports
- [ ] Rename `OsClientFactory` → `SolrClientFactory`
- [ ] Update all "OpenSearch" references to "Solr" where appropriate

Phase 4 - Dependency Cleanup:
- [ ] Remove opensearchpy from setup.py
- [ ] Remove opensearchpy from all imports
- [ ] Update documentation to reflect Solr-only nature
- [ ] Rename repository/project to "Solr Benchmark" officially

**Timeline**:
- Not urgent - can be done after telemetry parity is achieved
- Requires careful planning to avoid breaking existing users
- Should be done in stages with clear migration path

**Benefits After Completion**:
- ✅ Simpler codebase (50% reduction in conditional logic)
- ✅ Faster development (no need to maintain dual paths)
- ✅ Clearer purpose (pure Solr benchmark tool)
- ✅ Easier onboarding (no OpenSearch knowledge required)
- ✅ Reduced dependencies (smaller installation footprint)

---

## Decisions to Make

1. **Metrics Storage**: Which alternative storage backends to support?
   - JSON files (simplest)
   - InfluxDB (time-series optimized)
   - Prometheus (monitoring-friendly)
   - Solr itself (dogfooding)
   - All of the above?

2. **Backward Compatibility**: Should we maintain compatibility with OpenSearch Benchmark workload format?
   - Yes: Easier migration for existing users
   - No: Simpler codebase, Solr-native formats only

3. **Naming**: Should we rename the project entirely?
   - Keep "OpenSearch Benchmark (Solr Fork)"
   - Rename to "Apache Solr Benchmark"
   - Rename to something else

4. **Apache Incubation**: Should this be submitted as an Apache project?
   - Would fit well with Apache Solr project
   - Requires CLAs, governance alignment
   - Long-term sustainability

---

## Notes

- This TODO list is a living document
- Priorities may change based on user feedback
- See MEMORY.md for implementation history and lessons learned
- See TELEMETRY-GAP-ANALYSIS.md for detailed telemetry planning
