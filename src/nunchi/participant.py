"""Conversation-opportunity scheduling and the participant act-or-silence host."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import math
import queue
import threading
import time
from typing import Any, Literal, Protocol
from uuid import uuid4

from .errors import NunchiError, ValidationError
from .reactions import (
    ReactionCapability,
    UNAVAILABLE_REACTION_CAPABILITY,
    reaction_capability,
)
from .memory import ConversationMemory
from .observation import ObservationProvider
from .receipts import ReceiptJournal
from .v2_contracts import (
    shown_event_ids,
    validate_attention_decision,
    validate_attention_request,
    validate_participant_wake,
)

_MAX_CONTEXT_EXPANSIONS = 3
# How often a turn may ask what others posted since it last looked: the
# shared protocol asks once before the first post, and the participant may ask.
_MAX_NEW_CHECKS = 8


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
        self._lifecycle_id = str(uuid4())
        self._cancel_event: threading.Event | None = None
        self._dispatch_committed = False
        self._expired_generation: int | None = None
        self._lock = threading.RLock()

    def offer(self, anchor_event_id: str, *, only_if_idle: bool = False) -> OpportunityToken | None:
        """Return work only for an idle scheduler; otherwise replace pending.

        ``only_if_idle`` leaves pending work alone when busy: a look again
        never displaces a newer message (#94 step 6).
        """
        if not isinstance(anchor_event_id, str) or not anchor_event_id:
            raise ValidationError("opportunity anchor must be non-empty")
        with self._lock:
            if self._active:
                if not only_if_idle:
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
        """Finish exact current work and return one fresh pending opportunity.

        A token stopped through ``expire()`` still completes: expiry ends that
        work, but the newest pending event must still get its own attention.
        A token whose event was set any other way keeps the previous meaning
        and does not complete. Cancellation bumps the generation, so a
        cancelled token can never complete.
        """
        with self._lock:
            expired = (
                self._active
                and token.room_key == self.room_key
                and token.generation == self._generation
                and token.cancel_event is self._cancel_event
                and self._expired_generation == token.generation
            )
            if not (expired or self._matches(token)):
                return None
            self._expired_generation = None
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
            self._lifecycle_id = str(uuid4())

    restart = cancel

    def expire(self, token: OpportunityToken) -> None:
        """Stop this token's work at its deadline without dropping pending work."""
        with self._lock:
            if (
                self._active
                and token.generation == self._generation
                and token.cancel_event is self._cancel_event
            ):
                self._expired_generation = token.generation
                token.cancel_event.set()

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

    def authorize_effect_commit(
        self,
        token: OpportunityToken,
        *,
        deadline: float,
    ) -> bool:
        """Accept one effect only while this token is still current.

        The lock covers the current-token check and the one-shot commit mark.
        It must not be held across a network await. Cancellation that acquires
        the lock first prevents the commit. A commit that acquires it first
        cannot be relabelled by a later cancellation.
        """

        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
        ):
            return False
        with self._lock:
            if (
                not self._matches(token)
                or self._dispatch_committed
                or time.monotonic() >= deadline
            ):
                return False
            self._dispatch_committed = True
            return True

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def pending_anchor(self) -> str | None:
        with self._lock:
            return self._pending_anchor

    @property
    def lifecycle_id(self) -> str:
        with self._lock:
            return self._lifecycle_id


# What a message's commit says when the harness, not Nunchi, posts it
# (`nunchi.turn.HarnessDelivery`).
HARNESS_DELIVERS = "the harness delivers it"


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
        deadline: float | None = None,
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


def participant_host_receipt_body(
    wake: Mapping[str, Any],
    *,
    expansion_calls: int,
    invoked: bool,
    outcome: str,
) -> dict[str, Any]:
    """Build the one shared participant-host receipt body."""

    events = list(wake["events"])
    return {
        "wake_source": wake["attention"]["source"],
        "packet_event_count": len(events),
        "packet_byte_count": _packet_bytes(events, wake["actors"]),
        "delivered_event_ids": [event["id"] for event in events],
        "expansion_calls": expansion_calls,
        "invoked": invoked,
        "outcome": outcome,
    }


