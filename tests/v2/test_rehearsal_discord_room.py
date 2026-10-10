"""The probe's Discord room (step 9f, PR 3b): the scripts, the checks, and what the probe reads from the wire.

The lanes themselves run Nunchi's Discord processes at Discord's real
names, so they need the launcher (root, and namespaces) and run in CI's
scripted lanes. What is tested here needs neither: the scripted agents and
the plain-call participant, every ``discord-*`` check, the world and the
moments, and what the probe reads from the stand-in's wire, with the
stand-in on plain loopback driven by Nunchi's own transport clients through
the hooks they already have, as `test_fake_discord.py` does.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from nunchi.mcp_discord.authorization import ToolAuthorizer, make_tool_authorization
from nunchi.mcp_discord.gateway import GatewayProtocol
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient
from nunchi.mcp_discord.runner import GatewayRunner
from nunchi.mcp_discord.tools import ToolExecutor
from nunchi.mcp_discord.ws import WSClient
from nunchi.participant_model import _validate_inner_action

from evals.behavior.scene import load_scene
from evals.rehearsal import checks, discord_room, probe, standin
from evals.rehearsal.fake_discord.control import FakeDiscord

SCRIPT = discord_room.SCRIPT


def _turn(trigger: str, text: str, *, request_id: str = "req-1", **addressing) -> dict:
    return {
        "protocol": {"name": "nunchi.participant-turn", "version": 1},
        "binding": {"request_id": request_id},
        "wake": {"trigger_event_id": trigger, "events": [{"id": trigger, "text": text, **addressing}], "attention": {"source": "WAKE"}},
    }


def _tagged(turn: dict) -> str:
    document = json.dumps({"participant_turn": turn, "context_pages": []})
    return f"You are Vigil...\n\n<{standin.TURN_TAG}>{document}</{standin.TURN_TAG}>"


# -- the scripts --------------------------------------------------------------------------------------


class ScriptTest(unittest.TestCase):
    def test_each_graded_message_wakes_scripted_attention_only_where_it_should_and_gets_its_move(self):
        attention = standin.ScriptedAttention(spec.wake_phrase for spec in discord_room.MOMENTS if spec.wake_phrase)
        self.addCleanup(attention.close)
        moves = {"post": "send", "reply": "send", "reaction": "react"}
        for spec in discord_room.MOMENTS:
            scene = load_scene(spec.scene)
            for event in scene.events:
                with self.subTest(moment=spec.name, event=event["id"]):
                    body = {"messages": [{"content": json.dumps({"observation": {"trigger_event_id": "e", "events": [{"id": "e", "text": event["text"]}]}})}]}
                    disposition, _ = attention.disposition(body)
                    graded = event["id"] == scene.moments[0].event
                    self.assertEqual("WAKE" if graded and spec.wake_phrase else "SUPPRESS", disposition)
            if spec.expect not in moves:
                continue
            graded = next(event for event in scene.events if event["id"] == scene.moments[0].event)
            role, arguments = SCRIPT.move(_turn("discord:message:7", graded["text"]))
            self.assertEqual(moves[spec.expect], role, spec.name)
            if spec.expect == "reply":
                self.assertEqual({"text": discord_room.SCRIPTED_REPLY, "reply_to_event_id": "discord:message:7"}, arguments)
            elif spec.expect == "reaction":
                self.assertEqual({"target_event_id": "discord:message:7", "reaction": discord_room.REACTION}, arguments)
            else:
                self.assertEqual({"text": probe.SCRIPTED_ANSWER}, arguments)

    def test_every_scripted_action_is_one_a_plain_call_participant_may_return(self):
        for text in ("what's a sensible default timeout?", f"should we {discord_room.REPLY_PHRASE}?", f"a {discord_room.REACTION_PHRASE}"):
            with self.subTest(text=text):
                action = SCRIPT.action(_turn("discord:message:7", text))
                self.assertEqual(action, _validate_inner_action(action))
                self.assertEqual("discord:message:7", action["origin_event_id"])

    def test_the_newest_turn_is_found_wherever_each_harness_puts_it(self):
        first, newest = _turn("discord:message:1", "first"), _turn("discord:message:2", "newest", request_id="req-2")
        claude = {"model": "m", "messages": [{"role": "user", "content": [{"type": "text", "text": _tagged(newest)}]}], "tools": [{"name": "x"}]}
        codex = {"input": [{"type": "message", "content": [{"type": "input_text", "text": _tagged(first)}]},
                           {"type": "function_call_output", "output": "ok"},
                           {"type": "message", "content": [{"type": "input_text", "text": _tagged(newest)}]}]}
        plain = json.dumps({"participant_turn": newest, "context_pages": []})
        for body in (claude, codex, plain):
            with self.subTest(body=str(body)[:40]):
                self.assertEqual("req-2", standin.turn_document(body)["binding"]["request_id"])
        self.assertIsNone(standin.turn_document({"messages": [{"content": "no turn here"}]}))

    def test_the_scripted_participant_answers_in_the_protocols_envelope_and_keeps_each_answer(self):
        participant = standin.ScriptedParticipant(SCRIPT)
        self.addCleanup(participant.close)
        turn = _turn("discord:message:9", f"Vigil, {discord_room.REACTION_PHRASE} for you.")
        body = {"model": "m", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": json.dumps({"participant_turn": turn, "context_pages": []})}]}
        connection = http.client.HTTPConnection(participant.base_url.removeprefix("http://").split("/")[0], timeout=5)
        connection.request("POST", "/v1/chat/completions", json.dumps(body), {"Content-Type": "application/json"})
        response = connection.getresponse()
        answer = json.loads(response.read())
        connection.close()
        self.assertEqual(200, response.status)
        envelope = json.loads(answer["choices"][0]["message"]["content"])
        self.assertEqual({"protocol": turn["protocol"], "binding": {"request_id": "req-1"}}, {k: envelope[k] for k in ("protocol", "binding")})
        self.assertEqual("reaction", envelope["action"]["kind"])
        self.assertEqual([("req-1", "discord:message:9", "WAKE")], [(a["request_id"], a["trigger"], a["source"]) for a in participant.answers])
        self.assertEqual({"trigger": "discord:message:9", "mentioned_actor_ids": [], "reply_to_event_id": None}, participant.answers[0]["received"])

    def test_what_a_turn_showed_of_its_trigger_is_read_from_the_requests_an_agent_was_asked(self):
        ping, reply = "discord:actor:5", "discord:message:3"
        woken = _turn("discord:message:7", "q", mentioned_actor_ids=[ping], reply_to_event_id=reply)
        earlier = _turn("discord:message:6", "e")
        requests = [{"input": [{"content": [{"text": _tagged(earlier)}]}]},
                    {"body": {"messages": [{"content": [{"type": "text", "text": _tagged(woken)}]}]}, "headers": {}},
                    {"input": [{"content": [{"text": _tagged(woken)}, {"output": "ok"}]}]},  # the call after the tool's result
                    {"input": [{"content": [{"text": "no turn here"}]}]}]
        self.assertEqual(
            {"discord:message:6": {"trigger": "discord:message:6", "mentioned_actor_ids": [], "reply_to_event_id": None},
             "discord:message:7": {"trigger": "discord:message:7", "mentioned_actor_ids": [ping], "reply_to_event_id": reply}},
            standin.received_triggers(requests),
        )
        self.assertIsNone(standin.RoomScript.received(None))
        self.assertIsNone(standin.RoomScript.received({"wake": {"trigger_event_id": "x", "events": []}}))

    def test_the_scripted_claude_agent_follows_the_script_with_each_room_tool(self):
        agent = standin.ScriptedClaudeAgent("unused", "mcp__nunchi__room_send", script=SCRIPT, tools={"react": "mcp__nunchi__room_react"})
        self.addCleanup(agent.close)
        tools = [{"name": "mcp__nunchi__room_send"}, {"name": "mcp__nunchi__room_react"}]
        body = {"tools": tools, "messages": [{"role": "user", "content": [{"type": "text", "text": _tagged(_turn("discord:message:3", discord_room.REACTION_PHRASE))}]}]}
        kind, blocks, stop = agent.reply(body)
        self.assertEqual(("agent-tool-call", "tool_use"), (kind, stop))
        self.assertEqual("mcp__nunchi__room_react", blocks[0]["name"])
        self.assertEqual({"target_event_id": "discord:message:3", "reaction": discord_room.REACTION}, blocks[0]["input"])
        # Without a script it posts its answer, as in the in-process room.
        plain = standin.ScriptedClaudeAgent("Ten seconds.", "mcp__nunchi__room_send")
        self.addCleanup(plain.close)
        self.assertEqual({"text": "Ten seconds."}, plain.reply(body)[1][0]["input"])

    def test_the_scripted_codex_agent_follows_the_script(self):
        agent = standin.ScriptedCodexAgent("unused", script=SCRIPT)
        self.addCleanup(agent.close)
        replies = []
        request = {"input": [{"type": "message", "content": [{"type": "input_text", "text": _tagged(_turn("discord:message:4", f"so, {discord_room.REPLY_PHRASE}?"))}]}]}
        with mock.patch.object(agent.model, "latest", return_value=request), mock.patch.object(agent.model, "reply", replies.append):
            agent._next()
        self.assertEqual("room_send", replies[0]["tool"])
        self.assertEqual({"text": discord_room.SCRIPTED_REPLY, "reply_to_event_id": "discord:message:4"}, replies[0]["arguments"])


# -- the checks ---------------------------------------------------------------------------------------


class DiscordChecksTest(unittest.TestCase):
    def test_a_moments_outcome(self):
        outcome = checks.discord_moment_outcome
        reply = {"kind": "reply", "target_event_id": "e2"}
        self.assertEqual(checks.FITS, outcome("reply", reached=True, graded_turns=1, actions=[reply], graded_event="e2"))
        self.assertEqual(checks.MISSES, outcome("reply", reached=True, graded_turns=1, actions=[{**reply, "target_event_id": "e1"}], graded_event="e2"))
        self.assertEqual(checks.MISSES, outcome("reaction", reached=True, graded_turns=1, actions=[reply], graded_event="e2"))
        self.assertEqual(checks.NOT_DELIVERED, outcome("reaction", reached=False, graded_turns=0, actions=[], graded_event="e2"))
        self.assertEqual(checks.FITS, outcome("post", reached=True, graded_turns=1, actions=[{"kind": "message"}], graded_event="e2"))
        self.assertEqual(checks.FITS, outcome("no-turn", reached=True, graded_turns=0, actions=[], graded_event="e2"))
        self.assertEqual(checks.REACHED, outcome("report", reached=True, graded_turns=0, actions=[], graded_event="e2"))
        self.assertEqual(checks.NOT_DELIVERED, outcome("report", reached=False, graded_turns=0, actions=[], graded_event="e2"))

    def test_scripted_outcomes_hold_the_script_and_the_pins(self):
        moments = [
            {"name": "direct-question", "expect": "post", "outcome": "fits", "actions": [{"kind": "message", "text": probe.SCRIPTED_ANSWER}]},
            {"name": "reply", "expect": "reply", "outcome": "fits", "actions": [{"kind": "reply", "text": discord_room.SCRIPTED_REPLY}]},
            {"name": "reaction", "expect": "reaction", "outcome": "fits", "actions": [{"kind": "reaction", "reaction": discord_room.REACTION}]},
            {"name": "thread", "expect": "report", "outcome": "not delivered", "actions": []},
        ]
        pins = discord_room.TRANSPORT_PINS
        check = checks.discord_scripted_outcomes
        self.assertTrue(check(moments, discord_room.EXPECTED, pins=pins).ok)
        # Not pinned (the reference): a report moment reads whatever happened.
        flipped = [*moments[:3], {**moments[3], "outcome": "reached"}]
        self.assertTrue(check(flipped, discord_room.EXPECTED, pins={}).ok)
        failed = check(flipped, discord_room.EXPECTED, pins=pins)
        self.assertFalse(failed.ok)
        self.assertIn("not the pinned 'not delivered'", failed.detail)
        # The reference is pinned too: its first message reaches Nunchi, and a thread's message does not.
        reference = [{"name": "first-message", "expect": "report", "outcome": "reached"}, *moments, ]
        reference_pins = discord_room.REFERENCE_PINS
        self.assertTrue(check(reference, discord_room.EXPECTED, pins=reference_pins).ok)
        for name, outcome in (("first-message", "not delivered"), ("thread", "reached")):
            changed = [{**moment, "outcome": outcome} if moment["name"] == name else moment for moment in reference]
            failed = check(changed, discord_room.EXPECTED, pins=reference_pins)
            self.assertFalse(failed.ok, name)
            self.assertIn(f"{name} reads {outcome!r}, not the pinned", failed.detail)
        wrong = [{**moments[2], "actions": [{"kind": "reaction", "reaction": "ok"}]}]
        self.assertIn("reaction is 'ok'", check(wrong, discord_room.EXPECTED).detail)
        self.assertIn("1 turn(s) on other messages", check([{**moments[0], "other_turns": 1}], discord_room.EXPECTED).detail)
        self.assertFalse(check(moments, discord_room.EXPECTED, room_tool_called=False).ok)

    def test_preflight_and_processes(self):
        good = {
            "name": "nunchi-mcp-discord",
            "preflight": {"ok": True, "nonce_checked": True, "certificate_sha256": "abc"},
            "secrets": ["NUNCHI_DISCORD_TOKEN"],
            "own_keys": ["NUNCHI_DISCORD_TOKEN", "NUNCHI_DISCORD_OUTPUT_HMAC_KEY"],
            "running_after_moments": True,
            "stopped_by": "SIGINT",
            "exit": 0,
        }
        self.assertTrue(checks.discord_preflight([good], leaf_sha256="abc").ok)
        self.assertIn("another certificate", checks.discord_preflight([good], leaf_sha256="other").detail)
        self.assertFalse(checks.discord_preflight([{**good, "preflight": {"ok": False, "failures": ["proxy variables are set"]}}], leaf_sha256="abc").ok)
        self.assertFalse(checks.discord_preflight([], leaf_sha256="abc").ok)
        self.assertTrue(checks.discord_processes([good]).ok)
        self.assertIn("not its own in ANTHROPIC_AUTH_TOKEN", checks.discord_processes([{**good, "secrets": ["ANTHROPIC_AUTH_TOKEN"]}]).detail)
        self.assertIn("not running", checks.discord_processes([{**good, "running_after_moments": False}]).detail)
        self.assertIn("did not stop", checks.discord_processes([{**good, "stopped_by": "SIGKILL"}]).detail)

    def test_the_standin_must_be_clean_and_every_client_complete(self):
        self.assertTrue(checks.discord_standin_clean({"clean": True, "unknown": [], "raised": []}).ok)
        dirty = checks.discord_standin_clean({"clean": False, "unknown": [{"kind": "unknown", "what": "route", "path": "/api/v10/gateway/bot"}]})
        self.assertFalse(dirty.ok)
        self.assertIn("/api/v10/gateway/bot", dirty.detail)
        expected = {"Vigil": {"chunk": True, "calls": discord_room.REFERENCE_CALLS}}
        seen = {"Vigil": {"identify": 1, "ready": 1, "chunks": 1}}
        self.assertTrue(checks.discord_clients_complete(seen, expected, {"Vigil": list(discord_room.REFERENCE_CALLS)}).ok)
        missing = checks.discord_clients_complete({"Vigil": {"identify": 1, "ready": 1}}, expected, {"Vigil": [discord_room.POST]})
        self.assertIn("never got a member chunk", missing.detail)
        self.assertIn(discord_room.REACT, missing.detail)

    def test_writes_reconcile_with_what_was_committed(self):
        committed = [
            {"request_id": "r1", "kind": "message", "text": "hi", "delivery": "sent"},
            {"request_id": "r2", "kind": "reply", "text": "yes", "target_event_id": "discord:message:5", "delivery": "sent"},
            {"request_id": "r3", "kind": "reaction", "reaction": "\N{THUMBS UP SIGN}", "target_event_id": "discord:message:6", "operation": "add", "delivery": "sent"},
        ]
        writes = [
            {"kind": "message", "content": "hi", "reply_to": None},
            {"kind": "message", "content": "yes", "reply_to": "5"},
            {"kind": "reaction", "emoji": "\N{THUMBS UP SIGN}", "message_id": "6", "removed": False},
        ]
        self.assertTrue(checks.discord_writes_reconciled(committed, writes).ok)
        # A reply that landed as a plain message, a write nobody committed, a sent action never written.
        self.assertFalse(checks.discord_writes_reconciled(committed, [{**writes[0]}, {**writes[1], "reply_to": None}, writes[2]]).ok)
        self.assertIn("no committed action matches", checks.discord_writes_reconciled(committed, [*writes, writes[0]]).detail)
        self.assertIn("matches 0 write(s)", checks.discord_writes_reconciled(committed, writes[:2]).detail)
        # An action whose acknowledgement was lost may match a write, and need not.
        lost = [{**committed[0], "delivery": "unknown"}]
        self.assertTrue(checks.discord_writes_reconciled(lost, writes[:1]).ok)
        self.assertTrue(checks.discord_writes_reconciled(lost, []).ok)

    def test_addressing_compares_what_was_sent_with_what_the_agent_received(self):
        agent, zoe = "discord:actor:5", "discord:actor:9"
        writes = [{"kind": "message", "message_id": "100"}, {"kind": "message", "message_id": "300"}, {"kind": "reaction", "message_id": "250"}]
        moments = [
            {"name": "direct-question", "expect": "post", "graded_event": "discord:message:200", "deliveries": [
                {"event_id": "discord:message:200", "message_id": "200", "mentioned_actor_ids": [agent], "reply_to": None,
                 "received": {"trigger": "discord:message:200", "mentioned_actor_ids": [agent], "reply_to_event_id": None}}]},
            {"name": "bot-status-report", "expect": "no-turn", "graded_event": "discord:message:210", "deliveries": [{"event_id": "discord:message:210"}]},
            {"name": "reply", "expect": "reply", "graded_event": "discord:message:250", "deliveries": [
                {"event_id": "discord:message:250", "message_id": "250", "mentioned_actor_ids": [], "reply_to": "100",
                 "received": {"trigger": "discord:message:250", "mentioned_actor_ids": [zoe], "reply_to_event_id": "discord:message:100"}}]},
            {"name": "reaction", "expect": "reaction", "graded_event": "discord:message:400", "deliveries": [
                {"event_id": "discord:message:400", "message_id": "400", "mentioned_actor_ids": [agent], "reply_to": None,
                 "received": {"trigger": "discord:message:400", "mentioned_actor_ids": [agent], "reply_to_event_id": None}}]},
            {"name": "thread", "expect": "report", "graded_event": "discord:message:500", "deliveries": [{"event_id": "discord:message:500"}]},
        ]
        check = checks.discord_addressing
        self.assertTrue(check(moments, agent=agent, writes=writes).ok, check(moments, agent=agent, writes=writes).detail)

        def changed(index: int, **fields):
            delivery = {**moments[index]["deliveries"][0], **fields}
            return [*moments[:index], {**moments[index], "deliveries": [delivery]}, *moments[index + 1:]]

        def lost_received(index: int, **fields):
            delivery = moments[index]["deliveries"][0]
            return changed(index, received={**delivery["received"], **fields})

        # The transport or the reference dropped a ping, or the reply reference.
        failed = check(lost_received(0, mentioned_actor_ids=[]), agent=agent, writes=writes)
        self.assertFalse(failed.ok)
        self.assertIn(f"sent pinging {agent}, but Nunchi saw mentioned_actor_ids=[]", failed.detail)
        self.assertFalse(check(lost_received(3, mentioned_actor_ids=[zoe]), agent=agent, writes=writes).ok)
        failed = check(lost_received(2, reply_to_event_id=None), agent=agent, writes=writes)
        self.assertIn("Nunchi saw reply_to_event_id=None", failed.detail)
        self.assertFalse(check(lost_received(2, reply_to_event_id="discord:message:300"), agent=agent, writes=writes).ok)
        # The scene must address the agent, the reply must be to the agent's own last post, and a turn must have shown it.
        self.assertIn("did not ping the agent", check(changed(0, mentioned_actor_ids=[]), agent=agent, writes=writes).detail)
        self.assertIn("did not ping the agent", check(changed(3, mentioned_actor_ids=[]), agent=agent, writes=writes).detail)
        self.assertIn("not sent as a reply to the agent's own last message", check(changed(2, reply_to=None), agent=agent, writes=writes).detail)
        also = [*writes, {"kind": "message", "message_id": "220"}]  # a later post of the agent's: the reply was to an older one
        self.assertIn("not sent as a reply", check(moments, agent=agent, writes=also).detail)
        self.assertIn("no turn showed", check(changed(0, received=None), agent=agent, writes=writes).detail)
        self.assertIn("never posted", check([{**moments[0], "graded_event": "discord:message:1"}], agent=agent, writes=writes).detail)
        self.assertFalse(check([moments[1], moments[4]], agent=agent, writes=writes).ok)

    def test_continuity(self):
        start = {"process": "nunchi-mcp-discord", "gap": "discord:transport-gap:1"}
        clean = {"bot": "Vigil", "resumed": True, "identified_again": False, "message_reached": True, "transport_gaps": [], "participant_gaps": []}
        self.assertTrue(checks.discord_continuity(start, [clean], gaps_fail=True).ok)
        self.assertIn("never saw the gap", checks.discord_continuity({"process": "nunchi-mcp-discord", "gap": None}, [clean], gaps_fail=True).detail)
        gap = {**clean, "participant_gaps": ["discord:codex-app-server-stream-gap:1"]}
        self.assertFalse(checks.discord_continuity(start, [gap], gaps_fail=True).ok)
        recorded = checks.discord_continuity(start, [gap], gaps_fail=False)
        self.assertTrue(recorded.ok)
        self.assertIn("recorded and not failed", recorded.detail)
        for broken, words in (({"resumed": False}, "did not resume"), ({"identified_again": True}, "identified again"),
                              ({"message_reached": False}, "never reached Nunchi")):
            self.assertIn(words, checks.discord_continuity(start, [{**clean, **broken}], gaps_fail=False).detail)
        self.assertFalse(checks.discord_continuity(start, [], gaps_fail=False).ok)


# -- the world, the wire and the processes --------------------------------------------------------------


class _StandIn:
    def start(self, spec: dict) -> FakeDiscord:
        self.out = Path(tempfile.mkdtemp(prefix="discord-room-"))
        self.addCleanup(shutil.rmtree, self.out, True)
        self.fd = FakeDiscord(spec, self.out).start()
        self.addCleanup(self.fd.stop)
        return self.fd


def _world() -> tuple[dict, dict]:
    scenes = [load_scene(spec.scene) for spec in discord_room.MOMENTS]
    return discord_room.world_spec("codex", scenes, agent="Vigil")


class WorldTest(unittest.TestCase):
    def test_one_channel_for_the_column_its_bot_and_the_scenes_people_and_scripted_bots(self):
        spec, members = _world()
        self.assertEqual({"codex": {}}, spec["channels"])
        self.assertEqual(["zoe"], spec["people"])
        self.assertEqual({"CI": {"harness": False}, "Vigil": {}}, spec["bots"])
        self.assertEqual({"vigil": "Vigil", "zoe": "zoe", "ci": "CI"}, members)

    def test_the_moments_go_in_order_with_the_reconnect_before_the_reaction(self):
        names = [spec.name for spec in discord_room.MOMENTS]
        self.assertEqual(["first-message", "bot-status-report", "direct-question", "reply", "reaction", "thread"], names)
        self.assertEqual(["reaction"], [spec.name for spec in discord_room.MOMENTS if spec.reconnect_before])
        self.assertEqual(["reply"], [spec.name for spec in discord_room.MOMENTS if spec.reply_to_agent])
        self.assertEqual({"first-message", "thread"}, set(discord_room.TRANSPORT_PINS))
        self.assertEqual({"first-message": checks.REACHED, "thread": checks.NOT_DELIVERED}, discord_room.REFERENCE_PINS)
        self.assertIs(discord_room.REFERENCE_PINS, discord_room.ReferenceLeg.pins)
        self.assertIs(discord_room.TRANSPORT_PINS, discord_room.OnTheTransport.pins)

    def test_the_room_needs_the_launchers_record(self):
        with self.assertRaisesRegex(probe.CouldNotRun, "discord_net --offline"):
            discord_room.load_net({})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "net.json"
            path.write_text("{}")
            with self.assertRaisesRegex(probe.CouldNotRun, "cannot be read"):
                discord_room.load_net({discord_room.NET_ENV: str(path)})
            path.write_text(json.dumps({"tls": {"cert": "c", "key": "k"}}))
            self.assertEqual("c", discord_room.load_net({discord_room.NET_ENV: str(path)})["tls"]["cert"])


def _room(base: Path, *, env: dict | None = None, original: dict | None = None) -> discord_room.DiscordRoom:
    net = base / "net.json"
    net.write_text(json.dumps({"tls": {"cert": "c", "key": "k"}, "leaf_sha256": "abc"}))
    ctx = SimpleNamespace(
        original_env={discord_room.NET_ENV: str(net), **(original or {})},
        options=SimpleNamespace(discord_python=None),
        base=base,
        out=base / "out",
        profile={"display_name": "Vigil"},
        env=env or {},
        secrets={},
    )
    return discord_room.DiscordRoom(ctx, "codex")


class RoomTest(_StandIn, unittest.TestCase):
    def test_a_discord_process_gets_no_proxy_no_key_of_the_harnesss_and_its_own_homes(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"PATH": "/bin", "HTTPS_PROXY": "http://proxy:1", "no_proxy": "x", "ANTHROPIC_AUTH_TOKEN": "k" * 40,
                   "REHEARSAL_CANARY": "canary", "SSL_CERT_FILE": "/c.pem", "HOME": "/home/harness"}
            room = _room(Path(directory), env=env, original={"PYTHONPATH": f"src{os.pathsep}/abs"})
            built, where = room.environment("nunchi-mcp-discord", {"NUNCHI_DISCORD_TOKEN": "t"})
        self.assertEqual({"PATH", "SSL_CERT_FILE", "HOME", "TMPDIR", "PYTHONPATH", "NUNCHI_DISCORD_TOKEN"}, set(built))
        self.assertTrue(built["HOME"].startswith(str(where)))
        self.assertEqual([str(Path("src").absolute()), "/abs"], built["PYTHONPATH"].split(os.pathsep))

    def test_a_message_is_posted_as_a_person_types_it_in_a_thread_or_as_a_reply_to_the_agent(self):
        spec, members = _world()
        fd = self.start(spec)
        with tempfile.TemporaryDirectory() as directory:
            room = _room(Path(directory))
            room.fd, room.members = fd, members
            scenes = {moment.name: (moment, load_scene(moment.scene)) for moment in discord_room.MOMENTS}
            moment, scene = scenes["direct-question"]
            delivery = room.post(scene.events[0], datetime_now(), scene, moment)
            text = fd.world.messages[delivery["message_id"]]["content"]
            self.assertEqual([f"discord:actor:{fd.world.member('Vigil').id}"], delivery["mentioned_actor_ids"], "what the scene sent, for discord-addressing")
            self.assertTrue(text.startswith(f"<@{fd.world.member('Vigil').id}>, quick question"))
            self.assertEqual([fd.world.member("Vigil").id], fd.world.messages[delivery["message_id"]]["mentions"])
            # The reply moment answers the agent's last post; with none, it goes as a plain message and says so.
            moment, scene = scenes["reply"]
            plain = room.post(scene.events[0], datetime_now(), scene, moment)
            self.assertIn("no post to reply to", plain["note"])
            self.assertEqual(([], None), (plain["mentioned_actor_ids"], plain["reply_to"]))
            room.agent_last_post = lambda: delivery["message_id"]
            reply = room.post(scene.events[0], datetime_now(), scene, moment)
            self.assertEqual(delivery["message_id"], fd.world.messages[reply["message_id"]]["reply_to"])
            self.assertEqual(delivery["message_id"], reply["reply_to"], "what the scene sent as the message replied to")
            moment, scene = scenes["thread"]
            first = room.post(scene.events[0], datetime_now(), scene, moment)
            again = room.post(scene.events[0], datetime_now(), scene, moment)
            thread = fd.world.channel(discord_room.THREAD)
            self.assertEqual((discord_room.THREAD, discord_room.THREAD), (first["channel"], again["channel"]))
            self.assertEqual(fd.world.channel("codex").id, thread.parent_id)
            self.assertEqual({thread.id}, {fd.world.messages[item["message_id"]]["channel_id"] for item in (first, again)})

    def test_a_process_is_stopped_with_sigint_and_harder_only_when_it_ignores_it(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            stubborn = "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); print('up', flush=True); time.sleep(60)"
            for code, stopped_by in (("import time; print('up', flush=True); time.sleep(60)", "SIGINT"), (stubborn, "SIGTERM")):
                with self.subTest(stopped_by=stopped_by):
                    process = discord_room.DiscordProcess(
                        "nunchi-discord", [sys.executable, "-c", code], dict(os.environ), cwd=base, log=base / f"{stopped_by}.log",
                        secrets={}, own_keys=[],
                    )
                    process.start()
                    deadline = time.monotonic() + 10
                    while "up" not in process.tail() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    process.stop(waits=(2.0, 0.5, 2.0, 2.0))
                    document = process.document()
                    self.assertEqual((True, stopped_by), (document["running_after_moments"], document["stopped_by"]))
                    self.assertIsNotNone(document["exit"])

    def test_what_a_process_runs_on_is_read_in_its_own_python_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            room = _room(base)
            env = {"PATH": os.environ.get("PATH", "/bin"), "PYTHONPATH": str(probe.ROOT / "src")}
            process = discord_room.DiscordProcess("nunchi-mcp-discord", [], env, cwd=base, log=base / "a.log", secrets={}, own_keys=[])
            installed = room.installed(process)
            self.assertEqual(sys.version.split()[0], installed["python"])
            self.assertTrue(installed["nunchi"])
            self.assertIn("mcp", installed)  # its version, or None where the extra is not installed
            room.python = str(base / "no-such-python")
            self.assertIn("FileNotFoundError", room.installed(process)["error"])


def datetime_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


class WireTest(_StandIn, unittest.IsolatedAsyncioTestCase):
    """What the probe reads from the wire, with Nunchi's own transport clients on the stand-in."""

    async def asyncSetUp(self) -> None:
        spec, self.members = _world()
        fd = self.start(spec)
        self.room = fd.world.channel("codex").id
        self.vigil = fd.world.member("Vigil").id
        self.secret = secrets.token_bytes(32)
        authorizer = ToolAuthorizer(secret=self.secret, participant_routes={"vigil": frozenset({self.room})})
        rest = DiscordRestClient(fd.token("Vigil"), base_url=fd.rest_url)
        self.executor = ToolExecutor(rest, SendBackstop(50, 10), authorizer=authorizer)

    def tool(self, name: str, **arguments):
        arguments = {"channel_id": self.room, **arguments}
        authorization = make_tool_authorization(
            secret=self.secret, request_id=secrets.token_hex(4), participant_id="vigil", room_id=self.room, tool=name, arguments=arguments
        )
        return self.executor.call(
            name, {**arguments, "_nunchi_authorization": authorization},
            expected_route=("vigil", self.room), expected_self_actor_id=f"discord:actor:{self.vigil}",
        )

    async def test_the_agents_writes_and_calls_come_from_the_wire_and_reconcile(self):
        asked = self.fd.post("zoe", "codex", "a question")["id"]
        sent, ok = await asyncio.to_thread(self.tool, "send_message", content="an answer")
        self.assertTrue(ok, sent)
        _, ok = await asyncio.to_thread(self.tool, "reply_message", message_id=asked, content="a reply")
        self.assertTrue(ok)
        _, ok = await asyncio.to_thread(self.tool, "reaction_capability")
        self.assertTrue(ok)
        _, ok = await asyncio.to_thread(self.tool, "add_reaction", message_id=asked, reaction=discord_room.REACTION)
        self.assertTrue(ok)
        records = list(self.fd.wire.records)
        writes = discord_room.wire_writes(records, "Vigil")
        self.assertEqual(
            [("message", "an answer", None), ("message", "a reply", asked), ("reaction", discord_room.REACTION, asked)],
            [(w["kind"], w.get("content") or w.get("emoji"), w.get("reply_to") or w.get("message_id") if w["kind"] == "reaction" else w.get("reply_to")) for w in writes],
        )
        committed = [
            {"request_id": "a", "kind": "message", "text": "an answer", "delivery": "sent"},
            {"request_id": "b", "kind": "reply", "text": "a reply", "target_event_id": f"discord:message:{asked}", "delivery": "sent"},
            {"request_id": "c", "kind": "reaction", "reaction": discord_room.REACTION, "target_event_id": f"discord:message:{asked}",
             "operation": "add", "delivery": "sent"},
        ]
        self.assertTrue(checks.discord_writes_reconciled(committed, writes).ok)
        calls = discord_room.wire_calls(records, "Vigil")
        self.assertEqual(set(discord_room.TRANSPORT_CALLS), set(calls))
        # A person's post is the director's, never the agent's write.
        self.assertEqual([], discord_room.wire_writes(records, "zoe"))

    async def test_a_reconnect_resumes_and_replays_what_was_posted_meanwhile(self):
        events: list[dict] = []
        gaps: list[int] = []
        protocol = GatewayProtocol(self.fd.token("Vigil"))
        runner = GatewayRunner(
            protocol, events.append, allowed_channel_ids=frozenset({self.room}), on_source_gap=lambda: gaps.append(len(events)),
            connect=lambda url: WSClient.connect(url.replace("wss://gateway.discord.gg", self.fd.gateway_url)),
            rng=lambda: 0.5, initial_backoff=0.05,
        )
        shutdown = asyncio.Event()
        task = asyncio.create_task(runner.run(shutdown))
        logs = self.assertLogs("nunchi.mcp_discord.runner", level="INFO")
        watched = logs.__enter__()
        try:
            await asyncio.to_thread(self.fd.wait_for, lambda r: r.get("t") == "READY", 10)
            since = len(self.fd.wire.records)
            await asyncio.to_thread(self.fd.gateway, "Vigil", "reconnect")
            posted = await asyncio.to_thread(self.fd.post, "zoe", "codex", "posted while the bot reconnects")
            for _ in range(100):
                if any((event.get("event") or {}).get("id") == f"discord:message:{posted['id']}" for event in events):
                    break
                await asyncio.sleep(0.05)
            facts = discord_room.reconnect_facts(list(self.fd.wire.records)[since:], "Vigil", message_reached=True)
        finally:
            shutdown.set()
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
            logs.__exit__(None, None, None)
        # The transport's own words: it was asked to reconnect, and resumed.
        self.assertTrue(any("reconnect (resume=True)" in line for line in watched.output), watched.output)
        self.assertTrue(any("gateway connected (resuming)" in line for line in watched.output), watched.output)
        self.assertTrue(any((event.get("event") or {}).get("id") == f"discord:message:{posted['id']}" for event in events))
        self.assertEqual((1, True, False, [], []), (facts["op7"], facts["resumed"], facts["identified_again"], facts["transport_gaps"], facts["participant_gaps"]))
        self.assertEqual(1, len(gaps), "only the fresh process's own start gap")


