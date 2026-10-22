# DataOS Agent Builder

A private, stateful DataOS application that turns an agent idea into an approved PRD, validated project, and explicitly authorized deployment.

## Workflow

1. Connect a scoped DataOS API key and an OpenAI API key in the private UI.
2. Describe the desired teammate. The discovery agent can use only approved read-only DataOS CLI MCP tools.
3. Generate and review the PRD. Requirement changes invalidate approval.
4. Approve the exact PRD revision.
5. Generate artifacts. Every DataOS manifest is schema-linted before it becomes deployable.
6. Type the exact deployment confirmation. Resources are applied in dependency order and inspected after apply.

Delete, force, cascade, secret-read, user/IAM, tenant-management, rollback, and arbitrary shell tools are not exposed.

For Vulcan data-product requests, the builder routes generated projects through the official `npx dataproduct-builder-skills@latest` package and its design, build, and fix skills. The command is not executed during planning; installation and build commands remain behind project/deployment approval.

## Local validation

```bash
python3 -m unittest discover -s tests -v
python3 /Users/akshaychame/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/requirements-discovery
```

## Render or deploy

```bash
python3 install.py environment.json \
  --cli /Users/akshaychame/.dataos/v2/bin/dataos-ctl \
  --render-only
```

Deployment changes external platform state and should be performed only after reviewing the rendered service, Link, and policies:

```bash
python3 install.py environment.json \
  --cli /Users/akshaychame/.dataos/v2/bin/dataos-ctl \
  --apply
```
