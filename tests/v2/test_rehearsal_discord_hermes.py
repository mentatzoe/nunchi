"""The Hermes column of the probe's Discord room (step 9f, PR 3c): `hermes gateway run` with the Nunchi plugin, unmodified, on the stand-in.

The lane itself needs Hermes, the launcher (root, and namespaces) and about
half a minute: CI's ``hermes-plugin`` job runs it. What is tested here needs
neither Hermes nor root: the profile the leg writes for Hermes (the README's
room settings and variables), the scripted model, the checks that differ for a
harness that posts its final answer itself, and everything the leg reads from
outside Hermes's process (the participant's receipts, the library's record of
the message Hermes delivered, Hermes's own state file), on files written the
way the plugin writes them.
"""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from nunchi.integrations import hermes_plugin_conformance as kit
from nunchi.integrations.hermes_plugin import plugin as plugin_module
from nunchi.participant import HARNESS_DELIVERS

from evals.behavior.scene import load_scene
from evals.rehearsal import checks, discord_room, probe, record, routes, standin
from evals.rehearsal.fake_discord import rest
from evals.rehearsal.fake_discord.control import FakeDiscord

SCRIPT = discord_room.SCRIPT


def _turn(trigger: str, text: str, **addressing) -> dict:
    return {
        "protocol": {"name": "nunchi.participant-turn", "version": 1},
        "binding": {"request_id": "req-1"},
        "wake": {"trigger_event_id": trigger, "events": [{"id": trigger, "text": text, **addressing}], "attention": {"source": "WAKE"}},
    }


def _request(text: str | None, *, tools: bool = True, tool_result: str | None = None) -> dict:
    """A model request as Hermes makes it: the turn in the user message, and the tools it offers."""

    messages: list[dict] = [{"role": "system", "content": "You are Hermes."}]
    if text is not None:
        document = json.dumps({"participant_turn": _turn("discord:message:7", text), "context_pages": []})
        messages.append({"role": "user", "content": f'<nunchi_wake id="w"/>\nYou are Vigil.\n\n<{standin.TURN_TAG}>{document}</{standin.TURN_TAG}>'})
    if tool_result is not None:
        messages += [{"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function"}]},
                     {"role": "tool", "tool_call_id": "call_1", "content": tool_result}]
    return {"model": "m", "messages": messages, **({"tools": [{"type": "function", "function": {"name": "room_react"}}]} if tools else {})}


def _ask(agent: standin.ScriptedHermesAgent, body: dict) -> dict:
    connection = http.client.HTTPConnection(agent.base_url.removeprefix("http://").split("/")[0], timeout=10)
    try:
        connection.request("POST", "/v1/chat/completions", json.dumps(body), {"Content-Type": "application/json"})
        return json.loads(connection.getresponse().read())["choices"][0]
    finally:
        connection.close()


class ScriptedHermesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = standin.ScriptedHermesAgent(probe.SCRIPTED_ANSWER, script=SCRIPT)
        self.addCleanup(self.agent.close)

    def test_a_final_answer_is_the_post_whatever_the_moment_is_called(self):
        for text, expected in (
            ("what's a sensible default timeout?", probe.SCRIPTED_ANSWER),
            (f"should we {discord_room.REPLY_PHRASE}?", discord_room.SCRIPTED_REPLY),
            (f"{discord_room.THREAD_PHRASE} before it gives up?", discord_room.SCRIPTED_THREAD_REPLY),
        ):
            with self.subTest(text=text):
                choice = _ask(self.agent, _request(text))
                self.assertEqual((expected, "stop"), (choice["message"]["content"], choice["finish_reason"]))
                self.assertNotIn("tool_calls", choice["message"], "Hermes cannot reply: the answer is text")
        self.assertEqual(["send"] * 3, [move["role"] for move in self.agent.moves])
        self.assertEqual({"discord:message:7"}, {move["trigger"] for move in self.agent.moves})

    def test_a_reaction_is_one_call_of_the_plugins_room_tool_and_then_the_silence_marker(self):
        choice = _ask(self.agent, _request(f"a {discord_room.REACTION_PHRASE}"))
        (call,) = choice["message"]["tool_calls"]
        self.assertEqual("tool_calls", choice["finish_reason"])
        self.assertEqual(plugin_module.TOOL_NAMES["react"], call["function"]["name"])
        self.assertEqual(
            {"target_event_id": "discord:message:7", "reaction": discord_room.REACTION}, json.loads(call["function"]["arguments"])
        )
        # Hermes asks again with the tool's result: the move is made, and nothing more is said.
        after = _ask(self.agent, _request(f"a {discord_room.REACTION_PHRASE}", tool_result=json.dumps({"result": "Done"})))
        self.assertEqual(plugin_module.SILENCE_MARKER, after["message"]["content"])
        self.assertEqual([("react", "discord:message:7")], [(move["role"], move["trigger"]) for move in self.agent.moves])

    def test_a_call_without_tools_is_hermes_naming_its_session_and_is_not_a_move(self):
        self.assertEqual("Room", _ask(self.agent, _request("anything", tools=False))["message"]["content"])
        self.assertEqual([], self.agent.moves)
        self.assertEqual(0, len(self.agent.requests()), "only the agent's own calls are kept")

    def test_without_a_script_every_turn_is_the_answer(self):
        plain = standin.ScriptedHermesAgent("one answer")
        self.addCleanup(plain.close)
        self.assertEqual("one answer", _ask(plain, _request(f"a {discord_room.REACTION_PHRASE}"))["message"]["content"])
        self.assertEqual([], plain.moves)

    def test_what_a_turn_showed_of_its_trigger_is_read_from_hermes_requests(self):
        _ask(self.agent, _request("what's a sensible default timeout?"))
        self.assertEqual({"discord:message:7"}, set(standin.received_triggers(self.agent.requests())))


