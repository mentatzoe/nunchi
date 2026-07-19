"""I-020A ObservationProviderV2 — shared, transport-neutral observation.

This module is slice 020's sole product artifact (plan Sec. "Conflict
ownership"). It normalizes transport-attested native events into stable
actors and literal relations, assembles bounded factual
``AttentionRequestV2`` snapshots (I-010A), exposes an optional host-owned
``ContextContinuationV2`` fetch seam (I-010D), and emits one immutable
observation-stage ``AttentionReceiptV2`` record (I-010E) per request.

There is deliberately no attention judgment, participant invocation, send
safety, or social ledger here (FR-005, FR-010): the provider tracks facts
only, and every retention decision is outcome-neutral.

Validation is slice 020's own explicit Python-stdlib adapter (FR-013):
``validate_attention_request``, ``validate_context_continuation``, and
``validate_attention_receipt_record`` mirror ``schemas/v2/attention-request
.schema.json``, ``schemas/v2/context-continuation.schema.json``, and the
immutable staged-record shape of ``schemas/v2/attention-receipt.schema
.json`` field-for-field, independent of ``tests/v2/contract/schema_helpers
.py`` (010-owned test code). ``check_actor_reference_integrity``,
``check_trigger_membership``, ``check_id_uniqueness``,
``check_timestamp_order``, ``check_binding_expiry``, and
``check_receipt_sequence`` cover the runtime-adapter-only relational rules
docs/contracts/nunchi-v2.md assigns to every I-010A/I-010D/I-010E consumer.
"""

from __future__ import annotations

import json
import math
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Constants shared by the runtime and the validation adapter
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 2
EVENT_TYPES = ("message", "reaction", "membership")
MEMBERSHIP_SCOPE_KINDS = ("room", "thread", "space", "unknown")
MEMBERSHIP_CHANGES = ("join", "leave")
REACTION_OPERATIONS = ("add", "remove")
ACTOR_KINDS = ("human", "bot", "unknown")
ROOM_KINDS = ("group", "direct", "unknown")
CONTINUITY_VALUES = ("restart-safe", "session-only", "unknown")
TRUNCATION_CAUSES = ("events", "bytes", "age")
EVENT_VISIBILITY_VALUES = ("history-and-live", "live-only", "unavailable", "unknown")
FETCH_DIRECTIONS = ("before", "after", "around")
RECEIPT_STAGES = ("observation", "attention", "participant-host", "transport")
RECEIPT_WRITERS = ("observation-provider", "attention-engine", "participant-host", "transport")
RECEIPT_WRITER_MAP = dict(zip(RECEIPT_STAGES, RECEIPT_WRITERS))
PARTICIPANT_HOST_OUTCOMES = ("sent", "silent", "unknown")
WAKE_SOURCES = ("WAKE", "DEFER", "ERROR_FALLBACK", "PREATTENTION_BYPASS")
TRANSPORT_DELIVERY = ("sent", "failed", "unknown", "unavailable")

# The FR-013 slice-owned token-size proxy. Evidence-only; never written onto
# I-010E, whose closed observation body has no token field (FR-015).
ESTIMATOR_ID = "utf8-bytes-ceil-div4@1"


class ObservationInputError(ValueError):
    """A candidate native event failed normalization (operational error).

    Per the spec edge case, a normalization failure after an authorized,
    routable native event is an operational error downstream — never a
    silent drop and never a social suppression decision.
    """


# ---------------------------------------------------------------------------
# Serialization and the token-size proxy (FR-013)
# ---------------------------------------------------------------------------


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def serialized_byte_size(value: Any) -> int:
    """Exact UTF-8 byte length of the canonical serialization of ``value``."""
    return len(_canonical_bytes(value))


def estimate_tokens(serialized_bytes: int) -> dict[str, Any]:
    """The slice-owned ``utf8-bytes-ceil-div4@1`` proxy (evidence only).

    ``estimated_tokens = (serialized_utf8_bytes + 3) // 4``. Carries
    ``model_id: null`` and makes no model-tokenizer claim (FR-013).
    """
    if not isinstance(serialized_bytes, int) or serialized_bytes < 0:
        raise ValueError("serialized_bytes must be a non-negative integer")
    return {
        "estimator_id": ESTIMATOR_ID,
        "estimated_tokens": (serialized_bytes + 3) // 4,
        "serialized_bytes": serialized_bytes,
        "model_id": None,
    }


def _parse_timestamp(value: Any) -> datetime | None:
    """Best-effort ISO-8601 parse; ``None`` for absent/unparseable (honest unknown)."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_timestamp_raw(value: Any) -> datetime | None:
    """Like ``_parse_timestamp`` but never normalizes a naive result to UTC,
    so callers can detect mixed timezone-aware/naive comparisons."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _mixed_timezone_awareness(left_raw: Any, right_raw: Any) -> bool:
    left = _parse_timestamp_raw(left_raw)
    right = _parse_timestamp_raw(right_raw)
    if left is None or right is None:
        return False
    return (left.tzinfo is None) != (right.tzinfo is None)


# ---------------------------------------------------------------------------
# Own stdlib validation adapter: schema-constraint mirrors (I-010A)
# ---------------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_positive_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 1
    return isinstance(value, float) and math.isfinite(value) and value.is_integer() and value >= 1


def _nes(value: Any) -> bool:
    return isinstance(value, str) and len(value) >= 1


class _Errors(list):
    def add(self, path: str, message: str) -> None:
        self.append(f"{path}: {message}")


def _closed_object(errors: _Errors, path: str, value: Any, required: tuple, allowed: tuple) -> bool:
    if not isinstance(value, dict):
        errors.add(path, "must be an object")
        return False
    for name in required:
        if name not in value:
            errors.add(path, f"missing required property {name!r}")
    for name in value:
        if name not in allowed:
            errors.add(path, f"unexpected property {name!r} (closed contract)")
    return True


def _check_nes(errors: _Errors, path: str, value: Any) -> None:
    if not _nes(value):
        errors.add(path, "must be a non-empty string")


def _check_enum(errors: _Errors, path: str, value: Any, allowed: tuple) -> None:
    if not isinstance(value, str) or value not in allowed:
        errors.add(path, f"must be one of {allowed}")


def _check_actor(errors: _Errors, path: str, value: Any) -> None:
    if not _closed_object(errors, path, value, (), ("display_name", "kind")):
        return
    if "display_name" in value and not isinstance(value["display_name"], str):
        errors.add(f"{path}.display_name", "must be a string")
    if "kind" in value:
        _check_enum(errors, f"{path}.kind", value["kind"], ACTOR_KINDS)


