# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
# Modifications Copyright OpenSearch Contributors. See
# GitHub history for details.
# Licensed to Elasticsearch B.V. under one or more contributor
# license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright
# ownership. Elasticsearch B.V. licenses this file to you under
# the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import collections
import json
import logging
import os
import threading
import tabulate

from osbenchmark import metrics, time, exceptions
from osbenchmark.metrics import MetaInfoScope
from osbenchmark.utils import io, sysstats, console, opts, process
from osbenchmark.utils.versions import components

def list_telemetry():
    # Lazy import to avoid circular dependency (solr/telemetry.py imports TelemetryDevice from this module)
    from osbenchmark.solr import telemetry as solr_telemetry

    console.println("Available telemetry devices:\n")

    # --- Solr-native devices (always enabled) ---
    console.println("Always-enabled Solr devices (no --telemetry flag needed):\n")
    solr_devices = [
        [d.command, d.human_name, d.help] for d in [
            solr_telemetry.SolrJvmStats,
            solr_telemetry.SolrNodeStats,
            solr_telemetry.SolrCollectionStats,
            solr_telemetry.SolrQueryStats,
            solr_telemetry.SolrIndexingStats,
            solr_telemetry.SolrCacheStats,
        ]
    ]
    console.println(tabulate.tabulate(solr_devices, ["Command", "Name", "Description"]))
    console.println("\nAll always-on devices poll /solr/admin/metrics (JSON on Solr 9.x, Prometheus text on Solr 10.x).")

    # --- Optional REST devices (all pipelines) ---
    console.println("\n\nOptional REST devices (all pipelines — enable with --telemetry <command>):\n")
    rest_devices = [[device.command, device.human_name, device.help] for device in [
        SegmentStats, ShardStats, ClusterEnvironmentInfo,
    ]]
    console.println(tabulate.tabulate(rest_devices, ["Command", "Name", "Description"]))

    # --- Optional JVM/process devices (provisioned pipelines only) ---
    console.println("\n\nOptional JVM/process devices (docker or from-distribution pipelines only):\n")
    jvm_devices = [[device.command, device.human_name, device.help] for device in [
        FlightRecorder, Gc, JitCompiler, Heapdump,
    ]]
    console.println(tabulate.tabulate(jvm_devices, ["Command", "Name", "Description"]))
    console.println("\nJVM/process devices inject flags into SOLR_OPTS before Solr starts.")
    console.println("They are silently skipped when pipeline is benchmark-only.")
    console.println("\nNote: disk-io (disk I/O byte counters) is always active on provisioned pipelines.")


class Telemetry:
    def __init__(self, enabled_devices=None, devices=None):
        if devices is None:
            devices = []
        if enabled_devices is None:
            enabled_devices = []
        self.enabled_devices = enabled_devices
        self.devices = devices

    def instrument_candidate_java_opts(self):
        opts = []
        for device in self.devices:
            if self._enabled(device):
                additional_opts = device.instrument_java_opts()
                # properly merge values with the same key
                opts.extend(additional_opts)
        return opts

    def on_pre_node_start(self, node_name):
        for device in self.devices:
            if self._enabled(device):
                device.on_pre_node_start(node_name)

    def attach_to_node(self, node):
        for device in self.devices:
            if self._enabled(device):
                device.attach_to_node(node)

    def detach_from_node(self, node, running):
        for device in self.devices:
            if self._enabled(device):
                device.detach_from_node(node, running)

    def on_benchmark_start(self):
        for device in self.devices:
            if self._enabled(device):
                device.on_benchmark_start()

    def on_benchmark_stop(self):
        for device in self.devices:
            if self._enabled(device):
                device.on_benchmark_stop()

    def store_system_metrics(self, node, metrics_store):
        for device in self.devices:
            if self._enabled(device):
                device.store_system_metrics(node, metrics_store)

    def _enabled(self, device):
        return device.internal or device.command in self.enabled_devices


########################################################################################
#
# Telemetry devices
#
########################################################################################

