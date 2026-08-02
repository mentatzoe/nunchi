"""Shared configuration, diagnostics, and persistent-service primitives.

The CLI and dashboard both call this module.  Platform integrations register
native capability facts here; they never add social routing semantics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Iterator

from . import __version__
from .ack import AckPolicy
from .attention import AttentionPolicy
from .errors import ValidationError
from .install import initialize, verify

try:  # POSIX is the supported service environment; import stays portable.
    import fcntl
except ImportError:  # pragma: no cover - Windows reports unsupported service persistence.
    fcntl = None


OPERATOR_SCHEMA_VERSION = 1
_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SERVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_CONFIG_BYTES = 1_048_576
_LOCAL_SUPERVISORS: dict[int, subprocess.Popen[bytes]] = {}
_LOCAL_SUPERVISORS_LOCK = threading.Lock()


@dataclass(frozen=True)
class PlatformRegistration:
    name: str
    participant_kind: str
    capabilities: Mapping[str, Any]
    compatibility: Mapping[str, Any]


_PLATFORMS: dict[str, PlatformRegistration] = {}


def register_platform(registration: PlatformRegistration) -> None:
    if not isinstance(registration, PlatformRegistration):
        raise TypeError("platform registration must be PlatformRegistration")
    if not _PROFILE.fullmatch(registration.name):
        raise ValueError("platform registration name is invalid")
    if registration.participant_kind not in ("nunchi-owned", "native-host"):
        raise ValueError("platform participant_kind is invalid")
    if registration.name in _PLATFORMS and _PLATFORMS[registration.name] != registration:
        raise ValueError(f"platform {registration.name!r} is already registered differently")
    _PLATFORMS[registration.name] = registration


def _builtin_platforms() -> None:
    reaction_all = {
        "reaction": {"supported": True, "operations": ["add", "remove"], "reactions": ["*"]},
        "message": True,
        "reply": True,
    }
    for name, participant_kind, capabilities, compatibility in (
        (
            "channel",
            "nunchi-owned",
            reaction_all,
            {"status": "reference", "operator_managed": True},
        ),
        (
            "discord",
            "nunchi-owned",
            reaction_all,
            {"status": "reference", "operator_managed": True},
        ),
        (
            "matrix",
            "nunchi-owned",
            {
                "reaction": {"supported": True, "operations": ["add"], "reactions": ["*"]},
                "message": True,
                "reply": True,
            },
            {"status": "reference", "operator_managed": True},
        ),
        (
            "telegram",
            "nunchi-owned",
            {
                "reaction": {"supported": False, "operations": [], "reactions": []},
                "message": True,
                "reply": True,
            },
            {"status": "reference", "operator_managed": True},
        ),
        (
            "codex",
            "nunchi-owned",
            reaction_all,
            {"status": "adapter-required", "operator_managed": True},
        ),
        (
            "claude-code",
            "nunchi-owned",
            reaction_all,
            {"status": "adapter-required", "operator_managed": True},
        ),
        (
            "hermes",
            "native-host",
            {
                "reaction": {"supported": False, "operations": [], "reactions": []},
                "message": True,
                "reply": True,
            },
            {
                "status": "adapter-required",
                "operator_managed": False,
                "detail": "native participant host keeps its normal WAKE turn",
            },
        ),
    ):
        register_platform(
            PlatformRegistration(
                name=name,
                participant_kind=participant_kind,
                capabilities=deepcopy(capabilities),
                compatibility=deepcopy(compatibility),
            )
        )


_builtin_platforms()


def registered_platforms() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "participant_kind": item.participant_kind,
            "capabilities": deepcopy(dict(item.capabilities)),
            "compatibility": deepcopy(dict(item.compatibility)),
        }
        for name, item in sorted(_PLATFORMS.items())
    }


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"operator {label} must be non-empty")
    return value


def validate_profile_id(profile_id: str) -> str:
    if not isinstance(profile_id, str) or not _PROFILE.fullmatch(profile_id):
        raise ValidationError("profile_id must use 1-64 safe filename characters")
    return profile_id


def _model(value: Any, label: str) -> dict[str, Any]:
    required = {"provider", "model", "credential_env"}
    optional = {"base_url"}
    if not isinstance(value, Mapping) or required - set(value) or set(value) - (required | optional):
        raise ValidationError(f"operator {label} model has an invalid closed shape")
    result = dict(value)
    for name in result:
        _nonempty(result[name], f"{label} model {name}")
    credential_env = result["credential_env"]
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", credential_env):
        raise ValidationError(f"operator {label} credential_env is invalid")
    return result


def _room(value: Any, index: int) -> dict[str, Any]:
    required = {"platform", "room_id", "continuity_scope_id", "name", "enabled"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValidationError(f"operator rooms[{index}] has an invalid closed shape")
    result = dict(value)
    platform = _nonempty(result["platform"], f"rooms[{index}].platform")
    if platform not in _PLATFORMS:
        raise ValidationError(f"operator platform {platform!r} is not registered")
    for name in ("room_id", "continuity_scope_id", "name"):
        _nonempty(result[name], f"rooms[{index}].{name}")
    if not isinstance(result["enabled"], bool):
        raise ValidationError(f"operator rooms[{index}].enabled must be boolean")
    return result


def _service(value: Any, index: int) -> dict[str, Any]:
    required = {"name", "command", "restart", "environment"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValidationError(f"operator services[{index}] has an invalid closed shape")
    result = dict(value)
    if not isinstance(result["name"], str) or not _SERVICE.fullmatch(result["name"]):
        raise ValidationError(f"operator services[{index}].name is invalid")
    command = result["command"]
    if not isinstance(command, list) or not command or not all(
        isinstance(item, str) and item for item in command
    ):
        raise ValidationError(f"operator services[{index}].command must be non-empty strings")
    if result["restart"] not in ("never", "on-failure", "always"):
        raise ValidationError(f"operator services[{index}].restart is invalid")
    environment = result["environment"]
    if not isinstance(environment, Mapping) or any(
        not isinstance(key, str)
        or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key)
        or not isinstance(source, str)
        or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", source)
        for key, source in environment.items()
    ):
        raise ValidationError(
            f"operator services[{index}].environment must map variable names to source names"
        )
    return {**result, "command": list(command), "environment": dict(environment)}


def validate_operator_config(value: Any) -> dict[str, Any]:
    required = {
        "schema_version",
        "profile_id",
        "identity",
        "rooms",
        "models",
        "attention_policy",
        "ack_policy",
        "services",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValidationError("operator config has a missing or unexpected field")
    result = dict(value)
    if (
        isinstance(result["schema_version"], bool)
        or not isinstance(result["schema_version"], int)
        or result["schema_version"] != OPERATOR_SCHEMA_VERSION
    ):
        raise ValidationError(f"operator schema_version must be {OPERATOR_SCHEMA_VERSION}")
    profile_id = validate_profile_id(result["profile_id"])
    identity = result["identity"]
    identity_fields = {
        "participant_id",
        "actor_id",
        "display_name",
        "instructions",
        "provenance",
    }
    if not isinstance(identity, Mapping) or set(identity) != identity_fields:
        raise ValidationError("operator identity has an invalid closed shape")
    identity = dict(identity)
    for name in identity:
        _nonempty(identity[name], f"identity {name}")
    rooms = result["rooms"]
    if not isinstance(rooms, list) or not rooms:
        raise ValidationError("operator config requires at least one room")
    checked_rooms = [_room(room, index) for index, room in enumerate(rooms)]
    keys = [(room["platform"], room["room_id"]) for room in checked_rooms]
    if len(keys) != len(set(keys)):
        raise ValidationError("operator room bindings must be unique")
    models = result["models"]
    if not isinstance(models, Mapping) or set(models) != {"attention", "participant"}:
        raise ValidationError("operator models must contain attention and participant")
    checked_models = {
        "attention": _model(models["attention"], "attention"),
        "participant": _model(models["participant"], "participant"),
    }
    if not isinstance(result["attention_policy"], Mapping):
        raise ValidationError("operator attention_policy must be an object")
    try:
        attention_policy = AttentionPolicy(**dict(result["attention_policy"]))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"operator attention_policy is invalid: {exc}") from exc
    if not isinstance(result["ack_policy"], Mapping):
        raise ValidationError("operator ack_policy must be an object")
    try:
        ack_policy = AckPolicy(**dict(result["ack_policy"]))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"operator ack_policy is invalid: {exc}") from exc
    services = result["services"]
    if not isinstance(services, list):
        raise ValidationError("operator services must be an array")
    checked_services = [_service(item, index) for index, item in enumerate(services)]
    if len({item["name"] for item in checked_services}) != len(checked_services):
        raise ValidationError("operator service names must be unique")
    return {
        "schema_version": OPERATOR_SCHEMA_VERSION,
        "profile_id": profile_id,
        "identity": identity,
        "rooms": checked_rooms,
        "models": checked_models,
        "attention_policy": {
            name: getattr(attention_policy, name)
            for name in AttentionPolicy.__dataclass_fields__
        },
        "ack_policy": {
            name: getattr(ack_policy, name)
            for name in AckPolicy.__dataclass_fields__
        },
        "services": checked_services,
    }


def build_operator_config(
    *,
    profile_id: str,
    participant_id: str,
    actor_id: str,
    display_name: str,
    instructions: str,
    platform: str,
    room_id: str,
    room_name: str,
    continuity_scope_id: str,
    attention_model: str,
    participant_model: str,
    attention_provider: str = "openai-compatible",
    participant_provider: str = "openai-compatible",
    attention_credential_env: str = "NUNCHI_ATTENTION_API_KEY",
    participant_credential_env: str = "NUNCHI_PARTICIPANT_API_KEY",
    ack_enabled: bool = True,
    ack_reaction: str = "👂",
    services: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the shared schema from guided fields; no hand-written JSON."""

    return validate_operator_config(
        {
            "schema_version": OPERATOR_SCHEMA_VERSION,
            "profile_id": profile_id,
            "identity": {
                "participant_id": participant_id,
                "actor_id": actor_id,
                "display_name": display_name,
                "instructions": instructions,
                "provenance": f"operator:{profile_id}@1",
            },
            "rooms": [
                {
                    "platform": platform,
                    "room_id": room_id,
                    "continuity_scope_id": continuity_scope_id,
                    "name": room_name,
                    "enabled": True,
                }
            ],
            "models": {
                "attention": {
                    "provider": attention_provider,
                    "model": attention_model,
                    "credential_env": attention_credential_env,
                },
                "participant": {
                    "provider": participant_provider,
                    "model": participant_model,
                    "credential_env": participant_credential_env,
                },
            },
            "attention_policy": {
                name: getattr(AttentionPolicy(), name)
                for name in AttentionPolicy.__dataclass_fields__
            },
            "ack_policy": {
                "enabled": ack_enabled,
                "reaction": ack_reaction,
                "provenance": f"trusted:ack-policy/{profile_id}@1",
            },
            "services": [dict(item) for item in services],
        }
    )


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError(f"short write to {path}")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@dataclass(frozen=True)
class OperatorPaths:
    config_root: Path
    state_root: Path
    profile_id: str

    @property
    def config_directory(self) -> Path:
        return self.config_root / "profiles" / self.profile_id

    @property
    def state_directory(self) -> Path:
        return self.state_root / "profiles" / self.profile_id

    @property
    def config(self) -> Path:
        return self.config_directory / "config.json"

    @property
    def digest(self) -> Path:
        return self.config_directory / "config.sha256"

    @property
    def profile(self) -> Path:
        return self.config_directory / "participant-profile.json"

    @property
    def profile_digest(self) -> Path:
        return self.config_directory / "participant-profile.sha256"

    @property
    def revisions(self) -> Path:
        return self.config_directory / "revisions"


