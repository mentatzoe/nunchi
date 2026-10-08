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
from nunchi.integrations.hermes_plugin_conformance import (
    BOUND_CHANNEL,
    DISCORD_BOT,
    DISCORD_ROOM,
    DISCORD_ROOM_ROLE,
    ROOM,
    ROOM_ENV,
    ROOM_PLATFORM,
    TURN_USER,
    discord_available,
    hermes_available,
    room_settings,
)
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
DISCORD_BINDING = ParticipantBinding(
    participant_id="vigil",
    actor_id=f"discord:user:{DISCORD_BOT}",
    platform="discord",
    room_id=DISCORD_ROOM,
    continuity_scope_id=f"discord:{DISCORD_ROOM}",
)
DISCORD_PROFILE = ParticipantProfile(
    profile_id="vigil-profile",
    participant_id=DISCORD_BINDING.participant_id,
    actor_id=DISCORD_BINDING.actor_id,
    instructions="Participate directly and preserve uncertainty.",
    provenance="test:offline",
    sha256="0" * 64,
)
DISCORD_ROUTE = HermesRoute(platform="discord", chat_id=DISCORD_ROOM, turn_user_id=TURN_USER)
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
        # The room needs every actor an event names, except the agent itself.
        event = kwargs["event"]
        named = {event["author_id"], *event["mentioned_actor_ids"]} - {PROFILE.actor_id, DISCORD_PROFILE.actor_id}
        if named - set(kwargs["actors"]):
            raise AssertionError(f"the room cannot resolve {sorted(named - set(kwargs['actors']))}")
        self.delivered.append(kwargs)


