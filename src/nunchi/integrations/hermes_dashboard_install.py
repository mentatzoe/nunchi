"""Install and verify the Nunchi tab in Hermes's supported plugin directory."""

from __future__ import annotations

import argparse
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from nunchi import __version__


_ASSET_PACKAGE = "nunchi.integrations.hermes_dashboard_assets"
_ASSET_NAMES = ("manifest.json", "index.js", "plugin_api.py")
_BRIDGE_NAME = "nunchi-dashboard"
_MARKER_NAME = ".nunchi-dashboard.json"
_LEGACY_BRIDGE_NAME = "nunchi-v2-dashboard"
_LEGACY_MARKER_NAME = ".nunchi-v2-dashboard.json"


class DashboardInstallError(RuntimeError):
    """The dashboard bridge could not be safely installed or verified."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assets() -> dict[str, bytes]:
    root = resources.files(_ASSET_PACKAGE)
    return {name: root.joinpath(name).read_bytes() for name in _ASSET_NAMES}


def _target(hermes_home: Path) -> Path:
    return hermes_home / "plugins" / _BRIDGE_NAME


def default_hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    try:
        from hermes_cli.config import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        return Path.home() / ".hermes"


def _assert_safe_path(path: Path, *, boundary: Path) -> None:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise DashboardInstallError(
                f"refusing symlinked dashboard path: {current}"
            )
        if current == boundary:
            return
        if current == current.parent:
            raise DashboardInstallError(
                "dashboard path is outside the configured Hermes home"
            )
        current = current.parent


def _prepare_directory(path: Path, *, hermes_home: Path) -> None:
    _assert_safe_path(path, boundary=hermes_home)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise DashboardInstallError(f"dashboard path is not a directory: {path}")
    os.chmod(path, 0o700)


def _write_file(path: Path, data: bytes) -> None:
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
        os.replace(staged, path)
        os.chmod(path, 0o600)
    finally:
        staged.unlink(missing_ok=True)


def _bridge_is_owned(bridge: Path, marker_name: str) -> bool:
    marker_path = bridge / marker_name
    if marker_path.is_symlink() or not marker_path.is_file():
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if marker.get("format") != 1 or not isinstance(marker.get("assets"), dict):
        return False
    allowed_files = {Path(marker_name)} | {
        Path("dashboard") / name for name in _ASSET_NAMES
    }
    allowed_directories = {Path("dashboard")}
    for existing in bridge.rglob("*"):
        relative = existing.relative_to(bridge)
        if existing.is_symlink():
            return False
        if existing.is_dir() and relative not in allowed_directories:
            return False
        if existing.is_file() and relative not in allowed_files:
            return False
    return True


def _migrate_legacy_bridge(*, hermes_home: Path, bridge: Path) -> None:
    legacy = hermes_home / "plugins" / _LEGACY_BRIDGE_NAME
    if not legacy.exists() or bridge.exists():
        return
    if not _bridge_is_owned(legacy, _LEGACY_MARKER_NAME):
        raise DashboardInstallError(
            "legacy Nunchi dashboard directory is not safely attributable"
        )
    os.replace(legacy, bridge)


def install_dashboard(*, hermes_home: Path) -> dict[str, Any]:
    """Materialize wheel-owned assets where released Hermes scans for tabs."""

    hermes_home = hermes_home.expanduser().absolute()
    assets = _assets()
    bridge = _target(hermes_home)
    _migrate_legacy_bridge(hermes_home=hermes_home, bridge=bridge)
    dashboard = bridge / "dashboard"
    old_marker = bridge / _LEGACY_MARKER_NAME
    if old_marker.is_file() and not old_marker.is_symlink():
        old_marker.replace(bridge / _MARKER_NAME)
    if bridge.exists() and not _bridge_is_owned(bridge, _MARKER_NAME):
        existing_files = [path for path in bridge.rglob("*") if path.is_file()]
        if existing_files:
            raise DashboardInstallError(
                "refusing to overwrite an unmanaged Nunchi dashboard directory"
            )
    _prepare_directory(dashboard, hermes_home=hermes_home)
    allowed_files = {Path(_MARKER_NAME)} | {
        Path("dashboard") / name for name in _ASSET_NAMES
    }
    allowed_directories = {Path("dashboard")}
    for existing in bridge.rglob("*"):
        relative = existing.relative_to(bridge)
        if existing.is_symlink():
            raise DashboardInstallError(
                f"refusing symlinked dashboard entry: {existing}"
            )
        if existing.is_dir() and relative not in allowed_directories:
            raise DashboardInstallError(
                f"refusing unmanaged dashboard directory: {existing}"
            )
        if existing.is_file() and relative not in allowed_files:
            raise DashboardInstallError(
                f"refusing to overwrite unmanaged dashboard file: {existing}"
            )

    # The manifest is written last so Hermes never discovers a partial tab.
    for name in ("index.js", "plugin_api.py"):
        _write_file(dashboard / name, assets[name])
    marker = {
        "format": 1,
        "nunchi_version": __version__,
        "assets": {name: _sha256(data) for name, data in assets.items()},
    }
    _write_file(
        bridge / _MARKER_NAME,
        (json.dumps(marker, sort_keys=True, indent=2) + "\n").encode(),
    )
    _write_file(dashboard / "manifest.json", assets["manifest.json"])
    return verify_dashboard(hermes_home=hermes_home)


def verify_dashboard(*, hermes_home: Path) -> dict[str, Any]:
    hermes_home = hermes_home.expanduser().absolute()
    assets = _assets()
    bridge = _target(hermes_home)
    dashboard = bridge / "dashboard"
    _assert_safe_path(dashboard, boundary=hermes_home)
    marker_path = bridge / _MARKER_NAME
    if marker_path.is_symlink():
        raise DashboardInstallError("Nunchi dashboard marker must not be a symlink")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardInstallError("Nunchi dashboard marker is missing") from exc
    expected = {name: _sha256(data) for name, data in assets.items()}
    if marker.get("assets") != expected:
        raise DashboardInstallError("Nunchi dashboard marker does not match this wheel")
    for name, expected_sha in expected.items():
        path = dashboard / name
        if path.is_symlink() or not path.is_file():
            raise DashboardInstallError(f"Nunchi dashboard asset is missing: {name}")
        if _sha256(path.read_bytes()) != expected_sha:
            raise DashboardInstallError(f"Nunchi dashboard asset changed: {name}")
    return {
        "ok": True,
        "path": str(dashboard.resolve()),
        "nunchi_version": __version__,
        "assets": expected,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nunchi-hermes-dashboard",
        description="Install or verify the Nunchi tab in Hermes dashboard.",
    )
    parser.add_argument("command", choices=("install", "verify"))
    parser.add_argument(
        "--hermes-home",
        type=Path,
        help="Hermes home directory; defaults to HERMES_HOME or ~/.hermes",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    home = (
        arguments.hermes_home.expanduser()
        if arguments.hermes_home is not None
        else default_hermes_home()
    )
    try:
        result = (
            install_dashboard(hermes_home=home)
            if arguments.command == "install"
            else verify_dashboard(hermes_home=home)
        )
    except DashboardInstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
