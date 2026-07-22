"""Asyncio gateway runner: connection lifecycle around the sans-IO protocol.

Owns the WebSocket, the heartbeat task, reconnect backoff, and resume. All
protocol decisions live in :class:`.gateway.GatewayProtocol`; this module
only moves bytes and time. Fatal close codes (bad token, disallowed intents)
raise :class:`GatewayFatalError` — permanent errors abort immediately rather
than retrying forever.

Log lines carry opcodes/event names only; gateway payloads (which include the
token in IDENTIFY/RESUME) are never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Awaitable, Callable

from .events import (
    GatewayContinuityEvent,
    MessageEvent,
    ReactionEvent,
    filter_message_create,
    reaction_event_from_dispatch,
)
from .gateway import (
    CloseAndReconnect,
    Dispatch,
    GatewayProtocol,
    SendPayload,
    classify_close,
    close_hint,
)
from .rest import _strict_json
from .ws import WSClient, WSClosed, WSError

logger = logging.getLogger("nunchi.mcp_discord.runner")

_MAX_BACKOFF_SECONDS = 60.0
_RECONNECT_CLOSE_CODE = 4000  # client-initiated close that keeps the session resumable


class GatewayFatalError(Exception):
    """The gateway rejected us permanently (bad token, disallowed intents)."""


class GatewayRunner:
    """Runs one bot account's gateway connection until shutdown or fatal error."""

    def __init__(
        self,
        protocol: GatewayProtocol,
        on_event: Callable[[MessageEvent | ReactionEvent], None],
        *,
        connect: Callable[[str], Awaitable] | None = None,
        rng: Callable[[], float] = random.random,
        initial_backoff: float = 1.0,
    ) -> None:
        self._protocol = protocol
        self._on_event = on_event
        self._connect = connect or WSClient.connect
        self._rng = rng
        self._initial_backoff = initial_backoff

    async def run(self, shutdown: asyncio.Event) -> None:
        backoff = self._initial_backoff
        while not shutdown.is_set():
            url = self._protocol.connect_url()
            try:
                ws = await self._connect(url)
            except (OSError, WSError, asyncio.TimeoutError) as exc:
                logger.warning("gateway connect failed: %s; retrying in %.1fs", exc, backoff)
                await self._sleep_or_shutdown(backoff, shutdown)
                backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
                continue

            self._protocol.on_connection_open()
            logger.info(
                "gateway connected (%s)", "resuming" if self._protocol.can_resume else "identifying"
            )
            close_code = await self._run_connection(ws, shutdown)
            if shutdown.is_set():
                return

            if self._protocol.ready:
                backoff = self._initial_backoff

            strategy = classify_close(close_code)
            hint = close_hint(close_code)
            if strategy == "fatal":
                raise GatewayFatalError(
                    f"gateway closed with code {close_code}: {hint or 'not retryable'}"
                )
            if strategy == "identify":
                self._on_event(
                    GatewayContinuityEvent(
                        reason=f"gateway-close-{close_code}-requires-identify",
                        previous_session_id=self._protocol.session_id,
                        expected_sequence=(
                            self._protocol.seq + 1
                            if self._protocol.seq is not None
                            else None
                        ),
                        observed_sequence=None,
                    )
                )
                self._protocol.invalidate_session()
            logger.warning(
                "gateway connection ended (code=%s); will %s in %.1fs",
                close_code, strategy, backoff,
            )
            await self._sleep_or_shutdown(backoff, shutdown)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    async def _run_connection(self, ws, shutdown: asyncio.Event) -> int | None:
        """Drive one connection; returns the close code (None for EOF/local)."""
        heartbeat_task: asyncio.Task | None = None
        try:
            while True:
                try:
                    text = await ws.receive_text()
                except WSClosed as exc:
                    return exc.code
                try:
                    payload = _strict_json(text)
                except ValueError:
                    logger.warning(
                        "malformed gateway payload; reconnecting from the last "
                        "attested sequence"
                    )
                    await ws.send_close(_RECONNECT_CLOSE_CODE)
                    return None
                for action in self._protocol.handle(payload):
                    if isinstance(action, SendPayload):
                        await ws.send_text(json.dumps(action.payload))
                        if action.payload.get("op") == 1:
                            self._protocol.mark_heartbeat_sent()
                    elif isinstance(action, Dispatch):
                        if action.event == "MESSAGE_CREATE":
                            event = filter_message_create(
                                action.data,
                                self._protocol.own_user_id,
                                retain_self=True,
                                gateway_session_id=action.session_id,
                                gateway_sequence=action.sequence,
                                gateway_self_user_id=self._protocol.own_user_id,
                            )
                            if event is not None:
                                self._on_event(event)
                        elif action.event in (
                            "MESSAGE_REACTION_ADD",
                            "MESSAGE_REACTION_REMOVE",
                        ):
                            event = reaction_event_from_dispatch(
                                action.data,
                                operation=(
                                    "add"
                                    if action.event == "MESSAGE_REACTION_ADD"
                                    else "remove"
                                ),
                                gateway_session_id=action.session_id,
                                gateway_sequence=action.sequence,
                                gateway_self_user_id=self._protocol.own_user_id,
                            )
                            if event is not None:
                                self._on_event(event)
                    elif isinstance(action, CloseAndReconnect):
                        if action.reason is not None:
                            self._on_event(
                                GatewayContinuityEvent(
                                    reason=action.reason,
                                    previous_session_id=action.previous_session_id,
                                    expected_sequence=action.expected_sequence,
                                    observed_sequence=action.observed_sequence,
                                )
                            )
                        logger.info(
                            "gateway asked us to reconnect (resume=%s)", action.resume
                        )
                        if not action.resume:
                            self._protocol.invalidate_session()
                        await ws.send_close(_RECONNECT_CLOSE_CODE)
                        return None
                if heartbeat_task is None and self._protocol.heartbeat_interval_ms:
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
        except asyncio.CancelledError:
            # Graceful local shutdown: tell Discord we're leaving cleanly.
            await ws.send_close(1000)
            raise
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            await ws.close()

    async def _heartbeat_loop(self, ws) -> None:
        assert self._protocol.heartbeat_interval_ms is not None
        interval = self._protocol.heartbeat_interval_ms / 1000.0
        await asyncio.sleep(interval * self._rng())  # jitter, per gateway docs
        while True:
            if self._protocol.heartbeat_overdue():
                # Zombie connection: close resumable and let run() reconnect.
                logger.warning("heartbeat ACK missing; closing zombie connection")
                await ws.send_close(_RECONNECT_CLOSE_CODE)
                await ws.close()
                return
            await ws.send_text(json.dumps(self._protocol.heartbeat_payload()))
            self._protocol.mark_heartbeat_sent()
            await asyncio.sleep(interval)

    @staticmethod
    async def _sleep_or_shutdown(seconds: float, shutdown: asyncio.Event) -> None:
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
