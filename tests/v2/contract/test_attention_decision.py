"""Contract tests for ``I-010B AttentionDecisionV2@9`` (slice 010, T003;
reworked by T028 after rejection R2; @5 for #94 step 4, @6 for step 5, @7 and @8 for step 6).

@5 (Zoe, 2026-10-05) grounds every ``status: ok`` decision in the model's
typed answers (``answers``): exactly the step 1 and step 2 questions, each a
finite value in [0,1], choices naming exactly their options, and optional
``answered_by`` and (@6) ``responds_to`` pointers. @6 also asks whether the
judged message ``asks`` someone for something. The V1-era legacy verdict confidence vector it
replaces is no longer allowed. Red cases include the sentinel-decoded
``"NaN"``/``"Infinity"``/``"-Infinity"`` non-finite answers. Further red
cases cover the closed FR-005 routing audit's cross-field rules (applied
valve, override cause, margin status, effective margin exactly when the
margin applied, trusted margin source only on a margin-applied decision),
the sibling ok-branch ``reasons`` placement, the forbidden classifier fields
on the ``preattention-disabled`` bypass branch (the full FR-005 exclusion
set), and the reading rules (advice citing nonexistent event IDs is
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
    make_answers,
    make_decision_ok,
    make_request,
    make_routing,
)


class AttentionDecisionCorpusSuite(ContractCorpusMixin, unittest.TestCase):
    CORPUS = "attention-decision"
    REQUIRED_SCENES = frozenset({"S05", "S08", "S09", "S16", "010-Preattention-bypass"})


class TransitionMatrixCases(unittest.TestCase):
    """FR-006 / SC-003 / S09: permitted ok pairs, each mapped
    onto its applied valve."""

    VALID_PAIRS = {
        ("WAKE", "WAKE"): "none",
        ("DEFER", "DEFER"): "classifier-defer",
        ("SUPPRESS", "DEFER"): "margin-defer",
        ("SUPPRESS", "SUPPRESS"): "none",
    }

    def test_only_declared_ok_pairs_validate(self):
        # ACK is not a disposition since @9 (#94 step 7): every pair with
        # it rejects.
        dispositions = ("SUPPRESS", "ACK", "WAKE", "DEFER")
        for classifier in dispositions:
            for effective in dispositions:
                pair = (classifier, effective)
                with self.subTest(pair=pair):
                    valve = self.VALID_PAIRS.get(pair, "none")
                    doc = make_decision_ok(classifier, effective, valve)
                    expected = "valid" if pair in self.VALID_PAIRS else "invalid"
                    assert_schema_verdict(self, "attention-decision", doc, expected)

    def test_nunchis_own_nod_is_gone(self):
        # @9 (#94 step 7): no ACK disposition, audit, valve, or cause.
        for classifier, effective, valve in (
            ("ACK", "ACK", "none"),
            ("ACK", "DEFER", "policy-defer"),
            ("ACK", "DEFER", "capability-defer"),
        ):
            with self.subTest(pair=(classifier, effective, valve)):
                doc = make_decision_ok(classifier, effective, valve)
                assert_schema_verdict(self, "attention-decision", doc, "invalid")
        stray = make_decision_ok()
        stray["ack"] = make_decision_ok("ACK", "ACK", "none")["ack"]
        assert_schema_verdict(self, "attention-decision", stray, "invalid")
        for cause in ("ack-disabled", "ack-unsupported"):
            with self.subTest(cause=cause):
                doc = make_decision_ok("SUPPRESS", "DEFER", "policy-defer")
                doc["routing_audit"]["override_cause"] = cause
                assert_schema_verdict(self, "attention-decision", doc, "invalid")
        capability = make_decision_ok("SUPPRESS", "DEFER", "capability-defer")
        assert_schema_verdict(self, "attention-decision", capability, "invalid")

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
        del doc["routing_audit"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_widening_preserves_exact_valve_and_cause(self):
        # S05/S08: the widened route names its valve and override cause.
        margin = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        assert_schema_verdict(self, "attention-decision", margin, "valid")
        policy = make_decision_ok("SUPPRESS", "DEFER", "policy-defer")
        assert_schema_verdict(self, "attention-decision", policy, "valid")

    def test_widened_suppression_with_cause_none_rejects(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        doc["routing_audit"]["override_cause"] = "none"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_dual_defer_valves_stay_distinct(self):
        # S08: classifier-DEFER and margin-DEFER are separately auditable.
        classifier_defer = make_decision_ok("DEFER", "DEFER", "classifier-defer")
        assert_schema_verdict(self, "attention-decision", classifier_defer, "valid")
        mislabeled = make_decision_ok("DEFER", "DEFER", "margin-defer")
        assert_schema_verdict(self, "attention-decision", mislabeled, "invalid")

    def test_classifier_defer_cannot_carry_an_override_cause(self):
        doc = make_decision_ok("DEFER", "DEFER", "classifier-defer")
        doc["routing_audit"]["override_cause"] = "margin"
        assert_schema_verdict(self, "attention-decision", doc, "invalid")


class OutcomeTurnCases(unittest.TestCase):
    """@7 (#94 step 6): an outcome turn widens SUPPRESS to DEFER."""

    def test_outcome_turn_is_a_policy_widening_of_suppress(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "policy-defer")
        doc["routing_audit"]["override_cause"] = "outcome-turn"
        assert_schema_verdict(self, "attention-decision", doc, "valid")
        # It is a policy widening only, never a capability or margin one.
        for valve in ("capability-defer", "margin-defer", "none"):
            with self.subTest(valve=valve):
                doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
                doc["routing_audit"]["valve"] = valve
                doc["routing_audit"]["override_cause"] = "outcome-turn"
                assert_schema_verdict(self, "attention-decision", doc, "invalid")


class RoutingAuditCases(unittest.TestCase):
    """FR-005: the closed routing audit's cross-field rules (CHK084) and
    the sibling placement of ``reasons`` (CHK085)."""

    def test_margin_applied_requires_the_effective_margin(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        del doc["routing_audit"]["effective_margin"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_a_retired_margin_cannot_apply(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        doc["routing_audit"]["margin_status"] = "retired"
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
                doc["routing_audit"]["effective_margin"] = 0.12
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_margin_source_only_on_a_margin_applied_decision(self):
        allowed = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        allowed["routing_audit"]["margin_source"] = "trusted:profiles/default@2026-07"
        assert_schema_verdict(self, "attention-decision", allowed, "valid")
        forbidden = make_decision_ok()
        forbidden["routing_audit"]["margin_source"] = "trusted:profiles/default@2026-07"
        assert_schema_verdict(self, "attention-decision", forbidden, "invalid")

    def test_valve_and_override_cause_pair_exactly(self):
        wrong_none = make_decision_ok()
        wrong_none["routing_audit"]["override_cause"] = "margin"
        assert_schema_verdict(self, "attention-decision", wrong_none, "invalid")
        wrong_policy = make_decision_ok("SUPPRESS", "DEFER", "policy-defer")
        wrong_policy["routing_audit"]["override_cause"] = "margin"
        assert_schema_verdict(self, "attention-decision", wrong_policy, "invalid")

    def test_margin_status_is_always_recorded(self):
        doc = make_decision_ok()
        del doc["routing_audit"]["margin_status"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_out_of_range_effective_margin_rejects(self):
        for value in (-0.1, 1.5):
            with self.subTest(value=value):
                doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
                doc["routing_audit"]["effective_margin"] = value
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_zero_effective_margin_validates(self):
        # @2 amendment A2 (c834e8c: "a transition margin, when active, is a
        # finite number within [0,1]"): the domain is inclusive of the exact
        # boundary, matching the retained inclusive <= transition comparison.
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer")
        doc["routing_audit"]["effective_margin"] = 0
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_reasons_is_a_required_sibling_field(self):
        doc = make_decision_ok()
        del doc["reasons"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_reasons_never_lives_inside_the_routing_audit(self):
        doc = make_decision_ok()
        doc["routing_audit"]["reasons"] = ["misplaced audit material"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_empty_reasons_stays_valid_audit_material(self):
        doc = make_decision_ok(reasons=[])
        assert_schema_verdict(self, "attention-decision", doc, "valid")


class TypedAnswerCases(unittest.TestCase):
    """@5 (Zoe, 2026-10-05, #94 step 4): every ok decision carries the
    model's typed answers, exactly the questions with finite [0,1] values;
    the V1-era legacy confidence vector is gone. @6 adds asks and
    responds_to."""

    def test_every_ok_decision_requires_answers(self):
        for doc in (
            make_decision_ok(),
            make_decision_ok("DEFER", "DEFER", "classifier-defer"),
            make_decision_ok("SUPPRESS", "SUPPRESS", "none"),
            make_decision_ok("SUPPRESS", "DEFER", "margin-defer"),
        ):
            with self.subTest(pair=(doc["classifier_disposition"], doc["effective_disposition"])):
                assert_schema_verdict(self, "attention-decision", doc, "valid")
                del doc["answers"]
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_the_legacy_vector_is_no_longer_allowed(self):
        doc = make_decision_ok(legacy_verdict_confidences={"PASS": 0.05, "ACK": 0.1, "ASK": 0.15, "SPEAK": 0.7})
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_a_missing_or_extra_question_rejects(self):
        missing = make_decision_ok()
        del missing["answers"]["mid_thought"]
        no_asks = make_decision_ok()
        del no_asks["answers"]["asks"]
        extra = make_decision_ok()
        extra["answers"]["obligation"] = 1.0
        for doc in (missing, no_asks, extra):
            assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_a_choice_names_exactly_its_options(self):
        missing = make_decision_ok()
        del missing["answers"]["move"]["wait"]
        extra = make_decision_ok()
        extra["answers"]["addressee"]["everyone"] = 0.1
        for doc in (missing, extra):
            assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_out_of_range_values_reject(self):
        for value in (1.5, -0.1, 2, -1):
            with self.subTest(value=value):
                doc = make_decision_ok()
                doc["answers"]["conversation"] = value
                assert_schema_verdict(self, "attention-decision", doc, "invalid")
                doc = make_decision_ok()
                doc["answers"]["move"]["speak"] = value
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_boundary_values_are_on_scale(self):
        doc = make_decision_ok(answers=make_answers(conversation=0, answered=1, mid_thought=0.0, adds_something=1.0))
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_sentinel_decoded_non_finite_values_reject(self):
        # Strict JSON cannot carry non-finite literals; the corpus loader
        # decodes the reserved sentinel strings once, and both validators
        # must reject the decoded value.
        for sentinel in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(sentinel=sentinel):
                doc = make_decision_ok("SUPPRESS", "SUPPRESS", "none")
                doc["answers"]["conversation"] = sentinel
                decoded = decode_non_finite(doc)
                self.assertIsInstance(decoded["answers"]["conversation"], float)
                assert_schema_verdict(self, "attention-decision", decoded, "invalid")

    def test_boolean_and_string_values_reject(self):
        for value in (True, "0.5"):
            with self.subTest(value=value):
                doc = make_decision_ok()
                doc["answers"]["answered"] = value
                assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_each_pointer_names_one_message(self):
        # calls_for_participant since @8 (#94 step 6): asked only with unattended messages.
        for key in ("answered_by", "responds_to", "calls_for_participant"):
            assert_schema_verdict(
                self, "attention-decision", make_decision_ok(answers=make_answers(**{key: "e3"})), "valid"
            )
            for value in ("", 3, None):
                with self.subTest(key=key, value=value):
                    doc = make_decision_ok(answers=make_answers(**{key: value}))
                    assert_schema_verdict(self, "attention-decision", doc, "invalid")


class AdviceRuleCases(unittest.TestCase):
    """@4: the classifier's reading of the room may accompany every ok
    judgment, at most 4 items of at most 400 characters, and every citation
    must reference a request-supplied event ID."""

    def test_wake_with_grounded_advice_is_valid(self):
        doc = make_decision_ok(attention_advice=[make_advice()])
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_a_reading_on_classifier_defer_is_valid(self):
        doc = make_decision_ok("DEFER", "DEFER", "classifier-defer", attention_advice=[make_advice()])
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_a_reading_on_suppression_is_valid(self):
        doc = make_decision_ok("SUPPRESS", "SUPPRESS", "none", attention_advice=[make_advice()])
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_a_reading_on_widened_defer_is_valid(self):
        doc = make_decision_ok("SUPPRESS", "DEFER", "margin-defer", attention_advice=[make_advice()])
        assert_schema_verdict(self, "attention-decision", doc, "valid")

    def test_a_reading_is_bounded(self):
        many = make_decision_ok(attention_advice=[make_advice()] * 5)
        assert_schema_verdict(self, "attention-decision", many, "invalid")
        advice = make_advice()
        advice["note"] = "x" * 401
        long = make_decision_ok(attention_advice=[advice])
        assert_schema_verdict(self, "attention-decision", long, "invalid")

    def test_advice_without_citations_rejects(self):
        doc = make_decision_ok(attention_advice=[{"note": "ungrounded", "evidence_event_ids": []}])
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_advice_citing_nonexistent_event_is_runtime_adapter_only(self):
        request = make_request()
        decision = make_decision_ok(attention_advice=[make_advice(evidence_event_ids=["e-ghost"])])
        # Each document is schema-valid in isolation (oracle-expected-valid).
        assert_schema_verdict(self, "attention-request", request, "valid")
        assert_schema_verdict(self, "attention-decision", decision, "valid")
        self.assertTrue(check_advice_citations(decision, request))

    def test_advice_citing_supplied_events_passes_the_relational_check(self):
        request = make_request()
        decision = make_decision_ok(attention_advice=[make_advice(evidence_event_ids=["e1", "e3"])])
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
            "classifier": {"name": "nunchi-classifier"},
            "attention_advice": [make_advice()],
            "reasons": ["should not exist"],
            "legacy_verdict_confidences": {"PASS": 0.1, "ACK": 0.2, "ASK": 0.3, "SPEAK": 0.4},
            "answers": make_answers(),
            "evidence_event_ids": ["e1"],
            "routing_audit": make_routing(),
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

    def test_arbitrary_string_code_validates(self):
        # code is the authority's open string (FR-014, rejection R7) — not a
        # locally narrowed enum.
        assert_schema_verdict(
            self, "attention-decision", make_decision_error("transport-timeout"), "valid"
        )

    def test_error_missing_detail_rejects(self):
        doc = make_decision_error()
        del doc["error"]["detail"]
        assert_schema_verdict(self, "attention-decision", doc, "invalid")

    def test_error_empty_code_rejects(self):
        assert_schema_verdict(self, "attention-decision", make_decision_error(""), "invalid")

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
