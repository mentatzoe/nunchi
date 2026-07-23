#!/usr/bin/env python3
"""Run or resume one Nunchi workflow with an immutable exact-slice binding."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


WORKFLOWS = {"nunchi-plan", "speckit"}
INTEGRATIONS = {"auto", "claude", "codex"}
REQUIRED_SPECKIT_VERSION = "0.12.11"
EXPECTED_INTEGRATION_SKILLS = {
    "speckit-analyze",
    "speckit-checklist",
    "speckit-clarify",
    "speckit-constitution",
    "speckit-converge",
    "speckit-implement",
    "speckit-plan",
    "speckit-specify",
    "speckit-tasks",
    "speckit-taskstoissues",
}
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
BINDING_NAME = "nunchi-binding.json"
BINDING_SCHEMA_VERSION = 3
TASKS_STEP_ID = "tasks"
RESUMABLE_STATUSES = {"failed", "paused"}
RUN_STATUSES = {
    "aborted",
    "completed",
    "created",
    "failed",
    "paused",
    "running",
}
BINDING_KEYS = {
    "created_at",
    "finalized_at",
    "inputs_file_sha256",
    "integration",
    "integration_manifest_sha256",
    "initial_tasks_file_sha256",
    "persisted_workflow_sha256",
    "requested_inputs_sha256",
    "resolved_inputs_sha256",
    "run_id",
    "schema_version",
    "slice_directory",
    "state_created_at",
    "state_sha256",
    "state_status",
    "tasks_file_sha256",
    "tasks_transition_from_state_sha256",
    "tasks_transition_step_id",
    "tasks_transition_to_state_sha256",
    "tasks_transitioned_at",
    "workflow",
    "workflow_sha256",
    "workflow_version",
}
STATE_KEYS = {
    "created_at",
    "current_step_id",
    "current_step_index",
    "run_id",
    "status",
    "step_results",
    "updated_at",
    "workflow_id",
}


def verify_slice_binding(root: Path, slice_directory: str) -> dict[str, object]:
    """Load the sibling preflight in script and package execution modes."""

    scripts_directory = str(Path(__file__).resolve().parent)
    if scripts_directory not in sys.path:
        sys.path.insert(0, scripts_directory)
    module_name = (
        f"{__package__}.check_slice_binding" if __package__ else "check_slice_binding"
    )
    module = importlib.import_module(module_name)
    return module.verify_slice_binding(root, slice_directory)


def _governance_check_cli(root: Path) -> list[str]:
    """Load the repository's exact SpecKit version/provenance check."""

    scripts_directory = str(Path(__file__).resolve().parent)
    if scripts_directory not in sys.path:
        sys.path.insert(0, scripts_directory)
    module_name = (
        f"{__package__}.check_governance" if __package__ else "check_governance"
    )
    module = importlib.import_module(module_name)
    return module.check_cli(root)


def verify_speckit_installation(root: Path) -> None:
    """Fail before workflow execution unless CLI version and provenance match."""

    errors = _governance_check_cli(root)
    if errors:
        raise ValueError("SpecKit installation is not pinned: " + "; ".join(errors))