class TelemetryDevice:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def instrument_java_opts(self):
        return {}

    def on_pre_node_start(self, node_name):
        pass

    def attach_to_node(self, node):
        pass

    def detach_from_node(self, node, running):
        pass

    def on_benchmark_start(self):
        pass

    def on_benchmark_stop(self):
        pass

    def store_system_metrics(self, node, metrics_store):
        pass

    def __getstate__(self):
        state = self.__dict__.copy()
        del state["logger"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.logger = logging.getLogger(__name__)


class InternalTelemetryDevice(TelemetryDevice):
    internal = True


class SamplerThread(threading.Thread):
    def __init__(self, recorder):
        threading.Thread.__init__(self)
        self.stop = False
        self.recorder = recorder

    def finish(self):
        self.stop = True
        self.join()

    def run(self):
        # noinspection PyBroadException
        try:
            while not self.stop:
                self.recorder.record()
                time.sleep(self.recorder.sample_interval)
        except BaseException:
            logging.getLogger(__name__).exception("Could not determine %s", self.recorder)


class FlightRecorder(TelemetryDevice):
    internal = False
    command = "jfr"
    human_name = "Flight Recorder"
    help = "Enables Java Flight Recorder (requires OpenJDK 11+); injected into SOLR_OPTS."

    def __init__(self, telemetry_params, log_root, java_major_version):
        super().__init__()
        self.telemetry_params = telemetry_params
        self.log_root = log_root
        self.java_major_version = java_major_version

    def instrument_java_opts(self):
        if self.telemetry_params.get("pipeline", "") == "benchmark-only":
            self.logger.warning("jfr: Solr was not provisioned by Solr Benchmark; skipping JFR flags.")
            return []

        io.ensure_dir(self.log_root)
        log_file = os.path.join(self.log_root, "profile.jfr")
        console.info("%s: Writing flight recording to [%s]" % (self.human_name, log_file), logger=self.logger)
        java_opts = self.java_opts(log_file)
        self.logger.info("jfr: Adding JVM arguments: [%s].", java_opts)
        return java_opts

    def java_opts(self, log_file):
        recording_template = self.telemetry_params.get("recording-template")
        java_opts = ["-XX:+UnlockDiagnosticVMOptions", "-XX:+DebugNonSafepoints"]
        jfr_cmd = "-XX:StartFlightRecording=maxsize=0,maxage=0s,disk=true,dumponexit=true,filename={}".format(log_file)
        if recording_template:
            self.logger.info("jfr: Using recording template [%s].", recording_template)
            jfr_cmd += ",settings={}".format(recording_template)
        else:
            self.logger.info("jfr: Using default recording template.")
        java_opts.append(jfr_cmd)
        return java_opts


class JitCompiler(TelemetryDevice):
    internal = False
    command = "jit"
    human_name = "JIT Compiler Profiler"
    help = "Enables JIT compiler logs; injected into SOLR_OPTS."

    def __init__(self, log_root, telemetry_params=None):
        super().__init__()
        self.log_root = log_root
        self.telemetry_params = telemetry_params or {}

    def instrument_java_opts(self):
        if self.telemetry_params.get("pipeline", "") == "benchmark-only":
            self.logger.warning("jit: Solr was not provisioned by Solr Benchmark; skipping JIT flags.")
            return []

        io.ensure_dir(self.log_root)
        log_file = os.path.join(self.log_root, "jit.log")
        console.info("%s: Writing JIT compiler log to [%s]" % (self.human_name, log_file), logger=self.logger)
        return ["-XX:+UnlockDiagnosticVMOptions", "-XX:+TraceClassLoading", "-XX:+LogCompilation",
                "-XX:LogFile={}".format(log_file), "-XX:+PrintAssembly"]


class Gc(TelemetryDevice):
    internal = False
    command = "gc"
    human_name = "GC log"
    help = "Enables GC logs (Java 9+ -Xlog: format); injected into SOLR_OPTS."

    def __init__(self, telemetry_params, log_root, java_major_version):
        super().__init__()
        self.telemetry_params = telemetry_params
        self.log_root = log_root
        self.java_major_version = java_major_version

    def instrument_java_opts(self):
        if self.telemetry_params.get("pipeline", "") == "benchmark-only":
            self.logger.warning("gc: Solr was not provisioned by Solr Benchmark; skipping GC flags.")
            return []

        io.ensure_dir(self.log_root)
        log_file = os.path.join(self.log_root, "gc.log")
        console.info("%s: Writing GC log to [%s]" % (self.human_name, log_file), logger=self.logger)
        log_config = self.telemetry_params.get("gc-log-config", "gc*=info,safepoint=info,age*=trace")
        # see https://docs.oracle.com/javase/9/tools/java.htm#JSWOR-GUID-BE93ABDC-999C-4CB5-A88B-1994AAAC74D5
        return [f"-Xlog:{log_config}:file={log_file}:utctime,uptimemillis,level,tags:filecount=0"]


class Heapdump(TelemetryDevice):
    internal = False
    command = "heapdump"
    human_name = "Heap Dump"
    help = "Captures a heap dump from the Solr JVM on benchmark stop."

    def __init__(self, log_root, docker_container=None):
        super().__init__()
        self.log_root = log_root
        self.docker_container = docker_container

    def detach_from_node(self, node, running):
        if running:
            heap_dump_file = os.path.join(self.log_root, "heap_at_exit_{}.hprof".format(node.pid))
            console.info("{}: Writing heap dump to [{}]".format(self.human_name, heap_dump_file), logger=self.logger)
            # noinspection PyBroadException
            try:
                if self.docker_container:
                    cmd = "docker exec {} jmap -dump:format=b,file={} {}".format(
                        self.docker_container, heap_dump_file, node.pid)
                else:
                    cmd = "jmap -dump:format=b,file={} {}".format(heap_dump_file, node.pid)
                if process.run_subprocess_with_logging(cmd):
                    self.logger.warning("Could not write heap dump to [%s]", heap_dump_file)
            except BaseException:
                self.logger.warning("Could not write heap dump to [%s]", heap_dump_file)


class SegmentStats(TelemetryDevice):
    internal = False
    command = "segment-stats"
    human_name = "Segment Stats"
    help = "Captures per-collection segment stats (numDocs, deletedDocs, segmentCount, sizeInBytes) via the Solr Luke API."

    def __init__(self, log_root, admin_client):
        super().__init__()
        self.log_root = log_root
        self.admin_client = admin_client

    def on_benchmark_stop(self):
        # noinspection PyBroadException
        try:
            collections = self.admin_client.list_collections()
            stats_file = os.path.join(self.log_root, "segment_stats.log")
            console.info(f"{self.human_name}: Writing segment stats to [{stats_file}]", logger=self.logger)
            io.ensure_dir(self.log_root)
            with open(stats_file, "wt") as f:
                for coll in collections:
                    try:
                        idx = self.admin_client.get_luke_stats(coll)
                        row = {
                            "collection": coll,
                            "numDocs": idx.get("numDocs"),
                            "maxDoc": idx.get("maxDoc"),
                            "deletedDocs": idx.get("deletedDocs"),
                            "segmentCount": idx.get("segmentCount"),
                            "sizeInBytes": idx.get("sizeInBytes"),
                        }
                        f.write(json.dumps(row) + "\n")
                    except BaseException:
                        self.logger.warning("Could not retrieve Luke stats for collection [%s].", coll)
        except BaseException:
            self.logger.exception("Could not retrieve segment stats.")


class ShardStats(TelemetryDevice):
    """
    Collects per-shard document count and index size for SolrCloud clusters.
    Skipped silently on standalone Solr (no cluster.collections in CLUSTERSTATUS).
    """

    internal = False
    command = "shard-stats"
    human_name = "Shard Stats"
    help = "Regularly samples per-shard document count and index size (SolrCloud only)."

    def __init__(self, telemetry_params, admin_client, metrics_store):
        """
        :param telemetry_params: May optionally specify
            ``shard-stats-sample-interval``: positive integer, seconds between polls. Default: 60.
        :param admin_client: A SolrAdminClient instance used for V1 admin API calls.
        :param metrics_store: The configured metrics store we write to.
        """
        super().__init__()
        self.admin_client = admin_client
        self.metrics_store = metrics_store
        self.sample_interval = telemetry_params.get("shard-stats-sample-interval", 60)
        if self.sample_interval <= 0:
            raise exceptions.SystemSetupError(
                f"The telemetry parameter 'shard-stats-sample-interval' must be greater than zero but was {self.sample_interval}."
            )
        self.samplers = []

    def on_benchmark_start(self):
        # noinspection PyBroadException
        try:
            session = self.admin_client._get_session()
            cs_url = f"{self.admin_client.base_url}/solr/admin/collections?action=CLUSTERSTATUS&wt=json"
            resp = session.get(cs_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except BaseException:
            self.logger.exception("ShardStats: could not retrieve CLUSTERSTATUS; device will not run.")
            return

        if "cluster" not in data or "collections" not in data.get("cluster", {}):
            self.logger.info("ShardStats: no cluster.collections in CLUSTERSTATUS — skipping (standalone Solr).")
            return

        recorder = ShardStatsRecorder(self.admin_client, self.metrics_store, self.sample_interval)
        sampler = SamplerThread(recorder)
        self.samplers.append(sampler)
        sampler.daemon = True
        sampler.start()

    def on_benchmark_stop(self):
        for sampler in self.samplers:
            sampler.finish()


class ShardStatsRecorder:
    """
    Polls CLUSTERSTATUS and Core STATUS for each shard leader; pushes metrics per shard.
    """

    def __init__(self, admin_client, metrics_store, sample_interval):
        self.admin_client = admin_client
        self.metrics_store = metrics_store
        self.sample_interval = sample_interval
        self.logger = logging.getLogger(__name__)

    def __str__(self):
        return "shard stats"

    def record(self):
        # noinspection PyBroadException
        try:
            session = self.admin_client._get_session()
            cs_url = f"{self.admin_client.base_url}/solr/admin/collections?action=CLUSTERSTATUS&wt=json"
            cs_resp = session.get(cs_url, timeout=30)
            cs_resp.raise_for_status()
            cluster = cs_resp.json().get("cluster", {})
            collections = cluster.get("collections", {})
        except BaseException:
            self.logger.exception("ShardStats: could not retrieve CLUSTERSTATUS.")
            return

        session = self.admin_client._get_session()
        for _coll_name, coll_data in collections.items():
            shards = coll_data.get("shards", {})
            for shard_name, shard_data in shards.items():
                replicas = shard_data.get("replicas", {})
                for _replica_key, replica in replicas.items():
                    if replica.get("state") == "active" and replica.get("leader") == "true":
                        core_name = replica.get("core")
                        if not core_name:
                            continue
                        # noinspection PyBroadException
                        try:
                            status_url = (
                                f"{self.admin_client.base_url}/solr/admin/cores"
                                f"?action=STATUS&core={core_name}&wt=json"
                            )
                            sr = session.get(status_url, timeout=30)
                            sr.raise_for_status()
                            core_status = sr.json().get("status", {}).get(core_name, {})
                            idx = core_status.get("index", {})
                            num_docs = idx.get("numDocs", 0)
                            size_bytes = idx.get("sizeInBytes", 0)
                            self.metrics_store.put_value_cluster_level(
                                f"shard_{shard_name}_num_docs", num_docs, "")
                            self.metrics_store.put_value_cluster_level(
                                f"shard_{shard_name}_size_bytes", size_bytes, "byte")
                        except BaseException:
                            self.logger.warning("ShardStats: could not get core STATUS for [%s].", core_name)
                        break  # only need the leader replica per shard

class StartupTime(InternalTelemetryDevice):
    def __init__(self, stopwatch=time.StopWatch):
        super().__init__()
        self.timer = stopwatch()

    def on_pre_node_start(self, node_name):
        self.timer.start()

    def attach_to_node(self, node):
        self.timer.stop()

    def store_system_metrics(self, node, metrics_store):
        metrics_store.put_value_node_level(node.node_name, "node_startup_time", self.timer.total_time(), "s")


class DiskIo(InternalTelemetryDevice):
    """
    Gathers disk I/O stats.
    """
    def __init__(self, node_count_on_host):
        super().__init__()
        self.node_count_on_host = node_count_on_host
        self.read_bytes = None
        self.write_bytes = None

    def attach_to_node(self, node):
        os_process = sysstats.setup_process_stats(node.pid)
        process_start = sysstats.process_io_counters(os_process)
        if process_start:
            self.read_bytes = process_start.read_bytes
            self.write_bytes = process_start.write_bytes
            self.logger.info("Using more accurate process-based I/O counters.")
        else:
            # noinspection PyBroadException
            try:
                disk_start = sysstats.disk_io_counters()
                self.read_bytes = disk_start.read_bytes
                self.write_bytes = disk_start.write_bytes
                self.logger.warning("Process I/O counters are not supported on this platform. Falling back to less "
                                    "accurate disk I/O counters.")
            except BaseException:
                self.logger.exception("Could not determine I/O stats at benchmark start.")

    def detach_from_node(self, node, running):
        if running:
            # Be aware the semantics of write counts etc. are different for disk and process statistics.
            # Thus we're conservative and only publish I/O bytes now.
            # noinspection PyBroadException
            try:
                os_process = sysstats.setup_process_stats(node.pid)
                process_end = sysstats.process_io_counters(os_process)
                # we have process-based disk counters, no need to worry how many nodes are on this host
                if process_end:
                    self.read_bytes = process_end.read_bytes - self.read_bytes
                    self.write_bytes = process_end.write_bytes - self.write_bytes
                else:
                    disk_end = sysstats.disk_io_counters()
                    if self.node_count_on_host > 1:
                        self.logger.info("There are [%d] nodes on this host and OSB fell back to disk I/O counters. "
                                         "Attributing [1/%d] of total I/O to [%s].",
                                         self.node_count_on_host, self.node_count_on_host, node.node_name)

                    self.read_bytes = (disk_end.read_bytes - self.read_bytes) // self.node_count_on_host
                    self.write_bytes = (disk_end.write_bytes - self.write_bytes) // self.node_count_on_host
            # Catching RuntimeException is not sufficient: psutil might raise AccessDenied (derived from Exception)
            except BaseException:
                self.logger.exception("Could not determine I/O stats at benchmark end.")
                # reset all counters so we don't attempt to write inconsistent numbers to the metrics store later on
                self.read_bytes = None
                self.write_bytes = None

    def store_system_metrics(self, node, metrics_store):
        if self.write_bytes is not None:
            metrics_store.put_value_node_level(node.node_name, "disk_io_write_bytes", self.write_bytes, "byte")
        if self.read_bytes is not None:
            metrics_store.put_value_node_level(node.node_name, "disk_io_read_bytes", self.read_bytes, "byte")


def store_node_attribute_metadata(metrics_store, nodes_info):
    # push up all node level attributes to cluster level iff the values are identical for all nodes
    pseudo_cluster_attributes = {}
    for node in nodes_info:
        if "attributes" in node:
            for k, v in node["attributes"].items():
                attribute_key = "attribute_%s" % str(k)
                metrics_store.add_meta_info(metrics.MetaInfoScope.node, node["name"], attribute_key, v)
                if attribute_key not in pseudo_cluster_attributes:
                    pseudo_cluster_attributes[attribute_key] = set()
                pseudo_cluster_attributes[attribute_key].add(v)

    for k, v in pseudo_cluster_attributes.items():
        if len(v) == 1:
            metrics_store.add_meta_info(metrics.MetaInfoScope.cluster, None, k, next(iter(v)))


def store_plugin_metadata(metrics_store, nodes_info):
    # push up all plugins to cluster level iff all nodes have the same ones
    all_nodes_plugins = []
    all_same = False

    for node in nodes_info:
        plugins = [p["name"] for p in extract_value(node, ["plugins"], fallback=[]) if "name" in p]
        if not all_nodes_plugins:
            all_nodes_plugins = plugins.copy()
            all_same = True
        else:
            # order does not matter so we do a set comparison
            all_same = all_same and set(all_nodes_plugins) == set(plugins)

        if plugins:
            metrics_store.add_meta_info(metrics.MetaInfoScope.node, node["name"], "plugins", plugins)

    if all_same and all_nodes_plugins:
        metrics_store.add_meta_info(metrics.MetaInfoScope.cluster, None, "plugins", all_nodes_plugins)


def extract_value(node, path, fallback="unknown"):
    value = node
    try:
        for k in path:
            value = value[k]
    except KeyError:
        value = fallback
    return value


class ClusterEnvironmentInfo(TelemetryDevice):
    """
    Gathers static environment information on a cluster level (Solr version, JVM, CPU).
    Called once at benchmark start; stores results as run metadata.
    """
    internal = False
    command = "cluster-environment-info"
    human_name = "Cluster Environment Info"
    help = "Stores Solr version, JVM version, and CPU core count as benchmark metadata."

    def __init__(self, admin_client, metrics_store):
        super().__init__()
        self.admin_client = admin_client
        self.metrics_store = metrics_store

    def on_benchmark_start(self):
        # noinspection PyBroadException
        try:
            session = self.admin_client._get_session()
            system_url = f"{self.admin_client.base_url}/api/node/system"
            resp = session.get(system_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except BaseException:
            self.logger.exception("ClusterEnvironmentInfo: could not retrieve /api/node/system")
            return

        lucene = data.get("lucene", {})
        jvm = data.get("jvm", {})
        system = data.get("system", {})
        distribution_version = lucene.get("solr-spec-version", "unknown")
        jvm_version = jvm.get("version", "unknown")
        jvm_vendor = jvm.get("name", "unknown")
        cpu_logical_cores = system.get("availableProcessors", -1)

        self.metrics_store.add_meta_info(metrics.MetaInfoScope.cluster, None, "distribution_version", distribution_version)
        self.metrics_store.add_meta_info(metrics.MetaInfoScope.cluster, None, "jvm_version", jvm_version)
        self.metrics_store.add_meta_info(metrics.MetaInfoScope.cluster, None, "jvm_vendor", jvm_vendor)
        self.metrics_store.add_meta_info(metrics.MetaInfoScope.cluster, None, "cpu_logical_cores", cpu_logical_cores)

        # noinspection PyBroadException
        try:
            cs_url = f"{self.admin_client.base_url}/solr/admin/collections?action=CLUSTERSTATUS&wt=json"
            cs_resp = session.get(cs_url, timeout=30)
            cs_resp.raise_for_status()
            cluster = cs_resp.json().get("cluster", {})
            live_nodes = cluster.get("liveNodes", [])
            self.metrics_store.add_meta_info(metrics.MetaInfoScope.cluster, None, "cluster_node_count", len(live_nodes))
        except BaseException:
            self.logger.warning("ClusterEnvironmentInfo: could not retrieve CLUSTERSTATUS node count.")


def add_metadata_for_node(metrics_store, node_name, host_name):
    """
    Gathers static environment information like OS or CPU details for benchmark-provisioned nodes.
    """
    metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "os_name", sysstats.os_name())
    metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "os_version", sysstats.os_version())
    metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "cpu_logical_cores", sysstats.logical_cpu_cores())
    metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "cpu_physical_cores", sysstats.physical_cpu_cores())
    metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "cpu_model", sysstats.cpu_model())
    metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "node_name", node_name)
    metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "host_name", host_name)


