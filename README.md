<p align="center">
  <img src="plugins/codex-cloud-ready/assets/icon-400.png" width="180" alt="Codex Cloud Ready icon">
</p>

# Codex Cloud Ready

An open-source Codex plugin that prepares repositories so GitHub `@codex fix`
tasks can bootstrap predictably in Codex Cloud.

## Install

```bash
codex plugin marketplace add jtcchan/codex-cloud-ready
codex plugin add codex-cloud-ready@codex-cloud-ready
```

Start a new Codex task inside any repository, then say:

```text
Use $setup-codex-cloud to prepare this repository for @codex PR fixes.
```

## What it provides

- `$setup-codex-cloud` detects repository evidence and generates idempotent
  setup and maintenance scripts.
- `$verify-codex-cloud` independently checks the generated contract without
  repairing failures.
- Locked install support for Node, Python, Ruby, Rust, Go, and PHP projects.
- A bounded `AGENTS.md` section containing detected bootstrap and validation
  commands.
- Secret-safe repository files: credential values remain in hosted settings.

## Repository output

```text
.codex/cloud/setup.sh
.codex/cloud/maintenance.sh
.codex/cloud/environment.json
AGENTS.md
```

The plugin prepares repository-owned configuration. It cannot create the hosted
Codex environment, provide secret values, or grant the GitHub app write access.

## Development

```bash
python3 -m unittest discover -s plugins/codex-cloud-ready/tests -v
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  plugins/codex-cloud-ready/skills/setup-codex-cloud
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  plugins/codex-cloud-ready/skills/verify-codex-cloud
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py \
  plugins/codex-cloud-ready
```

## Trademark notice

This is an independent community project. It is not affiliated with, endorsed
by, or supported by OpenAI.

OpenAI, Codex, and related names and trademarks are the property of OpenAI. This
project uses those names only to describe compatibility with OpenAI services and
does not use or modify OpenAI logos.

See the current [OpenAI Brand Guidelines](https://openai.com/brand/).

## License

[MIT](LICENSE)
