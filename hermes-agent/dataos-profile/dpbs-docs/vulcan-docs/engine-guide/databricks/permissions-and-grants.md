---
description: Know about Unity Catalog grants and DataOS access for Databricks deployments.
---

# Permissions and grants

This is the authorize stage. Complete it before configuring a gateway or writing models. Configure Unity Catalog and DataOS access before deployment. These grants authorize the gateway, deployment workflow, scanner, and consumers.

## Databricks-side permissions and grants

Three roles are required, each with a distinct scope. Do not collapse them into one.

| Role                | Who holds it                    | Purpose                                             |
| ------------------- | ------------------------------- | --------------------------------------------------- |
| Admin role          | Workspace admin                 | Creates SQL warehouses, UC catalogs, and UC grants. |
| Vulcan service role | PAT principal                   | Runs models and manages target schemas and tables.  |
| Consumer role       | BI users and endpoint consumers | Reads Data Product tables.                          |

Run minimum grants as a workspace admin in the SQL editor. Use the warehouse configured by `http_path`.

```sql
GRANT USE CATALOG ON CATALOG <your_catalog> TO `<principal>`;
GRANT CREATE SCHEMA ON CATALOG <your_catalog> TO `<principal>`;
GRANT CREATE TABLE ON CATALOG <your_catalog> TO `<principal>`;
GRANT CREATE VIEW ON CATALOG <your_catalog> TO `<principal>`;

GRANT USE CATALOG ON CATALOG samples TO `<principal>`;
GRANT USE SCHEMA ON SCHEMA samples.tpch TO `<principal>`;
GRANT SELECT ON SCHEMA samples.tpch TO `<principal>`;
```

Consumer role (read-only):

```sql
GRANT USE CATALOG ON CATALOG <your_catalog> TO `<consumer>`;
GRANT USE SCHEMA ON SCHEMA <your_catalog>.<schema> TO `<consumer>`;
GRANT SELECT ON SCHEMA <your_catalog>.<schema> TO `<consumer>`;
```

Verify grants in the SQL editor (same warehouse as `http_path`):

```sql
SELECT current_user() AS user, current_catalog() AS catalog;
SHOW SCHEMAS IN <your_catalog>;
SHOW TABLES IN samples.tpch;
```

{% hint style="warning" %}
The UC catalog referenced in `connection.catalog` must exist before `vulcan apply`. Vulcan creates schemas and tables inside it; it cannot create the catalog itself. A missing catalog raises `NO_SUCH_CATALOG_EXCEPTION`.
{% endhint %}

## DataOS permissions

These permissions must be provisioned before you create and deploy Data Products:

| **Permission**                                                   | **What it Allows**                                                                                                                                                                                                      | **Granted By**                                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Tenant Access**                                                | Build and manage Data Products within your tenant.                                                                                                                                                                      | Tenant Admin                                                             |
| **`roles:id:data-dev`** _(or your tenant's equivalent role tag)_ | Create and apply Vulcan resources. Verify your role using `dataos-ctl user get` (check the **TAGS** column).                                                                                                            | Tenant Admin                                                             |
| **`depot:rw:<databricks-depot-name>`**                           | Read and write access to the Databricks depot.                                                                                                                                                                          | Tenant Admin or Data Admin                                               |
| **`depot:r:<databricks-depot-name>`**                            | Read-only access to the Databricks depot (for consumers).                                                                                                                                                               | Tenant Admin or Data Admin                                               |
| **Can Use** _(Compute, Depots, Secrets)_                         | Allows you to actually use Compute, Depots, and Secrets. **Note:** Resource access is deny-by-default. Even if you have a role tag or depot permission, you also need **Can Use** to use the resource.                  | Tenant Admin or Data Admin                                               |
| **`git-sync` Secret**                                            | Allows Vulcan to pull model code from Git using credentials stored in a Secret. Request a **git-sync Secret**, not raw Git credentials. If you create the Secret yourself, you still need **Can Use** permission on it. | Tenant Admin, Data Admin, or the Secret owner (with **Can Use** granted) |

Run `dataos-ctl get depot` to confirm your read access before you start. If the Databricks depot is missing, request `depot:r` from your operator.

### Next step

After access is ready, configure the gateway in [connect-to-databricks.md](connect-to-databricks.md "mention").
