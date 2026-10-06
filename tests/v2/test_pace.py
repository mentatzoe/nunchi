"""The room's pace reaches the judgment and the turn (#94, plan step 6).

`docs/behavior.md`: a socially aware participant notices the pace: a burst
of messages, someone mid-thought, a pause, a room quiet for hours, and its
own share. Timestamps alone leave that to arithmetic, so each snapshot
carries the pace as plain facts in whole seconds. These tests prove the facts
and where they go; whether models use them well is measured by behavior runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from nunchi.attention import participant_attention_prompt
from nunchi.attention_questions import answers_leaning, attention_state, fact_notes
from nunchi.pace import pace_facts
from nunchi.participant_model import participant_tool_turn_prompt, participant_turn_prompt
from nunchi.v2_contracts import validate_attention_request, validate_participant_wake
from tests.v2.test_operator_protocol import PROFILE
from tests.v2.test_shared_foundation import foundation, message

SELF = "discord:bot:9"
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
ZOE = {"human:zoe": {"kind": "human"}}


def at(seconds_ago):
    return (NOW - timedelta(seconds=seconds_ago)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class PaceFactTests(unittest.TestCase):
    def facts(self, events, trigger):
        return pace_facts(events, trigger_event_id=trigger, actor_id=SELF, now=NOW)

    def test_a_story_told_in_a_burst_after_a_quiet_night(self):
        events = [
            message("v1", author_id=SELF, text="Night all.", timestamp=at(8 * 3600)),
            message("s1", text="You won't believe the deploy.", timestamp=at(100)),
            message("s2", text="The canary looked fine.", timestamp=at(80)),
            message("s3", text="Then auth broke.", timestamp=at(60)),
        ]
        self.assertEqual(
            {
                "now": "2026-10-06T09:00:00.000Z",
                "window_messages": 4,
                "own_messages": 1,
                "judged_seconds_ago": 60,
                "quiet_before_seconds": 20,
                "author_run_messages": 3,
                "author_run_seconds": 40,
                "own_last_seconds_ago": 8 * 3600,
            },
            self.facts(events, "s3"),
        )
        # The first message of the morning came after hours of quiet.
        self.assertEqual(8 * 3600 - 100, self.facts(events, "s1")["quiet_before_seconds"])
        self.assertEqual(1, self.facts(events, "s1")["author_run_messages"])

    def test_someone_elses_message_breaks_a_run_and_a_reaction_does_not(self):
        events = [
            message("z1", timestamp=at(50)),
            message("c1", author_id="human:castor", timestamp=at(40)),
            message("z2", timestamp=at(30)),
            {"id": "r1", "type": "reaction", "author_id": "human:castor", "target_event_id": "z2",
             "reaction": "+1", "operation": "add", "timestamp": at(25)},
            message("z3", timestamp=at(20)),
        ]
        facts = self.facts(events, "z3")
        self.assertEqual((2, 10), (facts["author_run_messages"], facts["author_run_seconds"]))
        self.assertEqual(10, facts["quiet_before_seconds"])

    def test_a_fact_without_its_timestamps_is_left_out(self):
        facts = self.facts([message("z1"), message("z2")], "z2")
        self.assertEqual(
            {"now": "2026-10-06T09:00:00.000Z", "window_messages": 2, "own_messages": 0, "author_run_messages": 2},
            facts,
        )

    def test_a_reaction_trigger_has_no_author_run(self):
        events = [
            message("z1", timestamp=at(30)),
            {"id": "r1", "type": "reaction", "author_id": "human:castor", "target_event_id": "z1",
             "reaction": "+1", "operation": "add", "timestamp": at(5)},
        ]
        facts = self.facts(events, "r1")
        self.assertNotIn("author_run_messages", facts)
        self.assertEqual((5, 25), (facts["judged_seconds_ago"], facts["quiet_before_seconds"]))


class SnapshotTests(unittest.TestCase):
    def test_the_judgment_and_the_turn_carry_the_pace_at_their_own_time(self):
        wakes = []
        pipeline, _, _, _ = foundation(participant=lambda **turn: wakes.append(turn["wake"]) or None)
        clock = [NOW]
        pipeline.observation.clock = lambda: clock[0]
        pipeline.observation.observe(delivery_id="d-z1", event=message("z1", timestamp=at(7200)), actors=ZOE)
        request = pipeline.observation.build_snapshot("z1")
        self.assertEqual(7200, request["pace"]["judged_seconds_ago"])
        validate_attention_request(request)
        clock[0] = NOW + timedelta(seconds=30)
        pipeline.handle_delivery(delivery_id="d-z2", event=message("z2", timestamp=at(0)), actors=ZOE)
        pace = wakes[0]["pace"]
        self.assertEqual("2026-10-06T09:00:30.000Z", pace["now"])
        self.assertEqual((30, 7200), (pace["judged_seconds_ago"], pace["quiet_before_seconds"]))
        validate_participant_wake(wakes[0])


class PromptAndReadingTests(unittest.TestCase):
    def projection(self, pace):
        return {
            "self": {"participant_id": "vigil", "actor_id": SELF, "names": ["Vigil"]},
            "room": {"platform": "discord", "id": "42", "kind": "group"},
            "actors": {"human:zoe": {"display_name": "Zoe", "kind": "human"}},
            "events": [{"id": "z1", "type": "message", "author_id": "human:zoe", "text": "So..."}],
            "trigger_event_id": "z1",
            "coverage": {},
            "pace": pace,
        }

    def test_every_prompt_explains_the_pace(self):
        self.assertIn("observation.pace", participant_attention_prompt(PROFILE))
        for prompt in (participant_turn_prompt(PROFILE), participant_tool_turn_prompt(PROFILE, tools={"send": "send"})):
            with self.subTest(prompt=prompt[:30]):
                self.assertIn("When pace is present, it is the room's pace right now", prompt)

    def test_a_typed_model_gets_the_pace_in_its_state(self):
        pace = {"now": "2026-10-06T09:00:00.000Z", "window_messages": 1, "own_messages": 0}
        self.assertEqual(pace, attention_state(self.projection(pace), "x")["pace"])

    def test_the_reading_notes_a_long_quiet_and_a_quick_run(self):
        pace = {
            "now": "2026-10-06T09:00:00.000Z", "window_messages": 4, "own_messages": 0,
            "quiet_before_seconds": 7 * 3600, "author_run_messages": 3, "author_run_seconds": 40,
        }
        notes = [item["note"] for item in fact_notes(answers_leaning("WAKE"), self.projection(pace))]
        self.assertIn("The room was quiet for 7 hours before this message.", notes)
        self.assertIn("Zoe has sent 3 messages in a row over 40 seconds.", notes)
        slow = dict(pace, quiet_before_seconds=600, author_run_seconds=900)
        notes = [item["note"] for item in fact_notes(answers_leaning("WAKE"), self.projection(slow))]
        self.assertFalse([note for note in notes if "quiet for" in note or "in a row" in note])

    def test_a_look_again_says_how_long_the_room_has_been_quiet(self):
        pace = {"now": "2026-10-06T09:05:00.000Z", "window_messages": 1, "own_messages": 0, "judged_seconds_ago": 300}
        projection = dict(self.projection(pace), occasion="pause")
        notes = [item["note"] for item in fact_notes(answers_leaning("WAKE"), projection)]
        self.assertEqual("Nothing new has been said for 5 minutes since this message.", notes[1])
        self.assertEqual("pause", attention_state(projection, "x")["occasion"])
        # A judgment that comes with a new message says nothing of the kind.
        notes = [item["note"] for item in fact_notes(answers_leaning("WAKE"), self.projection(pace))]
        self.assertFalse([note for note in notes if note.startswith("Nothing new")])
        self.assertNotIn("occasion", attention_state(self.projection(pace), "x"))
        # Nor does a look again that something was said after.
        later = dict(projection, events=projection["events"] + [
            {"id": "c1", "type": "message", "author_id": "human:zoe", "text": "Found it."}
        ])
        notes = [item["note"] for item in fact_notes(answers_leaning("WAKE"), later)]
        self.assertFalse([note for note in notes if note.startswith("Nothing new")])

    def test_every_prompt_explains_a_look_again_and_an_outcome_turn(self):
        # Attention hears what an occasion means only when the judgment has one.
        ordinary = participant_attention_prompt(PROFILE)
        self.assertNotIn("occasion", ordinary)
        pause = participant_attention_prompt(PROFILE, occasion="pause")
        self.assertIn("This judgment has observation.occasion pause", pause)
        self.assertNotIn("outcome", pause)
        outcome = participant_attention_prompt(PROFILE, occasion="outcome")
        self.assertIn("This judgment has observation.occasion outcome", outcome)
        self.assertIn("Nobody in the room has been told how it went, and vigil gets a turn", outcome)
        for prompt in (participant_turn_prompt(PROFILE), participant_tool_turn_prompt(PROFILE, tools={"send": "send"})):
            with self.subTest(prompt=prompt[:30]):
                self.assertIn("When occasion is pause, no new message arrived", prompt)
                # Only a participant that may propose hears about outcome turns.
                self.assertNotIn("When occasion is outcome", prompt)
        proposing = participant_tool_turn_prompt(PROFILE, tools={"send": "send", "propose": "propose"})
        self.assertIn("When occasion is outcome, an operator approved an action you proposed", proposing)
        self.assertIn("Nunchi never says it for you", proposing)
        # Each way it can end is named, so the agent's words match it.
        for status in ("done means it ran", "failed means it was approved and tried", "unknown means", "denied means"):
            self.assertIn(status, proposing)
        self.assertIn("The approval was given in every case; only denied means the action was refused.", proposing)

    def test_an_outcome_turn_says_the_action_finished(self):
        pace = {"now": "2026-10-06T09:05:00.000Z", "window_messages": 1, "own_messages": 0, "judged_seconds_ago": 900}
        projection = dict(self.projection(pace), occasion="outcome")
        notes = [item["note"] for item in fact_notes(answers_leaning("DEFER"), projection)]
        self.assertEqual(
            "An operator approved an action Vigil proposed, and it has settled. "
            "Nobody in the room has been told how it went; Vigil has a turn to tell them.",
            notes[1],
        )
        self.assertFalse([note for note in notes if note.startswith("Nothing new")])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
