from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "skills/setup-codex-cloud/scripts/prepare_cloud_repo.py"
VERIFY = ROOT / "skills/verify-codex-cloud/scripts/verify_cloud_repo.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        check=False,
    )


class CloudReadyTests(unittest.TestCase):
    def node_repo(self, root: Path) -> None:
        package = {
            "name": "fixture",
            "private": True,
            "packageManager": "pnpm@10.0.0",
            "engines": {"node": ">=22"},
            "scripts": {
                "lint": "eslint .",
                "typecheck": "tsc --noEmit",
                "test": "vitest run",
            },
        }
        (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
        (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("# Existing instructions\n\nKeep this text.\n", encoding="utf-8")

    def test_apply_is_idempotent_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.node_repo(root)

            first = run(str(PREPARE), "--repo", str(root), "--apply")
            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            agents_after_first = (root / "AGENTS.md").read_text(encoding="utf-8")

            second = run(str(PREPARE), "--repo", str(root), "--apply")
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            self.assertEqual(agents_after_first, (root / "AGENTS.md").read_text(encoding="utf-8"))

            check = run(str(PREPARE), "--repo", str(root), "--check")
            self.assertEqual(check.returncode, 0, check.stderr or check.stdout)

            verify = run(str(VERIFY), "--repo", str(root), "--json")
            self.assertEqual(verify.returncode, 0, verify.stderr or verify.stdout)
            self.assertEqual(json.loads(verify.stdout)["verdict"], "PASS")
            self.assertIn("Keep this text.", agents_after_first)

    def test_unlocked_manifest_requires_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"name":"unlocked"}\n', encoding="utf-8")

            apply = run(str(PREPARE), "--repo", str(root), "--apply")
            self.assertEqual(apply.returncode, 0, apply.stderr or apply.stdout)
            manifest = json.loads((root / ".codex/cloud/environment.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["requires_manual_review"])

            verify = run(str(VERIFY), "--repo", str(root), "--json")
            self.assertEqual(verify.returncode, 1)
            self.assertEqual(json.loads(verify.stdout)["verdict"], "FAIL")

    def test_verifier_detects_drift_and_literal_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.node_repo(root)
            self.assertEqual(run(str(PREPARE), "--repo", str(root), "--apply").returncode, 0)
            setup = root / ".codex/cloud/setup.sh"
            setup.write_text(setup.read_text(encoding="utf-8") + "\nAPI_TOKEN=literal-secret\n", encoding="utf-8")

            verify = run(str(VERIFY), "--repo", str(root), "--json")
            payload = json.loads(verify.stdout)
            self.assertEqual(verify.returncode, 1)
            self.assertEqual(payload["verdict"], "FAIL")
            secret_check = next(item for item in payload["checks"] if item["name"] == "secret-safety")
            self.assertEqual(secret_check["status"], "FAIL")

    def test_static_repo_needs_no_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<h1>Hello</h1>\n", encoding="utf-8")
            self.assertEqual(run(str(PREPARE), "--repo", str(root), "--apply").returncode, 0)
            verify = run(str(VERIFY), "--repo", str(root), "--json")
            self.assertEqual(verify.returncode, 0, verify.stderr or verify.stdout)
            self.assertEqual(json.loads(verify.stdout)["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
