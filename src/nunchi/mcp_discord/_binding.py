"""Thin binding to the official ``mcp`` SDK (the only SDK-bound module).

Importing this module requires ``pip install nunchi[mcp-discord]``. All
transport behavior (gateway, filtering, queueing, rate limits, tool
execution) lives in the import-safe sibling modules and is tested without
the SDK; this module only wires them to the SDK: tool registration, session
tracking, notification push, and the uvicorn/Starlette lifecycle.

Custom vendor notifications: the SDK's ServerNotification union is closed,
but ``ServerSession.send_notification`` serializes with ``model_dump()`` and
only needs ``method`` and ``params`` fields, so a duck-typed pydantic model
carries ``notifications/nunchi/v2/discord/event`` (delivered on the session's
standalone SSE stream since it has no related request).

Session tracking: the low-level Server exposes sessions only inside request
handlers. Standard MCP clients send ``tools/list`` right after ``initialize``,
which registers them here; notifications start after a client's first
request. Documented in integrations/mcp-discord/README.md.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import logging
import signal
from dataclasses import dataclass

import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.streamable_http import EventMessage, EventStore
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount

from .config import Config
from .continuation import DiscordHistoryContinuations
from .events import (
    DiscordEventSourceV2,
    V2_NOTIFICATION_METHOD,
)
from .gateway import GatewayProtocol
from .ratelimit import SendBackstop
from .rest import DiscordRestClient
from .runner import GatewayFatalError, GatewayRunner
from .server import (
    BearerAuthMiddleware,
    InFlight,
    broadcast_sessions,
    enqueue_event,
    pump_notifications,
)
from .tools import TOOL_SCHEMAS, ToolExecutor
from .state import ExclusiveRequestClaimStore

logger = logging.getLogger("nunchi.mcp_discord.binding")


class _VendorNotification(BaseModel):
    """Duck-typed stand-in accepted by ServerSession.send_notification."""

    method: str
    params: dict


class BoundedEventStore(EventStore):
    """Process-local replay for disconnected MCP SSE streams.

    Capacity exhaustion raises instead of evicting an unseen event and
    pretending continuity. Discord/gateway restart truth remains separately
    represented by explicit continuity-boundary notifications.
    """

    def __init__(self, max_events: int = 4096) -> None:
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
            raise ValueError("MCP replay store capacity is invalid")
        self._max_events = max_events
        self._counter = 0
        self._events: collections.OrderedDict[str, tuple[str, object | None]] = (
            collections.OrderedDict()
        )
        self._lock = asyncio.Lock()
        self._failed = asyncio.Event()
        self._failure: RuntimeError | None = None

    def raise_if_failed(self) -> None:
        if self._failure is not None:
            raise self._failure

    async def wait_failed(self) -> RuntimeError:
        await self._failed.wait()
        assert self._failure is not None
        return self._failure

    async def store_event(self, stream_id: str, message: object | None) -> str:
        async with self._lock:
            if len(self._events) >= self._max_events:
                if self._failure is None:
                    self._failure = RuntimeError(
                        "MCP replay store capacity is exhausted; continuity is lost"
                    )
                    self._failed.set()
                raise self._failure
            self._counter += 1
            event_id = f"nunchi-{self._counter}"
            self._events[event_id] = (stream_id, message)
            return event_id

    async def replay_events_after(self, last_event_id: str, send_callback) -> str | None:
        async with self._lock:
            if last_event_id not in self._events:
                return None
            stream_id = self._events[last_event_id][0]
            after = False
            replay = []
            for event_id, (candidate_stream, message) in self._events.items():
                if event_id == last_event_id:
                    after = True
                    continue
                if after and candidate_stream == stream_id and message is not None:
                    replay.append((event_id, message))
        for event_id, message in replay:
            await send_callback(EventMessage(message=message, event_id=event_id))
        return stream_id


@dataclass(frozen=True)
class SessionBinding:
    session: object
    participant_id: str
    room_id: str
    self_actor_id: str
    capabilities: frozenset[str]


class SessionRegistry:
    """Live MCP sessions bound to one process credential and exact room."""

    def __init__(
        self,
        *,
        participant_id: str,
        room_id: str,
        self_actor_id: str,
        capabilities: frozenset[str],
        on_restart_gap=None,
    ) -> None:
        self._participant_id = participant_id
        self._room_id = room_id
        self._self_actor_id = self_actor_id
        self._capabilities = capabilities
        self._sessions: dict[int, SessionBinding] = {}
        self._gateway_session_id: str | None = None
        self._gateway_sequence: int | None = None
        self._has_restart_gap = False
        self._on_restart_gap = on_restart_gap

    def add(self, session: object) -> dict:
        if id(session) not in self._sessions:
            logger.info("MCP session registered (%d total)", len(self._sessions) + 1)
        self._sessions[id(session)] = SessionBinding(
            session=session,
            participant_id=self._participant_id,
            room_id=self._room_id,
            self_actor_id=self._self_actor_id,
            capabilities=self._capabilities,
        )
        return {
            "participant_id": self._participant_id,
            "room_id": self._room_id,
            "self_actor_id": self._self_actor_id,
            "capabilities": sorted(self._capabilities),
            "gateway_session_id": self._gateway_session_id,
            "gateway_sequence": self._gateway_sequence,
            "has_restart_gap": self._has_restart_gap,
        }

    def contains(self, session: object) -> bool:
        return id(session) in self._sessions

    def discard(self, session: object) -> None:
        self._sessions.pop(id(session), None)

    def sessions(self, params: dict) -> list:
        channel_id = params.get("channel_id")
        if channel_id is not None and channel_id != self._room_id:
            raise RuntimeError("notification crossed the bound MCP room")
        if params.get("kind") == "continuity-boundary":
            self._has_restart_gap = True
            if self._on_restart_gap is not None:
                self._on_restart_gap()
            self._gateway_session_id = None
            self._gateway_sequence = None
        else:
            gateway_session_id = params.get("gateway_session_id")
            gateway_sequence = params.get("gateway_sequence")
            if gateway_session_id is not None and gateway_sequence is not None:
                self._gateway_session_id = gateway_session_id
                self._gateway_sequence = gateway_sequence
        return [binding.session for binding in self._sessions.values()]


async def broadcast(
    registry: SessionRegistry,
    params: dict,
    *,
    method: str = V2_NOTIFICATION_METHOD,
    send_timeout: float = 5.0,
    replay_store: BoundedEventStore | None = None,
) -> None:
    """Push one event concurrently; evict clients that fail or stop reading."""
    if replay_store is not None:
        replay_store.raise_if_failed()
    notification = _VendorNotification(method=method, params=params)
    await broadcast_sessions(
        registry.sessions(params),
        notification,
        discard=registry.discard,
        send_timeout=send_timeout,
    )
    # The pinned SDK routes store_event in a separate task and swallows that
    # task's exception. Yield once, then surface its durable health bit here;
    # the lifespan watcher below independently guarantees eventual shutdown.
    await asyncio.sleep(0)
    if replay_store is not None:
        replay_store.raise_if_failed()


def build_server(
    executor: ToolExecutor,
    registry: SessionRegistry,
    in_flight: InFlight,
    *,
    tool_schemas: list[dict] = TOOL_SCHEMAS,
) -> Server:
    server: Server = Server("nunchi-mcp-discord")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=schema["name"],
                description=schema["description"],
                inputSchema=schema["inputSchema"],
            )
            for schema in tool_schemas
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        session = server.request_context.session
        if name == "subscribe_events":
            if arguments:
                raise RuntimeError("subscribe_events takes no arguments")
            binding = registry.add(session)
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(None, executor.bootstrap_history)
            in_flight.track_future(future)
            history = await asyncio.shield(future)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {"subscription": binding, "history": history}
                    ),
                )
            ]
        if not registry.contains(session):
            raise RuntimeError(
                "MCP session must call subscribe_events after opening its SSE stream"
            )
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, executor.call, name, arguments or {})
        in_flight.track_future(future)
        payload, ok = await asyncio.shield(future)
        if not ok:
            # The lowlevel server converts exceptions into isError tool results.
            raise RuntimeError(payload.get("error", "tool call failed"))
        return [types.TextContent(type="text", text=json.dumps(payload))]

    return server


def serve(config: Config) -> int:
    in_flight = InFlight()
    backstop = SendBackstop(config.backstop_max_sends, config.backstop_window_seconds)
    rest = DiscordRestClient(config.token)
    claims = ExclusiveRequestClaimStore(config.state_directory)
    continuations = DiscordHistoryContinuations(
        config.auth_token,
        participant_id=config.participant_id,
        room_id=config.channel_id,
        continuity_scope_id=f"discord:channel:{config.channel_id}",
    )
    registry = SessionRegistry(
        participant_id=config.participant_id,
        room_id=config.channel_id,
        self_actor_id=config.self_actor_id,
        capabilities=frozenset(schema["name"] for schema in TOOL_SCHEMAS),
        on_restart_gap=continuations.mark_restart_gap,
    )
    executor = ToolExecutor(
        rest,
        backstop,
        allowed_channel_ids=config.channels,
        action_claim=claims.claim,
        continuations=continuations,
    )
    server = build_server(
        executor,
        registry,
        in_flight,
        tool_schemas=TOOL_SCHEMAS,
    )
    replay_store = BoundedEventStore(config.queue_maxsize * 16)
    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=replay_store,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        shutdown = asyncio.Event()
        queue: asyncio.Queue = asyncio.Queue(maxsize=config.queue_maxsize)
        source = DiscordEventSourceV2(
            allowed_channel_ids=config.channels,
            blocked_actor_ids=config.blocked_actors,
            continuation_issuer=continuations.issue,
        )
        protocol = GatewayProtocol(
            config.token,
            expected_user_id=config.self_actor_id,
        )

        def _enqueue_or_fail(event) -> None:
            if not enqueue_event(queue, event):
                raise GatewayFatalError(
                    "notification continuity lost to bounded-queue overflow"
                )

        runner = GatewayRunner(
            protocol,
            _enqueue_or_fail,
        )
        gateway_task = asyncio.create_task(runner.run(shutdown), name="discord-gateway")
        pump_task = asyncio.create_task(
            pump_notifications(
                queue,
                lambda params: broadcast(
                    registry,
                    params,
                    method=V2_NOTIFICATION_METHOD,
                    replay_store=replay_store,
                ),
                shutdown=shutdown,
                projector=source.notification_params,
            ),
            name="notification-pump",
        )
        replay_store_task = asyncio.create_task(
            replay_store.wait_failed(),
            name="mcp-replay-store-health",
        )

        def _on_gateway_done(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            exc = task.exception()
            if isinstance(exc, GatewayFatalError):
                logger.critical("%s — shutting down", exc)
                signal.raise_signal(signal.SIGTERM)  # let uvicorn drain gracefully
            elif exc is not None:
                logger.critical("gateway task died: %s — shutting down", exc)
                signal.raise_signal(signal.SIGTERM)

        gateway_task.add_done_callback(_on_gateway_done)

        def _on_pump_done(task: asyncio.Task) -> None:
            if task.cancelled() or shutdown.is_set():
                return
            exc = task.exception()
            if exc is None:
                logger.critical("notification pump stopped — shutting down")
            else:
                logger.critical(
                    "notification pump died: %s — shutting down",
                    exc,
                )
            signal.raise_signal(signal.SIGTERM)

        pump_task.add_done_callback(_on_pump_done)

        def _on_replay_store_done(task: asyncio.Task) -> None:
            if task.cancelled() or shutdown.is_set():
                return
            exc = task.result()
            logger.critical("%s — shutting down", exc)
            signal.raise_signal(signal.SIGTERM)

        replay_store_task.add_done_callback(_on_replay_store_done)

        async with session_manager.run():
            try:
                yield
            finally:
                # SIGTERM/SIGINT arrives here via uvicorn's graceful shutdown:
                # stop pumping, drain in-flight sends, close the gateway cleanly.
                shutdown.set()
                drained = await in_flight.wait_idle(config.drain_timeout_seconds)
                if not drained:
                    logger.warning(
                        "%d send(s) still in flight after %.0fs drain timeout",
                        in_flight.count, config.drain_timeout_seconds,
                    )
                for task in (gateway_task, pump_task, replay_store_task):
                    task.cancel()
                await asyncio.gather(
                    gateway_task,
                    pump_task,
                    replay_store_task,
                    return_exceptions=True,
                )
                logger.info("transport shut down cleanly")
                claims.close()

    app = Starlette(
        routes=[
            Mount(
                "/mcp",
                app=BearerAuthMiddleware(
                    session_manager.handle_request,
                    config.auth_token,
                ),
            )
        ],
        lifespan=lifespan,
    )

    logger.info(
        "nunchi-mcp-discord V2 listening on http://%s:%d/mcp",
        config.host,
        config.port,
    )
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
    return 0
