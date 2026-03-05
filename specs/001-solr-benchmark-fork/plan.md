# Implementation Plan: Remaining Telemetry Devices

**Branch**: `001-solr-benchmark-fork` | **Date**: 2026-02-28 | **Spec**: `specs/001-solr-benchmark-fork/spec.md`
**Input**: Feature specification from `/specs/001-solr-benchmark-fork/spec.md`

## Summary

Port the remaining OSB telemetry devices to Solr Benchmark by editing the existing OSB device
classes in `osbenchmark/telemetry.py` to use Solr APIs and Solr PID file instead of OpenSearch
equivalents. Add one new Solr-only device (`ShardStats`) in `osbenchmark/solr/telemetry.py`.
Wire JVM-flag devices into the provisioner's `SOLR_OPTS` injection path.

Phase 1 (6 always-on Solr devices: `SolrJvmStats`, `SolrNodeStats`, `SolrCollectionStats`,
`SolrQueryStats`, `SolrIndexingStats`, `SolrCacheStats`) is **already complete**.

This plan covers Phase 2 (REST-based opt-in devices) and Phase 3 (JVM/PID opt-in devices):
- **Phase 2**: Edit `SegmentStats`, add `ShardStats`, edit `ClusterEnvironmentInfo`
- **Phase 3**: Edit `FlightRecorder`, `Gc`, `JitCompiler`, `Heapdump`, `DiskIo`
- **Supporting**: Update `list_telemetry()`, provisioner JVM opts injection, and tests

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: `pysolr` 3.x (data ops), `requests` (HTTP admin), `psutil` (process I/O for DiskIo), `thespian` (actor model)
**Storage**: N/A (telemetry data written to local result files via existing ResultWriter)
**Testing**: pytest (`tests/unit/test_telemetry.py`, `tests/unit/solr/test_telemetry.py`)
**Target Platform**: Linux/macOS — runs against local or remote Solr clusters
**Project Type**: Single Python package
**Performance Goals**: N/A — telemetry devices run asynchronously, outside the measured path
**Constraints**: JVM devices MUST be skipped gracefully on `benchmark-only` pipeline (no provisioner); REST devices MUST work on all pipelines
**Scale/Scope**: 8 devices edited/added; ~5 files changed; ~25 new unit tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Principle | Status |
|------|-----------|--------|
| All new/modified source files have correct license headers (ASF for new; OSB + ASF for carried-over files) | III. Source File License Headers | [X] PASS |
| No OpenSearch trademarks in user-facing code, docs, or output (outside permitted contexts) | VIII. Documentation & Branding + Trademark Rules | [X] PASS |
| No new runtime dependency on `opensearchpy` or any OpenSearch client | V. Solr-Native Scope | [X] PASS |
| New Solr-specific modules live under `osbenchmark/solr/` (`ShardStats` only) | IV. Architecture Fidelity | [X] PASS |
| Unit tests exist or are planned for all new `osbenchmark/solr/` modules | VII. Code Quality & Testing | [X] PASS |
| Terminology uses canonical Solr Benchmark terms (see Principle VI table) | VI. Terminology Consistency | [X] PASS |
| No `@author` tags added to any file | VII. Code Quality & Testing | [X] PASS |
| License is Apache 2.0; no incompatible dependency introduced | I. ASF Compliance + II. License & Attribution | [X] PASS |

**Gate result**: All PASS → proceed.

**Notes**:
- `telemetry.py` (OSB root) = Category B files (substantially modified for Solr) — OSB header + Solr attribution line
- `ShardStats` in `osbenchmark/solr/telemetry.py` = Category C (new Solr file) — full ASF header
- `psutil` is already in `setup.py` as an existing dependency; no new dependency added

## Project Structure

### Documentation (this feature)

