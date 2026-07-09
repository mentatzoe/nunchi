"""Tests for nunchi-gate's shared-channel quieting shim.

The Hermes nunchi plugin owns shared-channel UX defaults: when a channel is
under nunchi, operator-facing progress/steering chatter should be controlled
from the nunchi config surface rather than requiring separate Hermes display
knobs. These tests stay stdlib-only and load the plugin module directly.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import tempfile
import types
import unittest
from unittest.mock import patch

_PLUGIN_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "integrations"
    / "hermes"
    / "nunchi-gate"
    / "__init__.py"
)


def _load_plugin():
    spec = importlib.util.spec_from_file_location("nunchi_gate_under_test", _PLUGIN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _source(*, chat_id: str = "room-1", platform: str = "discord"):
    return types.SimpleNamespace(
        platform=platform,
        chat_id=chat_id,
        parent_chat_id=None,
        thread_id=None,
        user_id="human-1",
        user_name="Zoe",
        is_bot=False,
    )


def _event(*, chat_id: str = "room-1", platform: str = "discord"):
    return types.SimpleNamespace(
        text="follow-up while the agent is busy",
        source=_source(chat_id=chat_id, platform=platform),
        message_id="msg-1",
    )


class TestQuietSharedChannelConfig(unittest.TestCase):
    def test_channel_map_can_override_quiet_gateway_chatter(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "quiet_gateway_chatter": True,
            "channels": {
                "room-1": {"quiet_gateway_chatter": False},
            },
        }

        resolved = plugin.resolve_channel_config(cfg, {"room-1"})

        self.assertIsNotNone(resolved)
        self.assertIs(resolved["quiet_gateway_chatter"], False)

    def test_nunchi_quiet_display_defaults_for_matching_channel(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            self.assertEqual(
                plugin._nunchi_quiet_display_override("discord", "tool_progress", "room-1"),
                "off",
            )
            self.assertIs(
                plugin._nunchi_quiet_display_override("discord", "interim_assistant_messages", "room-1"),
                False,
            )
            self.assertIs(
                plugin._nunchi_quiet_display_override("discord", "long_running_notifications", "room-1"),
                False,
            )

    def test_nunchi_quiet_display_does_not_apply_outside_matching_channel(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            self.assertIsNone(
                plugin._nunchi_quiet_display_override("discord", "tool_progress", "other-room")
            )


class TestNunchiChatterCommand(unittest.TestCase):
    def test_status_surfaces_quiet_gateway_chatter_setting(self):
        plugin = _load_plugin()
        with tempfile.TemporaryDirectory() as td:
            cfg = {
                "enabled": True,
                "platforms": "discord",
                "channels": {"room-1": {}},
                "quiet_gateway_chatter": True,
                "state_path": str(pathlib.Path(td) / "state.json"),
            }
            with patch.object(plugin, "_nunchi_config", return_value=cfg):
                status = plugin._nunchi_command("status")

        self.assertIn("quiet_gateway_chatter", status)
        self.assertIn("True", status)

    def test_chatter_visible_writes_single_nunchi_override(self):
        plugin = _load_plugin()
        with tempfile.TemporaryDirectory() as td:
            state_path = pathlib.Path(td) / "state.json"
            cfg = {
                "enabled": True,
                "platforms": "discord",
                "channels": {"room-1": {}},
                "quiet_gateway_chatter": True,
                "state_path": str(state_path),
            }
            with patch.object(plugin, "_nunchi_config", return_value=cfg):
                result = plugin._nunchi_command("chatter visible room-1")
                status = plugin._nunchi_command("status")

        self.assertEqual(result, "nunchi: gateway chatter set to 'visible' (channel room-1)")
        self.assertIn("quiet_gateway_chatter  False  [channel-override]", status)

    def test_chatter_quiet_global_writes_global_override(self):
        plugin = _load_plugin()
        with tempfile.TemporaryDirectory() as td:
            cfg = {
                "enabled": True,
                "platforms": "discord",
                "channels": {"room-1": {}},
                "quiet_gateway_chatter": False,
                "state_path": str(pathlib.Path(td) / "state.json"),
            }
            with patch.object(plugin, "_nunchi_config", return_value=cfg):
                result = plugin._nunchi_command("chatter quiet global")
                status = plugin._nunchi_command("status")

        self.assertEqual(result, "nunchi: gateway chatter set to 'quiet' (global override)")
        self.assertIn("quiet_gateway_chatter  True  [global-override]", status)


class TestStatusMonkeyPatch(unittest.TestCase):
    def test_compaction_status_is_suppressed_for_nunchi_channel(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }
        sent: list[str] = []

        async def original(adapter, chat_id, status_key, content, metadata):
            sent.append(content)
            return types.SimpleNamespace(success=True, message_id="status-1")

        module = types.SimpleNamespace(_send_or_update_status_coro=original)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_status_sender(module)
            result = asyncio.run(
                module._send_or_update_status_coro(
                    adapter,
                    "room-1",
                    "lifecycle",
                    "📦 Preflight compression: ~253,603 tokens >= 231,200 threshold. This may take a moment.",
                    None,
                )
            )

        self.assertIsNone(result)
        self.assertEqual(sent, [])

    def test_status_patch_does_not_suppress_non_matching_channel(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }
        sent: list[str] = []

        async def original(adapter, chat_id, status_key, content, metadata):
            sent.append(content)
            return types.SimpleNamespace(success=True, message_id="status-1")

        module = types.SimpleNamespace(_send_or_update_status_coro=original)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_status_sender(module)
            result = asyncio.run(
                module._send_or_update_status_coro(
                    adapter,
                    "other-room",
                    "lifecycle",
                    "🗜️ Compacting context — summarizing earlier conversation so I can continue...",
                    None,
                )
            )

        self.assertTrue(result.success)
        self.assertEqual(sent, ["🗜️ Compacting context — summarizing earlier conversation so I can continue..."])

    def test_status_patch_does_not_suppress_non_chatter_status(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }
        sent: list[str] = []

        async def original(adapter, chat_id, status_key, content, metadata):
            sent.append(content)
            return types.SimpleNamespace(success=True, message_id="status-1")

        module = types.SimpleNamespace(_send_or_update_status_coro=original)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_status_sender(module)
            result = asyncio.run(
                module._send_or_update_status_coro(
                    adapter,
                    "room-1",
                    "credits",
                    "• Grant spent · $15.44 top-up left",
                    None,
                )
            )

        self.assertTrue(result.success)
        self.assertEqual(sent, ["• Grant spent · $15.44 top-up left"])


class TestBusyAckMonkeyPatch(unittest.TestCase):
    def test_busy_ack_messages_are_suppressed_for_nunchi_channel(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }
        sent: list[str] = []

        class Adapter:
            async def _send_with_retry(self, **kwargs):
                sent.append(kwargs["content"])

        class Runner:
            def __init__(self):
                self.adapters = {"discord": Adapter()}

            async def _handle_active_session_busy_message(self, event, session_key):
                await self.adapters[event.source.platform]._send_with_retry(
                    chat_id=event.source.chat_id,
                    content="⏩ Steered into current run. Your message arrives after the next tool call.",
                )
                return True

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_busy_ack_handler(Runner)
            result = asyncio.run(Runner()._handle_active_session_busy_message(_event(), "session-1"))

        self.assertTrue(result)
        self.assertEqual(sent, [])

    def test_busy_ack_patch_does_not_suppress_non_matching_channel(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }
        sent: list[str] = []

        class Adapter:
            async def _send_with_retry(self, **kwargs):
                sent.append(kwargs["content"])

        class Runner:
            def __init__(self):
                self.adapters = {"discord": Adapter()}

            async def _handle_active_session_busy_message(self, event, session_key):
                await self.adapters[event.source.platform]._send_with_retry(
                    chat_id=event.source.chat_id,
                    content="⏩ Steered into current run. Your message arrives after the next tool call.",
                )
                return True

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_busy_ack_handler(Runner)
            result = asyncio.run(
                Runner()._handle_active_session_busy_message(_event(chat_id="other-room"), "session-1")
            )

        self.assertTrue(result)
        self.assertEqual(sent, ["⏩ Steered into current run. Your message arrives after the next tool call."])


if __name__ == "__main__":
    unittest.main()
