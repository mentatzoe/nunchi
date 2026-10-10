"""The Discord stand-in through real discord.py (step 9f, PR 3a), configured as `nunchi-discord` runs it.

Only discord.py's REST base and first gateway URL are pointed at the
stand-in, here in the test; everything else is discord.py as installed, so
its aiohttp is an independent check on the stand-in's WebSocket codec (the
transport shares it). It checks what discord.py needs before any column can
read the room: ready within a few seconds, with the member chunk answered and
``guild.me`` set; ``permissions_for`` agreeing with the stand-in and with the
transport's reaction capability across overwrites and in threads, for the
bot and for a person; a person's message parsed with a Member author that
has roles (a missing key there is dropped silently); a thread known before
its message; raw reaction events; the bot's own echo with its nonce; a
reply; a resume; and a session Discord would end, which starts afresh.

Skipped where discord.py is not installed. CI runs it with discord.py 2.7.1
in the ``discord-standin`` job (Python 3.12, ``zlib-stream``) and the
``hermes-plugin`` job (3.14, ``zstd-stream``).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
import shutil
import tempfile
import unittest
from unittest import mock

from nunchi.mcp_discord.rest import DiscordRestClient, DiscordRestError

from evals.rehearsal.fake_discord.control import FakeDiscord
from evals.rehearsal.fake_discord.world import PERMISSIONS, bits, id_ms

try:
    import discord
    import yarl
except ImportError:  # the stdlib suite runs without it
    discord = None

WORLD = {
    "people": ["zoe", "kim"],
    "bots": {"dpy": {"roles": ["helpers"]}, "boss": {"roles": ["admin"]}},
    "roles": {"admin": ["ADMINISTRATOR"], "helpers": []},
    "channels": {
        "room": {},
        "read-only": {"agents": {"deny": ["SEND_MESSAGES"]}},
        "no-react": {"@everyone": {"deny": ["ADD_REACTIONS"]}},
        "no-history": {"agents": {"deny": ["READ_MESSAGE_HISTORY"]}},
        "react-back": {"@everyone": {"deny": ["ADD_REACTIONS"]}, "dpy": {"allow": ["ADD_REACTIONS"]}},
        "people-only": {"@everyone": {"deny": ["VIEW_CHANNEL"]}, "room": {"allow": ["VIEW_CHANNEL"]}},
        "agents-only": {"@everyone": {"deny": ["VIEW_CHANNEL"]}, "agents": {"allow": ["VIEW_CHANNEL"]}},
        "announce": {"room": {"deny": ["SEND_MESSAGES"]}},
        "split": {"helpers": {"allow": ["ADD_REACTIONS"]}, "agents": {"deny": ["ADD_REACTIONS"]}},
    },
}
COMPARED = bits(["VIEW_CHANNEL", "SEND_MESSAGES", "READ_MESSAGE_HISTORY", "ADD_REACTIONS", "MENTION_EVERYONE", "SEND_MESSAGES_IN_THREADS"])
REACT = bits(["VIEW_CHANNEL", "READ_MESSAGE_HISTORY", "ADD_REACTIONS"])
EVENTS = ("ready", "message", "raw_reaction_add", "raw_reaction_remove", "resumed", "thread_create")


@unittest.skipIf(discord is None, "needs discord.py")
class DiscordPyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        out = tempfile.mkdtemp(prefix="fake-discord-dpy-")
        self.addCleanup(shutil.rmtree, out, True)
        self.fd = FakeDiscord(WORLD, out).start()
        self.addCleanup(self.fd.stop)
        self.enterContext(mock.patch.object(discord.http.Route, "BASE", self.fd.rest_url))
        self.enterContext(mock.patch.object(discord.gateway.DiscordWebSocket, "DEFAULT_GATEWAY", yarl.URL(self.fd.gateway_url + "/")))
        intents = discord.Intents.none()  # as nunchi-discord asks (nunchi.adapters.discord)
        intents.guilds = intents.messages = intents.message_content = intents.reactions = intents.members = True
        self.client = discord.Client(intents=intents)
        self.queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        for name in EVENTS:
            async def handler(*args, name=name):
                self.queues[name].put_nowait(args)

            setattr(self.client, f"on_{name}", handler)
        loop = asyncio.get_running_loop()
        started = loop.time()
        task = asyncio.create_task(self.client.start(self.fd.token("dpy")))

        async def close() -> None:
            await self.client.close()
            await asyncio.wait_for(task, 10)

        self.addAsyncCleanup(close)
        await self.next("ready")
        self.ready_after = loop.time() - started
        self.guild = self.client.guilds[0]

    async def next(self, event: str, timeout: float = 10.0) -> tuple:
        return await asyncio.wait_for(self.queues[event].get(), timeout)

    def channel(self, name: str):
        return self.guild.get_channel_or_thread(int(self.fd.world.channel(name).id))

    def assertClean(self) -> None:
        verdict = self.fd.verdict()
        self.assertTrue(verdict["clean"], verdict["unknown"])

    async def test_ready_comes_with_the_member_chunk_and_permissions_agree_across_overwrites(self):
        self.assertLess(self.ready_after, 4.5, "discord.py waits 5 s for a member chunk nobody answers")
        self.assertIs(self.guild.me, self.guild.get_member(self.client.user.id))
        self.assertTrue(self.guild.chunked)
        self.assertEqual(len(self.guild.members), len(self.fd.world.members))
        self.assertEqual(self.fd.verdict()["bots"]["dpy"]["chunks"], 1)
        world, me = self.fd.world, self.fd.world.member("dpy").id
        for parent in ("room", "announce"):  # a thread takes its parent's, with SEND_MESSAGES_IN_THREADS for the implicit rule
            self.fd.create_thread("zoe", parent, f"{parent}-thread")
            await self.next("thread_create")
        kim = self.guild.get_member(int(world.member("kim").id))
        for name in [*WORLD["channels"], "room-thread", "announce-thread"]:
            for who in (self.guild.me, kim):
                with self.subTest(channel=name, member=who.name):
                    theirs = self.channel(name).permissions_for(who).value & COMPARED
                    self.assertEqual(theirs, world.permissions(str(who.id), world.channel(name).id) & COMPARED)
        transport = DiscordRestClient(self.fd.token("dpy"), base_url=self.fd.rest_url)
        for name in WORLD["channels"]:  # the transport reads a text channel's overwrites
            channel_id = world.channel(name).id
            ours = world.permissions(me, channel_id)
            with self.subTest(capability=name):
                try:
                    supported = (await asyncio.to_thread(transport.reaction_capability, channel_id, me))["capability"]["supported"]
                except DiscordRestError as error:
                    self.assertEqual((error.status, ours & PERMISSIONS["VIEW_CHANNEL"]), (403, 0))
                    continue
                self.assertEqual(supported, ours & REACT == REACT)
        self.assertClean()

    async def test_messages_reactions_and_replies_read_as_on_discord(self):
        me, room = self.client.user, self.channel("room")
        posted = self.fd.post("zoe", "room", f"<@{me.id}> hello, @everyone")
        (message,) = await self.next("message")
        self.assertIsInstance(message.author, discord.Member)  # a missing member key would leave a bare User, silently
        self.assertIn("room", [role.name for role in message.author.roles])
        self.assertEqual((message.mentions, message.mention_everyone), ([self.guild.me], True))
        self.assertEqual(message.created_at.timestamp(), id_ms(posted["id"]) / 1000)

        thread = self.fd.create_thread("kim", "room", "side")
        self.fd.post("kim", "side", "in the thread")
        (in_thread,) = await self.next("message")
        self.assertIsInstance(in_thread.channel, discord.Thread)
        self.assertEqual((in_thread.channel.id, in_thread.channel.parent_id), (int(thread["id"]), room.id))

        sent = await room.send("hello, room")
        (echo,) = await self.next("message")
        self.assertEqual((echo.id, echo.author, echo.nonce), (sent.id, me, sent.nonce))
        self.assertIsNotNone(echo.nonce)

        reply = await message.reply("hi Zoe", mention_author=False)
        (echo,) = await self.next("message")
        for seen in (reply, echo):
            self.assertEqual((seen.type, seen.reference.message_id, seen.mentions), (discord.MessageType.reply, message.id, []))
        self.assertEqual(echo.reference.resolved.id, message.id)

        await message.add_reaction("👀")
        (added,) = await self.next("raw_reaction_add")
        self.assertEqual((added.user_id, str(added.emoji), added.member), (me.id, "👀", self.guild.me))
        await message.remove_reaction("👀", me)
        (removed,) = await self.next("raw_reaction_remove")
        self.assertEqual((removed.user_id, str(removed.emoji)), (me.id, "👀"))
        with self.assertRaises(discord.HTTPException) as refused:
            await message.add_reaction("mhm")
        self.assertEqual((refused.exception.status, refused.exception.code), (400, 10014))
        self.fd.post("zoe", "no-react", "react here")
        (target,) = await self.next("message")
        with self.assertRaises(discord.Forbidden) as forbidden:
            await target.add_reaction("👀")
        self.assertEqual(forbidden.exception.code, 50013)
        self.assertClean()

    async def test_the_routes_hermes_calls_are_read_by_discord_py(self):
        """History, one message, a reaction read back, the slash-command sync and the application's flags: what `hermes gateway run` asks of Discord."""
        room = self.channel("room")
        ids = [int(self.fd.post("zoe", "room", f"message {number}")["id"]) for number in range(3)]
        found = [m async for m in room.history(limit=2, before=discord.Object(ids[2]))]
        self.assertEqual([m.id for m in found], [ids[1], ids[0]], "newest first, before the id")
        self.assertEqual([m.content for m in found], ["message 1", "message 0"])
        message = await room.fetch_message(ids[0])
        self.assertEqual((message.content, message.author.name), ("message 0", "zoe"))
        await message.add_reaction("👍")
        read_back = await room.fetch_message(ids[0])
        self.assertEqual([(str(r.emoji), r.count, r.me) for r in read_back.reactions], [("👍", 1, True)])
        with self.assertRaises(discord.NotFound) as unknown:
            await room.fetch_message(1)
        self.assertEqual(unknown.exception.code, 10008)
        flags = self.client.application_flags
        # An unverified bot in fewer than 100 servers, as Discord sets its flags: the "limited" bits, not the full ones.
        self.assertTrue(flags.gateway_message_content_limited and flags.gateway_guild_members_limited, "both privileged intents are enabled for the bot")
        self.assertFalse(flags.gateway_message_content or flags.gateway_guild_members, "the full bits are a verified bot's")

        tree = discord.app_commands.CommandTree(self.client)

        @tree.command(name="status", description="Show the session")
        async def status(interaction: discord.Interaction) -> None:  # pragma: no cover - never invoked
            pass

        self.assertEqual(await tree.fetch_commands(), [])
        desired = [command.to_dict(tree) for command in tree.get_commands()]
        created = await self.client.http.upsert_global_command(self.client.application_id, desired[0])
        self.assertEqual((created["name"], created["type"]), ("status", 1))
        (fetched,) = await tree.fetch_commands()
        self.assertEqual((fetched.name, fetched.description, fetched.id), ("status", "Show the session", int(created["id"])))
        again = await self.client.http.upsert_global_command(self.client.application_id, desired[0])
        self.assertEqual(again["id"], created["id"], "the same name overwrites")
        self.assertEqual(len(await tree.fetch_commands()), 1)
        self.assertClean()

    async def test_a_reconnect_resumes_the_session(self):
        self.fd.gateway("dpy", "reconnect")
        await self.next("resumed")
        self.fd.post("zoe", "room", "after the resume")
        (message,) = await self.next("message")
        self.assertEqual(message.content, "after the resume")
        bot = self.fd.verdict()["bots"]["dpy"]
        self.assertEqual((bot["identify"], bot["resume"], bot["ready"]), (1, 1, 1))
        self.assertClean()

    async def test_a_session_discord_ends_starts_afresh_and_what_was_missed_is_gone(self):
        self.fd.gateway("dpy", "close", code=4009)  # "session timed out": Discord answers the RESUME with op 9
        self.fd.post("zoe", "room", "said while the session was gone")
        await self.next("ready")
        self.fd.post("zoe", "room", "after the new session")
        (message,) = await self.next("message")
        self.assertEqual(message.content, "after the new session")
        bot = self.fd.verdict()["bots"]["dpy"]
        self.assertEqual((bot["identify"], bot["resume"], bot["ready"]), (2, 1, 2))
        self.assertClean()


if __name__ == "__main__":
    unittest.main()
