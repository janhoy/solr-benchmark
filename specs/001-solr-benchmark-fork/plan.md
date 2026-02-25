# Implementation Plan: Documentation Site (US5)

**Branch**: `001-solr-benchmark-fork` | **Date**: 2026-02-25 | **Spec**: `specs/001-solr-benchmark-fork/spec.md`
**Input**: Feature specification User Story 5 — Self-Contained Documentation Site (FR-035–FR-041)

## Summary

Build a self-contained Jekyll documentation site in `docs/` using the `just-the-docs` theme.
Content is migrated from the OpenSearch Benchmark `_benchmark/` documentation section and
fully adapted for Apache Solr Benchmark: Solr-native terminology throughout, OpenSearch-only
sections removed, new Solr workload format and converter-tool sections added, ASF licensing
and attribution page included. The site is deployed to GitHub Pages via GitHub Actions on
every push to `main`.

## Technical Context

**Language/Version**: Ruby 3.3 (Jekyll runtime); Python 3.10+ (source tool — unchanged)
**Primary Dependencies**: Jekyll 4.4.1, just-the-docs 0.12.0 gem
**Storage**: Static files in `docs/` — no database
**Testing**: Manual `bundle exec jekyll build --strict` + broken-link check; no Python unit tests
**Target Platform**: GitHub Pages (`https://janhoy.github.io/solr-benchmark/`)
**Project Type**: Static documentation site (Jekyll)
**Performance Goals**: Site builds in < 60s; page load < 2s on standard connection
**Constraints**: Must pass `jekyll build` with zero warnings/errors; no external CDN deps
**Scale/Scope**: ~35 Markdown pages; 6 navigation sections; 1 GitHub Actions workflow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Principle | Status |
|------|-----------|--------|
| All new doc files carry ASF copyright in footer include | III. Source File License Headers | ✅ PASS — enforced by `_includes/footer_custom.html` |
| No OpenSearch trademarks in content outside `about.md` credits page | VIII. Branding + Trademark Rules | ✅ PASS — OSB references confined to `about.md` |
| No new runtime Python dependency introduced | V. Solr-Native Scope | ✅ PASS — docs are static Jekyll only |
| New files placed in `docs/` and `.github/workflows/` only | IV. Architecture Fidelity | ✅ PASS |
| No Python unit test suite changes required | VII. Code Quality & Testing | ✅ PASS — no Python code modified |
| Canonical Solr terminology used throughout (collection, configset, etc.) | VI. Terminology Consistency | ✅ PASS — enforced by content review task |
| No `@author` tags | VII. Code Quality | ✅ PASS — not applicable to Markdown |
| Apache 2.0 license; NOTICE attribution chain preserved in `about.md` | I. ASF Compliance + II. Attribution | ✅ PASS — dedicated credits page |

**Gate result**: All PASS → proceed.

## Project Structure

### Specification Artifacts (this feature)

```text
specs/001-solr-benchmark-fork/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output (content inventory + nav structure)
├── quickstart.md        ← Phase 1 output (local dev instructions)
└── tasks.md             ← Phase 2 output (/speckit.tasks — not created here)
```

### Repository Files Added/Changed

```text
docs/                              ← Jekyll site root (NEW)
├── Gemfile
├── Gemfile.lock
├── _config.yml
├── index.md                       ← Home / landing page
├── about.md                       ← License, credits, trademark notices
├── quickstart.md
├── glossary.md
├── faq.md
├── _includes/
│   └── footer_custom.html         ← ASF copyright + attribution footer
├── assets/
│   └── images/
│       └── logo.png               ← project logo (placeholder)
├── user-guide/
│   ├── index.md
│   ├── concepts.md
│   ├── install-and-configure/
│   │   ├── index.md
│   │   ├── installing.md
│   │   └── configuring.md
│   ├── understanding-workloads/
│   │   ├── index.md
│   │   ├── anatomy-of-a-workload.md
│   │   └── common-operations.md
│   ├── working-with-workloads/
│   │   ├── index.md
│   │   ├── running-workloads.md
│   │   ├── creating-custom-workloads.md
│   │   └── finetune-workloads.md
│   └── understanding-results/
│       ├── index.md
│       ├── summary-reports.md
│       └── telemetry.md
├── reference/
│   ├── index.md
│   ├── workloads/
│   │   ├── index.md
│   │   ├── collections.md         ← NEW (replaces OSB indices.md)
│   │   ├── corpora.md
│   │   ├── operations.md          ← Solr-native ops only
│   │   └── test-procedures.md
│   ├── commands/
│   │   ├── index.md
│   │   ├── run.md
│   │   ├── list.md
│   │   ├── info.md
│   │   ├── compare.md
│   │   └── command-flags.md
│   ├── telemetry.md               ← Solr telemetry devices
│   └── summary-report.md          ← JSON/CSV output format
├── cluster-config/                ← NEW section
│   ├── index.md
│   └── available-configs.md
└── converter/                     ← NEW section
    ├── index.md
    ├── usage.md
    └── what-converts.md

.github/
└── workflows/
    └── docs.yml                   ← NEW GitHub Actions deploy workflow
```

**Structure Decision**: Single static Jekyll site in `docs/` at repository root.
No backend, no API contracts. 6 top-level sections mirror the adapted OSB navigation.
GitHub Actions handles build and GitHub Pages deployment.

## Complexity Tracking

> No constitution violations — no justification required.

---

## Phase 0: Research Findings Summary

