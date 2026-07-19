"""Tests for the reproducible Slice 020 static secret scanner."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class TestSlice020SecretScanner(unittest.TestCase):
    def test_added_secret_is_reported_without_echoing_secret_bytes(self):
        from scripts.check_slice020_secrets import scan_added_lines

        secret = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"
        diff = (
            "diff --git a/src/nunchi/observation.py b/src/nunchi/observation.py\n"
            "--- a/src/nunchi/observation.py\n"
            "+++ b/src/nunchi/observation.py\n"
            "@@ -1,0 +2 @@\n"
            f'+API_KEY = "{secret}"\n'
        )
        findings = scan_added_lines(diff)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "src/nunchi/observation.py")
        self.assertNotIn(secret, findings[0].render())

    def test_removed_secret_and_regex_matcher_source_are_not_findings(self):
        from scripts.check_slice020_secrets import scan_added_lines

        removed = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        diff = (
            "diff --git a/src/nunchi/observation.py b/src/nunchi/observation.py\n"
            "--- a/src/nunchi/observation.py\n"
            "+++ b/src/nunchi/observation.py\n"
            "@@ -1 +1 @@\n"
            f'-TOKEN = "{removed}"\n'
            "+GITHUB_TOKEN_PATTERN = r\"gh[pousr]_[A-Za-z0-9]{20,}\"\n"
        )
        self.assertEqual(scan_added_lines(diff), [])

    def test_explicit_base_head_range_emits_reproducible_clean_receipt(self):
        from scripts.check_slice020_secrets import main

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            source = repo / "src/nunchi/observation.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                text=True, capture_output=True,
            ).stdout.strip()
            source.write_text("VALUE = 2\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "head"], cwd=repo, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                text=True, capture_output=True,
            ).stdout.strip()
            output = io.StringIO()
            previous = Path.cwd()
            try:
                os.chdir(repo)
                with contextlib.redirect_stdout(output):
                    result = main(["--base", base, "--head", head])
            finally:
                os.chdir(previous)

        self.assertEqual(result, 0)
        receipt = output.getvalue()
        self.assertIn("SLICE020_SECRET_SCAN CLEAN", receipt)
        self.assertIn(f"base={base}", receipt)
        self.assertIn(f"head={head}", receipt)
        self.assertIn("matchers=4", receipt)


if __name__ == "__main__":
    unittest.main()
