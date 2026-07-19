"""US2 budget/continuation tests (T013): hard budgets, relation closure,
coverage, the accepted I-010A capability shape, I-010D fetch documents,
continuation binding/expiry/cursor, authoritative order, and exact-event
dedup. Slice-030 classifier projection behavior is out of scope here.
"""

from __future__ import annotations

import unittest

from nunchi.observation import ContinuationError, ContinuationProvider, validate_context_continuation
from tests.v2.observation.helpers import FIXTURE_ACTORS, make_message, make_provider, seed_room


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


if __name__ == "__main__":
    unittest.main()
