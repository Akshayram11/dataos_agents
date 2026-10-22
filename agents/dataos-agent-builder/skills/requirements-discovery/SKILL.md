---
name: requirements-discovery
description: Discover and structure requirements for a DataOS AI agent before architecture, generation, or deployment begins.
---

# Requirements discovery

Turn the user's desired outcome into a buildable agent brief. Ask only the smallest useful next question and reuse facts already supplied.

## Evidence discipline

Use only these sources for factual claims:

1. facts explicitly supplied by the user in the current conversation;
2. results returned by the connected DataOS MCP tools for the configured tenant;
3. bundled DataOS documentation or package documentation that identifies its source and version.

Do not fill gaps with general software, cloud, security, or environment terminology. In particular, never introduce environment names, lifecycle stages, DataOS components, resource types, roles, approval authorities, permission names, or platform capabilities unless one of the sources above establishes them. Do not present model knowledge as DataOS knowledge.

When a platform fact is unknown, first use an available read-only tool if it can answer the question. Otherwise mark it `Unverified` and ask an open question only when the answer materially changes the design. Never offer invented multiple-choice options. Clearly distinguish a user requirement from a verified platform fact and from an agent-design recommendation.

Capture these decisions before declaring discovery complete:

- business outcome and primary users;
- target tenant;
- how the user wants to interact with or trigger the agent, described in the user's own terms;
- data products and platform capabilities the agent must access;
- read-only, controlled-write, and explicitly forbidden actions;
- persistence, notifications, audit, cost, and latency expectations;
- preferred model/provider and whether user-supplied credentials are required;
- owner-only or group access;
- observable acceptance criteria.

Use read-only platform and documentation tools when live facts would change the design. If the user requests a privileged operation, inspect the available tool catalog and current schemas before claiming that the operation is supported. Do not ask for an API key in chat. Credentials belong only in the private Connections form.

Do not invent a platform default. A reversible product-design choice may be proposed only when it is labelled `Recommendation` with its rationale; it must never be described as existing DataOS behavior. Never infer permission to deploy from permission to generate a design.
