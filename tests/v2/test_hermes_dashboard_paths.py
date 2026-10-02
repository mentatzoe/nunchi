"""Dashboard installation accepts a profile alias, not redirected assets."""
from pathlib import Path
import tempfile
import unittest

from nunchi.integrations.hermes_dashboard_install import (
    DashboardInstallError,
    install_dashboard,
    verify_dashboard,
)


class HermesDashboardPathTests(unittest.TestCase):
    def test_symlinked_profile_installs_and_verifies_in_resolved_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_home = root / "volume" / "profile"
            real_home.mkdir(parents=True)
            alias = root / "profile-alias"
            alias.symlink_to(real_home, target_is_directory=True)

            installed = install_dashboard(hermes_home=alias)

            self.assertTrue(installed["ok"])
            self.assertEqual(installed, verify_dashboard(hermes_home=alias))
            self.assertEqual(installed, install_dashboard(hermes_home=alias))
            self.assertEqual(
                str(real_home.resolve() / "plugins/nunchi-dashboard/dashboard"),
                installed["path"],
            )
            self.assertTrue(alias.is_symlink())

    def test_redirected_plugins_rejected_before_bytecode_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            install_dashboard(hermes_home=outside)
            cache = outside / "plugins/nunchi-dashboard/dashboard/__pycache__"
            cache.mkdir()
            bytecode = cache / "plugin_api.cpython-311.pyc"
            bytecode.write_bytes(b"must not be removed")
            home = root / "profile"
            home.mkdir()
            (home / "plugins").symlink_to(outside / "plugins", target_is_directory=True)

            with self.assertRaises(DashboardInstallError):
                install_dashboard(hermes_home=home)

            self.assertTrue(bytecode.exists(), "rejection must precede all mutation")
            self.assertEqual(b"must not be removed", bytecode.read_bytes())

    def test_broken_profile_alias_does_not_create_its_missing_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "unmounted-volume" / "profile"
            alias = root / "profile-alias"
            alias.symlink_to(missing, target_is_directory=True)
            for operation in (install_dashboard, verify_dashboard):
                with self.assertRaisesRegex(DashboardInstallError, "Hermes home"):
                    operation(hermes_home=alias)
            self.assertFalse(missing.exists())

    def test_profile_symlink_cycle_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            first.symlink_to(second, target_is_directory=True)
            second.symlink_to(first, target_is_directory=True)
            for operation in (install_dashboard, verify_dashboard):
                with self.assertRaisesRegex(DashboardInstallError, "Hermes home"):
                    operation(hermes_home=first)

    def test_legacy_bridge_symlink_rejected_before_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            install_dashboard(hermes_home=outside)
            outside_bridge = outside / "plugins/nunchi-dashboard"
            marker = outside_bridge / ".nunchi-dashboard.json"
            legacy_marker = outside_bridge / ".nunchi-v2-dashboard.json"
            marker.rename(legacy_marker)
            home = root / "profile"
            plugins = home / "plugins"
            plugins.mkdir(parents=True)
            legacy = plugins / "nunchi-v2-dashboard"
            legacy.symlink_to(outside_bridge, target_is_directory=True)

            with self.assertRaises(DashboardInstallError):
                install_dashboard(hermes_home=home)

            self.assertTrue(legacy.is_symlink(), "must not migrate a redirected bridge")
            self.assertTrue(legacy_marker.is_file(), "outside marker must not be renamed")
            self.assertFalse(marker.exists())

    def test_dangling_dashboard_directory_symlinks_fail_with_repair_error(self):
        for relative in ("plugins", "plugins/nunchi-dashboard", "plugins/nunchi-dashboard/dashboard"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary) / "profile"
                link = home / relative
                link.parent.mkdir(parents=True)
                link.symlink_to(Path(temporary) / "missing", target_is_directory=True)
                for operation in (install_dashboard, verify_dashboard):
                    with self.assertRaisesRegex(DashboardInstallError, "symlink"):
                        operation(hermes_home=home)
                self.assertTrue(link.is_symlink())
                self.assertFalse((Path(temporary) / "missing").exists())

    def test_profile_alias_does_not_allow_redirected_dashboard_descendants(self):
        for relative in (
            "plugins",
            "plugins/nunchi-dashboard",
            "plugins/nunchi-dashboard/dashboard",
            "plugins/nunchi-dashboard/.nunchi-dashboard.json",
            "plugins/nunchi-dashboard/dashboard/index.js",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = root / "profile"
                outside = root / "outside"
                install_dashboard(hermes_home=home)
                redirected = home / relative
                redirected.rename(outside)
                redirected.symlink_to(outside, target_is_directory=outside.is_dir())
                alias = root / "alias"
                alias.symlink_to(home, target_is_directory=True)
                before = self._file_bytes(outside)
                for operation in (install_dashboard, verify_dashboard):
                    with self.assertRaises(DashboardInstallError):
                        operation(hermes_home=alias)
                self.assertEqual(before, self._file_bytes(outside))
                self.assertTrue(redirected.is_symlink())

    @staticmethod
    def _file_bytes(path):
        if path.is_file():
            return {"file": path.read_bytes()}
        return {
            str(child.relative_to(path)): child.read_bytes()
            for child in path.rglob("*") if child.is_file()
        }


if __name__ == "__main__":
    unittest.main()
