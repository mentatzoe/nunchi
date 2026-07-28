from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nunchi_hermes_v2.host_patch as host_patch
from nunchi_hermes_v2.host_patch import (
    HostPatchBundle,
    HostPatchError,
    apply_host_patch,
    inspect_host,
    rollback_host_patch,
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
        (self.repo / "package").mkdir()
        (self.repo / "package" / "marker.py").write_text("STOCK = True\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "stock")
        self.base_commit = _git(self.repo, "rev-parse", "HEAD").strip()
        stock_digest = hashlib.sha256((self.repo / "host.py").read_bytes()).hexdigest()

        (self.repo / "host.py").write_text("value = 'patched'\n", encoding="utf-8")
        (self.repo / "new_boundary.py").write_text("API_VERSION = 2\n", encoding="utf-8")
        _git(self.repo, "add", "-N", "new_boundary.py")
        self.patch_path = self.root / "host.patch"
        self.patch_path.write_bytes(_git(self.repo, "diff", "--binary", text=False))
        files = {
            "host.py": {
                "operation": "modify",
                "pre_sha256": stock_digest,
                "pre_mode": "100644",
                "post_sha256": hashlib.sha256((self.repo / "host.py").read_bytes()).hexdigest(),
                "post_mode": "100644",
            },
            "new_boundary.py": {
                "operation": "create",
                "pre_sha256": None,
                "pre_mode": None,
                "post_sha256": hashlib.sha256((self.repo / "new_boundary.py").read_bytes()).hexdigest(),
                "post_mode": "100644",
            },
        }
        _git(self.repo, "restore", "host.py")
        (self.repo / "new_boundary.py").unlink()
        _git(self.repo, "reset", "-q")

        manifest = {
            "schema_version": 2,
            "patch": self.patch_path.name,
            "patch_sha256": hashlib.sha256(self.patch_path.read_bytes()).hexdigest(),
            "supported_hermes_commit": self.base_commit,
            "files": files,
        }
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.bundle = HostPatchBundle.from_paths(self.manifest_path, self.patch_path)

    def _installed_bundle(self) -> HostPatchBundle:
        manifest = json.loads(self.manifest_path.read_text())
        manifest.update(
            {
                "schema_version": 3,
                "supported_distribution": {
                    "name": "hermes-agent",
                    "version": "0.19.0",
                },
                "stock_inventory": {
                    "host.py": {
                        "mode": manifest["files"]["host.py"]["pre_mode"],
                        "sha256": manifest["files"]["host.py"]["pre_sha256"],
                    },
                    "package/marker.py": {
                        "mode": "100644",
                        "sha256": hashlib.sha256(
                            (self.repo / "package" / "marker.py").read_bytes()
                        ).hexdigest(),
                    },
                },
            }
        )
        installed_manifest = self.root / "installed-manifest.json"
        installed_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        return HostPatchBundle.from_paths(installed_manifest, self.patch_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_exact_clean_host_is_ready_then_applies_and_verifies(self) -> None:
        self.assertEqual(inspect_host(self.repo, self.bundle)["status"], "ready")

        result = apply_host_patch(self.repo, self.bundle)

        self.assertEqual(result["status"], "applied")
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'patched'\n")
        self.assertEqual((self.repo / "new_boundary.py").read_text(), "API_VERSION = 2\n")
        self.assertEqual(inspect_host(self.repo, self.bundle)["status"], "applied")

    def test_exact_installed_distribution_needs_no_git_checkout(self) -> None:
        bundle = self._installed_bundle()
        shutil.rmtree(self.repo / ".git")

        self.assertEqual(inspect_host(self.repo, bundle)["status"], "ready")
        result = apply_host_patch(self.repo, bundle)

        self.assertEqual(result["status"], "applied")
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'patched'\n")
        self.assertEqual(inspect_host(self.repo, bundle)["status"], "applied")

    def test_installed_distribution_rolls_back_without_git_checkout(self) -> None:
        bundle = self._installed_bundle()
        shutil.rmtree(self.repo / ".git")
        apply_host_patch(self.repo, bundle)

        result = rollback_host_patch(self.repo, bundle)

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["changed"])
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())
        self.assertEqual(rollback_host_patch(self.repo, bundle)["status"], "ready")

    def test_installed_materialization_never_reads_touched_paths_by_name(self) -> None:
        bundle = self._installed_bundle()
        shutil.rmtree(self.repo / ".git")
        actual_read_bytes = Path.read_bytes
        touched = {self.repo / path for path in bundle.files}

        def guarded_read_bytes(path: Path) -> bytes:
            if path in touched:
                raise AssertionError("touched source was read outside pinned descriptors")
            return actual_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", guarded_read_bytes):
            self.assertEqual(apply_host_patch(self.repo, bundle)["status"], "applied")
            self.assertEqual(rollback_host_patch(self.repo, bundle)["status"], "ready")

    @unittest.skipIf(os.name == "nt", "POSIX FIFO semantics required")
    def test_installed_fifo_preimage_fails_closed_without_blocking(self) -> None:
        bundle = self._installed_bundle()
        shutil.rmtree(self.repo / ".git")
        (self.repo / "host.py").unlink()
        os.mkfifo(self.repo / "host.py", 0o600)

        with self.assertRaisesRegex(HostPatchError, "regular|inventory|mode"):
            apply_host_patch(self.repo, bundle)

    def test_bundled_manifest_closes_the_published_wheel_distribution(self) -> None:
        bundle = HostPatchBundle.bundled()

        self.assertIsNotNone(bundle.distribution_inventory)
        self.assertEqual(len(bundle.distribution_inventory or {}), 959)
        self.assertEqual(
            sum(
                item.kind == "runtime"
                for item in (bundle.distribution_inventory or {}).values()
            ),
            935,
        )
        self.assertEqual(
            set(bundle.generated_scripts or {}),
            {"hermes", "hermes-acp", "hermes-agent"},
        )
        self.assertIn(
            "hermes_agent-0.19.0.dist-info/METADATA",
            bundle.distribution_inventory or {},
        )
        self.assertIn(
            "hermes_agent-0.19.0.data/data/locales/en.yaml",
            bundle.distribution_inventory or {},
        )

    def test_root_module_bytecode_is_a_bounded_record_cache(self) -> None:
        inventory = {
            "batch_runner.py": host_patch.DistributionFile(
                kind="runtime",
                sha256="0" * 64,
                size=1,
            )
        }

        self.assertTrue(
            host_patch._is_bounded_record_cache(
                "__pycache__/batch_runner.cpython-313.pyc",
                "",
                "",
                inventory,
            )
        )

    def test_generated_script_accepts_bounded_pip_and_uv_launchers(self) -> None:
        script = host_patch.GeneratedScript(
            normalized_sha256="0" * 64,
            module="hermes_cli.main",
            function="main",
        )
        pip_launcher = b"""#!/venv/bin/python
import sys
from hermes_cli.main import main
if __name__ == '__main__':
    if sys.argv[0].endswith('.exe'):
        sys.argv[0] = sys.argv[0][:-4]
    sys.exit(main())
"""
        uv_launcher = b"""#!/venv/bin/python
# -*- coding: utf-8 -*-
import sys
from hermes_cli.main import main
if __name__ == "__main__":
    if sys.argv[0].endswith("-script.pyw"):
        sys.argv[0] = sys.argv[0][:-11]
    elif sys.argv[0].endswith(".exe"):
        sys.argv[0] = sys.argv[0][:-4]
    sys.exit(main())
"""
        setuptools_launcher = b"""#!/venv/bin/python
# -*- coding: utf-8 -*-
import re
import sys
from hermes_cli.main import main
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script.pyw|.exe)?$', '', sys.argv[0])
    sys.exit(main())
"""

        host_patch._verify_generated_script(pip_launcher, script)
        host_patch._verify_generated_script(uv_launcher, script)
        host_patch._verify_generated_script(setuptools_launcher, script)

    def test_generated_script_rejects_a_different_entry_point(self) -> None:
        script = host_patch.GeneratedScript(
            normalized_sha256="0" * 64,
            module="hermes_cli.main",
            function="main",
        )
        launcher = b"""#!/venv/bin/python
import sys
from attacker import main
if __name__ == '__main__':
    sys.exit(main())
"""

        with self.assertRaisesRegex(HostPatchError, "identity mismatch"):
            host_patch._verify_generated_script(launcher, script)

    def test_installed_distribution_rejects_unknown_runtime_source(self) -> None:
        bundle = self._installed_bundle()
        shutil.rmtree(self.repo / ".git")
        (self.repo / "package" / "rogue.py").write_text(
            "EXECUTES = True\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(HostPatchError, "inventory"):
            inspect_host(self.repo, bundle)

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

    def test_head_change_after_initial_check_cannot_fabricate_supported_receipt(self) -> None:
        _git(self.repo, "commit", "--allow-empty", "-q", "-m", "same-tree successor")
        successor = _git(self.repo, "rev-parse", "HEAD").strip()
        _git(self.repo, "reset", "--hard", "-q", self.base_commit)
        real_head = host_patch._head
        calls = 0

        def move_after_first_check(root):
            nonlocal calls
            observed = real_head(root)
            calls += 1
            if calls == 1:
                _git(self.repo, "reset", "--hard", "-q", successor)
            return observed

        with (
            mock.patch.object(host_patch, "_head", side_effect=move_after_first_check),
            self.assertRaisesRegex(HostPatchError, "unsupported Hermes commit"),
        ):
            inspect_host(self.repo, self.bundle)

    def test_dirty_source_fails_closed_before_mutation(self) -> None:
        (self.repo / "unrelated.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(HostPatchError, "source tree is not clean"):
            apply_host_patch(self.repo, self.bundle)
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())

    def test_ignored_runtime_file_fails_closed_before_mutation(self) -> None:
        (self.repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        _git(self.repo, "add", ".gitignore")
        _git(self.repo, "commit", "-q", "-m", "ignore runtime file")
        self.base_commit = _git(self.repo, "rev-parse", "HEAD").strip()
        manifest = json.loads(self.manifest_path.read_text())
        manifest["supported_hermes_commit"] = self.base_commit
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        bundle = HostPatchBundle.from_paths(self.manifest_path, self.patch_path)
        (self.repo / "ignored.py").write_text("RUNTIME = True\n", encoding="utf-8")

        with self.assertRaisesRegex(HostPatchError, "inventory"):
            apply_host_patch(self.repo, bundle)

        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")

    def test_applied_host_allows_bounded_runtime_cache_directories(self) -> None:
        apply_host_patch(self.repo, self.bundle)
        for relative in (
            "__pycache__/host.cpython-312.pyc",
            ".pytest_cache/v/cache/nodeids",
            ".pytest-cache/guard",
            ".ruff_cache/0/cache",
            ".venv/lib/python3.12/site-packages/runtime.txt",
            "hermes_agent.egg-info/PKG-INFO",
        ):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"runtime-cache")

        self.assertEqual(
            "applied",
            inspect_host(self.repo, self.bundle)["status"],
        )

    def test_applied_host_still_rejects_unknown_untracked_source(self) -> None:
        apply_host_patch(self.repo, self.bundle)
        (self.repo / "rogue.py").write_text("EXECUTES = True\n", encoding="utf-8")

        with self.assertRaisesRegex(HostPatchError, "inventory"):
            inspect_host(self.repo, self.bundle)

    def test_applied_host_rejects_index_divergence_hidden_by_worktree(self) -> None:
        apply_host_patch(self.repo, self.bundle)
        _git(self.repo, "add", "host.py", "new_boundary.py")
        _git(self.repo, "restore", "--staged", "host.py")

        with self.assertRaisesRegex(HostPatchError, "index"):
            inspect_host(self.repo, self.bundle)

    def test_git_environment_cannot_redirect_index_identity(self) -> None:
        alternate_index = self.root / "alternate-index"
        subprocess.run(
            ["git", "-C", str(self.repo), "read-tree", "HEAD"],
            check=True,
            env={**os.environ, "GIT_INDEX_FILE": str(alternate_index)},
        )
        (self.repo / "host.py").write_text("value = 'staged-divergence'\n", encoding="utf-8")
        _git(self.repo, "add", "host.py")
        (self.repo / "host.py").write_text("value = 'stock'\n", encoding="utf-8")

        with (
            mock.patch.dict(os.environ, {"GIT_INDEX_FILE": str(alternate_index)}),
            self.assertRaisesRegex(HostPatchError, "index"),
        ):
            inspect_host(self.repo, self.bundle)

    @unittest.skipIf(os.name == "nt", "POSIX mode semantics required")
    def test_applied_host_rejects_mode_drift_with_core_filemode_false(self) -> None:
        apply_host_patch(self.repo, self.bundle)
        _git(self.repo, "config", "core.filemode", "false")
        (self.repo / "host.py").chmod(0o755)

        with self.assertRaisesRegex(HostPatchError, "mode"):
            inspect_host(self.repo, self.bundle)

    @unittest.skipIf(os.name == "nt", "POSIX mode semantics required")
    def test_group_or_other_writable_repository_directory_is_rejected(self) -> None:
        self.repo.chmod(0o777)

        with self.assertRaisesRegex(HostPatchError, "directory mode"):
            inspect_host(self.repo, self.bundle)

    def test_invalid_post_apply_digest_is_rejected_before_mutation(self) -> None:
        manifest = json.loads(self.manifest_path.read_text())
        manifest["files"]["host.py"]["post_sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        bad_bundle = HostPatchBundle.from_paths(self.manifest_path, self.patch_path)

        with self.assertRaisesRegex(HostPatchError, "isolated patch result digest mismatch"):
            apply_host_patch(self.repo, bad_bundle)

        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())
        self.assertEqual(_git(self.repo, "status", "--porcelain"), "")

    def test_unmanifested_patch_path_cannot_survive_claimed_rollback(self) -> None:
        (self.repo / "extra.py").write_text("MUTATED = True\n", encoding="utf-8")
        _git(self.repo, "add", "-N", "extra.py")
        malicious_patch = self.root / "malicious.patch"
        malicious_patch.write_bytes(_git(self.repo, "diff", "--binary", text=False))
        (self.repo / "extra.py").unlink()
        _git(self.repo, "reset", "-q")
        manifest = json.loads(self.manifest_path.read_text())
        manifest["patch"] = malicious_patch.name
        manifest["patch_sha256"] = hashlib.sha256(malicious_patch.read_bytes()).hexdigest()
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(HostPatchError, "patch.*manifest|closed path"):
            HostPatchBundle.from_paths(self.manifest_path, malicious_patch)

        self.assertFalse((self.repo / "extra.py").exists())
        self.assertEqual(_git(self.repo, "status", "--porcelain"), "")

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlink_at_touched_path_is_rejected(self) -> None:
        (self.repo / "host.py").unlink()
        (self.repo / "host.py").symlink_to("outside.py")

        with self.assertRaisesRegex(HostPatchError, "mode|regular"):
            apply_host_patch(self.repo, self.bundle)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics required")
    def test_leaf_swapped_to_symlink_during_inventory_is_rejected(self) -> None:
        outside = self.root / "outside.py"
        outside.write_text("value = 'stock'\n", encoding="utf-8")
        real_open = os.open
        swapped = False

        def race_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if path == "host.py" and dir_fd is not None and not swapped:
                swapped = True
                (self.repo / "host.py").unlink()
                (self.repo / "host.py").symlink_to(outside)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with (
            mock.patch.object(host_patch.os, "open", side_effect=race_open),
            self.assertRaises(HostPatchError),
        ):
            inspect_host(self.repo, self.bundle)
        self.assertTrue(swapped)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics required")
    def test_directory_swapped_to_symlink_during_inventory_is_rejected(self) -> None:
        package = self.repo / "pkg"
        package.mkdir()
        (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        _git(self.repo, "add", "pkg/module.py")
        _git(self.repo, "commit", "-q", "-m", "tracked package")
        manifest = json.loads(self.manifest_path.read_text())
        manifest["supported_hermes_commit"] = _git(self.repo, "rev-parse", "HEAD").strip()
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        bundle = HostPatchBundle.from_paths(self.manifest_path, self.patch_path)
        outside = self.root / "outside-directory"
        outside.mkdir()
        (outside / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        real_open = os.open
        swapped = False

        def race_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if path == "pkg" and dir_fd is not None and not swapped:
                swapped = True
                (package / "module.py").unlink()
                package.rmdir()
                package.symlink_to(outside, target_is_directory=True)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with (
            mock.patch.object(host_patch.os, "open", side_effect=race_open),
            self.assertRaises(HostPatchError),
        ):
            inspect_host(self.repo, bundle)
        self.assertTrue(swapped)

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlink_repository_root_is_rejected(self) -> None:
        linked_root = self.root / "linked-hermes"
        linked_root.symlink_to(self.repo, target_is_directory=True)

        with self.assertRaisesRegex(HostPatchError, "symlink"):
            inspect_host(linked_root, self.bundle)

    def test_post_write_verification_failure_restores_complete_ready_state(self) -> None:
        real_verify = host_patch._verify_state

        def fail_applied(root, bundle, *, applied, pinned_root_fd=None):
            if applied:
                raise HostPatchError("injected post-write failure")
            return real_verify(
                root,
                bundle,
                applied=applied,
                pinned_root_fd=pinned_root_fd,
            )

        with (
            mock.patch.object(host_patch, "_verify_state", side_effect=fail_applied),
            self.assertRaisesRegex(HostPatchError, "complete mutation rolled back"),
        ):
            apply_host_patch(self.repo, self.bundle)

        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())
        self.assertEqual(_git(self.repo, "status", "--porcelain"), "")

    def test_touched_preimage_change_during_transaction_fails_before_write(self) -> None:
        real_snapshot = host_patch._snapshot_paths
        calls = 0

        def mutate_before_snapshot(root, paths):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.repo / "host.py").write_text("value = 'raced'\n", encoding="utf-8")
            return real_snapshot(root, paths)

        with mock.patch.object(
            host_patch,
            "_snapshot_paths",
            side_effect=mutate_before_snapshot,
        ), self.assertRaisesRegex(HostPatchError, "snapshot.*pre-apply"):
            apply_host_patch(self.repo, self.bundle)

        self.assertEqual((self.repo / "host.py").read_text(), "value = 'raced'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())

    def test_touched_preimage_change_after_snapshot_is_not_overwritten(self) -> None:
        real_write = host_patch._write_plan
        raced = False

        def mutate_before_write(*args, **kwargs):
            nonlocal raced
            if not raced:
                raced = True
                (self.repo / "host.py").write_text("value = 'late-race'\n", encoding="utf-8")
            return real_write(*args, **kwargs)

        with (
            mock.patch.object(host_patch, "_write_plan", side_effect=mutate_before_write),
            self.assertRaises(HostPatchError),
        ):
            apply_host_patch(self.repo, self.bundle)

        self.assertEqual((self.repo / "host.py").read_text(), "value = 'late-race'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())

    def _nested_package_bundle(self) -> HostPatchBundle:
        package = self.repo / "pkg"
        package.mkdir()
        module = package / "module.py"
        module.write_text("VALUE = 'stock'\n", encoding="utf-8")
        _git(self.repo, "add", "pkg/module.py")
        _git(self.repo, "commit", "-q", "-m", "nested stock")
        base_commit = _git(self.repo, "rev-parse", "HEAD").strip()
        stock_digest = hashlib.sha256(module.read_bytes()).hexdigest()

        module.write_text("VALUE = 'patched'\n", encoding="utf-8")
        nested_patch = self.root / "nested.patch"
        nested_patch.write_bytes(_git(self.repo, "diff", "--binary", text=False))
        manifest = {
            "schema_version": 2,
            "patch": nested_patch.name,
            "patch_sha256": hashlib.sha256(nested_patch.read_bytes()).hexdigest(),
            "supported_hermes_commit": base_commit,
            "files": {
                "pkg/module.py": {
                    "operation": "modify",
                    "pre_sha256": stock_digest,
                    "pre_mode": "100644",
                    "post_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
                    "post_mode": "100644",
                }
            },
        }
        nested_manifest = self.root / "nested-manifest.json"
        nested_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        bundle = HostPatchBundle.from_paths(nested_manifest, nested_patch)
        _git(self.repo, "restore", "pkg/module.py")
        return bundle

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics required")
    def test_touched_parent_exchange_cannot_mutate_detached_replacement(self) -> None:
        nested_bundle = self._nested_package_bundle()
        package = self.repo / "pkg"

        real_write = host_patch._write_plan
        original_detached = self.root / "original-pkg"
        replacement_detached = self.root / "replacement-pkg"

        def exchange_parent_during_commit(*args, **kwargs):
            package.rename(original_detached)
            package.mkdir()
            (package / "module.py").write_text("VALUE = 'stock'\n", encoding="utf-8")
            try:
                return real_write(*args, **kwargs)
            finally:
                package.rename(replacement_detached)
                original_detached.rename(package)

        with mock.patch.object(
            host_patch,
            "_write_plan",
            side_effect=exchange_parent_during_commit,
        ):
            try:
                apply_host_patch(self.repo, nested_bundle)
            except HostPatchError:
                pass

        self.assertEqual(
            "VALUE = 'stock'\n",
            (replacement_detached / "module.py").read_text(encoding="utf-8"),
        )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics required")
    def test_touched_parent_exchange_not_restored_fails_without_false_rollback(self) -> None:
        nested_bundle = self._nested_package_bundle()
        package = self.repo / "pkg"

        real_write = host_patch._write_plan
        detached = self.root / "detached-pkg"

        def exchange_parent_and_keep_detached(*args, **kwargs):
            package.rename(detached)
            package.mkdir()
            (package / "module.py").write_text(
                "VALUE = 'attacker-live'\n", encoding="utf-8"
            )
            return real_write(*args, **kwargs)

        with mock.patch.object(
            host_patch,
            "_write_plan",
            side_effect=exchange_parent_and_keep_detached,
        ), self.assertRaisesRegex(
            HostPatchError,
            "pinned original restored and live checkout unmodified",
        ):
            apply_host_patch(self.repo, nested_bundle)

        # The write went to the pinned original inode (now detached), never to
        # the attacker's live replacement. Rollback runs through the pinned
        # descriptors before the failure is reported, so the detached original
        # is restored to its exact preimage and the live replacement still
        # carries the attacker's bytes — no patch residue and no false
        # complete-restoration claim.
        self.assertEqual(
            "VALUE = 'stock'\n",
            (detached / "module.py").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            "VALUE = 'attacker-live'\n",
            (package / "module.py").read_text(encoding="utf-8"),
        )

    def test_modify_race_at_atomic_exchange_is_restored_not_overwritten(self) -> None:
        real_exchange = host_patch._exchange_names
        raced = False

        def mutate_at_exchange(parent_fd, left, right):
            nonlocal raced
            if not raced and right == "host.py":
                raced = True
                (self.repo / "host.py").write_text(
                    "value = 'exchange-race'\n",
                    encoding="utf-8",
                )
            return real_exchange(parent_fd, left, right)

        with mock.patch.object(
            host_patch,
            "_exchange_names",
            side_effect=mutate_at_exchange,
        ), self.assertRaisesRegex(HostPatchError, "rollback verification failed"):
            apply_host_patch(self.repo, self.bundle)

        self.assertTrue(raced)
        self.assertEqual(
            (self.repo / "host.py").read_text(),
            "value = 'exchange-race'\n",
        )
        self.assertFalse((self.repo / "new_boundary.py").exists())

    def test_create_race_at_no_clobber_commit_is_preserved(self) -> None:
        real_temporary = host_patch._write_temporary
        raced = False

        def create_at_commit(parent_fd, leaf, snapshot):
            nonlocal raced
            temporary = real_temporary(parent_fd, leaf, snapshot)
            if not raced and leaf == "new_boundary.py":
                raced = True
                (self.repo / leaf).write_text("CONCURRENT = True\n", encoding="utf-8")
            return temporary

        with mock.patch.object(
            host_patch,
            "_write_temporary",
            side_effect=create_at_commit,
        ), self.assertRaisesRegex(HostPatchError, "rollback verification failed"):
            apply_host_patch(self.repo, self.bundle)

        self.assertTrue(raced)
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertEqual(
            (self.repo / "new_boundary.py").read_text(),
            "CONCURRENT = True\n",
        )

    def test_temporary_is_removed_when_write_fails_before_replace(self) -> None:
        real_open = os.open
        real_write = os.write
        temporary_descriptors: set[int] = set()
        injected = False

        def track_temporary_open(path, flags, mode=0o777, *, dir_fd=None):
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            if isinstance(path, str) and ".nunchi-" in path:
                temporary_descriptors.add(descriptor)
            return descriptor

        def fail_first_write(descriptor, data):
            nonlocal injected
            if not injected and descriptor in temporary_descriptors:
                injected = True
                raise OSError("injected temporary write failure")
            return real_write(descriptor, data)

        with (
            mock.patch.object(host_patch.os, "open", side_effect=track_temporary_open),
            mock.patch.object(host_patch.os, "write", side_effect=fail_first_write),
            self.assertRaisesRegex(HostPatchError, "complete mutation rolled back"),
        ):
            apply_host_patch(self.repo, self.bundle)

        self.assertTrue(injected)
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")
        self.assertFalse((self.repo / "new_boundary.py").exists())
        self.assertEqual(list(self.repo.glob(".*.nunchi-*")), [])

    def test_rollback_write_failure_is_reported_without_fabricating_success(self) -> None:
        real_verify = host_patch._verify_state

        def fail_applied(root, bundle, *, applied, pinned_root_fd=None):
            if applied:
                raise HostPatchError("injected post-write failure")
            return real_verify(
                root,
                bundle,
                applied=applied,
                pinned_root_fd=pinned_root_fd,
            )

        with (
            mock.patch.object(host_patch, "_verify_state", side_effect=fail_applied),
            mock.patch.object(
                host_patch,
                "_rollback_plan",
                side_effect=OSError("injected rollback write failure"),
            ),
            self.assertRaisesRegex(HostPatchError, "rollback verification failed"),
        ):
            apply_host_patch(self.repo, self.bundle)

    def test_corrupted_patch_asset_is_rejected_before_host_inspection(self) -> None:
        self.patch_path.write_bytes(self.patch_path.read_bytes() + b"\ncorrupt\n")

        with self.assertRaisesRegex(HostPatchError, "patch digest mismatch"):
            HostPatchBundle.from_paths(self.manifest_path, self.patch_path)
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")

    def test_manifest_identity_pin_rejects_coordinated_asset_rewrite(self) -> None:
        with self.assertRaisesRegex(HostPatchError, "manifest identity mismatch"):
            HostPatchBundle.from_paths(
                self.manifest_path,
                self.patch_path,
                expected_manifest_sha256="0" * 64,
            )

    def test_manifest_mode_change_absent_from_patch_is_rejected(self) -> None:
        manifest = json.loads(self.manifest_path.read_text())
        manifest["files"]["host.py"]["post_mode"] = "100755"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(HostPatchError, "closed path/mode set mismatch"):
            HostPatchBundle.from_paths(self.manifest_path, self.patch_path)

    @unittest.skipIf(os.name == "nt", "POSIX no-follow semantics required")
    def test_predictable_temporary_symlink_cannot_redirect_transaction_write(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        temporary = self.repo / ".host.py.nunchi-fixed"
        real_snapshot = host_patch._snapshot_paths

        def plant_symlink(root, paths):
            snapshots = real_snapshot(root, paths)
            temporary.symlink_to(outside)
            return snapshots

        with (
            mock.patch.object(host_patch.secrets, "token_hex", return_value="fixed"),
            mock.patch.object(host_patch, "_snapshot_paths", side_effect=plant_symlink),
            self.assertRaisesRegex(HostPatchError, "inventory"),
        ):
            apply_host_patch(self.repo, self.bundle)

        self.assertEqual(outside.read_text(), "outside\n")
        self.assertEqual((self.repo / "host.py").read_text(), "value = 'stock'\n")


if __name__ == "__main__":
    unittest.main()