def _check_actor_map(errors: _Errors, path: str, value: Any) -> None:
    if not isinstance(value, dict):
        errors.add(path, "must be an object mapping actor ID to actor")
        return
    for actor_id, actor in value.items():
        if not _nes(actor_id):
            errors.add(f"{path}[{actor_id!r}]", "actor ID key must be a non-empty string")
        _check_actor(errors, f"{path}[{actor_id!r}]", actor)


def _check_message_event(errors: _Errors, path: str, event: dict) -> None:
    allowed = (
        "id", "type", "author_id", "timestamp", "text",
        "reply_to_event_id", "thread_root_event_id", "mentioned_actor_ids", "mentions_room",
    )
    required = ("id", "type", "author_id", "text", "mentioned_actor_ids", "mentions_room")
    if not _closed_object(errors, path, event, required, allowed):
        return
    _check_nes(errors, f"{path}.id", event.get("id"))
    _check_nes(errors, f"{path}.author_id", event.get("author_id"))
    if "timestamp" in event:
        _check_nes(errors, f"{path}.timestamp", event["timestamp"])
    if "text" in event and not isinstance(event["text"], str):
        errors.add(f"{path}.text", "must be a string")
    if "reply_to_event_id" in event:
        _check_nes(errors, f"{path}.reply_to_event_id", event["reply_to_event_id"])
    if "thread_root_event_id" in event:
        _check_nes(errors, f"{path}.thread_root_event_id", event["thread_root_event_id"])
    mentioned = event.get("mentioned_actor_ids")
    if "mentioned_actor_ids" in event:
        if not isinstance(mentioned, list):
            errors.add(f"{path}.mentioned_actor_ids", "must be an array of actor IDs")
        else:
            for index, actor_id in enumerate(mentioned):
                _check_nes(errors, f"{path}.mentioned_actor_ids[{index}]", actor_id)
    if "mentions_room" in event and not isinstance(event["mentions_room"], bool):
        errors.add(f"{path}.mentions_room", "must be a boolean")


def _check_reaction_event(errors: _Errors, path: str, event: dict) -> None:
    allowed = ("id", "type", "author_id", "timestamp", "target_event_id", "reaction", "operation")
    required = ("id", "type", "author_id", "target_event_id", "reaction", "operation")
    if not _closed_object(errors, path, event, required, allowed):
        return
    _check_nes(errors, f"{path}.id", event.get("id"))
    _check_nes(errors, f"{path}.author_id", event.get("author_id"))
    if "timestamp" in event:
        _check_nes(errors, f"{path}.timestamp", event["timestamp"])
    _check_nes(errors, f"{path}.target_event_id", event.get("target_event_id"))
    _check_nes(errors, f"{path}.reaction", event.get("reaction"))
    if "operation" in event:
        _check_enum(errors, f"{path}.operation", event["operation"], REACTION_OPERATIONS)


def _check_membership_event(errors: _Errors, path: str, event: dict) -> None:
    allowed = ("id", "type", "timestamp", "scope", "subject_actor_id", "caused_by_actor_id", "change")
    required = ("id", "type", "scope", "subject_actor_id", "change")
    if not _closed_object(errors, path, event, required, allowed):
        return
    _check_nes(errors, f"{path}.id", event.get("id"))
    if "timestamp" in event:
        _check_nes(errors, f"{path}.timestamp", event["timestamp"])
    scope = event.get("scope")
    if "scope" in event and _closed_object(errors, f"{path}.scope", scope, ("kind", "id"), ("kind", "id")):
        if "kind" in scope:
            _check_enum(errors, f"{path}.scope.kind", scope["kind"], MEMBERSHIP_SCOPE_KINDS)
        if "id" in scope:
            _check_nes(errors, f"{path}.scope.id", scope["id"])
    _check_nes(errors, f"{path}.subject_actor_id", event.get("subject_actor_id"))
    if "caused_by_actor_id" in event:
        _check_nes(errors, f"{path}.caused_by_actor_id", event["caused_by_actor_id"])
    if "change" in event:
        _check_enum(errors, f"{path}.change", event["change"], MEMBERSHIP_CHANGES)


def _check_event(errors: _Errors, path: str, event: Any) -> None:
    if not isinstance(event, dict):
        errors.add(path, "must be an object")
        return
    event_type = event.get("type")
    if event_type == "message":
        _check_message_event(errors, path, event)
    elif event_type == "reaction":
        _check_reaction_event(errors, path, event)
    elif event_type == "membership":
        _check_membership_event(errors, path, event)
    else:
        errors.add(f"{path}.type", f"must be one of {EVENT_TYPES}")


def _check_self(errors: _Errors, path: str, value: Any) -> None:
    if not _closed_object(
        errors, path, value,
        ("participant_id", "actor_id"),
        ("participant_id", "actor_id", "names", "role", "description"),
    ):
        return
    _check_nes(errors, f"{path}.participant_id", value.get("participant_id"))
    _check_nes(errors, f"{path}.actor_id", value.get("actor_id"))
    if "names" in value:
        names = value["names"]
        if not isinstance(names, list):
            errors.add(f"{path}.names", "must be an array")
        else:
            for index, name in enumerate(names):
                if not isinstance(name, str):
                    errors.add(f"{path}.names[{index}]", "must be a string")
    if "role" in value and not isinstance(value["role"], str):
        errors.add(f"{path}.role", "must be a string")
    if "description" in value and not isinstance(value["description"], str):
        errors.add(f"{path}.description", "must be a string")


def _check_room(errors: _Errors, path: str, value: Any) -> None:
    if not _closed_object(
        errors, path, value,
        ("platform", "id", "continuity_scope_id"),
        ("platform", "id", "continuity_scope_id", "name", "kind"),
    ):
        return
    _check_nes(errors, f"{path}.platform", value.get("platform"))
    _check_nes(errors, f"{path}.id", value.get("id"))
    _check_nes(errors, f"{path}.continuity_scope_id", value.get("continuity_scope_id"))
    if "name" in value and not isinstance(value["name"], str):
        errors.add(f"{path}.name", "must be a string")
    if "kind" in value:
        _check_enum(errors, f"{path}.kind", value["kind"], ROOM_KINDS)


