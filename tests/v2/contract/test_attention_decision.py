"""Contract tests for ``I-010B AttentionDecisionV2@1`` (slice 010, T003;
reworked by T028 after rejection R2).

This file supersedes, in writing, T003's original framing of
"legacy-confidence-vector constraints on every ``status: ok`` decision":
per the spec's 2026-07-17 clarification session (FR-005/FR-007 as landed at
``89aef07``), the legacy verdict confidence vector is optional on
``status: ok`` and required exactly when the classifier disposition is
``SUPPRESS`` while the routing audit reports the margin ``active``. The red
cases below — including the sentinel-decoded
``"NaN"``/``"Infinity"``/``"-Infinity"`` non-finite ones — are keyed to that
conditional FR-007 rule: a margin-active candidate ``SUPPRESS`` without a
valid vector rejects, while ``WAKE``, ``DEFER``, and margin-retired
``SUPPRESS`` decisions stay valid with or without a well-formed vector.
Further red cases cover the closed FR-005 routing audit's cross-field rules
(applied valve, override cause, margin status, effective margin exactly
when the margin applied, trusted margin source only on a margin-applied
decision), the sibling ok-branch ``reasons`` placement, the forbidden
classifier fields on the ``preattention-disabled`` bypass branch (the full
FR-005 exclusion set), and the FR-013 advice rules keyed to the classifier
disposition (advice citing nonexistent event IDs is runtime-adapter-only).
The corpus suite runs the ``evals/v2/contract/attention-decision`` corpus
through both validators.
"""

from __future__ import annotations

import unittest

from tests.v2.contract.schema_helpers import (
    ContractCorpusMixin,
    assert_schema_verdict,
    check_advice_citations,
    decode_non_finite,
    make_advice,
    make_decision_bypass,
    make_decision_error,
    make_decision_ok,
    make_request,
    make_routing,
)


class AttentionDecisionCorpusSuite(ContractCorpusMixin, unittest.TestCase):
    CORPUS = "attention-decision"
    REQUIRED_SCENES = frozenset({"S05", "S08", "S09", "S16", "010-Preattention-bypass"})


