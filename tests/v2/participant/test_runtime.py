from __future__ import annotations

import copy
import tempfile
import threading
import unittest
from unittest import mock

from nunchi.authorization import (
    PrivilegedActionCoordinator,
    PrivilegedActionGuard,
    canonical_action_digest,
)
from nunchi.policy import OperatorPolicySource, load_operator_policy
from nunchi.runtime import LiveRoomRuntime, LiveRoomRuntimeError
from nunchi.scheduling import ConversationOpportunityScheduler
from tests.v2.contract.schema_helpers import make_authorization_request
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


class ChangesAfterCopy(dict):
    """Mapping whose caller-owned view changes after the defensive copy."""

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo)

    def get(self, key, default=None):
        if key == "event":
            return None
        return super().get(key, default)


class HostCancellation(BaseException):
    pass


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
    def test_attention_receipt_failure_stops_before_participant_and_action(self):
        persisted = []
        effects = []

        def sink(receipt):
            if receipt["stage"] == "attention":
                raise OSError("durability unavailable")
            persisted.append(receipt)

        runtime = self.runtime(
            receipt_sink=sink,
            participant=lambda _turn: self.fail("receipt failure must not invoke"),
            action_sink=effects.append,
        )
        results = runtime.process_delivery(self.delivery(1))
        self.assertEqual(results[0]["status"], "error")
        self.assertEqual(
            results[0]["error"],
            "attention-receipt-persistence-unknown",
        )
        self.assertEqual([record["stage"] for record in persisted], ["observation"])
        self.assertEqual(effects, [])

    def test_concurrent_accept_preserves_ingest_order_in_scheduler(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingScheduler(ConversationOpportunityScheduler):
            def observe(inner_self, **arguments):
                if arguments["anchor_event_id"] == "e1":
                    entered.set()
                    self.assertTrue(release.wait(5))
                return super().observe(**arguments)

        runtime = self.runtime(scheduler=BlockingScheduler())
        accepted = []
        first = threading.Thread(
            target=lambda: accepted.append(runtime.accept(self.delivery(1))),
            daemon=True,
        )
        second = threading.Thread(
            target=lambda: accepted.append(runtime.accept(self.delivery(2))),
            daemon=True,
        )
        first.start()
        self.assertTrue(entered.wait(5))
        second.start()
        release.set()
        first.join(5)
        second.join(5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([event["id"] for event in self.provider._events], ["e1", "e2"])
        state = runtime.scheduler.snapshot()[0]
        self.assertEqual(state["active_anchor_event_id"], "e1")
        self.assertEqual(state["pending_anchor_event_id"], "e2")

    def test_non_none_observation_receipt_ack_stops_before_attention(self):
        offered = []

        def ambiguous_receipt(receipt):
            offered.append(receipt)
            return False

        runtime = self.runtime(receipt_sink=ambiguous_receipt)
        results = runtime.process_delivery(self.delivery(1))
        self.assertEqual(results[0]["status"], "error")
        self.assertEqual(
            results[0]["error"],
            "observation-receipt-persistence-unknown",
        )
        self.assertEqual([record["stage"] for record in offered], ["observation"])
        self.assertEqual(self.participant_packets, [])

    def test_single_delivery_schedules_from_the_exact_retained_copy(self):
        runtime = self.runtime()
        delivery = ChangesAfterCopy(self.delivery(1))
        accepted = runtime.accept(delivery)
        self.assertEqual(accepted.observation_disposition, "observed")
        self.assertIsNotNone(accepted.opportunity)
        self.assertEqual(accepted.opportunity.anchor_event_id, "e1")

    def test_batch_schedules_from_the_exact_retained_copy(self):
        runtime = self.runtime()
        accepted = runtime.accept_batch(
            [ChangesAfterCopy(self.delivery(1)), ChangesAfterCopy(self.delivery(2))]
        )
        self.assertEqual(accepted.observation_dispositions, ("observed", "observed"))
        self.assertIsNotNone(accepted.opportunity)
        self.assertEqual(accepted.opportunity.anchor_event_id, "e2")

    def test_backfill_batch_is_context_only_and_creates_no_wake_obligation(self):
        runtime = self.runtime()
        dispositions = runtime.observe_context_batch(
            [self.delivery(index) for index in range(1, 21)]
        )
        self.assertEqual(dispositions, ("observed",) * 20)
        self.assertEqual(runtime.scheduler.snapshot(), ())
        self.assertEqual(self.participant_packets, [])
        live = runtime.accept(self.delivery(21))
        self.assertIsNotNone(live.opportunity)
        result = runtime.drain(live.opportunity)
        self.assertEqual(len(result), 1)
        self.assertIn(
            "e20",
            [event["id"] for event in self.participant_packets[0]["events"]],
        )

    def test_poll_batch_records_all_context_but_starts_only_newest_opportunity(self):
        classifier_calls = []

        def record_judgment(projection, config):
            classifier_calls.append(projection["trigger_event_id"])
            return wake_judgment(projection, config)

        runtime = self.runtime(classifier_transport=record_judgment)
        accepted = runtime.accept_batch(
            [self.delivery(index) for index in range(1, 21)]
        )
        self.assertEqual(accepted.observation_dispositions, ("observed",) * 20)
        self.assertIsNotNone(accepted.opportunity)
        self.assertEqual(accepted.opportunity.anchor_event_id, "e20")
        results = runtime.drain(accepted.opportunity)
        self.assertEqual(classifier_calls, ["e20"])
        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.participant_packets), 1)
        self.assertIn(
            "e20",
            [event["id"] for event in self.participant_packets[0]["events"]],
        )

    def test_poll_batch_replaces_only_pending_anchor_while_work_is_active(self):
        runtime = self.runtime()
        first = runtime.accept(self.delivery(1))
        self.assertIsNotNone(first.opportunity)
        accepted = runtime.accept_batch(
            [self.delivery(index) for index in range(2, 21)]
        )
        self.assertIsNone(accepted.opportunity)
        self.assertEqual(
            runtime.scheduler.snapshot()[0]["pending_anchor_event_id"],
            "e20",
        )

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

    def test_host_cancellation_discards_pending_wake_but_retains_context(self):
        holder = {}

        def cancel_after_pending(_projection, _config):
            accepted = holder["runtime"].accept(self.delivery(2))
            self.assertIsNone(accepted.opportunity)
            raise HostCancellation()

        runtime = self.runtime(classifier_transport=cancel_after_pending)
        holder["runtime"] = runtime
        first = runtime.accept(self.delivery(1))
        with self.assertRaises(HostCancellation):
            runtime.drain(first.opportunity)
        self.assertEqual(runtime.scheduler.snapshot(), ())

        successor = runtime.accept(self.delivery(3))
        self.assertIsNotNone(successor.opportunity)
        self.assertEqual(successor.opportunity.anchor_event_id, "e3")
        self.assertEqual(
            [event["id"] for event in self.provider._events],
            ["e1", "e2", "e3"],
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


class RuntimeAuthorizationSurfaceCases(RuntimeCase):
    def test_runtime_exposes_pending_action_only_to_authenticated_host_surface(self):
        document = clone_policy()
        document["recoverability"][
            "continuity_scope_id"
        ] = "discord:room:42#2026-07"
        grant = document["authorization"]["grants"][1]
        grant["actor_id"] = "discord:1001"
        grant["scope"]["room_id"] = "42"
        grant["scope"]["resource"] = {
            "kind": "workspace-file",
            "id": "tmp/stale.txt",
        }
        grant["allowed_approver_actor_ids"] = ["discord:admin"]
        write_policy(self.temporary.name, document)
        operation = {"op": "delete", "path": "tmp/stale.txt"}
        proposal = make_authorization_request(
            action_id="runtime-action-1",
            action_digest=canonical_action_digest(operation),
            origin_event_id="e1",
            capability="workspace.file.delete",
            impact="destructive",
            scope={
                "platform": "discord",
                "room_id": "42",
                "participant_id": "vigil",
                "resource": {"kind": "workspace-file", "id": "tmp/stale.txt"},
            },
        )
        effects = []
        audits = []
        source = OperatorPolicySource(self.policy_path)
        coordinator = PrivilegedActionCoordinator(
            PrivilegedActionGuard(source.load),
            executors={"workspace.file.delete": effects.append},
            audit_sink=audits.append,
        )
        runtime = self.runtime(
            participant=lambda turn: {
                "kind": "privileged",
                "authorization_request": proposal,
                "operation": operation,
            },
            authorization_coordinator=coordinator,
        )
        result = runtime.process_delivery(self.delivery(1))[0]
        self.assertEqual(result["participant"]["outcome"], "silent")
        self.assertNotIn(
            "approval_challenge", result["participant"]["authorization"]
        )
        pending = runtime.pending_privileged_actions()
        challenge = pending[0]["authorization"]["approval_challenge"]
        completed = runtime.complete_authenticated_approval(
            {
                "challenge_id": challenge["challenge_id"],
                "attestation_id": "runtime-attestation-1",
                "approver_actor_id": "discord:admin",
                "approved_at": audits[0]["evaluated_at"],
                "channel": "local-operator",
            }
        )
        self.assertEqual(completed["execution"], "executed")
        self.assertEqual(effects, [operation])

    def test_runtime_without_privileged_seam_has_no_operator_surface(self):
        runtime = self.runtime()
        with self.assertRaises(LiveRoomRuntimeError):
            runtime.pending_privileged_actions()
        with self.assertRaises(LiveRoomRuntimeError):
            runtime.complete_authenticated_approval({})


if __name__ == "__main__":
    unittest.main()
