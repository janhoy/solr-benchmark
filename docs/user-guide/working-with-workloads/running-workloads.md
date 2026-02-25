---
title: Running a Workload
parent: Working with Workloads
grand_parent: User Guide
nav_order: 9
---

# Running a Workload

## Basic syntax

```bash
solr-benchmark run [--pipeline PIPELINE] [--target-hosts HOSTS] \
  [--workload WORKLOAD | --workload-path PATH] [OPTIONS]
```

## Using a named workload

Named workloads are fetched from [https://github.com/janhoy/solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads):

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis
```

## Using a local workload path

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload-path /path/to/my-workload
```

## Selecting a challenge

A workload may define multiple challenges. Use `--challenge`:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --challenge bulk-only
```

## Test mode

Pass `--test-mode` to run a shortened version of the workload (at most 1,000 documents) for quick validation:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --test-mode
```

## Targeting a multi-node cluster

Separate multiple hosts with commas:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts node1:8983,node2:8983,node3:8983 \
  --workload nyc_taxis
```

## Using the Docker pipeline

```bash
solr-benchmark run \
  --pipeline docker \
  --distribution-version 9.10.1 \
  --workload nyc_taxis \
  --test-mode
```

## Using the from-distribution pipeline

```bash
solr-benchmark run \
  --pipeline from-distribution \
  --distribution-version 9.10.1 \
  --workload nyc_taxis \
  --cluster-config 4gheap
```

## Customizing workload parameters

Override workload Jinja2 parameters at runtime with `--workload-params`:

```bash
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --workload-params "bulk_size:1000,search_clients:4"
```

## Error handling

By default, the run continues if individual operations fail. To abort on the first error:

```bash
solr-benchmark run --on-error abort ...
```
