"""Admission classifier registry and product provider boundary."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from numbers import Real
from typing import Any, Protocol

from .errors import TurnAwareError, ValidationError
from .models import AdmissionRequest, AdmissionResult, FORBIDDEN_REPLY_FIELDS, VERDICTS

PRODUCT_CLASSIFIER = "product"
SUPPORTED_CLASSIFIERS = (PRODUCT_CLASSIFIER,)

DEFAULT_PROVIDER = "openai-compatible"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
TEST_RESULT_ENV = "TURNAWARE_CLASSIFIER_TEST_RESULT"


@dataclass(frozen=True)
class ClassifierDecision:
    verdict: str
    confidences: dict[str, float]
    context_checked: tuple[str, ...]
    reasons: tuple[str, ...]


class AdmissionClassifier(Protocol):
    name: str
    provider: str
    model_id: str

    def classify(self, request: AdmissionRequest) -> ClassifierDecision:
        """Return an admission-only decision for one validated request."""


class FixtureAdmissionClient:
    """Deterministic provider transport for offline tests and CI evidence."""

    def __init__(self, raw_result: str) -> None:
        self.raw_result = raw_result

    def classify(self, request: AdmissionRequest) -> dict[str, Any]:
        try:
            return json.loads(self.raw_result)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{TEST_RESULT_ENV} must contain valid JSON") from exc


class OpenAICompatibleAdmissionClient:
    """Minimal OpenAI-compatible chat-completions client using the stdlib."""

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def classify(self, request: AdmissionRequest) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps(_provider_envelope(request), sort_keys=True)},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise TurnAwareError(f"classifier provider HTTP {exc.code}: {details}") from exc
        except OSError as exc:
            raise TurnAwareError(f"classifier provider request failed: {exc}") from exc

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise TurnAwareError("classifier provider returned invalid JSON") from exc


class ProductAdmissionClassifier:
    """Default admission classifier backed by a configured provider/model."""

    def __init__(self, name: str = PRODUCT_CLASSIFIER, config: dict[str, Any] | None = None) -> None:
        self.name = name
        self.config = _normalise_config(config) or {}
        unsupported = set(self.config).difference({"api_key_env", "base_url", "model", "provider", "timeout"})
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValidationError(f"unsupported classifier_config for {name}: {names}")

        self.provider = _string_config(self.config, "provider") or DEFAULT_PROVIDER
        if self.provider != DEFAULT_PROVIDER:
            raise ValidationError(f"unsupported classifier provider {self.provider!r}")

        test_result = os.environ.get(TEST_RESULT_ENV)
        if test_result is not None:
            self.provider = "test-fixture"
            self.model_id = _string_config(self.config, "model") or os.environ.get(
                "TURNAWARE_CLASSIFIER_MODEL", "turnaware-test-fixture-provider"
            )
            self.client = FixtureAdmissionClient(test_result)
            return

        self.model_id = _string_config(self.config, "model") or os.environ.get("TURNAWARE_CLASSIFIER_MODEL")
        if not self.model_id:
            raise ValidationError(
                "classifier provider model is required via classifier_config.model or TURNAWARE_CLASSIFIER_MODEL"
            )

        api_key = _api_key(self.config)
        if not api_key:
            raise ValidationError(
                "classifier provider API key is required via TURNAWARE_CLASSIFIER_API_KEY or OPENROUTER_API_KEY"
            )

        base_url = (
            _string_config(self.config, "base_url")
            or os.environ.get("TURNAWARE_CLASSIFIER_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or DEFAULT_BASE_URL
        )
        timeout = _timeout_config(self.config)
        self.client = OpenAICompatibleAdmissionClient(
            base_url=base_url,
            api_key=api_key,
            model=self.model_id,
            timeout=timeout,
        )

    def classify(self, request: AdmissionRequest) -> ClassifierDecision:
        provider_payload = self.client.classify(request)
        result_payload = _extract_result_payload(provider_payload)
        return _decision_from_provider_result(result_payload, request)


def _normalise_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValidationError("classifier_config must be an object when supplied")
    return dict(config)


def _string_config(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"classifier_config.{key} must be a non-empty string")
    return value


def _timeout_config(config: dict[str, Any]) -> float:
    value = config.get("timeout", 30)
    if isinstance(value, bool) or not isinstance(value, Real) or value <= 0:
        raise ValidationError("classifier_config.timeout must be a positive number")
    return float(value)


def _api_key(config: dict[str, Any]) -> str | None:
    api_key_env = _string_config(config, "api_key_env")
    if api_key_env:
        return os.environ.get(api_key_env)
    return os.environ.get("TURNAWARE_CLASSIFIER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")


def _system_prompt() -> str:
    verdicts = ", ".join(VERDICTS)
    return (
        "You are TurnAware's admission classifier. Decide only whether the current agent should visibly "
        f"participate. Return strict JSON with verdict ({verdicts}), confidences for all four verdicts, "
        "context_checked references that appear in the supplied envelope, and concise reasons. Do not "
        "write reply prose, drafts, or message content. PASS means the agent must remain silent."
    )


def _provider_envelope(request: AdmissionRequest) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "trigger": {
            "reference": request.trigger.reference,
            "content": request.trigger.content,
            "author": request.trigger.author,
            "timestamp": request.trigger.timestamp,
        },
        "context": [
            {
                "reference": item.reference,
                "content": item.content,
                "type": item.type,
                "author": item.author,
                "timestamp": item.timestamp,
            }
            for item in request.context
        ],
        "agent": request.agent,
        "surface": request.surface,
        "allowed_context_references": sorted(request.allowed_context_references),
    }


def _extract_result_payload(provider_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(provider_payload, dict):
        raise TurnAwareError("classifier provider response must be a JSON object")
    choices = provider_payload.get("choices")
    if choices is None:
        return provider_payload
    if not isinstance(choices, list) or not choices:
        raise TurnAwareError("classifier provider response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise TurnAwareError("classifier provider choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise TurnAwareError("classifier provider choice did not include a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise TurnAwareError("classifier provider message content must be a JSON string")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TurnAwareError("classifier provider message content was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise TurnAwareError("classifier provider message content must decode to a JSON object")
    return parsed


def _decision_from_provider_result(payload: dict[str, Any], request: AdmissionRequest) -> ClassifierDecision:
    forbidden = FORBIDDEN_REPLY_FIELDS.intersection(payload)
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise TurnAwareError(f"classifier provider returned forbidden reply fields: {names}")

    verdict = payload.get("verdict")
    if verdict not in VERDICTS:
        raise TurnAwareError("classifier provider returned an unsupported verdict")

    confidences = payload.get("confidences")
    if not isinstance(confidences, dict):
        raise TurnAwareError("classifier provider must return confidences")
    if set(confidences) != set(VERDICTS):
        raise TurnAwareError("classifier provider confidences must contain exactly PASS, ACK, ASK, SPEAK")
    normalised_confidences: dict[str, float] = {}
    for key in VERDICTS:
        value = confidences[key]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TurnAwareError(f"classifier provider confidence for {key} must be numeric")
        normalised_confidences[key] = float(value)

    checked = payload.get("context_checked")
    if not isinstance(checked, list) or not all(isinstance(item, str) and item.strip() for item in checked):
        raise TurnAwareError("classifier provider must return context_checked as a list of references")
    checked_tuple = tuple(checked)
    unknown_refs = set(checked_tuple).difference(request.allowed_context_references)
    if unknown_refs:
        names = ", ".join(sorted(unknown_refs))
        raise TurnAwareError(f"classifier provider returned unchecked context references: {names}")

    reasons = payload.get("reasons")
    if not isinstance(reasons, list) or not reasons or not all(isinstance(item, str) and item.strip() for item in reasons):
        raise TurnAwareError("classifier provider must return at least one reason")

    return ClassifierDecision(
        verdict=verdict,
        confidences=normalised_confidences,
        context_checked=checked_tuple,
        reasons=tuple(reasons),
    )


def get_classifier(name: str | None, config: dict[str, Any] | None = None) -> AdmissionClassifier:
    selected = name or PRODUCT_CLASSIFIER
    if selected not in SUPPORTED_CLASSIFIERS:
        supported = ", ".join(SUPPORTED_CLASSIFIERS)
        raise ValidationError(f"unsupported classifier {selected!r}; supported classifiers: {supported}")
    return ProductAdmissionClassifier(selected, config)


def classify(
    request: AdmissionRequest,
    *,
    classifier: str | None = None,
    classifier_config: dict[str, Any] | None = None,
) -> AdmissionResult:
    selected = classifier or request.classifier or PRODUCT_CLASSIFIER
    config = classifier_config if classifier_config is not None else request.classifier_config
    engine = get_classifier(selected, config)
    decision = engine.classify(request)
    return AdmissionResult(
        classifier=engine.name,
        classifier_provider=engine.provider,
        classifier_model=engine.model_id,
        verdict=decision.verdict,
        confidences=decision.confidences,
        context_checked=decision.context_checked,
        reasons=decision.reasons,
        request_id=request.request_id,
    )