class OperatorStore:
    def __init__(self, config_root: str | Path, state_root: str | Path, profile_id: str) -> None:
        self.paths = OperatorPaths(
            Path(config_root).expanduser(),
            Path(state_root).expanduser(),
            validate_profile_id(profile_id),
        )

    def initialize(self) -> dict[str, Any]:
        result = initialize(self.paths.config_root, self.paths.state_root)
        for path in (
            self.paths.config_directory,
            self.paths.state_directory,
            self.paths.revisions,
        ):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.chmod(0o700)
        return result

    @contextmanager
    def _lock(self, *, exclusive: bool = True) -> Iterator[None]:
        self.paths.config_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.paths.config_directory / ".config.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_unlocked(self) -> tuple[dict[str, Any], str]:
        try:
            raw = self.paths.config.read_bytes()
        except OSError as exc:
            raise ValidationError(f"operator profile is not configured: {exc}") from exc
        if len(raw) > _MAX_CONFIG_BYTES:
            raise ValidationError("operator config exceeds the bounded size")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"operator config is invalid JSON: {exc.msg}") from exc
        if isinstance(document, Mapping) and set(document) == {"digest", "config"}:
            expected = document["digest"]
            candidate = document["config"]
            payload = _canonical(candidate)
        else:
            # Read the candidate build's split form only to migrate it safely
            # on the next write. New commits always use the atomic envelope.
            try:
                expected = self.paths.digest.read_text(encoding="ascii").strip()
            except OSError as exc:
                raise ValidationError(f"operator profile is not configured: {exc}") from exc
            candidate = document
            payload = raw
        if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
            raise ValidationError("operator config or digest is untrustworthy")
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise ValidationError("operator config does not match its automatic integrity pin")
        checked = validate_operator_config(candidate)
        if checked["profile_id"] != self.paths.profile_id:
            raise ValidationError("operator config belongs to another profile")
        return checked, actual

    def read(self) -> tuple[dict[str, Any], str]:
        if not self.paths.config_directory.exists():
            raise ValidationError("operator profile is not configured")
        with self._lock(exclusive=False):
            return self._read_unlocked()

    def write(
        self,
        document: Mapping[str, Any],
        *,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        checked = validate_operator_config(document)
        if checked["profile_id"] != self.paths.profile_id:
            raise ValidationError("operator write targets another profile")
        payload = _canonical(checked)
        if len(payload) > _MAX_CONFIG_BYTES:
            raise ValidationError("operator config exceeds the bounded size")
        revision = hashlib.sha256(payload).hexdigest()
        committed_payload = _canonical({"digest": revision, "config": checked})
        self.initialize()
        with self._lock():
            current_revision = None
            current_config = None
            if self.paths.config.exists():
                current_config, current_revision = self._read_unlocked()
            if expected_revision is not None and expected_revision != current_revision:
                raise ValidationError("operator config changed since it was read")
            if current_revision is not None:
                revision_path = self.paths.revisions / f"{current_revision}.json"
                if not revision_path.exists():
                    assert current_config is not None
                    _atomic_write(revision_path, _canonical(current_config))
            _atomic_write(self.paths.config, committed_payload)
            for legacy_path in (
                self.paths.digest,
                self.paths.profile,
                self.paths.profile_digest,
            ):
                try:
                    legacy_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return {
            "status": "configured",
            "profile_id": self.paths.profile_id,
            "revision": revision,
            "config_path": str(self.paths.config),
        }

    def rollback(self, revision: str) -> dict[str, Any]:
        if not _SHA256.fullmatch(revision):
            raise ValidationError("rollback revision must be a sha256 digest")
        path = self.paths.revisions / f"{revision}.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"rollback revision is unavailable: {exc}") from exc
        _, current = self.read()
        return self.write(document, expected_revision=current)

    def uninstall(self) -> dict[str, Any]:
        """Remove exactly one validated profile; shared installation remains."""

        validate_profile_id(self.paths.profile_id)
        config, _ = self.read()
        services = ServiceManager(self)
        for definition in config["services"]:
            stopped = services.stop(definition["name"])
            if stopped["status"] == "stop-timeout":
                raise ValidationError(
                    f"service {definition['name']!r} did not stop; profile was preserved"
                )
            persistent_path, _ = services.render_persistent_definition(
                definition["name"]
            )
            if persistent_path.exists():
                services.uninstall_persistent(definition["name"])
        removed = []
        for path in (self.paths.config_directory, self.paths.state_directory):
            boundary = path.parent.resolve()
            resolved = path.resolve()
            if resolved.parent != boundary:
                raise ValidationError("profile uninstall target escaped its boundary")
            if path.exists():
                shutil.rmtree(path)
                removed.append(str(path))
        return {"status": "uninstalled", "profile_id": self.paths.profile_id, "removed": removed}

    def recent_receipts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValidationError("receipt limit must be within 1..500")
        records: list[dict[str, Any]] = []
        if not self.paths.state_directory.exists():
            return records
        for path in sorted(self.paths.state_directory.rglob("*.jsonl")):
            if "receipt" not in path.name:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines[-limit:]:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, Mapping):
                    records.append({"source": str(path.relative_to(self.paths.state_directory)), **dict(value)})
        return records[-limit:]

    def snapshot(self, *, receipt_limit: int = 50) -> dict[str, Any]:
        config, revision = self.read()
        services = ServiceManager(self).status_all()
        room_capabilities: dict[str, Any] = {}
        compatibility: dict[str, Any] = {}
        warnings = []
        ack = config["ack_policy"]
        for room in config["rooms"]:
            platform = _PLATFORMS[room["platform"]]
            key = f"{room['platform']}:{room['room_id']}"
            capability = deepcopy(dict(platform.capabilities))
            room_capabilities[key] = capability
            compatibility[key] = deepcopy(dict(platform.compatibility))
            reaction = capability["reaction"]
            if ack["enabled"] and (
                not reaction["supported"]
                or (
                    "*" not in reaction["reactions"]
                    and ack["reaction"] not in reaction["reactions"]
                )
            ):
                warnings.append(
                    {
                        "room": key,
                        "feature": "ACK",
                        "behavior": "DEFER",
                        "detail": "configured native reaction is unavailable",
                    }
                )
        credentials = {
            name: {
                "environment": model["credential_env"],
                "state": "present" if os.environ.get(model["credential_env"]) else "absent",
            }
            for name, model in config["models"].items()
        }
        for name, credential in credentials.items():
            if credential["state"] == "absent":
                warnings.append(
                    {
                        "feature": "credential",
                        "model": name,
                        "behavior": "unavailable",
                        "detail": f"{credential['environment']} is absent",
                    }
                )
        for service in services:
            if service["desired"] == "running" and not service["running"]:
                warnings.append(
                    {
                        "feature": "service",
                        "service": service["name"],
                        "behavior": "not-running",
                        "detail": (
                            "configured always-running service has an orphaned child"
                            if service["orphaned_child"]
                            else "configured always-running service is stopped"
                        ),
                    }
                )
        return {
            "schema_version": OPERATOR_SCHEMA_VERSION,
            "product": "nunchi",
            "product_version": __version__,
            "profile_id": self.paths.profile_id,
            "revision": revision,
            "config": config,
            "capabilities": room_capabilities,
            "compatibility": compatibility,
            "health": {
                "configuration": "valid",
                "credentials": credentials,
                "services": services,
                "warnings": warnings,
            },
            "recent_receipts": self.recent_receipts(limit=receipt_limit),
        }

    def diagnose(self) -> dict[str, Any]:
        installed = verify(self.paths.config_root)
        snapshot = self.snapshot()
        return {
            "status": "healthy" if not snapshot["health"]["warnings"] else "attention",
            "install": installed,
            **snapshot,
        }


