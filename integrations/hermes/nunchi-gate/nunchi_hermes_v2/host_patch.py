"""Verify and transactionally apply Nunchi's exact Hermes V2 host seam."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, Literal

try:
    import fcntl
except ImportError:  # pragma: no cover - the supported Hermes seam is POSIX-only
    fcntl = None


# Updated only when the reviewed bundled manifest is intentionally regenerated.
BUNDLED_MANIFEST_SHA256 = "243a8fa6961519d6008df81a73e16a9910d98eb0fda99d3958511937df7806cf"


class HostPatchError(RuntimeError):
    """The host seam cannot be verified or applied safely."""


@dataclass(frozen=True)
class HostPatchFile:
    operation: Literal["create", "modify", "delete"]
    pre_sha256: str | None
    pre_mode: str | None
    post_sha256: str | None
    post_mode: str | None


@dataclass(frozen=True)
class HostPatchBundle:
    supported_hermes_commit: str
    manifest_sha256: str
    patch_sha256: str
    patch_bytes: bytes
    files: Mapping[str, HostPatchFile]

    @property
    def post_apply_sha256(self) -> Mapping[str, str]:
        return {
            path: spec.post_sha256
            for path, spec in self.files.items()
            if spec.post_sha256 is not None
        }

    @classmethod
    def from_paths(
        cls,
        manifest_path: Path,
        patch_path: Path,
        *,
        expected_manifest_sha256: str | None = None,
    ) -> HostPatchBundle:
        try:
            manifest_bytes = Path(manifest_path).read_bytes()
            patch_bytes = Path(patch_path).read_bytes()
        except OSError as exc:
            raise HostPatchError("host-patch assets are unreadable") from exc
        return cls._from_bytes(
            manifest_bytes,
            patch_bytes,
            expected_manifest_sha256=expected_manifest_sha256,
        )

    @classmethod
    def bundled(cls) -> HostPatchBundle:
        package = resources.files("nunchi_hermes_v2") / "host_patch_assets"
        try:
            manifest_bytes = (package / "manifest.json").read_bytes()
        except OSError as exc:
            raise HostPatchError("bundled host-patch manifest is unreadable") from exc
        actual_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        if actual_manifest_sha != BUNDLED_MANIFEST_SHA256:
            raise HostPatchError("bundled host-patch manifest identity mismatch")
        try:
            manifest = json.loads(manifest_bytes)
            patch_name = manifest.get("patch")
            if not isinstance(patch_name, str) or Path(patch_name).name != patch_name:
                raise HostPatchError("host-patch manifest has an invalid patch name")
            patch_bytes = (package / patch_name).read_bytes()
        except HostPatchError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise HostPatchError("bundled host-patch assets are invalid") from exc
        return cls._from_manifest(
            manifest,
            manifest_sha256=actual_manifest_sha,
            patch_bytes=patch_bytes,
        )

    @classmethod
    def _from_bytes(
        cls,
        manifest_bytes: bytes,
        patch_bytes: bytes,
        *,
        expected_manifest_sha256: str | None = None,
    ) -> HostPatchBundle:
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
            raise HostPatchError("host-patch manifest identity mismatch")
        try:
            manifest = json.loads(manifest_bytes)
        except (TypeError, ValueError) as exc:
            raise HostPatchError("host-patch manifest is invalid JSON") from exc
        return cls._from_manifest(
            manifest,
            manifest_sha256=manifest_sha,
            patch_bytes=patch_bytes,
        )

    @classmethod
    def _from_manifest(
        cls,
        manifest: Any,
        *,
        manifest_sha256: str,
        patch_bytes: bytes,
    ) -> HostPatchBundle:
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
            raise HostPatchError("unsupported host-patch manifest schema")
        allowed_keys = {
            "schema_version",
            "patch",
            "patch_sha256",
            "supported_hermes_commit",
            "files",
            "source",
        }
        if not set(manifest).issubset(allowed_keys):
            raise HostPatchError("host-patch manifest has unknown fields")
        expected_patch_sha = manifest.get("patch_sha256")
        actual_patch_sha = hashlib.sha256(patch_bytes).hexdigest()
        if not isinstance(expected_patch_sha, str) or actual_patch_sha != expected_patch_sha:
            raise HostPatchError("host patch digest mismatch")
        commit = manifest.get("supported_hermes_commit")
        raw_files = manifest.get("files")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise HostPatchError("host-patch manifest has an invalid Hermes commit")
        if not isinstance(raw_files, dict) or not raw_files:
            raise HostPatchError("host-patch manifest has no file identities")
        files: dict[str, HostPatchFile] = {}
        for name, raw in raw_files.items():
            if not isinstance(name, str) or not _safe_relative_path(name):
                raise HostPatchError("host-patch manifest contains an unsafe path")
            if not isinstance(raw, dict) or set(raw) != {
                "operation",
                "pre_sha256",
                "pre_mode",
                "post_sha256",
                "post_mode",
            }:
                raise HostPatchError("host-patch manifest contains an invalid file record")
            operation = raw.get("operation")
            if operation not in {"create", "modify", "delete"}:
                raise HostPatchError("host-patch manifest contains an invalid operation")
            pre_sha = _optional_digest(raw.get("pre_sha256"))
            post_sha = _optional_digest(raw.get("post_sha256"))
            pre_mode = _optional_mode(raw.get("pre_mode"))
            post_mode = _optional_mode(raw.get("post_mode"))
            if operation == "create" and (pre_sha is not None or pre_mode is not None):
                raise HostPatchError("create operation has a pre-apply identity")
            if operation == "delete" and (post_sha is not None or post_mode is not None):
                raise HostPatchError("delete operation has a post-apply identity")
            if operation == "modify" and None in {pre_sha, pre_mode, post_sha, post_mode}:
                raise HostPatchError("modify operation has an incomplete identity")
            if operation == "create" and None in {post_sha, post_mode}:
                raise HostPatchError("create operation has an incomplete identity")
            if operation == "delete" and None in {pre_sha, pre_mode}:
                raise HostPatchError("delete operation has an incomplete identity")
            files[name] = HostPatchFile(
                operation=operation,
                pre_sha256=pre_sha,
                pre_mode=pre_mode,
                post_sha256=post_sha,
                post_mode=post_mode,
            )
        patch_shape = _parse_patch_shape(patch_bytes)
        if set(patch_shape) != set(files):
            raise HostPatchError("host patch and manifest closed path/mode set mismatch")
        for path, (operation, patch_pre_mode, patch_post_mode) in patch_shape.items():
            spec = files[path]
            if operation != spec.operation:
                raise HostPatchError("host patch and manifest closed path/mode set mismatch")
            if operation == "modify" and patch_pre_mode is None and patch_post_mode is None:
                if spec.pre_mode != spec.post_mode:
                    raise HostPatchError("host patch and manifest closed path/mode set mismatch")
            elif (patch_pre_mode, patch_post_mode) != (spec.pre_mode, spec.post_mode):
                raise HostPatchError("host patch and manifest closed path/mode set mismatch")
        return cls(
            supported_hermes_commit=commit,
            manifest_sha256=manifest_sha256,
            patch_sha256=expected_patch_sha,
            patch_bytes=patch_bytes,
            files=files,
        )


@dataclass(frozen=True)
class _TreeEntry:
    mode: str
    oid: str


@dataclass(frozen=True)
class _Snapshot:
    existed: bool
    data: bytes | None
    mode: int | None


def _optional_digest(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise HostPatchError("host-patch manifest contains an invalid file digest")
    return value


def _optional_mode(value: Any) -> str | None:
    if value is None:
        return None
    if value not in {"100644", "100755"}:
        raise HostPatchError("host-patch manifest contains an invalid file mode")
    return value


def _safe_relative_path(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value:
        return False
    parsed = PurePosixPath(value)
    return (
        not parsed.is_absolute()
        and all(part not in {"", ".", ".."} for part in parsed.parts)
        and parsed.as_posix() == value
    )


def _parse_patch_shape(
    patch_bytes: bytes,
) -> dict[str, tuple[str, str | None, str | None]]:
    try:
        text = patch_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise HostPatchError("host patch is not UTF-8 text") from exc
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts or starts[0] != 0:
        raise HostPatchError("host patch has no closed diff set")
    starts.append(len(lines))
    result: dict[str, tuple[str, str | None, str | None]] = {}
    header_pattern = re.compile(r"diff --git a/([A-Za-z0-9_.\-/]+) b/([A-Za-z0-9_.\-/]+)$")
    for begin, end in zip(starts, starts[1:]):
        block = lines[begin:end]
        match = header_pattern.fullmatch(block[0])
        if match is None or match.group(1) != match.group(2):
            raise HostPatchError("host patch contains an unsupported or unsafe path")
        path = match.group(1)
        if not _safe_relative_path(path) or path in result:
            raise HostPatchError("host patch contains a duplicate or unsafe path")
        if any(
            line.startswith(("rename from ", "rename to ", "copy from ", "copy to "))
            for line in block
        ):
            raise HostPatchError("host patch contains an unsupported rename or copy")
        new_modes = [line.removeprefix("new file mode ") for line in block if line.startswith("new file mode ")]
        deleted_modes = [
            line.removeprefix("deleted file mode ")
            for line in block
            if line.startswith("deleted file mode ")
        ]
        old_modes = [line.removeprefix("old mode ") for line in block if line.startswith("old mode ")]
        changed_modes = [line.removeprefix("new mode ") for line in block if line.startswith("new mode ")]
        if len(new_modes) > 1 or len(deleted_modes) > 1 or len(old_modes) > 1 or len(changed_modes) > 1:
            raise HostPatchError("host patch contains ambiguous modes")
        if new_modes:
            operation = "create"
            pre_mode = None
            post_mode = new_modes[0]
        elif deleted_modes:
            operation = "delete"
            pre_mode = deleted_modes[0]
            post_mode = None
        else:
            operation = "modify"
            pre_mode = old_modes[0] if old_modes else None
            post_mode = changed_modes[0] if changed_modes else pre_mode
        result[path] = (operation, pre_mode, post_mode)
    return result


def _git_env() -> dict[str, str]:
    """Return an operator environment with Git identity redirects removed."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "LC_ALL": "C",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return env


