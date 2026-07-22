from __future__ import annotations

import unittest

from nunchi.scheduling import (
    ConversationOpportunityScheduler,
    SchedulingError,
)


class ConversationOpportunityCases(unittest.TestCase):
    def setUp(self):
        self.scheduler = ConversationOpportunityScheduler()
        self.room = {
            "participant_id": "vigil",
            "platform": "discord",
            "room_id": "42",
        }

    def observe(self, event_id: str):
        return self.scheduler.observe(
            **self.room,
            anchor_event_id=event_id,
        )

    def test_idle_event_starts_one_opportunity(self):
        opportunity = self.observe("e1")
        self.assertIsNotNone(opportunity)
        self.assertEqual(opportunity.anchor_event_id, "e1")
        self.assertEqual(opportunity.generation, 1)
        self.assertEqual(len(self.scheduler.snapshot()), 1)

    def test_burst_during_active_work_coalesces_to_newest_pending_anchor(self):
        active = self.observe("e1")
        self.assertIsNone(self.observe("e2"))
        self.assertIsNone(self.observe("e3"))
        self.assertIsNone(self.observe("e4"))
        state = self.scheduler.snapshot()[0]
        self.assertEqual(state["active_anchor_event_id"], "e1")
        self.assertEqual(state["pending_anchor_event_id"], "e4")

        promoted = self.scheduler.complete(active)
        self.assertEqual(promoted.anchor_event_id, "e4")
        self.assertEqual(promoted.generation, 2)
        self.assertIsNone(self.scheduler.snapshot()[0]["pending_anchor_event_id"])

    def test_completion_when_no_pending_event_returns_to_idle(self):
        active = self.observe("e1")
        self.assertIsNone(self.scheduler.complete(active))
        self.assertEqual(self.scheduler.snapshot(), ())
        next_opportunity = self.observe("e2")
        self.assertEqual(next_opportunity.generation, 1)

    def test_new_event_during_promoted_work_becomes_one_new_pending_anchor(self):
        first = self.observe("e1")
        self.observe("e2")
        second = self.scheduler.complete(first)
        self.assertIsNone(self.observe("e3"))
        third = self.scheduler.complete(second)
        self.assertEqual(third.anchor_event_id, "e3")

    def test_rooms_and_participants_are_independent(self):
        first = self.observe("e1")
        second_room = self.scheduler.observe(
            participant_id="vigil",
            platform="discord",
            room_id="99",
            anchor_event_id="x1",
        )
        other_participant = self.scheduler.observe(
            participant_id="claude",
            platform="discord",
            room_id="42",
            anchor_event_id="c1",
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second_room)
        self.assertIsNotNone(other_participant)
        self.assertEqual(len(self.scheduler.snapshot()), 3)

    def test_stale_or_duplicate_completion_cannot_release_newer_work(self):
        first = self.observe("e1")
        self.observe("e2")
        second = self.scheduler.complete(first)
        with self.assertRaises(SchedulingError):
            self.scheduler.complete(first)
        self.assertEqual(self.scheduler.snapshot()[0]["active_generation"], 2)
        self.assertIsNone(self.scheduler.complete(second))

    def test_abort_drops_active_and_pending_without_promotion(self):
        active = self.observe("e1")
        self.assertIsNone(self.observe("e2"))
        self.scheduler.abort(active)
        self.assertEqual(self.scheduler.snapshot(), ())
        with self.assertRaises(SchedulingError):
            self.scheduler.abort(active)

    def test_restart_has_no_pending_wake_backlog(self):
        self.observe("e1")
        self.observe("e2")
        restarted = ConversationOpportunityScheduler()
        self.assertEqual(restarted.snapshot(), ())
        # Backfilled observation data does not create work unless a new live
        # canonical event is explicitly submitted after restart.

    def test_scheduler_accepts_no_semantic_or_age_inputs(self):
        with self.assertRaises(TypeError):
            self.scheduler.observe(
                **self.room,
                anchor_event_id="e1",
                message_text="already resolved",
            )
        with self.assertRaises(TypeError):
            self.scheduler.observe(
                **self.room,
                anchor_event_id="e1",
                age_seconds=300,
            )

    def test_empty_or_non_string_identity_rejects(self):
        for field, value in (
            ("participant_id", ""),
            ("platform", None),
            ("room_id", ""),
            ("anchor_event_id", 42),
        ):
            with self.subTest(field=field):
                values = {**self.room, "anchor_event_id": "e1", field: value}
                with self.assertRaises(SchedulingError):
                    self.scheduler.observe(**values)


if __name__ == "__main__":
    unittest.main()
