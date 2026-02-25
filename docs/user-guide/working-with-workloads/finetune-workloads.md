---
title: Fine-tuning Workloads
parent: Working with Workloads
grand_parent: User Guide
nav_order: 12
---

# Fine-tuning Workloads

## Overriding parameters at runtime

Workloads can expose Jinja2 parameters that you override at runtime with `--workload-params`.

In `workload.json` (or an included operations file):

{% raw %}
```json
{
  "operation-type": "bulk-index",
  "bulk-size": {{ bulk_size | default(500) }}
}
```
{% endraw %}

Override at runtime:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload my-workload \
  --workload-params "bulk_size:1000"
```

Multiple parameters are separated by commas:

```bash
--workload-params "bulk_size:1000,search_clients:4,warmup_time:120"
```

## Controlling throughput

Use `target-throughput` (operations per second) to cap the rate of an operation:

```json
{
  "operation": "search",
  "target-throughput": 100
}
```

If the operation is slower than the target, Apache Solr Benchmark will run it as fast as possible without throttling.

## Controlling warmup

Use `warmup-time-period` (seconds) or `warmup-iterations` to discard initial measurements:

```json
{
  "operation": "search",
  "warmup-time-period": 60,
  "iterations": 500
}
```

## Controlling concurrency

Use `clients` to set the number of parallel clients per operation:

```json
{
  "operation": "bulk-index",
  "clients": 8
}
```

## Controlling duration

Use `time-period` (seconds) to run an operation for a fixed duration instead of a fixed number of iterations:

```json
{
  "operation": "search",
  "time-period": 120,
  "clients": 4
}
```

## Selecting a subset of documents

Use `number-of-docs` and `offset` in the corpus definition to benchmark on a subset of the data without downloading the full corpus:

```json
{
  "source-file": "files/data.json.gz",
  "document-count": 165346692,
  "number-of-docs": 1000000,
  "offset": 0
}
```
