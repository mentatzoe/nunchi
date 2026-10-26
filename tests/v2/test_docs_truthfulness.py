"""Repository documentation structure and retired workflow checks."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DocumentationStructureTests(unittest.TestCase):
    def test_changelog_has_one_unreleased_section(self) -> None:
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("## [Unreleased]"), 1)
        self.assertEqual(text.count("\n## Unreleased"), 0)

    def test_spec_workflow_remains_retired(self) -> None:
        self.assertFalse(
            [path for path in (ROOT / ".specify").rglob("*") if path.is_file()]
        )
        self.assertFalse((ROOT / "scripts" / "run_slice_workflow.py").exists())
        self.assertFalse((ROOT / "scripts" / "check_governance.py").exists())
        self.assertFalse(list(ROOT.glob("specs/**/tasks.md")))
        self.assertFalse(list(ROOT.glob("specs/**/checklists/*.md")))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
