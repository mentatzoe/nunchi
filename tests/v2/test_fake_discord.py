"""The Discord stand-in (step 9f, PR 3a): Nunchi's own Discord clients against it, and its social facts with Discord's codes.

Nunchi's transport drives it through hooks it already has:
`DiscordRestClient(base_url=...)`, `GatewayRunner(connect=...)` and the
`ToolExecutor`, so each room action passes the same checks as in a real run,
the acknowledgement attestation included. The tables pin each social fact a
column reads the room from (the time of a message, who it addresses, what
it replies to, who wrote it, who may see, post or react, and the limits on
the agent's own moves) with Discord's own status and error codes. Plain
loopback and the standard library only; real discord.py drives the
stand-in in `test_fake_discord_discordpy.py`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import unittest
from unittest import mock

from nunchi.mcp_discord.authorization import ToolAuthorizer, make_tool_authorization
from nunchi.mcp_discord.gateway import INTENTS as TRANSPORT_INTENTS, GatewayProtocol
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient, DiscordRestError
from nunchi.mcp_discord.runner import GatewayFatalError, GatewayRunner
from nunchi.mcp_discord.tools import ToolExecutor
from nunchi.mcp_discord.ws import WSClient, WSClosed

from evals.rehearsal.fake_discord import payloads, shapes
from evals.rehearsal.fake_discord.control import FakeDiscord
from evals.rehearsal.fake_discord.world import INTENTS, PERMISSIONS, DiscordError, World, id_ms, iso

WORLD = {
    "people": ["zoe", "kim"],
    "bots": {  # every bot is a harness's unless the world says otherwise
        "vigil": {},
        "boss": {"roles": ["admin"]},
        "shy": {"roles": ["helpers"], "privileged": ["GUILD_MEMBERS"]},
        "ci": {"harness": False},
    },
    "roles": {"admin": ["ADMINISTRATOR"], "helpers": []},
    "channels": {
        "room": {},
        "other": {},
        "quiet": {"kim": {"deny": ["MENTION_EVERYONE"]}},
        "read-only": {"agents": {"deny": ["SEND_MESSAGES"]}},
        "no-react": {"@everyone": {"deny": ["ADD_REACTIONS"]}},
        "no-history": {"agents": {"deny": ["READ_MESSAGE_HISTORY"]}},
        "react-back": {"@everyone": {"deny": ["ADD_REACTIONS"]}, "vigil": {"allow": ["ADD_REACTIONS"]}},
        "people-only": {"@everyone": {"deny": ["VIEW_CHANNEL"]}, "room": {"allow": ["VIEW_CHANNEL"]}},
        "agents-only": {"@everyone": {"deny": ["VIEW_CHANNEL"]}, "agents": {"allow": ["VIEW_CHANNEL"]}},
        "announce": {"room": {"deny": ["SEND_MESSAGES"]}},
        "split": {"helpers": {"allow": ["ADD_REACTIONS"]}, "agents": {"deny": ["ADD_REACTIONS"]}},
    },
}
REACT = PERMISSIONS["VIEW_CHANNEL"] | PERMISSIONS["READ_MESSAGE_HISTORY"] | PERMISSIONS["ADD_REACTIONS"]
DISCORD_TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00$")
DPY_INTENTS = 46595  # what nunchi-discord, on discord.py, asks for


class StandIn:
    """Starts a stand-in for one test, writing its outputs to a temporary directory."""

    def start(self, world: dict | World = WORLD, **options) -> FakeDiscord:
        self.out = Path(tempfile.mkdtemp(prefix="fake-discord-"))
        self.addCleanup(shutil.rmtree, self.out, True)
        self.fd = FakeDiscord(world, self.out, **options).start()
        self.addCleanup(self.fd.stop)
        return self.fd

    def api(self, method: str, path: str, body=None, *, bot: str | None = "vigil", headers: dict | None = None):
        """One REST call as a client makes it: (status, lower-cased headers, JSON body or None). A bytes body is sent as it is."""
        headers = {"Content-Type": "application/json", **({"Authorization": f"Bot {self.fd.token(bot)}"} if bot else {}), **(headers or {})}
        data = body if body is None or isinstance(body, bytes) else json.dumps(body)
        connection = http.client.HTTPConnection("127.0.0.1", self.fd.port, timeout=5)
        try:
            connection.request(method, "/api/v10" + path, body=data, headers=headers)
            response = connection.getresponse()
            data = response.read()
        finally:
            connection.close()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, json.loads(data) if data else None

    def channel(self, name: str) -> str:
        return self.fd.world.channel(name).id

    def member(self, name: str) -> str:
        return self.fd.world.member(name).id


# -- Nunchi's transport against the stand-in ------------------------------------------------------------


class TransportTest(StandIn, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        fd = self.start()
        self.room = self.channel("room")
        self.vigil = self.member("vigil")
        self.secret = secrets.token_bytes(32)
        authorizer = ToolAuthorizer(secret=self.secret, participant_routes={"vigil": frozenset({self.room})})
        rest = DiscordRestClient(fd.token("vigil"), base_url=fd.rest_url)
        self.executor = ToolExecutor(rest, SendBackstop(50, 10), authorizer=authorizer)
        self.events: list[dict] = []
        self.gaps: list[int] = []

    def tool(self, name: str, **arguments):
        """One room tool call through the transport's executor, authorized as the host would."""
        arguments = {"channel_id": self.room, **arguments}
        authorization = make_tool_authorization(
            secret=self.secret, request_id=secrets.token_hex(4), participant_id="vigil", room_id=self.room, tool=name, arguments=arguments
        )
        return self.executor.call(
            name, {**arguments, "_nunchi_authorization": authorization},
            expected_route=("vigil", self.room), expected_self_actor_id=f"discord:actor:{self.vigil}",
        )

    def runner(self, token: str, **options) -> tuple[GatewayProtocol, GatewayRunner]:
        protocol = GatewayProtocol(token)
        runner = GatewayRunner(
            protocol, self.events.append, allowed_channel_ids=frozenset({self.room}), on_source_gap=lambda: self.gaps.append(len(self.events)),
            connect=lambda url: WSClient.connect(url.replace("wss://gateway.discord.gg", self.fd.gateway_url)),
            rng=lambda: 0.5, initial_backoff=0.05, **options,
        )
        return protocol, runner

    async def connect(self) -> GatewayProtocol:
        protocol, runner = self.runner(self.fd.token("vigil"))
        task = asyncio.create_task(runner.run(asyncio.Event()))

        async def stop() -> None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        self.addAsyncCleanup(stop)
        await self.until(lambda: protocol.ready)
        return protocol

    async def until(self, predicate, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while not predicate():
            self.assertLess(asyncio.get_running_loop().time(), deadline, "timed out")
            await asyncio.sleep(0.02)

    def texts(self) -> list[str | None]:
        return [event["event"].get("text") for event in self.events]

    async def test_a_message_reply_and_reaction_go_through_the_transport_as_on_discord(self):
        await self.connect()
        zoe = self.member("zoe")
        asked = self.fd.post("zoe", "room", f"<@{self.vigil}> what's a sensible webhook timeout?")
        await self.until(lambda: len(self.events) == 1)
        first = self.events[0]
        self.assertEqual(first["event"]["author_id"], f"discord:actor:{zoe}")
        self.assertEqual(first["event"]["mentioned_actor_ids"], [f"discord:actor:{self.vigil}"])
        self.assertEqual(first["actors"][f"discord:actor:{zoe}"], {"display_name": "Zoe", "kind": "human"})
        self.assertEqual(first["event"]["timestamp"], asked["timestamp"])

        payload, ok = await asyncio.to_thread(self.tool, "send_message", content="Ten seconds.")
        self.assertTrue(ok, payload)  # the acknowledgement passed the transport's attestation
        await self.until(lambda: len(self.events) == 2)
        self.assertEqual(self.events[1]["event"]["author_id"], f"discord:actor:{self.vigil}")  # the room shows the bot its own post

        payload, ok = await asyncio.to_thread(self.tool, "reply_message", message_id=asked["id"], content="Five, if it retries.")
        self.assertTrue(ok, payload)
        self.assertEqual(payload["message"]["reply_to_message_id"], asked["id"])
        await self.until(lambda: len(self.events) == 3)
        self.assertEqual(self.events[2]["event"]["reply_to_event_id"], f"discord:message:{asked['id']}")

        payload, ok = await asyncio.to_thread(self.tool, "reaction_capability")
        self.assertTrue(payload["reaction_capability"]["capability"]["supported"], payload)
        for name in ("add_reaction", "remove_reaction"):
            payload, ok = await asyncio.to_thread(self.tool, name, message_id=asked["id"], reaction="👀")
            self.assertTrue(ok, payload)
        await self.until(lambda: len(self.events) == 5)
        self.assertEqual([e["event"]["operation"] for e in self.events[3:]], ["add", "remove"])

        payload, ok = await asyncio.to_thread(self.tool, "add_reaction", message_id=asked["id"], reaction="mhm")
        self.assertFalse(ok)
        self.assertIn("Unknown Emoji", payload["error"])  # a nod sent as a word is refused, as in Zoe's room
        self.assertTrue(self.fd.verdict()["clean"], self.fd.verdict()["unknown"])

    async def test_a_resume_replays_what_the_transport_missed_without_a_gap(self):
        protocol = await self.connect()
        session = protocol.session_id
        self.fd.gateway("vigil", "drop")
        self.fd.post("zoe", "room", "while you were away")
        await self.until(lambda: "while you were away" in self.texts())
        self.assertEqual(protocol.session_id, session)
        self.assertEqual(len(self.gaps), 1, "only the fresh process's own gap")
        records = self.fd.wire.records
        self.assertEqual([r["op"] for r in records if r["kind"] == "ws" and r["dir"] == "in" and r["op"] != 1], [2, 6])
        replayed = next(r for r in records if r.get("t") == "MESSAGE_CREATE" and r["dir"] == "out")
        resumed = next(r for r in records if r.get("t") == "RESUMED")
        self.assertEqual(replayed["conn"], resumed["conn"])
        self.assertLess(replayed["n"], resumed["n"])

    async def test_a_session_discord_will_not_resume_is_a_gap_and_a_fresh_identify(self):
        protocol = await self.connect()
        for action, options in (("invalid_session", {}), ("close", {"code": 4009})):
            with self.subTest(action=action):
                before, gaps = protocol.session_id, len(self.gaps)
                self.assertEqual(self.fd.gateway("vigil", action, **options), 1)
                await self.until(lambda: protocol.ready and protocol.session_id not in (None, before))
                self.assertEqual(len(self.gaps), gaps + 1)

    async def test_a_bad_token_and_a_disallowed_intent_are_fatal(self):
        for token, code in (("not-a-token", "4004"), (self.fd.token("shy"), "4014")):
            with self.subTest(code=code):
                _, runner = self.runner(token)
                with self.assertRaisesRegex(GatewayFatalError, code):
                    await asyncio.wait_for(runner.run(asyncio.Event()), 5)
        identifies = [r["d"]["token"] for r in self.fd.wire.records if r["kind"] == "ws" and r["op"] == 2]
        self.assertEqual(identifies, ["<unknown token>", "<bot:shy>"])

    async def test_the_reaction_capability_agrees_with_the_stand_in_across_overwrites(self):
        world = self.fd.world
        expected = {
            "vigil": {"room": True, "other": True, "quiet": True, "read-only": True, "no-react": False, "no-history": False,
                      "react-back": True, "people-only": None, "agents-only": True, "announce": True, "split": False},
            "boss": dict.fromkeys(WORLD["channels"], True),  # ADMINISTRATOR passes every overwrite
            "shy": {"split": True},  # one role's allow beats another's deny
        }
        for bot, table in expected.items():
            client = DiscordRestClient(self.fd.token(bot), base_url=self.fd.rest_url)
            for name, supported in table.items():
                channel, member = self.channel(name), self.member(bot)
                with self.subTest(bot=bot, channel=name):
                    if supported is None:  # it cannot see the channel at all
                        with self.assertRaises(DiscordRestError) as caught:
                            await asyncio.to_thread(client.reaction_capability, channel, member)
                        self.assertEqual(caught.exception.status, 403)
                        self.assertEqual(world.permissions(member, channel), 0)
                        continue
                    result = await asyncio.to_thread(client.reaction_capability, channel, member)
                    self.assertEqual(result["capability"]["supported"], supported)
                    self.assertEqual(world.permissions(member, channel) & REACT == REACT, supported)

    async def test_an_injected_429_is_waited_out_by_the_transport(self):
        self.fd.fault("POST", "/channels/{channel}/messages", 429, retry_after=0.05)
        payload, ok = await asyncio.to_thread(self.tool, "send_message", content="after the limit")
        self.assertTrue(ok, payload)
        posts = [r for r in self.fd.wire.records if r["kind"] == "http" and r["method"] == "POST"]
        self.assertEqual([r["status"] for r in posts], [429, 200])


# -- the social facts, with Discord's codes ------------------------------------------------------------------


class SocialFactsTest(StandIn, unittest.TestCase):
    def setUp(self) -> None:
        self.start()

    def post(self, channel: str, body: dict, bot: str = "vigil"):
        return self.api("POST", f"/channels/{self.channel(channel)}/messages", body, bot=bot)

    def react(self, channel: str, message: str, emoji: str, bot: str = "vigil", method: str = "PUT"):
        from urllib.parse import quote

        return self.api(method, f"/channels/{self.channel(channel)}/messages/{message}/reactions/{quote(emoji, safe='')}/@me", bot=bot)

    def test_who_a_message_addresses(self):
        world = self.fd.world
        vigil, kim, zoe = self.member("vigil"), self.member("kim"), self.member("zoe")
        agents, admin = world.role("agents").id, world.role("admin").id
        everything = f"<@{vigil}> <@&{agents}> @everyone"
        self.fd.create_thread("zoe", "announce", "announce-thread")
        mention_everyone = PERMISSIONS["MENTION_EVERYONE"]
        self.assertFalse(world.permissions(kim, self.channel("announce")) & mention_everyone, "no SEND_MESSAGES, no MENTION_EVERYONE")
        self.assertTrue(world.permissions(kim, self.channel("announce-thread")) & mention_everyone, "a thread asks SEND_MESSAGES_IN_THREADS")

        def addressed(record):
            return [world.members[u].name for u in record["mentions"]], [world.roles[r].name for r in record["mention_roles"]], record["mention_everyone"]

        people = [
            ("a person with MENTION_EVERYONE", "zoe", "room", everything, (["vigil"], ["agents"], True)),
            ("a person without it, by an overwrite", "kim", "quiet", everything, (["vigil"], [], False)),
            ("@here is everyone too", "zoe", "room", "@here look", ([], [], True)),
            ("a thread under a channel she may not post in", "kim", "announce-thread", "@here look", ([], [], True)),
            ("the older mention form", "zoe", "room", f"<@!{kim}> hi", (["kim"], [], False)),
            ("an id nobody has", "zoe", "room", "<@123456789012345678> hi", ([], [], False)),
        ]
        for why, author, channel, content, expected in people:
            posted = self.fd.post(author, channel, content)
            self.assertEqual(addressed(world.messages[posted["id"]]), expected, why)
        bots = [
            ("a bot has no MENTION_EVERYONE", "vigil", None, f"<@{zoe}> @here", (["zoe"], [], False)),
            ("allowed_mentions parses nothing", "vigil", {"parse": []}, f"<@{zoe}>", ([], [], False)),
            ("allowed_mentions names one user", "vigil", {"parse": [], "users": [zoe]}, f"<@{zoe}> <@{kim}>", (["zoe"], [], False)),
            ("allowed_mentions names one role", "boss", {"parse": [], "roles": [agents]}, f"<@{zoe}> <@&{agents}> <@&{admin}> @everyone",
             ([], ["agents"], False)),
        ]
        for why, bot, allowed, content, expected in bots:
            body = {"content": content, **({"allowed_mentions": allowed} if allowed is not None else {})}
            status, _, message = self.post("room", body, bot=bot)
            self.assertEqual(status, 200)
            got = ([m["username"] for m in message["mentions"]], [world.roles[r].name for r in message["mention_roles"]], message["mention_everyone"])
            self.assertEqual(got, expected, why)

    def test_what_a_message_replies_to(self):
        world, room = self.fd.world, self.channel("room")
        target = self.fd.post("zoe", "room", "is the deploy done?")
        status, _, reply = self.post("room", {"content": "yes", "message_reference": {"message_id": target["id"]}})
        self.assertEqual(status, 200)
        self.assertEqual(reply["type"], 19)
        self.assertEqual(reply["message_reference"], {"type": 0, "message_id": target["id"], "channel_id": room, "guild_id": world.guild_id})
        self.assertEqual(reply["referenced_message"]["id"], target["id"])
        self.assertEqual([m["username"] for m in reply["mentions"]], ["zoe"], "the world's reply_ping")
        status, _, quiet = self.post("room", {"content": "yes", "message_reference": {"message_id": target["id"]},
                                              "allowed_mentions": {"parse": ["users"], "replied_user": False}})
        self.assertEqual(quiet["mentions"], [])
        status, _, unset = self.post("room", {"content": "yes", "message_reference": {"message_id": target["id"]},
                                              "allowed_mentions": {"parse": ["users"]}})
        self.assertEqual(unset["mentions"], [], "replied_user defaults to false once allowed_mentions is given")

        refused = [
            ("a target nobody posted", {"message_id": "1"}),
            ("a target in another channel", {"message_id": self.fd.post("zoe", "other", "elsewhere")["id"]}),
        ]
        for why, reference in refused:
            status, _, error = self.post("room", {"content": "yes", "message_reference": reference})
            self.assertEqual((status, error["code"]), (400, 50035), why)
            self.assertIn("message_reference", error["errors"])
        status, _, plain = self.post("room", {"content": "yes", "message_reference": {"message_id": "1", "fail_if_not_exists": False}})
        self.assertEqual((status, plain["type"]), (200, 0))
        self.assertNotIn("message_reference", plain)

        director = self.fd.post("kim", "room", "me too", reply_to=target["id"])
        self.assertEqual(payloads.message(world, world.messages[director["id"]], gateway=True)["type"], 19)

    def test_who_wrote_it(self):
        world = self.fd.world
        person = payloads.message(world, world.messages[self.fd.post("zoe", "room", "hi")["id"]], gateway=True)
        self.assertNotIn("bot", person["author"])
        self.assertEqual(person["author"]["global_name"], "Zoe")
        self.assertEqual(person["member"]["roles"], [world.role("room").id])
        scripted = payloads.message(world, world.messages[self.fd.post("ci", "room", "deploy finished")["id"]])
        self.assertIs(scripted["author"]["bot"], True)
        with self.assertRaisesRegex(ValueError, "harness's bot"):
            self.fd.post("vigil", "room", "said for the agent")  # a bot the world does not mark is a harness's
        with self.assertRaisesRegex(ValueError, "not a harness's bot"):
            self.fd.token("ci")  # and a scripted bot has no token, so no process runs as it

        once = {"content": "once", "nonce": "42", "enforce_nonce": True}
        first, second = self.post("room", once)[2], self.post("room", once)[2]
        self.assertEqual((first["id"], first["nonce"], first["author"]["bot"]), (second["id"], "42", True))
        twice = {"content": "twice", "nonce": "43"}
        self.assertNotEqual(self.post("room", twice)[2]["id"], self.post("room", twice)[2]["id"])

    def test_who_may_post_see_and_react(self):
        targets = {name: self.fd.post("zoe", name, "react here")["id"] for name in WORLD["channels"]}
        self.fd.create_thread("zoe", "people-only", "people-thread")
        self.fd.create_thread("zoe", "read-only", "read-only-thread")
        rows = [
            ("vigil", "post", "room", 200, None),
            ("vigil", "post", "read-only", 403, 50013),
            ("vigil", "post", "read-only-thread", 200, None),  # a thread asks SEND_MESSAGES_IN_THREADS instead
            ("vigil", "post", "people-only", 403, 50001),
            ("vigil", "post", "people-thread", 403, 50001),  # a thread takes its parent's overwrites
            ("vigil", "see", "people-only", 403, 50001),
            ("vigil", "see", "agents-only", 200, None),  # a role's allow beats @everyone's deny
            ("vigil", "reply", "no-history", 403, 50013),
            ("vigil", "react", "room", 204, None),
            ("vigil", "react", "no-react", 403, 50013),
            ("vigil", "react", "no-history", 403, 50013),
            ("vigil", "react", "react-back", 204, None),
            ("vigil", "react", "split", 403, 50013),
            ("shy", "react", "split", 204, None),  # one role's allow beats another's deny
            ("kim", "post", "people-only", 200, None),
            ("kim", "post", "agents-only", 403, 50001),
            ("zoe", "post", "agents-only", 200, None),  # the owner passes every overwrite
        ]
        for who, action, channel, status, code in rows:
            with self.subTest(who=who, action=action, channel=channel):
                if who in ("zoe", "kim"):
                    try:
                        self.fd.post(who, channel, "hello")
                        got = (200, None, None)
                    except DiscordError as error:
                        got = (error.status, None, error.body)
                elif action == "post":
                    got = self.post(channel, {"content": "hello"}, bot=who)
                elif action == "reply":
                    got = self.post(channel, {"content": "hello", "message_reference": {"message_id": targets[channel]}}, bot=who)
                elif action == "see":
                    got = self.api("GET", f"/channels/{self.channel(channel)}", bot=who)
                else:
                    got = self.react(channel, targets[channel], "👀", bot=who)
                self.assertEqual((got[0], got[2] and got[2].get("code")), (status, code))
        self.assertEqual(self.react("no-react", targets["no-react"], "👍", bot="boss")[0], 204)
        self.assertEqual(self.react("no-react", targets["no-react"], "👍")[0], 204, "joining a reaction needs only the history")
        self.assertEqual(self.react("room", targets["other"], "👍")[2]["code"], 10008)
        self.assertEqual(self.api("GET", "/channels/1")[2]["code"], 10003)
        self.assertEqual(self.api("GET", f"/guilds/{self.fd.world.guild_id}/members/1")[2]["code"], 10007)
        self.assertEqual(self.api("GET", "/guilds/1/roles")[2]["code"], 10004)

    def test_the_limits_on_the_agents_own_moves(self):
        target = self.fd.post("zoe", "room", "react here")["id"]
        rows = [
            ({"content": "a" * 2000}, 200, None),
            ({"content": "a" * 2001}, 400, 50035),
            ({"content": ""}, 400, 50006),
            ({"content": " \n"}, 400, 50006),
        ]
        for body, status, code in rows:
            got = self.post("room", body)
            self.assertEqual((got[0], got[2].get("code")), (status, code), len(body["content"]))
        self.assertIn("content", self.post("room", {"content": "a" * 2001})[2]["errors"])
        emoji_rows = [("mhm", 400), ("blob:123456789012345678", 400), ("👀👍", 400), ("\ufe0f", 400),
                      ("1", 400), ("👍🏽", 204), ("1️⃣", 204), ("🏳️‍🌈", 204), ("🇺🇸", 204), ("‼️", 204), ("ℹ️", 204), ("◽", 204)]
        for emoji, status in emoji_rows:
            self.assertEqual(self.react("room", target, emoji)[0], status, emoji)
        crowded = self.fd.post("zoe", "room", "so many")["id"]
        for i in range(20):
            self.assertEqual(self.react("room", crowded, chr(0x1F600 + i), bot="boss")[0], 204)
        self.assertEqual(self.react("room", crowded, "🚀")[2]["code"], 30010)
        status, _, body = self.post("room", {"content": " hi ", "tts": True})
        self.assertEqual(status, 599, "a field the stand-in does not model is unknown, never ignored")
        self.assertEqual(self.fd.verdict()["unknown"][-1]["what"], "request")
        multipart = b'--x\r\nContent-Disposition: form-data; name="payload_json"\r\n\r\n{"content": "a file"}\r\n--x--\r\n'
        status, _, _ = self.api("POST", f"/channels/{self.channel('room')}/messages", multipart,
                                headers={"Content-Type": "multipart/form-data; boundary=x"})
        self.assertEqual(status, 599, "a file's multipart is not modelled")
        self.assertEqual(self.fd.verdict()["unknown"][-1]["detail"], "a multipart/form-data body (a file, say)")
        self.post("room", {"content": " hi "})
        posts = [r for r in self.fd.wire.records if r["kind"] == "http" and r["method"] == "POST"]
        self.assertEqual((posts[-1]["response"]["content"], posts[-1]["whitespace"]), (" hi ", True))

    def test_every_response_carries_discords_headers(self):
        rate_limit = {"x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-reset-after", "x-ratelimit-bucket"}
        target = self.fd.post("zoe", "room", "x")["id"]
        for why, (_, headers, _) in [
            ("a read", self.api("GET", "/users/@me")),
            ("a refusal", self.post("read-only", {"content": "x"})),
            ("no token", self.api("GET", "/users/@me", bot=None)),
            ("a bot token without 'Bot '", self.api("GET", "/users/@me", headers={"Authorization": self.fd.token("vigil")})),
        ]:
            self.assertEqual(headers["content-type"], "application/json", why)  # exactly: discord.py compares with ==
            self.assertEqual(rate_limit & set(headers), rate_limit, why)
        for headers in ({}, {"Authorization": self.fd.token("vigil")}):  # no token, and a bot token without "Bot "
            status, _, body = self.api("GET", "/users/@me", bot=None, headers=headers)
            self.assertEqual((status, body), (401, {"message": "401: Unauthorized", "code": 0}))
        status, headers, body = self.react("room", target, "👀")
        self.assertEqual((status, body, "content-type" in headers, rate_limit <= set(headers)), (204, None, False, True))
        self.assertFalse(rate_limit & set(self.api("GET", "/gateway/bot")[1]), "an unknown route has none")

        self.fd.fault("GET", "/users/@me", 429, retry_after=0.25)
        status, headers, body = self.api("GET", "/users/@me")
        self.assertEqual((status, body), (429, {"message": "You are being rate limited.", "retry_after": 0.25, "global": False}))
        self.assertTrue(headers["via"])  # without Via, discord.py takes a 429 for a Cloudflare ban
        self.assertEqual(self.api("GET", "/users/@me")[0], 200)
        self.fd.fault("POST", f"/channels/{self.channel('room')}/messages", 502)
        status, headers, _ = self.post("room", {"content": "lost"})
        self.assertEqual((status, rate_limit & set(headers)), (502, set()), "only a 429 carries rate-limit headers")
        self.assertEqual(self.fd.world.channel("room").messages, 1, "a faulted request has no effect")

    def test_anything_else_is_599_and_fails_the_verdict(self):
        self.assertTrue(self.fd.verdict()["clean"])
        for path, host in (("/gateway/bot", None), ("/users/@me", "cdn.discordapp.com"), ("/channels/1/typing", None)):
            status, _, body = self.api("POST" if path.endswith("typing") else "GET", path, headers={"Host": host} if host else None)
            self.assertEqual((status, body["code"]), (599, 0), path)
        for body in ({"content": "hi", "allowed_mentions": ["users"]}, {"content": "hi", "message_reference": "123"}):
            self.assertEqual(self.post("room", body)[0], 599, "a request shape nobody foresaw is answered, not a dropped socket")
        verdict, posts = self.fd.verdict(), f"/api/v10/channels/{self.channel('room')}/messages"
        self.assertFalse(verdict["clean"])
        self.assertEqual([(u["what"], u["path"], u.get("host")) for u in verdict["unknown"]],
                         [("route", "/api/v10/gateway/bot", "127.0.0.1"), ("route", "/api/v10/users/@me", "cdn.discordapp.com"),
                          ("route", "/api/v10/channels/1/typing", "127.0.0.1"), ("stand-in error", posts, None), ("stand-in error", posts, None)])
        self.assertEqual(len([r for r in self.fd.wire.records if r["kind"] == "http"]), 5)


class ClockTest(StandIn, unittest.TestCase):
    def test_the_rooms_clock_only_moves_forward_and_a_bots_post_brings_it_to_the_wall(self):
        start = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc).timestamp()
        now = [start]
        fd = self.start(World(WORLD, clock=lambda: now[0]))

        def seconds(posted: dict) -> float:
            self.assertRegex(posted["timestamp"], DISCORD_TIME)
            self.assertEqual(posted["timestamp"], iso(id_ms(posted["id"])))
            return id_ms(posted["id"]) / 1000 - start

        def ago(s: float) -> datetime:
            return datetime.fromtimestamp(start + s, timezone.utc)

        times, ids = [], []

        def post(**options) -> None:
            posted = fd.post("zoe", "room", "x", **options)
            ids.append(int(posted["id"]))
            times.append(round(seconds(posted)))

        post(at=ago(-60))  # a scene that began a minute ago
        post()  # the room's time
        now[0] += 5
        post()
        self.assertEqual(fd.advance("room", 30), iso(int((start - 25) * 1000)))
        post()
        post(at=ago(-100))  # earlier than the channel's last id: raised, and recorded
        self.assertEqual(fd.state()["channels"]["room"]["lag"], 30.0, "a backdated post never moves the clock back")
        status, _, mine = self.api("POST", f"/channels/{self.channel('room')}/messages", {"content": "mine"})
        ids.append(int(mine["id"]))
        times.append(round(seconds(mine)))
        post()
        post(at=ago(100))  # never later than the wall
        self.assertEqual(times, [-60, -60, -55, -25, -25, 5, 5, 5])
        self.assertEqual(ids, sorted(set(ids)), "ids only increase")
        self.assertEqual(fd.state()["channels"]["room"]["lag"], 0.0)
        raised = fd.verdict()["raised"]
        self.assertEqual([(r["channel"], r["requested"]) for r in raised], [("room", iso(int((start - 100) * 1000)))])
        self.assertEqual(round(seconds(fd.post("zoe", "other", "x", at=ago(-300)))), -300, "each channel keeps its own clock")
        self.assertEqual(fd.advance("other", 10_000), iso(int(now[0] * 1000)), "and it never passes the wall")

    def test_a_thread_keeps_its_parents_clock(self):
        start = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc).timestamp()
        fd = self.start(World(WORLD, clock=lambda: start))
        first = fd.post("zoe", "room", "a scene that began a minute ago", at=datetime.fromtimestamp(start - 60, timezone.utc))
        fd.create_thread("kim", "room", "side", from_message=first["id"])
        self.assertEqual(fd.post("kim", "side", "a reply in the thread")["timestamp"], iso(int((start - 60) * 1000)), "the room's time")
        status, _, mine = self.api("POST", f"/channels/{self.channel('room')}/messages", {"content": "the agent's answer"})
        later = fd.post("zoe", "side", "a follow-up in the thread, after the answer")
        self.assertGreater(int(later["id"]), int(mine["id"]))
        self.assertEqual(later["timestamp"], iso(int(start * 1000)))
        self.assertEqual(fd.state()["channels"]["side"]["lag"], 0.0)
        early = fd.post("zoe", "side", "a time before the agent's answer", at=datetime.fromtimestamp(start - 30, timezone.utc))
        self.assertGreater(int(early["id"]), int(later["id"]), "the room's floor holds in its thread")
        self.assertEqual([(r["channel"], r["requested"]) for r in fd.verdict()["raised"]], [("side", iso(int((start - 30) * 1000)))])


