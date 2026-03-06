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

"""Unit tests for osbenchmark/tools/migrate_workload.py"""

import json
import os
import tempfile
import unittest

from osbenchmark.tools.migrate_workload import migrate, _translate_operation


class TestTranslateOperation(unittest.TestCase):
    def test_bulk_to_bulk_index(self):
        op = {"operation-type": "bulk", "bulk-size": 500}
        result = _translate_operation(op)
        self.assertEqual("bulk-index", result["operation-type"])

    def test_force_merge_to_optimize(self):
        op = {"operation-type": "force-merge", "max-num-segments": 1}
        result = _translate_operation(op)
        self.assertEqual("optimize", result["operation-type"])
        # max-num-segments → max-segments
        self.assertIn("max-segments", result)
        self.assertNotIn("max-num-segments", result)

    def test_search_preserved(self):
        op = {"operation-type": "search", "q": "*:*", "rows": 10}
        result = _translate_operation(op)
        self.assertEqual("search", result["operation-type"])
        self.assertEqual("*:*", result["q"])

    def test_index_renamed_to_collection(self):
        op = {"operation-type": "search", "index": "my-index"}
        result = _translate_operation(op)
        self.assertEqual("my-index", result["collection"])
        self.assertNotIn("index", result)

    def test_unsupported_op_gets_todo(self):
        op = {"operation-type": "wait-for-recovery"}
        result = _translate_operation(op)
        self.assertIn("_migration_todo", result)
        self.assertIn("TODO", result["_migration_todo"])

    def test_unknown_op_gets_todo(self):
        op = {"operation-type": "totally-unknown-op"}
        result = _translate_operation(op)
        self.assertIn("_migration_todo", result)

    def test_known_op_no_todo(self):
        op = {"operation-type": "search", "q": "*:*"}
        result = _translate_operation(op)
        self.assertNotIn("_migration_todo", result)

    def test_create_index_to_create_collection(self):
        op = {"operation-type": "create-index"}
        result = _translate_operation(op)
        self.assertEqual("create-collection", result["operation-type"])

    def test_delete_index_to_delete_collection(self):
        op = {"operation-type": "delete-index"}
        result = _translate_operation(op)
        self.assertEqual("delete-collection", result["operation-type"])

    def test_raw_request_preserved(self):
        op = {"operation-type": "raw-request", "method": "GET", "path": "/api/cluster"}
        result = _translate_operation(op)
        self.assertEqual("raw-request", result["operation-type"])


class TestMigrateWorkload(unittest.TestCase):
    def _workload(self):
        return {
            "name": "test-workload",
            "description": "A test workload",
            "indices": [
                {"name": "geonames", "body": {"mappings": {"properties": {}}}}
            ],
            "challenges": [
                {
                    "name": "default",
                    "schedule": [
                        {"operation": {"operation-type": "create-index"}},
                        {"operation": {"operation-type": "bulk", "bulk-size": 500}},
                        {"operation": {"operation-type": "search", "q": "*:*"}},
                        {"operation": {"operation-type": "force-merge"}},
                        {"operation": {"operation-type": "delete-index"}},
                    ],
                }
            ],
        }

    def test_all_operations_appear_in_output(self):
        """No operation should be silently dropped."""
        result = migrate(self._workload())
        schedule = result["challenges"][0]["schedule"]
        # Input has 5 operations; output must also have 5
        self.assertEqual(5, len(schedule))

    def test_indices_renamed_to_collections(self):
        result = migrate(self._workload())
        self.assertIn("collections", result)
        self.assertNotIn("indices", result)

    def test_bulk_translated(self):
        result = migrate(self._workload())
        schedule = result["challenges"][0]["schedule"]
        bulk_ops = [s for s in schedule
                    if s.get("operation", {}).get("operation-type") == "bulk-index"]
        self.assertEqual(1, len(bulk_ops))

    def test_force_merge_translated(self):
        result = migrate(self._workload())
        schedule = result["challenges"][0]["schedule"]
        optimize_ops = [s for s in schedule
                        if s.get("operation", {}).get("operation-type") == "optimize"]
        self.assertEqual(1, len(optimize_ops))

    def test_unsupported_ops_get_todo_not_dropped(self):
        workload = {
            "name": "test",
            "challenges": [
                {
                    "name": "default",
                    "schedule": [
                        {"operation": {"operation-type": "wait-for-recovery"}},
                        {"operation": {"operation-type": "search", "q": "*:*"}},
                    ],
                }
            ],
        }
        result = migrate(workload)
        schedule = result["challenges"][0]["schedule"]
        # Both operations must be present (not dropped)
        self.assertEqual(2, len(schedule))
        # The unsupported one must have a TODO
        unsupported = schedule[0]["operation"]
        self.assertIn("_migration_todo", unsupported)


class TestMigrateWorkloadCLI(unittest.TestCase):
    def test_cli_produces_output_file(self):
        workload = {
            "name": "cli-test",
            "challenges": [
                {"name": "default", "schedule": [
                    {"operation": {"operation-type": "bulk"}}
                ]}
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.json")
            output_path = os.path.join(tmpdir, "output.json")
            with open(input_path, "w") as f:
                json.dump(workload, f)

            # Simulate CLI via direct function call
            with open(input_path) as f:
                original = json.load(f)
            translated = migrate(original)
            with open(output_path, "w") as f:
                json.dump(translated, f, indent=2)

            self.assertTrue(os.path.isfile(output_path))
            with open(output_path) as f:
                out = json.load(f)
            ops = out["challenges"][0]["schedule"]
            self.assertEqual(1, len(ops))
            self.assertEqual("bulk-index", ops[0]["operation"]["operation-type"])


if __name__ == "__main__":
    unittest.main()
