# ASB Documentation Review

## Summary

Overall completeness is approximately **65–70%**. The docs cover the main user-facing
surface well: quickstart, core concepts, pipelines, telemetry devices, metrics keys,
workload format, and the converter tool. However, several subcommands are entirely absent
from the Command Reference index, a number of CLI flags use incorrect names or describe
flags that do not exist in the code, and the `create-collection` operation documents
wrong parameter keys in multiple places. No single page is wildly wrong, but the combined
effect of mismatched terminology (``--challenge`` vs ``--test-procedure``,
``--test-execution-id`` vs ``--test-run-id``) and missing entries would cause user
confusion. The quality of prose is generally high.

---

## Documentation Structure

| File | Content |
|------|---------|
| `docs/index.md` | Landing page |
| `docs/quickstart.md` | Install + first run |
| `docs/about.md` | Project background |
| `docs/faq.md` | Frequently asked questions |
| `docs/glossary.md` | Terminology mapping OSB → ASB |
| `docs/cluster-config/index.md` | Cluster config overview |
| `docs/cluster-config/available-configs.md` | Documented configs: defaults, 1gheap, 4gheap, g1gc, parallelgc |
| `docs/converter/index.md`, `usage.md`, `what-converts.md` | convert-workload tool |
| `docs/reference/commands/index.md` | Command reference index |
| `docs/reference/commands/aggregate.md` | aggregate subcommand |
| `docs/reference/commands/command-flags.md` | Complete flag reference |
| `docs/reference/commands/compare.md` | compare subcommand |
| `docs/reference/commands/download.md` | download subcommand |
| `docs/reference/commands/info.md` | info subcommand |
| `docs/reference/commands/list.md` | list subcommand |
| `docs/reference/commands/run.md` | run subcommand |
| `docs/reference/metrics/` | Metric records, filesystem store, keys reference |
| `docs/reference/summary-report.md` | Summary table explanation |
| `docs/reference/telemetry.md` | All telemetry devices |
| `docs/reference/workloads/` | collections, corpora, operations, test-procedures |
| `docs/user-guide/` | Concepts, install/configure, workloads, optimizing, results |

---

## CLI Reference Accuracy

### Subcommands

The following subcommands exist in `osbenchmark/benchmark.py` but are **not listed** in
`docs/reference/commands/index.md` and have no dedicated doc page:

- `generate-data` — generates synthetic data (lines 169–219 of benchmark.py)
- `create-workload` — creates a workload from an existing cluster (lines 221–266)
- `install` / `start` / `stop` — manual cluster node lifecycle (lines 392–523)
- `visualize` — generates HTML visualisation for a test run (lines 325–336)

The five documented command pages (`aggregate`, `compare`, `download`, `info`, `list`, `run`)
are present, but only `run`, `compare`, `aggregate`, and `list` are complete enough for
everyday use.

---

### `run` subcommand

**docs/reference/commands/run.md** and **docs/reference/commands/command-flags.md**

