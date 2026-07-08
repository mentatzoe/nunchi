"""Minimal RFC 6455 WebSocket client (stdlib only).

Implements exactly what the Discord gateway needs: the client handshake,
text/binary frames, ping/pong, close, no extensions, no compression (the
gateway URL is requested without ``compress=``). The frame codec and message
assembler are sans-IO and unit-tested offline; :class:`WSClient` is a thin
asyncio shell over them.
"""

from __future__ import annotations

import asyncio
import base64
import collections
import hashlib
import os
import ssl
import struct
from dataclasses import dataclass
from urllib.parse import urlsplit

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

_CONTROL_OPS = frozenset({OP_CLOSE, OP_PING, OP_PONG})


class WSError(Exception):
    """Protocol or handshake failure."""


class WSClosed(Exception):
    """The connection closed (close frame or EOF)."""

    def __init__(self, code: int | None, reason: str = "") -> None:
        super().__init__(f"websocket closed (code={code} reason={reason!r})")
        self.code = code
        self.reason = reason


def accept_key(key: str) -> str:
    """Compute the expected Sec-WebSocket-Accept for a client key."""
    digest = hashlib.sha1((key + _GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_frame(
    opcode: int,
    payload: bytes,
    *,
    fin: bool = True,
    mask: bool = True,
    mask_key: bytes | None = None,
) -> bytes:
    """Encode one frame. Client frames must be masked (mask=True)."""
    head = bytearray([(0x80 if fin else 0x00) | (opcode & 0x0F)])
    n = len(payload)
    mask_bit = 0x80 if mask else 0x00
    if n < 126:
        head.append(mask_bit | n)
    elif n < 65536:
        head.append(mask_bit | 126)
        head += struct.pack(">H", n)
    else:
        head.append(mask_bit | 127)
        head += struct.pack(">Q", n)
    if not mask:
        return bytes(head) + payload
    if mask_key is None:
        mask_key = os.urandom(4)
    if len(mask_key) != 4:
        raise WSError("mask_key must be 4 bytes")
    masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return bytes(head) + mask_key + masked


@dataclass(frozen=True)
class Frame:
    fin: bool
    opcode: int
    payload: bytes


class FrameDecoder:
    """Incremental frame parser: feed bytes, get complete frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        frames: list[Frame] = []
        while True:
            frame = self._try_parse()
            if frame is None:
                return frames
            frames.append(frame)

    def _try_parse(self) -> Frame | None:
        buf = self._buf
        if len(buf) < 2:
            return None
        b1, b2 = buf[0], buf[1]
        fin = bool(b1 & 0x80)
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        offset = 2
        if length == 126:
            if len(buf) < offset + 2:
                return None
            length = struct.unpack_from(">H", buf, offset)[0]
            offset += 2
        elif length == 127:
            if len(buf) < offset + 8:
                return None
            length = struct.unpack_from(">Q", buf, offset)[0]
            offset += 8
        mask_key = b""
        if masked:
            if len(buf) < offset + 4:
                return None
            mask_key = bytes(buf[offset : offset + 4])
            offset += 4
        if len(buf) < offset + length:
            return None
        payload = bytes(buf[offset : offset + length])
        del self._buf[: offset + length]
        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        return Frame(fin=fin, opcode=opcode, payload=payload)


class MessageAssembler:
    """Reassembles fragmented data frames; control frames pass through."""

    def __init__(self) -> None:
        self._opcode: int | None = None
        self._parts: list[bytes] = []

    def feed(self, frame: Frame) -> tuple[int, bytes] | None:
        """Returns a complete (opcode, payload) message, or None if buffering."""
        if frame.opcode in _CONTROL_OPS:
            if not frame.fin:
                raise WSError("fragmented control frame")
            return (frame.opcode, frame.payload)
        if frame.opcode == OP_CONT:
            if self._opcode is None:
                raise WSError("continuation frame without a started message")
            self._parts.append(frame.payload)
            if not frame.fin:
                return None
            opcode, payload = self._opcode, b"".join(self._parts)
            self._opcode, self._parts = None, []
            return (opcode, payload)
        # New data frame (text/binary)
        if self._opcode is not None:
            raise WSError("new data frame while a fragmented message is open")
        if frame.fin:
            return (frame.opcode, frame.payload)
        self._opcode = frame.opcode
        self._parts = [frame.payload]
        return None


def parse_close(payload: bytes) -> tuple[int | None, str]:
    """Extract (code, reason) from a close frame payload."""
    if len(payload) < 2:
        return (None, "")
    code = struct.unpack(">H", payload[:2])[0]
    reason = payload[2:].decode("utf-8", errors="replace")
    return (code, reason)


class WSClient:
    """Asyncio WebSocket client over the sans-IO codec."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._decoder = FrameDecoder()
        self._assembler = MessageAssembler()
        self._write_lock = asyncio.Lock()
        self._pending: collections.deque[tuple[int, bytes]] = collections.deque()
        self._closed = False

    @classmethod
    async def connect(cls, url: str, *, connect_timeout: float = 30.0) -> "WSClient":
        parts = urlsplit(url)
        if parts.scheme not in ("ws", "wss"):
            raise WSError(f"unsupported scheme {parts.scheme!r}")
        host = parts.hostname or ""
        secure = parts.scheme == "wss"
        port = parts.port or (443 if secure else 80)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        ssl_ctx = ssl.create_default_context() if secure else None
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_ctx), connect_timeout
        )
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        writer.write(request.encode("ascii"))
        await writer.drain()

        status_line = (await asyncio.wait_for(reader.readline(), connect_timeout)).decode(
            "latin-1"
        )
        if " 101 " not in status_line:
            writer.close()
            raise WSError(f"handshake rejected: {status_line.strip()!r}")
        headers: dict[str, str] = {}
        while True:
            line = (await asyncio.wait_for(reader.readline(), connect_timeout)).decode("latin-1")
            if line in ("\r\n", "\n", ""):
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        if headers.get("sec-websocket-accept") != accept_key(key):
            writer.close()
            raise WSError("handshake failed: bad Sec-WebSocket-Accept")
        return cls(reader, writer)

    async def _send_frame(self, opcode: int, payload: bytes) -> None:
        async with self._write_lock:
            self._writer.write(encode_frame(opcode, payload))
            await self._writer.drain()

    async def send_text(self, text: str) -> None:
        await self._send_frame(OP_TEXT, text.encode("utf-8"))

    async def send_close(self, code: int = 1000, reason: str = "") -> None:
        payload = struct.pack(">H", code) + reason.encode("utf-8")
        try:
            await self._send_frame(OP_CLOSE, payload)
        except (ConnectionError, OSError):
            pass

    async def receive_text(self) -> str:
        """Return the next text message; pings are answered; raises WSClosed."""
        while True:
            while self._pending:
                opcode, payload = self._pending.popleft()
                if opcode == OP_PING:
                    await self._send_frame(OP_PONG, payload)
                elif opcode == OP_PONG:
                    continue
                elif opcode == OP_CLOSE:
                    code, reason = parse_close(payload)
                    raise WSClosed(code, reason)
                else:
                    return payload.decode("utf-8")
            data = await self._reader.read(65536)
            if not data:
                raise WSClosed(None, "eof")
            for frame in self._decoder.feed(data):
                message = self._assembler.feed(frame)
                if message is not None:
                    self._pending.append(message)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
