"""Tests for the Discord reference adapter.

Pure-logic tests (author_kind mapping, history windowing, payload building,
receipt shaping) live in import-safe functions and run WITHOUT discord.py
installed.

Tests that require discord.py are decorated with
@unittest.skipUnless(DISCORD_AVAILABLE, "discord.py not installed") so they
show as skips in the test runner rather than silently passing or failing with
ImportError.

Run with:
    python3 -m unittest tests.test_discord_adapter
or from the worktree root:
    python3 -m unittest
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

# Ensure src is on the path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

# Check discord.py availability (no install required for pure tests)
try:
    import discord as _discord_lib
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

# These imports must work without discord.py installed
from nunchi.adapters.discord import (
    _append_to_history,
    _build_receipt,
    _resolve_author_kind,
    _write_receipt,
)
from nunchi.adapters.channel import ChannelGateResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


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


def _make_msg(content="hello", author="alice", author_kind="human", message_id="m1") -> dict:
    return {
        "content": content,
        "author": author,
        "author_kind": author_kind,
        "message_id": message_id,
        "timestamp": "1700000000",
    }


# --------------------------------------------------------------------------- #
# author_kind mapping (import-safe)
# --------------------------------------------------------------------------- #


class TestAuthorKindMapping(unittest.TestCase):
    """Pure function tests — no discord.py needed."""

    def test_self_returns_self(self):
        kind = _resolve_author_kind(123, 123, is_bot=True, bot_policy="all", peer_bot_ids=frozenset())
        self.assertEqual(kind, "self")

    def test_self_non_bot_returns_self(self):
        # Edge case: own user marked non-bot (shouldn't happen, but handle it)
        kind = _resolve_author_kind(123, 123, is_bot=False, bot_policy="all", peer_bot_ids=frozenset())
        self.assertEqual(kind, "self")

    def test_bot_all_policy_returns_peer_bot(self):
        kind = _resolve_author_kind(456, 123, is_bot=True, bot_policy="all", peer_bot_ids=frozenset())
        self.assertEqual(kind, "peer_bot")

    def test_bot_all_policy_ignores_peer_bot_ids(self):
        """In 'all' mode, peer_bot_ids is irrelevant — all bots are peer_bot."""
        kind = _resolve_author_kind(789, 123, is_bot=True, bot_policy="all", peer_bot_ids=frozenset({456}))
        self.assertEqual(kind, "peer_bot")

    def test_bot_allowlist_in_peer_list_returns_peer_bot(self):
        kind = _resolve_author_kind(456, 123, is_bot=True, bot_policy="allowlist", peer_bot_ids=frozenset({456}))
        self.assertEqual(kind, "peer_bot")

    def test_bot_allowlist_not_in_peer_list_returns_skip(self):
        kind = _resolve_author_kind(789, 123, is_bot=True, bot_policy="allowlist", peer_bot_ids=frozenset({456}))
        self.assertEqual(kind, "_skip")

    def test_bot_allowlist_empty_peer_list_returns_skip(self):
        kind = _resolve_author_kind(456, 123, is_bot=True, bot_policy="allowlist", peer_bot_ids=frozenset())
        self.assertEqual(kind, "_skip")

    def test_human_all_policy_returns_human(self):
        kind = _resolve_author_kind(999, 123, is_bot=False, bot_policy="all", peer_bot_ids=frozenset())
        self.assertEqual(kind, "human")

    def test_human_allowlist_policy_returns_human(self):
        kind = _resolve_author_kind(999, 123, is_bot=False, bot_policy="allowlist", peer_bot_ids=frozenset())
        self.assertEqual(kind, "human")


# --------------------------------------------------------------------------- #
# History windowing (import-safe)
# --------------------------------------------------------------------------- #


class TestHistoryWindowing(unittest.TestCase):
    """Pure function tests — no discord.py needed."""

    def test_append_to_empty(self):
        result = _append_to_history([], _make_msg(), history_len=10)
        self.assertEqual(len(result), 1)

    def test_append_preserves_order(self):
        h = [_make_msg("a", message_id="1"), _make_msg("b", message_id="2")]
        result = _append_to_history(h, _make_msg("c", message_id="3"), history_len=10)
        self.assertEqual([m["content"] for m in result], ["a", "b", "c"])

    def test_trim_to_history_len(self):
        h = [_make_msg(f"msg{i}", message_id=str(i)) for i in range(15)]
        result = _append_to_history(h, _make_msg("new", message_id="99"), history_len=5)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[-1]["content"], "new")

    def test_original_not_mutated(self):
        original = [_make_msg("a")]
        _ = _append_to_history(original, _make_msg("b"), history_len=10)
        self.assertEqual(len(original), 1, "original list must not be mutated")

    def test_trim_keeps_most_recent(self):
        h = [_make_msg(f"msg{i}", message_id=str(i)) for i in range(10)]
        result = _append_to_history(h, _make_msg("new", message_id="99"), history_len=3)
        contents = [m["content"] for m in result]
        # Should have the 3 most recent
        self.assertEqual(len(result), 3)
        self.assertIn("new", contents)


# --------------------------------------------------------------------------- #
# Payload building (import-safe)
# --------------------------------------------------------------------------- #


class TestPayloadBuilding(unittest.TestCase):
    """Test that trigger/history dicts have the right shape for the gate."""

    def test_trigger_fields_present(self):
        msg = _make_msg("hello world", author="alice", author_kind="human", message_id="m42")
        required = {"content", "author", "author_kind", "message_id"}
        self.assertTrue(required.issubset(msg.keys()))

    def test_author_kind_peer_bot_in_msg(self):
        msg = _make_msg(author_kind="peer_bot")
        self.assertEqual(msg["author_kind"], "peer_bot")

    def test_author_kind_self_in_msg(self):
        msg = _make_msg(author_kind="self")
        self.assertEqual(msg["author_kind"], "self")


# --------------------------------------------------------------------------- #
# Receipt shaping (import-safe)
# --------------------------------------------------------------------------- #


class TestReceiptShaping(unittest.TestCase):
    """Pure function tests — no discord.py needed."""

    def test_required_fields_present_on_speak(self):
        trigger = _make_msg()
        result = _make_gate_result("SPEAK")
        receipt = _build_receipt(12345, trigger, 3, result, "spoke", 50)
        required = {
            "ts", "room_id", "event_id", "author", "author_kind",
            "history_len", "verdict", "silent", "action", "elapsed_ms",
            "reasons", "confidences",
        }
        self.assertTrue(required.issubset(receipt.keys()))
        self.assertEqual(receipt["verdict"], "SPEAK")
        self.assertEqual(receipt["action"], "spoke")
        self.assertEqual(receipt["silent"], False)

    def test_required_fields_present_on_pass(self):
        trigger = _make_msg()
        result = _make_gate_result("PASS")
        receipt = _build_receipt(99999, trigger, 0, result, "silent", 10)
        self.assertEqual(receipt["verdict"], "PASS")
        self.assertEqual(receipt["silent"], True)
        self.assertEqual(receipt["action"], "silent")

    def test_room_id_is_string(self):
        receipt = _build_receipt(12345, _make_msg(), 0, _make_gate_result("PASS"), "silent", 5)
        self.assertIsInstance(receipt["room_id"], str)
        self.assertEqual(receipt["room_id"], "12345")

    def test_error_field_only_when_present(self):
        receipt_no_err = _build_receipt(1, _make_msg(), 0, None, "error", 0)
        self.assertNotIn("error", receipt_no_err)

        receipt_with_err = _build_receipt(1, _make_msg(), 0, None, "error", 0, error="oops")
        self.assertEqual(receipt_with_err["error"], "oops")

    def test_none_result_fields_are_none(self):
        receipt = _build_receipt(1, _make_msg(), 0, None, "error", 5)
        self.assertIsNone(receipt["verdict"])
        self.assertIsNone(receipt["silent"])
        self.assertEqual(receipt["reasons"], [])
        self.assertEqual(receipt["confidences"], {})

    def test_reasons_capped_at_three(self):
        result = ChannelGateResult(
            verdict="SPEAK",
            silent=False,
            run_shape="Produce one turn.",
            reasons=("r1", "r2", "r3", "r4", "r5"),
            confidences={},
            context_checked=(),
            request_id=None,
            classifier_model=None,
        )
        receipt = _build_receipt(1, _make_msg(), 0, result, "spoke", 0)
        self.assertEqual(len(receipt["reasons"]), 3)

    def test_history_len_reflects_snapshot(self):
        receipt = _build_receipt(1, _make_msg(), 7, _make_gate_result("ACK"), "spoke", 0)
        self.assertEqual(receipt["history_len"], 7)


# --------------------------------------------------------------------------- #
# _write_receipt (import-safe, touches filesystem)
# --------------------------------------------------------------------------- #


class TestWriteReceipt(unittest.TestCase):
    def test_creates_file_and_appends_json_lines(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = pathlib.Path(td) / "subdir" / "log.jsonl"
            r1 = _build_receipt(1, _make_msg(), 0, _make_gate_result("PASS"), "silent", 10)
            r2 = _build_receipt(1, _make_msg(), 1, _make_gate_result("SPEAK"), "spoke", 50)
            _write_receipt(log_path, r1)
            _write_receipt(log_path, r2)

            lines = log_path.read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["verdict"], "PASS")
            self.assertEqual(json.loads(lines[1])["verdict"], "SPEAK")

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = pathlib.Path(td) / "a" / "b" / "c" / "log.jsonl"
            _write_receipt(log_path, {"test": True})
            self.assertTrue(log_path.exists())


# --------------------------------------------------------------------------- #
# Send backstop (amplification-loops guard)
# --------------------------------------------------------------------------- #


class TestRateLimitedReceiptShape(unittest.TestCase):
    """rate-limited receipts keep the standard field shape (import-safe)."""

    def test_rate_limited_receipt_fields(self):
        trigger = _make_msg()
        result = _make_gate_result("SPEAK")
        receipt = _build_receipt(12345, trigger, 2, result, "rate-limited", 7)
        required = {
            "ts", "room_id", "event_id", "author", "author_kind",
            "history_len", "verdict", "silent", "action", "elapsed_ms",
            "reasons", "confidences",
        }
        self.assertTrue(required.issubset(receipt.keys()))
        self.assertEqual(receipt["action"], "rate-limited")
        self.assertEqual(receipt["verdict"], "SPEAK")


def _make_discord_stub(recorded_clients: list):
    """Build a minimal stand-in for the discord.py module.

    Only the surface main() touches is stubbed: Intents.default(), the Client
    base class (init/get_channel/run), and async channel.send recording.
    """
    import types

    stub = types.ModuleType("discord")

    class Intents:
        def __init__(self):
            self.message_content = False

        @classmethod
        def default(cls):
            return cls()

    class _FakeChannel:
        def __init__(self):
            self.sent: list[str] = []

        async def send(self, text):
            self.sent.append(text)

    class Client:
        def __init__(self, **kwargs):
            self._kwargs = kwargs
            self._fake_channels: dict[int, _FakeChannel] = {}
            recorded_clients.append(self)

        def get_channel(self, cid):
            return self._fake_channels.setdefault(cid, _FakeChannel())

        def run(self, token, log_handler=None):
            return None

    stub.Intents = Intents
    stub.Client = Client
    return stub


class TestSendBackstopWiring(unittest.TestCase):
    """Drive the real main()-built client offline via a stubbed discord module."""

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _build_client(self, extra_env: dict | None = None):
        from unittest.mock import patch
        import nunchi.adapters.discord as dmod

        clients: list = []
        stub = _make_discord_stub(clients)
        env = {
            "NUNCHI_DISCORD_TOKEN": "tok",
            "NUNCHI_DISCORD_CHANNELS": "111,222",
            "NUNCHI_DISCORD_LOG": str(self.tmp / "log.jsonl"),
            **(extra_env or {}),
        }
        with patch.dict(os.environ, env):
            with patch.dict(sys.modules, {"discord": stub}):
                rc = dmod.main([])
        self.assertEqual(rc, 0)
        client = clients[0]
        # Bypass on_ready (no gateway in the stub): wire identity + responder.
        client._own_user_id = 999
        client._agent_id = "test-agent"
        client._responder = lambda t, h, r: "reply!"
        return client

    def _gate(self, client, channel_id: int, verdict: str, msg_id: str):
        import asyncio
        from unittest.mock import patch

        trigger = _make_msg(message_id=msg_id)
        with patch("nunchi.adapters.discord.channel_gate", return_value=_make_gate_result(verdict)):
            asyncio.run(client._gate_and_respond(channel_id, trigger, []))

    def _read_receipts(self) -> list[dict]:
        log_path = self.tmp / "log.jsonl"
        if not log_path.exists():
            return []
        return [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]

    def test_backstop_trips_send_suppressed_receipt_rate_limited(self):
        client = self._build_client({"NUNCHI_DISCORD_BACKSTOP_MAX_SENDS": "1"})

        self._gate(client, 111, "SPEAK", "d1")
        self._gate(client, 111, "SPEAK", "d2")

        self.assertEqual(client.get_channel(111).sent, ["reply!"])
        receipts = self._read_receipts()
        self.assertEqual([r["action"] for r in receipts], ["spoke", "rate-limited"])
        self.assertEqual(receipts[1]["verdict"], "SPEAK")
        self.assertEqual(receipts[1]["room_id"], "111")

    def test_backstop_per_channel_isolation(self):
        client = self._build_client({"NUNCHI_DISCORD_BACKSTOP_MAX_SENDS": "1"})

        self._gate(client, 111, "SPEAK", "i1")
        self._gate(client, 111, "SPEAK", "i2")   # suppressed
        self._gate(client, 222, "SPEAK", "i3")   # other channel unaffected

        self.assertEqual(client.get_channel(111).sent, ["reply!"])
        self.assertEqual(client.get_channel(222).sent, ["reply!"])

    def test_pass_semantics_untouched_and_no_slot_consumed(self):
        client = self._build_client({"NUNCHI_DISCORD_BACKSTOP_MAX_SENDS": "1"})

        self._gate(client, 111, "PASS", "p1")    # silent, must not consume the slot
        self._gate(client, 111, "SPEAK", "p2")   # still sends

        self.assertEqual(client.get_channel(111).sent, ["reply!"])
        receipts = self._read_receipts()
        self.assertEqual([r["action"] for r in receipts], ["silent", "spoke"])

    def test_backstop_default_on(self):
        """Without env knobs, 5 sends pass and the 6th is rate-limited."""
        client = self._build_client()

        for i in range(6):
            self._gate(client, 111, "SPEAK", f"n{i}")

        self.assertEqual(len(client.get_channel(111).sent), 5)
        receipts = self._read_receipts()
        self.assertEqual([r["action"] for r in receipts][-1], "rate-limited")


class TestEmptySendGuard(unittest.TestCase):
    """Empty/whitespace responder output is suppressed, never sent.

    Drives the real main()-built client offline via a stubbed discord module
    (same harness as TestSendBackstopWiring).
    """

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _build_client(self, responder):
        from unittest.mock import patch
        import nunchi.adapters.discord as dmod

        clients: list = []
        stub = _make_discord_stub(clients)
        env = {
            "NUNCHI_DISCORD_TOKEN": "tok",
            "NUNCHI_DISCORD_CHANNELS": "111",
            "NUNCHI_DISCORD_LOG": str(self.tmp / "log.jsonl"),
        }
        with patch.dict(os.environ, env):
            with patch.dict(sys.modules, {"discord": stub}):
                rc = dmod.main([])
        self.assertEqual(rc, 0)
        client = clients[0]
        client._own_user_id = 999
        client._agent_id = "test-agent"
        client._responder = responder
        return client

    def _read_receipts(self) -> list[dict]:
        log_path = self.tmp / "log.jsonl"
        if not log_path.exists():
            return []
        return [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]

    def test_empty_reply_suppressed_receipt_empty_suppressed(self):
        import asyncio
        from unittest.mock import patch

        for empty_reply in ("", "   \n\t"):
            with self.subTest(reply=repr(empty_reply)):
                client = self._build_client(lambda t, h, r: empty_reply)
                trigger = _make_msg(message_id="e1")
                with patch("nunchi.adapters.discord.channel_gate", return_value=_make_gate_result("SPEAK")):
                    asyncio.run(client._gate_and_respond(111, trigger, []))

                self.assertEqual(client.get_channel(111).sent, [])
                receipts = self._read_receipts()
                self.assertEqual(receipts[-1]["action"], "empty-suppressed")

    def test_nonempty_reply_still_sends(self):
        import asyncio
        from unittest.mock import patch

        client = self._build_client(lambda t, h, r: "real reply")
        trigger = _make_msg(message_id="e2")
        with patch("nunchi.adapters.discord.channel_gate", return_value=_make_gate_result("SPEAK")):
            asyncio.run(client._gate_and_respond(111, trigger, []))

        self.assertEqual(client.get_channel(111).sent, ["real reply"])
        receipts = self._read_receipts()
        self.assertEqual(receipts[-1]["action"], "spoke")


# --------------------------------------------------------------------------- #
# discord.py-dependent tests (skipped when not installed)
# --------------------------------------------------------------------------- #


@unittest.skipUnless(DISCORD_AVAILABLE, "discord.py not installed")
class TestDiscordImports(unittest.TestCase):
    """Smoke tests for discord.py-dependent adapter code."""

    def test_module_importable(self):
        """Importing the adapter module does not raise even with discord.py present."""
        import importlib
        import nunchi.adapters.discord as d
        self.assertTrue(callable(d.main))

    def test_pure_functions_still_callable_with_discord_installed(self):
        """Pure functions work correctly regardless of discord.py availability."""
        kind = _resolve_author_kind(1, 2, is_bot=True, bot_policy="all", peer_bot_ids=frozenset())
        self.assertEqual(kind, "peer_bot")

    def test_intents_have_message_content(self):
        """Verify discord.Intents.default() can be extended with message_content."""
        import discord
        intents = discord.Intents.default()
        intents.message_content = True
        self.assertTrue(intents.message_content)


if __name__ == "__main__":
    unittest.main()
