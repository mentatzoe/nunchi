"""Strict shared V2 operator-policy loader.

Room input never reaches this loader.  A host selects one absolute file owned
by the effective user; the loader opens it without following symlinks, rejects
group/other permissions, duplicate JSON keys, non-finite numbers, unknown
fields, and partially valid sections, then returns immutable typed policy.

The policy provenance is derived from the validated source label and exact file
bytes.  The path, credentials, and raw grants are not part of that provenance
and must never enter classifier or participant projections.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .net import is_bounded_ascii_credential, is_loopback_hostname


MAX_POLICY_BYTES = 1024 * 1024
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
_UTC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z$"
)
IMPACTS = (
    "privileged-read",
    "mutation",
    "destructive",
    "external-side-effect",
    "secret-bearing",
    "account-configuration",
    "transport-send",
    "context-expansion",
)


class PolicyLoadError(ValueError):
    """A safe, stable policy-loading failure.

    ``code`` is suitable for an operational error branch.  ``detail`` is
    intentionally generic and never includes a path, credential, or raw value.
    """

    def __init__(self, code: str, detail: str = "operator policy is invalid") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ResourceScope:
    platform: str
    room_id: str
    participant_id: str
    resource_kind: str
    resource_id: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "room_id": self.room_id,
            "participant_id": self.participant_id,
            "resource": {"kind": self.resource_kind, "id": self.resource_id},
        }

    def matches(self, scope: dict[str, Any]) -> bool:
        return scope == self.to_contract()


@dataclass(frozen=True)
class CapabilityGrant:
    grant_id: str
    actor_id: str
    capability: str
    scope: ResourceScope
    impact: str
    execution: str
    status: str
    allowed_approver_actor_ids: tuple[str, ...] = ()
    expires_at: datetime | None = None


@dataclass(frozen=True)
class EffectiveAttentionPolicy:
    participant_id: str
    preattention_enabled: bool
    social_suppression_enabled: bool
    attention_max_events: int
    attention_max_bytes: int
    participant_max_events: int
    participant_max_bytes: int
    fetch_max_events: int
    fetch_max_bytes: int
    error_action: str
    source: str
    transition_defer_margin: float | None = None
    transition_defer_margin_source: str | None = None


@dataclass(frozen=True)
class RecoverabilityPolicy:
    participant_id: str
    continuity_scope_id: str
    eligible: bool
    source: str


@dataclass(frozen=True)
class ClassifierPolicy:
    provider: str
    endpoint: str
    model: str
    timeout_seconds: float
    max_retries: int
    source: str
    api_key: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class AuthorizationPolicy:
    decision_ttl_seconds: int
    approval_ttl_seconds: int
    grants: tuple[CapabilityGrant, ...]
    source: str


@dataclass(frozen=True)
class ReceiptSinkPolicy:
    type: str
    directory: str
    source: str


@dataclass(frozen=True)
class OperatorPolicy:
    schema_version: int
    source_label: str
    provenance: str
    attention: EffectiveAttentionPolicy
    recoverability: RecoverabilityPolicy
    classifier: ClassifierPolicy
    authorization: AuthorizationPolicy
    receipt_sink: ReceiptSinkPolicy


def _fail(code: str = "policy-invalid") -> PolicyLoadError:
    return PolicyLoadError(code)


def _closed_object(
    value: Any,
    *,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail()
    allowed = set(required) | set(optional)
    if set(value) - allowed or any(name not in value for name in required):
        raise _fail()
    return value


def _string(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise _fail()
    return value


def _identifier(value: Any) -> str:
    result = _string(value)
    if len(result) > 512:
        raise _fail()
    return result


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise _fail()
    return value


def _positive_integer(value: Any, *, maximum: int = 2**31 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail()
    if value < 1 or value > maximum:
        raise _fail()
    return value


def _finite_positive(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail()
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise _fail()
    return result


def _utc_timestamp(value: Any) -> datetime:
    text = _string(value)
    if _UTC_TIMESTAMP_RE.fullmatch(text) is None:
        raise _fail()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _fail() from exc


def _scope(value: Any) -> ResourceScope:
    data = _closed_object(
        value,
        required=("platform", "room_id", "participant_id", "resource"),
    )
    resource = _closed_object(data["resource"], required=("kind", "id"))
    return ResourceScope(
        platform=_string(data["platform"]),
        room_id=_identifier(data["room_id"]),
        participant_id=_identifier(data["participant_id"]),
        resource_kind=_string(resource["kind"]),
        resource_id=_identifier(resource["id"]),
    )


def _attention(value: Any, provenance: str) -> EffectiveAttentionPolicy:
    required = (
        "participant_id",
        "preattention_enabled",
        "social_suppression_enabled",
        "attention_max_events",
        "attention_max_bytes",
        "participant_max_events",
        "participant_max_bytes",
        "fetch_max_events",
        "fetch_max_bytes",
        "error_action",
    )
    data = _closed_object(
        value,
        required=required,
        optional=("transition_defer_margin", "transition_defer_margin_source"),
    )
    has_margin = "transition_defer_margin" in data
    has_source = "transition_defer_margin_source" in data
    if has_margin != has_source:
        raise _fail()
    margin: float | None = None
    margin_source: str | None = None
    if has_margin:
        raw_margin = data["transition_defer_margin"]
        if isinstance(raw_margin, bool) or not isinstance(raw_margin, (int, float)):
            raise _fail()
        margin = float(raw_margin)
        if not math.isfinite(margin) or not 0.0 <= margin <= 1.0:
            raise _fail()
        margin_source = _string(data["transition_defer_margin_source"])
    error_action = data["error_action"]
    if error_action not in ("WAKE", "NO_WAKE"):
        raise _fail()
    return EffectiveAttentionPolicy(
        participant_id=_identifier(data["participant_id"]),
        preattention_enabled=_boolean(data["preattention_enabled"]),
        social_suppression_enabled=_boolean(data["social_suppression_enabled"]),
        attention_max_events=_positive_integer(data["attention_max_events"]),
        attention_max_bytes=_positive_integer(data["attention_max_bytes"]),
        participant_max_events=_positive_integer(data["participant_max_events"]),
        participant_max_bytes=_positive_integer(data["participant_max_bytes"]),
        fetch_max_events=_positive_integer(data["fetch_max_events"]),
        fetch_max_bytes=_positive_integer(data["fetch_max_bytes"]),
        error_action=error_action,
        source=provenance,
        transition_defer_margin=margin,
        transition_defer_margin_source=margin_source,
    )


def _recoverability(value: Any, provenance: str) -> RecoverabilityPolicy:
    data = _closed_object(
        value,
        required=("participant_id", "continuity_scope_id", "eligible"),
    )
    return RecoverabilityPolicy(
        participant_id=_identifier(data["participant_id"]),
        continuity_scope_id=_identifier(data["continuity_scope_id"]),
        eligible=_boolean(data["eligible"]),
        source=provenance,
    )


def _classifier(value: Any, provenance: str) -> ClassifierPolicy:
    data = _closed_object(
        value,
        required=(
            "provider",
            "endpoint",
            "model",
            "timeout_seconds",
            "max_retries",
        ),
        optional=("api_key",),
    )
    retries = data["max_retries"]
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 2:
        raise _fail()
    api_key = None
    if "api_key" in data:
        api_key = data["api_key"]
        if not is_bounded_ascii_credential(api_key):
            raise _fail()
    provider = _string(data["provider"])
    if provider != "openai-compatible":
        raise _fail()
    endpoint = _classifier_endpoint(data["endpoint"])
    return ClassifierPolicy(
        provider=provider,
        endpoint=endpoint,
        model=_string(data["model"]),
        timeout_seconds=_finite_positive(data["timeout_seconds"]),
        max_retries=retries,
        source=provenance,
        api_key=api_key,
    )


def _classifier_endpoint(value: Any) -> str:
    endpoint = _string(value)
    if any(ord(character) <= 32 or ord(character) == 127 for character in endpoint):
        raise _fail()
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise _fail() from exc
    if (
        host is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise _fail()
    if parsed.scheme == "https":
        return endpoint
    if parsed.scheme != "http" or not is_loopback_hostname(host):
        raise _fail()
    return endpoint


def _grant(value: Any) -> CapabilityGrant:
    data = _closed_object(
        value,
        required=(
            "grant_id",
            "actor_id",
            "capability",
            "scope",
            "impact",
            "execution",
            "status",
        ),
        optional=("allowed_approver_actor_ids", "expires_at"),
    )
    capability = _string(data["capability"])
    if _CAPABILITY_RE.fullmatch(capability) is None:
        raise _fail()
    impact = data["impact"]
    if impact not in IMPACTS:
        raise _fail()
    execution = data["execution"]
    if execution not in ("direct", "approval"):
        raise _fail()
    status = data["status"]
    if status not in ("active", "revoked"):
        raise _fail()
    approvers: tuple[str, ...] = ()
    if "allowed_approver_actor_ids" in data:
        raw_approvers = data["allowed_approver_actor_ids"]
        if not isinstance(raw_approvers, list) or not raw_approvers:
            raise _fail()
        parsed = tuple(_identifier(item) for item in raw_approvers)
        if len(set(parsed)) != len(parsed):
            raise _fail()
        approvers = parsed
    if execution == "approval" and not approvers:
        raise _fail()
    if execution == "direct" and approvers:
        raise _fail()
    expires_at = _utc_timestamp(data["expires_at"]) if "expires_at" in data else None
    return CapabilityGrant(
        grant_id=_identifier(data["grant_id"]),
        actor_id=_identifier(data["actor_id"]),
        capability=capability,
        scope=_scope(data["scope"]),
        impact=impact,
        execution=execution,
        status=status,
        allowed_approver_actor_ids=approvers,
        expires_at=expires_at,
    )


def _authorization(value: Any, provenance: str) -> AuthorizationPolicy:
    data = _closed_object(
        value,
        required=("decision_ttl_seconds", "approval_ttl_seconds", "grants"),
    )
    raw_grants = data["grants"]
    if not isinstance(raw_grants, list):
        raise _fail()
    grants = tuple(_grant(item) for item in raw_grants)
    grant_ids = [grant.grant_id for grant in grants]
    if len(set(grant_ids)) != len(grant_ids):
        raise _fail()
    binding_keys = [
        (
            grant.actor_id,
            grant.capability,
            grant.scope,
            grant.impact,
        )
        for grant in grants
    ]
    if len(set(binding_keys)) != len(binding_keys):
        raise _fail()
    return AuthorizationPolicy(
        decision_ttl_seconds=_positive_integer(
            data["decision_ttl_seconds"], maximum=3600
        ),
        approval_ttl_seconds=_positive_integer(
            data["approval_ttl_seconds"], maximum=86400
        ),
        grants=grants,
        source=provenance,
    )


def _receipt_sink(value: Any, provenance: str) -> ReceiptSinkPolicy:
    data = _closed_object(value, required=("type", "directory", "source"))
    if data["type"] != "exclusive-json-file":
        raise _fail()
    directory = _string(data["directory"])
    if not Path(directory).is_absolute():
        raise _fail()
    return ReceiptSinkPolicy(
        type="exclusive-json-file",
        directory=directory,
        source=f"{_string(data['source'])}@{provenance}",
    )


def _reject_constant(_value: str) -> Any:
    raise _fail()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _fail("policy-duplicate-key")
        result[key] = value
    return result


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except PolicyLoadError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail("policy-invalid-json") from exc
    if not isinstance(value, dict):
        raise _fail()
    return value


def _read_secure_file(path: Path) -> bytes:
    if not path.is_absolute():
        raise _fail("policy-path-invalid")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise _fail("policy-unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise _fail("policy-source-unsafe")
        if metadata.st_uid != os.geteuid():
            raise _fail("policy-source-unsafe")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise _fail("policy-source-unsafe")
        if metadata.st_size > MAX_POLICY_BYTES:
            raise _fail("policy-too-large")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, MAX_POLICY_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_POLICY_BYTES:
                raise _fail("policy-too-large")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _policy_from_raw(raw: bytes) -> OperatorPolicy:
    root = _closed_object(
        _parse(raw),
        required=(
            "schema_version",
            "source",
            "attention",
            "recoverability",
            "classifier",
            "authorization",
            "receipt_sink",
        ),
    )
    if root["schema_version"] != 2:
        raise _fail()
    source_label = _string(root["source"])
    digest = hashlib.sha256(raw).hexdigest()
    provenance = f"{source_label}@sha256:{digest}"
    return OperatorPolicy(
        schema_version=2,
        source_label=source_label,
        provenance=provenance,
        attention=_attention(root["attention"], provenance),
        recoverability=_recoverability(root["recoverability"], provenance),
        classifier=_classifier(root["classifier"], provenance),
        authorization=_authorization(root["authorization"], provenance),
        receipt_sink=_receipt_sink(root["receipt_sink"], provenance),
    )


def load_operator_policy(path: str | os.PathLike[str]) -> OperatorPolicy:
    """Load one immutable V2 policy from a trusted operator-selected file."""
    return _policy_from_raw(_read_secure_file(Path(path)))


def update_operator_attention_controls(
    path: str | os.PathLike[str],
    patch: dict[str, Any],
    *,
    expected_provenance: str,
) -> OperatorPolicy:
    """Atomically update the small non-secret attention-control surface.

    The caller must present the exact provenance it inspected. Identity,
    provider endpoint/model/credential, authorization grants, receipt binding,
    recoverability, and all budgets are deliberately outside this mutation
    surface.
    """
    allowed = {
        "preattention_enabled",
        "social_suppression_enabled",
        "error_action",
        "transition_defer_margin",
    }
    if (
        not isinstance(patch, dict)
        or not patch
        or set(patch) - allowed
        or not isinstance(expected_provenance, str)
        or not expected_provenance
    ):
        raise _fail("policy-update-invalid")
    policy_path = Path(path)
    raw = _read_secure_file(policy_path)
    current = _policy_from_raw(raw)
    if current.provenance != expected_provenance:
        raise _fail("policy-stale")
    root = _parse(raw)
    attention = root.get("attention")
    if not isinstance(attention, dict):
        raise _fail()
    for key, value in patch.items():
        if key in ("preattention_enabled", "social_suppression_enabled"):
            if not isinstance(value, bool):
                raise _fail("policy-update-invalid")
            attention[key] = value
        elif key == "error_action":
            if value not in ("WAKE", "NO_WAKE"):
                raise _fail("policy-update-invalid")
            attention[key] = value
        elif key == "transition_defer_margin":
            if value is None:
                attention.pop("transition_defer_margin", None)
                attention.pop("transition_defer_margin_source", None)
            else:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    raise _fail("policy-update-invalid")
                attention[key] = float(value)
                attention["transition_defer_margin_source"] = (
                    "operator:codex-config-app"
                )
    try:
        updated_raw = (
            json.dumps(
                root,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _fail("policy-update-invalid") from exc
    if len(updated_raw) > MAX_POLICY_BYTES:
        raise _fail("policy-too-large")
    updated = _policy_from_raw(updated_raw)
    try:
        parent = policy_path.parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o022
        ):
            raise _fail("policy-source-unsafe")
        if _read_secure_file(policy_path) != raw:
            raise _fail("policy-stale")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=policy_path.parent,
            prefix=".nunchi-policy-",
            suffix=".tmp",
        )
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(updated_raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("policy update made no progress")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary_name, policy_path)
            directory_fd = os.open(
                policy_path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except BaseException:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
    except PolicyLoadError:
        raise
    except OSError as exc:
        raise _fail("policy-update-failed") from exc
    return updated


class OperatorPolicySource:
    """Reloadable source used by hosts immediately before privileged effects."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    def load(self) -> OperatorPolicy:
        return load_operator_policy(self._path)

    def loader(self) -> Callable[[], OperatorPolicy]:
        return self.load


__all__ = [
    "AuthorizationPolicy",
    "CapabilityGrant",
    "ClassifierPolicy",
    "EffectiveAttentionPolicy",
    "IMPACTS",
    "OperatorPolicy",
    "OperatorPolicySource",
    "PolicyLoadError",
    "RecoverabilityPolicy",
    "ReceiptSinkPolicy",
    "ResourceScope",
    "load_operator_policy",
    "update_operator_attention_controls",
]
