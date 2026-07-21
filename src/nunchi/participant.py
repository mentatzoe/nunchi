"""Framework-neutral V2 participant-turn host.

The host obeys one attention decision.  It never asks a second admission
question and never reclassifies an action at send time.  A woken participant
receives current materialized room facts plus optional bounded continuation and
returns one actual room action or ``None`` for silence.  Privileged tool actions
are routed through :mod:`nunchi.authorization` before any effect.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from typing import Any, Callable

from .authorization import (
    PrivilegedActionCoordinator,
    participant_authorization_result,
)
from .observation import (
    check_actor_reference_integrity,
    check_id_uniqueness,
    check_timestamp_order,
    check_trigger_membership,
    serialized_byte_size,
    validate_attention_request,
    validate_context_continuation,
)
from .policy import EffectiveAttentionPolicy


class ParticipantHostError(ValueError):
    pass


# The selected V2 operator-policy contract intentionally contains exactly six
# byte/event limits and has no expansion-call field.  Keep a host-owned absolute
# ceiling as defence in depth while the configured fetch limits bound every
# individual I-010D request and page.
MAX_EXPANSION_CALLS_PER_TURN = 8


def _canonical_size(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _validate_snapshot(value: Any, policy: EffectiveAttentionPolicy) -> dict[str, Any]:
    try:
        snapshot = copy.deepcopy(value)
    except Exception as exc:
        raise ParticipantHostError("participant snapshot is invalid") from exc
    errors = validate_attention_request(snapshot)
    if not errors:
        errors.extend(check_id_uniqueness(snapshot.get("events") or []))
        errors.extend(check_timestamp_order(snapshot.get("events") or []))
        errors.extend(check_trigger_membership(snapshot))
        errors.extend(check_actor_reference_integrity(snapshot))
    if errors:
        raise ParticipantHostError("participant snapshot is invalid")
    if snapshot["self"]["participant_id"] != policy.participant_id:
        raise ParticipantHostError("participant snapshot binding is invalid")
    if len(snapshot["events"]) > policy.participant_max_events:
        raise ParticipantHostError("participant snapshot exceeds event budget")
    return snapshot


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _classifier_audit(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) <= {"name", "provider", "model"}
        and "name" in value
        and all(_nonempty(item) for item in value.values())
    )


def _validate_attention_decision(
    value: Any,
    *,
    snapshot: dict[str, Any],
    policy: EffectiveAttentionPolicy,
) -> dict[str, Any]:
    """Validate the complete closed I-010B union and host-side binding."""
    try:
        decision = copy.deepcopy(value)
    except Exception as exc:
        raise ParticipantHostError("attention decision is invalid") from exc
    if not isinstance(decision, dict) or decision.get("request_id") != snapshot["request_id"]:
        raise ParticipantHostError("attention decision is not request-correlated")
    status = decision.get("status")
    if status == "bypass":
        if (
            set(decision) != {"status", "request_id", "cause"}
            or decision.get("cause") != "preattention-disabled"
            or policy.preattention_enabled
        ):
            raise ParticipantHostError("attention bypass is inconsistent with policy")
        return decision
    if status == "error":
        if (
            not policy.preattention_enabled
            or not {"status", "request_id", "error"} <= set(decision)
            or set(decision) - {"status", "request_id", "error", "classifier"}
            or not isinstance(decision.get("error"), dict)
            or set(decision["error"]) != {"code", "detail"}
            or not _nonempty(decision["error"].get("code"))
            or not isinstance(decision["error"].get("detail"), str)
            or ("classifier" in decision and not _classifier_audit(decision["classifier"]))
        ):
            raise ParticipantHostError("attention decision is invalid")
        return decision
    required = {
        "status", "request_id", "classifier_disposition",
        "effective_disposition", "routing_audit", "reasons",
        "evidence_event_ids", "classifier",
    }
    allowed = required | {"legacy_verdict_confidences", "attention_advice"}
    if (
        status != "ok"
        or not policy.preattention_enabled
        or not required <= set(decision)
        or set(decision) - allowed
        or not _classifier_audit(decision.get("classifier"))
        or not isinstance(decision.get("reasons"), list)
        or not all(_nonempty(item) for item in decision["reasons"])
        or not isinstance(decision.get("evidence_event_ids"), list)
        or not all(_nonempty(item) for item in decision["evidence_event_ids"])
    ):
        raise ParticipantHostError("attention decision is invalid")
    event_ids = {event["id"] for event in snapshot["events"]}
    if not set(decision["evidence_event_ids"]) <= event_ids:
        raise ParticipantHostError("attention decision cites unavailable evidence")
    routing = decision.get("routing_audit")
    if (
        not isinstance(routing, dict)
        or not {"valve", "override_cause", "margin_status"} <= set(routing)
        or set(routing) - {
            "valve", "override_cause", "margin_status",
            "effective_margin", "margin_source",
        }
        or routing.get("valve") not in {
            "none", "classifier-defer", "margin-defer", "policy-defer"
        }
        or routing.get("override_cause") not in {
            "none", "margin", "suppression-disabled", "recoverability-unproven"
        }
        or routing.get("margin_status") not in {"active", "retired"}
    ):
        raise ParticipantHostError("attention routing audit is invalid")
    valve = routing["valve"]
    if valve == "margin-defer":
        margin = routing.get("effective_margin")
        if (
            routing["override_cause"] != "margin"
            or routing["margin_status"] != "active"
            or isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(float(margin))
            or not 0 <= float(margin) <= 1
            or ("margin_source" in routing and not _nonempty(routing["margin_source"]))
        ):
            raise ParticipantHostError("attention routing audit is invalid")
    elif "effective_margin" in routing or "margin_source" in routing:
        raise ParticipantHostError("attention routing audit is invalid")
    if valve in {"none", "classifier-defer"} and routing["override_cause"] != "none":
        raise ParticipantHostError("attention routing audit is invalid")
    if valve == "policy-defer" and routing["override_cause"] not in {
        "suppression-disabled", "recoverability-unproven"
    }:
        raise ParticipantHostError("attention routing audit is invalid")
    pair = (decision.get("classifier_disposition"), decision.get("effective_disposition"), valve)
    if pair not in {
        ("WAKE", "WAKE", "none"),
        ("DEFER", "DEFER", "classifier-defer"),
        ("SUPPRESS", "DEFER", "margin-defer"),
        ("SUPPRESS", "DEFER", "policy-defer"),
        ("SUPPRESS", "SUPPRESS", "none"),
    }:
        raise ParticipantHostError("attention disposition pairing is invalid")
    advice = decision.get("attention_advice")
    if advice is not None:
        if pair != ("WAKE", "WAKE", "none") or not isinstance(advice, list):
            raise ParticipantHostError("attention advice is invalid")
        for item in advice:
            if (
                not isinstance(item, dict)
                or set(item) != {"note", "evidence_event_ids"}
                or not _nonempty(item.get("note"))
                or not isinstance(item.get("evidence_event_ids"), list)
                or not item["evidence_event_ids"]
                or not all(_nonempty(event_id) for event_id in item["evidence_event_ids"])
                or not set(item["evidence_event_ids"]) <= event_ids
            ):
                raise ParticipantHostError("attention advice is invalid")
    confidences = decision.get("legacy_verdict_confidences")
    if confidences is not None:
        if not isinstance(confidences, dict) or set(confidences) != {"PASS", "ACK", "ASK", "SPEAK"}:
            raise ParticipantHostError("legacy confidence audit is invalid")
        if any(
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not 0 <= float(score) <= 1
            for score in confidences.values()
        ):
            raise ParticipantHostError("legacy confidence audit is invalid")
    if (
        decision["classifier_disposition"] == "SUPPRESS"
        and routing["margin_status"] == "active"
        and confidences is None
    ):
        raise ParticipantHostError("legacy confidence audit is required")
    return decision


def build_participant_wake(
    snapshot: Any,
    decision: Any,
    *,
    policy: EffectiveAttentionPolicy,
) -> dict[str, Any]:
    """Build one I-010C packet from fresh participant-budgeted facts."""
    accepted = _validate_snapshot(snapshot, policy)
    decision = _validate_attention_decision(decision, snapshot=accepted, policy=policy)
    status = decision.get("status")
    attention: dict[str, Any]
    if status == "ok":
        effective = decision.get("effective_disposition")
        if effective not in ("WAKE", "DEFER"):
            raise ParticipantHostError("suppression does not produce a wake packet")
        attention = {"source": effective}
        if effective == "WAKE" and "attention_advice" in decision:
            event_ids = {event["id"] for event in accepted["events"]}
            advice = copy.deepcopy(decision["attention_advice"])
            cited = {
                event_id
                for item in advice
                for event_id in item.get("evidence_event_ids", [])
            }
            if not cited <= event_ids:
                raise ParticipantHostError("participant snapshot omitted advice evidence")
            attention["advice"] = advice
            attention["evidence_event_ids"] = sorted(cited)
    elif status == "bypass" and decision.get("cause") == "preattention-disabled":
        attention = {"source": "PREATTENTION_BYPASS"}
    elif status == "error":
        attention = {"source": "ERROR_FALLBACK"}
    else:
        raise ParticipantHostError("attention decision is invalid")
    packet = {
        "request_id": accepted["request_id"],
        "self": copy.deepcopy(accepted["self"]),
        "room": copy.deepcopy(accepted["room"]),
        "actors": copy.deepcopy(accepted["actors"]),
        "events": copy.deepcopy(accepted["events"]),
        "trigger_event_id": accepted["trigger_event_id"],
        "coverage": copy.deepcopy(accepted["coverage"]),
        "attention": attention,
    }
    if "continuation" in accepted:
        packet["continuation"] = copy.deepcopy(accepted["continuation"])
    if _canonical_size(packet) > policy.participant_max_bytes:
        raise ParticipantHostError("participant snapshot exceeds byte budget")
    return packet


class ParticipantTurn:
    """The participant's direct act-or-silence context."""

    def __init__(
        self,
        packet: dict[str, Any],
        continuation_fetch: Callable[[dict[str, Any]], dict[str, Any]] | None,
        *,
        policy: EffectiveAttentionPolicy | None = None,
        max_expansion_calls: int = MAX_EXPANSION_CALLS_PER_TURN,
        capabilities: frozenset[str] = frozenset(),
    ) -> None:
        self.packet = copy.deepcopy(packet)
        self._continuation_fetch = continuation_fetch
        self._policy = policy
        if (
            isinstance(max_expansion_calls, bool)
            or not isinstance(max_expansion_calls, int)
            or max_expansion_calls < 1
        ):
            raise ParticipantHostError("context expansion limit is invalid")
        self._max_expansion_calls = max_expansion_calls
        self._expansion_calls = 0
        self._fetch_requests: set[tuple[str, str, str | None, str | None]] = set()
        self._returned_cursors: set[str] = set()
        if not isinstance(capabilities, frozenset) or any(
            not _nonempty(capability) for capability in capabilities
        ):
            raise ParticipantHostError("participant capabilities are invalid")
        self.capabilities = tuple(sorted(capabilities))
        self._closed = False
        packet_events = self.packet.get("events", [])
        packet_actors = self.packet.get("actors", {})
        self._event_ids = {
            event["id"]
            for event in packet_events
            if isinstance(event, dict) and _nonempty(event.get("id"))
        }
        self._delivered_event_ids = [
            event["id"]
            for event in packet_events
            if isinstance(event, dict) and _nonempty(event.get("id"))
        ]
        self._actors = copy.deepcopy(packet_actors) if isinstance(packet_actors, dict) else {}

    @property
    def expansion_calls(self) -> int:
        return self._expansion_calls

    def close(self) -> None:
        self._closed = True
        self._continuation_fetch = None

    def binds_event(self, event_id: str) -> bool:
        return event_id in self._event_ids

    def binds_actor(self, actor_id: str) -> bool:
        return actor_id in self._actors

    @property
    def delivered_event_ids(self) -> tuple[str, ...]:
        return tuple(self._delivered_event_ids)

    def fetch_context(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._closed:
            raise ParticipantHostError("participant turn is closed")
        capability = self.packet.get("continuation")
        if (
            self._continuation_fetch is None
            or self._policy is None
            or not isinstance(capability, dict)
        ):
            raise ParticipantHostError("context expansion is unavailable")
        try:
            accepted_request = copy.deepcopy(request)
        except Exception as exc:
            raise ParticipantHostError("context expansion request is invalid") from exc
        if validate_context_continuation(accepted_request) or (
            "actors" in accepted_request or "coverage" in accepted_request
        ):
            raise ParticipantHostError("context expansion request is invalid")
        if (
            accepted_request["request_id"] != self.packet["request_id"]
            or accepted_request["handle_id"] != capability.get("handle_id")
        ):
            raise ParticipantHostError("context expansion binding is invalid")
        direction = accepted_request["direction"]
        direction_flag = {
            "before": "can_fetch_before",
            "after": "can_fetch_after",
            "around": "can_fetch_around_event",
        }[direction]
        if capability.get(direction_flag) is not True:
            raise ParticipantHostError("context expansion direction is unavailable")
        if accepted_request["max_events"] > min(
            self._policy.fetch_max_events,
            capability.get("max_events_per_fetch", 0),
        ):
            raise ParticipantHostError("context expansion exceeds event budget")
        if accepted_request["max_bytes"] > min(
            self._policy.fetch_max_bytes,
            capability.get("max_bytes_per_fetch", 0),
        ):
            raise ParticipantHostError("context expansion exceeds byte budget")
        request_key = (
            direction,
            accepted_request.get("anchor_event_id")
            or capability["bound_to"]["trigger_event_id"],
            accepted_request.get("cursor"),
            accepted_request.get("handle_id"),
        )
        if request_key in self._fetch_requests:
            raise ParticipantHostError("context expansion request was already consumed")
        if self._expansion_calls >= self._max_expansion_calls:
            raise ParticipantHostError("context expansion call limit is exhausted")
        self._fetch_requests.add(request_key)
        self._expansion_calls += 1
        try:
            page = copy.deepcopy(
                self._continuation_fetch(copy.deepcopy(accepted_request))
            )
        except Exception:
            raise
        if validate_context_continuation(page) or not (
            isinstance(page, dict) and "actors" in page and "coverage" in page
        ):
            raise ParticipantHostError("context expansion page is invalid")
        integrity_errors = check_id_uniqueness(page["events"])
        integrity_errors.extend(check_timestamp_order(page["events"]))
        integrity_errors.extend(check_actor_reference_integrity(page))
        if integrity_errors:
            raise ParticipantHostError("context expansion page is invalid")
        bound_to = capability["bound_to"]
        expected_anchor = accepted_request.get("anchor_event_id") or bound_to[
            "trigger_event_id"
        ]
        if (
            page["request_id"] != accepted_request["request_id"]
            or page["handle_id"] != accepted_request["handle_id"]
            or page["room_id"] != bound_to["room_id"]
            or page["continuity_scope_id"] != bound_to["continuity_scope_id"]
            or page["direction"] != direction
            or page["anchor_event_id"] != expected_anchor
        ):
            raise ParticipantHostError("context expansion page binding is invalid")
        if len(page["events"]) > accepted_request["max_events"]:
            raise ParticipantHostError("context expansion page exceeds event budget")
        page_event_bytes = sum(serialized_byte_size(event) for event in page["events"])
        if page_event_bytes > accepted_request["max_bytes"]:
            raise ParticipantHostError("context expansion page exceeds byte budget")
        coverage = page["coverage"]
        if (
            coverage.get("max_events") != accepted_request["max_events"]
            or coverage.get("max_bytes") != accepted_request["max_bytes"]
        ):
            raise ParticipantHostError("context expansion coverage is dishonest")
        next_cursor = page.get("next_cursor")
        if next_cursor is not None:
            if (
                next_cursor == accepted_request.get("cursor")
                or next_cursor in self._returned_cursors
            ):
                raise ParticipantHostError("context expansion cursor did not progress")
            self._returned_cursors.add(next_cursor)
        for actor_id, actor in page["actors"].items():
            if actor_id in self._actors and self._actors[actor_id] != actor:
                raise ParticipantHostError("context expansion actor identity changed")
        page_ids = {event["id"] for event in page["events"]}
        if page_ids & self._event_ids:
            raise ParticipantHostError("context expansion page overlaps delivered facts")
        self._actors.update(copy.deepcopy(page["actors"]))
        self._event_ids.update(page_ids)
        self._delivered_event_ids.extend(event["id"] for event in page["events"])
        return page


def _validate_action(value: Any, *, turn: ParticipantTurn) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ParticipantHostError("participant action is invalid")
    kind = value.get("kind")
    if kind == "message":
        required = {"kind", "content"}
        optional = {"reply_to_event_id", "mention_actor_ids"}
        if not required <= set(value) or set(value) - required - optional:
            raise ParticipantHostError("participant message action is invalid")
        if not isinstance(value["content"], str) or not value["content"]:
            raise ParticipantHostError("participant message action is invalid")
        if "reply_to_event_id" in value and (
            not isinstance(value["reply_to_event_id"], str)
            or not value["reply_to_event_id"]
        ):
            raise ParticipantHostError("participant message action is invalid")
        if "reply_to_event_id" in value and not turn.binds_event(value["reply_to_event_id"]):
            raise ParticipantHostError("participant reply target is unavailable")
        if "mention_actor_ids" in value:
            mentions = value["mention_actor_ids"]
            if not isinstance(mentions, list) or not all(
                isinstance(item, str) and item for item in mentions
            ):
                raise ParticipantHostError("participant message action is invalid")
            if any(not turn.binds_actor(actor_id) for actor_id in mentions):
                raise ParticipantHostError("participant mention target is unavailable")
    elif kind == "reaction":
        if set(value) != {"kind", "target_event_id", "reaction"}:
            raise ParticipantHostError("participant reaction action is invalid")
        if not all(
            isinstance(value[field], str) and value[field]
            for field in ("target_event_id", "reaction")
        ):
            raise ParticipantHostError("participant reaction action is invalid")
        if not turn.binds_event(value["target_event_id"]):
            raise ParticipantHostError("participant reaction target is unavailable")
    elif kind == "privileged":
        if set(value) != {"kind", "authorization_request", "operation"}:
            raise ParticipantHostError("participant privileged action is invalid")
        if not isinstance(value["authorization_request"], dict):
            raise ParticipantHostError("participant privileged action is invalid")
    else:
        raise ParticipantHostError("participant action kind is unsupported")
    return copy.deepcopy(value)


def _participant_receipt(
    *,
    packet: dict[str, Any],
    expansion_calls: int,
    invoked: bool,
    outcome: str,
    delivered_event_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": packet["request_id"],
        "stage": "participant-host",
        "writer": "participant-host",
        "body": {
            "wake_source": packet["attention"]["source"],
            "packet_event_count": len(packet["events"]),
            "packet_byte_count": _canonical_size(packet),
            "delivered_event_ids": list(delivered_event_ids or (
                event["id"] for event in packet["events"]
            )),
            "expansion_calls": expansion_calls,
            "invoked": invoked,
            "outcome": outcome,
        },
    }


def run_participant_turn(
    snapshot: Any,
    decision: Any,
    *,
    policy: EffectiveAttentionPolicy,
    participant: Callable[[ParticipantTurn], Any],
    receipt_sink: Callable[[dict[str, Any]], None],
    action_sink: Callable[[dict[str, Any]], Any] | None = None,
    correlated_action_sink: Callable[[str, dict[str, Any]], Any] | None = None,
    continuation_fetch: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    authorization_coordinator: PrivilegedActionCoordinator | None = None,
) -> dict[str, Any]:
    """Invoke one normal participant turn or stop on effective suppression."""
    if not isinstance(policy, EffectiveAttentionPolicy):
        raise ParticipantHostError("participant policy is invalid")
    if not callable(participant) or not callable(receipt_sink):
        raise ParticipantHostError("participant host callback is invalid")
    accepted_snapshot = _validate_snapshot(snapshot, policy)
    accepted_decision = _validate_attention_decision(
        decision,
        snapshot=accepted_snapshot,
        policy=policy,
    )
    if (
        accepted_decision.get("status") == "ok"
        and accepted_decision.get("effective_disposition") == "SUPPRESS"
    ):
        return {
            "status": "suppressed",
            "request_id": accepted_snapshot["request_id"],
            "invoked": False,
            "outcome": "suppressed",
        }
    packet = build_participant_wake(
        accepted_snapshot,
        accepted_decision,
        policy=policy,
    )
    if (
        accepted_decision.get("status") == "error"
        and policy.error_action == "NO_WAKE"
    ):
        receipt = _participant_receipt(
            packet=packet,
            expansion_calls=0,
            invoked=False,
            outcome="unknown",
        )
        try:
            returned = receipt_sink(copy.deepcopy(receipt))
            persistence = "persisted" if returned is None else "unknown"
        except Exception:
            persistence = "unknown"
        return {
            "status": "no-wake" if persistence == "persisted" else "error",
            "request_id": packet["request_id"],
            "wake_source": "ERROR_FALLBACK",
            "invoked": False,
            "outcome": "unknown",
            "receipt_persistence": persistence,
            **(
                {}
                if persistence == "persisted"
                else {"error": "participant-receipt-persistence-unknown"}
            ),
        }

    capabilities = set()
    if correlated_action_sink is not None or action_sink is not None:
        capabilities.update(("message", "reaction"))
    if authorization_coordinator is not None:
        capabilities.add("privileged")
    if continuation_fetch is not None and "continuation" in packet:
        capabilities.add("context-expansion")
    turn = ParticipantTurn(
        packet,
        continuation_fetch,
        policy=policy,
        capabilities=frozenset(capabilities),
    )
    authorization_result = None
    action = None
    outcome = "unknown"
    host_error = None
    receipt_written = False
    persistence = "unknown"
    try:
        try:
            raw_action = participant(turn)
        finally:
            turn.close()
        action = _validate_action(raw_action, turn=turn)
        if action is None:
            outcome = "silent"
        elif action["kind"] == "privileged":
            if authorization_coordinator is None:
                host_error = "unsupported-privileged-seam"
            else:
                def persist_before_privileged_effect() -> None:
                    nonlocal outcome, persistence, receipt_written
                    outcome = "unknown"
                    receipt = _participant_receipt(
                        packet=packet,
                        expansion_calls=turn.expansion_calls,
                        invoked=True,
                        outcome=outcome,
                        delivered_event_ids=turn.delivered_event_ids,
                    )
                    receipt_written = True
                    try:
                        returned = receipt_sink(copy.deepcopy(receipt))
                        persistence = "persisted" if returned is None else "unknown"
                    except Exception:
                        persistence = "unknown"
                        raise
                    if persistence != "persisted":
                        raise ParticipantHostError(
                            "participant receipt persistence is unknown"
                        )

                coordinated = authorization_coordinator.propose(
                    action,
                    snapshot,
                    before_execute=persist_before_privileged_effect,
                )
                authorization_result = participant_authorization_result(
                    coordinated["authorization"]
                )
                if coordinated["execution"] == "executed":
                    outcome = "sent"
                else:
                    outcome = "silent"
        elif correlated_action_sink is not None or action_sink is not None:
            # Before transport, the host can attest invocation and selection,
            # but not a downstream effect.  ``unknown`` is the only truthful
            # immutable outcome at this canonical receipt position.
            outcome = "unknown"
            receipt = _participant_receipt(
                packet=packet,
                expansion_calls=turn.expansion_calls,
                invoked=True,
                outcome=outcome,
                delivered_event_ids=turn.delivered_event_ids,
            )
            try:
                returned = receipt_sink(copy.deepcopy(receipt))
                persistence = "persisted" if returned is None else "unknown"
            except Exception:
                persistence = "unknown"
            receipt_written = True
            if persistence != "persisted":
                host_error = "participant-receipt-persistence-unknown"
                outcome = "unknown"
            elif correlated_action_sink is not None:
                returned = correlated_action_sink(
                    packet["request_id"], copy.deepcopy(action)
                )
                if returned is None:
                    outcome = "sent"
                else:
                    outcome = "unknown"
                    host_error = "action-sink-outcome-unknown"
            else:
                returned = action_sink(copy.deepcopy(action))
                if returned is None:
                    outcome = "sent"
                else:
                    outcome = "unknown"
                    host_error = "action-sink-outcome-unknown"
        elif action_sink is None:
            host_error = "action-sink-unavailable"
    except Exception:
        outcome = "unknown"
        host_error = "participant-or-action-failure"

    if not receipt_written:
        receipt = _participant_receipt(
            packet=packet,
            expansion_calls=turn.expansion_calls,
            invoked=True,
            outcome=outcome,
            delivered_event_ids=turn.delivered_event_ids,
        )
        try:
            returned = receipt_sink(copy.deepcopy(receipt))
            persistence = "persisted" if returned is None else "unknown"
        except Exception:
            persistence = "unknown"
        if persistence != "persisted" and host_error is None:
            host_error = "participant-receipt-persistence-unknown"
            outcome = "unknown"
    result = {
        "status": "completed" if host_error is None else "error",
        "request_id": packet["request_id"],
        "wake_source": packet["attention"]["source"],
        "invoked": True,
        "outcome": outcome,
        "receipt_persistence": persistence,
    }
    if action is not None:
        result["action_kind"] = action["kind"]
    if authorization_result is not None:
        result["authorization"] = authorization_result
    if host_error is not None:
        result["error"] = host_error
    return result


__all__ = [
    "ParticipantHostError",
    "ParticipantTurn",
    "build_participant_wake",
    "run_participant_turn",
]
