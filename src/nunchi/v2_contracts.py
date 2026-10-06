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


# Why a moment is judged when no new message arrived (#94 step 6): ``pause``
# is a look again after the room went quiet (I-010A@3, I-010C@9);
# ``outcome`` is a turn for an approved action that finished after the
# participant's turn about it ended (I-010A@4, I-010C@10).
OCCASIONS = ("pause", "outcome")

# Messages that arrived while the participant was busy with its previous turn
# and got no turn of their own (#94 step 6; I-010A@6, I-010C@12): the judgment
# and the turn read them with the newest, newest first, as a person catching up
# does. At most this many, besides the newest.
UNATTENDED_MAX = 3


def _unattended(value: Any, doc: Mapping[str, Any], path: str) -> list[str]:
    """Messages by others in the supplied events, newest first, not the trigger."""

    ids = _string_list(value, path, unique=True)
    if not 1 <= len(ids) <= UNATTENDED_MAX:
        _fail(path, f"must list 1 to {UNATTENDED_MAX} messages")
    order = {event["id"]: index for index, event in enumerate(doc["events"])}
    own = doc["self"]["actor_id"]
    for event_id in ids:
        event = next((item for item in doc["events"] if item["id"] == event_id), None)
        if event is None or event["type"] != "message" or event["author_id"] == own:
            _fail(path, "must name supplied messages by others")
        if event_id == doc["trigger_event_id"]:
            _fail(path, "must not name the trigger")
    if [order[event_id] for event_id in ids] != sorted((order[event_id] for event_id in ids), reverse=True):
        _fail(path, "must be newest first")
    return ids

# The room's pace at the snapshot (#94 step 6; I-010A@2, I-010C@8); see
# ``nunchi.pace``. Counts and durations in whole seconds, never verdicts.
PACE_COUNTS = ("window_messages", "own_messages")
PACE_OPTIONAL = (
    "judged_seconds_ago",
    "quiet_before_seconds",
    "author_run_messages",
    "author_run_seconds",
    "own_last_seconds_ago",
)


def _pace(value: Any, path: str) -> None:
    doc = _closed(value, path, required=("now",) + PACE_COUNTS, optional=PACE_OPTIONAL)
    _nes(doc["now"], f"{path}.now")
    for name in PACE_COUNTS + PACE_OPTIONAL:
        if name in doc:
            item = doc[name]
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                _fail(f"{path}.{name}", "must be a non-negative integer")
    if doc["own_messages"] > doc["window_messages"]:
        _fail(f"{path}.own_messages", "cannot exceed window_messages")
    if "author_run_messages" in doc and doc["author_run_messages"] < 1:
        _fail(f"{path}.author_run_messages", "must count the judged message")


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
        optional=("continuation", "pace", "occasion", "memory", "unattended_event_ids"),
    )
    _nes(doc["request_id"], "request_id")
    _observation_fields(doc, require_schema=True)
    if "unattended_event_ids" in doc:
        _unattended(doc["unattended_event_ids"], doc, "request.unattended_event_ids")
    if "memory" in doc:
        # I-010A@5: the participant's memory, the same facts its turn gets.
        _memory(doc["memory"], "request.memory")
    if "pace" in doc:
        _pace(doc["pace"], "request.pace")
    if "occasion" in doc and doc["occasion"] not in OCCASIONS:
        _fail("request.occasion", "must be one of " + ", ".join(OCCASIONS))
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
        # Since I-010B@7: an outcome turn always reaches the participant.
        "outcome-turn",
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


# The reading attention gives the participant: a few short notes, each
# pointing to the messages it comes from.
READING_MAX_ITEMS = 4
READING_NOTE_MAX_CHARS = 400

