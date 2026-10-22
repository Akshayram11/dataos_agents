---
description: Diagnose SQL Server connection, permissions, model, and runtime failures.
---

# Troubleshooting

Start here when a Vulcan Data Product on SQL Server fails to plan, deploy, or run. Identify the symptom, run health checks, then recover safely.

## Failure modes

Match the observed symptom to its likely cause and recommended fix.

| Symptom                                   | Likely cause                                  | Fix                                                             |
| ----------------------------------------- | --------------------------------------------- | --------------------------------------------------------------- |
| `database "warehouse" does not exist`     | Target database missing or wrong name         | Create the database and fix `connection.database`.              |
| Login failed for user                     | Wrong password or no database user mapping    | Fix the password and confirm `CREATE USER ... FOR LOGIN ...`.   |
| String or binary data would be truncated  | Bare `VARCHAR` defaulted to length 1          | Declare explicit column lengths.                                |
| `relation raw.raw_orders does not exist`  | Missing table, grant, or external declaration | Grant `SELECT` and add `external_models.yaml`.                  |
| Plan succeeds but SSMS shows empty schema | Different login or database                   | Use the same database and a `db_datareader` login.              |
| Semantic column does not exist            | Bracket or quoting mismatch                   | Quote identifiers consistently.                                 |
| Depot not resolvable on DataOS            | Depot name mismatch                           | Match the configured `dataos://` address to the Depot manifest. |
| `PermissionError: '.logs'`                | Working directory is not writable             | Use `vulcan --log-to-stdout` or make the directory writable.    |
| `vulcan plan` runs DDL                    | Lifecycle DDL is unguarded                    | Wrap it in `@IF(@runtime_stage = 'evaluating', ...)`.           |
| Incremental reprocesses history           | Incorrect `time_column` or `unique_key`       | Align model configuration with actual columns.                  |
| Endpoint OOM on large result              | API memory is too low                         | Raise API memory and limit result size.                         |
| Too many connections                      | Workers, replicas, and BI exceed capacity     | Lower concurrency or replicas, then add a pooler.               |
| `mssql_merge_exists` throws on `EXCEPT`   | Unsupported column type                       | Disable the optimization for that table.                        |
| `pymssql` fails to build                  | Required local headers are absent             | Use the supplied wheel or `driver: pyodbc`.                     |

## Health-check queries

Run these queries to confirm the active database, login, available tables, and active sessions.

```sql
SELECT DB_NAME() AS current_database, SUSER_SNAME() AS current_login;

SELECT s.name AS schema_name, t.name AS table_name
FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
ORDER BY s.name, t.name;

SELECT session_id, status, login_name, host_name
FROM sys.dm_exec_sessions WHERE is_user_process = 1;
```

## Recovery procedures

Use the matching procedure to restore the workload without unnecessary rework.

| Situation                         | Procedure                                                                      |
| --------------------------------- | ------------------------------------------------------------------------------ |
| Incremental run failed mid-window | Re-run. Time-range and partition incrementals reprocess the affected window.   |
| Table dropped manually            | `vulcan plan` detects and recreates it. Use a rebuild command if needed.       |
| Wrong database applied            | Fix the connection, verify with `SELECT DB_NAME()`, then re-run plan or apply. |
| Credentials leaked                | Rotate the password and update `.env` or the DataOS instance secret.           |
| Connection exhaustion             | Lower concurrency or replicas, add a pooler, and investigate blocked sessions. |
| MERGE deadlock between runs       | Set `concurrencyPolicy: Forbid` and stagger heavy MERGE models.                |

### Next step

Return to the [.](./ "mention") to review production readiness and related guides.
