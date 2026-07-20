"""Run the deterministic mechanics behind the S01-S18 V2 scene catalog.

This runner intentionally does not manufacture an oracle for socially correct
model behavior.  It maps stable acceptance-scene IDs to the repository's
deterministic contract/mechanics tests and reports external evidence that still
must be supplied by installed or live evaluation.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any


EXPECTED_SCENE_IDS = tuple(f"S{number:02d}" for number in range(1, 19))
DETERMINISTIC_TIME = "1970-01-01T00:00:00Z"


class CatalogError(ValueError):
    pass


def load_catalog() -> dict[str, Any]:
    resource = resources.files("evals.v2.parity").joinpath("catalog.json")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError("V2 scene catalog is unreadable") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "scenes"}:
        raise CatalogError("V2 scene catalog has an invalid root")
    if document["schema_version"] != 1 or not isinstance(document["scenes"], list):
        raise CatalogError("V2 scene catalog has an unsupported version")
    observed_ids: list[str] = []
    for scene in document["scenes"]:
        if not isinstance(scene, dict) or set(scene) != {
            "scene_id",
            "title",
            "mechanics_tests",
            "external_evidence",
        }:
            raise CatalogError("V2 scene catalog contains an invalid scene")
        if (
            not isinstance(scene["scene_id"], str)
            or not isinstance(scene["title"], str)
            or not scene["title"]
            or not isinstance(scene["mechanics_tests"], list)
            or not isinstance(scene["external_evidence"], list)
            or any(not isinstance(value, str) or not value for value in scene["mechanics_tests"])
            or any(not isinstance(value, str) or not value for value in scene["external_evidence"])
        ):
            raise CatalogError("V2 scene catalog contains invalid values")
        if len(set(scene["mechanics_tests"])) != len(scene["mechanics_tests"]):
            raise CatalogError("V2 scene catalog repeats a mechanics test")
        if len(set(scene["external_evidence"])) != len(scene["external_evidence"]):
            raise CatalogError("V2 scene catalog repeats external evidence")
        observed_ids.append(scene["scene_id"])
    if tuple(observed_ids) != EXPECTED_SCENE_IDS:
        raise CatalogError("V2 scene catalog must contain ordered S01-S18 exactly once")
    return copy.deepcopy(document)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_value(root: Path, *arguments: str, allow_empty: bool = False) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    if completed.returncode != 0 or (not value and not allow_empty):
        return None
    return value


def _provenance(root: Path) -> dict[str, Any]:
    head = _git_value(root, "rev-parse", "HEAD")
    status = _git_value(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
        allow_empty=True,
    )
    return {
        "commit": head or "unavailable",
        "worktree_clean": status == "" if status is not None else None,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


def _run_scene(scene: dict[str, Any], *, root: Path) -> dict[str, Any]:
    targets = scene["mechanics_tests"]
    external = scene["external_evidence"]
    if not targets:
        return {
            "scene_id": scene["scene_id"],
            "title": scene["title"],
            "mechanics": "not-applicable",
            "external_evidence": external,
            "complete": False,
        }
    command = [sys.executable, "-m", "unittest", "-q", *targets]
    environment = os.environ.copy()
    import_path = os.pathsep.join((str(root / "src"), str(root)))
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        os.pathsep.join((import_path, existing)) if existing else import_path
    )
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        mechanics = "passed" if completed.returncode == 0 else "failed"
        diagnostic = None
        if completed.returncode != 0:
            diagnostic = (completed.stdout + completed.stderr)[-16000:]
    except subprocess.TimeoutExpired:
        mechanics = "failed"
        diagnostic = "mechanics test command exceeded 300 seconds"
    except OSError:
        mechanics = "failed"
        diagnostic = "mechanics test command could not start"
    record: dict[str, Any] = {
        "scene_id": scene["scene_id"],
        "title": scene["title"],
        "mechanics": mechanics,
        "command": command,
        "external_evidence": external,
        "complete": mechanics == "passed" and not external,
    }
    if diagnostic is not None:
        record["diagnostic"] = diagnostic
    return record


def run(
    *,
    selected_ids: tuple[str, ...] = (),
    deterministic_time: bool = False,
) -> dict[str, Any]:
    catalog = load_catalog()
    selected = set(selected_ids)
    if selected - set(EXPECTED_SCENE_IDS):
        raise CatalogError("unknown V2 scene ID")
    root = _repository_root()
    scenes = [
        _run_scene(scene, root=root)
        for scene in catalog["scenes"]
        if not selected or scene["scene_id"] in selected
    ]
    failed = [scene["scene_id"] for scene in scenes if scene["mechanics"] == "failed"]
    incomplete = [scene["scene_id"] for scene in scenes if not scene["complete"]]
    return {
        "schema_version": 1,
        "evaluation": "nunchi-v2-acceptance-scenes",
        "recorded_at": (
            DETERMINISTIC_TIME
            if deterministic_time
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "provenance": _provenance(root),
        "scenes": scenes,
        "summary": {
            "selected": len(scenes),
            "mechanics_failed": failed,
            "incomplete": incomplete,
            "candidate_complete": not failed and not incomplete,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.v2.parity.runner",
        description=(
            "List or run deterministic mechanics for Nunchi V2 scenes S01-S18; "
            "live and installed evidence remains explicitly incomplete."
        ),
    )
    parser.add_argument("--list", action="store_true", help="List the scene catalog")
    parser.add_argument("--scene", action="append", default=[], help="Run one scene ID; repeatable")
    parser.add_argument("--output", type=Path, help="Write the JSON evidence record to this path")
    parser.add_argument("--deterministic-time", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        catalog = load_catalog()
        if arguments.list:
            for scene in catalog["scenes"]:
                if scene["mechanics_tests"] and scene["external_evidence"]:
                    evidence_class = "mechanics + external"
                elif scene["mechanics_tests"]:
                    evidence_class = "mechanics"
                else:
                    evidence_class = "external-only"
                print(f"{scene['scene_id']}\t{scene['title']}\t{evidence_class}")
            return 0
        record = run(
            selected_ids=tuple(arguments.scene),
            deterministic_time=arguments.deterministic_time,
        )
    except CatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        try:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            with arguments.output.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
        except FileExistsError:
            print("V2 evaluation output already exists", file=sys.stderr)
            return 2
        except OSError:
            print("could not create V2 evaluation output", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(serialized)
    return 1 if record["summary"]["mechanics_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
