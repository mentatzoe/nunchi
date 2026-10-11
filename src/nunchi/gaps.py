"""A continuity gap, said in one plain sentence (Zoe, 2026-10-10).

A gap is a point in the room's timeline where Nunchi may have missed
messages: a restart, a lost connection, a failed delivery. It is not a
lifetime flag. When what an agent reads (its window, or a page it asks for)
reaches or crosses a gap it has not been told about, the reading says so
once, in these words, and the same words reach attention's judgment. After
the agent has taken a turn whose reading included the gap, it is no longer
news (`ObservationProvider.gaps_told`).

The words are the library's, so every harness gets the same sentence. Times
are the room's own: UTC, as the events' timestamps and the pace are, with
the date only when the gap is not from the day the reading was made.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


def moment_of(text: Any) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _said(moment: datetime, today: datetime | None) -> str:
    """A gap's time as the reading says it: the clock in UTC, with the date when it is not today's."""

    clock = moment.strftime("%H:%M UTC")
    if today is not None and moment.date() == today.date():
        return clock
    return f"{moment.date().isoformat()} {clock}"


def gap_sentence(times: Sequence[str], now: str | None = None) -> str:
    """The sentence for gaps at ``times`` (ISO, UTC), or "" when there are none.

    ``now`` is the reading's own time; a gap from another day also gets its
    date, and so does every gap when ``now`` is not known. The sentence names
    minutes, so gaps in one minute are said once.
    """

    moments = sorted({moment for moment in map(moment_of, times) if moment is not None})
    if not moments:
        return ""
    today = moment_of(now)
    before = [f"before {said}" for said in dict.fromkeys(_said(moment, today) for moment in moments)]
    where = before[0] if len(before) == 1 else ", ".join(before[:-1]) + " and " + before[-1]
    return f"Messages may be missing {where}; read the history if it matters."


def not_listening_note(times: Sequence[str], now: str | None = None) -> str:
    """What a page of older messages says when it ends where Nunchi began to listen.

    A gap before everything Nunchi holds is not messages to go and read in its
    history: there is none. The page says so, with the time, in the same
    clock as the sentence. "" when ``times`` holds no time.
    """

    moments = [moment for moment in map(moment_of, times) if moment is not None]
    if not moments:
        return ""
    return f"Nunchi has no older messages: it was not listening before {_said(max(moments), moment_of(now))}."


def gap_times(coverage: Any) -> list[str]:
    """The times of the gaps a coverage document carries (none when it has none)."""

    gaps = coverage.get("gaps") if isinstance(coverage, Mapping) else None
    if not isinstance(gaps, list):
        return []
    return [gap["at"] for gap in gaps if isinstance(gap, Mapping) and isinstance(gap.get("at"), str)]


def gap_sentence_in(document: Any) -> str:
    """The sentence for the gaps in an attention request, its projection or a wake.

    It reads the document's ``coverage.gaps`` and says them in the document's
    own time (``pace.now``); "" when its view reaches no gap that is news.
    """

    if not isinstance(document, Mapping):
        return ""
    pace = document.get("pace")
    now = pace.get("now") if isinstance(pace, Mapping) else None
    return gap_sentence(gap_times(document.get("coverage")), now)
