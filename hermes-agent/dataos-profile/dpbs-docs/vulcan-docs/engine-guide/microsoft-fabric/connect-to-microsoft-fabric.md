---
description: >-
  Configure a Fabric gateway, develop against a dev warehouse, and prepare
  production deployment.
---

# Connect to Microsoft Fabric

## Connection options

Connect Vulcan to Fabric Warehouse directly, with the credentials supplied through a Secret's projection. This is the only supported connection path for Fabric: a Depot cannot be used. The connection itself uses Microsoft Entra service-principal authentication.

Set connection details under `gateways.<name>.connection` in `config.yaml`, and project the Secret's values into the environment variables the gateway reads.

### Authentication methods

Fabric Warehouse only accepts Microsoft Entra ID authentication. There is no SQL-login/password path.

* **Service principal (recommended for the Vulcan gateway):** register an Entra app registration and grant it Fabric workspace access. Set `user` to the client ID, `password` to the client secret, plus `tenant_id` and `workspace_id`.
* Set `driver: pyodbc` and `odbc_properties: {authentication: ActiveDirectoryServicePrincipal}`. Install the `fabric` extra with `pip install "vulcan-0.228.1.29-py3-none-any.whl[fabric]"`.
* Always inject the client secret from an environment variable: `password: {{ env_var('FABRIC_CLIENT_SECRET') }}`.

Interactive browser authentication suits local exploration. Do not use it for production gateways.

### Properties in `config.yaml`

In `config.yaml`, set these under `gateways.<name>.connection`.

| Option            | Description                                                                                                                                                  | Type          | Required |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------- | -------- |
| `type`            | Engine type name. Must be `fabric`.                                                                                                                          | string        | Yes      |
| `host`            | The hostname of the Fabric Warehouse SQL analytics endpoint.                                                                                                 | string        | Yes      |
| `user`            | The client ID (application ID) for authentication.                                                                                                           | string        | No       |
| `password`        | The client secret for authentication.                                                                                                                        | string        | No       |
| `port`            | The port number. Default `1433`.                                                                                                                             | int           | No       |
| `database`        | The target warehouse name.                                                                                                                                   | string        | No       |
| `charset`         | The character set used for the connection.                                                                                                                   | string        | No       |
| `timeout`         | Query timeout in seconds. Default: no timeout.                                                                                                               | int           | No       |
| `login_timeout`   | Seconds to wait for connection and login (default 60).                                                                                                       | int           | No       |
| `appname`         | The application name for the connection.                                                                                                                     | string        | No       |
| `conn_properties` | List of raw connection properties.                                                                                                                           | list\[string] | No       |
| `autocommit`      | Enable autocommit mode. Fabric Warehouse defaults this to `true` because the adapter does not rely on explicit transactions.                                 | bool          | No       |
| `driver`          | Driver used for the connection. Fabric only supports `pyodbc`.                                                                                               | string        | No       |
| `driver_name`     | ODBC driver name, for example `ODBC Driver 18 for SQL Server`.                                                                                               | string        | No       |
| `odbc_properties` | ODBC connection properties, for example `authentication: ActiveDirectoryServicePrincipal`.                                                                   | dict          | No       |
| `tenant_id`       | The Azure / Entra tenant UUID.                                                                                                                               | string        | **Yes**  |
| `workspace_id`    | The Fabric workspace UUID. Retrieve it by running `notebookutils.runtime.context.get("currentWorkspaceId")` in a Python notebook, or from the workspace URL. | string        | **Yes**  |

Set `driver_name` to `ODBC Driver 18 for SQL Server`. Set `odbc_properties.authentication` to `ActiveDirectoryServicePrincipal`.

{% hint style="warning" %}
Inject the client secret from an environment variable. Do not commit it to the repository.
{% endhint %}

## Gateway config examples

### Direct connection with a service principal

```yaml
gateways:
  fabric:
    connection:
      type: fabric
      host: xxxxx.datawarehouse.fabric.microsoft.com
      driver: pyodbc
      driver_name: "ODBC Driver 18 for SQL Server"
      odbc_properties:
        authentication: ActiveDirectoryServicePrincipal
      user: "{{ env_var('FABRIC_CLIENT_ID') }}"
      password: "{{ env_var('FABRIC_CLIENT_SECRET') }}"
      tenant_id: "{{ env_var('FABRIC_TENANT_ID') }}"
      workspace_id: "{{ env_var('FABRIC_WORKSPACE_ID') }}"
      database: warehouse
```

Validate the connection:

```bash
vulcan --log-to-stdout plan
```

### Supplying the credentials from a Secret

In production, keep the service-principal values in a DataOS Secret and project them into the workload, so the gateway resolves `FABRIC_CLIENT_ID`, `FABRIC_CLIENT_SECRET`, `FABRIC_TENANT_ID`, and `FABRIC_WORKSPACE_ID` from the environment rather than from anything committed to the repository. The gateway config stays exactly as shown above.

Apply the Secret, the Git Secret, the project configuration, and the Vulcan resource in that order. See [Production deployment](connect-to-microsoft-fabric.md#production-deployment) for the required resources.

## No local Docker setup

Fabric Warehouse is a SaaS-only service with no self-hosted or emulated equivalent, so there is no local Docker stack for this engine, unlike Postgres or Spark. Local development connects to a real (typically dev-tier) Fabric workspace. Keep a lightweight dev warehouse per developer or team, and rely on `vulcan plan` dry-runs plus unit tests (which run against DuckDB locally, not Fabric) to iterate quickly before touching the shared warehouse.

## Production deployment

{% stepper %}
{% step %}
**`secret-fabric-serviceprincipal.yaml`**

Stores the Entra client ID, client secret, tenant ID, and workspace ID.
{% endstep %}

{% step %}
**`secret-git-sync.yaml`**

Repo credentials for git-sync.
{% endstep %}

{% step %}
**`config.yaml`**

Gateway points at the warehouse (`type: fabric`), reading the service-principal values from the projected Secret.
{% endstep %}

{% step %}
**`workspace-deploy.yaml`**

Workflow plus API; references `engine: fabric`, the Secret, and the repo.
{% endstep %}
{% endstepper %}

## Before production

* Confirm least-privilege grants for the service principal and consumers.
* Validate the gateway against the target Fabric workspace and warehouse.
* Set concurrency and connection limits for scheduled workflows.
* Test recovery procedures for failed incrementals and warehouse creation.

### Next step

After you validate the connection, choose a model strategy in [materialization-behavior.md](materialization-behavior.md "mention").
