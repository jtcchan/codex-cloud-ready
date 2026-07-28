---
name: verify-codex-cloud
description: Independently and read-only verify that a repository's Codex Cloud bootstrap files are syntactically valid, internally consistent, secret-safe, executable, and documented in AGENTS.md. Use after setup-codex-cloud, before enabling GitHub @codex fixes, when auditing a repository's cloud environment, or when the user requests independent Codex Cloud readiness QA.
---

# Verify Codex Cloud

## Overview

Return exactly one readiness verdict—`PASS`, `FAIL`, or `BLOCKED`—from raw repository evidence. Never edit, regenerate, or repair the files being verified.

## Hard boundary

- Read-only verification only. Do not invoke the setup skill or run it with `--apply`.
- Never modify source, generated bootstrap files, Git state, dependencies, hosted settings, or GitHub permissions.
- Do not convert a missing prerequisite into a pass.
- Static verification is the default. Only run a live universal-image bootstrap when the user explicitly requests it because it can download a large image and install packages.

## Workflow

1. Confirm the exact repository root, branch, HEAD, and worktree status.
2. Resolve this skill directory and run:

   ```bash
   python3 <skill-directory>/scripts/verify_cloud_repo.py --repo "$PWD" --json
   ```

3. If the user explicitly asks for validation inside OpenAI's published universal image, add `--docker`. If Docker or the image is unavailable, return `BLOCKED`.
4. Report the script's raw checks and preserve its verdict. Do not repair failures.

## Verdict contract

- `PASS`: all required files exist; shell syntax, executable bits, manifest structure, command consistency, AGENTS markers, and secret-safety checks pass; any explicitly requested live run also passes.
- `FAIL`: repository-controlled evidence is missing, malformed, inconsistent, unsafe, or a requested bootstrap command exits nonzero.
- `BLOCKED`: the requested verification cannot run because a required external capability such as Docker is unavailable.

The verdict proves repository bootstrap readiness only. It does not prove that a hosted Codex environment exists, secrets are configured, the GitHub app can write, or a particular PR is mergeable.

Read [references/checks.md](references/checks.md) for the exact static and optional live checks.
