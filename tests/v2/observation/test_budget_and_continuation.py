"""US2 budget/continuation tests (T013): hard budgets, relation closure,
coverage, the accepted I-010A capability shape, I-010D fetch documents,
continuation binding/expiry/cursor, authoritative order, and exact-event
dedup. Slice-030 classifier projection behavior is out of scope here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
import unittest
from unittest.mock import patch

import nunchi.observation as observation_module
from evals.v2.observation.run_scenes import run_budget_sweep
from nunchi.observation import (
    ContinuationError,
    ContinuationProvider,
    ObservationInputError,
    serialized_byte_size,
    validate_attention_request,
    validate_context_continuation,
)
from tests.v2.observation.helpers import make_message, make_provider, make_reaction, seed_room


def _room_with_events(count: int, provider=None):
    provider = provider or make_provider()
    start = datetime(2026, 7, 17, 1, 0, 0, tzinfo=timezone.utc)
    events = [
        make_message(
            f"e{i}",
            "discord:1001",
            f"message {i}",
            timestamp=(start + timedelta(seconds=i)).isoformat().replace("+00:00", "Z"),
        )
        for i in range(1, count + 1)
    ]
    seed_room(provider, events)
    return provider, events


class TestHardBudgets(unittest.TestCase):
    def test_event_cap_is_enforced_and_reported(self):
        provider, events = _room_with_events(10)
        snapshot = provider.snapshot(trigger_event_id="e5", max_events=3, max_bytes=65536)
        self.assertLessEqual(len(snapshot["events"]), 3)
        self.assertIn("events", snapshot["coverage"]["truncated_by"])

    def test_trigger_larger_than_byte_cap_fails_closed(self):
        provider, events = _room_with_events(5)
        with self.assertRaises(ObservationInputError):
            provider.snapshot(trigger_event_id="e3", max_events=100, max_bytes=1)

    def test_budget_evidence_never_passes_an_accepted_event_byte_overrun(self):
        overruns = [
            row
            for row in run_budget_sweep()
            if row.get("observed") != "reject"
            and row.get("receipt_byte_count", 0) > row["configured_max_bytes"]
        ]
        self.assertEqual(overruns, [])

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
        capability = continuation.issue(trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=10, max_bytes_per_fetch=8192)
        page = continuation.fetch(
            {"request_id": "req-1", "handle_id": capability["handle_id"], "direction": "before", "max_events": 5, "max_bytes": 8192},
            host_context=capability["bound_to"], fetch_time="2026-07-17T01:30:00Z",
        )
        self.assertEqual(page["coverage"]["event_visibility"], {"message": "history-and-live"})

    def test_event_visibility_absent_from_fetch_page_coverage_when_unconfigured(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=10, max_bytes_per_fetch=8192)
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
    def test_issuance_requires_originating_request_event_ids(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        with self.assertRaises(ValueError):
            continuation.issue(
                trigger_event_id="e3", max_events_per_fetch=10,
                max_bytes_per_fetch=4096,
            )

    def test_issued_capability_matches_accepted_i010a_shape(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", originating_event_ids=["e3"],
            max_events_per_fetch=10, max_bytes_per_fetch=4096,
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
        self.assertNotIn("originating_event_ids", capability)


class TestFetchDocuments(unittest.TestCase):
    def _issued(self, count=6, max_events_per_fetch=10, max_bytes_per_fetch=8192):
        provider, events = _room_with_events(count)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id=events[-1]["id"],
            originating_event_ids=[events[-1]["id"]],
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

    def test_host_context_requires_the_exact_closed_binding_shape(self):
        invalid_contexts = {
            "additional-property": lambda context: dict(
                context, unexpected_tenant="other",
            ),
            "missing-property": lambda context: {
                key: value for key, value in context.items()
                if key != "continuity_scope_id"
            },
            "wrong-value": lambda context: dict(context, room_id="other-room"),
            "malformed": lambda context: {"participant_id": [context["participant_id"]]},
        }
        for label, mutate in invalid_contexts.items():
            with self.subTest(label=label):
                _, continuation, capability, host_context = self._issued(count=3)
                with self.assertRaises(ContinuationError):
                    continuation.fetch(
                        {
                            "request_id": f"closed-binding-{label}",
                            "handle_id": capability["handle_id"],
                            "direction": "before", "max_events": 10,
                            "max_bytes": 8192,
                        },
                        host_context=mutate(host_context),
                        fetch_time="2026-07-17T01:00:00Z",
                    )
                self.assertEqual(
                    continuation._cursors[capability["handle_id"]], set(),
                )
                self.assertEqual(
                    continuation._cursor_windows[capability["handle_id"]], {},
                )

    def test_additional_host_context_rejection_does_not_consume_cursor(self):
        _, continuation, capability, host_context = self._issued(
            count=6, max_events_per_fetch=1,
        )
        request = {
            "request_id": "closed-binding-page-1",
            "handle_id": capability["handle_id"],
            "direction": "before", "max_events": 1, "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=host_context,
            fetch_time="2026-07-17T01:00:00Z",
        )
        cursor = page1["next_cursor"]
        page2_request = dict(
            request, request_id="closed-binding-page-2", cursor=cursor,
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                page2_request,
                host_context=dict(host_context, unexpected_tenant="other"),
                fetch_time="2026-07-17T01:00:00Z",
            )
        page2 = continuation.fetch(
            page2_request, host_context=host_context,
            fetch_time="2026-07-17T01:00:00Z",
        )
        self.assertEqual([event["id"] for event in page2["events"]], ["e4"])

    def test_page_overlapping_originating_request_rejects_before_cursor_commit(self):
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e5", originating_event_ids=["e3", "e4", "e5"],
            max_events_per_fetch=10, max_bytes_per_fetch=8192,
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                {
                    "request_id": "origin-overlap", "handle_id": capability["handle_id"],
                    "direction": "before", "max_events": 10, "max_bytes": 8192,
                },
                host_context=capability["bound_to"],
                fetch_time="2026-07-17T01:30:00Z",
            )
        self.assertEqual(continuation._cursors[capability["handle_id"]], set())
        self.assertEqual(continuation._cursor_windows[capability["handle_id"]], {})

    def test_truncated_around_fetch_reports_truthful_side_specific_coverage(self):
        # L020-01: a truncated `around` page must report which side(s) have
        # more, not two nulls. e1..e10, anchor e5 (index 4), radius window
        # [e4, e5, e6] (indices 3-5) under a tight per-fetch cap leaves both
        # e1-e3 (before) and e7-e10 (after) unserved.
        provider, events = _room_with_events(10)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e10", originating_event_ids=["e10"], max_events_per_fetch=3, max_bytes_per_fetch=8192)
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e5", "max_events": 3, "max_bytes": 8192,
        }
        page = continuation.fetch(request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z")
        self.assertIsInstance(page["coverage"]["has_more_before"], bool)
        self.assertIsInstance(page["coverage"]["has_more_after"], bool)
        self.assertTrue(page["coverage"]["has_more_before"])
        self.assertTrue(page["coverage"]["has_more_after"])

    def test_full_buffer_around_fetch_rejects_origin_overlap(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id="e2", originating_event_ids=["e2"], max_events_per_fetch=100, max_bytes_per_fetch=65536)
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e2", "max_events": 100, "max_bytes": 65536,
        }
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                request, host_context=capability["bound_to"],
                fetch_time="2026-07-17T01:00:00Z",
            )

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
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=2, max_bytes_per_fetch=one_event_bytes,
        )
        request = {
            "request_id": "req-x", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e3", "max_events": 2, "max_bytes": one_event_bytes,
        }
        page = continuation.fetch(request, host_context=capability["bound_to"], fetch_time="2026-07-17T01:00:00Z")
        self.assertEqual([event["id"] for event in page["events"]], ["e2"])
        self.assertTrue(page["coverage"]["has_more_before"])  # e1 is outside the fixed window
        self.assertTrue(page["coverage"]["has_more_after"])  # e3 (anchor) and e4 were never served

    def test_around_cursor_progresses_without_overlap_and_exhausts(self):
        # H020-A1-01 / T055: a valid same-handle, same-direction cursor must
        # resume at the next unserved index inside the original anchor-bound
        # window rather than reconstructing and replaying page 1 forever.
        provider, events = _room_with_events(5)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=2, max_bytes_per_fetch=8192,
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
            trigger_event_id="e6", originating_event_ids=["e6"], max_events_per_fetch=4, max_bytes_per_fetch=8192,
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
            trigger_event_id="e6", originating_event_ids=["e6"], max_events_per_fetch=4, max_bytes_per_fetch=8192,
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
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=2, max_bytes_per_fetch=8192,
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
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=2, max_bytes_per_fetch=8192,
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
            trigger_event_id="e2", originating_event_ids=["e2"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
            trigger_event_id="e20", originating_event_ids=["e20"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
            trigger_event_id="e8", originating_event_ids=["e8"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
            trigger_event_id="e4", originating_event_ids=["e4"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
                trigger_event_id="e4", originating_event_ids=["e4"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
            trigger_event_id="e4", originating_event_ids=["e4"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        self.assertNotEqual(replacement["handle_id"], capability["handle_id"])

    def test_expired_fetch_rejects_and_reclaims_handle_state(self):
        provider, events = _room_with_events(4)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e4", originating_event_ids=["e4"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
                    trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=1,
                    max_bytes_per_fetch=8192, expires_at=expires_at,
                )

        for fetch_time in (None, "not-a-time", "2026-07-19T09:00:00"):
            with self.subTest(fetch_time=fetch_time):
                continuation = ContinuationProvider(provider)
                capability = continuation.issue(
                    trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=1,
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

    def test_exact_expiry_instant_rejects_and_reclaims_handle(self):
        provider, events = _room_with_events(3)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=1,
            max_bytes_per_fetch=8192, expires_at="2026-07-19T10:30:00Z",
        )
        with self.assertRaises(ContinuationError):
            continuation.fetch(
                {
                    "request_id": "expiry-equality", "handle_id": capability["handle_id"],
                    "direction": "before", "max_events": 1, "max_bytes": 8192,
                },
                host_context=capability["bound_to"],
                fetch_time="2026-07-19T10:30:00Z",
            )
        self.assertNotIn(capability["handle_id"], continuation._capabilities)
        self.assertNotIn(capability["handle_id"], continuation._cursor_windows)

    def test_returned_capability_mutation_cannot_rewrite_authority(self):
        provider, events = _room_with_events(4)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e1", originating_event_ids=["e1"], max_events_per_fetch=1,
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
            trigger_event_id="e4", originating_event_ids=["e4"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=3, max_bytes_per_fetch=8192,
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
            trigger_event_id="e1", originating_event_ids=["e1"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
            trigger_event_id="e2", originating_event_ids=["e2"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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
            trigger_event_id="e2", originating_event_ids=["e2"], max_events_per_fetch=2, max_bytes_per_fetch=8192,
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
            trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=6, max_bytes_per_fetch=8192,
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
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=2, max_bytes_per_fetch=8192,
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
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=2, max_bytes_per_fetch=one_event_bytes,
        )
        page = continuation.fetch(
            {
                "request_id": "byte-only", "handle_id": capability["handle_id"],
                "direction": "around", "anchor_event_id": "e3", "max_events": 2,
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
            trigger_event_id="e5", originating_event_ids=["e5"], max_events_per_fetch=1, max_bytes_per_fetch=one_event_bytes,
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
            trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=10, max_bytes_per_fetch=4096,
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
            trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=10, max_bytes_per_fetch=4096,
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
            trigger_event_id="e3", originating_event_ids=["e3"], max_events_per_fetch=2, max_bytes_per_fetch=4096,
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
        cap_a = continuation.issue(trigger_event_id="e6", originating_event_ids=["e6"], max_events_per_fetch=1, max_bytes_per_fetch=4096)
        cap_b = continuation.issue(trigger_event_id="e6", originating_event_ids=["e6"], max_events_per_fetch=10, max_bytes_per_fetch=4096)
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
        capability = continuation.issue(trigger_event_id="e6", originating_event_ids=["e6"], max_events_per_fetch=2, max_bytes_per_fetch=8192)
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
        capability = continuation.issue(trigger_event_id="e6", originating_event_ids=["e6"], max_events_per_fetch=2, max_bytes_per_fetch=8192)
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
        capability = continuation.issue(trigger_event_id="e6", originating_event_ids=["e6"], max_events_per_fetch=2, max_bytes_per_fetch=8192)
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
            trigger_event_id="e2", originating_event_ids=["e2"], max_events_per_fetch=1, max_bytes_per_fetch=8192,
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


class TestSharedContinuationAuthorityAndRelationGaps(unittest.TestCase):
    class _FixedUuid:
        def __init__(self, value: str):
            self.hex = value * 32

    def test_generated_handle_collision_retries_without_overwriting_authority(self):
        provider, _ = _room_with_events(2)
        continuation = ContinuationProvider(provider, max_handles=3)
        values = [self._FixedUuid("a"), self._FixedUuid("a"), self._FixedUuid("b")]
        with patch.object(observation_module.uuid, "uuid4", side_effect=values):
            first = continuation.issue(
                trigger_event_id="e1", originating_event_ids=["e1"],
                max_events_per_fetch=1, max_bytes_per_fetch=8192,
            )
            second = continuation.issue(
                trigger_event_id="e2", originating_event_ids=["e2"],
                max_events_per_fetch=1, max_bytes_per_fetch=8192,
            )
        self.assertNotEqual(first["handle_id"], second["handle_id"])
        self.assertEqual(len(continuation._capabilities), 2)
        self.assertEqual(
            continuation._capabilities[first["handle_id"]]["bound_to"]["trigger_event_id"],
            "e1",
        )

    def test_wrappers_share_provider_wide_state_and_limits(self):
        provider, _ = _room_with_events(1)
        first = ContinuationProvider(provider, max_handles=1, max_active_cursors_per_handle=2)
        second = ContinuationProvider(provider, max_handles=1, max_active_cursors_per_handle=2)
        self.assertIs(first._capabilities, second._capabilities)
        capability = first.issue(
            trigger_event_id="e1", originating_event_ids=["e1"],
            max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        with self.assertRaises(ContinuationError):
            second.issue(
                trigger_event_id="e1", originating_event_ids=["e1"],
                max_events_per_fetch=1, max_bytes_per_fetch=8192,
            )
        self.assertTrue(second.revoke(capability["handle_id"]))
        second.issue(
            trigger_event_id="e1", originating_event_ids=["e1"],
            max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        with self.assertRaises(ValueError):
            ContinuationProvider(provider, max_handles=2, max_active_cursors_per_handle=2)

    def test_cross_wrapper_concurrent_issue_obeys_one_global_cap(self):
        provider, _ = _room_with_events(1)
        wrappers = [
            ContinuationProvider(provider, max_handles=1),
            ContinuationProvider(provider, max_handles=1),
        ]
        barrier = Barrier(2)

        def issue(wrapper):
            barrier.wait()
            try:
                return wrapper.issue(
                    trigger_event_id="e1", originating_event_ids=["e1"],
                    max_events_per_fetch=1, max_bytes_per_fetch=8192,
                )["handle_id"]
            except ContinuationError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(issue, wrappers))
        self.assertEqual(results.count("rejected"), 1)
        self.assertEqual(len(wrappers[0]._capabilities), 1)

    def test_collision_exhaustion_rejects_without_overwriting_first_handle(self):
        provider, _ = _room_with_events(2)
        continuation = ContinuationProvider(provider, max_handles=3)
        fixed = self._FixedUuid("a")
        with patch.object(observation_module.uuid, "uuid4", return_value=fixed):
            first = continuation.issue(
                trigger_event_id="e1", originating_event_ids=["e1"],
                max_events_per_fetch=1, max_bytes_per_fetch=8192,
            )
            with self.assertRaises(ContinuationError):
                continuation.issue(
                    trigger_event_id="e2", originating_event_ids=["e2"],
                    max_events_per_fetch=1, max_bytes_per_fetch=8192,
                )
        self.assertEqual(list(continuation._capabilities), [first["handle_id"]])
        self.assertEqual(
            continuation._capabilities[first["handle_id"]]["bound_to"]["trigger_event_id"],
            "e1",
        )

    def test_unavailable_literal_relation_targets_are_reported_as_gaps(self):
        cases = [
            make_message("reply", "discord:1001", "reply", reply_to_event_id="missing"),
            make_message("thread", "discord:1001", "thread", thread_root_event_id="missing"),
            make_reaction("reaction", "discord:1001", "missing", "+1"),
        ]
        for event in cases:
            with self.subTest(event_type=event["type"], event_id=event["id"]):
                provider = make_provider()
                seed_room(provider, [event])
                snapshot = provider.snapshot(
                    trigger_event_id=event["id"], max_events=5, max_bytes=65536
                )
                self.assertTrue(snapshot["coverage"]["has_gaps"])

    def test_nearby_returned_relation_target_absence_is_reported_as_a_gap(self):
        provider = make_provider()
        reply = make_message(
            "reply", "discord:1001", "reply", reply_to_event_id="missing",
        )
        trigger = make_message("trigger", "discord:1001", "trigger")
        seed_room(provider, [reply, trigger])
        snapshot = provider.snapshot(
            trigger_event_id="trigger", max_events=2, max_bytes=8192,
        )
        self.assertEqual([event["id"] for event in snapshot["events"]], ["reply", "trigger"])
        self.assertTrue(snapshot["coverage"]["has_gaps"])

    def test_nearby_relation_target_excluded_by_event_cap_reports_gap_and_cause(self):
        provider = make_provider()
        target = make_message("target", "discord:1001", "target")
        reply = make_message(
            "reply", "discord:1001", "reply", reply_to_event_id="target",
        )
        trigger = make_message("trigger", "discord:1001", "trigger")
        seed_room(provider, [target, reply, trigger])
        snapshot = provider.snapshot(
            trigger_event_id="trigger", max_events=2, max_bytes=8192,
        )
        self.assertEqual([event["id"] for event in snapshot["events"]], ["reply", "trigger"])
        self.assertTrue(snapshot["coverage"]["has_gaps"])
        self.assertIn("events", snapshot["coverage"]["truncated_by"])

    def test_capped_trigger_relation_priority_is_hash_seed_independent(self):
        script = """
