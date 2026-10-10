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

Gaps: when a route may have missed something, the next event for it is queued
behind a continuity-gap notification, so the participant learns that something
may be missing and still hears the event. An event is rejected only when the
queue has no slot left, and never overtakes a gap whose delivery failed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import contextlib
import json
import logging
import os
from pathlib import Path
import sys
import threading
from typing import Any, Awaitable, Callable
from uuid import uuid4

from ..private_process import keep_private
from .config import Config, load_config
from .hygiene import install_redaction

logger = logging.getLogger("nunchi.mcp_discord.server")

_PUMP_POLL_SECONDS = 0.25


class AuthenticatedSessionRegistry:
    """One live session per authenticated participant/room route.

    Event-loop only. Beside the session it keeps what the participant said at
    registration: whether threads under the room are part of it, and the id of
    the session's notification stream, so the transport knows whether a
    notification sent now would reach anyone.
    """

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], tuple[object, str]] = {}
        self._threads: dict[tuple[str, str], bool] = {}
        self._stream_ids: dict[tuple[str, str], str | None] = {}
        self._open_streams: dict[str, int] = {}

    def bind(
        self,
        session: object,
        *,
        participant_id: str,
        room_id: str,
        transport_self_actor_id: str,
        threads_in_room: bool = True,
        stream_id: str | None = None,
    ) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (participant_id, room_id, transport_self_actor_id)
        ):
            raise ValueError("authenticated session route must be exact")
        if not isinstance(threads_in_room, bool):
            raise ValueError("threads_in_room must be true or false")
        for route, (existing, _) in list(self._sessions.items()):
            if existing is session:
                self._forget(route)
        route = (participant_id, room_id)
        self._sessions[route] = (session, transport_self_actor_id)
        self._threads[route] = threads_in_room
        self._stream_ids[route] = stream_id

    def _forget(self, route: tuple[str, str]) -> None:
        self._sessions.pop(route, None)
        self._threads.pop(route, None)
        self._stream_ids.pop(route, None)

    def discard(self, session: object) -> None:
        for route, (existing, _) in list(self._sessions.items()):
            if existing is session:
                self._forget(route)

    def route(self, session: object) -> tuple[str, str] | None:
        for route, (existing, _) in self._sessions.items():
            if existing is session:
                return route
        return None

    def session_for(
        self,
        participant_id: str,
        room_id: str,
    ) -> tuple[object, str] | None:
        return self._sessions.get((participant_id, room_id))

    def threads_in_room(self, participant_id: str, room_id: str) -> bool:
        """What the route's participant said about threads; True (the default) until it registers."""

        return self._threads.get((participant_id, room_id), True)

    def threads_wanted(self, routes: Mapping[str, frozenset[str]]) -> bool:
        """Whether any of the configured routes wants threads in its room."""

        return any(
            self.threads_in_room(participant, room)
            for participant, rooms in routes.items()
            for room in rooms
        )

    # -- the notification streams ---------------------------------------------------

    def stream_opened(self, stream_id: str) -> None:
        self._open_streams[stream_id] = self._open_streams.get(stream_id, 0) + 1

    def stream_closed(self, stream_id: str) -> list[tuple[str, str]]:
        """A stream ended; the routes still registered on it, whose last notifications may be lost."""

        count = self._open_streams.get(stream_id, 0) - 1
        if count > 0:
            self._open_streams[stream_id] = count
            return []  # another request still holds the session's stream
        self._open_streams.pop(stream_id, None)
        return [
            route
            for route, bound in self._stream_ids.items()
            if bound == stream_id and route in self._sessions
        ]

    def stream_is_open(self, session: object) -> bool:
        """Whether a notification sent to *session* now would reach a client.

        The MCP SDK drops, without an error, a notification sent while the
        session's notification stream is not open. A session registered
        without a stream id (nothing tracks its stream) counts as open.
        """

        route = self.route(session)
        stream_id = self._stream_ids.get(route) if route is not None else None
        return stream_id is None or self._open_streams.get(stream_id, 0) > 0


