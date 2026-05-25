"""Validation helpers for TurnAware admission requests and results."""

from collections.abc import Mapping
from numbers import Real
from typing import Any

from .errors import ValidationError
from .models import (
    AdmissionRequest,
    ContextItem,
    FORBIDDEN_REPLY_FIELDS,
    Trigger,
    VERDICTS,
)


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{name} must be an object")
    return value


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a string when supplied")
    return value


def _optional_mapping(value: Any, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return dict(_require_mapping(value, name))


def _required_non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def validate_request(raw):
    data = _require_mapping(raw, "request")

    trigger_data = _require_mapping(data.get("trigger"), "trigger")
    trigger = Trigger(
        content=_required_non_empty_string(trigger_data.get("content"), "trigger.content"),
        id=_optional_string(trigger_data.get("id"), "trigger.id") or "trigger",
        author=_optional_string(trigger_data.get("author"), "trigger.author"),
        timestamp=_optional_string(trigger_data.get("timestamp"), "trigger.timestamp"),
    )

    raw_context = data.get("context", [])
    if raw_context is None:
        raw_context = []
    if not isinstance(raw_context, list):
        raise ValidationError("context must be a list when supplied")

    context_items: list[ContextItem] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_context, start=1):
        item_data = _require_mapping(item, f"context[{index}]")
        item_id = _optional_string(item_data.get("id"), f"context[{index}].id") or f"context-{index}"
        if not item_id.strip():
            raise ValidationError(f"context[{index}].id must not be empty")
        if item_id in seen_ids:
            raise ValidationError(f"duplicate context id: {item_id}")
        seen_ids.add(item_id)
        context_items.append(
            ContextItem(
                content=_required_non_empty_string(item_data.get("content"), f"context[{index}].content"),
                id=item_id,
                type=_optional_string(item_data.get("type"), f"context[{index}].type"),
                author=_optional_string(item_data.get("author"), f"context[{index}].author"),
                timestamp=_optional_string(item_data.get("timestamp"), f"context[{index}].timestamp"),
            )
        )

    agent = data.get("agent")
    if agent is not None:
        agent = dict(_require_mapping(agent, "agent"))

    surface = data.get("surface")
    if surface is not None:
        surface = dict(_require_mapping(surface, "surface"))

    request_id = _optional_string(data.get("request_id"), "request_id")
    classifier = _optional_string(data.get("classifier"), "classifier")
    if classifier is not None and not classifier.strip():
        raise ValidationError("classifier must not be empty when supplied")
    classifier_config = _optional_mapping(data.get("classifier_config"), "classifier_config")

    return AdmissionRequest(
        trigger=trigger,
        context=tuple(context_items),
        agent=agent,
        surface=surface,
        request_id=request_id,
        classifier=classifier,
        classifier_config=classifier_config,
    )


def validate_result(raw):
    data = _require_mapping(raw, "result")

    forbidden = FORBIDDEN_REPLY_FIELDS.intersection(data)
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise ValidationError(f"result contains forbidden reply fields: {names}")

    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        raise ValidationError("result.verdict must be one of PASS, ACK, ASK, SPEAK")

    classifier = data.get("classifier")
    if not isinstance(classifier, str) or not classifier.strip():
        raise ValidationError("result.classifier must be a non-empty string")

    classifier_provider = data.get("classifier_provider")
    if classifier_provider is not None and (not isinstance(classifier_provider, str) or not classifier_provider.strip()):
        raise ValidationError("result.classifier_provider must be a non-empty string when supplied")

    classifier_model = data.get("classifier_model")
    if classifier_model is not None and (not isinstance(classifier_model, str) or not classifier_model.strip()):
        raise ValidationError("result.classifier_model must be a non-empty string when supplied")

    confidences = _require_mapping(data.get("confidences"), "result.confidences")
    missing = set(VERDICTS).difference(confidences)
    extra = set(confidences).difference(VERDICTS)
    if missing or extra:
        raise ValidationError("result.confidences must contain exactly PASS, ACK, ASK, SPEAK")
    for key in VERDICTS:
        value = confidences[key]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValidationError(f"result.confidences.{key} must be numeric")

    checked = data.get("context_checked")
    if not isinstance(checked, list) or not all(isinstance(item, str) for item in checked):
        raise ValidationError("result.context_checked must be a list of strings")

    reasons = data.get("reasons")
    if (
        not isinstance(reasons, list)
        or not reasons
        or not all(isinstance(item, str) and item.strip() for item in reasons)
    ):
        raise ValidationError("result.reasons must be a non-empty list of strings")

    request_id = data.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise ValidationError("result.request_id must be a string when supplied")

    return raw
