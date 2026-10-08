"""The Hermes plugin (#94 step 9e): public hooks only, consume and start, final-answer posting.

The first group needs no Hermes: it checks the plugin's own side with a stub
plugin context. The second group runs the plugin inside a real Hermes gateway
(`nunchi.integrations.hermes_plugin_conformance`), loaded from a throwaway
HERMES_HOME with only the model scripted, and skips when Hermes is not
installed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
import unittest

from nunchi.attention import AttentionPolicy, ParticipantProfile
from nunchi.conformance import fixture_attention_model
from nunchi.integrations.hermes_plugin import (
    HERMES_SILENT_ANSWERS,
    SILENCE_MARKER,
    WAKE_MARKER,
    HermesRoomPlugin,
    HermesRoute,
)
from nunchi.integrations.hermes_plugin.plugin import TOKEN_PATTERNS
from nunchi.integrations.hermes_plugin_conformance import ROOM, TURN_USER, hermes_available, room_settings
from nunchi.observation import ObservationLimits, ParticipantBinding
from nunchi.room import Room, RoomSettings
from nunchi.turn import SecretGuard
from nunchi.v2_contracts import validate_canonical_event

BINDING = ParticipantBinding(
    participant_id="vigil",
    actor_id="telegram:user:bot-7",
    platform="telegram",
    room_id=ROOM,
    continuity_scope_id=f"telegram:{ROOM}",
)
PROFILE = ParticipantProfile(
    profile_id="vigil-profile",
    participant_id=BINDING.participant_id,
    actor_id=BINDING.actor_id,
    instructions="Participate directly and preserve uncertainty.",
    provenance="test:offline",
    sha256="0" * 64,
)
ROUTE = HermesRoute(platform="telegram", chat_id=ROOM, turn_user_id=TURN_USER)
REPO = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO / "src" / "nunchi" / "integrations" / "hermes_plugin"
README = REPO / "integrations" / "hermes-plugin" / "README.md"


class _StubContext:
    """What the plugin uses of Hermes's `PluginContext`."""

    def __init__(self, *, accept: bool = True) -> None:
        self.tools: dict[str, dict] = {}
        self.hooks: dict[str, list] = {}
        self.injected: list[tuple[str, dict]] = []
        self.accept = accept

    def register_tool(self, *, name, toolset, schema, handler, **_):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_hook(self, name, callback):
        self.hooks.setdefault(name, []).append(callback)

    def inject_message(self, content, role="user", *, session_key=None, origin=None):
        self.injected.append((content, origin))
        return self.accept

    def has_capability(self, capability):
        return False


class _StubRoom:
    def __init__(self, *, fail: bool = False) -> None:
        self.delivered: list[dict] = []
        self.fail = fail

    def deliver(self, **kwargs):
        if self.fail:
            raise RuntimeError("room unavailable")
        self.delivered.append(kwargs)


def _plugin(room=None) -> HermesRoomPlugin:
    return HermesRoomPlugin(
        profile=PROFILE,
        guard=SecretGuard([]),
        route=ROUTE,
        room_factory=(lambda _plugin: room) if room is not None else None,
    )


class RouteTest(unittest.TestCase):
    def test_section_is_checked(self):
        route = HermesRoute.from_section({"platform": "Telegram", "chat_id": -100, "turn_user_id": "t"})
        self.assertEqual((route.platform, route.chat_id), ("telegram", "-100"))
        for section in ({"chat_id": "1", "turn_user_id": "t"}, {"platform": "telegram", "chat_id": "1",
                        "turn_user_id": "t", "bogus": 1}, "telegram"):
            with self.assertRaises(ValueError):
                HermesRoute.from_section(section)

    def test_origin_and_ids(self):
        route = HermesRoute(platform="discord", chat_id="9", turn_user_id="42", thread_id="77")
        self.assertEqual(route.origin()["thread_id"], "77")
        self.assertEqual(route.origin()["user_id"], "42")
        self.assertTrue(route.holds("discord", {"chat_id": "9", "thread_id": "77"}))
        self.assertFalse(route.holds("discord", {"chat_id": "9", "thread_id": "78"}))
        self.assertFalse(route.holds("telegram", {"chat_id": "9", "thread_id": "77"}))
        self.assertEqual(route.message_id(route.event_id("555")), "555")
        self.assertIsNone(route.message_id("telegram:message:555"))


