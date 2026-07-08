"""Offline tests for the Telegram reference adapter.

All tests are fully offline: urllib.request.urlopen is patched with canned
responses; time.sleep is patched to avoid real delays; no live network calls
are made.

Run with:
    python3 -m unittest tests.test_telegram_adapter
or from the worktree root:
    python3 -m unittest
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Ensure src is on the path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import urllib.error

from nunchi.adapters.telegram import (
    TelegramPollLoop,
    _load_offset,
    _save_offset,
    _send_message,
    _tg_call,
)
from nunchi.adapters.channel import ChannelGateResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_tg_response(result, *, ok: bool = True) -> MagicMock:
    """Return a mock that behaves like urllib.request.urlopen's context manager."""
    body = json.dumps({"ok": ok, "result": result}).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = 200
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_http_error(code: int, body_dict: dict | None = None) -> urllib.error.HTTPError:
    body_str = json.dumps(body_dict or {}).encode()
    hdrs = MagicMock()
    hdrs.get.return_value = None
    return urllib.error.HTTPError(
        url="http://test",
        code=code,
        msg=f"HTTP {code}",
        hdrs=hdrs,
        fp=io.BytesIO(body_str),
    )


def _fixture_env(verdict: str, *, checked=None, reasons=None) -> dict:
    """Build NUNCHI_CLASSIFIER_TEST_RESULT env for deterministic gate verdicts."""
    from tests.provider_helpers import provider_env
    checked = checked or ["trigger:trigger-test"]
    return provider_env(verdict, checked=checked, reasons=reasons)


def _make_loop(
    *,
    tmp_path: pathlib.Path,
    chat_ids=(100,),
    own_user_id=999,
    own_username="testbot",
    responder=None,
    dry_run=False,
    history_len=10,
) -> TelegramPollLoop:
    return TelegramPollLoop(
        token="TEST_TOKEN",
        chat_ids=list(chat_ids),
        agent_id="test-agent",
        own_user_id=own_user_id,
        own_username=own_username,
        history_len=history_len,
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "log.jsonl",
        responder=responder,
        dry_run=dry_run,
    )


def _make_gate_result(verdict: str) -> ChannelGateResult:
    run_shapes = {
        "PASS": "Stay silent. Post nothing to the channel for this turn.",
        "ACK": "Emit one short presence signal.",
        "ASK": "Ask one blocking clarifying question.",
        "SPEAK": "Produce one normal participant turn.",
    }
    return ChannelGateResult(
        verdict=verdict,
        silent=(verdict == "PASS"),
        run_shape=run_shapes[verdict],
        reasons=(f"Fixture: {verdict}",),
        confidences={v: 0.25 for v in ("PASS", "ACK", "ASK", "SPEAK")},
        context_checked=(),
        request_id="test-req",
        classifier_model="fixture",
    )


def _make_message_update(
    text: str,
    chat_id: int = 100,
    from_id: int = 42,
    is_bot: bool = False,
    username: str = "alice",
    message_id: int = 1,
    date: int = 1_700_000_000,
    update_id: int = 5001,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {
                "id": from_id,
                "is_bot": is_bot,
                "first_name": "Alice",
                "username": username,
            },
            "chat": {"id": chat_id, "type": "group", "title": "Test"},
            "date": date,
            "text": text,
        },
    }


def _read_receipts(loop: TelegramPollLoop) -> list[dict]:
    if not loop.log_path.exists():
        return []
    return [json.loads(l) for l in loop.log_path.read_text().splitlines() if l.strip()]


# --------------------------------------------------------------------------- #
# author_kind
# --------------------------------------------------------------------------- #


class TestAuthorKind(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.loop = _make_loop(tmp_path=pathlib.Path(self._td.name), own_user_id=999)

    def tearDown(self):
        self._td.cleanup()

    def test_own_user_returns_self(self):
        kind = self.loop._author_kind({"id": 999, "is_bot": True})
        self.assertEqual(kind, "self")

    def test_is_bot_returns_peer_bot(self):
        kind = self.loop._author_kind({"id": 123, "is_bot": True})
        self.assertEqual(kind, "peer_bot")

    def test_regular_user_returns_human(self):
        kind = self.loop._author_kind({"id": 42, "is_bot": False})
        self.assertEqual(kind, "human")

    def test_none_from_returns_human(self):
        kind = self.loop._author_kind(None)
        self.assertEqual(kind, "human")


# --------------------------------------------------------------------------- #
# Chat allowlist
# --------------------------------------------------------------------------- #


class TestChatAllowlist(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_unknown_chat_not_gated(self):
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp, chat_ids=[100])
        loop._gate_and_respond = lambda **kw: gate_calls.append(kw)

        update = _make_message_update("hello", chat_id=999, update_id=1)
        loop._process_update(update)

        self.assertEqual(gate_calls, [])

    def test_known_chat_is_gated(self):
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp, chat_ids=[100])
        loop._gate_and_respond = lambda chat_id, trigger_record, history_snapshot: gate_calls.append(chat_id)

        update = _make_message_update("hello", chat_id=100, update_id=1)
        loop._process_update(update)

        self.assertEqual(gate_calls, [100])


