from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from nunchi.attention import (
    AttentionEngine,
    AttentionPolicy,
    ParticipantProfile,
)
from nunchi.authorization import (
    AuthorizationCoordinator,
    AuthorizationError,
    AuthorizationJournal,
    CapabilityRule,
    PolicySnapshot,
    StaticPolicySource,
    canonical_operation_digest,
)
from nunchi.errors import ValidationError
from nunchi.observation import (
    ObservationLimits,
    ObservationProvider,
    ParticipantBinding,
)
from nunchi.participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
    TransportResult,
)
from nunchi.pipeline import AsyncDeliveryLane, NunchiV2Pipeline
from nunchi.receipts import ReceiptJournal
from nunchi.v2_contracts import classifier_projection, validate_receipt_stream
from tests.v2.contract.schema_helpers import (
    validate_privileged_action_authorization_flow,
)


def message(
    event_id: str,
    author_id: str = "human:zoe",
    text: str = "Could you look at this?",
    **extra,
):
    event = {
        "id": event_id,
        "type": "message",
        "author_id": author_id,
        "text": text,
        "mentioned_actor_ids": [],
        "mentions_room": False,
    }
    event.update(extra)
    return event


class FixtureModel:
    name = "fixture-participant-attention"
    provider = "fixture"
    model_id = "fixture-v2"

    def __init__(self, disposition="WAKE", *, block=None, fail=False):
        self.disposition = disposition
        self.block = block
        self.fail = fail
        self.calls = []
        self.started = threading.Event()

    def judge(self, *, profile, projection, timeout_seconds):
        self.calls.append((profile, deepcopy(projection)))
        self.started.set()
        if self.block is not None:
            self.block.wait(timeout_seconds * 2)
        if self.fail:
            raise RuntimeError("fixture provider failed")
        evidence = [projection["trigger_event_id"]]
        return {
            "disposition": self.disposition,
            "reasons": [f"{profile.profile_id} judgment"],
            "evidence_event_ids": evidence,
            "legacy_verdict_confidences": (
                {"PASS": 0.9, "ACK": 0.03, "ASK": 0.03, "SPEAK": 0.04}
                if self.disposition == "SUPPRESS"
                else {"PASS": 0.02, "ACK": 0.03, "ASK": 0.05, "SPEAK": 0.9}
            ),
        }


class RecordingTransport:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or TransportResult("sent", "native:1")

    def dispatch(self, *, action, wake):
        self.calls.append((deepcopy(action), deepcopy(wake)))
        return self.result


def foundation(
    *,
    model=None,
    participant=None,
    policy=None,
    persistence_path=None,
    limits=None,
    transport=None,
    participant_timeout_seconds=300,
):
    binding = ParticipantBinding(
        participant_id="vigil",
        actor_id="discord:bot:9",
        platform="discord",
        room_id="42",
        continuity_scope_id="discord:channel:42",
        names=("Vigil", "Codex"),
    )
    receipts = ReceiptJournal()
    observation = ObservationProvider(
        binding,
        receipts=receipts,
        persistence_path=persistence_path,
        limits=limits,
    )
    model = model or FixtureModel()
    attention = AttentionEngine(
        profile=ParticipantProfile(
            profile_id="vigil-default",
            participant_id="vigil",
            actor_id="discord:bot:9",
            instructions="Contribute on security and implementation correctness.",
            provenance="trusted:test",
            sha256="0" * 64,
        ),
        model=model,
        policy=policy,
        receipts=receipts,
    )
    scheduler = ConversationOpportunityScheduler("vigil:discord:channel:42")
    transport = transport or RecordingTransport()
    host = ParticipantTurnHost(
        observation=observation,
        participant=participant or (lambda **_: None),
        transport=transport,
        scheduler=scheduler,
        receipts=receipts,
        participant_timeout_seconds=participant_timeout_seconds,
    )
    pipeline = NunchiV2Pipeline(
        observation=observation,
        attention=attention,
        host=host,
        scheduler=scheduler,
    )
    return pipeline, model, transport, receipts


