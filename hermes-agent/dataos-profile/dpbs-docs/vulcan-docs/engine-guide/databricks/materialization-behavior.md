---
description: Understand how Vulcan model kinds map to Delta Lake operations on Databricks.
---

# Materialization behavior

With a validated gateway, this is the build stage. Choose a model kind and understand its Delta Lake operation before running it.

## Materialization behavior per model kind

SQL models compile to Databricks SQL. They execute on the configured SQL warehouse over Unity Catalog Delta tables.

| Model kind                  | Databricks operation                                                                                                                                                        |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FULL`                      | `INSERT OVERWRITE` (replaces table contents; Delta, UC-managed).                                                                                                            |
| `VIEW`                      | `CREATE OR REPLACE VIEW` (staging / intermediate layer).                                                                                                                    |
| `INCREMENTAL_BY_TIME_RANGE` | `INSERT OVERWRITE` by time-column partition (overwrites the whole partition for the window).                                                                                |
| `INCREMENTAL_BY_UNIQUE_KEY` | `MERGE` on the unique key (ACID upsert via Delta Lake).                                                                                                                     |
| `INCREMENTAL_BY_PARTITION`  | `REPLACE WHERE` by partitioning key (Delta partition-scoped overwrite).                                                                                                     |
| `SCD2`                      | <p><code>MERGE</code> INTO Delta table<br><br>(Maintains historical versions of records by expiring the existing record and inserting a new version when data changes.)</p> |

A typical layering pattern: declare Bronze/source tables in `external_models.yaml`, alias raw columns to business names in `VIEW` staging models, build gold dimensions as `FULL`, and build the gold fact as `INCREMENTAL_BY_TIME_RANGE` partitioned on the date column.

```sql
MODEL (
  name marts.fct_sales,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column order_date
  ),
  grain (ORDER_LINE_ID)
);
SELECT ...
FROM   intermediate.int_order_items
WHERE  order_date BETWEEN @start_date AND @end_date;
```

### Identifier casing

{% hint style="warning" %}
Match semantic model identifiers to the physical column casing of the model they reference. Databricks sample and raw tables use lowercase column names (`c_custkey`); alias them to UPPERCASE in staging, then use UPPERCASE everywhere in semantic models, filters, joins, DQ SQL, and metric expressions. Lowercase causes `column not found`.
{% endhint %}

```sql
SELECT c_custkey AS CUSTOMER_ID, c_name AS CUSTOMER_NAME FROM samples.tpch.customer
```

```yaml
kind: semantic
name: ORDERS
model: marts.fct_sales
dimensions:
  includes:
    - ORDER_LINE_ID
    - ORDER_DATE
    - CUSTOMER_ID
measures:
  - name: TOTAL_SALES
    type: sum
    sql: "{ORDERS.TOTAL_REVENUE}"
```

### Cross-catalog external models and lifecycle DDL

`vulcan create_external_models` may not discover tables outside the configured catalog (for example, `samples.tpch`). Declare them in `inputs.yaml`, or the linter throws `Table not found` and lineage stops at the model boundary.

```yaml
- name: samples.tpch.customer
  columns:
    c_custkey: BIGINT
    c_name:    VARCHAR(25)
    c_mktsegment: VARCHAR(10)
```

Wrap any DDL in `pre_statements` / `post_statements` that should run only on real execution, or `vulcan plan` executes it:

```sql
@IF(@runtime_stage = 'evaluating',
  OPTIMIZE <catalog>.<schema>.<table> ZORDER BY (order_date)
);
```

To make forward-only structural changes, set the Delta column-mapping property on the model, otherwise `ALTER` operations such as dropping a column fail with `DELTA_UNSUPPORTED_DROP_COLUMN`:

```
physical_properties (
  'delta.columnMapping.mode' = 'name'
)
```

### Next step

After models deploy, use [#endpoints](./#endpoints "mention") to serve Data Product data.
