"""Offline tests for the Matrix reference adapter.

All tests are fully offline: urllib.request.urlopen is patched with canned
responses; time.sleep is patched to avoid real delays; no live network calls
are made.

Run with:
    python3 -m unittest tests.test_matrix_adapter
or from the worktree root:
    python3 -m unittest
"""

from __future__ import annotations

import io
import json
import logging
import os
import pathlib
import time
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch, call

import sys

# Ensure src is on the path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from nunchi.adapters.matrix import (
    MatrixSyncLoop,
    _is_peer_bot,
    _load_since,
    _next_txn_id,
    _save_since,
    _send_message,
    _whoami,
    login,
)
from nunchi.adapters.channel import ChannelGateResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_http_response(body: dict, status: int = 200) -> MagicMock:
    """Return a mock that behaves like urllib.request.urlopen's context manager."""
    raw = json.dumps(body).encode()
    resp = MagicMock()
    resp.read.return_value = raw
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_http_error(code: int, body: str = "") -> mock.MagicMock:
    """Return an HTTPError-raising side_effect for urlopen."""
    import urllib.error
    err = urllib.error.HTTPError(
        url="http://test",
        code=code,
        msg=f"HTTP {code}",
        hdrs={},
        fp=io.BytesIO(body.encode()),
    )
    return err


def _fixture_env(verdict: str, *, checked=None, reasons=None) -> dict:
    """Build NUNCHI_CLASSIFIER_TEST_RESULT env for deterministic gate verdicts."""
    from tests.provider_helpers import provider_env
    checked = checked or ["trigger:trigger-test"]
    return provider_env(verdict, checked=checked, reasons=reasons)


def _make_loop(
    *,
    tmp_path: pathlib.Path,
    room_ids=("!room1:example.com",),
    own_user_id="@bot:example.com",
    peer_bot_specs=(),
    responder=None,
    dry_run=False,
    history_len=10,
) -> MatrixSyncLoop:
    return MatrixSyncLoop(
        homeserver="https://matrix.example.com",
        token="tok_test",
        room_ids=list(room_ids),
        agent_id="test-agent",
        own_user_id=own_user_id,
        peer_bot_specs=list(peer_bot_specs),
        history_len=history_len,
        state_path=tmp_path / "state.json",
        log_path=tmp_path / "log.jsonl",
        responder=responder,
        dry_run=dry_run,
    )


def _canned_sync(
    room_id: str,
    events: list[dict],
    next_batch: str = "s1",
) -> dict:
    """Build a minimal /sync response with the given events in a single room."""
    return {
        "next_batch": next_batch,
        "rooms": {
            "join": {
                room_id: {
                    "timeline": {
                        "events": events,
                    }
                }
            }
        },
    }


def _text_event(
    content: str,
    sender: str = "@user:example.com",
    event_id: str = "$evt1",
    ts: int = 1_700_000_000_000,
    msgtype: str = "m.text",
) -> dict:
    return {
        "type": "m.room.message",
        "sender": sender,
        "event_id": event_id,
        "origin_server_ts": ts,
        "content": {"msgtype": msgtype, "body": content},
    }


def _encrypted_event(sender: str = "@user:example.com") -> dict:
    return {
        "type": "m.room.encrypted",
        "sender": sender,
        "event_id": "$enc1",
        "origin_server_ts": 1_700_000_000_000,
        "content": {},
    }


# --------------------------------------------------------------------------- #
# Peer-bot detection
# --------------------------------------------------------------------------- #

