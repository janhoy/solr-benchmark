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

import io
import logging
import zipfile
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class SolrClientError(Exception):
    """Base exception for all SolrAdminClient errors."""


class CollectionAlreadyExistsError(SolrClientError):
    """Raised when create_collection() targets an existing collection."""


class CollectionNotFoundError(SolrClientError):
    """Raised when delete_collection() targets a non-existent collection."""


class SolrAdminClient:
    """
    Thin wrapper around requests.Session for Solr V2 API admin operations.

    Handles collection management, configset upload, version detection,
    cluster status, and metrics retrieval. High-frequency data operations
    (indexing, search, commit, optimize) use pysolr directly in runner.py.

    Not thread-safe — each worker process creates its own instance.
    """

    def __init__(self, host: str, port: int = 8983,
                 username: str = None, password: str = None,
                 tls: bool = False, timeout: int = 30):
        scheme = "https" if tls else "http"
        self.base_url = f"{scheme}://{host}:{port}"
        self.api_url = f"{self.base_url}/api"
        self.timeout = timeout
        self._session = requests.Session()
        if username and password:
            self._session.auth = (username, password)
        self._session.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # Version detection
    # ------------------------------------------------------------------

    def get_version(self) -> str:
        """
        Detect Solr version via GET /api/node/system.

        Returns the version string, e.g. "9.7.0".
        """
        resp = self._get("/api/node/system")
        data = resp.json()
        try:
            return data["lucene"]["solr-spec-version"]
        except KeyError as exc:
            raise SolrClientError(
                f"Could not parse Solr version from /api/node/system response: {data}"
            ) from exc

    def get_major_version(self) -> int:
        """Return the major version integer (9 or 10)."""
        version = self.get_version()
        return int(version.split(".")[0])

    # ------------------------------------------------------------------
    # Configset management
    # ------------------------------------------------------------------

    def upload_configset(self, name: str, configset_dir: str) -> None:
        """
        Zip the configset directory and upload it via PUT /api/cluster/configs/{name}.

        The directory must contain a conf/ sub-directory with at minimum
        schema.xml (or managed-schema) and solrconfig.xml.

        Args:
            name:           Configset name to register on the cluster.
            configset_dir:  Local path to the directory containing conf/.
        """
        zip_bytes = self._build_configset_zip(configset_dir)
        url = f"{self.api_url}/cluster/configs/{name}"
        resp = self._session.put(
            url,
            data=zip_bytes,
            headers={"Content-Type": "application/zip"},
            timeout=self.timeout,
        )
        self._raise_for_solr_error(resp, f"upload configset '{name}'")
        logger.info("Uploaded configset '%s' from '%s'", name, configset_dir)

    def delete_configset(self, name: str) -> None:
        """Delete a configset via DELETE /api/cluster/configs/{name}."""
        resp = self._session.delete(
            f"{self.api_url}/cluster/configs/{name}",
            timeout=self.timeout,
        )
        self._raise_for_solr_error(resp, f"delete configset '{name}'")
        logger.info("Deleted configset '%s'", name)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def create_collection(self, name: str, configset: str,
                          num_shards: int = 1, replication_factor: int = 1,
                          wait_for_active_shards: int = 1) -> None:
        """
        Create a Solr collection via POST /api/collections.

        The configset must already exist on the cluster (call upload_configset first).
        """
        payload = {
            "name": name,
            "config": configset,
            "numShards": num_shards,
            "replicationFactor": replication_factor,
            "waitForFinalState": True,
        }
        resp = self._session.post(
            f"{self.api_url}/collections",
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code == 400:
            body = self._try_parse_json(resp)
            if "already exists" in str(body).lower():
                raise CollectionAlreadyExistsError(
                    f"Collection '{name}' already exists"
                )
        self._raise_for_solr_error(resp, f"create collection '{name}'")
        logger.info("Created collection '%s' (shards=%d, rf=%d)", name, num_shards, replication_factor)

    def delete_collection(self, name: str) -> None:
        """Delete a Solr collection via DELETE /api/collections/{name}."""
        resp = self._session.delete(
            f"{self.api_url}/collections/{name}",
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            raise CollectionNotFoundError(f"Collection '{name}' not found")
        self._raise_for_solr_error(resp, f"delete collection '{name}'")
        logger.info("Deleted collection '%s'", name)

    # ------------------------------------------------------------------
    # Cluster status
    # ------------------------------------------------------------------

    def get_cluster_status(self) -> dict:
        """Return cluster state via GET /api/cluster."""
        resp = self._get("/api/cluster")
        return resp.json().get("cluster", resp.json())

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_node_metrics(self):
        """
        Retrieve node metrics via GET /api/node/metrics.

        Detects response format by Content-Type:
          - application/json  → Solr 9.x custom JSON → returns parsed dict
          - text/plain        → Solr 10.x Prometheus text → returns raw str

        The telemetry device is responsible for parsing the format-specific response.
        """
        resp = self._get("/api/node/metrics")
        content_type = resp.headers.get("Content-Type", "")
        if "text/plain" in content_type:
            return resp.text
        return resp.json()

    # ------------------------------------------------------------------
    # Raw request (for the raw-request workload operation)
    # ------------------------------------------------------------------

    def raw_request(self, method: str, path: str,
                    body=None, headers: dict = None) -> requests.Response:
        """
        Send an arbitrary HTTP request to a Solr endpoint.

        Args:
            method:  HTTP method ("GET", "POST", "DELETE", etc.)
            path:    URL path relative to http://{host}:{port}/ (e.g. "/api/cluster")
            body:    Request body (dict → serialized as JSON, str → sent as-is)
            headers: Additional request headers
        """
        url = f"{self.base_url}{path}"
        req_headers = dict(headers or {})
        kwargs = {"timeout": self.timeout, "headers": req_headers}
        if isinstance(body, dict):
            kwargs["json"] = body
        elif isinstance(body, str):
            kwargs["data"] = body
        resp = self._session.request(method.upper(), url, **kwargs)
        return resp

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str) -> requests.Response:
        resp = self._session.get(f"{self.base_url}{path}", timeout=self.timeout)
        self._raise_for_solr_error(resp, f"GET {path}")
        return resp

    def _raise_for_solr_error(self, resp: requests.Response, operation: str) -> None:
        if resp.ok:
            return
        body = self._try_parse_json(resp)
        msg = body.get("error", {}).get("msg", resp.text) if isinstance(body, dict) else resp.text
        raise SolrClientError(
            f"Solr {operation} failed (HTTP {resp.status_code}): {msg}"
        )

    @staticmethod
    def _try_parse_json(resp: requests.Response) -> dict:
        try:
            return resp.json()
        except Exception:
            return {}

    @staticmethod
    def _build_configset_zip(configset_dir: str) -> bytes:
        """
        Walk configset_dir and produce an in-memory ZIP suitable for
        PUT /api/cluster/configs/{name}.
        """
        buf = io.BytesIO()
        root = Path(configset_dir)
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(root.rglob("*")):
                if file_path.is_file():
                    arcname = file_path.relative_to(root)
                    zf.write(file_path, arcname)
        return buf.getvalue()