# The typed answers behind every model judgment (#94, step 4): step 1 asks
# whether the judged message is conversation; step 2 asks what is happening
# and which kinds of response could fit. Since @6 (step 5) step 2 also asks
# whether the message asks someone for something and which earlier message
# it responds to, so the participant's memory can follow who asked what and
# what got answered.
ANSWER_MOVES = ("speak", "mhm", "wait", "stay_quiet")
ANSWER_ADDRESSEES = ("participant", "room", "someone_else", "nobody")
ANSWER_QUESTIONS = (
    "conversation",
    "addressee",
    "asks",
    "answered",
    "answered_by",
    "responds_to",
    "mid_thought",
    "adds_something",
    "move",
)
# Pointer answers are optional: no message, or none the model was shown.
ANSWER_POINTERS = ("answered_by", "responds_to")
# Asked only when the request lists unattended messages (@8, #94 step 6):
# which of them still calls for the participant.
UNATTENDED_POINTER = "calls_for_participant"
_ANSWER_YES_NO = ("conversation", "asks", "answered", "mid_thought", "adds_something")
_ANSWER_CHOICES = {"addressee": ANSWER_ADDRESSEES, "move": ANSWER_MOVES}


def _unit(value: Any, path: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or not 0 <= float(value) <= 1
    ):
        _fail(path, "must be finite within [0, 1]")


def _answers(
    value: Any,
    event_ids: set[str] | None,
    path: str,
) -> dict[str, Any]:
    checked = _closed(
        value,
        path,
        required=tuple(key for key in ANSWER_QUESTIONS if key not in ANSWER_POINTERS),
        optional=ANSWER_POINTERS + (UNATTENDED_POINTER,),
    )
    for key in _ANSWER_YES_NO:
        _unit(checked[key], f"{path}.{key}")
    for key, options in _ANSWER_CHOICES.items():
        choice = _closed(checked[key], f"{path}.{key}", required=options)
        for option in options:
            _unit(choice[option], f"{path}.{key}.{option}")
    for key in ANSWER_POINTERS + (UNATTENDED_POINTER,):
        if key in checked:
            _nes(checked[key], f"{path}.{key}")
            if event_ids is not None and checked[key] not in event_ids:
                _fail(f"{path}.{key}", "is an unknown event ID")
    return deepcopy(dict(checked))


def _advice(
    value: Any,
    event_ids: set[str] | None,
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    if len(value) > READING_MAX_ITEMS:
        _fail(path, f"has more than {READING_MAX_ITEMS} items")
    result = []
    for index, raw in enumerate(value):
        item = _closed(
            raw,
            f"{path}[{index}]",
            required=("note", "evidence_event_ids"),
        )
        _nes(item["note"], f"{path}[{index}].note")
        if len(item["note"]) > READING_NOTE_MAX_CHARS:
            _fail(f"{path}[{index}].note", f"is longer than {READING_NOTE_MAX_CHARS} characters")
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
                "answers",
            ),
            optional=("attention_advice", "ack"),
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
        if pair == ("ACK", "DEFER", "policy-defer") and routing["override_cause"] not in (
            "ack-disabled",
            "outcome-turn",
        ):
            _fail("decision.routing_audit.override_cause", "must be ack-disabled or outcome-turn for ACK policy widening")
        if pair == ("ACK", "DEFER", "capability-defer") and routing["override_cause"] != "ack-unsupported":
            _fail("decision.routing_audit.override_cause", "must be ack-unsupported for ACK capability widening")
        if pair == ("SUPPRESS", "DEFER", "policy-defer") and routing["override_cause"] not in (
            "suppression-disabled",
            "recoverability-unproven",
            "outcome-turn",
        ):
            _fail("decision.routing_audit.override_cause", "must name a suppression policy widening")
        if request is not None and (routing["override_cause"] == "outcome-turn") != (
            request.get("occasion") == "outcome" and pair[0] != pair[1]
        ):
            # Runtime-adapter-only: only an outcome turn widens for itself,
            # and it always widens what would not reach the participant.
            _fail("decision.routing_audit.override_cause", "outcome-turn must match an outcome request")
        _string_list(checked["reasons"], "decision.reasons")
        evidence = _string_list(
            checked["evidence_event_ids"],
            "decision.evidence_event_ids",
            unique=True,
        )
        if event_ids is not None and set(evidence) - event_ids:
            _fail("decision.evidence_event_ids", "contains an unknown event ID")
        _classifier(checked["classifier"])
        # The model's typed answers behind the judgment (@5).
        answers = _answers(checked["answers"], event_ids, "decision.answers")
        if (
            request is not None
            and UNATTENDED_POINTER in answers
            and answers[UNATTENDED_POINTER] not in request.get("unattended_event_ids", ())
        ):
            # Runtime-adapter-only: it names one of the request's unattended messages.
            _fail(f"decision.answers.{UNATTENDED_POINTER}", "must name an unattended message")
        if "attention_advice" in checked:
            # The model's reading of the room may accompany any judgment; it
            # reaches the participant only on a turn it takes (WAKE or DEFER).
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


