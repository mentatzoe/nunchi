"""Phase 18 concurrency and replay-resource regressions for Slice 020."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, get_ident
import unittest
from unittest.mock import patch

import nunchi.observation as observation
from nunchi.observation import ContinuationError, ContinuationProvider
from tests.v2.observation.helpers import make_message, seed_room
from tests.v2.observation.test_budget_and_continuation import (
    _room_with_events,
    make_provider,
)


FETCH_TIME = "2026-07-19T10:00:00Z"


class _EntryGate:
    """Capture first/second concurrent entry without making GREEN lock paths deadlock."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries = 0
        self.first_entered = Event()
        self.second_entered = Event()
        self.release_first = Event()

    def enter(self) -> None:
        with self._lock:
            self._entries += 1
            entry = self._entries
        if entry == 1:
            self.first_entered.set()
            if not self.release_first.wait(timeout=5):
                raise RuntimeError("test gate timed out waiting to release first entrant")
        elif entry == 2:
            self.second_entered.set()


class TestContinuationAtomicity(unittest.TestCase):
    def test_concurrent_issue_obeys_hard_handle_limit(self):
        provider, _ = _room_with_events(3)
        continuation = ContinuationProvider(provider, max_handles=1)
        gate = _EntryGate()
        real_uuid4 = observation.uuid.uuid4

        def gated_uuid4():
            gate.enter()
            return real_uuid4()

        def issue_once():
            try:
                return continuation.issue(
                    trigger_event_id="e3",
                    originating_event_ids=["e3"],
                    max_events_per_fetch=1,
                    max_bytes_per_fetch=8192,
                )
            except Exception as exc:  # outcome is asserted below
                return exc

        with patch.object(observation.uuid, "uuid4", gated_uuid4):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(issue_once)
                self.assertTrue(gate.first_entered.wait(timeout=2))
                second = pool.submit(issue_once)
                second_was_blocked = not gate.second_entered.wait(timeout=0.2)
                gate.release_first.set()
                results = [first.result(timeout=5), second.result(timeout=5)]

        self.assertTrue(second_was_blocked)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, ContinuationError) for result in results), 1)
        self.assertEqual(len(continuation._capabilities), 1)

    def test_concurrent_fresh_fetch_obeys_active_cursor_limit(self):
        provider, _ = _room_with_events(5)
        continuation = ContinuationProvider(
            provider, max_active_cursors_per_handle=1,
        )
        capability = continuation.issue(
            trigger_event_id="e3",
            originating_event_ids=["e3"],
            max_events_per_fetch=1,
            max_bytes_per_fetch=8192,
        )
        gate = _EntryGate()
        per_thread_len_calls: dict[int, int] = {}
        calls_lock = Lock()

        class GatedSet(set):
            def __len__(self):
                value = super().__len__()
                thread_id = get_ident()
                with calls_lock:
                    per_thread_len_calls[thread_id] = per_thread_len_calls.get(thread_id, 0) + 1
                    call = per_thread_len_calls[thread_id]
                # First len() is sorted()'s length hint; second is the hard-limit check.
                if call == 2:
                    gate.enter()
                return value

        continuation._cursors[capability["handle_id"]] = GatedSet()

        def fetch_once(direction: str):
            try:
                return continuation.fetch(
                    {
                        "request_id": f"fresh-{direction}",
                        "handle_id": capability["handle_id"],
                        "direction": direction,
                        "anchor_event_id": "e3",
                        "max_events": 1,
                        "max_bytes": 8192,
                    },
                    host_context=capability["bound_to"],
                    fetch_time=FETCH_TIME,
                )
            except Exception as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(fetch_once, "before")
            self.assertTrue(gate.first_entered.wait(timeout=2))
            second = pool.submit(fetch_once, "after")
            second_was_blocked = not gate.second_entered.wait(timeout=0.2)
            gate.release_first.set()
            results = [first.result(timeout=5), second.result(timeout=5)]

        self.assertTrue(second_was_blocked)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, ContinuationError) for result in results), 1)
        self.assertEqual(len(continuation._cursors[capability["handle_id"]]), 1)

    def test_one_shot_cursor_has_exactly_one_concurrent_consumer(self):
        provider, _ = _room_with_events(8)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e8",
            originating_event_ids=["e8"],
            max_events_per_fetch=1,
            max_bytes_per_fetch=8192,
        )
        request = {
            "handle_id": capability["handle_id"],
            "direction": "before",
            "anchor_event_id": "e8",
            "max_events": 1,
            "max_bytes": 8192,
        }
        first_page = continuation.fetch(
            dict(request, request_id="mint"),
            host_context=capability["bound_to"],
            fetch_time=FETCH_TIME,
        )
        token = first_page["next_cursor"]
        gate = _EntryGate()
        windows = continuation._cursor_windows[capability["handle_id"]]

        class GatedWindowMap(dict):
            def get(self, key, default=None):
                captured = super().get(key, default)
                if key == token:
                    gate.enter()
                return captured

        continuation._cursor_windows[capability["handle_id"]] = GatedWindowMap(windows)

        def replay_once(number: int):
            try:
                return continuation.fetch(
                    dict(request, request_id=f"replay-{number}", cursor=token),
                    host_context=capability["bound_to"],
                    fetch_time=FETCH_TIME,
                )
            except Exception as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(replay_once, 1)
            self.assertTrue(gate.first_entered.wait(timeout=2))
            second = pool.submit(replay_once, 2)
            second_was_blocked = not gate.second_entered.wait(timeout=0.2)
            gate.release_first.set()
            results = [first.result(timeout=5), second.result(timeout=5)]

        self.assertTrue(second_was_blocked)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, ContinuationError) for result in results), 1)
        successful = next(result for result in results if isinstance(result, dict))
        self.assertEqual([event["id"] for event in successful["events"]], ["e6"])

    def test_fetch_and_revoke_are_linearizable_without_state_resurrection(self):
        provider, _ = _room_with_events(4)
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e4",
            originating_event_ids=["e4"],
            max_events_per_fetch=1,
            max_bytes_per_fetch=8192,
        )
        gate = _EntryGate()
        real_check = observation.check_binding_expiry

        def gated_check(fetch_case):
            gate.enter()
            return real_check(fetch_case)

        def fetch_once():
            try:
                return continuation.fetch(
                    {
                        "request_id": "fetch-revoke",
                        "handle_id": capability["handle_id"],
                        "direction": "before",
                        "max_events": 1,
                        "max_bytes": 8192,
                    },
                    host_context=capability["bound_to"],
                    fetch_time=FETCH_TIME,
                )
            except Exception as exc:
                return exc

        revoke_done = Event()

        def revoke_once():
            result = continuation.revoke(capability["handle_id"])
            revoke_done.set()
            return result

        with patch.object(observation, "check_binding_expiry", gated_check):
            with ThreadPoolExecutor(max_workers=2) as pool:
                fetch_future = pool.submit(fetch_once)
                self.assertTrue(gate.first_entered.wait(timeout=2))
                revoke_future = pool.submit(revoke_once)
                revoke_was_blocked = not revoke_done.wait(timeout=0.2)
                gate.release_first.set()
                fetch_result = fetch_future.result(timeout=5)
                revoke_result = revoke_future.result(timeout=5)

        self.assertTrue(revoke_was_blocked)
        self.assertIsInstance(fetch_result, dict)
        self.assertTrue(revoke_result)
        self.assertNotIn(capability["handle_id"], continuation._capabilities)
        self.assertNotIn(capability["handle_id"], continuation._cursor_windows)

    def test_ingest_and_fetch_share_one_provider_lock(self):
        provider, _ = _room_with_events(
            4, provider=make_provider(retention_max_events=4),
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e4",
            originating_event_ids=["e4"],
            max_events_per_fetch=1,
            max_bytes_per_fetch=8192,
        )
        gate = _EntryGate()
        real_check = observation.check_binding_expiry

        def gated_check(fetch_case):
            gate.enter()
            return real_check(fetch_case)

        def fetch_once():
            return continuation.fetch(
                {
                    "request_id": "fetch-ingest",
                    "handle_id": capability["handle_id"],
                    "direction": "before",
                    "max_events": 1,
                    "max_bytes": 8192,
                },
                host_context=capability["bound_to"],
                fetch_time=FETCH_TIME,
            )

        ingest_done = Event()

        def ingest_once():
            result = provider.ingest({
                "delivery_id": "delivery:e5",
                "disposition": "candidate-event",
                "authorized": True,
                "event": make_message("e5", "discord:1001", "later"),
                "actors": {},
            })
            ingest_done.set()
            return result

        with patch.object(observation, "check_binding_expiry", gated_check):
            with ThreadPoolExecutor(max_workers=2) as pool:
                fetch_future = pool.submit(fetch_once)
                self.assertTrue(gate.first_entered.wait(timeout=2))
                ingest_future = pool.submit(ingest_once)
                ingest_was_blocked = not ingest_done.wait(timeout=0.2)
                gate.release_first.set()
                page = fetch_future.result(timeout=5)
                ingest_result = ingest_future.result(timeout=5)

        self.assertTrue(ingest_was_blocked)
        self.assertEqual([event["id"] for event in page["events"]], ["e3"])
        self.assertEqual(ingest_result, "observed")


