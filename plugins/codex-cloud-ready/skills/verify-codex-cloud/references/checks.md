# Verification checks

## Static checks

- Required files exist:
  - `.codex/cloud/setup.sh`
  - `.codex/cloud/maintenance.sh`
  - `.codex/cloud/environment.json`
  - `AGENTS.md`
- Both shell scripts pass `bash -n` and are executable.
- The environment manifest is JSON, uses schema version 1, and contains lists
  for dependency installs, validation commands, warnings, and runtimes.
- Every manifest install command appears in both shell scripts.
- `AGENTS.md` contains exactly one complete managed block.
- Generated files contain no private-key blocks, common literal cloud keys, or
  literal values assigned to secret-like variable names.

## Optional live check

With `--docker`, mount the repository read-write into
`ghcr.io/openai/codex-universal:latest` and execute
`.codex/cloud/setup.sh`. This can install dependencies into the repository and
Docker cache, so run it only with explicit authorization.

## Verdicts

- `PASS`: all requested checks pass.
- `FAIL`: repository-controlled evidence fails.
- `BLOCKED`: an explicitly requested external capability is unavailable.
