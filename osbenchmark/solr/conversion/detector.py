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
Workload Format Detection

Determines whether a workload is OpenSearch Benchmark format (requiring conversion)
or native Solr Benchmark format (no conversion needed).
"""

import logging

logger = logging.getLogger(__name__)


# OpenSearch-specific operation types
OPENSEARCH_OPERATIONS = {
    "create-index",
    "delete-index",
    "cluster-health",
    "refresh",
    "force-merge",
    "index",  # OpenSearch uses "index", Solr uses "bulk-index"
    "search",  # Could be either, check param-source
}

# Solr-specific operation types
SOLR_OPERATIONS = {
    "create-collection",
    "delete-collection",
    "bulk-index",
    "commit",
    "optimize",
}

# OpenSearch-specific param sources
OPENSEARCH_PARAM_SOURCES = {
    "opensearch-bulk-source",
    "opensearch-search-source",
}

# Solr-specific param sources
SOLR_PARAM_SOURCES = {
    "solr-bulk-source",
    "solr-search-source",
}


def is_opensearch_workload(workload) -> bool:
    """
    Detect if a workload is in OpenSearch Benchmark format.

    Detection strategy (in order of priority):
    1. Check for explicit "collections" key → Solr workload
    2. Check for explicit "indices" key → OpenSearch workload
    3. Check operation types in challenges
    4. Check param-source values
    5. Default to False (treat as Solr if unclear)

    Args:
        workload: Workload object or dict

    Returns:
        True if OpenSearch format (needs conversion), False if Solr format
    """
    # Handle both Workload objects and dicts
    if hasattr(workload, "indices"):
        # Workload object - check for collections attribute
        has_collections = hasattr(workload, "collections") and len(getattr(workload, "collections", [])) > 0
        has_indices = len(workload.indices) > 0

        if has_collections:
            logger.debug("Detected Solr workload (has collections)")
            return False
        if has_indices:
            logger.debug("Detected OpenSearch workload (has indices)")
            return True

    # For dicts, check keys directly
    if isinstance(workload, dict):
        if "collections" in workload:
            logger.debug("Detected Solr workload (collections key)")
            return False
        if "indices" in workload:
            logger.debug("Detected OpenSearch workload (indices key)")
            return True

    # Fallback: Check operation types and param sources
    is_opensearch = _detect_from_operations(workload)

    if is_opensearch:
        logger.info("Detected OpenSearch workload format - conversion will be applied")
    else:
        logger.debug("Detected Solr workload format - no conversion needed")

    return is_opensearch


def _detect_from_operations(workload) -> bool:
    """
    Detect format by examining operations in challenges/test procedures.

    Returns:
        True if OpenSearch format, False if Solr format
    """
    # Get test procedures (challenges)
    test_procedures = []
    if hasattr(workload, "test_procedures"):
        test_procedures = workload.test_procedures
    elif isinstance(workload, dict) and "challenges" in workload:
        # Raw dict format
        test_procedures = workload.get("challenges", [])

    opensearch_score = 0
    solr_score = 0

    for test_proc in test_procedures:
        # Get schedule
        schedule = []
        if hasattr(test_proc, "schedule"):
            schedule = test_proc.schedule
        elif isinstance(test_proc, dict):
            schedule = test_proc.get("schedule", [])

        for task in schedule:
            # Get operation
            operation = None
            if hasattr(task, "operation"):
                operation = task.operation
            elif isinstance(task, dict):
                operation = task.get("operation", {})

            if not operation:
                continue

            # Get operation type
            op_type = None
            if hasattr(operation, "type"):
                op_type = operation.type
            elif isinstance(operation, dict):
                op_type = operation.get("operation-type") or operation.get("type")

            if op_type in OPENSEARCH_OPERATIONS:
                opensearch_score += 2
            if op_type in SOLR_OPERATIONS:
                solr_score += 2

            # Check param-source
            param_source = None
            if hasattr(operation, "param_source"):
                param_source = operation.param_source
            elif isinstance(operation, dict):
                param_source = operation.get("param-source")

            if param_source in OPENSEARCH_PARAM_SOURCES:
                opensearch_score += 3
            if param_source in SOLR_PARAM_SOURCES:
                solr_score += 3

    logger.debug(f"Detection scores - OpenSearch: {opensearch_score}, Solr: {solr_score}")

    # If unclear, default to Solr (no conversion)
    return opensearch_score > solr_score


def should_convert_workload(workload) -> bool:
    """
    Convenience function - alias for is_opensearch_workload.

    Args:
        workload: Workload object or dict

    Returns:
        True if workload needs conversion (is OpenSearch format)
    """
    return is_opensearch_workload(workload)
