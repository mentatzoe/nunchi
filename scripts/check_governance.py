#!/usr/bin/env python3
"""Validate Nunchi's SpecKit pin and control-plane/product boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


PINNED_SPECKIT_VERSION = "0.12.11"
PINNED_SPECKIT_COMMIT = "e802a7dd52a6eceba9403cbbf40e60dced043238"
PINNED_CONSTITUTION_VERSION = "2.3.0"
PINNED_VAULT_COMMIT = "c834e8c"
IMPLEMENTATION_AUTHORIZATION_PATH = Path(
    "evidence/governance/v2-implementation-authorization.md"
)
IMPLEMENTATION_AUTHORIZATION_BOUNDARY = (
    "This record documents externally granted implementation authority; it does "
    "not grant it and does not authorize cutover, release, or promotion."
)
HISTORICAL_EVIDENCE_HASHES = {
    Path(
        "evidence/governance/v2-execution-spine-2026-07-11.md"
    ): "c1a81b9e0f5b762e1870c45627a3338be2666626d1db15292456f71a16b8cb3e",
    Path(
        "evidence/governance/slice-lifecycle-amendment-2026-07-11.md"
    ): "626fb11347d50e343b533db163bde8df8eb1e3242b91a013e3f6532d597ba808",
}
PROGRAM_STATES = (
    "PLANNING",
    "READY",
    "DELIVERY",
    "INTEGRATION",
    "CUTOVER_ACCEPTED",
    "CUTOVER_VERIFIED",
)
SLICE_STATES = (
    "PLANNED",
    "READY",
    "ACTIVE",
    "CONVERGED",
    "HANDOFF_READY",
    "ACCEPTED",
)
ALLOWED_SPEC_FILES = {"spec.md", "plan.md", "tasks.md", "research.md", "README.md"}
FORBIDDEN_SPEC_PARTS = {
    "contracts",
    "docs",
    "evals",
    "evidence",
    "fixtures",
    "integrations",
    "schemas",
    "scripts",
    "src",
    "tests",
}
EXECUTABLE_SUFFIXES = {
    ".bash",
    ".cjs",
    ".js",
    ".json",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".yaml",
    ".yml",
    ".zsh",
}
SCAN_ROOTS = (".github", "src", "tests", "evals", "scripts", "integrations")
MANAGED_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"\.specify|specs|"
    r"\.agents/skills/speckit-[A-Za-z0-9_-]+|"
    r"\.claude/skills/speckit-[A-Za-z0-9_-]+"
    r")/"
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
WORKFLOW_COMMAND = re.compile(r"^\s+command:\s+([A-Za-z0-9_.-]+)\s*$", re.MULTILINE)
WORKFLOW_STEP_ID = re.compile(r"^  - id:\s+([A-Za-z0-9_.-]+)\s*$")
WORKFLOW_STEP_COMMAND = re.compile(r"^    command:\s+([A-Za-z0-9_.-]+)\s*$")
REQUIRED_BASH_SCRIPTS = {
    "check-prerequisites.sh",
    "common.sh",
    "create-new-feature.sh",
    "setup-plan.sh",
    "setup-tasks.sh",
}
EXPECTED_SPECKIT_SKILLS = {
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

ALLOWED_SPECIFY_FILES = {
    Path(".specify/feature.json"),
    Path(".specify/init-options.json"),
    Path(".specify/integration.json"),
    Path(".specify/speckit-lock.json"),
    Path(".specify/integrations/claude.manifest.json"),
    Path(".specify/integrations/codex.manifest.json"),
    Path(".specify/integrations/speckit.manifest.json"),
    Path(".specify/memory/constitution.md"),
    *{Path(".specify/scripts/bash") / name for name in REQUIRED_BASH_SCRIPTS},
    Path(".specify/templates/checklist-template.md"),
    Path(".specify/templates/constitution-template.md"),
    Path(".specify/templates/plan-template.md"),
    Path(".specify/templates/spec-template.md"),
    Path(".specify/templates/tasks-template.md"),
    Path(".specify/workflows/nunchi-plan/workflow.yml"),
    Path(".specify/workflows/speckit/workflow.yml"),
    Path(".specify/workflows/workflow-registry.json"),
}
ALLOWED_WORKFLOW_RUN_FILES = {
    "inputs.json",
    "log.jsonl",
    "nunchi-binding.json",
    "state.json",
    "workflow.yml",
}

EXPECTED_WORKFLOW_STEPS = {
    "nunchi-plan": (
        "bind-existing-slice",
        "review-spec",
        "clarify",
        "plan",
        "review-plan",
        "checklist",
        "tasks",
        "analyze",
        "planning-exit",
    ),
    "speckit": (
        "bind-existing-slice",
        "review-spec",
        "clarify",
        "plan",
        "review-plan",
        "checklist",
        "tasks",
        "analyze",
        "review-analysis",
        "implementation-authorization",
        "slice-readiness",
        "activate-slice",
        "implement",
        "converge",
        "record-convergence",
        "documentation-freshness",
        "prepare-handoff",
        "slice-handoff",
    ),
}
EXPECTED_WORKFLOW_COMMANDS = {
    "clarify": "speckit.clarify",
    "plan": "speckit.plan",
    "checklist": "speckit.checklist",
    "tasks": "speckit.tasks",
    "analyze": "speckit.analyze",
    "implement": "speckit.implement",
    "converge": "speckit.converge",
}
RETRYABLE_WORKFLOW_GATES = {
    "record-convergence",
    "documentation-freshness",
    "prepare-handoff",
    "slice-handoff",
}

EXPECTED_SLICES = {
    "010-v2-contract": {
        "owner": "v2-contract-owner",
        "dependencies": (),
        "feeds": ("020", "030", "040", "050", "060", "070", "080", "090", "100", "110"),
        "branch": "v2/contract",
        "worktree": ".worktrees/v2-contract/",
    },
    "020-v2-observation": {
        "owner": "v2-observation-owner",
        "dependencies": ("010",),
        "feeds": ("040", "050", "060", "070", "080", "090", "100", "110"),
        "branch": "v2/observation",
        "worktree": ".worktrees/v2-observation/",
    },
    "030-v2-core-attention": {
        "owner": "v2-core-owner",
        "dependencies": ("010",),
        "feeds": ("040", "060", "070", "080", "090", "100", "110"),
        "branch": "v2/core-attention",
        "worktree": ".worktrees/v2-core-attention/",
    },
    "040-v2-participant-wake": {
        "owner": "v2-wake-owner",
        "dependencies": ("010", "020", "030"),
        "feeds": ("060", "070", "080", "090", "100", "110"),
        "branch": "v2/participant-wake",
        "worktree": ".worktrees/v2-participant-wake/",
    },
    "050-v2-discord-transport": {
        "owner": "v2-transport-owner",
        "dependencies": ("010", "020"),
        "feeds": ("070", "080", "100", "110"),
        "branch": "v2/discord-transport",
        "worktree": ".worktrees/v2-discord-transport/",
    },
    "060-v2-hermes": {
        "owner": "v2-hermes-owner",
        "dependencies": ("010", "020", "030", "040"),
        "feeds": ("100", "110"),
        "branch": "v2/hermes",
        "worktree": ".worktrees/v2-hermes/",
    },
    "070-v2-claude-code": {
        "owner": "v2-claude-owner",
        "dependencies": ("010", "020", "030", "040", "050"),
        "feeds": ("100", "110"),
        "branch": "v2/claude-code",
        "worktree": ".worktrees/v2-claude-code/",
    },
    "080-v2-codex": {
        "owner": "v2-codex-owner",
        "dependencies": ("010", "020", "030", "040", "050"),
        "feeds": ("100", "110"),
        "branch": "v2/codex",
        "worktree": ".worktrees/v2-codex/",
    },
    "090-v2-channel-adapters": {
        "owner": "v2-adapters-owner",
        "dependencies": ("010", "020", "030", "040"),
        "feeds": ("100", "110"),
        "branch": "v2/channel-adapters",
        "worktree": ".worktrees/v2-channel-adapters/",
    },
    "100-v2-security-provenance": {
        "owner": "v2-security-owner",
        "dependencies": ("010", "020", "030", "040", "050", "060", "070", "080", "090"),
        "feeds": ("110",),
        "branch": "v2/security-provenance",
        "worktree": ".worktrees/v2-security-provenance/",
    },
    "110-v2-parity-cutover": {
        "owner": "v2-integrator",
        "dependencies": (
            "010",
            "020",
            "030",
            "040",
            "050",
            "060",
            "070",
            "080",
            "090",
            "100",
        ),
        "feeds": (),
        "branch": "integration/v2",
        "worktree": ".worktrees/v2-integration/",
    },
}

EXPECTED_ACTIVATION_PATHS = {
    "010-v2-contract": "evidence/v2/contract/slice-activation.md",
    "020-v2-observation": "evidence/v2/observation/slice-activation.md",
    "030-v2-core-attention": "evidence/v2/attention/slice-activation.md",
    "040-v2-participant-wake": "evidence/v2/participant/slice-activation.md",
    "050-v2-discord-transport": "evidence/v2/discord-transport/slice-activation.md",
    "060-v2-hermes": "evidence/v2/hermes/slice-activation.md",
    "070-v2-claude-code": "evidence/v2/claude-code/slice-activation.md",
    "080-v2-codex": "evidence/v2/codex/slice-activation.md",
    "090-v2-channel-adapters": "evidence/v2/adapters/slice-activation.md",
    "100-v2-security-provenance": "evidence/v2/security/slice-activation.md",
    "110-v2-parity-cutover": "evidence/v2/parity/slice-activation.md",
}

EXPECTED_LIFECYCLE_PATHS = {
    dirname: {
        "activation": activation,
        "candidate": str(Path(activation).with_name("slice-candidate.md")),
        "handoff": str(Path(activation).with_name("slice-handoff.md")),
        "acceptance": str(Path(activation).with_name("slice-acceptance.md")),
        "amendments": str(Path(activation).with_name("slice-amendments.md")),
    }
    for dirname, activation in EXPECTED_ACTIVATION_PATHS.items()
}
CUTOVER_ACCEPTANCE_PATH = Path("evidence/v2/parity/cutover-acceptance.md")
POST_MERGE_VERIFICATION_PATH = Path("evidence/v2/parity/post-merge-verification.md")
PLANNING_BASELINE_PATH = Path(
    "evidence/governance/slice-lifecycle-amendment-2026-07-11.md"
)

CANONICAL_INTERFACES = {
    "I-010A": "010-v2-contract",
    "I-010B": "010-v2-contract",
    "I-010C": "010-v2-contract",
    "I-010D": "010-v2-contract",
    "I-010E": "010-v2-contract",
    "I-020A": "020-v2-observation",
    "I-030A": "030-v2-core-attention",
    "I-040A": "040-v2-participant-wake",
    "I-050A": "050-v2-discord-transport",
}

REQUIRED_PLAN_SECTIONS = {
    "## Slice Interfaces",
    "## Integration Strategy",
    "## Acceptance Scenes and Evidence",
    "## Documentation Impact and Freshness",
    "## Ordinary Repository Targets",
    "## Owner Handoff",
}
REQUIRED_SPEC_SECTIONS = {
    "## Control-Plane Boundary",
    "## Interface Summary",
    "## Documentation Freshness",
    "## User Scenarios & Testing",
    "## Requirements",
    "## Success Criteria",
    "## Explicit Exclusions",
}
PLANNING_PLACEHOLDER = re.compile(
    r"\[NEEDS CLARIFICATION\]|\[FEATURE(?: NAME)?\]|\[DATE\]|\[###-[^]]+\]|"
    r"\bTXXX\b|\bTODO\b|\bTBD\b",
    re.IGNORECASE,
)
TASK_LINE = re.compile(r"^- \[ \] T(\d{3})(?: \[P\])?(?: \[US\d+\])? .+$")
INTERFACE_ID = re.compile(r"\bI-\d{3}[A-Z]\b")
SCENE_ID = re.compile(r"\bS(?:0[1-9]|1[0-6])\b")

EXPECTED_DOCUMENTATION_PATHS = {
    "010-v2-contract": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/contracts/channel-adapter-v1.md",
        "docs/contracts/nunchi-v2.md",
        "docs/integration.md",
        "docs/STABILITY.md",
    },
    "020-v2-observation": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/integration.md",
        "docs/observation/v2.md",
        "docs/STABILITY.md",
        "integrations/claude-code/README.md",
        "integrations/codex/README.md",
        "integrations/hermes/README.md",
        "integrations/mcp-discord/DESIGN.md",
        "integrations/mcp-discord/README.md",
    },
    "030-v2-core-attention": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/attention/v2.md",
        "docs/contracts/channel-adapter-v1.md",
        "docs/contracts/verdict-suite-data-model-v1.md",
        "docs/contracts/verdict-suite-requirements-v1.md",
        "docs/evaluations/verdict-suite-runner.md",
        "docs/evaluations/verdict-suite.md",
        "docs/INSTALL.md",
        "docs/integration.md",
        "docs/STABILITY.md",
        "integrations/claude-code/DEFER_EVAL.md",
        "integrations/claude-code/README.md",
        "integrations/codex/README.md",
        "integrations/hermes/README.md",
        "integrations/mcp-discord/DESIGN.md",
        "integrations/mcp-discord/README.md",
    },
    "040-v2-participant-wake": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/contracts/channel-adapter-v1.md",
        "docs/integration.md",
        "docs/participant/v2.md",
        "docs/STABILITY.md",
        "integrations/claude-code/DEFER_EVAL.md",
        "integrations/claude-code/README.md",
        "integrations/claude-code/transport-patch/README.md",
        "integrations/codex/README.md",
        "integrations/hermes/README.md",
        "integrations/mcp-discord/DESIGN.md",
        "integrations/mcp-discord/README.md",
    },
    "050-v2-discord-transport": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/integrations/discord-mcp-v2.md",
        "integrations/claude-code/transport-patch/README.md",
        "integrations/codex/README.md",
        "integrations/mcp-discord/DESIGN.md",
        "integrations/mcp-discord/README.md",
    },
    "060-v2-hermes": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/INSTALL.md",
        "docs/integration.md",
        "docs/integrations/hermes-core-patch-test-plan.md",
        "docs/integrations/hermes-core-patch.md",
        "docs/integrations/hermes-v2.md",
        "integrations/hermes/README.md",
    },
    "070-v2-claude-code": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/INSTALL.md",
        "docs/integration.md",
        "docs/integrations/claude-code-v2.md",
        "integrations/claude-code/DEFER_EVAL.md",
        "integrations/claude-code/README.md",
        "integrations/claude-code/transport-patch/README.md",
    },
    "080-v2-codex": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/integration.md",
        "docs/integrations/codex-v2.md",
        "integrations/codex/README.md",
        "integrations/mcp-discord/README.md",
    },
    "090-v2-channel-adapters": {
        "CHANGELOG.md",
        "README.md",
        "docs/adapters-v2.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/contracts/channel-adapter-v1.md",
        "docs/integration.md",
        "docs/STABILITY.md",
    },
    "100-v2-security-provenance": {
        "CHANGELOG.md",
        "README.md",
        "SECURITY.md",
        "docs/architecture/v2-selected-design.md",
        "docs/INSTALL.md",
        "docs/integration.md",
        "docs/security/assurance-handoffs.md",
        "docs/security/operational-safety.md",
        "docs/security/runtime-provenance.md",
        "docs/security/suppression-governance.md",
        "docs/security/threat-model-v2.md",
        "docs/STABILITY.md",
    },
    "110-v2-parity-cutover": {
        "AGENTS.md",
        "CHANGELOG.md",
        "CLAUDE.md",
        "README.md",
        "SECURITY.md",
        "docs/INSTALL.md",
        "docs/STABILITY.md",
        "docs/adapters-v2.md",
        "docs/adapters.md",
        "docs/architecture/v2-selected-design.md",
        "docs/archive/v1/README.md",
        "docs/attention/v2.md",
        "docs/contracts/channel-adapter-v1.md",
        "docs/contracts/nunchi-v2.md",
        "docs/contracts/verdict-suite-data-model-v1.md",
        "docs/contracts/verdict-suite-requirements-v1.md",
        "docs/evaluations/v2-parity.md",
        "docs/evaluations/verdict-suite-runner.md",
        "docs/evaluations/verdict-suite.md",
        "docs/governance/execution-spine.md",
        "docs/integration.md",
        "docs/integrations/claude-code-v2.md",
        "docs/integrations/codex-v2.md",
        "docs/integrations/discord-mcp-v2.md",
        "docs/integrations/hermes-core-patch-test-plan.md",
        "docs/integrations/hermes-core-patch.md",
        "docs/integrations/hermes-v2.md",
        "docs/observation/v2.md",
        "docs/participant/v2.md",
        "docs/releases/v2-readiness.md",
        "docs/security/assurance-handoffs.md",
        "docs/security/operational-safety.md",
        "docs/security/runtime-provenance.md",
        "docs/security/suppression-governance.md",
        "docs/security/threat-model-v2.md",
        "integrations/claude-code/DEFER_EVAL.md",
        "integrations/claude-code/README.md",
        "integrations/claude-code/transport-patch/README.md",
        "integrations/codex/README.md",
        "integrations/hermes/README.md",
        "integrations/mcp-discord/DESIGN.md",
        "integrations/mcp-discord/README.md",
    },
}


def _json(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: cannot read valid JSON ({exc})")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path}: expected a JSON object")
        return {}
    return value


def check_pin(root: Path) -> list[str]:
    errors: list[str] = []
    specify = root / ".specify"
    options = _json(specify / "init-options.json", errors)
    if options.get("speckit_version") != PINNED_SPECKIT_VERSION:
        errors.append(
            ".specify/init-options.json: speckit_version must be "
            f"{PINNED_SPECKIT_VERSION!r}"
        )

    lock = _json(specify / "speckit-lock.json", errors)
    expected_lock = {
        "schema_version": 1,
        "package": "specify-cli",
        "version": PINNED_SPECKIT_VERSION,
        "source": "https://github.com/github/spec-kit.git",
        "tag": f"v{PINNED_SPECKIT_VERSION}",
        "commit": PINNED_SPECKIT_COMMIT,
    }
    if lock != expected_lock:
        errors.append(".specify/speckit-lock.json: immutable upstream pin mismatch")

    integration = _json(specify / "integration.json", errors)
    if integration.get("version") != PINNED_SPECKIT_VERSION:
        errors.append(".specify/integration.json: version does not match the pin")
    installed = set(integration.get("installed_integrations", []))
    if installed != {"codex", "claude"}:
        errors.append(
            ".specify/integration.json: installed integrations must be exactly "
            "codex and claude"
        )
    if integration.get("default_integration") != "codex":
        errors.append(
            ".specify/integration.json: Codex must be the default integration"
        )

    for name in ("codex", "claude", "speckit"):
        manifest_relative = Path(
            f".specify/integrations/{name}.manifest.json"
        )
        manifest = _json(root / manifest_relative, errors)
        if manifest.get("integration") != name:
            errors.append(f"{manifest_relative}: integration identity mismatch")
        if manifest.get("version") != PINNED_SPECKIT_VERSION:
            errors.append(
                f"{manifest_relative}: version mismatch"
            )
        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            errors.append(f"{manifest_relative}: files must be a nonempty object")
            continue
        if name in {"codex", "claude"}:
            integration_root = ".agents" if name == "codex" else ".claude"
            expected_files = {
                f"{integration_root}/skills/{skill}/SKILL.md"
                for skill in EXPECTED_SPECKIT_SKILLS
            }
            if set(files) != expected_files:
                errors.append(
                    f"{manifest_relative}: must pin the exact installed skill set"
                )
        for relative_text, expected_digest in sorted(files.items()):
            if (
                not isinstance(relative_text, str)
                or not isinstance(expected_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
            ):
                errors.append(f"{manifest_relative}: invalid file digest entry")
                continue
            relative = Path(relative_text)
            if not _repo_path_is_safe(root, relative, require_file=True):
                errors.append(
                    f"{manifest_relative}: unsafe or missing file {relative_text!r}"
                )
                continue
            observed_digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
            if observed_digest != expected_digest:
                errors.append(
                    f"{manifest_relative}: installed file digest mismatch for "
                    f"{relative_text}"
                )

    for workflow in (
        specify / "workflows" / "speckit" / "workflow.yml",
        specify / "workflows" / "nunchi-plan" / "workflow.yml",
    ):
        try:
            text = workflow.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{workflow}: cannot read ({exc})")
            continue
        required = f'speckit_version: "=={PINNED_SPECKIT_VERSION}"'
        if required not in text:
            errors.append(f"{workflow}: workflow must require exact SpecKit pin")

    for obsolete in (specify / "extensions", specify / "extensions.yml"):
        if obsolete.exists() or obsolete.is_symlink():
            errors.append(f"{obsolete}: obsolete extension installation must be absent")

    for integration_root in (root / ".agents" / "skills", root / ".claude" / "skills"):
        observed = {
            path.name for path in integration_root.glob("speckit-*") if path.is_dir()
        }
        if observed != EXPECTED_SPECKIT_SKILLS:
            errors.append(
                f"{integration_root}: SpecKit skill set must match pinned clean install; "
                f"missing={sorted(EXPECTED_SPECKIT_SKILLS - observed)}, "
                f"extra={sorted(observed - EXPECTED_SPECKIT_SKILLS)}"
            )

    return errors


def check_control_plane(root: Path) -> list[str]:
    errors: list[str] = []
    specs = root / "specs"
    allowed_spec_paths = {Path("specs/README.md")}
    for dirname in EXPECTED_SLICES:
        allowed_spec_paths.update(
            {
                Path("specs") / dirname / "spec.md",
                Path("specs") / dirname / "plan.md",
                Path("specs") / dirname / "tasks.md",
                Path("specs") / dirname / "checklists" / "requirements.md",
            }
        )
    program = Path("specs/001-nunchi-v2-program")
    allowed_spec_paths.update(
        {
            program / "spec.md",
            program / "plan.md",
            program / "tasks.md",
            program / "research.md",
            program / "checklists" / "requirements.md",
            program / "checklists" / "program-readiness.md",
        }
    )
    if specs.exists():
        for path in specs.rglob("*"):
            rel = path.relative_to(root)
            if path.is_symlink():
                errors.append(f"{rel}: symlinks are forbidden in the control plane")
                continue
            if path.is_dir():
                if FORBIDDEN_SPEC_PARTS.intersection(rel.parts):
                    errors.append(
                        f"{rel}: product-artifact directory is forbidden under specs/"
                    )
                continue
            if FORBIDDEN_SPEC_PARTS.intersection(rel.parts):
                errors.append(f"{rel}: product artifact is forbidden under specs/")
                continue
            if "checklists" in rel.parts:
                if path.suffix != ".md":
                    errors.append(
                        f"{rel}: checklist artifacts must be Markdown planning files"
                    )
                elif rel not in allowed_spec_paths:
                    errors.append(
                        f"{rel}: checklist is outside the exact slice/program planning allowlist"
                    )
                continue
            if path.name not in ALLOWED_SPEC_FILES:
                errors.append(
                    f"{rel}: only spec/plan/tasks/research/README and checklist Markdown "
                    "are allowed under specs/"
                )
            elif rel not in allowed_spec_paths:
                errors.append(
                    f"{rel}: file is outside the exact slice/program planning allowlist"
                )

    specify = root / ".specify"
    if specify.exists():
        for path in specify.rglob("*"):
            rel = path.relative_to(root)
            if path.is_symlink():
                errors.append(
                    f"{rel}: managed control-plane paths may not symlink product assets"
                )
                continue
            if path.is_dir() or rel in ALLOWED_SPECIFY_FILES:
                continue
            parts = rel.parts
            is_run_file = (
                len(parts) == 5
                and parts[:3] == (".specify", "workflows", "runs")
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", parts[3])
                and parts[4] in ALLOWED_WORKFLOW_RUN_FILES
            )
            if not is_run_file:
                errors.append(
                    f"{rel}: file is outside the exact .specify control-plane allowlist"
                )

    for integration in (".agents", ".claude"):
        skill_root = root / integration / "skills"
        if not skill_root.exists():
            continue
        for path in skill_root.glob("speckit-*"):
            rel = path.relative_to(root)
            if path.is_symlink():
                errors.append(
                    f"{rel}: managed control-plane paths may not symlink product assets"
                )
                continue
            if path.name not in EXPECTED_SPECKIT_SKILLS or not path.is_dir():
                errors.append(f"{rel}: unexpected installed SpecKit skill path")
                continue
            for child in path.rglob("*"):
                child_rel = child.relative_to(root)
                if child.is_symlink():
                    errors.append(
                        f"{child_rel}: managed control-plane paths may not symlink product assets"
                    )
                elif child.is_dir() or child.name != "SKILL.md" or child.parent != path:
                    errors.append(
                        f"{child_rel}: installed SpecKit skills may contain only SKILL.md"
                    )
    return errors


def check_governance_documents(root: Path) -> list[str]:
    """Require the customized constitution and templates that stock init cannot supply."""

    errors: list[str] = []
    required_tokens = {
        ".specify/memory/constitution.md": (
            f"**Version**: {PINNED_CONSTITUTION_VERSION}",
            PINNED_VAULT_COMMIT,
            "SpecKit Is Control-Plane Only (NON-NEGOTIABLE)",
            "Trusted preattention-disabled configuration MUST bypass model judgment",
            "Receipt records MUST be immutable and request-correlated",
            "## Documentation Freshness Gate",
            "Each reviewed documentation surface MUST receive exactly one disposition",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "## Program and Slice Lifecycle Gates",
            "PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY -> ACCEPTED",
            "evidence/governance/assignments/<record>.md",
            "Dependency acceptance references",
            "append-only attempt streams",
            "directory wildcard or generic path is",
        ),
        ".specify/scripts/bash/common.sh": (
            "explicit environment binding is invocation-local",
            "Never persist it",
        ),
        ".agents/skills/speckit-plan/SKILL.md": (
            "Nunchi Existing-Slice Override (NON-NEGOTIABLE)",
            "MUST update its existing `plan.md` only",
            "MUST NOT create or replace a feature",
            "**Output**: the existing `plan.md` only",
        ),
        ".claude/skills/speckit-plan/SKILL.md": (
            "Nunchi Existing-Slice Override (NON-NEGOTIABLE)",
            "MUST update its existing `plan.md` only",
            "MUST NOT create or replace a feature",
            "**Output**: the existing `plan.md` only",
        ),
        ".agents/skills/speckit-converge/SKILL.md": (
            "## Nunchi Active-Correction Contract",
            "keep the slice `ACTIVE`",
            "run speckit specs/<same-exact-slice>",
            "handoff rejection or a second activation",
        ),
        ".claude/skills/speckit-converge/SKILL.md": (
            "## Nunchi Active-Correction Contract",
            "keep the slice `ACTIVE`",
            "run speckit specs/<same-exact-slice>",
            "handoff rejection or a second activation",
        ),
        ".specify/templates/plan-template.md": (
            "**SpecKit binding**:",
            "**Read-only preflight**:",
            "**Slice state**:",
            "**Program implementation authority**:",
            "Aggregate records MUST carry stable scene and",
            "scene-to-record result manifest",
            "## Documentation Impact and Freshness",
            "The `README.md` row is mandatory",
            "Generic directory rows are invalid",
            "Dependency acceptance mapping",
        ),
        ".specify/templates/spec-template.md": (
            "**SpecKit binding**:",
            "**Read-only preflight**:",
            "**Slice state**:",
            "**Program implementation authority**:",
            "## Documentation Freshness *(mandatory)*",
            "Every implementation MUST review `README.md`",
            "Generic directories or wildcards",
            "Delegated by: Zoe",
        ),
        ".specify/templates/tasks-template.md": (
            "activation records document prerequisites but never grant authority",
            "**SpecKit binding**:",
            "**Read-only preflight**:",
            "**Slice state**:",
            "**Program implementation authority**:",
            "A unit-only social-quality claim is invalid",
            "Documentation is a blocking implementation task",
            "documentation-freshness gate passes",
            "every exact row in `plan.md` §Documentation Impact and Freshness",
            "Candidate and handoff files are append-only attempt streams",
        ),
        ".specify/templates/checklist-template.md": (
            "python3 scripts/run_slice_workflow.py run <nunchi-plan|speckit>",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "outside slice `110`",
            "Mandatory `README.md` and affected-docs freshness dispositions",
            "Reject a bare `NO_IMPACT`",
            "Reject a directory wildcard",
            "slice=full-sha",
        ),
        "AGENTS.md": (
            "SpecKit-managed paths are control plane only",
            "Trusted preattention bypass wakes directly",
            PINNED_VAULT_COMMIT,
            "## Documentation freshness",
            "Use exactly one disposition per reviewed surface",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "scripts/run_slice_workflow.py run speckit",
            "scripts/run_slice_workflow.py resume <run-id>",
        ),
        "CLAUDE.md": (
            "continuation authority out of classifier input",
            "immutable singly",
            "documentation-freshness gate",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "scripts/run_slice_workflow.py run speckit",
            "scripts/run_slice_workflow.py resume <run-id>",
        ),
        "README.md": (
            "post-convergence documentation-freshness gate",
            "evidence-backed `NO_IMPACT`",
            "directory wildcard does not satisfy the gate",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "scripts/run_slice_workflow.py run speckit",
            "scripts/run_slice_workflow.py resume <run-id>",
        ),
        "docs/governance/execution-spine.md": (
            "## Documentation freshness",
            "The workflow's `documentation-freshness` gate",
            "## Participant action contract",
            "### Transition evidence schema",
            "Dependency commits",
            "Dependency acceptance references",
            "slice-acceptance.md",
            "scripts/run_slice_workflow.py run speckit",
            "scripts/run_slice_workflow.py resume <run-id>",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
        ),
        "evidence/governance/slice-lifecycle-amendment-2026-07-11.md": (
            "# Slice-centric execution-spine amendment",
            "PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "There is no central mutable",
            "It does not grant authority",
            "append-only attempt streams",
            "scripts/run_slice_workflow.py resume <run-id>",
        ),
    }
    for relative, tokens in required_tokens.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{relative}: cannot read governance document ({exc})")
            continue
        for token in tokens:
            if token not in text:
                errors.append(f"{relative}: missing required governance text {token!r}")

    tasks_template = root / ".specify" / "templates" / "tasks-template.md"
    if tasks_template.is_file():
        text = tasks_template.read_text(encoding="utf-8")
        for forbidden in (
            "Tests are OPTIONAL",
            "Record "
            + "Goal 2"
            + " authorization and dependency readiness in this task file",
        ):
            if forbidden in text:
                errors.append(
                    ".specify/templates/tasks-template.md: stock template contradicts "
                    f"Nunchi governance ({forbidden!r})"
                )
    return errors


def check_historical_evidence(root: Path) -> list[str]:
    """Reject rewrites of immutable governance observations."""

    errors: list[str] = []
    for relative, expected_digest in HISTORICAL_EVIDENCE_HASHES.items():
        path = root / relative
        try:
            canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
            digest = hashlib.sha256(canonical_bytes).hexdigest()
        except OSError as exc:
            errors.append(
                f"{relative}: immutable historical evidence is unreadable ({exc})"
            )
            continue
        if digest != expected_digest:
            errors.append(
                f"{relative}: immutable historical evidence changed; add a dated "
                "amendment instead"
            )
    return errors


def _workflow_steps(
    text: str,
) -> tuple[
    tuple[tuple[str, str | None], ...],
    tuple[str, ...],
    dict[str, str],
]:
    """Parse Nunchi's deliberately strict block-style workflow step surface."""

    lines = text.splitlines()
    try:
        start = lines.index("steps:") + 1
    except ValueError:
        return (), ("missing exact block-style steps section",), {}

    blocks: list[list[str]] = []
    parsing_steps = False
    errors: list[str] = []
    for line in lines[start:]:
        if line.startswith("  - "):
            parsing_steps = True
            if not WORKFLOW_STEP_ID.fullmatch(line):
                errors.append(
                    f"non-canonical or inline workflow step is forbidden: {line!r}"
                )
                blocks.append([line])
            else:
                blocks.append([line])
            continue
        if parsing_steps and line and not line.startswith("    "):
            errors.append(f"unexpected top-level content after steps: {line!r}")
            continue
        if blocks:
            blocks[-1].append(line)

    steps: list[tuple[str, str | None]] = []
    block_texts: dict[str, str] = {}
    allowed_gate_keys = {"id", "type", "message", "options", "on_reject"}
    allowed_command_keys = {"id", "command", "integration", "input"}
    for block in blocks:
        id_match = WORKFLOW_STEP_ID.fullmatch(block[0])
        if not id_match:
            continue
        step_id = id_match.group(1)
        if step_id in block_texts:
            errors.append(f"duplicate workflow step id is forbidden: {step_id!r}")
        block_texts[step_id] = "\n".join(block)
        command: str | None = None
        keys: list[str] = ["id"]
        nested_keys: list[str] = []
        for line in block[1:]:
            key_match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if key_match:
                keys.append(key_match.group(1))
            nested_match = re.fullmatch(r"      ([A-Za-z0-9_-]+):.*", line)
            if nested_match:
                nested_keys.append(nested_match.group(1))
            command_match = WORKFLOW_STEP_COMMAND.fullmatch(line)
            if command_match:
                command = command_match.group(1)
            if re.match(r"\s*(?:run|shell):", line):
                errors.append(f"step {step_id!r} may not contain shell/run actions")
        duplicates = sorted(key for key in set(keys) if keys.count(key) > 1)
        if duplicates:
            errors.append(f"step {step_id!r} has duplicate YAML keys {duplicates}")
        nested_duplicates = sorted(
            key for key in set(nested_keys) if nested_keys.count(key) > 1
        )
        if nested_duplicates:
            errors.append(
                f"step {step_id!r} has duplicate nested YAML keys {nested_duplicates}"
            )
        block_text = "\n".join(block)
        if "&" in block_text or "*" in block_text or "<<:" in block_text:
            errors.append(f"step {step_id!r} may not use YAML aliases or merges")
        if command is None:
            if set(keys) != allowed_gate_keys:
                errors.append(
                    f"gate step {step_id!r} keys must be exactly "
                    f"{sorted(allowed_gate_keys)}; observed {sorted(set(keys))}"
                )
            expected_rejection = (
                "retry" if step_id in RETRYABLE_WORKFLOW_GATES else "abort"
            )
            for required in (
                "    type: gate",
                "    options: [approve, reject]",
                f"    on_reject: {expected_rejection}",
            ):
                if required not in block:
                    errors.append(
                        f"gate step {step_id!r} must contain {required.strip()!r}"
                    )
            if nested_keys:
                errors.append(f"gate step {step_id!r} may not have nested mappings")
        else:
            if set(keys) != allowed_command_keys:
                errors.append(
                    f"command step {step_id!r} keys must be exactly "
                    f"{sorted(allowed_command_keys)}; observed {sorted(set(keys))}"
                )
            if nested_keys != ["args"] or "    input:" not in block:
                errors.append(
                    f"command step {step_id!r} input must contain exactly one args key"
                )
        steps.append((step_id, command))
    return tuple(steps), tuple(errors), block_texts


