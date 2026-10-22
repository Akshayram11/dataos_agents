---
description: >-
  The full technical reference for building and running a Vulcan Data Product on
  Databricks, covering connection, Unity Catalog grants, materialization, state
  store, operations, and troubleshooting.
noIndex: true
---

# Databricks

Databricks is an Apache Spark-based analytics platform with managed clusters, a SQL engine, Unity Catalog, and Delta Lake. Vulcan runs against Databricks to manage governed transformations on Unity Catalog Delta tables. This guide covers connection, grants, the required external state store, materialization, operations, and recovery.

## Decide

### Assess fit

Choose Databricks when your data lands in Unity Catalog as Delta tables. Use a SQL warehouse to transform and serve that data. The SQL warehouse plus Unity Catalog path is GA.

The Python and Databricks Connect path is partial. Validate Python model support against your Vulcan image before production use.

### Supported model kinds

`FULL`, `VIEW`, `INCREMENTAL_BY_TIME_RANGE`, `INCREMENTAL_BY_UNIQUE_KEY`, `INCREMENTAL_BY_PARTITION`, and `SCD_TYPE_2`.

### Engine characteristics

| Property            | Value                                                                |
| ------------------- | -------------------------------------------------------------------- |
| Engine adapter type | `databricks`                                                         |
| Model dialect       | `databricks`                                                         |
| Execution vehicle   | SQL warehouse via `http_path`, not an all-purpose cluster by default |

{% hint style="warning" %}
Vulcan state (plans, snapshots, intervals) cannot live in the SQL warehouse. Databricks requires an external Postgres `state_connection`. A running statestore is mandatory for both local development and production.
{% endhint %}

Once you choose Databricks as your Data Product engine, use this guide to explore **Authorize, Connect, Build, Serve, Operate, and Troubleshoot**—covering access, connectivity, model development, data serving, performance, and issue resolution.

Depending on where you are starting from, you may enter this path at a different point.

## Authorize

Complete access setup before configuring a gateway or deploying a Data Product.

Configure Unity Catalog roles, grants, and DataOS access in [Permissions and grants](permissions-and-grants.md).

## Connect

This is the first hands-on step after access provisioning.

For direct and depot connections, state-store setup, and deployment guidance, see [Connect to Databricks](connect-to-databricks.md).

## Build models

Choose a model strategy after validating the gateway connection.

Databricks materialization maps Vulcan model kinds to native Delta Lake operations. It also covers identifier casing, cross-catalog models, and lifecycle DDL.

See [Materialization behavior](materialization-behavior.md) for the complete reference and examples.

### Engine-native feature support

After core models work, add Databricks capabilities where they strengthen the Data Product.

| Databricks feature               | Vulcan pattern                                                                             |
| -------------------------------- | ------------------------------------------------------------------------------------------ |
| SQL warehouse                    | `connection.http_path` plus PAT (primary execution path).                                  |
| UC catalog (existing)            | `connection.catalog`; Vulcan creates schemas inside it.                                    |
| Managed Delta table              | kind `FULL` and incrementals.                                                              |
| Delta table properties / Z-order | `ALTER TABLE … SET TBLPROPERTIES` or `OPTIMIZE … ZORDER BY` in guarded `post_statements`.  |
| SQL UDF (inline)                 | `CREATE OR REPLACE FUNCTION` in `pre_statements`.                                          |
| Identity column                  | `GENERATED ALWAYS AS IDENTITY` in model DDL.                                               |
| UC row filters / column masks    | Enforced at query time by UC; test queries with the PAT principal's effective permissions. |

#### Not supported

Vulcan does not manage these Databricks infrastructure and workspace features:

* SQL warehouse creation, resizing, and auto-stop.
* All-purpose clusters as the default execution environment.
* Delta Live Tables, streaming tables, Unity Catalog catalog creation, Delta Sharing, MLflow, and Feature Store.

Publish output from these features as a Delta table. Then declare it as an input.

## Serve

### Endpoints

Use endpoints to make deployed Data Product data available to consumers.

Every Data Product on Databricks gets REST, GraphQL, and MySQL-wire endpoints. All push down to the same SQL warehouse, so latency is identical across protocols; the endpoint layer adds roughly 1.5 to 3 seconds (validate in your stack, since warehouse tier affects it). Result sets up to about 50,000 rows are buffered in API memory; keep `api.limit.memory` at 3 GiB and never below 1.5 GiB.

### Metadata scanning and catalog

DataOS scans Unity Catalog `information_schema` (real-time structural metadata) and Databricks system tables (query history and lineage; lag varies by workspace tier, with serverless system tables near real time and classic lagging minutes to hours). Use a read-only scanner principal separate from the Vulcan service role:

```sql
GRANT USE CATALOG ON CATALOG <your_catalog> TO `<scanner_principal>`;
GRANT USE SCHEMA ON ALL SCHEMAS IN CATALOG <your_catalog> TO `<scanner_principal>`;
GRANT SELECT ON ALL TABLES IN CATALOG <your_catalog> TO `<scanner_principal>`;
GRANT USE CATALOG ON CATALOG system TO `<scanner_principal>`;
GRANT SELECT ON ALL TABLES IN CATALOG system TO `<scanner_principal>`;
```

Lineage is computed from parsed view definitions, `MERGE` / `INSERT INTO SELECT` / `CTAS` statements, and Vulcan's own SQL parse. The scanner runs every 6 to 12 hours (configurable).

## Operate safely

Set workload limits before scaling consumers or production schedules.

For warehouse sizing, concurrency, cost controls, and planning baselines, see [Limits & Performance](limits-and-performance.md).

## Troubleshooting

Use focused recovery guidance when a connection, warehouse, or state-store failure occurs.

For failures, health checks, and recovery procedures, see [Troubleshooting](troubleshooting-databricks.md).

### Before production

Confirm these checks before opening the Data Product to production users:

* Validate least-privilege Unity Catalog and DataOS grants.
* Verify the gateway, state store, and warehouse configuration.
* Set concurrency, connection, and recovery limits for expected workloads.

## Full implementation example

Use this complete Databricks Data Product as a production-shaped starting point.

{% file src="../../.gitbook/assets/databricks-data-product.zip" %}

## Related

* [Engine guide overview](../) for the cross-engine rules.
