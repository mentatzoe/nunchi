"""The control API: the stand-in run on its own asyncio thread inside the caller's process, and what the probe or director may do to it.

The director posts as a person, or as a scripted bot that belongs to no
harness (a status report, say); never as a harness's bot, since every
visible move of an agent is its own. A bot is a harness's unless the world
says ``"harness": false``, and only a harness's bot has a token to hand
out, so the two never overlap. The director reads the room only from the
wire log (`wait_for`, `settle`), `state` and `verdict`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import itertools
import json
from pathlib import Path
import threading
from typing import Any, Callable

from . import payloads, shapes, wire
from .gateway import Hub
from .server import GATEWAY_HOST, REST_HOST, serve, tls_context
from .world import INTENTS, Member, World, id_ms, iso


class FakeDiscord:
    """Discord's REST API and gateway for one world, at ``host:port``.

    With ``tls=(certfile, keyfile)`` it answers as ``discord.com`` and
    ``gateway.discord.gg`` (PR 3b's launcher maps those names here); without,
    on plain loopback. With ``out``, it writes ``world.json`` on start, the
    wire log as it goes, and ``discord-standin.json`` (the verdict) on stop.
    """

    def __init__(self, world: World | dict[str, Any] | None = None, out: str | Path | None = None, *,
                 host: str = "127.0.0.1", port: int = 0, tls: tuple[str, str] | None = None) -> None:
        self.world = world if isinstance(world, World) else World(world)
        self.out = Path(out) if out is not None else None
        bots = [m for m in self.world.members.values() if m.bot]
        self.wire = wire.Wire(self.out / "discord-wire.jsonl" if self.out else None, {b.token: f"<bot:{b.name}>" for b in bots if b.token})
        self.world.log = self.wire.write
        self.hub = Hub(self)
        self.faults: list[dict[str, Any]] = []
        self.host, self.port, self.tls = host, port, tls
        self.rest_hosts = {REST_HOST} if tls else {REST_HOST, host}
        self.gateway_hosts = {GATEWAY_HOST} if tls else {GATEWAY_HOST, host}
        self._conns = itertools.count(1)
        self._tasks: set[asyncio.Task] = set()
        self._shapes_seen: set[tuple[str, tuple[str, ...]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.Server | None = None

    # -- lifecycle ----------------------------------------------------------------------------

    def start(self) -> FakeDiscord:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="fake-discord", daemon=True)
        self._thread.start()
        try:
            context = tls_context(*self.tls, self.wire) if self.tls else None
            self._server = self._run(asyncio.start_server(self._serve, self.host, self.port, ssl=context))
            self.port = self._server.sockets[0].getsockname()[1]
            if self.out is not None:
                world_file = {**self.world.describe(), "rest_url": self.rest_url, "gateway_url": self.gateway_url}
                (self.out / "world.json").write_text(json.dumps(world_file, indent=2) + "\n", encoding="utf-8")
        except BaseException:  # a port in use, say: leave no loop running behind the error
            self._shutdown()
            raise
        return self

    def stop(self) -> dict[str, Any]:
        """Close every connection and return the verdict (written to ``discord-standin.json`` with ``out``)."""
        if self._loop is None:
            return self.verdict()
        self._shutdown()
        result = self.verdict()
        if self.out is not None:
            (self.out / "discord-standin.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return result

    def _shutdown(self) -> None:
        """Close the server and every connection, then end the loop and its thread."""

        async def close() -> None:
            if self._server is not None:
                self._server.close()
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._run(close())
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._loop.close()
        self._loop = None

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        try:
            await serve(self, next(self._conns), reader, writer)
        finally:
            self._tasks.discard(task)

    def _run(self, coroutine: Any) -> Any:
        assert self._loop is not None, "the stand-in is not running"
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(10)

    def _on_loop(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        async def call() -> Any:
            return fn(*args, **kwargs)

        return self._run(call())

    @property
    def rest_url(self) -> str:
        return f"https://{REST_HOST}{self._port_suffix}/api/v10" if self.tls else f"http://{self.host}:{self.port}/api/v10"

    @property
    def gateway_url(self) -> str:
        """The first and the resume gateway URL (READY's ``resume_gateway_url``), so a resume stays here."""
        return f"wss://{GATEWAY_HOST}{self._port_suffix}" if self.tls else f"ws://{self.host}:{self.port}"

    @property
    def _port_suffix(self) -> str:
        return "" if self.port == 443 else f":{self.port}"

    def token(self, bot: str) -> str:
        """A harness's bot's per-run token, for the process that runs as it; never written to any output."""
        member = self.world.member(bot)
        if member.token is None:
            raise ValueError(f"{bot} is not a harness's bot: no process runs as a person or a scripted bot")
        return member.token

    def check_shape(self, kind: str, payload: Any) -> None:
        """Record, once each, a payload that lacks a key discord.py 2.7.1 requires (the shape pin)."""
        if kind not in payloads.SHAPES:
            return
        gaps = shapes.missing(payloads.SHAPES[kind], payload)
        if gaps and (kind, tuple(gaps)) not in self._shapes_seen:
            self._shapes_seen.add((kind, tuple(gaps)))
            self.wire.write("unknown", what="shape", payload=kind, missing=gaps)

    # -- what the probe or director does ---------------------------------------------------------

    def _director(self, name: str) -> Member:
        member = self.world.member(name)
        if member.harness:
            raise ValueError(f"{name} is a harness's bot: only its own process acts as it, since every visible move is the agent's own")
        return member

    def post(self, author: str, channel: str, content: str, reply_to: str | None = None, at: datetime | None = None) -> dict[str, Any]:
        """Post as a person or a scripted bot, at ``at`` (a scene time) or the room's time; returns {id, timestamp, dispatched_to}."""

        def run() -> dict[str, Any]:
            member, room = self._director(author), self.world.channel(channel)
            self.wire.write("control", call="post", author=author, channel=channel, content=content, reply_to=reply_to,
                            at=at.isoformat() if at else None)
            record, _ = self.world.create_message(member.id, room.id, content, reference={"message_id": reply_to} if reply_to else None, at=at)
            sent = self.hub.fan_out("MESSAGE_CREATE", payloads.message(self.world, record, gateway=True), room.id, INTENTS["GUILD_MESSAGES"])
            return {"id": record["id"], "timestamp": iso(id_ms(record["id"])), "dispatched_to": sent}

        return self._on_loop(run)

    def create_thread(self, person: str, channel: str, name: str, from_message: str | None = None) -> dict[str, Any]:
        """A public thread under ``channel``; THREAD_CREATE goes out before anything is posted in it."""

        def run() -> dict[str, Any]:
            member, parent = self._director(person), self.world.channel(channel)
            self.wire.write("control", call="create_thread", person=person, channel=channel, name=name, from_message=from_message)
            thread = self.world.create_thread(member.id, parent.id, name, from_message)
            data = {**payloads.channel(self.world, thread), "newly_created": True}
            return {"id": thread.id, "dispatched_to": self.hub.fan_out("THREAD_CREATE", data, thread.id, INTENTS["GUILDS"])}

        return self._on_loop(run)

    def gateway(self, bot: str, action: str, *, code: int = 4000, resumable: bool = False) -> int:
        """reconnect, invalid_session (``resumable`` or not), close (with ``code``) or drop the bot's connections; returns how many."""

        def run() -> int:
            self.wire.write("control", call="gateway", bot=bot, action=action, code=code, resumable=resumable)
            return self.hub.act(bot, action, code=code, resumable=resumable)

        return self._on_loop(run)

    def fault(self, method: str, path: str, status: int, count: int = 1, retry_after: float | None = None) -> None:
        """Answer the next ``count`` requests to ``path`` (a route template such as ``/channels/{channel}/messages``, or an exact path) with ``status``."""
        fault = {"method": method, "path": path, "status": status, "count": count, "retry_after": retry_after}

        def run() -> None:
            self.wire.write("control", call="fault", **fault)
            self.faults.append(fault)

        self._on_loop(run)

    def advance(self, channel: str, seconds: float) -> str:
        """Move a channel's clock forward (a pause in the scene); returns its time now."""

        def run() -> str:
            room = self.world.channel(channel)
            self.world.advance(room, seconds)
            self.wire.write("control", call="advance", channel=channel, seconds=seconds)
            return iso(self.world.room_ms(room))

        return self._on_loop(run)

    def wait_for(self, predicate: Callable[[dict[str, Any]], bool], timeout: float = 10.0, *, since: int = 0) -> dict[str, Any]:
        return self.wire.wait_for(predicate, timeout, since=since)

    def settle(self, quiet: float = 0.5, timeout: float = 10.0) -> bool:
        return self.wire.settle(quiet, timeout)

    def state(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            world = self.world
            return {
                "channels": {c.name: {"id": c.id, "room_time": iso(world.room_ms(c)), "lag": world.clock_of(c).lag, "messages": c.messages}
                             for c in world.channels.values()},
                "sessions": [{"bot": s.bot.name, "intents": s.intents, "seq": s.seq, "connected": s.connection is not None}
                             for s in self.hub.sessions.values()],
                "records": len(self.wire.records),
            }

        return self._on_loop(run)

    def verdict(self) -> dict[str, Any]:
        return wire.verdict(list(self.wire.records), [m.name for m in self.world.members.values() if m.bot])
