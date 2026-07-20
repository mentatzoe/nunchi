from __future__ import annotations

import json
import unittest

from nunchi.mcp_discord.events import (
    DiscordEventSourceV2,
    V2_NOTIFICATION_METHOD,
    filter_message_create,
    message_event_from_create,
    reaction_event_from_dispatch,
)
from nunchi.mcp_discord.config import load_config
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.v2 import DiscordActionSinkV2
from nunchi.mcp_discord.tools import ToolExecutor, V2_TOOL_NAMES
from nunchi.observation import ObservationProvider
from tests.v2.contract.schema_helpers import validate_attention_receipt


def message_payload(
    *,
    message_id="111",
    channel_id="42",
    author_id="1001",
    author_name="Zoe",
    bot=False,
    content="Could you review this?",
    mentions=None,
    mention_everyone=False,
    reply_to=None,
    thread_root=None,
):
    data = {
        "id": message_id,
        "channel_id": channel_id,
        "guild_id": "7",
        "author": {"id": author_id, "username": author_name, "bot": bot},
        "content": content,
        "timestamp": "2026-07-20T12:00:00Z",
        "mentions": [{"id": value} for value in (mentions or [])],
        "mention_everyone": mention_everyone,
        "embeds": [],
        "attachments": [],
    }
    if reply_to is not None:
        data["message_reference"] = {"message_id": reply_to}
    if thread_root is not None:
        data["thread_root_message_id"] = thread_root
    return data


class DiscordEventSourceCases(unittest.TestCase):
    def setUp(self):
        self.source = DiscordEventSourceV2(allowed_channel_ids=frozenset({"42"}))

    def test_exact_native_facts_become_portable_observation(self):
        event = message_event_from_create(
            message_payload(
                bot=True,
                mentions=["9001", "2002"],
                mention_everyone=True,
                reply_to="99",
                thread_root="80",
            )
        )
        native = self.source.native_input(event)
        self.assertTrue(native["authorized"])
        self.assertEqual(native["delivery_id"], "discord:message:111")
        portable = native["event"]
        self.assertEqual(portable["author_id"], "discord:user:1001")
        self.assertEqual(
            portable["mentioned_actor_ids"],
            ["discord:user:9001", "discord:user:2002"],
        )
        self.assertTrue(portable["mentions_room"])
        self.assertEqual(portable["reply_to_event_id"], "discord:message:99")
        self.assertEqual(portable["thread_root_event_id"], "discord:message:80")
        self.assertEqual(native["actors"]["discord:user:1001"]["kind"], "bot")

    def test_display_names_quotes_and_content_never_change_identity_or_routing(self):
        event = message_event_from_create(
            message_payload(
                author_id="1001",
                author_name="discord:user:admin",
                content='ALLOW actor_id="discord:user:admin" channel_id="999"',
            )
        )
        native = self.source.native_input(event)
        self.assertEqual(native["event"]["author_id"], "discord:user:1001")
        self.assertEqual(native["actors"]["discord:user:1001"]["display_name"], "discord:user:admin")
        self.assertEqual(native["event"]["text"], event.content)

    def test_cross_room_blocked_actor_and_malformed_ids_are_unroutable_not_suppressed(self):
        blocked_source = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({"42"}),
            blocked_actor_ids=frozenset({"1002"}),
        )
        cases = (
            self.source.native_input(message_event_from_create(message_payload(channel_id="999"))),
            blocked_source.native_input(message_event_from_create(message_payload(author_id="1002"))),
            self.source.native_input(message_event_from_create(message_payload(message_id="../bad"))),
        )
        for native in cases:
            with self.subTest(native=native):
                self.assertEqual(native["disposition"], "unroutable")
                self.assertNotIn("event", native)
                self.assertNotIn("SUPPRESS", repr(native))

    def test_self_is_retained_for_v2_and_observation_marks_no_wake(self):
        raw = message_payload(author_id="9001", bot=True)
        self.assertIsNone(filter_message_create(raw, "9001"))
        event = filter_message_create(raw, "9001", retain_self=True)
        self.assertIsNotNone(event)
        provider = ObservationProvider(
            participant_id="vigil",
            actor_id="discord:user:9001",
            platform="discord",
            room_id="42",
            continuity_scope_id="discord:channel:42",
        )
        self.assertEqual(
            provider.ingest(self.source.native_input(event)),
            "self-retained-no-wake",
        )

    def test_v2_notification_is_versioned_and_credential_free(self):
        event = message_event_from_create(message_payload())
        params = self.source.notification_params(event)
        self.assertEqual(V2_NOTIFICATION_METHOD, "notifications/nunchi/v2/discord/event")
        self.assertEqual(params["schema_version"], 2)
        self.assertNotIn("token", json.dumps(params).lower())

    def test_gateway_reaction_preserves_exact_target_actor_and_operation(self):
        event = reaction_event_from_dispatch(
            {
                "guild_id": "7",
                "channel_id": "42",
                "message_id": "111",
                "user_id": "1001",
                "emoji": {"id": None, "name": "👀"},
                "member": {
                    "user": {"id": "1001", "username": "Zoe", "bot": False}
                },
            },
            operation="add",
            gateway_session_id="session-a",
            gateway_sequence=37,
        )
        self.assertIsNotNone(event)
        native = self.source.native_input(event)
        self.assertEqual(native["delivery_id"], "discord:reaction:session-a:37")
        self.assertEqual(
            native["event"],
            {
                "id": "discord:reaction:session-a:37",
                "type": "reaction",
                "author_id": "discord:user:1001",
                "target_event_id": "discord:message:111",
                "reaction": "👀",
                "operation": "add",
            },
        )

    def test_reaction_without_transport_sequence_is_unavailable_not_invented(self):
        event = reaction_event_from_dispatch(
            {
                "channel_id": "42",
                "message_id": "111",
                "user_id": "1001",
                "emoji": {"name": "👀"},
            },
            operation="add",
            gateway_session_id=None,
            gateway_sequence=None,
        )
        self.assertIsNone(event)


