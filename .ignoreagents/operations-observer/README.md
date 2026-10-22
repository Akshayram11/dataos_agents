# DataOS Operations Observer

An always-on, single-tenant observer for the safe DataOS operational plane: Services, Workers, Workflows, Bundles, Apps, Compute, Dataplanes, Depots, Lakehouse, Minerva, Nilus, Stacks, Volumes, Vulcan data products and their dependency artifacts. Credential and IAM resource classes are intentionally excluded.

## Runtime behavior

1. Polls the tenant-scoped Poros resource API every 60 seconds using the projected application identity.
2. Opens a critical incident for explicit error/failure runtime states, including failed Vulcan plans even when the product API is still running.
3. Opens a warning when a pending/starting state exceeds 10 minutes.
4. Resolves an incident automatically after the resource recovers.
5. Stores resource snapshots, acknowledgements and up to 1,000 incidents on the stateful Service disk.
6. Calls the configured OpenAI model only for a newly opened incident. Monitoring itself never depends on the LLM.
7. Streams updates to the private dashboard with server-sent events.

New incidents are diagnosed with the bundled [`dataos-cli-diagnostics`](skills/dataos-cli-diagnostics/SKILL.md) skill. The runtime gathers the same read-only resource, runtime, bounded-log, and dependency evidence exposed by DataOS CLI through tenant-scoped Poros GET endpoints. For Vulcan products, the diagnostic contract also understands catalog, semantic-schema, lineage, quality, freshness and SLO evidence. The minimal Service image does not contain or shell out to a CLI binary.

The UI accepts an OpenAI key for the current process. It remains only in server memory, is never written to the state disk, and must be entered again after a Service restart.
The dashboard meters response-reported input, cached-input and output tokens for that process and shows an estimated USD cost using the verified GPT-5.6 Luna standard token rates. The estimate resets when a key is connected or the Service restarts; the OpenAI billing dashboard remains authoritative.

The installer also creates a tenant-scoped `Link` resource so the dashboard appears in
**Platform → Data Apps → engineering**. Browser navigation first loads an inert shell,
then sends the current same-origin DataOS OIDC bearer token to the app APIs. The server
validates that token with Heimdall and requires the exact configured owner ID before it
returns monitoring data or accepts an action.

## Deploy

Copy `environment.example.json` to an ignored `environment.json`, confirm the compute name, and use the real `dataos-ctl` binary rather than a local wrapper alias:

```bash
python3 install.py environment.json \
  --cli /path/to/dataos-ctl \
  --cli-config /Users/akshaychame/.dataos/v2 \
  --render-only

python3 install.py environment.json \
  --cli /path/to/dataos-ctl \
  --cli-config /Users/akshaychame/.dataos/v2 \
  --apply
```

The installer verifies the selected host and tenant, renders manifests, checks policy conflicts, creates a missing application identity, lints the Service, and then submits it. Submission is not readiness: verify the first successful scan and test access with both the owner and a different tenant user.

## Local tests

```bash
node --test runtime/server.test.mjs
python3 -m unittest discover -s tests -v
```
