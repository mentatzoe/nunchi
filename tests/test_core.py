import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.provider_helpers import fixture_case, provider_env
from turnaware import evaluate
from turnaware.errors import ValidationError
from turnaware.models import FORBIDDEN_REPLY_FIELDS, VERDICTS

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / f"{name}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


class CoreVerdictTests(unittest.TestCase):
    def test_evaluate_returns_expected_verdict_for_each_fixture(self):
        cases = {
            "pass": "PASS",
            "ack": "ACK",
            "ask": "ASK",
            "speak": "SPEAK",
        }

        for fixture_name, expected in cases.items():
            with self.subTest(fixture=fixture_name):
                with patch.dict("os.environ", fixture_case(fixture_name, expected), clear=True):
                    result = evaluate(load_fixture(fixture_name), classifier="product")
                self.assertEqual(result["verdict"], expected)
                self.assertEqual(result["classifier"], "product")
                self.assertEqual(set(result["confidences"]), set(VERDICTS))
                self.assertTrue(result["reasons"])

    def test_default_product_classifier_identity_is_audited(self):
        with patch.dict("os.environ", fixture_case("speak", "SPEAK"), clear=True):
            result = evaluate(load_fixture("speak"))

        self.assertEqual(result["classifier"], "product")
        self.assertEqual(result["verdict"], "SPEAK")

    def test_explicit_product_classifier_identity_is_audited(self):
        with patch.dict("os.environ", fixture_case("speak", "SPEAK"), clear=True):
            result = evaluate(load_fixture("speak"), classifier="product")

        self.assertEqual(result["classifier"], "product")
        self.assertEqual(result["verdict"], "SPEAK")

    def test_envelope_classifier_identity_is_audited(self):
        with patch.dict("os.environ", fixture_case("speak-classifier", "SPEAK"), clear=True):
            result = evaluate(load_fixture("speak_with_classifier"))

        self.assertEqual(result["classifier"], "product")
        self.assertEqual(result["verdict"], "SPEAK")

    def test_pass_result_has_no_visible_reply_fields(self):
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass", "context:ctx-pass-handled"],
            confidences={"PASS": 0.8, "ACK": 0.05, "ASK": 0.1, "SPEAK": 0.05},
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(load_fixture("pass"), classifier="product")

        self.assertEqual(result["verdict"], "PASS")
        self.assertTrue(FORBIDDEN_REPLY_FIELDS.isdisjoint(result))

    def test_context_checked_names_only_supplied_context(self):
        request = load_fixture("pass")
        env = provider_env("PASS", checked=["trigger:trigger-pass", "context:ctx-pass-handled"])
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(request, classifier="product")
        allowed = {"trigger:trigger-pass", "context:ctx-pass-handled", "context:ctx-pass-later"}

        self.assertLessEqual(set(result["context_checked"]), allowed)
        self.assertNotIn("context:missing", result["context_checked"])

    def test_false_pass_checks_contradictory_context(self):
        env = provider_env(
            "SPEAK",
            checked=["trigger:trigger-false-pass-contradicted-done", "context:ctx-false-pass-missing-work"],
            confidences={"PASS": 0.05, "ACK": 0.05, "ASK": 0.2, "SPEAK": 0.7},
            reasons=["Provider found contradicted missing-work evidence before allowing PASS."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(load_fixture("false_pass_contradicted_done"), classifier="product")

        self.assertNotEqual(result["verdict"], "PASS")
        self.assertIn("context:ctx-false-pass-missing-work", result["context_checked"])
        self.assertLess(result["confidences"]["PASS"], result["confidences"][result["verdict"]])

    def test_invalid_classifier_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            evaluate(load_fixture("invalid_classifier"))


if __name__ == "__main__":
    unittest.main()
