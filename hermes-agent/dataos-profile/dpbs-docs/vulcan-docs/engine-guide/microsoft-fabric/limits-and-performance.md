---
description: >-
  Set Fabric capacity, concurrency, and workload guardrails for reliable
  operations.
---

# Limits & performance

## Operational boundaries

### Compute sizing

Fabric Warehouse compute is tied to the workspace's assigned Fabric capacity (an F-SKU or trial capacity), not a per-query warehouse you resize yourself the way you would on Snowflake. Size the assigned capacity for your workload's concurrency and data volume at the Fabric-admin level; Vulcan has no lever to resize Fabric capacity from the project config.

### Concurrency

Start with `concurrent_tasks: 2` for daily incrementals. Because there are no explicit transactions and the overwrite strategy is DELETE\_INSERT rather than MERGE for time-range/partition kinds, avoid overlapping runs against the same table. A second run's `DELETE` can race a first run's `INSERT` with no transactional isolation to fall back on. Use `concurrencyPolicy: Forbid` for every scheduled workflow on this engine.

### Scheduling and latency floor

Schedule after upstream lands, set `timezone: UTC`, set `endOn` 1 to 2 years out, and use `concurrencyPolicy: Forbid`. The latency floor includes: warehouse SQL endpoint connection setup (Entra token acquisition plus ODBC connect), no index-assisted point lookups (every filtered query is closer to a scan than it would be on an indexed MSSQL table), and asynchronous warehouse creation/drop latency (seconds to tens of seconds) if your workflow provisions warehouses dynamically.

## Performance reference

Because there is no user-tunable indexing, sizing conversations for Fabric center on query shape and capacity tier rather than index design. Track plan/run duration per model, semantic query wall time, and rows touched per incremental window. When concurrency or latency degrades, fix in order: remove cross-join-shaped queries, pre-aggregate high-cardinality `COUNT(DISTINCT ...)` measures into a mart, stagger schedules so DELETE\_INSERT-based incrementals never overlap on the same table, then escalate the Fabric capacity tier as a platform-level change. Reproduce measurements against your own workspace capacity before quoting them externally. Fabric capacity tiers behave differently from a dedicated SQL Server instance under load.

### Next step

Use [troubleshooting.md](troubleshooting.md "mention") to diagnose connection, deployment, and runtime failures.
