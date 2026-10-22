---
name: platform-architecture
description: Select DataOS components and existing capabilities for an AI agent from verified platform documentation, schemas, and live tenant state.
---

# Platform architecture

Choose the smallest architecture that satisfies the approved outcome. Establish tenant context, search current DataOS documentation, inspect existing resources, and fetch current schemas before recommending a resource shape. Every recommended DataOS component must be supported by tool evidence, a current schema, or bundled source-identified documentation.

The following mappings are available only after the named component and required schema have been verified for the connected tenant:

- HTTP/chat or continuously available API: Service plus private ingress/Link.
- recurring bounded work: Workflow.
- continuously processing background work: Worker.
- durable agent state: stateful disk or a separately governed store.
- governed data-product consumption: Arguss/Vulcan MCP read-only tools.
- platform inspection or deployment: dataos-ctl MCP tools under explicit gates.
- reusable behavioral knowledge: versioned skills packaged with the application.

When the outcome includes designing, building, or repairing a Vulcan data product, route through the official `dataproduct-builder-skills` package and its `design-data-product`, `build-data-product`, or `fix-data-product` skill. Do not ask the consumption MCP to scaffold a data product.

Prefer an existing approved MCP, template, compute, or platform service when it meets the requirement. Explain reuse versus build-new tradeoffs. Never invent resource fields from model memory; use documentation and `dataos_schema_get`.

If evidence is unavailable, say that the component choice is unverified and leave it unresolved. Do not substitute generic cloud architecture, generic environment stages, or assumed organization roles.

Keep the application identity distinct from its human owner. Design permissions from required tool calls, not from broad job titles.
