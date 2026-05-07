# Solr Benchmark TODO List

## Testing

- [ ] Test telemetry with multi-node SolrCloud clusters
- [ ] Add integration tests for full workload execution
- [ ] Faceting/aggregation result validation

## Documentation

- [ ] Document telemetry usage and configuration in DEVELOPER_GUIDE.md
- [ ] Document the SolrClient pattern in DEVELOPER_GUIDE.md
- [ ] Create troubleshooting guide
- [ ] Add examples of custom native Solr workloads

## Telemetry

- [ ] SolrShardStats (per-shard statistics)
- [ ] SolrReplicationStats (replication lag tracking)
- [ ] SolrSegmentStats (detailed segment breakdown including deleted docs)
- [ ] StartupTime device (node startup duration tracking)
- [ ] DiskIo device (OS-level disk stats)
- [ ] Heapdump on demand (telemetry device)

## Workload

- [ ] Improve schema auto-generation for complex field types
- [ ] Support for nested documents (child docs in Solr)
- [ ] Support for Solr's streaming expressions
- [ ] Support for Solr SQL queries

## Codebase Hygiene

- [ ] Rename the product from "Solr Benchmark" to "Solr Orbit" once accepted into the Apache
  Solr project — touches the project name, CLI entry points (`solr-benchmark` → `solr-orbit`),
  `setup.py`, README, all docs, and PyPI package name
- [ ] Rename the `osbenchmark` package and folder to match the new product name — the current
  name is an artefact of the OpenSearch Benchmark fork; touches imports across the entire
  codebase, entry points in `setup.py`, and all references in docs and CI scripts

## Metrics Store

- [ ] Implement native Solr metrics store (currently only local filesystem JSON/CSV is used)

## Performance

- [ ] Profile memory usage with large workloads

## Release

- [ ] Publish the tool to PyPI as `solr-benchmark` (or `solr-orbit` once renamed) so users can
  install with `pip install solr-benchmark` rather than cloning the repo; requires a PyPI
  project, a CI publish workflow triggered on tags, and a `twine`/`build` release step
  (tooling already present in `develop_require`)
- [ ] Author a release guide documenting the end-to-end release process; evaluate
  [Apache Testing and Release (ATR)](https://release-test.apache.org/docs/) as the
  release tooling — ATR is the ASF's modern replacement for the manual svn-based release
  process and handles signing, staging, and voting workflows

## ASF Compliance

- [ ] Replace pylint with `ruff` for linting and formatting — Apache Airflow uses ruff as its
  primary tool (`[tool.ruff]` in `pyproject.toml`); much faster, broader rule coverage,
  and handles formatting (replacing black/isort) in one tool
- [ ] Add `pre-commit` framework with `insert-license` hook (Lucas-C/pre-commit-hooks) to
  enforce the SPDX license header on every source file at commit time — Apache Airflow
  uses this to cover `.py`, `.sh`, `.yaml`, `.xml`, `.md` and more via per-type templates
  in `scripts/ci/license-templates/`
- [ ] Add Apache RAT with a `.rat-excludes` exclusion list for release-time license audit —
  Apache Airflow maintains ~334 exclusion patterns; RAT is required by ASF release policy
  and is already available since JDK 21 is a prerequisite
- [ ] Add `liccheck` with an authorised-license allowlist in `setup.cfg` to gate CI on
  dependency license compliance — Apache Superset uses liccheck to flag GPL/LGPL
  transitive dependencies automatically; will also catch certifi (MPL-2.0, Category B)
- [ ] Add `pip-licenses` target (`make licenses`) to regenerate NOTICE / THIRD_PARTY
  attribution from installed packages — ensures the attribution file stays current as
  dependencies change
