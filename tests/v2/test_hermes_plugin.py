"""The Hermes plugin (#94 step 9e): public hooks only, consume and start, final-answer posting.

The first group needs no Hermes: it checks the plugin's own side with a stub
plugin context. The second group runs the plugin inside a real Hermes gateway
(`nunchi.integrations.hermes_plugin_conformance`), loaded from a throwaway
HERMES_HOME with only the model scripted, and skips when Hermes is not
installed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from nunchi.attention import AttentionPolicy, ParticipantProfile
from nunchi.conformance import fixture_attention_model
from nunchi.integrations.hermes_plugin import SILENCE_MARKER, WAKE_MARKER, HermesRoomPlugin, HermesRoute
from nunchi.integrations.hermes_plugin.plugin import TOKEN_PATTERNS
from nunchi.integrations.hermes_plugin_conformance import ROOM, TURN_USER, hermes_available
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
            {"post_gateway_admission", "pre_llm_call", "transform_tool_result", "post_api_request",
             "transform_llm_output", "on_session_end"},
        )

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

    def _next_turn_after_a_delivered_reply(self):
        harness = self._harness()
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"text": "On it."})
        self.assertTrue(harness.settle())
        harness.person_says("Thanks! Ping me when it's green.", message_id="102")
        self.assertTrue(harness.wait_for_requests(2))
        text = _user_text(harness.model.latest())
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        payload = text[text.index("<nunchi_participant_turn_v1>") + len("<nunchi_participant_turn_v1>"):
                       text.index("</nunchi_participant_turn_v1>")]
        return json.loads(payload)["participant_turn"]["wake"]

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
