"""The director, the grader and the scene script (rehearsal PR 4a, `evals/rehearsal/directed.py`).

The lane itself runs the reference as a process at Discord's real names, so it
needs the launcher and runs in CI's scripted lane. What is tested here needs
neither: which behavior scenes the director can play and why not the others,
how a played scene is graded (both ways, from the scene's own expectations),
the script attention and the agent follow, what the director posts to the
stand-in (on plain loopback, as `test_rehearsal_discord_room.py` drives it),
and the hard check that holds the script to the scene.
"""

from __future__ import annotations

import contextlib
import copy
from datetime import datetime, timezone
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from nunchi.participant_model import _validate_inner_action

from evals.behavior import run as behavior_run
from evals.behavior.scene import load_scene, load_scenes, parse_scene
from evals.behavior.score import agent_move, cell, grade
from evals.rehearsal import checks, directed, discord_room, probe, record, standin
from evals.rehearsal.fake_discord.world import id_ms

from tests.v2.test_rehearsal_discord_room import _StandIn, _room, _turn

ROOT = Path(__file__).resolve().parents[2]

# Why each of the 17 behavior scenes cannot be played, or () where it can. A new scene fails
# `test_every_behavior_scene_is_classified` until it is listed here, and so does a scene whose
# plan changed: update `docs/rehearsal.md` (the table in "Directed scenes") with it.
PINNED = {
    "addressee-first": ("pause",),
    "addressee-never-answers": (),
    "answered-by-someone-else": ("seen-through",),
    "answered-while-composing": (),
    "approval-comes-through": ("outcome", "pause"),
    "asked-while-busy": (),
    "bot-status-report": (),
    "build-finishes-after-promise": (),
    "build-finishes-long-after-promise": (),
    "did-you-see": (),
    "mention-in-busy-room": (),
    "never-mind-while-composing": (),
    "only-they-can-do-it": ("pause",),
    "quiet-for-hours": ("time",),
    "said-it-would-check": (),
    "story-across-messages": (),
    "two-agents-one-question": ("several-participants",),
}
# The eleven the lane plays in CI, one run each: the four of PR 4a and 4b, and the seven of PR 4c.
PLAYABLE = (
    "addressee-never-answers",
    "answered-while-composing",
    "asked-while-busy",
    "bot-status-report",
    "build-finishes-after-promise",
    "build-finishes-long-after-promise",
    "did-you-see",
    "mention-in-busy-room",
    "never-mind-while-composing",
    "said-it-would-check",
    "story-across-messages",
)
# The four scenes of PR 4a and 4b, as the CI loops list them first; the seven of PR 4c follow.
FIRST_FOUR = ("bot-status-report", "story-across-messages", "said-it-would-check", "mention-in-busy-room")
SEVEN = tuple(scene for scene in PLAYABLE if scene not in FIRST_FOUR)
# What the core's look before posting tells an agent when a message arrived while it composed (`standin.NEWS_MARK`).
NEWS = f"{standin.NEWS_MARK} 1 new message(s) arrived while you were composing."


def _news(script, event):
    """The page a held turn is shown before it decides: a graded moment whose own turn is held has one, any other none."""

    return NEWS if event in script.gates else None


def _scene(events: list[dict], moments: list[dict], **fields) -> object:
    raw = {
        "id": "director-test",
        "title": "A scene to direct",
        "source": "test",
        "review": "draft: test",
        "platform": "discord",
        "participants": ["vigil"],
        "actors": {"alice": {"display_name": "Alice", "kind": "human"}, "sam": {"display_name": "Sam", "kind": "human"}},
        "events": events,
        "moments": moments,
        **fields,
    }
    return parse_scene(raw)


def _moment(event: str, fitting: list[str], misses: list[str] = (), step1: str = "pass") -> dict:
    return {"event": event, "step1": step1, "fitting": fitting, "misses": [{"move": move, "why": f"{move} is wrong here"} for move in misses]}


# A scene with history (older than ten minutes before the first graded message), a mention of another
# agent, a reply and a ping of the agent: what the director has to get right on the stand-in.
def _directed_scene():
    return _scene(
        [
            {"id": "h1", "author": "alice", "at": "-3h", "text": "Morning all."},
            {"id": "h2", "author": "sam", "at": "-2h", "text": "Morning Alice."},
            {"id": "g1", "author": "alice", "at": "-30s", "mentions": ["castor"], "text": "Castor, how does the backoff work?"},
            {"id": "g2", "author": "sam", "at": "-20s", "reply_to": "g1", "text": "I wondered that too."},
            {"id": "g3", "author": "alice", "at": "0s", "mentions": ["vigil"], "text": "Vigil, did you see that?"},
        ],
        [_moment("g1", ["wait", "stay_quiet"]), _moment("g3", ["speak"], ["stay_quiet", "mhm"])],
    )


# -- which scenes can be played ---------------------------------------------------------------------------


class PlanTest(unittest.TestCase):
    def test_every_behavior_scene_is_classified(self):
        plans = {item.scene.id: item.reasons for item in directed.load_plans()}
        self.assertEqual(sorted(PINNED), sorted(plans), "a scene was added or removed: classify it in PINNED and in docs/rehearsal.md")
        for scene_id, reasons in PINNED.items():
            with self.subTest(scene=scene_id):
                self.assertEqual(reasons, plans[scene_id])
        self.assertEqual(17, len(plans))
        self.assertEqual(sorted(PLAYABLE), sorted(scene_id for scene_id, reasons in PINNED.items() if not reasons))
        self.assertTrue(set().union(*PINNED.values()) <= set(directed.REASONS), "every reason is explained")

    def test_a_scene_that_cannot_be_played_says_why_and_a_playable_one_does_not(self):
        plans = {item.scene.id: item for item in directed.load_plans()}
        self.assertIsNone(plans["story-across-messages"].unplayable)
        self.assertIsNone(plans["addressee-never-answers"].unplayable, "its v1 is the agent's own line, played on a cue (PR 4c)")
        self.assertIn("look-again timer", plans["only-they-can-do-it"].unplayable)
        self.assertIn("look-again timer", plans["addressee-first"].unplayable)
        self.assertIn("several agents", plans["two-agents-one-question"].unplayable)
        self.assertIn("hours of quiet", plans["quiet-for-hours"].unplayable)
        self.assertIn("m1 follows 7 hours of quiet", plans["quiet-for-hours"].unplayable)
        self.assertIn("approved action", plans["approval-comes-through"].unplayable)

    def test_an_event_of_the_agents_own_is_played_by_the_agent_as_its_move_on_a_message_never_posted_by_the_director(self):
        # What a scene says Vigil said earlier is a line the agent says itself: the director never posts as the agent.
        scene = _scene(
            [
                {"id": "z1", "author": "alice", "at": "-2h", "mentions": ["vigil"], "text": "Vigil, can you check the build?"},
                {"id": "v1", "author": "vigil", "at": "-2h", "reply_to": "z1", "text": "I will."},
                {"id": "r1", "type": "reaction", "author": "vigil", "at": "-1h", "target": "z1", "reaction": "x"},
                {"id": "q1", "author": "alice", "at": "0s", "mentions": ["vigil"], "text": "Vigil, how does it work?"},
            ],
            [_moment("q1", ["speak"])],
        )
        # Two lines on one message: the agent makes one action per turn, so the second cannot be placed.
        self.assertEqual(("agent-event",), directed.plan(scene).reasons)
        self.assertIn("r1 is a second move on z1", directed.plan(scene).unplayable)
        with self.assertRaisesRegex(directed.Unplayable, "second move on z1"):
            directed.play_scene(SimpleNamespace(), directed.plan(scene), 1.0)
        fine = _scene([*scene.events[:2], scene.events[3]], [_moment("q1", ["speak"])])
        item = directed.plan(fine)
        self.assertEqual((), item.reasons)
        self.assertEqual([("v1", "z1", "reply", "I will.", False)], [(l.event, l.trigger, l.kind, l.text, l.cue) for l in item.lines])
        self.assertEqual((), item.cues)

    def test_a_line_that_cannot_be_placed_is_refused_and_says_which(self):
        def refused(events, moments, expect):
            item = directed.plan(_scene(events, moments))
            self.assertEqual(("agent-event",), item.reasons)
            self.assertIn(expect, item.unplayable)

        z1 = {"id": "z1", "author": "alice", "at": "-2m", "mentions": ["vigil"], "text": "Vigil, a question?"}
        q = {"id": "q1", "author": "alice", "at": "0s", "text": "Vigil, anything else?"}
        # A line on a message a moment grades: the graded moment is the agent's own move there.
        refused([z1, {"id": "v1", "author": "vigil", "at": "-1m", "reply_to": "z1", "text": "Yes."}, q], [_moment("z1", ["speak"])], "which a moment grades")
        # A line on the agent's own line.
        refused(
            [z1, {"id": "v1", "author": "vigil", "at": "-90s", "reply_to": "z1", "text": "Yes."},
             {"id": "v2", "author": "vigil", "at": "-60s", "reply_to": "v1", "text": "Really."}, q],
            [_moment("q1", ["speak"])],
            "which is its own event",
        )
        # Two lines that answer nothing would need two cues, with the same words.
        refused(
            [{"id": "v1", "author": "vigil", "at": "-3m", "text": "One."}, {"id": "v2", "author": "vigil", "at": "-2m", "text": "Two."}, q],
            [_moment("q1", ["speak"])],
            "a cue is already added for another line",
        )

    def test_a_line_that_answers_nothing_is_cued_by_a_message_of_a_persons_added_just_before_it(self):
        scene = _scene(
            [
                {"id": "v1", "author": "vigil", "at": "-3h", "text": "Heads up: the cert expired."},
                {"id": "q1", "author": "sam", "at": "0s", "text": "Anyone know why the deploy failed?"},
            ],
            [_moment("q1", ["speak"])],
        )
        item = directed.plan(scene)
        self.assertEqual((), item.reasons)
        # The first human who posts in the scene cues it, naming the agent, and the cue is a trigger like any message.
        self.assertEqual(
            [{"id": "cue-v1", "author": "sam", "mentions": ["vigil"], "text": "Vigil, anything to report?", "before": "v1"}],
            [dict(cue) for cue in item.cues],
        )
        self.assertEqual([("v1", "cue-v1", "message", True)], [(l.event, l.trigger, l.kind, l.cue) for l in item.lines])
        # Played live from the cue: nothing after the agent's first line can be backdated, and its three hours are seconds.
        self.assertEqual((0, 2, 3 * 3600), (len(item.history), len(item.live), item.compressed))

    def test_other_reasons_a_scene_cannot_be_played(self):
        reaction = _scene(
            [
                {"id": "m1", "author": "alice", "at": "-5s", "text": "Look at this."},
                {"id": "r1", "type": "reaction", "author": "sam", "at": "-2s", "target": "m1", "reaction": "x"},
                {"id": "m2", "author": "alice", "at": "0s", "text": "Vigil?"},
            ],
            [_moment("m2", ["speak"])],
        )
        self.assertEqual(("reaction-event",), directed.plan(reaction).reasons)
        other = _scene(
            [{"id": "m1", "author": "alice", "at": "0s", "text": "Castor?"}], [_moment("m1", ["speak"])], participants=["castor"]
        )
        self.assertEqual(("other-participant",), directed.plan(other).reasons)

    def test_a_scene_is_split_into_history_older_than_ten_minutes_before_the_first_graded_message_and_the_rest(self):
        plans = {item.scene.id: item for item in directed.load_plans()}
        self.assertEqual(600, directed.HISTORY_SECONDS)
        ids = lambda events: [event["id"] for event in events]  # noqa: E731
        # The status report is 30 minutes after the first message; the story fits in two minutes.
        self.assertEqual((["c1"], ["b1"]), (ids(plans["bot-status-report"].history), ids(plans["bot-status-report"].live)))
        self.assertEqual(([], ["s1", "s2", "s3", "s4", "s5"]), (ids(plans["story-across-messages"].history), ids(plans["story-across-messages"].live)))
        self.assertEqual((), plans["said-it-would-check"].history)
        # 'c20' is 11 minutes before the follow-up and history; 'c21' is exactly ten and is played.
        busy = plans["mention-in-busy-room"]
        self.assertEqual(("c20", "c21"), (ids(busy.history)[-1], ids(busy.live)[0]))
        self.assertEqual((21, 11), (len(busy.history), len(busy.live)))
        # A scene with a line of the agent's is played live from the message that triggers it (or from the cue): the stand-in stamps the
        # agent's post at the wall, so nothing after it can be backdated, and the scene's own time is compressed.
        for scene_id in SEVEN:
            with self.subTest(scene=scene_id):
                self.assertEqual([], ids(plans[scene_id].history))
                self.assertGreater(plans[scene_id].compressed, 0)
        self.assertEqual({"asked-while-busy": 50, "answered-while-composing": 3 * 3600, "never-mind-while-composing": 3 * 3600,
                          "build-finishes-after-promise": 50 * 60, "build-finishes-long-after-promise": 3 * 3600,
                          "did-you-see": 12 * 60, "addressee-never-answers": 2 * 3600},
                         {scene_id: plans[scene_id].compressed for scene_id in SEVEN})
        self.assertEqual(0, plans["story-across-messages"].compressed)
        for item in plans.values():
            with self.subTest(scene=item.scene.id):
                self.assertEqual(ids(item.scene.events), ids(item.history) + ids(item.live))
                graded = {moment.event for moment in item.scene.moments if moment.event}
                self.assertTrue(graded <= set(ids(item.live)), "a graded message is always played live")

    def test_spec_names_the_playable_scenes_when_asked_for_one_that_cannot_be_played(self):
        self.assertEqual("story-across-messages", directed.spec("story-across-messages").name)
        with self.assertRaises(directed.Unplayable) as caught:
            directed.spec("quiet-for-hours")
        self.assertIn("Playable: " + ", ".join(PLAYABLE), str(caught.exception))
        with self.assertRaisesRegex(directed.Unplayable, "no behavior scene is called 'nope'"):
            directed.spec("nope")

    def test_a_graded_message_has_text_of_its_own_so_the_script_can_tell_it_from_the_chatter(self):
        for scene_id in PLAYABLE:
            item = directed.spec(scene_id)
            scene = item.plan.scene
            # The messages the script must tell apart: the graded ones and those that trigger a line of the agent's (a cue too).
            known = {moment.event for moment in scene.moments} | {line.trigger for line in item.plan.lines}
            texts = {event["id"]: event.get("text") for event in scene.events} | {cue["id"]: cue["text"] for cue in item.plan.cues}
            for event in known:
                with self.subTest(scene=scene_id, event=event):
                    self.assertEqual([event], [other for other, text in texts.items() if text == texts[event]])


