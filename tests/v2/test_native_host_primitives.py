"""Shared primitives native-host integrations build on (issue #85).

These were covered only through the Hermes harness; native hosts such as a
Claude Code mod rely on the same guarantees.
"""

from __future__ import annotations

import math
from pathlib import Path
import tempfile
import time
import unittest

from nunchi.ack import AckJournal
from nunchi.participant import ConversationOpportunityScheduler


def _binding() -> dict:
    return {
        "request_id": "r1",
        "participant_id": "vigil",
        "actor_id": "example:bot:9",
        "platform": "example",
        "room_id": "42",
        "continuity_scope_id": "example:room:42",
        "target_event_id": "e1",
        "reaction": "👂",
        "operation": "add",
        "opportunity_generation": 1,
        "lifecycle_id": "lifecycle",
        "deadline_id": "deadline",
        "permissions_revision": "rev",
    }


class EffectCommitTests(unittest.TestCase):
    def test_effect_commit_is_one_shot_and_excludes_commit_dispatch(self) -> None:
        scheduler = ConversationOpportunityScheduler("room")
        token = scheduler.offer("e0")
        deadline = time.monotonic() + 5
        self.assertTrue(scheduler.authorize_effect_commit(token, deadline=deadline))
        self.assertFalse(scheduler.authorize_effect_commit(token, deadline=deadline))
        committed, result = scheduler.commit_dispatch(token, lambda: "should not run")
        self.assertFalse(committed)
        self.assertIsNone(result)

    def test_effect_commit_refuses_expired_cancelled_and_malformed_deadlines(self) -> None:
        for deadline in (time.monotonic() - 1, True, "soon", math.nan, math.inf):
            with self.subTest(deadline=deadline):
                scheduler = ConversationOpportunityScheduler("room")
                token = scheduler.offer("e0")
                self.assertFalse(scheduler.authorize_effect_commit(token, deadline=deadline))
        scheduler = ConversationOpportunityScheduler("room")
        token = scheduler.offer("e0")
        scheduler.cancel()
        self.assertFalse(
            scheduler.authorize_effect_commit(token, deadline=time.monotonic() + 5)
        )


class AckSettlementTests(unittest.TestCase):
    def test_settle_returns_the_recorded_delivery_and_never_rewrites_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = AckJournal(Path(temp) / "ack.jsonl")
            ack_id, reserved = journal.reserve(_binding())
            self.assertTrue(reserved)
            self.assertEqual("sent", journal.settle(ack_id, delivery="sent", detail="ok"))
            # A later settlement for the same ACK reports what is on record.
            self.assertEqual(
                "sent", journal.settle(ack_id, delivery="unknown", detail="late")
            )
            reloaded = AckJournal(Path(temp) / "ack.jsonl")
            settled = [r for r in reloaded.records() if r["state"] == "settled"]
            self.assertEqual(["sent"], [r["delivery"] for r in settled])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
