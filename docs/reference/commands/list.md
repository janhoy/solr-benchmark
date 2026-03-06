---
title: list
parent: Command Reference
grand_parent: Reference
nav_order: 80
---

# list

Lists available resources such as workloads and telemetry devices.

## Syntax

```bash
solr-benchmark list [RESOURCE] [OPTIONS]
```

## Resources

| Resource | Description |
|----------|-------------|
| `workloads` | List workloads from the configured workloads repository |
| `telemetry` | List available telemetry device names |
| `pipelines` | List available pipeline names |
| `test-procedures` | List challenges in a workload (requires `--workload` or `--workload-path`) |
| `test-runs` | List past benchmark runs with their IDs, timestamps, and metadata |

## Options

| Option | Description |
|--------|-------------|
| `--workload` | Workload name (required for `list test-procedures`) |
| `--workload-path` | Path to a local workload directory |
| `--workload-repository` | Git URL for the workloads repository |
| `--workload-revision` | Git revision of the workloads repository |
| `--limit` | Maximum number of test-run results to show (default: `10`) |

## Examples

```bash
# List available workloads
solr-benchmark list workloads

# List available telemetry devices
solr-benchmark list telemetry

# List challenges in a workload
solr-benchmark list test-procedures --workload nyc_taxis

# List available pipelines
solr-benchmark list pipelines

# List recent test runs (shows IDs for use with compare and aggregate)
solr-benchmark list test-runs

# List the 20 most recent test runs
solr-benchmark list test-runs --limit 20
```

The `test-runs` output includes the test execution ID, timestamp, workload name, challenge, pipeline, and any user tags. Use the ID with `solr-benchmark compare` to compare two runs.
