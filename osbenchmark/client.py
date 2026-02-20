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

try:
    from osbenchmark.kafka_client import KafkaMessageProducer
except ImportError:
    KafkaMessageProducer = None
from osbenchmark import exceptions, doc_link
from osbenchmark.context import RequestContextHolder
from osbenchmark.utils import console

class SolrClientShim(RequestContextHolder):
    """
    Minimal client shim used in Solr benchmarks.

    Provides exactly what the OSB worker-coordinator framework needs:
      - new_request_context() — inherited from RequestContextHolder, supplies
        proper timing context for the async executor
      - transport — object with an async no-op close() for cleanup
    Everything else is deliberately absent; Solr runners do not use the client.
    """

    class _NoOpTransport:
        """Stub transport whose close() is a no-op awaitable."""
        async def close(self):
            pass

    transport = _NoOpTransport()


class OsClientFactory:
    """
    Client factory — always returns a SolrClientShim for this Solr benchmark fork.
    The host/client_options parameters are accepted for API compatibility but ignored.
    """
    def __init__(self, hosts, client_options):
        self.logger = logging.getLogger(__name__)

    def create(self):
        return SolrClientShim()

    def create_async(self):
        return SolrClientShim()


def wait_for_rest_layer(client, max_attempts=40):
    """
    In this Solr benchmark fork, always returns True immediately — the Solr cluster
    health check is handled separately via SolrAdminClient.
    """
    return True


class MessageProducerFactory:
    @staticmethod
    async def create(params):
        """
        Creates and returns a message producer based on the ingestion source.
        Currently supports Kafka. Ingestion source should be a dict like:
            {'type': 'kafka', 'param': {'topic': 'test', 'bootstrap-servers': 'localhost:34803'}}
        """
        ingestion_source = params.get("ingestion-source", {})
        producer_type = ingestion_source.get("type", "kafka").lower()
        if producer_type == "kafka":
            return await KafkaMessageProducer.create(params)
        else:
            raise ValueError(f"Unsupported ingestion source type: {producer_type}")


class UnifiedClient:
    """
    Unified client wrapper — delegates attribute access to the underlying client.
    """
    def __init__(self, inner_client):
        self._client = inner_client
        self._logger = logging.getLogger(__name__)

    def __getattr__(self, name):
        return getattr(self._client, name)

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass

    @property
    def client(self):
        """Provide access to the underlying client."""
        return self._client


class UnifiedClientFactory:
    """
    Factory that creates UnifiedClient instances.
    """
    def __init__(self, rest_client_factory, grpc_hosts=None):
        self.rest_client_factory = rest_client_factory
        self.logger = logging.getLogger(__name__)

    def create(self):
        raise NotImplementedError()

    def create_async(self):
        return UnifiedClient(self.rest_client_factory.create_async())
