"""Messages that arrive mid-turn are judged for the memory (#94 step 6).

`docs/behavior.md` listed it as not yet: a message that arrived while the
participant was mid-turn was never judged, so it started no thread. Only the
newest message after a turn gets an opportunity. The ones it replaced are now
judged for the memory alone, before it, so a question asked meanwhile is
remembered, and the newest message's judgment and turn both see it.
"""

from __future__ import annotations

import unittest

from nunchi.pipeline import MIDTURN_RECALL_LIMIT
from tests.v2.test_shared_foundation import FixtureModel, foundation, message

ACTORS = {"human:zoe": {"kind": "human"}, "human:sam": {"kind": "human"}}


class MidturnRecallTests(unittest.TestCase):
    def setUp(self):
        self.wakes = []
        # Messages posted while the participant composes its first turn.
        self.during = []
        self.pipeline, self.model, _, _ = foundation(model=FixtureModel("WAKE"), participant=self.participant)

    def participant(self, **turn):
        self.wakes.append(turn["wake"])
        while self.during:
            event_id, author_id, text = self.during.pop(0)
            self.pipeline.observe_and_offer(
                delivery_id=f"d-{event_id}", event=message(event_id, author_id, text), actors=ACTORS
            )
        return None

    def judged(self):
        return [projection["trigger_event_id"] for _, projection in self.model.calls]

    def start(self):
        return self.pipeline.handle_delivery(
            delivery_id="d-z1", event=message("z1", text="Vigil, can you check the build?"), actors=ACTORS
        )

    def test_a_question_asked_mid_turn_is_remembered_before_the_newest_is_judged(self):
        self.during = [("s1", "human:sam", "Vigil, is staging up?"), ("z2", "human:zoe", "Thanks!")]
        self.start()
        self.assertEqual(["z1", "s1", "z2"], self.judged())
        # Only the newest gets a turn; s1 was judged for the memory alone.
        self.assertEqual(["z1", "z2"], [wake["trigger_event_id"] for wake in self.wakes])
        _, projection = self.model.calls[-1]
        self.assertIn("s1", [thread["event_id"] for thread in projection["memory"]["threads"]])
        self.assertIn("s1", [thread["event_id"] for thread in self.wakes[-1]["memory"]["threads"]])

    def test_the_newest_is_judged_once_and_a_lone_message_is_not_recalled(self):
        self.during = [("z2", "human:zoe", "Also the nightly?")]
        self.start()
        self.assertEqual(["z1", "z2"], self.judged())

    def test_only_the_newest_few_are_recalled(self):
        count = MIDTURN_RECALL_LIMIT + 2
        self.during = [(f"s{index}", "human:sam", f"Point {index}.") for index in range(count)]
        self.start()
        recalled = [f"s{index}" for index in range(count - 1 - MIDTURN_RECALL_LIMIT, count - 1)]
        self.assertEqual(["z1", *recalled, f"s{count - 1}"], self.judged())

    def test_a_message_that_cannot_be_judged_does_not_stop_the_newest(self):
        self.during = [("s1", "human:sam", "Vigil, is staging up?"), ("z2", "human:zoe", "Thanks!")]
        recall = self.pipeline.recall

        def failing(event_id, **kwargs):
            if event_id == "s1":
                from nunchi.observation import SnapshotUnavailable

                raise SnapshotUnavailable("gone")
            return recall(event_id, **kwargs)

        self.pipeline.recall = failing
        self.start()
        self.assertEqual(["z1", "z2"], [wake["trigger_event_id"] for wake in self.wakes])

    def test_a_slow_provider_delays_the_newest_by_one_timeout_at_most(self):
        from dataclasses import replace
        import time

        attention = self.pipeline.attention
        attention.policy = replace(attention.policy, timeout_seconds=0.1)
        self.during = [(f"s{index}", "human:sam", f"Point {index}.") for index in range(4)]
        budgets = []

        def slow(event_id, *, timeout_seconds):
            budgets.append(timeout_seconds)
            time.sleep(0.06)

        self.pipeline.recall = slow
        self.start()
        # Three were waiting, but the shared budget ran out before the last.
        self.assertGreaterEqual(len(budgets), 1)
        self.assertLess(len(budgets), 3)
        self.assertTrue(all(budget <= 0.1 for budget in budgets))
        self.assertEqual(["z1", "s3"], [wake["trigger_event_id"] for wake in self.wakes])

    def test_cancel_and_restart_forget_what_was_waiting(self):
        for stop in ("cancel", "restart"):
            with self.subTest(stop=stop):
                pipeline, model, _, _ = foundation(model=FixtureModel("WAKE"))
                pipeline.observation.observe(delivery_id="d-z1", event=message("z1"), actors=ACTORS)
                active = pipeline.scheduler.offer("z1")
                self.assertIsNotNone(active)
                pipeline.observe_and_offer(delivery_id="d-s1", event=message("s1", "human:sam"), actors=ACTORS)
                getattr(pipeline, stop)()
                self.assertEqual(0, len(pipeline._arrived_midturn))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
