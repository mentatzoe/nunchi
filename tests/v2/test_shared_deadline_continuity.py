"""Deadlines end one opportunity without losing the conversation around it.

Post-merge review of PR #83 (issue #85):

- a turn that misses its deadline must not discard the newest message that
  arrived meanwhile; that message still gets its own attention;
- an ACK observed after the opportunity ended is never recorded as sent;
- deadlines must be finite numbers;
- a commit left open at startup means the process stopped mid-effect, so
  it is UNKNOWN and an approved retry becomes possible;
- discarding pending approvals never strands the scheduler.
"""

from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest

from nunchi.ack import AckJournal, ReactionCapability
from nunchi.authorization import AuthorizationJournal
from nunchi.participant import ConversationOpportunityScheduler, ParticipantError
from nunchi.receipts import PersistenceError
from tests.v2 import test_shared_foundation as fx


class PendingMessageSurvivesDeadlineTests(unittest.TestCase):
    def test_newest_message_is_attended_after_a_late_dispatch(self) -> None:
        started = threading.Event()
        woken: list[str] = []

        class SlowTransport(fx.RecordingTransport):
            def dispatch(self, *, action, wake):
                if wake["trigger_event_id"] == "e0":
                    time.sleep(0.4)
                return super().dispatch(action=action, wake=wake)

        def participant(**kwargs):
            trigger = kwargs["wake"]["trigger_event_id"]
            woken.append(trigger)
            started.set()
            if trigger == "e0":
                time.sleep(0.15)
            return {"kind": "message", "origin_event_id": trigger, "text": "hi"}

        pipeline, model, _, _ = fx.foundation(
            participant=participant,
            transport=SlowTransport(),
            participant_timeout_seconds=0.3,
        )
        first = threading.Thread(
            target=lambda: pipeline.handle_delivery(
                delivery_id="d0",
                event=fx.message("e0"),
                actors={"human:zoe": {"kind": "human"}},
            )
        )
        first.start()
        self.assertTrue(started.wait(2))
        pipeline.handle_delivery(
            delivery_id="d1",
            event=fx.message("e1", text="urgent: are you there?"),
            actors={"human:zoe": {"kind": "human"}},
        )
        first.join(5)
        self.assertFalse(first.is_alive())
        self.assertEqual(2, len(model.calls), "e1 must reach attention")
        self.assertEqual(["e0", "e1"], woken)

    def test_expired_token_completes_and_promotes_pending(self) -> None:
        scheduler = ConversationOpportunityScheduler("room")
        token = scheduler.offer("e0")
        self.assertIsNone(scheduler.offer("e1"))
        scheduler.expire(token)
        self.assertFalse(scheduler.is_current(token))
        successor = scheduler.complete(token)
        self.assertIsNotNone(successor)
        self.assertEqual("e1", successor.anchor_event_id)

    def test_cancelled_token_still_cannot_complete(self) -> None:
        scheduler = ConversationOpportunityScheduler("room")
        token = scheduler.offer("e0")
        scheduler.offer("e1")
        scheduler.cancel()
        self.assertIsNone(scheduler.complete(token))


