---
description: >-
  Size, schedule, and tune PostgreSQL workloads for reliable production
  operations.
---

# Limits & performance

Set practical resource and concurrency limits before production demand grows. These guardrails protect database stability as workloads, API traffic, and BI usage increase.

## Operational boundaries

### Compute sizing

A 1 to 2 vCPU, 2 to 4 GiB instance is usually enough for dev. For first backfills, temporarily raise `work_mem` / `maintenance_work_mem` and ensure disk headroom. Index the incremental `time_column` / `unique_key` and size IOPS to write volume. For the semantic API and concurrent BI, add a pooler or read replica and watch the connection count.

### Concurrency and API replicas

Start with `concurrent_tasks: 2` for daily incrementals; raise it only if plan/run duration is the bottleneck and the instance has connection and I/O headroom. The API is stateless, but each replica consumes PostgreSQL connections, so pair replica increases with PgBouncer or higher connection capacity. Size `max_connections` for Vulcan workers, API replicas, and BI sessions together.

### Scheduling and latency floor

Schedule after upstream lands, set `timezone: UTC`, set `endOn` 1 to 2 years out, and use `concurrencyPolicy: Forbid` (prevents overlapping windows and connection pile-ups). The latency floor: typically no cold start on provisioned PostgreSQL (serverless or auto-paused deployments may have wake-up latency); connection establishment is sub-second when warm; queries on unindexed filters pay sequential-scan cost.

## Performance reference

Measure active connections versus `max_connections`, plan/run duration per model, semantic query wall time, rows touched per incremental window, and the sequential-scan versus index-scan ratio (`EXPLAIN`). When concurrency degrades, fix in order: remove cross-join-shaped queries, add missing indexes on hot filter/join columns, add a connection pooler such as PgBouncer, add a read replica for query traffic, then raise instance size last.

Measured results from a 50M-row local run (2026-06-12) against a managed PostgreSQL 15.17 instance show the shape clearly: a point lookup by primary key returns in about 49 ms (index scan), while a 3-way join aggregate over 50.1M orders runs about 35 seconds (sequential scan ×3), and a `COUNT(DISTINCT customer_id)` runs about 28 seconds. `statement_timeout` enforcement is confirmed. A Vulcan-orchestrated full-refresh backfill of the same data (three `FULL` models in parallel: plan, snapshot, CTAS, audits) completed in about 2 minutes 28 seconds wall clock. Reproduce on your own instance before quoting these.

### Next step

When behavior needs investigation, use [troubleshooting.md](troubleshooting.md "mention").
