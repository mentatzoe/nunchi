"""Deterministic provenance-bound authorization for privileged V2 effects.

The participant proposes an action, capability, scope, and exact origin event.
It never supplies the requester.  The guard resolves that event from a trusted
I-010A observation, derives its transport actor, reloads strict operator policy,
and returns I-010F ``ALLOW``, ``DENY``, or ``APPROVAL_REQUIRED``.

An allow is short-lived, one-use, and rechecked against the exact operation,
origin, requester, grant, scope, expiry, revocation, and approval immediately
before execution.  The decision is consumed before dispatch, giving at-most-
once authorization even when the privileged executor fails.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .observation import (
    check_actor_reference_integrity,
    check_id_uniqueness,
    check_trigger_membership,
    validate_attention_request,
)
from .policy import CapabilityGrant, IMPACTS, OperatorPolicy, PolicyLoadError


_ACTION_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
_UTC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z$"
)
_REQUEST_FIELDS = (
    "kind",
    "schema_version",
    "action_id",
    "action_digest",
    "origin_event_id",
    "capability",
    "scope",
    "impact",
)


class AuthorizationRequestError(ValueError):
    """The proposed I-010F request is malformed and cannot be authorized."""


class AuthorizationContextError(ValueError):
    """The supplied observation is not valid trusted authorization context."""


class AuthorizationExecutionDenied(PermissionError):
    """A previously issued allow cannot authorize this execution attempt."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass
class _ChallengeState:
    decision: dict[str, Any]
    request: dict[str, Any]
    requester_actor_id: str
    grant_id: str
    expires_at: datetime
    satisfied: bool = False


@dataclass
class _AllowState:
    decision: dict[str, Any]
    request: dict[str, Any]
    requester_actor_id: str
    grant_id: str
    expires_at: datetime
    approver_actor_id: str | None = None
    consumed: bool = False