def _workflow_header_errors(text: str) -> list[str]:
    """Reject duplicate mapping keys in the non-step workflow header."""

    errors: list[str] = []
    if text.splitlines().count("steps:") != 1:
        errors.append("workflow must contain exactly one block-style steps key")
    header = text.split("\nsteps:", 1)[0]
    ancestors: dict[int, str] = {}
    seen: set[tuple[tuple[str, ...], int, str]] = set()
    for line in header.splitlines():
        match = re.fullmatch(r"( *)([A-Za-z0-9_-]+):(?:.*)", line)
        if not match:
            continue
        indent = len(match.group(1))
        key = match.group(2)
        for level in tuple(ancestors):
            if level >= indent:
                del ancestors[level]
        parent = tuple(
            value for level, value in sorted(ancestors.items()) if level < indent
        )
        marker = (parent, indent, key)
        if marker in seen:
            errors.append(
                f"duplicate YAML key {key!r} under {'/'.join(parent) or '<root>'}"
            )
        seen.add(marker)
        ancestors[indent] = key
    return errors


def check_workflow_surface(root: Path) -> list[str]:
    """Require runnable helpers and a skill for each workflow command."""

    errors: list[str] = []
    slice_preflight = root / "scripts" / "check_slice_binding.py"
    if not slice_preflight.is_file():
        errors.append(
            "scripts/check_slice_binding.py: exact-slice preflight is missing"
        )
    slice_runner = root / "scripts" / "run_slice_workflow.py"
    if not slice_runner.is_file():
        errors.append("scripts/run_slice_workflow.py: bound workflow runner is missing")
    scripts = root / ".specify" / "scripts" / "bash"
    for name in sorted(REQUIRED_BASH_SCRIPTS):
        path = scripts / name
        if not path.is_file():
            errors.append(
                f"{path.relative_to(root)}: required SpecKit helper is missing"
            )
        elif path.stat().st_mode & 0o111 == 0:
            errors.append(
                f"{path.relative_to(root)}: SpecKit helper must be executable"
            )

    workflows = {
        "nunchi-plan": root / ".specify" / "workflows" / "nunchi-plan" / "workflow.yml",
        "speckit": root / ".specify" / "workflows" / "speckit" / "workflow.yml",
    }
    contents: dict[str, str] = {}
    for name, path in workflows.items():
        try:
            contents[name] = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{path.relative_to(root)}: cannot read workflow ({exc})")
            continue
        errors.extend(
            f"{path.relative_to(root)}: {error}"
            for error in _workflow_header_errors(contents[name])
        )
        for command in WORKFLOW_COMMAND.findall(contents[name]):
            skill = command.replace(".", "-")
            for integration in (".agents", ".claude"):
                skill_file = root / integration / "skills" / skill / "SKILL.md"
                if not skill_file.is_file():
                    errors.append(
                        f"{path.relative_to(root)}: command {command!r} has no "
                        f"installed {integration} skill {skill!r}"
                    )
        observed_steps, parse_errors, step_blocks = _workflow_steps(contents[name])
        errors.extend(f"{path.relative_to(root)}: {error}" for error in parse_errors)
        observed_ids = tuple(step_id for step_id, _command in observed_steps)
        if observed_ids != EXPECTED_WORKFLOW_STEPS[name]:
            errors.append(
                f"{path.relative_to(root)}: workflow steps must be exactly "
                f"{EXPECTED_WORKFLOW_STEPS[name]}; observed {observed_ids}"
            )
        for step_id, command in observed_steps:
            expected_command = EXPECTED_WORKFLOW_COMMANDS.get(step_id)
            if expected_command is not None and command != expected_command:
                errors.append(
                    f"{path.relative_to(root)}: step {step_id!r} must invoke "
                    f"{expected_command!r}; observed {command!r}"
                )
            if expected_command is None and command is not None:
                errors.append(
                    f"{path.relative_to(root)}: gate step {step_id!r} must not invoke "
                    f"unexpected command {command!r}"
                )

        required_step_text = {
            "bind-existing-slice": (
                "scripts/run_slice_workflow.py",
                "pins the run input and workflow digest",
                "Resume only through the same wrapper",
            ),
        }
        if name == "speckit":
            required_step_text.update(
                {
                    "implementation-authorization": (
                        str(IMPLEMENTATION_AUTHORIZATION_PATH),
                        "exactly all eleven slices 010-110",
                        "does not grant it",
                    ),
                    "slice-readiness": (
                        "Dependency commits",
                        "Dependency acceptance references",
                        "already ACTIVE",
                        "latest handoff attempt is REJECTED",
                        "Convergence-appended tasks or a failed implementation",
                    ),
                    "activate-slice": (
                        "retain the original activation record",
                        "already ACTIVE",
                    ),
                    "documentation-freshness": (
                        "exact candidate",
                        "README.md",
                    ),
                    "record-convergence": (
                        "converge appended no tasks",
                        "start a new bound speckit run",
                    ),
                    "slice-handoff": (
                        "The delivery workflow ends here",
                        "v2-integrator",
                        "REJECTED record",
                        "v2-program-owner",
                    ),
                }
            )
        for step_id, tokens in required_step_text.items():
            block = step_blocks.get(step_id, "")
            for token in tokens:
                if token not in block:
                    errors.append(
                        f"{path.relative_to(root)}: step {step_id!r} must contain "
                        f"{token!r}"
                    )

    planning = contents.get("nunchi-plan", "")
    if "command: speckit.implement" in planning:
        errors.append("nunchi-plan workflow must not contain an implementation command")
    if "command: speckit.specify" in planning:
        errors.append("nunchi-plan workflow must not create a replacement feature")
    if (
        "slice_directory:" not in planning
        or "- id: bind-existing-slice" not in planning
        or "python3 scripts/run_slice_workflow.py run nunchi-plan {{ inputs.slice_directory }}"
        not in planning
        or "pins the run input and workflow digest" not in planning
    ):
        errors.append(
            "nunchi-plan workflow must read-only bind one exact existing slice"
        )

    full = contents.get("speckit", "")
    if "command: speckit.specify" in full:
        errors.append("speckit delivery workflow must operate on an existing slice")
    if (
        "slice_directory:" not in full
        or "required: true" not in full
        or "- id: bind-existing-slice" not in full
        or "python3 scripts/run_slice_workflow.py run speckit {{ inputs.slice_directory }}"
        not in full
        or "pins the run input and workflow digest" not in full
    ):
        errors.append(
            "speckit delivery workflow must require and bind one exact existing slice"
        )

    analysis = full.find("command: speckit.analyze")
    gate = full.find("- id: implementation-authorization")
    readiness = full.find("- id: slice-readiness")
    activation = full.find("- id: activate-slice")
    implementation = full.find("command: speckit.implement")
    convergence = full.find("command: speckit.converge")
    record_convergence = full.find("- id: record-convergence")
    documentation = full.find("- id: documentation-freshness")
    prepare_handoff = full.find("- id: prepare-handoff")
    handoff = full.find("- id: slice-handoff")
    if (
        analysis < 0
        or gate < 0
        or readiness < 0
        or activation < 0
        or implementation < 0
        or convergence < 0
        or record_convergence < 0
        or documentation < 0
        or prepare_handoff < 0
        or handoff < 0
        or not (
            analysis
            < gate
            < readiness
            < activation
            < implementation
            < convergence
            < record_convergence
            < documentation
            < prepare_handoff
            < handoff
        )
    ):
        errors.append(
            "speckit workflow must preserve the complete analyze-through-handoff "
            "slice lifecycle order"
        )
    if str(IMPLEMENTATION_AUTHORIZATION_PATH) not in full:
        errors.append(
            "speckit workflow must require the external implementation-authority record"
        )
    for token, message in (
        (
            "enumerates exactly all eleven slices 010-110",
            "speckit workflow must reject partial program authorization",
        ),
        (
            "Dependency acceptance references",
            "speckit workflow must require exact per-consumer dependency acceptance",
        ),
        (
            "The delivery workflow ends here",
            "speckit workflow must end owner delivery before recipient acceptance",
        ),
        (
            "recorder appends a REJECTED record",
            "speckit workflow must define append-only rejection and rework",
        ),
        (
            "already ACTIVE",
            "speckit workflow must provide executable rework re-entry",
        ),
    ):
        if token.lower() not in full.lower():
            errors.append(message)
    if "Only slice 110 performs integration or cutover" not in full:
        errors.append(
            "speckit workflow must reserve integration and cutover for slice 110"
        )

    registry = _json(root / ".specify" / "workflows" / "workflow-registry.json", errors)
    registered = registry.get("workflows", {})
    expected_versions = {"speckit": "2.5.0", "nunchi-plan": "1.4.0"}
    for name, version in expected_versions.items():
        observed = registered.get(name, {}) if isinstance(registered, dict) else {}
        if observed.get("version") != version:
            errors.append(
                f".specify/workflows/workflow-registry.json: {name} must be version {version}"
            )
    return errors


