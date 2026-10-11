"""Holds and the agent's own earlier lines (rehearsal PR 4c): the scenes where timing and the agent's own history matter.

PR 4a and 4b play four multi-person scenes through the reference, Claude Code
and Codex. PR 4c plays seven more, which need what a one-person test cannot
show: a message that lands while the agent is composing, a question asked while
it is busy, a promise it made and must keep, a nod it gave and is asked about.
The director never posts as the agent, so the agent's earlier lines are its own
scripted moves on the messages they answer (`standin.Line`), checked to have
landed exactly, and a turn is held at the scripted model endpoint (`standin.Gate`)
while the director posts what lands in it.

These tests need neither a harness nor the launcher. They hold the plan of each
scene, the gate, the script's draft and decision, the endpoints' reading of the
page the core's look before posting shows the agent, the director's order of
posting, how a hold and a line are judged, and the hard checks, each with the
mutation that must fail it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from nunchi.participant_model import _validate_inner_action

from evals.behavior.score import agent_move
from evals.rehearsal import checks, directed, discord_room, record, standin

from tests.v2.test_rehearsal_directed import FIRST_FOUR, NEWS, SEVEN, _moment, _news, _scene
from tests.v2.test_rehearsal_directed_harness import REACT, SEND
from tests.v2.test_rehearsal_discord_room import _tagged, _turn

DURING = ("answered-while-composing", "never-mind-while-composing")
# What each scene's agent says earlier, by its event, and the message it says it on: the plan of PR 4c.
LINES = {
    "asked-while-busy": {"v1": ("z1", "reply")},
    "answered-while-composing": {"v1": ("cue-v1", "message")},
    "never-mind-while-composing": {"v1": ("cue-v1", "message")},
    "build-finishes-after-promise": {"v1": ("z1", "reply")},
    "build-finishes-long-after-promise": {"v1": ("z1", "reply"), "r1": ("a1", "reply"), "r2": ("a2", "reply"), "r3": ("a3", "reply")},
    "did-you-see": {"r1": ("z1", "reaction")},
    "addressee-never-answers": {"v1": ("cue-v1", "message")},
}
# The turns that are held and the messages that land in them.
HOLDS = {
    "asked-while-busy": {"z1": ("s1", "z2")},
    "answered-while-composing": {"q1": ("a1",)},
    "never-mind-while-composing": {"q1": ("n1",)},
}


# -- the plan of each scene ---------------------------------------------------------------------------------


class PlanTest(unittest.TestCase):
    def test_each_of_the_seven_scenes_has_the_lines_and_holds_it_needs(self):
        plans = {item.scene.id: item for item in directed.load_plans()}
        for scene_id in SEVEN:
            item = plans[scene_id]
            with self.subTest(scene=scene_id):
                self.assertEqual(LINES[scene_id], {line.event: (line.trigger, line.kind) for line in item.lines})
                self.assertEqual(HOLDS.get(scene_id, {}), {hold.trigger: hold.events for hold in item.holds})
                self.assertEqual(len([line for line in item.lines if line.cue]), len(item.cues))
                self.assertEqual((), item.reasons)
        for scene_id in FIRST_FOUR:
            self.assertEqual(((), (), (), 0), (plans[scene_id].lines, plans[scene_id].cues, plans[scene_id].holds, plans[scene_id].compressed))

    def test_a_line_says_the_scenes_own_words_or_reaction(self):
        for scene_id in SEVEN:
            item = directed.spec(scene_id)
            events = {event["id"]: event for event in item.plan.scene.events}
            for line in item.plan.lines:
                with self.subTest(scene=scene_id, line=line.event):
                    own = events[line.event]
                    self.assertEqual(own.get("reaction"), line.reaction)
                    self.assertEqual(own.get("text") if own.get("type", "message") == "message" else None, line.text)

    def test_the_cue_of_a_line_that_answers_nothing_is_a_person_pinging_the_agent_and_a_scene_has_at_most_one(self):
        for scene_id in ("answered-while-composing", "never-mind-while-composing", "addressee-never-answers"):
            item = directed.spec(scene_id)
            with self.subTest(scene=scene_id):
                self.assertEqual(
                    [{"id": "cue-v1", "author": "zoe", "mentions": ["vigil"], "text": "Vigil, anything to report?", "before": "v1"}],
                    [dict(cue) for cue in item.plan.cues],
                )
        for scene_id in set(SEVEN) - {"answered-while-composing", "never-mind-while-composing", "addressee-never-answers"}:
            self.assertEqual((), directed.spec(scene_id).plan.cues, "a line that answers a message needs no cue")

    def test_an_unattended_moment_holds_the_turn_the_agent_was_busy_with_and_the_moments_own_message_lands_in_it_too(self):
        # Zoe's thanks arrives while Vigil is still answering her first question, with Sam's. Posted after that turn, Sam's message
        # would be judged on its own (one pending anchor, replaced only by a newer one), and the thanks would not read it as unattended.
        item = directed.spec("asked-while-busy")
        (hold,) = item.plan.holds
        self.assertEqual(("z1", ("s1", "z2"), "unattended", "z2"), (hold.trigger, hold.events, hold.kind, hold.moment))
        (moment,) = item.plan.scene.moments
        self.assertEqual(("s1",), moment.unattended)
        # Not derivable where no line of the agent's is being composed as the messages arrive, nor where the only line is one that
        # answers nothing: it begins where it is said, just after its cue, so the unattended messages cannot arrive while it is made.
        scene = _unattended_scene(line=False)
        self.assertEqual(("unattended",), directed.plan(scene).reasons)
        self.assertIn("the agent says no line while its messages arrive", directed.plan(scene).unplayable)
        cued = _scene(
            [
                {"id": "v1", "author": "vigil", "at": "-60s", "text": "Heads up."},
                {"id": "s1", "author": "sam", "at": "-30s", "mentions": ["vigil"], "text": "Vigil, and this?"},
                {"id": "z2", "author": "zoe", "at": "0s", "text": "Thanks!"},
            ],
            [{**_moment("z2", ["speak"]), "unattended": ["s1"]}],
        )
        self.assertEqual(("unattended",), directed.plan(cued).reasons)

    def test_a_during_turn_moment_holds_its_own_turn_and_may_not_name_an_event_of_the_agents(self):
        for scene_id in DURING:
            (hold,) = directed.spec(scene_id).plan.holds
            self.assertEqual(("q1", "during-turn", "q1"), (hold.trigger, hold.kind, hold.moment))
        scene = _scene(
            [
                {"id": "q1", "author": "zoe", "at": "-30s", "mentions": ["vigil"], "text": "Vigil, a question?"},
                {"id": "v1", "author": "vigil", "at": "-10s", "reply_to": "q1", "text": "An answer."},
            ],
            [{**_moment("q1", ["stay_quiet"]), "during_turn": ["v1"]}],
        )
        self.assertEqual(("agent-event", "during-turn"), directed.plan(scene).reasons)

    def test_a_scene_about_hours_of_quiet_cannot_be_played_but_a_gap_of_four_hours_or_less_can(self):
        def scene(hours):
            return _scene(
                [
                    {"id": "z1", "author": "zoe", "at": f"-{hours}h", "mentions": ["vigil"], "text": "Vigil, check the build?"},
                    {"id": "v1", "author": "vigil", "at": f"-{hours}h", "reply_to": "z1", "text": "Will do."},
                    {"id": "m1", "author": "sam", "at": "0s", "text": "Is it green?"},
                ],
                [_moment("m1", ["speak"])],
            )

        self.assertEqual(("time",), directed.plan(scene(5)).reasons)
        self.assertIn("m1 follows 5 hours of quiet", directed.plan(scene(5)).unplayable)
        self.assertEqual((), directed.plan(scene(4)).reasons)
        # Without a line of the agent's nothing is compressed, so the quiet is kept (backdated) and the scene can be played.
        plain = _scene(
            [{"id": "z1", "author": "zoe", "at": "-6h", "text": "Night all."}, {"id": "m1", "author": "sam", "at": "0s", "text": "Morning."}],
            [_moment("m1", ["speak"])],
        )
        self.assertEqual((), directed.plan(plain).reasons)

    def test_a_scene_with_lines_is_played_from_the_first_message_that_triggers_one_and_its_time_is_compressed(self):
        item = directed.plan(
            _scene(
                [
                    {"id": "h1", "author": "zoe", "at": "-5h", "text": "Morning."},
                    {"id": "h2", "author": "sam", "at": "-4h", "text": "Morning Zoe."},
                    {"id": "z1", "author": "zoe", "at": "-3h", "mentions": ["vigil"], "text": "Vigil, check the build?"},
                    {"id": "v1", "author": "vigil", "at": "-3h", "reply_to": "z1", "text": "Will do."},
                    {"id": "c1", "author": "sam", "at": "0s", "text": "Done."},
                ],
                [_moment("c1", ["speak"])],
            )
        )
        # The two earlier messages are history, backdated as before; nothing from z1 on can be, since the agent's post is stamped at the wall.
        self.assertEqual((["h1", "h2"], ["z1", "v1", "c1"], 3 * 3600), ([e["id"] for e in item.history], [e["id"] for e in item.live], item.compressed))


def _unattended_scene(*, line: bool):
    events = [
        {"id": "z1", "author": "zoe", "at": "-50s", "mentions": ["vigil"], "text": "Vigil, can you check?"},
        {"id": "s1", "author": "sam", "at": "-35s", "mentions": ["vigil"], "text": "Vigil, and this?"},
        *([{"id": "v1", "author": "vigil", "at": "-20s", "reply_to": "z1", "text": "Checked."}] if line else []),
        {"id": "z2", "author": "zoe", "at": "0s", "text": "Thanks!"},
    ]
    return _scene(events, [{**_moment("z2", ["speak"]), "unattended": ["s1"]}])


# -- the gate -----------------------------------------------------------------------------------------------


class GateTest(unittest.TestCase):
    def call(self, gate):
        done = threading.Event()
        thread = threading.Thread(target=lambda: (gate.pause(), done.set()), daemon=True)
        thread.start()
        return done

    def test_the_first_model_call_waits_for_the_director_and_later_calls_pass(self):
        gate = standin.Gate("q1", limit=10)
        first = self.call(gate)
        self.assertTrue(gate.wait_asked(2), "the director learns the call arrived")
        self.assertFalse(first.wait(0.3), "the call is held")
        self.assertIsNone(gate.released_at)
        gate.release()
        self.assertTrue(first.wait(2))
        self.assertEqual("director", gate.released_by)
        self.assertLessEqual(gate.asked_at, gate.released_at)
        later = time.monotonic()
        gate.pause()
        self.assertLess(time.monotonic() - later, 0.5, "only the turn's first call is held")

    def test_a_call_the_director_never_releases_goes_on_after_the_limit_and_the_record_says_so(self):
        gate = standin.Gate("q1", limit=0.2)
        began = time.monotonic()
        gate.pause()
        self.assertGreaterEqual(time.monotonic() - began, 0.2)
        self.assertEqual("timeout", gate.released_by)
        gate.release()
        self.assertEqual("timeout", gate.released_by, "the first to let it go is the one on record")

    def test_a_release_before_the_call_arrives_lets_it_through_at_once(self):
        gate = standin.Gate("q1", limit=10)
        gate.release()
        began = time.monotonic()
        gate.pause()
        self.assertLess(time.monotonic() - began, 0.5)
        self.assertEqual("director", gate.released_by)
        self.assertFalse(standin.Gate("q2", limit=10).wait_asked(0.05), "nobody asked yet")

    def test_it_keeps_the_pages_the_core_showed_the_turn_and_says_which_messages_they_hold(self):
        gate = standin.Gate("q1")
        gate.note_news(f"{standin.NEWS_MARK} 1 new message(s)\n" + json.dumps({"events": [{"id": "discord:message:5"}]}))
        self.assertEqual(["discord:message:5"], gate.shown(["discord:message:4", "discord:message:5"]))
        self.assertEqual({"asked_at": None, "released_at": None, "released_by": None, "pages": 1}, gate.document())


# -- what the script does -----------------------------------------------------------------------------------


class LineScriptTest(unittest.TestCase):
    def test_the_message_that_triggers_a_line_wakes_the_agent_and_it_says_exactly_the_line_nothing_else_does(self):
        for scene_id in SEVEN:
            item = directed.spec(scene_id)
            for gate in item.script.gates.values():
                gate.release()  # a held line is said once the director lets the turn go
            texts = {event["id"]: event.get("text") for event in item.plan.scene.events} | {cue["id"]: cue["text"] for cue in item.plan.cues}
            events = {event["id"]: event for event in item.plan.scene.events}
            for line in item.plan.lines:
                with self.subTest(scene=scene_id, line=line.event):
                    text = f"<@42> {texts[line.trigger]}"
                    item.script.register(text, line.trigger)
                    self.assertIs(line, item.script.line(text))
                    self.assertEqual("mhm" if line.kind == "reaction" else "WAKE", item.script.lean(text))
                    turn = _turn("discord:message:7", text)
                    action = item.script.action(turn, news=_news(item.script, line.trigger))
                    self.assertEqual(action, _validate_inner_action(action))
                    self.assertEqual(line.action("discord:message:7"), action)
                    own = events[line.event]
                    if line.kind == "reaction":
                        self.assertEqual(("reaction", own["reaction"], "discord:message:7"), (action["kind"], action["reaction"], action["target_event_id"]))
                        self.assertEqual("mhm", agent_move([action]))
                    else:
                        self.assertEqual(("reply" if line.kind == "reply" else "message", own["text"]), (action["kind"], action["text"]))
                        self.assertEqual("speak", agent_move([action]))
                    role, arguments = item.script.move(turn, news=_news(item.script, line.trigger))
                    expected = {
                        "reaction": ("react", {"target_event_id": "discord:message:7", "reaction": own.get("reaction")}),
                        "reply": ("send", {"text": own.get("text"), "reply_to_event_id": "discord:message:7"}),
                        "message": ("send", {"text": own.get("text")}),
                    }[line.kind]
                    self.assertEqual(expected, (role, arguments))
            # Any other message is chatter, whatever the scene holds.
            self.assertEqual("DEFER", item.script.lean("something nobody graded"))
            self.assertEqual({"kind": "silence"}, item.script.action(_turn("discord:message:9", "something nobody graded")))

    def test_a_held_graded_moment_composes_the_draft_first_and_decides_once_the_core_has_shown_the_page(self):
        for scene_id in DURING:
            item = directed.spec(scene_id)
            (moment,) = item.plan.scene.moments
            text = f"<@42> {next(e for e in item.plan.scene.events if e['id'] == moment.event)['text']}"
            item.script.register(text, moment.event)
            gate = item.script.gates[moment.event]
            turn = _turn("discord:message:7", text)
            with self.subTest(scene=scene_id):
                held = {}
                thread = threading.Thread(target=lambda: held.update(action=item.script.action(turn)), daemon=True)
                thread.start()
                self.assertTrue(gate.wait_asked(2))
                time.sleep(0.2)
                self.assertNotIn("action", held, "the first call waits for the director")
                gate.release()
                thread.join(2)
                # What the agent had ready: a post that names its moment, which the core's look before posting holds back.
                self.assertEqual({"kind": "message", "origin_event_id": "discord:message:7", "text": standin.SCENE_DRAFT.format(event=moment.event)}, held["action"])
                self.assertEqual("speak", agent_move([held["action"]]))
                self.assertNotEqual(standin.SCENE_SAY.format(event=moment.event), held["action"]["text"])
                # Shown the page, it does what the scene fits: stay quiet, which the scene lists first.
                self.assertEqual({"kind": "silence"}, item.script.action(turn, news=NEWS))
                self.assertEqual(("silence", {}), item.script.move(turn, news=NEWS))
                self.assertEqual([NEWS, NEWS], gate.news, "each page the core showed the turn is kept")

    def test_a_held_line_is_said_both_times_and_a_script_without_holds_never_waits(self):
        item = directed.spec("asked-while-busy")
        text = "<@42> Vigil, can you check why last night's nightly failed?"
        item.script.register(text, "z1")
        item.script.gates["z1"].release()
        turn = _turn("discord:message:7", text)
        first, again = item.script.action(turn), item.script.action(turn, news=NEWS)
        self.assertEqual(first, again)
        self.assertEqual("reply", first["kind"])
        story = directed.spec("story-across-messages")
        self.assertEqual({}, story.script.gates)
        began = time.monotonic()
        story.script.action(_turn("discord:message:1", "anything"))
        self.assertLess(time.monotonic() - began, 0.5)

    def test_attention_leans_as_the_script_says_at_the_messages_that_trigger_a_line(self):
        item = directed.spec("did-you-see")
        item.script.register("Vigil, I think we should drop the per-room secrets file", "z1")
        self.assertEqual("mhm", item.script.lean("Vigil, I think we should drop the per-room secrets file"))
        attention = standin.ScriptedAttention(script=item.script)
        self.addCleanup(attention.close)
        body = {"messages": [{"content": json.dumps({"observation": {"trigger_event_id": "e", "events": [{"id": "e", "text": "Vigil, I think we should drop the per-room secrets file"}]}})}]}
        self.assertEqual(("mhm", "e"), attention.disposition(body))


# -- what the page looks like in each request ---------------------------------------------------------------------


class NewsTest(unittest.TestCase):
    PAGE = NEWS + "\n" + json.dumps({"events": [{"id": "discord:message:5"}]})

    def test_the_page_is_found_in_the_newest_message_of_each_columns_request_and_only_there(self):
        turn = _turn("discord:message:4", "q")
        claude = {"messages": [{"role": "user", "content": [{"type": "text", "text": _tagged(turn)}]},
                               {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": SEND, "input": {}}]},
                               {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": self.PAGE}]}]}
        blocks = {"messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": [{"type": "text", "text": self.PAGE}]}]}]}
        codex = {"input": [{"type": "message", "content": [{"type": "input_text", "text": _tagged(turn)}]},
                           {"type": "function_call_output", "call_id": "c", "output": self.PAGE}]}
        plain = {"messages": [{"role": "user", "content": json.dumps({"participant_turn": turn, "context_pages": [{"note": self.PAGE, "events": []}]})}]}
        for name, body in (("claude", claude), ("claude blocks", blocks), ("codex", codex), ("plain", plain)):
            with self.subTest(column=name):
                self.assertIn("discord:message:5", standin.news_shown(body))
                self.assertIn(standin.NEWS_MARK, standin.news_shown(body))
        # An earlier turn's page is history, and a result that is not the page is not news.
        old = copy.deepcopy(claude)
        old["messages"].append({"role": "user", "content": [{"type": "text", "text": "a later message"}]})
        ok = copy.deepcopy(claude)
        ok["messages"][-1]["content"][0]["content"] = "Posted."
        for body in (old, ok, {"messages": []}, {"input": []}, {}, "text", None):
            self.assertIsNone(standin.news_shown(body))


class CoreWordsTest(unittest.TestCase):
    def test_the_mark_the_endpoints_look_for_is_what_the_core_tells_an_agent_whose_post_was_held_back(self):
        # The endpoints recognize the page by the core's own opening words, the same in a tool's result (`Turn.call`) and in a plain-call
        # turn's page (`nunchi.participant_model`). If the core words it otherwise, a hold would read `unseen` on every column.
        root = Path(__file__).resolve().parents[2] / "src" / "nunchi"
        for name in ("turn.py", "participant_model.py"):
            with self.subTest(file=name):
                self.assertIn(standin.NEWS_MARK + " {new_messages(page)} new message(s)", (root / name).read_text(encoding="utf-8"))


# -- the three scripted endpoints ----------------------------------------------------------------------------


def _held(scene_id="answered-while-composing"):
    """A scene's spec, its held moment's registered text, and the message that turn is about."""

    item = directed.spec(scene_id)
    (moment,) = item.plan.scene.moments
    text = f"<@42> {next(e for e in item.plan.scene.events if e['id'] == moment.event)['text']}"
    item.script.register(text, moment.event)
    return item, moment, text


class EndpointTest(unittest.TestCase):
    def asking(self, call):
        """Make ``call`` on a thread; returns (the thread, what it returned)."""

        got: dict = {}
        thread = threading.Thread(target=lambda: got.update(answer=call()), daemon=True)
        thread.start()
        return thread, got

    def test_the_scripted_claude_endpoint_holds_a_turns_first_call_drafts_then_decides_on_the_page(self):
        item, moment, text = _held()
        gate = item.script.gates[moment.event]
        agent = standin.ScriptedClaudeAgent("unused", SEND, script=item.script, tools={"react": REACT})
        self.addCleanup(agent.close)
        turn = _turn("discord:message:7", text)
        first = {"tools": [{"name": SEND}, {"name": REACT}], "messages": [{"role": "user", "content": [{"type": "text", "text": _tagged(turn)}]}]}
        thread, got = self.asking(lambda: agent.reply(first))
        self.assertTrue(gate.wait_asked(2))
        time.sleep(0.2)
        self.assertNotIn("answer", got, "the model's first answer is held")
        gate.release()
        thread.join(2)
        kind, blocks, stop = got["answer"]
        self.assertEqual(("agent-tool-call", "tool_use"), (kind, stop))
        self.assertEqual({"text": standin.SCENE_DRAFT.format(event=moment.event)}, blocks[0]["input"])
        # The room tool's answer is the page: the agent drops its post and the turn ends without a room tool call.
        second = copy.deepcopy(first)
        second["messages"].append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": NEWS}]})
        kind, blocks, stop = agent.reply(second)
        self.assertEqual(("agent", "end_turn", ["text"]), (kind, stop, [block["type"] for block in blocks]))
        self.assertEqual([NEWS], gate.news)
        # A result that is not the page ends the turn as it always did.
        done = copy.deepcopy(first)
        done["messages"].append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "Posted."}]})
        self.assertEqual(("agent", "end_turn"), agent.reply(done)[::2])
        self.assertEqual([NEWS], gate.news)

    def test_the_scripted_codex_endpoint_holds_a_turns_first_call_drafts_then_decides_on_the_page(self):
        item, moment, text = _held("never-mind-while-composing")
        gate = item.script.gates[moment.event]
        agent = standin.ScriptedCodexAgent("unused", script=item.script)
        self.addCleanup(agent.close)
        message = {"type": "message", "content": [{"type": "input_text", "text": _tagged(_turn("discord:message:7", text))}]}
        replies: list[dict] = []
        requests = {"input": [message]}
        with mock.patch.object(agent.model, "latest", side_effect=lambda: requests), mock.patch.object(agent.model, "reply", replies.append):
            thread, _ = self.asking(agent._next)
            self.assertTrue(gate.wait_asked(2))
            time.sleep(0.2)
            self.assertEqual([], replies, "the model's first answer is held")
            gate.release()
            thread.join(2)
            self.assertEqual(("room_send", {"text": standin.SCENE_DRAFT.format(event=moment.event)}), (replies[0]["tool"], replies[0]["arguments"]))
            requests = {"input": [message, {"type": "function_call_output", "call_id": "c", "output": NEWS}]}
            agent._next()
            self.assertNotIn("tool", replies[1], "shown the page, the agent makes no room tool call")
            self.assertIn("text", replies[1])
            requests = {"input": [message, {"type": "function_call_output", "call_id": "c", "output": "Posted."}]}
            agent._next()
            self.assertEqual({"text": "Posted my answer."}, replies[2])
        self.assertEqual([NEWS], gate.news)

    def test_the_scripted_participant_holds_a_turns_first_call_drafts_then_decides_on_the_page(self):
        item, moment, text = _held()
        gate = item.script.gates[moment.event]
        participant = standin.ScriptedParticipant(item.script)
        self.addCleanup(participant.close)
        turn = _turn("discord:message:7", text)

        def body(pages):
            return {"messages": [{"role": "user", "content": json.dumps({"participant_turn": turn, "context_pages": pages})}]}

        thread, got = self.asking(lambda: participant.answer(body([])))
        self.assertTrue(gate.wait_asked(2))
        time.sleep(0.2)
        self.assertNotIn("answer", got, "the participant model's first answer is held")
        self.assertEqual([], participant.answers)
        gate.release()
        thread.join(2)
        self.assertEqual(("message", standin.SCENE_DRAFT.format(event=moment.event)), (got["answer"]["action"]["kind"], got["answer"]["action"]["text"]))
        page = {"events": [{"id": "discord:message:8", "type": "message", "text": "answered"}], "note": NEWS + " Your pending action was {}. Send it again as it is, change it, or stay silent."}
        self.assertEqual({"kind": "silence"}, participant.answer(body([page]))["action"])
        self.assertEqual(1, len(gate.news))
        self.assertEqual(2, len(participant.answers))


# -- the director ---------------------------------------------------------------------------------------------


class _Fake:
    """A leg with no room: the director posts through it, and a held turn's first model call arrives at its gate as the trigger is posted.

    ``ask`` is False when no call arrives (the model is never asked about the turn); ``early`` names the events whose delivery is
    preceded by a release of the gate, as a director that let the turn go too soon would.
    """

    def __init__(self, item, *, ask=True, early=()):
        self.script, self.ask, self.early = item.script, ask, set(early)
        self.discord = SimpleNamespace(render=lambda raw, scene: str(raw["text"]), column="fake", fd=None)
        self.log: list[tuple[str, str]] = []
        self.calls: list[threading.Thread] = []
        for gate in self.script.gates.values():
            release = gate.release
            gate.release = lambda gate=gate, release=release: (self.log.append(("release", gate.event)), release())[1]
        self.count = 0
        self.invocations, self.committed, self.attention_calls = [], [], []

    def deliver(self, raw, at, scene, sequence):
        if raw["id"] in self.early:
            for gate in self.script.gates.values():
                gate.release()
            time.sleep(0.01)  # the message takes longer than a millisecond to arrive, as it does on the wire
        self.count += 1
        self.log.append(("post", raw["id"]))
        delivery = {"scene_event": raw["id"], "event_id": f"discord:message:{1000 + self.count}", "observed": True}
        gate = self.script.gates.get(raw["id"])
        if gate is not None and self.ask:
            call = threading.Thread(target=gate.pause, daemon=True)
            call.start()
            self.calls.append(call)
        return delivery

    def settle(self, timeout):
        return True


def _kept(action):
    return {key: value for key, value in action.items() if key != "operation"}


def _run(scene_id, *, ask=True, early=(), news=True, edit=None, judge=True):
    """A scene played by the director through a leg with no room and then judged, with the agent's process doing what the script says.

    The lines are said on their triggers, the graded moments are the script's moves (a held one after the page: the page names the held
    messages when ``news``), and the page is noted at the gate as the endpoint would. ``edit(leg, played)`` changes what the leg recorded.
    """

    item = directed.spec(scene_id)
    scene = item.plan.scene
    leg = _Fake(item, ask=ask, early=early)
    with mock.patch.object(directed, "HOLD_ASK_SECONDS", 0.5):
        played = directed.play_scene(leg, item.plan, 5.0)
    native = {delivery["scene_event"]: delivery["event_id"] for delivery in played["deliveries"]}
    for line in item.plan.lines:
        trigger, request = native[line.trigger], f"line-{line.event}"
        leg.invocations.append({"request_id": request, "trigger": trigger, "source": "WAKE"})
        leg.committed.append({"request_id": request, **_kept(line.action(trigger)), "delivery": "sent", "delivered": True})
    for moment in scene.moments:
        event_id, request = native[moment.event], f"graded-{moment.event}"
        turn = {"request_id": request, "trigger": event_id, "source": "WAKE"}
        if moment.unattended:
            turn["unattended"] = [native[event] for event in moment.unattended]
        leg.invocations.append(turn)
        action = directed.scripted_action(moment, event_id)
        if action is not None:
            leg.committed.append({"request_id": request, **action, "delivery": "sent", "delivered": True})
        leg.attention_calls.append({"trigger": event_id, "disposition": "DEFER", "evidence": [event_id]})
    if news:
        for hold in played.get("holds", ()):
            leg.script.gates[hold["trigger"]].note_news(NEWS + " " + " ".join(item["event_id"] for item in hold["held"]))
    if edit is not None:
        edit(leg, played)
    if judge:
        directed.judge_scene(leg, played, scene)
    return item, leg, played


def _drop_line(leg, played):
    leg.invocations[:] = [turn for turn in leg.invocations if turn["request_id"] != "line-v1"]
    leg.committed[:] = [action for action in leg.committed if action["request_id"] != "line-v1"]


def _backed(played):
    """The room tool calls a harness's record would show for the delivered actions (one completed call for each)."""

    calls = []
    for action in [*(a for line in played.get("lines", ()) for a in line["actions"]), *(a for item in played["graded"] for a in item["actions"])]:
        if not action.get("delivered"):
            continue
        if action["kind"] == "reaction":
            calls.append({"tool": "room_react", "arguments": {"target_event_id": action["target_event_id"], "reaction": action["reaction"]}, "completed": True})
        else:
            arguments = {"text": action["text"], **({"reply_to_event_id": action["target_event_id"]} if action["kind"] == "reply" else {})}
            calls.append({"tool": "room_send", "arguments": arguments, "completed": True})
    return calls


