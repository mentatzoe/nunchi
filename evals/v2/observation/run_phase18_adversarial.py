"""Reproducible Phase 18/23/25/26/28 authority and resource evidence.

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
from tests.v2.observation.test_input_atomicity import (
    TestCallerMemoryIsolation,
    TestEarlyCursorLimit,
)
from tests.v2.observation.test_budget_and_continuation import (
    TestSharedContinuationAuthorityAndRelationGaps,
)
from tests.v2.observation.test_continuation_authority import (
    TestContinuationComparatorExpiryPresence,
    TestLifetimeTimestampWatermark,
    TestProviderOwnedContinuationAuthority,
    TestReceiptCallerMemoryAuthority,
    TestRelationGapTruth,
)
from tests.v2.observation.test_eval_scenes import TestEvalScenesAllPass
from tests.v2.observation.test_recoverability import TestKnownGapVariant

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
    ("P23-INPUT-001", TestCallerMemoryIsolation, "test_fetch_uses_one_private_request_copy_after_authorization"),
    ("P23-INPUT-002", TestCallerMemoryIsolation, "test_ingest_copies_complete_native_input_before_validation"),
    ("P23-INPUT-003", TestCallerMemoryIsolation, "test_copy_failures_reject_without_state_mutation"),
    ("P23-RESOURCE-001", TestEarlyCursorLimit, "test_over_limit_fresh_fetch_rejects_before_retained_deque_visit"),
    ("P25-AUTH-001", TestSharedContinuationAuthorityAndRelationGaps, "test_generated_handle_collision_retries_without_overwriting_authority"),
    ("P25-AUTH-002", TestSharedContinuationAuthorityAndRelationGaps, "test_cross_wrapper_concurrent_issue_obeys_one_global_cap"),
    ("P25-GAP-001", TestSharedContinuationAuthorityAndRelationGaps, "test_unavailable_literal_relation_targets_are_reported_as_gaps"),
    ("P25-GAP-002", TestSharedContinuationAuthorityAndRelationGaps, "test_budget_excluded_known_relation_reports_actual_truncation_cause"),
    ("P26-COMP-001", TestContinuationComparatorExpiryPresence, "test_expiry_presence_is_semantic_but_exact_clock_value_is_opaque"),
    ("P26-AUTH-001", TestProviderOwnedContinuationAuthority, "test_generated_handle_collision_fails_without_overwriting_live_authority"),
    ("P26-AUTH-002", TestProviderOwnedContinuationAuthority, "test_revoked_handle_id_never_resurrects_old_capability"),
    ("P26-AUTH-003", TestProviderOwnedContinuationAuthority, "test_wrappers_share_one_registry_and_one_provider_wide_handle_cap"),
    ("P26-AUTH-004", TestProviderOwnedContinuationAuthority, "test_additional_wrapper_with_different_limits_rejects"),
    ("P26-AUTH-005", TestProviderOwnedContinuationAuthority, "test_issued_handle_filter_is_fixed_size"),
    ("P26-AUTH-006", TestProviderOwnedContinuationAuthority, "test_concurrent_wrappers_obey_one_provider_wide_handle_cap"),
    ("P26-AUTH-007", TestProviderOwnedContinuationAuthority, "test_concurrent_wrappers_cannot_overwrite_a_colliding_handle"),
    ("P26-GAP-001", TestRelationGapTruth, "test_missing_reply_target_is_an_honest_gap"),
    ("P26-GAP-002", TestRelationGapTruth, "test_missing_thread_root_is_an_honest_gap"),
    ("P26-GAP-003", TestRelationGapTruth, "test_missing_reaction_target_is_an_honest_gap"),
    ("P26-GAP-004", TestRelationGapTruth, "test_known_relation_target_that_cannot_fit_is_an_honest_gap"),
    ("P26-RECEIPT-001", TestReceiptCallerMemoryAuthority, "test_receipt_attests_private_issued_document_after_caller_mutation"),
    ("P26-RECEIPT-002", TestReceiptCallerMemoryAuthority, "test_receipt_copy_failure_does_not_consume_pending_authority"),
    ("P26-TIME-001", TestLifetimeTimestampWatermark, "test_undated_eviction_cannot_erase_parseable_time_order"),
    ("P28-RECON-GAP-001", TestSharedContinuationAuthorityAndRelationGaps, "test_nearby_returned_relation_target_absence_is_reported_as_a_gap"),
    ("P28-RECON-GAP-002", TestSharedContinuationAuthorityAndRelationGaps, "test_continuation_reports_relation_gaps_for_every_returned_event"),
    ("P28-RECON-RESTART-001", TestKnownGapVariant, "test_known_gap_variant_reports_the_dropped_tail_honestly"),
    ("P28-RECON-EVAL-001", TestEvalScenesAllPass, "test_equivalence_validates_final_pages_at_comparison_seam"),
    ("P28-RECON-ORDER-001", TestSharedContinuationAuthorityAndRelationGaps, "test_capped_trigger_relation_priority_is_hash_seed_independent"),
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