def _metadata_values(text: str, label: str) -> tuple[str, ...]:
    marker = f"**{label}**:"
    lines = text.splitlines()
    values: list[str] = []
    for index, line in enumerate(lines):
        if not line.startswith(marker):
            continue
        value = line[len(marker) :].strip()
        continuation: list[str] = []
        for following in lines[index + 1 :]:
            if (
                not following.strip()
                or following.startswith("#")
                or following.startswith("**")
            ):
                break
            continuation.append(following.strip())
        values.append(" ".join([value, *continuation]).strip())
    return tuple(values)


def _metadata_value(text: str, label: str, *, last: bool = False) -> str | None:
    values = _metadata_values(text, label)
    if not values:
        return None
    return values[-1] if last else values[0]


def _singleton_metadata_errors(
    text: str,
    labels: tuple[str, ...],
    context: str | Path,
) -> list[str]:
    """Require one and only one attestation for each metadata label."""

    errors: list[str] = []
    for label in labels:
        count = len(_metadata_values(text, label))
        if count != 1:
            errors.append(
                f"{context}: {label} must occur exactly once; observed {count}"
            )
    return errors


def _lifecycle_records(text: str) -> tuple[str, ...]:
    """Split an append-only lifecycle file into its individually attested records."""

    starts = [match.start() for match in re.finditer(r"(?m)^\*\*Slice\*\*:", text)]
    if not starts:
        return ()
    return tuple(
        text[start : starts[index + 1] if index + 1 < len(starts) else len(text)]
        for index, start in enumerate(starts)
    )


def _effective_dependency_commit(
    root: Path,
    upstream: str,
    terminal_commit: str,
    *,
    at_commit: str | None = None,
) -> tuple[str, list[str]]:
    """Resolve the exact commit a dependent slice must bind to for *upstream*.

    A post-acceptance amendment (see the constitution's amendment procedure)
    never appends to `slice-candidate.md`/`slice-handoff.md`/`slice-acceptance.md`
    — those stay pinned to the terminal accepted candidate so an amendment
    cannot reopen or reauthor the slice's own accepted lifecycle. Instead each
    accepted amendment appends one record to a separate canonical
    `slice-amendments.md` ledger. This validates that ledger's chain integrity
    independently (never by parsing narrative `amendment-A*.md` prose) and
    returns the commit downstream slices must now depend on.
    """

    errors: list[str] = []
    amendments_relative = Path(EXPECTED_LIFECYCLE_PATHS[upstream]["amendments"])
    if at_commit is not None:
        text = _git_file_text(root, at_commit, amendments_relative)
        if text is None:
            return terminal_commit, errors
    else:
        raw_path = root / amendments_relative
        if not raw_path.exists() and not raw_path.is_symlink():
            return terminal_commit, errors
        if not _repo_path_is_safe(root, amendments_relative, require_file=True):
            return terminal_commit, [
                f"{amendments_relative}: amendment ledger path is unsafe"
            ]
        try:
            text = raw_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return terminal_commit, [
                f"{amendments_relative}: amendment ledger is unreadable ({exc})"
            ]
    records = _lifecycle_records(text)
    if not records:
        return terminal_commit, [
            f"{amendments_relative}: amendment ledger exists but has no attested "
            "record"
        ]

    seen_ids: set[str] = set()
    interface_versions: dict[str, int] = {}
    previous_effective = terminal_commit
    effective_commit = terminal_commit
    for index, record in enumerate(records, 1):
        prefix = f"{amendments_relative} record {index}"
        if _clean_metadata(record, "Slice") != upstream:
            errors.append(f"{prefix}: Slice must be {upstream!r}")
        if _clean_metadata(record, "Status") != "ACCEPTED":
            errors.append(f"{prefix}: Status must be 'ACCEPTED'")
        amendment_id = _clean_metadata(record, "Amendment ID")
        if not amendment_id:
            errors.append(f"{prefix}: missing Amendment ID")
        elif amendment_id in seen_ids:
            errors.append(f"{prefix}: duplicate Amendment ID {amendment_id!r}")
        seen_ids.add(amendment_id)
        prior_effective = _clean_metadata(record, "Prior effective commit")
        candidate = _clean_metadata(record, "Amendment candidate commit")
        decision = _clean_metadata(record, "Amendment decision commit")
        commit_fields = {
            "Prior effective commit": prior_effective,
            "Amendment candidate commit": candidate,
            "Amendment decision commit": decision,
        }
        for label, value in commit_fields.items():
            if not re.fullmatch(r"[0-9a-f]{40}", value):
                errors.append(f"{prefix}: {label} must be a full Git SHA")
            elif not _git_commit_exists(root, value):
                errors.append(f"{prefix}: {label} does not exist in Git")
        commits_exist = all(
            re.fullmatch(r"[0-9a-f]{40}", value) and _git_commit_exists(root, value)
            for value in commit_fields.values()
        )
        if prior_effective != previous_effective:
            errors.append(
                f"{prefix}: Prior effective commit must be {previous_effective!r} "
                "(the terminal accepted candidate, or the immediately preceding "
                "amendment's candidate)"
            )
        if (
            commits_exist
            and candidate != prior_effective
            and not _git_is_ancestor(root, prior_effective, candidate)
        ):
            errors.append(
                f"{prefix}: Amendment candidate commit must descend from the "
                "Prior effective commit"
            )
        if (
            commits_exist
            and decision != candidate
            and not _git_is_ancestor(root, candidate, decision)
        ):
            errors.append(
                f"{prefix}: Amendment decision commit must descend from the "
                "Amendment candidate commit"
            )
        interface_match = re.search(
            r"I-\d{3}[A-Z]", _clean_metadata(record, "Amended interface")
        )
        if not interface_match:
            errors.append(f"{prefix}: missing concrete Amended interface")
        prior_version = _clean_metadata(record, "Prior interface version")
        new_version = _clean_metadata(record, "New interface version")
        prior_match = re.fullmatch(r"@(\d+)", prior_version)
        new_match = re.fullmatch(r"@(\d+)", new_version)
        if (
            not prior_match
            or not new_match
            or int(new_match.group(1)) != int(prior_match.group(1)) + 1
        ):
            errors.append(
                f"{prefix}: New interface version must be exactly one version "
                "above Prior interface version"
            )
        if interface_match and prior_match:
            interface_key = interface_match.group(0)
            expected_prior = interface_versions.get(interface_key, 1)
            if int(prior_match.group(1)) != expected_prior:
                errors.append(
                    f"{prefix}: Prior interface version for {interface_key} must "
                    f"be @{expected_prior} (its last effective version)"
                )
            if new_match:
                interface_versions[interface_key] = int(new_match.group(1))
        if _clean_metadata(record, "Accepted by") != "v2-integrator":
            errors.append(f"{prefix}: Accepted by must be 'v2-integrator'")
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", _clean_metadata(record, "Accepted on")
        ):
            errors.append(f"{prefix}: Accepted on must be an ISO date")
        decision_reference_path = Path(_clean_metadata(record, "Decision reference"))
        if not _repo_path_is_safe(root, decision_reference_path, require_file=True):
            errors.append(f"{prefix}: Decision reference must name an existing file")
        amendment_record_value = _clean_metadata(record, "Amendment record")
        amendment_record_path = Path(amendment_record_value)
        if not _repo_path_is_safe(root, amendment_record_path, require_file=True):
            errors.append(f"{prefix}: Amendment record must name an existing file")
        elif commits_exist and decision:
            amendment_record_text = _git_file_text(
                root, decision, amendment_record_path
            )
            if amendment_record_text is None:
                errors.append(
                    f"{prefix}: Amendment record is absent from the Amendment "
                    "decision commit"
                )
            else:
                expected_decision_fields = {
                    "Decision": "ACCEPTED",
                    "Accepted candidate": candidate,
                    "Accepted by": "v2-integrator",
                }
                for label, expected_value in expected_decision_fields.items():
                    observed = _clean_metadata(
                        amendment_record_text, label, last=True
                    )
                    if observed != expected_value:
                        errors.append(
                            f"{prefix}: Amendment record at the decision commit "
                            f"must have {label} {expected_value!r}; observed "
                            f"{observed!r}"
                        )
                referenced_decision = _clean_metadata(
                    amendment_record_text, "Decision reference", last=True
                )
                ledger_decision_reference = _clean_metadata(
                    record, "Decision reference"
                )
                if referenced_decision != ledger_decision_reference:
                    errors.append(
                        f"{prefix}: Amendment record's Decision reference at "
                        f"the decision commit must be {ledger_decision_reference!r}"
                        f"; observed {referenced_decision!r}"
                    )
                elif not _repo_path_is_safe(
                    root, Path(referenced_decision), require_file=False
                ) or _git_file_text(
                    root, decision, Path(referenced_decision)
                ) is None:
                    errors.append(
                        f"{prefix}: Amendment record's Decision reference must "
                        "name a file that already exists at the Amendment "
                        "decision commit"
                    )
        if candidate:
            previous_effective = candidate
            effective_commit = candidate
    summary_matches = list(
        re.finditer(
            r"Current effective dependency commit\s*\n+\s*`([0-9a-f]{40})`", text
        )
    )
    if summary_matches and summary_matches[-1].group(1) != effective_commit:
        errors.append(
            f"{amendments_relative}: 'Current effective dependency commit' "
            f"summary must be {effective_commit!r}; observed "
            f"{summary_matches[-1].group(1)!r}"
        )
    return effective_commit, errors