# The participant's memory of the room (#94 step 5); see ``nunchi.memory``.
# Its own recent moves, where each kind names exactly the fields it carries,
# and the threads: asks and the messages that responded to them.
MEMORY_TEXT_MAX_CHARS = 280
THREAD_RESPONSES_MAX = 4
# Since @6 any own move may carry ``why``: the participant's own reason at the
# time, in its own words, never posted.
MOVE_REASON_MAX_CHARS = 200
# Since @11 a move about a message may carry that message's author and text
# (``about_author_id``, ``about_text``), together (#94 step 6).
_ABOUT = ("about_author_id", "about_text")
_OWN_MOVE_FIELDS = {
    "message": (("kind", "event_id", "text"), ("at", "why")),
    "reply": (("kind", "event_id", "about_event_id", "text"), ("at", "why") + _ABOUT),
    "reaction": (("kind", "event_id", "about_event_id", "reaction"), ("at", "why") + _ABOUT),
    "silence": (("kind", "about_event_id", "at"), ("why",) + _ABOUT),
    # Since @7: a privileged proposal and what became of it (#90).
    "proposal": (("kind", "proposal_id", "about_event_id", "capability", "status", "at"), _ABOUT),
}
PROPOSAL_STATUSES = (
    "awaiting_approval",
    "done",
    "failed",
    "unknown",
    "denied",
    "expired",
    "withdrawn",
    "cancelled",
)


def _memory_text(value: Any, path: str) -> None:
    if not isinstance(value, str):
        _fail(path, "must be a string")
    if len(value) > MEMORY_TEXT_MAX_CHARS:
        _fail(path, f"must be at most {MEMORY_TEXT_MAX_CHARS} characters")


def _thread(value: Any, path: str) -> None:
    thread = _closed(
        value,
        path,
        required=("event_id", "author_id", "text", "responses"),
        optional=("addressed_to", "at"),
    )
    for name in ("event_id", "author_id", "at"):
        if name in thread:
            _nes(thread[name], f"{path}.{name}")
    _memory_text(thread["text"], f"{path}.text")
    if "addressed_to" in thread and thread["addressed_to"] not in ANSWER_ADDRESSEES:
        _fail(f"{path}.addressed_to", "must be one of " + ", ".join(ANSWER_ADDRESSEES))
    responses = thread["responses"]
    if not isinstance(responses, list) or len(responses) > THREAD_RESPONSES_MAX:
        _fail(f"{path}.responses", f"must be an array of at most {THREAD_RESPONSES_MAX}")
    for index, response in enumerate(responses):
        item = _closed(response, f"{path}.responses[{index}]", required=("event_id", "author_id", "text"))
        _nes(item["event_id"], f"{path}.responses[{index}].event_id")
        _nes(item["author_id"], f"{path}.responses[{index}].author_id")
        _memory_text(item["text"], f"{path}.responses[{index}].text")


