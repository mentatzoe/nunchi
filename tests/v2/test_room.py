"""`Room`: the library's side for one participant, assembled once (#94 step 9d)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from nunchi.conformance import fixture_attention_model
from nunchi.errors import ValidationError
from nunchi.participant import TransportResult
from nunchi.room import Room, RoomSettings
from nunchi.turn import HarnessDelivery, SecretGuard, Turn, TurnParticipant

PERSON = "room:person"
VISIBILITY = {"message": "history-and-live", "reaction": "history-and-live", "membership": "live-only"}


def _config(directory: Path, **overrides) -> dict:
    profile = {
        "profile_id": "room-profile",
        "participant_id": "room-participant",
        "actor_id": "room:actor:self",
        "instructions": "Participate directly and preserve uncertainty.",
        "provenance": "test",
    }
    raw = json.dumps(profile).encode()
    path = directory / "profile.json"
    path.write_bytes(raw)
    config = {
        "schema_version": 2,
        "binding": {
            "participant_id": "room-participant",
            "actor_id": "room:actor:self",
            "platform": "example",
            "room_id": "room-1",
            "continuity_scope_id": "example:room-1",
        },
        "profile": {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()},
        "attention": {"policy": {"preattention_enabled": True}, "model": {"kind": "fixture"}},
        "limits": {},
        "state_directory": str(directory / "state"),
        "harness": {"anything": "the integration checks it"},
    }
    config.update(overrides)
    return config


def _message(event_id: str, text: str) -> dict:
    return {
        "id": event_id,
        "type": "message",
        "author_id": PERSON,
        "text": text,
        "mentioned_actor_ids": [],
        "mentions_room": False,
    }


ACTORS = {PERSON: {"kind": "human", "display_name": "Sam"}}


class _Recording:
    def __init__(self) -> None:
        self.actions: list[dict] = []

    def dispatch(self, *, action, **_):
        self.actions.append(dict(action))
        return TransportResult("sent", "test room")


class _Driver:
    """Plays one move per turn on the agent's behalf."""

    def __init__(self, move) -> None:
        self.move = move
        self.participant: TurnParticipant | None = None
        self.results: list = []
        self.done = threading.Event()

    def start(self, turn: Turn) -> None:
        def run() -> None:
            participant = self.participant
            participant.bind_turn(turn_id="t1", wake_id=turn.wake_id)
            self.results.append(self.move(participant))
            participant.end_turn(turn_id="t1", ok=True)
            self.done.set()

        threading.Thread(target=run, daemon=True).start()

    def interrupt(self, turn: Turn) -> None:
        pass


