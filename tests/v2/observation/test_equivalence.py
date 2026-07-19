"""US3 equivalence/comparator tests (T021): reference-equivalence and the
reusable downstream comparator contract (S13, FR-012, SC-006)."""

from __future__ import annotations

import unittest

from evals.v2.observation.compare import compare_requests
from tests.v2.observation.helpers import FIXTURE_ACTORS, candidate, make_message, make_provider


def _snapshot_from(events, trigger_id, **provider_kwargs):
    provider = make_provider(**provider_kwargs)
    for event in events:
        provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
    return provider.snapshot(trigger_event_id=trigger_id, max_events=100, max_bytes=65536)


class TestReferenceEquivalence(unittest.TestCase):
    def test_equivalent_facts_and_budgets_compare_equal(self):
        events = [make_message("e1", "discord:1001", "hi"), make_message("e2", "discord:1001", "again")]
        left = _snapshot_from(events, "e2")
        right = _snapshot_from(events, "e2")
        result = compare_requests(left, right)
        self.assertTrue(result["equivalent"])
        self.assertEqual(result["unexplained"], [])

    def test_unexplained_content_divergence_is_reported(self):
        left = _snapshot_from([make_message("e1", "discord:1001", "hi")], "e1")
        right = _snapshot_from([make_message("e1", "discord:1001", "bye")], "e1")
        result = compare_requests(left, right)
        self.assertFalse(result["equivalent"])
        self.assertTrue(any("text" in diff for diff in result["unexplained"]))

    def test_honestly_unavailable_native_fact_is_explained_not_a_failure(self):
        left = _snapshot_from(
            [make_message("e1", "discord:1001", "hi"), make_message("e2", "discord:1001", "again")], "e2"
        )
        right = _snapshot_from([make_message("e2", "discord:1001", "again")], "e2")
        result = compare_requests(
            left, right, right_capability={"unavailable_event_ids": {"e1"}, "reason": "no reaction history on this surface"}
        )
        self.assertTrue(result["equivalent"])
        self.assertEqual(result["unexplained"], [])
        self.assertTrue(result["explained"])

    def test_unexplained_missing_event_without_declared_capability_fails(self):
        left = _snapshot_from(
            [make_message("e1", "discord:1001", "hi"), make_message("e2", "discord:1001", "again")], "e2"
        )
        right = _snapshot_from([make_message("e2", "discord:1001", "again")], "e2")
        result = compare_requests(left, right)  # no capability declared
        self.assertFalse(result["equivalent"])


class TestComparatorContractIsReusableNotAParityClaim(unittest.TestCase):
    def test_comparator_result_carries_no_installed_surface_field(self):
        events = [make_message("e1", "discord:1001", "hi")]
        left = _snapshot_from(events, "e1")
        right = _snapshot_from(events, "e1")
        result = compare_requests(left, right)
        self.assertNotIn("real_surface_parity", result)
        self.assertNotIn("installed", result)


if __name__ == "__main__":
    unittest.main()
