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
| `test-procedures` | List challenges in a workload (requires `--workload`) |

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
```
