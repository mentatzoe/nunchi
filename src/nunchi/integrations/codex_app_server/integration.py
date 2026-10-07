"""Nunchi in Codex through `codex app-server`: library-hosted, tool posting (#94 step 9e).

Built from `docs/harness-guide.md`, on the app-server's public JSON-RPC
protocol only. Nothing in Codex is patched, and the user's Codex configuration
is never written.

How a turn goes:

1. **Thread.** On the first turn the integration starts `codex app-server` with
   the user's own Codex home and starts one thread in the configured working
   directory. The thread's own ``config`` adds one MCP server, the room tools
   (`mcp_bridge.py`), on top of the user's servers, and the project's trust
   level, so Codex does not write trust into the user's config (contract,
   gap 5). Model, sandbox, approvals, instructions, tools and skills stay the
   user's.
2. **Start.** The library calls `start`; the integration sends ``turn/start``
   with the turn's text. Codex answers with the turn's id, and the integration
   binds that run to the wake: Codex itself says the run started with this
   text, and the thread's room tools are ready. The wake id never reaches the
   agent.
3. **Room tools.** Codex calls the bridge; the bridge calls this integration's
   socket (`nunchi.turn_server`, restricted to attach, call and after-tool)
   with the Codex turn id from the call's ``_meta``. The library's answer, and
   the room's news, go back as the tool's result.
4. **Steering.** After every other tool call in a bound run (commands, file
   changes, other MCP servers), the room's news goes to the running turn with
   ``turn/steer``.
5. **End.** ``turn/completed`` reports the run's end: ``completed`` is ok;
   ``interrupted`` and ``failed`` are not.
6. **Cancel.** ``interrupt`` sends ``turn/interrupt``.

Approval requests are declined: nobody is at the terminal, so whatever the
user's own rules would ask a person about does not run (contract, "Native tool
approvals"). The integration decides nothing about whether or what the agent
says.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
from typing import Any

from nunchi import __version__
from nunchi.errors import ValidationError
from nunchi.turn import DEFAULT_RESULT_WAIT_SECONDS, SecretGuard, Turn, TurnParticipant
from nunchi.turn_server import TurnServer

from . import mcp_bridge
from .client import AppServer, CodexAppServerError, RequestRefused, ServerRequestError

logger = logging.getLogger("nunchi.codex_app_server")

SECTION = "codex"
# The room's MCP server in the thread's config; the model sees its tools in the
# ``mcp__nunchi_room`` namespace.
MCP_SERVER_NAME = "nunchi_room"
TOOL_NAMES = {
    "send": "room_send",
    "react": "room_react",
    "context": "room_context",
    "propose": "room_propose",
    "withdraw": "room_withdraw",
}
TRUST_LEVELS = ("trusted", "untrusted")
BRIDGE_PATH = Path(mcp_bridge.__file__).resolve()
# Platform credentials Nunchi holds that the agent must never see or post.
DEFAULT_WITHHELD_ENV = ("DISCORD_BOT_TOKEN",)
TOKEN_PATTERNS = (
    # A Discord bot token: three dot-separated base64url parts.
    re.compile(r"[A-Za-z\d_-]{23,28}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"),
)
# Completed items that are not tool calls: no steering after them.
_NOT_TOOL_ITEMS = frozenset(
    {
        "userMessage",
        "hookPrompt",
        "agentMessage",
        "plan",
        "reasoning",
        "enteredReviewMode",
        "exitedReviewMode",
        "contextCompaction",
        "subAgentActivity",
    }
)
# Streams the integration never reads.
_QUIET = [
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/summaryPartAdded",
    "item/reasoning/textDelta",
    "item/commandExecution/outputDelta",
    "item/fileChange/outputDelta",
    "command/exec/outputDelta",
    "thread/tokenUsage/updated",
    "account/rateLimits/updated",
]
_REQUEST_SECONDS = 60.0
_ROOM_TOOLS_WAIT_SECONDS = 5.0
_START_WAIT_SECONDS = 15.0
_INTERRUPT_GRACE_SECONDS = 15.0
_ROOM_ROUTES = frozenset({"/v1/attach", "/v1/turn/call", "/v1/turn/after-tool"})
# The longest Unix socket path the platform binds (sun_path, without its NUL).
_MAX_SOCKET_PATH = 103 if sys.platform == "darwin" else 107
_DECLINED = "Nobody is at the terminal in a Nunchi room, so this was declined."
# How many of Codex's recent turns and tool calls to remember.
_RECENT = 256


class CodexIntegrationError(RuntimeError):
    """Codex could not take the turn. An operational failure, never silence."""


@dataclass(frozen=True)
class CodexSettings:
    """The integration's own config section, ``codex``.

    ``project_trust_level`` is passed in the thread's own config for the
    working directory when the user's Codex config has no trust decision for
    it, so Codex never writes one (contract, gap 5). The user's own decision,
    when there is one, stands.
    """

    working_directory: Path
    project_trust_level: str
    executable: str | None = None
    withheld_env: tuple[str, ...] = DEFAULT_WITHHELD_ENV
    resume_thread: bool = True
    start_timeout_seconds: float = 120.0

    @classmethod
    def from_section(cls, section: Any) -> "CodexSettings":
        if not isinstance(section, Mapping):
            raise ValueError("the codex section must be an object")
        allowed = {
            "executable",
            "working_directory",
            "project_trust_level",
            "withheld_env",
            "resume_thread",
            "start_timeout_seconds",
        }
        unknown = set(section) - allowed
        if unknown:
            raise ValueError(f"the codex section has unknown keys: {sorted(unknown)}")
        directory = section.get("working_directory")
        if not isinstance(directory, str) or not os.path.isabs(directory):
            raise ValueError("codex.working_directory must be an absolute path")
        trust = section.get("project_trust_level")
        if trust not in TRUST_LEVELS:
            raise ValueError("codex.project_trust_level must be 'trusted' or 'untrusted'")
        executable = section.get("executable")
        if executable is not None and (not isinstance(executable, str) or not executable):
            raise ValueError("codex.executable must be a path or null")
        withheld = section.get("withheld_env", DEFAULT_WITHHELD_ENV)
        if not isinstance(withheld, (list, tuple)) or not all(isinstance(name, str) for name in withheld):
            raise ValueError("codex.withheld_env must be a list of variable names")
        resume = section.get("resume_thread", True)
        if not isinstance(resume, bool):
            raise ValueError("codex.resume_thread must be true or false")
        timeout = section.get("start_timeout_seconds", 120.0)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("codex.start_timeout_seconds must be a positive number")
        return cls(
            working_directory=Path(directory),
            project_trust_level=trust,
            executable=executable,
            withheld_env=tuple(withheld),
            resume_thread=resume,
            start_timeout_seconds=float(timeout),
        )

    def resolve_executable(self, environment: Mapping[str, str]) -> str:
        if self.executable is not None:
            return self.executable
        found = shutil.which("codex", path=environment.get("PATH"))
        if found is None:
            raise CodexIntegrationError("the codex executable is not on PATH; set codex.executable")
        return found


def agent_environment(environ: Mapping[str, str], withheld: Iterable[str]) -> dict[str, str]:
    """The app-server's environment: the user's own, without what Nunchi withholds.

    Nunchi's own variables (``NUNCHI_*``) never reach the agent either.
    """

    names = set(withheld)
    return {
        key: value for key, value in environ.items() if key not in names and not key.startswith("NUNCHI_")
    }


def withheld_names(codex: "CodexSettings", attention_model: Mapping[str, Any] | None) -> list[str]:
    """What the agent must not see: the codex section's names and the attention model's keys.

    An attention route names its credential variables in ``*_env`` keys.
    """

    names = list(codex.withheld_env)
    if isinstance(attention_model, Mapping):
        names += [
            value
            for key, value in attention_model.items()
            if key.endswith("_env") and isinstance(value, str) and value
        ]
    return list(dict.fromkeys(names))


def runtime_directory() -> Path:
    """A short private directory for the room socket: Unix socket paths are short."""

    candidates = (os.environ.get("XDG_RUNTIME_DIR"), tempfile.gettempdir(), "/tmp")
    base = next(
        (path for path in candidates if path and len(path) <= 60 and os.path.isdir(path)),
        tempfile.gettempdir(),
    )
    return Path(base) / f"nunchi-codex-{secrets.token_hex(6)}"


def withheld_values(environ: Mapping[str, str], withheld: Iterable[str]) -> list[str]:
    return [value for name in withheld if (value := environ.get(name))]


def project_keys(directory: Path) -> list[str]:
    """Where Codex looks for a project's trust: the directory, then its repository root."""

    keys: list[str] = []
    candidates = [directory]
    root = next((parent for parent in (directory, *directory.parents) if (parent / ".git").exists()), None)
    if root is not None:
        candidates.append(root)
    for path in candidates:
        for key in (os.path.realpath(path), str(path)):
            if key not in keys:
                keys.append(key)
    return keys


