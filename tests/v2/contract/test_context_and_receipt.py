"""Contract tests for ``I-010D ContextContinuationV2@1`` and
``I-010E AttentionReceiptV2@1`` (slice 010, T005).

Red cases cover host-secret leakage, fetch-time binding validation
(expired-handle rejection and cross-binding cursor reuse,
runtime-adapter-only), the continuity-scope duplicate-ID collision between
a continuation page and its originating request (FR-003/FR-009,
runtime-adapter-only), immutable-stage and writer-ownership receipt
sequence rules (runtime-adapter-only), and explicit unknown/unavailable
outcomes. This file also runs the ``evals/v2/contract/downstream`` corpus
(wake, continuation, and receipt cases) through both validators.
"""

from __future__ import annotations

import unittest

from tests.v2.contract import schema_helpers as helpers
from tests.v2.contract.schema_helpers import (
    RECEIPT_STAGES,
    RECEIPT_WRITER_MAP,
    ContractCorpusMixin,
    assert_schema_verdict,
    check_cross_document_id_uniqueness,
    make_fetch_page,
    make_fetch_payload,
    make_fetch_request,
    make_receipt,
    make_receipt_stream,
    make_request,
    make_wake,
    validate_continuation_fetch,
    validate_receipt_stream,
)


class DownstreamCorpusSuite(ContractCorpusMixin, unittest.TestCase):
    CORPUS = "downstream"
    REQUIRED_SCENES = frozenset(
        {"S03", "S06", "S07", "S15", "S16", "010-Preattention-bypass", "010-V1"}
    )


class ContinuationShapeCases(unittest.TestCase):
    """FR-009: host-only fetch-request and fetch-page shapes."""

    def test_fetch_request_and_page_validate(self):
        assert_schema_verdict(self, "context-continuation", make_fetch_request(), "valid")
        assert_schema_verdict(self, "context-continuation", make_fetch_page(), "valid")

    def test_malformed_shape_matching_neither_union_member_rejects(self):
        assert_schema_verdict(self, "context-continuation", {"handle_id": "cont-7f3a"}, "invalid")

    def test_missing_handle_id_rejects(self):
        doc = make_fetch_request()
        del doc["handle_id"]
        assert_schema_verdict(self, "context-continuation", doc, "invalid")

    def test_around_direction_requires_anchor_event_id(self):
        doc = make_fetch_request(direction="around")
        assert_schema_verdict(self, "context-continuation", doc, "invalid")
        doc["anchor_event_id"] = "e3"
        assert_schema_verdict(self, "context-continuation", doc, "valid")

    def test_non_positive_fetch_budgets_reject(self):
        doc = make_fetch_request()
        doc["max_events"] = 0
        assert_schema_verdict(self, "context-continuation", doc, "invalid")

    def test_exhausted_page_omits_next_cursor(self):
        doc = make_fetch_page()
        del doc["next_cursor"]
        assert_schema_verdict(self, "context-continuation", doc, "valid")

    def test_page_returns_coverage(self):
        doc = make_fetch_page()
        del doc["coverage"]
        assert_schema_verdict(self, "context-continuation", doc, "invalid")


class HostSecretLeakageCases(unittest.TestCase):
    """FR-004/FR-009: continuation authority never reaches the classifier
    as a stray top-level field; the full `continuation` capability is
    legitimately representable on the wire document (FR-014)."""

    def test_stray_top_level_host_secret_fields_reject(self):
        for field, value in (
            ("continuation_handle", "cont-7f3a"),
            ("binding", {"participant_id": "vigil"}),
            ("cursor", "cur-1"),
            ("expires_at", "2026-07-17T02:00:00Z"),
        ):
            with self.subTest(field=field):
                doc = make_request(**{field: value})
                assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_wake_with_incomplete_continuation_rejects(self):
        doc = make_wake()
        doc["continuation"] = {"handle_id": "cont-7f3a"}
        assert_schema_verdict(self, "participant-wake", doc, "invalid")


