"""Durable invocation claims do not assert native effect success."""
import tempfile
import unittest
from pathlib import Path

from nunchi.integrations.hermes_tools import NativeInvocationJournal
from nunchi.receipts import PersistenceError


class NativeInvocationJournalTests(unittest.TestCase):
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