# -- what attention and the agent do -----------------------------------------------------------------------


def _expected_lean(moment) -> str:
    if moment.step1 == "suppress":
        return "SUPPRESS"
    return {"speak": "WAKE", "mhm": "mhm"}.get(moment.fitting[0], "DEFER")


class ScriptTest(unittest.TestCase):
    def test_at_each_graded_moment_attention_and_the_agent_do_what_the_first_fitting_move_says(self):
        for scene_id in PLAYABLE:
            item = directed.spec(scene_id)
            scene, script = item.plan.scene, item.script
            for moment in scene.moments:
                with self.subTest(scene=scene_id, moment=moment.label):
                    text = f"<@42> {next(e for e in scene.events if e['id'] == moment.event)['text']}"
                    script.register(text, moment.event)
                    self.assertIs(moment, script.moment(text))
                    self.assertEqual(_expected_lean(moment), script.lean(text))
                    # A moment whose own turn is held decides once the core has shown the turn what landed meanwhile.
                    action = script.action(_turn("discord:message:7", text), news=_news(script, moment.event))
                    self.assertEqual(action, _validate_inner_action(action))
                    move = agent_move([action])
                    self.assertEqual(standin.SceneScript.intended(moment), move)
                    self.assertEqual({"speak": "message", "mhm": "reaction", "stay_quiet": "silence"}[move], action["kind"])
                    if move == "speak":
                        self.assertIn(f"({moment.event})", action["text"])
                    if move == "mhm":
                        self.assertEqual(("discord:message:7", standin.SCENE_NOD), (action["target_event_id"], action["reaction"]))
                    # The script is the scene's own: it never plays a clear miss, and step 1 reads ok.
                    seen = grade(moment, move, attention="stay_quiet" if script.lean(text) == "SUPPRESS" else "woken")
                    self.assertEqual({"visible": "fits", "step1": "ok"}, seen)

    def test_the_action_the_grader_expects_is_the_one_the_script_makes_worked_out_from_the_scene_alone(self):
        for scene_id in PLAYABLE:
            item = directed.spec(scene_id)
            for moment in item.plan.scene.moments:
                with self.subTest(scene=scene_id, moment=moment.label):
                    text = f"<@42> {next(e for e in item.plan.scene.events if e['id'] == moment.event)['text']}"
                    item.script.register(text, moment.event)
                    made = item.script.action(_turn("discord:message:7", text), news=_news(item.script, moment.event))
                    expected = directed.scripted_action(moment, "discord:message:7")
                    if expected is None:
                        self.assertEqual({"kind": "silence"}, made)
                    else:
                        self.assertEqual(expected, {key: made.get(key) for key in expected})
                        # Worked out from the scene's first fitting move, not by asking the script what it did.
                        self.assertEqual(standin.SceneScript.intended(moment), agent_move([expected]))

    def test_a_message_no_moment_grades_is_chatter_attention_passes_and_the_agent_stays_quiet(self):
        script = directed.spec("story-across-messages").script
        self.assertEqual("DEFER", script.lean("something nobody graded"))
        self.assertEqual({"kind": "silence"}, script.action(_turn("discord:message:9", "something nobody graded")))
        self.assertEqual({"kind": "silence"}, script.action({"wake": {}}), "a turn with no trigger")

    def test_two_moments_never_post_alike_and_scripted_attention_leans_as_the_script_says(self):
        script = directed.spec("said-it-would-check").script
        first, second = (moment for moment in script.moments.values())
        script.register("q1 text", first.event)
        script.register("q2 text", second.event)
        said = {script.action(_turn("discord:message:1", text))["text"] for text in ("q1 text", "q2 text")}
        self.assertEqual(2, len(said), "discord-writes-reconciled matches a write to an action by its content")
        attention = standin.ScriptedAttention(script=script)
        self.addCleanup(attention.close)
        body = lambda text: {"messages": [{"content": json.dumps({"observation": {"trigger_event_id": "e", "events": [{"id": "e", "text": text}]}})}]}  # noqa: E731
        self.assertEqual(("WAKE", "e"), attention.disposition(body("q1 text")))
        self.assertEqual(("DEFER", "e"), attention.disposition(body("chatter")))
        # Without a script it is what it was: a phrase wakes, everything else is suppressed.
        phrases = standin.ScriptedAttention(["hello"])
        self.addCleanup(phrases.close)
        self.assertEqual(("SUPPRESS", "e"), phrases.disposition(body("chatter")))

    def test_the_scripted_participant_answers_a_scene_script_and_notes_messages_that_waited(self):
        script = directed.spec("said-it-would-check").script
        participant = standin.ScriptedParticipant(script)
        self.addCleanup(participant.close)
        moment = next(iter(script.moments.values()))
        script.register("the text", moment.event)
        turn = _turn("discord:message:9", "the text")
        envelope = participant.answer({"messages": [{"role": "user", "content": json.dumps({"participant_turn": turn, "context_pages": []})}]})
        self.assertEqual("message", envelope["action"]["kind"])
        self.assertNotIn("unattended", participant.answers[0], "the key appears only where messages waited")
        turn = _turn("discord:message:10", "the text", request_id="req-2")
        turn["wake"]["unattended_event_ids"] = ["discord:message:9"]
        participant.answer({"messages": [{"role": "user", "content": json.dumps({"participant_turn": turn, "context_pages": []})}]})
        self.assertEqual(["discord:message:9"], participant.answers[1]["unattended"])


