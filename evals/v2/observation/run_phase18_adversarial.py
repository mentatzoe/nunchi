"""Reproducible Phase 18 atomicity and replay-resource evidence.

This runner executes the deterministic barrier-controlled regression cases and
emits one JSONL row per mechanism plus explicit N/2N deque-visit metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from tests.v2.observation.test_continuation_atomicity import (
    TestContinuationAtomicity,
    TestContinuationRetentionGapCoverage,
    TestCursorReplayComplexity,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPO_ROOT / "evidence/v2/observation/phase18-adversarial.jsonl"

CASES = (
    ("P18-ATOMIC-001", TestContinuationAtomicity, "test_concurrent_issue_obeys_hard_handle_limit"),
    ("P18-ATOMIC-002", TestContinuationAtomicity, "test_concurrent_fresh_fetch_obeys_active_cursor_limit"),
    ("P18-ATOMIC-003", TestContinuationAtomicity, "test_one_shot_cursor_has_exactly_one_concurrent_consumer"),
    ("P18-ATOMIC-004", TestContinuationAtomicity, "test_fetch_and_revoke_are_linearizable_without_state_resurrection"),
    ("P18-ATOMIC-005", TestContinuationAtomicity, "test_ingest_and_fetch_share_one_provider_lock"),
    ("P18-GAP-001", TestContinuationRetentionGapCoverage, "test_before_terminal_page_discloses_known_retention_gap"),
    ("P18-GAP-002", TestContinuationRetentionGapCoverage, "test_after_chain_discloses_known_retention_gap_on_every_page"),
    ("P18-GAP-003", TestContinuationRetentionGapCoverage, "test_around_chain_discloses_known_retention_gap_through_exhaustion"),
    ("P18-RESOURCE-001", TestCursorReplayComplexity, "test_one_event_cursor_chain_replay_grows_near_linearly"),
    ("P18-RESOURCE-002", TestCursorReplayComplexity, "test_event_by_id_state_is_retention_bounded_and_reclaimed_with_eviction"),
)


def _run_test_case(case_id: str, test_class: type[unittest.TestCase], method: str) -> dict:
    result = unittest.TestResult()
    test_class(method).run(result)
    problems = result.failures + result.errors
    if result.skipped:
        problems.extend((test, reason) for test, reason in result.skipped)
    return {
        "case_id": case_id,
        "result": "PASS" if not problems else "FAIL",
        "test": f"{test_class.__name__}.{method}",
        "detail": "" if not problems else " | ".join(str(detail) for _, detail in problems),
    }


def run_cases() -> list[dict]:
    rows = [_run_test_case(*case) for case in CASES]
    metric_case = TestCursorReplayComplexity()
    visits_n, _, _ = metric_case._one_event_chain_visits(64)
    visits_2n, _, _ = metric_case._one_event_chain_visits(128)
    linear = visits_2n <= visits_n * 3 + 8
    rows.append({
        "case_id": "P18-RESOURCE-METRICS",
        "result": "PASS" if linear else "FAIL",
        "n": 64,
        "two_n": 128,
        "deque_visits_n": visits_n,
        "deque_visits_2n": visits_2n,
        "linear_bound": visits_n * 3 + 8,
        "detail": "cursor replay excludes fresh-page setup and counts retained-deque iteration",
    })
    return rows


def run_and_write(output: Path = DEFAULT_OUTPUT) -> list[dict]:
    rows = run_cases()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return rows


def main() -> int:
    rows = run_and_write()
    failures = sum(row["result"] != "PASS" for row in rows)
    print(f"phase18-adversarial.jsonl: {len(rows)} rows, {failures} FAIL")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
