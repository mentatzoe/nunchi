"""Thin binding to the official ``mcp`` SDK (the only SDK-bound module).

Importing this module requires ``pip install nunchi[mcp-discord]``. All
transport behavior (gateway, filtering, queueing, rate limits, tool
execution) lives in the import-safe sibling modules and is tested without
the SDK; this module only wires them to the SDK: tool registration, session
tracking, notification push, and the uvicorn/Starlette lifecycle.

Custom vendor notifications: the SDK's ServerNotification union is closed,
but ``ServerSession.send_notification`` serializes with ``model_dump()`` and
only needs ``method`` and ``params`` fields, so a duck-typed pydantic model
carries ``notifications/discord/message`` (delivered on the session's
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
    NOTIFICATION_METHOD,
    V2_NOTIFICATION_METHOD,
    notification_params,
)
from .gateway import GatewayProtocol, V2_INTENTS
from .ratelimit import SendBackstop
from .rest import DiscordRestClient
from .runner import GatewayFatalError, GatewayRunner
from .server import InFlight, enqueue_event, pump_notifications
from .tools import TOOL_SCHEMAS, V2_TOOL_SCHEMAS, ToolExecutor

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
    method: str = NOTIFICATION_METHOD,
) -> None:
    """Push one discord/message notification to every live session."""
    notification = _VendorNotification(method=method, params=params)
    for session in registry.sessions():
        try:
            await session.send_notification(notification)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 — one dead client must not stop the rest
            logger.info("dropping MCP session after failed send: %s", exc)
            registry.discard(session)


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
        allowed_channel_ids=(config.channels if config.mode == "v2" else None),
    )
    server = build_server(
        executor,
        registry,
        in_flight,
        tool_schemas=(V2_TOOL_SCHEMAS if config.mode == "v2" else TOOL_SCHEMAS),
    )
    session_manager = StreamableHTTPSessionManager(app=server, event_store=None)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        shutdown = asyncio.Event()
        queue: asyncio.Queue = asyncio.Queue(maxsize=config.queue_maxsize)
        source = (
            DiscordEventSourceV2(
                allowed_channel_ids=config.channels,
                blocked_actor_ids=config.blocked_actors,
            )
            if config.mode == "v2"
            else None
        )
        protocol = (
            GatewayProtocol(config.token, intents=V2_INTENTS)
            if source is not None
            else GatewayProtocol(config.token)
        )
        runner = GatewayRunner(
            protocol,
            lambda event: enqueue_event(queue, event),
            retain_self=source is not None,
            v2_events=source is not None,
        )
        gateway_task = asyncio.create_task(runner.run(shutdown), name="discord-gateway")
        pump_task = asyncio.create_task(
            pump_notifications(
                queue,
                lambda params: broadcast(
                    registry,
                    params,
                    method=(V2_NOTIFICATION_METHOD if source is not None else NOTIFICATION_METHOD),
                ),
                shutdown=shutdown,
                projector=(source.notification_params if source is not None else notification_params),
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
        routes=[Mount("/mcp", app=session_manager.handle_request)],
        lifespan=lifespan,
    )

    logger.info(
        "nunchi-mcp-discord listening on http://%s:%d/mcp (mode=%s, transport only)",
        config.host, config.port, config.mode,
    )
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
    return 0
