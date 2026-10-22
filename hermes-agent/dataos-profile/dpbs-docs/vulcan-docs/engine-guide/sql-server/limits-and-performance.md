---
description: >-
  Size, schedule, and tune SQL Server workloads for reliable production
  operations.
---

# Limits & performance

## Operational boundaries

### Compute sizing

A 2 to 4 vCPU, 4 to 8 GiB instance usually supports development. For first backfills, raise `tempdb` size and disk headroom. `SELECT * INTO` and bulk `MERGE` spill through `tempdb`.

Index the incremental `time_column` or `unique_key`. Size IOPS to write volume. For concurrent BI and the semantic API, watch connection count. Consider a connection pool.

### Concurrency

Start daily incrementals with `concurrent_tasks: 2`. Increase only when runtime is the bottleneck and the instance has connection and I/O headroom.

Each API replica consumes SQL Server connections. Pair replica increases with a pooler or more connection capacity.

### Scheduling and latency floor

Schedule after upstream data lands. Set `timezone: UTC`. Set `endOn` one to two years out. Use `concurrencyPolicy: Forbid` to prevent overlapping windows, connection pile-ups, and concurrent MERGE writers.

A provisioned instance has no cold start. Warm connections are typically sub-second. Unindexed filters scan tables. The first `SELECT * INTO` for a large FULL model is slower than later `TRUNCATE` plus `INSERT` runs.

## Performance reference

Measure active connections, model plan and run duration, semantic-query wall time, rows per incremental window, and index-seek versus table-scan ratio. Use `SET STATISTICS IO ON` and execution plans.

When concurrency degrades, act in this order:

1. Remove cross-join-shaped queries.
2. Add indexes on hot filter and join columns.
3. Add a connection pooler.
4. Size up the instance.
5. Investigate `tempdb` contention on bulk loads and MERGE.

Reproduce measurements on your own instance before quoting them externally.

### Next step

Use [troubleshooting.md](troubleshooting.md "mention") to diagnose failures and test recovery procedures.
