---
description: >-
  The full technical reference for building and running a Vulcan Data Product on
  Snowflake, covering connection, grants, materialization, operations,
  performance, and troubleshooting.
noIndex: true
---

# Snowflake

Snowflake is a cloud data warehouse with separated storage and compute. Vulcan runs against Snowflake to manage transformations with version control and gated deployments. This page is the full manual: it covers how you connect, what permissions you need, how each model kind materializes, how to set operational guardrails, and how to recover from the failures you are most likely to hit.

## Decide

### Assess fit

Choose Snowflake when your data already lands in a Snowflake account and governed transformations can run close to it. Snowflake suits elastic, per-query warehouse compute with minimal infrastructure to manage, incremental builds, governed semantic serving, and mixed SQL plus Snowpark Python workloads.

Snowflake is fully supported on Standard, Enterprise, and Business Critical editions. A few features - Dynamic Tables, masking policies, row access policies, and Semantic Views, require Enterprise or higher.

### Supported model kinds

`FULL`, `SEED`, `VIEW`, `INCREMENTAL_BY_TIME_RANGE`, `INCREMENTAL_BY_UNIQUE_KEY`, `INCREMENTAL_BY_PARTITION`, `MANAGED`, and `SCD`

### Engine characteristics

Once the model kinds above cover your workload, this is what you're actually connecting to:

| Property                   | Value                         |
| -------------------------- | ----------------------------- |
| Engine adapter type        | `snowflake`                   |
| Model dialect              | `snowflake`                   |
| Recommended authentication | Key-pair JSON Web Token (JWT) |

Once you choose Snowflake as your Data Product engine, use this guide to explore **Authorize, Connect, Build, Serve, Operate, and Troubleshoot**—covering access, connectivity, model development, data serving, performance, and issue resolution.

Depending on where you are starting from, you may enter this path at a different point.

## Authorize

Access setup is required before gateway configuration.

Configure Snowflake and DataOS access before deployment. See [Permissions and grants](permissions-and-grants.md) for role design, grant templates, and required DataOS permissions.

## Connect

This is the first hands-on step. Configure the gateway, test it locally, and prepare production deployment.

Choose a direct connection or DataOS Depot. For configuration examples, authentication options, and validation steps, see [Connect to Snowflake](connect-to-snowflake.md).

## Build models

Choose a model kind only after the connection validates successfully.

Review [Materialization behavior](materialization-behavior.md) for model-kind mappings, Snowpark implementation, lifecycle SQL, macros, and cross-database models.

### Engine-native feature support

You can drive most Snowflake objects from a Vulcan Data Product through guarded lifecycle SQL. Highlights:

| Feature                                                    | Vulcan pattern                                                                | Edition                                       |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------- |
| Transient / temporary table                                | kind `FULL` + `physical_properties (creatable_type = TRANSIENT \| TEMPORARY)` | Standard+                                     |
| Dynamic Table                                              | kind `MANAGED` + `physical_properties (target_lag, warehouse)`                | Enterprise+                                   |
| Secure view                                                | kind `VIEW` + `virtual_properties (createable_type = SECURE)`                 | Standard+                                     |
| Clustering                                                 | `ALTER TABLE … CLUSTER BY` in guarded `post_statements`                       | Standard+                                     |
| Masking / row access policy                                | `CREATE … POLICY` in `before_all`; apply in `post_statements`                 | Enterprise+                                   |
| Streams, stages, sequences, tasks, UDFs, stored procedures | `CREATE …` in `before_all` / `pre_statements`                                 | Standard+                                     |
| Iceberg table                                              | `CREATE ICEBERG TABLE` in `before_all` (external volume required)             | Standard+                                     |
| Time Travel / Fail-safe                                    | `DATA_RETENTION_TIME_IN_DAYS`; Fail-safe automatic on permanent tables        | Standard (1 day), Enterprise+ (up to 90 days) |

You can also import a Snowflake-native semantic view with `vulcan import_semantic_view` (requires Enterprise and `SELECT` on the view). The generated YAML follows the UPPERCASE rule.

#### Not supported

Vulcan does not support:

* Warehouse creation, resizing, or suspension. Provision warehouses out of band.
* OAuth/SSO for gateway connections.
* Automatic cross-database external-model discovery.
* `MANAGED` models on Standard edition.
* Incremental processing for `VIEW` models.
* Snowpark external network access. A Snowflake admin must create and grant the required external-access integration.

### Recipes

Use [Snowflake recipes](recipes/) for Dynamic Tables, access policies, and Snowpark Python models.

## Serve

### Endpoints

Choose a consumption endpoint and verify catalog coverage for governed access.

Every Data Product on Snowflake gets REST, GraphQL, MySQL-wire, and Postgres-wire endpoints. All four push queries down to the same Snowflake gateway, so latency is identical across protocols. The endpoint layer adds about 1.5 to 2 seconds of overhead on standard queries and 4 to 5 seconds on complex queries. Result sets up to about 50,000 rows are buffered in API memory before streaming, so keep `api.limit.memory` at 3 GiB and never below 1.5 GiB.

### Metadata scanning and catalog

DataOS scans two Snowflake surfaces: `INFORMATION_SCHEMA` (real-time structural metadata) and `SNOWFLAKE.ACCOUNT_USAGE` (lineage, tags, query history, with an approximately 3-hour lag that Snowflake imposes and that is not configurable).

Use a read-only scanner role separate from the Vulcan service role:

```sql
GRANT USAGE ON DATABASE <db> TO ROLE <scanner_role>;
GRANT USAGE ON ALL SCHEMAS IN DATABASE <db> TO ROLE <scanner_role>;
GRANT REFERENCES ON ALL TABLES IN DATABASE <db> TO ROLE <scanner_role>;
GRANT REFERENCES ON FUTURE TABLES IN DATABASE <db> TO ROLE <scanner_role>;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <scanner_role>;
GRANT ROLE <scanner_role> TO USER <scanner_user>;
```

{% hint style="warning" %}
`IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` requires `ACCOUNTADMIN`. Without it, lineage edges, tags, procedures, functions, and Dynamic Table history are not populated.
{% endhint %}

Lineage is computed, not fetched: DataOS parses view definitions, write queries (`MERGE`, `INSERT INTO SELECT`, `CTAS`), stored-procedure child queries, and external-table locations from `ACCOUNT_USAGE.QUERY_HISTORY`. The scanner runs every 6 to 12 hours (configurable). Lineage edges appear up to 3 hours after a query runs; if lineage is missing after a `vulcan apply`, wait or trigger a manual scan.

## Operate safely

Set workload limits before scaling consumers or production schedules.

For compute sizing, concurrency, scheduling, cost controls, and performance baselines, see [Limits & Performance](limits-and-performance.md).

#### Before production

* Confirm least-privilege grants for service, scanner, and consumer roles.
* Validate the gateway with `vulcan migrate` and `vulcan plan`.
* Set warehouse concurrency and connection limits.
* Test recovery procedures before scheduling production workloads.

## Troubleshooting

For common failures, health-check queries, and recovery procedures, see [Troubleshooting Snowflake](troubleshooting.md).

## Full implementation example

Start from a working reference. Use this complete Snowflake Data Product as a production-shaped starting point.

{% file src="../../.gitbook/assets/snowflake-data-product.zip" %}

## Related guides

* [..](../ "mention") — compare shared engine rules and deployment patterns.
