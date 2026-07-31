"""Initialize and verify stable operator state for an installed V2 artifact.

Hermes discovers its V2 plugin and Claude Code its runner from the installed
wheel. This installer owns only shared V2 operator state and never copies or
patches a host checkout.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from . import __version__

MARKER_NAME = "install.json"
MARKER_SCHEMA = 2


class InstallError(RuntimeError):
    pass


def _default_config_root() -> Path:
    return Path(
        os.environ.get(
            "NUNCHI_CONFIG_ROOT",
            Path.home() / ".config" / "nunchi-v2",
        )
    )


def _default_state_root() -> Path:
    return Path(
        os.environ.get(
            "NUNCHI_STATE_ROOT",
            Path.home() / ".local" / "state" / "nunchi-v2",
        )
    )


def _manifest(config_root: Path, state_root: Path) -> dict[str, Any]:
    return {
        "schema_version": MARKER_SCHEMA,
        "product": "nunchi",
        "product_version": __version__,
        "generation": 2,
        "config_root": str(config_root.resolve()),
        "state_root": str(state_root.resolve()),
        "v1_fallback": False,
        "excluded_integrations": [],
    }


def _write_exclusive(path: Path, payload: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError(f"short write to {path}")
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_replace(path: Path, payload: bytes, mode: int = 0o600) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    _write_exclusive(temporary, payload, mode)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def initialize(config_root: Path, state_root: Path) -> dict[str, Any]:
    for path in (config_root, state_root):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            path.chmod(0o700)
        except OSError as exc:
            raise InstallError(f"cannot secure {path}: {exc}") from exc
    marker = config_root / MARKER_NAME
    expected = _manifest(config_root, state_root)
    if marker.exists():
        try:
            existing = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise InstallError(f"existing V2 marker is untrustworthy: {exc}") from exc
        if existing != expected:
            raise InstallError(
                "existing install marker differs; use a new root or reconcile it explicitly"
            )
        return {"status": "already-initialized", **expected}
    payload = (
        json.dumps(expected, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()
    try:
        _write_exclusive(marker, payload)
    except OSError as exc:
        raise InstallError(f"cannot create V2 install marker: {exc}") from exc
    return {"status": "initialized", **expected}


def verify(config_root: Path) -> dict[str, Any]:
    marker = config_root / MARKER_NAME
    try:
        document = json.loads(marker.read_text())
    except FileNotFoundError as exc:
        raise InstallError(f"V2 install marker is absent at {marker}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"V2 install marker is untrustworthy: {exc}") from exc
    required = {
        "schema_version",
        "product",
        "product_version",
        "generation",
        "config_root",
        "state_root",
        "v1_fallback",
        "excluded_integrations",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise InstallError("V2 install marker has an invalid closed shape")
    if (
        document["schema_version"] != 2
        or document["product"] != "nunchi"
        or document["product_version"] != __version__
        or document["generation"] != 2
        or document["v1_fallback"] is not False
        or document["excluded_integrations"] != []
        or Path(document["config_root"]).resolve() != config_root.resolve()
    ):
        raise InstallError("V2 install marker does not match this installed artifact")
    state_root = Path(document["state_root"])
    if not state_root.is_dir():
        raise InstallError("configured V2 state root is absent")
    for path in (config_root, state_root):
        if path.stat().st_mode & 0o077:
            raise InstallError(f"{path} permissions expose operator state")
    return {"status": "verified", **document}


def upgrade(config_root: Path, state_root: Path) -> dict[str, Any]:
    """Upgrade only shared install metadata; profile bytes remain untouched."""

    marker = config_root / MARKER_NAME
    try:
        existing = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"existing V2 marker is untrustworthy: {exc}") from exc
    if not isinstance(existing, dict):
        raise InstallError("existing V2 marker has an invalid shape")
    expected = _manifest(config_root, state_root)
    invariant_fields = {
        "schema_version",
        "product",
        "generation",
        "config_root",
        "state_root",
        "v1_fallback",
        "excluded_integrations",
    }
    if any(existing.get(name) != expected[name] for name in invariant_fields):
        raise InstallError("existing install cannot be upgraded in place safely")
    old_version = existing.get("product_version")
    if not isinstance(old_version, str) or not old_version:
        raise InstallError("existing install version is absent")
    if old_version == __version__:
        return {"status": "already-current", **expected}
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", old_version)
    backup = config_root / f".{MARKER_NAME}.{safe_version}.rollback"
    if not backup.exists():
        _write_exclusive(backup, (json.dumps(existing, sort_keys=True) + "\n").encode())
    _atomic_replace(
        marker,
        (json.dumps(expected, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(),
    )
    return {"status": "upgraded", "from_version": old_version, **expected}


def rollback(config_root: Path, version: str) -> dict[str, Any]:
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", version)
    if not version or safe_version != version:
        raise InstallError("rollback version is invalid")
    backup = config_root / f".{MARKER_NAME}.{safe_version}.rollback"
    try:
        payload = backup.read_bytes()
        document = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"rollback metadata for {version!r} is unavailable: {exc}") from exc
    if not isinstance(document, dict) or document.get("product_version") != version:
        raise InstallError("rollback metadata is untrustworthy")
    _atomic_replace(config_root / MARKER_NAME, payload)
    return {"status": "rolled-back", **document}


def uninstall_state(config_root: Path, state_root: Path, *, purge: bool = False) -> dict[str, Any]:
    """Remove install registration, and state only after explicit purge."""

    marker = config_root / MARKER_NAME
    if marker.exists():
        marker.unlink()
    removed = [str(marker)]
    if purge:
        for path in (config_root, state_root):
            resolved = path.resolve()
            if len(resolved.parts) < 4 or resolved == Path.home().resolve():
                raise InstallError("refusing to purge a broad operator-state path")
            if path.exists():
                shutil.rmtree(path)
                removed.append(str(path))
    return {"status": "uninstalled", "purged": purge, "removed": removed}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi-install")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "verify", "upgrade"):
        command = commands.add_parser(name)
        command.add_argument("--config-root", type=Path, default=_default_config_root())
        if name in ("init", "upgrade"):
            command.add_argument("--state-root", type=Path, default=_default_state_root())
    rollback_command = commands.add_parser("rollback")
    rollback_command.add_argument("--config-root", type=Path, default=_default_config_root())
    rollback_command.add_argument("--version", required=True)
    uninstall_command = commands.add_parser("uninstall")
    uninstall_command.add_argument("--config-root", type=Path, default=_default_config_root())
    uninstall_command.add_argument("--state-root", type=Path, default=_default_state_root())
    uninstall_command.add_argument("--purge-state", action="store_true")
    commands.add_parser("probe")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.config_root, args.state_root)
        elif args.command == "verify":
            result = verify(args.config_root)
        elif args.command == "upgrade":
            result = upgrade(args.config_root, args.state_root)
        elif args.command == "rollback":
            result = rollback(args.config_root, args.version)
        elif args.command == "uninstall":
            result = uninstall_state(
                args.config_root,
                args.state_root,
                purge=args.purge_state,
            )
        else:
            result = {
                "product": "nunchi",
                "product_version": __version__,
                "generation": 2,
                "artifact_installable": True,
                "v1_fallback": False,
                "excluded_integrations": [],
            }
    except (InstallError, OSError, ValueError) as exc:
        print(f"nunchi-install: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
