"""US1 storage/receipt tests: bounded outcome-neutral retention, request
correlation, singly-attested immutable observation-stage receipts, and
operational-error treatment (T007)."""

from __future__ import annotations

import unittest

from nunchi.observation import ObservationInputError, validate_attention_receipt_record
from tests.v2.observation.helpers import FIXTURE_ACTORS, candidate, make_message, make_provider, seed_room


class TestOutcomeNeutralRetention(unittest.TestCase):
    def test_retention_is_bounded_regardless_of_outcome(self):
        provider = make_provider(retention_max_events=3)
        events = [make_message(f"e{i}", "discord:1001", f"msg {i}") for i in range(1, 6)]
        seed_room(provider, events)
        snapshot = provider.snapshot(trigger_event_id="e5", max_events=10, max_bytes=65536)
        # Only the most recent 3 remain retained; earlier ones were evicted
        # by the bound alone, never by any attention/social outcome.
        self.assertEqual(len(provider._events), 3)
        self.assertTrue(snapshot["coverage"]["has_gaps"])

    def test_no_attention_outcome_parameter_exists_on_ingest(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi")
        # ingest() has no disposition/outcome parameter to special-case
        # retention on a prior attention result (FR-010).
        native_input = candidate(event, actors=FIXTURE_ACTORS)
        self.assertNotIn("attention_disposition", native_input)
        provider.ingest(native_input)
        self.assertEqual(len(provider._events), 1)


class TestRequestCorrelation(unittest.TestCase):
    def test_receipt_request_id_matches_snapshot_request_id(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi")
        seed_room(provider, [event])
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536, request_id="req-fixed")
        receipt = provider.build_observation_receipt(snapshot)
        self.assertEqual(receipt["request_id"], "req-fixed")
        self.assertEqual(snapshot["request_id"], "req-fixed")

    def test_auto_generated_request_ids_are_unique_per_snapshot(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi")
        seed_room(provider, [event])
        first = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        second = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        self.assertNotEqual(first["request_id"], second["request_id"])


class TestSinglyAttestedImmutableReceipt(unittest.TestCase):
    def test_observation_receipt_is_valid_and_stage_bound(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi")
        seed_room(provider, [event])
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        receipt = provider.build_observation_receipt(snapshot)
        self.assertEqual(receipt["stage"], "observation")
        self.assertEqual(receipt["writer"], "observation-provider")
        self.assertEqual(validate_attention_receipt_record(receipt), [])

    def test_receipt_body_carries_only_attestable_facts(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi")
        seed_room(provider, [event])
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        receipt = provider.build_observation_receipt(snapshot)
        body = receipt["body"]
        self.assertEqual(set(body), {
            "schema_version", "trigger_event_id", "continuity_scope_id",
            "event_count", "byte_count", "coverage", "included_event_ids",
        })
        # No later-stage fact (attention/participant-host/transport) leaks in.
        self.assertNotIn("classifier_disposition", body)
        self.assertNotIn("outcome", body)

    def test_receipt_is_a_fresh_object_each_call_never_mutated_in_place(self):
        provider = make_provider()
        event = make_message("e1", "discord:1001", "hi")
        seed_room(provider, [event])
        snapshot = provider.snapshot(trigger_event_id="e1", max_events=10, max_bytes=65536)
        first = provider.build_observation_receipt(snapshot)
        first["body"]["event_count"] = 999  # mutate the returned copy
        second = provider.build_observation_receipt(snapshot)
        self.assertEqual(second["body"]["event_count"], 1)


class TestOperationalErrorSeparation(unittest.TestCase):
    def test_authorized_event_failing_normalization_raises_not_silently_suppresses(self):
        provider = make_provider()
        bad_event = {"id": "e1", "type": "message", "author_id": "discord:1001"}  # missing text/mentions
        native_input = candidate(bad_event, actors=FIXTURE_ACTORS)
        with self.assertRaises(ObservationInputError):
            provider.ingest(native_input)
        # Nothing was retained; the failure is loud, not a silent no-wake.
        self.assertEqual(len(provider._events), 0)


if __name__ == "__main__":
    unittest.main()
