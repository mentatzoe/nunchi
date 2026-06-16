import io
import json
import socket
import unittest
import urllib.error
from unittest.mock import patch

from tests.provider_helpers import provider_env
from tests.test_cli import FIXTURE_DIR, run_cli
from tests.test_core import load_fixture
from turnaware import evaluate
from turnaware.classifiers import SUPPORTED_CLASSIFIERS, get_classifier
from turnaware.errors import TurnAwareError, ValidationError


def fixture_provider_env(verdict="ACK"):
    return provider_env(
        verdict,
        checked=["trigger:trigger-speak"],
        confidences={"PASS": 0.05, "ACK": 0.8, "ASK": 0.05, "SPEAK": 0.1},
        reasons=["Fixture provider response used by product classifier tests."],
    )


def _ok_completion_response():
    provider_result = {
        "verdict": "SPEAK",
        "confidences": {"PASS": 0.05, "ACK": 0.05, "ASK": 0.05, "SPEAK": 0.85},
        "context_checked": ["trigger:trigger-speak"],
        "reasons": ["provider selected SPEAK after retry."],
    }
    completion = {"choices": [{"message": {"content": json.dumps(provider_result)}}]}
    return completion


class _FakeResponse:
    def __init__(self, completion):
        self._body = json.dumps(completion).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _http_error(code):
    # HTTPError needs a readable fp so the client's exc.read() works.
    return urllib.error.HTTPError(
        url="https://openrouter.ai/api/v1/chat/completions",
        code=code,
        msg="boom",
        hdrs=None,
        fp=io.BytesIO(b"provider error body"),
    )


# Provider env that omits TURNAWARE_CLASSIFIER_TEST_RESULT so the live
# OpenAICompatibleAdmissionClient path (with retry) is exercised.
LIVE_PROVIDER_ENV = {
    "TURNAWARE_CLASSIFIER_MODEL": "turnaware/provider-test-model",
    "OPENROUTER_API_KEY": "test-key",
}


class ProviderRetryTests(unittest.TestCase):
    def test_transient_failure_then_success_retries_and_succeeds(self):
        # First urlopen call raises a transient 503, second succeeds.
        side_effects = [_http_error(503), _FakeResponse(_ok_completion_response())]
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with patch("turnaware.classifiers.time.sleep") as slept:
                with patch("urllib.request.urlopen", side_effect=side_effects) as opened:
                    result = evaluate(load_fixture("speak"))

        self.assertEqual(result["verdict"], "SPEAK")
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(slept.call_count, 1)

    def test_socket_timeout_then_success_retries_and_succeeds(self):
        side_effects = [socket.timeout("timed out"), _FakeResponse(_ok_completion_response())]
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with patch("turnaware.classifiers.time.sleep"):
                with patch("urllib.request.urlopen", side_effect=side_effects) as opened:
                    result = evaluate(load_fixture("speak"))

        self.assertEqual(result["verdict"], "SPEAK")
        self.assertEqual(opened.call_count, 2)

    def test_401_aborts_immediately_without_retry(self):
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with patch("turnaware.classifiers.time.sleep") as slept:
                with patch("urllib.request.urlopen", side_effect=_http_error(401)) as opened:
                    with self.assertRaises(TurnAwareError):
                        evaluate(load_fixture("speak"))

        self.assertEqual(opened.call_count, 1)
        self.assertEqual(slept.call_count, 0)

    def test_403_aborts_immediately_without_retry(self):
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with patch("turnaware.classifiers.time.sleep") as slept:
                with patch("urllib.request.urlopen", side_effect=_http_error(403)) as opened:
                    with self.assertRaises(TurnAwareError):
                        evaluate(load_fixture("speak"))

        self.assertEqual(opened.call_count, 1)
        self.assertEqual(slept.call_count, 0)

    def test_exhausting_retries_raises_turnaware_error(self):
        # Always transient: default max_retries=2 -> 3 attempts -> 2 sleeps.
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with patch("turnaware.classifiers.time.sleep") as slept:
                with patch("urllib.request.urlopen", side_effect=_http_error(503)) as opened:
                    with self.assertRaises(TurnAwareError):
                        evaluate(load_fixture("speak"))

        self.assertEqual(opened.call_count, 3)
        self.assertEqual(slept.call_count, 2)

    def test_max_retries_config_controls_attempt_count(self):
        config = {"max_retries": 1, "retry_base_delay": 0.1}
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with patch("turnaware.classifiers.time.sleep") as slept:
                with patch("urllib.request.urlopen", side_effect=_http_error(500)) as opened:
                    with self.assertRaises(TurnAwareError):
                        evaluate(load_fixture("speak"), classifier_config=config)

        self.assertEqual(opened.call_count, 2)
        self.assertEqual(slept.call_count, 1)

    def test_retry_config_keys_accepted_via_classifier_config(self):
        config = {"max_retries": 0, "retry_base_delay": 1.5}
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with patch("turnaware.classifiers.time.sleep") as slept:
                with patch(
                    "urllib.request.urlopen",
                    return_value=_FakeResponse(_ok_completion_response()),
                ) as opened:
                    result = evaluate(load_fixture("speak"), classifier_config=config)

        # max_retries=0 -> exactly one attempt, no sleeps on the happy path.
        self.assertEqual(result["verdict"], "SPEAK")
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(slept.call_count, 0)

    def test_negative_max_retries_raises_validation_error(self):
        config = {"max_retries": -1}
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with self.assertRaises(ValidationError):
                get_classifier("product", config)

    def test_zero_retry_base_delay_raises_validation_error(self):
        config = {"retry_base_delay": 0}
        with patch.dict("os.environ", LIVE_PROVIDER_ENV, clear=True):
            with self.assertRaises(ValidationError):
                get_classifier("product", config)


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
        payload = json.loads(request.data.decode("utf-8"))
        system_prompt = payload["messages"][0]["content"]
        self.assertIn('"reasons":["short reason"]', system_prompt)
        self.assertIn("reasons MUST be a non-empty JSON array of strings", system_prompt)
        # Admission rubric: the load-bearing pragmatic rules every candidate
        # model must be told (addressing, suppressors, unverified-resolution).
        self.assertIn("ADDRESSING", system_prompt)
        self.assertIn("mention_id", system_prompt)
        self.assertIn("SUPPRESSORS", system_prompt)
        self.assertIn("Covered", system_prompt)
        self.assertIn("Duplicate", system_prompt)
        self.assertIn("UNVERIFIED RESOLUTION", system_prompt)
        self.assertIn("net-new value", system_prompt)
        self.assertIn("return SPEAK rather than ACK", system_prompt)

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

    def test_markdown_fenced_provider_json_is_accepted(self):
        # Some OpenAI-compatible endpoints ignore response_format and wrap the
        # object in a ```json fence; the parser must unwrap it for portability.
        provider_result = {
            "verdict": "PASS",
            "confidences": {"PASS": 0.8, "ACK": 0.1, "ASK": 0.05, "SPEAK": 0.05},
            "context_checked": ["trigger:trigger-pass", "context:ctx-pass-handled"],
            "reasons": ["fenced JSON still parses"],
        }
        fenced = "```json\n" + json.dumps(provider_result) + "\n```"
        completion = {"choices": [{"message": {"content": fenced}}]}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(completion).encode("utf-8")

        env = {"TURNAWARE_CLASSIFIER_MODEL": "m", "OPENROUTER_API_KEY": "k"}
        with patch.dict("os.environ", env, clear=True):
            with patch("urllib.request.urlopen", return_value=FakeResponse()):
                result = evaluate(load_fixture("pass"))
        self.assertEqual(result["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
