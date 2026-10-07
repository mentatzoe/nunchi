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
        for answer in ("[SILENT]", "  [SILENT]\n\nNothing to add here.", "[silent]", "", None):
            with self.subTest(answer=answer):
                turn = self.turn()
                self.assertEqual("silent", turn.decide(answer).kind)
                self.assertIsNone(turn.action)

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
        self.assertIn("reply with exactly [SILENT]", text)
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
        result = HarnessDelivery().dispatch(action=box["action"], wake=test_wake())
        self.assertEqual(TransportResult("unknown", HARNESS_DELIVERS), result)
        participant.settle(turn.request_id, result)
        finishing.join(5)
        self.assertEqual(("deliver", "On it."), (answer["finish"].kind, answer["finish"].text))
        self.assertEqual("silent", participant.finish(turn_id="other", answer="hi").kind)

    def test_without_a_native_transport_only_messages_are_offered(self):
        from nunchi.reactions import UNAVAILABLE_REACTION_CAPABILITY
        from nunchi.turn import HarnessDelivery

        delivery = HarnessDelivery()
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
        self.assertIn("reply with exactly [SILENT]", messages[0]["content"])
        self.assertIsNone(self.play(self.participant(["[SILENT] (nothing to add)"])))

    def test_it_replies_again_after_looking_again(self):
        room = Room()
        room.arrivals = [message("e2", "never mind")]
        speaker = self.participant(["On it.", "[SILENT]"])
        self.assertIsNone(self.play(speaker, room))
        messages, _ = speaker.sent[1]
        self.assertEqual(["user", "assistant", "user"], [message["role"] for message in messages])
        self.assertIn("never mind", messages[2]["content"])