class ExternalEnvironmentInfo(InternalTelemetryDevice):
    """
    Gathers static environment information for externally provisioned clusters.
    """
    def __init__(self, client, metrics_store):
        super().__init__()
        self.metrics_store = metrics_store
        self.client = client

    # noinspection PyBroadException
    def on_benchmark_start(self):
        try:
            nodes_stats = self.client.nodes.stats(metric="_all")["nodes"].values()
        except BaseException:
            self.logger.exception("Could not retrieve nodes stats")
            nodes_stats = []
        try:
            nodes_info = self.client.nodes.info(node_id="_all")["nodes"].values()
        except BaseException:
            self.logger.exception("Could not retrieve nodes info")
            nodes_info = []

        for node in nodes_stats:
            node_name = node["name"]
            host = node.get("host", "unknown")
            self.metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "node_name", node_name)
            self.metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, "host_name", host)

        for node in nodes_info:
            node_name = node["name"]
            self.store_node_info(node_name, "os_name", node, ["os", "name"])
            self.store_node_info(node_name, "os_version", node, ["os", "version"])
            self.store_node_info(node_name, "cpu_logical_cores", node, ["os", "available_processors"])
            self.store_node_info(node_name, "jvm_vendor", node, ["jvm", "vm_vendor"])
            self.store_node_info(node_name, "jvm_version", node, ["jvm", "version"])

        store_plugin_metadata(self.metrics_store, nodes_info)
        store_node_attribute_metadata(self.metrics_store, nodes_info)

    def store_node_info(self, node_name, metric_key, node, path):
        self.metrics_store.add_meta_info(metrics.MetaInfoScope.node, node_name, metric_key, extract_value(node, path))


