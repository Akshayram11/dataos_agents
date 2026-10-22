---
description: Choose Fabric model kinds and understand their native Warehouse behavior.
---

# Materialization behavior

SQL models compile to the `fabric` dialect and execute against the warehouse SQL endpoint. Because Fabric Warehouse has no native transactions and a restricted T-SQL surface, several kinds materialize differently than on generic MSSQL.

| Model kind                            | Compiles to                                                                         | Notes                                                                       |
| ------------------------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| SEED                                  | Staged bulk load via a temp table, then `INSERT ... SELECT`                         | Inherited from the MSSQL adapter's `bulk_copy` path.                        |
| FULL                                  | `SELECT * INTO` on first run; subsequent runs replace content via delete-and-insert | No atomic `CREATE OR REPLACE TABLE`.                                        |
| VIEW                                  | `CREATE OR ALTER VIEW`                                                              | Always a full rewrite.                                                      |
| INCREMENTAL\_BY\_TIME\_RANGE          | `DELETE` by `time_column` window, then `INSERT`                                     | Uses the DELETE\_INSERT strategy (see below), not MERGE.                    |
| INCREMENTAL\_BY\_UNIQUE\_KEY          | Native `MERGE INTO ... USING ... ON <key>`                                          | Same MERGE logic as MSSQL, including the `mssql_merge_exists` optimization. |
| INCREMENTAL\_BY\_PARTITION            | `DELETE` by partition key, then `INSERT`                                            | Generic delete-plus-insert fallback.                                        |
| INCREMENTAL\_UNMANAGED                | Append-only pattern                                                                 | Vulcan does not manage updates or deletes.                                  |
| SCD\_TYPE\_2 / SCD\_TYPE\_2\_BY\_TIME | History table with validity windows tracked by time                                 |                                                                             |
| SCD\_TYPE\_2\_BY\_COLUMN              | History table with validity windows tracked by checked columns                      |                                                                             |
| EMBEDDED                              | Not materialized                                                                    | Inlined into downstream models.                                             |

### Insert-overwrite strategy: DELETE\_INSERT, not MERGE

Unlike generic MSSQL, where the default insert-overwrite strategy is `MERGE`, the Fabric adapter overrides this to `DELETE_INSERT`. Time-range and partition overwrites compile to an explicit `DELETE FROM ... WHERE ...` followed by `INSERT INTO ... SELECT ...`, executed as separate statements rather than a single `MERGE`. Since Fabric Warehouse does not support explicit transactions (`SUPPORTS_TRANSACTIONS` is off for this adapter), the delete and insert are not wrapped in a rollback-able transaction the way they might be elsewhere; plan reruns and `concurrencyPolicy: Forbid` matter more here than on engines with full transactional DDL.

### `INCREMENTAL_BY_UNIQUE_KEY` still uses MERGE

