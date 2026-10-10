"""The shared Discord transport hides no person's message from the agent (#94 step 9f).

Every message reaches the agent, or the agent is told plainly that something
was missed. Three ways the transport used to break that:

1. **The first message after it starts** was replaced by the continuity gap
   the transport declares when it starts.
2. **A message sent before the runner's notification stream was open** (the
   runner registered first) was dropped by the MCP SDK and journaled as
   delivered; so was every message sent to a runner whose stream had died
   while its session stayed registered.
3. **A message in a thread under a routed channel** carried the thread's id,
   which is not routed, and was dropped.

The review's fixes are pinned here too: a move about a thread message the
agent read mid-turn goes to the thread (`ThreadMoveFromTheTurnTests`, the
transport and the reference); the thread lookup is bounded and its failures
are remembered (`ThreadWaitTests`, `RestNetworkErrorTests`, `SourceGapTests`);
a transport that dies mid-answer is a network error the runner reconnects from
(`HandshakeEndTests`); the client ends the sessions it drops
(`SessionEndTests`). CI runs this module on the lowest supported `mcp` too.

The transport's own pieces run on the Discord stand-in (loopback), first in
process with a stand-in for the MCP session, then as the process it is
(`nunchi.mcp_discord._binding.serve`: uvicorn, the mcp SDK, the gateway
runner), with Nunchi's own client. Nothing leaves loopback.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from evals.rehearsal.fake_discord.control import FakeDiscord
from nunchi.adapters.discord import DiscordPyTransport
from nunchi.integrations.discord_participant_transport import MCPDiscordTransport, thread_of
from nunchi.integrations.discord_room import DiscordRoomConnection
from nunchi.integrations.mcp_client import StreamableMCPClient
from nunchi.mcp_discord.authorization import ToolAuthorizer, make_tool_authorization
from nunchi.mcp_discord.events import v2_notification_from_dispatch
from nunchi.mcp_discord.gateway import GatewayProtocol
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.rest import DiscordRestClient, DiscordRestError
from nunchi.mcp_discord.runner import GatewayRunner
from nunchi.mcp_discord.server import (
    AuthenticatedSessionRegistry,
    GapAwareEnqueuer,
    TransportAuditJournal,
    deliver_targeted,
    pump_notifications,
)
from nunchi.mcp_discord.threads import ThreadDirectory
from nunchi.mcp_discord.tools import ToolExecutor
from nunchi.mcp_discord.ws import WSClient, WSClosed
from nunchi.observation import ObservationLimits, ParticipantBinding
from nunchi.reactions import ReactionCapability
from nunchi.room import RoomSettings
from tests.v2.test_shared_foundation import foundation, message

ROOT = Path(__file__).resolve().parents[2]
WORLD = {"guild": "g", "people": ["zoe"], "bots": {"Vigil": {}}, "channels": {"room": {}, "other": {}}}


def _sdk_missing() -> str:
    """Why the SDK-backed tests cannot run here: the mcp-discord extra (mcp, with uvicorn and starlette) is not installed."""

    missing = [name for name in ("mcp", "uvicorn", "starlette") if importlib.util.find_spec(name) is None]
    return f"needs the mcp-discord extra ({', '.join(missing)} not installed)" if missing else ""


SDK = unittest.skipIf(bool(_sdk_missing()), _sdk_missing())


def _wait(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return bool(predicate())


def _kill(stream) -> None:
    """End a notification stream the way a dead network does: the socket goes, whatever is reading it."""

    # urllib's own socket: only a test reaches for it. Not `close()`: another thread is reading the stream.
    with contextlib.suppress(AttributeError, OSError):
        stream.fp.raw._sock.shutdown(socket.SHUT_RDWR)


def _read(client: StreamableMCPClient, stream, into: list) -> threading.Thread:
    """Read a notification stream into ``into`` until it ends."""

    def run() -> None:
        # A stream killed under a reader ends it in whatever way urllib's closed socket does.
        with contextlib.suppress(OSError, AttributeError):
            for _, params in client.notifications(stream):
                into.append(params)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


# -- the threads a channel belongs to -------------------------------------------------------------------


class _Rest:
    """A REST client that knows some channels, and fails on request."""

    def __init__(self, channels: dict[str, dict]) -> None:
        self.channels = channels
        self.reads: list[str] = []
        self.fail: DiscordRestError | None = None

    def get_channel(self, channel_id: str) -> dict:
        self.reads.append(channel_id)
        if self.fail is not None:
            raise self.fail
        return self.channels[channel_id]


class ThreadDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rest = _Rest(
            {
                "10": {"id": "10", "type": 0, "parent_id": None},
                "11": {"id": "11", "type": 11, "parent_id": "10"},
                "12": {"id": "12", "type": 12, "parent_id": "10"},
                "20": {"id": "20", "type": 0, "parent_id": None},
                "21": {"id": "21", "type": 11, "parent_id": "20"},
                "30": {"id": "30", "type": 4, "parent_id": "10"},
            }
        )
        self.now = [0.0]
        self.threads = ThreadDirectory(self.rest, frozenset({"10"}), clock=lambda: self.now[0])

    def test_a_thread_belongs_to_the_routed_channel_it_was_opened_under(self):
        self.assertEqual("10", self.threads.parent_of("11"))
        self.assertEqual("10", self.threads.parent_of("12"))

    def test_nothing_else_is_part_of_a_room(self):
        self.assertIsNone(self.threads.parent_of("10"), "the room itself is not a thread")
        self.assertIsNone(self.threads.parent_of("21"), "a thread under a channel that is not routed")
        self.assertIsNone(self.threads.parent_of("20"))
        self.assertIsNone(self.threads.parent_of("30"), "a channel inside a category is not a thread")

    def test_what_is_not_a_snowflake_is_never_asked_about(self):
        for channel in ("", "12/../34", "abc", "11?x"):
            self.assertIsNone(self.threads.parent_of(channel))
        self.assertEqual([], self.rest.reads)

    def test_an_answer_is_asked_for_once(self):
        for _ in range(3):
            self.assertEqual("10", self.threads.parent_of("11"))
            self.assertIsNone(self.threads.parent_of("21"))
        self.assertEqual(["11", "21"], self.rest.reads)

    def test_when_discord_cannot_say_the_caller_hears_of_it_and_nothing_is_remembered_as_not_a_thread(self):
        self.rest.fail = DiscordRestError(403, "no access")
        with self.assertRaises(DiscordRestError):
            self.threads.parent_of("11")
        self.rest.fail = None
        self.now[0] = 100.0
        self.assertEqual("10", self.threads.parent_of("11"))

    def test_a_failed_lookup_is_not_retried_at_once(self):
        self.rest.fail = DiscordRestError(500, "down")
        for _ in range(3):
            with self.assertRaises(DiscordRestError) as raised:
                self.threads.parent_of("11")
            self.assertEqual(500, raised.exception.status)
        self.assertEqual(["11"], self.rest.reads, "one request, not one per message")
        self.rest.fail = None
        self.now[0] = 31.0
        self.assertEqual("10", self.threads.parent_of("11"))
        self.assertEqual(["11", "11"], self.rest.reads)

    def test_any_failure_is_remembered_a_timeout_included(self):
        self.rest.fail = TimeoutError("timed out")  # type: ignore[assignment]
        with self.assertRaises(TimeoutError):
            self.threads.parent_of("11")
        for _ in range(2):
            with self.assertRaises(DiscordRestError) as raised:
                self.threads.parent_of("11")
            self.assertIn("timed out", str(raised.exception))
        self.assertEqual(["11"], self.rest.reads, "the next messages do not wait for it again")


class ThreadWaitTests(unittest.IsolatedAsyncioTestCase):
    """The gateway's read loop waits for a thread lookup only so long."""

    async def test_a_slow_lookup_fails_within_the_bound_and_is_not_waited_for_again(self):
        release = threading.Event()
        self.addCleanup(release.set)

        class Slow:
            def __init__(self):
                self.reads: list[str] = []

            def get_channel(self, channel_id):
                self.reads.append(channel_id)
                release.wait(10)
                return {"id": channel_id, "type": 11, "parent_id": "10"}

        rest = Slow()
        threads = ThreadDirectory(rest, frozenset({"10"}))

        def placed() -> bool:
            try:
                return threads.parent_of("11") == "10"
            except DiscordRestError:
                return False

        started = time.monotonic()
        with self.assertRaises(DiscordRestError):
            await threads.parent_within("11", 0.2)
        self.assertLess(time.monotonic() - started, 5)
        with self.assertRaises(DiscordRestError):
            await threads.parent_within("11", 0.2)
        self.assertEqual(["11"], rest.reads, "the second message did not start a second lookup")
        # The lookup that was left running finishes, and its answer replaces the failure.
        release.set()
        self.assertTrue(await asyncio.to_thread(_wait, placed))

    async def test_a_quick_lookup_answers_as_parent_of_does(self):
        rest = _Rest({"11": {"id": "11", "type": 11, "parent_id": "10"}, "20": {"id": "20", "type": 0, "parent_id": None}})
        threads = ThreadDirectory(rest, frozenset({"10"}))
        self.assertEqual("10", await threads.parent_within("11"))
        self.assertIsNone(await threads.parent_within("20"))


