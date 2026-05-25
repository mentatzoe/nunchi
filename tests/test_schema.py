import unittest
from unittest.mock import patch

from tests.provider_helpers import fixture_case, provider_env
from tests.test_core import load_fixture
from turnaware import evaluate
from turnaware.errors import ValidationError
from turnaware.models import FORBIDDEN_REPLY_FIELDS, VERDICTS
from turnaware.schema import validate_request, validate_result


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
            "classifier_config": {"model": "turnaware-test-model"},
            "trigger": {"content": "Please acknowledge this."},
        })

        self.assertEqual(request.classifier, "product")
        self.assertEqual(request.classifier_config, {"model": "turnaware-test-model"})

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

    def test_result_without_classifier_is_validation_error(self):
        with patch.dict("os.environ", fixture_case("speak", "SPEAK"), clear=True):
            result = evaluate(load_fixture("speak"), classifier="product")
        del result["classifier"]

        with self.assertRaises(ValidationError):
            validate_result(result)


if __name__ == "__main__":
    unittest.main()
