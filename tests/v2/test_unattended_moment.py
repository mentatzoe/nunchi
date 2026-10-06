"""Messages that arrive mid-turn are read with the newest, as one moment.

Zoe, 2026-10-06 (#94 step 6): a person catching up reads the newest message
and glances back at what they missed. Run 45 showed why: Sam asked Vigil a
question while Vigil was answering Zoe, Zoe then said "Thanks!", and only her
thanks was judged as a moment, so Vigil mostly left Sam unanswered. Now the
judgment of the newest message lists the messages it replaced, newest first,
and answers one more question: which of them still calls for the participant.
That message is never hidden, the reading names it, and the turn lists them.
"""

from __future__ import annotations

import unittest

from nunchi.attention import attention_judgment_schema, participant_attention_prompt
from nunchi.attention_questions import (
    answers_leaning,
    attention_questions,
    attention_state,
    classifier_disposition,
    reading_from_answers,
    validate_answers,
)
from nunchi.participant_model import ParticipantTurnProtocol
from nunchi.v2_contracts import (
    UNATTENDED_POINTER,
    validate_attention_decision,
    validate_attention_request,
    validate_participant_wake,
)
from tests.v2.test_operator_protocol import PROFILE as TURN_PROFILE, opportunity
from tests.v2.test_shared_foundation import FixtureModel, foundation, message

ACTORS = {"human:zoe": {"kind": "human"}, "human:sam": {"kind": "human"}}


class PointingModel(FixtureModel):
    """On the merged moment, leans one way and names a message that still calls."""

    def __init__(self, disposition="DEFER", pointer="s1"):
        super().__init__("DEFER")
        self.merged, self.pointer = disposition, pointer

    def judge(self, *, instructions, projection, timeout_seconds):
        answers = super().judge(instructions=instructions, projection=projection, timeout_seconds=timeout_seconds)
        if projection.get("unattended_event_ids"):
            answers = dict(answers_leaning(self.merged), **{UNATTENDED_POINTER: self.pointer})
        return answers


class UnattendedMomentTests(unittest.TestCase):
    def setUp(self):
        self.wakes = []
        self.during = []

    def participant(self, pipeline):
        def take(**turn):
            self.wakes.append(turn["wake"])
            while self.during:
                event_id, author_id, text = self.during.pop(0)
                pipeline.observe_and_offer(
                    delivery_id=f"d-{event_id}", event=message(event_id, author_id, text), actors=ACTORS
                )
            return None

        return take

    def run_scene(self, model):
        pipeline, _, _, _ = foundation(model=model)
        pipeline.host.participant = self.participant(pipeline)
        self.judged = []
        judge = pipeline.attention.judge

        def capture(request, **kwargs):
            decision = judge(request, **kwargs)
            self.judged.append((request, decision))
            return decision

        pipeline.attention.judge = capture
        self.during = [("s1", "human:sam", "Vigil, is staging up?"), ("z2", "human:zoe", "Thanks!")]
        pipeline.handle_delivery(
            delivery_id="d-z1", event=message("z1", text="Vigil, can you check the build?"), actors=ACTORS
        )
        return pipeline

    def test_the_newest_is_judged_with_what_arrived_while_the_participant_was_busy(self):
        model = FixtureModel("DEFER")
        self.run_scene(model)
        instructions, projection = model.calls[-1]
        self.assertEqual(("z2", ["s1"]), (projection["trigger_event_id"], projection["unattended_event_ids"]))
        self.assertIn("observation.unattended_event_ids lists messages that arrived while", instructions)
        self.assertIn(f"- {UNATTENDED_POINTER}:", instructions)
        # The first judgment, of an ordinary new message, hears none of it.
        first_instructions, first = model.calls[0]
        self.assertNotIn("unattended_event_ids", first)
        self.assertNotIn(UNATTENDED_POINTER, first_instructions)
        wake = self.wakes[-1]
        self.assertEqual(["s1"], wake["unattended_event_ids"])
        validate_participant_wake(wake)
        self.assertNotIn("unattended_event_ids", self.wakes[0])

    def test_the_message_that_still_calls_is_never_hidden_and_the_reading_names_it(self):
        self.run_scene(PointingModel("SUPPRESS"))
        _, decision = self.judged[-1]
        self.assertEqual("s1", decision["answers"][UNATTENDED_POINTER])
        self.assertNotEqual("SUPPRESS", decision["classifier_disposition"])
        wake = self.wakes[-1]
        first = wake["attention"]["advice"][0]
        self.assertEqual(["s1"], first["evidence_event_ids"])
        self.assertIn("arrived while you were busy", first["note"])

    def test_the_turn_says_the_moment_is_more_than_its_trigger(self):
        self.run_scene(FixtureModel("DEFER"))
        allowed = opportunity()
        later = ParticipantTurnProtocol(profile=TURN_PROFILE, wake=self.wakes[-1], opportunity=allowed)
        self.assertIn("wake.unattended_event_ids lists them, newest first", later.instructions)
        self.assertIn("s1", later.visible_event_ids)
        first = ParticipantTurnProtocol(profile=TURN_PROFILE, wake=self.wakes[0], opportunity=allowed)
        self.assertNotIn("unattended_event_ids", first.instructions)

    def test_a_lone_message_mid_turn_has_nothing_unattended(self):
        model = FixtureModel("DEFER")
        pipeline, _, _, _ = foundation(model=model)
        pipeline.host.participant = self.participant(pipeline)
        self.during = [("z2", "human:zoe", "Also the nightly?")]
        pipeline.handle_delivery(delivery_id="d-z1", event=message("z1"), actors=ACTORS)
        self.assertNotIn("unattended_event_ids", model.calls[-1][1])

    def test_the_typed_route_gets_the_question_and_the_messages(self):
        seen = {}

        class Typed:
            name, provider, model_id = "typed", "fixture", "typed-v1"

            def answer(self, *, questions, state, timeout_seconds):
                seen["questions"], seen["state"] = questions, state
                return dict(answers_leaning("DEFER"), **({UNATTENDED_POINTER: "s1"} if UNATTENDED_POINTER in questions else {}))

        self.run_scene(Typed())
        self.assertEqual(["s1"], seen["questions"][UNATTENDED_POINTER]["candidates"])
        self.assertEqual(["s1"], seen["state"]["unattended_message_ids"])
        self.assertEqual("s1", self.judged[-1][1]["answers"][UNATTENDED_POINTER])