| Doc Claim | Reality | Severity |
|-----------|---------|----------|
| `--challenge` | Does not exist. The real flag is `--test-procedure` (benchmark.py line 575–576). | Critical |
| `--test-execution-id` | Does not exist. The real flag is `--test-run-id` (benchmark.py line 543–547). | Critical |
| `--results-number-align` (`run.md` line 61) | Does not exist. The real flag is `--results-numbers-align` (plural) (benchmark.py line 661). | Critical |
| `--loglevel` (command-flags.md line 23) | Not defined in benchmark.py argument parser. Not a CLI flag. | Critical |
| `--log-path` (command-flags.md line 24) | Not defined in benchmark.py argument parser. Not a CLI flag. | Critical |
| `--results-path` (command-flags.md line 81) | Not defined in benchmark.py argument parser. Not a CLI flag. | Major |
| `--pipeline` default stated as `benchmark-only` in run.md (line 36) and command-flags.md (line 45) | Partially correct: the default is dynamically derived; `benchmark-only` is used when neither `--distribution-version` nor explicit `--pipeline` is given (test_run_orchestrator.py lines 607–617). However, the docs state it as a flat default which is inaccurate. | Minor |
| `--client-options` not documented in `run.md` | The flag is valid (benchmark.py line 619–623) and significant; it is mentioned only in command-flags.md but missing from run.md. | Minor |
| `--grpc-target-hosts` not documented anywhere | Exists in benchmark.py (line 614–617). | Minor |
| `--redline-test`, `--redline-*` flags not documented | A full set of redline/load-test flags exists (lines 757–808). | Minor |
| `--visualize`, `--visualize-output-path` not documented | Exists in benchmark.py (lines 807–817). | Minor |
| `--latency-percentiles`, `--throughput-percentiles` not documented in run.md | Exists in benchmark.py (lines 701–712). | Minor |
| `--randomization-*` flags not documented in run.md | Four flags exist (lines 714–732). | Minor |
| `--solr-modules` not documented in run.md | Exists in benchmark.py (lines 594–597). | Minor |
| `--plugin-params` not documented in run.md | Exists in benchmark.py (lines 598–602). | Minor |
| `--test-iterations`, `--aggregate`, `--sleep-timer`, `--cancel-on-error` are documented | Correct, present in command-flags.md. | OK |

---

### `list` subcommand

**docs/reference/commands/list.md**

| Doc Claim | Reality | Severity |
|-----------|---------|----------|
| `list test-procedures` as a valid resource | The actual choice is `list workloads`; `test-procedures` is **not** a valid `list` argument. Valid choices: `telemetry`, `workloads`, `pipelines`, `test-runs`, `aggregated-results`, `cluster-configs` (benchmark.py lines 131–133). | Critical |
| `aggregated-results` not mentioned as a list target | Missing from the docs table. | Minor |

---

### `compare` subcommand

**docs/reference/commands/compare.md**

| Doc Claim | Reality | Severity |
|-----------|---------|----------|
| `--baseline` / `--contender` described as "Test execution ID" | The code parameter is `test-run-id`, not `test-execution-id`. While usage is correct, terminology is inconsistent with the CLI. | Minor |
| `--percentiles` flag not documented | Exists in benchmark.py (lines 302–305) as `--percentiles`. | Minor |
| `--show-in-results` for compare is not in compare.md | Exists in benchmark.py (lines 321–323). | Minor |

---

### `aggregate` subcommand

**docs/reference/commands/aggregate.md**

| Doc Claim | Reality | Severity |
|-----------|---------|----------|
| `--test-executions` as the flag name (lines 45, 52, 58) | Does not exist. The real flag is `--test-runs` (benchmark.py line 340–343). | Critical |
| `--test-execution-id` as the aggregated ID flag (lines 59) | Does not exist. The real flag is `--test-runs-id` (benchmark.py line 345–348). | Critical |
| `--workload-repository` flag not documented for `aggregate` | Exists in benchmark.py (lines 353–356). | Minor |

---

### `download` subcommand

**docs/reference/commands/download.md**

| Doc Claim | Reality | Severity |
|-----------|---------|----------|
| `--cluster-config-instance` flag | Does not exist. The actual flag is `--cluster-config` (benchmark.py line 381–385). | Critical |
| `--cluster-config-instance-params` flag | Does not exist. The actual flag is `--cluster-config-params` (benchmark.py line 386–390). | Critical |
| `--cluster-config-path` and `--cluster-config-repository` not documented | Both exist in benchmark.py (lines 362–366). | Minor |

---

### `info` subcommand

**docs/reference/commands/info.md**

| Doc Claim | Reality | Severity |
|-----------|---------|----------|
| `--challenge` option (line 26) | Does not exist. The real flag is `--test-procedure` (benchmark.py line 158–161). | Critical |
| `--workload-params` flag not documented | Exists in benchmark.py (lines 151–156). | Minor |

