"""Attention's reading of the room reaches the agent on every turn it takes.

Zoe, 2026-10-05 (#94, plan step 2): the reading goes with WAKE and DEFER
turns, it describes rather than orders, and a bad or empty reading never
throws away a valid judgment. Since step 4 it is written from the model's
typed answers: the model's own notes describe the moment (or, without
notes, notes rendered from its answers), and the last note is always the
kinds of response that could fit.
"""

from __future__ import annotations

import unittest

from nunchi.ack import AckPolicy, ReactionCapability
from nunchi.attention import (
    ATTENTION_JUDGMENT_SCHEMA,
    AttentionPolicy,
    participant_attention_prompt,
)
from nunchi.attention_questions import answers_leaning, moves_note
from nunchi.observation import ObservationLimits
from nunchi.participant_model import participant_tool_turn_prompt, participant_turn_prompt
from tests.v2.test_shared_foundation import (
    FixtureModel,
    RecordingTransport,
    foundation,
    message,
)


class ReadingModel(FixtureModel):
    """Answers for one disposition, with the model's own notes on the room."""

    def __init__(self, disposition, reading, *, during=None):
        super().__init__(disposition)
        self.reading = reading
        self.during = during

    def judge(self, *, instructions, projection, timeout_seconds):
        super().judge(instructions=instructions, projection=projection, timeout_seconds=timeout_seconds)
        if self.during is not None:
            self.during()
        judgment = answers_leaning(self.disposition)
        reading = self.reading(projection) if callable(self.reading) else self.reading
        if reading != "omit":
            judgment["notes"] = reading
        return judgment


def note(text, *event_ids):
    return {"note": text, "evidence_event_ids": list(event_ids)}


def moves(disposition, trigger="e1"):
    """The last note of every reading: the kinds of response that could fit."""

    return moves_note(answers_leaning(disposition), trigger)


def deliver(pipeline, event_id, text="Vigil, could you look at this?"):
    return pipeline.handle_delivery(
        delivery_id=f"d-{event_id}",
        event=message(event_id, text=text),
        actors={"human:zoe": {"kind": "human"}},
    )