def _loopback_server(test: unittest.TestCase, behave) -> str:
    """A server on loopback that reads one request per connection, then does what ``behave(connection)`` says."""

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    test.addCleanup(listener.close)
    held = []

    def run() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            held.append(connection)
            connection.settimeout(5)
            with contextlib.suppress(OSError):
                connection.recv(65536)
                behave(connection)

    threading.Thread(target=run, daemon=True).start()
    test.addCleanup(lambda: [c.close() for c in held])
    return f"http://127.0.0.1:{listener.getsockname()[1]}"


class RestNetworkErrorTests(unittest.TestCase):
    """A hung, reset or cut-short Discord answer is a `DiscordRestError`, whatever urllib raises for it."""

    def serve(self, behave):
        return _loopback_server(self, behave)

    def get(self, base: str):
        from unittest import mock

        from nunchi.mcp_discord import rest

        with mock.patch.object(rest, "_TIMEOUT_SECONDS", 0.5):
            return DiscordRestClient("t", base_url=base).get_channel("11")

    def test_a_server_that_never_answers(self):
        base = self.serve(lambda connection: time.sleep(2))
        with self.assertRaises(DiscordRestError) as raised:
            self.get(base)
        self.assertIsNone(raised.exception.status)

    def test_a_connection_that_is_reset(self):
        import struct

        def reset(connection):
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            connection.close()

        with self.assertRaises(DiscordRestError):
            self.get(self.serve(reset))

    def test_a_body_cut_short(self):
        def cut(connection):
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 200\r\nContent-Type: application/json\r\n\r\n{")
            connection.close()

        with self.assertRaises(DiscordRestError):
            self.get(self.serve(cut))


class SourceGapTests(unittest.TestCase):
    """Uncertainty about the source is one record and one gap, however many times it is declared."""

    ROUTES = {"vigil": frozenset({"42"}), "reviewer": frozenset({"43"})}

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "transport.jsonl"
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.enqueuer = GapAwareEnqueuer(self.queue, TransportAuditJournal(self.path), self.ROUTES)

    def records(self, outcome: str) -> list[tuple[str, str]]:
        lines = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
        return [(line["participant_id"], line["room_id"]) for line in lines if line["outcome"] == outcome]

    def test_a_route_already_pending_with_no_gap_queued_is_not_recorded_again(self):
        for _ in range(5):
            self.enqueuer.declare_source_gap()
        self.assertEqual([("vigil", "42"), ("reviewer", "43")], self.records("source-gap"))

    def test_once_a_gap_is_queued_a_later_loss_is_recorded_and_gets_its_own_gap(self):
        event = {
            "delivery_id": "d1", "room_id": "42", "event": {"id": "discord:message:1"}, "actors": {},
            "continuity_gap": False, "transport_self_actor_id": "discord:actor:9",
        }
        self.enqueuer.declare_source_gap()
        self.assertTrue(self.enqueuer(event))
        self.assertEqual([("vigil", "42")], self.records("gap-signal"))
        self.enqueuer.declare_source_gap()
        self.assertEqual([("vigil", "42"), ("reviewer", "43"), ("vigil", "42")], self.records("source-gap"))
        self.assertTrue(self.enqueuer({**event, "delivery_id": "d2"}))
        self.assertEqual([("vigil", "42"), ("vigil", "42")], self.records("gap-signal"))


class ThreadEventTests(unittest.TestCase):
    MESSAGE = {
        "id": "301",
        "channel_id": "300",
        "guild_id": "1",
        "author": {"id": "5", "username": "zoe"},
        "content": "in the thread",
        "mentions": [],
        "mention_everyone": False,
    }

    def notify(self, **kwargs):
        return v2_notification_from_dispatch(
            "MESSAGE_CREATE",
            self.MESSAGE,
            sequence=7,
            delivery_epoch="session",
            transport_self_actor_id="discord:actor:9",
            **kwargs,
        )

    def test_a_message_in_a_thread_is_in_the_room_and_names_its_thread(self):
        notification = self.notify(room_id="200", thread_id="300")
        self.assertEqual("200", notification["room_id"])
        self.assertEqual("discord:message:300", notification["event"]["thread_root_event_id"])

    def test_a_message_outside_a_thread_names_none(self):
        notification = self.notify()
        self.assertEqual("300", notification["room_id"])
        self.assertNotIn("thread_root_event_id", notification["event"])

    def test_the_first_message_of_a_forum_post_starts_its_thread_and_names_no_other(self):
        starter = {**self.MESSAGE, "id": "300"}
        notification = v2_notification_from_dispatch(
            "MESSAGE_CREATE", starter, sequence=7, delivery_epoch="s", transport_self_actor_id="discord:actor:9",
            room_id="200", thread_id="300",
        )
        self.assertEqual("200", notification["room_id"])
        self.assertNotIn("thread_root_event_id", notification["event"])

    def test_a_reaction_in_a_thread_is_the_rooms_reaction(self):
        notification = v2_notification_from_dispatch(
            "MESSAGE_REACTION_ADD",
            {"channel_id": "300", "user_id": "5", "message_id": "301", "emoji": {"id": None, "name": "\N{THUMBS UP SIGN}"}},
            sequence=8,
            delivery_epoch="session",
            transport_self_actor_id="discord:actor:9",
            room_id="200",
            thread_id="300",
        )
        self.assertEqual("200", notification["room_id"])
        self.assertEqual("discord:message:301", notification["event"]["target_event_id"])


class ThreadOfTests(unittest.TestCase):
    EVENTS = [
        {"id": "discord:message:1"},
        {"id": "discord:message:2", "thread_root_event_id": "discord:message:300"},
        {"id": "discord:message:3", "thread_root_event_id": "not-a-discord-id"},
    ]

    def wake(self):
        return {"room": {"id": "200"}, "events": self.EVENTS}

    def test_a_move_about_a_message_in_a_thread_goes_to_the_thread(self):
        for action in (
            {"kind": "reply", "target_event_id": "discord:message:2", "origin_event_id": "discord:message:2"},
            {"kind": "reaction", "target_event_id": "discord:message:2"},
            {"kind": "message", "origin_event_id": "discord:message:2"},
        ):
            with self.subTest(kind=action["kind"]):
                self.assertEqual("300", thread_of(action, self.wake()))

    def test_a_move_about_any_other_message_goes_to_the_room(self):
        self.assertIsNone(thread_of({"kind": "reply", "target_event_id": "discord:message:1"}, self.wake()))
        self.assertIsNone(thread_of({"kind": "reply", "target_event_id": "discord:message:3"}, self.wake()))
        self.assertIsNone(thread_of({"kind": "message", "origin_event_id": "discord:message:9"}, self.wake()))
        self.assertIsNone(thread_of({"kind": "message"}, {"room": {"id": "200"}}))


# -- the runner reads threads --------------------------------------------------------------------------


class _Socket:
    """A gateway socket that plays a script of frames, then closes."""

    def __init__(self, frames: list[dict]) -> None:
        self.frames = [json.dumps(frame) for frame in frames]
        self.sent: list[dict] = []

    async def receive_text(self) -> str:
        if self.frames:
            return self.frames.pop(0)
        raise WSClosed(1000)

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def send_close(self, code: int = 1000, reason: str = "") -> None:
        pass

    async def close(self) -> None:
        pass


def _dispatch(sequence: int, event: str, data: dict) -> dict:
    return {"op": 0, "s": sequence, "t": event, "d": data}


class RunnerThreadTests(unittest.IsolatedAsyncioTestCase):
    ROOM = "200"
    THREAD = "300"
    ELSEWHERE = "400"

    async def play(self, frames: list[dict], parent):
        events: list[tuple[dict, bool]] = []
        gaps: list[int] = []
        ready = _dispatch(1, "READY", {"session_id": "s", "user": {"id": "9"}, "resume_gateway_url": "wss://x"})
        hello = {"op": 10, "d": {"heartbeat_interval": 60000}}
        socket_ = _Socket([hello, ready, *frames])
        shutdown = asyncio.Event()

        async def connect(_url):
            # One connection; the next attempt ends the run.
            shutdown.set()
            return socket_

        runner = GatewayRunner(
            GatewayProtocol("test-token"),
            lambda event, in_thread=False: events.append((event, in_thread)),
            allowed_channel_ids=frozenset({self.ROOM}),
            on_source_gap=lambda: gaps.append(len(events)),
            thread_parent=parent,
            connect=connect,
            initial_backoff=0.01,
        )
        await asyncio.wait_for(runner.run(shutdown), 5)
        # The first gap is the fresh process's own, declared before it connects.
        self.assertEqual(0, gaps[0])
        return events, gaps[1:]

    @staticmethod
    def message(sequence: int, channel: str, message_id: str) -> dict:
        return _dispatch(
            sequence,
            "MESSAGE_CREATE",
            {"id": message_id, "channel_id": channel, "author": {"id": "5", "username": "zoe"}, "content": "hi", "mentions": []},
        )

    @staticmethod
    def reaction(sequence: int, channel: str, message_id: str) -> dict:
        return _dispatch(
            sequence,
            "MESSAGE_REACTION_ADD",
            {"channel_id": channel, "user_id": "5", "message_id": message_id, "emoji": {"id": None, "name": "\N{THUMBS UP SIGN}"}},
        )

    async def test_messages_and_reactions_in_a_thread_of_the_room_are_the_rooms(self):
        async def parent(channel):
            return {self.THREAD: self.ROOM}.get(channel)

        events, gaps = await self.play(
            [
                self.message(2, self.ROOM, "1001"),
                self.message(3, self.THREAD, "1002"),
                self.reaction(4, self.THREAD, "1002"),
                self.message(5, self.ELSEWHERE, "1003"),
            ],
            parent,
        )
        self.assertEqual([False, True, True], [in_thread for _, in_thread in events])
        message, thread_message, thread_reaction = [event for event, _ in events]
        self.assertEqual(self.ROOM, message["room_id"])
        self.assertEqual((self.ROOM, "discord:message:300"), (thread_message["room_id"], thread_message["event"]["thread_root_event_id"]))
        self.assertEqual((self.ROOM, "discord:message:1002"), (thread_reaction["room_id"], thread_reaction["event"]["target_event_id"]))
        self.assertEqual([], gaps)

    async def test_a_lookup_that_fails_declares_a_gap_and_the_next_message_still_arrives(self):
        async def parent(channel):
            if channel == self.THREAD:
                raise DiscordRestError(None, "Discord is unreachable")
            return None

        events, gaps = await self.play([self.message(2, self.THREAD, "1002"), self.message(3, self.ROOM, "1003")], parent)
        self.assertEqual(["discord:message:1003"], [event["event"]["id"] for event, _ in events])
        self.assertEqual([0], gaps, "a gap before the message it could not place was dropped; nothing was dropped quietly")

    async def test_without_a_directory_a_thread_is_another_channel(self):
        events, gaps = await self.play([self.message(2, self.THREAD, "1002")], None)
        self.assertEqual(([], []), (events, gaps))


# -- the transport's pieces on the stand-in, in process --------------------------------------------------


class _Session:
    """What the MCP SDK's session is to `deliver_targeted`: something that takes a notification."""

    def __init__(self) -> None:
        self.received: list[dict] = []

    async def send_notification(self, notification) -> None:
        self.received.append(dict(notification.params))


class _Notification:
    def __init__(self, params: dict) -> None:
        self.params = params


class Rig:
    """The pieces `serve()` wires, around a stand-in session: gateway runner, enqueuer, pump, registry, thread directory."""

    def __init__(self, test: unittest.TestCase, *, threads_in_room: bool = True, queue_maxsize: int = 64, register: bool = True) -> None:
        self.out = Path(tempfile.mkdtemp(prefix="gaps-rig-"))
        test.addCleanup(shutil.rmtree, self.out, True)
        self.fd = FakeDiscord(WORLD, self.out).start()
        self.room = self.fd.world.channel("room").id
        self.bot = self.fd.world.member("Vigil").id
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self.journal = self.out / "transport-delivery-audit.jsonl"
        self.registry = AuthenticatedSessionRegistry()
        self.session = _Session()
        self.routes = {"vigil": frozenset({self.room})}
        self.enqueuer = GapAwareEnqueuer(
            self.queue, TransportAuditJournal(self.journal), self.routes, wants_threads=self.registry.threads_in_room
        )
        self.rest = DiscordRestClient(self.fd.token("Vigil"), base_url=self.fd.rest_url)
        self.threads = ThreadDirectory(self.rest, frozenset({self.room}))
        self.shutdown = asyncio.Event()
        self.threads_in_room = threads_in_room
        self.register = register
        self.tasks: list[asyncio.Task] = []

        async def thread_parent(channel_id):
            if not self.registry.threads_wanted(self.routes):
                return None
            return await asyncio.to_thread(self.threads.parent_of, channel_id)

        self.runner = GatewayRunner(
            GatewayProtocol(self.fd.token("Vigil")),
            self.enqueuer,
            allowed_channel_ids=frozenset({self.room}),
            on_source_gap=self.enqueuer.declare_source_gap,
            thread_parent=thread_parent,
            connect=lambda url: WSClient.connect(url.replace("wss://gateway.discord.gg", self.fd.gateway_url)),
            rng=lambda: 0.5,
            initial_backoff=0.05,
        )

    async def start(self) -> None:
        if self.register:
            self.registry.bind(
                self.session,
                participant_id="vigil",
                room_id=self.room,
                transport_self_actor_id=f"discord:actor:{self.bot}",
                threads_in_room=self.threads_in_room,
            )

        async def send(params: dict) -> bool:
            return await deliver_targeted(self.registry, params, _Notification(params))

        self.tasks.append(asyncio.create_task(self.runner.run(self.shutdown)))
        self.tasks.append(
            asyncio.create_task(
                pump_notifications(
                    self.queue,
                    send,
                    shutdown=self.shutdown,
                    on_delivery_gap=self.enqueuer.declare_delivery_gap,
                    on_delivery_success=self.enqueuer.record_delivery,
                    hold=self.enqueuer.behind_a_failed_gap,
                )
            )
        )
        await asyncio.to_thread(self.fd.wait_for, lambda record: record.get("t") == "READY", 10)

    def outcomes(self) -> list[str]:
        try:
            return [json.loads(line)["outcome"] for line in self.journal.read_text().splitlines() if line.strip()]
        except OSError:
            return []

    def heard(self) -> list[str | None]:
        """What the participant was told, in order: ``"<gap>"`` or the event's text."""
        return ["<gap>" if item["continuity_gap"] else item["event"].get("text") for item in self.session.received]

    async def post(self, channel: str, text: str) -> dict:
        return await asyncio.to_thread(self.fd.post, "zoe", channel, text)

    async def until(self, predicate, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            await asyncio.sleep(0.05)
        return predicate()

    async def stop(self) -> None:
        self.shutdown.set()
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with contextlib.suppress(BaseException):
                await task
        self.fd.stop()


class StartTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_first_message_after_the_transport_starts_arrives_behind_the_start_gap(self):
        rig = Rig(self)
        await rig.start()
        self.addAsyncCleanup(rig.stop)
        self.assertEqual(["source-gap"], rig.outcomes(), "a fresh process declares that it cannot know what came before")
        await rig.post("room", "the first message after the transport started")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 2), rig.heard())
        self.assertEqual(["<gap>", "the first message after the transport started"], rig.heard())
        await rig.post("room", "the second")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 3), rig.heard())
        self.assertEqual(["<gap>", "the first message after the transport started", "the second"], rig.heard(), "one gap, not one per message")
        self.assertEqual(
            ["source-gap", "gap-signal", "accepted", "gap-delivered", "client-delivered", "accepted", "client-delivered"],
            rig.outcomes(),
        )

    async def test_a_message_that_finds_no_registered_client_is_lost_with_a_gap_for_the_next(self):
        rig = Rig(self, register=False)
        await rig.start()
        self.addAsyncCleanup(rig.stop)
        await rig.post("room", "nobody is listening")
        self.assertTrue(await rig.until(lambda: "client-delivery-lost" in rig.outcomes()), rig.outcomes())
        self.assertEqual([], rig.heard())
        rig.registry.bind(
            rig.session, participant_id="vigil", room_id=rig.room, transport_self_actor_id=f"discord:actor:{rig.bot}"
        )
        await rig.post("room", "now someone is")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 2), rig.heard())
        self.assertEqual(["<gap>", "now someone is"], rig.heard())


class ThreadRoomTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_message_in_a_thread_under_the_room_reaches_the_participant_as_part_of_the_room(self):
        rig = Rig(self)
        await rig.start()
        self.addAsyncCleanup(rig.stop)
        thread = (await asyncio.to_thread(rig.fd.create_thread, "zoe", "room", "details"))["id"]
        await rig.post("room", "in the room")
        await rig.post("details", "in the thread")
        await rig.post("details", "again in the thread")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 4), rig.heard())
        self.assertEqual(["<gap>", "in the room", "in the thread", "again in the thread"], rig.heard())
        room_message, thread_message, again = [item["event"] for item in rig.session.received[1:]]
        self.assertEqual({rig.room}, {item["room_id"] for item in rig.session.received})
        self.assertNotIn("thread_root_event_id", room_message)
        self.assertEqual(f"discord:message:{thread}", thread_message["thread_root_event_id"])
        self.assertEqual(f"discord:message:{thread}", again["thread_root_event_id"])
        reads = [r for r in rig.fd.wire.records if r.get("kind") == "http" and r.get("route") == "/channels/{channel}" and r.get("bot") == "Vigil"]
        self.assertEqual(1, len(reads), "the thread's parent is asked for once")

    async def test_a_thread_under_a_channel_that_is_not_routed_is_not_the_room(self):
        rig = Rig(self)
        await rig.start()
        self.addAsyncCleanup(rig.stop)
        await asyncio.to_thread(rig.fd.create_thread, "zoe", "other", "elsewhere")
        await rig.post("elsewhere", "in another channel's thread")
        await rig.post("other", "in another channel")
        await rig.post("room", "in the room")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 2), rig.heard())
        self.assertEqual(["<gap>", "in the room"], rig.heard())
        self.assertEqual(["source-gap", "gap-signal", "accepted", "gap-delivered", "client-delivered"], rig.outcomes())

    async def test_a_thread_that_cannot_be_placed_declares_a_gap_instead_of_vanishing(self):
        rig = Rig(self)
        await rig.start()
        self.addAsyncCleanup(rig.stop)
        await asyncio.to_thread(rig.fd.create_thread, "zoe", "room", "details")
        await rig.post("room", "before")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 2), rig.heard())
        await asyncio.to_thread(rig.fd.fault, "GET", "/channels/{channel}", 403, 5)
        await rig.post("details", "in the thread, which Discord will not place")
        self.assertTrue(await rig.until(lambda: rig.outcomes().count("source-gap") == 2), rig.outcomes())
        await rig.post("room", "after")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 4), rig.heard())
        self.assertEqual(["<gap>", "before", "<gap>", "after"], rig.heard())

    async def test_a_participant_whose_binding_keeps_threads_out_hears_none_and_nothing_is_looked_up(self):
        rig = Rig(self, threads_in_room=False)
        await rig.start()
        self.addAsyncCleanup(rig.stop)
        await asyncio.to_thread(rig.fd.create_thread, "zoe", "room", "details")
        await rig.post("details", "in the thread")
        await rig.post("room", "in the room")
        self.assertTrue(await rig.until(lambda: len(rig.heard()) >= 2), rig.heard())
        await asyncio.sleep(0.3)
        self.assertEqual(["<gap>", "in the room"], rig.heard())
        reads = [r for r in rig.fd.wire.records if r.get("kind") == "http" and r.get("route") == "/channels/{channel}" and r.get("bot") == "Vigil"]
        self.assertEqual([], reads, "no participant wants threads: Discord is not asked about any channel")
        self.assertEqual(1, rig.outcomes().count("gap-signal"), "leaving a thread out is not a loss; no gap for it")

    async def test_a_room_with_two_participants_gives_each_what_its_binding_says(self):
        room = "42"
        queue: asyncio.Queue = asyncio.Queue(maxsize=16)
        registry = AuthenticatedSessionRegistry()
        with tempfile.TemporaryDirectory() as directory:
            enqueuer = GapAwareEnqueuer(
                queue,
                TransportAuditJournal(Path(directory) / "journal.jsonl"),
                {"vigil": frozenset({room}), "castor": frozenset({room})},
                wants_threads=registry.threads_in_room,
            )
            for participant, threads in (("vigil", True), ("castor", False)):
                registry.bind(
                    _Session(), participant_id=participant, room_id=room, transport_self_actor_id="discord:actor:9",
                    threads_in_room=threads,
                )
            event = {
                "schema_version": 2, "delivery_id": "d1", "room_id": room, "event": None, "actors": {},
                "continuity_gap": False, "transport_self_actor_id": "discord:actor:9",
            }
            self.assertTrue(enqueuer(event, in_thread=True))
            self.assertEqual(["vigil"], [queue.get_nowait()["target_participant_id"]])
            self.assertTrue(queue.empty())
            self.assertTrue(enqueuer({**event, "delivery_id": "d2"}))
            self.assertEqual({"vigil", "castor"}, {queue.get_nowait()["target_participant_id"] for _ in range(2)})
        # Nobody has registered yet: the default is that threads are part of the room.
        fresh = AuthenticatedSessionRegistry()
        self.assertTrue(fresh.threads_in_room("vigil", room))
        self.assertTrue(fresh.threads_wanted({"vigil": frozenset({room})}))
        self.assertFalse(registry.threads_wanted({"castor": frozenset({room})}))
        self.assertTrue(registry.threads_wanted({"vigil": frozenset({room}), "castor": frozenset({room})}))


