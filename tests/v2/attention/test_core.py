from __future__ import annotations

import copy
import tempfile
import unittest

from nunchi.core import ReceiptSinkPersistenceError, evaluate_v2
from nunchi.policy import load_operator_policy
from tests.v2.contract.schema_helpers import (
    make_request,
    validate_attention_decision,
    validate_attention_receipt,
)
from tests.v2.security.helpers import clone_policy, write_policy


def judgment(disposition="WAKE", **overrides):
    result = {
        "disposition": disposition,
        "reasons": ["participant-shaped fixture judgment"],
        "evidence_event_ids": ["e1"],
    }
    if disposition == "SUPPRESS":
        result["legacy_verdict_confidences"] = {
            "PASS": 0.9,
            "ACK": 0.03,
            "ASK": 0.03,
            "SPEAK": 0.04,
        }
    result.update(overrides)
    return result


class AttentionCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        document = clone_policy()
        document["recoverability"]["continuity_scope_id"] = "discord:room:42#2026-07"
        self.path = write_policy(self.temporary.name, document)
        self.operator = load_operator_policy(self.path)
        self.request = make_request()
        self.receipts = []

    def evaluate(self, transport, **overrides):
        arguments = {
            "policy": self.operator.attention,
            "recoverability": self.operator.recoverability,
            "classifier_config": self.operator.classifier,
            "receipt_sink": self.receipts.append,
            "classifier_transport": transport,
        }
        arguments.update(overrides)
        return evaluate_v2(self.request, **arguments)

    def assert_valid_result_and_receipt(self, result):
        self.assertEqual(validate_attention_decision(result), [])
        self.assertEqual(len(self.receipts), 1)
        self.assertEqual(validate_attention_receipt(self.receipts[0]), [])


class ParticipantShapedJudgmentCases(AttentionCase):
    def test_wake_result_and_receipt_are_contract_valid(self):
        result = self.evaluate(
            lambda projection, config: judgment(
                "WAKE",
                attention_advice=[
                    {"note": "Current room may need a response", "evidence_event_ids": ["e1"]}
                ],
            )
        )
        self.assertEqual(result["effective_disposition"], "WAKE")
        self.assertEqual(result["routing_audit"]["valve"], "none")
        self.assert_valid_result_and_receipt(result)
        self.assertEqual(self.receipts[0]["body"]["policy_provenance"], self.operator.provenance)

    def test_classifier_defer_remains_distinct(self):
        result = self.evaluate(lambda projection, config: judgment("DEFER"))
        self.assertEqual(result["effective_disposition"], "DEFER")
        self.assertEqual(result["routing_audit"]["valve"], "classifier-defer")
        self.assert_valid_result_and_receipt(result)

    def test_governed_suppression_outside_margin_can_suppress(self):
        result = self.evaluate(lambda projection, config: judgment("SUPPRESS"))
        self.assertEqual(result["effective_disposition"], "SUPPRESS")
        self.assertEqual(result["routing_audit"]["valve"], "none")
        self.assert_valid_result_and_receipt(result)

    def test_inside_margin_widens_suppression_to_defer(self):
        vector = {"PASS": 0.5, "ACK": 0.4, "ASK": 0.05, "SPEAK": 0.05}
        result = self.evaluate(
            lambda projection, config: judgment(
                "SUPPRESS", legacy_verdict_confidences=vector
            )
        )
        self.assertEqual(result["effective_disposition"], "DEFER")
        self.assertEqual(result["routing_audit"]["valve"], "margin-defer")
        self.assertEqual(result["routing_audit"]["override_cause"], "margin")
        self.assert_valid_result_and_receipt(result)

    def test_suppression_policy_and_recoverability_only_widen(self):
        policy = copy.copy(self.operator.attention)
        object.__setattr__(policy, "social_suppression_enabled", False)
        result = self.evaluate(
            lambda projection, config: judgment("SUPPRESS"),
            policy=policy,
        )
        self.assertEqual(result["routing_audit"]["override_cause"], "suppression-disabled")
        self.assertEqual(result["effective_disposition"], "DEFER")

        recoverability = copy.copy(self.operator.recoverability)
        object.__setattr__(recoverability, "eligible", False)
        result = self.evaluate(
            lambda projection, config: judgment("SUPPRESS"),
            recoverability=recoverability,
        )
        self.assertEqual(result["routing_audit"]["override_cause"], "recoverability-unproven")
        self.assertEqual(result["effective_disposition"], "DEFER")

    def test_malformed_or_ungrounded_model_output_is_operational_error(self):
        for raw in (
            {"disposition": "PASS", "reasons": [], "evidence_event_ids": []},
            judgment("WAKE", evidence_event_ids=["ghost"]),
            judgment("DEFER", attention_advice=[]),
            judgment("SUPPRESS", legacy_verdict_confidences={"PASS": 1}),
        ):
            with self.subTest(raw=raw):
                self.receipts.clear()
                result = self.evaluate(lambda projection, config, raw=raw: raw)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"]["code"], "malformed-model-output")
                self.assert_valid_result_and_receipt(result)


