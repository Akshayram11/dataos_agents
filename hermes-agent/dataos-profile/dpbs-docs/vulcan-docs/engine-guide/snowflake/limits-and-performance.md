---
description: >-
  Size Snowflake compute, control concurrency, manage costs, and plan for
  performance.
---

# Limits & Performance

Once your Data Product serves consumers, tune Snowflake for reliable and predictable operation. Use these limits and baselines to size compute, control concurrency, and manage cost as demand grows.

## Operational boundaries

### Compute sizing

Match warehouse size to the workload below rather than defaulting to one size for everything — an oversized warehouse for dev iteration wastes credits, and an undersized one for backfills just takes longer to finish.

| Workload                          | Size                                 | Rationale                                                   |
| --------------------------------- | ------------------------------------ | ----------------------------------------------------------- |
| Dev or single-user plan iteration | X-SMALL or SMALL                     | Plans build only a few models.                              |
| First full backfill               | LARGE or X-LARGE                     | Parallel backfills finish faster and can cost less overall. |
| Daily incremental runs            | MEDIUM                               | Processes only new partitions.                              |
| Semantic API or concurrent BI     | LARGE; raise `MAX_CONCURRENCY_LEVEL` | Each API query reaches Snowflake directly.                  |
| Snowpark or Python models         | One size above equivalent SQL        | The warehouse coordinates the Snowpark pool.                |

Set `AUTO_SUSPEND = 60` and `AUTO_RESUME = TRUE` for bursty Vulcan workloads.

### Concurrency

`MAX_CONCURRENCY_LEVEL` controls queries before queueing. Use 8 for model runs, 12–16 with a live semantic API, and 20 or more for many BI sessions. Keep `concurrent_tasks` at or below `MAX_CONCURRENCY_LEVEL / 3`.

### API replicas

The API is stateless. Use 1–2 replicas for one team, 3–5 for multi-team dashboards, and 5 or more for high volume. Keep `api.limit.memory` at 3 GiB.

### Scheduling

Schedule after upstream data lands. Set `timezone: UTC`, use `concurrencyPolicy: Forbid`, and set `endOn` one to two years ahead. An expired `endOn` silently halts workflows.

### Latency floor

Warehouse cold starts add 1–3 seconds. The semantic API adds 1.5–2 seconds for standard queries and 4–5 seconds for complex queries. Query parsing takes 50–200 milliseconds. Result-cache hits complete in under one second.

### Cost guardrails

Cap spend with a resource monitor. Set query and queued timeouts. Tag queries for attribution. Keep auto-suspend short.

```sql
CREATE RESOURCE MONITOR vulcan_monthly_cap
  WITH CREDIT_QUOTA = 500
       FREQUENCY = MONTHLY
       START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 90 PERCENT DO SUSPEND
    ON 100 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE vulcan_wh SET
  STATEMENT_TIMEOUT_IN_SECONDS = 3600
  STATEMENT_QUEUED_TIMEOUT_IN_SECONDS = 300;

ALTER SESSION SET QUERY_TAG = 'vulcan:<project>:<model>';
```

Use `TRANSIENT` for Bronze or staging tables that you can re-derive.

## Performance reference

These TPC-H SF1000 baselines use a Medium warehouse, 100 queries, 10 users, and five parallel requests. Treat them as planning baselines.

| Metric                    | Value              |
| ------------------------- | ------------------ |
| Standard query completion | 12–15 seconds      |
| Semantic API overhead     | About 1.84 seconds |
| Cross-join-heavy queries  | Up to 5.13 minutes |
| Concurrent success rate   | 82%                |

Cross-joins can run 30 times slower. Fix SQL shape first. Then add API replicas, raise `MAX_CONCURRENCY_LEVEL`, and size up the warehouse.

### Next step

If a workload still misbehaves after applying these limits, continue to [troubleshooting.md](troubleshooting.md "mention") to diagnose and recover from failures.
