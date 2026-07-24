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
from nunchi.install import initialize, verify
from nunchi.mcp_discord.authorization import (
    ToolAuthorizer,
    make_tool_authorization,
)
from nunchi.mcp_discord.server import GapAwareEnqueuer, TransportAuditJournal
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
            self.assertFalse(restored.scheduler.active)

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
                participant_ids=frozenset({"vigil"}),
                room_ids=frozenset({"42"}),
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
                participant_ids=frozenset({"vigil"}),
                room_ids=frozenset({"42"}),
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
                    participant_ids=frozenset({"vigil"}),
                    room_ids=frozenset({"42"}),
                    journal_path=journal,
                )


class TransportGapTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_rejection_precedes_next_event_with_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = asyncio.Queue(maxsize=1)
            enqueuer = GapAwareEnqueuer(
                queue,
                TransportAuditJournal(Path(directory) / "transport.jsonl"),
            )
            first = {
                "schema_version": 2,
                "delivery_id": "d1",
                "room_id": "42",
                "event": None,
                "actors": {},
                "continuity_gap": False,
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