# --------------------------------------------------------------------------- #
# Own-message skip
# --------------------------------------------------------------------------- #


class TestOwnMessageSkip(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_own_message_not_gated_but_added_to_history(self):
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp, own_user_id=999)
        loop._gate_and_respond = lambda **kw: gate_calls.append(kw)

        own_update = _make_message_update("I am the bot", chat_id=100, from_id=999, update_id=1)
        loop._process_update(own_update)

        self.assertEqual(gate_calls, [])
        # But it should be in history
        hist = loop._get_history(100)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["author_kind"], "self")

    def test_non_own_message_is_gated(self):
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp, own_user_id=999)
        loop._gate_and_respond = lambda chat_id, trigger_record, history_snapshot: gate_calls.append(trigger_record)

        update = _make_message_update("hi bot", chat_id=100, from_id=42, update_id=2)
        loop._process_update(update)

        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(gate_calls[0]["content"], "hi bot")


# --------------------------------------------------------------------------- #
# Event extraction
# --------------------------------------------------------------------------- #


class TestEventExtraction(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_trigger_fields(self):
        """_process_update correctly extracts trigger fields from a message."""
        captured = {}

        def fake_gate(chat_id, trigger_record, history_snapshot):
            captured.update(trigger_record)

        loop = _make_loop(tmp_path=self.tmp)
        loop._gate_and_respond = fake_gate

        update = _make_message_update(
            "hello world",
            chat_id=100,
            from_id=42,
            username="alice",
            message_id=789,
            date=1_700_000_000,
            update_id=1,
        )
        loop._process_update(update)

        self.assertEqual(captured["content"], "hello world")
        self.assertEqual(captured["author"], "alice")
        self.assertEqual(captured["author_kind"], "human")
        self.assertEqual(captured["message_id"], "789")

    def test_empty_text_ignored(self):
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp)
        loop._gate_and_respond = lambda **kw: gate_calls.append(kw)

        update = _make_message_update("   ", chat_id=100, update_id=1)
        loop._process_update(update)

        self.assertEqual(gate_calls, [])

    def test_non_message_update_ignored(self):
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp)
        loop._gate_and_respond = lambda **kw: gate_calls.append(kw)

        # Update with no "message" key
        loop._process_update({"update_id": 1, "edited_message": {"text": "edited"}})
        self.assertEqual(gate_calls, [])

    def test_history_snapshot_before_trigger(self):
        """Gate receives history snapshot that does NOT include the trigger."""
        captured = {}

        def fake_gate(chat_id, trigger_record, history_snapshot):
            captured["history_len"] = len(history_snapshot)

        loop = _make_loop(tmp_path=self.tmp)
        # Pre-populate 2 messages
        loop._append_history(100, {"content": "a", "author": "x", "author_kind": "human", "message_id": "1"})
        loop._append_history(100, {"content": "b", "author": "y", "author_kind": "human", "message_id": "2"})
        loop._gate_and_respond = fake_gate

        update = _make_message_update("hi", chat_id=100, update_id=5)
        loop._process_update(update)

        self.assertEqual(captured["history_len"], 2)


# --------------------------------------------------------------------------- #
# PASS verdict -> no send
# --------------------------------------------------------------------------- #


class TestPassNoSend(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_pass_no_send_and_receipt_silent(self):
        send_calls = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "should not send")

        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("PASS")):
            with patch("nunchi.adapters.telegram._send_message", side_effect=send_calls.append):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={"content": "hi", "author": "alice", "author_kind": "human", "message_id": "m1"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])
        receipts = _read_receipts(loop)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["verdict"], "PASS")
        self.assertEqual(receipts[0]["action"], "silent")

    def test_pass_via_test_env(self):
        send_calls = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "text")

        env = _fixture_env("PASS")
        with patch.dict(os.environ, env):
            with patch("nunchi.adapters.telegram._send_message", side_effect=send_calls.append):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={"content": "boring", "author": "alice", "author_kind": "human", "message_id": "m2"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])


# --------------------------------------------------------------------------- #
# SPEAK/ACK/ASK verdict -> send called
# --------------------------------------------------------------------------- #


