"""Dependency-free runtime validation for the public Nunchi V2 seam.

The JSON schemas remain the portable oracle.  This module enforces the same
closed-document boundary on installed runtimes and adds the relational checks
that JSON Schema cannot express: exact trigger membership, unique event IDs,
actor reference integrity, ordered timestamps, advice citations, and receipt
stream ownership.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
import json
import math
from numbers import Real
from typing import Any

from .errors import ValidationError

DISPOSITIONS = ("SUPPRESS", "ACK", "WAKE", "DEFER")
WAKE_SOURCES = ("ACK", "WAKE", "DEFER", "ERROR_FALLBACK", "PREATTENTION_BYPASS")
RECEIPT_STAGES = ("observation", "attention", "participant-host", "transport")
RECEIPT_WRITERS = {
    "observation": "observation-provider",
    "attention": "attention-engine",
    "participant-host": "participant-host",
    "transport": "transport",
}
FORBIDDEN_SOCIAL_STATE = frozenset(
    {
        "reply",
        "draft",
        "handled",
        "open",
        "owed",
        "obligation",
        "permission",
        "roster",
        "speaker",
        "turn_owner",
        "continuation_handle",
        "cursor",
        "fetch_secret",
    }
)


def _fail(path: str, detail: str) -> None:
    raise ValidationError(f"{path}: {detail}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, "must be an object")
    return value


def _closed(
    value: Any,
    path: str,
    *,
    required: Sequence[str],
    optional: Sequence[str] = (),
) -> Mapping[str, Any]:
    doc = _mapping(value, path)
    allowed = set(required) | set(optional)
    missing = [name for name in required if name not in doc]
    if missing:
        _fail(path, f"missing required fields: {', '.join(missing)}")
    extra = sorted(set(doc) - allowed)
    if extra:
        _fail(path, f"unexpected fields: {', '.join(extra)}")
    return doc


def _nes(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, "must be a non-empty string")
    return value


def _string_list(
    value: Any,
    path: str,
    *,
    non_empty: bool = False,
    unique: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (non_empty and not value):
        _fail(path, "must be a non-empty array" if non_empty else "must be an array")
    for index, item in enumerate(value):
        _nes(item, f"{path}[{index}]")
    if unique and len(set(value)) != len(value):
        _fail(path, "must not contain duplicates")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(path, "must be a non-negative integer")
    return value


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(path, "must be a positive integer")
    return value


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _coverage(value: Any, path: str = "coverage") -> Mapping[str, Any]:
    doc = _closed(
        value,
        path,
        required=(
            "has_more_before",
            "has_more_after",
            "has_gaps",
            "truncated_by",
            "continuity",
            "has_restart_gap",
        ),
        optional=("max_events", "max_bytes", "max_age_seconds", "event_visibility"),
    )
    for name in ("has_more_before", "has_more_after", "has_restart_gap"):
        if doc[name] is not None and not isinstance(doc[name], bool):
            _fail(f"{path}.{name}", "must be a boolean or null")
    if not isinstance(doc["has_gaps"], bool):
        _fail(f"{path}.has_gaps", "must be a boolean")
    if not isinstance(doc["truncated_by"], list):
        _fail(f"{path}.truncated_by", "must be an array")
    if any(item not in ("events", "bytes", "age") for item in doc["truncated_by"]):
        _fail(f"{path}.truncated_by", "contains an unsupported truncation cause")
    if doc["continuity"] not in ("restart-safe", "session-only", "unknown"):
        _fail(f"{path}.continuity", "has an unsupported continuity value")
    for name in ("max_events", "max_bytes", "max_age_seconds"):
        if name in doc:
            _positive_int(doc[name], f"{path}.{name}")
    if "event_visibility" in doc:
        visibility = _mapping(doc["event_visibility"], f"{path}.event_visibility")
        for key, state in visibility.items():
            _nes(key, f"{path}.event_visibility key")
            if state not in ("history-and-live", "live-only", "unavailable", "unknown"):
                _fail(f"{path}.event_visibility.{key}", "has an unsupported visibility")
    return doc


def _actor_map(value: Any, path: str = "actors") -> Mapping[str, Any]:
    actors = _mapping(value, path)
    for actor_id, actor in actors.items():
        _nes(actor_id, f"{path} key")
        item = _closed(
            actor,
            f"{path}.{actor_id}",
            required=(),
            optional=("display_name", "kind"),
        )
        if "display_name" in item and not isinstance(item["display_name"], str):
            _fail(f"{path}.{actor_id}.display_name", "must be a string")
        if "kind" in item and item["kind"] not in ("human", "bot", "system", "unknown"):
            _fail(f"{path}.{actor_id}.kind", "has an unsupported actor kind")
    return actors


def _context_byte_count(
    events: list[Any],
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


def validate_canonical_event(value: Any, *, path: str = "event") -> dict[str, Any]:
    event = _mapping(value, path)
    event_type = event.get("type")
    common = ("id", "type")
    if event_type == "message":
        doc = _closed(
            event,
            path,
            required=common + ("author_id", "text", "mentioned_actor_ids", "mentions_room"),
            optional=("timestamp", "reply_to_event_id", "thread_root_event_id"),
        )
        _nes(doc["author_id"], f"{path}.author_id")
        if not isinstance(doc["text"], str):
            _fail(f"{path}.text", "must be a string")
        _string_list(doc["mentioned_actor_ids"], f"{path}.mentioned_actor_ids", unique=True)
        if not isinstance(doc["mentions_room"], bool):
            _fail(f"{path}.mentions_room", "must be a boolean")
        for name in ("timestamp", "reply_to_event_id", "thread_root_event_id"):
            if name in doc:
                _nes(doc[name], f"{path}.{name}")
    elif event_type == "reaction":
        doc = _closed(
            event,
            path,
            required=common
            + ("author_id", "target_event_id", "reaction", "operation"),
            optional=("timestamp",),
        )
        for name in ("author_id", "target_event_id", "reaction"):
            _nes(doc[name], f"{path}.{name}")
        if doc["operation"] not in ("add", "remove"):
            _fail(f"{path}.operation", "must be add or remove")
        if "timestamp" in doc:
            _nes(doc["timestamp"], f"{path}.timestamp")
    elif event_type == "membership":
        doc = _closed(
            event,
            path,
            required=common + ("scope", "subject_actor_id", "change"),
            optional=("caused_by_actor_id", "timestamp"),
        )
        scope = _closed(
            doc["scope"],
            f"{path}.scope",
            required=("kind", "id"),
        )
        if scope["kind"] not in ("room", "thread", "space", "unknown"):
            _fail(f"{path}.scope.kind", "has an unsupported scope kind")
        _nes(scope["id"], f"{path}.scope.id")
        _nes(doc["subject_actor_id"], f"{path}.subject_actor_id")
        if "caused_by_actor_id" in doc:
            _nes(doc["caused_by_actor_id"], f"{path}.caused_by_actor_id")
        if doc["change"] not in ("join", "leave"):
            _fail(f"{path}.change", "must be join or leave")
        if "timestamp" in doc:
            _nes(doc["timestamp"], f"{path}.timestamp")
    else:
        _fail(f"{path}.type", "must be message, reaction, or membership")
    _nes(event.get("id"), f"{path}.id")
    return deepcopy(dict(event))


def _event_actor_ids(event: Mapping[str, Any]) -> list[str]:
    if event["type"] == "message":
        return [event["author_id"], *event["mentioned_actor_ids"]]
    if event["type"] == "reaction":
        return [event["author_id"]]
    result = [event["subject_actor_id"]]
    if "caused_by_actor_id" in event:
        result.append(event["caused_by_actor_id"])
    return result


def _observation_fields(doc: Mapping[str, Any], *, require_schema: bool) -> None:
    if require_schema and doc.get("schema_version") != 2:
        _fail("schema_version", "must be 2")
    self_doc = _closed(
        doc["self"],
        "self",
        required=("participant_id", "actor_id"),
        optional=("names", "role", "description"),
    )
    _nes(self_doc["participant_id"], "self.participant_id")
    _nes(self_doc["actor_id"], "self.actor_id")
    if "names" in self_doc:
        _string_list(self_doc["names"], "self.names")
    for name in ("role", "description"):
        if name in self_doc and not isinstance(self_doc[name], str):
            _fail(f"self.{name}", "must be a string")

    room = _closed(
        doc["room"],
        "room",
        required=("platform", "id", "continuity_scope_id"),
        optional=("name", "kind"),
    )
    for name in ("platform", "id", "continuity_scope_id"):
        _nes(room[name], f"room.{name}")
    if "kind" in room and room["kind"] not in ("group", "direct", "unknown"):
        _fail("room.kind", "has an unsupported room kind")
    if "name" in room and not isinstance(room["name"], str):
        _fail("room.name", "must be a string")

    actors = _actor_map(doc["actors"])
    if self_doc["actor_id"] not in actors:
        _fail("self.actor_id", "does not resolve in actors")
    if not isinstance(doc["events"], list) or not doc["events"]:
        _fail("events", "must be a non-empty array")
    ids: set[str] = set()
    previous_timestamp: datetime | None = None
    for index, raw_event in enumerate(doc["events"]):
        event = validate_canonical_event(raw_event, path=f"events[{index}]")
        if event["id"] in ids:
            _fail(f"events[{index}].id", "duplicates an event ID in this snapshot")
        ids.add(event["id"])
        for actor_id in _event_actor_ids(event):
            if actor_id not in actors:
                _fail(f"events[{index}]", f"actor reference {actor_id!r} is absent from actors")
        current_timestamp = _timestamp(event.get("timestamp"))
        if (
            previous_timestamp is not None
            and current_timestamp is not None
            and current_timestamp < previous_timestamp
        ):
            _fail(f"events[{index}].timestamp", "contradicts authoritative event order")
        if current_timestamp is not None:
            previous_timestamp = current_timestamp
    _nes(doc["trigger_event_id"], "trigger_event_id")
    if doc["trigger_event_id"] not in ids:
        _fail("trigger_event_id", "must name an included event")
    coverage = _coverage(doc["coverage"])
    if (
        "max_events" in coverage
        and len(doc["events"]) > coverage["max_events"]
    ):
        _fail("events", "exceeds coverage.max_events")
    if (
        "max_bytes" in coverage
        and _context_byte_count(doc["events"], actors) > coverage["max_bytes"]
    ):
        _fail(
            "actors/events",
            "canonical context exceeds coverage.max_bytes",
        )
    if "continuation" in doc:
        continuation = _closed(
            doc["continuation"],
            "continuation",
            required=(
                "handle_id",
                "bound_to",
                "can_fetch_before",
                "can_fetch_after",
                "can_fetch_around_event",
                "max_events_per_fetch",
                "max_bytes_per_fetch",
            ),
            optional=("expires_at",),
        )
        _nes(continuation["handle_id"], "continuation.handle_id")
        binding = _closed(
            continuation["bound_to"],
            "continuation.bound_to",
            required=("participant_id", "room_id", "continuity_scope_id", "trigger_event_id"),
        )
        expected = {
            "participant_id": self_doc["participant_id"],
            "room_id": room["id"],
            "continuity_scope_id": room["continuity_scope_id"],
            "trigger_event_id": doc["trigger_event_id"],
        }
        if dict(binding) != expected:
            _fail("continuation.bound_to", "does not match the exact request binding")
        for name in ("can_fetch_before", "can_fetch_after", "can_fetch_around_event"):
            if not isinstance(continuation[name], bool):
                _fail(f"continuation.{name}", "must be a boolean")
        _positive_int(continuation["max_events_per_fetch"], "continuation.max_events_per_fetch")
        _positive_int(continuation["max_bytes_per_fetch"], "continuation.max_bytes_per_fetch")
        if "expires_at" in continuation:
            _nes(continuation["expires_at"], "continuation.expires_at")


def validate_attention_request(value: Any) -> dict[str, Any]:
    doc = _closed(
        value,
        "request",
        required=(
            "schema_version",
            "request_id",
            "self",
            "room",
            "actors",
            "events",
            "trigger_event_id",
            "coverage",
        ),
        optional=("continuation",),
    )
    _nes(doc["request_id"], "request_id")
    _observation_fields(doc, require_schema=True)
    return deepcopy(dict(doc))


def _classifier(value: Any, path: str = "classifier") -> Mapping[str, Any]:
    doc = _closed(value, path, required=("name",), optional=("provider", "model"))
    for name in doc:
        _nes(doc[name], f"{path}.{name}")
    return doc


def _routing(value: Any) -> Mapping[str, Any]:
    doc = _closed(
        value,
        "routing_audit",
        required=("valve", "override_cause", "margin_status"),
        optional=("effective_margin", "margin_source"),
    )
    valve = doc["valve"]
    if valve not in (
        "none",
        "classifier-defer",
        "margin-defer",
        "policy-defer",
        "capability-defer",
    ):
        _fail("routing_audit.valve", "has an unsupported valve")
    if doc["margin_status"] not in ("active", "retired"):
        _fail("routing_audit.margin_status", "must be active or retired")
    if valve in ("none", "classifier-defer") and doc["override_cause"] != "none":
        _fail("routing_audit.override_cause", "must be none for this valve")
    if valve == "margin-defer":
        if doc["override_cause"] != "margin" or doc["margin_status"] != "active":
            _fail("routing_audit", "margin-defer requires an active margin cause")
        margin = doc.get("effective_margin")
        if (
            isinstance(margin, bool)
            or not isinstance(margin, Real)
            or not math.isfinite(float(margin))
            or not 0 <= float(margin) <= 1
        ):
            _fail("routing_audit.effective_margin", "must be finite within [0, 1]")
    elif "effective_margin" in doc or "margin_source" in doc:
        _fail("routing_audit", "margin facts are allowed only when margin-defer applied")
    if valve == "policy-defer" and doc["override_cause"] not in (
        "suppression-disabled",
        "recoverability-unproven",
        "ack-disabled",
    ):
        _fail("routing_audit.override_cause", "does not match policy-defer")
    if valve == "capability-defer" and doc["override_cause"] != "ack-unsupported":
        _fail("routing_audit.override_cause", "does not match capability-defer")
    return doc


def _ack_audit(value: Any, path: str = "ack") -> Mapping[str, Any]:
    doc = _closed(
        value,
        path,
        required=("reaction", "policy_provenance", "permissions_revision"),
    )
    for name in doc:
        _nes(doc[name], f"{path}.{name}")
    return doc


def _advice(
    value: Any,
    event_ids: set[str] | None,
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    result = []
    for index, raw in enumerate(value):
        item = _closed(
            raw,
            f"{path}[{index}]",
            required=("note", "evidence_event_ids"),
        )
        _nes(item["note"], f"{path}[{index}].note")
        citations = _string_list(
            item["evidence_event_ids"],
            f"{path}[{index}].evidence_event_ids",
            non_empty=True,
        )
        missing = set(citations) - event_ids if event_ids is not None else set()
        if missing:
            _fail(f"{path}[{index}].evidence_event_ids", "contains an unknown event ID")
        result.append(deepcopy(dict(item)))
    return result


def validate_attention_decision(
    value: Any,
    *,
    request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    doc = _mapping(value, "decision")
    status = doc.get("status")
    event_ids = (
        {event["id"] for event in request["events"]}
        if request is not None
        else None
    )
    if status == "bypass":
        checked = _closed(doc, "decision", required=("status", "request_id", "cause"))
        if checked["cause"] != "preattention-disabled":
            _fail("decision.cause", "must be preattention-disabled")
    elif status == "error":
        checked = _closed(
            doc,
            "decision",
            required=("status", "error"),
            optional=("request_id", "classifier"),
        )
        error = _closed(checked["error"], "decision.error", required=("code", "detail"))
        _nes(error["code"], "decision.error.code")
        if not isinstance(error["detail"], str):
            _fail("decision.error.detail", "must be a string")
        if "classifier" in checked:
            _classifier(checked["classifier"])
    elif status == "ok":
        checked = _closed(
            doc,
            "decision",
            required=(
                "status",
                "request_id",
                "classifier_disposition",
                "effective_disposition",
                "routing_audit",
                "reasons",
                "evidence_event_ids",
                "classifier",
            ),
            optional=("legacy_verdict_confidences", "attention_advice", "ack"),
        )
        classifier_disposition = checked["classifier_disposition"]
        effective = checked["effective_disposition"]
        if classifier_disposition not in DISPOSITIONS or effective not in DISPOSITIONS:
            _fail("decision", "contains an unsupported disposition")
        routing = _routing(checked["routing_audit"])
        pair = (classifier_disposition, effective, routing["valve"])
        if pair not in (
            ("WAKE", "WAKE", "none"),
            ("ACK", "ACK", "none"),
            ("ACK", "DEFER", "policy-defer"),
            ("ACK", "DEFER", "capability-defer"),
            ("DEFER", "DEFER", "classifier-defer"),
            ("SUPPRESS", "DEFER", "margin-defer"),
            ("SUPPRESS", "DEFER", "policy-defer"),
            ("SUPPRESS", "SUPPRESS", "none"),
        ):
            _fail("decision", "contains an invalid disposition transition")
        if pair == ("ACK", "DEFER", "policy-defer") and routing["override_cause"] != "ack-disabled":
            _fail("decision.routing_audit.override_cause", "must be ack-disabled for ACK policy widening")
        if pair == ("ACK", "DEFER", "capability-defer") and routing["override_cause"] != "ack-unsupported":
            _fail("decision.routing_audit.override_cause", "must be ack-unsupported for ACK capability widening")
        if pair == ("SUPPRESS", "DEFER", "policy-defer") and routing["override_cause"] not in (
            "suppression-disabled",
            "recoverability-unproven",
        ):
            _fail("decision.routing_audit.override_cause", "must name a suppression policy widening")
        _string_list(checked["reasons"], "decision.reasons")
        evidence = _string_list(
            checked["evidence_event_ids"],
            "decision.evidence_event_ids",
            unique=True,
        )
        if event_ids is not None and set(evidence) - event_ids:
            _fail("decision.evidence_event_ids", "contains an unknown event ID")
        _classifier(checked["classifier"])
        if classifier_disposition == "SUPPRESS" and routing["margin_status"] == "active":
            if "legacy_verdict_confidences" not in checked:
                _fail("decision.legacy_verdict_confidences", "is required for active-margin suppression")
        if "legacy_verdict_confidences" in checked:
            vector = _closed(
                checked["legacy_verdict_confidences"],
                "decision.legacy_verdict_confidences",
                required=("PASS", "ACK", "ASK", "SPEAK"),
            )
            for key, raw in vector.items():
                if (
                    isinstance(raw, bool)
                    or not isinstance(raw, Real)
                    or not math.isfinite(float(raw))
                    or not 0 <= float(raw) <= 1
                ):
                    _fail(f"decision.legacy_verdict_confidences.{key}", "must be finite within [0, 1]")
        if "attention_advice" in checked:
            if pair != ("WAKE", "WAKE", "none"):
                _fail("decision.attention_advice", "is allowed only for WAKE")
            _advice(checked["attention_advice"], event_ids, "decision.attention_advice")
        if classifier_disposition == "ACK":
            if "ack" not in checked:
                _fail("decision.ack", "is required for an ACK selection")
            _ack_audit(checked["ack"], "decision.ack")
        elif "ack" in checked:
            _fail("decision.ack", "is allowed only for an ACK selection")
    else:
        _fail("decision.status", "must be ok, bypass, or error")
    if "request_id" in checked:
        _nes(checked["request_id"], "decision.request_id")
        if request is not None and checked["request_id"] != request["request_id"]:
            _fail("decision.request_id", "does not match the request")
    return deepcopy(dict(checked))


def validate_participant_wake(value: Any) -> dict[str, Any]:
    doc = _closed(
        value,
        "wake",
        required=(
            "request_id",
            "self",
            "room",
            "actors",
            "events",
            "trigger_event_id",
            "coverage",
            "attention",
        ),
        optional=("continuation",),
    )
    _nes(doc["request_id"], "wake.request_id")
    _observation_fields(doc, require_schema=False)
    attention = _closed(
        doc["attention"],
        "wake.attention",
        required=("source",),
        optional=("advice", "evidence_event_ids"),
    )
    source = attention["source"]
    if source not in WAKE_SOURCES:
        _fail("wake.attention.source", "has an unsupported wake source")
    event_ids = {event["id"] for event in doc["events"]}
    if source == "WAKE":
        if "advice" in attention:
            _advice(attention["advice"], event_ids, "wake.attention.advice")
        if "evidence_event_ids" in attention:
            citations = _string_list(
                attention["evidence_event_ids"],
                "wake.attention.evidence_event_ids",
                unique=True,
            )
            if set(citations) - event_ids:
                _fail("wake.attention.evidence_event_ids", "contains an unknown event ID")
    elif "advice" in attention or "evidence_event_ids" in attention:
        _fail("wake.attention", "DEFER, error fallback, and bypass must be advice-free")
    return deepcopy(dict(doc))


def validate_receipt(value: Any) -> dict[str, Any]:
    doc = _closed(value, "receipt", required=("request_id", "stage", "writer", "body"))
    _nes(doc["request_id"], "receipt.request_id")
    stage = doc["stage"]
    if stage not in RECEIPT_STAGES:
        _fail("receipt.stage", "has an unsupported stage")
    if doc["writer"] != RECEIPT_WRITERS[stage]:
        _fail("receipt.writer", "does not own this stage")
    body = _mapping(doc["body"], "receipt.body")
    if FORBIDDEN_SOCIAL_STATE.intersection(body):
        _fail("receipt.body", "contains forbidden social-state fields")
    if stage == "observation":
        checked = _closed(
            body,
            "receipt.body",
            required=(
                "schema_version",
                "trigger_event_id",
                "continuity_scope_id",
                "event_count",
                "byte_count",
                "coverage",
                "included_event_ids",
            ),
        )
        if checked["schema_version"] != 2:
            _fail("receipt.body.schema_version", "must be 2")
        for name in ("trigger_event_id", "continuity_scope_id"):
            _nes(checked[name], f"receipt.body.{name}")
        _nonnegative_int(checked["event_count"], "receipt.body.event_count")
        _nonnegative_int(checked["byte_count"], "receipt.body.byte_count")
        _coverage(checked["coverage"], "receipt.body.coverage")
        _string_list(checked["included_event_ids"], "receipt.body.included_event_ids", unique=True)
    elif stage == "attention":
        if "classifier_not_invoked" in body:
            checked = _closed(
                body,
                "receipt.body",
                required=("classifier_not_invoked", "cause", "policy_provenance"),
            )
            if checked["classifier_not_invoked"] is not True or checked["cause"] != "preattention-disabled":
                _fail("receipt.body", "is not a valid bypass receipt")
            _nes(checked["policy_provenance"], "receipt.body.policy_provenance")
        elif "error" in body:
            checked = _closed(
                body,
                "receipt.body",
                required=("error",),
                optional=("wake_action", "policy_provenance"),
            )
            error = _closed(checked["error"], "receipt.body.error", required=("code", "detail"))
            _nes(error["code"], "receipt.body.error.code")
            if not isinstance(error["detail"], str):
                _fail("receipt.body.error.detail", "must be a string")
            if ("wake_action" in checked) != ("policy_provenance" in checked):
                _fail("receipt.body", "wake override and provenance must appear together")
            if checked.get("wake_action") not in (None, "NO_WAKE"):
                _fail("receipt.body.wake_action", "must be NO_WAKE")
        else:
            checked = _closed(
                body,
                "receipt.body",
                required=(
                    "classifier_disposition",
                    "effective_disposition",
                    "classifier",
                    "evidence_event_ids",
                    "routing_audit",
                    "policy_provenance",
                ),
                optional=("ack",),
            )
            classifier = checked["classifier_disposition"]
            effective = checked["effective_disposition"]
            if classifier not in DISPOSITIONS or effective not in DISPOSITIONS:
                _fail("receipt.body", "contains an unsupported disposition")
            _classifier(checked["classifier"], "receipt.body.classifier")
            _string_list(checked["evidence_event_ids"], "receipt.body.evidence_event_ids")
            routing = _routing(checked["routing_audit"])
            pair = (classifier, effective, routing["valve"])
            if pair not in (
                ("WAKE", "WAKE", "none"),
                ("ACK", "ACK", "none"),
                ("ACK", "DEFER", "policy-defer"),
                ("ACK", "DEFER", "capability-defer"),
                ("DEFER", "DEFER", "classifier-defer"),
                ("SUPPRESS", "DEFER", "margin-defer"),
                ("SUPPRESS", "DEFER", "policy-defer"),
                ("SUPPRESS", "SUPPRESS", "none"),
            ):
                _fail("receipt.body", "contains an invalid disposition transition")
            if pair == ("ACK", "DEFER", "policy-defer") and routing["override_cause"] != "ack-disabled":
                _fail("receipt.body.routing_audit.override_cause", "must be ack-disabled for ACK policy widening")
            if pair == ("ACK", "DEFER", "capability-defer") and routing["override_cause"] != "ack-unsupported":
                _fail("receipt.body.routing_audit.override_cause", "must be ack-unsupported for ACK capability widening")
            if pair == ("SUPPRESS", "DEFER", "policy-defer") and routing["override_cause"] not in (
                "suppression-disabled",
                "recoverability-unproven",
            ):
                _fail("receipt.body.routing_audit.override_cause", "must name a suppression policy widening")
            _nes(checked["policy_provenance"], "receipt.body.policy_provenance")
            if checked["classifier_disposition"] == "ACK":
                if "ack" not in checked:
                    _fail("receipt.body.ack", "is required for an ACK selection")
                _ack_audit(checked["ack"], "receipt.body.ack")
            elif "ack" in checked:
                _fail("receipt.body.ack", "is allowed only for an ACK selection")
    elif stage == "participant-host":
        checked = _closed(
            body,
            "receipt.body",
            required=(
                "wake_source",
                "packet_event_count",
                "packet_byte_count",
                "delivered_event_ids",
                "expansion_calls",
                "invoked",
                "outcome",
            ),
        )
        if checked["wake_source"] not in WAKE_SOURCES:
            _fail("receipt.body.wake_source", "has an unsupported source")
        for name in ("packet_event_count", "packet_byte_count", "expansion_calls"):
            _nonnegative_int(checked[name], f"receipt.body.{name}")
        _string_list(checked["delivered_event_ids"], "receipt.body.delivered_event_ids")
        if not isinstance(checked["invoked"], bool):
            _fail("receipt.body.invoked", "must be a boolean")
        if checked["wake_source"] == "ACK" and checked["invoked"] is not False:
            _fail("receipt.body.invoked", "must be false for an ACK host record")
        if checked["outcome"] not in ("sent", "silent", "unknown"):
            _fail("receipt.body.outcome", "has an unsupported outcome")
    else:
        checked = _closed(body, "receipt.body", required=("delivery",), optional=("detail",))
        if checked["delivery"] not in ("sent", "failed", "unknown", "unavailable"):
            _fail("receipt.body.delivery", "has an unsupported outcome")
        if "detail" in checked and not isinstance(checked["detail"], str):
            _fail("receipt.body.detail", "must be a string")
    return deepcopy(dict(doc))


def validate_receipt_stream(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        _fail("receipts", "must be an array")
    validated = [validate_receipt(record) for record in records]
    if not validated:
        return []
    request_id = validated[0]["request_id"]
    stages = []
    for index, record in enumerate(validated):
        if record["request_id"] != request_id:
            _fail(f"receipts[{index}].request_id", "crosses request streams")
        stages.append(record["stage"])
    if stages != list(RECEIPT_STAGES[: len(stages)]):
        _fail("receipts", "must be a duplicate-free canonical stage prefix")
    return validated


def classifier_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return the only factual projection an attention model may receive."""
    checked = validate_attention_request(request)
    continuation = checked.pop("continuation", None)
    projection = deepcopy(checked)
    projection["expansion"] = {
        "available": continuation is not None,
        "can_fetch_before": bool(continuation and continuation["can_fetch_before"]),
        "can_fetch_after": bool(continuation and continuation["can_fetch_after"]),
        "can_fetch_around_event": bool(
            continuation and continuation["can_fetch_around_event"]
        ),
    }
    return projection
