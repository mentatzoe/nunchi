"""Portable Nunchi V2 attention core."""

from .observation import (
    check_actor_reference_integrity,
    check_id_uniqueness,
    check_timestamp_order,
    check_trigger_membership,
    validate_attention_request,
)
from .policy import (
    ClassifierPolicy,
    EffectiveAttentionPolicy,
    RecoverabilityPolicy,
)
import copy
import json
import math
from typing import Any, Callable


class ReceiptSinkPersistenceError(Exception):
    """Typed result from a sink that cannot prove durable persistence."""

    __slots__ = ("_persistence",)

    def __init__(self, persistence: str) -> None:
        if persistence not in ("not-persisted", "unknown"):
            raise ValueError("persistence must be 'not-persisted' or 'unknown'")
        super().__init__("attention receipt persistence failed")
        self._persistence = persistence

    @property
    def persistence(self) -> str:
        return self._persistence


class AttentionConfigurationError(ValueError):
    pass


class AttentionBudgetError(ValueError):
    pass


class AttentionClassifierOutputError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def classifier_projection(request: dict[str, Any]) -> dict[str, Any]:
    """Build the classifier-safe I-010A projection without host authority."""
    projection = copy.deepcopy(request)
    continuation = projection.pop("continuation", None)
    if continuation is None:
        available = {"before": False, "after": False, "around_event": False}
    else:
        available = {
            "before": continuation["can_fetch_before"],
            "after": continuation["can_fetch_after"],
            "around_event": continuation["can_fetch_around_event"],
        }
    projection["expansion_available"] = available
    return projection


def _request_errors(request: Any) -> list[str]:
    errors = validate_attention_request(request)
    if errors or not isinstance(request, dict):
        return errors
    errors.extend(check_id_uniqueness(request.get("events") or []))
    errors.extend(check_timestamp_order(request.get("events") or []))
    errors.extend(check_trigger_membership(request))
    errors.extend(check_actor_reference_integrity(request))
    return errors


def _validate_trusted_inputs(
    request: dict[str, Any],
    policy: Any,
    recoverability: Any,
    classifier_config: Any,
    receipt_sink: Any,
) -> tuple[
    EffectiveAttentionPolicy,
    RecoverabilityPolicy,
    ClassifierPolicy,
    Callable[[dict[str, Any]], None],
]:
    if not isinstance(policy, EffectiveAttentionPolicy):
        raise AttentionConfigurationError("attention policy is invalid")
    if not isinstance(recoverability, RecoverabilityPolicy):
        raise AttentionConfigurationError("recoverability policy is invalid")
    if not isinstance(classifier_config, ClassifierPolicy):
        raise AttentionConfigurationError("classifier policy is invalid")
    if not callable(receipt_sink):
        raise AttentionConfigurationError("receipt sink is unavailable")
    participant_id = request["self"]["participant_id"]
    continuity_scope_id = request["room"]["continuity_scope_id"]
    if (
        policy.participant_id != participant_id
        or recoverability.participant_id != participant_id
        or recoverability.continuity_scope_id != continuity_scope_id
    ):
        raise AttentionConfigurationError("trusted policy binding does not match request")
    return policy, recoverability, classifier_config, receipt_sink


def _enforce_attention_budget(
    request: dict[str, Any],
    projection: dict[str, Any],
    policy: EffectiveAttentionPolicy,
) -> None:
    if len(request["events"]) > policy.attention_max_events:
        raise AttentionBudgetError("attention budget exceeded")
    if len(_canonical_bytes(projection)) > policy.attention_max_bytes:
        raise AttentionBudgetError("attention budget exceeded")
    coverage = request["coverage"]
    if coverage.get("max_events", policy.attention_max_events) > policy.attention_max_events:
        raise AttentionBudgetError("attention budget exceeded")
    if coverage.get("max_bytes", policy.attention_max_bytes) > policy.attention_max_bytes:
        raise AttentionBudgetError("attention budget exceeded")


