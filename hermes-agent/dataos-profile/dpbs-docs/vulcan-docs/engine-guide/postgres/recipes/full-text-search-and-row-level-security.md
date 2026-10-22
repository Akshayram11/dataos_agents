---
description: >-
  Build PostgreSQL search and access controls with full-text search and
  row-level security.
---

# Full-Text Search and Row-Level Security

## Overview

This recipe demonstrates how to build postgres-security-demo, a Data Product that leverages two PostgreSQL-native capabilities: full-text search and Row-Level Security (RLS). It uses a generated tsvector column to enable efficient free-text search with plainto\_tsquery, and applies native RLS policies to control row-level access based on user roles. These features are specific to PostgreSQL.

{% hint style="info" %}
**Prerequisites**

* A reachable Postgres instance, with `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USERNAME`, `POSTGRES_PASSWORD` exported as environment variables (the gateway reads them via `env_var(...)`)
* `raw.customers` and `raw.orders` must already exist and be populated. This project only creates `raw`/`staging`/`marts` schemas in `before_all`; it doesn't seed the raw tables itself.
* A role that can `CREATE ROLE` (for the `east_user` demo role created in `before_all`) and can `ENABLE ROW LEVEL SECURITY` / `CREATE POLICY` on the target table (table owner or superuser)
{% endhint %}

## Steps

{% stepper %}
{% step %}
### Configure the Postgres engine connection

```yaml
gateways:
  default:
    connection:
      type: postgres
      host: "{{ env_var('POSTGRES_HOST') }}"
      port: "{{ env_var('POSTGRES_PORT', '5432') }}"
      database: "{{ env_var('POSTGRES_DB', 'postgres') }}"
      user: "{{ env_var('POSTGRES_USERNAME') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"

    state_connection:
      type: postgres
      host: "{{ env_var('STATESTORE_HOST', default='statestore') }}"
      port: "{{ env_var('STATESTORE_PORT', default='5432') }}"
      database: "{{ env_var('STATESTORE_DATABASE', default='statestore') }}"
      user: "{{ env_var('STATESTORE_USER', default='vulcan') }}"
      password: "{{ env_var('STATESTORE_PASSWORD', default='vulcan') }}"

    state_schema: postgres_security_demo_state

model_defaults:
  dialect: postgres
  start: "2024-01-01"
  cron: "@daily"
```

Shown here with the casing fixed (`state_connection`, `state_schema`, `model_defaults`). This is the shape every other Postgres/Snowflake config example in this engagement uses. Postgres also folds unquoted identifiers to lowercase. This is the opposite of Snowflake and Spark's UPPERCASE convention. Every model and column name below is deliberately lowercase for that reason.
{% endstep %}

{% step %}
### Bootstrap the schemas and the RLS test role

`before_all` creates the three schemas this project uses and a demo role for testing row-level security later:

```yaml
before_all:
  - CREATE SCHEMA IF NOT EXISTS raw;
  - CREATE SCHEMA IF NOT EXISTS staging;
  - CREATE SCHEMA IF NOT EXISTS marts;

  - |
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'east_user'
      ) THEN
        CREATE ROLE east_user LOGIN PASSWORD 'east123';
      END IF;
    END
    $$;
```

This `DO $$ ... $$` block is anonymous PL/pgSQL, which Vulcan's parser can't semantically interpret. Expect a harmless warning like `'DO $$ ...' could not be semantically understood` in the logs. The block still runs verbatim; silence the noise with `vulcan --ignore-warnings` if it's distracting.
{% endstep %}

{% step %}
### Build the full-text search mart

```sql
MODEL (
  name marts.customer_search,
  kind FULL,
  grains [customer_id]
);

SELECT
  customer_id,
  customer_name,
  region,
  signup_date,
  to_tsvector(
    'english',
    customer_name || ' ' || region
  ) AS search_vector
FROM staging.customers;
```

`to_tsvector` turns `customer_name || ' ' || region` into a searchable document; `plainto_tsquery` (used in step 6) matches against it with `@@`. This model builds `search_vector` fresh every run since it's `kind FULL`. There is no separate `GENERATED ALWAYS AS` column to keep in sync.

{% hint style="warning" %}
The documented pattern for Postgres full-text search is `tsvector` plus a GIN index. This model has the `tsvector` but no index. It's correct as written, just unindexed, so every `@@` match does a sequential scan. Fine for a demo-sized table; add a GIN index (see Troubleshooting) before treating this as a production pattern.
{% endhint %}
{% endstep %}

