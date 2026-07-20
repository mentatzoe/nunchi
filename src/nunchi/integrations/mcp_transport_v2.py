"""Authenticated, redirect-safe stdlib client for the Nunchi V2 MCP transport."""

from __future__ import annotations

import json
import math
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from typing import Any, Callable

from ..mcp_discord.events import V2_NOTIFICATION_METHOD


MAX_RESPONSE_BYTES = 1024 * 1024
MAX_SSE_EVENT_BYTES = 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30.0
STREAM_TIMEOUT_SECONDS = 65.0


class MCPTransportV2Error(RuntimeError):
    pass


def _strict_json(raw: str | bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(
            ValueError("non-finite")
        ),
    )


def iter_sse_data(lines: Iterable[str]) -> Iterator[str]:
    data_lines: list[str] = []
    size = 0
    for raw in lines:
        if len(raw.encode("utf-8")) > MAX_SSE_EVENT_BYTES + 2:
            raise MCPTransportV2Error("MCP SSE line exceeded its size budget")
        line = raw.rstrip("\r\n")
        if line == "":
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
                size = 0
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if field != "data":
            continue
        value = value.removeprefix(" ")
        size += len(value.encode("utf-8"))
        if size > MAX_SSE_EVENT_BYTES:
            raise MCPTransportV2Error("MCP SSE event exceeded its size budget")
        data_lines.append(value)
    if data_lines:
        yield "\n".join(data_lines)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _url(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 8192:
        raise MCPTransportV2Error("MCP transport URL is invalid")
    parsed = urllib.parse.urlsplit(value)
    loopback = parsed.hostname in ("127.0.0.1", "::1", "localhost")
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise MCPTransportV2Error("MCP transport URL is invalid") from exc
    if (
        parsed.scheme not in ("http", "https")
        or (parsed.scheme == "http" and not loopback)
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed_port is not None and not 1 <= parsed_port <= 65535
    ):
        raise MCPTransportV2Error("MCP transport URL is invalid")
    return value


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urllib.parse.urlsplit(value)
    return parsed.scheme, parsed.hostname or "", parsed.port


def _auth_token(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) < 32
        or len(value) > 4096
        or not value.isascii()
        or any(not 33 <= ord(character) <= 126 for character in value)
    ):
        raise MCPTransportV2Error("MCP bearer credential is invalid")
    return value


def _bounded_read(response) -> bytes:
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise MCPTransportV2Error("MCP response exceeded its size budget")
    return payload