class DirectorTest(unittest.TestCase):
    def test_the_agents_lines_are_never_posted_by_the_director_and_every_other_message_is_in_the_scenes_order(self):
        for scene_id in SEVEN:
            item = directed.spec(scene_id)
            leg = _Fake(item)
            with self.subTest(scene=scene_id):
                played = directed.play_scene(leg, item.plan, 5.0)
                agent = {line.event for line in item.plan.lines}
                posted = [delivery["scene_event"] for delivery in played["deliveries"]]
                self.assertFalse(agent & set(posted), "the director never posts as the agent")
                self.assertEqual(len(item.plan.scene.events) - len(agent) + len(item.plan.cues), len(posted))
                # A held message lands while its turn is held, which is ahead of the agent's line the turn was composing.
                held = {event for hold in item.plan.holds for event in hold.events}
                scene_order = [event["id"] for event in item.plan.scene.events if event["id"] not in agent and event["id"] not in held]
                self.assertEqual(scene_order, [event for event in posted if not event.startswith("cue-") and event not in held])
                self.assertEqual([event["id"] for event in item.plan.live], played["live"])
                for cue in item.plan.cues:
                    # The cue stands where the agent's line stands in the scene: before whatever follows it.
                    follows = next(event["id"] for event in item.plan.scene.events[[e["id"] for e in item.plan.scene.events].index(cue["before"]) + 1 :])
                    self.assertLess(posted.index(cue["id"]), posted.index(follows))
                self.assertEqual(item.plan.compressed, played["compressed"])
                self.assertEqual([line.event for line in item.plan.lines], [line["event"] for line in played["lines"]])

    def test_the_cue_comes_just_before_the_agents_line_from_a_person_pinging_the_agent(self):
        item = directed.spec("answered-while-composing")
        leg = _Fake(item)
        played = directed.play_scene(leg, item.plan, 5.0)
        self.assertEqual(["cue-v1", "q1", "a1"], [delivery["scene_event"] for delivery in played["deliveries"]])
        self.assertTrue(played["deliveries"][0]["cue"])
        self.assertEqual([{"id": "cue-v1", "author": "zoe", "mentions": ["vigil"], "text": "Vigil, anything to report?", "before": "v1"}], played["cues"])
        # The script knows the cue's text as the message that triggers the line, and q1 as the moment.
        self.assertEqual("v1", item.script.line("Vigil, anything to report?").event)
        self.assertEqual("q1", item.script.moment("@here does anyone know why last night's deploy failed?").event)

    def test_the_held_messages_land_after_the_model_was_asked_and_before_the_release(self):
        for scene_id, (trigger, events) in {"answered-while-composing": ("q1", ("a1",)), "never-mind-while-composing": ("q1", ("n1",)),
                                           "asked-while-busy": ("z1", ("s1", "z2"))}.items():
            item = directed.spec(scene_id)
            leg = _Fake(item)
            with self.subTest(scene=scene_id):
                played = directed.play_scene(leg, item.plan, 5.0)
                posts = [event for kind, event in leg.log if kind == "post"]
                at = posts.index(trigger)
                self.assertEqual(list(events), posts[at + 1 : at + 1 + len(events)], "the held messages follow their trigger directly")
                # The release comes after every held message, and nothing is posted between the last of them and the release.
                release = leg.log.index(("release", trigger))
                self.assertEqual(("post", events[-1]), leg.log[release - 1])
                self.assertEqual(1, [entry for entry in leg.log if entry[0] == "release"].count(("release", trigger)))
                (hold,) = played["holds"]
                gate = item.script.gates[trigger]
                self.assertTrue(hold["asked"])
                self.assertEqual("director", gate.released_by)
                for held in hold["held"]:
                    self.assertTrue(held["observed"])
                    self.assertLessEqual(gate.asked_at, held["delivered_at"], "the model was asked before the message landed")
                    self.assertLessEqual(held["delivered_at"], gate.released_at, "the message had reached Nunchi before the release")
                by_event = {delivery["scene_event"]: delivery for delivery in played["deliveries"]}
                self.assertEqual({trigger, *events}, {event for event, delivery in by_event.items() if event == trigger or delivery.get("held_for") == trigger})
                self.assertEqual([True], list({delivery["settled"] for delivery in played["deliveries"] if delivery["scene_event"] in (trigger, *events)}))

    def test_a_long_scene_posts_every_message_but_the_agents_four_lines_in_order(self):
        item = directed.spec("build-finishes-long-after-promise")
        leg = _Fake(item)
        played = directed.play_scene(leg, item.plan, 5.0)
        ids = [delivery["scene_event"] for delivery in played["deliveries"]]
        self.assertEqual(25, len(ids))
        self.assertEqual(["z1", "a1", "a2", "a3", "t1"], ids[:5])
        self.assertEqual("c1", ids[-1])
        self.assertNotIn("v1", ids)
        self.assertEqual(3 * 3600, played["compressed"])

    def test_a_scene_without_a_line_or_hold_records_neither(self):
        item = directed.spec("story-across-messages")
        played = directed.play_scene(_Fake(item), item.plan, 5.0)
        for key in ("lines", "cues", "holds", "compressed"):
            self.assertNotIn(key, played)

    def test_a_hold_nobody_asks_about_is_recorded_never_asked_and_the_scene_goes_on(self):
        item, leg, played = _run("answered-while-composing", ask=False)
        (hold,) = played["holds"]
        self.assertFalse(hold["asked"])
        self.assertEqual(("never-asked", ["a1"]), (hold["outcome"], [held["event"] for held in hold["held"]]), "the held message is posted anyway")
        self.assertIn("never asked", hold["detail"])
        self.assertEqual(checks.MISSES, played["outcome"])
        failed = checks.directed_outcomes([played])
        self.assertFalse(failed.ok)
        self.assertIn("hold never-asked", failed.detail)