async def deliver_targeted(
    registry: AuthenticatedSessionRegistry,
    params: dict,
    notification: object,
) -> bool:
    """Deliver only to the exact authenticated route in *params*."""
    participant_id = params.get("target_participant_id")
    room_id = params.get("room_id")
    self_actor = params.get("transport_self_actor_id")
    if any(
        not isinstance(value, str) or not value
        for value in (participant_id, room_id, self_actor)
    ):
        raise ValueError("targeted Discord notification lacks route identity")
    registered = registry.session_for(participant_id, room_id)
    if registered is None:
        return False
    session, registered_self = registered
    if registered_self != self_actor:
        registry.discard(session)
        return False
    if not registry.stream_is_open(session):
        # Sent now, the SDK would drop it and this would read as delivered.
        return False
    try:
        await session.send_notification(notification)  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001 — a dead client becomes a durable gap
        registry.discard(session)
        return False


class TransportAuditJournal:
    """Closed, durable per-participant delivery audit with no room content."""

    OUTCOMES = frozenset(
        {
            "accepted",
            "client-delivered",
            "queue-rejected",
            "client-delivery-lost",
            "shutdown-lost",
            "source-gap",
            "gap-signal",
            "gap-delivered",
        }
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._pending_routes: set[tuple[str, str]] = set()
        self._outstanding: set[tuple[str, str, str]] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if (
                        not isinstance(record, dict)
                        or set(record)
                        != {
                            "schema_version",
                            "outcome",
                            "delivery_id",
                            "room_id",
                            "participant_id",
                        }
                        or record["schema_version"] != 2
                        or record["outcome"] not in self.OUTCOMES
                        or any(
                            not isinstance(record[name], str) or not record[name]
                            for name in ("delivery_id", "room_id", "participant_id")
                        )
                    ):
                        raise ValueError(f"invalid record at line {line_number}")
                    self._apply(record)
            self._pending_routes.update(
                (participant_id, room_id)
                for participant_id, room_id, _ in self._outstanding
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Discord transport delivery journal is untrustworthy: {exc}"
            ) from exc

    def _apply(self, record: Mapping[str, Any]) -> None:
        route = (record["participant_id"], record["room_id"])
        delivery = (*route, record["delivery_id"])
        outcome = record["outcome"]
        if outcome == "accepted":
            self._outstanding.add(delivery)
        elif outcome == "client-delivered":
            self._outstanding.discard(delivery)
        elif outcome in {
            "queue-rejected",
            "client-delivery-lost",
            "shutdown-lost",
            "source-gap",
            "gap-signal",
        }:
            self._pending_routes.add(route)
            self._outstanding.discard(delivery)
        elif outcome == "gap-delivered":
            self._pending_routes.discard(route)

    def append(self, *, outcome: str, event: dict) -> None:
        if outcome not in self.OUTCOMES:
            raise ValueError("unsupported Discord transport audit outcome")
        participant_id = event.get("target_participant_id")
        room_id = event.get("room_id")
        delivery_id = event.get("delivery_id")
        if any(
            not isinstance(value, str) or not value
            for value in (participant_id, room_id, delivery_id)
        ):
            raise ValueError("Discord transport audit event lacks exact route identity")
        record = {
            "schema_version": 2,
            "outcome": outcome,
            "delivery_id": delivery_id,
            "room_id": room_id,
            "participant_id": participant_id,
        }
        payload = (
            json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        with self._lock:
            existed = self.path.exists()
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                if os.write(fd, payload) != len(payload):
                    raise OSError("short Discord transport-audit write")
                os.fsync(fd)
            finally:
                os.close(fd)
            if not existed:
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            self._apply(record)

    @property
    def pending_routes(self) -> set[tuple[str, str]]:
        with self._lock:
            return set(self._pending_routes)


class GapAwareEnqueuer:
    """Target every route and require a delivered gap before later facts.

    A route that may have missed something (queue rejection, a delivery lost,
    a source gap, a stream that ended) is *pending*. The next event for it
    queues a continuity gap first, then the event behind it when the queue has
    room: the gap says "something before this may be missing", not "this event
    is lost". Only when no slot is left is the event rejected. An event queued
    behind a gap must not overtake it if the gap's delivery fails
    (:meth:`behind_a_failed_gap`).
    """

    def __init__(
        self,
        queue: asyncio.Queue,
        audit: TransportAuditJournal,
        participant_routes: Mapping[str, frozenset[str]],
        *,
        wants_threads: Callable[[str, str], bool] | None = None,
    ) -> None:
        self.queue = queue
        self.audit = audit
        self._routes = {
            participant: frozenset(rooms)
            for participant, rooms in participant_routes.items()
        }
        if not self._routes:
            raise ValueError("Discord enqueuer requires exact participant routes")
        self._pending_routes = audit.pending_routes
        self._gap_enqueued: set[tuple[str, str]] = set()
        # Routes whose queued gap failed to reach the client.
        self._failed_gaps: set[tuple[str, str]] = set()
        # Whether a participant's room includes its threads (its registration says).
        self._wants_threads = wants_threads

    def __call__(self, event: dict, *, in_thread: bool = False) -> bool:
        """Queue *event* for every participant of its room; True when all accepted it.

        ``in_thread`` says the event happened in a thread under the room: a
        participant whose room does not include threads is skipped, as the
        event is not part of its room.
        """

        room_id = event.get("room_id")
        self_actor = event.get("transport_self_actor_id")
        if not isinstance(room_id, str) or not room_id:
            raise ValueError("Discord notification lacks room identity")
        if not isinstance(self_actor, str) or not self_actor:
            raise ValueError("Discord notification lacks authenticated self identity")
        targets = [
            participant
            for participant, rooms in self._routes.items()
            if room_id in rooms
        ]
        if not targets:
            raise ValueError("Discord event has no configured participant route")
        accepted_all = True
        for participant_id in targets:
            if (
                in_thread
                and self._wants_threads is not None
                and not self._wants_threads(participant_id, room_id)
            ):
                continue
            targeted = {**event, "target_participant_id": participant_id}
            route = (participant_id, room_id)
            if route in self._pending_routes:
                if route not in self._gap_enqueued:
                    if self.queue.full():
                        # Not even the gap fits; the route stays pending.
                        self.audit.append(outcome="queue-rejected", event=targeted)
                        accepted_all = False
                        continue
                    gap = {
                        "schema_version": 2,
                        "delivery_id": f"discord:transport-gap:{uuid4()}",
                        "room_id": room_id,
                        "event": None,
                        "actors": {},
                        "continuity_gap": True,
                        "transport_self_actor_id": self_actor,
                        "target_participant_id": participant_id,
                    }
                    self.audit.append(outcome="gap-signal", event=gap)
                    self.queue.put_nowait(gap)
                    self._gap_enqueued.add(route)
                if self.queue.full():
                    # The gap is queued, and a gap delivered later covers this
                    # event too: whoever reads history after it sees the event.
                    self.audit.append(outcome="queue-rejected", event=targeted)
                    accepted_all = False
                    continue
            elif self.queue.full():
                self.audit.append(outcome="queue-rejected", event=targeted)
                self._pending_routes.add(route)
                accepted_all = False
                logger.error(
                    "notification queue full (maxsize=%d); rejected a routed "
                    "Discord delivery; a continuity-gap signal is pending",
                    self.queue.maxsize,
                )
                continue
            self.audit.append(outcome="accepted", event=targeted)
            self.queue.put_nowait(targeted)
        return accepted_all

    def record_delivery(self, event: dict) -> None:
        route = (event["target_participant_id"], event["room_id"])
        if event.get("continuity_gap") is True:
            self.audit.append(outcome="gap-delivered", event=event)
            self._pending_routes.discard(route)
            self._gap_enqueued.discard(route)
            self._failed_gaps.discard(route)
        else:
            self.audit.append(outcome="client-delivered", event=event)

    def behind_a_failed_gap(self, event: dict) -> bool:
        """Whether *event* is queued behind a gap whose delivery failed.

        Delivering it would let it overtake the gap: the participant would hear
        it with no sign that something before it is missing. The pump treats it
        as lost instead, and the next event for the route queues a fresh gap.
        """

        route = (event["target_participant_id"], event["room_id"])
        return event.get("continuity_gap") is not True and route in self._failed_gaps

    def declare_delivery_gap(self, event: dict) -> None:
        self.audit.append(outcome="client-delivery-lost", event=event)
        route = (event["target_participant_id"], event["room_id"])
        self._pending_routes.add(route)
        if event.get("continuity_gap") is True:
            self._gap_enqueued.discard(route)
            self._failed_gaps.add(route)

    def declare_stream_gap(self, participant_id: str, room_id: str) -> None:
        """A route's notification stream ended: what was sent to it last may be lost."""

        event = {
            "delivery_id": f"discord:stream-gap:{uuid4()}",
            "room_id": room_id,
            "target_participant_id": participant_id,
        }
        self.audit.append(outcome="client-delivery-lost", event=event)
        route = (participant_id, room_id)
        self._pending_routes.add(route)
        self._gap_enqueued.discard(route)

    def declare_shutdown_gap(self, event: dict) -> None:
        self.audit.append(outcome="shutdown-lost", event=event)
        route = (event["target_participant_id"], event["room_id"])
        self._pending_routes.add(route)
        self._gap_enqueued.discard(route)

    def declare_source_gap(self) -> None:
        """Persist uncertainty for every configured participant/room route.

        A route that is already pending, with no gap queued for it yet, is
        covered: the gap its next event brings says it too. So a source that
        keeps failing (Discord's REST API down) leaves one record and one gap,
        not one per message.
        """
        gap_id = f"discord:gateway-source-gap:{uuid4()}"
        for participant_id, rooms in self._routes.items():
            for room_id in rooms:
                route = (participant_id, room_id)
                if route in self._pending_routes and route not in self._gap_enqueued:
                    continue
                event = {
                    "delivery_id": gap_id,
                    "room_id": room_id,
                    "target_participant_id": participant_id,
                }
                self.audit.append(outcome="source-gap", event=event)
                self._pending_routes.add(route)
                self._gap_enqueued.discard(route)


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
    on_delivery_success: Callable[[dict], None] | None = None,
    hold: Callable[[dict], bool] | None = None,
) -> None:
    """Drain the queue into *send* (broadcast to MCP sessions) until shutdown.

    A failing send declares a continuity gap for the room before pumping
    continues. An event for which *hold* answers True is not sent: it counts as
    a failed delivery (it sat behind a gap that did not arrive).
    """
    while not shutdown.is_set() or not queue.empty():
        try:
            event = await asyncio.wait_for(queue.get(), timeout=_PUMP_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue
        try:
            delivered = False if hold is not None and hold(event) else await send(event)
            if delivered is False and on_delivery_gap is not None:
                on_delivery_gap(event)
            elif delivered is not False and on_delivery_success is not None:
                on_delivery_success(event)
        except Exception as exc:  # noqa: BLE001 — transport must outlive one client
            logger.warning("notification delivery failed (client gone?): %s", exc)
            if on_delivery_gap is not None:
                on_delivery_gap(event)
        finally:
            queue.task_done()


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nunchi-mcp-discord`` console script."""
    # First, before the bot token and the output key are read: an agent of
    # this OS user must not read them out of this process.
    keep_private()
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
    except (RuntimeError, ValueError) as exc:
        print(f"nunchi-mcp-discord: configuration error: {exc}", file=sys.stderr)
        return 1

    install_redaction(config.token)

    from . import _binding

    return _binding.serve(config)
