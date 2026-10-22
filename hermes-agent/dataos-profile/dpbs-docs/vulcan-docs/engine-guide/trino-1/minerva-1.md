---
description: >-
  The full reference for connecting Vulcan to a shared, DataOS-managed Minerva
  (Trino) cluster, covering the secret and password generation, projection into
  config, and the connection setup.
---

# Minerva

On this shape you don't own the cluster. You connect to DataOS's Minerva cluster, provisioned and managed by your platform team. Vulcan never provisions or configures the cluster itself; there's no `spec.trino` block at all. Instead, a `vulcan` resource with `spec.engine: trino` points at the cluster's endpoint through a secret. See [Trino engine overview](./) for the rules shared with the dedicated-cluster shape.

{% hint style="info" %}
Catalogs are already mounted on the cluster before Vulcan ever runs. Your platform team owns catalog creation. Your job is just to connect, and to read/write catalogs you're permitted to use.
{% endhint %}

## When to use this shape

Choose Minerva when you want your Data Product to run on DataOS's shared Trino cluster instead of paying for a dedicated one per Data Product. This is the default shape for most Data Products that don't need dedicated compute, custom JVM sizing, or custom Java plugins.

|                        | Dedicated cluster                                        | Minerva                                                                         |
| ---------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Cluster ownership      | Vulcan provisions it                                     | DataOS-managed, used by many Data Products                                      |
| `spec.trino` block     | Required                                                 | Not used                                                                        |
| Gateway connection     | `no-auth`, `http`, `host: <resource>-trino`, port `8080` | `basic`/JWT, `https`, host + password via secret                                |
| Catalogs               | Generated from `spec.depots[]`                           | Already mounted on the cluster                                                  |
| Materialization target | First depot's catalog                                    | The configured gateway catalog                                                  |
| Best for               | A self-contained, federated DP that owns its compute     | Data Products that just need to query and write, without owning cluster compute |

## Local development

No local cluster to run. This is the biggest practical difference from the dedicated shape. Install Vulcan the same way:

```bash
pip install "/path/to/vulcan-<version>-py3-none-any.whl[trino]"
vulcan --version
```

Models, semantics, metrics, and DQ are written the same way as on a dedicated cluster. Only `config.yaml` changes: it points at the Minerva cluster's endpoint instead of a Docker container.

**`config.yaml`** - point directly at the tenant's Minerva endpoint, using connection details from your DataOS admin:

```yaml
gateways:
  default:
    connection:
      type: trino
      host: "{{ env_var('TRINO_HOST') }}"
      user: "{{ env_var('TRINO_USER') }}"
      catalog: "{{ env_var('TRINO_CATALOG') }}"
      port: "{{ env_var('TRINO_PORT') }}"
      http_scheme: "{{ env_var('TRINO_HTTP_SCHEME', 'https') }}"
      method: "{{ env_var('TRINO_METHOD', 'basic') }}"
      password: "{{ env_var('TRINO_PASSWORD') }}"
      verify: true
    state_connection:
      type: duckdb              # local dev only
      database: ./.state.db

default_gateway: default

model_defaults:
  dialect: trino
  start: '<project-start-date>'
  cron: '@daily'

ignore_patterns:
  - "*-deploy.yaml"
```

{% hint style="warning" %}
This connects to the same Minerva cluster your tenant already runs. It is not a personal instance. Use a catalog/schema you're actually permitted to write to for local testing, and ask your DataOS admin for `TRINO_HOST`, `TRINO_USER`, `TRINO_CATALOG`, `TRINO_PORT`, and `TRINO_PASSWORD`, exporting them as local environment variables before running Vulcan.

Don't assume the local Docker defaults from the dedicated-cluster flow. A tenant's Minerva `TRINO_PORT` is whatever your admin assigns it (not `18080`), and `TRINO_PASSWORD` is typically a DataOS-issued API key. It is a long encoded string, not a literal password. Put it in `.env` and keep `.env` out of git; never write it into `config.yaml` directly.
{% endhint %}

### Hello-world starter

Every model uses the fully-qualified three-part name: `<catalog>.<schema>.<table>`, where `<catalog>` is whatever `TRINO_CATALOG` resolves to for you. Ask your DataOS admin for a catalog and schema you're permitted to write to, then substitute it for `<catalog>` below. The target starts empty, so seed the raw table first, then build a summary model on top of it.

**`seeds/orders.csv`**

```csv
order_id,customer_id,total_price,order_date
O001,C001,120.50,2025-01-05
O002,C002,89.99,2025-01-06
O003,C001,45.00,2025-01-07
```

**`models/seeds/raw_orders.sql`**

```sql
MODEL (
  name <catalog>.raw.orders,
  kind SEED (
    path '../../seeds/orders.csv'
  ),
  columns (
    order_id VARCHAR,
    customer_id VARCHAR,
    total_price DECIMAL(10,2),
    order_date DATE
  ),
  grain order_id
);
```

**`models/full/orders_summary.sql`**

```sql
MODEL (
  name <catalog>.sales.orders_summary,
  kind FULL,
  grain order_id,
  assertions (
    unique_values(columns := order_id),
    not_null(columns := (order_id, customer_id))
  ),
  columns (
    order_id VARCHAR,
    customer_id VARCHAR,
    total_price DECIMAL(10,2),
    order_date DATE
  )
);
SELECT order_id, customer_id, total_price, order_date
FROM <catalog>.raw.orders;
```

