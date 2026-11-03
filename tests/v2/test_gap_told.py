"""Obsolete: tests the design under architecture review, in which Nunchi runs the agent's turn and sends for it. Not a requirement for the new design.

A continuity gap is a point in the room's timeline, told once in one plain sentence.

Agreed, 2026-10-10: "A plain sentence at the gap." When what the agent reads runs
up to or across a gap it has not been told about, the turn says so, attention's
judgment sees the same fact, and once the agent has taken a turn past it, it
is no longer news. The library does this, so every harness gets it through the
same interfaces.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nunchi.attention import participant_attention_prompt
from nunchi.attention_questions import attention_state
from nunchi.errors import ValidationError
from nunchi.gaps import gap_sentence, gap_sentence_in, gap_times, not_listening_note
from nunchi.observation import (
    MAX_GAPS,
    ObservationLimits,
    ObservationProvider,
    ParticipantBinding,
)
from nunchi.participant_model import (
    build_participant_turn_request,
    gap_turn_note,
    participant_tool_turn_text,
    participant_turn_instructions,
    participant_turn_text,
)
from nunchi.receipts import PersistenceError
from nunchi.turn import SecretGuard, Turn
from nunchi.v2_contracts import validate_attention_request, validate_participant_wake
from tests.v2.test_shared_foundation import FixtureModel, foundation, message

BINDING = ParticipantBinding(
    participant_id="vigil",
    actor_id="discord:bot:9",
    platform="discord",
    room_id="42",
    continuity_scope_id="discord:channel:42",
    names=("Vigil",),
)
ACTORS = {"human:alice": {"kind": "human"}}
START = datetime(2026, 10, 10, 14, 0, 0, tzinfo=timezone.utc)
# What the agent reads, whatever the harness.
SENTENCE = "Messages may be missing before 14:02 UTC; read the history if it matters."
OPPORTUNITY = {
    "generation": 1,
    "lifecycle_id": "gap-test",
    "deadline_id": "gap-test",
    "permissions": {
        "revision": "gap-test",
        "ordinary_actions": ["message", "reply", "reaction"],
        "privileged_proposals": False,
    },
}


class Clock:
    """The room's clock, moved by the test."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


def provider(clock: Clock | None = None, path: Path | None = None, **kwargs) -> ObservationProvider:
    return ObservationProvider(BINDING, clock=clock or Clock(), persistence_path=path, **kwargs)


def hear(observation: ObservationProvider, *numbers: int) -> None:
    for number in numbers:
        observation.observe(delivery_id=f"d{number}", event=message(f"e{number}"), actors=ACTORS)


def declare(observation: ObservationProvider, name: str = "g") -> None:
    observation.mark_continuity_gap(delivery_id=name, detail="the connection was lost")


def at_two_past(clock: Clock) -> None:
    """Move the room's clock to 14:02 UTC, where the tests' gap is declared."""

    clock.now = START + timedelta(minutes=2)


class GapSentenceTests(unittest.TestCase):
    def test_the_sentence_names_the_time_in_utc_and_says_to_read_the_history(self):
        self.assertEqual(SENTENCE, gap_sentence(["2026-10-10T14:02:00.000Z"], "2026-10-10T15:30:00.000Z"))

    def test_a_gap_from_another_day_names_its_date_and_so_does_a_reading_without_a_time(self):
        self.assertEqual(
            "Messages may be missing before 2026-10-09 23:58 UTC; read the history if it matters.",
            gap_sentence(["2026-10-09T23:58:00.000Z"], "2026-10-10T00:10:00.000Z"),
        )
        self.assertIn("before 2026-10-10 14:02 UTC", gap_sentence(["2026-10-10T14:02:00.000Z"]))
        self.assertIn("before 2026-10-10 14:02 UTC", gap_sentence(["2026-10-10T14:02:00.000Z"], "not a time"))

    def test_several_gaps_are_one_sentence_in_time_order_each_named_once(self):
        said = gap_sentence(
            ["2026-10-10T14:40:00.000Z", "2026-10-10T13:10:00.000Z", "2026-10-10T14:40:00.000Z"],
            "2026-10-10T15:00:00.000Z",
        )
        self.assertEqual("Messages may be missing before 13:10 UTC and before 14:40 UTC; read the history if it matters.", said)
        self.assertEqual(1, said.count("."))
        three = gap_sentence(
            ["2026-10-10T12:00:00Z", "2026-10-10T13:00:00Z", "2026-10-10T14:00:00Z"], "2026-10-10T15:00:00Z"
        )
        self.assertIn("before 12:00 UTC, before 13:00 UTC and before 14:00 UTC;", three)

    def test_gaps_in_one_minute_are_said_once(self):
        # Two points seconds apart, or a millisecond apart, read the same on the clock.
        for times in (
            ["2026-10-10T14:02:10.000Z", "2026-10-10T14:02:40.000Z"],
            ["2026-10-10T14:02:10.000Z", "2026-10-10T14:02:10.001Z"],
        ):
            with self.subTest(times=times):
                self.assertEqual(SENTENCE, gap_sentence(times, "2026-10-10T15:30:00.000Z"))
        said = gap_sentence(
            [
                "2026-10-10T14:20:30.000Z", "2026-10-10T14:02:10.000Z",
                "2026-10-10T14:20:00.000Z", "2026-10-10T14:02:40.000Z",
            ],
            "2026-10-10T15:00:00.000Z",
        )
        self.assertEqual(
            "Messages may be missing before 14:02 UTC and before 14:20 UTC; read the history if it matters.", said
        )

    def test_where_nunchi_was_not_listening_the_note_says_so_in_the_same_clock(self):
        self.assertEqual(
            "Nunchi has no older messages: it was not listening before 14:00 UTC.",
            not_listening_note(["2026-10-10T14:00:00.000Z"], "2026-10-10T15:30:00.000Z"),
        )
        self.assertIn("before 2026-10-09 23:58 UTC", not_listening_note(["2026-10-09T23:58:00.000Z"], "2026-10-10T00:10:00.000Z"))
        self.assertEqual("", not_listening_note([], "2026-10-10T15:30:00.000Z"))
        self.assertEqual("", not_listening_note(["yesterday"], "2026-10-10T15:30:00.000Z"))

    def test_no_gap_is_no_sentence(self):
        for times in ([], ["", "yesterday", "2026-10-10T14:02:00"]):
            with self.subTest(times=times):
                self.assertEqual("", gap_sentence(times, "2026-10-10T15:00:00Z"))

    def test_a_document_is_read_for_its_gaps_and_its_own_time(self):
        document = {"coverage": {"gaps": [{"at": "2026-10-10T14:02:00.000Z"}]}, "pace": {"now": "2026-10-10T16:00:00.000Z"}}
        self.assertEqual(["2026-10-10T14:02:00.000Z"], gap_times(document["coverage"]))
        self.assertEqual(SENTENCE, gap_sentence_in(document))
        for none in ({}, {"coverage": {}}, {"coverage": {"gaps": "x"}}, None, "x"):
            with self.subTest(none=none):
                self.assertEqual("", gap_sentence_in(none))


