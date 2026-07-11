#!/usr/bin/env python3
"""Validate Nunchi's SpecKit pin and control-plane/product boundary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


PINNED_SPECKIT_VERSION = "0.12.11"
PINNED_SPECKIT_COMMIT = "e802a7dd52a6eceba9403cbbf40e60dced043238"
PINNED_CONSTITUTION_VERSION = "2.1.0"
PINNED_VAULT_COMMIT = "c834e8c"
GOAL_2_AUTHORIZATION_PATH = Path(
    "evidence/governance/v2-goal-2-authorization.md"
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
        "dependencies": ("010", "020", "030", "040", "050", "060", "070", "080", "090", "100"),
        "feeds": (),
        "branch": "integration/v2",
        "worktree": ".worktrees/v2-integration/",
    },
}

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
        errors.append(".specify/integration.json: Codex must be the default integration")

    for name in ("codex", "claude", "speckit"):
        manifest = _json(specify / "integrations" / f"{name}.manifest.json", errors)
        if manifest.get("version") != PINNED_SPECKIT_VERSION:
            errors.append(f".specify/integrations/{name}.manifest.json: version mismatch")

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
            path.name
            for path in integration_root.glob("speckit-*")
            if path.is_dir()
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
    if specs.exists():
        for path in specs.rglob("*"):
            rel = path.relative_to(root)
            if path.is_symlink():
                errors.append(f"{rel}: symlinks are forbidden in the control plane")
                continue
            if path.is_dir():
                if FORBIDDEN_SPEC_PARTS.intersection(rel.parts):
                    errors.append(f"{rel}: product-artifact directory is forbidden under specs/")
                continue
            if FORBIDDEN_SPEC_PARTS.intersection(rel.parts):
                errors.append(f"{rel}: product artifact is forbidden under specs/")
                continue
            if "checklists" in rel.parts:
                if path.suffix != ".md":
                    errors.append(f"{rel}: checklist artifacts must be Markdown planning files")
                continue
            if path.name not in ALLOWED_SPEC_FILES:
                errors.append(
                    f"{rel}: only spec/plan/tasks/research/README and checklist Markdown "
                    "are allowed under specs/"
                )

    for base in (
        root / ".specify",
        root / ".agents" / "skills",
        root / ".claude" / "skills",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_symlink():
                errors.append(
                    f"{path.relative_to(root)}: managed control-plane paths may not symlink product assets"
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
            str(GOAL_2_AUTHORIZATION_PATH),
            "directory wildcard or generic path is",
        ),
        ".specify/templates/plan-template.md": (
            "Aggregate records MUST carry stable scene and",
            "scene-to-record result manifest",
            "## Documentation Impact and Freshness",
            "The `README.md` row is mandatory",
            "Generic directory rows are invalid",
        ),
        ".specify/templates/spec-template.md": (
            "## Documentation Freshness *(mandatory)*",
            "Every implementation MUST review `README.md`",
            "Generic directories or wildcards",
        ),
        ".specify/templates/tasks-template.md": (
            "evidence record and task status document authorization but never grant it",
            "A unit-only social-quality claim is invalid",
            "Documentation is a blocking implementation task",
            "documentation-freshness gate passes",
            "every exact row in `plan.md` §Documentation Impact and Freshness",
        ),
        ".specify/templates/checklist-template.md": (
            "Mandatory `README.md` and affected-docs freshness dispositions",
            "Reject a bare `NO_IMPACT`",
            "Reject a directory wildcard",
        ),
        "AGENTS.md": (
            "SpecKit-managed paths are control plane only",
            "Trusted preattention bypass wakes directly",
            PINNED_VAULT_COMMIT,
            "## Documentation freshness",
            "Use exactly one disposition per reviewed surface",
            str(GOAL_2_AUTHORIZATION_PATH),
        ),
        "CLAUDE.md": (
            "continuation authority out of classifier input",
            "immutable singly",
            "documentation-freshness gate",
            str(GOAL_2_AUTHORIZATION_PATH),
        ),
        "README.md": (
            "post-convergence documentation-freshness gate",
            "evidence-backed `NO_IMPACT`",
            "directory wildcard does not satisfy the gate",
            str(GOAL_2_AUTHORIZATION_PATH),
        ),
        "docs/governance/execution-spine.md": (
            "## Documentation freshness",
            "The workflow's `documentation-freshness` gate",
            str(GOAL_2_AUTHORIZATION_PATH),
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
        for forbidden in ("Tests are OPTIONAL", "Record Goal 2 authorization and dependency readiness in this task file"):
            if forbidden in text:
                errors.append(
                    ".specify/templates/tasks-template.md: stock template contradicts "
                    f"Nunchi governance ({forbidden!r})"
                )
    return errors


def check_workflow_surface(root: Path) -> list[str]:
    """Require runnable helpers and a skill for each workflow command."""

    errors: list[str] = []
    scripts = root / ".specify" / "scripts" / "bash"
    for name in sorted(REQUIRED_BASH_SCRIPTS):
        path = scripts / name
        if not path.is_file():
            errors.append(f"{path.relative_to(root)}: required SpecKit helper is missing")
        elif path.stat().st_mode & 0o111 == 0:
            errors.append(f"{path.relative_to(root)}: SpecKit helper must be executable")

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
        for command in WORKFLOW_COMMAND.findall(contents[name]):
            skill = command.replace(".", "-")
            for integration in (".agents", ".claude"):
                skill_file = root / integration / "skills" / skill / "SKILL.md"
                if not skill_file.is_file():
                    errors.append(
                        f"{path.relative_to(root)}: command {command!r} has no "
                        f"installed {integration} skill {skill!r}"
                    )

    planning = contents.get("nunchi-plan", "")
    if "command: speckit.implement" in planning:
        errors.append("nunchi-plan workflow must not contain an implementation command")

    full = contents.get("speckit", "")
    gate = full.find("- id: goal-2-authorization")
    implementation = full.find("command: speckit.implement")
    if gate < 0 or implementation < 0 or gate > implementation:
        errors.append(
            "speckit workflow must place the Goal 2 authorization gate before implementation"
        )
    if str(GOAL_2_AUTHORIZATION_PATH) not in full:
        errors.append(
            "speckit workflow must require the external Goal 2 authorization record"
        )
    convergence = full.find("command: speckit.converge")
    documentation = full.find("- id: documentation-freshness")
    handoff = full.find("- id: integration-handoff")
    if (
        convergence < 0
        or documentation < 0
        or handoff < 0
        or not convergence < documentation < handoff
    ):
        errors.append(
            "speckit workflow must place documentation freshness after "
            "convergence and before integration handoff"
        )

    registry = _json(root / ".specify" / "workflows" / "workflow-registry.json", errors)
    registered = registry.get("workflows", {})
    expected_versions = {"speckit": "2.1.0", "nunchi-plan": "1.1.0"}
    for name, version in expected_versions.items():
        observed = registered.get(name, {}) if isinstance(registered, dict) else {}
        if observed.get("version") != version:
            errors.append(
                f".specify/workflows/workflow-registry.json: {name} must be version {version}"
            )
    return errors


def _metadata_value(text: str, label: str) -> str | None:
    marker = f"**{label}**:"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(marker):
            continue
        value = line[len(marker) :].strip()
        continuation: list[str] = []
        for following in lines[index + 1 :]:
            if not following.strip() or following.startswith("#") or following.startswith("**"):
                break
            continuation.append(following.strip())
        return " ".join([value, *continuation]).strip()
    return None


def _slice_ids(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    known = {name[:3] for name in EXPECTED_SLICES}
    return tuple(dict.fromkeys(match for match in re.findall(r"(?<!\d)\d{3}(?!\d)", value) if match in known))


def _goal_2_authorization_state(root: Path) -> tuple[bool, list[str]]:
    """Return whether a separately granted Goal 2 authorization is validly recorded."""

    path = root / GOAL_2_AUTHORIZATION_PATH
    if not path.exists():
        return False, []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, [f"{GOAL_2_AUTHORIZATION_PATH}: cannot read ({exc})"]

    errors: list[str] = []
    expected = {
        "Program": "001-nunchi-v2-program",
        "Status": "AUTHORIZED",
        "Authorized by": "Zoe",
    }
    for label, value in expected.items():
        observed = (_metadata_value(text, label) or "").strip("`")
        if observed != value:
            errors.append(
                f"{GOAL_2_AUTHORIZATION_PATH}: {label} must be {value!r}; "
                f"observed {observed!r}"
            )

    authorized_on = (_metadata_value(text, "Authorized on") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", authorized_on):
        errors.append(
            f"{GOAL_2_AUTHORIZATION_PATH}: Authorized on must be an ISO date"
        )
    starting_commit = (_metadata_value(text, "Starting commit") or "").strip("`")
    if not re.fullmatch(r"[0-9a-f]{40}", starting_commit):
        errors.append(
            f"{GOAL_2_AUTHORIZATION_PATH}: Starting commit must be a full Git SHA"
        )
    objective = (_metadata_value(text, "Objective") or "").strip()
    if len(objective) < 40:
        errors.append(
            f"{GOAL_2_AUTHORIZATION_PATH}: Objective must record the commissioned Goal 2"
        )
    source = (_metadata_value(text, "Authority source") or "").strip()
    if len(source) < 10:
        errors.append(
            f"{GOAL_2_AUTHORIZATION_PATH}: Authority source must identify the external authorization"
        )
    if "This record documents external authorization; it does not grant it." not in text:
        errors.append(
            f"{GOAL_2_AUTHORIZATION_PATH}: missing non-self-authorizing boundary statement"
        )
    return not errors, errors


def _checked_task_authorization_errors(
    feature: Path,
    tasks_text: str,
    goal_2_authorized: bool,
) -> list[str]:
    """Keep Goal 2 dormant until a valid external authorization record exists."""

    if goal_2_authorized:
        return []
    errors: list[str] = []
    for line_number, line in enumerate(tasks_text.splitlines(), 1):
        if line.startswith("- [x] T") or line.startswith("- [X] T"):
            errors.append(
                f"{feature}/tasks.md:{line_number}: Goal 2 task is checked without "
                f"valid {GOAL_2_AUTHORIZATION_PATH}"
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
        errors.append(f"{dirname}/plan.md: documentation matrix must contain one README.md row")
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
            errors.append(
                f"{dirname}/plan.md: NO_IMPACT row lacks concrete rationale"
            )

    tasks_lower = tasks_text.lower()
    for token in (
        "documentation freshness",
        "documentation impact and freshness",
        "readme.md",
        "documentation dispositions",
        "reviewer",
    ):
        if token not in tasks_lower:
            errors.append(f"{dirname}/tasks.md: missing documentation gate task term {token!r}")
    if "documentation freshness" not in checklist_text.lower():
        errors.append(f"{dirname}/checklists/requirements.md: missing documentation freshness review")
    if "**`README.md` disposition**" not in spec_section:
        errors.append(f"{dirname}/spec.md: missing explicit README.md disposition")
    if "handoff evidence" not in spec_section.lower():
        errors.append(f"{dirname}/spec.md: missing ordinary handoff evidence for documentation")
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


def check_program(root: Path) -> list[str]:
    """Validate the V2 umbrella/slice graph and planning completeness."""

    errors: list[str] = []
    goal_2_authorized, authorization_errors = _goal_2_authorization_state(root)
    errors.extend(authorization_errors)
    specs = root / "specs"
    expected_directories = {"001-nunchi-v2-program", *EXPECTED_SLICES}
    actual_directories = {path.name for path in specs.iterdir() if path.is_dir()} if specs.is_dir() else set()
    if actual_directories != expected_directories:
        missing = sorted(expected_directories - actual_directories)
        extra = sorted(actual_directories - expected_directories)
        if missing:
            errors.append(f"specs/: missing planned directories {missing}")
        if extra:
            errors.append(f"specs/: unexpected planned directories {extra}")

    graph: dict[str, tuple[str, ...]] = {}
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
            missing = sorted(str(path.relative_to(root)) for path in required_files - actual_files)
            extra = sorted(str(path.relative_to(root)) for path in actual_files - required_files)
            if missing:
                errors.append(f"{feature.relative_to(root)}: missing required planning files {missing}")
            if extra:
                errors.append(f"{feature.relative_to(root)}: unexpected files {extra}")
            if not required_files.issubset(actual_files):
                continue

        spec_text = (feature / "spec.md").read_text(encoding="utf-8")
        plan_text = (feature / "plan.md").read_text(encoding="utf-8")
        tasks_text = (feature / "tasks.md").read_text(encoding="utf-8")
        checklist_text = (feature / "checklists" / "requirements.md").read_text(encoding="utf-8")
        combined = "\n".join((spec_text, plan_text, tasks_text))

        if PINNED_VAULT_COMMIT not in spec_text:
            errors.append(
                f"{feature.relative_to(root)}/spec.md: authority source must cite "
                f"Aleph Vault merge {PINNED_VAULT_COMMIT}"
            )

        for section in REQUIRED_SPEC_SECTIONS:
            if section not in spec_text:
                errors.append(f"{feature.relative_to(root)}/spec.md: missing section {section!r}")
        for section in REQUIRED_PLAN_SECTIONS:
            if section not in plan_text:
                errors.append(f"{feature.relative_to(root)}/plan.md: missing section {section!r}")
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
            _checked_task_authorization_errors(
                feature.relative_to(root),
                tasks_text,
                goal_2_authorized,
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
            errors.append(f"{feature.relative_to(root)}/plan.md: no shared S01-S16 scene mapping")
        if dirname == "110-v2-parity-cutover":
            if scenes != required_scenes:
                errors.append(
                    f"{feature.relative_to(root)}/plan.md: final parity must map exactly S01-S16"
                )
        else:
            all_nonfinal_scenes.update(scenes)

        for token in ("tests/v2/", "evals/v2/", "evidence/v2/"):
            if token not in plan_text:
                errors.append(f"{feature.relative_to(root)}/plan.md: missing ordinary target {token!r}")
        if "Goal 2" not in combined or "Goal 1" not in combined:
            errors.append(f"{feature.relative_to(root)}: missing explicit two-goal boundary")

    unknown_interfaces = all_interface_ids - set(CANONICAL_INTERFACES)
    if unknown_interfaces:
        errors.append(f"specs/: non-canonical interface IDs present {sorted(unknown_interfaces)}")
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
    actual_umbrella = {path for path in umbrella.rglob("*") if path.is_file()} if umbrella.is_dir() else set()
    if actual_umbrella != required_umbrella:
        errors.append("specs/001-nunchi-v2-program: umbrella artifact set is incomplete or unexpected")
    else:
        umbrella_text = "\n".join(path.read_text(encoding="utf-8") for path in required_umbrella)
        for interface in CANONICAL_INTERFACES:
            if interface not in umbrella_text:
                errors.append(f"specs/001-nunchi-v2-program: missing {interface} from registry")
        for scene in required_scenes:
            if scene not in umbrella_text:
                errors.append(f"specs/001-nunchi-v2-program: missing scene {scene}")

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
                "tests/test_governance.py",
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
    try:
        completed = subprocess.run(
            ["specify", "--version"],
            check=False,
            capture_output=True,
            text=True,
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
    errors.extend(check_workflow_surface(root))
    errors.extend(check_program(root))
    errors.extend(check_runtime_dependencies(root))
    if include_cli:
        errors.extend(check_cli(root))
    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-cli",
        action="store_true",
        help="also require the installed specify CLI to match the repository pin",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
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