class TestSpeakSends(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_speak_calls_send_message(self):
        send_calls: list[tuple] = []

        def _fake_send(token, chat_id, text):
            send_calls.append((chat_id, text))
            return 1001  # fake message_id

        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "Hello!")

        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("SPEAK")):
            with patch("nunchi.adapters.telegram._send_message", side_effect=_fake_send):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={"content": "speak!", "author": "alice", "author_kind": "human", "message_id": "m3"},
                    history_snapshot=[],
                )

        self.assertEqual(len(send_calls), 1)
        self.assertEqual(send_calls[0][0], 100)
        self.assertEqual(send_calls[0][1], "Hello!")

        receipts = _read_receipts(loop)
        self.assertEqual(receipts[0]["action"], "spoke")

    def test_responder_none_no_send(self):
        send_calls = []
        loop = _make_loop(tmp_path=self.tmp, responder=None)

        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("SPEAK")):
            with patch("nunchi.adapters.telegram._send_message", side_effect=send_calls.append):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={"content": "hi", "author": "alice", "author_kind": "human", "message_id": "m4"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])

    def test_responder_returns_none_no_send(self):
        send_calls = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: None)

        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("SPEAK")):
            with patch("nunchi.adapters.telegram._send_message", side_effect=send_calls.append):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={"content": "hi", "author": "alice", "author_kind": "human", "message_id": "m5"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])
        receipts = _read_receipts(loop)
        self.assertEqual(receipts[0]["action"], "responder-declined")

    def test_speak_via_test_env(self):
        send_calls: list[str] = []

        def _fake_send(token, chat_id, text):
            send_calls.append(text)
            return 1002

        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "env-wired reply")

        env = _fixture_env("SPEAK")
        with patch.dict(os.environ, env):
            with patch("nunchi.adapters.telegram._send_message", side_effect=_fake_send):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={"content": "speak!", "author": "alice", "author_kind": "human", "message_id": "m6"},
                    history_snapshot=[],
                )

        self.assertIn("env-wired reply", send_calls)


# --------------------------------------------------------------------------- #
# Dry-run
# --------------------------------------------------------------------------- #


class TestDryRun(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_dry_run_no_send_receipt_dry_run(self):
        send_calls = []
        loop = _make_loop(tmp_path=self.tmp, dry_run=True, responder=lambda t, h, r: "would be sent")

        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("SPEAK")):
            with patch("nunchi.adapters.telegram._send_message", side_effect=send_calls.append):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={"content": "hi", "author": "alice", "author_kind": "human", "message_id": "m7"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])
        receipts = _read_receipts(loop)
        self.assertTrue(any(r["action"] == "dry-run" for r in receipts))


# --------------------------------------------------------------------------- #
# Offset persistence
# --------------------------------------------------------------------------- #


class TestOffsetPersistence(unittest.TestCase):
    def test_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "state.json"
            _save_offset(p, 12345)
            loaded = _load_offset(p)
            self.assertEqual(loaded, 12345)

    def test_missing_file_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "nosuchfile.json"
            self.assertIsNone(_load_offset(p))

    def test_corrupted_file_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "state.json"
            p.write_text("not-json")
            self.assertIsNone(_load_offset(p))

    def test_poll_once_persists_offset(self):
        """After poll_once, the returned next_offset is the update_id+1."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            loop = _make_loop(tmp_path=pathlib.Path(td))
            updates = [
                _make_message_update("hi", chat_id=100, update_id=42),
            ]
            with patch("nunchi.adapters.telegram._get_updates", return_value=updates):
                with patch("nunchi.adapters.telegram.channel_gate",
                           return_value=_make_gate_result("PASS")):
                    next_offset = loop.poll_once(None)

            self.assertEqual(next_offset, 43)

    def test_run_stop_after_one_saves_offset(self):
        """run(stop_after_one=True) persists the offset after a single batch."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            loop = _make_loop(tmp_path=pathlib.Path(td))
            updates = [_make_message_update("hi", chat_id=100, update_id=77)]
            with patch("nunchi.adapters.telegram._get_updates", return_value=updates):
                with patch("nunchi.adapters.telegram.channel_gate",
                           return_value=_make_gate_result("PASS")):
                    loop.run(stop_after_one=True)

            saved = _load_offset(loop.state_path)
            self.assertEqual(saved, 78)


# --------------------------------------------------------------------------- #
# 429 retry_after
# --------------------------------------------------------------------------- #


