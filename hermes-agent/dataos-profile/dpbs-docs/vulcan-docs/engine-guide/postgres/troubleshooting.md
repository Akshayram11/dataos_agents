---
description: Diagnose PostgreSQL connection, permissions, model, and runtime failures.
---

# Troubleshooting

Start here when a Vulcan Data Product on PostgreSQL fails to plan, deploy, or run. Identify the symptom, validate the environment, then recover safely.

### Failure modes

Match the observed symptom to its likely cause and corrective action.

| Symptom                                     | Likely cause                                  | Fix                                                                    |
| ------------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------- |
| `database "warehouse" does not exist`       | Target database missing or wrong name         | Create the database; fix `WAREHOUSE_DATABASE` / `connection.database`. |
| PostgreSQL connection refused               | Infra not running or wrong host/port          | Start PostgreSQL; use `host.docker.internal` from containers.          |
| Password authentication failed              | Wrong password or role                        | Fix the password; confirm the role exists and can log in.              |
| `relation raw.raw_orders does not exist`    | Missing table, grant, or external declaration | Grant `SELECT`; add to `external_models.yaml`.                         |
| Plan succeeds but `psql` shows empty schema | Different role/database used for debugging    | Use the same database and a role with `USAGE`.                         |
| Semantic `column does not exist`            | Casing mismatch                               | Use lowercase identifiers or quote consistently.                       |
| `Depot not resolvable` on DataOS            | Depot name mismatch                           | Match `dataos://<depot-name>?purpose=rw` to the depot manifest.        |
| `PermissionError: '.logs'`                  | CWD not writable                              | Run `vulcan --log-to-stdout ...` or make the directory writable.       |
| `unacceptable schema name "pg_..."`         | `pg_` prefix reserved                         | Rename the schema.                                                     |
| `vulcan plan` runs DDL                      | Lifecycle DDL not guarded                     | Wrap in `@IF(@runtime_stage = 'evaluating', ...)`.                     |
| Incremental reprocesses history             | Missing/wrong `time_column` or `unique_key`   | Verify the model kind config matches actual columns.                   |
| Endpoint OOM on large result                | API memory too low                            | Raise API memory and limit result size.                                |
| Too many connections for role               | Workers plus replicas plus BI exceed budget   | Lower concurrency/replicas; add PgBouncer.                             |
| `psycopg2` fails to build from source       | Local build lacks `pg_config` / libpq headers | Use the wheel/binary supplied by the Vulcan distribution.              |

### Health-check queries

Run these queries to verify the active connection, available objects, and session load.

```sql
SELECT current_user, current_database(), current_schema();
\dn

SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name
LIMIT 50;

SELECT count(*) AS conns, state
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state;
```

### Recovery procedures

Use these procedures to safely resume work after common operational failures.

| Situation                         | Procedure                                                                                 |
| --------------------------------- | ----------------------------------------------------------------------------------------- |
| Incremental run failed mid-window | Re-run; time-range incrementals reprocess the affected window.                            |
| Table dropped manually            | `vulcan plan` detects and recreates; use a rebuild command if needed.                     |
| Wrong database applied            | Fix `WAREHOUSE_DATABASE`, verify with `SELECT current_database()`, re-run plan/apply.     |
| Credentials leaked                | Rotate the password; update `.env` / DataOS instance secret.                              |
| Connection exhaustion             | Lower concurrency/replicas, restart the pooler, investigate idle-in-transaction sessions. |

### Next step

Use the [#full-implementation-example](./#full-implementation-example "mention") to validate your gateway, grants, models, and deployment end to end.

For PostgreSQL-specific capabilities, explore [recipes](recipes/ "mention") for full-text search and row-level security patterns.