def _slice_ids(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(re.findall(r"(?<!\d)\d{3}(?!\d)", value))


def _task_entries(tasks_text: str) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for line in tasks_text.splitlines():
        if not line.startswith(("- [ ] T", "- [x] T", "- [X] T")):
            continue
        normalized = re.sub(r"^- \[[xX]\]", "- [ ]", line).rstrip()
        match = TASK_LINE.fullmatch(normalized)
        if match:
            entries.append((f"T{match.group(1)}", normalized))
    return tuple(entries)


def _task_manifest(entries: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    ids = ", ".join(task_id for task_id, _line in entries)
    payload = "\n".join(line for _task_id, line in entries) + ("\n" if entries else "")
    return ids, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _checked_task_ids(tasks_text: str) -> tuple[str, ...]:
    """Return only task IDs whose literal canonical checkbox is checked."""

    checked: list[str] = []
    for line in tasks_text.splitlines():
        if not line.startswith(("- [x] T", "- [X] T")):
            continue
        normalized = re.sub(r"^- \[[xX]\]", "- [ ]", line).rstrip()
        match = TASK_LINE.fullmatch(normalized)
        if match:
            checked.append(f"T{match.group(1)}")
    return tuple(checked)


def _candidate_task_completion_errors(
    *,
    tasks_complete: str,
    declared_completed: str,
    committed_tasks: str,
    committed_task_entries: tuple[tuple[str, str], ...],
    prefix: str,
) -> list[str]:
    """Validate candidate completion against literal committed checkboxes."""

    errors: list[str] = []
    valid_ids = {task_id for task_id, _line in committed_task_entries}
    checked_ids = tuple(
        task_id
        for task_id in _checked_task_ids(committed_tasks)
        if task_id in valid_ids
    )
    expected_completed = ", ".join(checked_ids)
    if tasks_complete != "YES":
        errors.append(f"{prefix}: Tasks complete must be 'YES'")
    elif len(checked_ids) != len(committed_task_entries):
        errors.append(
            f"{prefix}: Tasks complete 'YES' requires every committed task checkbox "
            "to be literally checked"
        )
    if declared_completed != expected_completed:
        errors.append(
            f"{prefix}: Completed task IDs must be exactly {expected_completed!r}"
        )
    return errors


def _validated_task_entries(tasks_text: str) -> tuple[tuple[str, str], ...]:
    """Return a complete sequential manifest or fail on any checkbox-shaped line."""

    checkbox_lines = [
        (line_number, line)
        for line_number, line in enumerate(tasks_text.splitlines(), 1)
        if re.match(r"^- \[[ xX]\]", line)
    ]
    entries = _task_entries(tasks_text)
    if len(entries) != len(checkbox_lines):
        invalid = next(
            line_number
            for line_number, line in checkbox_lines
            if not TASK_LINE.fullmatch(re.sub(r"^- \[[xX]\]", "- [ ]", line).rstrip())
        )
        raise ValueError(f"invalid task format at line {invalid}")
    numbers = [int(task_id[1:]) for task_id, _line in entries]
    if not numbers:
        raise ValueError("bound slice has no valid task entries")
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("task IDs must be sequential from T001")
    return entries


def _implementation_authorization_state(root: Path) -> tuple[bool, list[str]]:
    """Return whether external V2 implementation authority is validly recorded."""

    path = root / IMPLEMENTATION_AUTHORIZATION_PATH
    if path.exists() and not _repo_path_is_safe(
        root, IMPLEMENTATION_AUTHORIZATION_PATH
    ):
        return False, [
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: authority evidence path is unsafe"
        ]
    if not path.exists():
        return False, []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, [f"{IMPLEMENTATION_AUTHORIZATION_PATH}: cannot read ({exc})"]

    errors: list[str] = []
    errors.extend(
        _singleton_metadata_errors(
            text,
            (
                "Program",
                "Status",
                "Authorized slices",
                "Authorized by",
                "Authorized on",
                "Starting commit",
                "Commissioned objective",
                "Authority reference",
                "Recorded by",
            ),
            IMPLEMENTATION_AUTHORIZATION_PATH,
        )
    )
    expected = {
        "Program": "001-nunchi-v2-program",
        "Status": "AUTHORIZED",
        "Authorized by": "Zoe",
        "Recorded by": "v2-program-owner",
    }
    for label, value in expected.items():
        observed = (_metadata_value(text, label) or "").strip("`")
        if observed != value:
            errors.append(
                f"{IMPLEMENTATION_AUTHORIZATION_PATH}: {label} must be {value!r}; "
                f"observed {observed!r}"
            )

    expected_slice_ids = tuple(dirname[:3] for dirname in EXPECTED_SLICES)
    authorized_slices_value = _metadata_value(text, "Authorized slices") or ""
    authorized_slices = tuple(
        re.findall(r"(?<!\d)\d{3}(?!\d)", authorized_slices_value)
    )
    if authorized_slices != expected_slice_ids:
        errors.append(
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: Authorized slices must be "
            f"exactly {expected_slice_ids}; observed {authorized_slices}"
        )

    authorized_on = (_metadata_value(text, "Authorized on") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", authorized_on):
        errors.append(
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: Authorized on must be an ISO date"
        )
    starting_commit = (_metadata_value(text, "Starting commit") or "").strip("`")
    if not re.fullmatch(r"[0-9a-f]{40}", starting_commit):
        errors.append(
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: Starting commit must be a full Git SHA"
        )
    elif _git_commit_exists(root, starting_commit) is False:
        errors.append(
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: Starting commit does not exist in Git"
        )
    objective = (_metadata_value(text, "Commissioned objective") or "").strip()
    if len(objective) < 40:
        errors.append(
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: Commissioned objective must record "
            "the externally authorized implementation scope"
        )
    reference = (_metadata_value(text, "Authority reference") or "").strip()
    if len(reference) < 10:
        errors.append(
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: Authority reference must identify "
            "the durable external decision"
        )
    normalized_text = " ".join(text.split())
    if IMPLEMENTATION_AUTHORIZATION_BOUNDARY not in normalized_text:
        errors.append(
            f"{IMPLEMENTATION_AUTHORIZATION_PATH}: missing non-self-authorizing and "
            "non-cutover boundary statement"
        )
    return not errors, errors


def _checked_slice_task_errors(
    feature: Path,
    tasks_text: str,
    implementation_authorized: bool,
    slice_state: str,
    activation_exists: bool,
) -> list[str]:
    """Reject completed product tasks until one bound slice is actually active."""

    completed = [
        (line_number, line)
        for line_number, line in enumerate(tasks_text.splitlines(), 1)
        if line.startswith("- [x] T") or line.startswith("- [X] T")
    ]
    if not completed:
        return []

    errors: list[str] = []
    for line_number, _line in completed:
        if not implementation_authorized:
            errors.append(
                f"{feature}/tasks.md:{line_number}: slice task is checked without valid "
                f"{IMPLEMENTATION_AUTHORIZATION_PATH}"
            )
        if slice_state not in {"ACTIVE", "CONVERGED", "HANDOFF_READY", "ACCEPTED"}:
            errors.append(
                f"{feature}/tasks.md:{line_number}: slice task is checked while slice "
                f"state is {slice_state!r}, not ACTIVE or later"
            )
        if not activation_exists:
            errors.append(
                f"{feature}/tasks.md:{line_number}: slice task is checked without its "
                "activation evidence"
            )
    return errors


def _clean_metadata(text: str, label: str, *, last: bool = False) -> str:
    return (_metadata_value(text, label, last=last) or "").replace("`", "").strip()


def _mapping_metadata(
    value: str,
    expected_keys: tuple[str, ...],
) -> tuple[dict[str, str], str | None]:
    """Parse an ordered `slice=value` metadata mapping."""

    if not expected_keys:
        return ({}, None) if value == "none" else ({}, "must be 'none'")
    parts = [part.strip() for part in value.split(",") if part.strip()]
    parsed: dict[str, str] = {}
    observed_keys: list[str] = []
    for part in parts:
        key, separator, mapped = part.partition("=")
        key = key.strip()
        mapped = mapped.strip()
        if not separator or not key or not mapped or key in parsed:
            return {}, "must use unique ordered SLICE=value entries"
        observed_keys.append(key)
        parsed[key] = mapped
    if tuple(observed_keys) != expected_keys:
        return {}, f"must map exactly {expected_keys} in dependency order"
    return parsed, None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_commit_exists(root: Path, commit: str) -> bool:
    """Fail closed unless *commit* exists in a real Git worktree."""

    worktree = _git(root, "rev-parse", "--is-inside-work-tree")
    if (
        worktree is None
        or worktree.returncode != 0
        or worktree.stdout.strip() != "true"
    ):
        return False
    completed = _git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    if completed is None:
        return False
    return completed.returncode == 0


def _git_ref_commit(root: Path, reference: str) -> str | None:
    completed = _git(root, "rev-parse", "--verify", reference)
    if completed is None or completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    completed = _git(root, "merge-base", "--is-ancestor", ancestor, descendant)
    return completed is not None and completed.returncode == 0


def _repo_path_is_safe(
    root: Path, relative: Path, *, require_file: bool = False
) -> bool:
    """Reject absolute/traversing paths, symlinked ancestors, and escapes."""

    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        return False
    root_resolved = root.resolve()
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            return False
    try:
        if not candidate.resolve(strict=False).is_relative_to(root_resolved):
            return False
    except OSError:
        return False
    return not require_file or candidate.is_file()


def _git_file_text(root: Path, commit: str, relative: Path) -> str | None:
    completed = _git(root, "show", f"{commit}:{relative.as_posix()}")
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout.replace("\r\n", "\n")


def _git_path_exists_at_commit(root: Path, commit: str, relative: Path) -> bool:
    completed = _git(root, "cat-file", "-e", f"{commit}:{relative.as_posix()}")
    return completed is not None and completed.returncode == 0


def _git_first_commit_containing(
    root: Path,
    relative: Path,
    needle: str,
) -> str | None:
    """Return the first path revision containing one immutable marker."""

    history = _git(root, "log", "--format=%H", "--reverse", "--", relative.as_posix())
    if history is None or history.returncode != 0:
        return None
    for commit in history.stdout.splitlines():
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            continue
        revision = _git_file_text(root, commit, relative)
        if revision is not None and needle in revision:
            return commit
    return None


def _git_changed_paths(root: Path, older: str, newer: str) -> tuple[str, ...] | None:
    completed = _git(root, "diff", "--name-only", f"{older}..{newer}")
    if completed is None or completed.returncode != 0:
        return None
    return tuple(line for line in completed.stdout.splitlines() if line)


def _git_path_history_errors(
    root: Path, relative: Path, *, append_only: bool
) -> list[str]:
    """Replay all path revisions and reject deletion, rewrite, or non-prefix append."""

    path = root / relative
    history = _git(root, "log", "--format=%H", "--reverse", "--", relative.as_posix())
    if history is None or history.returncode != 0:
        return []
    commits = [line for line in history.stdout.splitlines() if line]
    if commits and not path.exists() and not path.is_symlink():
        return [f"{relative}: committed lifecycle evidence may not be deleted"]
    if not commits or not path.is_file() or not _repo_path_is_safe(root, relative):
        return []

    errors: list[str] = []
    current = path.read_bytes().replace(b"\r\n", b"\n")
    head_content = _git(root, "show", f"HEAD:{relative.as_posix()}")
    if head_content is not None and head_content.returncode == 0:
        committed = head_content.stdout.encode("utf-8").replace(b"\r\n", b"\n")
        if current != committed:
            if append_only and current.startswith(committed):
                pass
            else:
                action = (
                    "only be extended by appending"
                    if append_only
                    else "not be rewritten"
                )
                errors.append(f"{relative}: committed lifecycle evidence may {action}")

    previous_text: str | None = None
    for commit in commits:
        revision = _git_file_text(root, commit, relative)
        if revision is None:
            errors.append(f"{relative}: committed lifecycle evidence was deleted")
            previous_text = None
            continue
        if previous_text is not None:
            if append_only and not revision.startswith(previous_text):
                errors.append(
                    f"{relative}: committed attempt stream rewrote prior history"
                )
            elif not append_only and revision != previous_text:
                errors.append(f"{relative}: immutable lifecycle evidence was rewritten")
        previous_text = revision
    return sorted(set(errors))


def _ordinary_evidence_path_errors(
    root: Path,
    relative_record: Path,
    label: str,
    value: str,
) -> list[str]:
    """Require a comma-separated list of existing ordinary evidence files."""

    errors: list[str] = []
    entries = [entry.strip().strip("`") for entry in value.split(",")]
    if not entries or any(not entry for entry in entries):
        return [f"{relative_record}: {label} must name exact evidence files"]
    for entry in entries:
        candidate = Path(entry)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or any(character in entry for character in "*?[]")
            or not candidate.as_posix().startswith("evidence/v2/")
        ):
            errors.append(
                f"{relative_record}: {label} entry {entry!r} must be an exact "
                "repo-relative evidence/v2 file"
            )
            continue
        if candidate == relative_record:
            errors.append(
                f"{relative_record}: {label} may not cite its own lifecycle record"
            )
        elif not _repo_path_is_safe(root, candidate):
            errors.append(
                f"{relative_record}: {label} entry {entry!r} has an unsafe path"
            )
        elif not (root / candidate).is_file():
            errors.append(
                f"{relative_record}: {label} entry {entry!r} does not exist as a file"
            )
    return errors


def _assignment_errors(
    root: Path,
    declaration: str,
    expected_lane: str,
    context: str | Path,
) -> list[str]:
    """Validate one named participant against its durable assignment record."""

    if declaration.startswith("UNASSIGNED"):
        return []
    identity, separator, reference = declaration.partition(" — ")
    if not separator or not identity.strip() or not reference.strip():
        return [
            f"{context}: assignment must be '<identity> — <durable repository record>'"
        ]
    relative = Path(reference.strip().strip("`"))
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.as_posix().startswith("evidence/governance/assignments/")
        or relative.suffix != ".md"
    ):
        return [
            f"{context}: assignment reference must be an exact repo-relative "
            "evidence/governance/assignments/*.md record"
        ]
    path = root / relative
    if not _repo_path_is_safe(root, relative, require_file=True):
        return [f"{relative}: assignment evidence path is unsafe or missing"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{relative}: assignment record is unreadable ({exc})"]

    errors = _singleton_metadata_errors(
        text,
        ("Assignee", "Lane", "Assigned by", "Assigned on", "Authority reference"),
        relative,
    )
    expected = {"Assignee": identity.strip(), "Lane": expected_lane}
    for label, value in expected.items():
        observed = _clean_metadata(text, label)
        if observed != value:
            errors.append(
                f"{relative}: {label} must be {value!r}; observed {observed!r}"
            )
    assigner = _clean_metadata(text, "Assigned by")
    if not assigner:
        errors.append(f"{relative}: Assigned by must name Zoe or a durable delegate")
    elif assigner != "Zoe":
        errors.extend(
            _singleton_metadata_errors(
                text, ("Delegated by", "Delegation reference"), relative
            )
        )
        if _clean_metadata(text, "Delegated by") != "Zoe":
            errors.append(f"{relative}: non-Zoe assigner must be delegated by Zoe")
        if len(_clean_metadata(text, "Delegation reference")) < 10:
            errors.append(f"{relative}: missing durable Delegation reference")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _clean_metadata(text, "Assigned on")):
        errors.append(f"{relative}: Assigned on must be an ISO date")
    if len(_clean_metadata(text, "Authority reference")) < 10:
        errors.append(f"{relative}: missing durable Authority reference")
    return errors


def _slice_lifecycle_evidence_errors(
    root: Path,
    dirname: str,
    expected: dict[str, object],
    slice_state: str,
    assigned_participant: str,
    tasks_text: str,
) -> list[str]:
    """Validate immutable or append-only evidence for the declared transition."""

    errors: list[str] = []
    paths = EXPECTED_LIFECYCLE_PATHS[dirname]
    texts: dict[str, str] = {}
    activation_starting_commit = ""
    for stage in ("activation", "candidate", "handoff", "acceptance", "amendments"):
        relative = Path(paths[stage])
        path = root / relative
        if path.exists() and not _repo_path_is_safe(root, relative):
            errors.append(f"{relative}: lifecycle evidence path is unsafe")
            continue
        if path.is_file():
            try:
                texts[stage] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"{relative}: lifecycle evidence is unreadable ({exc})")
        errors.extend(
            _git_path_history_errors(
                root,
                relative,
                append_only=stage in {"candidate", "handoff", "amendments"},
            )
        )

    if slice_state == "PLANNED":
        for stage in texts:
            errors.append(
                f"{paths[stage]}: {stage} evidence exists while the slice is PLANNED"
            )
        return errors

    if "activation" not in texts:
        errors.append(f"{dirname}: {slice_state} requires {paths['activation']}")

    candidate_present = "candidate" in texts
    handoff_present = "handoff" in texts
    acceptance_present = "acceptance" in texts
    amendments_present = "amendments" in texts
    if slice_state == "READY" and (
        candidate_present or handoff_present or acceptance_present
    ):
        errors.append(f"{dirname}: READY permits only activation evidence")
    if amendments_present and not acceptance_present:
        errors.append(
            f"{dirname}: an accepted-amendment ledger requires prior terminal "
            "acceptance evidence"
        )
    if slice_state == "ACTIVE":
        if candidate_present != handoff_present:
            errors.append(
                f"{dirname}: ACTIVE may retain candidate and handoff evidence only "
                "as one rejected attempt"
            )
        if acceptance_present:
            errors.append(f"{dirname}: ACTIVE cannot retain acceptance evidence")
    if (
        slice_state in {"CONVERGED", "HANDOFF_READY", "ACCEPTED"}
        and not candidate_present
    ):
        errors.append(f"{dirname}: {slice_state} requires {paths['candidate']}")
    if slice_state in {"HANDOFF_READY", "ACCEPTED"} and not handoff_present:
        errors.append(f"{dirname}: {slice_state} requires {paths['handoff']}")
    if slice_state != "ACCEPTED" and acceptance_present:
        errors.append(f"{dirname}: {slice_state} cannot have acceptance evidence")
    if slice_state == "ACCEPTED" and not acceptance_present:
        errors.append(f"{dirname}: ACCEPTED requires {paths['acceptance']}")

    if slice_state in {"CONVERGED", "HANDOFF_READY", "ACCEPTED"}:
        unchecked = [
            line for line in tasks_text.splitlines() if line.startswith("- [ ] T")
        ]
        if unchecked:
            errors.append(
                f"{dirname}/tasks.md: {slice_state} requires every planned task to "
                "be complete"
            )

    activation = texts.get("activation")
    if activation is not None:
        relative = Path(paths["activation"])
        activation_record_commit = _git_first_commit_containing(
            root,
            relative,
            f"**Slice**: `{dirname}`",
        )
        activation_labels = (
            "Slice",
            "Status",
            "Assigned participant / source",
            "Authority record",
            "Accepted dependencies",
            "Dependency commits",
            "Dependency acceptance references",
            "Analysis result",
            "Branch",
            "Worktree",
            "Starting commit",
            "Interfaces",
            "Acceptance scenes",
            "Evidence targets",
            "Documentation scope",
            "Initial task IDs",
            "Initial tasks SHA256",
        )
        errors.extend(
            _singleton_metadata_errors(activation, activation_labels, relative)
        )
        exact_fields = {
            "Slice": dirname,
            "Status": "READY",
            "Assigned participant / source": assigned_participant,
            "Authority record": str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "Branch": str(expected["branch"]),
            "Worktree": str(expected["worktree"]),
        }
        for label, value in exact_fields.items():
            observed = _clean_metadata(activation, label)
            if observed != value:
                errors.append(
                    f"{relative}: {label} must be {value!r}; observed {observed!r}"
                )
        dependencies_value = _clean_metadata(activation, "Accepted dependencies")
        expected_dependencies = expected["dependencies"]
        expected_dependencies_value = (
            ", ".join(expected_dependencies) if expected_dependencies else "none"
        )
        if dependencies_value != expected_dependencies_value:
            errors.append(
                f"{relative}: Accepted dependencies must be exactly "
                f"{expected_dependencies_value!r}"
            )
        dependency_commits = _clean_metadata(activation, "Dependency commits")
        commit_map, mapping_error = _mapping_metadata(
            dependency_commits, expected_dependencies
        )
        if mapping_error:
            errors.append(f"{relative}: Dependency commits {mapping_error}")
        for dependency_id, commit in commit_map.items():
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                errors.append(
                    f"{relative}: Dependency commits entry {dependency_id} must be "
                    "a full Git SHA"
                )

        acceptance_references = _clean_metadata(
            activation, "Dependency acceptance references"
        )
        reference_map, reference_error = _mapping_metadata(
            acceptance_references, expected_dependencies
        )
        if reference_error:
            errors.append(
                f"{relative}: Dependency acceptance references {reference_error}"
            )
        by_id = {name[:3]: name for name in EXPECTED_SLICES}
        for dependency_id, reference in reference_map.items():
            reference_path = Path(reference)
            consumer_evidence_directory = relative.parent
            if (
                reference_path.is_absolute()
                or ".." in reference_path.parts
                or not reference_path.is_relative_to(consumer_evidence_directory)
                or dependency_id not in reference_path.name
                or not _repo_path_is_safe(root, reference_path, require_file=True)
            ):
                errors.append(
                    f"{relative}: dependency {dependency_id} acceptance reference "
                    "must name an existing consumer-owned evidence file whose name "
                    "includes the dependency ID"
                )
                continue
            try:
                reference_text = (root / reference_path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                errors.append(
                    f"{reference_path}: dependency acceptance evidence is unreadable"
                )
                continue
            upstream = by_id[dependency_id]
            stage = "acceptance" if dirname == "110-v2-parity-cutover" else "handoff"
            packet_reference = EXPECTED_LIFECYCLE_PATHS[upstream][stage]
            expected_reference_fields = {
                "Consumer slice": dirname,
                "Upstream slice": upstream,
                "Candidate commit": commit_map.get(dependency_id, ""),
                "Accepted by": assigned_participant.split(" — ", 1)[0],
                "Packet reference": packet_reference,
            }
            errors.extend(
                _singleton_metadata_errors(
                    reference_text,
                    (
                        "Consumer slice",
                        "Upstream slice",
                        "Candidate commit",
                        "Accepted by",
                        "Accepted on",
                        "Packet reference",
                        "Decision reference",
                    ),
                    reference_path,
                )
            )
            for label, expected_value in expected_reference_fields.items():
                observed = _clean_metadata(reference_text, label)
                if observed != expected_value:
                    errors.append(
                        f"{reference_path}: {label} must be {expected_value!r}; "
                        f"observed {observed!r}"
                    )
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}",
                _clean_metadata(reference_text, "Accepted on"),
            ):
                errors.append(f"{reference_path}: Accepted on must be an ISO date")
            if len(_clean_metadata(reference_text, "Decision reference")) < 10:
                errors.append(f"{reference_path}: missing durable Decision reference")

        for dependency_id, commit in commit_map.items():
            upstream = by_id[dependency_id]
            stage = "acceptance" if dirname == "110-v2-parity-cutover" else "handoff"
            upstream_relative = Path(EXPECTED_LIFECYCLE_PATHS[upstream][stage])
            upstream_path = root / upstream_relative
            if not _repo_path_is_safe(root, upstream_relative, require_file=True):
                continue
            if activation_record_commit is not None:
                upstream_text = _git_file_text(
                    root,
                    activation_record_commit,
                    upstream_relative,
                )
            else:
                try:
                    upstream_text = upstream_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    upstream_text = None
            if upstream_text is None:
                errors.append(
                    f"{relative}: dependency {dependency_id} packet did not exist "
                    "when activation was recorded"
                )
                continue
            upstream_records = _lifecycle_records(upstream_text)
            if upstream_records:
                terminal_commit = _clean_metadata(
                    upstream_records[-1], "Candidate commit"
                )
                effective_commit, amendment_errors = _effective_dependency_commit(
                    root,
                    upstream,
                    terminal_commit,
                    at_commit=activation_record_commit,
                )
                errors.extend(amendment_errors)
                if commit != effective_commit:
                    errors.append(
                        f"{relative}: dependency {dependency_id} commit must match "
                        f"the effective accepted candidate for "
                        f"{upstream_path.relative_to(root)} at activation time "
                        "(including amendments then present in its "
                        "slice-amendments.md ledger)"
                    )
        analysis = _clean_metadata(activation, "Analysis result")
        if analysis != "PASS — zero CRITICAL/HIGH findings":
            errors.append(
                f"{relative}: Analysis result must be exactly "
                "'PASS — zero CRITICAL/HIGH findings'"
            )
        activation_starting_commit = _clean_metadata(activation, "Starting commit")
        if not re.fullmatch(r"[0-9a-f]{40}", activation_starting_commit):
            errors.append(f"{relative}: Starting commit must be a full Git SHA")
        elif _git_commit_exists(root, activation_starting_commit) is False:
            errors.append(f"{relative}: Starting commit does not exist in Git")
        for label in (
            "Interfaces",
            "Acceptance scenes",
            "Evidence targets",
            "Documentation scope",
        ):
            if len(_clean_metadata(activation, label)) < 3:
                errors.append(f"{relative}: missing concrete {label}")

        plan_relative = Path("specs") / dirname / "plan.md"
        if _repo_path_is_safe(root, plan_relative, require_file=True):
            plan_text = (root / plan_relative).read_text(encoding="utf-8")
            expected_interfaces = set(INTERFACE_ID.findall(plan_text))
            observed_interfaces = set(
                INTERFACE_ID.findall(_clean_metadata(activation, "Interfaces"))
            )
            if observed_interfaces != expected_interfaces:
                errors.append(
                    f"{relative}: Interfaces must enumerate exactly "
                    f"{sorted(expected_interfaces)} from the bound plan"
                )
            expected_scenes = set(SCENE_ID.findall(plan_text))
            observed_scenes = set(
                SCENE_ID.findall(_clean_metadata(activation, "Acceptance scenes"))
            )
            if observed_scenes != expected_scenes:
                errors.append(
                    f"{relative}: Acceptance scenes must enumerate exactly "
                    f"{sorted(expected_scenes)} from the bound plan"
                )
            evidence_targets = {
                item.strip().strip("`")
                for item in _clean_metadata(activation, "Evidence targets").split(",")
                if item.strip()
            }
            if not evidence_targets or any(
                not target.startswith("evidence/v2/")
                or target.endswith("/")
                or any(character in target for character in "*?[]")
                or f"`{target}`" not in plan_text
                for target in evidence_targets
            ):
                errors.append(
                    f"{relative}: Evidence targets must be exact planned evidence/v2 files"
                )
            documentation_scope = {
                item.strip().strip("`")
                for item in _clean_metadata(activation, "Documentation scope").split(",")
                if item.strip()
            }
            expected_documentation = EXPECTED_DOCUMENTATION_PATHS.get(dirname, set())
            if documentation_scope != expected_documentation:
                errors.append(
                    f"{relative}: Documentation scope must enumerate exactly "
                    f"{sorted(expected_documentation)}"
                )

        task_entries = _task_entries(tasks_text)
        current_task_ids, _current_task_hash = _task_manifest(task_entries)
        initial_task_ids = _clean_metadata(activation, "Initial task IDs")
        declared_ids = tuple(
            part.strip() for part in initial_task_ids.split(",") if part.strip()
        )
        current_ids = tuple(task_id for task_id, _line in task_entries)
        if not declared_ids or declared_ids != current_ids[: len(declared_ids)]:
            errors.append(
                f"{relative}: Initial task IDs must be a nonempty unchanged prefix "
                f"of the current task manifest {current_task_ids!r}"
            )
        else:
            initial_entries = task_entries[: len(declared_ids)]
            _ids, expected_hash = _task_manifest(initial_entries)
            if _clean_metadata(activation, "Initial tasks SHA256") != expected_hash:
                errors.append(
                    f"{relative}: Initial tasks SHA256 must match the frozen initial "
                    "task manifest"
                )

    candidate = texts.get("candidate")
    candidate_commit = ""
    candidate_commits: list[str] = []
    if candidate is not None:
        relative = Path(paths["candidate"])
        records = _lifecycle_records(candidate)
        if not records:
            errors.append(f"{relative}: candidate evidence has no attested record")
        for attempt, record in enumerate(records, 1):
            prefix = f"{relative} attempt {attempt}"
            errors.extend(
                _singleton_metadata_errors(
                    record,
                    (
                        "Slice",
                        "Status",
                        "Candidate commit",
                        "Tasks complete",
                        "Completed task IDs",
                        "Tasks SHA256",
                        "Verification commands / results",
                        "Interface versions",
                        "Evidence paths",
                        "Known limitations",
                    ),
                    prefix,
                )
            )
            for label, value in {"Slice": dirname, "Status": "CONVERGED"}.items():
                observed = _clean_metadata(record, label)
                if observed != value:
                    errors.append(
                        f"{prefix}: {label} must be {value!r}; observed {observed!r}"
                    )
            commit = _clean_metadata(record, "Candidate commit")
            candidate_commits.append(commit)
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                errors.append(f"{prefix}: Candidate commit must be a full Git SHA")
            elif _git_commit_exists(root, commit) is False:
                errors.append(f"{prefix}: Candidate commit does not exist in Git")
            elif (
                activation_starting_commit
                and _git_commit_exists(root, activation_starting_commit)
                and not _git_is_ancestor(root, activation_starting_commit, commit)
            ):
                errors.append(
                    f"{prefix}: Candidate commit must descend from the activation "
                    "Starting commit"
                )
            committed_tasks = (
                _git_file_text(
                    root,
                    commit,
                    Path("specs") / dirname / "tasks.md",
                )
                if _git_commit_exists(root, commit)
                else None
            )
            if committed_tasks is None:
                errors.append(
                    f"{prefix}: Candidate commit must contain the bound tasks.md"
                )
                committed_task_entries: tuple[tuple[str, str], ...] = ()
            else:
                try:
                    committed_task_entries = _validated_task_entries(committed_tasks)
                except ValueError as exc:
                    errors.append(f"{prefix}: Candidate tasks.md is invalid ({exc})")
                    committed_task_entries = ()
            expected_task_ids, expected_task_hash = _task_manifest(
                committed_task_entries
            )
            record_commit = _git_first_commit_containing(
                root,
                relative,
                commit,
            )
            if record_commit is None:
                # Direct lifecycle-unit fixtures may construct an uncommitted
                # record around an already committed candidate. Repository
                # validation has path-history checks and takes the committed
                # introduction branch above.
                attested_tasks = committed_tasks
            elif _git_commit_exists(root, commit) and not _git_is_ancestor(
                root, commit, record_commit
            ):
                errors.append(
                    f"{prefix}: candidate record must be introduced at or after "
                    "the candidate commit"
                )
                attested_tasks = None
            else:
                attested_tasks = _git_file_text(
                    root,
                    record_commit,
                    Path("specs") / dirname / "tasks.md",
                )
            if attested_tasks is None:
                errors.append(
                    f"{prefix}: record-introduction commit must contain tasks.md"
                )
            else:
                try:
                    attested_task_entries = _validated_task_entries(attested_tasks)
                except ValueError as exc:
                    errors.append(
                        f"{prefix}: record-introduction tasks.md is invalid ({exc})"
                    )
                    attested_task_entries = ()
                attested_task_ids, _attested_task_hash = _task_manifest(
                    attested_task_entries
                )
                if attested_task_ids != expected_task_ids:
                    errors.append(
                        f"{prefix}: task IDs changed between candidate and "
                        "candidate-record introduction"
                    )
                errors.extend(
                    _candidate_task_completion_errors(
                        tasks_complete=_clean_metadata(record, "Tasks complete"),
                        declared_completed=_clean_metadata(record, "Completed task IDs"),
                        committed_tasks=attested_tasks,
                        committed_task_entries=attested_task_entries,
                        prefix=prefix,
                    )
                )
            if _clean_metadata(record, "Tasks SHA256") != expected_task_hash:
                errors.append(
                    f"{prefix}: Tasks SHA256 must match tasks.md at Candidate commit"
                )
            verification = _clean_metadata(record, "Verification commands / results")
            if not verification.startswith("PASS — "):
                errors.append(
                    f"{prefix}: Verification commands / results must start with "
                    "'PASS — '"
                )
            if not re.search(
                r"I-\d{3}[A-Z]", _clean_metadata(record, "Interface versions")
            ):
                errors.append(f"{prefix}: missing concrete Interface versions")
            evidence_paths = _clean_metadata(record, "Evidence paths")
            errors.extend(
                _ordinary_evidence_path_errors(
                    root, relative, "Evidence paths", evidence_paths
                )
            )
            if _git_commit_exists(root, commit):
                for entry in (
                    Path(item.strip().strip("`"))
                    for item in evidence_paths.split(",")
                    if item.strip()
                ):
                    if _repo_path_is_safe(
                        root, entry
                    ) and not _git_path_exists_at_commit(root, commit, entry):
                        errors.append(
                            f"{prefix}: Evidence path {entry} is absent from "
                            "Candidate commit"
                        )
            if len(_clean_metadata(record, "Known limitations")) < 3:
                errors.append(f"{prefix}: missing concrete Known limitations")
        if candidate_commits:
            candidate_commit = candidate_commits[-1]
        if len(set(candidate_commits)) != len(candidate_commits):
            errors.append(f"{relative}: every candidate attempt must use a new commit")

    acceptance_owner = "Zoe" if dirname == "110-v2-parity-cutover" else "v2-integrator"
    handoff = texts.get("handoff")
    latest_handoff_status = ""
    latest_handoff_commit = ""
    rejected_commits: list[str] = []
    if handoff is not None:
        relative = Path(paths["handoff"])
        records = _lifecycle_records(handoff)
        if not records:
            errors.append(f"{relative}: handoff evidence has no attested record")
        previous_status = ""
        previous_commit = ""
        for attempt, record in enumerate(records, 1):
            prefix = f"{relative} record {attempt}"
            status = _clean_metadata(record, "Status")
            commit = _clean_metadata(record, "Candidate commit")
            latest_handoff_status = status
            latest_handoff_commit = commit
            if _clean_metadata(record, "Slice") != dirname:
                errors.append(f"{prefix}: Slice must be {dirname!r}")
            if commit not in candidate_commits:
                errors.append(f"{prefix}: Candidate commit has no candidate record")
            if status == "HANDOFF_READY":
                errors.extend(
                    _singleton_metadata_errors(
                        record,
                        (
                            "Slice",
                            "Status",
                            "Candidate commit",
                            "Acceptance owner",
                            "Documentation freshness",
                            "Packet paths",
                        ),
                        prefix,
                    )
                )
                if previous_status == "HANDOFF_READY":
                    errors.append(f"{prefix}: a prior handoff must be rejected first")
                for label, value in {
                    "Acceptance owner": acceptance_owner,
                    "Documentation freshness": "PASS",
                }.items():
                    observed = _clean_metadata(record, label)
                    if observed != value:
                        errors.append(
                            f"{prefix}: {label} must be {value!r}; observed {observed!r}"
                        )
                errors.extend(
                    _ordinary_evidence_path_errors(
                        root,
                        relative,
                        "Packet paths",
                        _clean_metadata(record, "Packet paths"),
                    )
                )
            elif status == "REJECTED":
                errors.extend(
                    _singleton_metadata_errors(
                        record,
                        (
                            "Slice",
                            "Status",
                            "Candidate commit",
                            "Rejected by",
                            "Rejected on",
                            "Decision reference",
                            "Recorded by",
                        ),
                        prefix,
                    )
                )
                if previous_status != "HANDOFF_READY":
                    errors.append(
                        f"{prefix}: REJECTED must follow a HANDOFF_READY record"
                    )
                elif commit != previous_commit:
                    errors.append(
                        f"{prefix}: rejected commit must match the preceding handoff"
                    )
                rejected_commits.append(commit)
                if _clean_metadata(record, "Rejected by") != acceptance_owner:
                    errors.append(f"{prefix}: Rejected by must be {acceptance_owner!r}")
                if _clean_metadata(record, "Recorded by") != "v2-integrator":
                    errors.append(f"{prefix}: Recorded by must be 'v2-integrator'")
                if not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", _clean_metadata(record, "Rejected on")
                ):
                    errors.append(f"{prefix}: Rejected on must be an ISO date")
                if len(_clean_metadata(record, "Decision reference")) < 10:
                    errors.append(f"{prefix}: missing durable Decision reference")
            else:
                errors.append(f"{prefix}: Status must be 'HANDOFF_READY' or 'REJECTED'")
            previous_status = status
            previous_commit = commit

    expected_rejected_commits = (
        candidate_commits
        if slice_state == "ACTIVE" and candidate_present
        else candidate_commits[:-1]
    )
    if rejected_commits != expected_rejected_commits:
        errors.append(
            f"{dirname}: append-only attempts require rejected commits "
            f"{expected_rejected_commits}; observed {rejected_commits}"
        )

    if slice_state == "ACTIVE" and handoff_present:
        if (
            latest_handoff_status != "REJECTED"
            or latest_handoff_commit != candidate_commit
        ):
            errors.append(
                f"{dirname}: ACTIVE retained evidence must end with rejection of the "
                "latest candidate"
            )
    if slice_state == "CONVERGED" and handoff_present:
        if (
            latest_handoff_status != "REJECTED"
            or latest_handoff_commit == candidate_commit
        ):
            errors.append(
                f"{dirname}: CONVERGED may retain only a rejected earlier handoff "
                "followed by a new candidate"
            )
    if slice_state in {"HANDOFF_READY", "ACCEPTED"}:
        if (
            latest_handoff_status != "HANDOFF_READY"
            or latest_handoff_commit != candidate_commit
        ):
            errors.append(
                f"{dirname}: {slice_state} requires the latest handoff to match the "
                "latest candidate"
            )

    acceptance = texts.get("acceptance")
    if acceptance is not None:
        relative = Path(paths["acceptance"])
        acceptance_record = _lifecycle_records(acceptance)
        if len(acceptance_record) != 1:
            errors.append(f"{relative}: acceptance evidence must contain one record")
        record = acceptance_record[-1] if acceptance_record else acceptance
        exact_fields = {
            "Slice": dirname,
            "Status": "ACCEPTED",
            "Candidate commit": candidate_commit,
            "Accepted by": acceptance_owner,
            "Recorded by": "v2-integrator",
        }
        errors.extend(
            _singleton_metadata_errors(
                record,
                (
                    "Slice",
                    "Status",
                    "Candidate commit",
                    "Accepted by",
                    "Accepted on",
                    "Decision reference",
                    "Recorded by",
                ),
                relative,
            )
        )
        for label, value in exact_fields.items():
            observed = _clean_metadata(record, label)
            if observed != value:
                errors.append(
                    f"{relative}: {label} must be {value!r}; observed {observed!r}"
                )
        accepted_on = _clean_metadata(record, "Accepted on")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", accepted_on):
            errors.append(f"{relative}: Accepted on must be an ISO date")
        if len(_clean_metadata(record, "Decision reference")) < 10:
            errors.append(f"{relative}: missing durable Decision reference")

    return errors


