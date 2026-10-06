"""The room's pace at one moment (#94, plan step 6).

People notice the pace of a conversation: a burst of messages from someone
mid-thought, a pause, a room that has been quiet for hours, and how much
they themselves have said lately (``docs/behavior.md``). Timestamps alone
leave that to arithmetic a model does poorly, so the snapshot carries the
pace as a few plain facts, computed once when it is built:

- ``now``: the time the snapshot was built;
- ``judged_seconds_ago``: how long ago the judged event happened;
- ``quiet_before_seconds``: how long the room was quiet before it, since the
  previous message by anyone;
- ``author_run_messages`` and ``author_run_seconds``: the judged message's
  author's unbroken run of messages ending at it, and how long that run took;
- ``window_messages``, ``own_messages`` and ``own_last_seconds_ago``: how
  many messages the window holds, how many of them are the participant's
  own, and how long ago it last posted.

These are facts, never verdicts: nothing here says what the pace means or
what to do about it. A fact that needs a timestamp the platform did not
give is left out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


def _at(event: Mapping[str, Any]) -> datetime | None:
    raw = event.get("timestamp")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _seconds(later: datetime, earlier: datetime) -> int:
    return max(0, int((later - earlier).total_seconds()))


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def pace_facts(
    events: Sequence[Mapping[str, Any]],
    *,
    trigger_event_id: str,
    actor_id: str,
    now: datetime,
) -> dict[str, Any]:
    """The pace facts for one snapshot; ``events`` are its events in order."""

    messages = [event for event in events if event.get("type") == "message"]
    facts: dict[str, Any] = {
        "now": iso(now),
        "window_messages": len(messages),
        "own_messages": sum(1 for event in messages if event.get("author_id") == actor_id),
    }
    position = next(
        (index for index, event in enumerate(events) if event.get("id") == trigger_event_id),
        None,
    )
    if position is None:
        return facts
    trigger = events[position]
    judged_at = _at(trigger)
    if judged_at is not None:
        facts["judged_seconds_ago"] = _seconds(now, judged_at)
    before = [event for event in events[:position] if event.get("type") == "message"]
    timed_before = [event for event in before if _at(event) is not None]
    if judged_at is not None and timed_before:
        facts["quiet_before_seconds"] = _seconds(judged_at, _at(timed_before[-1]))
    if trigger.get("type") == "message":
        run = [trigger]
        for event in reversed(before):
            if event.get("author_id") != trigger.get("author_id"):
                break
            run.append(event)
        facts["author_run_messages"] = len(run)
        first_at = _at(run[-1])
        if len(run) > 1 and judged_at is not None and first_at is not None:
            facts["author_run_seconds"] = _seconds(judged_at, first_at)
    own_times = [
        _at(event) for event in messages if event.get("author_id") == actor_id and _at(event) is not None
    ]
    if own_times:
        facts["own_last_seconds_ago"] = _seconds(now, max(own_times))
    return facts
