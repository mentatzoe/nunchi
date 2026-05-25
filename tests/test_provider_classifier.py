import json
import unittest
from unittest.mock import patch

from tests.provider_helpers import provider_env
from tests.test_cli import FIXTURE_DIR, run_cli
from tests.test_core import load_fixture
from turnaware import evaluate
from turnaware.classifiers import SUPPORTED_CLASSIFIERS, get_classifier
from turnaware.errors import ValidationError


def fixture_provider_env(verdict="ACK"):
    return provider_env(
        verdict,
        checked=["trigger:trigger-speak"],
        confidences={"PASS": 0.05, "ACK": 0.8, "ASK": 0.05, "SPEAK": 0.1},
        reasons=["Fixture provider response used by product classifier tests."],
    )


class ProviderClassifierTests(unittest.TestCase):
    def test_only_product_classifier_path_is_supported(self):
        self.assertEqual(SUPPORTED_CLASSIFIERS, ("product",))

        with self.assertRaises(ValidationError):
            get_classifier("deterministic")

    def test_product_default_uses_provider_result_not_local_keyword_path(self):
        with patch.dict("os.environ", fixture_provider_env("ACK"), clear=True):
            result = evaluate(load_fixture("speak"))

        self.assertEqual(result["classifier"], "product")
        self.assertEqual(result["verdict"], "ACK")
        self.assertEqual(result["reasons"], ["Fixture provider response used by product classifier tests."])

    def test_product_default_accepts_openai_compatible_provider_response(self):
        provider_result = {
            "verdict": "SPEAK",
            "confidences": {"PASS": 0.05, "ACK": 0.05, "ASK": 0.05, "SPEAK": 0.85},
            "context_checked": ["trigger:trigger-speak"],
            "reasons": ["OpenAI-compatible provider selected SPEAK."],
        }
        completion_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(provider_result),
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(completion_response).encode("utf-8")

        env = {
            "TURNAWARE_CLASSIFIER_MODEL": "turnaware/provider-test-model",
            "OPENROUTER_API_KEY": "test-key",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("urllib.request.urlopen", return_value=FakeResponse()) as opened:
                result = evaluate(load_fixture("speak"))

        self.assertEqual(result["classifier"], "product")
        self.assertEqual(result["classifier_provider"], "openai-compatible")
        self.assertEqual(result["classifier_model"], "turnaware/provider-test-model")
        self.assertEqual(result["verdict"], "SPEAK")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")

    def test_product_default_without_provider_config_fails_clearly(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValidationError) as caught:
                evaluate(load_fixture("speak"))

        self.assertIn("classifier provider", str(caught.exception).casefold())

    def test_cli_rejects_deterministic_classifier_path(self):
        completed = run_cli(["--classifier", "deterministic", "--input", str(FIXTURE_DIR / "speak.json")])

        self.assertEqual(completed.returncode, 3)
        self.assertEqual(completed.stdout, "")
        self.assertIn("unsupported classifier", completed.stderr.lower())


if __name__ == "__main__":
    unittest.main()
