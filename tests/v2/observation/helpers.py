"""Reusable observation fixture, assertion, and evidence-only proxy helpers.

Shared by every test/eval module under ``tests/v2/observation/`` and
``evals/v2/observation/`` so no test module invents its own room-fixture
shape or its own token-size proxy math (T001).
"""

from __future__ import annotations

from typing import Any

from nunchi.observation import (
    ContinuationProvider,
    ObservationProvider,
    estimate_tokens,
    serialized_byte_size,
)

FIXTURE_PLATFORM = "discord"
FIXTURE_ROOM_ID = "42"
FIXTURE_CONTINUITY_SCOPE_ID = "discord:room:42#2026-07"

FIXTURE_ACTORS = {
    "discord:1001": {"display_name": "Zoe", "kind": "human"},
    "discord:2002": {"display_name": "Vigil", "kind": "bot"},
    "discord:3003": {"display_name": "Sol", "kind": "bot"},
}

FIXTURE_SELF_ACTOR_ID = "discord:9001"


def make_provider(**overrides: Any) -> ObservationProvider:
    """One shared-room provider fixture: exact self bound, room facts set."""
    kwargs = dict(
        participant_id="vigil",
        actor_id=FIXTURE_SELF_ACTOR_ID,
        names=["Vigil", "Aether"],
        role="developer",
        description="resident coding agent",
        platform=FIXTURE_PLATFORM,
        room_id=FIXTURE_ROOM_ID,
        continuity_scope_id=FIXTURE_CONTINUITY_SCOPE_ID,
    )
    kwargs.update(overrides)
    return ObservationProvider(**kwargs)


def make_message(
    event_id: str,
    author_id: str,
    text: str,
    *,
    timestamp: str | None = None,
    reply_to_event_id: str | None = None,
    thread_root_event_id: str | None = None,
    mentioned_actor_ids: list[str] | None = None,
    mentions_room: bool = False,
) -> dict:
    event: dict[str, Any] = {
        "id": event_id,
        "type": "message",
        "author_id": author_id,
        "text": text,
        "mentioned_actor_ids": list(mentioned_actor_ids or []),
        "mentions_room": mentions_room,
    }
    if timestamp is not None:
        event["timestamp"] = timestamp
    if reply_to_event_id is not None:
        event["reply_to_event_id"] = reply_to_event_id
    if thread_root_event_id is not None:
        event["thread_root_event_id"] = thread_root_event_id
    return event


def make_reaction(
    event_id: str, author_id: str, target_event_id: str, reaction: str, *, operation: str = "add",
    timestamp: str | None = None,
) -> dict:
    event: dict[str, Any] = {
        "id": event_id,
        "type": "reaction",
        "author_id": author_id,
        "target_event_id": target_event_id,
        "reaction": reaction,
        "operation": operation,
    }
    if timestamp is not None:
        event["timestamp"] = timestamp
    return event


def make_membership(
    event_id: str, subject_actor_id: str, change: str, *, scope_kind: str = "room", scope_id: str = FIXTURE_ROOM_ID,
    caused_by_actor_id: str | None = None, timestamp: str | None = None,
) -> dict:
    event: dict[str, Any] = {
        "id": event_id,
        "type": "membership",
        "scope": {"kind": scope_kind, "id": scope_id},
        "subject_actor_id": subject_actor_id,
        "change": change,
    }
    if caused_by_actor_id is not None:
        event["caused_by_actor_id"] = caused_by_actor_id
    if timestamp is not None:
        event["timestamp"] = timestamp
    return event


def candidate(event: dict, *, actors: dict | None = None, delivery_id: str | None = None) -> dict:
    """One authorized candidate-event native input (transport-attested)."""
    return {
        "delivery_id": delivery_id or f"delivery:{event['id']}",
        "disposition": "candidate-event",
        "authorized": True,
        "event": event,
        "actors": actors or {},
    }


def unroutable(delivery_id: str, reason: str) -> dict:
    return {"delivery_id": delivery_id, "disposition": "unroutable", "reason": reason}


def ingest_all(provider: ObservationProvider, native_inputs: list[dict]) -> list[str]:
    return [provider.ingest(item) for item in native_inputs]


def seed_room(provider: ObservationProvider, events: list[dict]) -> list[str]:
    """Ingest a list of fully-authored events with the shared actor fixture."""
    return ingest_all(provider, [candidate(event, actors=FIXTURE_ACTORS) for event in events])


def scene_evidence_row(
    *,
    scene_id: str,
    case_id: str,
    request: dict | None = None,
    receipt: dict | None = None,
    result: str,
    detail: str = "",
) -> dict:
    """One canonical aggregate evidence row (mandatory ``scene_id``, T012/T018/T019)."""
    row: dict[str, Any] = {"scene_id": scene_id, "case_id": case_id, "result": result}
    if request is not None:
        row["request_id"] = request.get("request_id")
        row["event_count"] = len(request.get("events", []))
        row["serialized_bytes"] = serialized_byte_size(request)
        row["token_proxy"] = estimate_tokens(row["serialized_bytes"])
    if receipt is not None:
        row["receipt_stage"] = receipt.get("stage")
    if detail:
        row["detail"] = detail
    return row


__all__ = [
    "FIXTURE_PLATFORM",
    "FIXTURE_ROOM_ID",
    "FIXTURE_CONTINUITY_SCOPE_ID",
    "FIXTURE_ACTORS",
    "FIXTURE_SELF_ACTOR_ID",
    "make_provider",
    "make_message",
    "make_reaction",
    "make_membership",
    "candidate",
    "unroutable",
    "ingest_all",
    "seed_room",
    "scene_evidence_row",
    "ContinuationProvider",
]
