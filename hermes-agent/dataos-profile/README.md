# DataOS Hermes Profile

This is the lean DataOS-specific layer for Hermes Agent. It keeps persistent profiles, memory, skills, cron, delegation, MCP, Git worktrees, and the web/gateway runtime while constraining the agent to verified DataOS evidence.

The distribution opts out of Hermes' non-essential bundled skills. A running
DataOS profile receives the essential Hermes runtime skill, seven application
skills (including the pinned Nilus workflow), and the three pinned
`dataproduct-builder-skills` workflows. Their version-matched grounding
material is stored under `/opt/data/hermes/dpbs-docs`.

## Connections

- `dataos-cli`: local `dataos-ctl develop assist mcp run` over stdio.
- `dataproduct-mcp`: the tenant Data Product MCP over HTTPS, authenticated by
  the DataOS key saved in the profile's Keys UI.
- `dataos-docs`: the official DataOS GitBook MCP over HTTPS.
- Bitbucket: standard Git over an operator-configured SSH identity or Git credential helper.

Credentials are profile-local and never shipped in this distribution.

## Security boundary

- The CLI MCP exposes only inspection, schema/lint, bounded diagnostics, depot health, and `dataos_resource_apply`.
- `dataos_resource_apply` must run in lint mode before an explicit, target-specific user approval permits deployment.
- Secret, API-key, user, tenant, delete, and runtime-stop tools are not available to the model.
- The Data Product MCP is pinned to its reviewed data-product tools; GitBook is pinned to three read-only documentation tools.
- Use a dedicated least-privilege DataOS app user. For a shared or production host, isolate the whole Hermes process/container; prompts and in-process approval checks are not a security sandbox.

## Install locally

```bash
hermes profile install ./dataos-profile --name dataos --alias
cp ~/.hermes/profiles/dataos/.env.template ~/.hermes/profiles/dataos/.env
chmod 600 ~/.hermes/profiles/dataos/.env
```

Fill the generated `.env` outside chat, then verify:

```bash
dataos doctor
dataos mcp status
dataos chat
```

## Persistent bots

Create one profile per persistent bot. Use the Agent Factory skill to produce its PRD, scoped skills, MCP allowlist, DataOS manifests, and verification plan. Do not clone credentials or running schedules between profiles.