def _sha256(path: Path) -> str:
    """Return the byte-exact digest of one pinned file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(payload: object) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _yaml_scalar(raw: str, *, label: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    if not value or "#" in value or any(character.isspace() for character in value):
        raise ValueError(f"workflow {label} must be one simple scalar")
    return value


def _workflow_metadata(path: Path) -> tuple[str, str]:
    """Read the workflow ID and version without adding a YAML dependency."""

    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^workflow:[ \t]*\n(?P<body>(?:^[ \t]+[^\n]*(?:\n|\Z))*)",
        text,
    )
    if match is None:
        raise ValueError(f"workflow metadata block is missing: {path}")
    body = match.group("body")

    values: dict[str, str] = {}
    for label in ("id", "version"):
        matches = re.findall(rf"(?m)^  {label}:[ \t]*(.+?)[ \t]*$", body)
        if len(matches) != 1:
            raise ValueError(
                f"workflow metadata must contain exactly one {label}: {path}"
            )
        values[label] = _yaml_scalar(matches[0], label=label)
    return values["id"], values["version"]


def _workflow_path(root: Path, workflow: str) -> Path:
    if workflow not in WORKFLOWS:
        raise ValueError(f"workflow must be one of {sorted(WORKFLOWS)}")
    workflow_directory = root / ".specify" / "workflows" / workflow
    path = workflow_directory / "workflow.yml"
    if workflow_directory.is_symlink() or not path.is_file() or path.is_symlink():
        raise ValueError(f"canonical workflow is missing or unsafe: {path}")
    workflow_id, _version = _workflow_metadata(path)
    if workflow_id != workflow:
        raise ValueError(
            f"canonical workflow ID {workflow_id!r} does not match {workflow!r}"
        )
    return path


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _run_directory(root: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be one safe workflow-run path component")
    workflows_directory = root / ".specify" / "workflows"
    runs_directory = workflows_directory / "runs"
    for directory in (workflows_directory, runs_directory):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ValueError(f"workflow run directory is unsafe: {directory}")
    run_directory = runs_directory / run_id
    if run_directory.is_symlink():
        raise ValueError(f"workflow run is a symlink: {run_directory}")
    return run_directory


def _load_json_file(path: Path, label: str) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or unsafe: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _parse_utc_timestamp(value: object, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")


def _generated_run_id(workflow: str, slice_directory: str) -> str:
    slice_id = Path(slice_directory).name.split("-", 1)[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{workflow}-{slice_id}-{timestamp}"


def _requested_inputs(slice_directory: str, integration: str) -> dict[str, str]:
    return {"integration": integration, "slice_directory": slice_directory}


def _resolve_integration(root: Path, requested: str) -> str:
    """Resolve ``auto`` exactly once and require an installed integration."""

    if requested not in INTEGRATIONS:
        raise ValueError(f"integration must be one of {sorted(INTEGRATIONS)}")
    state_path = root / ".specify" / "integration.json"
    state = _load_json_file(state_path, "SpecKit integration state")
    if state.get("version") != REQUIRED_SPECKIT_VERSION:
        raise ValueError(
            "SpecKit integration state does not match the required CLI version"
        )
    installed = state.get("installed_integrations")
    if (
        not isinstance(installed, list)
        or not installed
        or any(not isinstance(item, str) for item in installed)
    ):
        raise ValueError(
            "SpecKit integration state has no valid installed integrations"
        )
    selected = state.get("default_integration") if requested == "auto" else requested
    if not isinstance(selected, str) or selected not in installed:
        raise ValueError(
            f"requested integration {requested!r} does not resolve to an installed integration"
        )
    if selected not in INTEGRATIONS - {"auto"}:
        raise ValueError(f"integration {selected!r} is not supported by this spine")
    return selected


def _integration_manifest_path(root: Path, integration: str) -> Path:
    if integration not in INTEGRATIONS - {"auto"}:
        raise ValueError(f"integration {integration!r} cannot be bound")
    directory = root / ".specify" / "integrations"
    path = directory / f"{integration}.manifest.json"
    if directory.is_symlink() or not path.is_file() or path.is_symlink():
        raise ValueError(f"integration manifest is missing or unsafe: {path}")
    return path


def _safe_manifest_file(root: Path, relative_text: str) -> Path:
    relative = Path(relative_text)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"integration manifest path is unsafe: {relative_text!r}")
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(
                f"integration manifest path has a symlink: {relative_text!r}"
            )
    try:
        contained = candidate.resolve(strict=False).is_relative_to(root.resolve())
    except OSError as exc:
        raise ValueError(
            f"integration manifest path is unreadable: {relative_text!r}"
        ) from exc
    if not contained or not candidate.is_file():
        raise ValueError(
            f"integration manifest file is missing or unsafe: {relative_text!r}"
        )
    return candidate


def _validate_integration_manifest(root: Path, integration: str) -> Path:
    """Require the selected integration manifest and every pinned skill byte."""

    manifest_path = _integration_manifest_path(root, integration)
    manifest = _load_json_file(manifest_path, f"{integration} integration manifest")
    if set(manifest) != {"integration", "version", "installed_at", "files"}:
        raise ValueError(f"{integration} integration manifest has an invalid schema")
    if manifest.get("integration") != integration:
        raise ValueError(f"{integration} integration manifest has the wrong identity")
    version = manifest.get("version")
    if version != REQUIRED_SPECKIT_VERSION:
        raise ValueError(
            f"{integration} integration manifest has the wrong SpecKit version"
        )
    _parse_utc_timestamp(
        manifest.get("installed_at"),
        f"{integration} integration manifest installed_at",
    )
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"{integration} integration manifest has no files")
    required_prefix = (
        ".agents/skills/speckit-"
        if integration == "codex"
        else ".claude/skills/speckit-"
    )
    integration_root = ".agents" if integration == "codex" else ".claude"
    expected_files = {
        f"{integration_root}/skills/{skill}/SKILL.md"
        for skill in EXPECTED_INTEGRATION_SKILLS
    }
    if set(files) != expected_files:
        raise ValueError(
            f"{integration} integration manifest does not pin the exact skill set"
        )
    for relative_text, expected_digest in sorted(files.items()):
        if (
            not isinstance(relative_text, str)
            or not relative_text.startswith(required_prefix)
            or not isinstance(expected_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
        ):
            raise ValueError(
                f"{integration} integration manifest has an invalid file entry"
            )
        path = _safe_manifest_file(root, relative_text)
        if _sha256(path) != expected_digest:
            raise ValueError(
                f"{integration} integration implementation differs from its manifest: "
                f"{relative_text}"
            )
    return manifest_path


def _validate_binding_shape(
    root: Path,
    run_id: str,
    binding: dict[str, object],
    *,
    finalized: bool,
) -> tuple[Path, str]:
    if set(binding) != BINDING_KEYS:
        missing = sorted(BINDING_KEYS - set(binding))
        extra = sorted(set(binding) - BINDING_KEYS)
        raise ValueError(f"binding schema differs (missing={missing}, extra={extra})")
    if binding.get("schema_version") != BINDING_SCHEMA_VERSION:
        raise ValueError("unsupported Nunchi workflow binding schema")
    if binding.get("run_id") != run_id:
        raise ValueError("binding run_id does not match the requested run")

    workflow = binding.get("workflow")
    slice_directory = binding.get("slice_directory")
    integration = binding.get("integration")
    if (
        not isinstance(workflow, str)
        or not isinstance(slice_directory, str)
        or integration not in INTEGRATIONS - {"auto"}
    ):
        raise ValueError(
            "binding workflow, slice_directory, and integration must be canonical"
        )
    verify_slice_binding(root, slice_directory)

    workflow_path = _workflow_path(root, workflow)
    _workflow_id, workflow_version = _workflow_metadata(workflow_path)
    if binding.get("workflow_version") != workflow_version:
        raise ValueError("canonical workflow version changed; start a new bound run")
    if binding.get("workflow_sha256") != _sha256(workflow_path):
        raise ValueError("canonical workflow changed; start a new bound run")
    assert isinstance(integration, str)
    manifest_path = _validate_integration_manifest(root, integration)
    if binding.get("integration_manifest_sha256") != _sha256(manifest_path):
        raise ValueError(
            "selected integration manifest changed; start a new bound run"
        )
    expected_input_digest = _json_sha256(
        _requested_inputs(slice_directory, integration)
    )
    if binding.get("requested_inputs_sha256") != expected_input_digest:
        raise ValueError("requested slice input digest does not match the binding")
    _parse_utc_timestamp(binding.get("created_at"), "binding created_at")

    finalized_fields = (
        "finalized_at",
        "inputs_file_sha256",
        "persisted_workflow_sha256",
        "resolved_inputs_sha256",
        "state_created_at",
        "state_sha256",
        "state_status",
    )
    populated = [binding.get(field) is not None for field in finalized_fields]
    if finalized and not all(populated):
        raise ValueError("run lacks a complete finalized binding")
    if not finalized and any(populated):
        raise ValueError("new run binding was already partially finalized")
    initial_tasks_digest = binding.get("initial_tasks_file_sha256")
    tasks_digest = binding.get("tasks_file_sha256")
    for label, digest in (
        ("initial bound slice task", initial_tasks_digest),
        ("bound slice task", tasks_digest),
    ):
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError(f"{label} digest is malformed")

    transition_fields = (
        "tasks_transitioned_at",
        "tasks_transition_step_id",
        "tasks_transition_from_state_sha256",
        "tasks_transition_to_state_sha256",
    )
    transition_values = [binding.get(field) for field in transition_fields]
    if any(value is not None for value in transition_values):
        if not all(value is not None for value in transition_values):
            raise ValueError("task graph transition evidence is incomplete")
        _parse_utc_timestamp(
            binding.get("tasks_transitioned_at"),
            "task graph transition timestamp",
        )
        if binding.get("tasks_transition_step_id") != TASKS_STEP_ID:
            raise ValueError("task graph transition was not recorded at the tasks step")
        for field in (
            "tasks_transition_from_state_sha256",
            "tasks_transition_to_state_sha256",
        ):
            digest = binding.get(field)
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            ):
                raise ValueError("task graph transition state digest is malformed")
        if tasks_digest == initial_tasks_digest:
            raise ValueError("task graph transition did not change the task digest")
    elif tasks_digest != initial_tasks_digest:
        raise ValueError("task graph digest changed without transition evidence")
    return workflow_path, workflow_version


def _validate_inputs(
    run_directory: Path,
    binding: dict[str, object],
) -> dict[str, object]:
    inputs_path = run_directory / "inputs.json"
    inputs = _load_json_file(inputs_path, "SpecKit run inputs")
    if set(inputs) != {"inputs"}:
        raise ValueError("SpecKit run inputs have an unexpected outer schema")
    stored_inputs = inputs.get("inputs")
    if not isinstance(stored_inputs, dict):
        raise ValueError("SpecKit run inputs are malformed")
    if stored_inputs.get("slice_directory") != binding["slice_directory"]:
        raise ValueError("persisted slice input does not match the immutable binding")
    if stored_inputs.get("integration") != binding["integration"]:
        raise ValueError(
            "persisted integration input does not match the immutable binding"
        )
    if _json_sha256(stored_inputs) != binding.get("resolved_inputs_sha256"):
        raise ValueError("persisted workflow inputs changed after the run was bound")
    if _sha256(inputs_path) != binding.get("inputs_file_sha256"):
        raise ValueError(
            "persisted workflow input file changed after the run was bound"
        )
    return stored_inputs


def _tasks_path(root: Path, binding: dict[str, object]) -> Path:
    slice_directory = binding.get("slice_directory")
    if not isinstance(slice_directory, str):
        raise ValueError("binding slice_directory is malformed")
    path = root / slice_directory / "tasks.md"
    if not path.is_file() or path.is_symlink():
        raise ValueError("bound slice tasks.md is missing or unsafe")
    return path


def _validate_state_shape(
    state: dict[str, object],
    *,
    run_id: str,
    workflow: str,
) -> None:
    if set(state) != STATE_KEYS:
        raise ValueError("SpecKit run state has an unexpected schema")
    if state.get("run_id") != run_id or state.get("workflow_id") != workflow:
        raise ValueError("SpecKit run state does not match the bound workflow")
    status = state.get("status")
    if status not in RUN_STATUSES:
        raise ValueError(f"SpecKit run state has an invalid status: {status!r}")
    step_index = state.get("current_step_index")
    if (
        isinstance(step_index, bool)
        or not isinstance(step_index, int)
        or step_index < 0
    ):
        raise ValueError("SpecKit run state has an invalid current_step_index")
    step_id = state.get("current_step_id")
    if step_id is not None and not isinstance(step_id, str):
        raise ValueError("SpecKit run state has an invalid current_step_id")
    if not isinstance(state.get("step_results"), dict):
        raise ValueError("SpecKit run state has invalid step_results")
    _parse_utc_timestamp(state.get("created_at"), "SpecKit state created_at")
    _parse_utc_timestamp(state.get("updated_at"), "SpecKit state updated_at")


def _workflow_step_ids(path: Path) -> list[str]:
    """Return the canonical sequential step IDs used for boundary proofs."""

    values = re.findall(r"(?m)^  - id:[ \t]*(.+?)[ \t]*$", path.read_text("utf-8"))
    step_ids = [_yaml_scalar(value, label="step id") for value in values]
    if len(step_ids) != len(set(step_ids)):
        raise ValueError("workflow step IDs must be unique")
    return step_ids


def _tasks_step_index(root: Path, workflow: str) -> int:
    step_ids = _workflow_step_ids(_workflow_path(root, workflow))
    if step_ids.count(TASKS_STEP_ID) != 1:
        raise ValueError("bound workflow must contain exactly one tasks step")
    return step_ids.index(TASKS_STEP_ID)


def _completed_tasks_step_result(state: dict[str, object]) -> dict[str, object]:
    """Require the engine's exact successful ``speckit.tasks`` dispatch record."""

    step_results = state.get("step_results")
    if not isinstance(step_results, dict):
        raise ValueError("SpecKit run state has invalid step_results")
    result = step_results.get(TASKS_STEP_ID)
    if not isinstance(result, dict):
        raise ValueError("task graph transition lacks a recorded tasks step")
    output = result.get("output")
    if (
        result.get("type") != "command"
        or result.get("status") != "completed"
        or not isinstance(output, dict)
        or output.get("command") != "speckit.tasks"
        or output.get("dispatched") is not True
        or output.get("exit_code") != 0
    ):
        raise ValueError("task graph transition lacks a successful speckit.tasks step")
    return result


