"""nunchi-mcp-discord console entry point and transport plumbing.

Standing MCP transport server for one Discord bot account:

    NUNCHI_DISCORD_TOKEN=... nunchi-mcp-discord

Requires the mcp SDK (opt-in only):

    pip install nunchi[mcp-discord]

The server listens on http://HOST:PORT/mcp (streamable HTTP). Inbound Discord
messages, reactions, and membership events, including exact self events, are
pushed as the closed ``notifications/nunchi/v2/discord-event`` shape. Output
and history tools require one-use host authorization bound to the exact room
and operation.

This module holds the import-safe plumbing (bounded queue, notification
pump, in-flight tracking for drain-on-shutdown); everything that touches the
mcp SDK lives in :mod:`._binding` and is imported lazily by :func:`main`.

Backpressure: the notification queue is bounded
(NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE, default 256). A delivery that arrives while
the queue is full is explicitly rejected and audited in logs; an already
accepted older event is never silently erased to make room.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Awaitable, Callable
from uuid import uuid4

from .config import Config, load_config
from .hygiene import install_redaction

logger = logging.getLogger("nunchi.mcp_discord.server")

_PUMP_POLL_SECONDS = 0.25


class TransportAuditJournal:
    """Durable transport admission audit with no room content."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, *, outcome: str, event: dict) -> None:
        payload = (
            json.dumps(
                {
                    "schema_version": 2,
                    "outcome": outcome,
                    "delivery_id": str(event.get("delivery_id") or "unknown"),
                    "room_id": str(event.get("room_id") or "unknown"),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError("short Discord transport-audit write")
            os.fsync(fd)
        finally:
            os.close(fd)


class GapAwareEnqueuer:
    """Declare a continuity gap before the next accepted event for that room."""

    def __init__(self, queue: asyncio.Queue, audit: TransportAuditJournal) -> None:
        self.queue = queue
        self.audit = audit
        self._pending_rooms: set[str] = set()

    def __call__(self, event: dict) -> bool:
        room_id = str(event.get("room_id") or "unknown")
        if room_id in self._pending_rooms:
            gap = {
                "schema_version": 2,
                "delivery_id": f"discord:transport-gap:{uuid4()}",
                "room_id": room_id,
                "event": None,
                "actors": {},
                "continuity_gap": True,
            }
            if self.queue.full():
                return False
            self.audit.append(outcome="gap-signal", event=gap)
            self.queue.put_nowait(gap)
            self._pending_rooms.remove(room_id)
        if self.queue.full():
            self.audit.append(outcome="queue-rejected", event=event)
            self._pending_rooms.add(room_id)
            logger.error(
                "notification queue full (maxsize=%d); rejected delivery %s "
                "from room %s; a continuity-gap signal is pending",
                self.queue.maxsize,
                event.get("delivery_id", "unknown"),
                room_id,
            )
            return False
        self.audit.append(outcome="accepted", event=event)
        self.queue.put_nowait(event)
        return True

    def declare_delivery_gap(self, event: dict) -> None:
        room_id = str(event.get("room_id") or "unknown")
        self.audit.append(outcome="client-delivery-lost", event=event)
        self._pending_rooms.add(room_id)


class InFlight:
    """Counts in-flight sends so shutdown can drain them. Event-loop only."""

    def __init__(self) -> None:
        self._count = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @contextlib.contextmanager
    def track(self):
        self._count += 1
        self._idle.clear()
        try:
            yield
        finally:
            self._count -= 1
            if self._count == 0:
                self._idle.set()

    @property
    def count(self) -> int:
        return self._count

    async def wait_idle(self, timeout: float) -> bool:
        """True once nothing is in flight; False if *timeout* elapsed first."""
        try:
            await asyncio.wait_for(self._idle.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


async def pump_notifications(
    queue: asyncio.Queue,
    send: Callable[[dict], Awaitable[Any]],
    *,
    shutdown: asyncio.Event,
    on_delivery_gap: Callable[[dict], None] | None = None,
) -> None:
    """Drain the queue into *send* (broadcast to MCP sessions) until shutdown.

    A failing send declares a continuity gap for the room before pumping
    continues.
    """
    while not shutdown.is_set():
        try:
            event = await asyncio.wait_for(queue.get(), timeout=_PUMP_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue
        try:
            delivered = await send(event)
            if delivered is False and on_delivery_gap is not None:
                on_delivery_gap(event)
        except Exception as exc:  # noqa: BLE001 — transport must outlive one client
            logger.warning("notification delivery failed (client gone?): %s", exc)
            if on_delivery_gap is not None:
                on_delivery_gap(event)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nunchi-mcp-discord`` console script."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        print(
            "nunchi-mcp-discord: the mcp SDK is not installed.\n"
            "Install it with: pip install nunchi[mcp-discord]",
            file=sys.stderr,
        )
        return 1

    import argparse

    parser = argparse.ArgumentParser(
        prog="nunchi-mcp-discord",
        description=(
            "Standing MCP transport server for one Discord bot account. "
            "Reads NUNCHI_DISCORD_TOKEN from env; serves streamable HTTP MCP "
            "on NUNCHI_MCP_DISCORD_HOST:NUNCHI_MCP_DISCORD_PORT (/mcp). "
            "Transport only — no gate logic."
        ),
    )
    parser.parse_args(argv if argv is not None else sys.argv[1:])

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        config: Config = load_config(os.environ)
    except RuntimeError as exc:
        print(f"nunchi-mcp-discord: configuration error: {exc}", file=sys.stderr)
        return 1

    install_redaction(config.token)

    from . import _binding

    return _binding.serve(config)