# -- judging a hold -------------------------------------------------------------------------------------------


class TimeoutTest(unittest.TestCase):
    def test_the_hold_is_shorter_than_the_shortest_wait_for_a_model_and_the_reference_is_given_that_wait(self):
        import inspect

        # The reference's host waits 30 seconds for its participant model; Claude Code and Codex wait for minutes.
        self.assertEqual(30, discord_room.PARTICIPANT_TIMEOUT_SECONDS)
        self.assertLess(standin.HOLD_SECONDS, discord_room.PARTICIPANT_TIMEOUT_SECONDS)
        self.assertEqual(standin.HOLD_SECONDS, standin.Gate("q1").limit, "a gate holds for the whole time unless it is told otherwise")
        self.assertIn('"timeout_seconds": PARTICIPANT_TIMEOUT_SECONDS', inspect.getsource(discord_room.ReferenceLeg.prepare))
        # The whole hold fits in it: the director waits for the call, then for each held message (`REACH_SECONDS`) before the release.
        self.assertLess(discord_room.REACH_SECONDS * 2, standin.HOLD_SECONDS, "two held messages (the most a scene lands) reach in time")


class SettledTest(unittest.TestCase):
    def play(self, scene_id, fail_at):
        class Slow(_Fake):
            waits = 0

            def settle(self, timeout):
                self.waits += 1
                return self.waits != fail_at

        item = directed.spec(scene_id)
        with mock.patch.object(directed, "HOLD_ASK_SECONDS", 0.5):
            return directed.play_scene(Slow(item), item.plan, 5.0)

    def test_a_wait_that_ran_out_after_the_cue_is_recorded_and_fails_the_run(self):
        played = self.play("answered-while-composing", 1)
        self.assertEqual(["cue-v1"], played["unsettled"])
        self.assertFalse(played["deliveries"][0]["settled"])
        failed = checks.directed_outcomes([played])
        self.assertFalse(failed.ok)
        self.assertIn("answered-while-composing: the wait after cue-v1 timed out", failed.detail)
        self.assertNotIn("unsettled", self.play("answered-while-composing", 0))

    def test_a_wait_that_ran_out_after_a_hold_is_recorded_on_the_trigger_and_every_held_message(self):
        played = self.play("asked-while-busy", 1)
        self.assertEqual(["z1", "s1", "z2"], played["unsettled"])
        self.assertIn("the wait after z1, s1, z2 timed out", checks.directed_outcomes([played]).detail)
        played = self.play("answered-while-composing", 2)
        self.assertEqual(["q1", "a1"], played["unsettled"])


