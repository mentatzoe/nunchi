"""Red-first contract tests for the accepted I-010A/I-010D/I-010E shapes (T005).

These exercise slice 020's own stdlib validation adapter in
``src/nunchi/observation.py`` directly against the exact accepted 010
shapes: an optional continuation capability on I-010A, the I-010D
fetch-request/fetch-page pair, the immutable observation-stage I-010E
record with no token field, honest unknown/unavailable facts, and
rejection of contract drift (invented fields, wrong envelopes).
"""

from __future__ import annotations

import unittest

from nunchi.observation import (
    validate_attention_receipt_record,
    validate_attention_request,
    validate_context_continuation,
)

MINIMAL_REQUEST = {
    "schema_version": 2,
    "request_id": "req-0001",
    "self": {"participant_id": "vigil", "actor_id": "discord:9001"},
    "room": {"platform": "discord", "id": "42", "continuity_scope_id": "discord:room:42#2026-07"},
    "actors": {"discord:9001": {"kind": "bot"}, "discord:1001": {"kind": "human"}},
    "events": [
        {
            "id": "e1",
            "type": "message",
            "author_id": "discord:1001",
            "text": "hello",
            "mentioned_actor_ids": [],
            "mentions_room": False,
        }
    ],
    "trigger_event_id": "e1",
    "coverage": {
        "has_more_before": False,
        "has_more_after": False,
        "has_gaps": False,
        "truncated_by": [],
        "continuity": "session-only",
        "has_restart_gap": False,
    },
}


class TestAttentionRequestContract(unittest.TestCase):
    def test_minimal_request_is_valid(self):
        self.assertEqual(validate_attention_request(MINIMAL_REQUEST), [])

    def test_optional_continuation_capability_is_representable(self):
        request = dict(MINIMAL_REQUEST)
        request["continuation"] = {
            "handle_id": "cont-1",
            "bound_to": {
                "participant_id": "vigil",
                "room_id": "42",
                "continuity_scope_id": "discord:room:42#2026-07",
                "trigger_event_id": "e1",
            },
            "can_fetch_before": True,
            "can_fetch_after": False,
            "can_fetch_around_event": False,
            "max_events_per_fetch": 20,
            "max_bytes_per_fetch": 16384,
        }
        self.assertEqual(validate_attention_request(request), [])

    def test_unknown_platform_facts_are_honest_omission_not_null(self):
        request = dict(MINIMAL_REQUEST)
        request["events"] = [dict(MINIMAL_REQUEST["events"][0])]
        del request["events"][0]  # replaced below
        request["events"] = [
            {
                "id": "e1",
                "type": "message",
                "author_id": "discord:1001",
                "text": "hello",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            }
        ]
        self.assertNotIn("timestamp", request["events"][0])
        self.assertEqual(validate_attention_request(request), [])

    def test_invented_envelope_field_rejects(self):
        request = dict(MINIMAL_REQUEST)
        request["interface"] = "AttentionRequestV2"
        self.assertTrue(validate_attention_request(request))

    def test_missing_required_field_rejects(self):
        request = {k: v for k, v in MINIMAL_REQUEST.items() if k != "trigger_event_id"}
        self.assertTrue(validate_attention_request(request))

    def test_wrong_schema_version_rejects(self):
        request = dict(MINIMAL_REQUEST)
        request["schema_version"] = 1
        self.assertTrue(validate_attention_request(request))


FETCH_REQUEST = {
    "request_id": "req-0002",
    "handle_id": "cont-1",
    "direction": "before",
    "max_events": 10,
    "max_bytes": 4096,
}

FETCH_PAGE = {
    "request_id": "req-0002",
    "handle_id": "cont-1",
    "room_id": "42",
    "continuity_scope_id": "discord:room:42#2026-07",
    "direction": "before",
    "anchor_event_id": "e1",
    "actors": {"discord:1001": {"kind": "human"}},
    "events": [],
    "coverage": {
        "has_more_before": False,
        "has_more_after": None,
        "has_gaps": False,
        "truncated_by": [],
        "continuity": "session-only",
        "has_restart_gap": False,
    },
}


class TestContextContinuationContract(unittest.TestCase):
    def test_fetch_request_is_valid(self):
        self.assertEqual(validate_context_continuation(FETCH_REQUEST), [])

    def test_fetch_page_is_valid(self):
        self.assertEqual(validate_context_continuation(FETCH_PAGE), [])

    def test_around_direction_requires_anchor(self):
        request = dict(FETCH_REQUEST)
        request["direction"] = "around"
        request.pop("anchor_event_id", None)
        self.assertTrue(validate_context_continuation(request))

    def test_fetch_request_has_no_inline_binding_fields(self):
        # FR-014: a fetch request never carries participant/room/continuity
        # binding fields inline; only the wire shape's own fields are legal.
        request = dict(FETCH_REQUEST)
        request["participant_id"] = "vigil"
        self.assertTrue(validate_context_continuation(request))

    def test_handles_and_cursors_stay_opaque_strings(self):
        request = dict(FETCH_REQUEST)
        request["cursor"] = 12345  # not an opaque string
        self.assertTrue(validate_context_continuation(request))


OBSERVATION_RECEIPT = {
    "request_id": "req-0001",
    "stage": "observation",
    "writer": "observation-provider",
    "body": {
        "schema_version": 2,
        "trigger_event_id": "e1",
        "continuity_scope_id": "discord:room:42#2026-07",
        "event_count": 1,
        "byte_count": 120,
        "coverage": MINIMAL_REQUEST["coverage"],
        "included_event_ids": ["e1"],
    },
}


class TestAttentionReceiptContract(unittest.TestCase):
    def test_observation_stage_record_is_valid(self):
        self.assertEqual(validate_attention_receipt_record(OBSERVATION_RECEIPT), [])

    def test_observation_body_carries_no_token_field(self):
        # FR-015: the closed observation body has no token field; a slice-local
        # addition is contract drift and must reject.
        record = {
            "request_id": "req-0001",
            "stage": "observation",
            "writer": "observation-provider",
            "body": dict(OBSERVATION_RECEIPT["body"], estimated_tokens=30),
        }
        self.assertTrue(validate_attention_receipt_record(record))

    def test_cross_owner_writer_rejects(self):
        record = dict(OBSERVATION_RECEIPT, writer="transport")
        self.assertTrue(validate_attention_receipt_record(record))

    def test_prefix_partial_receipt_is_valid_in_progress(self):
        # A stream ending at participant-host (silence) is valid-in-progress;
        # per-record validation does not require the full stream.
        record = {
            "request_id": "req-0001",
            "stage": "participant-host",
            "writer": "participant-host",
            "body": {
                "wake_source": "DEFER",
                "packet_event_count": 1,
                "packet_byte_count": 120,
                "delivered_event_ids": ["e1"],
                "expansion_calls": 0,
                "invoked": False,
                "outcome": "silent",
            },
        }
        # Only the stage-to-writer binding and envelope are checked per record;
        # the participant-host body shape itself is another owner's contract.
        errors = validate_attention_receipt_record(record)
        self.assertEqual(errors, [])

    def test_unknown_stage_rejects(self):
        record = dict(OBSERVATION_RECEIPT, stage="social-suppression")
        self.assertTrue(validate_attention_receipt_record(record))


if __name__ == "__main__":
    unittest.main()