class HermesChecksTest(unittest.TestCase):
    def test_a_harness_that_posts_itself_fits_a_plain_message_about_the_graded_one(self):
        outcome = checks.discord_moment_outcome
        message = {"kind": "message", "origin_event_id": "e2", "where": "hermes"}
        host = {"posts_itself": True, "channel": "hermes", "thread": "retry details"}
        self.assertEqual(checks.FITS, outcome("reply", reached=True, graded_turns=1, actions=[message], graded_event="e2", **host))
        self.assertEqual(checks.MISSES, outcome("reply", reached=True, graded_turns=1, actions=[{**message, "origin_event_id": "e1"}], graded_event="e2", **host))
        self.assertEqual(checks.MISSES, outcome("reply", reached=True, graded_turns=1, actions=[{**message, "kind": "reply"}], graded_event="e2", **host))
        # The wire shows it posted as a Discord reply: Hermes now replies, which the pin does not allow; a plain message has no target.
        self.assertEqual(checks.MISSES, outcome("reply", reached=True, graded_turns=1, actions=[{**message, "replied_to": "9"}], graded_event="e2", **host))
        self.assertEqual(checks.FITS, outcome("reply", reached=True, graded_turns=1, actions=[{**message, "replied_to": None}], graded_event="e2", **host))
        self.assertEqual(checks.MISSES, outcome("reply", reached=True, graded_turns=1, actions=[message, message], graded_event="e2", **host))
        self.assertEqual(checks.NOT_DELIVERED, outcome("reply", reached=False, graded_turns=0, actions=[], graded_event="e2", **host))
        # Others read as they did: a reply to the agent's post still needs a Discord reply.
        self.assertEqual(checks.MISSES, outcome("reply", reached=True, graded_turns=1, actions=[message], graded_event="e2"))
        self.assertEqual(checks.FITS, outcome("post", reached=True, graded_turns=1, actions=[message], graded_event="e2", **host))
        reaction = {"kind": "reaction", "target_event_id": "e2"}
        self.assertEqual(checks.FITS, outcome("reaction", reached=True, graded_turns=1, actions=[reaction], graded_event="e2", **host))

    def test_the_answer_to_a_question_in_a_thread_is_pinned_to_the_main_channel(self):
        outcome = checks.discord_moment_outcome
        message = {"kind": "message", "origin_event_id": "e2", "where": "hermes"}
        host = {"posts_itself": True, "channel": "hermes", "thread": "retry details"}
        self.assertEqual(checks.FITS, outcome("thread-reply", reached=True, graded_turns=1, actions=[message], graded_event="e2", **host))
        # The gap closed: the answer landed in the thread. The pin fails and says so, until the docs follow.
        landed = [{**message, "where": "retry details"}]
        self.assertEqual(checks.MISSES, outcome("thread-reply", reached=True, graded_turns=1, actions=landed, graded_event="e2", **host))
        moments = [{"name": "thread-question", "expect": "thread-reply", "thread": discord_room.THREAD, "outcome": checks.MISSES,
                    "actions": [{"kind": "message", "text": "x"}]}]
        failed = checks.discord_scripted_outcomes(moments, discord_room.HERMES_EXPECTED, notes=discord_room.HERMES_NOTES)
        self.assertFalse(failed.ok)
        self.assertIn("thread-question reads 'misses', not 'fits' (Hermes posts its answer in the main channel", failed.detail)
        self.assertIn("update the pin and its docs", failed.detail)
        # The thread note names one cause: it is not attached when the person's message never reached Hermes, or off a thread.
        unheard = [{**moments[0], "outcome": checks.NOT_DELIVERED}]
        self.assertEqual("thread-question reads 'not delivered', not 'fits'", checks.discord_scripted_outcomes(
            unheard, discord_room.HERMES_EXPECTED, notes=discord_room.HERMES_NOTES).detail.split("; ")[0])
        self.assertNotIn("main channel", checks.discord_scripted_outcomes(unheard, discord_room.HERMES_EXPECTED, notes=discord_room.HERMES_NOTES).detail)
        elsewhere = [{**moments[0], "name": "reply", "expect": "reply"}]
        elsewhere[0].pop("thread")
        self.assertNotIn("main channel", checks.discord_scripted_outcomes(
            elsewhere, discord_room.HERMES_EXPECTED, notes={"reply": discord_room.HERMES_NOTES["thread-question"]}).detail)

    def test_an_answer_that_arrives_as_a_discord_reply_fails_the_plain_message_pin_and_says_so(self):
        outcome, scripted = checks.discord_moment_outcome, checks.discord_scripted_outcomes
        host = {"posts_itself": True, "channel": "hermes", "thread": "retry details"}
        replied = {"kind": "message", "text": discord_room.SCRIPTED_REPLY, "origin_event_id": "e2", "where": None, "replied_to": "100"}
        moments = [{"name": "reply", "expect": "reply", "outcome": outcome("reply", reached=True, graded_turns=1, actions=[replied], graded_event="e2", **host),
                    "actions": [replied]}]
        self.assertEqual(checks.MISSES, moments[0]["outcome"])
        failed = scripted(moments, discord_room.HERMES_EXPECTED, notes=discord_room.HERMES_NOTES, reply_note=discord_room.HERMES_REPLY_NOTE)
        self.assertFalse(failed.ok)
        self.assertIn("reply's message was posted as a Discord reply to 100 (Hermes now replies: update the plain-message pin and the docs)", failed.detail)
        self.assertNotIn("main channel", failed.detail, "the reply is not blamed on the thread pin")
        plain = [{**moments[0], "outcome": checks.FITS, "actions": [{**replied, "replied_to": None}]}]
        self.assertTrue(scripted(plain, discord_room.HERMES_EXPECTED, notes=discord_room.HERMES_NOTES, reply_note=discord_room.HERMES_REPLY_NOTE).ok)
        # Only a harness pinned to plain messages is asked: with no reply note, a reply is not looked for.
        self.assertNotIn("posted as a Discord reply", scripted(moments, discord_room.HERMES_EXPECTED).detail)

    def test_the_wire_decides_whether_a_harness_posted_message_replied(self):
        effects = [
            {"kind": "message", "where": "hermes", "text": "plain", "reply_to": None},
            {"kind": "message", "where": "hermes", "text": "a reply", "reply_to": "7"},
            {"kind": "message", "where": "hermes", "text": "both", "reply_to": "8"},
            {"kind": "message", "where": "hermes", "text": "both", "reply_to": None},
        ]
        found = discord_room.replied_to
        self.assertIsNone(found({"text": "plain"}, effects))
        self.assertEqual("7", found({"text": "a reply"}, effects))
        self.assertIsNone(found({"text": "both"}, effects), "one plain write matches it")
        self.assertIsNone(found({"text": "never posted"}, effects), "nothing on the wire: not a reply")

    def test_hermes_expected_actions_are_plain_messages_and_one_reaction(self):
        self.assertEqual(
            {"post": "message", "reply": "message", "reaction": "reaction", "thread-reply": "message"},
            {expect: action["kind"] for expect, action in discord_room.HERMES_EXPECTED.items()},
        )
        self.assertEqual(
            {name: action["text"] for name, action in discord_room.EXPECTED.items() if "text" in action},
            {name: action["text"] for name, action in discord_room.HERMES_EXPECTED.items() if "text" in action},
            "the same words as every column",
        )
        self.assertEqual({"first-message": checks.REACHED, "thread": checks.REACHED}, discord_room.HERMES_PINS)
        self.assertEqual(["thread-question"], list(discord_room.HERMES_NOTES))

    def test_a_process_that_declares_no_gap_at_its_start_is_recorded_and_not_failed(self):
        clean = {"bot": "Vigil", "resumed": True, "identified_again": False, "message_reached": True, "transport_gaps": [], "participant_gaps": []}
        start = {"process": "hermes gateway run", "gap": None, "declared": False}
        self.assertFalse(checks.discord_continuity(start, [clean], gaps_fail=False).ok, "the other columns must see the gap they declare")
        recorded = checks.discord_continuity(start, [clean], gaps_fail=False, start_required=False)
        self.assertTrue(recorded.ok, recorded.detail)
        self.assertIn("declares no start gap", recorded.detail)
        # Op 7 is still checked: a bot that identified again, or lost the message, fails.
        self.assertFalse(checks.discord_continuity(start, [{**clean, "identified_again": True}], gaps_fail=False, start_required=False).ok)
        self.assertFalse(checks.discord_continuity(start, [{**clean, "message_reached": False}], gaps_fail=False, start_required=False).ok)
        self.assertFalse(checks.discord_continuity(start, [], gaps_fail=False, start_required=False).ok)
        # Pinned absent (Hermes's plugin, a known gap): no start gap passes; one that appears fails and says to update the pin.
        pinned = checks.discord_continuity(start, [clean], gaps_fail=True, start_required=None)
        self.assertTrue(pinned.ok, pinned.detail)
        self.assertIn("declares no start gap", pinned.detail)
        declared = {"process": "hermes gateway run", "gap": "hermes:gap:1", "declared": True}
        now = checks.discord_continuity(declared, [clean], gaps_fail=True, start_required=None)
        self.assertFalse(now.ok)
        self.assertIn("now declares a gap when it starts (hermes:gap:1): update the pin, docs/rehearsal.md, the CHANGELOG and the plugin README", now.detail)
        # Recorded (False) still shows a declared gap without failing; every column but Hermes requires it.
        self.assertTrue(checks.discord_continuity(declared, [clean], gaps_fail=False, start_required=False).ok)
        self.assertTrue(checks.discord_continuity(declared, [clean], gaps_fail=False).ok)
        # And after op 7 a gap fails Hermes (it marks none), where the reference only records its own.
        gap = {**clean, "participant_gaps": ["hermes:gap:2"]}
        self.assertFalse(checks.discord_continuity(start, [gap], gaps_fail=True, start_required=None).ok)
        self.assertTrue(checks.discord_continuity(start, [gap], gaps_fail=False, start_required=None).ok)
        shown = record._discord_lines({"start_gap": {**start, "detail": "no gap"}})
        self.assertIn("- Start: no gap", shown)
        self.assertNotIn("never saw it", " ".join(shown))
        self.assertIn("never saw it", " ".join(record._discord_lines({"start_gap": {"gap": None, "detail": "x"}})))

    def test_the_hermes_leg_pins_its_known_gaps_in_the_checks_and_every_other_column_requires_them_closed(self):
        import inspect

        defaults = inspect.signature(discord_room.DiscordRoom.checks).parameters
        self.assertEqual((True, True, True), tuple(defaults[name].default for name in ("start_required", "reply_resolves", "own_reaction_remembered")))
        with tempfile.TemporaryDirectory() as directory:
            leg = discord_room.HermesGatewayLeg(_context(Path(directory)))
            with mock.patch.object(leg.discord, "checks", return_value=[]) as called:
                leg.room_checks({"moments": []})
        self.assertEqual(
            {"gaps_fail": True, "start_required": None, "reply_resolves": False, "own_reaction_remembered": False},
            {key: called.call_args.kwargs[key] for key in ("gaps_fail", "start_required", "reply_resolves", "own_reaction_remembered")},
        )
        # Not Hermes: the transport columns and the reference ask for all three.
        for source in (inspect.getsource(discord_room.OnTheTransport.room_checks), inspect.getsource(discord_room.ReferenceLeg.room_checks)):
            self.assertNotIn("start_required", source)
            self.assertNotIn("reply_resolves", source)
            self.assertNotIn("own_reaction_remembered", source)

    def test_typing_is_counted_from_the_requests_the_bot_made_not_from_a_route(self):
        # The stand-in serves no typing route, so such a request has no route template on the wire: it is answered 599.
        records = [
            {"kind": "http", "bot": "Vigil", "method": "POST", "decoded_path": "/api/v10/channels/5/typing", "status": 599},
            {"kind": "http", "bot": "Vigil", "method": "POST", "decoded_path": "/api/v10/channels/7/typing", "status": 599},
            {"kind": "http", "bot": "Vigil", "method": "POST", "decoded_path": "/api/v10/channels/5/messages", "route": "/channels/{channel}/messages", "status": 200},
            {"kind": "http", "bot": "Vigil", "method": "GET", "decoded_path": "/api/v10/channels/5/typing", "status": 599},
            {"kind": "http", "bot": "Other", "method": "POST", "decoded_path": "/api/v10/channels/5/typing", "status": 599},
            {"kind": "unknown", "bot": "Vigil", "method": "POST", "path": "/api/v10/channels/5/typing"},
        ]
        self.assertEqual(2, discord_room.typing_calls(records, "Vigil"))
        self.assertEqual(0, discord_room.typing_calls([], "Vigil"))
        self.assertNotIn(("POST", "/channels/{channel}/typing"), rest.ROUTES, "typing stays unserved: a scene that starts a fresh run fails discord-standin-clean")

    def test_every_call_hermes_must_make_has_a_route_of_its_own_on_the_standin(self):
        served = {f"{method} {template}" for method, template in rest.ROUTES}  # as `wire_calls` names a call from the wire
        for call in discord_room.HERMES_CALLS:
            with self.subTest(call=call):
                self.assertIn(call, served)
        self.assertEqual(len(discord_room.HERMES_CALLS), len(set(discord_room.HERMES_CALLS)))


