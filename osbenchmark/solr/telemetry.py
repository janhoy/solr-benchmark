# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
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

Devices provided:

  SolrJvmStats        — JVM heap, GC, threads, buffer pools
  SolrNodeStats       — CPU, OS memory, file descriptors, HTTP, query handler metrics
  SolrCollectionStats — per-collection doc count, index size, segment count, deleted docs
  SolrQueryStats      — query latency percentiles and cache hit ratios
  SolrIndexingStats   — indexing throughput and merge metrics
  SolrCacheStats      — Solr internal cache statistics (query, filter, document caches)

Each device polls the Solr V2 API via SolrAdminClient and stores metrics
using the OSB metrics store interface.  Both Solr 9.x (custom JSON) and
Solr 10.x (Prometheus text format) are supported for the /admin/metrics endpoint,
satisfying Constitution Principle VII (dual-format rule).

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
from abc import abstractmethod

from osbenchmark.telemetry import TelemetryDevice

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prometheus text format parser
# ---------------------------------------------------------------------------

def _parse_prometheus_text(text: str) -> dict:
    """
    Parse Prometheus exposition text format into a flat dict of {metric_name: float}.

    Lines starting with '#' are comments/help/type headers and are skipped.
    Handles optional labels: metric_name{label="value"} value [timestamp]

    When multiple series share the same base metric name (different labels),
    values are accumulated (summed). This provides aggregate totals across
    cores and collections for Solr telemetry use cases.
    """
    metrics = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
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
        # Accumulate values with matching base name (sums across label dimensions)
        metrics[base_name] = metrics.get(base_name, 0.0) + value

    return metrics


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

    Dual-format helper methods (Constitution Principle VII):

    Devices that query /admin/metrics MUST handle both response formats.
    Use the provided helpers to do so consistently:

      - `_fetch_node_metrics_parsed()` — fetch /admin/metrics, auto-detect format
        (JSON or Prometheus), and return `(format_str, data_dict)` where
        ``format_str`` is ``"json"`` or ``"prometheus"`` and ``data_dict`` is
        always a regular Python dict.
      - `_get_metric_json(data, *keys, default=None)` — navigate a nested
        JSON dict using successive key lookups (handles Solr dot-containing keys).
      - `_get_metric_prometheus(data, metric_name, default=None)` — look up
        a metric name from a parsed Prometheus dict.

    Typical device pattern::

        def _collect(self):
            fmt, data = self._fetch_node_metrics_parsed()
            if fmt == "json":
                self._collect_json(data)
            else:
                self._collect_prometheus(data)

        def _collect_json(self, data):
            val = self._get_metric_json(data, "metrics", "solr.jvm", "threads.count")
            if val is not None:
                self._put("jvm_thread_count", val, "")

        def _collect_prometheus(self, data):
            val = self._get_metric_prometheus(data, "solr_metrics_jvm_threads_count")
            if val is not None:
                self._put("jvm_thread_count", val, "")
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

    # ------------------------------------------------------------------
    # Dual-format helpers (satisfy Constitution Principle VII)
    # ------------------------------------------------------------------

    def _fetch_node_metrics_parsed(self):
        """
        Fetch /admin/metrics and return ``(format_str, data_dict)``.

        ``format_str`` is ``"json"`` or ``"prometheus"``.
        ``data_dict`` is always a regular Python dict:
          - For JSON responses:      the raw parsed dict from Solr
          - For Prometheus responses: the result of ``_parse_prometheus_text()``

        Detection is based on the Content-Type returned by
        ``SolrAdminClient.get_node_metrics()``:
          - dict → JSON (Solr pre-10.0)
          - str  → Prometheus text (Solr 10.0+)
        """
        raw = self._client.get_node_metrics()
        if isinstance(raw, str):
            return "prometheus", _parse_prometheus_text(raw)
        return "json", raw if isinstance(raw, dict) else {}

    @staticmethod
    def _get_metric_json(data: dict, *keys, default=None):
        """
        Navigate a nested dict using successive key lookups.

        Solr JSON metric keys often contain dots (e.g. ``"memory.heap.used"``),
        so a split-on-dot approach would be ambiguous.  Pass each nested key
        as a separate argument instead::

            _get_metric_json(data, "metrics", "solr.jvm", "threads.count")

        Returns ``default`` if any key is missing or the value is ``None``.
        """
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
            if current is None:
                return default
        return current

    @staticmethod
    def _get_metric_prometheus(data: dict, metric_name: str, default=None):
        """
        Look up a metric by exact base name from a parsed Prometheus dict.

        ``data`` is expected to be the output of ``_parse_prometheus_text()``.
        Returns ``default`` if the metric is not present.
        """
        return data.get(metric_name, default)

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
# Device: SolrJvmStats
# ---------------------------------------------------------------------------

