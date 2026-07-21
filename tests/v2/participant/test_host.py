from __future__ import annotations

import tempfile
import unittest

from nunchi.authorization import (
    PrivilegedActionCoordinator,
    PrivilegedActionGuard,
    canonical_action_digest,
)
from nunchi.participant import ParticipantTurn, build_participant_wake, run_participant_turn
from nunchi.policy import OperatorPolicySource, load_operator_policy
from tests.v2.contract.schema_helpers import (
    make_advice,
    make_authorization_request,
    make_decision_bypass,
    make_decision_error,
    make_decision_ok,
    make_request,
    validate_attention_receipt,
    validate_participant_wake,
)
from tests.v2.security.helpers import clone_policy, write_policy


class ParticipantHostCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.document = clone_policy()
        self.document["recoverability"]["continuity_scope_id"] = "discord:room:42#2026-07"
        grant = self.document["authorization"]["grants"][0]
        grant["actor_id"] = "discord:1001"
        grant["scope"]["room_id"] = "42"
        grant["scope"]["resource"] = {
            "kind": "workspace-file",
            "id": "docs/release.md",
        }
        self.path = write_policy(self.temporary.name, self.document)
        self.operator = load_operator_policy(self.path)
        self.snapshot = make_request()
        self.receipts = []

    def run_turn(self, decision, participant, **overrides):
        arguments = {
            "policy": self.operator.attention,
            "participant": participant,
            "receipt_sink": self.receipts.append,
        }
        arguments.update(overrides)
        return run_participant_turn(self.snapshot, decision, **arguments)


class WakePacketCases(ParticipantHostCase):
    def test_wake_packet_materializes_current_facts_and_grounded_advice(self):
        decision = make_decision_ok(
            "WAKE",
            "WAKE",
            "none",
            attention_advice=[make_advice()],
        )
        packet = build_participant_wake(
            self.snapshot,
            decision,
            policy=self.operator.attention,
        )
        self.assertEqual(validate_participant_wake(packet), [])
        self.assertEqual(packet["events"], self.snapshot["events"])
        self.assertEqual(packet["trigger_event_id"], "e3")
        self.assertEqual(packet["attention"]["source"], "WAKE")
        self.assertNotIn("reasons", repr(packet["attention"]))

    def test_bypass_defer_and_error_sources_are_advice_free(self):
        cases = (
            (make_decision_bypass(request_id="req-0001"), "PREATTENTION_BYPASS"),
            (make_decision_ok("DEFER", "DEFER", "classifier-defer"), "DEFER"),
            (make_decision_error(request_id="req-0001"), "ERROR_FALLBACK"),
        )
        for decision, source in cases:
            with self.subTest(source=source):
                packet = build_participant_wake(
                    self.snapshot,
                    decision,
                    policy=self.operator.attention,
                )
                self.assertEqual(validate_participant_wake(packet), [])
                self.assertEqual(packet["attention"], {"source": source})


