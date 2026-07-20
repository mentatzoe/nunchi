from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nunchi.core import ReceiptSinkPersistenceError
from nunchi.policy import load_operator_policy
from nunchi.receipts import ExclusiveJSONFileReceiptSink, ReceiptSinkConstructionError
from tests.v2.contract.schema_helpers import make_receipt
from tests.v2.security.helpers import clone_policy, write_policy


class ExclusiveReceiptCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.receipt_dir = Path(self.temporary.name) / "receipts"
        self.receipt_dir.mkdir(mode=0o700)
        document = clone_policy()
        document["receipt_sink"]["directory"] = str(self.receipt_dir)
        self.policy = load_operator_policy(write_policy(self.temporary.name, document))

    def test_persists_one_canonical_contract_valid_attention_receipt(self):
        receipt = make_receipt("attention")
        with ExclusiveJSONFileReceiptSink(self.policy.receipt_sink) as sink:
            self.assertIsNone(sink(receipt))
        files = list(self.receipt_dir.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(files[0].read_text(encoding="utf-8")), receipt)

    def test_invalid_receipt_fails_before_create(self):
        receipt = make_receipt("attention")
        receipt["writer"] = "transport"
        with ExclusiveJSONFileReceiptSink(self.policy.receipt_sink) as sink:
            with self.assertRaises(ReceiptSinkPersistenceError) as caught:
                sink(receipt)
        self.assertEqual(caught.exception.persistence, "not-persisted")
        self.assertEqual(list(self.receipt_dir.iterdir()), [])

    def test_collision_never_overwrites_and_is_unknown(self):
        receipt = make_receipt("attention")
        with ExclusiveJSONFileReceiptSink(self.policy.receipt_sink) as sink:
            sink(receipt)
            original = list(self.receipt_dir.iterdir())[0].read_bytes()
            with self.assertRaises(ReceiptSinkPersistenceError) as caught:
                sink(receipt)
        self.assertEqual(caught.exception.persistence, "unknown")
        self.assertEqual(list(self.receipt_dir.iterdir())[0].read_bytes(), original)

    def test_group_readable_directory_is_rejected(self):
        self.receipt_dir.chmod(0o750)
        with self.assertRaises(ReceiptSinkConstructionError):
            ExclusiveJSONFileReceiptSink(self.policy.receipt_sink)

    def test_symlink_directory_is_rejected(self):
        link = Path(self.temporary.name) / "linked-receipts"
        link.symlink_to(self.receipt_dir, target_is_directory=True)
        document = clone_policy()
        document["receipt_sink"]["directory"] = str(link)
        policy = load_operator_policy(write_policy(self.temporary.name, document))
        with self.assertRaises(ReceiptSinkConstructionError):
            ExclusiveJSONFileReceiptSink(policy.receipt_sink)


if __name__ == "__main__":
    unittest.main()
