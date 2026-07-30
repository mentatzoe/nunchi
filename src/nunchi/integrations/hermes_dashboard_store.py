"""Authenticated-dashboard storage for the Hermes V2 integration.

The Hermes dashboard supplies HTTP authentication. This module owns only
validated config reads/writes, optimistic concurrency, receipt reads, and
channel-directory discovery. It has no FastAPI or Hermes package dependency.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
from typing import Any

from nunchi.errors import ValidationError
from nunchi.integrations.hermes_dashboard_install import default_hermes_home
from nunchi.integrations.hermes_v2 import (
    HermesConfigSource,
    HermesPluginConfig,
    _config_backup_path,
    _recoverable_config_path,
    _require_private_regular_file,
    load_pinned_config,
    resolve_config_source,
    room_state_directory,
)


logger = logging.getLogger(__name__)
_MAX_RECEIPT_READ_BYTES = 2 * 1024 * 1024
_AUDIT_NAME = "nunchi-dashboard-audit.jsonl"
_PROFILE_PREFIX = re.compile(r"[^a-z0-9]+")
_CONFIG_WRITE_LOCK = threading.Lock()


class DashboardConfigError(ValidationError):
    """A dashboard config operation was rejected."""


class DashboardConfigConflict(DashboardConfigError):
    """The editor submitted a stale config revision."""


class DashboardConfigReadOnly(DashboardConfigError):
    """The config uses a literal digest that the dashboard cannot update."""


@dataclass(frozen=True)
class DashboardDefaultPaths:
    """Private, profile-scoped paths used when no env config is set."""

    config: Path
    digest: Path
    state_directory: Path


@dataclass(frozen=True)
class DashboardConfigSnapshot:
    profile: str
    source: HermesConfigSource
    document: dict[str, Any]
    config: HermesPluginConfig | None
    sha256: str | None
    revision: str
    validation_error: str | None = None
    bootstrap_required: bool = False
    bootstrap_recovery: bool = False
    update_recovery: bool = False

    def response(self) -> dict[str, Any]:
        rooms = self.document.get("rooms")
        configuration_loadable = (
            self.config is not None and not self.bootstrap_required
        )
        return {
            "api_version": "2",
            "profile": self.profile,
            "path": str(self.source.write_path.resolve()),
            "sha256": self.sha256,
            "revision": self.revision,
            "digest_path": (
                str(self.source.digest_path.resolve())
                if self.source.digest_path is not None
                else None
            ),
            "dashboard_writable": self.source.dashboard_writable,
            "document": self.document,
            "room_count": len(rooms) if isinstance(rooms, list) else 0,
            "configuration_valid": self.config is not None,
            "configuration_loadable": configuration_loadable,
            "validation_error": self.validation_error,
            "bootstrap_required": self.bootstrap_required,
            "bootstrap_recovery": self.bootstrap_recovery,
            "update_recovery": self.update_recovery,
            "setup_message": (
                (
                    "A first save was interrupted before activation. Review "
                    "the configuration and save again to repair it."
                    if self.bootstrap_recovery
                    else "Complete at least one room, then save to create the "
                    "private Nunchi configuration."
                )
                if self.bootstrap_required
                else (
                    "A later save was interrupted. Hermes is using the prior "
                    "pinned revision; review and save again to finish repair."
                    if self.update_recovery
                    else None
                )
            ),
            "restart_required_after_save": True,
        }


def active_hermes_profile() -> str:
    """Resolve the dashboard process's active Hermes profile."""

    try:
        from hermes_cli.profiles import get_active_profile_name
    except (ImportError, ModuleNotFoundError) as exc:
        raise DashboardConfigError(
            "Hermes active profile is unavailable"
        ) from exc
    try:
        value = get_active_profile_name()
    except Exception as exc:
        raise DashboardConfigError(
            "Hermes active profile could not be resolved"
        ) from exc
    if not isinstance(value, str) or not value.strip():
        raise DashboardConfigError(
            "Hermes active profile could not be resolved"
        )
    return value.strip()