`INCREMENTAL_BY_UNIQUE_KEY` is the one kind that keeps the inherited MSSQL `MERGE INTO` path, including the `mssql_merge_exists` optimization described in the [MSSQL manual](../sql-server/#merge-and-the-mssql_merge_exists-optimization). The same column-type caveats apply (`GEOMETRY`, `XML`, `TEXT`, `NTEXT`, `IMAGE`, most user-defined types are not supported by the `EXCEPT`-based optimization); however, Fabric Warehouse's own type surface is already narrower than SQL Server's. Most of those types will not exist in a Fabric-native schema.

## Catalog (warehouse) lifecycle

Fabric Warehouse creation and deletion are not synchronous DDL statements. The adapter calls the Fabric REST API (`https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/warehouses`) using OAuth2 client-credentials (service principal) authentication against `login.microsoftonline.com`. Warehouse creation is asynchronous: Fabric returns a `202 Accepted` and the adapter polls the operation status with retries and exponential backoff until the warehouse is ready.

If you drop and immediately recreate a warehouse with the same name, Fabric can return an `ItemDisplayNameNotAvailableYet` error while the old name is still reserved during cleanup. The adapter waits and retries automatically, but if you are scripting warehouse teardown/recreation outside Vulcan, build in a similar wait-and-retry step rather than recreating immediately.

### Catalog switching has no session-persistent `USE`

Fabric Warehouse does not support `USE <database>` persisting across statements the way SQL Server does; each statement can run against its own session context. Because of this, the adapter does not attempt `USE` when switching the active catalog: it commits any pending work, closes the current connection, and opens a new connection directly against the target warehouse. If you write custom lifecycle SQL that assumes a persistent `USE` session (common in scripts ported from generic MSSQL), it will not behave the same way on Fabric. Always qualify objects with the warehouse name or rely on Vulcan's own catalog-switch handling rather than raw `USE` statements.

Since mid-2025, Fabric also validates that the `Database=` value in the connection string still exists at connection time and raises an authentication failure if it does not. Practically, this means dropping a warehouse that a live connection is still pointed at can surface as a misleading "authentication failed" error rather than an object-not-found error. Always close and reopen a connection after dropping its target warehouse.

## `ALTER TABLE` limitations and workaround

Fabric Warehouse has limited support for `ALTER TABLE`: it does not support directly changing a column's data type (`ALTER COLUMN ... TYPE`). When a schema change requires a column type change, the adapter runs a four-step workaround inside the same session:

{% stepper %}
{% step %}
**Add a temporary column**

```sql
ALTER TABLE ... ADD <temp_column> <new_type>
```
{% endstep %}

{% step %}
**Cast existing values**

```sql
UPDATE ... SET <temp_column> = CAST(<old_column> AS <new_type>)
```
{% endstep %}

{% step %}
**Drop the old column**

```sql
ALTER TABLE ... DROP COLUMN <old_column>
```
{% endstep %}

{% step %}
**Rename the temporary column**

```sql
EXEC sp_rename
```

Rename `<temp_column>` back to the original column name.
{% endstep %}
{% endstepper %}

Column additions that are not type changes execute as a direct `ALTER TABLE ... ADD` without the workaround. If you see a schema-migration step taking noticeably longer or touching more rows than expected, check whether it triggered this rewrite path. It is a full column rewrite, not a metadata-only operation, and its cost scales with table size.

## No native indexes on Fabric Warehouse

Fabric Warehouse does not support user-defined indexes the way SQL Server does; `CREATE INDEX` in guarded `post_statements` is a MSSQL-only pattern and is not available here. There is no `SUPPORTS_INDEXES` path for this adapter. Query performance on large tables depends on Fabric's own internal storage and statistics rather than explicit indexing, so the levers available on Postgres/MSSQL (add an index on a hot filter column) do not apply. Instead, favor partition-aligned filters, narrower `SELECT` lists, and pre-aggregated marts for expensive query shapes.

## Identifier casing and type surface

Fabric Warehouse's T-SQL surface is narrower than full SQL Server: some data types (notably `GEOMETRY`, `XML`, `TEXT`, `NTEXT`, `IMAGE`, and most user-defined types) either do not exist or are not fully supported. Use the standard Fabric-supported types (`INT`, `BIGINT`, `DECIMAL`, `VARCHAR(n)`, `NVARCHAR(n)`, `DATETIME2`, and similar) in model DDL. As with MSSQL, always declare an explicit length on `VARCHAR`/`NVARCHAR` columns.

## Lifecycle DDL

Wrap DDL in `pre_statements` / `post_statements` when it should run only during real execution, or a dry-run plan executes it:

```sql
@IF(
    @runtime_stage = 'evaluating',
    ALTER TABLE warehouse.gold.orders ADD ingested_at DATETIME2
)
```

Because Fabric has no explicit transaction support, be conservative with multi-statement lifecycle DDL. A failure partway through will not roll back earlier statements in the block.

## External source declarations

Declare non-owned source tables in `external_models.yaml` so linting and lineage resolve them. The physical table must exist only if a model actually selects from it.

## Semantic models and metrics

Use `{semantic_model.column}` braces for measure references and declare joins for multi-entity queries; cross-join-shaped semantic queries are one of the easiest ways to generate an expensive query on a warehouse with no user-tunable indexing. `COUNT(DISTINCT ...)` over wide tables is a primary cost driver; pre-aggregate into a mart rather than relying on an index, since indexes are not available here. Native constraints declared in Fabric Warehouse (`PRIMARY KEY`, `UNIQUE`) are informational only in some Fabric editions. Do not assume they are enforced at write time the way they are on SQL Server; keep Vulcan audits as the actual guardrail.

### Next step

Expose validated models to consumers through the [#endpoints](./#endpoints "mention").
