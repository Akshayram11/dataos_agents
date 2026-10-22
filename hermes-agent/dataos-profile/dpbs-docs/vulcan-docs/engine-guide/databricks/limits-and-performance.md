---
description: >-
  Configure Databricks warehouse sizing, concurrency, cost guardrails, and
  performance baselines for reliable production workloads.
---

# Limits & Performance

Set warehouse and concurrency limits before production demand grows. Use these guardrails to keep Databricks workloads reliable and predictable as demand increases.

## Operational boundaries

### Compute sizing

Match the SQL warehouse to the workload. Use a small warehouse with 10-minute auto-stop for development. Right-size daily incrementals to partition volume. Scale up temporarily for first backfills, then revert. Use a dedicated or higher-tier warehouse for the semantic API.

Always enable auto-stop on development warehouses: **Workspace UI** → **SQL Warehouses** → **Edit** → **Auto Stop**.

### Concurrency and API replicas

Keep `concurrent_tasks` below what the warehouse can admit without queue timeouts; start at 2 for daily incrementals. The API is stateless: add replicas (1 to 2 single team, 3 to 5 multi-team, 5 or more high volume) before raising warehouse concurrency. Keep `api.limit.memory` at 3 GiB.

### Scheduling and latency floor

Schedule after upstream lands, set `timezone: UTC`, set `endOn` 1 to 2 years out, and use `concurrencyPolicy: Forbid`. The latency floor: SQL warehouse cold start after auto-stop adds 2 to 10 seconds (tier dependent); the semantic API adds about 1.5 to 3 seconds.

### Cost guardrails

Databricks bills SQL warehouse DBUs. Enable auto-stop, set a query timeout, tag queries for attribution, and use `VACUUM` to reclaim deleted Delta files.

```sql
SET spark.sql.session.timeoutMs = 3600000;       -- 1 hour, in pre_statements
SET spark.sql.query.tag = 'vulcan:<project>:<model>';
```

## Performance reference

Latency is warehouse-tier and data-volume shaped, so validate on a known dataset before publishing SLOs. Measure warehouse queue time (concurrency saturation), plan/run duration per model, semantic query wall time, rows touched per incremental window (the primary DBU driver), and cold-start overhead. When concurrency degrades, fix in order: remove cross-join-shaped queries, add API replicas, raise warehouse cluster count, split build and query warehouses, then increase warehouse size last.

### Next step

When workload behavior needs investigation, use [troubleshooting-databricks.md](troubleshooting-databricks.md "mention").