def _derived_program_state(
    slice_states: dict[str, str],
    *,
    planning_baseline_accepted: bool,
    cutover_accepted: bool,
    post_merge_verified: bool,
) -> str:
    if post_merge_verified:
        return "CUTOVER_VERIFIED"
    if cutover_accepted:
        return "CUTOVER_ACCEPTED"
    final_state = slice_states.get("110-v2-parity-cutover", "")
    if final_state in {"ACTIVE", "CONVERGED", "HANDOFF_READY", "ACCEPTED"}:
        return "INTEGRATION"
    if any(
        state in {"ACTIVE", "CONVERGED", "HANDOFF_READY", "ACCEPTED"}
        for name, state in slice_states.items()
        if name != "110-v2-parity-cutover"
    ):
        return "DELIVERY"
    return "READY" if planning_baseline_accepted else "PLANNING"


def _planning_baseline_accepted(root: Path) -> bool:
    """Recognize the durable, non-authorizing planning-baseline decision."""

    path = root / PLANNING_BASELINE_PATH
    if not _repo_path_is_safe(root, PLANNING_BASELINE_PATH, require_file=True):
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    normalized = " ".join(text.split())
    return all(
        token in normalized
        for token in (
            "# Slice-centric execution-spine amendment",
            "durable acceptance of the planning baseline",
            "PLANNING -> READY -> DELIVERY -> INTEGRATION",
            "It does not grant authority",
        )
    )


