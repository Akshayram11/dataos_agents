---
name: nilus-pipelines
description: Draft DataOS Nilus pipeline YAML and author CustomSource Python connectors. Use when the user asks to create, fix, or review a Nilus pipeline, custom source, custom:// URI, repo sync, incremental custom connector, source/sink options, data masking, type_hints, depot URI, schema_naming, CDC options, custom SQL query, partition_by, or DataOS secret projection.
---

# Nilus Pipeline YAML

Draft **DataOS `type: nilus`** manifests. Do not emit raw `type: workflow` or `type: nilus-v11` unless the user explicitly asks for a legacy form.

Read this file first. Then open only the folder/file for the current task:

| Task | Open |
|---|---|
| Domain allowlists, URIs, incremental / CDC / metadata keys | [references/domain.md](references/domain.md) |
| Masking, type_hints, and every source/sink option | [references/options.md](references/options.md) |
| Author a Python custom source | [references/custom-source.md](references/custom-source.md) |
| Starting YAML / Python files | [templates/](templates/) |
| First-party connector `source_table` values | `docs/connectors/<name>.md` in the Nilus repo |

Official custom-source docs: https://v2.dataos.info/references/resources/nilus/batch/custom-sources/creating-custom-source

## Workflow

1. Collect: pipeline kind (`batch` / `cdc` / `stream` / `metadata`), source, sink (**omit for metadata**), address form (depot vs URI; CDC prefers depot), tables, write strategy, compute, secrets, schedule, whether a PVC is needed, columns to mask, columns that need `type_hints`.
2. If they need a **custom source**, follow [references/custom-source.md](references/custom-source.md): write the Python connector first, then the YAML. Copy [templates/custom-source.py](templates/custom-source.py) and [templates/custom-source-pipeline.yml](templates/custom-source-pipeline.yml).
3. If a first-party connector is named (Jira, Kafka, Salesforce, …), read `docs/connectors/<name>.md` before inventing `source_table` values.
4. Draft the smallest valid YAML. Start from a file in [templates/](templates/) when one matches. Validate mentally against the **DataOS domain allowlist** in [references/domain.md](references/domain.md), not the inner Nilus CLI schema.
5. Show the YAML (and Python, if any). Do not apply to a cluster unless the user asks.
6. Never write real passwords, tokens, or key material into YAML or chat. Use `{ENV_VAR}` placeholders and `use.projection`.

## Envelope

```yaml
name: <kebab-case-name>          # DataOS resource name
version: v1alpha
type: nilus                      # always this
tags: [workflow, nilus-batch]    # or service / nilus-cdc
description: <one line>
spec:
  type: batch                    # batch | cdc | stream | metadata
  compute: <existing-compute>    # do not invent; ask if unknown
  logLevel: ERROR                # DEBUG | INFO | WARNING | ERROR
  source:
    address: <uri-or-depot>
    options: {}
  sink:                          # required for batch / cdc / stream; never on metadata
    address: <uri-or-depot>
    options:
      dest_table: schema.table   # batch SQL/lakehouse. CDC: schema only
      incremental_strategy: replace
```

Required on the domain: `spec.type`, `spec.compute`, `spec.source.address`.  
`spec.sink` is required for `batch` / `cdc` / `stream`. A **metadata** pipeline never has a `sink` section.  
`mode: shallow | deep` is required when `spec.type` is `metadata`.

`spec.type` maps to a DataOS runtime:

| `spec.type` | Runtime | Typical tags |
|---|---|---|
| `batch` | workflow | `workflow`, `nilus-batch` |
| `cdc` | service | `service`, `nilus-cdc` |
| `stream` | worker | `worker`, `nilus-stream` |
| `metadata` | workflow + DAG | `workflow`, `nilus-metadata` |

## Hard rules (cluster domain)

The DataOS `nilus` domain schema sets `additionalProperties: false` on `source.options` and `sink.options`. Unknown keys **quarantine the apply**.

**Do not put these in `source.options`:**

- `schema_naming` — project `SCHEMA_NAMING` as an env var instead
- `columns` — renamed to `type_hints`; `columns` is rejected by Nilus
- `engine`, `type`, `service_name`, or any connector-specific key not on the allowlist