class GapPointTests(unittest.TestCase):
    def test_a_gap_is_a_point_with_a_time_and_a_place_in_the_arrival_order(self):
        clock = Clock()
        observation = provider(clock)
        hear(observation, 1, 2)
        self.assertEqual((), observation.gaps_pending())
        at_two_past(clock)
        result = observation.mark_continuity_gap(delivery_id="gap-1", detail="the connection was lost")
        self.assertEqual("continuity-gap", result.audit.outcome)
        self.assertFalse(result.wake_eligible)
        hear(observation, 3)
        # No event was made up for it, and the point is where it was declared.
        self.assertEqual(["e1", "e2", "e3"], [event["id"] for event in observation.retained_events()])
        self.assertEqual(("2026-10-10T14:02:00.000Z",), observation.gaps_pending())
        coverage = observation.build_snapshot("e3")["coverage"]
        self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], coverage["gaps"])
        self.assertEqual((True, True, "unknown"), (coverage["has_gaps"], coverage["has_restart_gap"], coverage["continuity"]))

    def test_the_gap_is_persisted_with_the_event_it_came_after(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            clock = Clock()
            observation = provider(clock, path)
            hear(observation, 1, 2)
            at_two_past(clock)
            declare(observation)
            hear(observation, 3)
            stored = json.loads(path.with_name(path.name + ".continuity.json").read_text())
            self.assertEqual(
                {"schema_version": 3, "gaps": [{"at": "2026-10-10T14:02:00.000Z", "after": "e2"}]},
                stored,
            )

    def test_a_restart_finds_the_gap_again_between_the_events_it_was_between(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            clock = Clock()
            first = provider(clock, path)
            hear(first, 1, 2)
            at_two_past(clock)
            declare(first)
            hear(first, 3, 4)
            restored = provider(Clock(START + timedelta(hours=3)), path)
            # Still news, and still where it was: the restart declared none of its own.
            self.assertEqual(("2026-10-10T14:02:00.000Z",), restored.gaps_pending())
            self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], restored.build_snapshot("e4")["coverage"]["gaps"])
            # Between e2 and e3: a page of the two before it holds the neighbour on one side only,
            # a page of the two after it holds the neighbour on the other, and each says so.
            for direction, anchor, seen in (("before", "e3", {"e3", "e4"}), ("after", "e2", {"e1", "e2"})):
                with self.subTest(direction=direction):
                    page = restored.read_room(
                        direction=direction, anchor_event_id=anchor, seen_event_ids=seen,
                        since_arrival=0, max_events=12, max_bytes=16_384,
                    )
                    # Said in the reading's own time: three hours on, the gap is still today's.
                    self.assertEqual(SENTENCE, page["note"])

    def test_a_gap_whose_event_has_left_the_retained_history_is_before_everything_retained(self):
        limits = ObservationLimits(retention_events=2, retention_bytes=100_000, snapshot_events=2, snapshot_bytes=100_000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            clock = Clock()
            first = provider(clock, path, limits=limits)
            hear(first, 1, 2)
            at_two_past(clock)
            declare(first)
            hear(first, 3, 4, 5)
            restored = provider(Clock(), path, limits=limits)
            self.assertEqual(["e4", "e5"], [event["id"] for event in restored.retained_events()])
            self.assertEqual(1, len(restored.gaps_pending()))
            # The oldest retained event is the first after the gap, so a reading that holds it reaches it.
            self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], restored.build_snapshot("e5")["coverage"]["gaps"])

    def test_the_old_flag_becomes_a_gap_where_the_room_is_at_load_and_is_replaced_by_the_new_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            record = path.with_name(path.name + ".continuity.json")
            first = provider(Clock(), path)
            hear(first, 1, 2)
            record.write_bytes(b'{"has_gap":true,"schema_version":2}')
            clock = Clock(datetime(2026, 10, 10, 18, 30, tzinfo=timezone.utc))
            migrated = provider(clock, path)
            self.assertEqual(("2026-10-10T18:30:00.000Z",), migrated.gaps_pending())
            self.assertEqual(
                {"schema_version": 3, "gaps": [{"at": "2026-10-10T18:30:00.000Z", "after": "e2"}]},
                json.loads(record.read_text()),
            )
            coverage = migrated.build_snapshot("e2")["coverage"]
            self.assertEqual(([{"at": "2026-10-10T18:30:00.000Z"}], True, "unknown"), (
                coverage["gaps"], coverage["has_restart_gap"], coverage["continuity"]))
            # It was migrated once: a second load finds the same single gap, not another.
            again = provider(Clock(datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)), path)
            self.assertEqual(("2026-10-10T18:30:00.000Z",), again.gaps_pending())
            # And it is news only until the agent has been told.
            again.gaps_told(again.gaps_pending())
            self.assertEqual((), provider(Clock(), path).gaps_pending())

    def test_a_record_that_is_not_a_gap_record_is_refused(self):
        for text in (
            '{"has_gap":false,"schema_version":2}',
            '{"schema_version":3}',
            '{"schema_version":3,"gaps":{}}',
            '{"schema_version":3,"gaps":[{"at":"yesterday","after":null}]}',
            '{"schema_version":3,"gaps":[{"at":"2026-10-10T14:02:00Z"}]}',
            '{"schema_version":3,"gaps":[{"at":"2026-10-10T14:02:00Z","after":""}]}',
            '{"schema_version":3,"gaps":[{"at":"2026-10-10T14:02:00Z","after":null,"detail":"x"}]}',
            "[]",
            "not json",
        ):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "observations.jsonl"
                path.with_name(path.name + ".continuity.json").write_text(text)
                with self.assertRaises(PersistenceError):
                    provider(Clock(), path)

    def test_a_delivery_reserved_and_never_recorded_is_a_gap_once(self):
        limits = ObservationLimits(retention_events=4, retention_bytes=100_000, snapshot_events=4, snapshot_bytes=100_000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            first, _, _, _ = foundation(persistence_path=path, limits=limits)
            with mock.patch.object(first.observation, "_record_audit", side_effect=PersistenceError("simulated audit loss")):
                with self.assertRaises(PersistenceError):
                    first.handle_delivery(delivery_id="d1", event=message("e1"), actors=ACTORS)
            restored = provider(Clock(), path, limits=limits)
            self.assertEqual(1, len(restored.gaps_pending()))
            audits = path.with_name(path.name + ".delivery-audit.jsonl").read_text().splitlines()
            self.assertEqual(["continuity-gap"], [json.loads(line)["outcome"] for line in audits])
            self.assertEqual("e1", json.loads(audits[0])["event_id"])
            # Until the agent is told, a restart keeps it news without declaring a second.
            again = provider(Clock(START + timedelta(hours=1)), path, limits=limits)
            self.assertEqual(restored.gaps_pending(), again.gaps_pending())
            # Once the agent has taken a turn past it, no restart finds it again.
            again.gaps_told(again.gaps_pending())
            self.assertEqual((), provider(Clock(), path, limits=limits).gaps_pending())

    def test_a_gap_that_could_not_be_recorded_stays_news_and_is_found_again(self):
        limits = ObservationLimits(retention_events=4, retention_bytes=100_000, snapshot_events=4, snapshot_bytes=100_000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            first, _, _, _ = foundation(persistence_path=path, limits=limits)
            with mock.patch.object(first.observation, "_record_audit", side_effect=PersistenceError("simulated audit loss")):
                with self.assertRaises(PersistenceError):
                    first.handle_delivery(delivery_id="d1", event=message("e1"), actors=ACTORS)
            # The record of the gap cannot be written at load: nothing is accounted for.
            with mock.patch.object(ObservationProvider, "_persist_gaps", side_effect=PersistenceError("read-only")):
                unwritable = provider(Clock(), path, limits=limits)
            self.assertEqual(1, len(unwritable.gaps_pending()))
            self.assertEqual(1, len(provider(Clock(), path, limits=limits).gaps_pending()))

    def test_gaps_at_one_position_are_one_point_and_keep_the_later_time(self):
        clock = Clock()
        observation = provider(clock)
        hear(observation, 1)
        at_two_past(clock)
        declare(observation, "g1")
        clock.advance(minutes=8)
        declare(observation, "g2")
        self.assertEqual(("2026-10-10T14:10:00.000Z",), observation.gaps_pending())
        # An event between them makes two points.
        hear(observation, 2)
        clock.advance(minutes=5)
        declare(observation, "g3")
        self.assertEqual(("2026-10-10T14:10:00.000Z", "2026-10-10T14:15:00.000Z"), observation.gaps_pending())
        hear(observation, 3)
        self.assertEqual(
            [{"at": "2026-10-10T14:10:00.000Z"}, {"at": "2026-10-10T14:15:00.000Z"}],
            observation.build_snapshot("e3")["coverage"]["gaps"],
        )

    def test_two_points_never_share_a_name_even_when_the_clock_has_not_moved(self):
        observation = provider(Clock())
        hear(observation, 1)
        declare(observation, "g1")
        hear(observation, 2)
        declare(observation, "g2")
        self.assertEqual(("2026-10-10T14:00:00.000Z", "2026-10-10T14:00:00.001Z"), observation.gaps_pending())

    def test_two_points_in_one_minute_are_two_facts_and_one_phrase(self):
        clock = Clock()
        observation = provider(clock)
        hear(observation, 1)
        at_two_past(clock)
        declare(observation, "g1")
        hear(observation, 2)
        clock.advance(seconds=30)
        declare(observation, "g2")
        hear(observation, 3)
        request = observation.build_snapshot("e3")
        self.assertEqual(
            [{"at": "2026-10-10T14:02:00.000Z"}, {"at": "2026-10-10T14:02:30.000Z"}], request["coverage"]["gaps"]
        )
        self.assertEqual(SENTENCE, gap_sentence_in(request))

    def test_the_gaps_that_are_news_are_bounded(self):
        clock = Clock()
        observation = provider(clock)
        for number in range(MAX_GAPS + 4):
            hear(observation, number)
            clock.advance(minutes=1)
            declare(observation, f"g{number}")
        self.assertEqual(MAX_GAPS, len(observation.gaps_pending()))
        # The newest is never merged away.
        self.assertEqual(iso_minutes(MAX_GAPS + 4), observation.gaps_pending()[-1])

    def test_a_gap_declared_while_the_room_clock_is_not_utc_is_still_the_rooms_time(self):
        zone = timezone(timedelta(hours=2))
        observation = provider(lambda: datetime(2026, 10, 10, 16, 2, tzinfo=zone))
        hear(observation, 1)
        declare(observation)
        self.assertEqual(("2026-10-10T14:02:00.000Z",), observation.gaps_pending())


def iso_minutes(minutes: int) -> str:
    return (START + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class FailedWriteTests(unittest.TestCase):
    """A write that failed midway leaves a gap, told once: a restart does not find the same loss again."""

    def room(self, path):
        self.clock = Clock()
        self.wakes = []
        self.pipeline, _, _, _ = foundation(
            participant=lambda **turn: self.wakes.append(turn["wake"]) or None,
            persistence_path=path,
            clock=self.clock,
        )
        self.observation = self.pipeline.observation

    def deliver(self, number):
        return self.pipeline.handle_delivery(delivery_id=f"d{number}", event=message(f"e{number}"), actors=ACTORS)

    def fail_delivery(self, site, number):
        """Deliver one event whose write fails at ``site``: the reservation, the snapshot or the audit row."""

        real_reserve = ObservationProvider._reserve_replay
        real_audit = ObservationProvider._record_audit
        audits = []

        def reserved_then_lost(observation, delivery_id, event_id):
            real_reserve(observation, delivery_id, event_id)
            raise PersistenceError("simulated: the reservation was written and its sync failed")

        def first_audit_lost(observation, audit):
            audits.append(audit)
            if len(audits) == 1:
                raise PersistenceError("simulated audit loss")
            return real_audit(observation, audit)

        patched = {
            "reserve": mock.patch.object(ObservationProvider, "_reserve_replay", reserved_then_lost),
            "snapshot": mock.patch.object(
                ObservationProvider, "_persist_snapshot", side_effect=PersistenceError("simulated")
            ),
            "audit": mock.patch.object(ObservationProvider, "_record_audit", first_audit_lost),
        }[site]
        with patched, self.assertRaises(PersistenceError):
            self.deliver(number)

    def test_a_gap_declared_for_a_failed_write_and_told_is_not_found_again_after_a_restart(self):
        for site in ("reserve", "snapshot", "audit"):
            with self.subTest(site=site), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "observations.jsonl"
                self.room(path)
                self.deliver(1)
                self.fail_delivery(site, 2)
                self.assertEqual(1, len(self.observation.gaps_pending()))
                self.deliver(3)
                # The turn for e3 read across the gap and told it.
                self.assertEqual([False, True], ["gaps" in wake["coverage"] for wake in self.wakes])
                self.assertEqual((), self.observation.gaps_pending())
                # The process restarts: the same loss is not news again.
                self.room(path)
                self.assertEqual((), self.observation.gaps_pending())
                self.deliver(4)
                self.assertEqual([False], ["gaps" in wake["coverage"] for wake in self.wakes])

    def test_a_failed_write_that_was_not_told_before_a_restart_is_one_gap_not_two(self):
        for site in ("reserve", "snapshot", "audit"):
            with self.subTest(site=site), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "observations.jsonl"
                self.room(path)
                self.deliver(1)
                self.fail_delivery(site, 2)
                self.clock.advance(minutes=5)
                hear(self.observation, 3)
                self.room(path)
                self.assertEqual(1, len(self.observation.gaps_pending()))
                self.assertEqual("14:00", self.observation.gaps_pending()[0][11:16])

    def test_a_delivery_that_was_never_reserved_is_not_made_a_duplicate_of_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            self.room(Path(directory) / "observations.jsonl")
            self.deliver(1)

            def never_reserved(observation, delivery_id, event_id):
                raise PersistenceError("simulated: the reservation file could not be opened")

            with mock.patch.object(ObservationProvider, "_reserve_replay", never_reserved):
                with self.assertRaises(PersistenceError):
                    self.deliver(2)
            self.assertEqual(1, len(self.observation.gaps_pending()))
            self.assertNotIn("continuity-gap", [audit.outcome for audit in self.observation.delivery_audits()])
            # The platform delivers it again: it is recorded, not an exact duplicate.
            again = self.observation.observe(delivery_id="d2", event=message("e2"), actors=ACTORS)
            self.assertEqual("recorded", again.audit.outcome)


class GapReadingTests(unittest.TestCase):
    """A window reaches a gap by its neighbours, not by its distance; and coverage follows what is in view."""

    def setUp(self):
        self.clock = Clock()
        limits = ObservationLimits(snapshot_events=3)
        self.observation = provider(self.clock, limits=limits)
        hear(self.observation, 1, 2, 3)
        at_two_past(self.clock)
        declare(self.observation)

    def gaps(self, trigger):
        return self.observation.build_snapshot(trigger)["coverage"].get("gaps")

    def test_a_window_that_runs_up_to_the_gap_is_told(self):
        self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], self.gaps("e3"))

    def test_a_window_that_crosses_it_or_starts_right_after_it_is_told(self):
        # Three events a window: e4 crosses it, e5 still holds the event before it,
        # and e6 starts right after it.
        for number in (4, 5, 6):
            hear(self.observation, number)
            with self.subTest(trigger=f"e{number}"):
                self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], self.gaps(f"e{number}"))

    def test_a_window_further_on_is_not_told_though_the_gap_is_still_news(self):
        hear(self.observation, 4, 5, 6, 7)
        self.assertIsNone(self.gaps("e7"))
        coverage = self.observation.build_snapshot("e7")["coverage"]
        self.assertEqual((False, False, "session-only"), (coverage["has_gaps"], coverage["has_restart_gap"], coverage["continuity"]))
        self.assertEqual(1, len(self.observation.gaps_pending()))
        # Reading back toward it does reach it.
        page = self.observation.read_room(
            direction="before", anchor_event_id="e7", seen_event_ids={"e5", "e6", "e7"},
            since_arrival=0, max_events=12, max_bytes=16_384,
        )
        self.assertEqual([event["id"] for event in page["events"]], ["e1", "e2", "e3", "e4"])
        self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], page["coverage"]["gaps"])
        self.assertEqual(SENTENCE, page["note"])

    def test_a_page_that_does_not_reach_it_says_nothing(self):
        hear(self.observation, 4, 5, 6, 7)
        page = self.observation.read_room(
            direction="before", anchor_event_id="e7", seen_event_ids={"e7"},
            since_arrival=0, max_events=2, max_bytes=16_384,
        )
        self.assertEqual(["e5", "e6"], [event["id"] for event in page["events"]])
        self.assertNotIn("gaps", page["coverage"])
        self.assertNotIn("note", page)
        self.assertEqual((False, False), (page["coverage"]["has_gaps"], page["coverage"]["has_restart_gap"]))

    def test_a_message_that_arrives_after_the_gap_is_after_it_whatever_its_timestamp(self):
        # Backfill: a message older than everything the room holds sorts first, but it
        # arrived behind the gap, so the gap is right before it, and a page of only that
        # message reaches the gap.
        observation = provider(Clock())
        for number, stamp in ((1, "10:00"), (2, "10:01")):
            observation.observe(
                delivery_id=f"d{number}", event=message(f"e{number}", timestamp=f"2026-10-10T{stamp}:00.000Z"), actors=ACTORS
            )
        declare(observation)
        observation.observe(
            delivery_id="d-late", event=message("e-late", timestamp="2026-10-10T08:00:00.000Z"), actors=ACTORS
        )
        self.assertEqual(["e-late", "e1", "e2"], [event["id"] for event in observation.retained_events()])
        page = observation.read_room(
            direction="before", anchor_event_id="e1", seen_event_ids={"e1", "e2"},
            since_arrival=0, max_events=12, max_bytes=16_384,
        )
        self.assertEqual(["e-late"], [event["id"] for event in page["events"]])
        self.assertEqual(1, len(page["coverage"]["gaps"]))

    def test_a_window_that_holds_events_on_both_sides_of_a_gap_but_not_its_neighbours_crosses_it(self):
        # A late message with an old timestamp replies to an early one. The window holds that late
        # message (after the gap, by arrival), the early message it answers (before the gap) and
        # the newest message, and neither of the two messages that sit beside the gap.
        observation = provider(Clock(), limits=ObservationLimits(snapshot_events=3))

        def arrive(number, stamp, **extra):
            observation.observe(
                delivery_id=f"d{number}",
                event=message(f"e{number}", timestamp=f"2026-10-10T{stamp}:00.000Z", **extra),
                actors=ACTORS,
            )

        arrive(1, "10:00")
        arrive(2, "10:01")
        declare(observation)
        arrive(3, "10:02")
        arrive(4, "10:03")
        arrive("-late", "09:30", reply_to_event_id="e1")
        request = observation.build_snapshot("e-late")
        self.assertEqual({"e-late", "e1", "e4"}, {event["id"] for event in request["events"]})
        self.assertEqual([{"at": "2026-10-10T14:00:00.000Z"}], request["coverage"].get("gaps"))

    def test_the_declared_continuity_is_what_coverage_reports_when_no_gap_is_in_view(self):
        for declared in ("restart-safe", "session-only", "unknown"):
            with self.subTest(declared=declared), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "o.jsonl" if declared == "restart-safe" else None
                clock = Clock()
                observation = provider(clock, path, continuity=declared)
                hear(observation, 1)
                coverage = observation.build_snapshot("e1")["coverage"]
                self.assertEqual((declared, False, False), (coverage["continuity"], coverage["has_gaps"], coverage["has_restart_gap"]))
                declare(observation)
                coverage = observation.build_snapshot("e1")["coverage"]
                self.assertEqual(("unknown", True, True), (coverage["continuity"], coverage["has_gaps"], coverage["has_restart_gap"]))
                observation.gaps_told(gap_times(coverage))
                coverage = observation.build_snapshot("e1")["coverage"]
                self.assertEqual((declared, False, False), (coverage["continuity"], coverage["has_gaps"], coverage["has_restart_gap"]))

    def test_an_interior_hole_in_the_window_is_still_has_gaps_without_being_a_restart_gap(self):
        limits = ObservationLimits(snapshot_events=4)
        observation = provider(Clock(), limits=limits)
        observation.observe(
            delivery_id="d-first", event=message("e-first", mentioned_actor_ids=["discord:bot:9"]), actors=ACTORS
        )
        hear(observation, 1, 2, 3, 4, 5)
        coverage = observation.build_snapshot("e5")["coverage"]
        self.assertEqual((True, False, "session-only"), (coverage["has_gaps"], coverage["has_restart_gap"], coverage["continuity"]))
        self.assertNotIn("gaps", coverage)

    def test_a_gap_merged_into_one_the_agent_was_told_is_news_again(self):
        told = self.observation.gaps_pending()
        self.clock.advance(minutes=10)
        declare(self.observation, "merged")
        self.observation.gaps_told(told)
        self.assertEqual(("2026-10-10T14:12:00.000Z",), self.observation.gaps_pending())

    def test_a_gap_told_by_time_clears_only_that_gap(self):
        hear(self.observation, 4)
        self.clock.advance(minutes=5)
        declare(self.observation, "g2")
        self.assertEqual(2, len(self.observation.gaps_pending()))
        self.observation.gaps_told(["2026-10-10T14:02:00.000Z", 7, None])
        self.assertEqual(("2026-10-10T14:07:00.000Z",), self.observation.gaps_pending())
        self.observation.gaps_told([])
        self.observation.gaps_told(["2026-10-10T09:00:00.000Z"])
        self.assertEqual(1, len(self.observation.gaps_pending()))