class JvmStatsSummary(InternalTelemetryDevice):
    """
    Gathers a summary of various JVM statistics during the whole test run.
    """
    def __init__(self, client, metrics_store):
        super().__init__()
        self.metrics_store = metrics_store
        self.client = client
        self.jvm_stats_per_node = {}

    def on_benchmark_start(self):
        self.logger.info("JvmStatsSummary on benchmark start")
        self.jvm_stats_per_node = self.jvm_stats()

    def on_benchmark_stop(self):
        jvm_stats_at_end = self.jvm_stats()
        total_old_gen_collection_time = 0
        total_old_gen_collection_count = 0
        total_young_gen_collection_time = 0
        total_young_gen_collection_count = 0

        for node_name, jvm_stats_end in jvm_stats_at_end.items():
            if node_name in self.jvm_stats_per_node:
                jvm_stats_start = self.jvm_stats_per_node[node_name]
                young_gc_time = max(jvm_stats_end["young_gc_time"] - jvm_stats_start["young_gc_time"], 0)
                young_gc_count = max(jvm_stats_end["young_gc_count"] - jvm_stats_start["young_gc_count"], 0)
                old_gc_time = max(jvm_stats_end["old_gc_time"] - jvm_stats_start["old_gc_time"], 0)
                old_gc_count = max(jvm_stats_end["old_gc_count"] - jvm_stats_start["old_gc_count"], 0)

                total_young_gen_collection_time += young_gc_time
                total_young_gen_collection_count += young_gc_count
                total_old_gen_collection_time += old_gc_time
                total_old_gen_collection_count += old_gc_count

                self.metrics_store.put_value_node_level(node_name, "node_young_gen_gc_time", young_gc_time, "ms")
                self.metrics_store.put_value_node_level(node_name, "node_young_gen_gc_count", young_gc_count)
                self.metrics_store.put_value_node_level(node_name, "node_old_gen_gc_time", old_gc_time, "ms")
                self.metrics_store.put_value_node_level(node_name, "node_old_gen_gc_count", old_gc_count)

                all_pool_stats = {
                    "name": "jvm_memory_pool_stats"
                }
                for pool_name, pool_stats in jvm_stats_end["pools"].items():
                    all_pool_stats[pool_name] = {
                        "peak_usage": pool_stats["peak"],
                        "unit": "byte"
                    }
                self.metrics_store.put_doc(all_pool_stats, level=MetaInfoScope.node, node_name=node_name)

            else:
                self.logger.warning("Cannot determine JVM stats for [%s] (not in the cluster at the start of the benchmark).", node_name)

        self.metrics_store.put_value_cluster_level("node_total_young_gen_gc_time", total_young_gen_collection_time, "ms")
        self.metrics_store.put_value_cluster_level("node_total_young_gen_gc_count", total_young_gen_collection_count)
        self.metrics_store.put_value_cluster_level("node_total_old_gen_gc_time", total_old_gen_collection_time, "ms")
        self.metrics_store.put_value_cluster_level("node_total_old_gen_gc_count", total_old_gen_collection_count)

        self.jvm_stats_per_node = None

    def jvm_stats(self):
        self.logger.debug("Gathering JVM stats")
        jvm_stats = {}
        try:
            stats = self.client.nodes.stats(metric="_all")
        except exceptions.BenchmarkTransportError:
            self.logger.exception("Could not retrieve GC times.")
            return jvm_stats
        nodes = stats["nodes"]
        for node in nodes.values():
            node_name = node["name"]
            gc = node["jvm"]["gc"]["collectors"]
            old_gen_collection_time = gc["old"]["collection_time_in_millis"]
            old_gen_collection_count = gc["old"]["collection_count"]
            young_gen_collection_time = gc["young"]["collection_time_in_millis"]
            young_gen_collection_count = gc["young"]["collection_count"]
            jvm_stats[node_name] = {
                "young_gc_time": young_gen_collection_time,
                "young_gc_count": young_gen_collection_count,
                "old_gc_time": old_gen_collection_time,
                "old_gc_count": old_gen_collection_count,
                "pools": {}
            }
            pool_usage = node["jvm"]["mem"]["pools"]
            for pool_name, pool_stats in pool_usage.items():
                jvm_stats[node_name]["pools"][pool_name] = {
                    "peak": pool_stats["peak_used_in_bytes"]
                }
        return jvm_stats