class RoomSettingsTests(unittest.TestCase):
    def test_reads_the_shared_sections_and_returns_the_integrations_own(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = RoomSettings.from_config(
                _config(Path(directory)), label="Example", sections=("harness",)
            )
        self.assertEqual("room-participant", settings.binding.participant_id)
        self.assertEqual("room-profile", settings.profile.profile_id)
        self.assertTrue(settings.attention.preattention_enabled)
        self.assertEqual({"harness": {"anything": "the integration checks it"}}, dict(settings.sections))
        self.assertIsNone(settings.authorization)

    def test_refuses_a_config_that_is_not_the_shared_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = _config(root)
            cases = {
                "missing own section": ({}, ()),
                "unexpected section": ({"surprise": 1}, ("harness",)),
                "old schema": ({"schema_version": 1}, ("harness",)),
                "unknown binding field": ({"binding": {**good["binding"], "nick": "x"}}, ("harness",)),
                "someone else's profile": (
                    {"binding": {**good["binding"], "actor_id": "room:actor:other"}},
                    ("harness",),
                ),
                "bad limits": ({"limits": {"snapshot_events": 0}}, ("harness",)),
                "authorization with a stray key": (
                    {"authorization": {"policy_path": "p", "policy_sha256": "0", "extra": 1}},
                    ("harness",),
                ),
            }
            for name, (change, sections) in cases.items():
                with self.subTest(name), self.assertRaises(ValidationError):
                    RoomSettings.from_config(
                        _config(root, **change), label="Example", sections=sections
                    )

    def test_an_integration_may_allow_its_own_authorization_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            authorization = {"policy_path": "p", "policy_sha256": "0", "workspace_root": "/w"}
            settings = RoomSettings.from_config(
                _config(Path(directory), authorization=authorization),
                label="Example",
                sections=("harness",),
                authorization_keys=("workspace_root",),
            )
        self.assertEqual("/w", settings.authorization["workspace_root"])


class RoomTests(unittest.TestCase):
    def _room(self, directory: Path, *, driver, transport, silence_marker=None) -> Room:
        settings = RoomSettings.from_config(
            _config(directory), label="Example", sections=("harness",)
        )
        participant = TurnParticipant(
            profile=settings.profile,
            driver=driver,
            guard=SecretGuard(()),
            tool_names={role: f"room_{role}" for role in ("send", "react", "context")},
            roles=("send", "react", "context"),
            result_wait_seconds=5,
            silence_marker=silence_marker,
        )
        driver.participant = participant
        with mock.patch(
            "nunchi.room.attention_model_from_config",
            return_value=fixture_attention_model("WAKE"),
        ):
            return Room(
                settings,
                participant=participant,
                transport=transport,
                event_visibility=VISIBILITY,
                state_prefix="example-",
                participant_timeout_seconds=10,
            )

    def test_a_message_reaches_the_agent_and_its_post_reaches_the_room(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transport = _Recording()
            driver = _Driver(
                lambda participant: participant.call_tool(
                    turn_id="t1", tool="room_send", arguments={"text": "On it."}
                )
            )
            room = self._room(root, driver=driver, transport=transport)
            outcome = room.deliver(
                delivery_id="d1", event=_message("m1", "Can someone check the deploy?"), actors=ACTORS
            )
            self.assertTrue(outcome.observation.wake_eligible)
            self.assertTrue(driver.done.wait(10))
            self.assertTrue(room.drain(10))
            self.assertEqual((), room.errors)
            self.assertEqual(["On it."], [action["text"] for action in transport.actions])
            self.assertTrue(driver.results[0][0])
            state = root / "state"
            self.assertTrue((state / "example-receipts.jsonl").exists())
            self.assertTrue((state / "example-observations.jsonl").exists())
            self.assertEqual(0o700, state.stat().st_mode & 0o777)

    def test_a_harness_that_posts_its_agents_final_answer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = HarnessDelivery()
            driver = _Driver(
                lambda participant: participant.finish(turn_id="t1", answer="On it.")
            )
            room = self._room(
                Path(directory), driver=driver, transport=transport, silence_marker="[SILENT]"
            )
            room.deliver(
                delivery_id="d1", event=_message("m1", "Can someone check the deploy?"), actors=ACTORS
            )
            self.assertTrue(driver.done.wait(10))
            self.assertTrue(room.drain(10))
            self.assertEqual(("deliver", "On it."), (driver.results[0].kind, driver.results[0].text))

    def test_attention_needs_a_model_when_it_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = _config(Path(directory))
            config["attention"]["model"] = None
            settings = RoomSettings.from_config(config, label="Example", sections=("harness",))
            with self.assertRaises(ValidationError):
                Room(
                    settings,
                    participant=object(),
                    transport=_Recording(),
                    event_visibility=VISIBILITY,
                    state_prefix="example-",
                )

    def test_a_harness_model_can_judge_instead_of_a_configured_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = RoomSettings.from_config(
                _config(Path(directory)), label="Example", sections=("harness",)
            )
            model = fixture_attention_model("WAKE")
            room = Room(
                settings,
                participant=object(),
                transport=_Recording(),
                event_visibility=VISIBILITY,
                state_prefix="example-",
                attention_model=model,
            )
            self.assertIs(model, room.attention.model)


if __name__ == "__main__":
    unittest.main()