def _slice_dependency_state_errors(slice_states: dict[str, str]) -> list[str]:
    errors: list[str] = []
    by_id = {dirname[:3]: dirname for dirname in EXPECTED_SLICES}
    started_states = {"READY", "ACTIVE", "CONVERGED", "HANDOFF_READY", "ACCEPTED"}
    for dirname, state in slice_states.items():
        if state not in started_states:
            continue
        accepted_dependency_states = (
            {"ACCEPTED"}
            if dirname == "110-v2-parity-cutover"
            else {"HANDOFF_READY", "ACCEPTED"}
        )
        for dependency_id in EXPECTED_SLICES[dirname]["dependencies"]:
            dependency = by_id[dependency_id]
            dependency_state = slice_states.get(dependency, "")
            if dependency_state not in accepted_dependency_states:
                requirement = (
                    "ACCEPTED"
                    if dirname == "110-v2-parity-cutover"
                    else "HANDOFF_READY or ACCEPTED"
                )
                errors.append(
                    f"{dirname}: {state} requires dependency {dependency} to be "
                    f"{requirement}; observed {dependency_state!r}"
                )
    return errors


def _markdown_subsection(text: str, heading: str) -> str:
    marker = f"### {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\n## ", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


def _markdown_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\n## ", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


def _documentation_planning_errors(
    dirname: str,
    spec_text: str,
    plan_text: str,
    tasks_text: str,
    checklist_text: str,
) -> list[str]:
    """Validate one slice's mandatory README/docs disposition and gate tasks."""

    errors: list[str] = []
    spec_section = _markdown_section(spec_text, "Documentation Freshness")
    plan_section = _markdown_section(plan_text, "Documentation Impact and Freshness")
    if not spec_section:
        errors.append(f"{dirname}/spec.md: missing documentation freshness section")
    if not plan_section:
        errors.append(f"{dirname}/plan.md: missing documentation impact section")
        return errors

    for generic in ("`docs/`", "`docs/security/`"):
        if generic in plan_section or generic in spec_section:
            errors.append(
                f"{dirname}: generic documentation path {generic} is invalid when exact files are known"
            )

    for expected_path in sorted(EXPECTED_DOCUMENTATION_PATHS.get(dirname, set())):
        token = f"`{expected_path}`"
        if token not in plan_section:
            errors.append(
                f"{dirname}/plan.md: documentation matrix omits known affected path {expected_path!r}"
            )
        if token not in spec_section:
            errors.append(
                f"{dirname}/spec.md: documentation review omits known affected path {expected_path!r}"
            )

    rows: list[list[str]] = []
    for line in plan_section.splitlines():
        if not line.startswith("|") or re.fullmatch(r"[|:\- ]+", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0] == "Claim surface":
            continue
        rows.append(cells)

    readme_rows = [row for row in rows if "`README.md`" in row[1]]
    if len(readme_rows) != 1:
        errors.append(
            f"{dirname}/plan.md: documentation matrix must contain one README.md row"
        )
    else:
        readme = readme_rows[0]
        disposition = readme[2].strip("`")
        expected = "UPDATE" if dirname == "110-v2-parity-cutover" else "HANDOFF"
        if disposition != expected:
            errors.append(
                f"{dirname}/plan.md: README.md disposition must be {expected}; "
                f"observed {disposition or 'missing'}"
            )

    if not any(row[2].strip("`") == "UPDATE" for row in rows):
        errors.append(f"{dirname}/plan.md: no owned documentation UPDATE row")

    for row in rows:
        disposition = row[2].strip("`")
        details = row[4]
        if disposition not in {"UPDATE", "NO_IMPACT", "HANDOFF"}:
            errors.append(
                f"{dirname}/plan.md: invalid documentation disposition {disposition!r}"
            )
            continue
        if len(details) < 20:
            errors.append(
                f"{dirname}/plan.md: {disposition} row lacks concrete validation/rationale/delta"
            )
        if disposition == "HANDOFF" and "Accepting owner:" not in details:
            errors.append(
                f"{dirname}/plan.md: HANDOFF row lacks an explicit accepting owner"
            )
        if disposition == "NO_IMPACT" and "rationale" not in details.lower():
            errors.append(f"{dirname}/plan.md: NO_IMPACT row lacks concrete rationale")

    tasks_lower = tasks_text.lower()
    tasks_terms = tasks_lower.replace("-", " ")
    for token in (
        "documentation freshness",
        "documentation impact and freshness",
        "readme.md",
        "documentation dispositions",
        "reviewer",
    ):
        if token not in tasks_terms:
            errors.append(
                f"{dirname}/tasks.md: missing documentation gate task term {token!r}"
            )
    if "documentation freshness" not in checklist_text.lower():
        errors.append(
            f"{dirname}/checklists/requirements.md: missing documentation freshness review"
        )
    if "**`README.md` disposition**" not in spec_section:
        errors.append(f"{dirname}/spec.md: missing explicit README.md disposition")
    if "handoff evidence" not in spec_section.lower():
        errors.append(
            f"{dirname}/spec.md: missing ordinary handoff evidence for documentation"
        )
    return errors


def _graph_cycle(graph: dict[str, tuple[str, ...]]) -> list[str]:
    """Return one dependency cycle as IDs, or an empty list."""

    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visiting:
            return path[path.index(node) :] + [node]
        if node in visited:
            return []
        visiting.add(node)
        path.append(node)
        for dependency in graph.get(node, ()):
            cycle = visit(dependency)
            if cycle:
                return cycle
        path.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in graph:
        cycle = visit(node)
        if cycle:
            return cycle
    return []


def _cutover_evidence_errors(
    root: Path,
    *,
    final_state: str,
    accepted_candidate: str,
) -> list[str]:
    """Validate the exact accepted candidate, atomic merge, and main verification."""

    errors: list[str] = []
    cutover_path = root / CUTOVER_ACCEPTANCE_PATH
    verification_path = root / POST_MERGE_VERIFICATION_PATH
    if cutover_path.exists() and not _repo_path_is_safe(root, CUTOVER_ACCEPTANCE_PATH):
        errors.append(f"{CUTOVER_ACCEPTANCE_PATH}: cutover evidence path is unsafe")
        cutover = ""
    elif cutover_path.is_file():
        cutover = cutover_path.read_text(encoding="utf-8")
    else:
        cutover = ""
    if verification_path.exists() and not _repo_path_is_safe(
        root, POST_MERGE_VERIFICATION_PATH
    ):
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: verification evidence path is unsafe"
        )
        verification = ""
    elif verification_path.is_file():
        verification = verification_path.read_text(encoding="utf-8")
    else:
        verification = ""

    if cutover:
        if final_state != "ACCEPTED":
            errors.append(
                f"{CUTOVER_ACCEPTANCE_PATH}: cutover acceptance requires slice 110 ACCEPTED"
            )
        errors.extend(
            _singleton_metadata_errors(
                cutover,
                (
                    "Program",
                    "Status",
                    "Candidate commit",
                    "Accepted by",
                    "Accepted on",
                    "Decision reference",
                    "Recorded by",
                ),
                CUTOVER_ACCEPTANCE_PATH,
            )
        )
        for label, value in {
            "Program": "001-nunchi-v2-program",
            "Status": "CUTOVER_ACCEPTED",
            "Candidate commit": accepted_candidate,
            "Accepted by": "Zoe",
            "Recorded by": "v2-program-owner",
        }.items():
            if _clean_metadata(cutover, label) != value:
                errors.append(f"{CUTOVER_ACCEPTANCE_PATH}: {label} must be {value!r}")
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", _clean_metadata(cutover, "Accepted on")
        ):
            errors.append(f"{CUTOVER_ACCEPTANCE_PATH}: Accepted on must be an ISO date")
        if len(_clean_metadata(cutover, "Decision reference")) < 10:
            errors.append(
                f"{CUTOVER_ACCEPTANCE_PATH}: missing durable Decision reference"
            )

    if not verification:
        return errors
    errors.extend(
        _singleton_metadata_errors(
            verification,
            (
                "Program",
                "Status",
                "Accepted candidate commit",
                "Merged candidate commit",
                "Main ref",
                "Main commit",
                "Verified on",
                "Verification commands / results",
                "Evidence paths",
                "Documentation freshness",
                "Documentation commit",
            ),
            POST_MERGE_VERIFICATION_PATH,
        )
    )
    for label, value in {
        "Program": "001-nunchi-v2-program",
        "Status": "CUTOVER_VERIFIED",
    }.items():
        if _clean_metadata(verification, label) != value:
            errors.append(f"{POST_MERGE_VERIFICATION_PATH}: {label} must be {value!r}")
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", _clean_metadata(verification, "Verified on")
    ):
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: Verified on must be an ISO date"
        )
    if not cutover:
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: verification requires safe prior "
            f"{CUTOVER_ACCEPTANCE_PATH}"
        )
    accepted = _clean_metadata(verification, "Accepted candidate commit")
    merged = _clean_metadata(verification, "Merged candidate commit")
    main = _clean_metadata(verification, "Main commit")
    documentation_commit = _clean_metadata(verification, "Documentation commit")
    if accepted != accepted_candidate or accepted != _clean_metadata(
        cutover, "Candidate commit"
    ):
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: Accepted candidate commit must match "
            "the exact slice and cutover acceptance"
        )
    for label, commit in (
        ("Merged candidate commit", merged),
        ("Main commit", main),
        ("Documentation commit", documentation_commit),
    ):
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or not _git_commit_exists(
            root, commit
        ):
            errors.append(
                f"{POST_MERGE_VERIFICATION_PATH}: {label} must be an existing full Git SHA"
            )
    if _clean_metadata(verification, "Main ref") != "refs/heads/main":
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: Main ref must be 'refs/heads/main'"
        )
    local_main = _git_ref_commit(root, "refs/heads/main")
    if (
        local_main is None
        or not _git_commit_exists(root, main)
        or not _git_is_ancestor(root, main, local_main)
    ):
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: Main commit must be contained in local "
            "refs/heads/main"
        )
    if _git_commit_exists(root, accepted) and _git_commit_exists(root, merged):
        if not _git_is_ancestor(root, accepted, merged):
            errors.append(
                f"{POST_MERGE_VERIFICATION_PATH}: accepted candidate must be an ancestor "
                "of the merged candidate commit"
            )
    if _git_commit_exists(root, merged) and _git_commit_exists(root, main):
        if not _git_is_ancestor(root, merged, main):
            errors.append(
                f"{POST_MERGE_VERIFICATION_PATH}: merged candidate must be an ancestor "
                "of the verified main commit"
            )
    if _git_commit_exists(root, documentation_commit) and _git_commit_exists(
        root, main
    ):
        if documentation_commit == main or not _git_is_ancestor(
            root, main, documentation_commit
        ):
            errors.append(
                f"{POST_MERGE_VERIFICATION_PATH}: documentation commit must be a "
                "docs/evidence-only follow-up after the verified main commit"
            )
        if local_main and not _git_is_ancestor(root, documentation_commit, local_main):
            errors.append(
                f"{POST_MERGE_VERIFICATION_PATH}: documentation commit must be "
                "contained in local refs/heads/main"
            )
        changed_paths = _git_changed_paths(root, main, documentation_commit)

        def allowed_followup(path: str) -> bool:
            return path in {"README.md", "CHANGELOG.md"} or path.startswith(
                ("docs/", "evidence/")
            )

        if not changed_paths or any(
            not allowed_followup(path) for path in changed_paths
        ):
            errors.append(
                f"{POST_MERGE_VERIFICATION_PATH}: documentation follow-up must change "
                "only README.md, CHANGELOG.md, docs/, or evidence/"
            )
    verification_result = _clean_metadata(
        verification, "Verification commands / results"
    )
    if not verification_result.startswith("PASS — "):
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: verification commands/results must start "
            "with 'PASS — '"
        )
    if _clean_metadata(verification, "Documentation freshness") != "PASS":
        errors.append(
            f"{POST_MERGE_VERIFICATION_PATH}: Documentation freshness must be 'PASS'"
        )
    errors.extend(
        _ordinary_evidence_path_errors(
            root,
            POST_MERGE_VERIFICATION_PATH,
            "Evidence paths",
            _clean_metadata(verification, "Evidence paths"),
        )
    )
    return errors


