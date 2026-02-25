# Developer Quickstart: Solr Benchmark Fork

**Feature**: 001-solr-benchmark-fork
**Date**: 2026-02-19

This guide gets a developer contributing to the Solr Benchmark fork running in under 30 minutes.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| Java | 11+ | Required for local Solr provisioning |
| Docker | any | Optional — for Docker-based Solr integration tests |
| git | any | |

---

## 1. Clone and Set Up the Development Environment

```bash
git clone <repo-url> solr-benchmark
cd solr-benchmark
git checkout 001-solr-benchmark-fork

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

---

## 2. Run Unit Tests

```bash
# Run all unit tests
make test

# Or directly with pytest
python -m pytest tests/unit/

# Run only the new Solr-specific unit tests
python -m pytest tests/unit/solr/

# Run with coverage
python -m pytest tests/unit/ --cov=osbenchmark/solr --cov-report=term-missing
```

All unit tests should pass without a running Solr instance. Solr-specific tests use mocked HTTP responses and a mocked pysolr client.

---

## 3. Start a Local Solr 9.x Instance for Integration Testing

### Option A: Docker (recommended)

```bash
docker run -d --name solr-test -p 8983:8983 solr:9

# Verify it's up
curl http://localhost:8983/api/node/system | python -m json.tool
```

### Option B: Download and run Solr directly

```bash
# Download Solr 9.x from https://solr.apache.org/downloads.html
# or let the tool provision it:
./solr-benchmark install --target-os Linux --revision 9.7.0
```

---

## 4. Run Integration Tests

```bash
# Requires a running Solr instance (see step 3)
export SOLR_HOST=localhost
export SOLR_PORT=8983

make it
# Or directly:
python -m pytest tests/integration/solr/ -v
```

The integration tests run a full create-collection → bulk-index → search → delete-collection cycle against the live instance.

---

## 5. Run a Benchmark Manually

### Against an existing Solr cluster

```bash
./solr-benchmark execute-test \
  --workload=geonames \
  --workload-repository=default \
  --target-hosts=localhost:8983 \
  --pipeline=benchmark-only
```

### With local provisioning (downloads and starts Solr)

```bash
./solr-benchmark execute-test \
  --workload=geonames \
  --pipeline=from-distribution \
  --distribution-version=9.7.0
```

Results are written to `~/.solr-benchmark/benchmarks/races/` by default, or to the path configured in `benchmark.ini` under `results_path`.

---

## 6. Key Configuration File

`~/.solr-benchmark/benchmark.ini`:

```ini
[meta]
config.version = 17

[system]
env.name = local

[reporting]
results_writer = local_filesystem
results_path = ~/.solr-benchmark/results

[solr]
port = 8983
```

---

## 7. Run the Linter

```bash
make lint
# Or:
python -m pylint osbenchmark/solr/ osbenchmark/tools/migrate_workload.py
```

---

## 8. Key Source Locations for New Contributors

| Area | Location | Notes |
|---|---|---|
| Solr data operations | `osbenchmark/solr/runner.py` | bulk-index, search, commit, optimize |
| Solr admin (V2 API) | `osbenchmark/solr/client.py` | collection CRUD, version detection |
| Telemetry | `osbenchmark/solr/telemetry.py` | JVM, node, collection stats |
| Provisioner | `osbenchmark/solr/provisioner.py` | download, start, stop |
| Result output | `osbenchmark/solr/result_writer.py` | ResultWriter ABC + LocalFilesystemResultWriter |
| Workload params | `osbenchmark/workload/params.py` | NDJSON stripping, batch building |
| Migration utility | `osbenchmark/tools/migrate_workload.py` | OSB→Solr workload conversion |

---

## 9. Adding a New Result Writer

1. Create a new class subclassing `ResultWriter` from `osbenchmark/solr/result_writer.py`
2. Implement `open(run_metadata)`, `write(metrics)`, and `close()`
3. Register it in `WRITER_REGISTRY` in `result_writer.py`
4. Set `results_writer = <your_key>` in `benchmark.ini` to use it

See `contracts/result-writer.md` for the full interface contract.

---

## 10. Using the Migration Utility

Convert an existing OSB workload to Solr format:

```bash
python -m osbenchmark.tools.migrate_workload \
  path/to/osb-workload.json \
  path/to/output-solr-workload.json
```

Review all `# TODO` comments in the output — these indicate operations that require manual adaptation.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: pysolr` | Run `pip install -e ".[dev]"` again |
| Connection refused to Solr | Check `docker ps` or that `bin/solr start` succeeded; verify port 8983 |
| `404` on `/api/collections` | Ensure Solr version is 9.x+ (V2 API not available on 8.x) |
| Tests fail with OpenSearch import errors | An old `async_connection.py` import may remain — check for stale `.pyc` files |

---

## Documentation Site Local Development (US5)

### Prerequisites

- Ruby 3.3+ (`rbenv` or `rvm` recommended on macOS/Linux)
- Bundler: `gem install bundler`

### First-time setup

```bash
cd docs
bundle install
```

### Serve locally

```bash
cd docs
bundle exec jekyll serve
# Site available at http://localhost:4000
```

### Build for production (validates the site)

```bash
cd docs
bundle exec jekyll build --strict
# Output in docs/_site/
```

A successful build with `--strict` (zero warnings) is the acceptance criterion for
all documentation pull requests.

### Checking for broken links

After build, run a link checker against `docs/_site/`:

```bash
# Using htmlproofer gem (add to Gemfile as dev dependency if desired)
bundle exec htmlproofer docs/_site \
  --disable-external \
  --ignore-urls "/localhost/"
```

### Adding a new page

1. Create `docs/<section>/<page-name>.md`
2. Add front matter:
   ```yaml
   ---
   title: My Page Title
   parent: Section Title
   grand_parent: Parent Section Title   # only for 3rd-level pages
   nav_order: 10
   ---
   ```
3. Run `bundle exec jekyll serve` and verify it appears in the sidebar.

### Content adaptation checklist (for every migrated OSB page)

- [ ] Replace "OpenSearch Benchmark" → "Apache Solr Benchmark" in body text
- [ ] Replace `index`/`indices` (data container) → `collection`/`collections`
- [ ] Replace `create-index`/`delete-index` operations → `create-collection`/`delete-collection`
- [ ] Replace "aggregations" → "facets"
- [ ] Remove or replace links to opensearch.org documentation
- [ ] Replace OSB workloads repo URL → `https://github.com/janhoy/solr-benchmark-workloads`
- [ ] Use "Apache Solr" on first reference per page with link to https://solr.apache.org
- [ ] OpenSearch mentioned? → add TM notice on `about.md` only, not inline
- [ ] No `@author`, no `<!--` license header blocks in Markdown (footer handles attribution)