class ReadingTests(unittest.TestCase):
    def turn(self, model, **kwargs):
        wakes = []
        pipeline, _, _, receipts = foundation(
            model=model,
            participant=lambda **turn: wakes.append(turn["wake"]) or None,
            **kwargs,
        )
        if model.during is not None:
            model.during = model.during(pipeline)
        outcome = deliver(pipeline, "e1")
        return outcome.opportunities[0], wakes, receipts

    def test_an_empty_reading_never_discards_a_judgment(self):
        for disposition in ("SUPPRESS", "ACK", "WAKE", "DEFER"):
            for empty in (None, [], "not a list"):
                with self.subTest(disposition=disposition, reading=empty):
                    opportunity, _, _ = self.turn(ReadingModel(disposition, empty))
                    self.assertEqual("ok", opportunity.decision_status)

    def test_a_bad_item_is_dropped_and_the_rest_reach_the_agent(self):
        reading = [
            note("Zoe asked Vigil directly.", "e1"),
            note("Cites a message the model never saw.", "e1", "made-up"),
            {"note": "", "evidence_event_ids": ["e1"]},
            {"note": "No citation.", "evidence_event_ids": []},
            {"note": "Extra field.", "evidence_event_ids": ["e1"], "order": "speak"},
            note("A repeated citation is kept once.", "e1", "e1"),
        ]
        opportunity, wakes, _ = self.turn(ReadingModel("WAKE", reading))
        self.assertEqual(("ok", "WAKE"), (opportunity.decision_status, opportunity.effective_disposition))
        (wake,) = wakes
        self.assertEqual(
            [note("Zoe asked Vigil directly.", "e1"), note("A repeated citation is kept once.", "e1"), moves("WAKE")],
            wake["attention"]["advice"],
        )

    def test_a_reading_is_bounded(self):
        reading = [note(f"item {index} " + "x" * 500, "e1") for index in range(6)]
        _, wakes, _ = self.turn(ReadingModel("WAKE", reading))
        advice = wakes[0]["attention"]["advice"]
        self.assertEqual(4, len(advice))
        self.assertTrue(all(len(item["note"]) == 400 for item in advice[:3]))
        self.assertEqual(moves("WAKE"), advice[3])

    def test_a_defer_turn_carries_the_reading(self):
        reading = [note("Zoe asked something nobody has answered yet; speaking could fit.", "e1")]
        opportunity, wakes, _ = self.turn(ReadingModel("DEFER", reading))
        self.assertEqual("DEFER", opportunity.effective_disposition)
        (wake,) = wakes
        self.assertEqual("DEFER", wake["attention"]["source"])
        self.assertEqual(reading + [moves("DEFER")], wake["attention"]["advice"])
        self.assertEqual(["e1"], wake["attention"]["evidence_event_ids"])
        self.assertEqual("e1", wake["attention"]["judged_through_event_id"])

    def test_an_ack_the_agent_takes_carries_the_reading(self):
        # Without a reaction capability, ACK widens to a DEFER turn for the
        # agent; the reading says why a nod could fit.
        reading = [note("Zoe shared an update; a quick mhm could show Vigil is following.", "e1")]
        opportunity, wakes, _ = self.turn(ReadingModel("ACK", reading))
        self.assertEqual("DEFER", opportunity.effective_disposition)
        self.assertEqual(reading + [moves("ACK")], wakes[0]["attention"]["advice"])

    def test_by_default_the_agent_sends_its_own_mhm(self):
        # Zoe, 2026-10-05: every visible move is the agent's own. Even where
        # the platform could take Nunchi's nod, an ACK judgment is the
        # agent's turn, with the reading saying why a nod could fit.
        self.assertFalse(AckPolicy().enabled)
        transport = RecordingTransport(
            capability=ReactionCapability(
                supported=True,
                authenticated=True,
                operations=("add",),
                reactions=("👂",),
                permissions_revision="test:v1",
            )
        )
        reading = [note("Zoe shared an update; a quick mhm could show Vigil is following.", "e1")]
        opportunity, wakes, _ = self.turn(ReadingModel("ACK", reading), transport=transport)
        self.assertEqual("DEFER", opportunity.effective_disposition)
        self.assertEqual("DEFER", wakes[0]["attention"]["source"])
        self.assertEqual(reading + [moves("ACK")], wakes[0]["attention"]["advice"])
        self.assertEqual([], transport.calls)

    def test_a_suppressed_moment_reaches_no_one(self):
        opportunity, wakes, _ = self.turn(ReadingModel("SUPPRESS", [note("Addressed to Castor.", "e1")]))
        self.assertEqual("SUPPRESS", opportunity.effective_disposition)
        self.assertEqual([], wakes)

    def test_an_error_fallback_carries_no_reading(self):
        model = FixtureModel(fail=True)
        model.during = None
        opportunity, wakes, _ = self.turn(model)
        self.assertEqual("ERROR_FALLBACK", opportunity.effective_disposition)
        self.assertEqual({"source": "ERROR_FALLBACK"}, wakes[0]["attention"])

    def test_an_item_whose_messages_left_the_window_is_dropped_alone(self):
        # Messages arrive while attention runs, pushing the oldest out of the
        # agent's fresh window. Only the item that cites it is dropped.
        def newer_messages_arrive(pipeline):
            def arrive():
                for index in range(2, 7):
                    pipeline.observation.observe(
                        delivery_id=f"d-n{index}",
                        event=message(f"n{index}", text=f"later message {index}"),
                        actors={"human:zoe": {"kind": "human"}},
                    )

            return arrive

        wakes = []
        pipeline, _, _, _ = foundation(
            model=ReadingModel("WAKE", "omit"),
            participant=lambda **turn: wakes.append(turn["wake"]) or None,
            limits=ObservationLimits(snapshot_events=3),
        )
        for event_id in ("o1", "o2"):
            pipeline.observation.observe(
                delivery_id=f"d-{event_id}",
                event=message(event_id, text="earlier"),
                actors={"human:zoe": {"kind": "human"}},
            )
        model = pipeline.attention.model
        model.reading = [note("Zoe raised this earlier.", "o1"), note("Zoe asked Vigil directly.", "e1")]
        model.during = newer_messages_arrive(pipeline)
        deliver(pipeline, "e1")
        (wake,) = wakes
        self.assertNotIn("o1", [event["id"] for event in wake["events"]])
        self.assertEqual([note("Zoe asked Vigil directly.", "e1"), moves("WAKE")], wake["attention"]["advice"])
        self.assertEqual("e1", wake["attention"]["judged_through_event_id"])

    def test_without_notes_the_reading_is_written_from_the_answers(self):
        _, wakes, _ = self.turn(ReadingModel("WAKE", "omit"))
        self.assertEqual(
            [
                note("The judged message is addressed to you (0.80).", "e1"),
                note("You may know something useful that nobody has said yet (0.80).", "e1"),
                moves("WAKE"),
            ],
            wakes[0]["attention"]["advice"],
        )

    def test_a_reading_that_points_to_the_answer_cites_it(self):
        def answered(pipeline):
            pipeline.observation.observe(
                delivery_id="d-a1",
                event=message("a1", author_id="human:castor", text="It was the expired cert."),
                actors={"human:castor": {"display_name": "Castor", "kind": "human"}},
            )

        class Answered(ReadingModel):
            def judge(self, **kwargs):
                answers = super().judge(**kwargs)
                answers.update(answered=0.9, answered_by="a1")
                answers.pop("notes", None)
                return answers

        wakes = []
        pipeline, _, _, _ = foundation(
            model=Answered("DEFER", "omit"),
            participant=lambda **turn: wakes.append(turn["wake"]) or None,
        )
        answered(pipeline)
        deliver(pipeline, "e1")
        self.assertIn(
            note("Castor seems to have answered or handled it already, in a1 (0.90).", "e1", "a1"),
            wakes[0]["attention"]["advice"],
        )


