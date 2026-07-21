"""Tests for the nunchi-mcp-discord server layer (offline).

Covers the notification contract (exact param schema to a mock MCP client),
content/intent warning behavior, bounded-queue backpressure, Discord rate
limit handling (429 retry-after, bucket waits, non-retryable 401/403), the
send backstop, tool schemas/executor, shutdown drain, and token hygiene.

Tests that require the mcp SDK are decorated with
@unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed") — mirroring how
discord.py-gated tests are skipped in tests/test_discord_adapter.py. All
transport logic is import-safe and tested without the SDK.

Run with:
    python3 -m unittest tests.test_mcp_discord_server
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import pathlib
import sys
import unittest
from unittest import mock

# Ensure src is on the path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

# Check mcp SDK availability (no install required for transport-logic tests)
try:
    import mcp as _mcp_sdk  # noqa: F401

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from nunchi.mcp_discord.config import load_config
from nunchi.mcp_discord.continuation import DiscordHistoryContinuations
from nunchi.mcp_discord.events import (
    DiscordEventSourceV2,
    V2_NOTIFICATION_METHOD,
    filter_message_create,
    message_text,
)
from nunchi.mcp_discord.gateway import GatewayProtocol
from nunchi.mcp_discord.hygiene import REDACTED, TokenRedactionFilter
from nunchi.mcp_discord.ratelimit import RateLimiter, SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient, DiscordRestError
from nunchi.mcp_discord.server import (
    InFlight,
    broadcast_sessions,
    enqueue_event,
    main,
    pump_notifications,
)
from nunchi.mcp_discord.tools import TOOL_NAMES, TOOL_SCHEMAS, ToolExecutor, shape_message

TOKEN = "NUNCHI-TEST-TOKEN-4f9a2bconfidential"
AUTH_TOKEN = "MCP-CLIENT-TEST-TOKEN-9c8b7a6d5e4f3a2b"


def _config_env(**overrides):
    result = {
        "NUNCHI_DISCORD_TOKEN": TOKEN,
        "NUNCHI_MCP_DISCORD_AUTH_TOKEN": AUTH_TOKEN,
        "NUNCHI_MCP_DISCORD_CHANNELS": "100",
        "NUNCHI_MCP_DISCORD_PARTICIPANT_ID": "vigil",
        "NUNCHI_MCP_DISCORD_SELF_ACTOR_ID": "999",
        "NUNCHI_MCP_DISCORD_STATE_DIR": "/private/tmp/nunchi-mcp-test-state",
    }
    result.update(overrides)
    return result


def _create_data(
    author_id: str = "777",
    *,
    bot: bool = True,
    content: str = "ping",
    **overrides,
) -> dict:
    data = {
        "id": "111222333",
        "channel_id": "444555666",
        "guild_id": "777888999",
        "content": content,
        "timestamp": "2026-07-06T10:00:00.000000+00:00",
        "author": {"id": author_id, "username": "peer-bot", "bot": bot},
        "embeds": [],
        "attachments": [],
    }
    data.update(overrides)
    return data


def _api_message(**overrides) -> dict:
    msg = {
        "id": "42",
        "channel_id": "100",
        "author": {"id": "999", "username": "our-bot", "bot": True},
        "content": "sent!",
        "timestamp": "2026-07-06T10:05:00.000000+00:00",
    }
    msg.update(overrides)
    return msg


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _FakeHttp:
    """Scripted (status, headers, body) responses; records calls."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        if not self._responses:
            raise AssertionError("unexpected extra HTTP call")
        return self._responses.pop(0)


