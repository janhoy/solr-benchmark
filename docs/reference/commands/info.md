---
title: info
parent: Command Reference
grand_parent: Reference
nav_order: 70
---

# info

Shows detailed information about a workload.

## Syntax

```bash
solr-benchmark info --workload WORKLOAD [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--workload` | Workload name (fetched from the workloads repository) |
| `--workload-path` | Path to a local workload directory |
| `--challenge` | Show details for a specific challenge |

## Examples

```bash
# Show information about a named workload
solr-benchmark info --workload nyc_taxis

# Show information about a local workload
solr-benchmark info --workload-path /path/to/my-workload

# Show details for a specific challenge
solr-benchmark info --workload nyc_taxis --challenge append-no-conflicts
```

The output includes:
- Workload description
- Available challenges and their descriptions
- Corpora names and document counts
- Default parameters and their values
