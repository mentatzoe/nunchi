"""One participant's memory of a room (#94, plan step 5).

People remember what they said in a conversation, what they nodded at, and
where they kept quiet. They also remember who asked what, and who answered.
The participant's turn carries the same, in two parts.

Its own moves: its recent messages, replies and reactions, each pointing at
the message it was about, and where it stayed quiet. The visible moves come
from the room's retained history, which the host observes like anyone
else's. A silence leaves no trace in the room, so the participant host
records it here when a turn ends without an action. Its privileged proposals
come from the host that authorizes them, with what became of each: awaiting
approval, done, denied, expired, withdrawn (#90). A move may carry the
participant's own reason at the time, in its own words (``why``): a person
remembers that they held back because someone else was asked, not only that
they held back. The host keeps the reason it was given; a visible move gets
it when the room shows the move as it was sent.

Threads: recent messages that asked someone for something, and the
participant's own messages that others responded to, each with the messages
that responded. Whether a message asks, and what it responds to, are the
attention model's typed answers about it; a platform reply counts as a
response too. Each judgment is kept here as it is made.

These are facts with pointers, never verdicts. Nothing here says what the
participant should do next, nothing obliges a reply, and old items fade: the
memory keeps the newest items within a day, and an item whose message has
left the retained history is gone with it (``docs/behavior.md``). Silences
have their own small allowance, because most quiet turns end in one: what
the participant said should not be pushed out by every message it let pass.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
import threading
from typing import Any

from .v2_contracts import (
    ANSWER_ADDRESSEES,
    MEMORY_TEXT_MAX_CHARS,
    MOVE_REASON_MAX_CHARS,
    THREAD_RESPONSES_MAX,
)


OWN_MOVE_KINDS = ("message", "reply", "reaction", "silence", "proposal")
DEFAULT_OWN_MOVES = 8
DEFAULT_SILENCES = 3
DEFAULT_PROPOSALS = 3
DEFAULT_THREADS = 6
DEFAULT_JUDGMENTS = 64
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


def _excerpt(text: str, limit: int = MEMORY_TEXT_MAX_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def move_reason(value: Any) -> str | None:
    """A participant's stated reason, shortened, or None when it gave none."""

    if not isinstance(value, str) or not value.strip():
        return None
    return _excerpt(value, MOVE_REASON_MAX_CHARS)


