"""Admission classifier registry and product provider boundary."""

from __future__ import annotations

import json
import os
import socket
import time
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

# Bounded retry defaults for transient OpenRouter failures (timeouts, provider
# overload). DEFAULT_MAX_RETRIES=2 means up to 3 attempts total.
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BASE_DELAY = 0.5
# HTTP status codes treated as transient and worth retrying. 429 (rate limit)
# and 5xx (provider-side) are recoverable; every other 4xx is permanent
# (auth/validation/quota-forbidden) and must abort immediately.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


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

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

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
        response_body = self._read_with_retries(http_request)

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise TurnAwareError("classifier provider returned invalid JSON") from exc

    def _read_with_retries(self, http_request: urllib.request.Request) -> str:
        # Up to max_retries retries (max_retries + 1 attempts total). Only
        # transient failures are retried; permanent errors abort immediately to
        # avoid wasting tokens/time. The happy path makes exactly one call and
        # never sleeps.
        last_exc: TurnAwareError
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                error = TurnAwareError(f"classifier provider HTTP {exc.code}: {details}")
                if exc.code not in RETRYABLE_STATUS_CODES:
                    # Permanent (auth/validation/quota-forbidden): never retry.
                    raise error from exc
                last_exc = error
            except (socket.timeout, urllib.error.URLError, OSError) as exc:
                last_exc = TurnAwareError(f"classifier provider request failed: {exc}")

            if attempt < self.max_retries:
                time.sleep(self.retry_base_delay * (2 ** attempt))

        raise last_exc


