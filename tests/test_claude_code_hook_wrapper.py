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
`user-prompt-submit` the wrapper must print an actual `{"decision": "block",
...}` object — never `{"decision": "allow", ...}`, never a
`hookSpecificOutput.additionalContext` wake packet, and (Attempt 5) never
empty or truncated output either. Claude Code's own contract treats empty
stdout at exit 0 as an implicit allow, so an empty/truncated gate FILE that
executes cleanly (crashes without a nonzero exit) is just as dangerous as a
crash — the wrapper must treat empty/malformed configured
`user-prompt-submit` output exactly like a crash, and the Python gate must
never legitimately produce empty output on any successful configured path
(including a plain operator prompt with nothing to add).

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
    """True if *stdout* cannot be read as an allow/wake by Claude Code.

    Correction (Attempt 5): Claude Code's UserPromptSubmit hook contract
    treats empty stdout at exit 0 as an implicit allow — proceed normally,
    same as an explicit non-blocking decision. Empty output IS admissible;
    treating it as "safe" here was the exact class of bug Attempt 5 fixes
    (a gate that runs and exits 0 but is empty/truncated silently admits the
    room prompt). Only a parseable ``{"decision": "block", ...}`` object is
    unambiguously NOT an admission.
    """
    stripped = stdout.strip()
    if not stripped:
        return False  # empty stdout at exit 0 is an implicit allow
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

    def test_empty_gate_file_blocks_not_admits(self) -> None:
        # [N2-CLAUDE-A4-REWORK-01]: an empty (zero-byte) gate FILE executes
        # cleanly under python3 — no syntax error, exit 0, zero bytes of
        # stdout. Exit-status checking alone cannot catch this; it is
        # exit-status-invisible by construction.
        empty = self.tmp / "empty_gate.py"
        empty.write_text("", encoding="utf-8")
        env = self._configured_env(gate_path=empty)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(_cannot_be_interpreted_as_admission(result.stdout))
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")
        self.assertIn("empty, malformed, or unsupported", result.stderr)

    def test_truncated_gate_file_blocks_not_admits(self) -> None:
        # A gate file with only a trailing comment: parses, executes, exits
        # 0, produces nothing — the "truncated" half of the reported defect.
        truncated = self.tmp / "truncated_gate.py"
        truncated.write_text("# truncated mid-write\n", encoding="utf-8")
        env = self._configured_env(gate_path=truncated)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")

    def test_gate_exits_zero_with_malformed_output_blocks(self) -> None:
        # A gate that runs, exits 0 (not a crash the STATUS check would
        # catch), but writes non-JSON garbage instead of a real decision.
        malformed = self.tmp / "malformed_gate.py"
        malformed.write_text(
            "import sys\nsys.stdout.write('not json at all')\nsys.exit(0)\n",
            encoding="utf-8",
        )
        env = self._configured_env(gate_path=malformed)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")
        self.assertNotIn("not json at all", result.stdout)

    def test_gate_exits_zero_with_truncated_json_blocks(self) -> None:
        # Exit 0, output that looks like the start of a real decision but
        # cuts off mid-object — must not be forwarded as-is.
        truncated_json = self.tmp / "truncated_json_gate.py"
        truncated_json.write_text(
            'import sys\nsys.stdout.write(\'{"decision": "bl\')\nsys.exit(0)\n',
            encoding="utf-8",
        )
        env = self._configured_env(gate_path=truncated_json)
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        # The gate's own truncated fragment must not be forwarded verbatim —
        # the wrapper's manufactured, complete block JSON replaces it.
        self.assertNotEqual(result.stdout, '{"decision": "bl')
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")
        self.assertIn("gate unavailable", parsed.get("reason", ""))

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


