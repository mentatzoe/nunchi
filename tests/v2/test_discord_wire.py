"""Isolated Discord transport delivery and reconnect checks on loopback."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
import secrets
import shutil
import tempfile
import unittest

from nunchi.mcp_discord.authorization import ToolAuthorizer, make_tool_authorization
from nunchi.mcp_discord.gateway import GatewayProtocol
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient
from nunchi.mcp_discord.runner import GatewayRunner
from nunchi.mcp_discord.tools import ToolExecutor
from nunchi.mcp_discord.ws import WSClient
from tests.support.fake_discord.control import FakeDiscord


class DiscordWireTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        out = Path(tempfile.mkdtemp(prefix="discord-wire-"))
        self.addCleanup(shutil.rmtree, out, True)
        self.fd = FakeDiscord(
            {"people": ["alice"], "bots": {"participant": {}}, "channels": {"room": {}}}, out
        ).start()
        self.addCleanup(self.fd.stop)
        self.room = self.fd.world.channel("room").id
        self.participant = self.fd.world.member("participant").id
        self.secret = secrets.token_bytes(32)
        authorizer = ToolAuthorizer(secret=self.secret, participant_routes={"participant": frozenset({self.room})})
        rest = DiscordRestClient(self.fd.token("participant"), base_url=self.fd.rest_url)
        self.executor = ToolExecutor(rest, SendBackstop(50, 10), authorizer=authorizer)

    def tool(self, name: str, **arguments):
        arguments = {"channel_id": self.room, **arguments}
        authorization = make_tool_authorization(
            secret=self.secret, request_id=secrets.token_hex(4), participant_id="participant",
            room_id=self.room, tool=name, arguments=arguments,
        )
        return self.executor.call(
            name, {**arguments, "_nunchi_authorization": authorization},
            expected_route=("participant", self.room),
            expected_self_actor_id=f"discord:actor:{self.participant}",
        )

    async def test_authorized_messages_replies_and_reactions_reach_the_channel(self):
        asked = self.fd.post("alice", "room", "a question")["id"]
        for name, arguments in (
            ("send_message", {"content": "an answer"}),
            ("reply_message", {"message_id": asked, "content": "a reply"}),
            ("reaction_capability", {}),
            ("add_reaction", {"message_id": asked, "reaction": "👍"}),
        ):
            with self.subTest(tool=name):
                result, ok = await asyncio.to_thread(self.tool, name, **arguments)
                self.assertTrue(ok, result)

        writes = [
            record for record in self.fd.wire.records
            if record.get("kind") == "http" and record.get("bot") == "participant"
            and record.get("method") != "GET" and 200 <= record["status"] < 300
        ]
        self.assertEqual(3, len(writes), writes)
        message, reply, reaction = writes
        self.assertEqual(("POST", "/channels/{channel}/messages", "an answer"),
                         (message["method"], message["route"], message["request"]["content"]))
        self.assertEqual(("POST", "/channels/{channel}/messages", "a reply", asked),
                         (reply["method"], reply["route"], reply["request"]["content"],
                          reply["request"]["message_reference"]["message_id"]))
        self.assertEqual("PUT", reaction["method"])
        self.assertEqual(f"/api/v10/channels/{self.room}/messages/{asked}/reactions/👍/@me", reaction["decoded_path"])
        self.assertTrue(self.fd.verdict()["clean"], self.fd.verdict()["unknown"])

    async def test_reconnect_resumes_and_replays_messages_received_during_the_gap(self):
        events: list[dict] = []
        gaps: list[int] = []
        protocol = GatewayProtocol(self.fd.token("participant"))
        runner = GatewayRunner(
            protocol, events.append, allowed_channel_ids=frozenset({self.room}),
            on_source_gap=lambda: gaps.append(len(events)),
            connect=lambda url: WSClient.connect(url.replace("wss://gateway.discord.gg", self.fd.gateway_url)),
            rng=lambda: 0.5, initial_backoff=0.05,
        )
        shutdown = asyncio.Event()
        task = asyncio.create_task(runner.run(shutdown))
        try:
            await asyncio.to_thread(self.fd.wait_for, lambda record: record.get("t") == "READY", 10)
            since = len(self.fd.wire.records)
            await asyncio.to_thread(self.fd.gateway, "participant", "reconnect")
            posted = await asyncio.to_thread(self.fd.post, "alice", "room", "posted while reconnecting")
            for _ in range(100):
                if any((event.get("event") or {}).get("id") == f"discord:message:{posted['id']}" for event in events):
                    break
                await asyncio.sleep(0.05)
            frames = [record for record in self.fd.wire.records[since:]
                      if record.get("kind") == "ws" and record.get("bot") == "participant"]
        finally:
            shutdown.set()
            task.cancel()
            with contextlib.suppress(BaseException):
                await task

        self.assertTrue(any((event.get("event") or {}).get("id") == f"discord:message:{posted['id']}" for event in events))
        self.assertEqual(1, sum(record["dir"] == "out" and record["op"] == 7 for record in frames))
        self.assertTrue(any(record["dir"] == "in" and record["op"] == 6 for record in frames))
        self.assertTrue(any(record["dir"] == "out" and record.get("t") == "RESUMED" for record in frames))
        self.assertFalse(any(record["dir"] == "in" and record["op"] == 2 for record in frames))
        self.assertEqual(1, len(gaps), "only the fresh process's own start gap")
        self.assertTrue(self.fd.verdict()["clean"], self.fd.verdict()["unknown"])
