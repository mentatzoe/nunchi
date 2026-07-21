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
import contextlib
import json
import logging
import signal

import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount

from .config import Config
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

logger = logging.getLogger("nunchi.mcp_discord.binding")


class _VendorNotification(BaseModel):
    """Duck-typed stand-in accepted by ServerSession.send_notification."""

    method: str
    params: dict


class SessionRegistry:
    """Live MCP sessions, registered lazily from request handlers."""

    def __init__(self) -> None:
        self._sessions: dict[int, object] = {}

    def add(self, session: object) -> None:
        if id(session) not in self._sessions:
            logger.info("MCP session registered (%d total)", len(self._sessions) + 1)
        self._sessions[id(session)] = session

    def discard(self, session: object) -> None:
        self._sessions.pop(id(session), None)

    def sessions(self) -> list:
        return list(self._sessions.values())


async def broadcast(
    registry: SessionRegistry,
    params: dict,
    *,
    method: str = V2_NOTIFICATION_METHOD,
    send_timeout: float = 5.0,
) -> None:
    """Push one event concurrently; evict clients that fail or stop reading."""
    notification = _VendorNotification(method=method, params=params)
    await broadcast_sessions(
        registry.sessions(),
        notification,
        discard=registry.discard,
        send_timeout=send_timeout,
    )


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
        registry.add(server.request_context.session)
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
        registry.add(server.request_context.session)
        with in_flight.track():
            payload, ok = await asyncio.to_thread(executor.call, name, arguments or {})
        if not ok:
            # The lowlevel server converts exceptions into isError tool results.
            raise RuntimeError(payload.get("error", "tool call failed"))
        return [types.TextContent(type="text", text=json.dumps(payload))]

    return server


def serve(config: Config) -> int:
    registry = SessionRegistry()
    in_flight = InFlight()
    backstop = SendBackstop(config.backstop_max_sends, config.backstop_window_seconds)
    rest = DiscordRestClient(config.token)
    executor = ToolExecutor(
        rest,
        backstop,
        allowed_channel_ids=config.channels,
    )
    server = build_server(
        executor,
        registry,
        in_flight,
        tool_schemas=TOOL_SCHEMAS,
    )
    session_manager = StreamableHTTPSessionManager(app=server, event_store=None)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        shutdown = asyncio.Event()
        queue: asyncio.Queue = asyncio.Queue(maxsize=config.queue_maxsize)
        source = DiscordEventSourceV2(
            allowed_channel_ids=config.channels,
            blocked_actor_ids=config.blocked_actors,
        )
        protocol = GatewayProtocol(config.token)

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
                ),
                shutdown=shutdown,
                projector=source.notification_params,
            ),
            name="notification-pump",
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
                for task in (gateway_task, pump_task):
                    task.cancel()
                await asyncio.gather(gateway_task, pump_task, return_exceptions=True)
                logger.info("transport shut down cleanly")

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
