# Solr Benchmark TODO List

## High Priority

### Testing
- [ ] Test telemetry with multi-node SolrCloud clusters
- [ ] Add integration tests for full workload execution

### Documentation
- [ ] Document telemetry usage and configuration in DEVELOPER_GUIDE.md
- [ ] Document the SolrClient pattern in DEVELOPER_GUIDE.md

---

## Medium Priority

### Telemetry Enhancements (deferred)
- [ ] SolrShardStats (per-shard statistics)
- [ ] SolrReplicationStats (replication lag tracking)
- [ ] SolrSegmentStats (detailed segment breakdown including deleted docs)
- [ ] StartupTime device (node startup duration tracking)
- [ ] DiskIo device (OS-level disk stats)

### Workload Compatibility
- [ ] Test with more OpenSearch workloads (geopoint, http_logs, etc.)
- [ ] Add more native Solr workloads
- [ ] Improve schema auto-generation for complex field types
- [ ] Support for nested documents (child docs in Solr)

### Metrics Store
- [ ] Implement native Solr metrics store (currently OpenSearch metrics store is not supported; only local filesystem JSON/CSV is used)

### Performance
- [ ] Benchmark large corpus indexing (100M+ docs)
- [ ] Profile memory usage with large workloads

---

## Low Priority

### Documentation
- [ ] Create troubleshooting guide
- [ ] Add examples of custom native Solr workloads

### Nice to Have
- [ ] Heapdump on demand (telemetry device)
- [ ] Support for Solr's streaming expressions
- [ ] Faceting/aggregation result validation
- [ ] Support for Solr SQL queries

---

## Notes

- See TELEMETRY-GAP-ANALYSIS.md for detailed telemetry planning
