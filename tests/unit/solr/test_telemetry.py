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

"""Unit tests for osbenchmark/solr/telemetry.py"""

import threading
import time
import unittest
from unittest.mock import MagicMock

from osbenchmark.solr.telemetry import (
    SolrJvmStats,
    SolrNodeStats,
    SolrCollectionStats,
    _parse_prometheus_text,
)


class TestParsePrometheusText(unittest.TestCase):
    def test_basic_metric(self):
        text = "jvm_heap_used_bytes 1234567\n"
        result = _parse_prometheus_text(text)
        self.assertAlmostEqual(1234567.0, result["jvm_heap_used_bytes"])

    def test_comment_lines_skipped(self):
        text = "# HELP jvm_heap JVM heap\n# TYPE jvm_heap gauge\njvm_heap 9999\n"
        result = _parse_prometheus_text(text)
        self.assertIn("jvm_heap", result)
        self.assertAlmostEqual(9999.0, result["jvm_heap"])

    def test_labels_stripped(self):
        text = 'http_requests_total{method="GET",code="200"} 42\n'
        result = _parse_prometheus_text(text)
        self.assertIn("http_requests_total", result)
        self.assertAlmostEqual(42.0, result["http_requests_total"])

    def test_empty_text(self):
        result = _parse_prometheus_text("")
        self.assertEqual({}, result)

    def test_multiple_metrics(self):
        text = "a 1\nb 2\nc 3\n"
        result = _parse_prometheus_text(text)
        self.assertEqual(3, len(result))
        self.assertAlmostEqual(2.0, result["b"])


class TestSolrJvmStatsJson(unittest.TestCase):
    def _make_client(self, json_data):
        client = MagicMock()
        client.get_node_metrics.return_value = json_data
        return client

    def test_heap_metrics_extracted(self):
        stored = {}
        metrics_store = MagicMock()
        metrics_store.put_value_cluster_level = MagicMock(
            side_effect=lambda name, value, **kw: stored.update({name: value})
        )

        data = {
            "metrics": {
                "solr.jvm": {
                    "memory.heap.used": 512_000_000,
                    "memory.heap.max": 2_000_000_000,
                }
            }
        }
        device = SolrJvmStats(self._make_client(data), metrics_store)
        device._collect()

        self.assertIn("jvm_heap_used_bytes", stored)
        self.assertEqual(512_000_000, stored["jvm_heap_used_bytes"])
        self.assertIn("jvm_heap_max_bytes", stored)

    def test_gc_metrics_summed(self):
        stored = {}
        metrics_store = MagicMock()
        metrics_store.put_value_cluster_level = MagicMock(
            side_effect=lambda name, value, **kw: stored.update({name: value})
        )

        data = {
            "metrics": {
                "solr.jvm": {
                    "memory.heap.used": 1,
                    "memory.heap.max": 2,
                    "gc.G1-Young-Generation.count": 10,
                    "gc.G1-Old-Generation.count": 2,
                    "gc.G1-Young-Generation.time": 150,
                    "gc.G1-Old-Generation.time": 30,
                }
            }
        }
        device = SolrJvmStats(self._make_client(data), metrics_store)
        device._collect()

        self.assertIn("jvm_gc_count", stored)
        self.assertEqual(12, stored["jvm_gc_count"])
        self.assertIn("jvm_gc_time_ms", stored)
        self.assertEqual(180, stored["jvm_gc_time_ms"])

    def test_missing_jvm_section_no_error(self):
        client = MagicMock()
        client.get_node_metrics.return_value = {"metrics": {}}
        device = SolrJvmStats(client, MagicMock())
        # Should not raise
        device._collect()


class TestSolrJvmStatsPrometheus(unittest.TestCase):
    def test_prometheus_heap_extracted(self):
        stored = {}
        metrics_store = MagicMock()
        metrics_store.put_value_cluster_level = MagicMock(
            side_effect=lambda name, value, **kw: stored.update({name: value})
        )

        prometheus_text = (
            "# HELP jvm_memory_heap_used_bytes JVM heap used\n"
            "jvm_memory_heap_used_bytes 123456789\n"
            "jvm_memory_heap_max_bytes 2048000000\n"
        )
        client = MagicMock()
        client.get_node_metrics.return_value = prometheus_text
        device = SolrJvmStats(client, metrics_store)
        device._collect()

        self.assertIn("jvm_heap_used_bytes", stored)
        self.assertAlmostEqual(123456789.0, stored["jvm_heap_used_bytes"])
        self.assertIn("jvm_heap_max_bytes", stored)


class TestSolrNodeStats(unittest.TestCase):
    def test_cpu_extracted_from_system(self):
        stored = {}
        metrics_store = MagicMock()
        metrics_store.put_value_cluster_level = MagicMock(
            side_effect=lambda name, value, **kw: stored.update({name: value})
        )

        system_resp = MagicMock()
        system_resp.ok = True
        system_resp.json.return_value = {
            "system": {
                "processCpuLoad": 0.45,
                "freePhysicalMemorySize": 4_000_000_000,
            }
        }
        client = MagicMock()
        client._get.return_value = system_resp
        client.get_node_metrics.return_value = {}  # empty metrics

        device = SolrNodeStats(client, metrics_store)
        device._collect()

        self.assertIn("cpu_usage_percent", stored)
        self.assertAlmostEqual(45.0, stored["cpu_usage_percent"])
        self.assertIn("os_memory_free_bytes", stored)


class TestSolrCollectionStats(unittest.TestCase):
    def test_num_docs_extracted(self):
        stored = {}
        metrics_store = MagicMock()
        metrics_store.put_value_cluster_level = MagicMock(
            side_effect=lambda name, value, **kw: stored.update({name: value})
        )

        cluster_resp = MagicMock()
        cluster_resp.ok = True
        cluster_resp.json.return_value = {
            "cluster": {"collections": {"my-coll": {}}}
        }
        props_resp = MagicMock()
        props_resp.ok = True
        props_resp.json.return_value = {
            "core-properties": {
                "my-coll_shard1_replica1": {"numDocs": 5000}
            }
        }

        client = MagicMock()
        # get_cluster_status returns parsed cluster dict
        client.get_cluster_status.return_value = {
            "collections": {"my-coll": {}}
        }
        client._get.return_value = props_resp

        device = SolrCollectionStats(client, metrics_store,
                                     collections=["my-coll"])
        device._collect()

        self.assertIn("num_docs", stored)
        self.assertEqual(5000, stored["num_docs"])


class TestTelemetryPollingThread(unittest.TestCase):
    def test_start_and_stop(self):
        """Verify that the polling thread starts and stops cleanly."""
        client = MagicMock()
        client.get_node_metrics.return_value = {}
        client.get_cluster_status.return_value = {"collections": {}}

        collected = []
        metrics_store = MagicMock()
        metrics_store.put_value_cluster_level = MagicMock(
            side_effect=lambda **kw: collected.append(kw)
        )

        device = SolrJvmStats(client, metrics_store, sample_interval_s=0.05)
        device.on_benchmark_start()
        time.sleep(0.15)
        device.on_benchmark_stop()

        # Thread should be stopped
        self.assertFalse(device._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
