"""Steps 1 and 2 of reading the room are typed questions (#94, step 4).

Step 1 suppresses only what is more likely not conversation; anything else
gives the participant a turn with a reading written from the answers. Any
model answers the same questions: a chat model as one JSON object, a typed
decision model natively. These tests prove the mapping and the plumbing;
whether models answer well is measured by behavior runs.
"""

from __future__ import annotations

import math
import unittest

from nunchi.attention import AttentionPolicy, participant_attention_prompt
from nunchi.attention_questions import (
    QUESTION_IDS,
    answers_leaning,
    classifier_disposition,
    top_move,
    validate_answers,
)
from nunchi.errors import ValidationError
from nunchi.v2_contracts import validate_attention_decision
from tests.v2.test_shared_foundation import foundation, message


def leaning(disposition="WAKE", **changes):
    answers = answers_leaning(disposition)
    answers.update(changes)
    return answers


class MappingTests(unittest.TestCase):
    def test_each_move_maps_to_a_disposition(self):
        for move, expected in (("speak", "WAKE"), ("mhm", "ACK"), ("wait", "DEFER"), ("stay_quiet", "DEFER")):
            with self.subTest(move=move):
                answers = leaning(move={key: 1.0 if key == move else 0.0 for key in ("speak", "mhm", "wait", "stay_quiet")})
                self.assertEqual(expected, classifier_disposition(answers))

    def test_step_one_suppresses_only_what_is_not_conversation(self):
        self.assertEqual("SUPPRESS", classifier_disposition(leaning(conversation=0.49)))
        self.assertNotEqual("SUPPRESS", classifier_disposition(leaning(conversation=0.5)))
        # A question to someone else is still conversation: the participant
        # gets a turn and decides, with the reading saying who was asked.
        to_castor = leaning(
            "DEFER",
            addressee={"participant": 0, "room": 0, "someone_else": 1, "nobody": 0},
            move={"speak": 0, "mhm": 0, "wait": 0, "stay_quiet": 1},
        )
        self.assertEqual("DEFER", classifier_disposition(to_castor))

    def test_ties_go_to_paying_attention(self):
        self.assertEqual("speak", top_move(leaning(move={"speak": 0.5, "mhm": 0, "wait": 0.5, "stay_quiet": 0})))
        self.assertEqual("mhm", top_move(leaning(move={"speak": 0, "mhm": 0.5, "wait": 0, "stay_quiet": 0.5})))


