"""Tests for the copy-based operator-artifact installer (``nunchi.install``).

The installer touches operator environments, so every test here confines all
writes to fresh temp directories via the ``hermes_home`` / ``claude_home`` /
``prefix`` overrides. NOTHING in this module resolves or writes to the real
``~/.hermes`` or ``~/.claude`` (enforced structurally + by
``tests/test_no_home_writes.py``).

Determinism: the wall clock and the source-commit resolver are injected, so
marker timestamps and timestamped backup names are stable and offline.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nunchi import install
from nunchi.install import Installer, build_claude_settings_snippet, render_wrapper

_REPO_ROOT = Path(__file__).resolve().parents[1]

FIXED_DT = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
FIXED_SLUG = "20260709T120000Z"
FIXED_COMMIT = "abc1234def5678000000000000000000deadbeef"


def _fixed_clock():
    return FIXED_DT


def _seq_clock(*dts: datetime):
    """A clock that returns successive datetimes, repeating the last."""
    values = list(dts)

    def clock() -> datetime:
        return values.pop(0) if len(values) > 1 else values[0]

    return clock


def _installer(tmp: Path, *, repo_root: Path | None = None, dry_run: bool = False, clock=None, commit=FIXED_COMMIT):
    """Build an Installer confined to *tmp*, with injected clock + commit."""
    import io

    return Installer(
        repo_root=repo_root or _REPO_ROOT,
        hermes_home=tmp / ".hermes",
        claude_home=tmp / ".claude",
        dry_run=dry_run,
        clock=clock or _fixed_clock,
        commit_resolver=lambda: commit,
        out=io.StringIO(),
    )


def _make_fake_repo(root: Path) -> Path:
    """Create a minimal fake source repo tree under *root*; return *root*.

    Exercises the exclusion rules: ``docs/``, ``__pycache__/``, ``tests/`` must
    be dropped; top-level ``.py`` + ``plugin.yaml`` + ``dashboard/`` kept.
    """
    gate = root / "integrations" / "hermes" / "nunchi-gate"
    (gate / "dashboard").mkdir(parents=True)
    (gate / "__init__.py").write_text("# plugin entry\n", encoding="utf-8")
    (gate / "resolve.py").write_text("# resolve\n", encoding="utf-8")
    (gate / "plugin.yaml").write_text("name: nunchi-gate\n", encoding="utf-8")
    (gate / "dashboard" / "index.js").write_text("// dash\n", encoding="utf-8")
    (gate / "dashboard" / "plugin_api.py").write_text("# api\n", encoding="utf-8")
    # excluded groups:
    (gate / "docs").mkdir()
    (gate / "docs" / "README.md").write_text("# docs\n", encoding="utf-8")
    (gate / "__pycache__").mkdir()
    (gate / "__pycache__" / "resolve.cpython-311.pyc").write_bytes(b"\x00")
    (gate / "tests").mkdir()
    (gate / "tests" / "test_plugin.py").write_text("# t\n", encoding="utf-8")
    (gate / "stray.pyc").write_bytes(b"\x00")  # stray .pyc also skipped

    cc = root / "integrations" / "claude-code"
    cc.mkdir(parents=True)
    for name in install.CLAUDE_HOOK_FILES:
        (cc / name).write_text(f"# {name}\n", encoding="utf-8")
    return root


class _TmpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="nunchi-install-test-"))
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)


class InstallFreshTest(_TmpTest):
    def test_install_creates_real_dirs_not_symlinks(self) -> None:
        inst = _installer(self.tmp)
        report = inst.install()

        hermes = self.tmp / ".hermes" / "plugins" / "nunchi-gate"
        hooks = self.tmp / ".claude" / "hooks"
        self.assertTrue(hermes.is_dir())
        self.assertFalse(os.path.islink(hermes), "Hermes dest must be a REAL dir, never a symlink")
        self.assertTrue(hooks.is_dir())
        self.assertFalse(os.path.islink(hooks))
        self.assertEqual(report["artifacts"]["hermes"]["status"], "installed")

    def test_hermes_runtime_files_present(self) -> None:
        _installer(self.tmp).install()
        gate = self.tmp / ".hermes" / "plugins" / "nunchi-gate"
        for rel in ("__init__.py", "plugin.yaml", "resolve.py", "state.py", "dashboard/index.js"):
            self.assertTrue((gate / rel).is_file(), f"missing installed file {rel}")

    def test_claude_hooks_and_wrappers_present_and_executable(self) -> None:
        _installer(self.tmp).install()
        hooks = self.tmp / ".claude" / "hooks"
        for name in install.CLAUDE_HOOK_FILES:
            self.assertTrue((hooks / name).is_file())
        for wrapper in install.CLAUDE_WRAPPERS:
            path = hooks / wrapper
            self.assertTrue(path.is_file())
            self.assertTrue(os.access(path, os.X_OK), f"{wrapper} must be executable")
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertTrue(mode & stat.S_IXUSR)

    def test_version_stamp_written_with_injected_clock_and_commit(self) -> None:
        _installer(self.tmp).install()
        marker = json.loads(
            (self.tmp / ".hermes" / "plugins" / "nunchi-gate" / install.MARKER_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(marker["artifact"], "hermes-plugin")
        self.assertEqual(marker["source_commit"], FIXED_COMMIT)
        self.assertEqual(marker["installed_at"], FIXED_DT.isoformat())
        self.assertEqual(marker["installer"], "nunchi-install")
        self.assertIn("__init__.py", marker["files"])
        self.assertEqual(marker["source_path"], str(_REPO_ROOT / "integrations" / "hermes" / "nunchi-gate"))

    def test_claude_marker_written(self) -> None:
        _installer(self.tmp).install()
        marker = json.loads(
            (self.tmp / ".claude" / "hooks" / install.MARKER_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(marker["artifact"], "claude-code-hooks")
        self.assertEqual(marker["source_commit"], FIXED_COMMIT)
        for name in (*install.CLAUDE_HOOK_FILES, *install.CLAUDE_WRAPPERS):
            self.assertIn(name, marker["files"])

    def test_cli_check_reported(self) -> None:
        # nunchi-channel is present in this dev/CI env (installed package).
        report = _installer(self.tmp).install(groups=["cli"])
        self.assertIn(report["artifacts"]["cli"]["status"], (install.STATUS_IN_SYNC, install.STATUS_NOT_INSTALLED))


class ExclusionTest(_TmpTest):
    def test_excluded_dirs_and_pyc_not_copied_dashboard_kept(self) -> None:
        fake = _make_fake_repo(self.tmp / "repo")
        inst = _installer(self.tmp, repo_root=fake)
        report = inst.install(groups=["hermes"])

        gate = self.tmp / ".hermes" / "plugins" / "nunchi-gate"
        # kept
        self.assertTrue((gate / "__init__.py").is_file())
        self.assertTrue((gate / "plugin.yaml").is_file())
        self.assertTrue((gate / "dashboard" / "index.js").is_file())
        self.assertTrue((gate / "dashboard" / "plugin_api.py").is_file())
        # excluded
        self.assertFalse((gate / "docs").exists(), "docs/ must be excluded")
        self.assertFalse((gate / "__pycache__").exists(), "__pycache__/ must be excluded")
        self.assertFalse((gate / "tests").exists(), "tests/ must be excluded")
        self.assertFalse((gate / "stray.pyc").exists(), "stray .pyc must be skipped")

        files = report["artifacts"]["hermes"]["files"]
        self.assertNotIn("docs/README.md", files)
        self.assertIn("dashboard/index.js", files)

    def test_symlinked_source_file_copied_as_real_file(self) -> None:
        fake = _make_fake_repo(self.tmp / "repo")
        gate_src = fake / "integrations" / "hermes" / "nunchi-gate"
        real = gate_src / "resolve.py"
        link = gate_src / "linked.py"
        os.symlink(real, link)  # source contains a symlink

        _installer(self.tmp, repo_root=fake).install(groups=["hermes"])
        dest = self.tmp / ".hermes" / "plugins" / "nunchi-gate" / "linked.py"
        self.assertTrue(dest.is_file())
        self.assertFalse(os.path.islink(dest), "a symlinked source file must land as a REAL file")
        self.assertEqual(dest.read_text(encoding="utf-8"), "# resolve\n")


class SymlinkReplacementTest(_TmpTest):
    """The core incident fix: a symlinked destination is detected, backed up,
    and replaced with a real copy; the old target is recorded."""

    def _make_stale_checkout(self) -> Path:
        stale = self.tmp / "stale-checkout" / "nunchi-gate"
        stale.mkdir(parents=True)
        (stale / "__init__.py").write_text("# STALE branch code\n", encoding="utf-8")
        return stale

    def _pre_create_symlink(self, target: Path) -> Path:
        dest = self.tmp / ".hermes" / "plugins" / "nunchi-gate"
        dest.parent.mkdir(parents=True)
        os.symlink(target, dest)
        return dest

    def test_symlink_replaced_with_real_dir(self) -> None:
        target = self._make_stale_checkout()
        dest = self._pre_create_symlink(target)
        self.assertTrue(os.path.islink(dest))

        report = _installer(self.tmp).install(groups=["hermes"])

        self.assertFalse(os.path.islink(dest), "symlink must be gone")
        self.assertTrue(dest.is_dir())
        # real installed content, not the stale checkout's content
        self.assertIn("Nunchi", (dest / "__init__.py").read_text(encoding="utf-8"))
        replaced = report["artifacts"]["hermes"]["replaced_symlink"]
        self.assertEqual(replaced["target"], str(target))

    def test_old_symlink_target_recorded_in_marker(self) -> None:
        target = self._make_stale_checkout()
        self._pre_create_symlink(target)
        _installer(self.tmp).install(groups=["hermes"])

        marker = json.loads(
            (self.tmp / ".hermes" / "plugins" / "nunchi-gate" / install.MARKER_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(marker["replaced_symlink"]["target"], str(target))
        backup = Path(marker["replaced_symlink"]["backup"])
        self.assertTrue(os.path.islink(backup), "the replaced symlink is preserved as a backup link")
        self.assertEqual(os.readlink(backup), str(target))

    def test_verify_flags_symlink_found(self) -> None:
        target = self._make_stale_checkout()
        self._pre_create_symlink(target)
        report = _installer(self.tmp).verify(groups=["hermes"])
        self.assertEqual(report["artifacts"]["hermes"]["status"], install.STATUS_SYMLINK_FOUND)
        self.assertEqual(report["artifacts"]["hermes"]["symlink_target"], str(target))

    def test_claude_symlinked_hook_replaced_with_real_file(self) -> None:
        hooks = self.tmp / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        stale = self.tmp / "stale.py"
        stale.write_text("# stale hook\n", encoding="utf-8")
        hook = hooks / install.CLAUDE_HOOK_FILES[0]
        os.symlink(stale, hook)
        self.assertTrue(os.path.islink(hook))

        _installer(self.tmp).install(groups=["claude"])
        self.assertFalse(os.path.islink(hook), "symlinked hook must become a real file")
        self.assertTrue(hook.is_file())
        backups = list(hooks.glob(f"{install.CLAUDE_HOOK_FILES[0]}.symlink.bak.*"))
        self.assertEqual(len(backups), 1, "the replaced hook symlink must be backed up")


class UpgradeTest(_TmpTest):
    def test_upgrade_skips_when_commit_unchanged(self) -> None:
        _installer(self.tmp, commit=FIXED_COMMIT).install()
        report = _installer(self.tmp, commit=FIXED_COMMIT).upgrade()
        self.assertEqual(report["artifacts"]["hermes"]["action"], "skip")
        self.assertEqual(report["artifacts"]["hermes"]["status"], install.STATUS_IN_SYNC)
        # no backup created
        backups = list((self.tmp / ".hermes" / "plugins").glob("nunchi-gate.bak.*"))
        self.assertEqual(backups, [])

    def test_upgrade_recopies_and_backs_up_on_commit_change(self) -> None:
        clock = _seq_clock(FIXED_DT, FIXED_DT + timedelta(hours=1))
        _installer(self.tmp, commit="oldcommit", clock=clock).install()
        report = _installer(self.tmp, commit="newcommit", clock=clock).upgrade()

        self.assertEqual(report["artifacts"]["hermes"]["action"], "upgrade")
        # backup of the old copy exists (timestamped)
        backups = list((self.tmp / ".hermes" / "plugins").glob("nunchi-gate.bak.*"))
        self.assertEqual(len(backups), 1, "old copy must be backed up before re-copy")
        # marker now records the new commit
        marker = json.loads(
            (self.tmp / ".hermes" / "plugins" / "nunchi-gate" / install.MARKER_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(marker["source_commit"], "newcommit")

    def test_upgrade_force_recopies_even_if_unchanged(self) -> None:
        clock = _seq_clock(FIXED_DT, FIXED_DT + timedelta(hours=2))
        _installer(self.tmp, commit=FIXED_COMMIT, clock=clock).install()
        report = _installer(self.tmp, commit=FIXED_COMMIT, clock=clock).upgrade(force=True)
        self.assertEqual(report["artifacts"]["hermes"]["action"], "upgrade")
        backups = list((self.tmp / ".hermes" / "plugins").glob("nunchi-gate.bak.*"))
        self.assertEqual(len(backups), 1)

    def test_upgrade_installs_when_not_present(self) -> None:
        report = _installer(self.tmp).upgrade(groups=["hermes"])
        self.assertEqual(report["artifacts"]["hermes"]["action"], "upgrade")
        self.assertTrue((self.tmp / ".hermes" / "plugins" / "nunchi-gate").is_dir())

    def test_repeated_install_same_timestamp_makes_distinct_backups(self) -> None:
        # Same fixed clock across three installs must not clobber/raise: the
        # backup name gets a numeric suffix when the timestamped one exists.
        _installer(self.tmp).install(groups=["hermes"])  # creates, no backup
        _installer(self.tmp).install(groups=["hermes"])  # backup -> .bak.SLUG
        _installer(self.tmp).install(groups=["hermes"])  # backup -> .bak.SLUG.1
        backups = sorted((self.tmp / ".hermes" / "plugins").glob("nunchi-gate.bak.*"))
        self.assertEqual(len(backups), 2)
        self.assertTrue((self.tmp / ".hermes" / "plugins" / "nunchi-gate").is_dir())


class VerifyTest(_TmpTest):
    def test_not_installed(self) -> None:
        report = _installer(self.tmp).verify(groups=["hermes"])
        self.assertEqual(report["artifacts"]["hermes"]["status"], install.STATUS_NOT_INSTALLED)

    def test_in_sync(self) -> None:
        _installer(self.tmp, commit=FIXED_COMMIT).install()
        report = _installer(self.tmp, commit=FIXED_COMMIT).verify()
        self.assertEqual(report["artifacts"]["hermes"]["status"], install.STATUS_IN_SYNC)
        self.assertEqual(report["artifacts"]["claude"]["status"], install.STATUS_IN_SYNC)

    def test_stale_when_commit_differs(self) -> None:
        _installer(self.tmp, commit="oldcommit").install()
        report = _installer(self.tmp, commit="newcommit").verify(groups=["hermes"])
        self.assertEqual(report["artifacts"]["hermes"]["status"], install.STATUS_STALE)
        self.assertEqual(report["artifacts"]["hermes"]["installed_commit"], "oldcommit")

    def test_stale_when_unmanaged_no_marker(self) -> None:
        _installer(self.tmp).install(groups=["hermes"])
        (self.tmp / ".hermes" / "plugins" / "nunchi-gate" / install.MARKER_NAME).unlink()
        report = _installer(self.tmp).verify(groups=["hermes"])
        self.assertEqual(report["artifacts"]["hermes"]["status"], install.STATUS_STALE)

    def test_claude_symlink_found(self) -> None:
        hooks = self.tmp / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        target = self.tmp / "somewhere.py"
        target.write_text("x\n", encoding="utf-8")
        os.symlink(target, hooks / install.CLAUDE_HOOK_FILES[0])
        report = _installer(self.tmp).verify(groups=["claude"])
        self.assertEqual(report["artifacts"]["claude"]["status"], install.STATUS_SYMLINK_FOUND)


class DryRunTest(_TmpTest):
    def test_dry_run_install_touches_nothing(self) -> None:
        report = _installer(self.tmp, dry_run=True).install()
        # nothing created under either home
        created = list((self.tmp).rglob("*"))
        self.assertEqual(created, [], f"dry-run must not write anything, found {created}")
        # but actions were still planned
        self.assertTrue(any(a["op"] == "copy" for a in report["actions"]))
        self.assertTrue(all(a["dry_run"] for a in report["actions"]))

    def test_dry_run_uninstall_touches_nothing(self) -> None:
        _installer(self.tmp).install()
        before = sorted(p.name for p in (self.tmp / ".hermes" / "plugins" / "nunchi-gate").iterdir())
        _installer(self.tmp, dry_run=True).uninstall()
        after = sorted(p.name for p in (self.tmp / ".hermes" / "plugins" / "nunchi-gate").iterdir())
        self.assertEqual(before, after, "dry-run uninstall must not delete anything")


class UninstallTest(_TmpTest):
    def test_uninstall_removes_copies(self) -> None:
        _installer(self.tmp).install()
        _installer(self.tmp).uninstall()
        self.assertFalse((self.tmp / ".hermes" / "plugins" / "nunchi-gate").exists())
        hooks = self.tmp / ".claude" / "hooks"
        for name in (*install.CLAUDE_HOOK_FILES, *install.CLAUDE_WRAPPERS, install.MARKER_NAME):
            self.assertFalse((hooks / name).exists(), f"{name} should be removed")

    def test_uninstall_restores_backed_up_symlink(self) -> None:
        target = self.tmp / "live-checkout" / "nunchi-gate"
        target.mkdir(parents=True)
        (target / "__init__.py").write_text("# live\n", encoding="utf-8")
        dest = self.tmp / ".hermes" / "plugins" / "nunchi-gate"
        dest.parent.mkdir(parents=True)
        os.symlink(target, dest)

        _installer(self.tmp).install(groups=["hermes"])
        self.assertFalse(os.path.islink(dest))  # replaced with real dir

        report = _installer(self.tmp).uninstall(groups=["hermes"])
        self.assertTrue(os.path.islink(dest), "uninstall must restore the original symlink")
        self.assertEqual(os.readlink(dest), str(target))
        self.assertIsNotNone(report["artifacts"]["hermes"].get("restored_symlink"))

    def test_uninstall_not_installed_is_benign(self) -> None:
        report = _installer(self.tmp).uninstall()
        self.assertEqual(report["artifacts"]["hermes"]["action"], "skip")
        self.assertEqual(report["artifacts"]["claude"]["action"], "skip")

    def test_uninstall_leaves_foreign_files_in_hooks_dir(self) -> None:
        _installer(self.tmp).install()
        hooks = self.tmp / ".claude" / "hooks"
        foreign = hooks / "operator-note.txt"
        foreign.write_text("keep me\n", encoding="utf-8")
        _installer(self.tmp).uninstall()
        self.assertTrue(foreign.is_file(), "uninstall must not delete operator files it did not install")


class CliCheckTest(_TmpTest):
    def _bin_dir(self) -> Path:
        d = self.tmp / "bin"
        d.mkdir()
        return d

    def test_cli_found_when_on_path(self) -> None:
        from unittest.mock import patch

        bindir = self._bin_dir()
        fake = bindir / "nunchi-channel"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(fake, 0o755)
        with patch.dict(os.environ, {"PATH": str(bindir)}):
            report = _installer(self.tmp).verify(groups=["cli"])
        self.assertEqual(report["artifacts"]["cli"]["status"], install.STATUS_IN_SYNC)
        self.assertEqual(report["artifacts"]["cli"]["resolved"], str(fake))

    def test_cli_missing_gives_pip_guidance(self) -> None:
        from unittest.mock import patch

        empty = self._bin_dir()  # no nunchi-channel here
        with patch.dict(os.environ, {"PATH": str(empty)}):
            report = _installer(self.tmp).verify(groups=["cli"])
        self.assertEqual(report["artifacts"]["cli"]["status"], install.STATUS_NOT_INSTALLED)
        self.assertIn("pip install", report["artifacts"]["cli"]["guidance"])


class SettingsSnippetTest(_TmpTest):
    def test_snippet_points_at_stable_wrapper_paths_not_repo(self) -> None:
        snippet = build_claude_settings_snippet(self.tmp / ".claude")
        data = json.loads(snippet)
        ups = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertTrue(ups.endswith("/.claude/hooks/nunchi-user-prompt-submit.sh"))
        self.assertNotIn("integrations", ups, "snippet must not point at a repo checkout")

    def test_snippet_has_no_retired_send_time_gate(self) -> None:
        """One judgment per turn: the snippet must never re-suggest the retired
        PreToolUse (send-time) gate."""
        snippet = build_claude_settings_snippet(self.tmp / ".claude")
        data = json.loads(snippet)
        self.assertNotIn("PreToolUse", data["hooks"])
        self.assertNotIn("nunchi-pretool-reply", snippet)


class WrapperContentTest(_TmpTest):
    def test_wrapper_is_fail_open_and_sources_env(self) -> None:
        hooks = self.tmp / ".claude" / "hooks"
        hook_path = hooks / install.CLAUDE_HOOK_FILES[0]
        env_file = self.tmp / ".claude" / "nunchi-gate.env"
        content = render_wrapper("nunchi-user-prompt-submit.sh", hook_path, [env_file])

        self.assertIn("#!/bin/sh", content)
        self.assertIn("|| exit 0", content, "wrapper must fail open")
        self.assertIn('[ -f "$HOOK" ] || exit 0', content, "missing hook must not block")
        self.assertIn("command -v python3", content)
        self.assertIn(str(env_file), content, "wrapper must source the operator env file")
        self.assertIn(str(hook_path), content, "wrapper must point at the stable hook path")
        self.assertNotIn("integrations", content, "wrapper must not reference a repo checkout")

    def test_wrapper_sources_env_files_in_order(self) -> None:
        # Shared identity is sourced before the per-hook override so the
        # override's exports win (e.g. a narrower per-hook roster).
        hooks = self.tmp / ".claude" / "hooks"
        hook_path = hooks / install.CLAUDE_HOOK_FILES[0]
        shared = self.tmp / ".claude" / "nunchi-gate.env"
        override = self.tmp / ".claude" / "nunchi-user-prompt-submit.env"
        content = render_wrapper("nunchi-user-prompt-submit.sh", hook_path, [shared, override])

        self.assertLess(
            content.index(str(shared)),
            content.index(str(override)),
            "shared env must be sourced before the per-hook override",
        )
        # Each env file is guarded so a missing file never breaks the gate.
        self.assertIn(f'[ -f "{override}" ] && . "{override}"', content)

    def test_installed_wrapper_points_at_installed_hook(self) -> None:
        _installer(self.tmp).install(groups=["claude"])
        hooks = self.tmp / ".claude" / "hooks"
        wrapper = (hooks / "nunchi-user-prompt-submit.sh").read_text(encoding="utf-8")
        self.assertIn(str(hooks / install.CLAUDE_HOOK_FILES[0]), wrapper)

    def test_installed_wrapper_sources_shared_and_override_env(self) -> None:
        _installer(self.tmp).install(groups=["claude"])
        claude = self.tmp / ".claude"
        wrapper = (claude / "hooks" / "nunchi-user-prompt-submit.sh").read_text(encoding="utf-8")
        self.assertIn(str(claude / "nunchi-gate.env"), wrapper)
        self.assertIn(str(claude / "nunchi-user-prompt-submit.env"), wrapper)


class RetiredArtifactCleanupTest(_TmpTest):
    """Upgrading over an old two-gate install must remove the retired send-time
    gate — otherwise the machine keeps running the re-judgment path this
    version deleted (the false-PASS bug would silently stay live)."""

    def _seed_old_install(self) -> Path:
        hooks = self.tmp / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "nunchi_gate_hook.py").write_text("# retired send-time gate\n", encoding="utf-8")
        (hooks / "nunchi-pretool-reply.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        return hooks

    def test_install_removes_retired_send_time_gate(self) -> None:
        hooks = self._seed_old_install()
        result = _installer(self.tmp).install(groups=["claude"])
        claude = result["artifacts"]["claude"]
        self.assertFalse((hooks / "nunchi_gate_hook.py").exists())
        self.assertFalse((hooks / "nunchi-pretool-reply.sh").exists())
        self.assertEqual(
            sorted(claude["retired"]), ["nunchi-pretool-reply.sh", "nunchi_gate_hook.py"]
        )
        self.assertIn("PreToolUse", claude["settings_note"])
        # Removed, not destroyed: a timestamped backup of each retired file exists.
        for stem in ("nunchi_gate_hook.py", "nunchi-pretool-reply.sh"):
            self.assertTrue(
                list(hooks.glob(f"{stem}.bak.*")),
                f"expected a backup of retired {stem}",
            )

    def test_verify_flags_retired_leftovers_as_stale(self) -> None:
        inst = _installer(self.tmp)
        inst.install(groups=["claude"])
        hooks = self.tmp / ".claude" / "hooks"
        (hooks / "nunchi_gate_hook.py").write_text("# ghost\n", encoding="utf-8")
        report = inst.verify(groups=["claude"])
        claude = report["artifacts"]["claude"]
        self.assertEqual(claude["status"], install.STATUS_STALE)
        self.assertEqual(claude["retired_leftovers"], ["nunchi_gate_hook.py"])

    def test_uninstall_also_removes_retired_files(self) -> None:
        hooks = self._seed_old_install()
        inst = _installer(self.tmp)
        inst.install(groups=["claude"])
        (hooks / "nunchi_gate_hook.py").write_text("# ghost again\n", encoding="utf-8")
        inst.uninstall(groups=["claude"])
        self.assertFalse((hooks / "nunchi_gate_hook.py").exists())
        self.assertFalse((hooks / "nunchi-user-prompt-submit.sh").exists())

    def test_verify_upgrade_verify_converges(self) -> None:
        """Aleph's loop: verify says stale (leftovers) → upgrade must NOT
        early-skip on an in-sync marker — after it runs, verify is clean."""
        inst = _installer(self.tmp)
        inst.install(groups=["claude"])
        hooks = self.tmp / ".claude" / "hooks"
        # Marker is in-sync, but a retired ghost reappears (partial migration).
        (hooks / "nunchi_gate_hook.py").write_text("# ghost\n", encoding="utf-8")

        first = inst.verify(groups=["claude"])["artifacts"]["claude"]
        self.assertEqual(first["status"], install.STATUS_STALE)
        self.assertEqual(first["retired_leftovers"], ["nunchi_gate_hook.py"])

        result = inst.upgrade(groups=["claude"])["artifacts"]["claude"]
        self.assertNotEqual(
            result["action"], "skip",
            "upgrade must not skip past retired leftovers verify just flagged",
        )
        self.assertFalse((hooks / "nunchi_gate_hook.py").exists())

        second = inst.verify(groups=["claude"])["artifacts"]["claude"]
        self.assertEqual(second["status"], install.STATUS_IN_SYNC)
        self.assertNotIn("retired_leftovers", second)

    def test_upgrade_still_skips_when_clean_and_in_sync(self) -> None:
        """The early-skip fast path survives for genuinely clean installs."""
        inst = _installer(self.tmp)
        inst.install(groups=["claude"])
        result = inst.upgrade(groups=["claude"])["artifacts"]["claude"]
        self.assertEqual(result["action"], "skip")

    def test_verify_flags_stale_settings_entry_read_only(self) -> None:
        """A settings.json still registering the retired gate (e.g. an old
        absolute checkout path) is reported — without ever writing settings."""
        inst = _installer(self.tmp)
        inst.install(groups=["claude"])
        settings = self.tmp / ".claude" / "settings.json"
        settings.write_text(
            '{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", '
            '"command": "/old/checkout/integrations/claude-code/nunchi_gate_hook.py"}]}]}}\n',
            encoding="utf-8",
        )
        before = settings.read_text(encoding="utf-8")
        report = inst.verify(groups=["claude"])["artifacts"]["claude"]
        self.assertEqual(report["status"], install.STATUS_STALE)
        self.assertEqual(report["stale_settings_entries"], ["nunchi_gate_hook"])
        self.assertEqual(settings.read_text(encoding="utf-8"), before,
                         "verify must never modify operator-owned settings.json")


class NeverTouchesRealHomeTest(_TmpTest):
    def test_homes_are_confined_to_temp(self) -> None:
        inst = _installer(self.tmp)
        self.assertTrue(str(inst.hermes_home).startswith(str(self.tmp)))
        self.assertTrue(str(inst.claude_home).startswith(str(self.tmp)))

    def test_all_writes_land_under_given_homes(self) -> None:
        inst = _installer(self.tmp)
        inst.install()
        for record in inst_actions(inst):
            target = record["target"]
            if record["op"] in {"copy", "write", "stamp", "mkdir", "backup"}:
                self.assertTrue(
                    target.startswith(str(self.tmp)),
                    f"write op {record['op']} escaped temp: {target}",
                )


def inst_actions(inst: Installer):
    # Re-run report accessor: actions from the last command.
    return inst._actions  # noqa: SLF001 - test introspection


class ResolveSourceCommitTest(_TmpTest):
    def test_falls_back_to_version_file(self) -> None:
        repo = self.tmp / "repo-noniso"
        repo.mkdir()
        (repo / "VERSION").write_text("v9.9.9\n", encoding="utf-8")
        # Not a git repo → git rev-parse fails → VERSION used.
        self.assertEqual(install.resolve_source_commit(repo), "v9.9.9")

    def test_unknown_when_nothing_available(self) -> None:
        repo = self.tmp / "repo-empty"
        repo.mkdir()
        self.assertEqual(install.resolve_source_commit(repo), "unknown")

    def test_discover_repo_root_finds_integrations(self) -> None:
        root = install.discover_repo_root(Path(install.__file__))
        self.assertTrue((root / "integrations" / "hermes" / "nunchi-gate").is_dir())


class CliMainTest(_TmpTest):
    def _run(self, argv, extra_env: dict | None = None):
        """Run the CLI main with a sandboxed environment.

        HOME is pinned into the temp dir and HERMES_HOME is cleared so an
        operator's live profile can never be touched by a test run — an
        inherited HERMES_HOME once outranked --prefix and let a review run
        write backups into the ACTIVE Hermes plugin (2026-07-10).
        """
        import io
        from unittest.mock import patch

        env = {"HOME": str(self.tmp / "sandbox-home")}
        if extra_env:
            env.update(extra_env)
        buf = io.StringIO()
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("HERMES_HOME", None)
            if extra_env and "HERMES_HOME" in extra_env:
                os.environ["HERMES_HOME"] = extra_env["HERMES_HOME"]
            code = install.main(argv, out=buf)
        return code, buf.getvalue()

    def test_prefix_outranks_inherited_hermes_home(self) -> None:
        """--prefix confines every write even when HERMES_HOME points at a
        (simulated) live profile."""
        simulated_live = self.tmp / "simulated-live-hermes"
        simulated_live.mkdir()
        code, _ = self._run(
            ["--prefix", str(self.tmp / "sandbox"), "install"],
            extra_env={"HERMES_HOME": str(simulated_live)},
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            list(simulated_live.rglob("*")), [],
            "an inherited HERMES_HOME must not receive writes when --prefix is explicit",
        )
        self.assertTrue(
            (self.tmp / "sandbox" / ".hermes" / "plugins" / "nunchi-gate").is_dir()
        )

    def test_env_hermes_home_still_used_without_prefix(self) -> None:
        """Without --prefix, an explicit HERMES_HOME env remains the operator's
        chosen target (documented behavior, unchanged)."""
        env_home = self.tmp / "env-hermes"
        code, _ = self._run(
            ["--claude-home", str(self.tmp / ".claude"), "install", "--only", "hermes"],
            extra_env={"HERMES_HOME": str(env_home)},
        )
        self.assertEqual(code, 0)
        self.assertTrue((env_home / "plugins" / "nunchi-gate").is_dir())

    def test_install_via_main_creates_real_dir(self) -> None:
        code, _ = self._run(["--prefix", str(self.tmp), "install"])
        self.assertEqual(code, 0)
        dest = self.tmp / ".hermes" / "plugins" / "nunchi-gate"
        self.assertTrue(dest.is_dir())
        self.assertFalse(os.path.islink(dest))

    def test_flags_work_after_subcommand(self) -> None:
        code, _ = self._run(["install", "--prefix", str(self.tmp)])
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / ".hermes" / "plugins" / "nunchi-gate").is_dir())

    def test_dry_run_via_main_touches_nothing(self) -> None:
        code, out = self._run(["--dry-run", "--prefix", str(self.tmp), "install"])
        self.assertEqual(code, 0)
        self.assertEqual(list(self.tmp.rglob("*")), [])
        self.assertIn("DRY-RUN", out)

    def test_install_prints_settings_snippet(self) -> None:
        _code, out = self._run(["--prefix", str(self.tmp), "install"])
        self.assertIn("settings.json", out)
        self.assertIn("nunchi-user-prompt-submit.sh", out)
        self.assertIn("NOT applied for you", out)

    def test_print_claude_settings_command(self) -> None:
        code, out = self._run(["--claude-home", str(self.tmp / ".claude"), "print-claude-settings"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("UserPromptSubmit", data["hooks"])
        self.assertNotIn("PreToolUse", data["hooks"])

    def test_verify_via_main(self) -> None:
        self._run(["--prefix", str(self.tmp), "install"])
        code, out = self._run(["--prefix", str(self.tmp), "verify"])
        self.assertEqual(code, 0)
        self.assertIn("in-sync", out)

    def test_hermes_home_and_claude_home_overrides(self) -> None:
        h = self.tmp / "h"
        c = self.tmp / "c"
        code, _ = self._run(["--hermes-home", str(h), "--claude-home", str(c), "install"])
        self.assertEqual(code, 0)
        self.assertTrue((h / "plugins" / "nunchi-gate").is_dir())
        self.assertTrue((c / "hooks" / "nunchi-user-prompt-submit.sh").is_file())

    def test_missing_source_reports_error(self) -> None:
        empty_repo = self.tmp / "empty-repo"
        empty_repo.mkdir()
        code, out = self._run(["--repo-root", str(empty_repo), "--prefix", str(self.tmp), "install", "--only", "hermes"])
        self.assertEqual(code, install.EXIT_ERROR)
        self.assertIn("error", out.lower())


if __name__ == "__main__":
    unittest.main()
