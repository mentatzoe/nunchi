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
    """FR-009: host-only request and page shapes."""

    def test_fetch_request_and_page_validate(self):
        assert_schema_verdict(self, "context-continuation", make_fetch_request(), "valid")
        assert_schema_verdict(self, "context-continuation", make_fetch_page(), "valid")

    def test_kind_union_is_closed(self):
        doc = make_fetch_request(kind="fetch-stream")
        assert_schema_verdict(self, "context-continuation", doc, "invalid")

    def test_missing_binding_rejects(self):
        doc = make_fetch_request()
        del doc["binding"]
        assert_schema_verdict(self, "context-continuation", doc, "invalid")

    def test_partial_binding_rejects(self):
        doc = make_fetch_request()
        del doc["binding"]["trigger_event_id"]
        assert_schema_verdict(self, "context-continuation", doc, "invalid")

    def test_non_positive_fetch_budgets_reject(self):
        doc = make_fetch_request()
        doc["budgets"]["max_events"] = 0
        assert_schema_verdict(self, "context-continuation", doc, "invalid")

    def test_exhausted_page_uses_null_cursor(self):
        doc = make_fetch_page(cursor_next=None)
        assert_schema_verdict(self, "context-continuation", doc, "valid")

    def test_page_returns_coverage(self):
        doc = make_fetch_page()
        del doc["coverage"]
        assert_schema_verdict(self, "context-continuation", doc, "invalid")


class HostSecretLeakageCases(unittest.TestCase):
    """FR-004/FR-009: continuation authority never reaches the classifier."""

    def test_request_projection_with_host_secrets_rejects(self):
        for field, value in (
            ("continuation", {"handle": "cont-7f3a", "cursor": "cur-1"}),
            ("continuation_handle", "cont-7f3a"),
            ("binding", {"participant_id": "vigil"}),
            ("cursor", "cur-1"),
            ("expires_at", "2026-07-17T02:00:00Z"),
        ):
            with self.subTest(field=field):
                doc = make_request(**{field: value})
                assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_wake_observation_with_host_secrets_rejects(self):
        doc = make_wake()
        doc["observation"]["continuation"] = {"handle": "cont-7f3a"}
        assert_schema_verdict(self, "participant-wake", doc, "invalid")


class FetchTimeBindingCases(unittest.TestCase):
    """FR-012 ``binding-expiry`` class: behavioral, runtime-adapter-only."""

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
        payload["request"]["handle"] = "cont-forged"
        self.assertTrue(validate_continuation_fetch(payload))

    def test_changed_binding_rejects(self):
        # US3 scenario 2: a fetch changing participant, room, continuity
        # scope, or trigger binding is rejected.
        payload = make_fetch_payload()
        payload["request"]["binding"]["room_id"] = "discord:room:77"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("binding" in error for error in errors), errors)

    def test_cross_binding_cursor_reuse_rejects(self):
        payload = make_fetch_payload()
        payload["request"]["cursor"] = "cur-x1"
        errors = validate_continuation_fetch(payload)
        self.assertTrue(any("across bindings" in error for error in errors), errors)

    def test_never_minted_cursor_rejects(self):
        payload = make_fetch_payload()
        payload["request"]["cursor"] = "cur-forged"
        self.assertTrue(validate_continuation_fetch(payload))


