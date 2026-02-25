# Implementation Plan: cluster_config + Collection Settings + Logging Fix

**Branch**: `001-solr-benchmark-fork` | **Date**: 2026-02-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-solr-benchmark-fork/spec.md`
**Scope**: Three focused requirements (Krav 1–3) from 2026-02-25 clarification session.

---

## Summary

Three targeted improvements to the Solr Benchmark fork:

1. **Krav 1 — Logging fix**: `cluster_config [['external']]` → `cluster_config [external]` (double-bracket rendering bug in `test_run_orchestrator.py`).
2. **Krav 2 — Collection settings**: Add `shards`, `nrt_replicas`, `pull_replicas`, `tlog_replicas` fields to `workload.json` collections (with backward-compat aliases). Thread the values through `Collection` class → `SolrCreateCollection` runner → `SolrAdminClient.create_collection()` → Solr V2 API.
3. **Krav 3 — cluster_config for Solr**: Integrate the existing `ClusterConfigInstanceLoader` mechanism with `SolrProvisioner` and `SolrDockerLauncher`. Translate INI variables (`heap_size`, `gc_tune`, `solr_opts`) to Solr env vars (`SOLR_HEAP`, `GC_TUNE`, `SOLR_OPTS`) at provisioner startup. Validate that `--cluster-config` is not used with `benchmark-only` pipeline.

---

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: pysolr 3.x, requests, thespian (actor model), pytest
**Storage**: Local filesystem — JSON/CSV result files, SQLite test-runs store
**Testing**: pytest — tests under `tests/unit/solr/`
**Target Platform**: Linux/macOS server, Docker
**Project Type**: Single Python package (`osbenchmark/`)
**Performance Goals**: N/A for this change (infrastructure/config only)
**Constraints**: macOS fork-safety (`trust_env=False` on all sessions in forked processes); no external deps added

---

## Constitution Check

Constitution file is a placeholder (unfilled). Using project conventions derived from CLAUDE.md:

- ✅ Solr-only execution path (no OpenSearch/dual-mode introduced)
- ✅ No new external dependencies
- ✅ Unit tests required for all new logic
- ✅ `requests.Session.trust_env = False` on all sessions created post-fork
- ✅ Runners remain `async_runner=True`
- ✅ Admin ops use V2 API (V1 configset upload allowed as known exception per R&D)

---

## Project Structure

### Documentation (this feature)

```text
specs/001-solr-benchmark-fork/
├── plan.md              ← This file
├── research.md          ← Phase 0 output (updated 2026-02-25)
├── data-model.md        ← Phase 1 output (updated 2026-02-25)
├── quickstart.md        ← Phase 1 output
├── contracts/           ← Phase 1 output
└── tasks.md             ← Phase 2 output (/speckit.tasks)
```

### Source Code (affected files)

```text
osbenchmark/
├── test_run_orchestrator.py     ← Krav 1: fix cluster_config log format
│                                   Krav 3: add benchmark-only guard
├── benchmark.py                 ← Krav 3: --cluster-config validation
├── workload/
│   ├── workload.py              ← Krav 2: Collection class new fields
│   └── loader.py                ← Krav 2: parse new workload.json fields
├── solr/
│   ├── runner.py                ← Krav 2: SolrCreateCollection reads new params
│   ├── client.py                ← Krav 2: create_collection() new signature
│   └── provisioner.py          ← Krav 3: SolrProvisioner + SolrDockerLauncher
│                                          accept & apply cluster_config
└── resources/cluster_configs/main/cluster_configs/v1/
    ├── g1gc.ini                 ← Krav 3: add gc_tune variable
    └── parallelgc.ini           ← Krav 3: add gc_tune variable