# -- grading a played scene -------------------------------------------------------------------------------


def _played(scene):
    """What `play_scene` hands to the judge for a scene whose every message reached Nunchi."""

    deliveries = [
        {"scene_event": event["id"], "event_id": f"discord:message:{1000 + index}", "observed": True}
        for index, event in enumerate(scene.events)
    ]
    return {"deliveries": deliveries, "graded": directed.graded_moments(scene, deliveries), "reached": True}


def _leg(
    event_id: str | None,
    move: str | None,
    *,
    attention: str | None = "DEFER",
    delivered: bool = True,
    unattended_on: str | None = None,
    request: str = "r1",
    scene_event: str | None = None,
):
    """A leg as the reference reads back: the turn on the message with the move it made, and attention's call on it."""

    # The actions are the ones the script makes (`directed.scripted_action`) when the scene's event is named.
    said = standin.SCENE_SAY.format(event=scene_event) if scene_event else "something to say"
    action = {
        "speak": {"kind": "message", "text": said, "origin_event_id": event_id},
        "mhm": {"kind": "reaction", "reaction": standin.SCENE_NOD, "target_event_id": event_id},
        "stay_quiet": None,
    }.get(move)
    turns = [] if move is None else [{"request_id": request, "trigger": unattended_on or event_id, "source": "DEFER"}]
    if move is not None and unattended_on:
        turns[0]["unattended"] = [event_id]
    committed = [{"request_id": request, **action, "delivery": "sent", "delivered": delivered}] if action else []
    calls = [] if attention is None else [{"trigger": event_id, "disposition": attention, "evidence": [event_id]}]
    return SimpleNamespace(invocations=turns, committed=committed, attention_calls=calls)


def _visible(moment, move: str) -> str:
    if move in moment.fitting or (move == "stay_quiet" and "wait" in moment.fitting):
        return "fits"
    return "miss" if any(miss["move"] == move for miss in moment.misses) else "unlisted"


class JudgeTest(unittest.TestCase):
    def test_every_fitting_move_fits_every_miss_misses_and_the_rest_are_unlisted_for_every_moment_of_every_scene(self):
        seen = set()
        for scene in load_scenes(directed.SCENE_DIRECTORY):
            for number, moment in enumerate(scene.moments):
                if not moment.event:
                    continue
                for move in ("stay_quiet", "mhm", "speak"):
                    with self.subTest(scene=scene.id, moment=moment.label, move=move):
                        played = _played(scene)
                        event_id = played["graded"][number]["event_id"]
                        directed.judge_scene(_leg(event_id, move), played, scene)
                        item = played["graded"][number]
                        self.assertEqual((move, "agent"), (item["result"], item["by"]))
                        self.assertEqual(_visible(moment, move), item["grade"]["visible"])
                        self.assertEqual("over-wake" if moment.step1 == "suppress" else "ok", item["grade"]["step1"])
                        self.assertEqual(moment.miss_reason(move), item.get("why"))
                        seen.add(item["grade"]["visible"])
        self.assertEqual({"fits", "miss", "unlisted"}, seen, "the scenes between them give every grade")

    def test_a_message_attention_suppressed_is_quiet_by_attention_and_step_1_is_graded_from_it(self):
        for scene in load_scenes(directed.SCENE_DIRECTORY):
            for number, moment in enumerate(scene.moments):
                if not moment.event:
                    continue
                with self.subTest(scene=scene.id, moment=moment.label):
                    played = _played(scene)
                    event_id = played["graded"][number]["event_id"]
                    directed.judge_scene(_leg(event_id, None, attention="SUPPRESS"), played, scene)
                    item = played["graded"][number]
                    self.assertEqual(("stay_quiet", "attention"), (item["result"], item["by"]))
                    self.assertEqual(_visible(moment, "stay_quiet"), item["grade"]["visible"])
                    self.assertEqual("over-suppress" if moment.step1 == "pass" else "ok", item["grade"]["step1"])

    def test_what_cannot_be_graded_reads_unsupported_or_woken_and_fits_nothing(self):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played(scene)
        event_id = played["graded"][0]["event_id"]
        # Attention never judged it, or it never reached Nunchi: unsupported.
        directed.judge_scene(_leg(event_id, None, attention=None), played, scene)
        self.assertEqual(("unsupported", None), (played["graded"][0]["result"], played["graded"][0]["by"]))
        self.assertEqual({"visible": "unsupported", "step1": "unsupported"}, played["graded"][0]["grade"])
        played = _played(scene)
        played["graded"][0]["reached"] = played["reached"] = False
        directed.judge_scene(_leg(event_id, "speak"), played, scene)
        self.assertEqual("unsupported", played["graded"][0]["result"])
        self.assertEqual(checks.NOT_DELIVERED, played["outcome"])
        # It woke the agent, but no turn followed, or the turn's action was not delivered: woken, which fits nothing.
        for leg in (_leg(event_id, None, attention="DEFER"), _leg(event_id, "speak", delivered=False)):
            played = _played(scene)
            directed.judge_scene(leg, played, scene)
            item = played["graded"][0]
            self.assertEqual(("woken", None, "agent-decides"), (item["result"], item["by"], item["grade"]["visible"]))
        self.assertTrue(item["provider_error"])

    def test_a_message_that_waited_while_the_agent_was_busy_is_graded_from_the_turn_that_listed_it(self):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played(scene)
        event_id, later = played["graded"][0]["event_id"], played["graded"][2]["event_id"]
        leg = _leg(event_id, "mhm", unattended_on=later)
        directed.judge_scene(leg, played, scene)
        self.assertEqual("mhm", played["graded"][0]["result"])
        self.assertEqual(1, played["graded_turns"])

    def test_cited_says_which_facts_attentions_evidence_points_at(self):
        scene = directed.spec("mention-in-busy-room").plan.scene
        played = _played(scene)
        event_id = played["graded"][0]["event_id"]
        directed.judge_scene(_leg(event_id, "speak"), played, scene)
        # The fact about the request names an earlier message; the second names the trigger itself.
        self.assertEqual([False, True], played["graded"][0]["cited"])

    def test_the_record_totals_the_turns_posts_and_outcome_the_summary_reads(self):
        scene = directed.spec("said-it-would-check").plan.scene
        played = _played(scene)
        first, second = played["graded"][0]["event_id"], played["graded"][1]["event_id"]
        leg = SimpleNamespace(
            invocations=[
                {"request_id": "r1", "trigger": first, "source": "WAKE"},
                {"request_id": "r2", "trigger": "discord:message:5", "source": "DEFER"},
                {"request_id": "r3", "trigger": second, "source": "WAKE"},
            ],
            committed=[
                {"request_id": "r1", "kind": "message", "text": standin.SCENE_SAY.format(event="q1"), "origin_event_id": first,
                 "delivery": "sent", "delivered": True},
                {"request_id": "r3", "kind": "message", "text": standin.SCENE_SAY.format(event="q2"), "origin_event_id": second,
                 "delivery": "sent", "delivered": True},
            ],
            attention_calls=[{"trigger": first, "disposition": "WAKE"}, {"trigger": second, "disposition": "WAKE"}],
        )
        directed.judge_scene(leg, played, scene)
        self.assertEqual((2, 1, checks.FITS), (played["graded_turns"], played["other_turns"], played["outcome"]))
        self.assertEqual(["WAKE", "WAKE"], played["graded_wake_sources"])
        self.assertEqual(
            [(standin.SCENE_SAY.format(event="q1"), True), (standin.SCENE_SAY.format(event="q2"), True)],
            [(post["text"], post["delivered"]) for post in played["posts"]],
        )
        self.assertEqual([], played["other_actions"])
        # The same record read once more with a miss reads misses.
        leg.committed = []
        played = _played(scene)
        directed.judge_scene(leg, played, scene)
        self.assertEqual(checks.MISSES, played["outcome"])
        self.assertEqual("!", cell([played["graded"][0]])[-1:], "a clear miss is marked as the suite's matrix marks it")

    def test_the_suites_cell_reads_a_judged_moment(self):
        story = directed.spec("story-across-messages").plan.scene
        played = _played_with(story, {0: ("mhm", "DEFER"), 1: ("stay_quiet", "DEFER"), 2: ("stay_quiet", "DEFER")})
        self.assertEqual(["m", "q", "q!"], [cell([item]) for item in played["graded"]])
        report = directed.spec("bot-status-report").plan.scene
        self.assertEqual("Q", cell([_played_with(report, {0: (None, "SUPPRESS")})["graded"][0]]))
        self.assertEqual("S!", cell([_played_with(report, {0: ("speak", "WAKE")})["graded"][0]]))

    def test_agent_move_moved_to_the_score_module_and_the_runner_still_has_it(self):
        self.assertIs(agent_move, behavior_run.agent_move)
        self.assertEqual("speak", agent_move([{"kind": "reply"}, {"kind": "reaction"}]))
        self.assertEqual("mhm", agent_move([{"kind": "reaction"}, {"kind": "silence"}]))
        self.assertEqual("other", agent_move([{"kind": "privileged"}]))
        self.assertEqual("stay_quiet", agent_move([{"kind": "silence"}]))
        self.assertEqual("stay_quiet", agent_move([]))


# -- the hard check ---------------------------------------------------------------------------------------


