from __future__ import annotations

from copy import deepcopy
import hashlib
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
from nunchi.adapters.matrix import MatrixTransport
from nunchi.adapters.telegram import TelegramTransport
from nunchi.adapters.discord import DiscordPyTransport, DurableGatewaySequence
from nunchi.errors import ValidationError
from nunchi.attention import ParticipantProfile
from nunchi.integrations.codex_v2 import (
    CodexParticipant,
    CodexRoomRuntime,
    MCPDiscordTransport,
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
    def test_discord_ack_capability_tracks_exact_room_permissions(self):
        class Permissions:
            def __init__(self, allowed):
                self.view_channel = allowed
                self.read_message_history = allowed
                self.add_reactions = allowed

        class Channel:
            def __init__(self):
                self.allowed = True

            def permissions_for(self, _user):
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

    def test_codex_persistent_task_is_bound_to_profile_actor_room_and_behavior(self):
        profile, binding = self._codex_identity()
        thread_id = "019f9432-9300-7dd1-8225-d7f10f921968"
        with tempfile.TemporaryDirectory() as directory, self._installed_codex():
            first = CodexParticipant(
                profile=profile,
                config={"session_mode": "persistent", "model": "model-a"},
                binding=binding,
                state_directory=directory,
            )
            first._save_session(thread_id)
            self.assertEqual(thread_id, first._load_session())
            changed = CodexParticipant(
                profile=profile,
                config={"session_mode": "persistent", "model": "model-b"},
                binding=binding,
                state_directory=directory,
            )
            with self.assertRaises(RuntimeError):
                changed._load_session()

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
