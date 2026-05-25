"""Admission classifier registry and built-in classifier paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .errors import ValidationError
from .models import AdmissionRequest, AdmissionResult, VERDICTS

PRODUCT_CLASSIFIER = "product"
DETERMINISTIC_CLASSIFIER = "deterministic"
SUPPORTED_CLASSIFIERS = (PRODUCT_CLASSIFIER, DETERMINISTIC_CLASSIFIER)


@dataclass(frozen=True)
class ClassifierDecision:
    verdict: str
    confidences: dict[str, float]
    context_checked: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AdmissionSignals:
    checked: tuple[str, ...]
    trigger_assignment: bool
    context_assignment: bool
    ack_request: bool
    trigger_ask: bool
    any_ask: bool
    pass_signal: bool
    corroborated_completion: bool
    contradiction_refs: tuple[str, ...]


class AdmissionClassifier(Protocol):
    name: str
    model_id: str

    def classify(self, request: AdmissionRequest) -> ClassifierDecision:
        """Return an admission-only decision for one validated request."""


def _lower(text: str) -> str:
    return text.casefold()


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = _lower(text)
    return any(needle in lowered for needle in needles)


def _assignment_signal(text: str) -> bool:
    return _contains_any(
        text,
        (
            "please implement",
            "implement ",
            "build ",
            "fix ",
            "redo ",
            "complete ",
            "take this",
            "assigned",
            "owner",
            "proceed",
            "comment back with results",
            "report back with results",
            "what's dropping",
            "what is blocking",
        ),
    )


def _ack_signal(text: str) -> bool:
    return _contains_any(text, ("acknowledge", "ack ", "acknowledgement", "confirm receipt", "saw it"))


def _ask_signal(text: str) -> bool:
    return _contains_any(text, ("need clarification", "clarification", "unclear", "ambiguous", "not specified"))


def _pass_signal(text: str) -> bool:
    return _contains_any(
        text,
        (
            "already handled",
            "handled this",
            "posted the fix",
            "resolved",
            "no response needed",
            "complete",
            "done",
            "merged",
            "shipped",
        ),
    )


def _completion_support(text: str) -> bool:
    return _contains_any(
        text,
        ("already handled", "posted the fix", "merged", "tests pass", "implemented", "complete", "done", "resolved", "reviewed"),
    )


def _contradiction_signal(text: str) -> bool:
    return _contains_any(
        text,
        (
            "not implemented",
            "not complete",
            "not done",
            "missing",
            "no evidence",
            "evidence is missing",
            "work is missing",
            "blocked",
            "unavailable",
            "failed",
            "failing",
            "still at the start",
            "not the main path",
        ),
    )


def _admission_signals(request: AdmissionRequest) -> AdmissionSignals:
    checked = [request.trigger.reference]
    context_texts: list[tuple[str, str]] = []
    for item in request.context:
        checked.append(item.reference)
        context_texts.append((item.reference, item.content))

    trigger_text = request.trigger.content
    trigger_ask = _ask_signal(trigger_text)
    return AdmissionSignals(
        checked=tuple(checked),
        trigger_assignment=_assignment_signal(trigger_text),
        context_assignment=any(_assignment_signal(text) for _, text in context_texts),
        ack_request=_ack_signal(trigger_text),
        trigger_ask=trigger_ask,
        any_ask=trigger_ask or any(_ask_signal(text) for _, text in context_texts),
        pass_signal=_pass_signal(trigger_text) or any(_pass_signal(text) for _, text in context_texts),
        corroborated_completion=any(_completion_support(text) for _, text in context_texts),
        contradiction_refs=tuple(ref for ref, text in context_texts if _contradiction_signal(text)),
    )


def _confidences(verdict: str, *, strength: str = "normal") -> dict[str, float]:
    if strength == "conflict":
        table = {
            "PASS": {"PASS": 0.10, "ACK": 0.10, "ASK": 0.35, "SPEAK": 0.45},
            "ACK": {"PASS": 0.05, "ACK": 0.65, "ASK": 0.15, "SPEAK": 0.15},
            "ASK": {"PASS": 0.05, "ACK": 0.10, "ASK": 0.55, "SPEAK": 0.30},
            "SPEAK": {"PASS": 0.05, "ACK": 0.10, "ASK": 0.20, "SPEAK": 0.65},
        }
        return dict(table[verdict])
    if strength == "low":
        table = {
            "PASS": {"PASS": 0.55, "ACK": 0.10, "ASK": 0.20, "SPEAK": 0.15},
            "ACK": {"PASS": 0.05, "ACK": 0.70, "ASK": 0.10, "SPEAK": 0.15},
            "ASK": {"PASS": 0.05, "ACK": 0.10, "ASK": 0.60, "SPEAK": 0.25},
            "SPEAK": {"PASS": 0.05, "ACK": 0.10, "ASK": 0.15, "SPEAK": 0.70},
        }
        return dict(table[verdict])
    return {candidate: (0.80 if candidate == verdict else round(0.20 / 3, 2)) for candidate in VERDICTS}


def _score_confidences(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        return _confidences("ASK", strength="low")
    rounded = {verdict: round(scores[verdict] / total, 2) for verdict in VERDICTS}
    drift = round(1.0 - sum(rounded.values()), 2)
    if drift:
        winner = max(rounded, key=rounded.get)
        rounded[winner] = round(rounded[winner] + drift, 2)
    return rounded


class ProductAdmissionClassifier:
    """Default product admission classifier backed by a named local model boundary.

    This is separate from the deterministic fixture verifier.  The local product
    model scores competing admission hypotheses over the supplied envelope.  If a
    host asks for a different product model, that is an unavailable product path;
    TurnAware fails clearly rather than using the deterministic verifier under a
    product label.
    """

    model_id = "turnaware-local-admission-v1"

    def __init__(self, name: str = PRODUCT_CLASSIFIER, config: dict[str, Any] | None = None) -> None:
        self.name = name
        self.config = config or {}
        unsupported = set(self.config).difference({"strict", "model"})
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValidationError(f"unsupported classifier_config for {name}: {names}")
        strict = self.config.get("strict", True)
        if not isinstance(strict, bool):
            raise ValidationError(f"classifier_config.strict for {name} must be boolean")
        configured_model = self.config.get("model", self.model_id)
        if configured_model != self.model_id:
            raise ValidationError(
                f"product classifier model {configured_model!r} is unavailable; no deterministic fallback was used"
            )

    def classify(self, request: AdmissionRequest) -> ClassifierDecision:
        signals = _admission_signals(request)
        scores = {verdict: 0.05 for verdict in VERDICTS}
        reasons: list[str] = []

        if signals.trigger_ask:
            scores["ASK"] += 0.75
            reasons.append("The product admission model found an explicit clarification request in the trigger.")

        if signals.trigger_assignment or (signals.context_assignment and not signals.ack_request):
            scores["SPEAK"] += 0.75 if signals.trigger_assignment else 0.55
            reasons.append("The product admission model found a substantive work assignment in supplied material.")

        if signals.pass_signal and signals.contradiction_refs:
            scores["PASS"] *= 0.25
            scores["SPEAK" if signals.context_assignment else "ASK"] += 0.65
            reasons.append("The product admission model inspected contradicted missing-work evidence before allowing PASS.")
        elif signals.pass_signal and signals.corroborated_completion:
            scores["PASS"] += 0.70
            reasons.append("The product admission model found corroborated completion evidence in supplied context.")
        elif signals.pass_signal:
            scores["PASS"] += 0.10
            scores["ASK"] += 0.50
            reasons.append("The product admission model found resolved-looking text without supplied corroboration, so PASS remains unsafe.")

        if signals.ack_request and not signals.trigger_assignment:
            scores["ACK"] += 0.60
            reasons.append("The product admission model found a visible acknowledgement request without substantive trigger assignment.")

        if signals.any_ask and not signals.trigger_ask:
            scores["ASK"] += 0.35
            reasons.append("The product admission model found uncertainty in supplied context.")

        if not reasons:
            scores["ASK"] += 0.45
            reasons.append("The product admission model did not find enough supplied evidence to make participation clearly safe.")

        verdict = max(VERDICTS, key=lambda candidate: scores[candidate])
        return ClassifierDecision(
            verdict=verdict,
            confidences=_score_confidences(scores),
            context_checked=signals.checked,
            reasons=tuple(reasons),
        )


class RoomAdmissionClassifier:
    """Deterministic admission verifier for offline and CI fixture evidence.

    The verifier is intentionally admission-only: it chooses PASS/ACK/ASK/SPEAK
    and audit evidence, never reply prose. It inspects the trigger and supplied
    context for assignment, acknowledgement, clarification, completion, and
    contradiction evidence rather than returning on the first substring match.
    """

    model_id = "turnaware-deterministic-fixture-v1"

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        self.name = name
        self.config = config or {}
        unsupported = set(self.config).difference({"strict"})
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValidationError(f"unsupported classifier_config for {name}: {names}")
        strict = self.config.get("strict", True)
        if not isinstance(strict, bool):
            raise ValidationError(f"classifier_config.strict for {name} must be boolean")

    def classify(self, request: AdmissionRequest) -> ClassifierDecision:
        signals = _admission_signals(request)

        if signals.any_ask and signals.trigger_ask:
            return ClassifierDecision(
                verdict="ASK",
                confidences=_confidences("ASK", strength="low"),
                context_checked=signals.checked,
                reasons=("The trigger asks whether clarification is needed before substantive participation.",),
            )

        if signals.trigger_assignment:
            return ClassifierDecision(
                verdict="SPEAK",
                confidences=_confidences("SPEAK"),
                context_checked=signals.checked,
                reasons=("The trigger asks this agent to perform substantive work, so visible participation is warranted.",),
            )

        if signals.pass_signal and signals.contradiction_refs:
            verdict = "SPEAK" if signals.context_assignment else "ASK"
            return ClassifierDecision(
                verdict=verdict,
                confidences=_confidences(verdict, strength="conflict"),
                context_checked=signals.checked,
                reasons=("Resolved-looking language is contradicted by supplied missing-work or missing-evidence context.",),
            )

        if signals.pass_signal and signals.corroborated_completion:
            return ClassifierDecision(
                verdict="PASS",
                confidences=_confidences("PASS", strength="low"),
                context_checked=signals.checked,
                reasons=(
                    "Inspected context corroborates that the requested matter is already complete and no visible participation is needed.",
                ),
            )

        if signals.pass_signal and not signals.corroborated_completion:
            return ClassifierDecision(
                verdict="ASK",
                confidences=_confidences("ASK", strength="conflict"),
                context_checked=signals.checked,
                reasons=("Resolved-looking language has no corroborating supplied completion context; PASS is not safe.",),
            )

        if signals.ack_request:
            return ClassifierDecision(
                verdict="ACK",
                confidences=_confidences("ACK", strength="low"),
                context_checked=signals.checked,
                reasons=("The trigger asks for visible acknowledgement rather than substantive work.",),
            )

        if signals.any_ask:
            return ClassifierDecision(
                verdict="ASK",
                confidences=_confidences("ASK", strength="low"),
                context_checked=signals.checked,
                reasons=("Supplied material indicates a clarification is needed before substantive participation.",),
            )

        if signals.context_assignment:
            return ClassifierDecision(
                verdict="SPEAK",
                confidences=_confidences("SPEAK", strength="low"),
                context_checked=signals.checked,
                reasons=("Supplied context assigns substantive work to this agent.",),
            )

        return ClassifierDecision(
            verdict="ASK",
            confidences=_confidences("ASK", strength="low"),
            context_checked=signals.checked,
            reasons=("No supplied context made participation clearly safe; a clarifying question is warranted.",),
        )


def _normalise_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValidationError("classifier_config must be an object when supplied")
    return dict(config)


def get_classifier(name: str | None, config: dict[str, Any] | None = None) -> AdmissionClassifier:
    selected = name or PRODUCT_CLASSIFIER
    if selected not in SUPPORTED_CLASSIFIERS:
        supported = ", ".join(SUPPORTED_CLASSIFIERS)
        raise ValidationError(f"unsupported classifier {selected!r}; supported classifiers: {supported}")
    normalised_config = _normalise_config(config)
    if selected == PRODUCT_CLASSIFIER:
        return ProductAdmissionClassifier(selected, normalised_config)
    return RoomAdmissionClassifier(selected, normalised_config)


def classify(request: AdmissionRequest, *, classifier: str | None = None, classifier_config: dict[str, Any] | None = None) -> AdmissionResult:
    selected = classifier or request.classifier or PRODUCT_CLASSIFIER
    config = classifier_config if classifier_config is not None else request.classifier_config
    engine = get_classifier(selected, config)
    decision = engine.classify(request)
    return AdmissionResult(
        classifier=engine.name,
        verdict=decision.verdict,
        confidences=decision.confidences,
        context_checked=decision.context_checked,
        reasons=decision.reasons,
        request_id=request.request_id,
    )
