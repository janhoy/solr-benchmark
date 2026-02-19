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

"""Unit tests for osbenchmark/solr/runner.py"""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from osbenchmark.solr.runner import (
    _translate_ndjson_batch,
    SolrBulkIndex,
    SolrSearch,
    SolrCommit,
    SolrOptimize,
    SolrCreateCollection,
    SolrDeleteCollection,
    SolrRawRequest,
)


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestTranslateNdjsonBatch(unittest.TestCase):
    def test_id_injected_from_action_line(self):
        lines = [
            '{"index": {"_id": "doc-1", "_index": "my-index"}}',
            '{"title": "hello", "body": "world"}',
        ]
        docs = _translate_ndjson_batch(lines)
        self.assertEqual(1, len(docs))
        self.assertEqual("doc-1", docs[0]["id"])
        self.assertEqual("hello", docs[0]["title"])

    def test_id_absent_when_action_has_no_id(self):
        lines = [
            '{"index": {"_index": "my-index"}}',
            '{"title": "no id"}',
        ]
        docs = _translate_ndjson_batch(lines)
        self.assertEqual(1, len(docs))
        self.assertNotIn("id", docs[0])

    def test_type_dropped(self):
        lines = [
            '{"index": {"_id": "1", "_type": "_doc", "_index": "idx"}}',
            '{"field": "value"}',
        ]
        docs = _translate_ndjson_batch(lines)
        self.assertNotIn("_type", docs[0])

    def test_index_not_stored_in_doc(self):
        lines = [
            '{"index": {"_id": "1", "_index": "my-collection"}}',
            '{"x": 1}',
        ]
        docs = _translate_ndjson_batch(lines)
        self.assertNotIn("_index", docs[0])
        self.assertNotIn("my-collection", docs[0].values())

    def test_multiple_pairs(self):
        lines = [
            '{"index": {"_id": "a"}}',
            '{"f": 1}',
            '{"index": {"_id": "b"}}',
            '{"f": 2}',
        ]
        docs = _translate_ndjson_batch(lines)
        self.assertEqual(2, len(docs))
        self.assertEqual("a", docs[0]["id"])
        self.assertEqual("b", docs[1]["id"])

    def test_malformed_json_skipped(self):
        lines = [
            "not json",
            '{"f": 1}',
        ]
        docs = _translate_ndjson_batch(lines)
        self.assertEqual(0, len(docs))

    def test_empty_lines_ignored(self):
        lines = ["", '{"index": {"_id": "1"}}', '{"f": 1}', ""]
        docs = _translate_ndjson_batch(lines)
        self.assertEqual(1, len(docs))


class TestSolrBulkIndex(unittest.TestCase):
    def _params(self, corpus_lines):
        return {
            "host": "localhost",
            "port": 8983,
            "collection": "test",
            "corpus": corpus_lines,
            "bulk-size": 500,
        }

    @patch("osbenchmark.solr.runner.pysolr.Solr")
    def test_bulk_index_returns_weight(self, mock_solr_cls):
        mock_solr = MagicMock()
        mock_solr.add = MagicMock(return_value=None)
        mock_solr_cls.return_value = mock_solr

        lines = [
            '{"index": {"_id": "1"}}',
            '{"title": "doc"}',
        ]
        runner = SolrBulkIndex()
        result = _run(runner(None, self._params(lines)))

        self.assertEqual(1, result["weight"])
        self.assertEqual("docs", result["unit"])
        self.assertTrue(result["success"])

    @patch("osbenchmark.solr.runner.pysolr.Solr")
    def test_bulk_index_reports_errors(self, mock_solr_cls):
        import pysolr
        mock_solr = MagicMock()
        mock_solr.add.side_effect = pysolr.SolrError("Indexing error")
        mock_solr_cls.return_value = mock_solr

        lines = [
            '{"index": {"_id": "1"}}',
            '{"title": "doc"}',
        ]
        runner = SolrBulkIndex()
        result = _run(runner(None, self._params(lines)))
        self.assertFalse(result["success"])
        self.assertGreater(result["error-count"], 0)


class TestSolrSearch(unittest.TestCase):
    def _base_params(self):
        return {
            "host": "localhost",
            "port": 8983,
            "collection": "test",
        }

    @patch("osbenchmark.solr.runner.pysolr.Solr")
    def test_classic_mode(self, mock_solr_cls):
        mock_results = MagicMock()
        mock_results.hits = 42
        mock_solr = MagicMock()
        mock_solr.search.return_value = mock_results
        mock_solr_cls.return_value = mock_solr

        params = {**self._base_params(), "q": "hello world", "rows": 10}
        runner = SolrSearch()
        result = _run(runner(None, params))

        self.assertEqual(42, result["hits"])
        self.assertEqual(1, result["weight"])

    @patch("osbenchmark.solr.runner.requests.post")
    def test_json_dsl_mode(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": {"numFound": 7}}
        mock_post.return_value = mock_resp

        params = {**self._base_params(), "body": {"query": {"match_all": {}}}}
        runner = SolrSearch()
        result = _run(runner(None, params))

        self.assertEqual(7, result["hits"])
        mock_post.assert_called_once()


class TestSolrCreateCollection(unittest.TestCase):
    @patch("osbenchmark.solr.runner.SolrAdminClient")
    def test_two_step_sequence(self, mock_admin_cls):
        import tempfile, os
        mock_admin = MagicMock()
        mock_admin.upload_configset = MagicMock()
        mock_admin.create_collection = MagicMock()
        mock_admin_cls.return_value = mock_admin

        with tempfile.TemporaryDirectory() as tmpdir:
            params = {
                "host": "localhost",
                "port": 8983,
                "collection": "my-coll",
                "configset": "my-config",
                "configset-path": tmpdir,
            }
            runner = SolrCreateCollection()
            _run(runner(None, params))

        # Verify upload_configset called before create_collection
        mock_admin.upload_configset.assert_called_once_with("my-config", tmpdir)
        mock_admin.create_collection.assert_called_once()


class TestSolrDeleteCollection(unittest.TestCase):
    @patch("osbenchmark.solr.runner.SolrAdminClient")
    def test_delete_ignores_missing_by_default(self, mock_admin_cls):
        from osbenchmark.solr.client import CollectionNotFoundError
        mock_admin = MagicMock()
        mock_admin.delete_collection.side_effect = CollectionNotFoundError("not found")
        mock_admin.delete_configset = MagicMock()
        mock_admin_cls.return_value = mock_admin

        params = {
            "host": "localhost",
            "port": 8983,
            "collection": "missing-coll",
            "ignore-missing": True,
        }
        runner = SolrDeleteCollection()
        # Should not raise
        _run(runner(None, params))


if __name__ == "__main__":
    unittest.main()