from tests.v2.observation.helpers import make_provider, make_message, seed_room
p = make_provider()
seed_room(p, [
    make_message('reply-target', 'discord:1001', 'reply'),
    make_message('thread-target', 'discord:1001', 'thread'),
    make_message(
        'trigger', 'discord:1001', 'trigger',
        reply_to_event_id='reply-target', thread_root_event_id='thread-target',
    ),
])
s = p.snapshot(trigger_event_id='trigger', max_events=2, max_bytes=8192)
print(','.join(event['id'] for event in s['events']))
"""
        repo_root = Path(__file__).resolve().parents[3]
        outputs = []
        for seed in ("1", "2", "3", "4"):
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED=seed)
            env["PYTHONPATH"] = "src:."
            outputs.append(
                subprocess.check_output(
                    [sys.executable, "-c", script], cwd=repo_root, env=env, text=True,
                ).strip()
            )
        self.assertEqual(outputs, ["reply-target,trigger"] * 4)

    def test_continuation_reports_relation_gaps_for_every_returned_event(self):
        relation_events = [
            make_message("reply", "discord:1001", "reply", reply_to_event_id="missing"),
            make_message("thread", "discord:1001", "thread", thread_root_event_id="missing"),
            make_reaction(
                "reaction", "discord:1001", "missing", "reaction",
            ),
        ]
        for relation_event in relation_events:
            with self.subTest(event_type=relation_event["type"]):
                provider = make_provider()
                trigger = make_message("trigger", "discord:1001", "trigger")
                seed_room(provider, [relation_event, trigger])
                continuation = ContinuationProvider(provider)
                capability = continuation.issue(
                    trigger_event_id="trigger", originating_event_ids=["trigger"],
                    max_events_per_fetch=10, max_bytes_per_fetch=8192,
                )
                page = continuation.fetch(
                    {
                        "request_id": f"page-{relation_event['type']}",
                        "handle_id": capability["handle_id"],
                        "direction": "before", "max_events": 10, "max_bytes": 8192,
                    },
                    host_context=capability["bound_to"],
                    fetch_time="2026-07-19T10:00:00Z",
                )
                self.assertEqual([event["id"] for event in page["events"]], [relation_event["id"]])
                self.assertTrue(page["coverage"]["has_gaps"])

    def test_continuation_budget_excluded_relation_target_reports_exact_cause(self):
        target = make_message("target", "discord:1001", "x" * 200)
        reply = make_message(
            "reply", "discord:1001", "reply", reply_to_event_id="target",
        )
        trigger = make_message("trigger", "discord:1001", "trigger")
        for cause in ("events", "bytes"):
            with self.subTest(cause=cause):
                provider = make_provider()
                seed_room(provider, [target, reply, trigger])
                continuation = ContinuationProvider(provider)
                reply_bytes = observation_module.serialized_byte_size(reply)
                max_events = 1 if cause == "events" else 10
                max_bytes = 8192 if cause == "events" else reply_bytes
                capability = continuation.issue(
                    trigger_event_id="trigger", originating_event_ids=["trigger"],
                    max_events_per_fetch=max_events, max_bytes_per_fetch=max_bytes,
                )
                page = continuation.fetch(
                    {
                        "request_id": f"budget-{cause}",
                        "handle_id": capability["handle_id"],
                        "direction": "before", "max_events": max_events,
                        "max_bytes": max_bytes,
                    },
                    host_context=capability["bound_to"],
                    fetch_time="2026-07-19T10:00:00Z",
                )
                self.assertEqual([event["id"] for event in page["events"]], ["reply"])
                self.assertTrue(page["coverage"]["has_gaps"])
                self.assertIn(cause, page["coverage"]["truncated_by"])

    def test_budget_excluded_known_relation_reports_actual_truncation_cause(self):
        target = make_message(
            "target", "discord:1001", "x" * 200,
            timestamp="2026-07-17T01:00:00Z",
        )
        trigger = make_message(
            "trigger", "discord:1001", "reply",
            timestamp="2026-07-17T01:00:10Z", reply_to_event_id="target",
        )
        provider = make_provider()
        seed_room(provider, [target, trigger])

        event_limited = provider.snapshot(
            trigger_event_id="trigger", max_events=1, max_bytes=65536
        )
        self.assertTrue(event_limited["coverage"]["has_gaps"])
        self.assertIn("events", event_limited["coverage"]["truncated_by"])

        trigger_bytes = serialized_byte_size(trigger)
        byte_limited = provider.snapshot(
            trigger_event_id="trigger", max_events=5, max_bytes=trigger_bytes
        )
        self.assertTrue(byte_limited["coverage"]["has_gaps"])
        self.assertIn("bytes", byte_limited["coverage"]["truncated_by"])

        age_limited = provider.snapshot(
            trigger_event_id="trigger", max_events=5, max_bytes=65536,
            max_age_seconds=1,
        )
        self.assertTrue(age_limited["coverage"]["has_gaps"])
        self.assertIn("age", age_limited["coverage"]["truncated_by"])


if __name__ == "__main__":
    unittest.main()
