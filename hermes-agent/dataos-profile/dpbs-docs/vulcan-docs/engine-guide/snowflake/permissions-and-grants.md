---
description: >-
  Configure required Snowflake roles, grants, and DataOS access for Vulcan
  deployments.
---

# Permissions and grants

This is the authorize stage: the step before you touch a gateway config or write a model. Configure Snowflake and DataOS access before you deploy a Vulcan Data Product using Snowflake. Use separate administrative, service, and consumer roles.

## Snowflake-side permissions and grants

Three roles are required, each with a distinct scope. Do not collapse them into one.

| Role                | Who holds it                 | Purpose                                                                                    |
| ------------------- | ---------------------------- | ------------------------------------------------------------------------------------------ |
| Admin role          | Snowflake account admin      | Provisions warehouses, creates resource monitors, manages masking and row access policies. |
| Vulcan service role | The user Vulcan connects as  | Runs models, creates and modifies tables and schemas in the target database.               |
| Consumer role       | BI users, endpoint consumers | Reads data via Vulcan endpoints; no write access.                                          |

### Admin role: one-time setup

Run as `SYSADMIN` or `ACCOUNTADMIN`.

```sql
-- Create warehouse
CREATE WAREHOUSE vulcan_wh
  WITH WAREHOUSE_SIZE = 'MEDIUM'
       AUTO_SUSPEND = 60
       AUTO_RESUME = TRUE;

-- Attach resource monitor (required before production)
ALTER WAREHOUSE vulcan_wh SET RESOURCE_MONITOR = vulcan_monthly_cap;
```

### Vulcan service role: minimum grants

```sql
-- Warehouse access
GRANT USAGE ON WAREHOUSE <wh> TO ROLE <vulcan_role>;

-- Database access
GRANT USAGE ON DATABASE <db> TO ROLE <vulcan_role>;

-- Create objects (required for model materialization)
GRANT CREATE SCHEMA ON DATABASE <db> TO ROLE <vulcan_role>;
GRANT USAGE, CREATE TABLE, CREATE VIEW
  ON FUTURE SCHEMAS IN DATABASE <db> TO ROLE <vulcan_role>;

-- Key-pair auth on the user
ALTER USER <vulcan_user> SET RSA_PUBLIC_KEY = '<public_key>';

-- Bind role to user
GRANT ROLE <vulcan_role> TO USER <vulcan_user>;
```

### Consumer role: read-only grants

```sql
GRANT USAGE ON DATABASE <db> TO ROLE <consumer_role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <consumer_role>;
GRANT SELECT ON ALL TABLES IN SCHEMA <db>.<schema> TO ROLE <consumer_role>;
GRANT SELECT ON FUTURE TABLES IN SCHEMA <db>.<schema> TO ROLE <consumer_role>;
```

### Source schema versus target schema

Snowflake access in DataOS splits into two areas. Grant read-only access on every source schema Vulcan reads from, and managed access on the schema where Vulcan materializes output.

| Area                              | Purpose                                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Source schema (read-only)         | Dataset discovery, profiling, data quality checks, semantic querying, reading upstream tables during model builds. |
| Target schema (managed by Vulcan) | Tables and views created and updated by Vulcan during materialization.                                             |

Source schema grants (read-only):

```sql
GRANT USAGE ON WAREHOUSE <WAREHOUSE_NAME> TO ROLE <DATAOS_ROLE>;
GRANT USAGE ON DATABASE <DATABASE_NAME> TO ROLE <DATAOS_ROLE>;
GRANT USAGE ON SCHEMA <DATABASE_NAME>.<SOURCE_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT SELECT ON ALL TABLES IN SCHEMA <DATABASE_NAME>.<SOURCE_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT SELECT ON FUTURE TABLES IN SCHEMA <DATABASE_NAME>.<SOURCE_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT SELECT ON ALL VIEWS IN SCHEMA <DATABASE_NAME>.<SOURCE_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA <DATABASE_NAME>.<SOURCE_SCHEMA> TO ROLE <DATAOS_ROLE>;
```

Target schema grants (managed by Vulcan):