def _played_with(scene, moves: dict[int, tuple[str | None, str | None]], edit=None):
    """A record judged with one move (and attention's lean) per graded moment: {number: (move, attention)}.

    ``edit(leg, played)``, if given, changes what the leg recorded (or the record of what was posted) before the judge reads it.
    """

    played = _played(scene)
    legs = [
        _leg(
            played["graded"][number]["event_id"], move, attention=attention, request=f"r{number}",
            scene_event=scene.moments[number].event,
        )
        for number, (move, attention) in moves.items()
    ]
    leg = SimpleNamespace(
        invocations=[turn for one in legs for turn in one.invocations],
        committed=[action for one in legs for action in one.committed],
        attention_calls=[call for one in legs for call in one.attention_calls],
    )
    if edit is not None:
        edit(leg, played)
    directed.judge_scene(leg, played, scene)
    return {**played, "name": scene.id, "expect": "directed"}


class OutcomesTest(unittest.TestCase):
    def test_a_script_that_plays_each_moment_as_the_scene_says_holds(self):
        for scene_id in PLAYABLE:
            scene = directed.spec(scene_id).plan.scene
            with self.subTest(scene=scene_id):
                moves = {}
                for number, moment in enumerate(scene.moments):
                    intended = standin.SceneScript.intended(moment)
                    moves[number] = (None, "SUPPRESS") if moment.step1 == "suppress" else (intended, "DEFER")
                held = checks.directed_outcomes([_played_with(scene, moves)])
                self.assertTrue(held.ok, held.detail)
                self.assertEqual("directed-outcomes", held.name)
                self.assertIn("draft expectations", held.detail)

    def test_a_script_that_plays_a_listed_miss_fails_and_names_the_moment(self):
        for scene_id in PLAYABLE:
            scene = directed.spec(scene_id).plan.scene
            for number, moment in enumerate(scene.moments):
                for miss in moment.misses:
                    with self.subTest(scene=scene_id, moment=moment.label, miss=miss["move"]):
                        moves = {number: (None, "SUPPRESS") if miss["move"] == "stay_quiet" and moment.step1 == "suppress" else (miss["move"], "DEFER")}
                        held = checks.directed_outcomes([_played_with(scene, moves)])
                        self.assertFalse(held.ok)
                        self.assertIn(f"{scene_id}, {moment.label}", held.detail)
                        self.assertIn(miss["why"], held.detail)

    def test_a_script_that_stays_off_the_scene_fails_too(self):
        scene = directed.spec("story-across-messages").plan.scene
        # The first moment fits a nod, a silence or a wait: a silence fits but is not what the script does.
        held = checks.directed_outcomes([_played_with(scene, {0: ("stay_quiet", "DEFER"), 1: ("mhm", "DEFER"), 2: ("speak", "WAKE")})])
        self.assertFalse(held.ok)
        self.assertIn("not the scripted mhm", held.detail)
        self.assertIn("mid-story, second message", held.detail)
        # A step 1 that suppressed something it must pass.
        held = checks.directed_outcomes([_played_with(scene, {0: (None, "SUPPRESS"), 1: ("mhm", "DEFER"), 2: ("speak", "WAKE")})])
        self.assertFalse(held.ok)
        self.assertIn("step 1 graded over-suppress", held.detail)
        # A status report that woke the agent: step 1 over-woke.
        report = directed.spec("bot-status-report").plan.scene
        held = checks.directed_outcomes([_played_with(report, {0: ("stay_quiet", "DEFER")})])
        self.assertIn("step 1 graded over-wake", held.detail)

    def test_a_moment_that_never_reached_nunchi_fails_and_a_run_with_none_fails(self):
        scene = directed.spec("bot-status-report").plan.scene
        played = _played_with(scene, {0: (None, "SUPPRESS")})
        played["graded"][0]["reached"] = False
        held = checks.directed_outcomes([played])
        self.assertIn("the message never reached Nunchi", held.detail)
        self.assertFalse(checks.directed_outcomes([]).ok)
        self.assertFalse(checks.directed_outcomes([{"expect": "post"}]).ok)

    def test_the_other_checks_read_a_directed_record(self):
        # discord-addressing: each message a turn was handed reached the agent as sent.
        ok = {"name": "s", "expect": "directed", "deliveries": [
            {"scene_event": "a", "mentioned_actor_ids": ["discord:actor:1"], "reply_to": "5",
             "received": {"mentioned_actor_ids": ["discord:actor:1"], "reply_to_event_id": "discord:message:5"}},
            {"scene_event": "b", "mentioned_actor_ids": ["discord:actor:1"]},
        ]}
        self.assertTrue(checks.discord_addressing([ok], agent="discord:actor:1", writes=[]).ok)
        lost = copy.deepcopy(ok)
        lost["deliveries"][0]["received"]["mentioned_actor_ids"] = []
        self.assertIn("sent pinging discord:actor:1", checks.discord_addressing([lost], agent="discord:actor:1", writes=[]).detail)
        moved = copy.deepcopy(ok)
        moved["deliveries"][0]["received"]["reply_to_event_id"] = None
        self.assertIn("sent as a reply to 5", checks.discord_addressing([moved], agent="discord:actor:1", writes=[]).detail)
        # discord-continuity: a scene plays no reconnect, and says so; any other run without one still fails.
        start = {"gap": "discord:standalone-startup-gap:1"}
        self.assertTrue(checks.discord_continuity(start, [], gaps_fail=False, reconnects_required=False).ok)
        self.assertFalse(checks.discord_continuity(start, [], gaps_fail=False).ok)
        self.assertFalse(checks.discord_continuity({}, [], gaps_fail=False, reconnects_required=False).ok)
        # discord-clients-complete: the calls the script makes are the ones the reference must make.
        scene = directed.spec("story-across-messages").plan.scene
        calls = discord_room.directed_calls([_played_with(scene, {0: ("mhm", "DEFER"), 1: ("mhm", "DEFER"), 2: ("speak", "WAKE")})])
        self.assertEqual(("GET /users/@me", discord_room.POST, discord_room.REACT), calls)
        report = directed.spec("bot-status-report").plan.scene
        self.assertEqual(("GET /users/@me",), discord_room.directed_calls([_played_with(report, {0: (None, "SUPPRESS")})]))

    def test_the_rooms_judge_leaves_a_directed_moment_to_the_scene_judge_but_still_reads_what_each_turn_showed(self):
        leg = SimpleNamespace(
            harness_posts=False,
            discord=SimpleNamespace(column="reference", holds_own_post=lambda event_id: True),
            committed=[],
            room_effects=lambda: [],
        )
        moments = [{"name": "s", "expect": "directed", "deliveries": [{"scene_event": "a", "event_id": "discord:message:1"}]}]
        seen = {"trigger": "discord:message:1", "mentioned_actor_ids": [], "reply_to_event_id": None}
        discord_room.judge_discord_moments(leg, moments, {"discord:message:1": seen})
        self.assertEqual(seen, moments[0]["deliveries"][0]["received"])
        self.assertNotIn("outcome", moments[0])


# -- the room is graded, not the attention receipt or the kind of move ------------------------------------------


class RoomGradeTest(unittest.TestCase):
    """A grade fails whenever the column did the wrong thing in the room (rehearsal PR 4a, repairs after the first review)."""

    def test_a_turn_that_ran_on_a_message_attention_suppressed_is_graded_on_what_it_did(self):
        report = directed.spec("bot-status-report").plan.scene
        # Suppressed and the turn stayed silent: quiet, and now the agent's, since the turn ran.
        played = _played_with(report, {0: ("stay_quiet", "SUPPRESS")})
        item = played["graded"][0]
        self.assertEqual(("stay_quiet", "agent", {"visible": "fits", "step1": "ok"}), (item["result"], item["by"], item["grade"]))
        self.assertTrue(checks.directed_outcomes([played]).ok)
        # Suppressed and the turn spoke anyway: the room saw the agent speak on a status line. It was graded quiet by attention.
        played = _played_with(report, {0: ("speak", "SUPPRESS")})
        item = played["graded"][0]
        self.assertEqual(("speak", "agent"), (item["result"], item["by"]))
        self.assertEqual({"visible": "miss", "step1": "ok"}, item["grade"], "step 1 is attention's judgment, the grade the room's")
        self.assertEqual(checks.MISSES, played["outcome"])
        self.assertIn("the move was speak, graded miss", checks.directed_outcomes([played]).detail)
        self.assertIn("where the script is quiet", checks.directed_outcomes([played]).detail)
        self.assertEqual("S!", cell([item]))
        # A nod on it is the agent's mhm, a clear miss too.
        item = _played_with(report, {0: ("mhm", "SUPPRESS")})["graded"][0]
        self.assertEqual(("mhm", "agent", "miss"), (item["result"], item["by"], item["grade"]["visible"]))
        # A turn whose action was not delivered is woken, which fits nothing, and the run does not hold.
        held = _played_with(report, {0: ("speak", "SUPPRESS")}, edit=lambda leg, played: leg.committed[0].update(delivered=False))
        self.assertEqual(("woken", None, True), (held["graded"][0]["result"], held["graded"][0]["by"], held["graded"][0]["provider_error"]))
        self.assertFalse(checks.directed_outcomes([held]).ok)

    def test_a_turn_that_ran_on_a_message_nothing_judged_is_graded_and_step_1_reads_not_judged(self):
        report = directed.spec("bot-status-report").plan.scene
        played = _played_with(report, {0: ("speak", None)})
        item = played["graded"][0]
        self.assertEqual(("speak", "agent", {"visible": "miss", "step1": "not judged"}), (item["result"], item["by"], item["grade"]))
        self.assertIn("step 1 graded not judged, not ok", checks.directed_outcomes([played]).detail)

    def test_a_message_that_waited_in_a_turn_on_a_later_one_is_still_quiet_when_attention_suppressed_it(self):
        scene = directed.spec("bot-status-report").plan.scene
        played = _played(scene)
        event_id = played["graded"][0]["event_id"]
        # The turn began on another message and only listed this one: it did not run on this message.
        leg = _leg(event_id, "speak", attention="SUPPRESS", unattended_on="discord:message:9999", scene_event="b1")
        directed.judge_scene(leg, played, scene)
        self.assertEqual(("stay_quiet", "attention"), (played["graded"][0]["result"], played["graded"][0]["by"]))


