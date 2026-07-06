"""Tests for integrations/claude-code/nunchi_gate_hook.py.

All tests are stdlib-only (no pytest). The gate binary is faked with a tiny
Python stub script written to a temp directory; no network or real model calls.
Tests run the hook as a subprocess and assert on stdout + exit code.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

# Path to the hook script under test
_HOOK = (
    pathlib.Path(__file__).resolve().parent.parent
    / "integrations"
    / "claude-code"
    / "nunchi_gate_hook.py"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_hook(
    hook_input: dict,
    *,
    env_overrides: dict | None = None,
) -> tuple[int, str, str]:
    """Run the hook with hook_input JSON on stdin; return (returncode, stdout, stderr)."""
    env = {**os.environ, **(env_overrides or {})}
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _make_transcript(lines: list[dict]) -> str:
    """Write JSONL lines to a temp file; return the path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")
    return path


def _user_channel_entry(
    *,
    chat_id: str,
    message_id: str,
    user: str,
    body: str,
    ts: str = "2026-01-01T00:00:00Z",
    extra_attrs: str = "",
) -> dict:
    """Build a user JSONL entry with a <channel ...> tag."""
    tag = (
        f'<channel source="plugin:discord:discord"'
        f' chat_id="{chat_id}"'
        f' message_id="{message_id}"'
        f' user="{user}"'
        f' ts="{ts}"'
        f"{' ' + extra_attrs if extra_attrs else ''}>\n{body}\n</channel>"
    )
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": tag,
        },
    }


def _user_channel_entry_with_preamble(
    *,
    chat_id: str,
    message_id: str,
    user: str,
    body: str,
    preamble: str = "",
) -> dict:
    """Build a user entry where channel tag has surrounding system-reminder text."""
    tag = (
        f'{preamble}'
        f'<channel source="discord" message_id="{message_id}" chat_id="{chat_id}"'
        f' user="{user}" ts="2026-01-01T00:00:00Z">\n{body}\n</channel>'
    )
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": tag,
        },
    }


def _assistant_reply_entry(
    *,
    chat_id: str,
    text: str,
    tool_use_id: str = "toolu_abc",
    tool_name: str = "mcp__plugin_discord_discord__reply",
) -> dict:
    """Build an assistant JSONL entry with a tool_use reply block."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": {
                        "chat_id": chat_id,
                        "text": text,
                    },
                }
            ],
        },
    }


def _hook_input(
    *,
    tool_name: str = "mcp__plugin_discord_discord__reply",
    chat_id: str = "c1",
    text: str = "hello",
    transcript_path: str = "",
    session_id: str = "sess-abc",
) -> dict:
    return {
        "session_id": session_id,
        "transcript_path": transcript_path,
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {
            "chat_id": chat_id,
            "text": text,
        },
        "cwd": "/tmp",
        "permission_mode": "default",
    }


def _make_gate_stub(directive: dict, exit_code: int = 0) -> str:
    """Write a stub nunchi-channel script to a temp dir; return its path.

    The directive is embedded as a JSON *string* literal so Python booleans
    and null don't cause a NameError when the stub is exec'd.
    """
    # Double-encode: the outer json.dumps produces a Python string literal
    # containing valid JSON that the stub can print directly.
    json_literal = json.dumps(json.dumps(directive))
    stub_code = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys
        sys.stdin.read()  # consume stdin
        if {exit_code} != 0:
            print("stub gate error", file=sys.stderr)
            sys.exit({exit_code})
        print({json_literal})
        sys.exit(0)
    """)
    fd, path = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w") as fh:
        fh.write(stub_code)
    return path


def _gate_stub_env(directive: dict, exit_code: int = 0) -> tuple[str, dict]:
    """Return (stub_path, env_overrides) for a gate stub."""
    stub = _make_gate_stub(directive, exit_code)
    bin_path = f"{sys.executable} {stub}"
    # Use a shell wrapper so it can be invoked by subprocess.run([bin])
    # Instead, write a proper executable wrapper script
    wrapper_fd, wrapper_path = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(wrapper_fd, "w") as fh:
        fh.write(f"#!/bin/sh\n{sys.executable} {stub} \"$@\"\n")
    os.chmod(wrapper_path, 0o755)
    return wrapper_path, {"NUNCHI_CHANNEL_BIN": wrapper_path}


