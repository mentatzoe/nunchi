import unittest

from tests.test_core import load_fixture
from turnaware import evaluate
from turnaware.classifiers import SUPPORTED_CLASSIFIERS, get_classifier
from turnaware.errors import ValidationError


class ClassifierTests(unittest.TestCase):
    def test_registry_supports_product_default_and_deterministic_evidence_paths(self):
        self.assertIn("product", SUPPORTED_CLASSIFIERS)
        self.assertIn("deterministic", SUPPORTED_CLASSIFIERS)

    def test_product_and_deterministic_are_distinct_implementations_not_relabelled_same_engine(self):
        product = get_classifier("product")
        deterministic = get_classifier("deterministic")

        self.assertNotEqual(type(product), type(deterministic))
        self.assertNotEqual(getattr(product, "model_id", None), getattr(deterministic, "model_id", None))

    def test_product_payload_is_not_deterministic_payload_with_only_classifier_relabelled(self):
        product = evaluate(load_fixture("false_pass_no_corroboration"), classifier="product")
        deterministic = evaluate(load_fixture("false_pass_no_corroboration"), classifier="deterministic")

        product_without_identity = {key: value for key, value in product.items() if key != "classifier"}
        deterministic_without_identity = {key: value for key, value in deterministic.items() if key != "classifier"}
        self.assertNotEqual(product_without_identity, deterministic_without_identity)

    def test_product_classifier_returns_representative_pass_ack_ask_speak(self):
        cases = {
            "pass": "PASS",
            "ack": "ACK",
            "ask": "ASK",
            "speak": "SPEAK",
        }

        for fixture_name, expected in cases.items():
            with self.subTest(fixture=fixture_name):
                result = evaluate(load_fixture(fixture_name), classifier="product")
                self.assertEqual(result["classifier"], "product")
                self.assertEqual(result["verdict"], expected)

    def test_unavailable_product_model_fails_without_deterministic_fallback(self):
        with self.assertRaises(ValidationError) as caught:
            evaluate(load_fixture("speak"), classifier="product", classifier_config={"model": "missing-model"})

        message = str(caught.exception).casefold()
        self.assertIn("unavailable", message)
        self.assertIn("product", message)

    def test_false_ack_comment_back_is_speak_not_ack(self):
        for classifier in ("product", "deterministic"):
            with self.subTest(classifier=classifier):
                result = evaluate(load_fixture("false_ack_comment_back"), classifier=classifier)
                self.assertEqual(result["classifier"], classifier)
                self.assertEqual(result["verdict"], "SPEAK")
                self.assertNotEqual(result["verdict"], "ACK")
                self.assertIn("context:ctx-false-ack-assignment", result["context_checked"])

    def test_false_pass_contradicted_done_is_not_pass_and_checks_contradiction(self):
        for classifier in ("product", "deterministic"):
            with self.subTest(classifier=classifier):
                result = evaluate(load_fixture("false_pass_contradicted_done"), classifier=classifier)
                self.assertEqual(result["classifier"], classifier)
                self.assertNotEqual(result["verdict"], "PASS")
                self.assertIn("context:ctx-false-pass-missing-work", result["context_checked"])
                self.assertIn("contradicted", " ".join(result["reasons"]).casefold())

    def test_no_corroborating_context_does_not_become_high_confidence_pass(self):
        result = evaluate(load_fixture("false_pass_no_corroboration"), classifier="deterministic")

        self.assertEqual(result["verdict"], "ASK")
        self.assertLess(result["confidences"]["PASS"], result["confidences"]["ASK"])

    def test_legitimate_pass_remains_reachable_with_corroborating_context(self):
        result = evaluate(load_fixture("pass"), classifier="deterministic")

        self.assertEqual(result["verdict"], "PASS")
        self.assertIn("context:ctx-pass-handled", result["context_checked"])

    def test_unsupported_classifier_fails_without_fallback(self):
        with self.assertRaises(ValidationError):
            evaluate(load_fixture("speak"), classifier="does-not-exist")


if __name__ == "__main__":
    unittest.main()