class TestContinuationRetentionGapCoverage(unittest.TestCase):
    def test_before_terminal_page_discloses_known_retention_gap(self):
        provider = make_provider(retention_max_events=3)
        seed_room(
            provider,
            [make_message(f"e{i}", "discord:1001", f"message {i}") for i in range(1, 5)],
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e4", originating_event_ids=["e4"],
            max_events_per_fetch=10, max_bytes_per_fetch=8192,
        )
        page = continuation.fetch(
            {
                "request_id": "gap-before", "handle_id": capability["handle_id"],
                "direction": "before", "max_events": 10, "max_bytes": 8192,
            },
            host_context=capability["bound_to"], fetch_time=FETCH_TIME,
        )
        self.assertNotIn("next_cursor", page)
        self.assertTrue(page["coverage"]["has_gaps"])

    def test_after_chain_discloses_known_retention_gap_on_every_page(self):
        provider = make_provider(retention_max_events=3)
        seed_room(
            provider,
            [make_message(f"e{i}", "discord:1001", f"message {i}") for i in range(1, 5)],
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e2", originating_event_ids=["e2"],
            max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "gap-after-1", "handle_id": capability["handle_id"],
            "direction": "after", "max_events": 1, "max_bytes": 8192,
        }
        page1 = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time=FETCH_TIME,
        )
        page2 = continuation.fetch(
            dict(request, request_id="gap-after-2", cursor=page1["next_cursor"]),
            host_context=capability["bound_to"], fetch_time=FETCH_TIME,
        )
        self.assertTrue(page1["coverage"]["has_gaps"])
        self.assertTrue(page2["coverage"]["has_gaps"])
        self.assertNotIn("next_cursor", page2)

    def test_around_chain_discloses_known_retention_gap_through_exhaustion(self):
        provider = make_provider(retention_max_events=5)
        seed_room(
            provider,
            [make_message(f"e{i}", "discord:1001", f"message {i}") for i in range(1, 7)],
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id="e6", originating_event_ids=["e6"],
            max_events_per_fetch=1, max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "gap-around-1", "handle_id": capability["handle_id"],
            "direction": "around", "anchor_event_id": "e3",
            "max_events": 1, "max_bytes": 8192,
        }
        pages = []
        page = continuation.fetch(
            request, host_context=capability["bound_to"], fetch_time=FETCH_TIME,
        )
        pages.append(page)
        while "next_cursor" in page:
            page = continuation.fetch(
                dict(
                    request,
                    request_id=f"gap-around-{len(pages) + 1}",
                    cursor=page["next_cursor"],
                ),
                host_context=capability["bound_to"], fetch_time=FETCH_TIME,
            )
            pages.append(page)
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(page["coverage"]["has_gaps"] for page in pages))
        self.assertNotIn("next_cursor", pages[-1])


