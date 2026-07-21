from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from nunchi.authorization import canonical_action_digest
from nunchi.policy import load_operator_policy
from tests.v2.security.helpers import clone_policy, write_policy


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "integrations" / "hermes" / "nunchi-gate" / "v2_runtime.py"
SPEC = importlib.util.spec_from_file_location("nunchi_hermes_v2_runtime", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
v2 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v2
SPEC.loader.exec_module(v2)

PLUGIN_PATH = ROOT / "integrations" / "hermes" / "nunchi-gate" / "v2_plugin.py"
PLUGIN_SPEC = importlib.util.spec_from_file_location("nunchi_hermes_v2_plugin", PLUGIN_PATH)
assert PLUGIN_SPEC is not None and PLUGIN_SPEC.loader is not None
v2_plugin = importlib.util.module_from_spec(PLUGIN_SPEC)
sys.modules[PLUGIN_SPEC.name] = v2_plugin
PLUGIN_SPEC.loader.exec_module(v2_plugin)


def _load_fresh_plugin_module(name: str):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Platform:
    def __init__(self, value: str) -> None:
        self.value = value


class _Gateway:
    def __init__(self, adapter: object) -> None:
        self.adapter = adapter

    def _adapter_for_source(self, source: object) -> object:
        return self.adapter


class HermesV2IdentityTest(unittest.TestCase):
    def discord_event(self, *, profile: str = "default", message_id: str = "123"):
        source = SimpleNamespace(
            profile=profile,
            platform=_Platform("discord"),
            chat_id="42",
            thread_id="77",
            user_id="1001",
            user_name="Vigil",
            is_bot=False,
        )
        raw = SimpleNamespace(
            id=int(message_id),
            author=SimpleNamespace(id=1001, display_name="Vigil", bot=False),
            mentions=[SimpleNamespace(id=9001)],
            reference=SimpleNamespace(message_id=122),
            created_at=SimpleNamespace(isoformat=lambda: "2026-07-20T18:00:00+00:00"),
        )
        return SimpleNamespace(
            source=source,
            message_id=message_id,
            text="hello <@9001>",
            raw_message=raw,
            internal=False,
        )

    def test_discord_binding_uses_profile_native_self_and_room_scope(self):
        event = self.discord_event(profile="writer")
        adapter = SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        key = v2.resolve_binding_key(event, _Gateway(adapter))
        self.assertEqual(key.profile_name, "writer")
        self.assertEqual(key.platform, "discord")
        self.assertEqual(key.self_actor_id, "discord:user:9001")
        self.assertEqual(key.room_scope_id, "discord:thread:42:77")
        self.assertNotEqual(key.self_actor_id, "discord:user:1001")

    def test_telegram_binding_uses_authenticated_bot_not_sender(self):
        source = SimpleNamespace(
            profile="default",
            platform=_Platform("telegram"),
            chat_id="-10042",
            thread_id="9",
            user_id="1001",
            user_name="same-name",
            is_bot=False,
        )
        event = SimpleNamespace(source=source, message_id="12", text="hi", internal=False)
        adapter = SimpleNamespace(_bot=SimpleNamespace(id=9001))
        key = v2.resolve_binding_key(event, _Gateway(adapter))
        self.assertEqual(key.self_actor_id, "telegram:user:9001")
        self.assertEqual(key.room_scope_id, "telegram:chat:-10042:topic:9")

    def test_telegram_projection_preserves_ptb_entity_reply_and_timestamp(self):
        source = SimpleNamespace(
            profile="profile-t",
            platform=_Platform("telegram"),
            chat_id="-10042",
            thread_id="7",
        )
        raw = SimpleNamespace(
            message_id=77,
            from_user=SimpleNamespace(id=1001, is_bot=False),
            chat=SimpleNamespace(id=-10042),
            text="Zoe, thoughts?",
            caption=None,
            entities=[
                SimpleNamespace(
                    type="text_mention",
                    offset=0,
                    length=3,
                    user=SimpleNamespace(id=2002, is_bot=False),
                    url=None,
                    language=None,
                    custom_emoji_id=None,
                )
            ],
            reply_to_message=SimpleNamespace(message_id=76),
            date=datetime(2026, 7, 20, 19, 0, tzinfo=timezone.utc),
        )
        event = SimpleNamespace(
            source=source,
            raw_message=raw,
            message_id="77",
            platform_update_id=900,
            reply_to_message_id="76",
            timestamp=raw.date,
            text=raw.text,
            internal=False,
        )
        adapter = SimpleNamespace(_bot=SimpleNamespace(id=9002))
        native = v2.project_native_event(
            event, v2.resolve_binding_key(event, _Gateway(adapter))
        )
        self.assertEqual(native["disposition"], "candidate-event")
        self.assertEqual(
            native["event"]["mentioned_actor_ids"], ["telegram:user:2002"]
        )
        self.assertEqual(
            native["event"]["reply_to_event_id"],
            "telegram:message:-10042:76",
        )
        self.assertEqual(native["event"]["timestamp"], "2026-07-20T19:00:00Z")

    def test_display_name_collision_does_not_create_self_authorship(self):
        event = self.discord_event()
        adapter = SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        key = v2.resolve_binding_key(event, _Gateway(adapter))
        native = v2.project_native_event(event, key)
        self.assertEqual(native["event"]["author_id"], "discord:user:1001")
        self.assertEqual(native["actors"]["discord:user:1001"]["display_name"], "Vigil")
        self.assertNotEqual(native["event"]["author_id"], key.self_actor_id)

    def test_discord_projection_preserves_native_mentions_reply_and_timestamp(self):
        event = self.discord_event(message_id="123")
        adapter = SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        native = v2.project_native_event(event, v2.resolve_binding_key(event, _Gateway(adapter)))
        self.assertEqual(native["delivery_id"], "discord:message:123")
        self.assertEqual(native["event"]["mentioned_actor_ids"], ["discord:user:9001"])
        self.assertEqual(native["event"]["reply_to_event_id"], "discord:message:122")
        self.assertEqual(native["event"]["timestamp"], "2026-07-20T18:00:00+00:00")
        self.assertTrue(native["authorized"])

    def test_discord_projection_recovers_literal_mention_without_resolved_mentions(self):
        event = self.discord_event(message_id="124")
        event.raw_message.mentions = []
        event.text = "hello <@!9001>"
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        native = v2.project_native_event(
            event, v2.resolve_binding_key(event, _Gateway(adapter))
        )
        self.assertEqual(
            native["event"]["mentioned_actor_ids"], ["discord:user:9001"]
        )

    def test_telegram_projection_prefers_hermes_aggregated_text(self):
        source = SimpleNamespace(
            profile="default", platform=_Platform("telegram"),
            chat_id="-10042", thread_id=None,
        )
        raw = SimpleNamespace(
            message_id=78,
            from_user=SimpleNamespace(id=1001, is_bot=False),
            chat=SimpleNamespace(id=-10042),
            text="part one",
            caption=None,
            entities=[],
            reply_to_message=None,
            date=datetime(2026, 7, 20, 19, 0, tzinfo=timezone.utc),
        )
        event = SimpleNamespace(
            source=source,
            raw_message=raw,
            message_id="78",
            platform_update_id=901,
            text="part one\npart two",
            internal=False,
        )
        adapter = SimpleNamespace(_bot=SimpleNamespace(id=9002))
        native = v2.project_native_event(
            event, v2.resolve_binding_key(event, _Gateway(adapter))
        )
        self.assertEqual(native["event"]["text"], "part one\npart two")

    def test_discord_projection_rejects_coerced_native_facts(self):
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        cases = (
            (
                "float-message-id",
                lambda event: setattr(event.raw_message, "id", 123.5),
                "Discord message is unavailable",
            ),
            (
                "float-author-id",
                lambda event: setattr(event.raw_message.author, "id", 1001.5),
                "Discord author is unavailable",
            ),
            (
                "string-bot-flag",
                lambda event: setattr(event.raw_message.author, "bot", "false"),
                "Discord author bot flag must be a boolean",
            ),
            (
                "string-room-mention-flag",
                lambda event: setattr(event.raw_message, "mention_everyone", "false"),
                "Discord room mention flag must be a boolean",
            ),
            (
                "string-internal-flag",
                lambda event: setattr(event, "internal", "false"),
                "Hermes internal flag must be a boolean",
            ),
        )
        for name, mutate, message in cases:
            with self.subTest(name=name):
                event = self.discord_event()
                mutate(event)
                key = v2.resolve_binding_key(event, _Gateway(adapter))
                with self.assertRaisesRegex(v2.HermesV2BoundaryError, message):
                    v2.project_native_event(event, key)

    def test_telegram_projection_rejects_coerced_native_facts(self):
        adapter = SimpleNamespace(_bot=SimpleNamespace(id=9002))

        def telegram_event():
            source = SimpleNamespace(
                profile="profile-t",
                platform=_Platform("telegram"),
                chat_id="-10042",
                thread_id="7",
            )
            raw = SimpleNamespace(
                message_id=77,
                from_user=SimpleNamespace(id=1001, is_bot=False),
                chat=SimpleNamespace(id=-10042),
                text="Zoe, thoughts?",
                caption=None,
                entities=[
                    SimpleNamespace(
                        type="text_mention",
                        offset=0,
                        length=3,
                        user=SimpleNamespace(id=2002, is_bot=False),
                        url=None,
                        language=None,
                        custom_emoji_id=None,
                    )
                ],
                reply_to_message=SimpleNamespace(message_id=76),
                date=datetime(2026, 7, 20, 19, 0, tzinfo=timezone.utc),
            )
            return SimpleNamespace(
                source=source,
                raw_message=raw,
                message_id="77",
                platform_update_id=900,
                text=raw.text,
                internal=False,
            )

        cases = (
            (
                "float-message-id",
                lambda event: setattr(event.raw_message, "message_id", 77.5),
                "Telegram message is unavailable",
            ),
            (
                "float-author-id",
                lambda event: setattr(event.raw_message.from_user, "id", 1001.5),
                "Telegram author is unavailable",
            ),
            (
                "string-author-bot-flag",
                lambda event: setattr(event.raw_message.from_user, "is_bot", "false"),
                "Telegram author bot flag must be a boolean",
            ),
            (
                "string-entity-bot-flag",
                lambda event: setattr(
                    event.raw_message.entities[0].user, "is_bot", "false"
                ),
                "Telegram entity user bot flag must be a boolean",
            ),
            (
                "string-internal-flag",
                lambda event: setattr(event, "internal", "false"),
                "Hermes internal flag must be a boolean",
            ),
        )
        for name, mutate, message in cases:
            with self.subTest(name=name):
                event = telegram_event()
                mutate(event)
                key = v2.resolve_binding_key(event, _Gateway(adapter))
                with self.assertRaisesRegex(v2.HermesV2BoundaryError, message):
                    v2.project_native_event(event, key)


class HermesV2SchedulingTest(unittest.TestCase):
    def key(self, profile: str = "default"):
        return v2.BindingKey(profile, "discord", f"discord:user:{profile}-self", "discord:channel:42")

    @staticmethod
    def native(event_id: str, author: str = "discord:user:1001"):
        return {
            "delivery_id": f"delivery:{event_id}",
            "disposition": "candidate-event",
            "authorized": True,
            "event": {
                "id": event_id,
                "type": "message",
                "author_id": author,
                "text": event_id,
                "mentioned_actor_ids": [],
                "mentions_room": False,
            },
            "actors": {author: {"kind": "human"}},
        }

    def test_registry_isolates_same_room_between_profiles(self):
        registry = v2.BindingRegistry(participant_id="resident")
        first = registry.get_or_create(self.key("default"))
        second = registry.get_or_create(self.key("writer"))
        self.assertIsNot(first, second)
        self.assertIsNot(first.observation, second.observation)
        self.assertIsNot(first.scheduler, second.scheduler)
        self.assertEqual(len(registry.keys()), 2)

    def test_registry_evicts_idle_binding_and_never_active_binding(self):
        registry = v2.BindingRegistry(participant_id="resident", max_bindings=1)
        first = registry.get_or_create(self.key("first"))
        second = registry.get_or_create(self.key("second"))
        self.assertIsNot(first, second)
        self.assertEqual(registry.keys(), (self.key("second"),))
        second.accept(self.native("discord:message:active"))
        with self.assertRaisesRegex(
            v2.HermesV2BoundaryError, "full of active conversations"
        ):
            registry.get_or_create(self.key("third"))

    def test_busy_burst_keeps_one_active_and_only_newest_pending_anchor(self):
        binding = v2.BindingRegistry(participant_id="resident").get_or_create(self.key())
        first = binding.accept(self.native("discord:message:1"))
        self.assertIsNotNone(first.opportunity)
        self.assertIsNone(binding.accept(self.native("discord:message:2")).opportunity)
        self.assertIsNone(binding.accept(self.native("discord:message:3")).opportunity)
        rows = binding.scheduler.snapshot()
        self.assertEqual(rows[0]["active_anchor_event_id"], "discord:message:1")
        self.assertEqual(rows[0]["pending_anchor_event_id"], "discord:message:3")
        promoted = binding.scheduler.complete(first.opportunity)
        self.assertEqual(promoted.anchor_event_id, "discord:message:3")
        snapshot = binding.observation.snapshot(
            trigger_event_id="discord:message:3", max_events=10, max_bytes=10000
        )
        self.assertEqual([event["id"] for event in snapshot["events"]], [
            "discord:message:1", "discord:message:2", "discord:message:3"
        ])

    def test_restart_restores_context_without_scheduler_work(self):
        original = v2.BindingRegistry(participant_id="resident").get_or_create(self.key())
        original.accept(self.native("discord:message:1"))
        retained = original.export_context()
        restarted = v2.BindingRegistry(participant_id="resident").get_or_create(self.key())
        restarted.restore_context(retained)
        self.assertEqual(restarted.scheduler.snapshot(), ())
        next_delivery = restarted.accept(self.native("discord:message:2"))
        self.assertIsNotNone(next_delivery.opportunity)
        snapshot = restarted.observation.snapshot(
            trigger_event_id="discord:message:2", max_events=10, max_bytes=10000
        )
        self.assertEqual([event["id"] for event in snapshot["events"]], [
            "discord:message:1", "discord:message:2"
        ])
        self.assertTrue(snapshot["coverage"]["has_restart_gap"])


class HermesV2TicketTest(unittest.TestCase):
    def packet(self):
        return {
            "request_id": "req-1",
            "self": {"participant_id": "resident", "actor_id": "discord:user:9001"},
            "room": {
                "platform": "discord",
                "id": "discord:channel:42",
                "continuity_scope_id": "hermes:default:discord:discord:user:9001:discord:channel:42",
            },
            "actors": {"discord:user:1001": {"kind": "human"}},
            "events": [{
                "id": "discord:message:1", "type": "message",
                "author_id": "discord:user:1001", "text": "hi",
                "mentioned_actor_ids": [], "mentions_room": False,
            }],
            "trigger_event_id": "discord:message:1",
            "coverage": {
                "has_more_before": False, "has_more_after": False,
                "has_gaps": False, "truncated_by": [],
                "continuity": "session-only", "has_restart_gap": True,
            },
            "attention": {
                "source": "WAKE",
                "advice": [{"kind": "relevance", "text": "might need you", "evidence_event_ids": ["discord:message:1"]}],
                "evidence_event_ids": ["discord:message:1"],
            },
        }

    def test_ticket_is_one_use_and_wake_is_direct_act_or_silence(self):
        store = v2.TurnTicketStore()
        ticket = store.issue(
            event_id="discord:message:1", session_key="agent:default:discord:42",
            packet=self.packet(),
        )
        self.assertEqual(store.context_for_session("agent:default:discord:42"), "")
        self.assertIs(
            store.consume_dispatch("discord:message:1", "agent:default:discord:42"),
            ticket,
        )
        self.assertIsNone(
            store.consume_dispatch("discord:message:1", "agent:default:discord:42")
        )
        context = store.context_for_session("agent:default:discord:42")
        self.assertIn("act naturally in the room or remain silent", context)
        self.assertIn("untrusted attention annotation", context)
        self.assertNotIn("should you answer", context.lower())

    def test_reserved_wake_is_invisible_until_exact_redispatch_activation(self):
        store = v2.TurnTicketStore()
        session = "agent:default:discord:42"
        ticket = store.issue(
            event_id="discord:message:1",
            session_key=session,
            packet=self.packet(),
        )
        old_owner_context = store.context_for_session(session)
        self.assertEqual(old_owner_context, "")
        self.assertIsNone(store.consume_dispatch("discord:message:2", session))
        self.assertEqual(store.context_for_session(session), "")
        self.assertIs(store.consume_dispatch("discord:message:1", session), ticket)
        self.assertIn("I-010C", store.context_for_session(session))
        self.assertIsNone(store.consume_dispatch("discord:message:1", session))
        self.assertIs(store.complete_session(session), ticket)
        self.assertEqual(store.context_for_session(session), "")

    def test_same_native_event_can_wake_two_exact_profile_sessions(self):
        store = v2.TurnTicketStore()
        store.issue(
            event_id="discord:message:1",
            session_key="agent:profile-a:discord:42",
            packet=self.packet(),
        )
        store.issue(
            event_id="discord:message:1",
            session_key="agent:profile-b:discord:42",
            packet=self.packet(),
        )
        self.assertIsNotNone(
            store.consume_dispatch(
                "discord:message:1", "agent:profile-a:discord:42"
            )
        )
        self.assertIsNotNone(
            store.consume_dispatch(
                "discord:message:1", "agent:profile-b:discord:42"
            )
        )

    def test_internal_events_are_not_projected(self):
        source = SimpleNamespace(profile="default", platform=_Platform("discord"), chat_id="42", thread_id=None)
        event = SimpleNamespace(source=source, message_id="1", text="internal", internal=True)
        adapter = SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        with self.assertRaises(v2.HermesV2BoundaryError):
            v2.project_native_event(event, v2.resolve_binding_key(event, _Gateway(adapter)))


class HermesV2PluginBoundaryTest(unittest.TestCase):
    @staticmethod
    def load_root_plugin():
        path = ROOT / "integrations" / "hermes" / "nunchi-gate" / "__init__.py"
        spec = importlib.util.spec_from_file_location("nunchi_gate_v2_root", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_register_exposes_v2_hooks_and_tool_middleware(self):
        hooks = {}
        middleware = {}

        class Context:
            def register_hook(self, name, callback):
                hooks[name] = callback

            def register_middleware(self, name, callback):
                middleware[name] = callback

        discord_module = SimpleNamespace(
            DiscordAdapter=type("DiscordAdapter", (), {}),
            commands=SimpleNamespace(Bot=type("Bot", (), {})),
            discord=SimpleNamespace(),
        )
        telegram_module = SimpleNamespace(
            TelegramAdapter=type("TelegramAdapter", (), {})
        )
        with unittest.mock.patch.object(
            v2_plugin, "install_host_wrappers", return_value={
                "participant_turn": True, "transport": True,
            }
        ), unittest.mock.patch.object(
            v2_plugin, "install_discord_control_guard", return_value=True
        ), unittest.mock.patch.object(
            v2_plugin, "install_discord_raw_observer", return_value=True
        ), unittest.mock.patch.object(
            v2_plugin, "install_telegram_exact_text", return_value=True
        ), unittest.mock.patch.object(
            v2_plugin,
            "_load_platform_module",
            side_effect=lambda name: (
                discord_module if "discord" in name else telegram_module
            ),
        ):
            v2_plugin.register(Context())
        self.assertEqual(set(hooks), {"pre_gateway_dispatch", "pre_llm_call"})
        self.assertEqual(set(middleware), {"tool_execution"})
        self.assertIs(hooks["pre_gateway_dispatch"], v2_plugin.on_pre_gateway_dispatch)
        self.assertIs(hooks["pre_llm_call"], v2_plugin.on_pre_llm_call)

    def test_register_fails_closed_without_required_host_wrappers(self):
        class Context:
            def register_hook(self, name, callback):
                pass

            def register_middleware(self, name, callback):
                pass

        with unittest.mock.patch.object(
            v2_plugin, "install_host_wrappers", return_value={
                "participant_turn": False, "transport": False,
            }
        ):
            with self.assertRaisesRegex(
                v2_plugin.HermesV2BoundaryError,
                "participant and transport wrappers are required",
            ):
                v2_plugin.register(Context())

    def test_pre_llm_context_is_available_only_for_ticketed_session(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        packet = HermesV2TicketTest().packet()
        controller.tickets.issue(
            event_id="discord:message:1",
            session_key="agent:default:discord:42",
            packet=packet,
        )
        self.assertIsNone(
            controller.pre_llm_call(session_key="agent:default:discord:42")
        )
        controller.tickets.consume_dispatch(
            "discord:message:1", "agent:default:discord:42"
        )
        admitted = controller.pre_llm_call(session_key="agent:default:discord:42")
        self.assertIn("context", admitted)
        self.assertIn("act naturally in the room or remain silent", admitted["context"])
        self.assertIsNone(controller.pre_llm_call(session_key="other"))

    def test_ticketed_tool_effect_is_blocked_without_canonical_authorization(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        packet = HermesV2TicketTest().packet()
        controller.tickets.issue(
            event_id="discord:message:1",
            session_key="agent:default:discord:42",
            packet=packet,
        )
        controller.tickets.consume_dispatch(
            "discord:message:1", "agent:default:discord:42"
        )
        called = []
        token = controller.bind_tool_session("agent:default:discord:42")
        try:
            with self.assertRaises(v2.HermesV2BoundaryError):
                controller.tool_execution(
                    tool_name="terminal",
                    arguments={"command": "true"},
                    next_call=lambda: called.append(True),
                )
        finally:
            controller.reset_tool_session(token)
        self.assertEqual(called, [])

    def test_non_nunchi_tool_effect_passes_through_unchanged(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        called = []
        result = controller.tool_execution(
            tool_name="terminal",
            arguments={"command": "true"},
            next_call=lambda: called.append(True) or "ok",
        )
        self.assertEqual(result, "ok")
        self.assertEqual(called, [True])

    def test_root_plugin_registers_v2_not_retired_v1_gate(self):
        plugin = self.load_root_plugin()
        hooks = {}
        middleware = {}

        class Context:
            def register_hook(self, name, callback):
                hooks[name] = callback

            def register_middleware(self, name, callback):
                middleware[name] = callback

            def register_command(self, *args, **kwargs):
                raise AssertionError("the V1 /nunchi mutation surface must not register")

        discord_module = SimpleNamespace(
            DiscordAdapter=type("DiscordAdapter", (), {}),
            commands=SimpleNamespace(Bot=type("Bot", (), {})),
            discord=SimpleNamespace(),
        )
        telegram_module = SimpleNamespace(
            TelegramAdapter=type("TelegramAdapter", (), {})
        )
        with unittest.mock.patch.object(
            plugin._v2_plugin,
            "install_host_wrappers",
            return_value={"participant_turn": True, "transport": True},
        ), unittest.mock.patch.object(
            plugin._v2_plugin, "install_discord_control_guard", return_value=True
        ), unittest.mock.patch.object(
            plugin._v2_plugin, "install_discord_raw_observer", return_value=True
        ), unittest.mock.patch.object(
            plugin._v2_plugin, "install_telegram_exact_text", return_value=True
        ), unittest.mock.patch.object(
            plugin._v2_plugin,
            "_load_platform_module",
            side_effect=lambda name: (
                discord_module if "discord" in name else telegram_module
            ),
        ):
            plugin.register(Context())
        self.assertIs(hooks["pre_gateway_dispatch"], plugin._v2_plugin.on_pre_gateway_dispatch)
        self.assertIs(hooks["pre_llm_call"], plugin._v2_plugin.on_pre_llm_call)
        self.assertIs(middleware["tool_execution"], plugin._v2_plugin.on_tool_execution)
        self.assertFalse(hasattr(plugin, "_gate_event"))
        self.assertIsNotNone(plugin._v2_plugin._CONFIG_LOADER)
        self.assertIsNotNone(plugin._v2_plugin._SCHEDULE_REDISPATCH)

    def test_root_plugin_exposes_no_retired_v1_product_surface(self):
        plugin = self.load_root_plugin()
        forbidden = {
            "_gate_event",
            "_run_gate",
            "_nunchi_command",
            "resolve_channel_config",
            "_resolve_channel_config",
            "_cmd_enable_disable",
            "_cmd_senders",
            "_cmd_verbosity",
            "_cmd_chatter",
            "_cmd_reset",
            "_SEND_BACKSTOP",
            "_SPEAK_VERDICTS",
            "_install_quiet_room_patches",
        }
        exposed = set(vars(plugin))
        self.assertEqual(forbidden & exposed, set())
        self.assertEqual(getattr(plugin, "__all__", None), ["register"])
        source = (
            ROOT / "integrations" / "hermes" / "nunchi-gate" / "__init__.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("register_command", source)
        self.assertNotIn("turnaware", source)
        self.assertNotIn("PASS / ACK / ASK / SPEAK", source)

    def test_manifest_declares_v2_hooks_and_execution_middleware(self):
        manifest = (ROOT / "integrations" / "hermes" / "nunchi-gate" / "plugin.yaml").read_text()
        self.assertIn("version: 2.0.0", manifest)
        self.assertIn("- pre_gateway_dispatch", manifest)
        self.assertIn("- pre_llm_call", manifest)
        self.assertIn("- tool_execution", manifest)
        self.assertNotIn("PASS / ACK / ASK / SPEAK", manifest)


class HermesV2LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.key = v2.BindingKey(
            "default", "discord", "discord:user:9001", "discord:channel:42"
        )
        policy = clone_policy()
        policy["attention"]["participant_id"] = "resident"
        policy["recoverability"]["participant_id"] = "resident"
        policy["recoverability"]["continuity_scope_id"] = self.key.continuity_scope_id
        self.policy_path = write_policy(self.temporary.name, policy)
        self.receipts = []

    @staticmethod
    def native(event_id="discord:message:1"):
        return {
            "delivery_id": event_id,
            "disposition": "candidate-event",
            "authorized": True,
            "event": {
                "id": event_id,
                "type": "message",
                "author_id": "discord:user:1001",
                "text": "hello",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            },
            "actors": {"discord:user:1001": {"kind": "human"}},
        }

    def binding_and_opportunity(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        binding = controller.registry.get_or_create(self.key)
        accepted = binding.accept(self.native())
        return controller, binding, accepted.opportunity

    @staticmethod
    def hermes_event(message_id="1"):
        source = SimpleNamespace(
            profile="default", platform=_Platform("discord"), chat_id="42",
            thread_id=None, user_id="1001", user_name="Zoe", is_bot=False,
        )
        raw = SimpleNamespace(
            id=int(message_id),
            author=SimpleNamespace(id=1001, display_name="Zoe", bot=False),
            mentions=[], reference=None, created_at=None, mention_everyone=False,
        )
        return SimpleNamespace(
            source=source, message_id=message_id, text="hello",
            raw_message=raw, internal=False,
        )

    def policy_with_grant(
        self,
        *,
        capability: str,
        resource_kind: str,
        resource_id: str,
        actor_id: str = "discord:user:1001",
        impact: str = "mutation",
        execution: str = "direct",
    ):
        policy = clone_policy()
        policy["attention"]["participant_id"] = "resident"
        policy["recoverability"]["participant_id"] = "resident"
        policy["recoverability"]["continuity_scope_id"] = self.key.continuity_scope_id
        grant = {
            "grant_id": "grant-hermes-test",
            "actor_id": actor_id,
            "capability": capability,
            "scope": {
                "platform": "discord",
                "room_id": self.key.room_scope_id,
                "participant_id": "resident",
                "resource": {"kind": resource_kind, "id": resource_id},
            },
            "impact": impact,
            "execution": execution,
            "status": "active",
        }
        if execution == "direct":
            grant["expires_at"] = "2030-01-01T00:00:00Z"
        else:
            grant["allowed_approver_actor_ids"] = ["discord:user:admin"]
        policy["authorization"]["grants"] = [grant]
        self.policy_path = write_policy(self.temporary.name, policy)

    def active_tool_turn(self, controller, event_id, *, receipt_sink=None):
        session_key = "agent:default:discord:42"
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        result = controller.process_delivery(
            event=self.hermes_event(event_id),
            gateway=gateway,
            session_key=session_key,
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=receipt_sink or self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        trigger_id = f"discord:message:{event_id}"
        self.assertIsNotNone(controller.tickets.consume_dispatch(trigger_id, session_key))
        token = controller.bind_tool_session(session_key)
        self.addCleanup(controller.reset_tool_session, token)
        return session_key, result.evaluation

    def activate_turn(
        self,
        controller,
        event_id,
        session_key="agent:default:discord:42",
    ):
        trigger_id = (
            str(event_id)
            if str(event_id).startswith("discord:message:")
            else f"discord:message:{event_id}"
        )
        self.assertIsNotNone(
            controller.tickets.consume_dispatch(trigger_id, session_key)
        )

    def test_explicit_non_privileged_tool_runs_after_participant_receipt(self):
        order = []

        def sink(receipt):
            self.receipts.append(receipt)
            if receipt["stage"] == "participant-host":
                order.append("participant")

        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        session_key, _evaluation = self.active_tool_turn(
            controller, "3001", receipt_sink=sink
        )
        result = controller.tool_execution(
            tool_name="web_search",
            arguments={"query": "nunchi"},
            next_call=lambda arguments: order.append("executor") or {"ok": arguments},
        )
        self.assertEqual(result, {"ok": {"query": "nunchi"}})
        self.assertEqual(order, ["participant", "executor"])
        controller.complete_transport(session_key, delivery="sent")

    def test_reaction_tool_executes_only_after_exact_i040b_allow(self):
        self.policy_with_grant(
            capability="room.reaction.add",
            resource_kind="room-message",
            resource_id="discord:message:3002",
        )
        audits = []
        order = []
        controller = v2_plugin.HermesV2Controller(
            participant_id="resident",
            authorization_sink_factory=lambda policy_loader: audits.append,
        )

        def sink(receipt):
            self.receipts.append(receipt)
            if receipt["stage"] == "participant-host":
                order.append("participant")

        session_key, _evaluation = self.active_tool_turn(
            controller, "3002", receipt_sink=sink
        )
        arguments = {
            "action": "react",
            "target": "discord:42",
            "message_id": "3002",
            "emoji": "👀",
        }
        result = controller.tool_execution(
            tool_name="send_message",
            arguments=arguments,
            next_call=lambda supplied: order.append("executor") or "reacted",
        )
        self.assertEqual(result, "reacted")
        self.assertEqual(order, ["participant", "executor"])
        self.assertEqual(audits[-1]["decision"], "ALLOW")
        self.assertEqual(audits[-1]["origin_event_id"], "discord:message:3002")
        self.assertEqual(
            audits[-1]["action_digest"],
            canonical_action_digest(
                {"tool_name": "send_message", "arguments": arguments}
            ),
        )
        controller.complete_transport(session_key, delivery="sent")

    def test_telegram_reaction_binds_exact_topic_and_native_message(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        _session_key, evaluation = self.active_tool_turn(controller, "3002")
        packet = dict(evaluation.packet)
        packet["room"] = {
            "platform": "telegram",
            "id": "telegram:chat:-10042:topic:7",
        }
        packet["events"] = [
            {
                "id": "telegram:message:-10042:55",
                "author_id": "telegram:user:2002",
                "content": "hello",
            }
        ]
        evaluation = replace(evaluation, packet=packet)

        action = controller._privileged_action(
            evaluation,
            tool_name="send_message",
            arguments={
                "action": "react",
                "target": "telegram:-10042:7",
                "message_id": "55",
                "emoji": "✅",
            },
        )
        request = action["authorization_request"]
        self.assertEqual(request["scope"]["room_id"], "telegram:chat:-10042:topic:7")
        self.assertEqual(
            request["scope"]["resource"]["id"],
            "telegram:message:-10042:55",
        )
        with self.assertRaisesRegex(
            v2.HermesV2BoundaryError, "cross-room reaction"
        ):
            controller._privileged_action(
                evaluation,
                tool_name="send_message",
                arguments={
                    "action": "react",
                    "target": "telegram:7",
                    "message_id": "55",
                    "emoji": "✅",
                },
            )
        with self.assertRaisesRegex(
            v2.HermesV2BoundaryError, "reaction message ID is invalid"
        ):
            controller._privileged_action(
                evaluation,
                tool_name="send_message",
                arguments={
                    "action": "react",
                    "target": "telegram:-10042:7",
                    "message_id": "telegram:message:-10042:55",
                    "emoji": "✅",
                },
            )

    def test_reaction_bridge_executes_pinned_discord_and_telegram_native_paths(self):
        installer = getattr(v2_plugin, "install_reaction_bridge", None)
        self.assertTrue(callable(installer), "reaction bridge must be installed")

        discord_calls = []

        class DiscordMessage:
            reactions = [SimpleNamespace(me=True, emoji="✅")]

            async def add_reaction(self, emoji):
                discord_calls.append(("add", emoji))

            async def remove_reaction(self, emoji, actor):
                discord_calls.append(("remove", emoji, actor))

        message = DiscordMessage()

        class DiscordChannel:
            async def fetch_message(self, message_id):
                discord_calls.append(("fetch-message", message_id))
                return message

        class DiscordClient:
            user = "self-user"

            def get_channel(self, chat_id):
                discord_calls.append(("get-channel", chat_id))
                return DiscordChannel()

        class DiscordAdapter:
            def __init__(self):
                self._client = DiscordClient()

        self.assertTrue(installer(DiscordAdapter, platform="discord"))
        discord_adapter = DiscordAdapter()
        self.assertTrue(
            asyncio.run(
                discord_adapter.add_reaction(
                    chat_id="42", emoji="✅", message_id="3002"
                )
            )
        )
        self.assertTrue(
            asyncio.run(
                discord_adapter.remove_reaction(chat_id="42", message_id="3002")
            )
        )
        self.assertIn(("get-channel", 42), discord_calls)
        self.assertIn(("add", "✅"), discord_calls)
        self.assertIn(("remove", "✅", "self-user"), discord_calls)

        telegram_calls = []

        class TelegramBot:
            async def set_message_reaction(self, **kwargs):
                telegram_calls.append(kwargs)

        class TelegramAdapter:
            def __init__(self):
                self._app = SimpleNamespace(bot=TelegramBot())
                self._bot = None

        class Reaction:
            def __init__(self, emoji):
                self.emoji = emoji

        self.assertTrue(
            installer(
                TelegramAdapter,
                platform="telegram",
                reaction_factory=Reaction,
            )
        )
        telegram_adapter = TelegramAdapter()
        self.assertTrue(
            asyncio.run(
                telegram_adapter.add_reaction(
                    chat_id="-10042", emoji="✅", message_id="55"
                )
            )
        )
        self.assertTrue(
            asyncio.run(
                telegram_adapter.remove_reaction(
                    chat_id="-10042", message_id="55"
                )
            )
        )
        self.assertEqual(telegram_calls[0]["chat_id"], -10042)
        self.assertEqual(telegram_calls[0]["message_id"], 55)
        self.assertEqual(telegram_calls[0]["reaction"][0].emoji, "✅")
        self.assertEqual(telegram_calls[1]["reaction"], [])

    def test_privileged_tool_denies_wrong_requester_and_cross_room(self):
        self.policy_with_grant(
            capability="workspace.file.write",
            resource_kind="workspace-file",
            resource_id="docs/release.md",
            actor_id="discord:user:someone-else",
        )
        audits = []
        controller = v2_plugin.HermesV2Controller(
            participant_id="resident",
            authorization_sink_factory=lambda policy_loader: audits.append,
        )
        self.active_tool_turn(controller, "3003")
        effects = []
        with self.assertRaises(v2_plugin.HermesV2BoundaryError):
            controller.tool_execution(
                tool_name="write_file",
                arguments={"path": "docs/release.md", "content": "ready"},
                next_call=lambda supplied: effects.append(supplied),
            )
        self.assertEqual(effects, [])
        self.assertEqual(audits[-1]["decision"], "DENY")

        self.policy_with_grant(
            capability="room.reaction.add",
            resource_kind="room-message",
            resource_id="discord:message:3004",
        )
        controller = v2_plugin.HermesV2Controller(
            participant_id="resident",
            authorization_sink_factory=lambda policy_loader: audits.append,
        )
        self.active_tool_turn(controller, "3004")
        with self.assertRaisesRegex(v2_plugin.HermesV2BoundaryError, "cross-room"):
            controller.tool_execution(
                tool_name="send_message",
                arguments={
                    "action": "react",
                    "target": "discord:999",
                    "message_id": "3004",
                    "emoji": "👀",
                },
                next_call=lambda supplied: effects.append(supplied),
            )
        self.assertEqual(effects, [])

    def test_revoked_grant_and_executor_failure_have_zero_unattested_effects(self):
        self.policy_with_grant(
            capability="workspace.file.write",
            resource_kind="workspace-file",
            resource_id="docs/release.md",
        )
        audits = []

        def revoking_sink_factory(policy_loader):
            def persist(decision):
                audits.append(decision)
                document = json.loads(self.policy_path.read_text(encoding="utf-8"))
                document["authorization"]["grants"][0]["status"] = "revoked"
                write_policy(self.temporary.name, document)
            return persist

        controller = v2_plugin.HermesV2Controller(
            participant_id="resident",
            authorization_sink_factory=revoking_sink_factory,
        )
        self.active_tool_turn(controller, "3005")
        effects = []
        with self.assertRaises(Exception):
            controller.tool_execution(
                tool_name="write_file",
                arguments={"path": "docs/release.md", "content": "ready"},
                next_call=lambda supplied: effects.append(supplied),
            )
        self.assertEqual(audits[-1]["decision"], "ALLOW")
        self.assertEqual(effects, [])

        self.policy_with_grant(
            capability="workspace.file.write",
            resource_kind="workspace-file",
            resource_id="docs/release.md",
        )
        controller = v2_plugin.HermesV2Controller(
            participant_id="resident",
            authorization_sink_factory=lambda policy_loader: audits.append,
        )
        self.active_tool_turn(controller, "3006")
        with self.assertRaisesRegex(RuntimeError, "executor failed"):
            controller.tool_execution(
                tool_name="write_file",
                arguments={"path": "docs/release.md", "content": "ready"},
                next_call=lambda supplied: (_ for _ in ()).throw(
                    RuntimeError("executor failed")
                ),
            )
        self.assertEqual(audits[-1]["decision"], "ALLOW")

    def test_approval_required_never_executes_from_room_prose(self):
        self.policy_with_grant(
            capability="workspace.file.delete",
            resource_kind="workspace-file",
            resource_id="tmp/stale.txt",
            impact="destructive",
            execution="approval",
        )
        audits = []
        effects = []
        controller = v2_plugin.HermesV2Controller(
            participant_id="resident",
            authorization_sink_factory=lambda policy_loader: audits.append,
        )
        self.active_tool_turn(controller, "3007")
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError, "authenticated approval"
        ):
            controller.tool_execution(
                tool_name="delete_file",
                arguments={"path": "tmp/stale.txt"},
                next_call=lambda supplied: effects.append(supplied) or "deleted",
            )
        self.assertEqual(effects, [])
        pending = controller.pending_authorizations()
        self.assertEqual(len(pending), 1)
        challenge = pending[0]["authorization"]["approval_challenge"]
        completed = controller.complete_authenticated_approval(
            {
                "challenge_id": challenge["challenge_id"],
                "attestation_id": "operator-attestation-1",
                "approver_actor_id": "discord:user:admin",
                "approved_at": audits[-1]["evaluated_at"],
                "channel": "authenticated-transport",
            }
        )
        self.assertEqual(completed["execution"], "executed")
        self.assertEqual(effects, [{"path": "tmp/stale.txt"}])

    def test_suppress_writes_observation_and_attention_without_ticket(self):
        controller, binding, opportunity = self.binding_and_opportunity()
        result = controller.evaluate_opportunity(
            binding=binding,
            opportunity=opportunity,
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, config: {
                "disposition": "SUPPRESS",
                "reasons": ["no contribution is useful"],
                "evidence_event_ids": [projection["trigger_event_id"]],
                "legacy_verdict_confidences": {
                    "PASS": 0.99, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.01,
                },
            },
        )
        self.assertEqual(result.status, "suppressed")
        self.assertEqual([row["stage"] for row in self.receipts], ["observation", "attention"])
        self.assertEqual(binding.scheduler.snapshot(), ())

    def test_transport_context_is_retained_without_attention_opportunity(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("88")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        accepted = controller.accept_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: self.fail(
                "context-only delivery requested attention"
            ),
            schedule=False,
        )
        self.assertIsNone(accepted.opportunity)
        binding = controller.registry.get_or_create(
            v2.resolve_binding_key(event, gateway)
        )
        self.assertEqual(binding.scheduler.snapshot(), ())
        self.assertEqual(
            binding.export_context()[-1]["event"]["id"],
            "discord:message:88",
        )

    def test_discord_trigger_uses_snapshotted_native_room_text_everywhere(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("881")
        event.raw_message._nunchi_v2_raw_content = "<@9001> exact words"
        event.raw_message.content = "exact words"
        event.text = "exact words\n\n[Files attached: host-injected.txt]"
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        classifier_requests = []

        def classify(projection, classifier):
            classifier_requests.append(projection)
            return {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            }

        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=classify,
        )
        self.assertEqual(result.status, "wake")
        exact = "<@9001> exact words"
        binding = result.evaluation.binding
        self.assertEqual(binding.export_context()[-1]["event"]["text"], exact)
        self.assertEqual(classifier_requests[0]["events"][-1]["text"], exact)
        self.assertEqual(result.evaluation.request["events"][-1]["text"], exact)
        self.assertEqual(
            result.evaluation.participant_snapshot["events"][-1]["text"], exact
        )
        self.assertEqual(result.evaluation.packet["events"][-1]["text"], exact)
        self.assertNotIn("Files attached", result.evaluation.packet["events"][-1]["text"])
        controller.abort_participant_turn("agent:default:discord:42")

    def test_native_context_retention_is_bounded_and_keeps_newest_order(self):
        binding = v2.BindingState(
            self.key,
            participant_id="resident",
            max_native_context=2,
        )
        for event_id in ("discord:message:1", "discord:message:2", "discord:message:3"):
            binding.accept_context(self.native(event_id))
        self.assertEqual(
            [row["event"]["id"] for row in binding.export_context()],
            ["discord:message:2", "discord:message:3"],
        )

    def test_suppress_promotes_and_evaluates_newest_pending_anchor(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        classifier_calls = []

        def classifier(projection, config):
            trigger = projection["trigger_event_id"]
            classifier_calls.append(trigger)
            if trigger == "discord:message:1":
                return {
                    "disposition": "SUPPRESS",
                    "reasons": ["no contribution is useful"],
                    "evidence_event_ids": [trigger],
                    "legacy_verdict_confidences": {
                        "PASS": 0.99,
                        "ACK": 0.0,
                        "ASK": 0.0,
                        "SPEAK": 0.01,
                    },
                }
            return {
                "disposition": "WAKE",
                "reasons": ["the newest event may need a contribution"],
                "evidence_event_ids": [trigger],
            }

        common = {
            "gateway": gateway,
            "session_key": "agent:default:discord:42",
            "participant_id": "resident",
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
            "classifier_transport": classifier,
        }
        first = controller.accept_delivery(event=self.hermes_event("1"), **common)
        second = controller.accept_delivery(event=self.hermes_event("2"), **common)
        self.assertIsNotNone(first.opportunity)
        self.assertIsNone(second.opportunity)
        result = controller.evaluate_delivery(first)
        self.assertEqual(result.status, "suppressed")
        self.activate_turn(controller, "2")
        self.assertEqual(
            classifier_calls,
            ["discord:message:1", "discord:message:2"],
        )
        successor = controller.tickets.context_for_session(
            "agent:default:discord:42"
        )
        self.assertIn('"trigger_event_id": "discord:message:2"', successor)

    def test_host_delivery_retention_is_bounded_and_terminally_released(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )

        def suppress(projection, config):
            trigger = projection["trigger_event_id"]
            return {
                "disposition": "SUPPRESS",
                "reasons": ["no contribution is useful"],
                "evidence_event_ids": [trigger],
                "legacy_verdict_confidences": {
                    "PASS": 0.99,
                    "ACK": 0.0,
                    "ASK": 0.0,
                    "SPEAK": 0.01,
                },
            }

        common = {
            "gateway": gateway,
            "session_key": "agent:default:discord:42",
            "participant_id": "resident",
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
            "classifier_transport": suppress,
        }
        first = controller.accept_delivery(event=self.hermes_event("1"), **common)
        for message_id in range(2, 102):
            controller.accept_delivery(
                event=self.hermes_event(str(message_id)), **common
            )
        self.assertLessEqual(len(controller._host_deliveries), 2)
        controller.evaluate_delivery(first)
        self.assertEqual(controller._host_deliveries, {})

    def test_wake_stages_one_turn_and_receipts_before_transport(self):
        controller, binding, opportunity = self.binding_and_opportunity()
        result = controller.evaluate_opportunity(
            binding=binding,
            opportunity=opportunity,
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, config: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        ticket = controller.stage_turn(
            evaluation=result,
            session_key="agent:default:discord:42",
        )
        self.assertEqual(ticket.event_id, "discord:message:1")
        participant = controller.complete_participant_turn(
            "agent:default:discord:42", "I can help."
        )
        self.assertEqual(participant["kind"], "message")
        self.assertEqual([row["stage"] for row in self.receipts], [
            "observation", "attention", "participant-host"
        ])
        controller.complete_transport(
            "agent:default:discord:42", delivery="sent"
        )
        self.assertEqual([row["stage"] for row in self.receipts], [
            "observation", "attention", "participant-host", "transport"
        ])
        self.assertEqual(binding.scheduler.snapshot(), ())

    def test_process_delivery_stages_exactly_one_normal_hermes_turn(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event()
        gateway = _Gateway(SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001))))
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, config: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "1")
        context = controller.tickets.context_for_session("agent:default:discord:42")
        self.assertEqual(
            context.count("Nunchi V2 has admitted one normal participant turn"),
            1,
        )
        self.assertEqual(
            [row["stage"] for row in self.receipts],
            ["observation", "attention"],
        )

    def test_one_controller_supports_distinct_participants_per_profile(self):
        controller = v2_plugin.HermesV2Controller(
            participant_id="profile-a-participant"
        )
        profile_a = self.hermes_event("71")
        profile_b = self.hermes_event("72")
        profile_b.source.profile = "profile-b"
        adapter_a = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        adapter_b = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9002))
        )
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: (
                adapter_a if source.profile == "default" else adapter_b
            )
        )
        key_a = v2.resolve_binding_key(profile_a, gateway)
        key_b = v2.resolve_binding_key(profile_b, gateway)
        a = controller.registry_for("profile-a-participant").get_or_create(key_a)
        b = controller.registry_for("profile-b-participant").get_or_create(key_b)
        self.assertEqual(a.observation.participant_id, "profile-a-participant")
        self.assertEqual(b.observation.participant_id, "profile-b-participant")
        self.assertIsNot(a.observation, b.observation)

    def test_host_delivery_correlation_includes_participant_identity(self):
        controller = v2_plugin.HermesV2Controller(participant_id="participant-a")
        event = self.hermes_event("199")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        common = {
            "event": event,
            "gateway": gateway,
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
        }
        controller.accept_delivery(
            **common,
            session_key="agent:a:discord:42",
            participant_id="participant-a",
        )
        controller.accept_delivery(
            **common,
            session_key="agent:b:discord:42",
            participant_id="participant-b",
        )
        self.assertEqual(len(controller._host_deliveries), 2)
        self.assertEqual(
            {key[0] for key in controller._host_deliveries},
            {"participant-a", "participant-b"},
        )

    def test_secondary_profile_closure_recovers_gateway(self):
        class Gateway:
            def _session_key_for_source(self, source):
                return "agent:secondary:discord:42"

            async def handle(self, event):
                return None

        gateway = Gateway()

        def make_handler():
            async def handler(event):
                return await gateway.handle(event)

            return handler

        adapter = SimpleNamespace(_message_handler=make_handler())
        self.assertIs(v2_plugin._gateway_for_adapter(adapter), gateway)

    def test_promoted_policy_failure_releases_successor_generation(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        suppress = lambda projection, classifier: {
            "disposition": "SUPPRESS",
            "reasons": ["no contribution is useful"],
            "evidence_event_ids": [projection["trigger_event_id"]],
            "legacy_verdict_confidences": {
                "PASS": 0.99, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.01,
            },
        }
        first = controller.accept_delivery(
            event=self.hermes_event("201"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=suppress,
        )
        controller.accept_delivery(
            event=self.hermes_event("202"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: (_ for _ in ()).throw(OSError("policy unavailable")),
            receipt_sink=self.receipts.append,
            classifier_transport=suppress,
        )
        result = controller.evaluate_delivery(first)
        self.assertEqual(result.status, "suppressed")
        self.assertEqual(first.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_receipt_failure_closes_ticket_and_scheduler(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )

        def sink(receipt):
            if receipt["stage"] == "participant-host":
                raise OSError("receipt disk unavailable")
            self.receipts.append(receipt)

        result = controller.process_delivery(
            event=self.hermes_event("203"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=sink,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        with self.assertRaisesRegex(OSError, "receipt disk unavailable"):
            controller.complete_participant_turn(
                "agent:default:discord:42", "hello"
            )
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_non_none_observation_receipt_stops_before_classifier(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        classifier_calls = []
        receipts = []

        def sink(receipt):
            receipts.append(receipt)
            return False if receipt["stage"] == "observation" else None

        accepted = controller.accept_delivery(
            event=self.hermes_event("2032"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=sink,
            classifier_transport=lambda projection, classifier: classifier_calls.append(
                projection
            ),
        )
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError,
            "observation receipt persistence is unknown",
        ):
            controller.evaluate_delivery(accepted)
        self.assertEqual(classifier_calls, [])
        self.assertEqual([row["stage"] for row in receipts], ["observation"])
        self.assertEqual(accepted.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))

    def test_non_none_participant_receipt_stops_before_effect(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        receipts = []

        def sink(receipt):
            receipts.append(receipt)
            return False if receipt["stage"] == "participant-host" else None

        result = controller.process_delivery(
            event=self.hermes_event("2033"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=sink,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError,
            "participant-host receipt persistence is unknown",
        ):
            controller.complete_participant_turn(
                "agent:default:discord:42", "must not be released"
            )
        self.assertEqual(
            [row["stage"] for row in receipts],
            ["observation", "attention", "participant-host"],
        )
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_non_none_transport_receipt_never_becomes_terminal_fact(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        receipts = []

        def sink(receipt):
            receipts.append(receipt)
            return False if receipt["stage"] == "transport" else None

        result = controller.process_delivery(
            event=self.hermes_event("2034"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=sink,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        action = controller.complete_participant_turn(
            "agent:default:discord:42", "delivered but not attestable"
        )
        self.assertEqual(action["kind"], "message")
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError,
            "transport receipt persistence is unknown",
        ):
            controller.complete_transport(
                "agent:default:discord:42", delivery="sent"
            )
        self.assertEqual(
            [row["stage"] for row in receipts],
            ["observation", "attention", "participant-host", "transport"],
        )
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_no_wake_writes_canonical_uninvoked_participant_receipt(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        policy = load_operator_policy(self.policy_path)
        object.__setattr__(policy.attention, "error_action", "NO_WAKE")
        receipts = []

        result = controller.process_delivery(
            event=self.hermes_event("2035"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: policy,
            receipt_sink=receipts.append,
            classifier_transport=lambda projection, classifier: (
                _ for _ in ()
            ).throw(OSError("classifier unavailable")),
        )

        self.assertEqual(result.status, "no-wake")
        self.assertEqual(
            [row["stage"] for row in receipts],
            ["observation", "attention", "participant-host"],
        )
        participant = receipts[-1]["body"]
        self.assertIs(participant["invoked"], False)
        self.assertEqual(participant["outcome"], "unknown")
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_non_none_abort_receipt_is_persistence_unknown(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        receipts = []

        def sink(receipt):
            receipts.append(receipt)
            return False if receipt["stage"] == "participant-host" else None

        result = controller.process_delivery(
            event=self.hermes_event("2036"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=sink,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError,
            "participant-host receipt persistence is unknown",
        ):
            controller.abort_participant_turn("agent:default:discord:42")
        self.assertIs(receipts[-1]["body"]["invoked"], False)
        self.assertEqual(receipts[-1]["body"]["outcome"], "unknown")
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_participant_exception_abort_records_invoked_true(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("2037")
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        gateway = _Gateway(adapter)
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertIsNotNone(
            controller.tickets.consume_dispatch(
                "discord:message:2037", "agent:default:discord:42"
            )
        )
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)

        class Runner:
            def _adapter_for_source(self, source):
                return adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _normalize_source_for_session_key(self, source):
                return source

            def _resolve_session_agent_runtime(self, **kwargs):
                return "test-model", {"api_mode": "chat_completions"}

            async def _handle_message_with_agent(self, *args, **kwargs):
                raise RuntimeError("participant exploded")

        v2_plugin.install_host_wrappers(
            runner_cls=Runner, adapter_cls=type("AdapterWithoutOutput", (), {})
        )
        with self.assertRaisesRegex(RuntimeError, "participant exploded"):
            asyncio.run(
                Runner()._handle_message_with_agent(
                    event, event.source, "agent:default:discord:42", 1
                )
            )
        self.assertEqual(self.receipts[-1]["stage"], "participant-host")
        self.assertIs(self.receipts[-1]["body"]["invoked"], True)
        self.assertEqual(self.receipts[-1]["body"]["outcome"], "unknown")
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_cancellation_survives_failing_participant_receipt_cleanup(self):
        session_key = "agent:default:discord:42"
        event = self.hermes_event("2031")
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        started = asyncio.Event()
        blocked = asyncio.Event()

        class Runner:
            def __init__(self):
                self.adapter = SimpleNamespace(
                    _client=SimpleNamespace(user=SimpleNamespace(id=9001))
                )

            def _adapter_for_source(self, source):
                return self.adapter

            def _session_key_for_source(self, source):
                return session_key

            def _normalize_source_for_session_key(self, source):
                return source

            def _resolve_session_agent_runtime(self, **kwargs):
                return "test-model", {"api_mode": "chat_completions"}

            async def _handle_message_with_agent(
                self, supplied_event, source, supplied_session, generation
            ):
                started.set()
                await blocked.wait()

        runner = Runner()

        def failing_sink(receipt):
            if receipt["stage"] == "participant-host":
                raise OSError("participant receipt unavailable")
            self.receipts.append(receipt)

        result = controller.process_delivery(
            event=event,
            gateway=runner,
            session_key=session_key,
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=failing_sink,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "2031")
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        v2_plugin.install_host_wrappers(
            runner_cls=Runner,
            adapter_cls=type("AdapterWithoutOutput", (), {}),
        )

        async def cancel_participant():
            task = asyncio.create_task(
                runner._handle_message_with_agent(
                    event, event.source, session_key, 1
                )
            )
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        with self.assertLogs(v2_plugin.logger, level="ERROR") as cleanup_logs:
            asyncio.run(cancel_participant())
        self.assertTrue(
            any(
                "cleanup failed while preserving task cancellation" in message
                for message in cleanup_logs.output
            )
        )
        self.assertFalse(controller.is_ticketed(session_key))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})

    def test_promoted_redispatch_failure_aborts_staged_turn(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )

        def classify(projection, classifier):
            trigger = projection["trigger_event_id"]
            if trigger.endswith(":204"):
                return {
                    "disposition": "SUPPRESS",
                    "reasons": ["no contribution is useful"],
                    "evidence_event_ids": [trigger],
                    "legacy_verdict_confidences": {
                        "PASS": 0.99,
                        "ACK": 0.0,
                        "ASK": 0.0,
                        "SPEAK": 0.01,
                    },
                }
            return {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [trigger],
            }

        first = controller.accept_delivery(
            event=self.hermes_event("204"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=classify,
        )
        controller.accept_delivery(
            event=self.hermes_event("205"),
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=classify,
            redispatch=lambda supplied_event, supplied_gateway: (_ for _ in ()).throw(
                RuntimeError("redispatch failed")
            ),
        )
        result = controller.evaluate_delivery(first)
        self.assertEqual(result.status, "suppressed")
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(first.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})
        self.assertFalse(self.receipts[-1]["body"]["invoked"])

    def test_public_dispatch_hook_skips_first_pass_and_consumes_one_wake_ticket(self):
        event = self.hermes_event()
        adapter = SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            _is_user_authorized=lambda source: True,
        )
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )
        first = v2_plugin.on_pre_gateway_dispatch(event=event, gateway=gateway)
        self.assertEqual(first, {"action": "skip", "reason": "nunchi:v2-attention"})
        second = v2_plugin.on_pre_gateway_dispatch(event=event, gateway=gateway)
        self.assertIsNone(second)
        third = v2_plugin.on_pre_gateway_dispatch(event=event, gateway=gateway)
        self.assertEqual(third, {"action": "skip", "reason": "nunchi:v2-observed"})

    def test_unauthorized_dispatch_is_not_retained_or_receipted(self):
        event = self.hermes_event("41")
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            # Canonical authorization is a strict bool contract. A truthy
            # coroutine/object must fail closed rather than be coerced.
            _is_user_authorized=lambda source: object(),
        )
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=lambda projection, classifier: self.fail(
                "unauthorized text reached the classifier"
            ),
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )
        self.assertIsNone(
            v2_plugin.on_pre_gateway_dispatch(event=event, gateway=gateway)
        )
        self.assertEqual(self.receipts, [])
        self.assertEqual(len(v2_plugin._CONTROLLER.registry), 0)

    def test_receipt_sink_is_reused_and_closed_on_reconfigure(self):
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            _is_user_authorized=lambda source: True,
        )
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        created = []

        class Sink:
            def __init__(self):
                self.closed = False

            def __call__(self, receipt):
                self_receipts.append(receipt)

            def close(self):
                self.closed = True

        def factory(policy_loader):
            sink = Sink()
            created.append(sink)
            return sink

        def suppress(projection, classifier):
            trigger = projection["trigger_event_id"]
            return {
                "disposition": "SUPPRESS",
                "reasons": ["no contribution is useful"],
                "evidence_event_ids": [trigger],
                "legacy_verdict_confidences": {
                    "PASS": 0.99,
                    "ACK": 0.0,
                    "ASK": 0.0,
                    "SPEAK": 0.01,
                },
            }

        self_receipts = self.receipts
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=suppress,
            receipt_sink_factory=factory,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )
        for message_id in range(200, 220):
            result = v2_plugin.on_pre_gateway_dispatch(
                event=self.hermes_event(str(message_id)), gateway=gateway
            )
            self.assertEqual(
                result, {"action": "skip", "reason": "nunchi:v2-attention"}
            )
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].closed)
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=suppress,
            receipt_sink_factory=factory,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )
        self.assertTrue(created[0].closed)

    def test_host_wrappers_attest_whole_terminal_output_after_all_sends(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event()
        gateway = _Gateway(SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001))))
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "1")
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)

        class Runner:
            def _adapter_for_source(self, source):
                return gateway.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _normalize_source_for_session_key(self, source):
                return source

            def _resolve_session_agent_runtime(self, **kwargs):
                return "test-model", {"api_mode": "chat_completions"}

            async def _handle_message_with_agent(self, supplied_event, source, session_key, generation):
                self.assert_ticket_bound = controller._tool_session.get()
                return "I can help."

        class Adapter:
            def __init__(self):
                self._client = SimpleNamespace(user=SimpleNamespace(id=9001))

            async def _send_with_retry(self, content, **kwargs):
                self.stages_during_text_send = [
                    row["stage"] for row in self_receipts
                ]
                self.sent = content
                return True

            async def send_voice(self, **kwargs):
                self.stages_during_media_send = [
                    row["stage"] for row in self_receipts
                ]
                return SimpleNamespace(success=True)

            async def _process_message_background(self, supplied_event, session_key):
                self.response = await runner._handle_message_with_agent(
                    supplied_event, supplied_event.source, session_key, 1
                )
                await self._send_with_retry(self.response)
                await self.send_voice(audio_path="voice.mp3")
                self.stages_before_process_return = [
                    row["stage"] for row in self_receipts
                ]

        self_receipts = self.receipts

        v2_plugin.install_host_wrappers(runner_cls=Runner, adapter_cls=Adapter)
        runner = Runner()
        adapter = Adapter()
        gateway.adapter = adapter

        asyncio.run(
            adapter._process_message_background(
                event, "agent:default:discord:42"
            )
        )
        self.assertEqual(adapter.response, "I can help.")
        self.assertEqual(runner.assert_ticket_bound, "agent:default:discord:42")
        self.assertEqual(adapter.sent, "I can help.")
        self.assertEqual(
            adapter.stages_during_text_send,
            ["observation", "attention", "participant-host"],
        )
        self.assertEqual(
            adapter.stages_during_media_send,
            ["observation", "attention", "participant-host"],
        )
        self.assertEqual(
            adapter.stages_before_process_return,
            ["observation", "attention", "participant-host"],
        )
        self.assertEqual(
            [row["stage"] for row in self.receipts],
            ["observation", "attention", "participant-host", "transport"],
        )

    def test_host_wrappers_block_preparticipant_platform_output(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("299")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "299")
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)

        class Adapter:
            def __init__(self):
                self.platform_calls = 0

            async def send(self, *args, **kwargs):
                self.platform_calls += 1
                return SimpleNamespace(success=True)

            async def _process_message_background(self, supplied_event, session_key):
                await runner._handle_message_with_agent(
                    supplied_event, supplied_event.source, session_key, 1
                )

        adapter = Adapter()

        class Runner:
            async def _handle_message_with_agent(
                self, supplied_event, source, session_key, generation
            ):
                await adapter.send(content="interim output")
                return "final output"

        v2_plugin.install_host_wrappers(runner_cls=Runner, adapter_cls=Adapter)
        runner = Runner()
        with self.assertRaises(v2_plugin.HermesV2BoundaryError):
            asyncio.run(
                adapter._process_message_background(
                    event, "agent:default:discord:42"
                )
            )
        self.assertEqual(adapter.platform_calls, 0)
        self.assertEqual(
            [row["stage"] for row in self.receipts],
            ["observation", "attention", "participant-host"],
        )
        self.assertEqual(self.receipts[-1]["body"]["outcome"], "unknown")

    def test_preparticipant_process_cancellation_closes_all_staged_state(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("2981")
        stage_adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        stage_gateway = SimpleNamespace(
            _adapter_for_source=lambda source: stage_adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
        )
        result = controller.process_delivery(
            event=event,
            gateway=stage_gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "2981")
        pending_result = controller.process_delivery(
            event=self.hermes_event("2982"),
            gateway=stage_gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: self.fail(
                "pending work must not be evaluated during host cancellation"
            ),
        )
        self.assertEqual(pending_result.status, "observed")
        self.assertEqual(
            result.evaluation.binding.scheduler.snapshot()[0]["pending_anchor_event_id"],
            "discord:message:2982",
        )
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        started = asyncio.Event()
        blocked = asyncio.Event()

        class Gateway:
            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            async def handle(self, supplied_event):
                return None

        gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._message_handler = gateway.handle

            async def _process_message_background(self, supplied_event, session_key):
                started.set()
                await blocked.wait()

        v2_plugin.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurn", (), {}), adapter_cls=Adapter
        )

        async def cancel_before_participant():
            task = asyncio.create_task(
                Adapter()._process_message_background(
                    event, "agent:default:discord:42"
                )
            )
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(cancel_before_participant())

        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertFalse(
            controller.tickets.has_dispatch(
                "discord:message:2981", "agent:default:discord:42"
            )
        )
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})
        self.assertEqual(
            [row["stage"] for row in self.receipts],
            ["observation", "attention", "participant-host"],
        )
        self.assertFalse(self.receipts[-1]["body"]["invoked"])
        self.assertEqual(self.receipts[-1]["body"]["outcome"], "unknown")

    def test_preparticipant_cleanup_does_not_abort_promoted_generation(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        session_key = "agent:default:discord:42"

        class Gateway:
            def __init__(self):
                self.adapter: Any = SimpleNamespace(
                    _client=SimpleNamespace(user=SimpleNamespace(id=9001))
                )

            def _adapter_for_source(self, source):
                return self.adapter

            def _session_key_for_source(self, source):
                return session_key

            async def handle(self, supplied_event):
                return None

        gateway = Gateway()
        classifier_calls = []

        def classify(projection, classifier):
            classifier_calls.append(projection["trigger_event_id"])
            return {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            }

        common = {
            "gateway": gateway,
            "session_key": session_key,
            "participant_id": "resident",
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
            "classifier_transport": classify,
        }
        first = controller.process_delivery(event=self.hermes_event("2983"), **common)
        pending = controller.process_delivery(event=self.hermes_event("2984"), **common)
        self.assertEqual((first.status, pending.status), ("wake", "observed"))
        self.activate_turn(controller, "2983", session_key)
        self.assertEqual(first.evaluation.opportunity.generation, 1)

        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)

        class Adapter:
            def __init__(self):
                self._message_handler = gateway.handle
                self.promoted_on_return = None

            async def _process_message_background(self, supplied_event, supplied_session):
                controller.complete_participant_turn(session_key, "first")
                await asyncio.to_thread(
                    controller.complete_transport,
                    session_key,
                    delivery="sent",
                )
                self.promoted_on_return = controller._turns.get(session_key)

        v2_plugin.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurn", (), {}), adapter_cls=Adapter
        )
        adapter = Adapter()
        gateway.adapter = adapter
        asyncio.run(
            adapter._process_message_background(
                self.hermes_event("2983"), session_key
            )
        )

        self.assertIsNotNone(adapter.promoted_on_return)
        self.assertEqual(adapter.promoted_on_return.opportunity.generation, 2)
        self.assertIs(controller._turns.get(session_key), adapter.promoted_on_return)
        self.activate_turn(controller, "2984", session_key)
        self.assertTrue(controller.is_ticketed(session_key))
        self.assertEqual(
            classifier_calls,
            ["discord:message:2983", "discord:message:2984"],
        )

    def test_deferred_transport_cleanup_cannot_finish_promoted_generation(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        session_key = "agent:default:discord:42"

        class Gateway:
            def __init__(self):
                self.adapter: Any = SimpleNamespace(
                    _client=SimpleNamespace(user=SimpleNamespace(id=9001))
                )

            def _adapter_for_source(self, source):
                return self.adapter

            async def handle(self, supplied_event):
                return None

        gateway = Gateway()
        classify = lambda projection, classifier: {
            "disposition": "WAKE",
            "reasons": ["the participant may contribute"],
            "evidence_event_ids": [projection["trigger_event_id"]],
        }
        common = {
            "gateway": gateway,
            "session_key": session_key,
            "participant_id": "resident",
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
            "classifier_transport": classify,
        }
        first = controller.process_delivery(event=self.hermes_event("29831"), **common)
        pending = controller.process_delivery(event=self.hermes_event("29832"), **common)
        self.assertEqual((first.status, pending.status), ("wake", "observed"))
        self.activate_turn(controller, "29831", session_key)

        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)

        class Adapter:
            def __init__(self):
                self._message_handler = gateway.handle
                self.promoted = None

            async def send(self, **kwargs):
                return SimpleNamespace(success=True)

            async def _process_message_background(self, supplied_event, supplied_session):
                controller.complete_participant_turn(session_key, "first")
                controller.set_transport_session(session_key)
                await self.send(content="first")
                await asyncio.to_thread(
                    controller._finish_turn,
                    session_key,
                    first.evaluation,
                    promote_pending=True,
                )
                self.promoted = controller._turns.get(session_key)

        v2_plugin.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurn", (), {}), adapter_cls=Adapter
        )
        adapter = Adapter()
        gateway.adapter = adapter
        asyncio.run(
            adapter._process_message_background(
                self.hermes_event("29831"), session_key
            )
        )

        promoted = adapter.promoted
        self.assertIsNotNone(promoted)
        assert promoted is not None
        self.assertEqual(promoted.opportunity.generation, 2)
        self.assertIs(controller._turns.get(session_key), promoted)
        self.activate_turn(controller, "29832", session_key)
        self.assertTrue(controller.is_ticketed(session_key))
        promoted_event = promoted.packet["trigger_event_id"]
        self.assertFalse(
            any(
                receipt["stage"] == "participant-transport"
                and receipt["trigger_event_id"] == promoted_event
                for receipt in self.receipts
            )
        )

    def test_cancelled_attention_executor_cannot_stage_or_redispatch_late(self):
        classifier_started = threading.Event()
        classifier_release = threading.Event()
        worker_done = threading.Event()
        self.addCleanup(classifier_release.set)
        redispatched = []
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }

        def classify(projection, classifier):
            classifier_started.set()
            if not classifier_release.wait(timeout=2):
                raise RuntimeError("classifier release barrier timed out")
            return {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            }

        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=classify,
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: (
                redispatched.append(supplied_event.message_id)
            ),
        )
        controller = v2_plugin._CONTROLLER
        original_evaluate = controller.evaluate_delivery

        def tracked_evaluate(accepted, **kwargs):
            try:
                return original_evaluate(accepted, **kwargs)
            finally:
                worker_done.set()

        controller.evaluate_delivery = tracked_evaluate
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001)),
            _background_tasks=set(),
        )
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            _is_user_authorized=lambda source: True,
        )
        event = self.hermes_event("2985")

        async def cancel_worker_then_release():
            result = v2_plugin.on_pre_gateway_dispatch(event=event, gateway=gateway)
            self.assertEqual(result["reason"], "nunchi:v2-attention")
            started = await asyncio.to_thread(classifier_started.wait, 1)
            self.assertTrue(started)
            self.assertEqual(len(adapter._background_tasks), 1)
            future = next(iter(adapter._background_tasks))
            self.assertTrue(future.cancel())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertIn(future, adapter._background_tasks)
            self.assertFalse(future.done())
            self.assertTrue(future.cancel())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertIn(future, adapter._background_tasks)
            self.assertFalse(future.done())
            classifier_release.set()
            finished = await asyncio.to_thread(worker_done.wait, 1)
            self.assertTrue(finished)
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        asyncio.run(cancel_worker_then_release())

        self.assertEqual(redispatched, [])
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertFalse(
            controller.tickets.has_dispatch(
                "discord:message:2985", "agent:default:discord:42"
            )
        )
        key = v2.resolve_binding_key(event, gateway)
        binding = controller.registry.get_or_create(key)
        self.assertEqual(binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})
        self.assertEqual(adapter._background_tasks, set())

    def test_control_output_barrier_precedes_concurrent_first_stage(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        session_key = "agent:default:discord:42"
        event = self.hermes_event("2986")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        accepted = controller.accept_delivery(
            event=event,
            gateway=gateway,
            session_key=session_key,
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        evaluation = controller.evaluate_opportunity(
            binding=accepted.binding,
            opportunity=accepted.opportunity,
            policy_loader=accepted.host.policy_loader,
            receipt_sink=accepted.host.receipt_sink,
            classifier_transport=accepted.host.classifier_transport,
        )

        acquired, active = controller.begin_control_output(session_key)
        self.assertTrue(acquired)
        self.assertIsNone(active)
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError, "control output"
        ):
            controller.stage_turn(
                evaluation=evaluation,
                session_key=session_key,
            )
        controller.finish_control_output(session_key)
        controller.stage_turn(evaluation=evaluation, session_key=session_key)
        self.activate_turn(controller, "2986", session_key)
        self.assertTrue(controller.is_ticketed(session_key))

    def test_active_ticket_is_closed_before_plaintext_command_output(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("2991")
        stage_adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: stage_adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
        )
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        successor_packet = dict(result.evaluation.packet)
        successor_packet["trigger_event_id"] = "discord:message:2993"
        successor = replace(result.evaluation, packet=successor_packet)
        command = self.hermes_event("2992")
        command.text = "/status"
        command.get_command = lambda: "status"
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        platform_output = []
        stage_errors = []

        class Gateway:
            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            async def handle(self, supplied_event):
                return None

        command_gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._message_handler = command_gateway.handle
                self.ticketed_during_command = None

            async def handle_message(self, supplied_event):
                try:
                    controller.stage_turn(
                        evaluation=successor,
                        session_key="agent:default:discord:42",
                    )
                except v2_plugin.HermesV2BoundaryError as exc:
                    stage_errors.append(str(exc))
                self.ticketed_during_command = controller.is_ticketed(
                    "agent:default:discord:42"
                )
                await self._send_with_retry(content="STATUS-LEAK")
                raise RuntimeError("control output failed after send")

            async def _send_with_retry(self, **kwargs):
                platform_output.append(kwargs["content"])
                return SimpleNamespace(success=True)

            async def _process_message_background(self, supplied_event, session_key):
                return None

        v2_plugin.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurn", (), {}), adapter_cls=Adapter
        )
        adapter = Adapter()
        with self.assertRaisesRegex(RuntimeError, "control output failed"):
            asyncio.run(adapter.handle_message(command))

        self.assertFalse(adapter.ticketed_during_command)
        self.assertEqual(len(stage_errors), 1)
        self.assertIn("control output", stage_errors[0])
        self.assertEqual(platform_output, ["STATUS-LEAK"])
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertFalse(
            controller.tickets.has_dispatch(
                "discord:message:2991", "agent:default:discord:42"
            )
        )
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})
        self.assertEqual(
            [row["stage"] for row in self.receipts],
            ["observation", "attention", "participant-host"],
        )
        self.assertFalse(self.receipts[-1]["body"]["invoked"])
        ticket = controller.stage_turn(
            evaluation=successor,
            session_key="agent:default:discord:42",
        )
        self.assertEqual(ticket.event_id, "discord:message:2993")

    def test_raw_discord_retention_rechecks_canonical_gateway_authorization(self):
        event = self.hermes_event("2996")
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            _is_user_authorized=lambda source: object(),
        )
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=lambda projection, classifier: self.fail(
                "canonically unauthorized raw text reached classifier context"
            ),
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )

        v2_plugin._retain_transport_context(event, gateway)

        self.assertEqual(len(v2_plugin._CONTROLLER.registry), 0)
        self.assertEqual(self.receipts, [])

    def test_raw_discord_self_context_uses_authenticated_self_binding(self):
        class FakeDMChannel:
            pass

        class FakeThread:
            pass

        discord_module = SimpleNamespace(DMChannel=FakeDMChannel, Thread=FakeThread)
        self_user = SimpleNamespace(id=9001, bot=True, display_name="Hermes")
        channel = SimpleNamespace(id=42, name="room")
        message = SimpleNamespace(
            id=3101,
            author=self_user,
            channel=channel,
            guild=SimpleNamespace(id=7),
            content="self output",
            reference=None,
            created_at=None,
        )

        class Adapter:
            def __init__(self):
                self._client = SimpleNamespace(user=self_user)

            def _get_parent_channel_id(self, supplied_channel):
                return None

            def build_source(self, **kwargs):
                return SimpleNamespace(
                    profile="default",
                    platform=_Platform("discord"),
                    **kwargs,
                )

        adapter = Adapter()
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            _is_user_authorized=lambda source: (
                os.getenv("DISCORD_ALLOW_BOTS", "none") in {"mentions", "all"}
                if source.is_bot
                else getattr(source, "role_authorized", False) is True
            ),
        )
        event = v2_plugin._discord_context_event(adapter, message, discord_module)
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
        )
        with unittest.mock.patch.dict(
            os.environ, {"DISCORD_ALLOW_BOTS": "none"}
        ):
            v2_plugin._retain_transport_context(event, gateway)
        self.assertIs(getattr(event, "_nunchi_authenticated_self", None), True)
        self.assertEqual(len(v2_plugin._CONTROLLER.registry), 1)
        binding = next(iter(v2_plugin._CONTROLLER.registry._bindings.values()))
        self.assertEqual(binding.export_context()[-1]["event"]["text"], "self output")

    def test_raw_discord_role_context_carries_adapter_attestation(self):
        class FakeDMChannel:
            pass

        class FakeThread:
            pass

        discord_module = SimpleNamespace(DMChannel=FakeDMChannel, Thread=FakeThread)
        self_user = SimpleNamespace(id=9001, bot=True, display_name="Hermes")
        author = SimpleNamespace(id=1001, bot=False, display_name="Role User")
        channel = SimpleNamespace(id=42, name="room")
        message = SimpleNamespace(
            id=3102,
            author=author,
            channel=channel,
            guild=SimpleNamespace(id=7),
            content="role-only context",
            reference=None,
            created_at=None,
        )

        class Adapter:
            def __init__(self):
                self._client = SimpleNamespace(user=self_user)
                self._allowed_role_ids = {5555}

            def _get_parent_channel_id(self, supplied_channel):
                return None

            def _is_allowed_user(self, *args, **kwargs):
                return True

            def build_source(self, **kwargs):
                return SimpleNamespace(
                    profile="default",
                    platform=_Platform("discord"),
                    **kwargs,
                )

        adapter = Adapter()
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            _is_user_authorized=lambda source: (
                getattr(source, "role_authorized", False) is True
            ),
        )
        event = v2_plugin._discord_context_event(adapter, message, discord_module)
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
        )
        v2_plugin._retain_transport_context(event, gateway)
        self.assertIs(event.source.role_authorized, True)
        self.assertEqual(len(v2_plugin._CONTROLLER.registry), 1)
        binding = next(iter(v2_plugin._CONTROLLER.registry._bindings.values()))
        self.assertEqual(
            binding.export_context()[-1]["event"]["text"], "role-only context"
        )

    def test_raw_discord_dispatch_rejects_before_scheduling_retention(self):
        class FakeDMChannel:
            pass

        class FakeThread:
            pass

        discord_module = SimpleNamespace(
            DMChannel=FakeDMChannel,
            Thread=FakeThread,
            MessageType=SimpleNamespace(default="default", reply="reply"),
        )

        class Bot:
            def __init__(self):
                self.user = SimpleNamespace(id=9001)

            def dispatch(self, event_name, *args, **kwargs):
                return None

        class Gateway:
            def __init__(self):
                self.adapter: Any = None

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _is_user_authorized(self, source):
                return False

            async def handle(self, event):
                return None

        gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._client = Bot()
                self._message_handler = gateway.handle
                self._threads = set()
                self._background_tasks = set()

            async def _handle_message(self, message):
                return None

            def build_source(self, **kwargs):
                return SimpleNamespace(
                    profile="default",
                    platform=_Platform("discord"),
                    chat_id=kwargs["chat_id"],
                    parent_chat_id=kwargs.get("parent_chat_id"),
                    thread_id=kwargs.get("thread_id"),
                    user_id=kwargs.get("user_id"),
                    user_name=kwargs.get("user_name"),
                    is_bot=kwargs.get("is_bot", False),
                )

            def _is_allowed_user(self, user_id, author, **kwargs):
                return True

            def _self_is_explicitly_mentioned(self, message):
                return False

            def _get_parent_channel_id(self, channel):
                return None

            def _discord_channel_keys(self, message, parent_channel_id=None):
                return {str(message.channel.id)}

            def _discord_free_response_channels(self):
                return set()

            def _discord_require_mention(self):
                return True

            def _discord_thread_require_mention(self):
                return False

            def _discord_bots_require_inline_mention(self):
                return False

        self.assertTrue(
            v2_plugin.install_discord_raw_observer(
                adapter_cls=Adapter,
                bot_cls=Bot,
                discord_module=discord_module,
            )
        )
        adapter = Adapter()
        gateway.adapter = adapter
        guild = SimpleNamespace(id=7, name="guild")
        message = SimpleNamespace(
            id=2997,
            author=SimpleNamespace(
                id=1001, display_name="Zoe", name="Zoe", bot=False
            ),
            channel=SimpleNamespace(id=42, name="shared", guild=guild),
            guild=guild,
            content="<@8000> thoughts?",
            mentions=[SimpleNamespace(id=8000, bot=True)],
            mention_everyone=False,
            reference=None,
            created_at=None,
            type="default",
        )

        async def dispatch_and_drain():
            adapter._client.dispatch("message", message)
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        with unittest.mock.patch.dict(
            os.environ,
            {
                "DISCORD_ALLOWED_CHANNELS": "*",
                "DISCORD_IGNORED_CHANNELS": "",
                "DISCORD_IGNORE_NO_MENTION": "true",
            },
        ), unittest.mock.patch.object(
            v2_plugin, "_retain_transport_context"
        ) as retained:
            asyncio.run(dispatch_and_drain())

        retained.assert_not_called()
        self.assertEqual(adapter._background_tasks, set())
        self.assertIsNone(getattr(adapter, "_nunchi_v2_raw_tail", None))

    def test_raw_discord_wrapper_reregistration_uses_current_module_once(self):
        native_dispatches = []

        class Bot:
            def dispatch(self, event_name, *args, **kwargs):
                native_dispatches.append(event_name)

        class Adapter:
            def __init__(self):
                self._client = Bot()
                self._background_tasks = set()

            def _discord_free_response_channels(self):
                return set()

            async def _handle_message(self, message):
                return None

        first_module = SimpleNamespace(name="first")
        current_module = SimpleNamespace(name="current")
        self.assertTrue(
            v2_plugin.install_discord_raw_observer(
                adapter_cls=Adapter,
                bot_cls=Bot,
                discord_module=first_module,
            )
        )
        self.assertTrue(
            v2_plugin.install_discord_raw_observer(
                adapter_cls=Adapter,
                bot_cls=Bot,
                discord_module=current_module,
            )
        )
        adapter = Adapter()
        seen_modules = []

        async def dispatch_once():
            with unittest.mock.patch.object(
                v2_plugin,
                "_discord_message_should_be_context",
                side_effect=lambda owner, message, module: (
                    seen_modules.append(module) or False
                ),
            ):
                adapter._client.dispatch(
                    "message", SimpleNamespace(content="context")
                )
                await asyncio.sleep(0)

        asyncio.run(dispatch_once())

        self.assertEqual(seen_modules, [current_module])
        self.assertEqual(native_dispatches, ["message"])

    def test_host_wrapper_reload_rebinds_current_module_and_controller(self):
        module_a = _load_fresh_plugin_module("nunchi_hermes_v2_plugin_reload_a")
        module_b = _load_fresh_plugin_module("nunchi_hermes_v2_plugin_reload_b")
        self.addCleanup(sys.modules.pop, module_a.__name__, None)
        self.addCleanup(sys.modules.pop, module_b.__name__, None)

        class ControllerSpy:
            def __init__(self, suppress=False):
                self.asserted = 0
                self.recorded = 0
                self.telemetry = 0
                self.suppress = suppress

            def assert_terminal_output_allowed(self):
                self.asserted += 1

            def record_output_attempt(self, **kwargs):
                self.recorded += 1

            def suppress_host_telemetry(self):
                self.telemetry += 1
                return self.suppress

        controller_a = ControllerSpy(suppress=False)
        controller_b = ControllerSpy(suppress=True)
        module_a._CONTROLLER = controller_a
        module_b._CONTROLLER = controller_b
        busy_modules = []
        module_a._gateway_for_adapter = lambda adapter: (
            busy_modules.append("a") or None
        )
        module_b._gateway_for_adapter = lambda adapter: (
            busy_modules.append("b") or None
        )
        native = []

        class Adapter:
            async def _process_message_background(self, event, session_key):
                native.append("process")

            async def send(self, *args, **kwargs):
                native.append("send")
                return True

            async def send_typing(self, *args, **kwargs):
                native.append("typing")
                return True

            def set_busy_session_handler(self, handler):
                self.busy_handler = handler

        first = module_a.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurnA", (), {}), adapter_cls=Adapter
        )
        second = module_b.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurnB", (), {}), adapter_cls=Adapter
        )
        self.assertTrue(first["transport"])
        self.assertTrue(second["transport"])
        self.assertEqual(Adapter.send.__module__, module_b.__name__)
        self.assertEqual(Adapter.send_typing.__module__, module_b.__name__)
        self.assertEqual(
            Adapter.set_busy_session_handler.__module__, module_b.__name__
        )

        async def exercise():
            adapter = Adapter()
            self.assertTrue(await adapter.send(content="hello"))
            self.assertIsNone(await adapter.send_typing())
            async def fallback_handler(event, session):
                return False

            adapter.set_busy_session_handler(fallback_handler)
            self.assertFalse(await adapter.busy_handler(object(), "session"))

        asyncio.run(exercise())
        self.assertEqual(controller_a.asserted, 0)
        self.assertEqual(controller_a.recorded, 0)
        self.assertEqual(controller_a.telemetry, 0)
        self.assertEqual(controller_b.asserted, 1)
        self.assertEqual(controller_b.recorded, 1)
        self.assertEqual(controller_b.telemetry, 1)
        self.assertEqual(busy_modules, ["b"])
        self.assertEqual(native, ["send"])

    def test_telegram_wrapper_reload_uses_current_module_globals(self):
        module_a = _load_fresh_plugin_module("nunchi_hermes_v2_plugin_telegram_a")
        module_b = _load_fresh_plugin_module("nunchi_hermes_v2_plugin_telegram_b")
        self.addCleanup(sys.modules.pop, module_a.__name__, None)
        self.addCleanup(sys.modules.pop, module_b.__name__, None)
        scope_modules = []
        module_a._gateway_for_adapter = lambda adapter: object()
        module_b._gateway_for_adapter = lambda adapter: object()
        module_a._event_in_scope = lambda event, gateway: (
            scope_modules.append("a") or False
        )
        module_b._event_in_scope = lambda event, gateway: (
            scope_modules.append("b") or True
        )
        native = []
        exact = []

        class Adapter:
            def __init__(self):
                self._background_tasks = set()

            def _enqueue_text_event(self, event):
                native.append(event)

            async def handle_message(self, event):
                exact.append(event)
                return True

        self.assertTrue(module_a.install_telegram_exact_text(Adapter))
        self.assertTrue(module_b.install_telegram_exact_text(Adapter))
        self.assertEqual(Adapter._enqueue_text_event.__module__, module_b.__name__)
        event = object()

        async def exercise():
            adapter = Adapter()
            adapter._enqueue_text_event(event)
            await asyncio.gather(*tuple(adapter._background_tasks))

        asyncio.run(exercise())
        self.assertEqual(scope_modules, ["b"])
        self.assertEqual(native, [])
        self.assertEqual(exact, [event])

    def test_native_discord_control_closes_ticket_before_direct_interaction_output(self):
        self.assertTrue(hasattr(v2_plugin, "install_discord_control_guard"))
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("2993")
        stage_adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=9001))
        )
        stage_gateway = SimpleNamespace(
            _adapter_for_source=lambda source: stage_adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
        )
        result = controller.process_delivery(
            event=event,
            gateway=stage_gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        successor_packet = dict(result.evaluation.packet)
        successor_packet["trigger_event_id"] = "discord:message:2995"
        successor = replace(result.evaluation, packet=successor_packet)
        command = self.hermes_event("2994")
        command.text = "/status"
        command.get_command = lambda: "status"
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        interaction_output = []
        stage_errors = []

        class Gateway:
            def __init__(self):
                self.adapter: Any = None

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            async def handle(self, supplied_event):
                return None

        gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._message_handler = gateway.handle

            def _build_slash_event(self, interaction, command_text):
                return command

            def _evaluate_slash_authorization(self, interaction):
                return True, None

            async def _check_slash_authorization(self, interaction, command_text):
                try:
                    controller.stage_turn(
                        evaluation=successor,
                        session_key="agent:default:discord:42",
                    )
                except v2_plugin.HermesV2BoundaryError as exc:
                    stage_errors.append(str(exc))
                interaction_output.append(
                    controller.is_ticketed("agent:default:discord:42")
                )
                return True

        self.assertTrue(v2_plugin.install_discord_control_guard(Adapter))
        adapter = Adapter()
        gateway.adapter = adapter
        self.assertTrue(
            asyncio.run(adapter._check_slash_authorization(object(), "/status"))
        )

        self.assertEqual(interaction_output, [False])
        self.assertEqual(len(stage_errors), 1)
        self.assertIn("control output", stage_errors[0])
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(result.evaluation.binding.scheduler.snapshot(), ())
        self.assertEqual(controller._host_deliveries, {})
        self.assertEqual(
            [row["stage"] for row in self.receipts],
            ["observation", "attention", "participant-host"],
        )
        ticket = controller.stage_turn(
            evaluation=successor,
            session_key="agent:default:discord:42",
        )
        self.assertEqual(ticket.event_id, "discord:message:2995")

    def test_native_discord_unauthorized_reject_emits_nothing_during_active_ticket(self):
        controller, binding, opportunity = self.binding_and_opportunity()
        evaluation = controller.evaluate_opportunity(
            binding=binding,
            opportunity=opportunity,
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        controller.stage_turn(
            evaluation=evaluation, session_key="agent:default:discord:42"
        )
        self.activate_turn(controller, "1")
        command = self.hermes_event("2995")
        command.text = "/status"
        command.get_command = lambda: "status"
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        interaction_output = []

        class Gateway:
            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            async def handle(self, supplied_event):
                return None

        gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._message_handler = gateway.handle

            def _build_slash_event(self, interaction, command_text):
                return command

            def _evaluate_slash_authorization(self, interaction):
                return False, "unauthorized"

            async def _check_slash_authorization(self, interaction, command_text):
                interaction_output.append("UNAUTHORIZED-LEAK")
                return False

        self.assertTrue(v2_plugin.install_discord_control_guard(Adapter))
        allowed = asyncio.run(
            Adapter()._check_slash_authorization(object(), "/status")
        )

        self.assertFalse(allowed)
        self.assertEqual(interaction_output, [])
        self.assertTrue(controller.is_ticketed("agent:default:discord:42"))
        self.assertEqual(
            [row["stage"] for row in self.receipts],
            ["observation", "attention"],
        )

    def test_host_runtime_scope_requires_effect_middleware_and_streaming_rails(self):
        event = self.hermes_event("300")
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        self.assertTrue(v2_plugin._config_in_scope(config, event))
        for key in ("_host_streaming_disabled", "_host_effect_runtime_supported"):
            unsupported = dict(config)
            unsupported[key] = False
            self.assertFalse(v2_plugin._config_in_scope(unsupported, event))

    def test_scoped_discord_auto_thread_continues_in_parent_without_error(self):
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )

        class Gateway:
            def __init__(self):
                self.adapter: Any = None

            def _adapter_for_source(self, source):
                return self.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _is_user_authorized(self, source):
                return True

            async def handle(self, event):
                return True

        gateway = Gateway()
        bot_user = SimpleNamespace(id=9001, bot=True)
        sent = []

        class Channel:
            id = 42
            name = "room"

            async def send(self, content):
                sent.append(content)

        class Bot:
            def dispatch(self, event_name, *args, **kwargs):
                return None

        class Adapter:
            def __init__(self):
                self._client = SimpleNamespace(user=bot_user)
                self._message_handler = gateway.handle
                self.auto_thread_calls = 0
                self.processed = False
                self.raw_ready = False
                self.raw_completed_before_handle = False
                self._nunchi_v2_raw_tail: Any = None

            def _discord_free_response_channels(self):
                return set()

            def build_source(self, **kwargs):
                return SimpleNamespace(
                    profile="default",
                    platform=_Platform("discord"),
                    chat_id=kwargs["chat_id"],
                    thread_id=kwargs["thread_id"],
                    user_id=kwargs["user_id"],
                    user_name=kwargs["user_name"],
                    is_bot=kwargs["is_bot"],
                )

            def _self_is_explicitly_mentioned(self, message):
                return True

            async def _auto_create_thread(self, message):
                self.auto_thread_calls += 1
                return None

            async def _handle_message(self, message):
                self.raw_completed_before_handle = self.raw_ready
                is_free = str(message.channel.id) in self._discord_free_response_channels()
                if not is_free:
                    thread = await self._auto_create_thread(message)
                    if thread is None:
                        await message.channel.send("could not create a Discord thread")
                        return None
                message.content = "normalized"
                self.processed = True
                return True

        discord_module = SimpleNamespace(
            Thread=type("Thread", (), {}),
            DMChannel=type("DMChannel", (), {}),
        )
        self.assertTrue(
            v2_plugin.install_discord_raw_observer(
                adapter_cls=Adapter,
                bot_cls=Bot,
                discord_module=discord_module,
            )
        )
        adapter = Adapter()
        gateway.adapter = adapter
        message = SimpleNamespace(
            id=4001,
            content="<@9001> hello",
            author=SimpleNamespace(id=7, bot=False, display_name="A"),
            channel=Channel(),
            guild=SimpleNamespace(id=1),
            mentions=[bot_user],
            mention_everyone=False,
            reference=None,
            created_at=None,
        )
        async def exercise():
            async def finish_raw_retention():
                await asyncio.sleep(0)
                adapter.raw_ready = True

            adapter._nunchi_v2_raw_tail = asyncio.create_task(
                finish_raw_retention()
            )
            return await adapter._handle_message(message)

        self.assertTrue(asyncio.run(exercise()))
        self.assertEqual(adapter.auto_thread_calls, 0)
        self.assertEqual(sent, [])
        self.assertTrue(adapter.processed)
        self.assertTrue(adapter.raw_completed_before_handle)
        self.assertEqual(message._nunchi_v2_raw_content, "<@9001> hello")

    def test_scoped_preattention_suppresses_telemetry_and_blocks_drafts(self):
        event = self.hermes_event("3001")
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }

        class Gateway:
            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            async def handle(self, supplied_event):
                return None

        gateway = Gateway()
        calls = []

        class Adapter:
            def __init__(self):
                self._message_handler = gateway.handle

            async def send_typing(self, *args, **kwargs):
                calls.append("typing")

            async def on_processing_start(self, *args, **kwargs):
                calls.append("reaction")

            async def play_ack_in_voice(self, *args, **kwargs):
                calls.append("voice-ack")

            async def send_draft(self, *args, **kwargs):
                calls.append("draft")
                return True

            async def send_clarify(self, *args, **kwargs):
                calls.append("clarify")
                return "choice"

            async def _process_message_background(self, supplied_event, session_key):
                await self.send_typing("42")
                await self.on_processing_start(supplied_event)
                await self.play_ack_in_voice(1)
                with self_assert_raises(v2_plugin.HermesV2BoundaryError):
                    await self.send_draft("42", "draft")
                with self_assert_raises(v2_plugin.HermesV2BoundaryError):
                    await self.send_clarify("42", "choose")

        self_assert_raises = self.assertRaises
        previous = v2_plugin._CONTROLLER
        setattr(
            v2_plugin,
            "_CONTROLLER",
            v2_plugin.HermesV2Controller(participant_id="resident"),
        )
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )
        v2_plugin.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurn", (), {}), adapter_cls=Adapter
        )
        asyncio.run(
            Adapter()._process_message_background(
                event, "agent:default:discord:42"
            )
        )
        self.assertEqual(calls, [])

    def test_scoped_telegram_text_bypasses_lossy_batching(self):
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["telegram"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )

        class Gateway:
            async def handle(self, event):
                return True

        gateway = Gateway()
        source = SimpleNamespace(
            profile="default",
            platform=_Platform("telegram"),
            chat_id="42",
            thread_id=None,
        )
        event = SimpleNamespace(source=source, message_id="5001", text="part one")

        class Adapter:
            def __init__(self):
                self._message_handler = gateway.handle
                self._background_tasks = set()
                self.batched = []
                self.exact = []

            def _enqueue_text_event(self, supplied_event):
                self.batched.append(supplied_event)

            async def handle_message(self, supplied_event):
                self.exact.append(supplied_event)
                return True

        self.assertTrue(v2_plugin.install_telegram_exact_text(Adapter))
        adapter = Adapter()

        async def exercise():
            adapter._enqueue_text_event(event)
            await asyncio.gather(*tuple(adapter._background_tasks))

        asyncio.run(exercise())
        self.assertEqual(adapter.batched, [])
        self.assertEqual(adapter.exact, [event])

    def test_ticketed_participant_rechecks_host_configuration(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("3002")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "3002")
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        config["participant_id"] = "replacement"
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="replacement",
        )
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        invoked = []

        class Runner:
            async def _handle_message_with_agent(self, *args, **kwargs):
                invoked.append(True)
                return "must not run"

        v2_plugin.install_host_wrappers(
            runner_cls=Runner, adapter_cls=type("AdapterWithoutOutput", (), {})
        )
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError, "configured participant changed"
        ):
            asyncio.run(
                Runner()._handle_message_with_agent(
                    event, event.source, "agent:default:discord:42", 1
                )
            )
        self.assertEqual(invoked, [])
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))

    def test_participant_receipt_persistence_runs_off_event_loop(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("3003")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )

        def slow_sink(receipt):
            if receipt["stage"] == "participant-host":
                time.sleep(0.15)
            self.receipts.append(receipt)

        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=slow_sink,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "3003")
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)

        class Runner:
            def _adapter_for_source(self, source):
                return gateway.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _normalize_source_for_session_key(self, source):
                return source

            def _resolve_session_agent_runtime(self, **kwargs):
                return "test-model", {"api_mode": "chat_completions"}

            async def _handle_message_with_agent(self, *args, **kwargs):
                return "hello"

        v2_plugin.install_host_wrappers(
            runner_cls=Runner, adapter_cls=type("AdapterWithoutOutput", (), {})
        )

        async def exercise():
            timer_fired = asyncio.Event()
            asyncio.get_running_loop().call_later(0.01, timer_fired.set)
            turn = asyncio.create_task(
                Runner()._handle_message_with_agent(
                    event, event.source, "agent:default:discord:42", 1
                )
            )
            await asyncio.wait_for(timer_fired.wait(), timeout=0.05)
            self.assertFalse(turn.done())
            self.assertEqual(await turn, "hello")

        asyncio.run(exercise())
        controller.complete_transport(
            "agent:default:discord:42", delivery="sent"
        )

    def test_ticketed_participant_rejects_per_session_codex_runtime(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("3004")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
        self.assertEqual(result.status, "wake")
        self.activate_turn(controller, "3004")
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
        )
        previous = v2_plugin._CONTROLLER
        setattr(v2_plugin, "_CONTROLLER", controller)
        self.addCleanup(setattr, v2_plugin, "_CONTROLLER", previous)
        invoked = []

        class Runner:
            def _adapter_for_source(self, source):
                return gateway.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _normalize_source_for_session_key(self, source):
                return source

            def _resolve_session_agent_runtime(self, **kwargs):
                return "codex", {"api_mode": "codex_app_server"}

            async def _handle_message_with_agent(self, *args, **kwargs):
                invoked.append(True)
                return "must not run"

        v2_plugin.install_host_wrappers(
            runner_cls=Runner, adapter_cls=type("AdapterWithoutOutput", (), {})
        )
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError,
            "effective Hermes session runtime",
        ):
            asyncio.run(
                Runner()._handle_message_with_agent(
                    event, event.source, "agent:default:discord:42", 1
                )
            )
        self.assertEqual(invoked, [])
        self.assertFalse(controller.is_ticketed("agent:default:discord:42"))

    def test_ticketed_participant_rejects_policy_content_drift(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        event = self.hermes_event("3005")

        class Gateway:
            def __init__(self):
                self.adapter = SimpleNamespace(
                    _client=SimpleNamespace(user=SimpleNamespace(id=9001))
                )

            def _adapter_for_source(self, source):
                return self.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _normalize_source_for_session_key(self, source):
                return source

            def _resolve_session_agent_runtime(self, **kwargs):
                return "model", {"api_mode": "chat_completions"}

        gateway = Gateway()
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(self.policy_path),
            receipt_sink=self.receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
            policy_identity=str(self.policy_path),
        )
        self.assertEqual(result.status, "wake")
        changed = clone_policy()
        changed["attention"]["participant_id"] = "resident"
        changed["recoverability"]["participant_id"] = "resident"
        changed["recoverability"]["continuity_scope_id"] = self.key.continuity_scope_id
        changed["classifier"]["model"] = "replacement-model"
        write_policy(self.temporary.name, changed)
        config = {
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
        }
        with self.assertRaisesRegex(
            v2_plugin.HermesV2BoundaryError,
            "operator policy changed",
        ):
            controller.attest_participant_turn(
                session_key="agent:default:discord:42",
                event=event,
                source=event.source,
                gateway=gateway,
                config=config,
            )

    def test_busy_session_handler_retains_newest_without_hermes_queue(self):
        event_one = self.hermes_event("301")
        event_two = self.hermes_event("302")
        fallback_calls = []
        classifier_calls = []

        class Gateway:
            def __init__(self):
                self.adapter: Any = None

            def _adapter_for_source(self, source):
                return self.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _is_user_authorized(self, source):
                return True

            async def handle(self, event):
                return None

        gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._client = SimpleNamespace(user=SimpleNamespace(id=9001))
                self._message_handler = gateway.handle
                self._busy_session_handler = None

            def set_busy_session_handler(self, handler):
                self._busy_session_handler = handler

            async def _process_message_background(self, event, session_key):
                return None

            async def _send_with_retry(self, *args, **kwargs):
                return True

        gateway.adapter = Adapter()
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }

        def classify(projection, classifier):
            classifier_calls.append(projection["trigger_event_id"])
            return {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            }

        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=classify,
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )
        first = v2_plugin.on_pre_gateway_dispatch(
            event=event_one, gateway=gateway
        )
        self.assertEqual(
            first, {"action": "skip", "reason": "nunchi:v2-attention"}
        )
        v2_plugin.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurn", (), {}), adapter_cls=Adapter
        )

        async def fallback(event, session_key):
            fallback_calls.append((event.message_id, session_key))
            return False

        gateway.adapter.set_busy_session_handler(fallback)
        handled = asyncio.run(
            gateway.adapter._busy_session_handler(
                event_two, "agent:default:discord:42"
            )
        )
        self.assertTrue(handled)
        self.assertEqual(fallback_calls, [])
        self.assertEqual(classifier_calls, ["discord:message:301"])
        binding = v2_plugin._CONTROLLER.registry.get_or_create(
            v2.resolve_binding_key(event_two, gateway)
        )
        self.assertEqual(
            binding.scheduler.snapshot()[0]["pending_anchor_event_id"],
            "discord:message:302",
        )

    def test_busy_ticket_redispatch_waits_for_owner_and_runs_once(self):
        event = self.hermes_event("311")

        class Gateway:
            def __init__(self):
                self.adapter: Any = None

            def _adapter_for_source(self, source):
                return self.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _is_user_authorized(self, source):
                return True

            async def handle(self, supplied_event):
                return None

        gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._client = SimpleNamespace(user=SimpleNamespace(id=9001))
                self._message_handler = gateway.handle
                self._busy_session_handler = None
                self._session_tasks = {}
                self._background_tasks = set()
                self.redispatched = []

            def set_busy_session_handler(self, handler):
                self._busy_session_handler = handler

            async def handle_message(self, supplied_event):
                self.redispatched.append(supplied_event.message_id)

            async def _process_message_background(self, supplied_event, session_key):
                return None

            async def _send_with_retry(self, *args, **kwargs):
                return True

        gateway.adapter = Adapter()
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }
        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )
        self.assertEqual(
            v2_plugin.on_pre_gateway_dispatch(event=event, gateway=gateway),
            {"action": "skip", "reason": "nunchi:v2-attention"},
        )
        v2_plugin.install_host_wrappers(
            runner_cls=type("RunnerWithoutTurn", (), {}), adapter_cls=Adapter
        )
        gateway.adapter.set_busy_session_handler(None)

        async def exercise():
            owner = asyncio.get_running_loop().create_future()
            gateway.adapter._session_tasks["agent:default:discord:42"] = owner
            first = await gateway.adapter._busy_session_handler(
                event, "agent:default:discord:42"
            )
            second = await gateway.adapter._busy_session_handler(
                event, "agent:default:discord:42"
            )
            self.assertTrue(first)
            self.assertTrue(second)
            self.assertEqual(gateway.adapter.redispatched, [])
            owner.set_result(None)
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        asyncio.run(exercise())
        self.assertEqual(gateway.adapter.redispatched, ["311"])

    def test_raw_discord_filter_retains_self_and_peer_directed_context(self):
        class FakeDMChannel:
            pass

        class FakeThread:
            pass

        discord_module = SimpleNamespace(
            DMChannel=FakeDMChannel,
            Thread=FakeThread,
            MessageType=SimpleNamespace(default="default", reply="reply"),
        )

        class Bot:
            def __init__(self):
                self.user = SimpleNamespace(id=9001)
                self.dispatched = []

            def dispatch(self, event_name, *args, **kwargs):
                self.dispatched.append((event_name, args[0].id))

        class Gateway:
            def __init__(self):
                self.adapter: Any = None

            def _adapter_for_source(self, source):
                return self.adapter

            def _session_key_for_source(self, source):
                return "agent:default:discord:42"

            def _is_user_authorized(self, source):
                return True

            async def handle(self, event):
                return None

        gateway = Gateway()

        class Adapter:
            def __init__(self):
                self._client = Bot()
                self._message_handler = gateway.handle
                self._threads = set()
                self._background_tasks = set()

            async def _handle_message(self, message):
                return None

            def build_source(self, **kwargs):
                return SimpleNamespace(
                    profile="default",
                    platform=_Platform("discord"),
                    chat_id=kwargs["chat_id"],
                    parent_chat_id=kwargs.get("parent_chat_id"),
                    thread_id=kwargs.get("thread_id"),
                    user_id=kwargs.get("user_id"),
                    user_name=kwargs.get("user_name"),
                    is_bot=kwargs.get("is_bot", False),
                )

            def _is_allowed_user(self, user_id, author, **kwargs):
                return True

            def _self_is_explicitly_mentioned(self, message):
                return any(mention.id == 9001 for mention in message.mentions)

            def _get_parent_channel_id(self, channel):
                return None

            def _discord_channel_keys(self, message, parent_channel_id=None):
                return {str(message.channel.id)}

            def _discord_free_response_channels(self):
                return set()

            def _discord_require_mention(self):
                return True

            def _discord_thread_require_mention(self):
                return False

            def _discord_bots_require_inline_mention(self):
                return False

        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: {
                "enabled": True,
                "api_version": 2,
                "participant_id": "resident",
                "policy_path": str(self.policy_path),
                "platforms": ["discord"],
                "channels": ["42"],
                "streaming": False,
                "_host_streaming_disabled": True,
                "_host_effect_runtime_supported": True,
            },
            participant_id="resident",
            classifier_transport=lambda projection, classifier: self.fail(
                "raw context requested attention"
            ),
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )
        v2_plugin.install_discord_raw_observer(
            adapter_cls=Adapter,
            bot_cls=Bot,
            discord_module=discord_module,
        )
        gateway.adapter = Adapter()
        guild = SimpleNamespace(id=7, name="guild")
        channel = SimpleNamespace(id=42, name="shared", guild=guild)
        self_message = SimpleNamespace(
            id=401,
            author=SimpleNamespace(
                id=9001, display_name="Resident", name="Resident", bot=True
            ),
            channel=channel,
            guild=guild,
            content="I can help.",
            mentions=[],
            mention_everyone=False,
            reference=None,
            created_at=datetime(2026, 7, 20, 19, 1, tzinfo=timezone.utc),
            type="default",
        )
        peer_message = SimpleNamespace(
            id=402,
            author=SimpleNamespace(
                id=1001, display_name="Zoe", name="Zoe", bot=False
            ),
            channel=channel,
            guild=guild,
            content="<@8000> thoughts?",
            mentions=[SimpleNamespace(id=8000, bot=True)],
            mention_everyone=False,
            reference=None,
            created_at=datetime(2026, 7, 20, 19, 2, tzinfo=timezone.utc),
            type="default",
        )

        async def dispatch_and_drain():
            gateway.adapter._client.dispatch("message", self_message)
            gateway.adapter._client.dispatch("message", peer_message)
            await asyncio.sleep(0.05)

        with unittest.mock.patch.dict(
            os.environ,
            {
                "DISCORD_ALLOWED_CHANNELS": "*",
                "DISCORD_IGNORED_CHANNELS": "",
                "DISCORD_IGNORE_NO_MENTION": "true",
            },
        ):
            asyncio.run(dispatch_and_drain())
        key = v2.resolve_binding_key(
            SimpleNamespace(source=gateway.adapter.build_source(
                chat_id="42", user_id="1001", user_name="Zoe"
            )),
            gateway,
        )
        binding = v2_plugin._CONTROLLER.registry.get_or_create(key)
        self.assertEqual(
            [row["event"]["id"] for row in binding.export_context()],
            ["discord:message:401", "discord:message:402"],
        )
        self.assertEqual(gateway.adapter._background_tasks, set())
        self.assertIsNone(gateway.adapter._nunchi_v2_raw_tail)
        self.assertEqual(binding.scheduler.snapshot(), ())
        self.assertEqual(
            gateway.adapter._client.dispatched,
            [("message", 401), ("message", 402)],
        )

    def test_completed_turn_promotes_only_newest_busy_anchor(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001))))
        classifier_calls = []

        def classify(projection, classifier):
            classifier_calls.append(projection["trigger_event_id"])
            return {
                "disposition": "WAKE",
                "reasons": ["the participant may contribute"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            }

        kwargs = {
            "gateway": gateway,
            "session_key": "agent:default:discord:42",
            "participant_id": "resident",
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
            "classifier_transport": classify,
        }
        first = controller.process_delivery(event=self.hermes_event("1"), **kwargs)
        second = controller.process_delivery(event=self.hermes_event("2"), **kwargs)
        third = controller.process_delivery(event=self.hermes_event("3"), **kwargs)
        self.assertEqual((first.status, second.status, third.status), ("wake", "observed", "observed"))
        self.activate_turn(controller, "1")
        self.assertEqual(classifier_calls, ["discord:message:1"])
        controller.complete_participant_turn("agent:default:discord:42", "first")
        controller.complete_transport("agent:default:discord:42", delivery="sent")
        self.activate_turn(controller, "3")
        self.assertEqual(
            classifier_calls,
            ["discord:message:1", "discord:message:3"],
        )
        successor = controller.tickets.context_for_session("agent:default:discord:42")
        self.assertIn('"trigger_event_id": "discord:message:3"', successor)
        self.assertNotIn('"trigger_event_id": "discord:message:2"', successor)

    def test_completed_turn_promotes_slow_successor_off_event_loop(self):
        controller = v2_plugin.HermesV2Controller(participant_id="resident")
        gateway = _Gateway(
            SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        )
        successor_started = threading.Event()

        def classify(projection, classifier):
            trigger = projection["trigger_event_id"]
            if trigger == "discord:message:1":
                return {
                    "disposition": "WAKE",
                    "reasons": ["the participant may contribute"],
                    "evidence_event_ids": [trigger],
                }
            successor_started.set()
            time.sleep(0.25)
            return {
                "disposition": "SUPPRESS",
                "reasons": ["no contribution is useful"],
                "evidence_event_ids": [trigger],
                "legacy_verdict_confidences": {
                    "PASS": 0.99,
                    "ACK": 0.0,
                    "ASK": 0.0,
                    "SPEAK": 0.01,
                },
            }

        kwargs = {
            "gateway": gateway,
            "session_key": "agent:default:discord:42",
            "participant_id": "resident",
            "policy_loader": lambda: load_operator_policy(self.policy_path),
            "receipt_sink": self.receipts.append,
            "classifier_transport": classify,
        }
        self.assertEqual(
            controller.process_delivery(event=self.hermes_event("1"), **kwargs).status,
            "wake",
        )
        self.assertEqual(
            controller.process_delivery(event=self.hermes_event("2"), **kwargs).status,
            "observed",
        )
        controller.complete_participant_turn(
            "agent:default:discord:42", "first"
        )

        async def finish_transport():
            started = time.monotonic()
            controller.complete_transport(
                "agent:default:discord:42", delivery="sent"
            )
            return time.monotonic() - started

        elapsed = asyncio.run(finish_transport())
        self.assertLess(elapsed, 0.05)
        self.assertTrue(successor_started.wait(timeout=1.0))

    def test_dispatch_hook_keeps_slow_classifier_off_event_loop(self):
        event = self.hermes_event("91")
        adapter = SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
        gateway = SimpleNamespace(
            _adapter_for_source=lambda source: adapter,
            _session_key_for_source=lambda source: "agent:default:discord:42",
            _is_user_authorized=lambda source: True,
        )
        config = {
            "enabled": True,
            "api_version": 2,
            "participant_id": "resident",
            "policy_path": str(self.policy_path),
            "platforms": ["discord"],
            "channels": ["42"],
            "streaming": False,
            "_host_streaming_disabled": True,
            "_host_effect_runtime_supported": True,
        }

        def slow_classifier(projection, classifier):
            time.sleep(0.25)
            return {
                "disposition": "SUPPRESS",
                "reasons": ["no contribution is useful"],
                "evidence_event_ids": [projection["trigger_event_id"]],
                "legacy_verdict_confidences": {
                    "PASS": 0.99, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.01,
                },
            }

        v2_plugin.configure(
            config_loader=lambda supplied_event, supplied_gateway: config,
            participant_id="resident",
            classifier_transport=slow_classifier,
            receipt_sink_factory=lambda policy_loader: self.receipts.append,
            schedule_redispatch=lambda supplied_event, supplied_gateway: None,
        )

        async def invoke():
            loop = asyncio.get_running_loop()
            started = loop.time()
            result = v2_plugin.on_pre_gateway_dispatch(event=event, gateway=gateway)
            elapsed = loop.time() - started
            await asyncio.sleep(0.35)
            return result, elapsed

        result, elapsed = asyncio.run(invoke())
        self.assertEqual(result, {"action": "skip", "reason": "nunchi:v2-attention"})
        self.assertLess(elapsed, 0.10)
        self.assertEqual([row["stage"] for row in self.receipts], ["observation", "attention"])


if __name__ == "__main__":
    unittest.main()
