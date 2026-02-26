---
title: Command Flags
parent: Command Reference
grand_parent: Reference
nav_order: 150
---

# Command Flags

Complete reference of all `solr-benchmark` command-line flags.

## Global flags

Accepted by all subcommands.

| Flag | Description |
|------|-------------|
| `--version` | Show version and exit |
| `--quiet` | Suppress console output (except errors) |
| `--loglevel` | Log level: `debug`, `info` (default), `warning`, `error` |
| `--log-path` | Path to the log file (default: `~/.solr-benchmark/logs/`) |

## run flags

### Workload selection

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--workload` | string | — | Named workload (fetched from workloads repository) |
| `--workload-path` | path | — | Local workload directory path |
| `--workload-repository` | string | configured default | Git URL for the workloads repository |
| `--workload-revision` | string | `main` | Git revision (branch, tag, or commit) of the workloads repository |
| `--workload-params` | string | — | Comma-separated `key:value` Jinja2 parameter overrides |
| `--challenge` | string | workload default | Challenge name to run |
| `--include-tasks` | string | — | Comma-separated task names to run; all other tasks are skipped |
| `--exclude-tasks` | string | — | Comma-separated task names to skip |
| `--enable-assertions` | flag | off | Enable task-level assertions defined in the workload |

### Cluster and pipeline

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--pipeline` | string | `benchmark-only` | Pipeline to use |
| `--target-hosts` | string | — | Comma-separated `host:port` list |
| `--distribution-version` | string | — | Solr version for provisioning pipelines |
| `--cluster-config` | string | `defaults` | Cluster config preset for provisioning pipelines |

### Distributed load generation

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--worker-ips` | string | `localhost` | Comma-separated IP addresses of worker coordinator machines |

### Multiple-iteration aggregation

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--test-iterations` | integer | `1` | Number of times to repeat the workload |
| `--aggregate` | boolean | `true` | Aggregate results from all iterations |
| `--sleep-timer` | integer | `5` | Seconds to wait between iterations |
| `--cancel-on-error` | boolean | `false` | Abort remaining iterations on first error |

### Telemetry

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--telemetry` | string | — | Comma-separated telemetry device names |
| `--telemetry-params` | string | — | Telemetry device parameters |

### Result output

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--test-execution-id` | string | auto-generated | Custom ID for this run; used with `compare` and `aggregate` |
| `--user-tag` | string | — | Comma-separated `key:value` metadata (e.g., `intention:baseline,heap:4g`) |
| `--results-format` | string | `markdown` | Summary table format: `markdown` or `csv` |
| `--results-number-align` | string | `right` | Column alignment: `right`, `left`, or `center` |
| `--results-file` | path | — | Write the summary table to this file |
| `--results-path` | path | `~/.solr-benchmark/results` | Directory to write JSON/CSV result files |
| `--show-in-results` | string | `available` | Values to include: `available`, `all-percentiles`, or `all` |

### General

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--test-mode` | flag | off | Run with ≤1,000 documents for quick validation |
| `--on-error` | string | `continue` | Error strategy: `continue` or `abort` |
| `--client-options` | string | — | Extra options passed to the Solr client |

## list flags

| Flag | Description |
|------|-------------|
| `--workload` | Workload name (required for `list test-procedures`) |
| `--workload-path` | Local workload directory |
| `--workload-repository` | Git URL for the workloads repository |
| `--workload-revision` | Git revision of the workloads repository |
| `--limit` | Maximum number of test-run results to show (default: `10`) |

## info flags

| Flag | Description |
|------|-------------|
| `--workload` | Workload name |
| `--workload-path` | Local workload directory |
| `--workload-repository` | Git URL for the workloads repository |
| `--workload-revision` | Git revision of the workloads repository |
| `--challenge` | Specific challenge to describe |
| `--include-tasks` | Comma-separated task names to display |
| `--exclude-tasks` | Comma-separated task names to hide |

## compare flags

| Flag | Description |
|------|-------------|
| `--baseline` | Test execution ID of baseline run |
| `--contender` | Test execution ID of contender run |
| `--results-format` | Output format: `markdown` (default) or `csv` |
| `--results-numbers-align` | Column alignment: `right` (default), `left`, or `center` |
| `--results-file` | Write the comparison table to a file |
| `--show-in-results` | Values to include: `available` (default), `all-percentiles`, or `all` |

## aggregate flags

| Flag | Description |
|------|-------------|
| `--test-executions` | Comma-separated test execution IDs to aggregate |
| `--test-execution-id` | Custom ID for the aggregated result |
| `--results-file` | Path to write the aggregated results JSON |

## download flags

Solr is pure Java — no OS- or architecture-specific variants exist.

| Flag | Description |
|------|-------------|
| `--distribution-version` | Solr version to download (e.g., `9.10.1`) |
| `--distribution-repository` | Source repository (default: `release`) |
| `--cluster-config-instance` | Cluster configuration instance to apply |
| `--cluster-config-instance-params` | Comma-separated `key:value` variable overrides |

## convert-workload flags

| Flag | Description |
|------|-------------|
| `--workload-path` | Path to the source (OpenSearch Benchmark format) workload directory |
| `--output-path` | Destination directory for the converted workload |
| `--force` | Overwrite the output directory if it already exists |