class RoomToolServer(TurnServer):
    """The bridge's only way in: attach, call and after-tool, over a private socket.

    The integration binds and ends turns itself, so those routes are not
    offered. A call that races the turn's start waits until it is bound.
    """

    def __init__(self, integration: "CodexRoomIntegration", *, socket_path: Path, session_secret: str) -> None:
        super().__init__(integration.participant, socket_path=socket_path, session_secret=session_secret)
        self.integration = integration

    def route(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if path not in _ROOM_ROUTES:
            return {"error": f"{path} is not offered to the room tools"}
        if path != "/v1/attach":
            self.integration.wait_for_start()
        return super().route(path, body)


class CodexRoomIntegration:
    """One participant's Codex thread: the turn driver and the app-server's events.

    The library's side is `participant` (a `TurnParticipant` with this object
    as its driver) inside a `Room` the caller builds. ``environment`` is the
    app-server's whole environment: the user's own, without Nunchi's secrets.
    ``runtime_directory`` holds the private socket and is created ``0700``.
    """

    def __init__(
        self,
        *,
        profile: Any,
        guard: SecretGuard,
        settings: CodexSettings,
        environment: Mapping[str, str],
        runtime_directory: Path,
        roles: Iterable[str] = ("send", "react", "context"),
        result_wait_seconds: float = DEFAULT_RESULT_WAIT_SECONDS,
        thread_store: Path | None = None,
    ) -> None:
        self.settings = settings
        self.environment = dict(environment)
        self.runtime_directory = runtime_directory
        self.thread_store = thread_store if settings.resume_thread else None
        self.participant = TurnParticipant(
            profile=profile,
            driver=self,
            guard=guard,
            tool_names=TOOL_NAMES,
            roles=tuple(roles),
            result_wait_seconds=result_wait_seconds,
        )
        self._secret = secrets.token_urlsafe(32)
        socket_path = runtime_directory / "room.sock"
        if len(os.fsencode(str(socket_path))) > _MAX_SOCKET_PATH:
            raise ValueError(
                f"the runtime directory {runtime_directory} is too deep for a Unix socket; "
                f"its socket path must be at most {_MAX_SOCKET_PATH} bytes"
            )
        self.server = RoomToolServer(self, socket_path=socket_path, session_secret=self._secret)
        self._lock = threading.RLock()
        self._thread_lock = threading.Lock()
        self._app: AppServer | None = None
        self._thread_id: str | None = None
        self._serving = False
        self._closed = False
        # MCP startup status by (thread id, server name).
        self._mcp_status: dict[tuple[str, str], str] = {}
        self._mcp_changed = threading.Condition(self._lock)
        # The Codex turn running now, whoever started it.
        self._codex_turn: str | None = None
        # Turns Codex announced as started (read in order, for the steer check).
        self._started: dict[str, None] = {}
        # The library's turn, the Codex turn bound to it, and its app-server's generation.
        self._bound: tuple[Turn, str, int] | None = None
        # Each app-server process is a generation; a late event from an old one
        # never touches the current one's state.
        self._generation = 0
        self._starting = threading.Event()
        self._starting.set()
        self._steering: "queue.Queue[str | None]" = queue.Queue()
        self._steerer: threading.Thread | None = None
        # What Codex reported, for diagnostics and the conformance kit.
        self.completed_turns: dict[str, Mapping[str, Any]] = {}
        self.tool_items: dict[str, Mapping[str, Any]] = {}
        # The agent's newest message in each run: its last words.
        self._last_words: dict[str, str] = {}
        self.steered: list[tuple[str, str]] = []
        self.declined: list[str] = []
        self.warnings: list[str] = []

    # -- lifecycle -------------------------------------------------------------------

    @property
    def thread_id(self) -> str | None:
        return self._thread_id

    def _serve(self) -> None:
        with self._lock:
            if self._serving:
                return
            self.runtime_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.runtime_directory, 0o700)
            self.server.start()
            self._serving = True
            self._steerer = threading.Thread(target=self._steer_loop, name="nunchi-codex-steer", daemon=True)
            self._steerer.start()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            app, self._app = self._app, None
            serving, self._serving = self._serving, False
        if app is not None:
            app.stop()
        self._steering.put(None)
        if serving:
            self.server.close()
            try:
                self.runtime_directory.rmdir()
            except OSError:
                pass

    def thread_config(self, trust_level: str | None) -> dict[str, Any]:
        """The thread's own ``config``: the room's MCP server, and the project's trust."""

        server = {
            "command": sys.executable,
            "args": ["-I", str(BRIDGE_PATH)],
            "env": {
                mcp_bridge.SOCKET_ENV: str(self.server.socket_path),
                mcp_bridge.SECRET_ENV: self._secret,
            },
            "cwd": str(self.runtime_directory),
            # Without the room tools the thread does not start at all.
            "required": True,
            # The library's own rules govern the room tools; nobody approves them.
            "default_tools_approval_mode": "approve",
            "startup_timeout_sec": 30,
            "tool_timeout_sec": 120,
        }
        config: dict[str, Any] = {"mcp_servers": {MCP_SERVER_NAME: server}}
        if trust_level is not None:
            key = os.path.realpath(self.settings.working_directory)
            config["projects"] = {key: {"trust_level": trust_level}}
        return config

    def _start_app(self) -> AppServer:
        executable = self.settings.resolve_executable(self.environment)
        directory = self.settings.working_directory
        if not directory.is_dir():
            raise CodexIntegrationError(f"the working directory {directory} does not exist")
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._mcp_status.clear()

        def current() -> bool:
            return self._generation == generation

        def on_read(method: str, params: Mapping[str, Any]) -> None:
            if current():
                self._on_read(method, params)

        def on_notification(method: str, params: Mapping[str, Any]) -> None:
            if current():
                self._on_notification(method, params)

        app = AppServer(
            executable=executable,
            environment=self.environment,
            working_directory=str(directory),
            on_notification=on_notification,
            on_request=self._on_server_request,
            on_exit=lambda returncode: self._on_exit(generation, returncode),
            on_read=on_read,
        )
        app.start()
        try:
            app.request(
                "initialize",
                {
                    "clientInfo": {"name": "nunchi", "title": "Nunchi", "version": __version__},
                    "capabilities": {"experimentalApi": False, "optOutNotificationMethods": list(_QUIET)},
                },
                timeout=_REQUEST_SECONDS,
            )
            app.notify("initialized")
        except CodexAppServerError:
            app.stop()
            raise
        return app

    def _user_trust(self, app: AppServer) -> str | None:
        """The user's own trust decision for the working directory, if any (read only)."""

        directory = self.settings.working_directory
        result = app.request("config/read", {"cwd": str(directory)}, timeout=_REQUEST_SECONDS)
        config = result.get("config") if isinstance(result, Mapping) else None
        projects = config.get("projects") if isinstance(config, Mapping) else None
        if not isinstance(projects, Mapping):
            return None
        for key in project_keys(directory):
            entry = projects.get(key)
            if isinstance(entry, Mapping) and entry.get("trust_level") in TRUST_LEVELS:
                return str(entry["trust_level"])
        return None

    def _stored_thread(self) -> str | None:
        if self.thread_store is None:
            return None
        try:
            stored = json.loads(self.thread_store.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = stored.get("thread_id") if isinstance(stored, dict) else None
        return value if isinstance(value, str) and value else None

    def _store_thread(self, thread_id: str) -> None:
        if self.thread_store is None:
            return
        self.thread_store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.thread_store.with_name(f".{self.thread_store.name}.{secrets.token_hex(6)}.tmp")
        temporary.write_text(json.dumps({"thread_id": thread_id}), encoding="utf-8")
        os.replace(temporary, self.thread_store)

    def _ensure_thread(self) -> tuple[AppServer, str]:
        """The running app-server and the participant's thread, started or resumed if needed."""

        with self._thread_lock:
            with self._lock:
                if self._closed:
                    raise CodexIntegrationError("the Codex integration is closed")
                app, thread_id = self._app, self._thread_id
            if app is not None and app.alive and thread_id is not None:
                return app, thread_id
            self._serve()
            started: AppServer | None = None
            try:
                if app is None or not app.alive:
                    app = started = self._start_app()
                    with self._lock:
                        self._app = app
                trust = self._user_trust(app)
                config = self.thread_config(None if trust is not None else self.settings.project_trust_level)
                params = {"cwd": str(self.settings.working_directory), "config": config}
                timeout = self.settings.start_timeout_seconds
                thread = None
                with self._lock:
                    # The thread's room server must report ready for this load.
                    self._mcp_status.clear()
                stored = self._stored_thread()
                if stored is not None:
                    try:
                        thread = app.request("thread/resume", {"threadId": stored, **params}, timeout=timeout)
                    except RequestRefused as exc:
                        logger.warning("nunchi codex: could not resume thread %s: %s", stored, exc)
                if thread is None:
                    thread = app.request("thread/start", params, timeout=timeout)
                thread_id = str(thread["thread"]["id"])
            except (CodexAppServerError, KeyError, TypeError) as exc:
                if started is not None:
                    started.stop()
                    with self._lock:
                        if self._app is started:
                            self._app = None
                raise CodexIntegrationError(f"Codex could not start the room's thread: {exc}") from exc
            with self._lock:
                self._thread_id = thread_id
            self._store_thread(thread_id)
            return app, thread_id

    def _room_tools_ready(self, thread_id: str, cancel: threading.Event) -> bool:
        """Whether this thread's room MCP server is ready, after Codex had time to say so."""

        deadline = time.monotonic() + _ROOM_TOOLS_WAIT_SECONDS
        with self._mcp_changed:
            while True:
                status = self._mcp_status.get((thread_id, MCP_SERVER_NAME))
                if status == "ready":
                    return True
                remaining = deadline - time.monotonic()
                if status == "failed" or remaining <= 0 or cancel.is_set():
                    return False
                self._mcp_changed.wait(min(remaining, 0.1))

    # -- the driver (the library calls these) --------------------------------------------

    def ready(self, cancel: threading.Event) -> bool:
        """Start Codex and the thread if needed, then wait until no Codex turn runs."""

        app, thread_id = self._ensure_thread()
        if not self._room_tools_ready(thread_id, cancel):
            if cancel.is_set():
                return False
            raise CodexIntegrationError(
                f"the room tools did not reach Codex: the {MCP_SERVER_NAME} MCP server is not ready "
                "in this thread (is a server of that name disabled in the Codex config?)"
                + app.diagnostic_suffix()
            )
        waited = time.monotonic()
        interrupted = False
        while True:
            with self._lock:
                running = self._codex_turn
            if running is None:
                return not cancel.is_set()
            if cancel.is_set():
                return False
            if not interrupted and time.monotonic() - waited >= self.participant.previous_turn_grace_seconds:
                # A run that outlived its turn holds every later one.
                interrupted = True
                self._interrupt(app, thread_id, running)
            cancel.wait(0.05)

    def start(self, turn: Turn) -> None:
        """Start the agent's run with the turn's text, and bind it."""

        with self._lock:
            app, thread_id, generation = self._app, self._thread_id, self._generation
            started_before = set(self._started)
        if app is None or thread_id is None:
            raise CodexIntegrationError("Codex is not running")
        self._starting.clear()
        try:
            try:
                result = app.request(
                    "turn/start",
                    {"threadId": thread_id, "input": [{"type": "text", "text": turn.text, "text_elements": []}]},
                    timeout=_REQUEST_SECONDS,
                )
                codex_turn = str(result["turn"]["id"])
            except (CodexAppServerError, KeyError, TypeError) as exc:
                raise CodexIntegrationError(f"Codex did not start the turn: {exc}") from exc
            if codex_turn in started_before:
                # turn/start folded the text into a run already in progress.
                raise CodexIntegrationError("Codex added the turn to a run already in progress")
            with self._lock:
                # A quick run may have ended before this answer was read.
                done = self.completed_turns.get(codex_turn)
                if done is None:
                    self._codex_turn = codex_turn
                    self._bound = (turn, codex_turn, generation)
                # Codex says this run started with the turn's text, and the
                # thread's room tools are ready: the run is the wake's.
                bound = self.participant.bind_turn(turn_id=codex_turn, wake_id=turn.wake_id)
                if not bound and self._bound is not None and self._bound[1] == codex_turn:
                    self._bound = None
            if not bound:
                if done is None:
                    self._interrupt(app, thread_id, codex_turn)
                raise CodexIntegrationError("the Codex run could not be bound to its turn")
            if done is not None:
                ok, detail = _ending(done)
                self.participant.end_turn(turn_id=codex_turn, ok=ok, detail=detail)
        finally:
            self._starting.set()

    def interrupt(self, turn: Turn) -> None:
        with self._lock:
            app, thread_id = self._app, self._thread_id
            codex_turn = self._bound[1] if self._bound is not None and self._bound[0] is turn else None
        if app is None or thread_id is None:
            return
        # An empty turn id interrupts a turn Codex is still starting.
        threading.Thread(
            target=self._interrupt, args=(app, thread_id, codex_turn or ""), name="nunchi-codex-interrupt", daemon=True
        ).start()

    def _interrupt(self, app: AppServer, thread_id: str, codex_turn: str) -> None:
        try:
            app.request(
                "turn/interrupt", {"threadId": thread_id, "turnId": codex_turn}, timeout=_INTERRUPT_GRACE_SECONDS
            )
        except RequestRefused as exc:
            logger.info("nunchi codex: turn/interrupt refused: %s", exc)
        except CodexAppServerError as exc:
            # Codex did not stop the run: end the app-server, and the next turn starts it again.
            logger.warning("nunchi codex: the run did not stop (%s); restarting Codex", exc)
            app.kill()

    def wait_for_start(self) -> None:
        """A room tool call that races its turn's start waits until the run is bound."""

        self._starting.wait(_START_WAIT_SECONDS)

    # -- the app-server's side -----------------------------------------------------------

    def _on_read(self, method: str, params: Mapping[str, Any]) -> None:
        # In read order, before the response that follows: what Codex started,
        # and whether each thread's MCP servers are ready.
        if method == "turn/started":
            turn = params.get("turn")
            if isinstance(turn, Mapping) and isinstance(turn.get("id"), str):
                with self._lock:
                    _remember(self._started, turn["id"], None)
        elif method == "mcpServer/startupStatus/updated":
            name, thread, status = params.get("name"), params.get("threadId"), params.get("status")
            if isinstance(name, str) and isinstance(thread, str) and isinstance(status, str):
                with self._mcp_changed:
                    self._mcp_status[(thread, name)] = status
                    self._mcp_changed.notify_all()

    def _on_notification(self, method: str, params: Mapping[str, Any]) -> None:
        if method == "turn/started":
            turn = params.get("turn")
            if isinstance(turn, Mapping) and isinstance(turn.get("id"), str) and params.get("threadId") == self._thread_id:
                with self._lock:
                    self._codex_turn = turn["id"]
        elif method == "turn/completed":
            self._turn_completed(params)
        elif method == "item/completed":
            self._item_completed(params)
        elif method == "thread/closed":
            if params.get("threadId") == self._thread_id:
                # Codex unloaded the thread; the next turn resumes it.
                with self._lock:
                    self._thread_id = None
        elif method in ("warning", "configWarning", "error"):
            text = params.get("message") or params.get("summary") or params.get("error")
            self.warnings.append(f"{method}: {text}"[:500])
            del self.warnings[:-_RECENT]

    def _turn_completed(self, params: Mapping[str, Any]) -> None:
        turn = params.get("turn")
        if not isinstance(turn, Mapping) or not isinstance(turn.get("id"), str):
            return
        codex_turn = turn["id"]
        with self._lock:
            _remember(self.completed_turns, codex_turn, turn)
            if self._codex_turn == codex_turn:
                self._codex_turn = None
            if self._bound is not None and self._bound[1] == codex_turn:
                self._bound = None
        ok, detail = _ending(turn)
        with self._lock:
            note = self._last_words.pop(codex_turn, None)
        # Only the run bound to the open turn ends it; others are not Nunchi's.
        # The agent's last words are its reason if the turn ends in silence.
        self.participant.end_turn(turn_id=codex_turn, ok=ok, detail=detail, note=note)

    def _item_completed(self, params: Mapping[str, Any]) -> None:
        item = params.get("item")
        codex_turn = params.get("turnId")
        if not isinstance(item, Mapping) or not isinstance(codex_turn, str):
            return
        kind = item.get("type")
        if kind == "agentMessage" and isinstance(item.get("text"), str):
            with self._lock:
                _remember(self._last_words, codex_turn, item["text"])
        if kind in _NOT_TOOL_ITEMS:
            return
        if isinstance(item.get("id"), str):
            with self._lock:
                _remember(self.tool_items, item["id"], item)
        if kind == "mcpToolCall" and item.get("server") == MCP_SERVER_NAME:
            return  # the bridge already added the room's news to its result
        with self._lock:
            bound = self._bound is not None and self._bound[1] == codex_turn
        if bound:
            self._steering.put(codex_turn)

    def _steer_loop(self) -> None:
        while True:
            codex_turn = self._steering.get()
            if codex_turn is None:
                return
            update = self.participant.news(turn_id=codex_turn)
            if not update:
                continue
            with self._lock:
                app, thread_id = self._app, self._thread_id
            if app is None or thread_id is None:
                continue
            try:
                app.request(
                    "turn/steer",
                    {
                        "threadId": thread_id,
                        "expectedTurnId": codex_turn,
                        "input": [{"type": "text", "text": update, "text_elements": []}],
                    },
                    timeout=_REQUEST_SECONDS,
                )
                self.steered.append((codex_turn, update))
                del self.steered[:-_RECENT]
            except CodexAppServerError as exc:
                # The run ended first; what it missed is the next moment's.
                logger.info("nunchi codex: turn/steer failed: %s", exc)

    def _on_server_request(self, method: str, params: Mapping[str, Any]) -> Any:
        """Codex asks a person something; nobody is there, so the answer is no."""

        self.declined.append(method)
        del self.declined[:-_RECENT]
        if method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            return {"decision": "decline"}
        if method == "item/permissions/requestApproval":
            return {"permissions": {}, "scope": "turn"}
        if method == "mcpServer/elicitation/request":
            return {"action": "decline", "content": None, "_meta": None}
        if method == "item/tool/call":
            return {"contentItems": [{"type": "inputText", "text": _DECLINED}], "success": False}
        raise ServerRequestError(-32601, f"{method}: {_DECLINED}")

    def _on_exit(self, generation: int, returncode: int | None) -> None:
        with self._lock:
            bound = self._bound if self._bound is not None and self._bound[2] == generation else None
            if bound is not None:
                self._bound = None
            if generation == self._generation:
                self._codex_turn = None
                self._app, self._thread_id = None, None
                # A new process's room server must report ready again.
                self._mcp_status.clear()
        if bound is not None:
            self.participant.end_turn(
                turn_id=bound[1], ok=False, detail=f"codex app-server exited ({returncode})"
            )


def _remember(recent: dict[str, Any], key: str, value: Any) -> None:
    recent.pop(key, None)
    recent[key] = value
    while len(recent) > _RECENT:
        del recent[next(iter(recent))]


def _ending(turn: Mapping[str, Any]) -> tuple[bool, str]:
    """A completed Codex turn as the library's end: only ``completed`` is ok."""

    status = str(turn.get("status", "unknown"))
    error = turn.get("error")
    message = error.get("message") if isinstance(error, Mapping) else None
    return status == "completed", status + (f": {message}" if message else "")


def build_integration(
    config: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    sections: Iterable[str] = (),
    withhold: Iterable[str] = (),
) -> tuple[Any, CodexRoomIntegration]:
    """The room settings and the integration for one Nunchi config (`docs/harness-guide.md`, step 1).

    The caller builds the `Room` around ``integration.participant`` with its
    platform transport. ``sections`` are the caller's own config sections, such
    as its transport's, and ``withhold`` names more variables the agent must
    never see or post, such as the transport's key.
    """

    from nunchi.room import RoomSettings

    environ = os.environ if environ is None else environ
    settings = RoomSettings.from_config(config, label="Codex app-server", sections=(SECTION, *sections))
    try:
        codex = CodexSettings.from_section(settings.sections[SECTION])
    except ValueError as exc:
        raise ValidationError(f"Codex app-server config: {exc}") from exc
    state = settings.state_directory.resolve()
    if codex.working_directory.resolve().is_relative_to(state):
        # The agent may write in its working directory; Nunchi's state is not its.
        raise ValidationError("codex.working_directory must be outside state_directory")
    roles = ["send", "react", "context"]
    if settings.authorization is not None:
        roles += ["propose", "withdraw"]
    withheld = list(dict.fromkeys([*withheld_names(codex, settings.attention_model), *withhold]))
    guard = SecretGuard(withheld_values(environ, withheld), patterns=TOKEN_PATTERNS)
    integration = CodexRoomIntegration(
        profile=settings.profile,
        guard=guard,
        settings=codex,
        environment=agent_environment(environ, withheld),
        runtime_directory=runtime_directory(),
        roles=roles,
        thread_store=settings.state_directory / "codex-thread.json",
    )
    return settings, integration
