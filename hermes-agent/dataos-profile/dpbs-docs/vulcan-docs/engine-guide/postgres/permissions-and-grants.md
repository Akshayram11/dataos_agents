---
description: >-
  Provision PostgreSQL and DataOS access before configuring or deploying a Data
  Product.
---

# Permissions and grants

This is the authorize stage. Complete it before configuring a gateway or writing models.

## Postgres-side permissions and grants

Provision access before configuring a gateway. Three roles are required, each with a distinct scope. Do not collapse them into one.

| Role                | Who holds it                           | Purpose                                                                      |
| ------------------- | -------------------------------------- | ---------------------------------------------------------------------------- |
| Admin role          | PostgreSQL superuser / DBA             | Creates databases, installs extensions, grants privileges.                   |
| Vulcan service role | The role whose credentials Vulcan uses | Runs models, creates and modifies schemas and tables in the target database. |
| Consumer role       | BI users, endpoint consumers           | Read-only access to Data Product tables.                                     |

Vulcan needs `CREATE` on the target database (for schemas), `CREATE` on schemas (for tables and views), `USAGE` on schemas, and `SELECT`, `INSERT`, `UPDATE`, `DELETE` on tables. Run minimum grants as a superuser or database owner:

```sql
-- Target database. Vulcan materializes here; the database must already exist.
GRANT CONNECT ON DATABASE warehouse TO vulcan;
GRANT CREATE ON DATABASE warehouse TO vulcan;

-- Source data landed by Nilus, seeds, or another ingestion path.
GRANT USAGE ON SCHEMA raw TO vulcan;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO vulcan;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO vulcan;
```

Consumer role (read-only):

```sql
GRANT CONNECT ON DATABASE warehouse TO consumer;
GRANT USAGE ON SCHEMA sales TO consumer;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO consumer;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT SELECT ON TABLES TO consumer;
```

Verify grants in `psql`:

```sql
SELECT current_user, current_database();
\dn
\dp raw.*
```

{% hint style="warning" %}
`connection.database` must exist before `vulcan plan`. PostgreSQL has no catalog tier: use `database.schema.table`, and schemas referenced by models are created automatically when privileges allow.
{% endhint %}

## DataOS permissions

Provision these permissions before working with Data Products:

| **Permission**                                                   | **What it Allows**                                                                                                                                                                                                      | **Granted By**                                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Tenant Access**                                                | Build and manage Data Products within your tenant.                                                                                                                                                                      | Tenant Admin                                                             |
| **`roles:id:data-dev`** _(or your tenant's equivalent role tag)_ | Create and apply Vulcan resources. Verify your role using `dataos-ctl user get` (check the **TAGS** column).                                                                                                            | Tenant Admin                                                             |
| **`depot:rw:<postgres-depot-name>`**                             | Read and write access to the PostgreSQL depot.                                                                                                                                                                          | Tenant Admin or Data Admin                                               |
| **`depot:r:<postgres-depot-name>`**                              | Read-only access to the PostgreSQL depot (for consumers).                                                                                                                                                               | Tenant Admin or Data Admin                                               |
| **Can Use** _(Compute, Depots, Secrets)_                         | Allows you to actually use Compute, Depots, and Secrets. **Note:** Resource access is deny-by-default. Even if you have a role tag or depot permission, you also need **Can Use** to use the resource.                  | Tenant Admin or Data Admin                                               |
| **`git-sync` Secret**                                            | Allows Vulcan to pull model code from Git using credentials stored in a Secret. Request a **git-sync Secret**, not raw Git credentials. If you create the Secret yourself, you still need **Can Use** permission on it. | Tenant Admin, Data Admin, or the Secret owner (with **Can Use** granted) |

Run `dataos-ctl get depot` to confirm your read access before you start. If the PostgreSQL depot is missing, request `depot:r` from your operator.

### Next step

After access is ready, configure the gateway in [connect-to-postgres.md](connect-to-postgres.md "mention").
