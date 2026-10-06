"""The participant remembers its own part in the room (#94, plan step 5).

`docs/behavior.md`: the agent's turn carries its conversation memory and its
own recent moves. These tests cover the first part of that memory: what the
participant itself said, replied, reacted to, and where it stayed quiet,
each pointing at the message it was about. Facts with pointers, never
verdicts; old items fade.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from nunchi.errors import ValidationError
from nunchi.memory import ConversationMemory
from nunchi.participant_model import ParticipantTurnProtocol
from nunchi.v2_contracts import validate_participant_wake
from tests.v2.test_operator_protocol import PROFILE, opportunity
from tests.v2.test_shared_foundation import foundation, message

SELF = "discord:bot:9"
ZOE = {"human:zoe": {"kind": "human"}}
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)


def at(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def reaction(event_id, target, *, author_id=SELF, operation="add", **extra):
    return {
        "id": event_id,
        "type": "reaction",
        "author_id": author_id,
        "target_event_id": target,
        "reaction": "\U0001f442",
        "operation": operation,
        **extra,
    }


class OwnMovesTests(unittest.TestCase):
    def moves(self, events, memory=None, **kwargs):
        return (memory or ConversationMemory(**kwargs)).own_moves(events, actor_id=SELF, now=NOW)

    def test_its_own_messages_replies_and_reactions_are_its_moves(self):
        events = [
            message("q1", text="Vigil, can you check the build?", timestamp=at(30)),
            message("v1", author_id=SELF, text="Will do.", reply_to_event_id="q1", timestamp=at(29)),
            message("c1", author_id="human:castor", text="Thanks Vigil"),
            reaction("r1", "c1"),
            reaction("r2", "c1", operation="remove"),
            message("v2", author_id=SELF, text="Build is green."),
        ]
        self.assertEqual(
            [
                {"kind": "reply", "event_id": "v1", "about_event_id": "q1", "text": "Will do.", "at": at(29)},
                {"kind": "reaction", "event_id": "r1", "about_event_id": "c1", "reaction": "\U0001f442"},
                {"kind": "message", "event_id": "v2", "text": "Build is green."},
            ],
            self.moves(events),
        )

    def test_a_silence_sits_after_the_message_it_was_about(self):
        memory = ConversationMemory()
        memory.record_silence(about_event_id="q1", at=NOW - timedelta(minutes=5))
        events = [message("q1"), message("v1", author_id=SELF, text="Later answer.")]
        self.assertEqual(["silence", "message"], [move["kind"] for move in self.moves(events, memory)])
        self.assertEqual({"kind": "silence", "about_event_id": "q1", "at": at(5)}, self.moves(events, memory)[0])

    def test_old_moves_fade(self):
        memory = ConversationMemory(own_moves=2, max_age_seconds=3600)
        memory.record_silence(about_event_id="gone")
        events = [
            message("v0", author_id=SELF, text="Yesterday", timestamp=at(120)),
            message("v1", author_id=SELF, text="one"),
            message("v2", author_id=SELF, text="two"),
            message("v3", author_id=SELF, text="three"),
        ]
        # Too old, beyond the newest two, or about a message no longer kept.
        self.assertEqual(["v2", "v3"], [move["event_id"] for move in self.moves(events, memory)])

    def test_silences_never_push_out_what_it_said(self):
        memory = ConversationMemory(own_moves=8, silences=2)
        events = [message("v1", author_id=SELF, text="Will do.")]
        for index in range(5):
            events.append(message(f"q{index}"))
            memory.record_silence(about_event_id=f"q{index}")
        moves = self.moves(events, memory)
        self.assertEqual(
            [("message", "v1"), ("silence", "q3"), ("silence", "q4")],
            [(move["kind"], move.get("event_id") or move["about_event_id"]) for move in moves],
        )

    def test_long_text_is_shortened(self):
        (move,) = self.moves([message("v1", author_id=SELF, text="word " * 200)])
        self.assertLessEqual(len(move["text"]), 280)
        self.assertTrue(move["text"].endswith("…"))

    def test_limits_are_positive(self):
        for bad in ({"own_moves": 0}, {"silences": 0}, {"max_age_seconds": -1}, {"own_moves": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ConversationMemory(**bad)


class TurnTests(unittest.TestCase):
    """The host keeps the memory and every turn carries it."""

    def test_a_silent_turn_is_remembered_and_shown_next_time(self):
        wakes = []
        pipeline, _, _, _ = foundation(participant=lambda **turn: wakes.append(turn["wake"]) or None)
        pipeline.handle_delivery(delivery_id="d-q1", event=message("q1"), actors=ZOE)
        self.assertNotIn("memory", wakes[0])
        pipeline.handle_delivery(delivery_id="d-q2", event=message("q2", text="Anyone?"), actors=ZOE)
        (silence,) = wakes[1]["memory"]["own_moves"]
        self.assertEqual(("silence", "q1"), (silence["kind"], silence["about_event_id"]))
        # The model reads the wake inside its turn document.
        protocol = ParticipantTurnProtocol(profile=PROFILE, wake=wakes[1], opportunity=opportunity())
        self.assertEqual(wakes[1]["memory"], protocol.input_document["participant_turn"]["wake"]["memory"])

    def test_its_own_message_in_the_room_is_remembered(self):
        wakes = []
        pipeline, _, _, _ = foundation(participant=lambda **turn: wakes.append(turn["wake"]) or None)
        pipeline.observation.observe(
            delivery_id="d-v1",
            event=message("v1", author_id=SELF, text="I'll check the deploy."),
            actors={},
        )
        pipeline.handle_delivery(delivery_id="d-q1", event=message("q1", text="How's the deploy?"), actors=ZOE)
        self.assertEqual(
            [{"kind": "message", "event_id": "v1", "text": "I'll check the deploy."}],
            wakes[0]["memory"]["own_moves"],
        )

    def test_a_restart_forgets_what_only_the_host_knew(self):
        wakes = []
        pipeline, _, _, _ = foundation(participant=lambda **turn: wakes.append(turn["wake"]) or None)
        pipeline.handle_delivery(delivery_id="d-q1", event=message("q1"), actors=ZOE)
        pipeline.restart()
        pipeline.handle_delivery(delivery_id="d-q2", event=message("q2"), actors=ZOE)
        self.assertNotIn("memory", wakes[-1])

    def test_the_runtime_contract_checks_memory(self):
        wakes = []
        pipeline, _, _, _ = foundation(participant=lambda **turn: wakes.append(turn["wake"]) or None)
        pipeline.handle_delivery(delivery_id="d-q1", event=message("q1"), actors=ZOE)
        pipeline.handle_delivery(delivery_id="d-q2", event=message("q2"), actors=ZOE)
        wake = wakes[-1]
        validate_participant_wake(wake)
        for bad in (
            {"own_moves": []},
            {"own_moves": [{"kind": "silence", "about_event_id": "q1"}]},
            {"own_moves": [{"kind": "message", "event_id": "v1", "text": "x" * 281}]},
            {"own_moves": wake["memory"]["own_moves"], "obligations": ["reply to q1"]},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_participant_wake({**wake, "memory": bad})


class PromptTests(unittest.TestCase):
    def test_both_turn_prompts_read_like_a_person_in_a_room(self):
        from nunchi.participant_model import participant_tool_turn_prompt, participant_turn_prompt

        for prompt in (
            participant_turn_prompt(PROFILE),
            participant_tool_turn_prompt(PROFILE, tools={"send": "send", "context": "context"}),
        ):
            with self.subTest(prompt=prompt[:30]):
                self.assertIn("socially aware person in a group conversation", prompt)
                self.assertIn("a follow-up on something you said you would do", prompt)
                self.assertIn("memory.own_moves", prompt)
                self.assertIn("not a to-do list", prompt)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