def _move_key(move: Mapping[str, Any]) -> tuple[Any, ...] | None:
    """What identifies a visible move: its kind, target, and words."""

    kind = move.get("kind")
    if kind in ("message", "reply"):
        return (kind, move.get("about_event_id"), _excerpt(str(move.get("text", ""))))
    if kind == "reaction":
        return (kind, move.get("about_event_id"), move.get("reaction"))
    return None


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
    """The participant's memory of one room: its own moves and the threads."""

    def __init__(
        self,
        *,
        own_moves: int = DEFAULT_OWN_MOVES,
        silences: int = DEFAULT_SILENCES,
        threads: int = DEFAULT_THREADS,
        judgments: int = DEFAULT_JUDGMENTS,
        max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        for name, value in (
            ("own_moves", own_moves),
            ("silences", silences),
            ("threads", threads),
            ("judgments", judgments),
            ("max_age_seconds", max_age_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"memory {name} must be a positive integer")
        self.own_moves_limit = own_moves
        self.threads_limit = threads
        self.judgments_limit = judgments
        self.max_age = timedelta(seconds=max_age_seconds)
        self._silences: deque[dict[str, Any]] = deque(maxlen=silences)
        self._reasons: deque[tuple[tuple[Any, ...], str]] = deque(maxlen=own_moves * 2)
        self._judgments: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def record_silence(
        self,
        *,
        about_event_id: str,
        at: datetime | None = None,
        why: Any = None,
    ) -> None:
        """A turn about this message ended without a visible move."""

        if not isinstance(about_event_id, str) or not about_event_id:
            raise ValueError("a silence must name the message it was about")
        moment = at or datetime.now(timezone.utc)
        silence = {"kind": "silence", "about_event_id": about_event_id, "at": _timestamp(moment)}
        reason = move_reason(why)
        if reason:
            silence["why"] = reason
        with self._lock:
            self._silences.append(silence)

    def record_reason(self, action: Mapping[str, Any], why: Any) -> None:
        """Keep the reason the participant gave for a visible move it sent.

        ``action`` is the core action (message, reply or reaction). The reason
        joins the move once the room shows it with the same words; a move the
        room never shows keeps its reason to itself.
        """

        reason = move_reason(why)
        kind = action.get("kind")
        if reason is None or kind not in ("message", "reply", "reaction"):
            return
        if kind == "reaction" and action.get("operation") != "add":
            return
        move = {
            "kind": kind,
            "about_event_id": action.get("target_event_id"),
            "text": action.get("text", ""),
            "reaction": action.get("reaction"),
        }
        with self._lock:
            self._reasons.append((_move_key(move), reason))

    def record_judgment(
        self,
        *,
        event_id: str,
        answers: Mapping[str, Any],
    ) -> None:
        """Keep what the attention model found about one message.

        Only the facts threads need: whether it is conversation and asks
        someone for something, whom it addresses, and the messages it
        responds to or that answered it. A later judgment of the same
        message replaces the earlier one.
        """

        if not isinstance(event_id, str) or not event_id:
            raise ValueError("a judgment must name its message")
        addressee = answers["addressee"]
        judged: dict[str, Any] = {
            "event_id": event_id,
            "conversation": float(answers["conversation"]),
            "asks": float(answers["asks"]),
            "addressed_to": max(
                ANSWER_ADDRESSEES,
                key=lambda key: (addressee[key], -ANSWER_ADDRESSEES.index(key)),
            ),
        }
        for key in ("responds_to", "answered_by"):
            if answers.get(key):
                judged[key] = answers[key]
        with self._lock:
            self._judgments.pop(event_id, None)
            self._judgments[event_id] = judged
            while len(self._judgments) > self.judgments_limit:
                self._judgments.popitem(last=False)

    def restart(self) -> None:
        """Forget what only the host knew; the room's history keeps the rest."""

        with self._lock:
            self._silences.clear()
            self._reasons.clear()
            self._judgments.clear()

    def own_moves(
        self,
        events: Iterable[Mapping[str, Any]],
        *,
        actor_id: str,
        now: datetime | None = None,
        proposals: Iterable[Mapping[str, Any]] = (),
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
            reasons = list(self._reasons)
        # Each reason joins the newest move it matches, once.
        for _, move in reversed(visible):
            key = _move_key(move)
            for index in range(len(reasons) - 1, -1, -1):
                if reasons[index][0] == key:
                    move["why"] = reasons.pop(index)[1]
                    break
        quiet = [
            (position[silence["about_event_id"]] + 0.5 + order / 1000, silence)
            for order, silence in enumerate(silences)
            if silence["about_event_id"] in position and fresh(silence)
        ]
        proposed = [
            (
                position[proposal["about_event_id"]] + 0.5 + order / 1000,
                {
                    "kind": "proposal",
                    "proposal_id": proposal["proposal_id"],
                    "about_event_id": proposal["about_event_id"],
                    "capability": proposal["capability"],
                    "status": proposal["status"],
                    "at": proposal["at"],
                },
            )
            for order, proposal in enumerate(list(proposals)[-DEFAULT_PROPOSALS:])
            if proposal.get("about_event_id") in position and fresh(proposal)
        ]
        ordered = sorted(
            visible[-self.own_moves_limit :] + quiet + proposed, key=lambda item: item[0]
        )
        return [move for _, move in ordered]

    def threads(
        self,
        events: Iterable[Mapping[str, Any]],
        *,
        actor_id: str,
        now: datetime | None = None,
        exclude_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """The newest threads, in the order they started.

        A thread starts at a message by someone else that the attention
        model judged to ask for something, or at one of the participant's own
        messages that someone responded to. Its responses are later messages
        by others that reply to it on the platform, that the model judged to
        respond to it, or that the model named as having answered it, each
        with what it said: a response is not always an answer, and a promise
        is not the thing done. ``exclude_event_id`` is the message the turn
        is about: its own reading already describes it, so it neither starts
        a thread nor appears as a response.
        """

        now = now or datetime.now(timezone.utc)
        events = [event for event in events if event.get("type") == "message"]
        position = {event["id"]: index for index, event in enumerate(events)}
        with self._lock:
            judgments = {key: dict(value) for key, value in self._judgments.items()}

        responses: dict[str, set[str]] = {}

        def link(head: Any, response: str) -> None:
            if head in position and position[head] < position[response]:
                if events[position[head]]["author_id"] != events[position[response]]["author_id"]:
                    responses.setdefault(head, set()).add(response)

        for event in events:
            if event["id"] == exclude_event_id:
                continue
            if event.get("reply_to_event_id"):
                link(event["reply_to_event_id"], event["id"])
            judged = judgments.get(event["id"])
            if judged and "responds_to" in judged:
                link(judged["responds_to"], event["id"])
        for judged in judgments.values():
            if judged.get("answered_by") in position and judged["answered_by"] != exclude_event_id:
                link(judged["event_id"], judged["answered_by"])

        threads = []
        for event in events:
            if event["id"] == exclude_event_id:
                continue
            judged = judgments.get(event["id"])
            own = event.get("author_id") == actor_id
            if own:
                if event["id"] not in responses:
                    continue
            elif not judged or judged["asks"] < 0.5 or judged["conversation"] < 0.5:
                continue
            when = _parse(event.get("timestamp"))
            if when is not None and now - when > self.max_age:
                continue
            thread: dict[str, Any] = {
                "event_id": event["id"],
                "author_id": event["author_id"],
                "text": _excerpt(str(event.get("text", ""))),
            }
            if not own:
                thread["addressed_to"] = judged["addressed_to"]
            if isinstance(event.get("timestamp"), str):
                thread["at"] = event["timestamp"]
            # The first responses: who answered first is what a person
            # remembers; later ones are in the room.
            ordered = sorted(responses.get(event["id"], ()), key=position.__getitem__)
            thread["responses"] = [
                {
                    "event_id": response,
                    "author_id": events[position[response]]["author_id"],
                    "text": _excerpt(str(events[position[response]].get("text", ""))),
                }
                for response in ordered[:THREAD_RESPONSES_MAX]
            ]
            threads.append(thread)
        return threads[-self.threads_limit :]

    def facts(
        self,
        observation: Any,
        *,
        now: datetime | None = None,
        current_event_id: str | None = None,
        proposals: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any] | None:
        """The memory block for a participant's turn, or None when it is empty."""

        events = list(observation.retained_events())
        actor_id = observation.binding.actor_id
        facts: dict[str, Any] = {}
        moves = self.own_moves(events, actor_id=actor_id, now=now, proposals=proposals)
        if moves:
            facts["own_moves"] = moves
        threads = self.threads(events, actor_id=actor_id, now=now, exclude_event_id=current_event_id)
        if threads:
            facts["threads"] = threads
        return facts or None