class StrictOutputValidationCases(_FaultInjectionCase):
    """[N2-CLAUDE-A5-REWORK-01]: brace-wrapping alone is not proof of a real
    decision. A configured user-prompt-submit at exit 0 must independently,
    strictly validate stdout against the gate's own exact output contract —
    every one of these reproductions is brace-wrapped (would have passed
    Attempt 5's shell pattern check) but must still be blocked."""

    def _stub_gate(self, literal_stdout: str) -> Path:
        gate = self.tmp / "stub_gate.py"
        gate.write_text(
            "import sys\n"
            "sys.stdin.read()\n"
            f"sys.stdout.write({literal_stdout!r})\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        return gate

    def _assert_blocked(self, literal_stdout: str) -> None:
        env = self._configured_env(gate_path=self._stub_gate(literal_stdout))
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")
        # The rejected output must never be forwarded verbatim.
        self.assertNotEqual(result.stdout, literal_stdout)

    def test_invalid_json_but_brace_wrapped_blocks(self) -> None:
        self._assert_blocked('{not-json}')

    def test_unsupported_decision_value_blocks(self) -> None:
        # Well-formed JSON, brace-wrapped, but "allow" is not a decision the
        # gate ever legitimately emits.
        self._assert_blocked('{"decision":"allow"}')

    def test_duplicate_key_json_blocks(self) -> None:
        # A naive parser resolves this to {"decision": "allow"} (last key
        # wins) while looking like a block on the surface.
        self._assert_blocked('{"decision":"block","reason":"","decision":"allow"}')

    def test_unrecognized_shape_blocks(self) -> None:
        self._assert_blocked('{"unexpected":true}')

    def test_block_missing_reason_key_blocks(self) -> None:
        self._assert_blocked('{"decision":"block"}')

    def test_block_extra_key_blocks(self) -> None:
        self._assert_blocked('{"decision":"block","reason":"","extra":1}')

    def test_block_wrong_reason_type_blocks(self) -> None:
        self._assert_blocked('{"decision":"block","reason":5}')

    def test_context_missing_additional_context_key_blocks(self) -> None:
        self._assert_blocked('{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit"}}')

    def test_context_extra_key_blocks(self) -> None:
        self._assert_blocked(
            '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit",'
            '"additionalContext":"","extra":1}}'
        )

    def test_context_wrong_event_name_blocks(self) -> None:
        self._assert_blocked(
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":""}}'
        )

    def test_context_wrong_additional_context_type_blocks(self) -> None:
        self._assert_blocked(
            '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":5}}'
        )

    def test_non_finite_constant_blocks(self) -> None:
        # NaN/Infinity are a non-standard JSON extension some parsers accept.
        self._assert_blocked('{"decision":"block","reason":NaN}')

    def test_exact_block_shape_passes(self) -> None:
        # Control: the real gate-owned block shape, byte for byte, passes.
        env = self._configured_env(
            gate_path=self._stub_gate('{"decision": "block", "reason": "why"}')
        )
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '{"decision": "block", "reason": "why"}')

    def test_exact_context_shape_passes(self) -> None:
        # Control: the real gate-owned context shape, byte for byte, passes.
        shape = (
            '{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", '
            '"additionalContext": "note"}}'
        )
        env = self._configured_env(gate_path=self._stub_gate(shape))
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, shape)


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

    def test_post_tool_failure_configured_broken_gate_still_fails_open(self) -> None:
        broken = self.tmp / "broken_gate.py"
        broken.write_text("this is not python (\n", encoding="utf-8")
        env = self._configured_env(gate_path=broken)
        result = _run_wrapper(
            "post-tool-failure",
            {
                "session_id": "s",
                "tool_name": "x",
                "tool_input": {},
                "error": "boom",
                "tool_use_id": "toolu-1",
            },
            env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


class MalformedStdinFailsClosedCases(_FaultInjectionCase):
    """A configured gate that cannot even read/parse its OWN stdin must still
    block/deny — never silently treat the unreadable input as an empty,
    harmless (operator-prompt-shaped) payload.

    Unlike the fault-injection cases above (a broken/missing gate FILE), this
    exercises the real gate against a corrupted hook INVOCATION: the process
    starts and runs, but the JSON Claude Code piped to its stdin cannot be
    read as a well-formed object. ``main()`` deliberately lets this crash
    uncaught rather than synthesizing ``payload = {}`` — an empty payload
    reads to every handler as "no room event, no session", which is exactly
    the shape of a legitimate operator prompt or an inert unconfigured call.
    """

    def _real_gate_env(self) -> dict:
        env = sandbox_env()
        home = Path(env["HOME"])
        (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        real_gate = (
            _REPO_ROOT / "integrations" / "claude-code" / "nunchi_claude_v2.py"
        )
        (home / ".claude" / "hooks" / "nunchi_claude_v2.py").write_text(
            real_gate.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (home / ".claude" / "nunchi-claude-v2.env").write_text(
            "NUNCHI_CLAUDE_V2_POLICY=/tmp/does-not-exist-for-this-test.json\n"
            f"NUNCHI_CLAUDE_V2_STATE_DIR={home / 'state'}\n",
            encoding="utf-8",
        )
        env["PYTHONPATH"] = str(_REPO_ROOT / "src")
        return env

    def _run_raw(self, hook_event: str, raw_stdin: str, env: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/bin/sh", str(_WRAPPER), hook_event],
            input=raw_stdin,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_malformed_json_stdin_blocks_user_prompt_submit(self) -> None:
        env = self._real_gate_env()
        result = self._run_raw("user-prompt-submit", "{not-valid-json", env)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(
            _cannot_be_interpreted_as_admission(result.stdout),
            f"malformed stdin was admissible: {result.stdout!r}",
        )
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")

    def test_duplicate_key_stdin_blocks_user_prompt_submit(self) -> None:
        env = self._real_gate_env()
        result = self._run_raw(
            "user-prompt-submit",
            '{"session_id": "s", "prompt": "hi", "session_id": "s"}',
            env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(_cannot_be_interpreted_as_admission(result.stdout))
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")

    def test_non_object_stdin_blocks_user_prompt_submit(self) -> None:
        env = self._real_gate_env()
        result = self._run_raw("user-prompt-submit", "[1, 2, 3]", env)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(_cannot_be_interpreted_as_admission(result.stdout))
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")

    def test_malformed_json_stdin_denies_pre_tool_fail_closed(self) -> None:
        env = self._real_gate_env()
        result = self._run_raw("pre-tool", "{not-valid-json", env)
        self.assertEqual(result.returncode, 2)

    def test_unconfigured_malformed_stdin_still_fails_open(self) -> None:
        # Unconfigured (no policy) stays inert regardless: a crash here must
        # not newly surface as a block for a host that never opted in.
        env = sandbox_env()
        home = Path(env["HOME"])
        (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        real_gate = (
            _REPO_ROOT / "integrations" / "claude-code" / "nunchi_claude_v2.py"
        )
        (home / ".claude" / "hooks" / "nunchi_claude_v2.py").write_text(
            real_gate.read_text(encoding="utf-8"), encoding="utf-8"
        )
        env["PYTHONPATH"] = str(_REPO_ROOT / "src")
        result = self._run_raw("user-prompt-submit", "{not-valid-json", env)
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

    def test_healthy_configured_operator_prompt_gets_explicit_non_empty_allow(self) -> None:
        # [N2-CLAUDE-A4-REWORK-01]: the plain-operator-prompt-while-configured
        # path used to be the one legitimate source of empty stdout at exit
        # 0. It must now emit an explicit, non-empty, semantically inert
        # decision — proving the fix closes the gap without changing real
        # operator-prompt behavior (still no observation/attention/receipts).
        env = self._configured_env(gate_path=None)
        home = Path(env["HOME"])
        (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        real_gate = (
            _REPO_ROOT / "integrations" / "claude-code" / "nunchi_claude_v2.py"
        )
        target = home / ".claude" / "hooks" / "nunchi_claude_v2.py"
        target.write_text(real_gate.read_text(encoding="utf-8"), encoding="utf-8")
        env["PYTHONPATH"] = str(_REPO_ROOT / "src")
        result = _run_wrapper(
            "user-prompt-submit",
            {"session_id": "s", "prompt": "run the tests please"},
            env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotEqual(result.stdout, "")
        self.assertFalse(_cannot_be_interpreted_as_admission(result.stdout))
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(
            parsed,
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "",
                }
            },
        )


class WrapperHealthyRoomRoundTripCases(_FaultInjectionCase):
    """The real gate's room-event outcomes (wake, block) survive the wrapper
    end to end — not just its config-error fallback."""

    def _real_gate_env(self, **policy_overrides) -> dict:
        from tests.v2 import claude_code_helpers as helpers

        env = sandbox_env()
        home = Path(env["HOME"])
        (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
        real_gate = (
            _REPO_ROOT / "integrations" / "claude-code" / "nunchi_claude_v2.py"
        )
        (home / ".claude" / "hooks" / "nunchi_claude_v2.py").write_text(
            real_gate.read_text(encoding="utf-8"), encoding="utf-8"
        )
        config_dir = home / "nunchi-v2-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        document = helpers.claude_policy_document(config_dir, **policy_overrides)
        policy_path = helpers.write_claude_policy(config_dir, document)
        env.update(
            {
                "PYTHONPATH": str(_REPO_ROOT / "src"),
                "NUNCHI_CLAUDE_V2_POLICY": str(policy_path),
                "NUNCHI_CLAUDE_V2_STATE_DIR": str(home / "state"),
                "NUNCHI_CLAUDE_V2_CHANNEL_ID": helpers.CHANNEL_ID,
                "NUNCHI_CLAUDE_V2_SELF_USER_ID": helpers.SELF_USER_ID,
                "NUNCHI_CLAUDE_V2_PARTICIPANT_ID": helpers.PARTICIPANT_ID,
                "NUNCHI_CLAUDE_V2_PARTICIPANT_NAME": "Station",
                "NUNCHI_CLAUDE_V2_SIDECAR": str(
                    home / ".claude" / "channels" / "discord" / "nunchi-v2" / "native-events.jsonl"
                ),
            }
        )
        return env

    def test_healthy_room_wake_through_real_gate_and_wrapper(self) -> None:
        from tests.v2 import claude_code_helpers as helpers

        # Trusted preattention bypass: zero classifier calls, deterministic
        # WAKE for any authorized event — no live classifier endpoint needed.
        env = self._real_gate_env(preattention_enabled=False)
        message_id = "9000000000000000001"
        helpers.append_sidecar(
            env, helpers.sidecar_row(message_id=message_id, content="hello room")
        )
        payload = helpers.prompt_payload(
            helpers.channel_prompt(message_id=message_id, body="hello room"),
            session_id="sess-real-wake",
        )
        result = _run_wrapper("user-prompt-submit", payload, env)
        self.assertEqual(result.returncode, 0)
        self.assertNotEqual(result.stdout, "")
        parsed = json.loads(result.stdout.strip())
        self.assertIn("hookSpecificOutput", parsed)
        self.assertIn(
            "source=PREATTENTION_BYPASS",
            parsed["hookSpecificOutput"]["additionalContext"],
        )

    def test_healthy_room_block_through_real_gate_and_wrapper(self) -> None:
        from tests.v2 import claude_code_helpers as helpers

        # An exact self-authored event is a transport-proven non-event
        # (SELF_RETAINED_NO_WAKE) — deterministic block, no classifier
        # involved, exercised through the real gate and wrapper.
        env = self._real_gate_env()
        message_id = "9000000000000000002"
        helpers.append_sidecar(
            env,
            helpers.sidecar_row(
                message_id=message_id,
                author_id=helpers.SELF_USER_ID,
                username="station",
                bot=True,
                content="on it",
            ),
        )
        payload = helpers.prompt_payload(
            helpers.channel_prompt(message_id=message_id, user="station", body="on it"),
            session_id="sess-real-block",
        )
        result = _run_wrapper("user-prompt-submit", payload, env)
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["decision"], "block")


class UnconfiguredInertAcrossAllHookEventsCase(_FaultInjectionCase):
    """Unconfigured mode is fully inert regardless of hook event or gate
    health — a broken/missing gate must never surface when there is no
    policy to enforce in the first place."""

    def _unconfigured_broken_env(self) -> dict:
        env = sandbox_env()  # no nunchi-claude-v2.env written: unconfigured
        broken = self.tmp / "broken_gate.py"
        broken.write_text("this is not python (\n", encoding="utf-8")
        env["NUNCHI_CLAUDE_V2_GATE"] = str(broken)
        return env

    def test_user_prompt_submit_inert_when_unconfigured(self) -> None:
        env = self._unconfigured_broken_env()
        result = _run_wrapper("user-prompt-submit", _prompt_payload(), env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_pre_tool_inert_when_unconfigured(self) -> None:
        env = self._unconfigured_broken_env()
        result = _run_wrapper(
            "pre-tool", {"session_id": "s", "tool_name": "Bash", "tool_input": {}}, env
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_stop_inert_when_unconfigured(self) -> None:
        env = self._unconfigured_broken_env()
        result = _run_wrapper("stop", {"session_id": "s"}, env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_post_tool_inert_when_unconfigured(self) -> None:
        env = self._unconfigured_broken_env()
        result = _run_wrapper(
            "post-tool",
            {"session_id": "s", "tool_name": "x", "tool_input": {}, "tool_response": {}},
            env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_post_tool_failure_inert_when_unconfigured(self) -> None:
        env = self._unconfigured_broken_env()
        result = _run_wrapper(
            "post-tool-failure",
            {
                "session_id": "s",
                "tool_name": "x",
                "tool_input": {},
                "error": "boom",
                "tool_use_id": "toolu-1",
            },
            env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
