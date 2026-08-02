"""Conversation-opportunity scheduling and the participant act-or-silence host."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
from .ack import (
    AckJournal,
    AckPolicy,
    ReactionCapability,
    UNAVAILABLE_REACTION_CAPABILITY,
    reaction_capability,
)
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
        self._lifecycle_id = str(uuid4())
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
            self._lifecycle_id = str(uuid4())

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

    @property
    def lifecycle_id(self) -> str:
        with self._lock:
            return self._lifecycle_id


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


def build_participant_wake(
    observation: ObservationProvider,
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build the fresh bounded facts delivered to any admitted participant."""

    checked_request = validate_attention_request(request)
    checked_decision = validate_attention_decision(
        decision,
        request=checked_request,
    )
    if checked_decision["status"] == "ok":
        effective = checked_decision["effective_disposition"]
        if effective == "SUPPRESS":
            return None
        source = effective if effective in ("ACK", "WAKE") else "DEFER"
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
        ack_policy: AckPolicy | None = None,
        ack_journal: AckJournal | None = None,
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
        self.ack_policy = ack_policy or AckPolicy()
        self.ack_journal = ack_journal or AckJournal()
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
            current_reaction.allows(self.ack_policy.reaction, "add")
            or current_reaction.allows(self.ack_policy.reaction, "remove")
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

    def acknowledge(
        self,
        *,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
        token: OpportunityToken,
        deadline: float,
    ) -> TransportResult | None:
        """Commit one durable core ACK without invoking the participant."""

        checked_request = validate_attention_request(request)
        checked_decision = validate_attention_decision(decision, request=checked_request)
        if (
            checked_decision.get("status") != "ok"
            or checked_decision.get("effective_disposition") != "ACK"
        ):
            raise ParticipantError("ACK host received a non-ACK decision")
        if token.anchor_event_id != checked_request["trigger_event_id"]:
            raise ParticipantError("ACK token does not match the exact trigger")
        if not self.scheduler.is_current(token) or time.monotonic() >= deadline:
            return None
        ack = checked_decision["ack"]
        capability = self.reaction_capability()
        if (
            not self.ack_policy.enabled
            or ack["reaction"] != self.ack_policy.reaction
            or ack["policy_provenance"] != self.ack_policy.provenance
            or ack["permissions_revision"] != capability.permissions_revision
            or not capability.allows(self.ack_policy.reaction, "add")
        ):
            # Capability widening normally happens inside AttentionEngine.
            # A mismatch here means authority changed after that decision; it
            # is stale and therefore cannot produce a native effect.
            wake = self._make_wake(checked_request, checked_decision)
            if wake is None:
                raise ParticipantError("ACK decision did not materialize current facts")
            result = TransportResult(
                "unavailable",
                "ACK authority changed before dispatch",
            )
            self._append_host_receipt(
                wake,
                expansion_calls=0,
                invoked=False,
                outcome="unknown",
            )
            self._append_transport_receipt(wake["request_id"], result)
            return result
        wake = self._make_wake(checked_request, checked_decision)
        if wake is None:
            raise ParticipantError("ACK decision did not materialize current facts")
        opportunity = self._protocol_opportunity(token, deadline=deadline)
        binding = {
            "request_id": checked_request["request_id"],
            "participant_id": wake["self"]["participant_id"],
            "actor_id": wake["self"]["actor_id"],
            "platform": wake["room"]["platform"],
            "room_id": wake["room"]["id"],
            "continuity_scope_id": wake["room"]["continuity_scope_id"],
            "target_event_id": wake["trigger_event_id"],
            "reaction": ack["reaction"],
            "operation": "add",
            "opportunity_generation": token.generation,
            "lifecycle_id": opportunity["lifecycle_id"],
            "deadline_id": opportunity["deadline_id"],
            "permissions_revision": capability.permissions_revision,
        }
        action = {
            "kind": "reaction",
            "origin_event_id": wake["trigger_event_id"],
            "target_event_id": wake["trigger_event_id"],
            "reaction": ack["reaction"],
            "operation": "add",
        }

        host_receipt_persisted = False

        def dispatch_ack() -> TransportResult:
            nonlocal host_receipt_persisted
            ack_id, reserved = self.ack_journal.reserve(binding)
            self._append_host_receipt(
                wake,
                expansion_calls=0,
                invoked=False,
                outcome="unknown",
            )
            host_receipt_persisted = True
            if not reserved:
                return TransportResult("unknown", "duplicate ACK was durably suppressed")
            try:
                current_capability = self.reaction_capability()
            except Exception:
                current_capability = UNAVAILABLE_REACTION_CAPABILITY
            if (
                current_capability.permissions_revision
                != binding["permissions_revision"]
                or not current_capability.allows(binding["reaction"], "add")
            ):
                result = TransportResult(
                    "unavailable",
                    "ACK authority changed at the native dispatch boundary",
                )
            elif token.cancel_event.is_set() or time.monotonic() >= deadline:
                result = TransportResult("failed", "ACK cancelled before native dispatch")
            else:
                try:
                    result = self.transport.dispatch(action=action, wake=wake)
                except BaseException:
                    result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
                if not isinstance(result, TransportResult):
                    result = TransportResult("unknown", "ACK transport result was unattested")
            self.ack_journal.settle(
                ack_id,
                delivery=result.delivery,
                detail=result.detail,
            )
            return result

        try:
            committed, result = self.scheduler.commit_dispatch(token, dispatch_ack)
        except BaseException:
            if not host_receipt_persisted:
                raise
            committed = True
            result = TransportResult(
                "unknown",
                "ACK dispatch acknowledgement was lost",
            )
        if not committed:
            return None
        if not isinstance(result, TransportResult):
            result = TransportResult("unknown", "ACK commit result was unattested")
        self._append_transport_receipt(wake["request_id"], result)
        return result

    def _make_wake(
        self,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        return build_participant_wake(self.observation, request, decision)

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
            self.scheduler.cancel()
            return TransportResult("failed", "host total deadline exceeded")
        wake = self._make_wake(checked_request, checked_decision)
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
                expansion_calls=expansion_calls,
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
                    self.scheduler.cancel()
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
                self.scheduler.cancel()
            else:
                settle_host("unknown")
            return TransportResult("failed", "host total deadline exceeded")
        if status == "error":
            settle_host("unknown")
            return TransportResult("failed", "participant invocation failed")
        if not self.scheduler.is_current(token):
            settle_host("unknown")
            return None
        if raw_action is None:
            settle_host("silent")
            return None
        try:
            action = _validate_action(raw_action)
        except ParticipantError:
            settle_host("unknown")
            return TransportResult("failed", "participant returned an invalid action")
        if token.cancel_event.is_set() or not self.scheduler.is_current(token):
            settle_host("unknown")
            return None

        visible_event_ids = {event["id"] for event in wake["events"]}
        visible_event_ids.update(expanded_event_ids)
        if action["origin_event_id"] not in visible_event_ids:
            settle_host("unknown")
            return TransportResult("failed", "action origin is absent from participant facts")
        if (
            action["kind"] in ("reply", "reaction")
            and action["target_event_id"] not in visible_event_ids
        ):
            settle_host("unknown")
            return TransportResult("failed", "action target is absent from participant facts")
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
                self.scheduler.cancel()
                return TransportResult(
                    "failed",
                    "host total deadline exceeded before dispatch",
                )
            settle_host("unknown")
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
                target=invoke_dispatch,
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
