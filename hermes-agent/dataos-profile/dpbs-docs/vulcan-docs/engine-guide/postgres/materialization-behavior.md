---
description: Choose PostgreSQL model strategies and apply engine-specific model behavior.
---

# Materialization behavior

With a validated gateway, this is the build stage. Choose a model kind and understand its PostgreSQL operation before running it.

## Materialization behavior per model kind

SQL models compile to PostgreSQL SQL and execute directly on the server.

| Model kind                          | PostgreSQL operation                                                                                              |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `SEED`                              | `COPY` / batched `INSERT` from CSV into a table.                                                                  |
| `FULL`                              | `DROP TABLE`, `CREATE TABLE`, `INSERT` (rebuilds from scratch each run).                                          |
| `VIEW`                              | `CREATE OR REPLACE VIEW`.                                                                                         |
| `INCREMENTAL_BY_TIME_RANGE`         | DELETE by `time_column` window, then INSERT.                                                                      |
| `INCREMENTAL_BY_UNIQUE_KEY`         | Native `MERGE` (UPSERT) on PostgreSQL 15+, logical merge fallback on earlier versions.                            |
| `INCREMENTAL_BY_PARTITION`          | Partition-key replacement through Vulcan's generic delete-plus-insert fallback (not native partition DDL).        |
| `INCREMENTAL_UNMANAGED`             | Append/unmanaged pattern; Vulcan does not manage updates or deletes.                                              |
| `SCD_TYPE_2` / `SCD_TYPE_2_BY_TIME` | History table with validity windows tracked by time.                                                              |
| `SCD_TYPE_2_BY_COLUMN`              | History table with validity windows tracked by checked columns.                                                   |
| `EMBEDDED`                          | Not materialized; inlined into downstream models.                                                                 |
| `Python`                            | In-process Pandas DataFrame written through the adapter (not valid for `VIEW`, `EMBEDDED`, `SEED`, or `MANAGED`). |

### Lowercase identifiers

{% hint style="warning" %}
PostgreSQL folds unquoted identifiers to lowercase. Author model names, columns, semantic references, metric references, and DQ SQL in lowercase unless you intentionally use quoted identifiers everywhere. This is the opposite of the Snowflake and Spark UPPERCASE rule.
{% endhint %}

### Lifecycle DDL and raw PL/pgSQL

Wrap DDL in `pre_statements` / `post_statements` when it should run only during real execution, or a dry-run plan executes it:

```sql
@IF(@runtime_stage = 'evaluating',
  CREATE INDEX IF NOT EXISTS ix_orders_customer ON sales.orders (customer_id)
);
```

PostgreSQL-native DDL that the parser cannot interpret (anonymous `DO $$ ... $$` blocks, `CREATE FUNCTION ... LANGUAGE plpgsql`, trigger bodies) logs a harmless warning such as `'DO $$ ...' could not be semantically understood`. The block still runs verbatim; silence the console noise with `VULCAN_IGNORE_WARNINGS=1` or `vulcan --ignore-warnings`. Objects created inside PL/pgSQL are structural but opaque to SQL lineage.

### External source declarations

Declare non-owned source tables in `external_models.yaml` so linting and lineage resolve them. The physical table must exist only if a model actually selects from it.

```yaml
- name: '"warehouse"."raw_external"."country_lookup"'
  columns:
    country_code: VARCHAR
    country_name: VARCHAR
    region: VARCHAR
```

### Semantic models and metrics

Use `{semantic_model.column}` braces for measure references and declare joins for multi-entity queries; cross-join-shaped semantic queries are one of the easiest ways to saturate a single instance. Metrics use the current `kind: metric` shape with `ts` and `granularity`; some older example projects use an aggregate `metrics:` map with `time:`, which is legacy syntax. Two runtime behaviors matter: heavy `COUNT(DISTINCT ...)` over wide tables is a primary cost driver (pre-aggregate or add supporting indexes), and indexing matters more than on elastic warehouses (add an index on a slow filter/join column through guarded `post_statements`). Native constraints (`NOT NULL`, `CHECK`, `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`) are enforced at write time and complement Vulcan audits.

### Next step

After models deploy, make data available through [#endpoints](./#endpoints "mention").
