from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace

from nunchi.authorization import (
    PrivilegedActionCoordinator,
    PrivilegedActionGuard,
    canonical_action_digest,
)
from nunchi.participant import (
    MAX_EXPANSION_CALLS_PER_TURN,
    ParticipantHostError,
    ParticipantTurn,
    build_participant_wake,
    run_participant_turn,
)
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

    def policy_for(self, decision):
        return replace(
            self.operator.attention,
            preattention_enabled=decision.get("status") != "bypass",
        )


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
                    policy=self.policy_for(decision),
                )
                self.assertEqual(validate_participant_wake(packet), [])
                self.assertEqual(packet["attention"], {"source": source})

    def test_stale_suppression_malformed_advice_and_policy_inconsistent_bypass_fail_closed(self):
        stale = make_decision_ok("SUPPRESS", "SUPPRESS", "none")
        stale["request_id"] = "different-request"
        malformed = make_decision_ok("WAKE", "WAKE", "none")
        malformed["attention_advice"] = [{}]
        for decision in (stale, malformed, make_decision_bypass(request_id="req-0001")):
            with self.subTest(decision=decision):
                with self.assertRaises(ParticipantHostError):
                    run_participant_turn(
                        self.snapshot,
                        decision,
                        policy=self.operator.attention,
                        participant=lambda _turn: self.fail("invalid decision must not invoke"),
                        receipt_sink=self.receipts.append,
                    )


