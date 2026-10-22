---
description: >-
  Provision Fabric and DataOS access before configuring or deploying a Data
  Product.
---

# Permissions and grants

## Fabric-side permissions and grants

Provision access before configuring a gateway. Fabric and DataOS authorization are separate.

| Role                     | Scope                           | Required access                                                                            |
| ------------------------ | ------------------------------- | ------------------------------------------------------------------------------------------ |
| Admin role               | Fabric workspace or capacity    | Creates workspaces, assigns capacity, and grants workspace roles.                          |
| Vulcan service principal | Entra app registration          | **Contributor** or higher workspace role. It materializes models through the SQL endpoint. |
| Consumer role            | BI users and endpoint consumers | **Viewer** workspace role and SQL endpoint read access.                                    |

Grant the service principal a workspace role in the Fabric portal. Then verify its SQL-level access:

```sql
SELECT name, type_desc
FROM sys.database_principals
WHERE name = '<service-principal-name>';
```

In the Fabric portal, open **Workspace settings → Manage access → Add people or groups**. Select the app registration and assign **Contributor**. The service principal also needs `db_datareader` and `db_datawriter`-equivalent SQL endpoint access for model materialization.

`connection.database` must exist before `vulcan plan`, unless the Vulcan resource creates it. Warehouse creation uses the Fabric REST API.

## DataOS permissions

Provision these permissions before you create or deploy a Data Product.

| Permission                        | Outcome                                         |
| --------------------------------- | ----------------------------------------------- |
| Tenant Access                     | Build and manage Data Products in your tenant.  |
| `roles:id:data-dev`               | Create and apply Vulcan resources.              |
| Can Use (Compute, Secrets)        | Use the required Compute and Secrets resources. |
| git-sync Secret                   | Pull model code from Git.                       |
| Fabric workspace Contributor role | Authorize the service principal in Fabric.      |

{% hint style="info" %}
Confirm that you can use the service-principal Secret before you start. Request the Secret and its **Can Use** grant together.
{% endhint %}

Resource access is deny-by-default. A role tag alone does not grant resource use. Confirm **Can Use** for both Compute and the service-principal Secret.

### Next step

Configure and validate the gateway in [connect-to-microsoft-fabric.md](connect-to-microsoft-fabric.md "mention").
