"""What becomes of a proposal reaches the agent, and the agent can withdraw it.

Zoe, 2026-10-04 (#90 on #94): an approval for a privileged action outlives
the agent's turn, so the conversation memory gains two things tested here.
The outcome reaches the agent: approved and done, denied, expired, or
cancelled goes into its memory and its next turn, so nothing happens in its
name without it knowing. And the agent can withdraw a proposal still
awaiting approval, for example when the person who asked says "never mind".
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nunchi.authorization import (
    AuthorizationCoordinator,
    AuthorizationJournal,
    CapabilityRule,
    PolicySnapshot,
    StaticPolicySource,
)
from nunchi.participant import TransportResult
from nunchi.participant_model import participant_tool_action
from nunchi.v2_contracts import validate_participant_wake
from tests.v2.test_shared_foundation import foundation, message

ZOE = {"human:zoe": {"kind": "human"}}


def proposal(origin="e1"):
    return {
        "kind": "privileged",
        "origin_event_id": origin,
        "capability": "workspace.file.write",
        "resource": {"kind": "workspace-file", "id": "repo:README.md"},
        "operation": {"path": "README.md", "content": "bounded"},
    }


class ProposalOutcomeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.journal = AuthorizationJournal(Path(temp.name) / "authorization.jsonl")
        self.native_calls = []
        self.wakes = []
        self.replies = []
        self.pipeline, _, self.transport, _ = foundation(participant=self.participant)

    def participant(self, **turn):
        self.wakes.append(turn["wake"])
        reply = self.replies.pop(0) if self.replies else None
        return reply(turn["wake"]) if callable(reply) else reply

    def coordinator(self, *, approval=True, ttl=300, result=None):
        rule = CapabilityRule(
            requester_actor_id="human:zoe",
            capability="workspace.file.write",
            platform="discord",
            room_id="42",
            participant_id="vigil",
            resource_kind="workspace-file",
            resource_id="repo:README.md",
            direct_allow=not approval,
            impact="high" if approval else "low",
        )

        def execute(operation, idempotency_key):
            self.native_calls.append(deepcopy(operation))
            return result or TransportResult("sent", "native-effect:1")

        coordinator = AuthorizationCoordinator(
            observation=self.pipeline.observation,
            policy_source=StaticPolicySource(PolicySnapshot("policy", "r1", (rule,), ("operator:zoe",))),
            journal=self.journal,
            executors={"workspace.file.write": execute},
            approval_ttl_seconds=ttl,
        )
        self.pipeline.host.privileged = coordinator
        return coordinator

    def deliver(self, event_id, text="Vigil, please update the README."):
        return self.pipeline.handle_delivery(delivery_id=f"d-{event_id}", event=message(event_id, text=text), actors=ZOE)

    def proposals_in(self, wake):
        return [move for move in wake.get("memory", {}).get("own_moves", ()) if move["kind"] == "proposal"]

    def propose(self, coordinator):
        self.replies.append(lambda wake: proposal(wake["trigger_event_id"]))
        outcome = self.deliver("e1")
        self.assertEqual("unavailable", outcome.opportunities[0].transport.delivery)
        (record,) = coordinator.proposals()
        self.assertEqual("awaiting_approval", record["status"])
        return record

    def test_an_approved_and_done_proposal_reaches_the_next_turn(self):
        coordinator = self.coordinator()
        record = self.propose(coordinator)
        challenge = coordinator.pending_for_operator()[0]["challenge"]["approval_challenge_id"]
        # The next turn knows it is still waiting.
        self.deliver("e2", "Any news?")
        (waiting,) = self.proposals_in(self.wakes[-1])
        self.assertEqual(
            {
                "kind": "proposal",
                "proposal_id": record["proposal_id"],
                "about_event_id": "e1",
                "capability": "workspace.file.write",
                "status": "awaiting_approval",
                "at": record["at"],
            },
            waiting,
        )
        approved = coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge, authenticated_approver_id="operator:zoe"
        )
        self.assertEqual("sent", approved.delivery)
        self.deliver("e3", "Thanks!")
        (done,) = self.proposals_in(self.wakes[-1])
        self.assertEqual("done", done["status"])
        validate_participant_wake(self.wakes[-1])
        # Nunchi never says it in the room; only the agent can.
        self.assertEqual([], self.transport.calls)

    def test_a_proposal_that_waits_too_long_expires(self):
        coordinator = self.coordinator()
        self.propose(coordinator)
        challenge = coordinator.pending_for_operator()[0]["challenge"]
        later = coordinator.proposals()[0]
        with mock.patch("nunchi.authorization._now", return_value=_after(challenge["expires_at"])):
            self.assertEqual("expired", coordinator.proposals()[0]["status"])
            result = coordinator.complete_authenticated_approval(
                approval_challenge_id=challenge["approval_challenge_id"], authenticated_approver_id="operator:zoe"
            )
        self.assertEqual("failed", result.delivery)
        self.assertEqual("expired", coordinator.proposals()[0]["status"])
        self.assertEqual(later["proposal_id"], coordinator.proposals()[0]["proposal_id"])
        self.assertEqual([], self.native_calls)

    def test_the_agent_can_withdraw_a_proposal_awaiting_approval(self):
        coordinator = self.coordinator()
        record = self.propose(coordinator)
        challenge = coordinator.pending_for_operator()[0]["challenge"]["approval_challenge_id"]
        self.replies.append({"kind": "withdraw", "origin_event_id": "e2", "proposal_id": record["proposal_id"], "why": "Zoe changed her mind."})
        outcome = self.deliver("e2", "Never mind, I'll do it myself.")
        self.assertEqual("sent", outcome.opportunities[0].transport.delivery)
        self.assertEqual("withdrawn", coordinator.proposals()[0]["status"])
        self.assertEqual((), coordinator.pending_for_operator())
        # An operator can no longer approve it, and nothing runs.
        late = coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge, authenticated_approver_id="operator:zoe"
        )
        self.assertEqual("failed", late.delivery)
        self.assertEqual([], self.native_calls)
        self.assertEqual("withdrawn", coordinator.proposals()[0]["status"])
        # A second withdrawal, or one of an unknown proposal, changes nothing.
        for proposal_id in (record["proposal_id"], "authorization:unknown"):
            with self.subTest(proposal_id=proposal_id):
                again = coordinator.withdraw(proposal_id=proposal_id, wake=self.wakes[-1])
                self.assertEqual(("failed", "the proposal is not awaiting approval"), (again.delivery, again.detail))

    def test_immediate_outcomes_are_remembered_too(self):
        coordinator = self.coordinator(approval=False)
        self.replies.append(lambda wake: proposal(wake["trigger_event_id"]))
        self.deliver("e1")
        self.assertEqual("done", coordinator.proposals()[0]["status"])
        failing = self.coordinator(approval=False, result=TransportResult("failed", "disk full"))
        self.replies.append(lambda wake: proposal(wake["trigger_event_id"]))
        self.deliver("e2")
        self.assertEqual("failed", failing.proposals()[0]["status"])

    def test_a_denied_proposal_says_so(self):
        coordinator = self.coordinator()
        coordinator.policy_source = StaticPolicySource(PolicySnapshot("policy", "r2", (), ("operator:zoe",)))
        self.replies.append(lambda wake: proposal(wake["trigger_event_id"]))
        outcome = self.deliver("e1")
        self.assertEqual("failed", outcome.opportunities[0].transport.delivery)
        self.assertEqual("denied", coordinator.proposals()[0]["status"])

    def test_a_host_cancel_marks_waiting_proposals_cancelled(self):
        coordinator = self.coordinator()
        self.propose(coordinator)
        self.pipeline.cancel()
        self.assertEqual("cancelled", coordinator.proposals()[0]["status"])

    def test_withdrawal_needs_privileged_actions(self):
        self.replies.append({"kind": "withdraw", "origin_event_id": "e1", "proposal_id": "authorization:x"})
        outcome = self.deliver("e1")
        self.assertEqual("unavailable", outcome.opportunities[0].transport.delivery)

    def test_only_a_participant_that_may_propose_hears_how_to_withdraw(self):
        from nunchi.participant_model import ParticipantTurnProtocol
        from tests.v2.test_operator_protocol import PROFILE, opportunity, wake

        allowed = opportunity()
        allowed["permissions"]["privileged_proposals"] = True
        denied = opportunity()
        denied["permissions"]["privileged_proposals"] = False
        withdraw = "kind withdraw with a proposal_id withdraws"
        self.assertIn(withdraw, ParticipantTurnProtocol(profile=PROFILE, wake=wake(), opportunity=allowed).instructions)
        self.assertNotIn(withdraw, ParticipantTurnProtocol(profile=PROFILE, wake=wake(), opportunity=denied).instructions)

    def test_a_tool_host_withdraws_through_its_own_tool(self):
        request = {
            "permissions": {"ordinary_actions": ["message"], "privileged_proposals": True},
            "wake": {"trigger_event_id": "e1"},
        }
        self.assertEqual(
            {"kind": "withdraw", "origin_event_id": "e1", "proposal_id": "authorization:x"},
            participant_tool_action("withdraw", {"proposal_id": "authorization:x"}, request=request, visible_event_ids={"e1"}),
        )


def _after(timestamp):
    from datetime import datetime, timedelta

    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")) + timedelta(seconds=1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