class TestRateLimitBackoff(unittest.TestCase):
    def test_429_retry_after_from_json_body_honored(self):
        """HTTP 429 with retry_after in JSON body -> time.sleep called with that value."""
        retry_body = json.dumps(
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 7}}
        ).encode()
        hdrs = MagicMock()
        hdrs.get.return_value = None  # no Retry-After header
        err_429 = urllib.error.HTTPError(
            url="http://test",
            code=429,
            msg="Too Many Requests",
            hdrs=hdrs,
            fp=io.BytesIO(retry_body),
        )

        success_resp = _make_tg_response({"id": 12345, "username": "testbot"})

        sleep_calls: list[float] = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            with patch("urllib.request.urlopen", side_effect=[err_429, success_resp]):
                result = _tg_call("TOKEN", "getMe", timeout=5.0)

        self.assertEqual(result["id"], 12345)
        self.assertIn(7.0, sleep_calls)

    def test_429_retry_after_from_header_honored(self):
        """HTTP 429 with Retry-After header -> sleep called with that value."""
        retry_body = json.dumps({"ok": False, "error_code": 429}).encode()
        hdrs = MagicMock()
        hdrs.get.return_value = "3"  # Retry-After: 3
        err_429 = urllib.error.HTTPError(
            url="http://test",
            code=429,
            msg="Too Many Requests",
            hdrs=hdrs,
            fp=io.BytesIO(retry_body),
        )

        success_resp = _make_tg_response({"id": 99})

        sleep_calls: list[float] = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            with patch("urllib.request.urlopen", side_effect=[err_429, success_resp]):
                result = _tg_call("TOKEN", "getMe", timeout=5.0)

        self.assertEqual(result["id"], 99)
        self.assertIn(3.0, sleep_calls)

    def test_permanent_error_not_retried(self):
        """HTTP 403 aborts immediately without sleep."""
        err_403 = _make_http_error(403)
        sleep_calls = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            with patch("urllib.request.urlopen", side_effect=err_403):
                with self.assertRaises(RuntimeError):
                    _tg_call("TOKEN", "getMe", timeout=5.0)

        self.assertEqual(sleep_calls, [])

    def test_network_error_retried_with_backoff(self):
        """Network errors trigger retry with exponential backoff."""
        success_resp = _make_tg_response({"id": 55})

        sleep_calls: list[float] = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            with patch(
                "urllib.request.urlopen",
                side_effect=[
                    OSError("connection refused"),
                    success_resp,
                ],
            ):
                result = _tg_call("TOKEN", "getMe", timeout=5.0, retry_base_delay=0.5)

        self.assertEqual(result["id"], 55)
        self.assertTrue(len(sleep_calls) >= 1)


# --------------------------------------------------------------------------- #
# Receipt shape
# --------------------------------------------------------------------------- #


class TestReceiptShape(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_receipt_has_required_fields(self):
        loop = _make_loop(tmp_path=self.tmp)
        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("ACK")):
            with patch("nunchi.adapters.telegram._send_message", return_value=99):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={
                        "content": "hi",
                        "author": "alice",
                        "author_kind": "human",
                        "message_id": "m10",
                        "timestamp": "1700000000",
                    },
                    history_snapshot=[
                        {"content": "prev", "author": "bob", "author_kind": "human", "message_id": "m9"}
                    ],
                )

        receipts = _read_receipts(loop)
        required = {
            "ts", "room_id", "event_id", "author", "author_kind",
            "history_len", "verdict", "silent", "action", "elapsed_ms",
            "reasons", "confidences",
        }
        self.assertTrue(required.issubset(receipts[0].keys()))
        self.assertEqual(receipts[0]["room_id"], "100")
        self.assertEqual(receipts[0]["history_len"], 1)


# --------------------------------------------------------------------------- #
# Send backstop (amplification-loops guard)
# --------------------------------------------------------------------------- #


