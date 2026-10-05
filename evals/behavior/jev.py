"""A prototype attention route through Jev, a typed decision model.

Step 4 of the plan on #94 turns steps 1 and 2 into typed questions answered
by two routes: Jev, and an LLM. Before building that, this prototype answers
today's attention judgment with Jev's typed answers, so the behavior suite can
compare Jev's speed and fit with the LLM routes on the same scenes. It lives
in the evals because the shared core names no model vendor.

Jev answers questions about a ``state`` object through OpenRouter's Decisions
API (``POST /api/alpha/decisions``) and returns probabilities, never text. The
move it picks becomes the disposition, and the reading the agent sees is
written from its answers, each note citing the judged message.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Mapping
import urllib.error
import urllib.request

from nunchi.attention import AttentionError


DEFAULT_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_PREFIX = "typesafe/"

# The moves from docs/behavior.md, in the order ties are broken: when unsure,
# pay attention.
MOVES = ("speak", "mhm", "wait", "stay_quiet")


def is_jev(model_id: str) -> bool:
    return model_id.startswith(JEV_PREFIX) or model_id.startswith("~" + JEV_PREFIX)


def _name(projection: Mapping[str, Any]) -> str:
    self_doc = projection["self"]
    names = self_doc.get("names") or ()
    return names[0] if names else self_doc["participant_id"]


def jev_state(projection: Mapping[str, Any], instructions: str) -> dict[str, Any]:
    """The conversation as Jev sees it: who said what, to whom, and when."""

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
    state: dict[str, Any] = {
        "participant": {
            "name": _name(projection),
            "other_names": list(projection["self"].get("names", ())[1:]),
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
    return state


def jev_questions(name: str) -> dict[str, Any]:
    """Today's attention judgment as typed questions about the judged message."""

    return {
        "conversation": {
            "type": "noul",
            "instructions": (
                f"Is the judged message part of a conversation that people or agents are having, "
                f"which {name} could take part in?"
            ),
            "criteria": {
                "true": "Someone is talking to others: a question, an idea, a story, a request, a greeting, or a reply.",
                "false": "A status report, bot or CI output, a system event, or an automated notice nobody is talking through.",
            },
        },
        "addressee": {
            "type": "choice",
            "instructions": "Who is the judged message addressed to?",
            "criteria": {
                "participant": f"{name} specifically: by name, mention, reply, or clearly from context.",
                "room": f"Everyone in the room, or a group that includes {name}.",
                "someone_else": f"A specific person or agent other than {name}.",
                "nobody": "Nobody in particular: a remark, a status line, or thinking out loud.",
            },
        },
        "answered": {
            "type": "noul",
            "instructions": (
                f"Has someone other than {name} already answered or handled what the judged message asks for?"
            ),
            "criteria": {
                "true": "Another message from someone else already gives the answer or does what was asked.",
                "false": "Nothing in the conversation answers or handles it yet, or it asks for nothing.",
            },
        },
        "mid_thought": {
            "type": "noul",
            "instructions": (
                "Is the author of the judged message in the middle of saying something across several "
                "messages, and not finished yet?"
            ),
            "criteria": {
                "true": "The author is building up to a point, telling a story, or listing things, and has more to say.",
                "false": "The author's thought is complete, or the message stands on its own.",
            },
        },
        "adds_something": {
            "type": "noul",
            "instructions": (
                f"Given its instructions, does {name} have something useful to add here that nobody has said yet?"
            ),
            "criteria": {
                "true": f"{name}'s role or knowledge gives it a relevant answer, fact, or view the conversation lacks.",
                "false": f"{name} has nothing new to add, or the topic is outside its role.",
            },
        },
        "move": {
            "type": "choice",
            "instructions": (
                f"Which kind of response from {name} would fit this moment best, the way a socially aware "
                "person in the room would act?"
            ),
            "criteria": {
                "speak": "Say something to the room: an answer, a question, an opinion, or anything else.",
                "mhm": "A quick acknowledgement, like a nod or 'mhm', that shows it is following without taking the floor.",
                "wait": "Hold off for now: let the addressee answer first, or let the speaker finish.",
                "stay_quiet": f"Nothing is needed from {name} here.",
            },
        },
    }


def _probability(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, number)) if number == number else 0.0


def _noul(answers: Mapping[str, Any], key: str) -> float:
    return _probability((answers.get(key) or {}).get("noul"))


