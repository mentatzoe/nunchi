"""US3 equivalence/comparator tests (T021): reference-equivalence and the
reusable downstream comparator contract (S13, FR-012, SC-006)."""

from __future__ import annotations

from copy import deepcopy
import unittest

from evals.v2.observation.compare import compare_pages, compare_requests
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

    def test_reversed_authoritative_event_order_is_unexplained(self):
        left = _snapshot_from(
            [make_message("e1", "discord:1001", "hi"), make_message("e2", "discord:1001", "again")], "e2"
        )
        right = deepcopy(left)
        right["events"].reverse()
        result = compare_requests(left, right)
        self.assertFalse(result["equivalent"])
        self.assertTrue(any("authoritative event order" in diff for diff in result["unexplained"]))

    def test_one_sided_native_event_fact_is_unexplained(self):
        left = _snapshot_from([make_message("e1", "discord:1001", "hi")], "e1")
        right = deepcopy(left)
        right["events"][0].pop("text")
        result = compare_requests(left, right)
        self.assertFalse(result["equivalent"])
        self.assertTrue(any("events['e1'].text" in diff for diff in result["unexplained"]))

    def test_actor_divergence_is_unexplained(self):
        left = _snapshot_from([make_message("e1", "discord:1001", "hi")], "e1")
        right = deepcopy(left)
        right["actors"]["discord:1001"]["role"] = "different"
        result = compare_requests(left, right)
        self.assertFalse(result["equivalent"])
        self.assertTrue(any("actors.discord:1001.role" in diff for diff in result["unexplained"]))

    def test_semantic_coverage_divergence_is_unexplained(self):
        left = _snapshot_from([make_message("e1", "discord:1001", "hi")], "e1")
        right = deepcopy(left)
        right["coverage"]["has_gaps"] = True
        right["coverage"]["max_bytes"] = 1
        result = compare_requests(left, right)
        self.assertFalse(result["equivalent"])
        self.assertTrue(any("coverage.has_gaps" in diff for diff in result["unexplained"]))
        self.assertTrue(any("coverage.max_bytes" in diff for diff in result["unexplained"]))

    def test_request_local_request_id_is_intentionally_ignored(self):
        left = _snapshot_from([make_message("e1", "discord:1001", "hi")], "e1")
        right = deepcopy(left)
        right["request_id"] = "different-request-local-id"
        result = compare_requests(left, right)
        self.assertTrue(result["equivalent"])

    def test_continuation_page_semantics_are_compared(self):
        coverage = {
            "has_more_before": False, "has_more_after": True,
            "has_gaps": False, "truncated_by": ["events"],
            "continuity": "session-only", "has_restart_gap": False,
        }
        left = {
            "request_id": "left", "handle_id": "opaque-left",
            "direction": "after", "anchor_event_id": "e1",
            "events": [make_message("e2", "discord:1001", "next")],
            "coverage": coverage, "next_cursor": "opaque-cursor-left",
        }
        right = deepcopy(left)
        right["request_id"] = "right"
        right["handle_id"] = "opaque-right"
        right["next_cursor"] = None
        right["coverage"]["has_more_after"] = False
        result = compare_pages(left, right)
        self.assertFalse(result["equivalent"])
        self.assertTrue(any("next_cursor presence" in diff for diff in result["unexplained"]))
        self.assertTrue(any("coverage.has_more_after" in diff for diff in result["unexplained"]))


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
