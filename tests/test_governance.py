"""Tests for the SpecKit control-plane boundary."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
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
    def _init_git_repo(root: Path) -> str:
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "governance@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Governance Test"],
            cwd=root,
            check=True,
        )
        seed = root / "seed.txt"
        seed.write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "seed"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _next_git_commit(root: Path, marker: str) -> str:
        path = root / "seed.txt"
        path.write_text(
            path.read_text(encoding="utf-8") + f"{marker}\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "seed.txt"], cwd=root, check=True)
        subprocess.run(
            ["git", "commit", "-m", marker],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _commit_all(root: Path, marker: str) -> str:
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(
            ["git", "commit", "-m", marker],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _task_fields(tasks_text: str) -> tuple[str, str]:
        return check_governance._task_manifest(
            check_governance._task_entries(tasks_text)
        )

    @staticmethod
    def _write_assignment(root: Path, identity: str, lane: str, slug: str) -> str:
        relative = Path(f"evidence/governance/assignments/{slug}.md")
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"""# Assignment
**Assignee**: {identity}
**Lane**: {lane}
**Assigned by**: Zoe
**Assigned on**: 2026-07-12
**Authority reference**: durable Zoe assignment decision {slug}
""",
            encoding="utf-8",
        )
        return f"{identity} — {relative.as_posix()}"

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
        readme_disposition = (
            "UPDATE" if dirname == "110-v2-parity-cutover" else "HANDOFF"
        )
        owner = (
            "v2-integrator"
            if readme_disposition == "UPDATE"
            else "owner to v2-integrator"
        )
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

    def test_activation_metadata_uses_the_plan_at_its_starting_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = Path("specs/010-v2-contract/plan.md")
            path = root / relative
            path.parent.mkdir(parents=True)
            base_plan = (
                "# Plan\n\nI-010A\n\nS01\n\n"
                "`evidence/v2/contract/base.jsonl`\n"
            )
            path.write_text(base_plan, encoding="utf-8")
            starting_commit = self._init_git_repo(root)
            path.write_text(base_plan + "\nI-010F\n\nS18\n", encoding="utf-8")
            self._commit_all(root, "append accepted amendment plan")

            self.assertEqual(
                check_governance._activation_bound_plan_text(
                    root, starting_commit, relative
                ),
                base_plan,
            )

    def test_product_artifact_is_rejected_under_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forbidden = root / "specs" / "001-slice" / "contracts" / "schema.json"
            forbidden.parent.mkdir(parents=True)
            forbidden.write_text("{}", encoding="utf-8")
            errors = check_governance.check_control_plane(root)
        self.assertTrue(any("forbidden under specs" in error for error in errors))

    def test_managed_roots_use_exact_control_plane_allowlists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rogue_specify = root / ".specify" / "product.py"
            rogue_specify.parent.mkdir(parents=True)
            rogue_specify.write_text("pass\n", encoding="utf-8")
            rogue_skill = root / ".agents" / "skills" / "speckit-plan" / "runner.py"
            rogue_skill.parent.mkdir(parents=True)
            rogue_skill.write_text("pass\n", encoding="utf-8")
            rogue_checklist = (
                root / "specs" / "010-v2-contract" / "checklists" / "extra.md"
            )
            rogue_checklist.parent.mkdir(parents=True)
            rogue_checklist.write_text("# Extra\n", encoding="utf-8")
            errors = check_governance.check_control_plane(root)
        self.assertTrue(
            any(".specify control-plane allowlist" in error for error in errors)
        )
        self.assertTrue(any("only SKILL.md" in error for error in errors))
        self.assertTrue(any("planning allowlist" in error for error in errors))

    def test_normal_specify_run_log_is_allowed_control_plane_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".specify/workflows/runs/bound-run/log.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text('{"event":"workflow_finished"}\n', encoding="utf-8")

            errors = check_governance.check_control_plane(root)

        self.assertEqual(errors, [])

    def test_executable_dependency_on_specs_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = root / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "run: python specs/001-slice/test.py\n", encoding="utf-8"
            )
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
        self.assertTrue(
            any("common.sh" in error and "executable" in error for error in errors)
        )

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

    def test_slice_metadata_keeps_unknown_and_duplicate_ids_for_rejection(self):
        self.assertEqual(
            check_governance._slice_ids("010, 010, 999"), ("010", "010", "999")
        )

    def test_broken_local_documentation_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide = root / "docs" / "guide.md"
            guide.parent.mkdir(parents=True)
            guide.write_text("See [missing](not-there.md).\n", encoding="utf-8")
            errors = check_governance.check_runtime_dependencies(root)
        self.assertTrue(any("link target does not exist" in error for error in errors))

    def test_malformed_documentation_is_rejected_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assignment = (
                root
                / "evidence"
                / "governance"
                / "assignments"
                / "malformed.md"
            )
            assignment.parent.mkdir(parents=True)
            assignment.write_bytes(b"\xff")
            errors = check_governance.check_runtime_dependencies(root)
        self.assertTrue(any("documentation is unreadable" in error for error in errors))

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
        self.assertTrue(
            any("NO_IMPACT row lacks concrete rationale" in error for error in errors)
        )

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
        self.assertTrue(
            any("README.md disposition must be UPDATE" in error for error in errors)
        )

    def test_workflow_requires_complete_lifecycle_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            full = root / ".specify" / "workflows" / "speckit" / "workflow.yml"
            planning = root / ".specify" / "workflows" / "nunchi-plan" / "workflow.yml"
            full.parent.mkdir(parents=True)
            planning.parent.mkdir(parents=True)
            full.write_text(
                "inputs:\n"
                "  slice_directory:\n"
                "    required: true\n"
                "description: Only slice 110 performs integration or cutover\n"
                "steps:\n"
                "  - id: bind-existing-slice\n"
                "    run: python3 scripts/check_slice_binding.py {{ inputs.slice_directory }}; "
                "export SPECIFY_FEATURE_DIRECTORY={{ inputs.slice_directory }} without "
                "modifying .specify/feature.json\n"
                "  - command: speckit.analyze\n"
                "  - id: implementation-authorization\n"
                f"    run: test -f {check_governance.IMPLEMENTATION_AUTHORIZATION_PATH}\n"
                "  - id: slice-readiness\n"
                "  - id: activate-slice\n"
                "  - command: speckit.implement\n"
                "  - command: speckit.converge\n"
                "  - id: record-convergence\n"
                "  - id: prepare-handoff\n"
                "  - id: slice-handoff\n"
                "  - id: documentation-freshness\n",
                encoding="utf-8",
            )
            planning.write_text("steps:\n", encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "workflows": {
                            "speckit": {"version": "2.6.0"},
                            "nunchi-plan": {"version": "1.4.0"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(
            any("complete analyze-through-handoff" in error for error in errors)
        )

    def test_workflow_rejects_inline_hidden_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("speckit", "nunchi-plan"):
                source = ROOT / ".specify" / "workflows" / name / "workflow.yml"
                target = root / ".specify" / "workflows" / name / "workflow.yml"
                target.parent.mkdir(parents=True, exist_ok=True)
                text = source.read_text(encoding="utf-8")
                if name == "speckit":
                    text += (
                        "\n  - {id: bypass-authority, type: shell, "
                        'run: "echo bypass"}\n'
                    )
                target.write_text(text, encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                (ROOT / ".specify" / "workflows" / "workflow-registry.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(
            any("inline workflow step is forbidden" in error for error in errors)
        )

    def test_delivery_workflow_has_bounded_accepted_amendment_path(self):
        text = (
            ROOT / ".specify" / "workflows" / "speckit" / "workflow.yml"
        ).read_text(encoding="utf-8")
        for token in (
            'version: "2.6.0"',
            "post-acceptance amendment",
            "stable owner lane has exactly one valid current occupant",
            "terminal activation/candidate/handoff/acceptance records are unchanged",
            "declarations remain ACCEPTED",
            "fixed amendment record",
            "slice-amendments.md",
            "prior effective commit unchanged",
        ):
            self.assertIn(token, text)

    def test_workflow_registry_version_must_match_embedded_workflow_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("speckit", "nunchi-plan"):
                source = ROOT / ".specify" / "workflows" / name / "workflow.yml"
                target = root / ".specify" / "workflows" / name / "workflow.yml"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                (ROOT / ".specify" / "workflows" / "workflow-registry.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            delivery = root / ".specify/workflows/speckit/workflow.yml"
            delivery.write_text(
                delivery.read_text(encoding="utf-8").replace(
                    '  version: "2.6.0"', '  version: "2.5.0"', 1
                ),
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(any("embedded version must be 2.6.0" in error for error in errors))

    def test_workflow_rejects_non_aborting_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("speckit", "nunchi-plan"):
                source = ROOT / ".specify" / "workflows" / name / "workflow.yml"
                target = root / ".specify" / "workflows" / name / "workflow.yml"
                target.parent.mkdir(parents=True, exist_ok=True)
                text = source.read_text(encoding="utf-8")
                if name == "speckit":
                    text = text.replace(
                        "    on_reject: abort", "    on_reject: skip", 1
                    )
                target.write_text(text, encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                (ROOT / ".specify" / "workflows" / "workflow-registry.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(any("on_reject: abort" in error for error in errors))

    def test_post_activation_gate_must_pause_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("speckit", "nunchi-plan"):
                source = ROOT / ".specify" / "workflows" / name / "workflow.yml"
                target = root / ".specify" / "workflows" / name / "workflow.yml"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                (ROOT / ".specify" / "workflows" / "workflow-registry.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            workflow = root / ".specify/workflows/speckit/workflow.yml"
            text = workflow.read_text(encoding="utf-8")
            marker = "  - id: record-convergence\n"
            before, after = text.split(marker, 1)
            after = after.replace("    on_reject: retry", "    on_reject: abort", 1)
            workflow.write_text(before + marker + after, encoding="utf-8")

            errors = check_governance.check_workflow_surface(root)

        self.assertTrue(any("on_reject: retry" in error for error in errors))

    def test_workflow_rejects_duplicate_gate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("speckit", "nunchi-plan"):
                source = ROOT / ".specify" / "workflows" / name / "workflow.yml"
                target = root / ".specify" / "workflows" / name / "workflow.yml"
                target.parent.mkdir(parents=True, exist_ok=True)
                text = source.read_text(encoding="utf-8")
                if name == "speckit":
                    text = text.replace(
                        "    on_reject: abort\n",
                        "    on_reject: abort\n    on_reject: abort\n",
                        1,
                    )
                target.write_text(text, encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                (ROOT / ".specify" / "workflows" / "workflow-registry.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(any("duplicate YAML keys" in error for error in errors))

    def test_workflow_rejects_duplicate_nested_args_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("speckit", "nunchi-plan"):
                source = ROOT / ".specify" / "workflows" / name / "workflow.yml"
                target = root / ".specify" / "workflows" / name / "workflow.yml"
                target.parent.mkdir(parents=True, exist_ok=True)
                text = source.read_text(encoding="utf-8")
                if name == "speckit":
                    text = text.replace(
                        '      args: "Resolve only material ambiguity;',
                        '      args: &unsafe "Resolve only material ambiguity;',
                        1,
                    )
                    text = text.replace(
                        '      args: &unsafe "Resolve only material ambiguity; preserve the repository-owned selected design and current accepted lifecycle evidence."',
                        '      args: &unsafe "Resolve only material ambiguity; preserve the repository-owned selected design and current accepted lifecycle evidence."\n'
                        "      args: *unsafe",
                        1,
                    )
                target.write_text(text, encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                (ROOT / ".specify" / "workflows" / "workflow-registry.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            errors = check_governance.check_workflow_surface(root)

        self.assertTrue(any("duplicate nested YAML keys" in error for error in errors))
        self.assertTrue(any("aliases or merges" in error for error in errors))

    def test_workflow_requires_authority_text_in_its_own_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("speckit", "nunchi-plan"):
                source = ROOT / ".specify" / "workflows" / name / "workflow.yml"
                target = root / ".specify" / "workflows" / name / "workflow.yml"
                target.parent.mkdir(parents=True, exist_ok=True)
                text = source.read_text(encoding="utf-8")
                if name == "speckit":
                    text = text.replace(
                        "enumerates exactly all eleven slices 010-110",
                        "enumerates all eleven slices 010-110",
                        1,
                    )
                    text = text.replace(
                        "SLICE BINDING:",
                        "SLICE BINDING: enumerates exactly all eleven slices 010-110.",
                        1,
                    )
                target.write_text(text, encoding="utf-8")
            registry = root / ".specify" / "workflows" / "workflow-registry.json"
            registry.write_text(
                (ROOT / ".specify" / "workflows" / "workflow-registry.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            errors = check_governance.check_workflow_surface(root)
        self.assertTrue(
            any(
                "step 'implementation-authorization'" in error
                and "exactly all eleven" in error
                for error in errors
            )
        )

    def test_slice_binding_preflight_is_exact_and_read_only(self):
        feature_state = ROOT / ".specify" / "feature.json"
        before = feature_state.read_bytes()
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_slice_binding.py"),
                "specs/030-v2-core-attention",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        after = feature_state.read_bytes()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(before, after)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["SLICE_DIRECTORY"], "specs/030-v2-core-attention")
        self.assertFalse(payload["PERSISTED_FEATURE_STATE"])
        self.assertIn("tasks.md", payload["REQUIRED_ARTIFACTS"])
        self.assertIn("tasks.md", payload["AVAILABLE_DOCS"])

    def test_normal_prerequisite_helper_keeps_explicit_slice_binding_local(self):
        feature_state = ROOT / ".specify" / "feature.json"
        before = feature_state.read_bytes()
        environment = os.environ.copy()
        environment["SPECIFY_FEATURE_DIRECTORY"] = "specs/030-v2-core-attention"
        completed = subprocess.run(
            [
                str(ROOT / ".specify" / "scripts" / "bash" / "check-prerequisites.sh"),
                "--json",
                "--require-tasks",
                "--include-tasks",
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(before, feature_state.read_bytes())
        payload = json.loads(completed.stdout)
        self.assertEqual(
            Path(payload["FEATURE_DIR"]).resolve(),
            (ROOT / "specs/030-v2-core-attention").resolve(),
        )

    def test_slice_binding_preflight_rejects_umbrella_and_traversal(self):
        for unsafe in ("specs/001-nunchi-v2-program", "specs/../outside"):
            with self.subTest(unsafe=unsafe):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "check_slice_binding.py"),
                        unsafe,
                    ],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("canonical slice", completed.stderr)

    def test_checked_slice_task_requires_authority_active_state_and_activation(self):
        feature = Path("specs/010-v2-contract")
        checked = "- [X] T001 Implement the contract.\n"

        errors = check_governance._checked_slice_task_errors(
            feature,
            checked,
            False,
            "ACTIVE",
            True,
        )
        self.assertTrue(any("without valid" in error for error in errors))

        errors = check_governance._checked_slice_task_errors(
            feature,
            checked,
            True,
            "PLANNED",
            True,
        )
        self.assertTrue(any("PLANNED" in error for error in errors))

        errors = check_governance._checked_slice_task_errors(
            feature,
            checked,
            True,
            "ACTIVE",
            False,
        )
        self.assertTrue(any("activation evidence" in error for error in errors))

        self.assertEqual(
            check_governance._checked_slice_task_errors(
                feature,
                checked,
                True,
                "ACTIVE",
                True,
            ),
            [],
        )

    def test_planned_slice_with_unchecked_tasks_remains_dormant(self):
        self.assertEqual(
            check_governance._checked_slice_task_errors(
                Path("specs/010-v2-contract"),
                "- [ ] T001 Implement the contract.\n",
                False,
                "PLANNED",
                False,
            ),
            [],
        )

    def test_task_manifest_cli_prints_canonical_read_only_fields(self):
        tasks = ROOT / "specs" / "030-v2-core-attention" / "tasks.md"
        before = tasks.read_bytes()
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_governance.py"),
                "--task-manifest",
                "specs/030-v2-core-attention",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(before, tasks.read_bytes())
        task_ids, digest = check_governance.task_manifest_for_slice(
            ROOT, "specs/030-v2-core-attention"
        )
        _initial_ids, _digest, completed_ids = (
            check_governance.task_manifest_state_for_slice(
                ROOT, "specs/030-v2-core-attention"
            )
        )
        self.assertIn(f"**Initial task IDs**: {task_ids}", completed.stdout)
        self.assertIn(f"**Initial tasks SHA256**: {digest}", completed.stdout)
        self.assertIn(f"**Completed task IDs**: {completed_ids}", completed.stdout)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_task_manifest_state_preserves_literal_checkbox_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = root / "specs/010-v2-contract/tasks.md"
            tasks.parent.mkdir(parents=True)
            tasks.write_text(
                "- [X] T001 Done\n- [ ] T002 Still open\n",
                encoding="utf-8",
            )
            initial_ids, digest, completed_ids = (
                check_governance.task_manifest_state_for_slice(
                    root, "specs/010-v2-contract"
                )
            )
        self.assertEqual(initial_ids, "T001, T002")
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(completed_ids, "T001")

    def test_candidate_completion_rejects_any_open_committed_checkbox(self):
        tasks_text = "- [X] T001 Done\n- [ ] T002 Still open\n"
        entries = check_governance._validated_task_entries(tasks_text)
        errors = check_governance._candidate_task_completion_errors(
            tasks_complete="YES",
            declared_completed="T001, T002",
            committed_tasks=tasks_text,
            committed_task_entries=entries,
            prefix="candidate record",
        )
        self.assertTrue(
            any("every committed task checkbox" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("Completed task IDs must be exactly 'T001'" in error for error in errors),
            errors,
        )

    def test_task_manifest_rejects_gaps_and_noncanonical_checkboxes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = root / "specs/010-v2-contract/tasks.md"
            tasks.parent.mkdir(parents=True)
            tasks.write_text(
                "- [ ] T001 First\n- [ ] T003 Gap\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "sequential"):
                check_governance.task_manifest_for_slice(root, "specs/010-v2-contract")
            tasks.write_text("- [ ] 001 Missing T\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid task format"):
                check_governance.task_manifest_for_slice(root, "specs/010-v2-contract")

    @staticmethod
    def _write_lifecycle_record(root: Path, relative: str, text: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_slice_lifecycle_evidence_proves_each_declared_transition(self):
        dirname = "010-v2-contract"
        expected = check_governance.EXPECTED_SLICES[dirname]
        paths = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname]
        assigned = "Alice — durable assignment decision 42"
        tasks = "- [ ] T001 Work\n"
        task_ids, task_hash = self._task_fields(tasks)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starting_sha = self._init_git_repo(root)
            committed_tasks = root / "specs" / dirname / "tasks.md"
            committed_tasks.parent.mkdir(parents=True)
            committed_tasks.write_text("- [X] T001 Work\n", encoding="utf-8")
            self._write_lifecycle_record(
                root,
                "evidence/v2/contract/results.json",
                "{}\n",
            )
            sha = self._commit_all(root, "candidate")
            self._write_lifecycle_record(
                root,
                paths["activation"],
                f"""# Activation
