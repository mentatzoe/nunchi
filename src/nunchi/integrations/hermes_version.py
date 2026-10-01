"""Resolve installed Hermes identity without changing host metadata or source.

Recent stock source installs deliberately publish distribution version 0.0.0.
Only that exact placeholder permits the official version_info fallback. This
is a compatibility floor, not a signature check or a substitute for host-shape
validation. No profile-local clone may lend its identity to unrelated code.
"""
from __future__ import annotations

import importlib
import importlib.metadata
from pathlib import Path
import re
import subprocess

from nunchi.errors import ValidationError


_FINAL_VERSION = re.compile(
    r"(\d+)\.(\d+)\.(\d+)(?:\.post\d+)?"
    r"(?:\+[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*)?"
)
_MINIMUM = (0, 19, 0)
_STAMP_SOURCES = {"build", "commit-build", "ci", "docker", "local", "nix"}


def _require_supported_version(value: str) -> str:
    match = _FINAL_VERSION.fullmatch(value) if isinstance(value, str) else None
    if match is None or tuple(map(int, match.groups())) < _MINIMUM:
        raise ValidationError(
            f"Hermes version {value!r} is unknown, prerelease, or below 0.19.0"
        )
    return value


def hermes_version() -> str:
    """Return a released version or validated official source/build provenance.

    Errors deliberately prevent activation. Released metadata takes precedence;
    an older release cannot promote itself using a profile's newer Git clone.
    For source builds require the executing tree's clean, full commit identity
    and a known released base with a consistent distance/derived version.
    """
    try:
        installed = importlib.metadata.version("hermes-agent")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValidationError("Nunchi requires an installed hermes-agent runtime") from exc
    if installed != "0.0.0":
        return _require_supported_version(installed)

    try:
        module = importlib.import_module("hermes_cli.version_info")
        info = module.get_version_info()
        base = _require_supported_version(info.base_version)
        if not re.fullmatch(r"\d+\.\d+\.\d+", base):
            raise ValueError("source base must be a final release")
        commit = info.commit
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit) or set(commit) == {"0"}:
            raise ValueError("missing full commit identity")
        if info.dirty is not False:
            raise ValueError("dirty or unknown host source state")
        distance = info.distance
        if type(distance) is not int or distance < 0:
            raise ValueError("unknown release distance")
        expected = {base} if distance == 0 else {
            f"{base}+{distance}",
            # git's abbreviation grows when its object set needs more digits.
            *(f"{base}+{distance}.g{commit[:length]}" for length in range(7, 41)),
        }
        if info.derived_version not in expected:
            raise ValueError("derived version disagrees with release/commit provenance")
        if info.source == "git":
            if not module.__file__:
                raise ValueError("host module has no source location")
            root = Path(module.__file__).resolve().parent.parent
            if not (root / ".git").exists():
                raise ValueError("Git provenance is not from the executing host tree")
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if result.returncode or result.stdout.strip() != commit:
                raise ValueError("executing host commit differs from official provenance")
        elif info.source not in _STAMP_SOURCES:
            raise ValueError("unknown or fallback provenance source")
        return info.derived_version
    except Exception as exc:
        raise ValidationError(
            "Hermes 0.0.0 has no verifiable supported version provenance: " + str(exc)
        ) from exc
