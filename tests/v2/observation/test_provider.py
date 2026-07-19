"""US1 provider tests: exact self, native relations, transport hygiene (T006).

Covers S01 (exact-self alias collision), S02 (native relations), S04
(false-suppression scars stay out of deterministic hygiene), S11
(transport hygiene's three mechanical no-wake classes), and S16 (no
roster/registry/ledger is created).
"""

from __future__ import annotations

import unittest

from nunchi.observation import ObservationInputError, OBSERVED, DUPLICATE_RETAINED, SELF_RETAINED_NO_WAKE, UNROUTABLE
from tests.v2.observation.helpers import (
    FIXTURE_ACTORS,
    FIXTURE_SELF_ACTOR_ID,
    candidate,
    make_membership,
    make_message,
    make_provider,
    make_reaction,
    seed_room,
    unroutable,
)


class TestExactSelfAndAliasCollision(unittest.TestCase):
    """S01: only the transport-attested actor ID establishes self authorship."""

    def test_alias_collision_never_establishes_self(self):
        provider = make_provider()
        # An observed actor is named "Vigil" too (alias collision) but its
        # actor ID differs from self.actor_id.
        actors = dict(FIXTURE_ACTORS, **{"discord:2002": {"display_name": "Vigil", "kind": "bot"}})
        event = make_message("e1", "discord:2002", "I can take it")
        outcome = provider.ingest(candidate(event, actors=actors))
        self.assertEqual(outcome, OBSERVED)  # not self, despite the shared display name
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        self.assertEqual(snapshot["self"]["actor_id"], FIXTURE_SELF_ACTOR_ID)
        self.assertNotEqual(snapshot["events"][0]["author_id"], snapshot["self"]["actor_id"])

    def test_exact_self_event_is_retained_but_flagged_no_wake(self):
        provider = make_provider()
        event = make_message("e1", FIXTURE_SELF_ACTOR_ID, "I can take it")
        outcome = provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        self.assertEqual(outcome, SELF_RETAINED_NO_WAKE)
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        self.assertEqual(len(snapshot["events"]), 1)  # retained, not dropped


class TestSelfCausedMembership(unittest.TestCase):
    """FR-004 / D020-01: a membership event is exact-self-caused, and thus
    ``self-retained-no-wake``, only when ``caused_by_actor_id`` matches
    self; being the passive ``subject_actor_id`` is not self-causation."""

    def test_self_caused_membership_is_retained_no_wake(self):
        provider = make_provider()
        event = make_membership("e1", "discord:1001", "join", caused_by_actor_id=FIXTURE_SELF_ACTOR_ID)
        outcome = provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        self.assertEqual(outcome, SELF_RETAINED_NO_WAKE)

    def test_self_as_subject_with_other_cause_remains_observed(self):
        provider = make_provider()
        event = make_membership("e1", FIXTURE_SELF_ACTOR_ID, "join", caused_by_actor_id="discord:1001")
        outcome = provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        self.assertEqual(outcome, OBSERVED)

    def test_self_as_subject_with_no_cause_remains_observed(self):
        provider = make_provider()
        event = make_membership("e1", FIXTURE_SELF_ACTOR_ID, "join")
        outcome = provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        self.assertEqual(outcome, OBSERVED)