def _validate_recorded_task_transition(
    root: Path,
    binding: dict[str, object],
    state: dict[str, object],
) -> None:
    """Validate durable transition evidence retained by every later state."""

    if binding.get("tasks_transitioned_at") is None:
        return
    _completed_tasks_step_result(state)
    workflow = binding.get("workflow")
    if not isinstance(workflow, str):
        raise ValueError("binding workflow is malformed")
    tasks_index = _tasks_step_index(root, workflow)
    step_index = state.get("current_step_index")
    if not isinstance(step_index, int) or step_index < tasks_index:
        raise ValueError("recorded task transition predates the tasks step")


def _record_task_transition(
    root: Path,
    binding: dict[str, object],
    prior_state: dict[str, object] | None,
    state: dict[str, object],
    tasks_digest: str,
    state_sha256: str,
) -> None:
    """Consume the one task-digest transition only as ``tasks`` is crossed."""

    if prior_state is None:
        raise ValueError(
            "task graph changed without a wrapper-observed tasks transition"
        )
    if binding.get("tasks_transitioned_at") is not None:
        raise ValueError("task graph changed after its one allowed transition")

    workflow = binding.get("workflow")
    run_id = binding.get("run_id")
    if not isinstance(workflow, str) or not isinstance(run_id, str):
        raise ValueError("binding workflow identity is malformed")
    _validate_state_shape(prior_state, run_id=run_id, workflow=workflow)
    if prior_state.get("status") not in RESUMABLE_STATUSES:
        raise ValueError("task graph transition did not begin from a resumable state")
    if prior_state.get("created_at") != binding.get("state_created_at"):
        raise ValueError("task graph transition changed the run state identity")

    prior_results = prior_state.get("step_results")
    current_results = state.get("step_results")
    assert isinstance(prior_results, dict)
    assert isinstance(current_results, dict)
    if TASKS_STEP_ID in prior_results:
        raise ValueError("tasks step was already recorded before the task graph changed")
    _completed_tasks_step_result(state)

    tasks_index = _tasks_step_index(root, workflow)
    prior_index = prior_state.get("current_step_index")
    current_index = state.get("current_step_index")
    if (
        not isinstance(prior_index, int)
        or not isinstance(current_index, int)
        or prior_index >= tasks_index
        or current_index < tasks_index
    ):
        raise ValueError("task graph change did not cross the tasks boundary")

    prior_current_step = prior_state.get("current_step_id")
    for step_id, result in prior_results.items():
        if step_id != prior_current_step and current_results.get(step_id) != result:
            raise ValueError(
                "SpecKit rewrote completed step evidence while crossing tasks"
            )

    initial_digest = binding.get("initial_tasks_file_sha256")
    if tasks_digest == initial_digest:
        raise ValueError("task graph transition did not change the task digest")
    binding.update(
        {
            "tasks_file_sha256": tasks_digest,
            "tasks_transitioned_at": datetime.now(timezone.utc).isoformat(),
            "tasks_transition_step_id": TASKS_STEP_ID,
            "tasks_transition_from_state_sha256": binding["state_sha256"],
            "tasks_transition_to_state_sha256": state_sha256,
        }
    )