def _make_pass_directive(reasons: list[str] | None = None) -> dict:
    return {
        "verdict": "PASS",
        "silent": True,
        "run_shape": "Stay silent. Post nothing to the channel for this turn.",
        "reasons": reasons or ["no need to speak"],
        "confidences": {"PASS": 0.9, "ACK": 0.05, "ASK": 0.03, "SPEAK": 0.02},
        "context_checked": [],
        "request_id": "req-1",
        "classifier_model": "stub",
        "degraded": False,
    }


def _make_speak_directive(reasons: list[str] | None = None) -> dict:
    return {
        "verdict": "SPEAK",
        "silent": False,
        "run_shape": "Produce one normal participant turn.",
        "reasons": reasons or ["user addressed agent directly"],
        "confidences": {"PASS": 0.05, "ACK": 0.02, "ASK": 0.03, "SPEAK": 0.9},
        "context_checked": [],
        "request_id": "req-2",
        "classifier_model": "stub",
        "degraded": False,
    }


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestToolPatternFiltering(unittest.TestCase):
    """Non-matching tool names must exit 0 silently."""

    def test_non_reply_tool_is_ignored(self):
        rc, out, err = _run_hook(_hook_input(tool_name="Bash"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_read_tool_is_ignored(self):
        rc, out, err = _run_hook(_hook_input(tool_name="Read"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_custom_pattern_matches(self):
        """A custom NUNCHI_HOOK_TOOL_PATTERN selects the right tool."""
        # With default pattern __reply$, any tool ending in __reply matches
        rc, out, err = _run_hook(
            _hook_input(tool_name="some__other__reply", transcript_path=""),
            env_overrides={"NUNCHI_HOOK_TOOL_PATTERN": "__reply$"},
        )
        # No transcript → exits 0 silently (no transcript_path)
        self.assertEqual(rc, 0)

    def test_tool_without_chat_id_is_ignored(self):
        """Tools matching the pattern but lacking chat_id in input pass through."""
        inp = {
            "session_id": "s",
            "transcript_path": "",
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__plugin_discord_discord__reply",
            "tool_input": {"text": "hello"},  # no chat_id
            "cwd": "/tmp",
        }
        rc, out, err = _run_hook(inp)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_tool_without_text_is_ignored(self):
        """Tools matching the pattern but lacking text in input pass through."""
        inp = {
            "session_id": "s",
            "transcript_path": "",
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__plugin_discord_discord__reply",
            "tool_input": {"chat_id": "123"},  # no text
            "cwd": "/tmp",
        }
        rc, out, err = _run_hook(inp)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


class TestInboundChannelExtraction(unittest.TestCase):
    """Inbound <channel ...> tags are correctly parsed from user entries."""

    def _extract_events(self, lines: list[dict], chat_id: str) -> list[dict]:
        """Use the hook module's _parse_transcript via a stub transcript."""
        # Import hook module directly for unit-style extraction tests.
        # We need to import it, accounting for the env vars at module import time.
        # Use subprocess to call a helper that imports and prints parsed events.
        tpath = _make_transcript(lines)
        code = textwrap.dedent(f"""\
            import sys, json, os
            sys.path.insert(0, r"{str(_HOOK.parent)}")
            # Patch module-level env before import
            os.environ.setdefault("NUNCHI_HOOK_AGENT_ID", "agent")
            import importlib.util
            spec = importlib.util.spec_from_file_location("hook", r"{str(_HOOK)}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            events = mod._parse_transcript(r"{tpath}", "{chat_id}")
            print(json.dumps(events))
        """)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
        )
        os.unlink(tpath)
        if result.returncode != 0:
            self.fail(f"Helper failed: {result.stderr}")
        return json.loads(result.stdout)

    def test_basic_inbound_extraction(self):
        lines = [
            _user_channel_entry(
                chat_id="c1", message_id="m1", user="zoe", body="hello agent"
            )
        ]
        events = self._extract_events(lines, "c1")
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["kind"], "inbound")
        self.assertEqual(ev["author"], "zoe")
        self.assertEqual(ev["author_kind"], "human")
        self.assertEqual(ev["message_id"], "m1")
        self.assertEqual(ev["content"], "hello agent")

    def test_attribute_order_variant(self):
        """chat_id can appear in any position in the attribute list."""
        # Use _user_channel_entry_with_preamble which has a different attr order
        lines = [
            _user_channel_entry_with_preamble(
                chat_id="c1", message_id="m2", user="bob", body="test content"
            )
        ]
        events = self._extract_events(lines, "c1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["message_id"], "m2")
        self.assertEqual(events[0]["author"], "bob")
        self.assertEqual(events[0]["content"], "test content")

    def test_surrounding_system_reminder_text(self):
        """Channel tag embedded in surrounding text (like a system-reminder) is extracted."""
        preamble = "<system-reminder>You are helpful.</system-reminder>\n\n"
        lines = [
            _user_channel_entry_with_preamble(
                chat_id="c1", message_id="m3", user="alice",
                body="what is two plus two", preamble=preamble,
            )
        ]
        events = self._extract_events(lines, "c1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["content"], "what is two plus two")
        self.assertEqual(events[0]["author"], "alice")

    def test_ignores_other_chat_id(self):
        """Messages for a different chat_id are ignored."""
        lines = [
            _user_channel_entry(
                chat_id="other-chat", message_id="m-other", user="zoe", body="wrong chat"
            ),
            _user_channel_entry(
                chat_id="c1", message_id="m1", user="zoe", body="right chat"
            ),
        ]
        events = self._extract_events(lines, "c1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["message_id"], "m1")

    def test_peer_bot_author_kind(self):
        """Users in NUNCHI_HOOK_PEER_BOTS get author_kind peer_bot."""
        lines = [
            _user_channel_entry(
                chat_id="c1", message_id="m1", user="vigil", body="update done"
            )
        ]
        code = textwrap.dedent(f"""\
            import sys, json, os
            os.environ["NUNCHI_HOOK_PEER_BOTS"] = "vigil,station"
            os.environ.setdefault("NUNCHI_HOOK_AGENT_ID", "agent")
            import importlib.util
            spec = importlib.util.spec_from_file_location("hook", r"{str(_HOOK)}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            tpath = r"{_make_transcript(lines)}"
            events = mod._parse_transcript(tpath, "c1")
            print(json.dumps(events))
        """)
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        events = json.loads(result.stdout)
        self.assertEqual(events[0]["author_kind"], "peer_bot")


class TestSelfSendExtraction(unittest.TestCase):
    """Outbound assistant tool_use reply blocks are extracted as self events."""

    def _extract_events(self, lines: list[dict], chat_id: str) -> list[dict]:
        tpath = _make_transcript(lines)
        code = textwrap.dedent(f"""\
            import sys, json, os
            os.environ.setdefault("NUNCHI_HOOK_AGENT_ID", "dalgos")
            import importlib.util
            spec = importlib.util.spec_from_file_location("hook", r"{str(_HOOK)}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            events = mod._parse_transcript(r"{tpath}", "{chat_id}")
            print(json.dumps(events))
        """)
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        os.unlink(tpath)
        return json.loads(result.stdout)

    def test_self_send_extraction(self):
        lines = [
            _assistant_reply_entry(chat_id="c1", text="hi there", tool_use_id="toolu_xyz"),
        ]
        events = self._extract_events(lines, "c1")
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["kind"], "self")
        self.assertEqual(ev["author_kind"], "self")
        self.assertEqual(ev["content"], "hi there")
        self.assertEqual(ev["message_id"], "toolu_xyz")

    def test_self_send_ignored_for_other_chat(self):
        lines = [
            _assistant_reply_entry(chat_id="other", text="not for this chat"),
        ]
        events = self._extract_events(lines, "c1")
        self.assertEqual(len(events), 0)


class TestTriggerAndHistoryAssembly(unittest.TestCase):
    """Trigger = most recent inbound; history = up to 10 events before it."""

    def _run_and_get_payload(self, lines: list[dict], chat_id: str) -> dict | None:
        """Run the hook with a captured stub that prints the payload it received."""
        tpath = _make_transcript(lines)
        # Stub that echoes back the payload it receives (for inspection)
        stub_code = textwrap.dedent("""\
            #!/usr/bin/env python3
            import sys, json
            payload = json.loads(sys.stdin.read())
            # Print SPEAK so hook allows
            print(json.dumps({
                "verdict": "SPEAK", "silent": False,
                "run_shape": "speak", "reasons": ["test"],
                "confidences": {}, "context_checked": [],
                "request_id": None, "classifier_model": None, "degraded": False,
            }))
            # Also dump payload to a side file
            with open(r"/tmp/__nunchi_test_payload.json", "w") as f:
                json.dump(payload, f)
            sys.exit(0)
        """)
        fd, stub_path = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, "w") as fh:
            fh.write(stub_code)

        wrapper_fd, wrapper_path = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(wrapper_fd, "w") as fh:
            fh.write(f"#!/bin/sh\n{sys.executable} {stub_path} \"$@\"\n")
        os.chmod(wrapper_path, 0o755)

        inp = _hook_input(chat_id=chat_id, transcript_path=tpath)
        _run_hook(inp, env_overrides={"NUNCHI_CHANNEL_BIN": wrapper_path})

        os.unlink(tpath)
        os.unlink(stub_path)
        os.unlink(wrapper_path)

        payload_path = pathlib.Path("/tmp/__nunchi_test_payload.json")
        if not payload_path.exists():
            return None
        result = json.loads(payload_path.read_text())
        payload_path.unlink()
        return result

    def test_trigger_is_most_recent_inbound(self):
        """Trigger = last inbound message in the transcript."""
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="first"),
            _user_channel_entry(chat_id="c1", message_id="m2", user="zoe", body="second"),
        ]
        payload = self._run_and_get_payload(lines, "c1")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["trigger"]["message_id"], "m2")
        self.assertEqual(payload["trigger"]["content"], "second")

    def test_history_excludes_trigger(self):
        """History contains only events before the trigger."""
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="first"),
            _user_channel_entry(chat_id="c1", message_id="m2", user="zoe", body="second (trigger)"),
        ]
        payload = self._run_and_get_payload(lines, "c1")
        self.assertIsNotNone(payload)
        # history should have only m1
        history = payload["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["message_id"], "m1")

    def test_history_includes_self_sends(self):
        """Self-sends in history are included."""
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hi"),
            _assistant_reply_entry(chat_id="c1", text="reply here", tool_use_id="toolu_1"),
            _user_channel_entry(chat_id="c1", message_id="m3", user="zoe", body="ok thanks"),
        ]
        payload = self._run_and_get_payload(lines, "c1")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["trigger"]["message_id"], "m3")
        history = payload["history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["message_id"], "m1")
        self.assertEqual(history[1]["author_kind"], "self")

    def test_other_chat_ignored_in_history(self):
        """Messages for other chat_ids don't appear in history or trigger."""
        lines = [
            _user_channel_entry(chat_id="other", message_id="x1", user="bob", body="other chat"),
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="target chat"),
        ]
        payload = self._run_and_get_payload(lines, "c1")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["trigger"]["message_id"], "m1")
        self.assertEqual(len(payload["history"]), 0)

    def test_history_capped_at_default_window(self):
        """History is capped at NUNCHI_HOOK_HISTORY_WINDOW (default 25) before the trigger."""
        lines = []
        for i in range(28):
            lines.append(
                _user_channel_entry(
                    chat_id="c1", message_id=f"m{i}", user="zoe", body=f"msg {i}"
                )
            )
        # 28 entries: trigger = m27, history capped at default 25 = m2..m26
        payload = self._run_and_get_payload(lines, "c1")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["trigger"]["message_id"], "m27")
        self.assertLessEqual(len(payload["history"]), 25)


    def test_history_window_env_var_limits_entries(self):
        """NUNCHI_HOOK_HISTORY_WINDOW env var limits the number of history entries sent."""
        import tempfile, textwrap, json as _json, os as _os, pathlib as _pathlib
        entries = []
        for i in range(15):
            entries.append(
                _user_channel_entry(
                    chat_id="c1", message_id=f"m{i}", user="zoe", body=f"msg {i}"
                )
            )
        # 15 entries: trigger=m14; with window=5, history <= 5 entries
        tpath = _make_transcript(entries)
        stub_code = textwrap.dedent("""\
            #!/usr/bin/env python3
            import sys, json
            payload = json.loads(sys.stdin.read())
            print(json.dumps({
                "verdict": "SPEAK", "silent": False, "run_shape": "speak",
                "reasons": ["test"], "confidences": {}, "context_checked": [],
                "request_id": None, "classifier_model": None, "degraded": False,
            }))
            with open("/tmp/__nunchi_window_test.json", "w") as f:
                json.dump(payload, f)
            sys.exit(0)
        """)
        fd, stub_path = tempfile.mkstemp(suffix=".py")
        with _os.fdopen(fd, "w") as fh:
            fh.write(stub_code)
        wrapper_fd, wrapper_path = tempfile.mkstemp(suffix=".sh")
        with _os.fdopen(wrapper_fd, "w") as fh:
            fh.write("#!/bin/sh\n" + sys.executable + " " + stub_path + ' "$@"\n')
        _os.chmod(wrapper_path, 0o755)
        inp = _hook_input(chat_id="c1", transcript_path=tpath)
        _run_hook(inp, env_overrides={
            "NUNCHI_CHANNEL_BIN": wrapper_path,
            "NUNCHI_HOOK_HISTORY_WINDOW": "5",
        })
        _os.unlink(tpath)
        _os.unlink(stub_path)
        _os.unlink(wrapper_path)
        payload_path = _pathlib.Path("/tmp/__nunchi_window_test.json")
        if payload_path.exists():
            payload = _json.loads(payload_path.read_text())
            self.assertLessEqual(len(payload.get("history", [])), 5)


