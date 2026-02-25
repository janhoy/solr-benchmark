---
title: Concepts
parent: User Guide
nav_order: 3
---

# Concepts

## Workloads

A *workload* is the central concept in Apache Solr Benchmark. It defines:

- The **data** to load (corpora — compressed NDJSON files)
- The **collections** to create and configure
- The **operations** to run (bulk indexing, search queries, commits, etc.)
- The **challenges** (test procedures) that sequence those operations

Workloads are defined in a `workload.json` file. Pre-built workloads for Apache Solr are at [https://github.com/janhoy/solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads).

## Challenges (Test Procedures)

A *challenge* (also called *test procedure*) is a named configuration within a workload that specifies a particular benchmark scenario. A workload can have multiple challenges; you select one with `--challenge` when running the benchmark.

## Pipelines

A *pipeline* is a sequence of high-level phases that a benchmark run executes:

| Pipeline | Description |
|----------|-------------|
| `benchmark-only` | Run against an existing Solr cluster; no provisioning |
| `docker` | Start a Solr cluster via Docker, then benchmark, then tear down |
| `from-distribution` | Download and install Solr, benchmark, tear down |
| `from-sources` | Build Solr from source, install, benchmark, tear down |

## Collections

A *collection* is the Solr equivalent of an OpenSearch index — a logical grouping of documents distributed across shards. Collections are defined in the workload's `"collections"` array and are created before benchmarking begins.

## Configsets

A *configset* is a named set of Solr configuration files (primarily `schema.xml` and `solrconfig.xml`) stored in ZooKeeper. Every collection references a configset. Supply a custom configset in your workload's `configset-path`. See the [Apache Solr Reference Guide](https://solr.apache.org/guide/solr/latest/configuration-guide/configsets.html) for more information.

## Operations

*Operations* are the individual benchmarking actions. Built-in operations include:

| Operation | Description |
|-----------|-------------|
| `bulk-index` | Index a batch of documents from a corpus |
| `search` | Execute a Solr query |
| `commit` | Issue a hard commit to Solr |
| `optimize` | Issue an optimize (force-merge) command |
| `create-collection` | Create a Solr collection |
| `delete-collection` | Delete a Solr collection |
| `raw-request` | Execute an arbitrary Solr Admin API request |

## Schedules

A *schedule* controls how an operation executes: number of iterations, target throughput (ops/s), warmup iterations, and parallel client count.

## Corpora

*Corpora* are the datasets used by workloads. Each corpus references one or more data files (gzip-compressed NDJSON). Apache Solr Benchmark downloads corpora from the workload repository or a configured data URL.

## Facets

*Facets* are Solr's aggregation mechanism — the Solr equivalent of OpenSearch aggregations. When using the [Converter Tool](../converter/), OpenSearch aggregation expressions are translated into Solr facet syntax.
