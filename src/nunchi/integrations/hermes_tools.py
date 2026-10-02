"""Plugin-owned native invocation ledger, not a replacement authority engine.

A claim is durable before handing control to Hermes. A returned value is not
proof of an effect: native approvals/guards may have declined the invocation.
Unknown and returned claims both remain reserved across process restarts.
"""
from __future__ import annotations

import json
import importlib
import inspect
import os
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import stat
import time
from typing import Any, Callable, Iterable, Iterator, Mapping

from ..errors import ValidationError
from ..receipts import PersistenceError


class NativeInvocationJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            self._check_file()
            with self._connect() as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS invocations ("
                    "identity TEXT PRIMARY KEY, binding TEXT NOT NULL, "
                    "invocation TEXT NOT NULL, effect TEXT NOT NULL)"
                )
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (OSError, sqlite3.Error) as exc:
            raise PersistenceError("native invocation ledger unavailable") from exc

    def _check_file(self) -> None:
        info = self.path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_uid != os.getuid()
        ):
            raise PersistenceError("native invocation ledger is not a private regular file")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._check_file()
        # Native batches reserve under the runtime lock but finish outside it.
        # Allow their short durable writes to settle instead of spuriously
        # refusing another invocation. This never retries a native effect;
        # callers still recheck cancellation/deadline after reservation.
        db = sqlite3.connect(self.path, timeout=0.25)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, identity: str, binding: Mapping[str, Any]) -> bool:
        try:
            payload = json.dumps(dict(binding), sort_keys=True, separators=(",", ":"), allow_nan=False)
            with self._connect() as db:
                result = db.execute(
                    "INSERT OR IGNORE INTO invocations VALUES (?, ?, 'committed', 'unknown')",
                    (identity, payload),
                )
                return result.rowcount == 1
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise PersistenceError("could not reserve native invocation") from exc

    def finish(self, identity: str, invocation: str) -> None:
        if invocation not in {"returned", "raised", "cancelled-before-handoff"}:
            raise ValueError("unsupported native invocation outcome")
        try:
            with self._connect() as db:
                result = db.execute(
                    "UPDATE invocations SET invocation = ? WHERE identity = ?",
                    (invocation, identity),
                )
                if result.rowcount != 1:
                    raise PersistenceError("native invocation has no durable claim")
        except (OSError, sqlite3.Error) as exc:
            raise PersistenceError("could not record native invocation outcome") from exc

    def records(self) -> list[dict[str, Any]]:
        try:
            with self._connect() as db:
                return [
                    {"identity": identity, "binding": json.loads(binding),
                     "invocation": invocation, "effect": effect}
                    for identity, binding, invocation, effect in db.execute(
                        "SELECT identity, binding, invocation, effect FROM invocations ORDER BY rowid"
                    )
                ]
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise PersistenceError("could not read native invocation ledger") from exc


def install_approval_boundary(
    active_trace: Callable[[], Any],
    configured_route: Callable[[], bool],
    set_attribute: Callable[[Any, str, Any], None],
    runtimes: Iterable[Any],
) -> None:
    """Check native approval waits before and after resolution, never grant them.

    0.19 owns the wait in approval.py; 0.21 binds its shared gateway helper
    by name, whose global _poll_event covers both leaders and followers.
    Unknown private shapes reject activation before any callback is registered.
    """
    try:
        approval = importlib.import_module("tools.approval")
        interrupt = importlib.import_module("tools.interrupt")
        decision = approval._await_gateway_decision
        if decision.__module__ == "tools.approval_gateway_wait":
            target = importlib.import_module("tools.approval_gateway_wait")
            if decision is not target._await_gateway_decision:
                raise ValueError("approval helper binding changed")
            name = "_poll_event"
            required = {"event", "session_key", "interrupt_log"}
            denied: Any = "interrupted"
        elif decision.__module__ == "tools.approval":
            target, name = approval, "_await_gateway_decision"
            required = {"session_key", "notify_cb", "approval_data", "surface"}
            denied = {"resolved": True, "choice": "deny", "reason": None}
        else:
            raise ValueError("foreign approval implementation")
        current = getattr(target, name)
        if getattr(current, "__nunchi_approval_boundary__", False):
            return
        if (
            current.__module__ != target.__name__
            or not required.issubset(inspect.signature(current).parameters)
            or "is_interrupted" not in inspect.getsource(current)
            or not {"active", "thread_id"}.issubset(inspect.signature(interrupt.set_interrupt).parameters)
            or not callable(interrupt.is_interrupted)
        ):
            raise ValueError("native interrupt/approval wait shape changed")
    except (ImportError, AttributeError, TypeError, ValueError, OSError) as exc:
        raise ValidationError("unsupported Hermes native approval/interrupt boundary") from exc

    def current_opportunity() -> bool:
        trace = active_trace()
        if trace is None:
            return not configured_route()
        runtime = trace.runtime
        with runtime._lock:
            valid = (
                runtime._active_trace is trace
                and not trace.token.cancel_event.is_set()
                and runtime.scheduler.is_current(trace.token)
                and time.monotonic() < trace.deadline
            )
        if not valid:
            runtime.expire_stock_turn(trace)
        return valid

    def checked_wait(*args: Any, **kwargs: Any) -> Any:
        if not current_opportunity():
            return dict(denied) if isinstance(denied, dict) else denied
        result = current(*args, **kwargs)
        if not current_opportunity():
            return dict(denied) if isinstance(denied, dict) else denied
        return result

    checked_wait.__nunchi_approval_boundary__ = True  # type: ignore[attr-defined]
    # Preserve origin for repeated registration's shape selection.
    checked_wait.__module__ = current.__module__
    set_attribute(target, name, checked_wait)
    for runtime in runtimes:
        runtime._native_interrupt = interrupt.set_interrupt