def _validate_bound_run(
    root: Path,
    run_id: str,
    *,
    require_resumable: bool,
) -> dict[str, object]:
    run_directory = _run_directory(root, run_id)
    if not run_directory.is_dir():
        raise ValueError(f"workflow run directory is missing: {run_directory}")
    binding = _load_json_file(run_directory / BINDING_NAME, "Nunchi workflow binding")
    _workflow_path_current, workflow_version = _validate_binding_shape(
        root,
        run_id,
        binding,
        finalized=True,
    )

    persisted = run_directory / "workflow.yml"
    if not persisted.is_file() or persisted.is_symlink():
        raise ValueError("persisted workflow is missing or unsafe")
    persisted_id, persisted_version = _workflow_metadata(persisted)
    if persisted_id != binding["workflow"] or persisted_version != workflow_version:
        raise ValueError(
            "persisted workflow identity or version differs from the binding"
        )
    if _sha256(persisted) != binding.get("persisted_workflow_sha256"):
        raise ValueError("persisted workflow changed after the run was bound")

    _validate_inputs(run_directory, binding)
    if _sha256(_tasks_path(root, binding)) != binding.get("tasks_file_sha256"):
        raise ValueError(
            "bound slice task graph changed after the run paused; start a new bound run"
        )

    state_path = run_directory / "state.json"
    state = _load_json_file(state_path, "SpecKit run state")
    workflow = str(binding["workflow"])
    _validate_state_shape(state, run_id=run_id, workflow=workflow)
    _validate_recorded_task_transition(root, binding, state)
    if state.get("created_at") != binding.get("state_created_at"):
        raise ValueError("SpecKit run state identity changed after the run was bound")
    if state.get("status") != binding.get("state_status"):
        raise ValueError("SpecKit run status changed outside the bound wrapper")
    if _sha256(state_path) != binding.get("state_sha256"):
        raise ValueError("SpecKit run state changed outside the bound wrapper")
    if require_resumable and state.get("status") not in RESUMABLE_STATUSES:
        raise ValueError(
            f"run {run_id!r} cannot resume from status {state.get('status')!r}"
        )
    _parse_utc_timestamp(binding.get("finalized_at"), "binding finalized_at")
    return binding


