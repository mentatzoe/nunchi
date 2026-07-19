"""Regression guard over the four eval case corpora (T012, T018, T019,
T024, T025): every case must PASS so a later product change that breaks a
recorded scene fails the ordinary baseline, not just the evidence script."""

from __future__ import annotations

import unittest

from evals.v2.observation.run_scenes import (
    run_budget_sweep,
    run_continuation_attacks,
    run_equivalence,
    run_identity_and_hygiene,
    run_recoverability,
)


class TestEvalScenesAllPass(unittest.TestCase):
    def _assert_all_pass(self, rows):
        failures = [row for row in rows if row["result"] != "PASS"]
        self.assertEqual(failures, [], f"{len(failures)} of {len(rows)} case(s) failed")
        self.assertTrue(rows, "expected at least one case")
        self.assertTrue(all(row.get("scene_id") for row in rows), "every row needs a scene_id")

    def test_identity_and_hygiene(self):
        self._assert_all_pass(run_identity_and_hygiene())

    def test_budget_sweep(self):
        self._assert_all_pass(run_budget_sweep())

    def test_continuation_attacks(self):
        self._assert_all_pass(run_continuation_attacks())

    def test_recoverability(self):
        self._assert_all_pass(run_recoverability())

    def test_equivalence(self):
        self._assert_all_pass(run_equivalence())


if __name__ == "__main__":
    unittest.main()