```sql
GRANT CREATE SCHEMA ON DATABASE <DATABASE_NAME> TO ROLE <DATAOS_ROLE>;
GRANT USAGE ON SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT CREATE TABLE ON SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT CREATE VIEW ON SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
  ON ALL TABLES IN SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA>
  TO ROLE <DATAOS_ROLE>;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
  ON FUTURE TABLES IN SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA>
  TO ROLE <DATAOS_ROLE>;
GRANT SELECT ON ALL VIEWS IN SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA> TO ROLE <DATAOS_ROLE>;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA> TO ROLE <DATAOS_ROLE>;
```

Why each write privilege is needed:

* `DELETE` is used for incremental rebuilds. Vulcan deletes an existing partition or time slice, then inserts refreshed rows. Grant it only on Vulcan-managed target tables.
* `TRUNCATE` is used for full refreshes, overwrite-style rebuilds, and complete table regeneration.
* `OWNERSHIP` is needed only when DataOS manages the target schema lifecycle, including `ALTER`, `REPLACE`, and `DROP`:

```sql
CREATE SCHEMA IF NOT EXISTS <DATABASE_NAME>.<TARGET_SCHEMA>;
GRANT OWNERSHIP ON SCHEMA <DATABASE_NAME>.<TARGET_SCHEMA>
  TO ROLE <DATAOS_ROLE>
  COPY CURRENT GRANTS;
```

### Additional grants by feature

| Feature                    | Additional grant                                                                               | Edition     |
| -------------------------- | ---------------------------------------------------------------------------------------------- | ----------- |
| Read Snowflake sample data | `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE_SAMPLE_DATA TO ROLE <vulcan_role>`            | Standard+   |
| Masking policies           | `GRANT CREATE MASKING POLICY ON SCHEMA <db>.<schema> ...` plus `APPLY MASKING POLICY ON TABLE` | Enterprise+ |
| Row access policies        | `GRANT CREATE ROW ACCESS POLICY ON SCHEMA <db>.<schema> ...`                                   | Enterprise+ |
| Snowpark external access   | `GRANT USAGE ON INTEGRATION <integration_name> TO ROLE <vulcan_role>`                          | Standard+   |
| Dynamic Tables             | `GRANT CREATE DYNAMIC TABLE ON SCHEMA <db>.<schema> ...`                                       | Enterprise+ |

## DataOS permissions

Provision these permissions before you create and deploy Data Products:

| **Permission**                                                   | **What it Allows**                                                                                                                                                                                                      | **Granted By**                                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Tenant Access**                                                | Build and manage Data Products within your tenant.                                                                                                                                                                      | Tenant Admin                                                             |
| **`roles:id:data-dev`** _(or your tenant's equivalent role tag)_ | Create and apply Vulcan resources. Verify your role using `dataos-ctl user get` (check the **TAGS** column).                                                                                                            | Tenant Admin                                                             |
| **`depot:rw:<snowflake-depot-name>`**                            | Read and write access to the Snowflake depot.                                                                                                                                                                           | Tenant Admin or Data Admin                                               |
| **`depot:r:<snowflake-depot-name>`**                             | Read-only access to the Snowflake depot (for consumers).                                                                                                                                                                | Tenant Admin or Data Admin                                               |
| **Can Use** _(Compute, Depots, Secrets)_                         | Allows you to actually use Compute, Depots, and Secrets. **Note:** Resource access is deny-by-default. Even if you have a role tag or depot permission, you also need **Can Use** to use the resource.                  | Tenant Admin or Data Admin                                               |
| **`git-sync` Secret**                                            | Allows Vulcan to pull model code from Git using credentials stored in a Secret. Request a **git-sync Secret**, not raw Git credentials. If you create the Secret yourself, you still need **Can Use** permission on it. | Tenant Admin, Data Admin, or the Secret owner (with **Can Use** granted) |

{% hint style="info" %}
Run `dataos-ctl get depot` to confirm your read access before you start. If the Snowflake depot is missing, request `depot:r` from your operator.
{% endhint %}

### Next step

Continue to [connect-to-snowflake.md](connect-to-snowflake.md "mention") to configure and validate the gateway.
