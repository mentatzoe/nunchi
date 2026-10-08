"""The turn as versioned JSON over a private local socket (#94 step 9c).

For harnesses outside Python, the same calls a Python integration makes on a
`TurnParticipant` (`nunchi.turn`), as HTTP over a Unix socket only the
integration's process can reach. Each request carries the per-launch session
secret the integration was given; any other caller is refused. The harness
holds that secret, so its agent may read it: the server adds it to its
participant's secret guard, and a room action that carries it is refused like
any other withheld secret. This is interface ``I-040D LocalTurnProtocolV2@1``:

| Route | Body | Answer |
|---|---|---|
| `/v1/attach` | `{}` | `protocol`, `version`, `posting`, `silence_marker`, `tools` |
| `/v1/turn/bind` | `turn_id`, `wake_id` | `bound` |
| `/v1/turn/call` | `turn_id`, `tool`, `input` | `ok` with `text`, or `error` |
| `/v1/turn/after-tool` | `turn_id` | `text` or null (steering) |
| `/v1/turn/finish` | `turn_id`, `answer` | `finish` (`deliver`, `continue`, `silent`) and `text` |
| `/v1/turn/end` | `turn_id` (optional), `ok`, `detail`, `note` (optional) | `ended` |

`/v1/turn-start`, `/v1/tool` and `/v1/news` are the first integration's names
for bind, call and after-tool, and stay as aliases.
"""

from __future__ import annotations

from collections.abc import Mapping
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
import threading
from typing import Any

from .turn import TurnParticipant

PROTOCOL = "nunchi.turn-session"
VERSION = 1
MAX_BODY_BYTES = 256 * 1024
# A launch secret shorter than this is refused: the guard must be able to hold it.
MIN_SECRET_CHARACTERS = 16
_ALIASES = {
    "/v1/turn-start": "/v1/turn/bind",
    "/v1/tool": "/v1/turn/call",
    "/v1/news": "/v1/turn/after-tool",
}


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request: Any, client_address: Any) -> None:
        # A caller that hangs up is not the server's failure; stay quiet.
        pass


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


class TurnServer:
    """The integration's only way in to its participant's turns.

    Build it before the participant's first turn: it withholds
    ``session_secret`` from the room through the participant's guard
    (`TurnParticipant.withhold`), and a turn keeps the guard it started with.
    """

    def __init__(
        self,
        participant: TurnParticipant,
        *,
        socket_path: Path,
        session_secret: str,
    ) -> None:
        if not isinstance(session_secret, str) or len(session_secret) < MIN_SECRET_CHARACTERS:
            raise ValueError(
                f"the session secret must be at least {MIN_SECRET_CHARACTERS} characters"
            )
        self.participant = participant
        self.socket_path = socket_path
        self._secret = session_secret.encode()
        self._server: _UnixHTTPServer | None = None
        # The harness holds the secret, so its agent may read it; never post it.
        participant.withhold([session_secret])

    def start(self) -> None:
        directory = self.socket_path.parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                pass

            def address_string(self) -> str:
                return "local"

            def _answer(self, status: int, body: Mapping[str, Any]) -> None:
                payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                if status != 200:
                    # The request body may be unread; never parse it as a request.
                    self.send_header("Connection", "close")
                    self.close_connection = True
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = -1
                if not 0 <= length <= MAX_BODY_BYTES:
                    self._answer(413, {"error": "request body is too large"})
                    return
                # Read the bounded body before refusing anyone, so a refused
                # caller gets its answer instead of a reset connection.
                raw = self.rfile.read(length)
                supplied = self.headers.get("X-Nunchi-Session", "").encode()
                if not hmac.compare_digest(supplied, server._secret):
                    self._answer(401, {"error": "unknown session"})
                    return
                try:
                    body = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    self._answer(400, {"error": "request body is not JSON"})
                    return
                if not isinstance(body, dict):
                    self._answer(400, {"error": "request body must be an object"})
                    return
                self._answer(200, server.route(self.path, body))

        self._server = _UnixHTTPServer(str(self.socket_path), Handler)
        os.chmod(self.socket_path, 0o600)
        threading.Thread(
            target=self._server.serve_forever, name="nunchi-turn-server", daemon=True
        ).start()

    def route(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        participant = self.participant
        path = _ALIASES.get(path, path)
        turn_id = _text(body.get("turn_id"))
        if path == "/v1/attach":
            return {
                "protocol": PROTOCOL,
                "version": VERSION,
                "posting": "tools" if participant.silence_marker is None else "final-answer",
                "silence_marker": participant.silence_marker,
                "tools": participant.attach(),
            }
        if path == "/v1/turn/bind":
            if turn_id is None:
                return {"bound": False}
            return {
                "bound": participant.bind_turn(
                    turn_id=turn_id, wake_id=_text(body.get("wake_id"))
                )
            }
        if path == "/v1/turn/call":
            tool = body.get("tool")
            if not isinstance(tool, str):
                return {"ok": False, "error": "The tool name is missing."}
            ok, text = participant.call_tool(
                turn_id=turn_id, tool=tool, arguments=body.get("input", {})
            )
            return {"ok": True, "text": text} if ok else {"ok": False, "error": text}
        if path == "/v1/turn/after-tool":
            return {"text": participant.news(turn_id=turn_id)}
        if path == "/v1/turn/finish":
            answer = body.get("answer")
            if participant.silence_marker is None:
                return {"error": "this participant posts through tools"}
            decision = participant.finish(
                turn_id=turn_id, answer=answer if isinstance(answer, str) else None
            )
            return {"finish": decision.kind, "text": decision.text}
        if path == "/v1/turn/end":
            ok = body.get("ok")
            detail = body.get("detail")
            note = body.get("note")
            return {
                "ended": participant.end_turn(
                    turn_id=turn_id,
                    ok=ok is True,
                    detail=detail if isinstance(detail, str) else "",
                    note=note if isinstance(note, str) else None,
                )
            }
        return {"error": f"unknown path {path}"}

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
