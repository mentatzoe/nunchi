"""Initialize and verify stable operator state for an installed V2 artifact.

Hermes discovers its V2 plugin from the installed wheel, so this installer
never copies or patches a Hermes checkout. Claude Code remains outside this
installed artifact.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import os
from pathlib import Path
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi-install")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--config-root", type=Path, default=_default_config_root())
        if name == "init":
            command.add_argument("--state-root", type=Path, default=_default_state_root())
    commands.add_parser("probe")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.config_root, args.state_root)
        elif args.command == "verify":
            result = verify(args.config_root)
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
