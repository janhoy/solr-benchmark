---
title: Sharing Custom Workloads
parent: Working with Workloads
grand_parent: User Guide
nav_order: 13
---

# Sharing Custom Workloads

You can share a custom workload with other Apache Solr Benchmark users by uploading it to the [solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads) repository on GitHub.

Make sure that any data included in the workload's dataset does not contain proprietary data or personally identifiable information (PII).

To share a custom workload, follow these steps.

## Create a README.md

Provide a detailed `README.md` file that includes the following:

- The purpose of the workload. When writing a description, consider the specific use case and how it differs from other workloads in the [solr-benchmark-workloads repository](https://github.com/janhoy/solr-benchmark-workloads).
- An example document from the dataset that helps users understand the data's structure.
- The workload parameters that can be used to customize the workload.
- A list of default test procedures included in the workload, as well as other test procedures the workload can run.
- A sample of the console output produced after a test run.
- A copy of the open-source license that gives users and Apache Solr Benchmark permission to use the dataset.

For an example, see the `nyc_taxis` [README](https://github.com/janhoy/solr-benchmark-workloads/blob/main/nyc_taxis/README.md) in the workloads repository.

## Verify the workload's structure

The workload must include the following files:

- `workload.json` — the main workload definition (collections, corpora, operations, test procedures)
- `files.txt` — lists the corpus data files used by the workload
- `test_procedures/default.json` or `operations/default.json` — at least one operations or test-procedures file (the file names can be customized to be descriptive)

Solr workloads typically also include a `configsets/` directory containing a `schema.xml` and `solrconfig.xml` for the collection. If no configset is provided, Apache Solr Benchmark will attempt to auto-generate a basic schema from the workload's document structure.

The workload can include an optional `workload.py` file to add dynamic functionality. For more information about file contents, see [Anatomy of a Workload](../understanding-workloads/anatomy-of-a-workload.html).

## Testing the workload

All workloads contributed to the repository must fulfil the following requirements:

- All test runs used to produce example output must target a live Apache Solr cluster.
- The workload must run successfully end-to-end with `--test-mode` against at least one supported Solr version:

  ```bash
  solr-benchmark run \
    --pipeline benchmark-only \
    --target-hosts localhost:8983 \
    --workload-path /path/to/your/workload \
    --test-mode
  ```

- The workload must also complete a full (non-test-mode) run without errors, and the result summary should be included in the pull request description.

To test the workload against the integration suite:

1. Add the workload to your fork of the [solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads) repository.
2. In your fork of the [solr-benchmark](https://github.com/janhoy/solr-benchmark) repository, update the workload repository path in your benchmark configuration to point to your forked workloads repository.
3. Run the workload against a Solr cluster and verify that all operations complete with a `0.00%` error rate.

## Create a pull request

After testing the workload, create a pull request (PR) from your fork to the [solr-benchmark-workloads](https://github.com/janhoy/solr-benchmark-workloads) repository. Include a sample console output and summary result in the PR description.

The maintainers will review the workload structure, README, licensing, and test results.

Once the PR is approved, coordinate with the maintainers about hosting the data corpora so it can be made available for other users to download.
