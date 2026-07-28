# Codex Cloud Ready

Codex plugin for preparing repositories so GitHub `@codex fix` tasks can
bootstrap predictably in Codex Cloud.

## What it provides

- `$setup-codex-cloud` detects repository evidence and generates idempotent
  setup and maintenance scripts.
- `$verify-codex-cloud` independently checks the generated contract without
  repairing failures.
- Locked install support for Node, Python, Ruby, Rust, Go, and PHP projects.
- A bounded `AGENTS.md` section containing the detected bootstrap and validation
  commands.

## Install

```bash
codex plugin add codex-cloud-ready@personal
```

Start a new Codex task after installing, then say:

```text
Use $setup-codex-cloud to prepare this repository for @codex PR fixes.
```

## Repository output

```text
.codex/cloud/setup.sh
.codex/cloud/maintenance.sh
.codex/cloud/environment.json
AGENTS.md
```

No secret values are written. Hosted environments, secret values, and GitHub
app permissions remain account-level configuration.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/setup-codex-cloud
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/verify-codex-cloud
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```

## License

MIT