class HoldOutcomeTest(unittest.TestCase):
    def hold(self, **changes):
        base = {
            "trigger": "q1",
            "asked": True,
            "gate": {"asked_at": "2026-10-11T10:00:00.100Z", "released_at": "2026-10-11T10:00:01.000Z", "released_by": "director"},
            "held": [{"event": "a1", "event_id": "discord:message:5", "observed": True, "delivered_at": "2026-10-11T10:00:00.500Z"}],
            "shown": ["discord:message:5"],
        }
        return {**base, **changes}

    def test_a_hold_is_held_when_the_message_reached_nunchi_before_the_release_and_the_core_showed_the_turn_it(self):
        outcome, detail = directed.hold_outcome(self.hold())
        self.assertEqual("held", outcome)
        self.assertIn("a1 reached Nunchi while the turn on q1 was held", detail)

    def test_a_turn_that_went_on_before_the_message_reached_nunchi_raced(self):
        # Released before it arrived: the director's fault, whatever the turn then did.
        early = self.hold(held=[{"event": "a1", "event_id": "discord:message:5", "observed": True, "delivered_at": "2026-10-11T10:00:01.500Z"}])
        self.assertEqual("raced", directed.hold_outcome(early)[0])
        self.assertIn("released before a1 reached Nunchi", directed.hold_outcome(early)[1])
        # Not taken in by Nunchi at all.
        lost = self.hold(held=[{"event": "a1", "event_id": "discord:message:5", "observed": False, "delivered_at": "2026-10-11T10:00:00.500Z"}])
        self.assertEqual("raced", directed.hold_outcome(lost)[0])
        # The model's wait ran out: the turn went on without the director.
        late = self.hold(gate={"asked_at": "2026-10-11T10:00:00.100Z", "released_at": "2026-10-11T10:00:25.100Z", "released_by": "timeout"})
        self.assertEqual("raced", directed.hold_outcome(late)[0])
        self.assertIn("ran out", directed.hold_outcome(late)[1])

    def test_a_turn_still_held_when_the_scene_ended_was_never_released_and_raced(self):
        outcome, detail = directed.hold_outcome(self.hold(gate={"asked_at": "2026-10-11T10:00:00.100Z", "released_at": None, "released_by": None}))
        self.assertEqual("raced", outcome)
        self.assertIn("still held when the scene ended", detail)

    def test_a_message_that_reached_nunchi_in_time_but_was_not_shown_to_the_turn_is_unseen_the_columns_miss(self):
        outcome, detail = directed.hold_outcome(self.hold(shown=[]))
        self.assertEqual("unseen", outcome)
        self.assertIn("did not show the turn a page that holds it", detail)

    def test_a_hold_is_held_only_when_the_page_showed_every_held_message(self):
        # asked-while-busy lands two messages in the turn: a page that holds one of them leaves the other unseen.
        two = [
            {"event": "s1", "event_id": "discord:message:5", "observed": True, "delivered_at": "2026-10-11T10:00:00.400Z"},
            {"event": "z2", "event_id": "discord:message:6", "observed": True, "delivered_at": "2026-10-11T10:00:00.500Z"},
        ]
        self.assertEqual("held", directed.hold_outcome(self.hold(held=two, shown=["discord:message:5", "discord:message:6"]))[0])
        for shown, missing in ((["discord:message:5"], "z2"), (["discord:message:6"], "s1")):
            outcome, detail = directed.hold_outcome(self.hold(held=two, shown=shown))
            self.assertEqual("unseen", outcome)
            self.assertTrue(detail.startswith(f"{missing} reached Nunchi"), detail)

    def test_a_model_never_asked_about_the_turn_never_held_anything(self):
        for changes in ({"asked": False}, {"gate": {}}):
            self.assertEqual("never-asked", directed.hold_outcome(self.hold(**changes))[0])


