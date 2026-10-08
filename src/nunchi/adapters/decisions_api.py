"""The typed-decision route for attention, through a Decisions API endpoint.

Step 4 of the plan on #94 asks steps 1 and 2 as typed questions that two
routes can answer: a chat model, and a typed decision model such as Jev. This
adapter is the second route. It speaks the request shape of OpenRouter's
Decisions API (``POST {model, state, questions}``, answered with typed
``answers``): a yes/no question becomes a ``noul``, a choice stays a
``choice``, and a pointer question becomes a choice among the candidate
messages plus "none". The answers come back in the core's shape, so the
engine decides and writes the reading exactly as it does for a chat model.

It lives outside the core because it names one provider's protocol.
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any, Mapping
import urllib.error
import urllib.request

from ..attention import DEFAULT_API_KEY_ENV, AttentionError
from ..errors import ValidationError


DEFAULT_URL = "https://openrouter.ai/api/alpha/decisions"
KIND = "decisions-api"
# Pointer questions offer at most this many of the newest candidate messages.
MAX_POINTER_OPTIONS = 12
_NONE = "none"


def _pointer_options(
    question: Mapping[str, Any],
    state: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Label each candidate message, newest last, with who said what.

    Returns the option texts and the map from option label to message id.
    """

    by_id = {item["id"]: item for item in state.get("conversation", ())}
    candidates = [event_id for event_id in question.get("candidates", ()) if event_id in by_id]
    options: dict[str, str] = {}
    labels: dict[str, str] = {}
    for index, event_id in enumerate(candidates[-MAX_POINTER_OPTIONS:], start=1):
        item = by_id[event_id]
        text = " ".join(str(item.get("text", "")).split())
        label = f"message_{index}"
        options[label] = f"Message {event_id} from {item.get('from')}: {text[:160]}"
        labels[label] = event_id
    return options, labels


def decisions_questions(
    questions: Mapping[str, Mapping[str, Any]],
    state: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    """The core's questions in the Decisions API shape.

    Returns the request's questions and, for each pointer question, the map
    from option label back to message id.
    """

    request: dict[str, Any] = {}
    pointers: dict[str, dict[str, str]] = {}
    for key, question in questions.items():
        kind = question["kind"]
        if kind == "yes_no":
            request[key] = {
                "type": "noul",
                "instructions": question["ask"],
                "criteria": {"true": question["yes"], "false": question["no"]},
            }
        elif kind == "choice":
            request[key] = {
                "type": "choice",
                "instructions": question["ask"],
                "criteria": dict(question["options"]),
            }
        elif kind == "event":
            options, labels = _pointer_options(question, state)
            if not options:
                continue
            pointers[key] = labels
            request[key] = {
                "type": "choice",
                "instructions": question["ask"],
                "criteria": {**options, _NONE: question["no_message"]},
            }
        else:
            raise ValidationError(f"question {key} has an unsupported kind {kind!r}")
    return request, pointers


def _probability(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, number)) if number == number else 0.0


def core_answers(
    answers: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
    pointers: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """The Decisions API answers in the core's shape."""

    result: dict[str, Any] = {}
    for key, question in questions.items():
        answer = answers.get(key) or {}
        kind = question["kind"]
        if kind == "yes_no":
            if "noul" not in answer:
                raise AttentionError(f"typed decision has no answer to {key}")
            result[key] = _probability(answer["noul"])
        elif kind == "choice":
            probabilities = answer.get("probabilities")
            if not isinstance(probabilities, Mapping):
                raise AttentionError(f"typed decision has no answer to {key}")
            result[key] = {option: _probability(probabilities.get(option)) for option in question["options"]}
        else:
            choice = answer.get("choice")
            result[key] = pointers.get(key, {}).get(choice) if isinstance(choice, str) else None
    return result


class DecisionsAttentionModel:
    """The participant's attention, answered by a typed decision model."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        url: str = DEFAULT_URL,
        name: str = "participant-attention",
        provider: str = KIND,
    ) -> None:
        for label, value in (("model", model), ("api_key", api_key), ("url", url), ("name", name), ("provider", provider)):
            if not isinstance(value, str) or not value:
                raise ValidationError(f"typed decision model {label} must be non-empty")
        self.name = name
        self.provider = provider
        self.model_id = model
        self._url = url
        self._api_key = api_key
        # The provider's last full response, for audits and evaluations.
        self.last_response: Mapping[str, Any] | None = None

    @classmethod
    def from_trusted_config(cls, config: Mapping[str, Any]) -> "DecisionsAttentionModel":
        allowed = {"model", "url", "name", "provider", "api_key_env"}
        if not isinstance(config, Mapping) or set(config) - allowed:
            raise ValidationError("typed decision model config has unexpected fields")
        api_key_env = config.get("api_key_env", DEFAULT_API_KEY_ENV)
        if not isinstance(api_key_env, str) or not api_key_env:
            raise ValidationError("typed decision model api_key_env must be non-empty")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValidationError(f"typed decision model credential is absent from {api_key_env}")
        return cls(
            model=config.get("model"),
            api_key=api_key,
            url=config.get("url", DEFAULT_URL),
            name=config.get("name", "participant-attention"),
            provider=config.get("provider", KIND),
        )

    def answer(
        self,
        *,
        questions: Mapping[str, Mapping[str, Any]],
        state: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.last_response = None
        request_questions, pointers = decisions_questions(questions, state)
        body = {"model": self.model_id, "state": dict(state), "questions": request_questions}
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise AttentionError(f"typed decision provider returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, socket.timeout, OSError, json.JSONDecodeError) as exc:
            raise AttentionError("typed decision provider request failed") from exc
        if not isinstance(payload, Mapping) or not isinstance(payload.get("answers"), Mapping):
            raise AttentionError("typed decision response has no answers")
        self.last_response = payload
        return core_answers(payload["answers"], questions, pointers)


# Pass to ``attention_model_from_config(..., host_kinds=ATTENTION_KINDS)``.
ATTENTION_KINDS = {KIND: DecisionsAttentionModel.from_trusted_config}