class ObservationTests(unittest.TestCase):
    def test_exact_self_is_context_only_but_alias_collision_is_not_self(self):
        pipeline, model, _, _ = foundation()
        self_result = pipeline.handle_delivery(
            delivery_id="d-self",
            event=message("e-self", "discord:bot:9", "my earlier contribution"),
            actors={"discord:bot:9": {"display_name": "Vigil", "kind": "bot"}},
        )
        self.assertEqual("exact-self-context", self_result.observation.audit.outcome)
        self.assertEqual(0, len(model.calls))

        collision = pipeline.handle_delivery(
            delivery_id="d-human",
            event=message("e-human", "human:zoe", "Vigil is also my display name"),
            actors={
                "human:zoe": {"display_name": "Vigil", "kind": "human"},
            },
        )
        self.assertTrue(collision.observation.wake_eligible)
        self.assertEqual(1, len(model.calls))
        self.assertEqual(["e-self", "e-human"], [
            event["id"] for event in pipeline.observation.retained_events()
        ])

    def test_duplicate_unconstructable_and_route_rejection_never_call_model(self):
        pipeline, model, _, _ = foundation()
        first = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual(1, len(first.opportunities))
        for kwargs in (
            {
                "delivery_id": "d1",
                "event": message("e1"),
                "actors": {"human:zoe": {"kind": "human"}},
            },
            {"delivery_id": "d2", "event": None, "actors": None},
            {
                "delivery_id": "d3",
                "event": message("e3"),
                "actors": {"human:zoe": {"kind": "human"}},
                "authorized_route": False,
            },
        ):
            pipeline.handle_delivery(**kwargs)
        self.assertEqual(1, len(model.calls))

    def test_bounded_context_is_truthful_and_continuation_is_model_secret(self):
        limits = ObservationLimits(
            retention_events=20,
            retention_bytes=100_000,
            snapshot_events=3,
            snapshot_bytes=10_000,
            snapshot_age_seconds=86_400,
            continuation_events=2,
            continuation_bytes=10_000,
        )
        pipeline, model, _, _ = foundation(limits=limits)
        for index in range(5):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}", text=f"event {index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
        request = pipeline.observation.build_snapshot("e4")
        self.assertEqual(["e2", "e3", "e4"], [item["id"] for item in request["events"]])
        self.assertTrue(request["coverage"]["has_more_before"])
        self.assertIn("events", request["coverage"]["truncated_by"])
        projection = classifier_projection(request)
        serialized = json.dumps(projection)
        self.assertNotIn(request["continuation"]["handle_id"], serialized)
        self.assertNotIn("bound_to", serialized)
        self.assertTrue(projection["expansion"]["available"])

        with self.assertRaises(ValidationError):
            pipeline.observation.fetch_context(
                {
                    "request_id": request["request_id"],
                    "handle_id": request["continuation"]["handle_id"],
                    "direction": "before",
                    "max_events": 2,
                    "max_bytes": 1000,
                },
                host_context={
                    **request["continuation"]["bound_to"],
                    "room_id": "other-room",
                },
            )

    def test_restart_restores_context_without_creating_wake_work(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "observations.jsonl"
            first, _, _, _ = foundation(persistence_path=store)
            first.observation.observe(
                delivery_id="d1",
                event=message("e1"),
                actors={"human:zoe": {"kind": "human"}},
            )
            second, model, _, _ = foundation(persistence_path=store)
            self.assertEqual(["e1"], [event["id"] for event in second.observation.retained_events()])
            self.assertFalse(second.scheduler.active)
            self.assertEqual(0, len(model.calls))
            second.handle_delivery(
                delivery_id="d2",
                event=message("e2"),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertEqual(["e1", "e2"], [
                event["id"] for event in model.calls[0][1]["events"]
            ])


class AttentionAndHostTests(unittest.TestCase):
    def test_bypass_invokes_participant_without_model_or_advice(self):
        wakes = []
        model = FixtureModel()
        policy = AttentionPolicy(preattention_enabled=False)
        pipeline, _, transport, receipts = foundation(
            model=model,
            policy=policy,
            participant=lambda **kwargs: wakes.append(kwargs["wake"]) or None,
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual(0, len(model.calls))
        self.assertEqual("PREATTENTION_BYPASS", wakes[0]["attention"]["source"])
        self.assertEqual([], transport.calls)
        stream = receipts.records(outcome.opportunities[0].request_id)
        self.assertTrue(stream[1]["body"]["classifier_not_invoked"])
        self.assertEqual("silent", stream[2]["body"]["outcome"])

    def test_direct_and_margin_defer_remain_distinct(self):
        for disposition, expected_valve in (
            ("DEFER", "classifier-defer"),
            ("SUPPRESS", "margin-defer"),
        ):
            with self.subTest(disposition=disposition):
                model = FixtureModel(disposition)
                if disposition == "SUPPRESS":
                    original = model.judge

                    def close_margin(**kwargs):
                        result = original(**kwargs)
                        result["legacy_verdict_confidences"] = {
                            "PASS": 0.52,
                            "ACK": 0.1,
                            "ASK": 0.18,
                            "SPEAK": 0.48,
                        }
                        return result

                    model.judge = close_margin
                wakes = []
                pipeline, _, _, receipts = foundation(
                    model=model,
                    participant=lambda **kwargs: wakes.append(kwargs["wake"]) or None,
                )
                outcome = pipeline.handle_delivery(
                    delivery_id="d1",
                    event=message("e1"),
                    actors={"human:zoe": {"kind": "human"}},
                )
                self.assertEqual("DEFER", wakes[0]["attention"]["source"])
                request_id = outcome.opportunities[0].request_id
                self.assertEqual(
                    expected_valve,
                    receipts.records(request_id)[1]["body"]["routing_audit"]["valve"],
                )

    def test_governed_suppress_stops_only_participant(self):
        model = FixtureModel("SUPPRESS")
        pipeline, _, transport, receipts = foundation(model=model)
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual("SUPPRESS", outcome.opportunities[0].effective_disposition)
        self.assertEqual(0, pipeline.host.invocation_count)
        self.assertEqual([], transport.calls)
        self.assertEqual(2, len(receipts.records(outcome.opportunities[0].request_id)))
        self.assertEqual(["e1"], [event["id"] for event in pipeline.observation.retained_events()])

    def test_profile_binding_mismatch_errors_before_model_and_wakes_by_default(self):
        wakes = []
        pipeline, model, _, receipts = foundation(
            participant=lambda **kwargs: wakes.append(kwargs["wake"]) or None,
        )
        pipeline.attention.profile = ParticipantProfile(
            profile_id="swapped",
            participant_id="other",
            actor_id="discord:bot:other",
            instructions="unrelated",
            provenance="trusted:test",
            sha256="1" * 64,
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual(0, len(model.calls))
        self.assertEqual("error", outcome.opportunities[0].decision_status)
        self.assertEqual("ERROR_FALLBACK", wakes[0]["attention"]["source"])
        request_id = outcome.opportunities[0].request_id
        self.assertIn("profile-binding-mismatch", receipts.records(request_id)[1]["body"]["error"]["code"])

    def test_attention_and_dispatch_errors_do_not_persist_exception_content(self):
        secret = "room-context-and-credential-secret"
        model = FixtureModel(fail=True)
        pipeline, _, _, receipts = foundation(
            model=model,
            participant=lambda **_: {
                "kind": "message",
                "origin_event_id": "e1",
                "text": "safe output",
            },
        )
        model.judge = lambda **_: (_ for _ in ()).throw(RuntimeError(secret))
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        serialized = json.dumps(
            receipts.records(outcome.opportunities[0].request_id)
        )
        self.assertNotIn(secret, serialized)

        class FailingTransport:
            def dispatch(self, **_):
                raise RuntimeError(secret)

        second, _, _, second_receipts = foundation(
            transport=FailingTransport(),
            participant=lambda **_: {
                "kind": "message",
                "origin_event_id": "e2",
                "text": "safe output",
            },
        )
        second_outcome = second.handle_delivery(
            delivery_id="d2",
            event=message("e2"),
            actors={"human:zoe": {"kind": "human"}},
        )
        second_stream = second_receipts.records(
            second_outcome.opportunities[0].request_id
        )
        self.assertNotIn(secret, json.dumps(second_stream))
        self.assertEqual("unknown", second_outcome.opportunities[0].transport.delivery)

    def test_participant_silence_makes_no_transport_stage(self):
        pipeline, _, transport, receipts = foundation(participant=lambda **_: None)
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        stream = receipts.records(outcome.opportunities[0].request_id)
        self.assertEqual(["observation", "attention", "participant-host"], [
            record["stage"] for record in stream
        ])
        self.assertEqual("silent", stream[-1]["body"]["outcome"])
        self.assertEqual([], transport.calls)

    def test_cancellation_before_dispatch_prevents_stale_output(self):
        entered = threading.Event()
        release = threading.Event()

        def participant(**_):
            entered.set()
            release.wait(2)
            return {"kind": "message", "origin_event_id": "e1", "text": "late"}

        pipeline, _, transport, receipts = foundation(participant=participant)
        result = {}

        def run():
            result["outcome"] = pipeline.handle_delivery(
                delivery_id="d1",
                event=message("e1"),
                actors={"human:zoe": {"kind": "human"}},
            )

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(entered.wait(1))
        pipeline.cancel()
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], transport.calls)
        request_id = result["outcome"].opportunities[0].request_id
        self.assertEqual(["observation", "attention"], [
            record["stage"] for record in receipts.records(request_id)
        ])

    def test_host_deadline_invalidates_ignoring_participant_without_output(self):
        entered = threading.Event()
        release = threading.Event()

        def participant(**_):
            entered.set()
            release.wait(2)
            return {"kind": "message", "origin_event_id": "e1", "text": "late"}

        pipeline, _, transport, receipts = foundation(
            participant=participant,
            participant_timeout_seconds=0.05,
        )
        started = time.monotonic()
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        release.set()
        self.assertTrue(entered.is_set())
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(pipeline.scheduler.active)
        self.assertEqual([], transport.calls)
        self.assertEqual("failed", outcome.opportunities[0].transport.delivery)
        stream = receipts.records(outcome.opportunities[0].request_id)
        self.assertEqual("unknown", stream[-1]["body"]["outcome"])

    def test_async_live_ingress_is_active_plus_newest_not_fifo(self):
        entered = threading.Event()
        release = threading.Event()
        seen = []

        def participant(**kwargs):
            seen.append(kwargs["wake"]["trigger_event_id"])
            if len(seen) == 1:
                entered.set()
                release.wait(2)
            return None

        pipeline, _, _, _ = foundation(
            participant=participant,
            limits=ObservationLimits(snapshot_events=20),
        )
        lane = AsyncDeliveryLane(pipeline)
        lane.submit(
            delivery_id="d0",
            event=message("e0"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertTrue(entered.wait(1))
        for index in range(1, 8):
            outcome = lane.submit(
                delivery_id=f"d{index}",
                event=message(f"e{index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertTrue(outcome.coalesced)
        release.set()
        self.assertTrue(lane.drain(2))
        self.assertEqual(["e0", "e7"], seen)
        self.assertEqual(
            [f"e{index}" for index in range(8)],
            [event["id"] for event in pipeline.observation.retained_events()],
        )

    def test_twenty_events_during_slow_turn_create_one_fresh_opportunity(self):
        release = threading.Event()
        model = FixtureModel(block=release)
        seen_wakes = []
        pipeline, _, _, _ = foundation(
            model=model,
            participant=lambda **kwargs: seen_wakes.append(kwargs["wake"]) or None,
            limits=ObservationLimits(snapshot_events=24),
        )

        thread = threading.Thread(
            target=lambda: pipeline.handle_delivery(
                delivery_id="d0",
                event=message("e0"),
                actors={"human:zoe": {"kind": "human"}},
            )
        )
        thread.start()
        self.assertTrue(model.started.wait(1))
        for index in range(1, 21):
            outcome = pipeline.handle_delivery(
                delivery_id=f"d{index}",
                event=message(f"e{index}", text=f"intervening {index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertTrue(outcome.coalesced)
        self.assertEqual("e20", pipeline.scheduler.pending_anchor)
        release.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(2, len(model.calls))
        self.assertEqual(2, len(seen_wakes))
        self.assertEqual("e20", seen_wakes[-1]["trigger_event_id"])
        self.assertEqual([f"e{i}" for i in range(21)], [
            event["id"] for event in seen_wakes[-1]["events"]
        ])

    def test_profile_bytes_are_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            payload = {
                "profile_id": "vigil",
                "participant_id": "vigil",
                "actor_id": "discord:bot:9",
                "instructions": "security focus",
                "provenance": "operator:test",
            }
            raw = json.dumps(payload).encode()
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual("vigil", ParticipantProfile.load(path, expected_sha256=digest).profile_id)
            path.write_text(json.dumps({**payload, "instructions": "swapped"}))
            with self.assertRaises(ValidationError):
                ParticipantProfile.load(path, expected_sha256=digest)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pipeline, _, _, _ = foundation()
        self.pipeline.observation.observe(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.wake = self.pipeline.observation.build_snapshot("e1")
        self.wake.pop("schema_version")
        self.wake.pop("continuation", None)
        self.wake["attention"] = {"source": "WAKE"}
        self.rule = CapabilityRule(
            requester_actor_id="human:zoe",
            capability="workspace.file.write",
            platform="discord",
            room_id="42",
            participant_id="vigil",
            resource_kind="workspace-file",
            resource_id="repo:README.md",
            direct_allow=True,
            impact="low",
        )
        self.policy = StaticPolicySource(
            PolicySnapshot(
                "policy",
                "r1",
                (self.rule,),
                ("operator:zoe",),
            )
        )
        self.journal = AuthorizationJournal(Path(self.temp.name) / "authorization.jsonl")
        self.native_calls = []

    def coordinator(self, policy=None, result=None):
        def execute(operation, idempotency_key):
            self.native_calls.append((deepcopy(operation), idempotency_key))
            return result or TransportResult("sent", "native-effect:1")

        return AuthorizationCoordinator(
            observation=self.pipeline.observation,
            policy_source=policy or self.policy,
            journal=self.journal,
            executors={"workspace.file.write": execute},
        )

    def test_pipeline_cancel_discards_pending_approval(self):
        approval_rule = CapabilityRule(
            requester_actor_id="human:zoe",
            capability="workspace.file.write",
            platform="discord",
            room_id="42",
            participant_id="vigil",
            resource_kind="workspace-file",
            resource_id="repo:README.md",
            direct_allow=False,
            impact="high",
        )
        coordinator = self.coordinator(
            StaticPolicySource(
                PolicySnapshot(
                    "policy",
                    "approval",
                    (approval_rule,),
                    ("operator:zoe",),
                )
            )
        )
        self.pipeline.host.privileged = coordinator
        self.pipeline.host.participant = lambda **_: {
            "kind": "privileged",
            "origin_event_id": "e2",
            "capability": "workspace.file.write",
            "resource": {"kind": "workspace-file", "id": "repo:README.md"},
            "operation": {"path": "README.md", "content": "bounded"},
        }
        outcome = self.pipeline.handle_delivery(
            delivery_id="d2",
            event=message("e2"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual("unavailable", outcome.opportunities[0].transport.delivery)
        challenge = coordinator.pending_for_operator()[0]["challenge"][
            "approval_challenge_id"
        ]
        self.pipeline.cancel()
        result = coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge,
            authenticated_approver_id="operator:zoe",
        )
        self.assertEqual("failed", result.delivery)
        self.assertEqual([], self.native_calls)

    def test_corrupt_authorization_journal_and_executor_error_detail_fail_safe(self):
        corrupt = Path(self.temp.name) / "corrupt-authorization.jsonl"
        corrupt.write_text('{"kind":"invented"}\n')
        with self.assertRaises(AuthorizationError):
            AuthorizationJournal(corrupt)

        secret = "executor-secret-room-content"
        coordinator = self.coordinator(
            result=TransportResult("unknown", secret)
        )
        result = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("unknown", result.delivery)
        self.assertNotIn(secret, json.dumps(self.journal.records()))

    def proposal(self):
        return {
            "kind": "privileged",
            "origin_event_id": "e1",
            "capability": "workspace.file.write",
            "resource": {"kind": "workspace-file", "id": "repo:README.md"},
            "operation": {"path": "README.md", "content": "new"},
        }

    def test_direct_allow_rechecks_consumes_and_replay_dispatches_once(self):
        coordinator = self.coordinator()
        first = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        second = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("sent", first.delivery)
        self.assertEqual("failed", second.delivery)
        self.assertEqual(1, len(self.native_calls))
        self.assertEqual(1, len([
            record for record in self.journal.records() if record["kind"] == "effect_commit"
        ]))
        flow = [
            record["record"]
            for record in self.journal.records()
            if record["kind"] == "authorization_contract"
        ][:2]
        self.assertEqual([], validate_privileged_action_authorization_flow(flow))

    def test_policy_revocation_between_initial_check_and_commit_makes_zero_calls(self):
        allowed = PolicySnapshot("policy", "r1", (self.rule,), ("operator:zoe",))
        revoked_rule = CapabilityRule(**{**vars(self.rule), "revoked": True})
        revoked = PolicySnapshot("policy", "r1", (revoked_rule,), ("operator:zoe",))

        class ChangingPolicy:
            def __init__(self):
                self.calls = 0

            def load(inner):
                inner.calls += 1
                return allowed if inner.calls == 1 else revoked

        result = self.coordinator(policy=ChangingPolicy()).execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("failed", result.delivery)
        self.assertEqual([], self.native_calls)

    def test_high_impact_requires_authenticated_approval_and_wrong_actor_fails(self):
        high_rule = CapabilityRule(**{
            **vars(self.rule),
            "direct_allow": False,
            "impact": "high",
        })
        policy = StaticPolicySource(
            PolicySnapshot("policy", "r1", (high_rule,), ("operator:zoe",))
        )
        coordinator = self.coordinator(policy=policy)
        result = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("unavailable", result.delivery)
        pending = coordinator.pending_for_operator()
        self.assertEqual(1, len(pending))
        challenge_id = pending[0]["challenge"]["approval_challenge_id"]
        denied = coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge_id,
            authenticated_approver_id="operator:mallory",
        )
        self.assertEqual("failed", denied.delivery)
        self.assertEqual([], self.native_calls)

    def test_authenticated_approval_executes_exact_retained_operation(self):
        high_rule = CapabilityRule(**{
            **vars(self.rule),
            "direct_allow": False,
            "impact": "high",
        })
        policy = StaticPolicySource(
            PolicySnapshot("policy", "r1", (high_rule,), ("operator:zoe",))
        )
        coordinator = self.coordinator(policy=policy)
        coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        challenge_id = coordinator.pending_for_operator()[0]["challenge"]["approval_challenge_id"]
        approved = coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge_id,
            authenticated_approver_id="operator:zoe",
        )
        self.assertEqual("sent", approved.delivery)
        self.assertEqual(self.proposal()["operation"], self.native_calls[0][0])
        flow = [
            record["record"]
            for record in self.journal.records()
            if record["kind"] == "authorization_contract"
        ]
        self.assertEqual([], validate_privileged_action_authorization_flow(flow))

    def test_restart_discards_pending_approval(self):
        high_rule = CapabilityRule(**{
            **vars(self.rule),
            "direct_allow": False,
            "impact": "high",
        })
        policy = StaticPolicySource(
            PolicySnapshot("policy", "r1", (high_rule,), ("operator:zoe",))
        )
        coordinator = self.coordinator(policy=policy)
        coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        challenge_id = coordinator.pending_for_operator()[0]["challenge"]["approval_challenge_id"]
        coordinator.restart()
        result = coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge_id,
            authenticated_approver_id="operator:zoe",
        )
        self.assertEqual("failed", result.delivery)
        self.assertEqual([], self.native_calls)

    def test_nonidempotent_unknown_requires_fresh_duplicate_risk_approval(self):
        coordinator = self.coordinator(
            result=TransportResult("unknown", "acknowledgement lost")
        )
        first = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        second = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("unknown", first.delivery)
        self.assertEqual("unavailable", second.delivery)
        self.assertEqual(1, len(self.native_calls))
        pending = coordinator.pending_for_operator()
        self.assertEqual(1, len(pending))
        self.assertTrue(pending[0]["duplicate_effect_risk"])
        self.assertEqual(self.proposal()["operation"], pending[0]["operation"])
        self.assertEqual("e1", pending[0]["origin_observation"]["id"])
        retried = coordinator.complete_authenticated_approval(
            approval_challenge_id=pending[0]["challenge"]["approval_challenge_id"],
            authenticated_approver_id="operator:zoe",
        )
        self.assertEqual("unknown", retried.delivery)
        self.assertEqual(2, len(self.native_calls))
        retries = [
            record
            for record in self.journal.records()
            if record["kind"] == "effect_retry_commit"
        ]
        self.assertEqual(1, len(retries))
        self.assertTrue(retries[0]["duplicate_effect_risk"])

    def test_idempotent_unknown_reuses_same_key_and_confirmation_closes_replay(self):
        idempotent_rule = CapabilityRule(
            **{**vars(self.rule), "target_idempotency": True}
        )
        policy = StaticPolicySource(
            PolicySnapshot("policy", "idempotent", (idempotent_rule,), ("operator:zoe",))
        )
        results = [
            TransportResult("unknown", "lost"),
            TransportResult("sent", "confirmed"),
        ]

        def execute(operation, idempotency_key):
            self.native_calls.append((deepcopy(operation), idempotency_key))
            return results.pop(0)

        coordinator = AuthorizationCoordinator(
            observation=self.pipeline.observation,
            policy_source=policy,
            journal=self.journal,
            executors={"workspace.file.write": execute},
        )
        first = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        second = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        third = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual(("unknown", "sent", "failed"), (
            first.delivery,
            second.delivery,
            third.delivery,
        ))
        self.assertEqual(2, len(self.native_calls))
        self.assertIsNotNone(self.native_calls[0][1])
        self.assertEqual(self.native_calls[0][1], self.native_calls[1][1])
        self.assertFalse(
            self.journal.unknown(
                next(
                    record["effect_fingerprint"]
                    for record in self.journal.records()
                    if record["kind"] == "effect_commit"
                )
            )
        )

    def test_operation_digest_is_order_stable_and_rejects_nonfinite(self):
        self.assertEqual(
            canonical_operation_digest({"a": 1, "b": 2}),
            canonical_operation_digest({"b": 2, "a": 1}),
        )
        with self.assertRaises(ValidationError):
            canonical_operation_digest({"value": float("nan")})


class ReceiptTests(unittest.TestCase):
    def test_stage_owner_and_prefix_are_enforced(self):
        valid = [
            {
                "request_id": "r",
                "stage": "observation",
                "writer": "observation-provider",
                "body": {
                    "schema_version": 2,
                    "trigger_event_id": "e",
                    "continuity_scope_id": "scope",
                    "event_count": 1,
                    "byte_count": 10,
                    "coverage": {
                        "has_more_before": False,
                        "has_more_after": False,
                        "has_gaps": False,
                        "truncated_by": [],
                        "continuity": "session-only",
                        "has_restart_gap": False,
                    },
                    "included_event_ids": ["e"],
                },
            }
        ]
        self.assertEqual(valid, validate_receipt_stream(valid))
        forged = deepcopy(valid)
        forged[0]["writer"] = "transport"
        with self.assertRaises(ValidationError):
            validate_receipt_stream(forged)


if __name__ == "__main__":
    unittest.main()
