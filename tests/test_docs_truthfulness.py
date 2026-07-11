"""Docs-truthfulness enforcement tests.

Documentation is product (CLAUDE.md, "Definition of done"): defaults stated in
module docstrings and in ``docs/adapters.md`` must equal the constants the code
actually uses, and functional config keys must be documented. These tests pin
the history-default class of drift (docs said 10 after the code default moved
to 20) so it cannot silently recur.

Fully offline; reads only files inside the repo.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import tomllib
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADAPTERS_MD = _REPO_ROOT / "docs" / "adapters.md"
_README_MD = _REPO_ROOT / "README.md"
_AGENTS_MD = _REPO_ROOT / "AGENTS.md"
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_EXECUTION_SPINE_MD = _REPO_ROOT / "docs" / "governance" / "execution-spine.md"
_SPECS_README = _REPO_ROOT / "specs" / "README.md"
_EVIDENCE_README = _REPO_ROOT / "evidence" / "README.md"
_LIFECYCLE_AMENDMENT = (
    _REPO_ROOT
    / "evidence"
    / "governance"
    / "slice-lifecycle-amendment-2026-07-11.md"
)
_INSTALL_MD = _REPO_ROOT / "docs" / "INSTALL.md"
_MCP_DISCORD_README = _REPO_ROOT / "integrations" / "mcp-discord" / "README.md"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_HERMES_PLUGIN = _REPO_ROOT / "integrations" / "hermes" / "nunchi-gate" / "__init__.py"

# (module name, env var, adapters.md env-table row key)
_ADAPTER_CASES = (
    ("nunchi.adapters.matrix", "NUNCHI_MATRIX_HISTORY"),
    ("nunchi.adapters.telegram", "NUNCHI_TELEGRAM_HISTORY"),
    ("nunchi.adapters.discord", "NUNCHI_DISCORD_HISTORY"),
)


def _load_hermes_plugin() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("nunchi_gate_docs_check", _HERMES_PLUGIN)
    assert spec is not None and spec.loader is not None, f"missing plugin at {_HERMES_PLUGIN}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _documented_default_near(text: str, env_var: str) -> int | None:
    """Return the ``(default: N)`` value documented near *env_var*, if any."""
    idx = text.find(env_var)
    if idx == -1:
        return None
    window = text[idx : idx + 200]
    match = re.search(r"\(default:\s*(\d+)\)", window)
    return int(match.group(1)) if match else None


class AdapterHistoryDefaultDocstringTest(unittest.TestCase):
    """Module docstrings must state the same default as _DEFAULT_HISTORY_LEN."""

    def test_docstring_default_matches_code_default(self) -> None:
        for module_name, env_var in _ADAPTER_CASES:
            with self.subTest(module=module_name):
                mod = importlib.import_module(module_name)
                expected = mod._DEFAULT_HISTORY_LEN
                documented = _documented_default_near(mod.__doc__ or "", env_var)
                self.assertIsNotNone(
                    documented,
                    f"{module_name} docstring does not document a default for {env_var}",
                )
                self.assertEqual(
                    documented,
                    expected,
                    f"{module_name} docstring documents {env_var} default {documented}, "
                    f"but the code default is {expected}",
                )


class AdapterHistoryDefaultDocsTableTest(unittest.TestCase):
    """docs/adapters.md env tables must state the code defaults."""

    def test_adapters_md_defaults_match_code_defaults(self) -> None:
        text = _ADAPTERS_MD.read_text(encoding="utf-8")
        for module_name, env_var in _ADAPTER_CASES:
            with self.subTest(env_var=env_var):
                mod = importlib.import_module(module_name)
                expected = mod._DEFAULT_HISTORY_LEN
                row = re.search(
                    r"\|\s*`" + env_var + r"`\s*\|\s*no\s*\|\s*`(\d+)`\s*\|", text
                )
                self.assertIsNotNone(
                    row, f"docs/adapters.md has no env-table row for {env_var}"
                )
                self.assertEqual(
                    int(row.group(1)),
                    expected,
                    f"docs/adapters.md documents {env_var} default {row.group(1)}, "
                    f"but the code default is {expected}",
                )


class HermesHistoryWindowDocumentedTest(unittest.TestCase):
    """The functional history_window config key must be documented."""

    def test_docstring_documents_history_window_with_code_default(self) -> None:
        mod = _load_hermes_plugin()
        doc = mod.__doc__ or ""
        match = re.search(r"history_window\s*\(int,\s*default\s*(\d+)\)", doc)
        self.assertIsNotNone(
            match,
            "hermes nunchi-gate docstring does not document the history_window "
            "config key (it is read at runtime from the global config block)",
        )
        self.assertEqual(
            int(match.group(1)),
            mod._DEFAULT_HISTORY_WINDOW,
            "documented history_window default does not match _DEFAULT_HISTORY_WINDOW",
        )


class AdapterStatusClaimDisciplineTest(unittest.TestCase):
    """Adapter status language must stay evidence-tiered, not beta-gate-shaped."""

    def test_adapter_docs_do_not_define_beta_as_test_coverage(self) -> None:
        combined = "\n".join(
            [
                _README_MD.read_text(encoding="utf-8"),
                _ADAPTERS_MD.read_text(encoding="utf-8"),
            ]
        )
        forbidden = (
            "beta*",
            "beta\\*",
            "beta for the Matrix",
            "full offline test coverage",
            "Expect first-run rough edges",
        )
        for phrase in forbidden:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, combined)
        self.assertIn("Status labels are evidence tiers", combined)
        self.assertIn("Status labels in this table are evidence tiers", combined)
        self.assertNotIn(
            "Codex runner + hooks | Codex CLI via shared Discord-MCP transport | stdlib | offline-tested; live smoke owed",
            combined,
        )
        self.assertIn("bounded live-smokes evidenced", combined)


class ReadmeContractStateDisciplineTest(unittest.TestCase):
    """The landing page must not collapse release, checkout, and V2 truth."""

    def test_readme_separates_current_version_and_program_lifecycle(self) -> None:
        text = _README_MD.read_text(encoding="utf-8")
        normalized_text = " ".join(text.split())
        project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
        source_version = project["project"]["version"]
        bound_runner = (
            "python3 scripts/run_slice_workflow.py run <workflow> "
            + "specs"
            + "/<exact-slice>"
        )
        persisted_feature_state = ".specify" + "/feature.json"

        required = (
            f"checkout still reports package version `{source_version}`",
            "including the subsequently removed deterministic fast path",
            "2026-07-11 reset baseline snapshot: program `READY`; implementation authority `NOT_GRANTED`",
            "At that snapshot all slices were `PLANNED` and dormant",
            "V1 remains current until the atomic merge is post-merge verified as `CUTOVER_VERIFIED`",
            "dated snapshot of the shared repository program, not a permanent live registry",
            "Resolve live program progress from the umbrella declaration",
            "evidence/governance/v2-implementation-authorization.md",
            "the record does not grant authority or make the slice ready",
            bound_runner,
            "allowlists and preflights the existing slice",
            f"leaves `{persisted_feature_state}` unchanged",
            "sets the exact binding inside the workflow process",
            "Each dependent owner accepts every required upstream handoff",
            "At slice level, `v2-integrator` accepts slices `010`–`100`, while Zoe accepts the exact slice-`110` candidate",
            "Only `110-v2-parity-cutover` may combine accepted handoffs",
            "Zoe's explicit `CUTOVER_ACCEPTED` decision",
            "Selected V2 design — not implemented",
            "Current implementation: V1",
            "Status labels are evidence tiers",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized_text)

        forbidden = (
            "This library gives your agent that",
            "adapter tier (Constitution VI)",
            "classifier verdict test suite is the merge contract",
            "Goal 1",
            "Goal 2",
            "v2-goal-2-authorization.md",
        )
        for phrase in forbidden:
            with self.subTest(forbidden=phrase):
                self.assertNotIn(phrase, text)

    def test_external_guidance_resolves_live_state_from_authoritative_artifacts(self) -> None:
        guidance_paths = (
            _AGENTS_MD,
            _CLAUDE_MD,
            _README_MD,
            _EXECUTION_SPINE_MD,
            _SPECS_README,
            _EVIDENCE_README,
            _LIFECYCLE_AMENDMENT,
        )
        for path in guidance_paths:
            with self.subTest(path=path.relative_to(_REPO_ROOT)):
                normalized = " ".join(path.read_text(encoding="utf-8").split())
                self.assertIn("2026-07-11", normalized)
                self.assertIn("001-nunchi-v2-program", normalized)
                self.assertIn(
                    "evidence/governance/v2-implementation-authorization.md",
                    normalized,
                )
                self.assertIn("activation", normalized)
                self.assertIn("candidate", normalized)
                self.assertIn("handoff", normalized)
                self.assertIn("acceptance", normalized)

    def test_both_slice_workflows_use_the_bound_read_only_runner(self) -> None:
        workflow_guidance_paths = (
            _AGENTS_MD,
            _CLAUDE_MD,
            _README_MD,
            _EXECUTION_SPINE_MD,
            _SPECS_README,
            _LIFECYCLE_AMENDMENT,
        )
        persisted_feature_state = ".specify" + "/feature.json"
        direct_stateful_helper = (
            ".specify" + "/scripts/bash/check-prerequisites.sh"
        )
        for path in workflow_guidance_paths:
            with self.subTest(path=path.relative_to(_REPO_ROOT)):
                normalized = " ".join(path.read_text(encoding="utf-8").split())
                self.assertIn("scripts/run_slice_workflow.py", normalized)
                self.assertIn("run nunchi-plan", normalized)
                self.assertIn("run speckit", normalized)
                self.assertIn("resume <run-id>", normalized)
                self.assertIn("010", normalized)
                self.assertIn("110", normalized)
                self.assertIn("nunchi-plan", normalized)
                self.assertIn("speckit", normalized)
                self.assertIn(persisted_feature_state, normalized)
                self.assertNotIn(direct_stateful_helper, normalized)

    def test_workflow_evidence_pins_existing_slice_cycles(self) -> None:
        normalized = " ".join(
            _LIFECYCLE_AMENDMENT.read_text(encoding="utf-8").split()
        )
        required = (
            "Nunchi Existing-Slice Planning Cycle",
            "version `1.4.0` with nine steps",
            "beginning at `bind-existing-slice`",
            "no `speckit.specify` or implementation step",
            "version `2.5.0` with eighteen steps",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)

    def test_slice_acceptance_is_distinct_from_dependency_acceptance(self) -> None:
        acceptance_paths = (
            _AGENTS_MD,
            _CLAUDE_MD,
            _README_MD,
            _EXECUTION_SPINE_MD,
            _SPECS_README,
            _LIFECYCLE_AMENDMENT,
        )
        for path in acceptance_paths:
            with self.subTest(path=path.relative_to(_REPO_ROOT)):
                normalized = " ".join(path.read_text(encoding="utf-8").split())
                self.assertIn("v2-integrator", normalized)
                self.assertIn("Zoe", normalized)
                self.assertIn("010", normalized)
                self.assertIn("100", normalized)
                self.assertIn("110", normalized)
                self.assertIn("dependent", normalized)
                self.assertIn("upstream handoff", normalized)

    def test_source_only_install_guides_do_not_claim_pypi_surfaces(self) -> None:
        install_text = _INSTALL_MD.read_text(encoding="utf-8")
        mcp_text = _MCP_DISCORD_README.read_text(encoding="utf-8")

        self.assertIn("is not present in that release", install_text)
        self.assertIn("does not contain the", mcp_text)
        self.assertNotIn("pip install nunchi[mcp-discord]", mcp_text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
