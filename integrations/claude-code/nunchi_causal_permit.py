"""Turn-scoped causal permit for the Claude Code nunchi gate.

Because the Claude Code inbound gate (``UserPromptSubmit``) and outbound gate
(``PreToolUse``) run as *separate processes*, the outbound gate has no memory of
which message a reply was composed for. It currently reverse-scans the
transcript and judges the *newest* inbound line — so a peer message that lands
while the agent is composing steals the causal role and the already-composed
reply dies as a false ``PASS`` (the "how's everyone" bug, 2026-07-10).

This module bridges that gap with the smallest possible state: a record of the
*origin* message an admitted turn is composing for. It is emphatically **not** a
service queue / obligation ledger:

- **Session-scoped.** A permit never binds a different session; a restart cannot
  resurrect one.
- **Newest wins.** A later admit for the same (session, chat) supersedes the
  prior permit — we bind the *current* composition, never an oldest-FIFO one.
- **Short-lived.** Past its TTL (one active-turn lease) it is dead. A same-turn
  transport retry fits inside the lease; a future conversational turn does not.
- **Only admits write it.** A ``PASS`` on an unrelated peer line records
  nothing and never mutates an open permit.

Whether an origin is still *worth* answering — the room may have moved on — is
the classifier's judgment, not this module's. A drifted thread is a correct
``PASS``; this module only stops the integration from judging the *wrong*
message. It never wakes anything to necro a cold thread.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

_DEFAULT_PATH = Path.home() / ".nunchi" / "fable-permits.json"
#: One active-turn lease. Long enough for a slow compose + a same-turn retry,
#: short enough that a later turn cannot consume a stale permit.
_DEFAULT_TTL_SECONDS = 300.0

_UNIT_SEP = "\x1f"


def permit_path() -> Path:
    return Path(os.environ.get("NUNCHI_PERMIT_PATH") or _DEFAULT_PATH)


def permit_ttl() -> float:
    try:
        return float(os.environ.get("NUNCHI_PERMIT_TTL_SECONDS") or _DEFAULT_TTL_SECONDS)
    except ValueError:
        return _DEFAULT_TTL_SECONDS


def _key(session_id: str, chat_id: str) -> str:
    return f"{session_id}{_UNIT_SEP}{chat_id}"


def write_permit(
    session_id: str,
    chat_id: str,
    origin_message_id: str,
    origin_author: str = "",
    origin_ts: str = "",
    *,
    path: Path | None = None,
    now: float | None = None,
) -> None:
    """Record the origin of the current composition (call at inbound *admit*).

    Newest-wins: overwrites any prior permit for this (session, chat). Best-effort
    and atomic; a write failure degrades to legacy binding, never to a crash.
    """
    if not (session_id and chat_id and origin_message_id):
        return
    path = path or permit_path()
    now = time.time() if now is None else now
    store = _load(path)
    store[_key(session_id, chat_id)] = {
        "session_id": session_id,
        "chat_id": chat_id,
        "origin_message_id": origin_message_id,
        "origin_author": origin_author,
        "origin_ts": origin_ts,
        "created_at": now,
    }
    _atomic_write(path, store)


def read_permit(
    session_id: str,
    chat_id: str,
    *,
    path: Path | None = None,
    now: float | None = None,
    ttl: float | None = None,
) -> dict | None:
    """Return the fresh, same-session permit for this composition, or ``None``.

    Returns ``None`` (→ legacy newest-inbound binding) when there is no permit,
    the permit is from another session, or it has outlived its TTL. Never necros
    a past turn's permit.
    """
    if not (session_id and chat_id):
        return None
    path = path or permit_path()
    now = time.time() if now is None else now
    ttl = permit_ttl() if ttl is None else ttl
    permit = _load(path).get(_key(session_id, chat_id))
    if not isinstance(permit, dict):
        return None
    if permit.get("session_id") != session_id:  # never cross a session boundary
        return None
    if not permit.get("origin_message_id"):
        return None
    if now - float(permit.get("created_at") or 0.0) > ttl:  # stale: a past turn
        return None
    return permit


def clear_permit(session_id: str, chat_id: str, *, path: Path | None = None) -> None:
    """Close the permit once its turn's send has been decided (allow or deny)."""
    if not (session_id and chat_id):
        return
    path = path or permit_path()
    store = _load(path)
    if store.pop(_key(session_id, chat_id), None) is not None:
        _atomic_write(path, store)


def _load(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: Path, store: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".permit-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(store, fh)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        pass  # non-fatal: the gate falls back to legacy binding