class ThreadReplyTests(unittest.IsolatedAsyncioTestCase):
    """The agent's answer to a message in a thread goes into the thread."""

    async def asyncSetUp(self) -> None:
        self.out = Path(tempfile.mkdtemp(prefix="gaps-reply-"))
        self.addCleanup(shutil.rmtree, self.out, True)
        self.fd = FakeDiscord(WORLD, self.out).start()
        self.addCleanup(self.fd.stop)
        self.room = self.fd.world.channel("room").id
        self.other = self.fd.world.channel("other").id
        self.bot = self.fd.world.member("Vigil").id
        self.secret = secrets.token_bytes(32)
        rest = DiscordRestClient(self.fd.token("Vigil"), base_url=self.fd.rest_url)
        threads = ThreadDirectory(rest, frozenset({self.room}))
        self.authorizer = ToolAuthorizer(secret=self.secret, participant_routes={"vigil": frozenset({self.room})}, threads=threads)
        self.executor = ToolExecutor(rest, SendBackstop(50, 10), authorizer=self.authorizer)
        self.thread = (await asyncio.to_thread(self.fd.create_thread, "zoe", "room", "details"))["id"]
        self.elsewhere = (await asyncio.to_thread(self.fd.create_thread, "zoe", "other", "elsewhere"))["id"]

    def call(self, name: str, channel: str, **arguments):
        arguments = {"channel_id": channel, **arguments}
        authorization = make_tool_authorization(
            secret=self.secret, request_id=secrets.token_hex(4), participant_id="vigil", room_id=self.room, tool=name, arguments=arguments
        )
        return self.executor.call(
            name, {**arguments, "_nunchi_authorization": authorization},
            expected_route=("vigil", self.room), expected_self_actor_id=f"discord:actor:{self.bot}",
        )

    async def test_the_host_may_post_and_react_in_a_thread_of_the_authorized_room(self):
        asked = self.fd.post("zoe", "details", "a question in the thread")["id"]
        sent, ok = await asyncio.to_thread(self.call, "reply_message", self.thread, message_id=asked, content="an answer")
        self.assertTrue(ok, sent)
        self.assertEqual(self.thread, sent["message"]["channel_id"])
        _, ok = await asyncio.to_thread(self.call, "add_reaction", self.thread, message_id=asked, reaction="\N{THUMBS UP SIGN}")
        self.assertTrue(ok)
        self.assertEqual({self.thread}, {self.fd.world.messages[sent["message"]["message_id"]]["channel_id"]})

    async def test_the_authorization_covers_the_room_and_its_threads_only(self):
        for channel, why in ((self.other, "another channel"), (self.elsewhere, "a thread under another channel"), ("999", "an unknown channel")):
            with self.subTest(why):
                payload, ok = await asyncio.to_thread(self.call, "send_message", channel, content="hello")
                self.assertFalse(ok, payload)
                self.assertIn("channel binding mismatch", payload["error"])
        without = ToolAuthorizer(secret=self.secret, participant_routes={"vigil": frozenset({self.room})})
        arguments = {"channel_id": self.thread, "content": "x"}
        authorization = make_tool_authorization(
            secret=self.secret, request_id="r", participant_id="vigil", room_id=self.room, tool="send_message", arguments=arguments
        )
        ok, detail = without.verify(authorization=authorization, tool="send_message", arguments=arguments)
        self.assertFalse(ok, "a transport without a thread directory authorizes the room alone")
        self.assertIn("channel binding mismatch", detail)

    async def test_an_authorization_for_a_thread_that_cannot_be_placed_is_refused(self):
        await asyncio.to_thread(self.fd.fault, "GET", "/channels/{channel}", 403, 2)
        payload, ok = await asyncio.to_thread(self.call, "send_message", self.thread, content="hello")
        self.assertFalse(ok)
        self.assertIn("channel binding mismatch", payload["error"])


