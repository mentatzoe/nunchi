"""Tests for integrations/codex/nunchi_room_runner.py.

All tests are stdlib-only (no pytest) and fully offline: the MCP transport is
faked with an in-process http.server, and the gate/codex binaries are faked
with tiny shell scripts written to a temp directory. No network, no real
model calls, no real Codex.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import pathlib
import stat
import sys
import tempfile
import threading
import unittest

_RUNNER_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "integrations"
    / "codex"
    / "nunchi_room_runner.py"
)

_spec = importlib.util.spec_from_file_location("nunchi_room_runner", _RUNNER_PATH)
runner_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner_mod  # dataclasses resolve via sys.modules
_spec.loader.exec_module(runner_mod)
runner_mod.logger.disabled = True  # keep expected-failure noise out of test output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    *,
    channel_id: str = "c1",
    message_id: str = "m1",
    author_id: str = "u1",
    author_name: str = "zoe",
    author_is_bot: bool = False,
    content: str = "hello there",
    timestamp: str = "2026-07-07T00:00:00Z",
) -> dict:
    """One notifications/discord/message params object."""
    return {
        "guild_id": "g1",
        "channel_id": channel_id,
        "message_id": message_id,
        "author_id": author_id,
        "author_name": author_name,
        "author_is_bot": author_is_bot,
        "content": content,
        "timestamp": timestamp,
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


class _StubBinDir:
    """Tempdir holding stub gate + codex shell scripts and their capture files."""

    ARG_SEP = "\n<<<ARG>>>\n"

    def __init__(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="nunchi-codex-test-"))
        self.gate_stdin = self.dir / "gate_stdin.json"
        self.gate_directive = self.dir / "directive.json"
        self.gate_exit_file = self.dir / "gate_exit"
        self.codex_args = self.dir / "codex_args.txt"
        self.codex_exit_file = self.dir / "codex_exit"

        self.gate_bin = self.dir / "stub-nunchi-channel.sh"
        self.gate_bin.write_text(
            "#!/bin/sh\n"
            f'cat > "{self.gate_stdin}"\n'
            f'code=$(cat "{self.gate_exit_file}")\n'
            'if [ "$code" != "0" ]; then echo "stub gate error" >&2; exit "$code"; fi\n'
            f'cat "{self.gate_directive}"\n'
        )
        self.codex_bin = self.dir / "stub-codex.sh"
        self.codex_bin.write_text(
            "#!/bin/sh\n"
            f'printf \'%s\\n<<<ARG>>>\\n\' "$@" > "{self.codex_args}"\n'
            f'exit "$(cat "{self.codex_exit_file}")"\n'
        )
        for p in (self.gate_bin, self.codex_bin):
            p.chmod(p.stat().st_mode | stat.S_IXUSR)

        self.set_gate(_directive("SPEAK"))
        self.codex_exit_file.write_text("0")

    def set_gate(self, directive: dict, exit_code: int = 0) -> None:
        self.gate_directive.write_text(json.dumps(directive))
        self.gate_exit_file.write_text(str(exit_code))

    def gate_payload(self) -> dict:
        return json.loads(self.gate_stdin.read_text())

    def gate_called(self) -> bool:
        return self.gate_stdin.exists()

    def codex_called(self) -> bool:
        return self.codex_args.exists()

    def codex_argv(self) -> list[str]:
        raw = self.codex_args.read_text()
        parts = raw.split(self.ARG_SEP)
        return [p for p in parts[:-1]]  # trailing separator leaves one empty tail


def _make_runner(stubs: _StubBinDir, **overrides) -> "runner_mod.RoomRunner":
    defaults = dict(
        channel_bin=str(stubs.gate_bin),
        codex_bin=str(stubs.codex_bin),
        agent_id="dalgos",
        mention_id="<@42>",
        log_path=stubs.dir / "receipts.jsonl",
        gate_timeout=10.0,
        wake_timeout=10.0,
    )
    defaults.update(overrides)
    return runner_mod.RoomRunner(runner_mod.RunnerConfig(**defaults))


def _receipts(runner: "runner_mod.RoomRunner") -> list[dict]:
    path = runner.config.log_path
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# SSE line parser
# ---------------------------------------------------------------------------


class TestSseParser(unittest.TestCase):
    def test_multiple_events(self):
        lines = ['data: {"a": 1}', "", 'data: {"b": 2}', ""]
        self.assertEqual(
            list(runner_mod.iter_sse_data(lines)), ['{"a": 1}', '{"b": 2}']
        )

    def test_multi_line_data_joined_with_newline(self):
        lines = ["data: first", "data: second", ""]
        self.assertEqual(list(runner_mod.iter_sse_data(lines)), ["first\nsecond"])

    def test_ignores_non_data_fields_and_comments(self):
        lines = [
            ": keepalive comment",
            "event: message",
            "id: 7",
            "retry: 1000",
            "data: payload",
            "",
        ]
        self.assertEqual(list(runner_mod.iter_sse_data(lines)), ["payload"])

    def test_event_without_trailing_blank_line_still_emitted(self):
        self.assertEqual(list(runner_mod.iter_sse_data(["data: tail"])), ["tail"])

    def test_crlf_line_endings(self):
        lines = ["data: one\r\n", "\r\n", "data: two\r\n", "\r\n"]
        self.assertEqual(list(runner_mod.iter_sse_data(lines)), ["one", "two"])

    def test_data_without_space_after_colon(self):
        self.assertEqual(list(runner_mod.iter_sse_data(["data:tight", ""])), ["tight"])

    def test_blank_lines_without_data_emit_nothing(self):
        self.assertEqual(list(runner_mod.iter_sse_data(["", "", ": ping", ""])), [])


# ---------------------------------------------------------------------------
# Session handshake against a stub streamable-HTTP server
# ---------------------------------------------------------------------------

_SESSION_ID = "sess-test-123"


class _StubMcpHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 — silence test output
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.requests.append(("POST", body, {k.lower(): v for k, v in self.headers.items()}))
        if body.get("method") == "initialize":
            payload = json.dumps(
                {"jsonrpc": "2.0", "id": body.get("id"), "result": {"capabilities": {}}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("mcp-session-id", _SESSION_ID)
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_GET(self):
        self.server.requests.append(("GET", None, {k.lower(): v for k, v in self.headers.items()}))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(self.server.sse_body.encode())
        # HTTP/1.0 + no Content-Length: closing the connection ends the stream.


class TestHandshakeAndStream(unittest.TestCase):
    def setUp(self):
        self.server = http.server.HTTPServer(("127.0.0.1", 0), _StubMcpHandler)
        self.server.requests = []
        notif = {
            "jsonrpc": "2.0",
            "method": runner_mod.NOTIFICATION_METHOD,
            "params": _event(content="stream says hi"),
        }
        unrelated = {"jsonrpc": "2.0", "method": "notifications/other", "params": {}}
        self.server.sse_body = (
            ": ping\n\n"
            f"event: message\ndata: {json.dumps(unrelated)}\n\n"
            f"data: {json.dumps(notif)}\n\n"
            "data: not json at all\n\n"
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        # Trailing slash on purpose: the client must tolerate it.
        self.url = f"http://127.0.0.1:{port}/mcp/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_handshake_sequence_and_session_header(self):
        client = runner_mod.TransportClient(self.url)
        events = list(client.events())

        self.assertEqual(client.session_id, _SESSION_ID)
        kinds = [(method, body.get("method") if body else None) for method, body, _ in self.server.requests]
        self.assertEqual(
            kinds,
            [
                ("POST", "initialize"),
                ("POST", "notifications/initialized"),
                ("GET", None),
            ],
        )
        init_headers = self.server.requests[0][2]
        self.assertEqual(init_headers.get("content-type"), "application/json")
        self.assertIn("text/event-stream", init_headers.get("accept", ""))
        # notifications/initialized and the GET must carry the issued session id.
        self.assertEqual(self.server.requests[1][2].get("mcp-session-id"), _SESSION_ID)
        get_headers = self.server.requests[2][2]
        self.assertEqual(get_headers.get("mcp-session-id"), _SESSION_ID)
        self.assertEqual(get_headers.get("accept"), "text/event-stream")

        # Only the discord notification is yielded; other data lines are ignored.
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["content"], "stream says hi")

    def test_missing_session_header_raises(self):
        # A server that never issues mcp-session-id is a broken transport.
        original = _StubMcpHandler.do_POST

        def no_session(handler):
            length = int(handler.headers.get("Content-Length", "0"))
            handler.rfile.read(length)
            handler.send_response(200)
            handler.send_header("Content-Length", "2")
            handler.end_headers()
            handler.wfile.write(b"{}")

        _StubMcpHandler.do_POST = no_session
        try:
            client = runner_mod.TransportClient(self.url)
            with self.assertRaises(RuntimeError):
                list(client.events())
        finally:
            _StubMcpHandler.do_POST = original


# ---------------------------------------------------------------------------
# Verdict routing (stub gate + stub codex binaries)
# ---------------------------------------------------------------------------


class TestVerdictRouting(unittest.TestCase):
    def setUp(self):
        self.stubs = _StubBinDir()

    def test_speak_wakes_codex_with_full_prompt(self):
        self.stubs.set_gate(_directive("SPEAK", ["operator addressed the agent"]))
        runner = _make_runner(self.stubs)
        # Seed one PASS-suppressed history line first.
        self.stubs.set_gate(_directive("PASS"))
        runner.handle_notification(
            _event(message_id="m0", author_name="vigil", content="earlier context line")
        )
        self.stubs.set_gate(_directive("SPEAK", ["operator addressed the agent"]))
        action = runner.handle_notification(
            _event(message_id="m1", author_name="zoe", content="dalgos, status?")
        )

        self.assertEqual(action, "wake-ok")
        self.assertTrue(self.stubs.codex_called())
        argv = self.stubs.codex_argv()
        self.assertEqual(argv[0], "exec")
        self.assertIn("--skip-git-repo-check", argv)
        self.assertIn("--full-auto", argv)
        prompt = argv[-1]
        self.assertIn("verdict: SPEAK", prompt)
        self.assertIn("operator addressed the agent", prompt)
        self.assertIn("dalgos, status?", prompt)
        self.assertIn("channel_id: c1", prompt)
        self.assertIn("message_id: m1", prompt)
        self.assertIn("earlier context line", prompt)  # history window included
        self.assertIn("send_message", prompt)
        self.assertIn("reply_message", prompt)

        receipts = _receipts(runner)
        self.assertEqual(receipts[-1]["action"], "wake-ok")
        self.assertEqual(receipts[-1]["verdict"], "SPEAK")
        self.assertEqual(receipts[-1]["wake_exit"], 0)
        self.assertEqual(receipts[-1]["history_len"], 1)
        self.assertIn("confidences", receipts[-1])

    def test_ack_and_ask_wake_codex(self):
        for verdict in ("ACK", "ASK"):
            with self.subTest(verdict=verdict):
                stubs = _StubBinDir()
                stubs.set_gate(_directive(verdict))
                runner = _make_runner(stubs)
                action = runner.handle_notification(_event())
                self.assertEqual(action, "wake-ok")
                self.assertTrue(stubs.codex_called())
                prompt = stubs.codex_argv()[-1]
                self.assertIn(f"verdict: {verdict}", prompt)

    def test_pass_writes_receipt_and_never_wakes(self):
        self.stubs.set_gate(_directive("PASS", ["conversation is between two humans"]))
        runner = _make_runner(self.stubs)
        action = runner.handle_notification(_event())

        self.assertEqual(action, "pass-suppressed")
        self.assertTrue(self.stubs.gate_called())
        self.assertFalse(self.stubs.codex_called(), "PASS must not invoke codex")
        receipts = _receipts(runner)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["action"], "pass-suppressed")
        self.assertEqual(receipts[0]["verdict"], "PASS")
        self.assertEqual(receipts[0]["channel"], "c1")
        self.assertNotIn("wake_exit", receipts[0])

    def test_wake_error_recorded_with_exit_code(self):
        self.stubs.set_gate(_directive("SPEAK"))
        self.stubs.codex_exit_file.write_text("7")
        runner = _make_runner(self.stubs)
        action = runner.handle_notification(_event())

        self.assertEqual(action, "wake-error")
        receipts = _receipts(runner)
        self.assertEqual(receipts[-1]["action"], "wake-error")
        self.assertEqual(receipts[-1]["wake_exit"], 7)

    def test_gate_payload_shape_matches_channel_contract(self):
        self.stubs.set_gate(_directive("PASS"))
        runner = _make_runner(self.stubs)
        runner.handle_notification(_event(author_is_bot=True, author_name="vigil"))

        payload = self.stubs.gate_payload()
        self.assertEqual(payload["trigger"]["content"], "hello there")
        self.assertEqual(payload["trigger"]["author"], "vigil")
        self.assertEqual(payload["trigger"]["author_kind"], "peer_bot")
        self.assertEqual(payload["agent"], {"id": "dalgos", "mention_id": "<@42>"})
        self.assertEqual(payload["fail_policy"], "raise")
        self.assertEqual(payload["history"], [])


class TestGateFailurePolicy(unittest.TestCase):
    def setUp(self):
        self.stubs = _StubBinDir()

    def test_fail_closed_default_no_wake_on_gate_error(self):
        self.stubs.set_gate(_directive("SPEAK"), exit_code=3)
        runner = _make_runner(self.stubs)
        action = runner.handle_notification(_event())

        self.assertEqual(action, "no-wake-gate-error")
        self.assertFalse(self.stubs.codex_called(), "gate error must not wake (fail-closed)")
        receipts = _receipts(runner)
        self.assertEqual(receipts[-1]["action"], "no-wake-gate-error")
        self.assertIn("error", receipts[-1])
        self.assertIsNone(receipts[-1]["verdict"])

    def test_fail_closed_on_malformed_gate_output(self):
        self.stubs.gate_directive.write_text("this is not json")
        self.stubs.gate_exit_file.write_text("0")
        runner = _make_runner(self.stubs)
        action = runner.handle_notification(_event())

        self.assertEqual(action, "no-wake-gate-error")
        self.assertFalse(self.stubs.codex_called())

    def test_fail_closed_on_missing_gate_binary(self):
        runner = _make_runner(self.stubs, channel_bin=None)
        action = runner.handle_notification(_event())

        self.assertEqual(action, "no-wake-gate-error")
        self.assertFalse(self.stubs.codex_called())

    def test_fail_open_override_wakes_with_degraded_prompt(self):
        self.stubs.set_gate(_directive("SPEAK"), exit_code=3)
        runner = _make_runner(self.stubs, fail_policy="open")
        action = runner.handle_notification(_event())

        self.assertEqual(action, "wake-ok")
        self.assertTrue(self.stubs.codex_called())
        prompt = self.stubs.codex_argv()[-1]
        self.assertIn("DEGRADED", prompt)


# ---------------------------------------------------------------------------
# Rolling history: window + channel isolation
# ---------------------------------------------------------------------------


class TestRollingHistory(unittest.TestCase):
    def setUp(self):
        self.stubs = _StubBinDir()
        self.stubs.set_gate(_directive("PASS"))  # gate everything quietly

    def test_window_caps_history(self):
        runner = _make_runner(self.stubs, history_window=2)
        for i in range(1, 5):
            runner.handle_notification(
                _event(message_id=f"m{i}", content=f"message number {i}")
            )
        payload = self.stubs.gate_payload()  # payload of the 4th event
        contents = [h["content"] for h in payload["history"]]
        self.assertEqual(contents, ["message number 2", "message number 3"])
        self.assertEqual(payload["trigger"]["content"], "message number 4")

    def test_channels_are_isolated(self):
        runner = _make_runner(self.stubs, history_window=5)
        runner.handle_notification(_event(channel_id="c1", message_id="a1", content="c1 talk"))
        runner.handle_notification(_event(channel_id="c2", message_id="b1", content="c2 talk"))
        payload = self.stubs.gate_payload()  # payload of the c2 event
        self.assertEqual(payload["history"], [])
        self.assertEqual(payload["trigger"]["content"], "c2 talk")

    def test_trigger_joins_history_for_next_event(self):
        runner = _make_runner(self.stubs, history_window=5)
        runner.handle_notification(_event(message_id="m1", content="first"))
        runner.handle_notification(_event(message_id="m2", content="second"))
        payload = self.stubs.gate_payload()
        self.assertEqual([h["content"] for h in payload["history"]], ["first"])


# ---------------------------------------------------------------------------
# Skips: self and channel filter
# ---------------------------------------------------------------------------


class TestSkips(unittest.TestCase):
    def setUp(self):
        self.stubs = _StubBinDir()

    def test_self_author_skipped_without_gate_call(self):
        runner = _make_runner(self.stubs, self_id="999")
        action = runner.handle_notification(_event(author_id="999", content="my own send"))

        self.assertEqual(action, "skipped-self")
        self.assertFalse(self.stubs.gate_called(), "self events must not hit the gate")
        self.assertFalse(self.stubs.codex_called())
        receipts = _receipts(runner)
        self.assertEqual(receipts[0]["action"], "skipped-self")

    def test_self_message_still_enters_history_as_self(self):
        self.stubs.set_gate(_directive("PASS"))
        runner = _make_runner(self.stubs, self_id="999")
        runner.handle_notification(_event(author_id="999", message_id="s1", content="my send"))
        runner.handle_notification(_event(author_id="u1", message_id="m1", content="reply"))
        payload = self.stubs.gate_payload()
        self.assertEqual(len(payload["history"]), 1)
        self.assertEqual(payload["history"][0]["author_kind"], "self")
        self.assertEqual(payload["history"][0]["content"], "my send")

    def test_unwatched_channel_skipped_without_gate_call(self):
        runner = _make_runner(self.stubs, channels=frozenset({"c1"}))
        action = runner.handle_notification(_event(channel_id="c9"))

        self.assertEqual(action, "skipped-channel")
        self.assertFalse(self.stubs.gate_called())
        receipts = _receipts(runner)
        self.assertEqual(receipts[0]["action"], "skipped-channel")

    def test_empty_channel_filter_watches_all(self):
        self.stubs.set_gate(_directive("PASS"))
        runner = _make_runner(self.stubs, channels=frozenset())
        action = runner.handle_notification(_event(channel_id="c9"))
        self.assertEqual(action, "pass-suppressed")

    def test_empty_content_skipped(self):
        runner = _make_runner(self.stubs)
        action = runner.handle_notification(_event(content=""))
        self.assertEqual(action, "skipped-empty")
        self.assertFalse(self.stubs.gate_called())


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


class TestConfigFromEnv(unittest.TestCase):
    def test_defaults(self):
        cfg = runner_mod.RunnerConfig.from_env(environ={})
        self.assertEqual(cfg.transport_url, "http://127.0.0.1:3993/mcp")
        self.assertEqual(cfg.history_window, 20)
        self.assertEqual(cfg.fail_policy, "closed")
        self.assertEqual(cfg.codex_bin, "codex")
        self.assertEqual(cfg.wake_timeout, 300.0)
        self.assertEqual(cfg.channels, frozenset())

    def test_overrides_and_shell_split_args(self):
        env = {
            "NUNCHI_TRANSPORT_URL": "http://10.0.0.5:4000/mcp",
            "NUNCHI_RUNNER_CHANNELS": "c1, c2 ,",
            "NUNCHI_RUNNER_HISTORY_WINDOW": "7",
            "NUNCHI_RUNNER_FAIL_POLICY": "OPEN",
            "NUNCHI_RUNNER_CODEX_ARGS": "-c model_reasoning_effort=xhigh --json",
            "NUNCHI_RUNNER_SELF_ID": "42",
            "NUNCHI_CHANNEL_BIN": "/opt/bin/nunchi-channel",
        }
        cfg = runner_mod.RunnerConfig.from_env(environ=env)
        self.assertEqual(cfg.channels, frozenset({"c1", "c2"}))
        self.assertEqual(cfg.history_window, 7)
        self.assertEqual(cfg.fail_policy, "open")
        self.assertEqual(
            cfg.codex_extra_args, ("-c", "model_reasoning_effort=xhigh", "--json")
        )
        self.assertEqual(cfg.self_id, "42")
        self.assertEqual(cfg.channel_bin, "/opt/bin/nunchi-channel")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# 307 redirect following (mcp SDK mounts under a prefix; bare path redirects)
# ---------------------------------------------------------------------------


class _RedirectingStubHandler(_StubMcpHandler):
    """Serves only at the trailing-slash path; 307s the bare form like the SDK app."""

    def _redirect_if_bare(self) -> bool:
        if self.path.endswith("/"):
            return False
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self.send_response(307)
        self.send_header("Location", self.path + "/")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def do_POST(self):
        if not self._redirect_if_bare():
            super().do_POST()

    def do_GET(self):
        if not self._redirect_if_bare():
            super().do_GET()


class TestRedirectFollowing(unittest.TestCase):
    def setUp(self):
        self.server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectingStubHandler)
        self.server.requests = []
        notif = {
            "jsonrpc": "2.0",
            "method": runner_mod.NOTIFICATION_METHOD,
            "params": _event(content="redirected stream says hi"),
        }
        self.server.sse_body = f"data: {json.dumps(notif)}\n\n"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        # Bare path on purpose: the live transport 307s this to /mcp/.
        self.url = f"http://127.0.0.1:{port}/mcp"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_follows_307_and_pins_slash_url(self):
        client = runner_mod.TransportClient(self.url)
        events = list(client.events())

        self.assertEqual(client.session_id, _SESSION_ID)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["content"], "redirected stream says hi")
        # After the first hop the client pins the redirected URL: exactly one
        # redirect is served; every subsequent request lands on /mcp/ directly.
        served = [m for m, body, _ in self.server.requests]
        self.assertGreaterEqual(len(served), 3)  # initialize, initialized, GET
        self.assertTrue(client.url.endswith("/mcp/"))