class GapTurnTests(unittest.TestCase):
    """The turn says it once, in the library's words, whichever way the harness renders it."""

    def wake(self, *, gap=True):
        clock = Clock()
        observation = provider(clock)
        hear(observation, 1)
        at_two_past(clock)
        if gap:
            declare(observation)
        hear(observation, 2)
        clock.advance(minutes=28)
        request = observation.build_snapshot("e2")
        wake = {
            key: request[key]
            for key in ("request_id", "self", "room", "actors", "events", "trigger_event_id", "coverage", "pace")
        }
        wake["attention"] = {"source": "WAKE"}
        return validate_participant_wake(wake)

    def texts(self, wake):
        request = build_participant_turn_request(wake, OPPORTUNITY)
        profile = foundation()[0].attention.profile
        tools = {"send": "send", "react": "react", "context": "context"}
        return {
            "tools": participant_tool_turn_text(profile, request, tools=tools),
            "final-answer": participant_tool_turn_text(profile, request, tools={"react": "react", "context": "context"}, silence_marker="[SILENT]"),
            "one-reply": participant_turn_text(profile, request),
            "instructions": participant_turn_instructions(profile, request),
        }

    def test_every_way_of_rendering_the_turn_says_the_sentence_once_and_carries_the_gap(self):
        wake = self.wake()
        self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], wake["coverage"]["gaps"])
        for style, text in self.texts(wake).items():
            with self.subTest(style=style):
                self.assertEqual(1, text.count(SENTENCE))
                self.assertEqual("\n\n" + SENTENCE, gap_turn_note(build_participant_turn_request(wake, OPPORTUNITY)))
        # The facts the sentence comes from are in the turn's document too.
        self.assertIn('"gaps":[{"at":"2026-10-10T14:02:00.000Z"}]', self.texts(wake)["tools"])

    def test_a_turn_that_reaches_no_gap_has_no_sentence_and_no_gap_fact(self):
        wake = self.wake(gap=False)
        self.assertNotIn("gaps", wake["coverage"])
        for style, text in self.texts(wake).items():
            with self.subTest(style=style):
                self.assertNotIn("Messages may be missing", text)
                self.assertNotIn('"gaps"', text)
        self.assertEqual("", gap_turn_note(build_participant_turn_request(wake, OPPORTUNITY)))

    def test_a_turn_that_reaches_a_gap_differs_from_the_same_turn_without_only_by_the_gap(self):
        without = self.texts(self.wake(gap=False))["tools"]
        told = self.texts(self.wake())["tools"]
        stripped = told.replace("\n\n" + SENTENCE, "")
        self.assertNotEqual(without, told)
        # Everything else the turn says is the same words in the same places.
        self.assertEqual(without.split("<nunchi_participant_turn_v1>")[0], stripped.split("<nunchi_participant_turn_v1>")[0])

    def test_the_runtime_contract_takes_a_gap_and_refuses_a_malformed_one(self):
        wake = self.wake()
        for bad in ([], [{}], [{"at": ""}], [{"at": "not a time"}], [{"at": "2026-10-10T14:02:00Z", "x": 1}], "x"):
            with self.subTest(bad=bad):
                broken = json.loads(json.dumps(wake))
                broken["coverage"]["gaps"] = bad
                with self.assertRaises(ValidationError):
                    validate_participant_wake(broken)
                with self.assertRaises(ValidationError):
                    validate_attention_request({**{k: broken[k] for k in broken if k != "attention"}, "schema_version": 2})


