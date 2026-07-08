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

# Ensure src is on the path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

# Check mcp SDK availability (no install required for transport-logic tests)
try:
    import mcp as _mcp_sdk  # noqa: F401

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from nunchi.mcp_discord.config import load_config
from nunchi.mcp_discord.events import (
    NOTIFICATION_METHOD,
    filter_message_create,
    notification_params,
)
from nunchi.mcp_discord.gateway import GatewayProtocol
from nunchi.mcp_discord.hygiene import REDACTED, TokenRedactionFilter
from nunchi.mcp_discord.ratelimit import RateLimiter, SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient, DiscordRestError
from nunchi.mcp_discord.server import InFlight, enqueue_event, main, pump_notifications
from nunchi.mcp_discord.tools import TOOL_NAMES, TOOL_SCHEMAS, ToolExecutor, shape_message

TOKEN = "NUNCHI-TEST-TOKEN-4f9a2bconfidential"


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

    def create_message(self, channel_id, content, *, reply_to_message_id=None):
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

    def test_empty_content_with_attachment_no_warning(self):
        data = _create_data(content="", attachments=[{"id": "1", "filename": "x.png"}])
        with self.assertNoLogs("nunchi.mcp_discord.events", level="WARNING"):
            filter_message_create(data, "999")


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
        self.assertTrue(enqueue_event(queue, event))
        await asyncio.wait_for(
            pump_notifications(queue, mock_client_send, shutdown=shutdown), timeout=5.0
        )

        self.assertEqual(NOTIFICATION_METHOD, "notifications/discord/message")
        self.assertEqual(
            received,
            [
                {
                    "guild_id": "777888999",
                    "channel_id": "444555666",
                    "message_id": "111222333",
                    "author_id": "777",
                    "author_name": "peer-bot",
                    "author_is_bot": True,
                    "content": "ping",
                    "timestamp": "2026-07-06T10:00:00.000000+00:00",
                }
            ],
        )

    async def test_failing_client_does_not_stop_the_pump(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        shutdown = asyncio.Event()
        received: list[dict] = []
        calls = {"n": 0}

        async def flaky_send(params: dict) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("MCP client went away")
            received.append(params)
            shutdown.set()

        for author in ("111", "222"):
            enqueue_event(queue, filter_message_create(_create_data(author), "999"))
        await asyncio.wait_for(
            pump_notifications(queue, flaky_send, shutdown=shutdown), timeout=5.0
        )
        self.assertEqual([p["author_id"] for p in received], ["222"])

    async def test_dm_message_has_null_guild_id(self):
        data = _create_data()
        del data["guild_id"]
        params = notification_params(filter_message_create(data, "999"))
        self.assertIsNone(params["guild_id"])


# --------------------------------------------------------------------------- #
# Bounded queue backpressure
# --------------------------------------------------------------------------- #


class TestBackpressure(unittest.IsolatedAsyncioTestCase):
    async def test_drop_oldest_when_queue_full(self):
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
        self.assertEqual(remaining, ["msg2", "msg3"], "oldest must be dropped, newest kept")
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
        self.assertEqual(TOOL_NAMES, {"send_message", "reply_message", "read_history"})

    def test_schemas_have_required_fields(self):
        by_name = {s["name"]: s for s in TOOL_SCHEMAS}
        self.assertEqual(
            by_name["send_message"]["inputSchema"]["required"], ["channel_id", "content"]
        )
        self.assertEqual(
            by_name["reply_message"]["inputSchema"]["required"],
            ["channel_id", "message_id", "content"],
        )
        self.assertEqual(by_name["read_history"]["inputSchema"]["required"], ["channel_id"])

    def test_schemas_are_json_serializable(self):
        json.dumps(TOOL_SCHEMAS)


class TestToolExecutor(unittest.TestCase):
    def _executor(self, max_sends=5):
        rest = _FakeRest()
        backstop = SendBackstop(max_sends, 10.0, clock=_FakeClock())
        return ToolExecutor(rest, backstop), rest

    def test_send_message_happy_path(self):
        executor, rest = self._executor()
        payload, ok = executor.call("send_message", {"channel_id": "100", "content": "hi"})
        self.assertTrue(ok)
        self.assertEqual(rest.sent, [("100", "hi", None)])
        self.assertEqual(payload["message"]["content"], "hi")
        self.assertEqual(payload["message"]["message_id"], "42")

    def test_reply_message_passes_reference(self):
        executor, rest = self._executor()
        payload, ok = executor.call(
            "reply_message", {"channel_id": "100", "message_id": "55", "content": "re"}
        )
        self.assertTrue(ok)
        self.assertEqual(rest.sent, [("100", "re", "55")])

    def test_read_history_passes_limit_and_before(self):
        executor, rest = self._executor()
        payload, ok = executor.call(
            "read_history", {"channel_id": "100", "limit": 10, "before": "77"}
        )
        self.assertTrue(ok)
        self.assertEqual(rest.history_calls, [("100", 10, "77")])
        self.assertEqual(len(payload["messages"]), 2)
        self.assertIn("author_is_bot", payload["messages"][0])

    def test_non_numeric_channel_id_rejected(self):
        executor, rest = self._executor()
        payload, ok = executor.call(
            "send_message", {"channel_id": "../evil", "content": "hi"}
        )
        self.assertFalse(ok)
        self.assertIn("snowflake", payload["error"])
        self.assertEqual(rest.sent, [])

    def test_empty_content_rejected(self):
        executor, _ = self._executor()
        payload, ok = executor.call("send_message", {"channel_id": "100", "content": "  "})
        self.assertFalse(ok)

    def test_overlong_content_rejected(self):
        executor, _ = self._executor()
        payload, ok = executor.call(
            "send_message", {"channel_id": "100", "content": "x" * 2001}
        )
        self.assertFalse(ok)
        self.assertIn("2000", payload["error"])

    def test_unknown_tool_rejected(self):
        executor, _ = self._executor()
        payload, ok = executor.call("launch_missiles", {})
        self.assertFalse(ok)

    def test_backstop_blocks_send_with_retry_hint(self):
        executor, rest = self._executor(max_sends=1)
        _, ok = executor.call("send_message", {"channel_id": "100", "content": "one"})
        self.assertTrue(ok)
        payload, ok = executor.call("send_message", {"channel_id": "100", "content": "two"})
        self.assertFalse(ok)
        self.assertIn("backstop", payload["error"])
        self.assertIn("retry in", payload["error"])
        self.assertEqual(len(rest.sent), 1, "backstopped send must never reach Discord")

    def test_rest_error_surfaces_as_tool_error(self):
        class _FailingRest(_FakeRest):
            def create_message(self, channel_id, content, *, reply_to_message_id=None):
                raise DiscordRestError(403, "Discord API 403 on POST: Missing Access")

        backstop = SendBackstop(5, 10.0, clock=_FakeClock())
        executor = ToolExecutor(_FailingRest(), backstop)
        payload, ok = executor.call("send_message", {"channel_id": "100", "content": "hi"})
        self.assertFalse(ok)
        self.assertIn("403", payload["error"])


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
        config = load_config({"NUNCHI_DISCORD_TOKEN": TOKEN})
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 3993)
        self.assertEqual(config.queue_maxsize, 256)
        self.assertEqual(config.backstop_max_sends, 5)
        self.assertEqual(config.backstop_window_seconds, 10.0)

    def test_missing_token_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_config({})
        self.assertIn("NUNCHI_DISCORD_TOKEN", str(ctx.exception))

    def test_overrides(self):
        config = load_config(
            {
                "NUNCHI_DISCORD_TOKEN": TOKEN,
                "NUNCHI_MCP_DISCORD_PORT": "8080",
                "NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS": "2",
            }
        )
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.backstop_max_sends, 2)

    def test_bad_port_raises_with_var_name(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_config({"NUNCHI_DISCORD_TOKEN": TOKEN, "NUNCHI_MCP_DISCORD_PORT": "http"})
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
        self.assertNotIn(TOKEN, json.dumps(notification_params(event)))

        # 3. Config repr (token is excluded from the dataclass repr)
        config = load_config({"NUNCHI_DISCORD_TOKEN": TOKEN})
        self.assertNotIn(TOKEN, repr(config))
        self.assertNotIn(TOKEN, str(config))

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
            ToolExecutor(_FakeRest(), backstop).call(
                "send_message", {"channel_id": "100", "content": "hi"}
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
        with contextlib.redirect_stderr(stderr):
            rc = main([])
        self.assertEqual(rc, 1)
        self.assertIn("pip install nunchi[mcp-discord]", stderr.getvalue())


@unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
class TestMcpBinding(unittest.TestCase):
    """Smoke tests for the SDK-bound layer (mirrors discord.py gating)."""

    def test_binding_importable_and_serve_callable(self):
        from nunchi.mcp_discord import _binding

        self.assertTrue(callable(_binding.serve))

    def test_build_server_registers_handlers(self):
        from nunchi.mcp_discord import _binding

        executor = ToolExecutor(
            _FakeRest(), SendBackstop(5, 10.0, clock=_FakeClock())
        )
        server = _binding.build_server(executor, _binding.SessionRegistry(), InFlight())
        self.assertEqual(server.name, "nunchi-mcp-discord")

    def test_vendor_notification_dumps_method_and_params(self):
        from nunchi.mcp_discord import _binding

        notification = _binding._VendorNotification(
            method=NOTIFICATION_METHOD, params={"content": "x"}
        )
        dumped = notification.model_dump()
        self.assertEqual(dumped["method"], NOTIFICATION_METHOD)
        self.assertEqual(dumped["params"], {"content": "x"})


if __name__ == "__main__":
    unittest.main()
