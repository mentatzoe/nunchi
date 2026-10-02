"""Durable invocation claims do not assert native effect success."""
import tempfile
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path

from nunchi.integrations.hermes_tools import NativeInvocationJournal
from nunchi.receipts import PersistenceError


class NativeInvocationJournalTests(unittest.TestCase):
    def test_persistent_contention_fails_closed_and_keeps_existing_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native-tools.sqlite3"
            journal = NativeInvocationJournal(path)
            journal.reserve("prior", {})
            blocker = sqlite3.connect(path)
            blocker.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            try:
                with self.assertRaises(PersistenceError):
                    journal.reserve("next", {})
                with self.assertRaises(PersistenceError):
                    journal.finish("prior", "returned")
            finally:
                blocker.rollback()
                blocker.close()
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(["prior"], [r["identity"] for r in journal.records()])
            self.assertEqual("committed", journal.records()[0]["invocation"])
            self.assertFalse(journal.reserve("prior", {}))

    def test_reserve_and_finish_wait_for_brief_native_batch_contention(self):
        # A second native worker finishes outside the runtime lock while the
        # first reserves under it. Exercise actual SQLite locking, not a mock.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native-tools.sqlite3"
            journal = NativeInvocationJournal(path)
            journal.reserve("prior", {})
            for operation in (lambda: journal.reserve("next", {}),
                              lambda: journal.finish("prior", "returned")):
                with self.subTest(operation=operation), ThreadPoolExecutor(1) as pool:
                    blocker = sqlite3.connect(path)
                    blocker.execute("BEGIN IMMEDIATE")
                    entered = threading.Event()
                    def contend():
                        entered.set()
                        return operation()
                    pending = pool.submit(contend)
                    try:
                        self.assertTrue(entered.wait(2))
                        # This finite writer hold exceeds zero busy-timeout.
                        threading.Event().wait(0.05)
                    finally:
                        blocker.rollback()
                        blocker.close()
                    pending.result(timeout=2)
            records = journal.records()
            self.assertEqual(["returned", "committed"], [r["invocation"] for r in records])
            self.assertFalse(journal.reserve("next", {}))

    def test_claim_survives_restart_and_never_retries_returned_or_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native-tools.sqlite3"
            journal = NativeInvocationJournal(path)
            binding = {"tool_name": "terminal", "args_sha256": "a" * 64}
            self.assertTrue(journal.reserve("call-1", binding))
            self.assertFalse(journal.reserve("call-1", binding))
            self.assertEqual("unknown", journal.records()[0]["effect"])
            journal.finish("call-1", "returned")
            restarted = NativeInvocationJournal(path)
            self.assertFalse(restarted.reserve("call-1", binding))
            self.assertFalse(restarted.reserve("call-1", {"tool_name": "other"}))
            record = restarted.records()[0]
            self.assertEqual("returned", record["invocation"])
            self.assertEqual("unknown", record["effect"])
            self.assertEqual(binding, record["binding"])
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_corrupt_or_symlink_journal_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native-tools.sqlite3"
            path.write_text("not a database")
            with self.assertRaises(PersistenceError):
                NativeInvocationJournal(path)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises(PersistenceError):
                NativeInvocationJournal(link)

    def test_independent_writers_have_one_durable_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native-tools.sqlite3"
            first = NativeInvocationJournal(path)
            second = NativeInvocationJournal(path)
            self.assertTrue(first.reserve("one", {"tool_name": "read_file"}))
            self.assertFalse(second.reserve("one", {"tool_name": "read_file"}))
            first.finish("one", "raised")
            self.assertEqual("raised", second.records()[0]["invocation"])
