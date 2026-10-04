from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from nunchi.adapters.v2 import (
    normalize_discord_gateway,
    normalize_generic,
    normalize_matrix_event,
    normalize_telegram_update,
)
from nunchi.adapters.runtime import ReferenceAdapterRuntime
from nunchi.adapters.matrix import MatrixTransport
from nunchi.adapters.telegram import TelegramTransport
from nunchi.adapters.discord import DiscordPyTransport, DurableGatewaySequence
from nunchi.errors import ValidationError
from nunchi.attention import ParticipantProfile
from nunchi.integrations.codex_v2 import (
    CodexParticipant,
    CodexRoomRuntime,
    CodexTaskReceiptJournal,
    _atomic_write,
    MCPDiscordTransport,
    _credential_binding,
    _parse_codex_output,
)
from nunchi.integrations.mcp_client import StreamableMCPClient
from nunchi.mcp_discord.authorization import ToolAuthorizer, make_tool_authorization
from nunchi.mcp_discord.events import v2_notification_from_dispatch
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient, DiscordRestError
from nunchi.mcp_discord.tools import ToolExecutor
from nunchi.observation import ParticipantBinding
from nunchi.participant import TransportResult
from nunchi.participant_model import ParticipantTurnProtocol


BINDING = ParticipantBinding(
    participant_id="vigil",
    actor_id="discord:actor:9",
    platform="discord",
    room_id="42",
    continuity_scope_id="discord:channel:42",
)


