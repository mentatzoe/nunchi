"""Installed-host acceptance for the Hermes capability contract.

This test is opt-in because Hermes is not a runtime dependency of Nunchi. The
compatibility workflow installs an exact Hermes candidate, sets
``NUNCHI_REQUIRE_HERMES_CONTRACT=1``, and runs this module in an isolated
process.
"""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nunchi.integrations import hermes_v2
from tests.v2.test_hermes_portable import FakeLlm, room_config


@unittest.skipUnless(
    os.environ.get("NUNCHI_REQUIRE_HERMES_CONTRACT") == "1",
    "set NUNCHI_REQUIRE_HERMES_CONTRACT=1 after installing a Hermes candidate",
)
class InstalledHermesHostContractTests(unittest.TestCase):
    def test_aa_plugin_manager_failure_restores_registry_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            platform = os.environ.get("NUNCHI_HERMES_PLATFORM", "discord")
            self.assertIn(platform, {"discord", "telegram"})
            config, _ = room_config(
                Path(temporary),
                llm=FakeLlm([]),
                platform=platform,
            )
            plugins = importlib.import_module("hermes_cli.plugins")
            dashboard_install = importlib.import_module(
                "nunchi.integrations.hermes_dashboard_install"
            )
            manager = plugins.PluginManager()
            manifest = next(
                candidate
                for candidate in manager._scan_entry_points()
                if candidate.name == "nunchi"
            )

            def sentinel_hook():
                return None

            def sentinel_handler():
                return None

            sentinel_command = {
                "handler": sentinel_handler,
                "plugin": "existing",
            }
            original_hook_list = [sentinel_hook]
            hook_registry = manager._hooks
            command_registry = manager._plugin_commands
            hook_registry["pre_tool_call"] = original_hook_list
            command_registry["existing"] = sentinel_command
            original_register_command = plugins.PluginContext.register_command
            original_set_shim_attribute = hermes_v2._set_shim_attribute
            patched_attributes = {}

            def track_shim_attribute(target, name, replacement):
                patched_attributes.setdefault((target, name), getattr(target, name))
                original_set_shim_attribute(target, name, replacement)

            def fail_after_nunchi_command(context, name, handler, **kwargs):
                original_register_command(context, name, handler, **kwargs)
                if context.manifest.name == "nunchi" and name == "nunchi":
                    raise RuntimeError("command registry failed")

            with (
                mock.patch.dict(os.environ, {"HERMES_HOME": temporary}),
                mock.patch.object(
                    hermes_v2,
                    "_default_config_loader",
                    return_value=config,
                ),
                mock.patch.object(
                    dashboard_install,
                    "install_dashboard_for_profile",
                    return_value=None,
                ),
                mock.patch.object(
                    plugins.PluginContext,
                    "register_command",
                    new=fail_after_nunchi_command,
                ),
                mock.patch.object(
                    hermes_v2,
                    "_set_shim_attribute",
                    new=track_shim_attribute,
                ),
            ):
                manager._load_plugin(manifest)

        plugin = next(item for item in manager.list_plugins() if item["name"] == "nunchi")
        self.assertIn("command registry failed", plugin["error"])
        self.assertIs(manager._hooks, hook_registry)
        self.assertIs(manager._plugin_commands, command_registry)
        self.assertIs(hook_registry["pre_tool_call"], original_hook_list)
        self.assertEqual([sentinel_hook], original_hook_list)
        self.assertEqual({"pre_tool_call": original_hook_list}, hook_registry)
        self.assertEqual({"existing": sentinel_command}, command_registry)
        self.assertGreaterEqual(len(patched_attributes), 60)
        self.assertTrue(
            any(
                platform
                in (
                    f"{getattr(target, '__module__', '')}."
                    f"{getattr(target, '__name__', '')}"
                ).lower()
                for target, _ in patched_attributes
            )
        )
        for (target, name), original in patched_attributes.items():
            with self.subTest(target=target, name=name):
                self.assertIs(getattr(target, name), original)
        self.assertIsNone(hermes_v2._SHIM_OWNER)
        self.assertIsNone(hermes_v2._ORIGINAL_BASE_HANDLE)

    def test_ab_setup_mode_failure_restores_command_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugins = importlib.import_module("hermes_cli.plugins")
            dashboard_install = importlib.import_module(
                "nunchi.integrations.hermes_dashboard_install"
            )
            manager = plugins.PluginManager()
            manifest = next(
                candidate
                for candidate in manager._scan_entry_points()
                if candidate.name == "nunchi"
            )

            def sentinel_handler(raw_args):
                return raw_args

            command_registry = manager._plugin_commands
            sentinel_command = {
                "handler": sentinel_handler,
                "plugin": "existing",
            }
            command_registry["existing"] = sentinel_command
            original_register_command = plugins.PluginContext.register_command

            def fail_after_nunchi_command(context, name, handler, **kwargs):
                original_register_command(context, name, handler, **kwargs)
                if context.manifest.name == "nunchi" and name == "nunchi":
                    raise RuntimeError("setup command registry failed")

            with (
                mock.patch.dict(os.environ, {"HERMES_HOME": temporary}),
                mock.patch.object(
                    hermes_v2,
                    "_default_config_loader",
                    side_effect=hermes_v2.HermesSetupRequired("setup required"),
                ),
                mock.patch.object(
                    dashboard_install,
                    "install_dashboard_for_profile",
                    return_value=None,
                ),
                mock.patch.object(
                    plugins.PluginContext,
                    "register_command",
                    new=fail_after_nunchi_command,
                ),
            ):
                manager._load_plugin(manifest)

        plugin = next(item for item in manager.list_plugins() if item["name"] == "nunchi")
        self.assertIn("setup command registry failed", plugin["error"])
        self.assertIs(manager._plugin_commands, command_registry)
        self.assertEqual({"existing": sentinel_command}, command_registry)
        self.assertNotIn("nunchi", command_registry)

    def test_hermes_plugin_manager_discovers_installed_entry_point(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "config.yaml").write_text(
                "plugins:\n  enabled:\n    - nunchi\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"HERMES_HOME": temporary}):
                plugins = importlib.import_module("hermes_cli.plugins")

                previous_manager = getattr(plugins, "_plugin_manager")
                self.addCleanup(setattr, plugins, "_plugin_manager", previous_manager)
                setattr(plugins, "_plugin_manager", plugins.PluginManager())
                plugins.discover_plugins(force=True)
                plugin = next(
                    item
                    for item in plugins.get_plugin_manager().list_plugins()
                    if item["name"] == "nunchi"
                )

        self.assertEqual("entrypoint", plugin["source"])
        self.assertTrue(plugin["enabled"])
        self.assertGreaterEqual(plugin["commands"], 1)
        self.assertIsNone(plugin["error"])

    def test_installed_runtime_satisfies_host_contract_v1(self):
        hermes_version = importlib.metadata.version("hermes-agent")
        platform = os.environ.get("NUNCHI_HERMES_PLATFORM", "discord")
        self.assertIn(platform, {"discord", "telegram"})
        self.assertGreaterEqual(
            hermes_v2._version_tuple(hermes_version),
            hermes_v2._MINIMUM_HERMES,
        )

        with tempfile.TemporaryDirectory() as temporary:
            config, _ = room_config(
                Path(temporary),
                llm=FakeLlm([]),
                platform=platform,
            )
            plugins = importlib.import_module("hermes_cli.plugins")
            dashboard_install = importlib.import_module(
                "nunchi.integrations.hermes_dashboard_install"
            )
            manager = plugins.PluginManager()
            manifest = next(
                candidate
                for candidate in manager._scan_entry_points()
                if candidate.name == "nunchi"
            )
            original_owner = hermes_v2._SHIM_OWNER
            original_base_handle = hermes_v2._ORIGINAL_BASE_HANDLE
            original_set_shim_attribute = hermes_v2._set_shim_attribute
            patched_attributes = {}

            def track_shim_attribute(target, name, replacement):
                patched_attributes.setdefault((target, name), getattr(target, name))
                original_set_shim_attribute(target, name, replacement)

            try:
                with (
                    mock.patch.dict(
                        os.environ,
                        {"HERMES_HOME": temporary},
                        clear=False,
                    ),
                    mock.patch.object(
                        hermes_v2,
                        "_default_config_loader",
                        return_value=config,
                    ),
                    mock.patch.object(
                        dashboard_install,
                        "install_dashboard_for_profile",
                        return_value=None,
                    ),
                    mock.patch.object(
                        hermes_v2,
                        "_set_shim_attribute",
                        new=track_shim_attribute,
                    ),
                ):
                    manager._load_plugin(manifest)

                plugin_info = next(
                    item for item in manager.list_plugins() if item["name"] == "nunchi"
                )
                self.assertEqual("entrypoint", plugin_info["source"])
                self.assertTrue(plugin_info["enabled"])
                self.assertIsNone(plugin_info["error"])
                self.assertGreaterEqual(plugin_info["commands"], 1)
                self.assertEqual(
                    {"pre_llm_call", "post_llm_call", "pre_tool_call"},
                    set(manager._hooks),
                )
                self.assertIn("nunchi", manager._plugin_commands)

                plugin = hermes_v2._SHIM_OWNER
                self.assertIsNotNone(plugin)
                assert plugin is not None
                probe = plugin.probe()
                self.assertEqual(hermes_version, probe["hermes_version"])
                self.assertEqual("0.19.0", probe["minimum_hermes_version"])
                self.assertEqual(
                    "minimum-plus-host-contract",
                    probe["compatibility_policy"],
                )
                self.assertEqual(1, probe["host_contract_version"])
                self.assertEqual("checked", probe["host_contract_status"])
                self.assertEqual(
                    {platform},
                    {
                        configured_platform
                        for configured_platform, _ in plugin._rooms
                    },
                )
                self.assertGreaterEqual(len(patched_attributes), 60)
                self.assertTrue(
                    any(
                        platform
                        in (
                            f"{getattr(target, '__module__', '')}."
                            f"{getattr(target, '__name__', '')}"
                        ).lower()
                        for target, _ in patched_attributes
                    )
                )
            finally:
                for (target, name), original in reversed(
                    tuple(patched_attributes.items())
                ):
                    setattr(target, name, original)
                hermes_v2._SHIM_OWNER = original_owner
                hermes_v2._ORIGINAL_BASE_HANDLE = original_base_handle


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
