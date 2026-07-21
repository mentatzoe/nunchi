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
    validate_attention_request,
)
from .policy import EffectiveAttentionPolicy


class ParticipantHostError(ValueError):
    pass


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


def build_participant_wake(
    snapshot: Any,
    decision: Any,
    *,
    policy: EffectiveAttentionPolicy,
) -> dict[str, Any]:
    """Build one I-010C packet from fresh participant-budgeted facts."""
    accepted = _validate_snapshot(snapshot, policy)
    if not isinstance(decision, dict):
        raise ParticipantHostError("attention decision is invalid")
    if decision.get("request_id") != accepted["request_id"]:
        raise ParticipantHostError("attention decision is not request-correlated")
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
    ) -> None:
        self.packet = copy.deepcopy(packet)
        self._continuation_fetch = continuation_fetch
        self._expansion_calls = 0

    @property
    def expansion_calls(self) -> int:
        return self._expansion_calls

    def fetch_context(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._continuation_fetch is None:
            raise ParticipantHostError("context expansion is unavailable")
        self._expansion_calls += 1
        return copy.deepcopy(self._continuation_fetch(copy.deepcopy(request)))


def _validate_action(value: Any) -> dict[str, Any] | None:
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
        if "mention_actor_ids" in value:
            mentions = value["mention_actor_ids"]
            if not isinstance(mentions, list) or not all(
                isinstance(item, str) and item for item in mentions
            ):
                raise ParticipantHostError("participant message action is invalid")
    elif kind == "reaction":
        if set(value) != {"kind", "target_event_id", "reaction"}:
            raise ParticipantHostError("participant reaction action is invalid")
        if not all(
            isinstance(value[field], str) and value[field]
            for field in ("target_event_id", "reaction")
        ):
            raise ParticipantHostError("participant reaction action is invalid")
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
) -> dict[str, Any]:
    return {
        "request_id": packet["request_id"],
        "stage": "participant-host",
        "writer": "participant-host",
        "body": {
            "wake_source": packet["attention"]["source"],
            "packet_event_count": len(packet["events"]),
            "packet_byte_count": _canonical_size(packet),
            "delivered_event_ids": [event["id"] for event in packet["events"]],
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
    if isinstance(decision, dict) and decision.get("status") == "ok" and decision.get(
        "effective_disposition"
    ) == "SUPPRESS":
        return {
            "status": "suppressed",
            "request_id": decision.get("request_id"),
            "invoked": False,
            "outcome": "suppressed",
        }
    packet = build_participant_wake(snapshot, decision, policy=policy)
    if (
        decision.get("status") == "error"
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
            "status": "no-wake",
            "request_id": packet["request_id"],
            "wake_source": "ERROR_FALLBACK",
            "invoked": False,
            "outcome": "unknown",
            "receipt_persistence": persistence,
        }

    turn = ParticipantTurn(packet, continuation_fetch)
    authorization_result = None
    action = None
    outcome = "unknown"
    host_error = None
    receipt_written = False
    persistence = "unknown"
    try:
        action = _validate_action(participant(turn))
        if action is None:
            outcome = "silent"
        elif action["kind"] == "privileged":
            if authorization_coordinator is None:
                host_error = "unsupported-privileged-seam"
            else:
                def persist_before_privileged_effect() -> None:
                    nonlocal outcome, persistence, receipt_written
                    outcome = "sent"
                    receipt = _participant_receipt(
                        packet=packet,
                        expansion_calls=turn.expansion_calls,
                        invoked=True,
                        outcome=outcome,
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
            # The participant-host stage attests that one concrete action was
            # offered to transport.  Persist it before the transport writes its
            # later delivery stage; delivery success/failure is not this
            # writer's fact and never rewrites the host record.
            outcome = "sent"
            receipt = _participant_receipt(
                packet=packet,
                expansion_calls=turn.expansion_calls,
                invoked=True,
                outcome=outcome,
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
        )
        try:
            returned = receipt_sink(copy.deepcopy(receipt))
            persistence = "persisted" if returned is None else "unknown"
        except Exception:
            persistence = "unknown"
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
