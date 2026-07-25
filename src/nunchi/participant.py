"""Conversation-opportunity scheduling and the participant act-or-silence host."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextvars import copy_context
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import queue
import threading
import time
from typing import Any, Literal, Protocol

from .errors import NunchiError, ValidationError
from .observation import ObservationProvider
from .receipts import ReceiptJournal
from .v2_contracts import (
    validate_attention_decision,
    validate_attention_request,
    validate_participant_wake,
)

_MAX_CONTEXT_EXPANSIONS = 3


class ParticipantError(NunchiError):
    """An operational participant-host failure."""

    label = "participant error"


@dataclass(frozen=True)
class OpportunityToken:
    room_key: str
    generation: int
    anchor_event_id: str
    cancel_event: threading.Event = field(compare=False, repr=False)


class ConversationOpportunityScheduler:
    """At most one active opportunity and one replaceable newest anchor."""

    def __init__(self, room_key: str) -> None:
        if not isinstance(room_key, str) or not room_key:
            raise ValueError("room_key must be non-empty")
        self.room_key = room_key
        self._active = False
        self._pending_anchor: str | None = None
        self._generation = 0
        self._cancel_event: threading.Event | None = None
        self._dispatch_committed = False
        self._lock = threading.RLock()

    def offer(self, anchor_event_id: str) -> OpportunityToken | None:
        """Return work only for an idle scheduler; otherwise replace pending."""
        if not isinstance(anchor_event_id, str) or not anchor_event_id:
            raise ValidationError("opportunity anchor must be non-empty")
        with self._lock:
            if self._active:
                self._pending_anchor = anchor_event_id
                return None
            self._active = True
            self._generation += 1
            self._cancel_event = threading.Event()
            self._dispatch_committed = False
            return OpportunityToken(
                self.room_key,
                self._generation,
                anchor_event_id,
                self._cancel_event,
            )

    def complete(self, token: OpportunityToken) -> OpportunityToken | None:
        """Finish exact current work and return one fresh pending opportunity."""
        with self._lock:
            if not self._matches(token):
                return None
            pending = self._pending_anchor
            self._pending_anchor = None
            if pending is None:
                self._active = False
                self._cancel_event = None
                self._dispatch_committed = False
                return None
            self._generation += 1
            self._cancel_event = threading.Event()
            self._dispatch_committed = False
            return OpportunityToken(
                self.room_key,
                self._generation,
                pending,
                self._cancel_event,
            )

    def cancel(self) -> None:
        """Invalidate active and pending work without promoting retained events."""
        with self._lock:
            if self._cancel_event is not None:
                self._cancel_event.set()
            self._pending_anchor = None
            self._active = False
            self._dispatch_committed = False
            self._generation += 1

    restart = cancel

    def _matches(self, token: OpportunityToken) -> bool:
        return (
            self._active
            and token.room_key == self.room_key
            and token.generation == self._generation
            and token.cancel_event is self._cancel_event
            and not token.cancel_event.is_set()
        )

    def is_current(self, token: OpportunityToken) -> bool:
        with self._lock:
            return self._matches(token)

    def commit_dispatch(
        self,
        token: OpportunityToken,
        dispatcher: Callable[[], Any],
    ) -> tuple[bool, Any | None]:
        """Order cancellation against the single output/effect commit point.

        The lock covers the current-token check and native dispatch call.
        Cancellation ordered first prevents the call.  Cancellation ordered
        after cannot relabel a dispatch that already reached the transport.
        """
        with self._lock:
            if not self._matches(token) or self._dispatch_committed:
                return False, None
            self._dispatch_committed = True
            return True, dispatcher()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def pending_anchor(self) -> str | None:
        with self._lock:
            return self._pending_anchor


@dataclass(frozen=True)
class TransportResult:
    delivery: Literal["sent", "failed", "unknown", "unavailable"]
    detail: str = ""

    def __post_init__(self) -> None:
        if self.delivery not in ("sent", "failed", "unknown", "unavailable"):
            raise ValueError("unsupported transport result")
        if not isinstance(self.detail, str):
            raise ValueError("transport detail must be a string")


class Participant(Protocol):
    def __call__(
        self,
        *,
        wake: Mapping[str, Any],
        expand: Callable[..., Mapping[str, Any]],
        cancel: threading.Event,
    ) -> Mapping[str, Any] | None:
        """Return one direct room action, privileged proposal, or silence."""


class Transport(Protocol):
    def dispatch(
        self,
        *,
        action: Mapping[str, Any],
        wake: Mapping[str, Any],
    ) -> TransportResult:
        """Dispatch one ordinary participant action without social judgment."""


class PrivilegedCoordinator(Protocol):
    def execute_proposal(
        self,
        *,
        proposal: Mapping[str, Any],
        wake: Mapping[str, Any],
        cancel: threading.Event,
    ) -> TransportResult:
        """Authorize and optionally dispatch one exact privileged proposal."""


def _packet_bytes(
    events: list[Mapping[str, Any]],
    actors: Mapping[str, Any],
) -> int:
    return len(
        json.dumps(
            {"actors": actors, "events": events},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def _validate_action(action: Any) -> dict[str, Any]:
    if not isinstance(action, Mapping):
        raise ParticipantError("participant action must be an object or silence")
    kind = action.get("kind")
    common = {"kind", "origin_event_id"}
    if kind == "message":
        allowed = common | {"text"}
        required = allowed
        if set(action) != required or not isinstance(action.get("text"), str):
            raise ParticipantError("message action must contain kind, origin_event_id, and text")
    elif kind == "reply":
        allowed = common | {"target_event_id", "text"}
        required = allowed
        if set(action) != required or not isinstance(action.get("text"), str):
            raise ParticipantError("reply action has an invalid closed shape")
        if not isinstance(action.get("target_event_id"), str) or not action["target_event_id"]:
            raise ParticipantError("reply target_event_id must be non-empty")
    elif kind == "reaction":
        allowed = common | {"target_event_id", "reaction", "operation"}
        required = allowed
        if set(action) != required:
            raise ParticipantError("reaction action has an invalid closed shape")
        for name in ("target_event_id", "reaction"):
            if not isinstance(action.get(name), str) or not action[name]:
                raise ParticipantError(f"reaction {name} must be non-empty")
        if action["operation"] not in ("add", "remove"):
            raise ParticipantError("reaction operation must be add or remove")
    elif kind == "privileged":
        allowed = common | {"capability", "resource", "operation"}
        required = allowed
        if set(action) != required:
            raise ParticipantError("privileged proposal has an invalid closed shape")
        if not isinstance(action.get("capability"), str) or not action["capability"]:
            raise ParticipantError("privileged proposal capability must be non-empty")
        if not isinstance(action.get("resource"), Mapping):
            raise ParticipantError("privileged proposal resource must be an object")
        if not isinstance(action.get("operation"), Mapping):
            raise ParticipantError("privileged proposal operation must be an object")
    else:
        raise ParticipantError("participant action kind is unsupported")
    if not isinstance(action.get("origin_event_id"), str) or not action["origin_event_id"]:
        raise ParticipantError("participant action origin_event_id must be non-empty")
    return deepcopy(dict(action))


class ParticipantTurnHost:
    """Materialize one current wake and invoke the participant once."""

    def __init__(
        self,
        *,
        observation: ObservationProvider,
        participant: Participant,
        transport: Transport,
        scheduler: ConversationOpportunityScheduler,
        receipts: ReceiptJournal | None = None,
        privileged: PrivilegedCoordinator | None = None,
        participant_timeout_seconds: float = 300.0,
    ) -> None:
        if (
            isinstance(participant_timeout_seconds, bool)
            or not isinstance(participant_timeout_seconds, (int, float))
            or not math.isfinite(float(participant_timeout_seconds))
            or participant_timeout_seconds <= 0
        ):
            raise ValueError("host timeout must be positive and finite")
        self.observation = observation
        self.participant = participant
        self.transport = transport
        self.scheduler = scheduler
        self.receipts = receipts or observation.receipts
        self.privileged = privileged
        self.participant_timeout_seconds = float(participant_timeout_seconds)
        self.host_timeout_seconds = self.participant_timeout_seconds
        self.invocation_count = 0

    def _make_wake(
        self,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        checked_request = validate_attention_request(request)
        checked_decision = validate_attention_decision(decision, request=checked_request)
        if checked_decision["status"] == "ok":
            effective = checked_decision["effective_disposition"]
            if effective == "SUPPRESS":
                return None
            source = "WAKE" if effective == "WAKE" else "DEFER"
        elif checked_decision["status"] == "bypass":
            source = "PREATTENTION_BYPASS"
        else:
            source = "ERROR_FALLBACK"

        fresh = self.observation.build_snapshot(
            checked_request["trigger_event_id"],
            request_id=checked_request["request_id"],
            continuation=False,
            record_receipt=False,
        )
        # Continuation capability is retained only by this host.  The
        # participant receives a mediated expand callback, never opaque
        # handles, cursors, bindings, or expiry values.
        fresh.pop("continuation", None)
        wake: dict[str, Any] = {
            key: deepcopy(fresh[key])
            for key in (
                "request_id",
                "self",
                "room",
                "actors",
                "events",
                "trigger_event_id",
                "coverage",
            )
        }
        attention: dict[str, Any] = {"source": source}
        if source == "WAKE":
            event_ids = {event["id"] for event in wake["events"]}
            raw_advice = checked_decision.get("attention_advice")
            if raw_advice and all(
                set(item["evidence_event_ids"]).issubset(event_ids)
                for item in raw_advice
            ):
                attention["advice"] = deepcopy(raw_advice)
                attention["evidence_event_ids"] = sorted(
                    {
                        event_id
                        for item in raw_advice
                        for event_id in item["evidence_event_ids"]
                    }
                )
        wake["attention"] = attention
        return validate_participant_wake(wake)

    def run(
        self,
        *,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
        token: OpportunityToken,
        error_wake: bool = True,
        deadline: float | None = None,
    ) -> TransportResult | None:
        effective_deadline = (
            time.monotonic() + self.host_timeout_seconds
            if deadline is None
            else deadline
        )
        checked_decision = validate_attention_decision(decision, request=request)
        if (
            checked_decision["status"] == "error"
            and (not error_wake or checked_decision["error"]["code"] == "cancelled")
        ):
            return None
        if not self.scheduler.is_current(token):
            return None
        if time.monotonic() >= effective_deadline:
            self.scheduler.cancel()
            return TransportResult("failed", "host total deadline exceeded")
        wake = self._make_wake(request, checked_decision)
        if wake is None:
            return None
        if time.monotonic() >= effective_deadline:
            self.scheduler.cancel()
            return TransportResult("failed", "host total deadline exceeded")
        host_continuation = request.get("continuation")
        expansion_calls = 0
        expansion_cursors: dict[tuple[str, str], str] = {}
        expanded_event_ids: set[str] = set()

        def expand(
            *,
            direction: str,
            anchor_event_id: str | None = None,
            max_events: int = 12,
            max_bytes: int = 16_384,
        ) -> Mapping[str, Any]:
            nonlocal expansion_calls
            if token.cancel_event.is_set() or not self.scheduler.is_current(token):
                raise ParticipantError("context expansion cancelled")
            if time.monotonic() >= effective_deadline:
                self.scheduler.cancel()
                raise ParticipantError("context expansion deadline exceeded")
            if not host_continuation:
                raise ParticipantError("context expansion is unavailable")
            if expansion_calls >= _MAX_CONTEXT_EXPANSIONS:
                raise ParticipantError("context expansion call cap exceeded")
            fetch: dict[str, Any] = {
                "request_id": wake["request_id"],
                "handle_id": host_continuation["handle_id"],
                "direction": direction,
                "max_events": max_events,
                "max_bytes": max_bytes,
            }
            if anchor_event_id is not None:
                fetch["anchor_event_id"] = anchor_event_id
            anchor = anchor_event_id or wake["trigger_event_id"]
            cursor_key = (direction, anchor)
            cursor = expansion_cursors.pop(cursor_key, None)
            if cursor is not None:
                fetch["cursor"] = cursor
            expansion_calls += 1
            page = dict(
                self.observation.fetch_context(
                    fetch,
                    host_context=host_continuation["bound_to"],
                )
            )
            expanded_event_ids.update(
                event["id"]
                for event in page.get("events", ())
                if isinstance(event, Mapping)
                and isinstance(event.get("id"), str)
            )
            next_cursor = page.pop("next_cursor", None)
            if next_cursor is not None:
                expansion_cursors[cursor_key] = next_cursor
            # Capability material never crosses the host/participant boundary.
            page.pop("handle_id", None)
            page.pop("continuity_scope_id", None)
            page["has_next_page"] = next_cursor is not None
            return page

        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def invoke() -> None:
            try:
                result_queue.put_nowait(
                    (
                        "ok",
                        self.participant(
                            wake=deepcopy(wake),
                            expand=expand,
                            cancel=token.cancel_event,
                        ),
                    )
                )
            except BaseException:
                result_queue.put_nowait(("error", None))

        self.invocation_count += 1
        worker = threading.Thread(
            target=copy_context().run,
            args=(invoke,),
            name=f"nunchi-participant-{token.generation}",
            daemon=True,
        )
        worker.start()
        invocation_result: tuple[str, Any] | None = None
        while invocation_result is None:
            if token.cancel_event.is_set() or not self.scheduler.is_current(token):
                return None
            remaining = effective_deadline - time.monotonic()
            if remaining <= 0:
                if self.scheduler.is_current(token):
                    self._append_host_receipt(
                        wake,
                        expansion_calls=expansion_calls,
                        outcome="unknown",
                    )
                    self.scheduler.cancel()
                else:
                    token.cancel_event.set()
                return TransportResult("failed", "host total deadline exceeded")
            try:
                invocation_result = result_queue.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
        status, raw_action = invocation_result
        if time.monotonic() >= effective_deadline:
            if self.scheduler.is_current(token):
                self._append_host_receipt(
                    wake,
                    expansion_calls=expansion_calls,
                    outcome="unknown",
                )
                self.scheduler.cancel()
            return TransportResult("failed", "host total deadline exceeded")
        if status == "error":
            if self.scheduler.is_current(token):
                self._append_host_receipt(
                    wake,
                    expansion_calls=expansion_calls,
                    outcome="unknown",
                )
            return TransportResult("failed", "participant invocation failed")
        if not self.scheduler.is_current(token):
            return None
        if raw_action is None:
            self._append_host_receipt(
                wake,
                expansion_calls=expansion_calls,
                outcome="silent",
            )
            return None
        try:
            action = _validate_action(raw_action)
        except ParticipantError:
            self._append_host_receipt(
                wake,
                expansion_calls=expansion_calls,
                outcome="unknown",
            )
            return TransportResult("failed", "participant returned an invalid action")

        visible_event_ids = {event["id"] for event in wake["events"]}
        visible_event_ids.update(expanded_event_ids)
        if action["origin_event_id"] not in visible_event_ids:
            self._append_host_receipt(
                wake,
                expansion_calls=expansion_calls,
                outcome="unknown",
            )
            return TransportResult("failed", "action origin is absent from participant facts")
        if (
            action["kind"] in ("reply", "reaction")
            and action["target_event_id"] not in visible_event_ids
        ):
            self._append_host_receipt(
                wake,
                expansion_calls=expansion_calls,
                outcome="unknown",
            )
            return TransportResult("failed", "action target is absent from participant facts")

        def dispatch() -> TransportResult:
            # This append and the native call share the scheduler's commit
            # lock.  Cancellation ordered first yields neither a host stage nor
            # an outbound call; persistence failure also prevents dispatch.
            # The host cannot truthfully claim ``sent`` before the separately
            # owned transport stage has observed the native result.  Persist
            # ``unknown`` as the action handoff state, then let transport alone
            # attest sent/failed/unknown/unavailable.
            if time.monotonic() >= effective_deadline:
                self._append_host_receipt(
                    wake,
                    expansion_calls=expansion_calls,
                    outcome="unknown",
                )
                self.scheduler.cancel()
                return TransportResult(
                    "failed",
                    "host total deadline exceeded before dispatch",
                )
            self._append_host_receipt(
                wake,
                expansion_calls=expansion_calls,
                outcome="unknown",
            )
            if (
                token.cancel_event.is_set()
                or time.monotonic() >= effective_deadline
            ):
                self.scheduler.cancel()
                return TransportResult(
                    "failed",
                    "host total deadline exceeded before native dispatch",
                )
            dispatch_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

            def invoke_dispatch() -> None:
                try:
                    if (
                        token.cancel_event.is_set()
                        or time.monotonic() >= effective_deadline
                    ):
                        dispatch_queue.put_nowait(
                            (
                                "deadline",
                                TransportResult(
                                    "failed",
                                    "host total deadline exceeded before native dispatch",
                                ),
                            )
                        )
                        return
                    if action["kind"] == "privileged":
                        if self.privileged is None:
                            result = TransportResult(
                                "unavailable",
                                "privileged actions are disabled",
                            )
                        else:
                            result = self.privileged.execute_proposal(
                                proposal=action,
                                wake=wake,
                                cancel=token.cancel_event,
                            )
                    else:
                        result = self.transport.dispatch(action=action, wake=wake)
                except BaseException as exc:
                    dispatch_queue.put_nowait(("error", exc))
                else:
                    dispatch_queue.put_nowait(("ok", result))

            threading.Thread(
                target=copy_context().run,
                args=(invoke_dispatch,),
                name=f"nunchi-transport-{token.generation}",
                daemon=True,
            ).start()
            while True:
                remaining = effective_deadline - time.monotonic()
                if remaining <= 0:
                    self.scheduler.cancel()
                    return TransportResult(
                        "unknown",
                        "host total deadline exceeded during dispatch",
                    )
                try:
                    status, value = dispatch_queue.get(
                        timeout=min(0.05, remaining)
                    )
                except queue.Empty:
                    continue
                if status == "deadline":
                    self.scheduler.cancel()
                    return value
                if status == "error":
                    raise value
                return value

        try:
            committed, result = self.scheduler.commit_dispatch(token, dispatch)
        except BaseException:
            committed = True
            result = TransportResult("unknown", "dispatch acknowledgement was lost")
        if not committed:
            return None
        if not isinstance(result, TransportResult):
            result = TransportResult("unknown", "transport returned no attested result")
        self.receipts.append(
            {
                "request_id": wake["request_id"],
                "stage": "transport",
                "writer": "transport",
                "body": {
                    "delivery": result.delivery,
                    **({"detail": result.detail} if result.detail else {}),
                },
            },
            writer="transport",
        )
        return result

    def _append_host_receipt(
        self,
        wake: Mapping[str, Any],
        *,
        expansion_calls: int,
        outcome: str,
    ) -> None:
        events = list(wake["events"])
        self.receipts.append(
            {
                "request_id": wake["request_id"],
                "stage": "participant-host",
                "writer": "participant-host",
                "body": {
                    "wake_source": wake["attention"]["source"],
                    "packet_event_count": len(events),
                    "packet_byte_count": _packet_bytes(events, wake["actors"]),
                    "delivered_event_ids": [event["id"] for event in events],
                    "expansion_calls": expansion_calls,
                    "invoked": True,
                    "outcome": outcome,
                },
            },
            writer="participant-host",
        )
