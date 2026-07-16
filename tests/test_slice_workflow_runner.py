"""Tests for the exact-slice SpecKit workflow wrapper."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_slice_workflow as runner


SLICE = "specs/010-v2-contract"
WORKFLOW = "nunchi-plan"
WORKFLOW_VERSION = "1.4.0"
TIMESTAMP = "2026-07-11T12:00:00+00:00"


class SliceWorkflowRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.feature_state = self.root / ".specify" / "feature.json"
        self.feature_state.parent.mkdir(parents=True)
        self.feature_state.write_text('{"feature":"unchanged"}\n', encoding="utf-8")
        self.original_feature_state = self.feature_state.read_bytes()
        self._write_json(
            self.root / ".specify" / "integration.json",
            {
                "version": "0.12.11",
                "installed_integrations": ["codex", "claude"],
                "default_integration": "codex",
            },
        )
        self.integration_files: dict[str, Path] = {}
        for integration, prefix in (
            ("codex", ".agents"),
            ("claude", ".claude"),
        ):
            files: dict[str, str] = {}
            for skill_name in sorted(runner.EXPECTED_INTEGRATION_SKILLS):
                skill = self.root / prefix / "skills" / skill_name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(
                    f"# {integration} {skill_name} test integration\n",
                    encoding="utf-8",
                )
                relative = skill.relative_to(self.root).as_posix()
                files[relative] = runner._sha256(skill)
                if skill_name == "speckit-plan":
                    self.integration_files[integration] = skill
            self._write_json(
                self.root
                / ".specify"
                / "integrations"
                / f"{integration}.manifest.json",
                {
                    "integration": integration,
                    "version": "0.12.11",
                    "installed_at": TIMESTAMP,
                    "files": files,
                },
            )
        self._write_workflow()
        tasks = self.root / SLICE / "tasks.md"
        tasks.parent.mkdir(parents=True)
        tasks.write_text("- [ ] T001 Test task\n", encoding="utf-8")
        self.binding_patch = mock.patch.object(
            runner,
            "verify_slice_binding",
            return_value={"SLICE_DIRECTORY": SLICE},
        )
        self.binding_patch.start()
        self.addCleanup(self.binding_patch.stop)
        self.cli_patch = mock.patch.object(
            runner,
            "_governance_check_cli",
            return_value=[],
        )
        self.cli_patch.start()
        self.addCleanup(self.cli_patch.stop)

    def _workflow_path(self) -> Path:
        return self.root / ".specify" / "workflows" / WORKFLOW / "workflow.yml"

    def _write_workflow(self, *, suffix: str = "") -> None:
        workflow = self._workflow_path()
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            'schema_version: "1.0"\n'
            "workflow:\n"
            f'  id: "{WORKFLOW}"\n'
            '  name: "Test existing-slice workflow"\n'
            f'  version: "{WORKFLOW_VERSION}"\n'
            "inputs:\n"
            "  slice_directory:\n"
            "    type: string\n"
            "steps: []\n"
            f"{suffix}",
            encoding="utf-8",
        )

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _materialize_specify_run(
        self,
        run_id: str,
        *,
        status: str = "paused",
    ) -> None:
        run_directory = runner._run_directory(self.root, run_id)
        (run_directory / "workflow.yml").write_bytes(self._workflow_path().read_bytes())
        self._write_json(
            run_directory / "inputs.json",
            {
                "inputs": {
                    "slice_directory": SLICE,
                    "integration": "codex",
                }
            },
        )
        self._write_json(
            run_directory / "state.json",
            {
                "run_id": run_id,
                "workflow_id": WORKFLOW,
                "status": status,
                "current_step_index": 1,
                "current_step_id": "review-spec",
                "step_results": {},
                "created_at": TIMESTAMP,
                "updated_at": TIMESTAMP,
            },
        )

    def _create_finalized_run(self, *, run_id: str = "bound-run") -> str:
        runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            run_id=run_id,
        )
        self._materialize_specify_run(run_id)
        runner.finalize_run_binding(self.root, run_id)
        return run_id

    def test_start_and_resume_are_exactly_bound_and_self_validating(self) -> None:
        observed_commands: list[list[str]] = []

        def initial_invocation(
            root: Path,
            command: list[str],
            environment: dict[str, str],
        ) -> int:
            self.assertEqual(root, self.root)
            self.assertEqual(environment["SPECIFY_FEATURE_DIRECTORY"], SLICE)
            run_id = environment["SPECKIT_WORKFLOW_RUN_ID"]
            self.assertRegex(
                run_id,
                rf"^{WORKFLOW}-010-\d{{8}}T\d{{12}}Z$",
            )
            observed_commands.append(command)
            self._materialize_specify_run(run_id)
            return 0

        with mock.patch.object(runner, "_invoke", side_effect=initial_invocation):
            run_id, return_code = runner.start_bound_run(
                self.root,
                WORKFLOW,
                SLICE,
            )

        self.assertEqual(return_code, 0)
        self.assertEqual(
            observed_commands,
            [
                [
                    "specify",
                    "workflow",
                    "run",
                    WORKFLOW,
                    "--input",
                    f"slice_directory={SLICE}",
                    "--input",
                    "integration=codex",
                    "--json",
                ]
            ],
        )
        self.assertEqual(self.feature_state.read_bytes(), self.original_feature_state)

        binding = runner.validate_resume(self.root, run_id)
        self.assertEqual(binding["slice_directory"], SLICE)
        self.assertEqual(binding["workflow"], WORKFLOW)
        self.assertEqual(binding["workflow_version"], WORKFLOW_VERSION)
        self.assertEqual(binding["integration"], "codex")
        self.assertRegex(
            str(binding["integration_manifest_sha256"]), r"^[0-9a-f]{64}$"
        )
        self.assertRegex(str(binding["workflow_sha256"]), r"^[0-9a-f]{64}$")
        self.assertRegex(str(binding["requested_inputs_sha256"]), r"^[0-9a-f]{64}$")
        self.assertRegex(str(binding["resolved_inputs_sha256"]), r"^[0-9a-f]{64}$")
        self.assertRegex(str(binding["tasks_file_sha256"]), r"^[0-9a-f]{64}$")

        def resume_invocation(
            root: Path,
            command: list[str],
            environment: dict[str, str],
        ) -> int:
            self.assertEqual(root, self.root)
            self.assertEqual(
                command,
                ["specify", "workflow", "resume", run_id, "--json"],
            )
            self.assertEqual(environment["SPECIFY_FEATURE_DIRECTORY"], SLICE)
            self.assertEqual(environment["SPECKIT_WORKFLOW_RUN_ID"], run_id)
            state_path = runner._run_directory(self.root, run_id) / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "completed"
            state["current_step_index"] = 2
            state["current_step_id"] = None
            state["updated_at"] = "2026-07-11T12:01:00+00:00"
            self._write_json(state_path, state)
            return 0

        with mock.patch.object(runner, "_invoke", side_effect=resume_invocation):
            self.assertEqual(runner.resume_bound_run(self.root, run_id), 0)

        refreshed = runner._validate_bound_run(
            self.root,
            run_id,
            require_resumable=False,
        )
        self.assertEqual(refreshed["state_status"], "completed")
        with self.assertRaisesRegex(ValueError, "cannot resume"):
            runner.validate_resume(self.root, run_id)
        self.assertEqual(self.feature_state.read_bytes(), self.original_feature_state)

    def test_prepare_does_not_mutate_feature_selection(self) -> None:
        run_id, binding = runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            run_id="predictable-run",
        )

        self.assertEqual(run_id, "predictable-run")
        self.assertEqual(binding["workflow_version"], WORKFLOW_VERSION)
        self.assertEqual(self.feature_state.read_bytes(), self.original_feature_state)

    def test_initial_integration_selection_is_pinned(self) -> None:
        run_id, binding = runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            integration="claude",
            run_id="claude-run",
        )

        self.assertEqual(run_id, "claude-run")
        self.assertEqual(binding["integration"], "claude")
        with self.assertRaisesRegex(ValueError, "integration must be one of"):
            runner.prepare_run(
                self.root,
                WORKFLOW,
                SLICE,
                integration="unknown",
                run_id="bad-run",
            )

    def test_auto_integration_is_resolved_before_specify_persists_inputs(self) -> None:
        _run_id, binding = runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            integration="auto",
            run_id="auto-run",
        )

        self.assertEqual(binding["integration"], "codex")
        self._materialize_specify_run("auto-run", status="paused")
        finalized = runner.finalize_run_binding(self.root, "auto-run")
        self.assertEqual(finalized["integration"], "codex")

    def test_child_feature_selection_mutation_is_restored_and_rejected(self) -> None:
        def mutating_invocation(
            _root: Path,
            _command: list[str],
            _environment: dict[str, str],
        ) -> int:
            self.feature_state.write_text('{"feature":"wrong"}\n', encoding="utf-8")
            return 0

        with mock.patch.object(runner, "_invoke", side_effect=mutating_invocation):
            with self.assertRaisesRegex(ValueError, "change restored"):
                runner._invoke_without_feature_mutation(
                    self.root,
                    ["specify"],
                    {},
                )

        self.assertEqual(self.feature_state.read_bytes(), self.original_feature_state)

    def test_resume_rejects_altered_inputs(self) -> None:
        run_id = self._create_finalized_run()
        inputs_path = runner._run_directory(self.root, run_id) / "inputs.json"
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
        inputs["inputs"]["integration"] = "claude"
        self._write_json(inputs_path, inputs)

        with self.assertRaisesRegex(ValueError, "integration input"):
            runner.validate_resume(self.root, run_id)

    def test_resume_rejects_altered_current_workflow(self) -> None:
        run_id = self._create_finalized_run()
        self._write_workflow(suffix="# changed after binding\n")

        with self.assertRaisesRegex(ValueError, "canonical workflow changed"):
            runner.validate_resume(self.root, run_id)

    def test_resume_rejects_altered_persisted_workflow(self) -> None:
        run_id = self._create_finalized_run()
        persisted = runner._run_directory(self.root, run_id) / "workflow.yml"
        persisted.write_text(
            persisted.read_text(encoding="utf-8") + "# changed after binding\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "persisted workflow changed"):
            runner.validate_resume(self.root, run_id)

    def test_finalize_rejects_persisted_workflow_with_different_version(self) -> None:
        runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            run_id="divergent-workflow-run",
        )
        self._materialize_specify_run("divergent-workflow-run")
        persisted = (
            runner._run_directory(self.root, "divergent-workflow-run")
            / "workflow.yml"
        )
        persisted.write_text(
            persisted.read_text(encoding="utf-8").replace(
                f'version: "{WORKFLOW_VERSION}"', 'version: "0.0.1"'
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ValueError, "different workflow identity or version"
        ):
            runner.finalize_run_binding(self.root, "divergent-workflow-run")

    def test_finalize_accepts_reserialized_persisted_workflow(self) -> None:
        """The live specify CLI re-emits YAML (quotes, wrapping); finalize must
        accept a byte-different but identity-equal persisted copy — the gap the
        byte-exact mock previously hid."""
        runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            run_id="reserialized-workflow-run",
        )
        self._materialize_specify_run("reserialized-workflow-run")
        persisted = (
            runner._run_directory(self.root, "reserialized-workflow-run")
            / "workflow.yml"
        )
        reserialized = persisted.read_text(encoding="utf-8").replace('"', "'")
        persisted.write_text(reserialized, encoding="utf-8")

        finalized = runner.finalize_run_binding(
            self.root, "reserialized-workflow-run"
        )
        self.assertEqual(
            finalized["persisted_workflow_sha256"],
            runner._sha256(persisted),
        )
        runner.validate_resume(self.root, "reserialized-workflow-run")

    def test_resume_rejects_persisted_workflow_tampered_after_finalize(self) -> None:
        run_id = self._create_finalized_run()
        persisted = runner._run_directory(self.root, run_id) / "workflow.yml"
        persisted.write_text(
            persisted.read_text(encoding="utf-8") + "# tampered after bind\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ValueError, "changed after the run was bound"
        ):
            runner.validate_resume(self.root, run_id)

    def test_resume_rejects_altered_state(self) -> None:
        run_id = self._create_finalized_run()
        state_path = runner._run_directory(self.root, run_id) / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "failed"
        self._write_json(state_path, state)

        with self.assertRaisesRegex(ValueError, "status changed outside"):
            runner.validate_resume(self.root, run_id)

    def test_resume_rejects_changed_task_graph(self) -> None:
        run_id = self._create_finalized_run()
        tasks = self.root / SLICE / "tasks.md"
        tasks.write_text(
            tasks.read_text(encoding="utf-8") + "- [ ] T002 New work\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "task graph changed"):
            runner.validate_resume(self.root, run_id)

    def test_finalize_rejects_task_graph_changed_during_initial_run(self) -> None:
        runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            run_id="changed-initial-tasks-run",
        )
        self._materialize_specify_run("changed-initial-tasks-run")
        tasks = self.root / SLICE / "tasks.md"
        tasks.write_text(
            tasks.read_text(encoding="utf-8") + "- [ ] T002 New work\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "task graph changed"):
            runner.finalize_run_binding(self.root, "changed-initial-tasks-run")

    def test_resume_rejects_task_graph_changed_during_invocation(self) -> None:
        run_id = self._create_finalized_run(run_id="resume-task-change")
        binding_path = runner._run_directory(self.root, run_id) / runner.BINDING_NAME
        original_binding = json.loads(binding_path.read_text(encoding="utf-8"))

        def mutating_invocation(
            _root: Path,
            _command: list[str],
            _environment: dict[str, str],
        ) -> int:
            tasks = self.root / SLICE / "tasks.md"
            tasks.write_text(
                tasks.read_text(encoding="utf-8") + "- [ ] T002 New work\n",
                encoding="utf-8",
            )
            return 0

        with mock.patch.object(runner, "_invoke", side_effect=mutating_invocation):
            with self.assertRaisesRegex(ValueError, "changed during the run"):
                runner.resume_bound_run(self.root, run_id)

        current_binding = json.loads(binding_path.read_text(encoding="utf-8"))
        self.assertEqual(
            current_binding["tasks_file_sha256"],
            original_binding["tasks_file_sha256"],
        )

    def test_resume_rejects_changed_integration_implementation(self) -> None:
        run_id = self._create_finalized_run(run_id="changed-integration")
        self.integration_files["codex"].write_text(
            "# changed integration implementation\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "differs from its manifest"):
            runner.validate_resume(self.root, run_id)

    def test_resume_rejects_altered_binding(self) -> None:
        run_id = self._create_finalized_run()
        binding_path = runner._run_directory(self.root, run_id) / runner.BINDING_NAME
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        binding["requested_inputs_sha256"] = "0" * 64
        self._write_json(binding_path, binding)

        with self.assertRaisesRegex(ValueError, "input digest"):
            runner.validate_resume(self.root, run_id)

    def test_resume_rejects_non_resumable_unchanged_state(self) -> None:
        runner.prepare_run(
            self.root,
            WORKFLOW,
            SLICE,
            run_id="completed-run",
        )
        self._materialize_specify_run("completed-run", status="completed")
        runner.finalize_run_binding(self.root, "completed-run")

        with self.assertRaisesRegex(ValueError, "cannot resume"):
            runner.validate_resume(self.root, "completed-run")

    def test_generated_run_id_is_safe_and_slice_specific(self) -> None:
        run_id = runner._generated_run_id(WORKFLOW, SLICE)

        self.assertIsNotNone(runner.RUN_ID.fullmatch(run_id))
        self.assertTrue(run_id.startswith(f"{WORKFLOW}-010-"))
        self.assertLessEqual(len(run_id), 64)
        self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9_-]+", run_id))

    def test_wrong_speckit_installation_fails_before_execution(self) -> None:
        with mock.patch.object(
            runner,
            "_governance_check_cli",
            return_value=["wrong version", "wrong provenance"],
        ):
            with self.assertRaisesRegex(ValueError, "wrong version; wrong provenance"):
                runner.verify_speckit_installation(self.root)


if __name__ == "__main__":
    unittest.main()
