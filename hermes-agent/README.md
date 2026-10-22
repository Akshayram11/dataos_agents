# DataOS Hermes

Lean, DataOS-specific distribution of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) for persistent operational and agent-building bots.

## What remains

- Persistent profiles, memory, cron, delegation, sessions, gateway/web UI, and Git worktrees.
- OpenAI model access, defaulting to `gpt-5.6-luna` in the DataOS profile.
- Explicitly allowlisted DataOS CLI MCP, Arguss consumption MCP, and DataOS GitBook MCP connections.
- Bitbucket access through an operator-configured SSH identity or credential helper.
- Six DataOS skills for evidence, CLI operation, governed consumption, agent creation, bot orchestration, and Bitbucket workspaces.

Generic bundled skills, desktop/product surfaces, evaluation suites, test trees, documentation-site sources, translated project documents, Nix/Windows packaging, and unrelated development metadata have been removed from this branch or excluded from the sparse checkout.

## DataOS profile

The deployable profile source is [`dataos-profile/`](dataos-profile/README.md). Validate it without credentials or network access:

```bash
python3 dataos-profile/scripts/validate.py
```

Install it into a prepared Hermes runtime:

```bash
hermes profile install ./dataos-profile --name dataos --alias
```

Credentials must be supplied outside Git. Use a dedicated, least-privilege DataOS identity; do not reuse a human administrator key for an always-on agent.

## DataOS application

The application templates are in [`deploy/`](deploy/README.md). The custom image embeds the same pinned `dataos-ctl` binary used by the existing DataOS agents; its immutable source image and verified version are recorded in [`deploy/runtime.lock.json`](deploy/runtime.lock.json).

## Upstream

This work is based on NousResearch Hermes Agent at commit `6932521f258cca074ed206254b329d5b3b982eac` and retains the upstream MIT license. Core runtime code remains upstream-compatible; DataOS behavior is packaged as a profile distribution instead of being mixed into the agent core.
