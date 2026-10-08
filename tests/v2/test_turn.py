"""The turn's rules live in the core, the same for every harness (#94 step 9c).

These tests drive `nunchi.turn` through a driver that is no particular
harness, with tool names of its own choosing. The Claude Code gate's tests
cover the same rules through its session and mod.
"""

from __future__ import annotations

from copy import deepcopy
import re
import threading
import unittest

from nunchi.participant import TransportResult
from nunchi.turn import SecretGuard, TurnError, TurnParticipant
from tests.v2.test_claude_code import OPPORTUNITY, PROFILE, test_wake

NAMES = {
    "send": "say",
    "react": "emoji",
    "propose": "ask_operator",
    "withdraw": "take_back",
    "context": "look",
}


class RecordingDriver:
    """Starts nothing; the test plays the agent's calls by hand."""

    def __init__(self):
        self.started = []
        self.interrupted = []
        self.started_event = threading.Event()

    def start(self, turn):
        self.started.append(turn)
        self.started_event.set()

    def interrupt(self, turn):
        self.interrupted.append(turn)


class Room:
    """A live room view: `new` and `news` show each arrival once."""

    def __init__(self):
        self.arrivals = []
        self.calls = []

    def expand(self, **request):
        self.calls.append(request)
        if request["direction"] in ("new", "news"):
            events, self.arrivals = self.arrivals, []
            return {"events": events}
        return {"events": []}


def wait_until(condition, timeout=5.0):
    pause = threading.Event()
    for _ in range(int(timeout / 0.05)):
        if condition():
            return True
        pause.wait(0.05)
    return condition()


def message(event_id, text="meanwhile"):
    return {
        "id": event_id,
        "type": "message",
        "author_id": "discord:actor:7",
        "text": text,
        "mentioned_actor_ids": [],
        "mentions_room": False,
    }


class GuardTests(unittest.TestCase):
    """A guard grows by copy; the participant swaps its own before the first turn."""

    def refuses(self, guard, text):
        return guard.refusal({"kind": "message", "origin_event_id": "e1", "text": text}) is not None

    def test_including_returns_a_copy_with_the_new_values_and_the_same_shapes(self):
        original = SecretGuard(["a-withheld-secret-value"], [re.compile(r"tok_[a-z]{8}")])
        grown = original.including(["a-launch-secret-for-this-turn", "short"])
        self.assertIsNot(original, grown)
        self.assertTrue(self.refuses(grown, "a-launch-secret-for-this-turn"))
        self.assertTrue(self.refuses(grown, "a-withheld-secret-value"))
        self.assertTrue(self.refuses(grown, "tok_abcdefgh"))
        # Values under 12 characters are ignored; the original is unchanged.
        self.assertFalse(self.refuses(grown, "short"))
        self.assertFalse(self.refuses(original, "a-launch-secret-for-this-turn"))

    def test_a_subclass_keeps_its_own_shapes(self):
        from nunchi.integrations.claude_code_gate import SecretGuard as GateGuard

        token = "M" * 24 + ".GaBcDe." + "y" * 30
        grown = GateGuard([]).including(["a-launch-secret-for-this-turn"])
        self.assertIsInstance(grown, GateGuard)
        self.assertTrue(self.refuses(grown, f"the token is {token}"))
        self.assertTrue(self.refuses(grown, "a-launch-secret-for-this-turn"))

    def test_withhold_gives_later_turns_the_grown_guard_and_leaves_the_given_one(self):
        given = SecretGuard(["a-withheld-secret-value"])
        driver = RecordingDriver()
        participant = TurnParticipant(
            profile=PROFILE, driver=driver, guard=given, tool_names=NAMES, result_wait_seconds=5
        )
        participant.withhold(["a-launch-secret-for-this-turn"])
        self.assertIsNot(given, participant.guard)
        self.assertFalse(self.refuses(given, "a-launch-secret-for-this-turn"))
        cancel = threading.Event()
        self.addCleanup(cancel.set)
        threading.Thread(
            target=lambda: participant.run_protocol(
                wake=test_wake(), opportunity=deepcopy(OPPORTUNITY), expand=Room().expand, cancel=cancel
            ),
            daemon=True,
        ).start()
        self.assertTrue(driver.started_event.wait(5))
        turn = driver.started[0]
        self.assertIs(participant.guard, turn.guard)
        self.assertTrue(participant.bind_turn(turn_id="t1", wake_id=turn.wake_id))
        ok, text = participant.call_tool(
            turn_id="t1", tool="say", arguments={"text": "my session is a-launch-secret-for-this-turn"}
        )
        self.assertFalse(ok)
        self.assertIn("secret", text)
        self.assertFalse(turn.action_ready.is_set())