---

### `command-flags.md` — global flags section

| Doc Claim | Reality | Severity |
|-----------|---------|----------|
| `--loglevel` (line 23) | Not an argument in benchmark.py. | Critical |
| `--log-path` (line 24) | Not an argument in benchmark.py. | Critical |
| `--version` described as global | Correct, exists as `-v`/`--version` (benchmark.py line 113). | OK |

---

## Workload System

### Operations documentation

**docs/reference/workloads/operations.md** and **docs/user-guide/understanding-workloads/common-operations.md**

| Issue | Location | Severity |
|-------|----------|----------|
| `optimize` documented with parameter `max-num-segments` but code uses `max-segments` | `osbenchmark/solr/runner.py` line 577: `params.get("max-segments", 1)`. The docs show `"max-num-segments"` in the JSON example (operations.md line 76, common-operations.md line 82). | Critical |
| `create-collection` documented with `shards` (snake-case, no hyphen) | Code reads `num-shards` (loader.py line 1517). Docs use `"shards": 1` throughout (operations.md line 88, collections.md lines 20/48). | Critical |
| `create-collection` documented with `nrt_replicas` (underscore) | Code reads `tlog-replicas`, `pull-replicas` (hyphenated, loader.py line 1519–1520). Docs use `nrt_replicas` with underscores (operations.md line 89). | Major |
| `soft-commit` parameter on `commit` operation not documented | Code supports `params.get("soft-commit", False)` (runner.py line 546). | Minor |
| `wait-for-merges` operation not documented | Registered in runner.py line 826. | Minor |
| `paginated-search` and `scroll-search` operation aliases not documented | Registered in runner.py lines 833–834. | Minor |
| `refresh` alias for `commit` not documented | Registered in runner.py line 824. | Minor |
| `delete-collection` parameter `configset`, `delete-configset`, `ignore-missing` not documented | Code supports these (runner.py lines 737–746). | Minor |
| `create-collection` parameter `replication-factor`, `tlog-replicas`, `pull-replicas`, `delete-configset-on-error`, `configset` not documented | Code supports these (runner.py lines 668–675). | Minor |
| Backup-related operations (`create-backup`, `restore-backup`, `create-backup-repository`, `delete-backup-repository`, `wait-for-backup-create`) not documented | Registered in runner.py lines 49–53. | Minor |

---

### `collections` in `workload.json`

**docs/reference/workloads/collections.md**

The field names in the `"collections"` array of `workload.json` are documented as:
- `shards` → but code reads `num-shards` (loader.py line 1517)
- `nrt_replicas` → but code reads `replication-factor` for NRT replicas (loader.py line 1518)

This is a discrepancy between what the docs say you put in `workload.json` vs what the
loader actually parses. Users who follow the docs will produce invalid workloads.

---

## Pipeline & Architecture

The four pipeline names (`benchmark-only`, `docker`, `from-distribution`, `from-sources`)
are consistently and correctly documented everywhere.

Pipeline **stage** documentation (Setup → Build → Run → Publish) is described in
`CLAUDE.md` but not in the user-facing docs. The `docs/user-guide/concepts.md` page
describes pipelines at a high level without enumerating the internal stages, which is
appropriate for user documentation.

No issues with pipeline accuracy.

---

## Telemetry & Metrics

**docs/reference/telemetry.md** is well-written and matches the code accurately.

The `list_telemetry()` function in `osbenchmark/telemetry.py` (lines 43–72) lists:

- Always-enabled: `SolrJvmStats`, `SolrNodeStats`, `SolrCollectionStats`, `SolrQueryStats`,
  `SolrIndexingStats`, `SolrCacheStats` — all documented correctly.
- Optional REST: `SegmentStats`, `ShardStats`, `ClusterEnvironmentInfo` — documented correctly.
- Optional JVM: `FlightRecorder` (`jfr`), `Gc` (`gc`), `JitCompiler` (`jit`), `Heapdump`
  (`heapdump`) — documented correctly.