**Do not put these in `sink.options`:**

- `incremental_key`, `primary_key`, `interval_start`, `interval_end` — these belong in **`source.options`**
- `incremental_strategy: delete+insert` or `scd2` — runtime supports them; **domain enum is only** `replace` | `append` | `merge`

If a needed Nilus flag is not on the allowlist, project it as env:

```yaml
use:
  projection:
    projections:
      envVars:
        - key: SCHEMA_NAMING
          template: "direct"
```

Full allowlists: [references/domain.md](references/domain.md).

## Addresses

Two valid `source.address` / `sink.address` forms:

| Form | When | Example |
|---|---|---|
| Depot | Depot type exists and is already applied | `dataos://cdc12pgdepot?purpose=rw` |
| Direct URI | No depot type (DB2), or they have not created a depot | `db2://{USER}:{PASS}@host:50000/SAMPLEDB` |

Prefer a depot when one exists. Use a URI when the engine has no depot type (DB2), or they have not created one.

**CDC addresses:** use a depot for every depot-supported source (Postgres, MySQL, Mongo, MSSQL, …). A URI technically works, but depot is the recommended practice. **DB2 is the exception** — there is no DB2 depot type, so CDC source must be `db2://{USER}:{PASS}@…`.

URI credentials **must** be interpolated. Never paste passwords into the manifest (even URL-encoded). Pair the URI with `use.projection`:

```yaml
use:
  projection:
    secrets:
      - id: <workspace>:<secret-name>
        contextAlias: db2secret
    projections:
      envVars:
        - key: DB2_USER
          template: "{{ secrets['db2secret'].username | base64_decode }}"
        - key: DB2_PASSWORD
          template: "{{ secrets['db2secret'].password | base64_decode }}"
source:
  address: db2://{DB2_USER}:{DB2_PASSWORD}@host:50000/SAMPLEDB
```

Percent-encode reserved characters in the **secret value** (`@` → `%40`) so the interpolated URI stays valid.

Templates: [templates/batch-uri.yml](templates/batch-uri.yml), [templates/cdc-db2-uri.yml](templates/cdc-db2-uri.yml). Schemes: [references/domain.md](references/domain.md).

## Tables and writes

- SQL `source_table`: `"schema.table"`
- API sources: use the connector table name (`issues`, `issue_types`, …)
- Custom SQL: `"query:SELECT …"` — batch only; see `docs/connectors/custom_queries.md`
- `dest_table` is destination-specific:
  - Batch SQL / lakehouse: `schema.table`
  - Batch Mongo: `database.collection`
  - Custom source: **schema only** — resource `table_name` wins
  - **CDC: schema only** (`testing_nilus`, `nilus_cdc_sink`). The loaded table name comes from the topic / source object (`{topic}_{src_schema}_{src_table}`). A table segment in `dest_table` is ignored.
- `incremental_strategy` (sink):
  - `replace` — snapshot / small tables (runtime default). **Not valid for CDC** (CDC accepts only `append` or `merge`)
  - `append` — add rows; set `source.options.incremental_key` to avoid re-extracting the whole table
  - `merge` — requires `source.options.primary_key`. Add `incremental_key` when the extract should be incremental
- `full_refresh: true` (sink) resets the **cursor**, not the same as `replace`. One-off repair only.

### `type_hints`

`source.options.type_hints` overrides inferred types. It is **not** a rename map.

Supported types: `text`, `bigint`, `bool`, `timestamp`, `date`, `decimal`, `double`, `binary`, `json`, `time`.

```yaml
source:
  options:
    source_table: public.users
    type_hints:
      updated_at: timestamp
      amount: decimal
      payload: json
```

Hint only ambiguous columns. Keys are the **extracted** column names (SQL alias / source field). `SCHEMA_NAMING` still renames the destination separately. `columns` is rejected. Type hints are skipped on Debezium/CDC (`pipeline.py`).

To keep source identifiers as-is:

```yaml
use:
  projection:
    projections:
      envVars:
        - key: SCHEMA_NAMING
          template: "direct"
```

To **rename**, alias in SQL **and** set `SCHEMA_NAMING=direct`:

```yaml
source:
  options:
    source_table: "query:SELECT [p_Key] AS pKey, name FROM dbo.t"
```