class TurnTests(unittest.TestCase):
    def setUp(self):
        self.driver = RecordingDriver()
        self.room = Room()
        self.participant = TurnParticipant(
            profile=PROFILE,
            driver=self.driver,
            guard=SecretGuard(["a-withheld-secret-value"], [re.compile(r"tok_[a-z]{8}")]),
            tool_names=NAMES,
            result_wait_seconds=5,
        )
        self.cancel = threading.Event()
        self.box = {}

        def run():
            try:
                self.box["action"] = self.participant.run_protocol(
                    wake=test_wake(),
                    opportunity=deepcopy(OPPORTUNITY),
                    expand=self.room.expand,
                    cancel=self.cancel,
                )
            except BaseException as exc:  # noqa: BLE001 - recorded for assertions
                self.box["error"] = exc

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.assertTrue(self.driver.started_event.wait(5))
        self.turn = self.driver.started[0]

    def tearDown(self):
        self.cancel.set()
        self.thread.join(5)

    def act(self, tool, arguments, turn_id="t1"):
        answer = {}
        thread = threading.Thread(
            target=lambda: answer.setdefault(
                "value",
                self.participant.call_tool(turn_id=turn_id, tool=tool, arguments=arguments),
            ),
            daemon=True,
        )
        thread.start()
        return thread, answer

    def test_the_turn_text_names_the_integrations_tools(self):
        self.assertIn("say", self.turn.text)
        self.assertIn("<nunchi_participant_turn_v1>", self.turn.text)
        # Privileged proposals are off in this opportunity, so they are not offered.
        self.assertEqual({"send", "react", "context"}, set(self.turn.tool_names))
        self.assertTrue(self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id))
        self.assertEqual(
            (False, "ask_operator is not available in this turn."),
            self.participant.call_tool(turn_id="t1", tool="ask_operator", arguments={}),
        )
        self.assertEqual(
            (False, "post is not a Nunchi room tool."),
            self.participant.call_tool(turn_id="t1", tool="post", arguments={}),
        )

    def test_a_bound_turn_that_ends_without_an_action_is_silence(self):
        self.assertTrue(self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id))
        self.participant.turn_ended(ok=True, detail="done")
        self.thread.join(5)
        self.assertEqual({"action": None}, self.box)

    def test_a_silent_turns_last_words_are_its_reason(self):
        self.assertTrue(self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id))
        self.assertTrue(
            self.participant.end_turn(
                turn_id="t1", ok=True, detail="done", note="  Castor was asked,\n not me. "
            )
        )
        self.thread.join(5)
        self.assertEqual({"action": {"kind": "silence", "why": "Castor was asked, not me."}}, self.box)

    def test_last_words_holding_a_secret_are_not_kept(self):
        self.assertTrue(self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id))
        self.participant.turn_ended(ok=True, detail="done", note="The key is tok_abcdefgh.")
        self.thread.join(5)
        self.assertEqual({"action": None}, self.box)

    def test_last_words_after_an_action_are_no_reason(self):
        self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id)
        thread, answer = self.act("say", {"text": "on it"})
        self.thread.join(5)
        self.assertNotIn("why", self.box["action"])
        self.participant.settle(self.turn.request_id, TransportResult("sent", "ok"))
        thread.join(5)
        self.participant.end_turn(turn_id="t1", ok=True, note="Posted it.")
        self.assertIsNone(self.turn.note)

    def test_a_failed_runs_last_words_are_no_reason(self):
        self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id)
        self.participant.end_turn(turn_id="t1", ok=False, detail="crashed", note="I stopped.")
        self.thread.join(5)
        self.assertIsInstance(self.box.get("error"), TurnError)
        self.assertIsNone(self.turn.note)

    def test_an_unbound_turn_is_a_failure_never_silence(self):
        self.assertFalse(self.participant.bind_turn(turn_id="t1", wake_id="wrong"))
        self.participant.turn_ended(ok=True, detail="done")
        self.thread.join(5)
        self.assertIsInstance(self.box.get("error"), TurnError)
        self.assertIn("did not bind", str(self.box["error"]))

    def test_a_call_outside_a_bound_turn_posts_nothing(self):
        ok, text = self.participant.call_tool(turn_id="t1", tool="say", arguments={"text": "hi"})
        self.assertFalse(ok)
        self.assertIn("Nothing was posted", text)

    def test_the_one_action_goes_to_the_host_and_its_result_back_to_the_agent(self):
        self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id)
        thread, answer = self.act("say", {"text": "on it"})
        self.thread.join(5)
        action = self.box["action"]
        self.assertEqual(("message", "on it", "e1"), (action["kind"], action["text"], action["origin_event_id"]))
        self.participant.settle(self.turn.request_id, TransportResult("sent", "ok"))
        thread.join(5)
        self.assertEqual((True, "Done: the room accepted this action."), answer["value"])
        ok, text = self.participant.call_tool(turn_id="t1", tool="say", arguments={"text": "again"})
        self.assertFalse(ok)

    def test_the_first_post_is_held_once_when_others_posted_meanwhile(self):
        self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id)
        self.room.arrivals = [message("e2", "actually, never mind")]
        ok, text = self.participant.call_tool(turn_id="t1", tool="say", arguments={"text": "on it"})
        self.assertTrue(ok)
        self.assertTrue(text.startswith("Not posted yet: 1 new message(s)"))
        self.assertIn("never mind", text)
        self.assertFalse(self.turn.action_ready.is_set())
        # The agent may now answer the new message; the look-again happens once.
        self.room.arrivals = [message("e3")]
        thread, answer = self.act("say", {"text": "ok, dropping it", "reply_to_event_id": "e2"})
        self.thread.join(5)
        self.assertEqual("e2", self.box["action"]["target_event_id"])

    def test_steering_shows_each_message_once_and_the_look_again_skips_it(self):
        self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id)
        self.room.arrivals = [message("e2", "use the staging branch")]
        update = self.participant.news(turn_id="t1")
        self.assertTrue(update.startswith("Room update: 1 new message(s)"))
        self.assertIn("staging branch", update)
        self.assertIsNone(self.participant.news(turn_id="t1"))
        self.assertIsNone(self.participant.news(turn_id="someone-else"))
        thread, answer = self.act("say", {"text": "will do", "reply_to_event_id": "e2"})
        self.thread.join(5)
        self.assertEqual("e2", self.box["action"]["target_event_id"])

    def test_secret_values_and_named_credential_shapes_never_reach_the_room(self):
        self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id)
        for text in ("here: a-withheld-secret-value", "token tok_abcdefgh"):
            ok, answer = self.participant.call_tool(turn_id="t1", tool="say", arguments={"text": text})
            self.assertFalse(ok)
            self.assertIn("credential or secret", answer)
        self.assertFalse(self.turn.action_ready.is_set())

    def test_cancelling_the_turn_interrupts_the_agent(self):
        self.participant.bind_turn(turn_id="t1", wake_id=self.turn.wake_id)
        self.cancel.set()
        self.thread.join(5)
        self.assertEqual({"action": None}, self.box)
        self.assertEqual([self.turn], self.driver.interrupted)
        ok, text = self.participant.call_tool(turn_id="t1", tool="say", arguments={"text": "late"})
        self.assertFalse(ok)
        # The library is done with a cancelled turn: it is closed, so the next
        # one need not wait for the harness to report the end.
        self.assertIsNone(self.participant.active)
        self.assertFalse(self.participant.end_turn(turn_id="t1", ok=True))


class TurnLifecycleTests(unittest.TestCase):
    """One turn at a time, whatever the harness reports (#94 step 9e)."""

    def participant(self, driver, **kwargs):
        return TurnParticipant(
            profile=PROFILE, driver=driver, guard=SecretGuard(()), tool_names=NAMES, result_wait_seconds=5, **kwargs
        )

    def run_turn(self, participant, cancel):
        box = {}

        def run():
            try:
                box["action"] = participant.run_protocol(
                    wake=test_wake(), opportunity=deepcopy(OPPORTUNITY), expand=Room().expand, cancel=cancel
                )
            except BaseException as exc:  # noqa: BLE001 - recorded for assertions
                box["error"] = exc

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, box

    def test_the_next_turn_waits_for_the_previous_runs_end(self):
        driver = RecordingDriver()
        participant = self.participant(driver)
        first_cancel, second_cancel = threading.Event(), threading.Event()
        self.addCleanup(first_cancel.set)
        self.addCleanup(second_cancel.set)
        first, first_box = self.run_turn(participant, first_cancel)
        self.assertTrue(driver.started_event.wait(5))
        turn = driver.started[0]
        participant.bind_turn(turn_id="t1", wake_id=turn.wake_id)
        threading.Thread(
            target=participant.call_tool,
            kwargs={"turn_id": "t1", "tool": "say", "arguments": {"text": "On it."}},
            daemon=True,
        ).start()
        first.join(5)
        self.assertEqual("message", first_box["action"]["kind"])
        # The agent's run is still finishing after its post: the next turn waits.
        second, second_box = self.run_turn(participant, second_cancel)
        second.join(0.3)
        self.assertEqual(1, len(driver.started))
        participant.end_turn(turn_id="t1", ok=True)
        self.assertTrue(wait_until(lambda: len(driver.started) == 2))
        self.assertNotIn("error", second_box)

    def test_a_previous_turn_the_harness_never_ends_closes_after_a_grace(self):
        driver = RecordingDriver()
        participant = self.participant(driver, previous_turn_grace_seconds=0.2)
        first_cancel, second_cancel = threading.Event(), threading.Event()
        self.addCleanup(first_cancel.set)
        self.addCleanup(second_cancel.set)
        first, _ = self.run_turn(participant, first_cancel)
        self.assertTrue(driver.started_event.wait(5))
        old = driver.started[0]
        participant.bind_turn(turn_id="t1", wake_id=old.wake_id)
        old.take({"kind": "silence"})  # the run returned, and its end never comes
        first.join(5)
        second, second_box = self.run_turn(participant, second_cancel)
        self.assertTrue(wait_until(lambda: len(driver.started) == 2))
        self.assertTrue(old.ended.is_set())
        self.assertFalse(old.end_ok)
        self.assertIn("never reported the end", old.end_detail)
        # The old run's late calls find its turn closed.
        self.assertEqual("silent", participant.finish(turn_id="t1", answer="late").kind)
        self.assertFalse(participant.end_turn(turn_id="t1", ok=True))

    def test_a_harness_that_cannot_take_the_turn_fails_it(self):
        class NotReady(RecordingDriver):
            def ready(self, cancel):
                return False

        driver = NotReady()
        cancel = threading.Event()
        thread, box = self.run_turn(self.participant(driver), cancel)
        thread.join(5)
        self.assertIsInstance(box.get("error"), TurnError)
        self.assertEqual([], driver.started)
        # Not ready because the turn was cancelled is no failure.
        cancel.set()
        thread, box = self.run_turn(self.participant(NotReady()), cancel)
        thread.join(5)
        self.assertEqual({"action": None}, box)

    def test_a_run_that_never_binds_fails_after_the_bind_timeout(self):
        driver = RecordingDriver()
        participant = self.participant(driver, bind_timeout_seconds=0.2)
        cancel = threading.Event()
        self.addCleanup(cancel.set)
        thread, box = self.run_turn(participant, cancel)
        thread.join(5)
        self.assertIsInstance(box.get("error"), TurnError)
        self.assertIn("did not start within 0.2 seconds", str(box["error"]))
        self.assertEqual(driver.started, driver.interrupted)
        self.assertIsNone(participant.active)


