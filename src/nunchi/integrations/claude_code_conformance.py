"""The Claude Code gate under the turn conformance kit (#94 step 9d).

The scripted agent plays each turn the way the mod does: it reads the wake
marker from the turn the gate wrote to the session, binds, calls the room
tools, and asks for steering over the gate's private socket with the launch
secret. The session's end of turn reaches the gate as it does from
stream-json. Only the model and the session process are scripted.
"""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import re
import secrets
import shutil
import socket
import tempfile
import threading
from typing import Any, Mapping

from ..attention import ParticipantProfile
from ..turn import SecretGuard as CoreSecretGuard
from ..turn_conformance import ScriptedAgent
from .claude_code_gate import WAKE_MARKER, GatedParticipant, GateServer, full_tool_name

_WAKE = re.compile("^" + re.escape(WAKE_MARKER).replace(r"\{\}", "([A-Za-z0-9_-]+)"))


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str) -> None:
        super().__init__("localhost", timeout=30)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


class _SocketSurface:
    """What the mod sends: the gate's routes, with the launch secret."""

    def __init__(
        self, socket_path: Path, secret: str, wake_id: str, session: "_ScriptedSession", text: str
    ) -> None:
        self.socket_path = socket_path
        self.secret = secret
        self.wake_id = wake_id
        self.session = session
        self.text = text

    def _post(self, route: str, body: Mapping[str, Any]) -> dict[str, Any]:
        connection = _UnixConnection(str(self.socket_path))
        try:
            connection.request(
                "POST",
                route,
                json.dumps(body),
                {"Content-Type": "application/json", "X-Nunchi-Session": self.secret},
            )
            return json.loads(connection.getresponse().read())
        finally:
            connection.close()

    def bind(self, turn_id: str) -> bool:
        return bool(self._post("/v1/turn-start", {"turn_id": turn_id, "wake_id": self.wake_id}).get("bound"))

    def read(self, turn_id: str) -> str:
        # What the gate wrote to the session.
        return self.text

    def call(self, turn_id: str, role: str, arguments: Mapping[str, Any]) -> tuple[bool, str]:
        answer = self._post("/v1/tool", {"turn_id": turn_id, "tool": full_tool_name(role), "input": dict(arguments)})
        return (True, answer["text"]) if answer.get("ok") else (False, answer.get("error", ""))

    def after_tool(self, turn_id: str) -> str | None:
        return self._post("/v1/news", {"turn_id": turn_id}).get("text")

    def finish(self, turn_id: str, answer: str) -> tuple[str, str]:
        raise NotImplementedError("Claude Code posts through room tools")

    def end(self, turn_id: str, ok: bool, note: str | None = None) -> None:
        # Claude Code reports the end of its turn on stream-json, not the
        # socket, with its final message as the result.
        self.session.ended(ok, note)


class _ScriptedSession:
    """Stands in for the `claude -p` process: the scripted agent is its model."""

    def __init__(self, agent: ScriptedAgent, socket_path: Path, secret: str) -> None:
        self.agent = agent
        self.socket_path = socket_path
        self.secret = secret
        self.on_turn_end: Any = None

    def wait_idle(self, cancel: threading.Event) -> bool:
        return not cancel.is_set()

    def submit(self, text: str) -> None:
        match = _WAKE.match(text)
        if match is None:
            raise AssertionError("the gate's turn does not start with its wake marker")
        self.agent.play(_SocketSurface(self.socket_path, self.secret, match.group(1), self, text))

    def interrupt(self) -> None:
        pass

    def ended(self, ok: bool, note: str | None = None) -> None:
        self.on_turn_end(ok=ok, detail="success" if ok else "error_during_execution", note=note)


class ClaudeCodeKitIntegration:
    name = "Claude Code gate"
    posting = "tools"

    def __init__(self) -> None:
        self._directory: str | None = None
        self._server: GateServer | None = None
        # The session's launch secret: the agent can read it in its environment.
        self.launch_secret: str | None = None

    def participant(
        self, *, profile: ParticipantProfile, guard: CoreSecretGuard, agent: ScriptedAgent, privileged: bool = False
    ) -> Any:
        self._directory = tempfile.mkdtemp(prefix="ncc-kit-")
        socket_path = Path(self._directory) / "gate.sock"
        secret = secrets.token_urlsafe(24)
        session = _ScriptedSession(agent, socket_path, secret)
        participant = GatedParticipant(
            profile=profile,
            session=session,
            guard=guard,  # the kit's guard: its withheld values
            privileged_enabled=privileged,
            result_wait_seconds=5,
        )
        session.on_turn_end = participant.turn_ended
        self._server = GateServer(participant, socket_path=socket_path, session_secret=secret)
        self._server.start()
        participant.attach()
        self.launch_secret = secret
        return participant

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._directory is not None:
            shutil.rmtree(self._directory, ignore_errors=True)
            self._directory = None


def conformance_integrations() -> list[ClaudeCodeKitIntegration]:
    return [ClaudeCodeKitIntegration()]
