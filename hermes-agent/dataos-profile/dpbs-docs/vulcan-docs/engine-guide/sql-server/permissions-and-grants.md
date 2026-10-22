---
description: >-
  Provision SQL Server and DataOS access before configuring or deploying a Data
  Product.
---

# Permissions and grants

## SQL Server-side permissions and grants

Provision access before configuring a gateway. Three roles are required, each with a distinct scope.

| Role                | Who holds it                    | Purpose                                                            |
| ------------------- | ------------------------------- | ------------------------------------------------------------------ |
| Admin role          | SQL Server sysadmin/DBA         | Creates databases, logins, and grants privileges.                  |
| Vulcan service role | The login Vulcan connects as    | Runs models and manages schemas and tables in the target database. |
| Consumer role       | BI users and endpoint consumers | Reads Data Product tables only.                                    |

Run minimum grants as a sysadmin:

```sql
-- Vulcan service role
CREATE LOGIN vulcan_svc WITH PASSWORD = '<strong-password>';
USE <database>;
CREATE USER vulcan_svc FOR LOGIN vulcan_svc;
ALTER ROLE db_ddladmin ADD MEMBER vulcan_svc;
ALTER ROLE db_datareader ADD MEMBER vulcan_svc;
ALTER ROLE db_datawriter ADD MEMBER vulcan_svc;
GRANT CREATE SCHEMA TO vulcan_svc;
```

Consumer role (read-only):

```sql
CREATE LOGIN vulcan_consumer WITH PASSWORD = '<strong-password>';
USE <database>;
CREATE USER vulcan_consumer FOR LOGIN vulcan_consumer;
ALTER ROLE db_datareader ADD MEMBER vulcan_consumer;
```

Verify grants:

```sql
SELECT dp.name AS principal, r.name AS role
FROM sys.database_role_members m
JOIN sys.database_principals dp ON m.member_principal_id = dp.principal_id
JOIN sys.database_principals r ON m.role_principal_id = r.principal_id;
```

{% hint style="warning" %}
`connection.database` must exist before `vulcan plan`. SQL Server has no `CREATE SCHEMA IF NOT EXISTS` semantics. The adapter creates referenced schemas through guarded DDL when the role has privilege.
{% endhint %}

## DataOS permissions

These permissions are required before you configure or deploy Data Products.

| Permission                                                 | What it allows                                                        | Granted by                                |
| ---------------------------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------- |
| Tenant Access                                              | Build and manage Data Products within your tenant.                    | Tenant Admin                              |
| `roles:id:data-dev` (or your tenant's equivalent role tag) | Create and apply Vulcan resources. Verify with `dataos-ctl user get`. | Tenant Admin                              |
| `depot:rw:<mssql-depot-name>`                              | Read and write access to the SQL Server depot.                        | Tenant Admin or Data Admin                |
| `depot:r:<mssql-depot-name>`                               | Read-only depot access for consumers.                                 | Tenant Admin or Data Admin                |
| Can Use (Compute, Depots, Secrets)                         | Use Compute, Depots, and Secrets. Access is deny-by-default.          | Tenant Admin or Data Admin                |
| git-sync Secret                                            | Pull model code from Git using a Secret.                              | Tenant Admin, Data Admin, or Secret owner |

Run `dataos-ctl get depot` to confirm read access. If the depot is missing, request `depot:r` from your operator.

### Next step

After access is ready, configure and validate the gateway in [connect-to-sql-server.md](connect-to-sql-server.md "mention").