def _git(
    root: Path,
    *args: str,
    input_bytes: bytes | None = None,
    check: bool = True,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = _git_env()
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            input=input_bytes,
            capture_output=True,
            check=False,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostPatchError(f"git {' '.join(args[:2])} failed") from exc
    if check and result.returncode != 0:
        raise HostPatchError(f"git {' '.join(args[:2])} failed")
    return result


def _validated_root(source: Path) -> Path:
    requested = Path(source).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    try:
        requested_info = requested.lstat()
    except OSError as exc:
        raise HostPatchError("cannot inspect Hermes source path") from exc
    if stat.S_ISLNK(requested_info.st_mode):
        raise HostPatchError("Hermes source path must not be a symlink")
    root = requested.resolve()
    if not root.is_dir():
        raise HostPatchError("Hermes source is not a directory")
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise HostPatchError("cannot inspect Hermes repository directory") from exc
    _verify_owned_directory(root_info)
    try:
        git_info = (root / ".git").lstat()
        index_info = (root / ".git" / "index").lstat()
    except OSError as exc:
        raise HostPatchError("Hermes repository metadata is unavailable") from exc
    _verify_owned_directory(git_info)
    if (
        not stat.S_ISREG(index_info.st_mode)
        or index_info.st_uid != os.getuid()
        or stat.S_IMODE(index_info.st_mode) & 0o022
    ):
        raise HostPatchError("Hermes repository index type, ownership, or mode mismatch")
    result = _git(root, "rev-parse", "--show-toplevel")
    try:
        discovered = Path(result.stdout.decode("utf-8").strip()).resolve()
    except (OSError, UnicodeError) as exc:
        raise HostPatchError("cannot resolve Hermes repository root") from exc
    if discovered != root:
        raise HostPatchError("Hermes source must be the repository root")
    return root


def _verify_owned_directory(info: os.stat_result) -> None:
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise HostPatchError("Hermes repository directory ownership mismatch")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise HostPatchError("Hermes repository directory mode is group/other writable")


def _head(root: Path) -> str:
    try:
        return _git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    except UnicodeError as exc:
        raise HostPatchError("Hermes HEAD identity is invalid") from exc


def _parse_tree(raw: bytes) -> dict[str, _TreeEntry]:
    result: dict[str, _TreeEntry] = {}
    try:
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, path_bytes = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split(" ", 2)
            path = path_bytes.decode("utf-8")
            if kind not in {"blob", "commit"} or not _safe_relative_path(path):
                raise ValueError
            result[path] = _TreeEntry(mode=mode, oid=oid)
    except (UnicodeError, ValueError) as exc:
        raise HostPatchError("Hermes tree identity is malformed") from exc
    return result


def _head_tree(root: Path) -> dict[str, _TreeEntry]:
    return _parse_tree(_git(root, "ls-tree", "-rz", "--full-tree", "HEAD").stdout)


def _index_tree(root: Path) -> dict[str, _TreeEntry]:
    raw = _git(root, "ls-files", "--stage", "-z").stdout
    result: dict[str, _TreeEntry] = {}
    try:
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, path_bytes = record.split(b"\t", 1)
            mode, oid, stage = metadata.decode("ascii").split(" ", 2)
            path = path_bytes.decode("utf-8")
            if stage != "0" or not _safe_relative_path(path):
                raise ValueError
            result[path] = _TreeEntry(mode=mode, oid=oid)
    except (UnicodeError, ValueError) as exc:
        raise HostPatchError("Hermes index identity is malformed") from exc
    return result


def _verify_index(root: Path, head_tree: Mapping[str, _TreeEntry]) -> None:
    if _index_tree(root) != dict(head_tree):
        raise HostPatchError("Hermes index does not exactly match the stock commit")


def _git_object_id(data: bytes, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise HostPatchError("unsupported Git object format") from exc
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def _filesystem_entries(
    root: Path,
) -> tuple[dict[str, os.stat_result], dict[str, os.stat_result]]:
    directories: dict[str, os.stat_result] = {}
    leaves: dict[str, os.stat_result] = {}

    def visit(directory: Path, prefix: str) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise HostPatchError("cannot inventory Hermes filesystem") from exc
        for entry in entries:
            if not prefix and entry.name == ".git":
                continue
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            if not _safe_relative_path(relative):
                raise HostPatchError("Hermes filesystem inventory contains an unsafe path")
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise HostPatchError("cannot inventory Hermes filesystem") from exc
            if stat.S_ISDIR(info.st_mode):
                _verify_owned_directory(info)
                directories[relative] = info
                visit(Path(entry.path), relative)
            elif stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                if info.st_uid != os.getuid():
                    raise HostPatchError("Hermes filesystem ownership mismatch")
                leaves[relative] = info
            else:
                raise HostPatchError("Hermes filesystem inventory contains a non-regular path")

    visit(root, "")
    return directories, leaves


def _expected_directories(paths: Sequence[str] | set[str]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        parent = PurePosixPath(path).parent
        while parent.as_posix() != ".":
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def _read_worktree_bytes(root: Path, relative: str, info: os.stat_result) -> bytes:
    target = root / relative
    try:
        if stat.S_ISLNK(info.st_mode):
            return os.fsencode(os.readlink(target))
        if stat.S_ISREG(info.st_mode):
            return target.read_bytes()
    except OSError as exc:
        raise HostPatchError("cannot read Hermes filesystem inventory") from exc
    raise HostPatchError("Hermes filesystem inventory contains a non-regular path")


def _mode_for_info(info: os.stat_result) -> str:
    if stat.S_ISLNK(info.st_mode):
        return "120000"
    if not stat.S_ISREG(info.st_mode):
        raise HostPatchError("Hermes filesystem inventory contains a non-regular path")
    permissions = stat.S_IMODE(info.st_mode)
    if permissions == 0o644:
        return "100644"
    if permissions == 0o755:
        return "100755"
    raise HostPatchError("Hermes filesystem mode mismatch")


def _expected_applied_paths(
    head_tree: Mapping[str, _TreeEntry],
    bundle: HostPatchBundle,
) -> set[str]:
    paths = set(head_tree)
    for path, spec in bundle.files.items():
        if spec.operation == "create":
            paths.add(path)
        elif spec.operation == "delete":
            paths.discard(path)
    return paths


def _verify_manifest_preimages(
    root: Path,
    bundle: HostPatchBundle,
    head_tree: Mapping[str, _TreeEntry],
) -> None:
    for path, spec in bundle.files.items():
        entry = head_tree.get(path)
        if spec.operation == "create":
            if entry is not None:
                raise HostPatchError("manifest create path exists in stock commit")
            continue
        if entry is None or entry.mode != spec.pre_mode:
            raise HostPatchError("manifest pre-apply mode does not match stock commit")
        blob = _git(root, "cat-file", "blob", entry.oid).stdout
        if hashlib.sha256(blob).hexdigest() != spec.pre_sha256:
            raise HostPatchError("manifest pre-apply digest does not match stock commit")


def _verify_filesystem(
    root: Path,
    bundle: HostPatchBundle,
    head_tree: Mapping[str, _TreeEntry],
    *,
    applied: bool,
) -> None:
    expected_paths = _expected_applied_paths(head_tree, bundle) if applied else set(head_tree)
    directories, leaves = _filesystem_entries(root)
    if set(leaves) != expected_paths or set(directories) != _expected_directories(expected_paths):
        raise HostPatchError("Hermes source tree is not clean: filesystem inventory mismatch")
    object_format = _git(root, "rev-parse", "--show-object-format").stdout.decode("ascii").strip()
    for path, info in leaves.items():
        actual_mode = _mode_for_info(info)
        data = _read_worktree_bytes(root, path, info)
        spec = bundle.files.get(path)
        if applied and spec is not None:
            if spec.post_mode is None or spec.post_sha256 is None:
                raise HostPatchError("post-apply path unexpectedly exists")
            if actual_mode != spec.post_mode:
                raise HostPatchError("post-apply file mode mismatch")
            if hashlib.sha256(data).hexdigest() != spec.post_sha256:
                raise HostPatchError("post-apply digest mismatch")
            continue
        entry = head_tree[path]
        if actual_mode != entry.mode:
            raise HostPatchError("Hermes filesystem mode mismatch")
        if _git_object_id(data, object_format) != entry.oid:
            raise HostPatchError("Hermes filesystem content mismatch")


def _touched_match(root: Path, bundle: HostPatchBundle, *, applied: bool) -> bool:
    for path, spec in bundle.files.items():
        target = root / path
        expected_sha = spec.post_sha256 if applied else spec.pre_sha256
        try:
            info = target.lstat()
        except FileNotFoundError:
            if expected_sha is not None:
                return False
            continue
        except OSError:
            return False
        if expected_sha is None or not stat.S_ISREG(info.st_mode):
            return False
        try:
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected_sha:
                return False
        except OSError:
            return False
    return True


def _verify_state(root: Path, bundle: HostPatchBundle, *, applied: bool) -> None:
    head_tree = _head_tree(root)
    _verify_index(root, head_tree)
    _verify_manifest_preimages(root, bundle, head_tree)
    _verify_filesystem(root, bundle, head_tree, applied=applied)


def _materialized_patch(root: Path, bundle: HostPatchBundle) -> dict[str, _Snapshot]:
    with tempfile.TemporaryDirectory(prefix="nunchi-host-patch-") as temporary:
        clone = Path(temporary) / "repo"
        cloned = subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", "--shared", str(root), str(clone)],
            capture_output=True,
            check=False,
            timeout=60,
            env=_git_env(),
        )
        if cloned.returncode != 0:
            raise HostPatchError("cannot construct isolated host-patch transaction")
        _git(clone, "read-tree", bundle.supported_hermes_commit)
        applied = _git(
            clone,
            "apply",
            "--cached",
            "--index",
            "--whitespace=error-all",
            "-",
            input_bytes=bundle.patch_bytes,
            check=False,
        )
        if applied.returncode != 0:
            raise HostPatchError("host patch does not apply to the exact stock index")
        index = _index_tree(clone)
        plan: dict[str, _Snapshot] = {}
        for path, spec in bundle.files.items():
            entry = index.get(path)
            if spec.post_sha256 is None:
                if entry is not None:
                    raise HostPatchError("isolated patch result retained a deleted path")
                plan[path] = _Snapshot(False, None, None)
                continue
            if spec.post_mode is None or entry is None or entry.mode != spec.post_mode:
                raise HostPatchError("isolated patch result mode mismatch")
            data = _git(clone, "cat-file", "blob", entry.oid).stdout
            if hashlib.sha256(data).hexdigest() != spec.post_sha256:
                raise HostPatchError("isolated patch result digest mismatch")
            plan[path] = _Snapshot(True, data, int(spec.post_mode[-3:], 8))
        head_tree = _head_tree(clone)
        changed = {
            path
            for path in set(index) | set(head_tree)
            if index.get(path) != head_tree.get(path)
        }
        if changed != set(bundle.files):
            raise HostPatchError("isolated patch result changed a path outside the manifest")
        return plan


@contextlib.contextmanager
def _transaction_lock(root: Path) -> Iterator[None]:
    if fcntl is None:
        raise HostPatchError("host patch transactions require POSIX file locking")
    lock_path = root / ".git" / "nunchi-v2-host-patch.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        lock_info = os.fstat(descriptor)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.getuid():
            raise OSError("unsafe host-patch lock file")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise HostPatchError("cannot serialize host patch transaction") from exc
    assert descriptor is not None
    try:
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = PurePosixPath(relative).parts
    current = os.dup(root_fd)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        return current, parts[-1]
    except BaseException:
        os.close(current)
        raise


def _snapshot_paths(root: Path, paths: Sequence[str]) -> dict[str, _Snapshot]:
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    snapshots: dict[str, _Snapshot] = {}
    try:
        for relative in paths:
            parent_fd, leaf = _open_parent(root_fd, relative)
            try:
                try:
                    info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    snapshots[relative] = _Snapshot(False, None, None)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise HostPatchError(f"non-regular touched path: {relative}")
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(leaf, flags, dir_fd=parent_fd)
                try:
                    opened_info = os.fstat(descriptor)
                    if not stat.S_ISREG(opened_info.st_mode):
                        raise HostPatchError(f"non-regular touched path: {relative}")
                    with os.fdopen(descriptor, "rb", closefd=False) as stream:
                        data = stream.read()
                finally:
                    os.close(descriptor)
                snapshots[relative] = _Snapshot(
                    True,
                    data,
                    stat.S_IMODE(opened_info.st_mode),
                )
            finally:
                os.close(parent_fd)
    finally:
        os.close(root_fd)
    return snapshots


def _verify_snapshot_preimages(
    snapshots: Mapping[str, _Snapshot],
    bundle: HostPatchBundle,
) -> None:
    if set(snapshots) != set(bundle.files):
        raise HostPatchError("transaction snapshot path set does not match manifest")
    for path, spec in bundle.files.items():
        snapshot = snapshots[path]
        expected_exists = spec.pre_sha256 is not None
        if snapshot.existed != expected_exists:
            raise HostPatchError("transaction snapshot does not match manifest pre-apply state")
        if not expected_exists:
            continue
        if snapshot.data is None or snapshot.mode is None or spec.pre_mode is None:
            raise HostPatchError("transaction snapshot has an incomplete pre-apply identity")
        if snapshot.mode != int(spec.pre_mode[-3:], 8):
            raise HostPatchError("transaction snapshot mode does not match pre-apply identity")
        if hashlib.sha256(snapshot.data).hexdigest() != spec.pre_sha256:
            raise HostPatchError("transaction snapshot digest does not match pre-apply identity")


def _write_snapshot(root_fd: int, relative: str, snapshot: _Snapshot) -> None:
    parent_fd, leaf = _open_parent(root_fd, relative)
    try:
        if not snapshot.existed:
            try:
                info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            if not stat.S_ISREG(info.st_mode):
                raise OSError("refusing to remove non-regular transaction target")
            os.unlink(leaf, dir_fd=parent_fd)
            os.fsync(parent_fd)
            return
        if snapshot.data is None or snapshot.mode is None:
            raise OSError("invalid transaction snapshot")
        temporary = f".{leaf}.nunchi-{secrets.token_hex(16)}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, snapshot.mode, dir_fd=parent_fd)
        try:
            view = memoryview(snapshot.data)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fchmod(descriptor, snapshot.mode)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _write_plan(root: Path, plan: Mapping[str, _Snapshot]) -> None:
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for relative in sorted(plan):
            _write_snapshot(root_fd, relative, plan[relative])
    finally:
        os.close(root_fd)


def inspect_host(source: Path, bundle: HostPatchBundle) -> dict[str, Any]:
    root = _validated_root(source)
    if _head(root) != bundle.supported_hermes_commit:
        raise HostPatchError("unsupported Hermes commit")
    if _touched_match(root, bundle, applied=True):
        _verify_state(root, bundle, applied=True)
        return _result(root, bundle, status="applied", changed=False)
    _verify_state(root, bundle, applied=False)
    _materialized_patch(root, bundle)
    return _result(root, bundle, status="ready", changed=False)


def apply_host_patch(source: Path, bundle: HostPatchBundle) -> dict[str, Any]:
    root = _validated_root(source)
    with _transaction_lock(root):
        state = inspect_host(root, bundle)
        if state["status"] == "applied":
            return state
        plan = _materialized_patch(root, bundle)
        snapshots = _snapshot_paths(root, tuple(bundle.files))
        _verify_snapshot_preimages(snapshots, bundle)
        try:
            _write_plan(root, plan)
            _verify_state(root, bundle, applied=True)
        except BaseException as exc:
            try:
                _write_plan(root, snapshots)
                _verify_state(root, bundle, applied=False)
            except BaseException as rollback_exc:
                raise HostPatchError("host patch failed and rollback verification failed") from rollback_exc
            raise HostPatchError("host patch verification failed; complete mutation rolled back") from exc
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
        "manifest_sha256": bundle.manifest_sha256,
        "patch_sha256": bundle.patch_sha256,
        "status": status,
        "touched_files": len(bundle.files),
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