class _Client:
    """The MCP client `MCPDiscordTransport` calls: records the tool call and answers as the transport would."""

    def __init__(self, thread: str | None, room: str, bot: str) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.thread, self.room, self.bot = thread, room, bot

    def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        channel = arguments["channel_id"]
        if name in ("send_message", "reply_message"):
            body = {
                "message": {
                    "message_id": "777", "channel_id": channel, "author_id": self.bot, "author_is_bot": True,
                    "content": arguments["content"], "reply_to_message_id": arguments.get("message_id"),
                }
            }
        else:
            body = {"reaction": {"channel_id": channel, "message_id": arguments["message_id"], "reaction": arguments["reaction"], "operation": "add"}}
        return {"isError": False, "content": [{"type": "text", "text": json.dumps(body)}]}


class ParticipantTransportThreadTests(unittest.TestCase):
    ROOM, THREAD, BOT = "200", "300", "9"

    def transport(self) -> tuple[MCPDiscordTransport, _Client]:
        client = _Client(self.THREAD, self.ROOM, self.BOT)
        return MCPDiscordTransport(client, self.ROOM, "vigil", f"discord:actor:{self.BOT}", b"k" * 32), client

    def wake(self) -> dict:
        return {
            "request_id": "r1",
            "room": {"id": self.ROOM},
            "events": [
                {"id": "discord:message:1"},
                {"id": "discord:message:2", "thread_root_event_id": f"discord:message:{self.THREAD}"},
            ],
        }

    def test_a_reply_a_post_and_a_reaction_about_a_thread_message_go_to_the_thread(self):
        for action, tool in (
            ({"kind": "reply", "origin_event_id": "discord:message:2", "target_event_id": "discord:message:2", "text": "an answer"}, "reply_message"),
            ({"kind": "message", "origin_event_id": "discord:message:2", "text": "an answer"}, "send_message"),
            ({"kind": "reaction", "origin_event_id": "discord:message:2", "target_event_id": "discord:message:2", "reaction": "x", "operation": "add"}, "add_reaction"),
        ):
            with self.subTest(tool=tool):
                transport, client = self.transport()
                result = transport.dispatch(action=action, wake=self.wake())
                self.assertEqual("sent", result.delivery, result)
                self.assertEqual((tool, self.THREAD), (client.calls[0][0], client.calls[0][1]["channel_id"]))

    def test_everything_else_goes_to_the_room(self):
        transport, client = self.transport()
        action = {"kind": "reply", "origin_event_id": "discord:message:1", "target_event_id": "discord:message:1", "text": "an answer"}
        self.assertEqual("sent", transport.dispatch(action=action, wake=self.wake()).delivery)
        self.assertEqual(self.ROOM, client.calls[0][1]["channel_id"])

    def test_an_acknowledgement_from_another_channel_than_the_one_asked_is_not_a_confirmation(self):
        transport, client = self.transport()
        asked = client.call_tool

        def wrong_channel(name, arguments):
            result = asked(name, arguments)
            body = json.loads(result["content"][0]["text"])
            body["message"]["channel_id"] = self.ROOM
            result["content"][0]["text"] = json.dumps(body)
            return result

        client.call_tool = wrong_channel
        action = {"kind": "reply", "origin_event_id": "discord:message:2", "target_event_id": "discord:message:2", "text": "an answer"}
        self.assertEqual("unknown", transport.dispatch(action=action, wake=self.wake()).delivery)


class ThreadMoveFromTheTurnTests(unittest.TestCase):
    """The host gives its transport what the turn showed, not only the wake.

    The agent is woken by a message in the room. A message in a thread under the
    room reaches it another way: a look-again, a steering page, a history page,
    or its memory. A reply, post or reaction about that message still lands in
    its thread, on the transport (Claude Code, Codex) and the reference alike.
    """

    ROOM, THREAD, BOT = "200", "300", "9"
    IN_THREAD = "discord:message:301"
    ACTORS = {"human:zoe": {"kind": "human"}}
    ALLOWED = ReactionCapability(supported=True, authenticated=True, operations=("add",), reactions=("*",), permissions_revision="t")

    def setUp(self) -> None:
        self.loop = asyncio.new_event_loop()
        thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        thread.start()

        def stop() -> None:
            self.loop.call_soon_threadsafe(self.loop.stop)
            thread.join(5)
            self.loop.close()

        self.addCleanup(stop)

    def mcp_transport(self):
        client = _Client(self.THREAD, self.ROOM, self.BOT)
        transport = MCPDiscordTransport(client, self.ROOM, "vigil", f"discord:actor:{self.BOT}", b"k" * 32)
        return transport, lambda: [(name, arguments["channel_id"]) for name, arguments in client.calls]

    def reference_transport(self):
        moves = []

        class Channel:
            def __init__(channel, channel_id):
                channel.id = channel_id

            async def send(channel, text):
                moves.append(("send_message", str(channel.id)))
                return mock.Mock(id=900)

            def get_partial_message(channel, message_id):
                target = mock.Mock()

                async def reply(text, mention_author=False):
                    moves.append(("reply_message", str(channel.id)))
                    return mock.Mock(id=901)

                async def add_reaction(emoji):
                    moves.append(("add_reaction", str(channel.id)))

                target.reply, target.add_reaction = reply, add_reaction
                return target

        bot = mock.Mock()
        bot.get_channel = {int(self.ROOM): Channel(int(self.ROOM)), int(self.THREAD): Channel(int(self.THREAD))}.get
        return DiscordPyTransport(bot, self.loop, self.ROOM), lambda: list(moves)

    def post_in_thread(self, pipeline) -> None:
        pipeline.observation.observe(
            delivery_id="d-in-thread",
            event=message(self.IN_THREAD, thread_root_event_id=f"discord:message:{self.THREAD}"),
            actors=self.ACTORS,
        )

    def move(self, kind: str, wake: dict) -> dict:
        about = {"origin_event_id": self.IN_THREAD}
        if kind == "message":
            return {"kind": "message", "text": "an answer", **about}
        if kind == "reply":
            return {"kind": "reply", "target_event_id": self.IN_THREAD, "text": "an answer", **about}
        return {"kind": "reaction", "target_event_id": self.IN_THREAD, "reaction": "x", "operation": "add", **about}

    def play(self, make_transport, how: str, kind: str):
        transport, moves = make_transport()
        transport.reaction_capability = lambda: self.ALLOWED
        # With the window at one message, only the trigger is in the wake.
        limits = ObservationLimits(snapshot_events=1) if how in ("history", "memory") else None
        binding = ParticipantBinding(
            participant_id="vigil", actor_id=f"discord:actor:{self.BOT}", platform="discord", room_id=self.ROOM,
            continuity_scope_id=f"discord:channel:{self.ROOM}",
        )
        pages = []

        def participant(*, wake, expand, **_):
            self.assertEqual(["discord:message:400"], [event["id"] for event in wake["events"]])
            if how in ("look again", "steering"):
                # It arrives while the agent works, and only the page shows it.
                self.post_in_thread(pipeline)
                pages.append(expand(direction="new" if how == "look again" else "news"))
            elif how == "history":
                pages.append(expand(direction="before"))
            return self.move(kind, wake)

        pipeline, _, _, _ = foundation(participant=participant, transport=transport, binding=binding, limits=limits)
        if how in ("history", "memory"):
            self.post_in_thread(pipeline)
            pipeline.observation.observe(delivery_id="d-later", event=message("discord:message:302"), actors=self.ACTORS)
        if how == "memory":
            # An earlier turn stayed quiet about it: the wake's memory points at it.
            pipeline.host.memory.record_silence(about_event_id=self.IN_THREAD)
        outcome = pipeline.handle_delivery(delivery_id="d-wake", event=message("discord:message:400"), actors=self.ACTORS)
        if how != "memory":
            self.assertIn(self.IN_THREAD, [event["id"] for event in pages[0]["events"]], "the agent read it on a page")
        return outcome.opportunities[0].transport, moves()

    def test_a_move_about_a_thread_message_the_agent_read_mid_turn_goes_to_the_thread(self):
        tools = {"message": "send_message", "reply": "reply_message", "reaction": "add_reaction"}
        for transport in ("mcp", "reference"):
            for how in ("look again", "steering", "history", "memory"):
                for kind in tools:
                    with self.subTest(transport=transport, how=how, kind=kind):
                        result, moves = self.play(getattr(self, f"{transport}_transport"), how, kind)
                        self.assertEqual("sent", result.delivery, result)
                        self.assertEqual([(tools[kind], self.THREAD)], moves)

    def test_a_move_about_a_room_message_still_goes_to_the_room(self):
        for transport in ("mcp", "reference"):
            with self.subTest(transport=transport):
                send, moves = getattr(self, f"{transport}_transport")()
                pipeline, *_ = foundation(
                    participant=lambda *, wake, **_: {"kind": "message", "origin_event_id": wake["trigger_event_id"], "text": "an answer"},
                    transport=send,
                    binding=ParticipantBinding(
                        participant_id="vigil", actor_id=f"discord:actor:{self.BOT}", platform="discord", room_id=self.ROOM,
                        continuity_scope_id=f"discord:channel:{self.ROOM}",
                    ),
                )
                outcome = pipeline.handle_delivery(delivery_id="d-wake", event=message("discord:message:400"), actors=self.ACTORS)
                self.assertEqual("sent", outcome.opportunities[0].transport.delivery)
                self.assertEqual([("send_message", self.ROOM)], moves())