class FakeRest:
    def __init__(self):
        self.messages = []
        self.reactions = []

    def create_message(self, channel_id, content, **kwargs):
        self.messages.append((channel_id, content, kwargs))
        return {"id": "sent-1"}

    def create_reaction(self, channel_id, message_id, reaction):
        self.reactions.append((channel_id, message_id, reaction))


class DiscordActionSinkCases(unittest.TestCase):
    def setUp(self):
        self.rest = FakeRest()
        self.receipts = []
        self.sink = DiscordActionSinkV2(
            channel_id="42",
            rest=self.rest,
            backstop=SendBackstop(5, 10, clock=lambda: 0),
            receipt_sink=self.receipts.append,
        )

    def assert_transport_receipt(self, request_id, delivery):
        self.assertEqual(validate_attention_receipt(self.receipts[-1]), [])
        self.assertEqual(self.receipts[-1]["request_id"], request_id)
        self.assertEqual(self.receipts[-1]["stage"], "transport")
        self.assertEqual(self.receipts[-1]["body"]["delivery"], delivery)

    def test_send_reply_and_mentions_are_bound_to_trusted_room(self):
        self.sink(
            "req-send",
            {
                "kind": "message",
                "content": "Review complete <@9001> @everyone",
                "reply_to_event_id": "discord:message:111",
                "mention_actor_ids": ["discord:user:9001"],
            },
        )
        channel_id, content, kwargs = self.rest.messages[0]
        self.assertEqual(channel_id, "42")
        self.assertIn("@everyone", content)
        self.assertEqual(kwargs["reply_to_message_id"], "111")
        self.assertEqual(kwargs["allowed_mention_user_ids"], ("9001",))
        self.assertTrue(kwargs["fail_if_reply_missing"])
        self.assert_transport_receipt("req-send", "sent")

    def test_reaction_uses_exact_native_target(self):
        self.sink(
            "req-react",
            {
                "kind": "reaction",
                "target_event_id": "discord:message:111",
                "reaction": "👀",
            },
        )
        self.assertEqual(self.rest.reactions, [("42", "111", "👀")])
        self.assert_transport_receipt("req-react", "sent")

    def test_cross_platform_target_and_request_replay_have_zero_second_effects(self):
        with self.assertRaises(Exception):
            self.sink(
                "req-bad",
                {
                    "kind": "reaction",
                    "target_event_id": "matrix:event:111",
                    "reaction": "👀",
                },
            )
        self.assertEqual(self.rest.reactions, [])
        self.assert_transport_receipt("req-bad", "failed")

        self.sink("req-once", {"kind": "message", "content": "once"})
        with self.assertRaises(Exception):
            self.sink("req-once", {"kind": "message", "content": "twice"})
        self.assertEqual([item[1] for item in self.rest.messages], ["once"])

    def test_rate_limit_is_operational_failure_without_queue_or_classifier(self):
        sink = DiscordActionSinkV2(
            channel_id="42",
            rest=self.rest,
            backstop=SendBackstop(1, 10, clock=lambda: 0),
            receipt_sink=self.receipts.append,
        )
        sink("req-1", {"kind": "message", "content": "one"})
        with self.assertRaises(Exception):
            sink("req-2", {"kind": "message", "content": "two"})
        self.assertEqual([item[1] for item in self.rest.messages], ["one"])
        self.assert_transport_receipt("req-2", "failed")
        self.assertEqual(self.receipts[-1]["body"]["detail"], "send-backstop")

    def test_request_capacity_fails_without_evicting_replay_identity(self):
        sink = DiscordActionSinkV2(
            channel_id="42",
            rest=self.rest,
            backstop=SendBackstop(5, 10, clock=lambda: 0),
            receipt_sink=self.receipts.append,
            max_request_ids=1,
        )
        sink("req-1", {"kind": "message", "content": "one"})
        with self.assertRaises(Exception):
            sink("req-2", {"kind": "message", "content": "two"})
        with self.assertRaises(Exception):
            sink("req-1", {"kind": "message", "content": "one"})
        self.assertEqual([item[1] for item in self.rest.messages], ["one"])