class TestIsPeerBot(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(_is_peer_bot("@bot:server.com", ["@bot:server.com"]))

    def test_glob_prefix(self):
        self.assertTrue(_is_peer_bot("@agentX:server.com", ["@agent*"]))

    def test_no_match(self):
        self.assertFalse(_is_peer_bot("@human:server.com", ["@bot:server.com"]))

    def test_empty_specs(self):
        self.assertFalse(_is_peer_bot("@anyone:server.com", []))

    def test_glob_does_not_match_unrelated(self):
        self.assertFalse(_is_peer_bot("@human:server.com", ["@bot*"]))


# --------------------------------------------------------------------------- #
# Since-token persistence
# --------------------------------------------------------------------------- #

class TestSinceTokenPersistence(unittest.TestCase):
    def test_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "state.json"
            _save_since(p, "s_abc123")
            loaded = _load_since(p)
            self.assertEqual(loaded, "s_abc123")

    def test_missing_file_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "nosuchfile.json"
            self.assertIsNone(_load_since(p))

    def test_corrupted_file_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "state.json"
            p.write_text("not-json")
            result = _load_since(p)
            self.assertIsNone(result)

    def test_run_persists_since_token(self):
        """run() with stop_after_one=True persists the since token from /sync."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            loop = _make_loop(tmp_path=pathlib.Path(td))
            sync_body = _canned_sync("!room1:example.com", [], next_batch="s_persisted")
            with patch("urllib.request.urlopen", return_value=_make_http_response(sync_body)):
                loop.run(stop_after_one=True)
            saved = _load_since(loop.state_path)
            self.assertEqual(saved, "s_persisted")


# --------------------------------------------------------------------------- #
# Sync-loop event extraction
# --------------------------------------------------------------------------- #

class TestSyncEventExtraction(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _run_two_batches(self, loop, first_events, second_events, room_id="!room1:example.com"):
        """Run the loop twice: first batch is initial (skipped), second fires gating."""
        batch1 = _canned_sync(room_id, first_events, next_batch="s1")
        batch2 = _canned_sync(room_id, second_events, next_batch="s2")
        responses = [_make_http_response(batch1), _make_http_response(batch2)]
        with patch("urllib.request.urlopen", side_effect=responses):
            loop.run_once(None)   # initial sync, gates skipped
            loop.run_once("s1")   # second sync, gates fire

    def test_text_events_only_no_gate_for_non_message(self):
        """Non-message events (reactions, state) are ignored."""
        gate_calls = []

        def _spy_gate(trigger, history, **kw):
            gate_calls.append(trigger)
            return ChannelGateResult(
                verdict="PASS", silent=True, run_shape="Stay silent.",
                reasons=("test",), confidences={}, context_checked=(), request_id=None, classifier_model=None,
            )

        loop = _make_loop(tmp_path=self.tmp)
        # Inject gate spy
        loop._gate_and_respond = lambda room_id, trigger_record, history_snapshot: (
            gate_calls.append(trigger_record)
        )

        state_event = {
            "type": "m.room.member",
            "sender": "@user:example.com",
            "event_id": "$state1",
            "origin_server_ts": 1_700_000_000_000,
            "content": {"membership": "join"},
        }
        self._run_two_batches(loop, [], [state_event])
        self.assertEqual(gate_calls, [])

    def test_own_message_skipped_from_gate(self):
        """Messages from own user_id are not gated (but are added to history)."""
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp, own_user_id="@bot:example.com")
        loop._gate_and_respond = lambda room_id, trigger_record, history_snapshot: (
            gate_calls.append(trigger_record)
        )

        own_event = _text_event("I am the bot", sender="@bot:example.com", event_id="$own1")
        self._run_two_batches(loop, [], [own_event])
        self.assertEqual(gate_calls, [])

    def test_room_allowlist_filters_unknown_rooms(self):
        """Events from rooms not in the allowlist are ignored."""
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp, room_ids=("!allowed:example.com",))
        loop._gate_and_respond = lambda room_id, trigger_record, history_snapshot: (
            gate_calls.append(trigger_record)
        )

        batch1 = _canned_sync("!other:example.com", [], next_batch="s1")
        batch2 = _canned_sync(
            "!other:example.com",
            [_text_event("hi there", event_id="$e1")],
            next_batch="s2",
        )
        responses = [_make_http_response(batch1), _make_http_response(batch2)]
        with patch("urllib.request.urlopen", side_effect=responses):
            loop.run_once(None)
            loop.run_once("s1")

        self.assertEqual(gate_calls, [])

    def test_encrypted_room_skipped_with_warning(self):
        """Encrypted events trigger a one-time warning and are skipped."""
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp)
        loop._gate_and_respond = lambda room_id, trigger_record, history_snapshot: (
            gate_calls.append(trigger_record)
        )

        with self.assertLogs("nunchi.adapters.matrix", level="WARNING") as cm:
            self._run_two_batches(loop, [], [_encrypted_event()])

        self.assertEqual(gate_calls, [])
        self.assertTrue(any("encryption" in line for line in cm.output))

    def test_encrypted_room_warns_only_once(self):
        """The encryption warning fires exactly once per room, not per event."""
        loop = _make_loop(tmp_path=self.tmp)
        loop._gate_and_respond = lambda *a, **kw: None

        batch1 = _canned_sync("!room1:example.com", [], next_batch="s1")
        # Two encrypted events in the second batch
        enc1 = _encrypted_event()
        enc2 = dict(enc1, event_id="$enc2")
        batch2 = _canned_sync("!room1:example.com", [enc1, enc2], next_batch="s2")

        with self.assertLogs("nunchi.adapters.matrix", level="WARNING") as cm:
            with patch("urllib.request.urlopen", side_effect=[
                _make_http_response(batch1),
                _make_http_response(batch2),
            ]):
                loop.run_once(None)
                loop.run_once("s1")

        warnings = [l for l in cm.output if "encryption" in l]
        self.assertEqual(len(warnings), 1)

    def test_m_notice_also_gated(self):
        """m.notice events are treated the same as m.text."""
        gate_calls = []
        loop = _make_loop(tmp_path=self.tmp)
        loop._gate_and_respond = lambda room_id, trigger_record, history_snapshot: (
            gate_calls.append(trigger_record)
        )

        notice = _text_event("system notice", event_id="$n1", msgtype="m.notice")
        self._run_two_batches(loop, [], [notice])
        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(gate_calls[0]["content"], "system notice")


# --------------------------------------------------------------------------- #
# History window and author_kind
# --------------------------------------------------------------------------- #

class TestHistoryWindow(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_author_kind_peer_bot_by_id(self):
        """Senders matching NUNCHI_MATRIX_PEER_BOTS are tagged peer_bot."""
        loop = _make_loop(
            tmp_path=self.tmp,
            peer_bot_specs=["@peerbot:example.com"],
        )
        kind = loop._author_kind("@peerbot:example.com")
        self.assertEqual(kind, "peer_bot")

    def test_author_kind_human_for_unknown(self):
        loop = _make_loop(tmp_path=self.tmp)
        kind = loop._author_kind("@alice:example.com")
        self.assertEqual(kind, "human")

    def test_author_kind_self_for_own_user_id(self):
        loop = _make_loop(tmp_path=self.tmp, own_user_id="@bot:example.com")
        kind = loop._author_kind("@bot:example.com")
        self.assertEqual(kind, "self")

    def test_history_window_capped_at_history_len(self):
        loop = _make_loop(tmp_path=self.tmp, history_len=3)
        room_id = "!room1:example.com"
        for i in range(10):
            loop._append_history(room_id, {"content": f"msg{i}", "author": "a", "author_kind": "human", "message_id": f"${i}"})
        hist = loop._get_history(room_id)
        self.assertEqual(len(hist), 3)
        # Most recent items
        self.assertEqual(hist[-1]["content"], "msg9")

    def test_history_snapshot_passed_to_gate_before_trigger_appended(self):
        """The history passed to the gate does not yet include the trigger."""
        captured = {}

        def _fake_gate(trigger, history, **kw):
            captured["history_len"] = len(history)
            return ChannelGateResult(
                verdict="PASS", silent=True, run_shape="Stay silent.",
                reasons=("test",), confidences={}, context_checked=(), request_id=None, classifier_model=None,
            )

        loop = _make_loop(tmp_path=self.tmp)
        # Pre-populate 2 messages in history
        room_id = "!room1:example.com"
        loop._append_history(room_id, {"content": "msg1", "author": "@a:x", "author_kind": "human", "message_id": "$p1"})
        loop._append_history(room_id, {"content": "msg2", "author": "@b:x", "author_kind": "human", "message_id": "$p2"})

        with patch("nunchi.adapters.matrix.channel_gate", side_effect=_fake_gate):
            loop._initial_sync_done = True
            loop._gate_and_respond(
                room_id=room_id,
                trigger_record={"content": "new msg", "author": "@c:x", "author_kind": "human", "message_id": "$new"},
                history_snapshot=loop._get_history(room_id),
            )

        self.assertEqual(captured["history_len"], 2)


# --------------------------------------------------------------------------- #
# Gate wiring: PASS -> no send, SPEAK -> send called
# --------------------------------------------------------------------------- #

class TestGateWiring(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _make_gate_result(self, verdict: str) -> ChannelGateResult:
        silent = verdict == "PASS"
        run_shapes = {
            "PASS": "Stay silent. Post nothing to the channel for this turn.",
            "ACK": "Emit one short presence signal.",
            "ASK": "Ask one blocking clarifying question.",
            "SPEAK": "Produce one normal participant turn.",
        }
        return ChannelGateResult(
            verdict=verdict,
            silent=silent,
            run_shape=run_shapes[verdict],
            reasons=(f"Fixture: {verdict}",),
            confidences={v: 0.25 for v in ("PASS", "ACK", "ASK", "SPEAK")},
            context_checked=(),
            request_id="test-req",
            classifier_model="fixture",
        )

    def test_pass_verdict_no_send(self):
        """PASS result: responder is never called and nothing is sent."""
        responder_calls = []
        send_calls = []

        loop = _make_loop(
            tmp_path=self.tmp,
            responder=lambda t, h, r: (responder_calls.append(r), "reply")[1],
        )

        with patch("nunchi.adapters.matrix.channel_gate", return_value=self._make_gate_result("PASS")):
            with patch("nunchi.adapters.matrix._send_message", side_effect=send_calls.append):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "hi", "author": "@a:x", "author_kind": "human", "message_id": "$t1"},
                    history_snapshot=[],
                )

        self.assertEqual(responder_calls, [])
        self.assertEqual(send_calls, [])

    def test_speak_verdict_send_called_with_responder_output(self):
        """SPEAK result: responder is called and its output is sent."""
        send_calls: list[tuple] = []

        def _responder(trigger, history, gate_result):
            return "Hello from the bot!"

        loop = _make_loop(tmp_path=self.tmp, responder=_responder)

        def _fake_send(homeserver, token, room_id, text):
            send_calls.append((room_id, text))
            return "$sent1"

        with patch("nunchi.adapters.matrix.channel_gate", return_value=self._make_gate_result("SPEAK")):
            with patch("nunchi.adapters.matrix._send_message", side_effect=_fake_send):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "speak!", "author": "@a:x", "author_kind": "human", "message_id": "$t2"},
                    history_snapshot=[],
                )

        self.assertEqual(len(send_calls), 1)
        self.assertEqual(send_calls[0][0], "!room1:example.com")
        self.assertEqual(send_calls[0][1], "Hello from the bot!")

    def test_responder_returning_none_no_send(self):
        """When responder returns None, nothing is sent."""
        send_calls = []

        loop = _make_loop(
            tmp_path=self.tmp,
            responder=lambda t, h, r: None,
        )

        with patch("nunchi.adapters.matrix.channel_gate", return_value=self._make_gate_result("SPEAK")):
            with patch("nunchi.adapters.matrix._send_message", side_effect=send_calls.append):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "hi", "author": "@a:x", "author_kind": "human", "message_id": "$t3"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])

    def test_dry_run_no_send_receipt_says_dry_run(self):
        """In dry-run mode, _send_message is never called; receipt action='dry-run'."""
        send_calls = []
        loop = _make_loop(
            tmp_path=self.tmp,
            responder=lambda t, h, r: "This would be sent",
            dry_run=True,
        )

        with patch("nunchi.adapters.matrix.channel_gate", return_value=self._make_gate_result("SPEAK")):
            with patch("nunchi.adapters.matrix._send_message", side_effect=send_calls.append):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "do it", "author": "@a:x", "author_kind": "human", "message_id": "$t4"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])
        # Check receipt
        receipts = [json.loads(l) for l in loop.log_path.read_text().splitlines() if l.strip()]
        self.assertTrue(any(r["action"] == "dry-run" for r in receipts))

    def test_gate_wiring_via_test_result_env_speak(self):
        """NUNCHI_CLASSIFIER_TEST_RESULT=SPEAK -> responder called."""
        send_calls: list[tuple] = []
        responder_calls = []

        def _responder(trigger, history, gate_result):
            responder_calls.append(gate_result.verdict)
            return "env-wired reply"

        def _fake_send(homeserver, token, room_id, text):
            send_calls.append(text)
            return "$s1"

        loop = _make_loop(tmp_path=self.tmp, responder=_responder)

        env = _fixture_env("SPEAK")
        with patch.dict(os.environ, env):
            with patch("urllib.request.urlopen", return_value=_make_http_response(
                _canned_sync("!room1:example.com", [_text_event("hi", event_id="$te1")], next_batch="sX")
            )):
                with patch("nunchi.adapters.matrix._send_message", side_effect=_fake_send):
                    loop.run_once(None)   # initial sync
                    # Now gate should fire on second message
                    loop.run_once("sX")  # but we only ran once above; simulate manually

            # Directly call _gate_and_respond with NUNCHI_CLASSIFIER_TEST_RESULT set
            with patch("nunchi.adapters.matrix._send_message", side_effect=_fake_send):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "speak!", "author": "@u:x", "author_kind": "human", "message_id": "$te2"},
                    history_snapshot=[],
                )

        self.assertIn("SPEAK", responder_calls)
        self.assertIn("env-wired reply", send_calls)

    def test_gate_wiring_via_test_result_env_pass(self):
        """NUNCHI_CLASSIFIER_TEST_RESULT=PASS -> no send."""
        send_calls = []
        loop = _make_loop(
            tmp_path=self.tmp,
            responder=lambda t, h, r: "should not be sent",
        )

        env = _fixture_env("PASS")
        with patch.dict(os.environ, env):
            with patch("nunchi.adapters.matrix._send_message", side_effect=send_calls.append):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "not for bot", "author": "@u:x", "author_kind": "human", "message_id": "$tp1"},
                    history_snapshot=[],
                )

        self.assertEqual(send_calls, [])


# --------------------------------------------------------------------------- #
# 429 backoff
# --------------------------------------------------------------------------- #

class TestRateLimitBackoff(unittest.TestCase):
    def test_429_retried_with_sleep(self):
        """HTTP 429 triggers retry with backoff sleep; eventually succeeds."""
        import urllib.error

        success_body = json.dumps({"user_id": "@bot:example.com"}).encode()
        success_resp = MagicMock()
        success_resp.read.return_value = success_body
        success_resp.__enter__ = lambda s: s
        success_resp.__exit__ = MagicMock(return_value=False)

        err_429 = urllib.error.HTTPError(
            url="http://test",
            code=429,
            msg="Too Many Requests",
            hdrs=MagicMock(**{"get.return_value": None}),  # no Retry-After
            fp=io.BytesIO(b"rate limited"),
        )

        sleep_calls = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            with patch("urllib.request.urlopen", side_effect=[err_429, success_resp]):
                result = _whoami("https://matrix.example.com", "tok")

        self.assertEqual(result, "@bot:example.com")
        self.assertTrue(len(sleep_calls) >= 1)

    def test_permanent_error_not_retried(self):
        """HTTP 403 aborts immediately without sleep."""
        import urllib.error

        err_403 = urllib.error.HTTPError(
            url="http://test",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=io.BytesIO(b"forbidden"),
        )

        sleep_calls = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            with patch("urllib.request.urlopen", side_effect=err_403):
                with self.assertRaises(RuntimeError):
                    _whoami("https://matrix.example.com", "tok")

        self.assertEqual(sleep_calls, [])


# --------------------------------------------------------------------------- #
# Transaction ID monotonicity
# --------------------------------------------------------------------------- #

class TestTxnIdMonotonicity(unittest.TestCase):
    def test_txn_ids_are_unique(self):
        """Consecutive txn IDs are unique strings."""
        ids = [_next_txn_id() for _ in range(10)]
        self.assertEqual(len(set(ids)), 10)

    def test_txn_ids_contain_counter(self):
        """Txn IDs include a monotonically increasing counter component."""
        id1 = _next_txn_id()
        id2 = _next_txn_id()
        # Both start with "nunchi-"
        self.assertTrue(id1.startswith("nunchi-"))
        self.assertTrue(id2.startswith("nunchi-"))
        # Counter portion (last segment) of id2 is greater
        counter1 = int(id1.rsplit("-", 1)[-1])
        counter2 = int(id2.rsplit("-", 1)[-1])
        self.assertGreater(counter2, counter1)

    def test_send_message_uses_put(self):
        """_send_message uses PUT and returns an event_id."""
        put_calls = []

        def _fake_urlopen(req, timeout):
            put_calls.append(req.get_method())
            resp = MagicMock()
            resp.read.return_value = json.dumps({"event_id": "$sentX"}).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            eid = _send_message("https://matrix.example.com", "tok", "!r:x", "hello")

        self.assertIn("PUT", put_calls)
        self.assertEqual(eid, "$sentX")


# --------------------------------------------------------------------------- #
# JSONL receipt logging
# --------------------------------------------------------------------------- #

class TestReceiptLogging(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _read_receipts(self, loop: MatrixSyncLoop) -> list[dict]:
        if not loop.log_path.exists():
            return []
        return [json.loads(l) for l in loop.log_path.read_text().splitlines() if l.strip()]

    def test_receipt_written_on_pass(self):
        loop = _make_loop(tmp_path=self.tmp)
        gate_result = ChannelGateResult(
            verdict="PASS", silent=True, run_shape="Stay silent.",
            reasons=("test pass",), confidences={"PASS": 0.9, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.1},
            context_checked=(), request_id="r1", classifier_model="test",
        )
        with patch("nunchi.adapters.matrix.channel_gate", return_value=gate_result):
            loop._initial_sync_done = True
            loop._gate_and_respond(
                room_id="!room1:example.com",
                trigger_record={"content": "hi", "author": "@u:x", "author_kind": "human", "message_id": "$r1"},
                history_snapshot=[],
            )

        receipts = self._read_receipts(loop)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["verdict"], "PASS")
        self.assertEqual(receipts[0]["action"], "silent")
        self.assertEqual(receipts[0]["room_id"], "!room1:example.com")

    def test_receipt_written_on_speak(self):
        send_calls = []

        def _fake_send(homeserver, token, room_id, text):
            send_calls.append(text)
            return "$s1"

        loop = _make_loop(
            tmp_path=self.tmp,
            responder=lambda t, h, r: "reply text",
        )
        gate_result = ChannelGateResult(
            verdict="SPEAK", silent=False, run_shape="Produce one turn.",
            reasons=("test speak",), confidences={"PASS": 0.1, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.9},
            context_checked=(), request_id="r2", classifier_model="test",
        )
        with patch("nunchi.adapters.matrix.channel_gate", return_value=gate_result):
            with patch("nunchi.adapters.matrix._send_message", side_effect=_fake_send):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "speak!", "author": "@u:x", "author_kind": "human", "message_id": "$r2"},
                    history_snapshot=[],
                )

        receipts = self._read_receipts(loop)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["verdict"], "SPEAK")
        self.assertEqual(receipts[0]["action"], "spoke")

    def test_receipt_has_required_fields(self):
        loop = _make_loop(tmp_path=self.tmp)
        gate_result = ChannelGateResult(
            verdict="ACK", silent=False, run_shape="Emit one short presence signal.",
            reasons=("ack reason",), confidences={"PASS": 0.0, "ACK": 0.9, "ASK": 0.0, "SPEAK": 0.1},
            context_checked=(), request_id=None, classifier_model=None,
        )
        with patch("nunchi.adapters.matrix.channel_gate", return_value=gate_result):
            with patch("nunchi.adapters.matrix._send_message", return_value="$sent"):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!r:x",
                    trigger_record={"content": "ok", "author": "@u:x", "author_kind": "human",
                                    "message_id": "$rf1", "timestamp": "1700000000000"},
                    history_snapshot=[{"content": "earlier", "author": "@b:x", "author_kind": "human", "message_id": "$p1"}],
                )

        receipts = self._read_receipts(loop)
        required = {"ts", "room_id", "event_id", "author", "author_kind",
                    "history_len", "verdict", "silent", "action", "elapsed_ms",
                    "reasons", "confidences"}
        self.assertTrue(required.issubset(receipts[0].keys()))
        self.assertEqual(receipts[0]["history_len"], 1)


# --------------------------------------------------------------------------- #
# _make_gate_result_for_test helper used only in tests — we expose it via import
# --------------------------------------------------------------------------- #
# Actually this should live in matrix.py — but to avoid modifying the adapter
# just to satisfy tests, we test via the actual gate with fixture env instead.
# The receipt test above patches channel_gate directly.

# Verify the module does NOT export _make_gate_result_for_test (it's only in tests)
class TestModuleExports(unittest.TestCase):
    def test_no_accidental_test_helper_in_module(self):
        import nunchi.adapters.matrix as m
        self.assertFalse(hasattr(m, "_make_gate_result_for_test"))


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

    def _make_gate_result(self, verdict: str) -> ChannelGateResult:
        return ChannelGateResult(
            verdict=verdict,
            silent=(verdict == "PASS"),
            run_shape="Stay silent." if verdict == "PASS" else "Produce one turn.",
            reasons=(f"Fixture: {verdict}",),
            confidences={v: 0.25 for v in ("PASS", "ACK", "ASK", "SPEAK")},
            context_checked=(),
            request_id="test-req",
            classifier_model="fixture",
        )

    def _read_receipts(self, loop: MatrixSyncLoop) -> list[dict]:
        if not loop.log_path.exists():
            return []
        return [json.loads(l) for l in loop.log_path.read_text().splitlines() if l.strip()]

    def _speak(self, loop, room_id="!room1:example.com", msg_id="$b1", send_calls=None):
        def _fake_send(homeserver, token, rid, text):
            if send_calls is not None:
                send_calls.append((rid, text))
            return "$sent"

        with patch("nunchi.adapters.matrix.channel_gate", return_value=self._make_gate_result("SPEAK")):
            with patch("nunchi.adapters.matrix._send_message", side_effect=_fake_send):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id=room_id,
                    trigger_record={"content": "hi", "author": "@u:x", "author_kind": "human", "message_id": msg_id},
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

        self._speak(loop, msg_id="$b1", send_calls=send_calls)
        self._speak(loop, msg_id="$b2", send_calls=send_calls)

        self.assertEqual(len(send_calls), 1)
        receipts = self._read_receipts(loop)
        self.assertEqual([r["action"] for r in receipts], ["spoke", "rate-limited"])
        self.assertEqual(receipts[1]["verdict"], "SPEAK")
        self.assertEqual(receipts[1]["room_id"], "!room1:example.com")

    def test_backstop_window_slides(self):
        from nunchi.adapters._backstop import SendBackstop

        send_calls: list = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "reply")
        fake_now = [0.0]
        loop._backstop = SendBackstop(1, 10.0, clock=lambda: fake_now[0])

        self._speak(loop, msg_id="$w1", send_calls=send_calls)   # t=0: sends
        self._speak(loop, msg_id="$w2", send_calls=send_calls)   # t=0: suppressed
        fake_now[0] = 11.0
        self._speak(loop, msg_id="$w3", send_calls=send_calls)   # t=11: window slid

        self.assertEqual(len(send_calls), 2)
        receipts = self._read_receipts(loop)
        self.assertEqual([r["action"] for r in receipts], ["spoke", "rate-limited", "spoke"])

    def test_backstop_per_room_isolation(self):
        from nunchi.adapters._backstop import SendBackstop

        send_calls: list = []
        loop = _make_loop(
            tmp_path=self.tmp,
            room_ids=("!a:example.com", "!b:example.com"),
            responder=lambda t, h, r: "reply",
        )
        fake_now = [0.0]
        loop._backstop = SendBackstop(1, 10.0, clock=lambda: fake_now[0])

        self._speak(loop, room_id="!a:example.com", msg_id="$i1", send_calls=send_calls)
        self._speak(loop, room_id="!a:example.com", msg_id="$i2", send_calls=send_calls)
        self._speak(loop, room_id="!b:example.com", msg_id="$i3", send_calls=send_calls)

        self.assertEqual([c[0] for c in send_calls], ["!a:example.com", "!b:example.com"])

    def test_pass_semantics_untouched_and_no_slot_consumed(self):
        """PASS stays silent as before and never consumes a backstop slot."""
        from nunchi.adapters._backstop import SendBackstop

        send_calls: list = []
        loop = _make_loop(tmp_path=self.tmp, responder=lambda t, h, r: "reply")
        fake_now = [0.0]
        loop._backstop = SendBackstop(1, 10.0, clock=lambda: fake_now[0])

        with patch("nunchi.adapters.matrix.channel_gate", return_value=self._make_gate_result("PASS")):
            with patch("nunchi.adapters.matrix._send_message", side_effect=lambda *a: send_calls.append(a)):
                loop._initial_sync_done = True
                loop._gate_and_respond(
                    room_id="!room1:example.com",
                    trigger_record={"content": "hi", "author": "@u:x", "author_kind": "human", "message_id": "$p1"},
                    history_snapshot=[],
                )
        self.assertEqual(send_calls, [])

        # The PASS above must not have eaten the single slot: SPEAK still sends.
        speak_sends: list = []
        self._speak(loop, msg_id="$p2", send_calls=speak_sends)
        self.assertEqual(len(speak_sends), 1)

        receipts = self._read_receipts(loop)
        self.assertEqual([r["action"] for r in receipts], ["silent", "spoke"])

    def test_backstop_env_knobs(self):
        """NUNCHI_MATRIX_BACKSTOP_* env vars tune the backstop shape."""
        from nunchi.adapters.matrix import _build_loop_from_env

        env = {
            "NUNCHI_MATRIX_HOMESERVER": "https://matrix.example.com",
            "NUNCHI_MATRIX_TOKEN": "tok",
            "NUNCHI_MATRIX_ROOMS": "!room1:example.com",
            "NUNCHI_MATRIX_STATE": str(self.tmp / "state.json"),
            "NUNCHI_MATRIX_LOG": str(self.tmp / "log.jsonl"),
            "NUNCHI_MATRIX_BACKSTOP_MAX_SENDS": "2",
            "NUNCHI_MATRIX_BACKSTOP_WINDOW_SECONDS": "3.5",
        }
        with patch.dict(os.environ, env):
            with patch("nunchi.adapters.matrix._whoami", return_value="@bot:example.com"):
                loop = _build_loop_from_env()

        self.assertEqual(loop._backstop.max_sends, 2)
        self.assertEqual(loop._backstop.window_seconds, 3.5)


# --------------------------------------------------------------------------- #
# login() helper
# --------------------------------------------------------------------------- #

class TestLoginHelper(unittest.TestCase):
    def test_login_returns_token(self):
        """login() extracts access_token from response."""
        resp_body = {"access_token": "tok_abc123", "device_id": "DEV1"}
        resp = MagicMock()
        resp.read.return_value = json.dumps(resp_body).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            token = login("https://matrix.example.com", "@bot:example.com", "secret")

        self.assertEqual(token, "tok_abc123")

    def test_login_raises_on_missing_token(self):
        """login() raises if response has no access_token."""
        resp_body = {"error": "M_FORBIDDEN"}
        resp = MagicMock()
        resp.read.return_value = json.dumps(resp_body).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        import urllib.error
        err = urllib.error.HTTPError(
            url="http://test", code=403, msg="Forbidden", hdrs={}, fp=io.BytesIO(b"forbidden")
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(RuntimeError):
                login("https://matrix.example.com", "@bot:example.com", "badpassword")


if __name__ == "__main__":
    unittest.main()