class JudgeHoldTest(unittest.TestCase):
    def test_the_seven_scenes_played_as_scripted_pass_every_check_and_each_hold_and_line_is_judged(self):
        for scene_id in SEVEN:
            with self.subTest(scene=scene_id):
                item, leg, played = _run(scene_id)
                self.assertEqual(checks.FITS, played["outcome"])
                self.assertEqual({"held"} if item.plan.holds else set(), {hold["outcome"] for hold in played.get("holds", ())})
                self.assertEqual([[]] * len(item.plan.lines), [line["problems"] for line in played["lines"]])
                self.assertEqual([], played["other_actions"])
                self.assertEqual(0, played["other_turns"], "the turns that play the lines are not other turns")
                held = checks.directed_outcomes([played])
                self.assertTrue(held.ok, held.detail)
                self.assertIn(f"{len(item.plan.lines)} earlier line(s) of the agent's landed as the scene has them", held.detail)
                if item.plan.holds:
                    self.assertIn(f"{len(item.plan.holds)} hold(s) held", held.detail)
                # Through a harness: each action that reached the room has a completed room tool call of its own.
                backed = checks.directed_outcomes([played], room_tool_calls=_backed(played))
                self.assertTrue(backed.ok, backed.detail)

    def test_a_hold_is_attached_to_the_moment_it_is_for_and_a_scene_without_holds_attaches_nothing(self):
        _, _, played = _run("asked-while-busy")
        (item,) = played["graded"]
        self.assertEqual(("held", "z2"), (item["hold"], item["event"]))
        _, _, played = _run("did-you-see")
        self.assertNotIn("hold", played["graded"][0])

    def test_the_agent_answering_after_it_has_been_shown_the_page_is_a_listed_miss_and_fails(self):
        # The mutation: the agent posts the answer it had composed even though the room has moved on.
        for scene_id in DURING:
            item = directed.spec(scene_id)
            (moment,) = item.plan.scene.moments

            def speaks(leg, played):
                event_id = next(d["event_id"] for d in played["deliveries"] if d["scene_event"] == moment.event)
                leg.committed.append({"request_id": f"graded-{moment.event}", "kind": "message", "origin_event_id": event_id,
                                      "text": standin.SCENE_SAY.format(event=moment.event), "delivery": "sent", "delivered": True})

            with self.subTest(scene=scene_id):
                _, _, played = _run(scene_id, edit=speaks)
                (graded,) = played["graded"]
                self.assertEqual(("speak", "miss"), (graded["result"], graded["grade"]["visible"]))
                self.assertEqual(checks.MISSES, played["outcome"])
                failed = checks.directed_outcomes([played])
                self.assertFalse(failed.ok)
                self.assertIn(f"{scene_id}, {moment.label}: the move was speak, graded miss", failed.detail)
                self.assertIn(moment.miss_reason("speak"), failed.detail)
                self.assertIn("where the script is quiet", failed.detail)
                self.assertIn("`S!` miss/ok", record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "fail", "checks": [], "moments": [played]}))

    def test_the_draft_that_reached_the_room_is_a_miss_the_column_made_and_the_hold_says_unseen(self):
        # The core did not hold the post back: the first attempt was delivered, and the turn was never shown the page.
        def posted(leg, played):
            event_id = next(d["event_id"] for d in played["deliveries"] if d["scene_event"] == "q1")
            leg.committed.append({"request_id": "graded-q1", "kind": "message", "origin_event_id": event_id,
                                  "text": standin.SCENE_DRAFT.format(event="q1"), "delivery": "sent", "delivered": True})

        _, _, played = _run("answered-while-composing", news=False, edit=posted)
        self.assertEqual("unseen", played["holds"][0]["outcome"])
        self.assertEqual(("speak", "unseen"), (played["graded"][0]["result"], played["graded"][0]["hold"]))
        failed = checks.directed_outcomes([played])
        self.assertFalse(failed.ok)
        self.assertIn("the move was speak, graded miss", failed.detail, "a miss the column made, graded as one")
        self.assertIn("hold unseen", failed.detail)
        self.assertEqual(checks.MISSES, played["outcome"])

    def test_a_hold_that_raced_is_reported_as_raced_and_not_as_a_miss_and_fails_a_scripted_run(self):
        # The director let the turn go before the held message had reached Nunchi: the agent's first attempt posted.
        def posted(leg, played):
            event_id = next(d["event_id"] for d in played["deliveries"] if d["scene_event"] == "q1")
            leg.committed.append({"request_id": "graded-q1", "kind": "message", "origin_event_id": event_id,
                                  "text": standin.SCENE_DRAFT.format(event="q1"), "delivery": "sent", "delivered": True})

        _, _, played = _run("answered-while-composing", early=("a1",), news=False, edit=posted)
        (hold,) = played["holds"]
        self.assertEqual("raced", hold["outcome"])
        self.assertIn("released before a1 reached Nunchi", hold["detail"])
        self.assertEqual(checks.RACED, played["outcome"])
        failed = checks.directed_outcomes([played])
        self.assertFalse(failed.ok)
        self.assertIn("answered-while-composing, the turn on q1: hold raced", failed.detail)
        self.assertNotIn("graded miss", failed.detail, "the moment was not played as scripted, which is not a miss")
        self.assertNotIn("where the script is quiet", failed.detail)
        self.assertIn("hold raced", record.summary_markdown({"harness": "codex", "mode": "scripted", "status": "fail", "checks": [], "moments": [played]}))

    def test_a_director_that_releases_the_turn_before_the_held_message_has_reached_nunchi_fails_the_run(self):
        for scene_id, early in (("answered-while-composing", "a1"), ("never-mind-while-composing", "n1"), ("asked-while-busy", "s1")):
            with self.subTest(scene=scene_id):
                _, _, played = _run(scene_id, early=(early,))
                (hold,) = played["holds"]
                self.assertEqual("raced", hold["outcome"])
                self.assertFalse(checks.directed_outcomes([played]).ok)
        # Released on time, the same scene holds.
        _, _, played = _run("answered-while-composing")
        self.assertEqual("held", played["holds"][0]["outcome"])

    def test_an_unattended_message_the_graded_turn_did_not_read_with_it_is_unmerged_and_fails(self):
        # Posted after the turn that was busy, Sam's message gets a turn of its own, and the thanks does not read it as unattended:
        # the scene's moment is not played. The hold is not enough to say it was; the graded turn must list the message.
        def apart(leg, played):
            for turn in leg.invocations:
                turn.pop("unattended", None)

        _, _, played = _run("asked-while-busy", edit=apart)
        (hold,) = played["holds"]
        self.assertEqual(("unmerged", "unmerged"), (hold["outcome"], played["graded"][0]["hold"]))
        self.assertIn("s1 arrived while the agent was busy, but the turn on z2 did not list it as unattended", hold["detail"])
        self.assertEqual(checks.MISSES, played["outcome"])
        failed = checks.directed_outcomes([played])
        self.assertFalse(failed.ok)
        self.assertIn("asked-while-busy, the turn on z1: hold unmerged", failed.detail)
        # Listed, it is merged; a hold of the other kind has no such premise.
        _, _, played = _run("asked-while-busy")
        self.assertEqual("held", played["holds"][0]["outcome"])
        self.assertEqual("held", _run("answered-while-composing")[2]["holds"][0]["outcome"])

    def test_an_unattended_message_that_also_started_a_turn_of_its_own_was_read_twice_and_fails(self):
        # The reviewer's mutation: the message is listed as unattended by the thanks' turn, and a silent turn ran on it too.
        def twice(leg, played):
            event_id = next(d["event_id"] for d in played["deliveries"] if d["scene_event"] == "s1")
            leg.invocations.append({"request_id": "s1-alone", "trigger": event_id, "source": "DEFER"})

        _, _, played = _run("asked-while-busy", edit=twice)
        (hold,) = played["holds"]
        self.assertEqual(("unmerged", "unmerged"), (hold["outcome"], played["graded"][0]["hold"]))
        self.assertEqual("s1 was read with z2 as unattended and also started a turn of its own: the moment was not read as the scene has it", hold["detail"])
        self.assertEqual(checks.MISSES, played["outcome"])
        failed = checks.directed_outcomes([played])
        self.assertFalse(failed.ok)
        self.assertIn("asked-while-busy, the turn on z1: hold unmerged: s1 was read with z2 as unattended and also started a turn of its own", failed.detail)
        # A turn on some other message is chatter, not a second reading.
        def chatter(leg, played):
            leg.invocations.append({"request_id": "other", "trigger": "discord:message:999", "source": "DEFER"})

        self.assertEqual("held", _run("asked-while-busy", edit=chatter)[2]["holds"][0]["outcome"])

    def test_a_model_wait_that_ran_out_is_a_race_too(self):
        def timed_out(leg, played):
            gate = leg.script.gates["q1"]
            gate.released_by = "timeout"

        _, _, played = _run("answered-while-composing", edit=timed_out)
        self.assertEqual("raced", played["holds"][0]["outcome"])
        self.assertFalse(checks.directed_outcomes([played]).ok)