class HostTests(unittest.TestCase):
    """The agent is told when its reading reaches the gap, and not again once it has taken a turn past it."""

    def room(self, *, participant, model=None, path=None, limits=None, transport=None, guard=None):
        self.clock = Clock()
        self.pipeline, self.model, _, _ = foundation(
            participant=participant, model=model, persistence_path=path, limits=limits, clock=self.clock,
            transport=transport,
        )
        if guard is not None:
            self.pipeline.host.guard = guard
        self.observation = self.pipeline.observation
        self.profile = self.pipeline.attention.profile

    def deliver(self, number):
        return self.pipeline.handle_delivery(delivery_id=f"d{number}", event=message(f"e{number}"), actors=ACTORS)

    def text_of(self, wake):
        request = build_participant_turn_request(wake, OPPORTUNITY)
        return participant_tool_turn_text(self.profile, request, tools={"send": "send", "context": "context"})

    def test_told_in_the_turn_that_reaches_it_and_in_no_turn_after(self):
        wakes = []
        self.room(participant=lambda **turn: wakes.append(turn["wake"]) or None)
        self.deliver(1)
        at_two_past(self.clock)
        declare(self.observation)
        self.deliver(2)
        self.assertEqual((), self.observation.gaps_pending(), "the agent took a turn past it")
        self.deliver(3)
        told = [SENTENCE in self.text_of(wake) for wake in wakes]
        self.assertEqual([False, True, False], told)
        self.assertEqual([False, True, False], ["gaps" in wake["coverage"] for wake in wakes])
        # A later look at the same window is clean too.
        self.assertNotIn("gaps", self.observation.build_snapshot("e3")["coverage"])

    def test_a_turn_that_failed_leaves_the_gap_to_be_told_again(self):
        wakes = []

        def participant(**turn):
            wakes.append(turn["wake"])
            if len(wakes) == 2:
                raise RuntimeError("the agent's run failed")

        self.room(participant=participant)
        self.deliver(1)
        at_two_past(self.clock)
        declare(self.observation)
        failed = self.deliver(2)
        self.assertEqual("failed", failed.opportunities[0].transport.delivery)
        self.assertEqual(1, len(self.observation.gaps_pending()))
        self.deliver(3)
        self.assertEqual([False, True, True], ["gaps" in wake["coverage"] for wake in wakes])
        self.assertEqual((), self.observation.gaps_pending())

    def test_an_answer_the_host_refuses_leaves_the_gap_to_be_told_again(self):
        secret = "hunter2-hunter2-hunter2"
        for name, action, guard in (
            ("an action that is not one", {"kind": "nonsense"}, None),
            ("a reply holding a withheld secret", {"kind": "message", "origin_event_id": "e2", "text": secret}, SecretGuard([secret])),
            ("a move about a message it was never shown", {"kind": "message", "origin_event_id": "e-nowhere", "text": "hello"}, None),
        ):
            with self.subTest(answer=name):
                wakes = []
                self.room(participant=lambda action=action, **turn: wakes.append(turn["wake"]) or dict(action), guard=guard)
                self.deliver(1)
                at_two_past(self.clock)
                declare(self.observation)
                outcome = self.deliver(2)
                self.assertEqual("failed", outcome.opportunities[0].transport.delivery)
                self.assertEqual(1, len(self.observation.gaps_pending()))
                # The next turn is told again.
                self.deliver(3)
                self.assertEqual([False, True, True], ["gaps" in wake["coverage"] for wake in wakes])

    def test_an_accepted_action_tells_the_gap_even_when_the_platform_then_fails_it(self):
        from nunchi.participant import TransportResult
        from tests.v2.test_shared_foundation import RecordingTransport

        wakes = []
        self.room(
            participant=lambda **turn: wakes.append(turn["wake"]) or {"kind": "message", "origin_event_id": "e2", "text": "hello"},
            transport=RecordingTransport(TransportResult("failed", "the platform refused it")),
        )
        self.deliver(1)
        at_two_past(self.clock)
        declare(self.observation)
        outcome = self.deliver(2)
        self.assertEqual("failed", outcome.opportunities[0].transport.delivery)
        # The agent read the sentence and answered; the platform's failure is not the agent's.
        self.assertEqual((), self.observation.gaps_pending())

    def test_a_turn_that_was_cancelled_leaves_the_gap_to_be_told_again(self):
        def participant(*, wake, expand, cancel):
            cancel.set()

        self.room(participant=participant)
        self.deliver(1)
        at_two_past(self.clock)
        declare(self.observation)
        self.deliver(2)
        self.assertEqual(1, len(self.observation.gaps_pending()))

    def test_a_page_the_agent_reads_across_the_gap_is_told_once_the_turn_is_taken(self):
        pages, wakes = [], []
        limits = ObservationLimits(snapshot_events=2)

        def participant(*, wake, expand, cancel):
            wakes.append(wake)
            pages.append(expand(direction="before", max_events=12, max_bytes=16_384))
            return None

        self.room(participant=participant, limits=limits)
        hear(self.observation, 1, 2)
        at_two_past(self.clock)
        declare(self.observation)
        hear(self.observation, 3, 4, 5, 6)
        outcome = self.deliver(7)
        # The window does not reach the gap, so the turn's text does not say it.
        self.assertNotIn("gaps", wakes[0]["coverage"])
        self.assertNotIn(SENTENCE, self.text_of(wakes[0]))
        self.assertEqual(1, len(pages))
        self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], pages[0]["coverage"]["gaps"])
        self.assertEqual(SENTENCE, pages[0]["note"])
        self.assertIsNone(outcome.opportunities[0].transport)
        self.assertEqual((), self.observation.gaps_pending())

    def test_a_gap_declared_during_the_turn_is_news_for_the_next(self):
        wakes = []

        def participant(**turn):
            wakes.append(turn["wake"])
            if len(wakes) == 2:
                declare(self.observation, "mid-turn")
            return None

        self.room(participant=participant)
        self.deliver(1)
        at_two_past(self.clock)
        declare(self.observation)
        self.deliver(2)
        # The clock did not move, yet the one declared mid-turn is another point, not the one it was told.
        self.assertEqual(("2026-10-10T14:02:00.001Z",), self.observation.gaps_pending())
        self.deliver(3)
        self.assertEqual([False, True, True], ["gaps" in wake["coverage"] for wake in wakes])
        self.assertEqual((), self.observation.gaps_pending())

    def test_without_a_turn_the_gap_stays_news(self):
        self.room(participant=lambda **turn: None, model=FixtureModel("SUPPRESS"))
        self.deliver(1)
        at_two_past(self.clock)
        declare(self.observation)
        self.deliver(2)
        self.assertEqual(1, len(self.observation.gaps_pending()))
        # Attention was shown the gap each time it judged, until a turn was taken.
        self.assertIn("gaps", self.model.calls[-1][1]["coverage"])

    def test_the_gap_survives_a_restart_until_told(self):
        wakes = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            self.room(participant=lambda **turn: wakes.append(turn["wake"]) or None, path=path)
            hear(self.observation, 1)
            at_two_past(self.clock)
            declare(self.observation)
            # The process ends before the agent takes a turn.
            self.room(participant=lambda **turn: wakes.append(turn["wake"]) or None, path=path)
            self.assertEqual(1, len(self.observation.gaps_pending()))
            self.deliver(2)
            self.assertEqual(["gaps" in wake["coverage"] for wake in wakes], [True])
            self.room(participant=lambda **turn: wakes.append(turn["wake"]) or None, path=path)
            self.assertEqual((), self.observation.gaps_pending())
            self.deliver(3)
            self.assertEqual(["gaps" in wake["coverage"] for wake in wakes], [True, False])