**Slice**: `{dirname}`
**Status**: READY
**Assigned participant / source**: {assigned}
**Authority record**: `{check_governance.IMPLEMENTATION_AUTHORIZATION_PATH}`
**Accepted dependencies**: none
**Dependency commits**: none
**Dependency acceptance references**: none
**Analysis result**: PASS — zero CRITICAL/HIGH findings
**Branch**: `{expected["branch"]}`
**Worktree**: `{expected["worktree"]}`
**Starting commit**: `{starting_sha}`
**Interfaces**: I-010A through I-010E
**Acceptance scenes**: S01-S16 as planned
**Evidence targets**: exact ordinary paths
**Documentation scope**: exact README/docs dispositions
**Initial task IDs**: {task_ids}
**Initial tasks SHA256**: {task_hash}
""",
            )
            self.assertEqual(
                check_governance._slice_lifecycle_evidence_errors(
                    root, dirname, expected, "ACTIVE", assigned, tasks
                ),
                [],
            )
            changed_task_errors = check_governance._slice_lifecycle_evidence_errors(
                root,
                dirname,
                expected,
                "ACTIVE",
                assigned,
                "- [ ] T001 Changed after activation\n",
            )
            self.assertTrue(
                any("Initial tasks SHA256" in error for error in changed_task_errors)
            )

            self._write_lifecycle_record(
                root,
                paths["candidate"],
                f"""# Candidate
**Slice**: `{dirname}`
**Status**: CONVERGED
**Candidate commit**: `{sha}`
**Tasks complete**: YES
**Completed task IDs**: {task_ids}
**Tasks SHA256**: {task_hash}
**Verification commands / results**: PASS — full suite
**Interface versions**: I-010A through I-010E at version 1
**Evidence paths**: evidence/v2/contract/results.json
**Known limitations**: NONE
""",
            )
            self._write_lifecycle_record(
                root,
                paths["handoff"],
                f"""# Handoff
**Slice**: `{dirname}`
**Status**: HANDOFF_READY
**Candidate commit**: `{sha}`
**Acceptance owner**: v2-integrator
**Documentation freshness**: PASS
**Packet paths**: evidence/v2/contract/packet.md
""",
            )
            self._write_lifecycle_record(
                root,
                "evidence/v2/contract/packet.md",
                "# Packet\n",
            )
            self._write_lifecycle_record(
                root,
                paths["acceptance"],
                f"""# Acceptance