Full details in `research.md`. Key resolved decisions:

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| Jekyll theme | `just-the-docs` 0.12.0 | Sidebar nav, search, same family as OSB docs |
| Deployment | GitHub Pages via Actions | Zero-infra, automatic, standard for OSS |
| Build method | `bundle exec jekyll build` (not `jekyll-build-pages` action) | Works with gem-based theme; `baseurl` injected by `configure-pages` |
| OSB pages to include | ~35 of 55 | Exclude synthetic-data-gen, generate-data cmd, vector-search workload, contributing-workloads, migration-assistance, redline-test |
| New pages | collections.md, converter/ (3), cluster-config/ (2), about.md | No OSB equivalent |
| Copyright approach | ASF footer include + dedicated `about.md` | Constitution Principles I–III |

---

## Phase 1: Design Details

### Navigation Hierarchy

```text
Home                                   nav_order: 1
Quickstart                             nav_order: 2
User Guide                             nav_order: 5
  Concepts                               nav_order: 3
  Install and Configure                  nav_order: 5
    Installing                             nav_order: 5
    Configuring                            nav_order: 7
  Understanding Workloads                nav_order: 10
    Anatomy of a Workload                  nav_order: 15
    Common Operations                      nav_order: 16
  Working with Workloads                 nav_order: 15
    Running a Workload                     nav_order: 9
    Creating Custom Workloads              nav_order: 10
    Fine-tuning Workloads                  nav_order: 12
  Understanding Results                  nav_order: 20
    Summary Reports                        nav_order: 22
    Telemetry                              nav_order: 30
Reference                              nav_order: 25
  Workload Reference                     nav_order: 60
    collections                            nav_order: 65
    corpora                                nav_order: 70
    operations                             nav_order: 100
    test_procedures                        nav_order: 110
  Command Reference                      nav_order: 50
    run                                    nav_order: 90
    list                                   nav_order: 80
    info                                   nav_order: 70
    compare                                nav_order: 20
    Command flags                          nav_order: 150
  Telemetry devices                      nav_order: 45
  Summary report                         nav_order: 40
Cluster Config                         nav_order: 27
  Overview                               nav_order: 1
  Available Configs                      nav_order: 2
Converter Tool                         nav_order: 28
  Overview                               nav_order: 1
  Usage                                  nav_order: 2
  What Gets Converted                    nav_order: 3
Glossary                               nav_order: 100
FAQ                                    nav_order: 101
About / Credits                        nav_order: 102
```

### `_config.yml`

```yaml
title: Apache Solr Benchmark
description: >-
  A performance benchmarking tool for Apache Solr clusters, forked from
  OpenSearch Benchmark.
theme: just-the-docs
url: https://janhoy.github.io
# baseurl injected automatically by actions/configure-pages

aux_links:
  "GitHub": https://github.com/janhoy/solr-benchmark
  "Apache Solr": https://solr.apache.org

search_enabled: true

callouts:
  note:
    title: Note
    color: blue
  warning:
    title: Warning
    color: yellow
  important:
    title: Important
    color: red
```

### `Gemfile`

```ruby
source 'https://rubygems.org'
gem "jekyll", "~> 4.4.1"
gem "just-the-docs", "0.12.0"
```

### GitHub Actions Workflow (`.github/workflows/docs.yml`)

```yaml
name: Deploy docs to GitHub Pages
on:
  push:
    branches: ["main"]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: "pages"
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: docs
    steps:
      - uses: actions/checkout@v4
      - uses: ruby/setup-ruby@v1
        with:
          ruby-version: '3.3'
          bundler-cache: true
          cache-version: 0
          working-directory: docs
      - uses: actions/configure-pages@v5
        id: pages
      - name: Build
        run: bundle exec jekyll build --baseurl "${{ steps.pages.outputs.base_path }}"
        env:
          JEKYLL_ENV: production
      - uses: actions/upload-pages-artifact@v4
        with:
          path: docs/_site
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/deploy-pages@v4
        id: deployment
```

### Footer Include (`docs/_includes/footer_custom.html`)

```html
<p>Copyright &copy; 2024 The Apache Software Foundation. Licensed under the
<a href="https://www.apache.org/licenses/LICENSE-2.0">Apache License, Version 2.0</a>.
Apache, Apache Solr, and the Apache feather logo are trademarks of
The Apache Software Foundation. See <a href="{{ '/about' | relative_url }}">About</a>
for full attribution.</p>
```

### `about.md` Structure

1. **License** — Apache 2.0 with link to full text and the NOTICE file
2. **Attribution** — "Apache Solr Benchmark is derived from OpenSearch Benchmark
   (Copyright 2022 OpenSearch Contributors, licensed under Apache 2.0), which in turn
   derives from Elasticsearch Rally (Copyright Elasticsearch bv)."
3. **Trademarks** — "Apache Solr is a trademark of The Apache Software Foundation.
   OpenSearch is a registered trademark of Amazon Web Services, Inc. or its affiliates."
4. **Links** — apache.org, solr.apache.org, opensearch.org

### Content Adaptation Rules (applied to every migrated page)

| Rule | Action |
|------|--------|
| "OpenSearch Benchmark" in body text | Replace with "Apache Solr Benchmark" |
| "index" (as Solr collection) | Replace with "collection" |
| "indices" | Replace with "collections" |
| "OpenSearch cluster" | Replace with "Apache Solr cluster" |
| Links to opensearch.org documentation | Remove or replace with Solr equivalent |
| `create-index` / `delete-index` operations | Replace with `create-collection` / `delete-collection` |
| "aggregations" | Replace with "facets" |
| Workload examples using `indices` key | Update to `collections` key |
| OSB workload repository URL | Replace with `https://github.com/janhoy/solr-benchmark-workloads` |
| "benchmark.ini" default URL | Update to `https://github.com/janhoy/solr-benchmark-workloads` |