class FetchTimeBindingCases(unittest.TestCase):
    """FR-012 ``binding-expiry`` class: behavioral, runtime-adapter-only.
    A fetch request carries no inline binding fields (FR-014); the host's
    actual call context is compared against the issued capability's exact
    ``bound_to`` independently. A known, unexpired handle alone does not
    establish correct binding or bounded authorization (rejection R10) —
    exact binding, direction authorization, and cap enforcement are each
    checked explicitly against the issued capability."""

    def test_fresh_fetch_with_minted_cursor_passes(self):
        payload = make_fetch_payload()
        payload["request"]["cursor"] = "cur-1"
        self.assertEqual([], validate_continuation_fetch(payload))

    def test_expired_handle_rejects_at_fetch_time(self):
        payload = make_fetch_payload(fetch_time="2026-07-17T03:00:00Z")
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("expired" in error for error in errors), errors)

    def test_unknown_handle_rejects(self):
        payload = make_fetch_payload()
        payload["request"]["handle_id"] = "cont-forged"
        self.assertTrue(validate_continuation_fetch(payload))

    def test_cross_binding_cursor_reuse_rejects(self):
        payload = make_fetch_payload()
        payload["request"]["cursor"] = "cur-x1"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("across bindings" in error for error in errors), errors)

    def test_never_minted_cursor_rejects(self):
        payload = make_fetch_payload()
        payload["request"]["cursor"] = "cur-forged"
        self.assertTrue(validate_continuation_fetch(payload))

    def test_host_context_mismatched_against_bound_to_rejects(self):
        # Rejection R10: a known, unexpired handle used outside its exact
        # bound context (participant/room/continuity-scope/trigger) must
        # not be treated as correct by construction.
        payload = make_fetch_payload()
        payload["host_context"]["room_id"] = "999"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("exact-binding mismatch" in error for error in errors), errors)

    def test_unauthorized_direction_rejects(self):
        # cont-7f3a's issued capability declares can_fetch_after: false.
        payload = make_fetch_payload()
        payload["request"]["direction"] = "after"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("not authorized" in error for error in errors), errors)

    def test_max_events_cap_overrun_rejects(self):
        payload = make_fetch_payload()
        payload["request"]["max_events"] = 21
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("max_events" in error and "exceeds" in error for error in errors), errors)

    def test_max_bytes_cap_overrun_rejects(self):
        payload = make_fetch_payload()
        payload["request"]["max_bytes"] = 16385
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("max_bytes" in error and "exceeds" in error for error in errors), errors)

    def test_valid_no_expiry_capability_passes(self):
        # The selected design's own example continuation carries no
        # expires_at member (rejection R10 attempt-4 finding): absence is
        # valid, not a validation failure.
        payload = make_fetch_payload()
        del payload["issued"][0]["expires_at"]
        self.assertEqual([], validate_continuation_fetch(payload))

    def test_missing_required_capability_field_rejects(self):
        payload = make_fetch_payload()
        del payload["issued"][0]["max_events_per_fetch"]
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("max_events_per_fetch" in error for error in errors), errors)

    def test_mistyped_capability_cap_rejects(self):
        payload = make_fetch_payload()
        payload["issued"][0]["max_events_per_fetch"] = "20"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("max_events_per_fetch" in error for error in errors), errors)

    def test_mistyped_direction_flag_rejects(self):
        payload = make_fetch_payload()
        payload["issued"][0]["can_fetch_before"] = "yes"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("can_fetch_before" in error for error in errors), errors)

    def test_incomplete_binding_on_both_sides_still_rejects(self):
        # Two equally incomplete objects must not pass the equality check
        # by virtue of matching each other (rejection R10 attempt-4 finding).
        payload = make_fetch_payload()
        del payload["issued"][0]["bound_to"]["participant_id"]
        del payload["host_context"]["participant_id"]
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("participant_id" in error for error in errors), errors)

    def test_mixed_timezone_aware_and_naive_timestamps_return_error_not_raise(self):
        payload = make_fetch_payload()
        payload["issued"][0]["expires_at"] = "2026-07-17T02:00:00"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("not comparable" in error for error in errors), errors)

    def test_array_request_handle_id_returns_error_not_raise(self):
        # Rejection R11: a malformed (unhashable) request handle_id must
        # never become a dictionary key.
        payload = make_fetch_payload()
        payload["request"]["handle_id"] = []
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("handle_id" in error for error in errors), errors)

    def test_object_request_handle_id_returns_error_not_raise(self):
        payload = make_fetch_payload()
        payload["request"]["handle_id"] = {}
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("handle_id" in error for error in errors), errors)

    def test_array_request_direction_returns_error_not_raise(self):
        payload = make_fetch_payload()
        payload["request"]["direction"] = []
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("direction" in error for error in errors), errors)

    def test_object_request_direction_returns_error_not_raise(self):
        payload = make_fetch_payload()
        payload["request"]["direction"] = {}
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("direction" in error for error in errors), errors)

    def test_array_issued_handle_id_returns_error_not_raise(self):
        payload = make_fetch_payload()
        payload["issued"][0]["handle_id"] = []
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("handle_id" in error for error in errors), errors)

    def test_object_issued_handle_id_returns_error_not_raise(self):
        payload = make_fetch_payload()
        payload["issued"][0]["handle_id"] = {}
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("handle_id" in error for error in errors), errors)

    def test_duplicate_issued_handle_id_with_conflicting_binding_rejects(self):
        # A host-issued opaque handle cannot be exactly bound to two
        # different contexts; duplicate identities must reject rather than
        # acquire order-dependent (last-write-wins) meaning (rejection R11).
        payload = make_fetch_payload()
        conflicting = dict(payload["issued"][0])
        conflicting["bound_to"] = {
            "participant_id": "someone-else",
            "room_id": "999",
            "continuity_scope_id": "discord:room:999#2026-07",
            "trigger_event_id": "e-other",
        }
        payload["issued"].append(conflicting)
        payload["host_context"] = dict(conflicting["bound_to"])
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("duplicate" in error or "ambiguous" in error for error in errors), errors)


