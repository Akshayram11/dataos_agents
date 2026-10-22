---
description: >-
  Create a Snowflake Data Product with a Dynamic Table, column masking, and row
  access policies using Vulcan.
---

# Dynamic Tables and Access Policies

## Overview

This recipe demonstrates how to build a Snowflake-powered Data Product (sf-dp) using Vulcan. It covers two aspects:

1. Configure the Snowflake engine by setting up the gateway connection, credentials, warehouse, database, role, and `model_defaults.dialect`. These settings enable Vulcan to connect to and run models on Snowflake.
2. Leverage Snowflake-native capabilities once the connection is established. The recipe includes: `sales.customer_email_domains` as a Dynamic Table, which Snowflake refreshes automatically without Vulcan orchestration. `sales.customer_profile` as a `FULL` model with native column masking policies on `EMAIL` and `CUSTOMER_NAME`, and a native row access policy on `REGION_ID`.

{% hint style="info" %}
**Prerequisites**

* A Snowflake account, a warehouse, and a user/role Vulcan can connect as (key-pair, username/password, or another supported [authentication method](../))
* Snowflake Enterprise edition or higher. Dynamic Tables are available in standard editions, but masking policies and row access policies are Enterprise+.
* That role needs `CREATE MASKING POLICY`, `CREATE ROW ACCESS POLICY`, and `CREATE DYNAMIC TABLE` privileges on the target schema (the project as shipped runs as `ACCOUNTADMIN`, which has all three)
* A reachable warehouse
* `config.yaml` sets `after_authorize: "plugins.policies.auth:resolve_user_groups"`, but no `plugins/` module ships in this bundle. If `vulcan plan` fails on that import, comment out `after_authorize` before continuing; it isn't required for the capabilities below.
{% endhint %}

## Steps

{% stepper %}
{% step %}
### Configure the Snowflake engine connection

Before any model or policy exists, `config.yaml` has to point Vulcan at Snowflake. This step makes it a Snowflake Data Product. Everything after it is what you can build once the connection is live:

```yaml
gateways:
  default:
    connection:
      type: snowflake
      account: <org>-<account>          # from your Snowflake console URL
      user: <vulcan_user>
      private_key_path: ./snowflake_key.p8
      private_key_passphrase: <YOUR_PASSPHRASE>
      warehouse: <warehouse>
      database: <database>
      role: <role>
    state_connection:
      type: duckdb                      # local dev only
      database: ./state.duckdb

model_defaults:
  dialect: snowflake
  start: '2025-01-01'
```

`type: snowflake` plus `model_defaults.dialect: snowflake` compile every model below against Snowflake's SQL dialect instead of a generic one. `role` matters beyond permissions. It is what `CURRENT_ROLE()` returns inside the masking and row access policies in steps 3 and 4, so the policies must check that role.
{% endstep %}

{% step %}
### Set up the initial source table and the policy definitions

`config.yaml`'s `before_all` creates the schemas, seeds a source table, and defines all three native policies up front. It runs once, before any model, so the policies exist when a model tries to attach them:

```yaml
before_all:
  - USE DATABASE DEMO_DB;
  - CREATE SCHEMA IF NOT EXISTS RAW;
  - CREATE SCHEMA IF NOT EXISTS SALES;
  - USE SCHEMA SALES;

  # Source table (seeded with sample rows in the same block)
  - |
    CREATE TABLE IF NOT EXISTS RAW.RAW_CUSTOMERS (
      CUSTOMER_ID INTEGER, CUSTOMER_NAME STRING, EMAIL STRING,
      REGION_ID INTEGER, REGION_NAME STRING, CUSTOMER_SEGMENT STRING,
      LAST_ORDER_DATE DATE, TOTAL_ORDERS INTEGER, TOTAL_SPEND NUMBER(12,2)
    );

  # Email masking policy
  - |
    CREATE OR REPLACE MASKING POLICY SALES.email_mask
    AS (VAL STRING) RETURNS STRING ->
      CASE WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'SYSADMIN') THEN VAL ELSE '********' END;

  # Customer name masking policy
  - |
    CREATE OR REPLACE MASKING POLICY SALES.customer_name_mask
    AS (VAL STRING) RETURNS STRING ->
      CASE WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'SYSADMIN') THEN VAL ELSE '********' END;

  # Row access policy — differentiates by role, not just service-role-vs-everyone
  - |
    CREATE OR REPLACE ROW ACCESS POLICY SALES.region_access
    AS (REGION_ID NUMBER) RETURNS BOOLEAN ->
      CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'SYSADMIN') THEN TRUE
        WHEN CURRENT_ROLE() = 'EAST_ROLE' THEN REGION_ID = 1
        WHEN CURRENT_ROLE() = 'WEST_ROLE' THEN REGION_ID = 2
        ELSE FALSE
      END;
```

