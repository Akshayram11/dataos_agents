---
description: >-
  Diagnose common Snowflake and Vulcan failures, then recover production
  workloads.
---

# Troubleshooting

Start here when a Vulcan Data Product on Snowflake fails to plan, deploy, or run. Identify the symptom, run health checks, then recover safely.

## Failure modes

Match the observed symptom to its likely cause and recommended fix.

| Symptom                                   | Likely cause                                            | Fix                                                                      |
| ----------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------ |
| JWT token invalid on first run            | Public key is missing or the PEM and passphrase differ. | Run `ALTER USER … SET RSA_PUBLIC_KEY`; then verify the passphrase.       |
| Account identifier not found              | Account format is incorrect.                            | Use `<org>-<account>` from the console URL.                              |
| `Object 'COL' does not exist`             | A semantic model uses lowercase identifiers.            | Use UPPERCASE identifiers.                                               |
| `Table not found: SNOWFLAKE_SAMPLE_DATA…` | Cross-database source is not declared.                  | Add a triple-quoted identifier to `external_models.yaml`.                |
| Insufficient schema privileges            | Role lacks `CREATE SCHEMA` or `CREATE TABLE`.           | Apply the service-role grants.                                           |
| `IMPORTED PRIVILEGES` required            | The sample-data share is not mounted.                   | Grant imported privileges on `SNOWFLAKE_SAMPLE_DATA`.                    |
| `Depot not resolvable`                    | Depot name does not match the resource.                 | Match the `dataos://` name to the depot manifest.                        |
| `vulcan plan` runs DDL                    | Lifecycle DDL is unguarded.                             | Wrap the statement in `@IF(@runtime_stage = 'evaluating', …)`.           |
| `Coercion failed` in a macro              | Macro parameter is annotated `: str`.                   | Remove the annotation and render with `.sql(dialect=evaluator.dialect)`. |
| `NameError: 'col' is not defined`         | Snowpark functions are imported at module scope.        | Import them inside `execute()`.                                          |
| Endpoint OOM                              | API memory is below 1.5 GiB.                            | Raise it to 3 GiB.                                                       |

## Health-check queries

Run these queries to inspect recent Vulcan activity and warehouse queueing.

```sql
SELECT query_id, query_text, execution_status,
       total_elapsed_time / 1000 AS seconds, warehouse_name
FROM snowflake.account_usage.query_history
WHERE query_tag LIKE 'vulcan:%'
  AND start_time > DATEADD(hour, -2, CURRENT_TIMESTAMP())
ORDER BY start_time DESC
LIMIT 50;

SELECT warehouse_name, COUNT(*) AS queries,
       AVG(queued_provisioning_time + queued_overload_time) / 1000 AS avg_queued_s
FROM snowflake.account_usage.query_history
WHERE start_time > DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP BY warehouse_name
ORDER BY avg_queued_s DESC;
```

## Recovery procedures

Use the matching procedure to restore the workload without unnecessary rework.

| Situation                          | Procedure                                                                |
| ---------------------------------- | ------------------------------------------------------------------------ |
| Incremental run failed mid-way     | Re-run the workflow. Time-range models safely refresh the failed window. |
| State drifted                      | Run `vulcan plan`, or use `vulcan run --rebuild <model>`.                |
| Roll back a plan version           | Run `vulcan rollback <plan_id>`. This consumes credits.                  |
| Workflow stopped after `endOn`     | Update `endOn` and re-apply the resource.                                |
| Resource monitor suspended compute | Investigate spend, adjust `CREDIT_QUOTA`, or resume the warehouse.       |
