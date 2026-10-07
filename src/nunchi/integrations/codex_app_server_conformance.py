"""The Codex app-server integration under the turn conformance kit (#94 step 9e).

Each scenario runs a real `codex app-server` (a clean, pinned install; see
`.github/workflows/ci.yml`) with a throwaway ``HOME``, ``CODEX_HOME`` and
``TMPDIR``, a git working directory, and the integration exactly as it runs in
a room: its thread, its per-thread MCP server (`mcp_bridge.py`), its socket.
Only the model is scripted: a Responses API endpoint on localhost, configured
as the throwaway user's Codex model provider, answers each of the agent's
model calls with the scripted agent's next step.

So the script reaches its turn as a model would:

- ``bind`` checks that the integration bound the run when Codex started it;
- ``call`` is a function call the model makes to a room tool, in the
  ``mcp__nunchi_room`` namespace; what the agent is told comes back in Codex's
  next model request, and whether it succeeded in Codex's ``item/completed``;
- ``after_tool`` is the room's news that came with that result;
- ``end`` is the model's final answer, after which Codex ends the turn.

An unbound run, through Codex, is a run that never had the room tools: the
integration only binds a run when the thread's room server is ready. A script
without a ``bind`` step therefore runs with the throwaway user's own Codex
config disabling an MCP server of the room server's name, and the integration
must fail the turn rather than call it silence.
"""

from __future__ import annotations

from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any

from ..attention import ParticipantProfile
from ..turn import SecretGuard
from ..turn_conformance import ScriptedAgent
from .codex_app_server.integration import (
    MCP_SERVER_NAME,
    TOOL_NAMES,
    CodexRoomIntegration,
    CodexSettings,
)

CODEX_BIN_ENV = "NUNCHI_CODEX_BIN"
NAMESPACE = f"mcp__{MCP_SERVER_NAME}"
_STEP_SECONDS = 20.0
_FINAL = "Nothing to add."
# The throwaway user's own config, when the run must not get the room tools.
_ROOM_SERVER_DISABLED = f"""
[mcp_servers.{MCP_SERVER_NAME}]
command = "true"
enabled = false
"""


def codex_executable() -> str | None:
    """The pinned Codex to run: ``NUNCHI_CODEX_BIN``, else ``codex`` on PATH."""

    configured = os.environ.get(CODEX_BIN_ENV)
    if configured:
        return configured if os.access(configured, os.X_OK) else None
    return shutil.which("codex")


def codex_available() -> bool:
    return codex_executable() is not None


def throwaway_environment(base: Path) -> dict[str, str]:
    """Every Codex process gets its own HOME, CODEX_HOME and TMPDIR under ``base``."""

    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(base / "home"),
        "CODEX_HOME": str(base / "codex-home"),
        "TMPDIR": str(base / "tmp"),
    }
    for key in ("HOME", "CODEX_HOME", "TMPDIR"):
        Path(environment[key]).mkdir(parents=True, exist_ok=True)
    return environment


_VERSION: dict[str, str] = {}


def codex_version() -> str:
    """``codex --version`` of the pinned install, run in a throwaway home."""

    executable = codex_executable()
    if executable is None:
        return "not installed"
    if executable not in _VERSION:
        base = Path(tempfile.mkdtemp(prefix="nunchi-codex-version-"))
        try:
            done = subprocess.run(
                [executable, "--version"],
                env=throwaway_environment(base),
                cwd=str(base),
                capture_output=True,
                text=True,
                timeout=60,
            )
            _VERSION[executable] = (done.stdout.strip() or done.stderr.strip() or "unknown").splitlines()[-1]
        except (OSError, subprocess.SubprocessError):
            _VERSION[executable] = "unknown"
        finally:
            shutil.rmtree(base, ignore_errors=True)
    return _VERSION[executable]


# -- the model: the only scripted part -----------------------------------------------


