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

| Flag | Short | Description |
|------|-------|-------------|
| `--help` | `-h` | Display help text for the current command and exit |
| `--offline` | — | Run without network access; disables workload repository fetching and update checks |
| `--version` | `-v` | Show version and exit |
| `--quiet` | — | Suppress console output (except errors) |

## run flags

### Workload selection

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--workload` | string | — | Named workload (fetched from workloads repository) |
| `--workload-path` | path | — | Local workload directory path |
| `--workload-repository` | string | configured default | Git URL for the workloads repository |
| `--workload-revision` | string | `main` | Git revision (branch, tag, or commit) of the workloads repository |
| `--workload-params` | string | — | Comma-separated `key:value` Jinja2 parameter overrides |
| `--test-procedure` | string | workload default | Test procedure name to run |
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
| `--test-run-id` | string | auto-generated | Custom ID for this run; used with `compare` and `aggregate` |
| `--user-tag` | string | — | Comma-separated `key:value` metadata (e.g., `intention:baseline,heap:4g`) |
| `--results-format` | string | `markdown` | Summary table format: `markdown` or `csv` |
| `--results-numbers-align` | string | `right` | Column alignment: `right`, `left`, or `center` |
| `--results-file` | path | — | Write the summary table to this file |
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
| `--workload` | Workload name (used with `list workloads` to filter by workload) |
| `--workload-path` | Local workload directory |
| `--workload-repository` | Git URL for the workloads repository |
| `--workload-revision` | Git revision of the workloads repository |
| `--limit` | Maximum number of test-run results to show (default: `10`; applies to `list test-runs`) |

## info flags

| Flag | Description |
|------|-------------|
| `--workload` | Workload name |
| `--workload-path` | Local workload directory |
| `--workload-repository` | Git URL for the workloads repository |
| `--workload-revision` | Git revision of the workloads repository |
| `--workload-params` | Comma-separated `key:value` Jinja2 parameter overrides |
| `--test-procedure` | Specific test procedure to describe |
| `--include-tasks` | Comma-separated task names to display |
| `--exclude-tasks` | Comma-separated task names to hide |

## compare flags

| Flag | Description |
|------|-------------|
| `--baseline` | Test run ID of the baseline run (see `list test-runs`) |
| `--contender` | Test run ID of the contender run (see `list test-runs`) |
| `--results-format` | Output format: `markdown` (default) or `csv` |
| `--results-numbers-align` | Column alignment: `right` (default), `left`, or `center` |
| `--results-file` | Write the comparison table to a file |
| `--show-in-results` | Values to include: `available` (default), `all-percentiles`, or `all` |
| `--percentiles` | Comma-separated list of percentiles to include in the comparison |

## aggregate flags

| Flag | Description |
|------|-------------|
| `--test-runs` | Comma-separated test run IDs to aggregate |
| `--test-runs-id` | Custom ID for the aggregated result |
| `--results-file` | Path to write the aggregated results JSON |
| `--workload-repository` | Git URL for the workloads repository |

## download flags

Solr is pure Java — no OS- or architecture-specific variants exist.

| Flag | Description |
|------|-------------|
| `--distribution-version` | Solr version to download (e.g., `9.10.1`) |
| `--distribution-repository` | Source repository (default: `release`) |
| `--cluster-config` | Cluster configuration preset to apply |
| `--cluster-config-params` | Comma-separated `key:value` variable overrides for the cluster configuration |
| `--cluster-config-path` | Local path to a cluster configuration directory |
| `--cluster-config-repository` | Git URL for a cluster configuration repository |

## convert-workload flags

| Flag | Description |
|------|-------------|
| `--workload-path` | Path to the source (OpenSearch Benchmark format) workload directory |
| `--output-path` | Destination directory for the converted workload |
| `--force` | Overwrite the output directory if it already exists |