Without `direct`, `pKey` becomes `p_key`. Full rules: [references/options.md](references/options.md#type_hints). Template: [templates/batch-type-hints.yml](templates/batch-type-hints.yml).

## Data masking

Mask in flight under **`source.options.mask`**. The domain rejects `mask` on `sink.options`.

**Batch: works.** CDC on `type: nilus`: **does not mask today.** The domain accepts `source.options.mask` and the service starts, but the Debezium path builds a fresh `cdc_source_flattened(records)` per batch, so the startup `add_map(masking_filter)` never runs on those rows. Snapshot and streaming both write plaintext. Do not tell testers CDC masking works on `type: nilus`. Official pages that put `mask` on the sink are describing a different/experimental domain.

```yaml
source:
  options:
    source_table: public.users
    type_hints:
      salary: bigint
    mask:
      email: hash
      phone: "partial:3"
      ssn: ssn
      salary: "round:5000"
```

Quote algorithm values that contain `:`. Pair a type hint when the algorithm changes representation (`hash`/`uuid`/`range`/`month_year` → `text`, `sequential`/`year_only` → `bigint`).

Common algorithms: `hash`, `md5`, `email`, `phone`, `ssn`, `credit_card`, `redact`, `partial:N`, `round:N`, `uuid`, `sequential`, `year_only`, `month_year`. Full list: [references/options.md](references/options.md#data-masking).

Source data is unchanged. Dest gets only masked values **on batch**. Template: [templates/batch-mask.yml](templates/batch-mask.yml).

## Source and sink options

Start with `source_table` + `dest_table` + `incremental_strategy`. Add other keys only when needed.

| Need | Keys |
|---|---|
| Incremental / merge | source `primary_key` (merge); `incremental_key` for incremental extract; sink `incremental_strategy` |
| Backfill window | source `interval_start` / `interval_end` (requires `incremental_key`) |
| Types / PII | source `type_hints`, `mask` (batch only) |
| Nested JSON / Mongo | source `max_table_nesting` — `"0"` keeps nested as JSON (quoted string) |
| Sample a run | source `sql_limit` or `yield_limit`; `sql_exclude_columns` |
| Iceberg layout | sink `partition_by`, optional `cluster_by` |
| OOM / slowness | `page_size`, `extract_parallelism`, `loader_file_size` — see [references/options.md](references/options.md) |

Do not invent option keys. Do not put runtime env (`LOAD__WORKERS`, `DATA_WRITER__FILE_MAX_BYTES`) in options — project them as env vars.

## CDC

`spec.type: cdc`. Put Debezium properties under `source.cdc` (passthrough, extra keys allowed).  
`source.options.strategy`: `flatten` (typical) or `changelog`.  
Sink `incremental_strategy` must be `append` or `merge` (CDC raises on `replace`).  
Do **not** rely on `mask` or `type_hints` for CDC on `type: nilus` — both are skipped or no-ops on the Debezium path.  
Postgres CDC needs `table.include.list`, `topic.prefix`, `slot.name`.  
Mongo CDC uses `collection.include.list` instead of `table.include.list`.  
DB2 CDC has **no depot** and no replication slot; author `db2://…` (Nilus prefixes `debezium+` internally). That is the only CDC source that should use a URI by default.

For every other CDC source, put a **depot** on `source.address`. A URI works technically; do not use one unless they asked or no depot exists. `spec.type` stays `cdc`; do not write `debezium+` unless they already use that form.

CDC `sink.options.dest_table` is **schema only**.

## Metadata

`spec.type: metadata` plus `spec.mode: shallow` or `deep`.  
Never add a `sink` — metadata writes to the DataOS catalog, not a dest table.  
Do not set `source_table` unless they want a single Hera stage. Template: [templates/metadata.yml](templates/metadata.yml).

## Volumes (PVC)

Attach a DataOS `type: volume` so pipeline state (dlt working dir) survives pod restarts. Needed for large incremental/merge runs and anything that must keep local state.

1. Apply a volume on the **same dataplane** as `spec.compute` (template: [templates/volume.yml](templates/volume.yml)).
2. Mount it on the pipeline with `spec.use.volumes`.
3. Point `DATAOS_WORK_DIR` (and optionally `DATAOS_PERSISTENT_DIR`) at that mount.

```yaml
spec:
  use:
    volumes:
      - id: <workspace>:<volume-name>    # or the id from `ds2 resource get -t volume`
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

`directory` is the in-container mount path. `id` is the volume resource (name or `workspace:name`). If apply cannot resolve the name, use the identifier from `ds2 resource get -t volume`.  
Do not store secrets on the volume. Full notes: [references/domain.md](references/domain.md#volumes-pvc). Template: [templates/batch-pvc.yml](templates/batch-pvc.yml).

## Custom sources

Prefer a built-in connector or `query:SELECT …` if the system is SQL-accessible. Author a custom source only when auth, pagination, or the object model cannot be expressed that way.

Custom sources are **`spec.type: batch`**. Code lives in Git; Nilus clones `spec.repo` then imports the class named in `custom://<ClassName>`.

```yaml
spec:
  type: batch
  repo:
    url: https://bitbucket.org/org/repo
    baseDir: packages/my-connector/custom_source   # dir of *.py + optional requirements.txt
    secretId: <workspace>:<git-secret>             # private repos only
    syncFlags: ["--ref=main"]
  source:
    address: custom://MyCustomSource?api_token={API_TOKEN}
    options:
      source_table: orders                         # logical resource name
  sink:
    address: dataos://lakehouse?purpose=rw
    options:
      dest_table: raw                              # schema only; resource table_name wins
      incremental_strategy: replace
```

**Python contract** — full guide in [references/custom-source.md](references/custom-source.md):

1. Put `*.py` (and optional `requirements.txt`) in `baseDir`. Nilus loads **top-level** `.py` files only.
2. Subclass `CustomSource`. Class name must match the URI netloc exactly (`custom://MyCustomSource`).
3. Implement `nilus_source(self, uri, table, **kwargs)` and return a `@nilus.source`.
4. Yield one or more `nilus.resource(...)` with stable `name` / `table_name` and a `write_disposition`.
5. Parse connection params from the URI query (and env). Do **not** put connector-specific keys in `source.options` on `type: nilus`.
6. `handles_incrementality()` is `False` unless the source owns its own dlt cursor. If `True`, Nilus ignores YAML incremental strategy/key.

`spec.repo.secretId` authenticates **git-sync only**. Keys must be `GITSYNC_USERNAME` and `GITSYNC_PASSWORD`. Source/sink secrets stay on the URI or `use.projection`.

When the user asks to **create the connector itself**, write the Python first, then the pipeline YAML. Do not generate docker-compose or local mock servers unless they ask.

## Defaults when the user does not specify

- `type: nilus` / `version: v1alpha` / `spec.type: batch`
- `logLevel: ERROR` for a first test run
- `incremental_strategy: replace` unless they asked for incremental
- resources: requests `200m` / `256Mi`, limits `1000m` / `1Gi`
- `compute`: ask if unknown; do not copy `runnable-default` from docs unless that compute exists
- `schedule`: omit (instance run) unless they want a cron

## Do not

- Put credentials in the manifest (including inside a URI)
- Add a `sink` section to a metadata pipeline
- Default CDC `source.address` to a URI when a depot exists (DB2 is the URI exception)
- Put `schema.table` on CDC `dest_table` — schema only
- Use `type: workflow` + `stack: nilus` (legacy)
- Use hyphenated inner keys (`source-table`, `dest-table`) on `type: nilus`
- Treat `--columns` / `type_hints` as a rename map
- Put `mask` under `sink.options` on `type: nilus` (domain rejects it)
- Promise CDC masking on `type: nilus` (accepted by schema, not applied)
- Add `page_size` / `partition_by` / `full_refresh` without a reason
- Drop lakehouse tables or apply resources unless asked
- Invent `source_table` names for API connectors
- Put connector-specific keys (`api_token`, `survey_ids`, …) in `source.options` on `type: nilus`
- Nest the `CustomSource` class only in a subdirectory that `baseDir` does not scan

## After drafting

State in one short block: pipeline kind, source → dest, strategy, secrets used (names only), masks / type hints, and any allowlist workaround (`SCHEMA_NAMING` env, etc.).
