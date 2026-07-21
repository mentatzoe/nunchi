"""Fault-injection tests for ``nunchi-claude-v2-hook.sh``.

The Python gate (``nunchi_claude_v2.py``) is fail-closed for a configured
``user-prompt-submit`` event: any configuration, policy, or state failure it
can observe records a degraded marker and blocks. But the shell wrapper sits
*outside* that boundary — it is what actually runs `python3`. Before this
module's fix, the wrapper converted a gate crash, a missing gate file, a
missing `python3`, or any nonzero exit into a bare `exit 0` with **no output
at all**, which Claude Code treats as "allow" — silently admitting the room
prompt Attempt 3's fail-closed handler exists specifically to keep out.

These tests invoke the real wrapper as a subprocess (never the Python gate
directly — that would miss the exact defect) with a *configured* policy
(`NUNCHI_CLAUDE_V2_POLICY` set) and a deliberately broken/missing gate, and
assert the wrapper's stdout is never interpretable as admission: for
`user-prompt-submit` that means either nothing is printed, or a `{"decision":
"block", ...}` object is printed — never `{"decision": "allow", ...}`, never a
`hookSpecificOutput.additionalContext` wake packet, and never empty output
with exit 0 read as silent allow (the wrapper must print the block JSON in
that case, which is verified directly).

Every subprocess environment is built through ``tests.hook_sandbox.sandbox_env``
so ``HOME`` is sandboxed — this module references the hook wrapper by name and
is therefore covered by ``tests/test_no_home_writes.py``'s home-write guard.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.hook_sandbox import sandbox_env

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WRAPPER = (
    _REPO_ROOT / "integrations" / "claude-code" / "nunchi-claude-v2-hook.sh"
)


def _prompt_payload(body: str = "hi") -> dict:
    return {
        "session_id": "sess-fault",
        "transcript_path": "",
        "hook_event_name": "UserPromptSubmit",
        "prompt": (
            '<channel source="discord" chat_id="1" message_id="1" user="u" '
            f'ts="2026-07-21T00:00:00Z">{body}</channel>'
        ),
        "cwd": "/tmp",
    }


def _run_wrapper(hook_event: str, payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", str(_WRAPPER), hook_event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def _cannot_be_interpreted_as_admission(stdout: str) -> bool:
    """True if *stdout* cannot be read as an allow/wake by Claude Code."""
    stripped = stdout.strip()
    if not stripped:
        return True  # empty stdout with a block decision printed nowhere
    try:
        parsed = json.loads(stripped)
    except ValueError:
        return False  # unparseable output is not a safe "definitely blocked"
    if not isinstance(parsed, dict):
        return False
    if parsed.get("decision") == "block":
        return True
    return False


class _FaultInjectionCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="nunchi-wrapper-fault-"))
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _configured_env(self, *, gate_path: Path | None) -> dict:
        env = sandbox_env()
        home = Path(env["HOME"])
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "nunchi-claude-v2.env").write_text(
            "NUNCHI_CLAUDE_V2_POLICY=/tmp/does-not-matter-for-this-test.json\n",
            encoding="utf-8",
        )
        if gate_path is not None:
            env["NUNCHI_CLAUDE_V2_GATE"] = str(gate_path)
        return env


class ConfiguredGateFailureCases(_FaultInjectionCase):
    """A configured user-prompt-submit gate that cannot run must block."""

    def test_syntax_error_in_gate_blocks_not_admits(self) -> None:
        broken = self.tmp / "broken_gate.py"
        broken.write_text("this is not python (\n", encoding="utf-8")
        env = self._configured_env(gate_path=broken)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(
            _cannot_be_interpreted_as_admission(result.stdout),
            f"gate crash was admissible: {result.stdout!r}",
        )
        # The failure must be explicit: either a block JSON, or nothing —
        # never silence dressed as success. This wrapper prints block JSON.
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")
        self.assertIn("gate unavailable", parsed["reason"])
        self.assertIn("gate unavailable", result.stderr)

    def test_missing_gate_file_blocks_not_admits(self) -> None:
        missing = self.tmp / "does-not-exist.py"
        env = self._configured_env(gate_path=missing)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(_cannot_be_interpreted_as_admission(result.stdout))
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")

    def test_gate_exits_nonzero_without_crash_blocks(self) -> None:
        # A gate that runs, produces plausible-looking output, but exits
        # nonzero must not have that output treated as its real decision.
        odd_exit = self.tmp / "odd_exit_gate.py"
        odd_exit.write_text(
            "import sys\n"
            "sys.stdout.write('{\"decision\": \"allow-looking-but-not-trustworthy\"}')\n"
            "sys.exit(1)\n",
            encoding="utf-8",
        )
        env = self._configured_env(gate_path=odd_exit)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        # The wrapper must not forward the untrustworthy stdout: it emits the
        # block decision, not the gate's own (nonzero-exit) output.
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")
        self.assertNotIn("allow-looking-but-not-trustworthy", result.stdout)

    def test_gate_killed_by_signal_blocks(self) -> None:
        killed = self.tmp / "killed_gate.py"
        killed.write_text(
            "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n",
            encoding="utf-8",
        )
        env = self._configured_env(gate_path=killed)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(_cannot_be_interpreted_as_admission(result.stdout))
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")

    def test_missing_python3_blocks(self) -> None:
        # Simulate "no python3 on PATH" for a configured wrapper by giving it
        # a PATH with no python3 anywhere on it.
        env = self._configured_env(gate_path=self.tmp / "unused_gate.py")
        (self.tmp / "unused_gate.py").write_text("", encoding="utf-8")
        empty_path_dir = self.tmp / "empty-path"
        empty_path_dir.mkdir()
        env["PATH"] = str(empty_path_dir)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")
        self.assertIn("python3 missing", result.stderr)

    def test_healthy_gate_output_passes_through_unmodified(self) -> None:
        # Control: a gate that runs cleanly and prints a decision has that
        # exact decision forwarded, byte for byte.
        healthy = self.tmp / "healthy_gate.py"
        healthy.write_text(
            "import sys\n"
            "sys.stdin.read()\n"
            "sys.stdout.write('{\"hookSpecificOutput\": {\"hookEventName\": "
            "\"UserPromptSubmit\", \"additionalContext\": \"ok\"}}')\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        env = self._configured_env(gate_path=healthy)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            '{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", '
            '"additionalContext": "ok"}}',
        )

    def test_unconfigured_broken_gate_still_fails_open(self) -> None:
        # Without NUNCHI_CLAUDE_V2_POLICY the integration is inert: a broken
        # gate must not block operator prompts that never reach the room path.
        env = sandbox_env()  # no nunchi-claude-v2.env written: unconfigured
        broken = self.tmp / "broken_gate.py"
        broken.write_text("this is not python (\n", encoding="utf-8")
        env["NUNCHI_CLAUDE_V2_GATE"] = str(broken)
        result = _run_wrapper("user-prompt-submit", {"session_id": "s", "prompt": "hi"}, env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


class PreToolAndStopDirectionCases(_FaultInjectionCase):
    """Verify the other three events keep their deliberate fail direction."""

    def test_pre_tool_configured_broken_gate_fails_closed_exit_2(self) -> None:
        broken = self.tmp / "broken_gate.py"
        broken.write_text("this is not python (\n", encoding="utf-8")
        env = self._configured_env(gate_path=broken)
        result = _run_wrapper(
            "pre-tool", {"session_id": "s", "tool_name": "Bash", "tool_input": {}}, env
        )
        self.assertEqual(result.returncode, 2)

    def test_stop_configured_broken_gate_still_fails_open(self) -> None:
        broken = self.tmp / "broken_gate.py"
        broken.write_text("this is not python (\n", encoding="utf-8")
        env = self._configured_env(gate_path=broken)
        result = _run_wrapper("stop", {"session_id": "s"}, env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_post_tool_configured_broken_gate_still_fails_open(self) -> None:
        broken = self.tmp / "broken_gate.py"
        broken.write_text("this is not python (\n", encoding="utf-8")
        env = self._configured_env(gate_path=broken)
        result = _run_wrapper(
            "post-tool",
            {"session_id": "s", "tool_name": "x", "tool_input": {}, "tool_response": {}},
            env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


class WrapperHealthyRoundTripCase(_FaultInjectionCase):
    """The wrapper still round-trips to the real gate correctly."""

    def test_healthy_configured_channel_event_reaches_real_gate(self) -> None:
        # No gate override: use the real nunchi_claude_v2.py from the repo,
        # unconfigured beyond the policy pointer (which does not resolve), so
        # the real gate's own config-error path runs — proving the wrapper
        # forwards a real gate's decision end-to-end, not just a stub's.
        env = self._configured_env(gate_path=None)
        home = Path(env["HOME"])
        (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        real_gate = (
            _REPO_ROOT / "integrations" / "claude-code" / "nunchi_claude_v2.py"
        )
        target = home / ".claude" / "hooks" / "nunchi_claude_v2.py"
        target.write_text(real_gate.read_text(encoding="utf-8"), encoding="utf-8")
        env["PYTHONPATH"] = str(_REPO_ROOT / "src")
        env["NUNCHI_CLAUDE_V2_STATE_DIR"] = str(home / "state")
        env["NUNCHI_CLAUDE_V2_CHANNEL_ID"] = "1"
        env["NUNCHI_CLAUDE_V2_SELF_USER_ID"] = "2"
        env["NUNCHI_CLAUDE_V2_PARTICIPANT_ID"] = "p"
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        # The real gate's own config-error path (policy file does not exist)
        # runs and produces its own degraded-marker block — this proves the
        # wrapper is not just special-casing a stub gate.
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")


if __name__ == "__main__":
    unittest.main()