class _CountingDeque(deque):
    def __init__(self, values, *, maxlen):
        super().__init__(values, maxlen=maxlen)
        self.iterated_events = 0

    def __iter__(self):
        for value in super().__iter__():
            self.iterated_events += 1
            yield value


class TestCursorReplayComplexity(unittest.TestCase):
    def _one_event_chain_visits(self, count: int) -> tuple[int, ContinuationProvider, object]:
        provider, _ = _room_with_events(count)
        provider._events = _CountingDeque(
            provider._events, maxlen=provider._events.maxlen,
        )
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id=f"e{count}",
            originating_event_ids=[f"e{count}"],
            max_events_per_fetch=1,
            max_bytes_per_fetch=8192,
        )
        request = {
            "request_id": "complexity-1",
            "handle_id": capability["handle_id"],
            "direction": "before",
            "anchor_event_id": f"e{count}",
            "max_events": 1,
            "max_bytes": 8192,
        }
        page = continuation.fetch(
            request,
            host_context=capability["bound_to"],
            fetch_time=FETCH_TIME,
        )
        # Initial window creation is allowed one O(N) scan. Measure replay only.
        provider._events.iterated_events = 0
        page_number = 1
        while "next_cursor" in page:
            page_number += 1
            page = continuation.fetch(
                dict(
                    request,
                    request_id=f"complexity-{page_number}",
                    cursor=page["next_cursor"],
                ),
                host_context=capability["bound_to"],
                fetch_time=FETCH_TIME,
            )
        self.assertEqual(page_number, count - 1)
        return provider._events.iterated_events, continuation, capability

    def test_one_event_cursor_chain_replay_grows_near_linearly(self):
        visits_64, _, _ = self._one_event_chain_visits(64)
        visits_128, _, _ = self._one_event_chain_visits(128)
        self.assertLessEqual(visits_128, visits_64 * 2.5 + 128)
        self.assertLessEqual(visits_128, 128 * 3)

    def test_event_by_id_state_is_retention_bounded_and_reclaimed_with_eviction(self):
        provider = make_provider(retention_max_events=3)
        seed_room(
            provider,
            [
                make_message(f"e{i}", f"discord:{1000 + i}", f"message {i}")
                for i in range(1, 7)
            ],
        )
        events_by_id = getattr(provider, "_events_by_id")
        self.assertEqual(set(events_by_id), {"e4", "e5", "e6"})
        self.assertEqual(len(events_by_id), 3)
        self.assertIs(events_by_id["e6"], provider._events[-1])


if __name__ == "__main__":
    unittest.main()
