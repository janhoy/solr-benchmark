# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Solr telemetry devices.

Three devices are provided:

  SolrJvmStats       — JVM heap + GC metrics
  SolrNodeStats      — CPU, OS memory, query handler metrics
  SolrCollectionStats — per-collection doc count, index size, segment count

Each device polls the Solr V2 API via SolrAdminClient and stores metrics
using the OSB metrics store interface.  Both Solr 9.x (custom JSON) and
Solr 10.x (Prometheus text format) are supported.

Usage:
    from osbenchmark.solr.telemetry import SolrJvmStats, SolrNodeStats, SolrCollectionStats
    from osbenchmark.solr.client import SolrAdminClient

    client = SolrAdminClient("localhost", port=8983)
    device = SolrJvmStats(client, metrics_store, sample_interval_s=5)
    device.on_benchmark_start()
    # ... run benchmark ...
    device.on_benchmark_stop()
"""

import logging
import re
import threading
import time
from abc import abstractmethod

from osbenchmark.telemetry import TelemetryDevice

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class SolrTelemetryDevice(TelemetryDevice):
    """
    Abstract base for Solr telemetry polling devices.

    Extends TelemetryDevice so that Solr devices integrate seamlessly with
    the existing osbenchmark.telemetry.Telemetry wrapper.  Setting
    ``internal = True`` means the device is always enabled (not filtered by
    the ``--telemetry`` flag).

    Subclasses implement `_collect()` which is called periodically on a
    background thread between `on_benchmark_start()` and `on_benchmark_stop()`.
    """

    # Always enabled — not selectable/deselectable via --telemetry flag.
    internal = True
    command = None
    human_name = "Solr Telemetry"
    help = "Solr-specific background polling telemetry device."

    def __init__(self, admin_client, metrics_store, sample_interval_s: float = 5.0):
        super().__init__()
        self._client = admin_client
        self._metrics_store = metrics_store
        self._sample_interval = sample_interval_s
        self._thread = None
        self._stop_event = threading.Event()

    def on_benchmark_start(self) -> None:
        """Start background polling thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def on_benchmark_stop(self) -> None:
        """Stop background polling thread and flush any remaining metrics."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._sample_interval * 2 + 5)

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._collect()
            except Exception as exc:
                logger.warning("%s: collection error: %s", self.__class__.__name__, exc)
            self._stop_event.wait(self._sample_interval)

    @abstractmethod
    def _collect(self) -> None:
        """Collect metrics and store them via self._metrics_store."""

    def _put(self, name: str, value, unit: str, task: str = "", meta: dict = None) -> None:
        """Write a single metric to the metrics store."""
        if not hasattr(self._metrics_store, "put_value_cluster_level"):
            # Simple dict-based store for testing
            self._metrics_store[name] = {"value": value, "unit": unit}
            return
        self._metrics_store.put_value_cluster_level(
            name=name, value=value, unit=unit,
            task=task, operation_type="telemetry",
            meta_data=meta or {},
        )


# ---------------------------------------------------------------------------
# Prometheus text format parser
# ---------------------------------------------------------------------------

def _parse_prometheus_text(text: str) -> dict:
    """
    Parse Prometheus exposition text format into a flat dict of {metric_name: float}.

    Lines starting with '#' are comments/help/type headers and are skipped.
    Handles optional labels: metric_name{label="value"} value [timestamp]
    """
    metrics = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Split on last whitespace run to separate value (and optional timestamp)
        parts = line.split()
        if len(parts) < 2:
            continue
        name_part = parts[0]
        try:
            value = float(parts[1])
        except ValueError:
            continue

        # Strip labels: metric_name{...} → metric_name
        base_name = re.sub(r"\{[^}]*\}", "", name_part)
        metrics[base_name] = value

    return metrics


# ---------------------------------------------------------------------------
# Device: SolrJvmStats
# ---------------------------------------------------------------------------

class SolrJvmStats(SolrTelemetryDevice):
    """
    Collect JVM heap + GC metrics from Solr.

    Metrics stored:
      - jvm_heap_used_bytes    (gauge)
      - jvm_heap_max_bytes     (gauge)
      - jvm_gc_count           (counter)
      - jvm_gc_time_ms         (counter, cumulative)

    Supports both Solr 9.x JSON and Solr 10.x Prometheus formats.
    """

    def _collect(self) -> None:
        raw = self._client.get_node_metrics()
        if isinstance(raw, str):
            self._collect_prometheus(raw)
        else:
            self._collect_json(raw)

    def _collect_json(self, data: dict) -> None:
        """Parse Solr 9.x custom JSON metrics response."""
        try:
            jvm = data.get("metrics", {}).get("solr.jvm", {})
        except AttributeError:
            logger.debug("SolrJvmStats: unexpected JSON structure")
            return

        heap_used = jvm.get("memory.heap.used")
        heap_max = jvm.get("memory.heap.max")
        gc_count = None
        gc_time = None

        # GC metrics may be nested under "gc.<collector-name>.count"
        for k, v in jvm.items():
            if k.endswith(".count") and "gc." in k:
                gc_count = (gc_count or 0) + (v or 0)
            if k.endswith(".time") and "gc." in k:
                gc_time = (gc_time or 0) + (v or 0)

        if heap_used is not None:
            self._put("jvm_heap_used_bytes", heap_used, "bytes")
        if heap_max is not None:
            self._put("jvm_heap_max_bytes", heap_max, "bytes")
        if gc_count is not None:
            self._put("jvm_gc_count", gc_count, "")
        if gc_time is not None:
            self._put("jvm_gc_time_ms", gc_time, "ms")

    def _collect_prometheus(self, text: str) -> None:
        """Parse Solr 10.x Prometheus text format."""
        m = _parse_prometheus_text(text)
        # Best-effort name mapping — metric names differ across Solr versions
        mapping = {
            "jvm_memory_heap_used_bytes": ("jvm_heap_used_bytes", "bytes"),
            "jvm_memory_heap_max_bytes": ("jvm_heap_max_bytes", "bytes"),
            "jvm_gc_collection_count": ("jvm_gc_count", ""),
            "jvm_gc_collection_time_ms": ("jvm_gc_time_ms", "ms"),
        }
        for prom_name, (osb_name, unit) in mapping.items():
            if prom_name in m:
                self._put(osb_name, m[prom_name], unit)


# ---------------------------------------------------------------------------
# Device: SolrNodeStats
# ---------------------------------------------------------------------------

class SolrNodeStats(SolrTelemetryDevice):
    """
    Collect OS and query-handler metrics from Solr.

    Metrics stored:
      - cpu_usage_percent           (gauge)
      - os_memory_free_bytes        (gauge)
      - query_handler_requests_total (counter)
      - query_handler_errors_total   (counter)
    """

    def _collect(self) -> None:
        # OS stats from /api/node/system
        try:
            resp = self._client._get("/api/node/system")
            system = resp.json()
            os_data = system.get("system", {})
            cpu = os_data.get("processCpuLoad") or os_data.get("systemCpuLoad")
            if cpu is not None:
                self._put("cpu_usage_percent", cpu * 100.0, "%")
            free_mem = os_data.get("freePhysicalMemorySize")
            if free_mem is not None:
                self._put("os_memory_free_bytes", free_mem, "bytes")
        except Exception as exc:
            logger.debug("SolrNodeStats: /api/node/system error: %s", exc)

        # Query handler metrics from /api/node/metrics
        try:
            raw = self._client.get_node_metrics()
            if isinstance(raw, str):
                m = _parse_prometheus_text(raw)
                requests_total = m.get("solr_metrics_core_query_requests_total")
                errors_total = m.get("solr_metrics_core_query_errors_total")
            else:
                handlers = raw.get("metrics", {}).get("solr.core", {})
                requests_total = handlers.get("QUERY./select.requests")
                errors_total = handlers.get("QUERY./select.errors")

            if requests_total is not None:
                self._put("query_handler_requests_total", requests_total, "")
            if errors_total is not None:
                self._put("query_handler_errors_total", errors_total, "")
        except Exception as exc:
            logger.debug("SolrNodeStats: metrics error: %s", exc)


# ---------------------------------------------------------------------------
# Device: SolrCollectionStats
# ---------------------------------------------------------------------------

class SolrCollectionStats(SolrTelemetryDevice):
    """
    Collect per-collection document count, index size, and segment count.

    Metrics stored (per collection):
      - num_docs         (gauge)
      - index_size_bytes (gauge)
      - segment_count    (gauge)

    Constructor Args:
        admin_client:     SolrAdminClient instance.
        metrics_store:    OSB metrics store.
        collections:      List of collection names to monitor (default: all).
        sample_interval_s: Polling interval in seconds.
    """

    def __init__(self, admin_client, metrics_store,
                 collections: list = None, sample_interval_s: float = 30.0):
        super().__init__(admin_client, metrics_store, sample_interval_s)
        self._collections = collections  # None = auto-discover

    def _collect(self) -> None:
        try:
            cluster = self._client.get_cluster_status()
            col_state = cluster.get("collections", {})
            target_collections = self._collections or list(col_state.keys())

            for col_name in target_collections:
                self._collect_collection(col_name)
        except Exception as exc:
            logger.debug("SolrCollectionStats: cluster status error: %s", exc)

    def _collect_collection(self, collection: str) -> None:
        """
        Fetch per-collection stats via GET /api/collections/{collection}/core-properties.
        Falls back to the luke handler for doc count.
        """
        try:
            resp = self._client._get(f"/api/collections/{collection}/core-properties")
            data = resp.json()
            # Solr returns properties per core/shard; we sum across shards
            num_docs = 0
            index_size = 0
            for core_name, props in data.get("core-properties", {}).items():
                num_docs += props.get("numDocs", 0)
                index_size += props.get("indexHeapUsageBytes", 0)

            self._put("num_docs", num_docs, "docs",
                      meta={"collection": collection})
            if index_size:
                self._put("index_size_bytes", index_size, "bytes",
                          meta={"collection": collection})
        except Exception:
            # Fallback: use the Luke request handler
            try:
                resp = self._client._get(
                    f"/solr/{collection}/admin/luke?numTerms=0&wt=json"
                )
                info = resp.json().get("index", {})
                self._put("num_docs", info.get("numDocs", 0), "docs",
                          meta={"collection": collection})
                if "segmentCount" in info:
                    self._put("segment_count", info["segmentCount"], "",
                              meta={"collection": collection})
            except Exception as exc:
                logger.debug("SolrCollectionStats: luke fallback failed for %s: %s",
                             collection, exc)
