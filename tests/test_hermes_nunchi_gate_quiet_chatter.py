"""Tests for nunchi-gate's shared-channel quieting shim.

The Hermes nunchi plugin owns shared-channel UX defaults: when a channel is
under nunchi, operator-facing progress/steering chatter should be controlled
from the nunchi config surface rather than requiring separate Hermes display
knobs. A single operator key — ``quiet_gateway_chatter`` — governs all four
gateway emitters:

1. the busy-ACK send ("⏩ Steered" / "⏳ Queued" / "⚡ Interrupting"),
2. tool-progress / interim display receipts,
3. the per-turn "• Grant spent" credit notice, and
4. compression / lifecycle status chatter ("📦 Preflight compression" /
   "🗜️ Compacting context").

Final assistant replies, credit WARNINGS (⚠ Credits / ✕/✓ Credit access),
unrelated notices, and unrelated status updates are always delivered, and
nothing is suppressed outside a quiet nunchi channel. These tests stay
stdlib-only and load the plugin module directly. Async targets are exercised
with real coroutine doubles + asyncio.run.
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
            self.assertIs(
                plugin._nunchi_quiet_display_override("discord", "busy_ack_detail", "room-1"),
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

    def test_nunchi_quiet_display_off_when_chatter_visible(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {"quiet_gateway_chatter": False}},
            "quiet_gateway_chatter": True,
        }

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            self.assertIsNone(
                plugin._nunchi_quiet_display_override("discord", "tool_progress", "room-1")
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


class TestBusyAckMonkeyPatch(unittest.TestCase):
    """Emitter 1: the busy-ACK send bubble."""

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

    def test_normal_reply_never_swallowed_in_busy_handler(self):
        """A non-busy-ack send inside the busy handler still delivers in a quiet room.

        The busy handler only drops known busy-ACK strings; a normal final reply
        that happens to flow through the same adapter seam must pass through.
        """
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
                return "delivered"

        class Runner:
            def __init__(self):
                self.adapters = {"discord": Adapter()}

            async def _handle_active_session_busy_message(self, event, session_key):
                # Not a busy-ACK string: a normal reply body.
                await self.adapters[event.source.platform]._send_with_retry(
                    chat_id=event.source.chat_id,
                    content="Here is the answer you asked for.",
                )
                return True

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_busy_ack_handler(Runner)
            result = asyncio.run(Runner()._handle_active_session_busy_message(_event(), "session-1"))

        self.assertTrue(result)
        self.assertEqual(sent, ["Here is the answer you asked for."])

    def test_busy_ack_patch_is_idempotent(self):
        plugin = _load_plugin()

        class Runner:
            async def _handle_active_session_busy_message(self, event, session_key):
                return True

        plugin._patch_busy_ack_handler(Runner)
        first = Runner._handle_active_session_busy_message
        plugin._patch_busy_ack_handler(Runner)
        self.assertIs(Runner._handle_active_session_busy_message, first)


class TestStatusChatterMonkeyPatch(unittest.TestCase):
    """Emitter 4: compression / lifecycle status chatter.

    Emitted via the module-level async ``gateway.run._send_or_update_status_coro``
    — bypasses both the display resolver and the busy-ACK handler.
    """

    def _fake_run_module(self, delivered):
        async def _send_or_update_status_coro(adapter, chat_id, status_key, content, metadata):
            delivered.append(content)
            return "delivered"

        return types.SimpleNamespace(_send_or_update_status_coro=_send_or_update_status_coro)

    def _quiet_cfg(self):
        return {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }

    def test_compression_status_suppressed_in_quiet_room(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        mod = self._fake_run_module(delivered)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_status_sender(mod)
            result = asyncio.run(
                mod._send_or_update_status_coro(
                    adapter, "room-1", "compaction", "📦 Preflight compression before this turn", {}
                )
            )

        self.assertIsNone(result)
        self.assertEqual(delivered, [])

    def test_compacting_status_suppressed_in_quiet_room(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        mod = self._fake_run_module(delivered)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_status_sender(mod)
            result = asyncio.run(
                mod._send_or_update_status_coro(
                    adapter, "room-1", "compaction", "🗜️ Compacting context…", {}
                )
            )

        self.assertIsNone(result)
        self.assertEqual(delivered, [])

    def test_compression_status_delivered_in_non_quiet_room(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {"quiet_gateway_chatter": False}},
            "quiet_gateway_chatter": True,
        }
        delivered: list[str] = []
        mod = self._fake_run_module(delivered)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_status_sender(mod)
            result = asyncio.run(
                mod._send_or_update_status_coro(
                    adapter, "room-1", "compaction", "📦 Preflight compression before this turn", {}
                )
            )

        self.assertEqual(result, "delivered")
        self.assertEqual(delivered, ["📦 Preflight compression before this turn"])

    def test_non_chatter_status_delivered_in_quiet_room(self):
        """A status update that is not compression chatter still delivers (prefix-narrow)."""
        plugin = _load_plugin()
        delivered: list[str] = []
        mod = self._fake_run_module(delivered)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_status_sender(mod)
            result = asyncio.run(
                mod._send_or_update_status_coro(
                    adapter, "room-1", "turn", "✅ Turn complete", {}
                )
            )

        self.assertEqual(result, "delivered")
        self.assertEqual(delivered, ["✅ Turn complete"])

    def test_compression_status_delivered_in_unmatched_channel(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        mod = self._fake_run_module(delivered)
        adapter = types.SimpleNamespace(platform="discord")

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_status_sender(mod)
            result = asyncio.run(
                mod._send_or_update_status_coro(
                    adapter, "other-room", "compaction", "📦 Preflight compression before this turn", {}
                )
            )

        self.assertEqual(result, "delivered")
        self.assertEqual(delivered, ["📦 Preflight compression before this turn"])

    def test_status_patch_is_idempotent(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        mod = self._fake_run_module(delivered)

        plugin._patch_status_sender(mod)
        first = mod._send_or_update_status_coro
        plugin._patch_status_sender(mod)
        self.assertIs(mod._send_or_update_status_coro, first)

    def test_status_patch_noop_on_module_without_target(self):
        plugin = _load_plugin()
        bare = types.SimpleNamespace()  # no _send_or_update_status_coro
        plugin._patch_status_sender(bare)  # must not raise
        self.assertFalse(hasattr(bare, "_send_or_update_status_coro"))


class TestCreditGrantNoticeSuppression(unittest.TestCase):
    """Emitter 3: the per-turn '• Grant spent' credit notice.

    Only the narrow grant-spent notice is dropped, and only in a quiet nunchi
    channel. Credit WARNINGS and unrelated notices always deliver, and nothing
    is suppressed in a non-quiet or unmatched channel.
    """

    def _runner_cls(self, delivered):
        class Runner:
            async def _deliver_platform_notice(self, source, content):
                delivered.append(content)
                return "delivered"

        return Runner

    def _quiet_cfg(self):
        return {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {}},
            "quiet_gateway_chatter": True,
        }

    def test_is_credit_grant_notice_narrowness(self):
        plugin = _load_plugin()
        self.assertTrue(plugin._is_credit_grant_notice("• Grant spent · 3 credits this turn"))
        self.assertTrue(plugin._is_credit_grant_notice("anything", "credits.grant_spent"))
        # Credit warnings and unrelated notices are NOT grant-spent.
        self.assertFalse(plugin._is_credit_grant_notice("⚠ Credits low · top up soon"))
        self.assertFalse(plugin._is_credit_grant_notice("✕ Credit access paused"))
        self.assertFalse(plugin._is_credit_grant_notice("✓ Credit access restored"))
        self.assertFalse(plugin._is_credit_grant_notice("• Session resumed"))
        self.assertFalse(plugin._is_credit_grant_notice(None))

    def test_grant_spent_notice_suppressed_in_quiet_room(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        Runner = self._runner_cls(delivered)

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_notice_handler(Runner)
            result = asyncio.run(
                Runner()._deliver_platform_notice(_source(), "• Grant spent · 3 credits this turn")
            )

        self.assertIsNone(result)
        self.assertEqual(delivered, [])

    def test_credit_warning_delivered_in_quiet_room(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        Runner = self._runner_cls(delivered)

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_notice_handler(Runner)
            result = asyncio.run(
                Runner()._deliver_platform_notice(_source(), "⚠ Credits low · top up soon")
            )

        self.assertEqual(result, "delivered")
        self.assertEqual(delivered, ["⚠ Credits low · top up soon"])

    def test_unrelated_notice_delivered_in_quiet_room(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        Runner = self._runner_cls(delivered)

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_notice_handler(Runner)
            result = asyncio.run(
                Runner()._deliver_platform_notice(_source(), "• Session resumed")
            )

        self.assertEqual(result, "delivered")
        self.assertEqual(delivered, ["• Session resumed"])

    def test_grant_spent_notice_delivered_in_non_quiet_room(self):
        plugin = _load_plugin()
        cfg = {
            "enabled": True,
            "platforms": "discord",
            "channels": {"room-1": {"quiet_gateway_chatter": False}},
            "quiet_gateway_chatter": True,
        }
        delivered: list[str] = []
        Runner = self._runner_cls(delivered)

        with patch.object(plugin, "_nunchi_config", return_value=cfg):
            plugin._patch_notice_handler(Runner)
            result = asyncio.run(
                Runner()._deliver_platform_notice(_source(), "• Grant spent · 3 credits this turn")
            )

        self.assertEqual(result, "delivered")
        self.assertEqual(delivered, ["• Grant spent · 3 credits this turn"])

    def test_grant_spent_notice_delivered_in_unmatched_channel(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        Runner = self._runner_cls(delivered)

        with patch.object(plugin, "_nunchi_config", return_value=self._quiet_cfg()):
            plugin._patch_notice_handler(Runner)
            result = asyncio.run(
                Runner()._deliver_platform_notice(
                    _source(chat_id="other-room"), "• Grant spent · 3 credits this turn"
                )
            )

        self.assertEqual(result, "delivered")
        self.assertEqual(delivered, ["• Grant spent · 3 credits this turn"])

    def test_notice_patch_is_idempotent(self):
        plugin = _load_plugin()
        delivered: list[str] = []
        Runner = self._runner_cls(delivered)

        plugin._patch_notice_handler(Runner)
        first = Runner._deliver_platform_notice
        plugin._patch_notice_handler(Runner)
        self.assertIs(Runner._deliver_platform_notice, first)


class TestFailSafePatchTargets(unittest.TestCase):
    """Missing monkeypatch targets degrade to a no-op; nothing raises."""

    def test_patchers_noop_on_runner_without_targets(self):
        plugin = _load_plugin()

        class BareRunner:
            pass

        # None of these targets exist on BareRunner — must not raise.
        plugin._patch_busy_ack_handler(BareRunner)
        plugin._patch_notice_handler(BareRunner)
        self.assertFalse(hasattr(BareRunner, "_handle_active_session_busy_message"))
        self.assertFalse(hasattr(BareRunner, "_deliver_platform_notice"))

    def test_display_resolver_patch_noop_without_module(self):
        plugin = _load_plugin()
        # No display_config module object -> import fails -> no-op, no raise.
        self.assertFalse(plugin._patch_display_resolver(display_config_module=None))


class TestRegisterVisibility(unittest.TestCase):
    """The monkeypatch must be portable but NOT invisible: register() emits one
    INFO summary naming every emitter, its exact patched Hermes symbol, and the
    suppression boundary — so an operator can see and grep what was altered."""

    _EMITTERS = ("busy_ack", "tool_progress", "status_chatter", "grant_spent_notice")
    _TARGETS = (
        "gateway.display_config.resolve_display_setting",
        "gateway.run._send_or_update_status_coro",
        "GatewayRunner._handle_active_session_busy_message",
        "GatewayRunner._deliver_platform_notice",
    )

    def test_install_summary_names_every_emitter_and_exact_target(self):
        plugin = _load_plugin()
        with self.assertLogs(plugin.logger, level="INFO") as cm:
            results = plugin._install_quiet_room_patches()
        blob = "\n".join(cm.output)

        # One clear summary line.
        self.assertIn("installed emission suppression", blob)
        self.assertIn("quiet_gateway_chatter", blob)
        # Every emitter named, each tagged with its greppable Hermes symbol.
        for emitter in self._EMITTERS:
            self.assertIn(emitter, blob)
        for target in self._TARGETS:
            self.assertIn(target, blob)
        # The boundary is stated explicitly: lifecycle notices + credit
        # warnings are preserved.
        self.assertIn("never suppressed", blob)
        self.assertIn("LIFECYCLE", blob)
        self.assertIn("WARNINGS", blob)
        # Results report install state for all four emitters (bools).
        self.assertEqual(set(results), set(self._EMITTERS))
        for v in results.values():
            self.assertIsInstance(v, bool)

    def test_install_summary_reports_inert_targets_when_missing(self):
        """Offline (no gateway.* modules) every target is missing → the summary
        must flag them INERT so the operator knows those emitters stay visible."""
        plugin = _load_plugin()
        with self.assertLogs(plugin.logger, level="INFO") as cm:
            results = plugin._install_quiet_room_patches()
        blob = "\n".join(cm.output)
        self.assertIn("INERT", blob)
        self.assertIn("stays VISIBLE", blob)
        self.assertTrue(all(v is False for v in results.values()), results)

    def test_register_emits_the_install_summary(self):
        plugin = _load_plugin()

        class FakeCtx:
            def register_hook(self, name, fn):
                pass

            def register_command(self, *a, **k):
                pass

        with self.assertLogs(plugin.logger, level="INFO") as cm:
            plugin.register(FakeCtx())
        blob = "\n".join(cm.output)
        self.assertIn("installed emission suppression", blob)


if __name__ == "__main__":
    unittest.main()
