#!/usr/bin/env python3
"""Generate deterministic, repository-owned Codex Cloud bootstrap files."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

START = "<!-- codex-cloud-ready:start -->"
END = "<!-- codex-cloud-ready:end -->"
CONTRACT_PATH = ".codex/cloud/contract.json"
CONTRACT_SCHEMA_VERSION = 1
NETWORK_ACCESS = {"off", "limited", "unrestricted"}
CONTRACT_STATUS = {"pending", "ready", "blocked"}
CONTRACT_KEYS = {
    "schema_version",
    "provider",
    "status",
    "environment_name",
    "repository",
    "default_branch",
    "network_access",
    "environment_variables",
    "secrets",
    "secret_policy",
    "agent_secret_policy",
}
ENVIRONMENT_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]*$")
REPOSITORY = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?/[a-z0-9._-]+$")
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".next",
    ".svn",
    ".turbo",
    ".tox",
    ".venv",
    ".cache",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "out",
}


def files_named(root: Path, names: set[str]) -> list[Path]:
    found: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        current_path = Path(current)
        for name in sorted(set(files) & names):
            found.append(current_path / name)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def default_cloud_contract() -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "provider": "codex",
        "status": "pending",
        "environment_name": None,
        "repository": None,
        "default_branch": "main",
        "network_access": "off",
        "environment_variables": [],
        "secrets": [],
        "secret_policy": "setup_only",
        "agent_secret_policy": "unavailable",
    }


def read_cloud_contract(root: Path) -> dict[str, Any]:
    path = root / CONTRACT_PATH
    if not path.exists():
        return default_cloud_contract()
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cloud contract is not valid JSON: {error}") from error
    if not isinstance(contract, dict):
        raise ValueError("cloud contract must be a JSON object")
    return contract


def render_cloud_contract(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2, sort_keys=True) + "\n"


def validate_cloud_contract(contract: dict[str, Any]) -> None:
    unknown = sorted(set(contract) - CONTRACT_KEYS)
    if unknown:
        raise ValueError("cloud contract contains unknown keys: " + ", ".join(unknown))
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise ValueError("cloud contract schema_version must be 1")
    if contract.get("provider") != "codex":
        raise ValueError("cloud contract provider must be codex")
    if contract.get("status") not in CONTRACT_STATUS:
        raise ValueError("cloud contract status must be pending, ready, or blocked")
    if contract.get("network_access") not in NETWORK_ACCESS:
        raise ValueError("cloud contract network_access must be off, limited, or unrestricted")
    if contract.get("secret_policy") != "setup_only":
        raise ValueError("cloud contract secret_policy must be setup_only")
    if contract.get("agent_secret_policy") != "unavailable":
        raise ValueError("cloud contract agent_secret_policy must be unavailable")
    environment_name = contract.get("environment_name")
    if environment_name is not None and (not isinstance(environment_name, str) or not environment_name.strip()):
        raise ValueError("cloud contract environment_name must be a nonempty string or null")
    repository = contract.get("repository")
    if repository is not None and (not isinstance(repository, str) or not REPOSITORY.fullmatch(repository)):
        raise ValueError("cloud contract repository must be lowercase owner/repo or null")
    if not isinstance(contract.get("default_branch"), str) or not contract["default_branch"].strip():
        raise ValueError("cloud contract default_branch must be a nonempty string")
    for field in ("environment_variables", "secrets"):
        values = contract.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) or not ENVIRONMENT_VARIABLE.fullmatch(value) for value in values):
            raise ValueError(f"cloud contract {field} must contain uppercase environment-variable names")
        if len(values) != len(set(values)):
            raise ValueError(f"cloud contract {field} must not contain duplicates")
    if contract.get("status") == "ready" and (not environment_name or not repository):
        raise ValueError("ready cloud contract requires environment_name and repository")


def relative_dir(root: Path, path: Path) -> str:
    rel = path.parent.relative_to(root).as_posix()
    return "." if rel == "." else rel


def node_command(lock: Path) -> tuple[str, str]:
    if lock.name == "pnpm-lock.yaml":
        return "pnpm", "corepack enable && pnpm install --frozen-lockfile"
    if lock.name == "package-lock.json" or lock.name == "npm-shrinkwrap.json":
        return "npm", "npm ci"
    if lock.name in {"bun.lock", "bun.lockb"}:
        return "bun", "bun install --frozen-lockfile"

    package = read_json(lock.parent / "package.json")
    package_manager = str(package.get("packageManager", ""))
    yarn_major = 1
    if package_manager.startswith("yarn@"):
        try:
            yarn_major = int(package_manager.split("@", 1)[1].split(".", 1)[0])
        except ValueError:
            yarn_major = 1
    flag = "--immutable" if yarn_major >= 2 else "--frozen-lockfile"
    return "yarn", f"corepack enable && yarn install {flag}"


def detect_installs(root: Path) -> tuple[list[dict[str, str]], list[str], bool]:
    lock_names = {
        "pnpm-lock.yaml",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "requirements.txt",
        "Gemfile.lock",
        "Cargo.lock",
        "go.sum",
        "composer.lock",
    }
    locks = files_named(root, lock_names)
    candidates: dict[tuple[str, str], list[tuple[int, dict[str, str]]]] = {}

    def add(path: Path, ecosystem: str, priority: int, manager: str, command: str) -> None:
        item = {
            "path": relative_dir(root, path),
            "ecosystem": ecosystem,
            "manager": manager,
            "evidence": path.relative_to(root).as_posix(),
            "command": command,
        }
        candidates.setdefault((item["path"], ecosystem), []).append((priority, item))

    for lock in locks:
        if lock.name in {
            "pnpm-lock.yaml",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "yarn.lock",
            "bun.lock",
            "bun.lockb",
        }:
            priorities = {
                "pnpm-lock.yaml": 0,
                "package-lock.json": 1,
                "npm-shrinkwrap.json": 1,
                "yarn.lock": 2,
                "bun.lock": 3,
                "bun.lockb": 3,
            }
            manager, command = node_command(lock)
            add(lock, "node", priorities[lock.name], manager, command)
        elif lock.name == "uv.lock":
            add(lock, "python", 0, "uv", "uv sync --frozen")
        elif lock.name == "poetry.lock":
            add(lock, "python", 1, "poetry", "poetry install --no-interaction --no-ansi")
        elif lock.name == "Pipfile.lock":
            add(lock, "python", 2, "pipenv", "pipenv sync --dev")
        elif lock.name == "requirements.txt":
            add(lock, "python", 3, "pip", "python -m pip install -r requirements.txt")
        elif lock.name == "Gemfile.lock":
            add(lock, "ruby", 0, "bundler", "bundle install")
        elif lock.name == "Cargo.lock":
            add(lock, "rust", 0, "cargo", "cargo fetch --locked")
        elif lock.name == "go.sum":
            add(lock, "go", 0, "go", "go mod download")
        elif lock.name == "composer.lock":
            add(lock, "php", 0, "composer", "composer install --no-interaction --prefer-dist")

    installs: list[dict[str, str]] = []
    warnings: list[str] = []
    for key in sorted(candidates):
        options = sorted(candidates[key], key=lambda value: (value[0], value[1]["evidence"]))
        installs.append(options[0][1])
        if len(options) > 1:
            evidence = ", ".join(option[1]["evidence"] for option in options)
            warnings.append(
                f"Multiple {key[1]} lockfiles apply at {key[0]} ({evidence}); "
                f"selected {options[0][1]['evidence']} by deterministic priority."
            )

    manifest_names = {
        "package.json",
        "pyproject.toml",
        "Pipfile",
        "Gemfile",
        "Cargo.toml",
        "go.mod",
        "composer.json",
    }
    manifests = files_named(root, manifest_names)
    covered = {(item["path"], item["ecosystem"]) for item in installs}
    ecosystem_for_manifest = {
        "package.json": "node",
        "pyproject.toml": "python",
        "Pipfile": "python",
        "Gemfile": "ruby",
        "Cargo.toml": "rust",
        "go.mod": "go",
        "composer.json": "php",
    }
    uncovered = []
    for manifest in manifests:
        key = (relative_dir(root, manifest), ecosystem_for_manifest[manifest.name])
        if key not in covered:
            uncovered.append(manifest.relative_to(root).as_posix())
    if uncovered:
        warnings.append(
            "No deterministic locked install was found for: " + ", ".join(sorted(uncovered))
        )
    return installs, warnings, bool(uncovered)


def detect_runtimes(root: Path) -> list[dict[str, str]]:
    runtimes: list[dict[str, str]] = []
    runtime_files = [
        ("node", ".nvmrc"),
        ("node", ".node-version"),
        ("python", ".python-version"),
        ("ruby", ".ruby-version"),
    ]
    seen: set[str] = set()
    for runtime, filename in runtime_files:
        value = read_text(root / filename)
        if value and runtime not in seen:
            runtimes.append({"runtime": runtime, "version": value, "evidence": filename})
            seen.add(runtime)

    package = read_json(root / "package.json")
    node_engine = package.get("engines", {}).get("node") if isinstance(package.get("engines"), dict) else None
    if node_engine and "node" not in seen:
        runtimes.append(
            {"runtime": "node", "version": str(node_engine), "evidence": "package.json#engines.node"}
        )
    return runtimes


def manager_for_path(installs: list[dict[str, str]], path: str, ecosystem: str) -> str | None:
    for item in installs:
        if item["path"] == path and item["ecosystem"] == ecosystem:
            return item["manager"]
    return None


def command_in_path(path: str, command: str) -> dict[str, str]:
    return {"path": path, "command": command}


def detect_validation(root: Path, installs: list[dict[str, str]]) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    for package_path in files_named(root, {"package.json"}):
        package = read_json(package_path)
        scripts = package.get("scripts")
        if not isinstance(scripts, dict):
            continue
        path = relative_dir(root, package_path)
        manager = manager_for_path(installs, path, "node") or "npm"
        for name in ("lint", "typecheck", "test", "build"):
            body = scripts.get(name)
            if not isinstance(body, str) or not body.strip():
                continue
            if name == "test" and "no test specified" in body.lower():
                continue
            if manager == "npm":
                command = f"npm run {name}"
            elif manager == "pnpm":
                command = f"pnpm run {name}"
            elif manager == "bun":
                command = f"bun run {name}"
            else:
                command = f"yarn {name}"
            commands.append(command_in_path(path, command))

    for go_mod in files_named(root, {"go.mod"}):
        commands.append(command_in_path(relative_dir(root, go_mod), "go test ./..."))
    for cargo in files_named(root, {"Cargo.toml"}):
        suffix = " --locked" if (cargo.parent / "Cargo.lock").exists() else ""
        commands.append(command_in_path(relative_dir(root, cargo), f"cargo test{suffix}"))

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in commands:
        key = (item["path"], item["command"])
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def render_shell(installs: list[dict[str, str]], purpose: str) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "# Generated by codex-cloud-ready. Review changes; never add secret values.",
        "set -euo pipefail",
        "",
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"',
        "export CI=1",
        "",
        f'echo "Codex Cloud {purpose}: $ROOT"',
    ]
    if not installs:
        lines.append('echo "No locked dependency installation was detected; nothing to install."')
    for item in installs:
        lines.extend(["", "("])
        if item["path"] == ".":
            lines.append('  cd "$ROOT"')
        else:
            lines.append(f'  cd "$ROOT"/{shlex.quote(item["path"])}')
        lines.append(f'  echo "Installing {item["ecosystem"]} dependencies in {item["path"]}"')
        lines.append(f"  {item['command']}")
        lines.append(")")
    lines.extend(["", f'echo "Codex Cloud {purpose} complete."', ""])
    return "\n".join(lines)


def format_scoped_command(item: dict[str, str]) -> str:
    return item["command"] if item["path"] == "." else f"(cd {shlex.quote(item['path'])} && {item['command']})"


def render_agents_block(validations: list[dict[str, str]]) -> str:
    lines = [
        START,
        "## Codex Cloud",
        "",
        "- Bootstrap this repository with `bash .codex/cloud/setup.sh`.",
        "- On a resumed cloud container, run `bash .codex/cloud/maintenance.sh`.",
        "- Keep credential values in Codex Cloud secrets; never print or commit them.",
        "- Read `.codex/cloud/contract.json` for the value-free hosted environment contract.",
        "- Codex Cloud secrets are setup-only; do not expect secret values during the agent phase.",
    ]
    if validations:
        lines.append("- Before completing a PR fix, run the detected validation commands:")
        lines.extend(f"  - `{format_scoped_command(item)}`" for item in validations)
    else:
        lines.append("- No validation command was detected; inspect the repository before claiming completion.")
    lines.append(END)
    return "\n".join(lines)


def upsert_agents(existing: str, block: str) -> str:
    starts = existing.count(START)
    ends = existing.count(END)
    if starts != ends or starts > 1:
        raise ValueError("AGENTS.md has malformed or duplicate codex-cloud-ready markers")
    if starts == 1:
        before, remainder = existing.split(START, 1)
        _, after = remainder.split(END, 1)
        prefix = before.rstrip()
        suffix = after.strip()
        result = (prefix + "\n\n" if prefix else "") + block
        result += ("\n\n" + suffix + "\n") if suffix else "\n"
    elif existing.strip():
        result = existing.rstrip() + "\n\n" + block + "\n"
    else:
        result = block + "\n"
    return result


def build_plan(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    installs, warnings, manual = detect_installs(root)
    validations = detect_validation(root, installs)
    cloud_contract = read_cloud_contract(root)
    validate_cloud_contract(cloud_contract)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generated_by": "codex-cloud-ready/0.2.0",
        "runtimes": detect_runtimes(root),
        "dependency_installs": installs,
        "validation_commands": validations,
        "warnings": warnings,
        "requires_manual_review": manual,
        "cloud_environment": cloud_contract,
    }
    agents_path = root / "AGENTS.md"
    existing_agents = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    files = {
        ".codex/cloud/setup.sh": render_shell(installs, "setup"),
        ".codex/cloud/maintenance.sh": render_shell(installs, "maintenance"),
        ".codex/cloud/environment.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        CONTRACT_PATH: render_cloud_contract(cloud_contract),
        "AGENTS.md": upsert_agents(existing_agents, render_agents_block(validations)),
    }
    return manifest, files


def apply_plan(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        if destination.suffix == ".sh":
            destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def check_plan(root: Path, files: dict[str, str]) -> tuple[bool, list[str]]:
    drift: list[str] = []
    for relative, expected in files.items():
        path = root / relative
        if not path.exists():
            drift.append(f"missing: {relative}")
        elif path.read_text(encoding="utf-8") != expected:
            drift.append(f"drifted: {relative}")
    return not drift, drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="Print the plan without writing")
    mode.add_argument("--apply", action="store_true", help="Write the generated files")
    mode.add_argument("--check", action="store_true", help="Check generated files for drift")
    args = parser.parse_args()

    root = args.repo.expanduser().resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 2

    try:
        manifest, files = build_plan(root)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}))
        return 2

    if args.plan:
        print(json.dumps({"repo": str(root), "files": sorted(files), **manifest}, indent=2))
        return 0
    if args.apply:
        apply_plan(root, files)
        print(json.dumps({"status": "applied", "repo": str(root), "files": sorted(files)}, indent=2))
        return 0

    matches, drift = check_plan(root, files)
    print(json.dumps({"status": "current" if matches else "drift", "repo": str(root), "drift": drift}, indent=2))
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