```text
specs/001-solr-benchmark-fork/
├── plan.md              # This file
├── research.md          # Phase 0 output (sections 1–7 complete)
├── data-model.md        # N/A — no new data entities; telemetry API shapes documented in research.md §7
├── quickstart.md        # Phase 1 output (below)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
osbenchmark/
├── telemetry.py               # Edit: SegmentStats, FlightRecorder, Gc, JitCompiler, Heapdump, DiskIo, ClusterEnvironmentInfo
├── solr/
│   ├── telemetry.py           # Add: ShardStats class
│   └── provisioner.py         # Edit: JVM opts injection in _build_env() and _cluster_config_env_flags()
└── worker_coordinator/
    └── worker_coordinator.py  # Edit: _create_solr_telemetry_devices() — register ShardStats + updated devices

tests/
├── unit/
│   ├── test_telemetry.py      # Edit: update SegmentStats, DiskIo, Heapdump, ClusterEnvironmentInfo tests
│   └── solr/
│       └── test_telemetry.py  # Add: ShardStats tests
```

**Structure Decision**: No new directories or packages needed. This is a focused edit pass — existing modules receive Solr API calls in place of OpenSearch client calls.

## Phase 0: Research Findings

> Research is complete. See `research.md` §7 (Telemetry Device Portability Research).

Key decisions:
1. **Class names unchanged** — device flag values (`--telemetry=segment-stats`) keep OSB names
2. **Edit, don't dual-mode** — old OpenSearch code paths are removed, not kept alongside Solr
3. **`ShardStats` is new** — no OSB equivalent; goes in `osbenchmark/solr/telemetry.py`
4. **JVM opts via SOLR_OPTS** — `instrument_java_opts()` return values appended to `SOLR_OPTS` env var
5. **PID from file** — `{solr_root}/bin/solr-{port}.pid`; Docker via `docker inspect`
6. **Metrics format dual-support** — `_fetch_node_metrics_parsed()` already handles Solr 9.x JSON and 10.x Prometheus

## Phase 1: Design

### Device Inventory

| Device | Class location (after port) | Pipeline support |
|--------|----------------------------|------------------|
| `segment-stats` | `osbenchmark/telemetry.py` — edit `SegmentStats` | All |
| `shard-stats` | `osbenchmark/solr/telemetry.py` — new `ShardStats` | All |
| `cluster-environment-info` | `osbenchmark/telemetry.py` — edit `ClusterEnvironmentInfo` | All |
| `jfr` | `osbenchmark/telemetry.py` — edit `FlightRecorder` | Provisioned only |
| `gc` | `osbenchmark/telemetry.py` — edit `Gc` | Provisioned only |
| `jit` | `osbenchmark/telemetry.py` — edit `JitCompiler` | Provisioned only |
| `heapdump` | `osbenchmark/telemetry.py` — edit `Heapdump` | Provisioned only |
| `disk-io` | `osbenchmark/telemetry.py` — edit `DiskIo` | Provisioned only |

### Devices NOT to port (remove from list_telemetry if present)

`ccr-stats`, `transform-stats`, `searchable-snapshots-stats`, `segment-replication-stats`, `MlBucketProcessingTime` — OpenSearch-only concepts; no Solr equivalent.

### API Specifications

**SegmentStats** — per collection, called each `record()` iteration:
```
GET /solr/{collection}/admin/luke?numTerms=0&wt=json
Response: {"index": {"numDocs": N, "maxDoc": N, "deletedDocs": N, "segmentCount": N, "indexHeapUsageBytes": N}}
Emit: segment_numdocs, segment_maxdoc, segment_deleteddocs, segment_segmentcount, segment_indexheapusagebytes
```

**ShardStats** — per collection, called each `record()` iteration:
```
GET /solr/admin/collections?action=CLUSTERSTATUS
  → enumerate active shard leaders → list of (core_name, node_host, node_port)
GET /solr/admin/cores?action=STATUS&core={core_name}
  → status.{core}.index.{numDocs, sizeInBytes}
Emit: shard_num_docs, shard_size_bytes (labelled by shard name)
SolrCloud check: if CLUSTERSTATUS cluster.collections is absent/empty → skip silently
```

