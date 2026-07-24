"""Minimal streamable-HTTP MCP client for the shared Discord transport."""

from __future__ import annotations

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


class StreamableMCPClient:
    def __init__(self, url: str, *, timeout_seconds: float = 30) -> None:
        self.url = url
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
        request_id = self._next_id
        self._next_id += 1
        with self._post(
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
        with self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session=True,
        ) as response:
            response.read()
        self.call("tools/list", {})
        return self.session_id

    def call(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        with self._post(
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

    def notifications(self) -> Iterator[tuple[str, dict[str, Any]]]:
        if not self.session_id:
            self.connect()
        headers = {
            "Accept": "text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
            "mcp-session-id": self.session_id,
        }
        request = urllib.request.Request(self.url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=None) as response:
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