class NormalizerTests(unittest.TestCase):
    def test_permission_revisions_do_not_derive_from_live_secrets(self):
        first_discord = MCPDiscordTransport(
            object(), "42", "vigil", "discord:actor:9", b"a" * 32
        )
        second_discord = MCPDiscordTransport(
            object(), "42", "vigil", "discord:actor:9", b"b" * 32
        )
        self.assertEqual(
            first_discord.reaction_capability().permissions_revision,
            second_discord.reaction_capability().permissions_revision,
        )

        with mock.patch.dict(os.environ, {"MATRIX_TOKEN": "first-secret"}, clear=False):
            first_matrix = MatrixTransport(
                {
                    "homeserver": "https://matrix.invalid",
                    "access_token_env": "MATRIX_TOKEN",
                }
            )
        with mock.patch.dict(os.environ, {"MATRIX_TOKEN": "second-secret"}, clear=False):
            second_matrix = MatrixTransport(
                {
                    "homeserver": "https://matrix.invalid",
                    "access_token_env": "MATRIX_TOKEN",
                }
            )
        self.assertEqual(
            first_matrix.reaction_capability().permissions_revision,
            second_matrix.reaction_capability().permissions_revision,
        )

    def test_discord_ack_capability_tracks_exact_room_permissions(self):
        class Permissions:
            def __init__(self, allowed):
                self.view_channel = allowed
                self.read_message_history = allowed
                self.add_reactions = allowed

        class Channel:
            def __init__(self):
                self.allowed = True
                self.guild = type(
                    "Guild",
                    (),
                    {"me": type("Member", (), {"_roles": ()})()},
                )()

            def permissions_for(self, user):
                if not hasattr(user, "_roles"):
                    raise AttributeError("discord.py requires a Member or Role")
                return Permissions(self.allowed)

        class User:
            id = 9

        class Bot:
            user = User()

            def __init__(self, channel):
                self.channel = channel

            def get_channel(self, channel_id):
                return self.channel if channel_id == 42 else None

        channel = Channel()
        transport = DiscordPyTransport(Bot(channel), None, "42")
        allowed = transport.reaction_capability()
        self.assertTrue(allowed.authenticated)
        self.assertTrue(allowed.allows("👂", "add"))

        channel.allowed = False
        denied = transport.reaction_capability()
        self.assertFalse(denied.allows("👂", "add"))
        self.assertNotEqual(
            allowed.permissions_revision,
            denied.permissions_revision,
        )

        channel.permissions_for = mock.Mock(side_effect=AttributeError("shape drift"))
        unavailable = transport.reaction_capability()
        self.assertFalse(unavailable.supported)
        self.assertFalse(unavailable.allows("👂", "add"))

    def test_standalone_discord_occurrence_counter_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.json"
            first = DurableGatewaySequence(path)
            self.assertEqual(1, first.next())
            restored = DurableGatewaySequence(path)
            self.assertEqual(2, restored.next())
            path.write_text('{"schema_version":2,"value":"bad"}')
            with self.assertRaises(ValidationError):
                DurableGatewaySequence(path)

    def test_reference_transports_attest_authenticated_self_identity(self):
        with mock.patch.dict(os.environ, {"MATRIX_TOKEN": "secret"}, clear=False):
            matrix = MatrixTransport(
                {
                    "homeserver": "https://matrix.invalid",
                    "access_token_env": "MATRIX_TOKEN",
                }
            )
        matrix._request = lambda *args, **kwargs: {"user_id": "@vigil:example"}
        self.assertEqual(
            "matrix:actor:@vigil:example",
            matrix.authenticated_actor_id(),
        )
        with mock.patch.dict(os.environ, {"TELEGRAM_TOKEN": "secret"}, clear=False):
            telegram = TelegramTransport({"bot_token_env": "TELEGRAM_TOKEN"})
        telegram._call = lambda *args, **kwargs: {"id": 123}
        self.assertEqual("telegram:actor:123", telegram.authenticated_actor_id())

    def test_matrix_ack_capability_measures_exact_self_and_room_power(self):
        with mock.patch.dict(os.environ, {"MATRIX_TOKEN": "secret"}, clear=False):
            matrix = MatrixTransport(
                {
                    "homeserver": "https://matrix.invalid",
                    "access_token_env": "MATRIX_TOKEN",
                },
                room_id="!room:example",
                actor_id="matrix:actor:@vigil:example",
            )

        power_levels = {
            "users": {"@vigil:example": 50},
            "users_default": 0,
            "events": {"m.reaction": 40},
            "events_default": 0,
        }

        def request(_method, path, _payload=None):
            if path.endswith("/account/whoami"):
                return {"user_id": "@vigil:example"}
            return deepcopy(power_levels)

        matrix._request = mock.Mock(side_effect=request)
        allowed = matrix.reaction_capability()
        self.assertTrue(allowed.allows("👂", "add"))
        self.assertTrue(allowed.authenticated)

        power_levels["events"]["m.reaction"] = 60
        denied = matrix.reaction_capability()
        self.assertFalse(denied.allows("👂", "add"))
        self.assertTrue(denied.authenticated)
        self.assertNotEqual(
            allowed.permissions_revision,
            denied.permissions_revision,
        )

        matrix._request = mock.Mock(return_value={"user_id": "@other:example"})
        wrong_self = matrix.reaction_capability()
        self.assertFalse(wrong_self.supported)
        self.assertFalse(wrong_self.authenticated)

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
                "delivery_epoch": "session-a",
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
                "delivery_epoch": "session-a",
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

    def test_discord_reaction_repetition_uses_gateway_sequence_identity(self):
        payload = {
            "channel_id": "42",
            "user_id": "7",
            "message_id": "100",
            "emoji": {"name": "✅", "id": None},
        }
        deliveries = [
            normalize_discord_gateway(
                {
                    "t": event_type,
                    "s": sequence,
                    "delivery_epoch": "session-a",
                    "d": payload,
                },
                BINDING,
            )
            for event_type, sequence in (
                ("MESSAGE_REACTION_ADD", 10),
                ("MESSAGE_REACTION_REMOVE", 11),
                ("MESSAGE_REACTION_ADD", 12),
            )
        ]
        self.assertEqual(3, len({item.event["id"] for item in deliveries}))
        new_session = normalize_discord_gateway(
            {
                "t": "MESSAGE_REACTION_ADD",
                "s": 10,
                "delivery_epoch": "session-b",
                "d": payload,
            },
            BINDING,
        )
        self.assertNotEqual(deliveries[0].event["id"], new_session.event["id"])
        missing = normalize_discord_gateway(
            {
                "t": "MESSAGE_REACTION_ADD",
                "s": None,
                "delivery_epoch": "session-a",
                "d": payload,
            },
            BINDING,
        )
        self.assertIsNone(missing.event)

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
            delivery_epoch="session-a",
            transport_self_actor_id="discord:actor:9",
        )
        self.assertEqual(
            {
                "schema_version",
                "delivery_id",
                "room_id",
                "event",
                "actors",
                "continuity_gap",
                "transport_self_actor_id",
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
            participant_routes={
                "vigil": frozenset({"42"}),
                "reviewer": frozenset({"43"}),
            },
        )

    def authorization(
        self,
        arguments,
        *,
        now=None,
        tool="send_message",
        request_id="request-1",
    ):
        return make_tool_authorization(
            secret=self.secret,
            request_id=request_id,
            participant_id="vigil",
            room_id="42",
            tool=tool,
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
        cross_product_arguments = {"channel_id": "43", "content": "hello"}
        cross_product = make_tool_authorization(
            secret=self.secret,
            request_id="request-cross",
            participant_id="vigil",
            room_id="43",
            tool="send_message",
            arguments=cross_product_arguments,
            now=100,
        )
        self.assertFalse(
            self.authorizer.verify(
                authorization=cross_product,
                tool="send_message",
                arguments=cross_product_arguments,
                now=100,
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
        unbound, ok = executor.call("send_message", authorized)
        self.assertFalse(ok, unbound)
        self.assertEqual([], rest.calls)
        sent, ok = executor.call(
            "send_message",
            authorized,
            expected_self_actor_id="discord:actor:9",
        )
        self.assertTrue(ok, sent)
        self.assertEqual(1, len(rest.calls))

    def test_tool_executor_measures_reaction_capability_after_exact_authorization(self):
        class Rest:
            def __init__(self):
                self.calls = []

            def reaction_capability(self, channel_id, expected_user_id):
                self.calls.append((channel_id, expected_user_id))
                return {
                    "channel_id": channel_id,
                    "actor_id": expected_user_id,
                    "capability": {
                        "supported": False,
                        "authenticated": True,
                        "operations": [],
                        "reactions": [],
                        "permissions_revision": "denied-v1",
                    },
                }

        rest = Rest()
        executor = ToolExecutor(
            rest,
            SendBackstop(5, 10),
            authorizer=self.authorizer,
        )
        arguments = {"channel_id": "42"}
        payload, ok = executor.call(
            "reaction_capability",
            {
                **arguments,
                "_nunchi_authorization": self.authorization(
                    arguments,
                    tool="reaction_capability",
                    request_id="reaction-capability",
                ),
            },
            expected_route=("vigil", "42"),
            expected_self_actor_id="discord:actor:9",
        )
        self.assertTrue(ok, payload)
        self.assertEqual([("42", "9")], rest.calls)
        self.assertFalse(
            payload["reaction_capability"]["capability"]["supported"]
        )

    def test_tool_executor_does_not_confirm_malformed_create_response(self):
        class Rest:
            response = {}

            def create_message(self, *_args, **_kwargs):
                return deepcopy(self.response)

        rest = Rest()
        executor = ToolExecutor(
            rest,
            SendBackstop(5, 10),
            authorizer=self.authorizer,
        )
        arguments = {"channel_id": "42", "content": "hello"}
        for sequence, response in enumerate(
            (
                {},
                {
                    "id": "101",
                    "channel_id": "42",
                    "author": "malformed-author",
                    "content": "hello",
                },
                {
                    "id": "101",
                    "channel_id": "42",
                    "author": {"id": "9", "username": "Vigil", "bot": True},
                    "content": "hello",
                    "mentions": "malformed-mentions",
                },
            ),
            1,
        ):
            with self.subTest(response=response):
                rest.response = response
                payload, ok = executor.call(
                    "send_message",
                    {
                        **arguments,
                        "_nunchi_authorization": self.authorization(
                            arguments,
                            request_id=f"malformed-create-{sequence}",
                        ),
                    },
                    expected_self_actor_id="discord:actor:9",
                )
                self.assertTrue(ok)
                self.assertEqual("unknown", payload["delivery"]["status"])

    def test_tool_executor_preserves_uncertain_post_effect_outcomes(self):
        arguments = {"channel_id": "42", "content": "hello"}

        for sequence, failure in enumerate(
            (
                DiscordRestError(None, "network acknowledgement lost"),
                DiscordRestError(201, "malformed successful response"),
                DiscordRestError(503, "server acknowledgement uncertain"),
                RuntimeError("unexpected post-dispatch failure"),
            ),
            1,
        ):
            class Rest:
                def create_message(self, *_args, **_kwargs):
                    raise failure

            with self.subTest(failure=failure):
                executor = ToolExecutor(
                    Rest(),
                    SendBackstop(5, 10),
                    authorizer=self.authorizer,
                )
                payload, ok = executor.call(
                    "send_message",
                    {
                        **arguments,
                        "_nunchi_authorization": self.authorization(
                            arguments,
                            request_id=f"uncertain-create-{sequence}",
                        ),
                    },
                    expected_self_actor_id="discord:actor:9",
                )
                self.assertTrue(ok)
                self.assertEqual("unknown", payload["delivery"]["status"])

        class DeniedRest:
            def create_message(self, *_args, **_kwargs):
                raise DiscordRestError(403, "Discord rejected the effect")

        denied = ToolExecutor(
            DeniedRest(),
            SendBackstop(5, 10),
            authorizer=self.authorizer,
        )
        payload, ok = denied.call(
            "send_message",
            {
                **arguments,
                "_nunchi_authorization": self.authorization(
                    arguments,
                    request_id="definitive-create-denial",
                ),
            },
            expected_self_actor_id="discord:actor:9",
        )
        self.assertFalse(ok)
        self.assertIn("rejected", payload["error"])

    def test_tool_executor_preserves_uncertain_reaction_outcome(self):
        class Rest:
            def add_reaction(self, *_args, **_kwargs):
                raise DiscordRestError(None, "network acknowledgement lost")

        executor = ToolExecutor(
            Rest(),
            SendBackstop(5, 10),
            authorizer=self.authorizer,
        )
        arguments = {
            "channel_id": "42",
            "message_id": "101",
            "reaction": "✅",
        }
        payload, ok = executor.call(
            "add_reaction",
            {
                **arguments,
                "_nunchi_authorization": self.authorization(
                    arguments,
                    tool="add_reaction",
                    request_id="uncertain-reaction",
                ),
            },
            expected_self_actor_id="discord:actor:9",
        )
        self.assertTrue(ok)
        self.assertEqual("unknown", payload["delivery"]["status"])

    def test_discord_rest_does_not_retry_uncertain_mutating_5xx(self):
        calls = []

        def http(method, url, headers, body):
            calls.append((method, url, headers, body))
            return (503, {}, b"")

        client = DiscordRestClient(
            "test-token",
            http=http,
            sleeper=lambda _seconds: None,
        )
        with self.assertRaises(DiscordRestError) as caught:
            client.create_message("42", "hello")
        self.assertEqual(503, caught.exception.status)
        self.assertEqual(1, len(calls))

    def test_discord_rest_may_retry_read_only_5xx(self):
        calls = []
        responses = [
            (503, {}, b""),
            (200, {}, b"[]"),
        ]

        def http(method, url, headers, body):
            calls.append((method, url, headers, body))
            return responses.pop(0)

        client = DiscordRestClient(
            "test-token",
            http=http,
            sleeper=lambda _seconds: None,
        )
        self.assertEqual([], client.get_messages("42"))
        self.assertEqual(2, len(calls))

    def test_discord_rest_measures_effective_reaction_permissions(self):
        required = (1 << 6) | (1 << 10) | (1 << 16)

        def capability(overwrites, *, user_id="9"):
            responses = [
                {
                    "id": "42",
                    "guild_id": "1",
                    "permission_overwrites": overwrites,
                },
                {"user": {"id": user_id}, "roles": ["2"]},
                [
                    {"id": "1", "permissions": str(required)},
                    {"id": "2", "permissions": "0"},
                ],
            ]

            def http(_method, _url, _headers, _body):
                return (200, {}, json.dumps(responses.pop(0)).encode())

            return DiscordRestClient(
                "test-token",
                http=http,
                sleeper=lambda _seconds: None,
            ).reaction_capability("42", "9")

        allowed = capability([])["capability"]
        denied = capability(
            [{"id": "9", "type": 1, "allow": "0", "deny": str(1 << 6)}]
        )["capability"]
        self.assertTrue(allowed["supported"])
        self.assertFalse(denied["supported"])
        self.assertTrue(denied["authenticated"])
        self.assertNotEqual(
            allowed["permissions_revision"],
            denied["permissions_revision"],
        )
        with self.assertRaises(DiscordRestError):
            capability([], user_id="10")

    def test_tool_executor_requires_exact_message_effect_and_self(self):
        class Rest:
            response = {}

            def create_message(self, *_args, **_kwargs):
                return deepcopy(self.response)

        rest = Rest()
        executor = ToolExecutor(
            rest,
            SendBackstop(10, 10),
            authorizer=self.authorizer,
        )
        arguments = {
            "channel_id": "42",
            "message_id": "77",
            "content": "expected",
        }

        sequence = 0

        def call(response):
            nonlocal sequence
            sequence += 1
            rest.response = response
            return executor.call(
                "reply_message",
                {
                    **arguments,
                    "_nunchi_authorization": self.authorization(
                        arguments,
                        tool="reply_message",
                        request_id=f"reply-{sequence}",
                    ),
                },
                expected_self_actor_id="discord:actor:9",
            )

        valid = {
            "id": "101",
            "channel_id": "42",
            "author": {"id": "9", "username": "Vigil", "bot": True},
            "content": "expected",
            "message_reference": {"message_id": "77"},
        }
        self.assertTrue(call(valid)[1])
        for mutation in (
            {"content": "DIFFERENT"},
            {"message_reference": {"message_id": "88"}},
            {"author": {"id": "10", "username": "Other", "bot": True}},
        ):
            with self.subTest(mutation=mutation):
                payload, ok = call({**valid, **mutation})
                self.assertTrue(ok)
                self.assertEqual("unknown", payload["delivery"]["status"])


class CodexSurfaceTests(unittest.TestCase):
    @staticmethod
    def _installed_codex():
        return mock.patch(
            "nunchi.integrations.codex_v2.shutil.which",
            return_value="/trusted/bin/codex",
        )

    @staticmethod
    def _codex_identity():
        return (
            ParticipantProfile(
                profile_id="vigil",
                participant_id="vigil",
                actor_id="discord:actor:9",
                instructions="Contribute carefully.",
                provenance="trusted:test",
                sha256="a" * 64,
            ),
            ParticipantBinding(
                participant_id="vigil",
                actor_id="discord:actor:9",
                platform="discord",
                room_id="42",
                continuity_scope_id="discord:42",
            ),
        )

    @staticmethod
    def _persistent_runtime(directory, **overrides):
        root = Path(directory)
        codex_home = root / "codex-home"
        codex_home.mkdir(exist_ok=True)
        binary = root / "codex"
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o700)
        identity = {
            "provider": "openai",
            "account_id": "workspace:test-account",
            "credential_scope": "chatgpt:test-workspace",
            "auth_mode": "chatgpt",
            "codex_home": str(codex_home),
            "continuity_generation": 1,
        }
        (codex_home / "auth.json").write_text(
            json.dumps({"tokens": {"account_id": identity["account_id"]}}),
            encoding="utf-8",
        )
        identity.update(overrides)
        return binary, identity

    @staticmethod
    def _wake():
        return {
            "request_id": "r",
            "self": {
                "participant_id": "vigil",
                "actor_id": "discord:actor:9",
            },
            "room": {
                "platform": "discord",
                "id": "42",
                "continuity_scope_id": "discord:42",
            },
            "actors": {
                "discord:actor:9": {"kind": "bot"},
                "discord:actor:42": {"kind": "human"},
            },
            "events": [
                {
                    "id": "e1",
                    "type": "message",
                    "author_id": "discord:actor:42",
                    "text": "hello",
                    "mentioned_actor_ids": [],
                    "mentions_room": False,
                }
            ],
            "trigger_event_id": "e1",
            "coverage": {
                "has_more_before": False,
                "has_more_after": False,
                "has_gaps": False,
                "truncated_by": [],
                "continuity": "restart-safe",
                "has_restart_gap": False,
            },
            "attention": {"source": "WAKE"},
        }

    def test_codex_participant_rejects_arbitrary_process_configuration(self):
        profile, binding = self._codex_identity()
        with tempfile.TemporaryDirectory() as directory, self._installed_codex():
            for config in (
                {"binary": "/tmp/attacker"},
                {"args": ["--full-auto"]},
                {"working_directory": "/"},
                {"timeout_seconds": float("inf")},
            ):
                with self.subTest(config=config), self.assertRaises(ValidationError):
                    CodexParticipant(
                        profile=profile,
                        config=config,
                        binding=binding,
                        state_directory=directory,
                    )

    def test_codex_participant_requires_executable_on_trusted_path(self):
        profile, binding = self._codex_identity()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch(
                "nunchi.integrations.codex_v2.shutil.which",
                return_value=None,
            ),
            self.assertRaisesRegex(
                ValidationError,
                "Codex executable is not installed on trusted PATH",
            ),
        ):
            CodexParticipant(
                profile=profile,
                config={"session_mode": "fresh"},
                binding=binding,
                state_directory=directory,
            )

    def test_codex_process_is_fixed_read_only_tool_less_and_env_bounded(self):
        profile, binding = self._codex_identity()
        wake = {
            "request_id": "r",
            "self": {
                "participant_id": "vigil",
                "actor_id": "discord:actor:9",
            },
            "room": {
                "platform": "discord",
                "id": "42",
                "continuity_scope_id": "discord:42",
            },
            "actors": {
                "discord:actor:9": {"kind": "bot"},
                "discord:actor:42": {"kind": "human"},
            },
            "events": [
                {
                    "id": "e1",
                    "type": "message",
                    "author_id": "discord:actor:42",
                    "text": "hello",
                    "mentioned_actor_ids": [],
                    "mentions_room": False,
                }
            ],
            "trigger_event_id": "e1",
            "coverage": {
                "has_more_before": False,
                "has_more_after": False,
                "has_gaps": False,
                "truncated_by": [],
                "continuity": "restart-safe",
                "has_restart_gap": False,
            },
            "attention": {"source": "WAKE"},
        }
        protocol = ParticipantTurnProtocol(
            profile=profile,
            wake=wake,
            opportunity={
                "generation": 1,
                "lifecycle_id": "direct-library-call",
                "deadline_id": "direct-library-call",
                "permissions": {
                    "revision": "direct-library-call",
                    "ordinary_actions": ["message", "reply", "reaction"],
                    "privileged_proposals": True,
                },
            },
        )
        action = {
            "protocol": protocol.request["protocol"],
            "binding": protocol.request["binding"],
            "action": {"kind": "silence"},
        }

        class Process:
            returncode = 0

            def poll(self):
                return 0

            def communicate(self):
                return (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "agent_message",
                                "text": json.dumps(
                                    {"action_json": json.dumps(action)}
                                ),
                            },
                        }
                    ),
                    "",
                )

        with tempfile.TemporaryDirectory() as directory, self._installed_codex():
            participant = CodexParticipant(
                profile=profile,
                config={"session_mode": "fresh", "timeout_seconds": 5},
                binding=binding,
                state_directory=directory,
            )
            with mock.patch(
                "nunchi.integrations.codex_v2.subprocess.Popen",
                return_value=Process(),
            ) as popen:
                result = participant(
                    wake=wake,
                    expand=lambda **_: {},
                    cancel=threading.Event(),
                )
            schema = json.loads(participant.output_schema_path.read_text())
        self.assertIsNone(result)
        command = popen.call_args.args[0]
        self.assertEqual("/trusted/bin/codex", command[0])
        self.assertNotIn("--full-auto", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("--strict-config", command)
        self.assertIn("read-only", command)
        self.assertIn("--output-schema", command)
        self.assertNotIn("oneOf", schema)
        self.assertEqual(["action_json"], schema["required"])
        self.assertEqual(
            {"action_json"},
            set(schema["properties"]),
        )
        for feature in ("shell_tool", "unified_exec", "apps", "plugins"):
            self.assertIn(feature, command)
        child_env = popen.call_args.kwargs["env"]
        self.assertNotIn("NUNCHI_DISCORD_TOKEN", child_env)
        self.assertTrue(
            set(child_env).issubset(
                {
                    "CODEX_HOME",
                    "HOME",
                    "LANG",
                    "LC_ALL",
                    "LOGNAME",
                    "PATH",
                    "TMPDIR",
                    "USER",
                }
            )
        )

    def test_codex_expansions_share_one_turn_deadline(self):
        profile, binding = self._codex_identity()
        wake = self._wake()
        opportunity = {
            "generation": 1,
            "lifecycle_id": "lifecycle-1",
            "deadline_id": "deadline-1",
            "permissions": {
                "revision": "permissions-1",
                "ordinary_actions": ["message", "reply", "reaction"],
                "privileged_proposals": True,
            },
        }
        protocol = ParticipantTurnProtocol(
            profile=profile,
            wake=wake,
            opportunity=opportunity,
        )
        expansion = {
            "protocol": protocol.request["protocol"],
            "binding": protocol.request["binding"],
            "action": {
                "kind": "expand",
                "direction": "before",
                "max_events": 1,
                "max_bytes": 256,
            },
        }
        task_id = "019f9432-9300-7dd1-8225-d7f10f921968"
        stdout = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": task_id}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": json.dumps(
                                {"action_json": json.dumps(expansion)}
                            ),
                        },
                    }
                ),
            )
        )

        class CompletedProcess:
            returncode = 0

            def poll(self):
                return 0

            def communicate(self):
                return stdout, ""

        class BlockingProcess:
            returncode = None

            def __init__(self):
                self.terminated = False
                self.killed = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout):
                self.wait_timeout = timeout
                return 0

            def kill(self):
                self.killed = True

        blocked = BlockingProcess()
        with tempfile.TemporaryDirectory() as directory, self._installed_codex():
            participant = CodexParticipant(
                profile=profile,
                config={"session_mode": "fresh", "timeout_seconds": 5},
                binding=binding,
                state_directory=directory,
            )
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.subprocess.Popen",
                    side_effect=[CompletedProcess(), blocked],
                ) as popen,
                mock.patch(
                    "nunchi.integrations.codex_v2.time.monotonic",
                    side_effect=[0.0, 6.0],
                ) as monotonic,
            ):
                result = participant.run_protocol(
                    wake=wake,
                    opportunity=opportunity,
                    expand=lambda **_: {"events": []},
                    cancel=threading.Event(),
                )

        self.assertIsNone(result)
        self.assertEqual(2, popen.call_count)
        self.assertEqual(2, monotonic.call_count)
        self.assertTrue(blocked.terminated)
        self.assertFalse(blocked.killed)

    def test_codex_persistent_task_is_bound_to_profile_actor_room_and_behavior(self):
        profile, binding = self._codex_identity()
        thread_id = "019f9432-9300-7dd1-8225-d7f10f921968"
        with tempfile.TemporaryDirectory() as directory:
            binary, identity = self._persistent_runtime(directory)
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.shutil.which",
                    return_value=str(binary),
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_version",
                    return_value="codex-cli test",
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_auth_mode",
                    return_value="chatgpt",
                ),
            ):
                first = CodexParticipant(
                    profile=profile,
                    config={
                        "session_mode": "persistent",
                        "model": "model-a",
                        "runtime_identity": identity,
                    },
                    binding=binding,
                    state_directory=directory,
                )
                first._save_session(thread_id)
                self.assertEqual(thread_id, first._load_session())
                first._consume_committed_session()
                self.assertFalse(first.session_path.exists())
                self.assertTrue(first.inflight_session_path.exists())
                first.stage_task("accepted-request", thread_id)
                first.commit_task("accepted-request")
                self.assertEqual(thread_id, first._load_session())
                self.assertFalse(first.inflight_session_path.exists())
                changed = CodexParticipant(
                    profile=profile,
                    config={
                        "session_mode": "persistent",
                        "model": "model-b",
                        "runtime_identity": identity,
                    },
                    binding=binding,
                    state_directory=directory,
                )
                with self.assertRaises(RuntimeError):
                    changed._load_session()
                with self.assertRaisesRegex(ValidationError, "account differs"):
                    CodexParticipant(
                        profile=profile,
                        config={
                            "session_mode": "persistent",
                            "model": "model-a",
                            "runtime_identity": {
                                **identity,
                                "account_id": "workspace:different-account",
                                "continuity_generation": 2,
                            },
                        },
                        binding=binding,
                        state_directory=directory,
                    )

    def test_codex_persistent_mode_requires_an_exact_runtime_identity(self):
        profile, binding = self._codex_identity()
        with tempfile.TemporaryDirectory() as directory, self._installed_codex():
            with self.assertRaisesRegex(
                ValidationError,
                "requires a pinned runtime_identity",
            ):
                CodexParticipant(
                    profile=profile,
                    config={"session_mode": "persistent", "model": "model-a"},
                    binding=binding,
                    state_directory=directory,
                )

    def test_codex_credential_binding_checks_the_file_backed_account(self):
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory)
            (codex_home / "auth.json").write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {
                            "account_id": "account-1",
                            "access_token": "secret-token",
                        },
                    }
                ),
                encoding="utf-8",
            )
            digest = _credential_binding(
                codex_home,
                auth_mode="chatgpt",
                expected_account_id="account-1",
                provider="openai",
                credential_scope="chatgpt:workspace-1",
            )
            self.assertEqual(64, len(digest))
            self.assertNotIn("secret-token", digest)
            with self.assertRaisesRegex(ValidationError, "account differs"):
                _credential_binding(
                    codex_home,
                    auth_mode="chatgpt",
                    expected_account_id="account-2",
                    provider="openai",
                    credential_scope="chatgpt:workspace-1",
                )

    def test_codex_atomic_state_failure_preserves_prior_committed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            state.write_bytes(b"prior")
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.os.write",
                    side_effect=OSError("write failed"),
                ),
                self.assertRaisesRegex(OSError, "write failed"),
            ):
                _atomic_write(state, b"replacement")
            self.assertEqual(b"prior", state.read_bytes())

    def test_codex_runtime_identity_is_rechecked_before_execution(self):
        profile, binding = self._codex_identity()
        with tempfile.TemporaryDirectory() as directory:
            binary, identity = self._persistent_runtime(directory)
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.shutil.which",
                    return_value=str(binary),
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_version",
                    return_value="codex-cli test",
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_auth_mode",
                    return_value="chatgpt",
                ),
            ):
                participant = CodexParticipant(
                    profile=profile,
                    config={
                        "session_mode": "persistent",
                        "model": "model-a",
                        "runtime_identity": identity,
                    },
                    binding=binding,
                    state_directory=directory,
                )
                binary.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "identity changed"):
                    participant._verify_runtime_identity()

    def test_codex_uses_shared_authenticated_reference_adapters(self):
        class Transport:
            def ordinary_action_capabilities(self):
                return ("message", "reply", "reaction")

            def reaction_capability(self):
                return None

            def dispatch(self, *, action, wake):
                return TransportResult("sent", "test")

        cases = {
            "discord": (
                "discord:actor:9",
                "42",
                {
                    "t": "MESSAGE_CREATE",
                    "s": 1,
                    "delivery_epoch": "gateway-a",
                    "d": {
                        "id": "100",
                        "channel_id": "42",
                        "author": {"id": "7", "username": "Zoe", "bot": False},
                        "content": "hello",
                        "mentions": [],
                        "mention_everyone": False,
                    },
                },
            ),
            "matrix": (
                "matrix:actor:@vigil:example",
                "!room:example",
                {
                    "room_id": "!room:example",
                    "event": {
                        "event_id": "$event",
                        "type": "m.room.message",
                        "sender": "@zoe:example",
                        "content": {"msgtype": "m.text", "body": "hello"},
                    },
                },
            ),
            "telegram": (
                "telegram:actor:9",
                "-42",
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 100,
                        "chat": {"id": -42},
                        "from": {"id": 7, "first_name": "Zoe", "is_bot": False},
                        "text": "hello",
                    },
                },
            ),
            "channel": (
                "custom:actor:9",
                "room-42",
                {
                    "delivery_id": "custom:delivery:1",
                    "room_id": "room-42",
                    "event": {
                        "id": "custom:message:100",
                        "type": "message",
                        "author_id": "custom:actor:7",
                        "text": "hello",
                        "mentioned_actor_ids": [],
                        "mentions_room": False,
                    },
                    "actors": {"custom:actor:7": {"kind": "human"}},
                },
            ),
        }
        ingress_key = "i" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o700)
            for surface, (actor_id, room_id, payload) in cases.items():
                with self.subTest(surface=surface):
                    case_root = root / surface
                    case_root.mkdir()
                    profile_path = case_root / "profile.json"
                    profile_bytes = json.dumps(
                        {
                            "profile_id": "vigil",
                            "participant_id": "vigil",
                            "actor_id": actor_id,
                            "instructions": "Contribute carefully.",
                            "provenance": "trusted:test",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                    profile_path.write_bytes(profile_bytes)
                    binding_platform = "custom" if surface == "channel" else surface
                    config = {
                        "schema_version": 2,
                        "binding": {
                            "participant_id": "vigil",
                            "actor_id": actor_id,
                            "platform": binding_platform,
                            "room_id": room_id,
                            "continuity_scope_id": f"{binding_platform}:{room_id}",
                        },
                        "profile": {
                            "path": str(profile_path),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                        },
                        "attention": {
                            "policy": {
                                "preattention_enabled": False,
                                "suppression_enabled": False,
                            },
                            "model": {},
                        },
                        "codex": {"session_mode": "fresh"},
                        "limits": {},
                        "state_directory": str(case_root / "state"),
                        **(
                            {
                                "ingress_auth": {
                                    "source_id": "trusted-channel-plugin",
                                    "hmac_key_env": "TEST_NUNCHI_INGRESS_KEY",
                                }
                            }
                            if surface == "channel"
                            else {}
                        ),
                    }
                    submitted = payload
                    if surface == "channel":
                        payload_sha256 = hashlib.sha256(
                            json.dumps(
                                payload,
                                sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=False,
                            ).encode()
                        ).hexdigest()
                        material = (
                            b"nunchi.channel.ingress.v1\0trusted-channel-plugin\0"
                            + payload_sha256.encode()
                        )
                        submitted = {
                            "payload": payload,
                            "authorization": {
                                "schema_version": 1,
                                "source_id": "trusted-channel-plugin",
                                "payload_sha256": payload_sha256,
                                "mac": hmac.new(
                                    ingress_key.encode(),
                                    material,
                                    hashlib.sha256,
                                ).hexdigest(),
                            },
                        }
                    with (
                        mock.patch.dict(
                            os.environ,
                            {"TEST_NUNCHI_INGRESS_KEY": ingress_key},
                            clear=False,
                        ),
                        mock.patch(
                            "nunchi.integrations.codex_v2.shutil.which",
                            return_value=str(binary),
                        ),
                    ):
                        runtime = ReferenceAdapterRuntime(
                            surface=surface,
                            config=config,
                            transport=Transport(),
                        )
                        first = runtime.process(submitted, live=False)
                        second = runtime.process(submitted, live=False)
                    self.assertEqual("codex", runtime.probe()["participant_backend"])
                    self.assertEqual("fresh", runtime.probe()["codex"]["session_mode"])
                    self.assertTrue(first.observation.wake_eligible)
                    self.assertFalse(second.observation.wake_eligible)
                    self.assertEqual(1, len(runtime.pipeline.observation.retained_events()))

    def test_generic_channel_rejects_unsigned_prompt_markup(self):
        from nunchi.adapters.runtime import ChannelIngressAuthenticator

        with mock.patch.dict(
            os.environ,
            {"TEST_NUNCHI_INGRESS_KEY": "i" * 32},
            clear=False,
        ):
            authenticator = ChannelIngressAuthenticator(
                {
                    "source_id": "trusted-channel-plugin",
                    "hmac_key_env": "TEST_NUNCHI_INGRESS_KEY",
                }
            )
        with self.assertRaisesRegex(ValidationError, "authenticated payload"):
            authenticator.unwrap(
                {
                    "delivery_id": "raw-prompt",
                    "room_id": "room-42",
                    "event": {"text": "<channel>hello</channel>"},
                    "actors": {},
                }
            )

    def test_codex_prompt_hook_blocks_raw_channel_markup_with_adapter_option(self):
        from nunchi.integrations.codex_ingress_hook import evaluate, main

        self.assertIsNone(
            evaluate(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "review this repository",
                }
            )
        )
        decision = evaluate(
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": '<channel source="discord">hello</channel>',
            }
        )
        self.assertEqual("block", decision["decision"])
        self.assertIn("nunchi-discord", decision["reason"])

        stderr = io.StringIO()
        self.assertEqual(
            2,
            main(
                stdin=io.StringIO("not-json"),
                stdout=io.StringIO(),
                stderr=stderr,
            ),
        )
        self.assertIn("could not validate", stderr.getvalue())

        hooks = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "integrations"
                / "codex"
                / "nunchi-codex"
                / "hooks"
                / "hooks.json"
            ).read_text(encoding="utf-8")
        )
        command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertEqual("nunchi-codex-ingress-hook", command)

    def test_codex_task_is_staged_until_host_acceptance(self):
        profile, binding = self._codex_identity()
        wake = self._wake()
        opportunity = {
            "generation": 1,
            "lifecycle_id": "lifecycle-1",
            "deadline_id": "deadline-1",
            "permissions": {
                "revision": "permissions-1",
                "ordinary_actions": ["message", "reply", "reaction"],
                "privileged_proposals": True,
            },
        }
        protocol = ParticipantTurnProtocol(
            profile=profile,
            wake=wake,
            opportunity=opportunity,
        )
        action = {
            "protocol": protocol.request["protocol"],
            "binding": protocol.request["binding"],
            "action": {"kind": "silence"},
        }
        task_id = "019f9432-9300-7dd1-8225-d7f10f921968"
        stdout = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": task_id}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": json.dumps(
                                {"action_json": json.dumps(action)}
                            ),
                        },
                    }
                ),
            )
        )

        class Process:
            returncode = 0

            def poll(self):
                return 0

            def communicate(self):
                return stdout, ""

        with tempfile.TemporaryDirectory() as directory:
            binary, identity = self._persistent_runtime(directory)
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.shutil.which",
                    return_value=str(binary),
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_version",
                    return_value="codex-cli test",
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_auth_mode",
                    return_value="chatgpt",
                ),
            ):
                participant = CodexParticipant(
                    profile=profile,
                    config={
                        "session_mode": "persistent",
                        "model": "model-a",
                        "runtime_identity": identity,
                    },
                    binding=binding,
                    state_directory=directory,
                )
            with mock.patch(
                "nunchi.integrations.codex_v2.subprocess.Popen",
                return_value=Process(),
            ), mock.patch.object(participant, "_verify_runtime_identity"):
                self.assertIsNone(
                    participant.run_protocol(
                        wake=wake,
                        opportunity=opportunity,
                        expand=lambda **_: {},
                        cancel=threading.Event(),
                    )
                )
            self.assertEqual(1, participant.pending_task_count)
            self.assertFalse(participant.session_path.exists())

            journal = object.__new__(CodexTaskReceiptJournal)
            journal.participant = participant
            accepted = {
                "request_id": "r",
                "stage": "participant-host",
                "writer": "participant-host",
                "body": {"outcome": "silent"},
            }
            with mock.patch(
                "nunchi.integrations.codex_v2.ReceiptJournal.append",
                return_value=accepted,
            ):
                CodexTaskReceiptJournal.append(
                    journal,
                    accepted,
                    writer="participant-host",
                )
            self.assertEqual(0, participant.pending_task_count)
            self.assertEqual(task_id, participant._load_session())

    def test_failed_or_malformed_codex_turn_never_stages_task_state(self):
        profile, binding = self._codex_identity()
        wake = self._wake()
        opportunity = {
            "generation": 1,
            "lifecycle_id": "lifecycle-1",
            "deadline_id": "deadline-1",
            "permissions": {
                "revision": "permissions-1",
                "ordinary_actions": ["message", "reply", "reaction"],
                "privileged_proposals": True,
            },
        }
        protocol = ParticipantTurnProtocol(
            profile=profile,
            wake=wake,
            opportunity=opportunity,
        )
        action = {
            "protocol": protocol.request["protocol"],
            "binding": protocol.request["binding"],
            "action": {"kind": "silence"},
        }
        task_id = "019f9432-9300-7dd1-8225-d7f10f921968"

        class Process:
            def __init__(self, returncode, final_text):
                self.returncode = returncode
                self.final_text = final_text

            def poll(self):
                return self.returncode

            def communicate(self):
                return (
                    "\n".join(
                        (
                            json.dumps(
                                {"type": "thread.started", "thread_id": task_id}
                            ),
                            json.dumps(
                                {
                                    "type": "item.completed",
                                    "item": {
                                        "type": "agent_message",
                                        "text": self.final_text,
                                    },
                                }
                            ),
                        )
                    ),
                    "failed",
                )

        cases = (
            Process(7, json.dumps({"action_json": json.dumps(action)})),
            Process(0, json.dumps({"action_json": "not-json"})),
        )
        with tempfile.TemporaryDirectory() as directory:
            binary, identity = self._persistent_runtime(directory)
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.shutil.which",
                    return_value=str(binary),
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_version",
                    return_value="codex-cli test",
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_auth_mode",
                    return_value="chatgpt",
                ),
            ):
                participant = CodexParticipant(
                    profile=profile,
                    config={
                        "session_mode": "persistent",
                        "model": "model-a",
                        "runtime_identity": identity,
                    },
                    binding=binding,
                    state_directory=directory,
                )
            for process in cases:
                with (
                    self.subTest(returncode=process.returncode),
                    mock.patch(
                        "nunchi.integrations.codex_v2.subprocess.Popen",
                        return_value=process,
                    ),
                    mock.patch.object(participant, "_verify_runtime_identity"),
                    self.assertRaises(RuntimeError),
                ):
                    participant.run_protocol(
                        wake=wake,
                        opportunity=opportunity,
                        expand=lambda **_: {},
                        cancel=threading.Event(),
                    )
                self.assertEqual(0, participant.pending_task_count)
                self.assertFalse(participant.session_path.exists())

            participant._save_session(task_id)
            malformed_resume = Process(
                0,
                json.dumps({"action_json": "not-json"}),
            )
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.subprocess.Popen",
                    return_value=malformed_resume,
                ),
                mock.patch.object(participant, "_verify_runtime_identity"),
                self.assertRaises(RuntimeError),
            ):
                participant.run_protocol(
                    wake=wake,
                    opportunity=opportunity,
                    expand=lambda **_: {},
                    cancel=threading.Event(),
                )
            self.assertFalse(participant.session_path.exists())
            self.assertTrue(participant.inflight_session_path.exists())
            self.assertEqual("reset-required", participant.session_status()["status"])

    def test_fresh_mode_and_reduced_capability_are_reported_truthfully(self):
        profile, binding = self._codex_identity()
        with tempfile.TemporaryDirectory() as directory, self._installed_codex():
            participant = CodexParticipant(
                profile=profile,
                config={"session_mode": "fresh", "capability_mode": "reduced"},
                binding=binding,
                state_directory=directory,
            )
            self.assertEqual("fresh", participant.session_status()["mode"])
            self.assertFalse(participant.session_path.exists())
            with self.assertRaisesRegex(
                ValidationError,
                "final-effect bridge",
            ):
                CodexParticipant(
                    profile=profile,
                    config={
                        "session_mode": "fresh",
                        "capability_mode": "configured",
                    },
                    binding=binding,
                    state_directory=directory,
                )

    def test_corrupt_task_state_is_reported_as_incompatible(self):
        profile, binding = self._codex_identity()
        with tempfile.TemporaryDirectory() as directory:
            binary, identity = self._persistent_runtime(directory)
            with (
                mock.patch(
                    "nunchi.integrations.codex_v2.shutil.which",
                    return_value=str(binary),
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_version",
                    return_value="codex-cli test",
                ),
                mock.patch(
                    "nunchi.integrations.codex_v2._codex_auth_mode",
                    return_value="chatgpt",
                ),
            ):
                participant = CodexParticipant(
                    profile=profile,
                    config={
                        "session_mode": "persistent",
                        "model": "model-a",
                        "runtime_identity": identity,
                    },
                    binding=binding,
                    state_directory=directory,
                )
            participant.session_path.write_text("not-json", encoding="utf-8")
            status = participant.session_status()
            self.assertEqual("incompatible", status["status"])
            self.assertFalse(status["compatible"])
            self.assertIn("quarantine", status["repair"])

    def test_codex_registers_and_rejects_wrong_target_before_observation(self):
        secret = "s" * 32
        verifier = ToolAuthorizer(
            secret=secret.encode(),
            participant_routes={"vigil": frozenset({"42"})},
        )

        class Client:
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
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "registered": True,
                                    "participant_id": "vigil",
                                    "room_id": "42",
                                    "transport_self_actor_id": "discord:actor:9",
                                }
                            ),
                        }
                    ],
                }

        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "profile.json"
            profile_data = {
                "profile_id": "vigil",
                "participant_id": "vigil",
                "actor_id": "discord:actor:9",
                "instructions": "Contribute carefully.",
                "provenance": "trusted:test",
            }
            raw = json.dumps(profile_data).encode()
            profile_path.write_bytes(raw)
            config = {
                "schema_version": 2,
                "binding": {
                    "participant_id": "vigil",
                    "actor_id": "discord:actor:9",
                    "platform": "discord",
                    "room_id": "42",
                    "continuity_scope_id": "discord:42",
                },
                "profile": {
                    "path": str(profile_path),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
                "attention": {
                    "policy": {"preattention_enabled": False},
                    "model": {},
                },
                "limits": {},
                "state_directory": directory,
                "transport": {
                    "url": "http://127.0.0.1:3993/mcp",
                    "timeout_seconds": 5,
                    "output_key_env": "TEST_NUNCHI_OUTPUT_KEY",
                },
                "codex": {"session_mode": "fresh"},
            }
            with (
                mock.patch.dict(
                    os.environ,
                    {"TEST_NUNCHI_OUTPUT_KEY": secret},
                    clear=False,
                ),
                self._installed_codex(),
            ):
                runtime = CodexRoomRuntime(config, Client())
            probe = runtime.probe()
            self.assertEqual("fresh", probe["session_mode"])
            self.assertFalse(probe["persistent_session"])
            self.assertEqual("reduced", probe["capability_mode"])
            self.assertTrue(probe["disabled_capabilities"])
            runtime.register_transport()
            before = runtime.pipeline.observation.retained_events()
            with self.assertRaises(ValidationError):
                runtime.handle(
                    {
                        "schema_version": 2,
                        "delivery_id": "d1",
                        "room_id": "42",
                        "event": None,
                        "actors": {},
                        "continuity_gap": False,
                        "target_participant_id": "other",
                        "transport_self_actor_id": "discord:actor:9",
                    }
                )
            self.assertEqual(before, runtime.pipeline.observation.retained_events())

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
                                    "action_json": json.dumps(
                                        {
                                            "kind": "message",
                                            "origin_event_id": "discord:message:1",
                                            "text": "hello",
                                        }
                                    )
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

    def test_codex_jsonl_parser_rejects_malformed_action_envelope(self):
        for text in (
            '{"kind":"silence"}',
            '{"action_json":"not-json"}',
            '{"action_json":"[]"}',
            '{"action_json":"{\\"kind\\":\\"silence\\"}","extra":true}',
        ):
            with self.subTest(text=text):
                _, action = _parse_codex_output(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "agent_message",
                                "text": text,
                            },
                        }
                    )
                )
                self.assertIsNone(action)

    def test_codex_mcp_transport_binds_exact_output(self):
        secret = b"y" * 32
        verifier = ToolAuthorizer(
            secret=secret,
            participant_routes={"vigil": frozenset({"42"})},
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
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "message": {
                                        "message_id": "101",
                                        "channel_id": "42",
                                        "author_id": "9",
                                        "author_is_bot": True,
                                        "content": "hello",
                                        "reply_to_message_id": None,
                                    }
                                }
                            ),
                        }
                    ],
                }

        client = Client()
        transport = MCPDiscordTransport(
            client,
            "42",
            "vigil",
            "discord:actor:9",
            secret,
        )
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
        self.assertEqual(TransportResult("sent", "discord:message:101"), result)
        self.assertEqual(
            [("send_message", {"channel_id": "42", "content": "hello"})],
            client.calls,
        )

    def test_codex_mcp_transport_consumes_only_exact_measured_capability(self):
        class Client:
            channel_id = "42"
            actor_id = "9"

            def call_tool(self, name, _arguments):
                self.asserted_name = name
                payload = {
                    "reaction_capability": {
                        "channel_id": self.channel_id,
                        "actor_id": self.actor_id,
                        "capability": {
                            "supported": True,
                            "authenticated": True,
                            "operations": ["add", "remove"],
                            "reactions": ["*"],
                            "permissions_revision": "measured-v1",
                        },
                    }
                }
                return {
                    "isError": False,
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                }

        client = Client()
        transport = MCPDiscordTransport(
            client,
            "42",
            "vigil",
            "discord:actor:9",
            b"y" * 32,
        )
        measured = transport.reaction_capability()
        self.assertEqual("reaction_capability", client.asserted_name)
        self.assertTrue(measured.allows("👂", "add"))

        client.channel_id = "43"
        unbound = transport.reaction_capability()
        self.assertFalse(unbound.supported)
        self.assertFalse(unbound.authenticated)

    def test_codex_mcp_transport_treats_unattested_success_as_unknown(self):
        class Client:
            def call_tool(self, _name, _arguments):
                return {"isError": False, "content": []}

        transport = MCPDiscordTransport(
            Client(),
            "42",
            "vigil",
            "discord:actor:9",
            b"y" * 32,
        )
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
        self.assertEqual("unknown", result.delivery)

    def test_codex_mcp_transport_preserves_post_effect_unknown(self):
        class Client:
            def call_tool(self, _name, _arguments):
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "delivery": {
                                        "status": "unknown",
                                        "detail": (
                                            "Discord create-message "
                                            "acknowledgement was lost"
                                        ),
                                    }
                                }
                            ),
                        }
                    ],
                }

        transport = MCPDiscordTransport(
            Client(),
            "42",
            "vigil",
            "discord:actor:9",
            b"y" * 32,
        )
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
        self.assertEqual("unknown", result.delivery)

    def test_codex_mcp_reply_requires_exact_effect_and_self(self):
        class Client:
            message = {}

            def call_tool(self, _name, _arguments):
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"message": self.message}),
                        }
                    ],
                }

        client = Client()
        transport = MCPDiscordTransport(
            client,
            "42",
            "vigil",
            "discord:actor:9",
            b"y" * 32,
        )
        action = {
            "kind": "reply",
            "origin_event_id": "discord:message:1",
            "target_event_id": "discord:message:77",
            "text": "expected",
        }
        wake = {
            "request_id": "request-1",
            "self": {"participant_id": "vigil"},
            "room": {"id": "42"},
        }
        valid = {
            "message_id": "101",
            "channel_id": "42",
            "author_id": "9",
            "author_is_bot": True,
            "content": "expected",
            "reply_to_message_id": "77",
        }
        client.message = valid
        self.assertEqual(
            "sent",
            transport.dispatch(action=action, wake=wake).delivery,
        )
        for mutation in (
            {"content": "DIFFERENT"},
            {"reply_to_message_id": "88"},
            {"author_id": "10"},
        ):
            with self.subTest(mutation=mutation):
                client.message = {**valid, **mutation}
                self.assertEqual(
                    "unknown",
                    transport.dispatch(action=action, wake=wake).delivery,
                )

    def test_codex_mcp_reaction_requires_exact_echo(self):
        class Client:
            wrong = False

            def call_tool(self, name, arguments):
                payload = {
                    "reaction": {
                        "channel_id": arguments["channel_id"],
                        "message_id": (
                            "999" if self.wrong else arguments["message_id"]
                        ),
                        "reaction": arguments["reaction"],
                        "operation": "add" if name == "add_reaction" else "remove",
                    }
                }
                return {
                    "isError": False,
                    "content": [
                        {"type": "text", "text": json.dumps(payload)}
                    ],
                }

        client = Client()
        transport = MCPDiscordTransport(
            client,
            "42",
            "vigil",
            "discord:actor:9",
            b"y" * 32,
        )
        action = {
            "kind": "reaction",
            "origin_event_id": "discord:message:1",
            "target_event_id": "discord:message:101",
            "reaction": "✅",
            "operation": "add",
        }
        wake = {
            "request_id": "request-1",
            "self": {"participant_id": "vigil"},
            "room": {"id": "42"},
        }
        self.assertEqual(
            "sent",
            transport.dispatch(action=action, wake=wake).delivery,
        )
        client.wrong = True
        self.assertEqual(
            "unknown",
            transport.dispatch(action=action, wake=wake).delivery,
        )

    def test_mcp_json_response_must_correlate_request_id(self):
        class Response(io.BytesIO):
            headers = {"content-type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        client = StreamableMCPClient("http://127.0.0.1:3993/mcp")
        client.session_id = "session"
        client._post = mock.Mock(
            return_value=Response(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 999,
                        "result": {"isError": False, "content": []},
                    }
                ).encode()
            )
        )
        with self.assertRaises(RuntimeError):
            client.call_tool("send_message", {})

        valid = StreamableMCPClient("http://127.0.0.1:3993/mcp")
        valid.session_id = "session"
        valid._post = mock.Mock(
            return_value=Response(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "isError": False,
                            "content": [{"type": "text", "text": "{}"}],
                        },
                    }
                ).encode()
            )
        )
        self.assertEqual(
            {
                "isError": False,
                "content": [{"type": "text", "text": "{}"}],
            },
            valid.call_tool("send_message", {}),
        )

    def test_mcp_client_pins_canonical_streamable_http_path(self):
        bare = StreamableMCPClient("http://127.0.0.1:3993/mcp")
        canonical = StreamableMCPClient("http://127.0.0.1:3993/mcp/")

        self.assertEqual("http://127.0.0.1:3993/mcp/", bare.url)
        self.assertEqual("http://127.0.0.1:3993/mcp/", canonical.url)


