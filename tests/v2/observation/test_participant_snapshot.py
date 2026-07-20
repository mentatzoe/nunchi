from __future__ import annotations

import unittest

from nunchi.observation import ObservationInputError
from tests.v2.observation.helpers import (
    FIXTURE_ACTORS,
    candidate,
    make_message,
    make_provider,
)


class ParticipantSnapshotCases(unittest.TestCase):
    def setUp(self):
        self.provider = make_provider()
        for index in range(1, 4):
            self.provider.ingest(
                candidate(
                    make_message(f"e{index}", "discord:1001", f"message {index}"),
                    actors=FIXTURE_ACTORS,
                )
            )
        self.attention = self.provider.snapshot(
            trigger_event_id="e1",
            request_id="req-live-refresh",
            max_events=10,
            max_bytes=65536,
        )

    def test_refresh_requires_an_attested_attention_request(self):
        with self.assertRaises(ObservationInputError):
            self.provider.participant_snapshot(
                trigger_event_id="e1",
                request_id="req-live-refresh",
                max_events=3,
                max_bytes=65536,
            )

    def test_refresh_keeps_trigger_and_current_tail_without_second_receipt(self):
        receipt = self.provider.build_observation_receipt(self.attention)
        self.assertEqual(receipt["stage"], "observation")
        for index in range(4, 9):
            self.provider.ingest(
                candidate(
                    make_message(f"e{index}", "discord:1001", f"message {index}"),
                    actors=FIXTURE_ACTORS,
                )
            )

        refreshed = self.provider.participant_snapshot(
            trigger_event_id="e1",
            request_id="req-live-refresh",
            max_events=3,
            max_bytes=65536,
        )
        self.assertEqual([event["id"] for event in refreshed["events"]], ["e1", "e7", "e8"])
        self.assertEqual(refreshed["request_id"], "req-live-refresh")
        self.assertTrue(refreshed["coverage"]["has_more_after"])
        self.assertTrue(refreshed["coverage"]["has_gaps"])
        self.assertEqual(self.provider._pending_receipts, {})
        with self.assertRaises(ObservationInputError):
            self.provider.build_observation_receipt(refreshed)

    def test_cited_evidence_precedes_optional_tail_and_budget_failure_is_loud(self):
        self.provider.build_observation_receipt(self.attention)
        for index in range(4, 9):
            self.provider.ingest(
                candidate(
                    make_message(f"e{index}", "discord:1001", f"message {index}"),
                    actors=FIXTURE_ACTORS,
                )
            )
        refreshed = self.provider.participant_snapshot(
            trigger_event_id="e1",
            request_id="req-live-refresh",
            max_events=3,
            max_bytes=65536,
            required_event_ids=("e2",),
        )
        self.assertEqual([event["id"] for event in refreshed["events"]], ["e1", "e2", "e8"])
        with self.assertRaises(ObservationInputError):
            self.provider.participant_snapshot(
                trigger_event_id="e1",
                request_id="req-live-refresh",
                max_events=1,
                max_bytes=65536,
                required_event_ids=("e2",),
            )


if __name__ == "__main__":
    unittest.main()
