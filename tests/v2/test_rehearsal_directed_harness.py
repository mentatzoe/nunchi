"""Directed scenes through Claude Code and Codex (rehearsal PR 4b): the scripted endpoints, the legs' record and the hard checks.

PR 4a plays a behavior scene on the reference alone (`test_rehearsal_directed`).
PR 4b runs the same four scenes through the Claude Code and Codex columns, so
each harness's real process reads the room the director makes; the reference is
the control. These tests need neither harness nor the launcher: they hold the
parts that make a harness column play a scene (a scripted model endpoint that
follows the scene's script, a leg that records what 4a's judge reads) and show
that a script which plays a listed miss through a harness column fails
`directed-outcomes`, naming the moment.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from evals.behavior.score import agent_move
from evals.rehearsal import checks, directed, discord_room, probe, standin

from tests.v2.test_rehearsal_directed import NEWS, PLAYABLE, ROOT, _news, _played
from tests.v2.test_rehearsal_discord_room import _tagged, _turn

SEND, REACT = "mcp__nunchi__room_send", "mcp__nunchi__room_react"
HARNESS_LEGS = {"claude-code": discord_room.DiscordClaudeCodeLeg, "codex": discord_room.DiscordCodexLeg}


def _graded_turns(scene_id: str):
    """For each graded moment of a playable scene: the spec's script, the moment, and the text its message is posted with."""

    item = directed.spec(scene_id)
    for moment in item.plan.scene.moments:
        raw = next(event for event in item.plan.scene.events if event["id"] == moment.event)
        text = f"<@42> {raw['text']}"
        item.script.register(text, moment.event)
        yield item.script, moment, text


# -- the script, said as a room tool call -------------------------------------------------------------------


class MoveTest(unittest.TestCase):
    def test_a_graded_moment_is_a_send_a_react_or_silence_as_the_first_fitting_move_says_and_the_chatter_is_silence(self):
        for scene_id in PLAYABLE:
            for script, moment, text in _graded_turns(scene_id):
                with self.subTest(scene=scene_id, moment=moment.label):
                    turn = _turn("discord:message:7", text)
                    news = _news(script, moment.event)  # a held turn decides once it has been shown what landed meanwhile
                    role, arguments = script.move(turn, news=news)
                    intended = standin.SceneScript.intended(moment)
                    self.assertEqual({"speak": "send", "mhm": "react", "stay_quiet": "silence"}[intended], role)
                    if role == "send":
                        self.assertEqual({"text": standin.SCENE_SAY.format(event=moment.event)}, arguments)
                    elif role == "react":
                        self.assertEqual({"target_event_id": "discord:message:7", "reaction": standin.SCENE_NOD}, arguments)
                    else:
                        self.assertEqual({}, arguments)
                    # The same move as the reference's action, said once.
                    self.assertEqual(intended, agent_move([script.action(turn, news=news)]))
        script = directed.spec("story-across-messages").script
        self.assertEqual(("silence", {}), script.move(_turn("discord:message:9", "something nobody graded")))
        self.assertEqual(("silence", {}), script.move({"wake": {}}), "a turn with no trigger")
        self.assertEqual(("silence", {}), script.move(None), "a request that holds no turn")


