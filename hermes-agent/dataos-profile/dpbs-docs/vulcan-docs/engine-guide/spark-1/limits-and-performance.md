---
description: Size Spark workloads, tune execution, and set performance and cost guardrails.
---

# Limits & Performance

Use these limits and baselines to size drivers and executors, control concurrency, and manage cost as demand grows.

## Operational boundaries

### Driver and executor sizing

| Workload                           | Starting shape                                    | Rationale                                                 |
| ---------------------------------- | ------------------------------------------------- | --------------------------------------------------------- |
| Dev / local plan (\~1 GB)          | 1 driver, 1 worker.                               | Validate syntax, catalog, and small data paths            |
| Small production models (\~1 GB)   | Driver 1 core / 2G; Executor 2× 2 cores / 4G.     | Mostly scheduler and catalog overhead                     |
| Medium production models (\~10 GB) | Driver 2 cores / 4G; Executor 3× 2 cores / 4G.    | Enough parallelism for moderate joins                     |
| Large production models (\~100 GB) | Driver 2 cores / 6G; Executor 4× 3 cores / 6G.    | Baseline for shuffle-heavy lakehouse workloads            |
| XL backfill (\~1 TB)               | Driver 4 cores / 8G; Executor 8–16× 4 cores / 8G. | Scale executor instances after tuning shuffle/read splits |

Executor parallelism is roughly `executor.cores × executor.instances`. Add 10 to 15% memory overhead. Fix shuffle partitions and adaptive query execution (AQE) before adding more executors.

### Reliability targets

Reference targets assume the recommended configuration and workload validation in your tenant.

| Signal                                                           | Target                                                                     |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Daily incremental run success rate (stable upstream and compute) | ≥ 99%                                                                      |
| Plan/run driver startup success                                  | ≥ 99% after dependency and catalog validation                              |
| API track availability                                           | Same as DataOS service-level availability for the deployed Vulcan resource |
| Iceberg MERGE conflict recovery                                  | Commit retry configured before concurrent MERGE workloads go live          |
| Executor OOM rate                                                | 0 on representative production windows after sizing validation             |

### Spark tuning

| Setting                                         | Guidance                                                       |
| ----------------------------------------------- | -------------------------------------------------------------- |
| `spark.sql.shuffle.partitions`                  | First lever for shuffle-heavy stages; raise when stages spill. |
| `spark.sql.adaptive.enabled`                    | Keep `true`.                                                   |
| `spark.sql.adaptive.coalescePartitions.enabled` | Keep `true` to reduce tiny output files.                       |
| `spark.sql.adaptive.skewJoin.enabled`           | Enable for skewed joins.                                       |
| `spark.sql.files.maxPartitionBytes`             | Raise for huge scans; lower if executors OOM.                  |
| `spark.serializer`                              | Use `org.apache.spark.serializer.KryoSerializer`.              |
| `spark.sql.catalog.<depot>.commit.retry.*`      | Configure for concurrent MERGE / Iceberg commit conflicts.     |

Tuning order: shuffle partitions, AQE plus coalescing, skew-join handling, `maxPartitionBytes`, executor memory/instances, then Iceberg commit retry.

### API replicas and Kubernetes resources

| Traffic                           | API replicas |
| --------------------------------- | ------------ |
| Single team                       | 1–2          |
| Multi-team / scheduled dashboards | 3–5          |
| Enterprise / high-volume          | 5+           |

The API track is sized separately from the Spark workflow cluster:

```yaml
api:
  replicas: 2
  resource:
    request: { cpu: "200m", memory: "512Mi" }
    limit:   { cpu: "2000m", memory: "2Gi" }
```

Add API replicas for request concurrency and add workflow executors for Spark query execution. These are different bottlenecks.

### Scheduling and latency floor

Schedule after upstream files land, set `timezone: UTC`, use `concurrencyPolicy: Forbid` (prevents overlapping writers and Iceberg commit conflicts), set `endOn` 1 to 2 years out, and stagger MERGE-heavy models. The latency floor is driver and executor startup plus dependency load, Iceberg REST metadata round trips, object-storage listing/read latency, API parsing/planning/serialization, and small-file overhead. If your downstream SLO is sub-second, Spark/Iceberg is the wrong serving path. Pre-aggregate, cache into a serving store, or use a lower-latency engine for that surface.

## Performance reference

Reference sizing tiers for TPC-H-shaped joins on Iceberg over object storage, with AQE enabled. Validate on tenant data before publishing SLOs externally.

| Tier | Approx data | Driver       | Executor           | Total exec cores | `shuffle.partitions` | `maxPartitionBytes` | Expected complex-join time |
| ---- | ----------- | ------------ | ------------------ | ---------------- | -------------------- | ------------------- | -------------------------- |
| S    | \~1 GB      | 1 core / 2G  | 2× 2 cores / 4G    | 4                | 64–100               | 128 MB              | seconds to \~1 min         |
| M    | \~10 GB     | 2 cores / 4G | 3× 2 cores / 4G    | 6                | 200                  | 128 MB              | \~1–3 min                  |
| L    | \~100 GB    | 2 cores / 6G | 4× 3 cores / 6G    | 12               | 200–400              | 128 MB              | \~5–15 min                 |
| XL   | \~1 TB      | 4 cores / 8G | 8–16× 4 cores / 8G | 32–64            | 1000–2000            | 256 MB              | \~30–90 min                |

Track driver startup time, executor allocation time, shuffle read/write size, spill to disk, straggler tasks, output file count, and Iceberg commit duration as the core sizing signals. A simple validation loop: pick the closest tier, run a representative `vulcan plan` + `vulcan run` window, inspect the Spark UI for spill/stragglers/OOM/shuffle size, apply one tuning change, re-run and compare, then record the stable driver/executor/`sparkConf` combination as the workload baseline.

When concurrency degrades, fix in order: prevent overlapping writers, add Iceberg commit retry, stagger heavy schedules, add executor instances, then split across compute pools only after query shape and scheduling are clean.

### Performance ceilings

| Ceiling                                                 | Tune via                                                          |
| ------------------------------------------------------- | ----------------------------------------------------------------- |
| Shuffle-heavy joins spill to disk                       | Increase `shuffle.partitions`, executor memory, and skew handling |
| Object-storage small files dominate planning            | Keep AQE coalescing enabled; compact/rewrite tables when needed   |
| High-cardinality semantic queries run slowly            | Pre-aggregate marts; constrain governed query shapes              |
| Iceberg MERGE commit conflicts under concurrent writers | Stagger writers; raise `commit.retry.*` values                    |
| Executor OOM on wide scans                              | Lower `maxPartitionBytes` or raise executor memory                |
| Low cluster utilization                                 | Reduce executor instances or increase partition parallelism       |

### Cost guardrails

Size from the Spark UI, not instinct: if stages spill, tune shuffle partitions and memory before adding executors; if executors sit idle, reduce instances. Use `concurrencyPolicy: Forbid` for all scheduled workflows. Overlapping runs are expensive and can conflict on Iceberg commits.

Where supported, tag Spark sessions to attribute spend by project and model:

```python
context.spark.conf.set("spark.sql.session.description", "vulcan:<project>:<model>")
```

For storage cost: keep AQE coalescing enabled to control output file counts, run `VACUUM` on high-churn Iceberg tables to reclaim deleted-file storage, set short snapshot retention on Bronze/staging tables that can be re-derived, and partition deliberately (over-partitioning creates small files; under-partitioning forces full scans).

### Next steps

If a workload still misbehaves after applying these limits, continue to [troubleshooting.md](troubleshooting.md "mention") to diagnose and recover from failures.
