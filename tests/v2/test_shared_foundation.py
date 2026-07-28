from __future__ import annotations

import contextvars
import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from nunchi.adapters.runtime import ReferenceAdapterRuntime
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
        installation_id="default",
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
    def test_unknown_actor_mentions_remain_constructable_and_reach_attention(self):
        pipeline, model, _, _ = foundation()

        result = pipeline.handle_delivery(
            delivery_id="d-unknown-mentions",
            event=message("e-unknown-mentions", mentioned_actor_ids=None),
            actors={"human:zoe": {"display_name": "Zoe", "kind": "human"}},
        )

        self.assertTrue(result.observation.wake_eligible)
        self.assertEqual(1, len(model.calls))
        self.assertIsNone(model.calls[0][1]["events"][-1]["mentioned_actor_ids"])

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

    def test_exact_self_membership_cause_is_context_only(self):
        pipeline, model, _, _ = foundation()
        result = pipeline.handle_delivery(
            delivery_id="d-membership",
            event={
                "id": "e-membership",
                "type": "membership",
                "scope": {"kind": "room", "id": "42"},
                "subject_actor_id": "human:zoe",
                "caused_by_actor_id": "discord:bot:9",
                "change": "join",
            },
            actors={
                "human:zoe": {"display_name": "Zoe", "kind": "human"},
                "discord:bot:9": {"display_name": "Vigil", "kind": "bot"},
            },
        )
        self.assertEqual("exact-self-context", result.observation.audit.outcome)
        self.assertFalse(result.observation.wake_eligible)
        self.assertEqual([], model.calls)

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

    def test_contribution_delivery_is_attested_only_by_transport(self):
        pipeline, _, transport, receipts = foundation(
            participant=lambda **_: {
                "kind": "message",
                "origin_event_id": "e1",
                "text": "one direct contribution",
            }
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )

        stream = receipts.records(outcome.opportunities[0].request_id)
        self.assertEqual(
            ["observation", "attention", "participant-host", "transport"],
            [record["stage"] for record in stream],
        )
        self.assertEqual("unknown", stream[2]["body"]["outcome"])
        self.assertEqual("sent", stream[3]["body"]["delivery"])
        self.assertEqual(1, len(transport.calls))

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

    def test_host_total_deadline_bounds_native_transport_wait(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        class SlowTransport(RecordingTransport):
            def dispatch(self, *, action, wake):
                self.calls.append((deepcopy(action), deepcopy(wake)))
                entered.set()
                release.wait(2)
                finished.set()
                return TransportResult("sent", "late-native")

        transport = SlowTransport()
        pipeline, _, _, receipts = foundation(
            participant=lambda **_: {
                "kind": "message",
                "origin_event_id": "e1",
                "text": "hello",
            },
            policy=AttentionPolicy(preattention_enabled=False),
            participant_timeout_seconds=0.05,
            transport=transport,
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        result = outcome.opportunities[0].transport
        self.assertIsNotNone(result)
        self.assertEqual("unknown", result.delivery)
        self.assertTrue(entered.is_set())
        self.assertFalse(finished.is_set())
        self.assertFalse(pipeline.scheduler.active)
        stream = receipts.records(outcome.opportunities[0].request_id)
        self.assertEqual("unknown", stream[-1]["body"]["delivery"])
        release.set()
        self.assertTrue(finished.wait(1))
        self.assertFalse(pipeline.scheduler.active)

    def test_receipt_persistence_crossing_deadline_never_claims_sent_or_dispatches(self):
        class DelayedHostReceiptJournal(ReceiptJournal):
            def append(self, record, *, writer):
                if record.get("stage") == "participant-host":
                    time.sleep(0.07)
                return super().append(record, writer=writer)

        pipeline, _, transport, _ = foundation(
            participant=lambda **_: {
                "kind": "message",
                "origin_event_id": "e1",
                "text": "must not escape after the deadline",
            },
            policy=AttentionPolicy(preattention_enabled=False),
            participant_timeout_seconds=0.03,
        )
        receipts = DelayedHostReceiptJournal()
        pipeline.observation.receipts = receipts
        pipeline.attention.receipts = receipts
        pipeline.host.receipts = receipts

        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )

        self.assertEqual([], transport.calls)
        self.assertEqual("failed", outcome.opportunities[0].transport.delivery)
        stream = receipts.records(outcome.opportunities[0].request_id)
        self.assertEqual(
            ["observation", "attention", "participant-host", "transport"],
            [record["stage"] for record in stream],
        )
        self.assertEqual("unknown", stream[2]["body"]["outcome"])
        self.assertEqual("failed", stream[3]["body"]["delivery"])

    def test_host_total_deadline_spans_attention_participant_and_transport(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        class PhasedModel(FixtureModel):
            def judge(self, **kwargs):
                time.sleep(0.05)
                return super().judge(**kwargs)

        class PhasedTransport(RecordingTransport):
            def dispatch(self, *, action, wake):
                self.calls.append((deepcopy(action), deepcopy(wake)))
                entered.set()
                release.wait(2)
                finished.set()
                return TransportResult("sent", "late-native")

        def participant(**_):
            time.sleep(0.05)
            return {
                "kind": "message",
                "origin_event_id": "e1",
                "text": "hello",
            }

        pipeline, _, _, _ = foundation(
            model=PhasedModel(),
            participant=participant,
            policy=AttentionPolicy(timeout_seconds=0.5),
            participant_timeout_seconds=0.5,
            transport=PhasedTransport(),
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        result = outcome.opportunities[0].transport
        self.assertIsNotNone(result)
        self.assertNotEqual("sent", result.delivery)
        self.assertTrue(entered.is_set())
        self.assertFalse(finished.is_set())
        release.set()
        self.assertTrue(finished.wait(1))
        self.assertFalse(pipeline.scheduler.active)

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

    def test_restart_cannot_promote_pre_restart_ingress_into_new_generation(self):
        pipeline, _, _, _ = foundation()
        retained = threading.Event()
        release = threading.Event()
        original_observe = pipeline.observation.observe
        token_box = []

        def blocked_observe(**kwargs):
            result = original_observe(**kwargs)
            retained.set()
            release.wait(2)
            return result

        pipeline.observation.observe = blocked_observe
        ingress = threading.Thread(
            target=lambda: token_box.append(
                pipeline.observe_and_offer(
                    delivery_id="restart-race",
                    event=message("restart-race-event"),
                    actors={"human:zoe": {"kind": "human"}},
                )[1]
            )
        )
        ingress.start()
        self.assertTrue(retained.wait(1))

        restarted = threading.Event()
        restart = threading.Thread(
            target=lambda: (pipeline.restart(), restarted.set())
        )
        restart.start()
        self.assertFalse(restarted.wait(0.05))

        release.set()
        ingress.join(2)
        restart.join(2)
        self.assertFalse(ingress.is_alive())
        self.assertFalse(restart.is_alive())
        self.assertIsNotNone(token_box[0])
        self.assertFalse(pipeline.scheduler.is_current(token_box[0]))

    def test_async_delivery_lane_preserves_ingress_runtime_context(self):
        routed_profile = contextvars.ContextVar("routed_profile", default="missing")
        attention_seen = []
        participant_seen = []
        transport_seen = []
        model = FixtureModel()
        original_judge = model.judge

        def judge(**kwargs):
            attention_seen.append(routed_profile.get())
            return original_judge(**kwargs)

        model.judge = judge
        transport = RecordingTransport()
        original_dispatch = transport.dispatch

        def dispatch(**kwargs):
            transport_seen.append(routed_profile.get())
            return original_dispatch(**kwargs)

        transport.dispatch = dispatch
        pipeline, _, _, _ = foundation(
            model=model,
            participant=lambda **kwargs: participant_seen.append(
                routed_profile.get()
            )
            or {
                "kind": "message",
                "origin_event_id": kwargs["wake"]["trigger_event_id"],
                "text": "profile-bound output",
            },
            transport=transport,
        )
        lane = AsyncDeliveryLane(pipeline)
        marker = routed_profile.set("work")
        try:
            lane.submit(
                delivery_id="profile-context",
                event=message("profile-context-event"),
                actors={"human:zoe": {"kind": "human"}},
            )
        finally:
            routed_profile.reset(marker)

        self.assertTrue(lane.drain(2))
        self.assertEqual(["work"], attention_seen)
        self.assertEqual(["work"], participant_seen)
        self.assertEqual(["work"], transport_seen)

    def test_cancel_cannot_be_overtaken_by_pre_cancel_ingress(self):
        pipeline, _, _, _ = foundation()
        retained = threading.Event()
        release = threading.Event()
        original_observe = pipeline.observation.observe
        token_box = []

        def blocked_observe(**kwargs):
            result = original_observe(**kwargs)
            retained.set()
            release.wait(2)
            return result

        pipeline.observation.observe = blocked_observe
        ingress = threading.Thread(
            target=lambda: token_box.append(
                pipeline.observe_and_offer(
                    delivery_id="cancel-race",
                    event=message("cancel-race-event"),
                    actors={"human:zoe": {"kind": "human"}},
                )[1]
            )
        )
        ingress.start()
        self.assertTrue(retained.wait(1))

        cancelled = threading.Event()
        cancel = threading.Thread(
            target=lambda: (pipeline.cancel(), cancelled.set())
        )
        cancel.start()
        self.assertFalse(cancelled.wait(0.05))

        release.set()
        ingress.join(2)
        cancel.join(2)
        self.assertFalse(ingress.is_alive())
        self.assertFalse(cancel.is_alive())
        self.assertIsNotNone(token_box[0])
        self.assertFalse(pipeline.scheduler.is_current(token_box[0]))

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


class ReferenceAdapterIdentityTests(unittest.TestCase):
    def test_reference_adapter_plumbs_opaque_installation_id_into_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_data = {
                "profile_id": "vigil",
                "participant_id": "vigil",
                "actor_id": "discord:bot:9",
                "instructions": "Contribute carefully.",
                "provenance": "trusted:test",
            }
            raw = json.dumps(profile_data).encode()
            profile_path = root / "profile.json"
            profile_path.write_bytes(raw)
            config = {
                "schema_version": 2,
                "binding": {
                    "participant_id": "vigil",
                    "actor_id": "discord:bot:9",
                    "installation_id": "discord:installation:opaque-1",
                    "platform": "discord",
                    "room_id": "42",
                    "continuity_scope_id": "discord:42",
                },
                "profile": {
                    "path": str(profile_path),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
                "attention": {
                    "policy": {"preattention_enabled": False},
                    "model": {},
                },
                "participant_model": {
                    "model": "test-participant",
                    "api_key_env": "TEST_NUNCHI_PARTICIPANT_API_KEY",
                },
                "limits": {},
                "state_directory": str(root / "state"),
            }
            with mock.patch.dict(
                os.environ,
                {"TEST_NUNCHI_PARTICIPANT_API_KEY": "test-only"},
                clear=False,
            ):
                runtime = ReferenceAdapterRuntime(
                    surface="discord",
                    config=config,
                    transport=RecordingTransport(),
                )

            self.assertEqual(
                runtime.binding.installation_id,
                "discord:installation:opaque-1",
            )
            self.assertEqual(
                runtime.pipeline.observation.binding.installation_id,
                "discord:installation:opaque-1",
            )


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
            continuity_scope_id="discord:channel:42",
            installation_id="default",
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

    def test_bare_effect_commit_recovers_as_unknown_after_restart(self):
        path = Path(self.temp.name) / "bare-effect-commit.jsonl"
        fingerprint = "a" * 64
        journal = AuthorizationJournal(path)
        journal.append(
            {
                "kind": "effect_commit",
                "effect_fingerprint": fingerprint,
                "action_id": "action:1",
                "decision_id": "decision:1",
                "action_digest": {"sha256": "b" * 64},
                "idempotency_key": None,
                "committed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        recovered = AuthorizationJournal(path)

        self.assertTrue(recovered.consumed(fingerprint))
        self.assertTrue(recovered.unknown(fingerprint))

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
            continuity_scope_id="discord:channel:42",
            installation_id="default",
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

    def test_pipeline_cancel_invalidates_privileged_effect_while_policy_is_blocked(self):
        policy_started = threading.Event()
        release_policy = threading.Event()

        class BlockingPolicy:
            def __init__(inner):
                inner.calls = 0

            def load(inner):
                inner.calls += 1
                if inner.calls == 2:
                    policy_started.set()
                    release_policy.wait(2)
                return self.policy.load()

        coordinator = self.coordinator(policy=BlockingPolicy())
        self.pipeline.host.privileged = coordinator
        self.pipeline.host.participant = lambda **_: self.proposal()
        result_holder = {}
        worker = threading.Thread(
            target=lambda: result_holder.setdefault(
                "result",
                self.pipeline.handle_delivery(
                    delivery_id="d2",
                    event=message("e2"),
                    actors={"human:zoe": {"kind": "human"}},
                ),
            )
        )
        worker.start()
        self.assertTrue(policy_started.wait(1))
        cancel_done = threading.Event()
        cancel_worker = threading.Thread(
            target=lambda: (self.pipeline.cancel(), cancel_done.set())
        )
        cancel_worker.start()
        try:
            self.assertTrue(
                cancel_done.wait(0.25),
                "pipeline cancellation blocked behind privileged dispatch",
            )
        finally:
            release_policy.set()
            worker.join(2)
            cancel_worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertFalse(cancel_worker.is_alive())
        self.assertEqual([], self.native_calls)

    def test_host_deadline_during_policy_load_never_publishes_stale_approval(self):
        approval_rule = CapabilityRule(
            **{
                **vars(self.rule),
                "direct_allow": False,
                "impact": "high",
            }
        )
        policy_started = threading.Event()
        release_policy = threading.Event()

        class DelayedApprovalPolicy:
            def load(inner):
                policy_started.set()
                release_policy.wait()
                return PolicySnapshot(
                    "policy",
                    "delayed-approval",
                    (approval_rule,),
                    ("operator:zoe",),
                )

        coordinator = self.coordinator(policy=DelayedApprovalPolicy())
        self.pipeline.host.privileged = coordinator
        self.pipeline.host.host_timeout_seconds = 1.0
        self.pipeline.host.participant_timeout_seconds = 1.0
        self.pipeline.host.participant = lambda **_: {
            "kind": "privileged",
            "origin_event_id": "e2",
            "capability": "workspace.file.write",
            "resource": {"kind": "workspace-file", "id": "repo:README.md"},
            "operation": {"path": "README.md", "content": "bounded"},
        }

        outcome_holder = {}

        def run_delivery():
            outcome_holder["outcome"] = self.pipeline.handle_delivery(
                delivery_id="d2",
                event=message("e2"),
                actors={"human:zoe": {"kind": "human"}},
            )

        worker = threading.Thread(target=run_delivery)
        worker.start()
        self.assertTrue(policy_started.wait(2))
        wait_until = time.monotonic() + 2
        while self.pipeline.scheduler.active and time.monotonic() < wait_until:
            time.sleep(0.001)
        self.assertFalse(self.pipeline.scheduler.active)
        release_policy.set()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        outcome = outcome_holder["outcome"]

        self.assertIn(
            outcome.opportunities[0].transport.delivery,
            ("failed", "unknown", "unavailable"),
        )
        self.assertEqual((), coordinator.pending_for_operator())
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

    def test_same_scope_with_matching_continuity_and_installation_is_allowed(self):
        """Legitimate same-scope flow: rule bound to exact continuity and
        installation identity must still match when the binding carries the same values."""
        bound_rule = CapabilityRule(
            requester_actor_id="human:zoe",
            capability="workspace.file.write",
            platform="discord",
            room_id="42",
            participant_id="vigil",
            resource_kind="workspace-file",
            resource_id="repo:README.md",
            continuity_scope_id="discord:channel:42",
            installation_id="default",
            direct_allow=True,
            impact="low",
        )
        policy = StaticPolicySource(
            PolicySnapshot("policy", "r1", (bound_rule,), ("operator:zoe",))
        )
        coordinator = self.coordinator(policy=policy)
        # Patch the binding to include installation_id
        self.pipeline.observation.binding = ParticipantBinding(
            participant_id="vigil",
            actor_id="discord:bot:9",
            platform="discord",
            room_id="42",
            continuity_scope_id="discord:channel:42",
            names=("Vigil", "Codex"),
            installation_id="default",
        )
        result = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("sent", result.delivery)
        self.assertEqual(1, len(self.native_calls))

    def test_cross_installation_binding_is_denied(self):
        """Cross-installation denial: a rule bound to installation_id='default'
        must not match a binding whose installation_id is 'other'."""
        bound_rule = CapabilityRule(
            requester_actor_id="human:zoe",
            capability="workspace.file.write",
            platform="discord",
            room_id="42",
            participant_id="vigil",
            resource_kind="workspace-file",
            resource_id="repo:README.md",
            continuity_scope_id="discord:channel:42",
            installation_id="default",
            direct_allow=True,
            impact="low",
        )
        policy = StaticPolicySource(
            PolicySnapshot("policy", "r1", (bound_rule,), ("operator:zoe",))
        )
        coordinator = self.coordinator(policy=policy)
        # Same continuity, different installation
        self.pipeline.observation.binding = ParticipantBinding(
            participant_id="vigil",
            actor_id="discord:bot:9",
            platform="discord",
            room_id="42",
            continuity_scope_id="discord:channel:42",
            names=("Vigil", "Codex"),
            installation_id="other",
        )
        result = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("failed", result.delivery)
        self.assertEqual(0, len(self.native_calls))

    def test_changed_continuity_scope_is_denied(self):
        """Changed-continuity denial: a rule bound to continuity_scope_id
        'discord:channel:42' must not match a binding with a different
        continuity_scope_id even if all other fields are identical."""
        bound_rule = CapabilityRule(
            requester_actor_id="human:zoe",
            capability="workspace.file.write",
            platform="discord",
            room_id="42",
            participant_id="vigil",
            resource_kind="workspace-file",
            resource_id="repo:README.md",
            continuity_scope_id="discord:channel:42",
            installation_id="default",
            direct_allow=True,
            impact="low",
        )
        policy = StaticPolicySource(
            PolicySnapshot("policy", "r1", (bound_rule,), ("operator:zoe",))
        )
        coordinator = self.coordinator(policy=policy)
        # Same installation, different continuity (e.g. channel recreated)
        self.pipeline.observation.binding = ParticipantBinding(
            participant_id="vigil",
            actor_id="discord:bot:9",
            platform="discord",
            room_id="42",
            continuity_scope_id="discord:channel:43",
            names=("Vigil", "Codex"),
            installation_id="default",
        )
        # Wake must match the binding or _build_binding raises earlier
        self.wake["room"]["continuity_scope_id"] = "discord:channel:43"
        result = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("failed", result.delivery)
        self.assertEqual(0, len(self.native_calls))

    def test_cancel_fences_native_effect_between_final_check_and_dispatch(self):
        coordinator = self.coordinator()
        entered_dispatch_boundary = threading.Event()
        release_dispatch_boundary = threading.Event()

        class BlockingExecutors(dict):
            def __getitem__(inner, key):
                entered_dispatch_boundary.set()
                release_dispatch_boundary.wait(2)
                return super().__getitem__(key)

        coordinator.executors = BlockingExecutors(coordinator.executors)
        result_holder = {}
        worker = threading.Thread(
            target=lambda: result_holder.setdefault(
                "result",
                coordinator.execute_proposal(
                    proposal=self.proposal(),
                    wake=self.wake,
                    cancel=threading.Event(),
                ),
            )
        )
        worker.start()
        self.assertTrue(entered_dispatch_boundary.wait(1))

        cancel_returned = threading.Event()
        cancel_worker = threading.Thread(
            target=lambda: (coordinator.cancel(), cancel_returned.set())
        )
        cancel_worker.start()
        try:
            self.assertFalse(
                cancel_returned.wait(0.1),
                "cancellation returned while native dispatch could still begin",
            )
        finally:
            release_dispatch_boundary.set()
            worker.join(2)
            cancel_worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertFalse(cancel_worker.is_alive())
        self.assertTrue(cancel_returned.is_set())
        self.assertEqual("failed", result_holder["result"].delivery)
        self.assertEqual([], self.native_calls)

    def test_cancel_fences_native_effect_for_authenticated_approval_dispatch(self):
        high_rule = CapabilityRule(
            **{
                **vars(self.rule),
                "direct_allow": False,
                "impact": "high",
            }
        )
        snapshot = PolicySnapshot(
            "policy",
            "r1",
            (high_rule,),
            ("operator:zoe",),
        )
        coordinator = self.coordinator(policy=StaticPolicySource(snapshot))
        initial = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("unavailable", initial.delivery)
        challenge_id = coordinator.pending_for_operator()[0]["challenge"][
            "approval_challenge_id"
        ]

        entered_dispatch_boundary = threading.Event()
        release_dispatch_boundary = threading.Event()

        class BlockingExecutors(dict):
            def __getitem__(inner, key):
                entered_dispatch_boundary.set()
                release_dispatch_boundary.wait(2)
                return super().__getitem__(key)

        coordinator.executors = BlockingExecutors(coordinator.executors)
        result_holder = {}
        worker = threading.Thread(
            target=lambda: result_holder.setdefault(
                "result",
                coordinator.complete_authenticated_approval(
                    approval_challenge_id=challenge_id,
                    authenticated_approver_id="operator:zoe",
                ),
            )
        )
        worker.start()
        self.assertTrue(entered_dispatch_boundary.wait(1))

        cancel_returned = threading.Event()
        cancel_worker = threading.Thread(
            target=lambda: (coordinator.cancel(), cancel_returned.set())
        )
        cancel_worker.start()
        try:
            self.assertFalse(
                cancel_returned.wait(0.1),
                "cancellation returned while approved native dispatch could still begin",
            )
        finally:
            release_dispatch_boundary.set()
            worker.join(2)
            cancel_worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertFalse(cancel_worker.is_alive())
        self.assertTrue(cancel_returned.is_set())
        self.assertEqual("failed", result_holder["result"].delivery)
        self.assertEqual([], self.native_calls)

    def test_cancel_invalidates_direct_effect_while_policy_recheck_is_blocked(self):
        policy_started = threading.Event()
        release_policy = threading.Event()

        class BlockingPolicy:
            def __init__(inner):
                inner.calls = 0

            def load(inner):
                inner.calls += 1
                if inner.calls == 2:
                    policy_started.set()
                    release_policy.wait(2)
                return self.policy.load()

        coordinator = self.coordinator(policy=BlockingPolicy())
        result_holder = {}
        worker = threading.Thread(
            target=lambda: result_holder.setdefault(
                "result",
                coordinator.execute_proposal(
                    proposal=self.proposal(),
                    wake=self.wake,
                    cancel=threading.Event(),
                ),
            )
        )
        worker.start()
        self.assertTrue(policy_started.wait(1))
        cancel_done = threading.Event()
        cancel_worker = threading.Thread(
            target=lambda: (coordinator.cancel(), cancel_done.set())
        )
        cancel_worker.start()
        try:
            self.assertTrue(
                cancel_done.wait(0.25),
                "lifecycle invalidation blocked behind authorization work",
            )
        finally:
            release_policy.set()
            worker.join(2)
            cancel_worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertFalse(cancel_worker.is_alive())
        self.assertEqual("failed", result_holder["result"].delivery)
        self.assertEqual([], self.native_calls)

    def test_cancel_invalidates_authenticated_approval_during_policy_recheck(self):
        high_rule = CapabilityRule(
            **{
                **vars(self.rule),
                "direct_allow": False,
                "impact": "high",
            }
        )
        snapshot = PolicySnapshot(
            "policy",
            "r1",
            (high_rule,),
            ("operator:zoe",),
        )
        policy_started = threading.Event()
        release_policy = threading.Event()

        class BlockingApprovalPolicy:
            def __init__(inner):
                inner.calls = 0

            def load(inner):
                inner.calls += 1
                if inner.calls == 2:
                    policy_started.set()
                    release_policy.wait(2)
                return deepcopy(snapshot)

        coordinator = self.coordinator(policy=BlockingApprovalPolicy())
        initial = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("unavailable", initial.delivery)
        challenge_id = coordinator.pending_for_operator()[0]["challenge"][
            "approval_challenge_id"
        ]
        result_holder = {}
        worker = threading.Thread(
            target=lambda: result_holder.setdefault(
                "result",
                coordinator.complete_authenticated_approval(
                    approval_challenge_id=challenge_id,
                    authenticated_approver_id="operator:zoe",
                ),
            )
        )
        worker.start()
        self.assertTrue(policy_started.wait(1))
        coordinator.cancel()
        release_policy.set()
        worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertEqual("failed", result_holder["result"].delivery)
        self.assertEqual([], self.native_calls)

    def test_cancel_invalidates_unknown_retry_during_policy_recheck(self):
        snapshot = self.policy.load()
        policy_started = threading.Event()
        release_policy = threading.Event()

        class BlockingRetryPolicy:
            def __init__(inner):
                inner.calls = 0

            def load(inner):
                inner.calls += 1
                if inner.calls == 4:
                    policy_started.set()
                    release_policy.wait(2)
                return deepcopy(snapshot)

        coordinator = self.coordinator(
            policy=BlockingRetryPolicy(),
            result=TransportResult("unknown", "native outcome ambiguous"),
        )
        first = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        self.assertEqual("unknown", first.delivery)
        result_holder = {}
        worker = threading.Thread(
            target=lambda: result_holder.setdefault(
                "result",
                coordinator.execute_proposal(
                    proposal=self.proposal(),
                    wake=self.wake,
                    cancel=threading.Event(),
                ),
            )
        )
        worker.start()
        self.assertTrue(policy_started.wait(1))
        coordinator.cancel()
        release_policy.set()
        worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertEqual("failed", result_holder["result"].delivery)
        self.assertEqual(1, len(self.native_calls))

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

    def test_effect_commit_delay_cannot_outlive_rule_expiry(self):
        class DelayedEffectCommitJournal(AuthorizationJournal):
            def append(inner, record):
                if record.get("kind") == "effect_commit":
                    time.sleep(0.2)
                return super().append(record)

        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=0.12)
        ).isoformat().replace("+00:00", "Z")
        expiring_rule = CapabilityRule(
            **{
                **vars(self.rule),
                "expires_at": expires_at,
            }
        )
        policy = StaticPolicySource(
            PolicySnapshot(
                "policy",
                "expiring",
                (expiring_rule,),
                ("operator:zoe",),
            )
        )
        journal = DelayedEffectCommitJournal(
            Path(self.temp.name) / "delayed-effect-commit.jsonl"
        )

        def execute(operation, idempotency_key):
            self.native_calls.append((deepcopy(operation), idempotency_key))
            return TransportResult("sent", "must-not-run")

        coordinator = AuthorizationCoordinator(
            observation=self.pipeline.observation,
            policy_source=policy,
            journal=journal,
            executors={"workspace.file.write": execute},
        )
        result = coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )

        self.assertEqual("failed", result.delivery)
        self.assertEqual([], self.native_calls)
        self.assertEqual(
            ["authorization_contract", "authorization_contract", "effect_commit"],
            [record["kind"] for record in journal.records()],
        )

    def test_revocation_during_effect_commit_makes_zero_calls(self):
        allowed = PolicySnapshot("policy", "r1", (self.rule,), ("operator:zoe",))
        revoked_rule = CapabilityRule(**{**vars(self.rule), "revoked": True})
        revoked = PolicySnapshot(
            "policy",
            "r1",
            (revoked_rule,),
            ("operator:zoe",),
        )
        policy = StaticPolicySource(allowed)

        class RevokingEffectCommitJournal(AuthorizationJournal):
            def append(inner, record):
                result = super().append(record)
                if record.get("kind") == "effect_commit":
                    policy.replace(revoked)
                return result

        journal = RevokingEffectCommitJournal(
            Path(self.temp.name) / "revoking-effect-commit.jsonl"
        )

        def execute(operation, idempotency_key):
            self.native_calls.append((deepcopy(operation), idempotency_key))
            return TransportResult("sent", "must-not-run")

        coordinator = AuthorizationCoordinator(
            observation=self.pipeline.observation,
            policy_source=policy,
            journal=journal,
            executors={"workspace.file.write": execute},
        )
        result = coordinator.execute_proposal(
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

    def test_revocation_during_approved_effect_commit_makes_zero_calls(self):
        approval_rule = CapabilityRule(
            **{
                **vars(self.rule),
                "direct_allow": False,
                "impact": "high",
            }
        )
        revoked_rule = CapabilityRule(
            **{
                **vars(approval_rule),
                "revoked": True,
            }
        )
        policy = StaticPolicySource(
            PolicySnapshot(
                "policy",
                "approval-revocation",
                (approval_rule,),
                ("operator:zoe",),
            )
        )

        class RevokingApprovedCommitJournal(AuthorizationJournal):
            def append(inner, record):
                result = super().append(record)
                if record.get("kind") == "effect_commit":
                    policy.replace(
                        PolicySnapshot(
                            "policy",
                            "approval-revocation",
                            (revoked_rule,),
                            ("operator:zoe",),
                        )
                    )
                return result

        journal = RevokingApprovedCommitJournal(
            Path(self.temp.name) / "approved-revocation.jsonl"
        )

        def execute(operation, idempotency_key):
            self.native_calls.append((deepcopy(operation), idempotency_key))
            return TransportResult("sent", "must-not-run")

        coordinator = AuthorizationCoordinator(
            observation=self.pipeline.observation,
            policy_source=policy,
            journal=journal,
            executors={"workspace.file.write": execute},
        )
        coordinator.execute_proposal(
            proposal=self.proposal(),
            wake=self.wake,
            cancel=threading.Event(),
        )
        challenge_id = coordinator.pending_for_operator()[0]["challenge"][
            "approval_challenge_id"
        ]
        result = coordinator.complete_authenticated_approval(
            approval_challenge_id=challenge_id,
            authenticated_approver_id="operator:zoe",
        )

        self.assertEqual("failed", result.delivery)
        self.assertEqual([], self.native_calls)

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

    def test_revocation_during_unknown_retry_commit_makes_no_second_call(self):
        idempotent_rule = CapabilityRule(
            **{
                **vars(self.rule),
                "target_idempotency": True,
            }
        )
        revoked_rule = CapabilityRule(
            **{
                **vars(idempotent_rule),
                "revoked": True,
            }
        )
        policy = StaticPolicySource(
            PolicySnapshot(
                "policy",
                "retry-revocation",
                (idempotent_rule,),
                ("operator:zoe",),
            )
        )

        class RevokingRetryCommitJournal(AuthorizationJournal):
            def append(inner, record):
                result = super().append(record)
                if record.get("kind") == "effect_retry_commit":
                    policy.replace(
                        PolicySnapshot(
                            "policy",
                            "retry-revocation",
                            (revoked_rule,),
                            ("operator:zoe",),
                        )
                    )
                return result

        journal = RevokingRetryCommitJournal(
            Path(self.temp.name) / "retry-revocation.jsonl"
        )

        def execute(operation, idempotency_key):
            self.native_calls.append((deepcopy(operation), idempotency_key))
            return TransportResult("unknown", "acknowledgement lost")

        coordinator = AuthorizationCoordinator(
            observation=self.pipeline.observation,
            policy_source=policy,
            journal=journal,
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

        self.assertEqual("unknown", first.delivery)
        self.assertEqual("failed", second.delivery)
        self.assertEqual(1, len(self.native_calls))

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