class NativeAcknowledgementTests(unittest.TestCase):
    def test_matrix_missing_event_id_is_unknown(self):
        with mock.patch.dict(
            os.environ,
            {"MATRIX_TOKEN": "secret"},
            clear=False,
        ):
            transport = MatrixTransport(
                {
                    "homeserver": "https://matrix.example",
                    "access_token_env": "MATRIX_TOKEN",
                }
            )
        transport._request = mock.Mock(return_value={})
        result = transport.dispatch(
            action={
                "kind": "message",
                "origin_event_id": "matrix:event:$1",
                "text": "hello",
            },
            wake={"room": {"id": "!room:example"}},
        )
        self.assertEqual("unknown", result.delivery)

    def test_telegram_missing_or_wrong_message_identity_is_unknown(self):
        with mock.patch.dict(
            os.environ,
            {"TELEGRAM_TOKEN": "secret"},
            clear=False,
        ):
            transport = TelegramTransport(
                {"bot_token_env": "TELEGRAM_TOKEN"}
            )
        wake = {"room": {"id": "42"}}
        action = {
            "kind": "message",
            "origin_event_id": "telegram:message:42:1",
            "text": "hello",
        }
        for response in ({}, {"message_id": 7, "chat": {"id": 43}}):
            with self.subTest(response=response):
                transport._call = mock.Mock(return_value=response)
                self.assertEqual(
                    "unknown",
                    transport.dispatch(action=action, wake=wake).delivery,
                )
        transport._call = mock.Mock(
            return_value={"message_id": 7, "chat": {"id": 42}}
        )
        self.assertEqual(
            TransportResult("sent", "telegram:message:42:7"),
            transport.dispatch(action=action, wake=wake),
        )


if __name__ == "__main__":
    unittest.main()