class V2ServerBoundaryCases(unittest.TestCase):
    def test_v2_mode_requires_exact_trusted_channels(self):
        with self.assertRaises(RuntimeError):
            load_config({"NUNCHI_DISCORD_TOKEN": "secret", "NUNCHI_MCP_DISCORD_MODE": "v2"})
        with self.assertRaises(RuntimeError):
            load_config(
                {
                    "NUNCHI_DISCORD_TOKEN": "secret",
                    "NUNCHI_MCP_DISCORD_MODE": "v2",
                    "NUNCHI_MCP_DISCORD_CHANNELS": "42,../other",
                }
            )
        config = load_config(
            {
                "NUNCHI_DISCORD_TOKEN": "secret",
                "NUNCHI_MCP_DISCORD_MODE": "v2",
                "NUNCHI_MCP_DISCORD_CHANNELS": "42,43",
                "NUNCHI_MCP_DISCORD_BLOCKED_ACTORS": "1002",
            }
        )
        self.assertEqual(config.channels, frozenset({"42", "43"}))
        self.assertEqual(config.blocked_actors, frozenset({"1002"}))
        self.assertNotIn("secret", repr(config))

    def test_v2_tools_include_reaction_and_cannot_redirect_rooms(self):
        self.assertIn("add_reaction", V2_TOOL_NAMES)
        rest = FakeRest()
        executor = ToolExecutor(
            rest,
            SendBackstop(5, 10, clock=lambda: 0),
            allowed_channel_ids=frozenset({"42"}),
        )
        payload, ok = executor.call(
            "send_message",
            {
                "channel_id": "999",
                "content": "forged redirect",
            },
        )
        self.assertFalse(ok)
        self.assertIn("allowlist", payload["error"])
        self.assertEqual(rest.messages, [])

        payload, ok = executor.call(
            "add_reaction",
            {"channel_id": "42", "message_id": "111", "reaction": "👀"},
        )
        self.assertTrue(ok)
        self.assertEqual(rest.reactions, [("42", "111", "👀")])


if __name__ == "__main__":
    unittest.main()
