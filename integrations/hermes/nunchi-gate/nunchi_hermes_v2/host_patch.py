"""Verify and transactionally apply Nunchi's exact Hermes V2 host seam."""

from __future__ import annotations

import argparse
import base64
import contextlib
import csv
import ctypes
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
from importlib import metadata as importlib_metadata
from importlib import resources
from importlib.util import find_spec
from pathlib import Path, PurePosixPath
from typing import Any, Literal

try:
    import fcntl
except ImportError:  # pragma: no cover - the supported Hermes seam is POSIX-only
    fcntl = None


# Updated only when the reviewed bundled manifest is intentionally regenerated.
BUNDLED_MANIFEST_SHA256 = "6811fbde2a025b99bf669776eb307861075c9e62a09db60d0542a07ba9e2ced3"


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
class HostInventoryFile:
    sha256: str
    mode: str


@dataclass(frozen=True)
class DistributionFile:
    sha256: str
    size: int
    kind: str


@dataclass(frozen=True)
class GeneratedScript:
    normalized_sha256: str


@dataclass(frozen=True)
class HostPatchBundle:
    supported_hermes_commit: str
    manifest_sha256: str
    patch_sha256: str
    patch_bytes: bytes
    files: Mapping[str, HostPatchFile]
    stock_inventory: Mapping[str, HostInventoryFile] | None = None
    supported_distribution_name: str | None = None
    supported_distribution_version: str | None = None
    distribution_inventory: Mapping[str, DistributionFile] | None = None
    generated_scripts: Mapping[str, GeneratedScript] | None = None
    installer_metadata_allowlist: frozenset[str] = frozenset()

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
        if not isinstance(manifest, dict) or manifest.get("schema_version") not in {2, 3}:
            raise HostPatchError("unsupported host-patch manifest schema")
        schema_version = manifest["schema_version"]
        allowed_keys = {
            "schema_version",
            "patch",
            "patch_sha256",
            "supported_hermes_commit",
            "files",
            "source",
            "stock_inventory",
            "supported_distribution",
            "distribution_inventory",
            "generated_scripts",
            "installer_metadata_allowlist",
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
        stock_inventory: dict[str, HostInventoryFile] | None = None
        distribution_name: str | None = None
        distribution_version: str | None = None
        distribution_inventory: dict[str, DistributionFile] | None = None
        generated_scripts: dict[str, GeneratedScript] | None = None
        installer_metadata_allowlist: frozenset[str] = frozenset()
        if schema_version == 3:
            raw_distribution = manifest.get("supported_distribution")
            raw_inventory = manifest.get("stock_inventory")
            if not isinstance(raw_distribution, dict) or set(raw_distribution) != {
                "name",
                "version",
            }:
                raise HostPatchError("host-patch manifest has an invalid distribution identity")
            distribution_name = raw_distribution.get("name")
            distribution_version = raw_distribution.get("version")
            if (
                not isinstance(distribution_name, str)
                or not distribution_name
                or not isinstance(distribution_version, str)
                or not distribution_version
            ):
                raise HostPatchError("host-patch manifest has an invalid distribution identity")
            if not isinstance(raw_inventory, dict) or not raw_inventory:
                raise HostPatchError("host-patch manifest has no stock installation inventory")
            stock_inventory = {}
            for name, raw in raw_inventory.items():
                if not isinstance(name, str) or not _safe_relative_path(name):
                    raise HostPatchError("host-patch inventory contains an unsafe path")
                if not isinstance(raw, dict) or set(raw) != {"mode", "sha256"}:
                    raise HostPatchError("host-patch inventory contains an invalid record")
                digest = _optional_digest(raw.get("sha256"))
                mode = _optional_mode(raw.get("mode"))
                if digest is None or mode is None:
                    raise HostPatchError("host-patch inventory contains an incomplete record")
                stock_inventory[name] = HostInventoryFile(sha256=digest, mode=mode)
            for name, spec in files.items():
                inventory = stock_inventory.get(name)
                if spec.operation == "create":
                    if inventory is not None:
                        raise HostPatchError("manifest create path exists in stock inventory")
                elif (
                    inventory is None
                    or inventory.sha256 != spec.pre_sha256
                    or inventory.mode != spec.pre_mode
                ):
                    raise HostPatchError("manifest preimage does not match stock inventory")
            raw_distribution_inventory = manifest.get("distribution_inventory")
            raw_generated_scripts = manifest.get("generated_scripts")
            raw_installer_allowlist = manifest.get("installer_metadata_allowlist")
            distribution_fields = (
                raw_distribution_inventory,
                raw_generated_scripts,
                raw_installer_allowlist,
            )
            if any(value is not None for value in distribution_fields):
                if (
                    not isinstance(raw_distribution_inventory, dict)
                    or not raw_distribution_inventory
                    or not isinstance(raw_generated_scripts, dict)
                    or not raw_generated_scripts
                    or not isinstance(raw_installer_allowlist, list)
                ):
                    raise HostPatchError(
                        "host-patch manifest has an incomplete distribution inventory"
                    )
                distribution_inventory = {}
                valid_kinds = {"runtime", "data", "dist-info", "record"}
                for name, raw in raw_distribution_inventory.items():
                    if not isinstance(name, str) or not _safe_relative_path(name):
                        raise HostPatchError(
                            "host-patch distribution inventory contains an unsafe path"
                        )
                    if not isinstance(raw, dict) or set(raw) != {
                        "kind",
                        "sha256",
                        "size",
                    }:
                        raise HostPatchError(
                            "host-patch distribution inventory contains an invalid record"
                        )
                    digest = _optional_digest(raw.get("sha256"))
                    size = raw.get("size")
                    kind = raw.get("kind")
                    if (
                        digest is None
                        or not isinstance(size, int)
                        or isinstance(size, bool)
                        or size < 0
                        or kind not in valid_kinds
                    ):
                        raise HostPatchError(
                            "host-patch distribution inventory contains an invalid identity"
                        )
                    distribution_inventory[name] = DistributionFile(
                        sha256=digest,
                        size=size,
                        kind=kind,
                    )
                runtime_inventory = {
                    name: record
                    for name, record in distribution_inventory.items()
                    if record.kind == "runtime"
                }
                if set(runtime_inventory) != set(stock_inventory):
                    raise HostPatchError(
                        "distribution runtime inventory does not close the stock inventory"
                    )
                for name, record in runtime_inventory.items():
                    if record.sha256 != stock_inventory[name].sha256:
                        raise HostPatchError(
                            "distribution runtime inventory does not match stock inventory"
                        )
                if sum(
                    record.kind == "record"
                    for record in distribution_inventory.values()
                ) != 1:
                    raise HostPatchError(
                        "distribution inventory must contain exactly one RECORD"
                    )
                generated_scripts = {}
                for name, raw in raw_generated_scripts.items():
                    if (
                        not isinstance(name, str)
                        or Path(name).name != name
                        or not isinstance(raw, dict)
                        or set(raw) != {"normalized_sha256"}
                    ):
                        raise HostPatchError(
                            "host-patch generated-script inventory is invalid"
                        )
                    digest = _optional_digest(raw.get("normalized_sha256"))
                    if digest is None:
                        raise HostPatchError(
                            "host-patch generated-script identity is invalid"
                        )
                    generated_scripts[name] = GeneratedScript(
                        normalized_sha256=digest
                    )
                if any(
                    not isinstance(name, str)
                    or Path(name).name != name
                    or not name
                    for name in raw_installer_allowlist
                ):
                    raise HostPatchError(
                        "host-patch installer metadata allowlist is invalid"
                    )
                installer_metadata_allowlist = frozenset(raw_installer_allowlist)
        elif "stock_inventory" in manifest or "supported_distribution" in manifest:
            raise HostPatchError("legacy host-patch manifest contains installed-distribution fields")
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
            stock_inventory=stock_inventory,
            supported_distribution_name=distribution_name,
            supported_distribution_version=distribution_version,
            distribution_inventory=distribution_inventory,
            generated_scripts=generated_scripts,
            installer_metadata_allowlist=installer_metadata_allowlist,
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


@dataclass(frozen=True)
class _PinnedParents:
    root_fd: int
    descriptors: Mapping[str, int]


@dataclass(frozen=True)
class _InventoryLeaf:
    info: os.stat_result
    data: bytes


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
        raise HostPatchError("cannot inspect Hermes installation directory") from exc
    _verify_owned_directory(root_info)
    return root


def _validate_git_root(root: Path) -> None:
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


def _verify_owned_directory(info: os.stat_result) -> None:
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise HostPatchError("Hermes installation directory ownership mismatch")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise HostPatchError("Hermes installation directory mode is group/other writable")


def _verify_owned_regular(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise HostPatchError("Hermes distribution file ownership mismatch")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise HostPatchError("Hermes distribution file is group/other writable")


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


def _tree_at(root: Path, revision: str) -> dict[str, _TreeEntry]:
    return _parse_tree(
        _git(root, "ls-tree", "-rz", "--full-tree", revision).stdout
    )


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


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_uid,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_uid,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _filesystem_entries(
    root: Path,
    *,
    pinned_root_fd: int | None = None,
    allow_runtime_artifacts: bool = False,
    included_top_levels: set[str] | None = None,
) -> tuple[dict[str, os.stat_result], dict[str, _InventoryLeaf]]:
    directories: dict[str, os.stat_result] = {}
    leaves: dict[str, _InventoryLeaf] = {}

    def visit(directory_fd: int, prefix: str) -> None:
        try:
            entries = list(os.scandir(directory_fd))
        except OSError as exc:
            raise HostPatchError("cannot inventory Hermes filesystem") from exc
        for entry in entries:
            if (
                not prefix
                and included_top_levels is not None
                and entry.name not in included_top_levels
            ):
                continue
            if not prefix and entry.name == ".git":
                continue
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            if not _safe_relative_path(relative):
                raise HostPatchError("Hermes filesystem inventory contains an unsafe path")
            try:
                info = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise HostPatchError("cannot inventory Hermes filesystem") from exc
            if stat.S_ISDIR(info.st_mode):
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                try:
                    child_fd = os.open(entry.name, flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise HostPatchError("cannot open Hermes filesystem directory safely") from exc
                try:
                    opened = os.fstat(child_fd)
                    if not _same_inode(info, opened):
                        raise HostPatchError("Hermes filesystem directory changed during inventory")
                    _verify_owned_directory(opened)
                    runtime_cache = entry.name in {
                        "__pycache__",
                        ".pytest_cache",
                        ".pytest-cache",
                        ".ruff_cache",
                        ".mypy_cache",
                    } or (
                        not prefix
                        and (
                            entry.name in {".venv", "venv"}
                            or entry.name.endswith(".egg-info")
                        )
                    )
                    if allow_runtime_artifacts and runtime_cache:
                        closing = os.stat(
                            entry.name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                        if not _same_inode(opened, closing):
                            raise HostPatchError(
                                "Hermes filesystem directory changed during inventory"
                            )
                        continue
                    directories[relative] = opened
                    visit(child_fd, relative)
                    closing = os.stat(
                        entry.name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                    if not _same_inode(opened, closing):
                        raise HostPatchError("Hermes filesystem directory changed during inventory")
                finally:
                    os.close(child_fd)
                continue
            if stat.S_ISREG(info.st_mode):
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                try:
                    leaf_fd = os.open(entry.name, flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise HostPatchError("cannot open Hermes filesystem leaf safely") from exc
                try:
                    opened = os.fstat(leaf_fd)
                    if not stat.S_ISREG(opened.st_mode) or not _same_inode(info, opened):
                        raise HostPatchError("Hermes filesystem leaf changed during inventory")
                    data = _read_descriptor(leaf_fd)
                    if not _same_inode(opened, os.fstat(leaf_fd)):
                        raise HostPatchError("Hermes filesystem leaf changed during inventory")
                finally:
                    os.close(leaf_fd)
                closing = os.stat(
                    entry.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if not _same_inode(opened, closing):
                    raise HostPatchError("Hermes filesystem leaf changed during inventory")
            elif stat.S_ISLNK(info.st_mode):
                try:
                    data = os.fsencode(os.readlink(entry.name, dir_fd=directory_fd))
                    closing = os.stat(
                        entry.name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise HostPatchError("cannot read Hermes filesystem symlink safely") from exc
                if not _same_inode(info, closing):
                    raise HostPatchError("Hermes filesystem symlink changed during inventory")
                opened = closing
            else:
                raise HostPatchError("Hermes filesystem inventory contains a non-regular path")
            if opened.st_uid != os.getuid():
                raise HostPatchError("Hermes filesystem ownership mismatch")
            if allow_runtime_artifacts and entry.name == ".DS_Store":
                continue
            leaves[relative] = _InventoryLeaf(info=opened, data=data)

        try:
            closing_names = {
                entry.name
                for entry in os.scandir(directory_fd)
                if prefix
                or included_top_levels is None
                or entry.name in included_top_levels
            }
        except OSError as exc:
            raise HostPatchError("cannot close Hermes filesystem inventory") from exc
        opening_names = {
            entry.name
            for entry in entries
            if prefix
            or included_top_levels is None
            or entry.name in included_top_levels
        }
        if closing_names != opening_names:
            raise HostPatchError("Hermes filesystem directory changed during inventory")

    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.dup(pinned_root_fd) if pinned_root_fd is not None else os.open(root, root_flags)
    except OSError as exc:
        raise HostPatchError("cannot open Hermes filesystem root safely") from exc
    try:
        visit(root_fd, "")
    finally:
        os.close(root_fd)
    return directories, leaves


def _expected_directories(paths: Sequence[str] | set[str]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        parent = PurePosixPath(path).parent
        while parent.as_posix() != ".":
            result.add(parent.as_posix())
            parent = parent.parent
    return result


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
    pinned_root_fd: int | None = None,
) -> None:
    expected_paths = _expected_applied_paths(head_tree, bundle) if applied else set(head_tree)
    directories, leaves = _filesystem_entries(
        root,
        pinned_root_fd=pinned_root_fd,
        allow_runtime_artifacts=applied,
    )
    if set(leaves) != expected_paths or set(directories) != _expected_directories(expected_paths):
        raise HostPatchError("Hermes source tree is not clean: filesystem inventory mismatch")
    object_format = _git(root, "rev-parse", "--show-object-format").stdout.decode("ascii").strip()
    for path, leaf in leaves.items():
        actual_mode = _mode_for_info(leaf.info)
        data = leaf.data
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


def _verify_installed_filesystem(
    root: Path,
    bundle: HostPatchBundle,
    *,
    applied: bool,
    pinned_root_fd: int | None = None,
) -> None:
    inventory = bundle.stock_inventory
    if inventory is None:
        raise HostPatchError("host-patch manifest has no stock installation inventory")
    expected: dict[str, HostInventoryFile] = dict(inventory)
    if applied:
        for path, spec in bundle.files.items():
            if spec.post_sha256 is None or spec.post_mode is None:
                expected.pop(path, None)
            else:
                expected[path] = HostInventoryFile(
                    sha256=spec.post_sha256,
                    mode=spec.post_mode,
                )
    top_levels = {PurePosixPath(path).parts[0] for path in expected}
    top_levels.update(PurePosixPath(path).parts[0] for path in bundle.files)
    directories, leaves = _filesystem_entries(
        root,
        pinned_root_fd=pinned_root_fd,
        allow_runtime_artifacts=True,
        included_top_levels=top_levels,
    )
    if set(leaves) != set(expected) or set(directories) != _expected_directories(set(expected)):
        raise HostPatchError("Hermes installation inventory mismatch")
    for path, leaf in leaves.items():
        identity = expected[path]
        if _mode_for_info(leaf.info) != identity.mode:
            raise HostPatchError("Hermes installation mode mismatch")
        if hashlib.sha256(leaf.data).hexdigest() != identity.sha256:
            raise HostPatchError("Hermes installation content mismatch")


def _read_regular_nofollow(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current /= part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise HostPatchError("Hermes distribution path contains a symlink")
        before = absolute.lstat()
        _verify_owned_regular(before)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise HostPatchError("Hermes distribution file is unsafe or unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        _verify_owned_regular(opened)
        if not _same_inode(before, opened):
            raise HostPatchError("Hermes distribution file changed during inspection")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if not _same_inode(opened, after) or after.st_size != opened.st_size:
            raise HostPatchError("Hermes distribution file changed during inspection")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _record_digest(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _record_digest_from_hex(digest: str) -> str:
    return base64.urlsafe_b64encode(bytes.fromhex(digest)).rstrip(b"=").decode("ascii")


def _logical_record_path(root: Path, logical: str) -> Path:
    parsed = PurePosixPath(logical)
    if parsed.is_absolute() or "\\" in logical or "\x00" in logical:
        raise HostPatchError("Hermes RECORD contains an unsafe path")
    if any(part in {"", "."} for part in parsed.parts):
        raise HostPatchError("Hermes RECORD contains an unsafe path")
    leading_parents = 0
    for part in parsed.parts:
        if part != "..":
            break
        leading_parents += 1
    if leading_parents > 4 or ".." in parsed.parts[leading_parents:]:
        raise HostPatchError("Hermes RECORD contains an unsafe path")
    return root.joinpath(*parsed.parts)


def _record_suffix_match(logical: str, suffix: PurePosixPath) -> bool:
    parsed = PurePosixPath(logical)
    return (
        bool(parsed.parts)
        and parsed.parts[0] == ".."
        and len(parsed.parts) > len(suffix.parts)
        and parsed.parts[-len(suffix.parts) :] == suffix.parts
    )


def _is_bounded_record_cache(
    logical: str,
    digest: str,
    size: str,
    inventory: Mapping[str, DistributionFile],
) -> bool:
    parsed = PurePosixPath(logical)
    if digest or size or ".." in parsed.parts or parsed.parts.count("__pycache__") != 1:
        return False
    cache_index = parsed.parts.index("__pycache__")
    if cache_index == 0 or cache_index != len(parsed.parts) - 2:
        return False
    match = re.fullmatch(r"(.+)\.cpython-\d+(?:\.opt-\d+)?\.pyc", parsed.name)
    if match is None:
        return False
    source = PurePosixPath(*parsed.parts[:cache_index], f"{match.group(1)}.py").as_posix()
    item = inventory.get(source)
    return item is not None and item.kind == "runtime"


def _verify_distribution_identity(
    root: Path,
    bundle: HostPatchBundle,
    *,
    applied: bool,
) -> tuple[str, str]:
    inventory = bundle.distribution_inventory
    scripts = bundle.generated_scripts
    name = bundle.supported_distribution_name
    version = bundle.supported_distribution_version
    if inventory is None or scripts is None:
        return name or "", version or ""
    if name is None or version is None:
        raise HostPatchError("host-patch manifest has no distribution identity")
    try:
        distribution = importlib_metadata.distribution(name)
    except importlib_metadata.PackageNotFoundError as exc:
        raise HostPatchError("supported Hermes distribution metadata is unavailable") from exc
    observed_root = Path(str(distribution.locate_file(""))).resolve()
    if observed_root != root:
        raise HostPatchError("selected Hermes installation is not the active distribution")
    observed_name = str(distribution.metadata["Name"] or "")
    observed_version = str(distribution.version or "")
    canonical_name = observed_name.lower().replace("_", "-")
    if canonical_name != name.lower().replace("_", "-") or observed_version != version:
        raise HostPatchError("unsupported Hermes distribution identity")

    record_keys = [path for path, item in inventory.items() if item.kind == "record"]
    record_key = record_keys[0]
    record_bytes = _read_regular_nofollow(root / record_key)
    try:
        decoded = record_bytes.decode("utf-8")
        parsed_rows = list(csv.reader(decoded.splitlines()))
    except (UnicodeError, csv.Error) as exc:
        raise HostPatchError("Hermes distribution RECORD is invalid") from exc
    rows: dict[str, tuple[str, str]] = {}
    for row in parsed_rows:
        if len(row) != 3 or not row[0] or row[0] in rows:
            raise HostPatchError("Hermes distribution RECORD is not closed")
        _logical_record_path(root, row[0])
        rows[row[0]] = (row[1], row[2])

    wheel_to_record: dict[str, str] = {}
    for wheel_path, item in inventory.items():
        if item.kind == "data":
            marker = ".data/data/"
            if marker not in wheel_path:
                raise HostPatchError("Hermes data-scheme inventory is invalid")
            suffix = PurePosixPath(wheel_path.split(marker, 1)[1])
            matches = [path for path in rows if _record_suffix_match(path, suffix)]
            if len(matches) != 1:
                raise HostPatchError("Hermes data-scheme installation is ambiguous")
            wheel_to_record[wheel_path] = matches[0]
        else:
            wheel_to_record[wheel_path] = wheel_path

    script_records: dict[str, str] = {}
    for script_name in scripts:
        suffix = PurePosixPath("bin") / script_name
        matches = [path for path in rows if _record_suffix_match(path, suffix)]
        if len(matches) != 1:
            raise HostPatchError("Hermes generated entry-point script is unavailable")
        script_records[script_name] = matches[0]

    dist_info_dir = PurePosixPath(record_key).parent
    required_rows = set(wheel_to_record.values()) | set(script_records.values())
    optional_rows = {
        (dist_info_dir / filename).as_posix()
        for filename in bundle.installer_metadata_allowlist
    }
    observed_optional = set(rows) & optional_rows
    cache_rows = {
        path
        for path, (digest, size) in rows.items()
        if _is_bounded_record_cache(path, digest, size, inventory)
    }
    if set(rows) != required_rows | observed_optional | cache_rows:
        raise HostPatchError("Hermes distribution RECORD has unknown or missing files")

    content_by_record: dict[str, bytes] = {}
    record_to_wheel = {logical: wheel for wheel, logical in wheel_to_record.items()}
    for logical, (digest, size) in rows.items():
        wheel_path = record_to_wheel.get(logical)
        item = inventory.get(wheel_path) if wheel_path is not None else None
        spec = bundle.files.get(wheel_path) if wheel_path is not None else None
        record_holds_stock_preimage = (
            applied
            and item is not None
            and item.kind == "runtime"
            and spec is not None
        )
        if logical == record_key:
            data = _read_regular_nofollow(_logical_record_path(root, logical))
            content_by_record[logical] = data
            if digest or size:
                raise HostPatchError("Hermes RECORD self-entry is invalid")
            continue
        if record_holds_stock_preimage:
            assert item is not None and spec is not None
            if (
                digest != f"sha256={_record_digest_from_hex(item.sha256)}"
                or size != str(item.size)
            ):
                raise HostPatchError("Hermes RECORD stock preimage identity mismatch")
            if spec.post_sha256 is None:
                continue
            data = _read_regular_nofollow(_logical_record_path(root, logical))
            content_by_record[logical] = data
            continue
        data = _read_regular_nofollow(_logical_record_path(root, logical))
        content_by_record[logical] = data
        if not digest.startswith("sha256=") or not size.isdigit():
            if logical in cache_rows:
                continue
            raise HostPatchError("Hermes distribution RECORD identity is incomplete")
        if int(size) != len(data) or digest.removeprefix("sha256=") != _record_digest(data):
            raise HostPatchError("Hermes distribution RECORD digest mismatch")

    for wheel_path, item in inventory.items():
        if item.kind == "record":
            continue
        logical = wheel_to_record[wheel_path]
        spec = bundle.files.get(wheel_path)
        if applied and item.kind == "runtime" and spec is not None:
            if spec.post_sha256 is None:
                continue
            data = content_by_record[logical]
            if hashlib.sha256(data).hexdigest() != spec.post_sha256:
                raise HostPatchError("Hermes published distribution identity mismatch")
            continue
        data = content_by_record[logical]
        if len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
            raise HostPatchError("Hermes published distribution identity mismatch")

    for script_name, script in scripts.items():
        data = content_by_record[script_records[script_name]]
        first, separator, rest = data.partition(b"\n")
        if not separator or not first.startswith(b"#!"):
            raise HostPatchError("Hermes generated script has an invalid launcher")
        normalized = b"#!python\n" + rest
        if hashlib.sha256(normalized).hexdigest() != script.normalized_sha256:
            raise HostPatchError("Hermes generated script identity mismatch")
    return observed_name, observed_version


def _verify_root_descriptor(root: Path, root_fd: int) -> None:
    try:
        opened = os.fstat(root_fd)
        current = root.lstat()
    except OSError as exc:
        raise HostPatchError("Hermes transaction root identity is unavailable") from exc
    if not _same_inode(opened, current):
        raise HostPatchError("Hermes transaction root changed")
    _verify_owned_directory(opened)


def _verify_state(
    root: Path,
    bundle: HostPatchBundle,
    *,
    applied: bool,
    pinned_root_fd: int | None = None,
) -> None:
    if pinned_root_fd is not None:
        _verify_root_descriptor(root, pinned_root_fd)
    if bundle.stock_inventory is not None:
        _verify_installed_filesystem(
            root,
            bundle,
            applied=applied,
            pinned_root_fd=pinned_root_fd,
        )
        _verify_distribution_identity(root, bundle, applied=applied)
        if pinned_root_fd is not None:
            _verify_root_descriptor(root, pinned_root_fd)
        return
    _validate_git_root(root)
    if _head(root) != bundle.supported_hermes_commit:
        raise HostPatchError("unsupported Hermes commit")
    head_tree = _tree_at(root, bundle.supported_hermes_commit)
    _verify_index(root, head_tree)
    _verify_manifest_preimages(root, bundle, head_tree)
    _verify_filesystem(
        root,
        bundle,
        head_tree,
        applied=applied,
        pinned_root_fd=pinned_root_fd,
    )
    if _head(root) != bundle.supported_hermes_commit:
        raise HostPatchError("unsupported Hermes commit")
    if pinned_root_fd is not None:
        _verify_root_descriptor(root, pinned_root_fd)


def _materialized_patch(
    root: Path,
    bundle: HostPatchBundle,
    *,
    snapshots: Mapping[str, _Snapshot] | None = None,
) -> dict[str, _Snapshot]:
    if bundle.stock_inventory is not None:
        if snapshots is None:
            raise HostPatchError("installed patch materialization requires pinned snapshots")
        return _materialized_installed_patch(bundle, snapshots)
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
        head_tree = _tree_at(clone, bundle.supported_hermes_commit)
        changed = {
            path
            for path in set(index) | set(head_tree)
            if index.get(path) != head_tree.get(path)
        }
        if changed != set(bundle.files):
            raise HostPatchError("isolated patch result changed a path outside the manifest")
        return plan


def _materialized_installed_patch(
    bundle: HostPatchBundle,
    snapshots: Mapping[str, _Snapshot],
) -> dict[str, _Snapshot]:
    with tempfile.TemporaryDirectory(prefix="nunchi-installed-host-patch-") as temporary:
        work = Path(temporary) / "work"
        work.mkdir()
        _git(work, "init", "--quiet")
        for path, spec in bundle.files.items():
            if spec.pre_sha256 is None or spec.pre_mode is None:
                continue
            snapshot = snapshots.get(path)
            if (
                snapshot is None
                or not snapshot.existed
                or snapshot.data is None
                or snapshot.mode is None
            ):
                raise HostPatchError("installed host-patch preimage snapshot is incomplete")
            data = snapshot.data
            if hashlib.sha256(data).hexdigest() != spec.pre_sha256:
                raise HostPatchError("installed host-patch preimage digest mismatch")
            if snapshot.mode != int(spec.pre_mode[-3:], 8):
                raise HostPatchError("installed host-patch preimage mode mismatch")
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(int(spec.pre_mode[-3:], 8))
        _git(work, "add", "--all")
        base_index = _index_tree(work)
        applied = _git(
            work,
            "apply",
            "--cached",
            "--index",
            "--whitespace=error-all",
            "-",
            input_bytes=bundle.patch_bytes,
            check=False,
        )
        if applied.returncode != 0:
            raise HostPatchError("host patch does not apply to installed stock preimages")
        index = _index_tree(work)
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
            data = _git(work, "cat-file", "blob", entry.oid).stdout
            if hashlib.sha256(data).hexdigest() != spec.post_sha256:
                raise HostPatchError("isolated patch result digest mismatch")
            plan[path] = _Snapshot(True, data, int(spec.post_mode[-3:], 8))
        changed = {
            path
            for path in set(index) | set(base_index)
            if index.get(path) != base_index.get(path)
        }
        if changed != set(bundle.files):
            raise HostPatchError("isolated patch result changed a path outside the manifest")
        return plan


def _materialized_installed_rollback(
    bundle: HostPatchBundle,
    snapshots: Mapping[str, _Snapshot],
) -> dict[str, _Snapshot]:
    with tempfile.TemporaryDirectory(prefix="nunchi-installed-host-rollback-") as temporary:
        work = Path(temporary) / "work"
        work.mkdir()
        _git(work, "init", "--quiet")
        for path, spec in bundle.files.items():
            if spec.post_sha256 is None or spec.post_mode is None:
                continue
            snapshot = snapshots.get(path)
            if (
                snapshot is None
                or not snapshot.existed
                or snapshot.data is None
                or snapshot.mode is None
            ):
                raise HostPatchError("installed rollback postimage snapshot is incomplete")
            data = snapshot.data
            if hashlib.sha256(data).hexdigest() != spec.post_sha256:
                raise HostPatchError("installed host rollback postimage digest mismatch")
            if snapshot.mode != int(spec.post_mode[-3:], 8):
                raise HostPatchError("installed host rollback postimage mode mismatch")
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(int(spec.post_mode[-3:], 8))
        _git(work, "add", "--all")
        applied = _git(
            work,
            "apply",
            "--cached",
            "--index",
            "--reverse",
            "--whitespace=error-all",
            "-",
            input_bytes=bundle.patch_bytes,
            check=False,
        )
        if applied.returncode != 0:
            raise HostPatchError("host patch cannot reconstruct installed stock preimages")
        index = _index_tree(work)
        plan: dict[str, _Snapshot] = {}
        for path, spec in bundle.files.items():
            entry = index.get(path)
            if spec.pre_sha256 is None:
                if entry is not None:
                    raise HostPatchError("isolated rollback retained a created path")
                plan[path] = _Snapshot(False, None, None)
                continue
            if spec.pre_mode is None or entry is None or entry.mode != spec.pre_mode:
                raise HostPatchError("isolated rollback result mode mismatch")
            data = _git(work, "cat-file", "blob", entry.oid).stdout
            if hashlib.sha256(data).hexdigest() != spec.pre_sha256:
                raise HostPatchError("isolated rollback result digest mismatch")
            plan[path] = _Snapshot(True, data, int(spec.pre_mode[-3:], 8))
        return plan


def _stock_plan(
    root: Path,
    bundle: HostPatchBundle,
    *,
    snapshots: Mapping[str, _Snapshot] | None = None,
) -> dict[str, _Snapshot]:
    if bundle.stock_inventory is not None:
        if snapshots is None:
            raise HostPatchError("installed rollback materialization requires pinned snapshots")
        return _materialized_installed_rollback(bundle, snapshots)
    tree = _tree_at(root, bundle.supported_hermes_commit)
    plan: dict[str, _Snapshot] = {}
    for path, spec in bundle.files.items():
        if spec.pre_sha256 is None:
            plan[path] = _Snapshot(False, None, None)
            continue
        entry = tree.get(path)
        if spec.pre_mode is None or entry is None or entry.mode != spec.pre_mode:
            raise HostPatchError("stock rollback identity mismatch")
        data = _git(root, "cat-file", "blob", entry.oid).stdout
        if hashlib.sha256(data).hexdigest() != spec.pre_sha256:
            raise HostPatchError("stock rollback digest mismatch")
        plan[path] = _Snapshot(True, data, int(spec.pre_mode[-3:], 8))
    return plan


@contextlib.contextmanager
def _transaction_lock(root: Path) -> Iterator[None]:
    if fcntl is None:
        raise HostPatchError("host patch transactions require POSIX file locking")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(root, flags)
        lock_info = os.fstat(descriptor)
        _verify_owned_directory(lock_info)
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


def _open_directory(root_fd: int, relative: str) -> int:
    current = os.dup(root_fd)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parts = () if relative == "." else PurePosixPath(relative).parts
        for part in parts:
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    path = PurePosixPath(relative)
    return _open_directory(root_fd, path.parent.as_posix()), path.name


def _parent_key(relative: str) -> str:
    return PurePosixPath(relative).parent.as_posix()


def _transaction_parent(
    root: int | _PinnedParents,
    relative: str,
) -> tuple[int, str]:
    if isinstance(root, _PinnedParents):
        try:
            descriptor = root.descriptors[_parent_key(relative)]
        except KeyError as exc:
            raise HostPatchError("transaction parent was not pinned") from exc
        return os.dup(descriptor), PurePosixPath(relative).name
    return _open_parent(root, relative)


def _verify_pinned_parents(parents: _PinnedParents) -> None:
    for relative, descriptor in parents.descriptors.items():
        current = _open_directory(parents.root_fd, relative)
        try:
            pinned_info = os.fstat(descriptor)
            current_info = os.fstat(current)
            _verify_owned_directory(pinned_info)
            _verify_owned_directory(current_info)
            if not _same_inode(pinned_info, current_info):
                raise HostPatchError("Hermes transaction parent changed")
        finally:
            os.close(current)


def _parents_attached(parents: _PinnedParents) -> bool:
    """True when every pinned parent inode is still reachable by its name."""
    for relative, descriptor in parents.descriptors.items():
        try:
            current = _open_directory(parents.root_fd, relative)
        except OSError:
            return False
        try:
            if not _same_inode(os.fstat(descriptor), os.fstat(current)):
                return False
        finally:
            os.close(current)
    return True


def _verify_live_targets_present(
    root_fd: int,
    snapshots: Mapping[str, _Snapshot],
) -> None:
    """Attest every pre-existing live (by-name) target still exists.

    The live replacement tree belongs to whoever exchanged the parent; its
    contents were never written by this transaction and are not ours to
    demand. The load-bearing safety property is that rollback restored the
    pinned original (done separately through the pinned descriptors) and
    that no live target vanished mid-transaction, which would make the
    detached-restoration report misleading.
    """
    for relative in sorted(snapshots):
        if not snapshots[relative].existed:
            continue
        parent_fd, leaf = _open_parent(root_fd, relative)
        try:
            current = _read_leaf_snapshot(parent_fd, leaf)
        finally:
            os.close(parent_fd)
        if not current.existed:
            raise HostPatchError(
                "host patch failed; live transaction target vanished during rollback"
            )


@contextlib.contextmanager
def _pin_touched_parents(
    root_fd: int,
    paths: Sequence[str],
) -> Iterator[_PinnedParents]:
    descriptors: dict[str, int] = {}
    try:
        for relative in paths:
            parent = _parent_key(relative)
            if parent in descriptors:
                continue
            descriptor = _open_directory(root_fd, parent)
            try:
                _verify_owned_directory(os.fstat(descriptor))
            except BaseException:
                os.close(descriptor)
                raise
            descriptors[parent] = descriptor
        pinned = _PinnedParents(root_fd=root_fd, descriptors=descriptors)
        _verify_pinned_parents(pinned)
        yield pinned
    finally:
        for descriptor in descriptors.values():
            os.close(descriptor)


def _snapshot_paths(root: Path | int | _PinnedParents, paths: Sequence[str]) -> dict[str, _Snapshot]:
    pinned = root if isinstance(root, _PinnedParents) else None
    owns_root_fd = isinstance(root, Path)
    root_fd = (
        os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        if isinstance(root, Path)
        else root.root_fd
        if isinstance(root, _PinnedParents)
        else root
    )
    snapshots: dict[str, _Snapshot] = {}
    try:
        if pinned is not None:
            _verify_pinned_parents(pinned)
        for relative in paths:
            parent_fd, leaf = _transaction_parent(pinned or root_fd, relative)
            try:
                snapshot = _read_leaf_snapshot(parent_fd, leaf)
                if snapshot.existed and (snapshot.data is None or snapshot.mode is None):
                    raise HostPatchError(f"incomplete touched path snapshot: {relative}")
                snapshots[relative] = snapshot
            finally:
                os.close(parent_fd)
        if pinned is not None:
            _verify_pinned_parents(pinned)
    finally:
        if owns_root_fd:
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


def _snapshot_content_matches(
    snapshots: Mapping[str, _Snapshot],
    bundle: HostPatchBundle,
    *,
    applied: bool,
) -> bool:
    for path, spec in bundle.files.items():
        snapshot = snapshots.get(path)
        if snapshot is None:
            return False
        expected = spec.post_sha256 if applied else spec.pre_sha256
        if snapshot.existed != (expected is not None):
            return False
        if expected is not None and (
            snapshot.data is None
            or hashlib.sha256(snapshot.data).hexdigest() != expected
        ):
            return False
    return True


def _snapshots_equal(left: _Snapshot, right: _Snapshot) -> bool:
    return (
        left.existed == right.existed
        and left.data == right.data
        and left.mode == right.mode
    )


def _read_leaf_snapshot(parent_fd: int, leaf: str) -> _Snapshot:
    try:
        before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return _Snapshot(False, None, None)
    except OSError as exc:
        raise HostPatchError("cannot inspect transaction target") from exc
    if not stat.S_ISREG(before.st_mode):
        raise HostPatchError("transaction target is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(leaf, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise HostPatchError("cannot open transaction target safely") from exc
    try:
        opened = os.fstat(descriptor)
        if not _same_inode(before, opened):
            raise HostPatchError("transaction target changed while opening")
        data = _read_descriptor(descriptor)
        if not _same_inode(opened, os.fstat(descriptor)):
            raise HostPatchError("transaction target changed while reading")
    finally:
        os.close(descriptor)
    try:
        closing = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise HostPatchError("transaction target changed after reading") from exc
    if not _same_inode(opened, closing):
        raise HostPatchError("transaction target changed after reading")
    return _Snapshot(True, data, stat.S_IMODE(opened.st_mode))


def _exchange_names(parent_fd: int, left: str, right: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(libc, "renameatx_np", None)
        flag = 0x00000002  # RENAME_SWAP
    elif sys.platform.startswith("linux"):
        function = getattr(libc, "renameat2", None)
        flag = 0x00000002  # RENAME_EXCHANGE
    else:  # pragma: no cover - the supported Hermes host is POSIX macOS/Linux
        function = None
        flag = 0
    if function is None:
        raise HostPatchError("atomic transaction exchange is unavailable")
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    if function(
        parent_fd,
        os.fsencode(left),
        parent_fd,
        os.fsencode(right),
        flag,
    ) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def _write_temporary(
    parent_fd: int,
    leaf: str,
    snapshot: _Snapshot,
) -> str:
    if not snapshot.existed or snapshot.data is None or snapshot.mode is None:
        raise HostPatchError("invalid transaction postimage")
    temporary = f".{leaf}.nunchi-{secrets.token_hex(16)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(temporary, flags, snapshot.mode, dir_fd=parent_fd)
        created = True
        view = memoryview(snapshot.data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("zero-byte transaction write")
            view = view[written:]
        os.fchmod(descriptor, snapshot.mode)
        os.fsync(descriptor)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        if created:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return temporary


def _write_snapshot(
    parents: _PinnedParents,
    relative: str,
    desired: _Snapshot,
    expected: _Snapshot,
) -> None:
    parent_fd, leaf = _transaction_parent(parents, relative)
    try:
        current = _read_leaf_snapshot(parent_fd, leaf)
        if not _snapshots_equal(current, expected):
            raise HostPatchError("transaction target changed before commit")
        if not desired.existed:
            if not expected.existed:
                return
            temporary = f".{leaf}.nunchi-{secrets.token_hex(16)}"
            try:
                os.rename(leaf, temporary, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                moved = _read_leaf_snapshot(parent_fd, temporary)
                if not _snapshots_equal(moved, expected):
                    raise HostPatchError("transaction target changed during removal")
                os.unlink(temporary, dir_fd=parent_fd)
            except Exception:
                try:
                    temporary_state = _read_leaf_snapshot(parent_fd, temporary)
                    leaf_state = _read_leaf_snapshot(parent_fd, leaf)
                    if temporary_state.existed and not leaf_state.existed:
                        os.link(
                            temporary,
                            leaf,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                        os.unlink(temporary, dir_fd=parent_fd)
                    elif temporary_state.existed:
                        raise HostPatchError(
                            "cannot restore transaction target without clobbering data"
                        )
                except Exception as restore_exc:
                    os.fsync(parent_fd)
                    raise HostPatchError(
                        "transaction removal failed and displaced data was preserved"
                    ) from restore_exc
                os.fsync(parent_fd)
                raise
            os.fsync(parent_fd)
            return
        temporary = _write_temporary(parent_fd, leaf, desired)
        exchanged = False
        try:
            if not expected.existed:
                try:
                    os.link(
                        temporary,
                        leaf,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as exc:
                    raise HostPatchError("transaction create target appeared before commit") from exc
                os.unlink(temporary, dir_fd=parent_fd)
                os.fsync(parent_fd)
                return
            _exchange_names(parent_fd, temporary, leaf)
            exchanged = True
            displaced = _read_leaf_snapshot(parent_fd, temporary)
            if not _snapshots_equal(displaced, expected):
                raise HostPatchError("transaction target changed during atomic exchange")
            os.unlink(temporary, dir_fd=parent_fd)
            exchanged = False
            os.fsync(parent_fd)
        except BaseException:
            if exchanged:
                try:
                    _exchange_names(parent_fd, temporary, leaf)
                    exchanged = False
                except BaseException:
                    # The displaced preimage remains at the temporary name. Do not
                    # unlink unknown data merely to make rollback look clean.
                    os.fsync(parent_fd)
                    raise
            try:
                os.unlink(temporary, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileNotFoundError:
                pass
            raise
    finally:
        os.close(parent_fd)


def _write_plan(
    parents: _PinnedParents,
    plan: Mapping[str, _Snapshot],
    expected: Mapping[str, _Snapshot],
) -> list[str]:
    completed: list[str] = []
    for relative in sorted(plan):
        _write_snapshot(parents, relative, plan[relative], expected[relative])
        completed.append(relative)
    return completed


def _rollback_plan(
    parents: _PinnedParents,
    snapshots: Mapping[str, _Snapshot],
    postimages: Mapping[str, _Snapshot],
) -> None:
    failures: list[BaseException] = []
    for relative in sorted(snapshots, reverse=True):
        try:
            parent_fd, leaf = _transaction_parent(parents, relative)
            try:
                current = _read_leaf_snapshot(parent_fd, leaf)
            finally:
                os.close(parent_fd)
            if _snapshots_equal(current, snapshots[relative]):
                continue
            if not _snapshots_equal(current, postimages[relative]):
                raise HostPatchError("transaction target changed before rollback")
            _write_snapshot(
                parents,
                relative,
                snapshots[relative],
                postimages[relative],
            )
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise HostPatchError("one or more transaction paths could not be rolled back") from failures[0]


def inspect_host(source: Path, bundle: HostPatchBundle) -> dict[str, Any]:
    root = _validated_root(source)
    touched = _snapshot_paths(root, tuple(bundle.files))
    if _snapshot_content_matches(touched, bundle, applied=True):
        _verify_state(root, bundle, applied=True)
        return _result(root, bundle, status="applied", changed=False)
    _verify_state(root, bundle, applied=False)
    return _result(root, bundle, status="ready", changed=False)


def apply_host_patch(source: Path, bundle: HostPatchBundle) -> dict[str, Any]:
    root = _validated_root(source)
    with _transaction_lock(root):
        state = inspect_host(root, bundle)
        if state["status"] == "applied":
            return state
        root_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            root_fd = os.open(root, root_flags)
        except OSError as exc:
            raise HostPatchError("cannot pin Hermes transaction root") from exc
        try:
            with _pin_touched_parents(root_fd, tuple(bundle.files)) as parents:
                snapshots = _snapshot_paths(parents, tuple(bundle.files))
                _verify_snapshot_preimages(snapshots, bundle)
                _verify_state(
                    root,
                    bundle,
                    applied=False,
                    pinned_root_fd=root_fd,
                )
                plan = _materialized_patch(
                    root,
                    bundle,
                    snapshots=snapshots,
                )
                _verify_pinned_parents(parents)
                try:
                    _write_plan(parents, plan, snapshots)
                    _verify_pinned_parents(parents)
                    _verify_state(
                        root,
                        bundle,
                        applied=True,
                        pinned_root_fd=root_fd,
                    )
                except BaseException as exc:
                    rollback_done = False
                    try:
                        # Roll back through the pinned descriptors first. They
                        # still reference the originally pinned inodes even if
                        # an attacker exchanged a parent directory by name, so
                        # the pinned original never retains patch bytes.
                        _rollback_plan(parents, snapshots, plan)
                        rollback_done = True
                        _verify_pinned_parents(parents)
                        _verify_state(
                            root,
                            bundle,
                            applied=False,
                            pinned_root_fd=root_fd,
                        )
                    except BaseException as rollback_exc:
                        if rollback_done and not _parents_attached(parents):
                            # The pinned parents were detached by name after the
                            # pinned-original rollback completed. Attest the
                            # live replacement tree was never touched by this
                            # transaction, then report exactly what was
                            # restored — never a false complete-restoration
                            # claim.
                            _verify_live_targets_present(root_fd, snapshots)
                            raise HostPatchError(
                                "host patch rejected; pinned original restored "
                                "and live checkout unmodified, but transaction "
                                "parent remains detached"
                            ) from exc
                        raise HostPatchError(
                            "host patch failed and rollback verification failed"
                        ) from rollback_exc
                    raise HostPatchError(
                        "host patch verification failed; complete mutation rolled back"
                    ) from exc
        finally:
            os.close(root_fd)
        return _result(root, bundle, status="applied", changed=True)


def rollback_host_patch(source: Path, bundle: HostPatchBundle) -> dict[str, Any]:
    root = _validated_root(source)
    with _transaction_lock(root):
        state = inspect_host(root, bundle)
        if state["status"] == "ready":
            return state
        root_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            root_fd = os.open(root, root_flags)
        except OSError as exc:
            raise HostPatchError("cannot pin Hermes rollback root") from exc
        try:
            with _pin_touched_parents(root_fd, tuple(bundle.files)) as parents:
                snapshots = _snapshot_paths(parents, tuple(bundle.files))
                if not _snapshot_content_matches(snapshots, bundle, applied=True):
                    raise HostPatchError("rollback snapshot does not match the applied seam")
                _verify_state(
                    root,
                    bundle,
                    applied=True,
                    pinned_root_fd=root_fd,
                )
                stock_plan = _stock_plan(
                    root,
                    bundle,
                    snapshots=snapshots,
                )
                _verify_pinned_parents(parents)
                try:
                    _write_plan(parents, stock_plan, snapshots)
                    _verify_pinned_parents(parents)
                    _verify_state(
                        root,
                        bundle,
                        applied=False,
                        pinned_root_fd=root_fd,
                    )
                except BaseException as exc:
                    try:
                        _rollback_plan(parents, snapshots, stock_plan)
                        _verify_pinned_parents(parents)
                        _verify_state(
                            root,
                            bundle,
                            applied=True,
                            pinned_root_fd=root_fd,
                        )
                    except BaseException as rollback_exc:
                        raise HostPatchError(
                            "host rollback failed and applied-state restoration failed"
                        ) from rollback_exc
                    raise HostPatchError(
                        "host rollback verification failed; applied seam restored"
                    ) from exc
        finally:
            os.close(root_fd)
        return _result(root, bundle, status="ready", changed=True)


def _result(
    root: Path,
    bundle: HostPatchBundle,
    *,
    status: str,
    changed: bool,
) -> dict[str, Any]:
    if bundle.stock_inventory is None:
        observed_commit = _head(root)
        if observed_commit != bundle.supported_hermes_commit:
            raise HostPatchError("unsupported Hermes commit")
        observed_distribution = bundle.supported_distribution_name
        observed_version = bundle.supported_distribution_version
    else:
        observed_commit = bundle.supported_hermes_commit
        observed_distribution, observed_version = _verify_distribution_identity(
            root,
            bundle,
            applied=status == "applied",
        )
    return {
        "changed": changed,
        "hermes_commit": observed_commit,
        "hermes_installation": str(root),
        "hermes_distribution": observed_distribution,
        "hermes_version": observed_version,
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
    command.add_argument(
        "--hermes-installation",
        type=Path,
        help="Hermes site-packages root (default: discover the installed hermes-agent)",
    )
    action = command.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="verify readiness or exact applied state")
    action.add_argument("--apply", action="store_true", help="apply and verify the exact host seam")
    action.add_argument("--rollback", action="store_true", help="restore and verify exact stock bytes")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        bundle = HostPatchBundle.bundled()
        installation = args.hermes_installation
        if installation is None:
            spec = find_spec("gateway")
            locations = tuple(spec.submodule_search_locations or ()) if spec is not None else ()
            if len(locations) != 1:
                raise HostPatchError("installed Hermes distribution is not discoverable")
            installation = Path(locations[0]).resolve().parent
        if args.apply:
            result = apply_host_patch(installation, bundle)
        elif args.rollback:
            result = rollback_host_patch(installation, bundle)
        else:
            result = inspect_host(installation, bundle)
    except HostPatchError as exc:
        print(f"nunchi-hermes-v2-host-patch: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