**ClusterEnvironmentInfo** — called once at `on_benchmark_start()`:
```
GET /api/node/system
  → lucene.solr-spec-version, jvm.version, jvm.name, system.name, system.availableProcessors
GET /solr/admin/collections?action=CLUSTERSTATUS
  → node count, collection list
Emit as environment info key-value pairs (not time-series metrics)
```

**JVM devices (FlightRecorder, Gc, JitCompiler)** — called at `instrument_java_opts()`:
- Return list of JVM flags (strings)
- Provisioner collects from all active JVM devices and appends to `SOLR_OPTS`
- Device detects `benchmark-only` via `self.telemetry_params.get("pipeline", "")` and returns `[]` with a WARNING log

**Heapdump** — called at `on_benchmark_stop()`:
```
Read PID from provisioner-supplied node.pid (set via SolrProvisioner.start())
Execute: jmap -dump:format=b,file={output}.hprof {pid}
Docker: docker exec {container_name} jmap -dump:format=b,file={output}.hprof {pid}
```

**DiskIo** — called each `record()` iteration:
```
Read PID from provisioner-supplied node.pid
psutil.Process(pid).io_counters() → read_bytes, write_bytes, read_count, write_count
Emit: disk_io_read_bytes, disk_io_write_bytes, disk_io_read_count, disk_io_write_count
```

### JVM Opts Injection Architecture

```python
# In SolrProvisioner._build_env() / SolrDockerLauncher._cluster_config_env_flags():
jvm_extra = []
for device in self.telemetry_devices:
    if hasattr(device, "instrument_java_opts"):
        jvm_extra.extend(device.instrument_java_opts())
# Append to existing SOLR_OPTS value:
existing_opts = env.get("SOLR_OPTS", "")
env["SOLR_OPTS"] = (existing_opts + " " + " ".join(jvm_extra)).strip()
```

`self.telemetry_devices` is passed to the provisioner by the orchestrator before `prepare()` is called.

### list_telemetry() Update

Current `list_telemetry()` incorrectly labels ported devices as "OpenSearch-only". After this implementation:

- **Section "Always-on Solr devices"**: `SolrJvmStats`, `SolrNodeStats`, `SolrCollectionStats`, `SolrQueryStats`, `SolrIndexingStats`, `SolrCacheStats`
- **Section "Optional REST devices (all pipelines)"**: `SegmentStats`, `ShardStats`, `ClusterEnvironmentInfo`
- **Section "Optional JVM/process devices (provisioned pipelines only)"**: `FlightRecorder`, `Gc`, `JitCompiler`, `Heapdump`, `DiskIo`
- **Remove entirely**: `ccr-stats`, `transform-stats`, `searchable-snapshots-stats`, `segment-replication-stats`, `MlBucketProcessingTime`

## Quickstart: Enabling Optional Telemetry Devices

After implementation, users enable optional devices with `--telemetry`:

```bash
# Enable segment statistics collection
solr-benchmark run \
  --pipeline benchmark-only \
  --target-hosts localhost:8983 \
  --workload nyc_taxis \
  --telemetry segment-stats,cluster-environment-info

# Enable GC logging on a provisioned cluster (flags injected into SOLR_OPTS)
solr-benchmark run \
  --pipeline docker \
  --distribution-version 9.10.1 \
  --workload nyc_taxis \
  --telemetry gc,jfr
```

Results appear in the test-run JSON alongside metrics from always-on devices.

```bash
# View telemetry output for the most recent run
cat ~/.solr-benchmark/benchmarks/test-runs/$(ls -t ~/.solr-benchmark/benchmarks/test-runs/ | head -1)/test_run.json | python3 -m json.tool | grep segment_
```