def _profile_storage_key(profile: str) -> str:
    if not isinstance(profile, str) or not profile or len(profile) > 128:
        raise DashboardConfigError("invalid Hermes profile")
    try:
        profile_bytes = profile.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DashboardConfigError("invalid Hermes profile") from exc
    prefix = _PROFILE_PREFIX.sub("-", profile.lower()).strip("-")[:32].rstrip("-")
    if not prefix:
        prefix = "profile"
    suffix = hashlib.sha256(profile_bytes).hexdigest()[:12]
    return f"{prefix}-{suffix}"


def default_config_paths(
    profile: str,
    *,
    hermes_home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DashboardDefaultPaths:
    """Return the deterministic private paths for one exact Hermes profile."""

    if hermes_home is not None and environ is not None:
        raise DashboardConfigError("provide hermes_home or environ, not both")
    home = (
        Path(hermes_home).expanduser()
        if hermes_home is not None
        else _hermes_home(environ)
    ).resolve()
    directory = home / "nunchi" / "profiles" / _profile_storage_key(profile)
    config = directory / "config.json"
    return DashboardDefaultPaths(
        config=config,
        digest=Path(f"{config}.sha256"),
        state_directory=directory / "state",
    )


def _bootstrap_document(
    profile: str,
    *,
    paths: DashboardDefaultPaths,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "hermes_profile": profile,
        "state_directory": str(paths.state_directory),
        "rooms": [],
    }


def _bootstrap_revision(
    profile: str,
    *,
    paths: DashboardDefaultPaths,
) -> str:
    material = json.dumps(
        {
            "kind": "nunchi-dashboard-absent-config-v1",
            "profile": profile,
            "config": str(paths.config),
            "digest": str(paths.digest),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "absent:" + hashlib.sha256(material).hexdigest()


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


def _read_source_snapshot(
    profile: str,
    *,
    source: HermesConfigSource,
    allow_invalid: bool = False,
) -> DashboardConfigSnapshot:
    raw = _require_private_regular_file(source.path, "Hermes V2 config")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != source.expected_sha256:
        raise DashboardConfigError(
            "Hermes V2 config does not match its pinned digest"
        )
    document = _decode_config(raw)
    validation_error: str | None = None
    load_error: ValidationError | None = None
    try:
        config = load_pinned_config(
            source.path,
            expected_sha256=actual,
            hermes_profile=profile,
        )
    except ValidationError as exc:
        config = None
        load_error = exc
    confirmed = _require_private_regular_file(
        source.path,
        "Hermes V2 config",
    )
    if hashlib.sha256(confirmed).hexdigest() != actual:
        raise DashboardConfigError(
            "Hermes V2 config changed while the dashboard was reading it"
        )
    if load_error is not None:
        if not allow_invalid:
            raise load_error
        validation_error = str(load_error)
    revision = actual
    update_recovery = source.configured_path is not None
    if update_recovery:
        pending = _require_private_regular_file(
            source.configured_path,
            "interrupted Hermes V2 config update",
        )
        revision = (
            f"interrupted:{actual}:{hashlib.sha256(pending).hexdigest()}"
        )
    return DashboardConfigSnapshot(
        profile=profile,
        source=source,
        document=document,
        config=config,
        sha256=actual,
        revision=revision,
        validation_error=validation_error,
        update_recovery=update_recovery,
    )


def read_config_snapshot(
    profile: str,
    *,
    environ: Mapping[str, str] | None = None,
    allow_invalid: bool = False,
) -> DashboardConfigSnapshot:
    """Read an explicitly configured runtime source.

    This strict function retains the existing behavior used by receipt reads.
    Dashboard setup uses :func:`read_dashboard_snapshot`.
    """

    return _read_resolved_snapshot(
        profile,
        source_factory=lambda: resolve_config_source(
            profile,
            environ=environ,
        ),
        allow_invalid=allow_invalid,
    )


def _read_resolved_snapshot(
    profile: str,
    *,
    source_factory: Callable[[], HermesConfigSource],
    allow_invalid: bool,
) -> DashboardConfigSnapshot:
    """Read one consistent config revision across an atomic replacement."""

    for attempt in range(2):
        try:
            source = source_factory()
            return _read_source_snapshot(
                profile,
                source=source,
                allow_invalid=allow_invalid,
            )
        except ValidationError:
            if attempt:
                raise
    raise AssertionError("config snapshot retry loop did not return")


def _source_environment_is_set(
    profile: str,
    *,
    environ: Mapping[str, str] | None,
) -> bool:
    environment = os.environ if environ is None else environ
    token = re.sub(r"[^A-Za-z0-9]", "_", profile).upper()
    keys = [
        f"NUNCHI_HERMES_V2_CONFIG_{token}",
        f"NUNCHI_HERMES_V2_CONFIG_SHA256_{token}",
        f"NUNCHI_HERMES_V2_CONFIG_SHA256_FILE_{token}",
    ]
    if profile == "default":
        keys.extend(
            [
                "NUNCHI_HERMES_V2_CONFIG",
                "NUNCHI_HERMES_V2_CONFIG_SHA256",
                "NUNCHI_HERMES_V2_CONFIG_SHA256_FILE",
            ]
        )
    return any(environment.get(key, "").strip() for key in keys)


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DashboardConfigError(
            "default Nunchi configuration path is unavailable"
        ) from exc
    return True


def _default_source(paths: DashboardDefaultPaths) -> HermesConfigSource:
    raw_digest = _require_private_regular_file(
        paths.digest,
        "Hermes V2 config digest",
    )
    try:
        digest = raw_digest.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise DashboardConfigError(
            "Hermes V2 config digest file must contain ASCII"
        ) from exc
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise DashboardConfigError(
            "Hermes V2 config sha256 must be 64 lowercase hex"
        )
    readable_path, configured_path = _recoverable_config_path(
        paths.config,
        expected_sha256=digest,
    )
    return HermesConfigSource(
        path=readable_path,
        expected_sha256=digest,
        digest_path=paths.digest,
        configured_path=configured_path,
    )


def read_dashboard_snapshot(
    profile: str,
    *,
    environ: Mapping[str, str] | None = None,
    allow_invalid: bool = False,
) -> DashboardConfigSnapshot:
    """Read configured bytes or describe a safe first-run setup."""

    if _source_environment_is_set(profile, environ=environ):
        return read_config_snapshot(
            profile,
            environ=environ,
            allow_invalid=allow_invalid,
        )

    paths = default_config_paths(profile, environ=environ)
    config_exists = _path_entry_exists(paths.config)
    digest_exists = _path_entry_exists(paths.digest)
    if digest_exists and not config_exists:
        raise DashboardConfigError(
            "default Nunchi configuration has an orphan digest; remove the "
            "orphan digest or disable Nunchi before retrying setup"
        )
    if config_exists and digest_exists:
        return _read_resolved_snapshot(
            profile,
            source_factory=lambda: _default_source(paths),
            allow_invalid=allow_invalid,
        )
    if config_exists:
        raw = _require_private_regular_file(
            paths.config,
            "uncommitted Hermes V2 config",
        )
        actual = hashlib.sha256(raw).hexdigest()
        document = _decode_config(raw)
        validation_error: str | None = None
        try:
            config = load_pinned_config(
                paths.config,
                expected_sha256=actual,
                hermes_profile=profile,
            )
        except ValidationError as exc:
            if not allow_invalid:
                raise
            config = None
            validation_error = str(exc)
        return DashboardConfigSnapshot(
            profile=profile,
            source=HermesConfigSource(
                path=paths.config,
                expected_sha256=actual,
                digest_path=paths.digest,
            ),
            document=document,
            config=config,
            sha256=actual,
            revision=f"uncommitted:{actual}",
            validation_error=validation_error,
            bootstrap_required=True,
            bootstrap_recovery=True,
        )

    revision = _bootstrap_revision(profile, paths=paths)
    return DashboardConfigSnapshot(
        profile=profile,
        source=HermesConfigSource(
            path=paths.config,
            expected_sha256=revision,
            digest_path=paths.digest,
        ),
        document=_bootstrap_document(profile, paths=paths),
        config=None,
        sha256=None,
        revision=revision,
        bootstrap_required=True,
    )


def discord_runtime_status(
    snapshot: DashboardConfigSnapshot,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Describe the Discord behavior supplied by the installed Nunchi plugin."""

    environment = os.environ if environ is None else environ
    configuration_loadable = (
        snapshot.config is not None and not snapshot.bootstrap_required
    )
    if configuration_loadable:
        room_ids = sorted(
            room.binding.room_id
            for room in snapshot.config.rooms
            if room.binding.platform == "discord"
        )
    else:
        room_ids = []
    allow_bots = environment.get("DISCORD_ALLOW_BOTS", "none").strip().lower()
    if allow_bots not in {"none", "mentions", "all"}:
        allow_bots = "custom"
    return {
        "configured_room_ids": room_ids,
        "configuration_loadable": configuration_loadable,
        "natural_conversation_after_restart": bool(room_ids),
        "bot_admission_after_restart": (
            "configured-rooms" if room_ids else "not-configured"
        ),
        "missed_message_recovery_after_restart": (
            "configured-rooms" if room_ids else "not-configured"
        ),
        "mention_required_after_restart": False if room_ids else None,
        "auto_threading_after_restart": (
            "bypassed" if room_ids else "not-configured"
        ),
        "provided_by": "nunchi-runtime-shim",
        "profile_wide_hermes_allow_bots": allow_bots,
        "profile_wide_fallback_active": allow_bots in {"mentions", "all"},
        "restart_required_after_room_change": True,
    }


def _write_staged(path: Path, data: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    staged = Path(raw_path)
    try:
        if hasattr(os, "fchmod"):
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


def _prepare_private_directory(path: Path, label: str) -> None:
    try:
        path.mkdir(mode=0o700, exist_ok=True)
        metadata = path.lstat()
    except OSError as exc:
        raise DashboardConfigError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise DashboardConfigError(f"{label} must be a regular directory")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise DashboardConfigError(f"{label} must be owned by the Hermes user")
    if metadata.st_mode & 0o077:
        raise DashboardConfigError(
            f"{label} must not be accessible by group or other users"
        )


def _prepare_default_directories(paths: DashboardDefaultPaths) -> None:
    nunchi_directory = paths.config.parent.parent.parent
    profiles_directory = paths.config.parent.parent
    for path, label in (
        (nunchi_directory, "Nunchi data directory"),
        (profiles_directory, "Nunchi profile directory"),
        (paths.config.parent, "Nunchi Hermes profile directory"),
    ):
        _prepare_private_directory(path, label)


@contextmanager
def _cross_process_config_lock(directory: Path) -> Iterator[None]:
    """Serialize dashboard config commits across Hermes processes."""

    lock_path = directory / ".nunchi-dashboard-config.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise DashboardConfigError(
            "dashboard config lock is unavailable"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise DashboardConfigError(
                "dashboard config lock must be a regular file"
            )
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise DashboardConfigError(
                "dashboard config lock must be owned by the Hermes user"
            )
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        if metadata.st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)

        if os.name == "nt":  # pragma: no cover - exercised on Windows.
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)

            def unlock() -> None:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)

            def unlock() -> None:
                fcntl.flock(descriptor, fcntl.LOCK_UN)

        try:
            yield
        finally:
            unlock()
    finally:
        os.close(descriptor)


def _publish_complete_file_exclusive(
    source: Path,
    destination: Path,
    *,
    label: str,
) -> tuple[int, int]:
    """Atomically publish a complete private file without replacing a target."""

    try:
        source_metadata = source.lstat()
    except OSError as exc:
        raise DashboardConfigError(f"{label} source is unavailable") from exc
    if (
        stat.S_ISLNK(source_metadata.st_mode)
        or not stat.S_ISREG(source_metadata.st_mode)
        or source_metadata.st_mode & 0o077
    ):
        raise DashboardConfigError(
            f"{label} source must be a private regular file"
        )
    if hasattr(os, "getuid") and source_metadata.st_uid != os.getuid():
        raise DashboardConfigError(
            f"{label} source must be owned by the Hermes user"
        )
    identity = (source_metadata.st_dev, source_metadata.st_ino)
    try:
        os.link(source, destination, follow_symlinks=False)
    except FileExistsError as exc:
        raise DashboardConfigConflict(
            "configuration changed after this dashboard page loaded"
        ) from exc
    except OSError as exc:
        raise DashboardConfigError(
            f"{label} could not be published atomically"
        ) from exc
    try:
        published = destination.lstat()
        if (
            stat.S_ISLNK(published.st_mode)
            or not stat.S_ISREG(published.st_mode)
            or (published.st_dev, published.st_ino) != identity
        ):
            raise DashboardConfigError(
                f"{label} publication identity changed unexpectedly"
            )
    except Exception:
        _unlink_created(destination, identity)
        raise
    return identity


def _unlink_created(path: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISLNK(metadata.st_mode)
            and (metadata.st_dev, metadata.st_ino) == identity
        ):
            path.unlink()
    except FileNotFoundError:
        pass


def _append_audit(
    *,
    source: HermesConfigSource,
    profile: str,
    old_sha256: str,
    new_sha256: str,
) -> None:
    audit_path = source.write_path.parent / _AUDIT_NAME
    record = json.dumps(
        {
            "event": "dashboard-config-write",
            "profile": profile,
            "config_path": str(source.write_path.resolve()),
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
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        os.write(descriptor, record)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_config_document(
    profile: str,
    *,
    document: Mapping[str, Any],
    expected_sha256: str | None = None,
    expected_revision: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> DashboardConfigSnapshot:
    """Validate and commit a dashboard-managed V2 config."""

    if expected_revision is not None and expected_sha256 is not None:
        if expected_revision != expected_sha256:
            raise DashboardConfigError(
                "expected_revision and expected_sha256 disagree"
            )
    submitted_revision = expected_revision or expected_sha256
    if not submitted_revision:
        raise DashboardConfigError("expected_revision is required")

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

    with _CONFIG_WRITE_LOCK:
        if _source_environment_is_set(profile, environ=environ):
            preflight = read_dashboard_snapshot(
                profile,
                environ=environ,
                allow_invalid=True,
            )
            write_directory = preflight.source.write_path.parent
        else:
            default_paths = default_config_paths(profile, environ=environ)
            _prepare_default_directories(default_paths)
            write_directory = default_paths.config.parent
        _prepare_private_directory(
            write_directory,
            "dashboard-managed config directory",
        )
        with _cross_process_config_lock(write_directory):
            current = read_dashboard_snapshot(
                profile,
                environ=environ,
                allow_invalid=True,
            )
            if current.revision != submitted_revision:
                raise DashboardConfigConflict(
                    "configuration changed after this dashboard page loaded"
                )
            digest_path = current.source.digest_path
            config_path = current.source.write_path
            if digest_path is None:
                raise DashboardConfigReadOnly(
                    "dashboard writes require "
                    "NUNCHI_HERMES_V2_CONFIG_SHA256_FILE or an adjacent "
                    "<config>.sha256 file"
                )
            if (
                config_path.parent.resolve()
                != digest_path.parent.resolve()
            ):
                raise DashboardConfigReadOnly(
                    "dashboard-managed config and digest files must share "
                    "one directory"
                )

            config_staged = _write_staged(config_path, encoded)
            try:
                load_pinned_config(
                    config_staged,
                    expected_sha256=new_sha256,
                    hermes_profile=profile,
                )
                if current.bootstrap_required:
                    digest_staged = _write_staged(
                        digest_path,
                        f"{new_sha256}\n".encode("ascii"),
                    )
                    config_exists = _path_entry_exists(config_path)
                    digest_exists = _path_entry_exists(digest_path)
                    try:
                        if current.bootstrap_recovery:
                            if not config_exists or digest_exists:
                                raise DashboardConfigConflict(
                                    "configuration changed after this dashboard "
                                    "page loaded"
                                )
                            os.replace(config_staged, config_path)
                            _fsync_directory(config_path.parent)
                            _publish_complete_file_exclusive(
                                digest_staged,
                                digest_path,
                                label="Hermes V2 config digest",
                            )
                            _fsync_directory(config_path.parent)
                        else:
                            if config_exists or digest_exists:
                                raise DashboardConfigConflict(
                                    "configuration changed after this dashboard "
                                    "page loaded"
                                )
                            config_identity = (
                                _publish_complete_file_exclusive(
                                    config_staged,
                                    config_path,
                                    label="Hermes V2 config",
                                )
                            )
                            _fsync_directory(config_path.parent)
                            digest_identity: tuple[int, int] | None = None
                            try:
                                digest_identity = (
                                    _publish_complete_file_exclusive(
                                        digest_staged,
                                        digest_path,
                                        label="Hermes V2 config digest",
                                    )
                                )
                                _fsync_directory(config_path.parent)
                            except Exception:
                                if digest_identity is not None:
                                    _unlink_created(
                                        digest_path,
                                        digest_identity,
                                    )
                                _unlink_created(
                                    config_path,
                                    config_identity,
                                )
                                raise
                    finally:
                        digest_staged.unlink(missing_ok=True)
                else:
                    if current.sha256 is None:
                        raise DashboardConfigError(
                            "configured Nunchi revision has no digest"
                        )
                    digest_staged = _write_staged(
                        digest_path,
                        f"{new_sha256}\n".encode("ascii"),
                    )
                    try:
                        if current.update_recovery:
                            backup_path = current.source.path
                            backup_metadata = backup_path.lstat()
                            if (
                                backup_path
                                != _config_backup_path(
                                    config_path,
                                    current.sha256,
                                )
                                or stat.S_ISLNK(backup_metadata.st_mode)
                            ):
                                raise DashboardConfigError(
                                    "interrupted config update backup is invalid"
                                )
                            os.replace(config_staged, config_path)
                            _fsync_directory(config_path.parent)
                            os.replace(digest_staged, digest_path)
                            _fsync_directory(config_path.parent)
                            _unlink_created(
                                backup_path,
                                (
                                    backup_metadata.st_dev,
                                    backup_metadata.st_ino,
                                ),
                            )
                            _fsync_directory(config_path.parent)
                        else:
                            old_config_bytes = _require_private_regular_file(
                                config_path,
                                "Hermes V2 config",
                            )
                            if (
                                hashlib.sha256(old_config_bytes).hexdigest()
                                != current.sha256
                            ):
                                raise DashboardConfigConflict(
                                    "configuration changed after this dashboard "
                                    "page loaded"
                                )
                            backup_path = _config_backup_path(
                                config_path,
                                current.sha256,
                            )
                            if _path_entry_exists(backup_path):
                                stale_backup = _require_private_regular_file(
                                    backup_path,
                                    "stale Hermes V2 config update backup",
                                )
                                stale_metadata = backup_path.lstat()
                                if (
                                    hashlib.sha256(stale_backup).hexdigest()
                                    != current.sha256
                                ):
                                    raise DashboardConfigError(
                                        "stale config update backup does not "
                                        "match the active revision"
                                    )
                                _unlink_created(
                                    backup_path,
                                    (
                                        stale_metadata.st_dev,
                                        stale_metadata.st_ino,
                                    ),
                                )
                                if _path_entry_exists(backup_path):
                                    raise DashboardConfigError(
                                        "stale config update backup could not "
                                        "be removed"
                                    )
                                _fsync_directory(config_path.parent)
                            backup_identity = _publish_complete_file_exclusive(
                                config_path,
                                backup_path,
                                label="Hermes V2 config update backup",
                            )
                            _fsync_directory(config_path.parent)
                            config_replaced = False
                            try:
                                os.replace(config_staged, config_path)
                                config_replaced = True
                                _fsync_directory(config_path.parent)
                                os.replace(digest_staged, digest_path)
                                _fsync_directory(config_path.parent)
                            except Exception:
                                if not config_replaced:
                                    _unlink_created(
                                        backup_path,
                                        backup_identity,
                                    )
                                raise
                            _unlink_created(
                                backup_path,
                                backup_identity,
                            )
                            _fsync_directory(config_path.parent)
                    finally:
                        digest_staged.unlink(missing_ok=True)
            finally:
                config_staged.unlink(missing_ok=True)

            updated = read_dashboard_snapshot(profile, environ=environ)
            if updated.sha256 != new_sha256:
                raise DashboardConfigError(
                    "configuration read-back did not match the committed bytes"
                )
            try:
                _append_audit(
                    source=current.source,
                    profile=profile,
                    old_sha256=current.sha256 or current.revision,
                    new_sha256=new_sha256,
                )
            except OSError:
                logger.exception(
                    "could not append the Nunchi dashboard audit record"
                )
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
    snapshot = read_dashboard_snapshot(
        profile,
        environ=environ,
        allow_invalid=True,
    )
    if snapshot.bootstrap_required:
        return {
            "receipts": [],
            "config_sha256": snapshot.sha256,
            "bootstrap_required": True,
        }
    if snapshot.config is None:
        raise DashboardConfigError("Hermes V2 configuration is invalid")
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
        "bootstrap_required": False,
    }
