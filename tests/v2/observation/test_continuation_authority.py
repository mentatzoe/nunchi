"""Phase 25 RED/GREEN continuation authority and relation-gap regressions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
import unittest
from unittest.mock import patch

from evals.v2.observation.compare import compare_requests
from nunchi.observation import (
    ContinuationError,
    ContinuationProvider,
    ObservationInputError,
    serialized_byte_size,
)
from tests.v2.observation.helpers import (
    FIXTURE_ACTORS,
    candidate,
    make_message,
    make_provider,
    make_reaction,
    seed_room,
)


class _FixedUUID:
    hex = "0123456789abcdef0123456789abcdef"


class ContinuationFixture(unittest.TestCase):
    def setUp(self):
        self.provider = make_provider()
        seed_room(
            self.provider,
            [
                make_message("e1", "discord:1001", "one"),
                make_message("e2", "discord:1001", "two"),
            ],
        )

    @staticmethod
    def issue(continuation, trigger="e1", *, expires_at=None):
        return continuation.issue(
            trigger_event_id=trigger,
            originating_event_ids=[trigger],
            max_events_per_fetch=10,
            max_bytes_per_fetch=8192,
            expires_at=expires_at,
        )


class TestContinuationComparatorExpiryPresence(ContinuationFixture):
    def test_expiry_presence_is_semantic_but_exact_clock_value_is_opaque(self):
        continuation = ContinuationProvider(self.provider)
        left = self.provider.snapshot(
            trigger_event_id="e1", max_events=10, max_bytes=65536,
        )
        left["continuation"] = self.issue(
            continuation, expires_at="2026-07-20T00:00:00Z",
        )
        different_clock = deepcopy(left)
        different_clock["continuation"]["expires_at"] = "2026-07-21T00:00:00Z"
        self.assertTrue(compare_requests(left, different_clock)["equivalent"])

        no_expiry = deepcopy(left)
        no_expiry["continuation"].pop("expires_at")
        result = compare_requests(left, no_expiry)
        self.assertFalse(result["equivalent"])
        self.assertTrue(
            any("continuation.expires_at" in item for item in result["unexplained"]),
            result,
        )


class TestProviderOwnedContinuationAuthority(ContinuationFixture):
    @staticmethod
    def _raced_issue(barrier, continuation, trigger):
        barrier.wait(timeout=5)
        try:
            capability = ContinuationFixture.issue(continuation, trigger)
            return ("issued", capability["handle_id"], trigger)
        except ContinuationError as exc:
            return ("rejected", str(exc), trigger)

    def test_generated_handle_collision_fails_without_overwriting_live_authority(self):
        continuation = ContinuationProvider(self.provider, max_handles=2)
        with patch("nunchi.observation.uuid.uuid4", return_value=_FixedUUID()):
            first = self.issue(continuation, "e1")
            with self.assertRaises(ContinuationError):
                self.issue(continuation, "e2")
        self.assertEqual(len(continuation._capabilities), 1)
        self.assertEqual(
            continuation._capabilities[first["handle_id"]]["bound_to"]["trigger_event_id"],
            "e1",
        )

    def test_revoked_handle_id_never_resurrects_old_capability(self):
        continuation = ContinuationProvider(self.provider, max_handles=2)
        with patch("nunchi.observation.uuid.uuid4", return_value=_FixedUUID()):
            first = self.issue(continuation, "e1")
            self.assertTrue(continuation.revoke(first["handle_id"]))
            with self.assertRaises(ContinuationError):
                self.issue(continuation, "e1")
        self.assertEqual(continuation._capabilities, {})

    def test_wrappers_share_one_registry_and_one_provider_wide_handle_cap(self):
        first = ContinuationProvider(
            self.provider, max_handles=1, max_active_cursors_per_handle=2,
        )
        second = ContinuationProvider(
            self.provider, max_handles=1, max_active_cursors_per_handle=2,
        )
        self.assertIs(first._capabilities, second._capabilities)
        self.assertIs(first._cursors, second._cursors)
        self.issue(first, "e1")
        with self.assertRaises(ContinuationError):
            self.issue(second, "e2")
        self.assertEqual(len(first._capabilities), 1)

    def test_concurrent_wrappers_obey_one_provider_wide_handle_cap(self):
        first = ContinuationProvider(self.provider, max_handles=1)
        second = ContinuationProvider(self.provider, max_handles=1)
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                future.result(timeout=5)
                for future in (
                    pool.submit(self._raced_issue, barrier, first, "e1"),
                    pool.submit(self._raced_issue, barrier, second, "e2"),
                )
            ]
        self.assertEqual(sorted(result[0] for result in results), ["issued", "rejected"])
        self.assertEqual(len(first._capabilities), 1)

    def test_concurrent_wrappers_cannot_overwrite_a_colliding_handle(self):
        first = ContinuationProvider(self.provider, max_handles=2)
        second = ContinuationProvider(self.provider, max_handles=2)
        barrier = Barrier(2)
        with patch("nunchi.observation.uuid.uuid4", return_value=_FixedUUID()):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = [
                    future.result(timeout=5)
                    for future in (
                        pool.submit(self._raced_issue, barrier, first, "e1"),
                        pool.submit(self._raced_issue, barrier, second, "e2"),
                    )
                ]
        self.assertEqual(sorted(result[0] for result in results), ["issued", "rejected"])
        self.assertEqual(len(first._capabilities), 1)
        issued = next(result for result in results if result[0] == "issued")
        self.assertEqual(
            first._capabilities[issued[1]]["bound_to"]["trigger_event_id"],
            issued[2],
        )

    def test_additional_wrapper_with_different_limits_rejects(self):
        ContinuationProvider(
            self.provider, max_handles=1, max_active_cursors_per_handle=2,
        )
        with self.assertRaises(ValueError):
            ContinuationProvider(
                self.provider, max_handles=2, max_active_cursors_per_handle=2,
            )
        with self.assertRaises(ValueError):
            ContinuationProvider(
                self.provider, max_handles=1, max_active_cursors_per_handle=3,
            )

    def test_issued_handle_filter_is_fixed_size(self):
        continuation = ContinuationProvider(self.provider)
        initial_size = len(continuation._issued_handle_filter)
        for _ in range(64):
            cap = self.issue(continuation, "e1")
            continuation.revoke(cap["handle_id"])
        issued_ids = [f"cont-stress-{index:05d}" for index in range(25_000)]
        for handle_id in issued_ids:
            continuation._remember_handle_id(handle_id)
        misses = sum(
            not continuation._handle_id_was_issued(handle_id)
            for handle_id in issued_ids
        )
        self.assertEqual(initial_size, 8192)
        self.assertEqual(len(continuation._issued_handle_filter), initial_size)
        self.assertEqual(misses, 0)


class TestRelationGapTruth(unittest.TestCase):
    def _snapshot_for_only_event(self, event):
        provider = make_provider()
        provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        return provider.snapshot(
            trigger_event_id=event["id"], max_events=10, max_bytes=65536,
        )

    def test_missing_reply_target_is_an_honest_gap(self):
        page = self._snapshot_for_only_event(
            make_message(
                "e2", "discord:1001", "reply", reply_to_event_id="missing-e1",
            )
        )
        self.assertTrue(page["coverage"]["has_gaps"])
        self.assertEqual(page["events"][0]["reply_to_event_id"], "missing-e1")

    def test_missing_thread_root_is_an_honest_gap(self):
        page = self._snapshot_for_only_event(
            make_message(
                "e2", "discord:1001", "thread",
                thread_root_event_id="missing-root",
            )
        )
        self.assertTrue(page["coverage"]["has_gaps"])
        self.assertEqual(page["events"][0]["thread_root_event_id"], "missing-root")

    def test_missing_reaction_target_is_an_honest_gap(self):
        page = self._snapshot_for_only_event(
            make_reaction("r1", "discord:1001", "missing-message", "eyes")
        )
        self.assertTrue(page["coverage"]["has_gaps"])
        self.assertEqual(page["events"][0]["target_event_id"], "missing-message")

    def test_known_relation_target_that_cannot_fit_is_an_honest_gap(self):
        provider = make_provider()
        target = make_message("e1", "discord:1001", "original")
        trigger = make_message(
            "e2", "discord:1001", "reply", reply_to_event_id="e1",
        )
        seed_room(provider, [target, trigger])
        page = provider.snapshot(
            trigger_event_id="e2", max_events=1, max_bytes=65536,
        )
        self.assertTrue(page["coverage"]["has_gaps"])
        self.assertIn("events", page["coverage"]["truncated_by"])


class TestReceiptCallerMemoryAuthority(unittest.TestCase):
    def test_receipt_attests_private_issued_document_after_caller_mutation(self):
        provider = make_provider()
        seed_room(provider, [make_message("e1", "discord:1001", "issued")])
        request = provider.snapshot(
            trigger_event_id="e1", max_events=10, max_bytes=65536,
        )
        issued_byte_count = sum(serialized_byte_size(event) for event in request["events"])
        reached_size = Event()
        release_size = Event()
        blocked_once = False

        def blocked_size(value):
            nonlocal blocked_once
            if (
                not blocked_once
                and isinstance(value, dict)
                and value.get("id") == "e1"
            ):
                blocked_once = True
                reached_size.set()
                self.assertTrue(release_size.wait(timeout=5))
            return serialized_byte_size(value)

        with patch("nunchi.observation.serialized_byte_size", side_effect=blocked_size):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(provider.build_observation_receipt, request)
                self.assertTrue(reached_size.wait(timeout=5))
                request["events"][0]["text"] = "mutated" * 100
                release_size.set()
                receipt = future.result(timeout=5)

        self.assertEqual(receipt["body"]["byte_count"], issued_byte_count)
        self.assertNotEqual(
            receipt["body"]["byte_count"],
            sum(serialized_byte_size(event) for event in request["events"]),
        )

    def test_receipt_copy_failure_does_not_consume_pending_authority(self):
        provider = make_provider()
        seed_room(provider, [make_message("e1", "discord:1001", "issued")])
        request = provider.snapshot(
            trigger_event_id="e1", max_events=10, max_bytes=65536,
        )

        class Uncopyable(dict):
            def __deepcopy__(self, memo):
                raise RuntimeError("copy blocked")

        with self.assertRaises(ObservationInputError):
            provider.build_observation_receipt(Uncopyable(request))
        receipt = provider.build_observation_receipt(request)
        self.assertEqual(receipt["request_id"], request["request_id"])


class TestLifetimeTimestampWatermark(unittest.TestCase):
    def test_undated_eviction_cannot_erase_parseable_time_order(self):
        provider = make_provider(retention_max_events=2)
        provider.ingest(candidate(make_message(
            "e1", "discord:1001", "later", timestamp="2026-07-19T00:00:10Z",
        )))
        provider.ingest(candidate(make_message("e2", "discord:1001", "undated one")))
        provider.ingest(candidate(make_message("e3", "discord:1001", "undated two")))
        self.assertEqual([event["id"] for event in provider._events], ["e2", "e3"])
        watermark = provider._last_parseable_timestamp
        self.assertIsNotNone(watermark)
        assert watermark is not None
        self.assertEqual(watermark.isoformat(), "2026-07-19T00:00:10+00:00")
        with self.assertRaises(ObservationInputError):
            provider.ingest(candidate(make_message(
                "e4", "discord:1001", "earlier", timestamp="2026-07-19T00:00:05Z",
            )))
        self.assertEqual([event["id"] for event in provider._events], ["e2", "e3"])


if __name__ == "__main__":
    unittest.main()
