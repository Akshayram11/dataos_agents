# Access and security model

## Human access

Only the literal DataOS user in `operator_id` may use the dashboard API routes. For this deployment that user is `akshaychametmdcio`; wildcards are rejected. A top-level browser navigation cannot attach an Authorization header, so network authorization is disabled only at the ingress layer to let the inert HTML/CSS/JavaScript shell load. Every `/api/*` request supplies the current same-origin DataOS OIDC token, which the server validates with Heimdall and compares to the exact owner ID. Missing, expired, invalid, or non-owner credentials fail closed. The bearer token is never placed in a URL, persisted, logged, or returned.

## Runtime identity

The Service runs as the distinct application identity in `agent_id`. Its policy bundle contains twelve allow policies and no deny or mutation rule. Runtime capabilities are limited to:

- read status, runtime and bounded logs for explicitly allowlisted operational resource types;
- GET the tenant-scoped resource/runtime endpoints;
- use the configured compute;
- list and read operational metadata for Apps, Bundles, Compute, Dataplanes, Depots, Lakehouse, Links, Minerva, Nilus, Services, Stacks, Volumes, Vulcan products, Workers and Workflows.

It receives no create, update, delete, apply, grant-management, IAM, credential-payload or Git permission. Secret, Grant, Role and User resources are not part of the monitor allowlist.

## Credentials

The DataOS API key is projected by `runAsUser`; no personal operator key enters the container or browser. The human OIDC bearer token is used only to authorize incoming UI API requests. The OpenAI key is accepted only through the private UI, kept in process memory, never returned by an API, and lost on process restart.

## Persistence and fail-closed deployment

The Service is single-replica and stateful; DataOS provides its `/etc/dataos/work` persistent work volume. Incident state is written atomically with mode `0600`. The installer first lints the rendered manifest and stops on policy conflicts or target mismatch.
