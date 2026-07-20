"""Run the deterministic mechanics behind the S01-S18 V2 scene catalog.

This runner intentionally does not manufacture an oracle for socially correct
model behavior.  It maps stable acceptance-scene IDs to the repository's
deterministic contract/mechanics tests and reports external evidence that still
must be supplied by installed or live evaluation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any


EXPECTED_SCENE_IDS = tuple(f"S{number:02d}" for number in range(1, 19))
DETERMINISTIC_TIME = "1970-01-01T00:00:00Z"
DEFAULT_EVIDENCE_INDEX = Path("evidence/v2/parity/external-evidence-index.json")
MAX_EVIDENCE_INDEX_BYTES = 1024 * 1024
MAX_EVIDENCE_ARTIFACT_BYTES = 64 * 1024 * 1024
_COMMIT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_CROSS_FAMILY_REQUIREMENTS = frozenset(
    {"cross-family-participant-behavior-review"}
)


class CatalogError(ValueError):
    pass


class EvidenceIndexError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _strict_json_bytes(payload: bytes) -> Any:
    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=lambda _value: (_ for _ in ()).throw(
            ValueError("non-finite")
        ),
    )


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


def _git_success(root: Path, *arguments: str) -> bool:
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
        return False
    return completed.returncode == 0


def _safe_evidence_file(
    root: Path,
    raw_path: str | Path,
    *,
    maximum_bytes: int,
) -> tuple[Path, str]:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        absolute = candidate
    else:
        absolute = root / candidate
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise EvidenceIndexError("evidence path escapes the repository") from exc
    if (
        not relative.parts
        or relative.parts[:2] != ("evidence", "v2")
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise EvidenceIndexError("evidence path must be below evidence/v2")
    cursor = root
    try:
        for part in relative.parts:
            cursor = cursor / part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise EvidenceIndexError("evidence paths may not contain symlinks")
        metadata = absolute.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise EvidenceIndexError("evidence file is missing") from exc
    except OSError as exc:
        raise EvidenceIndexError("evidence file is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes:
        raise EvidenceIndexError("evidence file is not a bounded regular file")
    return absolute, relative.as_posix()


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 64:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() == timezone.utc.utcoffset(parsed)
    )


def _bounded_text(value: Any, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or "\0" in value
    ):
        raise EvidenceIndexError("evidence index contains invalid text")
    return value


def load_external_evidence_index(
    *,
    root: Path,
    index_path: Path | None = None,
) -> dict[str, Any]:
    """Load exact, committed evidence bound to one frozen product commit.

    Evidence may be committed after the reviewed candidate, but every change
    from that candidate to the current commit must remain below ``evidence/``.
    Any product, contract, test, evaluation, packaging, or documentation change
    therefore invalidates the earlier review and requires a new index.
    """
    selected = index_path or (root / DEFAULT_EVIDENCE_INDEX)
    if not selected.is_absolute():
        selected = root / selected
    if not selected.exists():
        return {
            "available": False,
            "path": selected.relative_to(root).as_posix()
            if selected.is_relative_to(root)
            else str(selected),
            "candidate_commit": None,
            "records": {},
        }
    absolute, relative = _safe_evidence_file(
        root,
        selected,
        maximum_bytes=MAX_EVIDENCE_INDEX_BYTES,
    )
    try:
        document = _strict_json_bytes(absolute.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EvidenceIndexError("external evidence index is invalid JSON") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "candidate_commit", "records"}
        or document.get("schema_version") != 1
        or not isinstance(document.get("records"), list)
    ):
        raise EvidenceIndexError("external evidence index has an invalid root")
    candidate_commit = document.get("candidate_commit")
    if not isinstance(candidate_commit, str) or _COMMIT_RE.fullmatch(candidate_commit) is None:
        raise EvidenceIndexError("external evidence index has an invalid candidate commit")
    head = _git_value(root, "rev-parse", "HEAD")
    status = _git_value(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
        allow_empty=True,
    )
    if (
        head is None
        or status != ""
        or not _git_success(root, "cat-file", "-e", f"{candidate_commit}^{{commit}}")
        or not _git_success(root, "merge-base", "--is-ancestor", candidate_commit, head)
        or not _git_success(
            root,
            "diff",
            "--quiet",
            candidate_commit,
            head,
            "--",
            ".",
            ":(exclude)evidence/**",
        )
        or not _git_success(root, "ls-files", "--error-unmatch", "--", relative)
    ):
        raise EvidenceIndexError(
            "external evidence is not committed cleanly against an unchanged frozen candidate"
        )

    records: dict[str, dict[str, Any]] = {}
    seen_artifacts: dict[str, str] = {}
    for raw_record in document["records"]:
        if (
            not isinstance(raw_record, dict)
            or set(raw_record)
            != {
                "evidence_id",
                "candidate_commit",
                "status",
                "recorded_at",
                "attestations",
                "artifacts",
                "limitations",
            }
        ):
            raise EvidenceIndexError("external evidence index contains an invalid record")
        evidence_id = _bounded_text(raw_record.get("evidence_id"), maximum=128)
        if evidence_id in records:
            raise EvidenceIndexError("external evidence index repeats an evidence ID")
        if (
            raw_record.get("candidate_commit") != candidate_commit
            or raw_record.get("status") != "PASS"
            or not _valid_utc_timestamp(raw_record.get("recorded_at"))
            or not isinstance(raw_record.get("attestations"), list)
            or not raw_record["attestations"]
            or len(raw_record["attestations"]) > 16
            or not isinstance(raw_record.get("artifacts"), list)
            or not raw_record["artifacts"]
            or len(raw_record["artifacts"]) > 64
            or not isinstance(raw_record.get("limitations"), list)
            or len(raw_record["limitations"]) > 64
        ):
            raise EvidenceIndexError("external evidence record is not a bound PASS")
        attestations: list[dict[str, str]] = []
        for attestation in raw_record["attestations"]:
            if not isinstance(attestation, dict) or set(attestation) != {"identity", "family"}:
                raise EvidenceIndexError("external evidence attestation is invalid")
            attestations.append(
                {
                    "identity": _bounded_text(attestation.get("identity")),
                    "family": _bounded_text(attestation.get("family"), maximum=128),
                }
            )
        if evidence_id in _CROSS_FAMILY_REQUIREMENTS and not any(
            attestation["family"].casefold() not in {"openai", "codex"}
            for attestation in attestations
        ):
            raise EvidenceIndexError("cross-family review lacks a non-OpenAI attestation")
        artifacts: list[dict[str, str]] = []
        for artifact in raw_record["artifacts"]:
            if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
                raise EvidenceIndexError("external evidence artifact is invalid")
            artifact_path = _bounded_text(artifact.get("path"), maximum=4096)
            expected_digest = artifact.get("sha256")
            if not isinstance(expected_digest, str) or _DIGEST_RE.fullmatch(expected_digest) is None:
                raise EvidenceIndexError("external evidence artifact digest is invalid")
            artifact_file, artifact_relative = _safe_evidence_file(
                root,
                artifact_path,
                maximum_bytes=MAX_EVIDENCE_ARTIFACT_BYTES,
            )
            if artifact_relative == relative:
                raise EvidenceIndexError("external evidence index cannot attest itself")
            prior_digest = seen_artifacts.get(artifact_relative)
            if prior_digest is not None and prior_digest != expected_digest:
                raise EvidenceIndexError("shared evidence artifact has conflicting digests")
            if not _git_success(root, "ls-files", "--error-unmatch", "--", artifact_relative):
                raise EvidenceIndexError("external evidence artifact is not committed")
            try:
                observed_digest = hashlib.sha256(artifact_file.read_bytes()).hexdigest()
            except OSError as exc:
                raise EvidenceIndexError("external evidence artifact is unavailable") from exc
            if observed_digest != expected_digest:
                raise EvidenceIndexError("external evidence artifact digest does not match")
            seen_artifacts[artifact_relative] = observed_digest
            artifacts.append({"path": artifact_relative, "sha256": observed_digest})
        limitations = [
            _bounded_text(limitation, maximum=2048)
            for limitation in raw_record["limitations"]
        ]
        records[evidence_id] = {
            "status": "satisfied",
            "recorded_at": raw_record["recorded_at"],
            "attestations": attestations,
            "artifacts": artifacts,
            "limitations": limitations,
        }
    return {
        "available": True,
        "path": relative,
        "candidate_commit": candidate_commit,
        "records": records,
    }


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


def _run_scene(
    scene: dict[str, Any],
    *,
    root: Path,
    evidence_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    targets = scene["mechanics_tests"]
    external = scene["external_evidence"]
    evidence_status = {
        evidence_id: evidence_records.get(
            evidence_id,
            {"status": "missing"},
        )
        for evidence_id in external
    }
    evidence_complete = all(
        record["status"] == "satisfied" for record in evidence_status.values()
    )
    if not targets:
        return {
            "scene_id": scene["scene_id"],
            "title": scene["title"],
            "mechanics": "not-applicable",
            "external_evidence": external,
            "external_evidence_status": evidence_status,
            "complete": evidence_complete,
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
        "external_evidence_status": evidence_status,
        "complete": mechanics == "passed" and evidence_complete,
    }
    if diagnostic is not None:
        record["diagnostic"] = diagnostic
    return record


def run(
    *,
    selected_ids: tuple[str, ...] = (),
    deterministic_time: bool = False,
    evidence_index_path: Path | None = None,
) -> dict[str, Any]:
    catalog = load_catalog()
    selected = set(selected_ids)
    if selected - set(EXPECTED_SCENE_IDS):
        raise CatalogError("unknown V2 scene ID")
    root = _repository_root()
    evidence_index = load_external_evidence_index(
        root=root,
        index_path=evidence_index_path,
    )
    scenes = [
        _run_scene(
            scene,
            root=root,
            evidence_records=evidence_index["records"],
        )
        for scene in catalog["scenes"]
        if not selected or scene["scene_id"] in selected
    ]
    failed = [scene["scene_id"] for scene in scenes if scene["mechanics"] == "failed"]
    incomplete = [scene["scene_id"] for scene in scenes if not scene["complete"]]
    missing_evidence = sorted(
        {
            evidence_id
            for scene in scenes
            for evidence_id, status in scene["external_evidence_status"].items()
            if status["status"] != "satisfied"
        }
    )
    return {
        "schema_version": 1,
        "evaluation": "nunchi-v2-acceptance-scenes",
        "recorded_at": (
            DETERMINISTIC_TIME
            if deterministic_time
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "provenance": _provenance(root),
        "external_evidence_index": {
            "available": evidence_index["available"],
            "path": evidence_index["path"],
            "candidate_commit": evidence_index["candidate_commit"],
        },
        "scenes": scenes,
        "summary": {
            "selected": len(scenes),
            "mechanics_failed": failed,
            "incomplete": incomplete,
            "missing_external_evidence": missing_evidence,
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
    parser.add_argument(
        "--evidence-index",
        type=Path,
        help="Use an exact committed external-evidence index (default: evidence/v2/parity/external-evidence-index.json)",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Return non-zero while any mechanics or external-evidence requirement is incomplete",
    )
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
            evidence_index_path=arguments.evidence_index,
        )
    except (CatalogError, EvidenceIndexError) as exc:
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
    if record["summary"]["mechanics_failed"]:
        return 1
    if arguments.require_complete and not record["summary"]["candidate_complete"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