def _check_coverage(errors: _Errors, path: str, value: Any) -> None:
    required = ("has_more_before", "has_more_after", "has_gaps", "truncated_by", "continuity", "has_restart_gap")
    allowed = required + ("max_events", "max_bytes", "max_age_seconds", "event_visibility")
    if not _closed_object(errors, path, value, required, allowed):
        return
    for name in ("max_events", "max_bytes", "max_age_seconds"):
        if name in value and not _is_positive_integer(value[name]):
            errors.add(f"{path}.{name}", "must be a positive integer (>= 1)")
    for name in ("has_more_before", "has_more_after", "has_restart_gap"):
        if name in value and value[name] is not None and not isinstance(value[name], bool):
            errors.add(f"{path}.{name}", "must be a boolean or null")
    if "has_gaps" in value and not isinstance(value["has_gaps"], bool):
        errors.add(f"{path}.has_gaps", "must be a boolean")
    truncated_by = value.get("truncated_by")
    if "truncated_by" in value:
        if not isinstance(truncated_by, list):
            errors.add(f"{path}.truncated_by", "must be an array")
        else:
            for index, item in enumerate(truncated_by):
                _check_enum(errors, f"{path}.truncated_by[{index}]", item, TRUNCATION_CAUSES)
    if "continuity" in value:
        _check_enum(errors, f"{path}.continuity", value["continuity"], CONTINUITY_VALUES)
    if "event_visibility" in value:
        visibility = value["event_visibility"]
        if not isinstance(visibility, dict):
            errors.add(f"{path}.event_visibility", "must be an object")
        else:
            for key, item in visibility.items():
                _check_enum(errors, f"{path}.event_visibility[{key!r}]", item, EVENT_VISIBILITY_VALUES)


def _check_continuation_binding(errors: _Errors, path: str, value: Any) -> None:
    fields = ("participant_id", "room_id", "continuity_scope_id", "trigger_event_id")
    if not _closed_object(errors, path, value, fields, fields):
        return
    for name in fields:
        _check_nes(errors, f"{path}.{name}", value.get(name))


def _check_continuation_capability(errors: _Errors, path: str, value: Any) -> None:
    required = (
        "handle_id", "bound_to", "can_fetch_before", "can_fetch_after",
        "can_fetch_around_event", "max_events_per_fetch", "max_bytes_per_fetch",
    )
    allowed = required + ("expires_at",)
    if not _closed_object(errors, path, value, required, allowed):
        return
    _check_nes(errors, f"{path}.handle_id", value.get("handle_id"))
    if "bound_to" in value:
        _check_continuation_binding(errors, f"{path}.bound_to", value["bound_to"])
    for name in ("can_fetch_before", "can_fetch_after", "can_fetch_around_event"):
        if name in value and not isinstance(value[name], bool):
            errors.add(f"{path}.{name}", "must be a boolean")
    for name in ("max_events_per_fetch", "max_bytes_per_fetch"):
        if name in value and not _is_positive_integer(value[name]):
            errors.add(f"{path}.{name}", "must be a positive integer (>= 1)")
    if "expires_at" in value:
        _check_nes(errors, f"{path}.expires_at", value["expires_at"])


def validate_attention_request(doc: Any) -> list[str]:
    """Mirror of ``schemas/v2/attention-request.schema.json`` (I-010A)."""
    errors = _Errors()
    required = ("schema_version", "request_id", "self", "room", "actors", "events", "trigger_event_id", "coverage")
    allowed = required + ("continuation",)
    if not _closed_object(errors, "request", doc, required, allowed):
        return list(errors)
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.add("schema_version", f"must be the number {SCHEMA_VERSION}")
    _check_nes(errors, "request_id", doc.get("request_id"))
    if "self" in doc:
        _check_self(errors, "self", doc["self"])
    if "room" in doc:
        _check_room(errors, "room", doc["room"])
    if "actors" in doc:
        _check_actor_map(errors, "actors", doc["actors"])
    events = doc.get("events")
    if "events" in doc:
        if not isinstance(events, list):
            errors.add("events", "must be an array of typed events")
        elif len(events) < 1:
            errors.add("events", "must contain at least one event")
        else:
            for index, event in enumerate(events):
                _check_event(errors, f"events[{index}]", event)
    if "trigger_event_id" in doc:
        _check_nes(errors, "trigger_event_id", doc["trigger_event_id"])
    if "coverage" in doc:
        _check_coverage(errors, "coverage", doc["coverage"])
    if "continuation" in doc:
        _check_continuation_capability(errors, "continuation", doc["continuation"])
    return list(errors)


def _check_fetch_request(errors: _Errors, doc: dict) -> None:
    required = ("request_id", "handle_id", "direction", "max_events", "max_bytes")
    allowed = required + ("anchor_event_id", "cursor")
    if not _closed_object(errors, "continuation", doc, required, allowed):
        return
    _check_nes(errors, "request_id", doc.get("request_id"))
    _check_nes(errors, "handle_id", doc.get("handle_id"))
    direction = doc.get("direction")
    if "direction" in doc:
        _check_enum(errors, "direction", direction, FETCH_DIRECTIONS)
    if "anchor_event_id" in doc:
        _check_nes(errors, "anchor_event_id", doc["anchor_event_id"])
    elif direction == "around":
        errors.add("anchor_event_id", "required when direction is 'around'")
    if "cursor" in doc:
        _check_nes(errors, "cursor", doc["cursor"])
    for name in ("max_events", "max_bytes"):
        if name in doc and not _is_positive_integer(doc[name]):
            errors.add(name, "must be a positive integer (>= 1)")


def _check_fetch_page(errors: _Errors, doc: dict) -> None:
    required = (
        "request_id", "handle_id", "room_id", "continuity_scope_id",
        "direction", "anchor_event_id", "actors", "events", "coverage",
    )
    allowed = required + ("next_cursor",)
    if not _closed_object(errors, "continuation", doc, required, allowed):
        return
    _check_nes(errors, "request_id", doc.get("request_id"))
    _check_nes(errors, "handle_id", doc.get("handle_id"))
    _check_nes(errors, "room_id", doc.get("room_id"))
    _check_nes(errors, "continuity_scope_id", doc.get("continuity_scope_id"))
    if "direction" in doc:
        _check_enum(errors, "direction", doc["direction"], FETCH_DIRECTIONS)
    _check_nes(errors, "anchor_event_id", doc.get("anchor_event_id"))
    if "actors" in doc:
        _check_actor_map(errors, "actors", doc["actors"])
    events = doc.get("events")
    if "events" in doc:
        if not isinstance(events, list):
            errors.add("events", "must be an array of typed events")
        else:
            for index, event in enumerate(events):
                _check_event(errors, f"events[{index}]", event)
    if "coverage" in doc:
        _check_coverage(errors, "coverage", doc["coverage"])
    if "next_cursor" in doc:
        _check_nes(errors, "next_cursor", doc["next_cursor"])


