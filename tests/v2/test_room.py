"""`Room`: the library's side for one participant, assembled once (#94 step 9d)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import re

from nunchi.attention import AttentionPolicy
from nunchi.conformance import fixture_attention_model, fixture_binding, fixture_profile
from nunchi.errors import ValidationError
from nunchi.observation import ObservationLimits
from nunchi.participant import TransportResult
from nunchi.room import Room, RoomSettings, room_guard, withheld_env_names
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
            transport = HarnessDelivery(room_shows_own_messages=False)
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


def _refuses(guard, text: str) -> bool:
    return guard.refusal({"kind": "message", "origin_event_id": "m1", "text": text}) is not None


def _settings(directory: Path, *, attention_model=None, authorization=None, sections=None) -> RoomSettings:
    binding = fixture_binding()
    return RoomSettings(
        binding=binding,
        profile=fixture_profile(binding),
        attention=AttentionPolicy(),
        attention_model=attention_model,
        limits=ObservationLimits(),
        state_directory=directory / "state",
        authorization=authorization,
        sections=sections or {},
    )


class _HoldsAToken(_Recording):
    """A transport that holds a platform token and names its shape."""

    def withheld_values(self):
        return ("transport-held-token-value",)

    def credential_patterns(self):
        return (re.compile(r"tok_[a-z]{8}"),)


class RoomGuardTests(unittest.TestCase):
    """One secret guard per room, from what the config and the transport name."""

    ENVIRON = {
        "ATTENTION_KEY": "attention-route-key-value",
        "TRANSPORT_KEY": "transport-output-key-value",
        "FIRST_TOKEN": "first-listed-token-value",
        "SECOND_TOKEN": "second-listed-token-value",
        "POLICY_KEY": "authorization-key-value",
        "NESTED_KEY": "nested-route-key-value",
        "SHORT": "too-short",
        "UNNAMED": "a-value-no-config-names",
    }

    def test_every_variable_an_env_key_names_is_withheld(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = _settings(
                Path(directory),
                attention_model={"kind": "example", "api_key_env": "ATTENTION_KEY"},
                authorization={"policy_path": "p", "policy_sha256": "0", "credential_env": "POLICY_KEY"},
                sections={
                    "transport": {"url": "http://127.0.0.1:1/mcp", "output_key_env": "TRANSPORT_KEY"},
                    # A list of names, and a key deeper in a section.
                    "harness": {"withheld_env": ["FIRST_TOKEN", "SECOND_TOKEN"], "routes": [{"api_key_env": "NESTED_KEY"}]},
                    "short": {"token_env": "SHORT"},
                },
            )
            guard = room_guard(settings, environ=self.ENVIRON)
            self.assertEqual(
                ["ATTENTION_KEY", "TRANSPORT_KEY", "FIRST_TOKEN", "SECOND_TOKEN", "NESTED_KEY", "SHORT", "POLICY_KEY"],
                withheld_env_names(settings),
            )
        for name in ("ATTENTION_KEY", "TRANSPORT_KEY", "FIRST_TOKEN", "SECOND_TOKEN", "POLICY_KEY", "NESTED_KEY"):
            with self.subTest(name):
                self.assertTrue(_refuses(guard, f"here it is: {self.ENVIRON[name]}"))
        # Values under 12 characters are ignored; plain text and unnamed values pass.
        self.assertFalse(_refuses(guard, "the word too-short is fine"))
        self.assertFalse(_refuses(guard, self.ENVIRON["UNNAMED"]))
        self.assertFalse(_refuses(guard, "On it: the deploy failed on step three."))

    def test_the_default_key_variables_are_withheld_when_the_config_names_none(self) -> None:
        environ = {
            "NUNCHI_ATTENTION_API_KEY": "default-attention-key-value",
            "NUNCHI_PARTICIPANT_API_KEY": "default-participant-key-value",
        }
        with tempfile.TemporaryDirectory() as directory:
            settings = _settings(Path(directory), attention_model={"base_url": "http://127.0.0.1:1/v1"})
            guard = room_guard(settings, environ=environ)
            self.assertEqual([], withheld_env_names(settings))
        self.assertTrue(_refuses(guard, "default-attention-key-value"))
        self.assertTrue(_refuses(guard, "default-participant-key-value"))

    def test_what_the_transport_holds_and_the_integrations_own_values_and_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = _settings(Path(directory))
            guard = room_guard(
                settings,
                transport=_HoldsAToken(),
                values=["an-integration-default-secret", "short"],
                patterns=[re.compile(r"key-[0-9]{6}")],
                environ={},
            )
        self.assertTrue(_refuses(guard, "transport-held-token-value"))
        self.assertTrue(_refuses(guard, "token tok_abcdefgh here"))
        self.assertTrue(_refuses(guard, "an-integration-default-secret"))
        self.assertTrue(_refuses(guard, "key-123456"))
        self.assertFalse(_refuses(guard, "short"))
        # A transport that declares nothing adds nothing.
        self.assertFalse(_refuses(room_guard(settings, transport=_Recording(), environ={}), "tok_abcdefgh"))

    def test_the_room_builds_its_guard_and_its_host_checks_with_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = _settings(Path(directory))
            room = Room(
                settings,
                participant=object(),
                transport=_HoldsAToken(),
                event_visibility=VISIBILITY,
                state_prefix="example-",
                attention_model=fixture_attention_model("WAKE"),
            )
            self.assertTrue(_refuses(room.guard, "transport-held-token-value"))
            self.assertIs(room.guard, room.host.guard)
            given = SecretGuard(["a-guard-the-integration-built"])
            room = Room(
                settings,
                participant=object(),
                transport=_HoldsAToken(),
                event_visibility=VISIBILITY,
                state_prefix="example-",
                attention_model=fixture_attention_model("WAKE"),
                guard=given,
            )
            self.assertIs(given, room.guard)
            self.assertIs(given, room.host.guard)


class HostGuardTests(unittest.TestCase):
    """The host's backstop: a participant that ignores the guard still posts nothing."""

    SECRET = "a-withheld-secret-for-the-host"

    def _run(self, move):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = _settings(Path(directory.name))
        transport = _Recording()

        def participant(*, wake, expand, cancel):
            # Never looks at a guard: whatever it says goes to the host.
            return move(wake)

        room = Room(
            settings,
            participant=participant,
            transport=transport,
            event_visibility=VISIBILITY,
            state_prefix="example-",
            attention_model=fixture_attention_model("WAKE"),
            guard=SecretGuard([self.SECRET]),
        )
        outcome = room.pipeline.handle_delivery(
            delivery_id="d1", event=_message("m1", "What is the deploy key?"), actors=ACTORS
        )
        return outcome.opportunities[0].transport, transport, room.host.memory_facts("m1") or {}

    def test_an_action_that_carries_a_secret_never_reaches_the_transport(self) -> None:
        for kind, extra in (("message", {}), ("reply", {"target_event_id": "m1"})):
            with self.subTest(kind):
                result, transport, _facts = self._run(
                    lambda wake: {
                        "kind": kind,
                        "origin_event_id": wake["trigger_event_id"],
                        "text": f"The key is {self.SECRET}",
                        **extra,
                    }
                )
                self.assertEqual([], transport.actions)
                self.assertEqual(
                    TransportResult(
                        "failed", "the action carried a withheld credential or secret; nothing was posted"
                    ),
                    result,
                )

    def test_a_reason_that_carries_a_secret_is_refused_with_its_action(self) -> None:
        result, transport, _facts = self._run(
            lambda wake: {
                "kind": "message",
                "origin_event_id": wake["trigger_event_id"],
                "text": "On it.",
                "why": f"they asked for {self.SECRET}",
            }
        )
        self.assertEqual([], transport.actions)
        self.assertEqual("failed", result.delivery)

    def test_a_clean_action_still_goes_out(self) -> None:
        result, transport, _facts = self._run(
            lambda wake: {"kind": "message", "origin_event_id": wake["trigger_event_id"], "text": "On it."}
        )
        self.assertEqual(["On it."], [action["text"] for action in transport.actions])
        self.assertEqual("sent", result.delivery)

    def test_a_silence_whose_reason_carries_a_secret_keeps_no_reason(self) -> None:
        result, transport, facts = self._run(lambda wake: {"kind": "silence", "why": f"not posting {self.SECRET}"})
        self.assertIsNone(result)
        self.assertEqual([], transport.actions)
        silences = [move for move in facts.get("own_moves", ()) if move.get("kind") == "silence"]
        self.assertEqual(1, len(silences))
        self.assertNotIn("why", silences[0])
        self.assertNotIn(self.SECRET, json.dumps(facts))
        _result, _transport, facts = self._run(lambda wake: {"kind": "silence", "why": "Castor was asked."})
        self.assertEqual(
            ["Castor was asked."],
            [move.get("why") for move in facts.get("own_moves", ()) if move.get("kind") == "silence"],
        )


if __name__ == "__main__":
    unittest.main()