class EndpointTest(unittest.TestCase):
    def claude(self, script):
        agent = standin.ScriptedClaudeAgent("unused", SEND, script=script, tools={"react": REACT})
        self.addCleanup(agent.close)
        return agent

    def body(self, turn, *, result=False, news=None):
        messages = [{"role": "user", "content": [{"type": "text", "text": _tagged(turn)}]}]
        if result or news:
            # The room tool's result: "ok", or the page the core's look before posting showed the turn.
            messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": news or "ok"}]})
        return {"tools": [{"name": SEND}, {"name": REACT}], "messages": messages}

    def test_the_scripted_claude_endpoint_follows_the_scene_each_graded_moment_by_its_tool_and_silence_by_none(self):
        for scene_id in PLAYABLE:
            agent = self.claude(directed.spec(scene_id).script)
            for script, moment, text in _graded_turns(scene_id):
                with self.subTest(scene=scene_id, moment=moment.label):
                    agent.script = script
                    kind, blocks, stop = agent.reply(self.body(_turn("discord:message:7", text), news=_news(script, moment.event)))
                    intended = standin.SceneScript.intended(moment)
                    if intended == "stay_quiet":
                        self.assertEqual(("agent", "end_turn"), (kind, stop))
                        self.assertEqual(["text"], [block["type"] for block in blocks], "no room tool call: the turn ends")
                        continue
                    self.assertEqual(("agent-tool-call", "tool_use"), (kind, stop))
                    self.assertEqual([SEND if intended == "speak" else REACT], [block["name"] for block in blocks])
                    expected = (
                        {"text": standin.SCENE_SAY.format(event=moment.event)}
                        if intended == "speak"
                        else {"target_event_id": "discord:message:7", "reaction": standin.SCENE_NOD}
                    )
                    self.assertEqual(expected, blocks[0]["input"])
                    # The call after the tool's result ends the turn, as before.
                    self.assertEqual(("agent", "end_turn"), agent.reply(self.body(_turn("discord:message:7", text), result=True))[::2])

    def test_the_scripted_claude_endpoint_is_silent_on_the_chatter_and_a_plain_run_still_posts_its_answer(self):
        agent = self.claude(directed.spec("story-across-messages").script)
        kind, blocks, stop = agent.reply(self.body(_turn("discord:message:9", "something nobody graded")))
        self.assertEqual(("agent", "end_turn", ["text"]), (kind, stop, [block["type"] for block in blocks]))
        plain = standin.ScriptedClaudeAgent("Ten seconds.", SEND)
        self.addCleanup(plain.close)
        self.assertEqual({"text": "Ten seconds."}, plain.reply(self.body(_turn("discord:message:9", "x")))[1][0]["input"])

    def test_the_scripted_codex_endpoint_follows_the_scene_a_tool_call_where_it_acts_and_a_bare_message_where_it_is_quiet(self):
        for scene_id in PLAYABLE:
            agent = standin.ScriptedCodexAgent("unused", script=directed.spec(scene_id).script)
            self.addCleanup(agent.close)
            for script, moment, text in _graded_turns(scene_id):
                with self.subTest(scene=scene_id, moment=moment.label):
                    agent.script = script
                    request = {"input": [{"type": "message", "content": [{"type": "input_text", "text": _tagged(_turn("discord:message:7", text))}]}]}
                    if _news(script, moment.event):
                        request["input"].append({"type": "function_call_output", "call_id": "c", "output": NEWS})
                    replies: list[dict] = []
                    with mock.patch.object(agent.model, "latest", return_value=request), mock.patch.object(agent.model, "reply", replies.append):
                        agent._next()
                    intended = standin.SceneScript.intended(moment)
                    if intended == "stay_quiet":
                        self.assertEqual(1, len(replies))
                        self.assertNotIn("tool", replies[0], "no room tool call: the turn ends on its message")
                        self.assertIn("text", replies[0])
                    elif intended == "speak":
                        self.assertEqual(("room_send", {"text": standin.SCENE_SAY.format(event=moment.event)}), (replies[0]["tool"], replies[0]["arguments"]))
                    else:
                        self.assertEqual(
                            ("room_react", {"target_event_id": "discord:message:7", "reaction": standin.SCENE_NOD}),
                            (replies[0]["tool"], replies[0]["arguments"]),
                        )

    def test_the_moments_script_is_still_followed_as_it_was(self):
        agent = standin.ScriptedCodexAgent("unused", script=discord_room.SCRIPT)
        self.addCleanup(agent.close)
        request = {"input": [{"type": "message", "content": [{"type": "input_text", "text": _tagged(_turn("discord:message:4", "anything"))}]}]}
        replies: list[dict] = []
        with mock.patch.object(agent.model, "latest", return_value=request), mock.patch.object(agent.model, "reply", replies.append):
            agent._next()
        self.assertEqual(("room_send", {"text": discord_room.SCRIPTED_ANSWER}), (replies[0]["tool"], replies[0]["arguments"]))


# -- what the legs record for a scene -----------------------------------------------------------------------


class InstrumentTest(unittest.TestCase):
    def leg(self, directed_spec):
        leg = probe.Leg(SimpleNamespace(directed=directed_spec, secrets={}))
        sent = []

        def dispatch(*, action, wake):
            sent.append(action)
            return SimpleNamespace(delivery="sent", detail="discord:message:5")

        participant = SimpleNamespace(run_protocol=lambda **_: {"kind": "silence"}, bind_turn=lambda **_: True, active=None)
        transport = SimpleNamespace(dispatch=dispatch)
        room = SimpleNamespace(host=SimpleNamespace(transport=transport), attention=SimpleNamespace(model=None))
        leg.instrument(participant, room)
        return leg, participant, transport

    def test_a_turn_that_took_messages_made_while_the_agent_was_busy_lists_them_and_a_plain_turn_lists_none(self):
        leg, participant, _ = self.leg(None)
        base = {"request_id": "r1", "trigger_event_id": "discord:message:2", "attention": {"source": "WAKE"}}
        participant.run_protocol(wake=base, opportunity=None, expand=None, cancel=None)
        participant.run_protocol(wake={**base, "request_id": "r2", "unattended_event_ids": ["discord:message:1"]}, opportunity=None, expand=None, cancel=None)
        self.assertNotIn("unattended", leg.invocations[0])
        self.assertEqual(["discord:message:1"], leg.invocations[1]["unattended"])

    def test_a_scene_keeps_what_each_committed_action_was_about_and_a_plain_lane_records_as_before(self):
        action = {"kind": "message", "origin_event_id": "discord:message:2", "text": "hi", "why": "x"}
        kept = {}
        for name, spec in (("scene", directed.spec("story-across-messages")), ("plain", None)):
            leg, _, transport = self.leg(spec)
            transport.dispatch(action=action, wake={"request_id": "r1"})
            kept[name] = leg.committed[0]
        self.assertEqual("discord:message:2", kept["scene"]["origin_event_id"])
        self.assertNotIn("origin_event_id", kept["plain"])
        self.assertEqual({**kept["plain"], "origin_event_id": "discord:message:2"}, kept["scene"])