tests/unit/solr/
├── test_runner.py               ← Krav 2: tests for new collection params
├── test_client.py               ← Krav 2: tests for new create_collection sig
├── test_provisioner.py          ← Krav 3: tests for env var application
└── test_cluster_config.py       ← Krav 3: tests for benchmark-only guard
```

---

## Phase 0: Research — COMPLETE

See [research.md](research.md) sections R-05, R-06, R-07.

Key findings:
- **Logging bug** (R-07): `self.test_run.cluster_config` is a list; format string renders it as `[['external']]`. Fix: `", ".join(names)`.
- **cluster_config INI** (R-05): Files exist at `osbenchmark/resources/cluster_configs/main/cluster_configs/v1/`. Variables `heap_size` → `SOLR_HEAP`, `gc_tune` → `GC_TUNE`, `solr_opts` → `SOLR_OPTS`.
- **Collection fields** (R-06): Solr V2 API supports `nrtReplicas`, `tlogReplicas`, `pullReplicas` directly. Replace `replication-factor` (→ `nrt_replicas`) with full three-type model.

---

## Phase 1: Design

### Krav 1 — Logging Fix

**File**: `osbenchmark/test_run_orchestrator.py`

Two call sites (~lines 297 and 305). Current code:
```python
console.info("...cluster_config [{}]...".format(self.test_run.cluster_config, ...))
```

Fix — produce a comma-joined string:
```python
cluster_cfg_display = ", ".join(self.test_run.cluster_config or ["none"])
console.info("...cluster_config [{}]...".format(cluster_cfg_display, ...))
```

No other changes needed. This is a pure display fix.

---

### Krav 2 — Collection Settings

Field naming: keep existing hyphen-style names (`num-shards`, `replication-factor`). `replication-factor` is an alias for nrt-replicas (semantically identical in SolrCloud). Only ADD the two new fields: `pull-replicas` and `tlog-replicas`.

#### 2a. `Collection` class (`osbenchmark/workload/workload.py`)

Add two new fields only — keep `num_shards` and `replication_factor` unchanged:

```python
class Collection:
    def __init__(self, name, configset=None, configset_path=None,
                 num_shards=1, replication_factor=1,
                 pull_replicas=0, tlog_replicas=0):   # ← only these two are new
        ...
        self.pull_replicas = pull_replicas
        self.tlog_replicas = tlog_replicas
```

#### 2b. Workload loader (`osbenchmark/workload/loader.py`)

Add two new reads only — keep existing `num-shards` and `replication-factor` reads:

```python
pull_replicas = int(self._r(col_spec, "pull-replicas", mandatory=False, default_value=0))
tlog_replicas = int(self._r(col_spec, "tlog-replicas", mandatory=False, default_value=0))
return workload.Collection(..., pull_replicas=pull_replicas, tlog_replicas=tlog_replicas)
```

#### 2b². `CreateCollectionParamSource` (`osbenchmark/workload/params.py`)

Add `"pull-replicas"` and `"tlog-replicas"` to both `collection_def` dicts (lines ~469–485):

```python
"pull-replicas": col.pull_replicas,
"tlog-replicas": col.tlog_replicas,
```

#### 2c. `SolrAdminClient.create_collection()` (`osbenchmark/solr/client.py`)

Add two params, replace `replicationFactor` with `nrtReplicas` in payload:

```python
def create_collection(self, name, configset,
                      num_shards=1, replication_factor=1,
                      tlog_replicas=0, pull_replicas=0, ...):
    payload = {
        "name": name,
        "config": configset,
        "numShards": num_shards,
        "nrtReplicas": replication_factor,   # replication-factor = nrt replicas
        "tlogReplicas": tlog_replicas,
        "pullReplicas": pull_replicas,
        "waitForFinalState": True,
    }
```

#### 2d. `SolrCreateCollection` runner (`osbenchmark/solr/runner.py`)

Add two new param reads — keep existing `num-shards` / `replication-factor` reads:

```python
tlog_replicas = params.get("tlog-replicas", 0)
pull_replicas = params.get("pull-replicas", 0)
await _run_in_executor(
    admin.create_collection,
    collection, configset, num_shards, replication_factor, tlog_replicas, pull_replicas,
)
```

---

### Krav 3 — cluster_config for Solr

#### 3a. INI files — add `gc_tune` variable

`g1gc.ini`:
```ini
[meta]
description=Use G1 Garbage Collector

[config]
base=vanilla

[variables]
gc_tune=-XX:+UseG1GC -XX:+UseStringDeduplication
```

`parallelgc.ini`:
```ini
[meta]
description=Use Parallel Garbage Collector

[config]
base=vanilla

[variables]
gc_tune=-XX:+UseParallelGC
```

(Remove old `use_g1_gc=true` / `use_parallel_gc=true` variables which were only used by the OSB Jinja2 template.)

#### 3b. `SolrProvisioner` (`osbenchmark/solr/provisioner.py`)

Add `cluster_config` parameter to `__init__` and `start()`:

```python
class SolrProvisioner:
    def __init__(self, ..., cluster_config=None):
        ...
        self.cluster_config = cluster_config

    def _build_env(self):
        """Build subprocess environment with Solr env vars from cluster_config."""
        env = os.environ.copy()
        if self.cluster_config:
            vars_ = self.cluster_config.variables
            if "heap_size" in vars_:
                env["SOLR_HEAP"] = vars_["heap_size"]
            if "gc_tune" in vars_:
                env["GC_TUNE"] = vars_["gc_tune"]
            if "solr_opts" in vars_:
                env["SOLR_OPTS"] = vars_["solr_opts"]
        return env

    def start(self, solr_root, mode=None):
        cmd = [bin_solr, "start", "-p", str(self.port), ...]
        result = subprocess.run(cmd, env=self._build_env(), ...)
