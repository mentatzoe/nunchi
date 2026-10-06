from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from nunchi.reactions import (
    ReactionCapability,
    UNAVAILABLE_REACTION_CAPABILITY,
)
from nunchi.attention import (
    AttentionEngine,
    AttentionPolicy,
    ParticipantProfile,
    participant_attention_prompt,
)
from nunchi.attention_questions import answers_leaning
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
from nunchi.adapters.matrix import MatrixTransport
from nunchi.integrations.discord_participant_transport import MCPDiscordTransport
from nunchi.observation import (
    ObservationLimits,
    ObservationProvider,
    ParticipantBinding,
    SnapshotUnavailable,
)
from nunchi.participant import (
    ConversationOpportunityScheduler,
    ParticipantError,
    ParticipantTurnHost,
    TransportResult,
)
from nunchi.pipeline import AsyncDeliveryLane, NunchiV2Pipeline
from nunchi.receipts import PersistenceError, ReceiptJournal
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

    def judge(self, *, instructions, projection, timeout_seconds):
        self.calls.append((instructions, deepcopy(projection)))
        self.started.set()
        if self.block is not None:
            self.block.wait(timeout_seconds * 2)
        if self.fail:
            raise RuntimeError("fixture provider failed")
        return answers_leaning(self.disposition)


class RecordingTransport:
    def __init__(self, result=None, *, capability=None):
        self.calls = []
        self.result = result or TransportResult("sent", "native:1")
        self.capability = capability or UNAVAILABLE_REACTION_CAPABILITY

    def dispatch(self, *, action, wake):
        self.calls.append((deepcopy(action), deepcopy(wake)))
        return self.result

    def reaction_capability(self):
        return self.capability


