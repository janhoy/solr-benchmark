# Legal Review Checklist — Apache Solr Benchmark Fork

Generated: 2026-02-19

## Per-file License Header Status

### New files added by this fork (Category A — ASF-originated)

All new files carry the standard ASF header block:

```
# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. ...
# The ASF licenses this file to You under the Apache License, Version 2.0
```

| File | Header Present | Notes |
|------|---------------|-------|
| osbenchmark/solr/__init__.py | ✅ | |
| osbenchmark/solr/client.py | ✅ | |
| osbenchmark/solr/result_writer.py | ✅ | |
| osbenchmark/solr/runner.py | ✅ | |
| osbenchmark/solr/provisioner.py | ✅ | |
| osbenchmark/solr/telemetry.py | ✅ | |
| osbenchmark/solr/config.py | ✅ | |
| osbenchmark/solr/metrics.py | ✅ | |
| osbenchmark/solr/publisher.py | ✅ | |
| osbenchmark/tools/migrate_workload.py | ✅ | |
| osbenchmark/tools/__init__.py | ✅ | |
| solrbenchmark/__init__.py | ✅ | |
| solrbenchmark/main.py | ✅ | |
| tests/unit/solr/__init__.py | ✅ | Fixed 2026-02-19 |
| tests/unit/solr/test_client.py | ✅ | |
| tests/unit/solr/test_result_writer.py | ✅ | |
| tests/unit/solr/test_runner.py | ✅ | |
| tests/unit/solr/test_telemetry.py | ✅ | |
| tests/unit/solr/test_migrate_workload.py | ✅ | |

### Inherited files (Category B — OpenSearch Contributors / Elasticsearch origin)

Existing files in the `osbenchmark/` package carry the original header chain
(OpenSearch Contributors + Elasticsearch B.V.) and are retained unchanged.
This is correct per ASF policy for derivative works: the original copyright
notices must not be removed.

Spot-checked files:
| File | Original author preserved | Notes |
|------|--------------------------|-------|
| osbenchmark/__init__.py | ✅ OpenSearch Contributors + Elasticsearch B.V. | |
| osbenchmark/benchmark.py | ✅ OpenSearch Contributors + Elasticsearch B.V. | |
| osbenchmark/workload/workload.py | ✅ OpenSearch Contributors + Elasticsearch B.V. | |
| osbenchmark/worker_coordinator/runner.py | ✅ OpenSearch Contributors + Elasticsearch B.V. | |
| osbenchmark/workload/loader.py | ✅ OpenSearch Contributors + Elasticsearch B.V. | |
| osbenchmark/telemetry.py | ✅ OpenSearch Contributors + Elasticsearch B.V. | |

## NOTICE file

- ✅ Top of NOTICE identifies this product as "Apache Solr Benchmark"
- ✅ Copyright year and entity: "2024 The Apache Software Foundation"
- ✅ Attribution chain retained: OpenSearch Contributors (2022) + Elasticsearch B.V.

## LICENSE file

- ✅ Preamble identifies "Apache Solr Benchmark" and "The Apache Software Foundation"
- ✅ Full Apache License 2.0 text retained

## Third-party dependencies

Key runtime dependencies and their licenses (all Apache 2.0 compatible):

| Package | License | Notes |
|---------|---------|-------|
| pysolr | Apache 2.0 | Solr client |
| requests | Apache 2.0 | HTTP client |
| tabulate | MIT | Results table formatting |
| thespian | MIT | Actor framework (retained from OSB) |
| boto3 | Apache 2.0 | AWS SDK (retained from OSB) |
| opensearch-py | Apache 2.0 | Retained for metrics store compatibility |
| psutil | BSD 3-Clause | System metrics |
| Jinja2 | BSD 3-Clause | Template rendering |

All licenses are Category A (Apache 2.0) or Category B (MIT, BSD) per ASF
third-party licensing policy — no Category X (GPL/LGPL) dependencies.

## Open items

- [ ] When submitting to Apache Incubator/TLP, add "Incubating" disclaimer if
  required by the PMC.
- [ ] Verify `tabulate` (MIT) is listed in LICENSE under "bundled dependencies"
  section if the distribution includes it vendored (currently it is a pip
  dependency, not vendored — no action needed).
