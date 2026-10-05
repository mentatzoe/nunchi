"""Gate one dedicated Claude Code session into one Nunchi room through a mod.

The gate is the participant the shared `ParticipantTurnHost` invokes.  On each
wake it writes one turn into a dedicated `claude -p` session it started.  The
Nunchi mod inside that session registers the room tools, binds each model turn
to the wake that started it, and forwards room tool calls back to the gate over
a private Unix socket.  The gate hands the participant's one room action to the
host, waits for the host's result, and returns that result to the tool call.

Observation, attention, scheduling, authority, and the one output commit point
stay with the shared owners.  The session keeps the user's own Claude Code
configuration: model, instructions, memory, tools, permission rules, MCP
servers, plugins, and skills.

A turn that ends without a room action is silence only when the mod bound that
turn to its wake, which shows the room tools were present.  Every other ending
is an operational failure, never silence.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import secrets
import socketserver
import subprocess
import threading
from typing import Any
import uuid

from ..attention import ParticipantProfile
from ..errors import NunchiError
from ..participant import ParticipantTurnHost, TransportResult
from ..participant_model import (
    PARTICIPANT_TOOL_SPECS,
    PARTICIPANT_TURN_PROTOCOL_VERSION,
    ParticipantModelError,
    build_participant_turn_request,
    participant_tool_action,
    participant_tool_expansion,
    participant_tool_roles,
    participant_tool_turn_text,
)

SOCKET_ENV = "NUNCHI_CLAUDE_CODE_GATE_SOCKET"
SESSION_ENV = "NUNCHI_CLAUDE_CODE_GATE_SESSION"
PLUGIN_NAME = "nunchi"
TOOL_NAMES = {
    "send": "room_send",
    "react": "room_react",
    "propose": "room_propose",
    "context": "room_context",
}
WAKE_MARKER = '<nunchi_wake id="{}"/>'

_MAX_BODY_BYTES = 256 * 1024
_RESULT_WAIT_SECONDS = 25.0
_INTERRUPT_GRACE_SECONDS = 10.0
_DIAGNOSTIC_LINES = 40
# A Discord bot token has three dot-separated base64url parts.
_TOKEN_PATTERNS = (
    re.compile(r"[A-Za-z\d_-]{23,28}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"),
)


class ClaudeCodeGateError(RuntimeError):
    """An operational failure of the gated session.  Never silence."""


def atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Write `payload` to `path` atomically without following a symlink."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    try:
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError(f"short write to {path}")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def full_tool_name(role: str) -> str:
    return f"mcp__{PLUGIN_NAME}__{TOOL_NAMES[role]}"


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


class SecretGuard:
    """Refuses a room action that carries a withheld secret.

    The session never receives Nunchi's secrets in its environment, but it may
    still read them some other way, for example from a file.  This is the last
    check before an action reaches the host: exact withheld values, and the
    shape of a bot token.
    """

    def __init__(self, values: Iterable[str]) -> None:
        self._values = tuple(sorted({value for value in values if len(value) >= 12}))

    def refusal(self, action: Mapping[str, Any]) -> str | None:
        texts = list(_strings(action))
        if any(value in text for text in texts for value in self._values) or any(
            pattern.search(text) for text in texts for pattern in _TOKEN_PATTERNS
        ):
            return (
                "Refused: this action contains a credential or secret. Nothing "
                "was posted. Remove it and try again."
            )
        return None


class _Turn:
    """One wake, from the prompt written to the session to its end."""

    def __init__(
        self,
        *,
        request: Mapping[str, Any],
        roles: Sequence[str],
        expand: Callable[..., Mapping[str, Any]],
        cancel: threading.Event,
    ) -> None:
        self.request = request
        self.request_id = request["binding"]["request_id"]
        self.wake_id = secrets.token_urlsafe(18)
        self.roles = frozenset(roles)
        self.expand = expand
        self.cancel = cancel
        self.visible_event_ids = {event["id"] for event in request["wake"]["events"]}
        self.looked_again = False
        self.lock = threading.Lock()
        self.turn_id: str | None = None
        self.turn_ids: set[str] = set()
        self.action: dict[str, Any] | None = None
        self.action_ready = threading.Event()
        self.outcome: TransportResult | None = None
        self.outcome_ready = threading.Event()
        self.ended = threading.Event()
        self.end_ok = False
        self.end_detail = ""


def _describe(result: TransportResult | None) -> tuple[bool, str]:
    if result is None:
        return False, (
            "The room opportunity ended before this action was committed. "
            "Nothing was posted."
        )
    if result.delivery == "sent":
        return True, "Done: the room accepted this action."
    if result.delivery == "unavailable":
        return True, f"Not done yet: {result.detail}. Do not repeat it."
    if result.delivery == "unknown":
        return True, (
            f"Delivery is uncertain: {result.detail}. Do not repeat it."
        )
    return False, f"Not posted: {result.detail}."


class GatedParticipant:
    """The participant the shared host invokes; the session does the thinking."""

    core_protocol_version = PARTICIPANT_TURN_PROTOCOL_VERSION

    def __init__(
        self,
        *,
        profile: ParticipantProfile,
        session: Any,
        guard: SecretGuard,
        privileged_enabled: bool,
        result_wait_seconds: float = _RESULT_WAIT_SECONDS,
    ) -> None:
        self.profile = profile
        self.session = session
        self.guard = guard
        self.registered_roles = tuple(
            role
            for role in ("send", "react", "propose", "context")
            if role != "propose" or privileged_enabled
        )
        self._roles_by_tool = {full_tool_name(role): role for role in self.registered_roles}
        self.result_wait_seconds = result_wait_seconds
        self._lock = threading.Lock()
        self._active: _Turn | None = None
        self._recent: deque[_Turn] = deque(maxlen=4)
        self.attached = False

    # -- what the mod registers ------------------------------------------------

    def tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": TOOL_NAMES[role],
                "description": PARTICIPANT_TOOL_SPECS[role]["description"],
                "inputSchema": deepcopy(PARTICIPANT_TOOL_SPECS[role]["input_schema"]),
            }
            for role in self.registered_roles
        ]

    def attach(self) -> list[dict[str, Any]]:
        self.attached = True
        return self.tool_specs()

    # -- the shared host's side ------------------------------------------------

    def run_protocol(self, *, wake, opportunity, expand, cancel):
        request = build_participant_turn_request(wake, opportunity)
        roles = [
            role for role in participant_tool_roles(request) if role in self.registered_roles
        ]
        turn = _Turn(request=request, roles=roles, expand=expand, cancel=cancel)
        text = (
            WAKE_MARKER.format(turn.wake_id)
            + "\n"
            + participant_tool_turn_text(
                self.profile,
                request,
                tools={role: full_tool_name(role) for role in roles},
            )
        )
        if not self.session.wait_idle(cancel):
            return None
        with self._lock:
            if self._active is not None:
                raise ClaudeCodeGateError("another Claude Code turn is still open")
            self._active = turn
            self._recent.append(turn)
        try:
            self.session.submit(text)
        except BaseException:
            self._close(turn, ok=False, detail="the turn could not be written")
            raise
        while True:
            if turn.action_ready.wait(0.05):
                return deepcopy(turn.action)
            if cancel.is_set():
                self.session.interrupt()
                return None
            if turn.ended.is_set():
                if turn.action_ready.is_set():
                    return deepcopy(turn.action)
                if turn.end_ok and turn.turn_id is not None:
                    return None
                if turn.turn_id is None:
                    raise ClaudeCodeGateError(
                        "the Nunchi mod did not bind this Claude Code turn"
                        + ("" if self.attached else "; the mod never attached")
                        + (f" ({turn.end_detail})" if turn.end_detail else "")
                    )
                raise ClaudeCodeGateError(
                    f"the Claude Code turn ended without an answer: {turn.end_detail}"
                )

    def __call__(self, *, wake, expand, cancel):
        return self.run_protocol(
            wake=wake,
            opportunity={
                "generation": 1,
                "lifecycle_id": "direct-library-call",
                "deadline_id": "direct-library-call",
                "permissions": {
                    "revision": "direct-library-call",
                    "ordinary_actions": ["message", "reply", "reaction"],
                    "privileged_proposals": False,
                },
            },
            expand=expand,
            cancel=cancel,
        )

    def settle(self, request_id: str, result: TransportResult | None) -> None:
        """Record what the host did with the action of one request."""

        with self._lock:
            turn = next(
                (item for item in self._recent if item.request_id == request_id), None
            )
        if turn is None:
            return
        with turn.lock:
            if turn.outcome_ready.is_set():
                return
            turn.outcome = result
            turn.outcome_ready.set()

    # -- the session's side ------------------------------------------------------

    def turn_ended(self, *, ok: bool, detail: str) -> None:
        with self._lock:
            turn = self._active
        if turn is not None:
            self._close(turn, ok=ok, detail=detail)

    def _close(self, turn: _Turn, *, ok: bool, detail: str) -> None:
        with self._lock:
            if self._active is turn:
                self._active = None
        turn.end_ok = ok
        turn.end_detail = detail
        turn.ended.set()

    # -- the mod's side ------------------------------------------------------------

    def bind_turn(self, *, turn_id: str, wake_id: str | None) -> bool:
        """Bind a model turn to the open wake.

        The first turn must carry the wake's id.  A later turn with no wake
        marker while that wake is still open is a continuation of it (the
        session runs one wake at a time), so it keeps the room tools.
        """

        with self._lock:
            turn = self._active
            if turn is None:
                return False
            if turn.turn_id is None:
                if wake_id is None or not hmac.compare_digest(
                    wake_id.encode(), turn.wake_id.encode()
                ):
                    return False
                turn.turn_id = turn_id
                turn.turn_ids.add(turn_id)
                return True
            if wake_id is None:
                turn.turn_ids.add(turn_id)
                return True
            return False

    def call_tool(
        self, *, turn_id: str | None, tool: str, arguments: Any
    ) -> tuple[bool, str]:
        role = self._roles_by_tool.get(tool)
        if role is None:
            return False, f"{tool} is not a Nunchi room tool."
        with self._lock:
            turn = self._active
        if turn is None or turn.turn_id is None or turn_id not in turn.turn_ids:
            return False, (
                "No room opportunity is open for this turn. Nothing was posted."
            )
        if (
            turn.cancel.is_set()
            or turn.ended.is_set()
            or (turn.action is None and turn.outcome_ready.is_set())
        ):
            return False, "This room opportunity has ended. Nothing was posted."
        if role not in turn.roles:
            return False, f"{tool} is not available in this turn."
        if role == "context":
            return self._context(turn, arguments)
        with turn.lock:
            if turn.action is not None:
                return False, (
                    "You already took your one room action in this turn. End "
                    "your turn."
                )
            try:
                action = participant_tool_action(
                    role,
                    arguments,
                    request=turn.request,
                    visible_event_ids=turn.visible_event_ids,
                )
            except ParticipantModelError as exc:
                return False, f"Refused: {exc}. Nothing was posted."
            refusal = self.guard.refusal(action)
            if refusal is not None:
                return False, refusal
            held = self._look_again(turn, action)
            if held is not None:
                return True, held
            turn.action = action
            turn.action_ready.set()
        if not turn.outcome_ready.wait(self.result_wait_seconds):
            return True, (
                "The room has not confirmed this action yet. Do not repeat it."
            )
        return _describe(turn.outcome)

    def _look_again(self, turn: _Turn, action: Mapping[str, Any]) -> str | None:
        """Before the first post or reaction, show what others said meanwhile.

        The action is held once when others posted while the session was
        composing; the session then decides again. A failed check never
        blocks the action.
        """

        if turn.looked_again or action["kind"] not in ("message", "reply", "reaction"):
            return None
        turn.looked_again = True
        try:
            page = dict(turn.expand(direction="new", max_events=12, max_bytes=16_384))
        except NunchiError:
            return None
        events = [
            event
            for event in page.get("events", ())
            if isinstance(event, Mapping) and isinstance(event.get("id"), str)
        ]
        turn.visible_event_ids.update(event["id"] for event in events)
        # Only another person's message holds the post; a new reaction alone
        # does not change what the room needs.
        messages = [event for event in events if event.get("type") == "message"]
        if not messages:
            return None
        return (
            f"Not posted yet: {len(messages)} new message(s) arrived while you were "
            "composing. Call the tool again to send it as it is or changed, or "
            "end your turn to stay silent.\n"
            + json.dumps(page, sort_keys=True, ensure_ascii=False)
        )

    def _context(self, turn: _Turn, arguments: Any) -> tuple[bool, str]:
        if turn.action is not None:
            return False, "You already took your room action in this turn."
        try:
            page = turn.expand(**participant_tool_expansion(arguments))
        except ParticipantModelError as exc:
            return False, f"Refused: {exc}."
        except NunchiError as exc:
            return False, f"Room context is unavailable: {exc}."
        page = dict(page)
        for event in page.get("events", ()):
            if isinstance(event, Mapping) and isinstance(event.get("id"), str):
                turn.visible_event_ids.add(event["id"])
        return True, json.dumps(page, sort_keys=True, ensure_ascii=False)


class GatedTurnHost(ParticipantTurnHost):
    """The shared host, reporting each result back to the gated participant."""

    def run(self, **kwargs):  # type: ignore[override]
        settle = getattr(self.participant, "settle", None)
        request_id = kwargs["request"]["request_id"]
        try:
            result = super().run(**kwargs)
        except BaseException:
            # The host may fail after the native call (a receipt write, say),
            # so the participant must not be told that nothing was posted.
            if callable(settle):
                settle(
                    request_id,
                    TransportResult("unknown", "the host failed while handling it"),
                )
            raise
        if callable(settle):
            settle(request_id, result)
        return result


class ClaudeCodeSession:
    """One dedicated `claude -p` session, written to over stream-json.

    The session starts on the first wake and again on the next wake after it
    exits.  It runs in the configured working directory with the user's own
    Claude Code configuration, the Nunchi mod, and an environment that holds
    none of Nunchi's secrets.
    """

    def __init__(
        self,
        *,
        executable: str | None,
        plugin_directory: Path,
        working_directory: Path,
        environment: Mapping[str, str],
        model: str | None = None,
        disallowed_tools: Sequence[str] = (),
        session_store: Path | None = None,
        on_turn_end: Callable[..., None] | None = None,
    ) -> None:
        self.executable = executable
        self.plugin_directory = plugin_directory
        self.working_directory = working_directory
        self.environment = dict(environment)
        self.model = model
        self.disallowed_tools = tuple(disallowed_tools)
        self.session_store = session_store
        self.on_turn_end = on_turn_end
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._idle = threading.Event()
        self._busy = False
        self._session_id: str | None = None
        self._resumed = False
        self._answered = False
        self.diagnostics: deque[str] = deque(maxlen=_DIAGNOSTIC_LINES)

    # -- process lifecycle ---------------------------------------------------------

    def command(self, resume: str | None) -> list[str]:
        command = [
            self.executable,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--plugin-dir",
            str(self.plugin_directory),
        ]
        if resume is not None:
            command.extend(("--resume", resume))
        if self.model is not None:
            command.extend(("--model", self.model))
        if self.disallowed_tools:
            command.append("--disallowedTools")
            command.extend(self.disallowed_tools)
        return command

    def _stored_session(self) -> str | None:
        if self.session_store is None or not self.session_store.exists():
            return None
        try:
            stored = json.loads(self.session_store.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = stored.get("session_id") if isinstance(stored, dict) else None
        try:
            return str(uuid.UUID(value)) if isinstance(value, str) else None
        except ValueError:
            return None

    def _store_session(self, session_id: str) -> None:
        if self.session_store is None or session_id == self._session_id:
            return
        self._session_id = session_id
        atomic_write(
            self.session_store,
            json.dumps({"session_id": session_id}).encode("utf-8"),
        )

    def _forget_session(self) -> None:
        if self.session_store is not None:
            try:
                self.session_store.unlink()
            except FileNotFoundError:
                pass

    def start(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            stale = self._busy
        if stale:
            # The previous process died mid-turn and its reader may not have
            # reported it yet; that turn can never finish, so close it now.
            self._busy = False
            if self.on_turn_end is not None:
                self.on_turn_end(
                    ok=False,
                    detail="Claude Code exited mid-turn" + self._diagnostic_suffix(),
                )
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            if self.executable is None:
                raise ClaudeCodeGateError(
                    "Claude Code executable is not installed on trusted PATH"
                )
            resume = self._stored_session()
            self._resumed = resume is not None
            self._answered = False
            self._session_id = resume
            self.working_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                process = subprocess.Popen(
                    self.command(resume),
                    cwd=self.working_directory,
                    env=self.environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                raise ClaudeCodeGateError(f"Claude Code could not start: {exc}") from exc
            self._process = process
            self._busy = False
            self._idle.set()
        threading.Thread(
            target=self._read_stdout, args=(process,), name="nunchi-claude-stdout", daemon=True
        ).start()
        threading.Thread(
            target=self._read_stderr, args=(process,), name="nunchi-claude-stderr", daemon=True
        ).start()

    def stop(self) -> None:
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    @property
    def alive(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    # -- turns ---------------------------------------------------------------------

    def wait_idle(self, cancel: threading.Event) -> bool:
        """Start the session if needed and wait until no turn is running.

        One wake starts the session at most once, so a session that keeps
        exiting fails each wake with its diagnostics instead of looping.
        """

        started = False
        while True:
            if cancel.is_set():
                return False
            if not self.alive:
                if started:
                    raise ClaudeCodeGateError(
                        "Claude Code exited before the turn started"
                        + self._diagnostic_suffix()
                    )
                self.start()
                started = True
                continue
            if self._idle.wait(0.05):
                return not cancel.is_set()

    def _write(self, message: Mapping[str, Any]) -> None:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                raise ClaudeCodeGateError(
                    "the Claude Code session is not running" + self._diagnostic_suffix()
                )
            try:
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise ClaudeCodeGateError(
                    f"the Claude Code session stopped reading: {exc}"
                ) from exc

    def submit(self, text: str) -> None:
        self._idle.clear()
        self._busy = True
        try:
            self._write(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": text}],
                    },
                }
            )
        except BaseException:
            self._busy = False
            self._idle.set()
            raise

    def interrupt(self) -> None:
        """Stop the running turn; end the process if it does not stop."""

        if not self._busy:
            return
        try:
            self._write(
                {
                    "type": "control_request",
                    "request_id": str(uuid.uuid4()),
                    "request": {"subtype": "interrupt"},
                }
            )
        except ClaudeCodeGateError:
            return
        with self._lock:
            process = self._process

        def enforce() -> None:
            if self._idle.wait(_INTERRUPT_GRACE_SECONDS):
                return
            if process is not None and process.poll() is None:
                process.kill()

        threading.Thread(target=enforce, name="nunchi-claude-interrupt", daemon=True).start()

    def _diagnostic_suffix(self) -> str:
        tail = " | ".join(list(self.diagnostics)[-3:])
        return f": {tail[-500:]}" if tail else ""

    def _turn_ended(
        self, process: subprocess.Popen[str], *, ok: bool, detail: str
    ) -> None:
        with self._lock:
            if process is not self._process:
                return
        # The participant closes its turn before the session reads as idle,
        # so the next wake never finds the previous turn still open.
        if self.on_turn_end is not None:
            self.on_turn_end(ok=ok, detail=detail)
        self._busy = False
        self._idle.set()

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            session_id = message.get("session_id")
            if isinstance(session_id, str):
                try:
                    self._store_session(str(uuid.UUID(session_id)))
                except (ValueError, OSError):
                    pass
            if message.get("type") == "result":
                self._answered = True
                ok = message.get("subtype") == "success" and message.get("is_error") is False
                self._turn_ended(
                    process, ok=ok, detail=str(message.get("subtype", "unknown"))
                )
        process.wait()
        for stream in (process.stdin, process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        if self._resumed and not self._answered:
            # A session that cannot be resumed must not block every restart.
            self._forget_session()
        self._turn_ended(
            process,
            ok=False,
            detail=f"Claude Code exited {process.returncode}" + self._diagnostic_suffix(),
        )

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        assert process.stderr is not None
        for line in process.stderr:
            text = line.strip()
            if text:
                self.diagnostics.append(text[:500])
        process.stderr.close()


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request: Any, client_address: Any) -> None:
        # A caller that hangs up is not the gate's failure; stay quiet.
        pass


class GateServer:
    """The mod's only way in: HTTP over a private Unix socket.

    Every request carries the per-launch session secret the gate gave the
    session it started.  Any other caller is refused.
    """

    def __init__(
        self,
        participant: GatedParticipant,
        *,
        socket_path: Path,
        session_secret: str,
    ) -> None:
        self.participant = participant
        self.socket_path = socket_path
        self._secret = session_secret.encode()
        self._server: _UnixHTTPServer | None = None

    def start(self) -> None:
        directory = self.socket_path.parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        gate = self

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
                if not 0 <= length <= _MAX_BODY_BYTES:
                    self._answer(413, {"error": "request body is too large"})
                    return
                # Read the bounded body before refusing anyone, so a refused
                # caller gets its answer instead of a reset connection.
                raw = self.rfile.read(length)
                supplied = self.headers.get("X-Nunchi-Session", "").encode()
                if not hmac.compare_digest(supplied, gate._secret):
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
                self._answer(200, gate.route(self.path, body))

        self._server = _UnixHTTPServer(str(self.socket_path), Handler)
        os.chmod(self.socket_path, 0o600)
        threading.Thread(
            target=self._server.serve_forever, name="nunchi-claude-gate", daemon=True
        ).start()

    def route(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        participant = self.participant
        if path == "/v1/attach":
            return {"tools": participant.attach()}
        if path == "/v1/turn-start":
            turn_id = body.get("turn_id")
            wake_id = body.get("wake_id")
            if not isinstance(turn_id, str) or not turn_id:
                return {"bound": False}
            return {
                "bound": participant.bind_turn(
                    turn_id=turn_id,
                    wake_id=wake_id if isinstance(wake_id, str) else None,
                )
            }
        if path == "/v1/tool":
            turn_id = body.get("turn_id")
            tool = body.get("tool")
            if not isinstance(tool, str):
                return {"ok": False, "error": "The tool name is missing."}
            ok, text = participant.call_tool(
                turn_id=turn_id if isinstance(turn_id, str) else None,
                tool=tool,
                arguments=body.get("input", {}),
            )
            return {"ok": True, "text": text} if ok else {"ok": False, "error": text}
        return {"error": f"unknown gate path {path}"}

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
