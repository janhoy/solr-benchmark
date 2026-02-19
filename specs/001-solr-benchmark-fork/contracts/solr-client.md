# Contract: SolrAdminClient Interface

**Feature**: 001-solr-benchmark-fork
**Date**: 2026-02-19
**Module**: `osbenchmark/solr/client.py`

---

## Purpose

`SolrAdminClient` is a thin wrapper around `requests.Session` that handles Solr V2 API admin operations — collection management, version detection, cluster status, and metrics retrieval. It is **not** used for high-frequency data operations (indexing, search, commit); those are handled by `pysolr`.

---

## Interface

```python
class SolrAdminClient:

    def __init__(self, host: str, port: int = 8983,
                 username: str | None = None,
                 password: str | None = None,
                 tls: bool = False) -> None:
        """
        Args:
            host:     Solr hostname or IP
            port:     Solr port (default 8983)
            username: HTTP Basic Auth username (optional)
            password: HTTP Basic Auth password (optional)
            tls:      Use HTTPS if True (default False)
        """

    def get_version(self) -> str:
        """
        Detect Solr version via GET /api/node/system.

        Returns:
            Version string, e.g. "9.7.0"

        Raises:
            SolrClientError: if the request fails or version cannot be parsed
        """

    def get_major_version(self) -> int:
        """
        Return the major version integer (9 or 10).
        Parsed from get_version().
        """

    def upload_configset(self, name: str, configset_dir: str) -> None:
        """
        Zip the configset directory and upload it via PUT /api/cluster/configs/{name}.

        The directory must contain conf/schema.xml and conf/solrconfig.xml at minimum.
        Additional files (synonyms, stopwords, etc.) are included automatically.

        Args:
            name:           Configset name to register on the cluster
            configset_dir:  Local path to the directory containing the conf/ folder

        Raises:
            SolrClientError: if the upload fails
        """

    def delete_configset(self, name: str) -> None:
        """
        Delete a configset via DELETE /api/cluster/configs/{name}.

        Raises:
            SolrClientError: if deletion fails
        """

    def create_collection(self,
                          name: str,
                          configset: str,
                          num_shards: int = 1,
                          replication_factor: int = 1,
                          wait_for_active_shards: int | str = 1) -> None:
        """
        Create a Solr collection via POST /api/collections.

        Args:
            name:                    Collection name
            configset:               Configset name (must exist on cluster)
            num_shards:              Number of shards (default 1)
            replication_factor:      Replicas per shard (default 1)
            wait_for_active_shards:  Number of active shards to wait for, or "all"

        Raises:
            SolrClientError: if creation fails (non-200 response or Solr error body)
            CollectionAlreadyExistsError: if collection already exists
        """

    def delete_collection(self, name: str) -> None:
        """
        Delete a Solr collection via DELETE /api/collections/{name}.

        Raises:
            SolrClientError: if deletion fails
            CollectionNotFoundError: if collection does not exist
        """

    def get_cluster_status(self) -> dict:
        """
        Return cluster state via GET /api/cluster.

        Returns:
            Parsed JSON response body (the "cluster" key dict).
        """

    def get_node_metrics(self) -> dict | str:
        """
        Retrieve node metrics via GET /api/node/metrics.

        Automatically detects response format by Content-Type:
          - Solr 9.x: returns parsed JSON dict
          - Solr 10.x: returns raw Prometheus exposition text (str)

        The caller (telemetry device) is responsible for parsing the
        format-specific response.

        Returns:
            dict (Solr 9.x JSON) or str (Solr 10.x Prometheus text)
        """

    def raw_request(self, method: str, path: str,
                    body: dict | str | None = None,
                    headers: dict | None = None) -> requests.Response:
        """
        Send an arbitrary HTTP request to a Solr endpoint.
        Used by the `raw-request` workload operation type.

        Args:
            method:  HTTP method ("GET", "POST", "DELETE", etc.)
            path:    URL path relative to http://{host}:{port}/ (e.g., "/api/cluster")
            body:    Request body (dict serialized to JSON, or raw string)
            headers: Additional request headers

        Returns:
            requests.Response object (caller handles status checking)
        """
```

---

## Error Types

```python
class SolrClientError(Exception):
    """Base for all SolrAdminClient errors."""

class CollectionAlreadyExistsError(SolrClientError):
    """Raised when create_collection() targets an existing collection."""

class CollectionNotFoundError(SolrClientError):
    """Raised when delete_collection() targets a non-existent collection."""
```

---

## Behaviour Contracts

1. All methods that make HTTP calls retry **once** on connection timeout before raising `SolrClientError`.
2. `create_collection()` and `delete_collection()` block until the operation completes or times out (configurable via `SolrAdminClient(timeout=30)`).
3. `get_node_metrics()` detects format from `Content-Type` response header:
   - `application/json` → parse as JSON, return dict
   - `text/plain` (Prometheus) → return raw string unchanged
4. All methods raise on non-2xx HTTP status after parsing the Solr error body for a human-readable message.
5. The client is **not thread-safe**. Each worker process creates its own instance.

---

## Data Operations: pysolr

High-frequency operations use `pysolr.Solr` directly, not `SolrAdminClient`:

```python
import pysolr

# One instance per worker, per collection
solr = pysolr.Solr(f"http://{host}:{port}/solr/{collection}", timeout=10)

# Bulk index
solr.add(docs, commit=False)           # docs: list[dict]

# Search
results = solr.search("q=*:*&rows=10")

# Commit
solr.commit()

# Soft commit
solr.commit(softCommit=True)

# Optimize
solr.optimize()
```

pysolr handles HTTP transport, response parsing, and basic error wrapping for these operations. Errors surface as `pysolr.SolrError`.

---

## Testing Guidance

Mock `SolrAdminClient` at the boundary using `unittest.mock.MagicMock`:

```python
from unittest.mock import MagicMock, patch

with patch("osbenchmark.solr.runner.SolrAdminClient") as MockClient:
    instance = MockClient.return_value
    instance.get_version.return_value = "9.7.0"
    instance.create_collection.return_value = None
    # ... run the code under test
    instance.create_collection.assert_called_once_with(
        name="my-collection", configset="_default"
    )
```

For pysolr operations, patch `pysolr.Solr`:

```python
with patch("osbenchmark.solr.runner.pysolr.Solr") as MockSolr:
    instance = MockSolr.return_value
    instance.add.return_value = None
    instance.search.return_value = MagicMock(hits=100)
```
