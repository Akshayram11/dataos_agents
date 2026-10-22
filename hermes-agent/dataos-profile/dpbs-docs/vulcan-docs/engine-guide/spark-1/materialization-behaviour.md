---
description: >-
  Understand how Vulcan model kinds map to native Spark/Iceberg operations,  
  and how the semantic layer and business metrics build on top of them.
---

# Materialization behaviour

With a validated gateway from [connection-options.md](connection-options.md "mention"), this is the build stage: choose a model kind and know exactly what Spark/Iceberg operation it produces before you run it.

SQL models compile to Spark SQL and write Iceberg tables through the lakehouse REST catalog. The Vulcan workflow acts as the Spark driver; executors perform scans, joins, shuffles, and writes.

## Materialization behavior per model kind

| Model kind                  | Spark / Iceberg operation                   | Notes                                                                           |
| --------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------- |
| `FULL`                      | `INSERT OVERWRITE` (replace target content) | Good for small tables, aggregates, rebuildable marts.                           |
| `SEED` / `EMBEDDED`         | File-backed or embedded reference data      | Small reference tables.                                                         |
| `INCREMENTAL_BY_TIME_RANGE` | `INSERT OVERWRITE` by time-window partition | Keep `time_column` UTC; filter source by interval macros.                       |
| `INCREMENTAL_BY_PARTITION`  | `INSERT OVERWRITE` by partition key         | Best when the partition key is the natural restatement boundary.                |
| `INCREMENTAL_BY_UNIQUE_KEY` | Iceberg `MERGE INTO`                        | Requires Iceberg `physical_properties`; supports upsert and conditional delete. |
| `SCD_TYPE_2`                | Spark/Iceberg slowly changing dimension     | Dimension history with current and historical rows.                             |

{% hint style="warning" %}
Declare Iceberg `physical_properties` on all production tables. `INCREMENTAL_BY_UNIQUE_KEY` compiles to Iceberg `MERGE INTO`: without `physical_properties(format = 'iceberg')` or `table_format iceberg`, the model silently does nothing. Align `grain`/`grains` with `unique_key`.
{% endhint %}

```sql
MODEL (
  name lakehouse_depot.tpch_lakehouse.customer_360,
  kind FULL,
  owner 'data-product-owner',
  grains (customer_key),
  physical_properties (
    format = 'iceberg',
    'write.format.default' = 'parquet',
    'write.parquet.compression-codec' = 'snappy'
  ),
  assertions (
    unique_values(columns := customer_key),
    not_null(columns := (customer_key, customer_name))
  )
);
SELECT
  cn.c_custkey                                               AS customer_key,
  cn.c_name                                                  AS customer_name,
  cn.c_mktsegment                                            AS market_segment,
  COUNT(DISTINCT oi.l_orderkey)                              AS order_count,
  COALESCE(SUM(oi.net_amount), 0)                            AS total_revenue
FROM lakehouse_depot.tpch_lakehouse.int_customer_nation cn
LEFT JOIN lakehouse_depot.tpch_lakehouse.int_order_items oi
  ON oi.o_custkey = cn.c_custkey
GROUP BY cn.c_custkey, cn.c_name, cn.c_mktsegment;
```

A MERGE-heavy unique-key model uses `source.` and `target.` aliases. New keys fall through to an implicit insert, so delete tombstones for missing keys insert rows unless filtered upstream:

```sql
kind INCREMENTAL_BY_UNIQUE_KEY (
  unique_key c_custkey,
  when_matched (
    WHEN MATCHED AND source.last_op = 'D' THEN DELETE
    WHEN MATCHED AND source.last_op IN ('I', 'U') THEN UPDATE SET ...
  )
),
table_format iceberg,
grain (c_custkey)
```

Wrap `pre_statements` / `post_statements` lifecycle DDL that should only run on real execution. Otherwise, `vulcan plan` dry-runs execute it:

```sql
@IF(@runtime_stage = 'evaluating',
  ALTER TABLE lakehouse_depot.gold.orders SET TBLPROPERTIES ('write.metadata.delete-after-commit.enabled' = 'true')
);
```

### Python models

Python models should return a Spark DataFrame, using `context.spark.sql()` or the DataFrame API. Do not convert large inputs to Pandas on the driver: this pulls data to the driver and causes OOM. A Pandas return is safe only for a bounded summary (one row). RDD APIs are supported for legacy or custom logic but bypass the Catalyst optimizer and Iceberg column pruning. Prefer DataFrames in production models. Avoid `collect()` and `toPandas()` on large tables.

### Identifier casing

