from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from nunchi.integrations.hermes_dashboard_install import (
    DashboardInstallError,
    install_dashboard_for_profile,
)


class HermesDashboardProfileInstallTests(unittest.TestCase):
    def _modules(
        self,
        *,
        root: Path,
        profile_home: Path,
        disabled: bool = False,
        persist_enable: bool = True,
    ) -> tuple[dict[str, types.ModuleType], list[tuple[str, bool]]]:
        calls: list[tuple[str, bool]] = []
        loaded_config = {
            "plugins": {
                "enabled": [],
                "disabled": ["nunchi"] if disabled else [],
            }
        }
        package = types.ModuleType("hermes_cli")
        package.__path__ = []
        profiles = types.ModuleType("hermes_cli.profiles")
        profiles.normalize_profile_name = lambda value: str(value).strip().lower()
        profiles.validate_profile_name = lambda value: None
        profiles.get_profile_dir = (
            lambda value: root if value == "default" else profile_home
        )
        config = types.ModuleType("hermes_cli.config")
        config.load_config = lambda: loaded_config
        plugins_cmd = types.ModuleType("hermes_cli.plugins_cmd")

        def enable(name: str, *, enabled: bool) -> dict[str, object]:
            calls.append((name, enabled))
            if persist_enable:
                loaded_config["plugins"]["enabled"] = [name]
                loaded_config["plugins"]["disabled"] = []
            return {"ok": True, "name": name, "unchanged": False}

        plugins_cmd.dashboard_set_agent_plugin_enabled = enable
        constants = types.ModuleType("hermes_constants")
        constants.set_hermes_home_override = lambda path: ("token", path)
        constants.reset_hermes_home_override = lambda token: None
        return (
            {
                "hermes_cli": package,
                "hermes_cli.profiles": profiles,
                "hermes_cli.config": config,
                "hermes_cli.plugins_cmd": plugins_cmd,
                "hermes_constants": constants,
            },
            calls,
        )

    def test_named_profile_installs_profile_and_machine_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hermes"
            profile_home = root / "profiles" / "fiction-writer"
            profile_home.mkdir(parents=True)
            modules, calls = self._modules(
                root=root,
                profile_home=profile_home,
            )
            with (
                patch.dict(sys.modules, modules),
                patch(
                    "nunchi.integrations.hermes_dashboard_install."
                    "default_hermes_home",
                    return_value=profile_home,
                ),
            ):
                result = install_dashboard_for_profile(
                    profile="fiction-writer"
                )

            self.assertTrue(result["ok"])
            self.assertEqual([("nunchi", True)], calls)
            for home in (root, profile_home):
                self.assertTrue(
                    (
                        home
                        / "plugins"
                        / "nunchi-dashboard"
                        / "dashboard"
                        / "manifest.json"
                    ).is_file()
                )

    def test_named_profile_alias_installs_in_target_and_machine_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hermes"
            target = Path(temporary) / "volume" / "profile"
            target.mkdir(parents=True)
            alias = root / "profiles" / "fiction-writer"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(target, target_is_directory=True)
            modules, calls = self._modules(root=root, profile_home=alias)
            with (
                patch.dict(sys.modules, modules),
                patch(
                    "nunchi.integrations.hermes_dashboard_install.default_hermes_home",
                    return_value=alias,
                ),
            ):
                result = install_dashboard_for_profile(profile="fiction-writer")

            self.assertTrue(result["ok"])
            self.assertEqual([("nunchi", True)], calls)
            self.assertEqual(
                {
                    str(home.resolve() / "plugins/nunchi-dashboard/dashboard")
                    for home in (root, target)
                },
                {entry["path"] for entry in result["installed"]},
            )

    def test_broken_machine_home_is_rejected_before_profile_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "machine"
            root.symlink_to(Path(temporary) / "missing", target_is_directory=True)
            profile = Path(temporary) / "profile"
            profile.mkdir()
            modules, calls = self._modules(root=root, profile_home=profile)
            with (
                patch.dict(sys.modules, modules),
                patch(
                    "nunchi.integrations.hermes_dashboard_install.default_hermes_home",
                    return_value=profile,
                ),
                self.assertRaisesRegex(DashboardInstallError, "Hermes home"),
            ):
                install_dashboard_for_profile(profile="fiction-writer")
            self.assertFalse((profile / "plugins").exists())
            self.assertEqual([], calls)

    def test_explicit_machine_disable_is_respected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hermes"
            profile_home = root / "profiles" / "fiction-writer"
            profile_home.mkdir(parents=True)
            modules, calls = self._modules(
                root=root,
                profile_home=profile_home,
                disabled=True,
            )
            with (
                patch.dict(sys.modules, modules),
                patch(
                    "nunchi.integrations.hermes_dashboard_install."
                    "default_hermes_home",
                    return_value=profile_home,
                ),
            ):
                result = install_dashboard_for_profile(
                    profile="fiction-writer"
                )

            self.assertEqual([], calls)
            self.assertFalse(result["machine_dashboard"]["enabled"])
            self.assertEqual(
                "explicitly-disabled",
                result["machine_dashboard"]["reason"],
            )

    def test_reported_enable_must_be_visible_on_read_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hermes"
            profile_home = root / "profiles" / "fiction-writer"
            profile_home.mkdir(parents=True)
            modules, calls = self._modules(
                root=root,
                profile_home=profile_home,
                persist_enable=False,
            )
            with (
                patch.dict(sys.modules, modules),
                patch(
                    "nunchi.integrations.hermes_dashboard_install."
                    "default_hermes_home",
                    return_value=profile_home,
                ),
            ):
                with self.assertRaisesRegex(
                    Exception,
                    "did not persist Nunchi.*administrator.*--isolated",
                ):
                    install_dashboard_for_profile(
                        profile="fiction-writer"
                    )

            self.assertEqual([("nunchi", True)], calls)


if __name__ == "__main__":
    unittest.main()
