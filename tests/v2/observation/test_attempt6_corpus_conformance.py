"""T037: slice 020's own stdlib adapter over the complete, identical
attempt-6 corpus revision (202 cases), including all seven
runtime-adapter-only semantic/relational classes, with every
non-consumed-interface case explicitly accounted for rather than
silently skipped."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.v2.observation.contract_helpers import (
    EVALS_DIR,
    EXPECTED_CORPUS_SHA256,
    EXPECTED_CORPUS_REVISION,
    EXPECTED_TOTAL_CASES,
    corpus_digest,
    run_all,
    summarize,
)

# Locked per-class expected (consumed, non_consumed) counts (T037): a drift
# in either number fails loudly rather than silently shrinking coverage.
EXPECTED_BY_CLASS = {
    "schema-expressible": (54, 98),
    "id-uniqueness": (4, 0),
    "timestamp-order": (2, 0),
    "advice-citation": (0, 2),
    "trigger-membership": (2, 0),
    "actor-reference-integrity": (7, 2),
    "binding-expiry": (20, 0),
    "receipt-sequence": (11, 0),
}


class TestAttempt6CorpusConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_all()
        cls.summary = summarize(cls.results)

    def test_total_case_count_matches_the_frozen_revision(self):
        self.assertEqual(self.summary["total_cases"], EXPECTED_TOTAL_CASES)

    def test_consumed_and_non_consumed_split(self):
        self.assertEqual(self.summary["consumed_count"], 100)
        self.assertEqual(self.summary["non_consumed_count"], 102)
        self.assertEqual(
            self.summary["consumed_count"] + self.summary["non_consumed_count"],
            EXPECTED_TOTAL_CASES,
        )

    def test_every_case_matches_its_expected_result_or_is_explicitly_non_consumed(self):
        self.assertEqual(self.summary["mismatch_count"], 0, self.summary["mismatches"])

    def test_all_seven_relational_classes_are_present_and_accounted_for(self):
        for klass, expected in EXPECTED_BY_CLASS.items():
            with self.subTest(klass=klass):
                observed = self.summary["by_class"][klass]
                self.assertEqual(
                    (observed["consumed"], observed["non_consumed"]), expected,
                    f"class {klass!r} count drifted from the frozen accounting",
                )

    def test_corpus_revision_and_exact_bytes_are_pinned(self):
        self.assertEqual(len(EXPECTED_CORPUS_REVISION), 40)
        self.assertEqual(corpus_digest(), EXPECTED_CORPUS_SHA256)

    def test_any_corpus_byte_drift_changes_the_pinned_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "contract"
            shutil.copytree(EVALS_DIR, copied)
            target = copied / "attention-request" / "cases.jsonl"
            target.write_bytes(target.read_bytes() + b"\n")
            self.assertNotEqual(corpus_digest(copied), EXPECTED_CORPUS_SHA256)


if __name__ == "__main__":
    unittest.main()
