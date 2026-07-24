"""Thin binding to the official ``mcp`` SDK (the only SDK-bound module).

Importing this module requires ``pip install nunchi[mcp-discord]``. All
transport behavior (gateway, filtering, queueing, rate limits, tool
execution) lives in the import-safe sibling modules and is tested without
the SDK; this module only wires them to the SDK: tool registration, session
tracking, notification push, and the uvicorn/Starlette lifecycle.

Custom vendor notifications: the SDK's ServerNotification union is closed,
but ``ServerSession.send_notification`` serializes with ``model_dump()`` and
only needs ``method`` and ``params`` fields, so a duck-typed pydantic model
carries ``notifications/nunchi/v2/discord-event`` (delivered on the session's
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
from pathlib import Path
import signal
from typing import Callable

import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount

from .config import Config
from .authorization import ToolAuthorizer
from .events import NOTIFICATION_METHOD
from .gateway import GatewayProtocol
from .ratelimit import SendBackstop
from .rest import DiscordRestClient
from .runner import GatewayFatalError, GatewayRunner
from .server import (
    AuthenticatedSessionRegistry,
    GapAwareEnqueuer,
    InFlight,
    TransportAuditJournal,
    deliver_targeted,
    pump_notifications,
)
from .tools import TOOL_SCHEMAS, ToolExecutor

logger = logging.getLogger("nunchi.mcp_discord.binding")


class _VendorNotification(BaseModel):
    """Duck-typed stand-in accepted by ServerSession.send_notification."""

    method: str
    params: dict


SessionRegistry = AuthenticatedSessionRegistry


async def broadcast(registry: SessionRegistry, params: dict) -> bool:
    """Push a targeted V2 Discord notification to its authenticated session."""
    notification = _VendorNotification(method=NOTIFICATION_METHOD, params=params)
    return await deliver_targeted(registry, params, notification)


def build_server(
    executor: ToolExecutor,
    registry: SessionRegistry,
    in_flight: InFlight,
    authorizer: ToolAuthorizer,
    self_actor_id: Callable[[], str | None],
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
            for schema in TOOL_SCHEMAS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        session = server.request_context.session
        supplied = arguments or {}
        if name == "register_participant":
            if not isinstance(supplied, dict):
                raise RuntimeError("registration arguments must be an object")
            unsigned = dict(supplied)
            authorization = unsigned.pop("_nunchi_authorization", None)
            actor_id = self_actor_id()
            if actor_id is None:
                raise RuntimeError("Discord transport self identity is not ready")
            participant_id = unsigned.get("participant_id")
            room_id = unsigned.get("channel_id")
            ok, detail = authorizer.verify(
                authorization=authorization,
                tool=name,
                arguments=unsigned,
                expected_participant_id=(
                    participant_id if isinstance(participant_id, str) else None
                ),
                expected_room_id=room_id if isinstance(room_id, str) else None,
            )
            if not ok:
                raise RuntimeError(detail)
            registry.bind(
                session,
                participant_id=participant_id,
                room_id=room_id,
                transport_self_actor_id=actor_id,
            )
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "registered": True,
                            "participant_id": participant_id,
                            "room_id": room_id,
                            "transport_self_actor_id": actor_id,
                        }
                    ),
                )
            ]
        route = registry.route(session)
        if route is None:
            raise RuntimeError("MCP session is not authenticated for a participant route")
        registered = registry.session_for(*route)
        if registered is None or registered[0] is not session:
            raise RuntimeError("MCP session route lost its authenticated self binding")
        with in_flight.track():
            payload, ok = await asyncio.to_thread(
                executor.call,
                name,
                supplied,
                expected_route=route,
                expected_self_actor_id=registered[1],
            )
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
    authorizer = ToolAuthorizer(
        secret=config.output_hmac_key,
        participant_routes={
            participant: frozenset(rooms)
            for participant, rooms in config.participant_routes
        },
        journal_path=Path(config.state_directory) / "output-authorizations.jsonl",
    )
    executor = ToolExecutor(
        rest,
        backstop,
        authorizer=authorizer,
    )
    protocol = GatewayProtocol(config.token)
    server = build_server(
        executor,
        registry,
        in_flight,
        authorizer,
        lambda: (
            f"discord:actor:{protocol.own_user_id}"
            if protocol.own_user_id is not None
            else None
        ),
    )
    session_manager = StreamableHTTPSessionManager(app=server, event_store=None)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        shutdown = asyncio.Event()
        queue: asyncio.Queue = asyncio.Queue(maxsize=config.queue_maxsize)
        route_map = {
            participant: frozenset(rooms)
            for participant, rooms in config.participant_routes
        }
        enqueuer = GapAwareEnqueuer(
            queue,
            TransportAuditJournal(
                Path(config.state_directory) / "transport-delivery-audit.jsonl"
            ),
            route_map,
        )
        runner = GatewayRunner(
            protocol,
            enqueuer,
            allowed_channel_ids=frozenset(config.allowed_channel_ids),
            membership_room_ids=config.membership_room_ids,
            on_source_gap=enqueuer.declare_source_gap,
        )
        gateway_task = asyncio.create_task(runner.run(shutdown), name="discord-gateway")
        pump_task = asyncio.create_task(
            pump_notifications(
                queue,
                lambda params: broadcast(registry, params),
                shutdown=shutdown,
                on_delivery_gap=enqueuer.declare_delivery_gap,
                on_delivery_success=enqueuer.record_delivery,
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
                gateway_task.cancel()
                try:
                    await asyncio.wait_for(
                        queue.join(),
                        timeout=config.drain_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    while True:
                        try:
                            event = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        enqueuer.declare_shutdown_gap(event)
                        queue.task_done()
                pump_task.cancel()
                await asyncio.gather(gateway_task, pump_task, return_exceptions=True)
                logger.info("transport shut down cleanly")

    app = Starlette(
        routes=[Mount("/mcp", app=session_manager.handle_request)],
        lifespan=lifespan,
    )

    logger.info(
        "nunchi-mcp-discord listening on http://%s:%d/mcp (transport only — no gate logic)",
        config.host, config.port,
    )
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
    return 0