class TestNoInboundAllowsUntriggered(unittest.TestCase):
    """When there is no inbound channel message, the hook must allow silently."""

    def test_no_inbound_in_empty_transcript(self):
        tpath = _make_transcript([])
        inp = _hook_input(transcript_path=tpath)
        rc, out, err = _run_hook(inp, env_overrides={"NUNCHI_CHANNEL_BIN": "/nonexistent"})
        os.unlink(tpath)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")  # No output

    def test_no_inbound_only_self_sends(self):
        """Only self-sends in transcript → allow-untriggered."""
        lines = [
            _assistant_reply_entry(chat_id="c1", text="agent-initiated"),
        ]
        tpath = _make_transcript(lines)
        inp = _hook_input(transcript_path=tpath)
        rc, out, err = _run_hook(inp, env_overrides={"NUNCHI_CHANNEL_BIN": "/nonexistent"})
        os.unlink(tpath)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")


class TestPassVerdict(unittest.TestCase):
    """PASS verdict → deny JSON with exact permissionDecision fields on stdout."""

    def test_pass_produces_deny_json(self):
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hey"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env(_make_pass_directive(["conversation is still active"]))
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        hso = parsed.get("hookSpecificOutput", {})
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertIn("permissionDecisionReason", hso)
        reason = hso["permissionDecisionReason"]
        self.assertIn("PASS", reason)
        self.assertIn("conversation is still active", reason)
        self.assertIn("Do not send this message", reason)

    def test_pass_reason_includes_first_reason(self):
        reasons = ["bot chatter ratio too high", "second reason", "third reason"]
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hi"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env(_make_pass_directive(reasons))
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        parsed = json.loads(out)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        # Only first reason should appear in the deny message
        self.assertIn("bot chatter ratio too high", reason)
        self.assertNotIn("second reason", reason)