def _chatter(leg, played, *, request="chatter-1", text="chatter reply"):
    """A turn on a message nobody graded that nonetheless made a post."""

    leg.invocations.append({"request_id": request, "trigger": "discord:message:999", "source": "DEFER"})
    leg.committed.append(
        {"request_id": request, "kind": "message", "text": text, "origin_event_id": "discord:message:999", "delivery": "sent", "delivered": True}
    )


STORY = {0: ("mhm", "DEFER"), 1: ("mhm", "DEFER"), 2: ("speak", "WAKE")}


class ExactActionTest(unittest.TestCase):
    """The delivered actions of a graded moment are the one the script makes, about the graded message; nothing else is done."""

    def story(self, edit=None):
        scene = directed.spec("story-across-messages").plan.scene
        return scene, _played_with(scene, STORY, edit=edit)

    def test_the_exact_script_holds_and_lists_no_deviation_and_no_other_action(self):
        _, played = self.story()
        self.assertEqual([[], [], []], [item["off_script"] for item in played["graded"]])
        self.assertEqual([], played["other_actions"])
        self.assertEqual(checks.FITS, played["outcome"])
        self.assertTrue(checks.directed_outcomes([played]).ok)

    def test_a_reaction_on_another_message_is_a_mhm_by_kind_but_fails_and_names_the_target(self):
        _, played = self.story(edit=lambda leg, played: leg.committed[0].update(target_event_id="discord:message:1000"))
        item = played["graded"][0]
        self.assertEqual(("mhm", "fits"), (item["result"], item["grade"]["visible"]), "the kind of move is as scripted")
        self.assertEqual(["its target_event_id is discord:message:1000, not the graded message discord:message:1001"], item["off_script"])
        self.assertEqual(checks.MISSES, played["outcome"])
        held = checks.directed_outcomes([played])
        self.assertFalse(held.ok)
        self.assertIn("mid-story, second message: its target_event_id is discord:message:1000", held.detail)
        self.assertIn("off script", record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "fail", "checks": [], "moments": [played]}))

    def test_a_message_about_another_message_or_in_other_words_or_with_another_reaction_fails(self):
        for change, expected in (
            ({"origin_event_id": "discord:message:1003"}, "its origin_event_id is discord:message:1003, not the graded message discord:message:1004"),
            ({"origin_event_id": None}, "its origin_event_id is None"),
            ({"text": "something else entirely"}, "its text is 'something else entirely', not the scripted"),
            ({"kind": "reply"}, "its kind is 'reply', not the scripted 'message'"),
        ):
            with self.subTest(change=change):
                _, played = self.story(edit=lambda leg, played: leg.committed[2].update(change))
                self.assertIn(expected, " ".join(played["graded"][2]["off_script"]))
                self.assertFalse(checks.directed_outcomes([played]).ok)
        _, played = self.story(edit=lambda leg, played: leg.committed[0].update(reaction="\N{THUMBS UP SIGN}"))
        self.assertIn("its reaction is", " ".join(played["graded"][0]["off_script"]))

    def test_more_than_the_one_scripted_action_or_none_fails(self):
        def two(leg, played):
            leg.committed.append({**leg.committed[2], "text": "and another thing"})

        _, played = self.story(edit=two)
        self.assertEqual(["it delivered 2 action(s), not the one scripted message"], played["graded"][2]["off_script"])
        self.assertFalse(checks.directed_outcomes([played]).ok)
        # The script nods at the fourth message; a silence fits the scene (`wait`) but is not the script.
        scene = directed.spec("story-across-messages").plan.scene
        played = _played_with(scene, {0: ("mhm", "DEFER"), 1: ("stay_quiet", "DEFER"), 2: ("speak", "WAKE")})
        self.assertEqual("fits", played["graded"][1]["grade"]["visible"])
        self.assertEqual(["it delivered 0 action(s), not the one scripted reaction"], played["graded"][1]["off_script"])

    def test_a_message_the_script_acts_on_needs_a_turn_that_began_on_it_not_one_that_only_listed_it_as_unattended(self):
        # The second message gets no turn of its own; the turn on the fourth lists it as unattended, and makes the one nod the
        # fourth is owed. One nod then stands for both moments, and the old grade passed it (target in the turn's triggers).
        def fold(leg, played):
            leg.invocations[:] = [turn for turn in leg.invocations if turn["request_id"] != "r0"]
            leg.committed[:] = [action for action in leg.committed if action["request_id"] != "r0"]
            next(turn for turn in leg.invocations if turn["request_id"] == "r1")["unattended"] = [played["graded"][0]["event_id"]]

        _, played = self.story(edit=fold)
        first, fourth = played["graded"][0], played["graded"][1]
        self.assertEqual(["mhm", "mhm"], [first["result"], fourth["result"]], "the room did see one nod")
        self.assertEqual(
            [f"no turn began on it: it was only folded into the turn on {fourth['event_id']} as an unattended message"], first["off_script"]
        )
        self.assertEqual([], fourth["off_script"], "the turn that began on the fourth message is not at fault")
        self.assertEqual(checks.MISSES, played["outcome"])
        held = checks.directed_outcomes([played])
        self.assertFalse(held.ok)
        self.assertIn("story-across-messages, mid-story, second message: no turn began on it: it was only folded into the turn on", held.detail)
        self.assertNotIn("mid-story, fourth message", held.detail)
        # A moment where the script is quiet, and one attention suppressed, may be folded: nothing is owed there.
        report = directed.spec("bot-status-report").plan.scene
        played = _played(report)
        leg = _leg(played["graded"][0]["event_id"], "stay_quiet", attention="SUPPRESS", unattended_on="discord:message:9999")
        directed.judge_scene(leg, played, report)
        self.assertEqual([], played["graded"][0]["off_script"])

    def test_an_action_where_the_script_is_quiet_fails(self):
        report = directed.spec("bot-status-report").plan.scene
        played = _played_with(report, {0: ("mhm", "DEFER")})
        self.assertEqual(["it made a reaction where the script is quiet"], played["graded"][0]["off_script"])

    def test_a_committed_action_outside_the_graded_turns_fails_and_is_listed(self):
        _, played = self.story(edit=_chatter)
        self.assertEqual(1, played["other_turns"])
        self.assertEqual(1, len(played["other_actions"]))
        self.assertEqual(checks.MISSES, played["outcome"])
        # Every graded moment is as scripted: only the chatter's post is wrong.
        self.assertEqual([[], [], []], [item["off_script"] for item in played["graded"]])
        held = checks.directed_outcomes([played])
        self.assertFalse(held.ok)
        self.assertIn("a turn that was not graded made a message 'chatter reply' about discord:message:999", held.detail)
        # A chatter turn that ends in silence is the scene as scripted.
        scene = directed.spec("story-across-messages").plan.scene
        silent = _played_with(scene, STORY, edit=lambda leg, played: leg.invocations.append({"request_id": "c", "trigger": "discord:message:999", "source": "DEFER"}))
        self.assertEqual((1, [], True), (silent["other_turns"], silent["other_actions"], checks.directed_outcomes([silent]).ok))
        # An undelivered chatter action is still a committed action.
        _, undelivered = self.story(
            edit=lambda leg, played: (_chatter(leg, played), leg.committed[-1].update(delivered=False, delivery="failed"))
        )
        self.assertFalse(checks.directed_outcomes([undelivered]).ok)

    def test_a_record_that_was_not_held_to_the_script_does_not_pass(self):
        _, played = self.story()
        for item in played["graded"]:
            del item["off_script"]
        self.assertIn("its actions were not held to the script", checks.directed_outcomes([played]).detail)
        _, played = self.story()
        del played["other_actions"]
        self.assertIn("the actions outside the graded turns were not listed", checks.directed_outcomes([played]).detail)