class ContinuityScopeCollisionCases(unittest.TestCase):
    """FR-003/FR-009: a continuation page whose event IDs collide with the
    originating request rejects at fetch time under exact merge identity."""

    def test_colliding_page_rejects_in_runtime_adapter_only(self):
        request = make_request()
        page = make_fetch_page()
        page["events"][0]["id"] = "e1"
        # Both documents are schema-valid in isolation (oracle-expected-valid).
        assert_schema_verdict(self, "attention-request", request, "valid")
        assert_schema_verdict(self, "context-continuation", page, "valid")
        errors = check_cross_document_id_uniqueness(request, page)
        self.assertTrue(any("collides" in error for error in errors), errors)

    def test_disjoint_page_passes_merge_identity(self):
        self.assertEqual(
            [], check_cross_document_id_uniqueness(make_request(), make_fetch_page())
        )

    def test_duplicate_ids_inside_the_page_also_reject(self):
        page = make_fetch_page()
        page["events"].append(dict(page["events"][0]))
        self.assertTrue(check_cross_document_id_uniqueness(make_request(), page))


class ReceiptRecordCases(unittest.TestCase):
    """FR-010: single stage records — closed bodies per stage."""

    def test_each_stage_record_validates(self):
        for stage in RECEIPT_STAGES:
            with self.subTest(stage=stage):
                assert_schema_verdict(self, "attention-receipt", make_receipt(stage), "valid")

    def test_body_must_match_stage(self):
        doc = make_receipt("observation", body={"outcome": "silence"})
        assert_schema_verdict(self, "attention-receipt", doc, "invalid")

    def test_attention_outcomes_stay_separate(self):
        # Classifier outcome, operational error, and bypass are mutually
        # exclusive attention-stage bodies.
        mixed = make_receipt(
            "attention",
            body={
                "classifier_disposition": "WAKE",
                "effective_disposition": "WAKE",
                "classifier": {"name": "nunchi-classifier"},
                "evidence_event_ids": ["e1"],
                "routing_audit": {"valve": "none", "override_cause": "none", "margin_status": "active"},
                "error": {"code": "provider-failure", "detail": "classifier output failed validation"},
            },
        )
        assert_schema_verdict(self, "attention-receipt", mixed, "invalid")
        error = make_receipt(
            "attention",
            body={"error": {"code": "provider-failure", "detail": "classifier output failed validation"}},
        )
        assert_schema_verdict(self, "attention-receipt", error, "valid")
        missing_detail = make_receipt("attention", body={"error": {"code": "provider-failure"}})
        assert_schema_verdict(self, "attention-receipt", missing_detail, "invalid")

    def test_classifier_outcome_requires_policy_provenance(self):
        # @2 amendment A1 (c834e8c: "the effective policy and its source are
        # inspectable in receipts"): required on every classifier-outcome
        # attention body, not just the trusted-bypass variant.
        doc = make_receipt("attention")
        del doc["body"]["policy_provenance"]
        assert_schema_verdict(self, "attention-receipt", doc, "invalid")

    def test_error_operator_override_requires_both_wake_action_and_provenance(self):
        # @2 amendment A1 (c834e8c: "NO_WAKE is an explicit operator
        # override... receipted as operational failure policy"): wake_action
        # and policy_provenance are present together or both absent.
        ordinary = make_receipt(
            "attention", body={"error": {"code": "provider-failure", "detail": "provider timeout"}}
        )
        assert_schema_verdict(self, "attention-receipt", ordinary, "valid")
        overridden = make_receipt(
            "attention",
            body={
                "error": {"code": "provider-failure", "detail": "provider timeout"},
                "wake_action": "NO_WAKE",
                "policy_provenance": "trusted:profiles/default@2026-07",
            },
        )
        assert_schema_verdict(self, "attention-receipt", overridden, "valid")
        only_action = make_receipt(
            "attention",
            body={"error": {"code": "provider-failure", "detail": "provider timeout"}, "wake_action": "NO_WAKE"},
        )
        assert_schema_verdict(self, "attention-receipt", only_action, "invalid")
        only_provenance = make_receipt(
            "attention",
            body={
                "error": {"code": "provider-failure", "detail": "provider timeout"},
                "policy_provenance": "trusted:profiles/default@2026-07",
            },
        )
        assert_schema_verdict(self, "attention-receipt", only_provenance, "invalid")

    def test_bypass_attention_record_carries_trusted_provenance(self):
        # 010-Preattention-bypass: classifier_not_invoked plus provenance,
        # with no fabricated model judgment.
        body = {
            "classifier_not_invoked": True,
            "cause": "preattention-disabled",
            "policy_provenance": "host:vigil",
        }
        assert_schema_verdict(self, "attention-receipt", make_receipt("attention", body=body), "valid")
        missing_flag = make_receipt(
            "attention",
            body={"cause": "preattention-disabled", "policy_provenance": "host:vigil"},
        )
        assert_schema_verdict(self, "attention-receipt", missing_flag, "invalid")
        wrong_policy = make_receipt(
            "attention",
            body={
                "classifier_not_invoked": True,
                "cause": "operator-mute",
                "policy_provenance": "host:vigil",
            },
        )
        assert_schema_verdict(self, "attention-receipt", wrong_policy, "invalid")

    def test_participant_silence_is_a_distinct_staged_outcome(self):
        # S07: silence is neither suppression nor non-invocation.
        base_body = dict(helpers._STAGE_BODIES["participant-host"])
        silence = make_receipt("participant-host", body={**base_body, "outcome": "silent"})
        assert_schema_verdict(self, "attention-receipt", silence, "valid")
        contributed = make_receipt("participant-host")
        assert_schema_verdict(self, "attention-receipt", contributed, "valid")
        unknown = make_receipt("participant-host", body={**base_body, "outcome": "unknown"})
        assert_schema_verdict(self, "attention-receipt", unknown, "valid")

    def test_transport_unknown_and_unavailable_are_explicit(self):
        for delivery in ("unknown", "unavailable"):
            with self.subTest(delivery=delivery):
                doc = make_receipt("transport", body={"delivery": delivery})
                assert_schema_verdict(self, "attention-receipt", doc, "valid")
        invented = make_receipt("transport", body={"delivery": "probably-sent"})
        assert_schema_verdict(self, "attention-receipt", invented, "invalid")

    def test_social_ledger_in_receipt_body_rejects(self):
        base_body = dict(helpers._STAGE_BODIES["participant-host"])
        doc = make_receipt("participant-host", body={**base_body, "handled": False})
        assert_schema_verdict(self, "attention-receipt", doc, "invalid")

    def test_v1_envelope_rejects_as_receipt(self):
        v1 = {"verdict": "PASS", "classifier": "openrouter", "reasons": ["quiet"]}
        assert_schema_verdict(self, "attention-receipt", v1, "invalid")