class SolrJvmStats(SolrTelemetryDevice):
    """
    Collect JVM heap, GC, thread, and buffer pool metrics from Solr.

    Metrics stored:
      - jvm_heap_used_bytes           (gauge)
      - jvm_heap_max_bytes            (gauge)
      - jvm_gc_count                  (counter, cumulative across all collectors)
      - jvm_gc_time_ms                (counter, cumulative across all collectors)
      - jvm_gc_young_count            (counter, young-generation GC cycles)
      - jvm_gc_young_time_ms          (counter, young-generation GC wall time)
      - jvm_gc_old_count              (counter, old-generation GC cycles)
      - jvm_gc_old_time_ms            (counter, old-generation GC wall time)
      - jvm_thread_count              (gauge)
      - jvm_thread_peak_count         (gauge)
      - jvm_buffer_pool_direct_bytes  (gauge, direct byte buffer pool usage)
      - jvm_buffer_pool_mapped_bytes  (gauge, memory-mapped buffer pool usage)

    Supports both Solr 9.x JSON and Solr 10.x Prometheus formats.
    """

    human_name = "Solr JVM Stats"
    help = "JVM heap, GC (total/young/old), threads, and buffer pool metrics"

    def _collect(self) -> None:
        fmt, data = self._fetch_node_metrics_parsed()
        if fmt == "prometheus":
            self._collect_prometheus(data)
        else:
            self._collect_json(data)

    def _collect_json(self, data: dict) -> None:
        """Parse Solr 9.x custom JSON metrics response."""
        jvm = self._get_metric_json(data, "metrics", "solr.jvm") or {}

        heap_used = jvm.get("memory.heap.used")
        heap_max = jvm.get("memory.heap.max")
        if heap_used is not None:
            self._put("jvm_heap_used_bytes", heap_used, "bytes")
        if heap_max is not None:
            self._put("jvm_heap_max_bytes", heap_max, "bytes")

        # Thread counts
        thread_count = jvm.get("threads.count")
        thread_peak = jvm.get("threads.peak.count")
        if thread_count is not None:
            self._put("jvm_thread_count", thread_count, "")
        if thread_peak is not None:
            self._put("jvm_thread_peak_count", thread_peak, "")

        # Buffer pools (direct and memory-mapped)
        direct_bytes = jvm.get("buffers.direct.MemoryUsed")
        mapped_bytes = jvm.get("buffers.mapped.MemoryUsed")
        if direct_bytes is not None:
            self._put("jvm_buffer_pool_direct_bytes", direct_bytes, "bytes")
        if mapped_bytes is not None:
            self._put("jvm_buffer_pool_mapped_bytes", mapped_bytes, "bytes")

        # GC metrics — aggregate across all collectors and split young/old
        gc_count_total = None
        gc_time_total = None
        gc_young_count = None
        gc_young_time = None
        gc_old_count = None
        gc_old_time = None

        for k, v in jvm.items():
            if v is None:
                continue
            if k.endswith(".count") and "gc." in k:
                gc_count_total = (gc_count_total or 0) + v
                k_lower = k.lower()
                if "young" in k_lower or "minor" in k_lower or "eden" in k_lower:
                    gc_young_count = (gc_young_count or 0) + v
                elif "old" in k_lower or "major" in k_lower or "tenured" in k_lower:
                    gc_old_count = (gc_old_count or 0) + v
            if k.endswith(".time") and "gc." in k:
                gc_time_total = (gc_time_total or 0) + v
                k_lower = k.lower()
                if "young" in k_lower or "minor" in k_lower or "eden" in k_lower:
                    gc_young_time = (gc_young_time or 0) + v
                elif "old" in k_lower or "major" in k_lower or "tenured" in k_lower:
                    gc_old_time = (gc_old_time or 0) + v

        if gc_count_total is not None:
            self._put("jvm_gc_count", gc_count_total, "")
        if gc_time_total is not None:
            self._put("jvm_gc_time_ms", gc_time_total, "ms")
        if gc_young_count is not None:
            self._put("jvm_gc_young_count", gc_young_count, "")
        if gc_young_time is not None:
            self._put("jvm_gc_young_time_ms", gc_young_time, "ms")
        if gc_old_count is not None:
            self._put("jvm_gc_old_count", gc_old_count, "")
        if gc_old_time is not None:
            self._put("jvm_gc_old_time_ms", gc_old_time, "ms")

    def _collect_prometheus(self, data: dict) -> None:
        """
        Parse Solr 10.x Prometheus text format.

        Metric name mappings are best-effort; exact names depend on Solr version
        and the Prometheus exporter configuration.
        """
        mapping = {
            "jvm_memory_heap_used_bytes": ("jvm_heap_used_bytes", "bytes"),
            "jvm_memory_heap_max_bytes": ("jvm_heap_max_bytes", "bytes"),
            "jvm_gc_collection_count": ("jvm_gc_count", ""),
            "jvm_gc_collection_time_ms": ("jvm_gc_time_ms", "ms"),
            "jvm_threads_current": ("jvm_thread_count", ""),
            "jvm_threads_peak": ("jvm_thread_peak_count", ""),
            "jvm_buffer_pool_used_bytes": ("jvm_buffer_pool_direct_bytes", "bytes"),
        }
        for prom_name, (osb_name, unit) in mapping.items():
            val = self._get_metric_prometheus(data, prom_name)
            if val is not None:
                self._put(osb_name, val, unit)


