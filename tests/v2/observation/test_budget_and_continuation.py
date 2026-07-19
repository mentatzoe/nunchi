"""US2 budget/continuation tests (T013): hard budgets, relation closure,
coverage, the accepted I-010A capability shape, I-010D fetch documents,
continuation binding/expiry/cursor, authoritative order, and exact-event
dedup. Slice-030 classifier projection behavior is out of scope here.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from nunchi.observation import (
    ContinuationError,
    ContinuationProvider,
    ObservationInputError,
    serialized_byte_size,
    validate_attention_request,
    validate_context_continuation,
)
from tests.v2.observation.helpers import make_message, make_provider, seed_room


def _room_with_events(count: int, provider=None):
    provider = provider or make_provider()
    events = [make_message(f"e{i}", "discord:1001", f"message {i}", timestamp=f"2026-07-17T01:00:{i:02d}Z") for i in range(1, count + 1)]
    seed_room(provider, events)
    return provider, events


class TestHardBudgets(unittest.TestCase):
    def test_event_cap_is_enforced_and_reported(self):
        provider, events = _room_with_events(10)
        snapshot = provider.snapshot(trigger_event_id="e5", max_events=3, max_bytes=65536)
        self.assertLessEqual(len(snapshot["events"]), 3)
        self.assertIn("events", snapshot["coverage"]["truncated_by"])

    def test_byte_cap_is_enforced_and_reported(self):
        provider, events = _room_with_events(5)
        snapshot = provider.snapshot(trigger_event_id="e3", max_events=100, max_bytes=1)
        self.assertEqual(len(snapshot["events"]), 1)  # only the trigger fits
        self.assertIn("bytes", snapshot["coverage"]["truncated_by"])

    def test_age_cap_is_enforced_and_reported(self):
        provider = make_provider()
        old = make_message("e1", "discord:1001", "old", timestamp="2026-07-17T00:00:00Z")
        trigger = make_message("e2", "discord:1001", "new", timestamp="2026-07-17T01:00:00Z")
        seed_room(provider, [old, trigger])
        snapshot = provider.snapshot(trigger_event_id="e2", max_events=100, max_bytes=65536, max_age_seconds=60)
        included_ids = [event["id"] for event in snapshot["events"]]
        self.assertNotIn("e1", included_ids)
        self.assertIn("age", snapshot["coverage"]["truncated_by"])

    def test_trigger_always_included_even_under_tight_caps(self):
        provider, events = _room_with_events(5)
        snapshot = provider.snapshot(trigger_event_id="e3", max_events=1, max_bytes=65536)
        self.assertEqual(snapshot["events"][0]["id"], "e3")


class TestEventVisibilityCoverage(unittest.TestCase):
    """FR-007 / M020-04: configured ``event_visibility`` must appear
    consistently in both snapshot and continuation-fetch coverage, and stay
    absent from both when unconfigured."""

    def test_event_visibility_present_in_snapshot_coverage_when_configured(self):
        provider, events = _room_with_events(3, provider=make_provider(event_visibility={"message": "history-and-live"}))
        snapshot = provider.snapshot(trigger_event_id="e3", max_events=10, max_bytes=65536)
        self.assertEqual(snapshot["coverage"]["event_visibility"], {"message": "history-and-live"})

    def test_event_visibility_absent_from_snapshot_coverage_when_unconfigured(self):
        provider, events = _room_with_events(3)
        snapshot = provider.snapshot(trigger_event_id="e3", max_events=10, max_bytes=65536)
        self.assertNotIn("event_visibility", snapshot["coverage"])

    def test_event_visibility_present_in_fetch_page_coverage_when_configured(self):
        provider, events = _room_with_events(3, provider=make_provider(event_visibility={"message": "history-and-live"}))
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e3", max_events_per_fetch=10, max_bytes_per_fetch=8192)
        page = continuation.fetch(
            {"request_id": "req-1", "handle_id": capability["handle_id"], "direction": "before", "max_events": 5, "max_bytes": 8192},
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual(page["coverage"]["event_visibility"], {"message": "history-and-live"})

    def test_event_visibility_absent_from_fetch_page_coverage_when_unconfigured(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e3", max_events_per_fetch=10, max_bytes_per_fetch=8192)
        page = continuation.fetch(
            {"request_id": "req-1", "handle_id": capability["handle_id"], "direction": "before", "max_events": 5, "max_bytes": 8192},
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertNotIn("event_visibility", page["coverage"])


class TestRelationClosure(unittest.TestCase):
    def test_reply_relation_target_is_prioritized_over_nearby_fill(self):
        provider = make_provider()
        far_reply_target = make_message("e1", "discord:1001", "original", timestamp="2026-07-17T01:00:00Z")
        filler = [
            make_message(f"e{i}", "discord:1001", f"filler {i}", timestamp=f"2026-07-17T01:0{i}:00Z")
            for i in range(2, 6)
        ]
        trigger = make_message(
            "e6", "discord:1001", "reply", reply_to_event_id="e1", timestamp="2026-07-17T01:06:00Z"
        )
        seed_room(provider, [far_reply_target, *filler, trigger])
        snapshot = provider.snapshot(trigger_event_id="e6", max_events=2, max_bytes=65536)
        included_ids = {event["id"] for event in snapshot["events"]}
        self.assertEqual(included_ids, {"e1", "e6"})  # relation closure wins over nearer filler

    def test_relation_target_that_cannot_fit_reports_honest_gap(self):
        provider = make_provider()
        target = make_message("e1", "discord:1001", "original")
        trigger = make_message("e2", "discord:1001", "reply", reply_to_event_id="e1")
        seed_room(provider, [target, trigger])
        snapshot = provider.snapshot(trigger_event_id="e2", max_events=1, max_bytes=65536)
        included_ids = {event["id"] for event in snapshot["events"]}
        self.assertEqual(included_ids, {"e2"})
        self.assertIn("events", snapshot["coverage"]["truncated_by"])
        # The literal reference remains in the trigger event even though the
        # target could not be fit.
        self.assertEqual(snapshot["events"][0]["reply_to_event_id"], "e1")


class TestCoverageAuthoritativeOrder(unittest.TestCase):
    def test_included_events_preserve_authoritative_ingestion_order(self):
        provider, events = _room_with_events(6)
        snapshot = provider.snapshot(trigger_event_id="e6", max_events=100, max_bytes=65536)
        ids = [event["id"] for event in snapshot["events"]]
        self.assertEqual(ids, sorted(ids, key=lambda x: int(x[1:])))


class TestAcceptedCapabilityShape(unittest.TestCase):
    def test_issued_capability_matches_accepted_i010a_shape(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=10, max_bytes_per_fetch=4096
        )
        self.assertEqual(
            capability["bound_to"],
            {
                "participant_id": provider.participant_id,
                "room_id": provider.room_id,
                "continuity_scope_id": provider.continuity_scope_id,
                "trigger_event_id": "e3",
            },
        )


class TestFetchDocuments(unittest.TestCase):
    def _issued(self, count=6, max_events_per_fetch=10, max_bytes_per_fetch=8192):
        provider, events = _room_with_events(count)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id=events[-1]["id"],
            max_events_per_fetch=max_events_per_fetch,
            max_bytes_per_fetch=max_bytes_per_fetch,
        )
        host_context = dict(capability["bound_to"])
        return provider, continuation, capability, host_context

    def test_before_fetch_returns_valid_page_in_authoritative_order(self):
        provider, continuation, capability, host_context = self._issued()
        request = {
            "request_id": "req-x",
            "handle_id": capability["handle_id"],
            "direction": "before",
            "max_events": 10,
            "max_bytes": 8192,
        }
        page = continuation.fetch(request, host_context=host_context, fetch_time="2026-07-17T01:00:00Z")
        self.assertEqual(validate_context_continuation(page), [])
        ids = [event["id"] for event in page["events"]]
        self.assertEqual(ids, sorted(ids, key=lambda x: int(x[1:])))

    def test_truncated_around_fetch_reports_truthful_side_specific_coverage(self):
        # L020-01: a truncated `around` page must report which side(s) have
        # more, not two nulls. e1..e10, anchor e5 (index 4), radius window
        # [e4, e5, e6] (indices 3-5) under a tight per-fetch cap leaves both
        # e1-e3 (before) and e7-e10 (after) unserved.
        provider, events = _room_with_events(10)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e5", max_events_per_fetch=3, max_bytes_per_fetch=8192)
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e5", "max_events": 3, "max_bytes": 8192,
        }
        page = continuation.fetch(request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z")
        self.assertIsInstance(page["coverage"]["has_more_before"], bool)
        self.assertIsInstance(page["coverage"]["has_more_after"], bool)
        self.assertTrue(page["coverage"]["has_more_before"])
        self.assertTrue(page["coverage"]["has_more_after"])

    def test_untruncated_around_fetch_reports_no_more_on_either_side(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e2", max_events_per_fetch=100, max_bytes_per_fetch=65536)
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e2", "max_events": 100, "max_bytes": 65536,
        }
        page = continuation.fetch(request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z")
        self.assertFalse(page["coverage"]["has_more_before"])
        self.assertFalse(page["coverage"]["has_more_after"])

    def test_around_fetch_cap_truncated_strictly_before_anchor_reports_has_more_before(self):
        # F1 CRITICAL (Phase 11, convergence-phase11-2026-07-19.md): the
        # ascending window scan can truncate at a candidate index strictly
        # before anchor_index, e.g. e1..e5, anchor e3 (index 2), a radius
        # wide enough to reach both buffer edges (around_window_start == 0)
        # but a byte cap sized to admit only e1. The old
        # ``has_more_before = around_window_start > 0`` formula ignored this
        # cap-based truncation and reported False even though e2, a genuine
        # before-anchor event, was never served.
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        one_event_bytes = serialized_byte_size(provider._events[0])
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=6, max_bytes_per_fetch=one_event_bytes,
        )
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e3", "max_events": 6, "max_bytes": one_event_bytes,
        }
        page = continuation.fetch(request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z")
        self.assertEqual([event["id"] for event in page["events"]], ["e1"])
        self.assertTrue(page["coverage"]["has_more_before"])  # e2 was never served
        self.assertTrue(page["coverage"]["has_more_after"])  # e3 (anchor)..e5 were never served either

    def test_around_cursor_progresses_without_overlap_and_exhausts(self):
        # H020-A1-01 / T055: a valid same-handle, same-direction cursor must
        # resume at the next unserved index inside the original anchor-bound
        # window rather than reconstructing and replaying page 1 forever.
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=2, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "around-page-1", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e3", "max_events": 2, "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page1["events"]], ["e2", "e3"])
        self.assertIn("next_cursor", page1)

        page2 = continuation.fetch(
            dict(request, request_id="around-page-2", cursor=page1["next_cursor"]),
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        ids1 = {event["id"] for event in page1["events"]}
        ids2 = {event["id"] for event in page2["events"]}
        self.assertEqual([event["id"] for event in page2["events"]], ["e4"])
        self.assertEqual(ids1 & ids2, set())
        self.assertNotIn("next_cursor", page2)

    def test_around_cursor_rejects_a_changed_anchor(self):
        provider, events = _room_with_events(6)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=4, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "around-anchor-1", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e3", "max_events": 2, "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                dict(
                    request,
                    request_id="around-anchor-2",
                    anchor_event_id="e5",
                    cursor=page1["next_cursor"],
                ),
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )

    def test_around_cursor_preserves_original_window_when_page_cap_changes(self):
        provider, events = _room_with_events(6)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=4, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "around-window-1", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e3", "max_events": 2, "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        page2 = continuation.fetch(
            dict(
                request,
                request_id="around-window-2",
                max_events=4,
                cursor=page1["next_cursor"],
            ),
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page2["events"]], ["e4"])
        self.assertNotIn("next_cursor", page2)

    def test_around_cursor_preserves_event_identity_across_retention_shift(self):
        provider = make_provider(retention_max_events=5)
        initial_events = [
            make_message(
                f"e{i}", "discord:1001", f"message {i}",
                timestamp=f"2026-07-17T01:00:0{i}Z",
            )
            for i in range(1, 6)
        ]
        seed_room(provider, initial_events)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=2, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "around-retention-1", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e3", "max_events": 2, "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page1["events"]], ["e2", "e3"])

        # Appending e6 evicts e1 and shifts every surviving deque index. The
        # cursor must still resolve the original window's remaining e4 by
        # identity; treating its opaque numeric tail as a live index serves e5.
        seed_room(
            provider,
            [make_message("e6", "discord:1001", "message 6", timestamp="2026-07-17T01:00:06Z")],
        )
        page2 = continuation.fetch(
            dict(request, request_id="around-retention-2", cursor=page1["next_cursor"]),
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page2["events"]], ["e4"])
        self.assertNotIn("next_cursor", page2)

    def test_before_cursor_fails_closed_when_retention_evicts_original_remainder(self):
        provider = make_provider(retention_max_events=5)
        seed_room(
            provider,
            [
                make_message(
                    f"e{i}", "discord:1001", f"message {i}",
                    timestamp=f"2026-07-17T01:00:0{i}Z",
                )
                for i in range(1, 6)
            ],
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e5", max_events_per_fetch=2, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "before-retention-1", "handle_id": capability["handle_id"],
            "direction": "before", "anchor_event_id": "e5", "max_events": 2,
            "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page1["events"]], ["e3", "e4"])

        # e6 evicts e1, which belonged to the cursor's original remainder.
        # Replaying a stale numeric position would duplicate e3 while claiming
        # gap-free coverage; identity-bound replay must reject instead.
        seed_room(
            provider,
            [make_message("e6", "discord:1001", "message 6", timestamp="2026-07-17T01:00:06Z")],
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                dict(request, request_id="before-retention-2", cursor=page1["next_cursor"]),
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )

    def test_after_cursor_preserves_original_remainder_across_retention_shift(self):
        provider = make_provider(retention_max_events=5)
        seed_room(
            provider,
            [
                make_message(
                    f"e{i}", "discord:1001", f"message {i}",
                    timestamp=f"2026-07-17T01:00:0{i}Z",
                )
                for i in range(1, 6)
            ],
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e2", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "after-retention-1", "handle_id": capability["handle_id"],
            "direction": "after", "anchor_event_id": "e2", "max_events": 1,
            "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page1["events"]], ["e3"])

        # e6 evicts e1 and shifts e4 from index 3 to index 2. Replay must serve
        # the original e4/e5 remainder, not the objects now occupying old
        # numeric positions, and must not admit later arrival e6.
        seed_room(
            provider,
            [make_message("e6", "discord:1001", "message 6", timestamp="2026-07-17T01:00:06Z")],
        )
        page2 = continuation.fetch(
            dict(request, request_id="after-retention-2", cursor=page1["next_cursor"]),
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page2["events"]], ["e4"])
        page3 = continuation.fetch(
            dict(request, request_id="after-retention-3", cursor=page2["next_cursor"]),
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual([event["id"] for event in page3["events"]], ["e5"])
        self.assertNotIn("next_cursor", page3)

    def test_cursor_chain_reuses_one_window_and_reclaims_consumed_state(self):
        provider, events = _room_with_events(20)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e20", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "bounded-chain-1", "handle_id": capability["handle_id"],
            "direction": "before", "anchor_event_id": "e20", "max_events": 1,
            "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        cursor1 = page1["next_cursor"]
        window1 = continuation._cursor_windows[capability["handle_id"]][cursor1]["window_event_refs"]
        self.assertIsInstance(window1, tuple)
        self.assertEqual(len(continuation._cursor_windows[capability["handle_id"]]), 1)

        page2 = continuation.fetch(
            dict(request, request_id="bounded-chain-2", cursor=cursor1),
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        cursor2 = page2["next_cursor"]
        active = continuation._cursor_windows[capability["handle_id"]]
        self.assertNotIn(cursor1, active)
        self.assertIs(active[cursor2]["window_event_refs"], window1)
        self.assertEqual(len(active), 1)
        self.assertEqual(continuation._cursors[capability["handle_id"]], {cursor2})
        self.assertNotIn("cursors", capability)
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                dict(request, request_id="bounded-chain-replay", cursor=cursor1),
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )

        page = page2
        page_number = 3
        while "next_cursor" in page:
            page = continuation.fetch(
                dict(
                    request,
                    request_id=f"bounded-chain-{page_number}",
                    cursor=page["next_cursor"],
                ),
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )
            self.assertLessEqual(
                len(continuation._cursor_windows[capability["handle_id"]]), 1,
            )
            page_number += 1
        self.assertEqual(continuation._cursor_windows[capability["handle_id"]], {})
        self.assertEqual(continuation._cursors[capability["handle_id"]], set())
        self.assertNotIn("cursors", capability)

    def test_active_cursor_limit_rejects_a_second_independent_sequence(self):
        provider, events = _room_with_events(8)
        continuation = ContinuationProvider(provider, max_active_cursors_per_handle=1)
        capability = continuation.issue(
            trigger_event_id="e8", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        continuation.fetch(
            {
                "request_id": "active-limit-1", "handle_id": capability["handle_id"],
                "direction": "before", "anchor_event_id": "e8", "max_events": 1,
                "max_bytes": 8192,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                {
                    "request_id": "active-limit-2", "handle_id": capability["handle_id"],
                    "direction": "around", "anchor_event_id": "e4", "max_events": 1,
                    "max_bytes": 8192,
                },
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )
        self.assertEqual(len(continuation._cursor_windows[capability["handle_id"]]), 1)

    def test_handle_limit_and_revoke_release_all_state(self):
        provider, events = _room_with_events(4)
        continuation = ContinuationProvider(provider, max_handles=1)
        capability = continuation.issue(
            trigger_event_id="e4", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        page = continuation.fetch(
            {
                "request_id": "revoke-1", "handle_id": capability["handle_id"],
                "direction": "before", "max_events": 1, "max_bytes": 8192,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        with self.assertRaises(ContinuationError):
            continuation.issue(
                trigger_event_id="e4", max_events_per_fetch=1, max_bytes_per_fetch=8192,
            )
        continuation.revoke(capability["handle_id"])
        self.assertFalse(continuation.revoke(capability["handle_id"]))
        self.assertNotIn(capability["handle_id"], continuation._capabilities)
        self.assertNotIn(capability["handle_id"], continuation._cursor_windows)
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                {
                    "request_id": "revoke-2", "handle_id": capability["handle_id"],
                    "direction": "before", "max_events": 1, "max_bytes": 8192,
                    "cursor": page["next_cursor"],
                },
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )
        replacement = continuation.issue(
            trigger_event_id="e4", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        self.assertNotEqual(replacement["handle_id"], capability["handle_id"])

    def test_expired_fetch_rejects_and_reclaims_handle_state(self):
        provider, events = _room_with_events(4)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e4", max_events_per_fetch=1, max_bytes_per_fetch=8192,
            expires_at="2026-07-17T01:00:00Z",
        )
        page = continuation.fetch(
            {
                "request_id": "expiry-cleanup-1", "handle_id": capability["handle_id"],
                "direction": "before", "max_events": 1, "max_bytes": 8192,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-17T00:30:00Z",
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                {
                    "request_id": "expiry-cleanup-2", "handle_id": capability["handle_id"],
                    "direction": "before", "max_events": 1, "max_bytes": 8192,
                    "cursor": page["next_cursor"],
                },
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )
        self.assertNotIn(capability["handle_id"], continuation._capabilities)
        self.assertNotIn(capability["handle_id"], continuation._cursor_windows)

    def test_expiring_capability_requires_valid_aware_times(self):
        provider, events = _room_with_events(3)
        for expires_at in ("not-a-time", "2027-01-01T00:00:00"):
            with self.subTest(expires_at=expires_at), self.assertRaises(ValueError):
                ContinuationProvider(provider).issue(
                    trigger_event_id="e3", max_events_per_fetch=1,
                    max_bytes_per_fetch=8192, expires_at=expires_at,
                )

        for fetch_time in (None, "not-a-time", "2026-07-19T09:00:00"):
            with self.subTest(fetch_time=fetch_time):
                continuation = ContinuationProvider(provider)
                capability = continuation.issue(
                    trigger_event_id="e3", max_events_per_fetch=1,
                    max_bytes_per_fetch=8192,
                    expires_at="2027-01-01T00:00:00Z",
                )
                request = {
                    "request_id": "expiry-validity", "handle_id": capability["handle_id"],
                    "direction": "before", "max_events": 1, "max_bytes": 8192,
                }
                kwargs = {} if fetch_time is None else {"fetch_time": fetch_time}
                with self.assertRaises(ContinuationError):
                    continuation.fetch(
                        request, host_context=capability["bound_to"], **kwargs,
                    )

    def test_returned_capability_mutation_cannot_rewrite_authority(self):
        provider, events = _room_with_events(4)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e1", max_events_per_fetch=1,
            max_bytes_per_fetch=8192, can_fetch_after=False,
            expires_at="2027-01-01T00:00:00Z",
        )
        internal_before = deepcopy(continuation._capabilities[capability["handle_id"]])
        capability["bound_to"]["room_id"] = "attacker-room"
        capability["can_fetch_after"] = True
        capability["max_events_per_fetch"] = 99
        capability["expires_at"] = "2028-01-01T00:00:00Z"
        self.assertEqual(continuation._capabilities[capability["handle_id"]], internal_before)
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                {
                    "request_id": "mutated-authority", "handle_id": capability["handle_id"],
                    "direction": "after", "max_events": 3, "max_bytes": 8192,
                },
                host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
            )

    def test_cursor_minting_keeps_returned_capability_wire_clean(self):
        provider, events = _room_with_events(4)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e4", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        original = deepcopy(capability)
        page = continuation.fetch(
            {
                "request_id": "wire-clean", "handle_id": capability["handle_id"],
                "direction": "before", "max_events": 1, "max_bytes": 8192,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
        )
        self.assertIn("next_cursor", page)
        self.assertEqual(capability, original)
        self.assertNotIn("cursors", capability)
        attention_request = provider.snapshot(
            trigger_event_id="e4", max_events=4, max_bytes=65536,
        )
        attention_request["continuation"] = capability
        self.assertEqual(validate_attention_request(attention_request), [])

    def test_cursor_rejects_reingested_remainder_id_instance(self):
        provider, events = _room_with_events(5, provider=make_provider(retention_max_events=5))
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e5", max_events_per_fetch=3, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "instance-1", "handle_id": capability["handle_id"],
            "direction": "before", "anchor_event_id": "e5", "max_events": 3,
            "max_bytes": 8192,
        }
        page = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
        )
        provider.ingest({
            "delivery_id": "delivery:e6", "disposition": "candidate-event",
            "authorized": True, "event": make_message("e6", "discord:1001", "six"),
            "actors": {},
        })
        provider.ingest({
            "delivery_id": "delivery:e1-replacement", "disposition": "candidate-event",
            "authorized": True,
            "event": make_message("e1", "discord:1001", "REPLACEMENT"), "actors": {},
        })
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                dict(request, request_id="instance-2", cursor=page["next_cursor"]),
                host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
            )

    def test_cursor_rejects_reingested_anchor_id_instance(self):
        provider, events = _room_with_events(3, provider=make_provider(retention_max_events=3))
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e1", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "anchor-instance-1", "handle_id": capability["handle_id"],
            "direction": "after", "anchor_event_id": "e1", "max_events": 1,
            "max_bytes": 8192,
        }
        page = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
        )
        provider.ingest({
            "delivery_id": "delivery:e4", "disposition": "candidate-event",
            "authorized": True, "event": make_message("e4", "discord:1001", "four"),
            "actors": {},
        })
        provider.ingest({
            "delivery_id": "delivery:e1-replacement", "disposition": "candidate-event",
            "authorized": True,
            "event": make_message("e1", "discord:1001", "REPLACEMENT"), "actors": {},
        })
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                dict(request, request_id="anchor-instance-2", cursor=page["next_cursor"]),
                host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
            )

    def test_after_final_page_discloses_later_arrival_without_admitting_it(self):
        provider, events = _room_with_events(5, provider=make_provider(retention_max_events=10))
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e2", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "after-later-1", "handle_id": capability["handle_id"],
            "direction": "after", "anchor_event_id": "e2", "max_events": 1,
            "max_bytes": 8192,
        }
        page = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
        )
        provider.ingest({
            "delivery_id": "delivery:e6", "disposition": "candidate-event",
            "authorized": True, "event": make_message("e6", "discord:1001", "six"),
            "actors": {},
        })
        while "next_cursor" in page:
            page = continuation.fetch(
                dict(request, request_id=f"after-later-{page['events'][0]['id']}", cursor=page["next_cursor"]),
                host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
            )
        self.assertEqual([event["id"] for event in page["events"]], ["e5"])
        self.assertTrue(page["coverage"]["has_more_after"])
        self.assertNotIn("e6", [event["id"] for event in page["events"]])

    def test_around_final_page_discloses_later_arrival_after_retention_shift(self):
        provider, events = _room_with_events(5, provider=make_provider(retention_max_events=5))
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e4", max_events_per_fetch=2, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "around-later-1", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e4", "max_events": 2,
            "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
        )
        provider.ingest({
            "delivery_id": "delivery:e6", "disposition": "candidate-event",
            "authorized": True, "event": make_message("e6", "discord:1001", "six"),
            "actors": {},
        })
        page2 = continuation.fetch(
            dict(request, request_id="around-later-2", cursor=page1["next_cursor"]),
            host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
        )
        self.assertEqual([event["id"] for event in page2["events"]], ["e5"])
        self.assertTrue(page2["coverage"]["has_more_after"])
        self.assertNotIn("e6", [event["id"] for event in page2["events"]])

    def test_fetch_rejects_when_byte_cap_cannot_admit_the_next_event(self):
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=6, max_bytes_per_fetch=8192,
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                {
                    "request_id": "no-progress-byte-cap", "handle_id": capability["handle_id"],
                    "direction": "around", "anchor_event_id": "e3", "max_events": 6, "max_bytes": 1,
                },
                host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
            )

    def test_continuation_fetch_reports_event_only_truncation(self):
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=2, max_bytes_per_fetch=8192,
        )
        page = continuation.fetch(
            {
                "request_id": "event-only", "handle_id": capability["handle_id"],
                "direction": "around", "anchor_event_id": "e3", "max_events": 2, "max_bytes": 8192,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual(page["coverage"]["truncated_by"], ["events"])

    def test_continuation_fetch_reports_byte_only_truncation(self):
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        one_event_bytes = serialized_byte_size(provider._events[0])
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=6, max_bytes_per_fetch=one_event_bytes,
        )
        page = continuation.fetch(
            {
                "request_id": "byte-only", "handle_id": capability["handle_id"],
                "direction": "around", "anchor_event_id": "e3", "max_events": 6,
                "max_bytes": one_event_bytes,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual(page["coverage"]["truncated_by"], ["bytes"])

    def test_continuation_fetch_reports_both_truncation_causes(self):
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        one_event_bytes = serialized_byte_size(provider._events[1])
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=1, max_bytes_per_fetch=one_event_bytes,
        )
        page = continuation.fetch(
            {
                "request_id": "both-causes", "handle_id": capability["handle_id"],
                "direction": "around", "anchor_event_id": "e3", "max_events": 1,
                "max_bytes": one_event_bytes,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual(page["coverage"]["truncated_by"], ["events", "bytes"])

    def test_around_fetch_requires_anchor(self):
        provider, continuation, capability, host_context = self._issued()
        request = {
            "request_id": "req-x",
            "handle_id": capability["handle_id"],
            "direction": "around",
            "anchor_event_id": "e3",
            "max_events": 4,
            "max_bytes": 8192,
        }
        page = continuation.fetch(request, host_context=host_context, fetch_time="2026-07-17T01:00:00Z")
        self.assertIn("e3", [event["id"] for event in page["events"]])


class TestContinuationBindingAndExpiry(unittest.TestCase):
    def test_cross_binding_fetch_rejects(self):
        provider, continuation, capability, host_context = TestFetchDocuments()._issued()
        bad_context = dict(host_context, room_id="different-room")
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "before", "max_events": 5, "max_bytes": 4096,
        }
        with self.assertRaises(ContinuationError):
            continuation.fetch(request, host_context=bad_context, fetch_time="2026-07-17T01:00:00Z")

    def test_expired_handle_rejects(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=10, max_bytes_per_fetch=4096,
            expires_at="2026-07-17T00:00:00Z",
        )
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "before", "max_events": 5, "max_bytes": 4096,
        }
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z"
            )

    def test_unauthorized_direction_rejects(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=10, max_bytes_per_fetch=4096,
            can_fetch_after=False,
        )
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "after", "max_events": 5, "max_bytes": 4096,
        }
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z"
            )

    def test_over_cap_request_rejects(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", max_events_per_fetch=2, max_bytes_per_fetch=4096,
        )
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "before", "max_events": 50, "max_bytes": 4096,
        }
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z"
            )

    def test_cross_handle_cursor_reuse_rejects(self):
        provider, events = _room_with_events(6)
        continuation = ContinuationProvider(provider)
        cap_a = continuation.issue(trigger_event_id="e6", max_events_per_fetch=1, max_bytes_per_fetch=4096)
        cap_b = continuation.issue(trigger_event_id="e6", max_events_per_fetch=10, max_bytes_per_fetch=4096)
        first_page = continuation.fetch(
            {"request_id": "r1", "handle_id": cap_a["handle_id"], "direction": "before", "max_events": 1, "max_bytes": 4096},
            host_context=cap_a["bound_to"], fetch_time="2026-07-17T01:00:00Z",
        )
        stolen_cursor = first_page["next_cursor"]
        request = {
            "request_id": "r2", "handle_id": cap_b["handle_id"], "direction": "before",
            "max_events": 5, "max_bytes": 4096, "cursor": stolen_cursor,
        }
        with self.assertRaises(ContinuationError):
            continuation.fetch(request, host_context=cap_b["bound_to"], fetch_time="2026-07-17T01:00:00Z")

    def test_cross_direction_cursor_replay_rejects(self):
        # H020-01: a cursor minted by a 'before' fetch must not be
        # replayable under 'after' for the same handle — that would return
        # an event already served by the first page (e.g. ['e4', 'e5']
        # followed by ['e3', 'e4']).
        provider, events = _room_with_events(6)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e6", max_events_per_fetch=2, max_bytes_per_fetch=8192)
        page1 = continuation.fetch(
            {"request_id": "r1", "handle_id": capability["handle_id"], "direction": "before", "max_events": 2, "max_bytes": 8192},
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z",
        )
        self.assertIn("next_cursor", page1)
        request2 = {
            "request_id": "r2", "handle_id": capability["handle_id"], "direction": "after",
            "max_events": 2, "max_bytes": 8192, "cursor": page1["next_cursor"],
        }
        with self.assertRaises(ContinuationError):
            continuation.fetch(request2, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z")

    def test_same_direction_cursor_replay_still_paginates(self):
        provider, events = _room_with_events(6)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e6", max_events_per_fetch=2, max_bytes_per_fetch=8192)
        page1 = continuation.fetch(
            {"request_id": "r1", "handle_id": capability["handle_id"], "direction": "before", "max_events": 2, "max_bytes": 8192},
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z",
        )
        request2 = {
            "request_id": "r2", "handle_id": capability["handle_id"], "direction": "before",
            "max_events": 2, "max_bytes": 8192, "cursor": page1["next_cursor"],
        }
        page2 = continuation.fetch(request2, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z")
        ids_page1 = {event["id"] for event in page1["events"]}
        ids_page2 = {event["id"] for event in page2["events"]}
        self.assertEqual(ids_page1 & ids_page2, set())

    def test_cursor_replay_continues_without_duplication(self):
        provider, events = _room_with_events(6)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e6", max_events_per_fetch=2, max_bytes_per_fetch=8192)
        page1 = continuation.fetch(
            {"request_id": "r1", "handle_id": capability["handle_id"], "direction": "before", "max_events": 2, "max_bytes": 8192},
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z",
        )
        self.assertIn("next_cursor", page1)
        page2 = continuation.fetch(
            {
                "request_id": "r2", "handle_id": capability["handle_id"], "direction": "before",
                "max_events": 2, "max_bytes": 8192, "cursor": page1["next_cursor"],
            },
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z",
        )
        ids_page1 = {event["id"] for event in page1["events"]}
        ids_page2 = {event["id"] for event in page2["events"]}
        self.assertEqual(ids_page1 & ids_page2, set())  # exact-event dedup across pages


class TestRetentionCoupledAuxiliaryState(unittest.TestCase):
    def test_returned_documents_cannot_mutate_provider_or_source_request(self):
        provider = make_provider(retention_max_events=3)
        event1 = make_message("e1", "discord:1001", "original one")
        event2 = make_message("e2", "discord:1002", "original two")
        provider.ingest({
            "delivery_id": "delivery:e1", "disposition": "candidate-event",
            "authorized": True, "event": event1,
            "actors": {"discord:1001": {"display_name": "actor one"}},
        })
        provider.ingest({
            "delivery_id": "delivery:e2", "disposition": "candidate-event",
            "authorized": True, "event": event2,
            "actors": {"discord:1002": {"display_name": "actor two"}},
        })
        snapshot = provider.snapshot(trigger_event_id="e2", max_events=2, max_bytes=65536)
        snapshot_e1 = next(event for event in snapshot["events"] if event["id"] == "e1")
        snapshot_e1["text"] = "MUTATED SNAPSHOT"
        snapshot["actors"]["discord:1001"]["display_name"] = "MUTATED"
        retained_e1 = next(event for event in provider._events if event["id"] == "e1")
        self.assertEqual(retained_e1["text"], "original one")
        self.assertEqual(provider._actors["discord:1001"]["display_name"], "actor one")

        source_request = provider.snapshot(
            trigger_event_id="e2", max_events=2, max_bytes=65536,
        )
        receipt = provider.build_observation_receipt(source_request)
        receipt["body"]["coverage"]["max_events"] = 999
        self.assertEqual(source_request["coverage"]["max_events"], 2)

        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e2", max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        page = continuation.fetch(
            {
                "request_id": "copy-page", "handle_id": capability["handle_id"],
                "direction": "before", "max_events": 1, "max_bytes": 8192,
            },
            host_context=capability["bound_to"], fetch_time="2026-07-19T09:00:00Z",
        )
        page["events"][0]["text"] = "MUTATED PAGE"
        page["actors"]["discord:1001"]["display_name"] = "MUTATED"
        self.assertEqual(retained_e1["text"], "original one")
        self.assertEqual(provider._actors["discord:1001"]["display_name"], "actor one")

    def test_ingest_copies_event_and_actor_inputs_into_private_state(self):
        provider = make_provider(retention_max_events=3)
        event = make_message("e1", "discord:1001", "original")
        actors = {"discord:1001": {"display_name": "original-name"}}
        provider.ingest({
            "delivery_id": "delivery:copy", "disposition": "candidate-event",
            "authorized": True, "event": event, "actors": actors,
        })
        event["text"] = "MUTATED"
        event["mentioned_actor_ids"].append("discord:attacker")
        actors["discord:1001"]["display_name"] = "MUTATED"
        retained = provider._events[0]
        self.assertEqual(retained["text"], "original")
        self.assertEqual(retained["mentioned_actor_ids"], [])
        self.assertEqual(provider._actors["discord:1001"]["display_name"], "original-name")

    def test_delivery_generation_and_actor_state_follow_retained_events(self):
        provider = make_provider(retention_max_events=3)
        for i in range(10):
            actor_id = f"discord:{1000 + i}"
            unrelated_id = f"discord:unrelated-{i}"
            provider.ingest({
                "delivery_id": f"delivery:{i}", "disposition": "candidate-event",
                "authorized": True,
                "event": make_message(f"e{i}", actor_id, f"message {i}"),
                "actors": {
                    actor_id: {"display_name": f"actor {i}"},
                    unrelated_id: {"display_name": "must not persist"},
                },
            })
        retained_actor_ids = {event["author_id"] for event in provider._events}
        self.assertEqual(len(provider._events), 3)
        self.assertEqual(len(provider._seen_delivery_ids), 3)
        self.assertEqual(len(provider._event_generations), 3)
        self.assertEqual(set(provider._actors), retained_actor_ids | {provider.actor_id})
        self.assertFalse(any("unrelated" in actor_id for actor_id in provider._actors))

    def test_invalid_candidate_does_not_poison_delivery_dedup(self):
        provider = make_provider(retention_max_events=3)
        with self.assertRaises(ObservationInputError):
            provider.ingest({
                "delivery_id": "delivery:retry", "disposition": "candidate-event",
                "authorized": True, "event": {"id": "broken"}, "actors": {},
            })
        outcome = provider.ingest({
            "delivery_id": "delivery:retry", "disposition": "candidate-event",
            "authorized": True,
            "event": make_message("e1", "discord:1001", "valid retry"), "actors": {},
        })
        self.assertEqual(outcome, "observed")

        with self.assertRaises(ObservationInputError):
            provider.ingest({
                "delivery_id": "delivery:actor-retry", "disposition": "candidate-event",
                "authorized": True,
                "event": make_message("e2", "discord:1002", "bad actor facts"),
                "actors": {"discord:1002": {"unexpected": "field"}},
            })
        actor_retry = provider.ingest({
            "delivery_id": "delivery:actor-retry", "disposition": "candidate-event",
            "authorized": True,
            "event": make_message("e2", "discord:1002", "valid actor retry"),
            "actors": {"discord:1002": {"display_name": "Actor Two"}},
        })
        self.assertEqual(actor_retry, "observed")

    def test_delivery_id_leaves_duplicate_set_when_its_event_is_evicted(self):
        provider = make_provider(retention_max_events=2)
        for delivery_id, event_id in (("delivery:1", "e1"), ("delivery:2", "e2")):
            self.assertEqual(
                provider.ingest({
                    "delivery_id": delivery_id, "disposition": "candidate-event",
                    "authorized": True,
                    "event": make_message(event_id, "discord:1001", event_id), "actors": {},
                }),
                "observed",
            )
        self.assertEqual(
            provider.ingest({
                "delivery_id": "delivery:1", "disposition": "candidate-event",
                "authorized": True,
                "event": make_message("duplicate", "discord:1001", "duplicate"), "actors": {},
            }),
            "duplicate-retained",
        )
        provider.ingest({
            "delivery_id": "delivery:3", "disposition": "candidate-event",
            "authorized": True,
            "event": make_message("e3", "discord:1001", "e3"), "actors": {},
        })
        self.assertEqual(
            provider.ingest({
                "delivery_id": "delivery:1", "disposition": "candidate-event",
                "authorized": True,
                "event": make_message("e4", "discord:1001", "e4"), "actors": {},
            }),
            "observed",
        )


if __name__ == "__main__":
    unittest.main()
