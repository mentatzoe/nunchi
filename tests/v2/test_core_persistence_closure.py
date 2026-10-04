"""Shared journals stay truthful when work stops between commit and effect.

Covers the post-merge review of PR #83 (issue #85):

- an authorization commit that never reaches its executor is closed as
  "not attempted" instead of looking like a crash during dispatch;
- ACK journal rollback failures, non-I/O confirm failures, and the first
  directory sync are handled without misleading diagnostics or lost
  durability.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from nunchi.ack import AckJournal
from nunchi.authorization import (
    AuthorizationError,
    AuthorizationJournal,
    PolicySnapshot,
    StaticPolicySource,
)
from nunchi.receipts import PersistenceError
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


class AckJournalClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ack.jsonl"

    def _binding(self, request_id: str = "r1") -> dict:
        return {
            "request_id": request_id,
            "participant_id": "vigil",
            "actor_id": "discord:bot:9",
            "platform": "discord",
            "room_id": "42",
            "continuity_scope_id": "discord:channel:42",
            "target_event_id": f"e-{request_id}",
            "reaction": "👂",
            "operation": "add",
            "opportunity_generation": 1,
            "lifecycle_id": "lifecycle",
            "deadline_id": "deadline",
            "permissions_revision": "rev",
        }

    def test_rollback_failure_is_reported_as_uncertain_not_as_a_lock_failure(self) -> None:
        journal = AckJournal(self.path)
        ack_id, _ = journal.reserve(self._binding())
        size_after_reservation = self.path.stat().st_size

        def failing_confirm():
            raise PersistenceError("observer abandoned")

        with mock.patch("nunchi.ack.os.ftruncate", side_effect=OSError(5, "EIO")):
            with self.assertRaises(PersistenceError) as raised:
                journal._append(
                    {"schema_version": 1, "ack_id": ack_id, "state": "settled",
                     "delivery": "sent"},
                    confirm=failing_confirm,
                )
        message = str(raised.exception)
        self.assertIn("withdrawal failed", message)
        self.assertNotIn("could not lock", message)
        self.assertGreaterEqual(self.path.stat().st_size, size_after_reservation)

    def test_non_io_confirm_failure_still_withdraws_the_record(self) -> None:
        journal = AckJournal(self.path)
        ack_id, _ = journal.reserve(self._binding())
        size_after_reservation = self.path.stat().st_size

        def broken_confirm():
            raise RuntimeError("observer bug")

        with self.assertRaises(RuntimeError):
            journal._append(
                {"schema_version": 1, "ack_id": ack_id, "state": "settled",
                 "delivery": "sent"},
                confirm=broken_confirm,
            )
        self.assertEqual(size_after_reservation, self.path.stat().st_size)

    def test_first_content_syncs_the_directory_even_if_the_file_already_exists(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600)  # left empty by an earlier aborted append
        journal = AckJournal(self.path)
        synced = []
        real_fsync = os.fsync

        def spy(fd):
            synced.append(os.path.isdir(f"/proc/self/fd/{fd}") if os.path.exists(
                f"/proc/self/fd/{fd}") else None)
            return real_fsync(fd)

        with mock.patch("nunchi.ack.os.fsync", side_effect=spy):
            journal.reserve(self._binding())
        self.assertIn(True, synced, "the directory entry must be synced once")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
