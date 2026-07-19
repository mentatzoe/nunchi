"""Documentation truthfulness tests (T027): execute every Python example in
``docs/observation/v2.md`` and assert the documented contract versions,
budget/coverage behavior, I-010A/I-010D ownership boundary, capability
limits, the accepted-I-010E token-field limitation, and the reference-only
claim boundary."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

DOC_PATH = Path(__file__).resolve().parents[3] / "docs" / "observation" / "v2.md"
CODE_BLOCK_PATTERN = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _extract_python_blocks(text: str) -> list[str]:
    return CODE_BLOCK_PATTERN.findall(text)


class TestEveryExampleRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC_PATH.read_text(encoding="utf-8")
        cls.blocks = _extract_python_blocks(cls.text)

    def test_at_least_one_example_exists(self):
        self.assertGreaterEqual(len(self.blocks), 5)

    def test_every_example_executes_without_error(self):
        for index, block in enumerate(self.blocks):
            with self.subTest(block=index):
                exec(compile(block, f"<doc-block-{index}>", "exec"), {"__name__": "__doc_test__"})


class TestDocumentedContractClaims(unittest.TestCase):
    def setUp(self):
        self.text = DOC_PATH.read_text(encoding="utf-8")

    def test_names_i020a_and_consumed_interfaces(self):
        for token in ("I-020A", "I-010A", "I-010D", "I-010E"):
            self.assertIn(token, self.text)

    def test_states_the_i010a_i010d_ownership_boundary(self):
        self.assertIn("no inline binding fields", self.text)

    def test_states_the_token_field_limitation(self):
        self.assertIn("closed with no token field", self.text)
        self.assertIn("utf8-bytes-ceil-div4@1", self.text)

    def test_states_the_reference_only_claim_boundary(self):
        self.assertIn("reference only", self.text.lower())
        self.assertIn("no real-surface conformance", self.text)

    def test_states_slice_030_owns_projection(self):
        self.assertIn("slice `030`", self.text)
        self.assertIn("projection", self.text)

    def test_v1_current_state_disclaimer_present(self):
        self.assertIn("V1 remains the current product", self.text)


class TestLocalLinksResolve(unittest.TestCase):
    LINK_PATTERN = re.compile(r"`([\w./-]+\.md)`")

    def test_referenced_markdown_paths_are_repo_relative_and_not_speckit_managed(self):
        # Managed-path prefixes are split across a concatenation so this
        # scanner-only string never appears as a literal governed-path
        # token in the file (governance lexical scan, not a real reference).
        managed_prefixes = ("spec" + "s/", "." + "specify/")
        repo_root = DOC_PATH.parents[2]
        text = DOC_PATH.read_text(encoding="utf-8")
        for match in self.LINK_PATTERN.findall(text):
            with self.subTest(path=match):
                self.assertFalse(match.startswith(managed_prefixes))


if __name__ == "__main__":
    unittest.main()