class ArrivalTest(unittest.TestCase):
    """Every message the director posts reaches Nunchi, and the pings the scene meant arrive."""

    def test_a_message_nobody_graded_that_never_reached_nunchi_fails_the_check(self):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played_with(scene, STORY)
        self.assertTrue(checks.directed_outcomes([played]).ok)
        played["deliveries"][0].update(observed=False, note="it never reached Nunchi")
        held = checks.directed_outcomes([played])
        self.assertFalse(held.ok)
        self.assertIn("story-across-messages, s1: the message never reached Nunchi (it never reached Nunchi)", held.detail)
        # A graded message that was lost is named once, as the moment.
        played = _played_with(scene, STORY)
        played["graded"][0]["reached"] = False
        played["deliveries"][1]["observed"] = False
        self.assertEqual(1, checks.directed_outcomes([played]).detail.count("never reached Nunchi"))

    def delivery(self, **fields):
        return {"name": "s", "expect": "directed", "deliveries": [{"scene_event": "a", "mentioned_actor_ids": [], "meant_actor_ids": [], **fields}]}

    def test_what_the_scene_meant_to_ping_must_have_been_sent_and_seen(self):
        agent, other = "discord:actor:1", "discord:actor:2"
        seen = {"mentioned_actor_ids": [agent], "reply_to_event_id": None}
        ok = self.delivery(mentioned_actor_ids=[agent], meant_actor_ids=[agent], received=seen, logged=seen)
        self.assertTrue(checks.discord_addressing([ok], agent=agent, writes=[]).ok)
        # The stand-in sent no ping the scene meant, and Nunchi saw none either: nothing is "lost" after sending, the scene is not honored.
        dropped = self.delivery(mentioned_actor_ids=[], meant_actor_ids=[agent], received={"mentioned_actor_ids": []}, logged={"mentioned_actor_ids": []})
        held = checks.discord_addressing([dropped], agent=agent, writes=[])
        self.assertFalse(held.ok)
        self.assertIn(f"s a: the scene pings {agent}, but the message was sent pinging []", held.detail)
        # Sent, but Nunchi's room log lacks it, or the turn's packet does.
        for view in ("logged", "received"):
            lost = self.delivery(mentioned_actor_ids=[agent], meant_actor_ids=[agent], **{"received": seen, "logged": seen, view: {"mentioned_actor_ids": []}})
            held = checks.discord_addressing([lost], agent=agent, writes=[])
            self.assertFalse(held.ok, view)
            self.assertIn(f"sent pinging {agent}, but Nunchi saw mentioned_actor_ids=[]", held.detail)
        # A message no turn was handed is read from Nunchi's room log alone, and a ping it lacks fails too.
        suppressed = self.delivery(mentioned_actor_ids=[agent, other], meant_actor_ids=[agent], logged={"mentioned_actor_ids": [agent]})
        held = checks.discord_addressing([suppressed], agent=agent, writes=[])
        self.assertIn(f"sent pinging {other}, but Nunchi saw", held.detail)
        # A message with nothing meant and nothing sent is as before.
        self.assertTrue(checks.discord_addressing([self.delivery()], agent=agent, writes=[]).ok)

    def test_a_reply_must_arrive_as_a_reply_in_the_room_log_too(self):
        agent = "discord:actor:1"
        item = self.delivery(reply_to="5", received={"mentioned_actor_ids": [], "reply_to_event_id": "discord:message:5"},
                             logged={"mentioned_actor_ids": [], "reply_to_event_id": None})
        held = checks.discord_addressing([item], agent=agent, writes=[])
        self.assertIn("sent as a reply to 5, but Nunchi saw reply_to_event_id=None", held.detail)

    def test_an_agents_reaction_must_be_in_its_memory_at_the_next_turn_about_the_message_it_reacted_to(self):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played_with(scene, STORY)
        ids = [delivery["event_id"] for delivery in played["deliveries"]]
        moves = lambda *kept: [{"kind": "reaction", "about_event_id": about, "reaction": standin.SCENE_NOD} for about in kept]  # noqa: E731
        # Every turn was shown its trigger (a request holds it), and some also show what the agent remembers of its own moves.
        for turn in played["turns"]:
            by_trigger = next(delivery for delivery in played["deliveries"] if delivery["event_id"] == turn["trigger"])
            by_trigger["received"] = {"mentioned_actor_ids": [], "trigger": turn["trigger"]}
        # s3's turn holds the nod on s2, s5's holds the nod on s4: as the reference's memory shows them.
        for delivery, own in ((played["deliveries"][2], moves(ids[1])), (played["deliveries"][4], moves(ids[1], ids[3]))):
            delivery["received"] = {"mentioned_actor_ids": [], "trigger": delivery["event_id"], "own_moves": own}
        self.assertTrue(checks.discord_addressing([played], agent="a", writes=[]).ok)
        played["deliveries"][2]["received"]["own_moves"] = moves(ids[0])
        held = checks.discord_addressing([played], agent="a", writes=[])
        self.assertFalse(held.ok)
        self.assertIn(f"the next turn ({ids[2]}) does not hold the agent's reaction to {ids[1]} in memory.own_moves", held.detail)


class SettledTest(unittest.TestCase):
    """A wait for a quiet room that timed out fails a scripted record, scene or moments alike, and flags a live one."""

    def late(self, *events):
        return [{"scene_event": event, "settled": False} for event in events]

    def test_unsettled_names_the_events_whose_wait_ran_out_and_ignores_a_record_without_the_key(self):
        self.assertEqual(["b"], checks.unsettled([{"scene_event": "a", "settled": True}, {"scene_event": "b", "settled": False}, {"scene_event": "c"}]))
        self.assertEqual([], checks.unsettled([]))

    def test_the_scripted_checks_fail_on_it_in_the_moments_and_in_a_scene(self):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played_with(scene, STORY)
        self.assertTrue(checks.directed_outcomes([played]).ok)
        played["deliveries"][3]["settled"] = False
        held = checks.directed_outcomes([played])
        self.assertFalse(held.ok)
        self.assertIn("story-across-messages: the wait after s4 timed out (the room had not gone quiet", held.detail)
        # The plain lanes' two scripted checks, each with its own moment shape, still pass a settled moment and fail an unsettled one.
        moment = {"name": "direct-question", "expect": "post", "outcome": checks.FITS, "other_turns": 0,
                  "actions": [{"kind": "message", "text": "x"}], "posts": [{"text": "x"}], "deliveries": [{"scene_event": "q", "settled": True}]}
        self.assertTrue(checks.scripted_outcomes([moment], "x").ok)
        self.assertTrue(checks.discord_scripted_outcomes([moment], {"post": {"kind": "message", "text": "x"}}).ok)
        moment["deliveries"] = self.late("q")
        for held in (checks.scripted_outcomes([moment], "x"), checks.discord_scripted_outcomes([moment], {"post": {"kind": "message", "text": "x"}})):
            self.assertFalse(held.ok)
            self.assertIn("direct-question: the wait after q timed out", held.detail)
        # Many at once are listed shortly.
        many = {**moment, "deliveries": self.late(*"abcdefgh")}
        self.assertIn("after a, b, c, d, e, f and 2 more timed out", checks.scripted_outcomes([many], "x").detail)

    def test_play_moment_records_it_on_the_moment_and_a_settled_moment_is_as_before(self):
        spec = discord_room.MOMENTS[0]

        class Leg:
            invocations: list = []

            def __init__(self, settled):
                self.settled = settled

            def deliver(self, raw, at, scene, sequence):
                return {"scene_event": raw["id"], "event_id": f"discord:message:{sequence}", "observed": True}

            def settle(self, timeout):
                return self.settled

        steady = probe.play_moment(Leg(True), spec, settle_seconds=1.0)
        self.assertNotIn("unsettled", steady, "a settled moment's record is as it was")
        self.assertTrue(all(delivery["settled"] for delivery in steady["deliveries"]))
        late = probe.play_moment(Leg(False), spec, settle_seconds=1.0)
        self.assertEqual([delivery["scene_event"] for delivery in late["deliveries"]], late["unsettled"])

    def test_the_summary_flags_it_for_a_live_run_and_says_it_fails_a_scripted_one(self):
        moment = {"name": "direct-question", "expect": "post", "unsettled": ["q"], "posts": []}
        live = record.summary_markdown({"harness": "codex", "mode": "live", "status": "pass", "checks": [], "moments": [moment]})
        self.assertIn("- Not settled (flagged, not failed): direct-question: the wait after q timed out", live)
        scripted = record.summary_markdown({"harness": "codex", "mode": "scripted", "status": "fail", "checks": [], "moments": [moment]})
        self.assertIn("- Not settled (fails the run): direct-question", scripted)
        quiet = record.summary_markdown({"harness": "codex", "mode": "live", "status": "pass", "checks": [], "moments": [{"name": "m", "expect": "post"}]})
        self.assertNotIn("Not settled", quiet)


# -- what the director posts to the stand-in -------------------------------------------------------------------


class _Leg:
    """The part of a leg the director uses: its room, posting through `deliver`, and settling.

    A held turn waits at its gate for the model endpoint's first call, which this stands in for: the call arrives (``Gate.pause`` on a
    thread) as soon as the turn's trigger is posted, and ``log`` keeps the order things happened in.
    """

    def __init__(self, room, spec) -> None:
        self.discord, self.script, self._spec = room, spec.script, spec
        self.settled: list[float] = []
        self.log: list[tuple[str, str]] = []
        self.calls: list[threading.Thread] = []
        for gate in self.script.gates.values():
            gate.release = self._logged(gate, gate.release)

    def _logged(self, gate, release):
        def logged():
            self.log.append(("release", gate.event))
            release()

        return logged

    def deliver(self, raw, at, scene, sequence):
        delivery = self.discord.post(raw, at, scene, self._spec)
        delivery["observed"] = True
        self.log.append(("post", raw["id"]))
        gate = self.script.gates.get(raw["id"])
        if gate is not None:
            call = threading.Thread(target=gate.pause, daemon=True)
            call.start()
            self.calls.append(call)
        return delivery

    def settle(self, timeout):
        self.settled.append(timeout)
        return True


