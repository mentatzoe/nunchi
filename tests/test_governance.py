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
    @staticmethod
    def _valid_documentation_planning(dirname="010-v2-contract"):
        expected_paths = sorted(
            check_governance.EXPECTED_DOCUMENTATION_PATHS.get(dirname, set())
        )
        spec_paths = "\n".join(f"- `{path}`" for path in expected_paths)
        spec = f"""## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` exact delta to `v2-integrator`.
- **Handoff evidence**: `evidence/v2/example/handoff.md` records review.
- **Affected ordinary docs**:
{spec_paths}
"""
        readme_disposition = "UPDATE" if dirname == "110-v2-parity-cutover" else "HANDOFF"
        owner = "v2-integrator" if readme_disposition == "UPDATE" else "owner to v2-integrator"
        readme_details = (
            "Validate exact current-state claims against the candidate."
            if readme_disposition == "UPDATE"
            else "Accepting owner: `v2-integrator`; apply the exact candidate claim delta."
        )
        rows = [
            f"| Global state | `README.md` | `{readme_disposition}` | {owner} | {readme_details} |",
            "| Owned guide | `docs/example.md` | `UPDATE` | owner | Validate links, commands, and examples against the candidate. |",
        ]
        for path in expected_paths:
            if path == "README.md":
                continue
            disposition = "UPDATE" if dirname == "110-v2-parity-cutover" else "HANDOFF"
            details = (
                "Validate exact claims against the accepted atomic candidate."
                if disposition == "UPDATE"
                else "Accepting owner: `v2-integrator`; apply the exact interface claim delta."
            )
            rows.append(
                f"| Known path | `{path}` | `{disposition}` | owner | {details} |"
            )
        plan = f"""## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
{chr(10).join(rows)}
"""
        tasks = (
            "- [ ] T001 Complete documentation freshness and every exact plan.md "
            "Documentation Impact and Freshness row for README.md and docs; "
            "record documentation dispositions, validation, and reviewer in handoff evidence.\n"
        )
        checklist = "- [x] CHK001 Documentation freshness is concrete.\n"
        return spec, plan, tasks, checklist

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

    def test_documentation_plan_requires_readme_disposition(self):
        spec, plan, tasks, checklist = self._valid_documentation_planning()
        plan = plan.replace("`README.md`", "`docs/other.md`", 1)
        errors = check_governance._documentation_planning_errors(
            "010-v2-contract", spec, plan, tasks, checklist
        )
        self.assertTrue(any("one README.md row" in error for error in errors))

    def test_bare_no_impact_documentation_disposition_is_rejected(self):
        spec, plan, tasks, checklist = self._valid_documentation_planning()
        plan += (
            "| Unchanged guide | `docs/unchanged.md` | `NO_IMPACT` | owner | "
            "Nothing changed here. |\n"
        )
        errors = check_governance._documentation_planning_errors(
            "010-v2-contract", spec, plan, tasks, checklist
        )
        self.assertTrue(any("NO_IMPACT row lacks concrete rationale" in error for error in errors))

    def test_generic_documentation_directory_is_rejected(self):
        spec, plan, tasks, checklist = self._valid_documentation_planning()
        plan += (
            "| Generic docs | `docs/` | `UPDATE` | owner | "
            "Validate every file without naming any exact path. |\n"
        )
        errors = check_governance._documentation_planning_errors(
            "010-v2-contract", spec, plan, tasks, checklist
        )
        self.assertTrue(any("generic documentation path" in error for error in errors))

    def test_documentation_gate_requires_task_and_checklist_coverage(self):
        spec, plan, _, _ = self._valid_documentation_planning()
        errors = check_governance._documentation_planning_errors(
            "010-v2-contract", spec, plan, "- [ ] T001 Implement code.\n", ""
        )
        self.assertTrue(any("tasks.md" in error for error in errors))
        self.assertTrue(any("checklists/requirements.md" in error for error in errors))

    def test_final_integrator_readme_disposition_must_update(self):
        spec, plan, tasks, checklist = self._valid_documentation_planning(
            "110-v2-parity-cutover"
        )
        plan = plan.replace("`UPDATE`", "`HANDOFF`", 1)
        errors = check_governance._documentation_planning_errors(
            "110-v2-parity-cutover", spec, plan, tasks, checklist
        )
        self.assertTrue(any("README.md disposition must be UPDATE" in error for error in errors))

    def test_workflow_requires_documentation_gate_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            full = root / ".specify" / "workflows" / "speckit" / "workflow.yml"
            planning = root / ".specify" / "workflows" / "nunchi-plan" / "workflow.yml"
            full.parent.mkdir(parents=True)
            planning.parent.mkdir(parents=True)
            full.write_text(
                "steps:\n"
                "  - id: goal-2-authorization\n"
                "  - command: speckit.implement\n"
                "  - command: speckit.converge\n"
                "  - id: integration-handoff\n",
                encoding="utf-8",
            )
            planning.write_text("steps:\n", encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "workflows": {
                            "speckit": {"version": "2.1.0"},
                            "nunchi-plan": {"version": "1.1.0"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(any("documentation freshness after" in error for error in errors))

    def test_goal_2_tasks_remain_dormant_without_external_authorization(self):
        errors = check_governance._checked_task_authorization_errors(
            Path("specs/010-v2-contract"),
            "- [X] T001 Implement the contract.\n",
            False,
        )
        self.assertTrue(any("without valid" in error for error in errors))
        self.assertEqual(
            check_governance._checked_task_authorization_errors(
                Path("specs/010-v2-contract"),
                "- [X] T001 Implement the contract.\n",
                True,
            ),
            [],
        )

    def test_goal_2_authorization_record_is_external_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / check_governance.GOAL_2_AUTHORIZATION_PATH
            path.parent.mkdir(parents=True)
            path.write_text(
                "# Nunchi V2 Goal 2 Authorization\n\n"
                "**Program**: `001-nunchi-v2-program`\n\n"
                "**Status**: AUTHORIZED\n\n"
                "**Authorized by**: Zoe\n\n"
                "**Authorized on**: 2026-07-12\n\n"
                f"**Starting commit**: `{'a' * 40}`\n\n"
                "**Objective**: Implement and validate the complete atomic Nunchi V2 lifecycle across every owned surface.\n\n"
                "**Authority source**: Zoe-set Codex Goal 2 in the project thread.\n\n"
                "This record documents external authorization; it does not grant it.\n",
                encoding="utf-8",
            )
            authorized, errors = check_governance._goal_2_authorization_state(root)
        self.assertTrue(authorized)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
