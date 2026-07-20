"""Owner-only persistent Codex thread identity for the V2 participant."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID


_CODEX_SESSION_VERSION = 2
_MAX_SESSION_BYTES = 65536


class CodexSessionStateError(RuntimeError):
    """Persistent Codex room-session state is absent, unsafe, or invalid."""


def _valid_thread_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None


def _valid_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def load_codex_session(path: Path) -> dict[str, Any] | None:
    """Read one no-follow, owner-only V2 session document."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise CodexSessionStateError("Codex session state path must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CodexSessionStateError("Codex session state is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size > _MAX_SESSION_BYTES
        ):
            raise CodexSessionStateError("Codex session state source is unsafe")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(8192, _MAX_SESSION_BYTES + 1 - total),
            )
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_SESSION_BYTES:
                raise CodexSessionStateError("Codex session state is too large")
            chunks.append(chunk)
        try:
            raw = json.loads(
                b"".join(chunks).decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("non-finite")
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise CodexSessionStateError("Codex session state is invalid") from exc
    finally:
        os.close(descriptor)
    if (
        not isinstance(raw, dict)
        or set(raw) != {"version", "thread_id", "created_at", "updated_at"}
        or type(raw.get("version")) is not int
        or raw.get("version") != _CODEX_SESSION_VERSION
    ):
        raise CodexSessionStateError("Codex session state has an unsupported shape")
    thread_id = _valid_thread_id(raw.get("thread_id"))
    if thread_id is None:
        raise CodexSessionStateError("Codex session state has an invalid thread identity")
    created_at = _valid_timestamp(raw.get("created_at"))
    updated_at = _valid_timestamp(raw.get("updated_at"))
    if created_at is None or updated_at is None or created_at > updated_at:
        raise CodexSessionStateError("Codex session state has an invalid timestamp")
    return {
        "version": _CODEX_SESSION_VERSION,
        "thread_id": thread_id,
        "created_at": raw["created_at"],
        "updated_at": raw["updated_at"],
    }


def save_codex_session(
    path: Path,
    thread_id: str,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Atomically persist a Codex thread identity with mode 0600."""
    normalized = _valid_thread_id(thread_id)
    if normalized is None:
        raise CodexSessionStateError("cannot save an invalid Codex thread identity")
    if not isinstance(path, Path) or not path.is_absolute():
        raise CodexSessionStateError("Codex session state path must be absolute")
    now = datetime.now(timezone.utc).isoformat()
    parsed_created_at = _valid_timestamp(created_at) if created_at is not None else None
    parsed_now = _valid_timestamp(now)
    if (
        created_at is not None
        and (
            parsed_created_at is None
            or parsed_now is None
            or parsed_created_at > parsed_now
        )
    ):
        raise CodexSessionStateError("cannot save an invalid Codex session timestamp")
    state = {
        "version": _CODEX_SESSION_VERSION,
        "thread_id": normalized,
        "created_at": created_at or now,
        "updated_at": now,
    }
    try:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        parent = path.parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o077
        ):
            raise CodexSessionStateError("Codex session state directory is unsafe")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".codex-v2-session-",
            suffix=".tmp",
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state, handle, allow_nan=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            directory_fd = os.open(
                path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise CodexSessionStateError("cannot save Codex session state") from exc
    return state


def reset_codex_session(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise CodexSessionStateError("Codex session state path must be absolute")
    try:
        metadata = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise CodexSessionStateError("Codex session state source is unsafe")
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise CodexSessionStateError("cannot reset Codex session state") from exc


__all__ = [
    "CodexSessionStateError",
    "load_codex_session",
    "reset_codex_session",
    "save_codex_session",
]