class RegistrationTest(unittest.TestCase):
    def test_room_tools_and_hooks(self):
        ctx = _StubContext()
        _plugin().register(ctx)
        # Final-answer posting: the answer is the post, so there is no send tool.
        self.assertEqual(set(ctx.tools), {"room_react", "room_context"})
        for entry in ctx.tools.values():
            self.assertEqual(entry["toolset"], "nunchi_room")
            self.assertEqual(entry["schema"]["parameters"]["type"], "object")
            self.assertTrue(entry["schema"]["description"])
        self.assertEqual(
            set(ctx.hooks),
            {"pre_gateway_dispatch", "post_gateway_admission", "pre_llm_call", "transform_tool_result",
             "pre_api_request", "post_api_request", "api_request_error", "transform_llm_output",
             "on_session_end"},
        )

    def test_the_manifest_declares_every_hook_and_tool(self):
        # `hermes plugins validate` compares these with what register() registers.
        ctx = _StubContext()
        _plugin().register(ctx)
        manifest = (PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8")
        self.assertEqual(set(_manifest_list(manifest, "provides_hooks")), set(ctx.hooks))
        self.assertEqual(set(_manifest_list(manifest, "provides_tools")), {"room_react", "room_context"})

    def test_only_the_models_own_words_and_hermess_silence(self):
        # Hermes's own text in place of an answer is never the agent's post
        # (leak audit row 5), and every answer Hermes hides is the agent's
        # silence, never a reply nobody saw (row 6).
        participant = _plugin().participant
        self.assertTrue(participant.model_text)
        self.assertEqual(SILENCE_MARKER, participant.silence_marker)
        self.assertEqual(HERMES_SILENT_ANSWERS, participant.also_silent)

    def test_platform_token_shapes_are_withheld(self):
        guard = SecretGuard([], patterns=TOKEN_PATTERNS)
        for token in ("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawq",
                      "MTA" + "x" * 21 + ".GaBcDe." + "y" * 30):
            self.assertIsNotNone(guard.refusal({"kind": "message", "text": f"the token is {token}"}))


class IngressTest(unittest.TestCase):
    def _admit(self, plugin, **kwargs):
        return asyncio.run(plugin.on_admission(**kwargs))

    def test_a_message_in_the_room_is_consumed_and_observed(self):
        room = _StubRoom()
        plugin = _plugin(room)
        answer = self._admit(plugin, session_key="k", platform="telegram",
                             source={"chat_id": ROOM, "user_id": "u1", "user_name": "Sam"},
                             message_id="100", text="anyone around?")
        self.assertEqual(answer, {"action": "handled"})
        (delivery,) = room.delivered
        event = validate_canonical_event(delivery["event"])
        self.assertEqual(event["id"], "telegram:message:100")
        self.assertEqual(event["author_id"], "telegram:user:u1")
        # Hermes's admission payload does not say whether the author is a bot.
        self.assertEqual(delivery["actors"]["telegram:user:u1"]["kind"], "unknown")

    def _dispatch(self, plugin, message_id, *, chat_id=ROOM, **fields):
        source = SimpleNamespace(platform=SimpleNamespace(value="telegram"), chat_id=chat_id, thread_id=None)
        self.assertIsNone(plugin.on_dispatch(event=SimpleNamespace(source=source, message_id=message_id, **fields)))

    def test_what_hermes_knew_at_dispatch_reaches_the_room(self):
        room = _StubRoom()
        plugin = _plugin(room)
        raw = SimpleNamespace(
            mentions=[SimpleNamespace(id="bot-7"), SimpleNamespace(id="u2")],
            mention_everyone=False,
            author=SimpleNamespace(bot=True),
        )
        sent = datetime(2026, 10, 7, 21, 5, 3, 250000, tzinfo=timezone.utc)
        self._dispatch(plugin, "101", reply_to_message_id="100", timestamp=sent, raw_message=raw)
        self._admit(plugin, platform="telegram", source={"chat_id": ROOM, "user_id": "u3", "user_name": "CI"},
                    message_id="101", text="can you look?")
        (delivery,) = room.delivered
        event = validate_canonical_event(delivery["event"])
        # Hermes took the bot's own mention out of the text; the mention is kept.
        self.assertEqual(["telegram:user:bot-7", "telegram:user:u2"], event["mentioned_actor_ids"])
        self.assertEqual("telegram:message:100", event["reply_to_event_id"])
        self.assertEqual("2026-10-07T21:05:03.250Z", event["timestamp"])
        self.assertEqual("bot", delivery["actors"]["telegram:user:u3"]["kind"])

    def test_a_message_meant_for_the_bot_mentions_it(self):
        room = _StubRoom()
        plugin = _plugin(room)
        class Placeholder:
            """What the plugin host gets for a live object (Hermes's `Opaque`)."""

            def __getattr__(self, name):
                raise AttributeError(f"{name} is not available inside the plugin host")

        # Under plugins.isolation: host the platform's message is a placeholder.
        self._dispatch(plugin, "102", reply_expected=True, reply_to_message_id="101", raw_message=Placeholder())
        self._admit(plugin, platform="telegram", source={"chat_id": ROOM, "user_id": "u1"},
                    message_id="102", text="and this one?")
        (delivery,) = room.delivered
        self.assertEqual([PROFILE.actor_id], delivery["event"]["mentioned_actor_ids"])
        self.assertEqual("telegram:message:101", delivery["event"]["reply_to_event_id"])
        self.assertEqual("unknown", delivery["actors"]["telegram:user:u1"]["kind"])

    def test_messages_elsewhere_are_not_noted(self):
        plugin = _plugin(_StubRoom())
        self._dispatch(plugin, "103", chat_id="elsewhere", reply_to_message_id="9")
        self.assertEqual({}, dict(plugin._noted))

    def test_other_chats_are_left_to_hermes(self):
        room = _StubRoom()
        answer = self._admit(_plugin(room), platform="telegram", source={"chat_id": "elsewhere"},
                             message_id="1", text="hi")
        self.assertIsNone(answer)
        self.assertEqual(room.delivered, [])

    def test_a_room_failure_still_consumes(self):
        # Fail closed: Hermes answering the person directly would bypass the room.
        with self.assertLogs("nunchi.hermes_plugin", level="ERROR"):
            answer = self._admit(_plugin(_StubRoom(fail=True)), platform="telegram",
                                 source={"chat_id": ROOM, "user_id": "u1"}, message_id="1", text="hi")
        self.assertEqual(answer, {"action": "handled"})


def _manifest_list(manifest: str, key: str) -> list[str]:
    """One list from plugin.yaml (a block of ``  - item`` lines)."""

    block = re.search(rf"^{key}:\n((?:  - .+\n)+)", manifest, re.M)
    return [line[4:].strip() for line in block.group(1).splitlines()] if block else []


class RunTest(unittest.TestCase):
    def test_only_nunchi_runs_are_touched(self):
        plugin = _plugin()
        plugin.on_pre_llm_call(session_id="s", task_id="s", turn_id="t1", user_message="hello")
        self.assertIsNone(plugin.on_final_answer(response_text="hi", turn_id="t1", session_id="s"))

    def test_a_stale_nunchi_run_is_silenced(self):
        # No turn is open: a run that carries a Nunchi marker may not post.
        plugin = _plugin()
        plugin.on_pre_llm_call(session_id="s", task_id="s", turn_id="t1",
                               user_message=WAKE_MARKER.format("stale") + "\nold turn")
        self.assertEqual(plugin.on_final_answer(response_text="late draft", turn_id="t1", session_id="s"),
                         SILENCE_MARKER)
        plugin.on_run_end(turn_id="t1", completed=True)
        self.assertIsNone(plugin.participant.active)

    def test_tools_outside_a_bound_run_post_nothing(self):
        ctx = _StubContext()
        _plugin().register(ctx)
        answer = json.loads(ctx.tools["room_context"]["handler"]({"direction": "before"}, task_id="x"))
        self.assertIn("error", answer)


# -- inside a real Hermes gateway -----------------------------------------------------------------


def _room_factory(state: Path):
    settings = RoomSettings(
        binding=BINDING,
        profile=PROFILE,
        attention=AttentionPolicy(),
        attention_model=None,
        limits=ObservationLimits(),
        state_directory=state,
    )

    def build(plugin):
        return Room(
            settings,
            participant=plugin.participant,
            transport=plugin.transport(),
            event_visibility={"message": "live-only", "reaction": "unavailable", "membership": "unavailable"},
            state_prefix="hermes-plugin-",
            attention_model=fixture_attention_model("WAKE"),
        )

    return build


def _user_text(request) -> str:
    return next(m["content"] for m in reversed(request["messages"]) if m["role"] == "user")


def _tool_text(request) -> str:
    return next(m["content"] for m in reversed(request["messages"]) if m["role"] == "tool")


def _wake_in(text: str) -> dict:
    """The library's wake inside a turn's text."""

    start = text.index("<nunchi_participant_turn_v1>") + len("<nunchi_participant_turn_v1>")
    return json.loads(text[start:text.index("</nunchi_participant_turn_v1>")])["participant_turn"]["wake"]


def _record_turns(harness) -> list[tuple[str, str]]:
    """How each of the agent's turns ends, as the library's host gets it: ("failed", why),
    ("silence", why) or (the action's kind, its text)."""

    outcomes: list[tuple[str, str]] = []
    participant = harness.plugin.participant
    run = participant.run_protocol

    def recorded(**kwargs):
        try:
            action = run(**kwargs)
        except Exception as exc:
            outcomes.append(("failed", str(exc)))
            raise
        action = action or {"kind": "silence"}
        outcomes.append((action["kind"], action.get("text") or action.get("why") or ""))
        return action

    participant.run_protocol = recorded
    return outcomes


def _own_moves(harness, event_id: str = "telegram:message:100") -> list[tuple]:
    facts = harness.plugin.room.host.memory_facts(event_id) or {}
    return [(move.get("kind"), move.get("text") or move.get("why")) for move in facts.get("own_moves", ())]


def _readme_settings() -> dict:
    """The README's "Hermes setup the room needs" YAML block, as Hermes's own reader reads it."""

    try:
        if not hermes_available():
            raise ImportError
        from nunchi.integrations.hermes_plugin_conformance import isolate

        isolate()
        import hermes_yaml as yaml  # what Hermes reads its config.yaml with
    except ImportError:
        try:
            import yaml
        except ImportError:
            raise unittest.SkipTest("needs Hermes or PyYAML to read YAML") from None
    text = README.read_text(encoding="utf-8")
    section = text[text.index("## Hermes setup the room needs"):]
    block = re.search(r"```yaml\n(.*?)```", section, re.S)
    return yaml.safe_load(block.group(1))


class ReadmeTest(unittest.TestCase):
    def test_the_readme_room_setup_is_what_the_kit_tests(self):
        settings = _readme_settings()
        plugins = settings.pop("plugins")
        self.assertEqual(room_settings("telegram"), settings)
        self.assertEqual(["nunchi-room"], plugins["enabled"])
        self.assertIs(True, plugins["entries"]["nunchi-room"]["allow_gateway_injection"])


class HostModelAttentionTest(unittest.TestCase):
    """Attention on Hermes's own model (`ctx.llm`), instead of a configured route."""

    class _Llm:
        def __init__(self, error=None):
            self.calls = []
            self.error = error

        def complete_structured(self, **kwargs):
            self.calls.append(kwargs)
            if self.error is not None:
                raise self.error
            return type("Result", (), {"provider": "example", "model": "small", "parsed": {"ok": True}})()

    def _config(self, directory: Path) -> dict:
        import hashlib

        raw = json.dumps({
            "profile_id": PROFILE.profile_id,
            "participant_id": PROFILE.participant_id,
            "actor_id": PROFILE.actor_id,
            "instructions": PROFILE.instructions,
            "provenance": "test",
        }).encode()
        (directory / "profile.json").write_bytes(raw)
        return {
            "schema_version": 2,
            "binding": {
                "participant_id": BINDING.participant_id,
                "actor_id": BINDING.actor_id,
                "platform": "telegram",
                "room_id": ROOM,
                "continuity_scope_id": BINDING.continuity_scope_id,
            },
            "profile": {"path": str(directory / "profile.json"), "sha256": hashlib.sha256(raw).hexdigest()},
            "attention": {
                "policy": {"preattention_enabled": True},
                "model": {"kind": "hermes-host", "provider": "example", "model": "small"},
            },
            "limits": {},
            "state_directory": str(directory / "state"),
            "hermes": {"platform": "telegram", "chat_id": ROOM, "turn_user_id": TURN_USER},
        }

    def _room(self, llm):
        from nunchi.integrations.hermes_plugin import build_plugin

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        plugin = build_plugin(self._config(Path(directory.name)))
        context = _StubContext()
        context.llm = llm
        plugin.register(context)
        return plugin._ensure_room()

    def test_attention_asks_hermes_for_the_configured_model(self):
        from nunchi.attention import HostStructuredAttentionModel

        llm = self._Llm()
        room = self._room(llm)
        model = room.attention.model
        self.assertIsInstance(model, HostStructuredAttentionModel)
        self.assertEqual({"ok": True}, dict(model.judge(instructions="i", projection={}, timeout_seconds=5)))
        self.assertEqual(("example", "small"), (llm.calls[0]["provider"], llm.calls[0]["model"]))

    def test_a_hermes_refusal_says_how_to_allow_the_model(self):
        from nunchi.attention import HostAttentionPermissionError

        room = self._room(self._Llm(error=PermissionError("not allowed")))
        with self.assertRaises(HostAttentionPermissionError) as raised:
            room.attention.model.judge(instructions="i", projection={}, timeout_seconds=5)
        self.assertIn("plugins.entries.nunchi-room.llm", str(raised.exception))


class PluginGuardTest(unittest.TestCase):
    """The plugin's one guard: the agent's turns and the room refuse the same secrets."""

    def _room(self, environ, **hermes):
        from unittest import mock

        from nunchi.integrations.hermes_plugin import build_plugin

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        config = HostModelAttentionTest._config(self, Path(directory.name))
        config["attention"] = {
            "policy": {"preattention_enabled": False},
            "model": {"model": "m", "base_url": "http://127.0.0.1:9/v1", "api_key_env": "HERMES_TEST_ATTENTION_KEY"},
        }
        config["hermes"].update(hermes)
        with mock.patch.dict("os.environ", environ):
            plugin = build_plugin(config)
        plugin.register(_StubContext())
        return plugin, plugin._ensure_room()

    @staticmethod
    def _refuses(guard, text):
        return guard.refusal({"kind": "message", "text": text}) is not None

    def test_the_turns_and_the_room_refuse_the_attention_key_platform_tokens_and_their_shapes(self):
        plugin, room = self._room(
            {"HERMES_TEST_ATTENTION_KEY": "a-hermes-attention-route-key", "TELEGRAM_BOT_TOKEN": "held-telegram-bot-token"}
        )
        self.assertIs(plugin.participant.guard, room.guard)
        self.assertIs(room.guard, room.host.guard)
        for text in (
            "a-hermes-attention-route-key",
            "held-telegram-bot-token",
            "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawq",
            "MTA" + "x" * 21 + ".GaBcDe." + "y" * 30,
            # Built in parts so the fake token never appears whole in the source.
            "xox" + "b-123456789012-1234567890123-" + "AbCdEfGhIjKlMnOpQrStUvWx",
        ):
            with self.subTest(text=text[:12]):
                self.assertTrue(self._refuses(room.guard, text))
        self.assertFalse(self._refuses(room.guard, "On it, xoxo"))

    def test_the_sections_own_names_replace_the_default_platform_tokens(self):
        _plugin, room = self._room(
            {"TELEGRAM_BOT_TOKEN": "held-telegram-bot-token", "MY_HERMES_TOKEN": "my-own-withheld-value"},
            withheld_env=["MY_HERMES_TOKEN"],
        )
        self.assertTrue(self._refuses(room.guard, "my-own-withheld-value"))
        self.assertFalse(self._refuses(room.guard, "held-telegram-bot-token"))


@unittest.skipUnless(hermes_available(), "requires an installed Hermes (hermes-agent)")
class HermesGatewayTest(unittest.TestCase):
    """The plugin in a real Hermes gateway, with only the model scripted."""

    def _harness(self, **kwargs):
        from nunchi.integrations.hermes_plugin_conformance import HermesHarness

        state = Path(tempfile.mkdtemp(prefix="nunchi-hermes-plugin-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(state, ignore_errors=True))
        kwargs.setdefault("room_factory", _room_factory(state))
        harness = HermesHarness(profile=PROFILE, guard=SecretGuard(["withheld-secret-value-123"]), **kwargs)
        self.addCleanup(harness.close)
        harness.state = state
        return harness

    def test_kit_final_answer_scenarios(self):
        from nunchi import turn_conformance as kit
        from nunchi.integrations.hermes_plugin_conformance import HermesKitIntegration

        for name, scenario in kit.SCENARIOS.items():
            if scenario.posting != "final-answer":
                continue
            with self.subTest(name):
                result = kit.run_scenario(name, HermesKitIntegration())
                self.assertEqual(result["status"], "pass", result.get("failures"))

    def test_the_room_sees_hermess_reply_target_time_and_mentions(self):
        harness = self._harness()
        sent = datetime(2026, 10, 7, 21, 5, 3, tzinfo=timezone.utc)
        harness.person_says(
            "Can someone look at the failing deploy?",
            message_id="101",
            reply_to_message_id="100",
            timestamp=sent,
            raw_message=SimpleNamespace(mentions=[SimpleNamespace(id="bot-7")], author=SimpleNamespace(bot=False)),
        )
        self.assertTrue(harness.wait_observed("telegram:message:101"))
        (event,) = [
            event for event in harness.plugin.room.observation.retained_events()
            if event["id"] == "telegram:message:101"
        ]
        self.assertEqual(
            (["telegram:user:bot-7"], "telegram:message:100", "2026-10-07T21:05:03.000Z"),
            (event["mentioned_actor_ids"], event["reply_to_event_id"], event["timestamp"]),
        )

    def test_a_person_speaks_and_the_agent_answers_through_the_room(self):
        harness = self._harness()
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        request = harness.model.latest()
        # The run is the plugin's injected turn, not Hermes answering the person.
        self.assertTrue(_user_text(request).startswith('<nunchi_wake id="'))
        self.assertIn("failing deploy", _user_text(request))
        harness.model.reply({"text": "On it."})
        self.assertTrue(harness.settle())
        self.assertEqual(harness.gateway.adapter.sent, [(ROOM, "On it.")])
        self.assertEqual(harness.model.count(), 1)

    def _next_turn_after(self, answer="On it."):
        """The agent answers ``answer`` to message 100; the wake of its next turn, and what the room got."""

        harness = self._harness()
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"text": answer})
        self.assertTrue(harness.settle())
        sent = list(harness.gateway.adapter.sent)
        harness.person_says("Thanks! Ping me when it's green.", message_id="102")
        self.assertTrue(harness.wait_for_requests(2))
        text = _user_text(harness.model.latest())
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        return _wake_in(text), sent

    def _next_turn_after_a_delivered_reply(self):
        return self._next_turn_after("On it.")[0]

    def test_the_delivered_message_is_in_the_agents_memory(self):
        # Hermes drops its agent's own messages before any plugin hook; the
        # library puts what HarnessDelivery committed into the room log, as a
        # reply to the message the turn was about.
        wake = self._next_turn_after_a_delivered_reply()
        moves = wake.get("memory", {}).get("own_moves", [])
        self.assertIn(
            ("reply", "telegram:message:100", "On it."),
            [(move.get("kind"), move.get("about_event_id"), move.get("text")) for move in moves],
        )

    def test_the_room_counts_the_delivered_message(self):
        # Hermes never shows the delivered message, so the library puts it into
        # the room log: the question it answered has a response, and the
        # agent's own share of the conversation (pace) counts it.
        wake = self._next_turn_after_a_delivered_reply()
        self.assertEqual(wake["pace"]["own_messages"], 1)
        thread = next(item for item in wake["memory"]["threads"] if item["event_id"] == "telegram:message:100")
        self.assertTrue(thread["responses"])

    def test_silence_sends_nothing(self):
        harness = self._harness()
        harness.person_says("Castor, can you check this?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"text": f"<thinking>Castor was asked, not me.</thinking>\n{SILENCE_MARKER}"})
        self.assertTrue(harness.settle())
        self.assertEqual(harness.gateway.adapter.sent, [])
        facts = harness.plugin.room.host.memory_facts("telegram:message:100") or {}
        reasons = [move.get("why") for move in facts.get("own_moves", ()) if move.get("kind") == "silence"]
        self.assertEqual(reasons, ["Castor was asked, not me."])

    # -- only what the agent chose reaches the room (leak audit rows 3, 5, 6) -------------

    def test_hermess_other_silent_answers_are_remembered_as_silence(self):
        # Hermes hides NO_REPLY and a marker in markdown; the library must
        # remember silence, not a reply nobody saw (leak audit row 6). A marker
        # in backticks, which Hermes would post, is silence too.
        for answer in ("NO_REPLY", "**[SILENT]**", "`[SILENT]`"):
            with self.subTest(answer=answer):
                wake, sent = self._next_turn_after(f"<thinking>Castor has this one.</thinking>\n{answer}")
                self.assertEqual([], sent)
                moves = [(move.get("kind"), move.get("about_event_id"), move.get("why"))
                         for move in wake["memory"]["own_moves"]]
                self.assertEqual([("silence", "telegram:message:100", "Castor has this one.")], moves)
                self.assertEqual(0, wake["pace"]["own_messages"])
                thread = next(item for item in wake["memory"]["threads"]
                              if item["event_id"] == "telegram:message:100")
                self.assertEqual([], thread["responses"])

    def test_a_post_that_only_looks_like_silence_is_delivered_and_remembered(self):
        post = "No reply from Bob yet. Want me to ping him?"
        wake, sent = self._next_turn_after(post)
        self.assertEqual([(ROOM, post)], sent)
        self.assertIn(("reply", post), [(move.get("kind"), move.get("text")) for move in wake["memory"]["own_moves"]])
        self.assertEqual(1, wake["pace"]["own_messages"])

    def _after_a_failed_file_edit(self, harness, answer):
        # The model's edit fails (the file does not exist), then it answers.
        missing = harness.state / "does-not-exist.txt"
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"tool": "patch", "arguments": {
            "mode": "replace", "path": str(missing), "old_string": "foo", "new_string": "bar"}})
        self.assertTrue(harness.wait_for_requests(2))
        self.assertIn("error", _tool_text(harness.model.latest()).lower())
        harness.model.reply({"text": answer})
        self.assertTrue(harness.settle())
        return harness.gateway.adapter.sent

    def test_the_room_setup_adds_nothing_after_a_failed_file_edit(self):
        self.assertEqual([], self._after_a_failed_file_edit(self._harness(), SILENCE_MARKER))
        harness = self._harness()
        self.assertEqual([(ROOM, "On it.")], self._after_a_failed_file_edit(harness, "On it."))
        self.assertEqual([("reply", "On it.")], _own_moves(harness))

    def test_hermes_defaults_add_a_footer_the_library_never_committed(self):
        # Hermes's default display.file_mutation_verifier appends a footer
        # (with local file paths) after the output hook: the room sees more
        # than the agent's post, and more than the library remembers. Only the
        # top-level setting stops it (integrations/hermes-plugin/README.md).
        harness = self._harness(extra_config={"display": {"file_mutation_verifier": True}})
        ((chat, text),) = self._after_a_failed_file_edit(harness, "On it.")
        self.assertTrue(text.startswith("On it.") and text != "On it.", text)
        self.assertEqual([("reply", "On it.")], _own_moves(harness))

    def test_an_empty_model_is_never_the_agents_reply(self):
        # The model answers nothing, every time Hermes asks. Hermes retries,
        # then hands the plugin "(empty)": the turn fails, the room gets
        # nothing, and the agent remembers no reply (leak audit rows 3 and 5).
        harness = self._harness()
        turns = _record_turns(harness)
        harness.model.on_request = lambda: harness.model.reply({"text": ""})
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        self.assertTrue(harness.settle(timeout=90))
        self.assertGreaterEqual(harness.model.count(), 2)  # Hermes retried
        self.assertEqual([], harness.gateway.adapter.sent)
        self.assertEqual([], _own_moves(harness))
        ((kind, why),) = turns
        self.assertEqual("failed", kind)
        self.assertIn('"(empty)" came from the harness', why)

    def test_hermes_defaults_explain_an_empty_model_in_the_room(self):
        # Without the room setup Hermes posts its retry lines, and appends its
        # explanation even to the plugin's silence marker; the library still
        # commits and remembers nothing.
        harness = self._harness(
            display={"streaming": False, "tool_progress": "off", "interim_assistant_messages": False},
            extra_config={"display": {"turn_completion_explainer": True}},
        )
        turns = _record_turns(harness)
        harness.model.on_request = lambda: harness.model.reply({"text": ""})
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        self.assertTrue(harness.settle(timeout=90))
        sent = [text for _, text in harness.gateway.adapter.sent]
        self.assertTrue(sent[-1].startswith(f"{SILENCE_MARKER}\n\n"), sent)
        self.assertGreater(len(sent), 1, sent)
        self.assertEqual([], _own_moves(harness))
        self.assertEqual(["failed"], [kind for kind, _ in turns])

    def test_hermess_iteration_limit_text_is_never_the_agents_reply(self):
        # With a budget of one model call, the model writes beside a tool call
        # and Hermes ends the run with "I reached the iteration limit and
        # couldn't generate a summary.": not the model's words.
        harness = self._harness(agent={"max_turns": 1})
        turns = _record_turns(harness)
        tool = {"tool": "room_context", "arguments": {"direction": "before"}}
        first = dict(tool, text="Let me check the deploy logs first.")
        harness.model.on_request = lambda: harness.model.reply(first if harness.model.count() == 1 else tool)
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        self.assertTrue(harness.settle(timeout=60))
        self.assertEqual([], harness.gateway.adapter.sent)
        self.assertEqual([], _own_moves(harness))
        ((kind, why),) = turns
        self.assertEqual("failed", kind)
        self.assertIn("iteration limit", why)
        self.assertIn("is not what its model wrote", why)

    def test_the_output_hook_fails_closed(self):
        # Hermes posts the raw draft when an output hook raises.
        harness = self._harness()
        turns = _record_turns(harness)

        def broken(**_):
            raise RuntimeError("conformance: the library failed")

        harness.plugin.participant.finish = broken
        with self.assertLogs("nunchi.hermes_plugin", level="ERROR"):
            harness.person_says("Can someone look at the failing deploy?", message_id="100")
            self.assertTrue(harness.wait_for_requests(1))
            harness.model.reply({"text": "On it."})
            self.assertTrue(harness.settle())
        self.assertEqual([], harness.gateway.adapter.sent)
        self.assertEqual(["failed"], [kind for kind, _ in turns])

    def test_a_provider_refusal_ends_the_turn_promptly(self):
        # Hermes runs no output or end hook when the provider refuses for
        # good. The plugin ends the turn after a short wait for Hermes to
        # recover, instead of the library's deadline (300 s).
        harness = self._harness()
        turns = _record_turns(harness)
        harness.model.on_request = lambda: harness.model.reply(
            {"status": 400, "error": "conformance: the provider refused the request"})
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        refused = time.monotonic()
        self.assertTrue(harness.settle(timeout=30))
        self.assertLess(time.monotonic() - refused, 15)
        ((kind, why),) = turns
        self.assertEqual("failed", kind)
        self.assertIn("the model provider failed (400", why)
        self.assertEqual([], _own_moves(harness))
        # Known gap: Hermes still posts its failed-turn notice, which no hook
        # or setting stops (README, Known gaps). Its "❌" status line is muted.
        ((chat, notice),) = harness.gateway.adapter.sent
        self.assertFalse(notice.startswith("❌"), notice)

    def test_a_provider_failure_hermes_recovers_from_still_delivers(self):
        # Hermes reports the refusal before it tries its fallback provider.
        # The fallback answers after the plugin's wait would have run out: the
        # new model request keeps the turn open, and the answer is posted.
        harness = self._harness(failure_grace_seconds=2.0)
        turns = _record_turns(harness)
        config = harness.gateway.home / "config.yaml"
        settings = json.loads(config.read_text(encoding="utf-8"))
        settings["fallback_providers"] = [{"provider": "custom", "model": "conformance/fallback",
                                           "base_url": harness.model.base_url, "api_key": "sk-local-conformance"}]
        config.write_text(json.dumps(settings), encoding="utf-8")  # Hermes reads it for each run

        def on_request():
            if harness.model.count() == 1:
                harness.model.reply({"status": 400, "error": "conformance: the provider refused the request"})
            else:
                __import__("threading").Timer(4.0, harness.model.reply, args=({"text": "On it."},)).start()

        harness.model.on_request = on_request
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(2))
        self.assertEqual("conformance/fallback", harness.model.latest()["model"])
        self.assertTrue(harness.settle(timeout=30))
        self.assertEqual([(ROOM, "On it.")], harness.gateway.adapter.sent)
        self.assertEqual([("message", "On it.")], turns)

    def _offered(self, harness):
        harness.person_says("Castor, can you check this?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        offered = {tool["function"]["name"] for tool in harness.model.latest()["tools"]}
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        return offered

    def test_the_room_setup_offers_no_clarify_form(self):
        # Hermes's default clarify tool posts a question form that nobody in
        # the room is meant to answer; the room setup disables its toolset.
        self.assertIn("clarify", self._offered(self._harness(extra_config={"agent": {"disabled_toolsets": []}})))
        self.assertNotIn("clarify", self._offered(self._harness()))

    def test_the_room_setup_sends_no_typing(self):
        harness = self._harness()
        self.assertFalse(harness.gateway.adapter.config.typing_indicator)
        harness.person_says("Castor, can you check this?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        time.sleep(2.5)  # Hermes refreshes typing every 2 s while a run is on
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        self.assertEqual([], harness.gateway.adapter.typing)

    def test_hermes_defaults_show_typing_for_a_turn_that_stays_silent(self):
        harness = self._harness(extra_config={"telegram": {"typing_indicator": True}})
        harness.person_says("Castor, can you check this?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        time.sleep(2.5)
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        self.assertEqual([], harness.gateway.adapter.sent)
        self.assertTrue(harness.gateway.adapter.typing)

    def test_steering_shows_a_message_that_arrives_mid_turn(self):
        harness = self._harness()
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.person_says("Please use the staging box.", message_id="101", user_id="u2", user_name="Kim")
        self.assertTrue(harness.wait_observed("telegram:message:101"))
        harness.model.reply({"tool": "room_context", "arguments": {"direction": "before"}})
        self.assertTrue(harness.wait_for_requests(2))
        result = _tool_text(harness.model.latest())
        self.assertIn("Room update: 1 new message(s)", result)
        self.assertIn("staging box", result)
        harness.model.reply({"text": "Will do, on staging."})
        # The library then catches up on the message that arrived mid-turn, in a
        # turn of its own (the same for every harness).
        self.assertTrue(harness.wait_for_requests(3))
        catch_up = _user_text(harness.model.latest())
        self.assertIn('"trigger_event_id":"telegram:message:101"', catch_up)
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        # Shown by steering, the message no longer held the answer.
        self.assertEqual(harness.gateway.adapter.sent, [(ROOM, "Will do, on staging.")])

    def test_look_again_starts_a_fresh_run_with_the_draft(self):
        harness = self._harness()
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.person_says("Actually, I found it myself.", message_id="101", user_id="u2", user_name="Kim")
        self.assertTrue(harness.wait_observed("telegram:message:101"))
        harness.model.reply({"text": "On it."})
        self.assertTrue(harness.wait_for_requests(2))
        fresh = _user_text(harness.model.latest())
        self.assertIn("Not posted yet", fresh)
        self.assertIn('"On it."', fresh)
        harness.model.reply({"text": SILENCE_MARKER})
        # The catch-up turn for the message that arrived mid-turn.
        self.assertTrue(harness.wait_for_requests(3))
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        self.assertEqual(harness.gateway.adapter.sent, [])
        # Two Hermes runs in the first turn (the draft, then the fresh run), one in the next.
        self.assertEqual(harness.model.count(), 3)

    def test_a_message_in_another_chat_is_left_to_hermes(self):
        harness = self._harness()
        harness.gateway.run(_person_elsewhere(harness.gateway))
        self.assertTrue(harness.wait_for_requests(1))
        self.assertFalse(_user_text(harness.model.latest()).startswith("<nunchi_wake"))
        harness.model.reply({"text": "Hello there."})
        self.assertTrue(harness.settle())
        # Hermes may first post its own onboarding notice in a new chat.
        self.assertEqual(harness.gateway.adapter.sent[-1], ("elsewhere", "Hello there."))
        self.assertNotIn(ROOM, [chat for chat, _ in harness.gateway.adapter.sent])

    def test_a_turn_hermes_never_runs_fails_instead_of_hanging(self):
        # The injected turns' identity is not an allowed user: Hermes accepts the
        # injection and drops it at dispatch, without telling the plugin.
        harness = self._harness(allowed_users="u1,u2", start_timeout_seconds=2.0)
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.settle(timeout=15))
        self.assertEqual(harness.model.count(), 0)
        self.assertEqual(harness.gateway.adapter.sent, [])
        self.assertIsNone(harness.plugin.participant.active)

    def _text_beside_a_tool_call(self, harness):
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"tool": "room_context", "text": "Let me look at the room first.",
                             "arguments": {"direction": "before"}})
        self.assertTrue(harness.wait_for_requests(2))
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        return harness.gateway.adapter.sent

    def test_the_room_setup_keeps_interim_text_out_of_the_room(self):
        self.assertEqual(self._text_beside_a_tool_call(self._harness()), [])

    def test_hermes_defaults_post_interim_text_without_the_library(self):
        # Hermes's own display default posts text the model writes beside a tool
        # call, before any final answer: it never reaches the library's commit.
        # No plugin hook can stop it, so the room needs the operator setting
        # (integrations/hermes-plugin/README.md).
        from nunchi.integrations.hermes_plugin_conformance import ROOM_DISPLAY

        defaults = {key: value for key, value in ROOM_DISPLAY.items() if key in ("streaming", "tool_progress")}
        sent = self._text_beside_a_tool_call(self._harness(display=defaults))
        self.assertEqual(sent, [(ROOM, "Let me look at the room first.")])

    def test_a_reaction_is_the_agents_own_through_platform_actions(self):
        harness = self._harness(platform_actions=True)
        harness.person_says("Deploy is green again.", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        self.assertIn("room_react", _user_text(harness.model.latest()))
        harness.model.reply({"tool": "room_react",
                             "arguments": {"target_event_id": "telegram:message:100", "reaction": "👍"}})
        self.assertTrue(harness.wait_for_requests(2))
        self.assertIn("Done", json.loads(_tool_text(harness.model.latest()))["result"])
        # One room action per turn: a final answer after the reaction posts nothing.
        harness.model.reply({"text": "Nice."})
        self.assertTrue(harness.settle())
        self.assertEqual(harness.gateway.adapter.reactions, [(ROOM, "100", "👍")])
        self.assertEqual(harness.gateway.adapter.sent, [])

    def test_without_the_grant_the_agent_is_not_offered_reactions(self):
        harness = self._harness()
        harness.person_says("Deploy is green again.", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        self.assertNotIn("room_react", _user_text(harness.model.latest()))
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())

    def test_room_tools_through_the_tool_search_bridge(self):
        # Hermes's default defers plugin tools behind tool_search / tool_call.
        harness = self._harness(tool_search="auto")
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        offered = {tool["function"]["name"] for tool in harness.model.latest()["tools"]}
        self.assertNotIn("room_context", offered)
        self.assertIn("tool_call", offered)
        harness.model.reply({"tool": "tool_call", "arguments": {
            "calls": [{"name": "room_context", "arguments": {"direction": "before"}}]}})
        self.assertTrue(harness.wait_for_requests(2))
        # Hermes unwrapped the bridge and the room view answered for this run.
        answer = json.loads(_tool_text(harness.model.latest()))
        self.assertIn('"direction": "before"', answer["result"])
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())


