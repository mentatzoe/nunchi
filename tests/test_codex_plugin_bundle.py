"""Codex plugin bundle contract tests."""

from __future__ import annotations

import json
import pathlib
import tomllib
import unittest


_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PLUGIN_ROOT = _ROOT / "integrations" / "codex" / "nunchi-codex"
_MARKETPLACE = _ROOT / ".agents" / "plugins" / "marketplace.json"
_SMOKE_SCRIPT = _ROOT / "integrations" / "codex" / "run_vigil_smoke.sh"


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestCodexPluginBundle(unittest.TestCase):
    def test_manifest_is_installable_repo_plugin(self):
        manifest_path = _PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)

        self.assertEqual(manifest["name"], _PLUGIN_ROOT.name)
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertNotIn("hooks", manifest)
        self.assertNotIn("[TODO", manifest_text)

        interface = manifest["interface"]
        for key in (
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
            "category",
            "capabilities",
        ):
            with self.subTest(key=key):
                self.assertTrue(interface[key])

    def test_hooks_are_bundled_and_use_installed_scripts(self):
        pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = set(pyproject["project"]["scripts"])

        hooks_path = _PLUGIN_ROOT / "hooks" / "hooks.json"
        hooks_text = hooks_path.read_text(encoding="utf-8")
        hooks = json.loads(hooks_text)["hooks"]

        expected = {
            "UserPromptSubmit": "nunchi-codex-prompt-gate",
            "PreToolUse": "nunchi-codex-send-gate",
        }
        for event, command in expected.items():
            with self.subTest(event=event):
                groups = hooks[event]
                self.assertEqual(len(groups), 1)
                handlers = groups[0]["hooks"]
                self.assertEqual(len(handlers), 1)
                self.assertEqual(handlers[0]["type"], "command")
                self.assertEqual(handlers[0]["command"], command)
                self.assertIn(command, scripts)

        forbidden_fragments = ("/Volumes/", "/Users/", ".py", "python")
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, hooks_text)

    def test_bundled_mcp_points_to_local_nunchi_transport(self):
        mcp = _read_json(_PLUGIN_ROOT / ".mcp.json")
        servers = mcp["mcpServers"]
        server = servers["nunchi-discord"]

        self.assertEqual(server["url"], "http://127.0.0.1:3993/mcp")
        self.assertIs(server["enabled"], True)
        self.assertIs(server["required"], False)
        self.assertEqual(server["default_tools_approval_mode"], "prompt")
        self.assertEqual(
            server["enabled_tools"],
            ["read_history", "send_message", "reply_message"],
        )

        config_server = servers["nunchi-config"]
        self.assertEqual(config_server["command"], "nunchi-codex-config-app")
        self.assertIs(config_server["enabled"], True)
        self.assertIs(config_server["required"], False)
        self.assertEqual(config_server["default_tools_approval_mode"], "prompt")
        self.assertEqual(
            config_server["enabled_tools"],
            [
                "open_nunchi_config",
                "get_nunchi_config",
                "update_nunchi_config",
                "get_nunchi_receipts",
            ],
        )

    def test_repo_marketplace_exposes_plugin(self):
        marketplace = _read_json(_MARKETPLACE)
        entries = {plugin["name"]: plugin for plugin in marketplace["plugins"]}
        entry = entries["nunchi-codex"]

        self.assertEqual(marketplace["name"], "local-repo")
        self.assertEqual(entry["source"], {
            "source": "local",
            "path": "./integrations/codex/nunchi-codex",
        })
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")
        self.assertEqual(entry["category"], "Developer Tools")


class TestVigilSmokeScript(unittest.TestCase):
    def test_script_encodes_reproducible_live_smoke_setup(self):
        text = _SMOKE_SCRIPT.read_text(encoding="utf-8")

        required_fragments = (
            "[discord,mcp-discord]",
            "NUNCHI_DISCORD_TOKEN",
            "NUNCHI_CLASSIFIER_MODEL",
            "OPENROUTER_API_KEY",
            "1522258711047831653",
            "1494822530643398827",
            "nunchi-codex@local-repo",
            "NUNCHI_RUNNER_CODEX_ARGS",
            "--dangerously-bypass-hook-trust",
            "PATH=\"$VENV/bin:$PATH\"",
            "summarize_vigil_smoke.py",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)

        self.assertNotIn("set -x", text)
        self.assertIn("export NUNCHI_RUNNER_LOG=", text)


if __name__ == "__main__":
    unittest.main()
