# DataOS source policy

Use sources in this order:

1. Current user requirements.
2. Live results from `mcp__dataos_cli__*` for tenant and resource state.
3. Live results from `mcp__dataos_consumption__*` for governed data-product discovery and consumption.
4. Current DataOS documentation from `mcp__dataos_docs__*`.
5. Repository evidence from the connected workspace.

Do not use model memory to fill a DataOS-specific gap. A source conflict is resolved in favor of current live schema/state, then current official documentation. Report the conflict instead of silently choosing.

Credential values are never valid evidence and must never appear in a plan, generated file, tool trace, commit, or response.

