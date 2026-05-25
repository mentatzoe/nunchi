import unittest
from unittest.mock import patch

from tests.provider_helpers import fixture_case, provider_env
from tests.test_core import load_fixture
from turnaware import evaluate
from turnaware.classifiers import SUPPORTED_CLASSIFIERS, get_classifier
from turnaware.errors import ValidationError


class ClassifierTests(unittest.TestCase):
    def test_registry_supports_only_product_default_path(self):
        self.assertEqual(SUPPORTED_CLASSIFIERS, ("product",))

    def test_product_classifier_uses_provider_model_identity(self):
        with patch.dict("os.environ", provider_env("ASK", checked=["trigger:trigger-speak"]), clear=True):
            product = get_classifier("product")

        self.assertEqual(type(product).__name__, "ProductAdmissionClassifier")
        self.assertEqual(getattr(product, "provider", None), "test-fixture")
        self.assertEqual(getattr(product, "model_id", None), "turnaware-test-fixture-provider")

    def test_deterministic_classifier_path_is_unsupported(self):
        with self.assertRaises(ValidationError):
            get_classifier("deterministic")

        with self.assertRaises(ValidationError):
            evaluate(load_fixture("speak"), classifier="deterministic")

    def test_product_classifier_returns_representative_pass_ack_ask_speak(self):
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
                self.assertEqual(result["classifier"], "product")
                self.assertEqual(result["verdict"], expected)

    def test_unavailable_product_model_fails_without_deterministic_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValidationError) as caught:
                evaluate(load_fixture("speak"), classifier="product", classifier_config={"model": "missing-model"})

        message = str(caught.exception).casefold()
        self.assertIn("classifier provider", message)
        self.assertIn("api key", message)

    def test_false_ack_comment_back_is_speak_not_ack(self):
        env = provider_env(
            "SPEAK",
            checked=["trigger:trigger-false-ack-comment-back", "context:ctx-false-ack-assignment"],
            reasons=["Provider inspected assignment context and rejected ACK."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(load_fixture("false_ack_comment_back"), classifier="product")

        self.assertEqual(result["classifier"], "product")
        self.assertEqual(result["verdict"], "SPEAK")
        self.assertNotEqual(result["verdict"], "ACK")
        self.assertIn("context:ctx-false-ack-assignment", result["context_checked"])

    def test_false_pass_contradicted_done_is_not_pass_and_checks_contradiction(self):
        env = provider_env(
            "SPEAK",
            checked=["trigger:trigger-false-pass-contradicted-done", "context:ctx-false-pass-missing-work"],
            reasons=["Provider found contradicted missing-work evidence before allowing PASS."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(load_fixture("false_pass_contradicted_done"), classifier="product")

        self.assertEqual(result["classifier"], "product")
        self.assertNotEqual(result["verdict"], "PASS")
        self.assertIn("context:ctx-false-pass-missing-work", result["context_checked"])
        self.assertIn("contradicted", " ".join(result["reasons"]).casefold())

    def test_no_corroborating_context_does_not_become_high_confidence_pass(self):
        env = provider_env(
            "ASK",
            checked=["trigger:trigger-false-pass-no-corroboration"],
            confidences={"PASS": 0.1, "ACK": 0.05, "ASK": 0.75, "SPEAK": 0.1},
            reasons=["Provider found no corroborating supplied completion evidence."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(load_fixture("false_pass_no_corroboration"), classifier="product")

        self.assertEqual(result["verdict"], "ASK")
        self.assertLess(result["confidences"]["PASS"], result["confidences"]["ASK"])

    def test_legitimate_pass_remains_reachable_with_corroborating_context(self):
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass", "context:ctx-pass-handled"],
            confidences={"PASS": 0.8, "ACK": 0.05, "ASK": 0.1, "SPEAK": 0.05},
            reasons=["Provider found corroborating completion evidence in supplied context."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(load_fixture("pass"), classifier="product")

        self.assertEqual(result["verdict"], "PASS")
        self.assertIn("context:ctx-pass-handled", result["context_checked"])

    def test_unsupported_classifier_fails_without_fallback(self):
        with self.assertRaises(ValidationError):
            evaluate(load_fixture("speak"), classifier="does-not-exist")


if __name__ == "__main__":
    unittest.main()
