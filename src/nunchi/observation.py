"""Canonical observation, bounded current context, and host-only continuation."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import threading
from typing import Any, Literal
from uuid import uuid4

from .errors import NunchiError, ValidationError
from .receipts import PersistenceError, ReceiptJournal
from .v2_contracts import (
    validate_attention_request,
    validate_canonical_event,
)


class ObservationError(NunchiError):
    """An operational failure after a routable canonical event exists."""

    label = "observation error"


class SnapshotUnavailable(ObservationError):
    """A valid current snapshot could not be assembled."""


@dataclass(frozen=True)
class ObservationLimits:
    retention_events: int = 512
    retention_bytes: int = 1_048_576
    snapshot_events: int = 24
    snapshot_bytes: int = 32_768
    snapshot_age_seconds: int = 86_400
    continuation_events: int = 24
    continuation_bytes: int = 32_768
    continuation_ttl_seconds: int = 300
    continuation_handles: int = 64

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ParticipantBinding:
    participant_id: str
    actor_id: str
    platform: str
    room_id: str
    continuity_scope_id: str
    names: tuple[str, ...] = ()
    role: str | None = None
    description: str | None = None
    room_name: str | None = None
    room_kind: Literal["group", "direct", "unknown"] = "unknown"
    provenance: str = "trusted-installation"
    hermes_profile: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "participant_id",
            "actor_id",
            "platform",
            "room_id",
            "continuity_scope_id",
            "provenance",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty trusted value")
        if self.room_kind not in ("group", "direct", "unknown"):
            raise ValueError("room_kind must be group, direct, or unknown")
        if any(not isinstance(name, str) for name in self.names):
            raise ValueError("names must be strings")
        if self.hermes_profile is not None and (
            not isinstance(self.hermes_profile, str) or not self.hermes_profile
        ):
            raise ValueError("hermes_profile must be non-empty when present")

    def self_document(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "participant_id": self.participant_id,
            "actor_id": self.actor_id,
        }
        if self.names:
            result["names"] = list(self.names)
        if self.role is not None:
            result["role"] = self.role
        if self.description is not None:
            result["description"] = self.description
        return result

    def room_document(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "platform": self.platform,
            "id": self.room_id,
            "continuity_scope_id": self.continuity_scope_id,
            "kind": self.room_kind,
        }
        if self.room_name is not None:
            result["name"] = self.room_name
        return result


@dataclass(frozen=True)
class DeliveryAudit:
    delivery_id: str
    outcome: Literal[
        "recorded",
        "exact-self-context",
        "exact-duplicate",
        "unconstructable",
        "route-rejected",
        "continuity-gap",
    ]
    detail: str
    event_id: str | None = None


@dataclass(frozen=True)
class ObservationResult:
    audit: DeliveryAudit
    wake_eligible: bool


@dataclass
class _ContinuationState:
    handle_id: str
    request_id: str
    binding: dict[str, str]
    expires_at: datetime
    events: list[dict[str, Any]]
    actors: dict[str, dict[str, Any]]
    can_fetch_before: bool
    can_fetch_after: bool
    can_fetch_around_event: bool
    delivered_event_ids: set[str]
    cursors: dict[str, tuple[str, str, tuple[int, ...]]]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _event_refs(event: Mapping[str, Any]) -> tuple[str, ...]:
    if event["type"] == "message":
        return tuple(
            ref
            for ref in (
                event.get("reply_to_event_id"),
                event.get("thread_root_event_id"),
            )
            if ref
        )
    if event["type"] == "reaction":
        return (event["target_event_id"],)
    return ()


def _actor_refs(event: Mapping[str, Any]) -> set[str]:
    if event["type"] == "message":
        return {event["author_id"], *(event["mentioned_actor_ids"] or ())}
    if event["type"] == "reaction":
        return {event["author_id"]}
    result = {event["subject_actor_id"]}
    if event.get("caused_by_actor_id"):
        result.add(event["caused_by_actor_id"])
    return result


def _context_actors(
    events: list[Mapping[str, Any]],
    actors: Mapping[str, Mapping[str, Any]],
    *,
    include: set[str] | None = None,
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    referenced = set(include or ())
    for event in events:
        referenced.update(_actor_refs(event))
    selected = {
        actor_id: actors[actor_id]
        for actor_id in referenced
        if actor_id in actors
    }
    return selected, referenced - set(selected)


def _context_byte_count(
    events: list[Mapping[str, Any]],
    actors: Mapping[str, Mapping[str, Any]],
) -> int:
    """Count the complete variable factual context, including actor metadata."""
    return len(_canonical_bytes({"actors": actors, "events": events}))


class ObservationProvider:
    """One participant/room observation provider.

    Trusted routing is construction-time state.  Room payloads cannot change
    the participant, self actor, room, continuity scope, budgets, or receipt
    destination.
    """

    def __init__(
        self,
        binding: ParticipantBinding,
        *,
        limits: ObservationLimits | None = None,
        receipts: ReceiptJournal | None = None,
        persistence_path: str | Path | None = None,
        continuity: Literal["restart-safe", "session-only", "unknown"] | None = None,
        event_visibility: Mapping[str, str] | None = None,
    ) -> None:
        self.binding = binding
        self.limits = limits or ObservationLimits()
        self.receipts = receipts or ReceiptJournal()
        self._path = Path(persistence_path) if persistence_path is not None else None
        self._audit_path = (
            self._path.with_name(self._path.name + ".delivery-audit.jsonl")
            if self._path is not None
            else None
        )
        self._replay_path = (
            self._path.with_name(self._path.name + ".replay-reservations.jsonl")
            if self._path is not None
            else None
        )
        self._continuity_path = (
            self._path.with_name(self._path.name + ".continuity.json")
            if self._path is not None
            else None
        )
        self._continuity = continuity or (
            "restart-safe" if self._path is not None else "session-only"
        )
        if self._continuity == "restart-safe" and self._path is None:
            raise ValueError("restart-safe continuity requires a persistence path")
        if self._continuity not in ("restart-safe", "session-only", "unknown"):
            raise ValueError("invalid continuity")
        self._visibility = dict(
            event_visibility
            or {
                "message": "history-and-live" if self._path else "live-only",
                "reaction": "live-only",
                "membership": "live-only",
            }
        )
        self._events: deque[dict[str, Any]] = deque()
        self._actors: dict[str, dict[str, Any]] = {
            binding.actor_id: {
                "display_name": binding.names[0] if binding.names else binding.actor_id,
                "kind": "bot",
            }
        }
        self._delivery_ids: set[str] = set()
        self._event_ids: set[str] = set()
        self._accepted_event_ids: set[str] = set()
        self._delivery_by_event: dict[str, str] = {}
        self._audits: list[DeliveryAudit] = []
        self._reserved_replays: set[tuple[str, str]] = set()
        self._committed_replays: set[tuple[str, str]] = set()
        self._continuations: dict[str, _ContinuationState] = {}
        self._restart_gap = False
        self._retention_evicted_before = False
        self._lock = threading.RLock()
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._continuity_path is not None and self._continuity_path.exists():
                try:
                    state = json.loads(self._continuity_path.read_text())
                except (OSError, json.JSONDecodeError) as exc:
                    raise PersistenceError(
                        f"observation continuity state is untrustworthy: {exc}"
                    ) from exc
                if state != {"schema_version": 2, "has_gap": True}:
                    raise PersistenceError(
                        "observation continuity state has an invalid closed shape"
                    )
                self._restart_gap = True
                self._continuity = "unknown"
            if self._replay_path is not None and self._replay_path.exists():
                self._load_replay_index()
            if self._audit_path is not None and self._audit_path.exists():
                self._load_audit_index()
            if self._path.exists():
                self._load()
            if self._reserved_replays - self._committed_replays:
                self._restart_gap = True
                self._continuity = "unknown"
            if len(self._accepted_event_ids) > len(self._events):
                self._retention_evicted_before = True

    def _load_replay_index(self) -> None:
        """Restore reservations written before mutable observation content."""
        assert self._replay_path is not None
        try:
            with self._replay_path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if (
                        not isinstance(record, dict)
                        or set(record)
                        != {"schema_version", "delivery_id", "event_id"}
                        or record["schema_version"] != 2
                        or any(
                            not isinstance(record[name], str) or not record[name]
                            for name in ("delivery_id", "event_id")
                        )
                    ):
                        raise ValueError(
                            f"invalid replay reservation at line {line_number}"
                        )
                    pair = (record["delivery_id"], record["event_id"])
                    if pair in self._reserved_replays:
                        raise ValueError(
                            f"duplicate replay reservation at line {line_number}"
                        )
                    self._reserved_replays.add(pair)
                    self._delivery_ids.add(record["delivery_id"])
                    self._event_ids.add(record["event_id"])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PersistenceError(
                f"observation replay reservations are untrustworthy: {exc}"
            ) from exc

    def _load_audit_index(self) -> None:
        """Restore content-free exact replay identities from durable audit."""
        assert self._audit_path is not None
        outcomes = {
            "recorded",
            "exact-self-context",
            "exact-duplicate",
            "unconstructable",
            "route-rejected",
            "continuity-gap",
        }
        try:
            with self._audit_path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if (
                        not isinstance(record, dict)
                        or set(record)
                        != {
                            "schema_version",
                            "delivery_id",
                            "outcome",
                            "detail",
                            "event_id",
                        }
                        or record["schema_version"] != 2
                        or not isinstance(record["delivery_id"], str)
                        or not record["delivery_id"]
                        or record["outcome"] not in outcomes
                        or not isinstance(record["detail"], str)
                        or (
                            record["event_id"] is not None
                            and (
                                not isinstance(record["event_id"], str)
                                or not record["event_id"]
                            )
                        )
                    ):
                        raise ValueError(f"invalid audit record at line {line_number}")
                    self._delivery_ids.add(record["delivery_id"])
                    if record["event_id"] is not None:
                        self._event_ids.add(record["event_id"])
                        if record["outcome"] in (
                            "recorded",
                            "exact-self-context",
                        ):
                            self._accepted_event_ids.add(record["event_id"])
                            self._committed_replays.add(
                                (record["delivery_id"], record["event_id"])
                            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PersistenceError(
                f"observation delivery audit is untrustworthy: {exc}"
            ) from exc

    def _load(self) -> None:
        assert self._path is not None
        try:
            with self._path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if set(entry) != {"delivery_id", "event", "actors"}:
                        raise ValueError(f"line {line_number} has unknown fields")
                    event = validate_canonical_event(entry["event"])
                    actors = entry["actors"]
                    if not isinstance(actors, dict):
                        raise ValueError(f"line {line_number} actors must be an object")
                    self._append_memory(entry["delivery_id"], event, actors)
        except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            self._restart_gap = True
            self._continuity = "unknown"
            raise PersistenceError(
                f"observation store {self._path} is not trustworthy: {exc}"
            ) from exc
        self._persist_snapshot()

    def _persist_snapshot(self) -> None:
        """Atomically retain only the configured bounded observation horizon."""
        if self._path is None:
            return
        lines: list[bytes] = []
        for event in self._events:
            lines.append(_canonical_bytes(self._retained_entry(event)) + b"\n")
        payload = b"".join(lines)
        temporary = self._path.with_name(self._path.name + ".tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        try:
            written = os.write(fd, payload)
            if written != len(payload):
                raise OSError(f"short write ({written}/{len(payload)} bytes)")
            os.fsync(fd)
        except OSError as exc:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise PersistenceError(
                f"could not atomically retain bounded canonical observations: {exc}"
            ) from exc
        finally:
            os.close(fd)
        try:
            os.replace(temporary, self._path)
            directory_fd = os.open(self._path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise PersistenceError(
                f"bounded observation replacement is uncertain: {exc}"
            ) from exc

    def _record_audit(self, audit: DeliveryAudit) -> None:
        if self._audit_path is not None:
            existed = self._audit_path.exists()
            payload = _canonical_bytes(
                {
                    "schema_version": 2,
                    "delivery_id": audit.delivery_id,
                    "outcome": audit.outcome,
                    "detail": audit.detail,
                    "event_id": audit.event_id,
                }
            ) + b"\n"
            fd = os.open(
                self._audit_path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                if os.write(fd, payload) != len(payload):
                    raise OSError("short delivery-audit write")
                os.fsync(fd)
            except OSError as exc:
                raise PersistenceError(
                    f"observation delivery audit is uncertain: {exc}"
                ) from exc
            finally:
                os.close(fd)
            if not existed:
                try:
                    directory_fd = os.open(self._audit_path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError as exc:
                    raise PersistenceError(
                        "observation delivery-audit directory persistence is uncertain"
                    ) from exc
        self._audits.append(audit)
        self._delivery_ids.add(audit.delivery_id)
        if audit.event_id is not None:
            self._event_ids.add(audit.event_id)
            if audit.outcome in ("recorded", "exact-self-context"):
                self._committed_replays.add((audit.delivery_id, audit.event_id))

    def _reserve_replay(self, delivery_id: str, event_id: str) -> None:
        """Durably make one native delivery non-wakeable before content writes."""
        pair = (delivery_id, event_id)
        if pair in self._reserved_replays:
            raise PersistenceError("observation replay reservation already exists")
        if self._replay_path is not None:
            existed = self._replay_path.exists()
            payload = _canonical_bytes(
                {
                    "schema_version": 2,
                    "delivery_id": delivery_id,
                    "event_id": event_id,
                }
            ) + b"\n"
            fd = os.open(
                self._replay_path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                if os.write(fd, payload) != len(payload):
                    raise OSError("short replay-reservation write")
                os.fsync(fd)
            except OSError as exc:
                self._reserved_replays.add(pair)
                self._delivery_ids.add(delivery_id)
                self._event_ids.add(event_id)
                raise PersistenceError(
                    f"observation replay reservation is uncertain: {exc}"
                ) from exc
            finally:
                os.close(fd)
            self._reserved_replays.add(pair)
            self._delivery_ids.add(delivery_id)
            self._event_ids.add(event_id)
            if not existed:
                try:
                    directory_fd = os.open(self._replay_path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError as exc:
                    raise PersistenceError(
                        "observation replay-reservation directory persistence "
                        "is uncertain"
                    ) from exc
        else:
            self._reserved_replays.add(pair)
            self._delivery_ids.add(delivery_id)
            self._event_ids.add(event_id)

    def _mark_persistence_uncertain(self) -> None:
        self._restart_gap = True
        self._continuity = "unknown"
        self._continuations.clear()
        try:
            self._persist_gap_state()
        except (OSError, PersistenceError):
            # The durable replay reservation still prevents a stale wake after
            # restart even if the separate coverage marker cannot be replaced.
            pass

    def _persist_gap_state(self) -> None:
        if self._continuity_path is None:
            return
        temporary = self._continuity_path.with_name(
            self._continuity_path.name + ".tmp"
        )
        payload = b'{"has_gap":true,"schema_version":2}'
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError("short continuity-state write")
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, self._continuity_path)
            directory_fd = os.open(self._continuity_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise PersistenceError(
                f"observation continuity state is uncertain: {exc}"
            ) from exc

    def _append_memory(
        self,
        delivery_id: str,
        event: Mapping[str, Any],
        actors: Mapping[str, Any],
    ) -> None:
        checked_actors: dict[str, dict[str, Any]] = {}
        for actor_id, actor in actors.items():
            if not isinstance(actor_id, str) or not actor_id:
                raise ValidationError("actors keys must be non-empty strings")
            if not isinstance(actor, Mapping):
                raise ValidationError(f"actor {actor_id!r} must be an object")
            allowed = {"display_name", "kind"}
            if set(actor) - allowed:
                raise ValidationError(f"actor {actor_id!r} has unexpected fields")
            checked_actors[actor_id] = deepcopy(dict(actor))
        self._delivery_ids.add(delivery_id)
        self._event_ids.add(event["id"])
        self._accepted_event_ids.add(event["id"])
        self._delivery_by_event[event["id"]] = delivery_id
        self._events.append(deepcopy(dict(event)))
        self._actors.update(checked_actors)
        self._trim_retention()

    def _trim_retention(self) -> None:
        while len(self._events) > self.limits.retention_events:
            removed = self._events.popleft()
            self._delivery_by_event.pop(removed["id"], None)
            self._retention_evicted_before = True
        while (
            self._events
            and self._retained_persistence_bytes() > self.limits.retention_bytes
        ):
            removed = self._events.popleft()
            self._delivery_by_event.pop(removed["id"], None)
            self._retention_evicted_before = True
        referenced = {self.binding.actor_id}
        for event in self._events:
            referenced.update(_actor_refs(event))
        self._actors = {
            actor_id: actor
            for actor_id, actor in self._actors.items()
            if actor_id in referenced
        }

    def _retained_entry(self, event: Mapping[str, Any]) -> dict[str, Any]:
        actors, missing = _context_actors([event], self._actors)
        if missing:
            raise PersistenceError("retained observation actor metadata is incomplete")
        return {
            "delivery_id": self._delivery_by_event[event["id"]],
            "event": event,
            "actors": actors,
        }

    def _retained_persistence_bytes(self) -> int:
        return sum(
            len(_canonical_bytes(self._retained_entry(event))) + 1
            for event in self._events
        )

    def observe(
        self,
        *,
        delivery_id: str,
        event: Mapping[str, Any] | None,
        actors: Mapping[str, Any] | None,
        authorized_route: bool = True,
    ) -> ObservationResult:
        """Record one transport-attested delivery.

        Only ``wake_eligible=True`` may enter scheduling.  Self events are
        retained for later factual context but cannot wake this participant.
        """
        if not isinstance(delivery_id, str) or not delivery_id:
            raise ValidationError("delivery_id must be a non-empty transport value")
        if not authorized_route:
            audit = DeliveryAudit(delivery_id, "route-rejected", "trusted route rejected")
            with self._lock:
                self._record_audit(audit)
            return ObservationResult(audit, False)
        if event is None:
            audit = DeliveryAudit(
                delivery_id,
                "unconstructable",
                "payload could not produce the required native event facts",
            )
            with self._lock:
                self._record_audit(audit)
            return ObservationResult(audit, False)
        checked = validate_canonical_event(event)
        checked_actors = deepcopy(dict(actors or {}))
        refs = _actor_refs(checked)
        if not refs.issubset(set(checked_actors) | set(self._actors)):
            missing = ", ".join(sorted(refs - (set(checked_actors) | set(self._actors))))
            raise ValidationError(f"canonical event has unresolved actor references: {missing}")
        with self._lock:
            if delivery_id in self._delivery_ids or checked["id"] in self._event_ids:
                audit = DeliveryAudit(
                    delivery_id,
                    "exact-duplicate",
                    "exact retained delivery or native event ID",
                    checked["id"],
                )
                self._record_audit(audit)
                return ObservationResult(audit, False)
            previous = (
                deepcopy(self._events),
                deepcopy(self._actors),
                set(self._accepted_event_ids),
                dict(self._delivery_by_event),
                self._retention_evicted_before,
            )
            try:
                self._reserve_replay(delivery_id, checked["id"])
            except BaseException:
                self._mark_persistence_uncertain()
                raise
            self._append_memory(delivery_id, checked, checked_actors)
            try:
                self._persist_snapshot()
            except BaseException:
                (
                    self._events,
                    self._actors,
                    self._accepted_event_ids,
                    self._delivery_by_event,
                    self._retention_evicted_before,
                ) = previous
                self._mark_persistence_uncertain()
                raise
            if (
                checked.get("author_id") == self.binding.actor_id
                or checked.get("caused_by_actor_id") == self.binding.actor_id
            ):
                outcome = "exact-self-context"
                eligible = False
                detail = (
                    "exact transport self author or cause retained as context "
                    "without self wake"
                )
            else:
                outcome = "recorded"
                eligible = True
                detail = "canonical event recorded"
            audit = DeliveryAudit(delivery_id, outcome, detail, checked["id"])
            try:
                self._record_audit(audit)
            except BaseException:
                self._mark_persistence_uncertain()
                raise
            return ObservationResult(audit, eligible)

    def _selected_indices(self, trigger_event_id: str) -> tuple[list[int], set[str]]:
        events = list(self._events)
        by_id = {event["id"]: index for index, event in enumerate(events)}
        if trigger_event_id not in by_id:
            raise SnapshotUnavailable(
                f"trigger {trigger_event_id!r} is outside the retained observation horizon"
            )
        trigger_index = by_id[trigger_event_id]
        start = max(0, len(events) - self.limits.snapshot_events)
        selected = set(range(start, len(events)))
        selected.add(trigger_index)
        required = {trigger_index}
        pending = [trigger_index]
        while pending:
            index = pending.pop()
            for relation in _event_refs(events[index]):
                related = by_id.get(relation)
                if related is not None and related not in required:
                    required.add(related)
                    selected.add(related)
                    pending.append(related)

        truncated: set[str] = set()
        if len(selected) > self.limits.snapshot_events:
            removable = sorted(selected - required)
            while len(selected) > self.limits.snapshot_events and removable:
                selected.remove(removable.pop(0))
                truncated.add("events")
        if len(selected) > self.limits.snapshot_events:
            # Relation closure cannot be represented honestly inside the cap.
            raise SnapshotUnavailable(
                "trigger relation closure exceeds the configured event budget"
            )

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.limits.snapshot_age_seconds)
        for index in sorted(selected - required):
            raw = events[index].get("timestamp")
            try:
                timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
            except ValueError:
                timestamp = None
            if timestamp is not None and timestamp < cutoff:
                selected.remove(index)
                truncated.add("age")

        while selected:
            ordered = [events[index] for index in sorted(selected)]
            actors, missing = _context_actors(
                ordered,
                self._actors,
                include={self.binding.actor_id},
            )
            if missing:
                raise SnapshotUnavailable("retained event actor metadata is incomplete")
            if (
                _context_byte_count(ordered, actors)
                <= self.limits.snapshot_bytes
            ):
                break
            removable = sorted(selected - required)
            if not removable:
                raise SnapshotUnavailable(
                    "trigger relation closure exceeds the configured byte budget"
                )
            selected.remove(removable[0])
            truncated.add("bytes")
        return sorted(selected), truncated

    def build_snapshot(
        self,
        trigger_event_id: str,
        *,
        request_id: str | None = None,
        continuation: bool = True,
        record_receipt: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            all_events = list(self._events)
            indices, truncated = self._selected_indices(trigger_event_id)
            events = [deepcopy(all_events[index]) for index in indices]
            first = indices[0]
            last = indices[-1]
            retained_more_before = first > 0
            retained_more_after = last < len(all_events) - 1
            if retained_more_before or self._retention_evicted_before:
                truncated.add("events")
            raw_actors, missing = _context_actors(
                events,
                self._actors,
                include={self.binding.actor_id},
            )
            if missing:
                raise SnapshotUnavailable("retained event actor metadata is incomplete")
            actors = deepcopy(raw_actors)
            coverage: dict[str, Any] = {
                "max_events": self.limits.snapshot_events,
                "max_bytes": self.limits.snapshot_bytes,
                "max_age_seconds": self.limits.snapshot_age_seconds,
                "has_more_before": (
                    retained_more_before or self._retention_evicted_before
                ),
                "has_more_after": retained_more_after,
                "has_gaps": self._restart_gap or any(
                    b - a > 1 for a, b in zip(indices, indices[1:])
                ),
                "truncated_by": sorted(truncated),
                "continuity": self._continuity,
                "has_restart_gap": self._restart_gap,
                "event_visibility": deepcopy(self._visibility),
            }
            rid = request_id or f"{self.binding.platform}:{self.binding.room_id}:{uuid4()}"
            request: dict[str, Any] = {
                "schema_version": 2,
                "request_id": rid,
                "self": self.binding.self_document(),
                "room": self.binding.room_document(),
                "actors": actors,
                "events": events,
                "trigger_event_id": trigger_event_id,
                "coverage": coverage,
            }
            if continuation and (retained_more_before or retained_more_after):
                request["continuation"] = self._issue_continuation(
                    request_id=rid,
                    trigger_event_id=trigger_event_id,
                    events=all_events,
                    actors=self._actors,
                    delivered_event_ids={event["id"] for event in events},
                    can_fetch_before=retained_more_before,
                    can_fetch_after=retained_more_after,
                )
            checked = validate_attention_request(request)
            body = {
                "schema_version": 2,
                "trigger_event_id": trigger_event_id,
                "continuity_scope_id": self.binding.continuity_scope_id,
                "event_count": len(events),
                "byte_count": _context_byte_count(events, actors),
                "coverage": deepcopy(coverage),
                "included_event_ids": [event["id"] for event in events],
            }
            if record_receipt:
                self.receipts.append(
                    {
                        "request_id": rid,
                        "stage": "observation",
                        "writer": "observation-provider",
                        "body": body,
                    },
                    writer="observation-provider",
                )
            return checked

    def _issue_continuation(
        self,
        *,
        request_id: str,
        trigger_event_id: str,
        events: list[dict[str, Any]],
        actors: Mapping[str, Any],
        delivered_event_ids: set[str],
        can_fetch_before: bool,
        can_fetch_after: bool,
    ) -> dict[str, Any]:
        self._prune_continuations(
            datetime.now(timezone.utc),
            reserve_capacity=True,
        )
        handle_id = f"ctx:{secrets.token_urlsafe(24)}"
        binding = {
            "participant_id": self.binding.participant_id,
            "room_id": self.binding.room_id,
            "continuity_scope_id": self.binding.continuity_scope_id,
            "trigger_event_id": trigger_event_id,
        }
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.limits.continuation_ttl_seconds
        )
        state = _ContinuationState(
            handle_id=handle_id,
            request_id=request_id,
            binding=binding,
            expires_at=expires_at,
            events=deepcopy(events),
            actors=deepcopy(dict(actors)),
            can_fetch_before=can_fetch_before,
            can_fetch_after=can_fetch_after,
            can_fetch_around_event=can_fetch_before or can_fetch_after,
            delivered_event_ids=set(delivered_event_ids),
            cursors={},
        )
        self._continuations[handle_id] = state
        return {
            "handle_id": handle_id,
            "bound_to": deepcopy(binding),
            "can_fetch_before": state.can_fetch_before,
            "can_fetch_after": state.can_fetch_after,
            "can_fetch_around_event": state.can_fetch_around_event,
            "max_events_per_fetch": self.limits.continuation_events,
            "max_bytes_per_fetch": self.limits.continuation_bytes,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

    def _prune_continuations(
        self,
        current: datetime,
        *,
        reserve_capacity: bool = False,
    ) -> None:
        expired = [
            handle_id
            for handle_id, state in self._continuations.items()
            if current >= state.expires_at
        ]
        for handle_id in expired:
            self._continuations.pop(handle_id, None)
        if reserve_capacity:
            while len(self._continuations) >= self.limits.continuation_handles:
                self._continuations.pop(next(iter(self._continuations)))

    def fetch_context(
        self,
        request: Mapping[str, Any],
        *,
        host_context: Mapping[str, str],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Fulfil an I-010D fetch through exact host-supplied binding."""
        allowed = {
            "request_id",
            "handle_id",
            "direction",
            "anchor_event_id",
            "cursor",
            "max_events",
            "max_bytes",
        }
        required = {"request_id", "handle_id", "direction", "max_events", "max_bytes"}
        if not isinstance(request, Mapping) or set(request) - allowed or required - set(request):
            raise ValidationError("continuation fetch request has an invalid closed shape")
        for name in ("request_id", "handle_id"):
            if not isinstance(request[name], str) or not request[name]:
                raise ValidationError(f"continuation fetch {name} must be non-empty")
        if request["direction"] not in ("before", "after", "around"):
            raise ValidationError("continuation fetch direction is invalid")
        for name in ("max_events", "max_bytes"):
            value = request[name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValidationError(f"continuation fetch {name} must be positive")
        with self._lock:
            current = now or datetime.now(timezone.utc)
            self._prune_continuations(current)
            state = self._continuations.get(request["handle_id"])
            if state is None:
                raise ValidationError("continuation handle is unknown or expired")
            if request["request_id"] != state.request_id:
                raise ValidationError("continuation request ID does not match the issued handle")
            if dict(host_context) != state.binding:
                raise ValidationError("continuation host context does not match the issued binding")
            if request["max_events"] > self.limits.continuation_events:
                raise ValidationError("continuation event cap exceeds issued authority")
            if request["max_bytes"] > self.limits.continuation_bytes:
                raise ValidationError("continuation byte cap exceeds issued authority")
            by_id = {event["id"]: index for index, event in enumerate(state.events)}
            direction = request["direction"]
            direction_allowed = {
                "before": state.can_fetch_before,
                "after": state.can_fetch_after,
                "around": state.can_fetch_around_event,
            }[direction]
            if not direction_allowed:
                raise ValidationError("continuation direction is not authorized by the handle")
            cursor = request.get("cursor")
            if cursor is not None:
                if cursor not in state.cursors:
                    raise ValidationError("continuation cursor is not bound to this handle")
                cursor_direction, cursor_anchor, stored_indices = state.cursors.pop(cursor)
                if cursor_direction != direction:
                    raise ValidationError("continuation cursor direction mismatch")
                requested_anchor = request.get("anchor_event_id")
                if requested_anchor is not None and requested_anchor != cursor_anchor:
                    raise ValidationError("continuation cursor anchor mismatch")
                anchor = cursor_anchor
                candidate_indices = [
                    index
                    for index in stored_indices
                    if state.events[index]["id"] not in state.delivered_event_ids
                ]
            else:
                anchor = request.get("anchor_event_id") or state.binding["trigger_event_id"]
                if anchor not in by_id:
                    raise ValidationError("continuation anchor is outside the issued context")
                anchor_index = by_id[anchor]
                if direction == "before":
                    candidate_indices = list(range(anchor_index - 1, -1, -1))
                elif direction == "after":
                    candidate_indices = list(range(anchor_index + 1, len(state.events)))
                else:
                    candidate_indices = sorted(
                        (
                            index
                            for index in range(len(state.events))
                            if index != anchor_index
                        ),
                        key=lambda index: (abs(index - anchor_index), index),
                    )
                candidate_indices = [
                    index
                    for index in candidate_indices
                    if state.events[index]["id"] not in state.delivered_event_ids
                ]
            selected_indices: list[int] = []
            truncated_by: set[str] = set()
            for index in candidate_indices:
                if len(selected_indices) >= request["max_events"]:
                    truncated_by.add("events")
                    break
                proposed_indices = sorted([*selected_indices, index])
                proposed_events = [
                    state.events[candidate] for candidate in proposed_indices
                ]
                proposed_actors, missing = _context_actors(
                    proposed_events,
                    state.actors,
                )
                if missing:
                    raise ValidationError(
                        "continuation actor metadata is incomplete"
                    )
                if (
                    _context_byte_count(proposed_events, proposed_actors)
                    > request["max_bytes"]
                ):
                    truncated_by.add("bytes")
                    break
                selected_indices.append(index)
            exhausted = len(selected_indices) == len(candidate_indices)
            selected = [
                deepcopy(state.events[index])
                for index in sorted(selected_indices)
            ]
            state.delivered_event_ids.update(event["id"] for event in selected)
            next_cursor = None
            if not exhausted:
                next_cursor = f"cur:{secrets.token_urlsafe(24)}"
                state.cursors[next_cursor] = (
                    direction,
                    anchor,
                    tuple(candidate_indices[len(selected_indices) :]),
                )
            page_actors, missing = _context_actors(selected, state.actors)
            if missing:
                raise ValidationError("continuation actor metadata is incomplete")
            page: dict[str, Any] = {
                "request_id": request["request_id"],
                "handle_id": state.handle_id,
                "room_id": self.binding.room_id,
                "continuity_scope_id": self.binding.continuity_scope_id,
                "direction": direction,
                "anchor_event_id": anchor,
                "actors": deepcopy(page_actors),
                "events": selected,
                "coverage": {
                    "has_more_before": not exhausted if direction == "before" else None,
                    "has_more_after": not exhausted if direction == "after" else None,
                    "has_gaps": self._restart_gap,
                    "truncated_by": sorted(truncated_by),
                    "continuity": self._continuity,
                    "has_restart_gap": self._restart_gap,
                },
            }
            if next_cursor is not None:
                page["next_cursor"] = next_cursor
            return page

    def resolve_event(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            for event in self._events:
                if event["id"] == event_id:
                    return deepcopy(event)
        return None

    def retained_events(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(list(self._events)))

    def delivery_audits(self) -> tuple[DeliveryAudit, ...]:
        with self._lock:
            return tuple(self._audits)

    def mark_continuity_gap(
        self,
        *,
        delivery_id: str,
        detail: str,
    ) -> ObservationResult:
        """Persist a transport-declared gap without fabricating an event."""
        if not isinstance(delivery_id, str) or not delivery_id:
            raise ValidationError("gap delivery_id must be non-empty")
        if not isinstance(detail, str) or not detail:
            raise ValidationError("gap detail must be non-empty")
        audit = DeliveryAudit(delivery_id, "continuity-gap", detail)
        with self._lock:
            self._persist_gap_state()
            self._restart_gap = True
            self._continuity = "unknown"
            self._continuations.clear()
            self._record_audit(audit)
        return ObservationResult(audit, False)

    def restart(self) -> None:
        """Drop ephemeral continuation authority; retained facts stay context."""
        with self._lock:
            self._continuations.clear()
