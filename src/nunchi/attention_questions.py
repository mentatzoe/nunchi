"""Steps 1 and 2 of reading the room, as typed questions (#94, step 4).

Step 1 asks whether the judged message is conversation that a participant
like this one could take part in. Step 2 asks what is happening and which
kinds of response could fit. Both are fixed typed questions with pointers to
messages, so any model can answer them: a chat model answers them as a JSON
object, and a typed decision model answers them natively. The core sees one
set of answers either way, decides from them, and writes the participant's
reading of the room from them (``docs/behavior.md``).

The answers are the model's judgment. Code here only maps them onto the
contract's dispositions and renders them as notes; it never decides relevance
on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math
from numbers import Real
from typing import Any

from .v2_contracts import (
    ANSWER_ADDRESSEES,
    ANSWER_MOVES,
    ANSWER_POINTERS,
    ANSWER_QUESTIONS,
    READING_MAX_ITEMS,
    READING_NOTE_MAX_CHARS,
    UNATTENDED_POINTER,
)


# Ties are broken toward paying attention: speak, then mhm, then wait.
MOVES = ANSWER_MOVES
ADDRESSEES = ANSWER_ADDRESSEES

YES_NO = "yes_no"
CHOICE = "choice"
EVENT = "event"

# The order questions are asked and answers are kept.
QUESTION_IDS = ANSWER_QUESTIONS

_MOVE_WORDS = {
    "speak": "speak",
    "mhm": "a quick mhm",
    "wait": "wait",
    "stay_quiet": "stay quiet",
}
# A mhm is the participant's own move (#94 step 7): it gets the turn, with the
# reading, and decides for itself.
_MOVE_DISPOSITION = {"speak": "WAKE", "mhm": "DEFER", "wait": "DEFER", "stay_quiet": "DEFER"}


def attention_questions(name: str, *, unattended: bool = False) -> dict[str, dict[str, Any]]:
    """The fixed typed questions, worded for the participant called ``name``.

    Each question has a ``kind``: ``yes_no`` (a probability that the answer
    is yes), ``choice`` (a probability for every option), or ``event`` (the
    id of one supplied message, or none). ``step`` says which step of
    reading the room it belongs to. With ``unattended``, the judgment also
    covers messages that arrived while the participant was busy, and one more
    question asks which of them still calls for it (#94 step 6).
    """

    questions = {
        "conversation": {
            "step": 1,
            "kind": YES_NO,
            "ask": (
                f"Is the judged message conversation that a participant like {name} "
                "could take part in?"
            ),
            "yes": (
                "Someone is talking to people or agents in the room: a question, an "
                "idea, a story, a request, a greeting, a reply, or a remark. This "
                "holds whoever it is addressed to."
            ),
            "no": (
                "Not conversation: a status report, bot or CI output, a system event, "
                f"an automated notice nobody is talking through, or {name}'s own "
                "message echoed back."
            ),
        },
        "addressee": {
            "step": 2,
            "kind": CHOICE,
            "ask": "Who is the judged message addressed to?",
            "options": {
                "participant": f"{name} specifically: by name, mention, reply, or clearly from context.",
                "room": f"Everyone in the room, or a group that includes {name}.",
                "someone_else": f"A specific person or agent other than {name}.",
                "nobody": "Nobody in particular: a remark, a status line, or thinking out loud.",
            },
        },
        "asks": {
            "step": 2,
            "kind": YES_NO,
            "ask": "Does the judged message ask someone in the room for something?",
            "yes": "It asks a question, or asks for an action, an opinion or a decision.",
            "no": "It asks nothing: a remark, a report, an answer, thanks, or a greeting.",
        },
        "answered": {
            "step": 2,
            "kind": YES_NO,
            "ask": (
                f"Has someone other than {name} already answered or handled what the "
                "judged message asks for?"
            ),
            "yes": "A message from someone else already gives the answer or does what was asked.",
            "no": "Nothing answers or handles it yet, or it asks for nothing.",
        },
        "answered_by": {
            "step": 2,
            "kind": EVENT,
            "ask": (
                f"Which supplied message from someone other than {name} answered or "
                "handled it?"
            ),
            "none": "null if nothing did",
            "no_message": "No supplied message answered or handled it.",
        },
        "responds_to": {
            "step": 2,
            "kind": EVENT,
            "ask": (
                "Which earlier supplied message, if any, does the judged message answer "
                f"or respond to? It may be one of {name}'s own."
            ),
            "none": "null if it responds to none",
            "no_message": "It answers or responds to no earlier supplied message.",
        },
        "mid_thought": {
            "step": 2,
            "kind": YES_NO,
            "ask": (
                "Is the author of the judged message in the middle of saying something "
                "across several messages, with more to come?"
            ),
            "yes": "The author is building up to a point, telling a story, or listing things, and has more to say.",
            "no": "The author's thought is complete, or the message stands on its own.",
        },
        "adds_something": {
            "step": 2,
            "kind": YES_NO,
            "ask": (
                f"Given its instructions, does {name} have something useful to add here "
                "that nobody has said yet?"
            ),
            "yes": f"{name}'s role or knowledge gives it a relevant answer, fact, question, or view the conversation lacks.",
            "no": f"{name} has nothing new to add, or the topic is outside its role.",
        },
        "move": {
            "step": 2,
            "kind": CHOICE,
            "ask": (
                f"Which kind of response from {name} would fit this moment best, the way "
                "a socially aware person in the room would act?"
            ),
            "options": {
                "speak": "Say something to the room: an answer, a question, an opinion, or anything else.",
                "mhm": "A quick acknowledgement, like a nod or 'mhm', that shows it is following without taking the floor.",
                "wait": "Hold off for now: let the addressee answer first, or let the speaker finish.",
                "stay_quiet": f"Nothing is needed from {name} here.",
            },
        },
    }
    if unattended:
        questions[UNATTENDED_POINTER] = {
            "step": 2,
            "kind": EVENT,
            "ask": (
                f"Which of the messages that arrived while {name} was busy with its "
                f"previous turn still calls for {name}: asked of it or of the room, and "
                "not yet answered?"
            ),
            "none": "null if none does",
            "no_message": f"None of them still calls for {name}.",
        }
    return questions


def participant_name(projection: Mapping[str, Any]) -> str:
    """The name the questions use for the participant."""

    self_doc = projection["self"]
    names = self_doc.get("names") or ()
    return names[0] if names else self_doc["participant_id"]


def attention_state(projection: Mapping[str, Any], instructions: str) -> dict[str, Any]:
    """The conversation as a typed decision model sees it.

    The same facts the chat-model route receives, shaped as a plain state
    document: who said what, to whom, and when, with the participant's own
    trusted instructions.
    """

    actors = projection.get("actors", {})
    own_actor = projection["self"]["actor_id"]

    def who(actor_id: str) -> str:
        actor = actors.get(actor_id) or {}
        return actor.get("display_name") or actor_id

    conversation = []
    for event in projection["events"]:
        item: dict[str, Any] = {"id": event["id"], "from": who(event["author_id"])}
        if event["author_id"] == own_actor:
            item["from_participant"] = True
        kind = (actors.get(event["author_id"]) or {}).get("kind")
        if kind:
            item["from_kind"] = kind
        if event["type"] == "message":
            item["text"] = event.get("text", "")
            mentions = [who(actor_id) for actor_id in event.get("mentioned_actor_ids", ())]
            if mentions:
                item["mentions"] = mentions
            if event.get("mentions_room"):
                item["mentions_room"] = True
            if event.get("reply_to_event_id"):
                item["reply_to"] = event["reply_to_event_id"]
        elif event["type"] == "reaction":
            item["reaction"] = event.get("reaction")
            item["reacting_to"] = event.get("target_event_id")
        else:
            item["event"] = event["type"]
        if event.get("timestamp"):
            item["time"] = event["timestamp"]
        conversation.append(item)
    names = list(projection["self"].get("names", ()))
    state: dict[str, Any] = {
        "participant": {
            "name": participant_name(projection),
            "other_names": names[1:],
            "instructions": instructions,
        },
        "room": {
            "platform": projection["room"].get("platform"),
            "kind": projection["room"].get("kind"),
        },
        "conversation": conversation,
        "judged_message_id": projection["trigger_event_id"],
    }
    if projection.get("coverage", {}).get("has_more_before"):
        state["earlier_messages_not_shown"] = True
    if projection.get("pace"):
        state["pace"] = deepcopy(dict(projection["pace"]))
    if projection.get("occasion"):
        state["occasion"] = projection["occasion"]
    if projection.get("unattended_event_ids"):
        # Arrived while the participant was busy, newest first (#94 step 6).
        state["unattended_message_ids"] = list(projection["unattended_event_ids"])
    # The participant's memory is left out on purpose (#94 step 6): with it,
    # Jev's own top move fit fell from 186 to 175 of 231 moments (run 37),
    # mostly turning "speak" into "wait" or "stay quiet" where the agent had
    # held back before, and it still hid the CI line the agent had promised
    # to report on. A chat model gets the memory; a typed model does not yet.
    return state


def answer_candidates(projection: Mapping[str, Any]) -> list[str]:
    """Messages that could have answered the judged message.

    Messages by anyone but the participant, other than the judged message
    itself; the pointer question chooses among these.
    """

    own_actor = projection["self"]["actor_id"]
    trigger = projection["trigger_event_id"]
    return [
        event["id"]
        for event in projection["events"]
        if event["type"] == "message"
        and event["id"] != trigger
        and event["author_id"] != own_actor
    ]


def response_candidates(projection: Mapping[str, Any]) -> list[str]:
    """Earlier messages the judged message could answer or respond to.

    Messages before the judged one, the participant's own included: someone
    answering the participant's question is part of what it remembers.
    """

    trigger = projection["trigger_event_id"]
    earlier = []
    for event in projection["events"]:
        if event["id"] == trigger:
            break
        if event["type"] == "message":
            earlier.append(event["id"])
    return earlier


def _probability(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or not 0 <= float(value) <= 1
    ):
        raise ValueError(f"answer {label} must be a probability within [0, 1]")
    return round(float(value), 4)


_YES_NO_WORDS = {"yes": 1.0, "true": 1.0, "no": 0.0, "false": 0.0}


def _yes_no(value: Any, label: str) -> float:
    """The probability of yes.

    Chat models asked for a probability sometimes write a yes/no answer as a
    boolean, a word, or a ``{"yes", "no"}`` split. Each states its answer
    unambiguously, so it is read as that probability rather than failing the
    whole judgment. Anything else must be a probability.
    """

    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, str) and value.strip().lower() in _YES_NO_WORDS:
        return _YES_NO_WORDS[value.strip().lower()]
    if isinstance(value, Mapping) and set(value) == {"yes", "no"}:
        return _distribution(value, ("yes", "no"), label)["yes"]
    return _probability(value, label)


def _distribution(value: Any, options: tuple[str, ...], label: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) - set(options):
        raise ValueError(f"answer {label} must give probabilities for {', '.join(options)}")
    raw = {key: _probability(value.get(key, 0), f"{label}.{key}") for key in options}
    total = sum(raw.values())
    if total <= 0:
        # No preference at all is uncertainty: spread it evenly.
        return {key: round(1 / len(options), 4) for key in options}
    return {key: round(raw[key] / total, 4) for key in options}


def validate_answers(
    raw: Any,
    *,
    event_ids: set[str],
    trigger_event_id: str,
    unattended: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Check one set of typed answers and return it in the core's shape.

    Raises ``ValueError`` when an answer is missing or malformed. A yes/no
    answer written as a boolean, a word, or a yes/no split is read as the
    probability it states. A choice is normalized to sum to 1. A pointer to
    a message the model was not given, or to the judged message itself, is
    dropped on its own rather than failing the judgment. The answer about
    unattended messages is kept only when it names one of ``unattended``.
    """

    if not isinstance(raw, Mapping):
        raise ValueError("answers must be an object")
    required = set(QUESTION_IDS) - set(ANSWER_POINTERS)
    if required - set(raw) or set(raw) - set(QUESTION_IDS) - {UNATTENDED_POINTER}:
        raise ValueError("answers have a missing or unexpected question")
    answers: dict[str, Any] = {
        "conversation": _yes_no(raw["conversation"], "conversation"),
        "addressee": _distribution(raw["addressee"], ADDRESSEES, "addressee"),
        "asks": _yes_no(raw["asks"], "asks"),
        "answered": _yes_no(raw["answered"], "answered"),
        "mid_thought": _yes_no(raw["mid_thought"], "mid_thought"),
        "adds_something": _yes_no(raw["adds_something"], "adds_something"),
        "move": _distribution(raw["move"], MOVES, "move"),
    }
    for key in ANSWER_POINTERS:
        pointer = raw.get(key)
        if pointer is not None and not isinstance(pointer, str):
            raise ValueError(f"answer {key} must be a message id or null")
        if pointer and pointer in event_ids and pointer != trigger_event_id:
            answers[key] = pointer
    waiting = raw.get(UNATTENDED_POINTER)
    if waiting is not None and not isinstance(waiting, str):
        raise ValueError(f"answer {UNATTENDED_POINTER} must be a message id or null")
    kept = {key: answers[key] for key in QUESTION_IDS if key in answers}
    if waiting and waiting in unattended:
        kept[UNATTENDED_POINTER] = waiting
    return kept


def top_move(answers: Mapping[str, Any]) -> str:
    """The most likely move; ties go to the one that pays more attention."""

    move = answers["move"]
    return max(MOVES, key=lambda key: (move[key], -MOVES.index(key)))


def classifier_disposition(answers: Mapping[str, Any]) -> str:
    """Map the answers onto the contract's classifier disposition.

    Step 1 suppresses only what is more likely not conversation, and only
    when the judgment's own most likely move is not to speak. A CI line the
    participant promised to report on is not conversation, but if the
    answers say speaking is most likely, hiding it would be the invisible
    mistake: a wrong suppression is never seen, and a wrong pass costs one
    turn (``docs/behavior.md``; #94 step 6). Otherwise the participant gets
    a turn: speaking wakes it, and a mhm, waiting or staying quiet defer to
    it with the reading. A message that arrived while the
    participant was busy and still calls for it is never hidden either.
    """

    move = top_move(answers)
    if answers["conversation"] < 0.5 and move != "speak" and not answers.get(UNATTENDED_POINTER):
        return "SUPPRESS"
    return _MOVE_DISPOSITION[move]


def suppression_margin_distance(answers: Mapping[str, Any]) -> float:
    """How far step 1 leans toward "not conversation", for the margin valve."""

    return (1 - answers["conversation"]) - answers["conversation"]


def answer_reasons(answers: Mapping[str, Any]) -> list[str]:
    """Short audit strings that record the answers."""

    addressee = answers["addressee"]
    who = max(ADDRESSEES, key=lambda key: (addressee[key], -ADDRESSEES.index(key)))
    move = top_move(answers)
    reasons = [
        f"conversation {answers['conversation']:.2f}",
        f"addressee {who} {addressee[who]:.2f}",
        f"asks {answers['asks']:.2f}",
        f"answered {answers['answered']:.2f}",
    ]
    for key in ANSWER_POINTERS + (UNATTENDED_POINTER,):
        if answers.get(key):
            reasons.append(f"{key} {answers[key]}")
    reasons += [
        f"mid_thought {answers['mid_thought']:.2f}",
        f"adds_something {answers['adds_something']:.2f}",
        f"move {move} {answers['move'][move]:.2f}",
    ]
    return reasons


def answer_evidence(answers: Mapping[str, Any], trigger_event_id: str) -> list[str]:
    evidence = [trigger_event_id]
    for key in ANSWER_POINTERS + (UNATTENDED_POINTER,):
        if answers.get(key) and answers[key] not in evidence:
            evidence.append(answers[key])
    return evidence


_ADDRESSEE_NOTES = {
    "participant": "The judged message is addressed to you",
    "room": "The judged message is addressed to the whole room, which includes you",
    "someone_else": "The judged message is addressed to someone else",
    "nobody": "The judged message is not addressed to anyone in particular",
}


def _author(projection: Mapping[str, Any], event_id: str) -> str | None:
    for event in projection.get("events", ()):
        if event["id"] == event_id:
            actor = (projection.get("actors") or {}).get(event["author_id"]) or {}
            return actor.get("display_name") or event["author_id"]
    return None


def _duration(seconds: int) -> str:
    """A pause or run in the words a person would use."""

    for unit, size in (("day", 86_400), ("hour", 3_600), ("minute", 60)):
        if seconds >= size:
            count = seconds // size
            return f"{count} {unit}{'' if count == 1 else 's'}"
    return f"{seconds} second{'' if seconds == 1 else 's'}"


def _pace_notes(projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What a person would notice about the pace (#94 step 6), as facts."""

    pace = projection.get("pace") or {}
    trigger = projection["trigger_event_id"]
    notes = []
    quiet = pace.get("quiet_before_seconds")
    if isinstance(quiet, int) and quiet >= 3_600:
        notes.append(
            {"note": f"The room was quiet for {_duration(quiet)} before this message.", "evidence_event_ids": [trigger]}
        )
    run, took = pace.get("author_run_messages"), pace.get("author_run_seconds")
    if isinstance(run, int) and run >= 2 and isinstance(took, int) and took <= 300:
        author = _author(projection, trigger) or "The author"
        notes.append(
            {
                "note": f"{author} has sent {run} messages in a row over {_duration(took)}.",
                "evidence_event_ids": [trigger],
            }
        )
    return notes


def _occasion_note(projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Why this message is judged without a new one (#94 step 6).

    On a look again after a pause, how long the room has been quiet; on an
    outcome turn, that the participant's approved action has finished.
    """

    if projection.get("occasion") == "outcome":
        name = participant_name(projection)
        return [
            {
                "note": f"An operator approved an action {name} proposed, and it has settled. "
                f"Nobody in the room has been told how it went; {name} has a turn to tell them.",
                "evidence_event_ids": [projection["trigger_event_id"]],
            }
        ]
    since = (projection.get("pace") or {}).get("judged_seconds_ago")
    if projection.get("occasion") != "pause" or not isinstance(since, int):
        return []
    events = projection["events"]
    trigger = projection["trigger_event_id"]
    position = next((index for index, event in enumerate(events) if event.get("id") == trigger), None)
    if position is None or any(event.get("type") == "message" for event in events[position + 1:]):
        return []
    return [
        {
            "note": f"Nothing new has been said for {_duration(since)} since this message.",
            "evidence_event_ids": [projection["trigger_event_id"]],
        }
    ]


def _is_own(projection: Mapping[str, Any], event_id: str) -> bool:
    own_actor = projection["self"]["actor_id"]
    return any(
        event["id"] == event_id and event["author_id"] == own_actor
        for event in projection.get("events", ())
    )


def fact_notes(answers: Mapping[str, Any], projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Describe what the answers found, each note citing its messages."""

    trigger = projection["trigger_event_id"]
    notes = []
    addressee = answers["addressee"]
    who = max(ADDRESSEES, key=lambda key: (addressee[key], -ADDRESSEES.index(key)))
    if answers["asks"] >= 0.5:
        text = f"{_ADDRESSEE_NOTES[who]}, and it asks for something ({addressee[who]:.2f}; asks {answers['asks']:.2f})."
    else:
        text = f"{_ADDRESSEE_NOTES[who]} ({addressee[who]:.2f})."
    notes.append({"note": text, "evidence_event_ids": [trigger]})
    notes += _occasion_note(projection)
    if answers["conversation"] < 0.5:
        notes.append(
            {
                "note": (
                    "It reads more like a status update or system output than conversation "
                    f"({answers['conversation']:.2f} that it is conversation)."
                ),
                "evidence_event_ids": [trigger],
            }
        )
    if answers["answered"] >= 0.5:
        by = answers.get("answered_by")
        if by:
            author = _author(projection, by) or "someone else"
            text = f"{author} seems to have answered or handled it already, in {by} ({answers['answered']:.2f})."
            cited = [trigger, by]
        else:
            text = f"Someone else seems to have answered or handled it already ({answers['answered']:.2f})."
            cited = [trigger]
        notes.append({"note": text, "evidence_event_ids": cited})
    earlier = answers.get("responds_to")
    if earlier:
        if _is_own(projection, earlier):
            text = f"It answers or responds to your message {earlier}."
        else:
            author = _author(projection, earlier) or "someone"
            text = f"It answers or responds to {author}'s message {earlier}."
        notes.append({"note": text, "evidence_event_ids": [trigger, earlier]})
    notes += _pace_notes(projection)
    if answers["mid_thought"] >= 0.5:
        notes.append(
            {
                "note": f"The author seems mid-thought, with more to say ({answers['mid_thought']:.2f}).",
                "evidence_event_ids": [trigger],
            }
        )
    if answers["adds_something"] >= 0.5:
        notes.append(
            {
                "note": (
                    "You may know something useful that nobody has said yet "
                    f"({answers['adds_something']:.2f})."
                ),
                "evidence_event_ids": [trigger],
            }
        )
    return notes


def moves_note(answers: Mapping[str, Any], trigger_event_id: str) -> dict[str, Any]:
    move = answers["move"]
    ranked = sorted(MOVES, key=lambda key: (-move[key], MOVES.index(key)))
    return {
        "note": (
            "Kinds of response that could fit, most likely first: "
            + ", ".join(f"{_MOVE_WORDS[key]} {move[key]:.2f}" for key in ranked)
            + "."
        ),
        "evidence_event_ids": [trigger_event_id],
    }


def reading_from_answers(
    answers: Mapping[str, Any],
    projection: Mapping[str, Any],
    *,
    notes: list[dict[str, Any]] | None = None,
    max_items: int = READING_MAX_ITEMS,
    max_chars: int = READING_NOTE_MAX_CHARS,
) -> list[dict[str, Any]]:
    """The participant's reading of the room.

    It describes what is happening, with pointers to the messages, then the
    kinds of response that could fit with their probabilities. The
    description is the model's own notes when it wrote some, else notes
    rendered from its typed answers. It describes; it never orders.
    """

    if max_items <= 0:
        return []
    described = list(notes) if notes else fact_notes(answers, projection)
    waiting = answers.get(UNATTENDED_POINTER)
    if waiting:
        # The core says it on both routes, first: it is why this moment may
        # call for the participant even when the newest message does not.
        author = _author(projection, waiting) or "someone"
        described.insert(
            0,
            {
                "note": (
                    f"{author}'s message {waiting} arrived while you were busy with your "
                    "previous turn, and it still calls for you."
                ),
                "evidence_event_ids": [waiting],
            },
        )
    reading = described[: max_items - 1] + [moves_note(answers, projection["trigger_event_id"])]
    return [
        {"note": item["note"][:max_chars], "evidence_event_ids": list(item["evidence_event_ids"])}
        for item in deepcopy(reading)
    ]


def answers_leaning(disposition: str, *, close: bool = False) -> dict[str, Any]:
    """Typed answers that map to ``disposition``, for scripted models.

    Conformance checks and tests use these to drive the engine through each
    disposition; ``"mhm"`` leans toward a quick mhm, which defers to the
    participant. They match the chat-model schema exactly, so a host that
    validates structured output accepts them. ``close`` makes a suppression a
    near call that the margin valve widens to DEFER.
    """

    if disposition == "SUPPRESS":
        return {
            "conversation": 0.47 if close else 0.05,
            "addressee": {"participant": 0.0, "room": 0.0, "someone_else": 0.0, "nobody": 1.0},
            "asks": 0.0,
            "answered": 0.0,
            "answered_by": None,
            "responds_to": None,
            "mid_thought": 0.0,
            "adds_something": 0.0,
            "move": {"speak": 0.0, "mhm": 0.0, "wait": 0.1, "stay_quiet": 0.9},
        }
    move = {
        "WAKE": {"speak": 0.7, "mhm": 0.1, "wait": 0.15, "stay_quiet": 0.05},
        "mhm": {"speak": 0.2, "mhm": 0.6, "wait": 0.15, "stay_quiet": 0.05},
        "DEFER": {"speak": 0.25, "mhm": 0.05, "wait": 0.6, "stay_quiet": 0.1},
    }[disposition]
    return {
        "conversation": 0.95,
        "addressee": (
            {"participant": 0.1, "room": 0.1, "someone_else": 0.7, "nobody": 0.1}
            if disposition == "DEFER"
            else {"participant": 0.8, "room": 0.1, "someone_else": 0.05, "nobody": 0.05}
        ),
        "asks": 0.1 if disposition == "mhm" else 0.8,
        "answered": 0.05,
        "answered_by": None,
        "responds_to": None,
        "mid_thought": 0.8 if disposition == "mhm" else 0.05,
        "adds_something": 0.8 if disposition == "WAKE" else 0.3,
        "move": move,
    }