Use UPPERCASE dimensions and measure expressions to match the physical column casing in the underlying Iceberg tables (as aliased in staging). Lowercase causes `column not found`. `COUNT(DISTINCT …)` over large Iceberg tables is shuffle-heavy and the primary sizing driver; declare explicit joins, because cross-join-shaped queries are the biggest avoidable latency risk.

### Semantic models

Semantic models wrap Vulcan-managed Iceberg tables and expose dimensions, measures, segments, and joins to API and SQL-wire consumers. The API track translates semantic queries into Spark/Iceberg reads. Declare explicit joins in semantics. Cross-join-shaped queries are the biggest avoidable latency risk on Spark. Identifier casing follows the same UPPERCASE rule as models above.

```yaml
kind: semantic
name: CUSTOMER_ORDERS_SUMMARY
depends_on: lakehouse_depot.tpch_lakehouse.customer_360
dimensions:
  - MARKET_SEGMENT
measures:
  - name: TOTAL_REVENUE
    type: sum
    expression: "{CUSTOMER_ORDERS_SUMMARY.TOTAL_REVENUE}"
  - name: CUSTOMER_COUNT
    type: count_distinct
    expression: "{CUSTOMER_ORDERS_SUMMARY.CUSTOMER_KEY}"
segments:
  - name: positive_balance
    expression: "{CUSTOMER_ORDERS_SUMMARY.ACCT_BAL} > 0"
```

### Business metrics

A metric is a YAML manifest that references a measure already defined in a semantic model. Vulcan compiles it to a Spark SQL aggregation executed against Iceberg.

```yaml
kind: metric
name: DAILY_REVENUE
measure: CUSTOMER_ORDERS_SUMMARY.TOTAL_REVENUE
ts: CUSTOMER_ORDERS_SUMMARY.ORDER_DATE
granularity: day
dimensions:
  - name: MARKET_SEGMENT
    ref: CUSTOMER_ORDERS_SUMMARY.MARKET_SEGMENT
```

Two Spark-specific behaviors matter at runtime. `COUNT(DISTINCT …)` over large Iceberg tables is shuffle-heavy and the primary compute sizing driver. Size up executors or pre-aggregate distinct counts into a mart before rewriting the metric. Identifier casing in metric `filters`/`expressions` follows the same UPPERCASE rule as semantic models. Lowercase references cause "column not found" errors.

## Data quality

Vulcan quality is layered on Spark. Live checks execute as Spark SQL against Iceberg tables and consume compute from the workflow run or a dedicated quality track.

| Layer                        | Where it runs                                  | Spark cost                | When it catches a problem                 |
| ---------------------------- | ---------------------------------------------- | ------------------------- | ----------------------------------------- |
| Linter                       | Locally, before Spark execution                | None                      | Authoring time                            |
| Assertions (in `MODEL(...)`) | Spark during model materialization             | Counted in the model run  | Every run                                 |
| Unit tests (`tests/`)        | Locally (DuckDB in-process)                    | No cluster cost           | Pre-deploy logic regressions              |
| Audits (`audits/`)           | Spark after model materializes                 | One Spark query per audit | Post-run relationship failures            |
| Data quality (`kind: dq`)    | Spark SQL after model execution or on schedule | One or more Spark jobs    | Observability, drift, freshness, accuracy |

Use `assertions` inside `MODEL(...)` for invariants that make the table unsafe if they fail (primary key uniqueness, required columns, non-negative measures). Use `kind: dq` for non-blocking drift, freshness, and distribution checks.

```yaml
kind: dq
name: customer_360_dq
depends_on: lakehouse_depot.tpch_lakehouse.customer_360
profiles:
  - order_count
  - total_revenue
  - market_segment
rules:
  - row_count > 0:
      name: customer_360_not_empty
      dimension: completeness
  - missing_count(customer_key) = 0:
      name: no_missing_customer_key
      dimension: completeness
  - failed rows:
      name: negative_revenue
      dimension: accuracy
      fail query: |
        SELECT customer_key, total_revenue
        FROM lakehouse_depot.tpch_lakehouse.customer_360
        WHERE total_revenue < 0
      samples limit: 10
```

Keep `failed rows` queries narrow and always set `samples limit` so incident payloads stay bounded. Profile only operationally useful columns. Profiling high-cardinality string columns on large Iceberg tables is expensive. Use fully qualified lakehouse table names in all DQ and audit SQL, and for partitioned Iceberg tables add partition predicates where the rule only needs the latest window.

## Next steps

Size and tune the workload before production schedules in [limits-and-performance.md](limits-and-performance.md "mention").
