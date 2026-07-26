"""Verify and transactionally apply Nunchi's exact Hermes V2 host seam."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any


class HostPatchError(RuntimeError):
    """The host seam cannot be verified or applied safely."""


@dataclass(frozen=True)
class HostPatchBundle:
    supported_hermes_commit: str
    patch_sha256: str
    patch_bytes: bytes
    post_apply_sha256: Mapping[str, str]

    @classmethod
    def from_paths(cls, manifest_path: Path, patch_path: Path) -> HostPatchBundle:
        try:
            manifest_bytes = Path(manifest_path).read_bytes()
            patch_bytes = Path(patch_path).read_bytes()
        except OSError as exc:
            raise HostPatchError("host-patch assets are unreadable") from exc
        return cls._from_bytes(manifest_bytes, patch_bytes)

    @classmethod
    def bundled(cls) -> HostPatchBundle:
        package = resources.files("nunchi_hermes_v2") / "host_patch_assets"
        try:
            manifest_bytes = (package / "manifest.json").read_bytes()
            manifest = json.loads(manifest_bytes)
            patch_name = manifest.get("patch")
            if not isinstance(patch_name, str) or Path(patch_name).name != patch_name:
                raise HostPatchError("host-patch manifest has an invalid patch name")
            patch_bytes = (package / patch_name).read_bytes()
        except HostPatchError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise HostPatchError("bundled host-patch assets are invalid") from exc
        return cls._from_manifest(manifest, patch_bytes)

    @classmethod
    def _from_bytes(cls, manifest_bytes: bytes, patch_bytes: bytes) -> HostPatchBundle:
        try:
            manifest = json.loads(manifest_bytes)
        except (TypeError, ValueError) as exc:
            raise HostPatchError("host-patch manifest is invalid JSON") from exc
        return cls._from_manifest(manifest, patch_bytes)

    @classmethod
    def _from_manifest(cls, manifest: Any, patch_bytes: bytes) -> HostPatchBundle:
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise HostPatchError("unsupported host-patch manifest schema")
        expected_patch_sha = manifest.get("patch_sha256")
        actual_patch_sha = hashlib.sha256(patch_bytes).hexdigest()
        if not isinstance(expected_patch_sha, str) or actual_patch_sha != expected_patch_sha:
            raise HostPatchError("host patch digest mismatch")
        commit = manifest.get("supported_hermes_commit")
        post_apply = manifest.get("post_apply_sha256")
        if not isinstance(commit, str) or len(commit) != 40:
            raise HostPatchError("host-patch manifest has an invalid Hermes commit")
        if not isinstance(post_apply, dict) or not post_apply:
            raise HostPatchError("host-patch manifest has no post-apply identities")
        normalized: dict[str, str] = {}
        for name, digest in post_apply.items():
            if not isinstance(name, str) or not _safe_relative_path(name):
                raise HostPatchError("host-patch manifest contains an unsafe path")
            if not isinstance(digest, str) or len(digest) != 64:
                raise HostPatchError("host-patch manifest contains an invalid file digest")
            normalized[name] = digest
        return cls(
            supported_hermes_commit=commit,
            patch_sha256=expected_patch_sha,
            patch_bytes=patch_bytes,
            post_apply_sha256=normalized,
        )


@dataclass(frozen=True)
class _Snapshot:
    existed: bool
    data: bytes | None
    mode: int | None


def _safe_relative_path(value: str) -> bool:
    parsed = PurePosixPath(value)
    return (
        bool(value)
        and not parsed.is_absolute()
        and ".." not in parsed.parts
        and parsed.as_posix() == value
    )


def _git(
    root: Path,
    *args: str,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.update({"LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"})
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=60,
        env=env,
    )
    if check and result.returncode != 0:
        raise HostPatchError(f"git {' '.join(args[:2])} failed")
    return result


def _validated_root(source: Path) -> Path:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise HostPatchError("Hermes source is not a directory")
    result = _git(root, "rev-parse", "--show-toplevel")
    try:
        discovered = Path(result.stdout.decode("utf-8").strip()).resolve()
    except (OSError, UnicodeError) as exc:
        raise HostPatchError("cannot resolve Hermes repository root") from exc
    if discovered != root:
        raise HostPatchError("Hermes source must be the repository root")
    return root


def _head(root: Path) -> str:
    try:
        return _git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    except UnicodeError as exc:
        raise HostPatchError("Hermes HEAD identity is invalid") from exc


def _path(root: Path, relative: str) -> Path:
    target = root / relative
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise HostPatchError(f"non-regular parent in touched path: {relative}")
    return target


def _validate_touched_paths(root: Path, bundle: HostPatchBundle) -> None:
    for relative in bundle.post_apply_sha256:
        target = _path(root, relative)
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HostPatchError(f"cannot inspect touched path: {relative}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise HostPatchError(f"non-regular touched path: {relative}")


def _clean(root: Path) -> bool:
    return not _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout


def _changed_paths(root: Path) -> set[str]:
    tracked = _git(root, "diff", "--name-only", "-z", "HEAD").stdout
    untracked = _git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    ).stdout
    try:
        return {
            item.decode("utf-8")
            for item in (tracked + untracked).split(b"\0")
            if item
        }
    except UnicodeError as exc:
        raise HostPatchError("Hermes source contains a non-UTF-8 changed path") from exc


def _post_apply_mismatches(root: Path, bundle: HostPatchBundle) -> list[str]:
    mismatches: list[str] = []
    for relative, expected in bundle.post_apply_sha256.items():
        target = _path(root, relative)
        try:
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode):
                mismatches.append(relative)
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            mismatches.append(relative)
            continue
        if actual != expected:
            mismatches.append(relative)
    return mismatches


def _verify_applied(root: Path, bundle: HostPatchBundle) -> None:
    mismatches = _post_apply_mismatches(root, bundle)
    if mismatches:
        raise HostPatchError("post-apply digest mismatch")
    expected_paths = set(bundle.post_apply_sha256)
    actual_paths = _changed_paths(root)
    if actual_paths != expected_paths:
        raise HostPatchError("post-apply changed-path set mismatch")


def inspect_host(source: Path, bundle: HostPatchBundle) -> dict[str, Any]:
    root = _validated_root(source)
    head = _head(root)
    if head != bundle.supported_hermes_commit:
        raise HostPatchError("unsupported Hermes commit")
    _validate_touched_paths(root, bundle)

    if not _post_apply_mismatches(root, bundle):
        _verify_applied(root, bundle)
        return _result(root, bundle, status="applied", changed=False)

    if not _clean(root):
        raise HostPatchError("Hermes source tree is not clean")
    check = _git(
        root,
        "apply",
        "--check",
        "--whitespace=error-all",
        "-",
        input_bytes=bundle.patch_bytes,
        check=False,
    )
    if check.returncode != 0:
        raise HostPatchError("host patch does not apply to the exact clean source")
    return _result(root, bundle, status="ready", changed=False)


def _snapshot(root: Path, bundle: HostPatchBundle) -> dict[str, _Snapshot]:
    snapshots: dict[str, _Snapshot] = {}
    for relative in bundle.post_apply_sha256:
        target = _path(root, relative)
        try:
            info = target.lstat()
        except FileNotFoundError:
            snapshots[relative] = _Snapshot(False, None, None)
            continue
        if not stat.S_ISREG(info.st_mode):
            raise HostPatchError(f"non-regular touched path: {relative}")
        snapshots[relative] = _Snapshot(True, target.read_bytes(), stat.S_IMODE(info.st_mode))
    return snapshots


def _restore(root: Path, snapshots: Mapping[str, _Snapshot]) -> None:
    failures: list[str] = []
    for relative, snapshot in snapshots.items():
        target = _path(root, relative)
        try:
            if not snapshot.existed:
                if target.exists() or target.is_symlink():
                    info = target.lstat()
                    if not stat.S_ISREG(info.st_mode):
                        raise OSError("refusing to remove non-regular rollback target")
                    target.unlink()
                continue
            if snapshot.data is None or snapshot.mode is None:
                raise OSError("invalid rollback snapshot")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.nunchi-rollback-{os.getpid()}")
            temporary.write_bytes(snapshot.data)
            temporary.chmod(snapshot.mode)
            os.replace(temporary, target)
        except OSError:
            failures.append(relative)
    if failures:
        raise HostPatchError("host patch failed and rollback failed")


def apply_host_patch(source: Path, bundle: HostPatchBundle) -> dict[str, Any]:
    state = inspect_host(source, bundle)
    if state["status"] == "applied":
        return state
    root = Path(state["hermes_source"])
    snapshots = _snapshot(root, bundle)
    try:
        applied = _git(
            root,
            "apply",
            "--whitespace=error-all",
            "-",
            input_bytes=bundle.patch_bytes,
            check=False,
        )
        if applied.returncode != 0:
            raise HostPatchError("host patch application failed")
        _validate_touched_paths(root, bundle)
        _verify_applied(root, bundle)
    except BaseException as exc:
        try:
            _restore(root, snapshots)
        except HostPatchError as rollback_exc:
            raise rollback_exc from exc
        raise HostPatchError("host patch verification failed; mutation rolled back") from exc
    return _result(root, bundle, status="applied", changed=True)


def _result(
    root: Path,
    bundle: HostPatchBundle,
    *,
    status: str,
    changed: bool,
) -> dict[str, Any]:
    return {
        "changed": changed,
        "hermes_commit": bundle.supported_hermes_commit,
        "hermes_source": str(root),
        "patch_sha256": bundle.patch_sha256,
        "status": status,
        "touched_files": len(bundle.post_apply_sha256),
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="nunchi-hermes-v2-host-patch",
        description="Verify or transactionally apply Nunchi's exact Hermes V2 host seam.",
    )
    command.add_argument("--hermes-source", required=True, type=Path)
    action = command.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="verify readiness or exact applied state")
    action.add_argument("--apply", action="store_true", help="apply and verify the exact host seam")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        bundle = HostPatchBundle.bundled()
        result = (
            apply_host_patch(args.hermes_source, bundle)
            if args.apply
            else inspect_host(args.hermes_source, bundle)
        )
    except HostPatchError as exc:
        print(f"nunchi-hermes-v2-host-patch: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
