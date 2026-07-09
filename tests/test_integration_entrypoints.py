"""Stable installed entry points for hook and runner integrations."""

from __future__ import annotations

import importlib
import pathlib
import tomllib
import unittest


_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestPackageModules(unittest.TestCase):
    def test_hook_and_runner_modules_are_importable_from_package(self):
        modules = [
            "nunchi.integrations.codex_prompt_gate",
            "nunchi.integrations.codex_send_gate",
            "nunchi.integrations.codex_room_runner",
            "nunchi.integrations.codex_config_app",
        ]
        for name in modules:
            with self.subTest(name=name):
                mod = importlib.import_module(name)
                self.assertTrue(callable(getattr(mod, "main", None)))


class TestConsoleScripts(unittest.TestCase):
    def test_pyproject_exposes_stable_integration_scripts(self):
        data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]
        self.assertEqual(
            scripts["nunchi-codex-prompt-gate"],
            "nunchi.integrations.codex_prompt_gate:main",
        )
        self.assertEqual(
            scripts["nunchi-codex-send-gate"],
            "nunchi.integrations.codex_send_gate:main",
        )
        self.assertEqual(
            scripts["nunchi-codex-room-runner"],
            "nunchi.integrations.codex_room_runner:main",
        )
        self.assertEqual(
            scripts["nunchi-codex-config-app"],
            "nunchi.integrations.codex_config_app:main",
        )


if __name__ == "__main__":
    unittest.main()