class ValidationTests(unittest.TestCase):
    def check(self, answers, *, event_ids=frozenset({"e1", "a1"})):
        return validate_answers(answers, event_ids=set(event_ids), trigger_event_id="e1")

    def test_choices_are_normalized(self):
        result = self.check(leaning(move={"speak": 2 / 10, "mhm": 0, "wait": 2 / 10, "stay_quiet": 0}))
        self.assertEqual({"speak": 0.5, "mhm": 0.0, "wait": 0.5, "stay_quiet": 0.0}, result["move"])
        result = self.check(leaning(move={"speak": 0, "mhm": 0, "wait": 0, "stay_quiet": 0}))
        self.assertEqual({0.25}, set(result["move"].values()))
        # A choice that leaves an option out gives it nothing.
        result = self.check(leaning(addressee={"room": 1}))
        self.assertEqual(1.0, result["addressee"]["room"])

    def test_a_bad_pointer_is_dropped_alone(self):
        self.assertEqual("a1", self.check(leaning(answered=0.9, answered_by="a1"))["answered_by"])
        for pointer in ("made-up", "e1", None):
            with self.subTest(pointer=pointer):
                self.assertNotIn("answered_by", self.check(leaning(answered_by=pointer)))

    def test_a_plainly_stated_yes_or_no_is_read_as_its_probability(self):
        # Chat models asked for a probability sometimes answer a yes/no
        # question as a boolean, a word, or a yes/no split (#114 run).
        for written, expected in (
            (True, 1.0),
            (False, 0.0),
            ("no", 0.0),
            (" Yes ", 1.0),
            ({"yes": 0.2, "no": 0.6}, 0.25),
            ({"yes": 0, "no": 0}, 0.5),
        ):
            with self.subTest(written=written):
                result = self.check(leaning(answered=written, conversation=written))
                self.assertEqual((expected, expected), (result["answered"], result["conversation"]))

    def test_malformed_answers_are_rejected(self):
        missing = leaning()
        del missing["mid_thought"]
        extra = leaning(disposition="WAKE")
        extra["legacy_verdict_confidences"] = {"PASS": 0, "ACK": 0, "ASK": 0, "SPEAK": 1}
        for bad in (
            [],
            missing,
            extra,
            leaning(conversation=1.5),
            leaning(conversation=-0.1),
            leaning(conversation=math.nan),
            leaning(adds_something="high"),
            leaning(answered={"probability": 0.9}),
            leaning(answered={"yes": 0.7}),
            leaning(answered={"yes": 2, "no": 0}),
            leaning(move=[0.7, 0.3]),
            leaning(move={"speak": 1, "shout": 0}),
            leaning(answered_by=7),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.check(bad)


class TypedModel:
    """A typed decision model: it answers the questions natively."""

    name = "participant-attention"
    provider = "fixture-typed"
    model_id = "fixture/typed"

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def judge(self, **kwargs):  # pragma: no cover - the engine must not call it
        raise AssertionError("a typed model is never given the chat prompt")

    def answer(self, *, questions, state, timeout_seconds):
        self.calls.append((questions, state))
        return self.answers


class RouteTests(unittest.TestCase):
    def deliver(self, model, **kwargs):
        wakes = []
        pipeline, _, _, receipts = foundation(
            model=model,
            participant=lambda **turn: wakes.append(turn["wake"]) or None,
            **kwargs,
        )
        pipeline.observation.observe(
            delivery_id="d-a1",
            event=message("a1", author_id="human:castor", text="Done already."),
            actors={"human:castor": {"display_name": "Castor", "kind": "human"}},
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d-e1",
            event=message("e1", text="Vigil, could you look at this?"),
            actors={"human:zoe": {"kind": "human"}},
        )
        return outcome.opportunities[0], wakes, pipeline

    def test_a_typed_model_gets_the_questions_and_the_state(self):
        model = TypedModel(leaning("WAKE", answered=0.2, answered_by="a1"))
        opportunity, wakes, pipeline = self.deliver(model)
        (questions, state), = model.calls
        self.assertEqual(list(QUESTION_IDS), list(questions))
        self.assertEqual(["a1"], questions["answered_by"]["candidates"])
        self.assertEqual(pipeline.attention.profile.instructions, state["participant"]["instructions"])
        self.assertEqual("e1", state["judged_message_id"])
        self.assertEqual("WAKE", opportunity.effective_disposition)
        self.assertEqual("WAKE", wakes[0]["attention"]["source"])

    def test_the_decision_carries_the_answers(self):
        model = TypedModel(leaning("DEFER", answered=0.9, answered_by="a1"))
        decisions = []
        pipeline, _, _, _ = foundation(model=model, participant=lambda **turn: None)
        judge = pipeline.attention.judge
        pipeline.attention.judge = lambda request, **kwargs: decisions.append(judge(request, **kwargs)) or decisions[-1]
        pipeline.observation.observe(
            delivery_id="d-a1",
            event=message("a1", author_id="human:castor", text="Done already."),
            actors={"human:castor": {"display_name": "Castor", "kind": "human"}},
        )
        pipeline.handle_delivery(
            delivery_id="d-e1",
            event=message("e1", text="Vigil, could you look at this?"),
            actors={"human:zoe": {"kind": "human"}},
        )
        (decision,) = decisions
        self.assertEqual("DEFER", decision["effective_disposition"])
        self.assertEqual("a1", decision["answers"]["answered_by"])
        self.assertEqual(["e1", "a1"], decision["evidence_event_ids"])
        self.assertIn("answered_by a1", decision["reasons"])
        self.assertIn(
            "Castor seems to have answered or handled it already, in a1 (0.90).",
            [item["note"] for item in decision["attention_advice"]],
        )

    def test_a_near_call_on_conversation_is_widened_to_defer(self):
        for conversation, expected in ((0.47, "DEFER"), (0.3, "SUPPRESS")):
            with self.subTest(conversation=conversation):
                opportunity, wakes, _ = self.deliver(TypedModel(leaning("SUPPRESS", conversation=conversation)))
                self.assertEqual(expected, opportunity.effective_disposition)
                self.assertEqual(expected != "SUPPRESS", bool(wakes))

    def test_the_chat_prompt_asks_every_question(self):
        profile = foundation()[0].attention.profile
        prompt = participant_attention_prompt(profile)
        for key in QUESTION_IDS:
            self.assertIn(f"- {key}: ", prompt)
        self.assertIn('wrong "not conversation" hides the moment', prompt)
        self.assertIn("This holds whoever it is addressed to.", prompt)
        self.assertIn('"answered": p, "answered_by": "<message id>" or null', prompt)
        self.assertIn('never true, false, "yes", or "no"', prompt)


class ContractTests(unittest.TestCase):
    def decision(self, **changes):
        doc = {
            "status": "ok",
            "request_id": "r1",
            "classifier_disposition": "WAKE",
            "effective_disposition": "WAKE",
            "routing_audit": {"valve": "none", "override_cause": "none", "margin_status": "active"},
            "reasons": ["conversation 0.95"],
            "evidence_event_ids": ["e1"],
            "classifier": {"name": "participant-attention"},
            "answers": {key: value for key, value in answers_leaning("WAKE").items() if value is not None},
        }
        doc.update(changes)
        return doc

    def test_an_ok_decision_carries_typed_answers(self):
        validate_attention_decision(self.decision())
        with_pointer = self.decision(answers={**self.decision()["answers"], "answered_by": "a1"})
        validate_attention_decision(with_pointer)

    def test_the_old_confidence_vector_is_gone(self):
        legacy = self.decision(legacy_verdict_confidences={"PASS": 0, "ACK": 0, "ASK": 0, "SPEAK": 1})
        for bad in (legacy, {k: v for k, v in self.decision().items() if k != "answers"}):
            with self.subTest(keys=sorted(bad)), self.assertRaises(ValidationError):
                validate_attention_decision(bad)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
