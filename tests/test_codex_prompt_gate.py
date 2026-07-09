"""Tests for integrations/codex/nunchi_prompt_gate_codex.py.

All tests are stdlib-only (no pytest). The gate binary is faked with a tiny
shell stub written to a temp directory; no network or real model calls.
Tests run the hook as a subprocess with a Codex UserPromptSubmit envelope on
stdin and assert on stdout + exit code + receipts.

Mirrors tests/test_claude_code_hook.py's stubbed-gate-binary pattern.
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

from tests.hook_sandbox import sandbox_env

_HOOK = (
    pathlib.Path(__file__).resolve().parent.parent
    / "integrations"
    / "codex"
    / "nunchi_prompt_gate_codex.py"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_hook(hook_input, *, env_overrides: dict | None = None) -> tuple[int, str, str]:
    """Run the hook with hook_input (dict or raw str) on stdin.

    The env is always sandboxed (HOME + NUNCHI_HOOK_LOG pinned to a temp dir)
    so no receipt can ever fall through to the operator's real log file.
    """
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


def _channel_prompt(
    *,
    chat_id: str = "c1",
    message_id: str = "m1",
    user: str = "zoe",
    body: str = "hello",
    ts: str = "2026-07-07T00:00:00Z",
) -> str:
    return (
        f'<channel source="discord" chat_id="{chat_id}" message_id="{message_id}"'
        f' user="{user}" ts="{ts}">{body}</channel>'
    )


def _hook_input(
    *,
    prompt: str = "",
    transcript_path: str | None = None,
    session_id: str = "sess-codex-1",
) -> dict:
    """A Codex UserPromptSubmit envelope (developers.openai.com/codex/hooks)."""
    return {
        "session_id": session_id,
        "transcript_path": transcript_path,
        "cwd": "/tmp",
        "hook_event_name": "UserPromptSubmit",
        "model": "gpt-5-codex",
        "turn_id": "turn-1",
        "permission_mode": "default",
        "prompt": prompt,
    }


def _directive(verdict: str, reasons: list[str] | None = None) -> dict:
    silent = verdict == "PASS"
    return {
        "verdict": verdict,
        "silent": silent,
        "run_shape": "stub shape",
        "reasons": reasons or [f"stub reason for {verdict}"],
        "confidences": {"PASS": 0.7 if silent else 0.1, "ACK": 0.1, "ASK": 0.1, "SPEAK": 0.1},
        "context_checked": [],
        "request_id": "req-1",
        "classifier_model": "stub",
        "degraded": False,
    }


class _GateStub:
    """Shell-script gate stub in a tempdir: captures stdin, prints a directive."""

    def __init__(self, directive: dict | str, exit_code: int = 0) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="nunchi-codex-hook-test-"))
        self.stdin_path = self.dir / "gate_stdin.json"
        self.receipts = self.dir / "receipts.jsonl"
        directive_path = self.dir / "directive.json"
        directive_path.write_text(
            directive if isinstance(directive, str) else json.dumps(directive)
        )
        self.path = self.dir / "stub-nunchi-channel.sh"
        self.path.write_text(
            "#!/bin/sh\n"
            f'cat > "{self.stdin_path}"\n'
            f'if [ "{exit_code}" != "0" ]; then echo "stub gate error" >&2; exit {exit_code}; fi\n'
            f'cat "{directive_path}"\n'
        )
        self.path.chmod(self.path.stat().st_mode | stat.S_IXUSR)

    def env(self) -> dict:
        return {
            "NUNCHI_CHANNEL_BIN": str(self.path),
            "NUNCHI_RUNNER_LOG": str(self.receipts),
        }

    def called(self) -> bool:
        return self.stdin_path.exists()

    def payload(self) -> dict:
        return json.loads(self.stdin_path.read_text())

    def receipt_lines(self) -> list[dict]:
        if not self.receipts.exists():
            return []
        return [json.loads(l) for l in self.receipts.read_text().splitlines() if l.strip()]


def _rollout_user_entry(text: str) -> dict:
    """A Codex rollout JSONL line: payload-wrapped user message."""
    return {
        "timestamp": "2026-07-07T00:00:00Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def _rollout_send_entry(channel_id: str, content: str) -> dict:
    """A Codex rollout JSONL line: MCP send_message function call."""
    return {
        "timestamp": "2026-07-07T00:00:01Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "nunchi-discord__send_message",
            "arguments": json.dumps({"channel_id": channel_id, "content": content}),
            "call_id": "call_1",
        },
    }


def _write_transcript(lines: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")
    return path


# ---------------------------------------------------------------------------
# Non-channel prompts bypass the gate entirely
# ---------------------------------------------------------------------------


class TestNonChannelBypass(unittest.TestCase):
    def test_plain_operator_prompt_allowed(self):
        rc, out, _ = _run_hook(
            _hook_input(prompt="refactor the parser please"),
            env_overrides={"NUNCHI_CHANNEL_BIN": "/nonexistent"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_empty_prompt_allowed(self):
        rc, out, _ = _run_hook(
            _hook_input(prompt=""), env_overrides={"NUNCHI_CHANNEL_BIN": "/nonexistent"}
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_partial_channel_tag_allowed(self):
        rc, out, _ = _run_hook(
            _hook_input(prompt='<channel chat_id="c1">no closing tag'),
            env_overrides={"NUNCHI_CHANNEL_BIN": "/nonexistent"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_gate_not_invoked_and_no_receipt_for_non_channel_prompt(self):
        stub = _GateStub(_directive("SPEAK"))
        rc, out, _ = _run_hook(
            _hook_input(prompt="just typing at the terminal"), env_overrides=stub.env()
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertFalse(stub.called(), "gate must not run for non-channel prompts")
        self.assertEqual(stub.receipt_lines(), [])


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


class TestPassBlocks(unittest.TestCase):
    def test_pass_emits_block_json(self):
        stub = _GateStub(_directive("PASS", ["two humans are mid-conversation"]))
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt(body="what do you all think?")),
            env_overrides=stub.env(),
        )
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["decision"], "block")
        self.assertIn("PASS", parsed["reason"])
        self.assertIn("two humans are mid-conversation", parsed["reason"])

    def test_pass_with_no_reasons_uses_fallback(self):
        directive = _directive("PASS")
        directive["reasons"] = []
        stub = _GateStub(directive)
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt()), env_overrides=stub.env()
        )
        parsed = json.loads(out)
        self.assertEqual(parsed["decision"], "block")
        self.assertIn("PASS", parsed["reason"])

    def test_pass_receipt_direction_hook_inbound(self):
        stub = _GateStub(_directive("PASS"))
        _run_hook(_hook_input(prompt=_channel_prompt()), env_overrides=stub.env())
        receipts = stub.receipt_lines()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["direction"], "hook-inbound")
        self.assertEqual(receipts[0]["action"], "block-pass")
        self.assertEqual(receipts[0]["verdict"], "PASS")


class TestAllowVerdicts(unittest.TestCase):
    def test_speak_ack_ask_allow(self):
        for verdict in ("SPEAK", "ACK", "ASK"):
            with self.subTest(verdict=verdict):
                stub = _GateStub(_directive(verdict))
                rc, out, _ = _run_hook(
                    _hook_input(prompt=_channel_prompt()), env_overrides=stub.env()
                )
                self.assertEqual(rc, 0)
                self.assertEqual(out.strip(), "")
                receipts = stub.receipt_lines()
                self.assertEqual(receipts[0]["action"], f"allow-{verdict.lower()}")
                self.assertEqual(receipts[0]["direction"], "hook-inbound")


# ---------------------------------------------------------------------------
# Fail-open on any gate failure
# ---------------------------------------------------------------------------


class TestFailOpen(unittest.TestCase):
    def test_gate_nonzero_exit_allows(self):
        stub = _GateStub(_directive("PASS"), exit_code=3)
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt()), env_overrides=stub.env()
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        receipts = stub.receipt_lines()
        self.assertEqual(receipts[0]["action"], "allow-gate-error")
        self.assertIn("error", receipts[0])

    def test_gate_invalid_json_allows(self):
        stub = _GateStub("definitely not json")
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt()), env_overrides=stub.env()
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertEqual(stub.receipt_lines()[0]["action"], "allow-gate-error")

    def test_gate_missing_verdict_allows_as_gate_error(self):
        stub = _GateStub({"silent": False, "reasons": ["malformed"]})
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt()), env_overrides=stub.env()
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        receipts = stub.receipt_lines()
        self.assertEqual(receipts[0]["action"], "allow-gate-error")
        self.assertIn("malformed directive", receipts[0]["error"])

    def test_gate_contradictory_silent_flag_allows_as_gate_error(self):
        directive = _directive("SPEAK")
        directive["silent"] = True
        stub = _GateStub(directive)
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt()), env_overrides=stub.env()
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        receipts = stub.receipt_lines()
        self.assertEqual(receipts[0]["action"], "allow-gate-error")
        self.assertIn("contradictory silent", receipts[0]["error"])

    def test_missing_gate_binary_allows(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "receipts.jsonl")
            rc, out, _ = _run_hook(
                _hook_input(prompt=_channel_prompt()),
                env_overrides={
                    "NUNCHI_CHANNEL_BIN": "/nonexistent/nunchi-channel",
                    "NUNCHI_RUNNER_LOG": log,
                },
            )
            self.assertEqual(rc, 0)
            self.assertEqual(out.strip(), "")
            with open(log) as fh:
                record = json.loads(fh.readline())
            self.assertEqual(record["action"], "allow-gate-error")

    def test_malformed_stdin_allows_silently(self):
        rc, out, _ = _run_hook(
            "not valid json {{{{", env_overrides={"NUNCHI_CHANNEL_BIN": "/nonexistent"}
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_non_dict_stdin_allows_silently(self):
        rc, out, _ = _run_hook(
            '["not", "a", "dict"]', env_overrides={"NUNCHI_CHANNEL_BIN": "/nonexistent"}
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_null_transcript_path_tolerated(self):
        stub = _GateStub(_directive("SPEAK"))
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt(), transcript_path=None),
            env_overrides=stub.env(),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertEqual(stub.payload()["history"], [])


# ---------------------------------------------------------------------------
# Payload and rollout-transcript history
# ---------------------------------------------------------------------------


class TestPayloadAndHistory(unittest.TestCase):
    def test_trigger_fields_from_channel_tag(self):
        stub = _GateStub(_directive("SPEAK"))
        prompt = _channel_prompt(chat_id="c7", message_id="m9", user="vigil", body="ping dalgos")
        _run_hook(
            _hook_input(prompt=prompt),
            env_overrides={
                **stub.env(),
                "NUNCHI_HOOK_AGENT_ID": "dalgos",
                "NUNCHI_HOOK_MENTION_ID": "<@42>",
                "NUNCHI_HOOK_PEER_BOTS": "vigil",
            },
        )
        payload = stub.payload()
        self.assertEqual(payload["trigger"]["content"], "ping dalgos")
        self.assertEqual(payload["trigger"]["author"], "vigil")
        self.assertEqual(payload["trigger"]["author_kind"], "peer_bot")
        self.assertEqual(payload["trigger"]["message_id"], "m9")
        self.assertEqual(payload["agent"], {"id": "dalgos", "mention_id": "<@42>"})
        self.assertEqual(payload["fail_policy"], "raise")

    def test_rollout_history_inbound_and_self_sends(self):
        transcript = _write_transcript(
            [
                _rollout_user_entry(
                    _channel_prompt(chat_id="c1", message_id="m1", user="zoe", body="earlier ask")
                ),
                _rollout_send_entry("c1", "earlier reply from the agent"),
                _rollout_user_entry(
                    _channel_prompt(chat_id="OTHER", message_id="x1", user="zoe", body="other room")
                ),
            ]
        )
        stub = _GateStub(_directive("SPEAK"))
        _run_hook(
            _hook_input(
                prompt=_channel_prompt(chat_id="c1", message_id="m2", body="new trigger"),
                transcript_path=transcript,
            ),
            env_overrides=stub.env(),
        )
        os.unlink(transcript)

        history = stub.payload()["history"]
        self.assertEqual(len(history), 2, f"unexpected history: {history}")
        self.assertEqual(history[0]["content"], "earlier ask")
        self.assertEqual(history[0]["author_kind"], "human")
        self.assertEqual(history[1]["content"], "earlier reply from the agent")
        self.assertEqual(history[1]["author_kind"], "self")

    def test_history_window_env_caps_history(self):
        lines = [
            _rollout_user_entry(
                _channel_prompt(chat_id="c1", message_id=f"m{i}", body=f"line {i}")
            )
            for i in range(6)
        ]
        transcript = _write_transcript(lines)
        stub = _GateStub(_directive("SPEAK"))
        _run_hook(
            _hook_input(prompt=_channel_prompt(chat_id="c1"), transcript_path=transcript),
            env_overrides={**stub.env(), "NUNCHI_HOOK_HISTORY_WINDOW": "2"},
        )
        os.unlink(transcript)

        history = stub.payload()["history"]
        self.assertEqual([h["content"] for h in history], ["line 4", "line 5"])

    def test_unreadable_transcript_fails_soft_to_empty_history(self):
        stub = _GateStub(_directive("SPEAK"))
        rc, out, _ = _run_hook(
            _hook_input(prompt=_channel_prompt(), transcript_path="/nonexistent/rollout.jsonl"),
            env_overrides=stub.env(),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stub.payload()["history"], [])


class TestAgentAliases(unittest.TestCase):
    """NUNCHI_HOOK_ALIASES lands in the payload as agent.aliases."""

    def test_aliases_env_lands_in_payload_cleaned_and_deduped(self):
        stub = _GateStub(_directive("SPEAK"))
        _run_hook(
            _hook_input(prompt=_channel_prompt()),
            env_overrides={
                **stub.env(),
                "NUNCHI_HOOK_AGENT_ID": "vigil",
                "NUNCHI_HOOK_MENTION_ID": "111",
                # dupes of agent_id/mention_id and blanks must be dropped
                "NUNCHI_HOOK_ALIASES": " Vigil, Codex ,vigil,111,, Vigil ",
            },
        )
        self.assertEqual(
            stub.payload()["agent"],
            {"id": "vigil", "mention_id": "111", "aliases": ["Vigil", "Codex"]},
        )

    def test_no_aliases_env_keeps_agent_shape_unchanged(self):
        stub = _GateStub(_directive("SPEAK"))
        _run_hook(
            _hook_input(prompt=_channel_prompt()),
            env_overrides={
                **stub.env(),
                "NUNCHI_HOOK_AGENT_ID": "vigil",
                "NUNCHI_HOOK_MENTION_ID": "111",
                "NUNCHI_HOOK_ALIASES": "",
            },
        )
        self.assertEqual(stub.payload()["agent"], {"id": "vigil", "mention_id": "111"})


if __name__ == "__main__":
    unittest.main()
