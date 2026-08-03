#!/usr/bin/env python3
"""Read-only verifier for repository-owned Codex Cloud bootstrap files."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

START = "<!-- codex-cloud-ready:start -->"
END = "<!-- codex-cloud-ready:end -->"
CONTRACT = ".codex/cloud/contract.json"
REQUIRED = [
    ".codex/cloud/setup.sh",
    ".codex/cloud/maintenance.sh",
    ".codex/cloud/environment.json",
    "AGENTS.md",
    CONTRACT,
]
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(
        r"(?im)^\s*(?:export\s+)?(?:[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)"
        r"\s*=\s*['\"]?(?!\$\{?)[^'\"\s][^'\"\n]*"
    ),
]
ENVIRONMENT_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]*$")
REPOSITORY = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?/[a-z0-9._-]+$")


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def load_manifest(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, str(error)
    if not isinstance(value, dict):
        return None, "top-level JSON value is not an object"
    return value, "valid JSON object"


def validate_cloud_contract(contract_path: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [check("cloud-contract:json", False, str(error))]
    results.append(check("cloud-contract:json", isinstance(contract, dict), "valid JSON object"))
    if not isinstance(contract, dict):
        return results
    results.append(check("cloud-contract:schema-version", contract.get("schema_version") == 1, f"value={contract.get('schema_version')!r}"))
    results.append(check("cloud-contract:provider", contract.get("provider") == "codex", f"value={contract.get('provider')!r}"))
    results.append(check("cloud-contract:status", contract.get("status") in {"pending", "ready", "blocked"}, f"value={contract.get('status')!r}"))
    results.append(check("cloud-contract:network-access", contract.get("network_access") in {"off", "limited", "unrestricted"}, f"value={contract.get('network_access')!r}"))
    results.append(check("cloud-contract:secret-policy", contract.get("secret_policy") == "setup_only" and contract.get("agent_secret_policy") == "unavailable", "setup-only secrets"))
    environment_name = contract.get("environment_name")
    repository = contract.get("repository")
    results.append(check("cloud-contract:identity", contract.get("status") != "ready" or (isinstance(environment_name, str) and bool(environment_name.strip()) and isinstance(repository, str) and REPOSITORY.fullmatch(repository) is not None), "ready identity is complete" if contract.get("status") == "ready" else "hosted identity pending or blocked"))
    for field in ("environment_variables", "secrets"):
        values = contract.get(field)
        all_names = isinstance(values, list) and all(isinstance(value, str) and ENVIRONMENT_VARIABLE.fullmatch(value) for value in values)
        valid = all_names and len(values) == len(set(values)) if all_names else False
        results.append(check(f"cloud-contract:{field}", valid, "names only" if valid else "must contain unique uppercase names"))
    return results


def static_checks(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    results: list[dict[str, Any]] = []
    contract: dict[str, Any] | None = None
    for relative in REQUIRED:
        path = root / relative
        results.append(check(f"exists:{relative}", path.is_file(), "present" if path.is_file() else "missing"))

    setup = root / ".codex/cloud/setup.sh"
    maintenance = root / ".codex/cloud/maintenance.sh"
    for relative, path in [
        (".codex/cloud/setup.sh", setup),
        (".codex/cloud/maintenance.sh", maintenance),
    ]:
        if not path.is_file():
            continue
        syntax = subprocess.run(
            ["bash", "-n", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            check(
                f"bash-syntax:{relative}",
                syntax.returncode == 0,
                syntax.stderr.strip() or "valid",
            )
        )
        executable = os.access(path, os.X_OK)
        results.append(check(f"executable:{relative}", executable, "executable" if executable else "not executable"))

    manifest_path = root / ".codex/cloud/environment.json"
    manifest: dict[str, Any] | None = None
    if manifest_path.is_file():
        manifest, detail = load_manifest(manifest_path)
        results.append(check("manifest:json", manifest is not None, detail))

    if manifest is not None:
        required_types = {
            "runtimes": list,
            "dependency_installs": list,
            "validation_commands": list,
            "warnings": list,
            "requires_manual_review": bool,
        }
        schema_ok = manifest.get("schema_version") == 1
        results.append(check("manifest:schema-version", schema_ok, f"value={manifest.get('schema_version')!r}"))
        for key, expected_type in required_types.items():
            ok = isinstance(manifest.get(key), expected_type)
            results.append(check(f"manifest:type:{key}", ok, f"expected {expected_type.__name__}"))

        if isinstance(manifest.get("dependency_installs"), list):
            setup_text = setup.read_text(encoding="utf-8") if setup.is_file() else ""
            maintenance_text = maintenance.read_text(encoding="utf-8") if maintenance.is_file() else ""
            commands = [
                item.get("command")
                for item in manifest["dependency_installs"]
                if isinstance(item, dict) and isinstance(item.get("command"), str)
            ]
            complete = len(commands) == len(manifest["dependency_installs"])
            present = complete and all(command in setup_text and command in maintenance_text for command in commands)
            results.append(
                check(
                    "manifest:install-command-consistency",
                    present,
                    f"{len(commands)} command(s) checked",
                )
            )

        manual = manifest.get("requires_manual_review")
        results.append(
            check(
                "manifest:no-manual-review",
                manual is False,
                "no unresolved install evidence" if manual is False else "manual review required",
            )
        )

        cloud = manifest.get("cloud_environment")
        results.append(check("manifest:cloud-environment", isinstance(cloud, dict), "cloud handoff metadata present" if isinstance(cloud, dict) else "missing cloud handoff metadata"))

    agents = root / "AGENTS.md"
    if agents.is_file():
        text = agents.read_text(encoding="utf-8")
        markers_ok = text.count(START) == 1 and text.count(END) == 1 and text.index(START) < text.index(END)
        results.append(check("agents:managed-block", markers_ok, "one complete block" if markers_ok else "markers malformed"))

    contract_path = root / CONTRACT
    if contract_path.is_file():
        try:
            parsed_contract = json.loads(contract_path.read_text(encoding="utf-8"))
            if isinstance(parsed_contract, dict):
                contract = parsed_contract
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        results.extend(validate_cloud_contract(contract_path))
    if manifest is not None and isinstance(manifest.get("cloud_environment"), dict) and contract is not None:
        results.append(
            check(
                "manifest:cloud-contract-match",
                manifest["cloud_environment"] == contract,
                "manifest and contract agree" if manifest["cloud_environment"] == contract else "manifest cloud metadata differs from contract",
            )
        )

    generated = [root / relative for relative in REQUIRED[:3]] + [root / CONTRACT]
    findings: list[str] = []
    for path in generated:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{path.relative_to(root)} matched {pattern.pattern[:32]}")
    results.append(
        check(
            "secret-safety",
            not findings,
            "no literal secret patterns" if not findings else "; ".join(findings),
        )
    )
    return results, manifest


def docker_check(root: Path) -> tuple[str, dict[str, Any]]:
    docker = shutil.which("docker")
    if docker is None:
        return "BLOCKED", {"name": "docker:universal-image", "status": "BLOCKED", "detail": "docker not installed"}
    availability = subprocess.run(
        [docker, "info"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if availability.returncode != 0:
        return "BLOCKED", {
            "name": "docker:universal-image",
            "status": "BLOCKED",
            "detail": availability.stderr.strip() or "docker daemon unavailable",
        }
    run = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{root}:/workspace",
            "-w",
            "/workspace",
            "ghcr.io/openai/codex-universal:latest",
            "bash",
            ".codex/cloud/setup.sh",
        ],
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    detail = (run.stdout + "\n" + run.stderr).strip()[-4000:]
    if run.returncode == 0:
        return "PASS", {"name": "docker:universal-image", "status": "PASS", "detail": detail or "setup passed"}
    return "FAIL", {"name": "docker:universal-image", "status": "FAIL", "detail": detail or f"exit {run.returncode}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable evidence")
    parser.add_argument("--docker", action="store_true", help="Run setup in codex-universal (may install dependencies)")
    args = parser.parse_args()
    root = args.repo.expanduser().resolve()

    if not root.is_dir():
        payload = {"verdict": "BLOCKED", "repo": str(root), "checks": [], "reason": "repository directory missing"}
        print(json.dumps(payload, indent=2) if args.json else f"BLOCKED: {payload['reason']}")
        return 2

    checks, _ = static_checks(root)
    if any(item["status"] == "FAIL" for item in checks):
        verdict = "FAIL"
    else:
        verdict = "PASS"

    if args.docker and verdict == "PASS":
        docker_verdict, docker_evidence = docker_check(root)
        checks.append(docker_evidence)
        verdict = docker_verdict

    payload = {"verdict": verdict, "repo": str(root), "checks": checks}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(verdict)
        for item in checks:
            print(f"{item['status']}: {item['name']} — {item['detail']}")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
