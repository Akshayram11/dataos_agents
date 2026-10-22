---
description: Understand how Vulcan model kinds map to native Snowflake operations.
---

# Materialization behavior

With a validated gateway from [connect-to-snowflake.md](connect-to-snowflake.md "mention"), this is the build stage: choose a model kind and know exactly what Snowflake operation it produces before you run it. SQL models compile to native Snowflake SQL. Each model kind maps to a Snowflake operation.

## Materialization behavior per model kind

| Model kind                  | Snowflake operation                                  | Notes                                                       |
| --------------------------- | ---------------------------------------------------- | ----------------------------------------------------------- |
| `FULL`                      | `CREATE OR REPLACE TABLE`                            | Rebuilds the table from scratch each run.                   |
| `SEED`                      | Loads a file-backed reference dataset, commonly CSV. | Use for small reference tables.                             |
| `VIEW`                      | `CREATE OR REPLACE VIEW`                             | Always fully rewrites. It has no partition or key tracking. |
| `INCREMENTAL_BY_TIME_RANGE` | DELETE by time range, then INSERT                    | Deletes and refreshes the target window. Re-runs are safe.  |
| `INCREMENTAL_BY_UNIQUE_KEY` | `MERGE` on the unique key                            | Updates existing rows or inserts new rows.                  |
| `INCREMENTAL_BY_PARTITION`  | DELETE by partitioning key, then INSERT              | Maintains partition-level consistency during reprocessing.  |
| `MANAGED`                   | `CREATE OR REPLACE DYNAMIC TABLE`                    | Requires Enterprise edition or higher.                      |
| `SCD`                       | `MERGE` implementing SCD Type 2                      | Maintains history with effective and expiration dates.      |

### Python (Snowpark) models

Python models run through Snowpark. Declare the model kind with `@model(...)`. Return a Snowpark DataFrame from the model body.

{% hint style="warning" %}
Import Snowpark functions inside `execute()`. Module-level imports raise `NameError: 'col' is not defined`.
{% endhint %}

```python
def execute(context, start, end, execution_time, **kwargs):
    from snowflake.snowpark.functions import col, lit, when
    df = context.snowpark.table(
        context.resolve_table('"SNOWFLAKE_SAMPLE_DATA"."TPCH_SF1"."CUSTOMER"')
    )
    return df.select(col("C_CUSTKEY"), col("C_NAME"))
```

Default to SQL. Use Snowpark for Python libraries or complex DataFrame operations.

### Semantic models, metrics, and identifier casing

Snowflake stores unquoted identifiers in UPPERCASE. Use UPPERCASE in dimensions, measures, filters, joins, DQ SQL, and metric expressions. Lowercase causes `object does not exist`.

```yaml
dimensions:
  - USER_ID
  - SIGNUP_DATE
  - PLAN_TYPE
measures:
  - name: ACTIVE_USERS
    type: COUNT
    filters:
      - "{users.STATUS} = 'active'"
```

`COUNT(DISTINCT …)` runs exactly on Snowflake. Cross-join-shaped semantic queries can run 30 times slower. Model joins explicitly and pre-aggregate a mart when needed.

### Lifecycle DDL

Guard raw DDL and DML in `pre_statements`, `post_statements`, `after_all`, and `before_all`. By default, `vulcan plan` executes these blocks.

```sql
@IF(@runtime_stage = 'evaluating',
  ALTER TABLE myproj.gold.orders CLUSTER BY (order_date, nation_name)
);
```

Refer to [Vulcan Models](../../models/data-models/statements.md) for more details.

### Macro rules

Macro column arguments are expression objects, not strings. Do not annotate them as `: str`. Render them with `.sql(dialect=evaluator.dialect)`. Keep an empty `macros/__init__.py` file so Vulcan discovers the folder.

Refer to [Vulcan- Macros](../../advanced-features/macros/) for more details.

### Cross-database external models

`vulcan create_external_models` only inspects the gateway database. Declare cross-database sources manually with triple-quoted identifiers.

```yaml
- name: '"SNOWFLAKE_SAMPLE_DATA"."TPCH_SF1"."ORDERS"'
  columns:
    o_orderkey: NUMBER
    o_custkey: NUMBER
    o_orderdate: DATE
    o_totalprice: NUMBER
```

The triple quote preserves Snowflake’s case-sensitive UPPERCASE identifier. Without it, the linter reports `Table not found`.

### Next step

Return to [#endpoints](./#endpoints "mention") to select a consumption interface.