# ---------------------------------------------------------------------------
# Device: SolrNodeStats
# ---------------------------------------------------------------------------

class SolrNodeStats(SolrTelemetryDevice):
    """
    Collect OS, file-descriptor, HTTP, and query-handler metrics from Solr.

    Metrics stored:
      - cpu_usage_percent              (gauge)
      - os_memory_free_bytes           (gauge)
      - node_file_descriptors_open     (gauge)
      - node_file_descriptors_max      (gauge)
      - node_http_requests_total       (counter, Jetty total requests)
      - query_handler_requests_total   (counter)
      - query_handler_errors_total     (counter)
      - query_handler_avg_latency_ms   (gauge, rolling mean)
    """

    human_name = "Solr Node Stats"
    help = "CPU usage, OS memory, file descriptors, HTTP requests, and query handler latency"

    def _collect(self) -> None:
        self._collect_system_stats()
        self._collect_metrics_stats()

    def _collect_system_stats(self) -> None:
        """Fetch OS stats from /api/node/system."""
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

            open_fds = os_data.get("openFileDescriptorCount")
            max_fds = os_data.get("maxFileDescriptorCount")
            if open_fds is not None:
                self._put("node_file_descriptors_open", open_fds, "")
            if max_fds is not None:
                self._put("node_file_descriptors_max", max_fds, "")
        except Exception as exc:
            logger.debug("SolrNodeStats: /api/node/system error: %s", exc)

    def _collect_metrics_stats(self) -> None:
        """Fetch query handler and HTTP stats from /admin/metrics."""
        try:
            fmt, data = self._fetch_node_metrics_parsed()
            if fmt == "prometheus":
                self._collect_metrics_prometheus(data)
            else:
                self._collect_metrics_json(data)
        except Exception as exc:
            logger.debug("SolrNodeStats: metrics error: %s", exc)

    def _collect_metrics_json(self, data: dict) -> None:
        core = self._get_metric_json(data, "metrics", "solr.core") or {}

        requests = core.get("QUERY./select.requests")
        errors = core.get("QUERY./select.errors")
        avg_latency = core.get("QUERY./select.requestTimes.mean")

        if requests is not None:
            self._put("query_handler_requests_total", requests, "")
        if errors is not None:
            self._put("query_handler_errors_total", errors, "")
        if avg_latency is not None:
            self._put("query_handler_avg_latency_ms", avg_latency, "ms")

        jetty = self._get_metric_json(data, "metrics", "solr.jetty") or {}
        http_requests = jetty.get(
            "org.eclipse.jetty.server.handler.StatisticsHandler.requests"
        )
        if http_requests is not None:
            self._put("node_http_requests_total", http_requests, "")

    def _collect_metrics_prometheus(self, data: dict) -> None:
        mapping = {
            "solr_metrics_core_query_requests_total": ("query_handler_requests_total", ""),
            "solr_metrics_core_query_errors_total": ("query_handler_errors_total", ""),
            "solr_metrics_core_query_request_times_mean_ms": ("query_handler_avg_latency_ms", "ms"),
            "solr_metrics_jetty_requests_total": ("node_http_requests_total", ""),
        }
        for prom_name, (osb_name, unit) in mapping.items():
            val = self._get_metric_prometheus(data, prom_name)
            if val is not None:
                self._put(osb_name, val, unit)