class IndexStats(InternalTelemetryDevice):
    """
    Gathers statistics via the OpenSearch index stats API
    """
    def __init__(self, client, metrics_store):
        super().__init__()
        self.client = client
        self.metrics_store = metrics_store
        self.first_time = True

    def on_benchmark_start(self):
        # we only determine this value at the start of the benchmark. This is actually only useful for
        # the pipeline "benchmark-only" where we don't have control over the cluster and the user might not have restarted
        # the cluster so we can at least tell them.
        if self.first_time:
            for t in self.index_times(self.index_stats(), per_shard_stats=False):
                n = t["name"]
                v = t["value"]
                if t["value"] > 0:
                    console.warn("%s is %d ms indicating that the cluster is not in a defined clean state. Recorded index time "
                                 "metrics may be misleading." % (n, v), logger=self.logger)
            self.first_time = False

    def on_benchmark_stop(self):
        self.logger.info("Gathering indices stats for all primaries on benchmark stop.")
        index_stats = self.index_stats()
        # import json
        # self.logger.debug("Returned indices stats:\n%s", json.dumps(index_stats, indent=2))
        if "_all" not in index_stats or "primaries" not in index_stats["_all"]:
            return
        p = index_stats["_all"]["primaries"]
        # actually this is add_count
        self.add_metrics(self.extract_value(p, ["segments", "count"]), "segments_count")
        self.add_metrics(self.extract_value(p, ["segments", "memory_in_bytes"]), "segments_memory_in_bytes", "byte")

        for t in self.index_times(index_stats):
            self.metrics_store.put_doc(doc=t, level=metrics.MetaInfoScope.cluster)

        for ct in self.index_counts(index_stats):
            self.metrics_store.put_doc(doc=ct, level=metrics.MetaInfoScope.cluster)

        self.add_metrics(self.extract_value(p, ["segments", "doc_values_memory_in_bytes"]), "segments_doc_values_memory_in_bytes", "byte")
        self.add_metrics(self.extract_value(p, ["segments", "stored_fields_memory_in_bytes"]), "segments_stored_fields_memory_in_bytes",
                                            "byte")
        self.add_metrics(self.extract_value(p, ["segments", "terms_memory_in_bytes"]), "segments_terms_memory_in_bytes", "byte")
        self.add_metrics(self.extract_value(p, ["segments", "norms_memory_in_bytes"]), "segments_norms_memory_in_bytes", "byte")
        self.add_metrics(self.extract_value(p, ["segments", "points_memory_in_bytes"]), "segments_points_memory_in_bytes", "byte")
        self.add_metrics(self.extract_value(index_stats, ["_all", "total", "store", "size_in_bytes"]), "store_size_in_bytes", "byte")
        self.add_metrics(self.extract_value(index_stats, ["_all", "total", "translog", "size_in_bytes"]), "translog_size_in_bytes", "byte")

    def index_stats(self):
        # noinspection PyBroadException
        try:
            return self.client.indices.stats(metric="_all", level="shards")
        except BaseException:
            self.logger.exception("Could not retrieve index stats.")
            return {}

    def index_times(self, stats, per_shard_stats=True):
        times = []
        self.index_time(times, stats, "merges_total_time", ["merges", "total_time_in_millis"], per_shard_stats)
        self.index_time(times, stats, "merges_total_throttled_time", ["merges", "total_throttled_time_in_millis"], per_shard_stats)
        self.index_time(times, stats, "indexing_total_time", ["indexing", "index_time_in_millis"], per_shard_stats)
        self.index_time(times, stats, "indexing_throttle_time", ["indexing", "throttle_time_in_millis"], per_shard_stats)
        self.index_time(times, stats, "refresh_total_time", ["refresh", "total_time_in_millis"], per_shard_stats)
        self.index_time(times, stats, "flush_total_time", ["flush", "total_time_in_millis"], per_shard_stats)
        return times

    def index_time(self, values, stats, name, path, per_shard_stats):
        primary_total_stats = self.extract_value(stats, ["_all", "primaries"], default_value={})
        value = self.extract_value(primary_total_stats, path)
        if value is not None:
            doc = {
                "name": name,
                "value": value,
                "unit": "ms",
            }
            if per_shard_stats:
                doc["per-shard"] = self.primary_shard_stats(stats, path)
            values.append(doc)

    def index_counts(self, stats):
        counts = []
        self.index_count(counts, stats, "merges_total_count", ["merges", "total"])
        self.index_count(counts, stats, "refresh_total_count", ["refresh", "total"])
        self.index_count(counts, stats, "flush_total_count", ["flush", "total"])
        return counts

    def index_count(self, values, stats, name, path):
        primary_total_stats = self.extract_value(stats, ["_all", "primaries"], default_value={})
        value = self.extract_value(primary_total_stats, path)
        if value is not None:
            doc = {
                "name": name,
                "value": value
            }
            values.append(doc)

    def primary_shard_stats(self, stats, path):
        shard_stats = []
        try:
            for shards in stats["indices"].values():
                for shard in shards["shards"].values():
                    for shard_metrics in shard:
                        if shard_metrics["routing"]["primary"]:
                            shard_stats.append(self.extract_value(shard_metrics, path, default_value=0))
        except KeyError:
            self.logger.warning("Could not determine primary shard stats at path [%s].", ",".join(path))
        return shard_stats

    def add_metrics(self, value, metric_key, unit=None):
        if value is not None:
            if unit:
                self.metrics_store.put_value_cluster_level(metric_key, value, unit)
            else:
                self.metrics_store.put_value_cluster_level(metric_key, value)

    def extract_value(self, primaries, path, default_value=None):
        value = primaries
        try:
            for k in path:
                value = value[k]
            return value
        except KeyError:
            self.logger.warning("Could not determine value at path [%s]. Returning default value [%s]", ",".join(path), str(default_value))
            return default_value


