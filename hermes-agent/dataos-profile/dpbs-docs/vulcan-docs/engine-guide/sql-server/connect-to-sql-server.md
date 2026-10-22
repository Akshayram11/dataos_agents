---
description: >-
  Configure SQL Server gateways, develop locally with Docker, and prepare
  production deployment.
---

# Connect to SQL Server

## Connection options

This is the first hands-on stage. Complete access provisioning before this step.

Connect Vulcan directly or through a DataOS Depot. Direct connections support SQL Server username/password and Microsoft Entra ID authentication. Use a Depot for production.

### Authentication methods

* **Username and password:** Set `user` and `password` with `driver: pymssql`.
* **Microsoft Entra ID:** Install `mssql-odbc`. Set `driver: pyodbc`, `driver_name`, and `odbc_properties`.
* Inject passwords with `password: {{ env_var('MSSQL_PASSWORD') }}`.

{% hint style="info" %}
Azure SQL Database uses the same adapter under an `azuresql` connection-config type. Azure SQL is `SINGLE_CATALOG_ONLY`. Generic MSSQL is `REQUIRES_SET_CATALOG`. Grants, materialization, MERGE behavior, and troubleshooting remain the same.
{% endhint %}

### Properties in config.yaml

Set these properties under `gateways.<name>.connection`.

| Option            | Description                               | Type          | Required |
| ----------------- | ----------------------------------------- | ------------- | -------- |
| `type`            | Engine type name. Must be `mssql`.        | string        | Yes      |
| `host`            | SQL Server instance hostname.             | string        | Yes      |
| `user`            | Authentication username.                  | string        | No       |
| `password`        | Authentication password.                  | string        | No       |
| `port`            | Port number. Default `1433`.              | int           | No       |
| `database`        | Target database.                          | string        | No       |
| `charset`         | Connection character set.                 | string        | No       |
| `timeout`         | Query timeout in seconds.                 | int           | No       |
| `login_timeout`   | Login timeout in seconds. Default `60`.   | int           | No       |
| `appname`         | Connection application name.              | string        | No       |
| `conn_properties` | Raw connection properties.                | list\[string] | No       |
| `autocommit`      | Enables autocommit. Default `false`.      | bool          | No       |
| `driver`          | `pymssql` or `pyodbc`. Default `pymssql`. | string        | No       |
| `driver_name`     | ODBC driver name. Used with `pyodbc`.     | string        | No       |
| `odbc_properties` | ODBC properties.                          | dict          | No       |

## Gateway configuration

Minimum local connection with `pymssql`:

```yaml
gateways:
  local:
    connection:
      type: mssql
      host: localhost
      user: sa
      password: "{{ env_var('MSSQL_PASSWORD') }}"
      port: 1433
      database: warehouse
```

Entra ID / Azure AD via `pyodbc`:

```yaml
gateways:
  prod:
    connection:
      type: mssql
      host: myserver.database.windows.net
      driver: pyodbc
      driver_name: "ODBC Driver 18 for SQL Server"
      odbc_properties:
        authentication: ActiveDirectoryServicePrincipal
      user: "{{ env_var('AZURE_CLIENT_ID') }}"
      password: "{{ env_var('AZURE_CLIENT_SECRET') }}"
      database: warehouse
```

## Local development with Docker

SQL Server runs locally through the official container image. Save this as `docker/docker-compose.warehouse.yml`:

```yaml
version: "3.8"
services:
  mssql:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      ACCEPT_EULA: "Y"
      MSSQL_SA_PASSWORD: "${MSSQL_SA_PASSWORD}"
    ports:
      - "1433:1433"
    volumes:
      - mssql-data:/var/opt/mssql
volumes:
  mssql-data:
```

Use the matching connection and DuckDB state:

```yaml
state_connection:
  type: duckdb
  database: .state.db

gateways:
  local:
    connection:
      type: mssql
      host: localhost
      user: sa
      password: "{{ env_var('MSSQL_SA_PASSWORD') }}"
      port: 1433
      database: warehouse
```

Validate the connection:

```bash
vulcan --log-to-stdout plan
```

`--log-to-stdout` avoids a `.logs/` directory when the working directory is not writable.

## Production deployment

Use a DataOS Depot for production. Configure `type: depot` and `address: dataos://<mssql-depot-name>?purpose=rw`.

```yaml
gateways:
  default:
    connection:
      type: depot
      address: dataos://<mssql-depot-name>?purpose=rw
```

Apply resources in this order: Secret, Depot, Git Secret, project configuration, then Vulcan resource.

{% stepper %}
{% step %}
**`secret-mssql.yaml`**

Stores the SQL login/password or Entra service-principal credentials.
{% endstep %}

{% step %}
**`depot-mssql.yaml`**

Registers host, database, driver, and binds purposes to the secret.
{% endstep %}

{% step %}
**`secret-git-sync.yaml`**

Stores repository credentials for git-sync.
{% endstep %}

{% step %}
**`config.yaml`**

Points the gateway at the Depot.
{% endstep %}

{% step %}
**`workspace-deploy.yaml`**

Defines the workflow and API using `engine: mssql`, the Depot, and the repository.
{% endstep %}
{% endstepper %}

Two wiring styles are supported. Use a depot gateway, or use `envFrom` with an instance secret. Do not mix a depot gateway with conflicting environment variables.

### Depot purposes

| Purpose | Used by                | Grants                                                        |
| ------- | ---------------------- | ------------------------------------------------------------- |
| `rw`    | Vulcan workflow        | Reads sources and creates, updates, and deletes model output. |
| `scan`  | Metadata scanner       | Reads `INFORMATION_SCHEMA` and `sys.*` catalog views.         |
| `query` | Consumer direct access | Read-only Data Product table access.                          |

### Next step

After the connection validates, choose model behavior in [materialization-behavior.md](materialization-behavior.md "mention").