_ADDRESSEE = {
    "participant": "The judged message is addressed to you",
    "room": "The judged message is addressed to the whole room, which includes you",
    "someone_else": "The judged message is addressed to someone else",
    "nobody": "The judged message is not addressed to anyone in particular",
}
_MOVE_WORDS = {"speak": "speak", "mhm": "a quick mhm", "wait": "wait", "stay_quiet": "stay quiet"}


def judgment_from_answers(
    answers: Mapping[str, Any],
    projection: Mapping[str, Any],
    *,
    max_notes: int = 4,
) -> dict[str, Any]:
    """Map Jev's typed answers onto today's attention judgment.

    The most likely move decides the disposition: speak wakes, mhm acknowledges,
    wait or stay quiet suppresses, and the engine's margin widens a close
    suppression to DEFER. The reading describes what Jev found, citing the
    judged message, and never orders a move.
    """

    trigger = projection["trigger_event_id"]
    move = answers.get("move") or {}
    probabilities = {key: _probability((move.get("probabilities") or {}).get(key)) for key in MOVES}
    vector = {
        "PASS": min(1.0, probabilities["wait"] + probabilities["stay_quiet"]),
        "ACK": probabilities["mhm"],
        "ASK": 0.0,
        "SPEAK": probabilities["speak"],
    }
    disposition = max(
        (("WAKE", vector["SPEAK"]), ("ACK", vector["ACK"]), ("SUPPRESS", vector["PASS"])),
        key=lambda item: item[1],
    )[0]

    notes = []
    addressee = answers.get("addressee") or {}
    choice = addressee.get("choice")
    if choice in _ADDRESSEE:
        share = _probability((addressee.get("probabilities") or {}).get(choice))
        notes.append(f"{_ADDRESSEE[choice]} (Jev: {share:.2f}).")
    conversation = _noul(answers, "conversation")
    if "conversation" in answers and conversation < 0.5:
        notes.append(
            f"It reads more like a status update or system output than conversation "
            f"(Jev: {conversation:.2f} that it is conversation)."
        )
    for key, text in (
        ("answered", "Someone else seems to have already answered or handled it"),
        ("mid_thought", "The author seems to be mid-thought, with more to say"),
        ("adds_something", "You may know something useful that nobody has said yet"),
    ):
        share = _noul(answers, key)
        if share >= 0.5:
            notes.append(f"{text} (Jev: {share:.2f}).")
    ranked = sorted(MOVES, key=lambda key: -probabilities[key])
    fits = (
        "Kinds of response that could fit, by Jev's probability: "
        + ", ".join(f"{_MOVE_WORDS[key]} {probabilities[key]:.2f}" for key in ranked)
        + "."
    )
    notes = notes[: max(0, max_notes - 1)] + [fits]

    reasons = [f"Jev move: {move.get('choice', 'none')} (confidence {_probability(move.get('confidence')):.2f})"]
    reasons += [
        f"Jev {key}: {_noul(answers, key):.2f}"
        for key in ("conversation", "answered", "mid_thought", "adds_something")
        if key in answers
    ]
    if choice:
        reasons.append(f"Jev addressee: {choice}")
    return {
        "disposition": disposition,
        "reasons": reasons[:8],
        "evidence_event_ids": [trigger],
        "legacy_verdict_confidences": vector,
        "attention_advice": [{"note": note, "evidence_event_ids": [trigger]} for note in notes],
    }


class JevAttentionModel:
    """Today's attention judgment, answered by Jev through the Decisions API."""

    name = "participant-attention"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        url: str = DEFAULT_DECISIONS_URL,
        provider: str = "openrouter",
        max_notes: int = 4,
    ) -> None:
        self.model_id = model
        self.provider = provider
        self._url = url
        self._api_key = api_key
        self.max_notes = max_notes
        self._instructions = ""
        self.last_response: Mapping[str, Any] | None = None

    def bind_profile(self, profile: Any) -> None:
        """Give Jev the participant's own instructions, not the LLM prompt."""

        self._instructions = profile.instructions

    def judge(
        self,
        *,
        instructions: str,
        projection: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        body = {
            "model": self.model_id,
            "state": jev_state(projection, self._instructions),
            "questions": jev_questions(_name(projection)),
        }
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise AttentionError(f"Jev returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, socket.timeout, OSError, json.JSONDecodeError) as exc:
            raise AttentionError("Jev request failed") from exc
        if not isinstance(payload, Mapping) or not isinstance(payload.get("answers"), Mapping):
            raise AttentionError("Jev response has no answers")
        self.last_response = payload
        return judgment_from_answers(payload["answers"], projection, max_notes=self.max_notes)
