from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from nunchi import cli
from nunchi.adapters.discord import DiscordPyTransport, _declare_fresh_gateway_gap
from nunchi.adapters.telegram import TelegramTransport, _poll_updates
from nunchi.errors import ValidationError
from nunchi.install import initialize, verify
from nunchi.mcp_discord.authorization import (
    ToolAuthorizer,
    make_tool_authorization,
)
from nunchi.mcp_discord.config import load_config
from nunchi.mcp_discord.gateway import GatewayProtocol
from nunchi.mcp_discord.runner import GatewayRunner
from nunchi.mcp_discord.server import (
    AuthenticatedSessionRegistry,
    GapAwareEnqueuer,
    TransportAuditJournal,
    deliver_targeted,
    pump_notifications,
)
from nunchi.observation import (
    ObservationLimits,
    ObservationProvider,
    ParticipantBinding,
    SnapshotUnavailable,
)
from nunchi.receipts import PersistenceError
from nunchi.v2_contracts import validate_attention_request
from tests.v2.test_shared_foundation import foundation, message


class BoundedPersistenceTests(unittest.TestCase):
    def test_retained_file_and_restart_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            limits = ObservationLimits(
                retention_events=3,
                retention_bytes=100_000,
                snapshot_events=3,
                snapshot_bytes=100_000,
            )
            pipeline, _, _, _ = foundation(
                persistence_path=path,
                limits=limits,
            )
            for index in range(10):
                pipeline.observation.observe(
                    delivery_id=f"d{index}",
                    event=message(f"e{index}"),
                    actors={"human:zoe": {"kind": "human"}},
                )
            self.assertEqual(3, len(path.read_text().splitlines()))
            restored, _, _, _ = foundation(
                persistence_path=path,
                limits=limits,
            )
            self.assertEqual(
                ["e7", "e8", "e9"],
                [event["id"] for event in restored.observation.retained_events()],
            )
            snapshot = restored.observation.build_snapshot("e9")
            self.assertTrue(snapshot["coverage"]["has_more_before"])
            self.assertIn("events", snapshot["coverage"]["truncated_by"])
            self.assertNotIn(
                "continuation",
                snapshot,
                "evicted context must not fabricate fetch authority",
            )
            self.assertFalse(restored.scheduler.active)

    def test_actor_metadata_counts_toward_snapshot_and_continuation_bytes(self):
        pipeline, _, _, receipts = foundation(
            limits=ObservationLimits(
                retention_events=10,
                retention_bytes=1_000_000,
                snapshot_events=1,
                snapshot_bytes=512,
                continuation_events=1,
                continuation_bytes=512,
            )
        )
        pipeline.observation.observe(
            delivery_id="d-large",
            event=message("e-large", author_id="human:large"),
            actors={
                "human:large": {
                    "display_name": "x" * 100_000,
                    "kind": "human",
                }
            },
        )
        pipeline.observation.observe(
            delivery_id="d-small",
            event=message("e-small"),
            actors={"human:zoe": {"display_name": "Zoe", "kind": "human"}},
        )
        request = pipeline.observation.build_snapshot("e-small")
        expected_bytes = len(
            json.dumps(
                {"actors": request["actors"], "events": request["events"]},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        )
        self.assertLessEqual(expected_bytes, 512)
        self.assertEqual(
            expected_bytes,
            receipts.records(request["request_id"])[0]["body"]["byte_count"],
        )
        continuation = request["continuation"]
        page = pipeline.observation.fetch_context(
            {
                "request_id": request["request_id"],
                "handle_id": continuation["handle_id"],
                "direction": "before",
                "max_events": 1,
                "max_bytes": 512,
            },
            host_context=continuation["bound_to"],
        )
        self.assertEqual([], page["events"])
        self.assertEqual({}, page["actors"])
        self.assertIn("bytes", page["coverage"]["truncated_by"])
        with self.assertRaises(SnapshotUnavailable):
            pipeline.observation.build_snapshot("e-large")
        dishonest = deepcopy(request)
        dishonest["actors"]["human:zoe"]["display_name"] = "x" * 100_000
        with self.assertRaises(ValidationError):
            validate_attention_request(dishonest)

    def test_retention_bytes_include_persisted_actor_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            pipeline, _, _, _ = foundation(
                persistence_path=path,
                limits=ObservationLimits(
                    retention_events=10,
                    retention_bytes=512,
                    snapshot_events=1,
                    snapshot_bytes=512,
                ),
            )
            pipeline.observation.observe(
                delivery_id="d-large",
                event=message("e-large", author_id="human:large"),
                actors={
                    "human:large": {
                        "display_name": "x" * 100_000,
                        "kind": "human",
                    }
                },
            )
            self.assertLessEqual(path.stat().st_size, 512)
            self.assertEqual((), pipeline.observation.retained_events())

    def test_evicted_event_replay_remains_no_wake_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            limits = ObservationLimits(
                retention_events=2,
                retention_bytes=100_000,
                snapshot_events=2,
                snapshot_bytes=100_000,
            )
            first, first_model, _, _ = foundation(
                persistence_path=path,
                limits=limits,
            )
            for index in range(5):
                first.handle_delivery(
                    delivery_id=f"d{index}",
                    event=message(f"e{index}"),
                    actors={"human:zoe": {"kind": "human"}},
                )
            self.assertEqual(5, len(first_model.calls))
            in_process = first.handle_delivery(
                delivery_id="d0",
                event=message("e0"),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertEqual("exact-duplicate", in_process.observation.audit.outcome)
            self.assertEqual(5, len(first_model.calls))

            restored, restored_model, _, _ = foundation(
                persistence_path=path,
                limits=limits,
            )
            replay = restored.handle_delivery(
                delivery_id="d0",
                event=message("e0"),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertEqual("exact-duplicate", replay.observation.audit.outcome)
            self.assertEqual([], restored_model.calls)

    def test_corrupt_delivery_audit_fails_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            first, _, _, _ = foundation(persistence_path=path)
            first.observation.observe(
                delivery_id="d1",
                event=message("e1"),
                actors={"human:zoe": {"kind": "human"}},
            )
            audit = path.with_name(path.name + ".delivery-audit.jsonl")
            audit.write_text('{"kind":"invented"}\n')
            with self.assertRaises(PersistenceError):
                foundation(persistence_path=path)

    def test_corrupt_replay_reservation_fails_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            replay = path.with_name(path.name + ".replay-reservations.jsonl")
            replay.write_text('{"event_id":"e1"}\n')
            with self.assertRaises(PersistenceError):
                foundation(persistence_path=path)

    def test_atomic_persistence_failure_rolls_back_and_does_not_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            pipeline, model, _, _ = foundation(persistence_path=path)
            with mock.patch(
                "nunchi.observation.os.replace",
                side_effect=OSError("simulated replacement failure"),
            ):
                with self.assertRaises(PersistenceError):
                    pipeline.handle_delivery(
                        delivery_id="d1",
                        event=message("e1"),
                        actors={"human:zoe": {"kind": "human"}},
                    )
            self.assertEqual((), pipeline.observation.retained_events())
            self.assertEqual([], model.calls)

    def test_replay_reservation_precedes_content_and_audit_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            limits = ObservationLimits(
                retention_events=2,
                retention_bytes=100_000,
                snapshot_events=2,
                snapshot_bytes=100_000,
            )
            first, first_model, _, _ = foundation(
                persistence_path=path,
                limits=limits,
            )
            with mock.patch.object(
                first.observation,
                "_record_audit",
                side_effect=PersistenceError("simulated audit loss"),
            ):
                with self.assertRaises(PersistenceError):
                    first.handle_delivery(
                        delivery_id="d1",
                        event=message("e1"),
                        actors={"human:zoe": {"kind": "human"}},
                    )
            self.assertEqual([], first_model.calls)
            replay_path = path.with_name(path.name + ".replay-reservations.jsonl")
            self.assertTrue(replay_path.exists())

            after_loss, _, _, _ = foundation(
                persistence_path=path,
                limits=limits,
            )
            for index in (2, 3, 4):
                after_loss.observation.observe(
                    delivery_id=f"d{index}",
                    event=message(f"e{index}"),
                    actors={"human:zoe": {"kind": "human"}},
                )
            restored, restored_model, _, _ = foundation(
                persistence_path=path,
                limits=limits,
            )
            replay = restored.handle_delivery(
                delivery_id="d1",
                event=message("e1"),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertEqual("exact-duplicate", replay.observation.audit.outcome)
            self.assertEqual([], restored_model.calls)
            snapshot = restored.observation.build_snapshot("e4")
            self.assertTrue(snapshot["coverage"]["has_gaps"])

    def test_uncertain_replay_reservation_blocks_same_process_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            pipeline, model, _, _ = foundation(persistence_path=path)
            with mock.patch(
                "nunchi.observation.os.write",
                side_effect=OSError("simulated reservation uncertainty"),
            ):
                with self.assertRaises(PersistenceError):
                    pipeline.handle_delivery(
                        delivery_id="d1",
                        event=message("e1"),
                        actors={"human:zoe": {"kind": "human"}},
                    )
            retry = pipeline.handle_delivery(
                delivery_id="d1",
                event=message("e1"),
                actors={"human:zoe": {"kind": "human"}},
            )
            self.assertEqual("exact-duplicate", retry.observation.audit.outcome)
            self.assertEqual([], model.calls)
            self.assertEqual((), pipeline.observation.retained_events())

    def test_durable_gap_survives_restart_and_invalidates_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            first, _, _, _ = foundation(persistence_path=path)
            first.observation.observe(
                delivery_id="d1",
                event=message("e1"),
                actors={"human:zoe": {"kind": "human"}},
            )
            request = first.observation.build_snapshot("e1")
            first.observation.mark_continuity_gap(
                delivery_id="gap-1",
                detail="bounded transport loss",
            )
            if "continuation" in request:
                with self.assertRaises(Exception):
                    first.observation.fetch_context(
                        {
                            "request_id": request["request_id"],
                            "handle_id": request["continuation"]["handle_id"],
                            "direction": "before",
                            "max_events": 1,
                            "max_bytes": 100,
                        },
                        host_context=request["continuation"]["bound_to"],
                    )
            restored, _, _, _ = foundation(persistence_path=path)
            snapshot = restored.observation.build_snapshot("e1")
            self.assertTrue(snapshot["coverage"]["has_gaps"])
            self.assertTrue(snapshot["coverage"]["has_restart_gap"])
            self.assertEqual("unknown", snapshot["coverage"]["continuity"])

    def test_continuation_is_request_bound_truthful_and_nonoverlapping(self):
        limits = ObservationLimits(
            retention_events=10,
            retention_bytes=100_000,
            snapshot_events=2,
            snapshot_bytes=100_000,
            continuation_events=2,
            continuation_bytes=10_000,
        )
        pipeline, _, _, _ = foundation(limits=limits)
        for index in range(5):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
        request = pipeline.observation.build_snapshot("e4")
        continuation = request["continuation"]
        self.assertTrue(continuation["can_fetch_before"])
        self.assertFalse(continuation["can_fetch_after"])
        self.assertTrue(continuation["can_fetch_around_event"])
        base_fetch = {
            "request_id": request["request_id"],
            "handle_id": continuation["handle_id"],
            "direction": "before",
            "max_events": 2,
            "max_bytes": 10_000,
        }
        with self.assertRaises(ValidationError):
            pipeline.observation.fetch_context(
                {**base_fetch, "request_id": "wrong-request"},
                host_context=continuation["bound_to"],
            )
        with self.assertRaises(ValidationError):
            pipeline.observation.fetch_context(
                {**base_fetch, "direction": "after"},
                host_context=continuation["bound_to"],
            )
        first = pipeline.observation.fetch_context(
            base_fetch,
            host_context=continuation["bound_to"],
        )
        second = pipeline.observation.fetch_context(
            {**base_fetch, "cursor": first["next_cursor"]},
            host_context=continuation["bound_to"],
        )
        original_ids = {event["id"] for event in request["events"]}
        first_ids = {event["id"] for event in first["events"]}
        second_ids = {event["id"] for event in second["events"]}
        self.assertFalse(original_ids & first_ids)
        self.assertFalse(original_ids & second_ids)
        self.assertFalse(first_ids & second_ids)
        self.assertEqual({"e0", "e1", "e2"}, first_ids | second_ids)
        self.assertNotIn("next_cursor", second)

    def test_around_cursor_advances_without_repeating_events(self):
        pipeline, _, _, _ = foundation(
            limits=ObservationLimits(
                retention_events=10,
                retention_bytes=100_000,
                snapshot_events=1,
                snapshot_bytes=100_000,
                continuation_events=1,
                continuation_bytes=10_000,
            )
        )
        for index in range(4):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
        request = pipeline.observation.build_snapshot("e3")
        continuation = request["continuation"]
        fetch = {
            "request_id": request["request_id"],
            "handle_id": continuation["handle_id"],
            "direction": "around",
            "anchor_event_id": "e3",
            "max_events": 1,
            "max_bytes": 10_000,
        }
        seen = []
        cursor = None
        for _ in range(3):
            page = pipeline.observation.fetch_context(
                {**fetch, **({"cursor": cursor} if cursor else {})},
                host_context=continuation["bound_to"],
            )
            seen.extend(event["id"] for event in page["events"])
            cursor = page.get("next_cursor")
        self.assertEqual(["e2", "e1", "e0"], seen)
        self.assertIsNone(cursor)

    def test_continuation_handles_are_pruned_and_capacity_bounded(self):
        pipeline, _, _, _ = foundation(
            limits=ObservationLimits(
                retention_events=10,
                retention_bytes=100_000,
                snapshot_events=1,
                snapshot_bytes=100_000,
                continuation_events=1,
                continuation_bytes=10_000,
                continuation_handles=3,
            )
        )
        for index in range(4):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
        first = pipeline.observation.build_snapshot("e3")["continuation"]
        for _ in range(9):
            pipeline.observation.build_snapshot("e3")
        self.assertEqual(3, len(pipeline.observation._continuations))
        retained_id, retained = next(iter(pipeline.observation._continuations.items()))
        retained_page = pipeline.observation.fetch_context(
            {
                "request_id": retained.request_id,
                "handle_id": retained_id,
                "direction": "before",
                "max_events": 1,
                "max_bytes": 10_000,
            },
            host_context=retained.binding,
        )
        self.assertEqual(1, len(retained_page["events"]))
        with self.assertRaises(ValidationError):
            pipeline.observation.fetch_context(
                {
                    "request_id": next(
                        state.request_id
                        for state in pipeline.observation._continuations.values()
                    ),
                    "handle_id": first["handle_id"],
                    "direction": "before",
                    "max_events": 1,
                    "max_bytes": 100,
                },
                host_context=first["bound_to"],
            )


class HostMediationTests(unittest.TestCase):
    def test_participant_expansion_never_receives_capability_material(self):
        pages = []

        def participant(*, wake, expand, **_):
            page = expand(
                direction="before",
                anchor_event_id=wake["trigger_event_id"],
                max_events=2,
                max_bytes=10_000,
            )
            pages.append(deepcopy(page))
            return None

        pipeline, _, _, receipts = foundation(
            participant=participant,
            limits=ObservationLimits(
                retention_events=10,
                retention_bytes=100_000,
                snapshot_events=2,
                snapshot_bytes=100_000,
                continuation_events=2,
                continuation_bytes=10_000,
                continuation_handles=1,
            ),
        )
        for index in range(3):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
        outcome = pipeline.handle_delivery(
            delivery_id="d3",
            event=message("e3"),
            actors={"human:zoe": {"kind": "human"}},
        )
        serialized = json.dumps(pages)
        for forbidden in (
            "handle_id",
            "next_cursor",
            "continuity_scope_id",
            "expires_at",
            "bound_to",
        ):
            self.assertNotIn(forbidden, serialized)
        stream = receipts.records(outcome.opportunities[0].request_id)
        self.assertEqual(1, stream[2]["body"]["expansion_calls"])

    def test_host_caps_expansion_even_for_custom_participant(self):
        attempts = []

        def participant(*, wake, expand, **_):
            for _ in range(5):
                attempts.append(
                    expand(
                        direction="before",
                        anchor_event_id=wake["trigger_event_id"],
                        max_events=1,
                        max_bytes=10_000,
                    )
                )
            return None

        pipeline, _, transport, receipts = foundation(
            participant=participant,
            limits=ObservationLimits(
                retention_events=10,
                retention_bytes=100_000,
                snapshot_events=1,
                snapshot_bytes=100_000,
                continuation_events=1,
                continuation_bytes=10_000,
            ),
        )
        for index in range(4):
            pipeline.observation.observe(
                delivery_id=f"d{index}",
                event=message(f"e{index}"),
                actors={"human:zoe": {"kind": "human"}},
            )
        outcome = pipeline.handle_delivery(
            delivery_id="d4",
            event=message("e4"),
            actors={"human:zoe": {"kind": "human"}},
        )
        opportunity = outcome.opportunities[0]
        self.assertEqual("failed", opportunity.transport.delivery)
        # Three pages, then one note that the limit is reached; only asking
        # again after the note fails the turn.
        self.assertEqual(4, len(attempts))
        self.assertEqual([], attempts[3]["events"])
        self.assertIn("the limit", attempts[3]["note"])
        self.assertEqual([], transport.calls)
        stream = receipts.records(opportunity.request_id)
        self.assertEqual(3, stream[2]["body"]["expansion_calls"])
        self.assertEqual("unknown", stream[2]["body"]["outcome"])

    def test_expanded_fact_may_bind_origin_and_target(self):
        def participant(*, wake, expand, **_):
            page = expand(
                direction="before",
                anchor_event_id=wake["trigger_event_id"],
                max_events=1,
                max_bytes=10_000,
            )
            target = page["events"][0]["id"]
            return {
                "kind": "reply",
                "origin_event_id": target,
                "target_event_id": target,
                "text": "Replying from explicitly expanded context.",
            }

        pipeline, _, transport, _ = foundation(
            participant=participant,
            limits=ObservationLimits(
                retention_events=10,
                retention_bytes=100_000,
                snapshot_events=1,
                snapshot_bytes=100_000,
                continuation_events=1,
                continuation_bytes=10_000,
            ),
        )
        pipeline.observation.observe(
            delivery_id="d0",
            event=message("e0"),
            actors={"human:zoe": {"kind": "human"}},
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual("sent", outcome.opportunities[0].transport.delivery)
        self.assertEqual("e0", transport.calls[0][0]["origin_event_id"])
        self.assertEqual("e0", transport.calls[0][0]["target_event_id"])

    def test_unseen_reply_target_is_rejected(self):
        pipeline, _, transport, _ = foundation(
            participant=lambda **_: {
                "kind": "reply",
                "origin_event_id": "e1",
                "target_event_id": "not-visible",
                "text": "must not escape visible facts",
            }
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual("failed", outcome.opportunities[0].transport.delivery)
        self.assertEqual([], transport.calls)

    def test_cross_room_origin_cannot_escape_its_observation_provider(self):
        first, _, first_transport, _ = foundation(
            participant=lambda **_: {
                "kind": "message",
                "origin_event_id": "room-two-event",
                "text": "cross-room leak",
            }
        )
        outcome = first.handle_delivery(
            delivery_id="d1",
            event=message("room-one-event"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual("failed", outcome.opportunities[0].transport.delivery)
        self.assertEqual([], first_transport.calls)


class DiscordConfigurationTests(unittest.TestCase):
    def base_environment(self):
        return {
            "NUNCHI_DISCORD_TOKEN": "token",
            "NUNCHI_DISCORD_PARTICIPANT_ROUTES": json.dumps(
                {"vigil": ["42"], "reviewer": ["43"]}
            ),
            "NUNCHI_DISCORD_OUTPUT_HMAC_KEY": "x" * 32,
            "NUNCHI_DISCORD_STATE_DIRECTORY": "/tmp/nunchi-test-state",
        }

    def test_routes_are_exact_not_a_participant_room_cross_product(self):
        config = load_config(self.base_environment())
        self.assertEqual(
            (
                ("vigil", ("42",)),
                ("reviewer", ("43",)),
            ),
            config.participant_routes,
        )
        self.assertEqual(("42", "43"), config.allowed_channel_ids)

    def test_nonpositive_or_nonfinite_queue_and_timing_limits_fail(self):
        variables = (
            ("NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE", "0"),
            ("NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS", "-1"),
            ("NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS", "nan"),
            ("NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS", "0"),
        )
        for name, value in variables:
            environment = {**self.base_environment(), name: value}
            with self.subTest(name=name), self.assertRaises(ValueError):
                load_config(environment)


class DurableToolAuthorizationTests(unittest.TestCase):
    def test_accepted_nonce_is_replay_blocked_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "nonces.jsonl"
            secret = b"s" * 32
            arguments = {"channel_id": "42", "content": "hello"}
            authorization = make_tool_authorization(
                secret=secret,
                request_id="request",
                participant_id="vigil",
                room_id="42",
                tool="send_message",
                arguments=arguments,
                now=100,
            )
            first = ToolAuthorizer(
                secret=secret,
                participant_routes={"vigil": frozenset({"42"})},
                journal_path=journal,
            )
            self.assertTrue(
                first.verify(
                    authorization=authorization,
                    tool="send_message",
                    arguments=arguments,
                    now=100,
                )[0]
            )
            second = ToolAuthorizer(
                secret=secret,
                participant_routes={"vigil": frozenset({"42"})},
                journal_path=journal,
            )
            ok, detail = second.verify(
                authorization=authorization,
                tool="send_message",
                arguments=arguments,
                now=100,
            )
            self.assertFalse(ok)
            self.assertIn("replayed", detail)

    def test_untrusted_nonce_journal_fails_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "nonces.jsonl"
            journal.write_text('{"nonce":"n"}\n')
            with self.assertRaises(ValueError):
                ToolAuthorizer(
                    secret=b"s" * 32,
                    participant_routes={"vigil": frozenset({"42"})},
                    journal_path=journal,
                )


class TransportGapTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_shared_gateway_declares_gap_before_connect(self):
        gaps = []
        shutdown = asyncio.Event()

        async def fail_connect(_url):
            shutdown.set()
            raise OSError("offline test")

        runner = GatewayRunner(
            GatewayProtocol("test-token"),
            lambda _event: None,
            on_source_gap=lambda: gaps.append("gap"),
            connect=fail_connect,
        )
        await runner.run(shutdown)
        self.assertEqual(["gap"], gaps)

    async def test_unauthenticated_or_wrong_route_session_never_receives(self):
        class Session:
            def __init__(self):
                self.received = []

            async def send_notification(self, notification):
                self.received.append(notification)

        registry = AuthenticatedSessionRegistry()
        session = Session()
        params = {
            "target_participant_id": "vigil",
            "room_id": "42",
            "transport_self_actor_id": "discord:actor:9",
        }
        self.assertFalse(await deliver_targeted(registry, params, object()))
        self.assertEqual([], session.received)
        registry.bind(
            session,
            participant_id="vigil",
            room_id="42",
            transport_self_actor_id="discord:actor:9",
        )
        self.assertFalse(
            await deliver_targeted(
                registry,
                {**params, "room_id": "43"},
                object(),
            )
        )
        self.assertFalse(
            await deliver_targeted(
                registry,
                {**params, "target_participant_id": "other"},
                object(),
            )
        )
        self.assertTrue(await deliver_targeted(registry, params, object()))
        self.assertEqual(1, len(session.received))

    async def test_queue_rejection_precedes_next_event_with_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = asyncio.Queue(maxsize=1)
            enqueuer = GapAwareEnqueuer(
                queue,
                TransportAuditJournal(Path(directory) / "transport.jsonl"),
                {"vigil": frozenset({"42"})},
            )
            first = {
                "schema_version": 2,
                "delivery_id": "d1",
                "room_id": "42",
                "event": None,
                "actors": {},
                "continuity_gap": False,
                "transport_self_actor_id": "discord:actor:9",
            }
            second = {**first, "delivery_id": "d2"}
            third = {**first, "delivery_id": "d3"}
            self.assertTrue(enqueuer(first))
            self.assertFalse(enqueuer(second))
            self.assertEqual("d1", (await queue.get())["delivery_id"])
            # The gap uses the only slot; the current event is safely rejected
            # and remains represented by another pending gap.
            self.assertFalse(enqueuer(third))
            gap = await queue.get()
            self.assertTrue(gap["continuity_gap"])
            records = [
                json.loads(line)
                for line in (Path(directory) / "transport.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                ["accepted", "queue-rejected", "gap-signal", "queue-rejected"],
                [record["outcome"] for record in records],
            )

    async def test_per_participant_loss_and_restart_reconstruct_only_its_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport.jsonl"
            routes = {
                "vigil": frozenset({"42"}),
                "reviewer": frozenset({"42"}),
            }
            queue = asyncio.Queue(maxsize=8)
            enqueuer = GapAwareEnqueuer(
                queue,
                TransportAuditJournal(path),
                routes,
            )
            event = {
                "schema_version": 2,
                "delivery_id": "d1",
                "room_id": "42",
                "event": None,
                "actors": {},
                "continuity_gap": False,
                "transport_self_actor_id": "discord:actor:9",
            }
            self.assertTrue(enqueuer(event))
            first = await queue.get()
            second = await queue.get()
            by_participant = {
                item["target_participant_id"]: item
                for item in (first, second)
            }
            enqueuer.record_delivery(by_participant["vigil"])
            enqueuer.declare_delivery_gap(by_participant["reviewer"])

            restored_queue = asyncio.Queue(maxsize=8)
            restored = GapAwareEnqueuer(
                restored_queue,
                TransportAuditJournal(path),
                routes,
            )
            # Every event is accepted: the reviewer's behind a gap, not in its place.
            self.assertTrue(restored({**event, "delivery_id": "d2"}))
            routed = [
                await restored_queue.get(),
                await restored_queue.get(),
                await restored_queue.get(),
            ]
            self.assertTrue(restored_queue.empty())
            self.assertEqual(
                [
                    ("vigil", False, "d2"),
                    ("reviewer", True, None),
                    ("reviewer", False, "d2"),
                ],
                [
                    (
                        item["target_participant_id"],
                        item["continuity_gap"],
                        None if item["continuity_gap"] else item["delivery_id"],
                    )
                    for item in routed
                ],
            )
            gap = routed[1]
            restored.record_delivery(gap)
            self.assertTrue(restored({**event, "delivery_id": "d3"}))
            accepted = [
                await restored_queue.get(),
                await restored_queue.get(),
            ]
            self.assertEqual(
                {"vigil", "reviewer"},
                {item["target_participant_id"] for item in accepted},
            )
            self.assertFalse(any(item["continuity_gap"] for item in accepted))

    async def test_the_event_behind_a_gap_is_accepted_when_it_fits(self):
        """A restart (or any loss) makes the next event arrive behind a gap, not in its place."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport.jsonl"
            routes = {"vigil": frozenset({"42"})}
            # A previous process lost a delivery.
            previous = GapAwareEnqueuer(asyncio.Queue(maxsize=8), TransportAuditJournal(path), routes)
            previous.declare_source_gap()
            queue = asyncio.Queue(maxsize=8)
            enqueuer = GapAwareEnqueuer(queue, TransportAuditJournal(path), routes)
            first = {
                "schema_version": 2,
                "delivery_id": "d1",
                "room_id": "42",
                "event": None,
                "actors": {},
                "continuity_gap": False,
                "transport_self_actor_id": "discord:actor:9",
            }
            self.assertTrue(enqueuer(first))
            gap = await queue.get()
            self.assertTrue(gap["continuity_gap"])
            self.assertEqual("d1", (await queue.get())["delivery_id"])
            # The gap goes in once; a second event queues behind the first.
            self.assertTrue(enqueuer({**first, "delivery_id": "d2"}))
            self.assertEqual("d2", (await queue.get())["delivery_id"])
            self.assertTrue(queue.empty())
            enqueuer.record_delivery(gap)
            self.assertTrue(enqueuer({**first, "delivery_id": "d3"}))
            self.assertEqual("d3", (await queue.get())["delivery_id"])
            self.assertTrue(queue.empty(), "no new gap once one was delivered")
            outcomes = [json.loads(line)["outcome"] for line in path.read_text().splitlines()]
            self.assertEqual(
                ["source-gap", "gap-signal", "accepted", "accepted", "gap-delivered", "accepted"],
                outcomes,
            )

    async def test_an_event_is_rejected_only_when_no_slot_is_left(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport.jsonl"
            routes = {"vigil": frozenset({"42"})}
            GapAwareEnqueuer(
                asyncio.Queue(maxsize=8), TransportAuditJournal(path), routes
            ).declare_source_gap()
            event = {
                "schema_version": 2,
                "delivery_id": "d1",
                "room_id": "42",
                "event": None,
                "actors": {},
                "continuity_gap": False,
                "transport_self_actor_id": "discord:actor:9",
            }
            # One slot: the gap takes it and the event is rejected, the gap standing for it.
            one = asyncio.Queue(maxsize=1)
            enqueuer = GapAwareEnqueuer(one, TransportAuditJournal(path), routes)
            self.assertFalse(enqueuer(event))
            self.assertTrue((await one.get())["continuity_gap"])
            # No slot at all: not even the gap is queued, and the route stays pending.
            full = asyncio.Queue(maxsize=1)
            full.put_nowait({"placeholder": True})
            blocked = GapAwareEnqueuer(full, TransportAuditJournal(path), routes)
            self.assertFalse(blocked({**event, "delivery_id": "d2"}))
            self.assertEqual([{"placeholder": True}], [full.get_nowait()])
            self.assertEqual({("vigil", "42")}, blocked.audit.pending_routes)
            # Two slots: both fit.
            two = asyncio.Queue(maxsize=2)
            fits = GapAwareEnqueuer(two, TransportAuditJournal(path), routes)
            self.assertTrue(fits({**event, "delivery_id": "d3"}))
            self.assertEqual(2, two.qsize())

    async def test_an_event_does_not_overtake_a_gap_whose_delivery_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport.jsonl"
            routes = {"vigil": frozenset({"42"})}
            queue = asyncio.Queue(maxsize=8)
            enqueuer = GapAwareEnqueuer(queue, TransportAuditJournal(path), routes)
            enqueuer.declare_source_gap()
            event = {
                "schema_version": 2,
                "delivery_id": "d1",
                "room_id": "42",
                "event": None,
                "actors": {},
                "continuity_gap": False,
                "transport_self_actor_id": "discord:actor:9",
            }
            self.assertTrue(enqueuer(event))  # the gap, then d1 behind it
            client_is_up = False
            sent: list[tuple[bool, str]] = []

            async def send(params):
                if not client_is_up:
                    return False
                sent.append((params["continuity_gap"], params["delivery_id"]))
                return True

            shutdown = asyncio.Event()
            pump = asyncio.create_task(
                pump_notifications(
                    queue,
                    send,
                    shutdown=shutdown,
                    on_delivery_gap=enqueuer.declare_delivery_gap,
                    on_delivery_success=enqueuer.record_delivery,
                    hold=enqueuer.behind_a_failed_gap,
                )
            )
            try:
                await asyncio.wait_for(queue.join(), 5)
                self.assertEqual([], sent)
                # The client is back. d1 sat behind the gap that failed: it is
                # lost with its audit, not delivered without the gap.
                client_is_up = True
                self.assertTrue(enqueuer({**event, "delivery_id": "d2"}))
                await asyncio.wait_for(queue.join(), 5)
            finally:
                shutdown.set()
                await asyncio.wait_for(pump, 5)
            self.assertEqual(
                [(True, None), (False, "d2")],
                [(gap, None if gap else delivery) for gap, delivery in sent],
            )
            records = [json.loads(line) for line in path.read_text().splitlines()]
            lost = [r["delivery_id"] for r in records if r["outcome"] == "client-delivery-lost"]
            self.assertEqual(2, len(lost))  # the gap, and d1 behind it
            self.assertIn("d1", lost)
            self.assertEqual(
                ["gap-delivered", "client-delivered"], [r["outcome"] for r in records[-2:]]
            )
            self.assertEqual(set(), enqueuer.audit.pending_routes)

    async def test_a_delivered_gap_lets_the_events_behind_it_through(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = asyncio.Queue(maxsize=8)
            enqueuer = GapAwareEnqueuer(
                queue,
                TransportAuditJournal(Path(directory) / "transport.jsonl"),
                {"vigil": frozenset({"42"})},
            )
            enqueuer.declare_source_gap()
            event = {
                "schema_version": 2,
                "delivery_id": "d1",
                "room_id": "42",
                "event": None,
                "actors": {},
                "continuity_gap": False,
                "transport_self_actor_id": "discord:actor:9",
            }
            enqueuer(event)
            gap, behind = await queue.get(), await queue.get()
            self.assertFalse(enqueuer.behind_a_failed_gap(behind))
            enqueuer.declare_delivery_gap(gap)
            self.assertTrue(enqueuer.behind_a_failed_gap(behind))
            self.assertFalse(enqueuer.behind_a_failed_gap(gap))
            # A fresh gap that arrives clears it.
            enqueuer.record_delivery(gap)
            self.assertFalse(enqueuer.behind_a_failed_gap(behind))

    async def test_corrupt_transport_journal_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport.jsonl"
            path.write_text('{"outcome":"accepted"}\n')
            with self.assertRaises(ValueError):
                TransportAuditJournal(path)

    async def test_gateway_source_gap_persists_for_every_exact_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport.jsonl"
            routes = {
                "vigil": frozenset({"42"}),
                "reviewer": frozenset({"43"}),
            }
            enqueuer = GapAwareEnqueuer(
                asyncio.Queue(maxsize=8),
                TransportAuditJournal(path),
                routes,
            )
            enqueuer.declare_source_gap()
            restored = TransportAuditJournal(path)
            self.assertEqual(
                {("vigil", "42"), ("reviewer", "43")},
                restored.pending_routes,
            )


class ThreadsInRoomTests(unittest.TestCase):
    """`binding.threads_in_room`: whether a thread under the room is part of it, decided once in the core."""

    def binding(self, **fields) -> ParticipantBinding:
        return ParticipantBinding(
            participant_id="vigil", actor_id="discord:actor:9", platform="discord", room_id="200",
            continuity_scope_id="discord:channel:200", **fields,
        )

    def test_a_message_in_a_thread_is_the_rooms_unless_the_binding_keeps_threads_out_of_it(self):
        """The rule is the library's, once: any harness that names a message's thread gets it."""
        actors = {"human:zoe": {"kind": "human", "display_name": "Zoe"}}
        for threads, outcome in ((True, "recorded"), (False, "route-rejected")):
            with self.subTest(threads_in_room=threads):
                pipeline, *_ = foundation(binding=self.binding(threads_in_room=threads))
                observation = pipeline.observation
                inside = observation.observe(
                    delivery_id="d1", event=message("discord:message:301", thread_root_event_id="discord:message:300"), actors=actors
                )
                main = observation.observe(delivery_id="d2", event=message("discord:message:302"), actors=actors)
                self.assertEqual(outcome, inside.audit.outcome)
                self.assertEqual(outcome == "recorded", inside.wake_eligible)
                self.assertEqual("recorded", main.audit.outcome, "the room's own messages are always heard")
                held = [event["id"] for event in observation.retained_events()]
                self.assertEqual(["discord:message:301", "discord:message:302"] if threads else ["discord:message:302"], held)



class ReferenceThreadReplyTests(unittest.IsolatedAsyncioTestCase):
    """The reference answers where the message it answers was said: in the thread, or the room."""

    async def asyncSetUp(self):
        self.sent = []

        class Channel:
            def __init__(inner, channel_id):
                inner.id = channel_id

            async def send(inner, text):
                self.sent.append((inner.id, "send", text))
                return mock.Mock(id=900)

            def get_partial_message(inner, message_id):
                target = mock.Mock()

                async def reply(text, mention_author=False):
                    self.sent.append((inner.id, "reply", text, message_id))
                    return mock.Mock(id=901)

                async def add_reaction(emoji):
                    self.sent.append((inner.id, "react", emoji, message_id))

                target.reply, target.add_reaction = reply, add_reaction
                return target

        channels = {200: Channel(200), 300: Channel(300)}
        bot = mock.Mock()
        bot.get_channel = channels.get
        self.transport = DiscordPyTransport(bot, asyncio.get_running_loop(), "200")
        self.wake = {
            "room": {"id": "200"},
            "events": [
                {"id": "discord:message:1"},
                {"id": "discord:message:2", "thread_root_event_id": "discord:message:300"},
            ],
        }

    async def test_a_reply_a_post_and_a_reaction_about_a_thread_message_go_to_the_thread(self):
        for action in (
            {"kind": "reply", "origin_event_id": "discord:message:2", "target_event_id": "discord:message:2", "text": "yes"},
            {"kind": "message", "origin_event_id": "discord:message:2", "text": "yes"},
            {"kind": "reaction", "origin_event_id": "discord:message:2", "target_event_id": "discord:message:2",
             "reaction": "+1", "operation": "add"},
        ):
            with self.subTest(kind=action["kind"]):
                self.assertEqual("sent", (await self.transport._dispatch(action, self.wake)).delivery)
        self.assertEqual({300}, {item[0] for item in self.sent})
        self.assertEqual(["reply", "send", "react"], [item[1] for item in self.sent])

    async def test_anything_else_goes_to_the_room(self):
        action = {"kind": "reply", "origin_event_id": "discord:message:1", "target_event_id": "discord:message:1", "text": "yes"}
        self.assertEqual("sent", (await self.transport._dispatch(action, self.wake)).delivery)
        self.assertEqual([200], [item[0] for item in self.sent])


class ReferenceThreadHearingTests(unittest.TestCase):
    """What `nunchi-discord` does with a message or reaction in a thread, by `threads_in_room`.

    `main` runs for real with discord.py scripted: its handlers (`on_ready`,
    `on_message`, `on_raw_reaction_add`) are handed what Discord would send,
    and the adapter's own normalizer and observation read it, so the thread
    rule is the one that runs in `nunchi-discord`. The model is never called.
    """

    ROOM, THREAD, BOT = 200, 300, 9

    def run_adapter(self, *, room_id: int, threads_in_room: bool, scenario):
        """Run `main` with ``scenario`` as the gateway; returns [(audit outcome, event id)] for each delivery, in order."""
        import sys
        import types

        from nunchi.adapters import discord as adapter
        from nunchi.adapters.runtime import ReferenceAdapterRuntime
        from tests.v2.test_room_secret_guard import _profile

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        config = {
            "schema_version": 2,
            "binding": {
                "participant_id": "vigil",
                "actor_id": f"discord:actor:{self.BOT}",
                "platform": "discord",
                "room_id": str(room_id),
                "continuity_scope_id": f"discord:channel:{room_id}",
                "threads_in_room": threads_in_room,
            },
            "profile": _profile(base, f"discord:actor:{self.BOT}"),
            "attention": {
                "policy": {"preattention_enabled": False},
                "model": {"model": "m", "base_url": "http://127.0.0.1:9/v1", "api_key_env": "REF_ATTENTION_KEY"},
            },
            "limits": {},
            "state_directory": str(base / "state"),
            "participant_model": {"model": "m", "base_url": "http://127.0.0.1:9/v1"},
            "transport": {"bot_token_env": "DISCORD_BOT_TOKEN"},
        }

        class Thread:
            def __init__(inner, channel_id, parent_id):
                inner.id, inner.parent_id = channel_id, parent_id

        discord = types.ModuleType("discord")
        discord.Thread = Thread
        discord.HTTPException = type("HTTPException", (Exception,), {})
        discord.Intents = type("Intents", (), {"none": classmethod(lambda cls: cls())})
        fetched = []
        channels = {self.THREAD: Thread(self.THREAD, self.ROOM), self.ROOM: types.SimpleNamespace(id=self.ROOM)}

        class Client:
            def __init__(inner, intents):
                inner.handlers = {}
                inner.user = types.SimpleNamespace(id=self.BOT)

            def event(inner, handler):
                inner.handlers[handler.__name__] = handler
                return handler

            def get_channel(inner, channel_id):
                return channels.get(channel_id)

            async def fetch_channel(inner, channel_id):
                fetched.append(channel_id)
                raise discord.HTTPException()

            def run(inner, token, log_handler=None):
                async def play():
                    await inner.handlers["on_ready"]()
                    await scenario(inner.handlers, channels)

                asyncio.run(play())

            async def close(inner):
                pass

        discord.Client = Client
        heard = []

        def submit(runtime, payload, *, live=True):
            # What the room would do with it, without waking anyone.
            observed = runtime.process(payload, live=False).observation
            heard.append((observed.audit.outcome, observed.audit.event_id))
            return mock.Mock()

        environment = {"DISCORD_BOT_TOKEN": "t", "REF_ATTENTION_KEY": "a" * 24, "NUNCHI_PARTICIPANT_API_KEY": "p" * 24}
        with (
            mock.patch.dict(sys.modules, {"discord": discord}),
            mock.patch.dict(os.environ, environment),
            mock.patch.object(adapter, "keep_private"),
            mock.patch.object(adapter, "load_pinned_config", return_value=config),
            mock.patch.object(ReferenceAdapterRuntime, "submit", submit),
        ):
            self.assertEqual(0, adapter.main(["--config", "c", "--config-sha256", "s"]))
        self.fetched = fetched
        return heard

    @staticmethod
    def said(message_id, channel):
        import types
        from datetime import datetime, timezone

        return types.SimpleNamespace(
            id=message_id, channel=channel, guild=types.SimpleNamespace(id=1),
            author=types.SimpleNamespace(id=5, name="zoe", global_name="Zoe", display_name="Zoe", bot=False),
            content="hello", mentions=[], mention_everyone=False,
            created_at=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc), reference=None,
        )

    @staticmethod
    def reacted(channel_id, message_id):
        import types

        return types.SimpleNamespace(
            channel_id=channel_id, guild_id=1, user_id=5, message_id=message_id,
            emoji=types.SimpleNamespace(id=None, name="\N{THUMBS UP SIGN}"),
        )

    def test_a_message_and_a_reaction_in_a_thread_are_the_rooms_unless_the_binding_keeps_threads_out_of_it(self):
        async def scenario(handlers, channels):
            await handlers["on_message"](self.said(1000, channels[self.ROOM]))
            await handlers["on_message"](self.said(1001, channels[self.THREAD]))
            await handlers["on_raw_reaction_add"](self.reacted(self.THREAD, 1001))

        for threads, thread_outcome in ((True, "recorded"), (False, "route-rejected")):
            with self.subTest(threads_in_room=threads):
                heard = self.run_adapter(room_id=self.ROOM, threads_in_room=threads, scenario=scenario)
                self.assertEqual(
                    [("recorded", "discord:message:1000"), (thread_outcome, "discord:message:1001" if threads else None),
                     (thread_outcome, mock.ANY if threads else None)],
                    heard,
                )
                self.assertEqual([], self.fetched, "a thread the cache holds is not fetched")

    def test_bound_to_one_thread_it_hears_that_thread(self):
        """A binding's room may be a thread's id: that channel is the room, not a thread of another."""

        async def scenario(handlers, channels):
            await handlers["on_message"](self.said(1001, channels[self.THREAD]))
            await handlers["on_raw_reaction_add"](self.reacted(self.THREAD, 1001))
            await handlers["on_message"](self.said(1002, channels[self.ROOM]))

        heard = self.run_adapter(room_id=self.THREAD, threads_in_room=True, scenario=scenario)
        self.assertEqual(
            [("recorded", "discord:message:1001"), ("recorded", mock.ANY), ("route-rejected", None)],
            heard,
            "its own messages and reactions arrive; the channel above it is another room",
        )
        self.assertEqual([], self.fetched)


class ReferenceStartupTests(unittest.TestCase):
    def test_standalone_discord_fresh_ready_declares_gap(self):
        runtime = mock.Mock()
        _declare_fresh_gateway_gap(runtime)
        call = runtime.pipeline.observation.mark_continuity_gap.call_args.kwargs
        self.assertTrue(call["delivery_id"].startswith("discord:standalone-startup-gap:"))
        self.assertIn("before READY", call["detail"])

    def test_telegram_backfill_is_one_bounded_tail_poll(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_TOKEN": "secret"}, clear=False):
            transport = TelegramTransport(
                {
                    "bot_token_env": "TELEGRAM_TOKEN",
                    "poll_timeout_seconds": 30,
                }
            )
        transport._call = mock.Mock(return_value=[])
        self.assertEqual(
            [],
            _poll_updates(transport, offset=123, backfilling=True),
        )
        method, payload = transport._call.call_args.args
        self.assertEqual("getUpdates", method)
        self.assertEqual(-100, payload["offset"])
        self.assertEqual(0, payload["timeout"])
        self.assertEqual(100, payload["limit"])
        transport._call.reset_mock()
        _poll_updates(transport, offset=123, backfilling=False)
        self.assertEqual(123, transport._call.call_args.args[1]["offset"])
        self.assertEqual(30, transport._call.call_args.args[1]["timeout"])


class InstalledSurfaceTests(unittest.TestCase):
    def test_installer_creates_private_v2_only_state(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            state = Path(directory) / "state"
            result = initialize(config, state)
            self.assertEqual("initialized", result["status"])
            checked = verify(config)
            self.assertFalse(checked["v1_fallback"])
            self.assertEqual([], checked["excluded_integrations"])
            self.assertEqual(0, config.stat().st_mode & 0o077)
            self.assertEqual(0, state.stat().st_mode & 0o077)

    def test_cli_probe_is_v2_and_admit_is_absent(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main(["probe"]))
        probe = json.loads(output.getvalue())
        self.assertEqual(2, probe["generation"])
        self.assertFalse(probe["v1_fallback"])
        # The probe reports the versions the schemas declare.
        from tests.v2.contract.schema_helpers import INTERFACE_VERSIONS

        for interface, _, version in INTERFACE_VERSIONS.values():
            with self.subTest(interface=interface):
                self.assertEqual(version, probe["interfaces"][interface])
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["admit"])

    def test_packaging_and_codex_bundle_have_no_v1_execution_paths(self):
        root = Path(__file__).resolve().parents[2]
        pyproject = (root / "pyproject.toml").read_text()
        self.assertIn('requires = ["setuptools==83.0.0"]', pyproject)
        for retired in (
            "nunchi-codex-prompt-gate",
            "nunchi-codex-send-gate",
            "nunchi-codex-config-app",
            "nunchi admit",
        ):
            self.assertNotIn(retired, pyproject)
        for retired_module in (
            "adapters.py",
            "loader.py",
            "report.py",
            "invariants.py",
        ):
            self.assertFalse(
                (root / "evals" / "verdict_suite" / retired_module).exists()
            )
        hooks = json.loads(
            (
                root
                / "integrations"
                / "codex"
                / "nunchi-codex"
                / "hooks"
                / "hooks.json"
            ).read_text()
        )
        tools = json.loads(
            (
                root
                / "integrations"
                / "codex"
                / "nunchi-codex"
                / ".mcp.json"
            ).read_text()
        )
        self.assertEqual({"hooks": {}}, hooks)
        self.assertEqual({"mcpServers": {}}, tools)


if __name__ == "__main__":
    unittest.main()