class TransitionMatrixCases(unittest.TestCase):
    """FR-006 / SC-003 / S09: exactly four permitted ok pairs, each mapped
    onto its applied valve."""

    VALID_PAIRS = {
        ("WAKE", "WAKE"): "none",
        ("DEFER", "DEFER"): "classifier-defer",
        ("SUPPRESS", "DEFER"): "margin-defer",
        ("SUPPRESS", "SUPPRESS"): "none",
    }

    def test_only_four_ok_pairs_validate(self):
        dispositions = ("SUPPRESS", "WAKE", "DEFER")
        for classifier in dispositions:
            for effective in dispositions:
                pair = (classifier, effective)
                with self.subTest(pair=pair):
                    valve = self.VALID_PAIRS.get(pair, "none")
                    doc = make_decision_ok(classifier, effective, valve)
                    expected = "valid" if pair in self.VALID_PAIRS else "invalid"
                    assert_schema_verdict(self, "attention-decision", doc, expected)

    def test_governed_suppression_records_no_applied_valve(self):
        # S05: suppression legitimacy is explicit — valve none, override
        # cause none, and the margin-active vector requirement satisfied.
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "none")
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_suppression_with_a_widening_valve_rejects(self):
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "margin-defer")
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_missing_routing_cannot_validate_a_hard_stop(self):
        # S05: missing legitimacy evidence cannot support suppression.
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "none")
        del doc["routing"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_widening_preserves_exact_valve_and_cause(self):
        # S05/S08: the widened route names its valve and override cause.
        margin = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        assert_schema_verdict(self, "attention-decision", margin, "valid")
        policy = make_decision_ok("SUPPRESS", "DEFER", "policy-defer")
        assert_schema_verdict(self, "attention-decision", policy, "valid")

    def test_widened_suppression_with_cause_none_rejects(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        doc["routing"]["override_cause"] = "none"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_dual_defer_valves_stay_distinct(self):
        # S08: classifier-DEFER and margin-DEFER are separately auditable.
        classifier_defer = make_decision_ok("DEFER", "DEFER", "classifier-defer")
        assert_schema_verdict(self, "attention-decision", classifier_defer, "valid")
        mislabeled = make_decision_ok("DEFER", "DEFER", "margin-defer")
        assert_schema_verdict(self, "attention-decision", mislabeled, "invalid")

    def test_classifier_defer_cannot_carry_an_override_cause(self):
        doc = make_decision_ok("DEFER", "DEFER", "classifier-defer")
        doc["routing"]["override_cause"] = "margin"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")


class RoutingAuditCases(unittest.TestCase):
    """FR-005: the closed routing audit's cross-field rules (CHK084) and
    the sibling placement of ``reasons`` (CHK085)."""

    def test_margin_applied_requires_the_effective_margin(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        del doc["routing"]["effective_margin"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_a_retired_margin_cannot_apply(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        doc["routing"]["margin_status"] = "retired"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_effective_margin_forbidden_when_no_margin_applied(self):
        for valve in ("none", "classifier-defer", "policy-defer"):
            with self.subTest(valve=valve):
                pair = {
                    "none": ("WAKE", "WAKE"),
                    "classifier-defer": ("DEFER", "DEFER"),
                    "policy-defer": ("SUPPRESS", "DEFER"),
                }[valve]
                doc = make_decision_ok(pair[0], pair[1], valve)
                doc["routing"]["effective_margin"] = 0.12
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_margin_source_only_on_a_margin_applied_decision(self):
        allowed = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        allowed["routing"]["margin_source"] = "trusted:profiles/default@2026-07"
        assert_schema_verdict(self, "attention-decision", allowed, "valid")
        forbidden = make_decision_ok()
        forbidden["routing"]["margin_source"] = "trusted:profiles/default@2026-07"
        assert_schema_verdict(self, "attention-decision", forbidden, "invalid")

    def test_valve_and_override_cause_pair_exactly(self):
        wrong_none = make_decision_ok()
        wrong_none["routing"]["override_cause"] = "margin"
        assert_schema_verdict(self, "attention-decision", wrong_none, "invalid")
        wrong_policy = make_decision_ok("SUPPRESS", "DEFER", "policy-defer")
        wrong_policy["routing"]["override_cause"] = "margin"
        assert_schema_verdict(self, "attention-decision", wrong_policy, "invalid")

    def test_margin_status_is_always_recorded(self):
        doc = make_decision_ok()
        del doc["routing"]["margin_status"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_out_of_range_effective_margin_rejects(self):
        for value in (0, -0.1, 1.5):
            with self.subTest(value=value):
                doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
                doc["routing"]["effective_margin"] = value
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_reasons_is_a_required_sibling_field(self):
        doc = make_decision_ok()
        del doc["reasons"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_reasons_never_lives_inside_the_routing_audit(self):
        doc = make_decision_ok()
        doc["routing"]["reasons"] = ["misplaced audit material"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_empty_reasons_stays_valid_audit_material(self):
        doc = make_decision_ok(reasons=[])
        assert_schema_verdict(self, "attention-decision", doc, "valid")


class LegacyConfidenceCases(unittest.TestCase):
    """FR-007 (conditional, superseding T003's every-ok-decision framing):
    required exactly for a margin-active candidate ``SUPPRESS``; optional —
    and permitted — on ``WAKE``, ``DEFER``, and margin-retired
    ``SUPPRESS``; exactly four finite [0,1] keys when present."""

    @staticmethod
    def _margin_active_suppression(**overrides):
        return make_decision_ok("SUPPRESS", "SUPPRESS", "none", **overrides)

    def test_margin_active_suppression_without_vector_rejects(self):
        # The decisive R2 red case: a margin-active candidate SUPPRESS
        # without the vector cannot validate.
        doc = self._margin_active_suppression()
        del doc["legacy_confidence"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_wake_and_defer_without_the_optional_vector_stay_valid(self):
        wake = make_decision_ok()
        del wake["legacy_confidence"]
        assert_schema_verdict(self, "attention-decision", wake, "valid")
        defer = make_decision_ok("DEFER", "DEFER", "classifier-defer")
        del defer["legacy_confidence"]
        assert_schema_verdict(self, "attention-decision", defer, "valid")

    def test_margin_retired_suppression_without_vector_stays_valid(self):
        doc = self._margin_active_suppression()
        doc["routing"]["margin_status"] = "retired"
        del doc["legacy_confidence"]
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_vector_presence_never_invalidates_an_ok_decision(self):
        # CHK088: the permissive side — a well-formed vector may accompany
        # WAKE, DEFER, or a margin-retired SUPPRESS.
        retired = self._margin_active_suppression()
        retired["routing"]["margin_status"] = "retired"
        for doc in (
            make_decision_ok(),
            make_decision_ok("DEFER", "DEFER", "classifier-defer"),
            retired,
        ):
            assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_margin_widened_suppression_requires_the_vector_too(self):
        # SUPPRESS->DEFER via margin-defer implies margin active, so the
        # candidate-SUPPRESS vector requirement applies.
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        del doc["legacy_confidence"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_missing_key_rejects(self):
        doc = self._margin_active_suppression()
        del doc["legacy_confidence"]["ASK"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_extra_key_rejects(self):
        doc = self._margin_active_suppression()
        doc["legacy_confidence"]["MUMBLE"] = 0.2
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_out_of_range_values_reject(self):
        for value in (1.5, -0.1, 2, -1):
            with self.subTest(value=value):
                doc = self._margin_active_suppression()
                doc["legacy_confidence"]["SPEAK"] = value
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_boundary_values_are_on_scale(self):
        doc = self._margin_active_suppression()
        doc["legacy_confidence"] = {"PASS": 0, "ACK": 1, "ASK": 0.0, "SPEAK": 1.0}
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_sentinel_decoded_non_finite_values_cannot_support_suppression(self):
        # Strict JSON cannot carry non-finite literals; the corpus loader
        # decodes the reserved sentinel strings once, and both validators
        # must reject the decoded value on the margin-active suppression
        # where the vector is load-bearing (FR-007).
        for sentinel in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(sentinel=sentinel):
                doc = self._margin_active_suppression()
                doc["legacy_confidence"]["SPEAK"] = sentinel
                decoded = decode_non_finite(doc)
                self.assertIsInstance(decoded["legacy_confidence"]["SPEAK"], float)
                assert_schema_verdict(self, "attention-decision", decoded, "invalid")

    def test_malformed_present_vector_rejects_even_where_optional(self):
        # Present-but-malformed evidence rejects on every ok decision, not
        # only where the vector is required.
        doc = make_decision_ok()
        doc["legacy_confidence"]["PASS"] = True
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_string_confidence_rejects(self):
        doc = self._margin_active_suppression()
        doc["legacy_confidence"]["ACK"] = "0.5"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")


class AdviceRuleCases(unittest.TestCase):
    """FR-013: advice is keyed to classifier disposition ``WAKE`` and every
    citation must reference a request-supplied event ID."""

    def test_wake_with_grounded_advice_is_valid(self):
        doc = make_decision_ok(advice=make_advice())
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_advice_on_classifier_defer_rejects(self):
        doc = make_decision_ok("DEFER", "DEFER", "classifier-defer", advice=make_advice())
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_advice_on_suppression_rejects(self):
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "none", advice=make_advice())
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_advice_on_widened_defer_rejects(self):
        # The key is the classifier disposition, not the effective one.
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer", advice=make_advice())
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_advice_without_citations_rejects(self):
        doc = make_decision_ok(advice={"summary": "ungrounded", "evidence_event_ids": []})
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_advice_citing_nonexistent_event_is_runtime_adapter_only(self):
        request = make_request()
        decision = make_decision_ok(advice=make_advice(evidence_event_ids=["e-ghost"]))
        # Each document is schema-valid in isolation (oracle-expected-valid).
        assert_schema_verdict(self, "attention-request", request, "valid")
        assert_schema_verdict(self, "attention-decision", decision, "valid")
        self.assertTrue(check_advice_citations(decision, request))

    def test_advice_citing_supplied_events_passes_the_relational_check(self):
        request = make_request()
        decision = make_decision_ok(advice=make_advice(evidence_event_ids=["e1", "e3"]))
        self.assertEqual([], check_advice_citations(decision, request))


class BypassBranchCases(unittest.TestCase):
    """FR-005 / 010-Preattention-bypass: ``status: bypass`` carries exactly
    cause ``preattention-disabled`` and excludes the full FR-005 set —
    classifier/effective disposition, classifier audit, reasons, evidence,
    legacy confidence vector, routing audit, and advice (CHK086)."""

    def test_bypass_is_valid_without_classifier_fields(self):
        assert_schema_verdict(self, "attention-decision", make_decision_bypass(), "valid")

    def test_the_full_exclusion_set_rejects_on_bypass(self):
        forbidden = {
            "classifier_disposition": "WAKE",
            "effective_disposition": "WAKE",
            "classifier_audit": {"model": "openrouter/test-model"},
            "advice": make_advice(),
            "reasons": ["should not exist"],
            "legacy_confidence": {"PASS": 0.1, "ACK": 0.2, "ASK": 0.3, "SPEAK": 0.4},
            "evidence_event_ids": ["e1"],
            "routing": make_routing(),
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                doc = make_decision_bypass(**{field: value})
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_bypass_requires_exact_cause(self):
        doc = make_decision_bypass(cause="trusted-bypass")
        assert_schema_verdict(self, "attention-decision", doc, "invalid")
        missing = make_decision_bypass()
        del missing["cause"]
        assert_schema_verdict(self, "attention-decision", missing, "invalid")


class ErrorBranchCases(unittest.TestCase):
    """S09: malformed output validates only as tagged operational error."""

    def test_error_kinds_validate(self):
        for kind in (
            "malformed-model-output",
            "invalid-transition",
            "invalid-legacy-confidence",
            "provider-failure",
            "runtime-failure",
        ):
            with self.subTest(kind=kind):
                assert_schema_verdict(self, "attention-decision", make_decision_error(kind), "valid")

    def test_unknown_error_kind_rejects(self):
        assert_schema_verdict(
            self, "attention-decision", make_decision_error("social-suppression"), "invalid"
        )

    def test_error_branch_cannot_carry_dispositions(self):
        # Malformed transition evidence must not fabricate suppression.
        doc = make_decision_error("invalid-transition", effective_disposition="SUPPRESS")
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_status_must_be_closed_union(self):
        doc = make_decision_ok()
        doc["status"] = "maybe"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")


class LedgerRejectionCases(unittest.TestCase):
    """S16: no participant reply and no social-ledger state on decisions."""

    def test_reply_bearing_fields_reject(self):
        for field in ("reply", "reply_text", "message"):
            with self.subTest(field=field):
                doc = make_decision_ok(**{field: "sure, sending now"})
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_social_ledger_fields_reject(self):
        for field, value in (("handled", True), ("owed", ["reply"]), ("open", True)):
            with self.subTest(field=field):
                doc = make_decision_ok(**{field: value})
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_v1_result_envelope_rejects(self):
        v1_result = {
            "verdict": "SPEAK",
            "classifier": "openrouter",
            "confidences": {"PASS": 0.1, "ACK": 0.1, "ASK": 0.1, "SPEAK": 0.7},
            "context_checked": ["ctx-1"],
            "reasons": ["directly addressed"],
        }
        assert_schema_verdict(self, "attention-decision", v1_result, "invalid")


if __name__ == "__main__":
    unittest.main()
