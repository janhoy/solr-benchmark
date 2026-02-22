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
OpenSearch Query DSL to Solr Query Syntax Translation

This module handles translation of OpenSearch Query DSL (JSON-based query language)
to Solr's Lucene query syntax.

IMPORTANT: This module should ONLY be used when converting OpenSearch workloads.
Native Solr workloads should not go through this translation layer.
"""

import logging
from datetime import datetime

from .field import normalize_field_name

logger = logging.getLogger(__name__)


def translate_opensearch_query(body: dict) -> str:
    """
    Translate an OpenSearch query DSL dict to a Solr ``q`` string.

    Supported patterns:
      - ``match_all``             → ``*:*``
      - ``term``                  → ``field:value``
      - ``terms``                 → ``field:(v1 v2 v3)``
      - ``match`` / ``match_phrase`` → ``field:value``
      - ``range``                 → ``field:[lo TO hi]``
      - ``exists``                → ``field:[* TO *]``
      - ``bool`` (must/filter/should/must_not) → recursive translation
      - ``ids``                   → ``id:(id1 id2 ...)``

    Falls back to ``*:*`` for unrecognised patterns (logs warning).

    Args:
        body: OpenSearch query body dict with "query" key

    Returns:
        Solr query string suitable for the q parameter

    Examples:
        >>> translate_opensearch_query({"query": {"match_all": {}}})
        '*:*'
        >>> translate_opensearch_query({"query": {"term": {"country": "US"}}})
        'country:US'
    """
    if not body or not isinstance(body, dict):
        return "*:*"
    query = body.get("query", {})
    return _translate_query_node(query)


def extract_sort_parameter(body: dict) -> str:
    """
    Extract a Solr sort string from an OpenSearch sort clause.

    Args:
        body: OpenSearch query body dict with optional "sort" key

    Returns:
        Solr sort parameter string (e.g., "name_raw desc, _score asc")
        or None if no sort clause present

    Examples:
        >>> extract_sort_parameter({"sort": [{"name.raw": "desc"}]})
        'name_raw desc'
    """
    if not isinstance(body, dict) or "sort" not in body:
        return None
    sort_clauses = body["sort"]
    if isinstance(sort_clauses, dict):
        sort_clauses = [sort_clauses]
    solr_sorts = []
    for clause in sort_clauses:
        if isinstance(clause, str):
            # Normalize field name before adding to sort
            field = normalize_field_name(clause.split()[0] if " " in clause else clause)
            suffix = " " + clause.split()[1] if " " in clause else ""
            solr_sorts.append(field + suffix)
        elif isinstance(clause, dict):
            for field, order_info in clause.items():
                if field == "_score":
                    continue
                # Normalize field name
                field = normalize_field_name(field)
                if isinstance(order_info, dict):
                    order = order_info.get("order", "asc")
                elif isinstance(order_info, str):
                    order = order_info
                else:
                    order = "asc"
                solr_sorts.append(f"{field} {order}")
    return ", ".join(solr_sorts) if solr_sorts else None


# ---------------------------------------------------------------------------
# Internal helper functions
# ---------------------------------------------------------------------------

def _translate_query_node(node: dict) -> str:
    """Recursively translate a single OpenSearch query node to Solr syntax."""
    if not node or not isinstance(node, dict):
        return "*:*"

    if "match_all" in node:
        return "*:*"

    if "match_none" in node:
        return "-*:*"

    if "term" in node:
        for field, value in node["term"].items():
            v = value.get("value", value) if isinstance(value, dict) else value
            field = normalize_field_name(field)
            return f"{field}:{_escape_solr_value(v)}"

    if "terms" in node:
        for field, values in node["terms"].items():
            if field.startswith("_"):
                continue
            field = normalize_field_name(field)
            escaped = " ".join(_escape_solr_value(v) for v in values)
            return f"{field}:({escaped})"

    if "match" in node or "match_phrase" in node:
        sub = node.get("match") or node.get("match_phrase")
        for field, value in sub.items():
            v = value.get("query", value) if isinstance(value, dict) else value
            field = normalize_field_name(field)
            return f"{field}:{_escape_solr_value(v)}"

    if "range" in node:
        for field, bounds in node["range"].items():
            field = normalize_field_name(field)
            lo = bounds.get("gte", bounds.get("gt", "*"))
            hi = bounds.get("lte", bounds.get("lt", "*"))
            # Convert dates if format is specified (common for date fields)
            os_format = bounds.get("format")
            lo = _convert_date_to_solr_format(lo, os_format)
            hi = _convert_date_to_solr_format(hi, os_format)
            return f"{field}:[{lo} TO {hi}]"

    if "exists" in node:
        field = node["exists"].get("field", "*")
        field = normalize_field_name(field)
        return f"{field}:[* TO *]"

    if "ids" in node:
        values = node["ids"].get("values", [])
        if values:
            escaped = " ".join(_escape_solr_value(v) for v in values)
            return f"id:({escaped})"
        return "*:*"

    if "bool" in node:
        bool_q = node["bool"]
        parts = []

        def _add(clauses, prefix):
            if not clauses:
                return
            if isinstance(clauses, dict):
                clauses = [clauses]
            for clause in clauses:
                sub = _translate_query_node(clause)
                if sub and sub != "*:*":
                    parts.append(f"{prefix}({sub})")

        _add(bool_q.get("must"), "+")
        _add(bool_q.get("filter"), "+")
        _add(bool_q.get("must_not"), "-")

        shoulds = bool_q.get("should", [])
        if isinstance(shoulds, dict):
            shoulds = [shoulds]
        should_parts = [_translate_query_node(s) for s in shoulds]
        should_parts = [s for s in should_parts if s and s != "*:*"]
        if should_parts:
            parts.append("(" + " ".join(should_parts) + ")")

        return " ".join(parts) if parts else "*:*"

    # Unknown / untranslatable query node
    logger.warning(
        "Cannot translate OpenSearch query type '%s' to Solr syntax. "
        "Falling back to q=*:* (results may not match workload intent). "
        "Consider rewriting this operation as a native Solr workload task.",
        list(node.keys()),
    )
    return "*:*"


def _escape_solr_value(value) -> str:
    """Escape special Lucene/Solr query characters in a field value."""
    special = r'+-&&||!(){}[]^"~*?:\/'
    result = []
    for char in str(value):
        if char in special:
            result.append('\\' + char)
        else:
            result.append(char)
    return ''.join(result)


def _convert_date_to_solr_format(date_str, os_format=None) -> str:
    """
    Convert an OpenSearch date string to Solr ISO 8601 format.

    Args:
        date_str: Date string in various OpenSearch formats
        os_format: Optional OpenSearch date format pattern (e.g., "dd/MM/yyyy")

    Returns:
        ISO 8601 date string for Solr (e.g., "2015-01-01T00:00:00Z")

    If the date is already in ISO format or conversion fails, returns the
    original string unchanged.
    """
    if not isinstance(date_str, str) or date_str in ("*", "now"):
        return date_str

    # Map OpenSearch date format patterns to Python strptime format
    OS_TO_PYTHON_FORMAT = {
        "dd/MM/yyyy": "%d/%m/%Y",
        "MM/dd/yyyy": "%m/%d/%Y",
        "yyyy-MM-dd": "%Y-%m-%d",
        "yyyy/MM/dd": "%Y/%m/%d",
        "dd-MM-yyyy": "%d-%m-%Y",
        "MM-dd-yyyy": "%m-%d-%Y",
        # Add more as needed
    }

    # If format is provided, use it to parse the date
    if os_format:
        python_fmt = OS_TO_PYTHON_FORMAT.get(os_format)
        if python_fmt:
            try:
                dt = datetime.strptime(date_str, python_fmt)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                logger.warning(f"Failed to parse date '{date_str}' with format '{os_format}'")
                return date_str
        else:
            logger.warning(f"Unknown OpenSearch date format: '{os_format}'")

    # Try common patterns if no format specified
    for python_fmt in OS_TO_PYTHON_FORMAT.values():
        try:
            dt = datetime.strptime(date_str, python_fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    # If it's already in ISO-like format, return as-is
    # (handles cases like "2015-01-01T00:00:00Z" or partial ISO)
    if "T" in date_str or len(date_str) == 10:  # YYYY-MM-DD
        return date_str

    logger.warning(f"Could not parse date '{date_str}', using as-is")
    return date_str
