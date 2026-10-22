---
description: >-
  Confirm Trino catalog compatibility, model support, and view security before
  deployment.
---

# Capabilities and limitations

## Capabilities and limitations

Use this page to confirm that your Trino catalogs and models work with Vulcan.

### Views and catalogs

Views are supported only when the catalog supports them. Iceberg catalogs must use an `iceberg.catalog.type` that supports views:

* `hive_metastore`
* `glue`
* `rest`

The `jdbc` and native `nessie` catalog types do not support views. They are incompatible with Vulcan. Vulcan's virtual layer is built from views.

DataOS lakehouse depots generate an Iceberg connector using REST and OAuth2. Views work on the standard depot path. Use Nessie only through REST, never through the native catalog type.

Hive-backed catalogs require these settings:

```properties
hive.allow-drop-table=true
hive.allow-add-column=true
hive.allow-drop-column=true
hive.allow-rename-table=true
hive.allow-rename-column=true
hive.metastore-cache-ttl=0s
```

### View limitations and security

Materialized views are not supported.

Secure views are not supported. `virtual_properties (creatable_type = SECURE)` is a Snowflake-only feature. Vulcan passes `SECURE` through unchanged. The Trino coordinator then receives `CREATE SECURE VIEW` and returns a syntax error.

Vulcan does not validate this setting for Trino. The error appears during apply, not during plan.

A model definition cannot select Trino's `SECURITY DEFINER` or `SECURITY INVOKER` option. Vulcan-created Trino views run with definer semantics. They read with the Vulcan service principal's privileges, not the querying user's privileges.

Do not use a Trino view as an access-control boundary. Enforce access through Trino access control, DataOS policies, and depot `purpose: query` credentials.

### Model and catalog limitations

Python models are not supported on Trino.

`INCREMENTAL_BY_PARTITION` is not supported on Postgres catalogs. Use `FULL` or `VIEW` instead.

Databricks catalogs are read-only. They use Iceberg REST against Unity Catalog. Writing to Databricks is not supported in this release.
