# Read-only command mapping

These commands were verified against the DataOS CLI source used for this project. The deployed observer calls the equivalent tenant-scoped Poros GET endpoints because its minimal runtime image does not contain the CLI binary.

| Evidence | Operator-side CLI equivalent | Runtime use |
|---|---|---|
| Resource definition and status | `dataos-ctl resource get -i TYPE:VERSION:NAME -d` | Always |
| Runtime and container groups | `dataos-ctl resource get runtime -i TYPE:VERSION:NAME -d` | Runnable built-in and dynamic resource types, including Vulcan |
| Recent logs | `dataos-ctl resource log -i TYPE:VERSION:NAME -l 80` | Runnable resources; bounded and non-following |
| Dependency graph | `dataos-ctl resource deps --id TYPE:VERSION:NAME` | When available |
| Vulcan catalog / schema / lineage / quality | DataOS Assist `dataos_dp_search`, `dataos_dp_schema`, `dataos_dp_lineage`, `dataos_dp_quality` | Vulcan products; read-only enrichment when available |

Do not add `--unSanitize`, `--follow`, `--tls-allow-insecure`, mutation subcommands, or runtime directives.

## Interpretation notes

- `crashing:0/1`, explicit failure states, or fewer running than desired replicas are immediate failure evidence.
- A Vulcan product with `vulcan-api:running` and `vulcan-plan:failed` is unhealthy; API availability does not cancel the failed plan signal.
- Pending, queued, initializing, provisioning, starting, reconciling, or waiting is an incident only after the configured threshold.
- HTTP 403 means the application identity lacks that read capability; preserve the denial as evidence and stop that branch.
- HTTP 404 may mean that a capability is not supported for the resource type. It does not prove that the resource itself is absent.
- An empty log response is unknown evidence, not proof of health.
- Never persist or send complete raw logs to the model. Use a bounded, redacted excerpt relevant to the detected failure.