- `DiskIo` always active on provisioned pipelines — documented correctly.

The claim in telemetry.md (line 9) that "Six devices are always enabled" is accurate (6
always-enabled Solr devices). No factual errors found in telemetry docs.

The **metrics reference** (`docs/reference/metrics/metrics-reference.md`) is thorough and
accurate.

---

## Configuration Reference

**docs/user-guide/install-and-configure/configuring.md** is accurate.

Minor gap: the docs say you can control log level with `--loglevel` (line 149). There is
**no `--loglevel` flag** in `osbenchmark/benchmark.py`. This is an error; log level control
is only via the `~/.solr-benchmark/logging.json` file (as the text above it correctly states).

---

## Issues Found

### Critical Issues

1. **`--challenge` used throughout docs instead of `--test-procedure`**
   - `docs/reference/commands/run.md` lines 28, 37 (Workload selection table, option name)
   - `docs/reference/commands/command-flags.md` lines 36, 110
   - `docs/reference/commands/info.md` lines 26, 40
   - `docs/reference/workloads/test-procedures.md` lines 63–68 (example command uses `--challenge`)
   - `docs/user-guide/concepts.md` lines 22–23
   - `docs/glossary.md` line 14
   - Real flag: `--test-procedure` (benchmark.py line 575)

2. **`--test-execution-id` used throughout docs instead of `--test-run-id`**
   - `docs/reference/commands/run.md` line 59
   - `docs/reference/commands/command-flags.md` lines 76, 130
   - `docs/reference/commands/aggregate.md` lines 59 (here as `--test-execution-id`)
   - Real flag: `--test-run-id` (benchmark.py line 543)

3. **`--test-executions` in `aggregate` command instead of `--test-runs`**
   - `docs/reference/commands/aggregate.md` lines 45, 52, 58
   - `docs/reference/commands/command-flags.md` line 129
   - Real flag: `--test-runs` (benchmark.py line 340)

4. **`--loglevel` and `--log-path` do not exist**
   - `docs/reference/commands/command-flags.md` lines 23–24
   - These flags are not in the argument parser (benchmark.py)

5. **`--cluster-config-instance` / `--cluster-config-instance-params` do not exist**
   - `docs/reference/commands/download.md` lines 27–28
   - `docs/reference/commands/command-flags.md` lines 141–142
   - Real flags: `--cluster-config` and `--cluster-config-params` (benchmark.py lines 381–390)

6. **`optimize` operation documented with `max-num-segments` but code reads `max-segments`**
   - `docs/reference/workloads/operations.md` line 76
   - `docs/user-guide/understanding-workloads/common-operations.md` line 82
   - Real parameter: `max-segments` (osbenchmark/solr/runner.py line 577)

7. **`create-collection` in `workload.json` uses wrong field names**
   - `docs/reference/workloads/collections.md` lines 20, 35–38, 48
   - `docs/reference/workloads/operations.md` lines 88–89
   - Docs say `"shards"` but loader reads `"num-shards"` (loader.py line 1517)
   - Docs say `"nrt_replicas"` but loader reads `"replication-factor"` (loader.py line 1518)

8. **`list test-procedures` is not a valid `list` argument**
   - `docs/reference/commands/list.md` line 25 (table row for `test-procedures`)
   - `docs/reference/commands/command-flags.md` line 96
   - `docs/reference/commands/info.md` line 40
   - Valid choices: `telemetry`, `workloads`, `pipelines`, `test-runs`, `aggregated-results`, `cluster-configs`

9. **`--results-number-align` in `run.md` instead of `--results-numbers-align`**
   - `docs/reference/commands/run.md` line 62
   - Real flag: `--results-numbers-align` (benchmark.py line 661)

---

### Minor Issues

1. **`--results-path` does not exist** — `docs/reference/commands/command-flags.md` line 81. No such CLI flag in benchmark.py.

