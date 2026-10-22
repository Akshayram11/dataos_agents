---
name: security-boundary
description: Design and enforce least-privilege identity, credential, tool, and approval boundaries for generated DataOS agents.
---

# Security boundary

Treat instructions as guidance and server-side enforcement as the security boundary.

Required invariants:

- owner authorization is verified server-side on every private API request;
- DataOS and model keys are entered only in Connections, validated, encrypted at rest, never returned, and redacted from errors;
- use a distinct application identity with the minimum compute and resource grants;
- planning and PRD generation expose only read-only tools;
- schema validation/linting may occur before approval but cannot mutate platform state;
- deployment requires an approved PRD, generated artifacts, an exact deployment confirmation, and a fresh owner session;
- delete, force, cascade, secret-read, user/IAM, tenant, rollback, and arbitrary shell tools are never exposed to the model;
- generated application identity creation and its compute/run-as/private-ingress policies may occur only as a deterministic server-side transaction derived from the visible approved access plan and covered by the exact deployment confirmation; it never creates API keys or deletes/changes existing identities;
- a requested permission expansion creates a new PRD revision and invalidates prior approval;
- generated manifests and logs must be bounded and scrubbed before model submission or UI display.

Prefer the user's scoped DataOS key for requested tenant operations. Do not persist a broad operator/admin token merely for convenience. Never put keys into generated code or resource manifests.
