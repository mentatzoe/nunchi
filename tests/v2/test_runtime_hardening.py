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
from nunchi.errors import ValidationError
from nunchi.install import initialize, verify
from nunchi.mcp_discord.authorization import (
    ToolAuthorizer,
    make_tool_authorization,
)
from nunchi.mcp_discord.config import load_config
from nunchi.mcp_discord.server import (
    AuthenticatedSessionRegistry,
    GapAwareEnqueuer,
    TransportAuditJournal,
    deliver_targeted,
)
from nunchi.observation import (
    ObservationLimits,
    ObservationProvider,
    ParticipantBinding,
)
from nunchi.receipts import PersistenceError
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
            for _ in range(4):
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
        self.assertEqual(3, len(attempts))
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
            self.assertFalse(restored({**event, "delivery_id": "d2"}))
            routed = [
                await restored_queue.get(),
                await restored_queue.get(),
            ]
            ordinary = next(item for item in routed if not item["continuity_gap"])
            gap = next(item for item in routed if item["continuity_gap"])
            self.assertEqual("vigil", ordinary["target_participant_id"])
            self.assertEqual("reviewer", gap["target_participant_id"])
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


class InstalledSurfaceTests(unittest.TestCase):
    def test_installer_creates_private_v2_only_state(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            state = Path(directory) / "state"
            result = initialize(config, state)
            self.assertEqual("initialized", result["status"])
            checked = verify(config)
            self.assertFalse(checked["v1_fallback"])
            self.assertEqual(["hermes", "claude-code"], checked["excluded_integrations"])
            self.assertEqual(0, config.stat().st_mode & 0o077)
            self.assertEqual(0, state.stat().st_mode & 0o077)

    def test_cli_probe_is_v2_and_admit_is_absent(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, cli.main(["probe"]))
        probe = json.loads(output.getvalue())
        self.assertEqual(2, probe["generation"])
        self.assertFalse(probe["v1_fallback"])
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["admit"])

    def test_packaging_and_codex_bundle_have_no_v1_execution_paths(self):
        root = Path(__file__).resolve().parents[2]
        pyproject = (root / "pyproject.toml").read_text()
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