2. **`--percentiles` for `compare` not documented** — benchmark.py line 302.

3. **`aggregated-results` not mentioned as a `list` target** — `docs/reference/commands/list.md` (missing row in table).

4. **`--workload-params` not documented for `info` command** — benchmark.py lines 151–156.

5. **`--grpc-target-hosts` not documented** — benchmark.py lines 614–617.

6. **`--solr-modules`, `--plugin-params` not documented in `run.md`** — benchmark.py lines 594–602.

7. **`--load-test-qps`, `--redline-test` and related flags not documented** — benchmark.py lines 753–808.

8. **`--visualize` and `--visualize-output-path` flags not documented** — benchmark.py lines 807–817.

9. **`--latency-percentiles` and `--throughput-percentiles` not documented in `run.md`** — benchmark.py lines 701–712.

10. **`--randomization-enabled`, `--randomization-repeat-frequency`, `--randomization-n`, `--randomization-alpha` not documented** — benchmark.py lines 714–732.

11. **`soft-commit` parameter for `commit` operation not documented** — osbenchmark/solr/runner.py line 546.

12. **`wait-for-merges`, `paginated-search`, `scroll-search`, `refresh` operations not documented** — osbenchmark/solr/runner.py lines 824–834.

13. **`delete-collection` extended parameters not documented** — `configset`, `delete-configset`, `ignore-missing` (runner.py lines 737–746).

14. **Backup operations (`create-backup`, `restore-backup`, etc.) not documented** — runner.py lines 49–53.

15. **`--log-path` on configuring.md line 149** — Says users can use `--loglevel` on the run command; the flag does not exist in the CLI.

16. **Cluster config docs missing entries** — `docs/cluster-config/available-configs.md` documents only `defaults`, `1gheap`, `4gheap`, `g1gc`, `parallelgc`. The actual resource bundle at `osbenchmark/resources/cluster_configs/1.0/cluster_configs/v1/` also contains: `2gheap`, `8gheap`, `16gheap`, `24gheap`, `ea`, `fp`, `debug-non-safepoints`, `vanilla`.

17. **`--show-in-results` for `compare` not in compare.md** — benchmark.py lines 321–323.

18. **`list` missing `--limit` option docs note that it applies only to `test-runs`** — could be clearer.

---

### OpenSearch/OSB Terminology in Docs

The docs do a good job of using Solr-native terminology in most places. The following
residual issues were found:

1. `docs/reference/commands/compare.md` line 22 — describes `--baseline` / `--contender` as
   "Test execution ID" in the options table. The code uses "test run" / `test_run_id`. While
   not strictly wrong, it introduces a third term.

2. `docs/glossary.md` line 38 — correctly maps terms, but the `Collection` entry says "In OSB
   terminology: *index*" which mixes terminology in an otherwise clean page.

3. `docs/user-guide/concepts.md` line 37 — "the Solr equivalent of an OpenSearch index" is
   useful contextual info, not a bug.

4. `docs/reference/commands/run.md` line 37 — `--cluster-config` docs say "cluster config preset
   for `docker`/`from-distribution`/`from-sources` pipelines" — correct.

---

### Missing Documentation (code features not documented at all)