def _memory(value: Any, path: str) -> dict[str, Any]:
    doc = _closed(value, path, required=(), optional=("own_moves", "threads"))
    if not doc:
        _fail(path, "must carry own_moves or threads")
    for key in doc:
        if not isinstance(doc[key], list) or not doc[key]:
            _fail(f"{path}.{key}", "must be a non-empty array")
    for index, thread in enumerate(doc.get("threads", ())):
        _thread(thread, f"{path}.threads[{index}]")
    for index, move in enumerate(doc.get("own_moves", ())):
        item = f"{path}.own_moves[{index}]"
        kind = move.get("kind") if isinstance(move, Mapping) else None
        if kind not in _OWN_MOVE_FIELDS:
            _fail(f"{item}.kind", "must be message, reply, reaction, silence or proposal")
        required, optional = _OWN_MOVE_FIELDS[kind]
        _closed(move, item, required=required, optional=optional)
        if kind == "proposal" and move["status"] not in PROPOSAL_STATUSES:
            _fail(f"{item}.status", "must be one of " + ", ".join(PROPOSAL_STATUSES))
        for name in ("event_id", "about_event_id", "reaction", "at", "proposal_id", "capability"):
            if name in move:
                _nes(move[name], f"{item}.{name}")
        if "text" in move:
            _memory_text(move["text"], f"{item}.text")
        if ("about_author_id" in move) != ("about_text" in move):
            _fail(item, "about_author_id and about_text come together")
        if "about_author_id" in move:
            _nes(move["about_author_id"], f"{item}.about_author_id")
            _memory_text(move["about_text"], f"{item}.about_text")
        if "why" in move:
            _nes(move["why"], f"{item}.why")
            if len(move["why"]) > MOVE_REASON_MAX_CHARS:
                _fail(f"{item}.why", f"must be at most {MOVE_REASON_MAX_CHARS} characters")
    return doc


def shown_event_ids(wake: Mapping[str, Any]) -> set[str]:
    """The messages a turn has shown the participant before it looks around.

    Its events, and every message its memory points at: memory items come
    from the room's retained history, so a participant may reply to the
    request it remembers after that request has left the window (#94 step 6).
    """

    shown = {event["id"] for event in wake["events"]}
    memory = wake.get("memory") or {}
    for move in memory.get("own_moves", ()):
        shown.update(move[key] for key in ("event_id", "about_event_id") if key in move)
    for thread in memory.get("threads", ()):
        shown.add(thread["event_id"])
        shown.update(response["event_id"] for response in thread["responses"])
    return shown


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
        optional=("continuation", "memory", "pace", "occasion", "unattended_event_ids"),
    )
    if "pace" in doc:
        _pace(doc["pace"], "wake.pace")
    if "occasion" in doc and doc["occasion"] not in OCCASIONS:
        _fail("wake.occasion", "must be one of " + ", ".join(OCCASIONS))
    if "memory" in doc:
        # Memory points at messages that may have left the window; the
        # participant can look around them in the room.
        _memory(doc["memory"], "wake.memory")
    _nes(doc["request_id"], "wake.request_id")
    _observation_fields(doc, require_schema=False)
    if "unattended_event_ids" in doc:
        _unattended(doc["unattended_event_ids"], doc, "wake.unattended_event_ids")
    attention = _closed(
        doc["attention"],
        "wake.attention",
        required=("source",),
        optional=("advice", "evidence_event_ids", "judged_through_event_id"),
    )
    source = attention["source"]
    if source not in WAKE_SOURCES:
        _fail("wake.attention.source", "has an unsupported wake source")
    event_ids = {event["id"] for event in doc["events"]}
    if source in ("WAKE", "DEFER"):
        # A turn the participant takes after a model judgment carries that
        # judgment's reading of the room.
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
        if "judged_through_event_id" in attention:
            if "advice" not in attention:
                _fail("wake.attention.judged_through_event_id", "is allowed only with a reading")
            _nes(attention["judged_through_event_id"], "wake.attention.judged_through_event_id")
            if attention["judged_through_event_id"] not in event_ids:
                _fail("wake.attention.judged_through_event_id", "must name an event in the wake")
    elif {"advice", "evidence_event_ids", "judged_through_event_id"} & set(attention):
        _fail(
            "wake.attention",
            "ACK, error fallback, and bypass carry no reading",
        )
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
            if pair == ("ACK", "DEFER", "policy-defer") and routing["override_cause"] not in (
                "ack-disabled",
                "outcome-turn",
            ):
                _fail("receipt.body.routing_audit.override_cause", "must be ack-disabled or outcome-turn for ACK policy widening")
            if pair == ("ACK", "DEFER", "capability-defer") and routing["override_cause"] != "ack-unsupported":
                _fail("receipt.body.routing_audit.override_cause", "must be ack-unsupported for ACK capability widening")
            if pair == ("SUPPRESS", "DEFER", "policy-defer") and routing["override_cause"] not in (
                "suppression-disabled",
                "recoverability-unproven",
                "outcome-turn",
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
