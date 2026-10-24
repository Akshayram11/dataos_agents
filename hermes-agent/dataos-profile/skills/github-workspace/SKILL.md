---
name: github-workspace
description: Work safely with connected GitHub repositories.
version: 0.1.0
author: Akshay Chame
license: MIT
metadata:
  hermes:
    tags: [github, git, repositories]
    category: software-development
---

# GitHub Workspace Skill

Use `terminal` for Git operations against the GitHub repository connected from
**Repository Workspace** in the dashboard. The checkout persists under
`$HERMES_HOME/workspace/repos`. Never ask for or store repository credentials in
chat; the configured `GIT_ASKPASS` bridge supplies the saved token.

## When to Use

Use when the user asks to inspect, edit, validate, commit, or push an explicitly
identified GitHub repository.

## Prerequisites

- The repository and fixed branch are configured in the authenticated Repository Workspace UI.
- Confirm the checkout exists under `$HERMES_HOME/workspace/repos` before editing.
- Inspect `git remote get-url origin`, the current branch, and `git status` before work.
- Run `vulcan` inside the checkout for offline DataOS product validation.
- Use an isolated branch or worktree for changes unless the user explicitly selected a writable working branch.

## Procedure

1. Verify the origin is a credential-free `https://github.com/owner/repository.git` URL.
2. Fetch without changing the working tree; never put the token in a command or remote URL.
3. Read repository instructions and relevant files before editing.
4. Apply the smallest requested change and run repository-defined checks plus relevant Vulcan validation.
5. Show the diff, validation results, destination repository, and branch.
6. Obtain explicit user approval before creating a commit or pushing it.
7. Push only to the approved repository and branch; never force-push or bypass branch protection.
8. Create a pull request only when a verified GitHub API capability is available and the user separately approves it.

## Forbidden

Never reveal credentials, place credentials in URLs or Git config, commit secrets,
rewrite history, force-push, delete branches, bypass protections, or merge without
exact approval.

## Verification

Report repository, branch, commit SHA if created, checks executed, push result, and
whether pull-request creation was performed or remains unavailable.