| Feature | Code Location |
|---------|--------------|
| `generate-data` subcommand | benchmark.py lines 169–219 |
| `create-workload` subcommand | benchmark.py lines 221–266 |
| `install` subcommand | benchmark.py lines 392–477 |
| `start` subcommand | benchmark.py lines 479–508 |
| `stop` subcommand | benchmark.py lines 510–523 |
| `visualize` subcommand | benchmark.py lines 325–336 |
| Load testing (`--load-test-qps`) | benchmark.py line 752–756 |
| Redline testing (`--redline-test` + 7 related flags) | benchmark.py lines 757–808 |
| Query randomization flags | benchmark.py lines 714–732 |
| gRPC support (`--grpc-target-hosts`) | benchmark.py lines 614–617 |
| `wait-for-merges` operation | osbenchmark/solr/runner.py line 826 |
| `paginated-search` / `scroll-search` operation aliases | osbenchmark/solr/runner.py lines 833–834 |
| `refresh` alias for `commit` | osbenchmark/solr/runner.py line 824 |
| Backup operations | osbenchmark/worker_coordinator/runner.py lines 49–53 |
| Additional cluster configs: `2gheap`, `8gheap`, `16gheap`, `24gheap`, `ea`, `fp`, `debug-non-safepoints`, `vanilla` | osbenchmark/resources/cluster_configs/1.0/cluster_configs/v1/ |
| `sleep` operation type | workload.py OperationType.Sleep |
| `composite` operation type | workload.py OperationType.Composite |

---

## Recommendations

Prioritized from most impactful to least:

1. **Fix all `--challenge` → `--test-procedure` references** across all doc files.
   This is probably the single most-confusing issue for new users who read the docs
   and then run the command.

2. **Fix `--test-execution-id` → `--test-run-id`** and `--test-executions` → `--test-runs`
   throughout `aggregate.md` and `command-flags.md`.

3. **Fix `--cluster-config-instance` → `--cluster-config`** and
   `--cluster-config-instance-params` → `--cluster-config-params` in `download.md`.

4. **Fix `optimize` parameter**: change `max-num-segments` to `max-segments` in
   `docs/reference/workloads/operations.md` and `common-operations.md`.

5. **Fix `create-collection` / `collections` field names**:
   - In `workload.json` collections array: change `"shards"` to `"num-shards"` and
     `"nrt_replicas"` to `"replication-factor"` (in `collections.md`, `operations.md`,
     `anatomy-of-a-workload.md`, `creating-custom-workloads.md`, and `common-operations.md`).
   - Add `"tlog-replicas"` and `"pull-replicas"` as valid fields in both collections
     reference and create-collection operation docs.

6. **Remove `--loglevel` and `--log-path` from `command-flags.md`** (and from the
   `configuring.md` `--loglevel` example).

7. **Remove `--results-path` and `--test-execution-id` from `command-flags.md`** and
   fix `--results-number-align` → `--results-numbers-align`.

8. **Fix `list` resource choices**: remove `test-procedures` and add `aggregated-results`
   to the table in `list.md`.

9. **Add a page for the `visualize` subcommand** to the Command Reference index.

10. **Document missing operations** (`wait-for-merges`, `soft-commit` parameter, backup ops)
    in `docs/reference/workloads/operations.md`.

11. **Expand cluster config docs** to include the 8 configs currently missing
    (`2gheap`, `8gheap`, `16gheap`, `24gheap`, `ea`, `fp`, `debug-non-safepoints`, `vanilla`).

12. **Add `generate-data` and `create-workload` subcommand pages** to the Command Reference.
    These are useful for users who want to create workloads from existing Solr indices.

13. **Document `--redline-test`** and related flags (possibly as a separate advanced-use page).

---

## CLI Flag Naming: OSB vs ASB Comparison

### Methodology

Both benchmark.py files were read in full:
- **OSB upstream base**: `git show 92982c56fa212ab6287225fb5a9bff7b96f7041b:osbenchmark/benchmark.py`
- **ASB current**: `osbenchmark/benchmark.py` on branch `purer-refactor`

A structural diff was performed on all `add_argument(...)` calls to identify every flag that was added, removed, or renamed between the two versions. Each critical discrepancy previously recorded in this document was then cross-checked against both files to determine whether the issue originated in the code (a genuine rename) or solely in the documentation.

---

### Flag Renames: Justified vs Unjustified

#### Justified Renames (Solr/ASB terminology)

| OSB Flag | ASB Flag | Reason |
|----------|----------|--------|
| `--opensearch-plugins` (`install`, `run`) | `--solr-modules` | The OSB flag installed OpenSearch plugins via configuration. ASB replaced that concept with Solr modules (`SOLR_MODULES`), which is a completely different mechanism. The rename accurately reflects the new Solr-native feature. |