def _plugin(room=None, *, route=ROUTE) -> HermesRoomPlugin:
    return HermesRoomPlugin(
        profile=PROFILE if route.platform == "telegram" else DISCORD_PROFILE,
        guard=SecretGuard([]),
        route=route,
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

    def test_a_thread_under_the_bound_channel_is_part_of_the_room(self):
        # Hermes gives a message in a Discord thread the thread as its chat and
        # the channel as its parent; Hermes would answer it itself if the
        # plugin left it.
        route = HermesRoute(platform="discord", chat_id="1100", turn_user_id="t")
        thread = {"chat_id": "777", "thread_id": "777", "parent_chat_id": "1100"}
        self.assertTrue(route.holds("discord", thread))
        self.assertTrue(route.inside(thread))
        self.assertTrue(route.holds("discord", {"chat_id": "1100", "thread_id": None}))
        self.assertFalse(route.inside({"chat_id": "1100", "thread_id": None}))
        self.assertFalse(route.holds("discord", {**thread, "parent_chat_id": "1200"}))
        self.assertFalse(route.holds("discord", {"chat_id": "777", "thread_id": "777"}))
        self.assertFalse(route.holds("telegram", thread))
        # A binding to one thread holds that thread only, not its neighbours.
        one = HermesRoute(platform="discord", chat_id="777", turn_user_id="t", thread_id="777")
        self.assertTrue(one.holds("discord", thread))
        self.assertFalse(one.holds("discord", {"chat_id": "778", "thread_id": "778", "parent_chat_id": "1100"}))
        topic = HermesRoute(platform="telegram", chat_id="-100", turn_user_id="t", thread_id="5")
        self.assertFalse(topic.holds("telegram", {"chat_id": "-200", "thread_id": "5", "parent_chat_id": "-100"}))


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
            mentions=[SimpleNamespace(id="bot-7"), SimpleNamespace(id="u2", bot=False, display_name="Kim")],
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
        # Each person it names is an actor the room knows; the agent keeps its own name.
        self.assertEqual({"kind": "human", "display_name": "Kim"}, delivery["actors"]["telegram:user:u2"])
        self.assertNotIn("telegram:user:bot-7", delivery["actors"])

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

    def test_a_message_in_a_thread_under_the_channel_is_observed_in_its_thread(self):
        room = _StubRoom()
        plugin = _plugin(room, route=DISCORD_ROUTE)
        source = SimpleNamespace(platform=SimpleNamespace(value="discord"), chat_id="777", thread_id="777",
                                 parent_chat_id=DISCORD_ROOM)
        raw = SimpleNamespace(mentions=[], mention_everyone=False, author=SimpleNamespace(bot=False))
        plugin.on_dispatch(event=SimpleNamespace(source=source, message_id="2002", raw_message=raw))
        answer = self._admit(plugin, platform="discord",
                             source={"chat_id": "777", "thread_id": "777", "parent_chat_id": DISCORD_ROOM,
                                     "chat_type": "thread", "user_id": "42", "user_name": "Sam"},
                             message_id="2002", text="is the rollback done?")
        self.assertEqual(answer, {"action": "handled"})
        (delivery,) = room.delivered
        event = validate_canonical_event(delivery["event"])
        self.assertEqual("discord:message:777", event["thread_root_event_id"])
        # The facts noted at dispatch reached the room.
        self.assertEqual("human", delivery["actors"]["discord:user:42"]["kind"])
        # The agent's reaction to it goes through the thread.
        self.assertEqual("777", plugin.chat_of("2002"))
        self.assertEqual(DISCORD_ROOM, plugin.chat_of("2001"))

    def test_a_message_hermes_admits_without_dispatch_keeps_only_its_discord_time(self):
        # Hermes runs a message it rescues from its busy queue without
        # pre_gateway_dispatch (README, Known gaps): it reaches the room with
        # no mentions or reply target. A Discord id says when it was sent
        # (Discord's documented example id); a Telegram id does not.
        for route, timestamp in ((DISCORD_ROUTE, "2016-04-30T11:18:25.796Z"), (ROUTE, None)):
            with self.subTest(route.platform):
                room = _StubRoom()
                plugin = _plugin(room, route=route)
                with self.assertLogs("nunchi.hermes_plugin", level="WARNING") as logs:
                    self._admit(plugin, platform=route.platform,
                                source={"chat_id": route.chat_id, "user_id": "42", "user_name": "Sam"},
                                message_id="175928847299117063", text="can you look?")
                self.assertIn("without its dispatch facts", "\n".join(logs.output))
                (delivery,) = room.delivered
                event = validate_canonical_event(delivery["event"])
                self.assertEqual(([], timestamp), (event["mentioned_actor_ids"], event.get("timestamp")))
                self.assertNotIn("reply_to_event_id", event)

    def test_a_message_in_the_channel_names_no_thread(self):
        room = _StubRoom()
        plugin = _plugin(room, route=DISCORD_ROUTE)
        self._admit(plugin, platform="discord", source={"chat_id": DISCORD_ROOM, "thread_id": None, "user_id": "42"},
                    message_id="2001", text="anyone around?")
        (delivery,) = room.delivered
        self.assertNotIn("thread_root_event_id", delivery["event"])

    def test_a_telegram_topic_in_the_bound_group_is_observed_in_its_thread(self):
        # Hermes gives a forum topic message the group as its chat and the
        # topic as its thread; the General topic (thread 1) is the group's
        # main chat. Reactions on Telegram need only the group.
        room = _StubRoom()
        plugin = _plugin(room)
        for message_id, thread in (("300", "5"), ("301", "1"), ("302", None)):
            self._admit(plugin, platform="telegram",
                        source={"chat_id": ROOM, "thread_id": thread, "chat_type": "forum", "user_id": "u1"},
                        message_id=message_id, text="hi")
        roots = [delivery["event"].get("thread_root_event_id") for delivery in room.delivered]
        self.assertEqual(["telegram:message:5", None, None], roots)
        validate_canonical_event(room.delivered[0]["event"])
        self.assertEqual(ROOM, plugin.chat_of("300"))

    def test_after_a_restart_the_room_log_names_a_messages_thread(self):
        # The plugin notes a thread message's chat when it arrives; a new
        # plugin process finds it in the room's log instead.
        events = {
            "discord:message:2002": {"id": "discord:message:2002", "thread_root_event_id": "discord:message:777"},
            "discord:message:2001": {"id": "discord:message:2001"},
        }
        plugin = _plugin(_StubRoom(), route=DISCORD_ROUTE)
        plugin.room = SimpleNamespace(observation=SimpleNamespace(resolve_event=events.get))
        self.assertEqual("777", plugin.chat_of("2002"))
        self.assertEqual(DISCORD_ROOM, plugin.chat_of("2001"))
        self.assertEqual(DISCORD_ROOM, plugin.chat_of("2999"))
        # A Telegram topic is not a chat of its own.
        telegram = _plugin(_StubRoom())
        telegram.room = SimpleNamespace(observation=SimpleNamespace(resolve_event=lambda _id: {
            "id": "telegram:message:300", "thread_root_event_id": "telegram:message:5"}))
        self.assertEqual(ROOM, telegram.chat_of("300"))

    def test_a_thread_hermes_opened_itself_is_consumed_and_named_in_an_error(self):
        # Under Hermes's Discord defaults an @mention gets a new thread before
        # any plugin hook. The message still reaches the room, as the start of
        # that thread in the channel, and the error names the settings.
        room = _StubRoom()
        plugin = _plugin(room, route=DISCORD_ROUTE)
        with self.assertLogs("nunchi.hermes_plugin", level="ERROR") as logs:
            answer = self._admit(plugin, platform="discord",
                                 source={"chat_id": "2004", "thread_id": "2004", "parent_chat_id": DISCORD_ROOM,
                                         "chat_type": "thread", "auto_thread_created": True, "user_id": "42"},
                                 message_id="2004", text="can you look?")
        self.assertEqual(answer, {"action": "handled"})
        (line,) = logs.output
        for key in ("discord.free_response_channels", f'["{DISCORD_ROOM}"]', "discord.free_response_auto_thread"):
            self.assertIn(key, line)
        (delivery,) = room.delivered
        self.assertNotIn("thread_root_event_id", delivery["event"])
        self.assertEqual(DISCORD_ROOM, plugin.chat_of("2004"))

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


class WhatTheModelWroteTest(unittest.TestCase):
    """What the plugin reports, and how long it waits on a provider failure, without Hermes."""

    def test_reasoning_is_read_as_hermes_reads_it(self):
        from nunchi.integrations.hermes_plugin.plugin import _reasoning

        # In process: an object whose provider-data fields are properties.
        message = SimpleNamespace(reasoning=None, reasoning_content="Sam asked me.", reasoning_details=None)
        self.assertEqual(["Sam asked me."], _reasoning(message))
        # Under plugins.isolation: host the message is a record of its fields:
        # reasoning_content and reasoning_details live in its provider data.
        record = {"content": "", "reasoning": None, "provider_data": {
            "reasoning_content": "Sam asked me.",
            "reasoning_details": [{"type": "reasoning.summary", "summary": "The migration timed out."},
                                  {"type": "reasoning.text", "text": "Sam asked me."}],
        }}
        self.assertEqual(
            ["Sam asked me.", "The migration timed out.", "Sam asked me.\n\nThe migration timed out."],
            _reasoning(record),
        )
        self.assertEqual([], _reasoning({"content": "On it."}))

    def test_the_parts_of_an_answer_cut_at_the_length_limit_are_this_runs(self):
        from nunchi.integrations.hermes_plugin.plugin import _fragments

        history = [
            {"role": "user", "content": "an earlier turn"},
            {"role": "assistant", "content": "Earlier part.", "_length_continuation_fragment": True},
            {"role": "user", "content": "<nunchi_wake/> this turn"},
            {"role": "assistant", "content": "First part,", "_length_continuation_fragment": True},
            {"role": "user", "content": "[System: continue]", "_length_continuation_nudge": True},
            {"role": "assistant", "content": "second part,", "_length_continuation_fragment": True},
            {"role": "user", "content": "[System: continue]", "_length_continuation_nudge": True},
        ]
        self.assertEqual(["First part,", "second part,"], _fragments(history))
        self.assertEqual([], _fragments(None))

    def _failing_run(self):
        from unittest import mock

        from nunchi.integrations.hermes_plugin.plugin import _Run

        plugin = HermesRoomPlugin(profile=PROFILE, guard=SecretGuard([]), route=ROUTE,
                                  failure_grace_seconds=5, recovery_grace_seconds=130)
        plugin._runs["t1"] = _Run(turn_id="t1", session_id="s", task_id="s", bound=True)
        timers = []
        patcher = mock.patch("nunchi.integrations.hermes_plugin.plugin.threading.Timer",
                             lambda grace, *args, **kwargs: timers.append(grace) or SimpleNamespace(
                                 daemon=True, start=lambda: None))
        patcher.start()
        self.addCleanup(patcher.stop)
        return plugin, timers

    def test_a_refusal_ends_the_turn_soon_and_a_spent_retry_waits_out_hermess_recovery(self):
        plugin, timers = self._failing_run()
        # Hermes retries: nothing to wait for.
        plugin.on_api_error(turn_id="t1", retryable=True, retry_count=0, max_retries=3, status_code=503)
        self.assertEqual([], timers)
        # The provider refused: Hermes moves to a fallback at once, or gives up.
        plugin.on_api_error(turn_id="t1", retryable=False, retry_count=0, max_retries=3, status_code=400)
        # Retries spent on an outage: Hermes may wait in its recovery ladder (up to 120 s).
        plugin.on_api_error(turn_id="t1", retryable=True, retry_count=2, max_retries=3, status_code=503)
        self.assertEqual([5, 130], timers)

    def test_the_default_wait_outlasts_hermess_longest_recovery_wait(self):
        from nunchi.integrations.hermes_plugin.plugin import (
            DEFAULT_FAILURE_GRACE_SECONDS,
            DEFAULT_RECOVERY_GRACE_SECONDS,
        )

        # agent/turn_recovery_autorecover.py: 60 s plus 20 % jitter, or a
        # Retry-After of up to 120 s.
        self.assertGreater(DEFAULT_RECOVERY_GRACE_SECONDS, 120)
        self.assertLessEqual(DEFAULT_FAILURE_GRACE_SECONDS, 5)


# -- inside a real Hermes gateway -----------------------------------------------------------------


def _room_factory(state: Path, *, binding=BINDING, profile=PROFILE):
    settings = RoomSettings(
        binding=binding,
        profile=profile,
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


def _readme_settings(after: str = "## Hermes setup the room needs") -> dict:
    """The README's first YAML block after ``after`` in "Hermes setup the room needs",
    as Hermes's own reader reads it."""

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
    section = text[text.index("## Hermes setup the room needs"):text.index("## Known gaps")]
    block = re.search(r"```yaml\n(.*?)```", section[section.index(after):], re.S)
    return yaml.safe_load(block.group(1))


class ReadmeTest(unittest.TestCase):
    def test_the_readme_room_setup_is_what_the_kit_tests(self):
        settings = _readme_settings()
        plugins = settings.pop("plugins")
        self.assertEqual(room_settings("telegram"), settings)
        self.assertEqual(["nunchi-room"], plugins["enabled"])
        self.assertIs(True, plugins["entries"]["nunchi-room"]["allow_gateway_injection"])

    def test_the_readme_discord_block_is_what_the_discord_lane_tests(self):
        discord = _readme_settings(after="### On Discord")
        self.assertEqual({"discord": room_settings("discord")["discord"]}, discord)
        self.assertEqual([BOUND_CHANNEL], discord["discord"]["free_response_channels"])
        self.assertIs(True, room_settings("discord")["thread_sessions_per_user"])

    def test_the_readme_discord_env_is_what_the_discord_lane_tests(self):
        text = README.read_text(encoding="utf-8")
        section = text[text.index("### On Discord"):text.index("## Known gaps")]
        block = re.search(r"```sh\n(.*?)```", section, re.S).group(1)
        env = dict(line.split("#")[0].strip().split("=", 1) for line in block.splitlines() if "=" in line)
        # The README's example turn_user_id is the kit's.
        self.assertEqual(ROOM_ENV["discord"], {key: env[key] for key in ROOM_ENV["discord"]})
        # The room's role, and no user allowlist (the kit's `ALLOWED_ROLES`, `ALLOWED_USERS`).
        self.assertIn("DISCORD_ALLOWED_ROLES", env)
        self.assertEqual("", env["DISCORD_ALLOWED_USERS"])


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

        for platform in ("telegram", "discord"):
            integration = HermesKitIntegration(platform=platform)
            for name, scenario in kit.SCENARIOS.items():
                if scenario.posting != "final-answer":
                    continue
                with self.subTest(integration.name, scenario=name):
                    if platform == "discord" and not discord_available():
                        self.skipTest("the Discord lane needs discord.py (hermes-agent[messaging])")
                    result = kit.run_scenario(name, integration)
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
        self.assertIn('"(empty)": no reported model response holds this text', why)

    def test_hermess_empty_is_never_the_agents_reply_when_the_model_wrote_the_word(self):
        # Hermes's "(empty)" is not the model's word "empty" in its interim
        # text, its thinking or its reasoning (leak audit row 5).
        tool = {"tool": "room_context", "arguments": {"direction": "before"}}
        for name, first, again in (
            ("interim text", dict(tool, text="Let me see whether the deploy queue is empty."), {"text": ""}),
            ("thinking", {"text": "<thinking>The log might be empty.</thinking>"}, {"text": ""}),
            ("reasoning", {"text": "", "reasoning": "The log they pasted is empty, so I cannot see the error."},
             {"text": "", "reasoning": "The log they pasted is empty, so I cannot see the error."}),
        ):
            with self.subTest(name):
                harness = self._harness()
                turns = _record_turns(harness)
                harness.model.on_request = lambda harness=harness, first=first, again=again: harness.model.reply(
                    first if harness.model.count() == 1 else again)
                harness.person_says("Why did the deploy fail? Log attached.", message_id="100")
                self.assertTrue(harness.wait_for_requests(1))
                self.assertTrue(harness.settle(timeout=90))
                self.assertEqual([], harness.gateway.adapter.sent)
                self.assertEqual([], _own_moves(harness))
                ((kind, why),) = turns
                self.assertEqual("failed", kind)
                self.assertIn('"(empty)": no reported model response holds this text', why)

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
        self.assertIn("no reported model response holds this text", why)

    def test_known_gap_a_summary_the_model_writes_at_the_iteration_limit_fails_the_turn(self):
        # Hermes asks for that summary outside its model-request hooks, so no
        # hook shows the plugin what the model wrote (README, Known gaps): the
        # model's own summary fails the turn and is not posted. The room setup
        # leaves agent.max_turns unset.
        harness = self._harness(agent={"max_turns": 1})
        turns = _record_turns(harness)
        summary = "The deploy failed because the database migration timed out. Rerunning it should fix it."
        first = {"tool": "room_context", "arguments": {"direction": "before"}, "text": "Let me check the logs first."}
        harness.model.on_request = lambda: harness.model.reply(first if harness.model.count() == 1 else {"text": summary})
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(2))
        self.assertTrue(harness.settle(timeout=60))
        self.assertEqual([], harness.gateway.adapter.sent)
        self.assertEqual([], _own_moves(harness))
        ((kind, why),) = turns
        self.assertEqual("failed", kind)
        self.assertIn(summary[:40], why)
        self.assertIn("no reported model response holds this text", why)

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
        # good (a 400 is not retryable). The plugin ends the turn after a
        # short wait for a fallback, instead of the library's deadline (300 s).
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

    def test_an_outage_hermes_rides_out_is_still_answered(self):
        # The provider is out of service (503) through Hermes's retries, then
        # back. Hermes waits in its auto-recovery ladder (about 15 s) and asks
        # again: the turn stays open, and the answer is posted and remembered.
        harness = self._harness()
        turns = _record_turns(harness)
        asked: list[float] = []

        def on_request():
            asked.append(time.monotonic())
            if len(asked) < 2 or asked[-1] - asked[-2] < 10:
                harness.model.reply({"status": 503, "error": "conformance: upstream overloaded, try again later"})
            else:
                harness.model.reply({"text": "On it."})

        harness.model.on_request = on_request
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        self.assertTrue(harness.settle(timeout=120))
        self.assertGreaterEqual(asked[-1] - asked[-2], 10)  # Hermes's own recovery wait
        self.assertEqual([(ROOM, "On it.")], harness.gateway.adapter.sent)
        self.assertEqual([("message", "On it.")], turns)
        self.assertEqual([("reply", "On it.")], _own_moves(harness))

    ROLLBACK = (
        "Here is the rollback plan, step by step. First, freeze deploys in the pipeline and tell "
        "the on-call channel. Second, scale the canary down to zero and confirm traffic drains",
        " in the dashboard. Third, run the down migration against the replica before the primary. "
        "Fourth, flip the feature flag back and watch the error rates for fifteen minutes.",
    )
    # A cut inside a tag pair leaves half of it in each part.
    BANNER = (
        "Here is the fixed banner for the status page, then the deploy steps.\n\n```html\n"
        "<div class=\"banner\">\n  <p>Deploys are paused while we roll back the migration.",
        " Next update at 02:00.</p>\n</div>\n```\n\nThen merge it, deploy to the canary first, and watch "
        "the error rate for fifteen minutes before you promote it to the rest of the fleet.",
    )

    def _a_cut_answer(self, cut, parts=ROLLBACK):
        # The model's answer is cut, Hermes asks it to go on, and joins the parts.
        harness = self._harness()
        turns = _record_turns(harness)
        first, rest = parts
        replies = [dict(cut, text=first), {"text": rest}]
        harness.model.on_request = lambda: harness.model.reply(replies.pop(0) if replies else {"text": ""})
        harness.person_says("Can someone write up the rollback plan for tonight?", message_id="100")
        self.assertTrue(harness.wait_for_requests(2))
        self.assertIn("[System:", _user_text(harness.model.latest()))  # Hermes asked it to go on
        self.assertTrue(harness.settle(timeout=60))
        joined = first + rest
        self.assertEqual([(ROOM, joined)], harness.gateway.adapter.sent)
        self.assertEqual([("message", joined)], turns)
        # Memory keeps the start of a long move, with its whitespace folded.
        ((kind, remembered),) = _own_moves(harness)
        self.assertEqual("reply", kind)
        self.assertTrue(" ".join(joined.split()).startswith(" ".join(remembered.rstrip("…").split())), remembered)

    def test_an_answer_cut_at_the_length_limit_is_delivered_whole(self):
        self._a_cut_answer({"finish": "length"})

    def test_an_answer_whose_stream_broke_off_is_delivered_whole(self):
        self._a_cut_answer({"drop": True})

    def test_an_answer_cut_inside_a_tag_pair_is_delivered_whole(self):
        self._a_cut_answer({"finish": "length"}, self.BANNER)

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

    def _after_a_command(self, command):
        # A room member's Hermes command, then a turn the agent answers.
        harness = self._harness()
        harness.person_says(command, message_id="90")
        time.sleep(2.0)
        replied = list(harness.gateway.adapter.sent)
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"text": "<thinking>Sam asked the room; I know the log path.</thinking>\n"
                                     "The log is in the deploy job's artifacts."})
        self.assertTrue(harness.settle())
        self.assertEqual([("reply", "The log is in the deploy job's artifacts.")], _own_moves(harness))
        return replied, harness.gateway.adapter.sent[len(replied):]

    def test_the_room_setup_keeps_the_runtime_footer_off_after_footer_on(self):
        # /footer on writes the top-level setting; the room setup's
        # per-platform one outranks it.
        replied, posted = self._after_a_command("/footer on")
        self.assertTrue(replied)  # Known gap: the command still gets Hermes's reply.
        self.assertEqual([(ROOM, "The log is in the deploy job's artifacts.")], posted)

    def test_known_gap_reasoning_show_posts_the_agents_thinking(self):
        # Any room member may turn reasoning display back on (README, Known
        # gaps): Hermes then posts the agent's private thinking with its answer.
        _, posted = self._after_a_command("/reasoning show")
        ((chat, text),) = posted
        self.assertIn("Sam asked the room; I know the log path.", text)
        self.assertTrue(text.endswith("The log is in the deploy job's artifacts."), text)

    def test_known_gap_a_look_again_run_shows_typing(self):
        # The fresh run a look-again starts runs as Hermes's queued follow-up,
        # which sends typing whatever typing_indicator says (README, Known
        # gaps). This pins the gap so it stays visible.
        harness = self._harness()
        self.assertFalse(harness.gateway.adapter.config.typing_indicator)
        harness.person_says("Can someone look at the failing deploy?", message_id="100")
        self.assertTrue(harness.wait_for_requests(1))
        harness.person_says("Actually, I found it myself.", message_id="101", user_id="u2", user_name="Kim")
        self.assertTrue(harness.wait_observed("telegram:message:101"))
        harness.model.reply({"text": "On it."})
        self.assertTrue(harness.wait_for_requests(2))
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.wait_for_requests(3))
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        self.assertEqual([], harness.gateway.adapter.sent)
        self.assertEqual([ROOM], harness.gateway.adapter.typing)

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

    def test_an_answer_hermes_takes_from_the_reasoning_is_posted_in_either_isolation(self):
        # A route that may answer in its reasoning: the model stops with its
        # answer only in reasoning_content, and Hermes posts that. Under
        # plugins.isolation: host the plugin reads it from the provider data.
        answer = "On it, the migration step timed out at 02:00."
        for isolation in ("in_process", "host"):
            with self.subTest(isolation):
                self._run_from_config(isolation, reply={"text": "", "reasoning": answer}, expect=answer,
                                      answer_in_reasoning=True)

    def _run_from_config(self, isolation, *, reply=None, expect="On it.", answer_in_reasoning=False):
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
        extra = {"plugins": {"isolation": isolation}}
        if answer_in_reasoning:
            # Hermes's opt-in for a custom provider that may answer in its reasoning.
            extra["custom_providers"] = [{"name": "conformance", "base_url": model.base_url,
                                          "api_key": "sk-local-conformance",
                                          "capabilities": {"answer_in_reasoning": True}}]
        gateway = HermesGateway(model=model, plugin_source=Path(package.__file__).parent,
                                plugin_settings={"config_path": str(config)},
                                extra_config=extra)
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
        model.reply(reply or {"text": "On it."})
        for _ in range(500):
            if gateway.adapter.sent and gateway.idle():
                break
            __import__("time").sleep(0.02)
        self.assertEqual(gateway.adapter.sent, [(ROOM, expect)])
        self.assertTrue((directory / "state" / "hermes-plugin-receipts.jsonl").exists())


