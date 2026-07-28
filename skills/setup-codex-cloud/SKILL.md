---
name: setup-codex-cloud
description: Prepare a repository for Codex Cloud and GitHub @codex PR remediation by detecting its runtimes, lockfiles, package managers, and validation scripts; generating idempotent .codex/cloud setup and maintenance scripts; and adding a bounded Codex Cloud section to AGENTS.md. Use when the user says setup Codex Cloud, make @codex fixes work, configure a cloud environment, bootstrap a repository for Codex, or audit cloud readiness.
---

# Setup Codex Cloud

## Overview

Generate repository-owned, reviewable bootstrap files so a Codex Cloud task can install dependencies consistently. This skill configures the repository; the user must still create or select the hosted environment in Codex settings and grant the GitHub app write access before `@codex fix` can push changes.

## Safety boundary

- Never write secrets, tokens, private keys, host credentials, or literal environment-variable values into the repository.
- Preserve all existing repository content. Only create or update `.codex/cloud/*` and the marker-delimited `Codex Cloud` block in `AGENTS.md`.
- Treat a dirty worktree as user-owned. Show the intended diff and do not overwrite overlapping changes.
- Do not create a hosted Codex environment or change GitHub permissions. Those are account-level actions and require explicit user action.

## Workflow

1. Confirm the exact repository root, branch, HEAD, and worktree status.
2. Resolve this skill directory, then preview the deterministic plan:

   ```bash
   python3 <skill-directory>/scripts/prepare_cloud_repo.py --repo "$PWD" --plan
   ```

3. Review `warnings` and `requires_manual_review`. If an install command cannot be inferred from repository evidence, report that gap rather than inventing one.
4. Apply the plan:

   ```bash
   python3 <skill-directory>/scripts/prepare_cloud_repo.py --repo "$PWD" --apply
   ```

5. Inspect the resulting diff. Then run the separate `$verify-codex-cloud` skill. The verifier is read-only and must return `PASS`, `FAIL`, or `BLOCKED`.

## Generated contract

- `.codex/cloud/setup.sh`: first-run dependency bootstrap.
- `.codex/cloud/maintenance.sh`: dependency refresh when a cached cloud container resumes.
- `.codex/cloud/environment.json`: detected runtimes, install commands, validation commands, and warnings. It contains names only, never secret values.
- `AGENTS.md`: a marker-delimited block telling Codex how to bootstrap and validate the repository.

The generator recognizes common Node, Python, Ruby, Rust, Go, and PHP lockfiles. It prefers locked installs and records ambiguity instead of guessing.

## Hosted environment handoff

After repository verification passes, give the user the remaining account-level checklist:

1. In Codex Cloud settings, create or select an environment for this repository.
2. Use the default universal image unless the repository needs a custom container.
3. Put credential values in the environment's secret store, not in Git.
4. Ensure the Codex GitHub app has permission to write to the repository.
5. Use `@codex fix` on an actionable Codex review comment. A plain `@codex` mention is conversational; `@codex fix` is the documented remediation command.

Read [references/cloud-behavior.md](references/cloud-behavior.md) when explaining caching, billing, or the boundary between this skill and hosted environment settings.
