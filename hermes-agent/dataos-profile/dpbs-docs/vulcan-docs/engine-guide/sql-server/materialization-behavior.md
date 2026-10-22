---
description: Choose SQL Server model strategies and apply engine-specific model behavior.
---

# Materialization behavior

## Materialization behavior per model kind

Choose model behavior after the gateway connects successfully. SQL models compile to T-SQL and execute directly on the server.

| Model kind                            | Compiles to                                                  | Notes                                               |
| ------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------- |
| SEED                                  | `bulk_copy` staged insert, then `INSERT ... SELECT`          | Loads CSV-backed reference data.                    |
| FULL                                  | `SELECT * INTO` first run; `TRUNCATE TABLE` + `INSERT` later | SQL Server has no atomic `CREATE OR REPLACE TABLE`. |
| VIEW                                  | `CREATE OR ALTER VIEW`                                       | Always a full rewrite.                              |
| INCREMENTAL\_BY\_TIME\_RANGE          | `DELETE` by `time_column`, then `INSERT`                     | Re-runs replace the affected window.                |
| INCREMENTAL\_BY\_UNIQUE\_KEY          | Native `MERGE INTO ... USING ... ON <key>`                   | See the MERGE optimization below.                   |
| INCREMENTAL\_BY\_PARTITION            | `DELETE` by partition key, then `INSERT`                     | Delete-plus-insert fallback.                        |
| INCREMENTAL\_UNMANAGED                | Append-only pattern                                          | Vulcan does not manage updates or deletes.          |
| SCD\_TYPE\_2 / SCD\_TYPE\_2\_BY\_TIME | History table with time validity windows                     |                                                     |
| SCD\_TYPE\_2\_BY\_COLUMN              | History table with checked-column validity windows           |                                                     |
| EMBEDDED                              | Not materialized                                             | Inlined into downstream models.                     |

{% hint style="info" %}
`MANAGED` models and table cloning are not supported on this adapter.
{% endhint %}

### MERGE and `mssql_merge_exists`

By default, `MERGE` updates all non-key columns for each matching row. Set `mssql_merge_exists` in `physical_properties` to skip identical updates through an `EXISTS ... EXCEPT` comparison:

```sql
MODEL (
    name warehouse.gold.unique_key,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key id
    ),
    cron '@daily',
    physical_properties (
        mssql_merge_exists = true
    )
);
```

{% hint style="warning" %}
`EXCEPT` does not support `GEOMETRY`, `XML`, `TEXT`, `NTEXT`, `IMAGE`, or most user-defined types. Do not enable this optimization for those tables.
{% endhint %}

The setting also changes FULL-style overwrites. Without it, Vulcan uses `TRUNCATE` plus `INSERT`. With it, or with a conditional overwrite, Vulcan uses `MERGE`.

### Data types and identifiers

SQL Server defaults bare `VARCHAR` to `VARCHAR(1)`. Always specify a length, such as `VARCHAR(255)` or `VARCHAR(MAX)`.

The default collation is case-insensitive but case-preserving. Vulcan quotes reserved words and spaced identifiers with square brackets. Do not rely on casing to distinguish identifiers.

### Indexing

SQL Server supports clustered and non-clustered indexes, plus unique constraints. SQL Server has no `CREATE INDEX IF NOT EXISTS`. Use an existence check against `sys.indexes`:

```sql
IF NOT EXISTS (
    SELECT * FROM sys.indexes WHERE name = 'ix_orders_customer_id' AND object_id = OBJECT_ID('warehouse.gold.orders')
)
CREATE INDEX ix_orders_customer_id ON warehouse.gold.orders (customer_id);
```

Index incremental `time_column` or `unique_key` columns. Also index hot filter and join columns used by the semantic API.

### Python models

Python models materialize in-process Pandas DataFrames. Large DataFrames stage through a temp table and `pymssql` `bulk_copy`. Datetime and date values are stringified before loading. Timezone-aware timestamps become ISO strings before casting. Python models do not support VIEW, EMBEDDED, SEED, or MANAGED kinds.

### Lifecycle DDL and raw T-SQL

Wrap DDL in `pre_statements` or `post_statements` when it should run only during execution. Otherwise, a dry-run plan executes it.

```sql
@IF(
    @runtime_stage = 'evaluating',
    CREATE OR ALTER TRIGGER trg_orders_audit ON warehouse.gold.orders AFTER INSERT AS BEGIN SET NOCOUNT ON; END
)
```

For table-shaped objects, use `IF NOT EXISTS` checks against `sys.tables` and `EXEC(...)`.

### External source declarations

Declare non-owned source tables in `external_models.yaml`. This keeps linting and lineage accurate. The table must exist only when a model selects from it.

### Semantic models and metrics

Use `{semantic_model.column}` braces for measure references. Declare joins for multi-entity queries. Cross-join-shaped semantic queries can saturate a single instance.

Metrics use `kind: metric` with `ts` and `granularity`. Pre-aggregate wide `COUNT(DISTINCT ...)` workloads or add supporting indexes. Native constraints complement Vulcan audits.

### Next step

After models deploy, make the Data Product available through [#endpoints](./#endpoints "mention").
