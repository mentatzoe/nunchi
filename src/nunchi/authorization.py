"""Execution-time authorization for exact privileged actions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
from typing import Any, Protocol
from uuid import uuid4

from .errors import NunchiError, ValidationError
from .observation import ObservationProvider
from .participant import TransportResult


class AuthorizationError(NunchiError):
    """A privileged action could not be safely authorized."""

    label = "authorization error"


_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.-]*\.[a-z0-9_.-]+$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValidationError("policy expiry must be an ISO-8601 timestamp") from exc


def _strictly_after(reference: datetime) -> datetime:
    moment = _now()
    return moment if moment > reference else reference + timedelta(microseconds=1)


def canonical_operation_digest(operation: Mapping[str, Any]) -> dict[str, str]:
    try:
        payload = json.dumps(
            operation,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"privileged operation is not canonical JSON: {exc}") from exc
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(payload).hexdigest(),
        "canonicalization_profile": "nunchi.operation-json.v1",
    }


def _sanitized_effect_result(result: TransportResult) -> TransportResult:
    details = {
        "sent": "privileged effect confirmed",
        "failed": "privileged effect failed",
        "unknown": "privileged effect acknowledgement is unknown",
        "unavailable": "privileged effect is unavailable",
    }
    return TransportResult(result.delivery, details[result.delivery])


@dataclass(frozen=True)
class CapabilityRule:
    requester_actor_id: str
    capability: str
    platform: str
    room_id: str
    participant_id: str
    resource_kind: str
    resource_id: str
    continuity_scope_id: str
    installation_id: str
    direct_allow: bool = False
    preauthorized_high_impact: bool = False
    impact: str = "high"
    expires_at: str | None = None
    revoked: bool = False
    target_idempotency: bool = False

    def __post_init__(self) -> None:
        # Fail closed: an authorization rule that does not pin both the
        # trusted continuity scope and the host installation identity is
        # rejected at load time — it is never silently wildcarded.
        for name in (
            "requester_actor_id",
            "capability",
            "platform",
            "room_id",
            "participant_id",
            "resource_kind",
            "resource_id",
            "continuity_scope_id",
            "installation_id",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")
        if not _CAPABILITY.fullmatch(self.capability):
            raise ValueError("capability must be a namespaced identifier")
        if self.impact not in ("low", "high"):
            raise ValueError("impact must be low or high")
        if self.expires_at is not None:
            _parse_time(self.expires_at)


@dataclass(frozen=True)
class PolicySnapshot:
    policy_id: str
    revision: str
    rules: tuple[CapabilityRule, ...]
    approver_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.policy_id or not self.revision:
            raise ValueError("policy identity and revision must be non-empty")
        if len(set(self.approver_ids)) != len(self.approver_ids):
            raise ValueError("approver IDs must be unique")
        if any(not isinstance(item, str) or not item for item in self.approver_ids):
            raise ValueError("approver IDs must be non-empty")

    @property
    def provenance(self) -> dict[str, str]:
        return {
            "source": "trusted-operator-policy",
            "policy_id": self.policy_id,
            "revision": self.revision,
        }


class PolicySource(Protocol):
    def load(self) -> PolicySnapshot:
        """Reload the current trusted operator policy."""


class StaticPolicySource:
    """Thread-safe operator policy source useful for embedded hosts and tests."""

    def __init__(self, snapshot: PolicySnapshot) -> None:
        self._snapshot = snapshot
        self._lock = threading.Lock()

    def load(self) -> PolicySnapshot:
        with self._lock:
            return deepcopy(self._snapshot)

    def replace(self, snapshot: PolicySnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot


class PinnedFilePolicySource:
    """Policy file whose exact bytes are pinned by trusted host configuration."""

    def __init__(self, path: str | Path, *, expected_sha256: str) -> None:
        self.path = Path(path)
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValidationError("policy sha256 must be 64 lowercase hex characters")
        self.expected_sha256 = expected_sha256

    def load(self) -> PolicySnapshot:
        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise AuthorizationError(f"trusted policy cannot be read: {exc}") from exc
        if hashlib.sha256(raw).hexdigest() != self.expected_sha256:
            raise AuthorizationError("trusted policy bytes do not match the pinned digest")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthorizationError(f"trusted policy is invalid JSON: {exc.msg}") from exc
        if not isinstance(data, dict) or set(data) != {
            "policy_id",
            "revision",
            "approver_ids",
            "rules",
        }:
            raise AuthorizationError("trusted policy has an invalid closed shape")
        if not isinstance(data["rules"], list) or not isinstance(data["approver_ids"], list):
            raise AuthorizationError("trusted policy rules and approvers must be arrays")
        try:
            rules = tuple(CapabilityRule(**rule) for rule in data["rules"])
            return PolicySnapshot(
                policy_id=data["policy_id"],
                revision=data["revision"],
                rules=rules,
                approver_ids=tuple(data["approver_ids"]),
            )
        except (TypeError, ValueError) as exc:
            raise AuthorizationError(f"trusted policy is invalid: {exc}") from exc


class AuthorizationJournal:
    """Durable immutable authorization and effect-commit audit."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[dict[str, Any]] = []
        self._consumed_effects: set[str] = set()
        self._unknown_effects: set[str] = set()
        self._idempotency_keys: dict[str, str | None] = {}
        self._lock = threading.RLock()
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        try:
            with self.path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    self._validate_record(record, line_number=line_number)
                    self._records.append(record)
                    if record["kind"] == "effect_commit":
                        self._consumed_effects.add(record["effect_fingerprint"])
                        self._unknown_effects.add(record["effect_fingerprint"])
                        self._idempotency_keys[record["effect_fingerprint"]] = record[
                            "idempotency_key"
                        ]
                    if record["kind"] == "effect_retry_commit":
                        self._unknown_effects.add(record["effect_fingerprint"])
                    if record["kind"] == "effect_result":
                        if record["outcome"] == "UNKNOWN":
                            self._unknown_effects.add(record["effect_fingerprint"])
                        else:
                            self._unknown_effects.discard(record["effect_fingerprint"])
        except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
            raise AuthorizationError(
                f"authorization journal is not trustworthy at startup: {exc}"
            ) from exc

    @staticmethod
    def _validate_record(record: Any, *, line_number: int | None = None) -> None:
        label = f" at line {line_number}" if line_number is not None else ""
        if not isinstance(record, dict):
            raise ValueError(f"authorization audit record is not an object{label}")
        kind = record.get("kind")
        shapes = {
            "authorization_contract": {"kind", "record", "recorded_at"},
            "effect_commit": {
                "kind",
                "effect_fingerprint",
                "action_id",
                "decision_id",
                "action_digest",
                "idempotency_key",
                "committed_at",
            },
            "effect_retry_commit": {
                "kind",
                "effect_fingerprint",
                "action_id",
                "decision_id",
                "action_digest",
                "idempotency_key",
                "retry_id",
                "duplicate_effect_risk",
                "committed_at",
            },
            "effect_result": {
                "kind",
                "effect_fingerprint",
                "action_id",
                "outcome",
                "detail",
                "recorded_at",
            },
        }
        if kind not in shapes or set(record) != shapes[kind]:
            raise ValueError(f"authorization audit record has an invalid closed shape{label}")
        if kind == "authorization_contract":
            contract = record["record"]
            contract_shapes = {
                "request": (
                    {
                        "schema_version",
                        "kind",
                        "request_id",
                        "binding",
                        "requested_at",
                    },
                    set(),
                ),
                "decision": (
                    {
                        "schema_version",
                        "kind",
                        "request_id",
                        "decision_id",
                        "binding",
                        "outcome",
                        "reason",
                        "policy_provenance",
                        "evaluated_at",
                        "expires_at",
                        "revocation_checked_at",
                        "revocation_status",
                        "persistence_status",
                        "authorization_path",
                    },
                    {"approval_challenge_id", "approval_completion_id"},
                ),
                "approval_challenge": (
                    {
                        "schema_version",
                        "kind",
                        "request_id",
                        "approval_challenge_id",
                        "binding",
                        "policy_provenance",
                        "approver_ids",
                        "expires_at",
                        "host_only",
                    },
                    set(),
                ),
                "approval_completion": (
                    {
                        "schema_version",
                        "kind",
                        "request_id",
                        "approval_completion_id",
                        "approval_challenge_id",
                        "binding",
                        "authenticated_approver_id",
                        "completed_at",
                        "recheck",
                        "host_only",
                    },
                    set(),
                ),
            }
            if (
                not isinstance(contract, dict)
                or contract.get("schema_version") != 1
                or contract.get("kind") not in contract_shapes
            ):
                raise ValueError(f"authorization contract record is malformed{label}")
            required, optional = contract_shapes[contract["kind"]]
            if required - set(contract) or set(contract) - required - optional:
                raise ValueError(
                    f"authorization contract record has an invalid closed shape{label}"
                )
            if (
                not isinstance(contract.get("request_id"), str)
                or not contract["request_id"]
                or not isinstance(contract.get("binding"), dict)
                or not isinstance(record["recorded_at"], str)
            ):
                raise ValueError(f"authorization contract identity is malformed{label}")
        else:
            if (
                not isinstance(record["effect_fingerprint"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["effect_fingerprint"])
                or not isinstance(record["action_id"], str)
                or not record["action_id"]
            ):
                raise ValueError(f"authorization effect identity is malformed{label}")
        if kind in {"effect_commit", "effect_retry_commit"}:
            if (
                not isinstance(record["decision_id"], str)
                or not record["decision_id"]
                or not isinstance(record["action_digest"], dict)
                or not isinstance(record["committed_at"], str)
                or
                record["idempotency_key"] is not None
                and (
                    not isinstance(record["idempotency_key"], str)
                    or not record["idempotency_key"]
                )
            ):
                raise ValueError(f"authorization idempotency key is malformed{label}")
        if kind == "effect_retry_commit" and record["duplicate_effect_risk"] is not True:
            raise ValueError(f"effect retry must record duplicate risk{label}")
        if kind == "effect_result" and record["outcome"] not in {
            "CONFIRMED",
            "UNKNOWN",
            "FAILED",
        }:
            raise ValueError(f"authorization effect outcome is malformed{label}")
        if kind == "effect_result" and (
            not isinstance(record["detail"], str)
            or not isinstance(record["recorded_at"], str)
        ):
            raise ValueError(f"authorization effect result is malformed{label}")

    def append(self, record: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(record, Mapping) or not isinstance(record.get("kind"), str):
            raise ValidationError("authorization audit record must have a kind")
        checked = deepcopy(dict(record))
        try:
            self._validate_record(checked)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        payload = (
            json.dumps(
                checked,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        with self._lock:
            existed = self.path.exists()
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                written = os.write(fd, payload)
                if written != len(payload):
                    raise OSError(f"short write ({written}/{len(payload)} bytes)")
                os.fsync(fd)
            except OSError as exc:
                raise AuthorizationError(
                    f"authorization persistence is uncertain: {exc}"
                ) from exc
            finally:
                os.close(fd)
            if not existed:
                try:
                    directory_fd = os.open(self.path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError as exc:
                    raise AuthorizationError(
                        "authorization journal directory persistence is uncertain"
                    ) from exc
            self._records.append(checked)
            if checked["kind"] == "effect_commit":
                self._consumed_effects.add(checked["effect_fingerprint"])
                self._unknown_effects.add(checked["effect_fingerprint"])
                self._idempotency_keys[checked["effect_fingerprint"]] = checked[
                    "idempotency_key"
                ]
            if checked["kind"] == "effect_retry_commit":
                self._unknown_effects.add(checked["effect_fingerprint"])
            if checked["kind"] == "effect_result":
                if checked["outcome"] == "UNKNOWN":
                    self._unknown_effects.add(checked["effect_fingerprint"])
                else:
                    self._unknown_effects.discard(checked["effect_fingerprint"])
        return deepcopy(checked)

    def consumed(self, fingerprint: str) -> bool:
        with self._lock:
            return fingerprint in self._consumed_effects

    def unknown(self, fingerprint: str) -> bool:
        with self._lock:
            return fingerprint in self._unknown_effects

    def idempotency_key(self, fingerprint: str) -> str | None:
        with self._lock:
            return self._idempotency_keys.get(fingerprint)

    def records(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(self._records))


@dataclass
class _PendingApproval:
    request: dict[str, Any]
    decision: dict[str, Any]
    challenge: dict[str, Any]
    operation: dict[str, Any]
    effect_fingerprint: str
    cancel: threading.Event
    lifecycle_generation: int
    unknown_retry: bool = False


class AuthorizationCoordinator:
    """Resolve, recheck, persist, consume, and execute exact actions once."""

    def __init__(
        self,
        *,
        observation: ObservationProvider,
        policy_source: PolicySource,
        journal: AuthorizationJournal,
        executors: Mapping[
            str,
            Callable[[Mapping[str, Any], str | None], TransportResult],
        ],
        grant_ttl_seconds: int = 120,
        approval_ttl_seconds: int = 300,
    ) -> None:
        if grant_ttl_seconds < 1 or approval_ttl_seconds < 1:
            raise ValueError("authorization TTLs must be positive")
        self.observation = observation
        self.policy_source = policy_source
        self.journal = journal
        self.executors = dict(executors)
        self.grant_ttl_seconds = grant_ttl_seconds
        self.approval_ttl_seconds = approval_ttl_seconds
        self._pending: dict[str, _PendingApproval] = {}
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.Lock()
        self._native_effect_lock = threading.Lock()
        self._lifecycle_generation = 0

    def _capture_lifecycle(self) -> int:
        with self._lifecycle_lock:
            return self._lifecycle_generation

    def _lifecycle_is_current(
        self,
        generation: int,
        cancel: threading.Event,
    ) -> bool:
        if cancel.is_set():
            return False
        with self._lifecycle_lock:
            return generation == self._lifecycle_generation and not cancel.is_set()

    def _invalidate_lifecycle(self) -> None:
        # This fence is deliberately independent from authorization and effect
        # locks. A host lifecycle boundary must become visible immediately even
        # while policy I/O, journal persistence, approval work, or an executor
        # is blocking under ``self._lock``.
        with self._lifecycle_lock:
            self._lifecycle_generation += 1

    def _invoke_native_effect(
        self,
        *,
        capability: str,
        operation: Mapping[str, Any],
        idempotency_key: str | None,
        lifecycle_generation: int,
        cancel: threading.Event,
        cancelled_detail: str,
    ) -> TransportResult:
        """Cross the revocable lifecycle/native-call boundary exactly once."""
        with self._native_effect_lock:
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", cancelled_detail)
            try:
                executor = self.executors[capability]
            except BaseException:
                return TransportResult("unknown", "privileged acknowledgement was lost")
            # Executor resolution can itself block or execute user-controlled
            # mapping code. Recheck under the same dispatch barrier before the
            # actual privileged call.
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", cancelled_detail)
            try:
                result = executor(operation, idempotency_key)
            except BaseException:
                result = TransportResult("unknown", "privileged acknowledgement was lost")
        if not isinstance(result, TransportResult):
            result = TransportResult("unknown", "privileged executor returned no attestation")
        result = _sanitized_effect_result(result)
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult(
                "unknown",
                "privileged effect completed after lifecycle cancellation",
            )
        return result

    @staticmethod
    def _matching_rule(
        policy: PolicySnapshot,
        binding: Mapping[str, Any],
    ) -> CapabilityRule | None:
        scope = binding["scope"]
        resource = scope["resource"]
        requester = binding["derived_requester"]["actor_id"]
        for rule in policy.rules:
            if (
                rule.requester_actor_id == requester
                and rule.capability == binding["capability"]
                and rule.platform == scope["platform"]
                and rule.room_id == scope["room_id"]
                and rule.participant_id == scope["participant_id"]
                and rule.resource_kind == resource["kind"]
                and rule.resource_id == resource["id"]
                # Exact-scope bindings are mandatory: both identities are
                # required on the rule (enforced at construction), so a rule
                # only matches a binding carrying the identical trusted
                # continuity scope and host installation.
                and rule.continuity_scope_id == scope.get("continuity_scope_id")
                and rule.installation_id == scope.get("installation_id")
            ):
                return rule
        return None

    @staticmethod
    def _effect_fingerprint(binding: Mapping[str, Any]) -> str:
        stable = {
            "participant_id": binding["participant_id"],
            "origin_event_id": binding["origin_event_id"],
            "capability": binding["capability"],
            "scope": binding["scope"],
            "action_digest": binding["action_digest"],
        }
        return hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _build_binding(
        self,
        proposal: Mapping[str, Any],
        wake: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        origin = self.observation.resolve_event(proposal["origin_event_id"])
        if origin is None or origin.get("type") != "message":
            raise AuthorizationError("privileged origin is not a retained canonical message")
        if wake["self"]["participant_id"] != self.observation.binding.participant_id:
            raise AuthorizationError("participant identity changed before authorization")
        if (
            wake["room"]["id"] != self.observation.binding.room_id
            or wake["room"]["continuity_scope_id"]
            != self.observation.binding.continuity_scope_id
        ):
            raise AuthorizationError("room binding changed before authorization")
        resource = proposal["resource"]
        if set(resource) != {"kind", "id"}:
            raise ValidationError("privileged resource must contain exactly kind and id")
        for name in ("kind", "id"):
            if not isinstance(resource[name], str) or not resource[name]:
                raise ValidationError(f"privileged resource {name} must be non-empty")
        capability = proposal["capability"]
        if not isinstance(capability, str) or not _CAPABILITY.fullmatch(capability):
            raise ValidationError("privileged capability must be namespaced")
        operation = deepcopy(dict(proposal["operation"]))
        digest = canonical_operation_digest(operation)
        scope = {
            "platform": self.observation.binding.platform,
            "room_id": self.observation.binding.room_id,
            "continuity_scope_id": self.observation.binding.continuity_scope_id,
            "participant_id": self.observation.binding.participant_id,
            "resource": deepcopy(dict(resource)),
        }
        installation_id = getattr(self.observation.binding, "installation_id", None)
        if installation_id is not None:
            scope["installation_id"] = installation_id
        binding = {
            "action_id": f"action:{uuid4()}",
            "participant_id": self.observation.binding.participant_id,
            "origin_event_id": proposal["origin_event_id"],
            "capability": capability,
            "scope": scope,
            "action_digest": digest,
            "derived_requester": {
                "actor_id": origin["author_id"],
                "origin_event_id": origin["id"],
                "source": "transport-attested-origin-event",
            },
        }
        return binding, operation

    def _evaluate(
        self,
        *,
        binding: Mapping[str, Any],
        policy: PolicySnapshot,
        now: datetime,
        retry_unknown: bool = False,
        committed_recheck: bool = False,
    ) -> tuple[str, str, CapabilityRule | None]:
        fingerprint = self._effect_fingerprint(binding)
        if (
            self.journal.consumed(fingerprint)
            and not committed_recheck
            and not (retry_unknown and self.journal.unknown(fingerprint))
        ):
            return "DENY", "replay", None
        rule = self._matching_rule(policy, binding)
        if rule is None:
            return "DENY", "unauthorized", None
        if rule.revoked:
            return "DENY", "revoked", rule
        if rule.expires_at is not None and now >= _parse_time(rule.expires_at):
            return "DENY", "expired", rule
        if binding["capability"] not in self.executors:
            return "DENY", "policy-deny", rule
        high_impact = rule.impact == "high"
        if rule.direct_allow and (not high_impact or rule.preauthorized_high_impact):
            return "ALLOW", "policy-allow", rule
        return "APPROVAL_REQUIRED", "approval-required", rule

    def _decision(
        self,
        *,
        request_id: str,
        binding: Mapping[str, Any],
        policy: PolicySnapshot,
        outcome: str,
        reason: str,
        evaluated_at: datetime,
        authorization_path: str,
        decision_id: str | None = None,
        challenge_id: str | None = None,
        completion_id: str | None = None,
    ) -> dict[str, Any]:
        decision: dict[str, Any] = {
            "schema_version": 1,
            "kind": "decision",
            "request_id": request_id,
            "decision_id": decision_id or f"decision:{uuid4()}",
            "binding": deepcopy(dict(binding)),
            "outcome": outcome,
            "reason": reason,
            "policy_provenance": policy.provenance,
            "evaluated_at": _iso(evaluated_at),
            "expires_at": _iso(
                evaluated_at + timedelta(seconds=self.grant_ttl_seconds)
            ),
            "revocation_checked_at": _iso(evaluated_at),
            "revocation_status": "clear" if reason != "revoked" else "revoked",
            "persistence_status": "durable",
            "authorization_path": authorization_path,
        }
        if challenge_id is not None:
            decision["approval_challenge_id"] = challenge_id
        if completion_id is not None:
            decision["approval_completion_id"] = completion_id
        return decision

    def _persist_contract(self, record: Mapping[str, Any]) -> None:
        self.journal.append(
            {
                "kind": "authorization_contract",
                "record": deepcopy(dict(record)),
                "recorded_at": _iso(_now()),
            }
        )

    def _dispatch_once(
        self,
        *,
        binding: Mapping[str, Any],
        operation: Mapping[str, Any],
        decision: Mapping[str, Any],
        rule: CapabilityRule,
        cancel: threading.Event,
        lifecycle_generation: int,
    ) -> TransportResult:
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "privileged work cancelled before commit")
        # Exact execution-time policy and origin recheck.
        current_policy = self.policy_source.load()
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "privileged work cancelled during policy recheck")
        moment = _now()
        outcome, reason, current_rule = self._evaluate(
            binding=binding,
            policy=current_policy,
            now=moment,
        )
        if (
            outcome != "ALLOW"
            or reason != "policy-allow"
            or current_rule != rule
            or current_policy.provenance != decision["policy_provenance"]
            or moment >= _parse_time(decision["expires_at"])
            or self.observation.resolve_event(binding["origin_event_id"]) is None
            or canonical_operation_digest(operation) != binding["action_digest"]
        ):
            return TransportResult("failed", "authorization changed before effect commit")
        fingerprint = self._effect_fingerprint(binding)
        if self.journal.consumed(fingerprint):
            return TransportResult("failed", "authorization replay rejected")
        idempotency_key = (
            f"nunchi:{fingerprint}" if rule.target_idempotency else None
        )
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "privileged work cancelled before effect commit")
        # Persisting consumption is the one-use gate immediately before native
        # dispatch.  An uncertain write makes zero calls.
        self.journal.append(
            {
                "kind": "effect_commit",
                "effect_fingerprint": fingerprint,
                "action_id": binding["action_id"],
                "decision_id": decision["decision_id"],
                "action_digest": deepcopy(binding["action_digest"]),
                "idempotency_key": idempotency_key,
                "committed_at": _iso(moment),
            }
        )
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "privileged work cancelled before native effect")
        # Persistence can itself consume the remaining grant lifetime or
        # overlap a policy revocation. Reload every deterministic authority
        # fact after that blocking boundary and immediately before the effect.
        current_policy = self.policy_source.load()
        moment = _now()
        outcome, reason, current_rule = self._evaluate(
            binding=binding,
            policy=current_policy,
            now=moment,
            committed_recheck=True,
        )
        if (
            not self._lifecycle_is_current(lifecycle_generation, cancel)
            or outcome != "ALLOW"
            or reason != "policy-allow"
            or current_rule != rule
            or current_policy.provenance != decision["policy_provenance"]
            or moment >= _parse_time(decision["expires_at"])
            or self.observation.resolve_event(binding["origin_event_id"]) is None
            or canonical_operation_digest(operation) != binding["action_digest"]
        ):
            return TransportResult(
                "failed",
                "authorization changed before native effect",
            )
        result = self._invoke_native_effect(
            capability=binding["capability"],
            operation=operation,
            idempotency_key=idempotency_key,
            lifecycle_generation=lifecycle_generation,
            cancel=cancel,
            cancelled_detail="privileged work cancelled at native effect boundary",
        )
        native_outcome = "CONFIRMED" if result.delivery == "sent" else (
            "UNKNOWN" if result.delivery == "unknown" else "FAILED"
        )
        self.journal.append(
            {
                "kind": "effect_result",
                "effect_fingerprint": fingerprint,
                "action_id": binding["action_id"],
                "outcome": native_outcome,
                "detail": result.detail,
                "recorded_at": _iso(_now()),
            }
        )
        return result

    def _retry_unknown_effect(
        self,
        *,
        binding: Mapping[str, Any],
        operation: Mapping[str, Any],
        decision: Mapping[str, Any],
        rule: CapabilityRule,
        cancel: threading.Event,
        lifecycle_generation: int,
        authenticated_approval: bool,
    ) -> TransportResult:
        """Retry one previously unknown effect under fresh exact authority."""
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "unknown-effect retry was cancelled")
        fingerprint = self._effect_fingerprint(binding)
        if not self.journal.consumed(fingerprint) or not self.journal.unknown(fingerprint):
            return TransportResult("failed", "unknown-effect retry has no unknown predecessor")
        policy = self.policy_source.load()
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "unknown-effect retry was cancelled during policy recheck")
        now = _now()
        outcome, reason, current_rule = self._evaluate(
            binding=binding,
            policy=policy,
            now=now,
            retry_unknown=True,
        )
        authority_matches = (
            (authenticated_approval and outcome in {"ALLOW", "APPROVAL_REQUIRED"})
            or (
                not authenticated_approval
                and outcome == "ALLOW"
                and reason == "policy-allow"
                and rule.target_idempotency
            )
        )
        if (
            not authority_matches
            or current_rule != rule
            or policy.provenance != decision["policy_provenance"]
            or now >= _parse_time(decision["expires_at"])
            or self.observation.resolve_event(binding["origin_event_id"]) is None
            or canonical_operation_digest(operation) != binding["action_digest"]
        ):
            return TransportResult("failed", "unknown-effect retry authority changed")
        expected_key = f"nunchi:{fingerprint}" if rule.target_idempotency else None
        if self.journal.idempotency_key(fingerprint) != expected_key:
            return TransportResult("failed", "unknown-effect target idempotency binding changed")
        retry_id = f"effect-retry:{uuid4()}"
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "unknown-effect retry was cancelled before commit")
        self.journal.append(
            {
                "kind": "effect_retry_commit",
                "effect_fingerprint": fingerprint,
                "action_id": binding["action_id"],
                "decision_id": decision["decision_id"],
                "action_digest": deepcopy(binding["action_digest"]),
                "idempotency_key": expected_key,
                "retry_id": retry_id,
                "duplicate_effect_risk": True,
                "committed_at": _iso(now),
            }
        )
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "unknown-effect retry was cancelled before native effect")
        policy = self.policy_source.load()
        now = _now()
        outcome, reason, current_rule = self._evaluate(
            binding=binding,
            policy=policy,
            now=now,
            retry_unknown=True,
        )
        authority_matches = (
            (authenticated_approval and outcome in {"ALLOW", "APPROVAL_REQUIRED"})
            or (
                not authenticated_approval
                and outcome == "ALLOW"
                and reason == "policy-allow"
                and rule.target_idempotency
            )
        )
        if (
            not self._lifecycle_is_current(lifecycle_generation, cancel)
            or not authority_matches
            or current_rule != rule
            or policy.provenance != decision["policy_provenance"]
            or now >= _parse_time(decision["expires_at"])
            or self.observation.resolve_event(binding["origin_event_id"]) is None
            or canonical_operation_digest(operation) != binding["action_digest"]
            or self.journal.idempotency_key(fingerprint) != expected_key
        ):
            return TransportResult(
                "failed",
                "unknown-effect retry authority changed before native effect",
            )
        result = self._invoke_native_effect(
            capability=binding["capability"],
            operation=operation,
            idempotency_key=expected_key,
            lifecycle_generation=lifecycle_generation,
            cancel=cancel,
            cancelled_detail="unknown-effect retry cancelled at native effect boundary",
        )
        self.journal.append(
            {
                "kind": "effect_result",
                "effect_fingerprint": fingerprint,
                "action_id": binding["action_id"],
                "outcome": (
                    "CONFIRMED"
                    if result.delivery == "sent"
                    else "UNKNOWN"
                    if result.delivery == "unknown"
                    else "FAILED"
                ),
                "detail": result.detail,
                "recorded_at": _iso(_now()),
            }
        )
        return result

    def execute_proposal(
        self,
        *,
        proposal: Mapping[str, Any],
        wake: Mapping[str, Any],
        cancel: threading.Event,
    ) -> TransportResult:
        """Authorize one proposal; never accepts room text as authority."""
        lifecycle_generation = self._capture_lifecycle()
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "privileged proposal was already cancelled")
        with self._lock:
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", "privileged proposal was already cancelled")
            try:
                binding, operation = self._build_binding(proposal, wake)
            except (AuthorizationError, ValidationError) as exc:
                return TransportResult("failed", str(exc))
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", "privileged proposal was cancelled before audit")
            requested_at = _now()
            request_id = f"authorization:{uuid4()}"
            request = {
                "schema_version": 1,
                "kind": "request",
                "request_id": request_id,
                "binding": deepcopy(binding),
                "requested_at": _iso(requested_at),
            }
            self._persist_contract(request)
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", "privileged proposal was cancelled during audit")
            try:
                policy = self.policy_source.load()
            except BaseException:
                return TransportResult("failed", "trusted authorization policy is unavailable")
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", "privileged proposal was cancelled during policy load")
            evaluated_at = _strictly_after(requested_at)
            fingerprint = self._effect_fingerprint(binding)
            unknown_retry = self.journal.unknown(fingerprint)
            outcome, reason, rule = self._evaluate(
                binding=binding,
                policy=policy,
                now=evaluated_at,
                retry_unknown=unknown_retry,
            )
            if (
                unknown_retry
                and outcome == "ALLOW"
                and rule is not None
                and not rule.target_idempotency
            ):
                # A target without idempotency can only be retried after a
                # fresh authenticated operator accepts the duplicate risk.
                outcome = "APPROVAL_REQUIRED"
                reason = "approval-required"
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", "privileged proposal was cancelled during evaluation")
            if outcome == "APPROVAL_REQUIRED":
                challenge_id = f"approval:{secrets.token_urlsafe(24)}"
                decision = self._decision(
                    request_id=request_id,
                    binding=binding,
                    policy=policy,
                    outcome=outcome,
                    reason=reason,
                    evaluated_at=evaluated_at,
                    authorization_path="direct-policy",
                    challenge_id=challenge_id,
                )
                challenge = {
                    "schema_version": 1,
                    "kind": "approval_challenge",
                    "request_id": request_id,
                    "approval_challenge_id": challenge_id,
                    "binding": deepcopy(binding),
                    "policy_provenance": policy.provenance,
                    "approver_ids": list(policy.approver_ids),
                    "expires_at": _iso(
                        evaluated_at + timedelta(seconds=self.approval_ttl_seconds)
                    ),
                    "host_only": True,
                }
                if not self._lifecycle_is_current(lifecycle_generation, cancel):
                    return TransportResult("failed", "privileged proposal was cancelled before challenge")
                self._persist_contract(decision)
                if not self._lifecycle_is_current(lifecycle_generation, cancel):
                    return TransportResult("failed", "privileged proposal was cancelled during challenge audit")
                self._persist_contract(challenge)
                if not self._lifecycle_is_current(lifecycle_generation, cancel):
                    return TransportResult("failed", "privileged proposal was cancelled during challenge audit")
                self._pending[challenge_id] = _PendingApproval(
                    request=request,
                    decision=decision,
                    challenge=challenge,
                    operation=operation,
                    effect_fingerprint=fingerprint,
                    cancel=cancel,
                    lifecycle_generation=lifecycle_generation,
                    unknown_retry=unknown_retry,
                )
                if not self._lifecycle_is_current(lifecycle_generation, cancel):
                    self._pending.pop(challenge_id, None)
                    return TransportResult("failed", "privileged proposal was cancelled before challenge publication")
                return TransportResult("unavailable", "authenticated operator approval required")
            decision = self._decision(
                request_id=request_id,
                binding=binding,
                policy=policy,
                outcome=outcome,
                reason=reason,
                evaluated_at=evaluated_at,
                authorization_path="direct-policy",
            )
            self._persist_contract(decision)
            if not self._lifecycle_is_current(lifecycle_generation, cancel):
                return TransportResult("failed", "privileged proposal was cancelled during decision audit")
            if outcome != "ALLOW" or rule is None:
                return TransportResult("failed", f"privileged action denied: {reason}")
            if unknown_retry:
                return self._retry_unknown_effect(
                    binding=binding,
                    operation=operation,
                    decision=decision,
                    rule=rule,
                    cancel=cancel,
                    lifecycle_generation=lifecycle_generation,
                    authenticated_approval=False,
                )
            return self._dispatch_once(
                binding=binding,
                operation=operation,
                decision=decision,
                rule=rule,
                cancel=cancel,
                lifecycle_generation=lifecycle_generation,
            )

    def pending_for_operator(self) -> tuple[dict[str, Any], ...]:
        """Return the exact host-only proposal an operator must inspect."""
        with self._lock:
            now = _now()
            for challenge_id, item in tuple(self._pending.items()):
                if (
                    not self._lifecycle_is_current(
                        item.lifecycle_generation,
                        item.cancel,
                    )
                    or now >= _parse_time(item.challenge["expires_at"])
                ):
                    self._pending.pop(challenge_id, None)
            return tuple(
                {
                    "challenge": deepcopy(item.challenge),
                    "request": deepcopy(item.request),
                    "origin_observation": self.observation.resolve_event(
                        item.request["binding"]["origin_event_id"]
                    ),
                    "operation": deepcopy(item.operation),
                    "duplicate_effect_risk": item.unknown_retry,
                }
                for item in self._pending.values()
            )

    def complete_authenticated_approval(
        self,
        *,
        approval_challenge_id: str,
        authenticated_approver_id: str,
    ) -> TransportResult:
        """Complete approval only from a trusted, authenticated operator seam."""
        with self._lock:
            pending = self._pending.pop(approval_challenge_id, None)
            if pending is None:
                return TransportResult("failed", "approval challenge is unknown or already consumed")
            now = _strictly_after(_parse_time(pending.decision["evaluated_at"]))
            challenge = pending.challenge
            if (
                not self._lifecycle_is_current(pending.lifecycle_generation, pending.cancel)
                or now >= _parse_time(challenge["expires_at"])
                or authenticated_approver_id not in challenge["approver_ids"]
            ):
                return TransportResult("failed", "approval is cancelled, expired, or unauthorized")
            policy = self.policy_source.load()
            now = _strictly_after(now)
            if (
                not self._lifecycle_is_current(pending.lifecycle_generation, pending.cancel)
                or now >= _parse_time(challenge["expires_at"])
            ):
                return TransportResult("failed", "approval was cancelled or expired during policy recheck")
            binding = pending.request["binding"]
            outcome, reason, rule = self._evaluate(
                binding=binding,
                policy=policy,
                now=now,
                retry_unknown=pending.unknown_retry,
            )
            # Approval is the sole missing authority.  The matching rule may
            # still report APPROVAL_REQUIRED; the authenticated completion
            # supplies that exact authority while every other fact is rechecked.
            valid_authority = (
                pending.unknown_retry
                and outcome in {"ALLOW", "APPROVAL_REQUIRED"}
                and rule is not None
            ) or (
                not pending.unknown_retry
                and outcome == "APPROVAL_REQUIRED"
                and reason == "approval-required"
                and rule is not None
            )
            if not valid_authority:
                return TransportResult("failed", "policy changed before approval completion")
            if policy.provenance != challenge["policy_provenance"]:
                return TransportResult("failed", "policy revision changed before approval completion")
            if not self._lifecycle_is_current(pending.lifecycle_generation, pending.cancel):
                return TransportResult("failed", "approval was cancelled before completion audit")
            completion_id = f"approval-completion:{uuid4()}"
            recheck_at = _strictly_after(now)
            completion = {
                "schema_version": 1,
                "kind": "approval_completion",
                "request_id": pending.request["request_id"],
                "approval_completion_id": completion_id,
                "approval_challenge_id": approval_challenge_id,
                "binding": deepcopy(binding),
                "authenticated_approver_id": authenticated_approver_id,
                "completed_at": _iso(now),
                "recheck": {
                    "outcome": "ALLOW",
                    "policy_provenance": policy.provenance,
                    "evaluated_at": _iso(recheck_at),
                    "expires_at": _iso(
                        recheck_at + timedelta(seconds=self.grant_ttl_seconds)
                    ),
                    "revocation_checked_at": _iso(recheck_at),
                    "revocation_status": "clear",
                    "persistence_status": "durable",
                },
                "host_only": True,
            }
            allow = self._decision(
                request_id=pending.request["request_id"],
                binding=binding,
                policy=policy,
                outcome="ALLOW",
                reason="policy-allow",
                evaluated_at=_strictly_after(recheck_at),
                authorization_path="authenticated-approval",
                challenge_id=approval_challenge_id,
                completion_id=completion_id,
            )
            # The completion grants one fixed expiry horizon. The later
            # correlated ALLOW cannot extend it.
            allow["expires_at"] = completion["recheck"]["expires_at"]
            self._persist_contract(completion)
            if not self._lifecycle_is_current(pending.lifecycle_generation, pending.cancel):
                return TransportResult("failed", "approval was cancelled during completion audit")
            self._persist_contract(allow)
            if not self._lifecycle_is_current(pending.lifecycle_generation, pending.cancel):
                return TransportResult("failed", "approval was cancelled during completion audit")
            if pending.unknown_retry:
                return self._retry_unknown_effect(
                    binding=binding,
                    operation=pending.operation,
                    decision=allow,
                    rule=rule,
                    cancel=pending.cancel,
                    lifecycle_generation=pending.lifecycle_generation,
                    authenticated_approval=True,
                )
            # The dispatch recheck expects a direct allow.  The authenticated
            # completion is the only difference; every rule fact remains exact.
            return self._dispatch_approved_once(
                binding=binding,
                operation=pending.operation,
                decision=allow,
                rule=rule,
                cancel=pending.cancel,
                lifecycle_generation=pending.lifecycle_generation,
            )

    def _dispatch_approved_once(
        self,
        *,
        binding: Mapping[str, Any],
        operation: Mapping[str, Any],
        decision: Mapping[str, Any],
        rule: CapabilityRule,
        cancel: threading.Event,
        lifecycle_generation: int,
    ) -> TransportResult:
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "approved work was cancelled before commit")
        policy = self.policy_source.load()
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "approved work was cancelled during policy recheck")
        now = _now()
        outcome, reason, current_rule = self._evaluate(
            binding=binding,
            policy=policy,
            now=now,
        )
        if (
            outcome != "APPROVAL_REQUIRED"
            or reason != "approval-required"
            or current_rule != rule
            or policy.provenance != decision["policy_provenance"]
            or now >= _parse_time(decision["expires_at"])
            or self.observation.resolve_event(binding["origin_event_id"]) is None
            or canonical_operation_digest(operation) != binding["action_digest"]
        ):
            return TransportResult("failed", "approved authority changed before effect commit")
        fingerprint = self._effect_fingerprint(binding)
        if self.journal.consumed(fingerprint):
            return TransportResult("failed", "approved action replay rejected")
        idempotency_key = f"nunchi:{fingerprint}" if rule.target_idempotency else None
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "approved work was cancelled before effect commit")
        self.journal.append(
            {
                "kind": "effect_commit",
                "effect_fingerprint": fingerprint,
                "action_id": binding["action_id"],
                "decision_id": decision["decision_id"],
                "action_digest": deepcopy(binding["action_digest"]),
                "idempotency_key": idempotency_key,
                "committed_at": _iso(now),
            }
        )
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult("failed", "approved work was cancelled before native effect")
        policy = self.policy_source.load()
        now = _now()
        outcome, reason, current_rule = self._evaluate(
            binding=binding,
            policy=policy,
            now=now,
            committed_recheck=True,
        )
        if (
            not self._lifecycle_is_current(lifecycle_generation, cancel)
            or outcome != "APPROVAL_REQUIRED"
            or reason != "approval-required"
            or current_rule != rule
            or policy.provenance != decision["policy_provenance"]
            or now >= _parse_time(decision["expires_at"])
            or self.observation.resolve_event(binding["origin_event_id"]) is None
            or canonical_operation_digest(operation) != binding["action_digest"]
        ):
            return TransportResult(
                "failed",
                "approved authority changed before native effect",
            )
        if not self._lifecycle_is_current(lifecycle_generation, cancel):
            return TransportResult(
                "failed",
                "approved work cancelled at native effect boundary",
            )
        result = self._invoke_native_effect(
            capability=binding["capability"],
            operation=operation,
            idempotency_key=idempotency_key,
            lifecycle_generation=lifecycle_generation,
            cancel=cancel,
            cancelled_detail="approved work cancelled at native effect boundary",
        )
        self.journal.append(
            {
                "kind": "effect_result",
                "effect_fingerprint": fingerprint,
                "action_id": binding["action_id"],
                "outcome": (
                    "CONFIRMED"
                    if result.delivery == "sent"
                    else "UNKNOWN"
                    if result.delivery == "unknown"
                    else "FAILED"
                ),
                "detail": result.detail,
                "recorded_at": _iso(_now()),
            }
        )
        return result

    def cancel(self) -> None:
        """Synchronously invalidate all privileged work and pending approvals."""
        self._invalidate_lifecycle()
        # Replacing the map is an atomic visibility boundary on supported
        # CPython hosts and does not wait behind policy, audit, approval, or
        # executor work holding ``self._lock``. In-flight paths retain their
        # own generation and must fail their next lifecycle check.
        pending = self._pending
        self._pending = {}
        # Do not return while a native effect can still begin. Invalidation is
        # visible before this barrier, so blocked executor lookup is fenced by
        # the generation recheck and an already-running executor is drained
        # before cancellation reports completion.
        with self._native_effect_lock:
            pass
        for item in pending.values():
            item.cancel.set()

    restart = cancel