# ---------------------------------------------------------------------------
# Device: SolrCollectionStats
# ---------------------------------------------------------------------------

class SolrCollectionStats(SolrTelemetryDevice):
    """
    Collect per-collection document count, index size, segment count, and deleted docs.

    Metrics stored (per collection, with ``collection`` meta tag):
      - num_docs         (gauge)
      - index_size_bytes (gauge)
      - segment_count    (gauge)
      - num_deleted_docs (gauge)

    Constructor Args:
        admin_client:     SolrAdminClient instance.
        metrics_store:    OSB metrics store.
        collections:      List of collection names to monitor (default: all).
        sample_interval_s: Polling interval in seconds.
    """

    human_name = "Solr Collection Stats"
    help = "Per-collection: doc count, deleted docs, index size, and segment count (30 s interval)"

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
        Fetch per-collection stats via the core-properties API.
        Falls back to /admin/luke for doc count and segment info.
        """
        try:
            resp = self._client._get(f"/api/collections/{collection}/core-properties")
            data = resp.json()
            num_docs = 0
            index_size = 0
            for _core_name, props in data.get("core-properties", {}).items():
                num_docs += props.get("numDocs", 0)
                index_size += props.get("indexHeapUsageBytes", 0)

            self._put("num_docs", num_docs, "docs", meta={"collection": collection})
            if index_size:
                self._put("index_size_bytes", index_size, "bytes",
                          meta={"collection": collection})
        except Exception:
            pass

        # Always fetch Luke stats for segment info and deleted docs
        self._fetch_luke_stats(collection)

    def _fetch_luke_stats(self, collection: str) -> None:
        """
        Fetch index statistics via the Luke request handler.

        Provides deleted doc count and segment count, which are not available
        from the core-properties API.
        """
        try:
            resp = self._client._get(
                f"/solr/{collection}/admin/luke?numTerms=0&wt=json"
            )
            info = resp.json().get("index", {})
            num_docs = info.get("numDocs")
            deleted_docs = info.get("deletedDocs") or info.get("numDeletedDocs")
            segment_count = info.get("segmentCount")

            if num_docs is not None:
                # Only store from luke if core-properties gave 0 (fallback)
                self._put("num_docs", num_docs, "docs", meta={"collection": collection})
            if deleted_docs is not None:
                self._put("num_deleted_docs", deleted_docs, "docs",
                          meta={"collection": collection})
            if segment_count is not None:
                self._put("segment_count", segment_count, "",
                          meta={"collection": collection})
        except Exception as exc:
            logger.debug("SolrCollectionStats: luke fallback failed for %s: %s",
                         collection, exc)


# ---------------------------------------------------------------------------
# Device: SolrQueryStats
# ---------------------------------------------------------------------------

class SolrQueryStats(SolrTelemetryDevice):
    """
    Collect query latency percentiles and cache hit ratio metrics from Solr.

    Metrics stored:
      - query_latency_p50_ms    (gauge, rolling 50th percentile)
      - query_latency_p99_ms    (gauge, rolling 99th percentile)
      - query_latency_p999_ms   (gauge, rolling 99.9th percentile)
      - query_requests_total    (counter)
      - query_errors_total      (counter)
      - query_cache_hit_ratio   (gauge, filter cache hit ratio 0.0–1.0)

    Supports both Solr 9.x JSON and Solr 10.x Prometheus formats.
    """

    human_name = "Solr Query Stats"
    help = "Query latency percentiles (p50/p99/p999), cache hit ratio, request and error totals"

    def _collect(self) -> None:
        fmt, data = self._fetch_node_metrics_parsed()
        if fmt == "prometheus":
            self._collect_prometheus(data)
        else:
            self._collect_json(data)

    def _collect_json(self, data: dict) -> None:
        core = self._get_metric_json(data, "metrics", "solr.core") or {}

        mappings = [
            ("QUERY./select.requestTimes.p_50", "query_latency_p50_ms", "ms"),
            ("QUERY./select.requestTimes.p_99", "query_latency_p99_ms", "ms"),
            # Solr may use p_99_9 or p_999 depending on version
            ("QUERY./select.requestTimes.p_99_9", "query_latency_p999_ms", "ms"),
            ("QUERY./select.requests", "query_requests_total", ""),
            ("QUERY./select.errors", "query_errors_total", ""),
            ("CACHE.searcher.filterCache.hitratio", "query_cache_hit_ratio", ""),
        ]
        for json_key, osb_name, unit in mappings:
            val = core.get(json_key)
            if val is None and json_key.endswith("p_99_9"):
                # Try alternate name used in older Solr versions
                val = core.get(json_key.replace("p_99_9", "p_999"))
            if val is not None:
                self._put(osb_name, val, unit)

    def _collect_prometheus(self, data: dict) -> None:
        mapping = {
            "solr_metrics_core_query_request_times_p50_ms": ("query_latency_p50_ms", "ms"),
            "solr_metrics_core_query_request_times_p99_ms": ("query_latency_p99_ms", "ms"),
            "solr_metrics_core_query_request_times_p999_ms": ("query_latency_p999_ms", "ms"),
            "solr_metrics_core_query_requests_total": ("query_requests_total", ""),
            "solr_metrics_core_query_errors_total": ("query_errors_total", ""),
            "solr_metrics_core_cache_hitratio": ("query_cache_hit_ratio", ""),
        }
        for prom_name, (osb_name, unit) in mapping.items():
            val = self._get_metric_prometheus(data, prom_name)
            if val is not None:
                self._put(osb_name, val, unit)


# ---------------------------------------------------------------------------
# Device: SolrIndexingStats
# ---------------------------------------------------------------------------

class SolrIndexingStats(SolrTelemetryDevice):
    """
    Collect indexing throughput and merge metrics from Solr.

    Metrics stored:
      - indexing_requests_total       (counter)
      - indexing_errors_total         (counter)
      - indexing_avg_time_ms          (gauge, rolling mean request time)
      - index_merge_major_running     (gauge, count of running major merges)
      - index_merge_minor_running     (gauge, count of running minor merges)

    Supports both Solr 9.x JSON and Solr 10.x Prometheus formats.
    """

    human_name = "Solr Indexing Stats"
    help = "Indexing request counts, average indexing time, and major/minor merge activity"

    def _collect(self) -> None:
        fmt, data = self._fetch_node_metrics_parsed()
        if fmt == "prometheus":
            self._collect_prometheus(data)
        else:
            self._collect_json(data)

    def _collect_json(self, data: dict) -> None:
        core = self._get_metric_json(data, "metrics", "solr.core") or {}

        mappings = [
            ("UPDATE./update.requests", "indexing_requests_total", ""),
            ("UPDATE./update.errors", "indexing_errors_total", ""),
            ("UPDATE./update.requestTimes.mean", "indexing_avg_time_ms", "ms"),
            ("INDEX.merge.major.running", "index_merge_major_running", ""),
            ("INDEX.merge.minor.running", "index_merge_minor_running", ""),
        ]
        for json_key, osb_name, unit in mappings:
            val = core.get(json_key)
            if val is not None:
                self._put(osb_name, val, unit)

    def _collect_prometheus(self, data: dict) -> None:
        mapping = {
            "solr_metrics_core_update_requests_total": ("indexing_requests_total", ""),
            "solr_metrics_core_update_errors_total": ("indexing_errors_total", ""),
            "solr_metrics_core_update_request_times_mean_ms": ("indexing_avg_time_ms", "ms"),
            "solr_metrics_core_index_merge_major_running": ("index_merge_major_running", ""),
            "solr_metrics_core_index_merge_minor_running": ("index_merge_minor_running", ""),
        }
        for prom_name, (osb_name, unit) in mapping.items():
            val = self._get_metric_prometheus(data, prom_name)
            if val is not None:
                self._put(osb_name, val, unit)


# ---------------------------------------------------------------------------
# Device: SolrCacheStats
# ---------------------------------------------------------------------------

class SolrCacheStats(SolrTelemetryDevice):
    """
    Collect Solr internal cache statistics for the three primary caches.

    Caches monitored: queryResultCache, filterCache, documentCache.

    Metrics stored per cache (with ``cache`` meta tag):
      - cache_hits_total        (counter)
      - cache_inserts_total     (counter, total inserts / misses+hits)
      - cache_evictions_total   (counter)
      - cache_memory_bytes      (gauge, RAM used by cache)
      - cache_hit_ratio         (gauge, 0.0–1.0)

    Supports both Solr 9.x JSON and Solr 10.x Prometheus formats.
    """

    human_name = "Solr Cache Stats"
    help = "Per-cache hits, inserts, evictions, memory, and hit ratio (query/filter/document caches)"

    CACHE_NAMES = ["queryResultCache", "filterCache", "documentCache"]

    def _collect(self) -> None:
        fmt, data = self._fetch_node_metrics_parsed()
        if fmt == "prometheus":
            self._collect_prometheus(data)
        else:
            self._collect_json(data)

    def _collect_json(self, data: dict) -> None:
        core = self._get_metric_json(data, "metrics", "solr.core") or {}

        for cache_name in self.CACHE_NAMES:
            prefix = f"CACHE.searcher.{cache_name}."
            hits = core.get(f"{prefix}hits")
            inserts = core.get(f"{prefix}inserts")
            evictions = core.get(f"{prefix}evictions")
            ram_bytes = core.get(f"{prefix}ramBytesUsed")
            hitratio = core.get(f"{prefix}hitratio")

            meta = {"cache": cache_name}
            if hits is not None:
                self._put("cache_hits_total", hits, "", meta=meta)
            if inserts is not None:
                self._put("cache_inserts_total", inserts, "", meta=meta)
            if evictions is not None:
                self._put("cache_evictions_total", evictions, "", meta=meta)
            if ram_bytes is not None:
                self._put("cache_memory_bytes", ram_bytes, "bytes", meta=meta)
            if hitratio is not None:
                self._put("cache_hit_ratio", hitratio, "", meta=meta)

    def _collect_prometheus(self, data: dict) -> None:
        # In Prometheus format, cache metrics are typically not individually
        # separated by cache type in a predictable way; store aggregates
        aggregate_mappings = {
            "solr_metrics_core_cache_hits_total": ("cache_hits_total", ""),
            "solr_metrics_core_cache_inserts_total": ("cache_inserts_total", ""),
            "solr_metrics_core_cache_evictions_total": ("cache_evictions_total", ""),
            "solr_metrics_core_cache_ram_bytes_used": ("cache_memory_bytes", "bytes"),
            "solr_metrics_core_cache_hitratio": ("cache_hit_ratio", ""),
        }
        for prom_name, (osb_name, unit) in aggregate_mappings.items():
            val = self._get_metric_prometheus(data, prom_name)
            if val is not None:
                self._put(osb_name, val, unit, meta={"cache": "aggregate"})
