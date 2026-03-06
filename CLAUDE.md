# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

Prerequisites: `pyenv`, JDK 21, Docker, `docker-compose`, `jq`

```bash
make develop          # Install Python 3.10 via pyenv, create .venv, install all deps
source .venv/bin/activate  # Activate virtual environment
```

## Common Commands

```bash
make lint             # Run pylint on osbenchmark/, benchmarks/, scripts/, tests/, it/
make test             # Run unit tests (pytest tests/)
pytest tests/path/to/test_file.py::TestClass::test_method  # Run a single test
make it               # Run integration tests via tox (requires Java, Docker; ~30 min)
make it310            # Integration tests for Python 3.10 only
make benchmark        # Run performance benchmarks (pytest benchmarks/)
make build            # Build distribution wheel
make clean            # Remove build artifacts, caches, tox environments
```

## Code Style

- **Linter**: pylint with `pylint-quotes` plugin (`.pylintrc`)
- **String quotes**: Double quotes enforced
- **Max line length**: 180 characters
- **Max module lines**: 1000

## Architecture

Apache Solr Benchmark (ASB) is a **macrobenchmarking framework** for Apache Solr clusters, using an **actor-based concurrent execution model** via the [Thespian](https://thespianpy.com/) library.

### Entry Points

- `solr-benchmark` / `sb` → `osbenchmark/benchmark.py:main` — CLI for running benchmarks
- `solr-benchmarkd` / `sbd` → `osbenchmark/benchmarkd.py:main` — Daemon for distributed worker nodes

### Core Package (`osbenchmark/`)

**Orchestration layer:**
- `benchmark.py` — CLI arg parsing, subcommands: `run`, `list`, `info`, `generate`
- `test_run_orchestrator.py` — Pipeline execution: prepares, launches cluster, runs workload, publishes results
- `actor.py` — Thespian actor system setup for parallel/distributed execution
- `config.py` — Configuration loading and management

**Cluster management (`builder/`):**
- `provisioners/` — Provision cluster nodes (bare metal, Docker, cloud)
- `downloaders/` — Download Solr distributions
- `installers/` — Install Solr on provisioned nodes
- `launchers/` — Start/stop cluster nodes
- `executors/` — Execute remote commands on cluster nodes
- `configs/` — Jinja2 templates for cluster configuration

**Benchmark execution:**
- `workload/` — Load and manage workload definitions (test procedures, operations, challenges)
- `worker_coordinator/` — Coordinate distributed worker nodes; `driver.py` drives actual load
- `metrics.py` — Collect, store, and aggregate benchmark metrics
- `telemetry.py` — Collect system metrics (CPU, memory, GC, etc.) during benchmarks
- `publisher.py` — Publish and format benchmark results

**Data and connectivity:**
- `client.py`, `async_connection.py` — Solr client wrappers
- `kafka_client.py`, `data_streaming/` — Kafka-based data streaming support
- `synthetic_data_generator/` — Generate synthetic test datasets
- `workload_generator/` — Generate workload definition files from existing indices

**Utilities:**
- `utils/` — IO, process management, console output, network, version parsing, options handling
- `cloud_provider/` — Cloud provider integrations (AWS via boto3, GCP via google-auth)
- `visualizations/` — Result visualization

### Test Structure

- `tests/` — Unit tests mirroring `osbenchmark/` structure
- `it/` — Integration tests (spin up real Solr clusters via Docker/provisioning)
- `benchmarks/` — Performance benchmarks for Solr Benchmark itself

### Workload System

Workloads are defined as JSON/YAML files with:
- **Operations**: individual actions (bulk indexing, search queries)
- **Test procedures** (formerly "challenges"): sequences of operations with parameters
- **Schedules**: timing and throughput targets

Workloads must be in Solr format (use `solr-benchmark convert-workload` to convert from OpenSearch Benchmark format). They can be loaded from a local path (`--workload-path`) or from a git workload repository (`--workload-repository`).

### Pipeline Execution Flow

1. **Prepare** — Load workload, configure metrics store
2. **Build** (optional) — Download and provision Solr cluster
3. **Run** — Execute test procedure via worker coordinator and drivers
4. **Publish** — Store metrics, generate report

## Active Technologies
- Python 3.10+ (001-solr-benchmark-fork)
- Local filesystem (JSON + CSV result files, configurable path). No external store required. (001-solr-benchmark-fork)
- Python 3.10+ + pysolr 3.x (data operations), requests (admin HTTP), thespian (actor model), pytest (tests), tabulate (console tables) (001-solr-benchmark-fork)
- Local filesystem — JSON/CSV result files at `~/.solr-benchmark/`, SQLite test-runs store (001-solr-benchmark-fork)
- Python 3.10+ + pysolr 3.x, requests, thespian (actor model), pytes (001-solr-benchmark-fork)
- Local filesystem — JSON/CSV result files, SQLite test-runs store (001-solr-benchmark-fork)
- Python 3.10+ + `pysolr` 3.x (data ops), `requests` (HTTP admin), `psutil` (process I/O for DiskIo), `thespian` (actor model) (001-solr-benchmark-fork)
- N/A (telemetry data written to local result files via existing ResultWriter) (001-solr-benchmark-fork)

- Jekyll 4.4.1 + just-the-docs 0.12.0 gem — documentation site in `docs/` (001-solr-benchmark-fork)
- GitHub Actions (`docs.yml`) — deploy docs to GitHub Pages on push to main (001-solr-benchmark-fork)

## Recent Changes
- 001-solr-benchmark-fork: Added Python 3.10+
- 001-solr-benchmark-fork: Added Jekyll docs site (docs/) with just-the-docs theme