class JudgeLineTest(unittest.TestCase):
    def drop(self, request):
        def edit(leg, played):
            leg.invocations[:] = [turn for turn in leg.invocations if turn["request_id"] != request]
            leg.committed[:] = [action for action in leg.committed if action["request_id"] != request]

        return edit

    def change(self, request, **changes):
        def edit(leg, played):
            next(action for action in leg.committed if action["request_id"] == request).update(changes)

        return edit

    def test_a_line_missing_fails_the_run_and_names_it_in_every_scene(self):
        for scene_id in SEVEN:
            item = directed.spec(scene_id)
            for line in item.plan.lines:
                with self.subTest(scene=scene_id, line=line.event):
                    _, _, played = _run(scene_id, edit=self.drop(f"line-{line.event}"))
                    failed = checks.directed_outcomes([played])
                    self.assertFalse(failed.ok)
                    self.assertIn(f"{scene_id}, {line.event}: the agent's earlier line did not land as the scene has it", failed.detail)
                    self.assertIn(f"no turn began on {line.trigger}", failed.detail)
                    self.assertEqual(checks.MISSES, played["outcome"])

    def test_a_line_in_other_words_of_another_kind_or_about_another_message_fails_and_says_how(self):
        for request, change, expect in (
            ("line-v1", {"text": "Something else entirely."}, "its text is 'Something else entirely.', not the scene's"),
            ("line-v1", {"kind": "message"}, "its kind is 'message', not the scene's 'reply'"),
            ("line-v1", {"target_event_id": "discord:message:9"}, "its target_event_id is discord:message:9, not the message that triggers it"),
            ("line-v1", {"delivered": False, "delivery": "failed"}, "it delivered 0 action(s), not the one scripted reply"),
        ):
            with self.subTest(change=change):
                _, _, played = _run("build-finishes-after-promise", edit=self.change(request, **change))
                self.assertIn(expect, " ".join(played["lines"][0]["problems"]))
                self.assertFalse(checks.directed_outcomes([played]).ok)
        _, _, played = _run("did-you-see", edit=self.change("line-r1", reaction="\N{THUMBS UP SIGN}"))
        self.assertIn("its reaction is", " ".join(played["lines"][0]["problems"]))
        _, _, played = _run("did-you-see", edit=self.change("line-r1", target_event_id="discord:message:9"))
        self.assertIn("its target_event_id is discord:message:9", " ".join(played["lines"][0]["problems"]))
        _, _, played = _run("answered-while-composing", edit=self.change("line-v1", origin_event_id="discord:message:9"))
        self.assertIn("its origin_event_id is discord:message:9", " ".join(played["lines"][0]["problems"]))

    def test_a_line_said_twice_or_posted_where_the_scene_has_a_reply_fails(self):
        def twice(leg, played):
            leg.committed.append({**next(action for action in leg.committed if action["request_id"] == "line-v1"), "text": "and again"})

        _, _, played = _run("build-finishes-after-promise", edit=twice)
        self.assertEqual(["it delivered 2 action(s), not the one scripted reply"], played["lines"][0]["problems"])
        self.assertFalse(checks.directed_outcomes([played]).ok)

    def test_the_turns_that_play_the_lines_are_not_other_turns_but_any_other_action_still_is(self):
        def chatter(leg, played):
            leg.invocations.append({"request_id": "chatter", "trigger": "discord:message:999", "source": "DEFER"})
            leg.committed.append({"request_id": "chatter", "kind": "message", "text": "uninvited", "origin_event_id": "discord:message:999",
                                  "delivery": "sent", "delivered": True})

        _, _, played = _run("build-finishes-after-promise", edit=chatter)
        self.assertEqual(1, played["other_turns"])
        self.assertEqual(["uninvited"], [action["text"] for action in played["other_actions"]])
        failed = checks.directed_outcomes([played])
        self.assertFalse(failed.ok)
        self.assertIn("a turn that was not graded made a message 'uninvited'", failed.detail)
        self.assertNotIn("Sure, I'll tell you", failed.detail, "the line is the scene's setup, not an action outside it")

    def test_a_line_that_was_not_checked_does_not_pass(self):
        _, _, played = _run("did-you-see")
        del played["lines"][0]["problems"]
        self.assertIn("the agent's earlier line was not checked", checks.directed_outcomes([played]).detail)

    def test_each_line_through_a_harness_needs_a_completed_room_tool_call_of_its_own(self):
        for scene_id in ("build-finishes-after-promise", "did-you-see", "answered-while-composing"):
            _, _, played = _run(scene_id)
            calls = _backed(played)  # the first call is the line's
            other = "room_send" if calls[0]["tool"] == "room_react" else "room_react"
            for broken in ({"completed": False}, {"tool": other}, {"arguments": {"text": "x", "target_event_id": "e", "reaction": "x"}}):
                with self.subTest(scene=scene_id, broken=broken):
                    changed = [dict(call) for call in calls]
                    changed[0].update(broken)
                    failed = checks.directed_outcomes([played], room_tool_calls=changed)
                    self.assertFalse(failed.ok)
                    self.assertIn("reached the room, but the harness showed no completed room tool call for it", failed.detail)
            self.assertFalse(checks.directed_outcomes([played], room_tool_calls=[]).ok)

    def test_a_reply_needs_a_call_that_names_the_message_it_answers_and_a_post_needs_one_that_names_none(self):
        reply = {"kind": "reply", "text": "hi", "target_event_id": "discord:message:3"}
        post = {"kind": "message", "text": "hi"}
        call = lambda **arguments: [{"tool": "room_send", "arguments": {"text": "hi", **arguments}, "completed": True}]  # noqa: E731
        self.assertIsNotNone(checks.room_call_for(reply, call(reply_to_event_id="discord:message:3")))
        self.assertIsNone(checks.room_call_for(reply, call()), "a reply that the tool call did not make as one")
        self.assertIsNone(checks.room_call_for(reply, call(reply_to_event_id="discord:message:4")))
        self.assertIsNotNone(checks.room_call_for(post, call()))
        self.assertIsNone(checks.room_call_for(post, call(reply_to_event_id="discord:message:3")))


