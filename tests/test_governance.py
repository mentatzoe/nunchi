"""Tests for the SpecKit control-plane boundary."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts import check_governance


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipIf(
    os.environ.get("NUNCHI_SKIP_GOVERNANCE_TESTS") == "1"
    or not (ROOT / ".specify").is_dir(),
    "SpecKit control plane intentionally absent from this verification copy",
)
class GovernanceBoundaryTests(unittest.TestCase):
    def test_repository_governance_boundary_is_clean(self):
        self.assertEqual(check_governance.validate(ROOT), [])

    def test_product_artifact_is_rejected_under_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forbidden = root / "specs" / "001-slice" / "contracts" / "schema.json"
            forbidden.parent.mkdir(parents=True)
            forbidden.write_text("{}", encoding="utf-8")
            errors = check_governance.check_control_plane(root)
        self.assertTrue(any("forbidden under specs" in error for error in errors))

    def test_executable_dependency_on_specs_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = root / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("run: python specs/001-slice/test.py\n", encoding="utf-8")
            errors = check_governance.check_runtime_dependencies(root)
        self.assertTrue(any("depends on managed path" in error for error in errors))

    def test_executable_dependency_on_speckit_skill_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "scripts" / "release.py"
            script.parent.mkdir(parents=True)
            script.write_text(
                'open(".agents/skills/speckit-plan/SKILL.md")\n',
                encoding="utf-8",
            )
            errors = check_governance.check_runtime_dependencies(root)
        self.assertTrue(any("depends on managed path" in error for error in errors))

    def test_fixture_payload_is_treated_as_opaque_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "evals" / "suite" / "fixtures" / "captured.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                '{"content":"read .claude/skills/speckit-plan/SKILL.md"}',
                encoding="utf-8",
            )
            self.assertEqual(check_governance.check_runtime_dependencies(root), [])

    def test_non_executable_speckit_helper_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper = root / ".specify" / "scripts" / "bash" / "common.sh"
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/bin/sh\n", encoding="utf-8")
            helper.chmod(0o644)
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(any("common.sh" in error and "executable" in error for error in errors))

    def test_workflow_command_without_installed_skill_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = root / ".specify" / "workflows" / "nunchi-plan" / "workflow.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "steps:\n  - id: missing\n    command: speckit.missing\n",
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(any("speckit-missing" in error for error in errors))

    def test_dependency_cycle_is_rejected(self):
        graph = {"010": ("020",), "020": ("010",)}
        self.assertEqual(
            check_governance._graph_cycle(graph),
            ["010", "020", "010"],
        )

    def test_slice_metadata_parser_reads_wrapped_values(self):
        text = "**Depends on**: `010`, `020`,\n`030`\n\n## Next\n"
        self.assertEqual(
            check_governance._slice_ids(
                check_governance._metadata_value(text, "Depends on")
            ),
            ("010", "020", "030"),
        )

    def test_broken_local_documentation_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide = root / "docs" / "guide.md"
            guide.parent.mkdir(parents=True)
            guide.write_text("See [missing](not-there.md).\n", encoding="utf-8")
            errors = check_governance.check_runtime_dependencies(root)
        self.assertTrue(any("link target does not exist" in error for error in errors))

    def test_installed_speckit_commit_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool_dir = Path(tmp)
            direct_url = (
                tool_dir
                / "specify-cli"
                / "lib"
                / "python3.14"
                / "site-packages"
                / "specify_cli-0.12.11.dist-info"
                / "direct_url.json"
            )
            direct_url.parent.mkdir(parents=True)
            direct_url.write_text(
                json.dumps(
                    {
                        "url": "https://github.com/github/spec-kit.git",
                        "vcs_info": {
                            "vcs": "git",
                            "commit_id": "wrong",
                            "requested_revision": "wrong",
                        },
                    }
                ),
                encoding="utf-8",
            )
            errors = check_governance._check_installed_direct_url(tool_dir)
        self.assertTrue(any("immutable SpecKit pin" in error for error in errors))

    def test_stock_optional_test_template_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / ".specify" / "templates" / "tasks-template.md"
            template.parent.mkdir(parents=True)
            template.write_text("Tests are OPTIONAL\n", encoding="utf-8")
            errors = check_governance.check_governance_documents(root)
        self.assertTrue(any("stock template contradicts" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
