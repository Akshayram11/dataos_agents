---
description: Diagnose Databricks connection, warehouse, and state-store failures.
---

# Troubleshooting

Start here when a Vulcan Data Product on Databricks fails to plan, deploy, or run. Identify the symptom, validate the warehouse, catalog, and state store, then recover safely.

### Failure modes

Match the observed symptom to its likely cause and corrective action.

| Symptom                                               | Likely cause                                          | Fix                                                                     |
| ----------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------- |
| `NO_SUCH_CATALOG_EXCEPTION`                           | Catalog missing or wrong name                         | Create the UC catalog; fix `DATABRICKS_CATALOG` / `connection.catalog`. |
| `connection refused` to Postgres statestore           | Infra not running or wrong host/port                  | Start Postgres; use `host.docker.internal:5432` from inside Docker.     |
| Auth / 403 on warehouse                               | Expired PAT or wrong workspace URL                    | New PAT; ensure `server_hostname` matches the PAT's workspace.          |
| `Table samples.tpch.customer not found`               | Missing UC grant or not declared external             | Grant `SELECT` on `samples.tpch`; add to `external_models.yaml`.        |
| Plan succeeds but Catalog Explorer shows empty schema | Different SQL warehouse used in UI versus `http_path` | Use the same warehouse in the SQL editor and `config.yaml`.             |
| Semantic `column not found`                           | Casing mismatch                                       | Use UPPERCASE identifiers in semantic models.                           |
| `Depot not resolvable` on DataOS                      | Depot name mismatch                                   | Match `dataos://<depot-name>?purpose=rw` to the depot `name`.           |
| Duplicate apply appears skipped                       | Postgres state believes the model is current          | Create a new `state_schema`, run `vulcan migrate`, re-apply (dev only). |
| `http_path invalid` / `warehouse not found`           | Warehouse stopped or deleted                          | Recreate; update `http_path`.                                           |
| `vulcan plan` runs DDL                                | Lifecycle DDL not guarded                             | Wrap in `@IF(@runtime_stage = 'evaluating', …)`.                        |
| Incremental reprocesses all history                   | Missing/wrong `time_column`                           | Verify `kind INCREMENTAL_BY_TIME_RANGE (time_column <col>)`.            |
| Endpoint OOM on large result                          | `api.memory.limit` below 1.5 GiB                      | Raise to 3 GiB.                                                         |
| First query after idle 2 to 10 seconds slower         | Cold start after auto-stop                            | Expected; document in the SLO or pin a warming query.                   |

A depot address identifies the Databricks connection. Its purpose controls access: use `rw` for workflows, `scan` for metadata scanning, and `query` for consumer reads.

### Health-check queries

Run these queries on the configured SQL warehouse to verify access and metadata.

```sql
SELECT current_user() AS user, current_catalog() AS catalog, current_schema() AS schema;
SHOW SCHEMAS IN <your_catalog>;
SELECT table_catalog, table_schema, table_name, table_type
FROM   <your_catalog>.information_schema.tables
WHERE  table_schema NOT LIKE 'information_schema'
ORDER  BY table_schema, table_name
LIMIT  50;
```

### Recovery procedures

Use these procedures to safely resume work after common operational failures.

| Situation                               | Procedure                                                                              |
| --------------------------------------- | -------------------------------------------------------------------------------------- |
| Incremental run failed mid-window       | Re-run; `INCREMENTAL_BY_TIME_RANGE` re-processes the window, so re-runs are safe.      |
| Table dropped manually                  | `vulcan plan` detects and recreates; or `vulcan run --rebuild <model>`.                |
| Wrong UC catalog applied                | Fix `DATABRICKS_CATALOG`, create a new `state_schema`, run `vulcan migrate`, re-apply. |
| PAT leaked or expired                   | Revoke, issue a new token, update `.env` / DataOS instance secret.                     |
| Workflow halted because `endOn` expired | Update `endOn` and re-apply.                                                           |

### Next step

Use the [#full-implementation-example](./#full-implementation-example "mention") to validate the complete setup.