# -- the agent's own history, as the next turn's memory shows it ---------------------------------------------------


class MemoryTest(unittest.TestCase):
    def remembered(self, scene_id, *, edit=None, turns=None):
        """A played scene whose deliveries carry what each turn's memory held of the agent's own moves, as the script says they were made."""

        item, leg, played = _run(scene_id)
        native = {d["scene_event"]: d["event_id"] for d in played["deliveries"]}
        moves: list[dict] = []
        for delivery in played["deliveries"]:
            delivery["received"] = {"trigger": delivery["event_id"], "mentioned_actor_ids": [], "reply_to_event_id": None, "own_moves": copy.deepcopy(moves)}
            for line in item.plan.lines:
                if native[line.trigger] == delivery["event_id"]:
                    action = line.action(delivery["event_id"])
                    move = {"kind": action["kind"]}
                    if action["kind"] != "message":
                        move["about_event_id"] = delivery["event_id"]
                    if action["kind"] == "reaction":
                        move["reaction"] = action["reaction"]
                    else:
                        move["text"] = action["text"]
                    moves.append(move)
        played["turns"] = [{"request_id": turn["request_id"], "trigger": turn["trigger"]} for turn in leg.invocations]
        if edit is not None:
            edit(played)
        return played

    def addressing(self, played):
        return checks.discord_addressing([played], agent="discord:actor:1", writes=[])

    def test_the_next_turn_and_each_graded_one_hold_the_agents_earlier_line_in_memory(self):
        for scene_id in SEVEN:
            with self.subTest(scene=scene_id):
                held = self.addressing(self.remembered(scene_id))
                self.assertTrue(held.ok, held.detail)

    def test_a_turn_that_forgot_the_nod_the_promise_or_the_words_fails_and_names_the_turn(self):
        def forget(scene_id, trigger, change):
            def edit(played):
                for delivery in played["deliveries"]:
                    if delivery["scene_event"] == trigger:
                        change(delivery["received"]["own_moves"])

            return self.addressing(self.remembered(scene_id, edit=edit))

        # The nod, at the turn that is asked about it.
        failed = forget("did-you-see", "z2", lambda moves: moves.clear())
        self.assertFalse(failed.ok)
        self.assertIn("did-you-see r1: the turn on discord:message:", failed.detail)
        self.assertIn("does not hold the agent's earlier reaction", failed.detail)
        # The promise, at the graded turn, however many messages came between.
        failed = forget("build-finishes-long-after-promise", "c1", lambda moves: moves.pop(0))
        self.assertFalse(failed.ok)
        self.assertIn("build-finishes-long-after-promise v1: the turn on", failed.detail)
        self.assertIn("does not hold the agent's earlier reply", failed.detail)
        # The words of a line that answered a cue, at the next turn.
        failed = forget("answered-while-composing", "q1", lambda moves: moves.__setitem__(0, {"kind": "message", "text": "something else"}))
        self.assertFalse(failed.ok)
        self.assertIn("answered-while-composing v1", failed.detail)
        # A move of the right kind about another message is not the nod.
        failed = forget("did-you-see", "z2", lambda moves: moves[0].update(about_event_id="discord:message:9"))
        self.assertFalse(failed.ok)
        # Nor is another reaction on the same message.
        failed = forget("did-you-see", "z2", lambda moves: moves[0].update(reaction="\N{THUMBS UP SIGN}"))
        self.assertFalse(failed.ok)
        self.assertIn("does not hold the agent's earlier reaction", failed.detail)

    def test_the_very_next_turn_must_hold_the_line_even_when_it_is_not_a_graded_one(self):
        # The promise is said on z1. The turn after it is on a1, chatter nobody grades; a memory that lost the promise there
        # and had it back by the graded turn would pass a check that read graded turns alone.
        def forget(trigger):
            def edit(played):
                for delivery in played["deliveries"]:
                    if delivery["scene_event"] == trigger:
                        delivery["received"]["own_moves"] = []

            return self.addressing(self.remembered("build-finishes-long-after-promise", edit=edit))

        failed = forget("a1")
        self.assertFalse(failed.ok)
        self.assertIn("build-finishes-long-after-promise v1: the turn on", failed.detail)
        # A turn in the middle that is neither the next nor a graded one is not held to it.
        self.assertTrue(forget("t5").ok)

    def test_a_line_that_did_not_land_is_left_to_directed_outcomes(self):
        def undelivered(played):
            for line in played["lines"]:
                line["actions"] = []

        self.assertTrue(self.addressing(self.remembered("did-you-see", edit=undelivered)).ok)


