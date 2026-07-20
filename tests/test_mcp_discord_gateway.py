"""Tests for the nunchi-mcp-discord gateway layer (sans-IO, offline).

Covers the RFC 6455 frame codec, the gateway protocol state machine
(identify, resume after simulated disconnect, heartbeat bookkeeping, close
code classification), and the load-bearing dispatch filter: bot-authored
MESSAGE_CREATEs are delivered, self-authored ones are dropped.

Everything here runs without network access and without any third-party
package installed.

Run with:
    python3 -m unittest tests.test_mcp_discord_gateway
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import unittest

# Ensure src is on the path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from nunchi.mcp_discord import ws as wslib
from nunchi.mcp_discord.events import filter_message_create
from nunchi.mcp_discord.gateway import (
    INTENTS,
    CloseAndReconnect,
    Dispatch,
    GatewayProtocol,
    SendPayload,
    classify_close,
    close_hint,
)
from nunchi.mcp_discord.runner import GatewayFatalError, GatewayRunner

TOKEN = "test-token-000"


def _hello(interval_ms: int = 45000) -> dict:
    return {"op": 10, "d": {"heartbeat_interval": interval_ms}}


def _ready(session_id: str = "sess-1", own_id: str = "999", seq: int = 1) -> dict:
    return {
        "op": 0,
        "t": "READY",
        "s": seq,
        "d": {
            "session_id": session_id,
            "resume_gateway_url": "wss://resume.example.gg",
            "user": {"id": own_id, "username": "our-bot", "bot": True},
        },
    }


def _message_create(
    author_id: str,
    *,
    bot: bool = True,
    content: str = "ping",
    seq: int = 2,
    **overrides,
) -> dict:
    data = {
        "id": "111222333",
        "channel_id": "444555666",
        "guild_id": "777888999",
        "content": content,
        "timestamp": "2026-07-06T10:00:00.000000+00:00",
        "author": {"id": author_id, "username": "peer-bot", "bot": bot},
        "embeds": [],
        "attachments": [],
    }
    data.update(overrides)
    return {"op": 0, "t": "MESSAGE_CREATE", "s": seq, "d": data}


# --------------------------------------------------------------------------- #
# WebSocket frame codec
# --------------------------------------------------------------------------- #


class TestWSCodec(unittest.TestCase):
    def test_accept_key_rfc_vector(self):
        # RFC 6455 section 1.3 sample handshake
        self.assertEqual(
            wslib.accept_key("dGhlIHNhbXBsZSBub25jZQ=="),
            "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
        )

    def test_masked_roundtrip_small(self):
        raw = wslib.encode_frame(wslib.OP_TEXT, b"hello", mask_key=b"\x01\x02\x03\x04")
        frames = wslib.FrameDecoder().feed(raw)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].opcode, wslib.OP_TEXT)
        self.assertEqual(frames[0].payload, b"hello")
        self.assertTrue(frames[0].fin)

    def test_mask_actually_masks_wire_bytes(self):
        raw = wslib.encode_frame(wslib.OP_TEXT, b"secret", mask_key=b"\xaa\xbb\xcc\xdd")
        self.assertNotIn(b"secret", raw)

    def test_unmasked_roundtrip_lengths(self):
        # Server frames are unmasked; exercise 7-bit, 16-bit, 64-bit lengths
        for size in (125, 300, 70000):
            payload = bytes(i % 251 for i in range(size))
            raw = wslib.encode_frame(wslib.OP_BINARY, payload, mask=False)
            frames = wslib.FrameDecoder().feed(raw)
            self.assertEqual(len(frames), 1, f"size={size}")
            self.assertEqual(frames[0].payload, payload, f"size={size}")

    def test_incremental_feed(self):
        raw = wslib.encode_frame(wslib.OP_TEXT, b"chunked payload", mask=False)
        decoder = wslib.FrameDecoder()
        frames = []
        for i in range(len(raw)):
            frames.extend(decoder.feed(raw[i : i + 1]))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, b"chunked payload")

    def test_two_frames_in_one_feed(self):
        raw = wslib.encode_frame(wslib.OP_TEXT, b"one", mask=False) + wslib.encode_frame(
            wslib.OP_TEXT, b"two", mask=False
        )
        frames = wslib.FrameDecoder().feed(raw)
        self.assertEqual([f.payload for f in frames], [b"one", b"two"])

    def test_fragmented_message_assembly(self):
        assembler = wslib.MessageAssembler()
        first = wslib.Frame(fin=False, opcode=wslib.OP_TEXT, payload=b"hel")
        cont = wslib.Frame(fin=True, opcode=wslib.OP_CONT, payload=b"lo")
        self.assertIsNone(assembler.feed(first))
        self.assertEqual(assembler.feed(cont), (wslib.OP_TEXT, b"hello"))

    def test_control_frame_interleaved_with_fragments(self):
        assembler = wslib.MessageAssembler()
        self.assertIsNone(
            assembler.feed(wslib.Frame(fin=False, opcode=wslib.OP_TEXT, payload=b"a"))
        )
        ping = assembler.feed(wslib.Frame(fin=True, opcode=wslib.OP_PING, payload=b"hb"))
        self.assertEqual(ping, (wslib.OP_PING, b"hb"))
        done = assembler.feed(wslib.Frame(fin=True, opcode=wslib.OP_CONT, payload=b"b"))
        self.assertEqual(done, (wslib.OP_TEXT, b"ab"))

    def test_parse_close(self):
        import struct

        payload = struct.pack(">H", 4004) + b"auth"
        self.assertEqual(wslib.parse_close(payload), (4004, "auth"))
        self.assertEqual(wslib.parse_close(b""), (None, ""))


# --------------------------------------------------------------------------- #
# Gateway protocol: identify / heartbeat
# --------------------------------------------------------------------------- #


class TestGatewayIdentify(unittest.TestCase):
    def test_hello_triggers_identify_with_intents(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        actions = proto.handle(_hello())
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SendPayload)
        payload = actions[0].payload
        self.assertEqual(payload["op"], 2)
        self.assertEqual(payload["d"]["token"], TOKEN)
        # GUILD_MESSAGES | GUILD_MESSAGE_REACTIONS | MESSAGE_CONTENT
        self.assertEqual(
            payload["d"]["intents"],
            (1 << 9) | (1 << 10) | (1 << 15),
        )
        self.assertEqual(payload["d"]["intents"], INTENTS)

    def test_ready_captures_session_state(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello())
        proto.handle(_ready(session_id="s-42", own_id="1234", seq=7))
        self.assertEqual(proto.session_id, "s-42")
        self.assertEqual(proto.own_user_id, "1234")
        self.assertEqual(proto.seq, 7)
        self.assertTrue(proto.ready)
        self.assertTrue(proto.can_resume)

    def test_server_heartbeat_request_answered_immediately(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello())
        proto.handle(_ready(seq=3))
        actions = proto.handle({"op": 1})
        self.assertEqual(actions, [SendPayload({"op": 1, "d": 3})])

    def test_heartbeat_ack_bookkeeping(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello())
        self.assertFalse(proto.heartbeat_overdue())
        proto.mark_heartbeat_sent()
        self.assertTrue(proto.heartbeat_overdue())
        proto.handle({"op": 11})
        self.assertFalse(proto.heartbeat_overdue())

    def test_hello_sets_heartbeat_interval(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello(interval_ms=41250))
        self.assertEqual(proto.heartbeat_interval_ms, 41250)


# --------------------------------------------------------------------------- #
# Gateway protocol: resume after simulated disconnect
# --------------------------------------------------------------------------- #


class TestGatewayResume(unittest.TestCase):
    def test_resume_after_simulated_disconnect(self):
        proto = GatewayProtocol(TOKEN)
        # First connection: identify, become ready, observe some traffic
        proto.on_connection_open()
        first = proto.handle(_hello())
        self.assertEqual(first[0].payload["op"], 2)
        proto.handle(_ready(session_id="sess-abc", seq=1))
        proto.handle(_message_create("777", seq=5))

        # Simulated disconnect (network drop); 1006-style close is resumable
        self.assertEqual(classify_close(1006), "resume")
        self.assertTrue(proto.can_resume)
        self.assertEqual(proto.connect_url(), "wss://resume.example.gg/?v=10&encoding=json")

        # Second connection: HELLO must trigger RESUME, not IDENTIFY
        proto.on_connection_open()
        actions = proto.handle(_hello())
        self.assertEqual(len(actions), 1)
        payload = actions[0].payload
        self.assertEqual(payload["op"], 6)
        self.assertEqual(payload["d"]["session_id"], "sess-abc")
        self.assertEqual(payload["d"]["seq"], 5)
        self.assertEqual(payload["d"]["token"], TOKEN)

        # RESUMED restores ready state
        proto.handle({"op": 0, "t": "RESUMED", "s": 6, "d": {}})
        self.assertTrue(proto.ready)

    def test_invalid_session_not_resumable_forces_identify(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello())
        proto.handle(_ready(session_id="sess-abc", seq=4))

        actions = proto.handle({"op": 9, "d": False})
        self.assertEqual(actions, [CloseAndReconnect(resume=False)])
        self.assertFalse(proto.can_resume)

        proto.on_connection_open()
        actions = proto.handle(_hello())
        self.assertEqual(actions[0].payload["op"], 2)  # fresh IDENTIFY

    def test_invalid_session_resumable_keeps_session(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello())
        proto.handle(_ready(session_id="sess-abc", seq=4))
        actions = proto.handle({"op": 9, "d": True})
        self.assertEqual(actions, [CloseAndReconnect(resume=True)])
        self.assertTrue(proto.can_resume)

    def test_reconnect_op_requests_resume(self):
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello())
        actions = proto.handle({"op": 7, "d": None})
        self.assertEqual(actions, [CloseAndReconnect(resume=True)])

    def test_close_code_classification(self):
        self.assertEqual(classify_close(4004), "fatal")  # bad token
        self.assertEqual(classify_close(4013), "fatal")  # invalid intents
        self.assertEqual(classify_close(4014), "fatal")  # disallowed intents
        self.assertEqual(classify_close(4007), "identify")  # bad seq
        self.assertEqual(classify_close(4009), "identify")  # session timeout
        self.assertEqual(classify_close(1006), "resume")
        self.assertEqual(classify_close(None), "resume")

    def test_close_hints_mention_remediation(self):
        self.assertIn("NUNCHI_DISCORD_TOKEN", close_hint(4004))
        self.assertIn("MESSAGE CONTENT INTENT", close_hint(4014))
        self.assertIsNone(close_hint(1000))


# --------------------------------------------------------------------------- #
# THE LOAD-BEARING TEST: bot-authored delivered, self-authored dropped
# --------------------------------------------------------------------------- #


class TestSelfDropFilter(unittest.TestCase):
    OWN_ID = "999"

    def test_bot_authored_message_is_delivered_not_filtered(self):
        data = _message_create("777", bot=True)["d"]
        event = filter_message_create(data, self.OWN_ID)
        self.assertIsNotNone(event)
        self.assertTrue(event.author_is_bot)
        self.assertEqual(event.author_id, "777")
        self.assertEqual(event.content, "ping")

    def test_self_authored_message_is_dropped(self):
        data = _message_create(self.OWN_ID, bot=True)["d"]
        self.assertIsNone(filter_message_create(data, self.OWN_ID))

    def test_human_authored_message_is_delivered(self):
        data = _message_create("555", bot=False)["d"]
        event = filter_message_create(data, self.OWN_ID)
        self.assertIsNotNone(event)
        self.assertFalse(event.author_is_bot)

    def test_other_bot_delivered_end_to_end_through_protocol(self):
        """Dispatch path: READY then MESSAGE_CREATEs through the protocol."""
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        proto.handle(_hello())
        proto.handle(_ready(own_id=self.OWN_ID))

        delivered = []
        for payload in (
            _message_create("777", bot=True, seq=2),
            _message_create(self.OWN_ID, bot=True, seq=3),
            _message_create("555", bot=False, seq=4),
        ):
            for action in proto.handle(payload):
                self.assertIsInstance(action, Dispatch)
                event = filter_message_create(action.data, proto.own_user_id)
                if event is not None:
                    delivered.append(event.author_id)
        self.assertEqual(delivered, ["777", "555"])


# --------------------------------------------------------------------------- #
# Runner integration (fake socket, offline)
# --------------------------------------------------------------------------- #


class _ScriptedWS:
    """Feeds scripted gateway payloads to the runner; records sends."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.sent: list[dict] = []
        self.close_codes: list[int] = []

    async def receive_text(self) -> str:
        if not self._script:
            raise wslib.WSClosed(1006, "script exhausted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return json.dumps(item)

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def send_close(self, code: int = 1000, reason: str = "") -> None:
        self.close_codes.append(code)

    async def close(self) -> None:
        pass


class TestGatewayRunner(unittest.IsolatedAsyncioTestCase):
    async def test_runner_identifies_dispatches_and_raises_on_fatal_close(self):
        script = [
            _hello(interval_ms=600000),  # huge interval: heartbeat never fires
            _ready(own_id="999"),
            _message_create("777", bot=True, seq=2),
            _message_create("999", bot=True, seq=3),  # self — retained as context
            wslib.WSClosed(4004, "Authentication failed."),
        ]
        ws = _ScriptedWS(script)

        async def fake_connect(url: str):
            return ws

        proto = GatewayProtocol(TOKEN)
        events = []
        runner = GatewayRunner(
            proto, events.append, connect=fake_connect, rng=lambda: 1.0
        )
        shutdown = asyncio.Event()

        with self.assertRaises(GatewayFatalError) as ctx:
            await runner.run(shutdown)
        self.assertIn("NUNCHI_DISCORD_TOKEN", str(ctx.exception))

        # IDENTIFY was sent; V2 retains exact self echoes for observation.
        self.assertEqual(ws.sent[0]["op"], 2)
        self.assertEqual([e.author_id for e in events], ["777", "999"])

    async def test_runner_resumes_on_next_connection(self):
        first = _ScriptedWS(
            [
                _hello(interval_ms=600000),
                _ready(session_id="sess-9", own_id="999", seq=1),
                _message_create("777", seq=8),
                wslib.WSClosed(1001, "server going away"),
            ]
        )
        second = _ScriptedWS(
            [
                _hello(interval_ms=600000),
                {"op": 0, "t": "RESUMED", "s": 9, "d": {}},
                wslib.WSClosed(4004, "stop the test"),
            ]
        )
        sockets = [first, second]

        async def fake_connect(url: str):
            return sockets.pop(0)

        proto = GatewayProtocol(TOKEN)
        runner = GatewayRunner(
            proto, lambda e: None, connect=fake_connect, rng=lambda: 1.0, initial_backoff=0.01
        )

        with self.assertRaises(GatewayFatalError):
            await runner.run(asyncio.Event())

        # Second connection resumed with the stored session and sequence
        self.assertEqual(second.sent[0]["op"], 6)
        self.assertEqual(second.sent[0]["d"]["session_id"], "sess-9")
        self.assertEqual(second.sent[0]["d"]["seq"], 8)


if __name__ == "__main__":
    unittest.main()