class StreamEndTests(unittest.TestCase):
    """A stream that ends in the middle of a chunk is a network error the runner reconnects from."""

    def test_the_server_going_away_mid_chunk_raises_a_network_error_not_an_http_one(self):
        import http.client

        class Response:
            closed = False

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.closed = True

            def __iter__(self):
                yield b'data: {"method": "m", "params": {"n": 1}}\n'
                yield b"\n"
                raise http.client.IncompleteRead(b"")

        response = Response()
        client = StreamableMCPClient("http://127.0.0.1:1/mcp")
        stream = client.notifications(response)
        self.assertEqual(("m", {"n": 1}), next(stream))
        with self.assertRaises(OSError):
            next(stream)
        self.assertTrue(response.closed)


class HandshakeEndTests(unittest.TestCase):
    """A transport that dies in the middle of an answer during the handshake is a network error too.

    The runners reconnect on `OSError`; `http.client.IncompleteRead` is not one,
    and used to end the runner.
    """

    def cut_off(self, connection) -> None:
        connection.sendall(
            b"HTTP/1.1 200 OK\r\nmcp-session-id: s1\r\nContent-Type: application/json\r\nContent-Length: 200\r\n\r\n{"
        )
        connection.close()

    def client(self) -> StreamableMCPClient:
        return StreamableMCPClient(_loopback_server(self, self.cut_off) + "/mcp", timeout_seconds=5)

    def test_connect_call_and_registration_raise_a_network_error(self):
        client = self.client()
        with self.assertRaises(ConnectionError):
            client.connect()
        client.session_id = "s1"
        with self.assertRaises(ConnectionError):
            client.call("tools/list", {})
        binding = ParticipantBinding(
            participant_id="vigil", actor_id="discord:actor:9", platform="discord", room_id="200",
            continuity_scope_id="discord:channel:200",
        )
        connection = DiscordRoomConnection(client=client, binding=binding, secret=b"k" * 48, label="test", surface="test")
        with self.assertRaises(ConnectionError):
            connection.register()

    def test_the_runner_reconnects_instead_of_ending(self):
        client = self.client()
        binding = ParticipantBinding(
            participant_id="vigil", actor_id="discord:actor:9", platform="discord", room_id="200",
            continuity_scope_id="discord:channel:200",
        )
        connection = DiscordRoomConnection(client=client, binding=binding, secret=b"k" * 48, label="test", surface="test")
        marks, stop = [], threading.Event()
        connection.interrupted = lambda: marks.append(1)  # type: ignore[method-assign]
        connection.serve(stop=stop, sleep=lambda _: stop.set())
        self.assertEqual([1], marks, "it marked the gap and went back to reconnect")


@SDK
class SessionEndTests(unittest.TestCase):
    """The client ends the MCP session it drops, so a reconnecting runner leaves none alive in the transport."""

    def rejected(self, url: str, session_id: str) -> int | None:
        """The HTTP status the transport answers a call on ``session_id`` with, or None when it answers."""
        import urllib.error

        probe = StreamableMCPClient(url, timeout_seconds=10)
        probe.session_id = session_id
        try:
            probe.call("tools/list", {})
        except urllib.error.HTTPError as exc:
            return exc.code
        return None

    def test_closing_ends_the_session(self):
        transport = RealTransport(self)
        client = StreamableMCPClient(transport.url, timeout_seconds=10)
        session = client.connect()
        self.assertIsNone(self.rejected(transport.url, session), "alive while it is in use")
        client.close()
        self.assertIsNone(client.session_id)
        self.assertIn(self.rejected(transport.url, session), (400, 404), "the transport ended it")
        client.close()  # nothing to end

    def test_a_reconnect_ends_the_session_it_replaces(self):
        transport = RealTransport(self)
        client = StreamableMCPClient(transport.url, timeout_seconds=10)
        first = client.connect()
        second = client.connect()
        self.assertNotEqual(first, second)
        self.assertIn(self.rejected(transport.url, first), (400, 404))
        self.assertIsNone(self.rejected(transport.url, second))

    def test_a_transport_that_is_gone_does_not_stop_the_client_closing(self):
        client = StreamableMCPClient("http://127.0.0.1:1/mcp", timeout_seconds=2)
        client.session_id = "s1"
        client.close()
        self.assertIsNone(client.session_id)


class _Stop(BaseException):
    """Ends a loop that would run forever."""


class CodexRunnerLoopTests(unittest.TestCase):
    """`nunchi-codex-room-runner` has its own serve loop: the same order as `DiscordRoomConnection.serve`."""

    def run_main(self, client_class):
        from unittest import mock

        from nunchi.integrations import codex_v2

        steps: list[str] = []
        transport = {"url": "http://127.0.0.1:1/mcp", "timeout_seconds": 5, "output_key_env": "K"}

        class Runtime:
            def __init__(self, config, client):
                pass

            def register_transport(self):
                steps.append("register")

            def handle(self, params):
                steps.append("handle")

            def transport_interrupted(self):
                steps.append("gap")

        def sleep(_seconds):
            raise _Stop

        with (
            mock.patch.object(codex_v2, "keep_private", return_value="private"),
            mock.patch.object(codex_v2, "load_pinned_config", return_value={"transport": transport}),
            mock.patch.object(codex_v2, "StreamableMCPClient", lambda *a, **k: client_class(steps)),
            mock.patch.object(codex_v2, "CodexRoomRuntime", Runtime),
            mock.patch.object(codex_v2.time, "sleep", sleep),
        ):
            with self.assertRaises(_Stop):
                codex_v2.main(["--config", "c", "--config-sha256", "s"])
        return steps

    def test_it_opens_the_stream_marks_the_gap_and_registers_before_it_reads(self):
        class Client:
            def __init__(self, steps):
                self.steps = steps

            def connect(self):
                self.steps.append("connect")

            def open_stream(self):
                self.steps.append("open_stream")
                return self

            def close(self):
                self.steps.append("close")

            def notifications(self, stream=None):
                self.steps.append("read")
                yield "notifications/nunchi/v2/discord-event", {}
                raise OSError("the stream died")

        self.assertEqual(
            ["connect", "open_stream", "gap", "register", "read", "handle", "close", "gap"],
            self.run_main(Client),
        )


# -- the setting, in the core --------------------------------------------------------------------------


