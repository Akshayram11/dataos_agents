---
description: >-
  The full per-engine technical reference for building and running a Data
  Product on each supported Vulcan engine in DataOS.
noIndex: true
---

# Overview

This is the full technical reference for each engine that Vulcan runs against in DataOS. Where the Build section gives you the thin connection config you need to wire a gateway, this guide gives you the depth: authentication and grants, materialization behavior per model kind, local development setups, operational boundaries, performance ceilings, and the failure modes you hit in real projects.

Use this guide when you are building or operating a Data Product and you need to understand how a specific engine behaves, not just how to connect to it. Each page consolidates the engine setup, the runtime behavior, and the troubleshooting reference into one place.

## Who this is for

You are a data-product builder, a data engineer setting up an engine for the first time, or a developer debugging a Data Product. Each page leads with the common path (connect, materialize, deploy) and pushes deep edge cases into clearly marked sections, so you can read the top of a page and stop, or go all the way down when you need to.

## How Vulcan uses an engine

Vulcan transforms data that an ingestion path (such as Nilus) has already landed in your engine. Across every engine, the pattern is the same:

* You connect a gateway to the engine and set `model_defaults.dialect` to match.
* Vulcan compiles your SQL and semantic models to native engine SQL and materializes them as tables and views.
* A serving layer exposes the Data Product through REST, GraphQL, and (where supported) MySQL-wire and Postgres-wire endpoints.
* A scheduled workflow plans and runs the models; a Depot binds the engine credentials to the DataOS resource.

What changes per engine is the connection options, the authentication methods, the supported model kinds, the identifier casing rule, and the operational limits. That is what each page documents.

## Choose an engine

| Engine                                | Adapter type | Use it when                                                                    |
| ------------------------------------- | ------------ | ------------------------------------------------------------------------------ |
| [Snowflake](snowflake/)               | `snowflake`  | You run on a cloud warehouse with separate storage and compute.                |
| [Databricks](databricks/)             | `databricks` | You use Databricks SQL Warehouse, Unity Catalog, and Delta Lake.               |
| [Spark](spark-1/)                     | `spark`      | You run an Iceberg lakehouse on Apache Spark and object storage.               |
| [Postgres](postgres/)                 | `postgres`   | You need a PostgreSQL server for smaller projects or database control.         |
| [Trino](trino-1/)                     | `trino`      | You query data lakes, databases, and object storage with a distributed engine. |
| [SQL Server](sql-server/)             | `mssql`      | You run an existing SQL Server estate or need on-premises T-SQL control.       |
| [Microsoft Fabric](microsoft-fabric/) | `fabric`     | You use Fabric Warehouse with OneLake and Microsoft Entra authentication.      |

## Common rules across engines

Apply these rules when configuring an engine for Vulcan. They cover engine settings, credentials, metadata scanning, and external source definitions.

* In `config.yaml`, set `connection.type` and `model_defaults.dialect` to match the target engine unless you have a specific transpilation need.
* Keep credentials out of `config.yaml`. Use `env_var()` for local environment variables and DataOS secrets for production.
* Set `timezone: UTC` on production schedules, set `endOn` 1 to 2 years out, and use `concurrencyPolicy: Forbid` to prevent overlapping runs.
* Declare externally managed source tables and views in `inputs.yaml`. This lets Vulcan resolve them during linting and lineage generation.
* Use a separate read-only role for the metadata scanning. Do not reuse the Vulcan service role for scanning.

## Related

For the thin connection config and the wiring steps, see the matching Build pages under [Connect engine](https://v2.dataos.info/build/productize/connect-engine).