#### Unjustified Renames (breaks OSB muscle memory, no clear reason)

No unjustified renames were found. Every flag that exists in OSB and still applies to ASB retained its original name. The diff between the two `benchmark.py` files shows no flag renaming beyond the justified `--opensearch-plugins` → `--solr-modules` change.

#### Docs-Only Errors (flag name was NOT changed in code, docs just used wrong name)

These flags **never existed under the "doc" name** in either OSB or ASB. The documentation was written with invented or incorrectly remembered names.

| Docs Used | Correct Flag | OSB Name | Notes |
|-----------|-------------|----------|-------|
| `--challenge` | `--test-procedure` | `--test-procedure` | OSB already used `--test-procedure`. The docs reverting to the old Elasticsearch Rally term `--challenge` is a documentation authoring error. |
| `--test-execution-id` | `--test-run-id` | `--test-run-id` | OSB already used `--test-run-id`. The "execution" variant never existed in either codebase. |
| `--test-executions` (aggregate) | `--test-runs` | `--test-runs` | OSB already used `--test-runs`. Docs invented a non-existent variant. |
| `--test-execution-id` (aggregate ID) | `--test-runs-id` | `--test-runs-id` | OSB already used `--test-runs-id`. Docs invented a non-existent variant. |
| `--loglevel` | _(does not exist)_ | _(never existed)_ | There is no `--loglevel` CLI flag in either OSB or ASB. Log level is set via `~/.solr-benchmark/logging.json`. |
| `--log-path` | _(does not exist)_ | _(never existed)_ | There is no `--log-path` CLI flag in either OSB or ASB. |
| `--results-path` | _(does not exist)_ | _(never existed)_ | There is no `--results-path` CLI flag. Results location is configured in `benchmark.ini`. |
| `--results-number-align` | `--results-numbers-align` | `--results-numbers-align` | Typo in the docs (missing the `s` in `numbers`). The correct plural form was always used in the code. |
| `--cluster-config-instance` | `--cluster-config` | `--cluster-config` | OSB already used `--cluster-config`. The `--cluster-config-instance` variant never existed. |
| `--cluster-config-instance-params` | `--cluster-config-params` | `--cluster-config-params` | OSB already used `--cluster-config-params`. The `--cluster-config-instance-params` variant never existed. |

#### New Flags (exist in ASB, not in OSB)

| Flag | Subcommand | Purpose |
|------|-----------|---------|
| `--solr-modules` | `run`, `install` | Enable Solr modules at startup (replaces `--opensearch-plugins`). Sets the `SOLR_MODULES` env var for the Solr process. |
| `--grpc-target-hosts` | `run` | gRPC endpoint list for workloads that use gRPC instead of HTTP. |
| `--load-test-qps` | `run` | Drive a fixed-QPS load test against the cluster. |
| `--redline-test` | `run` | Run an auto-scaling redline test up to a maximum QPS. |
| `--redline-scale-step` | `run` | Client count increment per step during redline scale-up. |
| `--redline-scaledown-percentage` | `run` | Percentage of clients to drop on error during redline test. |
| `--redline-post-scaledown-sleep` | `run` | Seconds to wait before scaling up again after a scale-down. |
| `--redline-max-clients` | `run` | Hard cap on concurrent clients during redline testing. |
| `--redline-max-cpu-usage` | `run` | CPU utilization ceiling; triggers client scale-back. |
| `--redline-cpu-window-seconds` | `run` | Rolling window for CPU average during CPU-based redline. |
| `--redline-cpu-check-interval` | `run` | Interval between CPU samples during CPU-based redline. |
| `--visualize` | `run` | Generate an HTML visualization after the run. |
| `--visualize-output-path` | `run` | Directory for the HTML visualization output. |
| `--test-iterations` | `run` | Repeat the workload N times (multi-run). |
| `--aggregate` | `run` | Auto-aggregate results of multi-iteration runs. |
| `--sleep-timer` | `run` | Pause between iterations in a multi-run. |
| `--cancel-on-error` | `run` | Abort remaining iterations if one iteration fails. |
| `--randomization-enabled` | `run` | Enable query randomization for the run. |
| `--randomization-repeat-frequency` | `run` | Zipf repeat-frequency parameter for query randomization. |
| `--randomization-n` | `run` | Number of standard values per field for randomization. |
| `--randomization-alpha` | `run` | Zipf alpha parameter for query randomization. |
| `--latency-percentiles` | `run` | Comma-separated percentile list for latency reporting. |
| `--throughput-percentiles` | `run` | Comma-separated percentile list for throughput reporting. |
| `convert-workload` subcommand | — | Convert an OSB/OpenSearch workload to Solr-native format. |

