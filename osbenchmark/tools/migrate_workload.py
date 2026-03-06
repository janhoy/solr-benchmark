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
OSB-to-Solr workload migration utility.

Translates an OpenSearch Benchmark workload JSON/YAML to an equivalent
Solr Benchmark workload JSON.

Translation rules:
  - ``index``        → ``collection``
  - ``type``         → ``configset``  (mapping type → Solr schema configset)
  - ``bulk``         → ``bulk-index``
  - ``search``       → ``search``  (query params preserved)
  - ``force-merge``  → ``optimize``
  - Unsupported operations are retained with a ``# TODO: <reason>`` comment
    (stored as an ``_migration_todo`` key in the output).

Usage:
    python -m osbenchmark.tools.migrate_workload <input.json> <output.json>

    Or from code:
        from osbenchmark.tools.migrate_workload import migrate
        result = migrate(input_dict)
"""

import argparse
import json
from copy import deepcopy
from typing import Any, Dict

# Operations that can be directly translated
_OP_MAP = {
    "bulk": "bulk-index",
    "search": "search",
    "force-merge": "optimize",
    "create-index": "create-collection",
    "delete-index": "delete-collection",
    "raw-request": "raw-request",
    "sleep": "sleep",
    "cluster-health": "raw-request",  # Solr doesn't have an exact equivalent
}

# Operations with no direct Solr equivalent
_UNSUPPORTED_OPS = {
    "cluster-health": "No direct Solr equivalent — use raw-request to poll GET /api/cluster",
    "wait-for-recovery": "No Solr equivalent — remove or replace with a raw-request health check",
    "wait-for-snapshot-create": "Snapshots not applicable to Solr",
    "restore-snapshot": "Snapshots not applicable to Solr",
    "create-snapshot": "Snapshots not applicable to Solr",
    "delete-snapshot-repository": "Snapshots not applicable to Solr",
    "create-snapshot-repository": "Snapshots not applicable to Solr",
    "put-settings": "No direct Solr equivalent — use raw-request for Solr config API",
    "create-transform": "ML Transforms not applicable to Solr",
    "start-transform": "ML Transforms not applicable to Solr",
    "delete-transform": "ML Transforms not applicable to Solr",
    "create-data-stream": "Data streams not applicable to Solr",
    "delete-data-stream": "Data streams not applicable to Solr",
    "create-index-template": "Index templates not applicable — use configset for Solr",
    "delete-index-template": "Index templates not applicable to Solr",
    "shrink-index": "Not applicable to Solr",
    "put-pipeline": "Ingest pipelines not applicable to Solr",
    "delete-pipeline": "Ingest pipelines not applicable to Solr",
}


def _translate_operation(op: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate a single operation definition dict.

    Returns a new dict with Solr-native operation type and param names.
    May add ``_migration_todo`` for unsupported operations.
    """
    result = deepcopy(op)
    op_type = op.get("operation-type", op.get("type", ""))

    # Rename index → collection in params
    if "index" in result:
        result["collection"] = result.pop("index")
    if "indices" in result:
        result["collection"] = result.pop("indices")

    # Map operation type
    if op_type in _UNSUPPORTED_OPS:
        result["_migration_todo"] = (
            f"TODO: '{op_type}' has no direct Solr equivalent. "
            f"{_UNSUPPORTED_OPS[op_type]}"
        )
    elif op_type in _OP_MAP:
        result["operation-type"] = _OP_MAP[op_type]
        if "type" in result and result.get("type") == op_type:
            result["type"] = _OP_MAP[op_type]
    # else: unknown type — leave as-is with a todo
    elif op_type and op_type not in set(_OP_MAP.values()):
        result["_migration_todo"] = (
            f"TODO: Unknown operation type '{op_type}'. "
            "Verify this operation is supported by Solr Benchmark."
        )

    # Translate force-merge → optimize params
    if op_type == "force-merge" and "max-num-segments" in result:
        result["max-segments"] = result.pop("max-num-segments")

    return result


def _translate_workload(workload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate an entire workload dict from OSB format to Solr Benchmark format.
    """
    result = deepcopy(workload)

    # Translate top-level indices → collections
    if "indices" in result:
        result["collections"] = []
        for idx in result.pop("indices"):
            col = deepcopy(idx)
            col.pop("body", None)  # ES mapping body — replaced by configset
            col["configset"] = col.pop("name", col.get("name", ""))
            col.setdefault("configset-path", "# TODO: path to configset directory")
            result["collections"].append(col)

    # Translate corpora / document source format references
    # (no structural change needed — just record)

    # Translate challenges
    challenges = result.get("challenges", [])
    for challenge in challenges:
        _translate_challenge(challenge)

    # Single challenge shorthand
    if "schedule" in result:
        _translate_schedule(result)

    return result


def _translate_challenge(challenge: Dict[str, Any]) -> None:
    """Translate operations within a single challenge (in-place)."""
    default_params = challenge.get("default-test-procedure-parameters", {})
    if "index" in default_params:
        default_params["collection"] = default_params.pop("index")

    for test_procedure in challenge.get("test-procedures", [challenge]):
        _translate_schedule(test_procedure)


def _translate_schedule(container: Dict[str, Any]) -> None:
    """Translate the schedule list within a challenge or top-level (in-place)."""
    schedule = container.get("schedule", [])
    translated = []
    for step in schedule:
        if isinstance(step, dict):
            if "operation" in step and isinstance(step["operation"], dict):
                step["operation"] = _translate_operation(step["operation"])
            elif "operation" in step and isinstance(step["operation"], str):
                # Operation defined by name reference — no inline params to translate
                pass
            translated.append(step)
        else:
            translated.append(step)
    container["schedule"] = translated

    # Translate named operations definitions
    operations = container.get("operations", [])
    translated_ops = []
    for op in operations:
        if isinstance(op, dict):
            translated_ops.append(_translate_operation(op))
        else:
            translated_ops.append(op)
    if translated_ops:
        container["operations"] = translated_ops


def migrate(input_workload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate a workload dict from OSB format to Solr Benchmark format.

    Args:
        input_workload: Parsed workload JSON/dict.

    Returns:
        Translated workload dict.
    """
    return _translate_workload(input_workload)


def _print_summary(original: Dict, translated: Dict) -> None:
    """Print migration summary to stdout."""
    def _collect_todos(obj, todos=None):
        if todos is None:
            todos = []
        if isinstance(obj, dict):
            if "_migration_todo" in obj:
                todos.append(obj["_migration_todo"])
            for v in obj.values():
                _collect_todos(v, todos)
        elif isinstance(obj, list):
            for item in obj:
                _collect_todos(item, todos)
        return todos

    todos = _collect_todos(translated)
    print("\n=== Migration Summary ===")
    if todos:
        print(f"\nFound {len(todos)} item(s) requiring manual review:")
        for i, todo in enumerate(todos, 1):
            print(f"  {i}. {todo}")
    else:
        print("\nNo manual review items — migration appears complete.")
    print("========================\n")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate an OSB workload JSON to Solr Benchmark format."
    )
    parser.add_argument("input", help="Input workload JSON file path")
    parser.add_argument("output", help="Output workload JSON file path")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        workload = json.load(f)

    translated = migrate(workload)
    _print_summary(workload, translated)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(translated, f, indent=2)

    print(f"Translated workload written to: {args.output}")


if __name__ == "__main__":
    main()