class AuditTest(unittest.TestCase):
    def test_a_messages_audit_is_found_by_its_event_or_its_native_id(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "x.observations.jsonl.delivery-audit.jsonl").write_text(
                "\n".join(
                    json.dumps(record)
                    for record in (
                        {"delivery_id": "discord:standalone-startup-gap:1", "outcome": "continuity-gap", "event_id": None},
                        {"delivery_id": "d1", "outcome": "recorded", "event_id": "discord:message:11"},
                        {"delivery_id": "discord:gateway:unknown:MESSAGE_CREATE:12", "outcome": "route-rejected", "event_id": None},
                    )
                )
                + "\nnot json\n"
            )
            audits = discord_room.delivery_audits(state)
        self.assertEqual(3, len(audits))
        self.assertEqual("recorded", discord_room.audit_for(audits, "11")["outcome"])
        self.assertEqual("route-rejected", discord_room.audit_for(audits, "12")["outcome"])
        self.assertIsNone(discord_room.audit_for(audits, "1"))


class JudgeTest(unittest.TestCase):
    def test_each_moment_reads_its_graded_turns_delivered_actions(self):
        leg = SimpleNamespace(
            committed=[
                {"request_id": "r1", "kind": "reply", "text": "t", "target_event_id": "discord:message:2", "delivery": "sent"},
                {"request_id": "r2", "kind": "reaction", "reaction": "x", "target_event_id": "discord:message:3", "delivery": "failed"},
            ],
            room_effects=lambda: [],
        )
        moments = [
            {"name": "reply", "expect": "reply", "reached": True, "graded_turns": 1, "graded_event": "discord:message:2",
             "turns": [{"request_id": "r1", "trigger": "discord:message:2"}]},
            {"name": "reaction", "expect": "reaction", "reached": True, "graded_turns": 1, "graded_event": "discord:message:3",
             "turns": [{"request_id": "r2", "trigger": "discord:message:3"}]},
        ]
        moments[0]["deliveries"] = [{"event_id": "discord:message:2"}]
        moments[1]["deliveries"] = [{"event_id": "discord:message:3"}]
        seen = {"trigger": "discord:message:2", "mentioned_actor_ids": [], "reply_to_event_id": "discord:message:1"}
        discord_room.judge_discord_moments(leg, moments, {"discord:message:2": seen})
        self.assertEqual((seen, None), (moments[0]["deliveries"][0]["received"], moments[1]["deliveries"][0]["received"]))
        self.assertEqual(("fits", "misses"), (moments[0]["outcome"], moments[1]["outcome"]))
        self.assertEqual([{"text": "t", "delivery": "sent", "delivered": True}], moments[0]["posts"])
        self.assertEqual([False], [action["delivered"] for action in moments[1]["actions"]])