class ReadingLengthTests(unittest.TestCase):
    """Zoe, 2026-10-05: the reading's length is configurable, to weigh it
    against latency and fit."""

    def test_the_policy_bounds_the_length(self):
        self.assertEqual((4, 400), (AttentionPolicy().reading_items, AttentionPolicy().reading_note_chars))
        AttentionPolicy(reading_items=0, reading_note_chars=40)
        for bad in ({"reading_items": 5}, {"reading_items": -1}, {"reading_items": True},
                    {"reading_note_chars": 39}, {"reading_note_chars": 401}, {"reading_note_chars": 120.0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                AttentionPolicy(**bad)

    def test_the_prompt_asks_for_the_configured_length(self):
        profile = foundation()[0].attention.profile
        # The last note is always the kinds of response, written from the
        # answers, so the model is asked for one note fewer.
        short = participant_attention_prompt(profile, reading_items=3, reading_note_chars=160)
        self.assertIn("at most 2 {note, evidence_event_ids} items", short)
        self.assertIn("one short sentence (at most 160 characters)", short)
        two = participant_attention_prompt(profile, reading_items=2, reading_note_chars=300)
        self.assertIn("at most 1 {note, evidence_event_ids} item,", two)
        for items in (1, 0):
            with self.subTest(items=items):
                self.assertNotIn("notes", participant_attention_prompt(profile, reading_items=items))

    def test_the_engine_keeps_the_reading_within_the_configured_length(self):
        reading = [note(f"Observation {index}: " + "y" * 120, "e1") for index in range(4)]
        wakes = []
        model = ReadingModel("WAKE", reading)
        pipeline, _, _, _ = foundation(
            model=model,
            participant=lambda **turn: wakes.append(turn["wake"]) or None,
            policy=AttentionPolicy(reading_items=2, reading_note_chars=60),
        )
        deliver(pipeline, "e1")
        advice = wakes[0]["attention"]["advice"]
        self.assertEqual(2, len(advice))
        self.assertTrue(all(len(item["note"]) <= 60 for item in advice))
        self.assertTrue(advice[1]["note"].startswith("Kinds of response that could fit"))
        self.assertIn("at most 1", model.calls[0][0])

    def test_no_reading_asked_means_none_delivered(self):
        wakes = []
        pipeline, _, _, _ = foundation(
            model=ReadingModel("WAKE", [note("Zoe asked Vigil directly.", "e1")]),
            participant=lambda **turn: wakes.append(turn["wake"]) or None,
            policy=AttentionPolicy(reading_items=0),
        )
        deliver(pipeline, "e1")
        self.assertEqual({"source": "WAKE"}, wakes[0]["attention"])


class ReadingPromptTests(unittest.TestCase):
    def test_attention_asks_for_a_descriptive_reading_on_every_disposition(self):
        profile = foundation()[0].attention.profile
        prompt = participant_attention_prompt(profile)
        self.assertIn("notes is your reading of the room", prompt)
        self.assertIn("never give orders", prompt)
        self.assertIn("attribute", prompt)
        self.assertNotIn("only for WAKE", prompt)

    def test_the_schema_bounds_the_reading(self):
        notes = ATTENTION_JUDGMENT_SCHEMA["properties"]["notes"]
        self.assertEqual(3, notes["maxItems"])
        self.assertEqual(400, notes["items"]["properties"]["note"]["maxLength"])

    def test_every_turn_prompt_frames_the_reading_as_a_recommendation(self):
        profile = foundation()[0].attention.profile
        for prompt in (
            participant_turn_prompt(profile),
            participant_tool_turn_prompt(profile, tools={"send": "send"}),
        ):
            self.assertIn("recommendation with reasons, not an order", prompt)
            self.assertIn("judged_through_event_id", prompt)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
