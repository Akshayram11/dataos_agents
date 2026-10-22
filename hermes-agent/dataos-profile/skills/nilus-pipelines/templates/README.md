# Templates

Copy a file, then replace compute, depot, secret, and table names. Do not apply as-is.

| File | Use when |
|---|---|
| `batch-depot.yml` | Depot → depot batch replace |
| `batch-uri.yml` | Direct `postgresql://` source URI + depot sink |
| `batch-schema-naming.yml` | Keep source identifiers (`SCHEMA_NAMING=direct`) |
| `batch-merge.yml` | Incremental merge |
| `batch-type-hints.yml` | `type_hints` on merge columns |
| `batch-mask.yml` | In-flight masking + matching type hints |
| `batch-sample.yml` | `sql_limit` / exclude columns for a validation run |
| `batch-partition.yml` | Lakehouse `partition_by` + `cluster_by` |
| `batch-query-rename.yml` | SQL `query:` plus column alias |
| `batch-jira.yml` | API source + secret projection |
| `batch-scheduled.yml` | Cron + URI secrets + masking |
| `batch-pvc.yml` | Batch with a mounted volume / PVC |
| `volume.yml` | DataOS `type: volume` (apply before `batch-pvc.yml`) |
| `cdc-postgres.yml` | Postgres CDC (depot source; `dest_table` is schema only) |
| `cdc-mongo.yml` | Mongo CDC → lakehouse (depot; schema-only `dest_table`) |
| `cdc-db2-uri.yml` | DB2 CDC via URI (no depot type) → Postgres depot |
| `metadata.yml` | Hera / metadata pipeline — no `sink` |
| `custom-source-pipeline.yml` | Custom source batch + repo sync |
| `custom-source.py` | `CustomSource` skeleton |
| `git-sync-secret.yml` | Private-repo git-sync secret |