# -- the probe's signals -------------------------------------------------------------------------------


class TerminationTest(unittest.TestCase):
    """SIGTERM and SIGHUP end a run as Ctrl-C does, so the Discord processes it started are stopped (`leg.close`)."""

    def setUp(self) -> None:
        before = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGHUP)}
        for number, handler in before.items():
            self.addCleanup(signal.signal, number, handler)

    def test_the_first_signal_interrupts_the_run_once_and_the_handlers_come_back(self):
        before = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGHUP)}
        handlers = probe._interrupt_on_termination()
        self.assertEqual(set(before), set(handlers))
        with self.assertRaises(KeyboardInterrupt):
            os.kill(os.getpid(), signal.SIGTERM)
        os.kill(os.getpid(), signal.SIGHUP)  # disarmed: a second signal does not cut the wind-down short
        os.kill(os.getpid(), signal.SIGTERM)
        for number, handler in handlers.items():
            signal.signal(number, handler)
        self.assertEqual(before, {number: signal.getsignal(number) for number in before})

    def test_a_signal_ignored_on_purpose_stays_ignored(self):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)  # as nohup does
        handlers = probe._interrupt_on_termination()
        self.assertEqual([signal.SIGTERM], list(handlers))
        os.kill(os.getpid(), signal.SIGHUP)
        self.assertEqual(signal.SIG_IGN, signal.getsignal(signal.SIGHUP))

    def test_off_the_main_thread_it_sets_nothing(self):
        found: list[object] = []
        thread = threading.Thread(target=lambda: found.append(probe._interrupt_on_termination()))
        thread.start()
        thread.join()
        self.assertEqual([{}], found)