class ReceiptsTest(unittest.TestCase):
    def test_attention_is_read_from_the_participants_receipts_for_every_column_and_the_evidence_only_for_a_scene(self):
        trigger = "discord:message:1"
        receipts = [
            {"request_id": "r1", "stage": "observation", "body": {"trigger_event_id": trigger}},
            {"request_id": "r1", "stage": "attention", "body": {"effective_disposition": "SUPPRESS", "evidence_event_ids": [trigger]}},
            {"request_id": "r2", "stage": "observation", "body": {"trigger_event_id": "discord:message:2"}},
            {"request_id": "r2", "stage": "attention", "body": {"error": {"code": "timeout", "detail": "slow"}, "wake_action": "WAKE"}},
            {"request_id": "r3", "stage": "observation", "body": {"trigger_event_id": "discord:message:3"}},
        ]
        stages = discord_room.stages_by_request(receipts)
        self.assertEqual({"observation", "attention"}, set(stages["r1"]))
        scene = discord_room.attention_entries(stages, "m", evidence=True)
        self.assertEqual(
            [
                {"request_id": "r1", "trigger": trigger, "model": "m", "disposition": "SUPPRESS", "served": {"provider": "scripted"}, "evidence": [trigger]},
                {"request_id": "r2", "trigger": "discord:message:2", "model": "m", "error": "timeout: slow", "wake_action": "WAKE"},
            ],
            scene,
        )
        plain = discord_room.attention_entries(stages, "m", evidence=False)
        self.assertNotIn("evidence", plain[0])
        self.assertEqual("SUPPRESS", plain[0]["disposition"])


# -- the harness legs ---------------------------------------------------------------------------------------


def _scene_leg(leg_class, scene_id: str, *, state: Path, invocations=(), committed=(), receipts=(), requests=(), room_calls=None):
    """A Claude Code or Codex leg, judged as the room reads it back: its turns and actions as the probe recorded them, and the participant's receipts."""

    item = directed.spec(scene_id)
    leg = object.__new__(leg_class)
    leg.directed = item
    leg.ctx = SimpleNamespace(attention={"model": "m"})
    leg.discord = SimpleNamespace(
        state=state, column=leg_class.harness, agent="Vigil", holds_own_post=lambda event_id: True, effects=lambda: []
    )
    leg.invocations, leg.committed, leg.attention_calls = [dict(turn) for turn in invocations], [dict(action) for action in committed], []
    leg.agent = SimpleNamespace(requests=lambda: list(requests))
    leg._room = SimpleNamespace(receipts=SimpleNamespace(all_records=lambda: list(receipts)))
    leg.reports = {}
    leg.room_calls = room_calls
    return item, leg


def _receipts(request: str, trigger: str, disposition: str) -> list[dict]:
    return [
        {"request_id": request, "stage": "observation", "body": {"trigger_event_id": trigger}},
        {"request_id": request, "stage": "attention", "body": {"effective_disposition": disposition, "evidence_event_ids": [trigger]}},
    ]


