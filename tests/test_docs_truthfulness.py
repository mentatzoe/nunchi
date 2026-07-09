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
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADAPTERS_MD = _REPO_ROOT / "docs" / "adapters.md"
_README_MD = _REPO_ROOT / "README.md"
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
        self.assertIn("single live-smoke evidenced", combined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
