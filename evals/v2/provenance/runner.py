"""Build, install, and audit the exact Nunchi V2 product candidate.

The first use is intentionally diagnostic: a mixed V1/V2 repository returns a
non-zero result with exact residue and console-surface findings.  Once the
atomic candidate is assembled, the same command builds a wheel without network
or dependency resolution, installs it in a fresh virtual environment, compares
installed metadata and scripts to the frozen surface contract, and probes every
entry point's import-safe ``--help`` path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any


DETERMINISTIC_TIME = "1970-01-01T00:00:00Z"


class ProvenanceAuditError(ValueError):
    pass


def load_surface_contract() -> dict[str, Any]:
    resource = resources.files("evals.v2.provenance").joinpath("surfaces.json")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProvenanceAuditError("V2 surface contract is unreadable") from exc
    required_fields = {
        "schema_version",
        "product_version_major",
        "required_scripts",
        "removed_scripts",
        "forbidden_runtime_symbols",
        "forbidden_runtime_fragments",
    }
    if not isinstance(document, dict) or set(document) != required_fields:
        raise ProvenanceAuditError("V2 surface contract root is invalid")
    if document["schema_version"] != 1 or document["product_version_major"] != 2:
        raise ProvenanceAuditError("V2 surface contract version is invalid")
    for field in ("required_scripts", "removed_scripts"):
        value = document[field]
        if (
            not isinstance(value, dict)
            or not value
            or any(
                not isinstance(key, str)
                or not key
                or not isinstance(item, str)
                or not item
                for key, item in value.items()
            )
        ):
            raise ProvenanceAuditError("V2 surface contract scripts are invalid")
    if set(document["required_scripts"]) & set(document["removed_scripts"]):
        raise ProvenanceAuditError("V2 surface contract script sets overlap")
    for field in ("forbidden_runtime_symbols", "forbidden_runtime_fragments"):
        value = document[field]
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item for item in value)
            or len(set(value)) != len(value)
        ):
            raise ProvenanceAuditError("V2 residue contract is invalid")
    return document


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_project(root: Path) -> dict[str, Any]:
    try:
        with (root / "pyproject.toml").open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProvenanceAuditError("pyproject.toml is unreadable") from exc
    try:
        project = document["project"]
        scripts = project["scripts"]
        version = project["version"]
    except (KeyError, TypeError) as exc:
        raise ProvenanceAuditError("project metadata is incomplete") from exc
    if not isinstance(scripts, dict) or not isinstance(version, str):
        raise ProvenanceAuditError("project metadata is invalid")
    return {"version": version, "scripts": dict(scripts)}


def _version_major(version: str) -> int | None:
    match = re.match(r"^([0-9]+)(?:\.|$)", version)
    return int(match.group(1)) if match else None


def _runtime_files(root: Path) -> list[Path]:
    """Return ordinary product runtime sources, excluding docs/tests/evidence.

    The wheel is only one product surface. Hermes, Claude Code, Codex, and
    transport packets also execute from ``integrations`` before or during
    installation, so a source-only scan could falsely report a V1-clean
    repository while a live hook or dashboard still exposed the old gate.
    """
    suffixes = frozenset({".py", ".js", ".json", ".sh", ".yaml", ".yml"})
    roots = (root / "src" / "nunchi", root / "integrations")
    return sorted(
        path
        for runtime_root in roots
        if runtime_root.is_dir()
        for path in runtime_root.rglob("*")
        if path.is_file()
        and path.suffix in suffixes
        and "__pycache__" not in path.parts
    )


def _residue_findings(root: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    symbol_patterns = [
        (symbol, re.compile(rf"\b{re.escape(symbol)}\b"))
        for symbol in contract["forbidden_runtime_symbols"]
    ]
    for path in _runtime_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            relative = str(path.relative_to(root))
            grouped[(relative, "unreadable-runtime-source", "unavailable")] = {
                "path": relative,
                "first_line": None,
                "occurrences": 1,
                "kind": "unreadable-runtime-source",
                "match": "unavailable",
            }
            continue
        relative = str(path.relative_to(root))
        for line_number, line in enumerate(lines, start=1):
            for symbol, pattern in symbol_patterns:
                if pattern.search(line):
                    key = (relative, "forbidden-v1-symbol", symbol)
                    finding = grouped.setdefault(
                        key,
                        {
                            "path": relative,
                            "first_line": line_number,
                            "occurrences": 0,
                            "kind": "forbidden-v1-symbol",
                            "match": symbol,
                        },
                    )
                    finding["occurrences"] += 1
            for fragment in contract["forbidden_runtime_fragments"]:
                if fragment in line:
                    key = (relative, "forbidden-v1-fragment", fragment)
                    finding = grouped.setdefault(
                        key,
                        {
                            "path": relative,
                            "first_line": line_number,
                            "occurrences": 0,
                            "kind": "forbidden-v1-fragment",
                            "match": fragment,
                        },
                    )
                    finding["occurrences"] += 1
    return [grouped[key] for key in sorted(grouped)]


def audit_repository(root: Path | None = None) -> dict[str, Any]:
    root = (root or _repository_root()).resolve()
    contract = load_surface_contract()
    project = _read_project(root)
    expected = contract["required_scripts"]
    removed = contract["removed_scripts"]
    scripts = project["scripts"]
    missing = sorted(name for name in expected if name not in scripts)
    wrong_targets = {
        name: {"expected": target, "observed": scripts.get(name)}
        for name, target in expected.items()
        if name in scripts and scripts[name] != target
    }
    unexpected = sorted(set(scripts) - set(expected))
    forbidden_present = sorted(set(scripts) & set(removed))
    version_major = _version_major(project["version"])
    residue = _residue_findings(root, contract)
    failures: list[str] = []
    if version_major != contract["product_version_major"]:
        failures.append("product-version-not-v2")
    if missing:
        failures.append("required-entrypoints-missing")
    if wrong_targets:
        failures.append("entrypoint-target-mismatch")
    if unexpected:
        failures.append("unexpected-entrypoints-present")
    if forbidden_present:
        failures.append("removed-entrypoints-present")
    if residue:
        failures.append("v1-runtime-residue-present")
    return {
        "project_version": project["version"],
        "expected_product_version_major": contract["product_version_major"],
        "required_scripts": expected,
        "observed_scripts": scripts,
        "missing_scripts": missing,
        "wrong_targets": wrong_targets,
        "unexpected_scripts": unexpected,
        "removed_scripts_present": forbidden_present,
        "residue_findings": residue,
        "failures": failures,
        "passed": not failures,
    }


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


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
            "passed": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "command timed out",
            "passed": False,
        }
    except OSError:
        return {
            "command": command,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "command could not start",
            "passed": False,
        }


def _installed_metadata(
    python: Path,
    root: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    code = (
        "import importlib.metadata as m,json;"
        "d=m.distribution('nunchi');"
        "e={x.name:x.value for x in d.entry_points if x.group=='console_scripts'};"
        "print(json.dumps({'version':d.version,'scripts':e},sort_keys=True))"
    )
    result = _run_command(
        [str(python), "-I", "-c", code],
        cwd=root,
        timeout=20,
        environment=environment,
    )
    if not result["passed"]:
        return {"probe": result, "metadata": None}
    try:
        metadata = json.loads(result["stdout_tail"])
    except json.JSONDecodeError:
        metadata = None
    return {"probe": result, "metadata": metadata}


def _minimal_environment() -> dict[str, str]:
    allowed = (
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "TERM",
    )
    return {name: os.environ[name] for name in allowed if name in os.environ}


def _expected_package_inventory(root: Path) -> list[str]:
    package = root / "src" / "nunchi"
    return sorted(
        path.relative_to(root / "src").as_posix()
        for path in package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def _wheel_package_inventory(wheel: Path, root: Path) -> dict[str, Any]:
    expected = _expected_package_inventory(root)
    try:
        with zipfile.ZipFile(wheel) as archive:
            observed = sorted(
                name
                for name in archive.namelist()
                if name.startswith("nunchi/")
                and not name.endswith("/")
                and "/__pycache__/" not in name
                and not name.endswith(".pyc")
            )
    except (OSError, zipfile.BadZipFile):
        return {
            "expected": expected,
            "observed": None,
            "missing": expected,
            "unexpected": [],
            "matches_source": False,
            "error": "wheel-inventory-unreadable",
        }
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    return {
        "expected": expected,
        "observed": observed,
        "missing": missing,
        "unexpected": unexpected,
        "matches_source": not missing and not unexpected,
    }


def build_and_probe(root: Path | None = None) -> dict[str, Any]:
    root = (root or _repository_root()).resolve()
    contract = load_surface_contract()
    with tempfile.TemporaryDirectory(prefix="nunchi-v2-install-") as temporary:
        temporary_path = Path(temporary)
        wheel_dir = temporary_path / "wheel"
        wheel_dir.mkdir()
        environment = _minimal_environment()
        uv = shutil.which("uv")
        build_command = (
            [
                uv,
                "build",
                "--wheel",
                "--offline",
                "--out-dir",
                str(wheel_dir),
                ".",
            ]
            if uv is not None
            else [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheel_dir),
                ".",
            ]
        )
        build = _run_command(
            build_command,
            cwd=root,
            timeout=300,
            environment=environment,
        )
        if not build["passed"]:
            return {"build": build, "wheel": None, "install": None, "passed": False}
        wheels = sorted(wheel_dir.glob("nunchi-*.whl"))
        if len(wheels) != 1:
            return {
                "build": build,
                "wheel": None,
                "install": None,
                "failure": "build did not produce exactly one Nunchi wheel",
                "passed": False,
            }
        wheel = wheels[0]
        wheel_digest = "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()
        package_inventory = _wheel_package_inventory(wheel, root)
        create_venv = _run_command(
            [sys.executable, "-m", "venv", str(temporary_path / "venv")],
            cwd=root,
            timeout=120,
            environment=environment,
        )
        bin_dir = temporary_path / "venv" / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        if not create_venv["passed"]:
            return {
                "build": build,
                "wheel": {"filename": wheel.name, "digest": wheel_digest},
                "package_inventory": package_inventory,
                "create_venv": create_venv,
                "install": None,
                "passed": False,
            }
        install = _run_command(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                str(wheel),
            ],
            cwd=root,
            timeout=120,
            environment=environment,
        )
        if not install["passed"]:
            return {
                "build": build,
                "wheel": {"filename": wheel.name, "digest": wheel_digest},
                "package_inventory": package_inventory,
                "create_venv": create_venv,
                "install": install,
                "passed": False,
            }
        installed = _installed_metadata(python, root, environment)
        metadata = installed["metadata"] or {}
        expected_scripts = contract["required_scripts"]
        metadata_matches = (
            _version_major(str(metadata.get("version", "")))
            == contract["product_version_major"]
            and metadata.get("scripts") == expected_scripts
        )
        help_probes = []
        for script in expected_scripts:
            executable = bin_dir / (f"{script}.exe" if os.name == "nt" else script)
            help_probes.append(
                {
                    "script": script,
                    **_run_command(
                        [str(executable), "--help"],
                        cwd=temporary_path,
                        timeout=20,
                        environment=environment,
                    ),
                }
            )
        return {
            "build": build,
            "wheel": {"filename": wheel.name, "digest": wheel_digest},
            "package_inventory": package_inventory,
            "create_venv": create_venv,
            "install": install,
            "installed_metadata": installed,
            "metadata_matches_surface_contract": metadata_matches,
            "help_probes": help_probes,
            "passed": (
                package_inventory["matches_source"]
                and metadata_matches
                and all(probe["passed"] for probe in help_probes)
            ),
        }


def run(*, install_probe: bool, deterministic_time: bool = False) -> dict[str, Any]:
    root = _repository_root()
    status = _git_value(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
        allow_empty=True,
    )
    repository = audit_repository(root)
    installed = build_and_probe(root) if install_probe else None
    passed = repository["passed"] and (installed is None or installed["passed"])
    return {
        "schema_version": 1,
        "evaluation": "nunchi-v2-installed-provenance",
        "recorded_at": (
            DETERMINISTIC_TIME
            if deterministic_time
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "source": {
            "commit": _git_value(root, "rev-parse", "HEAD") or "unavailable",
            "worktree_clean": status == "" if status is not None else None,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "repository_audit": repository,
        "clean_install_probe": installed,
        "summary": {
            "repository_passed": repository["passed"],
            "install_probe_requested": install_probe,
            "install_probe_passed": installed["passed"] if installed is not None else None,
            "candidate_complete": passed,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.v2.provenance.runner",
        description="Audit V2 console surfaces, V1 residue, and an optional clean wheel install.",
    )
    parser.add_argument("--install", action="store_true", help="Build and probe a clean wheel install")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--deterministic-time", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        record = run(
            install_probe=arguments.install,
            deterministic_time=arguments.deterministic_time,
        )
    except ProvenanceAuditError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(serialized)
    else:
        try:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            with arguments.output.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
        except FileExistsError:
            print("provenance output already exists", file=sys.stderr)
            return 2
        except OSError:
            print("could not create provenance output", file=sys.stderr)
            return 2
    return 0 if record["summary"]["candidate_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