class ScriptedModel:
    """A Responses API endpoint whose answers the scripted agent supplies.

    Only the agent's own model calls (those that offer the room tools) are
    scripted; anything else Codex asks gets a short fixed answer. Codex makes
    one model call at a time per thread, so a reply goes to the newest call:
    an older one still open belongs to a run Codex abandoned (interrupted, or a
    process that died) and gets an empty answer.
    """

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.other_requests: list[dict[str, Any]] = []
        self.on_request: Any = None
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        # The newest open call's answer slot, and replies given before any call.
        self._open: dict[str, Any] | None = None
        self._early: list[dict[str, Any]] = []
        self._closed = False
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="nunchi-kit-codex-model", daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def provider_config(self, user_config: str = "") -> str:
        """The throwaway user's Codex config: this endpoint as the model provider.

        ``user_config`` is the rest of the user's own settings; its top-level
        keys come before any table.
        """

        return f"""
model = "conformance-model"
model_provider = "conformance"
{user_config}

[model_providers.conformance]
name = "Conformance"
base_url = "{self.base_url}"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
supports_websockets = false
"""

    def reply(self, reply: Mapping[str, Any]) -> None:
        with self._changed:
            if self._open is not None and self._open["reply"] is None:
                self._open["reply"] = dict(reply)
                self._changed.notify_all()
            else:
                self._early.append(dict(reply))

    def count(self) -> int:
        with self._lock:
            return len(self.requests)

    def latest(self) -> dict[str, Any]:
        with self._lock:
            return self.requests[-1]

    def close(self) -> None:
        with self._changed:
            self._closed = True
            self._changed.notify_all()
        self._server.shutdown()
        self._server.server_close()

    @staticmethod
    def is_agent(request: Mapping[str, Any]) -> bool:
        return any(
            isinstance(tool, Mapping) and tool.get("type") == "namespace" and tool.get("name") == NAMESPACE
            for tool in request.get("tools", ())
        )

    def _answer(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not self.is_agent(request):
            with self._lock:
                self.other_requests.append(dict(request))
            return {"text": "Room"}
        slot: dict[str, Any] = {"reply": None}
        with self._changed:
            self.requests.append(dict(request))
            superseded = self._open
            if superseded is not None and superseded["reply"] is None:
                superseded["reply"] = {"text": ""}
            self._open = slot
            if self._early:
                slot["reply"] = self._early.pop(0)
            self._changed.notify_all()
        if self.on_request is not None:
            self.on_request()
        deadline = time.monotonic() + _STEP_SECONDS * 3
        with self._changed:
            while slot["reply"] is None and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._changed.wait(remaining)
            if self._open is slot:
                self._open = None
            return slot["reply"] or {"text": ""}

    def _handler(self):
        model = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                pass

            def _send(self, status: int, content_type: str, payload: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                self._send(200, "application/json", json.dumps({"object": "list", "data": []}).encode())

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    request = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    request = {}
                if not self.path.endswith("/responses") or not isinstance(request, dict):
                    self._send(404, "application/json", b"{}")
                    return
                reply = model._answer(request)
                response_id = f"resp-{secrets.token_hex(4)}"
                if "tool" in reply:
                    item: dict[str, Any] = {
                        "type": "function_call",
                        "call_id": reply["call_id"],
                        "name": reply["tool"],
                        "arguments": json.dumps(reply.get("arguments", {})),
                    }
                    # Room tools are in the room server's namespace; Codex's own are not.
                    namespace = reply.get("namespace", NAMESPACE)
                    if namespace:
                        item["namespace"] = namespace
                else:
                    item = {
                        "type": "message",
                        "role": "assistant",
                        "id": f"msg-{secrets.token_hex(4)}",
                        "content": [{"type": "output_text", "text": reply.get("text", "")}],
                    }
                events = [
                    {"type": "response.created", "response": {"id": response_id}},
                    {"type": "response.output_item.done", "item": item},
                    {
                        "type": "response.completed",
                        "response": {
                            "id": response_id,
                            "usage": {
                                "input_tokens": 10,
                                "input_tokens_details": None,
                                "output_tokens": 5,
                                "output_tokens_details": None,
                                "total_tokens": 15,
                            },
                        },
                    },
                ]
                payload = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
                try:
                    self._send(200, "text/event-stream", payload.encode())
                except OSError:
                    pass  # Codex stopped waiting, for example after an interrupt

        return Handler


# -- a real app-server in a throwaway home -----------------------------------------------


class CodexHarness:
    """The integration with a real `codex app-server`, a throwaway user and a scripted model."""

    def __init__(
        self,
        *,
        profile: ParticipantProfile,
        guard: SecretGuard,
        user_config: str = "",
        project_trust_level: str = "trusted",
        roles: tuple[str, ...] = ("send", "react", "context"),
        result_wait_seconds: float = 5.0,
        resume_thread: bool = False,
    ) -> None:
        executable = codex_executable()
        if executable is None:
            raise RuntimeError(f"Codex is not installed; set {CODEX_BIN_ENV} to a pinned codex")
        # Short names: the socket path must fit a Unix socket address.
        self.base = Path(tempfile.mkdtemp(prefix="nck-"))
        self.environment = throwaway_environment(self.base)
        self.codex_home = Path(self.environment["CODEX_HOME"])
        self.work = self.base / "work"
        self.work.mkdir()
        # A git checkout: the case in which Codex would write trust (contract, gap 5).
        subprocess.run(["git", "init", "-q", str(self.work)], check=True, env=self.environment)
        self.model = ScriptedModel()
        self.user_config = self.model.provider_config(user_config)
        (self.codex_home / "config.toml").write_text(self.user_config, encoding="utf-8")
        self.integration = CodexRoomIntegration(
            profile=profile,
            guard=guard,
            settings=CodexSettings(
                working_directory=self.work,
                project_trust_level=project_trust_level,
                executable=executable,
                resume_thread=resume_thread,
            ),
            environment=self.environment,
            runtime_directory=self.base / "r",
            roles=roles,
            result_wait_seconds=result_wait_seconds,
            thread_store=self.base / "state" / "codex-thread.json",
        )

    def user_config_unchanged(self) -> bool:
        return (self.codex_home / "config.toml").read_text(encoding="utf-8") == self.user_config

    def close(self) -> None:
        try:
            self.integration.close()
        finally:
            self.model.close()
            shutil.rmtree(self.base, ignore_errors=True)


# -- the scripted agent's surface: Codex's real I/O --------------------------------------------


def _output_text(request: Mapping[str, Any], call_id: str) -> str | None:
    """What Codex told the model a tool call returned, without Codex's own header."""

    for item in request.get("input", ()):
        if not isinstance(item, Mapping) or item.get("type") != "function_call_output":
            continue
        if item.get("call_id") != call_id:
            continue
        output = item.get("output")
        if isinstance(output, str):
            parts = [output]
        else:
            parts = [part.get("text", "") for part in output or () if isinstance(part, Mapping)]
        parts = [part for part in parts if not part.startswith("Wall time:")]
        return "\n".join(parts)
    return None


def _input_text(request: Mapping[str, Any]) -> str:
    """The newest user message Codex gave the model: the turn's text."""

    for item in reversed(request.get("input", ())):
        if isinstance(item, Mapping) and item.get("type", "message") == "message" and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, str):
                return content
            return "\n".join(part.get("text", "") for part in content or () if isinstance(part, Mapping))
    return ""


class CodexSurface:
    """One turn, as the model inside a real Codex run reaches it."""

    def __init__(self, harness: CodexHarness, turn: Any) -> None:
        self.harness = harness
        self.turn = turn
        self.news: str | None = None
        # Made at the turn's first model request: what Codex gave the model.
        self.shown = _input_text(harness.model.latest())

    @property
    def codex_turn(self) -> str | None:
        return self.turn.turn_id if self.turn is not None else None

    def _ended(self) -> bool:
        codex_turn = self.codex_turn
        return codex_turn is not None and codex_turn in self.harness.integration.completed_turns

    def bind(self, turn_id: str) -> bool:
        # The integration binds when Codex answers turn/start, before the model
        # is asked; the script starts when the model is first asked.
        deadline = time.monotonic() + _STEP_SECONDS
        while self.codex_turn is None and time.monotonic() < deadline:
            time.sleep(0.02)
        return self.codex_turn is not None

    def read(self, turn_id: str) -> str:
        return self.shown

    def call(self, turn_id: str, role: str, arguments: Mapping[str, Any]) -> tuple[bool, str]:
        model = self.harness.model
        before = model.count()
        call_id = f"call-{secrets.token_hex(6)}"
        model.reply({"tool": TOOL_NAMES.get(role, role), "arguments": dict(arguments), "call_id": call_id})
        deadline = time.monotonic() + _STEP_SECONDS
        while model.count() <= before:
            if self._ended() or time.monotonic() >= deadline:
                return False, "Codex ended the turn before the tool call ran"
            time.sleep(0.02)
        text = _output_text(model.latest(), call_id)
        if text is None:
            return False, "Codex did not return the tool's result to the model"
        # Codex's own account of the call: failed when the room refused it.
        while call_id not in self.harness.integration.tool_items and time.monotonic() < deadline:
            time.sleep(0.02)
        item = self.harness.integration.tool_items.get(call_id, {})
        content, marker, update = text.partition("\n\nRoom update:")
        self.news = "Room update:" + update if marker else None
        return item.get("status") == "completed", content

    def after_tool(self, turn_id: str) -> str | None:
        # The bridge adds the room's news to the tool's result, at the tool call.
        news, self.news = self.news, None
        return news

    def finish(self, turn_id: str, answer: str) -> tuple[str, str]:
        raise NotImplementedError("Codex posts through room tools")

    def end(self, turn_id: str, ok: bool, note: str | None = None) -> None:
        if not self._ended():
            # The model's final message: the agent's last words.
            self.harness.model.reply({"text": note or _FINAL})
        deadline = time.monotonic() + _STEP_SECONDS
        while time.monotonic() < deadline:
            if self._ended() and self.harness.integration.participant.active is not self.turn:
                return
            time.sleep(0.02)


# -- the kit's integration ------------------------------------------------------------------------


class CodexKitIntegration:
    posting = "tools"

    def __init__(self) -> None:
        self.name = f"Codex app-server ({codex_version()})"
        self.harness: CodexHarness | None = None

    def participant(
        self, *, profile: ParticipantProfile, guard: SecretGuard, agent: ScriptedAgent, privileged: bool = False
    ) -> Any:
        # An unbound run is one without the room tools (see the module docstring).
        unbound = not any(step[0] == "bind" for step in agent.steps)
        roles = ("send", "react", "context")
        self.harness = harness = CodexHarness(
            profile=profile,
            guard=guard,
            user_config=_ROOM_SERVER_DISABLED if unbound else "",
            roles=(*roles, "propose", "withdraw") if privileged else roles,
        )

        def first_request() -> None:
            # Codex asked the model for the first time in a turn: that turn's script starts.
            turn = harness.integration.participant.active
            if turn is not None:
                agent.play_once(turn, lambda: CodexSurface(harness, turn))

        harness.model.on_request = first_request
        return harness.integration.participant

    def close(self) -> None:
        if self.harness is not None:
            self.harness.close()
            self.harness = None


def conformance_integrations() -> list[CodexKitIntegration]:
    return [CodexKitIntegration()]


__all__ = [
    "CODEX_BIN_ENV",
    "CodexHarness",
    "CodexKitIntegration",
    "CodexSurface",
    "ScriptedModel",
    "codex_available",
    "codex_executable",
    "codex_version",
    "conformance_integrations",
    "throwaway_environment",
]