Defining the policies here, rather than inline in a model file, means both downstream models can reference them by name without either one owning their definition.
{% endstep %}

{% step %}
### Create the Dynamic Table

`models/sales/customer_email_domains.sql` is the first capability. `kind MANAGED` plus `physical_properties` make this a Dynamic Table instead of a portable `FULL` model:

```sql
MODEL (
  name sales.customer_email_domains,
  kind MANAGED,
  grains [CUSTOMER_ID],
  description '
    Demonstrates Snowflake Dynamic Tables by automatically
    maintaining customer email domains.
  ',
  physical_properties (
    target_lag = '5 minutes',
    warehouse = 'COMPUTE_WH'
  )
);

SELECT
  CUSTOMER_ID,
  CUSTOMER_NAME,
  EMAIL,
  SPLIT_PART(LOWER(EMAIL), '@', 2) AS EMAIL_DOMAIN,
  REGION_NAME
FROM raw.raw_customers;
```
{% endstep %}

{% step %}
### Create the profile model and attach masking + row access

`models/sales/customer_profile.sql` is a plain `FULL` model; the two capabilities are the `ALTER TABLE` statements that run after it:

```sql
MODEL (
  name sales.customer_profile,
  kind FULL,
  grains [CUSTOMER_ID],
  description '
    Customer profile enriched with Snowflake native
    masking policies and row access policies.
  '
);

SELECT
  CUSTOMER_ID, CUSTOMER_NAME, EMAIL, REGION_ID, REGION_NAME,
  CUSTOMER_SEGMENT, LAST_ORDER_DATE, TOTAL_ORDERS, TOTAL_SPEND
FROM RAW.RAW_CUSTOMERS;

ALTER TABLE SALES.CUSTOMER_PROFILE
MODIFY COLUMN EMAIL SET MASKING POLICY SALES.email_mask;

ALTER TABLE SALES.CUSTOMER_PROFILE
MODIFY COLUMN CUSTOMER_NAME SET MASKING POLICY SALES.customer_name_mask;

ALTER TABLE SALES.CUSTOMER_PROFILE
ADD ROW ACCESS POLICY SALES.region_access ON (REGION_ID);
```
{% endstep %}

{% step %}
### Apply and run

```bash
vulcan plan
vulcan run
```
{% endstep %}

{% step %}
### Verify the three capabilities directly in Snowflake

Vulcan's run history only confirms the models applied. It does not confirm Snowflake completed what steps 3 and 4 requested. Connect directly and check each capability at the source.

**Connect:**

```bash
snowsql \
  -a <account_identifier> \
  -u <username> \
  -r ACCOUNTADMIN \
  -w SNOWFLAKE_LEARNING_WH \
  -d DEMO_DB \
  -s SALES \
  --private-key-path <path_to_private_key>
```

If the warehouse has been idle, resume it explicitly before querying:

```sql
ALTER WAREHOUSE SNOWFLAKE_LEARNING_WH RESUME;
```

**Confirm the objects exist:**

```sql
SHOW TABLES IN SCHEMA SALES;
SHOW DYNAMIC TABLES IN SCHEMA SALES;
SHOW MASKING POLICIES IN SCHEMA SALES;
SHOW ROW ACCESS POLICIES IN SCHEMA SALES;
```

You should see `CUSTOMER_PROFILE` as a table, `CUSTOMER_EMAIL_DOMAINS` as a dynamic table, and `EMAIL_MASK` / `CUSTOMER_NAME_MASK` / `REGION_ACCESS` in their respective policy lists.

**Confirm the policies are actually attached, not just defined:** A policy can exist without being applied to anything.

```sql
SELECT * FROM TABLE(
  INFORMATION_SCHEMA.POLICY_REFERENCES(POLICY_NAME => 'DEMO_DB.SALES.EMAIL_MASK')
);

SELECT * FROM TABLE(
  INFORMATION_SCHEMA.POLICY_REFERENCES(POLICY_NAME => 'DEMO_DB.SALES.CUSTOMER_NAME_MASK')
);

SELECT * FROM TABLE(
  INFORMATION_SCHEMA.POLICY_REFERENCES(POLICY_NAME => 'DEMO_DB.SALES.REGION_ACCESS')
);
```