def _context(base: Path, **extra) -> SimpleNamespace:
    net = base / "net.json"
    net.write_text(json.dumps({"tls": {"cert": "c", "key": "k"}, "leaf_sha256": "abc"}))
    (base / "hermes-home").mkdir(exist_ok=True)
    secrets = {"OPENROUTER_API_KEY": "placeholder-key", "REHEARSAL_CANARY": "canary-value"}
    values = dict(
        original_env={discord_room.NET_ENV: str(net)},
        options=SimpleNamespace(discord_python=None, expect_version=None),
        base=base,
        out=base / "out",
        profile={"display_name": "Vigil", "names": ["Vigil"], "instructions": "Take part."},
        env={"PATH": "/usr/bin", "HOME": str(base / "home"), **secrets},
        secrets=dict(secrets),
        homes={"HERMES_HOME": str(base / "hermes-home")},
        route=routes.hermes_route("anthropic/claude-haiku-4.5"),
        attention={"model": "scripted", "provider": "scripted"},
        attention_endpoint=None,
    )
    values.update(extra)
    return SimpleNamespace(**values)


class _Leg(unittest.TestCase):
    def leg(self) -> discord_room.HermesGatewayLeg:
        directory = Path(tempfile.mkdtemp(prefix="hermes-leg-"))
        self.addCleanup(shutil.rmtree, directory, True)
        self.base = directory
        leg = discord_room.HermesGatewayLeg(_context(directory))
        leg.home = directory / "hermes-home"
        return leg

    def started(self) -> discord_room.HermesGatewayLeg:
        """The leg with the stand-in running on plain loopback and its scripted model, as `prepare` has them before Hermes starts."""

        leg = self.leg()
        scenes = [load_scene(spec.scene) for spec in discord_room.MOMENTS]
        spec, leg.discord.members = discord_room.world_spec(discord_room.HERMES, scenes, agent="Vigil")
        leg.discord.ctx.out.mkdir(parents=True, exist_ok=True)
        leg.discord.fd = FakeDiscord(spec, leg.discord.ctx.out).start()
        self.addCleanup(leg.discord.fd.stop)
        leg.room_id = leg.discord.channel_id = leg.discord.fd.world.channel(discord_room.HERMES).id
        leg.discord.agent_id = leg.discord.fd.world.member("Vigil").id
        leg.agent = standin.ScriptedHermesAgent(probe.SCRIPTED_ANSWER, script=SCRIPT)
        self.addCleanup(leg.agent.close)
        return leg