class BindingSettingTests(unittest.TestCase):
    def binding(self, **fields) -> ParticipantBinding:
        return ParticipantBinding(
            participant_id="vigil", actor_id="discord:actor:9", platform="discord", room_id="200",
            continuity_scope_id="discord:channel:200", **fields,
        )

    def test_threads_are_part_of_the_room_unless_the_binding_says_otherwise(self):
        self.assertTrue(self.binding().threads_in_room)
        self.assertFalse(self.binding(threads_in_room=False).threads_in_room)

    def test_the_setting_is_true_or_false_and_nothing_else(self):
        for value in ("false", 0, None, "yes"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.binding(threads_in_room=value)

    def test_the_setting_is_a_binding_key_every_integration_reads_through_the_shared_settings(self):
        base = Path(tempfile.mkdtemp(prefix="gaps-settings-"))
        self.addCleanup(shutil.rmtree, base, True)
        profile = json.dumps(
            {
                "profile_id": "p", "participant_id": "vigil", "actor_id": "discord:actor:9",
                "instructions": "Participate directly.", "provenance": "test",
            }
        ).encode()
        (base / "profile.json").write_bytes(profile)
        for given, wanted in ((None, True), (True, True), (False, False)):
            with self.subTest(setting=given):
                binding = {
                    "participant_id": "vigil", "actor_id": "discord:actor:9", "platform": "discord", "room_id": "200",
                    "continuity_scope_id": "discord:channel:200",
                }
                if given is not None:
                    binding["threads_in_room"] = given
                settings = RoomSettings.from_config(
                    {
                        "schema_version": 2,
                        "binding": binding,
                        "profile": {"path": str(base / "profile.json"), "sha256": hashlib.sha256(profile).hexdigest()},
                        "attention": {"policy": {}, "model": None},
                        "limits": {},
                        "state_directory": str(base / "state"),
                    },
                    label="test",
                )
                self.assertEqual(wanted, settings.binding.threads_in_room)


# -- the transport as a process, on the real MCP SDK ------------------------------------------------------

BOOT = """
import functools, os, sys
from nunchi.mcp_discord import _binding
from nunchi.mcp_discord.config import load_config
from nunchi.mcp_discord.rest import DiscordRestClient
from nunchi.mcp_discord.ws import WSClient

gateway, rest = os.environ["GAPS_GATEWAY_URL"], os.environ["GAPS_REST_URL"]
original = WSClient.connect.__func__

async def connect(cls, url, *, connect_timeout=30.0):
    return await original(cls, url.replace("wss://gateway.discord.gg", gateway), connect_timeout=connect_timeout)

WSClient.connect = classmethod(connect)
_binding.DiscordRestClient = functools.partial(DiscordRestClient, base_url=rest)
sys.exit(_binding.serve(load_config(os.environ)))
"""


class RealTransport:
    """`nunchi-mcp-discord`'s own `serve()` (uvicorn, the mcp SDK, the gateway runner), pointed at the stand-in."""

    def __init__(self, test: unittest.TestCase, participants: tuple[str, ...] = ("vigil",)) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="gaps-transport-"))
        test.addCleanup(shutil.rmtree, self.base, True)
        (self.base / "out").mkdir()
        self.fd = FakeDiscord(WORLD, self.base / "out").start()
        test.addCleanup(self.fd.stop)
        self.room = self.fd.world.channel("room").id
        self.bot = self.fd.world.member("Vigil").id
        self.key = secrets.token_urlsafe(48)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        state = self.base / "state"
        state.mkdir()
        self.journal = state / "transport-delivery-audit.jsonl"
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.base),
            "TMPDIR": str(self.base),
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "GAPS_GATEWAY_URL": self.fd.gateway_url,
            "GAPS_REST_URL": self.fd.rest_url,
            "NUNCHI_DISCORD_TOKEN": self.fd.token("Vigil"),
            "NUNCHI_DISCORD_PARTICIPANT_ROUTES": json.dumps({name: [self.room] for name in participants}),
            "NUNCHI_DISCORD_OUTPUT_HMAC_KEY": self.key,
            "NUNCHI_DISCORD_STATE_DIRECTORY": str(state),
            "NUNCHI_MCP_DISCORD_HOST": "127.0.0.1",
            "NUNCHI_MCP_DISCORD_PORT": str(self.port),
        }
        self.log = self.base / "transport.log"
        with open(self.log, "wb") as handle:
            self.process = subprocess.Popen(
                [sys.executable, "-c", BOOT], env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True
            )
        test.addCleanup(self.stop)
        self.clients: list[StreamableMCPClient] = []
        self.streams: list = []
        self.stops: list[threading.Event] = []
        test.addCleanup(self.close_streams)
        self.fd.wait_for(lambda record: record.get("kind") == "ws" and record.get("t") == "READY", timeout=60)
        if not _wait(lambda: self.process.poll() is not None or socket.socket().connect_ex(("127.0.0.1", self.port)) == 0, 60) or self.process.poll() is not None:
            raise AssertionError(f"the transport did not come up: {self.log.read_text()[-800:]}")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/mcp"

    def outcomes(self) -> list[str]:
        try:
            return [json.loads(line)["outcome"] for line in self.journal.read_text().splitlines() if line.strip()]
        except OSError:
            return []

    def connection(self, participant: str = "vigil", *, threads_in_room: bool = True) -> DiscordRoomConnection:
        """A runner's connection for a participant: the real client and registration, hearing into ``connection.heard``."""

        client = StreamableMCPClient(self.url, timeout_seconds=30)
        binding = ParticipantBinding(
            participant_id=participant, actor_id=f"discord:actor:{self.bot}", platform="discord", room_id=self.room,
            continuity_scope_id=f"discord:channel:{self.room}", threads_in_room=threads_in_room,
        )
        connection = DiscordRoomConnection(client=client, binding=binding, secret=self.key.encode(), label="test", surface="test")
        connection.heard = []  # type: ignore[attr-defined]
        connection.marks = []  # type: ignore[attr-defined]
        connection.handle = lambda params: connection.heard.append(  # type: ignore[assignment,attr-defined]
            "<gap>" if params["continuity_gap"] else (params["event"].get("text"), params["event"].get("thread_root_event_id"))
        )
        connection.interrupted = lambda: connection.marks.append(time.monotonic())  # type: ignore[assignment,attr-defined]
        open_stream = client.open_stream

        def tracked():
            stream = open_stream()
            self.streams.append(stream)
            return stream

        client.open_stream = tracked  # type: ignore[method-assign]
        self.clients.append(client)
        return connection

    def serve(self, connection: DiscordRoomConnection) -> threading.Event:
        stop = threading.Event()
        self.stops.append(stop)
        threading.Thread(target=lambda: connection.serve(stop=stop), daemon=True).start()
        return stop

    def close_streams(self) -> None:
        """End every runner and every stream, so the transport has nothing left to wait for when it stops."""

        for stop in self.stops:
            stop.set()
        for stream in self.streams:
            _kill(stream)

    def stop(self) -> None:
        self.close_streams()
        if self.process.poll() is None:
            for how, wait in ((signal.SIGINT, 3), (signal.SIGINT, 8), (signal.SIGKILL, 5)):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, how)
                try:
                    self.process.wait(wait)
                    break
                except subprocess.TimeoutExpired:
                    continue


@SDK
class ConnectRaceTests(unittest.TestCase):
    """A client that registers before its stream is open (the order the runner used) loses nothing silently."""

    def test_serving_in_the_clients_rule_order_a_message_posted_the_instant_registration_returns_arrives(self):
        transport = RealTransport(self)
        lost = []
        for index in range(8):
            connection = transport.connection()
            register = connection.register
            text = f"posted the instant registration returned #{index}"

            def posting(register=register, text=text):
                register()
                transport.fd.post("zoe", "room", text)

            connection.register = posting
            stop = transport.serve(connection)
            if not _wait(lambda: any(isinstance(item, tuple) and item[0] == text for item in connection.heard), 5):
                lost.append(text)
            stop.set()
        self.assertEqual([], lost, "every message reached the runner")

    def test_a_client_that_registers_first_is_told_what_it_missed_not_silently_dropped(self):
        """Another client's order, or an older runner's: the notification cannot be sent, and the transport says so."""
        transport = RealTransport(self)
        connection = transport.connection()
        client = connection.client
        client.connect()
        connection.register()  # registered; its stream is not open yet
        before = transport.fd.post("zoe", "room", "sent while the client had no stream")
        self.assertTrue(_wait(lambda: "client-delivery-lost" in transport.outcomes()), transport.outcomes())
        self.assertNotIn("client-delivered", transport.outcomes(), "it was not journaled as delivered")
        stream = client.open_stream()
        transport.streams.append(stream)
        transport.fd.post("zoe", "room", "sent once the stream is open")
        heard: list[dict] = []
        _read(client, stream, heard)
        self.assertTrue(_wait(lambda: len(heard) >= 2), heard)
        self.assertEqual([True, False], [item["continuity_gap"] for item in heard[:2]], "the client learns that something was missed")
        self.assertEqual("sent once the stream is open", heard[1]["event"]["text"])
        self.assertNotEqual(before["id"], heard[1]["event"]["id"].removeprefix("discord:message:"))