**Slice**: `{dirname}`
**Status**: ACCEPTED
**Candidate commit**: `{sha}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-12
**Decision reference**: durable integration acceptance 42
**Recorded by**: v2-integrator
""",
            )
            self.assertEqual(
                check_governance._slice_lifecycle_evidence_errors(
                    root, dirname, expected, "ACCEPTED", assigned, "- [X] T001 Work\n"
                ),
                [],
            )

    def test_slice_lifecycle_rejects_premature_or_empty_evidence(self):
        dirname = "010-v2-contract"
        expected = check_governance.EXPECTED_SLICES[dirname]
        paths = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_lifecycle_record(root, paths["candidate"], "")
            errors = check_governance._slice_lifecycle_evidence_errors(
                root,
                dirname,
                expected,
                "PLANNED",
                "UNASSIGNED — awaiting durable assignment source",
                "- [ ] T001 Work\n",
            )
        self.assertTrue(any("while the slice is PLANNED" in error for error in errors))

    def test_lifecycle_evidence_rejects_symlinks(self):
        dirname = "010-v2-contract"
        expected = check_governance.EXPECTED_SLICES[dirname]
        relative = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname]["candidate"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "outside.md"
            target.write_text("# Outside\n", encoding="utf-8")
            path = root / relative
            path.parent.mkdir(parents=True)
            path.symlink_to(target)
            errors = check_governance._slice_lifecycle_evidence_errors(
                root,
                dirname,
                expected,
                "PLANNED",
                "UNASSIGNED — waiting",
                "- [ ] T001 Work\n",
            )
        self.assertTrue(any("path is unsafe" in error for error in errors))

    def test_git_history_enforces_immutable_and_append_only_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_git_repo(root)
            immutable = Path("evidence/v2/contract/slice-activation.md")
            immutable_path = root / immutable
            immutable_path.parent.mkdir(parents=True)
            immutable_path.write_text("activation\n", encoding="utf-8")
            append_only = Path("evidence/v2/contract/slice-candidate.md")
            append_path = root / append_only
            append_path.write_text("attempt one\n", encoding="utf-8")
            subprocess.run(["git", "add", "evidence"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "lifecycle"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            immutable_path.write_text("rewritten\n", encoding="utf-8")
            immutable_errors = check_governance._git_path_history_errors(
                root, immutable, append_only=False
            )
            self.assertTrue(
                any("may not be rewritten" in error for error in immutable_errors)
            )

            append_path.write_text("attempt one\nattempt two\n", encoding="utf-8")
            self.assertEqual(
                check_governance._git_path_history_errors(
                    root, append_only, append_only=True
                ),
                [],
            )
            append_path.write_text("replacement\n", encoding="utf-8")
            append_errors = check_governance._git_path_history_errors(
                root, append_only, append_only=True
            )
            self.assertTrue(any("only be extended" in error for error in append_errors))

    def test_full_history_replay_catches_laundered_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_git_repo(root)
            relative = Path("evidence/v2/contract/slice-candidate.md")
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_text("attempt one\n", encoding="utf-8")
            self._commit_all(root, "attempt one")
            path.write_text("destructive rewrite\n", encoding="utf-8")
            self._commit_all(root, "rewrite")
            path.write_text("destructive rewrite\nvalid append\n", encoding="utf-8")
            self._commit_all(root, "append after rewrite")

            errors = check_governance._git_path_history_errors(
                root, relative, append_only=True
            )

        self.assertTrue(any("rewrote prior history" in error for error in errors))

    def test_assignment_rejects_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            (outside / "alice.md").write_text(
                "# Assignment\n"
                "**Assignee**: Alice\n"
                "**Lane**: v2-contract-owner\n"
                "**Assigned by**: Zoe\n"
                "**Assigned on**: 2026-07-12\n"
                "**Authority reference**: durable Zoe assignment\n",
                encoding="utf-8",
            )
            assignment_root = root / "evidence/governance/assignments"
            assignment_root.parent.mkdir(parents=True)
            assignment_root.symlink_to(outside, target_is_directory=True)

            errors = check_governance._assignment_errors(
                root,
                "Alice — evidence/governance/assignments/alice.md",
                "v2-contract-owner",
                "specs/010-v2-contract",
            )

        self.assertTrue(any("path is unsafe" in error for error in errors))

    def test_rejected_handoff_can_be_reworked_append_only(self):
        dirname = "010-v2-contract"
        expected = check_governance.EXPECTED_SLICES[dirname]
        paths = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname]
        assigned = "Alice — durable assignment decision 42"
        complete_tasks = "- [X] T001 Work\n"
        task_ids, task_hash = self._task_fields(complete_tasks)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starting_sha = self._init_git_repo(root)
            committed_tasks = root / "specs" / dirname / "tasks.md"
            committed_tasks.parent.mkdir(parents=True)
            committed_tasks.write_text(complete_tasks, encoding="utf-8")
            self._write_lifecycle_record(
                root, "evidence/v2/contract/results-one.json", "{}\n"
            )
            first_sha = self._commit_all(root, "first candidate")
            self._write_lifecycle_record(
                root,
                paths["activation"],
                f"""# Activation
**Slice**: `{dirname}`
**Status**: READY
**Assigned participant / source**: {assigned}
**Authority record**: `{check_governance.IMPLEMENTATION_AUTHORIZATION_PATH}`
**Accepted dependencies**: none
**Dependency commits**: none
**Dependency acceptance references**: none
**Analysis result**: PASS — zero CRITICAL/HIGH findings
**Branch**: `{expected["branch"]}`
**Worktree**: `{expected["worktree"]}`
**Starting commit**: `{starting_sha}`
**Interfaces**: I-010A through I-010E
**Acceptance scenes**: S01-S16 as planned
**Evidence targets**: evidence/v2/contract/results-one.json
**Documentation scope**: README.md and docs/contracts.md
**Initial task IDs**: {task_ids}
**Initial tasks SHA256**: {task_hash}
""",
            )
            for name in ("packet-one.md", "packet-two.md"):
                self._write_lifecycle_record(
                    root, f"evidence/v2/contract/{name}", "# Packet\n"
                )
            self._write_lifecycle_record(
                root,
                paths["candidate"],
                f"""# Candidate attempt 1
**Slice**: `{dirname}`
**Status**: CONVERGED
**Candidate commit**: `{first_sha}`
**Tasks complete**: YES
**Completed task IDs**: {task_ids}
**Tasks SHA256**: {task_hash}
**Verification commands / results**: PASS — python3 -m unittest
**Interface versions**: I-010A version 1
**Evidence paths**: evidence/v2/contract/results-one.json
**Known limitations**: NONE
""",
            )
            self._write_lifecycle_record(
                root,
                paths["handoff"],
                f"""# Handoff attempt 1
**Slice**: `{dirname}`
**Status**: HANDOFF_READY
**Candidate commit**: `{first_sha}`
**Acceptance owner**: v2-integrator
**Documentation freshness**: PASS
**Packet paths**: evidence/v2/contract/packet-one.md

## Rejection 1

**Slice**: `{dirname}`
**Status**: REJECTED
**Candidate commit**: `{first_sha}`
**Rejected by**: v2-integrator
**Rejected on**: 2026-07-12
**Decision reference**: durable rejection decision 42
**Recorded by**: v2-integrator
""",
            )
            self.assertEqual(
                check_governance._slice_lifecycle_evidence_errors(
                    root, dirname, expected, "ACTIVE", assigned, complete_tasks
                ),
                [],
            )

            complete_tasks_v2 = "- [X] T001 Work\n- [X] T002 Rework finding\n"
            task_ids_v2, task_hash_v2 = self._task_fields(complete_tasks_v2)
            committed_tasks.write_text(complete_tasks_v2, encoding="utf-8")
            self._write_lifecycle_record(
                root, "evidence/v2/contract/results-two.json", "{}\n"
            )
            second_sha = self._commit_all(root, "rework candidate")

            candidate = root / paths["candidate"]
            candidate.write_text(
                candidate.read_text(encoding="utf-8")
                + f"""
## Candidate attempt 2

**Slice**: `{dirname}`
**Status**: CONVERGED
**Candidate commit**: `{second_sha}`
**Tasks complete**: YES
**Completed task IDs**: {task_ids_v2}
**Tasks SHA256**: {task_hash_v2}
**Verification commands / results**: PASS — python3 -m unittest
**Interface versions**: I-010A version 2
**Evidence paths**: evidence/v2/contract/results-two.json
**Known limitations**: NONE
""",
                encoding="utf-8",
            )
            self.assertEqual(
                check_governance._slice_lifecycle_evidence_errors(
                    root, dirname, expected, "CONVERGED", assigned, complete_tasks_v2
                ),
                [],
            )

            handoff = root / paths["handoff"]
            handoff.write_text(
                handoff.read_text(encoding="utf-8")
                + f"""
## Handoff attempt 2

**Slice**: `{dirname}`
**Status**: HANDOFF_READY
**Candidate commit**: `{second_sha}`
**Acceptance owner**: v2-integrator
**Documentation freshness**: PASS
**Packet paths**: evidence/v2/contract/packet-two.md
""",
                encoding="utf-8",
            )
            self.assertEqual(
                check_governance._slice_lifecycle_evidence_errors(
                    root,
                    dirname,
                    expected,
                    "HANDOFF_READY",
                    assigned,
                    complete_tasks_v2,
                ),
                [],
            )

    def test_dependency_activation_requires_exact_commit_and_acceptance_reference(self):
        dirname = "020-v2-observation"
        expected = check_governance.EXPECTED_SLICES[dirname]
        paths = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname]
        assigned = "Bob — durable assignment decision 43"
        tasks = "- [ ] T001 Work\n"
        task_ids, task_hash = self._task_fields(tasks)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha = self._init_git_repo(root)
            acceptance_reference = (
                "evidence/v2/observation/dependency-010-acceptance.md"
            )
            self._write_lifecycle_record(
                root,
                acceptance_reference,
                f"""# Accepted dependency 010
**Consumer slice**: `{dirname}`
**Upstream slice**: `010-v2-contract`
**Candidate commit**: `{sha}`
**Accepted by**: Bob
**Accepted on**: 2026-07-12
**Packet reference**: `evidence/v2/contract/slice-handoff.md`
**Decision reference**: durable dependency acceptance 43
""",
            )
            self._write_lifecycle_record(
                root,
                check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"]["handoff"],
                f"""# Upstream handoff
**Slice**: `010-v2-contract`
**Status**: HANDOFF_READY
**Candidate commit**: `{sha}`
""",
            )
            activation = f"""# Activation
**Slice**: `{dirname}`
**Status**: READY
**Assigned participant / source**: {assigned}
**Authority record**: `{check_governance.IMPLEMENTATION_AUTHORIZATION_PATH}`
**Accepted dependencies**: 010
**Dependency commits**: 010={sha}
**Dependency acceptance references**: 010={acceptance_reference}
**Analysis result**: PASS — zero CRITICAL/HIGH findings
**Branch**: `{expected["branch"]}`
**Worktree**: `{expected["worktree"]}`
**Starting commit**: `{sha}`
**Interfaces**: I-010A and I-020A
**Acceptance scenes**: S01-S16 as planned
**Evidence targets**: evidence/v2/observation/results.json
**Documentation scope**: README.md and docs/observation.md
**Initial task IDs**: {task_ids}
**Initial tasks SHA256**: {task_hash}
"""
            self._write_lifecycle_record(root, paths["activation"], activation)
            self.assertEqual(
                check_governance._slice_lifecycle_evidence_errors(
                    root, dirname, expected, "READY", assigned, tasks
                ),
                [],
            )

            activation_path = root / paths["activation"]
            activation_path.write_text(
                activation.replace(f"010={sha}", "010=not-a-commit", 1),
                encoding="utf-8",
            )
            errors = check_governance._slice_lifecycle_evidence_errors(
                root, dirname, expected, "READY", assigned, tasks
            )
            self.assertTrue(any("must be a full Git SHA" in error for error in errors))

    def test_candidate_commit_must_exist_in_repository_git(self):
        self.assertFalse(check_governance._git_commit_exists(ROOT, "a" * 40))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(check_governance._git_commit_exists(Path(tmp), "a" * 40))

    def test_effective_dependency_commit_without_ledger_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha = self._init_git_repo(root)
            binding, packet, binding_errors = (
                check_governance._effective_dependency_binding(
                    root, "010-v2-contract", sha
                )
            )
            effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", sha
            )
            self.assertEqual(binding, sha)
            self.assertEqual(
                packet,
                check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                    "handoff"
                ],
            )
            self.assertEqual(binding_errors, [])
            self.assertEqual(effective, sha)
            self.assertEqual(errors, [])

    def _accept_amendment_commit(
        self,
        root: Path,
        record_path: str,
        candidate: str,
    ) -> str:
        """Write a real 'Integrator decision: ACCEPTED' record and commit it."""

        self._write_lifecycle_record(
            root,
            record_path,
            f"""# Amendment record

## Integrator decision

**Decision**: `ACCEPTED`

**Accepted candidate**: `{candidate}`

**Accepted by**: `v2-integrator`

**Decision reference**: `seed.txt`
""",
        )
        return self._commit_all(root, f"accept {record_path}")

    def test_effective_dependency_commit_resolves_through_accepted_amendment_chain(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            a1_candidate = self._next_git_commit(root, "a1")
            a1_decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", a1_candidate
            )
            a2_candidate = self._next_git_commit(root, "a2")
            a2_decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A2-test.md", a2_candidate
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{a1_candidate}`
**Amendment decision commit**: `{a1_decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`

