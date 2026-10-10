"""Minimal streamable-HTTP MCP client for the shared Discord transport."""

from __future__ import annotations

import contextlib
import http.client
import json
from typing import Any, Iterator
import urllib.request


def _iter_sse(lines) -> Iterator[str]:
    data: list[str] = []
    for raw in lines:
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        line = line.rstrip("\r\n")
        if not line:
            if data:
                yield "\n".join(data)
                data.clear()
            continue
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield "\n".join(data)


@contextlib.contextmanager
def _ends_as_a_network_error():
    """``http.client``'s errors (a response cut short) are not ``OSError``s; the runners reconnect on those."""

    try:
        yield
    except http.client.HTTPException as exc:
        raise ConnectionError(f"the transport ended mid-response: {type(exc).__name__}") from exc


class StreamableMCPClient:
    def __init__(self, url: str, *, timeout_seconds: float = 30) -> None:
        # Starlette mounts the streamable-HTTP app at ``/mcp/`` and redirects
        # the documented bare ``/mcp`` path with HTTP 307.  urllib deliberately
        # refuses to replay a POST across that redirect, so pin the canonical
        # endpoint before any initialize or tool request can carry a body.
        self.url = url if url.endswith("/") else f"{url}/"
        self.timeout_seconds = timeout_seconds
        self.session_id: str | None = None
        self._next_id = 1

    def _post(self, body: dict[str, Any], *, session: bool):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if session and self.session_id:
            headers["mcp-session-id"] = self.session_id
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=self.timeout_seconds)

    def connect(self) -> str:
        # A reconnect drops the old session first: the transport keeps one alive,
        # with its tasks and streams, until it is ended.
        self.close()
        request_id = self._next_id
        self._next_id += 1
        with _ends_as_a_network_error(), self._post(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "nunchi-codex-v2", "version": "2.0.0"},
                },
            },
            session=False,
        ) as response:
            self.session_id = response.headers.get("mcp-session-id")
            response.read()
        if not self.session_id:
            raise RuntimeError("shared Discord transport did not issue an MCP session")
        with _ends_as_a_network_error(), self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session=True,
        ) as response:
            response.read()
        self.call("tools/list", {})
        return self.session_id

    def close(self) -> None:
        """End the MCP session on the server, if there is one (``DELETE``), and forget it.

        Best effort: a transport that is gone ends its sessions itself.
        """

        session_id, self.session_id = self.session_id, None
        if not session_id:
            return
        request = urllib.request.Request(
            self.url,
            headers={"MCP-Protocol-Version": "2025-03-26", "mcp-session-id": session_id},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()
        except (OSError, http.client.HTTPException):
            pass

    def call(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        with _ends_as_a_network_error(), self._post(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
            session=True,
        ) as response:
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                messages = _iter_sse(response)
                for data in messages:
                    payload = json.loads(data)
                    if isinstance(payload, dict) and payload.get("id") == request_id:
                        break
                else:
                    raise RuntimeError(f"MCP {method} returned no correlated response")
            else:
                payload = json.load(response)
        if (
            not isinstance(payload, dict)
            or payload.get("jsonrpc") != "2.0"
            or payload.get("id") != request_id
        ):
            raise RuntimeError(f"MCP {method} returned an uncorrelated response")
        if ("result" in payload) == ("error" in payload):
            raise RuntimeError(f"MCP {method} response has an invalid result shape")
        if "error" in payload:
            raise RuntimeError(f"MCP {method} failed: {payload['error']}")
        return payload["result"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self.call("tools/call", {"name": name, "arguments": arguments})

    def open_stream(self):
        """Open the notification stream (``GET``) and return once the server has it.

        The server keeps a notification for a session only while this stream is
        open: the MCP SDK drops one sent earlier, with no error. Open the stream
        before anything registers the session for notifications, and read it
        with :meth:`notifications`. The caller closes a stream it does not read.
        """

        if not self.session_id:
            self.connect()
        headers = {
            "Accept": "text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
            "mcp-session-id": self.session_id,
        }
        request = urllib.request.Request(self.url, headers=headers, method="GET")
        return urllib.request.urlopen(request, timeout=None)

    def notifications(self, stream=None) -> Iterator[tuple[str, dict[str, Any]]]:
        """The notifications of *stream* (from :meth:`open_stream`), or of a stream opened here; closes it at the end."""

        with (stream if stream is not None else self.open_stream()) as response:
            try:
                for data in _iter_sse(response):
                    try:
                        message = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(message, dict) or message.get("method") is None:
                        continue
                    params = message.get("params")
                    if isinstance(params, dict):
                        yield str(message["method"]), params
            except http.client.HTTPException as exc:
                # The server went away mid-chunk. Say so as the network error it
                # is, so the caller reconnects and records a gap.
                raise ConnectionError(f"the notification stream ended: {type(exc).__name__}") from exc
