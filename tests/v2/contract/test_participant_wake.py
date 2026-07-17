"""Contract tests for ``I-010C ParticipantWakeV2@1`` (slice 010, T004).

Red cases cover the wake sources, advice-free ``PREATTENTION_BYPASS``
(010-Preattention-bypass), the FR-013 advice-source violations (advice on
any non-``WAKE`` ``source``), and non-positive participant budgets (S15).
The downstream corpus containing the wake cases is run by
``test_context_and_receipt.py``.
"""

from __future__ import annotations

import unittest

from tests.v2.contract.schema_helpers import (
    assert_schema_verdict,
    check_advice_citations,
    make_advice,
    make_wake,
)


class WakeSourceCases(unittest.TestCase):
    """FR-008: explicit sources, no admission meta-answer, facts separate."""

    def test_every_source_validates_without_advice(self):
        for source in ("WAKE", "DEFER", "ERROR_FALLBACK", "PREATTENTION_BYPASS"):
            with self.subTest(source=source):
                assert_schema_verdict(self, "participant-wake", make_wake(source), "valid")

    def test_unknown_source_rejects(self):
        assert_schema_verdict(self, "participant-wake", make_wake("BYPASS"), "invalid")

    def test_missing_source_rejects(self):
        doc = make_wake()
        del doc["source"]
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_missing_observation_rejects(self):
        doc = make_wake()
        del doc["observation"]
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_observation_must_be_a_valid_request(self):
        doc = make_wake()
        del doc["observation"]["self"]
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_v1_envelope_observation_rejects(self):
        doc = make_wake(
            observation={
                "trigger": {"id": "trigger-speak", "content": "please implement"},
                "context": [],
                "agent": {"id": "turnaware-vigil"},
            }
        )
        assert_schema_verdict(self, "participant-wake", doc, "invalid")


class WakeAdviceCases(unittest.TestCase):
    """FR-013: advice appears only on ``source: WAKE`` packets."""

    def test_wake_source_with_advice_is_valid(self):
        doc = make_wake("WAKE", advice=make_advice())
        assert_schema_verdict(self, "participant-wake", doc, "valid")

    def test_bypass_wake_is_advice_free(self):
        # 010-Preattention-bypass: no classifier ran, so no advice exists.
        doc = make_wake("PREATTENTION_BYPASS", advice=make_advice())
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_defer_wake_is_advice_free(self):
        doc = make_wake("DEFER", advice=make_advice())
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_error_fallback_wake_is_advice_free(self):
        doc = make_wake("ERROR_FALLBACK", advice=make_advice())
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_wake_advice_citations_are_checked_against_the_observation(self):
        # Runtime-adapter-only: the packet is schema-valid in isolation while
        # the citation references no observed event (FR-013).
        doc = make_wake("WAKE", advice=make_advice(evidence_event_ids=["e-ghost"]))
        assert_schema_verdict(self, "participant-wake", doc, "valid")
        self.assertTrue(check_advice_citations(doc, doc["observation"]))
        grounded = make_wake("WAKE", advice=make_advice(evidence_event_ids=["e1"]))
        self.assertEqual([], check_advice_citations(grounded, grounded["observation"]))


class WakeBudgetCases(unittest.TestCase):
    """S15: participant budgets are independent, explicit, and positive."""

    def test_zero_participant_event_budget_rejects(self):
        doc = make_wake()
        doc["budgets"]["max_events"] = 0
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_negative_participant_byte_budget_rejects(self):
        doc = make_wake()
        doc["budgets"]["max_bytes"] = -5
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_missing_participant_budgets_reject(self):
        doc = make_wake()
        del doc["budgets"]
        assert_schema_verdict(self, "participant-wake", doc, "invalid")


class WakeLedgerRejectionCases(unittest.TestCase):
    """S16: no composed reply, admission answer, or social ledger."""

    def test_reply_and_admission_fields_reject(self):
        for field, value in (
            ("reply", "sure, I can help"),
            ("admission_answer", "SPEAK"),
            ("composed_reply", {"text": "hello"}),
        ):
            with self.subTest(field=field):
                doc = make_wake(**{field: value})
                assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_social_ledger_fields_reject(self):
        for field, value in (("handled", False), ("owed", ["reply"])):
            with self.subTest(field=field):
                doc = make_wake(**{field: value})
                assert_schema_verdict(self, "participant-wake", doc, "invalid")


if __name__ == "__main__":
    unittest.main()
