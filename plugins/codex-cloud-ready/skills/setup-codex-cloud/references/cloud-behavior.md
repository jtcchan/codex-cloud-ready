# Codex Cloud behavior

## Repository files versus hosted settings

This skill owns only repository files. It cannot create the hosted environment,
set account secrets, or grant the GitHub app repository access.

The repository bootstrap contract is portable and version-controlled:

- `.codex/cloud/setup.sh` installs locked dependencies on a fresh container.
- `.codex/cloud/maintenance.sh` refreshes dependencies when a cached container
  resumes.
- `.codex/cloud/environment.json` records detected requirements for humans and
  agents.
- `.codex/cloud/contract.json` records the intended hosted environment identity,
  network policy, and required variable/secret names. It never contains secret
  values. The contract is repository-owned metadata; the actual environment
  and secret store remain account-level Codex settings.

The hosted environment is selected per repository in Codex Cloud settings.

## Cache behavior

Codex Cloud may resume a cached container, but repository bootstrap must remain
safe on both a fresh container and a resumed one. Do not rely on cache lifetime
for correctness. Setup and maintenance commands should be idempotent.

Package installation consumes environment compute and network time. It is not
model reasoning and should not be optimized by hiding dependencies from Codex.
Use lockfiles and the universal image's preinstalled runtimes to minimize
repeated work.

## GitHub remediation

Automatic review and remediation are separate actions. The documented
remediation command is `@codex fix` on an actionable review comment. It starts a
Codex Cloud task that can push a change only when:

- the repository is connected to a Codex Cloud environment;
- setup succeeds;
- required secrets are present in hosted settings; and
- the Codex GitHub app has write permission.

Codex Cloud decrypts secrets for setup, then removes them before the agent
phase. Do not design an agent task that expects to read a secret after setup.
This plugin verifies the repository contract, not those account-level
conditions.
