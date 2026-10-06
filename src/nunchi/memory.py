"""One participant's memory of its own part in a room (#94, plan step 5).

People remember what they said in a conversation, what they nodded at, and
where they kept quiet. The participant's turn carries the same: its own
recent moves in this room, each pointing at the message it was about.

The visible moves come from the room's retained history: the participant's
own messages, replies and reactions, which the host observes like anyone
else's. A silence leaves no trace in the room, so the participant host
records it here when a turn ends without an action.

These are facts with pointers, never verdicts. Nothing here says what the
participant should do next, nothing obliges a reply, and old items fade: the
memory keeps the newest visible moves and the latest few silences within a
day, and a silence whose message has left the retained history is gone with
it (``docs/behavior.md``). Silences have their own small allowance, because
most quiet turns end in one: what the participant said should not be pushed
out by every message it let pass.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
import threading
from typing import Any


OWN_MOVE_KINDS = ("message", "reply", "reaction", "silence")
MEMORY_TEXT_MAX_CHARS = 280
DEFAULT_OWN_MOVES = 8
DEFAULT_SILENCES = 3
DEFAULT_MAX_AGE_SECONDS = 86_400


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= MEMORY_TEXT_MAX_CHARS:
        return text
    return text[: MEMORY_TEXT_MAX_CHARS - 1].rstrip() + "…"


def _own_move(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """The move one of the participant's own events shows, or None."""

    if event.get("type") == "message":
        target = event.get("reply_to_event_id")
        move: dict[str, Any] = {"kind": "reply" if target else "message", "event_id": event["id"]}
        if target:
            move["about_event_id"] = target
        move["text"] = _excerpt(str(event.get("text", "")))
    elif event.get("type") == "reaction" and event.get("operation") == "add":
        move = {
            "kind": "reaction",
            "event_id": event["id"],
            "about_event_id": event["target_event_id"],
            "reaction": event["reaction"],
        }
    else:
        return None
    if isinstance(event.get("timestamp"), str):
        move["at"] = event["timestamp"]
    return move


class ConversationMemory:
    """The participant's own recent moves in one room, newest last."""

    def __init__(
        self,
        *,
        own_moves: int = DEFAULT_OWN_MOVES,
        silences: int = DEFAULT_SILENCES,
        max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        for name, value in (
            ("own_moves", own_moves),
            ("silences", silences),
            ("max_age_seconds", max_age_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"memory {name} must be a positive integer")
        self.own_moves_limit = own_moves
        self.max_age = timedelta(seconds=max_age_seconds)
        self._silences: deque[dict[str, Any]] = deque(maxlen=silences)
        self._lock = threading.Lock()

    def record_silence(self, *, about_event_id: str, at: datetime | None = None) -> None:
        """A turn about this message ended without a visible move."""

        if not isinstance(about_event_id, str) or not about_event_id:
            raise ValueError("a silence must name the message it was about")
        moment = at or datetime.now(timezone.utc)
        with self._lock:
            self._silences.append(
                {"kind": "silence", "about_event_id": about_event_id, "at": _timestamp(moment)}
            )

    def restart(self) -> None:
        """Forget what only the host knew; the room's history keeps the rest."""

        with self._lock:
            self._silences.clear()

    def own_moves(
        self,
        events: Iterable[Mapping[str, Any]],
        *,
        actor_id: str,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """The newest own moves, in the order they happened.

        ``events`` is the room's retained history in arrival order. The
        newest visible moves are kept, and the latest silences beside them;
        a silence is placed just after the message it was about, and is
        dropped once that message is no longer retained.
        """

        now = now or datetime.now(timezone.utc)

        def fresh(move: Mapping[str, Any]) -> bool:
            when = _parse(move.get("at"))
            return when is None or now - when <= self.max_age

        visible: list[tuple[float, dict[str, Any]]] = []
        position: dict[str, int] = {}
        for index, event in enumerate(events):
            position[event["id"]] = index
            if event.get("author_id") == actor_id:
                move = _own_move(event)
                if move is not None and fresh(move):
                    visible.append((float(index), move))
        with self._lock:
            silences = [dict(item) for item in self._silences]
        quiet = [
            (position[silence["about_event_id"]] + 0.5 + order / 1000, silence)
            for order, silence in enumerate(silences)
            if silence["about_event_id"] in position and fresh(silence)
        ]
        ordered = sorted(visible[-self.own_moves_limit :] + quiet, key=lambda item: item[0])
        return [move for _, move in ordered]

    def facts(self, observation: Any, *, now: datetime | None = None) -> dict[str, Any] | None:
        """The memory block for a participant's turn, or None when it is empty."""

        moves = self.own_moves(
            observation.retained_events(),
            actor_id=observation.binding.actor_id,
            now=now,
        )
        return {"own_moves": moves} if moves else None
