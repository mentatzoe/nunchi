"""Enforcement: the test suite must never write outside temp directories.

Background (real observed bug): the operator's live receipt log
(``$HOME/.claude/nunchi-gate-receipts.jsonl``) accumulated 700+ test
artifacts (``chat_id`` values like ``c1``) because tests ran the Claude Code
hook scripts as subprocesses with the parent environment inherited, letting
``NUNCHI_HOOK_LOG`` fall through to its home-anchored default.

This module enforces the fix at three levels:

1. Static scan (ENTIRE ``tests/`` tree, not selected files):
   a. No test may resolve home-anchored paths (``Path.home()`` /
      ``expanduser()``).
   b. Any test module that references receipt-writing hook scripts
      (Claude or Codex) must not build a subprocess environment from the bare
      parent environment; it must go through ``tests.hook_sandbox.sandbox_env``
      which pins ``HOME`` and hook logs into a temp dir.
2. Detector self-tests proving the scanners actually catch the forbidden
   patterns (an enforcement test that cannot fail is worse than none).
3. Runtime canary: running a hook subprocess through the sandbox with
   ``NUNCHI_HOOK_LOG`` unset writes its receipt inside the sandbox HOME —
   the home-default fall-through is contained, never the operator's file.

Tests here must NOT modify or read the operator's actual log file.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tests.hook_sandbox import sandbox_env

_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent

# Files allowed to mention home-path APIs / bare-env patterns:
#  - this enforcement module (contains the patterns as string literals),
#  - the sandbox helper (the single designated place that reads os.environ
#    and pins HOME/NUNCHI_HOOK_LOG before any hook subprocess runs).
_ALLOWED_FILES = {"test_no_home_writes.py", "hook_sandbox.py"}

# Rule 1: no home-anchored path resolution anywhere in the test suite.
_HOME_PATTERNS = (
    "Path.home(",
    "expanduser(",
)

# Rule 2: hook-running test modules must not inherit the bare parent env.
_GATE = _REPO_ROOT / "integrations" / "claude-code" / "nunchi_prompt_gate.py"
_HOOK_SCRIPT_MARKERS = ("nunchi_prompt_gate", "nunchi_send_gate")
_BARE_ENV_PATTERNS = (
    "**os.environ",
    "os.environ.copy",
    "dict(os.environ)",
    "os.environ.items(",
)


def _iter_test_sources() -> list[pathlib.Path]:
    """Every .py file under tests/, recursively — the whole tree."""
    return sorted(p for p in _TESTS_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _scan_for_home_paths(name: str, text: str) -> list[str]:
    """Return violation strings for Rule 1 (home-path resolution)."""
    if name in _ALLOWED_FILES:
        return []
    violations = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in _HOME_PATTERNS:
            if pattern in line:
                violations.append(f"{name}:{lineno}: forbidden home-path call {pattern!r}")
    return violations


def _scan_for_bare_env(name: str, text: str) -> list[str]:
    """Return violation strings for Rule 2 (bare env in hook-running modules)."""
    if name in _ALLOWED_FILES:
        return []
    if not any(marker in text for marker in _HOOK_SCRIPT_MARKERS):
        return []
    violations = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in _BARE_ENV_PATTERNS:
            if pattern in line:
                violations.append(
                    f"{name}:{lineno}: hook-running test builds subprocess env from "
                    f"bare os.environ ({pattern!r}); use tests.hook_sandbox.sandbox_env"
                )
    return violations


class TestSuiteCannotResolveHomePaths(unittest.TestCase):
    """Rule 1 over the entire tests/ tree."""

    def test_no_home_path_resolution_in_any_test_file(self):
        violations: list[str] = []
        scanned = 0
        for path in _iter_test_sources():
            scanned += 1
            violations.extend(
                _scan_for_home_paths(path.name, path.read_text(encoding="utf-8"))
            )
        self.assertGreaterEqual(scanned, 10, "scan looks broken: too few test files found")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_detector_catches_home_path_pattern(self):
        """Self-test: the scanner must flag a known-bad sample."""
        bad = "log = Path.home() / '.claude' / 'receipts.jsonl'\n"
        self.assertTrue(_scan_for_home_paths("sample.py", bad))
        bad2 = "p = os.path.expanduser('~/.hermes/logs/x.jsonl')\n"
        self.assertTrue(_scan_for_home_paths("sample.py", bad2))

    def test_detector_ignores_allowed_files(self):
        bad = "log = Path.home() / 'x'\n"
        self.assertEqual(_scan_for_home_paths("hook_sandbox.py", bad), [])


class TestHookRunnersUseSandbox(unittest.TestCase):
    """Rule 2 over the entire tests/ tree."""

    def test_no_bare_env_in_hook_running_test_files(self):
        violations: list[str] = []
        hook_referencing = 0
        for path in _iter_test_sources():
            text = path.read_text(encoding="utf-8")
            if path.name not in _ALLOWED_FILES and any(
                m in text for m in _HOOK_SCRIPT_MARKERS
            ):
                hook_referencing += 1
            violations.extend(_scan_for_bare_env(path.name, text))
        # Guard against silent no-op: the remaining inherited hook test
        # modules must be seen while the V2 packet is still pending.
        self.assertGreaterEqual(
            hook_referencing, 2,
            "scan looks broken: expected the inherited hook test modules",
        )
        self.assertEqual(violations, [], "\n".join(violations))

    def test_detector_catches_bare_env_pattern(self):
        bad = (
            "HOOK = 'nunchi_prompt_gate.py'\n"
            "env = {**os.environ, 'X': '1'}\n"
        )
        self.assertTrue(_scan_for_bare_env("sample.py", bad))

    def test_detector_ignores_non_hook_files(self):
        """Bare env in a module that never touches the hook scripts is fine
        (e.g. CLI subprocess tests: the nunchi CLI writes only to stdout)."""
        bad = "env = os.environ.copy()\n"
        self.assertEqual(_scan_for_bare_env("sample.py", bad), [])


class TestSandboxEnvContract(unittest.TestCase):
    """The sandbox helper must pin HOME and NUNCHI_HOOK_LOG into a temp dir."""

    def test_home_is_pinned_into_temp(self):
        env = sandbox_env()
        self.assertIn("HOME", env)
        self.assertNotEqual(env["HOME"], os.environ.get("HOME"))
        self.assertTrue(
            env["HOME"].startswith(tempfile.gettempdir()),
            f"sandbox HOME {env['HOME']!r} is not under the temp dir",
        )

    def test_hook_log_is_pinned_under_sandbox_home(self):
        env = sandbox_env()
        self.assertIn("NUNCHI_HOOK_LOG", env)
        self.assertTrue(env["NUNCHI_HOOK_LOG"].startswith(env["HOME"]))

    def test_explicit_overrides_win(self):
        env = sandbox_env({"NUNCHI_HOOK_LOG": "/dev/null", "EXTRA": "1"})
        self.assertEqual(env["NUNCHI_HOOK_LOG"], "/dev/null")
        self.assertEqual(env["EXTRA"], "1")

    def test_parent_env_is_otherwise_preserved(self):
        env = sandbox_env()
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))


class TestRuntimeCanary(unittest.TestCase):
    """A hook subprocess with NUNCHI_HOOK_LOG unset must write its receipt
    under the sandbox HOME — proving the home-default fall-through exists and
    is contained by the sandbox (this is the exact scenario that polluted the
    operator's live log)."""

    def test_receipt_fallthrough_lands_in_sandbox_home(self):
        # Channel-tagged prompt + missing gate binary → "allow-gate-error"
        # receipt (a write path that needs no gate binary).
        fd, transcript = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        env = sandbox_env({"NUNCHI_CHANNEL_BIN": "/nonexistent"})
        # Simulate the historical mistake: no explicit NUNCHI_HOOK_LOG.
        env.pop("NUNCHI_HOOK_LOG", None)
        hook_input = {
            "session_id": "sess-canary",
            "transcript_path": transcript,
            "hook_event_name": "UserPromptSubmit",
            "prompt": (
                '<channel source="discord" chat_id="enforcement-canary" '
                'message_id="m1" user="alice" ts="2026-01-01T00:00:00Z">\n'
                "hi\n</channel>"
            ),
            "cwd": "/tmp",
        }
        try:
            result = subprocess.run(
                [sys.executable, str(_GATE)],
                input=json.dumps(hook_input),
                capture_output=True,
                text=True,
                env=env,
            )
        finally:
            os.unlink(transcript)
        self.assertEqual(result.returncode, 0, result.stderr)

        sandbox_home = pathlib.Path(env["HOME"])
        receipt_file = sandbox_home / ".claude" / "nunchi-gate-receipts.jsonl"
        self.assertTrue(
            receipt_file.exists(),
            "expected the home-default receipt inside the sandbox HOME; "
            "if the hook's default path changed, update this canary",
        )
        records = [
            json.loads(line)
            for line in receipt_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["chat_id"], "enforcement-canary")


if __name__ == "__main__":
    unittest.main()
