"""Discord's gateway: sessions, heartbeats, IDENTIFY and RESUME, member chunks, fan-out and close codes.

A client may send op 1 at any time, even before IDENTIFY (discord.py
heartbeats as soon as HELLO arrives), and ops 2, 6 and 8; op 8 before
IDENTIFY closes with 4003, a second IDENTIFY or RESUME with 4005, and any
other op with 4001 and an ``unknown`` record. Nothing is dispatched before
READY. A session outlives its connection and keeps every dispatch, so a
RESUME replays what the client missed, unless the director ended it (op 9
not resumable, or a close with 4007 or 4009, after which Discord says to
start a new session). Frames are uncompressed TEXT, whatever ``compress=``
asks. The frame codec is the transport's own (`nunchi.mcp_discord.ws`);
discord.py's aiohttp is the independent check on it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import struct
from typing import Any

from nunchi.mcp_discord.ws import OP_CLOSE, OP_PING, OP_PONG, OP_TEXT, FrameDecoder, MessageAssembler, WSError, encode_frame, parse_close

from . import payloads
from .world import INTENTS, PERMISSIONS, PRIVILEGED, Member

HEARTBEAT_INTERVAL_MS = 41_250
NEW_SESSION = (4007, 4009)  # close codes after which Discord says to reconnect and start a new session


def _op(op: int, d: Any = None) -> dict[str, Any]:
    return {"op": op, "d": d, "s": None, "t": None}


class Session:
    """One bot's gateway session; its frames stay for RESUME."""

    def __init__(self, hub: Hub, bot: Member, intents: int) -> None:
        self.hub = hub
        self.id = secrets.token_hex(16)
        self.bot = bot
        self.intents = intents
        self.seq = 0
        self.frames: list[dict[str, Any]] = []
        self.connection: Connection | None = None

    def dispatch(self, event: str, data: dict[str, Any]) -> None:
        self.hub.fd.check_shape(event, data)
        self.seq += 1
        frame = {"op": 0, "t": event, "s": self.seq, "d": data}
        self.frames.append(frame)
        if self.connection is not None:
            self.connection.send(frame)


class Hub:
    """Every session; fan-out and the director's gateway actions."""

    def __init__(self, fd: Any) -> None:
        self.fd = fd
        self.sessions: dict[str, Session] = {}

    def fan_out(self, event: str, data: dict[str, Any], channel_id: str, intent: int) -> list[str]:
        """Dispatch to every session with the intent whose bot can see the channel, the author's included."""
        sent = []
        for session in list(self.sessions.values()):
            if session.intents & intent and self.fd.world.permissions(session.bot.id, channel_id) & PERMISSIONS["VIEW_CHANNEL"]:
                session.dispatch(event, data)
                sent.append(session.bot.name)
        return sent

    def act(self, bot: str, action: str, *, code: int = 4000, resumable: bool = False) -> int:
        """reconnect (op 7), invalid_session (op 9), close with ``code``, or drop, on each of the bot's live connections."""
        connections = [s.connection for s in self.sessions.values() if s.bot.name == bot and s.connection is not None]
        for connection in connections:
            if action == "reconnect":
                connection.send(_op(7))
            elif action == "invalid_session":
                connection.send(_op(9, resumable))
                if not resumable and connection.session is not None:
                    del self.sessions[connection.session.id]
                    connection.detach()
            elif action == "close":
                if code in NEW_SESSION and connection.session is not None:
                    del self.sessions[connection.session.id]
                connection.close(code)
            elif action == "drop":
                connection.drop()
            else:
                raise ValueError(f"unknown gateway action {action!r}")
        return len(connections)


