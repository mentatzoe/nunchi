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

These rules, with looking again, steering and the secret guard, are the core's
(`nunchi.turn`), the same for every harness.  This module adds the session,
the mod's tool names, and the socket the mod calls.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
from typing import Any
import uuid

from ..attention import ParticipantProfile
from ..participant_model import PARTICIPANT_TOOL_SPECS
from ..turn import TURN_ROLES, SecretGuard as CoreSecretGuard, Turn, TurnError, TurnParticipant
from ..turn_server import TurnServer
from .discord_participant_transport import DISCORD_TOKEN_PATTERNS

SOCKET_ENV = "NUNCHI_CLAUDE_CODE_GATE_SOCKET"
SESSION_ENV = "NUNCHI_CLAUDE_CODE_GATE_SESSION"
PLUGIN_NAME = "nunchi"
TOOL_NAMES = {
    "send": "room_send",
    "react": "room_react",
    "propose": "room_propose",
    "withdraw": "room_withdraw",
    "context": "room_context",
}
WAKE_MARKER = '<nunchi_wake id="{}"/>'

_RESULT_WAIT_SECONDS = 25.0
_INTERRUPT_GRACE_SECONDS = 10.0
_DIAGNOSTIC_LINES = 40


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


class SecretGuard(CoreSecretGuard):
    """The core's guard, which also refuses a Discord bot token's shape.

    The runtime builds its guard with `nunchi.room.room_guard`, which takes
    the shape from the shared Discord transport; this class is for a gate
    built without a room config.
    """

    def __init__(self, values: Iterable[str]) -> None:
        super().__init__(values, DISCORD_TOKEN_PATTERNS)


class _SessionDriver:
    """Runs each turn in the dedicated session; the mod binds it to its wake."""

    def __init__(self, session: Any) -> None:
        self.session = session

    def ready(self, cancel: threading.Event) -> bool:
        return self.session.wait_idle(cancel)

    def start(self, turn: Turn) -> None:
        self.session.submit(WAKE_MARKER.format(turn.wake_id) + "\n" + turn.text)

    def interrupt(self, turn: Turn) -> None:
        self.session.interrupt()


class GatedParticipant(TurnParticipant):
    """The participant the shared host invokes; the session does the thinking.

    The turn's rules are the core's (`nunchi.turn`); this class adds only what
    the mod registers and the session that runs each turn.
    """

    def __init__(
        self,
        *,
        profile: ParticipantProfile,
        session: Any,
        guard: SecretGuard,
        privileged_enabled: bool,
        result_wait_seconds: float = _RESULT_WAIT_SECONDS,
    ) -> None:
        super().__init__(
            profile=profile,
            driver=_SessionDriver(session),
            guard=guard,
            tool_names={role: full_tool_name(role) for role in TURN_ROLES},
            roles=[
                role
                for role in TURN_ROLES
                if role not in ("propose", "withdraw") or privileged_enabled
            ],
            result_wait_seconds=result_wait_seconds,
        )
        self.session = session

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

    def unbound_detail(self) -> str:
        return "" if self.attached else "; the mod never attached"

    def run_protocol(self, *, wake, opportunity, expand, cancel):
        try:
            return super().run_protocol(
                wake=wake, opportunity=opportunity, expand=expand, cancel=cancel
            )
        except TurnError as exc:
            raise ClaudeCodeGateError(str(exc)) from exc


class ClaudeCodeSession:
    """One dedicated `claude -p` session, written to over stream-json.

    The session starts on the first wake and again on the next wake after it
    exits.  It runs in the configured working directory with the user's own
    Claude Code configuration, the Nunchi mod, and the environment the runtime
    gives it: without the secrets the config names, but with the gate's socket
    path and the per-launch session secret, which the mod needs.  The agent
    can read that secret; the gate refuses a room action that carries it.
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
        self, process: subprocess.Popen[str], *, ok: bool, detail: str, note: str | None = None
    ) -> None:
        with self._lock:
            if process is not self._process:
                return
        # The participant closes its turn before the session reads as idle,
        # so the next wake never finds the previous turn still open.
        if self.on_turn_end is not None:
            self.on_turn_end(ok=ok, detail=detail, note=note)
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
                # The session's final message: the agent's last words, kept as
                # its reason if the turn ends in silence.
                result = message.get("result")
                self._turn_ended(
                    process,
                    ok=ok,
                    detail=str(message.get("subtype", "unknown")),
                    note=result if isinstance(result, str) else None,
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


class GateServer(TurnServer):
    """The mod's only way in: the core's local turn protocol over a private Unix socket.

    Every request carries the per-launch session secret the gate gave the
    session it started.  Any other caller is refused.
    """