class DirectorTest(_StandIn, unittest.TestCase):
    def play(self, scene, leg_class=_Leg, **options):
        item = directed.plan(scene)
        self.assertIsNone(item.unplayable)
        spec = directed.DirectedSpec(item, directed.script_for(item))
        world, members = discord_room.world_spec("codex", [scene], agent="Vigil")
        fd = self.start(world)
        base = Path(tempfile.mkdtemp(prefix="director-"))
        self.addCleanup(shutil.rmtree, base, True)
        room = _room(base)
        room.fd, room.members = fd, members
        leg = leg_class(room, spec)
        return leg, fd, directed.play_scene(leg, item, 5.0, **options)

    def test_history_is_backdated_the_graded_messages_are_posted_live_and_the_room_records_no_raise(self):
        scene = _directed_scene()
        leg, fd, played = self.play(scene)
        now = time.time()
        by_event = {delivery["scene_event"]: delivery for delivery in played["deliveries"]}
        age = lambda event: now - id_ms(by_event[event]["message_id"]) / 1000  # noqa: E731
        self.assertEqual(["h1", "h2"], played["history"])
        self.assertEqual(["g1", "g2", "g3"], played["live"])
        self.assertEqual(["history", "history", "live", "live", "live"], [delivery["phase"] for delivery in played["deliveries"]])
        # The history keeps its age relative to the first live message, which is the room's now.
        self.assertAlmostEqual(3 * 3600 - 30, age("h1"), delta=15)
        self.assertAlmostEqual(2 * 3600 - 30, age("h2"), delta=15)
        for event in ("g1", "g2", "g3"):
            self.assertLess(age(event), 15, f"{event} is posted live, at the room's time")
        ids = [int(delivery["message_id"]) for delivery in played["deliveries"]]
        self.assertEqual(sorted(ids), ids, "the room's ids only go up")
        self.assertEqual([], [record for record in fd.wire.records if record.get("kind") == "raise"])
        self.assertAlmostEqual(0.0, fd.state()["channels"]["codex"]["lag"], delta=0.5, msg="the room's clock was moved to the wall")
        # One settle after the history, one after each live message.
        self.assertEqual([5.0] * 4, leg.settled)
        self.assertTrue(played["reached"])

    def test_a_ping_a_reply_and_the_graded_moments_arrive_as_the_scene_sent_them(self):
        scene = _directed_scene()
        leg, fd, played = self.play(scene)
        by_event = {delivery["scene_event"]: delivery for delivery in played["deliveries"]}
        castor, vigil = fd.world.member("Castor").id, fd.world.member("Vigil").id
        # Castor is pinged by name, in place of the name in the text; so is the agent.
        self.assertEqual([castor], fd.world.messages[by_event["g1"]["message_id"]]["mentions"])
        self.assertTrue(fd.world.messages[by_event["g1"]["message_id"]]["content"].startswith(f"<@{castor}>, how does"))
        self.assertEqual([f"discord:actor:{castor}"], by_event["g1"]["mentioned_actor_ids"], "what the scene sent, for discord-addressing")
        self.assertEqual([vigil], fd.world.messages[by_event["g3"]["message_id"]]["mentions"])
        # The pings the scene meant are recorded beside the ones sent, worked out from the scene.
        self.assertEqual([f"discord:actor:{castor}"], by_event["g1"]["meant_actor_ids"])
        self.assertEqual([f"discord:actor:{vigil}"], by_event["g3"]["meant_actor_ids"])
        self.assertEqual([], by_event["g2"]["meant_actor_ids"])
        # g2 answers g1, mapped from the scene's id to the message the stand-in made.
        self.assertEqual(by_event["g1"]["message_id"], fd.world.messages[by_event["g2"]["message_id"]]["reply_to"])
        self.assertEqual(by_event["g1"]["message_id"], by_event["g2"]["reply_to"])
        # Only the people and the scripted bot posted: the director never posts as the agent.
        authors = {fd.world.messages[delivery["message_id"]]["author_id"] for delivery in played["deliveries"]}
        self.assertNotIn(vigil, authors)
        # Each graded message's text was told to the script before it was posted, as the room holds it.
        for item, moment in zip(played["graded"], scene.moments):
            text = fd.world.messages[by_event[moment.event]["message_id"]]["content"]
            self.assertIs(moment, leg.script.moment(text))
            self.assertEqual((moment.event, True, "speak" if moment.fitting[0] == "speak" else "stay_quiet"), (item["event"], item["reached"], item["scripted"]))
        self.assertIsNone(leg.script.moment(fd.world.messages[by_event["h1"]["message_id"]]["content"]), "the chatter is not graded")

    def test_a_ping_the_stand_in_drops_is_in_the_record_as_meant_and_not_sent_and_the_addressing_check_fails_it(self):
        scene = _directed_scene()
        with mock.patch.object(discord_room.DiscordRoom, "render", lambda self, raw, scene: str(raw["text"])):
            leg, fd, played = self.play(scene)
        by_event = {delivery["scene_event"]: delivery for delivery in played["deliveries"]}
        castor = fd.world.member("Castor").id
        self.assertEqual(([], [f"discord:actor:{castor}"]), (by_event["g1"]["mentioned_actor_ids"], by_event["g1"]["meant_actor_ids"]))
        held = checks.discord_addressing([{**played, "name": scene.id, "expect": "directed"}], agent="discord:actor:1", writes=[])
        self.assertFalse(held.ok)
        self.assertIn(f"director-test g1: the scene pings discord:actor:{castor}, but the message was sent pinging []", held.detail)
        # As posted, it holds, given what Nunchi's room log holds of each message: the pings as sent, or nothing shows what it saw.
        leg, fd, played = self.play(scene)
        record = {**played, "name": scene.id, "expect": "directed"}
        self.assertIn("nothing shows what Nunchi saw of the pings the scene meant", checks.discord_addressing([record], agent="discord:actor:1", writes=[]).detail)
        for delivery in played["deliveries"]:
            delivery["logged"] = {"mentioned_actor_ids": delivery["mentioned_actor_ids"], "reply_to_event_id": delivery["reply_to"] and f"discord:message:{delivery['reply_to']}"}
        self.assertTrue(checks.discord_addressing([record], agent="discord:actor:1", writes=[]).ok)

    def test_the_moments_delivery_records_carry_no_meant_pings_and_are_as_they_were(self):
        moment = next(spec for spec in discord_room.MOMENTS if spec.name == "direct-question")
        scene = load_scene(moment.scene)
        world, members = discord_room.world_spec("codex", [scene], agent="Vigil")
        fd = self.start(world)
        base = Path(tempfile.mkdtemp(prefix="director-"))
        self.addCleanup(shutil.rmtree, base, True)
        room = _room(base)
        room.fd, room.members = fd, members
        delivery = room.post(scene.events[0], datetime.now(timezone.utc), scene, moment)
        self.assertEqual([f"discord:actor:{fd.world.member('Vigil').id}"], delivery["mentioned_actor_ids"])
        self.assertNotIn("meant_actor_ids", delivery)

    def test_a_wait_that_runs_out_is_recorded_on_the_scene_and_a_settled_scene_has_no_such_key(self):
        scene = _directed_scene()
        leg, fd, played = self.play(scene)
        self.assertNotIn("unsettled", played)
        self.assertTrue(all(delivery["settled"] for delivery in played["deliveries"]))
        item = directed.plan(scene)
        spec = directed.DirectedSpec(item, directed.script_for(item))
        world, members = discord_room.world_spec("codex", [scene], agent="Vigil")
        fd = self.start(world)
        base = Path(tempfile.mkdtemp(prefix="director-"))
        self.addCleanup(shutil.rmtree, base, True)
        room = _room(base)
        room.fd, room.members = fd, members

        class Slow(_Leg):
            def settle(self, timeout):
                super().settle(timeout)
                return len(self.settled) != 4  # the wait after the last message ran out

        late = directed.play_scene(Slow(room, spec), item, 5.0)
        self.assertEqual(["g3"], late["unsettled"])
        self.assertFalse(late["deliveries"][-1]["settled"])
        self.assertFalse(checks.directed_outcomes([{**late, "name": scene.id}]).ok)

    def test_the_gaps_between_live_messages_are_the_scenes_own_scaled_by_pace_and_none_by_default(self):
        scene = _directed_scene()
        with mock.patch.object(directed.time, "sleep") as slept:
            self.play(scene)
        slept.assert_not_called()
        with mock.patch.object(directed.time, "sleep") as slept:
            self.play(scene, pace=0.5)
        # 10 seconds from g1 to g2, 20 from g2 to g3, halved; nothing is waited for before the history.
        self.assertEqual([mock.call(5.0), mock.call(10.0)], slept.call_args_list)

    def test_a_scene_with_no_history_posts_every_message_live_and_moves_no_clock(self):
        scene = parse_scene(
            {**{"id": "short", "title": "t", "source": "s", "review": "draft", "platform": "discord", "participants": ["vigil"],
                "actors": {"alice": {"display_name": "Alice", "kind": "human"}}},
             "events": [{"id": "a", "author": "alice", "at": "-40s", "text": "one"}, {"id": "b", "author": "alice", "at": "0s", "text": "two"}],
             "moments": [_moment("b", ["speak"])]}
        )
        leg, fd, played = self.play(scene)
        self.assertEqual(([], ["a", "b"]), (played["history"], played["live"]))
        self.assertEqual([5.0, 5.0], leg.settled)
        self.assertEqual([], [record for record in fd.wire.records if record.get("kind") == "raise"])

    def test_the_playable_scenes_post_without_a_raise_on_the_stand_in(self):
        for scene_id in PLAYABLE:
            with self.subTest(scene=scene_id):
                scene = directed.spec(scene_id).plan.scene
                leg, fd, played = self.play(scene)
                # Every event but the agent's own is posted, and a line that answers nothing has a cue posted for it.
                agent = {event["id"] for event in scene.events if event["author"] in scene.participants}
                self.assertEqual(len(scene.events) - len(agent) + len(played.get("cues", ())), len(played["deliveries"]))
                self.assertEqual([], [record for record in fd.wire.records if record.get("kind") == "raise"])
                self.assertEqual([moment.event for moment in scene.moments], [item["event"] for item in played["graded"]])
                # The director never posts as the agent.
                authors = {fd.world.messages[delivery["message_id"]]["author_id"] for delivery in played["deliveries"]}
                self.assertNotIn(fd.world.member("Vigil").id, authors)


# -- what the reference leg records for a scene ---------------------------------------------------------------


