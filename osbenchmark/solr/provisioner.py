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
Solr provisioner: download, install, start, stop, and clean local Solr instances.

Also provides SolrDockerLauncher for containerised deployments.
"""

import logging
import os
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

import requests

from osbenchmark import exceptions

logger = logging.getLogger(__name__)

# Apache Solr download locations
# Latest versions available at downloads.apache.org
_DOWNLOADS_URL = "https://downloads.apache.org/solr/solr"
# Solr 9.0+ archived versions
_ARCHIVE_9_URL = "https://archive.apache.org/dist/solr/solr"
# Pre-9.0 versions (in lucene directory)
_ARCHIVE_PRE9_URL = "https://archive.apache.org/dist/lucene/solr"


class SolrProvisionerError(Exception):
    """Raised for provisioning failures."""


class SolrProvisioner:
    """
    Manages a local Solr installation lifecycle.

    Typical usage:
        p = SolrProvisioner(cache_dir="/tmp/solr-cache")
        p.download("9.7.0")
        p.install("9.7.0", "/tmp/solr-node")
        p.start("/tmp/solr-node")
        # ... run benchmark ...
        p.stop("/tmp/solr-node")
        p.clean("/tmp/solr-node")
    """

    def __init__(self, cache_dir: str = None, port: int = 8983,
                 startup_timeout: int = 120):
        self.cache_dir = cache_dir or os.path.join(os.path.expanduser("~"), ".solr-benchmark", "cache")
        self.port = port
        self.startup_timeout = startup_timeout
        os.makedirs(self.cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def download(self, version: str) -> str:
        """
        Download the Solr tarball for the given version to the cache dir.

        Returns the path to the cached tarball.
        Skips download if the tarball is already cached.

        Tries multiple mirrors in order:
        1. downloads.apache.org (latest versions)
        2. archive.apache.org/dist/solr/solr (Solr 9.0+)
        3. archive.apache.org/dist/lucene/solr (pre-9.0)
        """
        tarball = f"solr-{version}.tgz"
        dest = os.path.join(self.cache_dir, tarball)
        if os.path.exists(dest):
            logger.info("Solr %s already cached at %s", version, dest)
            return dest

        # Try all Apache mirrors in order
        for base_url in (_DOWNLOADS_URL, _ARCHIVE_9_URL, _ARCHIVE_PRE9_URL):
            url = f"{base_url}/{version}/{tarball}"
            logger.info("Downloading Solr %s from %s", version, url)
            try:
                urllib.request.urlretrieve(url, dest)
                logger.info("Downloaded Solr %s to %s", version, dest)
                return dest
            except Exception as exc:
                logger.warning("Download from %s failed: %s", url, exc)
                if os.path.exists(dest):
                    os.remove(dest)

        raise SolrProvisionerError(
            f"Could not download Solr {version} from any mirror. "
            f"Please download manually to {dest}."
        )

    def install(self, version: str, install_dir: str) -> str:
        """
        Extract the Solr tarball into install_dir.

        Returns the path to the extracted Solr root (i.e., {install_dir}/solr-{version}).
        If install_dir already contains an extracted Solr, skips extraction.
        """
        solr_root = os.path.join(install_dir, f"solr-{version}")
        if os.path.isdir(solr_root):
            logger.info("Solr %s already installed at %s", version, solr_root)
            return solr_root

        tarball = os.path.join(self.cache_dir, f"solr-{version}.tgz")
        if not os.path.exists(tarball):
            tarball = self.download(version)

        os.makedirs(install_dir, exist_ok=True)
        logger.info("Extracting Solr %s to %s", version, install_dir)
        with tarfile.open(tarball, "r:gz") as tf:
            tf.extractall(install_dir)
        logger.info("Installed Solr %s at %s", version, solr_root)
        return solr_root

    def start(self, solr_root: str, mode: str = None) -> None:
        """
        Start Solr using bin/solr start.

        Args:
            solr_root: Path to the extracted Solr root directory.
            mode:      "cloud" (default), "user-managed", or None (defaults to "cloud").
        """
        if mode is None:
            mode = "cloud"

        bin_solr = self._bin_solr(solr_root)

        cmd = [bin_solr, "start", "-p", str(self.port)]
        if mode == "cloud":
            cmd.append("-c")  # SolrCloud mode
        elif mode == "user-managed":
            pass  # standalone (default in Solr 10+)

        logger.info("Starting Solr with: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SolrProvisionerError(
                f"Solr failed to start: {result.stderr or result.stdout}"
            )

        self._wait_for_ready()
        logger.info("Solr started on port %d", self.port)

    def stop(self, solr_root: str) -> None:
        """Stop Solr using bin/solr stop."""
        bin_solr = self._bin_solr(solr_root)
        cmd = [bin_solr, "stop", "-p", str(self.port)]
        logger.info("Stopping Solr on port %d", self.port)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("Solr stop returned non-zero: %s", result.stderr or result.stdout)
        else:
            logger.info("Solr stopped.")

    def clean(self, install_dir: str) -> None:
        """Remove the extracted Solr installation directory."""
        if os.path.isdir(install_dir):
            logger.info("Removing Solr installation at %s", install_dir)
            shutil.rmtree(install_dir, ignore_errors=True)
        else:
            logger.info("Nothing to clean at %s", install_dir)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _bin_solr(self, solr_root: str) -> str:
        script = os.path.join(solr_root, "bin", "solr")
        if not os.path.isfile(script):
            raise SolrProvisionerError(
                f"bin/solr not found in {solr_root}. "
                "Ensure install() was called first."
            )
        return script

    def _detect_version(self, solr_root: str) -> str:
        """Read version from the Solr installation directory name."""
        name = Path(solr_root).name  # e.g. "solr-9.7.0"
        if name.startswith("solr-"):
            return name[len("solr-"):]
        return ""

    def _wait_for_ready(self) -> None:
        """Poll GET /api/node/system until Solr responds or timeout."""
        url = f"http://localhost:{self.port}/api/node/system"
        deadline = time.monotonic() + self.startup_timeout
        last_exc = None
        while time.monotonic() < deadline:
            try:
                resp = requests.get(url, timeout=5)
                if resp.ok:
                    return
            except Exception as exc:
                last_exc = exc
            time.sleep(2)
        raise SolrProvisionerError(
            f"Solr did not become ready within {self.startup_timeout}s. "
            f"Last error: {last_exc}"
        )


# ---------------------------------------------------------------------------
# Docker launcher (T019)
# ---------------------------------------------------------------------------

class SolrDockerLauncher:
    """
    Launch an official Solr Docker container for benchmarking.

    Uses the ``docker`` CLI; Docker must be installed and available in PATH.

    Supported modes:
      - "cloud" (default) → runs Solr in SolrCloud mode (SOLR_CLOUD_MODE=yes)
      - "user-managed"    → runs Solr in standalone mode

    Example:
        launcher = SolrDockerLauncher(port=8983)
        launcher.start("9")   # pulls solr:9 if needed
        # ... run benchmark ...
        launcher.stop()
    """

    DEFAULT_CONTAINER_NAME = "solr-benchmark"

    def __init__(self, port: int = 8983, startup_timeout: int = 60,
                 container_name: str = None):
        self.port = port
        self.startup_timeout = startup_timeout
        self.container_name = container_name or self.DEFAULT_CONTAINER_NAME

    def start(self, version_tag: str = "9", mode: str = None) -> None:
        """
        Start a Solr container.

        Args:
            version_tag: Docker image tag, e.g. "9.10.1", "10.0.0-SNAPSHOT".
                         SNAPSHOT builds are pulled from apache/solr-nightly;
                         stable releases use the official solr image.
            mode:        "cloud" (default), "user-managed", or None (defaults to "cloud").
        """
        if mode is None:
            mode = "cloud"

        # SNAPSHOT builds live in apache/solr-nightly; stable releases use the official solr image
        if "SNAPSHOT" in version_tag.upper():
            image = f"apache/solr-nightly:{version_tag}"
        else:
            image = f"solr:{version_tag}"

        # Build the command — pass '-c' after the image to start in cloud mode
        cmd = [
            "docker", "run",
            "--rm",
            "--name", self.container_name,
            "-p", f"{self.port}:8983",
            "-d",
            image,
        ]
        if mode == "cloud":
            cmd.append("-c")  # SolrCloud mode

        # Remove any stale container with the same name before starting
        subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True, text=True)

        logger.info("Starting Solr Docker container: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SolrProvisionerError(
                f"Failed to start Solr Docker container: {result.stderr or result.stdout}"
            )

        self._wait_for_ready()
        logger.info("Solr Docker container '%s' ready on port %d", self.container_name, self.port)

    def stop(self) -> None:
        """Stop and remove the Solr container."""
        cmd = ["docker", "rm", "-f", self.container_name]
        logger.info("Stopping Solr container '%s'", self.container_name)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("docker rm returned non-zero: %s", result.stderr or result.stdout)
        else:
            logger.info("Container '%s' removed.", self.container_name)

    def _wait_for_ready(self) -> None:
        """Poll until Solr container responds on localhost:{port}."""
        url = f"http://localhost:{self.port}/api/node/system"
        deadline = time.monotonic() + self.startup_timeout
        last_exc = None
        while time.monotonic() < deadline:
            try:
                resp = requests.get(url, timeout=5)
                if resp.ok:
                    return
            except Exception as exc:
                last_exc = exc
            time.sleep(2)
        raise SolrProvisionerError(
            f"Solr container did not become ready within {self.startup_timeout}s. "
            f"Last error: {last_exc}"
        )