class TestSpeakVerdict(unittest.TestCase):
    """Non-PASS verdicts → allow JSON on stdout."""

    def test_speak_produces_allow_json(self):
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="help"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env(_make_speak_directive())
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        hso = parsed["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "allow")

    def test_ack_produces_allow_json(self):
        directive = {
            "verdict": "ACK", "silent": False,
            "run_shape": "Emit one short presence signal.",
            "reasons": ["minimal ack warranted"], "confidences": {},
            "context_checked": [], "request_id": None,
            "classifier_model": None, "degraded": False,
        }
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="ack me"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env(directive)
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "allow")


class TestGateErrorFailPolicies(unittest.TestCase):
    """Gate binary failure → open allows, closed denies."""

    def test_fail_open_allows_on_gate_error(self):
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hey"),
        ]
        tpath = _make_transcript(lines)
        inp = _hook_input(transcript_path=tpath)
        rc, out, err = _run_hook(
            inp,
            env_overrides={
                "NUNCHI_CHANNEL_BIN": "/nonexistent-bin",
                "NUNCHI_HOOK_FAIL_POLICY": "open",
                "NUNCHI_HOOK_LOG": "/dev/null",
            },
        )
        os.unlink(tpath)
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_fail_closed_denies_on_gate_error(self):
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hey"),
        ]
        tpath = _make_transcript(lines)
        inp = _hook_input(transcript_path=tpath)
        rc, out, err = _run_hook(
            inp,
            env_overrides={
                "NUNCHI_CHANNEL_BIN": "/nonexistent-bin",
                "NUNCHI_HOOK_FAIL_POLICY": "closed",
                "NUNCHI_HOOK_LOG": "/dev/null",
            },
        )
        os.unlink(tpath)
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("permissionDecisionReason", parsed["hookSpecificOutput"])

    def test_fail_open_on_gate_binary_exit_nonzero(self):
        """Gate binary exits non-zero → apply fail policy."""
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hi"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env({}, exit_code=2)
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_FAIL_POLICY"] = "open"
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_fail_closed_on_gate_binary_exit_nonzero(self):
        """Gate binary exits non-zero → deny when fail_closed."""
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hi"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env({}, exit_code=2)
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_FAIL_POLICY"] = "closed"
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["hookSpecificOutput"]["permissionDecision"], "deny")


