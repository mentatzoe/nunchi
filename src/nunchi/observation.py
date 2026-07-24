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
    binding: dict[str, str]
    expires_at: datetime
    events: list[dict[str, Any]]
    actors: dict[str, dict[str, Any]]
    cursors: dict[str, tuple[str, int]]


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
        return {event["author_id"], *event["mentioned_actor_ids"]}
    if event["type"] == "reaction":
        return {event["author_id"]}
    result = {event["subject_actor_id"]}
    if event.get("caused_by_actor_id"):
        result.add(event["caused_by_actor_id"])
    return result


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
        self._delivery_by_event: dict[str, str] = {}
        self._audits: list[DeliveryAudit] = []
        self._continuations: dict[str, _ContinuationState] = {}
        self._restart_gap = False
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
            if self._path.exists():
                self._load()

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

    def _persist_snapshot(self) -> None:
        """Atomically retain only the configured bounded observation horizon."""
        if self._path is None:
            return
        lines: list[bytes] = []
        for event in self._events:
            referenced = _actor_refs(event)
            actors = {
                actor_id: self._actors[actor_id]
                for actor_id in referenced
                if actor_id in self._actors
            }
            if set(actors) != referenced:
                raise PersistenceError("retained observation actor metadata is incomplete")
            lines.append(
                _canonical_bytes(
                    {
                        "delivery_id": self._delivery_by_event[event["id"]],
                        "event": event,
                        "actors": actors,
                    }
                )
                + b"\n"
            )
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
        self._audits.append(audit)
        if self._audit_path is None:
            return
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
        self._delivery_by_event[event["id"]] = delivery_id
        self._events.append(deepcopy(dict(event)))
        self._actors.update(checked_actors)
        self._trim_retention()

    def _trim_retention(self) -> None:
        while len(self._events) > self.limits.retention_events:
            removed = self._events.popleft()
            self._event_ids.discard(removed["id"])
            delivery_id = self._delivery_by_event.pop(removed["id"], None)
            if delivery_id is not None:
                self._delivery_ids.discard(delivery_id)
        while self._events and len(_canonical_bytes(list(self._events))) > self.limits.retention_bytes:
            removed = self._events.popleft()
            self._event_ids.discard(removed["id"])
            delivery_id = self._delivery_by_event.pop(removed["id"], None)
            if delivery_id is not None:
                self._delivery_ids.discard(delivery_id)
        referenced = {self.binding.actor_id}
        for event in self._events:
            referenced.update(_actor_refs(event))
        self._actors = {
            actor_id: actor
            for actor_id, actor in self._actors.items()
            if actor_id in referenced
        }

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
                set(self._delivery_ids),
                set(self._event_ids),
                dict(self._delivery_by_event),
            )
            self._append_memory(delivery_id, checked, checked_actors)
            try:
                self._persist_snapshot()
            except BaseException:
                (
                    self._events,
                    self._actors,
                    self._delivery_ids,
                    self._event_ids,
                    self._delivery_by_event,
                ) = previous
                raise
            if checked.get("author_id") == self.binding.actor_id:
                outcome = "exact-self-context"
                eligible = False
                detail = "exact transport self retained as context without self wake"
            else:
                outcome = "recorded"
                eligible = True
                detail = "canonical event recorded"
            audit = DeliveryAudit(delivery_id, outcome, detail, checked["id"])
            self._record_audit(audit)
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
            if len(_canonical_bytes(ordered)) <= self.limits.snapshot_bytes:
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
            if first > 0:
                truncated.add("events")
            referenced = {self.binding.actor_id}
            for event in events:
                referenced.update(_actor_refs(event))
            actors = {
                actor_id: deepcopy(self._actors[actor_id])
                for actor_id in referenced
                if actor_id in self._actors
            }
            if referenced - set(actors):
                raise SnapshotUnavailable("retained event actor metadata is incomplete")
            coverage: dict[str, Any] = {
                "max_events": self.limits.snapshot_events,
                "max_bytes": self.limits.snapshot_bytes,
                "max_age_seconds": self.limits.snapshot_age_seconds,
                "has_more_before": first > 0,
                "has_more_after": last < len(all_events) - 1,
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
            if continuation and (coverage["has_more_before"] or coverage["has_more_after"]):
                request["continuation"] = self._issue_continuation(
                    trigger_event_id=trigger_event_id,
                    events=all_events,
                    actors=self._actors,
                )
            checked = validate_attention_request(request)
            body = {
                "schema_version": 2,
                "trigger_event_id": trigger_event_id,
                "continuity_scope_id": self.binding.continuity_scope_id,
                "event_count": len(events),
                "byte_count": len(_canonical_bytes(events)),
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
        trigger_event_id: str,
        events: list[dict[str, Any]],
        actors: Mapping[str, Any],
    ) -> dict[str, Any]:
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
            binding=binding,
            expires_at=expires_at,
            events=deepcopy(events),
            actors=deepcopy(dict(actors)),
            cursors={},
        )
        self._continuations[handle_id] = state
        return {
            "handle_id": handle_id,
            "bound_to": deepcopy(binding),
            "can_fetch_before": True,
            "can_fetch_after": True,
            "can_fetch_around_event": True,
            "max_events_per_fetch": self.limits.continuation_events,
            "max_bytes_per_fetch": self.limits.continuation_bytes,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

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
            state = self._continuations.get(request["handle_id"])
            current = now or datetime.now(timezone.utc)
            if state is None or current >= state.expires_at:
                raise ValidationError("continuation handle is unknown or expired")
            if dict(host_context) != state.binding:
                raise ValidationError("continuation host context does not match the issued binding")
            if request["max_events"] > self.limits.continuation_events:
                raise ValidationError("continuation event cap exceeds issued authority")
            if request["max_bytes"] > self.limits.continuation_bytes:
                raise ValidationError("continuation byte cap exceeds issued authority")
            anchor = request.get("anchor_event_id") or state.binding["trigger_event_id"]
            by_id = {event["id"]: index for index, event in enumerate(state.events)}
            if anchor not in by_id:
                raise ValidationError("continuation anchor is outside the issued context")
            direction = request["direction"]
            cursor = request.get("cursor")
            if cursor is not None:
                if cursor not in state.cursors:
                    raise ValidationError("continuation cursor is not bound to this handle")
                cursor_direction, offset = state.cursors.pop(cursor)
                if cursor_direction != direction:
                    raise ValidationError("continuation cursor direction mismatch")
            else:
                offset = by_id[anchor]
            if direction == "before":
                candidates = state.events[:offset]
                candidates = list(reversed(candidates))
            elif direction == "after":
                candidates = state.events[offset + 1 :]
            else:
                candidates = state.events
                offset = 0
            selected: list[dict[str, Any]] = []
            used_bytes = 2
            for event in candidates:
                event_bytes = len(_canonical_bytes(event)) + (1 if selected else 0)
                if len(selected) >= request["max_events"] or used_bytes + event_bytes > request["max_bytes"]:
                    break
                selected.append(deepcopy(event))
                used_bytes += event_bytes
            if direction == "before":
                selected.reverse()
            exhausted = len(selected) == len(candidates)
            next_cursor = None
            if not exhausted:
                next_cursor = f"cur:{secrets.token_urlsafe(24)}"
                advance = len(selected)
                if direction == "before":
                    next_offset = max(0, offset - advance)
                else:
                    next_offset = offset + advance
                state.cursors[next_cursor] = (direction, next_offset)
            referenced = set()
            for event in selected:
                referenced.update(_actor_refs(event))
            page: dict[str, Any] = {
                "request_id": request["request_id"],
                "handle_id": state.handle_id,
                "room_id": self.binding.room_id,
                "continuity_scope_id": self.binding.continuity_scope_id,
                "direction": direction,
                "anchor_event_id": anchor,
                "actors": {
                    actor_id: deepcopy(state.actors[actor_id])
                    for actor_id in referenced
                    if actor_id in state.actors
                },
                "events": selected,
                "coverage": {
                    "has_more_before": not exhausted if direction == "before" else None,
                    "has_more_after": not exhausted if direction == "after" else None,
                    "has_gaps": self._restart_gap,
                    "truncated_by": [] if exhausted else ["events"],
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