class ProfileTest(_Leg):
    def test_hermes_gets_the_readmes_room_settings_and_variables_and_nothing_secret_in_a_file(self):
        leg = self.started()
        _, config_path = leg.room_config({"hermes": routes.hermes_section(leg.room_id)})
        leg.write_home(config_path, ["compression", "vision"], 50)
        config = json.loads((leg.home / "config.yaml").read_text())
        environment = dict(line.split("=", 1) for line in (leg.home / ".env").read_text().splitlines())
        room = leg.discord.fd.world.role("room").id
        # The README's `discord:` block, with the bound channel, and the peer-agent settings the probe adds.
        self.assertEqual(
            {"typing_indicator": False, "reactions": False, "free_response_channels": [leg.room_id], "free_response_auto_thread": False,
             "allow_bots": "all", "bots_require_inline_mention": False},
            config["discord"],
        )
        self.assertEqual(kit.room_settings("discord", channel=leg.room_id)["display"], config["display"])
        self.assertTrue(config["thread_sessions_per_user"])
        self.assertEqual(["clarify", "cronjob"], config["agent"]["disabled_toolsets"])
        entry = config["plugins"]["entries"]["nunchi-room"]
        self.assertEqual(["nunchi-room"], config["plugins"]["enabled"])
        self.assertEqual((True, True, str(config_path)), (entry["allow_gateway_injection"], entry["allow_platform_actions"], entry["settings"]["config_path"]))
        self.assertEqual(50, config["_config_version"], "stamped as `hermes setup` does")
        # The README's profile `.env`: the room's role and no user allowlist, the turns' identity, no text batching.
        self.assertEqual(
            {"DISCORD_ALLOWED_USERS": "", "DISCORD_ALLOWED_ROLES": room, "GATEWAY_ALLOWED_USERS": routes.HERMES_TURN_USER,
             "HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS": "0"},
            environment,
        )
        self.assertTrue(all(person.roles and room in person.roles for person in leg.discord.fd.world.members.values() if not person.bot),
                        "every person the scenes play has the room's role, which Hermes lets in")
        # The scripted model through the custom provider and base_url, for the agent and every auxiliary task.
        self.assertEqual(("custom", leg.agent.base_url), (config["model"]["provider"], config["model"]["base_url"]))
        self.assertEqual({"compression", "vision"}, set(config["auxiliary"]))
        self.assertTrue(all(task["base_url"] == leg.agent.base_url for task in config["auxiliary"].values()))
        # The plugin directory is where `hermes plugins install` puts it, without bytecode; tools are shown directly.
        self.assertTrue((leg.home / "plugins" / "nunchi-room" / "plugin.yaml").is_file())
        self.assertEqual({"enabled": "off"}, config["tools"]["tool_search"])
        # No file holds a token or a key: the bot's token goes in the environment only.
        token = leg.discord.fd.token("Vigil")
        for path in (leg.home / "config.yaml", leg.home / ".env", config_path):
            text = path.read_text()
            self.assertNotIn(token, text, path.name)
            self.assertNotIn("placeholder-key", text, path.name)
        self.assertEqual(["hermes config.yaml", "hermes profile .env"], [name for name, _ in leg.configs[-2:]])

    def test_the_plugins_config_binds_the_discord_channel_as_the_plugin_names_it(self):
        leg = self.started()
        leg.actor_id = f"{discord_room.HERMES_ACTOR}:{leg.discord.agent_id}"
        leg.scope = f"discord:{leg.room_id}"
        config, _ = leg.room_config({"hermes": routes.hermes_section(leg.room_id)})
        self.assertEqual("discord", config["binding"]["platform"])
        self.assertEqual((leg.room_id, leg.scope, leg.actor_id), (config["binding"]["room_id"], config["binding"]["continuity_scope_id"], config["binding"]["actor_id"]))
        self.assertTrue(config["binding"]["actor_id"].startswith("discord:user:"), "the plugin's ids, not the transport's discord:actor:")
        self.assertEqual(["DISCORD_BOT_TOKEN", "OPENROUTER_API_KEY"], config["hermes"]["withheld_env"])
        self.assertEqual(routes.HERMES_TURN_USER, config["hermes"]["turn_user_id"])

    def test_hermes_gets_its_home_its_token_its_models_placeholder_key_and_the_canary_only(self):
        leg = self.started()
        own = leg.own_environment()
        self.assertEqual({"HERMES_HOME", "DISCORD_BOT_TOKEN", "OPENROUTER_API_KEY", "REHEARSAL_CANARY"}, set(own))
        self.assertEqual(leg.discord.fd.token("Vigil"), own["DISCORD_BOT_TOKEN"])
        environment, where = leg.discord.environment(discord_room.HERMES, own)
        self.assertEqual({"PATH", "HOME", "TMPDIR", *own}, set(environment))
        self.assertTrue(environment["HOME"].startswith(str(where)))
        self.assertFalse([name for name in environment if name.lower().endswith("_proxy")])

    def test_hermes_runs_as_a_user_starts_it(self):
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            python = bin_dir / "python"
            python.write_text("")
            self.assertEqual([str(python), "-c"], discord_room.hermes_argv(str(python))[:2], "no console script: its own body")
            self.assertEqual(["gateway", "run"], discord_room.hermes_argv(str(python))[-2:])
            self.assertIn("from hermes_cli.main import main", discord_room.hermes_argv(str(python))[2])
            (bin_dir / "hermes").write_text("#!/bin/sh\n")
            self.assertEqual([str(bin_dir / "hermes"), "gateway", "run"], discord_room.hermes_argv(str(python)))

    def test_a_python_without_hermes_could_not_run(self):
        leg = self.leg()
        leg.discord.python = sys.executable
        with self.assertRaisesRegex(probe.CouldNotRun, "Hermes cannot be read"):
            leg.run_facts("raise SystemExit('no hermes here')", {"PATH": os.environ.get("PATH", "/usr/bin")})
        self.assertEqual({"a": 1}, leg.run_facts("import json; print('noise'); print(json.dumps({'a': 1}))", {"PATH": os.environ.get("PATH", "/usr/bin")}))

    def test_the_hermes_leg_is_in_the_discord_room_and_the_probe_accepts_it_only_scripted(self):
        self.assertIs(discord_room.HermesGatewayLeg, discord_room.LEGS["hermes"])
        leg_class, moments, route = probe._room_parts(probe.Options(harness="hermes", out=Path("x"), room="discord", scripted=True))
        self.assertEqual((discord_room.HermesGatewayLeg, discord_room.MOMENTS, "hermes"), (leg_class, moments, route.harness))
        self.assertIs(probe.LEGS["hermes"], probe.HermesLeg, "the in-process room still runs the kit's gateway")
        self.assertTrue(discord_room.HermesGatewayLeg.harness_posts)
        self.assertIs(discord_room.HERMES_PINS, discord_room.HermesGatewayLeg.pins)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(probe.EXIT_USAGE, probe.main(["--harness", "hermes", "--room", "discord", "--out", directory]))
            with mock.patch.object(probe, "run_probe", return_value=0) as run:
                self.assertEqual(0, probe.main(["--harness", "hermes", "--room", "discord", "--scripted", "--out", directory]))
        options = run.call_args.args[0]
        self.assertEqual(("hermes", "discord", True), (options.harness, options.room, options.scripted))