class LegTest(unittest.TestCase):
    def test_a_harness_leg_takes_the_scenes_script_and_starts_the_scenes_world_and_the_moments_are_as_they_were(self):
        item = directed.spec("said-it-would-check")
        # The harness's own leg, which `OnTheTransport` is put in front of: its constructor builds a room client this test does not need.
        harness_legs = {"claude-code": probe.ClaudeCodeLeg, "codex": probe.CodexLeg}
        for harness, leg_class in HARNESS_LEGS.items():
            with self.subTest(harness=harness), mock.patch.object(discord_room, "DiscordRoom"), mock.patch.object(
                harness_legs[harness], "__init__", lambda self, ctx: None
            ):
                ctx = SimpleNamespace(directed=item, options=SimpleNamespace(discord_python=None), original_env={})
                leg = leg_class(ctx)
                self.assertIs(item, leg.directed)
                self.assertIs(item.script, leg.script)
                self.assertIs(discord_room.SCRIPT, leg_class.script, "without a scene it is the moments' script")
                plain = leg_class(SimpleNamespace(options=SimpleNamespace(discord_python=None), original_env={}))
                self.assertIsNone(plain.directed)
                self.assertIs(discord_room.SCRIPT, plain.script)

    def test_a_scene_is_played_by_the_director_and_the_start_gap_is_noted_for_the_continuity_check(self):
        item = directed.spec("bot-status-report")
        _, leg = _scene_leg(discord_room.DiscordCodexLeg, "bot-status-report", state=Path("."))
        leg.invocations = [{"request_id": "r1", "trigger": "t", "source": "WAKE"}]
        leg.discord.transport_journal = lambda: [{"outcome": "gap-signal"}]
        played = {"name": "bot-status-report"}
        with mock.patch.object(directed, "play_scene", return_value=played) as play, mock.patch.object(discord_room, "delivery_audits") as audits:
            audits.return_value = [{"delivery_id": "discord:transport-gap:1"}, {"delivery_id": "discord:message:3"}]
            moment = leg.play(item, settle_seconds=7.0)
        play.assert_called_once_with(leg, item.plan, 7.0)
        self.assertIs(played, moment)
        self.assertIs(item, leg._spec)
        self.assertEqual("discord:transport-gap:1", leg.discord.start_gap["gap"])
        self.assertEqual("bot-status-report", leg.invocations[0]["moment"])

    def test_a_scene_expects_the_transports_own_calls_and_the_ones_its_script_makes(self):
        acts = [{"expect": "directed", "graded": [{"scripted": "mhm"}, {"scripted": "speak"}]}]
        quiet = [{"expect": "directed", "graded": [{"scripted": "stay_quiet"}]}]
        self.assertTrue({discord_room.POST, discord_room.REACT} <= set(discord_room.directed_calls(acts, discord_room.TRANSPORT_ALWAYS)))
        self.assertEqual(discord_room.TRANSPORT_ALWAYS, discord_room.directed_calls(quiet, discord_room.TRANSPORT_ALWAYS))
        self.assertEqual({discord_room.POST, discord_room.REACT}, set(discord_room.TRANSPORT_CALLS) - set(discord_room.TRANSPORT_ALWAYS))
        self.assertEqual(("GET /users/@me", discord_room.POST), discord_room.directed_calls([{"expect": "directed", "graded": [{"scripted": "speak"}]}]))

    def test_the_scenes_checks_are_the_scenes_and_a_reconnect_is_not_required(self):
        _, leg = _scene_leg(discord_room.DiscordCodexLeg, "bot-status-report", state=Path("."), room_calls=[])
        seen = {}
        leg.discord.checks = lambda committed, **kwargs: seen.update(kwargs) or ["checks"]
        document = {"moments": [{"expect": "directed", "graded": [{"scripted": "speak"}]}], "lane_errors": [], "discord": {"serve_errors": []}}
        found = leg.room_checks(document)
        self.assertEqual(["checks", "room-errors"], [item if isinstance(item, str) else item.name for item in found])
        self.assertTrue(found[1].ok)
        self.assertFalse(seen["reconnects_required"])
        self.assertTrue(seen["gaps_fail"])
        wanted = seen["expected"]["Vigil"]["calls"]
        self.assertIn(discord_room.POST, wanted)
        self.assertNotIn(discord_room.REACT, wanted)
        self.assertEqual("directed-outcomes", leg.scripted_check(document["moments"]).name)

    def test_a_scene_fails_on_an_error_the_rooms_lane_met_or_that_ended_the_runners_serve_loop_and_a_plain_lane_is_as_it_was(self):
        _, leg = _scene_leg(discord_room.DiscordCodexLeg, "bot-status-report", state=Path("."), room_calls=[])
        leg.discord.checks = lambda committed, **kwargs: []
        moments = [{"expect": "directed", "graded": []}]
        clean = leg.room_checks({"moments": moments, "lane_errors": [], "discord": {"serve_errors": []}})
        self.assertEqual((["room-errors"], [True]), ([c.name for c in clean], [c.ok for c in clean]))
        broken = leg.room_checks({"moments": moments, "lane_errors": ["ValueError: a worker died"], "discord": {"serve_errors": ["OSError: the stream"]}})
        self.assertFalse(broken[0].ok)
        self.assertIn("the room's lane met: ValueError: a worker died", broken[0].detail)
        self.assertIn("the runner's serve loop ended with: OSError: the stream", broken[0].detail)
        # The same errors in a run that plays the moments are recorded and not checked, as they were.
        leg.directed = None
        self.assertEqual([], leg.room_checks({"moments": [{"expect": "post"}], "lane_errors": ["ValueError: x"], "discord": {"serve_errors": ["y"]}}))
        self.assertTrue(checks.room_errors([], []).ok)
        self.assertFalse(checks.room_errors([], ["y"]).ok)

    def test_a_scene_keeps_the_harnesss_room_tool_calls_in_its_record_and_the_moments_do_not(self):
        _, leg = _scene_leg(discord_room.DiscordCodexLeg, "bot-status-report", state=Path("."), room_calls=[{"tool": "room_send", "arguments": {}, "completed": True}])
        leg.discord.record = lambda: {"column": {}}
        leg.runner_calls, leg.serve_errors = {}, []
        self.assertEqual([{"tool": "room_send", "arguments": {}, "completed": True}], leg.room_record()["discord"]["room_tool_calls"])
        leg.directed = None
        self.assertNotIn("room_tool_calls", leg.room_record()["discord"])


