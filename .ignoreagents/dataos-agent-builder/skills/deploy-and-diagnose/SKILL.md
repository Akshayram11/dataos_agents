---
name: deploy-and-diagnose
description: Validate, deploy, observe, and safely diagnose approved DataOS agent resources without destructive recovery actions.
---

# Deploy and diagnose

Operate only after the PRD and generated revision are explicitly approved.

Sequence:

1. Confirm tenant and owner match the approved PRD.
2. Inspect current resources and identify create versus update. Provision only the deterministic approved application identity/access plan before resource apply.
3. Fetch the current schema for every resource type.
4. Lint/validate every manifest; stop before writes if any validation fails.
5. Apply dependencies before dependents.
6. After each apply, call resource get and runtime get when applicable.
7. If unhealthy, obtain bounded recent logs, diagnose from evidence, and propose the smallest correction.
8. Automatically retry only a safe generated configuration correction, at most twice. Permission expansion, architecture changes, destructive operations, or replacement of an unrelated existing resource require a new approval.
9. Verify acceptance criteria and report exact identifiers, state, evidence, token usage, and remaining risks.

A successful apply is not a successful deployment. Health and intended behavior must be verified. Never call delete, force, cascade, rollback, secret-read, IAM, tenant-management, or arbitrary shell capabilities.
