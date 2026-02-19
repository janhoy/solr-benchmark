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

import csv
import json
import logging
import os
from abc import ABC, abstractmethod

import tabulate as tabulate_lib

from osbenchmark import exceptions

logger = logging.getLogger(__name__)


class ResultWriter(ABC):
    """
    Abstract base class for all benchmark result output destinations.

    Contract:
    - open() is always called before the first write().
    - write() may be called zero or more times.
    - close() is always called exactly once, even if a previous method raised.
    - close() must be safe to call multiple times (idempotent).
    - Implementations must not suppress exceptions from open() or write().
    """

    @abstractmethod
    def open(self, run_metadata: dict) -> None:
        """
        Called once before any metrics are written.

        Args:
            run_metadata: dict with at minimum:
                - "run_id":     str  — unique run identifier (ISO timestamp)
                - "workload":   str  — workload name
                - "challenge":  str  — challenge name
                - "solr_version": str — detected Solr version string
        """

    @abstractmethod
    def write(self, metrics: list) -> None:
        """
        Write a batch of metric record dicts.

        Each record dict contains:
            - "name":           str   — metric name
            - "value":          float — numeric value
            - "unit":           str   — unit string
            - "task":           str   — operation name
            - "operation_type": str   — operation type
            - "sample_type":    str   — "normal" or "warmup"
            - "timestamp":      float — Unix epoch seconds
            - "meta":           dict  — optional extra labels
        """

    @abstractmethod
    def close(self) -> None:
        """Flush and close. Idempotent — safe to call multiple times."""


class LocalFilesystemResultWriter(ResultWriter):
    """
    Writes benchmark results to the local filesystem.

    Output layout:
        {results_path}/{run_id}/
            results.json   — all metrics as JSON array
            results.csv    — flattened CSV
            summary.txt    — markdown table (also printed to stdout)
    """

    def __init__(self, results_path: str):
        self._results_path = results_path
        self._run_dir = None
        self._run_metadata = None
        self._metrics = []
        self._opened = False

    def open(self, run_metadata: dict) -> None:
        self._run_metadata = run_metadata
        run_id = run_metadata.get("run_id", "unknown")
        self._run_dir = os.path.join(self._results_path, run_id)
        os.makedirs(self._run_dir, exist_ok=True)
        self._metrics = []
        self._opened = True
        logger.info("Result writer opened, output dir: %s", self._run_dir)

    def write(self, metrics: list) -> None:
        self._metrics.extend(metrics)

    def close(self) -> None:
        if not self._opened:
            return
        self._opened = False
        if not self._metrics:
            logger.warning("No metrics to write — result files will be empty")

        self._write_json()
        self._write_csv()
        summary = self._write_summary()
        print(summary)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write_json(self) -> None:
        output = dict(self._run_metadata)
        output["metrics"] = self._metrics
        path = os.path.join(self._run_dir, "results.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        logger.info("Wrote %s", path)

    def _write_csv(self) -> None:
        if not self._metrics:
            return
        path = os.path.join(self._run_dir, "results.csv")
        fieldnames = ["name", "value", "unit", "task", "operation_type", "sample_type", "timestamp"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self._metrics)
        logger.info("Wrote %s", path)

    def _write_summary(self) -> str:
        if not self._metrics:
            return "(no metrics recorded)"

        normal = [m for m in self._metrics if m.get("sample_type") != "warmup"]
        rows = [
            [m.get("task", ""), m.get("name", ""), m.get("value", ""), m.get("unit", "")]
            for m in normal
        ]
        table = tabulate_lib.tabulate(
            rows,
            headers=["Task", "Metric", "Value", "Unit"],
            tablefmt="pipe",
            numalign="right",
            stralign="left",
        )
        summary = f"\n## Benchmark Results\n\n{table}\n"
        path = os.path.join(self._run_dir, "summary.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(summary)
        logger.info("Wrote %s", path)
        return summary


# ------------------------------------------------------------------
# Registry and factory
# ------------------------------------------------------------------

WRITER_REGISTRY = {
    "local_filesystem": None,  # populated below to avoid forward reference
}


def create_writer(name: str, **kwargs) -> ResultWriter:
    """
    Instantiate a ResultWriter by registry name.

    Args:
        name:   Registry key (e.g. "local_filesystem").
        kwargs: Constructor arguments forwarded to the writer class.

    Raises:
        exceptions.SystemSetupError: if name is not registered.
    """
    registry = {
        "local_filesystem": LocalFilesystemResultWriter,
    }
    if name not in registry:
        raise exceptions.SystemSetupError(
            f"Unknown results_writer '{name}'. "
            f"Available: {', '.join(registry)}"
        )
    return registry[name](**kwargs)
