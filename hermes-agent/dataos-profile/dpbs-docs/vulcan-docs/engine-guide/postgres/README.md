---
description: >-
  Choose, configure, build, serve, and operate PostgreSQL-backed Vulcan Data
  Products.
noIndex: true
---

# Postgres

PostgreSQL is an open-source relational database that works with Vulcan. Use it for smaller projects, development environments, or full database-infrastructure control. This guide covers connection, grants, materialization, local Docker setup, operational guardrails, and recovery.

## Decide

### Assess fit

Choose PostgreSQL for smaller Data Products, development, or full database control. There is no warehouse cold-start penalty. PostgreSQL also has no elastic scale-out.

Performance depends on instance size, IOPS, indexes, and data volume. Native features such as indexes, constraints, row-level security, materialized views, triggers, and federation work through guarded raw DDL.

### Engine characteristics

| Property            | Value                                                              |
| ------------------- | ------------------------------------------------------------------ |
| Engine adapter type | `postgres`                                                         |
| Model dialect       | `postgres`                                                         |
| Query execution     | PostgreSQL server; no separate warehouse to start, stop, or resize |

### Supported model kinds

`SEED`, `FULL`, `VIEW`, `INCREMENTAL_BY_TIME_RANGE`, `INCREMENTAL_BY_UNIQUE_KEY`, `INCREMENTAL_BY_PARTITION`, `INCREMENTAL_UNMANAGED`, `SCD_TYPE_2`, `SCD_TYPE_2_BY_TIME`, `SCD_TYPE_2_BY_COLUMN`, and `EMBEDDED`. Python models materialize an in-process Pandas DataFrame through the adapter and do not support `VIEW`, `EMBEDDED`, `SEED`, or `MANAGED` kinds.

Once you choose Postgres as your Data Product engine, use this guide to explore **Authorize, Connect, Build, Serve, Operate, and Troubleshoot**—covering access, connectivity, model development, data serving, performance, and issue resolution.

Depending on where you are starting from, you may enter this path at a different point.

## Authorize

Provision PostgreSQL and DataOS access before configuring a gateway or deploying a Data Product. Use [permissions-and-grants.md](permissions-and-grants.md "mention") for role design, grant templates, and required permissions.

## Connect

This is the first hands-on step after access provisioning.

For connection options, gateway configuration, local Docker development, and production deployment, see [connect-to-postgres.md](connect-to-postgres.md "mention").

## Build models

Choose a model strategy after you validate the connection.

For model-kind mappings, lifecycle SQL, external source declarations, and semantic-model guidance, see [materialization-behavior.md](materialization-behavior.md "mention").

### Engine-native feature support

After core models work, add PostgreSQL-specific capabilities where they add clear value.

| PostgreSQL feature          | Vulcan pattern                                                                                  |
| --------------------------- | ----------------------------------------------------------------------------------------------- |
| Database                    | `connection.database` (must exist before apply).                                                |
| Schema                      | Referenced by model names; created automatically when the role has privilege.                   |
| Regular / incremental table | `FULL` and incremental models.                                                                  |
| View                        | `kind VIEW`.                                                                                    |
| SCD history                 | `SCD_TYPE_2_BY_TIME` / `SCD_TYPE_2_BY_COLUMN`.                                                  |
| Indexes                     | `CREATE INDEX` in guarded `post_statements`.                                                    |
| Row-level security          | `ENABLE ROW LEVEL SECURITY` plus `CREATE POLICY`.                                               |
| Triggers / functions        | Guarded PL/pgSQL DDL (parser warning expected).                                                 |
| Materialized view           | Raw `CREATE MATERIALIZED VIEW` / `REFRESH` (`kind VIEW materialized true` does not create one). |
| Full-text search            | Generated `tsvector` plus GIN index.                                                            |
| FDW federation              | `postgres_fdw` extension plus foreign tables (DBA-level setup).                                 |

#### Not supported

Vulcan does not manage these PostgreSQL capabilities:

* `MANAGED` models and `kind VIEW materialized true` materialized views.
* Elastic scale-out and auto-suspend.
* Cross-database queries.

Treat server lifecycle, database creation, extensions, replication, and instance parameters as DBA boundaries.

### Recipes

Use [recipes](recipes/ "mention") for full-text search and row-level security patterns.

## Serve

### Endpoints

Use endpoints to make deployed Data Product data available to consumers.

Every deployed Data Product gets REST, GraphQL, and MySQL-wire endpoints, all pushing down to the same PostgreSQL gateway. Large result sets are buffered before streaming; size `api.resource.limit.memory` for expected payloads, with 3 GiB a practical starting point for high-row responses.

### Metadata scanning and catalog

DataOS scans PostgreSQL for discovery and governance. The scan catalogs available assets and maps their lineage.

DataOS scans `information_schema` (databases, schemas, tables, columns, grants) and `pg_catalog` (constraints, indexes, comments, view definitions). PostgreSQL has no warehouse-style query-history table, so lineage comes from parsed definitions and Vulcan's model graph. Use a read-only scanner role separate from the Vulcan service role:

```sql
GRANT CONNECT ON DATABASE warehouse TO scanner;
GRANT USAGE ON SCHEMA sales, raw TO scanner;
GRANT SELECT ON ALL TABLES IN SCHEMA sales, raw TO scanner;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT SELECT ON TABLES TO scanner;
```

Scanner cadence is commonly every 6 to 12 hours. If lineage is missing after `vulcan apply`, verify `external_models.yaml`, then wait for the next scan.

## Operate safely

Set workload limits before scaling consumers or production schedules.

For compute sizing, concurrency, scheduling, and performance guidance, see [limits-and-performance.md](limits-and-performance.md "mention").

### Before production

* Confirm least-privilege grants.
* Validate the gateway.
* Set concurrency and connection limits.
* Test recovery procedures.

## Troubleshooting

Use these checks when configuration, deployment, or runtime behavior needs investigation.

For failure modes, health checks, and recovery procedures, see [troubleshooting.md](troubleshooting.md "mention").

## Full implementation example

Use this complete Postgres Data Product as a production-shaped starting point.

{% file src="../../.gitbook/assets/postgres-data-product.zip" %}

## Related

* [Engine guide overview](../) for the cross-engine rules.
