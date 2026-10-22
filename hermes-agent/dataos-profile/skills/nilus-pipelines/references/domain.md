# Nilus pipeline reference

Use when drafting or validating `source.options` / `sink.options`, URIs, incremental keys, CDC, or metadata.

How to **use** each option (masking, type hints, incremental, partitions, sampling): [options.md](options.md). This file is the allowlist.

Source of truth for DataOS domain keys: `.artifacts/nilus-domain.yaml` (`specSchema.jsonSchema`).  
Inner Nilus runtime is more permissive (`nilus/src/helper.py`, `nilus/src/pipeline.py`). **Draft to the domain allowlist.**

## `source.options` allowlist

| Key | Notes |
|---|---|
| `source_table` | SQL: `schema.table`. API: connector table. Custom SQL: `query:…` |
| `primary_key` | Required for `merge`. Comma-separated if composite |
| `incremental_key` | Timestamp/cursor column |
| `interval_start` / `interval_end` | ISO-like datetimes; see formats below |
| `type_hints` | map of `column: type` — types only, not a rename. See [options.md](options.md#type_hints) |
| `mask` | map of `column: algorithm`. **Source only.** Works on **batch**. CDC accepts it but does **not** apply it (verified). See [options.md](options.md#data-masking) |
| `strategy` | CDC only: `flatten` \| `changelog` |
| `max_table_nesting` | **string**. `"0"` = no child tables (nested stays JSON). See [options.md](options.md#shape) |
| `extract_parallelism` | int |
| `page_size` | int |
| `sql_limit` | int |
| `sql_exclude_columns` | comma-separated names |
| `sql_reflection_level` | `minimal` \| `full` \| `full_with_precision` |
| `sql_backend` | `default` \| `sqlalchemy` \| `pyarrow` \| `connectorx` |
| `yield_limit` | int |
| `service_type` | metadata/Hera |
| `query_log_duration` | metadata, int |
| `result_limit` | metadata, int |
| `threads` | metadata, int ≥ 1 |
| `database_filter` / `schema_filter` / `table_filter` | `{includes: [], excludes: []}` |

`source.cdc` is a free-form object (Debezium properties). Extra keys are allowed **there only**.

## `sink.options` allowlist

| Key | Notes |
|---|---|
| `dest_table` | Batch SQL/lakehouse: `schema.table`. Batch Mongo: `db.collection`. Custom: schema only. **CDC: schema only** |
| `incremental_strategy` | **domain:** `replace` \| `append` \| `merge` |
| `full_refresh` | bool — resets cursor; not the same as `replace` |
| `aws_region` / `aws_endpoint` | lakehouse / S3-backed sinks |
| `iceberg_metadata_compression` | `gzip` \| `none` |
| `loader_file_size` | int |
| `staging_bucket` | string |
| `cluster_by` | list of column names |
| `partition_by` | list of partition specs (below) |

```yaml
partition_by:
  - column: updated_at
    type: day          # year | month | day | hour | bucket | identity
    name: updated_at_day
    index: 1            # sort order
    # bucket_count required when type=bucket
```

## Runtime vs domain

Nilus runtime (`IncrementalStrategy`) also accepts `delete+insert`, `scd2`, `none`.  
Do **not** put those in a `type: nilus` manifest unless the cluster domain schema has been updated to allow them.

`SCHEMA_NAMING` is a Nilus env (`default` | `direct`), not a domain option.

Usage sources: prefer `usage+<engine>://…` in `source.address`. Do not add `type: usage` under `source.options` — the domain rejects `type`.

## Incremental placement

On DataOS YAML, keys go on **source**, strategy on **sink**. Same for `type_hints` and `mask`.

```yaml
source:
  options:
    source_table: public.users
    incremental_key: updated_at
    primary_key: id
    type_hints:
      updated_at: timestamp
    mask:
      email: hash
sink:
  options:
    dest_table: raw.users
    incremental_strategy: merge
```

Interval formats (`pipeline.py` `DATE_FORMATS`): `2023-01-31`, `2023-01-31T15:00:00`, `2023-01-31T15:00:00+00:00`, `2023-01-31 15:00:00`, plus optional microseconds.

Custom query incremental loads must filter in SQL (`:interval_start` / `:interval_end`) and return the incremental column.

## Common addresses

| Kind | Address |
|---|---|
| DataOS depot / lakehouse | `dataos://<name>?purpose=rw` |
| Postgres | `postgresql://{USER}:{PASS}@host:5432/db` |
| MySQL | `mysql://{USER}:{PASS}@host:3306/db` |
| MSSQL | `mssql://{USER}:{PASS}@host:1433/db` |
| DB2 | `db2://{USER}:{PASS}@host:50000/SAMPLEDB` |
| Mongo | `mongodb://{USER}:{PASS}@host:27017/?replicaSet=rs0` |
| Jira | `jira://site.atlassian.net?email={EMAIL}&api_token={TOKEN}` |
| Kafka | `kafka://?bootstrap_servers=host:9092&group_id=g` |
| Custom | `custom://ClassName?param=value` — ClassName must match the Python class |
| Postgres / MySQL / Mongo / MSSQL CDC | **depot** (`dataos://…`). URI works; depot is the recommended practice |
| DB2 CDC | `db2://{USER}:{PASS}@host:50000/DB` only — no depot type |
| Metadata | `metadata+<engine>://…` or a depot; `spec.type: metadata`; **no `sink`** |
| Usage | `usage+<engine>://…` — do not set `type: usage` under `source.options` |

### Depot vs URI

- `dataos://<depot>?purpose=rw` — credentials come from the depot secret. Use when a depot exists.
- Scheme URI (`postgresql://…`, `db2://…`, `jira://…`) — credentials must be `{ENV}` placeholders plus `use.projection`. Use when there is no depot type (DB2) or they have not created one.
- **CDC:** depot on `source.address` for every depot-supported engine. URI is technically valid; do not use it as the default. DB2 CDC is URI-only. Sink `dest_table` is schema only.
- Source and sink can mix when needed (the usual exception: `db2://…` source → depot sink).
- Keep `spec.type: cdc` and put Debezium keys under `source.cdc`. Do not invent a `debezium+` prefix unless that is already the working form.
- Never inline passwords. If a password contains `@`, `#`, `/`, encode it in the secret (`@` → `%40`) before interpolation.

Templates: `templates/batch-uri.yml`, `templates/cdc-db2-uri.yml`.

For API connectors, `source_table` is a **logical table**, not `schema.table`. Read `docs/connectors/<name>.md`.

Jira tables: `projects`, `issues` (merge on `fields.updated`), `users`, `issue_types`, `statuses`, `priorities`, `resolutions`, `project_versions`, `project_components`, `issue_changelogs`. Suffix `:skip_archived` on projects / versions / components.

## CDC checklist

- `spec.type: cdc`
- Source address: **depot** unless the engine has no depot type (DB2 → URI)
- `source.options.strategy: flatten` unless they want raw changelog
- Unique `topic.prefix` per pipeline
- Postgres: `table.include.list`, `slot.name`, often `publication.name` + `publication.autocreate.mode`
- Mongo: `collection.include.list`, `snapshot.mode` as needed
- Sink `dest_table`: **schema only**; `incremental_strategy`: `append` or `merge` (`replace` raises)
- Do not expect `mask` or `type_hints` to apply on CDC
- Size memory up vs batch; 2–4Gi limits are common

## Metadata checklist

- `spec.type: metadata` and `spec.mode: deep` or `shallow` (`mode` is required by the domain `if`/`then` when `type` is `metadata`)
- **No `sink` section** — metadata writes to the DataOS catalog, not a dest table
- `source.options.service_type` is required by Hera
- Do **not** set `source_table` unless they want a single Hera workflow (`metadata` \| `profiler` \| `lineage` \| `usage` \| `classification`). Hera defaults to `metadata`; the DAG assigns the stage name
- Filters: `database_filter` / `schema_filter` / `table_filter` with `includes` / `excludes`

## Other `spec` keys

```yaml
spec:
  runAsUser: <dataos-user>
  schedule:                    # batch only
    crons: ["30 11 * * *"]
    timezone: Asia/Kolkata
    endOn: "2026-12-31T00:00:00Z"
    concurrencyPolicy: Forbid  # Allow | Forbid | Replace
  resources:
    requests: { cpu: "200m", memory: "256Mi" }
    limits: { cpu: "1000m", memory: "1Gi" }
  use:
    volumes:
      - id: workspace:nilus-state
        directory: /var/dataos/public/nilus_state
        readOnly: false
    projection:
      secrets: []
      projections:
        envVars: []
  repo:
    url: https://…
    baseDir: path
    secretId: workspace:gitsecret
    syncFlags: ["--ref=main"]
```

## Volumes (PVC)

A DataOS volume is a PVC. Create the volume first, then mount it on the Nilus pipeline.

**When to attach one**

- Incremental / merge batch that must keep dlt pipeline state across reruns
- Large extracts that spill to disk
- Any run where ephemeral pod disk is not enough

**1. Volume resource** (`type: volume`, not `type: nilus`):

```yaml
name: nilus-state
version: v2alpha
type: volume
volume:
  size: 20Gi
  type: disk
  dataplane: <same-dataplane-as-compute>
```

**2. Mount on the pipeline** (`spec.use.volumes` is the domain field; there is no `envs:` block on `type: nilus`):

```yaml
spec:
  use:
    volumes:
      - id: <workspace>:nilus-state
        directory: /var/dataos/public/nilus_state
        readOnly: false
    projection:
      projections:
        envVars:
          - key: DATAOS_WORK_DIR
            template: "/var/dataos/public/nilus_state"
          - key: DATAOS_PERSISTENT_DIR
            template: "/var/dataos/public/nilus_state"
```

| Field | Rule |
|---|---|
| `id` | Volume resource name, or `workspace:name`. If resolve fails, use the id from `ds2 resource get -t volume` (sometimes `volumev2alpha<name>-xxxx`). |
| `directory` | Absolute mount path **inside** the container. Must match the `DATAOS_*` templates. |
| `readOnly` | `false` when Nilus writes state. Default is `false`. |
| `DATAOS_WORK_DIR` | Working dir (repo checkout, temp files). Domain also injects a default; override it to the mount. |
| `DATAOS_PERSISTENT_DIR` | If set, Nilus stores the dlt pipeline dir under `$DATAOS_PERSISTENT_DIR/temp_pipeline_dir`. Prefer this for state that must survive restarts. |

Volume and compute must share a dataplane. Do not put credentials on the volume. Do not reuse a git-sync work dir as the PVC mount if `spec.repo` is also set (custom sources clone into `DATAOS_WORK_DIR`).

Templates: `templates/volume.yml`, `templates/batch-pvc.yml`.

## Apply / inspect (only if asked)

```bash
ds2 apply -f pipeline.yml -w <workspace>
ds2 resource get -t nilus -n <name> -w <workspace>
ds2 resource log -t nilus -n <name> -w <workspace>
```

Validate with DataOS MCP `dataos_schema_validate` when that server is available, before apply.
