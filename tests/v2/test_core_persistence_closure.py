"""Shared journals stay truthful when work stops between commit and effect.

Covers the post-merge review of PR #83 (issue #85):

- an authorization commit that never reaches its executor is closed as
  "not attempted" instead of looking like a crash during dispatch.
"""

from __future__ import annotations

from pathlib import Path
import threading
import unittest

from nunchi.authorization import (
    AuthorizationError,
    AuthorizationJournal,
    PolicySnapshot,
    StaticPolicySource,
)
from tests.v2 import test_shared_foundation as shared


NOT_ATTEMPTED = "privileged effect was not attempted"


class AuthorizationCommitClosureTests(unittest.TestCase):
    """Post-commit exits, on the shared authorization fixture."""

    setUp = shared.AuthorizationTests.setUp
    coordinator = shared.AuthorizationTests.coordinator
    proposal = shared.AuthorizationTests.proposal

    def _assert_closed_not_attempted(self, journal) -> None:
        records = journal.records()
        kinds = [record["kind"] for record in records]
        self.assertIn("effect_commit", kinds)
        self.assertEqual("effect_result", kinds[-1])
        self.assertEqual("FAILED", records[-1]["outcome"])
        self.assertTrue(records[-1]["detail"].startswith(NOT_ATTEMPTED))
        self.assertEqual([], self.native_calls)

    def test_cancel_after_commit_closes_the_commit(self) -> None:
        cancel = threading.Event()

        class CancellingJournal(AuthorizationJournal):
            def append(inner, record):
                result = super().append(record)
                if record.get("kind") == "effect_commit":
                    cancel.set()
                return result

        journal = CancellingJournal(Path(self.temp.name) / "cancel.jsonl")
        self.journal = journal
        result = self.coordinator().execute_proposal(
            proposal=self.proposal(), wake=self.wake, cancel=cancel
        )
        self.assertEqual("failed", result.delivery)
        self._assert_closed_not_attempted(journal)
        # The grant stays consumed: a second proposal is refused as replay.
        again = self.coordinator().execute_proposal(
            proposal=self.proposal(), wake=self.wake, cancel=threading.Event()
        )
        self.assertEqual("failed", again.delivery)
        self.assertEqual([], self.native_calls)

    def test_policy_reload_failure_after_commit_closes_the_commit(self) -> None:
        snapshot = PolicySnapshot("policy", "r1", (self.rule,), ("operator:zoe",))
        journal = self.journal

        class FlakyPolicy(StaticPolicySource):
            def load(inner):
                if any(r["kind"] == "effect_commit" for r in journal.records()):
                    raise AuthorizationError("pinned policy changed on disk")
                return snapshot

        with self.assertRaises(AuthorizationError):
            self.coordinator(FlakyPolicy(snapshot)).execute_proposal(
                proposal=self.proposal(), wake=self.wake, cancel=threading.Event()
            )
        self._assert_closed_not_attempted(self.journal)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