# -- the calls, the summary and CI --------------------------------------------------------------------------------


class RecordTest(unittest.TestCase):
    def test_the_column_must_make_the_post_or_the_reaction_an_earlier_line_of_the_agents_is(self):
        quiet = [{"expect": "directed", "graded": [{"scripted": "stay_quiet"}], "lines": [{"kind": "message"}]}]
        self.assertEqual(("GET /users/@me", discord_room.POST), discord_room.directed_calls(quiet))
        reply = [{"expect": "directed", "graded": [{"scripted": "stay_quiet"}], "lines": [{"kind": "reply"}]}]
        self.assertEqual(("GET /users/@me", discord_room.POST), discord_room.directed_calls(reply))
        nod = [{"expect": "directed", "graded": [{"scripted": "speak"}], "lines": [{"kind": "reaction"}]}]
        self.assertEqual(("GET /users/@me", discord_room.POST, discord_room.REACT), discord_room.directed_calls(nod))
        self.assertEqual(discord_room.TRANSPORT_ALWAYS, discord_room.directed_calls([{"expect": "directed", "graded": [{"scripted": "stay_quiet"}]}], discord_room.TRANSPORT_ALWAYS))

    def test_the_summary_says_a_scene_was_played_with_a_cue_and_that_its_time_was_compressed_and_how_each_hold_and_line_went(self):
        _, _, played = _run("answered-while-composing")
        text = record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "pass", "checks": [], "moments": [played]})
        self.assertIn("## How the scenes were played", text)
        self.assertIn("played with a cue", text)
        self.assertIn('"Vigil, anything to report?"', text)
        self.assertIn("time compressed", text)
        self.assertIn("3 h after the agent's first line play out in seconds", text)
        self.assertIn("the agent's earlier line v1", text)
        self.assertIn("landed as the scene has it", text)
        self.assertIn("hold on the turn at q1 (during-turn; a1 landed in it): **held**", text)
        _, _, played = _run("answered-while-composing", edit=_drop_line)
        text = record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "fail", "checks": [], "moments": [played]})
        self.assertIn("did not land: no turn began on cue-v1", text)
        # A scene without a line or a hold has nothing to say here.
        plain = directed.spec("story-across-messages")
        story = directed.play_scene(_Fake(plain), plain.plan, 5.0)
        self.assertNotIn("How the scenes were played", record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "pass", "checks": [], "moments": [story]}))

    def test_the_summary_says_asked_while_busy_was_played_in_another_order_and_what_that_means_live(self):
        _, _, played = _run("asked-while-busy")
        text = record.summary_markdown({"harness": "codex", "mode": "scripted", "status": "pass", "checks": [], "moments": [played]})
        self.assertIn("played in another order than the scene's", text)
        self.assertIn("The scene has z1, s1, v1, z2; played, z1, s1, z2, v1", text)
        self.assertIn("may drop it once it has been shown them", text)
        self.assertIn("cannot be assumed in a live run", text)
        self.assertIn("holds only once z2 is in", text)
        # A hold whose turn plays no line that the scene puts among the held messages changes no order.
        for scene_id in DURING:
            _, _, other = _run(scene_id)
            self.assertNotIn("another order", record.summary_markdown({"harness": "codex", "mode": "scripted", "status": "pass", "checks": [], "moments": [other]}))

    def test_a_reaction_line_is_described_by_its_emoji_and_a_reply_by_its_words(self):
        _, _, played = _run("did-you-see")
        text = record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "pass", "checks": [], "moments": [played]})
        self.assertIn(f"(reaction {standin.SCENE_NOD}, on z1)", text)
        self.assertIn("time compressed. The scene's 12 min", text)
        _, _, played = _run("build-finishes-after-promise")
        text = record.summary_markdown({"harness": "reference", "mode": "scripted", "status": "pass", "checks": [], "moments": [played]})
        self.assertIn('(reply "Sure, I\'ll tell you when it finishes.", on z1)', text)
        self.assertIn("The scene's 50 min", text)

    def test_the_matrix_marks_a_hold_that_did_not_hold(self):
        _, _, played = _run("answered-while-composing", early=("a1",), news=False)
        text = record.summary_markdown({"harness": "claude-code", "mode": "scripted", "status": "fail", "checks": [], "moments": [played]})
        self.assertIn("hold raced", text)
        _, _, held = _run("answered-while-composing")
        self.assertNotIn("hold held", record.summary_markdown({"harness": "claude-code", "mode": "scripted", "status": "pass", "checks": [], "moments": [held]}))


class DocsTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def test_the_order_asked_while_busy_is_played_in_is_stated_as_a_deviation_where_the_scenes_are_listed(self):
        for path in ("docs/rehearsal.md", "CHANGELOG.md", "evals/behavior/README.md"):
            with self.subTest(path=path):
                text = " ".join((self.ROOT / path).read_text(encoding="utf-8").split())
                self.assertIn("another order than", text)
                self.assertIn("asked-while-busy", text)
        text = " ".join((self.ROOT / "docs" / "rehearsal.md").read_text(encoding="utf-8").split())
        self.assertIn("holds only after z2", text)
        self.assertIn("may drop the reply after the look page", text)
        self.assertNotIn("changes nothing about what it owes Zoe", text)


if __name__ == "__main__":
    unittest.main()
