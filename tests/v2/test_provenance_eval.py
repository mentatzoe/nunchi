from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evals.v2.provenance import runner


class ProvenanceAuditCases(unittest.TestCase):
    def test_surface_contract_keeps_required_products_and_removes_only_superseded_gates(self):
        contract = runner.load_surface_contract()
        required = contract["required_scripts"]
        removed = contract["removed_scripts"]
        for script in (
            "nunchi",
            "nunchi-install",
            "nunchi-channel",
            "nunchi-discord",
            "nunchi-matrix",
            "nunchi-telegram",
            "nunchi-mcp-discord",
            "nunchi-codex-room-v2",
            "nunchi-codex-config-app",
        ):
            self.assertIn(script, required)
        self.assertIn("nunchi-codex-send-gate", removed)
        self.assertIn("send-time", removed["nunchi-codex-send-gate"].lower())
        self.assertFalse(set(required) & set(removed))

    def test_mixed_fixture_fails_honestly_with_grouped_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "src" / "nunchi"
            package.mkdir(parents=True)
            package.joinpath("legacy.py").write_text(
                "class ChannelGateResult:\n    pass\n",
                encoding="utf-8",
            )
            contract = runner.load_surface_contract()
            scripts = dict(contract["required_scripts"])
            scripts["nunchi-codex-send-gate"] = "nunchi.legacy:main"
            rendered = "\n".join(
                f'{json.dumps(name)} = {json.dumps(target)}'
                for name, target in scripts.items()
            )
            root.joinpath("pyproject.toml").write_text(
                "[project]\n"
                'name = "nunchi"\n'
                'version = "0.2.0"\n'
                "[project.scripts]\n"
                f"{rendered}\n",
                encoding="utf-8",
            )
            audit = runner.audit_repository(root)
        self.assertFalse(audit["passed"])
        self.assertIn("product-version-not-v2", audit["failures"])
        self.assertIn("removed-entrypoints-present", audit["failures"])
        self.assertIn("v1-runtime-residue-present", audit["failures"])
        self.assertIn("nunchi-codex-send-gate", audit["removed_scripts_present"])
        finding = audit["residue_findings"][0]
        self.assertEqual(
            set(finding),
            {"path", "first_line", "occurrences", "kind", "match"},
        )
        self.assertGreaterEqual(finding["occurrences"], 1)

    def test_clean_v2_fixture_passes_exact_script_and_residue_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "src" / "nunchi"
            package.mkdir(parents=True)
            package.joinpath("__init__.py").write_text("\n", encoding="utf-8")
            contract = runner.load_surface_contract()
            scripts = "\n".join(
                f'{json.dumps(name)} = {json.dumps(target)}'
                for name, target in contract["required_scripts"].items()
            )
            root.joinpath("pyproject.toml").write_text(
                "[project]\n"
                'name = "nunchi"\n'
                'version = "2.0.0rc1"\n'
                "[project.scripts]\n"
                f"{scripts}\n",
                encoding="utf-8",
            )
            audit = runner.audit_repository(root)
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["failures"], [])

    def test_unexpected_entrypoint_is_a_failure_even_when_not_named_legacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "src" / "nunchi"
            package.mkdir(parents=True)
            package.joinpath("__init__.py").write_text("\n", encoding="utf-8")
            contract = runner.load_surface_contract()
            scripts = dict(contract["required_scripts"])
            scripts["nunchi-mystery"] = "nunchi.mystery:main"
            rendered = "\n".join(
                f'{json.dumps(name)} = {json.dumps(target)}'
                for name, target in scripts.items()
            )
            root.joinpath("pyproject.toml").write_text(
                "[project]\n"
                'name = "nunchi"\n'
                'version = "2.0.0"\n'
                "[project.scripts]\n"
                f"{rendered}\n",
                encoding="utf-8",
            )
            audit = runner.audit_repository(root)
        self.assertEqual(audit["unexpected_scripts"], ["nunchi-mystery"])
        self.assertIn("unexpected-entrypoints-present", audit["failures"])

    def test_deterministic_repository_record_is_byte_stable(self):
        first = runner.run(install_probe=False, deterministic_time=True)
        second = runner.run(install_probe=False, deterministic_time=True)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
