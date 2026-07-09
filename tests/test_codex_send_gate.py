"""Tests for integrations/codex/nunchi_send_gate_codex.py.

The Codex outbound hook is the parity guard for room sends: a matching
send_message/reply_message PreToolUse call must be admitted by Nunchi before
Codex can post into the room. The transport backstop still exists, but these
tests assert the hook is a gate, not just telemetry.
"""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from tests.hook_sandbox import sandbox_env

_HOOK = (
    pathlib.Path(__file__).resolve().parent.parent
    / "integrations"
    / "codex"
    / "nunchi_send_gate_codex.py"
)


def _run_hook(hook_input, *, env_overrides: dict | None = None) -> tuple[int, str, str]:
    env = sandbox_env(env_overrides)
    stdin = hook_input if isinstance(hook_input, str) else json.dumps(hook_input)
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _hook_input(
    *,
    tool_name: str = "mcp__nunchi_discord__send_message",
    tool_input: dict | None = None,
    transcript_path: str | None = None,
    session_id: str = "sess-codex-outbound-1",
) -> dict:
    return {
        "session_id": session_id,
        "transcript_path": transcript_path,
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "turn_id": "turn-1",
        "tool_name": tool_name,
        "tool_input": tool_input
        if tool_input is not None
        else {"channel_id": "1522258711047831653", "content": "I can take this."},
    }


def _directive(verdict: str, reasons: list[str] | None = None) -> dict:
    return {
        "verdict": verdict,
        "silent": verdict == "PASS",
        "run_shape": "stub",
        "reasons": reasons or [f"stub reason for {verdict}"],
        "confidences": {"PASS": 0.8 if verdict == "PASS" else 0.1, "SPEAK": 0.9},
        "context_checked": [],
        "request_id": "req-1",
        "classifier_model": "stub",
        "degraded": False,
    }


class _GateStub:
    def __init__(
        self,
        directive: dict | str,
        exit_code: int = 0,
        delay_seconds: float = 0,
    ) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="nunchi-codex-send-hook-"))
        self.stdin_path = self.dir / "gate_stdin.json"
        self.model_path = self.dir / "gate_model.txt"
        self.receipts = self.dir / "receipts.jsonl"
        directive_path = self.dir / "directive.json"
        directive_path.write_text(
            directive if isinstance(directive, str) else json.dumps(directive)
        )
        self.path = self.dir / "stub-nunchi-channel.sh"
        self.path.write_text(
            "#!/bin/sh\n"
            f'cat > "{self.stdin_path}"\n'
            f'printf "%s" "${{NUNCHI_CLASSIFIER_MODEL:-}}" > "{self.model_path}"\n'
            f'sleep "{delay_seconds}"\n'
            f'if [ "{exit_code}" != "0" ]; then echo "stub gate error" >&2; exit {exit_code}; fi\n'
            f'cat "{directive_path}"\n'
        )
        self.path.chmod(self.path.stat().st_mode | stat.S_IXUSR)

    def env(self, extra: dict | None = None) -> dict:
        base = {
            "NUNCHI_CHANNEL_BIN": str(self.path),
            "NUNCHI_RUNNER_LOG": str(self.receipts),
        }
        if extra:
            base.update(extra)
        return base

    def called(self) -> bool:
        return self.stdin_path.exists()

    def payload(self) -> dict:
        return json.loads(self.stdin_path.read_text())

    def receipt_lines(self) -> list[dict]:
        if not self.receipts.exists():
            return []
        return [json.loads(l) for l in self.receipts.read_text().splitlines() if l.strip()]


