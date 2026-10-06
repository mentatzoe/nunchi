"""Nunchi looks again at a moment after the room stays quiet (#94 step 6).

`docs/behavior.md`: a participant who waits for the addressee, or for the
speaker to finish, also notices when nobody answers. When a judgment's most
likely move is to wait, the pipeline arms one look again. If nothing new is
said for the pause, it judges the same message again as a ``pause``, and the
participant may get a turn that knows it is looking again. These tests prove
when it looks again and when it does not; whether models then join well is
measured by the behavior eval's pause moments.
"""

from __future__ import annotations

import threading
import unittest

from nunchi.pipeline import AsyncDeliveryLane, NunchiV2Pipeline
from nunchi.v2_contracts import validate_attention_request, validate_participant_wake
from tests.v2.test_shared_foundation import FixtureModel, foundation, message

ZOE = {"human:zoe": {"kind": "human"}}


class LookAgainTests(unittest.TestCase):
    def setUp(self):
        self.wakes = []
        self.replies = []

    def participant(self, **turn):
        self.wakes.append(turn["wake"])
        return self.replies.pop(0) if self.replies else None

    def pipeline(self, disposition="DEFER"):
        pipeline, model, transport, _ = foundation(model=FixtureModel(disposition), participant=self.participant)
        return pipeline, model, transport

    def deliver(self, pipeline, event_id, text="Castor, how does the retry backoff work?"):
        return pipeline.handle_delivery(delivery_id=f"d-{event_id}", event=message(event_id, text=text), actors=ZOE)

    def test_a_moment_to_wait_on_is_judged_again_as_a_pause(self):
        pipeline, model, _ = self.pipeline()
        self.deliver(pipeline, "q1")
        due = pipeline.look_again_due()
        self.assertIsNotNone(due)
        self.assertGreater(due, 290)
        # Not yet due: nothing happens.
        self.assertIsNone(pipeline.look_again())
        self.assertEqual(1, len(model.calls))
        (outcome,) = pipeline.look_again(now=True)
        self.assertEqual("q1", outcome.anchor_event_id)
        _, projection = model.calls[-1]
        self.assertEqual("pause", projection["occasion"])
        self.assertNotIn("occasion", model.calls[0][1])
        wake = self.wakes[-1]
        self.assertEqual(("q1", "pause"), (wake["trigger_event_id"], wake["occasion"]))
        validate_participant_wake(wake)
        self.assertNotIn("occasion", self.wakes[0])

    def test_it_looks_again_once_per_quiet_stretch(self):
        pipeline, model, _ = self.pipeline()
        self.deliver(pipeline, "q1")
        pipeline.look_again(now=True)
        # The second judgment also read it as a wait; it does not re-arm.
        self.assertIsNone(pipeline.look_again_due())
        self.assertIsNone(pipeline.look_again(now=True))
        self.assertEqual(2, len(model.calls))

    def test_a_new_message_ends_the_quiet(self):
        pipeline, model, _ = self.pipeline()
        self.deliver(pipeline, "q1")
        pipeline.scheduler.cancel()  # keep the next delivery from being judged
        pipeline.observe_and_offer(delivery_id="d-c1", event=message("c1", text="On it."), actors=ZOE)
        self.assertIsNone(pipeline.look_again_due())
        self.assertIsNone(pipeline.look_again(now=True))

    def test_only_a_judgment_to_wait_arms_it(self):
        for disposition in ("WAKE", "ACK", "SUPPRESS"):
            with self.subTest(disposition=disposition):
                pipeline, _, _ = self.pipeline(disposition)
                self.deliver(pipeline, "q1")
                self.assertIsNone(pipeline.look_again_due())

    def test_a_later_judgment_not_to_wait_disarms_it(self):
        pipeline, model, _ = self.pipeline()
        self.deliver(pipeline, "q1")
        model.disposition = "WAKE"
        self.deliver(pipeline, "q2", "Never mind, found it.")
        self.assertIsNone(pipeline.look_again_due())

    def test_nothing_to_look_again_for_once_the_participant_has_spoken(self):
        pipeline, _, transport = self.pipeline()
        self.replies.append({"kind": "message", "origin_event_id": "q1", "text": "Exponential with jitter."})
        self.deliver(pipeline, "q1")
        self.assertEqual(1, len(transport.calls))
        self.assertIsNone(pipeline.look_again_due())

    def test_a_participant_that_stayed_quiet_keeps_it_armed(self):
        pipeline, _, transport = self.pipeline()
        self.replies.append({"kind": "silence", "origin_event_id": "q1", "why": "Waiting for Castor."})
        self.deliver(pipeline, "q1")
        self.assertEqual([], transport.calls)
        self.assertIsNotNone(pipeline.look_again_due())
        pipeline.look_again(now=True)
        (silence,) = [move for move in self.wakes[-1]["memory"]["own_moves"] if move["kind"] == "silence"]
        self.assertEqual("Waiting for Castor.", silence["why"])

    def test_a_look_again_never_displaces_a_newer_message(self):
        pipeline, model, _ = self.pipeline()
        self.deliver(pipeline, "q1")
        # A newer message is being judged when the pause runs out.
        active = pipeline.scheduler.offer("q1")
        pipeline.observation.observe(delivery_id="d-c1", event=message("c1", text="On it."), actors=ZOE)
        pipeline.scheduler.offer("c1")
        pipeline._look_again = ("q1", 0.0)
        self.assertIsNone(pipeline.look_again())
        successor = pipeline.scheduler.complete(active)
        self.assertEqual("c1", successor.anchor_event_id)
        self.assertEqual(1, len(model.calls))

    def test_a_message_that_arrives_during_the_judgment_ends_the_quiet(self):
        pipeline, model, _ = self.pipeline()
        judge = model.judge

        def judge_while_castor_answers(**kwargs):
            if len(model.calls) == 0:
                pipeline.observe_and_offer(delivery_id="d-c1", event=message("c1", text="On it."), actors=ZOE)
                answers = judge(**kwargs)
                model.disposition = "WAKE"
                return answers
            return judge(**kwargs)

        model.judge = judge_while_castor_answers
        self.deliver(pipeline, "q1")
        # q1 was read as a wait, but c1 is newer, and c1 is not one to wait on.
        self.assertEqual(["q1", "c1"], [call[1]["trigger_event_id"] for call in model.calls])
        self.assertIsNone(pipeline.look_again_due())

    def test_a_look_again_that_lost_the_race_judges_the_newer_message(self):
        pipeline, model, _ = self.pipeline("WAKE")
        self.deliver(pipeline, "q1")
        token = pipeline.scheduler.offer("q1", only_if_idle=True)
        pipeline.observe_and_offer(delivery_id="d-c1", event=message("c1", text="On it."), actors=ZOE)
        outcomes = pipeline.run_opportunities(token, occasion="pause")
        self.assertEqual(["c1"], [outcome.anchor_event_id for outcome in outcomes])
        self.assertNotIn("occasion", model.calls[-1][1])

    def test_a_wait_on_something_that_is_not_conversation_does_not_arm(self):
        pipeline, model, _ = self.pipeline()
        judge = model.judge

        def not_conversation(**kwargs):
            return dict(judge(**kwargs), conversation=0.3)

        model.judge = not_conversation
        self.deliver(pipeline, "q1")
        self.assertIsNone(pipeline.look_again_due())

    def test_zero_seconds_never_looks_again_and_bad_values_are_refused(self):
        pipeline, _, _ = self.pipeline()
        pipeline.look_again_seconds = 0
        self.deliver(pipeline, "q1")
        self.assertIsNone(pipeline.look_again_due())
        for bad in (-1, True, "300"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                NunchiV2Pipeline(
                    observation=pipeline.observation,
                    attention=pipeline.attention,
                    host=pipeline.host,
                    scheduler=pipeline.scheduler,
                    look_again_seconds=bad,
                )

    def test_cancel_and_restart_disarm_it(self):
        for stop in ("cancel", "restart"):
            with self.subTest(stop=stop):
                pipeline, _, _ = self.pipeline()
                self.deliver(pipeline, "q1")
                getattr(pipeline, stop)()
                self.assertIsNone(pipeline.look_again_due())

    def test_the_snapshot_says_why_it_was_built(self):
        pipeline, _, _ = self.pipeline()
        pipeline.observation.observe(delivery_id="d-q1", event=message("q1"), actors=ZOE)
        request = pipeline.observation.build_snapshot("q1", occasion="pause")
        self.assertEqual("pause", validate_attention_request(request)["occasion"])
        with self.assertRaises(Exception):
            validate_attention_request(dict(request, occasion="later"))


class LaneTests(unittest.TestCase):
    def test_the_lane_looks_again_when_the_pause_is_over(self):
        looked = threading.Event()
        wakes = []

        def participant(**turn):
            wakes.append(turn["wake"])
            if turn["wake"].get("occasion") == "pause":
                looked.set()
            return None

        pipeline, _, _, _ = foundation(model=FixtureModel("DEFER"), participant=participant)
        pipeline.look_again_seconds = 0.05
        lane = AsyncDeliveryLane(pipeline)
        lane.submit(delivery_id="d-q1", event=message("q1"), actors=ZOE)
        self.assertTrue(looked.wait(2))
        self.assertTrue(lane.drain(2))
        self.assertEqual(["q1", "q1"], [wake["trigger_event_id"] for wake in wakes])
        self.assertEqual((), lane.errors)

    def test_cancelling_the_lane_stops_a_pending_look_again(self):
        wakes = []
        pipeline, _, _, _ = foundation(
            model=FixtureModel("DEFER"), participant=lambda **turn: wakes.append(turn["wake"])
        )
        pipeline.look_again_seconds = 60
        lane = AsyncDeliveryLane(pipeline)
        lane.submit(delivery_id="d-q1", event=message("q1"), actors=ZOE)
        self.assertTrue(lane.drain(2))
        for _ in range(100):
            if lane._look_again_timer is not None:
                break
            threading.Event().wait(0.01)
        self.assertIsNotNone(lane._look_again_timer)
        lane.cancel()
        self.assertIsNone(lane._look_again_timer)
        self.assertIsNone(pipeline.look_again_due())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