class RoutingAndOutcomeCases(ParticipantHostCase):
    def test_suppress_invokes_no_participant_and_writes_no_host_stage(self):
        calls = []
        result = self.run_turn(
            make_decision_ok("SUPPRESS", "SUPPRESS", "none"),
            lambda turn: calls.append(turn),
        )
        self.assertEqual(result["status"], "suppressed")
        self.assertEqual(calls, [])
        self.assertEqual(self.receipts, [])

    def test_every_waking_source_can_end_silent(self):
        cases = (
            make_decision_ok("WAKE", "WAKE", "none"),
            make_decision_ok("DEFER", "DEFER", "classifier-defer"),
            make_decision_bypass(request_id="req-0001"),
            make_decision_error(request_id="req-0001"),
        )
        for decision in cases:
            with self.subTest(decision=decision["status"]):
                self.receipts.clear()
                result = self.run_turn(decision, lambda turn: None)
                self.assertEqual(result["outcome"], "silent")
                self.assertEqual(len(self.receipts), 1)
                self.assertEqual(validate_attention_receipt(self.receipts[0]), [])

    def test_actual_message_and_reaction_go_directly_to_action_sink(self):
        for action in (
            {
                "kind": "message",
                "content": "I can take the deploy.",
                "reply_to_event_id": "e1",
                "mention_actor_ids": ["discord:1001"],
            },
            {"kind": "reaction", "target_event_id": "e1", "reaction": "👀"},
        ):
            with self.subTest(kind=action["kind"]):
                self.receipts.clear()
                sent = []
                result = self.run_turn(
                    make_decision_ok("WAKE", "WAKE", "none"),
                    lambda turn, action=action: action,
                    action_sink=lambda value: sent.append(value),
                )
                self.assertEqual(result["outcome"], "sent")
                self.assertEqual(sent, [action])
                self.assertEqual(validate_attention_receipt(self.receipts[0]), [])

    def test_ambiguous_action_sink_ack_is_an_error_and_is_not_retried(self):
        action = {"kind": "message", "content": "I can take the deploy."}
        offered = []

        def ambiguous_sink(value):
            offered.append(value)
            return False

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            lambda _turn: action,
            action_sink=ambiguous_sink,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "action-sink-outcome-unknown")
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(offered, [action])
        self.assertEqual(len(self.receipts), 1)
        self.assertEqual(self.receipts[0]["body"]["outcome"], "sent")

    def test_ambiguous_correlated_action_sink_ack_is_an_error_and_not_retried(self):
        action = {"kind": "reaction", "target_event_id": "e1", "reaction": "👀"}
        offered = []

        def ambiguous_sink(request_id, value):
            offered.append((request_id, value))
            return {"accepted": True}

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            lambda _turn: action,
            correlated_action_sink=ambiguous_sink,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "action-sink-outcome-unknown")
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(offered, [("req-0001", action)])
        self.assertEqual(len(self.receipts), 1)
        self.assertEqual(self.receipts[0]["body"]["outcome"], "sent")

    def test_meta_answer_is_not_a_sendable_action_and_is_not_reclassified(self):
        calls = []

        def participant(turn):
            calls.append(turn)
            return {"should_respond": True, "reason": "yes"}

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            participant,
            action_sink=lambda value: self.fail("invalid meta answer must not send"),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["outcome"], "unknown")

    def test_no_wake_error_override_does_not_invoke_participant(self):
        policy = self.operator.attention
        object.__setattr__(policy, "error_action", "NO_WAKE")
        calls = []
        result = self.run_turn(
            make_decision_error(request_id="req-0001"),
            lambda turn: calls.append(turn),
            policy=policy,
        )
        self.assertEqual(result["status"], "no-wake")
        self.assertEqual(calls, [])
        self.assertEqual(validate_attention_receipt(self.receipts[0]), [])

    def test_no_wake_non_none_receipt_ack_is_persistence_unknown(self):
        policy = self.operator.attention
        object.__setattr__(policy, "error_action", "NO_WAKE")
        offered = []

        def ambiguous_receipt(receipt):
            offered.append(receipt)
            return False

        result = self.run_turn(
            make_decision_error(request_id="req-0001"),
            lambda _turn: self.fail("NO_WAKE must not invoke the participant"),
            policy=policy,
            receipt_sink=ambiguous_receipt,
        )
        self.assertEqual(result["status"], "no-wake")
        self.assertEqual(result["receipt_persistence"], "unknown")
        self.assertEqual([record["stage"] for record in offered], ["participant-host"])

    def test_bound_context_expansion_is_available_without_second_judgment(self):
        pages = []

        def fetch(request):
            pages.append(request)
            return {"events": [], "coverage": {}}

        def participant(turn: ParticipantTurn):
            self.assertEqual(turn.fetch_context({"direction": "before"})["events"], [])
            return None

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            participant,
            continuation_fetch=fetch,
        )
        self.assertEqual(result["outcome"], "silent")
        self.assertEqual(pages, [{"direction": "before"}])
        self.assertEqual(self.receipts[0]["body"]["expansion_calls"], 1)