class TestOutputContractExactFields(unittest.TestCase):
    """Verify the exact hookSpecificOutput JSON structure matches the docs contract."""

    def test_deny_output_has_required_fields(self):
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hi"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env(_make_pass_directive())
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        parsed = json.loads(out)
        # Top-level key
        self.assertIn("hookSpecificOutput", parsed)
        hso = parsed["hookSpecificOutput"]
        # Required fields per docs
        self.assertIn("hookEventName", hso)
        self.assertIn("permissionDecision", hso)
        self.assertIn("permissionDecisionReason", hso)
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")

    def test_allow_output_has_required_fields(self):
        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hi"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env(_make_speak_directive())
        inp = _hook_input(transcript_path=tpath)
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        rc, out, err = _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        parsed = json.loads(out)
        self.assertIn("hookSpecificOutput", parsed)
        hso = parsed["hookSpecificOutput"]
        self.assertIn("hookEventName", hso)
        self.assertIn("permissionDecision", hso)
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "allow")


class TestReceiptLogging(unittest.TestCase):
    """Gate calls are logged to the receipts file."""

    def test_receipt_written_on_pass(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            log_path = tf.name

        lines = [
            _user_channel_entry(chat_id="c1", message_id="m1", user="zoe", body="hi"),
        ]
        tpath = _make_transcript(lines)
        stub_path, env = _gate_stub_env(_make_pass_directive())
        inp = _hook_input(transcript_path=tpath, session_id="sess-test", chat_id="c1")
        env["NUNCHI_HOOK_LOG"] = log_path
        _run_hook(inp, env_overrides=env)
        os.unlink(tpath)
        os.unlink(stub_path)

        with open(log_path) as fh:
            lines_logged = [json.loads(l) for l in fh if l.strip()]
        os.unlink(log_path)

        self.assertEqual(len(lines_logged), 1)
        rec = lines_logged[0]
        self.assertEqual(rec["session_id"], "sess-test")
        self.assertEqual(rec["chat_id"], "c1")
        self.assertIn("ts", rec)
        self.assertIn("action", rec)
        self.assertIn("elapsed_ms", rec)
        self.assertEqual(rec["verdict"], "PASS")
        self.assertTrue(rec["silent"])

    def test_receipt_written_on_allow_untriggered(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            log_path = tf.name

        tpath = _make_transcript([])  # empty transcript
        inp = _hook_input(transcript_path=tpath, session_id="sess-2", chat_id="c1")
        _run_hook(
            inp,
            env_overrides={
                "NUNCHI_CHANNEL_BIN": "/nonexistent",
                "NUNCHI_HOOK_LOG": log_path,
            },
        )
        os.unlink(tpath)

        with open(log_path) as fh:
            lines_logged = [json.loads(l) for l in fh if l.strip()]
        os.unlink(log_path)

        self.assertEqual(len(lines_logged), 1)
        rec = lines_logged[0]
        self.assertEqual(rec["action"], "allow-untriggered")
        self.assertIsNone(rec["trigger_message_id"])


class TestMissingTranscriptPath(unittest.TestCase):
    """Missing transcript_path → silent pass-through."""

    def test_no_transcript_path_exits_cleanly(self):
        inp = _hook_input(transcript_path="")
        rc, out, err = _run_hook(inp)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")


if __name__ == "__main__":
    unittest.main()