def validate_context_continuation(doc: Any) -> list[str]:
    """Mirror of ``schemas/v2/context-continuation.schema.json`` (I-010D).

    A bare ``oneOf`` over the fetch-request/fetch-page shapes: a page is
    distinguished by carrying ``actors`` or ``coverage``, fields no fetch
    request has.
    """
    if not isinstance(doc, dict):
        return ["continuation: must be an object"]
    errors = _Errors()
    if "actors" in doc or "coverage" in doc:
        _check_fetch_page(errors, doc)
    else:
        _check_fetch_request(errors, doc)
    return list(errors)


def _check_observation_body(errors: _Errors, path: str, value: Any) -> None:
    required = (
        "schema_version", "trigger_event_id", "continuity_scope_id",
        "event_count", "byte_count", "coverage", "included_event_ids",
    )
    if not _closed_object(errors, path, value, required, required):
        return
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.add(f"{path}.schema_version", f"must be the number {SCHEMA_VERSION}")
    _check_nes(errors, f"{path}.trigger_event_id", value.get("trigger_event_id"))
    _check_nes(errors, f"{path}.continuity_scope_id", value.get("continuity_scope_id"))
    for name in ("event_count", "byte_count"):
        amount = value.get(name)
        if name in value and (not _is_number(amount) or amount < 0 or not float(amount).is_integer()):
            errors.add(f"{path}.{name}", "must be an integer >= 0")
    if "coverage" in value:
        _check_coverage(errors, f"{path}.coverage", value["coverage"])
    cited = value.get("included_event_ids")
    if "included_event_ids" in value:
        if not isinstance(cited, list):
            errors.add(f"{path}.included_event_ids", "must be an array of event IDs")
        else:
            for index, event_id in enumerate(cited):
                _check_nes(errors, f"{path}.included_event_ids[{index}]", event_id)


def validate_attention_receipt_record(doc: Any) -> list[str]:
    """Mirror of the immutable staged-record shape (I-010E).

    Slice 020 attests only the ``observation`` stage body in full; the
    other three stage bodies are validated only at the envelope/writer-
    binding level, matching FR-015 ("leave later ... facts unknown ...
    never mutate or complete another owner's receipt stage").
    """
    errors = _Errors()
    required = ("request_id", "stage", "writer", "body")
    if not _closed_object(errors, "receipt", doc, required, required):
        return list(errors)
    _check_nes(errors, "request_id", doc.get("request_id"))
    stage = doc.get("stage")
    if "stage" in doc:
        _check_enum(errors, "stage", stage, RECEIPT_STAGES)
    writer = doc.get("writer")
    if "writer" in doc:
        _check_enum(errors, "writer", writer, RECEIPT_WRITERS)
    body = doc.get("body")
    if "body" in doc and not isinstance(body, dict):
        errors.add("body", "must be an object")
        return list(errors)
    if stage in RECEIPT_WRITER_MAP:
        expected_writer = RECEIPT_WRITER_MAP[stage]
        if writer is not None and writer != expected_writer:
            errors.add("writer", f"stage {stage!r} requires writer {expected_writer!r} (FR-010)")
        if stage == "observation" and isinstance(body, dict):
            _check_observation_body(errors, "body", body)
    return list(errors)


# ---------------------------------------------------------------------------
# Runtime-adapter-only relational rules (docs/contracts/nunchi-v2.md)
# ---------------------------------------------------------------------------


def check_id_uniqueness(*event_lists: list[dict]) -> list[str]:
    """Cross-item ID uniqueness across one or more event-bearing documents."""
    errors: list[str] = []
    seen: set[str] = set()
    for events in event_lists:
        if not isinstance(events, list):
            continue
        for event in events:
            event_id = event.get("id") if isinstance(event, dict) else None
            if event_id is None:
                continue
            if event_id in seen:
                errors.append(f"duplicate event id across documents: {event_id!r}")
            seen.add(event_id)
    return errors


def check_timestamp_order(events: list[dict]) -> list[str]:
    """Array order is authoritative; parseable timestamps must not contradict it."""
    errors: list[str] = []
    last: datetime | None = None
    last_index = -1
    for index, event in enumerate(events):
        parsed = _parse_timestamp(event.get("timestamp")) if isinstance(event, dict) else None
        if parsed is None:
            continue
        if last is not None and parsed < last:
            errors.append(
                f"events[{index}].timestamp precedes events[{last_index}].timestamp; "
                "array order is authoritative"
            )
        last, last_index = parsed, index
    return errors


def check_trigger_membership(doc: dict) -> list[str]:
    events = doc.get("events") or []
    trigger = doc.get("trigger_event_id")
    ids = {event.get("id") for event in events if isinstance(event, dict)}
    if trigger not in ids:
        return [f"trigger_event_id {trigger!r} does not name an event in events"]
    return []


def _actor_references(doc: dict) -> list[str]:
    refs: list[str] = []
    self_block = doc.get("self")
    if isinstance(self_block, dict) and "actor_id" in self_block:
        refs.append(self_block["actor_id"])
    for event in doc.get("events") or []:
        if not isinstance(event, dict):
            continue
        if "author_id" in event:
            refs.append(event["author_id"])
        if event.get("type") == "message":
            refs.extend(event.get("mentioned_actor_ids") or [])
        if event.get("type") == "membership":
            if "subject_actor_id" in event:
                refs.append(event["subject_actor_id"])
            if "caused_by_actor_id" in event:
                refs.append(event["caused_by_actor_id"])
    return refs


def check_actor_reference_integrity(doc: dict) -> list[str]:
    """``self.actor_id`` and every event actor reference must resolve in ``actors``."""
    actors = doc.get("actors")
    known = set(actors) if isinstance(actors, dict) else set()
    errors: list[str] = []
    for ref in _actor_references(doc):
        if ref not in known:
            errors.append(f"actor reference {ref!r} does not resolve to a key in actors")
    return errors