@unittest.skipUnless(hermes_available(), "requires an installed Hermes (hermes-agent)")
class HermesSilenceParityTest(unittest.TestCase):
    """The plugin knows every answer the pinned Hermes hides (leak audit row 6)."""

    @classmethod
    def setUpClass(cls):
        from nunchi.integrations.hermes_plugin_conformance import isolate

        isolate()

    def test_the_plugin_lists_every_silent_answer_hermes_has(self):
        from gateway.response_filters import LIVE_GATEWAY_SILENT_MARKERS

        self.assertEqual(set(LIVE_GATEWAY_SILENT_MARKERS), {SILENCE_MARKER, *HERMES_SILENT_ANSWERS})

    def test_whatever_hermes_hides_the_library_remembers_as_silence(self):
        from copy import deepcopy

        from gateway.response_filters import LIVE_GATEWAY_SILENT_MARKERS, is_intentional_silence_response
        from nunchi.participant_model import build_participant_turn_request
        from nunchi.turn import Turn
        from tests.v2.test_claude_code import OPPORTUNITY, test_wake
        from tests.v2.test_turn import Room as Expander

        participant = _plugin().participant
        hidden = 0
        for marker in sorted(LIVE_GATEWAY_SILENT_MARKERS):
            for form in ("{}", "{}.", "**{}**", "*{}*", "_{}_", "({})", '"{}"', "  {}  ", "{}!", "-{}-"):
                answer = form.format(marker)
                if not is_intentional_silence_response(answer):
                    continue
                hidden += 1
                turn = Turn(
                    profile=PROFILE,
                    request=build_participant_turn_request(test_wake(), deepcopy(OPPORTUNITY)),
                    tool_names={"react": "room_react", "context": "room_context"},
                    expand=Expander().expand,
                    result_wait_seconds=2,
                    silence_marker=participant.silence_marker,
                    also_silent=participant.also_silent,
                )
                with self.subTest(answer=answer):
                    self.assertEqual("silent", turn.decide(answer).kind)
        self.assertGreater(hidden, len(LIVE_GATEWAY_SILENT_MARKERS))


