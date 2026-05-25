"""Admission request and result model helpers."""

from dataclasses import dataclass, field
from typing import Any

VERDICTS = ("PASS", "ACK", "ASK", "SPEAK")
FORBIDDEN_REPLY_FIELDS = {"message", "reply", "draft", "content"}


@dataclass(frozen=True)
class Trigger:
    content: str
    id: str = "trigger"
    author: str | None = None
    timestamp: str | None = None

    @property
    def reference(self) -> str:
        return f"trigger:{self.id}"


@dataclass(frozen=True)
class ContextItem:
    content: str
    id: str
    type: str | None = None
    author: str | None = None
    timestamp: str | None = None

    @property
    def reference(self) -> str:
        return f"context:{self.id}"


@dataclass(frozen=True)
class AdmissionRequest:
    trigger: Trigger
    context: tuple[ContextItem, ...] = field(default_factory=tuple)
    agent: dict[str, Any] | None = None
    surface: dict[str, Any] | None = None
    request_id: str | None = None
    classifier: str | None = None
    classifier_config: dict[str, Any] | None = None

    @property
    def allowed_context_references(self) -> set[str]:
        return {self.trigger.reference, *(item.reference for item in self.context)}


@dataclass(frozen=True)
class AdmissionResult:
    classifier: str
    verdict: str
    confidences: dict[str, float]
    context_checked: tuple[str, ...]
    reasons: tuple[str, ...]
    request_id: str | None = None
    classifier_provider: str | None = None
    classifier_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "classifier": self.classifier,
            "verdict": self.verdict,
            "confidences": dict(self.confidences),
            "context_checked": list(self.context_checked),
            "reasons": list(self.reasons),
        }
        if self.request_id is not None:
            payload["request_id"] = self.request_id
        if self.classifier_provider is not None:
            payload["classifier_provider"] = self.classifier_provider
        if self.classifier_model is not None:
            payload["classifier_model"] = self.classifier_model
        return payload


def result_to_dict(result):
    if isinstance(result, AdmissionResult):
        payload = result.to_dict()
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        raise TypeError("result must be an AdmissionResult or dict")

    forbidden = FORBIDDEN_REPLY_FIELDS.intersection(payload)
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise ValueError(f"admission results must not contain reply fields: {names}")
    return payload