def _pid_alive(pid: int) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        return False
    with _LOCAL_SUPERVISORS_LOCK:
        local = _LOCAL_SUPERVISORS.get(pid)
        if local is not None:
            if local.poll() is None:
                return True
            _LOCAL_SUPERVISORS.pop(pid, None)
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ServiceManager:
    def __init__(self, store: OperatorStore) -> None:
        self.store = store
        self.root = store.paths.state_directory / "services"

    def _definition(self, name: str) -> tuple[dict[str, Any], str]:
        if not _SERVICE.fullmatch(name):
            raise ValidationError("service name is invalid")
        config, revision = self.store.read()
        for service in config["services"]:
            if service["name"] == name:
                return service, revision
        raise ValidationError(f"service {name!r} is not configured")

    def _directory(self, name: str) -> Path:
        if not _SERVICE.fullmatch(name):
            raise ValidationError("service name is invalid")
        return self.root / name

    def _pidfile(self, name: str) -> Path:
        return self._directory(name) / "supervisor.json"

    def _persistent_environment_path(self, name: str) -> Path:
        return self._directory(name) / "persistent-environment.json"

    def _write_persistent_environment(self, name: str) -> Path:
        definition, _ = self._definition(name)
        values: dict[str, str] = {}
        for source in sorted(set(definition["environment"].values())):
            value = os.environ.get(source)
            if value is None:
                raise ValidationError(
                    f"persistent service environment source {source} is absent"
                )
            values[source] = value
        path = self._persistent_environment_path(name)
        _atomic_write(path, _canonical(values), mode=0o600)
        return path

    def _supervisor_lock_held(self, name: str) -> bool:
        """Return whether an exact live supervisor owns its durable lock."""

        if fcntl is None:
            return False
        lock_path = self._directory(name) / "supervisor.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)

    def _runtime(self, name: str) -> dict[str, Any]:
        try:
            value = json.loads(
                (self._directory(name) / "status.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, Mapping) else {}

    @contextmanager
    def _control(self, name: str) -> Iterator[None]:
        """Serialize start/stop/restart/reset for one exact profile service."""

        directory = self._directory(name)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(directory / ".control.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_pidfile(self, name: str) -> dict[str, Any] | None:
        try:
            value = json.loads(self._pidfile(name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return {"state": "untrustworthy"}
        required = {
            "schema_version",
            "pid",
            "profile_id",
            "service",
            "config_revision",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != required
            or isinstance(value.get("schema_version"), bool)
            or not isinstance(value.get("schema_version"), int)
            or value.get("schema_version") != 1
            or isinstance(value.get("pid"), bool)
            or not isinstance(value.get("pid"), int)
            or value["pid"] < 1
            or value.get("profile_id") != self.store.paths.profile_id
            or value.get("service") != name
            or not isinstance(value.get("config_revision"), str)
            or not _SHA256.fullmatch(value["config_revision"])
        ):
            return {"state": "untrustworthy"}
        return dict(value)

    def status(self, name: str) -> dict[str, Any]:
        definition, revision = self._definition(name)
        state = self._read_pidfile(name)
        pid = state.get("pid") if isinstance(state, Mapping) else None
        lock_held = self._supervisor_lock_held(name)
        running = lock_held and _pid_alive(pid)
        runtime = self._runtime(name)
        child_pid = runtime.get("child_pid")
        orphaned_child = (
            not lock_held
            and not isinstance(child_pid, bool)
            and isinstance(child_pid, int)
            and _pid_alive(child_pid)
        )
        return {
            "name": name,
            "desired": "running" if definition["restart"] == "always" else "stopped",
            "running": running,
            "pid": pid if running else None,
            "orphaned_child": orphaned_child,
            "config_revision": revision,
            "restart_policy": definition["restart"],
            "runtime": runtime,
        }

    def status_all(self) -> list[dict[str, Any]]:
        config, _ = self.store.read()
        return [self.status(item["name"]) for item in config["services"]]

    def _start_locked(self, name: str) -> dict[str, Any]:
        self._definition(name)
        current = self.status(name)
        if current["running"]:
            return {"status": "already-running", **current}
        if current["orphaned_child"]:
            return {"status": "orphaned-child", **current}
        directory = self._directory(name)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        log = directory / "service.log"
        command = [
            sys.executable,
            "-m",
            "nunchi.service_worker",
            "--config-root",
            str(self.store.paths.config_root),
            "--state-root",
            str(self.store.paths.state_root),
            "--profile",
            self.store.paths.profile_id,
            "--service",
            name,
        ]
        worker_environment = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[1])
        inherited_pythonpath = worker_environment.get("PYTHONPATH")
        worker_environment["PYTHONPATH"] = (
            package_root
            if not inherited_pythonpath
            else package_root + os.pathsep + inherited_pythonpath
        )
        with log.open("ab", buffering=0) as output:
            process = subprocess.Popen(
                command,
                env=worker_environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        with _LOCAL_SUPERVISORS_LOCK:
            _LOCAL_SUPERVISORS[process.pid] = process
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            current = self.status(name)
            if current["running"] and current["runtime"].get("state") == "running":
                return {"status": "started", **current}
            if process.poll() is not None:
                break
            time.sleep(0.025)
        if process.poll() is None:
            process.terminate()
        return {
            "status": "start-failed",
            **self.status(name),
            "detail": "service supervisor did not reach running state",
            "log_tail": self.logs(name, lines=20)["lines"],
        }

    def start(self, name: str) -> dict[str, Any]:
        with self._control(name):
            return self._start_locked(name)

    def _signal_locked(self, name: str, *, timeout: float = 10.0) -> dict[str, Any]:
        state = self._read_pidfile(name)
        pid = state.get("pid") if isinstance(state, Mapping) else None
        if not self._supervisor_lock_held(name) or not _pid_alive(pid):
            self._pidfile(name).unlink(missing_ok=True)
            return {"status": "already-stopped", **self.status(name)}
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + timeout
        while _pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if _pid_alive(pid):
            return {"status": "stop-timeout", **self.status(name)}
        self._pidfile(name).unlink(missing_ok=True)
        return {"status": "stopped", **self.status(name)}

    def stop(self, name: str) -> dict[str, Any]:
        with self._control(name):
            return self._signal_locked(name)

    def restart(self, name: str) -> dict[str, Any]:
        with self._control(name):
            stopped = self._signal_locked(name)
            if stopped["status"] == "stop-timeout":
                return stopped
            return self._start_locked(name)

    def logs(self, name: str, *, lines: int = 100) -> dict[str, Any]:
        if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= 1000:
            raise ValidationError("service log lines must be within 1..1000")
        path = self._directory(name) / "service.log"
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            content = []
        return {"name": name, "lines": content[-lines:]}

    def reset(self, name: str) -> dict[str, Any]:
        with self._control(name):
            stopped = self._signal_locked(name)
            if stopped["status"] == "stop-timeout":
                return {"status": "reset-timeout", "name": name, "removed": []}
            directory = self._directory(name)
            removed = []
            for filename in ("control", "status.json", "supervisor.json"):
                path = directory / filename
                if path.exists():
                    path.unlink()
                    removed.append(filename)
        # Durable ACK and receipt journals deliberately live outside this
        # ephemeral service directory and survive reset.
        return {"status": "reset", "name": name, "removed": removed}

    def render_persistent_definition(self, name: str, *, platform: str | None = None) -> tuple[Path, bytes]:
        self._definition(name)
        operating_system = platform or sys.platform
        base_command = [
            sys.executable,
            "-m",
            "nunchi.service_worker",
            "--config-root",
            str(self.store.paths.config_root),
            "--state-root",
            str(self.store.paths.state_root),
            "--profile",
            self.store.paths.profile_id,
            "--service",
            name,
            "--environment-file",
            str(self._persistent_environment_path(name)),
        ]
        safe_profile = self.store.paths.profile_id
        if operating_system == "darwin":
            import plistlib

            path = Path.home() / "Library" / "LaunchAgents" / f"dev.nunchi.{safe_profile}.{name}.plist"
            payload = plistlib.dumps(
                {
                    "Label": f"dev.nunchi.{safe_profile}.{name}",
                    "ProgramArguments": base_command,
                    "RunAtLoad": True,
                    # The worker owns the configured restart policy. An outer
                    # always-restart loop would turn `never` into `always`.
                    "KeepAlive": False,
                    "ProcessType": "Background",
                },
                sort_keys=True,
            )
            return path, payload
        if operating_system.startswith("linux"):
            path = Path.home() / ".config" / "systemd" / "user" / f"nunchi-{safe_profile}-{name}.service"
            quoted = " ".join(json.dumps(item) for item in base_command)
            payload = (
                "[Unit]\nDescription=Nunchi profile service\n\n"
                "[Service]\nType=simple\nRestart=no\n"
                f"ExecStart={quoted}\n\n[Install]\nWantedBy=default.target\n"
            ).encode("utf-8")
            return path, payload
        raise ValidationError("persistent services require launchd or systemd user services")

    @staticmethod
    def _service_control(command: list[str], *, required: bool = True) -> None:
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if required:
                raise ValidationError(
                    f"persistent service control could not run {command[0]}: {exc}"
                ) from exc
            return
        if required and completed.returncode != 0:
            detail = (completed.stdout or "").strip()[-1000:]
            raise ValidationError(
                f"persistent service control failed ({command[0]}): {detail or completed.returncode}"
            )

    def install_persistent(self, name: str) -> dict[str, Any]:
        environment_path = self._write_persistent_environment(name)
        path, payload = self.render_persistent_definition(name)
        _atomic_write(path, payload, mode=0o600)
        if sys.platform == "darwin":
            domain = f"gui/{os.getuid()}"
            label = f"dev.nunchi.{self.store.paths.profile_id}.{name}"
            self._service_control(["/bin/launchctl", "bootout", f"{domain}/{label}"], required=False)
            self._service_control(["/bin/launchctl", "bootstrap", domain, str(path)])
            self._service_control(["/bin/launchctl", "enable", f"{domain}/{label}"])
            self._service_control(["/bin/launchctl", "kickstart", "-k", f"{domain}/{label}"])
        elif sys.platform.startswith("linux"):
            systemctl = shutil.which("systemctl") or "systemctl"
            self._service_control([systemctl, "--user", "daemon-reload"])
            self._service_control([systemctl, "--user", "enable", "--now", path.name])
        else:  # render_persistent_definition normally rejects this first.
            raise ValidationError("persistent services require launchd or systemd user services")
        return {
            "status": "installed",
            "name": name,
            "definition": str(path),
            "environment": str(environment_path),
            "activated": True,
        }

    def uninstall_persistent(self, name: str) -> dict[str, Any]:
        path, _ = self.render_persistent_definition(name)
        existed = path.exists()
        if sys.platform == "darwin":
            domain = f"gui/{os.getuid()}"
            label = f"dev.nunchi.{self.store.paths.profile_id}.{name}"
            self._service_control(["/bin/launchctl", "bootout", f"{domain}/{label}"], required=False)
        elif sys.platform.startswith("linux"):
            systemctl = shutil.which("systemctl") or "systemctl"
            self._service_control(
                [systemctl, "--user", "disable", "--now", path.name],
                required=False,
            )
        path.unlink(missing_ok=True)
        environment_path = self._persistent_environment_path(name)
        environment_path.unlink(missing_ok=True)
        if sys.platform.startswith("linux"):
            self._service_control([systemctl, "--user", "daemon-reload"])
        return {
            "status": "uninstalled",
            "name": name,
            "removed": existed,
            "environment": str(environment_path),
            "deactivated": True,
        }


def verify_install_and_profile(store: OperatorStore) -> dict[str, Any]:
    return {"install": verify(store.paths.config_root), "snapshot": store.snapshot()}
