---
title: Filesystem Metrics Store
parent: Metrics Reference
grand_parent: Reference
nav_order: 1
---

# Filesystem Metrics Store

The filesystem metrics store is the default metrics store for Apache Solr Benchmark.
It extends the in-memory store by also streaming each metric document to a `metrics.jsonl`
file on disk as the benchmark runs, so that raw samples are available for offline analysis
even after the process exits.

## Configuration

The store type is controlled by the `metrics_store` key under the `[reporting]` section in
`~/.solr-benchmark/solr-benchmark.ini`:

```ini
[reporting]
# Default: filesystem (writes metrics.jsonl alongside test_run.json)
# Set to "memory" to disable disk persistence
metrics_store = filesystem
```

You can also override it for a single run using `--workload-params` or by setting the value
in the configuration file before running.

## File layout

After a completed benchmark run the following structure is created under `~/.solr-benchmark/`:

```
~/.solr-benchmark/
├── benchmarks/
│   └── test-runs/
│       └── <run-id>/
│           ├── test_run.json   # full run record with calculated results
│           └── metrics.jsonl  # raw metric documents, one JSON object per line
└── results/
    └── <timestamp>_<run-id>/
        ├── summary.txt         # human-readable Markdown summary table
        ├── results.csv         # flattened CSV of calculated results
        └── test_run.json       # copy of the canonical run record
```

### `test_run.json`

Written by the test-run store after the run finishes.
Contains the full computed results (percentiles, error rates, throughput summaries)
together with workload metadata and benchmark environment information.

### `metrics.jsonl`

Written by the filesystem metrics store incrementally during the run.
Each line is a standalone JSON object representing a single metric measurement.
Lines are written in chronological order with line buffering (no data is lost if the
process is killed after the first measurement).

Example line:

```json
{"test-run-id":"abc123","environment":"local","workload":"nyc_taxis","test_procedure":"append-no-conflicts","name":"service_time","value":42.7,"unit":"ms","task":"index","operation-type":"bulk","sample-type":"normal","absolute-time-ms":1709123456789,"relative-time-ms":1234,"meta":{"success":true}}
```

## Inspecting raw metrics

### Using `jq`

List all distinct metric names recorded in a run:

```sh
jq -r '.name' ~/.solr-benchmark/benchmarks/test-runs/<run-id>/metrics.jsonl | sort -u
```

Compute the median service time for a task:

```sh
jq 'select(.name=="service_time" and .task=="index") | .value' \
  ~/.solr-benchmark/benchmarks/test-runs/<run-id>/metrics.jsonl \
  | sort -n | awk '{a[NR]=$0} END{print a[int(NR/2)]}'
```

### Using Python

```python
import json

with open("~/.solr-benchmark/benchmarks/test-runs/<run-id>/metrics.jsonl") as f:
    docs = [json.loads(line) for line in f]

service_times = [d["value"] for d in docs if d["name"] == "service_time"]
print(f"Samples: {len(service_times)}, avg: {sum(service_times)/len(service_times):.2f} ms")
```

### Pretty-printing a single line

```sh
head -1 ~/.solr-benchmark/benchmarks/test-runs/<run-id>/metrics.jsonl | python3 -m json.tool
```
