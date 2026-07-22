from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_BASE = "8e64746970f9910d03b372291c5aa173883e869f"
EXPECTED_HERMES_COMMIT = "279be8211d8347cc3500b9a78c6a0f8cb4d92a6a"
EXPECTED_HERMES_VERSION = "0.19.0"
REQUIRED_PATHS = (
    "integrations/hermes/nunchi-gate/__init__.py",
    "integrations/hermes/nunchi-gate/v2_runtime.py",
    "integrations/hermes/nunchi-gate/v2_plugin.py",
    "integrations/hermes/nunchi-gate/plugin.yaml",
    "integrations/hermes/README.md",
    "docs/integrations/hermes-v2.md",
    "tests/v2/test_hermes.py",
    "tests/v2/test_hermes_eval.py",
    "tests/fixtures/v2/hermes/cases.json",
    "evals/v2/hermes/scenes.jsonl",
    "evals/v2/hermes/runner.py",
    "evidence/v2/hermes/hermes-scenes.jsonl",
    "evidence/v2/hermes/telegram-scenes.jsonl",
    "evidence/v2/hermes/installed-runtime.md",
    "evidence/v2/hermes/verification.md",
    "evidence/v2/hermes/handoff.md",
    "evidence/v2/hermes/candidate-files.sha256",
)
EXPECTED_CASES = {f"HM-{index:02d}" for index in range(1, 7)}
REQUIRED_LIFECYCLE_PATHS = (
    "evidence/v2/hermes/slice-activation.md",
    "evidence/v2/hermes/slice-candidate.md",
    "evidence/v2/hermes/slice-handoff.md",
)


def _git_output(source: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=source, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _scene_errors(rows: list[dict], catalog_rows: list[dict]) -> list[str]:
    errors: list[str] = []
    case_ids = [row.get("hm_case_id") for row in rows]
    if set(case_ids) != EXPECTED_CASES:
        errors.append(f"hm-case-set:{sorted(str(value) for value in set(case_ids))}")
    if len(case_ids) != len(set(case_ids)):
        errors.append("hm-case-duplicate")
    catalog = {row.get("hm_case_id"): row for row in catalog_rows}
    for row in rows:
        case_id = row.get("hm_case_id")
        if row.get("result") != "PASS":
            errors.append(f"hm-result-not-pass:{case_id}")
        assertions = row.get("assertions")
        if not isinstance(assertions, dict) or not assertions:
            errors.append(f"hm-assertions-missing:{case_id}")
        else:
            for name, value in assertions.items():
                if value is not True:
                    errors.append(f"hm-assertion-not-true:{case_id}:{name}")
        expected = catalog.get(case_id)
        if expected is None:
            continue
        for field in ("scene_id", "claim", "evidence_grade"):
            if row.get(field) != expected.get(field):
                errors.append(f"hm-catalog-mismatch:{case_id}:{field}")
    return errors


def _candidate_paths(root: Path) -> set[str]:
    base = "HEAD"
    if subprocess.run(
        ["git", "cat-file", "-e", f"{CANDIDATE_BASE}^{{commit}}"],
        cwd=root,
        capture_output=True,
    ).returncode == 0:
        base = CANDIDATE_BASE
    changed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", base, "--"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    raw = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root, check=True, capture_output=True,
    ).stdout.decode()
    paths: set[str] = {path for path in changed if path}
    for entry in raw.split("\0"):
        if not entry:
            continue
        relative = entry[3:]
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        if entry.startswith("?? ") and relative != "evidence/v2/hermes/candidate-files.sha256":
            paths.add(relative)
    paths.discard("evidence/v2/hermes/candidate-files.sha256")
    return paths


