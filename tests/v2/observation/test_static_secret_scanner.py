"""Tests for the reproducible Slice 020 static secret scanner."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


def _synthetic_openai_key() -> str:
    """Build a matcher-shaped token without storing one in repository text."""
    return "".join(("sk", "-", "proj", "-", "A" * 24))


def _synthetic_github_token() -> str:
    """Build another matcher-shaped token without a literal scanner finding."""
    return "".join(("gh", "p", "_", "B" * 24))


class TestSlice020SecretScanner(unittest.TestCase):
    def test_added_secret_is_reported_without_echoing_secret_bytes(self):
        from scripts.check_slice020_secrets import scan_added_lines

        secret = _synthetic_openai_key()
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

    def test_fixture_marker_text_does_not_suppress_a_finding(self):
        from scripts.check_slice020_secrets import scan_added_lines

        secret = _synthetic_openai_key()
        diff = (
            "diff --git a/src/nunchi/observation.py b/src/nunchi/observation.py\n"
            "--- a/src/nunchi/observation.py\n"
            "+++ b/src/nunchi/observation.py\n"
            "@@ -1,0 +2 @@\n"
            f'+API_KEY = "{secret}"  # slice020-secret-fixture\n'
        )
        findings = scan_added_lines(diff)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matcher, "openai-style-key")

    def test_removed_secret_and_regex_matcher_source_are_not_findings(self):
        from scripts.check_slice020_secrets import scan_added_lines

        removed = _synthetic_github_token()
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

    def test_exact_range_scans_lifecycle_critical_checker_and_all_changed_paths(self):
        from scripts.check_slice020_secrets import main

        secret = _synthetic_openai_key()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
            checker = repo / "scripts/check_slice020_task_state.py"
            checker.parent.mkdir(parents=True)
            checker.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            checker.write_text(f'SECRET = "{secret}"\n', encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "head"], cwd=repo, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            output = io.StringIO()
            previous = Path.cwd()
            try:
                os.chdir(repo)
                with contextlib.redirect_stdout(output):
                    result = main(["--base", base, "--head", head])
            finally:
                os.chdir(previous)

        self.assertEqual(result, 1)
        receipt = output.getvalue()
        self.assertIn("SLICE020_SECRET_SCAN FINDINGS", receipt)
        self.assertIn("files=1", receipt)
        self.assertIn("scripts/check_slice020_task_state.py", receipt)
        self.assertNotIn(secret, receipt)


if __name__ == "__main__":
    unittest.main()