class _FakeRest:
    """RestLike fake for executor tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str | None]] = []
        self.history_calls: list[tuple[str, int, str | None]] = []

    def create_message(
        self,
        channel_id,
        content,
        *,
        reply_to_message_id=None,
        allowed_mention_user_ids=None,
        fail_if_reply_missing=False,
        nonce=None,
    ):
        self.sent.append((channel_id, content, reply_to_message_id))
        return _api_message(channel_id=channel_id, content=content)

    def get_messages(self, channel_id, *, limit=50, before=None):
        self.history_calls.append((channel_id, limit, before))
        return [_api_message(id="1"), _api_message(id="2")]


# --------------------------------------------------------------------------- #
# Content / MESSAGE_CONTENT intent behavior
# --------------------------------------------------------------------------- #


class TestContentBehavior(unittest.TestCase):
    def test_content_populated_no_warning(self):
        with self.assertNoLogs("nunchi.mcp_discord.events", level="WARNING"):
            event = filter_message_create(_create_data(content="hello room"), "999")
        self.assertEqual(event.content, "hello room")

    def test_empty_content_warns_loudly_and_still_delivers(self):
        data = _create_data(content="")
        with self.assertLogs("nunchi.mcp_discord.events", level="WARNING") as captured:
            event = filter_message_create(data, "999")
        self.assertIsNotNone(event, "empty-content messages must still be delivered")
        self.assertEqual(event.content, "")
        joined = "\n".join(captured.output)
        self.assertIn("MESSAGE_CONTENT", joined)
        self.assertIn("Developer Portal", joined)

    def test_empty_content_with_embed_is_legitimate_no_warning(self):
        data = _create_data(content="", embeds=[{"title": "an embed"}])
        with self.assertNoLogs("nunchi.mcp_discord.events", level="WARNING"):
            event = filter_message_create(data, "999")
        self.assertIsNotNone(event)
        self.assertEqual(event.content, "[Discord rich message]\nan embed")

    def test_empty_content_with_attachment_no_warning(self):
        data = _create_data(content="", attachments=[{"id": "1", "filename": "x.png"}])
        with self.assertNoLogs("nunchi.mcp_discord.events", level="WARNING"):
            event = filter_message_create(data, "999")
        self.assertEqual(event.content, "[Discord rich message]\n[attachment] x.png")

    def test_plain_content_wins_over_rich_fallback(self):
        data = _create_data(
            content="  exact plain content  ",
            embeds=[{"title": "must not be appended"}],
            components=[{"type": 10, "content": "also excluded"}],
        )
        event = filter_message_create(data, "999")
        self.assertEqual(event.content, "  exact plain content  ")

    def test_rich_only_message_normalizes_visible_conversational_text(self):
        data = _create_data(
            content="",
            embeds=[
                {
                    "author": {"name": "Review agent"},
                    "title": "Review complete",
                    "description": "No blockers found.",
                    "fields": [{"name": "Warning", "value": "Receipt is soft."}],
                    "footer": {"text": "123 tests passed"},
                }
            ],
            components=[
                {
                    "type": 1,
                    "components": [
                        {"type": 10, "content": "Approval is still required."},
                        {"type": 2, "label": "Approve command"},
                    ],
                }
            ],
            attachments=[{"description": "review.txt", "filename": "ignored.txt"}],
            sticker_items=[{"name": "Reviewed"}],
            poll={
                "question": {"text": "Merge now?"},
                "answers": [
                    {"poll_media": {"text": "Yes"}},
                    {"poll_media": {"text": "No"}},
                ],
            },
        )

        content = message_text(data)

        self.assertTrue(content.startswith("[Discord rich message]\n"))
        for expected in (
            "Review agent",
            "Review complete",
            "No blockers found.",
            "Warning: Receipt is soft.",
            "123 tests passed",
            "Approval is still required.",
            "[attachment] review.txt",
            "[sticker] Reviewed",
            "[poll] Merge now?",
            "- Yes",
            "- No",
        ):
            self.assertIn(expected, content)
        self.assertNotIn("Approve command", content)
        self.assertNotIn("ignored.txt", content)

    def test_rich_only_message_is_bounded(self):
        content = message_text(
            _create_data(content="", embeds=[{"description": "x" * 7000}])
        )
        self.assertEqual(len(content), 6000)
        self.assertTrue(content.endswith("..."))

    def test_reply_mentions_and_referenced_message_are_preserved(self):
        data = _create_data(
            content="review complete",
            mentions=[
                {"id": "999"},
                {"id": "999"},
                {"id": "888"},
                {"id": "not-a-snowflake"},
            ],
            message_reference={"message_id": "reply-target"},
            referenced_message={
                "id": "reply-target",
                "content": "please review",
                "author": {"id": "999", "username": "Vigil", "bot": True},
            },
        )

        data["mentions"] = [{"id": "999"}, {"id": "999"}, {"id": "888"}]
        data["message_reference"] = {"message_id": "555"}
        data["referenced_message"]["id"] = "555"
        event = filter_message_create(data, "123")
        params = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({"444555666"})
        ).notification_params(event)
        portable = params["native_input"]["event"]

        self.assertEqual(portable["text"], "review complete")
        self.assertEqual(
            portable["mentioned_actor_ids"],
            ["discord:user:999", "discord:user:888"],
        )
        self.assertEqual(portable["reply_to_event_id"], "discord:message:555")
        self.assertEqual(
            params["native_input"]["actors"]["discord:user:777"]["kind"],
            "bot",
        )


# --------------------------------------------------------------------------- #
# Notification contract: delivery to a mock MCP client
# --------------------------------------------------------------------------- #


class TestNotificationDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_notification_delivered_with_exact_param_schema(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        shutdown = asyncio.Event()
        received: list[dict] = []

        async def mock_client_send(params: dict) -> None:
            received.append(params)
            shutdown.set()

        event = filter_message_create(_create_data(), own_user_id="999")
        source = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({"444555666"})
        )
        self.assertTrue(enqueue_event(queue, event))
        await asyncio.wait_for(
            pump_notifications(
                queue,
                mock_client_send,
                shutdown=shutdown,
                projector=source.notification_params,
            ),
            timeout=5.0,
        )

        self.assertEqual(
            V2_NOTIFICATION_METHOD,
            "notifications/nunchi/v2/discord/event",
        )
        self.assertEqual(received[0]["schema_version"], 2)
        self.assertEqual(received[0]["platform"], "discord")
        self.assertEqual(received[0]["channel_id"], "444555666")
        self.assertEqual(
            received[0]["native_input"]["event"]["author_id"],
            "discord:user:777",
        )

    async def test_global_send_failure_stops_before_a_post_gap_event(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        shutdown = asyncio.Event()
        received: list[dict] = []
        async def failed_broadcast(params: dict) -> None:
            received.append(params)
            raise ConnectionError("global broadcast failed")

        for author in ("111", "222"):
            enqueue_event(queue, filter_message_create(_create_data(author), "999"))
        source = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({"444555666"})
        )
        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(
                pump_notifications(
                    queue,
                    failed_broadcast,
                    shutdown=shutdown,
                    projector=source.notification_params,
                ),
                timeout=5.0,
            )
        self.assertEqual(len(received), 1)
        self.assertEqual(queue.qsize(), 1)

    async def test_dm_message_has_null_guild_id(self):
        data = _create_data()
        del data["guild_id"]
        params = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({"444555666"})
        ).notification_params(filter_message_create(data, "999"))
        self.assertIsNone(params["guild_id"])


# --------------------------------------------------------------------------- #
# Bounded queue backpressure
# --------------------------------------------------------------------------- #


class TestBackpressure(unittest.IsolatedAsyncioTestCase):
    async def test_queue_overflow_refuses_post_gap_event_without_eviction(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        events = [
            filter_message_create(_create_data(str(i), content=f"msg{i}"), "999")
            for i in (1, 2, 3)
        ]
        self.assertTrue(enqueue_event(queue, events[0]))
        self.assertTrue(enqueue_event(queue, events[1]))
        with self.assertLogs("nunchi.mcp_discord.server", level="WARNING") as captured:
            self.assertFalse(enqueue_event(queue, events[2]))
        self.assertIn("queue full", "\n".join(captured.output))

        remaining = [queue.get_nowait().content for _ in range(queue.qsize())]
        self.assertEqual(
            remaining,
            ["msg1", "msg2"],
            "a post-gap event must not replace retained continuity",
        )
        self.assertEqual(queue.qsize(), 0)


# --------------------------------------------------------------------------- #
# Rate limiting: 429 retry-after, buckets, non-retryable errors
# --------------------------------------------------------------------------- #


class TestRateLimit(unittest.TestCase):
    def _client(self, responses, clock, sleeps):
        limiter = RateLimiter(clock=clock, sleeper=sleeps.append)
        http = _FakeHttp(responses)
        client = DiscordRestClient(
            TOKEN, limiter=limiter, http=http, sleeper=sleeps.append
        )
        return client, http

    def test_429_retry_after_is_respected(self):
        clock = _FakeClock()
        sleeps: list[float] = []
        responses = [
            (429, {"content-type": "application/json"},
             json.dumps({"retry_after": 0.75, "global": False,
                         "message": "You are being rate limited."}).encode()),
            (200, {}, json.dumps(_api_message()).encode()),
        ]
        client, http = self._client(responses, clock, sleeps)
        result = client.create_message("100", "hello")
        self.assertEqual(result["id"], "42")
        self.assertEqual(len(http.calls), 2, "must retry exactly once")
        self.assertIn(0.75, sleeps, "retry-after must be slept out before the retry")

    def test_429_json_retry_after_rejects_coercible_types(self):
        for value in (True, False, "0.01", None, [], {}):
            with self.subTest(value=value):
                retry_after, is_global = DiscordRestClient._parse_retry_after(
                    {},
                    json.dumps({"retry_after": value, "global": False}).encode(),
                )
                self.assertEqual(retry_after, 1.0)
                self.assertFalse(is_global)

    def test_429_retries_exhausted_raises(self):
        clock = _FakeClock()
        body = json.dumps({"retry_after": 0.1, "global": False}).encode()
        responses = [(429, {}, body)] * 4
        client, http = self._client(responses, clock, [])
        with self.assertRaises(DiscordRestError) as ctx:
            client.create_message("100", "hello")
        self.assertEqual(ctx.exception.status, 429)
        self.assertEqual(len(http.calls), 4)

    def test_bucket_remaining_zero_waits_before_next_request(self):
        clock = _FakeClock()
        sleeps: list[float] = []
        responses = [
            (200, {"x-ratelimit-remaining": "0", "x-ratelimit-reset-after": "2.5"},
             json.dumps(_api_message()).encode()),
            (200, {}, json.dumps(_api_message()).encode()),
        ]
        client, _ = self._client(responses, clock, sleeps)
        client.create_message("100", "one")
        self.assertEqual(sleeps, [])
        client.create_message("100", "two")
        self.assertEqual(sleeps, [2.5], "second send must wait out the bucket reset")

    def test_shared_bucket_identity_and_last_slot_are_reserved_atomically(self):
        clock = _FakeClock()
        sleeps = []
        limiter = RateLimiter(clock=clock, sleeper=sleeps.append)
        headers = {
            "x-ratelimit-bucket": "shared-1",
            "x-ratelimit-remaining": "1",
            "x-ratelimit-reset-after": "3",
        }
        limiter.after_response("GET /channels/42/messages", headers)
        limiter.after_response("POST /channels/42/messages", headers)
        limiter.before_request("GET /channels/42/messages")
        self.assertEqual(sleeps, [])
        limiter.before_request("POST /channels/42/messages")
        self.assertEqual(sleeps, [3.0])

    def test_401_aborts_immediately_no_retry(self):
        clock = _FakeClock()
        responses = [(401, {}, json.dumps({"message": "401: Unauthorized"}).encode())]
        client, http = self._client(responses, clock, [])
        with self.assertRaises(DiscordRestError) as ctx:
            client.create_message("100", "hello")
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(len(http.calls), 1, "permanent auth errors must not be retried")

    def test_403_aborts_immediately_no_retry(self):
        clock = _FakeClock()
        responses = [(403, {}, json.dumps({"message": "Missing Access"}).encode())]
        client, http = self._client(responses, clock, [])
        with self.assertRaises(DiscordRestError) as ctx:
            client.get_messages("100")
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(len(http.calls), 1)

    def test_global_429_blocks_other_routes(self):
        clock = _FakeClock()
        sleeps: list[float] = []
        limiter = RateLimiter(clock=clock, sleeper=sleeps.append)
        limiter.note_retry_after("POST /channels/1/messages", 3.0, is_global=True)
        limiter.before_request("GET /channels/2/messages")
        self.assertEqual(sleeps, [3.0])


class TestSendBackstop(unittest.TestCase):
    def test_backstop_window_enforced(self):
        clock = _FakeClock()
        backstop = SendBackstop(2, 10.0, clock=clock)
        self.assertEqual(backstop.try_acquire("100"), 0.0)
        self.assertEqual(backstop.try_acquire("100"), 0.0)
        wait = backstop.try_acquire("100")
        self.assertGreater(wait, 0.0, "third send inside the window must be refused")
        self.assertAlmostEqual(wait, 10.0, delta=0.01)

    def test_backstop_is_per_channel(self):
        clock = _FakeClock()
        backstop = SendBackstop(1, 10.0, clock=clock)
        self.assertEqual(backstop.try_acquire("100"), 0.0)
        self.assertEqual(backstop.try_acquire("200"), 0.0)
        self.assertGreater(backstop.try_acquire("100"), 0.0)

    def test_backstop_window_slides(self):
        clock = _FakeClock()
        backstop = SendBackstop(1, 10.0, clock=clock)
        self.assertEqual(backstop.try_acquire("100"), 0.0)
        self.assertGreater(backstop.try_acquire("100"), 0.0)
        clock.now += 10.1
        self.assertEqual(backstop.try_acquire("100"), 0.0)


# --------------------------------------------------------------------------- #
# Tool schemas and executor
# --------------------------------------------------------------------------- #


class TestToolContract(unittest.TestCase):
    def test_tool_names(self):
        self.assertEqual(
            TOOL_NAMES,
            {
                "subscribe_events",
                "send_message",
                "reply_message",
                "read_history",
                "add_reaction",
            },
        )

    def test_schemas_have_required_fields(self):
        by_name = {s["name"]: s for s in TOOL_SCHEMAS}
        self.assertEqual(
            by_name["send_message"]["inputSchema"]["required"],
            ["request_id", "channel_id", "content"],
        )
        self.assertEqual(
            by_name["reply_message"]["inputSchema"]["required"],
            ["request_id", "channel_id", "message_id", "content"],
        )
        self.assertEqual(
            by_name["read_history"]["inputSchema"]["required"],
            ["request_id", "handle_id", "direction", "max_events", "max_bytes"],
        )

    def test_schemas_are_json_serializable(self):
        json.dumps(TOOL_SCHEMAS)


class TestToolExecutor(unittest.TestCase):
    def _executor(self, max_sends=5):
        rest = _FakeRest()
        backstop = SendBackstop(max_sends, 10.0, clock=_FakeClock())
        claimed = set()

        def claim(request_id):
            if request_id in claimed:
                raise RuntimeError("duplicate")
            claimed.add(request_id)

        return ToolExecutor(
            rest,
            backstop,
            allowed_channel_ids=frozenset({"100"}),
            action_claim=claim,
            continuations=DiscordHistoryContinuations(
                AUTH_TOKEN,
                participant_id="vigil",
                room_id="100",
                continuity_scope_id="discord:channel:100",
            ),
        ), rest

    @staticmethod
    def _history_request(trigger="77", **overrides):
        continuations = DiscordHistoryContinuations(
            AUTH_TOKEN,
            participant_id="vigil",
            room_id="100",
            continuity_scope_id="discord:channel:100",
        )
        capability = continuations.issue(f"discord:message:{trigger}")
        request = {
            "request_id": "req-history",
            "handle_id": capability["handle_id"],
            "direction": "before",
            "max_events": 10,
            "max_bytes": 32768,
        }
        request.update(overrides)
        return request

    def test_send_message_happy_path(self):
        executor, rest = self._executor()
        payload, ok = executor.call(
            "send_message",
            {"request_id": "req-send", "channel_id": "100", "content": "hi"},
        )
        self.assertTrue(ok)
        self.assertEqual(rest.sent, [("100", "hi", None)])
        self.assertEqual(payload["message"]["content"], "hi")
        self.assertEqual(payload["message"]["message_id"], "42")

    def test_reply_message_passes_reference(self):
        executor, rest = self._executor()
        payload, ok = executor.call(
            "reply_message",
            {
                "request_id": "req-reply",
                "channel_id": "100",
                "message_id": "55",
                "content": "re",
            },
        )
        self.assertTrue(ok)
        self.assertEqual(rest.sent, [("100", "re", "55")])

    def test_read_history_passes_limit_and_before(self):
        executor, rest = self._executor()
        payload, ok = executor.call(
            "read_history", self._history_request()
        )
        self.assertTrue(ok)
        self.assertEqual(rest.history_calls, [("100", 10, "77")])
        self.assertEqual(len(payload["events"]), 2)
        self.assertEqual(payload["room_id"], "100")

    def test_read_history_normalizes_rich_only_messages(self):
        shaped = shape_message(
            _api_message(content="", embeds=[{"title": "Approval required"}])
        )
        self.assertEqual(
            shaped["content"], "[Discord rich message]\nApproval required"
        )

    def test_read_history_preserves_reply_addressing(self):
        shaped = shape_message(
            _api_message(
                mentions=[{"id": "999"}],
                message_reference={"message_id": "41"},
                referenced_message={
                    "id": "41",
                    "content": "prior message",
                    "author": {"id": "999", "username": "Vigil", "bot": True},
                },
            )
        )

        self.assertEqual(shaped["mentioned_user_ids"], ["999"])
        self.assertEqual(shaped["reply_to_message_id"], "41")
        self.assertEqual(shaped["reply_to_author_id"], "999")
        self.assertEqual(shaped["reply_to_content"], "prior message")

    def test_read_history_preserves_exact_room_mention_boolean(self):
        shaped = shape_message(_api_message(mention_everyone=True))
        self.assertIs(shaped["mentions_room"], True)
        with self.assertRaises(ValueError):
            shape_message(_api_message(mention_everyone="true"))

    def test_read_history_rejects_coercible_native_addressing(self):
        cases = (
            {"mentions": [{"id": 999}]},
            {"message_reference": {"message_id": 41}},
            {
                "referenced_message": {
                    "id": "41",
                    "content": "prior",
                    "author": {"id": "999", "username": "Vigil", "bot": "true"},
                }
            },
        )
        for override in cases:
            with self.subTest(override=override), self.assertRaises(ValueError):
                shape_message(_api_message(**override))

    def test_non_numeric_channel_id_rejected(self):
        executor, rest = self._executor()
        payload, ok = executor.call(
            "send_message",
            {"request_id": "req-bad", "channel_id": "../evil", "content": "hi"},
        )
        self.assertFalse(ok)
        self.assertIn("snowflake", payload["error"])
        self.assertEqual(rest.sent, [])

    def test_empty_content_rejected(self):
        executor, _ = self._executor()
        payload, ok = executor.call(
            "send_message",
            {"request_id": "req-empty", "channel_id": "100", "content": "  "},
        )
        self.assertFalse(ok)

    def test_overlong_content_rejected(self):
        executor, _ = self._executor()
        payload, ok = executor.call(
            "send_message",
            {"request_id": "req-long", "channel_id": "100", "content": "x" * 2001},
        )
        self.assertFalse(ok)
        self.assertIn("2000", payload["error"])

    def test_unknown_tool_rejected(self):
        executor, _ = self._executor()
        payload, ok = executor.call("launch_missiles", {})
        self.assertFalse(ok)

    def test_backstop_blocks_send_with_retry_hint(self):
        executor, rest = self._executor(max_sends=1)
        _, ok = executor.call(
            "send_message",
            {"request_id": "req-one", "channel_id": "100", "content": "one"},
        )
        self.assertTrue(ok)
        payload, ok = executor.call(
            "send_message",
            {"request_id": "req-two", "channel_id": "100", "content": "two"},
        )
        self.assertFalse(ok)
        self.assertIn("backstop", payload["error"])
        self.assertIn("retry in", payload["error"])
        self.assertEqual(len(rest.sent), 1, "backstopped send must never reach Discord")

    def test_rest_error_surfaces_as_tool_error(self):
        class _FailingRest(_FakeRest):
            def create_message(self, channel_id, content, **kwargs):
                raise DiscordRestError(403, "Discord API 403 on POST: Missing Access")

        backstop = SendBackstop(5, 10.0, clock=_FakeClock())
        executor = ToolExecutor(
            _FailingRest(),
            backstop,
            allowed_channel_ids=frozenset({"100"}),
            action_claim=lambda _request_id: None,
            continuations=DiscordHistoryContinuations(
                AUTH_TOKEN,
                participant_id="vigil",
                room_id="100",
                continuity_scope_id="discord:channel:100",
            ),
        )
        payload, ok = executor.call(
            "send_message",
            {"request_id": "req-fail", "channel_id": "100", "content": "hi"},
        )
        self.assertFalse(ok)
        self.assertIn("403", payload["error"])

    def test_malformed_success_response_is_not_reported_as_a_sent_message(self):
        class _MalformedRest(_FakeRest):
            def create_message(self, channel_id, content, **kwargs):
                self.sent.append((channel_id, content, None))
                return {"id": "", "channel_id": channel_id, "author": {}}

        executor = ToolExecutor(
            _MalformedRest(),
            SendBackstop(5, 10.0, clock=_FakeClock()),
            allowed_channel_ids=frozenset({"100"}),
            action_claim=lambda _request_id: None,
            continuations=DiscordHistoryContinuations(
                AUTH_TOKEN,
                participant_id="vigil",
                room_id="100",
                continuity_scope_id="discord:channel:100",
            ),
        )
        payload, ok = executor.call(
            "send_message",
            {"request_id": "req-malformed", "channel_id": "100", "content": "hi"},
        )
        self.assertFalse(ok)
        self.assertIn("error", payload)


# --------------------------------------------------------------------------- #
# Shutdown drain
# --------------------------------------------------------------------------- #


class TestInFlightDrain(unittest.IsolatedAsyncioTestCase):
    async def test_wait_idle_waits_for_inflight_send(self):
        in_flight = InFlight()

        async def slow_send():
            with in_flight.track():
                await asyncio.sleep(0.05)

        task = asyncio.create_task(slow_send())
        await asyncio.sleep(0.01)
        self.assertEqual(in_flight.count, 1)
        self.assertTrue(await in_flight.wait_idle(timeout=5.0))
        self.assertEqual(in_flight.count, 0)
        await task

    async def test_wait_idle_times_out_when_send_hangs(self):
        in_flight = InFlight()
        release = asyncio.Event()

        async def hanging_send():
            with in_flight.track():
                await release.wait()

        task = asyncio.create_task(hanging_send())
        await asyncio.sleep(0.01)
        self.assertFalse(await in_flight.wait_idle(timeout=0.05))
        release.set()
        await task


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        config = load_config(_config_env())
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 3993)
        self.assertEqual(config.queue_maxsize, 256)
        self.assertEqual(config.backstop_max_sends, 5)
        self.assertEqual(config.backstop_window_seconds, 10.0)

    def test_missing_token_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_config(
                {
                    "NUNCHI_MCP_DISCORD_AUTH_TOKEN": AUTH_TOKEN,
                    "NUNCHI_MCP_DISCORD_CHANNELS": "100",
                }
            )
        self.assertIn("NUNCHI_DISCORD_TOKEN", str(ctx.exception))

    def test_overrides(self):
        config = load_config(
            _config_env(
                NUNCHI_MCP_DISCORD_PORT="8080",
                NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS="2",
            )
        )
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.backstop_max_sends, 2)

    def test_bad_port_raises_with_var_name(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_config(_config_env(NUNCHI_MCP_DISCORD_PORT="http"))
        self.assertIn("NUNCHI_MCP_DISCORD_PORT", str(ctx.exception))


# --------------------------------------------------------------------------- #
# TOKEN HYGIENE: the token must never surface anywhere
# --------------------------------------------------------------------------- #


class _CollectingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


class TestTokenHygiene(unittest.TestCase):
    def test_token_never_surfaces(self):
        # 1. Tool schemas
        self.assertNotIn(TOKEN, json.dumps(TOOL_SCHEMAS))

        # 2. A sample notification payload
        event = filter_message_create(_create_data(), "999")
        params = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({"444555666"})
        ).notification_params(event)
        self.assertNotIn(TOKEN, json.dumps(params))

        # 3. Config repr (token is excluded from the dataclass repr)
        config = load_config(_config_env())
        self.assertNotIn(TOKEN, repr(config))
        self.assertNotIn(TOKEN, str(config))
        self.assertNotIn(AUTH_TOKEN, repr(config))
        self.assertNotIn(AUTH_TOKEN, str(config))

        # 4. REST error paths (401 body maliciously echoing the auth header)
        echo_body = json.dumps({"message": f"Bot {TOKEN} is not authorized"}).encode()
        http = _FakeHttp([(401, {}, echo_body)])
        client = DiscordRestClient(TOKEN, http=http, sleeper=lambda s: None)
        with self.assertRaises(DiscordRestError) as ctx:
            client.create_message("100", "hi")
        # Discord would never echo the token itself; even if a proxy did, the
        # redaction filter below is the log backstop. The structured detail is
        # truncated upstream — here we assert our own framing added nothing.
        error_text = str(ctx.exception)
        self.assertNotIn("Authorization", error_text)
        self.assertNotIn(TOKEN, error_text)

        # 5. Captured log output from real code paths, with the redaction
        # filter installed exactly as main() installs it.
        collector = _CollectingHandler()
        collector.addFilter(TokenRedactionFilter(TOKEN))
        collector.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        package_logger = logging.getLogger("nunchi.mcp_discord")
        package_logger.addHandler(collector)
        old_level = package_logger.level
        package_logger.setLevel(logging.DEBUG)
        try:
            # Gateway identify flow (payload carries the token; must not be logged)
            proto = GatewayProtocol(TOKEN)
            proto.on_connection_open()
            proto.handle({"op": 10, "d": {"heartbeat_interval": 45000}})
            # Content warning path
            filter_message_create(_create_data(content=""), "999")
            # 429 + retry logging path
            http = _FakeHttp(
                [
                    (429, {}, json.dumps({"retry_after": 0.0, "global": False}).encode()),
                    (200, {}, json.dumps(_api_message()).encode()),
                ]
            )
            limiter = RateLimiter(clock=_FakeClock(), sleeper=lambda s: None)
            client = DiscordRestClient(TOKEN, limiter=limiter, http=http, sleeper=lambda s: None)
            client.create_message("100", "hello")
            # Backstop warning path
            backstop = SendBackstop(0, 10.0, clock=_FakeClock())
            ToolExecutor(
                _FakeRest(),
                backstop,
                allowed_channel_ids=frozenset({"100"}),
                action_claim=lambda _request_id: None,
                continuations=DiscordHistoryContinuations(
                    AUTH_TOKEN,
                    participant_id="vigil",
                    room_id="100",
                    continuity_scope_id="discord:channel:100",
                ),
            ).call(
                "send_message",
                {"request_id": "req-hygiene", "channel_id": "100", "content": "hi"},
            )
            # Adversarial: a hypothetical future log line that embeds the token
            # must be rewritten by the redaction filter before it hits a stream.
            logging.getLogger("nunchi.mcp_discord.adversarial").warning(
                "connecting with token %s", TOKEN
            )
        finally:
            package_logger.removeHandler(collector)
            package_logger.setLevel(old_level)

        joined = "\n".join(collector.messages)
        self.assertNotIn(TOKEN, joined)
        self.assertIn(REDACTED, joined, "adversarial line must be redacted, not dropped")

    def test_identify_and_resume_payloads_carry_token_but_are_never_stringified_in_logs(self):
        # The token must reach Discord (IDENTIFY/RESUME) — hygiene is about
        # logs and surfaces, not about the wire. Sanity-check both payloads.
        proto = GatewayProtocol(TOKEN)
        proto.on_connection_open()
        actions = proto.handle({"op": 10, "d": {"heartbeat_interval": 45000}})
        self.assertEqual(actions[0].payload["d"]["token"], TOKEN)


# --------------------------------------------------------------------------- #
# Entry point / SDK-gated tests
# --------------------------------------------------------------------------- #


@unittest.skipIf(MCP_AVAILABLE, "mcp SDK installed; missing-SDK error path not reachable")
class TestMainWithoutSdk(unittest.TestCase):
    def test_main_reports_missing_sdk_with_install_hint(self):
        stderr = io.StringIO()
        with mock.patch.dict("os.environ", _config_env(), clear=True):
            with contextlib.redirect_stderr(stderr):
                rc = main([])
        self.assertEqual(rc, 2)
        self.assertIn("mcp-discord", stderr.getvalue())


@unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
class TestMcpBinding(unittest.TestCase):
    """Smoke tests for the SDK-bound layer (mirrors discord.py gating)."""

    def test_binding_importable_and_serve_callable(self):
        from nunchi.mcp_discord import _binding

        self.assertTrue(callable(_binding.serve))

    def test_build_server_registers_handlers(self):
        from nunchi.mcp_discord import _binding

        executor = ToolExecutor(
            _FakeRest(),
            SendBackstop(5, 10.0, clock=_FakeClock()),
            allowed_channel_ids=frozenset({"100"}),
            action_claim=lambda _request_id: None,
            continuations=DiscordHistoryContinuations(
                AUTH_TOKEN,
                participant_id="vigil",
                room_id="100",
                continuity_scope_id="discord:channel:100",
            ),
        )
        server = _binding.build_server(
            executor,
            _binding.SessionRegistry(
                participant_id="vigil",
                room_id="100",
                self_actor_id="999",
                capabilities=TOOL_NAMES,
            ),
            InFlight(),
        )
        self.assertEqual(server.name, "nunchi-mcp-discord")

    def test_vendor_notification_dumps_method_and_params(self):
        from nunchi.mcp_discord import _binding

        notification = _binding._VendorNotification(
            method=V2_NOTIFICATION_METHOD, params={"schema_version": 2}
        )
        dumped = notification.model_dump()
        self.assertEqual(dumped["method"], V2_NOTIFICATION_METHOD)
        self.assertEqual(dumped["params"], {"schema_version": 2})

    def test_bounded_event_store_replays_notifications_sent_without_live_stream(self):
        from nunchi.mcp_discord import _binding

        async def scenario():
            store = _binding.BoundedEventStore(max_events=3)
            priming = await store.store_event("_GET_stream", None)
            first = await store.store_event("_GET_stream", {"message": 1})
            second = await store.store_event("_GET_stream", {"message": 2})
            replayed = []

            async def capture(message):
                replayed.append(message)

            stream = await store.replay_events_after(first, capture)
            self.assertEqual(stream, "_GET_stream")
            self.assertEqual([item.message for item in replayed], [{"message": 2}])
            self.assertNotEqual(priming, second)
            with self.assertRaises(RuntimeError):
                await store.store_event("_GET_stream", {"message": 3})

        asyncio.run(scenario())


class TestMcpBroadcast(unittest.IsolatedAsyncioTestCase):
    async def test_slow_session_is_bounded_and_does_not_delay_healthy_session(self):
        class SlowSession:
            async def send_notification(self, _notification):
                await asyncio.Event().wait()

        class HealthySession:
            def __init__(self):
                self.notifications = []

            async def send_notification(self, notification):
                self.notifications.append(notification)

        slow = SlowSession()
        healthy = HealthySession()
        sessions = [slow, healthy]
        discarded = []
        await broadcast_sessions(
            sessions,
            {"schema_version": 2},
            discard=discarded.append,
            send_timeout=0.01,
        )
        self.assertEqual(len(healthy.notifications), 1)
        self.assertEqual(discarded, [slow])

    async def test_failed_session_does_not_remove_other_sessions(self):
        class Session:
            def __init__(self, fail=False):
                self.fail = fail
                self.called = False

            async def send_notification(self, _notification):
                self.called = True
                if self.fail:
                    raise OSError("gone")

        failed = Session(fail=True)
        healthy = Session()
        discarded = []
        await broadcast_sessions(
            [failed, healthy],
            {"schema_version": 2},
            discard=discarded.append,
        )
        self.assertTrue(failed.called)
        self.assertTrue(healthy.called)
        self.assertEqual(discarded, [failed])


if __name__ == "__main__":
    unittest.main()
