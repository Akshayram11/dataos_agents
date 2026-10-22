# Authoring a Nilus custom source

Use when the user wants the **Python connector**, not only the pipeline YAML.

Official docs: [Building a custom source](https://v2.dataos.info/references/resources/nilus/batch/custom-sources/creating-custom-source).  
Nilus loads the class via `nilus/src/factory.py` (`custom://` netloc = class name; `baseDir` = top-level `*.py`).

If the system is JDBC/SQL and a query is enough, use `source_table: "query:SELECT …"` instead.

Starting files: [templates/custom-source.py](../templates/custom-source.py) and [templates/custom-source-pipeline.yml](../templates/custom-source-pipeline.yml).  
Pipeline rules: [../SKILL.md](../SKILL.md). Domain allowlist: [domain.md](domain.md).

## Philosophy

A custom source is a thin adapter around extraction logic the team owns:

- **One job**: turn an upstream system into stable row/document streams.
- **The class is a loader hook**. `CustomSource` only parses config and returns a `@nilus.source`. HTTP clients, SQL, pagination, and transforms live in helpers beside it.
- **Resources own the dataset identity**. Each `nilus.resource` sets `name`, `table_name`, and `write_disposition`. Downstream tables come from those names, not from `sink.options.dest_table`.
- **Yield a predictable shape**. Same keys every row. Nesting that would explode Iceberg/SQL columns should be serialized (JSON string) unless the user asked for flattened fields.
- **Stream**. Paginate, server-side cursors, or file streams. Do not build giant in-memory lists.
- **Retries must be safe**. No duplicate side effects upstream. Persist only the minimum cursor if incremental.
- **Secrets stay out of code**. URI `{ENV}` interpolation or env fallbacks. Never commit tokens.

`nilus` is a dlt alias (`import nilus` → `@nilus.source` / `@nilus.resource`). Prefer `nilus_*` method names; `dlt_source` still delegates for compatibility.

## Layout

`spec.repo.baseDir` must be the directory that contains the implementation. Nilus lists **only that directory’s `*.py` files** (not nested packages) and installs `requirements.txt` if present.

```text
packages/<connector>/custom_source/
├── my_source.py          # CustomSource subclass + @nilus.source
├── requirements.txt      # optional, runtime-installed
└── helpers.py            # optional; must be importable from a top-level .py
```

The subclass **must be visible** on a top-level module Nilus loads (`dir(module)` finds it). If you split files, import the class from a top-level `.py` or define it there.

Class name is PascalCase and **exactly** the URI host:

```text
custom://QualtricsApiCustomSource?api_token={TOKEN}
```

matches `class QualtricsApiCustomSource(CustomSource)`.

## Contract

```python
from nilus import CustomSource

class CustomSource:
    def handles_incrementality(self) -> bool:
        return False

    def nilus_source(self, uri: str, table: str, **kwargs):
        raise NotImplementedError
```

| Piece | Rule |
|---|---|
| `nilus_source(uri, table, **kwargs)` | Required. `uri` is the full `custom://…` string. `table` is `source.options.source_table`. Return a `@nilus.source`. |
| `handles_incrementality()` | `False` unless this source manages its own dlt state. `True` makes Nilus set incremental strategy to `none` and ignore YAML `incremental_key`. |
| Resources | Yield 1..N `nilus.resource(fn, name=…, table_name=…, write_disposition=…)`. `table_name` is the dest table. |
| Params | Connection/auth/filter on the **URI query**. `source.options` on `type: nilus` only accepts the domain allowlist (`source_table`, `type_hints`, `mask`, incremental keys, …). Extra keys quarantine the apply. |
| Output | Dict rows or Arrow batches. Keep columns stable. |

### `dest_table` for custom sources

Nilus patches destinations so **resource `table_name` wins**. Set `sink.options.dest_table` to the destination **schema** (`raw`, `testing_nilus`). A `schema.table` value is misleading: the table segment is ignored.

### Repo vs source secrets

- `spec.repo.secretId` → git-sync only. Secret keys: `GITSYNC_USERNAME`, `GITSYNC_PASSWORD`.
- Source credentials → `custom://Class?api_token={TOKEN}` plus `use.projection` env vars. Never reuse the repo secret for API auth.

## Incremental (only if needed)

```python
def handles_incrementality(self) -> bool:
    return True

@nilus.resource()
def fetch_incremental():
    state = nilus.current.resource_state()
    last_id = state.get("last_id")
    for item in get_after(last_id):
        yield item
        state["last_id"] = item["id"]
```

Store only the cursor. Do not dump full payloads into state.

## Practices

Patterns from team custom sources (minimal example, SQL extract, multi-table API). Ignore docker-compose / mock servers unless asked.

**Structure**

- Thin `CustomSource`: parse URI → dataclass/config → return `@nilus.source`.
- One resource per dest table. Stable `table_name` so runs do not collide.
- Frozen dataclass for connection/query settings (host, days, batch size, endpoints).
- Optional `requirements.txt` with pinned extras only (`requests`, `ijson`, `psycopg2-binary`). Nilus/dlt are already in the runtime.

**Config**

- URI query for runtime knobs (`days`, `batch_size`, `survey_ids`, tokens).
- Env fallbacks for the same knobs so local and cluster agree.
- Fail fast with a clear `ValueError` when a required secret is missing.
- Document required URI params in the class docstring.

**Extraction**

- SQL: push filters into the database; stream with a server-side cursor; prefer one query over collect-then-IN-list.
- HTTP: session + retries on 429/5xx, honor `Retry-After`, timeout every call.
- Large payloads: stream to disk / `ijson`; do not `json.load` a multi-GB export.
- Wide or irregular JSON: store as a `payload` string column plus a few identity columns (`survey_id`, `extracted_at`).
- Pagination loops until empty; yield per item or per Arrow batch.

**Resilience**

- Close connections in `with` / `finally`.
- Decide skip-vs-abort per entity (log and continue vs fail the run) and keep it consistent.
- Progress logs should `flush=True` so cluster logs move during long extracts.

**Do not**

- Hardcode production tokens or customer endpoints in committed defaults if they can live on the URI (constants are OK for a tenant-owned fork when documented at the top of the file).
- Return different column sets across rows of the same resource.
- Put `api_token` / `survey_ids` under `source.options` on a DataOS `type: nilus` manifest.
- Implement incrementality in YAML **and** in the source (`handles_incrementality=True` disables YAML incremental).
- Generate compose files, mock APIs, or local volume mounts unless requested.

## Agent workflow

1. Confirm no built-in connector or `query:` path fits.
2. Name the class, resources/tables, write disposition, and URI params.
3. Copy [templates/custom-source.py](../templates/custom-source.py) into `baseDir` and add `requirements.txt` if needed.
4. Copy [templates/custom-source-pipeline.yml](../templates/custom-source-pipeline.yml) and fill `repo`, `custom://ClassName`, schema-only `dest_table`.
5. List required secrets (git-sync vs source) by **name only**.
