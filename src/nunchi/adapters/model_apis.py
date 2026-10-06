"""Attention routes through two more model APIs: Messages and Responses.

Step 8 of the plan on #94 (#87). The core's own route is any OpenAI-compatible
chat completions endpoint. These two adapters send the same prompt, the same
observation text and the same answer schema through two other request shapes:

- ``messages-api``: the Anthropic Messages API, ``POST {base_url}/messages``;
- ``responses-api``: the OpenAI Responses API, ``POST {base_url}/responses``.

Each hands the reply to the core's own decoder, so the engine validates every
route's judgment the same way. They live outside the core because each names
one provider's protocol; any endpoint that speaks the protocol works, a
router included. The endpoint is always explicit configuration.

Both ask the API to hold the reply to the judgment schema. Structured output
on these APIs accepts a subset of JSON Schema: no numeric, length or array
bounds, and every property required. The adapters send that portable form;
the engine still checks the bounds itself.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
import os
import socket
from typing import Any, Mapping
import urllib.error
import urllib.request

from ..attention import (
    AttentionError,
    attention_input_text,
    attention_judgment_schema,
    decode_judgment_text,
)
from ..errors import ValidationError
from .decisions_api import ATTENTION_KINDS as _DECISIONS_KINDS


MESSAGES_KIND = "messages-api"
RESPONSES_KIND = "responses-api"
MESSAGES_API_VERSION = "2023-06-01"
SCHEMA_NAME = "nunchi_attention"
# Room for the judgment, a full reading (4 notes of up to 400 characters), and
# a model that thinks before it answers.
DEFAULT_MAX_TOKENS = 4096
_UNPORTABLE = frozenset(
    {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "uniqueItems"}
)
_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def portable_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """The judgment schema in the subset structured output accepts.

    Drops numeric, length and array bounds, and makes every property
    required: an optional field becomes one the model may leave empty or
    null. The engine validates the bounds on the reply as it does for every
    route.
    """

    def strip(node: Any) -> Any:
        if isinstance(node, list):
            return [strip(item) for item in node]
        if not isinstance(node, Mapping):
            return node
        out = {key: strip(value) for key, value in node.items() if key not in _UNPORTABLE}
        if out.get("type") == "object" and isinstance(out.get("properties"), Mapping):
            out["required"] = list(out["properties"])
        return out

    return strip(deepcopy(dict(schema)))


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"attention model {label} must be non-empty")
    return value


class _JsonRoute:
    """One configured HTTPS call that returns one judgment object."""

    path = ""
    kind = ""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        name: str = "participant-attention",
        provider: str | None = None,
        temperature: float | None = None,
        effort: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        extra_body: Mapping[str, Any] | None = None,
    ) -> None:
        _nonempty(model, "model")
        _nonempty(api_key, "api_key")
        _nonempty(base_url, "base_url")
        _nonempty(name, "name")
        if provider is not None:
            _nonempty(provider, "provider")
        if temperature is not None and (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or temperature < 0
        ):
            raise ValidationError("attention model temperature must be a finite non-negative number")
        if effort is not None and effort not in _EFFORTS:
            raise ValidationError(f"attention model effort must be one of {', '.join(_EFFORTS)}")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 256 <= max_tokens <= 65536:
            raise ValidationError("attention model max_tokens must be an integer from 256 through 65536")
        extra = dict(extra_body or {})
        reserved = self._reserved() & set(extra)
        if reserved:
            raise ValidationError(f"attention model extra_body cannot override {sorted(reserved)}")
        self.name = name
        self.provider = provider or self.kind
        self.model_id = model
        self._api_key = api_key
        self._url = base_url.rstrip("/") + self.path
        self._temperature = temperature
        self._effort = effort
        self._max_tokens = max_tokens
        self._extra_body = deepcopy(extra)
        # The provider's last full response, for audits and evaluations.
        self.last_response: Mapping[str, Any] | None = None

    @staticmethod
    def _reserved() -> set[str]:
        return set()

    @classmethod
    def _config_fields(cls) -> set[str]:
        return {
            "model",
            "base_url",
            "name",
            "provider",
            "api_key_env",
            "temperature",
            "effort",
            "max_tokens",
            "extra_body",
        }

    @classmethod
    def _from_config(cls, config: Mapping[str, Any], **extra: Any) -> Any:
        if not isinstance(config, Mapping) or set(config) - cls._config_fields():
            raise ValidationError("attention model config has unexpected fields")
        if not config.get("base_url"):
            raise ValidationError(
                f"attention model base_url is required: name the {cls.kind} endpoint explicitly"
            )
        extra_body = config.get("extra_body")
        if extra_body is not None and not isinstance(extra_body, Mapping):
            raise ValidationError("attention model extra_body must be an object")
        api_key_env = config.get("api_key_env", "NUNCHI_ATTENTION_API_KEY")
        if not isinstance(api_key_env, str) or not api_key_env:
            raise ValidationError("attention model api_key_env must be non-empty")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValidationError(f"attention model credential is absent from {api_key_env}")
        return cls(
            model=config.get("model"),
            api_key=api_key,
            base_url=config["base_url"],
            name=config.get("name", "participant-attention"),
            provider=config.get("provider"),
            temperature=config.get("temperature"),
            effort=config.get("effort"),
            max_tokens=config.get("max_tokens", DEFAULT_MAX_TOKENS),
            extra_body=extra_body,
            **extra,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, body: Mapping[str, Any], timeout_seconds: float) -> Mapping[str, Any]:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise AttentionError(f"attention provider returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, socket.timeout, OSError, json.JSONDecodeError) as exc:
            raise AttentionError("attention provider request failed") from exc
        if not isinstance(payload, Mapping):
            raise AttentionError("attention provider response was not an object")
        self.last_response = payload
        return payload


class MessagesAttentionModel(_JsonRoute):
    """The participant's attention through the Anthropic Messages API.

    ``auth`` is ``x-api-key`` for the provider's own endpoint and ``bearer``
    for a router that takes the key as a bearer token.
    """

    path = "/messages"
    kind = MESSAGES_KIND

    def __init__(self, *, auth: str = "x-api-key", **kwargs: Any) -> None:
        if auth not in ("x-api-key", "bearer"):
            raise ValidationError("attention model auth must be x-api-key or bearer")
        self._auth = auth
        super().__init__(**kwargs)

    @staticmethod
    def _reserved() -> set[str]:
        return {"model", "system", "messages", "max_tokens", "output_config", "temperature"}

    @classmethod
    def from_trusted_config(cls, config: Mapping[str, Any]) -> "MessagesAttentionModel":
        if not isinstance(config, Mapping):
            raise ValidationError("attention model config has unexpected fields")
        body = {key: value for key, value in config.items() if key != "auth"}
        return cls._from_config(body, auth=config.get("auth", "x-api-key"))

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": MESSAGES_API_VERSION,
        }
        if self._auth == "bearer":
            headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            headers["x-api-key"] = self._api_key
        return headers

    def judge(
        self,
        *,
        instructions: str,
        projection: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        output_config: dict[str, Any] = {
            "format": {
                "type": "json_schema",
                "schema": portable_schema(
                    attention_judgment_schema(unattended=bool(projection.get("unattended_event_ids")))
                ),
            }
        }
        if self._effort is not None:
            output_config["effort"] = self._effort
        body: dict[str, Any] = {
            **deepcopy(self._extra_body),
            "model": self.model_id,
            "max_tokens": self._max_tokens,
            "system": instructions,
            "messages": [{"role": "user", "content": attention_input_text(projection)}],
            "output_config": output_config,
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        self.last_response = None
        payload = self._post(body, timeout_seconds)
        stop = payload.get("stop_reason")
        if stop in ("refusal", "max_tokens"):
            raise AttentionError(f"attention provider stopped early ({stop})")
        content = payload.get("content")
        if not isinstance(content, list):
            raise AttentionError("attention provider response has no content")
        text = "".join(
            block["text"]
            for block in content
            if isinstance(block, Mapping) and block.get("type") == "text" and isinstance(block.get("text"), str)
        )
        if not text:
            raise AttentionError("attention provider response has no text")
        return decode_judgment_text(text)


class ResponsesAttentionModel(_JsonRoute):
    """The participant's attention through the OpenAI Responses API.

    The request is stateless: it asks the provider not to store it.
    """

    path = "/responses"
    kind = RESPONSES_KIND

    @staticmethod
    def _reserved() -> set[str]:
        return {"model", "instructions", "input", "text", "max_output_tokens", "temperature", "store"}

    @classmethod
    def from_trusted_config(cls, config: Mapping[str, Any]) -> "ResponsesAttentionModel":
        return cls._from_config(config)

    def judge(
        self,
        *,
        instructions: str,
        projection: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        body: dict[str, Any] = {
            **deepcopy(self._extra_body),
            "model": self.model_id,
            "instructions": instructions,
            "input": [{"role": "user", "content": attention_input_text(projection)}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": SCHEMA_NAME,
                    "schema": portable_schema(
                        attention_judgment_schema(unattended=bool(projection.get("unattended_event_ids")))
                    ),
                    "strict": True,
                }
            },
            "max_output_tokens": self._max_tokens,
            "store": False,
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        if self._effort is not None:
            body["reasoning"] = {**dict(body.get("reasoning") or {}), "effort": self._effort}
        self.last_response = None
        payload = self._post(body, timeout_seconds)
        if payload.get("status") not in (None, "completed"):
            raise AttentionError(f"attention provider response is {payload.get('status')}")
        texts = []
        for item in payload.get("output") or ():
            if not isinstance(item, Mapping) or item.get("type") != "message":
                continue
            for part in item.get("content") or ():
                if not isinstance(part, Mapping):
                    continue
                if part.get("type") == "refusal":
                    raise AttentionError("attention provider refused")
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        if not texts:
            raise AttentionError("attention provider response has no output text")
        return decode_judgment_text("".join(texts))


# Every attention route outside the core, for
# ``attention_model_from_config(..., host_kinds=ATTENTION_KINDS)``.
ATTENTION_KINDS = {
    **_DECISIONS_KINDS,
    MESSAGES_KIND: MessagesAttentionModel.from_trusted_config,
    RESPONSES_KIND: ResponsesAttentionModel.from_trusted_config,
}