class PrivilegedActionCases(ParticipantHostCase):
    def proposal(self, op, actor_capability="workspace.file.write"):
        return make_authorization_request(
            action_id="action-host-1",
            action_digest=canonical_action_digest(op),
            origin_event_id="e1",
            capability=actor_capability,
            impact="mutation",
            scope={
                "platform": "discord",
                "room_id": "42",
                "participant_id": "vigil",
                "resource": {"kind": "workspace-file", "id": "docs/release.md"},
            },
        )

    def test_exact_direct_grant_executes_through_shared_guard(self):
        operation = {"op": "write", "path": "docs/release.md", "content": "ready"}
        proposal = self.proposal(operation)
        guard = PrivilegedActionGuard(OperatorPolicySource(self.path).load)
        effects = []
        audits = []
        coordinator = PrivilegedActionCoordinator(
            guard,
            executors={"workspace.file.write": effects.append},
            audit_sink=audits.append,
        )
        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            lambda turn: {
                "kind": "privileged",
                "authorization_request": proposal,
                "operation": operation,
            },
            authorization_coordinator=coordinator,
        )
        self.assertEqual(result["outcome"], "sent")
        self.assertEqual(result["authorization"]["decision"], "ALLOW")
        self.assertEqual(effects, [operation])

    def test_unauthorized_or_unsupported_privileged_action_has_zero_effects(self):
        operation = {"op": "write", "path": "docs/release.md", "content": "ready"}
        proposal = self.proposal(operation, "workspace.file.publish")
        guard = PrivilegedActionGuard(OperatorPolicySource(self.path).load)
        effects = []
        coordinator = PrivilegedActionCoordinator(
            guard,
            executors={"workspace.file.publish": effects.append},
            audit_sink=lambda _decision: None,
        )
        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            lambda turn: {
                "kind": "privileged",
                "authorization_request": proposal,
                "operation": operation,
            },
            authorization_coordinator=coordinator,
        )
        self.assertEqual(result["authorization"]["decision"], "DENY")
        self.assertEqual(result["outcome"], "silent")
        self.assertEqual(effects, [])

    def test_approval_bound_action_is_retained_off_surface_and_completed_later(self):
        approval = self.document["authorization"]["grants"][1]
        approval["actor_id"] = "discord:1001"
        approval["scope"]["room_id"] = "42"
        approval["scope"]["resource"] = {
            "kind": "workspace-file",
            "id": "tmp/stale.txt",
        }
        approval["allowed_approver_actor_ids"] = ["discord:admin"]
        write_policy(self.temporary.name, self.document)
        operation = {"op": "delete", "path": "tmp/stale.txt"}
        proposal = make_authorization_request(
            action_id="action-host-approval",
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
        coordinator = PrivilegedActionCoordinator(
            PrivilegedActionGuard(OperatorPolicySource(self.path).load),
            executors={"workspace.file.delete": effects.append},
            audit_sink=audits.append,
        )
        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            lambda turn: {
                "kind": "privileged",
                "authorization_request": proposal,
                "operation": operation,
            },
            authorization_coordinator=coordinator,
        )
        self.assertEqual(result["outcome"], "silent")
        self.assertEqual(result["authorization"]["decision"], "APPROVAL_REQUIRED")
        self.assertNotIn("approval_challenge", result["authorization"])
        self.assertEqual(effects, [])
        pending = coordinator.pending_for_operator()
        self.assertEqual(pending[0]["operation"], operation)
        challenge = pending[0]["authorization"]["approval_challenge"]

        completed = coordinator.complete_authenticated_approval(
            {
                "challenge_id": challenge["challenge_id"],
                "attestation_id": "host-attestation-1",
                "approver_actor_id": "discord:admin",
                "approved_at": audits[0]["evaluated_at"],
                "channel": "authenticated-transport",
            }
        )
        self.assertEqual(completed["execution"], "executed")
        self.assertEqual(effects, [operation])
        self.assertEqual(coordinator.pending_for_operator(), ())


if __name__ == "__main__":
    unittest.main()
