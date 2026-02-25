---
title: Installing
parent: Install and Configure
grand_parent: User Guide
nav_order: 5
---

# Installing Apache Solr Benchmark

## Prerequisites

- Python 3.10 or later
- pip (Python package manager)
- Git
- Docker (required for the `docker` pipeline only)
- JDK 21 (required for the `from-distribution` and `from-sources` pipelines only)

## Install from source

Apache Solr Benchmark is currently only available by cloning the repository and installing locally:

```bash
git clone https://github.com/janhoy/solr-benchmark.git
cd solr-benchmark
pip install -e .
```

Verify the installation:

```bash
solr-benchmark --version
```

{: .note }
Apache Solr Benchmark is not yet published as a package on PyPI. A `pip install solr-benchmark` release is planned for the future.

## Virtual environment (recommended)

It is recommended to install Apache Solr Benchmark in a virtual environment to avoid dependency conflicts:

```bash
git clone https://github.com/janhoy/solr-benchmark.git
cd solr-benchmark
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Developer install

To also install development and test dependencies:

```bash
pip install -e ".[develop]"
```

## Upgrading

To pick up the latest changes, pull from the repository:

```bash
cd solr-benchmark
git pull
pip install -e .
```