class TestNativeRelations(unittest.TestCase):
    """S02: actor-targeted mentions, room-wide mentions, replies, threads,
    reactions, and membership stay distinct literal facts."""

    def test_actor_mention_and_room_mention_are_distinct(self):
        provider = make_provider()
        e1 = make_message("e1", "discord:1001", "hey @Vigil", mentioned_actor_ids=[FIXTURE_SELF_ACTOR_ID])
        e2 = make_message("e2", "discord:1001", "@here deploy starting", mentions_room=True)
        seed_room(provider, [e1, e2])
        snapshot = provider.snapshot(trigger_event_id="e2", max_events=10, max_bytes=65536)
        by_id = {event["id"]: event for event in snapshot["events"]}
        self.assertEqual(by_id["e1"]["mentioned_actor_ids"], [FIXTURE_SELF_ACTOR_ID])
        self.assertFalse(by_id["e1"]["mentions_room"])
        self.assertEqual(by_id["e2"]["mentioned_actor_ids"], [])
        self.assertTrue(by_id["e2"]["mentions_room"])

    def test_reply_reaction_membership_thread_relations_survive(self):
        provider = make_provider()
        e1 = make_message("e1", "discord:1001", "hey @Vigil", mentioned_actor_ids=[FIXTURE_SELF_ACTOR_ID])
        e2 = make_message("e2", "discord:2002", "replying", reply_to_event_id="e1")
        e3 = make_reaction("e3", "discord:3003", "e2", "\U0001f44d")
        e4 = make_membership("e4", "discord:1001", "join")
        e5 = make_message("e5", "discord:1001", "thread opener", thread_root_event_id="e1")
        seed_room(provider, [e1, e2, e3, e4, e5])
        snapshot = provider.snapshot(trigger_event_id="e5", max_events=10, max_bytes=65536)
        by_id = {event["id"]: event for event in snapshot["events"]}
        self.assertEqual(by_id["e2"]["reply_to_event_id"], "e1")
        self.assertEqual(by_id["e3"]["target_event_id"], "e2")
        self.assertEqual(by_id["e4"]["change"], "join")
        self.assertEqual(by_id["e5"]["thread_root_event_id"], "e1")

    def test_unavailable_fact_stays_honest_omission(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "no timestamp on this platform")
        seed_room(provider, [event])
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        self.assertNotIn("timestamp", snapshot["events"][0])


class TestFalseSuppressionScars(unittest.TestCase):
    """S04: referential mention, resolution, other-addressee, and class
    address never enter deterministic transport hygiene decisions."""

    def test_operator_correction_addressed_to_agent_is_not_auto_suppressed(self):
        provider = make_provider()
        event = make_message(
            "e1", "discord:1001", "no, revert that change", mentioned_actor_ids=[FIXTURE_SELF_ACTOR_ID]
        )
        outcome = provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        # The provider only reports the observed fact; it never independently
        # decides suppression from mention/resolution semantics.
        self.assertEqual(outcome, OBSERVED)

    def test_message_addressed_to_another_actor_is_observed_not_classified(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "@Sol can you check this", mentioned_actor_ids=["discord:3003"])
        outcome = provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        self.assertEqual(outcome, OBSERVED)


class TestTransportHygiene(unittest.TestCase):
    """S11: exact duplicate, exact self, and unroutable are the only three
    mechanical no-wake classes; nothing else short-circuits."""

    def test_exact_duplicate_delivery_is_retained_without_reappending(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hello")
        first = provider.ingest(candidate(event, actors=FIXTURE_ACTORS, delivery_id="d1"))
        second = provider.ingest(candidate(event, actors=FIXTURE_ACTORS, delivery_id="d1"))
        self.assertEqual(first, OBSERVED)
        self.assertEqual(second, DUPLICATE_RETAINED)
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        self.assertEqual(len(snapshot["events"]), 1)

    def test_unroutable_carries_no_candidate_event(self):
        provider = make_provider()
        outcome = provider.ingest(unroutable("d2", "transport could not authorize this delivery"))
        self.assertEqual(outcome, UNROUTABLE)

    def test_candidate_event_without_authorization_is_operational_error(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hello")
        malformed = {"delivery_id": "d3", "disposition": "candidate-event", "event": event}
        with self.assertRaises(ObservationInputError):
            provider.ingest(malformed)

    def test_malformed_event_is_operational_error_not_silent_drop(self):
        provider = make_provider()
        malformed_event = {"id": "e1", "type": "message"}  # missing required fields
        native_input = candidate(malformed_event, actors=FIXTURE_ACTORS)
        with self.assertRaises(ObservationInputError):
            provider.ingest(native_input)


class TestNoSocialLedger(unittest.TestCase):
    """S16: no roster inference, outcome registry, obligation queue, or
    handled/open state is created by the shared provider."""

    def test_provider_exposes_no_roster_or_ledger_attributes(self):
        provider = make_provider()
        forbidden = {"roster", "handled", "open", "obligations", "speaker_queue", "response_debt"}
        public_attrs = {name for name in vars(provider) if not name.startswith("_")}
        self.assertFalse(forbidden & public_attrs)

    def test_actors_map_holds_only_observed_or_referenced_cast(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi", mentioned_actor_ids=[FIXTURE_SELF_ACTOR_ID])
        seed_room(provider, [event])
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        # discord:3003 (Sol) was never observed or referenced in this room yet.
        self.assertNotIn("discord:3003", snapshot["actors"])


if __name__ == "__main__":
    unittest.main()