class ProjectionAndBudgetCases(AttentionCase):
    def test_projection_removes_all_continuation_authority_and_preserves_input(self):
        self.request["continuation"] = {
            "handle_id": "secret-handle",
            "bound_to": {
                "participant_id": "vigil",
                "room_id": "42",
                "continuity_scope_id": "discord:room:42#2026-07",
                "trigger_event_id": "e3",
            },
            "can_fetch_before": True,
            "can_fetch_after": False,
            "can_fetch_around_event": True,
            "max_events_per_fetch": 20,
            "max_bytes_per_fetch": 32768,
            "expires_at": "2026-07-20T15:00:00Z",
        }
        before = copy.deepcopy(self.request)
        projections = []
        result = self.evaluate(
            lambda projection, config: projections.append(projection) or judgment("WAKE")
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(self.request, before)
        projection = projections[0]
        self.assertNotIn("continuation", projection)
        self.assertEqual(
            projection["expansion_available"],
            {"before": True, "after": False, "around_event": True},
        )
        self.assertNotIn("secret-handle", repr(projection))

    def test_event_or_byte_overage_has_zero_classifier_calls(self):
        for field, value in (("attention_max_events", 1), ("attention_max_bytes", 10)):
            with self.subTest(field=field):
                self.receipts.clear()
                policy = copy.copy(self.operator.attention)
                object.__setattr__(policy, field, value)
                calls = []
                result = self.evaluate(
                    lambda projection, config: calls.append(projection) or judgment("WAKE"),
                    policy=policy,
                )
                self.assertEqual(calls, [])
                self.assertEqual(result["error"]["code"], "attention-budget-error")
                self.assert_valid_result_and_receipt(result)

    def test_invalid_request_has_no_classifier_or_fabricated_receipt(self):
        del self.request["self"]["actor_id"]
        calls = []
        result = self.evaluate(
            lambda projection, config: calls.append(projection) or judgment("WAKE")
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "invalid-request")
        self.assertEqual(calls, [])
        self.assertEqual(self.receipts, [])
        self.assertEqual(validate_attention_decision(result), [])


class BypassAndFailureCases(AttentionCase):
    def test_trusted_bypass_invokes_no_classifier_and_fabricates_no_disposition(self):
        policy = copy.copy(self.operator.attention)
        object.__setattr__(policy, "preattention_enabled", False)
        calls = []
        result = self.evaluate(
            lambda projection, config: calls.append(projection),
            policy=policy,
        )
        self.assertEqual(calls, [])
        self.assertEqual(result, {
            "status": "bypass",
            "request_id": "req-0001",
            "cause": "preattention-disabled",
        })
        self.assert_valid_result_and_receipt(result)
        self.assertEqual(
            self.receipts[0]["body"],
            {
                "classifier_not_invoked": True,
                "cause": "preattention-disabled",
                "policy_provenance": self.operator.provenance,
            },
        )

    def test_provider_failure_is_error_with_wake_default(self):
        def failed(_projection, _config):
            raise RuntimeError("secret provider detail")

        result = self.evaluate(failed)
        self.assertEqual(result["error"]["code"], "provider-error")
        self.assertNotIn("secret", repr(result))
        self.assert_valid_result_and_receipt(result)
        self.assertNotIn("wake_action", self.receipts[0]["body"])

    def test_validated_no_wake_override_is_only_in_error_receipt(self):
        policy = copy.copy(self.operator.attention)
        object.__setattr__(policy, "error_action", "NO_WAKE")

        def failed(_projection, _config):
            raise TimeoutError

        result = self.evaluate(failed, policy=policy)
        self.assertEqual(result["error"]["code"], "provider-timeout")
        self.assertNotIn("wake_action", result)
        self.assert_valid_result_and_receipt(result)
        self.assertEqual(self.receipts[0]["body"]["wake_action"], "NO_WAKE")
        self.assertEqual(self.receipts[0]["body"]["policy_provenance"], policy.source)

    def test_sink_failure_returns_error_without_second_offer_or_no_wake(self):
        offers = []

        def sink(record):
            offers.append(record)
            raise ReceiptSinkPersistenceError("unknown")

        result = self.evaluate(
            lambda projection, config: judgment("WAKE"),
            receipt_sink=sink,
        )
        self.assertEqual(len(offers), 1)
        self.assertEqual(result["error"]["code"], "receipt-sink-failure")
        self.assertEqual(validate_attention_decision(result), [])

    def test_host_control_base_exception_propagates(self):
        class StopHost(BaseException):
            pass

        def sink(_record):
            raise StopHost

        with self.assertRaises(StopHost):
            self.evaluate(
                lambda projection, config: judgment("WAKE"),
                receipt_sink=sink,
            )


if __name__ == "__main__":
    unittest.main()