## Amendment A2

**Slice**: `010-v2-contract`
**Amendment ID**: A2
**Status**: ACCEPTED
**Amended interface**: I-010B
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{a1_candidate}`
**Amendment candidate commit**: `{a2_candidate}`
**Amendment decision commit**: `{a2_decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A2-test.md`

## Current effective dependency commit

`{a2_candidate}`
""",
            )
            effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            binding, packet, binding_errors = (
                check_governance._effective_dependency_binding(
                    root, "010-v2-contract", base
                )
            )
            self.assertEqual(errors, [])
            self.assertEqual(effective, a2_candidate)
            self.assertEqual(binding_errors, [])
            self.assertEqual(binding, a2_candidate)
            self.assertEqual(
                packet, "evidence/v2/contract/amendment-A2-test.md"
            )

    def test_effective_dependency_commit_rejects_stale_summary_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            candidate = self._next_git_commit(root, "candidate")
            decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", candidate
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`

## Current effective dependency commit

`{base}`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(
                any(
                    "'Current effective dependency commit' summary must be"
                    in error
                    for error in errors
                )
            )

    def test_effective_dependency_commit_rejects_repeated_interface_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            a1_candidate = self._next_git_commit(root, "a1")
            a1_decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", a1_candidate
            )
            a2_candidate = self._next_git_commit(root, "a2")
            a2_decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A2-test.md", a2_candidate
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{a1_candidate}`
**Amendment decision commit**: `{a1_decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`

## Amendment A2

**Slice**: `010-v2-contract`
**Amendment ID**: A2
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{a1_candidate}`
**Amendment candidate commit**: `{a2_candidate}`
**Amendment decision commit**: `{a2_decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A2-test.md`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(
                any(
                    "Prior interface version for I-010E must be @2" in error
                    for error in errors
                )
            )

    def test_effective_dependency_commit_rejects_foreign_interface_amendment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            candidate = self._next_git_commit(root, "candidate")
            decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", candidate
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS[
                "010-v2-contract"
            ]["amendments"]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-020A
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(
                any("is not owned by 010-v2-contract" in error for error in errors)
            )

    def test_effective_dependency_commit_rejects_forged_decision_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            candidate = self._next_git_commit(root, "candidate")
            # An unrelated commit that never accepted this candidate.
            unrelated_decision = self._next_git_commit(root, "unrelated")
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{unrelated_decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `seed.txt`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(
                any("Amendment record must name an existing file" in error for error in errors)
            )

    def test_effective_dependency_commit_fails_closed_on_malformed_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(root, ledger, "not a lifecycle record\n")
            effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertEqual(effective, base)
            self.assertTrue(
                any("has no attested record" in error for error in errors)
            )

    def test_effective_dependency_commit_validates_last_summary_on_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            a1_candidate = self._next_git_commit(root, "a1")
            a1_decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", a1_candidate
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            # First candidate: only A1, with its own correct summary.
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{a1_candidate}`
**Amendment decision commit**: `{a1_decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`

## Current effective dependency commit

`{a1_candidate}`
""",
            )
            effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertEqual(errors, [])
            self.assertEqual(effective, a1_candidate)

            # Append-only extension: retain the A1 record and its summary
            # verbatim, then append A2 and a fresh summary below it.
            a2_candidate = self._next_git_commit(root, "a2")
            a2_decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A2-test.md", a2_candidate
            )
            existing = (root / ledger).read_text(encoding="utf-8")
            appended = existing.replace(
                f"## Current effective dependency commit\n\n`{a1_candidate}`\n",
                f"""## Amendment A2

**Slice**: `010-v2-contract`
**Amendment ID**: A2
**Status**: ACCEPTED
**Amended interface**: I-010B
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{a1_candidate}`
**Amendment candidate commit**: `{a2_candidate}`
**Amendment decision commit**: `{a2_decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A2-test.md`

## Current effective dependency commit

`{a2_candidate}`
""",
            )
            self._write_lifecycle_record(root, ledger, appended)
            effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertEqual(errors, [])
            self.assertEqual(effective, a2_candidate)

    def test_effective_dependency_commit_rejects_decision_reference_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            candidate = self._next_git_commit(root, "candidate")
            decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", candidate
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            # Ledger claims a different Decision reference than the one
            # actually recorded inside the amendment record at that commit.
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `evidence/v2/contract/amendment-A1-test.md`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(
                any(
                    "Decision reference at the decision commit must be" in error
                    for error in errors
                )
            )

    def test_effective_dependency_commit_rejects_decision_reference_absent_at_commit(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            candidate = self._next_git_commit(root, "candidate")
            # Write an amendment record whose Decision reference names a file
            # that does not yet exist at the decision commit itself.
            self._write_lifecycle_record(
                root,
                "evidence/v2/contract/amendment-A1-test.md",
                """# Amendment record

## Integrator decision

**Decision**: `ACCEPTED`

**Accepted candidate**: `%s`

**Accepted by**: `v2-integrator`

**Decision reference**: `evidence/v2/contract/does-not-exist-yet.md`
"""
                % candidate,
            )
            decision = self._commit_all(root, "accept without decision file")
            # The referenced file is created only afterwards -- too late to
            # prove it existed at the exact decision commit.
            self._write_lifecycle_record(
                root, "evidence/v2/contract/does-not-exist-yet.md", "late\n"
            )
            self._commit_all(root, "late decision file")
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `evidence/v2/contract/does-not-exist-yet.md`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(
                any(
                    "must name a file that already exists at the Amendment "
                    "decision commit" in error
                    for error in errors
                )
            )

    def test_effective_dependency_commit_rejects_broken_prior_effective_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            stray = self._next_git_commit(root, "stray")
            candidate = self._next_git_commit(root, "candidate")
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{stray}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{candidate}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `seed.txt`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(
                any("Prior effective commit must be" in error for error in errors)
            )

    def test_effective_dependency_commit_rejects_non_ancestor_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            later = self._next_git_commit(root, "later")
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            # "Prior effective commit" is a strict descendant of the claimed
            # "Amendment candidate commit" — candidate does not descend from it.
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{later}`
**Amendment candidate commit**: `{base}`
**Amendment decision commit**: `{base}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `seed.txt`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", later
            )
            self.assertTrue(
                any("must descend from" in error for error in errors)
            )

    def test_effective_dependency_commit_rejects_non_accepted_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            candidate = self._next_git_commit(root, "candidate")
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: REJECTED
**Amended interface**: I-010E
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{candidate}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `seed.txt`
""",
            )
            _effective, errors = check_governance._effective_dependency_commit(
                root, "010-v2-contract", base
            )
            self.assertTrue(any("Status must be 'ACCEPTED'" in error for error in errors))

    def test_dependency_activation_requires_amended_effective_commit(self):
        dirname = "030-v2-core-attention"
        expected = check_governance.EXPECTED_SLICES[dirname]
        paths = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname]
        assigned = "Codex — durable assignment decision 44"
        tasks = "- [ ] T001 Work\n"
        task_ids, task_hash = self._task_fields(tasks)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            amended = self._next_git_commit(root, "amended")
            decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", amended
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                "amendments"
            ]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1

