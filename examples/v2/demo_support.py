"""Small, offline harness shared by the executable V2 examples.

The harness replaces only the remote model transport with an explicit fixture.
It still uses the ordinary V2 policy loader, observation provider, scheduler,
attention core, participant host, receipts, and action sink.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from nunchi.adapters.v2 import GenericEventSourceV2
from nunchi.observation import ObservationProvider
from nunchi.policy import load_operator_policy
from nunchi.runtime import LiveRoomRuntime


PARTICIPANT_ID = "vigil"
PARTICIPANT_ACTOR_ID = "reference:user:vigil"
ROOM_ID = "room-1"
CONTINUITY_SCOPE_ID = "reference:room:1"
ACTORS = {
    "reference:user:zoe": {"display_name": "Zoe", "kind": "human"},
    "reference:user:sol": {"display_name": "Sol", "kind": "bot"},
    PARTICIPANT_ACTOR_ID: {"display_name": "Vigil", "kind": "bot"},
}


@dataclass
class DemoHarness:
    runtime: LiveRoomRuntime
    source: GenericEventSourceV2
    receipts: list[dict[str, Any]]
    actions: list[dict[str, Any]]


def _write_policy(root: Path, *, preattention_enabled: bool) -> Path:
    document = {
        "schema_version": 2,
        "source": "operator:offline-v2-example",
        "attention": {
            "participant_id": PARTICIPANT_ID,
            "preattention_enabled": preattention_enabled,
            "social_suppression_enabled": True,
            "attention_max_events": 50,
            "attention_max_bytes": 65536,
            "participant_max_events": 50,
            "participant_max_bytes": 65536,
            "fetch_max_events": 20,
            "fetch_max_bytes": 32768,
            "error_action": "WAKE",
        },
        "recoverability": {
            "participant_id": PARTICIPANT_ID,
            "continuity_scope_id": CONTINUITY_SCOPE_ID,
            "eligible": True,
        },
        "classifier": {
            "provider": "openai-compatible",
            "endpoint": "https://offline.example.invalid/v1/chat/completions",
            "model": "participant-shaped-fixture",
            "timeout_seconds": 5,
            "max_retries": 0,
        },
        "authorization": {
            "decision_ttl_seconds": 30,
            "approval_ttl_seconds": 300,
            "grants": [],
        },
        "receipt_sink": {
            "type": "exclusive-json-file",
            "directory": str(root),
            "source": "operator:offline-example-receipts",
        },
    }
    path = root / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    path.chmod(0o600)
    return path


def build_harness(
    root: Path,
    *,
    classifier: Callable[[dict[str, Any], Any], Any],
    participant: Callable[[Any], Any],
    preattention_enabled: bool = True,
) -> DemoHarness:
    policy_path = _write_policy(
        root,
        preattention_enabled=preattention_enabled,
    )
    policy = load_operator_policy(policy_path)
    receipts: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    provider = ObservationProvider(
        participant_id=PARTICIPANT_ID,
        actor_id=PARTICIPANT_ACTOR_ID,
        names=["Vigil"],
        role="participant",
        description="offline V2 example participant",
        platform="reference",
        room_id=ROOM_ID,
        room_kind="group",
        continuity_scope_id=CONTINUITY_SCOPE_ID,
        continuity="restart-safe",
        has_restart_gap=False,
        event_visibility={
            "message": "history-and-live",
            "reaction": "history-and-live",
            "membership": "history-and-live",
        },
    )
    return DemoHarness(
        runtime=LiveRoomRuntime(
            observation=provider,
            policy_loader=lambda: policy,
            receipt_sink=receipts.append,
            participant=participant,
            action_sink=actions.append,
            classifier_transport=classifier,
        ),
        source=GenericEventSourceV2(platform="reference", room_id=ROOM_ID),
        receipts=receipts,
        actions=actions,
    )


def message_delivery(
    source: GenericEventSourceV2,
    event_id: str,
    author_id: str,
    text: str,
    *,
    mentioned_actor_ids: list[str] | None = None,
    authorized: bool = True,
) -> dict[str, Any]:
    return source.native_input(
        delivery_id=f"reference:delivery:{event_id}",
        authorized=authorized,
        routing_room_id=ROOM_ID,
        event={
            "id": f"reference:event:{event_id}",
            "type": "message",
            "author_id": author_id,
            "text": text,
            "mentioned_actor_ids": list(mentioned_actor_ids or []),
            "mentions_room": False,
        },
        actors=ACTORS,
    )


__all__ = [
    "ACTORS",
    "PARTICIPANT_ACTOR_ID",
    "DemoHarness",
    "build_harness",
    "message_delivery",
]
