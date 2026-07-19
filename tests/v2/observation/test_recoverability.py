"""US3 recoverability reference tests (T020): restart/backfill,
outcome-neutral later-hearing, session-only, unknown, known-gap, and
suppression-eligibility reference behavior."""

from __future__ import annotations

import unittest

from evals.v2.observation.capabilities.reference_provider import make_reference_provider
from tests.v2.observation.helpers import FIXTURE_ACTORS, candidate, make_message, make_provider


class TestGovernedSuppressionRecoverability(unittest.TestCase):
    """S05: an event later hypothetically suppressed remains ordinarily
    available under claimed continuity within the retention horizon."""

    def test_earlier_event_remains_available_for_a_later_snapshot(self):
        provider = make_provider()
        earlier = make_message("e1", "discord:1001", "earlier remark")
        provider.ingest(candidate(earlier, actors=FIXTURE_ACTORS))
        later = make_message("e2", "discord:1001", "later remark")
        provider.ingest(candidate(later, actors=FIXTURE_ACTORS))
        snapshot = provider.snapshot(trigger_event_id="e2", max_events=10, max_bytes=65536)
        self.assertIn("e1", {event["id"] for event in snapshot["events"]})

    def test_no_outcome_derived_retention_special_case(self):
        # Retention does not depend on whether e1 was ever "suppressed" —
        # the provider has no such concept at all (FR-010).
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi")
        provider.ingest(candidate(event, actors=FIXTURE_ACTORS))
        self.assertFalse(hasattr(provider, "suppressed_event_ids"))


class TestRestartSafeVariant(unittest.TestCase):
    def test_restart_safe_variant_retains_content_and_identity_after_restart(self):
        reference = make_reference_provider(
            "restart-safe",
            participant_id="vigil", actor_id="discord:9001",
            platform="discord", room_id="42", continuity_scope_id="discord:room:42#2026-07",
        )
        event = make_message("e1", "discord:1001", "before restart")
        reference.ingest(candidate(event, actors=FIXTURE_ACTORS))
        reference.simulate_restart()
        trigger = make_message("e2", "discord:1001", "after restart")
        reference.ingest(candidate(trigger, actors=FIXTURE_ACTORS))
        snapshot = reference.snapshot(trigger_event_id="e2", max_events=10, max_bytes=65536)
        by_id = {ev["id"]: ev for ev in snapshot["events"]}
        self.assertIn("e1", by_id)
        self.assertEqual(by_id["e1"]["text"], "before restart")
        self.assertEqual(snapshot["coverage"]["continuity"], "restart-safe")


class TestSessionOnlyVariant(unittest.TestCase):
    def test_session_only_variant_reports_a_restart_gap_not_fabricated_history(self):
        reference = make_reference_provider(
            "session-only",
            participant_id="vigil", actor_id="discord:9001",
            platform="discord", room_id="42", continuity_scope_id="discord:room:42#2026-07",
        )
        event = make_message("e1", "discord:1001", "before restart")
        reference.ingest(candidate(event, actors=FIXTURE_ACTORS))
        reference.simulate_restart()
        trigger = make_message("e2", "discord:1001", "after restart")
        reference.ingest(candidate(trigger, actors=FIXTURE_ACTORS))
        snapshot = reference.snapshot(trigger_event_id="e2", max_events=10, max_bytes=65536)
        ids = {ev["id"] for ev in snapshot["events"]}
        self.assertNotIn("e1", ids)  # not fabricated back into existence
        self.assertEqual(snapshot["coverage"]["continuity"], "session-only")
        self.assertTrue(snapshot["coverage"]["has_gaps"])
        self.assertIs(snapshot["coverage"]["has_restart_gap"], True)
        self.assertIn("e1", reference.known_gap_event_ids)


class TestUnknownContinuityVariant(unittest.TestCase):
    def test_unknown_variant_never_upgrades_to_restart_safe_by_inference(self):
        reference = make_reference_provider(
            "unknown",
            participant_id="vigil", actor_id="discord:9001",
            platform="discord", room_id="42", continuity_scope_id="discord:room:42#2026-07",
        )
        event = make_message("e1", "discord:1001", "hi")
        reference.ingest(candidate(event, actors=FIXTURE_ACTORS))
        snapshot = reference.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        self.assertEqual(snapshot["coverage"]["continuity"], "unknown")
        self.assertIsNone(snapshot["coverage"]["has_restart_gap"])


class TestKnownGapVariant(unittest.TestCase):
    def test_known_gap_variant_reports_the_dropped_tail_honestly(self):
        reference = make_reference_provider(
            "known-gap",
            participant_id="vigil", actor_id="discord:9001",
            platform="discord", room_id="42", continuity_scope_id="discord:room:42#2026-07",
        )
        events = [make_message(f"e{i}", "discord:1001", f"m{i}") for i in range(1, 5)]
        for event in events:
            reference.ingest(candidate(event, actors=FIXTURE_ACTORS))
        reference.simulate_restart()
        self.assertTrue(reference.known_gap_event_ids)  # half the history is an honest gap
        self.assertLess(len(reference.provider._events), 4)
        trigger = make_message("e5", "discord:1001", "after restart")
        reference.ingest(candidate(trigger, actors=FIXTURE_ACTORS))
        snapshot = reference.snapshot(
            trigger_event_id="e5", max_events=10, max_bytes=65536,
        )
        self.assertTrue(snapshot["coverage"]["has_gaps"])
        self.assertIs(snapshot["coverage"]["has_restart_gap"], True)


class TestSuppressionEligibilityBoundary(unittest.TestCase):
    def test_reference_pass_alone_does_not_certify_a_real_surface(self):
        reference = make_reference_provider(
            "restart-safe",
            participant_id="vigil", actor_id="discord:9001",
            platform="discord", room_id="42", continuity_scope_id="discord:room:42#2026-07",
        )
        # No attribute on the reference variant claims installed-surface
        # eligibility; that proof is an explicit downstream obligation.
        self.assertFalse(hasattr(reference, "suppression_eligible"))
        self.assertFalse(hasattr(reference, "certified"))


if __name__ == "__main__":
    unittest.main()