class JudgeTest(unittest.TestCase):
    """A script that plays through a harness: graded from the scene, and failed when it plays a listed miss."""

    def run_scene(self, leg_class, scene_id, doings, *, calls="all", shown=True):
        """``doings`` is {moment number: (move, attention)}; returns the scene, its record and the leg after the leg judged it.

        ``calls`` are the room tool calls the harness's record shows: "all" is one completed call for each action, or a list.
        ``shown`` is whether a request the agent's model was asked holds each turn that ran.
        """

        item = directed.spec(scene_id)
        scene = item.plan.scene
        played = _played(scene)
        played.update(name=scene.id, expect="directed")
        turns, actions, receipts, requests = [], [], [], []
        for number, (move, disposition) in doings.items():
            graded = played["graded"][number]
            event_id, request = graded["event_id"], f"r{number}"
            receipts += _receipts(request, event_id, disposition)
            if move is None:
                continue
            turns.append({"request_id": request, "trigger": event_id, "source": "WAKE"})
            if shown:
                requests.append({"input": [{"content": [{"text": _tagged(_turn(event_id, "the message", request_id=request))}]}]})
            said = standin.SCENE_SAY.format(event=graded["event"])
            action = {
                "speak": {"kind": "message", "text": said, "origin_event_id": event_id},
                "mhm": {"kind": "reaction", "reaction": standin.SCENE_NOD, "target_event_id": event_id, "origin_event_id": event_id},
                "stay_quiet": None,
            }[move]
            if action:
                actions.append({"request_id": request, **action, "delivery": "sent"})
        if calls == "all":
            calls = [self.call_for(action) for action in actions]
        with tempfile.TemporaryDirectory() as directory:
            _, leg = _scene_leg(
                leg_class, scene_id, state=Path(directory), invocations=turns, committed=actions, receipts=receipts,
                requests=requests, room_calls=calls,
            )
            leg.judge([played])
        return scene, played, leg

    @staticmethod
    def call_for(action):
        """The completed room tool call that makes an action, as the harness's own record shows it."""

        if action["kind"] == "reaction":
            return {"tool": "room_react", "arguments": {"target_event_id": action["target_event_id"], "reaction": action["reaction"]}, "completed": True}
        return {"tool": "room_send", "arguments": {"text": action["text"]}, "completed": True}

    def quiet_and_right(self, scene):
        """What the script does at every moment of a scene: suppress where step 1 does, else the first fitting move."""

        return {
            number: (None, "SUPPRESS") if moment.step1 == "suppress" else (standin.SceneScript.intended(moment), "DEFER")
            for number, moment in enumerate(scene.moments)
        }

    def test_a_script_that_plays_each_scene_as_it_says_holds_through_each_harness_column(self):
        for harness, leg_class in HARNESS_LEGS.items():
            for scene_id in PLAYABLE:
                with self.subTest(harness=harness, scene=scene_id):
                    scene = directed.spec(scene_id).plan.scene
                    _, played, leg = self.run_scene(leg_class, scene_id, self.quiet_and_right(scene))
                    held = leg.scripted_check([played])
                    self.assertTrue(held.ok, held.detail)
                    self.assertEqual("directed-outcomes", held.name)
                    self.assertEqual({"fits"}, {item["grade"]["visible"] for item in played["graded"]})
                    self.assertEqual({"ok"}, {item["grade"]["step1"] for item in played["graded"]})
                    self.assertEqual(checks.FITS, played["outcome"])
                    # Attention was read from the participant's receipts, with the evidence it cited.
                    self.assertEqual(len(scene.moments), len(leg.attention_calls))
                    self.assertTrue(all("evidence" in call and call["served"] == {"provider": "scripted"} for call in leg.attention_calls))

    def test_a_script_that_plays_a_listed_miss_through_a_harness_column_fails_and_names_the_moment(self):
        for harness, leg_class in HARNESS_LEGS.items():
            for scene_id in PLAYABLE:
                scene = directed.spec(scene_id).plan.scene
                for number, moment in enumerate(scene.moments):
                    for miss in moment.misses:
                        with self.subTest(harness=harness, scene=scene_id, moment=moment.label, miss=miss["move"]):
                            doings = self.quiet_and_right(scene)
                            doings[number] = (
                                (None, "SUPPRESS") if miss["move"] == "stay_quiet" and moment.step1 == "suppress" else (miss["move"], "DEFER")
                            )
                            _, played, leg = self.run_scene(leg_class, scene_id, doings)
                            held = leg.scripted_check([played])
                            self.assertFalse(held.ok)
                            self.assertEqual("directed-outcomes", held.name)
                            self.assertIn(f"{scene_id}, {moment.label}", held.detail)
                            self.assertIn(miss["why"], held.detail)
                            self.assertEqual(checks.MISSES, played["outcome"])

    def test_the_status_report_the_agent_spoke_on_reads_what_the_room_would_show(self):
        # The finding a harness column would pin: a CI line from a bot, answered. The room shows a message on it.
        for leg_class in HARNESS_LEGS.values():
            scene, played, leg = self.run_scene(leg_class, "bot-status-report", {0: ("speak", "DEFER")})
            item = played["graded"][0]
            self.assertEqual(("speak", "agent"), (item["result"], item["by"]))
            self.assertEqual({"visible": "miss", "step1": "over-wake"}, item["grade"])
            held = leg.scripted_check([played])
            self.assertFalse(held.ok)
            self.assertIn("bot-status-report, the CI status line: the move was speak, graded miss, not fits", held.detail)
            self.assertIn("step 1 graded over-wake", held.detail)

    def test_a_turn_the_script_did_not_make_is_listed_as_an_action_outside_the_graded_turns(self):
        scene = directed.spec("story-across-messages").plan.scene
        scene_id = scene.id
        doings = self.quiet_and_right(scene)
        item, played, leg = self.run_scene(HARNESS_LEGS["codex"], scene_id, doings)
        self.assertEqual([], played["other_actions"])
        # The chatter gets a post the script never makes.
        with tempfile.TemporaryDirectory() as directory:
            _, again = _scene_leg(
                HARNESS_LEGS["codex"], scene_id, state=Path(directory), invocations=leg.invocations,
                committed=[*leg.committed, {"request_id": "chatter", "kind": "message", "text": "uninvited", "delivery": "sent"}],
                receipts=[record for record in leg._room.receipts.all_records()], room_calls=leg.room_calls,
            )
            replay = _played(scene)
            replay.update(name=scene_id, expect="directed")
            again.judge([replay])
        self.assertEqual(["message 'uninvited'"], [f"{a['kind']} {a['text']!r}" for a in replay["other_actions"]])
        self.assertIn("a turn that was not graded made a message 'uninvited'", again.scripted_check([replay]).detail)

    def test_every_action_that_reached_the_room_needs_a_completed_room_tool_call_of_its_own_and_a_quiet_scene_needs_none(self):
        scene = directed.spec("story-across-messages").plan.scene
        doings = self.quiet_and_right(scene)
        # The calls of a scene that went right back every action: a nod, a nod and a post.
        _, played, leg = self.run_scene(HARNESS_LEGS["claude-code"], scene.id, doings)
        self.assertEqual(3, len(leg.room_calls))
        self.assertTrue(leg.scripted_check([played]).ok, leg.scripted_check([played]).detail)
        # No call at all: each of the three actions is named, however it got to the room.
        _, played, leg = self.run_scene(HARNESS_LEGS["claude-code"], scene.id, doings, calls=[])
        held = leg.scripted_check([played])
        self.assertFalse(held.ok)
        self.assertEqual(3, held.detail.count("reached the room, but the harness showed no completed room tool call for it"))
        # A run-wide fact would pass this: the harness made calls, but not one for the last post. Per action, it fails and names it.
        _, played, leg = self.run_scene(HARNESS_LEGS["codex"], scene.id, doings)
        fewer = leg.room_calls[:-1]
        _, played, leg = self.run_scene(HARNESS_LEGS["codex"], scene.id, doings, calls=fewer)
        held = leg.scripted_check([played])
        self.assertFalse(held.ok)
        self.assertEqual(1, held.detail.count("no completed room tool call"))
        self.assertIn("story-across-messages, the story ends with a question: its message reached the room", held.detail)
        # A call that did not complete made nothing; a call of the wrong tool or for other words backs nothing.
        for broken in ({"completed": False}, {"tool": "room_react"}, {"arguments": {"text": "something else"}}):
            _, played, leg = self.run_scene(HARNESS_LEGS["codex"], scene.id, doings)
            calls = [dict(call) for call in leg.room_calls]
            calls[-1].update(broken)
            _, played, leg = self.run_scene(HARNESS_LEGS["codex"], scene.id, doings, calls=calls)
            self.assertFalse(leg.scripted_check([played]).ok, broken)
        # One call backs one action: two nods that the record shows one reaction call for.
        call = {"tool": "room_react", "arguments": {"target_event_id": "e", "reaction": "x"}, "completed": True}
        twice = {"moments": [{"expect": "directed", "name": "s", "graded": [
            {"label": "m", "reached": True, "grade": {"visible": "fits", "step1": "ok"}, "result": "mhm", "scripted": "mhm", "off_script": [],
             "actions": [{"kind": "reaction", "target_event_id": "e", "reaction": "x", "delivered": True}] * 2}], "deliveries": [], "other_actions": []}]}
        self.assertEqual(1, checks.directed_outcomes(twice["moments"], room_tool_calls=[call]).detail.count("no completed room tool call"))
        self.assertTrue(checks.directed_outcomes(twice["moments"], room_tool_calls=[call, call]).ok)
        # A quiet scene makes no call and needs none; the reference, which acts through no tool, is not asked.
        report = directed.spec("bot-status-report").plan.scene
        _, played, leg = self.run_scene(HARNESS_LEGS["claude-code"], report.id, {0: (None, "SUPPRESS")}, calls=[])
        self.assertTrue(leg.scripted_check([played]).ok)
        self.assertTrue(checks.directed_outcomes([played]).ok)

    def test_the_calls_a_harness_shows_are_read_from_its_own_record(self):
        send, react = "mcp__nunchi__room_send", "mcp__nunchi__room_react"
        stream = [
            {"direction": "to-claude", "message": {"type": "user"}},
            {"direction": "from-claude", "message": {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": react, "input": {"target_event_id": "e1", "reaction": "x"}}]}}},
            {"direction": "from-claude", "message": {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "Done"}]}}},
            {"direction": "from-claude", "message": {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t2", "name": send, "input": {"text": "hi"}},
                {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "ls"}}]}}},
            {"direction": "from-claude", "message": {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "refused"}]}}},
            {"direction": "from-claude", "message": {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t4", "name": send, "input": {"text": "never answered"}}]}}},
        ]
        self.assertEqual(
            [
                {"tool": react, "arguments": {"target_event_id": "e1", "reaction": "x"}, "completed": True},
                {"tool": send, "arguments": {"text": "hi"}, "completed": False},
                {"tool": send, "arguments": {"text": "never answered"}, "completed": False},
            ],
            probe.claude_room_calls(stream, [send, react]),
        )
        items = [
            {"type": "mcpToolCall", "server": "nunchi_room", "tool": "room_send", "arguments": {"text": "hi"}, "status": "completed", "error": None},
            {"type": "mcpToolCall", "server": "nunchi_room", "tool": "room_send", "arguments": {"text": "x"}, "status": "failed", "error": {"message": "no"}},
            {"type": "mcpToolCall", "server": "another", "tool": "room_send", "arguments": {}, "status": "completed"},
            {"type": "agentMessage", "text": "words"},
        ]
        self.assertEqual(
            [{"tool": "room_send", "arguments": {"text": "hi"}, "completed": True}, {"tool": "room_send", "arguments": {"text": "x"}, "completed": False}],
            probe.codex_room_calls(items, "nunchi_room"),
        )

    def test_a_quiet_answer_to_a_message_the_model_was_never_shown_fails_the_addressing_check(self):
        report = directed.spec("bot-status-report").plan.scene
        chatter = {0: (None, "SUPPRESS")}
        for leg_class in HARNESS_LEGS.values():
            # A turn ran on the status report's first message and stayed silent. With the model shown it, nothing is wrong.
            for shown, ok in ((True, True), (False, False)):
                scene, played, leg = self.run_scene(leg_class, report.id, chatter, shown=shown)
                chatty = {"request_id": "chatter", "trigger": played["deliveries"][0]["event_id"], "source": "DEFER"}
                with tempfile.TemporaryDirectory() as directory:
                    _, again = _scene_leg(
                        leg_class, report.id, state=Path(directory), invocations=[*leg.invocations, chatty], receipts=leg._room.receipts.all_records(),
                        requests=[{"input": [{"content": [{"text": _tagged(_turn(chatty["trigger"], "the first message", request_id="chatter"))}]}]}]
                        if shown else [],
                        room_calls=[],
                    )
                    replay = _played(scene)
                    replay.update(name=scene.id, expect="directed")
                    again.judge([replay])
                    held = checks.discord_addressing([replay], agent="discord:actor:1", writes=[])
                self.assertEqual(ok, held.ok, held.detail)
                if not ok:
                    self.assertIn("turn chatter ran on it, but no request the agent's model was asked shows that turn", held.detail)
                    self.assertIn(f"{scene.id} {replay['deliveries'][0]['scene_event']}", held.detail)

    def test_what_nunchis_room_log_holds_of_each_message_goes_beside_what_was_sent(self):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played(scene)
        played.update(name=scene.id, expect="directed")
        first = played["deliveries"][0]["event_id"]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "x.observations.jsonl").write_text(
                json.dumps({"event": {"id": first, "type": "message", "mentioned_actor_ids": ["discord:actor:9"], "reply_to_event_id": None}}) + "\n",
                encoding="utf-8",
            )
            _, leg = _scene_leg(HARNESS_LEGS["codex"], scene.id, state=state)
            leg.judge([played])
        self.assertEqual({"mentioned_actor_ids": ["discord:actor:9"], "reply_to_event_id": None}, played["deliveries"][0]["logged"])