> Note: `--test-iterations`, `--aggregate`, `--sleep-timer`, `--cancel-on-error`, `--redline-*`, `--load-test-qps`, `--randomization-*`, `--latency-percentiles`, `--throughput-percentiles`, `--visualize`, and `--visualize-output-path` are all ASB additions that do not exist in the upstream OSB base commit. They were added as part of the Solr-specific feature set.

#### Removed Flags (existed in OSB, removed in ASB)

| Flag | Subcommand | Reason Removed |
|------|-----------|---------------|
| `--opensearch-plugins` | `run`, `install` | Replaced by `--solr-modules`. The OpenSearch plugin installation mechanism does not apply to Solr. |
| `--target-os` | `download` | Removed from the `download` subcommand. Cross-OS artifact download targeting is not needed for the ASB use case. |
| `--target-arch` | `download` | Same reason as `--target-os`. |
| `opensearch-plugins` list choice | `list` | The `list opensearch-plugins` option was removed. The valid `list` choices are now: `telemetry`, `workloads`, `pipelines`, `test-runs`, `aggregated-results`, `cluster-configs`. |

---

### Recommendations

#### Highest priority (users will fail immediately)

1. **Fix all docs-only flag name errors.** None of the "critical" discrepancies recorded in this document represent code changes — they are all documentation authoring mistakes. The correct action in every case is to **fix the docs to match the code**, not to change the code. The following specific changes are needed:
   - Replace every `--challenge` with `--test-procedure` across all doc files.
   - Replace every `--test-execution-id` with `--test-run-id`.
   - Replace `--test-executions` with `--test-runs` and `--test-execution-id` (aggregate ID) with `--test-runs-id` in `aggregate.md` and `command-flags.md`.
   - Remove `--loglevel` and `--log-path` from `command-flags.md` and `configuring.md`.
   - Remove `--results-path` from `command-flags.md`.
   - Fix `--results-number-align` → `--results-numbers-align` in `run.md`.
   - Replace `--cluster-config-instance` with `--cluster-config` and `--cluster-config-instance-params` with `--cluster-config-params` in `download.md` and `command-flags.md`.

#### Code changes to consider

2. **No code reversions are needed for OSB compatibility.** Because no flags were unjustifiably renamed (the only rename was `--opensearch-plugins` → `--solr-modules`, which is justified), there is nothing to revert to restore OSB muscle memory.

3. **Consider adding aliases for removed flags as deprecated pass-throughs.** If users who migrated from OSB are likely to use `--opensearch-plugins`, adding it as a hidden deprecated alias that maps to `--solr-modules` would ease migration. This is optional.

#### Documentation completeness

4. **Document all new ASB-only flags.** The "New Flags" table above lists 24+ flags and one subcommand (`convert-workload`) that are entirely absent from the docs. The highest-value additions to document are: `--test-iterations`/`--aggregate` (commonly needed for multi-run benchmarks), `convert-workload` (essential for migrating OSB workloads), and the `--redline-*` family (advanced but unique to ASB).