if __name__ == "__main__":
    unittest.main()


class OneReplyTurnTests(unittest.TestCase):
    """The one-reply style drives the same Turn and gets the same rules."""

    def protocol(self, guard=None):
        from nunchi.participant_model import ParticipantTurnProtocol

        return ParticipantTurnProtocol(
            profile=PROFILE, wake=test_wake(), opportunity=deepcopy(OPPORTUNITY), guard=guard
        )

    @staticmethod
    def reply(protocol, action):
        return {
            "protocol": protocol.request["protocol"],
            "binding": {"request_id": protocol.request_id},
            "action": action,
        }

    def test_the_look_again_is_the_turns_own(self):
        protocol = self.protocol()
        room = Room()
        room.arrivals = [message("e2", "actually, never mind")]
        say = {"kind": "message", "origin_event_id": "e1", "text": "on it"}
        self.assertEqual((False, None), protocol.consume(self.reply(protocol, say), expand=room.expand))
        self.assertTrue(protocol.turn.looked_again)
        self.assertIn("e2", protocol.turn.visible_event_ids)
        self.assertTrue(protocol.pages[-1]["note"].startswith("Not posted yet: 1 new message(s)"))
        done, action = protocol.consume(self.reply(protocol, say), expand=room.expand)
        self.assertTrue(done)
        self.assertEqual(action, protocol.turn.action)

    def test_a_guarded_secret_is_refused_once_then_fails_the_turn(self):
        from nunchi.participant_model import ParticipantModelError

        protocol = self.protocol(guard=SecretGuard(["a-withheld-secret-value"]))
        leak = {"kind": "message", "origin_event_id": "e1", "text": "a-withheld-secret-value"}
        self.assertEqual((False, None), protocol.consume(self.reply(protocol, leak), expand=None))
        self.assertIn("credential or secret", protocol.pages[-1]["note"])
        with self.assertRaises(ParticipantModelError):
            protocol.consume(self.reply(protocol, leak), expand=None)


class FinalAnswerTurnTests(unittest.TestCase):
    """Final-answer posting: the agent's answer is its post (#94 step 9c)."""

    def turn(self, room=None, guard=None, tool_names=None):
        from nunchi.participant_model import build_participant_turn_request
        from nunchi.turn import Turn

        return Turn(
            profile=PROFILE,
            request=build_participant_turn_request(test_wake(), deepcopy(OPPORTUNITY)),
            tool_names=tool_names or {"react": "emoji", "context": "look"},
            expand=(room or Room()).expand,
            guard=guard,
            result_wait_seconds=2,
            silence_marker="[SILENT]",
        )

    def test_the_marker_or_nothing_is_silence_and_a_note_after_it_is_never_posted(self):
        for answer in (
            "[SILENT]",
            "  [SILENT]\n\nNothing to add here.",
            "[silent]",
            "Zoe asked Castor, who has not answered.\nCastor should take it.\n\n[SILENT]",
            "",
            None,
        ):
            with self.subTest(answer=answer):
                turn = self.turn()
                self.assertEqual("silent", turn.decide(answer).kind)
                self.assertIsNone(turn.action)

    def test_thinking_is_never_posted_and_becomes_the_reason(self):
        turn = self.turn()
        decision = turn.decide("<thinking>Zoe asked me directly; I have not checked yet.</thinking>\nNot yet, checking now.")
        self.assertEqual(("deliver", "Not yet, checking now."), (decision.kind, decision.text))
        self.assertEqual("Zoe asked me directly; I have not checked yet.", turn.action["why"])
        self.assertEqual("Not yet, checking now.", turn.action["text"])
        quiet = self.turn()
        self.assertEqual("silent", quiet.decide("<thinking>Castor was asked; let him answer.</thinking>\n[SILENT]").kind)
        self.assertEqual("Castor was asked; let him answer.", quiet.note)
        unclosed = self.turn()
        self.assertEqual("silent", unclosed.decide("<thinking>I could say that the build").kind)
        self.assertIsNone(unclosed.action)

    def test_an_answer_is_the_turns_one_message(self):
        turn = self.turn()
        decision = turn.decide("  On it, checking the logs now.  ")
        self.assertEqual(("deliver", "On it, checking the logs now."), (decision.kind, decision.text))
        self.assertEqual(
            {"kind": "message", "origin_event_id": "e1", "text": "On it, checking the logs now."},
            turn.action,
        )
        self.assertEqual("silent", turn.decide("and another thing").kind)

    def test_it_looks_again_once_before_posting(self):
        room = Room()
        room.arrivals = [message("e2", "never mind, found it")]
        turn = self.turn(room)
        decision = turn.decide("On it.")
        self.assertEqual("continue", decision.kind)
        self.assertTrue(decision.text.startswith("Not posted yet: 1 new message(s)"))
        self.assertIn('"On it."', decision.text)
        self.assertIn("never mind", decision.text)
        self.assertIn("e2", turn.visible_event_ids)
        room.arrivals = [message("e3")]
        self.assertEqual("deliver", turn.decide("Glad you found it.").kind)

    def test_a_secret_is_refused_once_then_the_turn_stays_silent(self):
        turn = self.turn(guard=SecretGuard(["a-withheld-secret-value"]))
        first = turn.decide("the key is a-withheld-secret-value")
        self.assertEqual("continue", first.kind)
        self.assertIn("credential or secret", first.text)
        self.assertIn("[SILENT]", first.text)
        self.assertEqual("silent", turn.decide("the key is a-withheld-secret-value").kind)
        self.assertIsNone(turn.action)

    def test_a_reaction_taken_as_a_tool_is_the_turns_action(self):
        turn = self.turn()
        turn.bind(turn_id="t1", wake_id=turn.wake_id)
        threading.Thread(
            target=turn.call, args=("react", {"target_event_id": "e1", "reaction": "👍"}), daemon=True
        ).start()
        self.assertTrue(turn.action_ready.wait(5))
        self.assertEqual("silent", turn.decide("Thanks!").kind)

    def test_the_harness_delivers_only_what_the_host_committed_for_it(self):
        from nunchi.turn import HARNESS_DELIVERS

        for result, expected in (
            (TransportResult("unknown", HARNESS_DELIVERS), "deliver"),
            (None, "silent"),
            (TransportResult("sent", "posted by the library"), "silent"),
            (TransportResult("failed", "stale"), "silent"),
        ):
            with self.subTest(result=result):
                turn = self.turn()
                answer = {}
                thread = threading.Thread(
                    target=lambda: answer.setdefault("finish", turn.finish("On it.")), daemon=True
                )
                thread.start()
                self.assertTrue(turn.action_ready.wait(5))
                turn.settle(result)
                thread.join(5)
                self.assertEqual(expected, answer["finish"].kind)

    def test_a_turn_needs_a_marker_and_has_no_send_tool(self):
        with self.assertRaises(ValueError):
            self.turn(tool_names={"send": "say", "context": "look"})
        from nunchi.turn import Turn, TurnError
        from nunchi.participant_model import build_participant_turn_request

        tools_turn = Turn(
            profile=PROFILE,
            request=build_participant_turn_request(test_wake(), deepcopy(OPPORTUNITY)),
            tool_names={"send": "say"},
        )
        with self.assertRaises(TurnError):
            tools_turn.decide("hi")

    def test_the_text_says_the_reply_is_the_post_and_names_the_marker(self):
        text = self.turn().text
        self.assertIn("Your final reply in this turn is posted to the room", text)
        self.assertIn("no reasoning, analysis, headings, or notes to yourself", text)
        self.assertIn("put exactly [SILENT] outside it", text)
        self.assertIn("inside <thinking></thinking>: it is never posted", text)
        self.assertIn("call emoji once", text)
        self.assertNotIn("never posted to the room", text)