class DiscardedPageTests(unittest.TestCase):
    """A gap counts as read when the page that reached it is returned to the agent, not when it was only fetched."""

    REACTION = {
        "id": "r1", "type": "reaction", "author_id": "human:alice",
        "target_event_id": "e2", "reaction": "\U0001F44D", "operation": "add",
    }

    def run_turns(self, arrival, steer):
        """Turn 1 loses the connection mid-turn (a loss nothing cancelled for), then ``arrival`` comes in and the turn steers."""

        clock = Clock()
        seen = {"turns": 0, "texts": []}
        tools = {"send": "send", "context": "context"}

        def participant(*, wake, expand, cancel):
            seen["turns"] += 1
            request = build_participant_turn_request(wake, OPPORTUNITY)
            seen["texts"].append(participant_tool_turn_text(pipeline.attention.profile, request, tools=tools))
            if seen["turns"] > 1:
                return None
            turn = Turn(
                profile=pipeline.attention.profile, request=request, tool_names=tools, expand=expand, cancel=cancel
            )
            declare(observation, "mid-turn")
            clock.advance(seconds=30)
            observation.observe(delivery_id="d-meanwhile", event=dict(arrival), actors=ACTORS)
            seen["shown"] = steer(turn)
            return None

        pipeline, _, _, _ = foundation(participant=participant, clock=clock)
        observation = pipeline.observation
        hear(observation, 1)
        pipeline.handle_delivery(delivery_id="d2", event=message("e2"), actors=ACTORS)
        seen["pending_after_turn"] = observation.gaps_pending()
        pipeline.handle_delivery(delivery_id="d3", event=message("e3"), actors=ACTORS)
        seen["pending_after_next"] = observation.gaps_pending()
        return seen

    STEERING = {
        "steering": lambda turn: turn.after_tool_call(),
        "the look before posting": lambda turn: turn.look_again(
            {"kind": "message", "text": "hi", "origin_event_id": "e2"}
        ),
    }

    def test_a_gap_only_the_turns_own_read_reached_is_told_by_the_next_turn(self):
        # Steering and the look before posting show their page only when it
        # holds a message, and the view cannot tell which: when unsure, tell.
        for arrival, shown in ((self.REACTION, False), (message("e-meanwhile"), True)):
            for name, steer in self.STEERING.items():
                with self.subTest(page=name, shown=shown):
                    seen = self.run_turns(arrival, steer)
                    self.assertEqual(shown, seen["shown"] is not None)
                    self.assertEqual(1, len(seen["pending_after_turn"]))
                    self.assertEqual(1, seen["texts"][1].count("Messages may be missing"))
                    self.assertEqual((), seen["pending_after_next"])