class LateAckTests(unittest.TestCase):
    def test_ack_observed_after_the_deadline_is_unknown_not_sent(self) -> None:
        capability = ReactionCapability(
            supported=True,
            authenticated=True,
            operations=("add", "remove"),
            reactions=("*",),
            permissions_revision="rev:1",
        )

        class SlowTransport(fx.RecordingTransport):
            def dispatch(self, *, action, wake):
                time.sleep(0.4)
                return super().dispatch(action=action, wake=wake)

        pipeline, _, _, receipts = fx.foundation(
            model=fx.FixtureModel("ACK"),
            transport=SlowTransport(capability=capability),
            participant_timeout_seconds=0.2,
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d-ack",
            event=fx.message("e-ack"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual("unknown", outcome.opportunities[0].transport.delivery)
        settled = [
            record
            for record in pipeline.host.ack_journal.records()
            if record["state"] == "settled"
        ]
        self.assertEqual(["unknown"], [record["delivery"] for record in settled])


class FiniteDeadlineTests(unittest.TestCase):
    NON_FINITE = (math.nan, math.inf, -math.inf)

    def test_scheduler_refuses_non_finite_effect_deadlines(self) -> None:
        for value in self.NON_FINITE:
            with self.subTest(value=value):
                scheduler = ConversationOpportunityScheduler("room")
                token = scheduler.offer("e0")
                self.assertFalse(scheduler.authorize_effect_commit(token, deadline=value))

    def test_ack_journal_refuses_non_finite_deadlines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = AckJournal(Path(temp) / "ack.jsonl")
            for value in self.NON_FINITE:
                with self.subTest(value=value):
                    with self.assertRaises(PersistenceError):
                        journal.reserve(_ack_binding(), deadline=value)

    def test_host_refuses_a_non_finite_turn_deadline(self) -> None:
        pipeline, _, _, _ = fx.foundation()
        pipeline.observation.observe(
            delivery_id="d1",
            event=fx.message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        token = pipeline.scheduler.offer("e1")
        request = pipeline.observation.build_snapshot("e1")
        with self.assertRaises(ParticipantError):
            pipeline.host.run(
                request=request,
                decision={"status": "bypass", "request_id": request["request_id"],
                          "cause": "preattention-disabled"},
                token=token,
                deadline=math.nan,
            )

    def test_coordinator_refuses_a_non_finite_deadline(self) -> None:
        case = fx.AuthorizationTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        result = case.coordinator().execute_proposal(
            proposal=case.proposal(),
            wake=case.wake,
            cancel=threading.Event(),
            deadline=math.nan,
        )
        self.assertEqual("failed", result.delivery)
        self.assertEqual([], case.native_calls)


class OpenCommitAtStartupTests(unittest.TestCase):
    def test_commit_without_result_is_unknown_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authorization.jsonl"
            record = {
                "kind": "effect_commit",
                "effect_fingerprint": "f" * 64,
                "action_id": "action-1",
                "decision_id": "decision-1",
                "action_digest": {"algorithm": "sha256", "value": "0" * 64},
                "idempotency_key": None,
                "committed_at": "2026-10-04T00:00:00Z",
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            journal = AuthorizationJournal(path)
            self.assertTrue(journal.consumed("f" * 64))
            self.assertTrue(journal.unknown("f" * 64))


class CoordinatorCancelTests(unittest.TestCase):
    def test_discarding_pending_approvals_does_not_strand_the_scheduler(self) -> None:
        case = fx.AuthorizationTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.policy.replace(
            fx.PolicySnapshot(
                "policy",
                "approval",
                (replace(case.rule, direct_allow=False, impact="high"),),
                ("operator:zoe",),
            )
        )
        scheduler = case.pipeline.scheduler
        token = scheduler.offer("e-live")
        coordinator = case.coordinator()
        # A pending approval published from inside the live turn.
        result = coordinator.execute_proposal(
            proposal=case.proposal(), wake=case.wake, cancel=token.cancel_event
        )
        self.assertEqual("unavailable", result.delivery)
        self.assertEqual(1, len(coordinator.pending_for_operator()))
        coordinator.cancel()
        self.assertEqual((), coordinator.pending_for_operator())
        self.assertTrue(scheduler.is_current(token))
        self.assertIsNone(scheduler.offer("e-next"))
        successor = scheduler.complete(token)
        self.assertIsNotNone(successor)
        self.assertEqual("e-next", successor.anchor_event_id)


def _ack_binding() -> dict:
    return {
        "request_id": "r1",
        "participant_id": "vigil",
        "actor_id": "discord:bot:9",
        "platform": "discord",
        "room_id": "42",
        "continuity_scope_id": "discord:channel:42",
        "target_event_id": "e1",
        "reaction": "👂",
        "operation": "add",
        "opportunity_generation": 1,
        "lifecycle_id": "lifecycle",
        "deadline_id": "deadline",
        "permissions_revision": "rev",
    }


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
