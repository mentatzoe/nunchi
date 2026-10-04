"""Deterministic shared-host deadlines, independent of waiter scheduling."""

from dataclasses import replace
import queue
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from tests.v2 import test_shared_foundation as fixtures


class SharedDeadlineRaceTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.AuthorizationTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.clock = [1000.0]
        clock_module = mock.Mock(wraps=time)
        clock_module.monotonic.side_effect = lambda: self.clock[0]
        for module in ("pipeline", "participant", "attention", "authorization"):
            self.enterContext(mock.patch(
                f"nunchi.{module}.time", clock_module, create=True,
            ))

    def test_expired_policy_finishes_before_host_waiter_without_publishing_approval(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        self.addCleanup(release.set)
        case = self.case

        class DelayedPolicy:
            def load(inner):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("policy was not released")
                return fixtures.PolicySnapshot(
                    "policy", "approval", (replace(
                        case.rule, direct_allow=False, impact="high",
                    ),), ("operator:zoe",),
                )

        coordinator = case.coordinator(policy=DelayedPolicy())
        execute = coordinator.execute_proposal
        before_host_resumes = {}

        def observed_execute(**kwargs):
            try:
                result = execute(**kwargs)
                before_host_resumes["worker_delivery"] = result.delivery
                # Observe and try to use a stale approval BEFORE the host can
                # set cancellation. A host-only fix must fail this assertion.
                pending = coordinator.pending_for_operator()
                before_host_resumes["pending"] = pending
                if pending:
                    coordinator.complete_authenticated_approval(
                        approval_challenge_id=pending[0]["challenge"]["approval_challenge_id"],
                        authenticated_approver_id="operator:zoe",
                    )
                before_host_resumes["effects"] = len(case.native_calls)
                return result
            finally:
                finished.set()

        coordinator.execute_proposal = observed_execute
        queues = []
        clock = self.clock

        class ScheduledQueue(queue.Queue):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                queues.append(inner)
                inner.dispatch_queue = len(queues) == 2

            def get(inner, block=True, timeout=None):
                if inner.dispatch_queue:
                    if not entered.wait(2):
                        raise RuntimeError("policy was never reached")
                    # get() was called with positive remaining time, but its
                    # consumer is not scheduled again until the worker ends.
                    clock[0] = 1000.08
                    release.set()
                    if not finished.wait(2):
                        raise RuntimeError("coordinator did not finish")
                return super().get(block=block, timeout=timeout)

        self.enterContext(mock.patch("nunchi.participant.queue", SimpleNamespace(
            Queue=ScheduledQueue, Empty=queue.Empty,
        )))
        case.pipeline.host.privileged = coordinator
        case.pipeline.host.host_timeout_seconds = 0.03
        case.pipeline.host.participant = lambda **_: {
            **case.proposal(), "origin_event_id": "e2",
        }
        outcome = case.pipeline.handle_delivery(
            delivery_id="d2", event=fixtures.message("e2"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual((), before_host_resumes["pending"])
        self.assertEqual(0, before_host_resumes["effects"])
        self.assertEqual("failed", before_host_resumes["worker_delivery"])
        result = outcome.opportunities[0].transport
        assert result is not None
        self.assertEqual("unknown", result.delivery)
        self.assertEqual((), coordinator.pending_for_operator())
        self.assertEqual([], case.native_calls)

    def _host_proposal(self, coordinator):
        case = self.case
        case.pipeline.host.privileged = coordinator
        case.pipeline.host.host_timeout_seconds = 0.03
        case.pipeline.host.participant = lambda **_: {
            **case.proposal(), "origin_event_id": "e2",
        }
        return case.pipeline.handle_delivery(
            delivery_id="d2", event=fixtures.message("e2"),
            actors={"human:zoe": {"kind": "human"}},
        )

    def _approval(self):
        self.case.policy.replace(fixtures.PolicySnapshot(
            "policy", "approval", (replace(
                self.case.rule, direct_allow=False, impact="high",
            ),), ("operator:zoe",),
        ))
        coordinator = self.case.coordinator()
        outcome = self._host_proposal(coordinator)
        result = outcome.opportunities[0].transport
        assert result is not None
        self.assertEqual("unavailable", result.delivery)
        pending = coordinator.pending_for_operator()
        self.assertEqual(1, len(pending))
        self.assertFalse(self.case.pipeline.scheduler.active)
        return coordinator, pending[0]["challenge"]["approval_challenge_id"]

    def _approve(self, coordinator, challenge):
        return coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge,
            authenticated_approver_id="operator:zoe",
        )

    def _expire_on_record(self, kind):
        append = self.case.journal.append

        def delayed_append(record):
            result = append(record)
            record_kind = (
                record["record"]["kind"]
                if record["kind"] == "authorization_contract"
                else record["kind"]
            )
            if record_kind == kind:
                self.clock[0] = 1000.03
            return result

        self.enterContext(mock.patch.object(
            self.case.journal, "append", side_effect=delayed_append,
        ))

    def test_on_time_host_approval_executes_once_after_scheduler_completion(self):
        coordinator, challenge = self._approval()
        self.clock[0] = 1000.02
        self.assertEqual("sent", self._approve(coordinator, challenge).delivery)
        self.assertEqual("failed", self._approve(coordinator, challenge).delivery)
        self.assertEqual(1, len(self.case.native_calls))

    def test_published_approval_outlives_the_participant_turn_deadline(self):
        # The turn deadline bounds how long the host waits on the model, not
        # how long a human operator has to decide. A published challenge stays
        # usable for the window its expires_at advertises.
        coordinator, challenge = self._approval()
        self.clock[0] = 1000.03 + 60
        pending = coordinator.pending_for_operator()
        self.assertEqual(1, len(pending))
        self.assertEqual("sent", self._approve(coordinator, challenge).delivery)
        self.assertEqual(1, len(self.case.native_calls))

    def test_cancelled_approval_cannot_be_used(self):
        coordinator, challenge = self._approval()
        self.case.pipeline.cancel()
        self.assertEqual((), coordinator.pending_for_operator())
        self.assertEqual("failed", self._approve(coordinator, challenge).delivery)
        self.assertEqual([], self.case.native_calls)

    def test_approval_past_its_own_expiry_cannot_be_used(self):
        coordinator, challenge = self._approval()
        expires_at = coordinator.pending_for_operator()[0]["challenge"]["expires_at"]
        later = fixtures.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        with mock.patch(
            "nunchi.authorization._now",
            return_value=later + fixtures.timedelta(seconds=1),
        ):
            self.assertEqual("failed", self._approve(coordinator, challenge).delivery)
        self.assertEqual([], self.case.native_calls)

    def test_deadline_during_challenge_persistence_prevents_publication(self):
        self._expire_on_record("approval_challenge")
        self.case.policy.replace(fixtures.PolicySnapshot(
            "policy", "approval", (replace(
                self.case.rule, direct_allow=False, impact="high",
            ),), ("operator:zoe",),
        ))
        coordinator = self.case.coordinator()
        result = coordinator.execute_proposal(
            proposal=self.case.proposal(), wake=self.case.wake,
            cancel=threading.Event(), deadline=1000.03,
        )
        self.assertEqual("failed", result.delivery)
        self.assertEqual((), coordinator.pending_for_operator())
        self.assertEqual([], self.case.native_calls)

    def test_deadline_during_direct_commit_prevents_effect_and_replay(self):
        self._expire_on_record("effect_commit")
        coordinator = self.case.coordinator()
        result = coordinator.execute_proposal(
            proposal=self.case.proposal(), wake=self.case.wake,
            cancel=threading.Event(), deadline=1000.03,
        )
        self.assertEqual("failed", result.delivery)
        # A persisted consumption is never reused even if dispatch was fenced.
        retry = coordinator.execute_proposal(
            proposal=self.case.proposal(), wake=self.case.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("failed", retry.delivery)
        self.assertEqual([], self.case.native_calls)

    def test_expiry_during_approved_commit_prevents_effect_and_closes_commit(self):
        coordinator, challenge = self._approval()
        expires_at = coordinator.pending_for_operator()[0]["challenge"]["expires_at"]
        after = fixtures.datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        ) + fixtures.timedelta(seconds=1)
        real_now = fixtures.datetime.now
        moments = {"expired": False}
        append = self.case.journal.append

        def expiring_append(record):
            result = append(record)
            if record["kind"] == "effect_commit":
                moments["expired"] = True
            return result

        def now():
            return after if moments["expired"] else real_now(fixtures.timezone.utc)

        self.enterContext(mock.patch.object(
            self.case.journal, "append", side_effect=expiring_append,
        ))
        self.enterContext(mock.patch("nunchi.authorization._now", side_effect=now))
        self.assertEqual("failed", self._approve(coordinator, challenge).delivery)
        self.assertEqual([], self.case.native_calls)
        last = self.case.journal.records()[-1]
        self.assertEqual("effect_result", last["kind"])
        self.assertEqual("FAILED", last["outcome"])
        self.assertTrue(last["detail"].startswith("privileged effect was not attempted"))

    def test_deadline_during_final_policy_reload_prevents_direct_effect(self):
        load = self.case.policy.load
        loads = []

        def delayed_load():
            policy = load()
            loads.append(policy)
            if len(loads) == 3:
                self.clock[0] = 1000.03
            return policy

        self.enterContext(mock.patch.object(self.case.policy, "load", side_effect=delayed_load))
        result = self.case.coordinator().execute_proposal(
            proposal=self.case.proposal(), wake=self.case.wake,
            cancel=threading.Event(), deadline=1000.03,
        )
        self.assertEqual(3, len(loads))
        self.assertEqual("failed", result.delivery)
        self.assertEqual([], self.case.native_calls)

    def test_deadline_during_final_origin_recheck_prevents_effect(self):
        resolve = self.case.pipeline.observation.resolve_event
        resolutions = []

        def delayed_resolve(event_id):
            result = resolve(event_id)
            resolutions.append(event_id)
            if len(resolutions) == 3:
                self.clock[0] = 1000.03
            return result

        self.enterContext(mock.patch.object(
            self.case.pipeline.observation, "resolve_event", side_effect=delayed_resolve,
        ))
        result = self.case.coordinator().execute_proposal(
            proposal=self.case.proposal(), wake=self.case.wake,
            cancel=threading.Event(), deadline=1000.03,
        )
        self.assertEqual(3, len(resolutions))
        self.assertEqual("failed", result.delivery)
        self.assertEqual([], self.case.native_calls)

    def test_deadline_during_unknown_retry_commit_prevents_second_effect(self):
        self.case.policy.replace(fixtures.PolicySnapshot(
            "policy", "idempotent", (replace(
                self.case.rule, target_idempotency=True,
            ),), ("operator:zoe",),
        ))
        coordinator = self.case.coordinator(result=fixtures.TransportResult("unknown"))
        first = coordinator.execute_proposal(
            proposal=self.case.proposal(), wake=self.case.wake, cancel=threading.Event(),
        )
        self.assertEqual("unknown", first.delivery)
        self._expire_on_record("effect_retry_commit")
        retry = coordinator.execute_proposal(
            proposal=self.case.proposal(), wake=self.case.wake,
            cancel=threading.Event(), deadline=1000.03,
        )
        self.assertEqual("failed", retry.delivery)
        self.assertEqual(1, len(self.case.native_calls))

    def test_late_native_ack_is_unknown_to_host_but_remains_confirmed_in_effect_journal(self):
        coordinator = self.case.coordinator()
        cancellations = []

        def participant(**kwargs):
            cancellations.append(kwargs["cancel"])
            return {**self.case.proposal(), "origin_event_id": "e2"}

        queues = []
        clock = self.clock

        class ScheduledQueue(queue.Queue):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                queues.append(inner)
                inner.dispatch_queue = len(queues) == 2

            def get(inner, block=True, timeout=None):
                result = super().get(block=block, timeout=timeout)
                if inner.dispatch_queue:
                    clock[0] = 1000.08
                return result

        self.enterContext(mock.patch("nunchi.participant.queue", SimpleNamespace(
            Queue=ScheduledQueue, Empty=queue.Empty,
        )))
        self.case.pipeline.host.privileged = coordinator
        self.case.pipeline.host.host_timeout_seconds = 0.03
        self.case.pipeline.host.participant = participant
        outcome = self.case.pipeline.handle_delivery(
            delivery_id="d2", event=fixtures.message("e2"),
            actors={"human:zoe": {"kind": "human"}},
        )
        result = outcome.opportunities[0].transport
        assert result is not None
        self.assertEqual("unknown", result.delivery)
        self.assertTrue(cancellations[0].is_set())
        self.assertEqual(1, len(self.case.native_calls))
        records = self.case.journal.records()
        self.assertEqual("CONFIRMED", records[-1]["outcome"])
        request_id = outcome.opportunities[0].request_id
        assert request_id is not None
        receipts = self.case.pipeline.host.receipts.records(request_id)
        self.assertEqual("unknown", receipts[-2]["body"]["outcome"])
        self.assertEqual("unknown", receipts[-1]["body"]["delivery"])


if __name__ == "__main__":
    unittest.main()
