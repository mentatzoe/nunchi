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

    def test_the_request_validates_and_a_typed_model_does_not_get_the_memory_yet(self):
        self.deliver("z1", text="Vigil, tell me when the nightly finishes?")
        self.pipeline.observation.observe(
            delivery_id="d-v1", event=message("v1", author_id=SELF, text="Will do.", reply_to_event_id="z1"), actors=ZOE
        )
        self.pipeline.observation.observe(delivery_id="d-c1", event=message("c1", text="passed"), actors=ZOE)
        request = self.pipeline.observation.build_snapshot("c1", memory=self.pipeline.host.memory_facts("c1"))
        validate_attention_request(request)
        self.assertIn("memory", request)
        # Run 37: the memory made Jev hold back where it should speak.
        self.assertNotIn("memory", attention_state(request, "x"))

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


class RememberedTargetTests(unittest.TestCase):
    def test_the_agent_may_reply_to_a_request_it_remembers_after_it_left_the_window(self):
        # Run 38: with the request in its memory, an agent replied to it and
        # was refused because the request was no longer among the turn's events.
        from nunchi.observation import ObservationLimits

        replies = []

        def participant(**turn):
            wake = turn["wake"]
            if wake["trigger_event_id"] != "c1":
                return None
            replies.append(wake)
            return {"kind": "reply", "origin_event_id": "c1", "target_event_id": "z1", "text": "Zoe, it passed."}

        pipeline, _, transport, _ = foundation(
            model=FixtureModel("WAKE"), participant=participant, limits=ObservationLimits(snapshot_events=4)
        )
        observe = pipeline.observation.observe
        observe(delivery_id="d-z1", event=message("z1", text="Tell me when the nightly finishes?"), actors=ZOE)
        observe(delivery_id="d-v1", event=message("v1", author_id=SELF, text="I will.", reply_to_event_id="z1"), actors=ZOE)
        for index in range(6):
            observe(delivery_id=f"d-t{index}", event=message(f"t{index}", text=f"Other talk {index}."), actors=ZOE)
        pipeline.handle_delivery(
            delivery_id="d-c1",
            event=message("c1", author_id="bot:ci", text="nightly passed"),
            actors={"bot:ci": {"kind": "bot"}},
        )
        (wake,) = replies
        self.assertNotIn("z1", [event["id"] for event in wake["events"]])
        (move,) = [move for move in wake["memory"]["own_moves"] if move["kind"] == "reply"]
        self.assertEqual(("z1", "Tell me when the nightly finishes?"), (move["about_event_id"], move["about_text"]))
        ((action, _),) = transport.calls
        self.assertEqual(("reply", "z1"), (action["kind"], action["target_event_id"]))

    def test_a_target_nobody_showed_the_agent_is_still_refused(self):
        from nunchi.v2_contracts import shown_event_ids

        wake = {"events": [{"id": "c1"}], "memory": {"own_moves": [
            {"kind": "reply", "event_id": "v1", "about_event_id": "z1", "text": "I will."}]}}
        self.assertEqual({"c1", "v1", "z1"}, shown_event_ids(wake))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