class UnattendedAnswerTests(unittest.TestCase):
    def test_the_pointer_is_kept_only_for_an_unattended_message(self):
        raw = dict(answers_leaning("DEFER"), **{UNATTENDED_POINTER: "s1"})
        kept = validate_answers(raw, event_ids={"s1", "z2"}, trigger_event_id="z2", unattended=("s1",))
        self.assertEqual("s1", kept[UNATTENDED_POINTER])
        for unattended in ((), ("s2",)):
            with self.subTest(unattended=unattended):
                dropped = validate_answers(raw, event_ids={"s1", "z2"}, trigger_event_id="z2", unattended=unattended)
                self.assertNotIn(UNATTENDED_POINTER, dropped)
        with self.assertRaises(ValueError):
            validate_answers(dict(raw, **{UNATTENDED_POINTER: 3}), event_ids={"s1"}, trigger_event_id="z2")

    def test_step_one_never_hides_a_message_that_still_calls(self):
        quiet = answers_leaning("SUPPRESS")
        self.assertEqual("SUPPRESS", classifier_disposition(quiet))
        self.assertEqual("DEFER", classifier_disposition(dict(quiet, **{UNATTENDED_POINTER: "s1"})))

    def test_the_question_and_schema_appear_only_with_unattended_messages(self):
        self.assertNotIn(UNATTENDED_POINTER, attention_questions("Vigil"))
        self.assertIn(UNATTENDED_POINTER, attention_questions("Vigil", unattended=True))
        self.assertNotIn(UNATTENDED_POINTER, attention_judgment_schema()["properties"])
        schema = attention_judgment_schema(unattended=True)
        self.assertIn(UNATTENDED_POINTER, schema["required"])
        from nunchi.attention import ATTENTION_JUDGMENT_SCHEMA

        self.assertNotIn(UNATTENDED_POINTER, ATTENTION_JUDGMENT_SCHEMA["required"])
        from nunchi.attention import ParticipantProfile

        profile = ParticipantProfile(
            profile_id="p", participant_id="vigil", actor_id="a", instructions="i", provenance="t", sha256="0" * 64
        )
        self.assertNotIn(UNATTENDED_POINTER, participant_attention_prompt(profile))

    def test_the_reading_names_the_message_first_on_both_routes(self):
        projection = {
            "trigger_event_id": "z2",
            "self": {"actor_id": "bot:9", "participant_id": "vigil"},
            "actors": {"human:sam": {"display_name": "Sam"}},
            "events": [{"id": "s1", "author_id": "human:sam"}, {"id": "z2", "author_id": "human:zoe"}],
        }
        answers = dict(answers_leaning("DEFER"), **{UNATTENDED_POINTER: "s1"})
        for notes in (None, [{"note": "Zoe thanks Vigil.", "evidence_event_ids": ["z2"]}]):
            with self.subTest(model_notes=bool(notes)):
                reading = reading_from_answers(answers, projection, notes=notes)
                self.assertEqual("Sam's message s1 arrived while you were busy with your previous turn, and it still calls for you.", reading[0]["note"])
                self.assertTrue(reading[-1]["note"].startswith("Kinds of response"))


class UnattendedContractTests(unittest.TestCase):
    def setUp(self):
        pipeline, _, _, _ = foundation()
        observe = pipeline.observation.observe
        observe(delivery_id="d-z1", event=message("z1"), actors=ACTORS)
        observe(delivery_id="d-s1", event=message("s1", "human:sam"), actors=ACTORS)
        observe(delivery_id="d-s2", event=message("s2", "human:sam"), actors=ACTORS)
        observe(delivery_id="d-v1", event=message("v1", "discord:bot:9"), actors=ACTORS)
        observe(delivery_id="d-z2", event=message("z2"), actors=ACTORS)
        self.observation = pipeline.observation

    def test_the_snapshot_lists_them_newest_first_and_drops_what_does_not_qualify(self):
        request = self.observation.build_snapshot("z2", unattended=("s1", "v1", "z2", "gone", "s2"))
        self.assertEqual(["s2", "s1"], request["unattended_event_ids"])
        self.assertNotIn("unattended_event_ids", self.observation.build_snapshot("z2", unattended=("v1",)))

    def test_the_request_rejects_a_wrong_list(self):
        request = self.observation.build_snapshot("z2", unattended=("s1", "s2"))
        for bad in (["s1", "s2"], ["z2"], ["v1"], ["missing"], [], ["s2", "s2"], ["s2", "s1", "z1", "s1"]):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                validate_attention_request(dict(request, unattended_event_ids=bad))

    def test_the_decision_may_only_name_an_unattended_message(self):
        scene = UnattendedMomentTests()
        scene.wakes, scene.during = [], []
        scene.run_scene(PointingModel("DEFER"))
        request, decision = scene.judged[-1]
        validate_attention_decision(decision, request=request)
        wrong = dict(decision, answers=dict(decision["answers"], **{UNATTENDED_POINTER: "z1"}))
        with self.assertRaises(Exception):
            validate_attention_decision(wrong, request=request)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
