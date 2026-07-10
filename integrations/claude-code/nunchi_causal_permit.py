"""Turn-scoped causal permit for the Claude Code nunchi gate.

Because the Claude Code inbound gate (``UserPromptSubmit``) and outbound gate
(``PreToolUse``) run as *separate processes*, the outbound gate has no memory of
which message a reply was composed for. It used to reverse-scan the transcript
and judge the *newest* inbound line — so a peer message that lands while the
agent is composing steals the causal role and the already-composed reply dies as
a false ``PASS`` (the "how's everyone" bug, 2026-07-10).

This module bridges that gap with the smallest possible state: the *origin*
message an admitted turn is composing for. It is emphatically **not** a service
queue / obligation ledger:

- **Session-scoped.** A permit never binds a different session; a restart cannot
  resurrect one.
- **Newest wins.** A later admit for the same (session, chat) supersedes.
- **Short-lived.** Past its TTL it is dead. A same-turn transport retry is not
  guaranteed reuse — the caller **consumes** the permit on its first outbound
  decision (see ``clear_permit``), so an unrelated later send cannot inherit it.
- **Only admits write it.** A ``PASS`` on an unrelated peer line records
  nothing and never mutates an open permit.

**Storage is one file per (session, chat) key** (``<dir>/<sha>.json``), not a
shared JSON map. Concurrent admits for *different* keys write to *different*
files and cannot clobber each other; same-key writes resolve by atomic rename
(newest wins). This removes the lost-permit race a shared read-modify-write map
would have. Whether an origin is still *worth* answering is the classifier's
call, not this module's — a drifted thread is a correct ``PASS``.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

_DEFAULT_DIR = Path.home() / ".nunchi" / "permits"
_DEFAULT_TTL_SECONDS = 300.0


def permit_dir() -> Path:
    return Path(os.environ.get("NUNCHI_PERMIT_DIR") or _DEFAULT_DIR)


def permit_ttl() -> float:
    try:
        return float(os.environ.get("NUNCHI_PERMIT_TTL_SECONDS") or _DEFAULT_TTL_SECONDS)
    except ValueError:
        return _DEFAULT_TTL_SECONDS


def _key_file(directory: Path, session_id: str, chat_id: str) -> Path:
    digest = hashlib.sha256(f"{session_id}\x1f{chat_id}".encode("utf-8")).hexdigest()[:32]
    return directory / f"{digest}.json"


def write_permit(
    session_id: str,
    chat_id: str,
    origin_message_id: str,
    origin_author: str = "",
    origin_ts: str = "",
    *,
    directory: Path | None = None,
    now: float | None = None,
) -> None:
    """Record the origin of the current composition (call at inbound *admit*).

    Newest-wins per (session, chat); atomic per-key rename. Best-effort — a write
    failure degrades to legacy binding, never to a crash.
    """
    if not (session_id and chat_id and origin_message_id):
        return
    directory = directory or permit_dir()
    now = time.time() if now is None else now
    record = {
        "session_id": session_id,
        "chat_id": chat_id,
        "origin_message_id": origin_message_id,
        "origin_author": origin_author,
        "origin_ts": origin_ts,
        "created_at": now,
    }
    dest = _key_file(directory, session_id, chat_id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(directory), prefix=".permit-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(record, fh)
            os.replace(tmp, dest)  # atomic; newest write for this key wins
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        pass  # non-fatal: the gate falls back to legacy binding


def read_permit(
    session_id: str,
    chat_id: str,
    *,
    directory: Path | None = None,
    now: float | None = None,
    ttl: float | None = None,
) -> dict | None:
    """Return the fresh, same-session permit for this composition, or ``None``.

    ``None`` (→ legacy newest-inbound binding) when there is no permit, it is
    from another session, or it has outlived its TTL. Never necros a past turn.
    """
    if not (session_id and chat_id):
        return None
    directory = directory or permit_dir()
    now = time.time() if now is None else now
    ttl = permit_ttl() if ttl is None else ttl
    try:
        with open(_key_file(directory, session_id, chat_id), encoding="utf-8") as fh:
            permit = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(permit, dict):
        return None
    if permit.get("session_id") != session_id:  # never cross a session boundary
        return None
    if not permit.get("origin_message_id"):
        return None
    if now - float(permit.get("created_at") or 0.0) > ttl:  # stale: a past turn
        return None
    return permit


def clear_permit(session_id: str, chat_id: str, *, directory: Path | None = None) -> None:
    """Consume the permit once its turn's outbound decision has been made, so an
    unrelated later send cannot inherit it (one-shot)."""
    if not (session_id and chat_id):
        return
    directory = directory or permit_dir()
    try:
        os.unlink(_key_file(directory, session_id, chat_id))
    except OSError:
        pass  # already gone / unwritable — nothing to consume