class ContinuityScopeCollisionCases(unittest.TestCase):
    """FR-003/FR-009: a continuation page whose event IDs collide with the
    originating request rejects at fetch time under exact merge identity."""

    def test_colliding_page_rejects_in_runtime_adapter_only(self):
        request = make_request()
        page = make_fetch_page()
        page["events"][0]["event_id"] = "e1"
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
                "policy_provenance": "profiles/default@2026-07",
                "error_kind": "provider-failure",
            },
        )
        assert_schema_verdict(self, "attention-receipt", mixed, "invalid")
        error = make_receipt("attention", body={"error_kind": "provider-failure"})
        assert_schema_verdict(self, "attention-receipt", error, "valid")

    def test_bypass_attention_record_carries_trusted_provenance(self):
        # 010-Preattention-bypass: classifier_not_invoked plus provenance,
        # with no fabricated model judgment.
        body = {
            "classifier_not_invoked": True,
            "bypass_provenance": {"policy": "preattention-disabled", "attested_by": "host:vigil"},
        }
        assert_schema_verdict(self, "attention-receipt", make_receipt("attention", body=body), "valid")
        missing_flag = make_receipt(
            "attention",
            body={"bypass_provenance": {"policy": "preattention-disabled", "attested_by": "host:vigil"}},
        )
        assert_schema_verdict(self, "attention-receipt", missing_flag, "invalid")
        wrong_policy = make_receipt(
            "attention",
            body={
                "classifier_not_invoked": True,
                "bypass_provenance": {"policy": "operator-mute", "attested_by": "host:vigil"},
            },
        )
        assert_schema_verdict(self, "attention-receipt", wrong_policy, "invalid")

    def test_participant_silence_is_a_distinct_staged_outcome(self):
        # S07: silence is neither suppression nor non-invocation.
        silence = make_receipt("participant-host", body={"outcome": "silence"})
        assert_schema_verdict(self, "attention-receipt", silence, "valid")
        contributed = make_receipt("participant-host")
        assert_schema_verdict(self, "attention-receipt", contributed, "valid")
        silent_with_action = make_receipt(
            "participant-host", body={"outcome": "silence", "action_ref": "discord:msg:1"}
        )
        assert_schema_verdict(self, "attention-receipt", silent_with_action, "invalid")

    def test_transport_unknown_and_unavailable_are_explicit(self):
        for delivery in ("unknown", "unavailable"):
            with self.subTest(delivery=delivery):
                doc = make_receipt("transport", body={"delivery": delivery})
                assert_schema_verdict(self, "attention-receipt", doc, "valid")
        invented = make_receipt("transport", body={"delivery": "probably-sent"})
        assert_schema_verdict(self, "attention-receipt", invented, "invalid")

    def test_social_ledger_in_receipt_body_rejects(self):
        doc = make_receipt("participant-host", body={"outcome": "silence", "handled": False})
        assert_schema_verdict(self, "attention-receipt", doc, "invalid")

    def test_v1_envelope_rejects_as_receipt(self):
        v1 = {"verdict": "PASS", "classifier": "openrouter", "reasons": ["quiet"]}
        assert_schema_verdict(self, "attention-receipt", v1, "invalid")


class ReceiptSequenceCases(unittest.TestCase):
    """FR-012 ``receipt-sequence`` class: behavioral, runtime-adapter-only."""

    def test_full_canonical_stream_passes(self):
        self.assertEqual([], validate_receipt_stream(make_receipt_stream()))

    def test_prefix_partial_receipts_are_valid_in_progress(self):
        for upto in (1, 2, 3):
            with self.subTest(upto=upto):
                self.assertEqual([], validate_receipt_stream(make_receipt_stream(upto)))

    def test_silence_stream_ends_at_participant_host(self):
        # S07: an invoked participant that sends nothing is a prefix ending
        # at the participant-host stage.
        stream = make_receipt_stream(3)
        stream[2] = make_receipt("participant-host", body={"outcome": "silence"})
        self.assertEqual([], validate_receipt_stream(stream))

    def test_suppression_stream_ends_at_attention(self):
        stream = make_receipt_stream(2)
        stream[1] = make_receipt(
            "attention",
            body={
                "classifier_disposition": "SUPPRESS",
                "effective_disposition": "SUPPRESS",
                "policy_provenance": "profiles/default@2026-07",
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
                "bypass_provenance": {"policy": "preattention-disabled", "attested_by": "host:vigil"},
            },
        )
        self.assertEqual([], validate_receipt_stream(stream))

    def test_mutating_an_earlier_stage_rejects(self):
        stream = make_receipt_stream(2)
        mutation = make_receipt("observation", body={"event_count": 99, "visibility": "complete"})
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