# -- the gateway, the log and the pin ---------------------------------------------------------------------


class GatewayTest(StandIn, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.start()

    async def open(self, query: str = "?v=10&encoding=json") -> WSClient:
        ws = await WSClient.connect(self.fd.gateway_url + "/" + query)
        self.addAsyncCleanup(ws.close)
        hello = await self.receive(ws)
        self.assertEqual(hello, {"op": 10, "d": {"heartbeat_interval": 41250}, "s": None, "t": None})
        return ws

    async def receive(self, ws: WSClient) -> dict:
        return json.loads(await asyncio.wait_for(ws.receive_text(), 5))

    async def identify(self, ws: WSClient, bot: str, intents: int) -> dict:
        await ws.send_text(json.dumps({"op": 2, "d": {"token": self.fd.token(bot), "intents": intents, "properties": {}}}))
        ready = await self.receive(ws)
        self.assertEqual((ready["t"], ready["s"]), ("READY", 1))
        return ready["d"]

    async def test_a_heartbeat_before_identify_then_ready_the_guild_and_a_member_chunk(self):
        ws = await self.open()
        await ws.send_text(json.dumps({"op": 1, "d": None}))  # discord.py beats as soon as HELLO arrives
        self.assertEqual((await self.receive(ws))["op"], 11)
        ready = await self.identify(ws, "vigil", DPY_INTENTS)
        world = self.fd.world
        self.assertEqual(ready["resume_gateway_url"], self.fd.gateway_url)
        self.assertEqual((ready["user"]["id"], ready["guilds"]), (self.member("vigil"), [{"id": world.guild_id, "unavailable": True}]))
        guild = await self.receive(ws)
        self.assertEqual((guild["t"], guild["s"]), ("GUILD_CREATE", 2))
        self.assertEqual([m["user"]["id"] for m in guild["d"]["members"]], [self.member("vigil")], "without presences, only the bot itself")
        self.assertEqual(guild["d"]["member_count"], len(world.members))
        self.assertEqual(guild["d"]["roles"][0]["id"], world.guild_id)  # @everyone carries the guild's id
        await ws.send_text(json.dumps({"op": 8, "d": {"guild_id": int(world.guild_id), "query": "", "limit": 0, "nonce": "n1"}}))
        chunk = await self.receive(ws)
        self.assertEqual((chunk["t"], chunk["d"]["nonce"], len(chunk["d"]["members"])), ("GUILD_MEMBERS_CHUNK", "n1", len(world.members)))
        self.assertTrue(self.fd.verdict()["clean"], self.fd.verdict()["unknown"])

    async def test_an_op_out_of_place_closes_with_discords_code(self):
        undecodable = '{"op": 2, "d": {"token": "%s"}} and more' % self.fd.token("vigil")
        rows = [
            ("a member request before IDENTIFY", None, {"op": 8, "d": {}}, 4003),
            ("an op no client here sends", "vigil", {"op": 3, "d": {}}, 4001),
            ("a second IDENTIFY", "vigil", {"op": 2, "d": {"token": self.fd.token("vigil"), "intents": TRANSPORT_INTENTS}}, 4005),
            ("a frame that does not decode", None, undecodable, 4002),
            ("a resume nobody foresaw", None, {"op": 6, "d": {"token": self.fd.token("vigil"), "session_id": [], "seq": 1}}, 4000),
        ]
        for why, bot, payload, code in rows:
            ws = await self.open()
            if bot:
                await self.identify(ws, bot, TRANSPORT_INTENTS)
            await ws.send_text(payload if isinstance(payload, str) else json.dumps(payload))
            with self.assertRaises(WSClosed) as closed:
                while True:
                    await self.receive(ws)
            self.assertEqual(closed.exception.code, code, why)
        await self.open("?v=6&encoding=etf")
        unknown = self.fd.verdict()["unknown"]
        self.assertEqual([(u["what"], u.get("op")) for u in unknown], [("op", 3), ("payload", None), ("stand-in error", 6), ("gateway query", None)])
        self.assertEqual((unknown[1]["bytes"], "text" in unknown[1]), (len(undecodable), False), "a frame that may hold a token is never logged")

    async def test_fan_out_follows_who_can_see_and_a_thread_comes_before_its_messages(self):
        transport = await self.open()
        await self.identify(transport, "vigil", TRANSPORT_INTENTS)  # no GUILDS intent: no GUILD_CREATE, no THREAD_CREATE
        watcher = await self.open()
        await self.identify(watcher, "boss", INTENTS["GUILDS"] | INTENTS["GUILD_MESSAGES"])
        self.assertEqual((await self.receive(watcher))["t"], "GUILD_CREATE")
        self.assertEqual(self.fd.post("zoe", "people-only", "just us")["dispatched_to"], ["boss"])
        self.assertEqual((await self.receive(watcher))["d"]["content"], "just us")
        self.assertEqual(self.fd.post("zoe", "room", "everyone")["dispatched_to"], ["vigil", "boss"])
        self.assertEqual((await self.receive(transport))["d"]["content"], "everyone")
        self.assertEqual((await self.receive(watcher))["d"]["content"], "everyone")
        thread = self.fd.create_thread("zoe", "room", "side")
        self.fd.post("zoe", "side", "in the thread")
        created, message = await self.receive(watcher), await self.receive(watcher)
        self.assertEqual((created["t"], created["d"]["newly_created"], created["d"]["parent_id"]), ("THREAD_CREATE", True, self.channel("room")))
        self.assertEqual((message["t"], message["d"]["channel_id"]), ("MESSAGE_CREATE", thread["id"]))
        self.assertEqual((await self.receive(transport))["d"]["channel_id"], thread["id"])
        self.assertEqual(self.fd.create_thread("zoe", "people-only", "hidden")["dispatched_to"], ["boss"])
        self.assertEqual(self.fd.post("kim", "hidden", "between us")["dispatched_to"], ["boss"], "a thread takes its parent's")
        self.assertTrue(self.fd.verdict()["clean"], self.fd.verdict()["unknown"])

    async def test_a_resume_finds_its_session_unless_discord_would_have_ended_it(self):
        rows = [
            ("a close Discord resumes", "close", {"code": 4000}, (0, "RESUMED", {})),
            ("op 9, not resumable", "invalid_session", {}, (9, None, False)),
            ("a session that timed out", "close", {"code": 4009}, (9, None, False)),
            ("a seq that is invalid", "close", {"code": 4007}, (9, None, False)),
        ]
        for why, action, options, expected in rows:
            ws = await self.open()
            ready = await self.identify(ws, "vigil", TRANSPORT_INTENTS)
            self.fd.gateway("vigil", action, **options)
            later = await self.open()
            await later.send_text(json.dumps({"op": 6, "d": {"token": self.fd.token("vigil"), "session_id": ready["session_id"], "seq": 1}}))
            answer = await self.receive(later)
            self.assertEqual((answer["op"], answer["t"], answer["d"]), expected, why)
            await ws.close()
            await later.close()

    async def test_a_payload_sent_without_a_pinned_key_is_unknown(self):
        member = payloads.member
        with mock.patch.object(payloads, "member", lambda m, **options: {k: v for k, v in member(m, **options).items() if k != "flags"}):
            await asyncio.to_thread(self.api, "GET", f"/guilds/{self.fd.world.guild_id}/members/{self.member('kim')}")
            ws = await self.open()
            await self.identify(ws, "vigil", INTENTS["GUILDS"])
            await self.receive(ws)
        self.assertEqual([(u["what"], u["payload"], u["missing"]) for u in self.fd.verdict()["unknown"]],
                         [("shape", "member", ["flags"]), ("shape", "GUILD_CREATE", ["members.flags"])])

    async def test_settle_waits_for_a_quiet_wire_and_heartbeats_are_not_traffic(self):
        ws = await self.open()
        self.assertTrue(await asyncio.to_thread(self.fd.settle, 0.2, 2))
        self.assertFalse(await asyncio.to_thread(self.fd.settle, 5, 0.3))
        await asyncio.sleep(0.25)
        await ws.send_text(json.dumps({"op": 1, "d": None}))
        await self.receive(ws)
        self.assertTrue(await asyncio.to_thread(self.fd.settle, 0.2, 0.1), "a heartbeat does not end the quiet")

    async def test_no_token_reaches_any_output_and_the_world_file_names_every_id(self):
        ws = await self.open()
        await self.identify(ws, "vigil", TRANSPORT_INTENTS)
        token = self.fd.token("vigil")
        status, _, _ = await asyncio.to_thread(self.api, "POST", f"/channels/{self.channel('room')}/messages", {"content": f"my token is {token}"})
        self.assertEqual((status, (await self.receive(ws))["t"]), (200, "MESSAGE_CREATE"))  # its own post, echoed
        later = await self.open()
        await later.send_text(json.dumps({"op": 6, "d": {"token": token, "session_id": "gone", "seq": 1}}))
        self.assertEqual(await self.receive(later), {"op": 9, "d": False, "s": None, "t": None})
        await later.send_text(json.dumps({"op": 6, "d": {"token": "a-stranger", "session_id": "x", "seq": 1}}))
        with self.assertRaises(WSClosed) as closed:
            while True:
                await self.receive(later)
        self.assertEqual(closed.exception.code, 4004)
        self.fd.stop()
        outputs = {path.name: path.read_text(encoding="utf-8") for path in self.out.iterdir()}
        self.assertEqual(set(outputs), {"world.json", "discord-wire.jsonl", "discord-standin.json"})
        for name, text in outputs.items():
            for bot in ("vigil", "boss", "shy"):
                self.assertNotIn(self.fd.token(bot), text, name)
        self.assertIn('"token": "<bot:vigil>"', outputs["discord-wire.jsonl"])
        self.assertIn("my token is <bot:vigil>", outputs["discord-wire.jsonl"])
        self.assertIn('"token": "<unknown token>"', outputs["discord-wire.jsonl"])
        world = json.loads(outputs["world.json"])
        self.assertEqual(world["bots"]["vigil"], {"id": self.member("vigil"), "harness": True, "roles": ["agents"],
                                                  "privileged_intents": ["GUILD_MEMBERS", "MESSAGE_CONTENT"]})
        self.assertEqual(world["channels"]["no-react"]["overwrites"], [{"target": "@everyone", "allow": [], "deny": ["ADD_REACTIONS"]}])
        self.assertEqual(world["rest_url"], self.fd.rest_url)


class ShapePinTest(unittest.TestCase):
    def test_the_pin_covers_every_payload_and_every_exemption_has_a_reason(self):
        pin = shapes.vendored()
        self.assertEqual(pin["discord.py"], "2.7.1")
        for kind, name in payloads.SHAPES.items():
            self.assertIn(pin["aliases"].get(name, name), pin["types"], kind)
        for name, exempt in shapes.EXEMPT.items():
            for key, reason in exempt.items():
                self.assertIn(key, pin["types"][name]["required"])
                self.assertTrue(reason)
        for name, unions in shapes.UNIONS.items():
            for key, nested in unions.items():
                self.assertNotIn(key, pin["types"][name]["nested"], "the pin follows it already")
                self.assertIn(nested.removesuffix("[]"), pin["types"])

    def test_inherited_and_nested_keys_are_required(self):
        self.assertIn("channel_id", shapes.vendored()["types"]["message.Message"]["required"], "from PartialMessage")
        member = {"user": {"id": "1", "username": "kim", "discriminator": "0", "avatar": None, "global_name": None},
                  "roles": [], "joined_at": None, "deaf": False, "mute": False}
        self.assertEqual(shapes.missing("member.MemberWithUser", member), ["flags"])  # discord.py dies with KeyError('flags')
        del member["user"]["username"]
        self.assertEqual(shapes.missing("gateway.GuildMembersChunkEvent", {"guild_id": "1", "chunk_index": 0, "chunk_count": 1, "members": [member]}),
                         ["members.flags", "members.user.username"])

    def test_every_payload_the_stand_in_builds_carries_the_keys_discord_py_requires(self):
        world = World(WORLD)
        zoe, vigil, room = world.member("zoe"), world.member("vigil"), world.channel("room")
        asked, _ = world.create_message(zoe.id, room.id, f"<@{vigil.id}> is the deploy done?")
        reply, _ = world.create_message(vigil.id, room.id, "yes", reference={"message_id": asked["id"]}, nonce="1", wall=True)
        thread = world.create_thread(zoe.id, room.id, "side")
        built = {
            "READY": payloads.ready(world, vigil, "session", "ws://127.0.0.1:1"),
            "GUILD_CREATE": payloads.guild_create(world, vigil, INTENTS["GUILDS"] | INTENTS["GUILD_PRESENCES"]),
            "GUILD_MEMBERS_CHUNK": payloads.members_chunk(world, list(world.members.values()), "n"),
            "MESSAGE_CREATE": payloads.message(world, reply, gateway=True),
            "MESSAGE_REACTION_ADD": payloads.reaction(world, vigil.id, asked, "👀", add=True),
            "MESSAGE_REACTION_REMOVE": payloads.reaction(world, vigil.id, asked, "👀", add=False),
            "THREAD_CREATE": {**payloads.channel(world, thread), "newly_created": True},
            "user": payloads.user(vigil),
            "application": payloads.application(world, vigil),
            "message": payloads.message(world, reply),
            "text": payloads.channel(world, room),
            "thread": payloads.channel(world, thread),
            "member": payloads.member(zoe),
            "role": payloads.role(world.role("agents")),
        }
        self.assertEqual(set(built), set(payloads.SHAPES))
        for kind, payload in built.items():
            self.assertEqual(shapes.missing(payloads.SHAPES[kind], payload), [], kind)
        del built["GUILD_CREATE"]["channels"][0]["position"]  # a Union in discord.types, followed through shapes.UNIONS
        self.assertEqual(shapes.missing(payloads.SHAPES["GUILD_CREATE"], built["GUILD_CREATE"]), ["channels.position"])

    def test_guild_create_lists_only_the_threads_a_bot_can_see(self):
        world = World(WORLD)
        zoe = world.member("zoe")
        world.create_thread(zoe.id, world.channel("room").id, "side")
        world.create_thread(zoe.id, world.channel("people-only").id, "hidden")
        threads = {bot: [t["name"] for t in payloads.guild_create(world, world.member(bot), INTENTS["GUILDS"])["threads"]]
                   for bot in ("vigil", "boss")}
        self.assertEqual(threads, {"vigil": ["side"], "boss": ["side", "hidden"]})

    def test_a_payload_that_misses_the_pin_is_unknown_once(self):
        fd = FakeDiscord(WORLD)
        fd.check_shape("MESSAGE_CREATE", {"id": "1"})
        fd.check_shape("MESSAGE_CREATE", {"id": "1"})
        unknown = fd.verdict()["unknown"]
        self.assertEqual(len(unknown), 1)
        self.assertIn("channel_id", unknown[0]["missing"])


class LifecycleTest(unittest.TestCase):
    def test_a_start_that_fails_leaves_nothing_running(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            fd = FakeDiscord(WORLD, port=busy.getsockname()[1])
            with self.assertRaises(OSError):
                fd.start()
        self.assertFalse(fd._thread.is_alive())
        self.assertTrue(fd.stop()["clean"])


@unittest.skipUnless(shutil.which("openssl"), "needs the openssl command to make a certificate")
class TlsTest(StandIn, unittest.TestCase):
    def test_tls_answers_only_discords_names(self):
        keys = Path(tempfile.mkdtemp(prefix="fake-discord-tls-"))
        self.addCleanup(shutil.rmtree, keys, True)
        cert, key = keys / "cert.pem", keys / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=discord.com",
                        "-addext", "subjectAltName=DNS:discord.com,DNS:gateway.discord.gg", "-keyout", str(key), "-out", str(cert)],
                       check=True, capture_output=True)
        fd = self.start(tls=(str(cert), str(key)))
        self.assertEqual((fd.rest_url, fd.gateway_url), (f"https://discord.com:{fd.port}/api/v10", f"wss://gateway.discord.gg:{fd.port}"))
        context = ssl.create_default_context(cafile=str(cert))
        context.set_alpn_protocols(["http/1.1"])
        with socket.create_connection(("127.0.0.1", fd.port), timeout=5) as raw, context.wrap_socket(raw, server_hostname="discord.com") as tls:
            self.assertEqual(tls.selected_alpn_protocol(), "http/1.1")
            tls.sendall(f"GET /api/v10/users/@me HTTP/1.1\r\nHost: discord.com\r\nAuthorization: Bot {fd.token('vigil')}\r\nConnection: close\r\n\r\n".encode())
            reply = b"".join(iter(lambda: tls.recv(4096), b""))
        self.assertTrue(reply.startswith(b"HTTP/1.1 200 OK"), reply[:40])
        with socket.create_connection(("127.0.0.1", fd.port), timeout=5) as raw:
            with self.assertRaises(OSError):  # an ssl.SSLError or a reset: the handshake is refused
                context.wrap_socket(raw, server_hostname="evil.example").close()
        fd.wait_for(lambda r: r["kind"] == "unknown", 5)
        self.assertEqual([(u["what"], u["server_name"]) for u in fd.verdict()["unknown"]], [("sni", "evil.example")])
        with socket.create_connection(("127.0.0.1", fd.port), timeout=5) as raw:
            with self.assertRaises(ssl.SSLCertVerificationError):  # a client without the run's certificate
                ssl.create_default_context().wrap_socket(raw, server_hostname="discord.com").close()
        hellos = [r["server_name"] for r in fd.wire.records if r["kind"] == "tls_hello"]
        handshakes = [r for r in fd.wire.records if r["kind"] == "tls"]
        self.assertEqual(hellos, ["discord.com", "discord.com"], "the refused certificate shows as a hello with no handshake")
        self.assertEqual([(r["server_name"], r["alpn"]) for r in handshakes], [("discord.com", "http/1.1")])


if __name__ == "__main__":
    unittest.main()
