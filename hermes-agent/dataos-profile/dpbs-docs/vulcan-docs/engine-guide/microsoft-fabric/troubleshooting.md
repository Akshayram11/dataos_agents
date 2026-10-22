---
description: Diagnose Fabric connection, warehouse, materialization, and endpoint failures.
---

# Troubleshooting

Start here when a Vulcan Data Product on Fabric Warehouse fails to plan, deploy, or run. Identify the symptom, run health checks, then recover safely.

## Failure modes

Match the observed symptom to its likely cause and recommended fix.

| Symptom                                                                    | Likely cause                                                                | Fix                                                                                                          |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Authentication failed on connect                                           | Client secret expired, or `tenant_id`/`workspace_id` mismatched             | Rotate the secret; verify tenant and workspace UUIDs.                                                        |
| Authentication failed after a warehouse drop                               | Connection string still points at a `Database=` value that no longer exists | Close and reopen the connection against a valid warehouse.                                                   |
| `ItemDisplayNameNotAvailableYet`                                           | Warehouse recreated immediately after being dropped                         | Wait for cleanup to finish; the adapter retries automatically, but scripted flows should add a delay.        |
| Column type change appears slow / rewrites the whole table                 | Fabric has no direct `ALTER COLUMN` type change                             | Expected: the adapter performs a full column rewrite (add, cast, drop, rename). Size the change accordingly. |
| `CREATE INDEX` fails or is a no-op                                         | Fabric Warehouse does not support user indexes                              | Remove index DDL from `post_statements`; rely on query shape and pre-aggregation instead.                    |
| Incremental overwrite left the table in a partial state after a failed run | No explicit transaction wraps DELETE\_INSERT                                | Re-run the affected window; avoid overlapping schedules with `concurrencyPolicy: Forbid`.                    |
| `mssql_merge_exists` throws on `EXCEPT`                                    | Unsupported column type in the merge comparison                             | Disable the optimization for that table.                                                                     |
| `vulcan plan` runs DDL                                                     | Lifecycle DDL not guarded                                                   | Wrap in `@IF(@runtime_stage = 'evaluating', ...)`.                                                           |
| Endpoint OOM on large result                                               | API memory too low                                                          | Raise API memory and limit result size.                                                                      |
| Local Docker stack expected but unavailable                                | Fabric has no local/self-hosted equivalent                                  | Develop against a dedicated dev-tier Fabric workspace instead.                                               |

## Health-check queries

Run these queries to confirm the current warehouse, service principal, and available tables.

```sql
SELECT DB_NAME() AS current_warehouse, SUSER_SNAME() AS current_principal;

SELECT s.name AS schema_name, t.name AS table_name
FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
ORDER BY s.name, t.name;
```

## Recovery procedures

Use the matching procedure to restore the workload without unnecessary rework.

| Situation                                    | Procedure                                                                                                                                                                                          |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Incremental run failed mid-window            | Re-run; time-range and partition incrementals reprocess the affected window via `DELETE` + `INSERT`.                                                                                               |
| Warehouse creation stuck in progress         | Check the Fabric portal for the operation status; the adapter's polling has a bounded number of retries, after which it surfaces an error. Retry `vulcan apply` once the warehouse shows as ready. |
| Table dropped manually                       | `vulcan plan` detects and recreates; use a rebuild command if needed.                                                                                                                              |
| Column-type migration failed partway         | Inspect the table for a leftover temp column from the rewrite workaround; drop it manually and re-run the migration.                                                                               |
| Credentials leaked                           | Rotate the service principal's client secret in Entra ID; update `.env` / DataOS instance secret.                                                                                                  |
| Concurrent runs conflicted on the same table | Set `concurrencyPolicy: Forbid`; stagger heavy incremental models.                                                                                                                                 |

### Next step

Return to [.](./ "mention") to review operating limits and the production checklist.