def _non_empty_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _validate_confidences(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {"PASS", "ACK", "ASK", "SPEAK"}:
        raise AttentionClassifierOutputError("legacy confidence vector is invalid")
    result: dict[str, float] = {}
    for name, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise AttentionClassifierOutputError("legacy confidence vector is invalid")
        number = float(raw)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise AttentionClassifierOutputError("legacy confidence vector is invalid")
        result[name] = number
    return result


def _validate_classifier_judgment(
    value: Any,
    *,
    request: dict[str, Any],
    margin_active: bool,
) -> dict[str, Any]:
    required = {"disposition", "reasons", "evidence_event_ids"}
    optional = {"legacy_verdict_confidences", "attention_advice"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise AttentionClassifierOutputError("classifier output is malformed")
    disposition = value.get("disposition")
    if disposition not in ("SUPPRESS", "WAKE", "DEFER"):
        raise AttentionClassifierOutputError("classifier disposition is invalid")
    if not _non_empty_strings(value.get("reasons")):
        raise AttentionClassifierOutputError("classifier reasons are invalid")
    if not _non_empty_strings(value.get("evidence_event_ids")):
        raise AttentionClassifierOutputError("classifier evidence is invalid")
    known_event_ids = {event["id"] for event in request["events"]}
    if not set(value["evidence_event_ids"]) <= known_event_ids:
        raise AttentionClassifierOutputError("classifier evidence is not grounded")
    result = {
        "disposition": disposition,
        "reasons": copy.deepcopy(value["reasons"]),
        "evidence_event_ids": copy.deepcopy(value["evidence_event_ids"]),
    }
    if "legacy_verdict_confidences" in value:
        result["legacy_verdict_confidences"] = _validate_confidences(
            value["legacy_verdict_confidences"]
        )
    elif disposition == "SUPPRESS" and margin_active:
        raise AttentionClassifierOutputError("candidate suppression requires confidence evidence")
    if "attention_advice" in value:
        advice = value["attention_advice"]
        if disposition != "WAKE" or not isinstance(advice, list):
            raise AttentionClassifierOutputError("attention advice is invalid")
        parsed_advice = []
        for item in advice:
            if not isinstance(item, dict) or set(item) != {"note", "evidence_event_ids"}:
                raise AttentionClassifierOutputError("attention advice is invalid")
            if not isinstance(item["note"], str) or not item["note"]:
                raise AttentionClassifierOutputError("attention advice is invalid")
            if not _non_empty_strings(item["evidence_event_ids"]):
                raise AttentionClassifierOutputError("attention advice is invalid")
            if not set(item["evidence_event_ids"]) <= known_event_ids:
                raise AttentionClassifierOutputError("attention advice is not grounded")
            parsed_advice.append(copy.deepcopy(item))
        result["attention_advice"] = parsed_advice
    return result


def route_attention_judgment(
    judgment: dict[str, Any],
    *,
    policy: EffectiveAttentionPolicy,
    recoverability: RecoverabilityPolicy,
) -> tuple[str, dict[str, Any]]:
    """Apply only the protective, one-way widening valves."""
    disposition = judgment["disposition"]
    margin_active = policy.transition_defer_margin is not None
    margin_status = "active" if margin_active else "retired"
    if disposition == "WAKE":
        return "WAKE", {
            "valve": "none",
            "override_cause": "none",
            "margin_status": margin_status,
        }
    if disposition == "DEFER":
        return "DEFER", {
            "valve": "classifier-defer",
            "override_cause": "none",
            "margin_status": margin_status,
        }
    if not policy.social_suppression_enabled:
        return "DEFER", {
            "valve": "policy-defer",
            "override_cause": "suppression-disabled",
            "margin_status": margin_status,
        }
    if not recoverability.eligible:
        return "DEFER", {
            "valve": "policy-defer",
            "override_cause": "recoverability-unproven",
            "margin_status": margin_status,
        }
    if margin_active:
        confidences = judgment["legacy_verdict_confidences"]
        gap = confidences["PASS"] - max(
            confidences["ACK"],
            confidences["ASK"],
            confidences["SPEAK"],
        )
        if gap <= policy.transition_defer_margin:
            routing = {
                "valve": "margin-defer",
                "override_cause": "margin",
                "margin_status": "active",
                "effective_margin": policy.transition_defer_margin,
            }
            if policy.transition_defer_margin_source is not None:
                routing["margin_source"] = policy.transition_defer_margin_source
            return "DEFER", routing
    return "SUPPRESS", {
        "valve": "none",
        "override_cause": "none",
        "margin_status": margin_status,
    }


def _classifier_audit(config: ClassifierPolicy) -> dict[str, str]:
    return {
        "name": "participant-shaped-v2",
        "provider": config.provider,
        "model": config.model,
    }


def _receipt(request_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "stage": "attention",
        "writer": "attention-engine",
        "body": copy.deepcopy(body),
    }


def _offer_receipt(
    sink: Callable[[dict[str, Any]], None],
    record: dict[str, Any],
) -> str:
    try:
        returned = sink(copy.deepcopy(record))
    except BaseException:
        raise
    if returned is not None:
        raise ReceiptSinkPersistenceError("unknown")
    return "persisted"


def _error_result(
    *,
    code: str,
    detail: str,
    request_id: str | None,
    classifier_audit: dict[str, str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "error",
        "error": {"code": code, "detail": detail},
    }
    if request_id:
        result["request_id"] = request_id
    if classifier_audit is not None:
        result["classifier"] = copy.deepcopy(classifier_audit)
    return result


def evaluate_v2(
    request: Any,
    *,
    policy: Any,
    recoverability: Any,
    classifier_config: Any,
    receipt_sink: Any,
    classifier_transport: Callable[[dict[str, Any], ClassifierPolicy], Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one I-010A request into one I-010B@2 decision.

    ``classifier_transport`` is an injectable transport seam; production hosts
    omit it and use :func:`nunchi.classifiers.classify_attention_v2`.
    """
    try:
        accepted = copy.deepcopy(request)
    except Exception:
        return _error_result(
            code="invalid-request",
            detail="attention request failed validation",
            request_id=None,
        )
    request_id = accepted.get("request_id") if isinstance(accepted, dict) else None
    request_id = request_id if isinstance(request_id, str) and request_id else None
    errors = _request_errors(accepted)
    if errors:
        return _error_result(
            code="invalid-request",
            detail="attention request failed validation",
            request_id=request_id,
        )
    try:
        policy, recoverability, classifier_config, sink = _validate_trusted_inputs(
            accepted,
            policy,
            recoverability,
            classifier_config,
            receipt_sink,
        )
    except AttentionConfigurationError:
        return _error_result(
            code="configuration-error",
            detail="trusted attention configuration is invalid",
            request_id=request_id,
        )

    projection = classifier_projection(accepted)
    try:
        _enforce_attention_budget(accepted, projection, policy)
    except AttentionBudgetError:
        result = _error_result(
            code="attention-budget-error",
            detail="attention budget exceeded",
            request_id=request_id,
        )
        body: dict[str, Any] = copy.deepcopy(result["error"])
        receipt_body: dict[str, Any] = {"error": body}
        if policy.error_action == "NO_WAKE":
            receipt_body.update(
                {"wake_action": "NO_WAKE", "policy_provenance": policy.source}
            )
        try:
            _offer_receipt(sink, _receipt(request_id, receipt_body))
        except Exception:
            return _error_result(
                code="receipt-sink-failure",
                detail="attention receipt persistence is unknown",
                request_id=request_id,
            )
        return result

    if not policy.preattention_enabled:
        result = {
            "status": "bypass",
            "request_id": request_id,
            "cause": "preattention-disabled",
        }
        receipt_body = {
            "classifier_not_invoked": True,
            "cause": "preattention-disabled",
            "policy_provenance": policy.source,
        }
        try:
            _offer_receipt(sink, _receipt(request_id, receipt_body))
        except Exception:
            return _error_result(
                code="receipt-sink-failure",
                detail="attention receipt persistence is unknown",
                request_id=request_id,
            )
        return result

    if classifier_transport is None:
        from .classifiers import classify_attention_v2

        classifier_transport = classify_attention_v2
    audit = _classifier_audit(classifier_config)
    try:
        raw = classifier_transport(copy.deepcopy(projection), classifier_config)
        judgment = _validate_classifier_judgment(
            raw,
            request=accepted,
            margin_active=policy.transition_defer_margin is not None,
        )
        effective, routing = route_attention_judgment(
            judgment,
            policy=policy,
            recoverability=recoverability,
        )
    except TimeoutError:
        error = ("provider-timeout", "attention provider timed out")
    except AttentionClassifierOutputError:
        error = ("malformed-model-output", "attention provider output was invalid")
    except Exception:
        error = ("provider-error", "attention provider failed")
    else:
        result = {
            "status": "ok",
            "request_id": request_id,
            "classifier_disposition": judgment["disposition"],
            "effective_disposition": effective,
            "routing_audit": routing,
            "reasons": copy.deepcopy(judgment["reasons"]),
            "evidence_event_ids": copy.deepcopy(judgment["evidence_event_ids"]),
            "classifier": audit,
        }
        if "legacy_verdict_confidences" in judgment:
            result["legacy_verdict_confidences"] = copy.deepcopy(
                judgment["legacy_verdict_confidences"]
            )
        if "attention_advice" in judgment:
            result["attention_advice"] = copy.deepcopy(judgment["attention_advice"])
        receipt_body = {
            "classifier_disposition": judgment["disposition"],
            "effective_disposition": effective,
            "classifier": audit,
            "evidence_event_ids": copy.deepcopy(judgment["evidence_event_ids"]),
            "routing_audit": copy.deepcopy(routing),
            "policy_provenance": policy.source,
        }
        try:
            _offer_receipt(sink, _receipt(request_id, receipt_body))
        except Exception:
            return _error_result(
                code="receipt-sink-failure",
                detail="attention receipt persistence is unknown",
                request_id=request_id,
                classifier_audit=audit,
            )
        return result

    result = _error_result(
        code=error[0],
        detail=error[1],
        request_id=request_id,
        classifier_audit=audit,
    )
    receipt_body = {"error": copy.deepcopy(result["error"])}
    if policy.error_action == "NO_WAKE":
        receipt_body.update(
            {"wake_action": "NO_WAKE", "policy_provenance": policy.source}
        )
    try:
        _offer_receipt(sink, _receipt(request_id, receipt_body))
    except Exception:
        return _error_result(
            code="receipt-sink-failure",
            detail="attention receipt persistence is unknown",
            request_id=request_id,
            classifier_audit=audit,
        )
    return result


__all__ = [
    "AttentionBudgetError",
    "AttentionClassifierOutputError",
    "AttentionConfigurationError",
    "ReceiptSinkPersistenceError",
    "classifier_projection",
    "evaluate",
    "evaluate_v2",
    "route_attention_judgment",
]