def check_binding_expiry(fetch_case: dict) -> list[str]:
    """Fetch-time binding/expiry validation (docs rule 6).

    ``fetch_case`` carries ``fetch_time``, ``issued`` (one or more issued
    continuation capabilities), the ``request`` (a bare fetch request), and
    the host's actual ``host_context`` at fetch time.
    """
    request = fetch_case.get("request") or {}
    shape_errors = _Errors()
    _check_fetch_request(shape_errors, request)
    if shape_errors:
        return list(shape_errors)

    handle_id = request.get("handle_id")
    matching = [
        entry
        for entry in fetch_case.get("issued") or []
        if isinstance(entry, dict) and entry.get("handle_id") == handle_id
    ]
    if not matching:
        return [f"handle_id {handle_id!r} was not issued for this continuity scope"]
    if len(matching) > 1:
        return [
            f"handle_id {handle_id!r} was issued more than once; a duplicate issued "
            "handle is rejected rather than resolved last-write-wins"
        ]
    capability = matching[0]
    capability_errors = _Errors()
    # ``cursors`` is fixture-only bookkeeping (the corpus's record of cursor
    # tokens minted under this handle so far) — not part of the closed
    # I-010A continuation wire shape, so it is excluded before the shape
    # check rather than rejected as an invented field.
    wire_capability = {key: value for key, value in capability.items() if key != "cursors"}
    _check_continuation_capability(capability_errors, "issued", wire_capability)
    if capability_errors:
        return list(capability_errors)

    errors: list[str] = []
    host_context = fetch_case.get("host_context") or {}
    fetch_time_raw = fetch_case.get("fetch_time")
    expires_at_raw = capability.get("expires_at")
    if _mixed_timezone_awareness(fetch_time_raw, expires_at_raw):
        errors.append(
            "fetch_time and expires_at mix timezone-aware and naive timestamps; "
            "cannot be compared safely"
        )
    else:
        fetch_time = _parse_timestamp(fetch_time_raw)
        expires_at = _parse_timestamp(expires_at_raw)
        if expires_at is not None and fetch_time is not None and fetch_time > expires_at:
            errors.append("handle is expired at fetch time")
    bound_to = capability.get("bound_to") or {}
    for field in ("participant_id", "room_id", "continuity_scope_id", "trigger_event_id"):
        if bound_to.get(field) != host_context.get(field):
            errors.append(
                f"host context {field}={host_context.get(field)!r} does not match "
                f"issued binding {field}={bound_to.get(field)!r}"
            )
    direction = request.get("direction")
    direction_flag = {
        "before": "can_fetch_before",
        "after": "can_fetch_after",
        "around": "can_fetch_around_event",
    }.get(direction)
    if direction_flag is not None and not capability.get(direction_flag):
        errors.append(f"direction {direction!r} is not authorized by the issued capability")
    for requested_field, cap_field in (
        ("max_events", "max_events_per_fetch"),
        ("max_bytes", "max_bytes_per_fetch"),
    ):
        requested = request.get(requested_field)
        cap = capability.get(cap_field)
        if isinstance(requested, (int, float)) and isinstance(cap, (int, float)) and requested > cap:
            errors.append(f"{requested_field}={requested!r} exceeds the issued cap {cap_field}={cap!r}")
    cursor = request.get("cursor")
    if cursor is not None:
        if cursor not in (capability.get("cursors") or []):
            errors.append(f"cursor {cursor!r} was not minted under handle {request.get('handle_id')!r}")
        else:
            # Cursors are minted as ``{handle_id}:{direction}:{sequence}``
            # (H020-01): a cursor minted for one direction must never be
            # replayable under a different direction, which would silently
            # re-serve events the minting direction's page already returned.
            cursor_parts = cursor.rsplit(":", 2)
            cursor_direction = cursor_parts[1] if len(cursor_parts) == 3 else None
            if cursor_direction is not None and cursor_direction != direction:
                errors.append(
                    f"cursor {cursor!r} was minted for direction {cursor_direction!r}; "
                    f"it cannot be replayed under direction {direction!r}"
                )
    return errors


def check_receipt_sequence(stream: list[dict]) -> list[str]:
    """Receipt-stage sequence rules (docs rule 7): one stream, canonical
    prefix order, each stage appended at most once, correct writer per stage."""
    errors: list[str] = []
    if not stream:
        return ["a receipt stream must carry at least one record"]
    request_ids = {record.get("request_id") for record in stream if isinstance(record, dict)}
    if len(request_ids) > 1:
        errors.append(f"a receipt stream must correlate one request_id; found {sorted(request_ids)}")
    seen_stages: list[str] = []
    for index, record in enumerate(stream):
        stage = record.get("stage") if isinstance(record, dict) else None
        writer = record.get("writer") if isinstance(record, dict) else None
        if stage not in RECEIPT_STAGES:
            errors.append(f"stream[{index}] has an unknown stage {stage!r}")
            continue
        if stage in seen_stages:
            errors.append(f"stage {stage!r} is appended more than once")
            continue
        expected_index = RECEIPT_STAGES.index(stage)
        if expected_index != len(seen_stages):
            errors.append(
                f"stage {stage!r} is out of canonical order; expected next stage "
                f"{RECEIPT_STAGES[len(seen_stages)]!r}"
            )
        if writer != RECEIPT_WRITER_MAP.get(stage):
            errors.append(f"stage {stage!r} was written by {writer!r}, not its sole owner")
        seen_stages.append(stage)
    return errors


# ---------------------------------------------------------------------------
# ObservationProvider — I-020A runtime
# ---------------------------------------------------------------------------

DUPLICATE_RETAINED = "duplicate-retained"
SELF_RETAINED_NO_WAKE = "self-retained-no-wake"
UNROUTABLE = "unroutable"
OBSERVED = "observed"


