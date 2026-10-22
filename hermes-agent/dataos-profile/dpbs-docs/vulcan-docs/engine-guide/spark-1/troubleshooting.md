---
description: Diagnose Spark, Iceberg, dependency, deployment, and runtime failures.
---

# Troubleshooting

Start here when a Vulcan Data Product on Spark fails to plan, deploy, or run. Identify the symptom, run health checks, then recover safely.

## Failure modes and troubleshooting

Match the observed symptom below before changing configuration. Apply the fix in a non-production environment first when possible.

| Symptom                                          | Likely cause                                                | Fix                                                                                 |
| ------------------------------------------------ | ----------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Unique-key model "does nothing"                  | Iceberg format missing                                      | Add `physical_properties(format = 'iceberg')`.                                      |
| `NoClassDefFoundError: DataLakeStorageException` | ABFSS FileIO classes missing from classpath                 | Add the `iceberg-azure-bundle` JAR under `dependencies/java/`.                      |
| Dependency not available at runtime              | JAR/wheel not shipped or not imported                       | Place under `dependencies/java/` or `dependencies/python/`; redeploy.               |
| `CommitFailedException` (Iceberg)                | Concurrent writers to the same table                        | Raise commit retry; stagger schedules; `concurrencyPolicy: Forbid`.                 |
| Delete tombstones appear as rows after MERGE     | Missing-key DELETE falls through to implicit insert         | Filter tombstones before MERGE or handle downstream.                                |
| Many tiny output files slow queries              | Shuffle partitions too high or AQE coalescing off           | Keep AQE coalescing enabled; tune `shuffle.partitions`.                             |
| One task runs far longer than others             | Skewed join key                                             | Enable `spark.sql.adaptive.skewJoin.enabled`; review join strategy.                 |
| Executor OOM                                     | Partitions too large or memory too low                      | Lower `maxPartitionBytes` or raise executor memory.                                 |
| Driver OOM                                       | Python model collects a large DataFrame to the driver       | Return Spark DataFrames; avoid `toPandas()` on large outputs.                       |
| API query times out                              | Semantic query launches an expensive job                    | Pre-aggregate, add segments, constrain query shape.                                 |
| DataOS fails to resolve catalog (works locally)  | Depot missing or misnamed in `spec.depots[]`                | Verify `spec.depots[]` and the fully qualified catalog prefix.                      |
| Production `vulcan migrate` fails                | Platform-managed state store not provisioned or unreachable | Escalate to the SRE/platform team, then re-run `vulcan migrate`.                    |
| `Table not found` for external source            | External model not declared                                 | Add to `external_models.yaml` with the fully qualified lakehouse name.              |
| Time-range incremental reprocesses all history   | Missing or wrong `time_column`; interval macros not used    | Verify `kind INCREMENTAL_BY_TIME_RANGE (time_column <col>)` and the source filter.  |
| Straggler stage on a large join                  | Data skew on the join key                                   | Enable AQE skew join; review partition distribution; pre-aggregate the skewed side. |
| First job after an idle period is slow           | Spark startup plus dependency load                          | Expected cold-start cost; document in the SLO or pre-warm the cluster.              |

### Logs and where to look

Collect logs from the component that failed. Include the Spark application ID and affected model name when escalating.

| Symptom                                        | Where                                  | How                                                                                                      |
| ---------------------------------------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Local Docker startup issue                     | Docker compose services                | `docker compose -f docker/docker-compose.local-python.yml logs <service>` (or the python-in-docker file) |
| Spark scheduler / catalog / auth failure       | DataOS driver container                | `dataos-ctl resource log -t Vulcan -n <name> --container-group <name>-run-execute -c main`               |
| Executor OOM, shuffle-fetch failure, UDF error | Spark executor logs                    | Spark UI → application → executors                                                                       |
| API / semantic query issue                     | API track containers                   | `dataos-ctl resource log ... --container-group <name>-api`                                               |
| Iceberg commit conflict                        | Driver logs + Spark SQL execution logs | Search for `CommitFailedException` and the target table name                                             |

### Recovery procedures

Recover the failed workload only after confirming its cause. Check the target table and its Iceberg snapshots before replaying writes.

| Situation                                    | Procedure                                                                                |
| -------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Incremental time-range run failed mid-window | Re-run the affected window; partition overwrite is safe to replay                        |
| Unique-key MERGE failed before commit        | Re-run after checking target table snapshots and commit conflict logs                    |
| Unique-key MERGE committed bad data          | Restore with Iceberg snapshot rollback, coordinated with the platform SRE team           |
| Dependency artifact missing                  | Add the JAR/wheel under `dependencies/`, redeploy, run `vulcan plan` before `vulcan run` |
| Compute exhausted                            | Reduce concurrency, tune shuffle/read splits, then scale executor instances              |
| Schedule overlap caused an Iceberg conflict  | Stop the overlapping run; set `concurrencyPolicy: Forbid`; stagger heavy writers         |
| Workflow halted because `endOn` expired      | Update the Vulcan resource with a new `endOn` and re-apply                               |

## Next steps

Use [deployment-recipes.md](deployment-recipes.md "mention") to apply a proven sizing profile after recovery.