class MCPTransportClientV2:
    """Minimal streamable-HTTP MCP client with one bearer-bound session."""

    def __init__(
        self,
        url: str,
        auth_token: str,
        *,
        http_timeout: float = HTTP_TIMEOUT_SECONDS,
        open_request: Callable | None = None,
    ) -> None:
        if (
            isinstance(http_timeout, bool)
            or not isinstance(http_timeout, (int, float))
            or not math.isfinite(float(http_timeout))
            or not 1 <= float(http_timeout) <= 300
        ):
            raise MCPTransportV2Error("MCP HTTP timeout is invalid")
        self.url = _url(url)
        self._auth_token = _auth_token(auth_token)
        self.http_timeout = float(http_timeout)
        self.session_id: str | None = None
        self._next_id = 10
        self._lock = threading.RLock()
        self._open_request = open_request or urllib.request.build_opener(
            _NoRedirect()
        ).open

    def _headers(self, *, with_session: bool, accept: str) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self._auth_token}",
        }
        if with_session:
            if not self.session_id:
                raise MCPTransportV2Error("MCP session is unavailable")
            headers["mcp-session-id"] = self.session_id
        return headers

    def _open(self, request: urllib.request.Request, timeout: float):
        try:
            return self._open_request(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in (307, 308):
                try:
                    exc.close()
                except Exception:
                    pass
                raise MCPTransportV2Error(
                    f"MCP HTTP request failed with status {exc.code}"
                ) from exc
            location = exc.headers.get("Location")
            try:
                exc.close()
            except Exception:
                pass
            if not location:
                raise MCPTransportV2Error("MCP redirect is invalid") from exc
            target = _url(urllib.parse.urljoin(request.full_url, location))
            if _origin(target) != _origin(request.full_url):
                raise MCPTransportV2Error("MCP cross-origin redirect was refused")
            self.url = target
            retry = urllib.request.Request(
                target,
                data=request.data,
                method=request.get_method(),
                headers=dict(request.header_items()),
            )
            try:
                return self._open_request(retry, timeout=timeout)
            except urllib.error.HTTPError as retry_error:
                raise MCPTransportV2Error(
                    f"MCP HTTP request failed with status {retry_error.code}"
                ) from retry_error
            except (urllib.error.URLError, OSError) as retry_error:
                raise MCPTransportV2Error("MCP network request failed") from retry_error
        except (urllib.error.URLError, OSError) as exc:
            raise MCPTransportV2Error("MCP network request failed") from exc

    def _post(self, body: dict[str, Any], *, with_session: bool):
        headers = self._headers(
            with_session=with_session,
            accept="application/json, text/event-stream",
        )
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.url,
            data=json.dumps(
                body,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        return self._open(request, self.http_timeout)

    def initialize(self) -> str:
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "nunchi-v2-room", "version": "2"},
            },
        }
        with self._post(initialize, with_session=False) as response:
            session_id = response.headers.get("mcp-session-id")
            _bounded_read(response)
        if (
            not isinstance(session_id, str)
            or not session_id
            or len(session_id) > 512
            or not session_id.isascii()
            or any(ord(character) < 33 or ord(character) > 126 for character in session_id)
        ):
            raise MCPTransportV2Error("MCP session identity is invalid")
        self.session_id = session_id
        with self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            with_session=True,
        ) as response:
            _bounded_read(response)
        with self._post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            with_session=True,
        ) as response:
            _bounded_read(response)
        return session_id

    def open_stream(self):
        request = urllib.request.Request(
            self.url,
            method="GET",
            headers=self._headers(
                with_session=True,
                accept="text/event-stream",
            ),
        )
        return self._open(request, STREAM_TIMEOUT_SECONDS)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(name, str) or not name or not isinstance(arguments, dict):
            raise MCPTransportV2Error("MCP tool call is invalid")
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        with self._post(body, with_session=True) as response:
            raw = _bounded_read(response)
        try:
            document = _strict_json(raw)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            document = None
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise MCPTransportV2Error("MCP tool response is invalid") from exc
            for data in iter_sse_data(text.splitlines(keepends=True)):
                try:
                    candidate = _strict_json(data)
                except (ValueError, json.JSONDecodeError):
                    continue
                if isinstance(candidate, dict) and candidate.get("id") == request_id:
                    document = candidate
                    break
        if not isinstance(document, dict) or document.get("id") != request_id:
            raise MCPTransportV2Error("MCP tool response is invalid")
        if document.get("error") is not None:
            raise MCPTransportV2Error("MCP tool call failed")
        result = document.get("result")
        if not isinstance(result, dict):
            raise MCPTransportV2Error("MCP tool result is invalid")
        if result.get("isError") is True:
            raise MCPTransportV2Error("MCP tool call failed")
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text = item.get("text")
                if not isinstance(text, str):
                    continue
                try:
                    parsed = _strict_json(text)
                except (ValueError, json.JSONDecodeError) as exc:
                    raise MCPTransportV2Error(
                        "MCP tool content is invalid"
                    ) from exc
                if not isinstance(parsed, dict):
                    raise MCPTransportV2Error("MCP tool content is invalid")
                return parsed
        return result

    def stream_events(
        self,
        notification_method: str = V2_NOTIFICATION_METHOD,
    ) -> Iterator[dict[str, Any]]:
        if notification_method != V2_NOTIFICATION_METHOD:
            raise MCPTransportV2Error("MCP notification method is invalid")
        with self.open_stream() as stream:
            def decoded_lines():
                for raw in stream:
                    try:
                        yield raw.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise MCPTransportV2Error(
                            "MCP SSE stream is invalid"
                        ) from exc

            lines = decoded_lines()
            for data in iter_sse_data(lines):
                try:
                    message = _strict_json(data)
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                    continue
                if (
                    not isinstance(message, dict)
                    or message.get("method") != notification_method
                    or not isinstance(message.get("params"), dict)
                ):
                    continue
                yield message["params"]


__all__ = [
    "MCPTransportClientV2",
    "MCPTransportV2Error",
    "iter_sse_data",
]
