---
title: Command Reference
parent: Reference
nav_order: 50
has_children: true
---

# Command Reference

Reference documentation for all `solr-benchmark` subcommands and their flags.

| Command | Description |
|---------|-------------|
| [aggregate](aggregate.html) | Combine results from multiple benchmark runs |
| [compare](compare.html) | Compare two benchmark runs side by side |
| [convert-workload](../../converter/) | Convert an OpenSearch Benchmark workload to Solr format |
| [download](download.html) | Download a Solr distribution without running a benchmark |
| [info](info.html) | Show detailed information about a workload |
| [list](list.html) | List available workloads, telemetry, pipelines, or past runs |
| [run](run.html) | Run a benchmark workload |

## Common options

The following flags are accepted by every `solr-benchmark` subcommand.

| Flag | Short | Description |
|------|-------|-------------|
| `--help` | `-h` | Display help text for the current command and exit |
| `--offline` | — | Run without network access; disables workload repository fetching and any update checks |
