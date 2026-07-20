"""Tool-neutral V2 participant subprocess for reference adapters.

The operator selects one argv vector and an owner-only workspace.  One fresh
ParticipantWakeV2 document is written to stdin and the process returns exactly
one JSON message action, reaction action, or ``null``.  No shell is involved,
the child receives a minimal environment, and platform/classifier credentials
are not inherited implicitly.
"""

from __future__ import annotations

import copy
import json
import os
import re
import signal
import stat
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..participant import ParticipantTurn


MAX_OUTPUT_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_RESERVED_ENV = frozenset(
    {
        "HOME",
        "PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "CODEX_HOME",
        "NUNCHI_DISCORD_TOKEN",
        "DISCORD_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "MATRIX_ACCESS_TOKEN",
        "NUNCHI_CLASSIFIER_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
    }
)
_RESERVED_ENV_PREFIXES = (
    "NUNCHI_",
    "CODEX_",
    "CLAUDE_",
    "DISCORD_",
    "MATRIX_",
    "TELEGRAM_",
)


class SubprocessParticipantError(RuntimeError):
    pass


def _strict_json(raw: str) -> Any:
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


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except OSError:
        pass


def run_bounded_process(
    command: tuple[str, ...],
    *,
    workspace: Path,
    environment: Mapping[str, str],
    payload: bytes,
    timeout_seconds: float,
) -> tuple[int, bytes, bytes]:
    """Run one child while bounding both captured pipes during execution."""
    try:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
    except OSError as exc:
        raise SubprocessParticipantError(
            "participant process could not start"
        ) from exc

    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()
    writer_error: list[BaseException] = []

    def write_input() -> None:
        assert process.stdin is not None
        try:
            process.stdin.write(payload)
            process.stdin.flush()
        except BrokenPipeError:
            pass
        except OSError as exc:
            writer_error.append(exc)
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    def drain(pipe, buffer: bytearray, limit: int) -> None:
        try:
            while True:
                read = getattr(pipe, "read1", pipe.read)
                chunk = read(65536)
                if not chunk:
                    return
                remaining = limit + 1 - len(buffer)
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
                if len(buffer) > limit or len(chunk) > remaining:
                    overflow.set()
                    _stop_process(process)
                    return
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    assert process.stdout is not None and process.stderr is not None
    threads = [
        threading.Thread(target=write_input, daemon=True),
        threading.Thread(
            target=drain,
            args=(process.stdout, stdout, MAX_OUTPUT_BYTES),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(process.stderr, stderr, MAX_STDERR_BYTES),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            _stop_process(process)
            break
        try:
            process.wait(timeout=min(remaining, 0.1))
        except subprocess.TimeoutExpired:
            continue
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _stop_process(process)
        process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)

    if timed_out:
        raise SubprocessParticipantError("participant process timed out")
    if overflow.is_set():
        raise SubprocessParticipantError(
            "participant process output exceeded its budget"
        )
    if writer_error:
        raise SubprocessParticipantError("participant process I/O failed")
    if any(thread.is_alive() for thread in threads):
        raise SubprocessParticipantError("participant process I/O did not close")
    assert process.returncode is not None
    return process.returncode, bytes(stdout), bytes(stderr)


def _owner_only_directory(value: Path) -> Path:
    if not value.is_absolute():
        raise ValueError("participant workspace must be absolute")
    try:
        metadata = value.lstat()
    except OSError as exc:
        raise ValueError("participant workspace is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("participant workspace is unsafe")
    return value


def _command(value: Sequence[str]) -> tuple[str, ...]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not 1 <= len(value) <= 64
        or any(
            not isinstance(item, str) or not item or len(item) > 4096
            or "\0" in item
            for item in value
        )
    ):
        raise ValueError("participant command is invalid")
    executable = Path(value[0])
    if not executable.is_absolute():
        raise ValueError("participant executable must be absolute")
    try:
        resolved = executable.resolve(strict=True)
        metadata = resolved.stat(follow_symlinks=False)
    except OSError as exc:
        raise ValueError("participant executable is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid not in (0, os.geteuid())
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or not os.access(resolved, os.X_OK)
    ):
        raise ValueError("participant executable is unsafe")
    return (str(resolved), *value[1:])


def _environment(
    workspace: Path,
    pass_env: Sequence[str],
    source: Mapping[str, str],
) -> dict[str, str]:
    if isinstance(pass_env, (str, bytes)) or not isinstance(pass_env, Sequence):
        raise ValueError("participant environment selection is invalid")
    names: list[str] = []
    for name in pass_env:
        if (
            not isinstance(name, str)
            or _ENV_NAME_RE.fullmatch(name) is None
            or name in _RESERVED_ENV
            or name.startswith(_RESERVED_ENV_PREFIXES)
            or name in names
        ):
            raise ValueError("participant environment selection is invalid")
        if name not in source:
            raise ValueError("participant environment value is unavailable")
        selected_value = source[name]
        if (
            not isinstance(selected_value, str)
            or "\0" in selected_value
            or len(selected_value) > 65536
        ):
            raise ValueError("participant environment value is invalid")
        names.append(name)
    result = {
        "HOME": str(workspace),
        "PATH": os.defpath,
    }
    for name in (
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "TERM",
    ):
        if name in source:
            result[name] = source[name]
    for name in names:
        result[name] = source[name]
    return result


class SubprocessParticipantV2:
    """Invoke one explicitly configured participant process per waking turn."""

    def __init__(
        self,
        *,
        command: Sequence[str],
        workspace: Path,
        timeout_seconds: float = 120,
        pass_env: Sequence[str] = (),
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 1 <= float(timeout_seconds) <= 600
        ):
            raise ValueError("participant timeout is invalid")
        self.command = _command(command)
        self.workspace = _owner_only_directory(Path(workspace))
        self.timeout_seconds = float(timeout_seconds)
        source = os.environ if environ is None else environ
        self.environment = _environment(self.workspace, pass_env, source)

    def __call__(self, turn: ParticipantTurn) -> Any:
        if not isinstance(turn, ParticipantTurn):
            raise SubprocessParticipantError("participant turn is invalid")
        try:
            payload = (
                json.dumps(
                    turn.packet,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
        except (TypeError, ValueError) as exc:
            raise SubprocessParticipantError("participant packet is invalid") from exc
        returncode, stdout, _stderr = run_bounded_process(
            self.command,
            workspace=self.workspace,
            environment=self.environment,
            payload=payload.encode("utf-8"),
            timeout_seconds=self.timeout_seconds,
        )
        if returncode != 0:
            raise SubprocessParticipantError("participant process failed")
        try:
            action = _strict_json(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise SubprocessParticipantError(
                "participant process returned invalid JSON"
            ) from exc
        if action is not None and not isinstance(action, dict):
            raise SubprocessParticipantError("participant process returned an invalid action")
        return copy.deepcopy(action)


__all__ = [
    "SubprocessParticipantError",
    "SubprocessParticipantV2",
    "run_bounded_process",
]