def _terminal_integrator_assignment_errors(
    root: Path, integrator_assignment: str
) -> list[str]:
    """Require a durable slice-110 occupant before any 010-100 decision."""

    terminal_decision = False
    for dirname in EXPECTED_SLICES:
        if dirname == "110-v2-parity-cutover":
            continue
        paths = EXPECTED_LIFECYCLE_PATHS[dirname]
        acceptance = root / paths["acceptance"]
        handoff = root / paths["handoff"]
        if acceptance.is_file():
            terminal_decision = True
            break
        if handoff.is_file():
            try:
                if any(
                    _clean_metadata(record, "Status") == "REJECTED"
                    for record in _lifecycle_records(
                        handoff.read_text(encoding="utf-8")
                    )
                ):
                    terminal_decision = True
                    break
            except (OSError, UnicodeDecodeError):
                pass
    if terminal_decision and (
        not integrator_assignment or integrator_assignment.startswith("UNASSIGNED")
    ):
        return [
            "specs/110-v2-parity-cutover: v2-integrator must have a valid durable "
            "assignment before any 010-100 terminal acceptance or rejection"
        ]
    return []


def check_program(root: Path) -> list[str]:
    """Validate the V2 umbrella/slice graph and planning completeness."""

    errors: list[str] = []
    implementation_authorized, authorization_errors = (
        _implementation_authorization_state(root)
    )
    errors.extend(authorization_errors)
    specs = root / "specs"
    expected_directories = {"001-nunchi-v2-program", *EXPECTED_SLICES}
    actual_directories = (
        {path.name for path in specs.iterdir() if path.is_dir()}
        if specs.is_dir()
        else set()
    )
    if actual_directories != expected_directories:
        missing = sorted(expected_directories - actual_directories)
        extra = sorted(actual_directories - expected_directories)
        if missing:
            errors.append(f"specs/: missing planned directories {missing}")
        if extra:
            errors.append(f"specs/: unexpected planned directories {extra}")

    graph: dict[str, tuple[str, ...]] = {}
    slice_states: dict[str, str] = {}
    slice_assignments: dict[str, str] = {}
    owners: dict[str, str] = {}
    all_interface_ids: set[str] = set()
    all_nonfinal_scenes: set[str] = set()
    required_scenes = {f"S{number:02d}" for number in range(1, 17)}

    for dirname, expected in EXPECTED_SLICES.items():
        feature = specs / dirname
        if not feature.is_dir():
            continue
        required_files = {
            feature / "spec.md",
            feature / "plan.md",
            feature / "tasks.md",
            feature / "checklists" / "requirements.md",
        }
        actual_files = {path for path in feature.rglob("*") if path.is_file()}
        if actual_files != required_files:
            missing = sorted(
                str(path.relative_to(root)) for path in required_files - actual_files
            )
            extra = sorted(
                str(path.relative_to(root)) for path in actual_files - required_files
            )
            if missing:
                errors.append(
                    f"{feature.relative_to(root)}: missing required planning files {missing}"
                )
            if extra:
                errors.append(f"{feature.relative_to(root)}: unexpected files {extra}")
            if not required_files.issubset(actual_files):
                continue

        spec_text = (feature / "spec.md").read_text(encoding="utf-8")
        plan_text = (feature / "plan.md").read_text(encoding="utf-8")
        tasks_text = (feature / "tasks.md").read_text(encoding="utf-8")
        checklist_text = (feature / "checklists" / "requirements.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((spec_text, plan_text, tasks_text))

        artifact_texts = {
            "spec.md": spec_text,
            "plan.md": plan_text,
            "tasks.md": tasks_text,
        }
        observed_states: set[str] = set()
        planning_binding = (
            "planning uses python3 scripts/run_slice_workflow.py run nunchi-plan "
            f"specs/{dirname}; delivery uses python3 scripts/run_slice_workflow.py "
            f"run speckit specs/{dirname}"
        )
        delivery_binding = (
            f"python3 scripts/run_slice_workflow.py run speckit specs/{dirname}"
        )
        expected_preflight = (
            "performed atomically by the bound runner above; a paused run with an "
            "unchanged task graph resumes only with "
            "python3 scripts/run_slice_workflow.py resume <run-id>"
        )
        expected_activation = EXPECTED_ACTIVATION_PATHS[dirname]
        expected_lifecycle_paths = EXPECTED_LIFECYCLE_PATHS[dirname]
        expected_authority = "GRANTED" if implementation_authorized else "NOT_GRANTED"
        assigned_values: dict[str, str] = {}
        for artifact_name, artifact_text in artifact_texts.items():
            errors.extend(
                _singleton_metadata_errors(
                    artifact_text,
                    (
                        "Slice state",
                        "Program implementation authority",
                        "Assigned participant / source",
                        "SpecKit binding",
                        "Read-only preflight",
                        "Activation evidence",
                        "Candidate evidence",
                        "Handoff evidence",
                        "Acceptance evidence",
                    ),
                    f"{feature.relative_to(root)}/{artifact_name}",
                )
            )
            state = (_metadata_value(artifact_text, "Slice state") or "").strip("`")
            if state not in SLICE_STATES:
                errors.append(
                    f"{feature.relative_to(root)}/{artifact_name}: Slice state must be "
                    f"one of {SLICE_STATES}; observed {state!r}"
                )
            else:
                observed_states.add(state)

            authority = (
                _metadata_value(artifact_text, "Program implementation authority") or ""
            ).strip("`")
            if authority != expected_authority:
                errors.append(
                    f"{feature.relative_to(root)}/{artifact_name}: Program implementation "
                    f"authority must be {expected_authority!r}; observed {authority!r}"
                )

            assigned = (
                (_metadata_value(artifact_text, "Assigned participant / source") or "")
                .replace("`", "")
                .strip()
            )
            assigned_values[artifact_name] = assigned
            if not assigned:
                errors.append(
                    f"{feature.relative_to(root)}/{artifact_name}: missing assigned "
                    "participant and durable source"
                )

            binding = _clean_metadata(artifact_text, "SpecKit binding")
            expected_binding = (
                delivery_binding if artifact_name == "tasks.md" else planning_binding
            )
            if binding != expected_binding:
                errors.append(
                    f"{feature.relative_to(root)}/{artifact_name}: SpecKit binding must be "
                    f"{expected_binding!r}; observed {binding!r}"
                )

            preflight = _clean_metadata(artifact_text, "Read-only preflight")
            if preflight != expected_preflight:
                errors.append(
                    f"{feature.relative_to(root)}/{artifact_name}: Read-only preflight "
                    f"must be {expected_preflight!r}; observed {preflight!r}"
                )

            for label, stage in (
                ("Activation evidence", "activation"),
                ("Candidate evidence", "candidate"),
                ("Handoff evidence", "handoff"),
                ("Acceptance evidence", "acceptance"),
            ):
                evidence_value = _metadata_value(artifact_text, label) or ""
                expected_path = expected_lifecycle_paths[stage]
                if expected_path not in evidence_value:
                    errors.append(
                        f"{feature.relative_to(root)}/{artifact_name}: {label} must "
                        f"name {expected_path!r}"
                    )

        if len(observed_states) != 1:
            errors.append(
                f"{feature.relative_to(root)}: spec, plan, and tasks must declare one "
                f"consistent slice state; observed {sorted(observed_states)}"
            )
        slice_state = next(iter(observed_states), "")
        slice_states[dirname] = slice_state
        distinct_assignments = set(assigned_values.values())
        if len(distinct_assignments) != 1:
            errors.append(
                f"{feature.relative_to(root)}: spec, plan, and tasks must declare one "
                f"consistent assigned participant/source; observed {sorted(distinct_assignments)}"
            )
        assigned_participant = next(iter(distinct_assignments), "")
        slice_assignments[dirname] = assigned_participant
        if (
            assigned_participant
            and not assigned_participant.startswith("UNASSIGNED")
            and (
                " — " not in assigned_participant
                or len(assigned_participant.split(" — ", 1)[1].strip()) < 10
            )
        ):
            errors.append(
                f"{feature.relative_to(root)}: assigned participant must include a "
                "durable source after an em dash"
            )
        if assigned_participant and not assigned_participant.startswith("UNASSIGNED"):
            errors.extend(
                _assignment_errors(
                    root,
                    assigned_participant,
                    str(expected["owner"]),
                    feature.relative_to(root),
                )
            )
        activation_exists = (root / expected_activation).is_file()
        if not implementation_authorized:
            if slice_state != "PLANNED":
                errors.append(
                    f"{feature.relative_to(root)}: slice must remain PLANNED while "
                    "program implementation authority is NOT_GRANTED"
                )
        if slice_state in {"READY", "ACTIVE", "CONVERGED", "HANDOFF_READY", "ACCEPTED"}:
            if not implementation_authorized:
                errors.append(
                    f"{feature.relative_to(root)}: {slice_state} requires valid program "
                    "implementation authority"
                )
            if not activation_exists:
                errors.append(
                    f"{feature.relative_to(root)}: {slice_state} requires "
                    f"{expected_activation}"
                )
            for artifact_name, assigned in assigned_values.items():
                if assigned.startswith("UNASSIGNED"):
                    errors.append(
                        f"{feature.relative_to(root)}/{artifact_name}: {slice_state} "
                        "requires a named participant and durable assignment source"
                    )
        errors.extend(
            _slice_lifecycle_evidence_errors(
                root,
                dirname,
                expected,
                slice_state,
                assigned_participant,
                tasks_text,
            )
        )

        if PINNED_VAULT_COMMIT not in spec_text:
            errors.append(
                f"{feature.relative_to(root)}/spec.md: authority source must cite "
                f"Aleph Vault merge {PINNED_VAULT_COMMIT}"
            )

        for section in REQUIRED_SPEC_SECTIONS:
            if section not in spec_text:
                errors.append(
                    f"{feature.relative_to(root)}/spec.md: missing section {section!r}"
                )
        for section in REQUIRED_PLAN_SECTIONS:
            if section not in plan_text:
                errors.append(
                    f"{feature.relative_to(root)}/plan.md: missing section {section!r}"
                )
        errors.extend(
            _documentation_planning_errors(
                dirname,
                spec_text,
                plan_text,
                tasks_text,
                checklist_text,
            )
        )
        placeholder = PLANNING_PLACEHOLDER.search(combined)
        if placeholder:
            errors.append(
                f"{feature.relative_to(root)}: unresolved planning placeholder {placeholder.group(0)!r}"
            )

        for required_term in ("scene_id", "manifest", "immutable"):
            if required_term not in combined:
                errors.append(
                    f"{feature.relative_to(root)}: missing cross-slice planning "
                    f"requirement {required_term!r}"
                )
        bypass_consumers = {
            "010-v2-contract",
            "030-v2-core-attention",
            "040-v2-participant-wake",
            "060-v2-hermes",
            "070-v2-claude-code",
            "080-v2-codex",
            "090-v2-channel-adapters",
            "100-v2-security-provenance",
            "110-v2-parity-cutover",
        }
        if dirname in bypass_consumers and "PREATTENTION_BYPASS" not in combined:
            errors.append(
                f"{feature.relative_to(root)}: missing canonical trusted-bypass lifecycle coverage"
            )

        owner = _metadata_value(spec_text, "Accountable owner lane")
        owner = owner.strip("`") if owner else ""
        if owner != expected["owner"]:
            errors.append(
                f"{feature.relative_to(root)}/spec.md: owner must be {expected['owner']!r}; observed {owner!r}"
            )
        elif owner in owners:
            errors.append(
                f"{feature.relative_to(root)}/spec.md: owner {owner!r} also owns {owners[owner]}"
            )
        else:
            owners[owner] = dirname

        branch = (_metadata_value(spec_text, "Feature Branch") or "").strip("`")
        if branch != expected["branch"]:
            errors.append(
                f"{feature.relative_to(root)}/spec.md: branch must be {expected['branch']!r}; observed {branch!r}"
            )
        if expected["branch"] not in plan_text or expected["worktree"] not in plan_text:
            errors.append(
                f"{feature.relative_to(root)}/plan.md: missing canonical branch/worktree "
                f"{expected['branch']!r} / {expected['worktree']!r}"
            )

        dependencies = _slice_ids(_metadata_value(spec_text, "Depends on"))
        feeds = _slice_ids(_metadata_value(spec_text, "Feeds"))
        if dependencies != expected["dependencies"]:
            errors.append(
                f"{feature.relative_to(root)}/spec.md: dependencies must be "
                f"{expected['dependencies']}; observed {dependencies}"
            )
        if feeds != expected["feeds"]:
            errors.append(
                f"{feature.relative_to(root)}/spec.md: feeds must be {expected['feeds']}; observed {feeds}"
            )
        graph[dirname[:3]] = dependencies

        errors.extend(
            _checked_slice_task_errors(
                feature.relative_to(root),
                tasks_text,
                implementation_authorized,
                slice_state,
                activation_exists,
            )
        )
        task_numbers: list[int] = []
        for line_number, line in enumerate(tasks_text.splitlines(), 1):
            if not line.startswith(("- [ ] T", "- [x] T", "- [X] T")):
                continue
            normalized_line = re.sub(r"^- \[[xX]\]", "- [ ]", line)
            match = TASK_LINE.fullmatch(normalized_line)
            if not match:
                errors.append(
                    f"{feature.relative_to(root)}/tasks.md:{line_number}: invalid task format"
                )
                continue
            task_numbers.append(int(match.group(1)))
            if MANAGED_REFERENCE.search(normalized_line):
                errors.append(
                    f"{feature.relative_to(root)}/tasks.md:{line_number}: product task targets managed path"
                )
        if not task_numbers:
            errors.append(
                f"{feature.relative_to(root)}/tasks.md: slice must have a nonempty task manifest"
            )
        if task_numbers != list(range(1, len(task_numbers) + 1)):
            errors.append(
                f"{feature.relative_to(root)}/tasks.md: T identifiers must be sequential from T001"
            )

        observed_interfaces = set(INTERFACE_ID.findall(combined))
        all_interface_ids.update(observed_interfaces)
        produced = _markdown_subsection(plan_text, "Produces")
        for interface, interface_owner in CANONICAL_INTERFACES.items():
            if interface_owner == dirname and interface not in produced:
                errors.append(
                    f"{feature.relative_to(root)}/plan.md: owner does not produce {interface}"
                )

        scenes = set(SCENE_ID.findall(plan_text))
        if not scenes:
            errors.append(
                f"{feature.relative_to(root)}/plan.md: no shared S01-S16 scene mapping"
            )
        if dirname == "110-v2-parity-cutover":
            if scenes != required_scenes:
                errors.append(
                    f"{feature.relative_to(root)}/plan.md: final parity must map exactly S01-S16"
                )
        else:
            all_nonfinal_scenes.update(scenes)

        for token in ("tests/v2/", "evals/v2/", "evidence/v2/"):
            if token not in plan_text:
                errors.append(
                    f"{feature.relative_to(root)}/plan.md: missing ordinary target {token!r}"
                )

    integrator_assignment = slice_assignments.get("110-v2-parity-cutover", "")
    errors.extend(_terminal_integrator_assignment_errors(root, integrator_assignment))

    errors.extend(_slice_dependency_state_errors(slice_states))
    unknown_interfaces = all_interface_ids - set(CANONICAL_INTERFACES)
    if unknown_interfaces:
        errors.append(
            f"specs/: non-canonical interface IDs present {sorted(unknown_interfaces)}"
        )
    if all_nonfinal_scenes != required_scenes:
        errors.append(
            "specs/: implementing slices must collectively map S01-S16; "
            f"missing {sorted(required_scenes - all_nonfinal_scenes)}"
        )
    cycle = _graph_cycle(graph)
    if cycle:
        errors.append(f"specs/: dependency cycle {' -> '.join(cycle)}")

    umbrella = specs / "001-nunchi-v2-program"
    required_umbrella = {
        umbrella / "spec.md",
        umbrella / "plan.md",
        umbrella / "research.md",
        umbrella / "tasks.md",
        umbrella / "checklists" / "requirements.md",
        umbrella / "checklists" / "program-readiness.md",
    }
    actual_umbrella = (
        {path for path in umbrella.rglob("*") if path.is_file()}
        if umbrella.is_dir()
        else set()
    )
    if actual_umbrella != required_umbrella:
        errors.append(
            "specs/001-nunchi-v2-program: umbrella artifact set is incomplete or unexpected"
        )
    else:
        umbrella_artifacts = {
            path.relative_to(umbrella).as_posix(): path.read_text(encoding="utf-8")
            for path in required_umbrella
        }
        umbrella_text = "\n".join(umbrella_artifacts.values())
        for interface in CANONICAL_INTERFACES:
            if interface not in umbrella_text:
                errors.append(
                    f"specs/001-nunchi-v2-program: missing {interface} from registry"
                )
        for scene in required_scenes:
            if scene not in umbrella_text:
                errors.append(f"specs/001-nunchi-v2-program: missing scene {scene}")
        declared_program_states: dict[str, str] = {}
        for artifact_name in ("spec.md", "plan.md", "tasks.md"):
            errors.extend(
                _singleton_metadata_errors(
                    umbrella_artifacts[artifact_name],
                    (
                        "Program state",
                        "Program implementation authority",
                        "Assigned program participant / source (declaration)",
                    ),
                    f"specs/001-nunchi-v2-program/{artifact_name}",
                )
            )
            state = (
                _metadata_value(umbrella_artifacts[artifact_name], "Program state")
                or ""
            ).strip("`")
            declared_program_states[artifact_name] = state
            if state not in PROGRAM_STATES:
                errors.append(
                    f"specs/001-nunchi-v2-program/{artifact_name}: Program state "
                    f"must be canonical; observed {state!r}"
                )
        if len(set(declared_program_states.values())) != 1:
            errors.append(
                "specs/001-nunchi-v2-program: spec, plan, and tasks must declare "
                f"one program state; observed {declared_program_states}"
            )
        program_state = next(iter(declared_program_states.values()), "")
        expected_program_authority = (
            "GRANTED" if implementation_authorized else "NOT_GRANTED"
        )
        program_assignments: dict[str, str] = {}
        for artifact_name in ("spec.md", "plan.md", "tasks.md"):
            program_authority = (
                _metadata_value(
                    umbrella_artifacts[artifact_name],
                    "Program implementation authority",
                )
                or ""
            ).strip("`")
            if program_authority != expected_program_authority:
                errors.append(
                    f"specs/001-nunchi-v2-program/{artifact_name}: Program "
                    f"implementation authority must be {expected_program_authority!r}; "
                    f"observed {program_authority!r}"
                )
            program_assignments[artifact_name] = _clean_metadata(
                umbrella_artifacts[artifact_name],
                "Assigned program participant / source (declaration)",
            )
        if len(set(program_assignments.values())) != 1:
            errors.append(
                "specs/001-nunchi-v2-program: spec, plan, and tasks must declare "
                f"one program participant/source; observed {program_assignments}"
            )
        program_assignment = next(iter(program_assignments.values()), "")
        if (
            program_assignment
            and not program_assignment.startswith("UNASSIGNED")
            and (
                " — " not in program_assignment
                or len(program_assignment.split(" — ", 1)[1].strip()) < 10
            )
        ):
            errors.append(
                "specs/001-nunchi-v2-program: program participant must include a "
                "durable source after an em dash"
            )
        if program_assignment and not program_assignment.startswith("UNASSIGNED"):
            errors.extend(
                _assignment_errors(
                    root,
                    program_assignment,
                    "v2-program-owner",
                    "specs/001-nunchi-v2-program",
                )
            )

        cutover_path = root / CUTOVER_ACCEPTANCE_PATH
        verification_path = root / POST_MERGE_VERIFICATION_PATH
        cutover_exists = cutover_path.is_file()
        verification_exists = verification_path.is_file()
        final_state = slice_states.get("110-v2-parity-cutover", "")
        expected_program_state = _derived_program_state(
            slice_states,
            planning_baseline_accepted=_planning_baseline_accepted(root),
            cutover_accepted=cutover_exists,
            post_merge_verified=verification_exists,
        )
        if program_state != expected_program_state:
            errors.append(
                "specs/001-nunchi-v2-program: declared program state must be "
                f"{expected_program_state!r} for the observed slice/evidence state; "
                f"observed {program_state!r}"
            )
        if expected_program_state in {
            "DELIVERY",
            "INTEGRATION",
            "CUTOVER_ACCEPTED",
            "CUTOVER_VERIFIED",
        } and (not program_assignment or program_assignment.startswith("UNASSIGNED")):
            errors.append(
                "specs/001-nunchi-v2-program: active delivery requires an assigned "
                "v2-program-owner with a durable source"
            )

        final_acceptance = root / Path(
            EXPECTED_LIFECYCLE_PATHS["110-v2-parity-cutover"]["acceptance"]
        )
        accepted_candidate = ""
        if final_acceptance.is_file():
            try:
                accepted_candidate = _clean_metadata(
                    final_acceptance.read_text(encoding="utf-8"), "Candidate commit"
                )
            except (OSError, UnicodeDecodeError):
                pass
        if cutover_exists:
            if final_state != "ACCEPTED":
                errors.append(
                    f"{CUTOVER_ACCEPTANCE_PATH}: cutover acceptance requires slice 110 "
                    "to be ACCEPTED"
                )
            try:
                cutover = cutover_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"{CUTOVER_ACCEPTANCE_PATH}: unreadable ({exc})")
                cutover = ""
            for label, value in {
                "Program": "001-nunchi-v2-program",
                "Status": "CUTOVER_ACCEPTED",
                "Accepted by": "Zoe",
                "Candidate commit": accepted_candidate,
            }.items():
                observed = _clean_metadata(cutover, label)
                if observed != value:
                    errors.append(
                        f"{CUTOVER_ACCEPTANCE_PATH}: {label} must be {value!r}; "
                        f"observed {observed!r}"
                    )
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", _clean_metadata(cutover, "Accepted on")
            ):
                errors.append(
                    f"{CUTOVER_ACCEPTANCE_PATH}: Accepted on must be an ISO date"
                )
            if len(_clean_metadata(cutover, "Decision reference")) < 10:
                errors.append(
                    f"{CUTOVER_ACCEPTANCE_PATH}: missing durable Decision reference"
                )
        if verification_exists:
            if not cutover_exists:
                errors.append(
                    f"{POST_MERGE_VERIFICATION_PATH}: verification requires prior "
                    f"{CUTOVER_ACCEPTANCE_PATH}"
                )
            try:
                verification = verification_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"{POST_MERGE_VERIFICATION_PATH}: unreadable ({exc})")
                verification = ""
            for label, value in {
                "Program": "001-nunchi-v2-program",
                "Status": "CUTOVER_VERIFIED",
            }.items():
                observed = _clean_metadata(verification, label)
                if observed != value:
                    errors.append(
                        f"{POST_MERGE_VERIFICATION_PATH}: {label} must be {value!r}; "
                        f"observed {observed!r}"
                    )
            main_commit = _clean_metadata(verification, "Main commit")
            if not re.fullmatch(r"[0-9a-f]{40}", main_commit):
                errors.append(
                    f"{POST_MERGE_VERIFICATION_PATH}: Main commit must be a full Git SHA"
                )
            elif _git_commit_exists(root, main_commit) is False:
                errors.append(
                    f"{POST_MERGE_VERIFICATION_PATH}: Main commit does not exist in Git"
                )
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", _clean_metadata(verification, "Verified on")
            ):
                errors.append(
                    f"{POST_MERGE_VERIFICATION_PATH}: Verified on must be an ISO date"
                )
            if (
                len(_clean_metadata(verification, "Verification commands / results"))
                < 10
            ):
                errors.append(
                    f"{POST_MERGE_VERIFICATION_PATH}: missing verification commands/results"
                )
        errors.extend(
            _cutover_evidence_errors(
                root,
                final_state=final_state,
                accepted_candidate=accepted_candidate,
            )
        )
        normalized_umbrella_text = " ".join(umbrella_text.split())
        umbrella_tasks = umbrella_artifacts["tasks.md"]
        for forbidden_header in (
            "| Slice | Current state |",
            "| Slice | State | Assigned participant",
            "| Slice | Assigned participant / source |",
        ):
            if forbidden_header in umbrella_tasks:
                errors.append(
                    "specs/001-nunchi-v2-program/tasks.md: umbrella must not duplicate "
                    f"mutable slice state/occupancy ({forbidden_header!r})"
                )
        for token in (
            "PLANNING -> READY -> DELIVERY -> INTEGRATION -> CUTOVER_ACCEPTED",
            "PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY -> ACCEPTED",
            str(IMPLEMENTATION_AUTHORIZATION_PATH),
            "no central",
        ):
            if token.lower() not in normalized_umbrella_text.lower():
                errors.append(
                    "specs/001-nunchi-v2-program: missing lifecycle authority text "
                    f"{token!r}"
                )

    return errors


