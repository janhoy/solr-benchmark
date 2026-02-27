---
title: Metrics Reference
parent: Reference
nav_order: 60
has_children: true
---

# Metrics

Apache Solr Benchmark stores all metrics collected during a benchmark run so that they can be
analyzed and compared across runs. This page describes the available storage options.

## Storing metrics

Metrics can be stored in two ways depending on your analysis requirements.

### In memory

The simplest configuration keeps all metric records in RAM for the duration of the run.
Results are computed from this in-memory state and written to the filesystem when the run
completes. The raw individual samples are not persisted beyond the process lifetime.

To use in-memory storage, set `metrics_store` in your configuration file
(`~/.solr-benchmark/solr-benchmark.ini`):

```ini
[reporting]
metrics_store = memory
```

Use this option when you only need the aggregated results (percentiles, throughput summaries)
and do not require access to the individual raw samples after the run.

### Filesystem (default)

The filesystem metrics store is the default. It keeps all metric records in RAM (exactly
like the in-memory store) **and** streams every raw metric document to a `metrics.jsonl`
file on disk as it arrives. This makes individual samples available for offline analysis
even after the benchmark process exits.

```ini
[reporting]
metrics_store = filesystem
```

Files are written to:

```
~/.solr-benchmark/
└── benchmarks/
    └── test-runs/
        └── <run-id>/
            ├── test_run.json   # computed results (percentiles, error rates, …)
            └── metrics.jsonl   # raw metric documents, one JSON object per line
```

See [Filesystem Metrics Store](filesystem-metrics-store.html) for full configuration and
file layout details, including `jq` and Python examples for inspecting raw samples.

## Next steps

- [Filesystem Metrics Store](filesystem-metrics-store.html) — store configuration and file layout
- [Metric Records](metric-records.html) — structure of individual metric documents
- [Metric Keys](metrics-reference.html) — catalog of every metric key Solr Benchmark can record
