"""Ephemeral live-conversation opportunity scheduling for Nunchi V2.

Events are observations, not response jobs.  For each exact participant/room
key this scheduler exposes at most one active attention-or-participant turn and
one replaceable newest pending anchor.  Completing active work promotes only
that newest anchor; the host must then request a fresh bounded observation, so
all intervening events are context rather than queued obligations.

The scheduler never examines message content, timestamps, mentions, replies,
apparent resolution, prior dispositions, or participant outcomes.  It has no
persistence API: constructing a new scheduler after restart begins with no
pending wake work, while the observation provider may still retain honest
backfill as context for future live events.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass


class SchedulingError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class ConversationKey:
    participant_id: str
    platform: str
    room_id: str


@dataclass(frozen=True)
class ConversationOpportunity:
    key: ConversationKey
    anchor_event_id: str
    generation: int


@dataclass
class _RoomState:
    generation: int = 0
    active: ConversationOpportunity | None = None
    pending_anchor_event_id: str | None = None


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise SchedulingError(f"{name} must be a non-empty opaque identifier")
    return value


class ConversationOpportunityScheduler:
    """Thread-safe one-active/one-newest-pending scheduler."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rooms: dict[ConversationKey, _RoomState] = {}

    @staticmethod
    def key(*, participant_id: str, platform: str, room_id: str) -> ConversationKey:
        return ConversationKey(
            participant_id=_identifier("participant_id", participant_id),
            platform=_identifier("platform", platform),
            room_id=_identifier("room_id", room_id),
        )

    @staticmethod
    def _new_opportunity(
        key: ConversationKey,
        state: _RoomState,
        anchor_event_id: str,
    ) -> ConversationOpportunity:
        state.generation += 1
        opportunity = ConversationOpportunity(
            key=key,
            anchor_event_id=anchor_event_id,
            generation=state.generation,
        )
        state.active = opportunity
        return opportunity

    def observe(
        self,
        *,
        participant_id: str,
        platform: str,
        room_id: str,
        anchor_event_id: str,
    ) -> ConversationOpportunity | None:
        """Accept one already-canonical live event.

        Returns an opportunity only when the room was idle.  While work is
        active, the newest anchor replaces the previous pending anchor and no
        additional job is created.
        """
        key = self.key(
            participant_id=participant_id,
            platform=platform,
            room_id=room_id,
        )
        anchor = _identifier("anchor_event_id", anchor_event_id)
        with self._lock:
            state = self._rooms.setdefault(key, _RoomState())
            if state.active is None:
                return self._new_opportunity(key, state, anchor)
            state.pending_anchor_event_id = anchor
            return None

    def complete(
        self,
        opportunity: ConversationOpportunity,
    ) -> ConversationOpportunity | None:
        """Complete exact active work and promote at most one fresh anchor."""
        if not isinstance(opportunity, ConversationOpportunity):
            raise SchedulingError("completion requires a scheduler-issued opportunity")
        with self._lock:
            state = self._rooms.get(opportunity.key)
            if state is None or state.active != opportunity:
                raise SchedulingError("opportunity is not the exact active generation")
            state.active = None
            pending = state.pending_anchor_event_id
            state.pending_anchor_event_id = None
            if pending is not None:
                return self._new_opportunity(opportunity.key, state, pending)
            del self._rooms[opportunity.key]
            return None

    def snapshot(self) -> tuple[dict[str, object], ...]:
        """Return a non-authoritative operator/debug copy of ephemeral state."""
        with self._lock:
            rows = []
            for key in sorted(self._rooms):
                state = self._rooms[key]
                rows.append(
                    {
                        "participant_id": key.participant_id,
                        "platform": key.platform,
                        "room_id": key.room_id,
                        "active_anchor_event_id": (
                            state.active.anchor_event_id if state.active else None
                        ),
                        "active_generation": (
                            state.active.generation if state.active else None
                        ),
                        "pending_anchor_event_id": state.pending_anchor_event_id,
                    }
                )
            return tuple(copy.deepcopy(rows))


__all__ = [
    "ConversationKey",
    "ConversationOpportunity",
    "ConversationOpportunityScheduler",
    "SchedulingError",
]
