"""Contract tests for ``I-010B AttentionDecisionV2@1`` (slice 010, T003).

Red cases cover forbidden classifier fields on the ``preattention-disabled``
bypass branch, the legacy-confidence-vector constraints on every
``status: ok`` decision (exactly the four ``PASS``/``ACK``/``ASK``/``SPEAK``
keys, finite values in [0, 1] including the sentinel-decoded
``"NaN"``/``"Infinity"``/``"-Infinity"`` red cases, extra keys forbidden),
and the FR-013 advice rules keyed to the classifier disposition (advice on
``DEFER`` or ``SUPPRESS`` rejects; advice citing nonexistent event IDs is
runtime-adapter-only). The corpus suite runs the
``evals/v2/contract/attention-decision`` corpus through both validators.
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
)


class AttentionDecisionCorpusSuite(ContractCorpusMixin, unittest.TestCase):
    CORPUS = "attention-decision"
    REQUIRED_SCENES = frozenset({"S05", "S08", "S09", "S16", "010-Preattention-bypass"})


class TransitionMatrixCases(unittest.TestCase):
    """FR-006 / SC-003 / S09: exactly four permitted ok pairs."""

    VALID_PAIRS = {
        ("WAKE", "WAKE"): "wake",
        ("DEFER", "DEFER"): "classifier-defer",
        ("SUPPRESS", "DEFER"): "margin-defer",
        ("SUPPRESS", "SUPPRESS"): "suppress-no-override",
    }

    def test_only_four_ok_pairs_validate(self):
        dispositions = ("SUPPRESS", "WAKE", "DEFER")
        for classifier in dispositions:
            for effective in dispositions:
                pair = (classifier, effective)
                with self.subTest(pair=pair):
                    route = self.VALID_PAIRS.get(pair, "wake")
                    doc = make_decision_ok(classifier, effective, route)
                    if pair == ("SUPPRESS", "DEFER"):
                        doc["routing"]["override_cause"] = "uncertainty margin widened the route"
                    expected = "valid" if pair in self.VALID_PAIRS else "invalid"
                    assert_schema_verdict(self, "attention-decision", doc, expected)

    def test_governed_suppression_names_the_no_override_route(self):
        # S05: suppression legitimacy is explicit.
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "suppress-no-override")
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_suppression_with_wrong_route_rejects(self):
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "margin-defer")
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_missing_routing_cannot_validate_a_hard_stop(self):
        # S05: missing legitimacy evidence cannot support suppression.
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "suppress-no-override")
        del doc["routing"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_margin_widening_preserves_exact_valve_and_cause(self):
        # S05/S08: the widened route names its valve and override cause.
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        doc["routing"]["override_cause"] = "uncertainty margin widened the route"
        assert_schema_verdict(self, "attention-decision", doc, "valid")
        delegated = make_decision_ok("SUPPRESS", "DEFER", "delegation-defer")
        delegated["routing"]["override_cause"] = "delegation policy widened the route"
        assert_schema_verdict(self, "attention-decision", delegated, "valid")

    def test_widened_suppression_without_override_cause_rejects(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_dual_defer_valves_stay_distinct(self):
        # S08: classifier-DEFER and margin-DEFER are separately auditable.
        classifier_defer = make_decision_ok("DEFER", "DEFER", "classifier-defer")
        assert_schema_verdict(self, "attention-decision", classifier_defer, "valid")
        mislabeled = make_decision_ok("DEFER", "DEFER", "margin-defer")
        assert_schema_verdict(self, "attention-decision", mislabeled, "invalid")

    def test_classifier_defer_cannot_carry_override_cause(self):
        doc = make_decision_ok("DEFER", "DEFER", "classifier-defer")
        doc["routing"]["override_cause"] = "spurious"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")


class LegacyConfidenceCases(unittest.TestCase):
    """FR-007: required on every ok decision; exactly four finite [0,1] keys."""

    def test_missing_vector_rejects(self):
        doc = make_decision_ok()
        del doc["legacy_confidence"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_missing_key_rejects(self):
        doc = make_decision_ok()
        del doc["legacy_confidence"]["ASK"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_extra_key_rejects(self):
        doc = make_decision_ok()
        doc["legacy_confidence"]["MUMBLE"] = 0.2
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_out_of_range_values_reject(self):
        for value in (1.5, -0.1, 2, -1):
            with self.subTest(value=value):
                doc = make_decision_ok()
                doc["legacy_confidence"]["SPEAK"] = value
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_boundary_values_are_on_scale(self):
        doc = make_decision_ok()
        doc["legacy_confidence"] = {"PASS": 0, "ACK": 1, "ASK": 0.0, "SPEAK": 1.0}
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_sentinel_decoded_non_finite_values_reject(self):
        # Strict JSON cannot carry non-finite literals; the corpus loader
        # decodes the reserved sentinel strings once, and both validators
        # must reject the decoded value (FR-012 schema-expressible class).
        for sentinel in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(sentinel=sentinel):
                doc = make_decision_ok()
                doc["legacy_confidence"]["SPEAK"] = sentinel
                decoded = decode_non_finite(doc)
                self.assertIsInstance(decoded["legacy_confidence"]["SPEAK"], float)
                assert_schema_verdict(self, "attention-decision", decoded, "invalid")

    def test_boolean_confidence_rejects(self):
        doc = make_decision_ok()
        doc["legacy_confidence"]["PASS"] = True
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_string_confidence_rejects(self):
        doc = make_decision_ok()
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
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "suppress-no-override", advice=make_advice())
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_advice_on_widened_defer_rejects(self):
        # The key is the classifier disposition, not the effective one.
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer", advice=make_advice())
        doc["routing"]["override_cause"] = "uncertainty margin widened the route"
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
    cause ``preattention-disabled`` and no classifier fields."""

    def test_bypass_is_valid_without_classifier_fields(self):
        assert_schema_verdict(self, "attention-decision", make_decision_bypass(), "valid")

    def test_forbidden_classifier_fields_on_bypass_reject(self):
        forbidden = {
            "classifier_disposition": "WAKE",
            "effective_disposition": "WAKE",
            "classifier_audit": {"model": "openrouter/test-model"},
            "advice": make_advice(),
            "reasons": ["should not exist"],
            "legacy_confidence": {"PASS": 0.1, "ACK": 0.2, "ASK": 0.3, "SPEAK": 0.4},
            "evidence_event_ids": ["e1"],
            "routing": {"route": "wake"},
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
