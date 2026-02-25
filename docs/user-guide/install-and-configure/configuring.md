---
title: Configuring
parent: Install and Configure
grand_parent: User Guide
nav_order: 7
---

# Configuring Apache Solr Benchmark

Apache Solr Benchmark stores its configuration in `~/.solr-benchmark/benchmark.ini`. A minimal configuration file is generated automatically on the first run.

## Configuration file location

```
~/.solr-benchmark/benchmark.ini
```

## Key configuration sections

### `[results_publishing]`

Controls where benchmark results are stored.

```ini
[results_publishing]
datastore.type = filesystem
datastore.root = ~/.solr-benchmark/results
```

### `[workloads]`

Controls how workloads are resolved.

```ini
[workloads]
default.repository = https://github.com/janhoy/solr-benchmark-workloads
```

### `[reporting]`

Controls report output format and destination.

```ini
[reporting]
output.path = ~/.solr-benchmark/results
```

## Environment variables

You can also configure Apache Solr Benchmark via environment variables:

| Variable | Description |
|----------|-------------|
| `SOLR_BENCHMARK_HOME` | Override the home directory (default: `~/.solr-benchmark`) |

## Logging

Log files are written to `~/.solr-benchmark/logs/`. Log level can be controlled with `--loglevel` at runtime:

```bash
solr-benchmark run --loglevel debug ...
```