def _write_transcript(entries: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return path


def _runner_context_prompt(
    *,
    channel_id: str = "1522258711047831653",
    message_id: str = "m-trigger",
    content: str = "Vigil, can you weigh in?",
) -> str:
    context = {
        "trigger": {
            "content": content,
            "author": "decisionparalysis",
            "author_kind": "human",
            "message_id": message_id,
            "timestamp": "2026-07-09T12:00:00Z",
        },
        "history": [
            {
                "content": "Earlier context",
                "author": "Aether",
                "author_kind": "peer_bot",
                "message_id": "m-history",
            }
        ],
        "surface": {"type": "channel", "channel_id": channel_id},
    }
    return (
        "[nunchi] Admitted room turn - verdict: SPEAK\n"
        f"<nunchi_context>{json.dumps(context)}</nunchi_context>\n"
    )


def _codex_user_entry(text: str) -> dict:
    return {
        "timestamp": "2026-07-09T12:00:01Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def _codex_send_entry(channel_id: str, content: str, *, call_id: str = "call-prior-send") -> dict:
    return {
        "timestamp": "2026-07-09T12:00:02Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "mcp__nunchi_discord__send_message",
            "arguments": json.dumps({"channel_id": channel_id, "content": content}),
            "call_id": call_id,
        },
    }


def _prior_allow_receipt(
    *,
    session_id: str = "sess-codex-outbound-1",
    channel_id: str = "1522258711047831653",
    trigger_message_id: str = "m-trigger",
) -> dict:
    return {
        "ts": "2026-07-09T12:00:03Z",
        "direction": "hook-outbound",
        "session_id": session_id,
        "channel": channel_id,
        "trigger_message_id": trigger_message_id,
        "verdict": "SPEAK",
        "action": "allow-speak",
        "history_len": 1,
        "elapsed_ms": 1.0,
        "reasons": ["prior allow"],
    }


def _deny_reason(stdout: str) -> str:
    parsed = json.loads(stdout)
    return parsed["hookSpecificOutput"]["permissionDecisionReason"]


class TestToolFiltering(unittest.TestCase):
    def test_non_send_tool_is_ignored(self):
        rc, out, _ = _run_hook(_hook_input(tool_name="Read"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_direct_discord_webhook_bash_send_is_denied(self):
        stub = _GateStub(_directive("SPEAK"))

        rc, out, _ = _run_hook(
            _hook_input(
                tool_name="Bash",
                tool_input={
                    "command": (
                        "curl -X POST https://discord.com/api/webhooks/123/token "
                        "-d '{\"content\":\"bypass\"}'"
                    )
                },
            ),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("direct Discord send commands", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(stub.receipt_lines()[0]["action"], "deny-direct-send-path")

    def test_matching_send_without_room_context_denies_without_gate_call(self):
        stub = _GateStub(_directive("SPEAK"))
        transcript = _write_transcript([_codex_user_entry("ordinary prompt")])

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("no Nunchi room context", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(stub.receipt_lines()[0]["action"], "deny-untriggered")

    def test_context_without_trigger_message_id_is_denied(self):
        stub = _GateStub(_directive("SPEAK"))
        transcript = _write_transcript(
            [_codex_user_entry(_runner_context_prompt(message_id=""))]
        )

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("stable message_id", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(stub.receipt_lines()[0]["action"], "deny-context-error")

    def test_matching_send_with_malformed_tool_input_is_denied(self):
        stub = _GateStub(_directive("SPEAK"))

        rc, out, _ = _run_hook(
            _hook_input(tool_input={"channel_id": "1522258711047831653"}),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("missing channel or content", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(
            stub.receipt_lines()[0]["action"], "deny-malformed-envelope"
        )

    def test_malformed_json_identifying_send_is_denied(self):
        stub = _GateStub(_directive("SPEAK"))
        raw = '{"tool_name":"mcp__nunchi_discord__send_message","tool_input":'

        rc, out, _ = _run_hook(raw, env_overrides=stub.env())

        self.assertEqual(rc, 0)
        self.assertIn("malformed PreToolUse", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(
            stub.receipt_lines()[0]["action"], "deny-malformed-envelope"
        )

    def test_malformed_json_for_unrelated_tool_is_ignored(self):
        stub = _GateStub(_directive("SPEAK"))
        raw = '{"tool_name":"Read","tool_input":'

        rc, out, err = _run_hook(raw, env_overrides=stub.env())

        self.assertEqual((rc, out, err), (0, "", ""))
        self.assertFalse(stub.called())
        self.assertEqual(stub.receipt_lines(), [])

    def test_stale_context_from_older_user_turn_is_not_reused(self):
        stub = _GateStub(_directive("SPEAK"))
        transcript = _write_transcript(
            [
                _codex_user_entry(_runner_context_prompt()),
                _codex_user_entry("operator asks for a fresh manual send later"),
            ]
        )

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("no current Nunchi room context", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(stub.receipt_lines()[0]["action"], "deny-untriggered")


class TestOutboundGate(unittest.TestCase):
    def test_invalid_numeric_env_does_not_crash_hook(self):
        stub = _GateStub(_directive("PASS", ["bad env still gates"]))
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env({"NUNCHI_HOOK_TIMEOUT": "not-an-int"}),
        )

        self.assertEqual(rc, 0)
        self.assertIn("bad env still gates", _deny_reason(out))
        self.assertTrue(stub.called())

    def test_pass_denies_mcp_send_tool(self):
        stub = _GateStub(_directive("PASS", ["two humans are mid-conversation"]))
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        decision = parsed["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("PASS", decision["permissionDecisionReason"])
        self.assertIn("two humans are mid-conversation", decision["permissionDecisionReason"])
        receipts = stub.receipt_lines()
        self.assertEqual(receipts[0]["direction"], "hook-outbound")
        self.assertEqual(receipts[0]["action"], "deny-pass")

    def test_speak_allows_mcp_send_tool_and_payload_has_room_context(self):
        stub = _GateStub(_directive("SPEAK", ["addressed Vigil"]))
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(
                {
                    "NUNCHI_HOOK_AGENT_ID": "vigil",
                    "NUNCHI_HOOK_MENTION_ID": "1494822530643398827",
                    "NUNCHI_HOOK_ALIASES": "Vigil,Codex",
                }
            ),
        )

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "allow")
        payload = stub.payload()
        self.assertEqual(payload["trigger"]["message_id"], "m-trigger")
        self.assertEqual(payload["history"][0]["content"], "Earlier context")
        self.assertEqual(
            payload["agent"],
            {
                "id": "vigil",
                "mention_id": "1494822530643398827",
                "aliases": ["Vigil", "Codex"],
            },
        )
        self.assertEqual(
            payload["surface"],
            {"type": "channel", "channel_id": "1522258711047831653"},
        )
        self.assertEqual(stub.receipt_lines()[0]["action"], "allow-speak")

    def test_current_inflight_send_in_transcript_is_not_counted_as_prior(self):
        stub = _GateStub(_directive("SPEAK", ["first send attempt"]))
        transcript = _write_transcript(
            [
                _codex_user_entry(_runner_context_prompt()),
                _codex_send_entry("1522258711047831653", "current in-flight send"),
            ]
        )

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertTrue(stub.called())
        self.assertEqual(stub.receipt_lines()[0]["action"], "allow-speak")

    def test_gate_error_denies_by_default(self):
        stub = _GateStub(_directive("SPEAK"), exit_code=2)
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("nunchi gate error", _deny_reason(out))
        self.assertEqual(stub.receipt_lines()[0]["action"], "deny-gate-error")

    def test_fail_open_is_explicit_override(self):
        stub = _GateStub(_directive("SPEAK"), exit_code=2)
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env({"NUNCHI_HOOK_FAIL_POLICY": "open"}),
        )

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertEqual(stub.receipt_lines()[0]["action"], "allow-gate-error")

    def test_allow_is_denied_when_receipt_cannot_be_persisted(self):
        stub = _GateStub(_directive("SPEAK", ["addressed Vigil"]))
        stub.receipts.mkdir()
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        rc, out, err = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("receipt could not be persisted", _deny_reason(out))
        self.assertIn("outbound receipt error", err)
        self.assertTrue(stub.called())

    def test_second_send_for_same_room_context_is_denied_without_gate_call(self):
        stub = _GateStub(_directive("SPEAK"))
        stub.receipts.write_text(json.dumps(_prior_allow_receipt()) + "\n")
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        rc, out, _ = _run_hook(
            _hook_input(transcript_path=transcript),
            env_overrides=stub.env(),
        )

        self.assertEqual(rc, 0)
        self.assertIn("already sent", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(stub.receipt_lines()[-1]["action"], "deny-already-sent")

    def test_concurrent_sends_for_same_context_allow_exactly_one(self):
        stub = _GateStub(_directive("SPEAK"), delay_seconds=0.2)
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])

        def run_once():
            return _run_hook(
                _hook_input(transcript_path=transcript),
                env_overrides=stub.env(),
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run_once(), range(2)))

        decisions = [
            json.loads(stdout)["hookSpecificOutput"]["permissionDecision"]
            for _, stdout, _ in results
        ]
        self.assertEqual(sorted(decisions), ["allow", "deny"])
        actions = [receipt["action"] for receipt in stub.receipt_lines()]
        self.assertEqual(actions.count("allow-speak"), 1)
        self.assertEqual(actions.count("deny-already-sent"), 1)


class TestHotRuntimePolicy(unittest.TestCase):
    def _run_with_state(self, state: dict, stub: _GateStub):
        state_path = stub.dir / "runtime-state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        transcript = _write_transcript([_codex_user_entry(_runner_context_prompt())])
        try:
            return _run_hook(
                _hook_input(transcript_path=transcript),
                env_overrides=stub.env({"NUNCHI_RUNNER_STATE": str(state_path)}),
            )
        finally:
            os.unlink(transcript)

    def test_disabled_channel_denies_without_gate_call(self):
        stub = _GateStub(_directive("SPEAK"))
        rc, out, err = self._run_with_state(
            {
                "version": 1,
                "channels": {"1522258711047831653": {"enabled": False}},
            },
            stub,
        )

        self.assertEqual((rc, err), (0, ""))
        self.assertIn("disabled", _deny_reason(out))
        self.assertFalse(stub.called())
        self.assertEqual(stub.receipt_lines()[-1]["action"], "deny-disabled")

    def test_runtime_model_and_pinned_rules_reach_outbound_gate(self):
        stub = _GateStub(_directive("SPEAK"))
        rc, out, err = self._run_with_state(
            {
                "version": 1,
                "channels": {
                    "1522258711047831653": {
                        "model": "deepseek/deepseek-v4-flash",
                        "pinned_rules": "Wait for a useful opening.",
                    }
                },
            },
            stub,
        )

        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(
            json.loads(out)["hookSpecificOutput"]["permissionDecision"],
            "allow",
        )
        self.assertEqual(
            stub.model_path.read_text(encoding="utf-8"),
            "deepseek/deepseek-v4-flash",
        )
        self.assertEqual(stub.payload()["pinned_rules"], "Wait for a useful opening.")


if __name__ == "__main__":
    unittest.main()
