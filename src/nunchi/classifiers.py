"""Bounded OpenAI-compatible provider boundary for V2 social attention."""

from __future__ import annotations

import hashlib
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from .errors import NunchiError, ValidationError
from .policy import ClassifierPolicy


MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024


def _attention_v2_system_prompt() -> str:
    return (
        "You are the named participant's pre-attention faculty in a live shared "
        "conversation. Read the supplied current factual room snapshot as that "
        "participant would. Decide whether this current conversational moment is "
        "worth waking the participant now. The trigger_event_id is only the anchor "
        "that caused a fresh look; it is not an obligation to answer that event, and "
        "later events may have superseded or resolved it. Do not compose a reply, "
        "issue a tool instruction, infer a complete roster, or decide authorization.\n\n"
        "Return one JSON object only with: disposition (SUPPRESS, WAKE, or DEFER), "
        "reasons (array of short strings), evidence_event_ids (array containing only "
        "supplied event IDs), optional legacy_verdict_confidences with exactly PASS, "
        "ACK, ASK, SPEAK numeric values in [0,1], and optional attention_advice only "
        "for WAKE as an array of {note,evidence_event_ids}. Use SUPPRESS only when "
        "confident the participant would not want attention. Uncertainty is DEFER. "
        "Advice is a sparse non-authoritative observation, never drafted response text."
    )


def attention_v2_prompt_digest() -> str:
    """Return stable provenance for the exact V2 social-judgment prompt."""
    return "sha256:" + hashlib.sha256(
        _attention_v2_system_prompt().encode("utf-8")
    ).hexdigest()


def _strict_json(raw: str | bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(
            ValueError("non-finite JSON number")
        ),
    )


def _strip_json_fence(content: str) -> str:
    """Unwrap one provider-added JSON markdown fence."""
    text = content.strip()
    if text.startswith("```"):
        text = text[3:]
        if text[:4].lower() == "json":
            text = text[4:]
        end = text.rfind("```")
        if end != -1:
            text = text[:end]
    return text.strip()


def _extract_result_payload(provider_payload: Any) -> dict[str, Any]:
    if not isinstance(provider_payload, dict):
        raise NunchiError("attention provider response must be a JSON object")
    choices = provider_payload.get("choices")
    if choices is None:
        return provider_payload
    if not isinstance(choices, list) or not choices:
        raise NunchiError("attention provider response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise NunchiError("attention provider choice is invalid")
    message = first.get("message")
    if not isinstance(message, dict):
        raise NunchiError("attention provider choice is invalid")
    content = message.get("content")
    if not isinstance(content, str):
        raise NunchiError("attention provider message is invalid")
    try:
        parsed = _strict_json(_strip_json_fence(content))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise NunchiError("attention provider message is invalid") from exc
    if not isinstance(parsed, dict):
        raise NunchiError("attention provider message is invalid")
    return parsed


def _bounded_response(response) -> bytes:
    body = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
    if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
        raise NunchiError("attention provider response exceeded its size budget")
    return body


def classify_attention_v2(
    projection: dict[str, Any],
    config: ClassifierPolicy,
) -> dict[str, Any]:
    """Invoke one trusted OpenAI-compatible V2 classifier configuration.

    Provider identity, endpoint, model, credential, timeout, and retry data come
    only from strict operator policy. Retries repeat the identical judgment and
    use the fixed 0.5s/1.0s schedule.
    """
    if not isinstance(projection, dict) or not isinstance(config, ClassifierPolicy):
        raise ValidationError("V2 classifier configuration is invalid")
    payload = {
        "model": config.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _attention_v2_system_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    projection,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ],
    }
    body = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if config.api_key is not None:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = urllib.request.Request(
        config.endpoint,
        data=body,
        method="POST",
        headers=headers,
    )
    retry_delays = (0.5, 1.0)
    last_error: Exception | None = None
    for attempt in range(config.max_retries + 1):
        try:
            with urllib.request.urlopen(
                request,
                timeout=config.timeout_seconds,
            ) as response:
                response_body = _bounded_response(response)
            try:
                provider_payload = _strict_json(response_body)
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                raise NunchiError("attention provider returned invalid JSON") from exc
            return _extract_result_payload(provider_payload)
        except urllib.error.HTTPError as exc:
            last_error = NunchiError(f"attention provider HTTP {exc.code}")
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            exc.close()
            if not retryable:
                raise last_error from exc
        except (socket.timeout, TimeoutError):
            last_error = TimeoutError("attention provider timed out")
        except urllib.error.URLError:
            last_error = NunchiError("attention provider request failed")
        except OSError:
            last_error = NunchiError("attention provider request failed")
        if attempt < config.max_retries:
            time.sleep(retry_delays[attempt])
    assert last_error is not None
    raise last_error


__all__ = ["attention_v2_prompt_digest", "classify_attention_v2"]