def _canonical_json(value: Any) -> bytes:
    def reject_non_finite(item: Any) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise AuthorizationRequestError("operation is not canonical JSON")
        if isinstance(item, list):
            for child in item:
                reject_non_finite(child)
        elif isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise AuthorizationRequestError("operation object keys must be strings")
            for child in item.values():
                reject_non_finite(child)

    reject_non_finite(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuthorizationRequestError("operation is not canonical JSON") from exc


def canonical_action_digest(operation: Any) -> str:
    """Return the I-010F digest of the exact canonical JSON operation."""
    return "sha256:" + hashlib.sha256(_canonical_json(operation)).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return an aware datetime")
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise AuthorizationRequestError("approval timestamp is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationRequestError("approval timestamp is invalid") from exc


def _opaque(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise AuthorizationRequestError("authorization ID is invalid")
    return value


def _validate_scope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuthorizationRequestError("authorization scope is invalid")
    if set(value) != {"platform", "room_id", "participant_id", "resource"}:
        raise AuthorizationRequestError("authorization scope is invalid")
    resource = value.get("resource")
    if not isinstance(resource, dict) or set(resource) != {"kind", "id"}:
        raise AuthorizationRequestError("authorization scope is invalid")
    platform = value["platform"]
    kind = resource["kind"]
    if not isinstance(platform, str) or not platform:
        raise AuthorizationRequestError("authorization scope is invalid")
    if not isinstance(kind, str) or not kind:
        raise AuthorizationRequestError("authorization scope is invalid")
    _opaque(value["room_id"])
    _opaque(value["participant_id"])
    _opaque(resource["id"])
    return copy.deepcopy(value)


def validate_authorization_request(value: Any) -> dict[str, Any]:
    """Validate and privately copy the I-010F host request branch."""
    if not isinstance(value, dict) or set(value) != set(_REQUEST_FIELDS):
        raise AuthorizationRequestError("authorization request is invalid")
    if value.get("kind") != "authorization-request" or value.get("schema_version") != 2:
        raise AuthorizationRequestError("authorization request is invalid")
    action_id = _opaque(value.get("action_id"))
    origin_event_id = _opaque(value.get("origin_event_id"))
    digest = value.get("action_digest")
    if not isinstance(digest, str) or _ACTION_DIGEST_RE.fullmatch(digest) is None:
        raise AuthorizationRequestError("action digest is invalid")
    capability = value.get("capability")
    if not isinstance(capability, str) or _CAPABILITY_RE.fullmatch(capability) is None:
        raise AuthorizationRequestError("capability is invalid")
    impact = value.get("impact")
    if impact not in IMPACTS:
        raise AuthorizationRequestError("impact is invalid")
    return {
        "kind": "authorization-request",
        "schema_version": 2,
        "action_id": action_id,
        "action_digest": digest,
        "origin_event_id": origin_event_id,
        "capability": capability,
        "scope": _validate_scope(value.get("scope")),
        "impact": impact,
    }


def _validate_observation(value: Any) -> dict[str, Any]:
    try:
        observation = copy.deepcopy(value)
    except Exception as exc:
        raise AuthorizationContextError("authorization observation is invalid") from exc
    errors = validate_attention_request(observation)
    errors.extend(check_id_uniqueness(observation.get("events") or []))
    errors.extend(check_trigger_membership(observation))
    errors.extend(check_actor_reference_integrity(observation))
    if errors:
        raise AuthorizationContextError("authorization observation is invalid")
    return observation


def _resolve_requester(
    request: dict[str, Any], observation: dict[str, Any]
) -> tuple[str | None, str | None]:
    scope = request["scope"]
    room = observation["room"]
    if (
        room["platform"] != scope["platform"]
        or room["id"] != scope["room_id"]
        or observation["self"]["participant_id"] != scope["participant_id"]
    ):
        return None, "deny-origin-scope-mismatch"
    matching = [
        event
        for event in observation["events"]
        if event.get("id") == request["origin_event_id"]
    ]
    if not matching:
        return None, "deny-origin-not-found"
    if len(matching) != 1:
        return None, "deny-origin-not-found"
    event = matching[0]
    if event.get("type") in ("message", "reaction"):
        actor_id = event.get("author_id")
    elif event.get("type") == "membership":
        actor_id = event.get("caused_by_actor_id")
    else:
        actor_id = None
    if not isinstance(actor_id, str) or not actor_id:
        return None, "deny-requester-unknown"
    if actor_id not in observation["actors"]:
        return None, "deny-requester-unknown"
    return actor_id, None


def _approval(value: Any) -> dict[str, Any]:
    fields = {
        "challenge_id",
        "attestation_id",
        "approver_actor_id",
        "approved_at",
        "channel",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise AuthorizationRequestError("approval attestation is invalid")
    channel = value.get("channel")
    if channel not in ("authenticated-transport", "local-operator"):
        raise AuthorizationRequestError("approval attestation is invalid")
    return {
        "challenge_id": _opaque(value.get("challenge_id")),
        "attestation_id": _opaque(value.get("attestation_id")),
        "approver_actor_id": _opaque(value.get("approver_actor_id")),
        "approved_at": _timestamp(_parse_timestamp(value.get("approved_at"))),
        "channel": channel,
    }


def participant_authorization_result(decision: dict[str, Any]) -> dict[str, Any]:
    """Return the closed non-secret participant projection of one decision."""
    return {
        "kind": "participant-result",
        "schema_version": 2,
        "decision_id": decision["decision_id"],
        "action_id": decision["action_id"],
        "action_digest": decision["action_digest"],
        "origin_event_id": decision["origin_event_id"],
        "capability": decision["capability"],
        "scope": copy.deepcopy(decision["scope"]),
        "decision": decision["decision"],
        "reason_code": decision["reason_code"],
    }


class PrivilegedActionGuard:
    """Thread-safe I-040B reference guard over one reloadable operator policy."""

    def __init__(
        self,
        policy_loader: Callable[[], OperatorPolicy],
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
        max_state_entries: int = 4096,
        max_audit_records: int = 8192,
    ) -> None:
        if (
            isinstance(max_state_entries, bool)
            or not isinstance(max_state_entries, int)
            or not 1 <= max_state_entries <= 100000
            or isinstance(max_audit_records, bool)
            or not isinstance(max_audit_records, int)
            or not 1 <= max_audit_records <= 200000
        ):
            raise ValueError("authorization state limits are invalid")
        self._policy_loader = policy_loader
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")
        self._max_state_entries = max_state_entries
        self._lock = threading.RLock()
        self._action_bindings: dict[str, bytes] = {}
        self._challenges: dict[str, _ChallengeState] = {}
        self._allows: dict[str, _AllowState] = {}
        self._used_attestations: set[str] = set()
        self._audits: deque[dict[str, Any]] = deque(maxlen=max_audit_records)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authorization clock must return an aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _binding_bytes(request: dict[str, Any]) -> bytes:
        return _canonical_json(request)

    def _policy(self) -> OperatorPolicy:
        policy = self._policy_loader()
        if not isinstance(policy, OperatorPolicy) or policy.schema_version != 2:
            raise PolicyLoadError("policy-invalid")
        return policy

    @staticmethod
    def _candidate_grants(
        policy: OperatorPolicy,
        request: dict[str, Any],
        requester: str,
    ) -> tuple[list[CapabilityGrant], list[CapabilityGrant]]:
        actor_capability = [
            grant
            for grant in policy.authorization.grants
            if grant.actor_id == requester and grant.capability == request["capability"]
        ]
        exact = [
            grant
            for grant in actor_capability
            if grant.impact == request["impact"] and grant.scope.matches(request["scope"])
        ]
        return actor_capability, exact

    def _decision(
        self,
        request: dict[str, Any],
        *,
        policy_provenance: str,
        decision: str,
        reason_code: str,
        requester: str | None,
        impact: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": "authorization-decision",
            "schema_version": 2,
            "decision_id": self._id_factory("decision"),
            "action_id": request["action_id"],
            "action_digest": request["action_digest"],
            "origin_event_id": request["origin_event_id"],
            "capability": request["capability"],
            "scope": copy.deepcopy(request["scope"]),
            "impact": impact or request["impact"],
            "decision": decision,
            "reason_code": reason_code,
            "policy_provenance": policy_provenance,
            "evaluated_at": _timestamp(self._now()),
        }
        if requester is not None:
            result["derived_requester_actor_id"] = requester
        result.update(copy.deepcopy(extra))
        self._audits.append(copy.deepcopy(result))
        return result

    def _deny(
        self,
        request: dict[str, Any],
        *,
        policy_provenance: str,
        reason_code: str,
        requester: str | None,
    ) -> dict[str, Any]:
        return self._decision(
            request,
            policy_provenance=policy_provenance,
            decision="DENY",
            reason_code=reason_code,
            requester=requester,
        )

    def authorize(
        self,
        request: Any,
        observation: Any,
        *,
        approval: Any | None = None,
    ) -> dict[str, Any]:
        """Evaluate one request without executing its privileged operation."""
        proposed = validate_authorization_request(request)
        context = _validate_observation(observation)
        parsed_approval = _approval(approval) if approval is not None else None
        with self._lock:
            binding = self._binding_bytes(proposed)
            previous = self._action_bindings.get(proposed["action_id"])
            if previous is not None and previous != binding:
                return self._deny(
                    proposed,
                    policy_provenance="unavailable:action-binding-conflict",
                    reason_code="deny-action-digest-mismatch",
                    requester=None,
                )
            if previous is None and len(self._action_bindings) >= self._max_state_entries:
                return self._deny(
                    proposed,
                    policy_provenance="unavailable:authorization-capacity",
                    reason_code="deny-unsupported-seam",
                    requester=None,
                )
            self._action_bindings.setdefault(proposed["action_id"], binding)

            try:
                policy = self._policy()
                provenance = policy.authorization.source
            except Exception:
                return self._deny(
                    proposed,
                    policy_provenance="unavailable:policy-load-failed",
                    reason_code="deny-policy-invalid",
                    requester=None,
                )

            requester, origin_error = _resolve_requester(proposed, context)
            if origin_error is not None:
                return self._deny(
                    proposed,
                    policy_provenance=provenance,
                    reason_code=origin_error,
                    requester=requester,
                )
            assert requester is not None

            actor_capability, exact = self._candidate_grants(policy, proposed, requester)
            if not exact:
                reason = "deny-scope-mismatch" if actor_capability else "deny-capability-missing"
                return self._deny(
                    proposed,
                    policy_provenance=provenance,
                    reason_code=reason,
                    requester=requester,
                )
            if len(exact) != 1:
                return self._deny(
                    proposed,
                    policy_provenance=provenance,
                    reason_code="deny-policy-invalid",
                    requester=requester,
                )
            grant = exact[0]
            now = self._now()
            if grant.status == "revoked":
                return self._deny(
                    proposed,
                    policy_provenance=provenance,
                    reason_code="deny-revoked",
                    requester=requester,
                )
            if grant.expires_at is not None and now >= grant.expires_at:
                return self._deny(
                    proposed,
                    policy_provenance=provenance,
                    reason_code="deny-expired",
                    requester=requester,
                )

            existing_allow = next(
                (
                    state
                    for state in self._allows.values()
                    if state.request["action_id"] == proposed["action_id"]
                ),
                None,
            )
            if existing_allow is not None:
                return self._deny(
                    proposed,
                    policy_provenance=provenance,
                    reason_code="deny-replay",
                    requester=requester,
                )

            if grant.execution == "direct":
                expires = now + timedelta(
                    seconds=policy.authorization.decision_ttl_seconds
                )
                decision = self._decision(
                    proposed,
                    policy_provenance=provenance,
                    decision="ALLOW",
                    reason_code="allow-direct-grant",
                    requester=requester,
                    authorization_basis="direct-grant",
                    expires_at=_timestamp(expires),
                )
                self._allows[decision["decision_id"]] = _AllowState(
                    decision=copy.deepcopy(decision),
                    request=copy.deepcopy(proposed),
                    requester_actor_id=requester,
                    grant_id=grant.grant_id,
                    expires_at=expires,
                )
                return copy.deepcopy(decision)

            challenge_state = next(
                (
                    state
                    for state in self._challenges.values()
                    if state.request == proposed and not state.satisfied
                ),
                None,
            )
            if parsed_approval is None:
                if challenge_state is not None and now < challenge_state.expires_at:
                    return copy.deepcopy(challenge_state.decision)
                expires = now + timedelta(
                    seconds=policy.authorization.approval_ttl_seconds
                )
                challenge = {
                    "challenge_id": self._id_factory("challenge"),
                    "allowed_approver_actor_ids": list(
                        grant.allowed_approver_actor_ids
                    ),
                    "expires_at": _timestamp(expires),
                }
                decision = self._decision(
                    proposed,
                    policy_provenance=provenance,
                    decision="APPROVAL_REQUIRED",
                    reason_code="approval-required-high-impact",
                    requester=requester,
                    approval_challenge=challenge,
                )
                self._challenges[challenge["challenge_id"]] = _ChallengeState(
                    decision=copy.deepcopy(decision),
                    request=copy.deepcopy(proposed),
                    requester_actor_id=requester,
                    grant_id=grant.grant_id,
                    expires_at=expires,
                )
                return copy.deepcopy(decision)

            challenge_state = self._challenges.get(parsed_approval["challenge_id"])
            approved_at = _parse_timestamp(parsed_approval["approved_at"])
            invalid = (
                challenge_state is None
                or challenge_state.satisfied
                or challenge_state.request != proposed
                or challenge_state.requester_actor_id != requester
                or challenge_state.grant_id != grant.grant_id
                or now >= challenge_state.expires_at
                or approved_at > now
                or approved_at >= challenge_state.expires_at
                or parsed_approval["approver_actor_id"]
                not in grant.allowed_approver_actor_ids
                or parsed_approval["attestation_id"] in self._used_attestations
            )
            if invalid:
                return self._deny(
                    proposed,
                    policy_provenance=provenance,
                    reason_code="deny-approval-invalid",
                    requester=requester,
                )
            challenge_state.satisfied = True
            self._used_attestations.add(parsed_approval["attestation_id"])
            expires = now + timedelta(seconds=policy.authorization.decision_ttl_seconds)
            decision = self._decision(
                proposed,
                policy_provenance=provenance,
                decision="ALLOW",
                reason_code="allow-authenticated-approval",
                requester=requester,
                authorization_basis="authenticated-approval",
                expires_at=_timestamp(expires),
                approval_evidence=parsed_approval,
            )
            self._allows[decision["decision_id"]] = _AllowState(
                decision=copy.deepcopy(decision),
                request=copy.deepcopy(proposed),
                requester_actor_id=requester,
                grant_id=grant.grant_id,
                expires_at=expires,
                approver_actor_id=parsed_approval["approver_actor_id"],
            )
            return copy.deepcopy(decision)

    @staticmethod
    def _current_grant(
        policy: OperatorPolicy,
        state: _AllowState,
    ) -> CapabilityGrant | None:
        matches = [
            grant
            for grant in policy.authorization.grants
            if grant.grant_id == state.grant_id
            and grant.actor_id == state.requester_actor_id
            and grant.capability == state.request["capability"]
            and grant.impact == state.request["impact"]
            and grant.scope.matches(state.request["scope"])
        ]
        return matches[0] if len(matches) == 1 else None

    def execute(
        self,
        decision_id: str,
        *,
        request: Any,
        observation: Any,
        operation: Any,
        executor: Callable[[Any], Any],
    ) -> Any:
        """Consume one exact allow and dispatch the exact bound operation once."""
        decision_id = _opaque(decision_id)
        proposed = validate_authorization_request(request)
        context = _validate_observation(observation)
        digest = canonical_action_digest(operation)
        with self._lock:
            state = self._allows.get(decision_id)
            if state is None or state.consumed:
                raise AuthorizationExecutionDenied("deny-replay")
            if state.request != proposed or digest != state.request["action_digest"]:
                raise AuthorizationExecutionDenied("deny-action-digest-mismatch")
            now = self._now()
            if now >= state.expires_at:
                raise AuthorizationExecutionDenied("deny-expired")
            requester, origin_error = _resolve_requester(proposed, context)
            if origin_error is not None or requester != state.requester_actor_id:
                raise AuthorizationExecutionDenied(
                    origin_error or "deny-origin-scope-mismatch"
                )
            try:
                policy = self._policy()
            except Exception as exc:
                raise AuthorizationExecutionDenied("deny-policy-invalid") from exc
            grant = self._current_grant(policy, state)
            if grant is None:
                raise AuthorizationExecutionDenied("deny-scope-mismatch")
            if grant.status == "revoked":
                raise AuthorizationExecutionDenied("deny-revoked")
            if grant.expires_at is not None and now >= grant.expires_at:
                raise AuthorizationExecutionDenied("deny-expired")
            basis = state.decision["authorization_basis"]
            if basis == "direct-grant" and grant.execution != "direct":
                raise AuthorizationExecutionDenied("deny-approval-invalid")
            if basis == "authenticated-approval":
                if (
                    grant.execution != "approval"
                    or state.approver_actor_id not in grant.allowed_approver_actor_ids
                ):
                    raise AuthorizationExecutionDenied("deny-approval-invalid")
            state.consumed = True
        return executor(copy.deepcopy(operation))

    def audit_records(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(copy.deepcopy(self._audits))


__all__ = [
    "AuthorizationContextError",
    "AuthorizationExecutionDenied",
    "AuthorizationRequestError",
    "PrivilegedActionGuard",
    "canonical_action_digest",
    "participant_authorization_result",
    "validate_authorization_request",
]
