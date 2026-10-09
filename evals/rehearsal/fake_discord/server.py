"""The stand-in's server: HTTP/1.1 with keep-alive, routing by ``Host``, and the WebSocket upgrade.

With a certificate it serves TLS at Discord's names, for the launcher (PR
3b): every ClientHello is recorded (``tls_hello``), and each handshake that
completes (``tls``), so a client that refuses the certificate shows as a
hello with no handshake; only an SNI in `HOSTS` is answered (any other is
refused and recorded as unknown), and ALPN offers ``http/1.1``, as aiohttp
asks. Without one it serves plain loopback, for tests, where the loopback
address stands for both ``discord.com`` and ``gateway.discord.gg``. A
gateway URL other than ``?v=10&encoding=json`` (``compress=`` aside) is
recorded as unknown, since every frame is v10 JSON.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import ssl
from typing import Any
from urllib.parse import parse_qs, urlsplit

from nunchi.mcp_discord.ws import accept_key

from . import rest
from .gateway import Connection

REST_HOST = "discord.com"
GATEWAY_HOST = "gateway.discord.gg"
# The names a client may reach; only the first two are served, the rest are answered 599 and recorded.
HOSTS = (REST_HOST, GATEWAY_HOST, "cdn.discordapp.com", "media.discordapp.net", "discordapp.com")


def tls_context(certfile: str, keyfile: str, wire: Any) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)
    context.set_alpn_protocols(["http/1.1"])

    def check_name(ssl_object: ssl.SSLObject, server_name: str | None, _context: ssl.SSLContext) -> int | None:
        ssl_object.server_name_seen = server_name  # type: ignore[attr-defined]
        if server_name in HOSTS:
            wire.write("tls_hello", server_name=server_name)
            return None
        wire.write("unknown", what="sni", server_name=server_name)
        return ssl.ALERT_DESCRIPTION_UNRECOGNIZED_NAME

    context.sni_callback = check_name
    return context


async def serve(fd: Any, conn: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """One client connection: requests until it closes, or a WebSocket upgrade that hands it to the gateway."""
    ssl_object = writer.get_extra_info("ssl_object")
    if ssl_object is not None:
        fd.wire.write("tls", conn=conn, server_name=getattr(ssl_object, "server_name_seen", None), alpn=ssl_object.selected_alpn_protocol())
    try:
        while True:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            method, target, _ = head[0].split(" ", 2)
            headers = {}
            for line in head[1:]:
                name, _, value = line.partition(":")
                if name:
                    headers[name.strip().lower()] = value.strip()
            host = headers.get("host", "").rsplit(":", 1)[0]
            if "transfer-encoding" in headers:
                fd.wire.write("unknown", what="chunked request", conn=conn, method=method, path=target)
                return
            body = await reader.readexactly(int(headers.get("content-length") or 0))
            if headers.get("upgrade", "").lower() == "websocket" and host in fd.gateway_hosts:
                writer.write(
                    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept_key(headers.get('sec-websocket-key', ''))}\r\n\r\n".encode()
                )
                fd.wire.write("ws_open", conn=conn, host=host, path=target, headers=sorted(headers), user_agent=headers.get("user-agent"))
                query = parse_qs(urlsplit(target).query)
                if query.get("v") != ["10"] or query.get("encoding") != ["json"]:
                    fd.wire.write("unknown", what="gateway query", conn=conn, path=target)
                await Connection(fd.hub, reader, writer, conn).run()
                return
            status, response_headers, data = rest.handle(fd, rest.Request(conn, host, method, target, headers, body))
            try:
                reason = HTTPStatus(status).phrase
            except ValueError:
                reason = "Unknown"
            if status != 204:
                response_headers["Content-Length"] = str(len(data))
            lines = "".join(f"{name}: {value}\r\n" for name, value in response_headers.items())
            writer.write(f"HTTP/1.1 {status} {reason}\r\n{lines}\r\n".encode() + data)
            await writer.drain()
            if headers.get("connection", "").lower() == "close":
                return
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError, ValueError):
        return
    finally:
        writer.close()