# -- the probe's command --------------------------------------------------------------------------------


class DiscordCommandTest(unittest.TestCase):
    def test_the_discord_room_is_scripted_and_the_reference_lives_only_there(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(probe.EXIT_USAGE, probe.main(["--harness", "reference", "--scripted", "--out", directory]))
            self.assertEqual(probe.EXIT_USAGE, probe.main(["--harness", "codex", "--room", "discord", "--out", directory]))
            self.assertEqual(probe.EXIT_USAGE, probe.main(["--harness", "hermes", "--room", "discord", "--scripted", "--out", directory]))
            self.assertEqual([], list(Path(directory).iterdir()))
        self.assertIn("--room discord --scripted", error.getvalue())

    def test_without_the_launcher_the_discord_room_could_not_run_and_started_nothing(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(discord_room.NET_ENV, None)
            options = probe.Options(harness="reference", out=Path(directory), scripted=True, room="discord", command=["test"])
            with contextlib.redirect_stdout(io.StringIO()):
                code = probe.run_probe(options)
            out = Path(directory) / "reference"
            run = json.loads((out / "run.json").read_text())
            self.assertFalse((out / "discord-wire.jsonl").exists())
        self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
        self.assertIn("runs inside the launcher", " ".join(run["errors"]))

    def test_the_in_process_room_stays_the_default(self):
        parsed = probe._parser().parse_args(["--harness", "codex", "--out", "x"])
        self.assertEqual("standin", parsed.room)
        self.assertEqual(probe.MOMENTS, probe._room_parts(probe.Options(harness="codex", out=Path("x")))[1])


if __name__ == "__main__":
    unittest.main()
