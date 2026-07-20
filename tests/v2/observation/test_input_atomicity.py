"""Phase 20 caller-memory and early resource-bound atomicity regressions."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
import unittest
from unittest.mock import patch

import nunchi.observation as observation
from nunchi.observation import (
    ContinuationError,
    ContinuationProvider,
    ObservationInputError,
)
from tests.v2.observation.helpers import candidate, make_message, make_provider, seed_room

FETCH_TIME = "2026-07-19T10:00:00Z"


class _UncopyableDict(dict):
    def __deepcopy__(self, memo):
        raise RuntimeError("synthetic copy failure")


class _CountingDeque(deque):
    def __init__(self, values, *, maxlen):
        super().__init__(values, maxlen=maxlen)
        self.visits = 0

    def __iter__(self):
        for value in super().__iter__():
            self.visits += 1
            yield value


class TestCallerMemoryIsolation(unittest.TestCase):
    def test_receipt_uses_one_private_request_copy_after_exact_match(self):
        provider = make_provider()
        seed_room(provider, [make_message("e1", "discord:1001", "x")])
        request = provider.snapshot(
            trigger_event_id="e1", max_events=1, max_bytes=8192,
            request_id="receipt-copy",
        )
        issued_bytes = sum(
            observation.serialized_byte_size(event) for event in request["events"]
        )
        checked = Event()
        release = Event()
        real_size = observation.serialized_byte_size

        def gated_size(value):
            checked.set()
            if not release.wait(timeout=5):
                raise RuntimeError("receipt test release timeout")
            return real_size(value)

        with patch.object(observation, "serialized_byte_size", gated_size):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(provider.build_observation_receipt, request)
                self.assertTrue(checked.wait(timeout=2))
                request["events"][0]["text"] = "M" * 200
                release.set()
                receipt = future.result(timeout=5)

        self.assertEqual(receipt["body"]["byte_count"], issued_bytes)
        self.assertEqual(receipt["body"]["included_event_ids"], ["e1"])
        self.assertNotIn("receipt-copy", provider._pending_receipts)

    def test_fetch_uses_one_private_request_copy_after_authorization(self):
        provider = make_provider()
        seed_room(
            provider,
            [make_message(f"e{i}", "discord:1001", f"message {i}") for i in range(1, 6)],
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e3", originating_event_ids=["e3"],
            max_events_per_fetch=2, max_bytes_per_fetch=8192,
            can_fetch_before=True, can_fetch_after=False,
        )
        request = {
            "request_id": "request-copy", "handle_id": capability["handle_id"],
            "direction": "before", "max_events": 2, "max_bytes": 8192,
        }
        checked = Event()
        release = Event()
        real_check = observation.check_binding_expiry

        def gated_check(fetch_case):
            result = real_check(fetch_case)
            checked.set()
            if not release.wait(timeout=5):
                raise RuntimeError("fetch test release timeout")
            return result

        with patch.object(observation, "check_binding_expiry", gated_check):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    continuation.fetch,
                    request,
                    host_context=deepcopy(capability["bound_to"]),
                    fetch_time=FETCH_TIME,
                )
                self.assertTrue(checked.wait(timeout=2))
                request["direction"] = "after"
                release.set()
                page = future.result(timeout=5)

        self.assertEqual(page["direction"], "before")
        self.assertEqual([event["id"] for event in page["events"]], ["e1", "e2"])

    def test_ingest_copies_complete_native_input_before_validation(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "valid")
        native = candidate(event)
        checked = Event()
        release = Event()
        real_check = observation._check_event

        def gated_check(errors, path, value):
            real_check(errors, path, value)
            checked.set()
            if not release.wait(timeout=5):
                raise RuntimeError("ingest test release timeout")

        with patch.object(observation, "_check_event", gated_check):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(provider.ingest, native)
                self.assertTrue(checked.wait(timeout=2))
                event["type"] = "schema-invalid-after-validation"
                release.set()
                self.assertEqual(future.result(timeout=5), "observed")

        self.assertEqual(provider._events_by_id["e1"]["type"], "message")

    def test_copy_failures_reject_without_state_mutation(self):
        provider = make_provider()
        with self.assertRaisesRegex(ObservationInputError, "copy"):
            provider.ingest(_UncopyableDict(candidate(make_message("e1", "discord:1001", "x"))))
        self.assertEqual(list(provider._events), [])

        seed_room(provider, [make_message("e1", "discord:1001", "one")])
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e1", originating_event_ids=["e1"],
            max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        with self.assertRaisesRegex(ContinuationError, "copy"):
            continuation.fetch(
                _UncopyableDict({
                    "request_id": "bad-copy", "handle_id": capability["handle_id"],
                    "direction": "before", "max_events": 1, "max_bytes": 8192,
                }),
                host_context=capability["bound_to"], fetch_time=FETCH_TIME,
            )
        self.assertEqual(continuation._cursors[capability["handle_id"]], set())

        receipt_provider = make_provider()
        seed_room(receipt_provider, [make_message("e1", "discord:1001", "one")])
        pending = receipt_provider.snapshot(
            trigger_event_id="e1", max_events=1, max_bytes=8192,
            request_id="receipt-copy-failure",
        )
        with self.assertRaisesRegex(ObservationInputError, "copy"):
            receipt_provider.build_observation_receipt(_UncopyableDict(pending))
        self.assertIn("receipt-copy-failure", receipt_provider._pending_receipts)


class TestEarlyCursorLimit(unittest.TestCase):
    def test_over_limit_fresh_fetch_rejects_before_retained_deque_visit(self):
        provider = make_provider(retention_max_events=256)
        seed_room(
            provider,
            [make_message(f"e{i}", "discord:1001", f"message {i}") for i in range(1, 257)],
        )
        continuation = ContinuationProvider(provider, max_active_cursors_per_handle=1)
        capability = continuation.issue(
            trigger_event_id="e256", originating_event_ids=["e256"],
            max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "occupy", "handle_id": capability["handle_id"],
            "direction": "before", "anchor_event_id": "e256",
            "max_events": 1, "max_bytes": 8192,
        }
        first = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time=FETCH_TIME,
        )
        self.assertIn("next_cursor", first)

        provider._events = _CountingDeque(
            provider._events, maxlen=provider._events.maxlen,
        )
        with self.assertRaisesRegex(ContinuationError, "active cursor limit"):
            continuation.fetch(
                dict(request, request_id="over-limit"),
                host_context=capability["bound_to"], fetch_time=FETCH_TIME,
            )
        self.assertEqual(provider._events.visits, 0)


if __name__ == "__main__":
    unittest.main()