class ReceiptWriterBindingCases(unittest.TestCase):
    """FR-010 per-record stage-to-writer binding (rejection R3, CHK082/CHK087):
    a record attributing one stage to another stage's owner is invalid as a
    single document in both validators — schema-expressible enforcement,
    reclassified from the stream-only receipt-sequence coverage (the moved
    corpus case is DWN-S06-306)."""

    def test_the_reviews_forged_record_rejects_as_a_single_document(self):
        # The exact rejected probe: stage observation written by transport.
        forged = make_receipt("observation", writer="transport")
        assert_schema_verdict(self, "attention-receipt", forged, "invalid")

    def test_every_cross_owner_stage_writer_pair_rejects(self):
        for stage in RECEIPT_STAGES:
            for writer in RECEIPT_WRITER_MAP.values():
                expected = "valid" if RECEIPT_WRITER_MAP[stage] == writer else "invalid"
                with self.subTest(stage=stage, writer=writer):
                    doc = make_receipt(stage, writer=writer)
                    assert_schema_verdict(self, "attention-receipt", doc, expected)


class ReceiptSequenceCases(unittest.TestCase):
    """FR-012 ``receipt-sequence`` class: behavioral, runtime-adapter-only.
    The multi-record stream checks (canonical order, skipped stages,
    earlier-stage mutation, request-ID correlation, and stream-level writer
    ownership) remain here in addition to the per-record binding above."""

    def test_full_canonical_stream_passes(self):
        self.assertEqual([], validate_receipt_stream(make_receipt_stream()))

    def test_prefix_partial_receipts_are_valid_in_progress(self):
        for upto in (1, 2, 3):
            with self.subTest(upto=upto):
                self.assertEqual([], validate_receipt_stream(make_receipt_stream(upto)))

    def test_silence_stream_ends_at_participant_host(self):
        # S07: an invoked participant that sends nothing is a prefix ending
        # at the participant-host stage.
        base_body = dict(helpers._STAGE_BODIES["participant-host"])
        stream = make_receipt_stream(3)
        stream[2] = make_receipt("participant-host", body={**base_body, "outcome": "silent"})
        self.assertEqual([], validate_receipt_stream(stream))

    def test_suppression_stream_ends_at_attention(self):
        stream = make_receipt_stream(2)
        stream[1] = make_receipt(
            "attention",
            body={
                "classifier_disposition": "SUPPRESS",
                "effective_disposition": "SUPPRESS",
                "classifier": {"name": "nunchi-classifier"},
                "evidence_event_ids": ["e1"],
                "routing_audit": {"valve": "none", "override_cause": "none", "margin_status": "active"},
                "policy_provenance": "trusted:profiles/default@2026-07",
            },
        )
        self.assertEqual([], validate_receipt_stream(stream))

    def test_bypass_contribution_stream_correlates_by_request_id(self):
        # S06: a direct contribution act after a bypass wake ties every
        # stage to the same request ID.
        stream = make_receipt_stream(4)
        stream[1] = make_receipt(
            "attention",
            body={
                "classifier_not_invoked": True,
                "cause": "preattention-disabled",
                "policy_provenance": "host:vigil",
            },
        )
        self.assertEqual([], validate_receipt_stream(stream))

    def test_mutating_an_earlier_stage_rejects(self):
        stream = make_receipt_stream(2)
        base_body = dict(helpers._STAGE_BODIES["observation"])
        mutation = make_receipt("observation", body={**base_body, "event_count": 99})
        errors = validate_receipt_stream(stream + [mutation])
        self.assertTrue(any("append-only" in error for error in errors), errors)

    def test_out_of_order_stages_reject(self):
        stream = [make_receipt("attention"), make_receipt("observation")]
        errors = validate_receipt_stream(stream)
        self.assertTrue(any("canonical order" in error for error in errors), errors)

    def test_skipping_a_stage_rejects(self):
        stream = [make_receipt("observation"), make_receipt("participant-host")]
        self.assertTrue(validate_receipt_stream(stream))

    def test_filling_another_owners_stage_rejects(self):
        stream = make_receipt_stream(3)
        stream[2] = make_receipt("participant-host", writer="attention-engine")
        errors = validate_receipt_stream(stream)
        self.assertTrue(any("another owner" in error for error in errors), errors)

    def test_writer_map_is_the_canonical_ownership(self):
        self.assertEqual(
            {
                "observation": "observation-provider",
                "attention": "attention-engine",
                "participant-host": "participant-host",
                "transport": "transport",
            },
            RECEIPT_WRITER_MAP,
        )

    def test_mixed_request_ids_reject(self):
        stream = make_receipt_stream(2)
        stream[1]["request_id"] = "req-9999"
        errors = validate_receipt_stream(stream)
        self.assertTrue(any("one request ID" in error for error in errors), errors)

    def test_empty_stream_rejects(self):
        self.assertTrue(validate_receipt_stream([]))


if __name__ == "__main__":
    unittest.main()