class RoutingAndOutcomeCases(ParticipantHostCase):
    def _enable_continuation(self):
        self.snapshot["continuation"] = {
            "handle_id": "cont-7f3a",
            "bound_to": {
                "participant_id": "vigil",
                "room_id": "42",
                "continuity_scope_id": "discord:room:42#2026-07",
                "trigger_event_id": "e3",
            },
            "can_fetch_before": True,
            "can_fetch_after": True,
            "can_fetch_around_event": True,
            "max_events_per_fetch": 20,
            "max_bytes_per_fetch": 32768,
        }

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
                result = self.run_turn(
                    decision,
                    lambda turn: None,
                    policy=self.policy_for(decision),
                )
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
        self.assertEqual(self.receipts[0]["body"]["outcome"], "unknown")

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
        self.assertEqual(self.receipts[0]["body"]["outcome"], "unknown")

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
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "participant-receipt-persistence-unknown")
        self.assertEqual(result["receipt_persistence"], "unknown")
        self.assertEqual([record["stage"] for record in offered], ["participant-host"])

    def test_bound_context_expansion_is_available_without_second_judgment(self):
        self._enable_continuation()
        pages = []

        def fetch(request):
            pages.append(request)
            return {
                "request_id": request["request_id"],
                "handle_id": request["handle_id"],
                "room_id": "42",
                "continuity_scope_id": "discord:room:42#2026-07",
                "direction": request["direction"],
                "anchor_event_id": "e3",
                "actors": {},
                "events": [],
                "coverage": {
                    "has_more_before": False,
                    "has_more_after": None,
                    "has_gaps": False,
                    "truncated_by": [],
                    "continuity": "restart-safe",
                    "has_restart_gap": False,
                    "max_events": request["max_events"],
                    "max_bytes": request["max_bytes"],
                },
            }

        def participant(turn: ParticipantTurn):
            self.assertEqual(
                turn.fetch_context(
                    {
                        "request_id": "req-0001",
                        "handle_id": "cont-7f3a",
                        "direction": "before",
                        "max_events": 20,
                        "max_bytes": 32768,
                    }
                )["events"],
                [],
            )
            return None

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            participant,
            continuation_fetch=fetch,
        )
        self.assertEqual(result["outcome"], "silent")
        self.assertEqual(pages[0]["direction"], "before")
        self.assertEqual(self.receipts[0]["body"]["expansion_calls"], 1)

    def test_turn_capabilities_are_explicit_and_expire_with_context_fetch(self):
        self._enable_continuation()
        retained = []

        def fetch(request):
            return {
                "request_id": request["request_id"],
                "handle_id": request["handle_id"],
                "room_id": "42",
                "continuity_scope_id": "discord:room:42#2026-07",
                "direction": request["direction"],
                "anchor_event_id": "e3",
                "actors": {},
                "events": [],
                "coverage": {
                    "has_more_before": False,
                    "has_more_after": None,
                    "has_gaps": False,
                    "truncated_by": [],
                    "continuity": "restart-safe",
                    "has_restart_gap": False,
                    "max_events": request["max_events"],
                    "max_bytes": request["max_bytes"],
                },
            }

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            lambda turn: retained.append(turn),
            continuation_fetch=fetch,
            action_sink=lambda _action: None,
        )
        self.assertEqual(result["outcome"], "silent")
        self.assertEqual(
            retained[0].capabilities,
            ("context-expansion", "message", "reaction"),
        )
        with self.assertRaisesRegex(ParticipantHostError, "closed"):
            retained[0].fetch_context(
                {
                    "request_id": "req-0001",
                    "handle_id": "cont-7f3a",
                    "direction": "before",
                    "max_events": 1,
                    "max_bytes": 1024,
                }
            )

    def test_action_references_must_name_delivered_facts(self):
        for action in (
            {"kind": "message", "content": "x", "reply_to_event_id": "missing"},
            {"kind": "message", "content": "x", "mention_actor_ids": ["discord:missing"]},
            {"kind": "reaction", "target_event_id": "missing", "reaction": "x"},
        ):
            effects = []
            result = self.run_turn(
                make_decision_ok("WAKE", "WAKE", "none"),
                lambda _turn, action=action: action,
                action_sink=effects.append,
            )
            self.assertEqual(result["status"], "error")
            self.assertEqual(effects, [])

    def test_context_expansion_rejects_request_and_page_budget_overruns(self):
        self._enable_continuation()
        cases = (
            (
                {"max_events": 21, "max_bytes": 32768},
                lambda request: self.fail("over-budget request must not fetch"),
            ),
            (
                {"max_events": 1, "max_bytes": 32768},
                lambda request: self._continuation_page(
                    request,
                    events=[self.snapshot["events"][0], self.snapshot["events"][1]],
                ),
            ),
        )
        for request_limits, fetch in cases:
            with self.subTest(request_limits=request_limits):
                def participant(turn):
                    turn.fetch_context(
                        {
                            "request_id": "req-0001",
                            "handle_id": "cont-7f3a",
                            "direction": "before",
                            **request_limits,
                        }
                    )

                result = self.run_turn(
                    make_decision_ok("WAKE", "WAKE", "none"),
                    participant,
                    continuation_fetch=fetch,
                )
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["outcome"], "unknown")

    def test_context_expansion_rejects_foreign_and_expired_capabilities_before_invocation(self):
        cases = (
            ("participant_id", "other", None),
            ("room_id", "99", None),
            ("continuity_scope_id", "wrong-scope", None),
            ("trigger_event_id", "alien", None),
            (None, None, "2000-01-01T00:00:00Z"),
        )
        for field, value, expires_at in cases:
            with self.subTest(field=field, expires_at=expires_at):
                self._enable_continuation()
                if field is not None:
                    self.snapshot["continuation"]["bound_to"][field] = value
                if expires_at is not None:
                    self.snapshot["continuation"]["expires_at"] = expires_at
                with self.assertRaisesRegex(
                    ParticipantHostError,
                    "binding or expiry",
                ):
                    self.run_turn(
                        make_decision_ok("WAKE", "WAKE", "none"),
                        lambda _turn: self.fail("invalid capability must not invoke"),
                        continuation_fetch=lambda _request: self.fail(
                            "invalid capability must not fetch"
                        ),
                        fetch_time=lambda: "2026-07-22T00:00:00Z",
                    )

    def test_context_expansion_rejects_cursor_not_returned_in_this_turn(self):
        self._enable_continuation()

        def participant(turn):
            turn.fetch_context(
                {
                    "request_id": "req-0001",
                    "handle_id": "cont-7f3a",
                    "direction": "before",
                    "max_events": 1,
                    "max_bytes": 1024,
                    "cursor": "never-issued",
                }
            )

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            participant,
            continuation_fetch=lambda _request: self.fail(
                "unissued cursor must stop before fetch"
            ),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["outcome"], "unknown")

    def test_context_expansion_has_an_absolute_per_turn_call_ceiling(self):
        self._enable_continuation()
        def fetch(request):
            page = self._continuation_page(request)
            page["next_cursor"] = f"cursor-{request.get('cursor', 'root')}-{len(calls)}"
            return page

        calls = []

        def participant(turn):
            cursor = None
            for _ in range(MAX_EXPANSION_CALLS_PER_TURN + 1):
                request = {
                    "request_id": "req-0001",
                    "handle_id": "cont-7f3a",
                    "direction": "before",
                    "max_events": 1,
                    "max_bytes": 32768,
                }
                if cursor is not None:
                    request["cursor"] = cursor
                page = turn.fetch_context(request)
                calls.append(request)
                cursor = page["next_cursor"]

        result = self.run_turn(
            make_decision_ok("WAKE", "WAKE", "none"),
            participant,
            continuation_fetch=fetch,
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(calls), MAX_EXPANSION_CALLS_PER_TURN)
        self.assertEqual(
            self.receipts[0]["body"]["expansion_calls"],
            MAX_EXPANSION_CALLS_PER_TURN,
        )

    def _continuation_page(self, request, *, events=None):
        return {
            "request_id": request["request_id"],
            "handle_id": request["handle_id"],
            "room_id": "42",
            "continuity_scope_id": "discord:room:42#2026-07",
            "direction": request["direction"],
            "anchor_event_id": request.get("anchor_event_id", "e3"),
            "actors": {},
            "events": list(events or []),
            "coverage": {
                "has_more_before": False,
                "has_more_after": None,
                "has_gaps": False,
                "truncated_by": [],
                "continuity": "restart-safe",
                "has_restart_gap": False,
                "max_events": request["max_events"],
                "max_bytes": request["max_bytes"],
            },
        }


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