def _is_silence(action: Any) -> bool:
    """A participant stays silent by returning nothing, or a silence with its reason."""

    return action is None or (isinstance(action, Mapping) and action.get("kind") == "silence")


def _validate_action(action: Any) -> dict[str, Any]:
    """Check one participant action and return it with its reason apart.

    Any action may carry ``why``, the participant's own reason, for its
    memory only: it is returned under ``why`` and never reaches the room.
    """

    if not isinstance(action, Mapping):
        raise ParticipantError("participant action must be an object or silence")
    why = action.get("why")
    action = {key: action[key] for key in action if key != "why"}
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
    elif kind == "withdraw":
        if set(action) != common | {"proposal_id"}:
            raise ParticipantError("withdrawal has an invalid closed shape")
        if not isinstance(action.get("proposal_id"), str) or not action["proposal_id"]:
            raise ParticipantError("withdrawal proposal_id must be non-empty")
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
    checked = deepcopy(dict(action))
    if why is not None:
        checked["why"] = why
    return checked


def build_participant_wake(
    observation: ObservationProvider,
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    memory: ConversationMemory | None = None,
    proposals: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any] | None:
    """Build the fresh bounded facts delivered to any admitted participant.

    With ``memory``, the wake also carries the participant's memory of the
    room (#94 step 5): its own recent moves, and the threads before the
    message this turn is about. ``proposals`` are its privileged proposals
    and what became of them (#90), shown among its own moves.
    """

    checked_request = validate_attention_request(request)
    checked_decision = validate_attention_decision(
        decision,
        request=checked_request,
    )
    if checked_decision["status"] == "ok":
        effective = checked_decision["effective_disposition"]
        if effective == "SUPPRESS":
            return None
        source = "WAKE" if effective == "WAKE" else "DEFER"
    elif checked_decision["status"] == "bypass":
        source = "PREATTENTION_BYPASS"
    else:
        source = "ERROR_FALLBACK"

    fresh = observation.build_snapshot(
        checked_request["trigger_event_id"],
        request_id=checked_request["request_id"],
        continuation=False,
        record_receipt=False,
    )
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
            "pace",
        )
        if key in fresh
    }
    if "occasion" in checked_request:
        # The turn knows it comes from a look again, not a new message.
        wake["occasion"] = checked_request["occasion"]
    shown = {event["id"] for event in wake["events"]}
    waiting = [event_id for event_id in checked_request.get("unattended_event_ids", ()) if event_id in shown]
    if waiting:
        # The turn reads what arrived while the participant was busy with the
        # newest message, as one moment (#94 step 6).
        wake["unattended_event_ids"] = waiting
    attention: dict[str, Any] = {"source": source}
    if source in ("WAKE", "DEFER") and checked_decision["status"] == "ok":
        # The turn carries the model's reading of the room. The wake is built
        # fresh, so an item whose messages have left the window is dropped on
        # its own; the reading never stops the turn.
        event_ids = {event["id"] for event in wake["events"]}
        reading = [
            deepcopy(item)
            for item in checked_decision.get("attention_advice", ())
            if set(item["evidence_event_ids"]).issubset(event_ids)
        ]
        if reading:
            attention["advice"] = reading
            attention["evidence_event_ids"] = sorted(
                {event_id for item in reading for event_id in item["evidence_event_ids"]}
            )
            # The newest message attention saw, so the participant can tell
            # which messages arrived after the reading was written.
            judged_through = checked_request["events"][-1]["id"]
            if judged_through in event_ids:
                attention["judged_through_event_id"] = judged_through
    wake["attention"] = attention
    if memory is not None:
        facts = memory.facts(
            observation,
            current_event_id=wake["trigger_event_id"],
            proposals=proposals,
        )
        if facts:
            wake["memory"] = facts
    return validate_participant_wake(wake)