**`models/semantics/orders.yml`**

```yaml
kind: semantic
name: orders
depends_on: <catalog>.sales.orders_summary
dimensions:
  - order_date
measures:
  - name: total_sales
    type: sum
    expression: "{orders.total_price}"
```

**`metrics/daily_revenue.yml`**

```yaml
kind: metric
name: daily_revenue
measure: orders.total_sales
granularity: day
```

### Validate the connection

Run these once `config.yaml` exists, your environment variables are exported, and the hello-world models are in place:

```bash
vulcan migrate        # initializes Vulcan state (DuckDB local / Postgres prod)
vulcan plan           # dry-run — you should see the seed and orders_summary staged
vulcan run            # materializes <catalog>.sales.orders_summary
```

If `vulcan plan` succeeds, your local setup is complete. Call the REST endpoint to confirm end-to-end. Common failures at this step are in the troubleshooting table below.

## Deploying

The gateway shape carries straight into production. The deploy resource re-injects the same env vars instead of your shell exporting them. Drop `state_connection` first; it's local-only, and in production DataOS provisions the state store automatically.

`config.yaml` in production is the same shape as the local one above. It uses the same env-var templating.

Resource (`type: vulcan`) projects the connection from a secret:

```yaml
version: v1alpha
type: vulcan
name: <resource-name>
spec:
  runAsUser: "<owner>"
  compute: <trino-compute-pool>
  engine: trino
  repo:
    url: <git-repo-url>
    syncFlags: ["--ref=<branch>", "--submodules=off"]
    baseDir: <path/to/your/project>
    secret: <tenant>:<git-sync-secret>
  use:
    projection:
      secrets:
        - id: <tenant>:<trino-connection-secret>
          contextAlias: trinosec
      projections:
        envVars:
          - { key: TRINO_HOST,        template: "{{ secrets['trinosec'].TRINO_HOST | base64_decode }}" }
          - { key: TRINO_PORT,        template: "{{ secrets['trinosec'].TRINO_PORT | base64_decode }}" }
          - { key: TRINO_USER,        template: "{{ secrets['trinosec'].TRINO_USER | base64_decode }}" }
          - { key: TRINO_CATALOG,     template: "{{ secrets['trinosec'].TRINO_CATALOG | base64_decode }}" }
          - { key: TRINO_HTTP_SCHEME, template: "{{ secrets['trinosec'].TRINO_HTTP_SCHEME | base64_decode }}" }
          - { key: TRINO_METHOD,      template: "{{ secrets['trinosec'].TRINO_METHOD | base64_decode }}" }
          - { key: TRINO_PASSWORD,    template: "{{ secrets['trinosec'].TRINO_PASSWORD | base64_decode }}" }
  workflow:
    schedule:
      crons: ["0 */6 * * *"]
      endOn: "<YYYY-MM-DDT00:00:00-00:00>"
      timezone: "UTC"
      concurrencyPolicy: Forbid
    migrate: { command: [vulcan], arguments: ["--log-to-stdout", "migrate"] }
    plan:    { command: [vulcan], arguments: ["--log-to-stdout", "plan", "--auto-apply"] }
    run:     { command: [vulcan], arguments: ["--log-to-stdout", "run"] }
  api:
    replicas: 1
    resource:
      request: { cpu: "1000m", memory: "2Gi" }
      limit:   { cpu: "2000m", memory: "4Gi" }
```

There's no separate deployment story beyond this. There is no cluster to size, JVM to tune, or plugin directory to manage. What you're deploying is the workflow, the API, and the connection secret.

## Failure modes specific to this shape

| Symptom                                      | Likely cause                                                                                | Fix                                                                                                                           |
| -------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `vulcan plan` works locally, fails in DataOS | Wrong catalog/schema permission on Minerva, or an env var not projected correctly           | Verify with `SHOW CATALOGS`; check the projected secret values                                                                |
| Catalog present but queries fail             | Missing credentials or permission on Minerva that only surfaces on access                   | `SHOW SCHEMAS FROM <catalog>;` then `SELECT 1 FROM <catalog>.<schema>.<table> LIMIT 1;`; ask your platform team to fix grants |
| Production `vulcan migrate` fails            | Platform-managed state store not provisioned or unreachable                                 | Escalate to the SRE/platform team, then re-run `vulcan migrate`                                                               |
| Auth failure connecting to Minerva           | `TRINO_PASSWORD` treated as a literal password instead of the DataOS API key it actually is | Confirm the secret's password field carries the full API key string, not a placeholder                                        |
| Deploy manifest parsed as a model            | `*-deploy.yaml` not ignored                                                                 | Add it to `ignore_patterns` in `config.yaml`                                                                                  |

General troubleshooting that applies to both shapes (`Table not found`, timestamp precision, incremental reprocessing) is on the [Trino engine overview](./) page.

## Full implementation example

Use this complete Data Product as a production-shaped starting point.

{% file src="../../.gitbook/assets/minerva-data-product.zip" %}

## Related

* [Trino engine overview](./) for the rules shared with the dedicated-cluster shape.
* [Dedicated cluster](dedicated-cluster.md) if you're weighing whether to move to a self-owned cluster instead.
