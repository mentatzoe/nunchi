"""Shared ACK policy, authenticated capability, and at-most-once journal."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterator

from .errors import ValidationError
from .receipts import PersistenceError

try:
    import fcntl
except ImportError:  # pragma: no cover - durable ACK is supported on POSIX hosts.
    fcntl = None


@dataclass(frozen=True)
class AckPolicy:
    enabled: bool = True
    reaction: str = "👂"
    provenance: str = "trusted:ack-policy/default@1"

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("ACK enabled must be a boolean")
        if not isinstance(self.reaction, str) or not self.reaction:
            raise ValueError("ACK reaction must be non-empty")
        if len(self.reaction.encode("utf-8")) > 64:
            raise ValueError("ACK reaction must be at most 64 UTF-8 bytes")
        if not isinstance(self.provenance, str) or not self.provenance:
            raise ValueError("ACK policy provenance must be non-empty")


@dataclass(frozen=True)
class ReactionCapability:
    """Authenticated native reaction facts supplied by a platform adapter."""

    supported: bool
    authenticated: bool
    operations: tuple[str, ...] = ()
    reactions: tuple[str, ...] = ()
    permissions_revision: str = "unavailable"
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.supported, bool) or not isinstance(self.authenticated, bool):
            raise ValueError("reaction capability booleans are invalid")
        if any(item not in ("add", "remove") for item in self.operations):
            raise ValueError("reaction capability operation is unsupported")
        if len(self.operations) != len(set(self.operations)):
            raise ValueError("reaction capability operations must be unique")
        if not all(isinstance(item, str) and item for item in self.reactions):
            raise ValueError("reaction capability reactions must be non-empty strings")
        if not isinstance(self.permissions_revision, str) or not self.permissions_revision:
            raise ValueError("reaction permissions revision must be non-empty")
        if not isinstance(self.detail, str):
            raise ValueError("reaction capability detail must be a string")

    def allows(self, reaction: str, operation: str = "add") -> bool:
        return (
            self.supported
            and self.authenticated
            and operation in self.operations
            and ("*" in self.reactions or reaction in self.reactions)
        )

    def document(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "authenticated": self.authenticated,
            "operations": list(self.operations),
            "reactions": list(self.reactions),
            "permissions_revision": self.permissions_revision,
            **({"detail": self.detail} if self.detail else {}),
        }


UNAVAILABLE_REACTION_CAPABILITY = ReactionCapability(
    supported=False,
    authenticated=False,
    permissions_revision="unavailable",
    detail="adapter did not attest native reaction capability",
)


def reaction_capability(value: Any) -> ReactionCapability:
    if isinstance(value, ReactionCapability):
        return value
    if value is None:
        return UNAVAILABLE_REACTION_CAPABILITY
    if not isinstance(value, Mapping):
        raise ValidationError("reaction capability must be an object")
    required = {
        "supported",
        "authenticated",
        "operations",
        "reactions",
        "permissions_revision",
    }
    optional = {"detail"}
    if required - set(value) or set(value) - (required | optional):
        raise ValidationError("reaction capability has a missing or unexpected field")
    try:
        return ReactionCapability(
            supported=value["supported"],
            authenticated=value["authenticated"],
            operations=tuple(value["operations"]),
            reactions=tuple(value["reactions"]),
            permissions_revision=value["permissions_revision"],
            detail=value.get("detail", ""),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"reaction capability is invalid: {exc}") from exc


class AckJournal:
    """Durably reserve an ACK before effect so replay cannot duplicate it.

    The stable ACK key intentionally excludes process lifecycle and scheduler
    generation.  Those facts are retained in the reservation binding, while
    the stable key prevents the same participant/reaction/message tuple from
    being emitted again after restart.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._records: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.RLock()
        if self.path is not None:
            if fcntl is None:
                raise PersistenceError("durable ACK journal requires process locking")
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.exists():
                self._load()

    @contextmanager
    def _process_lock(self, *, timeout: float | None = None) -> Iterator[None]:
        if self.path is None:
            yield
            return
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise PersistenceError(f"could not lock ACK journal: {exc}") from exc
        if fcntl is None:
            os.close(fd)
            raise PersistenceError("durable ACK journal requires process locking")
        locker = fcntl
        acquired = False
        try:
            self._acquire_flock(fd, timeout)
            acquired = True
            if self.path.exists():
                self._load()
            else:
                self._records = {}
            yield
        except OSError as exc:
            raise PersistenceError(f"could not lock ACK journal: {exc}") from exc
        finally:
            if acquired:
                locker.flock(fd, locker.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _acquire_flock(fd: int, timeout: float | None) -> None:
        """Take the shared journal lock. ``None`` waits; a number is a bound.

        The bounded path uses a non-blocking lock so a contending writer cannot
        pin the caller past the opportunity deadline. It does not run on the
        gateway event loop; the async ACK path calls it from a worker thread.
        """

        assert fcntl is not None
        if timeout is None:
            fcntl.flock(fd, fcntl.LOCK_EX)
            return
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout < 0
        ):
            raise PersistenceError("ACK journal lock timeout is invalid")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PersistenceError(
                        "ACK journal lock was not acquired before the deadline"
                    ) from exc
                time.sleep(min(0.005, remaining))

    @staticmethod
    def ack_id(binding: Mapping[str, Any]) -> str:
        stable = {
            name: binding[name]
            for name in (
                "participant_id",
                "actor_id",
                "platform",
                "room_id",
                "continuity_scope_id",
                "target_event_id",
                "reaction",
                "operation",
            )
        }
        return "ack:" + hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_binding(value: Any) -> dict[str, Any]:
        required = {
            "request_id",
            "participant_id",
            "actor_id",
            "platform",
            "room_id",
            "continuity_scope_id",
            "target_event_id",
            "reaction",
            "operation",
            "opportunity_generation",
            "lifecycle_id",
            "deadline_id",
            "permissions_revision",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise ValidationError("ACK binding has an invalid closed shape")
        checked = dict(value)
        for name in required - {"opportunity_generation"}:
            if not isinstance(checked[name], str) or not checked[name]:
                raise ValidationError(f"ACK binding {name} must be non-empty")
        generation = checked["opportunity_generation"]
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ValidationError("ACK opportunity generation must be positive")
        if checked["operation"] != "add":
            raise ValidationError("core ACK operation must be add")
        return checked

    def _load(self) -> None:
        assert self.path is not None
        loaded: dict[str, list[dict[str, Any]]] = {}
        try:
            with self.path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if not isinstance(record, Mapping) or set(record) - {
                        "schema_version",
                        "ack_id",
                        "state",
                        "binding",
                        "delivery",
                        "detail",
                    }:
                        raise ValidationError(f"invalid ACK journal line {line_number}")
                    if record.get("schema_version") != 1 or record.get("state") not in (
                        "reserved",
                        "settled",
                    ):
                        raise ValidationError(f"invalid ACK journal state at line {line_number}")
                    ack_id = record.get("ack_id")
                    if not isinstance(ack_id, str) or not ack_id:
                        raise ValidationError(f"invalid ACK ID at line {line_number}")
                    if record["state"] == "reserved":
                        binding = self._validate_binding(record.get("binding"))
                        if ack_id != self.ack_id(binding) or ack_id in loaded:
                            raise ValidationError(f"invalid ACK reservation at line {line_number}")
                        loaded[ack_id] = [deepcopy(dict(record))]
                    else:
                        if ack_id not in loaded or len(loaded[ack_id]) != 1:
                            raise ValidationError(f"orphan ACK settlement at line {line_number}")
                        if record.get("delivery") not in (
                            "sent",
                            "failed",
                            "unknown",
                            "unavailable",
                        ):
                            raise ValidationError(f"invalid ACK delivery at line {line_number}")
                        loaded[ack_id].append(deepcopy(dict(record)))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise PersistenceError(f"ACK journal {self.path} is untrustworthy: {exc}") from exc
        self._records = loaded

    def _append(
        self, record: Mapping[str, Any], *, deadline: float | None = None,
        abandoned: threading.Event | None = None,
        confirm: Callable[[], None] | None = None,
    ) -> None:
        """Append under the journal locks, withdrawing an uncertain final write.

        A deadline bounds lock waits, not a kernel call already in progress.
        Recheck after file setup and each write/sync. If completion is late,
        restore the previous prefix before releasing the locks; the reservation
        remains the no-retry fence. Rollback I/O itself must remain owned too.
        """
        def check() -> None:
            self._ensure_deadline(deadline)
            if abandoned is not None and abandoned.is_set():
                raise PersistenceError("ACK persistence was abandoned")

        check()
        if self.path is None:
            if confirm is not None:
                confirm()
            return
        existed = self.path.exists()
        payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        offset = None
        writing = False
        try:
            offset = os.fstat(fd).st_size
            check()
            writing = True
            if os.write(fd, payload) != len(payload):
                raise OSError("short ACK journal write")
            check()
            os.fsync(fd)
            check()
            if not existed:
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    check()
                    os.fsync(directory_fd)
                    check()
                finally:
                    os.close(directory_fd)
            if confirm is not None:
                # The observer accepts the durable commit here, not when an
                # executor future is eventually delivered to the event loop.
                confirm()
        except (OSError, PersistenceError) as exc:
            if writing and offset is not None:
                # No other journal writer can append while we own both locks.
                # Never remove the previously durable reservation on settlement.
                os.ftruncate(fd, offset)
                os.fsync(fd)
            raise PersistenceError(f"could not durably append ACK state: {exc}") from exc
        finally:
            os.close(fd)

    @staticmethod
    def _absolute_deadline(
        timeout: float | None,
        deadline: float | None,
    ) -> float | None:
        """Return one monotonic budget. A relative timeout must not extend it."""

        if deadline is not None:
            if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
                raise PersistenceError("ACK journal deadline is invalid")
            return deadline
        if timeout is None:
            return None
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout < 0
        ):
            raise PersistenceError("ACK journal lock timeout is invalid")
        return time.monotonic() + timeout

    def _acquire_thread_lock(self, deadline: float | None) -> None:
        """Take the in-process lock without starting a new budget afterwards."""

        if deadline is None:
            self._lock.acquire()
            return
        remaining = deadline - time.monotonic()
        if remaining < 0:
            remaining = 0
        if not self._lock.acquire(timeout=remaining):
            raise PersistenceError(
                "ACK journal lock was not acquired before the deadline"
            )

    @staticmethod
    def _ensure_deadline(deadline: float | None) -> None:
        if deadline is not None and time.monotonic() >= deadline:
            raise PersistenceError("ACK persistence deadline exhausted")

    def _lock_timeout(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        self._ensure_deadline(deadline)
        return max(0.0, deadline - time.monotonic())

    def reserve(
        self,
        binding: Mapping[str, Any],
        *,
        timeout: float | None = None,
        deadline: float | None = None,
    ) -> tuple[str, bool]:
        checked = self._validate_binding(binding)
        ack_id = self.ack_id(checked)
        absolute = self._absolute_deadline(timeout, deadline)
        self._acquire_thread_lock(absolute)
        try:
            with self._process_lock(timeout=self._lock_timeout(absolute)):
                self._ensure_deadline(absolute)
                if ack_id in self._records:
                    return ack_id, False
                record = {
                    "schema_version": 1,
                    "ack_id": ack_id,
                    "state": "reserved",
                    "binding": checked,
                }
                self._ensure_deadline(absolute)
                self._append(record, deadline=absolute)
                self._records[ack_id] = [deepcopy(record)]
                return ack_id, True
        finally:
            self._lock.release()

    def settle(
        self,
        ack_id: str,
        *,
        delivery: str,
        detail: str = "",
        timeout: float | None = None,
        deadline: float | None = None,
        abandoned: threading.Event | None = None,
        confirm: Callable[[str], None] | None = None,
    ) -> str:
        """Return the actual delivery; confirm at commit, not at worker return.

        ``confirm`` must be a non-blocking observer. It may reject an abandoned
        commit with PersistenceError, causing the unconfirmed append to roll back.
        """
        if delivery not in ("sent", "failed", "unknown", "unavailable"):
            raise ValidationError("ACK settlement delivery is invalid")
        if not isinstance(detail, str):
            raise ValidationError("ACK settlement detail must be a string")
        absolute = self._absolute_deadline(timeout, deadline)
        self._acquire_thread_lock(absolute)
        try:
            with self._process_lock(timeout=self._lock_timeout(absolute)):
                self._ensure_deadline(absolute)
                records = self._records.get(ack_id)
                if records is None:
                    raise ValidationError("ACK settlement has no reservation")
                if len(records) > 1:
                    actual = str(records[-1]["delivery"])
                    if confirm is not None:
                        confirm(actual)
                    return actual
                record = {
                    "schema_version": 1,
                    "ack_id": ack_id,
                    "state": "settled",
                    "delivery": delivery,
                    **({"detail": detail} if detail else {}),
                }
                self._ensure_deadline(absolute)
                self._append(
                    record, deadline=absolute, abandoned=abandoned,
                    confirm=(lambda: confirm(delivery)) if confirm is not None else None,
                )
                records.append(deepcopy(record))
                return delivery
        finally:
            self._lock.release()

    def records(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            with self._process_lock():
                return tuple(
                    deepcopy(record)
                    for records in self._records.values()
                    for record in records
                )
