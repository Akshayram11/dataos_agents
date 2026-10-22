---
description: >-
  How Vulcan is put together, how a data product moves from setup to a
  governed asset, and how `vulcan plan` and `vulcan run` decide what to
  execute.
---

# Concepts

Understand how Vulcan is put together before you build with it.

This section covers the ideas that don't belong to any single page: how the pieces fit together, how a data product moves from an idea to a governed asset, and how Vulcan decides what to run.

## Choose a page

* **[Architecture](architecture.md)** - how Vulcan sits above your engine and turns models into a governed data product.
* **[Data product lifecycle](data-product-lifecycle.md)** - the full path from local setup to a production data product.
* **[State management](state-management.md)** - the PostgreSQL state store and object store cache Vulcan runs on, and the Secrets that connect them.
* **[Run and plan](run-and-plan/README.md)** - how `vulcan plan` and `vulcan run` decide what changed and what to execute.
* **[Write-Audit-Publish](write-audit-publish.md)** - how Vulcan writes to an isolated copy, runs blocking assertions, and publishes only after every check passes.
* **[Query result caching](query-result-caching.md)** - when Vulcan reuses a previous query result instead of running the query again.

## Where to go next

Once you understand the concepts, move to [Models](../models/README.md) to start building, or [Configurations](../configurations/README.md) to set up your project.
