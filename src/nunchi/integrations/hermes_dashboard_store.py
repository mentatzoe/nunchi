"""Authenticated-dashboard storage for the Hermes V2 integration.

The Hermes dashboard supplies HTTP authentication. This module owns only
validated config reads/writes, optimistic concurrency, receipt reads, and
channel-directory discovery. It has no FastAPI or Hermes package dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from nunchi.errors import ValidationError
from nunchi.integrations.hermes_dashboard_install import default_hermes_home
from nunchi.integrations.hermes_v2 import (
    HermesConfigSource,
    HermesPluginConfig,
    _require_private_regular_file,
    load_pinned_config,
    resolve_config_source,
    room_state_directory,
)


logger = logging.getLogger(__name__)
_MAX_RECEIPT_READ_BYTES = 2 * 1024 * 1024
_AUDIT_NAME = "nunchi-dashboard-audit.jsonl"


class DashboardConfigError(ValidationError):
    """A dashboard config operation was rejected."""


class DashboardConfigConflict(DashboardConfigError):
    """The editor submitted a stale config revision."""


class DashboardConfigReadOnly(DashboardConfigError):
    """The config uses a literal digest that the dashboard cannot update."""


@dataclass(frozen=True)
class DashboardConfigSnapshot:
    profile: str
    source: HermesConfigSource
    document: dict[str, Any]
    config: HermesPluginConfig
    sha256: str

    def response(self) -> dict[str, Any]:
        return {
            "api_version": "2",
            "profile": self.profile,
            "path": str(self.source.path.resolve()),
            "sha256": self.sha256,
            "digest_path": (
                str(self.source.digest_path.resolve())
                if self.source.digest_path is not None
                else None
            ),
            "dashboard_writable": self.source.dashboard_writable,
            "document": self.document,
            "room_count": len(self.config.rooms),
            "restart_required_after_save": True,
        }


def active_hermes_profile() -> str:
    """Resolve the dashboard process's active Hermes profile."""

    try:
        from hermes_cli.profiles import get_active_profile_name

        value = get_active_profile_name()
        if isinstance(value, str) and value:
            return value
    except Exception:
        pass
    return "default"