class HistoryPageTests(unittest.TestCase):
    """The history the agent is told to read says what is true at the edge of what Nunchi heard."""

    NOT_LISTENING = "Nunchi has no older messages: it was not listening before 14:00 UTC."

    def fresh_start(self, *, limits=None):
        """A room whose integration declared its start gap before the first message."""

        self.clock = Clock()
        self.observation = provider(self.clock, limits=limits)
        declare(self.observation, "start")
        hear(self.observation, 1, 2, 3)

    def page(self, direction, anchor, seen=()):
        return self.observation.read_room(
            direction=direction, anchor_event_id=anchor, seen_event_ids=set(seen),
            since_arrival=0, max_events=12, max_bytes=16_384,
        )

    def test_the_first_message_has_no_older_ones_because_nunchi_was_not_listening(self):
        self.fresh_start()
        page = self.page("before", "e1")
        self.assertEqual([], page["events"])
        self.assertEqual(self.NOT_LISTENING, page["note"])
        # The page reached the gap through the message it starts from, and says so as a fact too.
        self.assertEqual([{"at": "2026-10-10T14:00:00.000Z"}], page["coverage"]["gaps"])
        self.assertTrue(page["coverage"]["has_restart_gap"])

    def test_a_page_that_ends_where_nunchi_began_to_listen_says_so_in_place_of_the_sentence(self):
        self.fresh_start()
        page = self.page("before", "e3")
        self.assertEqual(["e1", "e2"], [event["id"] for event in page["events"]])
        self.assertEqual(self.NOT_LISTENING, page["note"])

    def test_a_gap_with_messages_before_it_is_still_the_sentence(self):
        self.fresh_start()
        at_two_past(self.clock)
        declare(self.observation, "later")
        hear(self.observation, 4)
        page = self.page("before", "e4")
        self.assertEqual(["e1", "e2", "e3"], [event["id"] for event in page["events"]])
        # The gap before e4 has history before it, and the one before e1 has none.
        self.assertEqual(self.NOT_LISTENING + " " + SENTENCE, page["note"])
        middle = self.page("before", "e4", seen={"e1", "e2"})
        self.assertEqual(["e3"], [event["id"] for event in middle["events"]])
        self.assertEqual(SENTENCE, middle["note"])

    def test_where_older_messages_were_heard_and_let_go_the_page_does_not_say_nunchi_was_not_listening(self):
        limits = ObservationLimits(retention_events=2, retention_bytes=100_000, snapshot_events=2, snapshot_bytes=100_000)
        self.fresh_start(limits=limits)
        page = self.page("before", "e2")
        self.assertEqual([], page["events"])
        self.assertEqual(
            "No older messages are retained. Messages may be missing before 14:00 UTC; read the history if it matters.",
            page["note"],
        )

    def test_a_page_with_nothing_newer_still_reaches_a_gap_after_the_last_message(self):
        clock = Clock()
        self.observation = provider(clock)
        hear(self.observation, 1, 2)
        at_two_past(clock)
        declare(self.observation)
        page = self.page("after", "e2")
        self.assertEqual([], page["events"])
        self.assertEqual("Nothing newer yet. " + SENTENCE, page["note"])
        self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], page["coverage"]["gaps"])

    def test_the_agent_told_to_read_the_history_finds_it_says_the_same(self):
        pages, wakes = [], []

        def participant(*, wake, expand, cancel):
            wakes.append(wake)
            pages.append(expand(direction="before", max_events=12, max_bytes=16_384))
            return None

        pipeline, _, _, _ = foundation(participant=participant, clock=Clock())
        declare(pipeline.observation, "start")
        pipeline.handle_delivery(delivery_id="d1", event=message("e1"), actors=ACTORS)
        self.assertEqual("gaps" in wakes[0]["coverage"], True)
        self.assertEqual(self.NOT_LISTENING, pages[0]["note"])
        self.assertEqual((), pipeline.observation.gaps_pending())


