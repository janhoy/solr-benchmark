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
DEPRECATED: This module has been moved to osbenchmark.solr.conversion.schema

This file provides backward compatibility for existing imports.
New code should import from osbenchmark.solr.conversion.schema instead.

IMPORTANT: This module is ONLY used when converting OpenSearch workloads.
Native Solr workloads should not use schema translation.
"""

import warnings

# Issue deprecation warning
warnings.warn(
    "osbenchmark.solr.schema_generator is deprecated. "
    "Use osbenchmark.solr.conversion.schema instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from the new location for backward compatibility
from osbenchmark.solr.conversion.schema import (  # noqa: F401
    OPENSEARCH_TO_SOLR_TYPES,
    translate_opensearch_mapping,
    generate_schema_xml,
    create_configset_from_schema,
    cleanup_configset,
)

__all__ = [
    "OPENSEARCH_TO_SOLR_TYPES",
    "translate_opensearch_mapping",
    "generate_schema_xml",
    "create_configset_from_schema",
    "cleanup_configset",
]
