"""The live Codex runner on the shared room connection (#94 step 9e).

`nunchi.integrations.discord_room` is the room connection every library-hosted
integration shares; the Codex runner builds its `Room` with it. These tests
need no Codex and no Discord: a stub stands in for the shared transport, and
attention lets every message pass, so Codex is never started.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from nunchi.attention_questions import answers_leaning
from nunchi.errors import ValidationError
from nunchi.integrations.codex_app_server import runner as codex_runner
from nunchi.integrations.codex_app_server.runner import CodexRoomRunner
from nunchi.integrations.discord_room import NOTIFICATION_METHOD

OUTPUT_KEY = "k" * 40


class _PassModel:
    """Attention that lets every message pass: no turn, so Codex never starts."""

    name = "pass"
    provider = "test"
    model_id = "pass"

    def judge(self, *, instructions, projection, timeout_seconds):
        return {
            **answers_leaning("SUPPRESS"),
            "notes": [{"note": "Not for this participant.", "evidence_event_ids": [projection["trigger_event_id"]]}],
        }


class _Client:
    """The shared transport's client, as the connection uses it."""

    def __init__(self, notifications=(), attestation=None):
        self.notifications_to_send = list(notifications)
        self.attestation = attestation
        self.calls = []
        self.connected = 0

    def connect(self):
        self.connected += 1
        return "session"

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": json.dumps(self.attestation)}]}

    def notifications(self):
        yield from self.notifications_to_send


def _config(base: Path) -> dict:
    raw = json.dumps({
        "profile_id": "vigil-profile",
        "participant_id": "vigil",
        "actor_id": "discord:actor:9",
        "instructions": "Participate directly and preserve uncertainty.",
        "provenance": "test",
    }).encode()
    (base / "profile.json").write_bytes(raw)
    (base / "work").mkdir()
    return {
        "schema_version": 2,
        "binding": {
            "participant_id": "vigil",
            "actor_id": "discord:actor:9",
            "platform": "discord",
            "room_id": "42",
            "continuity_scope_id": "discord:channel:42",
        },
        "profile": {"path": str(base / "profile.json"), "sha256": hashlib.sha256(raw).hexdigest()},
        "attention": {"policy": {"preattention_enabled": True}, "model": {"kind": "test"}},
        "limits": {},
        "state_directory": str(base / "state"),
        "transport": {"url": "http://127.0.0.1:1/mcp", "timeout_seconds": 5, "output_key_env": "ROOM_OUTPUT_KEY"},
        "codex": {"working_directory": str(base / "work"), "project_trust_level": "untrusted"},
    }


def _notification(event_id: str, text: str = "Anyone around?", **overrides) -> dict:
    params = {
        "schema_version": 2,
        "delivery_id": f"delivery:{event_id}",
        "room_id": "42",
        "event": {
            "id": event_id,
            "type": "message",
            "author_id": "discord:actor:5",
            "text": text,
            "mentioned_actor_ids": [],
            "mentions_room": False,
        },
        "actors": {"discord:actor:5": {"kind": "human", "display_name": "Sam"}},
        "continuity_gap": False,
        "target_participant_id": "vigil",
        "transport_self_actor_id": "discord:actor:9",
    }
    params.update(overrides)
    return params


ATTESTATION = {
    "registered": True,
    "participant_id": "vigil",
    "room_id": "42",
    "transport_self_actor_id": "discord:actor:9",
}


class CodexRoomRunnerTest(unittest.TestCase):
    def _runner(self, client=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environ = {"PATH": "/bin", "ROOM_OUTPUT_KEY": OUTPUT_KEY, "OPENAI_API_KEY": "the-agent-own-key"}
        with mock.patch("nunchi.room.attention_model_from_config", return_value=_PassModel()):
            runner = CodexRoomRunner(_config(Path(directory.name)), client or _Client(), environ=environ)
        self.addCleanup(runner.close)
        return runner

    def test_the_transport_key_never_reaches_codex_or_the_room(self):
        runner = self._runner()
        self.assertNotIn("ROOM_OUTPUT_KEY", runner.integration.environment)
        self.assertEqual("the-agent-own-key", runner.integration.environment["OPENAI_API_KEY"])
        refusal = runner.integration.participant.guard.refusal({"kind": "message", "text": f"key {OUTPUT_KEY}"})
        self.assertIsNotNone(refusal)

    def test_a_room_message_reaches_the_room_through_the_shared_connection(self):
        runner = self._runner()
        outcome = runner.connection.handle(_notification("discord:message:1"))
        self.assertTrue(outcome.observation.wake_eligible)
        self.assertTrue(runner.room.drain(10))
        self.assertEqual(["discord:message:1"], [event["id"] for event in runner.room.observation.retained_events()])
        # Attention let it pass: no Codex turn, so no app-server was started.
        self.assertIsNone(runner.integration.thread_id)

    def test_notifications_for_someone_else_are_refused(self):
        runner = self._runner()
        for change in (
            {"target_participant_id": "castor"},
            {"transport_self_actor_id": "discord:actor:8"},
            {"room_id": "43"},
            {"schema_version": 1},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                runner.connection.handle(_notification("discord:message:2", **change))

    def test_a_gap_is_recorded_and_cannot_carry_an_event(self):
        runner = self._runner()
        gap = _notification("discord:message:3", continuity_gap=True, event=None, actors={})
        outcome = runner.connection.handle(gap)
        self.assertEqual("continuity-gap", outcome.observation.audit.outcome)
        with self.assertRaises(ValidationError):
            runner.connection.handle(_notification("discord:message:4", continuity_gap=True))

    def test_registration_checks_the_transports_attestation(self):
        runner = self._runner(_Client(attestation=ATTESTATION))
        runner.connection.register()
        name, arguments = runner.connection.client.calls[0]
        self.assertEqual(("register_participant", "vigil", "42"), (name, arguments["participant_id"], arguments["channel_id"]))
        other = self._runner(_Client(attestation={**ATTESTATION, "transport_self_actor_id": "discord:actor:8"}))
        with self.assertRaises(RuntimeError):
            other.connection.register()

    def test_serve_connects_registers_hands_events_over_and_stops(self):
        stop = threading.Event()

        class Stopping(_Client):
            def notifications(self):
                yield NOTIFICATION_METHOD, _notification("discord:message:5")
                yield "notifications/other", {}
                stop.set()
                yield NOTIFICATION_METHOD, _notification("discord:message:6")

        client = Stopping(attestation=ATTESTATION)
        runner = self._runner(client)
        runner.connection.serve(stop=stop, sleep=lambda _: None)
        self.assertEqual(1, client.connected)
        retained = [event["id"] for event in runner.room.observation.retained_events()]
        self.assertEqual(["discord:message:5", "discord:message:6"], retained)

    def test_probe_says_what_is_configured(self):
        probe = self._runner().probe()
        self.assertEqual(("codex-app-server", True, "untrusted"), (probe["surface"], probe["configured"], probe["project_trust_level"]))
        self.assertEqual(["room_send", "room_react", "room_context"], probe["room_tools"])

    def test_the_command_line_without_a_config(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, codex_runner.main(["--probe"]))
        self.assertFalse(json.loads(output.getvalue())["configured"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(3, codex_runner.main([]))


if __name__ == "__main__":
    unittest.main()
