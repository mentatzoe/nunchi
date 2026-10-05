"""The participant sees the room as it is now, and looks again before speaking.

Zoe, 2026-10-05 (#94, plan step 3): the context the gate reads to decide and
the history the agent reads during its own turn are separate things. The
agent's view reads the live room, including messages that arrived after its
turn began, never fails the turn, and shows messages, not verdicts. Before
its first post or reaction goes out, it is shown anything others said while
it was composing, once, and decides again.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from nunchi.observation import ObservationLimits
from nunchi.participant import RoomView
from nunchi.participant_model import (
    ParticipantTurnProtocol,
    participant_tool_turn_prompt,
    participant_turn_prompt,
)
from tests.v2.test_operator_protocol import PROFILE, opportunity, wake
from tests.v2.test_shared_foundation import foundation, message


ZOE = {"human:zoe": {"kind": "human"}}


def observe(pipeline, event_id, **extra):
    extra.setdefault("text", f"message {event_id}")
    pipeline.observation.observe(
        delivery_id=f"d-{event_id}",
        event=message(event_id, **extra),
        actors=ZOE,
    )


class ReadRoomTests(unittest.TestCase):
    def setUp(self):
        self.pipeline, _, _, _ = foundation()
        self.observation = self.pipeline.observation
        for index in range(1, 6):
            observe(self.pipeline, f"e{index}")

    def read(self, direction, anchor="e3", seen=("e3",), **kwargs):
        options = {"since_arrival": 0, "max_events": 12, "max_bytes": 16_384}
        options.update(kwargs)
        return self.observation.read_room(
            direction=direction, anchor_event_id=anchor, seen_event_ids=set(seen), **options
        )

    def ids(self, page):
        return [event["id"] for event in page["events"]]

    def test_before_after_and_around_skip_what_was_seen(self):
        self.assertEqual(["e1", "e2"], self.ids(self.read("before")))
        self.assertEqual(["e4", "e5"], self.ids(self.read("after")))
        self.assertEqual(["e2", "e4"], self.ids(self.read("around", max_events=2)))
        self.assertEqual(["e1"], self.ids(self.read("before", seen=("e2", "e3"))))

    def test_asking_again_pages_further_and_says_when_nothing_is_left(self):
        page = self.read("before", max_events=1)
        self.assertEqual((["e2"], True), (self.ids(page), page["has_next_page"]))
        page = self.read("before", seen=("e2", "e3"), max_events=1)
        self.assertEqual((["e1"], False), (self.ids(page), page["has_next_page"]))
        page = self.read("before", seen=("e1", "e2", "e3"))
        self.assertEqual(([], "There are no older messages."), (page["events"], page["note"]))

    def test_new_is_what_others_posted_after_the_mark(self):
        mark = self.observation.arrival_mark()
        observe(self.pipeline, "e6")
        self.observation.observe(
            delivery_id="d-own",
            event=message("own", author_id=self.observation.binding.actor_id),
            actors={},
        )
        page = self.read("new", anchor=None, since_arrival=mark)
        self.assertEqual(["e6"], self.ids(page))
        self.assertNotIn("anchor_event_id", page)
        page = self.read("new", anchor=None, seen=("e6",), since_arrival=mark)
        self.assertEqual("Nobody else has posted since you last looked.", page["note"])

    def test_a_late_message_with_an_earlier_time_is_still_new(self):
        mark = self.observation.arrival_mark()
        observe(self.pipeline, "late", timestamp="2000-01-01T00:00:00.000Z")
        self.assertEqual(["late"], self.ids(self.read("new", anchor=None, since_arrival=mark)))

    def test_a_forked_view_reads_the_same_turn_afresh(self):
        mark = self.observation.arrival_mark()
        observe(self.pipeline, "e6")
        wake = {"request_id": "r1", "trigger_event_id": "e3", "events": [{"id": "e3"}]}
        view = RoomView(self.observation, wake, turn_began=mark, guard=lambda: None)
        self.assertEqual(["e6"], self.ids(view.expand(direction="new")))
        self.assertEqual(["e1", "e2"], self.ids(view.expand(direction="before")))
        self.assertEqual(([], 1, 1), (view.expand(direction="new")["events"], view.expansion_calls, view.new_checks - 1))
        fork = view.fork()
        self.assertEqual((0, 0, {"e3"}), (fork.expansion_calls, fork.new_checks, fork.seen_event_ids))
        self.assertEqual(["e6"], self.ids(fork.expand(direction="new")))
        self.assertEqual(["e1", "e2"], self.ids(fork.expand(direction="before")))
        self.assertIn("e6", view.seen_event_ids)

    def test_a_page_never_fails(self):
        self.assertIn("no longer in the room's retained history", self.read("before", anchor="gone")["note"])
        self.assertIn("Unknown direction", self.read("sideways")["note"])

    def test_requests_are_held_to_the_room_limits(self):
        page = self.read("after", max_events=10_000, max_bytes=10_000_000)
        self.assertLessEqual(len(page["events"]), self.observation.limits.continuation_events)

    def test_evicted_history_is_reported(self):
        pipeline, _, _, _ = foundation(limits=ObservationLimits(retention_events=3))
        for index in range(1, 6):
            observe(pipeline, f"e{index}")
        page = pipeline.observation.read_room(
            direction="before",
            anchor_event_id="e3",
            seen_event_ids={"e3"},
            since_arrival=0,
            max_events=12,
            max_bytes=16_384,
        )
        self.assertEqual("No older messages are retained.", page["note"])


class HostRoomViewTests(unittest.TestCase):
    def test_asking_for_history_in_a_short_room_never_fails_the_turn(self):
        pages = []

        def participant(*, wake, expand, **_):
            pages.append(expand(direction="before"))
            return None

        pipeline, _, transport, receipts = foundation(participant=participant)
        outcome = pipeline.handle_delivery(delivery_id="d-e1", event=message("e1"), actors=ZOE)
        opportunity = outcome.opportunities[0]
        self.assertIsNone(opportunity.transport)
        self.assertEqual("There are no older messages.", pages[0]["note"])
        self.assertEqual("silent", receipts.records(opportunity.request_id)[2]["body"]["outcome"])

    def test_a_message_that_arrives_mid_turn_is_visible_and_can_be_answered(self):
        seen = {}

        def participant(*, wake, expand, **_):
            observe(pipeline, "e2", text="Castor: it was the expired cert.")
            seen["new"] = expand(direction="new")
            seen["after"] = expand(direction="after")
            return {
                "kind": "reply",
                "origin_event_id": wake["trigger_event_id"],
                "target_event_id": "e2",
                "text": "Thanks, that matches what I saw.",
            }

        pipeline, _, transport, _ = foundation(participant=participant)
        pipeline.handle_delivery(delivery_id="d-e1", event=message("e1"), actors=ZOE)
        self.assertEqual(["e2"], [event["id"] for event in seen["new"]["events"]])
        # Already seen through "new", so "after" has nothing to repeat.
        self.assertEqual([], seen["after"]["events"])
        self.assertEqual("e2", transport.calls[0][0]["target_event_id"])


class LookAgainTests(unittest.TestCase):
    """The shared protocol looks again before the first post, once."""

    def setUp(self):
        self.protocol = ParticipantTurnProtocol(profile=PROFILE, wake=wake(), opportunity=opportunity())
        self.calls = []

    def envelope(self, action):
        return {
            "protocol": deepcopy(self.protocol.request["protocol"]),
            "binding": deepcopy(self.protocol.request["binding"]),
            "action": action,
        }

    def host(self, *new_pages):
        pages = list(new_pages)

        def expand(**kwargs):
            self.calls.append(kwargs)
            if kwargs["direction"] == "new" and pages:
                return pages.pop(0)
            return {"events": []}

        return expand

    def test_a_post_is_held_once_when_others_spoke_meanwhile(self):
        newer = {"events": [{"id": "e9", "type": "message", "author_id": "human:castor", "text": "Cert expired."}]}
        expand = self.host(newer, newer)
        first = {"kind": "message", "origin_event_id": "e1", "text": "Looking into the deploy."}
        done, action = self.protocol.consume(self.envelope(first), expand=expand)
        self.assertEqual((False, None), (done, action))
        page = self.protocol.pages[-1]
        self.assertIn("Not posted yet: 1 new message(s)", page["note"])
        self.assertIn("Looking into the deploy.", page["note"])
        self.assertIn("e9", self.protocol.visible_event_ids)
        second = {"kind": "reply", "origin_event_id": "e1", "target_event_id": "e9", "text": "Thanks, Castor."}
        done, action = self.protocol.consume(self.envelope(second), expand=expand)
        self.assertEqual((True, second), (done, action))
        self.assertEqual(["new"], [call["direction"] for call in self.calls])

    def test_a_new_reaction_alone_does_not_hold_the_post(self):
        reaction = {"events": [{"id": "r9", "type": "reaction", "author_id": "human:castor", "target_event_id": "e1"}]}
        action = {"kind": "message", "origin_event_id": "e1", "text": "On it."}
        done, returned = self.protocol.consume(self.envelope(action), expand=self.host(reaction))
        self.assertEqual((True, action), (done, returned))

    def test_nothing_new_means_the_post_goes_out(self):
        action = {"kind": "message", "origin_event_id": "e1", "text": "On it."}
        done, returned = self.protocol.consume(self.envelope(action), expand=self.host())
        self.assertEqual((True, action), (done, returned))
        self.assertEqual([{"direction": "new", "max_events": 12, "max_bytes": 16_384}], self.calls)

    def test_silence_never_looks_again(self):
        done, action = self.protocol.consume(self.envelope({"kind": "silence"}), expand=self.host())
        self.assertEqual((True, None), (done, action))
        self.assertEqual([], self.calls)

    def test_the_new_direction_is_part_of_the_protocol(self):
        request = {"kind": "expand", "direction": "new", "max_events": 5, "max_bytes": 2048}
        done, action = self.protocol.consume(self.envelope(request), expand=self.host())
        self.assertEqual((False, None), (done, action))
        self.assertEqual("new", self.calls[0]["direction"])

    def test_the_prompts_offer_history_and_say_the_post_waits(self):
        turn = participant_turn_prompt(PROFILE)
        self.assertIn("or new (what others posted since you last looked)", turn)
        self.assertIn("you are shown anything others posted while you were composing", turn)
        self.assertNotIn("When coverage says more context exists", turn)
        tool = participant_tool_turn_prompt(PROFILE, tools={"send": "send", "context": "context"})
        self.assertIn("context shows the room as it is now", tool)
        self.assertIn("your first post or reaction is not sent", tool)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