**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010B
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{amended}`
**Amendment decision commit**: `{decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-19
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`
""",
            )
            self._write_lifecycle_record(
                root,
                check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                    "handoff"
                ],
                f"""# Upstream handoff
**Slice**: `010-v2-contract`
**Status**: HANDOFF_READY
**Candidate commit**: `{base}`
""",
            )
            self._write_lifecycle_record(
                root,
                check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                    "acceptance"
                ],
                f"""# Upstream acceptance
**Slice**: `010-v2-contract`
**Status**: ACCEPTED
**Candidate commit**: `{base}`
""",
            )

            def activation_with(
                dependency_commit: str,
                reference: str,
                packet_reference: str,
            ) -> str:
                self._write_lifecycle_record(
                    root,
                    reference,
                    f"""# Accepted dependency 010
**Consumer slice**: `{dirname}`
**Upstream slice**: `010-v2-contract`
**Candidate commit**: `{dependency_commit}`
**Accepted by**: Codex
**Accepted on**: 2026-07-19
**Packet reference**: `{packet_reference}`
**Decision reference**: durable dependency acceptance 44
""",
                )
                return f"""# Activation
**Slice**: `{dirname}`
**Status**: READY
**Assigned participant / source**: {assigned}
**Authority record**: `{check_governance.IMPLEMENTATION_AUTHORIZATION_PATH}`
**Accepted dependencies**: 010
**Dependency commits**: 010={dependency_commit}
**Dependency acceptance references**: 010={reference}
**Analysis result**: PASS — zero CRITICAL/HIGH findings
**Branch**: `{expected["branch"]}`
**Worktree**: `{expected["worktree"]}`
**Starting commit**: `{base}`
**Interfaces**: I-010B and I-030A
**Acceptance scenes**: S06 as planned
**Evidence targets**: evidence/v2/attention/results.json
**Documentation scope**: README.md and docs/attention.md
**Initial task IDs**: {task_ids}
**Initial tasks SHA256**: {task_hash}
"""

            reference = "evidence/v2/attention/dependency-010-acceptance.md"
            amendment_packet = "evidence/v2/contract/amendment-A1-test.md"

            # Binding to the pre-amendment terminal commit must now fail: it
            # would falsely consume the superseded interface version.
            self._write_lifecycle_record(
                root,
                paths["activation"],
                activation_with(base, reference, amendment_packet),
            )
            stale_errors = check_governance._slice_lifecycle_evidence_errors(
                root, dirname, expected, "READY", assigned, tasks
            )
            self.assertTrue(
                any(
                    "stale dependency 010" in error
                    or "Candidate commit must be" in error
                    for error in stale_errors
                )
            )

            # Binding to the exact accepted amendment candidate must pass.
            self._write_lifecycle_record(
                root,
                paths["activation"],
                activation_with(amended, reference, amendment_packet),
            )
            fresh_errors = check_governance._slice_lifecycle_evidence_errors(
                root, dirname, expected, "READY", assigned, tasks
            )
            self.assertEqual(fresh_errors, [])

            # A consumer cannot cite the terminal packet for an amended commit.
            self._write_lifecycle_record(
                root,
                paths["activation"],
                activation_with(
                    amended,
                    reference,
                    "evidence/v2/contract/slice-handoff.md",
                ),
            )
            wrong_packet_errors = (
                check_governance._slice_lifecycle_evidence_errors(
                    root, dirname, expected, "READY", assigned, tasks
                )
            )
            self.assertTrue(
                any(
                    "Packet reference must be "
                    "'evidence/v2/contract/amendment-A1-test.md'"
                    in error
                    for error in wrong_packet_errors
                )
            )

    def test_post_activation_successor_uses_append_only_compatibility_reattestation(
        self,
    ):
        dirname = "020-v2-observation"
        expected = check_governance.EXPECTED_SLICES[dirname]
        paths = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname]
        assigned = "Bob — durable assignment decision 45"
        tasks = "- [ ] T001 Work\n"
        task_ids, task_hash = self._task_fields(tasks)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_git_repo(root)
            tasks_path = root / "specs" / dirname / "tasks.md"
            tasks_path.parent.mkdir(parents=True, exist_ok=True)
            tasks_path.write_text(tasks, encoding="utf-8")
            terminal = self._commit_all(root, "terminal contract and consumer tasks")

            upstream_handoff = check_governance.EXPECTED_LIFECYCLE_PATHS[
                "010-v2-contract"
            ]["handoff"]
            upstream_acceptance = check_governance.EXPECTED_LIFECYCLE_PATHS[
                "010-v2-contract"
            ]["acceptance"]
            self._write_lifecycle_record(
                root,
                upstream_handoff,
                f"""# Handoff
**Slice**: `010-v2-contract`
**Status**: HANDOFF_READY
**Candidate commit**: `{terminal}`
""",
            )
            self._write_lifecycle_record(
                root,
                upstream_acceptance,
                f"""# Acceptance
**Slice**: `010-v2-contract`
**Status**: ACCEPTED
**Candidate commit**: `{terminal}`
""",
            )
            reference = "evidence/v2/observation/dependency-010-acceptance.md"
            initial_reference = f"""# Accepted dependency 010
**Consumer slice**: `{dirname}`
**Upstream slice**: `010-v2-contract`
**Candidate commit**: `{terminal}`
**Accepted by**: Bob
**Accepted on**: 2026-07-22
**Packet reference**: `{upstream_handoff}`
**Decision reference**: durable dependency acceptance 45
"""
            self._write_lifecycle_record(root, reference, initial_reference)
            activation = f"""# Activation
**Slice**: `{dirname}`
**Status**: READY
**Assigned participant / source**: {assigned}
**Authority record**: `{check_governance.IMPLEMENTATION_AUTHORIZATION_PATH}`
**Accepted dependencies**: 010
**Dependency commits**: 010={terminal}
**Dependency acceptance references**: 010={reference}
**Analysis result**: PASS — zero CRITICAL/HIGH findings
**Branch**: `{expected["branch"]}`
**Worktree**: `{expected["worktree"]}`
**Starting commit**: `{terminal}`
**Interfaces**: I-010A and I-020A
**Acceptance scenes**: S01-S16 as planned
**Evidence targets**: evidence/v2/observation/results.json
**Documentation scope**: README.md and docs/observation.md
**Initial task IDs**: {task_ids}
**Initial tasks SHA256**: {task_hash}
"""
            self._write_lifecycle_record(root, paths["activation"], activation)
            activation_commit = self._commit_all(root, "activate consumer")

            amended = self._next_git_commit(root, "amended contract")
            decision = self._accept_amendment_commit(
                root, "evidence/v2/contract/amendment-A1-test.md", amended
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS[
                "010-v2-contract"
            ]["amendments"]
            self._write_lifecycle_record(
                root,
                ledger,
                f"""## Amendment A1
**Slice**: `010-v2-contract`
**Amendment ID**: A1
**Status**: ACCEPTED
**Amended interface**: I-010B
**Prior interface version**: @1
**New interface version**: @2
**Prior effective commit**: `{terminal}`
**Amendment candidate commit**: `{amended}`
**Amendment decision commit**: `{decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-23
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A1-test.md`
""",
            )
            compatibility_evidence = (
                root / "evidence/v2/observation/dependency-010-compatibility.md"
            )
            compatibility_evidence.write_text("PASS\n", encoding="utf-8")
            (root / reference).write_text(
                initial_reference
                + f"""
## Successor re-attestation
**Consumer slice**: `{dirname}`
**Upstream slice**: `010-v2-contract`
**Candidate commit**: `{amended}`
**Accepted by**: Bob
**Accepted on**: 2026-07-23
**Packet reference**: `evidence/v2/contract/amendment-A1-test.md`
**Decision reference**: durable compatibility decision 45
**Prior accepted commit**: `{terminal}`
**Compatibility result**: PASS
**Affected candidate commit**: `{activation_commit}`
**Compatibility evidence**: `evidence/v2/observation/dependency-010-compatibility.md`
""",
                encoding="utf-8",
            )
            errors = check_governance._slice_lifecycle_evidence_errors(
                root, dirname, expected, "READY", assigned, tasks
            )
            self.assertEqual(errors, [])

    def test_program_state_is_derived_from_slice_and_cutover_evidence(self):
        planned = {name: "PLANNED" for name in check_governance.EXPECTED_SLICES}
        self.assertEqual(
            check_governance._derived_program_state(
                planned,
                planning_baseline_accepted=False,
                cutover_accepted=False,
                post_merge_verified=False,
            ),
            "PLANNING",
        )
        self.assertEqual(
            check_governance._derived_program_state(
                planned,
                planning_baseline_accepted=True,
                cutover_accepted=False,
                post_merge_verified=False,
            ),
            "READY",
        )
        delivery = dict(planned)
        delivery["010-v2-contract"] = "ACTIVE"
        self.assertEqual(
            check_governance._derived_program_state(
                delivery,
                planning_baseline_accepted=True,
                cutover_accepted=False,
                post_merge_verified=False,
            ),
            "DELIVERY",
        )
        integration = dict(delivery)
        integration["110-v2-parity-cutover"] = "ACTIVE"
        self.assertEqual(
            check_governance._derived_program_state(
                integration,
                planning_baseline_accepted=True,
                cutover_accepted=False,
                post_merge_verified=False,
            ),
            "INTEGRATION",
        )
        self.assertEqual(
            check_governance._derived_program_state(
                integration,
                planning_baseline_accepted=True,
                cutover_accepted=True,
                post_merge_verified=False,
            ),
            "CUTOVER_ACCEPTED",
        )
        self.assertEqual(
            check_governance._derived_program_state(
                integration,
                planning_baseline_accepted=True,
                cutover_accepted=True,
                post_merge_verified=True,
            ),
            "CUTOVER_VERIFIED",
        )

    def test_post_merge_verification_is_exact_main_ancestry_and_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accepted = self._init_git_repo(root)
            merged = self._next_git_commit(root, "atomic merge")
            main = self._next_git_commit(root, "verified main")
            result = root / "evidence" / "v2" / "parity" / "results.json"
            result.parent.mkdir(parents=True)
            result.write_text("{}\n", encoding="utf-8")
            documentation_commit = self._commit_all(root, "documentation follow-up")
            self._write_lifecycle_record(
                root,
                check_governance.CUTOVER_ACCEPTANCE_PATH.as_posix(),
                f"""# Cutover acceptance
**Program**: 001-nunchi-v2-program
**Status**: CUTOVER_ACCEPTED
**Candidate commit**: {accepted}
**Accepted by**: Zoe
**Accepted on**: 2026-07-12
**Decision reference**: durable exact candidate decision
**Recorded by**: v2-program-owner
""",
            )
            self._write_lifecycle_record(
                root,
                check_governance.POST_MERGE_VERIFICATION_PATH.as_posix(),
                f"""# Verification
**Program**: 001-nunchi-v2-program
**Status**: CUTOVER_VERIFIED
**Accepted candidate commit**: {accepted}
**Merged candidate commit**: {merged}
**Main ref**: refs/heads/main
**Main commit**: {main}
**Verified on**: 2026-07-12
**Verification commands / results**: PASS — python3 -m unittest
**Evidence paths**: evidence/v2/parity/results.json
**Documentation freshness**: PASS
**Documentation commit**: {documentation_commit}
""",
            )
            self.assertEqual(
                check_governance._cutover_evidence_errors(
                    root, final_state="ACCEPTED", accepted_candidate=accepted
                ),
                [],
            )
            verification = root / check_governance.POST_MERGE_VERIFICATION_PATH
            valid_verification = verification.read_text(encoding="utf-8")
            verification.write_text(
                valid_verification.replace(
                    "PASS — python3 -m unittest", "DO NOT PASS tests"
                ),
                encoding="utf-8",
            )
            errors = check_governance._cutover_evidence_errors(
                root, final_state="ACCEPTED", accepted_candidate=accepted
            )
            verification.write_text(
                valid_verification.replace(documentation_commit, accepted),
                encoding="utf-8",
            )
            chronology_errors = check_governance._cutover_evidence_errors(
                root, final_state="ACCEPTED", accepted_candidate=accepted
            )
        self.assertTrue(any("must start with 'PASS — '" in error for error in errors))
        self.assertTrue(
            any("docs/evidence-only follow-up" in error for error in chronology_errors)
        )

    def test_planning_baseline_requires_the_durable_acceptance_record(self):
        self.assertTrue(check_governance._planning_baseline_accepted(ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / check_governance.PLANNING_BASELINE_PATH
            path.parent.mkdir(parents=True)
            path.write_text(
                "# Similar-looking but incomplete record\n", encoding="utf-8"
            )
            self.assertFalse(check_governance._planning_baseline_accepted(root))

    def test_dependent_slice_cannot_start_before_upstream_acceptance(self):
        states = {name: "PLANNED" for name in check_governance.EXPECTED_SLICES}
        states["020-v2-observation"] = "READY"
        errors = check_governance._slice_dependency_state_errors(states)
        self.assertTrue(any("010-v2-contract" in error for error in errors))
        states["010-v2-contract"] = "HANDOFF_READY"
        errors = check_governance._slice_dependency_state_errors(states)
        self.assertTrue(
            any(
                "requires dependency 010-v2-contract to be ACCEPTED" in error
                for error in errors
            )
        )
        states["010-v2-contract"] = "ACCEPTED"
        self.assertEqual(check_governance._slice_dependency_state_errors(states), [])

    def test_completion_vocabulary_includes_freshness_and_authorization(self):
        self.assertEqual(
            set(check_governance.SCENE_ID.findall("S16 S17 S18 S19")),
            {"S16", "S17", "S18"},
        )
        self.assertEqual(
            check_governance.CANONICAL_INTERFACES["I-010F"],
            "010-v2-contract",
        )
        self.assertEqual(
            check_governance.CANONICAL_INTERFACES["I-040B"],
            "040-v2-participant-wake",
        )
        self.assertEqual(
            check_governance.CANONICAL_INTERFACES["I-040C"],
            "040-v2-participant-wake",
        )
        self.assertNotIn(
            "I-010F",
            check_governance.COMPLETION_PLAN_TERMS["020-v2-observation"],
        )
        self.assertNotIn(
            "030-v2-core-attention",
            check_governance.COMPLETION_PLAN_TERMS,
        )

    def test_i010f_stability_gate_blocks_started_downstream_slices(self):
        states = {name: "PLANNED" for name in check_governance.EXPECTED_SLICES}
        self.assertEqual(
            check_governance._i010f_stability_errors(states, set()), []
        )

        states["020-v2-observation"] = "READY"
        states["030-v2-core-attention"] = "ACTIVE"
        errors = check_governance._i010f_stability_errors(states, set())
        self.assertTrue(any("020-v2-observation: READY" in error for error in errors))
        self.assertTrue(any("030-v2-core-attention: ACTIVE" in error for error in errors))
        self.assertEqual(
            check_governance._i010f_stability_errors(states, {"I-010F"}),
            [],
        )

    def test_validated_amendment_interfaces_require_a_valid_accepted_a3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._init_git_repo(root)
            acceptance = check_governance.EXPECTED_LIFECYCLE_PATHS[
                "010-v2-contract"
            ]["acceptance"]
            self._write_lifecycle_record(
                root,
                acceptance,
                f"""# Terminal acceptance
**Slice**: `010-v2-contract`
**Status**: ACCEPTED
**Candidate commit**: `{base}`
""",
            )
            candidate = self._next_git_commit(root, "a3")
            decision = self._accept_amendment_commit(
                root,
                "evidence/v2/contract/amendment-A3-test.md",
                candidate,
            )
            ledger = check_governance.EXPECTED_LIFECYCLE_PATHS[
                "010-v2-contract"
            ]["amendments"]
            valid = f"""## Amendment A3

**Slice**: `010-v2-contract`
**Amendment ID**: A3
**Status**: ACCEPTED
**Amended interface**: I-010F
**Prior interface version**: @0
**New interface version**: @1
**Prior effective commit**: `{base}`
**Amendment candidate commit**: `{candidate}`
**Amendment decision commit**: `{decision}`
**Accepted by**: v2-integrator
**Accepted on**: 2026-07-23
**Decision reference**: `seed.txt`
**Amendment record**: `evidence/v2/contract/amendment-A3-test.md`
"""
            self._write_lifecycle_record(root, ledger, valid)
            self.assertEqual(
                check_governance._validated_accepted_amended_interfaces(
                    root, "010-v2-contract"
                ),
                {"I-010F"},
            )

            self._write_lifecycle_record(
                root,
                ledger,
                valid.replace("**Status**: ACCEPTED", "**Status**: REJECTED"),
            )
            self.assertEqual(
                check_governance._validated_accepted_amended_interfaces(
                    root, "010-v2-contract"
                ),
                set(),
            )

    def test_open_a3_must_bind_owner_scope_and_appended_task_manifest(self):
        dirname = "010-v2-contract"
        expected = check_governance.EXPECTED_SLICES[dirname]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            terminal = self._init_git_repo(root)
            tasks_path = root / "specs" / dirname / "tasks.md"
            tasks_path.parent.mkdir(parents=True, exist_ok=True)
            accepted_tasks = "- [X] T001 Accepted work\n"
            tasks_path.write_text(accepted_tasks, encoding="utf-8")
            assignment = (
                root
                / "evidence/governance/assignments/alice-v2-contract-owner.md"
            )
            assignment.parent.mkdir(parents=True, exist_ok=True)
            assignment.write_text(
                """# Assignment
**Assignee**: Alice
**Lane**: v2-contract-owner
**Assigned by**: Zoe
**Assigned on**: 2026-07-23
**Authority reference**: durable Zoe assignment for A3
""",
                encoding="utf-8",
            )
            starting = self._commit_all(root, "prepare amendment")
            amendment_task = "- [ ] T002 Implement I-010F\n"
            tasks_path.write_text(
                accepted_tasks + amendment_task,
                encoding="utf-8",
            )
            amendment_entries = check_governance._task_entries(amendment_task)
            task_ids, task_hash = check_governance._task_manifest(
                amendment_entries
            )
            record_relative = Path(
                "evidence/v2/contract/"
                "amendment-A3-privileged-action-authorization.md"
            )
            record = root / record_relative
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(
                f"""# A3
**Slice**: `{dirname}`
**Amendment ID**: A3
**Amended interface**: I-010F
**Prior interface version**: @0
**New interface version**: @1
**Prior effective commit**: `{terminal}`
**Prior effective packet**: `evidence/v2/contract/slice-handoff.md`
**Starting commit**: `{starting}`
**Owner lane**: v2-contract-owner
**Assigned participant / source**: Alice — evidence/governance/assignments/alice-v2-contract-owner.md
**Fixed scope paths**: `specs/010-v2-contract/spec.md`, `specs/010-v2-contract/plan.md`, `specs/010-v2-contract/tasks.md`, `evidence/v2/contract/amendment-A3-privileged-action-authorization.md`
**Amendment task IDs**: {task_ids}
**Amendment tasks SHA256**: {task_hash}
**Analysis result**: PASS — zero CRITICAL/HIGH findings
**Branch**: v2/contract-a3
**Worktree**: .worktrees/v2-contract-a3/
**Amendment phase**: READY
""",
                encoding="utf-8",
            )
            errors, open_amendment = (
                check_governance._accepted_amendment_attempt_errors(
                    root,
                    dirname,
                    expected,
                    tasks_path.read_text(),
                    terminal,
                    "Alice — evidence/governance/assignments/"
                    "alice-v2-contract-owner.md",
                )
            )
            self.assertEqual(errors, [])
            self.assertTrue(open_amendment)

            replacement = self._write_assignment(
                root, "Bob", "v2-contract-owner", "bob-v2-contract-owner"
            )
            errors, open_amendment = (
                check_governance._accepted_amendment_attempt_errors(
                    root,
                    dirname,
                    expected,
                    tasks_path.read_text(),
                    terminal,
                    replacement,
                )
            )
            self.assertFalse(open_amendment)
            self.assertTrue(
                any(
                    "must be the current slice assignment" in error
                    for error in errors
                )
            )

            record.write_text(
                record.read_text(encoding="utf-8").replace(
                    "**Amended interface**: I-010F",
                    "**Amended interface**: I-020A",
                ),
                encoding="utf-8",
            )
            errors, open_amendment = (
                check_governance._accepted_amendment_attempt_errors(
                    root,
                    dirname,
                    expected,
                    tasks_path.read_text(),
                    terminal,
                    "Alice — evidence/governance/assignments/"
                    "alice-v2-contract-owner.md",
                )
            )
            self.assertFalse(open_amendment)
            self.assertTrue(
                any("Amended interface must be owned" in error for error in errors)
            )

    def test_final_slice_requires_accepted_dependencies(self):
        states = {name: "ACCEPTED" for name in check_governance.EXPECTED_SLICES}
        states["110-v2-parity-cutover"] = "READY"
        states["010-v2-contract"] = "HANDOFF_READY"
        errors = check_governance._slice_dependency_state_errors(states)
        self.assertTrue(
            any(
                "requires dependency 010-v2-contract to be ACCEPTED" in error
                for error in errors
            )
        )

    def test_terminal_decision_requires_early_integrator_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acceptance = Path(
                check_governance.EXPECTED_LIFECYCLE_PATHS["010-v2-contract"][
                    "acceptance"
                ]
            )
            path = root / acceptance
            path.parent.mkdir(parents=True)
            path.write_text("**Status**: ACCEPTED\n", encoding="utf-8")

            errors = check_governance._terminal_integrator_assignment_errors(
                root, "UNASSIGNED — awaiting assignment"
            )
            assigned_errors = check_governance._terminal_integrator_assignment_errors(
                root,
                "Iris — evidence/governance/assignments/integrator.md",
            )

        self.assertTrue(any("v2-integrator" in error for error in errors))
        self.assertEqual(assigned_errors, [])

    def test_central_mutable_slice_registry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = (
                root
                / "evidence"
                / "v2"
                / "administration"
                / "slice-status-registry.json"
            )
            registry.parent.mkdir(parents=True)
            registry.write_text("{}", encoding="utf-8")
            errors = check_governance.check_central_state_artifacts(root)
        self.assertTrue(any("central mutable" in error for error in errors))

    def test_neutrally_named_aggregate_slice_state_table_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "evidence" / "v2" / "administration" / "current.md"
            current.parent.mkdir(parents=True)
            current.write_text(
                "| Slice | Current state | Assigned participant |\n"
                "|---|---|---|\n"
                "| 010 | ACTIVE | Alice |\n"
                "| 020 | PLANNED | UNASSIGNED |\n",
                encoding="utf-8",
            )
            errors = check_governance.check_central_state_artifacts(root)
        self.assertTrue(any("aggregate per-slice" in error for error in errors))

    def test_neutral_slice_state_lines_are_rejected_but_parity_results_are_allowed(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            administration = root / "evidence" / "v2" / "administration"
            administration.mkdir(parents=True)
            current = administration / "current.md"
            current.write_text(
                "010: ACTIVE — Alice\n020: PLANNED — UNASSIGNED\n",
                encoding="utf-8",
            )
            parity = root / "evidence" / "v2" / "parity" / "results.json"
            parity.parent.mkdir(parents=True)
            parity.write_text(
                json.dumps({"status": "PASS", "slices": ["010", "020"]}),
                encoding="utf-8",
            )

            errors = check_governance.check_central_state_artifacts(root)

        self.assertTrue(any("current.md" in error for error in errors))
        self.assertFalse(any("results.json" in error for error in errors))

    def _stage_synthetic_active_contract_baseline(
        self, source_root: Path, root: Path
    ) -> dict[str, str]:
        """Construct the synthetic ACTIVE-slice-010 planning baseline at
        ``root`` from ``source_root``'s planning tree.

        Rejection R1 invariant: the staged baseline is independent of the
        source repository's live slice state. Every copied slice
        declaration is replaced with the synthetic state — not only
        ``PLANNED`` ones — and any lifecycle record staged under the
        synthetic evidence paths is removed before the one synthetic
        activation record is written.
        """
        shutil.copytree(source_root / "specs", root / "specs")
        # Real slice declarations may reference durable assignment records;
        # the synthetic repo must carry them or every declaration dangles.
        assignments = source_root / "evidence" / "governance" / "assignments"
        if assignments.is_dir():
            shutil.copytree(
                assignments, root / "evidence" / "governance" / "assignments"
            )
        ownership = source_root / check_governance.OWNERSHIP_SUPERSESSION_PATH
        if ownership.is_file():
            target = root / check_governance.OWNERSHIP_SUPERSESSION_PATH
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ownership, target)
        self._write_valid_implementation_authorization(root)

        for dirname in check_governance.EXPECTED_SLICES:
            for artifact in ("spec.md", "plan.md", "tasks.md"):
                path = root / "specs" / dirname / artifact
                text = path.read_text(encoding="utf-8")
                text = re.sub(
                    r"(\*\*Slice state\*\*: )`?[A-Z_]+`?",
                    r"\1`PLANNED`",
                    text,
                    count=1,
                )
                text = re.sub(
                    r"(\*\*Program implementation authority\*\*: )`?[A-Z_]+`?",
                    r"\1`GRANTED`",
                    text,
                    count=1,
                )
                path.write_text(text, encoding="utf-8")
        # No live lifecycle record may survive into the synthetic
        # baseline; only the activation record written below exists.
        for lifecycle_paths in check_governance.EXPECTED_LIFECYCLE_PATHS.values():
            for relative in lifecycle_paths.values():
                staged = root / relative
                if staged.exists():
                    staged.unlink()

        dirname = "010-v2-contract"
        assigned = check_governance._clean_metadata(
            (root / "specs" / dirname / "spec.md").read_text(encoding="utf-8"),
            "Assigned participant / source",
        )
        for artifact in ("spec.md", "plan.md", "tasks.md"):
            path = root / "specs" / dirname / artifact
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "**Slice state**: `PLANNED`", "**Slice state**: `ACTIVE`", 1
            )
            text = re.sub(
                r"(\*\*Assigned participant / source\*\*:).*?(?=\n\n\*\*)",
                rf"\1 {assigned}",
                text,
                count=1,
                flags=re.DOTALL,
            )
            path.write_text(text, encoding="utf-8")

        umbrella = root / "specs" / "001-nunchi-v2-program"
        program_assignment = check_governance._clean_metadata(
            (umbrella / "spec.md").read_text(encoding="utf-8"),
            "Assigned program participant / source (declaration)",
        )
        for artifact in ("spec.md", "plan.md", "tasks.md"):
            path = umbrella / artifact
            text = path.read_text(encoding="utf-8")
            text = re.sub(
                r"(\*\*Program implementation authority\*\*: )`?[A-Z_]+`?",
                r"\1`GRANTED`",
                text,
                count=1,
            )
            text = re.sub(
                r"(\*\*Program state\*\*: )`?[A-Z_]+`?",
                r"\1`DELIVERY`",
                text,
                count=1,
            )
            text = re.sub(
                r"(\*\*Assigned program participant / source \(declaration\)\*\*:).*?(?=\n\n\*\*)",
                rf"\1 {program_assignment}",
                text,
                count=1,
                flags=re.DOTALL,
            )
            path.write_text(text, encoding="utf-8")

        expected = check_governance.EXPECTED_SLICES[dirname]
        activation = check_governance.EXPECTED_LIFECYCLE_PATHS[dirname][
            "activation"
        ]
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        task_text = (root / "specs" / dirname / "tasks.md").read_text(
            encoding="utf-8"
        )
        task_ids, task_hash = self._task_fields(task_text)
        plan_text = (root / "specs" / dirname / "plan.md").read_text(
            encoding="utf-8"
        )
        interfaces = ", ".join(
            sorted(set(check_governance.INTERFACE_ID.findall(plan_text)))
        )
        scenes = ", ".join(
            sorted(set(check_governance.SCENE_ID.findall(plan_text)))
        )
        evidence_target = "evidence/v2/contract/attention-request.jsonl"
        documentation_scope = ", ".join(
            sorted(check_governance.EXPECTED_DOCUMENTATION_PATHS[dirname])
        )
        self._write_lifecycle_record(
            root,
            activation,
            f"""# Activation
**Slice**: `{dirname}`
**Status**: READY
**Assigned participant / source**: {assigned}
**Authority record**: `{check_governance.IMPLEMENTATION_AUTHORIZATION_PATH}`
**Accepted dependencies**: none
**Dependency commits**: none
**Dependency acceptance references**: none
**Analysis result**: PASS — zero CRITICAL/HIGH findings
**Branch**: `{expected["branch"]}`
**Worktree**: `{expected["worktree"]}`
**Starting commit**: `{sha}`
**Interfaces**: {interfaces}
**Acceptance scenes**: {scenes}
**Evidence targets**: {evidence_target}
**Documentation scope**: {documentation_scope}
**Initial task IDs**: {task_ids}
**Initial tasks SHA256**: {task_hash}
""",
        )
        return {"assigned": assigned, "program_assignment": program_assignment}

    def test_authorized_contract_slice_can_reach_active_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staged = self._stage_synthetic_active_contract_baseline(ROOT, root)
            errors = check_governance.check_program(root)
            self.assertEqual(errors, [])

            umbrella = root / "specs" / "001-nunchi-v2-program"
            program_assignment = staged["program_assignment"]
            for artifact in ("spec.md", "plan.md", "tasks.md"):
                path = umbrella / artifact
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        f"**Assigned program participant / source (declaration)**: {program_assignment}",
                        "**Assigned program participant / source (declaration)**:",
                        1,
                    ),
                    encoding="utf-8",
                )
            errors = check_governance.check_program(root)
        self.assertTrue(any("active delivery requires" in error for error in errors))

    def test_activation_fixture_is_independent_of_live_slice_state(self):
        # Rejection R1 / CHK095 regression proof: the synthetic activation
        # baseline stays green while the source tree's live slice
        # declarations read ACTIVE or HANDOFF_READY. The rejected packet
        # commit failed exactly here — the fixture replaced only PLANNED
        # declarations, so live HANDOFF_READY records leaked into a
        # contradictory synthetic baseline.
        for live_state in ("ACTIVE", "HANDOFF_READY"):
            with self.subTest(live_state=live_state):
                with tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    source = base / "source"
                    source.mkdir()
                    shutil.copytree(ROOT / "specs", source / "specs")
                    assignments = ROOT / "evidence" / "governance" / "assignments"
                    if assignments.is_dir():
                        shutil.copytree(
                            assignments,
                            source / "evidence" / "governance" / "assignments",
                        )
                    ownership = ROOT / check_governance.OWNERSHIP_SUPERSESSION_PATH
                    ownership_target = (
                        source / check_governance.OWNERSHIP_SUPERSESSION_PATH
                    )
                    ownership_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ownership, ownership_target)
                    for dirname in check_governance.EXPECTED_SLICES:
                        for artifact in ("spec.md", "plan.md", "tasks.md"):
                            path = source / "specs" / dirname / artifact
                            text = path.read_text(encoding="utf-8")
                            text = re.sub(
                                r"(\*\*Slice state\*\*: )`?[A-Z_]+`?",
                                rf"\1`{live_state}`",
                                text,
                                count=1,
                            )
                            path.write_text(text, encoding="utf-8")
                    # A live tree carries lifecycle attempt records too;
                    # none of them may leak into the synthetic baseline.
                    for lifecycle_paths in (
                        check_governance.EXPECTED_LIFECYCLE_PATHS.values()
                    ):
                        for relative in lifecycle_paths.values():
                            record = source / relative
                            record.parent.mkdir(parents=True, exist_ok=True)
                            record.write_text(
                                "# Live lifecycle record\n"
                                f"**Status**: {live_state}\n",
                                encoding="utf-8",
                            )
                    root = base / "staged"
                    self._stage_synthetic_active_contract_baseline(source, root)
                    errors = check_governance.check_program(root)
                    self.assertEqual(errors, [])

    @staticmethod
    def _write_valid_implementation_authorization(root: Path) -> Path:
        starting_commit = check_governance._git_ref_commit(root, "HEAD")
        if starting_commit is None:
            starting_commit = GovernanceBoundaryTests._init_git_repo(root)
        path = root / check_governance.IMPLEMENTATION_AUTHORIZATION_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        slices = ", ".join(
            f"`{dirname[:3]}`" for dirname in check_governance.EXPECTED_SLICES
        )
        path.write_text(
            "# Nunchi V2 Implementation Authorization\n\n"
            "**Program**: `001-nunchi-v2-program`\n\n"
            "**Status**: AUTHORIZED\n\n"
            f"**Authorized slices**: {slices}\n\n"
            "**Authorized by**: Zoe\n\n"
            "**Authorized on**: 2026-07-12\n\n"
            f"**Starting commit**: `{starting_commit}`\n\n"
            "**Commissioned objective**: Implement and validate the complete atomic "
            "Nunchi V2 lifecycle across every independently owned slice.\n\n"
            "**Authority reference**: Zoe's durable program-implementation commission.\n\n"
            "**Recorded by**: v2-program-owner\n\n"
            "This record documents externally granted implementation authority; it "
            "does not grant it and does not authorize cutover, release, or promotion.\n",
            encoding="utf-8",
        )
        return path

    def test_implementation_authorization_record_is_external_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_valid_implementation_authorization(root)
            authorized, errors = check_governance._implementation_authorization_state(
                root
            )
        self.assertTrue(authorized)
        self.assertEqual(errors, [])

    def test_implementation_authorization_requires_recorded_by(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write_valid_implementation_authorization(root)
            text = path.read_text(encoding="utf-8").replace(
                "**Recorded by**: v2-program-owner\n\n", ""
            )
            path.write_text(text, encoding="utf-8")
            authorized, errors = check_governance._implementation_authorization_state(
                root
            )
        self.assertFalse(authorized)
        self.assertTrue(any("Recorded by" in error for error in errors))

    def test_implementation_authorization_rejects_duplicate_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write_valid_implementation_authorization(root)
            text = path.read_text(encoding="utf-8")
            path.write_text(text + "\n**Status**: AUTHORIZED\n", encoding="utf-8")
            authorized, errors = check_governance._implementation_authorization_state(
                root
            )
        self.assertFalse(authorized)
        self.assertTrue(
            any("Status must occur exactly once" in error for error in errors)
        )

    def test_assignment_record_requires_zoe_or_durable_delegate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            declaration = self._write_assignment(
                root, "Alice", "v2-contract-owner", "contract-owner"
            )
            self.assertEqual(
                check_governance._assignment_errors(
                    root, declaration, "v2-contract-owner", "slice 010"
                ),
                [],
            )
            record = root / declaration.split(" — ", 1)[1]
            record.write_text(
                record.read_text(encoding="utf-8").replace(
                    "**Assigned by**: Zoe", "**Assigned by**: Mallory"
                ),
                encoding="utf-8",
            )
            errors = check_governance._assignment_errors(
                root, declaration, "v2-contract-owner", "slice 010"
            )
        self.assertTrue(any("Delegated by" in error for error in errors))

    def test_current_assignment_may_supersede_immutable_lifecycle_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_git_repo(root)
            historical = self._write_assignment(
                root, "Alice", "v2-contract-owner", "alice-contract-owner"
            )
            activation_relative = Path(
                "evidence/v2/contract/slice-activation.md"
            )
            activation = root / activation_relative
            activation.parent.mkdir(parents=True, exist_ok=True)
            activation.write_text("# Historical activation\n", encoding="utf-8")
            self._commit_all(root, "historical activation")

            current = self._write_assignment(
                root, "Codex", "v2-contract-owner", "codex-contract-owner"
            )
            current_record = root / current.split(" — ", 1)[1]
            historical_reference = historical.split(" — ", 1)[1]
            current_record.write_text(
                current_record.read_text(encoding="utf-8")
                + f"**Supersedes assignment**: {historical_reference}\n",
                encoding="utf-8",
            )
            self._commit_all(root, "current assignment")

            self.assertEqual(
                check_governance._assignment_supersession_errors(
                    root,
                    current,
                    historical,
                    "v2-contract-owner",
                    activation_relative,
                ),
                [],
            )

            future_relative = Path("evidence/v2/observation/slice-activation.md")
            future = root / future_relative
            future.parent.mkdir(parents=True, exist_ok=True)
            future.write_text("# Future activation\n", encoding="utf-8")
            self._commit_all(root, "future activation")
            future_errors = check_governance._assignment_supersession_errors(
                root,
                current,
                historical,
                "v2-contract-owner",
                future_relative,
            )
            self.assertTrue(
                any(
                    "committed before the current assignment" in error
                    for error in future_errors
                )
            )

            current_record.write_text(
                current_record.read_text(encoding="utf-8").replace(
                    historical_reference,
                    "evidence/governance/assignments/unrelated.md",
                ),
                encoding="utf-8",
            )
            errors = check_governance._assignment_supersession_errors(
                root,
                current,
                historical,
                "v2-contract-owner",
                activation_relative,
            )
            unassigned_errors = check_governance._assignment_supersession_errors(
                root,
                "UNASSIGNED — awaiting assignment",
                historical,
                "v2-contract-owner",
                activation_relative,
            )
        self.assertTrue(
            any("must supersede immutable lifecycle" in error for error in errors)
        )
        self.assertTrue(
            any("requires two named durable" in error for error in unassigned_errors)
        )

    def test_exact_zoe_ownership_mapping_rejects_fabricated_current_owner(self):
        self.assertEqual(
            check_governance.check_ownership_supersession(ROOT),
            [],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "specs", root / "specs")
            governance = root / "evidence" / "governance"
            governance.mkdir(parents=True)
            shutil.copytree(
                ROOT / "evidence" / "governance" / "assignments",
                governance / "assignments",
            )
            shutil.copy2(
                ROOT / check_governance.OWNERSHIP_SUPERSESSION_PATH,
                root / check_governance.OWNERSHIP_SUPERSESSION_PATH,
            )
            authority = root / check_governance.OWNERSHIP_SUPERSESSION_PATH
            authority.write_bytes(
                authority.read_bytes().replace(b"\n", b"\r\n")
            )
            self.assertEqual(
                check_governance.check_ownership_supersession(root),
                [],
            )

            observation_assignment = (
                governance
                / "assignments"
                / "codex-v2-observation-owner-2026-07-23.md"
            )
            original_assignment = observation_assignment.read_text(encoding="utf-8")
            expected_predecessor = (
                check_governance.OWNERSHIP_EXPECTED_PREDECESSORS["020"]
            )
            observation_assignment.write_text(
                original_assignment.replace(
                    expected_predecessor,
                    "evidence/governance/assignments/unrelated.md",
                ),
                encoding="utf-8",
            )
            lineage_errors = check_governance.check_ownership_supersession(root)
            self.assertTrue(
                any(
                    "Supersedes assignment must be" in error
                    for error in lineage_errors
                )
            )
            observation_assignment.write_text(
                original_assignment, encoding="utf-8"
            )
            observation_assignment.write_text(
                original_assignment.replace(
                    "**Authority reference**: evidence/governance/"
                    "v2-end-to-end-ownership-supersession-2026-07-23.md "
                    "— Codex task 019f8ff1-46c7-7c60-b427-47bf82e06d7c",
                    "**Authority reference**: fabricated durable authority",
                ),
                encoding="utf-8",
            )
            authority_errors = check_governance.check_ownership_supersession(root)
            self.assertTrue(
                any(
                    "exact Zoe assignment digest" in error
                    for error in authority_errors
                )
            )
            observation_assignment.write_text(
                original_assignment, encoding="utf-8"
            )
            observation_assignment.write_bytes(
                original_assignment.encode("utf-8") + b"\xff"
            )
            malformed_errors = (
                check_governance.check_ownership_supersession(root)
            )
            self.assertTrue(
                any(
                    "assignment record is unreadable" in error
                    for error in malformed_errors
                )
            )
            observation_assignment.write_text(
                original_assignment, encoding="utf-8"
            )

            forged = self._write_assignment(
                root, "Mallory", "v2-observation-owner", "mallory-observation-owner"
            )
            expected = (
                "Codex — evidence/governance/assignments/"
                "codex-v2-observation-owner-2026-07-23.md"
            )
            for artifact in ("spec.md", "plan.md", "tasks.md"):
                path = root / "specs" / "020-v2-observation" / artifact
                path.write_text(
                    path.read_text(encoding="utf-8").replace(expected, forged),
                    encoding="utf-8",
                )
            errors = check_governance.check_ownership_supersession(root)
            program_errors = check_governance.check_program(root)
        self.assertTrue(
            any("Zoe ownership decision requires" in error for error in errors)
        )
        self.assertTrue(
            any(
                "Zoe ownership decision requires" in error
                for error in program_errors
            )
        )

    def test_every_current_v2_owner_is_session_agnostic_codex(self):
        expected_slice_ids = tuple(
            dirname[:3] for dirname in check_governance.EXPECTED_SLICES
        )
        self.assertEqual(
            check_governance.OWNERSHIP_CURRENT_SLICES,
            expected_slice_ids,
        )
        self.assertEqual(check_governance.OWNERSHIP_RETAINED_SLICES, ())
        self.assertEqual(
            set(check_governance.OWNERSHIP_EXPECTED_IDENTITIES.values()),
            {"Codex"},
        )

        authority = (
            ROOT / check_governance.OWNERSHIP_SUPERSESSION_PATH
        ).read_text(encoding="utf-8")
        self.assertIn(
            "`Codex` is a stable, session-agnostic participant identity",
            authority,
        )
        self.assertIn(
            "Codex session turnover does not require\nreassignment",
            authority,
        )

        for dirname in check_governance.EXPECTED_SLICES:
            for artifact in ("spec.md", "plan.md", "tasks.md"):
                text = (
                    ROOT / "specs" / dirname / artifact
                ).read_text(encoding="utf-8")
                declaration = check_governance._clean_metadata(
                    text, "Assigned participant / source"
                )
                self.assertTrue(
                    declaration.startswith("Codex — "),
                    f"{dirname}/{artifact}: {declaration}",
                )

        expected_program = (
            f"Codex — "
            f"{check_governance.OWNERSHIP_PROGRAM_ASSIGNMENT_PATH.as_posix()}"
        )
        for artifact in ("spec.md", "plan.md", "tasks.md"):
            text = (
                ROOT / "specs/001-nunchi-v2-program" / artifact
            ).read_text(encoding="utf-8")
            self.assertEqual(
                check_governance._clean_metadata(
                    text,
                    "Assigned program participant / source (declaration)",
                ),
                expected_program,
            )

    def test_implementation_authorization_rejects_incomplete_slice_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write_valid_implementation_authorization(root)
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(", `110`", ""), encoding="utf-8")
            authorized, errors = check_governance._implementation_authorization_state(
                root
            )
        self.assertFalse(authorized)
        self.assertTrue(any("Authorized slices" in error for error in errors))

    def test_implementation_authorization_rejects_extra_or_duplicate_slice_scope(self):
        for suffix in (", `110`", ", `999`"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = self._write_valid_implementation_authorization(root)
                text = path.read_text(encoding="utf-8")
                path.write_text(
                    text.replace(
                        "`110`\n\n**Authorized by**: Zoe",
                        f"`110`{suffix}\n\n**Authorized by**: Zoe",
                    ),
                    encoding="utf-8",
                )
                authorized, errors = (
                    check_governance._implementation_authorization_state(root)
                )
            self.assertFalse(authorized)
            self.assertTrue(any("Authorized slices" in error for error in errors))

    def test_active_execution_language_rejects_numbered_goal_terms(self):
        checker = getattr(check_governance, "check_active_execution_language", None)
        if checker is None:
            self.skipTest("active execution language checker not exposed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents = root / "AGENTS.md"
            agents.write_text("Implementation starts under Goal 2.\n", encoding="utf-8")
            errors = checker(root)
        self.assertTrue(any("Goal 2" in error for error in errors))

    def test_active_execution_language_ignores_historical_evidence(self):
        checker = getattr(check_governance, "check_active_execution_language", None)
        if checker is None:
            self.skipTest("active execution language checker not exposed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            historical = (
                root / "evidence" / "governance" / "v2-execution-spine-2026-07-11.md"
            )
            historical.parent.mkdir(parents=True)
            historical.write_text(
                "Historical Goal 1 and Goal 2 record.\n",
                encoding="utf-8",
            )
            errors = checker(root)
        self.assertEqual(errors, [])

    def test_historical_governance_evidence_rewrite_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in check_governance.HISTORICAL_EVIDENCE_HASHES:
                historical = root / relative
                historical.parent.mkdir(parents=True, exist_ok=True)
                historical.write_bytes((ROOT / relative).read_bytes())
            rewritten = next(iter(check_governance.HISTORICAL_EVIDENCE_HASHES))
            (root / rewritten).write_text(
                "rewritten observation\n", encoding="utf-8"
            )
            errors = check_governance.check_historical_evidence(root)
        self.assertTrue(
            any("immutable historical evidence changed" in error for error in errors)
        )

    def test_historical_governance_evidence_hash_is_eol_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in check_governance.HISTORICAL_EVIDENCE_HASHES:
                historical = root / relative
                historical.parent.mkdir(parents=True, exist_ok=True)
                source = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
                historical.write_bytes(source.replace(b"\n", b"\r\n"))
            errors = check_governance.check_historical_evidence(root)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