class ObservationProvider:
    """Bounded, outcome-neutral shared observation buffer for one room scope.

    Binds ``self.actor_id`` from a transport- or host-attested identity
    only (FR-002); no name/alias/role/text ever establishes authorship.
    Retention is bounded by ``retention_max_events`` regardless of any
    later attention outcome (FR-010).
    """

    def __init__(
        self,
        *,
        participant_id: str,
        actor_id: str,
        platform: str,
        room_id: str,
        continuity_scope_id: str,
        names: list[str] | None = None,
        role: str | None = None,
        description: str | None = None,
        room_name: str | None = None,
        room_kind: str | None = None,
        continuity: str = "session-only",
        retention_max_events: int = 2000,
        event_visibility: dict[str, str] | None = None,
    ) -> None:
        if continuity not in CONTINUITY_VALUES:
            raise ValueError(f"continuity must be one of {CONTINUITY_VALUES}")
        self.participant_id = participant_id
        self.actor_id = actor_id
        self.names = list(names) if names else None
        self.role = role
        self.description = description
        self.platform = platform
        self.room_id = room_id
        self.continuity_scope_id = continuity_scope_id
        self.room_name = room_name
        self.room_kind = room_kind
        self.continuity = continuity
        self.event_visibility = dict(event_visibility) if event_visibility else None

        self._events: deque[dict] = deque(maxlen=retention_max_events)
        self._event_index: dict[str, int] = {}
        self._actors: dict[str, dict] = {}
        self._seen_delivery_ids: set[str] = set()
        self._evicted = False
        self._unroutable_count = 0

    # -- identity -----------------------------------------------------

    def self_block(self) -> dict:
        block: dict[str, Any] = {"participant_id": self.participant_id, "actor_id": self.actor_id}
        if self.names:
            block["names"] = list(self.names)
        if self.role is not None:
            block["role"] = self.role
        if self.description is not None:
            block["description"] = self.description
        return block

    def room_block(self) -> dict:
        block: dict[str, Any] = {
            "platform": self.platform,
            "id": self.room_id,
            "continuity_scope_id": self.continuity_scope_id,
        }
        if self.room_name is not None:
            block["name"] = self.room_name
        if self.room_kind is not None:
            block["kind"] = self.room_kind
        return block

    # -- ingestion (FR-003, FR-004, FR-010) ----------------------------

    def ingest(self, native_event_input: dict) -> str:
        """Normalize one transport-attested native event input.

        Returns one of ``observed``, ``duplicate-retained``,
        ``self-retained-no-wake``, or ``unroutable`` — the only three
        mechanical no-wake classes plus the ordinary observed case
        (FR-004). Never derives authorization or routing from payload
        content: ``authorized``/``reason`` must be supplied explicitly.

        Exact self-causation (D020-01): an event is self-caused, and thus
        ``self-retained-no-wake``, only when its own transport-attested
        ``author_id`` matches ``self.actor_id`` (``message``/``reaction``),
        or, for a ``membership`` event with no ``author_id``, when its
        ``caused_by_actor_id`` exactly matches ``self.actor_id``. A
        membership event where self appears only as ``subject_actor_id``
        (acted upon, not acting) remains ordinary ``observed`` — being the
        subject of another actor's action is not the participant's own
        action.
        """
        if not isinstance(native_event_input, dict):
            raise ObservationInputError("native event input must be an object")
        delivery_id = native_event_input.get("delivery_id")
        if not _nes(delivery_id):
            raise ObservationInputError("delivery_id is required and must be a non-empty string")
        disposition = native_event_input.get("disposition")
        if disposition not in ("candidate-event", "unroutable"):
            raise ObservationInputError("disposition must be 'candidate-event' or 'unroutable'")

        if disposition == "unroutable":
            if not _nes(native_event_input.get("reason")):
                raise ObservationInputError(
                    "unroutable requires the transport-owned proof in 'reason'"
                )
            self._unroutable_count += 1
            return UNROUTABLE

        if native_event_input.get("authorized") is not True:
            raise ObservationInputError(
                "candidate-event requires transport-attested authorization "
                "('authorized': True); it is never derived from payload content"
            )

        if delivery_id in self._seen_delivery_ids:
            return DUPLICATE_RETAINED
        self._seen_delivery_ids.add(delivery_id)

        event = native_event_input.get("event")
        errors = _Errors()
        _check_event(errors, "event", event)
        if errors:
            raise ObservationInputError(
                f"candidate-event failed normalization (operational error): {list(errors)}"
            )
        event_id = event["id"]
        if event_id in self._event_index:
            raise ObservationInputError(
                f"event id {event_id!r} collides with an already-observed event "
                "(cross-item ID uniqueness)"
            )

        actor_facts = native_event_input.get("actors") or {}
        if not isinstance(actor_facts, dict):
            raise ObservationInputError("actors must be an object mapping actor ID to actor facts")
        for actor_id, facts in actor_facts.items():
            merged = dict(self._actors.get(actor_id, {}))
            merged.update({k: v for k, v in (facts or {}).items() if v is not None})
            self._actors[actor_id] = merged
        for ref in _actor_references({"self": None, "events": [event]}):
            self._actors.setdefault(ref, {})

        if len(self._events) == self._events.maxlen:
            self._evicted = True
        self._events.append(event)
        self._reindex()

        is_self_caused = event.get("author_id") == self.actor_id or (
            event.get("type") == "membership" and event.get("caused_by_actor_id") == self.actor_id
        )
        return SELF_RETAINED_NO_WAKE if is_self_caused else OBSERVED

    def _reindex(self) -> None:
        self._event_index = {event["id"]: index for index, event in enumerate(self._events)}

    # -- snapshot assembly (FR-006, FR-007) ----------------------------

    def _relation_closure_ids(self, trigger: dict) -> list[str]:
        if trigger.get("type") == "message":
            return [
                event_id
                for event_id in (trigger.get("reply_to_event_id"), trigger.get("thread_root_event_id"))
                if event_id
            ]
        if trigger.get("type") == "reaction":
            return [trigger["target_event_id"]] if trigger.get("target_event_id") else []
        return []

    def snapshot(
        self,
        *,
        trigger_event_id: str,
        max_events: int,
        max_bytes: int,
        max_age_seconds: int | None = None,
        request_id: str | None = None,
    ) -> dict:
        """Assemble one bounded, trigger-first ``AttentionRequestV2`` document."""
        if not _is_positive_integer(max_events) or not _is_positive_integer(max_bytes):
            raise ValueError("max_events and max_bytes must be positive integers")
        events = list(self._events)
        trigger_index = self._event_index.get(trigger_event_id)
        if trigger_index is None:
            raise ValueError(f"trigger_event_id {trigger_event_id!r} is not an observed event")
        trigger = events[trigger_index]

        trigger_time = _parse_timestamp(trigger.get("timestamp"))
        age_cutoff = None
        if max_age_seconds is not None and trigger_time is not None:
            age_cutoff = trigger_time.timestamp() - max_age_seconds

        def within_age(event: dict) -> bool:
            if age_cutoff is None:
                return True
            parsed = _parse_timestamp(event.get("timestamp"))
            if parsed is None:
                return True
            return parsed.timestamp() >= age_cutoff

        selected: dict[int, dict] = {trigger_index: trigger}
        truncated_by: set[str] = set()
        total_bytes = serialized_byte_size(trigger)
        if total_bytes > max_bytes:
            truncated_by.add("bytes")

        def try_add(index: int) -> bool:
            nonlocal total_bytes
            if index in selected:
                return True
            if len(selected) >= max_events:
                truncated_by.add("events")
                return False
            candidate = events[index]
            if not within_age(candidate):
                truncated_by.add("age")
                return False
            size = serialized_byte_size(candidate)
            if total_bytes + size > max_bytes:
                truncated_by.add("bytes")
                return False
            selected[index] = candidate
            total_bytes += size
            return True

        for relation_id in self._relation_closure_ids(trigger):
            relation_index = self._event_index.get(relation_id)
            if relation_index is not None:
                try_add(relation_index)

        before_index = trigger_index - 1
        after_index = trigger_index + 1
        has_more_before = False
        has_more_after = False
        while before_index >= 0 or after_index < len(events):
            progressed = False
            if after_index < len(events):
                progressed = True
                if not try_add(after_index):
                    has_more_after = True
                after_index += 1
            if before_index >= 0:
                progressed = True
                if not try_add(before_index):
                    has_more_before = True
                before_index -= 1
            if not progressed:
                break
        if before_index >= 0:
            has_more_before = True
        if after_index < len(events):
            has_more_after = True

        included_indices = sorted(selected)
        included_events = [selected[index] for index in included_indices]
        has_gaps = self._evicted and included_indices[0] == 0
        if not has_gaps:
            has_gaps = any(
                b - a > 1 for a, b in zip(included_indices, included_indices[1:])
            )

        actors_used = {ref for event in included_events for ref in _actor_references({"self": None, "events": [event]})}
        actors_used.add(self.actor_id)
        actors = {actor_id: dict(self._actors.get(actor_id, {})) for actor_id in actors_used}

        coverage: dict[str, Any] = {
            "has_more_before": has_more_before,
            "has_more_after": has_more_after,
            "has_gaps": has_gaps,
            "truncated_by": sorted(truncated_by),
            "continuity": self.continuity,
            "has_restart_gap": False if self.continuity != "unknown" else None,
            "max_events": max_events,
            "max_bytes": max_bytes,
        }
        if max_age_seconds is not None:
            coverage["max_age_seconds"] = max_age_seconds
        if self.event_visibility:
            coverage["event_visibility"] = dict(self.event_visibility)

        document: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id or f"req-{uuid.uuid4()}",
            "self": self.self_block(),
            "room": self.room_block(),
            "actors": actors,
            "events": included_events,
            "trigger_event_id": trigger_event_id,
            "coverage": coverage,
        }
        errors = validate_attention_request(document)
        if errors:
            raise ObservationInputError(f"assembled snapshot failed self-validation: {errors}")
        return document

    # -- observation-stage receipt (FR-015) ----------------------------

    def build_observation_receipt(self, request: dict) -> dict:
        """One immutable observation-stage I-010E record for ``request``.

        Attests only snapshot/coverage facts this provider can prove;
        never adds an estimated-token field (token-proxy evidence stays
        separate, FR-015) and never mutates or completes another stage.
        """
        events = request["events"]
        body = {
            "schema_version": SCHEMA_VERSION,
            "trigger_event_id": request["trigger_event_id"],
            "continuity_scope_id": request["room"]["continuity_scope_id"],
            "event_count": len(events),
            "byte_count": sum(serialized_byte_size(event) for event in events),
            "coverage": request["coverage"],
            "included_event_ids": [event["id"] for event in events],
        }
        record = {
            "request_id": request["request_id"],
            "stage": "observation",
            "writer": "observation-provider",
            "body": body,
        }
        errors = validate_attention_receipt_record(record)
        if errors:
            raise ObservationInputError(f"assembled receipt failed self-validation: {errors}")
        return record


