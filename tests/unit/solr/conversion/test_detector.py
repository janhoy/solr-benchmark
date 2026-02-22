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

"""Unit tests for osbenchmark/solr/conversion/detector.py"""

import unittest

from osbenchmark.solr.conversion.detector import is_opensearch_workload


class TestWorkloadDetection(unittest.TestCase):
    """Test workload format detection."""

    def test_detect_solr_workload_with_collections_key(self):
        """Test detection of Solr workload by collections key."""
        workload = {
            "name": "test-workload",
            "collections": [
                {"name": "my-collection", "configset": "my-configset"}
            ]
        }
        self.assertFalse(is_opensearch_workload(workload))

    def test_detect_opensearch_workload_with_indices_key(self):
        """Test detection of OpenSearch workload by indices key."""
        workload = {
            "name": "test-workload",
            "indices": [
                {"name": "my-index", "body": "index.json"}
            ]
        }
        self.assertTrue(is_opensearch_workload(workload))

    def test_detect_solr_by_operation_types(self):
        """Test detection based on Solr-specific operation types."""
        workload = {
            "name": "test-workload",
            "challenges": [
                {
                    "name": "default",
                    "schedule": [
                        {"operation": {"operation-type": "create-collection"}},
                        {"operation": {"operation-type": "bulk-index"}},
                        {"operation": {"operation-type": "commit"}},
                    ]
                }
            ]
        }
        self.assertFalse(is_opensearch_workload(workload))

    def test_detect_opensearch_by_operation_types(self):
        """Test detection based on OpenSearch-specific operation types."""
        workload = {
            "name": "test-workload",
            "challenges": [
                {
                    "name": "default",
                    "schedule": [
                        {"operation": {"operation-type": "create-index"}},
                        {"operation": {"operation-type": "index"}},
                        {"operation": {"operation-type": "force-merge"}},
                    ]
                }
            ]
        }
        self.assertTrue(is_opensearch_workload(workload))

    def test_detect_by_param_source(self):
        """Test detection based on param-source values."""
        opensearch_workload = {
            "name": "test-workload",
            "challenges": [
                {
                    "name": "default",
                    "schedule": [
                        {
                            "operation": {
                                "operation-type": "search",
                                "param-source": "opensearch-search-source"
                            }
                        }
                    ]
                }
            ]
        }
        self.assertTrue(is_opensearch_workload(opensearch_workload))

        solr_workload = {
            "name": "test-workload",
            "challenges": [
                {
                    "name": "default",
                    "schedule": [
                        {
                            "operation": {
                                "operation-type": "search",
                                "param-source": "solr-search-source"
                            }
                        }
                    ]
                }
            ]
        }
        self.assertFalse(is_opensearch_workload(solr_workload))

    def test_empty_workload_defaults_to_solr(self):
        """Test that empty/unclear workloads default to Solr (no conversion)."""
        workload = {"name": "test-workload"}
        self.assertFalse(is_opensearch_workload(workload))

    def test_mixed_signals_scores_correctly(self):
        """Test that scoring works correctly with mixed signals."""
        # More Solr signals than OpenSearch
        workload = {
            "name": "test-workload",
            "challenges": [
                {
                    "name": "default",
                    "schedule": [
                        {"operation": {"operation-type": "create-collection"}},  # Solr +2
                        {"operation": {"operation-type": "bulk-index"}},         # Solr +2
                        {"operation": {"operation-type": "commit"}},             # Solr +2
                        {"operation": {"operation-type": "search"}},             # Neutral
                    ]
                }
            ]
        }
        self.assertFalse(is_opensearch_workload(workload))


if __name__ == "__main__":
    unittest.main()