def _lifecycle_errors(root: Path) -> list[str]:
    missing = [
        f"missing-lifecycle:{relative}"
        for relative in REQUIRED_LIFECYCLE_PATHS
        if not (root / relative).is_file()
        or (root / relative).stat().st_size == 0
    ]
    if missing:
        return missing
    checker = root / "scripts/check_governance.py"
    result = subprocess.run(
        [sys.executable, str(checker), "--check-cli"],
        cwd=root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return ["lifecycle-governance-invalid"]
    return []


def validate(
    *,
    hermes_source: Path,
    require_lifecycle: bool = False,
    root: Path = ROOT,
) -> list[str]:
    errors = []
    for relative in REQUIRED_PATHS:
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing-or-empty:{relative}")
    if require_lifecycle:
        errors.extend(_lifecycle_errors(root))

    scenes_path = root / "evidence/v2/hermes/hermes-scenes.jsonl"
    catalog_path = root / "evals/v2/hermes/scenes.jsonl"
    rows = []
    if scenes_path.is_file():
        try:
            rows = [
                json.loads(line)
                for line in scenes_path.read_text().splitlines()
                if line.strip()
            ]
        except (OSError, ValueError) as exc:
            errors.append(f"invalid-scenes:{type(exc).__name__}")
    catalog_rows = []
    if catalog_path.is_file():
        try:
            catalog_rows = [
                json.loads(line)
                for line in catalog_path.read_text().splitlines()
                if line.strip()
            ]
        except (OSError, ValueError) as exc:
            errors.append(f"invalid-scene-catalog:{type(exc).__name__}")
    errors.extend(_scene_errors(rows, catalog_rows))

    manifest_path = root / "evidence/v2/hermes/candidate-files.sha256"
    if manifest_path.is_file():
        listed = 0
        listed_paths: set[str] = set()
        for line in manifest_path.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            try:
                expected, relative = line.split("  ", 1)
            except ValueError:
                errors.append("candidate-manifest-shape")
                continue
            if relative in listed_paths:
                errors.append(f"candidate-manifest-duplicate:{relative}")
            listed_paths.add(relative)
            if expected != "DELETE" and not re.fullmatch(r"[0-9a-f]{64}", expected):
                errors.append(f"candidate-manifest-hash-shape:{relative}")
            candidate_path = root / relative
            if expected == "DELETE":
                if candidate_path.exists():
                    errors.append(f"candidate-manifest-not-deleted:{relative}")
                listed += 1
                continue
            if not candidate_path.is_file():
                errors.append(f"candidate-manifest-missing:{relative}")
                continue
            actual = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            if actual != expected:
                errors.append(f"candidate-manifest-digest:{relative}")
            listed += 1
        if listed == 0:
            errors.append("candidate-manifest-empty")
        try:
            candidate_paths = _candidate_paths(root)
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"candidate-git-status:{type(exc).__name__}")
        else:
            for relative in sorted(candidate_paths - listed_paths):
                errors.append(f"candidate-manifest-omitted:{relative}")
            for relative in sorted(listed_paths - candidate_paths):
                errors.append(f"candidate-manifest-extra:{relative}")

    telegram_path = root / "evidence/v2/hermes/telegram-scenes.jsonl"
    if telegram_path.is_file():
        telegram = [json.loads(line) for line in telegram_path.read_text().splitlines() if line.strip()]
        hm05 = next((row for row in rows if row.get("hm_case_id") == "HM-05"), None)
        if len(telegram) != 1 or telegram[0] != hm05:
            errors.append("telegram-evidence-shape")

    plugin = (root / "integrations/hermes/nunchi-gate/plugin.yaml")
    if plugin.is_file():
        manifest = plugin.read_text()
        for token in ("version: 2.0.0", "- pre_gateway_dispatch", "- pre_llm_call", "- tool_execution"):
            if token not in manifest:
                errors.append(f"manifest-token:{token}")

    for relative in (
        "docs/integrations/hermes-v2.md",
        "integrations/hermes/README.md",
        "evidence/v2/hermes/installed-runtime.md",
        "evidence/v2/hermes/verification.md",
        "evidence/v2/hermes/handoff.md",
    ):
        path = root / relative
        if path.is_file():
            text = path.read_text()
            documented = set(
                re.findall(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", text)
            )
            allowed = {EXPECTED_HERMES_COMMIT, CANDIDATE_BASE}
            expected_fields = {
                "Installed Hermes version": EXPECTED_HERMES_VERSION,
                "Installed Hermes commit": EXPECTED_HERMES_COMMIT,
                "Candidate base": CANDIDATE_BASE,
            }
            fields_match = all(
                re.findall(
                    rf"(?m)^- {re.escape(label)}: `([^`\n]+)`\s*$",
                    text,
                )
                == [expected]
                for label, expected in expected_fields.items()
            )
            if not fields_match or documented - allowed:
                errors.append(f"hermes-provenance:{relative}")

    try:
        commit = _git_output(hermes_source, "rev-parse", "HEAD")
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append(f"hermes-git:{type(exc).__name__}")
    else:
        if commit != EXPECTED_HERMES_COMMIT:
            errors.append(f"hermes-commit:{commit}")

    try:
        with (hermes_source / "pyproject.toml").open("rb") as handle:
            installed_version = tomllib.load(handle)["project"]["version"]
    except (KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"hermes-version:{type(exc).__name__}")
    else:
        if installed_version != EXPECTED_HERMES_VERSION:
            errors.append(f"hermes-version:{installed_version}")

    try:
        installed_status = _git_output(
            hermes_source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append(f"hermes-status:{type(exc).__name__}")
    else:
        status_lines = installed_status.splitlines()
        if any(not line.startswith("?? ") for line in status_lines):
            errors.append("hermes-tracked-dirty")
        for line in status_lines:
            if line.startswith("?? ") and line[3:] != ".install_method":
                errors.append(f"hermes-untracked:{line[3:]}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Hermes V2 pre-activation draft review packet"
    )
    parser.add_argument("--hermes-source", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    errors = validate(
        hermes_source=args.hermes_source,
        require_lifecycle=args.require_complete,
    )
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    if args.require_complete:
        print("Hermes V2 packet: handoff-complete")
    else:
        print(
            "Hermes V2 draft review packet: internally consistent; "
            "lifecycle not evaluated; not a canonical candidate"
        )
    print("HM cases: HM-01 HM-02 HM-03 HM-04 HM-05 HM-06")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
