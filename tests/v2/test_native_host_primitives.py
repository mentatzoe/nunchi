"""Shared primitives native-host integrations build on (issue #85).

These were covered only through the Hermes harness; native hosts such as a
Claude Code mod rely on the same guarantees.
"""

from __future__ import annotations

import math
import time
import unittest

from nunchi.participant import ConversationOpportunityScheduler


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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
