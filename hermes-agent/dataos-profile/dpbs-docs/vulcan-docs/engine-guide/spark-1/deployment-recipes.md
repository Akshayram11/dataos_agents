---
description: >-
  Ready-to-copy sparkConf and resource sizing for common Spark deployment  
  shapes: daily incremental, medium lakehouse mart, large backfill, and  
  MERGE-heavy CDC.
---

# Deployment recipes

Use these recipes as a starting `spec` instead of tuning from a blank slate. Each one is a complete resource-sizing shape for a common workload; pair it with the driver/executor guidance in limits-and-performance.md if you need to adjust further.

Every recipe sets `sparkConf` in both `spec.workflow.sparkConf` (tunes `migrate`/`plan`/`run`) and `spec.sparkConf` (tunes the API track's separate Spark session). `spec.api` is sized independently. It sets request and limit resources plus replica count for REST/GraphQL/MySQL-wire concurrency.

### Daily incremental, small project (5–20 models)

```yaml
spec:
  engine: spark
  compute: spark-compute
  depots:
    - dataos://lakehouse-depot?purpose=rw
  workflow:
    schedule:
      crons: ['0 3 * * *']
      timezone: UTC
      endOn: '2028-01-01T00:00:00Z'
      concurrencyPolicy: Forbid
    resource:
      driver: { coreLimit: "2000m", cores: 1, memory: "2G" }
      executor: { coreLimit: "4000m", cores: 2, memory: "4G", instances: 2 }
    sparkConf:
      spark.sql.adaptive.enabled: "true"
      spark.sql.adaptive.coalescePartitions.enabled: "true"
      spark.serializer: org.apache.spark.serializer.KryoSerializer
  sparkConf:
    spark.sql.adaptive.enabled: "true"
    spark.sql.adaptive.coalescePartitions.enabled: "true"
    spark.serializer: org.apache.spark.serializer.KryoSerializer
  api:
    replicas: 2
    resource:
      request: { cpu: "200m", memory: "512Mi" }
      limit:   { cpu: "2000m", memory: "2Gi" }
```

### Medium lakehouse mart (\~10–100 GB)

```yaml
spec:
  engine: spark
  compute: spark-compute
  workflow:
    resource:
      driver: { coreLimit: "4000m", cores: 2, memory: "6G" }
      executor: { coreLimit: "4000m", cores: 3, memory: "6G", instances: 4 }
    sparkConf:
      spark.sql.shuffle.partitions: "300"
      spark.sql.adaptive.enabled: "true"
      spark.sql.adaptive.skewJoin.enabled: "true"
      spark.sql.adaptive.coalescePartitions.enabled: "true"
      spark.sql.files.maxPartitionBytes: "134217728"
      spark.serializer: org.apache.spark.serializer.KryoSerializer
  sparkConf:
    spark.sql.shuffle.partitions: "300"
    spark.sql.adaptive.enabled: "true"
    spark.sql.adaptive.skewJoin.enabled: "true"
    spark.sql.adaptive.coalescePartitions.enabled: "true"
    spark.sql.files.maxPartitionBytes: "134217728"
    spark.serializer: org.apache.spark.serializer.KryoSerializer
  api:
    replicas: 2
    resource:
      request: { cpu: "500m", memory: "1Gi" }
      limit:   { cpu: "2000m", memory: "4Gi" }
```

### Large backfill (first run, 1–5 years of history)

```yaml
spec:
  workflow:
    type: trigger                 # one-shot; no recurring schedule
    resource:
      driver: { coreLimit: "4000m", cores: 4, memory: "8G" }
      executor: { coreLimit: "6000m", cores: 4, memory: "8G", instances: 8 }
    sparkConf:
      spark.sql.shuffle.partitions: "1000"
      spark.sql.files.maxPartitionBytes: "268435456"
      spark.sql.adaptive.enabled: "true"
      spark.sql.adaptive.skewJoin.enabled: "true"
  sparkConf:
    spark.sql.shuffle.partitions: "1000"
    spark.sql.files.maxPartitionBytes: "268435456"
    spark.sql.adaptive.enabled: "true"
    spark.sql.adaptive.skewJoin.enabled: "true"
  api:
    replicas: 2
    resource:
      request: { cpu: "200m", memory: "512Mi" }
      limit:   { cpu: "2000m", memory: "2Gi" }
```

Run backfills off-peak, and return to the normal executor count immediately after the backfill completes. The API track keeps serving existing materialized data throughout. Its sizing doesn't need to scale with the backfill's driver and executor resources.

### MERGE-heavy CDC project

```yaml
spec:
  workflow:
    schedule:
      crons: ['30 2 * * *']
      timezone: UTC
      concurrencyPolicy: Forbid
    resource:
      driver: { coreLimit: "4000m", cores: 2, memory: "6G" }
      executor: { coreLimit: "4000m", cores: 3, memory: "6G", instances: 4 }
    sparkConf:
      spark.sql.shuffle.partitions: "300"
      spark.sql.adaptive.enabled: "true"
      spark.sql.catalog.lakehouse_depot.commit.retry.num-retries: "10"
      spark.sql.catalog.lakehouse_depot.commit.retry.min-wait-ms: "1000"
      spark.sql.catalog.lakehouse_depot.commit.retry.max-wait-ms: "60000"
  sparkConf:
    spark.sql.shuffle.partitions: "300"
    spark.sql.adaptive.enabled: "true"
    spark.sql.catalog.lakehouse_depot.commit.retry.num-retries: "10"
    spark.sql.catalog.lakehouse_depot.commit.retry.min-wait-ms: "1000"
    spark.sql.catalog.lakehouse_depot.commit.retry.max-wait-ms: "60000"
  api:
    replicas: 2
    resource:
      request: { cpu: "500m", memory: "1Gi" }
      limit:   { cpu: "2000m", memory: "4Gi" }
```

Pair with unique-key models that explicitly declare Iceberg format:

```sql
MODEL (
  name lakehouse_depot.crm.customer_snapshot,
  kind INCREMENTAL_BY_UNIQUE_KEY (
    unique_key c_custkey,
    batch_size 1,
    when_matched (
      WHEN MATCHED AND source.last_op = 'D' THEN DELETE
      WHEN MATCHED AND source.last_op IN ('I', 'U') THEN UPDATE SET
        c_name       = source.c_name,
        c_mktsegment = source.c_mktsegment,
        last_op      = source.last_op
    )
  ),
  table_format iceberg,
  partitioned_by (source_ds),
  grain (c_custkey)
);
```

`when_matched` branches use `source.` and `target.` aliases. New keys fall through to implicit insert, so delete tombstones for missing keys insert rows unless filtered upstream.

## Next steps

Return to the [.](./ "mention") to continue with serving, operations, and troubleshooting guidance.