```

#### 3c. `SolrDockerLauncher` (`osbenchmark/solr/provisioner.py`)

Add `-e KEY=VALUE` flags to `docker run`:

```python
def _cluster_config_env_flags(self):
    flags = []
    if self.cluster_config:
        vars_ = self.cluster_config.variables
        mapping = {"heap_size": "SOLR_HEAP", "gc_tune": "GC_TUNE", "solr_opts": "SOLR_OPTS"}
        for ini_key, env_key in mapping.items():
            if ini_key in vars_:
                flags += ["-e", f"{env_key}={vars_[ini_key]}"]
    return flags

def start(self, version_tag="9", mode=None):
    cmd = ["docker", "run", "--rm", "--name", self.container_name,
           "-p", f"{self.port}:8983", "-d"]
    cmd += self._cluster_config_env_flags()
    cmd.append(image)
    ...
```

#### 3d. Provisioner wiring (`osbenchmark/test_run_orchestrator.py` or `builder/`)

Where `SolrProvisioner` / `SolrDockerLauncher` is instantiated, pass the loaded `cluster_config` instance.

The `cluster_config` is loaded via:
```python
from osbenchmark.builder import cluster_config as cluster_config_module
cfg_instance = cluster_config_module.load_cluster_config(
    repo=...,
    name=self.config.opts("builder", "cluster_config.names")[0],
    cluster_config_params=self.config.opts("builder", "cluster_config.params"),
)
```

#### 3e. `benchmark-only` validation (`osbenchmark/benchmark.py`)

In `configure_builder_params()`, after reading `args.cluster_config`:

```python
pipeline = cfg.opts("test_execution", "pipeline")
if pipeline == "benchmark-only" and args.cluster_config != "defaults":
    raise SystemExit(
        "ERROR: --cluster-config is only valid for provisioning pipelines "
        "(from-distribution, docker, from-sources). "
        "It cannot be used with the 'benchmark-only' pipeline."
    )
```

---

## Test Plan

### Unit Tests

| Test | File | What it covers |
|---|---|---|
| `test_cluster_config_log_format` | `test_run_orchestrator` | Verifies `cluster_config [external]` not `[['external']]` |
| `test_collection_new_fields_defaults` | `test_workload_loader` | Parses workload.json with no topology fields → defaults |
| `test_collection_new_fields_explicit` | `test_workload_loader` | Parses `shards=2, nrt_replicas=2, tlog_replicas=1, pull_replicas=0` |
| `test_collection_backward_compat` | `test_workload_loader` | Old `num-shards` / `replication-factor` still parsed |
| `test_create_collection_new_params` | `test_client` | `create_collection()` sends `nrtReplicas`, `tlogReplicas`, `pullReplicas` |
| `test_create_collection_runner_new_params` | `test_runner` | Runner reads new params, passes to admin client |
| `test_provisioner_heap_env` | `test_provisioner` | `SolrProvisioner._build_env()` sets `SOLR_HEAP=4g` from `4gheap` config |
| `test_provisioner_gc_env` | `test_provisioner` | `_build_env()` sets `GC_TUNE` from `g1gc` config |
| `test_provisioner_no_config` | `test_provisioner` | No env vars set when `cluster_config=None` |
| `test_docker_env_flags` | `test_provisioner` | `_cluster_config_env_flags()` produces `-e SOLR_HEAP=4g` |
| `test_benchmark_only_rejects_cluster_config` | `test_benchmark` | `--cluster-config 4gheap` with `benchmark-only` raises `SystemExit` |

---

## Implementation Order

Tasks to be broken down in `/speckit.tasks`. Suggested sequence:

1. **T-A**: Fix logging bug in `test_run_orchestrator.py` (trivial, 5 min, zero risk)
2. **T-B**: Update `Collection` class fields + loader backward-compat
3. **T-C**: Update `SolrAdminClient.create_collection()` signature + tests
4. **T-D**: Update `SolrCreateCollection` runner to read new params
5. **T-E**: Update GC INI configs (`g1gc.ini`, `parallelgc.ini`) with `gc_tune`
6. **T-F**: Add `_build_env()` + `_cluster_config_env_flags()` to provisioners
7. **T-G**: Wire cluster_config loading into provisioner instantiation
8. **T-H**: Add `benchmark-only` + `--cluster-config` guard in `benchmark.py`
9. **T-I**: Unit tests for all above

---

## Artifacts Generated

- ✅ `research.md` — updated with R-05, R-06, R-07
- ✅ `data-model.md` — Collection entity updated; ClusterConfig entity added
- ✅ `plan.md` — this file
- `tasks.md` — next step: `/speckit.tasks`
