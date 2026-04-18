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

import logging

from osbenchmark.context import RequestContextHolder


class SolrClient(RequestContextHolder):
    """
    Single unified Solr client. Wraps SolrAdminClient (admin/HTTP) and pysolr.Solr
    (indexing/search) as private implementation details.

    All runners and telemetry devices receive a SolrClient and call methods
    on it directly — SolrAdminClient and pysolr.Solr are never referenced
    externally.
    """

    class _NoOpTransport:
        async def close(self):
            pass

    def __init__(self, host="localhost", port=8983, username=None, password=None,
                 tls=False, timeout=30):
        # pylint: disable=import-outside-toplevel
        from osbenchmark.solr.client import SolrAdminClient
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._tls = tls
        self._timeout = timeout
        self._admin = SolrAdminClient(host=host, port=port, username=username,
                                      password=password, tls=tls, timeout=timeout)
        self._pysolr_clients = {}  # collection → pysolr.Solr (created lazily)
        self.transport = SolrClient._NoOpTransport()

    # ------------------------------------------------------------------
    # Admin / cluster operations  (delegated to _admin)
    # ------------------------------------------------------------------

    def get_version(self):
        return self._admin.get_version()

    def get_major_version(self):
        return self._admin.get_major_version()

    def get_cluster_status(self):
        return self._admin.get_cluster_status()

    def get_node_metrics(self):
        return self._admin.get_node_metrics()

    def get_clusterstatus(self):
        return self._admin.get_clusterstatus()

    def get_core_status(self, core_name):
        return self._admin.get_core_status(core_name)

    def list_collections(self):
        return self._admin.list_collections()

    def get_luke_stats(self, collection):
        return self._admin.get_luke_stats(collection)

    def upload_configset(self, name, path):
        return self._admin.upload_configset(name, path)

    def delete_configset(self, name):
        return self._admin.delete_configset(name)

    def create_collection(self, name, *args, **kwargs):
        return self._admin.create_collection(name, *args, **kwargs)

    def delete_collection(self, name, **kwargs):
        return self._admin.delete_collection(name, **kwargs)

    def wait_for_cluster_ready(self, **kwargs):
        return self._admin.wait_for_cluster_ready(**kwargs)

    def raw_request(self, method, path, body=None, headers=None):
        return self._admin.raw_request(method, path, body=body, headers=headers)

    def count_documents(self, collection):
        return self._admin.count_documents(collection)

    def get_schema(self, collection):
        return self._admin.get_schema(collection)

    # ------------------------------------------------------------------
    # Data operations  (delegated to pysolr.Solr, per collection)
    # ------------------------------------------------------------------

    def _get_pysolr(self, collection: str):
        """Return (lazily-created, cached) pysolr.Solr for the given collection."""
        import pysolr  # pylint: disable=import-outside-toplevel
        import requests as _requests  # pylint: disable=import-outside-toplevel
        if collection not in self._pysolr_clients:
            scheme = "https" if self._tls else "http"
            url = f"{scheme}://{self._host}:{self._port}/solr/{collection}"
            session = _requests.Session()
            session.trust_env = False  # fork-safe on macOS (no CFNetwork proxy detection)
            if self._username and self._password:
                session.auth = (self._username, self._password)
            self._pysolr_clients[collection] = pysolr.Solr(
                url, timeout=self._timeout, always_commit=False, session=session)
        return self._pysolr_clients[collection]

    def add(self, collection, docs, **kwargs):
        return self._get_pysolr(collection).add(docs, **kwargs)

    def search(self, collection, q, **kwargs):
        return self._get_pysolr(collection).search(q, **kwargs)

    def commit(self, collection, **kwargs):
        return self._get_pysolr(collection).commit(**kwargs)

    def optimize(self, collection, **kwargs):
        return self._get_pysolr(collection).optimize(**kwargs)


class ClientFactory:
    """
    Factory that creates SolrClient instances from cluster host configuration.
    """

    def __init__(self, hosts, client_options):
        self._hosts = hosts
        self._client_options = dict(client_options)
        self.logger = logging.getLogger(__name__)

    def _parse_host(self):
        entry = self._hosts[0] if self._hosts else {}
        if isinstance(entry, dict):
            return entry.get("host", "localhost"), int(entry.get("port", 8983))
        parts = str(entry).rsplit(":", 1)
        host = parts[0] if parts else "localhost"
        port = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 8983
        return host, port

    def create(self):
        host, port = self._parse_host()
        return SolrClient(
            host=host,
            port=port,
            username=self._client_options.get("basic_auth_user"),
            password=self._client_options.get("basic_auth_password"),
            tls=self._client_options.get("use_ssl", False),
        )

    def create_async(self):
        return self.create()