# -- the command and CI ---------------------------------------------------------------------------------------


class CommandTest(unittest.TestCase):
    def run_main(self, *arguments):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as error:
            code = probe.main([*arguments, "--out", directory])
            self.assertEqual([], list(Path(directory).iterdir()), "a refused command starts and writes nothing")
        return code, error.getvalue()

    def test_a_scene_is_played_scripted_in_the_discord_room_by_the_reference_claude_code_and_codex(self):
        for harness in ("reference", "claude-code", "codex"):
            with self.subTest(harness=harness), mock.patch.object(probe, "run_probe", return_value=0) as run:
                code, error = self.run_main("--harness", harness, "--scripted", "--room", "discord", "--scene", "story-across-messages")
                self.assertEqual((0, ""), (code, error))
                options = run.call_args[0][0]
                self.assertEqual((harness, "story-across-messages", "discord", True), (options.harness, options.scene, options.room, options.scripted))
            for missing in (["--room", "discord"], ["--scripted"]):
                with self.subTest(harness=harness, only=missing):
                    code, error = self.run_main("--harness", harness, "--scene", "story-across-messages", *missing)
                    self.assertEqual(probe.EXIT_USAGE, code)

    def test_hermes_is_parked_and_plays_no_scene(self):
        code, error = self.run_main("--harness", "hermes", "--scripted", "--room", "discord", "--scene", "story-across-messages")
        self.assertEqual(probe.EXIT_USAGE, code)
        self.assertIn("Hermes is parked", error)
        with self.assertRaisesRegex(ValueError, "played in the Discord room by reference or claude-code or codex"):
            probe.run_probe(probe.Options(harness="hermes", out=Path("x"), scripted=True, room="discord", scene="bot-status-report"))
        self.assertFalse(hasattr(discord_room.HermesGatewayLeg, "directed"))
        self.assertNotIn("hermes", probe.SCENE_HARNESSES)

    def test_each_columns_leg_and_the_scene_come_from_the_options(self):
        for harness, leg_class in HARNESS_LEGS.items():
            with self.subTest(harness=harness):
                options = probe.Options(harness=harness, out=Path("x"), scripted=True, room="discord", scene="bot-status-report")
                found, specs, route = probe._room_parts(options)
                self.assertIs(leg_class, found)
                self.assertEqual(["bot-status-report"], [spec.name for spec in specs])
                self.assertIsInstance(specs[0], directed.DirectedSpec)
                plain = probe._room_parts(probe.Options(harness=harness, out=Path("x"), scripted=True, room="discord"))
                self.assertEqual(discord_room.MOMENTS, plain[1])