class SilenceFormTests(unittest.TestCase):
    """The agent's silence is silence in whatever form it wrote it (leak audit row 6)."""

    def turn(self, also_silent=("NO_REPLY", "SILENT")):
        from nunchi.participant_model import build_participant_turn_request
        from nunchi.turn import Turn

        return Turn(
            profile=PROFILE,
            request=build_participant_turn_request(test_wake(), deepcopy(OPPORTUNITY)),
            tool_names={"react": "emoji", "context": "look"},
            expand=Room().expand,
            result_wait_seconds=2,
            silence_marker="[SILENT]",
            also_silent=also_silent,
        )

    def test_a_wrapped_marker_or_the_harnesss_other_silent_answer_is_silence(self):
        for answer in (
            "**[SILENT]**",
            "`[SILENT]`",
            "~~[SILENT]~~",
            "[silent].",
            '"[SILENT]"',
            "_[SILENT]_",
            "**[SILENT]** Castor has this one.",
            "Castor has it.\n`[SILENT]`",
            "NO_REPLY",
            "no_reply.",
            "Silent",
            "(silent)",
            "<thinking>Bob asked Castor.</thinking>\nSILENT.",
        ):
            with self.subTest(answer=answer):
                turn = self.turn()
                self.assertEqual("silent", turn.decide(answer).kind)
                self.assertIsNone(turn.action)
        quiet = self.turn()
        quiet.decide("<thinking>Bob asked Castor.</thinking>\n**NO_REPLY**")
        self.assertEqual("Bob asked Castor.", quiet.note)

    def test_a_post_that_only_looks_like_silence_goes_out(self):
        for answer in (
            "No reply from Bob yet. Want me to ping him?",
            "I pinged the vendor twice.\nNo reply.\nWant me to escalate?",
            "Use `[SILENT]` when nothing changed.",
            "Silent night is my favourite carol.",
            "SILENT is a great film.",
            "Done: NO_REPLY was the wrong flag name.",
            "> [SILENT]",
        ):
            with self.subTest(answer=answer):
                turn = self.turn()
                decision = turn.decide(answer)
                self.assertEqual(("deliver", answer), (decision.kind, decision.text))
                self.assertEqual(answer, turn.action["text"])

    def test_another_silent_answer_counts_only_when_the_integration_lists_it(self):
        turn = self.turn(also_silent=())
        self.assertEqual("deliver", turn.decide("NO_REPLY").kind)

    def test_also_silent_needs_a_marker_and_real_answers(self):
        from nunchi.participant_model import build_participant_turn_request
        from nunchi.turn import Turn

        for kwargs in (
            {"silence_marker": "..."},
            {"also_silent": ("NO_REPLY",)},
            {"silence_marker": "[SILENT]", "also_silent": "NO_REPLY"},
            {"silence_marker": "[SILENT]", "also_silent": ("NO_REPLY", "**")},
            {"silence_marker": "[SILENT]", "also_silent": (None,)},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    Turn(
                        profile=PROFILE,
                        request=build_participant_turn_request(test_wake(), deepcopy(OPPORTUNITY)),
                        **kwargs,
                    )
                with self.assertRaises(ValueError):
                    TurnParticipant(
                        profile=PROFILE, driver=RecordingDriver(), guard=SecretGuard(()), tool_names=NAMES, **kwargs
                    )


def run_in_thread(participant, room=None):
    """Run the participant's turn; the box gets ("ok", action) or ("error", exception)."""

    box = {}
    cancel = threading.Event()

    def play():
        try:
            box["ok"] = participant.run_protocol(
                wake=test_wake(), opportunity=deepcopy(OPPORTUNITY), expand=(room or Room()).expand, cancel=cancel
            )
        except BaseException as exc:  # recorded for the test
            box["error"] = exc

    thread = threading.Thread(target=play, daemon=True)
    thread.start()
    return box, thread, cancel


class ModelTextTests(unittest.TestCase):
    """Only words the agent's model wrote can be its post (leak audit row 5)."""

    def setUp(self):
        self.fresh()

    def fresh(self):
        # Each turn of the same wake has the same request id: one per participant.
        self.driver = RecordingDriver()
        self.participant = TurnParticipant(
            profile=PROFILE,
            driver=self.driver,
            guard=SecretGuard(["a-withheld-secret-value"]),
            tool_names=NAMES,
            result_wait_seconds=5,
            silence_marker="[SILENT]",
            model_text=True,
        )

    def open_turn(self):
        self.box, self.thread, cancel = run_in_thread(self.participant)
        self.addCleanup(cancel.set)
        self.assertTrue(self.driver.started_event.wait(5))
        turn = self.driver.started[0]
        self.assertTrue(self.participant.bind_turn(turn_id="t1", wake_id=turn.wake_id))
        return turn

    def end(self, ok=True):
        self.participant.end_turn(turn_id="t1", ok=ok, detail="the run ended")
        self.thread.join(5)
        return self.box

    def finish_and_commit(self, turn, answer):
        from nunchi.turn import HARNESS_DELIVERS

        answered = {}
        thread = threading.Thread(
            target=lambda: answered.setdefault("finish", self.participant.finish(turn_id="t1", answer=answer)),
            daemon=True,
        )
        thread.start()
        if turn.action_ready.wait(2):
            self.participant.settle(turn.request_id, TransportResult("unknown", HARNESS_DELIVERS))
        thread.join(5)
        return answered["finish"]

    def test_an_answer_its_model_wrote_is_delivered(self):
        turn = self.open_turn()
        self.assertTrue(self.participant.model_wrote(turn_id="t1", text="On it, checking the logs now."))
        decision = self.finish_and_commit(turn, "On it, checking the logs now.")
        self.assertEqual(("deliver", "On it, checking the logs now."), (decision.kind, decision.text))
        self.thread.join(5)
        self.assertEqual("On it, checking the logs now.", self.box["ok"]["text"])
        self.assertIsNone(turn.unattributed)

    def test_the_harnesss_text_is_never_posted_and_fails_the_turn_even_when_the_run_ended_ok(self):
        held = "no reported model response holds this text"
        empty = f"{held} (each was empty)"
        for wrote, answer, detail in (
            (["Let me check the deploy logs first."], "I reached the iteration limit and couldn't generate a summary.", held),
            ([""], "(empty)", empty),
            (["", ""], "⚠️ No reply: the model didn't produce a reply this time. Send `continue` to try again.", empty),
            (["Looking into it now."], "Hermes hit repeated errors. Details: RuntimeError: boom", held),
            # Scattered words are not a contiguous run.
            (["I reached the end of the logs; the iteration count hit its limit."], "I reached the iteration limit", held),
            # The marker counts only when the model wrote it.
            (["On it."], "[SILENT]", held),
            # A harness's one-word stand-in is not the model's word inside
            # what it wrote, its thinking or its reasoning (leak audit row 5).
            (["The queue is not empty."], "(empty)", held),
            (["Let me see whether the deploy queue is empty.", ""], "(empty)", held),
            (["<think>The deploy log is empty, so the job never started.</think>"], "(empty)", held),
            (["<thinking>empty</thinking>"], "(empty)", held),
            (["", ("The log they pasted is empty, so I cannot see the error yet.", True)], "(empty)", held),
            (["", ("empty", True)], "(empty)", held),
            # Reasoning counts only as a whole, not a run of words inside it.
            (["", ("I could say the deploy failed at the migration step, but let me check first.", True)],
             "The deploy failed at the migration step.", held),
            (["<think>Maybe: the deploy failed at the migration step. Check first.</think>"],
             "The deploy failed at the migration step.", held),
            # A short answer keeps its punctuation and its word edges.
            (["Button it."], "On it.", held),
        ):
            with self.subTest(answer=answer, wrote=wrote):
                self.fresh()
                turn = self.open_turn()
                for text in wrote:
                    text, reasoning = text if isinstance(text, tuple) else (text, False)
                    self.participant.model_wrote(turn_id="t1", text=text, reasoning=reasoning)
                self.assertEqual("silent", self.participant.finish(turn_id="t1", answer=answer).kind)
                self.assertIsNone(turn.action)
                self.assertIn(detail, turn.unattributed)
                # Whatever comes next in the run, the turn posts nothing.
                self.participant.model_wrote(turn_id="t1", text="On it.")
                self.assertEqual("silent", self.participant.finish(turn_id="t1", answer="On it.").kind)
                box = self.end(ok=True)
                self.assertNotIn("ok", box)
                self.assertIsInstance(box["error"], TurnError)
                self.assertIn("the agent's run ended with an answer that is not its model's reported words", str(box["error"]))
                self.assertIn(detail, str(box["error"]))

    def test_the_models_words_reshaped_by_its_harness_are_still_its_own(self):
        reasoning = lambda text: (text, True)  # noqa: E731
        for wrote, answer in (
            # The harness strips thinking or a tool call the model wrote as text.
            (["<think>Sam asked me directly.</think>The migration step timed out."], "The migration step timed out."),
            (["Checking.<tool_call>{\"name\": \"room_context\"}</tool_call> The migration timed out."], "Checking. The migration timed out."),
            # It strips markdown.
            (["**The migration** step _timed out_."], "The migration step timed out."),
            # It joins a continuation cut at the length limit, with or without a
            # separator, with the reasoning reported between the parts.
            (["The migration step timed out at 02:00 and the", reasoning("(reasoning)"), "rollback finished cleanly."],
             "The migration step timed out at 02:00 and the\nrollback finished cleanly."),
            (["The migra", "tion step timed out."], "The migration step timed out."),
            # A cut inside a tagged block, such as an HTML snippet, leaves half
            # the pair in each part.
            (["Here is the banner, then the steps.\n\n```html\n<div class=\"banner\">\n  <p>Deploys are paused.",
              "</p>\n</div>\n```\n\nThen merge it and deploy to the canary first."],
             "Here is the banner, then the steps.\n\n```html\n<div class=\"banner\">\n  <p>Deploys are paused."
             "</p>\n</div>\n```\n\nThen merge it and deploy to the canary first."),
            # A short reply cut between its two words.
            (["On", "it."], "On\nit."),
            # It joins a stream cut mid-answer to a continuation that repeats
            # the last words, dropping the repeat.
            (["Freeze deploys first. Then scale the canary down and confirm traffic drains",
              "confirm traffic drains in the dashboard. Then run the down migration."],
             "Freeze deploys first. Then scale the canary down and confirm traffic drains in the dashboard. "
             "Then run the down migration."),
            # It answers with the model's reasoning when the content was empty,
            # whole, or the parts of its reasoning joined.
            (["", reasoning("Sam asked me; the migration step timed out at 02:00.")],
             "Sam asked me; the migration step timed out at 02:00."),
            (["", reasoning("On it.")], "On it."),
            (["", reasoning("Run <code>make rollback</code> first, then redeploy the canary.")],
             "Run <code>make rollback</code> first, then redeploy the canary."),
            (["", reasoning("The migration step timed out.\n\nRerunning it should fix it.")],
             "The migration step timed out.\n\nRerunning it should fix it."),
            # It reuses what the model wrote before a tool call.
            (["Checking the logs now.", ""], "Checking the logs now."),
            # A short reply, alone or at the start of what the model wrote.
            (["On it."], "On it."),
            (["Done. Next I'll check the logs."], "Done."),
            (["<think>Sam asked me.</think>On it."], "On it."),
            # An emoji alone, with or without its presentation selector.
            (["👍️"], "👍"),
            (["👍"], "👍️"),
            (["…"], "…"),
            # Thinking in the answer is the agent's own and is not compared.
            (["On it."], "<thinking>Sam asked me, and nobody else has looked.</thinking>On it."),
        ):
            with self.subTest(answer=answer):
                self.fresh()
                turn = self.open_turn()
                for text in wrote:
                    text, kind = text if isinstance(text, tuple) else (text, False)
                    self.participant.model_wrote(turn_id="t1", text=text, reasoning=kind)
                decision = self.finish_and_commit(turn, answer)
                self.assertEqual("deliver", decision.kind, turn.unattributed)
                self.thread.join(5)
                self.assertEqual("message", self.box["ok"]["kind"])

    def test_a_long_or_repetitive_answer_is_checked_in_bounded_time(self):
        # A harness gives up on a slow output hook (Hermes then posts the raw draft).
        import time

        from nunchi.turn import _written_by_model

        text = " ".join(["alpha beta gamma delta epsilon zeta eta theta iota kappa"] * 4000)
        half = len(text) // 2
        started = time.monotonic()
        self.assertTrue(_written_by_model(text, [text[:half], text[half - 500:]]))
        self.assertFalse(_written_by_model(text + " omega", [text[:half], "x", text[half:]]))
        self.assertLess(time.monotonic() - started, 5)

    def test_an_integration_that_reports_nothing_fails_loudly(self):
        turn = self.open_turn()
        self.assertEqual("silent", self.participant.finish(turn_id="t1", answer="On it.").kind)
        self.assertIn("reported nothing its model wrote", turn.unattributed)
        box = self.end()
        self.assertIn("declared model_text", str(box["error"]))

    def test_an_empty_answer_is_still_silence(self):
        turn = self.open_turn()
        self.assertEqual("silent", self.participant.finish(turn_id="t1", answer="").kind)
        self.assertEqual("silent", self.participant.finish(turn_id="t1", answer="<thinking>Castor has it.</thinking>").kind)
        self.assertIsNone(turn.unattributed)
        self.assertEqual({"ok": {"kind": "silence", "why": "Castor has it."}}, self.end())

    def test_after_its_reaction_the_harnesss_text_posts_nothing_more(self):
        turn = self.open_turn()
        reacting = threading.Thread(
            target=self.participant.call_tool,
            kwargs={"turn_id": "t1", "tool": "emoji", "arguments": {"target_event_id": "e1", "reaction": "👍"}},
            daemon=True,
        )
        reacting.start()
        self.assertTrue(turn.action_ready.wait(5))
        self.assertEqual("silent", self.participant.finish(turn_id="t1", answer="(empty)").kind)
        self.thread.join(5)
        self.assertEqual("reaction", self.box["ok"]["kind"])

    def test_a_harness_text_holding_a_secret_is_not_quoted(self):
        turn = self.open_turn()
        self.participant.model_wrote(turn_id="t1", text="Checking.")
        self.participant.finish(turn_id="t1", answer="Error: a-withheld-secret-value was rejected")
        self.assertNotIn("a-withheld-secret-value", turn.unattributed)
        self.assertNotIn("a-withheld-secret-value", str(self.end()["error"]))

    def test_a_report_for_another_run_is_not_kept(self):
        turn = self.open_turn()
        self.assertFalse(self.participant.model_wrote(turn_id="other", text="On it."))
        self.assertEqual([], turn.written)
        self.assertEqual(0, turn.model_reports)

    def test_model_text_needs_final_answer_posting(self):
        with self.assertRaises(ValueError):
            TurnParticipant(
                profile=PROFILE, driver=RecordingDriver(), guard=SecretGuard(()), tool_names=NAMES, model_text=True
            )

    def test_without_model_text_the_answer_is_not_checked(self):
        participant = TurnParticipant(
            profile=PROFILE,
            driver=RecordingDriver(),
            guard=SecretGuard(()),
            tool_names=NAMES,
            silence_marker="[SILENT]",
        )
        self.assertFalse(participant.model_text)
        from nunchi.participant_model import build_participant_turn_request
        from nunchi.turn import Turn

        turn = Turn(
            profile=PROFILE,
            request=build_participant_turn_request(test_wake(), deepcopy(OPPORTUNITY)),
            silence_marker="[SILENT]",
        )
        self.assertEqual("deliver", turn.decide("(empty)").kind)


class HarnessHostedFinalAnswerTests(unittest.TestCase):
    """A harness that posts its agent's answer itself, through the library's turn."""

    def test_the_answer_goes_out_after_the_hosts_commit(self):
        from nunchi.turn import HARNESS_DELIVERS, HarnessDelivery

        driver = RecordingDriver()
        participant = TurnParticipant(
            profile=PROFILE,
            driver=driver,
            guard=SecretGuard(()),
            tool_names=NAMES,
            result_wait_seconds=5,
            silence_marker="[SILENT]",
        )
        box = {}
        cancel = threading.Event()
        thread = threading.Thread(
            target=lambda: box.setdefault(
                "action",
                participant.run_protocol(
                    wake=test_wake(), opportunity=deepcopy(OPPORTUNITY), expand=Room().expand, cancel=cancel
                ),
            ),
            daemon=True,
        )
        thread.start()
        self.assertTrue(driver.started_event.wait(5))
        turn = driver.started[0]
        self.assertNotIn("send", turn.tool_names)
        self.assertTrue(participant.bind_turn(turn_id="t1", wake_id=turn.wake_id))
        answer = {}
        finishing = threading.Thread(
            target=lambda: answer.setdefault("finish", participant.finish(turn_id="t1", answer="On it.")),
            daemon=True,
        )
        finishing.start()
        thread.join(5)
        self.assertEqual("message", box["action"]["kind"])
        # The host commits the message for the harness to post.
        result = HarnessDelivery(room_shows_own_messages=False).dispatch(action=box["action"], wake=test_wake())
        self.assertEqual(TransportResult("unknown", HARNESS_DELIVERS), result)
        participant.settle(turn.request_id, result)
        finishing.join(5)
        self.assertEqual(("deliver", "On it."), (answer["finish"].kind, answer["finish"].text))
        self.assertEqual("silent", participant.finish(turn_id="other", answer="hi").kind)

    def test_without_a_native_transport_only_messages_are_offered(self):
        from nunchi.reactions import UNAVAILABLE_REACTION_CAPABILITY
        from nunchi.turn import HarnessDelivery

        delivery = HarnessDelivery(room_shows_own_messages=False)
        self.assertEqual(["message"], delivery.ordinary_action_capabilities())
        self.assertIs(UNAVAILABLE_REACTION_CAPABILITY, delivery.reaction_capability())
        self.assertEqual(
            "unavailable",
            delivery.dispatch(action={"kind": "reaction"}, wake=test_wake()).delivery,
        )


class PlainReplyParticipantTests(unittest.TestCase):
    """The model participant whose plain reply is its post drives the same Turn."""

    def participant(self, replies):
        from nunchi.participant_model import OpenAICompatibleParticipant

        class Scripted(OpenAICompatibleParticipant):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.sent = []

            def _complete(self, messages, *, json_reply):
                self.sent.append((deepcopy(messages), json_reply))
                return replies.pop(0)

        return Scripted(
            profile=PROFILE,
            model="m",
            api_key="k",
            base_url="http://localhost",
            silence_marker="[SILENT]",
        )

    def play(self, participant, room=None):
        return participant.run_protocol(
            wake=test_wake(),
            opportunity=deepcopy(OPPORTUNITY),
            expand=(room or Room()).expand,
            cancel=threading.Event(),
        )

    def test_a_reply_is_the_post_and_the_marker_is_silence(self):
        speaker = self.participant(["On it."])
        self.assertEqual(
            {"kind": "message", "origin_event_id": "e1", "text": "On it."}, self.play(speaker)
        )
        messages, json_reply = speaker.sent[0]
        self.assertFalse(json_reply)
        self.assertEqual(["user"], [message["role"] for message in messages])
        self.assertIn("put exactly [SILENT] outside it", messages[0]["content"])
        self.assertIsNone(self.play(self.participant(["[SILENT] (nothing to add)"])))
        self.assertEqual(
            {"kind": "silence", "why": "Castor was asked."},
            self.play(self.participant(["<thinking>Castor was asked.</thinking>[SILENT]"])),
        )

    def test_it_replies_again_after_looking_again(self):
        room = Room()
        room.arrivals = [message("e2", "never mind")]
        speaker = self.participant(["On it.", "[SILENT]"])
        self.assertIsNone(self.play(speaker, room))
        messages, _ = speaker.sent[1]
        self.assertEqual(["user", "assistant", "user"], [message["role"] for message in messages])
        self.assertIn("never mind", messages[2]["content"])


    def test_a_guard_refuses_a_reply_with_a_secret_and_the_model_answers_again(self):
        speaker = self.participant(["The key is a-withheld-secret-value", "I can't share that."])
        speaker.guard = SecretGuard(["a-withheld-secret-value"])
        self.assertEqual(
            {"kind": "message", "origin_event_id": "e1", "text": "I can't share that."}, self.play(speaker)
        )
        messages, _ = speaker.sent[1]
        self.assertIn("credential or secret", messages[2]["content"])

    def test_the_one_reply_style_gets_the_guard_too(self):
        from nunchi.participant_model import OpenAICompatibleParticipant

        replies = []

        class Scripted(OpenAICompatibleParticipant):
            def _invoke(self, protocol):
                # What the model saw: a refusal note after the first reply.
                replies.append([page.get("note") for page in protocol.pages])
                text = "a-withheld-secret-value" if len(replies) == 1 else "I can't share that."
                return {
                    "protocol": protocol.request["protocol"],
                    "binding": {"request_id": protocol.request_id},
                    "action": {"kind": "message", "origin_event_id": "e1", "text": text},
                }

        speaker = Scripted(
            profile=PROFILE,
            model="m",
            api_key="the-participants-own-key",
            base_url="http://localhost",
            guard=SecretGuard(["a-withheld-secret-value"]),
        )
        self.assertEqual(("the-participants-own-key",), speaker.withheld_values())
        self.assertEqual(
            {"kind": "message", "origin_event_id": "e1", "text": "I can't share that."}, self.play(speaker)
        )
        self.assertEqual(2, len(replies))
        self.assertIn("credential or secret", replies[1][-1])


class LocalTurnProtocolTests(unittest.TestCase):
    """I-040D: the same turn as versioned JSON over a private socket."""

    def setUp(self):
        import tempfile
        from pathlib import Path

        from nunchi.turn_server import TurnServer

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.socket_path = Path(directory.name) / "turns" / "turn.sock"
        self.secret = "a-launch-secret-for-this-test"
        self.driver = RecordingDriver()
        self.room = Room()

    def serve(self, **participant):
        from nunchi.turn_server import TurnServer

        self.participant = TurnParticipant(
            profile=PROFILE,
            driver=self.driver,
            guard=SecretGuard(()),
            tool_names=NAMES,
            result_wait_seconds=5,
            **participant,
        )
        server = TurnServer(self.participant, socket_path=self.socket_path, session_secret=self.secret)
        server.start()
        self.addCleanup(server.close)

    def post(self, path, body, secret=None):
        from tests.v2.test_claude_code import gate_post

        return gate_post(self.socket_path, path, body, self.secret if secret is None else secret)

    def open_turn(self):
        self.box = {}
        cancel = threading.Event()
        self.addCleanup(cancel.set)
        threading.Thread(
            target=lambda: self.box.setdefault(
                "action",
                self.participant.run_protocol(
                    wake=test_wake(), opportunity=deepcopy(OPPORTUNITY), expand=self.room.expand, cancel=cancel
                ),
            ),
            daemon=True,
        ).start()
        self.assertTrue(self.driver.started_event.wait(5))
        return self.driver.started[0]

    def test_attach_names_the_protocol_the_posting_style_and_the_tools(self):
        self.serve()
        self.assertEqual(401, self.post("/v1/attach", {}, secret="wrong")[0])
        status, body = self.post("/v1/attach", {})
        self.assertEqual(200, status)
        self.assertEqual(
            ("nunchi.turn-session", 2, "tools", None, False),
            (body["protocol"], body["version"], body["posting"], body["silence_marker"], body["model_text"]),
        )
        self.assertEqual(["say", "emoji", "ask_operator", "take_back", "look"], [tool["name"] for tool in body["tools"]])
        self.assertTrue(self.participant.attached)

    def test_a_tool_turn_binds_calls_steers_and_ends(self):
        self.serve()
        turn = self.open_turn()
        self.assertEqual({"bound": True}, self.post("/v1/turn/bind", {"turn_id": "t1", "wake_id": turn.wake_id})[1])
        self.room.arrivals = [message("e2", "use staging")]
        status, update = self.post("/v1/turn/after-tool", {"turn_id": "t1"})
        self.assertIn("use staging", update["text"])
        self.assertEqual({"ended": False}, self.post("/v1/turn/end", {"turn_id": "nope", "ok": True})[1])
        self.assertEqual(
            {"ended": True},
            self.post("/v1/turn/end", {"turn_id": "t1", "ok": True, "detail": "done", "note": "Nothing to add."})[1],
        )
        for _ in range(100):
            if "action" in self.box:
                break
            threading.Event().wait(0.05)
        # The agent's last words are the silence's reason.
        self.assertEqual({"action": {"kind": "silence", "why": "Nothing to add."}}, self.box)

    def test_the_first_integrations_route_names_still_work(self):
        self.serve()
        turn = self.open_turn()
        self.assertEqual({"bound": True}, self.post("/v1/turn-start", {"turn_id": "t1", "wake_id": turn.wake_id})[1])
        self.assertEqual({"text": None}, self.post("/v1/news", {"turn_id": "t1"})[1])
        answer = {}
        threading.Thread(
            target=lambda: answer.setdefault(
                "body", self.post("/v1/tool", {"turn_id": "t1", "tool": "say", "input": {"text": "on it"}})[1]
            ),
            daemon=True,
        ).start()
        self.assertTrue(turn.action_ready.wait(5))
        self.participant.settle(turn.request_id, TransportResult("sent", "ok"))
        for _ in range(100):
            if "body" in answer:
                break
            threading.Event().wait(0.05)
        self.assertEqual({"ok": True, "text": "Done: the room accepted this action."}, answer["body"])

    def test_a_final_answer_turn_finishes_over_the_socket(self):
        from nunchi.turn import HARNESS_DELIVERS

        self.serve(silence_marker="[SILENT]")
        status, body = self.post("/v1/attach", {})
        self.assertEqual(("final-answer", "[SILENT]"), (body["posting"], body["silence_marker"]))
        self.assertNotIn("say", [tool["name"] for tool in body["tools"]])
        turn = self.open_turn()
        self.post("/v1/turn/bind", {"turn_id": "t1", "wake_id": turn.wake_id})
        self.assertEqual({"finish": "silent", "text": ""}, self.post("/v1/turn/finish", {"turn_id": "t1", "answer": "[SILENT]"})[1])
        answer = {}
        threading.Thread(
            target=lambda: answer.setdefault(
                "body", self.post("/v1/turn/finish", {"turn_id": "t1", "answer": "On it."})[1]
            ),
            daemon=True,
        ).start()
        self.assertTrue(turn.action_ready.wait(5))
        self.participant.settle(turn.request_id, TransportResult("unknown", HARNESS_DELIVERS))
        for _ in range(100):
            if "body" in answer:
                break
            threading.Event().wait(0.05)
        self.assertEqual({"finish": "deliver", "text": "On it."}, answer["body"])

    def test_finish_is_refused_for_a_participant_that_posts_through_tools(self):
        self.serve()
        self.assertIn("error", self.post("/v1/turn/finish", {"turn_id": "t1", "answer": "hi"})[1])

    def test_attach_says_the_integration_must_report_what_the_model_wrote(self):
        self.serve(silence_marker="[SILENT]", model_text=True)
        status, body = self.post("/v1/attach", {})
        self.assertEqual((200, True), (status, body["model_text"]))

    def test_model_text_over_the_socket_lets_only_the_models_words_post(self):
        from nunchi.turn import HARNESS_DELIVERS

        self.serve(silence_marker="[SILENT]", model_text=True)
        box, thread, cancel = run_in_thread(self.participant, self.room)
        self.addCleanup(cancel.set)
        self.assertTrue(self.driver.started_event.wait(5))
        turn = self.driver.started[0]
        self.post("/v1/turn/bind", {"turn_id": "t1", "wake_id": turn.wake_id})
        self.assertEqual({"kept": False}, self.post("/v1/turn/model-text", {"turn_id": "other", "text": "hi"})[1])
        self.assertIn("error", self.post("/v1/turn/model-text", {"turn_id": "t1", "text": 7})[1])
        self.assertIn("error", self.post("/v1/turn/model-text", {"turn_id": "t1", "text": "hi", "reasoning": "yes"})[1])
        self.assertEqual({"kept": True}, self.post("/v1/turn/model-text", {"turn_id": "t1", "text": "On it."})[1])
        answer = {}
        threading.Thread(
            target=lambda: answer.setdefault(
                "body", self.post("/v1/turn/finish", {"turn_id": "t1", "answer": "On it."})[1]
            ),
            daemon=True,
        ).start()
        self.assertTrue(turn.action_ready.wait(5))
        self.participant.settle(turn.request_id, TransportResult("unknown", HARNESS_DELIVERS))
        thread.join(5)
        self.assertTrue(wait_until(lambda: "body" in answer))
        self.assertEqual({"finish": "deliver", "text": "On it."}, answer["body"])
        self.assertEqual("On it.", box["ok"]["text"])

    def test_the_harnesss_own_text_over_the_socket_fails_the_turn_and_says_why(self):
        self.serve(silence_marker="[SILENT]", model_text=True)
        box, thread, cancel = run_in_thread(self.participant, self.room)
        self.addCleanup(cancel.set)
        self.assertTrue(self.driver.started_event.wait(5))
        turn = self.driver.started[0]
        self.post("/v1/turn/bind", {"turn_id": "t1", "wake_id": turn.wake_id})
        self.post("/v1/turn/model-text", {"turn_id": "t1", "text": ""})
        # Reasoning is reported apart; the stand-in is not a word inside it.
        self.assertEqual({"kept": True}, self.post(
            "/v1/turn/model-text", {"turn_id": "t1", "text": "The log is empty.", "reasoning": True})[1])
        status, body = self.post("/v1/turn/finish", {"turn_id": "t1", "answer": "(empty)"})
        self.assertEqual(("silent", ""), (body["finish"], body["text"]))
        self.assertIn('"(empty)": no reported model response holds this text', body["failed"])
        self.post("/v1/turn/end", {"turn_id": "t1", "ok": True})
        thread.join(5)
        self.assertIsInstance(box["error"], TurnError)

    def test_a_harness_that_declares_model_text_and_never_reports_fails_loudly(self):
        self.serve(silence_marker="[SILENT]", model_text=True)
        box, thread, cancel = run_in_thread(self.participant, self.room)
        self.addCleanup(cancel.set)
        self.assertTrue(self.driver.started_event.wait(5))
        turn = self.driver.started[0]
        self.post("/v1/turn/bind", {"turn_id": "t1", "wake_id": turn.wake_id})
        body = self.post("/v1/turn/finish", {"turn_id": "t1", "answer": "On it."})[1]
        self.assertEqual("silent", body["finish"])
        self.assertIn("reported nothing its model wrote", body["failed"])
        self.post("/v1/turn/end", {"turn_id": "t1", "ok": True})
        thread.join(5)
        self.assertIn("declared model_text", str(box["error"]))

    def test_model_text_is_refused_for_a_participant_that_posts_through_tools(self):
        self.serve()
        self.assertIn("error", self.post("/v1/turn/model-text", {"turn_id": "t1", "text": "hi"})[1])

    def test_the_launch_secret_is_refused_on_a_tool_call(self):
        self.serve()
        turn = self.open_turn()
        self.post("/v1/turn/bind", {"turn_id": "t1", "wake_id": turn.wake_id})
        status, body = self.post(
            "/v1/turn/call",
            {"turn_id": "t1", "tool": "say", "input": {"text": f"NUNCHI_SESSION={self.secret}"}},
        )
        self.assertEqual(200, status)
        self.assertFalse(body["ok"])
        self.assertIn("secret", body["error"])
        # Nothing reached the host, and the agent can still post.
        self.assertFalse(turn.action_ready.is_set())
        answer = {}
        threading.Thread(
            target=lambda: answer.setdefault(
                "body", self.post("/v1/turn/call", {"turn_id": "t1", "tool": "say", "input": {"text": "on it"}})[1]
            ),
            daemon=True,
        ).start()
        self.assertTrue(turn.action_ready.wait(5))
        self.assertEqual("on it", turn.action["text"])

    def test_a_final_answer_with_the_launch_secret_answers_again(self):
        self.serve(silence_marker="[SILENT]")
        turn = self.open_turn()
        self.post("/v1/turn/bind", {"turn_id": "t1", "wake_id": turn.wake_id})
        status, body = self.post("/v1/turn/finish", {"turn_id": "t1", "answer": f"my session: {self.secret}"})
        self.assertEqual("continue", body["finish"])
        self.assertIn("credential or secret", body["text"])
        self.assertNotIn(self.secret, body["text"])
        self.assertFalse(turn.action_ready.is_set())

    def test_the_server_leaves_the_guard_it_was_given_and_refuses_a_short_secret(self):
        from nunchi.turn_server import TurnServer

        given = SecretGuard(())
        participant = TurnParticipant(profile=PROFILE, driver=self.driver, guard=given, tool_names=NAMES)
        TurnServer(participant, socket_path=self.socket_path, session_secret=self.secret)
        self.assertIsNone(given.refusal({"kind": "message", "text": self.secret}))
        self.assertIsNotNone(participant.guard.refusal({"kind": "message", "text": self.secret}))
        for short in ("ten-chars!", "", "fifteen-chars!!"):
            with self.subTest(short), self.assertRaises(ValueError):
                TurnServer(participant, socket_path=self.socket_path, session_secret=short)
