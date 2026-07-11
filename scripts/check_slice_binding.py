#!/usr/bin/env python3
"""Resolve and validate one canonical V2 slice without persisting feature state."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from check_governance import EXPECTED_SLICES


EXPECTED_SLICE_DIRECTORIES = tuple(f"specs/{name}" for name in EXPECTED_SLICES)
REQUIRED_SLICE_ARTIFACTS = (
    "spec.md",
    "plan.md",
    "tasks.md",
    "checklists/requirements.md",
)


def verify_slice_binding(root: Path, slice_directory: str) -> dict[str, object]:
    """Return a preflight payload or raise ValueError for an unsafe binding."""

    if slice_directory not in EXPECTED_SLICE_DIRECTORIES:
        allowed = ", ".join(EXPECTED_SLICE_DIRECTORIES)
        raise ValueError(
            f"slice_directory must name one existing canonical slice; allowed: {allowed}"
        )

    helper = root / ".specify" / "scripts" / "bash" / "check-prerequisites.sh"
    if not helper.is_file() or helper.is_symlink():
        raise ValueError(f"SpecKit prerequisite helper is missing: {helper}")
    if helper.stat().st_mode & 0o111 == 0:
        raise ValueError(f"SpecKit prerequisite helper is not executable: {helper}")

    slice_path = root / slice_directory
    if not slice_path.is_dir() or slice_path.is_symlink():
        raise ValueError(f"canonical slice directory is missing or unsafe: {slice_path}")

    feature_state = root / ".specify" / "feature.json"
    before = feature_state.read_bytes() if feature_state.exists() else None
    environment = os.environ.copy()
    environment["SPECIFY_FEATURE_DIRECTORY"] = slice_directory
    completed = subprocess.run(
        [str(helper), "--json", "--require-tasks", "--include-tasks"],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    after = feature_state.read_bytes() if feature_state.exists() else None
    if after != before:
        raise ValueError("read-only slice preflight modified .specify/feature.json")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"SpecKit could not resolve the requested slice: {detail}")
    try:
        resolved = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"SpecKit returned invalid prerequisite JSON: {exc}") from exc

    expected_directory = slice_path.resolve()
    observed_directory = Path(str(resolved.get("FEATURE_DIR", ""))).resolve()
    if observed_directory != expected_directory:
        raise ValueError(
            "SpecKit resolved a different feature directory: "
            f"expected {expected_directory}, observed {observed_directory}"
        )

    missing = [
        artifact
        for artifact in REQUIRED_SLICE_ARTIFACTS
        if not (expected_directory / artifact).is_file()
        or (expected_directory / artifact).is_symlink()
    ]
    if missing:
        raise ValueError(
            f"{slice_directory} is missing required planning artifacts: {missing}"
        )

    return {
        "SLICE_DIRECTORY": slice_directory,
        "FEATURE_DIR": str(expected_directory),
        "REQUIRED_ARTIFACTS": list(REQUIRED_SLICE_ARTIFACTS),
        "AVAILABLE_DOCS": resolved.get("AVAILABLE_DOCS", []),
        "PERSISTED_FEATURE_STATE": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slice_directory", help="exact specs/010-... through specs/110-... path")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    try:
        payload = verify_slice_binding(root, args.slice_directory)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
