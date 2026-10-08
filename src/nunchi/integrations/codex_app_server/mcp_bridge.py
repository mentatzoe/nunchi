"""The room tools as an MCP server over stdio, for a Codex thread (#94 step 9e).

Codex starts this file once per thread, from the thread's own config
(`thread/start` ``config.mcp_servers``), and talks MCP to it over stdio. The
bridge holds no turn rules: it forwards each call to the integration's private
socket, which speaks the library's local turn protocol (`nunchi.turn_server`,
``I-040D``), and returns the library's answer unchanged.

- ``tools/list`` asks ``/v1/attach`` for the room tools.
- ``tools/call`` sends ``/v1/turn/call`` with the Codex turn id Codex puts in the
  request's ``_meta`` (``x-codex-turn-metadata.turn_id``), then asks
  ``/v1/turn/after-tool`` and adds the room's news to the result (steering).

It runs as a plain script (``python -I mcp_bridge.py``) and imports only the
standard library, so it needs no path setup and starts fast. The socket path
and the launch secret come from its environment, which Codex sets from the
thread's config. A command Codex runs outside its sandbox can read them; the
guard keeps the secret out of the room.
"""

from __future__ import annotations

from collections.abc import Mapping
import http.client
import json
import os
import socket
import sys
from typing import Any, TextIO

SOCKET_ENV = "NUNCHI_CODEX_TURN_SOCKET"
SECRET_ENV = "NUNCHI_CODEX_TURN_SESSION"
SERVER_NAME = "nunchi-room"
# MCP versions this bridge speaks; it answers with the client's when it can.
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
TURN_METADATA_KEY = "x-codex-turn-metadata"
UNREACHABLE = "The Nunchi room is unreachable. Nothing was posted."
_SOCKET_TIMEOUT_SECONDS = 90.0


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


class TurnSocket:
    """The integration's private socket, with the launch secret."""

    def __init__(self, path: str, secret: str, timeout: float = _SOCKET_TIMEOUT_SECONDS) -> None:
        self.path = path
        self.secret = secret
        self.timeout = timeout

    def post(self, route: str, body: Mapping[str, Any]) -> dict[str, Any]:
        connection = _UnixConnection(self.path, self.timeout)
        try:
            connection.request(
                "POST",
                route,
                json.dumps(body, ensure_ascii=False).encode("utf-8"),
                {"Content-Type": "application/json", "X-Nunchi-Session": self.secret},
            )
            response = connection.getresponse()
            payload = response.read()
            if response.status != 200:
                raise OSError(f"the room answered {response.status}")
            answer = json.loads(payload)
            if not isinstance(answer, dict):
                raise OSError("the room's answer is not an object")
            return answer
        finally:
            connection.close()


def codex_turn_id(params: Mapping[str, Any]) -> str | None:
    """The Codex turn a tool call belongs to, from the request's ``_meta``."""

    meta = params.get("_meta")
    if not isinstance(meta, Mapping):
        return None
    turn = meta.get(TURN_METADATA_KEY)
    if isinstance(turn, str):
        try:
            turn = json.loads(turn)
        except json.JSONDecodeError:
            return None
    if not isinstance(turn, Mapping):
        return None
    value = turn.get("turn_id")
    return value if isinstance(value, str) and value else None


class Bridge:
    """Answers one MCP message at a time; see the module docstring."""

    def __init__(self, room: TurnSocket) -> None:
        self.room = room

    def handle(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        if "id" not in message:
            return None  # a notification, such as notifications/initialized
        request_id = message["id"]
        params = message.get("params")
        params = params if isinstance(params, Mapping) else {}
        try:
            if method == "initialize":
                result: dict[str, Any] = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._tools()}
            elif method == "tools/call":
                result = self._call(params)
            else:
                return _error(request_id, -32601, f"{method} is not supported")
        except OSError as exc:
            return _error(request_id, -32603, f"{UNREACHABLE} ({exc})")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _initialize(self, params: Mapping[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": "1"},
        }

    def _tools(self) -> list[dict[str, Any]]:
        attached = self.room.post("/v1/attach", {})
        tools = attached.get("tools")
        if not isinstance(tools, list):
            raise OSError("the room offered no tools")
        return [
            {"name": tool["name"], "description": tool["description"], "inputSchema": tool["inputSchema"]}
            for tool in tools
            if isinstance(tool, Mapping)
        ]

    def _call(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments")
        turn_id = codex_turn_id(params)
        try:
            answer = self.room.post(
                "/v1/turn/call",
                {
                    "turn_id": turn_id,
                    "tool": name,
                    "input": arguments if isinstance(arguments, Mapping) else {},
                },
            )
        except OSError:
            return _text(UNREACHABLE, error=True)
        ok = answer.get("ok") is True
        text = str(answer.get("text") if ok else answer.get("error", ""))
        # Steering: what others posted meanwhile goes with this tool's result.
        if turn_id is not None:
            try:
                update = self.room.post("/v1/turn/after-tool", {"turn_id": turn_id}).get("text")
            except OSError:
                update = None
            if isinstance(update, str) and update:
                text = f"{text}\n\n{update}"
        return _text(text, error=not ok)


def _text(text: str, *, error: bool) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(bridge: Bridge, stdin: TextIO, stdout: TextIO) -> None:
    """Newline-delimited JSON-RPC over stdio, one message per line (MCP's stdio transport)."""

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "not JSON")) + "\n")
            stdout.flush()
            continue
        if not isinstance(message, dict):
            continue
        answer = bridge.handle(message)
        if answer is not None:
            stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
            stdout.flush()


def main(environ: Mapping[str, str] | None = None) -> int:
    environ = os.environ if environ is None else environ
    path = environ.get(SOCKET_ENV)
    secret = environ.get(SECRET_ENV)
    if not path or not secret:
        sys.stderr.write(f"nunchi room bridge: {SOCKET_ENV} and {SECRET_ENV} must be set\n")
        return 2
    serve(Bridge(TurnSocket(path, secret)), sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
