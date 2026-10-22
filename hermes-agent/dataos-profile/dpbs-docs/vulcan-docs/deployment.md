---
description: >-
  Deploy a Vulcan Data Product into a DataOS environment: prerequisites,
  the deployment: section in config.yaml, linting, deploying, and
  checking status.
---

# Deployment steps

Deploy Vulcan data products into a DataOS environment by following these steps in order: check prerequisites, add a `deployment:` section to `config.yaml`, lint the generated manifest, deploy it, then check status.

---

## Step 1: Check prerequisites

Confirm the following resources already exist in your DataOS environment before deploying.

### 1.1 DataOS CLI

```bash
# Verify CLI installation
dataos-ctl version

# Login to your DataOS instance
dataos-ctl login
```

### 1.2 Depot (data source connection)

```bash
dataos-ctl resource -t depot get -a
```

{% hint style="info" %}
The depot needs read/write permissions for your data warehouse schema.
{% endhint %}

### 1.3 Compute resource

```bash
dataos-ctl resource -t compute get -a
```

**Example compute resources:** `cyclone-compute` (general purpose), `minerva-compute` (query engine), or a custom compute cluster.

### 1.4 Git-sync secret

Needed to access a private Git repository containing your Vulcan project.

```bash
dataos-ctl resource apply -f git-sync-secret.yaml
```

```yaml
name: git-sync
version: v2alpha
type: secret
workspace: system
layer: user
description: "Secret for git-sync authentication (Bitbucket)"
secret:
  type: key-value
  data:
    GITSYNC_USERNAME: "<your-git-username>"
    GITSYNC_PASSWORD: "<your-git-token-or-password>"
```

{% hint style="warning" %}
Replace `GITSYNC_USERNAME` and `GITSYNC_PASSWORD` with your actual Git repository credentials or access tokens.
{% endhint %}

Once all four exist, move on to configuration.

---

## Step 2: Add the `deployment:` section to `config.yaml`

A Vulcan deployment is driven entirely by `config.yaml`. There is no separate `domain-resource.yaml` to hand-edit. The `deployment:` section supplies everything `vulcan create_deploy_yaml` needs to render a DataOS Vulcan resource manifest, deterministically and with no `<placeholder>` values left to fill in.

For the rest of `config.yaml` (project identity, `users`, `gateways`, `model_defaults`, notifications), see [Configurations](configurations/README.md). Business-facing usage guidance belongs in a separate [usage.yaml](configurations/usage.md), and the data-sharing agreement text in [agreement.md](configurations/agreement.md).

{% tabs %}

{% tab title="What's derived vs. set" %}
Some fields are computed automatically and are never written under `deployment:`:


| Field                         | Source                                                                                                                      |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `name`, `description`, `tags` | From `config.yaml`'s top-level `name`, `description`, `tags`                                                                |
| `engine`                      | From the default gateway connection type, or `model_defaults.dialect`                                                        |
| `depots` (default)            | From the depot address on a depot-typed gateway connection                                                                  |
| `workflow.schedule.crons`     | Union of every model's effective cron (explicit `cron`, or `model_defaults.cron` when a model doesn't set one), deduplicated |


`engine` and the derived `crons` can't be overridden. `depots` is derived but may be overridden explicitly under `deployment.depots`.

A couple of fields are fixed and not configurable: `version` is always `v1alpha`, and `workflow.schedule.concurrency_policy` is always `Forbid`.

Everything else lives under `deployment:`. Only `repo.url`, `repo.base_dir`, `compute`, and `run_as_user` are required; everything else has a default.
{% endtab %}

{% tab title="Minimal" %}

```yaml
deployment:
  repo:
    url: git@bitbucket.org:org/repo.git
    base_dir: repo/vulcan-project
  compute: general-purpose-shared
  run_as_user: svc-user
```

{% endtab %}

{% tab title="Complete" %}