def _receipt(request_id: str, stage: str, **body) -> str:
    writer = {"observation": "observation-provider", "attention": "attention-engine", "participant-host": "participant-host", "transport": "transport"}[stage]
    return json.dumps({"body": body, "request_id": request_id, "stage": stage, "writer": writer})


def _turn_receipts(request_id: str, trigger: str, *, disposition: str = "WAKE", host: dict | None = None, transport: dict | None = None) -> list[str]:
    lines = [
        _receipt(request_id, "observation", trigger_event_id=trigger, coverage={"continuity": "restart-safe", "has_gaps": False, "has_restart_gap": False}),
        _receipt(request_id, "attention", effective_disposition=disposition, classifier={"provider": "scripted"}),
    ]
    if host is not None:
        lines.append(_receipt(request_id, "participant-host", wake_source="WAKE", invoked=True, **host))
    if transport is not None:
        lines.append(_receipt(request_id, "transport", **transport))
    return lines


class OutsideTheProcessTest(_Leg):
    """What the leg reads from files the plugin wrote in its own process, written here as the plugin writes them."""

    def state(self, leg: discord_room.HermesGatewayLeg) -> Path:
        state = leg.discord.state
        state.mkdir(parents=True, exist_ok=True)
        return state

    @staticmethod
    def reaction_on_the_wire(message: str, emoji: str) -> dict:
        """The stand-in's record of the bot's 2xx PUT of a reaction (`discord_room.wire_writes` reads it)."""

        return {"kind": "http", "bot": "Vigil", "method": "PUT", "status": 204, "route": "/channels/{channel}/messages/{message}/reactions/{emoji}/@me",
                "decoded_path": f"/api/v10/channels/5/messages/{message}/reactions/{emoji}/@me"}

    def write_run(self, leg: discord_room.HermesGatewayLeg, receipts: list[str], observed: dict[str, tuple[str, str]] | None = None) -> None:
        state = self.state(leg)
        (state / "hermes-plugin-receipts.jsonl").write_text("\n".join(receipts) + "\n")
        events = [
            {"event": {"id": f"nunchi:delivered:{request_id}", "text": text, "reply_to_event_id": origin, "type": "message"}}
            for request_id, (text, origin) in (observed or {}).items()
        ]
        # The plugin's file is `<state_prefix>observations.jsonl`, its audits beside it with a suffix.
        (state / "hermes-plugin-observations.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))
        (state / "hermes-plugin-observations.jsonl.delivery-audit.jsonl").write_text(json.dumps({"outcome": "recorded", "event_id": "discord:message:1"}) + "\n")

    def test_a_turn_is_an_invoked_host_and_its_action_is_what_the_transport_receipt_and_the_library_recorded(self):
        leg = self.leg()
        # What the scripted model asked for, which none of the committed actions may be taken from: other words, another
        # emoji, another message. The wire shows what Hermes did.
        leg.agent = SimpleNamespace(
            moves=[
                {"trigger": "discord:message:2", "role": "send", "arguments": {"text": "scripted words"}},
                {"trigger": "discord:message:3", "role": "react", "arguments": {"target_event_id": "discord:message:99", "reaction": "\N{PARTY POPPER}"}},
                {"trigger": "discord:message:5", "role": "send", "arguments": {"text": "unused"}},
            ]
        )
        leg.discord.fd = SimpleNamespace(wire=SimpleNamespace(records=[self.reaction_on_the_wire("3", "\N{THUMBS UP SIGN}")]))
        leg.discord.agent = "Vigil"
        delivered = {"transport": {"delivery": "unknown", "detail": HARNESS_DELIVERS}}
        receipts = [
            *_turn_receipts("r0", "discord:message:1", disposition="SUPPRESS"),
            *_turn_receipts("r1", "discord:message:2", host={"outcome": "unknown"}, **delivered),
            *_turn_receipts("r2", "discord:message:3", host={"outcome": "unknown"},
                            transport={"delivery": "sent", "detail": "Hermes added the reaction"}),
            *_turn_receipts("r3", "discord:message:4", host={"outcome": "silent"}),
            *_turn_receipts("r4", "discord:message:5", host={"outcome": "unknown"}),  # handed nothing: it failed
        ]
        self.write_run(leg, receipts, {"r1": ("the words the library recorded", "discord:message:2")})
        leg.read_turns()
        turns = {turn["request_id"]: turn for turn in leg.invocations}
        self.assertEqual(["r1", "r2", "r3", "r4"], list(turns), "a turn is a request the host invoked the harness for; a suppressed one is not")
        self.assertEqual({"kind": "message", "text": "the words the library recorded"}, turns["r1"]["result"])
        self.assertEqual({"kind": "reaction", "reaction": "\N{THUMBS UP SIGN}", "target_event_id": "discord:message:3"}, turns["r2"]["result"],
                         "the wire's reaction, not the model's call")
        self.assertEqual({"kind": "silence"}, turns["r3"]["result"])
        self.assertIsNone(turns["r4"]["result"])
        self.assertEqual([True, True, True, False], [turns[name]["bound"] for name in turns])
        self.assertIn("inferred", turns["r1"]["bound_evidence"])
        self.assertEqual("discord:message:2", turns["r1"]["trigger"])
        self.assertEqual("WAKE", turns["r1"]["source"])
        committed = {item["request_id"]: item for item in leg.committed}
        self.assertEqual(["r1", "r2"], list(committed))
        self.assertEqual(
            {"kind": "message", "text": "the words the library recorded", "origin_event_id": "discord:message:2", "delivery": "unknown", "detail": HARNESS_DELIVERS},
            {key: committed["r1"][key] for key in ("kind", "text", "origin_event_id", "delivery", "detail")},
        )
        self.assertEqual("the library's record of the delivered message", committed["r1"]["text_from"])
        self.assertIn("the wire", committed["r2"]["reaction_from"])
        self.assertEqual([], leg.harness_failures, "the library holds a record of what Hermes delivered")
        self.assertEqual(
            {"kind": "reaction", "reaction": "\N{THUMBS UP SIGN}", "target_event_id": "discord:message:3", "operation": "add", "delivery": "sent"},
            {key: committed["r2"][key] for key in ("kind", "reaction", "target_event_id", "operation", "delivery")},
        )
        self.assertEqual(5, len(leg.attention_calls))
        self.assertEqual(["SUPPRESS", "WAKE", "WAKE", "WAKE", "WAKE"], [call["disposition"] for call in leg.attention_calls])
        # Read again, nothing is counted twice.
        leg.read_turns()
        self.assertEqual((4, 2), (len(leg.invocations), len(leg.committed)))
        # The turn checks read it as they read any harness's.
        host = [r for r in leg.receipts() if r["stage"] == "participant-host"]
        problems = checks.turns_bound_and_ended(leg.invocations, host, leg.committed)
        self.assertFalse(problems.ok)
        self.assertEqual(1, problems.detail.count("never ended"), "only the turn that handed the room nothing")
        self.assertIn("turn r4 on discord:message:5 never ended", problems.detail)

    def test_without_the_librarys_record_of_a_delivery_the_words_are_missing_and_that_is_a_hard_problem(self):
        leg = self.leg()
        leg.agent = SimpleNamespace(moves=[{"trigger": "discord:message:2", "role": "send", "arguments": {"text": "from the script"}}])
        receipts = _turn_receipts("r1", "discord:message:2", host={"outcome": "unknown"}, transport={"delivery": "unknown", "detail": HARNESS_DELIVERS})
        self.write_run(leg, receipts)
        leg.read_turns()
        (item,) = leg.committed
        # The receipt says Hermes delivered it; the library holds nothing, and the scripted model's words are not put in its place.
        self.assertIsNone(item["text"])
        self.assertIn("missing", item["text_from"])
        self.assertEqual("discord:message:2", item["origin_event_id"], "the receipt's trigger")
        self.assertEqual(["turn r1: the transport receipt says Hermes delivered its answer, but the library's room log holds no record of it "
                          "(nunchi:delivered:r1)"], leg.harness_failures)
        problems = checks.turns_bound_and_ended(leg.invocations, [r for r in leg.receipts() if r["stage"] == "participant-host"], leg.committed,
                                                harness_failures=leg.harness_failures)
        self.assertFalse(problems.ok)
        self.assertIn("holds no record of it", problems.detail)
        # Read again once the library has written it (the transport receipt comes first): the same action, now with its words.
        self.write_run(leg, receipts, {"r1": ("the words the library recorded", "discord:message:2")})
        leg.read_turns()
        self.assertEqual(1, len(leg.committed))
        self.assertEqual(("the words the library recorded", "the library's record of the delivered message"), (item["text"], item["text_from"]))
        self.assertEqual([], leg.harness_failures)
        self.assertEqual("the words the library recorded", leg.invocations[0]["result"]["text"])

    def test_a_reaction_the_wire_does_not_show_is_missing_not_the_models_call(self):
        leg = self.leg()
        leg.agent = SimpleNamespace(
            moves=[{"trigger": "discord:message:3", "role": "react", "arguments": {"target_event_id": "discord:message:3", "reaction": "\N{THUMBS UP SIGN}"}}]
        )
        leg.discord.fd = SimpleNamespace(wire=SimpleNamespace(records=[]))
        leg.discord.agent = "Vigil"
        self.write_run(leg, _turn_receipts("r2", "discord:message:3", host={"outcome": "unknown"},
                                           transport={"delivery": "sent", "detail": "Hermes added the reaction"}))
        leg.read_turns()
        (item,) = leg.committed
        self.assertEqual(("reaction", None, None), (item["kind"], item["reaction"], item["target_event_id"]))
        self.assertIn("missing", item["reaction_from"])
        # It reads `sent` and no write matches it: discord-writes-reconciled fails.
        self.assertIn("matches 0 write(s)", checks.discord_writes_reconciled(leg.committed, []).detail)
        # The nth reaction turn takes the nth reaction on the wire, and later reads fill it in.
        leg.discord.fd.wire.records.append(self.reaction_on_the_wire("3", "\N{THUMBS UP SIGN}"))
        leg.read_turns()
        self.assertEqual(("\N{THUMBS UP SIGN}", "discord:message:3"), (item["reaction"], item["target_event_id"]))
        self.assertTrue(checks.discord_writes_reconciled(leg.committed, discord_room.wire_writes(leg.discord.records, "Vigil")).ok)

    def test_the_library_records_what_hermes_delivered_in_the_observation_log_and_nowhere_else(self):
        leg = self.leg()
        self.assertEqual({}, discord_room.delivered_messages(self.base / "no-such-directory"))
        self.write_run(leg, [], {"discord:1:abc": ("posted", "discord:message:9")})
        found = discord_room.delivered_messages(leg.discord.state)
        self.assertEqual(["discord:1:abc"], list(found))
        self.assertEqual(("posted", "discord:message:9"), (found["discord:1:abc"]["text"], found["discord:1:abc"]["reply_to_event_id"]))
        # The audits beside the log hold no message: only the observation file is read.
        (leg.discord.state / "x.delivery-audit.jsonl").write_text(json.dumps({"event": {"id": "nunchi:delivered:other", "text": "no"}}) + "\n")
        self.assertEqual(["discord:1:abc"], list(discord_room.delivered_messages(leg.discord.state)))

    def test_the_room_log_holds_the_agents_own_post_under_its_discord_id_or_under_the_librarys_own(self):
        from nunchi.participant import DELIVERED_EVENT_PREFIX

        self.assertEqual(DELIVERED_EVENT_PREFIX, discord_room.DELIVERED_PREFIX, "the prefix the library files a harness-posted message under")
        leg = self.leg()
        leg.discord.agent_id = "55"
        state = self.state(leg)
        own, other = f"{discord_room.HERMES_ACTOR}:55", f"{discord_room.HERMES_ACTOR}:9"
        events = [
            {"id": "discord:message:10", "type": "message", "author_id": other},
            {"id": "discord:message:11", "type": "message", "author_id": own},
            {"id": f"{DELIVERED_EVENT_PREFIX}r1", "type": "message", "author_id": own, "reply_to_event_id": "discord:message:10"},
            {"id": "discord:reaction:1", "type": "reaction", "author_id": own, "target_event_id": "discord:message:10"},
        ]
        (state / "x-observations.jsonl").write_text("".join(json.dumps({"event": event}) + "\n" for event in events) + "not json\n")
        (state / "x-observations.jsonl.delivery-audit.jsonl").write_text(json.dumps({"event": {"id": "discord:message:12"}}) + "\n")
        self.assertEqual({event["id"] for event in events}, set(discord_room.room_events(state)))
        # A reply to the agent's own post resolves when the log holds that post under the id the reply names.
        self.assertTrue(leg.discord.holds_own_post("discord:message:11"))
        self.assertFalse(leg.discord.holds_own_post("discord:message:10"), "another author's")
        self.assertFalse(leg.discord.holds_own_post("discord:message:12"), "not in the observation log")
        self.assertFalse(leg.discord.holds_own_post("discord:reaction:1"), "not a message")
        # Hermes's own post is there only as the library's own id, which no reply names.
        self.assertFalse(leg.discord.holds_own_post("discord:message:99"))
        self.assertEqual(["r1"], list(discord_room.delivered_messages(state)))

    def test_a_turn_is_open_from_attentions_wake_until_the_host_receipt(self):
        leg = self.leg()
        self.write_run(leg, [*_turn_receipts("r0", "discord:message:1", disposition="SUPPRESS"), *_turn_receipts("r1", "discord:message:2")])
        self.assertEqual(["r1"], leg.open_turns())
        self.write_run(leg, [*_turn_receipts("r1", "discord:message:2", host={"outcome": "silent"})])
        self.assertEqual([], leg.open_turns())

    def test_settle_waits_for_an_open_turn_and_a_quiet_wire(self):
        leg = self.started()
        leg.ctx.attention_endpoint = SimpleNamespace(judged=[])
        self.write_run(leg, _turn_receipts("r1", "discord:message:2"))

        def end_the_turn() -> None:
            time.sleep(1.0)
            self.write_run(leg, _turn_receipts("r1", "discord:message:2", host={"outcome": "silent"}))

        threading.Thread(target=end_the_turn, daemon=True).start()
        began = time.monotonic()
        self.assertTrue(leg.settle(30))
        self.assertGreaterEqual(time.monotonic() - began, 1.0, "not while the turn is open")
        self.write_run(leg, _turn_receipts("r2", "discord:message:3"))
        self.assertFalse(leg.settle(0.5), "an open turn does not settle")

    def test_a_leg_that_could_not_start_collects_and_closes_without_a_process(self):
        leg = self.leg()  # prepare failed before Hermes was launched: could-not-run
        leg.ctx.out.mkdir(parents=True)
        leg.collect()
        leg.close()
        self.assertEqual([], leg.invocations)
        self.assertEqual("hermes gateway run took 0 turn(s) through the plugin and committed 0 action(s); its session records 0 model call(s)",
                         leg.reports["hermes"]["verdict"])
        self.assertEqual([], leg.processes, "no environment was recorded for a process that never ran")

    def test_the_start_is_what_the_plugin_says_of_it(self):
        leg = self.leg()
        self.write_run(leg, _turn_receipts("r1", "discord:message:2"))
        start = leg.start_facts()
        self.assertEqual((None, False), (start["gap"], start["declared"]))
        self.assertIn("declares no gap when it starts", start["detail"])
        self.assertIn("'restart-safe'", start["detail"])
        (leg.discord.state / "hermes-plugin-observations.jsonl.delivery-audit.jsonl").write_text(
            json.dumps({"outcome": "continuity-gap", "delivery_id": "hermes:gap:1"}) + "\n"
        )
        start = leg.start_facts()
        self.assertEqual(("hermes:gap:1", True), (start["gap"], start["declared"]))

    def test_the_leg_waits_for_hermes_own_record_of_a_running_gateway_with_discord_connected(self):
        leg = self.leg()
        process = SimpleNamespace(alive=lambda: True, tail=lambda: "", process=None)
        state = leg.home / "gateway_state.json"

        def write(**fields) -> None:
            state.write_text(json.dumps(fields))

        write(gateway_state="starting", platforms={"discord": {"state": "connected"}})
        threading.Timer(0.6, write, kwargs={"gateway_state": "running", "platforms": {"discord": {"state": "connecting"}}}).start()
        threading.Timer(1.2, write, kwargs={"gateway_state": "running", "platforms": {"discord": {"state": "connected"}}}).start()
        began = time.monotonic()
        leg.wait_connected(process, timeout=20)
        self.assertGreaterEqual(time.monotonic() - began, 1.1)
        dead = SimpleNamespace(alive=lambda: False, tail=lambda: "boom", process=SimpleNamespace(poll=lambda: 1))
        write(gateway_state="starting", platforms={})
        with self.assertRaisesRegex(RuntimeError, "exited \\(1\\) before it connected: boom"):
            leg.wait_connected(dead, timeout=5)

    def test_what_hermes_posts_itself_is_delivered_when_the_wire_shows_exactly_that_text(self):
        leg = SimpleNamespace(
            harness_posts=True,
            discord=SimpleNamespace(column="hermes"),
            committed=[
                {"request_id": "r1", "kind": "message", "text": "the answer", "origin_event_id": "discord:message:2", "delivery": "unknown"},
                {"request_id": "r2", "kind": "message", "text": "a thread answer", "origin_event_id": "discord:message:3", "delivery": "unknown"},
                {"request_id": "r3", "kind": "message", "text": "never posted", "origin_event_id": "discord:message:4", "delivery": "unknown"},
            ],
            room_effects=lambda: [
                {"kind": "message", "where": "hermes", "text": "the answer", "reply_to": None},
                {"kind": "message", "where": "hermes", "text": "a thread answer", "reply_to": None},
            ],
        )
        moments = [
            {"name": "reply", "expect": "reply", "reached": True, "graded_turns": 1, "graded_event": "discord:message:2", "deliveries": [],
             "turns": [{"request_id": "r1", "trigger": "discord:message:2"}]},
            {"name": "thread-question", "expect": "thread-reply", "thread": discord_room.THREAD, "reached": True, "graded_turns": 1,
             "graded_event": "discord:message:3", "deliveries": [], "turns": [{"request_id": "r2", "trigger": "discord:message:3"}]},
            {"name": "lost", "expect": "reply", "reached": True, "graded_turns": 1, "graded_event": "discord:message:4", "deliveries": [],
             "turns": [{"request_id": "r3", "trigger": "discord:message:4"}]},
        ]
        discord_room.judge_discord_moments(leg, moments, {})
        self.assertEqual([True, True, False], [item["delivered"] for item in leg.committed])
        self.assertEqual(["hermes", "hermes", None], [moment["actions"][0]["where"] for moment in moments])
        self.assertEqual(["fits", "fits", "misses"], [moment["outcome"] for moment in moments])
        self.assertEqual("discord:message:3", moments[1]["actions"][0]["origin_event_id"])
        self.assertEqual([{"text": "a thread answer", "delivery": "unknown", "delivered": True}], moments[1]["posts"], "a plain message is a post")
        self.assertEqual([None, None], [moment["actions"][0]["replied_to"] for moment in moments[:2]], "the wire shows both posted plain")

    def test_an_answer_the_wire_shows_as_a_discord_reply_misses_and_names_the_pin_it_breaks(self):
        leg = SimpleNamespace(
            harness_posts=True,
            discord=SimpleNamespace(column="hermes", holds_own_post=lambda event_id: False),
            committed=[{"request_id": "r1", "kind": "message", "text": discord_room.SCRIPTED_REPLY, "origin_event_id": "discord:message:2",
                        "delivery": "unknown"}],
            room_effects=lambda: [{"kind": "message", "where": "hermes", "text": discord_room.SCRIPTED_REPLY, "reply_to": "100"}],
        )
        moments = [{"name": "reply", "expect": "reply", "reached": True, "graded_turns": 1, "graded_event": "discord:message:2", "deliveries": [],
                    "turns": [{"request_id": "r1", "trigger": "discord:message:2"}]}]
        discord_room.judge_discord_moments(leg, moments, {})
        (action,) = moments[0]["actions"]
        self.assertEqual(("100", None, "misses"), (action["replied_to"], action["where"], moments[0]["outcome"]))
        failed = checks.discord_scripted_outcomes(
            moments, discord_room.HERMES_EXPECTED, notes=discord_room.HERMES_NOTES, reply_note=discord_room.HERMES_REPLY_NOTE
        )
        self.assertIn("Hermes now replies: update the plain-message pin and the docs", failed.detail)
        # What the library committed does not match that write either, so the writes check fails too.
        committed = [{**leg.committed[0], "delivery": "unknown"}]
        self.assertFalse(checks.discord_writes_reconciled(committed, [{"kind": "message", "content": discord_room.SCRIPTED_REPLY, "reply_to": "100"}]).ok)


class DiscordRoomActorTest(unittest.TestCase):
    def test_the_plugins_ids_name_a_user_where_the_transports_name_an_actor(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            hermes = discord_room.DiscordRoom(_context(base), "hermes", actor=discord_room.HERMES_ACTOR)
            transport = discord_room.DiscordRoom(_context(base), "codex")
        self.assertEqual(("discord:user", "discord:actor"), (hermes.actor, transport.actor))


if __name__ == "__main__":
    unittest.main()