class RoomView:
    """The participant's own view of the room for one turn.

    It reads the live log, so it shows messages that arrived after the turn
    began, and it never fails the turn: nothing more, an evicted anchor or the
    per-turn limit come back as a page with a note. It never repeats an event
    it has shown, and every event it has shown may be an action's origin or
    target. ``guard`` raises when the turn is cancelled or out of time.

    ``news`` is the host's own direction, for steering (#94 step 6; Zoe,
    2026-10-06): what others posted since the participant last looked, like
    ``new``, but it never counts against the participant's checks. A host
    that can reach a running turn delivers it there; models cannot ask for
    it, since every action schema names only the four model directions.
    """

    def __init__(
        self,
        observation: ObservationProvider,
        wake: Mapping[str, Any],
        *,
        turn_began: int,
        guard: Callable[[], None],
    ) -> None:
        self._observation = observation
        self._wake = wake
        self._turn_began = turn_began
        self._guard = guard
        self.expansion_calls = 0
        self.new_checks = 0
        self._limit_noted = False
        self.seen_event_ids: set[str] = shown_event_ids(wake)

    def fork(self) -> "RoomView":
        """A fresh view of the same turn, as if nothing had been read yet.

        For replaying a turn, as the behavior suite does to play it again
        without the reading. Its actions are never dispatched.
        """

        return RoomView(
            self._observation,
            self._wake,
            turn_began=self._turn_began,
            guard=self._guard,
        )

    def expand(
        self,
        *,
        direction: str,
        anchor_event_id: str | None = None,
        max_events: int = 12,
        max_bytes: int = 16_384,
    ) -> Mapping[str, Any]:
        self._guard()
        if direction == "news":
            direction = "new"
        elif direction == "new":
            if self.new_checks >= _MAX_NEW_CHECKS:
                raise ParticipantError("look-again call cap exceeded")
            self.new_checks += 1
        else:
            if self.expansion_calls >= _MAX_CONTEXT_EXPANSIONS:
                if self._limit_noted:
                    raise ParticipantError("context expansion call cap exceeded")
                self._limit_noted = True
                return {
                    "request_id": self._wake["request_id"],
                    "room_id": self._observation.binding.room_id,
                    "direction": direction,
                    "actors": {},
                    "events": [],
                    "has_next_page": False,
                    "note": (
                        "You have looked at the room's history "
                        f"{_MAX_CONTEXT_EXPANSIONS} times this turn, the limit. "
                        "Act on what you have seen."
                    ),
                }
            self.expansion_calls += 1
        if isinstance(max_events, bool) or not isinstance(max_events, int):
            max_events = 12
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            max_bytes = 16_384
        page = dict(
            self._observation.read_room(
                direction=direction,
                anchor_event_id=(
                    None
                    if direction == "new"
                    else anchor_event_id or self._wake["trigger_event_id"]
                ),
                seen_event_ids=frozenset(self.seen_event_ids),
                since_arrival=self._turn_began,
                max_events=max_events,
                max_bytes=max_bytes,
            )
        )
        self.seen_event_ids.update(
            event["id"]
            for event in page.get("events", ())
            if isinstance(event, Mapping) and isinstance(event.get("id"), str)
        )
        page["request_id"] = self._wake["request_id"]
        return page


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
        memory: ConversationMemory | None = None,
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
        # The participant's own moves in this room; every turn carries them.
        self.memory = memory if memory is not None else ConversationMemory()
        self.participant_timeout_seconds = float(participant_timeout_seconds)
        self.host_timeout_seconds = self.participant_timeout_seconds
        self.invocation_count = 0

    def reaction_capability(self) -> ReactionCapability:
        provider = getattr(self.transport, "reaction_capability", None)
        try:
            return reaction_capability(
                provider() if callable(provider) else UNAVAILABLE_REACTION_CAPABILITY
            )
        except Exception:
            return UNAVAILABLE_REACTION_CAPABILITY

    def _protocol_opportunity(
        self,
        token: OpportunityToken,
        *,
        deadline: float,
    ) -> dict[str, Any]:
        """Bind an owned participant action to current host authority."""

        capabilities = getattr(self.transport, "ordinary_action_capabilities", None)
        ordinary = (
            list(capabilities())
            if callable(capabilities)
            else ["message", "reply", "reaction"]
        )
        ordinary = [
            item
            for item in ("message", "reply", "reaction")
            if item in set(ordinary)
        ]
        current_reaction = self.reaction_capability()
        if "reaction" in ordinary and not (
            current_reaction.permits("add") or current_reaction.permits("remove")
        ):
            ordinary.remove("reaction")
        permission_document = {
            "participant_id": self.observation.binding.participant_id,
            "actor_id": self.observation.binding.actor_id,
            "room_id": self.observation.binding.room_id,
            "continuity_scope_id": self.observation.binding.continuity_scope_id,
            "ordinary_actions": ordinary,
            "privileged_proposals": self.privileged is not None,
            "reaction_capability": current_reaction.document(),
        }
        revision = hashlib.sha256(
            json.dumps(
                permission_document,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        deadline_id = hashlib.sha256(
            (
                f"{self.scheduler.lifecycle_id}\0{token.generation}\0"
                f"{deadline:.9f}\0{revision}"
            ).encode("utf-8")
        ).hexdigest()
        return {
            "generation": token.generation,
            "lifecycle_id": self.scheduler.lifecycle_id,
            "deadline_id": deadline_id,
            "permissions": {
                "revision": revision,
                "ordinary_actions": ordinary,
                "privileged_proposals": self.privileged is not None,
            },
        }

    def _make_wake(
        self,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        return build_participant_wake(
            self.observation,
            request,
            decision,
            memory=self.memory,
            proposals=self._proposals(),
        )

    def memory_facts(self, trigger_event_id: str) -> dict[str, Any] | None:
        """The participant's memory as its turn about ``trigger_event_id`` sees it."""

        return self.memory.facts(
            self.observation,
            current_event_id=trigger_event_id,
            proposals=self._proposals(),
        )

    def _proposals(self) -> tuple[Mapping[str, Any], ...]:
        """The participant's proposals and their status, when the host keeps them."""

        source = getattr(self.privileged, "proposals", None)
        return tuple(source()) if callable(source) else ()

    def run(
        self,
        *,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
        token: OpportunityToken,
        error_wake: bool = True,
        deadline: float | None = None,
    ) -> TransportResult | None:
        """Run one turn, and tell a participant that waits on it what became of its action.

        A participant whose agent keeps working after its room action (a tool
        call that waits for the room's answer) has a ``settle`` method.
        """

        settle = getattr(self.participant, "settle", None)
        request_id = request.get("request_id") if isinstance(request, Mapping) else None
        if not isinstance(request_id, str):
            settle = None
        try:
            result = self._run(
                request=request,
                decision=decision,
                token=token,
                error_wake=error_wake,
                deadline=deadline,
            )
        except BaseException:
            # The host may fail after the native call (a receipt write, say),
            # so the participant must not be told that nothing was posted.
            if callable(settle):
                settle(
                    request_id,
                    TransportResult("unknown", "the host failed while handling it"),
                )
            raise
        if callable(settle):
            settle(request_id, result)
        return result

    def _run(
        self,
        *,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
        token: OpportunityToken,
        error_wake: bool,
        deadline: float | None,
    ) -> TransportResult | None:
        effective_deadline = (
            time.monotonic() + self.host_timeout_seconds
            if deadline is None
            else deadline
        )
        if (
            isinstance(effective_deadline, bool)
            or not isinstance(effective_deadline, (int, float))
            or not math.isfinite(effective_deadline)
        ):
            raise ParticipantError("host deadline must be a finite monotonic time")
        checked_request = validate_attention_request(request)
        checked_decision = validate_attention_decision(
            decision,
            request=checked_request,
        )
        if token.anchor_event_id != checked_request["trigger_event_id"]:
            raise ParticipantError(
                "opportunity token does not match the participant request trigger"
            )
        if (
            checked_decision["status"] == "error"
            and (not error_wake or checked_decision["error"]["code"] == "cancelled")
        ):
            return None
        if (
            checked_decision["status"] == "ok"
            and checked_decision["effective_disposition"] == "SUPPRESS"
        ):
            return None
        if not self.scheduler.is_current(token):
            return None
        if time.monotonic() >= effective_deadline:
            self.scheduler.expire(token)
            return TransportResult("failed", "host total deadline exceeded")
        # Taken before the wake is built: anything that arrives after this and
        # is not in the wake is new to the participant.
        turn_began = self.observation.arrival_mark()
        wake = self._make_wake(checked_request, checked_decision)
        if wake is None:
            return None
        if time.monotonic() >= effective_deadline:
            self.scheduler.expire(token)
            return TransportResult("failed", "host total deadline exceeded")
        def guard() -> None:
            if token.cancel_event.is_set() or not self.scheduler.is_current(token):
                raise ParticipantError("context expansion cancelled")
            if time.monotonic() >= effective_deadline:
                self.scheduler.expire(token)
                raise ParticipantError("context expansion deadline exceeded")

        view = RoomView(self.observation, wake, turn_began=turn_began, guard=guard)
        expand = view.expand

        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def invoke() -> None:
            try:
                core_run = getattr(self.participant, "run_protocol", None)
                if callable(core_run):
                    action = core_run(
                        wake=deepcopy(wake),
                        opportunity=self._protocol_opportunity(
                            token,
                            deadline=effective_deadline,
                        ),
                        expand=expand,
                        cancel=token.cancel_event,
                    )
                else:
                    action = self.participant(
                        wake=deepcopy(wake),
                        expand=expand,
                        cancel=token.cancel_event,
                    )
                result_queue.put_nowait(
                    (
                        "ok",
                        action,
                    )
                )
            except BaseException:
                result_queue.put_nowait(("error", None))

        self.invocation_count += 1
        worker = threading.Thread(
            target=invoke,
            name=f"nunchi-participant-{token.generation}",
            daemon=True,
        )
        worker.start()
        host_receipt_persisted = False

        def settle_host(outcome: str) -> None:
            nonlocal host_receipt_persisted
            if host_receipt_persisted:
                return
            self._append_host_receipt(
                wake,
                expansion_calls=view.expansion_calls + view.new_checks,
                outcome=outcome,
            )
            host_receipt_persisted = True

        invocation_result: tuple[str, Any] | None = None
        while invocation_result is None:
            if token.cancel_event.is_set() or not self.scheduler.is_current(token):
                settle_host("unknown")
                return None
            remaining = effective_deadline - time.monotonic()
            if remaining <= 0:
                if self.scheduler.is_current(token):
                    settle_host("unknown")
                    self.scheduler.expire(token)
                else:
                    token.cancel_event.set()
                    settle_host("unknown")
                return TransportResult("failed", "host total deadline exceeded")
            try:
                invocation_result = result_queue.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
        status, raw_action = invocation_result
        if time.monotonic() >= effective_deadline:
            if self.scheduler.is_current(token):
                settle_host("unknown")
                self.scheduler.expire(token)
            else:
                settle_host("unknown")
            return TransportResult("failed", "host total deadline exceeded")
        if status == "error":
            settle_host("unknown")
            return TransportResult("failed", "participant invocation failed")
        if not self.scheduler.is_current(token):
            settle_host("unknown")
            return None
        if _is_silence(raw_action):
            settle_host("silent")
            # A silence leaves no trace in the room; the participant's memory
            # keeps it, with the reason the participant gave, so a later turn
            # knows where it held back and why.
            self.memory.record_silence(
                about_event_id=wake["trigger_event_id"],
                why=raw_action.get("why") if raw_action is not None else None,
            )
            return None
        try:
            action = _validate_action(raw_action)
        except ParticipantError:
            settle_host("unknown")
            return TransportResult("failed", "participant returned an invalid action")
        # The reason is the participant's own memory; it never reaches the room.
        why = action.pop("why", None)
        if token.cancel_event.is_set() or not self.scheduler.is_current(token):
            settle_host("unknown")
            return None

        visible_event_ids = set(view.seen_event_ids)
        if action["origin_event_id"] not in visible_event_ids:
            settle_host("unknown")
            return TransportResult("failed", "action origin is absent from participant facts")
        if (
            action["kind"] in ("reply", "reaction")
            and action["target_event_id"] not in visible_event_ids
        ):
            settle_host("unknown")
            return TransportResult("failed", "action target is absent from participant facts")
        if action["kind"] == "reaction" and not self.reaction_capability().allows(
            action["reaction"], action.get("operation", "add")
        ):
            # The adapter's attested capability names the reactions the
            # participant may use; any other is refused before dispatch.
            settle_host("unknown")
            return TransportResult("unavailable", "the platform does not permit this reaction")
        if token.cancel_event.is_set() or not self.scheduler.is_current(token):
            settle_host("unknown")
            return None

        def dispatch() -> TransportResult:
            # This append and the native call share the scheduler's commit
            # lock. Cancellation ordered first yields no outbound call; the
            # already-invoked participant still receives a terminal ``unknown``
            # host receipt after commit rejection. Persistence failure also
            # prevents dispatch.
            # The host cannot truthfully claim ``sent`` before the separately
            # owned transport stage has observed the native result.  Persist
            # ``unknown`` as the action handoff state, then let transport alone
            # attest sent/failed/unknown/unavailable.
            if time.monotonic() >= effective_deadline:
                settle_host("unknown")
                self.scheduler.expire(token)
                return TransportResult(
                    "failed",
                    "host total deadline exceeded before dispatch",
                )
            settle_host("unknown")
            if (
                token.cancel_event.is_set()
                or time.monotonic() >= effective_deadline
            ):
                self.scheduler.expire(token)
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
                    if action["kind"] == "withdraw":
                        withdraw = getattr(self.privileged, "withdraw", None)
                        result = (
                            withdraw(proposal_id=action["proposal_id"], wake=wake)
                            if callable(withdraw)
                            else TransportResult("unavailable", "privileged actions are disabled")
                        )
                    elif action["kind"] == "privileged":
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
                                deadline=effective_deadline,
                            )
                    else:
                        result = self.transport.dispatch(action=action, wake=wake)
                except BaseException as exc:
                    dispatch_queue.put_nowait(("error", exc))
                else:
                    dispatch_queue.put_nowait(("ok", result))

            threading.Thread(
                target=invoke_dispatch,
                name=f"nunchi-transport-{token.generation}",
                daemon=True,
            ).start()
            while True:
                remaining = effective_deadline - time.monotonic()
                if remaining <= 0:
                    self.scheduler.expire(token)
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
                # Queue.get's timeout does not bound when this consumer is
                # scheduled again. Never accept a result observed too late.
                if time.monotonic() >= effective_deadline:
                    token.cancel_event.set()
                    self.scheduler.expire(token)
                    return TransportResult(
                        "unknown",
                        "host total deadline exceeded during dispatch",
                    )
                if status == "deadline":
                    self.scheduler.expire(token)
                    return value
                if status == "error":
                    raise value
                return value

        try:
            committed, result = self.scheduler.commit_dispatch(token, dispatch)
        except BaseException:
            if not host_receipt_persisted:
                raise
            committed = True
            result = TransportResult("unknown", "dispatch acknowledgement was lost")
        if not committed:
            settle_host("unknown")
            return None
        if not isinstance(result, TransportResult):
            result = TransportResult("unknown", "transport returned no attested result")
        self._append_transport_receipt(wake["request_id"], result)
        self.memory.record_reason(action, why)
        if (result.delivery, result.detail) == ("unknown", HARNESS_DELIVERS):
            # The harness posts it and may never show it back (#94 step 9d).
            self.memory.record_delivered(action, why=why)
        return result

    def _append_transport_receipt(
        self,
        request_id: str,
        result: TransportResult,
    ) -> None:
        self.receipts.append(
            {
                "request_id": request_id,
                "stage": "transport",
                "writer": "transport",
                "body": {
                    "delivery": result.delivery,
                    **({"detail": result.detail} if result.detail else {}),
                },
            },
            writer="transport",
        )

    def _append_host_receipt(
        self,
        wake: Mapping[str, Any],
        *,
        expansion_calls: int,
        invoked: bool = True,
        outcome: str,
    ) -> None:
        self.receipts.append(
            {
                "request_id": wake["request_id"],
                "stage": "participant-host",
                "writer": "participant-host",
                "body": participant_host_receipt_body(
                    wake,
                    expansion_calls=expansion_calls,
                    invoked=invoked,
                    outcome=outcome,
                ),
            },
            writer="participant-host",
        )
