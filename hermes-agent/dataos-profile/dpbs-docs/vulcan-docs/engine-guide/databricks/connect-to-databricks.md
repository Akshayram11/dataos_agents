---
description: >-
  Configure direct and depot connections, external state storage, local
  development, and production deployment.
---

# Connect to Databricks

With the required grants in place, this is the connect stage. Configure the gateway that lets Vulcan reach Databricks, then validate it before writing models.

Connect through a Databricks SQL warehouse. Vulcan requires an external Postgres state store.

## Authentication methods <a href="#authentication-methods" id="authentication-methods"></a>

* Personal access token (PAT): set `access_token`. Generate one under User Settings → Developer → Access tokens → Generate new token.
* Service principal token: set `access_token` to the service principal token.

{% hint style="info" %}
The PAT's workspace must match `server_hostname`. A cross-workspace PAT fails silently at auth. Never commit the token; inject it with `access_token: {{ env_var('DATABRICKS_ACCESS_TOKEN') }}`.
{% endhint %}

## Connection options

Local development and quick tests typically use a direct connection; production deployments should move to a DataOS Depot.

Set these options under `gateways.<name>.connection` in `config.yaml`.

| Option            | Description                                                                                                        | Type   | Required |
| ----------------- | ------------------------------------------------------------------------------------------------------------------ | ------ | -------- |
| `type`            | Engine type name. Must be `databricks`.                                                                            | string | Yes      |
| `server_hostname` | The workspace hostname (for example, `adb-xxxxx.azuredatabricks.net` or `dbc-xxxxxxxx-xxxx.cloud.databricks.com`). | string | Yes      |
| `http_path`       | The HTTP path to the SQL warehouse or cluster. Find it under SQL Warehouses → your warehouse → Connection Details. | string | Yes      |
| `access_token`    | Personal access token (PAT) or service principal token.                                                            | string | Yes      |
| `catalog`         | The Unity Catalog name to use as the default catalog.                                                              | string | Yes      |

## Example gateway configuration

Minimum local connection. Note the required `state_connection` and `state_schema` in `config.yaml`

```yaml
gateways:
  default:
    connection:
      type: databricks
      server_hostname: <workspace-host>
      http_path: /sql/1.0/warehouses/<id>
      access_token: "{{ env_var('DATABRICKS_ACCESS_TOKEN', '') }}"
      catalog: "{{ env_var('DATABRICKS_CATALOG', 'main') }}"
    state_connection:
      type: postgres
      host: "{{ env_var('STATESTORE_HOST', 'localhost') }}"
      port: "{{ env_var('STATESTORE_PORT', '5432') }}"
      user: "{{ env_var('STATESTORE_USER', 'vulcan') }}"
      password: "{{ env_var('STATESTORE_PASSWORD', 'vulcan') }}"
      database: "{{ env_var('STATESTORE_DATABASE', 'statestore') }}"
    state_schema: <project_name>
    
default_gateway: default
model_defaults:
  dialect: databricks
```

Isolate multiple projects on the same Postgres instance with different `state_schema` values. For local development, run Postgres in Docker; in production, a DataOS-managed Postgres is used.

## Local development

Databricks itself runs in the cloud; what you run locally is the Postgres statestore Vulcan needs.

```bash
docker run -d --name vulcan-state \
  -e POSTGRES_USER=vulcan -e POSTGRES_PASSWORD=vulcan \
  -e POSTGRES_DB=statestore -p 5432:5432 postgres:15

export DATABRICKS_ACCESS_TOKEN=dapi<your-token>
export DATABRICKS_CATALOG=<your-catalog>

vulcan migrate        # initializes Vulcan state in Postgres
vulcan plan           # dry run against Unity Catalog; should succeed with no errors
```

{% hint style="info" %}
If the CLI runs inside Docker and cannot reach Postgres, set `STATESTORE_HOST=host.docker.internal` and confirm the port mapping.
{% endhint %}

## Production deployment

Production uses a depot instead of a direct connection. Apply resources in this order:

```
Databricks PAT instance secret → Databricks depot → Git secret → config.yaml → Vulcan resource
```

| Manifest                              | Purpose                                                                       |
| ------------------------------------- | ----------------------------------------------------------------------------- |
| `instance-secret-databricks-pat.yaml` | Stores the Databricks PAT.                                                    |
| `depot-databricks.yaml`               | Registers workspace URL, HTTP path, UC catalog; binds purposes to the secret. |
| `secret-git-sync.yaml`                | Repo credentials for git-sync.                                                |
| `config.yaml`                         | Gateway points at the depot.                                                  |
| `domain-resource.yaml`                | Workflow plus API; `engine: databricks`, depot, repo.                         |

Depot purposes:

Each purpose grants scoped access through the same depot. Assign only the purpose required by each workload.

| Purpose | Who uses it            | What it allows                                                                       |
| ------- | ---------------------- | ------------------------------------------------------------------------------------ |
| `rw`    | Vulcan workflow        | Read source tables, create and write model output, manage schemas in the UC catalog. |
| `scan`  | Metadata scanner       | Read UC `information_schema` to populate the catalog and lineage.                    |
| `query` | Consumer direct access | Read-only access to Data Product tables.                                             |

{% hint style="warning" %}
A misspelled depot name passes `apply` but fails at every run with `Depot not resolvable`. Verify `dataos://<depot-name>?purpose=rw` matches the depot manifest's `name` exactly.
{% endhint %}

### Next step

After the gateway works, choose model behavior in [materialization-behavior.md](materialization-behavior.md "mention").