def _decode_config(raw: bytes) -> dict[str, Any]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DashboardConfigError(
            f"Hermes V2 config is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(document, dict):
        raise DashboardConfigError("Hermes V2 config must be a JSON object")
    return document


def read_config_snapshot(
    profile: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> DashboardConfigSnapshot:
    source = resolve_config_source(profile, environ=environ)
    raw = _require_private_regular_file(source.path, "Hermes V2 config")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != source.expected_sha256:
        raise DashboardConfigError(
            "Hermes V2 config does not match its pinned digest"
        )
    document = _decode_config(raw)
    config = load_pinned_config(
        source.path,
        expected_sha256=actual,
        hermes_profile=profile,
    )
    return DashboardConfigSnapshot(
        profile=profile,
        source=source,
        document=document,
        config=config,
        sha256=actual,
    )


def _write_staged(path: Path, data: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    staged = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        staged.unlink(missing_ok=True)
        raise
    return staged


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_bytes(path: Path, data: bytes) -> None:
    staged = _write_staged(path, data)
    try:
        os.replace(staged, path)
        _fsync_directory(path.parent)
    finally:
        staged.unlink(missing_ok=True)


def _append_audit(
    *,
    source: HermesConfigSource,
    profile: str,
    old_sha256: str,
    new_sha256: str,
) -> None:
    audit_path = source.path.parent / _AUDIT_NAME
    record = json.dumps(
        {
            "event": "dashboard-config-write",
            "profile": profile,
            "config_path": str(source.path.resolve()),
            "old_sha256": old_sha256,
            "new_sha256": new_sha256,
            "pid": os.getpid(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(audit_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, record)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_config_document(
    profile: str,
    *,
    document: Mapping[str, Any],
    expected_sha256: str,
    environ: Mapping[str, str] | None = None,
) -> DashboardConfigSnapshot:
    """Validate and atomically replace a dashboard-managed V2 config.

    The digest sidecar is replaced before the config. A crash between those
    operations produces a safe digest mismatch, never silent activation of
    unpinned bytes. The dashboard restarts Hermes only after both replacements
    and the final read-back succeed.
    """

    current = read_config_snapshot(profile, environ=environ)
    if current.sha256 != expected_sha256:
        raise DashboardConfigConflict(
            "configuration changed after this dashboard page loaded"
        )
    digest_path = current.source.digest_path
    if digest_path is None:
        raise DashboardConfigReadOnly(
            "dashboard writes require NUNCHI_HERMES_V2_CONFIG_SHA256_FILE "
            "or an adjacent <config>.sha256 file"
        )
    if (
        current.source.path.parent.resolve()
        != digest_path.parent.resolve()
    ):
        raise DashboardConfigReadOnly(
            "dashboard-managed config and digest files must share one directory"
        )
    if not isinstance(document, Mapping):
        raise DashboardConfigError("configuration must be a JSON object")
    try:
        encoded = (
            json.dumps(
                dict(document),
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode()
    except (TypeError, ValueError) as exc:
        raise DashboardConfigError(
            "configuration must contain only JSON values"
        ) from exc
    new_sha256 = hashlib.sha256(encoded).hexdigest()
    config_staged = _write_staged(current.source.path, encoded)
    digest_staged = _write_staged(
        digest_path,
        f"{new_sha256}\n".encode("ascii"),
    )
    old_digest_bytes = _require_private_regular_file(
        digest_path,
        "Hermes V2 config digest",
    )
    try:
        load_pinned_config(
            config_staged,
            expected_sha256=new_sha256,
            hermes_profile=profile,
        )
        os.replace(digest_staged, digest_path)
        try:
            os.replace(config_staged, current.source.path)
        except Exception:
            _replace_bytes(digest_path, old_digest_bytes)
            raise
        _fsync_directory(current.source.path.parent)
    finally:
        config_staged.unlink(missing_ok=True)
        digest_staged.unlink(missing_ok=True)

    updated = read_config_snapshot(profile, environ=environ)
    if updated.sha256 != new_sha256:
        raise DashboardConfigError(
            "configuration read-back did not match the committed bytes"
        )
    try:
        _append_audit(
            source=current.source,
            profile=profile,
            old_sha256=current.sha256,
            new_sha256=new_sha256,
        )
    except OSError:
        logger.exception("could not append the Nunchi dashboard audit record")
    return updated


def _hermes_home(environ: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environ is None else environ
    configured = environment.get("HERMES_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    if environ is not None:
        return Path.home() / ".hermes"
    return default_hermes_home()


def channel_directory(
    *,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    path = _hermes_home(environ) / "channel_directory.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(document, Mapping):
        return []
    result: list[dict[str, str]] = []
    platforms = document.get("platforms")
    if not isinstance(platforms, Mapping):
        return result
    for platform, entries in platforms.items():
        if not isinstance(platform, str) or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            room_id = str(entry.get("id") or "").strip()
            name = str(entry.get("name") or "").strip()
            if not room_id:
                continue
            result.append(
                {
                    "platform": platform,
                    "id": room_id,
                    "name": name or room_id,
                    "guild": str(entry.get("guild") or "").strip(),
                }
            )
    return sorted(
        result,
        key=lambda row: (
            row["platform"],
            row["guild"].casefold(),
            row["name"].casefold(),
            row["id"],
        ),
    )


def _tail_json_objects(path: Path, *, limit: int) -> list[dict[str, Any]]:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            return []
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - _MAX_RECEIPT_READ_BYTES))
            data = handle.read()
    except OSError:
        return []
    if size > len(data):
        _, _, data = data.partition(b"\n")
    result: list[dict[str, Any]] = []
    for raw_line in reversed(data.splitlines()):
        try:
            value = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            result.append(value)
        if len(result) >= limit:
            break
    return result


def read_receipts(
    profile: str,
    *,
    limit: int = 100,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise DashboardConfigError("receipt limit must be within [1, 500]")
    snapshot = read_config_snapshot(profile, environ=environ)
    receipts: list[dict[str, Any]] = []
    for room in snapshot.config.rooms:
        directory = room_state_directory(
            snapshot.config.state_directory,
            profile=profile,
            binding=room.binding,
        )
        for receipt in _tail_json_objects(
            directory / "receipts.jsonl",
            limit=limit,
        ):
            receipt["_nunchi_room"] = {
                "platform": room.binding.platform,
                "room_id": room.binding.room_id,
                "participant_id": room.binding.participant_id,
            }
            receipts.append(receipt)
    receipts.sort(
        key=lambda item: str(
            item.get("created_at")
            or item.get("timestamp")
            or item.get("ts")
            or ""
        ),
        reverse=True,
    )
    return {
        "receipts": receipts[:limit],
        "config_sha256": snapshot.sha256,
    }