class AttentionTests(unittest.TestCase):
    """Attention's judgment sees the same fact, in the same plain words."""

    def room(self, model):
        clock = Clock()
        pipeline, model, _, _ = foundation(model=model, participant=lambda **turn: None, clock=clock)
        hear(pipeline.observation, 1)
        at_two_past(clock)
        declare(pipeline.observation)
        clock.advance(minutes=28)
        return pipeline, model

    def test_the_chat_model_is_told_in_the_same_words_the_turn_carries(self):
        pipeline, model = self.room(FixtureModel())
        pipeline.handle_delivery(delivery_id="d2", event=message("e2"), actors=ACTORS)
        instructions, projection = model.calls[0]
        self.assertEqual([{"at": "2026-10-10T14:02:00.000Z"}], projection["coverage"]["gaps"])
        self.assertIn(SENTENCE, instructions)
        self.assertIn("observation.coverage.gaps", instructions)
        self.assertEqual(participant_attention_prompt(pipeline.attention.profile, gap=SENTENCE), instructions)

    def test_a_typed_model_gets_the_sentence_in_its_state(self):
        from tests.v2.test_attention_questions import TypedModel, leaning

        pipeline, model = self.room(TypedModel(leaning("WAKE")))
        pipeline.handle_delivery(delivery_id="d2", event=message("e2"), actors=ACTORS)
        (_, state), = model.calls
        self.assertEqual(SENTENCE, state["gap"])

    def test_a_judgment_that_reaches_no_gap_is_given_neither(self):
        from tests.v2.test_attention_questions import TypedModel, leaning

        pipeline, model, _, _ = foundation(participant=lambda **turn: None)
        pipeline.handle_delivery(delivery_id="d1", event=message("e1"), actors=ACTORS)
        instructions, projection = model.calls[0]
        self.assertEqual(participant_attention_prompt(pipeline.attention.profile), instructions)
        self.assertNotIn("gaps", projection["coverage"])
        self.assertNotIn("Messages may be missing", instructions)
        typed = TypedModel(leaning("WAKE"))
        other, typed, _, _ = foundation(model=typed, participant=lambda **turn: None)
        other.handle_delivery(delivery_id="d1", event=message("e1"), actors=ACTORS)
        (_, state), = typed.calls
        self.assertNotIn("gap", state)

    def test_the_state_of_a_projection_with_a_gap_says_it(self):
        pipeline, _ = self.room(FixtureModel())
        pipeline.observation.observe(delivery_id="d2", event=message("e2"), actors=ACTORS)
        request = pipeline.observation.build_snapshot("e2")
        self.assertEqual(SENTENCE, attention_state(request, "x")["gap"])
        self.assertEqual(SENTENCE, gap_sentence_in(request))


if __name__ == "__main__":
    unittest.main()
