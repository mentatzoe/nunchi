"""The agent reports an approved action's outcome itself (#94 step 6).

Zoe, #90 decision 2 on #94: when an approved action completes after the
agent's turn has ended, the agent is the one who says so in the room;
Nunchi doesn't. So when an approval settles, the agent gets a turn about
the message it proposed the action for, with ``occasion: "outcome"`` and
the outcome in its memory. Attention still reads the room, as advice, but
cannot keep that turn from the agent.
"""

from __future__ import annotations

from dataclasses import replace
import threading
import unittest

from nunchi.participant import TransportResult
from nunchi.pipeline import AsyncDeliveryLane
from nunchi.v2_contracts import validate_attention_decision, validate_participant_wake
from tests.v2.test_proposal_outcomes import ProposalFixture, proposal
from tests.v2.test_shared_foundation import message

ZOE = {"human:zoe": {"kind": "human"}}


class OutcomeTurnTests(ProposalFixture, unittest.TestCase):
    def approve(self, coordinator):
        challenge = coordinator.pending_for_operator()[0]["challenge"]["approval_challenge_id"]
        return coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge, authenticated_approver_id="operator:zoe"
        )

    def proposed(self, **coordinator_options):
        coordinator = self.coordinator(**coordinator_options)
        coordinator.add_outcome_listener(self.pipeline.outcome_arrived)
        record = self.propose(coordinator)
        return coordinator, record

    def test_the_agent_gets_a_turn_to_say_its_approved_action_is_done(self):
        coordinator, record = self.proposed()
        self.deliver("e2", "Thanks, no rush.")
        self.assertFalse(self.pipeline.outcomes_waiting())
        self.assertEqual("sent", self.approve(coordinator).delivery)
        self.assertTrue(self.pipeline.outcomes_waiting())
        self.replies.append({"kind": "reply", "origin_event_id": "e1", "target_event_id": "e1",
                             "text": "Done: the README is updated."})
        (outcome,) = self.pipeline.report_outcomes()
        wake = self.wakes[-1]
        self.assertEqual(("e1", "outcome"), (wake["trigger_event_id"], wake["occasion"]))
        (done,) = self.proposals_in(wake)
        self.assertEqual((record["proposal_id"], "done"), (done["proposal_id"], done["status"]))
        validate_participant_wake(wake)
        # The agent said it, not Nunchi.
        self.assertEqual("sent", outcome.transport.delivery)
        self.assertEqual("Done: the README is updated.", self.transport.calls[-1][0]["text"])
        self.assertFalse(self.pipeline.outcomes_waiting())
        self.assertEqual((), self.pipeline.report_outcomes())

    def test_a_reading_to_stay_quiet_still_reaches_the_agent(self):
        coordinator, _ = self.proposed()
        self.approve(coordinator)
        self.pipeline.report_outcomes()
        for disposition in ("SUPPRESS", "ACK"):
            with self.subTest(disposition=disposition):
                self.pipeline.attention.model.disposition = disposition
                self.pipeline.outcome_arrived(coordinator.proposals()[0])
                before = len(self.wakes)
                self.pipeline.report_outcomes()
                self.assertEqual(before + 1, len(self.wakes))
                self.assertEqual("DEFER", self.wakes[-1]["attention"]["source"])

    def test_the_widening_is_audited_and_only_an_outcome_may_use_it(self):
        coordinator, _ = self.proposed()
        self.approve(coordinator)
        self.pipeline.attention.model.disposition = "SUPPRESS"
        request = self.pipeline.observation.build_snapshot("e1", occasion="outcome")
        decision = self.pipeline.attention.judge(request)
        self.assertEqual(
            ("SUPPRESS", "DEFER", "policy-defer", "outcome-turn"),
            (
                decision["classifier_disposition"],
                decision["effective_disposition"],
                decision["routing_audit"]["valve"],
                decision["routing_audit"]["override_cause"],
            ),
        )
        validate_attention_decision(decision, request=request)
        ordinary = self.pipeline.observation.build_snapshot("e1")
        with self.assertRaises(Exception):
            validate_attention_decision(dict(decision, request_id=ordinary["request_id"]), request=ordinary)
        # An outcome turn that would reach the agent anyway is not widened.
        self.pipeline.attention.model.disposition = "WAKE"
        woken = self.pipeline.attention.judge(self.pipeline.observation.build_snapshot("e1", occasion="outcome"))
        self.assertEqual("none", woken["routing_audit"]["override_cause"])

    def test_a_failed_attention_still_gives_the_outcome_turn(self):
        coordinator, _ = self.proposed()
        self.approve(coordinator)
        attention = self.pipeline.attention
        attention.policy = replace(attention.policy, error_action="NO_WAKE")
        attention.model.fail = True
        before = len(self.wakes)
        self.pipeline.report_outcomes()
        self.assertEqual(before + 1, len(self.wakes))
        self.assertEqual("ERROR_FALLBACK", self.wakes[-1]["attention"]["source"])

    def test_a_failed_or_denied_action_gets_its_turn_too(self):
        coordinator, _ = self.proposed(result=TransportResult("failed", "disk full"))
        self.assertEqual("failed", self.approve(coordinator).delivery)
        self.pipeline.report_outcomes()
        (failed,) = self.proposals_in(self.wakes[-1])
        self.assertEqual(("outcome", "failed"), (self.wakes[-1]["occasion"], failed["status"]))

    def test_no_outcome_turn_without_an_approval(self):
        # Withdrawn, expired and cancelled proposals never ran: no turn.
        coordinator, record = self.proposed()
        coordinator.withdraw(proposal_id=record["proposal_id"], wake=self.wakes[-1])
        coordinator.cancel()
        self.assertFalse(self.pipeline.outcomes_waiting())

    def test_an_outcome_waits_while_another_turn_runs(self):
        coordinator, _ = self.proposed()
        self.approve(coordinator)
        active = self.pipeline.scheduler.offer("e1")
        self.assertEqual((), self.pipeline.report_outcomes())
        self.assertTrue(self.pipeline.outcomes_waiting())
        self.pipeline.scheduler.complete(active)
        self.pipeline.report_outcomes()
        self.assertEqual("outcome", self.wakes[-1]["occasion"])

    def test_an_outcome_about_a_message_that_left_the_window_uses_the_newest(self):
        coordinator, _ = self.proposed()
        self.approve(coordinator)
        self.pipeline.observation.observe(delivery_id="d-e9", event=message("e9", text="Later."), actors=ZOE)
        # The agent's own message is newer, but a turn is about someone else's.
        self.pipeline.observation.observe(
            delivery_id="d-v9", event=message("v9", author_id="discord:bot:9", text="Noted."), actors=ZOE
        )
        self.pipeline._outcomes[0]["about_event_id"] = "gone"
        self.pipeline.report_outcomes()
        self.assertEqual(("e9", "outcome"), (self.wakes[-1]["trigger_event_id"], self.wakes[-1]["occasion"]))

    def test_an_outcome_turn_leaves_a_look_again_alone(self):
        coordinator, _ = self.proposed()
        self.approve(coordinator)
        self.pipeline._newest_eligible = "e1"
        self.pipeline._look_again = ("e2", 1e12)
        self.pipeline.report_outcomes()
        self.assertEqual("e2", self.pipeline._look_again[0])

    def test_a_failing_listener_never_breaks_the_approval(self):
        coordinator, _ = self.proposed()

        def broken(_):
            raise RuntimeError("listener failed")

        coordinator.add_outcome_listener(broken)
        self.assertEqual("sent", self.approve(coordinator).delivery)
        self.assertTrue(self.pipeline.outcomes_waiting())

    def test_cancel_and_restart_drop_waiting_outcomes(self):
        for stop in ("cancel", "restart"):
            with self.subTest(stop=stop):
                self.pipeline.outcome_arrived({"proposal_id": "p", "about_event_id": "e1"})
                getattr(self.pipeline, stop)()
                self.assertFalse(self.pipeline.outcomes_waiting())


class LaneOutcomeTests(ProposalFixture, unittest.TestCase):
    def test_the_lane_gives_the_outcome_turn_on_its_own(self):
        coordinator = self.coordinator()
        told = threading.Event()

        def participant(**turn):
            self.wakes.append(turn["wake"])
            if turn["wake"].get("occasion") == "outcome":
                told.set()
                return None
            return proposal(turn["wake"]["trigger_event_id"])

        self.pipeline.host.participant = participant
        # The lane listens to the coordinator the host has when it starts.
        lane = AsyncDeliveryLane(self.pipeline)
        lane.submit(delivery_id="d-e1", event=message("e1", text="Vigil, update the README."), actors=ZOE)
        self.assertTrue(lane.drain(2))
        challenge = coordinator.pending_for_operator()[0]["challenge"]["approval_challenge_id"]
        coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge, authenticated_approver_id="operator:zoe"
        )
        self.assertTrue(told.wait(2))
        self.assertTrue(lane.drain(2))
        self.assertEqual((), lane.errors)
        self.assertEqual("e1", self.wakes[-1]["trigger_event_id"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
