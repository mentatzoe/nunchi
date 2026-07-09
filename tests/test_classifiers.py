import json
import unittest
from unittest.mock import patch

from tests.provider_helpers import fixture_case, provider_env
from tests.test_core import load_fixture
from nunchi import evaluate
from nunchi.classifiers import (
    SUPPORTED_CLASSIFIERS,
    _provider_envelope,
    _system_prompt,
    get_classifier,
)
from nunchi.errors import ValidationError
from nunchi.schema import validate_request


class ClassifierTests(unittest.TestCase):
    def test_registry_supports_only_product_default_path(self):
        self.assertEqual(SUPPORTED_CLASSIFIERS, ("product",))

    def test_product_classifier_uses_provider_model_identity(self):
        with patch.dict("os.environ", provider_env("ASK", checked=["trigger:trigger-speak"]), clear=True):
            product = get_classifier("product")

        self.assertEqual(type(product).__name__, "ProductAdmissionClassifier")
        self.assertEqual(getattr(product, "provider", None), "test-fixture")
        self.assertEqual(getattr(product, "model_id", None), "nunchi-test-fixture-provider")

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


class ProviderEnvelopeAliasTests(unittest.TestCase):
    """agent.aliases flows to the provider; absent aliases stay byte-identical."""

    _RAW_REQUEST = {
        "request_id": "req-golden",
        "trigger": {
            "id": "t1",
            "author": "zoe",
            "content": "Vigil, can you take a look?",
            "timestamp": "2026-07-08T10:00:00Z",
        },
        "context": [
            {
                "id": "c1",
                "type": "peer",
                "author": "dalgos",
                "content": "I'm on the deploy.",
                "timestamp": "2026-07-08T09:59:00Z",
            }
        ],
        "agent": {"id": "vigil", "mention_id": "111", "role": "participant"},
        "surface": {"type": "discord-channel"},
    }

    # The exact serialized provider envelope (the user-message content the
    # OpenAI-compatible client sends) for the alias-free request above, as
    # produced BEFORE agent.aliases existed. Backward-compat contract: with no
    # aliases supplied, the classifier request must stay byte-for-byte
    # identical to this golden.
    _GOLDEN = (
        '{"agent": {"id": "vigil", "mention_id": "111", "role": "participant"}, '
        '"allowed_context_references": ["context:c1", "trigger:t1"], '
        '"context": [{"author": "dalgos", "content": "I\'m on the deploy.", '
        '"reference": "context:c1", "timestamp": "2026-07-08T09:59:00Z", "type": "peer"}], '
        '"request_id": "req-golden", "surface": {"type": "discord-channel"}, '
        '"trigger": {"author": "zoe", "content": "Vigil, can you take a look?", '
        '"reference": "trigger:t1", "timestamp": "2026-07-08T10:00:00Z"}}'
    )

    def test_no_aliases_provider_envelope_matches_golden_byte_for_byte(self):
        request = validate_request(dict(self._RAW_REQUEST))
        serialized = json.dumps(_provider_envelope(request), sort_keys=True)
        self.assertEqual(serialized, self._GOLDEN)

    def test_aliases_are_carried_into_the_provider_envelope(self):
        raw = dict(self._RAW_REQUEST)
        raw["agent"] = {**raw["agent"], "aliases": ["Vigil", "Codex", "222222222222222222"]}
        request = validate_request(raw)
        envelope = _provider_envelope(request)
        self.assertEqual(envelope["agent"]["aliases"], ["Vigil", "Codex", "222222222222222222"])

    def test_system_prompt_explains_aliases_as_addressable_identities(self):
        prompt = _system_prompt()
        self.assertIn("`aliases`", prompt)
        self.assertIn("several", prompt)  # one agent may carry several identities


class ClassifierConfigProvenanceTests(unittest.TestCase):
    """Request-supplied config must not steer the outbound call or key source."""

    def test_request_supplied_base_url_is_rejected(self):
        # base_url in the envelope would let an untrusted request redirect the
        # provider call (carrying the operator API key) to an attacker host.
        with patch.dict("os.environ", provider_env("ASK", checked=["trigger:trigger-speak"]), clear=True):
            with self.assertRaises(ValidationError) as caught:
                get_classifier("product", {"base_url": "http://attacker.example/v1"})
        self.assertIn("base_url", str(caught.exception))

    def test_request_supplied_api_key_env_is_rejected(self):
        # api_key_env would let a request name an arbitrary environment variable
        # to read and exfiltrate as the bearer token.
        with patch.dict("os.environ", provider_env("ASK", checked=["trigger:trigger-speak"]), clear=True):
            with self.assertRaises(ValidationError) as caught:
                get_classifier("product", {"api_key_env": "AWS_SECRET_ACCESS_KEY"})
        self.assertIn("api_key_env", str(caught.exception))

    def test_base_url_resolves_only_from_operator_environment(self):
        env = {
            "NUNCHI_CLASSIFIER_MODEL": "operator/model",
            "OPENROUTER_API_KEY": "operator-key",
            "NUNCHI_CLASSIFIER_BASE_URL": "https://operator.internal/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            product = get_classifier("product")
        self.assertEqual(product.client.base_url, "https://operator.internal/v1")

    def test_api_key_resolves_only_from_fixed_operator_environment(self):
        env = {
            "NUNCHI_CLASSIFIER_MODEL": "operator/model",
            "NUNCHI_CLASSIFIER_API_KEY": "operator-key",
        }
        with patch.dict("os.environ", env, clear=True):
            product = get_classifier("product")
        self.assertEqual(product.client.api_key, "operator-key")


if __name__ == "__main__":
    unittest.main()