Each should return a row with `REF_ENTITY_NAME = CUSTOMER_PROFILE`. An empty result means step 4's `ALTER TABLE` statements defined the policy reference, but the attachment never took. See Troubleshooting below.

**Test masking and row access together, by switching role.** The project's policies exempt only `ACCOUNTADMIN`/`SYSADMIN`, and the row access policy only recognizes `EAST_ROLE`/`WEST_ROLE`. Neither role is created anywhere in this project, so create them first:

```sql
USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS EAST_ROLE;
CREATE ROLE IF NOT EXISTS WEST_ROLE;

GRANT ROLE EAST_ROLE TO USER <your_user>;
GRANT USAGE ON WAREHOUSE SNOWFLAKE_LEARNING_WH TO ROLE EAST_ROLE;
GRANT USAGE ON DATABASE DEMO_DB TO ROLE EAST_ROLE;
GRANT USAGE ON SCHEMA DEMO_DB.SALES TO ROLE EAST_ROLE;
GRANT SELECT ON TABLE DEMO_DB.SALES.CUSTOMER_PROFILE TO ROLE EAST_ROLE;
-- repeat the last four GRANTs for WEST_ROLE
```

Then, as your own user:

```sql
USE ROLE EAST_ROLE;

SELECT CUSTOMER_ID, CUSTOMER_NAME, EMAIL, REGION_ID
FROM SALES.CUSTOMER_PROFILE;
```

Expected: `CUSTOMER_NAME` and `EMAIL` both return `'********'` (masking policy firing), and only `REGION_ID = 1` rows appear (row access policy firing). `EAST_ROLE` only ever sees region 1 per the policy defined in step 2. Switch to `WEST_ROLE` and only region 2 rows should appear.

Compare against the exempt role:

```sql
USE ROLE ACCOUNTADMIN;

SELECT CUSTOMER_ID, CUSTOMER_NAME, EMAIL, REGION_ID
FROM SALES.CUSTOMER_PROFILE;
```

This should return every row, fully unmasked. `ACCOUNTADMIN` is exempt from both policies.

**Verify the Dynamic Table independently of Vulcan:**

```sql
SELECT * FROM SALES.CUSTOMER_EMAIL_DOMAINS LIMIT 10;

SHOW DYNAMIC TABLES LIKE 'CUSTOMER_EMAIL_DOMAINS' IN SCHEMA SALES;

SELECT *
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
WHERE NAME = 'CUSTOMER_EMAIL_DOMAINS'
ORDER BY REFRESH_START_TIME DESC;
```

If `SHOW DYNAMIC TABLES` reports it `SUSPENDED`, resume it explicitly:

```sql
ALTER DYNAMIC TABLE SALES.CUSTOMER_EMAIL_DOMAINS RESUME;
```

**Cleanup, once you're done with the demo (optional):**

```sql
ALTER TABLE SALES.CUSTOMER_PROFILE MODIFY COLUMN EMAIL UNSET MASKING POLICY;
ALTER TABLE SALES.CUSTOMER_PROFILE MODIFY COLUMN CUSTOMER_NAME UNSET MASKING POLICY;
DROP MASKING POLICY SALES.EMAIL_MASK;
DROP MASKING POLICY SALES.CUSTOMER_NAME_MASK;
DROP ROW ACCESS POLICY SALES.REGION_ACCESS;
```
{% endstep %}
{% endstepper %}

## Troubleshooting

| Symptom                                                      | Cause                                                                                    | Resolution                                                                                                                                              |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vulcan plan`/`vulcan run` can't connect to Snowflake at all | Bad `account`, `private_key_path`, or `private_key_passphrase` in the gateway connection | Verify the account locator matches your Snowflake console URL, and that the key file path and passphrase are correct for the environment Vulcan runs in |
| `vulcan plan` fails on an import of `plugins.policies.auth`  | `after_authorize` in `config.yaml` points at a plugin module this bundle doesn't ship    | Comment out `after_authorize`. It is unrelated to the three capabilities this recipe demonstrates                                                       |

## References

* [Snowflake engine guide: authentication methods](../): Key-pair, username/password, OAuth token, external browser SSO, and Depot-based auth, if step 1's connection needs to look different from the key-pair example shown.
* [Model kinds: MANAGED](../../../models/data-models/model-kinds.md#managed)
* [Model statements: on-virtual-update and post-statements](../../../models/data-models/statements.md)

## Download the complete project

{% file src="../../../.gitbook/assets/sf-dp-sample.zip" %}