def scene_loop(job: str) -> list[str]:
    """The scene ids a job's ``for scene in ...; do`` loop plays (the list may continue on following lines with a backslash)."""

    loop = re.search(r"for scene in ([a-z \\\n-]+); do", job)
    return [word for word in loop.group(1).split() if word != "\\"]


class CiTest(unittest.TestCase):
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def job(self, name: str) -> str:
        """The text of one job: from its key to the next key at the same indent."""

        start = self.text.index(f"\n  {name}:\n") + 1
        following = re.search(r"\n  [a-z][a-z-]*:\n", self.text[start + len(name) + 3 :])
        return self.text[start : start + len(name) + 3 + following.start()] if following else self.text[start:]

    def test_the_claude_code_and_codex_jobs_play_each_playable_scene_after_their_discord_lane_with_the_scan_and_upload(self):
        for job_name, harness, lane, scenes, scan, artifact in (
            ("claude-code-mod", "claude-code", "discord_claude_lane", "discord_claude_scenes_lane", "discord_claude_scenes_scan", "rehearsal-discord-claude-code-scenes-"),
            ("codex-app-server", "codex", "discord_codex_lane", "discord_codex_scenes_lane", "discord_codex_scenes_scan", "rehearsal-discord-codex-scenes-"),
        ):
            with self.subTest(job=job_name):
                job = self.job(job_name)
                # One loop over the four scenes, one probe command, in the launcher, offline, with the lane's own sandbox check.
                self.assertEqual(1, job.count("--scene"))
                self.assertEqual(sorted(PLAYABLE), sorted(scene_loop(job)))
                self.assertIn(f"--harness {harness} --scripted --room discord", job[job.index(f"id: {scenes}"):])
                self.assertIn("discord_net --offline --require-bwrap --", job[job.index(f"id: {scenes}"):])
                self.assertIn('--out "$RUNNER_TEMP/rehearsal-directed/$scene"', job)
                # In order: the lane, then the scenes, then their scan, then the upload (which needs a clean scan).
                positions = [job.index(f"id: {name}") for name in (lane, scenes, scan)]
                self.assertEqual(sorted(positions), positions)
                self.assertLess(positions[-1], job.index(artifact))
                self.assertIn(f"if: failure() && steps.{scenes}.outcome == 'failure'", job)
                self.assertIn(f"if: failure() && steps.{scan}.outcome == 'success'", job)
                self.assertIn("python -m evals.rehearsal.scan --out \"$RUNNER_TEMP/rehearsal-directed\"", job)
                self.assertEqual(2, job.count("--env NUNCHI_ATTENTION_API_KEY --env REHEARSAL_CANARY"))
                self.assertIn("path: ${{ runner.temp }}/rehearsal-directed/", job)
                # The lane's sandbox is the lane's: CI never passes --no-sandbox, here or in the lane above.
                commands = [line for line in job.splitlines() if "--no-sandbox" in line and not line.lstrip().startswith("#")]
                self.assertEqual([], commands)

    def test_every_step_of_the_three_jobs_that_runs_the_launcher_has_a_timeout_sized_from_the_measured_times(self):
        # Measured here (2026-10-11): a room lane 14 to 21 seconds, the eleven scenes 2 to 3 minutes for a column. CI is slower and
        # runs bubblewrap, so the room lane gets 15 minutes and the scene loop 20: a hung scene fails the job rather than waiting
        # for the runner's six hours. The loops still fail the job on a failing scene (the test below).
        for job_name in ("discord-standin", "codex-app-server", "claude-code-mod"):
            job = self.job(job_name)
            steps = re.split(r"\n      - ", job)[1:]
            launched = [step for step in steps if "discord_net" in step]
            self.assertEqual(2, len(launched), f"{job_name}: the room lane and the scene loop")
            for step in launched:
                with self.subTest(job=job_name, step=step.splitlines()[0]):
                    found = re.search(r"\n        timeout-minutes: (\d+)\n", step)
                    self.assertIsNotNone(found, "a step that runs the launcher needs a timeout-minutes")
                    minutes = int(found.group(1))
                    if "--scene" in step:
                        self.assertTrue(15 <= minutes <= 30, minutes)
                    else:
                        self.assertTrue(10 <= minutes <= 20, minutes)

    def test_each_scene_loop_fails_its_step_after_the_last_scene_when_any_scene_failed_and_does_not_stop_at_the_first(self):
        for job_name, lane in (
            ("discord-standin", "discord_scenes_lane"),
            ("claude-code-mod", "discord_claude_scenes_lane"),
            ("codex-app-server", "discord_codex_scenes_lane"),
        ):
            with self.subTest(job=job_name):
                job = self.job(job_name)
                start = job.index(f"id: {lane}")
                step = job[start : job.find("\n      - name:", start) if job.find("\n      - name:", start) != -1 else len(job)]
                script = step[step.index("run: |") :]
                # A scene that fails marks the step failed and the loop goes on; the step then fails after the last scene.
                self.assertIn("set -uo pipefail", script)
                self.assertNotIn("set -e", script, "an error exit would stop the loop at the first failed scene")
                body = script[script.index("for scene in") : script.index("done")]
                self.assertIn('|| { echo "::error::the scene $scene failed"; failed=1; }', body)
                self.assertNotIn("|| true", script)
                self.assertLess(script.index("failed=0"), script.index("for scene in"))
                after = script[script.index("done") + len("done") :]
                self.assertEqual('exit "$failed"', after.strip())

    def test_the_reference_job_plays_the_same_scenes_and_the_hermes_job_plays_none(self):
        reference = self.job("discord-standin")
        self.assertEqual(1, reference.count("--scene"))
        self.assertIn("--harness reference --scripted --room discord", reference)
        self.assertEqual(sorted(PLAYABLE), sorted(scene_loop(reference)))
        hermes = self.job("hermes-plugin")
        self.assertNotIn("--scene", hermes)
        self.assertNotIn("rehearsal-directed", hermes)


if __name__ == "__main__":
    unittest.main()