class TestSendBackstopWiring(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _speak(self, loop, chat_id=100, msg_id="m1", send_calls=None):
        def _fake_send(token, cid, text):
            if send_calls is not None:
                send_calls.append((cid, text))
            return 999

        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("SPEAK")):
            with patch("nunchi.adapters.telegram._send_message", side_effect=_fake_send):
                loop._gate_and_respond(
                    chat_id=chat_id,
                    trigger_record={
                        "content": "hi",
                        "author": "alice",
                        "author_kind": "human",
                        "message_id": msg_id,
                        "timestamp": "1700000000",
                    },
                    history_snapshot=[],
                )

    def test_backstop_default_on(self):
        """A loop built without backstop knobs has the guard active (5/10s)."""
        loop = _make_loop(tmp_path=self.tmp)
        self.assertEqual(loop._backstop.max_sends, 5)
        self.assertEqual(loop._backstop.window_seconds, 10.0)

    def test_backstop_trips_send_suppressed_receipt_rate_limited(self):
        from nunchi.adapters._backstop import SendBackstop

        send_calls: list = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "reply")
        fake_now = [0.0]
        loop._backstop = SendBackstop(1, 10.0, clock=lambda: fake_now[0])

        self._speak(loop, msg_id="b1", send_calls=send_calls)
        self._speak(loop, msg_id="b2", send_calls=send_calls)

        self.assertEqual(len(send_calls), 1)
        receipts = _read_receipts(loop)
        self.assertEqual([r["action"] for r in receipts], ["spoke", "rate-limited"])
        self.assertEqual(receipts[1]["verdict"], "SPEAK")
        self.assertEqual(receipts[1]["room_id"], "100")

    def test_backstop_window_slides(self):
        from nunchi.adapters._backstop import SendBackstop

        send_calls: list = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "reply")
        fake_now = [0.0]
        loop._backstop = SendBackstop(1, 10.0, clock=lambda: fake_now[0])

        self._speak(loop, msg_id="w1", send_calls=send_calls)   # t=0: sends
        self._speak(loop, msg_id="w2", send_calls=send_calls)   # t=0: suppressed
        fake_now[0] = 11.0
        self._speak(loop, msg_id="w3", send_calls=send_calls)   # t=11: window slid

        self.assertEqual(len(send_calls), 2)
        receipts = _read_receipts(loop)
        self.assertEqual([r["action"] for r in receipts], ["spoke", "rate-limited", "spoke"])

    def test_backstop_per_chat_isolation(self):
        from nunchi.adapters._backstop import SendBackstop

        send_calls: list = []
        loop = _make_loop(tmp_path=self.tmp, chat_ids=(100, 200), responder=lambda t, h, r: "reply")
        fake_now = [0.0]
        loop._backstop = SendBackstop(1, 10.0, clock=lambda: fake_now[0])

        self._speak(loop, chat_id=100, msg_id="i1", send_calls=send_calls)
        self._speak(loop, chat_id=100, msg_id="i2", send_calls=send_calls)
        self._speak(loop, chat_id=200, msg_id="i3", send_calls=send_calls)

        self.assertEqual([c[0] for c in send_calls], [100, 200])

    def test_pass_semantics_untouched_and_no_slot_consumed(self):
        """PASS stays silent as before and never consumes a backstop slot."""
        from nunchi.adapters._backstop import SendBackstop

        send_calls: list = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "reply")
        fake_now = [0.0]
        loop._backstop = SendBackstop(1, 10.0, clock=lambda: fake_now[0])

        with patch("nunchi.adapters.telegram.channel_gate", return_value=_make_gate_result("PASS")):
            with patch("nunchi.adapters.telegram._send_message", side_effect=lambda *a: send_calls.append(a)):
                loop._gate_and_respond(
                    chat_id=100,
                    trigger_record={
                        "content": "hi",
                        "author": "alice",
                        "author_kind": "human",
                        "message_id": "p1",
                        "timestamp": "1700000000",
                    },
                    history_snapshot=[],
                )
        self.assertEqual(send_calls, [])

        # The PASS above must not have eaten the single slot: SPEAK still sends.
        speak_sends: list = []
        self._speak(loop, msg_id="p2", send_calls=speak_sends)
        self.assertEqual(len(speak_sends), 1)

        receipts = _read_receipts(loop)
        self.assertEqual([r["action"] for r in receipts], ["silent", "spoke"])

    def test_backstop_env_knobs(self):
        """NUNCHI_TELEGRAM_BACKSTOP_* env vars tune the backstop shape."""
        from nunchi.adapters.telegram import _build_loop_from_env

        env = {
            "NUNCHI_TELEGRAM_TOKEN": "tok",
            "NUNCHI_TELEGRAM_CHATS": "100",
            "NUNCHI_TELEGRAM_STATE": str(self.tmp / "state.json"),
            "NUNCHI_TELEGRAM_LOG": str(self.tmp / "log.jsonl"),
            "NUNCHI_TELEGRAM_BACKSTOP_MAX_SENDS": "2",
            "NUNCHI_TELEGRAM_BACKSTOP_WINDOW_SECONDS": "3.5",
        }
        with patch.dict(os.environ, env):
            with patch(
                "nunchi.adapters.telegram._get_me",
                return_value={"id": 999, "username": "testbot"},
            ):
                loop = _build_loop_from_env()

        self.assertEqual(loop._backstop.max_sends, 2)
        self.assertEqual(loop._backstop.window_seconds, 3.5)


if __name__ == "__main__":
    unittest.main()
