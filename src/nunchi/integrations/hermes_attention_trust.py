"""Operator-owned stock Hermes attention permissions, never runtime grants.

Only an explicit dashboard save calls the transaction. Reads return structural
status, not host config values (which may include credentials).
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterator

from nunchi.errors import ValidationError
from nunchi.attention import HostAttentionPermissionError


TRUST_REPAIR = HostAttentionPermissionError.detail


def _read_host_config(path: Path) -> tuple[bytes | None, dict[str, Any]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if path.is_symlink():
            raise ValidationError("Hermes config.yaml must not be a symlink")
        return None, {}
    except OSError as exc:
        raise ValidationError("Hermes config.yaml is unavailable or symlinked") from exc
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or (
            hasattr(os, "getuid") and metadata.st_uid != os.getuid()
        ):
            raise ValidationError("Hermes config.yaml must be a regular file owned by the Hermes user")
        raw = handle.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValidationError("Hermes config.yaml is too large")
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError):
        try:
            try:
                import hermes_yaml as yaml  # use the installed host's YAML policy
            except ModuleNotFoundError as exc:
                if exc.name != "hermes_yaml":
                    raise  # a broken host dependency must not select another parser
                import yaml  # released hosts before hermes_yaml supply PyYAML
            document = yaml.safe_load(raw)
        except Exception as exc:
            raise ValidationError("Hermes config.yaml could not be parsed; repair it before saving Nunchi") from exc
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ValidationError("Hermes config.yaml must contain a mapping")
    return raw, document


def _llm_entry(document: dict[str, Any]) -> dict[str, Any]:
    current = document
    for key in ("plugins", "entries", "nunchi", "llm"):
        child = current.get(key, {})
        if not isinstance(child, dict):
            raise ValidationError("plugins.entries.nunchi.llm must contain mappings")
        # YAML aliases can share a mapping with another plugin. Detach each
        # edited node so granting Nunchi never grants that unrelated plugin.
        current[key] = dict(child)
        current = current[key]
    return current


def _required(config: Any) -> dict[str, Any]:
    providers = sorted({room.attention_model.provider for room in config.rooms})
    models = sorted({room.attention_model.model for room in config.rooms})
    if "*" in providers or "*" in models:
        raise ValidationError("attention trust setup requires exact provider and model names, not '*'")
    return {
        "allow_provider_override": True,
        "allow_model_override": True,
        "allowed_providers": providers,
        "allowed_models": models,
    }


def attention_trust_status(home: Path, config: Any) -> dict[str, Any]:
    """Read-only prerequisite check; never claims a model call succeeded."""
    result: dict[str, Any] = {
        "ready": False, "scope": "saved-configuration",
        "runtime_verified": False, "detail": TRUST_REPAIR,
    }
    if config is None:
        result["detail"] = "Complete Nunchi room setup before checking attention trust."
        return result
    try:
        _, document = _read_host_config(home / "config.yaml")
        llm = _llm_entry(document)
        required = _required(config)
        missing = []
        for kind in ("provider", "model"):
            permission = f"allow_{kind}_override"
            allowlist = f"allowed_{kind}s"
            if llm.get(permission) is not True:
                missing.append(permission)
            allowed = llm.get(allowlist)
            if isinstance(allowed, list):
                normalized = {v.strip().lower() for v in allowed if isinstance(v, str)}
                if "*" not in normalized and any(
                    v.strip().lower() not in normalized for v in required[allowlist]
                ):
                    missing.append(allowlist)
        result["missing"] = missing
        result["ready"] = not missing
        if not missing:
            result["detail"] = (
                "Saved host permissions allow the configured attention routes. "
                "This is not a provider, credential, quota or running-gateway health check."
            )
    except (OSError, ValidationError):
        result["detail"] = "Hermes config.yaml is unavailable or invalid. Repair it, then " + TRUST_REPAIR
    return result


@contextmanager
def attention_trust_transaction(
    home: Path, config: Any, *, lock_held: bool = False,
) -> Iterator[None]:
    """Back up and grant exact configured routes during an operator save.

    On a save exception restore the prior bytes, but never overwrite a concurrent
    host-config edit. Backups persist for operator rollback. A process crash can
    leave the narrow grant installed; repeat Save to reconcile with the pinned
    room config. No gateway or runtime reload is performed here.
    """
    from .hermes_dashboard_store import (
        _cross_process_config_lock, _fsync_directory,
        _publish_complete_file_exclusive, _write_staged,
    )

    home = home.resolve(strict=True)
    path = home / "config.yaml"
    with nullcontext() if lock_held else _cross_process_config_lock(home):
        raw, document = _read_host_config(path)
        desired = deepcopy(document)
        _llm_entry(desired).update(_required(config))
        if desired == document:
            yield
            return
        # JSON is a YAML subset and keeps this store dependency-free. Preserve
        # every unrelated value; retain original YAML bytes/comments in backup.
        try:
            encoded = (json.dumps(desired, indent=2, ensure_ascii=False) + "\n").encode()
        except (TypeError, ValueError) as exc:
            raise ValidationError("Hermes config.yaml contains non-JSON values; configure attention trust manually") from exc
        if raw is not None:
            backup = home / ("config.yaml.nunchi-backup-" + hashlib.sha256(raw).hexdigest())
            staged_backup = _write_staged(backup, raw)
            try:
                if backup.exists() or backup.is_symlink():
                    prior, _ = _read_host_config(backup)
                    if prior != raw:
                        raise ValidationError("Hermes attention trust backup does not match")
                else:
                    _publish_complete_file_exclusive(staged_backup, backup, label="Hermes attention trust backup")
                _fsync_directory(home)
            finally:
                staged_backup.unlink(missing_ok=True)
        staged = _write_staged(path, encoded)
        published = False
        try:
            if _read_host_config(path)[0] != raw:
                raise ValidationError("Hermes config.yaml changed during Nunchi save; reload and retry")
            os.replace(staged, path)
            published = True
            _fsync_directory(home)
            if _read_host_config(path)[0] != encoded:
                raise ValidationError("Hermes attention trust read-back failed")
            yield
        except BaseException:
            if published:
                if _read_host_config(path)[0] != encoded:
                    raise ValidationError("Hermes config.yaml changed during rollback; preserve the current file and restore the Nunchi backup manually")
                if raw is None:
                    path.unlink()
                else:
                    restore = _write_staged(path, raw)
                    try:
                        os.replace(restore, path)
                    finally:
                        restore.unlink(missing_ok=True)
                _fsync_directory(home)
            raise
        finally:
            staged.unlink(missing_ok=True)
