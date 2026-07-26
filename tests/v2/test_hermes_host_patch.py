from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from nunchi_hermes_v2.host_patch import (
    HostPatchBundle,
    HostPatchError,
    apply_host_patch,
    inspect_host,
)


def _git(repo: Path, *args: str, text: bool = True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    ).stdout


class HostPatchApplicatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "hermes"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.name", "Nunchi test")
        _git(self.repo, "config", "user.email", "nunchi-test@example.invalid")
        (self.repo / "host.py").write_text("value = 'stock'\n", encoding="utf-8")
        _git(self.repo, "add", "host.py")
        _git(self.repo, "commit", "-q", "-m", "stock")
        self.base_commit = _git(self.repo, "rev-parse", "HEAD").strip()

        (self.repo / "host.py").write_text("value = 'patched'\n", encoding="utf-8")
        (self.repo / "new_boundary.py").write_text("API_VERSION = 2\n", encoding="utf-8")
        _git(self.repo, "add", "-N", "new_boundary.py")
        self.patch_path = self.root / "host.patch"
        self.patch_path.write_bytes(_git(self.repo, "diff", "--binary", text=False))
        post_apply = {
            name: hashlib.sha256((self.repo / name).read_bytes()).hexdigest()
            for name in ("host.py", "new_boundary.py")
        }
        _git(self.repo, "restore", "host.py")
        (self.repo / "new_boundary.py").unlink()
        _git(self.repo, "reset", "-q")

        manifest = {
            "schema_version": 1,
            "patch": self.patch_path.name,
            "patch_sha256": hashlib.sha256(self.patch_path.read_bytes()).hexdigest(),
            "supported_hermes_commit": self.base_commit,
            "post_apply_sha256": post_apply,
        }
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.bundle = HostPatchBundle.from_paths(self.manifest_path, self.patch_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_exact_clean_host_is_ready_then_applies_and_verifies(self) -> None:
        self.assertEqual(inspect_host(self.repo, self.bundle)["status"], "ready")

        result = apply_host_patch(self.repo, self.bundle)

        self.assertEqual(result["status"], "applied")
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'patched'\n")
        self.assertEqual((self.repo / "new_boundary.py").read_text(), "API_VERSION = 2\n")
        self.assertEqual(inspect_host(self.repo, self.bundle)["status"], "applied")

    def test_apply_is_idempotent_only_for_the_exact_verified_result(self) -> None:
        apply_host_patch(self.repo, self.bundle)
        second = apply_host_patch(self.repo, self.bundle)
        self.assertEqual(second["status"], "applied")
        self.assertFalse(second["changed"])

    def test_wrong_commit_fails_closed(self) -> None:
        (self.repo / "other.txt").write_text("successor\n", encoding="utf-8")
        _git(self.repo, "add", "other.txt")
        _git(self.repo, "commit", "-q", "-m", "successor")

        with self.assertRaisesRegex(HostPatchError, "unsupported Hermes commit"):
            inspect_host(self.repo, self.bundle)

    def test_dirty_source_fails_closed_before_mutation(self) -> None:
        (self.repo / "unrelated.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(HostPatchError, "source tree is not clean"):
            apply_host_patch(self.repo, self.bundle)
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())

    def test_post_apply_digest_failure_rolls_back_every_touched_path(self) -> None:
        manifest = json.loads(self.manifest_path.read_text())
        manifest["post_apply_sha256"]["host.py"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        bad_bundle = HostPatchBundle.from_paths(self.manifest_path, self.patch_path)

        with self.assertRaisesRegex(HostPatchError, "rolled back"):
            apply_host_patch(self.repo, bad_bundle)

        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())
        self.assertEqual(_git(self.repo, "status", "--porcelain"), "")

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlink_at_touched_path_is_rejected(self) -> None:
        (self.repo / "host.py").unlink()
        (self.repo / "host.py").symlink_to("outside.py")

        with self.assertRaisesRegex(HostPatchError, "non-regular"):
            apply_host_patch(self.repo, self.bundle)

    def test_corrupted_patch_asset_is_rejected_before_host_inspection(self) -> None:
        self.patch_path.write_bytes(self.patch_path.read_bytes() + b"\ncorrupt\n")

        with self.assertRaisesRegex(HostPatchError, "patch digest mismatch"):
            HostPatchBundle.from_paths(self.manifest_path, self.patch_path)
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")


if __name__ == "__main__":
    unittest.main()
