---
name: agent-prd
description: Produce a concise approval-ready PRD for a DataOS AI agent from discovered requirements and verified platform evidence.
---

# Agent PRD

Generate a decision-ready PRD before producing deployable artifacts. It must be understandable without the chat transcript and include:

1. problem and measurable outcome;
2. users and access boundary;
3. in-scope and out-of-scope behavior;
4. user journey;
5. proposed DataOS architecture and component rationale;
6. tools, MCP servers, and deterministic tool order;
7. credentials, identity, grants, secret storage, and data sent to the model;
8. state, audit, token usage, and cost behavior;
9. generated resources and deployment order;
10. acceptance tests, failure handling, rollback, and open assumptions.

For every DataOS-specific claim, record its provenance as user-provided, MCP evidence, schema, or bundled documentation. Platform unknowns must remain unresolved; never convert them into assumptions. Non-platform design recommendations must be labelled `Recommendation` and must not be presented as existing DataOS behavior. A PRD is `draft` until the user presses the explicit approval action. Editing requirements after approval invalidates that approval.

Do not place secret values, API keys, bearer tokens, or hidden runtime credentials in the PRD.