class ReferenceLegTest(unittest.TestCase):
    def leg(self, directory, *, scene_spec):
        leg = object.__new__(discord_room.ReferenceLeg)
        state = Path(directory) / "state"
        state.mkdir()
        leg.discord = SimpleNamespace(state=state, column="reference", holds_own_post=lambda event_id: True, effects=lambda: [])
        leg.ctx = SimpleNamespace(attention={"model": "m"})
        leg.directed = scene_spec
        leg.invocations, leg.committed, leg.attention_calls = [], [], []
        leg.participant_endpoint = SimpleNamespace(answers=[])
        leg.harness_posts = False
        return leg, state

    def write(self, path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_a_scene_keeps_what_each_committed_action_was_about_and_the_plain_lane_records_as_before(self):
        trigger = "discord:message:1"
        answers = [{"request_id": "r1", "trigger": trigger, "source": "WAKE", "at": "t",
                    "action": {"kind": "message", "origin_event_id": trigger, "text": "hi", "why": "x"}}]
        receipts = [
            {"request_id": "r1", "stage": "observation", "writer": "w", "body": {"trigger_event_id": trigger}},
            {"request_id": "r1", "stage": "attention", "writer": "w", "body": {"effective_disposition": "WAKE", "evidence_event_ids": [trigger]}},
            {"request_id": "r1", "stage": "participant-host", "writer": "w", "body": {"invoked": True}},
            {"request_id": "r1", "stage": "transport", "writer": "w", "body": {"delivery": "sent", "detail": "discord:message:5"}},
        ]
        kept = {}
        for name, scene_spec in (("scene", directed.spec("story-across-messages")), ("plain", None)):
            with tempfile.TemporaryDirectory() as directory:
                leg, state = self.leg(directory, scene_spec=scene_spec)
                leg.participant_endpoint.answers = answers
                self.write(state / "x.receipts.jsonl", receipts)
                leg.read_turns()
                kept[name] = leg.committed[0]
                self.assertEqual(scene_spec is not None, "evidence" in leg.attention_calls[0])
        self.assertEqual(trigger, kept["scene"]["origin_event_id"])
        self.assertNotIn("origin_event_id", kept["plain"], "the plain lanes' records are as they were")
        self.assertNotIn("why", kept["scene"])
        self.assertEqual({**kept["plain"], "origin_event_id": trigger}, kept["scene"])

    def test_a_scene_notes_what_nunchis_room_log_holds_of_each_message_it_took_in_and_a_plain_lane_notes_nothing(self):
        scene = directed.spec("story-across-messages")
        for scene_spec in (scene, None):
            with tempfile.TemporaryDirectory() as directory:
                leg, state = self.leg(directory, scene_spec=scene_spec)
                played = _played(scene.plan.scene)
                played.update(name="story-across-messages", expect="directed")
                first = played["deliveries"][0]["event_id"]
                self.write(
                    state / "x.observations.jsonl",
                    [{"event": {"id": first, "type": "message", "mentioned_actor_ids": ["discord:actor:9"], "reply_to_event_id": "discord:message:4"}}],
                )
                leg.judge([played])
                if scene_spec is None:
                    self.assertTrue(all("logged" not in delivery for delivery in played["deliveries"]))
                    continue
                self.assertEqual({"mentioned_actor_ids": ["discord:actor:9"], "reply_to_event_id": "discord:message:4"}, played["deliveries"][0]["logged"])
                self.assertTrue(all("logged" not in delivery for delivery in played["deliveries"][1:]), "a message the log lacks has nothing to show")
                self.assertIn("graded", played)


# -- the command and the summary ----------------------------------------------------------------------------


class CommandTest(unittest.TestCase):
    def run_main(self, *arguments):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as error:
            code = probe.main([*arguments, "--out", directory])
            self.assertEqual([], list(Path(directory).iterdir()), "a refused command starts and writes nothing")
        return code, error.getvalue()

    def test_a_scene_is_played_in_the_discord_room_scripted_and_by_no_column_but_the_reference_claude_code_and_codex(self):
        # Hermes is parked (AGENTS.md); Claude Code and Codex play scenes since PR 4b (test_rehearsal_directed_harness).
        base = ["--scripted", "--room", "discord", "--scene", "story-across-messages"]
        code, error = self.run_main("--harness", "hermes", *base)
        self.assertEqual(probe.EXIT_USAGE, code)
        self.assertIn("--harness reference or claude-code or codex with --room discord (Hermes is parked)", error)
        # Without --scripted a scene is live (PR 4d): refused off a CI runner (test_rehearsal_live_scene has the whole of it).
        with mock.patch.dict(os.environ):
            os.environ.pop("CI", None)
            code, error = self.run_main("--harness", "reference", "--room", "discord", "--scene", "story-across-messages")
        self.assertEqual(probe.EXIT_USAGE, code)
        self.assertIn("only on a CI runner", error)
        self.assertEqual(probe.EXIT_USAGE, self.run_main("--harness", "reference", "--scripted", "--scene", "story-across-messages")[0])

    def test_a_scene_that_does_not_exist_or_cannot_be_played_is_refused_with_the_reason(self):
        code, error = self.run_main("--harness", "reference", "--scripted", "--room", "discord", "--scene", "quiet-for-hours")
        self.assertEqual(probe.EXIT_USAGE, code)
        self.assertIn("hours of quiet", error)
        self.assertIn("Playable: " + ", ".join(PLAYABLE), error)
        code, error = self.run_main("--harness", "reference", "--scripted", "--room", "discord", "--scene", "nope")
        self.assertEqual(probe.EXIT_USAGE, code)
        self.assertIn("no behavior scene is called 'nope'", error)

    def test_the_options_carry_the_scene_into_the_room_and_without_the_launcher_nothing_starts(self):
        options = probe.Options(harness="reference", out=Path("x"), scripted=True, room="discord", scene="bot-status-report")
        leg_class, specs, _ = probe._room_parts(options)
        self.assertIs(discord_room.ReferenceLeg, leg_class)
        self.assertEqual(["bot-status-report"], [item.name for item in specs])
        self.assertIsInstance(specs[0], directed.DirectedSpec)
        self.assertEqual(discord_room.MOMENTS, probe._room_parts(probe.Options(harness="reference", out=Path("x"), scripted=True, room="discord"))[1])
        with self.assertRaisesRegex(ValueError, "played in the Discord room by reference or claude-code or codex"):
            probe.run_probe(probe.Options(harness="hermes", out=Path("x"), scripted=True, room="discord", scene="bot-status-report"))
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(discord_room.NET_ENV, None)
            options.out = Path(directory)
            with contextlib.redirect_stdout(io.StringIO()):
                code = probe.run_probe(options)
            run = json.loads((Path(directory) / "reference" / "run.json").read_text())
            self.assertFalse((Path(directory) / "reference" / "discord-wire.jsonl").exists())
        self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
        self.assertIn("runs inside the launcher", " ".join(run["errors"]))

    def test_the_reference_takes_the_scenes_script_and_the_world_holds_the_scenes_people_and_bots(self):
        item = directed.spec("said-it-would-check")
        ctx = SimpleNamespace(directed=item, options=SimpleNamespace(discord_python=None), original_env={})
        with mock.patch.object(discord_room, "DiscordRoom"):
            leg = discord_room.ReferenceLeg(ctx)
        self.assertIs(item.script, leg.script)
        self.assertIs(discord_room.SCRIPT, discord_room.ReferenceLeg.script, "without a scene it is the moments' script")
        spec, members = discord_room.world_spec("reference", [item.plan.scene], agent="Vigil")
        self.assertEqual(["alice", "sam"], spec["people"])
        self.assertEqual({"CI": {"harness": False}, "Vigil": {}}, spec["bots"])
        self.assertEqual({"vigil": "Vigil", "alice": "alice", "sam": "sam", "ci": "CI"}, members)

    def test_hermes_and_the_moments_are_as_they_were(self):
        self.assertEqual(
            ["first-message", "bot-status-report", "direct-question", "reply", "reaction", "thread", "thread-question"],
            [spec.name for spec in discord_room.MOMENTS],
        )
        hermes = discord_room.HermesGatewayLeg
        self.assertFalse(hasattr(hermes, "directed"), "Hermes runs no scenes")
        self.assertIsNone(inspect.signature(discord_room.DiscordRoom.start).parameters["scenes"].default)


class SummaryTest(unittest.TestCase):
    def document(self, status="pass"):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played_with(scene, {0: ("mhm", "DEFER"), 1: ("stay_quiet", "DEFER"), 2: ("speak", "WAKE")})
        return {"harness": "reference", "mode": "scripted", "status": status, "checks": [], "moments": [played]}

    def test_the_summary_shows_the_grade_matrix_with_the_columns_grades_and_says_the_expectations_are_drafts(self):
        text = record.summary_markdown(self.document())
        self.assertIn("## Grade matrix (draft expectations)", text)
        self.assertIn("awaiting the maintainer's review", text)
        self.assertIn("| story-across-messages | mid-story, second message | mhm, stay_quiet, wait (pass) | `m` fits/ok |", text)
        # The fourth message fits a silence, but the script nods there: the matrix says it was off script.
        self.assertIn("| story-across-messages | mid-story, fourth message | mhm, stay_quiet, wait (pass) | `q` fits/ok off script |", text)
        self.assertIn("| story-across-messages | the story ends with a question | speak (pass) | `S` fits/ok |", text)
        self.assertIn("**Passed (draft expectations):**", text)
        self.assertNotIn("without a room action", text)

    def test_a_miss_is_marked_in_the_matrix_and_a_run_that_is_not_a_scene_has_no_matrix(self):
        scene = directed.spec("story-across-messages").plan.scene
        played = _played_with(scene, {0: ("speak", "WAKE")})
        text = record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "fail", "checks": [], "moments": [played]})
        self.assertIn("`S!` miss/ok", text)
        plain = record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "pass", "checks": [],
                                         "moments": [{"name": "direct-question", "expect": "post", "posts": [{"delivered": True}]}]})
        self.assertNotIn("Grade matrix", plain)
        self.assertIn("**Passed:**", plain)


class CiTest(unittest.TestCase):
    def test_ci_plays_each_playable_scene_in_the_launcher_with_the_same_scan_and_upload_as_the_room_lane(self):
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = text[text.index("  discord-standin:"):text.index("  hermes-plugin:")]
        for scene in PLAYABLE:
            self.assertIn(scene, job)
        self.assertEqual(2, job.count("--scene"), "each playable scene in the loop, and the story once more with a word first")
        self.assertEqual(1, job.count("--nod-with-a-word-first"))
        self.assertIn("--scene story-across-messages --nod-with-a-word-first", job)
        self.assertIn("discord_net --offline --", job)
        self.assertIn("steps.discord_scenes_lane.outcome == 'failure'", job)
        self.assertIn("rehearsal-directed", job)
        self.assertIn("rehearsal-discord-scenes-", job)


if __name__ == "__main__":
    unittest.main()