def foundation(
    *,
    model=None,
    participant=None,
    policy=None,
    persistence_path=None,
    limits=None,
    transport=None,
    participant_timeout_seconds=300,
    binding=None,
):
    binding = binding or ParticipantBinding(
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
    transport = transport or RecordingTransport()
    attention = AttentionEngine(
        profile=ParticipantProfile(
            profile_id="vigil-default",
            participant_id=binding.participant_id,
            actor_id=binding.actor_id,
            instructions="Contribute on security and implementation correctness.",
            provenance="trusted:test",
            sha256="0" * 64,
        ),
        model=model,
        policy=policy,
        receipts=receipts,
    )
    scheduler = ConversationOpportunityScheduler(
        f"{binding.participant_id}:{binding.continuity_scope_id}"
    )
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
    def test_attention_engine_owns_the_exact_model_prompt(self):
        pipeline, model, _, _ = foundation()
        pipeline.handle_delivery(
            delivery_id="d-prompt",
            event=message("e-prompt"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual(
            participant_attention_prompt(pipeline.attention.profile),
            model.calls[0][0],
        )

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

    def test_late_delivery_is_retained_in_canonical_event_time_order(self):
        reference = datetime.now(timezone.utc)
        newer_timestamp = reference.isoformat().replace("+00:00", "Z")
        older_timestamp = (reference - timedelta(hours=1)).isoformat().replace(
            "+00:00", "Z"
        )
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "observations.jsonl"
            first, _, _, _ = foundation(persistence_path=store)
            first.observation.observe(
                delivery_id="d-newer",
                event=message(
                    "e-newer",
                    timestamp=newer_timestamp,
                ),
                actors={"human:zoe": {"kind": "human"}},
            )
            first.observation.observe(
                delivery_id="d-older",
                event=message(
                    "e-older",
                    timestamp=older_timestamp,
                ),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertEqual(
                ["e-older", "e-newer"],
                [
                    event["id"]
                    for event in first.observation.retained_events()
                ],
            )
            self.assertEqual(
                ["e-older", "e-newer"],
                [
                    event["id"]
                    for event in first.observation.build_snapshot(
                        "e-newer"
                    )["events"]
                ],
            )

            restored, _, _, _ = foundation(persistence_path=store)
            self.assertEqual(
                ["e-older", "e-newer"],
                [
                    event["id"]
                    for event in restored.observation.retained_events()
                ],
            )

    def test_unparseable_timestamp_is_retained_as_unknown_by_omission(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "observations.jsonl"
            first, _, _, _ = foundation(persistence_path=store)

            first.observation.observe(
                delivery_id="d-invalid-time",
                event=message("e-invalid-time", timestamp="not-a-timestamp"),
                actors={"human:zoe": {"kind": "human"}},
            )

            retained = first.observation.retained_events()[0]
            self.assertNotIn("timestamp", retained)
            self.assertNotIn(
                "timestamp",
                first.observation.build_snapshot("e-invalid-time")["events"][0],
            )

            restored, _, _, _ = foundation(persistence_path=store)
            self.assertNotIn(
                "timestamp",
                restored.observation.retained_events()[0],
            )

    def test_mixed_aware_and_naive_timestamps_do_not_raise(self):
        reference = datetime.now(timezone.utc)
        pipeline, _, _, _ = foundation()
        pipeline.observation.observe(
            delivery_id="d-aware",
            event=message(
                "e-aware",
                timestamp=reference.isoformat().replace("+00:00", "Z"),
            ),
            actors={"human:zoe": {"kind": "human"}},
        )
        pipeline.observation.observe(
            delivery_id="d-naive",
            event=message(
                "e-naive",
                timestamp=(reference - timedelta(hours=1))
                .replace(tzinfo=None)
                .isoformat(),
            ),
            actors={"human:zoe": {"kind": "human"}},
        )

        retained = pipeline.observation.retained_events()
        self.assertEqual(["e-aware", "e-naive"], [event["id"] for event in retained])
        self.assertNotIn("timestamp", retained[1])
        snapshot = pipeline.observation.build_snapshot("e-naive")
        self.assertEqual(
            ["e-aware", "e-naive"],
            [event["id"] for event in snapshot["events"]],
        )

    def test_older_direct_mention_survives_newer_chatter(self):
        pipeline, model, _, _ = foundation()
        actors = {"human:zoe": {"display_name": "Zoe", "kind": "human"}}
        for index in range(1, 30):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(
                    f"e{index}",
                    text=f"message {index}",
                    mentioned_actor_ids=["discord:bot:9"] if index == 2 else [],
                ),
                actors=actors,
            )
        pipeline.handle_delivery(
            delivery_id="d30",
            event=message("e30", text="message 30"),
            actors=actors,
        )

        projection = model.calls[0][1]
        self.assertEqual(
            ["e2", *(f"e{index}" for index in range(8, 31))],
            [event["id"] for event in projection["events"]],
        )
        self.assertTrue(projection["coverage"]["has_more_before"])
        self.assertTrue(projection["coverage"]["has_gaps"])
        self.assertIn("events", projection["coverage"]["truncated_by"])

    def test_older_reply_to_own_message_survives_newer_chatter(self):
        pipeline, _, _, _ = foundation()
        pipeline.observation.observe(
            delivery_id="d-own",
            event=message("e-own", "discord:bot:9", "my earlier answer"),
            actors={"discord:bot:9": {"display_name": "Vigil", "kind": "bot"}},
        )
        actors = {"human:zoe": {"display_name": "Zoe", "kind": "human"}}
        pipeline.observation.observe(
            delivery_id="d-reply",
            event=message("e-reply", text="why that way?", reply_to_event_id="e-own"),
            actors=actors,
        )
        for index in range(28):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}", text=f"message {index}"),
                actors=actors,
            )

        snapshot = pipeline.observation.build_snapshot("e27")
        ids = [event["id"] for event in snapshot["events"]]
        self.assertEqual(
            ["e-own", "e-reply", *(f"e{index}" for index in range(6, 28))], ids
        )

    def test_older_mention_keeps_the_participants_answer(self):
        pipeline, _, _, _ = foundation()
        actors = {"human:zoe": {"display_name": "Zoe", "kind": "human"}}
        pipeline.observation.observe(
            delivery_id="d-ask",
            event=message("e-ask", text="Vigil, can you check X?",
                          mentioned_actor_ids=["discord:bot:9"]),
            actors=actors,
        )
        pipeline.observation.observe(
            delivery_id="d-answer",
            event=message("e-answer", "discord:bot:9", "X is fine."),
            actors={"discord:bot:9": {"display_name": "Vigil", "kind": "bot"}},
        )
        for index in range(30):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}", text=f"message {index}"),
                actors=actors,
            )

        ids = [
            event["id"]
            for event in pipeline.observation.build_snapshot("e29")["events"]
        ]
        self.assertEqual(
            ["e-ask", "e-answer", *(f"e{index}" for index in range(8, 30))], ids
        )

    def test_direct_exchange_never_displaces_recent_context(self):
        # Zoe mentions Vigil in every message while Castor answers between
        # them: the newest window is already the conversation, so nothing
        # older may push Castor's answers out.
        pipeline, _, _, _ = foundation()
        actors = {
            "human:zoe": {"display_name": "Zoe", "kind": "human"},
            "discord:bot:7": {"display_name": "Castor", "kind": "bot"},
        }
        events = []
        for index in range(40):
            if index % 2:
                event = message(f"e{index}", "discord:bot:7", f"answer {index}")
            else:
                event = message(f"e{index}", text=f"question {index}",
                                mentioned_actor_ids=["discord:bot:9"])
            events.append(event["id"])
            pipeline.observation.observe(
                delivery_id=f"d{index}", event=event, actors=actors
            )

        snapshot = pipeline.observation.build_snapshot("e39")
        self.assertEqual(events[-24:], [event["id"] for event in snapshot["events"]])
        self.assertFalse(snapshot["coverage"]["has_gaps"])

    def test_interior_gap_stays_fetchable(self):
        limits = ObservationLimits(snapshot_events=4)
        pipeline, _, _, _ = foundation(limits=limits)
        actors = {"human:zoe": {"kind": "human"}}
        pipeline.observation.observe(
            delivery_id="d-first",
            event=message("e-first", text="first",
                          mentioned_actor_ids=["discord:bot:9"]),
            actors=actors,
        )
        for index in range(6):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}", text=f"message {index}"),
                actors=actors,
            )

        request = pipeline.observation.build_snapshot("e5")
        self.assertEqual(
            ["e-first", "e3", "e4", "e5"],
            [event["id"] for event in request["events"]],
        )
        self.assertFalse(request["coverage"]["has_more_before"])
        self.assertTrue(request["coverage"]["has_gaps"])
        page = pipeline.observation.fetch_context(
            {
                "request_id": request["request_id"],
                "handle_id": request["continuation"]["handle_id"],
                "direction": "before",
                "max_events": 10,
                "max_bytes": 10_000,
            },
            host_context=request["continuation"]["bound_to"],
        )
        self.assertEqual(
            ["e0", "e1", "e2"], [event["id"] for event in page["events"]]
        )

    def test_direct_address_is_kept_newest_first_within_budgets(self):
        stale = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        mention = ["discord:bot:9"]
        events = (
            message(
                "e-stale",
                text="stale mention",
                mentioned_actor_ids=mention,
                timestamp=stale.replace("+00:00", "Z"),
            ),
            message("e-older", text="older mention", mentioned_actor_ids=mention),
            message("e-newer", text="newer mention", mentioned_actor_ids=mention),
            message("e-chat1", text="chatter one"),
            message("e-chat2", text="chatter two"),
            message("e-chat3", text="chatter six"),
        )

        def snapshot(limits):
            pipeline, _, _, receipts = foundation(limits=limits)
            for event in events:
                pipeline.observation.observe(
                    delivery_id=f"d-{event['id']}",
                    event=event,
                    actors={"human:zoe": {"kind": "human"}},
                )
            request = pipeline.observation.build_snapshot("e-chat3")
            return request, receipts.all_records()[-1]["body"]["byte_count"]

        by_events, byte_count = snapshot(ObservationLimits(snapshot_events=2))
        self.assertEqual(
            ["e-newer", "e-chat3"],
            [event["id"] for event in by_events["events"]],
        )
        self.assertEqual(["events"], by_events["coverage"]["truncated_by"])

        by_bytes, _ = snapshot(ObservationLimits(snapshot_bytes=byte_count))
        self.assertEqual(
            ["e-newer", "e-chat3"],
            [event["id"] for event in by_bytes["events"]],
        )
        self.assertIn("age", by_bytes["coverage"]["truncated_by"])
        self.assertIn("bytes", by_bytes["coverage"]["truncated_by"])

    def test_reaction_never_erases_known_actor_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "observations.jsonl"
            pipeline, _, _, _ = foundation(persistence_path=store)
            pipeline.observation.observe(
                delivery_id="d-said",
                event=message("e-said"),
                actors={"human:zoe": {"display_name": "Zoe", "kind": "human"}},
            )
            # A reaction delivery may know only the reactor's ID.
            pipeline.observation.observe(
                delivery_id="d-reacted",
                event={
                    "id": "e-reacted",
                    "type": "reaction",
                    "author_id": "human:zoe",
                    "target_event_id": "e-said",
                    "reaction": "✅",
                    "operation": "add",
                },
                actors={"human:zoe": {"kind": "unknown"}},
            )
            known = {"display_name": "Zoe", "kind": "human"}
            self.assertEqual(
                known,
                pipeline.observation.build_snapshot("e-reacted")["actors"]["human:zoe"],
            )

            restored, _, _, _ = foundation(persistence_path=store)
            self.assertEqual(
                known,
                restored.observation.build_snapshot("e-reacted")["actors"]["human:zoe"],
            )

            # A newly known name still replaces the old one.
            restored.observation.observe(
                delivery_id="d-renamed",
                event=message("e-renamed"),
                actors={"human:zoe": {"display_name": "Zoë", "kind": "human"}},
            )
            self.assertEqual(
                {"display_name": "Zoë", "kind": "human"},
                restored.observation.build_snapshot("e-renamed")["actors"]["human:zoe"],
            )