def prepare_run(
    root: Path,
    workflow: str,
    slice_directory: str,
    *,
    integration: str = "auto",
    run_id: str | None = None,
) -> tuple[str, dict[str, object]]:
    """Preflight one slice and persist the wrapper-owned initial binding."""

    verify_slice_binding(root, slice_directory)
    resolved_integration = _resolve_integration(root, integration)
    manifest_path = _validate_integration_manifest(root, resolved_integration)
    workflow_path = _workflow_path(root, workflow)
    workflow_id, workflow_version = _workflow_metadata(workflow_path)
    if workflow_id != workflow:  # Defensive: _workflow_path already checks this.
        raise ValueError("canonical workflow ID changed during binding")
    selected_run_id = run_id or _generated_run_id(workflow, slice_directory)
    run_directory = _run_directory(root, selected_run_id)
    if run_directory.exists():
        raise ValueError(f"workflow run already exists: {selected_run_id}")
    initial_tasks_digest = _sha256(
        _tasks_path(root, {"slice_directory": slice_directory})
    )
    payload: dict[str, object] = {
        "schema_version": BINDING_SCHEMA_VERSION,
        "run_id": selected_run_id,
        "workflow": workflow,
        "workflow_version": workflow_version,
        "workflow_sha256": _sha256(workflow_path),
        "slice_directory": slice_directory,
        "integration": resolved_integration,
        "integration_manifest_sha256": _sha256(manifest_path),
        "requested_inputs_sha256": _json_sha256(
            _requested_inputs(slice_directory, resolved_integration)
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finalized_at": None,
        "persisted_workflow_sha256": None,
        "resolved_inputs_sha256": None,
        "inputs_file_sha256": None,
        "state_created_at": None,
        "state_sha256": None,
        "state_status": None,
        "initial_tasks_file_sha256": initial_tasks_digest,
        "tasks_file_sha256": initial_tasks_digest,
        "tasks_transitioned_at": None,
        "tasks_transition_step_id": None,
        "tasks_transition_from_state_sha256": None,
        "tasks_transition_to_state_sha256": None,
    }
    _atomic_json(run_directory / BINDING_NAME, payload)
    return selected_run_id, payload


def finalize_run_binding(root: Path, run_id: str) -> dict[str, object]:
    """Pin and self-validate the run artifacts produced by SpecKit."""

    run_directory = _run_directory(root, run_id)
    binding_path = run_directory / BINDING_NAME
    binding = _load_json_file(binding_path, "Nunchi workflow binding")
    _workflow_path_current, workflow_version = _validate_binding_shape(
        root,
        run_id,
        binding,
        finalized=False,
    )

    persisted = run_directory / "workflow.yml"
    if not persisted.is_file() or persisted.is_symlink():
        raise ValueError("SpecKit did not persist a safe workflow copy")
    persisted_id, persisted_version = _workflow_metadata(persisted)
    if persisted_id != binding["workflow"] or persisted_version != workflow_version:
        raise ValueError("SpecKit persisted a different workflow identity or version")
    # SpecKit re-serializes the workflow when persisting its run copy (quote
    # style, line wrapping), so byte-equality with the canonical file is the
    # wrong oracle here. The canonical file — the one SpecKit actually loaded —
    # is re-verified against the prepare-time pin in _validate_binding_shape;
    # the persisted copy is identity-checked above and its exact digest is
    # recorded below so resume can prove it never changes afterwards.

    inputs_path = run_directory / "inputs.json"
    inputs = _load_json_file(inputs_path, "SpecKit run inputs")
    if set(inputs) != {"inputs"} or not isinstance(inputs.get("inputs"), dict):
        raise ValueError("SpecKit run inputs are malformed")
    resolved_inputs = inputs["inputs"]
    assert isinstance(resolved_inputs, dict)
    if resolved_inputs.get("slice_directory") != binding["slice_directory"]:
        raise ValueError("SpecKit persisted a different slice input")
    if resolved_inputs.get("integration") != binding["integration"]:
        raise ValueError("SpecKit persisted a different integration input")

    state_path = run_directory / "state.json"
    state = _load_json_file(state_path, "SpecKit run state")
    workflow = str(binding["workflow"])
    _validate_state_shape(state, run_id=run_id, workflow=workflow)

    binding.update(
        {
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "persisted_workflow_sha256": _sha256(persisted),
            "resolved_inputs_sha256": _json_sha256(resolved_inputs),
            "inputs_file_sha256": _sha256(inputs_path),
            "state_created_at": state["created_at"],
            "state_sha256": _sha256(state_path),
            "state_status": state["status"],
        }
    )
    _atomic_json(binding_path, binding)
    return _validate_bound_run(root, run_id, require_resumable=False)


def validate_resume(root: Path, run_id: str) -> dict[str, object]:
    """Fail closed unless every pinned run artifact is safe to resume."""

    return _validate_bound_run(root, run_id, require_resumable=True)


def _refresh_state_binding_after_resume(
    root: Path,
    run_id: str,
    prior_binding: dict[str, object],
    *,
    prior_state: dict[str, object] | None = None,
) -> dict[str, object]:
    """Accept only the state transition made by the just-finished resume."""

    run_directory = _run_directory(root, run_id)
    binding_path = run_directory / BINDING_NAME
    current_binding = _load_json_file(binding_path, "Nunchi workflow binding")
    if current_binding != prior_binding:
        raise ValueError("Nunchi workflow binding changed during resume")

    # The workflow and inputs are immutable across a resume. Temporarily verify
    # the prior state separately because the workflow invocation is expected to
    # advance state.json.
    _workflow_path_current, workflow_version = _validate_binding_shape(
        root,
        run_id,
        current_binding,
        finalized=True,
    )
    persisted = run_directory / "workflow.yml"
    if not persisted.is_file() or persisted.is_symlink():
        raise ValueError("persisted workflow is missing or unsafe after resume")
    persisted_id, persisted_version = _workflow_metadata(persisted)
    if (
        persisted_id != current_binding["workflow"]
        or persisted_version != workflow_version
        or _sha256(persisted) != current_binding["persisted_workflow_sha256"]
    ):
        raise ValueError("persisted workflow changed during resume")
    _validate_inputs(run_directory, current_binding)

    state_path = run_directory / "state.json"
    state = _load_json_file(state_path, "SpecKit run state")
    workflow = str(current_binding["workflow"])
    _validate_state_shape(state, run_id=run_id, workflow=workflow)
    if state.get("created_at") != current_binding.get("state_created_at"):
        raise ValueError("SpecKit run state identity changed during resume")

    tasks_digest = _sha256(_tasks_path(root, current_binding))
    if tasks_digest != current_binding["tasks_file_sha256"]:
        _record_task_transition(
            root,
            current_binding,
            prior_state,
            state,
            tasks_digest,
            _sha256(state_path),
        )

    current_binding["state_sha256"] = _sha256(state_path)
    current_binding["state_status"] = state["status"]
    _atomic_json(binding_path, current_binding)
    return _validate_bound_run(root, run_id, require_resumable=False)


def _feature_state_snapshot(root: Path) -> tuple[bool, bytes | None]:
    path = root / ".specify" / "feature.json"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(".specify/feature.json is unsafe")
    return path.exists(), path.read_bytes() if path.exists() else None


def _restore_feature_state(root: Path, snapshot: tuple[bool, bytes | None]) -> None:
    """Restore the umbrella feature selector after an unexpected child write."""

    path = root / ".specify" / "feature.json"
    existed, content = snapshot
    if path.is_symlink():
        path.unlink()
    if not existed:
        path.unlink(missing_ok=True)
        return
    if content is None:  # Defensive: an existing snapshot always has bytes.
        raise ValueError("cannot restore .specify/feature.json from an empty snapshot")
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _invoke(root: Path, command: list[str], environment: dict[str, str]) -> int:
    completed = subprocess.run(command, cwd=root, env=environment, check=False)
    return completed.returncode


def _invoke_without_feature_mutation(
    root: Path,
    command: list[str],
    environment: dict[str, str],
) -> int:
    before = _feature_state_snapshot(root)
    try:
        return _invoke(root, command, environment)
    finally:
        if _feature_state_snapshot(root) != before:
            _restore_feature_state(root, before)
            raise ValueError(
                "bound workflow modified .specify/feature.json; change restored and run rejected"
            )


def start_bound_run(
    root: Path,
    workflow: str,
    slice_directory: str,
    *,
    integration: str = "auto",
) -> tuple[str, int]:
    """Start, finalize, and self-validate one exact-slice workflow run."""

    verify_speckit_installation(root)
    run_id, binding = prepare_run(
        root,
        workflow,
        slice_directory,
        integration=integration,
    )
    environment = os.environ.copy()
    environment["SPECIFY_FEATURE_DIRECTORY"] = str(binding["slice_directory"])
    environment["SPECKIT_WORKFLOW_RUN_ID"] = run_id
    print(
        f"Bound {workflow} run {run_id} to {slice_directory} "
        f"with {binding['integration']}",
        file=sys.stderr,
    )
    return_code = _invoke_without_feature_mutation(
        root,
        [
            "specify",
            "workflow",
            "run",
            workflow,
            "--input",
            f"slice_directory={slice_directory}",
            "--input",
            f"integration={binding['integration']}",
            "--json",
        ],
        environment,
    )
    finalized = finalize_run_binding(root, run_id)
    print(
        f"Bound run {run_id} finished with status {finalized['state_status']}",
        file=sys.stderr,
    )
    if finalized["state_status"] in RESUMABLE_STATUSES:
        print(
            f"Resume only with: python3 scripts/run_slice_workflow.py resume {run_id}",
            file=sys.stderr,
        )
    return run_id, return_code


def resume_bound_run(root: Path, run_id: str) -> int:
    """Resume one validated run without permitting new or altered inputs."""

    verify_speckit_installation(root)
    binding = validate_resume(root, run_id)
    prior_state = _load_json_file(
        _run_directory(root, run_id) / "state.json",
        "SpecKit run state",
    )
    environment = os.environ.copy()
    environment["SPECIFY_FEATURE_DIRECTORY"] = str(binding["slice_directory"])
    environment["SPECKIT_WORKFLOW_RUN_ID"] = run_id
    return_code = _invoke_without_feature_mutation(
        root,
        ["specify", "workflow", "resume", run_id, "--json"],
        environment,
    )
    refreshed = _refresh_state_binding_after_resume(
        root,
        run_id,
        binding,
        prior_state=prior_state,
    )
    print(
        f"Bound run {run_id} finished with status {refreshed['state_status']}",
        file=sys.stderr,
    )
    if refreshed["state_status"] in RESUMABLE_STATUSES:
        print(
            f"Resume only with: python3 scripts/run_slice_workflow.py resume {run_id}",
            file=sys.stderr,
        )
    return return_code


def repair_bound_run(root: Path, run_id: str) -> int:
    """Re-pin the binding to the engine's own recorded state transition.

    An interrupted invocation (killed step session, wrapper death) can leave
    state.json legitimately advanced by the SpecKit engine while the binding
    still pins the pre-invocation state, which makes every later resume fail
    with a drift error. This deliberate operator command accepts exactly that
    transition: every other pin (workflow, inputs, task graph, state identity)
    is still enforced by the refresh validation.
    """

    binding = _load_json_file(
        _run_directory(root, run_id) / BINDING_NAME, "Nunchi workflow binding"
    )
    refreshed = _refresh_state_binding_after_resume(root, run_id, binding)
    print(
        f"Repaired binding for {run_id}: status {refreshed['state_status']}",
        file=sys.stderr,
    )
    if refreshed["state_status"] in RESUMABLE_STATUSES:
        print(
            f"Resume only with: python3 scripts/run_slice_workflow.py resume {run_id}",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    run_parser = subparsers.add_parser("run", help="start one bound slice workflow")
    run_parser.add_argument("workflow", choices=sorted(WORKFLOWS))
    run_parser.add_argument("slice_directory")
    run_parser.add_argument(
        "--integration",
        choices=sorted(INTEGRATIONS),
        default="auto",
        help="SpecKit agent integration to pin for this run (default: auto)",
    )

    resume_parser = subparsers.add_parser(
        "resume", help="resume without changing the bound slice or workflow"
    )
    resume_parser.add_argument("run_id")

    repair_parser = subparsers.add_parser(
        "repair",
        help="re-pin the binding after an interrupted invocation advanced state",
    )
    repair_parser.add_argument("run_id")

    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    try:
        if args.action == "run":
            _run_id, return_code = start_bound_run(
                root,
                args.workflow,
                args.slice_directory,
                integration=args.integration,
            )
            return return_code
        if args.action == "repair":
            return repair_bound_run(root, args.run_id)
        return resume_bound_run(root, args.run_id)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
