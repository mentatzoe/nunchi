from __future__ import annotations

from copy import deepcopy
import json
import time
import unittest

from nunchi.adapters.v2 import (
    normalize_discord_gateway,
    normalize_generic,
    normalize_matrix_event,
    normalize_telegram_update,
)
from nunchi.errors import ValidationError
from nunchi.integrations.codex_v2 import MCPDiscordTransport, _parse_codex_output
from nunchi.mcp_discord.authorization import ToolAuthorizer, make_tool_authorization
from nunchi.mcp_discord.events import v2_notification_from_dispatch
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.tools import ToolExecutor
from nunchi.observation import ParticipantBinding
from nunchi.participant import TransportResult


BINDING = ParticipantBinding(
    participant_id="vigil",
    actor_id="discord:actor:9",
    platform="discord",
    room_id="42",
    continuity_scope_id="discord:channel:42",
)


class NormalizerTests(unittest.TestCase):
    def test_discord_preserves_self_and_other_bot_messages(self):
        for actor_id in ("9", "10"):
            delivery = normalize_discord_gateway(
                {
                    "t": "MESSAGE_CREATE",
                    "s": 4,
                    "d": {
                        "id": f"100{actor_id}",
                        "channel_id": "42",
                        "author": {
                            "id": actor_id,
                            "username": f"bot-{actor_id}",
                            "bot": True,
                        },
                        "content": "hello",
                        "mentions": [],
                        "mention_everyone": False,
                    },
                },
                BINDING,
            )
            self.assertEqual(f"discord:actor:{actor_id}", delivery.event["author_id"])
            self.assertEqual("bot", delivery.actors[f"discord:actor:{actor_id}"]["kind"])

    def test_discord_reaction_and_membership_are_constructible(self):
        reaction = normalize_discord_gateway(
            {
                "t": "MESSAGE_REACTION_ADD",
                "s": 5,
                "d": {
                    "channel_id": "42",
                    "user_id": "7",
                    "message_id": "100",
                    "emoji": {"name": "✅", "id": None},
                },
            },
            BINDING,
        )
        self.assertEqual("reaction", reaction.event["type"])
        membership = normalize_discord_gateway(
            {
                "t": "GUILD_MEMBER_ADD",
                "s": 6,
                "d": {
                    "guild_id": "99",
                    "room_id": "42",
                    "user": {"id": "7", "username": "Zoe", "bot": False},
                },
            },
            BINDING,
        )
        self.assertEqual("42", membership.room_id)
        self.assertEqual("membership", membership.event["type"])
        self.assertEqual({"kind": "space", "id": "99"}, membership.event["scope"])

    def test_matrix_and_telegram_preserve_equivalent_available_message_facts(self):
        matrix = normalize_matrix_event(
            {
                "room_id": "!room:example",
                "event": {
                    "event_id": "$event",
                    "type": "m.room.message",
                    "sender": "@zoe:example",
                    "content": {"body": "hello", "msgtype": "m.text"},
                },
            },
            ParticipantBinding(
                "matrix-agent",
                "matrix:actor:@bot:example",
                "matrix",
                "!room:example",
                "matrix:!room:example",
            ),
        )
        telegram = normalize_telegram_update(
            {
                "update_id": 1,
                "message": {
                    "message_id": 3,
                    "chat": {"id": -42},
                    "from": {"id": 7, "first_name": "Zoe", "is_bot": False},
                    "text": "hello",
                    "date": 1_700_000_000,
                },
            },
            ParticipantBinding(
                "telegram-agent",
                "telegram:actor:9",
                "telegram",
                "-42",
                "telegram:-42",
            ),
        )
        self.assertEqual("message", matrix.event["type"])
        self.assertEqual("message", telegram.event["type"])
        self.assertEqual(matrix.event["text"], telegram.event["text"])
        self.assertEqual([], matrix.event["mentioned_actor_ids"])
        self.assertEqual([], telegram.event["mentioned_actor_ids"])
        self.assertFalse(matrix.event["mentions_room"])
        self.assertFalse(telegram.event["mentions_room"])

    def test_generic_adapter_rejects_unknown_fields(self):
        with self.assertRaises(ValidationError):
            normalize_generic(
                {
                    "delivery_id": "d",
                    "room_id": "42",
                    "event": None,
                    "actors": {},
                    "handled": True,
                },
                BINDING,
            )

    def test_shared_notification_is_closed_v2_and_keeps_exact_self(self):
        params = v2_notification_from_dispatch(
            "MESSAGE_CREATE",
            {
                "id": "100",
                "channel_id": "42",
                "author": {"id": "9", "username": "Vigil", "bot": True},
                "content": "my contribution",
                "mentions": [],
                "mention_everyone": False,
            },
            sequence=8,
        )
        self.assertEqual(
            {
                "schema_version",
                "delivery_id",
                "room_id",
                "event",
                "actors",
                "continuity_gap",
            },
            set(params),
        )
        self.assertIs(params["continuity_gap"], False)
        self.assertEqual("discord:actor:9", params["event"]["author_id"])


class ToolAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.secret = b"x" * 32
        self.authorizer = ToolAuthorizer(
            secret=self.secret,
            participant_ids=frozenset({"vigil"}),
            room_ids=frozenset({"42"}),
        )

    def authorization(self, arguments, *, now=None):
        return make_tool_authorization(
            secret=self.secret,
            request_id="request-1",
            participant_id="vigil",
            room_id="42",
            tool="send_message",
            arguments=arguments,
            now=now,
        )

    def test_exact_action_allows_once_and_mutation_or_replay_fails(self):
        arguments = {"channel_id": "42", "content": "hello"}
        authorization = self.authorization(arguments, now=100)
        self.assertTrue(
            self.authorizer.verify(
                authorization=authorization,
                tool="send_message",
                arguments=arguments,
                now=100,
            )[0]
        )
        self.assertFalse(
            self.authorizer.verify(
                authorization=authorization,
                tool="send_message",
                arguments=arguments,
                now=100,
            )[0]
        )
        fresh = self.authorization(arguments, now=100)
        self.assertFalse(
            self.authorizer.verify(
                authorization=fresh,
                tool="send_message",
                arguments={**arguments, "content": "mutated"},
                now=100,
            )[0]
        )

    def test_expired_wrong_room_and_forged_mac_fail(self):
        arguments = {"channel_id": "42", "content": "hello"}
        expired = self.authorization(arguments, now=1)
        self.assertFalse(
            self.authorizer.verify(
                authorization=expired,
                tool="send_message",
                arguments=arguments,
                now=1000,
            )[0]
        )
        wrong_room = deepcopy(self.authorization(arguments, now=100))
        wrong_room["room_id"] = "43"
        self.assertFalse(
            self.authorizer.verify(
                authorization=wrong_room,
                tool="send_message",
                arguments=arguments,
                now=100,
            )[0]
        )

    def test_tool_executor_calls_rest_only_after_authorization(self):
        class Rest:
            def __init__(self):
                self.calls = []

            def create_message(self, channel_id, content, *, reply_to_message_id=None):
                self.calls.append((channel_id, content, reply_to_message_id))
                return {
                    "id": "101",
                    "channel_id": channel_id,
                    "author": {"id": "9", "username": "Vigil", "bot": True},
                    "content": content,
                }

            def get_messages(self, *args, **kwargs):
                return []

            def add_reaction(self, *args):
                self.calls.append(args)

            def remove_reaction(self, *args):
                self.calls.append(args)

        rest = Rest()
        executor = ToolExecutor(
            rest,
            SendBackstop(5, 10),
            authorizer=self.authorizer,
        )
        arguments = {"channel_id": "42", "content": "hello"}
        denied, ok = executor.call("send_message", arguments)
        self.assertFalse(ok)
        self.assertEqual([], rest.calls)
        authorized = {
            **arguments,
            "_nunchi_authorization": self.authorization(arguments),
        }
        sent, ok = executor.call("send_message", authorized)
        self.assertTrue(ok, sent)
        self.assertEqual(1, len(rest.calls))


class CodexSurfaceTests(unittest.TestCase):
    def test_codex_jsonl_parser_extracts_task_and_exact_action(self):
        output = "\n".join(
            [
                json.dumps(
                    {
                        "type": "thread.started",
                        "thread_id": "019f9432-9300-7dd1-8225-d7f10f921968",
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": json.dumps(
                                {
                                    "kind": "message",
                                    "origin_event_id": "discord:message:1",
                                    "text": "hello",
                                }
                            ),
                        },
                    }
                ),
            ]
        )
        thread_id, action = _parse_codex_output(output)
        self.assertEqual("019f9432-9300-7dd1-8225-d7f10f921968", thread_id)
        self.assertEqual("message", action["kind"])

    def test_codex_mcp_transport_binds_exact_output(self):
        secret = b"y" * 32
        verifier = ToolAuthorizer(
            secret=secret,
            participant_ids=frozenset({"vigil"}),
            room_ids=frozenset({"42"}),
        )

        class Client:
            def __init__(self):
                self.calls = []

            def call_tool(self, name, arguments):
                supplied = dict(arguments)
                authorization = supplied.pop("_nunchi_authorization")
                ok, detail = verifier.verify(
                    authorization=authorization,
                    tool=name,
                    arguments=supplied,
                )
                if not ok:
                    return {"isError": True, "content": detail}
                self.calls.append((name, supplied))
                return {"isError": False, "content": []}

        client = Client()
        transport = MCPDiscordTransport(client, "42", "vigil", secret)
        result = transport.dispatch(
            action={
                "kind": "message",
                "origin_event_id": "discord:message:1",
                "text": "hello",
            },
            wake={
                "request_id": "request-1",
                "self": {"participant_id": "vigil"},
                "room": {"id": "42"},
            },
        )
        self.assertEqual(TransportResult("sent", "mcp:send_message"), result)
        self.assertEqual(
            [("send_message", {"channel_id": "42", "content": "hello"})],
            client.calls,
        )


if __name__ == "__main__":
    unittest.main()