class MlBucketProcessingTime(InternalTelemetryDevice):
    def __init__(self, client, metrics_store):
        super().__init__()
        self.client = client
        self.metrics_store = metrics_store

    def on_benchmark_stop(self):
        try:
            results = self.client.search(index=".ml-anomalies-*", body={
                "size": 0,
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"result_type": "bucket"}}
                        ]
                    }
                },
                "aggs": {
                    "jobs": {
                        "terms": {
                            "field": "job_id"
                        },
                        "aggs": {
                            "min_pt": {
                                "min": {"field": "processing_time_ms"}
                            },
                            "max_pt": {
                                "max": {"field": "processing_time_ms"}
                            },
                            "mean_pt": {
                                "avg": {"field": "processing_time_ms"}
                            },
                            "median_pt": {
                                "percentiles": {"field": "processing_time_ms", "percents": [50]}
                            }
                        }
                    }
                }
            })
        except exceptions.BenchmarkTransportError:
            self.logger.exception("Could not retrieve ML bucket processing time.")
            return
        try:
            for job in results["aggregations"]["jobs"]["buckets"]:
                ml_job_stats = collections.OrderedDict()
                ml_job_stats["name"] = "ml_processing_time"
                ml_job_stats["job"] = job["key"]
                ml_job_stats["min"] = job["min_pt"]["value"]
                ml_job_stats["mean"] = job["mean_pt"]["value"]
                ml_job_stats["median"] = job["median_pt"]["values"]["50.0"]
                ml_job_stats["max"] = job["max_pt"]["value"]
                ml_job_stats["unit"] = "ms"
                self.metrics_store.put_doc(doc=dict(ml_job_stats), level=MetaInfoScope.cluster)
        except KeyError:
            # no ML running
            pass


class IndexSize(InternalTelemetryDevice):
    """
    Measures the final size of the index
    """
    def __init__(self, data_paths):
        super().__init__()
        self.data_paths = data_paths
        self.attached = False
        self.index_size_bytes = None

    def attach_to_node(self, node):
        self.attached = True

    def detach_from_node(self, node, running):
        # we need to gather the file size after the node has terminated so we can be sure that it has written all its buffers.
        if not running and self.attached and self.data_paths:
            self.attached = False
            index_size_bytes = 0
            for data_path in self.data_paths:
                index_size_bytes += io.get_size(data_path)
            self.index_size_bytes = index_size_bytes

    def store_system_metrics(self, node, metrics_store):
        if self.index_size_bytes:
            metrics_store.put_value_node_level(node.node_name, "final_index_size_bytes", self.index_size_bytes, "byte")

