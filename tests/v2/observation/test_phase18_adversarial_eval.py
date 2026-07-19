"""Tests for the Phase 18/23/25/26 authority/resource evidence runner."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from evals.v2.observation.run_phase18_adversarial import run_and_write


class TestPhase18AdversarialEval(unittest.TestCase):
    def test_runner_emits_deterministic_green_case_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "phase18.jsonl"
            rows = run_and_write(output)
            self.assertEqual(len(rows), 34)
            self.assertTrue(all(row["result"] == "PASS" for row in rows))
            self.assertEqual(
                {row["case_id"] for row in rows},
                {
                    "P18-ATOMIC-001", "P18-ATOMIC-002", "P18-ATOMIC-003",
                    "P18-ATOMIC-004", "P18-ATOMIC-005",
                    "P18-GAP-001", "P18-GAP-002", "P18-GAP-003",
                    "P18-RESOURCE-001", "P18-RESOURCE-002",
                    "P18-RESOURCE-METRICS",
                    "P23-INPUT-001", "P23-INPUT-002", "P23-INPUT-003",
                    "P23-RESOURCE-001",
                    "P25-AUTH-001", "P25-AUTH-002",
                    "P25-GAP-001", "P25-GAP-002",
                    "P26-COMP-001",
                    "P26-AUTH-001", "P26-AUTH-002", "P26-AUTH-003",
                    "P26-AUTH-004", "P26-AUTH-005", "P26-AUTH-006",
                    "P26-AUTH-007",
                    "P26-GAP-001", "P26-GAP-002", "P26-GAP-003",
                    "P26-GAP-004",
                    "P26-RECEIPT-001", "P26-RECEIPT-002",
                    "P26-TIME-001",
                },
            )
            serialized = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(serialized, rows)
            metrics = next(
                row for row in rows if row["case_id"] == "P18-RESOURCE-METRICS"
            )
            self.assertLessEqual(metrics["deque_visits_2n"], metrics["deque_visits_n"] * 3 + 8)


if __name__ == "__main__":
    unittest.main()
