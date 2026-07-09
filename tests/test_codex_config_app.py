"""Offline backend and bundle tests for the Codex MCP Apps config panel."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

from nunchi.integrations.codex_config_app import (
    TEMPLATE_URI,
    ConfigAppService,
    build_mcp_server,
    default_config_argv,
    load_ui_html,
)
from nunchi.integrations.codex_room_runner import RunnerConfig, save_codex_session
from tests.hook_sandbox import sandbox_env


def _service(root: pathlib.Path) -> ConfigAppService:
    return ConfigAppService(
        environ={},
        config=RunnerConfig(
            channels=frozenset({"1522258711047831653"}),
            channel_bin="/bin/sh",
            codex_bin="/bin/sh",
            state_path=root / "state.json",
            log_path=root / "receipts.jsonl",
            session_path=root / "session.json",
            agent_id="vigil",
            mention_id="1494822530643398827",
        ),
    )


class TestConfigAppService(unittest.TestCase):
    def test_default_config_argv_discovers_conventional_runner_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.assertEqual(default_config_argv({"HOME": td}), [])
            config = root / ".nunchi" / "codex-runner.toml"
            config.parent.mkdir()
            config.write_text("[runner]\nchannels = [\"123\"]\n", encoding="utf-8")

            self.assertEqual(
                default_config_argv({"HOME": td}),
                ["--config", str(config)],
            )
            self.assertEqual(
                default_config_argv(
                    {"HOME": td, "NUNCHI_RUNNER_CONFIG": "/operator/explicit.toml"}
                ),
                [],
            )

    def test_snapshot_exposes_runtime_controls_without_operator_identity(self):
        with tempfile.TemporaryDirectory() as td:
            snapshot = _service(pathlib.Path(td)).snapshot()

        self.assertEqual(snapshot["api_version"], 1)
        self.assertIn("1522258711047831653", snapshot["effective"])
        self.assertEqual(snapshot["baseline"]["senders"], "all")
        self.assertNotIn("agent_id", snapshot["baseline"])
        self.assertNotIn("mention_id", snapshot["baseline"])
        self.assertNotIn("state_path", snapshot)
        self.assertNotIn("log_path", snapshot)

    def test_update_is_immediately_visible_in_effective_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            service = _service(pathlib.Path(td))
            result = service.update(
                {
                    "global": {"senders": "humans", "verbosity": "debug"},
                    "channels": {
                        "1522258711047831653": {
                            "model": "deepseek/deepseek-v4-flash",
                            "pinned_rules": "Wait for a useful opening.",
                        }
                    },
                }
            )

        self.assertTrue(result["ok"])
        effective = result["snapshot"]["effective"]["1522258711047831653"]
        self.assertEqual(effective["senders"], "humans")
        self.assertEqual(effective["verbosity"], "debug")
        self.assertEqual(effective["model"], "deepseek/deepseek-v4-flash")
        self.assertEqual(effective["pinned_rules"], "Wait for a useful opening.")

    def test_rejected_patch_is_all_or_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            service = _service(root)
            result = service.update(
                {"global": {"senders": "humans", "agent_id": "attacker"}}
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["rejected_keys"], ["global.agent_id"])
            self.assertFalse((root / "state.json").exists())

    def test_receipts_are_newest_first(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            path = root / "receipts.jsonl"
            path.write_text(
                json.dumps({"message_id": "old"})
                + "\n"
                + json.dumps({"message_id": "new"})
                + "\n",
                encoding="utf-8",
            )
            result = _service(root).receipts(limit=10)

        self.assertEqual(
            [receipt["message_id"] for receipt in result["receipts"]],
            ["new", "old"],
        )

    def test_snapshot_and_reset_expose_persistent_session_health(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            service = _service(root)
            self.assertFalse(service.snapshot()["health"]["codex_session"]["active"])
            save_codex_session(
                root / "session.json",
                "019f4914-a9c7-7090-bec3-0e78fa9b84e1",
            )

            health = service.snapshot()["health"]["codex_session"]
            self.assertTrue(health["active"])
            self.assertIsNotNone(health["updated_at"])
            self.assertNotIn("thread_id", health)
            result = service.reset_session()

        self.assertTrue(result["ok"])
        self.assertFalse(result["snapshot"]["health"]["codex_session"]["active"])

    def test_corrupt_session_is_reported_and_can_be_reset(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            service = _service(root)
            (root / "session.json").write_text("bad-json", encoding="utf-8")

            health = service.snapshot()["health"]["codex_session"]
            self.assertFalse(health["active"])
            self.assertIn("cannot read Codex session state", health["error"])
            service.reset_session()

            self.assertIsNone(service.snapshot()["health"]["codex_session"]["error"])


class TestConfigUiAsset(unittest.TestCase):
    def test_ui_contains_settings_receipts_and_host_tool_calls(self):
        html = load_ui_html()
        for fragment in (
            "Global overrides",
            "Add channel",
            "Receipt detail",
            "Room governance",
            "Confirm reset",
            "Global senders",
            "document.createElement",
            "textContent",
            "pending add",
            "get_nunchi_config",
            "update_nunchi_config",
            "reset_nunchi_session",
            "get_nunchi_receipts",
            'method: "tools/call"',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("window.confirm", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "mcp extra not installed")
class TestMcpAppsContract(unittest.TestCase):
    def test_tools_and_ui_resource_publish_mcp_apps_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            server = build_mcp_server(_service(pathlib.Path(td)))

            async def inspect_server():
                tools = {tool.name: tool for tool in await server.list_tools()}
                resources = await server.list_resources()
                content = list(await server.read_resource(TEMPLATE_URI))
                return tools, resources, content

            tools, resources, content = asyncio.run(inspect_server())

        self.assertEqual(
            set(tools),
            {
                "open_nunchi_config",
                "get_nunchi_config",
                "update_nunchi_config",
                "reset_nunchi_session",
                "get_nunchi_receipts",
            },
        )
        open_meta = tools["open_nunchi_config"].meta
        self.assertEqual(open_meta["ui"]["resourceUri"], TEMPLATE_URI)
        self.assertEqual(open_meta["openai/outputTemplate"], TEMPLATE_URI)
        self.assertTrue(tools["open_nunchi_config"].annotations.readOnlyHint)
        self.assertFalse(tools["update_nunchi_config"].annotations.readOnlyHint)
        self.assertTrue(tools["reset_nunchi_session"].annotations.destructiveHint)
        self.assertEqual(str(resources[0].uri), TEMPLATE_URI)
        self.assertEqual(content[0].mime_type, "text/html;profile=mcp-app")
        self.assertIn("Nunchi", content[0].content)

    def test_stdio_server_round_trip(self):
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            env = sandbox_env(
                {
                    "NUNCHI_RUNNER_STATE": str(root / "state.json"),
                    "NUNCHI_RUNNER_LOG": str(root / "receipts.jsonl"),
                    "NUNCHI_RUNNER_SESSION_STATE": str(root / "session.json"),
                    "NUNCHI_CHANNEL_BIN": "/bin/sh",
                    "NUNCHI_RUNNER_CODEX_BIN": "/bin/sh",
                    "NUNCHI_RUNNER_CHANNELS": "1522258711047831653",
                }
            )

            async def round_trip():
                params = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "nunchi.integrations.codex_config_app"],
                    env=env,
                )
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        opened = await session.call_tool("open_nunchi_config", {})
                        updated = await session.call_tool(
                            "update_nunchi_config",
                            {
                                "patch": {
                                    "channels": {
                                        "1522258711047831653": {"senders": "humans"}
                                    }
                                }
                            },
                        )
                        resource = await session.read_resource(TEMPLATE_URI)
                        return tools, opened, updated, resource

            tools, opened, updated, resource = asyncio.run(round_trip())

        self.assertEqual(len(tools.tools), 5)
        self.assertEqual(opened.structuredContent["api_version"], 1)
        self.assertTrue(updated.structuredContent["ok"])
        effective = updated.structuredContent["snapshot"]["effective"]
        self.assertEqual(effective["1522258711047831653"]["senders"], "humans")
        self.assertEqual(resource.contents[0].mimeType, "text/html;profile=mcp-app")


if __name__ == "__main__":
    unittest.main()