```yaml
deployment:
  type: vulcan                      # default vulcan; override for a custom resource type

  # ── repo (url + base_dir required) ───────────────────────────────
  repo:
    url:      <string>              # required: git remote
    base_dir:  <string>              # required: project path inside the repo
    secret_id: <tenant>:<name>       # required, private repos only (DataOS secret ref)
    sync_flags:                      # optional, any git-sync flag, verbatim
      - --ref=main                  # default when sync_flags omitted
      - --submodules=off            # default when sync_flags omitted

  # ── spec-level ──────────────────────────────────────────────────
  compute:   general-purpose-shared # required
  run_as_user: <string>               # required
  state_store_connection:  <name>     # advanced; omit → vulcan-state-connection
  object_store_connection: <name>     # advanced; omit → vulcan-object-store-connection

  # ── depots (override; else derived from config.yaml depot conn) ──
  depots:
    - dataos://lakehouse?purpose=rw

  # ── schedule (crons are derived from models) ────────────────────
  schedule:
    end_on:    <ISO-8601>            # optional; omit if none
    timezone: UTC                   # default UTC

  # ── workflow (service-scoped: knobs + resource + commands) ──────
  workflow:
    log_level: INFO                  # default INFO
    resource:
      request: { cpu: 200m,  memory: 512Mi }
      limit:   { cpu: 1000m, memory: 1Gi }
    plan: { command: [vulcan], arguments: [plan, --auto-apply] }
    run:  { command: [vulcan], arguments: [run] }

  # ── api (service-scoped) ────────────────────────────────────────
  api:
    replicas: 1                     # default 1
    log_level: INFO                  # default INFO
    resource:
      request: { cpu: 200m,  memory: 512Mi }
      limit:   { cpu: 1000m, memory: 1Gi }

  # ── use: secret / env projection, optional ─────────────────────
  use:
    secrets:
      - { id: <tenant>:<name>, context_alias: <alias> }
    env_vars:
      - { key: <ENV_NAME>, template: "{% raw %}{{ secrets[<alias>].<KEY> | base64_decode }}{% endraw %}" }

  # ── spark_conf, only when engine == spark ───────────────────────
  spark_conf:
    spark.sql.shuffle.partitions: "16"
    spark.sql.adaptive.coalescePartitions.enabled: "true"

  # ── trino, only when engine == trino ───────────────────────────
  trino:
    catalog:
      config: [ "lakehouse.metastore=thrift" ]
    coordinator:
      resource: { request: { cpu: "1", memory: 2Gi }, limit: { cpu: "2", memory: 4Gi } }
    workers:
      replicas: 3
      resource: { request: { cpu: "2", memory: 4Gi } }
      autoscale: { min_replicas: 2, max_replicas: 6, cpu_target: 70 }
```

{% hint style="info" %}
**`spark_conf` and `trino` are engine-gated**

`spark_conf` is only valid when the resolved `engine` is `spark`; `trino` only when it's `trino`. Setting either under the wrong engine fails validation at `create_deploy_yaml` time, not at DataOS apply time. Depot cardinality is also engine-dependent: `spark` and `trino` allow one or more depots, every other engine requires exactly one.
{% endhint %}

{% hint style="info" %}
**Tenant comes from the environment**

Set `DATAOS_TENANT_ID` in your shell or `.env`. It's no longer a YAML key.
{% endhint %}
{% endtab %}

{% endtabs %}

Once `config.yaml` is committed and pushed to your Git repository, move on to linting.

---

## Step 3: Lint the deploy manifest

Before deploying, render the manifest and validate it with `-l` (lint / dry-run) instead of applying it. This catches a missing required field, an unsupported `engine`, or an unknown key under `deployment:` before anything reaches DataOS:

```bash
vulcan create_deploy_yaml -o - | dataos-ctl resource apply --in -l
```

Fix any errors it reports in `config.yaml` and re-run this command until it passes clean.

---

## Step 4: Deploy

Once the lint check passes, render the manifest and apply it for real:

```bash
vulcan create_deploy_yaml -o - | dataos-ctl resource apply --in
```

---

## Step 5: Check status

```bash
dataos-ctl resource -t vulcan -n <name-of-dp> get -r
```

`-r` prints the resource's runtime status.

---

## Verification

Confirm the deployment actually worked.

### Verify models in data warehouse

```sql
-- For Snowflake
SHOW TABLES IN SCHEMA <database>.<schema>;

-- Check specific table
SELECT * FROM <database>.<schema>.<table-name> LIMIT 10;
```

### Access Vulcan API

```bash
# Test API (if exposed)
curl --location 'https://<env-fqn>/<tenant>/vulcan/<data-product-name>/livez' \
  --header 'Authorization: Bearer <your-token>'
```

---

## Related pages

- [Configurations overview](configurations/README.md): full `config.yaml` key reference.
- [Usage guidance](configurations/usage.md)
- [Agreement](configurations/agreement.md)
- [Model Defaults](configurations/model-defaults.md)

