from __future__ import annotations

import tempfile
import threading
import unittest
from unittest import mock

from nunchi.policy import load_operator_policy
from nunchi.runtime import LiveRoomRuntime
from tests.v2.observation.helpers import (
    FIXTURE_ACTORS,
    candidate,
    make_message,
    make_provider,
)
from tests.v2.security.helpers import clone_policy, write_policy


def wake_judgment(projection, _config):
    return {
        "disposition": "WAKE",
        "reasons": ["the current room warrants a participant turn"],
        "evidence_event_ids": [projection["trigger_event_id"]],
    }


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        document = clone_policy()
        document["recoverability"]["continuity_scope_id"] = "discord:room:42#2026-07"
        self.policy_path = write_policy(self.temporary.name, document)
        self.provider = make_provider()
        self.receipts = []
        self.participant_packets = []

    def runtime(self, **overrides):
        arguments = {
            "observation": self.provider,
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
            "participant": lambda turn: self.participant_packets.append(turn.packet),
            "classifier_transport": wake_judgment,
        }
        arguments.update(overrides)
        return LiveRoomRuntime(**arguments)

    def delivery(self, index):
        return candidate(
            make_message(f"e{index}", "discord:1001", f"message {index}"),
            actors=FIXTURE_ACTORS,
        )


class LiveCoalescingCases(RuntimeCase):
    def test_twenty_events_during_slow_turn_create_one_fresh_successor(self):
        entered = threading.Event()
        release = threading.Event()
        classifier_calls = []

        def slow_first(projection, config):
            classifier_calls.append(projection["trigger_event_id"])
            if len(classifier_calls) == 1:
                entered.set()
                self.assertTrue(release.wait(5))
            return wake_judgment(projection, config)

        runtime = self.runtime(classifier_transport=slow_first)
        first = runtime.accept(self.delivery(1))
        self.assertIsNotNone(first.opportunity)
        results = []
        worker = threading.Thread(
            target=lambda: results.extend(runtime.drain(first.opportunity)),
            daemon=True,
        )
        worker.start()
        self.assertTrue(entered.wait(5))
        for index in range(2, 21):
            accepted = runtime.accept(self.delivery(index))
            self.assertIsNone(accepted.opportunity)
        release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())

        self.assertEqual(classifier_calls, ["e1", "e20"])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(self.participant_packets), 2)
        self.assertIn("e20", [event["id"] for event in self.participant_packets[0]["events"]])
        self.assertEqual(self.participant_packets[1]["trigger_event_id"], "e20")
        self.assertEqual(runtime.scheduler.snapshot(), ())
        self.assertEqual(
            [record["stage"] for record in self.receipts],
            ["observation", "attention", "participant-host"] * 2,
        )

    def test_suppression_stops_without_participant_invocation(self):
        runtime = self.runtime(
            classifier_transport=lambda projection, config: {
                "disposition": "SUPPRESS",
                "reasons": ["no contribution is currently useful"],
                "evidence_event_ids": [projection["trigger_event_id"]],
                "legacy_verdict_confidences": {
                    "PASS": 0.96,
                    "ACK": 0.01,
                    "ASK": 0.01,
                    "SPEAK": 0.02,
                },
            }
        )
        results = runtime.process_delivery(self.delivery(1))
        self.assertEqual(results[0]["status"], "suppressed")
        self.assertEqual(self.participant_packets, [])
        self.assertEqual([record["stage"] for record in self.receipts], ["observation", "attention"])

    def test_duplicate_and_self_delivery_never_create_wake_work(self):
        runtime = self.runtime()
        duplicate = self.delivery(1)
        first = runtime.accept(duplicate)
        self.assertIsNotNone(first.opportunity)
        repeated = runtime.accept(duplicate)
        self.assertEqual(repeated.observation_disposition, "duplicate-retained")
        self.assertIsNone(repeated.opportunity)
        self_event = candidate(
            make_message("self-e", self.provider.actor_id, "sent by this participant"),
            actors=FIXTURE_ACTORS,
        )
        accepted_self = runtime.accept(self_event)
        self.assertEqual(accepted_self.observation_disposition, "self-retained-no-wake")
        self.assertIsNone(accepted_self.opportunity)


class SnapshotRecoveryCases(RuntimeCase):
    def test_snapshot_gets_exactly_one_current_history_recovery_attempt(self):
        recovery_calls = []
        runtime = self.runtime(
            recover_current_history=lambda anchor: recovery_calls.append(anchor)
        )
        original = self.provider.snapshot
        calls = []

        def fail_once(**arguments):
            calls.append(arguments)
            if len(calls) == 1:
                raise ValueError("transient unavailable history")
            return original(**arguments)

        with mock.patch.object(self.provider, "snapshot", side_effect=fail_once):
            results = runtime.process_delivery(self.delivery(1))
        self.assertEqual(len(calls), 2)
        self.assertEqual(recovery_calls, ["e1"])
        self.assertEqual(results[0]["status"], "completed")

    def test_failed_recovery_fabricates_neither_decision_nor_participant_turn(self):
        recovery_calls = []
        classifier_calls = []
        runtime = self.runtime(
            recover_current_history=lambda anchor: recovery_calls.append(anchor),
            classifier_transport=lambda projection, config: classifier_calls.append(projection),
        )
        with mock.patch.object(self.provider, "snapshot", side_effect=ValueError("unavailable")) as snapshot:
            results = runtime.process_delivery(self.delivery(1))
        self.assertEqual(snapshot.call_count, 2)
        self.assertEqual(recovery_calls, ["e1"])
        self.assertEqual(classifier_calls, [])
        self.assertEqual(self.participant_packets, [])
        self.assertEqual(results[0]["error"], "snapshot-unavailable")
        self.assertEqual(self.receipts, [])


if __name__ == "__main__":
    unittest.main()
