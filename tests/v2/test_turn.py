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
