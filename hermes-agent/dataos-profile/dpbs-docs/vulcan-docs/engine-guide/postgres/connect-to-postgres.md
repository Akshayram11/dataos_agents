---
description: >-
  Configure PostgreSQL gateways, develop locally with Docker, and prepare
  production deployment.
---

# Connect to Postgres

With roles and grants in place, this is the connect stage. Configure the gateway that lets Vulcan reach PostgreSQL, then validate it before writing models.

## Connection options

Set these options under `gateways.<name>.connection` in `config.yaml`.

| Option             | Description                                         | Type   | Required |
| ------------------ | --------------------------------------------------- | ------ | -------- |
| `type`             | Engine type name. Must be `postgres`.               | string | Yes      |
| `host`             | The hostname of the Postgres server.                | string | Yes      |
| `user`             | The username for authentication.                    | string | Yes      |
| `password`         | The password for authentication.                    | string | Yes      |
| `port`             | The port number.                                    | int    | Yes      |
| `database`         | The database to connect to. Must already exist.     | string | Yes      |
| `keepalives_idle`  | Seconds between keepalive packets.                  | int    | No       |
| `connect_timeout`  | Seconds to wait for the connection (default 10).    | int    | No       |
| `role`             | The role for authentication.                        | string | No       |
| `sslmode`          | Connection security level (for example, `require`). | string | No       |
| `application_name` | The application name for the connection.            | string | No       |

### Authentication methods

* Username and password (required): set `user` and `password`.
* SSL mode (optional): set `sslmode: require` or stricter for secure connections in production.

{% hint style="warning" %}
Always inject the password from an environment variable: `password: {{ env_var('POSTGRES_PASSWORD') }}`.
{% endhint %}

## Example gateway config

Minimum local connection:

```yaml
gateways:
  default:
    connection:
      type: postgres
      host: "{{ env_var('WAREHOUSE_HOST', 'localhost') }}"
      port: "{{ env_var('WAREHOUSE_PORT', '5432') }}"
      database: "{{ env_var('WAREHOUSE_DATABASE', 'warehouse') }}"
      user: "{{ env_var('WAREHOUSE_USER', 'vulcan') }}"
      password: "{{ env_var('WAREHOUSE_PASSWORD', 'vulcan') }}"

default_gateway: default
model_defaults:
  dialect: postgres
  start: '2024-01-01'
```

For a local starter project, Vulcan can use the default PostgreSQL gateway connection. For TLS, add `sslmode: require` or stricter.

## Local development with Docker

PostgreSQL is the one engine you can run end to end on your laptop. Create the Docker network once, then bring up a Postgres container.

```bash
docker network create vulcan   # if it already exists, continue
```

Save the following as `docker/docker-compose.warehouse.yml`:

```yaml
# Central Warehouse - PostgreSQL for project data
# Access: postgresql://vulcan:vulcan@localhost:5433/warehouse

x-images:
  postgres: &postgres_image "postgres:17-alpine"

volumes:
  warehouse:
    driver: local

networks:
  vulcan:
    external: true

services:
  warehouse:
    image: *postgres_image
    environment:
      POSTGRES_DB: warehouse
      POSTGRES_USER: vulcan
      POSTGRES_PASSWORD: vulcan
      POSTGRES_HOST_AUTH_METHOD: trust
    ports:
      - "5433:5432"
    volumes:
      - warehouse:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vulcan -d warehouse"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - vulcan
```

```bash
docker compose -f docker/docker-compose.warehouse.yml up -d
```

Use the matching connection (note port `5433` on the host, and DuckDB for local state):

```yaml
gateways:
  default:
    connection:
      type: postgres
      host: localhost
      port: 5433
      database: warehouse
      user: vulcan
      password: vulcan
    state_connection:
      type: duckdb
      database: ./.state/vulcan.db

default_gateway: default
model_defaults:
  dialect: postgres
```

Validate the connection:

```bash
vulcan --log-to-stdout plan
```

{% hint style="info" %}
`--log-to-stdout` skips creating a `.logs/` directory, which avoids `PermissionError` when the working directory is not writable.
{% endhint %}

## Production deployment

DataOS Depot is recommended for production. Configure a gateway with `type: depot` and `address: dataos://<depot-name>`. The depot manages the Postgres credential and access purpose.

Apply resources in this order:

```
PostgreSQL password instance secret → PostgreSQL depot → Git secret → config.yaml → Vulcan resource
```

{% hint style="info" %}
Two wiring styles are supported. Use a depot gateway (`type: depot`, `address: dataos://<name>`), or bind an instance secret into the workflow with `envFrom` and let `config.yaml` read `WAREHOUSE_*` through `env_var()`. Pick one style per project; do not mix a depot gateway with conflicting environment variables.
{% endhint %}

### Depot purposes

Bind the correct purpose to each secret. Each purpose grants scoped access through the same depot. Assign only the purpose required by each workload. A `query` credential cannot create tables. Do not give consumers an `rw` credential.

| Purpose | Who uses it            | What it allows                                                   |
| ------- | ---------------------- | ---------------------------------------------------------------- |
| `rw`    | Vulcan workflow        | Read source tables and create, update, and delete model output.  |
| `scan`  | Metadata scanner       | Read `information_schema` and `pg_catalog` for catalog metadata. |
| `query` | Consumer direct access | Read-only access to Data Product tables.                         |

### Next step

After connection configuration is ready, choose a model strategy in [materialization-behavior.md](materialization-behavior.md "mention").
