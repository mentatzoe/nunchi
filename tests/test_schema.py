import unittest
from unittest.mock import patch

from tests.provider_helpers import fixture_case, provider_env
from tests.test_core import load_fixture
from nunchi import evaluate
from nunchi.errors import ValidationError
from nunchi.models import FORBIDDEN_REPLY_FIELDS, VERDICTS
from nunchi.schema import validate_request, validate_result


class SchemaTests(unittest.TestCase):
    def test_success_result_schema_has_classifier_verdict_confidences_context_and_reasons(self):
        with patch.dict("os.environ", fixture_case("speak", "SPEAK"), clear=True):
            result = evaluate(load_fixture("speak"))
        validated = validate_result(result)

        self.assertIs(validated, result)
        self.assertEqual(result["classifier"], "product")
        self.assertIn(result["verdict"], VERDICTS)
        self.assertEqual(set(result["confidences"]), set(VERDICTS))
        self.assertIsInstance(result["context_checked"], list)
        self.assertGreaterEqual(len(result["context_checked"]), 1)
        self.assertIsInstance(result["reasons"], list)
        self.assertTrue(result["reasons"])

    def test_success_result_contains_no_reply_composition_fields(self):
        for fixture_name in ("pass", "ack", "ask", "speak"):
            with self.subTest(fixture=fixture_name):
                expected = {"pass": "PASS", "ack": "ACK", "ask": "ASK", "speak": "SPEAK"}[fixture_name]
                with patch.dict("os.environ", fixture_case(fixture_name, expected), clear=True):
                    result = evaluate(load_fixture(fixture_name), classifier="product")
                self.assertTrue(FORBIDDEN_REPLY_FIELDS.isdisjoint(result))

    def test_request_accepts_classifier_and_classifier_config(self):
        request = validate_request({
            "classifier": "product",
            "classifier_config": {"model": "nunchi-test-model"},
            "trigger": {"content": "Please acknowledge this."},
        })

        self.assertEqual(request.classifier, "product")
        self.assertEqual(request.classifier_config, {"model": "nunchi-test-model"})

    def test_context_checked_references_only_request_items(self):
        request = load_fixture("pass")
        env = provider_env("PASS", checked=["trigger:trigger-pass", "context:ctx-pass-handled"])
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(request, classifier="product")
        allowed = {"trigger:trigger-pass", "context:ctx-pass-handled", "context:ctx-pass-later"}

        self.assertLessEqual(set(result["context_checked"]), allowed)
        self.assertNotIn("context:missing", result["context_checked"])

    def test_missing_trigger_is_validation_error(self):
        with self.assertRaises(ValidationError):
            validate_request({"context": []})

    def test_duplicate_context_ids_are_validation_error(self):
        request = load_fixture("pass")
        request["context"][1]["id"] = request["context"][0]["id"]

        with self.assertRaises(ValidationError):
            validate_request(request)

    def test_invalid_classifier_config_is_validation_error(self):
        with self.assertRaises(ValidationError):
            evaluate({
                "classifier": "product",
                "classifier_config": {"unknown": True},
                "trigger": {"content": "Please acknowledge this."},
            })

    def test_agent_aliases_accepted_and_passed_through(self):
        request = validate_request({
            "trigger": {"content": "Vigil, can you look at this?"},
            "agent": {"id": "vigil", "mention_id": "111", "aliases": ["Vigil", "Codex", "Aether"]},
        })

        self.assertEqual(request.agent["aliases"], ["Vigil", "Codex", "Aether"])

    def test_agent_without_aliases_passes_through_unchanged(self):
        # Additive-optional: an alias-free agent object is exactly what was supplied.
        request = validate_request({
            "trigger": {"content": "Vigil, can you look at this?"},
            "agent": {"id": "vigil", "mention_id": "111"},
        })

        self.assertEqual(request.agent, {"id": "vigil", "mention_id": "111"})
        self.assertNotIn("aliases", request.agent)

    def test_agent_aliases_must_be_a_list(self):
        with self.assertRaises(ValidationError):
            validate_request({
                "trigger": {"content": "ping"},
                "agent": {"id": "vigil", "aliases": "Vigil,Codex"},
            })

    def test_agent_aliases_non_string_entry_is_validation_error(self):
        with self.assertRaises(ValidationError):
            validate_request({
                "trigger": {"content": "ping"},
                "agent": {"id": "vigil", "aliases": ["Vigil", 42]},
            })

    def test_agent_aliases_blank_entry_is_validation_error(self):
        with self.assertRaises(ValidationError):
            validate_request({
                "trigger": {"content": "ping"},
                "agent": {"id": "vigil", "aliases": ["Vigil", "   "]},
            })

    def test_agent_aliases_empty_list_is_accepted(self):
        request = validate_request({
            "trigger": {"content": "ping"},
            "agent": {"id": "vigil", "aliases": []},
        })

        self.assertEqual(request.agent["aliases"], [])

    def test_result_without_classifier_is_validation_error(self):
        with patch.dict("os.environ", fixture_case("speak", "SPEAK"), clear=True):
            result = evaluate(load_fixture("speak"), classifier="product")
        del result["classifier"]

        with self.assertRaises(ValidationError):
            validate_result(result)


if __name__ == "__main__":
    unittest.main()


class ConfidenceDomainTests(unittest.TestCase):
    """Round-4: the shared boundary enforces the [0, 1] confidence scale so
    core and the hook cannot disagree about what counts as evidence."""

    def _result(self, conf):
        return {
            "classifier": "product",
            "verdict": "PASS",
            "confidences": conf,
            "context_checked": [],
            "reasons": ["r"],
        }

    def test_out_of_range_confidence_rejected(self):
        from nunchi.schema import validate_result
        from nunchi.errors import ValidationError
        for conf in ({"PASS": 9.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0},
                     {"PASS": -0.1, "ACK": -1.0, "ASK": -1.0, "SPEAK": -1.0},
                     {"PASS": float("nan"), "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0}):
            with self.subTest(conf=conf):
                with self.assertRaises(ValidationError):
                    validate_result(self._result(conf))

    def test_huge_int_confidence_gets_named_error_not_overflow(self):
        """Aleph's post-approval note: a ~1000-digit integer confidence must
        raise the named ValidationError, not OverflowError."""
        from nunchi.schema import validate_result
        from nunchi.errors import ValidationError
        with self.assertRaises(ValidationError):
            validate_result(self._result(
                {"PASS": 10 ** 1000, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0}))

    def test_boundary_values_accepted(self):
        from nunchi.schema import validate_result
        validate_result(self._result({"PASS": 1.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0}))
