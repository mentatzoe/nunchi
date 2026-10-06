"""Attention reads the message with the participant's memory (#94 step 6).

`docs/behavior.md`: the memory holds what the agent said it would do. Until
now only the agent's turn saw it, so step 1 could hide a CI line the agent
had promised to report on once the promise left the judgment's window. The
judgment now carries the same memory the turn gets, and its prompt explains
it only when it is there.
"""

from __future__ import annotations

import unittest

from nunchi.attention_questions import attention_state
from nunchi.v2_contracts import validate_attention_request
from tests.v2.test_shared_foundation import FixtureModel, foundation, message

ZOE = {"human:zoe": {"kind": "human"}}
SELF = "discord:bot:9"


class AttentionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.pipeline, self.model, _, _ = foundation(model=FixtureModel("DEFER"))

    def deliver(self, event_id, **kwargs):
        return self.pipeline.handle_delivery(delivery_id=f"d-{event_id}", event=message(event_id, **kwargs), actors=ZOE)

    def test_the_judgment_carries_what_the_participant_said_it_would_do(self):
        self.deliver("z1", text="Vigil, tell me when the nightly finishes?")
        first_instructions, first = self.model.calls[-1]
        self.assertNotIn("memory", first)
        self.assertNotIn("observation.memory", first_instructions)
        self.pipeline.observation.observe(
            delivery_id="d-v1",
            event=message("v1", author_id=SELF, text="I'll tell you when it finishes.", reply_to_event_id="z1"),
            actors=ZOE,
        )
        self.pipeline.handle_delivery(
            delivery_id="d-c1",
            event=message("c1", author_id="bot:ci", text="nightly #812: passed"),
            actors={"bot:ci": {"kind": "bot"}},
        )
        instructions, projection = self.model.calls[-1]
        (move,) = [move for move in projection["memory"]["own_moves"] if move["kind"] == "reply"]
        self.assertEqual(("v1", "z1"), (move["event_id"], move["about_event_id"]))
        (thread,) = projection["memory"]["threads"]
        self.assertEqual(("z1", ["v1"]), (thread["event_id"], [r["event_id"] for r in thread["responses"]]))
        self.assertIn("observation.memory is vigil's own memory of this room", instructions)
        self.assertIn("a status line it said it would report on", instructions)

    def test_the_request_validates_and_a_typed_model_gets_the_memory(self):
        self.deliver("z1", text="Vigil, tell me when the nightly finishes?")
        self.pipeline.observation.observe(
            delivery_id="d-v1", event=message("v1", author_id=SELF, text="Will do.", reply_to_event_id="z1"), actors=ZOE
        )
        self.pipeline.observation.observe(delivery_id="d-c1", event=message("c1", text="passed"), actors=ZOE)
        request = self.pipeline.observation.build_snapshot("c1", memory=self.pipeline.host.memory_facts("c1"))
        validate_attention_request(request)
        self.assertEqual(request["memory"], attention_state(request, "x")["memory"])

    def test_a_recalled_message_is_judged_with_the_memory_too(self):
        self.deliver("z1", text="Vigil, tell me when the nightly finishes?")
        self.pipeline.observation.observe(
            delivery_id="d-v1", event=message("v1", author_id=SELF, text="Will do.", reply_to_event_id="z1"), actors=ZOE
        )
        self.pipeline.observation.observe(delivery_id="d-c1", event=message("c1", text="passed"), actors=ZOE)
        self.pipeline.recall("c1")
        _, projection = self.model.calls[-1]
        self.assertIn("own_moves", projection["memory"])

    def test_the_turn_and_the_judgment_see_the_same_memory(self):
        wakes = []
        pipeline, model, _, _ = foundation(model=FixtureModel("WAKE"), participant=lambda **turn: wakes.append(turn["wake"]))
        pipeline.handle_delivery(delivery_id="d-z1", event=message("z1", text="Vigil, can you check?"), actors=ZOE)
        pipeline.observation.observe(
            delivery_id="d-v1", event=message("v1", author_id=SELF, text="Checking.", reply_to_event_id="z1"), actors=ZOE
        )
        pipeline.handle_delivery(delivery_id="d-z2", event=message("z2", text="Any luck?"), actors=ZOE)
        _, projection = model.calls[-1]
        self.assertEqual(wakes[-1]["memory"], projection["memory"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