# ---------------------------------------------------------------------------
# ContinuationProvider — host-owned I-010D fetch seam
# ---------------------------------------------------------------------------


class ContinuationError(ValueError):
    """A fetch request failed binding/expiry validation (rejected, not served)."""


class ContinuationProvider:
    """Host-owned, bounded, opaque-to-room-data continuation over one
    :class:`ObservationProvider`'s buffer (FR-008, FR-009)."""

    def __init__(self, provider: ObservationProvider) -> None:
        self._provider = provider
        self._capabilities: dict[str, dict] = {}
        self._cursors: dict[str, set[str]] = {}
        self._cursor_windows: dict[str, dict[str, dict[str, Any]]] = {}
        self._cursor_sequences: dict[str, int] = {}

    def issue(
        self,
        *,
        trigger_event_id: str,
        max_events_per_fetch: int,
        max_bytes_per_fetch: int,
        can_fetch_before: bool = True,
        can_fetch_after: bool = True,
        can_fetch_around_event: bool = True,
        expires_at: str | None = None,
    ) -> dict:
        if trigger_event_id not in self._provider._event_index:
            raise ValueError(f"trigger_event_id {trigger_event_id!r} is not an observed event")
        handle_id = f"cont-{uuid.uuid4().hex[:12]}"
        capability = {
            "handle_id": handle_id,
            "bound_to": {
                "participant_id": self._provider.participant_id,
                "room_id": self._provider.room_id,
                "continuity_scope_id": self._provider.continuity_scope_id,
                "trigger_event_id": trigger_event_id,
            },
            "can_fetch_before": can_fetch_before,
            "can_fetch_after": can_fetch_after,
            "can_fetch_around_event": can_fetch_around_event,
            "max_events_per_fetch": max_events_per_fetch,
            "max_bytes_per_fetch": max_bytes_per_fetch,
        }
        if expires_at is not None:
            capability["expires_at"] = expires_at
        errors = _Errors()
        _check_continuation_capability(errors, "continuation", capability)
        if errors:
            raise ValueError(f"issued capability failed self-validation: {list(errors)}")
        self._capabilities[handle_id] = capability
        self._cursors[handle_id] = set()
        self._cursor_windows[handle_id] = {}
        self._cursor_sequences[handle_id] = 0
        return capability

    def fetch(self, request: dict, *, host_context: dict, fetch_time: str | None = None) -> dict:
        """Validate binding/expiry/direction/caps/cursor, then serve one page."""
        errors = validate_context_continuation(request)
        if errors:
            raise ContinuationError(f"malformed fetch request: {errors}")

        handle_id = request["handle_id"]
        capability = self._capabilities.get(handle_id)
        fetch_case = {
            "fetch_time": fetch_time,
            "issued": [capability] if capability else [],
            "request": request,
            "host_context": host_context,
        }
        binding_errors = check_binding_expiry(fetch_case)
        if binding_errors:
            raise ContinuationError(f"binding/expiry validation failed: {binding_errors}")

        events = list(self._provider._events)
        index = self._provider._event_index
        direction = request["direction"]
        anchor_id = request.get("anchor_event_id") or capability["bound_to"]["trigger_event_id"]
        anchor_index = index.get(anchor_id)
        if anchor_index is None:
            raise ContinuationError(f"anchor_event_id {anchor_id!r} is not an observed event")

        cursor = request.get("cursor")
        max_events = request["max_events"]
        max_bytes = request["max_bytes"]
        cap_events = min(max_events, capability["max_events_per_fetch"])
        cap_bytes = min(max_bytes, capability["max_bytes_per_fetch"])
        around_window_start: int | None = None
        around_window_end: int | None = None
        cursor_remaining_event_ids: list[str] | None = None

        if cursor:
            cursor_window = self._cursor_windows[handle_id].get(cursor)
            if cursor_window is None:
                raise ContinuationError(f"cursor {cursor!r} has no bound window metadata")
            if cursor_window["direction"] != direction:
                raise ContinuationError(
                    f"cursor {cursor!r} is bound to direction "
                    f"{cursor_window['direction']!r}, not {direction!r}"
                )
            if cursor_window["anchor_event_id"] != anchor_id:
                raise ContinuationError(
                    f"cursor {cursor!r} is bound to anchor_event_id "
                    f"{cursor_window['anchor_event_id']!r}, not {anchor_id!r}"
                )
            remaining_event_ids = list(cursor_window["remaining_event_ids"])
            missing_event_ids = [
                event_id for event_id in remaining_event_ids if event_id not in index
            ]
            if missing_event_ids:
                raise ContinuationError(
                    f"cursor {cursor!r} references events no longer retained: "
                    f"{missing_event_ids}"
                )
            # Resolve every direction's original remainder by identity against
            # the live deque. Numeric positions are not stable under bounded
            # retention; event IDs and the cursor's scan order are.
            candidate_indices = [index[event_id] for event_id in remaining_event_ids]
            if direction == "around":
                around_window_start = int(cursor_window["window_start"])
                around_window_end = int(cursor_window["window_end"])
        elif direction == "before":
            candidate_indices = list(range(anchor_index - 1, -1, -1))
        elif direction == "after":
            candidate_indices = list(range(anchor_index + 1, len(events)))
        else:  # around
            radius = max(1, cap_events // 2)
            around_window_start = max(0, anchor_index - radius)
            around_window_end = min(len(events), anchor_index + radius + 1)
            candidate_indices = list(range(around_window_start, around_window_end))
            # H020-A1-01 / T056: an ``around`` cursor is the next unserved
            # index inside its original fixed, anchor-bound window. The host
            # rejects an anchor swap and does not let a changed page cap widen
            # that already-minted window.

        page_events: list[dict] = []
        total_bytes = 0
        next_index = None
        truncated_by: list[str] = []
        for position, i in enumerate(candidate_indices):
            event = events[i]
            size = serialized_byte_size(event)
            event_cap_reached = len(page_events) >= cap_events
            byte_cap_exceeded = total_bytes + size > cap_bytes
            if event_cap_reached or byte_cap_exceeded:
                next_index = i
                # M020-A1-02 / T058: the next-index sentinel says only that
                # the page stopped. Preserve each actual stop cause instead of
                # attributing every truncation to the event cap.
                if event_cap_reached:
                    truncated_by.append("events")
                if byte_cap_exceeded:
                    truncated_by.append("bytes")
                remaining_indices = list(candidate_indices)[position:]
                cursor_remaining_event_ids = [events[j]["id"] for j in remaining_indices]
                break
            page_events.append(event)
            total_bytes += size
        if next_index is not None and not page_events:
            # A cursor at the same unserved index would repeat forever. Fail
            # closed instead: the caller must request a byte cap large enough
            # to admit at least one authoritative event.
            raise ContinuationError(
                f"max_bytes={cap_bytes} cannot admit the next event; refusing a non-progress cursor"
            )
        if direction in ("before", "after"):
            page_events_ordered = list(reversed(page_events)) if direction == "before" else page_events
            has_more_before = next_index is not None if direction == "before" else None
            has_more_after = next_index is not None if direction == "after" else None
        else:
            if around_window_start is None or around_window_end is None:
                raise ContinuationError("around cursor window was not initialized")
            page_events_ordered = page_events
            # L020-01: truthful side-specific coverage instead of two nulls.
            # Either side is incomplete when the fixed radius window ends
            # before the buffer's own edge, independent of any cap. On top
            # of that: the ascending scan can also cut off before it ever
            # reaches anchor_index (e.g. a tight byte cap admits only the
            # first one or two candidates) — that always leaves the anchor
            # itself and everything after it unserved too, so any cap
            # truncation within the window (``next_index is not None``)
            # always implies more-after. F1 CRITICAL (Phase 11): a cap that
            # truncates strictly before anchor_index additionally leaves a
            # genuine before-anchor event unserved, which the window-only
            # ``around_window_start > 0`` check alone missed.
            cap_truncated_before_anchor = next_index is not None and next_index < anchor_index
            has_more_before = around_window_start > 0 or cap_truncated_before_anchor
            has_more_after = next_index is not None or around_window_end < len(events)

        next_cursor = None
        if next_index is not None:
            # Direction-bound (H020-01): encoding ``direction`` into the
            # cursor lets ``check_binding_expiry`` reject a cursor replayed
            # under a different direction before any page is served.
            self._cursor_sequences[handle_id] += 1
            next_cursor = f"{handle_id}:{direction}:{self._cursor_sequences[handle_id]}"
            self._cursors[handle_id].add(next_cursor)
            capability.setdefault("cursors", [])
            if next_cursor not in capability["cursors"]:
                capability["cursors"].append(next_cursor)
            if cursor_remaining_event_ids is None:
                raise ContinuationError("cursor remaining-event metadata was not initialized")
            new_cursor_window: dict[str, Any] = {
                "anchor_event_id": anchor_id,
                "direction": direction,
                "remaining_event_ids": cursor_remaining_event_ids,
            }
            if direction == "around":
                if around_window_start is None or around_window_end is None:
                    raise ContinuationError("around cursor window was not initialized")
                new_cursor_window["window_start"] = around_window_start
                new_cursor_window["window_end"] = around_window_end
            self._cursor_windows[handle_id][next_cursor] = new_cursor_window

        actor_ids = {
            ref for event in page_events_ordered for ref in _actor_references({"self": None, "events": [event]})
        }
        actors = {actor_id: dict(self._provider._actors.get(actor_id, {})) for actor_id in actor_ids}

        page: dict[str, Any] = {
            "request_id": request["request_id"],
            "handle_id": handle_id,
            "room_id": self._provider.room_id,
            "continuity_scope_id": self._provider.continuity_scope_id,
            "direction": direction,
            "anchor_event_id": anchor_id,
            "actors": actors,
            "events": page_events_ordered,
            "coverage": {
                "has_more_before": has_more_before,
                "has_more_after": has_more_after,
                "has_gaps": False,
                "truncated_by": truncated_by,
                "continuity": self._provider.continuity,
                "has_restart_gap": False if self._provider.continuity != "unknown" else None,
                "max_events": cap_events,
                "max_bytes": cap_bytes,
            },
        }
        if self._provider.event_visibility:
            page["coverage"]["event_visibility"] = dict(self._provider.event_visibility)
        if next_cursor is not None:
            page["next_cursor"] = next_cursor
        page_errors = validate_context_continuation(page)
        if page_errors:
            raise ContinuationError(f"assembled page failed self-validation: {page_errors}")
        dedup_errors = check_id_uniqueness(page_events_ordered)
        if dedup_errors:
            raise ContinuationError(f"assembled page failed exact-event dedup: {dedup_errors}")
        return page