@SDK
class StreamDeathTests(unittest.TestCase):
    """A runner's stream dies while its session stays registered."""

    def test_messages_for_a_dead_stream_are_not_journaled_as_delivered_and_the_next_listener_is_told(self):
        transport = RealTransport(self)
        runner = transport.connection()
        client = runner.client
        # The runner's steps, by hand, so the test holds its stream.
        client.connect()
        stream = client.open_stream()
        runner.register()
        heard: list[dict] = []
        _read(client, stream, heard)
        transport.fd.post("zoe", "room", "heard")
        self.assertTrue(_wait(lambda: len(heard) >= 2), heard)
        self.assertEqual([True, False], [item["continuity_gap"] for item in heard[:2]])
        delivered = transport.outcomes().count("client-delivered")
        lost = transport.outcomes().count("client-delivery-lost")
        # The stream dies: the runner's connection is gone, but its session is still registered.
        _kill(stream)
        self.assertTrue(
            _wait(lambda: transport.outcomes().count("client-delivery-lost") > lost), "the transport noticed the stream end"
        )
        lost = transport.outcomes().count("client-delivery-lost")
        transport.fd.post("zoe", "room", "while the runner is gone")
        # The gap that would have told it, and the message behind the gap, both fail to arrive; neither reads as delivered.
        self.assertTrue(_wait(lambda: transport.outcomes().count("client-delivery-lost") >= lost + 2, 10), transport.outcomes())
        self.assertEqual(delivered, transport.outcomes().count("client-delivered"), "nothing was journaled as delivered to a dead stream")
        self.assertEqual(2, len(heard), "and nothing reached the dead stream's client")
        # A new listener is told that it missed something, then hears what comes next.
        second = transport.connection()
        transport.serve(second)
        self.assertTrue(_wait(lambda: second.marks), "the new runner is listening")
        time.sleep(0.3)
        transport.fd.post("zoe", "room", "back")
        self.assertTrue(_wait(lambda: len(second.heard) >= 2), second.heard)
        self.assertEqual(["<gap>", ("back", None)], second.heard[:2])


@SDK
class SdkDropTests(unittest.TestCase):
    """What the MCP SDK does with a notification sent while the session has no notification stream.

    Pinned, because the transport's guard (`AuthenticatedSessionRegistry.stream_is_open`) exists for it. If a
    future SDK keeps such a notification, this fails, and the guard can go.
    """

    def test_the_sdk_drops_a_notification_sent_before_the_stream_is_open_without_an_error(self):
        import uvicorn
        from mcp import types
        from mcp.server.lowlevel import Server
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.routing import Mount

        from nunchi.mcp_discord._binding import _VendorNotification

        server = Server("pin")

        @server.list_tools()
        async def list_tools():
            return [types.Tool(name="push", description="push", inputSchema={"type": "object", "properties": {"n": {"type": "integer"}}})]

        @server.call_tool()
        async def call_tool(name, arguments):
            session = server.request_context.session
            await session.send_notification(_VendorNotification(method="notifications/pin", params={"n": arguments["n"]}))
            return [types.TextContent(type="text", text="sent")]

        manager = StreamableHTTPSessionManager(app=server, event_store=None)

        import contextlib as _contextlib

        @_contextlib.asynccontextmanager
        async def lifespan(_app):
            async with manager.run():
                yield

        app = Starlette(routes=[Mount("/mcp", app=manager.handle_request)], lifespan=lifespan)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
        http = uvicorn.Server(config)
        thread = threading.Thread(target=http.run, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(setattr, http, "should_exit", True)
        self.assertTrue(_wait(lambda: http.started), "uvicorn did not start")
        port = http.servers[0].sockets[0].getsockname()[1]
        client = StreamableMCPClient(f"http://127.0.0.1:{port}/mcp", timeout_seconds=15)
        client.connect()
        client.call_tool("push", {"n": 1})  # no stream is open: no error, and nothing is kept
        stream = client.open_stream()
        self.addCleanup(_kill, stream)
        client.call_tool("push", {"n": 2})
        heard: list[dict] = []
        _read(client, stream, heard)
        self.assertTrue(_wait(lambda: heard), "the notification sent with the stream open arrives")
        time.sleep(0.3)
        self.assertEqual([2], [item["n"] for item in heard], "the one sent before the stream was open is gone")


class StreamLedgerTests(unittest.TestCase):
    """The registry knows whether a notification sent now would reach anyone."""

    def test_a_session_registered_without_a_stream_id_counts_as_open(self):
        registry = AuthenticatedSessionRegistry()
        session = object()
        registry.bind(session, participant_id="vigil", room_id="42", transport_self_actor_id="discord:actor:9")
        self.assertTrue(registry.stream_is_open(session))

    def test_a_stream_is_open_between_its_request_and_its_end(self):
        registry = AuthenticatedSessionRegistry()
        session = object()
        registry.bind(session, participant_id="vigil", room_id="42", transport_self_actor_id="discord:actor:9", stream_id="s1")
        self.assertFalse(registry.stream_is_open(session), "registered, stream not open yet")
        registry.stream_opened("s1")
        self.assertTrue(registry.stream_is_open(session))
        self.assertEqual([("vigil", "42")], registry.stream_closed("s1"))
        self.assertFalse(registry.stream_is_open(session))

    def test_a_second_request_for_the_stream_does_not_end_it_and_a_replaced_registration_has_no_route_to_mark(self):
        registry = AuthenticatedSessionRegistry()
        old, new = object(), object()
        registry.bind(old, participant_id="vigil", room_id="42", transport_self_actor_id="discord:actor:9", stream_id="s1")
        registry.stream_opened("s1")
        registry.stream_opened("s1")  # the SDK refuses a second one; the request still ends
        self.assertEqual([], registry.stream_closed("s1"))
        self.assertTrue(registry.stream_is_open(old))
        # The runner reconnected: a new session took the route. The old stream ending marks nothing.
        registry.bind(new, participant_id="vigil", room_id="42", transport_self_actor_id="discord:actor:9", stream_id="s2")
        self.assertEqual([], registry.stream_closed("s1"))

    def test_a_notification_for_a_session_without_a_stream_is_a_failed_delivery_not_a_delivered_one(self):
        async def run() -> tuple[bool, bool]:
            registry = AuthenticatedSessionRegistry()
            session = _Session()
            registry.bind(session, participant_id="vigil", room_id="42", transport_self_actor_id="discord:actor:9", stream_id="s1")
            params = {"target_participant_id": "vigil", "room_id": "42", "transport_self_actor_id": "discord:actor:9"}
            closed = await deliver_targeted(registry, params, _Notification(params))
            registry.stream_opened("s1")
            opened = await deliver_targeted(registry, params, _Notification(params))
            return closed, opened

        self.assertEqual((False, True), asyncio.run(run()))


@SDK
class HiddenRequestTests(unittest.TestCase):
    """An SDK that gives a tool call no HTTP request cannot place a session's stream: it says so, loudly, once."""

    def test_the_session_id_comes_from_the_request_the_sdk_hands_the_call(self):
        from types import SimpleNamespace

        from nunchi.mcp_discord import _binding

        request = SimpleNamespace(headers={"mcp-session-id": "s1"})
        self.assertEqual("s1", _binding._stream_id(SimpleNamespace(request_context=SimpleNamespace(request=request))))

    def test_a_context_without_a_request_logs_one_error_and_no_session_id(self):
        from types import SimpleNamespace

        from nunchi.mcp_discord import _binding

        # mcp before 1.10: the context has no `request`.
        server = SimpleNamespace(request_context=SimpleNamespace(session=object()))
        previous, _binding._request_hidden = _binding._request_hidden, False
        self.addCleanup(setattr, _binding, "_request_hidden", previous)
        with self.assertLogs("nunchi.mcp_discord.binding", level="ERROR") as logged:
            self.assertIsNone(_binding._stream_id(server))
            self.assertIsNone(_binding._stream_id(server))
        self.assertEqual(1, len(logged.records), "once, not on every call")
        self.assertIn("mcp>=1.10", logged.output[0])


if __name__ == "__main__":
    unittest.main()
