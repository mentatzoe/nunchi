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
            ("nunchi.turn-session", 1, "tools", None),
            (body["protocol"], body["version"], body["posting"], body["silence_marker"]),
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
        self.assertEqual({"ended": True}, self.post("/v1/turn/end", {"turn_id": "t1", "ok": True, "detail": "done"})[1])
        for _ in range(100):
            if "action" in self.box:
                break
            threading.Event().wait(0.05)
        self.assertEqual({"action": None}, self.box)

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