class ProductAdmissionClassifier:
    """Default admission classifier backed by a configured provider/model."""

    def __init__(self, name: str = PRODUCT_CLASSIFIER, config: dict[str, Any] | None = None) -> None:
        self.name = name
        self.config = _normalise_config(config) or {}
        # base_url and the API key source are operator-only. A request envelope
        # carries classifier_config, so allowing it to set base_url would let an
        # untrusted request redirect the provider call (with the operator's API
        # key) to an attacker host, and api_key_env would let it name any env var
        # to exfiltrate as the bearer token. Both are resolved exclusively from
        # operator environment variables below. max_retries and retry_base_delay
        # only tune transient-failure resilience (no host/credential influence),
        # so they are safe to accept from classifier_config. require_pass_corroboration
        # only post-processes the emitted verdict (a downgrade, never an upgrade),
        # so it has no host/credential influence and is safe from classifier_config.
        unsupported = set(self.config).difference(
            {"model", "provider", "timeout", "max_retries", "retry_base_delay", "require_pass_corroboration"}
        )
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValidationError(f"unsupported classifier_config for {name}: {names}")

        # Opt-in structural guard for FR-005: every tested model PASSes on a bare
        # unverified completion claim ("Already handled. Resolved.") with no
        # corroborating context. When enabled, a PASS that did not consult any
        # `context:` reference is downgraded to ASK (see _decision_from_provider_result).
        self.require_pass_corroboration = _require_pass_corroboration_config(self.config)

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

        api_key = _api_key()
        if not api_key:
            raise ValidationError(
                "classifier provider API key is required via TURNAWARE_CLASSIFIER_API_KEY or OPENROUTER_API_KEY"
            )

        base_url = (
            os.environ.get("TURNAWARE_CLASSIFIER_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or DEFAULT_BASE_URL
        )
        timeout = _timeout_config(self.config)
        self.client = OpenAICompatibleAdmissionClient(
            base_url=base_url,
            api_key=api_key,
            model=self.model_id,
            timeout=timeout,
            max_retries=_max_retries_config(self.config),
            retry_base_delay=_retry_base_delay_config(self.config),
        )

    def classify(self, request: AdmissionRequest) -> ClassifierDecision:
        provider_payload = self.client.classify(request)
        result_payload = _extract_result_payload(provider_payload)
        return _decision_from_provider_result(
            result_payload,
            request,
            require_pass_corroboration=self.require_pass_corroboration,
        )


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


def _max_retries_config(config: dict[str, Any]) -> int:
    value = config.get("max_retries", DEFAULT_MAX_RETRIES)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError("classifier_config.max_retries must be a non-negative integer")
    return value


def _retry_base_delay_config(config: dict[str, Any]) -> float:
    value = config.get("retry_base_delay", DEFAULT_RETRY_BASE_DELAY)
    if isinstance(value, bool) or not isinstance(value, Real) or value <= 0:
        raise ValidationError("classifier_config.retry_base_delay must be a positive number")
    return float(value)


def _require_pass_corroboration_config(config: dict[str, Any]) -> bool:
    # Default False preserves current behavior (PASS emitted as the provider
    # returned it). Only a literal bool is accepted; 1/0/"true" are rejected so
    # the flag is unambiguous about whether the guard is armed.
    value = config.get("require_pass_corroboration", False)
    if not isinstance(value, bool):
        raise ValidationError("classifier_config.require_pass_corroboration must be a boolean")
    return value


def _api_key() -> str | None:
    # Operator-only: the caller never names which env var holds the key.
    return os.environ.get("TURNAWARE_CLASSIFIER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")


def _system_prompt() -> str:
    verdicts = ", ".join(VERDICTS)
    return (
        "You are TurnAware's admission classifier. You are given one participant in a shared, multi-party "
        "conversation (\"this agent\") and the conversation around it. Decide ONLY whether this agent "
        "should visibly take a turn right now, and what shape of turn. Do not write any reply, draft, or "
        "message content.\n\n"
        "The envelope describes the room: `agent` is who this agent is (its `id`, any `mention_id` — its "
        "@mention handle on this surface — and any `role`). `trigger` is the message it is reacting to, "
        "with its `author`. `context` is the recent conversation, oldest first; each item names its "
        "`author` and `type` — `operator` (a human this agent serves), `peer` (another participant), "
        "`self` (a message this agent wrote earlier), or `pinned-rules` (this room's own governance "
        "text).\n\n"
        "Answer the question a person answers instinctively before speaking in any group conversation: "
        "reading who is talking, what has already been said, and who I am in this room — is it my turn? "
        "Judge as a socially competent participant in this agent's position would:\n"
        "- A message plainly directed at another participant — it names them, or @mentions an id that is "
        "not this agent's `id` or `mention_id` — and not at this agent or the room at large, is not this "
        "agent's turn.\n"
        "- Repeating what this agent or anyone else has already said adds nothing.\n"
        "- A question or request aimed at this agent deserves a response.\n"
        "- Both silence and speaking are ordinary outcomes in a healthy room. Neither is the default; the "
        "conversation decides.\n\n"
        "If a `pinned-rules` item is present, it is this room's governance and takes precedence over "
        "plain social sense: a room may set a stricter or looser bar for taking a turn, and you apply the "
        "room's bar.\n\n"
        "Return one strict JSON object and nothing else, in exactly this shape: {\"verdict\":\"SPEAK\","
        "\"confidences\":{\"PASS\":0.0,\"ACK\":0.0,\"ASK\":0.0,\"SPEAK\":1.0},"
        "\"context_checked\":[\"trigger:example\"],\"reasons\":[\"short reason\"]}.\n"
        f"- verdict is one of {verdicts}, the shape of turn warranted: PASS — no visible turn; this agent "
        "stays silent and emits no message. ACK — a brief presence signal only. ASK — exactly one "
        "clarifying question this agent needs answered. SPEAK — one substantive participant turn.\n"
        "- confidences has all four verdicts and MUST reflect genuine uncertainty; do not always emit one "
        "high value.\n"
        "- context_checked lists only references you actually consulted, copied exactly from the "
        "envelope's `allowed_context_references`.\n"
        "- reasons MUST be a non-empty JSON array of strings, not a string."
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


def _strip_json_fence(content: str) -> str:
    """Tolerate providers that wrap the JSON object in a markdown code fence.

    Some OpenAI-compatible endpoints ignore response_format and return
    ```json ... ``` or ``` ... ```; unwrap to the inner object so portability
    across providers does not depend on strict fence-free output.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text[3:]
        if text[:4].lower() == "json":
            text = text[4:]
        end = text.rfind("```")
        if end != -1:
            text = text[:end]
    return text.strip()


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
        parsed = json.loads(_strip_json_fence(content))
    except json.JSONDecodeError as exc:
        raise TurnAwareError("classifier provider message content was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise TurnAwareError("classifier provider message content must decode to a JSON object")
    return parsed


def _normalise_context_reference(raw: str, request: AdmissionRequest) -> str | None:
    """Map one provider-reported reference to its canonical envelope reference.

    Exact matches pass through. The bare word "trigger" and prefix-less
    trigger/context ids map to their canonical form. Anything else returns
    None so the caller drops it instead of failing the evaluation.
    """
    allowed = request.allowed_context_references
    ref = raw.strip()
    if ref in allowed:
        return ref
    if ref == "trigger":
        return request.trigger.reference
    for candidate in (f"trigger:{ref}", f"context:{ref}"):
        if candidate in allowed:
            return candidate
    return None


def _decision_from_provider_result(
    payload: dict[str, Any],
    request: AdmissionRequest,
    *,
    require_pass_corroboration: bool = False,
) -> ClassifierDecision:
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
    # Reference bookkeeping must not kill an otherwise-valid verdict: providers
    # occasionally emit near-miss references ("trigger" for "trigger:<id>", or a
    # bare id without its "trigger:"/"context:" prefix). Near-misses normalise
    # to their canonical envelope reference; anything unrecognisable is dropped
    # rather than failing the whole evaluation. Dropping is conservative for the
    # FR-005 guard below: a PASS whose only "corroboration" was an unknown
    # reference ends up uncorroborated and is downgraded, never upgraded.
    normalised_checked: list[str] = []
    for item in checked:
        ref = _normalise_context_reference(item, request)
        if ref is not None and ref not in normalised_checked:
            normalised_checked.append(ref)
    checked_tuple = tuple(normalised_checked)

    reasons = payload.get("reasons")
    if not isinstance(reasons, list) or not reasons or not all(isinstance(item, str) and item.strip() for item in reasons):
        raise TurnAwareError("classifier provider must return at least one reason")
    reasons_tuple = tuple(reasons)

    # Opt-in structural mitigation for FR-005. The provider may PASS on a bare
    # completion claim ("Already handled. Resolved.") that no consulted context
    # corroborates. When require_pass_corroboration is on, a PASS that did NOT
    # consult any `context:` reference (justified by the trigger alone, or by
    # nothing) is downgraded to ASK so the unverified claim is challenged.
    #
    # The rule is purely STRUCTURAL: it keys ONLY off whether context_checked
    # contains a `context:` reference. It never inspects or pattern-matches the
    # trigger/context text, so it cannot be reintroduced via keyword traps and a
    # corroborated PASS (Covered/Duplicate, whose context_checked includes a
    # context: ref) is always left untouched.
    #
    # DELIBERATE TRADE-OFF: this also downgrades legitimate empty-context PASSes
    # (e.g. a trigger addressed to another agent, which warrants PASS with no
    # context consulted). That is why it is OPT-IN and DEFAULT OFF: it pairs with
    # the deterministic addressing fast-path that resolves "not my turn" before
    # the model is ever consulted, so the only PASSes that reach this guard are
    # the model's own judgement calls. Enable it on surfaces where unverified
    # completion claims must be challenged rather than silently trusted.
    if require_pass_corroboration and verdict == "PASS":
        # Room governance is not conversational evidence: a pinned-rules item
        # can justify HOW to judge, but it cannot corroborate a completion
        # claim, so its reference does not count toward corroboration.
        conversational_refs = {
            item.reference for item in request.context if item.type != "pinned-rules"
        }
        corroborated = any(ref in conversational_refs for ref in checked_tuple)
        if not corroborated:
            verdict = "ASK"
            reasons_tuple = reasons_tuple + (
                "PASS not corroborated by any checked context item; "
                "require_pass_corroboration downgraded PASS -> ASK",
            )

    return ClassifierDecision(
        verdict=verdict,
        confidences=normalised_confidences,
        context_checked=checked_tuple,
        reasons=reasons_tuple,
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