class AttentionAndHostTests(unittest.TestCase):
    def test_snapshot_reconstruction_uses_error_fallback_without_model_call(self):
        wakes = []
        pipeline, model, _, receipts = foundation(
            participant=lambda **kwargs: wakes.append(kwargs["wake"]) or None,
        )
        original = pipeline.observation.build_snapshot
        calls = 0

        def transient_snapshot(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise SnapshotUnavailable("transient snapshot fault")
            return original(*args, **kwargs)

        with mock.patch.object(
            pipeline.observation,
            "build_snapshot",
            side_effect=transient_snapshot,
        ):
            outcome = pipeline.handle_delivery(
                delivery_id="d-reconstruct",
                event=message("e-reconstruct"),
                actors={"human:zoe": {"kind": "human"}},
            )

        opportunity = outcome.opportunities[0]
        self.assertEqual("error", opportunity.decision_status)
        self.assertEqual("ERROR_FALLBACK", opportunity.effective_disposition)
        self.assertEqual([], model.calls)
        self.assertEqual("ERROR_FALLBACK", wakes[0]["attention"]["source"])
        stream = receipts.records(opportunity.request_id)
        self.assertEqual(
            "snapshot-reconstructed",
            stream[1]["body"]["error"]["code"],
        )

    def test_unrecoverable_snapshot_is_an_explicit_error_without_effect(self):
        pipeline, model, transport, receipts = foundation()
        with mock.patch.object(
            pipeline.observation,
            "build_snapshot",
            side_effect=SnapshotUnavailable("unrecoverable snapshot"),
        ) as build_snapshot:
            outcome = pipeline.handle_delivery(
                delivery_id="d-unrecoverable",
                event=message("e-unrecoverable"),
                actors={"human:zoe": {"kind": "human"}},
            )

        opportunity = outcome.opportunities[0]
        self.assertEqual(2, build_snapshot.call_count)
        self.assertIsNone(opportunity.request_id)
        self.assertIn(
            "after one reconstruction attempt",
            opportunity.operational_error,
        )
        self.assertEqual([], model.calls)
        self.assertEqual([], transport.calls)
        self.assertEqual((), receipts.all_records())

    def test_snapshot_persistence_error_is_not_retried_or_woken(self):
        pipeline, model, transport, _ = foundation()
        with mock.patch.object(
            pipeline.observation,
            "build_snapshot",
            side_effect=PersistenceError("receipt durability uncertain"),
        ) as build_snapshot:
            with self.assertRaisesRegex(
                PersistenceError,
                "durability uncertain",
            ):
                pipeline.handle_delivery(
                    delivery_id="d-persistence",
                    event=message("e-persistence"),
                    actors={"human:zoe": {"kind": "human"}},
                )

        self.assertEqual(1, build_snapshot.call_count)
        self.assertEqual([], model.calls)
        self.assertEqual([], transport.calls)

    def test_participant_request_cannot_cross_opportunity_token_binding(self):
        participant_calls = []
        pipeline, _, transport, _ = foundation(
            participant=lambda **kwargs: participant_calls.append(kwargs) or None,
        )
        for event_id in ("e-a", "e-b"):
            pipeline.observation.observe(
                delivery_id=f"d-{event_id}",
                event=message(event_id),
                actors={"human:zoe": {"kind": "human"}},
            )
        request_b = pipeline.observation.build_snapshot("e-b")
        decision_b = pipeline.attention.judge(request_b)
        token_a = pipeline.scheduler.offer("e-a")

        with self.assertRaisesRegex(
            ParticipantError,
            "does not match",
        ):
            pipeline.host.run(
                request=request_b,
                decision=decision_b,
                token=token_a,
            )

        self.assertEqual([], participant_calls)
        self.assertEqual([], transport.calls)

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
                        original(**kwargs)
                        return answers_leaning("SUPPRESS", close=True)

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

    def test_host_receipt_failure_blocks_transport_dispatch(self):
        pipeline, _, transport, receipts = foundation(
            participant=lambda **_: {
                "kind": "message",
                "origin_event_id": "e1",
                "text": "must not dispatch",
            }
        )
        original_append = receipts.append

        def append(record, *, writer):
            if record.get("stage") == "participant-host":
                raise PersistenceError("host receipt durability uncertain")
            return original_append(record, writer=writer)

        with mock.patch.object(receipts, "append", side_effect=append):
            with self.assertRaisesRegex(
                PersistenceError,
                "host receipt durability uncertain",
            ):
                pipeline.handle_delivery(
                    delivery_id="d1",
                    event=message("e1"),
                    actors={"human:zoe": {"kind": "human"}},
                )

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
        stream = receipts.records(request_id)
        self.assertEqual(
            ["observation", "attention", "participant-host"],
            [record["stage"] for record in stream],
        )
        self.assertTrue(stream[-1]["body"]["invoked"])
        self.assertEqual("unknown", stream[-1]["body"]["outcome"])

    def test_cancellation_during_action_validation_settles_host_without_output(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingAction(dict):
            def __iter__(self):
                entered.set()
                release.wait(2)
                return super().__iter__()

        def participant(**_):
            return BlockingAction(
                kind="message",
                origin_event_id="e1",
                text="late",
            )

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
        stream = receipts.records(request_id)
        self.assertEqual(
            ["observation", "attention", "participant-host"],
            [record["stage"] for record in stream],
        )
        self.assertTrue(stream[-1]["body"]["invoked"])
        self.assertEqual("unknown", stream[-1]["body"]["outcome"])

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
        clock = mock.Mock(wraps=time)
        clock.monotonic.return_value = 1000.0
        release = threading.Event()
        finished = threading.Event()
        workers = []

        class SlowTransport(RecordingTransport):
            def dispatch(self, *, action, wake):
                workers.append(threading.current_thread())
                self.calls.append((deepcopy(action), deepcopy(wake)))
                # Spend the unchanged budget only once native dispatch started.
                clock.monotonic.return_value = 1000.05
                release.wait(2)  # Cleanup watchdog, not a latency assertion.
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
        with (
            mock.patch("nunchi.pipeline.time", clock),
            mock.patch("nunchi.participant.time", clock),
            mock.patch("nunchi.attention.time", clock),
        ):
            try:
                outcome = pipeline.handle_delivery(
                    delivery_id="d1",
                    event=message("e1"),
                    actors={"human:zoe": {"kind": "human"}},
                )
                result = outcome.opportunities[0].transport
                self.assertIsNotNone(result)
                self.assertEqual("unknown", result.delivery)
                self.assertFalse(finished.is_set())
                self.assertEqual(1, len(transport.calls))
                self.assertFalse(pipeline.scheduler.active)
                stream = receipts.records(outcome.opportunities[0].request_id)
                self.assertEqual("unknown", stream[-1]["body"]["delivery"])
            finally:
                release.set()
                for worker in workers:
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
            self.assertEqual(stream, receipts.records(outcome.opportunities[0].request_id))
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
        clock = mock.Mock(wraps=time)
        clock.monotonic.return_value = 1000.0
        release = threading.Event()
        finished = threading.Event()
        workers = []
        phases = []
        participant_cancel = []

        class PhasedModel(FixtureModel):
            def judge(self, **kwargs):
                phases.append("attention")
                clock.monotonic.return_value = 1000.04
                return super().judge(**kwargs)

        class PhasedTransport(RecordingTransport):
            def dispatch(self, *, action, wake):
                workers.append(threading.current_thread())
                self.calls.append((deepcopy(action), deepcopy(wake)))
                phases.append("transport")
                # After the original .10 deadline, before a restarted .14 one.
                clock.monotonic.return_value = 1000.12
                release.wait(2)  # Cleanup watchdog, not a latency assertion.
                finished.set()
                return TransportResult("sent", "late-native")

        def participant(**kwargs):
            phases.append("participant")
            participant_cancel.append(kwargs["cancel"])
            clock.monotonic.return_value = 1000.08
            return {
                "kind": "message",
                "origin_event_id": "e1",
                "text": "hello",
            }

        transport = PhasedTransport()
        pipeline, _, _, receipts = foundation(
            model=PhasedModel(),
            participant=participant,
            policy=AttentionPolicy(timeout_seconds=0.1),
            participant_timeout_seconds=0.1,
            transport=transport,
        )
        with (
            mock.patch("nunchi.pipeline.time", clock),
            mock.patch("nunchi.participant.time", clock),
            mock.patch("nunchi.attention.time", clock),
        ):
            try:
                outcome = pipeline.handle_delivery(
                    delivery_id="d1",
                    event=message("e1"),
                    actors={"human:zoe": {"kind": "human"}},
                )
                result = outcome.opportunities[0].transport
                self.assertIsNotNone(result)
                self.assertEqual("unknown", result.delivery)
                self.assertEqual(["attention", "participant", "transport"], phases)
                self.assertEqual(1, len(transport.calls))
                self.assertTrue(participant_cancel[0].is_set())
                self.assertFalse(pipeline.scheduler.active)
                self.assertFalse(finished.is_set())
                stream = receipts.records(outcome.opportunities[0].request_id)
            finally:
                release.set()
                for worker in workers:
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
            self.assertEqual(stream, receipts.records(outcome.opportunities[0].request_id))

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
        # One fresh opportunity; the newest few it replaced are judged for
        # the memory alone, first (#94 step 6).
        self.assertEqual(
            ["e0", "e17", "e18", "e19", "e20"],
            [projection["trigger_event_id"] for _, projection in model.calls],
        )
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

    def test_host_deadline_during_policy_load_never_publishes_stale_approval(self):
        approval_rule = CapabilityRule(
            **{
                **vars(self.rule),
                "direct_allow": False,
                "impact": "high",
            }
        )
        load_started = threading.Event()
        release_load = threading.Event()
        proposal_done = threading.Event()
        self.addCleanup(release_load.set)

        class BlockingApprovalPolicy:
            def load(inner):
                # Hold the load open until the host deadline has passed, so the
                # deadline lands mid-load however slow the runner is.
                load_started.set()
                release_load.wait(10)
                return PolicySnapshot(
                    "policy",
                    "delayed-approval",
                    (approval_rule,),
                    ("operator:zoe",),
                )

        coordinator = self.coordinator(policy=BlockingApprovalPolicy())
        execute = coordinator.execute_proposal

        def tracked_execute(**kwargs):
            try:
                return execute(**kwargs)
            finally:
                proposal_done.set()

        coordinator.execute_proposal = tracked_execute
        self.pipeline.host.privileged = coordinator
        self.pipeline.host.host_timeout_seconds = 0.5
        self.pipeline.host.participant_timeout_seconds = 0.5
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

        self.assertIn(
            outcome.opportunities[0].transport.delivery,
            ("failed", "unknown"),
        )
        self.assertTrue(
            load_started.is_set(), "the policy load did not start before the deadline"
        )
        release_load.set()
        self.assertTrue(proposal_done.wait(5))
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
        records = journal.records()
        kinds = [record["kind"] for record in records]
        self.assertEqual(["authorization_contract", "authorization_contract"], kinds[:2])
        # Expiry may land before or after the effect commit depending on disk
        # speed (issue #37); both refuse the effect. A commit that was refused
        # is closed as not attempted, never left looking like a lost dispatch.
        if "effect_commit" in kinds:
            self.assertEqual(["effect_commit", "effect_result"], kinds[2:])
            self.assertEqual("FAILED", records[-1]["outcome"])
            self.assertTrue(
                records[-1]["detail"].startswith("privileged effect was not attempted")
            )
        else:
            self.assertEqual(2, len(kinds))

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


class CapturingParticipant:
    """A participant that records each turn's opportunity and returns one action."""

    def __init__(self, action=None):
        self.action = action
        self.opportunities = []
        self.wakes = []

    def run_protocol(self, *, wake, opportunity, expand, cancel):
        self.wakes.append(deepcopy(wake))
        self.opportunities.append(deepcopy(opportunity))
        return deepcopy(self.action)


class MhmTests(unittest.TestCase):
    """A mhm is the participant's own move (#94 step 7)."""

    @staticmethod
    def capability(reactions=("*",), revision="discord-reactions:v1"):
        return ReactionCapability(
            supported=True,
            authenticated=True,
            operations=("add", "remove"),
            reactions=reactions,
            permissions_revision=revision,
        )

    @staticmethod
    def own_mhm(event_id, reaction="👂"):
        return {
            "kind": "reaction",
            "origin_event_id": event_id,
            "target_event_id": event_id,
            "reaction": reaction,
            "operation": "add",
        }

    def test_a_mhm_judgment_gives_the_participant_its_turn(self):
        transport = RecordingTransport(capability=self.capability())
        participant = CapturingParticipant(self.own_mhm("e-mhm"))
        pipeline, _, _, receipts = foundation(
            model=FixtureModel("mhm"),
            participant=participant,
            transport=transport,
        )

        outcome = pipeline.handle_delivery(
            delivery_id="d-mhm",
            event=message("e-mhm"),
            actors={"human:zoe": {"kind": "human"}},
        )

        self.assertEqual("DEFER", outcome.opportunities[0].effective_disposition)
        self.assertEqual(1, len(participant.wakes))
        wake = participant.wakes[0]
        self.assertEqual("DEFER", wake["attention"]["source"])
        self.assertTrue(any("mhm" in item["note"] for item in wake["attention"]["advice"]))
        self.assertIn("reaction", participant.opportunities[0]["permissions"]["ordinary_actions"])
        self.assertEqual([self.own_mhm("e-mhm")], [action for action, _wake in transport.calls])
        attention = receipts.records(outcome.opportunities[0].request_id)[1]
        self.assertEqual("DEFER", attention["body"]["classifier_disposition"])
        self.assertEqual("classifier-defer", attention["body"]["routing_audit"]["valve"])
        self.assertNotIn("ack", attention["body"])
        host = receipts.records(outcome.opportunities[0].request_id)[2]
        self.assertEqual("DEFER", host["body"]["wake_source"])
        self.assertTrue(host["body"]["invoked"])

    def test_a_reaction_the_platform_does_not_permit_is_refused(self):
        transport = RecordingTransport(capability=self.capability(reactions=("👍",)))
        participant = CapturingParticipant(self.own_mhm("e-other-emoji"))
        pipeline, _, _, receipts = foundation(
            model=FixtureModel("mhm"),
            participant=participant,
            transport=transport,
        )

        outcome = pipeline.handle_delivery(
            delivery_id="d-other-emoji",
            event=message("e-other-emoji"),
            actors={"human:zoe": {"kind": "human"}},
        )

        # The participant may react, but only with what the platform attests.
        self.assertIn("reaction", participant.opportunities[0]["permissions"]["ordinary_actions"])
        self.assertEqual([], transport.calls)
        self.assertEqual("unavailable", outcome.opportunities[0].transport.delivery)

    def test_without_reaction_capability_the_participant_cannot_react(self):
        participant = CapturingParticipant(self.own_mhm("e-no-reactions"))
        pipeline, _, transport, _ = foundation(
            model=FixtureModel("mhm"),
            participant=participant,
        )

        outcome = pipeline.handle_delivery(
            delivery_id="d-no-reactions",
            event=message("e-no-reactions"),
            actors={"human:zoe": {"kind": "human"}},
        )

        self.assertEqual("DEFER", outcome.opportunities[0].effective_disposition)
        self.assertNotIn("reaction", participant.opportunities[0]["permissions"]["ordinary_actions"])
        self.assertEqual([], transport.calls)

    def test_measured_discord_permission_denial_removes_the_reaction_action(self):
        class Client:
            def __init__(self):
                self.calls = []

            def call_tool(self, name, arguments):
                self.calls.append((name, deepcopy(arguments)))
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "reaction_capability": {
                                        "channel_id": "42",
                                        "actor_id": "9",
                                        "capability": {
                                            "supported": False,
                                            "authenticated": True,
                                            "operations": [],
                                            "reactions": [],
                                            "permissions_revision": "discord-denied-v1",
                                            "detail": "add reactions denied",
                                        },
                                    }
                                }
                            ),
                        }
                    ],
                }

        client = Client()
        transport = MCPDiscordTransport(
            client,
            "42",
            "vigil",
            "discord:actor:9",
            b"y" * 32,
        )
        participant = CapturingParticipant()
        pipeline, _, _, receipts = foundation(
            model=FixtureModel("mhm"),
            participant=participant,
            transport=transport,
        )

        outcome = pipeline.handle_delivery(
            delivery_id="d-discord-permission-denied",
            event=message("e-discord-permission-denied"),
            actors={"human:zoe": {"kind": "human"}},
        )

        self.assertEqual("DEFER", outcome.opportunities[0].effective_disposition)
        # The participant still gets its turn, without a reaction action:
        # the platform measured that it may not react here.
        self.assertEqual(1, len(participant.opportunities))
        self.assertNotIn(
            "reaction",
            participant.opportunities[0]["permissions"]["ordinary_actions"],
        )
        self.assertTrue(client.calls)
        self.assertEqual(
            {"reaction_capability"},
            {name for name, _arguments in client.calls},
        )
        self.assertEqual(
            ["observation", "attention", "participant-host"],
            [record["stage"] for record in receipts.all_records()],
        )

    def test_measured_matrix_permission_denial_removes_the_reaction_action(self):
        binding = ParticipantBinding(
            participant_id="vigil",
            actor_id="matrix:actor:@vigil:example",
            platform="matrix",
            room_id="!room:example",
            continuity_scope_id="matrix:room:example",
        )
        with mock.patch.dict(os.environ, {"MATRIX_TOKEN": "secret"}, clear=False):
            transport = MatrixTransport(
                {
                    "homeserver": "https://matrix.invalid",
                    "access_token_env": "MATRIX_TOKEN",
                },
                room_id=binding.room_id,
                actor_id=binding.actor_id,
            )
        native_calls = []

        def request(method, path, payload=None):
            native_calls.append((method, path, deepcopy(payload)))
            if path.endswith("/account/whoami"):
                return {"user_id": "@vigil:example"}
            if path.endswith("/state/m.room.power_levels"):
                return {
                    "users": {"@vigil:example": 0},
                    "events": {"m.reaction": 50},
                }
            raise AssertionError(f"unexpected Matrix call: {method} {path}")

        transport._request = request
        participant = CapturingParticipant()
        pipeline, _, _, receipts = foundation(
            model=FixtureModel("mhm"),
            participant=participant,
            transport=transport,
            binding=binding,
        )

        outcome = pipeline.handle_delivery(
            delivery_id="d-matrix-permission-denied",
            event=message("e-matrix-permission-denied"),
            actors={"human:zoe": {"kind": "human"}},
        )

        self.assertEqual("DEFER", outcome.opportunities[0].effective_disposition)
        # The participant still gets its turn, without a reaction action:
        # the platform measured that it may not react here.
        self.assertEqual(1, len(participant.opportunities))
        self.assertNotIn(
            "reaction",
            participant.opportunities[0]["permissions"]["ordinary_actions"],
        )
        self.assertTrue(native_calls)
        self.assertEqual({"GET"}, {method for method, _path, _body in native_calls})
        self.assertEqual(
            ["observation", "attention", "participant-host"],
            [record["stage"] for record in receipts.all_records()],
        )


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

    def test_a_journal_with_records_of_nunchis_removed_nod_still_loads(self):
        # #94 step 7 removed Nunchi's own nod; journals it wrote must still
        # load at startup, or the surface would not start.
        observation = self.observation_record("r-nod")
        legacy = [
            observation,
            {
                "request_id": "r-nod",
                "stage": "attention",
                "writer": "attention-engine",
                "body": {
                    "classifier_disposition": "ACK",
                    "effective_disposition": "ACK",
                    "classifier": {"name": "fixture"},
                    "evidence_event_ids": ["e"],
                    "routing_audit": {"valve": "none", "override_cause": "none", "margin_status": "active"},
                    "policy_provenance": "trusted:attention-policy/default@1",
                    "ack": {
                        "reaction": "👂",
                        "policy_provenance": "trusted:ack-policy/default@1",
                        "permissions_revision": "rev:1",
                    },
                },
            },
            {
                "request_id": "r-nod",
                "stage": "participant-host",
                "writer": "participant-host",
                "body": {
                    "wake_source": "ACK",
                    "packet_event_count": 1,
                    "packet_byte_count": 10,
                    "delivered_event_ids": ["e"],
                    "expansion_calls": 0,
                    "invoked": False,
                    "outcome": "unknown",
                },
            },
            {
                "request_id": "r-nod",
                "stage": "transport",
                "writer": "transport",
                "body": {"delivery": "sent", "detail": "native:1"},
            },
        ]
        widened = [
            self.observation_record("r-widened"),
            {
                "request_id": "r-widened",
                "stage": "attention",
                "writer": "attention-engine",
                "body": {
                    "classifier_disposition": "ACK",
                    "effective_disposition": "DEFER",
                    "classifier": {"name": "fixture"},
                    "evidence_event_ids": ["e"],
                    "routing_audit": {
                        "valve": "policy-defer",
                        "override_cause": "ack-disabled",
                        "margin_status": "active",
                    },
                    "policy_provenance": "trusted:attention-policy/default@1",
                    "ack": {
                        "reaction": "👂",
                        "policy_provenance": "trusted:ack-policy/default@1",
                        "permissions_revision": "unavailable",
                    },
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in legacy + widened),
                encoding="utf-8",
            )
            journal = ReceiptJournal(path)
            self.assertEqual(4, len(journal.records("r-nod")))
            self.assertEqual(2, len(journal.records("r-widened")))

    @staticmethod
    def observation_record(request_id):
        return {
            "request_id": request_id,
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


if __name__ == "__main__":
    unittest.main()