class Connection:
    def __init__(self, hub: Hub, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, conn: int) -> None:
        self.hub = hub
        self.world = hub.fd.world
        self.wire = hub.fd.wire
        self.reader = reader
        self.writer = writer
        self.id = conn
        self.session: Session | None = None
        self.bot_name: str | None = None
        self.closing = False

    def log(self, direction: str, payload: dict[str, Any]) -> None:
        d = payload.get("d")
        if direction == "in" and payload.get("op") in (2, 6) and isinstance(d, dict):
            d = {**d, "token": f"<bot:{self.bot_name}>" if self.bot_name else "<unknown token>"}
        self.wire.write("ws", conn=self.id, dir=direction, op=payload.get("op"), t=payload.get("t"), s=payload.get("s"), d=d, bot=self.bot_name)

    def send(self, payload: dict[str, Any]) -> None:
        if self.closing:
            return
        self.log("out", payload)
        self.writer.write(encode_frame(OP_TEXT, json.dumps(payload).encode(), mask=False))

    async def run(self) -> None:
        self.send(_op(10, {"heartbeat_interval": HEARTBEAT_INTERVAL_MS}))
        decoder, assembler = FrameDecoder(), MessageAssembler()
        try:
            while True:
                data = await self.reader.read(65536)
                if not data:
                    return self._ended("eof", None)
                for frame in decoder.feed(data):
                    message = assembler.feed(frame)
                    if message is None:
                        continue
                    opcode, body = message
                    if opcode == OP_CLOSE:
                        code, _ = parse_close(body)
                        if not self.closing:
                            self.writer.write(encode_frame(OP_CLOSE, body[:2], mask=False))
                        return self._ended("client", code)
                    if opcode == OP_PING:
                        self.writer.write(encode_frame(OP_PONG, body, mask=False))
                    elif opcode != OP_PONG and not self.closing:
                        self.receive(body)
        except (ConnectionError, WSError):
            self._ended("error", None)
        finally:
            self.detach()
            self.writer.close()

    def receive(self, raw: bytes) -> None:
        try:
            payload = json.loads(raw)
            assert isinstance(payload, dict)
        except (ValueError, AssertionError):  # its size and hash only: the text may hold a token
            self.wire.write("unknown", what="payload", conn=self.id, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()[:16])
            return self.close(4002, "Decode error.")
        op, d = payload.get("op"), payload.get("d") if isinstance(payload.get("d"), dict) else {}
        if op in (2, 6):
            bot = self.world.bot_by_token(d.get("token"))
            self.bot_name = bot.name if bot else None
        self.log("in", payload)
        try:
            if op in (2, 6) and self.session is not None:
                self.close(4005, "Already authenticated.")
            elif op == 1:
                self.send(_op(11))
            elif op == 2:
                self.identify(d)
            elif op == 6:
                self.resume(d)
            elif op == 8:
                self.request_members(d)
            else:
                self.wire.write("unknown", what="op", op=op, conn=self.id, bot=self.bot_name)
                self.close(4001, "Unknown opcode.")
        except Exception as error:  # a payload nobody foresaw, or a stand-in bug: recorded, never a silent drop
            self.wire.write("unknown", what="stand-in error", op=op, conn=self.id, bot=self.bot_name, detail=repr(error))
            self.close(4000, "Unknown error.")

    def identify(self, d: dict[str, Any]) -> None:
        bot = self.world.bot_by_token(d.get("token"))
        if bot is None:
            return self.close(4004, "Authentication failed.")
        intents = d.get("intents") if isinstance(d.get("intents"), int) else 0
        if intents & PRIVILEGED & ~bot.privileged:
            return self.close(4014, "Disallowed intent(s).")
        for old in [s for s in self.hub.sessions.values() if s.bot is bot and s.connection is None]:
            del self.hub.sessions[old.id]  # a fresh IDENTIFY ends the bot's sessions nobody can resume
        session = Session(self.hub, bot, intents)
        self.hub.sessions[session.id] = session
        self.attach(session)
        session.dispatch("READY", payloads.ready(self.world, bot, session.id, self.hub.fd.gateway_url))
        if intents & INTENTS["GUILDS"]:
            session.dispatch("GUILD_CREATE", payloads.guild_create(self.world, bot, intents))

    def resume(self, d: dict[str, Any]) -> None:
        bot = self.world.bot_by_token(d.get("token"))
        if bot is None:
            return self.close(4004, "Authentication failed.")
        session = self.hub.sessions.get(d.get("session_id"))
        if session is None or session.bot is not bot:
            return self.send(_op(9, False))
        self.attach(session)
        seq = d.get("seq") if isinstance(d.get("seq"), int) else 0
        for frame in session.frames:
            if frame["s"] > seq:
                self.send(frame)
        session.dispatch("RESUMED", {})

    def request_members(self, d: dict[str, Any]) -> None:
        if self.session is None:
            return self.close(4003, "Not authenticated.")
        wanted = d.get("user_ids")
        ids = {str(i) for i in (wanted if isinstance(wanted, list) else [wanted] if wanted else [])}
        query = str(d.get("query") or "")
        found = [m for m in self.world.members.values() if (m.id in ids if ids else m.name.startswith(query))]
        limit = d.get("limit") if isinstance(d.get("limit"), int) else 0
        self.session.dispatch("GUILD_MEMBERS_CHUNK", payloads.members_chunk(self.world, found[:limit] if limit else found, d.get("nonce")))

    def attach(self, session: Session) -> None:
        if session.connection is not None and session.connection is not self:
            session.connection.session = None
        self.session, session.connection = session, self

    def detach(self) -> None:
        if self.session is not None and self.session.connection is self:
            self.session.connection = None
        self.session = None

    def close(self, code: int, reason: str = "") -> None:
        """Close with ``code``; the client answers with its own close frame, or the socket goes after a second."""
        if self.closing:
            return
        self.closing = True
        self.wire.write("ws_close", conn=self.id, code=code, by="server", bot=self.bot_name)
        self.writer.write(encode_frame(OP_CLOSE, struct.pack(">H", code) + reason.encode(), mask=False))
        self.detach()
        asyncio.get_running_loop().call_later(1.0, self.writer.close)

    def drop(self) -> None:
        """End the TCP connection without a close frame, as a network failure would."""
        self.closing = True
        self.wire.write("ws_close", conn=self.id, code=None, by="drop", bot=self.bot_name)
        self.detach()
        self.writer.transport.abort()

    def _ended(self, by: str, code: int | None) -> None:
        if not self.closing:
            self.wire.write("ws_close", conn=self.id, code=code, by=by, bot=self.bot_name)
        self.closing = True