@unittest.skipUnless(discord_available(), "requires an installed Hermes with discord.py (hermes-agent[messaging])")
class HermesDiscordTest(unittest.TestCase):
    """The plugin bound to a Discord channel, behind Hermes's stock Discord adapter (leak audit row 1).

    People's messages enter through the adapter's own ingress, so Hermes's
    mention gate, allowlists and auto-threading run as they would live.
    """

    def _harness(self, **kwargs):
        from nunchi.integrations.hermes_plugin_conformance import HermesHarness

        state = Path(tempfile.mkdtemp(prefix="nunchi-hermes-discord-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(state, ignore_errors=True))
        kwargs.setdefault("room_factory", _room_factory(state, binding=DISCORD_BINDING, profile=DISCORD_PROFILE))
        harness = HermesHarness(profile=DISCORD_PROFILE, guard=SecretGuard(["withheld-secret-value-123"]),
                                platform="discord", **kwargs)
        self.addCleanup(harness.close)
        return harness

    def _event(self, harness, event_id):
        self.assertTrue(harness.wait_observed(event_id))
        (event,) = [event for event in harness.plugin.room.observation.retained_events() if event["id"] == event_id]
        return event

    def _quiet(self, harness, timeout=60.0):
        """The agent stays silent on every turn the room starts, until Hermes and the room are idle."""

        answered = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            while answered < harness.model.count():
                harness.model.reply({"text": SILENCE_MARKER})
                answered += 1
            if harness.settle(timeout=1.0):
                time.sleep(0.5)
                if answered == harness.model.count() and harness.settle(timeout=1.0):
                    return
        self.fail("Hermes and the room did not settle")

    def _all_marked(self, harness):
        # Hermes never ran its own agent on a person's message: every model
        # request is a turn the library started.
        texts = [_user_text(request) for request in harness.model.requests]
        self.assertTrue(texts)
        for text in texts:
            self.assertTrue(text.startswith('<nunchi_wake id="'), text[:80])

    def test_the_room_setup_is_what_hermes_loads(self):
        harness = self._harness()
        adapter = harness.gateway.adapter
        self.assertEqual({DISCORD_ROOM}, adapter._discord_free_response_channels())
        self.assertFalse(adapter._discord_free_response_auto_thread())
        self.assertFalse(adapter._reactions_enabled())
        self.assertFalse(adapter.config.typing_indicator)
        # One session per person in a thread, each message on its own, the
        # people let in by the room's role and by no user allowlist, and
        # Hermes's busy handler filing each quick message on its own.
        runner = harness.gateway.runner
        self.assertIs(True, runner.config.thread_sessions_per_user)
        self.assertIs(True, adapter.config.extra["thread_sessions_per_user"])
        self.assertEqual(0, adapter._text_batch_delay_seconds)
        self.assertEqual((set(), {int(DISCORD_ROOM_ROLE)}), (adapter._allowed_user_ids, adapter._allowed_role_ids))
        self.assertEqual(TURN_USER, __import__("os").environ.get("GATEWAY_ALLOWED_USERS"))
        self.assertIsNotNone(adapter._busy_session_handler)
        self.assertEqual(("interrupt", "interrupt"), (runner._busy_input_mode, runner._busy_text_mode))

    def test_an_unmentioned_message_reaches_the_room_and_hermes_adds_nothing(self):
        # With the README setup every message in the channel reaches the room,
        # with no thread, reaction or typing from Hermes.
        harness = self._harness()
        self.assertTrue(harness.person_says("Anyone around? The deploy is red.", message_id="2001"))
        event = self._event(harness, "discord:message:2001")
        self.assertEqual(("discord:user:42", [], False),
                         (event["author_id"], event["mentioned_actor_ids"], "thread_root_event_id" in event))
        self.assertTrue(harness.wait_for_requests(1))
        time.sleep(2.5)  # Hermes refreshes typing every 2 s while a run is on
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        self._all_marked(harness)
        adapter = harness.gateway.adapter
        self.assertEqual(([], [], [], [], []), (adapter.threads, adapter.reactions,
                                                harness.gateway.world.reactions_removed, adapter.typing, adapter.sent))

    def test_a_message_in_a_persons_thread_is_the_rooms_and_only_the_library_posts(self):
        # Free-response for the channel makes every thread under it
        # free-response too: Hermes would answer there itself, raw, if the
        # plugin did not hold the thread as part of the room.
        harness = self._harness()
        harness.gateway.world.thread(777, name="rollback")
        self.assertTrue(harness.person_says("Is the rollback done?", message_id="2002", channel="777"))
        event = self._event(harness, "discord:message:2002")
        self.assertEqual("discord:message:777", event["thread_root_event_id"])
        self.assertTrue(harness.wait_for_requests(1))
        self.assertIn("rollback done", _user_text(harness.model.latest()))
        harness.model.reply({"text": "Yes, it finished at 02:10."})
        self.assertTrue(harness.settle())
        self._all_marked(harness)
        adapter = harness.gateway.adapter
        # The library's commit, and nothing else. It lands in the channel, not
        # the thread, until thread placement (README, Known gaps).
        self.assertEqual([(DISCORD_ROOM, "Yes, it finished at 02:10.")], adapter.sent)
        self.assertEqual(([], []), (adapter.threads, adapter.reactions))
        facts = harness.plugin.room.host.memory_facts("discord:message:2002") or {}
        self.assertEqual([("reply", "Yes, it finished at 02:10.")],
                         [(move.get("kind"), move.get("text")) for move in facts.get("own_moves", ())])

    def test_hermes_discord_defaults_drop_the_room_and_open_threads(self):
        # Hermes's Discord defaults, kept as a regression pin: without
        # free_response_channels an unmentioned message never reaches any
        # plugin hook, and an @mention is moved into a new thread before one.
        # The plugin still consumes it, so no raw reply, and names the keys.
        harness = self._harness(platform_block=dict(ROOM_PLATFORM))
        adapter = harness.gateway.adapter
        self.assertEqual(set(), adapter._discord_free_response_channels())
        self.assertFalse(harness.person_says("Anyone around? The deploy is red.", message_id="2003"))
        with self.assertLogs("nunchi.hermes_plugin", level="ERROR") as logs:
            self.assertTrue(harness.person_says("can you look at it?", message_id="2004", mentions=(DISCORD_BOT,)))
            event = self._event(harness, "discord:message:2004")
        self.assertIn("discord.free_response_channels", "\n".join(logs.output))
        self.assertIsNone(harness.plugin.room.observation.resolve_event("discord:message:2003"))
        self.assertEqual(["2004"], adapter.threads)
        self.assertEqual([f"discord:user:{DISCORD_BOT}"], event["mentioned_actor_ids"])
        self.assertNotIn("thread_root_event_id", event)
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())
        self._all_marked(harness)
        self.assertEqual([], adapter.sent)

    def test_the_agents_reaction_to_a_thread_message_lands_in_the_thread(self):
        harness = self._harness(platform_actions=True)
        world = harness.gateway.world
        world.thread(777, name="deploy")
        self.assertTrue(harness.person_says("Deploy is green again.", message_id="2005", channel="777"))
        self.assertTrue(harness.wait_for_requests(1))
        self.assertIn("room_react", _user_text(harness.model.latest()))
        harness.model.reply({"tool": "room_react",
                             "arguments": {"target_event_id": "discord:message:2005", "reaction": "👍"}})
        self.assertTrue(harness.wait_for_requests(2))
        self.assertIn("Done", json.loads(_tool_text(harness.model.latest()))["result"])
        harness.model.reply({"text": "Nice."})
        self.assertTrue(harness.settle())
        # Discord finds the message only through the thread it is in.
        self.assertEqual([("777", "2005", "👍")], world.reactions)
        self.assertEqual([], harness.gateway.adapter.sent)

    def test_two_people_in_a_thread_stay_two_messages_under_hermess_batching(self):
        # Hermes batches text by session (0.6 s by default). With one session
        # per person in a thread, two people posting back to back stay two
        # messages, each with its own author and id. Hermes's default shares
        # the thread's session: Kim's words reach the room as Sam's.
        for sessions, separate in ((None, True), ({"thread_sessions_per_user": False}, False)):
            with self.subTest(separate=separate):
                harness = self._harness(env={"HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS": None}, extra_config=sessions)
                self.assertEqual(0.6, harness.gateway.adapter._text_batch_delay_seconds)
                harness.gateway.world.thread(777, name="rollback")
                self.assertTrue(harness.person_says("Is the rollback done?", message_id="3001", channel="777"))
                self.assertTrue(harness.person_says("Yes, I did it an hour ago.", message_id="3002", user_id="43",
                                                    channel="777"))
                first = self._event(harness, "discord:message:3001")
                if separate:
                    second = self._event(harness, "discord:message:3002")
                    self.assertEqual(("discord:user:42", "Is the rollback done?"), (first["author_id"], first["text"]))
                    self.assertEqual(("discord:user:43", "Yes, I did it an hour ago.", "discord:message:777"),
                                     (second["author_id"], second["text"], second["thread_root_event_id"]))
                self._quiet(harness)
                if not separate:
                    self.assertEqual(("discord:user:42", "Is the rollback done?\nYes, I did it an hour ago."),
                                     (first["author_id"], first["text"]))
                    self.assertIsNone(harness.plugin.room.observation.resolve_event("discord:message:3002"))
                harness.close()

    def test_known_gap_a_person_hermes_does_not_allow_is_never_heard(self):
        # Hermes drops a person who is not on its allowlist before any plugin
        # hook, in the channel and in its threads (README, On Discord).
        harness = self._harness()
        world = harness.gateway.world
        world.person("44", "Lee")
        world.thread(777, name="deploy")
        self.assertFalse(harness.person_says("the deploy is red, can someone look?", message_id="2009", user_id="44"))
        self.assertFalse(harness.person_says("anyone?", message_id="2010", user_id="44", channel="777"))
        self.assertTrue(harness.person_says("I see it too.", message_id="2011"))
        self._event(harness, "discord:message:2011")
        self._quiet(harness)
        for event_id in ("discord:message:2009", "discord:message:2010"):
            self.assertIsNone(harness.plugin.room.observation.resolve_event(event_id))

    def test_known_gap_a_message_that_is_only_an_at_mention_never_reaches_the_room(self):
        # Hermes takes the bot's own mention out of the text and drops a
        # message left empty, before any plugin hook (README, Known gaps).
        harness = self._harness()
        self.assertFalse(harness.person_says("", message_id="2012", mentions=(DISCORD_BOT,)))
        self.assertTrue(harness.person_says("can you look at the deploy?", message_id="2013"))
        self._event(harness, "discord:message:2013")
        self._quiet(harness)
        self.assertIsNone(harness.plugin.room.observation.resolve_event("discord:message:2012"))

    def test_known_gap_a_reply_that_pings_another_bot_never_reaches_the_room(self):
        # Discord's Reply pings the replied-to author by default, which puts
        # a peer agent's bot in the message's mentions: Hermes drops it before
        # any plugin hook, whatever the bot settings. With the ping off the
        # reply is heard (README, Known gaps).
        peers = {**ROOM_PLATFORM, "free_response_channels": [DISCORD_ROOM], "free_response_auto_thread": False,
                 "allow_bots": "all", "bots_require_inline_mention": False}
        for block in (None, peers):
            with self.subTest(peer_settings=block is not None):
                harness = self._harness(platform_block=block)
                world = harness.gateway.world
                world.peer_bot("8800", "Castor")
                world.message("Deploy is green.", message_id="2014", user_id="8800")
                self.assertFalse(harness.person_says("Which deploy do you mean?", message_id="2015", reply_to="2014",
                                                     reply_ping=True))
                self.assertTrue(harness.person_says("Which deploy do you mean?", message_id="2016", reply_to="2014"))
                event = self._event(harness, "discord:message:2016")
                self.assertEqual("discord:message:2014", event["reply_to_event_id"])
                self._quiet(harness)
                self.assertIsNone(harness.plugin.room.observation.resolve_event("discord:message:2015"))
                harness.close()

    def test_a_turn_identity_in_discord_allowed_users_is_dropped_at_connect(self):
        # The setup before GATEWAY_ALLOWED_USERS: Hermes's connect-time
        # resolution drops "nunchi-turns", which names no guild member, and
        # rewrites DISCORD_ALLOWED_USERS, so Hermes refuses every turn the
        # library injects. The room still hears the channel; the agent never runs.
        harness = self._harness(allowed_users=f"42,43,{TURN_USER}", env={"GATEWAY_ALLOWED_USERS": None},
                                start_timeout_seconds=3.0)
        self.assertEqual("42,43", __import__("os").environ.get("DISCORD_ALLOWED_USERS"))
        self.assertTrue(harness.person_says("Anyone around? The deploy is red.", message_id="2017"))
        self._event(harness, "discord:message:2017")
        time.sleep(5.0)
        self.assertTrue(harness.settle())
        self.assertEqual(0, harness.model.count())
        self.assertEqual([], harness.gateway.adapter.sent)

    def test_after_a_restart_the_agents_reaction_to_a_thread_message_lands_in_the_thread(self):
        # The plugin notes a thread message's chat when it arrives; after a
        # restart on the same state, the room's log names its thread.
        from nunchi.integrations.hermes_plugin_conformance import HermesHarness

        state = Path(tempfile.mkdtemp(prefix="nunchi-hermes-discord-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(state, ignore_errors=True))

        def harness():
            started = HermesHarness(profile=DISCORD_PROFILE, guard=SecretGuard([]), platform="discord",
                                    platform_actions=True,
                                    room_factory=_room_factory(state, binding=DISCORD_BINDING, profile=DISCORD_PROFILE))
            self.addCleanup(started.close)
            started.gateway.world.thread(777, name="deploy")
            return started

        before = harness()
        self.assertTrue(before.person_says("Deploy is green again.", message_id="2018", user_id="43", channel="777"))
        self._event(before, "discord:message:2018")
        self._quiet(before)
        before.close()
        after = harness()
        world = after.gateway.world
        world.message("Deploy is green again.", message_id="2018", user_id="43", channel="777")
        self.assertTrue(after.person_says("Nice work, Kim.", message_id="2019"))
        self.assertTrue(after.wait_for_requests(1))
        self.assertEqual("discord:message:777",
                         after.plugin.room.observation.resolve_event("discord:message:2018")["thread_root_event_id"])
        after.model.reply({"tool": "room_react",
                           "arguments": {"target_event_id": "discord:message:2018", "reaction": "👍"}})
        self.assertTrue(after.wait_for_requests(2))
        answer = json.loads(_tool_text(after.model.latest()))
        self.assertIn("Done", answer.get("result", ""), answer)
        after.model.reply({"text": "Nice."})
        self.assertTrue(after.settle())
        self.assertEqual([("777", "2018", "👍")], world.reactions)

    def test_known_gap_a_message_that_names_only_another_bot_never_reaches_the_room(self):
        # Hermes drops a message that @mentions another bot and not this one
        # before any plugin hook, whatever the channel's settings (README,
        # Known gaps).
        harness = self._harness()
        harness.gateway.world.peer_bot("8800", "Castor")
        self.assertFalse(harness.person_says("can you check the logs?", message_id="2006", mentions=("8800",)))
        self.assertTrue(harness.person_says("and Vigil, you too?", message_id="2007", mentions=("8800", DISCORD_BOT)))
        self.assertTrue(harness.wait_observed("discord:message:2007"))
        self.assertIsNone(harness.plugin.room.observation.resolve_event("discord:message:2006"))
        self.assertTrue(harness.wait_for_requests(1))
        harness.model.reply({"text": SILENCE_MARKER})
        self.assertTrue(harness.settle())

    def test_peer_agents_are_heard_only_with_the_profiles_bot_settings(self):
        # Another agent's bot is dropped by Hermes's defaults (allow_bots:
        # none). With allow_bots: all and bots_require_inline_mention: false,
        # for the whole profile, its messages reach the room.
        for block, heard in ((dict(ROOM_PLATFORM), False),
                             ({**ROOM_PLATFORM, "allow_bots": "all", "bots_require_inline_mention": False}, True)):
            with self.subTest(heard=heard):
                harness = self._harness(platform_block={**block, "free_response_channels": [DISCORD_ROOM],
                                                        "free_response_auto_thread": False})
                harness.gateway.world.peer_bot("8800", "Castor")
                self.assertIs(heard, harness.person_says("Deploy is green.", message_id="2008", user_id="8800"))
                if heard:
                    event = self._event(harness, "discord:message:2008")
                    self.assertEqual("discord:user:8800", event["author_id"])
                    self.assertTrue(harness.wait_for_requests(1))
                    harness.model.reply({"text": SILENCE_MARKER})
                self.assertTrue(harness.settle())
                harness.close()

    def test_the_room_role_lets_the_room_in_and_keeps_direct_messages_out(self):
        # The README's allowlist: the room's role in DISCORD_ALLOWED_ROLES and
        # no user allowlist. Hermes hears the role's members in the channel and
        # its threads, drops anyone else before any hook, and refuses the
        # members' direct messages, where it would answer them itself.
        harness = self._harness()
        world = harness.gateway.world
        world.person("44", "Lee")
        world.thread(777, name="deploy")
        world.dm(9001, "42")
        self.assertTrue(harness.person_says("the deploy is red", message_id="2020"))
        self.assertTrue(harness.person_says("on it", message_id="2021", user_id="43", channel="777"))
        self.assertFalse(harness.person_says("me too", message_id="2022", user_id="44"))
        self.assertFalse(harness.person_says("what's the deploy key?", message_id="2023", channel="9001"))
        self._event(harness, "discord:message:2020")
        self.assertEqual("discord:message:777", self._event(harness, "discord:message:2021")["thread_root_event_id"])
        self._quiet(harness)
        for event_id in ("discord:message:2022", "discord:message:2023"):
            self.assertIsNone(harness.plugin.room.observation.resolve_event(event_id))
        self._all_marked(harness)
        self.assertEqual([], harness.gateway.adapter.sent)

    def test_other_allowlists_open_direct_messages_that_hermes_answers_itself(self):
        # A user allowlist opens direct messages to those users, `*` to anyone
        # who shares a server with the bot, and `discord.dm_role_auth_guild`
        # to the role's members. Hermes answers a direct message itself,
        # outside Nunchi.
        for name, sender, kwargs in (
            ("users", "42", {"allowed_users": "42,43", "env": {"DISCORD_ALLOWED_ROLES": None}}),
            ("wildcard", "44", {"allowed_users": "*", "env": {"DISCORD_ALLOWED_ROLES": None}}),
            ("dm_role_auth_guild", "42", {"extra_config": {"discord": {"dm_role_auth_guild": 70}}}),
        ):
            with self.subTest(name):
                harness = self._harness(**kwargs)
                world = harness.gateway.world
                world.person("44", "Lee")
                world.dm(9001, sender)
                self.assertTrue(harness.person_says("what's the deploy key?", message_id="2024", user_id=sender,
                                                    channel="9001"))
                self.assertTrue(harness.wait_for_requests(1))
                # Hermes's own run on the message, with no wake marker.
                self.assertTrue(_user_text(harness.model.latest()).startswith("what's the deploy key?"))
                harness.model.reply({"text": "Hermes's own answer."})
                self.assertTrue(harness.settle())
                self.assertIn(("9001", "Hermes's own answer."), harness.gateway.adapter.sent)
                room = harness.plugin.room
                self.assertTrue(room is None or room.observation.resolve_event("discord:message:2024") is None)
                harness.close()

    def _burst(self, harness):
        """Sam posts four messages while Hermes still handles the first; the third
        @mentions the agent and replies to Kim. Returns their ids and Kim's."""

        gateway, world = harness.gateway, harness.gateway.world
        earlier = world.snowflake()
        world.message("Deploy is red.", message_id=earlier, user_id="43")
        ids = [world.snowflake() for _ in range(4)]
        release = gateway.run(_hold(gateway.adapter, ids[0]))
        self.assertTrue(harness.person_says("the deploy is red", message_id=ids[0]))
        self.assertTrue(harness.person_says("again", message_id=ids[1]))
        self.assertTrue(harness.person_says("can you look?", message_id=ids[2], mentions=(DISCORD_BOT,),
                                            reply_to=earlier))
        self.assertTrue(harness.person_says("please", message_id=ids[3], mentions=(DISCORD_BOT,)))
        gateway.loop.call_soon_threadsafe(release.set)
        return ids, earlier

    def test_known_gap_a_message_hermes_rescues_from_its_busy_queue_loses_its_mentions(self):
        # Hermes's busy handler files each message that arrives while the
        # sender's previous one is still being handled as one of its own
        # (busy_input_mode: interrupt). A message the plugin consumes skips
        # Hermes's post-turn promotion of that queue, so the third and later
        # wait until the next one starts, which runs the oldest in its place
        # without pre_gateway_dispatch: the room gets it with no mentions and
        # no reply target (README, Known gaps). Its Discord id still gives its
        # time, so the room files it in order.
        harness = self._harness()
        with self.assertLogs("nunchi.hermes_plugin", level="WARNING") as logs:
            (first, second, rescued, last), _ = self._burst(harness)
            for message_id in (first, second, rescued, last):
                self._event(harness, f"discord:message:{message_id}")
        self.assertIn(f"message {rescued} reached the room without its dispatch facts", "\n".join(logs.output))
        self._quiet(harness)
        events = [event for event in harness.plugin.room.observation.retained_events()
                  if event["type"] == "message" and event["author_id"] == "discord:user:42"]
        self.assertEqual([first, second, rescued, last], [event["id"].rsplit(":", 1)[1] for event in events])
        lost = events[2]
        self.assertEqual(("can you look?", []), (lost["text"], lost["mentioned_actor_ids"]))
        self.assertNotIn("reply_to_event_id", lost)
        sent = harness.gateway.world.channels[int(DISCORD_ROOM)].messages[int(rescued)].created_at
        self.assertEqual(sent.isoformat(timespec="milliseconds").replace("+00:00", "Z"), lost["timestamp"])
        self.assertEqual([f"discord:user:{DISCORD_BOT}"], events[3]["mentioned_actor_ids"])
        self.assertEqual([], harness.gateway.adapter.sent)

    def test_hermess_queue_busy_mode_merges_a_persons_quick_messages(self):
        # Without busy_input_mode: interrupt. With `queue`, Hermes merges the
        # messages sent while it still handles the first into one, under the
        # last one's id: the earlier ones never exist for the room, and their
        # @mentions and reply target are gone.
        harness = self._harness(extra_config={"display": {"busy_input_mode": "queue"}})
        (first, second, rescued, last), _ = self._burst(harness)
        merged = self._event(harness, f"discord:message:{last}")
        self._quiet(harness)
        self.assertEqual(("again\ncan you look?\nplease", []), (merged["text"], merged["mentioned_actor_ids"]))
        for message_id in (second, rescued):
            self.assertIsNone(harness.plugin.room.observation.resolve_event(f"discord:message:{message_id}"))

    def test_hermes_defaults_post_a_busy_notice_on_quick_messages(self):
        # Without display.busy_ack_enabled: false, a person's quick second
        # message makes Hermes post "⚡ Interrupting current task…" in the room.
        harness = self._harness(extra_config={"display": {"busy_ack_enabled": True}})
        ids, _ = self._burst(harness)
        self._event(harness, f"discord:message:{ids[-1]}")
        self._quiet(harness)
        (notice,) = harness.gateway.adapter.sent
        self.assertEqual(DISCORD_ROOM, notice[0])
        self.assertTrue(notice[1].startswith("⚡ Interrupting current task"), notice[1])

    def test_known_gap_while_hermes_drains_it_answers_each_room_message_itself(self):
        # While Hermes drains for a restart or a stop, it answers each message
        # in the room itself, before any plugin hook, and the room never hears
        # the message. No setting stops it (README, Known gaps).
        harness = self._harness()
        gateway = harness.gateway
        gateway.runner._draining = True
        self.addCleanup(setattr, gateway.runner, "_draining", False)
        release = gateway.run(_hold(gateway.adapter, "2025"))
        self.assertTrue(harness.person_says("the deploy is red", message_id="2025"))
        self.assertTrue(harness.person_says("anyone?", message_id="2026"))
        gateway.loop.call_soon_threadsafe(release.set)
        self.assertTrue(harness.settle())
        self.assertEqual([(DISCORD_ROOM, "⏳ Gateway is shutting down and is not accepting another turn right now."),
                          (DISCORD_ROOM, "⏳ Gateway is shutting down and is not accepting new work right now.")],
                         gateway.adapter.sent)
        room = harness.plugin.room
        self.assertTrue(room is None or room.observation.resolve_event("discord:message:2025") is None)
        self.assertEqual(0, harness.model.count())


async def _hold(adapter, message_id):
    """Hold Hermes's handling of one message until the returned event is set, as a slow
    admission would: the sender's next messages meet Hermes's busy session meanwhile."""

    release = asyncio.Event()
    handler = adapter._message_handler

    async def held(event):
        if str(event.message_id) == message_id:
            await release.wait()
        return await handler(event)

    adapter._message_handler = held
    return release


async def _person_elsewhere(gateway):
    from gateway.platforms.base import MessageEvent, MessageType

    source = gateway.adapter.build_source(chat_id="elsewhere", chat_type="group", user_id="u1", user_name="Sam")
    await gateway.adapter.handle_message(
        MessageEvent(text="hi hermes", message_type=MessageType.TEXT, source=source, message_id="9")
    )


if __name__ == "__main__":
    unittest.main()
