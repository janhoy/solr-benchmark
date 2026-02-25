---
title: Command Flags
parent: Command Reference
grand_parent: Reference
nav_order: 150
---

# Command Flags

Complete reference of all `solr-benchmark` command-line flags.

## Global flags

| Flag | Description |
|------|-------------|
| `--version` | Show version and exit |
| `--quiet` | Suppress console output (except errors) |
| `--loglevel` | Log level: `debug`, `info` (default), `warning`, `error` |
| `--log-path` | Path to the log file (default: `~/.solr-benchmark/logs/`) |

## run flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--pipeline` | string | `benchmark-only` | Pipeline to use |
| `--target-hosts` | string | — | Comma-separated `host:port` list |
| `--workload` | string | — | Named workload (fetched from workloads repo) |
| `--workload-path` | path | — | Local workload directory path |
| `--workload-repository` | string | [janhoy/solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads) | Git URL for workloads repository |
| `--challenge` | string | (workload default) | Challenge name to run |
| `--test-mode` | flag | off | Run with ≤1,000 documents |
| `--workload-params` | string | — | Comma-separated `key:value` parameter overrides |
| `--distribution-version` | string | — | Solr version for provisioning pipelines |
| `--cluster-config` | string | `defaults` | Cluster config preset for provisioning pipelines |
| `--telemetry` | string | — | Comma-separated telemetry device names |
| `--telemetry-params` | string | — | Telemetry device parameters |
| `--on-error` | string | `continue` | `continue` or `abort` |
| `--client-options` | string | — | Extra options passed to the Solr client |
| `--results-path` | path | `~/.solr-benchmark/results` | Directory to write results |

## list flags

| Flag | Description |
|------|-------------|
| `--workload` | Workload name (required for `list test-procedures`) |

## info flags

| Flag | Description |
|------|-------------|
| `--workload` | Workload name |
| `--workload-path` | Local workload directory |
| `--challenge` | Specific challenge to describe |

## compare flags

| Flag | Description |
|------|-------------|
| `--baseline` | Test execution ID of baseline run |
| `--contender` | Test execution ID of contender run |

## convert-workload flags

| Flag | Description |
|------|-------------|
| `--workload-path` | Path to the source (OpenSearch Benchmark format) workload directory |
| `--output-path` | Destination directory for the converted workload |
| `--force` | Overwrite the output directory if it already exists |