@unittest.skipUnless(hermes_available(), "requires an installed Hermes (hermes-agent)")
class HermesInstalledPluginTest(unittest.TestCase):
    """The shipped plugin directory, loaded by Hermes with its own register() and a Nunchi config."""

    def test_the_plugin_directory_runs_a_turn_from_its_config(self):
        self._run_from_config("in_process")

    def test_the_plugin_runs_out_of_process_in_hermess_plugin_host(self):
        # harness-contract.md, parity table: "also under plugins.isolation: host (to verify)".
        self._run_from_config("host")

    def _run_from_config(self, isolation):
        import hashlib
        import shutil

        import nunchi.integrations.hermes_plugin as package
        from nunchi.integrations.hermes_plugin_conformance import HermesGateway, ScriptedModel

        directory = Path(tempfile.mkdtemp(prefix="nunchi-hermes-config-test-"))
        self.addCleanup(shutil.rmtree, directory, True)
        profile = directory / "vigil.profile.json"
        profile.write_text(json.dumps({
            "profile_id": PROFILE.profile_id, "participant_id": PROFILE.participant_id,
            "actor_id": PROFILE.actor_id, "instructions": PROFILE.instructions, "provenance": "test:offline",
        }), encoding="utf-8")
        config = directory / "nunchi.json"
        config.write_text(json.dumps({
            "schema_version": 2,
            "binding": {"participant_id": BINDING.participant_id, "actor_id": BINDING.actor_id,
                        "platform": "telegram", "room_id": ROOM, "continuity_scope_id": BINDING.continuity_scope_id,
                        "names": ["Vigil"]},
            "profile": {"path": str(profile), "sha256": hashlib.sha256(profile.read_bytes()).hexdigest()},
            # No attention route, so no credentials: every message reaches the agent.
            "attention": {"policy": {"preattention_enabled": False}, "model": None},
            "limits": {},
            "state_directory": str(directory / "state"),
            "hermes": {"platform": "telegram", "chat_id": ROOM, "turn_user_id": TURN_USER},
        }), encoding="utf-8")
        model = ScriptedModel()
        self.addCleanup(model.close)
        gateway = HermesGateway(model=model, plugin_source=Path(package.__file__).parent,
                                plugin_settings={"config_path": str(config)},
                                extra_config={"plugins": {"isolation": isolation}})
        self.addCleanup(gateway.close)
        gateway.run(gateway.person_says("Can someone look at the failing deploy?", message_id="100"))
        for _ in range(500):
            if model.count():
                break
            __import__("time").sleep(0.02)
        self.assertEqual(model.count(), 1)
        self.assertTrue(_user_text(model.latest()).startswith('<nunchi_wake id="'))
        offered = {tool["function"]["name"] for tool in model.latest()["tools"]}
        self.assertTrue({"room_context"} <= offered)
        model.reply({"text": "On it."})
        for _ in range(500):
            if gateway.adapter.sent and gateway.idle():
                break
            __import__("time").sleep(0.02)
        self.assertEqual(gateway.adapter.sent, [(ROOM, "On it.")])
        self.assertTrue((directory / "state" / "hermes-plugin-receipts.jsonl").exists())


async def _person_elsewhere(gateway):
    from gateway.platforms.base import MessageEvent, MessageType

    source = gateway.adapter.build_source(chat_id="elsewhere", chat_type="group", user_id="u1", user_name="Sam")
    await gateway.adapter.handle_message(
        MessageEvent(text="hi hermes", message_type=MessageType.TEXT, source=source, message_id="9")
    )


if __name__ == "__main__":
    unittest.main()