def check_central_state_artifacts(root: Path) -> list[str]:
    """Reject a second mutable source of truth for per-slice state or assignment."""

    errors: list[str] = []
    evidence_v2 = root / "evidence" / "v2"
    forbidden_name = re.compile(
        r"^(?:(?:slice|program)[-_]?(?:status|state|registry)|"
        r"assignments?(?:[-_]?registry)?)(?:[-_.].*)?$",
        re.IGNORECASE,
    )
    candidates: set[Path] = set()
    if evidence_v2.is_dir():
        candidates.update(path for path in evidence_v2.rglob("*") if path.is_file())
    umbrella = root / "specs" / "001-nunchi-v2-program"
    if umbrella.is_dir():
        candidates.update(path for path in umbrella.rglob("*") if path.is_file())

    canonical_ids = tuple(dirname[:3] for dirname in EXPECTED_SLICES)
    for path in sorted(candidates):
        if forbidden_name.fullmatch(path.name):
            errors.append(
                f"{path.relative_to(root)}: central mutable slice state/assignment "
                "artifact is forbidden; use per-slice transition evidence"
            )
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        aggregate_header = False
        for line in text.splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [
                cell.strip().lower() for cell in line.strip().strip("|").split("|")
            ]
            if not any(cell == "slice" or cell.startswith("slice ") for cell in cells):
                continue
            if any(
                any(
                    term in cell
                    for term in (
                        "state",
                        "status",
                        "progress",
                        "assign",
                        "occup",
                        "participant",
                    )
                )
                for cell in cells
            ):
                aggregate_header = True
                break
        ids_in_text = {
            slice_id
            for slice_id in canonical_ids
            if re.search(rf"(?<!\d){slice_id}(?!\d)", text)
        }
        lifecycle_states = (
            "PLANNED|READY|ACTIVE|CONVERGED|HANDOFF_READY|ACCEPTED|REJECTED"
        )
        direct_registry_ids = {
            match.group(1)
            for match in re.finditer(
                rf"(?im)^\s*(?:[-*]\s*)?[`\"']?(\d{{3}})[`\"']?\s*[:|—-]"
                rf"[^\n]*(?:{lifecycle_states})\b",
                text,
            )
            if match.group(1) in canonical_ids
        }
        structured_registry_ids: set[str] = set()
        for slice_id in ids_in_text:
            block = re.search(
                rf"(?is)(?<!\d){slice_id}(?!\d).{{0,240}}?"
                rf"(?:state|status|progress)[\"']?\s*[:=]\s*[\"']?"
                rf"(?:{lifecycle_states})\b",
                text,
            )
            occupant = re.search(
                rf"(?is)(?<!\d){slice_id}(?!\d).{{0,240}}?"
                r"(?:assigned|occupant|participant)[\"']?\s*[:=]\s*[\"']?"
                r"(?!UNASSIGNED\b)[A-Za-z0-9]",
                text,
            )
            if block or occupant:
                structured_registry_ids.add(slice_id)
        structured_registry = len(direct_registry_ids | structured_registry_ids) >= 2
        if aggregate_header or structured_registry:
            errors.append(
                f"{path.relative_to(root)}: aggregate per-slice state/occupancy content "
                "is forbidden; derive it from per-slice evidence"
            )
    return errors


def check_active_execution_language(root: Path) -> list[str]:
    """Keep active guidance slice-centric while leaving immutable history intact."""

    errors: list[str] = []
    candidates: set[Path] = {
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / "README.md",
        root / "CHANGELOG.md",
        root / "evidence" / "README.md",
        root / "evidence" / "governance" / "slice-lifecycle-amendment-2026-07-11.md",
    }
    for managed_root in (
        root / ".specify" / "memory",
        root / ".specify" / "templates",
        root / ".specify" / "workflows",
        root / "specs",
        root / "docs",
    ):
        if not managed_root.exists():
            continue
        candidates.update(
            path
            for path in managed_root.rglob("*")
            if path.is_file() and path.suffix in {".md", ".json", ".yaml", ".yml"}
        )

    retired_numbered_goal = re.compile(
        r"\bgoal\s*-?\s*[12]\b|\btwo-goal\b|v2-goal-2-authorization",
        re.IGNORECASE,
    )
    for path in sorted(candidates):
        if not path.exists() or "archive" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            match = retired_numbered_goal.search(line)
            if match:
                errors.append(
                    f"{path.relative_to(root)}:{line_number}: active execution spine "
                    f"uses retired numbered-goal language {match.group(0)!r}"
                )
    return errors


def _iter_executable_files(root: Path):
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        yield pyproject
    for dirname in SCAN_ROOTS:
        base = root / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in EXECUTABLE_SUFFIXES:
                continue
            rel = path.relative_to(root)
            if "fixtures" in rel.parts:
                continue
            if rel.as_posix() in {
                "scripts/check_governance.py",
                "scripts/check_slice_binding.py",
                "scripts/run_slice_workflow.py",
                "tests/test_governance.py",
                "tests/test_slice_workflow_runner.py",
            }:
                continue
            yield path


def check_runtime_dependencies(root: Path) -> list[str]:
    errors: list[str] = []
    for path in _iter_executable_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in MANAGED_REFERENCE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{path.relative_to(root)}:{line}: executable/build/test path depends on "
                f"managed path {match.group(0)!r}"
            )

    documentation = {
        root / "README.md",
        root / "AGENTS.md",
        root / "CLAUDE.md",
        *(root / "docs").rglob("*.md"),
        *(root / "evidence").rglob("*.md"),
        *(root / "integrations").rglob("*.md"),
    }
    for path in sorted(documentation):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            normalized_target = target.strip().strip("<>")
            target_without_anchor = normalized_target.split("#", 1)[0]
            if MANAGED_REFERENCE.search(target_without_anchor):
                errors.append(
                    f"{path.relative_to(root)}: product documentation links to managed path "
                    f"{target!r}"
                )
                continue
            if (
                not target_without_anchor
                or "://" in target_without_anchor
                or target_without_anchor.startswith(("mailto:", "/"))
            ):
                continue
            local_target = (path.parent / target_without_anchor).resolve()
            if not local_target.exists():
                errors.append(
                    f"{path.relative_to(root)}: local Markdown link target does not exist "
                    f"{target!r}"
                )
    return errors


def _check_installed_direct_url(tool_dir: Path) -> list[str]:
    candidates = sorted(
        tool_dir.glob(
            "specify-cli/lib/python*/site-packages/"
            "specify_cli-*.dist-info/direct_url.json"
        )
    )
    if len(candidates) != 1:
        return [
            "installed specify-cli must expose exactly one PEP 610 direct_url.json; "
            f"observed {len(candidates)}"
        ]
    try:
        direct_url = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"installed specify-cli direct_url.json is unreadable: {exc}"]
    vcs = direct_url.get("vcs_info", {})
    if (
        direct_url.get("url") != "https://github.com/github/spec-kit.git"
        or vcs.get("vcs") != "git"
        or vcs.get("commit_id") != PINNED_SPECKIT_COMMIT
        or vcs.get("requested_revision") != PINNED_SPECKIT_COMMIT
    ):
        return [
            "installed specify-cli source/commit must match the immutable "
            f"SpecKit pin {PINNED_SPECKIT_COMMIT}"
        ]
    return []


def check_cli(root: Path) -> list[str]:
    del root
    # Color-forcing environments (FORCE_COLOR) make uv/specify emit ANSI codes
    # on stdout; the version comparison and Path(stdout) parsing below need
    # plain text.
    plain_env = {**os.environ, "NO_COLOR": "1"}
    plain_env.pop("FORCE_COLOR", None)
    try:
        completed = subprocess.run(
            ["specify", "--version"],
            check=False,
            capture_output=True,
            text=True,
            env=plain_env,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"specify CLI unavailable: {exc}"]
    observed = completed.stdout.strip()
    expected = f"specify {PINNED_SPECKIT_VERSION}"
    if completed.returncode != 0 or observed != expected:
        return [f"specify CLI must report {expected!r}; observed {observed!r}"]
    try:
        tool_dir_result = subprocess.run(
            ["uv", "tool", "dir"],
            check=False,
            capture_output=True,
            text=True,
            env=plain_env,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"uv tool metadata unavailable: {exc}"]
    if tool_dir_result.returncode != 0:
        return [
            "uv tool dir failed while verifying the installed SpecKit commit: "
            f"{tool_dir_result.stderr.strip()}"
        ]
    return _check_installed_direct_url(Path(tool_dir_result.stdout.strip()))


def validate(root: Path, *, include_cli: bool = False) -> list[str]:
    errors = check_pin(root)
    errors.extend(check_control_plane(root))
    errors.extend(check_governance_documents(root))
    errors.extend(check_historical_evidence(root))
    errors.extend(check_workflow_surface(root))
    errors.extend(check_program(root))
    errors.extend(check_central_state_artifacts(root))
    errors.extend(check_active_execution_language(root))
    errors.extend(check_runtime_dependencies(root))
    if include_cli:
        errors.extend(check_cli(root))
    return sorted(set(errors))


def task_manifest_state_for_slice(
    root: Path, slice_directory: str,
) -> tuple[str, str, str]:
    """Return initial IDs/digest plus literal completed IDs for one slice."""

    expected = {f"specs/{dirname}" for dirname in EXPECTED_SLICES}
    if slice_directory not in expected:
        raise ValueError(
            "task manifest path must be one exact canonical slice directory"
        )
    task_relative = Path(slice_directory) / "tasks.md"
    task_path = root / task_relative
    if not _repo_path_is_safe(root, task_relative, require_file=True):
        raise ValueError("bound slice tasks.md is missing or unsafe")
    tasks_text = task_path.read_text(encoding="utf-8")
    entries = _validated_task_entries(tasks_text)
    task_ids, digest = _task_manifest(entries)
    completed_ids = ", ".join(_checked_task_ids(tasks_text))
    return task_ids, digest, completed_ids


def task_manifest_for_slice(root: Path, slice_directory: str) -> tuple[str, str]:
    """Return the canonical initial task IDs and digest for one planned slice."""

    task_ids, digest, _completed_ids = task_manifest_state_for_slice(
        root, slice_directory,
    )
    return task_ids, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-cli",
        action="store_true",
        help="also require the installed specify CLI to match the repository pin",
    )
    parser.add_argument(
        "--task-manifest",
        metavar="SPECS/EXACT-SLICE",
        help="print canonical lifecycle task-manifest metadata without changing files",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    if args.task_manifest:
        if args.check_cli:
            parser.error("--task-manifest cannot be combined with --check-cli")
        try:
            task_ids, digest, completed_ids = task_manifest_state_for_slice(
                root, args.task_manifest,
            )
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"**Initial task IDs**: {task_ids}")
        print(f"**Initial tasks SHA256**: {digest}")
        print(f"**Completed task IDs**: {completed_ids}")
        print(f"**Tasks SHA256**: {digest}")
        return 0
    errors = validate(root, include_cli=args.check_cli)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    suffix = " + CLI" if args.check_cli else ""
    print(f"governance boundary{suffix}: OK (SpecKit {PINNED_SPECKIT_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