{% step %}
### Build the row-level security mart, with the table name fixed

```sql
MODEL (
  name marts.secure_orders,
  kind FULL,
  grains [order_id]
);

SELECT
  o.order_id,
  o.customer_id,
  c.region,
  o.amount,
  o.order_date,
  o.status
FROM staging.orders o
JOIN staging.customers c
  ON o.customer_id = c.customer_id;

@IF(@runtime_stage = 'evaluating',
  ALTER TABLE staging.customers ENABLE ROW LEVEL SECURITY
);

@IF(@runtime_stage = 'evaluating',
  CREATE POLICY east_region_policy
  ON staging.customers
  FOR SELECT
  USING (region = 'East')
);
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
### Verify in Postgres

Vulcan's run history confirms the models applied. It doesn't confirm the search vector matches correctly or that RLS actually restricts rows. Connect directly and check both.

**Connect:**

```bash
PGPASSWORD="<password>" psql \
  -h <host> \
  -p 5432 \
  -U postgres \
  -d postgres
```

**Confirm the full-text search mart exists and holds data:**

```sql
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_name = 'customer_search';

SELECT *
FROM marts.customer_search
LIMIT 5;
```

**Test the search vector directly:**

```sql
SELECT customer_name, region
FROM marts.customer_search
WHERE search_vector @@ plainto_tsquery('english', 'East');
```

Swap `'East'` for a real region or customer-name fragment from your own `raw.customers` data. The exact rows returned depend on what you seeded.

**Confirm RLS is actually enabled:**

```sql
SELECT relrowsecurity
FROM pg_class c
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = 'staging'
AND c.relname = 'customers';

SELECT *
FROM pg_policies
WHERE schemaname = 'staging'
AND tablename = 'customers';
```

`relrowsecurity` should be `true`, and `pg_policies` should return one row for `east_region_policy`. An empty result on either means step 4's DDL never ran. See Troubleshooting.

**Test the policy by switching roles:** The table owner and superusers bypass RLS by default, so testing as your own admin role won't show anything restricted.

```sql
GRANT USAGE ON SCHEMA staging TO east_user;
GRANT SELECT ON staging.customers TO east_user;

SET ROLE east_user;

SELECT customer_name, region
FROM staging.customers;

RESET ROLE;
```

Expected: as `east_user`, only rows where `region = 'East'` come back. As the table owner or a superuser, every row comes back regardless of the policy. That's expected Postgres behavior, not a bug. If you need the policy enforced even for the owner, add:

```sql
ALTER TABLE staging.customers FORCE ROW LEVEL SECURITY;
```
{% endstep %}
{% endstepper %}

## Troubleshooting

| Symptom                                                                                              | Cause                                                                                           | Resolution                                                                                                                                 |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `vulcan plan` appears to run the `ALTER TABLE` / `CREATE POLICY` DDL during a dry-run                | Lifecycle DDL not guarded                                                                       | Wrap both statements in `@IF(@runtime_stage = 'evaluating', ...)`, as shown in step 4                                                      |
| `SET ROLE east_user` then querying `staging.customers` returns every row, not just `region = 'East'` | You're connected as the table owner or a superuser, which bypasses RLS by default               | Run `ALTER TABLE staging.customers FORCE ROW LEVEL SECURITY;` if the policy must apply even to the owner                                   |
| `east_user` gets a permission error instead of a filtered result                                     | Missing `GRANT USAGE ON SCHEMA staging` or `GRANT SELECT ON staging.customers`                  | Run both grants in step 6 before switching roles                                                                                           |
| Full-text queries feel slow on a larger table                                                        | No index on `search_vector`. The model builds the `tsvector` but not the accompanying GIN index | Add `CREATE INDEX IF NOT EXISTS ix_customer_search_vector ON marts.customer_search USING GIN (search_vector);` as a guarded post-statement |

## References

* [PostgreSQL engine guide](../): Lowercase identifiers, lifecycle DDL, and engine-native features.
* [Model statements](../../../models/data-models/statements.md): Post-statements and the `@IF(@runtime_stage, ...)` guard.
* [Model kinds: FULL](../../../models/data-models/model-kinds.md#full): Both models use portable `kind FULL`; only the SQL and `staging.customers` DDL are PostgreSQL-specific.
