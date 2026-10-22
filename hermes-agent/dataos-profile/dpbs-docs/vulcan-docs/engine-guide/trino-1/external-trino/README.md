---
description: >-
  The full reference for connecting Vulcan to a bring-your-own Trino, Starburst,
  or self-hosted cluster that exists outside DataOS, covering connection
  options, authentication, and catalog notes.
---

# External cluster

External Trino means Vulcan connects to an existing Trino-compatible endpoint that runs outside the Vulcan deployment. Vulcan does not provision or manage the cluster; it points at the coordinator host and port and uses catalogs already mounted on that cluster. This covers Starburst, self-hosted Trino, and any hosted Trino-compatible endpoint.

Use this shape when the cluster already exists and Vulcan only needs to connect to it. For the DataOS-managed shared cluster (which has its own password generation), see [Minerva](../minerva-1.md). To have Vulcan provision and own a cluster per Data Product, see [Dedicated cluster](../dedicated-cluster.md). For the rules common to all three shapes, see [Trino](../).

## Core settings

| Setting                 | Value                                         |
| ----------------------- | --------------------------------------------- |
| Resource type           | `vulcan`                                      |
| Gateway connection type | `trino`                                       |
| Model dialect           | `trino`                                       |
| VDE                     | `false`                                       |
| Scheduler               | Local or built-in scheduler                   |
| `spec.trino` block      | Not used (Vulcan does not manage the cluster) |

Do not set `vde: true` for Trino. Trino gateways must run in simple mode.

## Prerequisites

You need:

* The Trino coordinator host and port.
* A Trino username.
* A Trino password, token, or API key.
* A target catalog (such as `s3depot`, `hive`, `iceberg`, or `delta`).
* Network access from Vulcan to the Trino coordinator.
* Permissions to create schemas, tables, and views in the target catalog.

## Connection options

Set these under `gateways.<name>.connection`.

| Option                    | Description                                                                            | Required |
| ------------------------- | -------------------------------------------------------------------------------------- | -------- |
| `type`                    | Engine type. Must be `trino`.                                                          | Yes      |
| `host`                    | Coordinator host. Do not include `http://` or `https://`.                              | Yes      |
| `user`                    | Trino user. For Starburst Galaxy, this may include a role suffix.                      | Yes      |
| `catalog`                 | Default Trino catalog.                                                                 | Yes      |
| `port`                    | Coordinator port. Defaults depend on the scheme.                                       | No       |
| `http_scheme`             | `http` or `https`. Use `https` in production.                                          | No       |
| `method`                  | Auth method: `basic`, `ldap`, `jwt`, `kerberos`, `certificate`, `oauth`, or `no-auth`. | No       |
| `password`                | Password or generated token for password-based auth.                                   | No       |
| `roles`                   | Catalog-to-role mapping for role-based access control.                                 | No       |
| `http_headers`            | Extra HTTP headers sent with each request.                                             | No       |
| `session_properties`      | Trino session properties.                                                              | No       |
| `retries`                 | Number of request retries.                                                             | No       |
| `timezone`                | Connection timezone.                                                                   | No       |
| `schema_location_mapping` | Regex-to-location mapping for schema creation.                                         | No       |
| `catalog_type_overrides`  | Explicit connector type per catalog (for example `iceberg`, `hive`, `delta_lake`).     | No       |

### Authentication methods

Set `method` to the auth scheme the cluster enables: `basic` (username and password), `ldap`, `jwt`, `kerberos`, `certificate`, `oauth`, or `no-auth`. Use `https` in production and store the password or token in an environment variable.

## Minimal config.yaml

```yaml
vde: false

gateways:
  default:
    connection:
      type: trino
      host: "{{ env_var('TRINO_HOST') }}"
      port: "{{ env_var('TRINO_PORT', '8080') }}"
      user: "{{ env_var('TRINO_USER') }}"
      catalog: "{{ env_var('TRINO_CATALOG') }}"
      http_scheme: "{{ env_var('TRINO_HTTP_SCHEME', 'https') }}"
      method: "{{ env_var('TRINO_METHOD', 'basic') }}"
      password: "{{ env_var('TRINO_PASSWORD') }}"
      verify: true

default_gateway: default

model_defaults:
  dialect: trino
  start: "2024-01-01"

ignore_patterns:
  - "*-deploy.yaml"
```

## Starburst

For Starburst, use the same external pattern. Confirm whether the username needs a role suffix, and use the common Starburst settings:

```yaml
user: "{{ env_var('STARBURST_USER') }}" # example: analyst@example.com/analyst
http_scheme: https
port: 443
method: basic
```

## Self-hosted Trino

For self-hosted Trino, confirm whether the endpoint uses `http` or `https`, which authentication method is enabled, which catalog to use, and whether the catalog can infer table locations. If the catalog cannot infer schema or table locations, configure `schema_location_mapping`:

```yaml
gateways:
  default:
    connection:
      type: trino
      host: "{{ env_var('TRINO_HOST') }}"
      user: "{{ env_var('TRINO_USER') }}"
      catalog: "{{ env_var('TRINO_CATALOG') }}"
      schema_location_mapping:
        ".*": "s3://warehouse/vulcan/@{schema_name}"
```

## Catalog and storage notes

Trino behavior depends on the catalog connector. Hive, Iceberg, and Delta Lake catalogs are common for Vulcan. Some catalogs infer table locations from a warehouse or schema location; if no default exists, use `schema_location_mapping`. Use `catalog_type_overrides` when Vulcan cannot reliably infer whether a catalog is `hive`, `iceberg`, or `delta_lake`:

```yaml
gateways:
  default:
    connection:
      type: trino
      catalog_type_overrides:
        datalake: iceberg
        analytics: hive
```

## Materialization, models, and identifier casing

External Trino uses the same model, semantic, metric, and DQ code as any Trino-backed Vulcan project. Supported model kinds are `VIEW`, `FULL`, `SEED`, `INCREMENTAL_BY_TIME_RANGE`, and `INCREMENTAL_BY_PARTITION`. Identifiers are lowercase (quote with `"` only on reserved-word collisions), use fully qualified `catalog.schema.table` names, and prefer `TIMESTAMP(6)` for Iceberg-backed columns. The materialization target is the configured gateway catalog, and the Trino user must be able to create schemas, tables, and views in it. For the full model, semantic, DQ, and endpoint behavior shared across shapes, see [Trino](../).

## Quick checklist

Before running `vulcan plan`, confirm:

* `vde: false` is set.
* `connection.type` is `trino` and `model_defaults.dialect` is `trino`.
* Trino host, port, user, catalog, and password/token are configured.
* The Trino user can create schemas, tables, and views in the target catalog.

## Related

* [Trino](../) for the common rules and shared behavior.
* [Dedicated cluster](../dedicated-cluster.md) and [Minerva](../minerva-1.md) for the other deployment shapes.
