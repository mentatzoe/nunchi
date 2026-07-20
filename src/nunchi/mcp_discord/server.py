"""nunchi-mcp-discord console entry point and transport plumbing.

Standing MCP transport server for one Discord bot account:

    NUNCHI_DISCORD_TOKEN=... nunchi-mcp-discord

Requires the mcp SDK (opt-in only):

    pip install nunchi[mcp-discord]

The server listens on http://HOST:PORT/mcp (streamable HTTP). Inbound Discord
events are pushed as ``notifications/nunchi/v2/discord/event``. Exact self
events remain context; the observation owner decides the deterministic no-wake
result. Tools are exact-channel scoped and require a separate bearer token.

This module holds the import-safe plumbing (bounded queue, notification
pump, in-flight tracking for drain-on-shutdown); everything that touches the
mcp SDK lives in :mod:`._binding` and is imported lazily by :func:`main`.

Backpressure: the notification queue is bounded
(NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE, default 256). When a slow MCP client lets
it fill, the OLDEST event is dropped with a warning — for an admission-gate
transport the room's present matters more than its backlog, and memory stays
bounded. See integrations/mcp-discord/DESIGN.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import os
import sys
from typing import Awaitable, Callable

from .config import Config, load_config
from .events import MessageEvent, ReactionEvent
from .hygiene import install_redaction

logger = logging.getLogger("nunchi.mcp_discord.server")

_PUMP_POLL_SECONDS = 0.25


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


class BearerAuthMiddleware:
    """Authenticate every MCP HTTP request without logging credentials."""

    def __init__(self, app, token: str) -> None:
        if not callable(app) or not isinstance(token, str) or not token:
            raise ValueError("MCP bearer authentication is invalid")
        self.app = app
        self.expected = b"Bearer " + token.encode("ascii")

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http":
            values = [
                value
                for key, value in scope.get("headers", [])
                if key.lower() == b"authorization"
            ]
            if len(values) != 1 or not hmac.compare_digest(
                values[0],
                self.expected,
            ):
                body = b'{"error":"unauthorized"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("ascii")),
                            (b"www-authenticate", b"Bearer"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def enqueue_event(
    queue: asyncio.Queue,
    event: MessageEvent | ReactionEvent,
) -> bool:
    """Bounded enqueue with drop-oldest backpressure.

    Returns False when the queue was full and the oldest event was evicted
    to make room (never blocks, never grows without bound).
    """
    try:
        queue.put_nowait(event)
        return True
    except asyncio.QueueFull:
        try:
            dropped = queue.get_nowait()
            logger.warning(
                "notification queue full (maxsize=%d); dropped oldest message %s "
                "from channel %s — is the MCP client keeping up?",
                queue.maxsize, dropped.message_id, dropped.channel_id,
            )
        except asyncio.QueueEmpty:  # pragma: no cover — racing consumers only
            pass
        queue.put_nowait(event)
        return False


async def pump_notifications(
    queue: asyncio.Queue,
    send: Callable[[dict], Awaitable[None]],
    *,
    shutdown: asyncio.Event,
    projector: Callable[[MessageEvent | ReactionEvent], dict],
) -> None:
    """Drain the queue into *send* (broadcast to MCP sessions) until shutdown.

    A failing send (MCP client gone mid-write) drops that notification and
    keeps pumping; delivery to admission gates is best-effort by design.
    """
    while not shutdown.is_set():
        try:
            event = await asyncio.wait_for(queue.get(), timeout=_PUMP_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue
        params = projector(event)
        try:
            await send(params)
        except Exception as exc:  # noqa: BLE001 — transport must outlive one client
            logger.warning("notification delivery failed (client gone?): %s", exc)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nunchi-mcp-discord`` console script."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="nunchi-mcp-discord",
        description=(
            "Standing MCP transport server for one Discord bot account. "
            "V2 only; exact channels and bearer authentication are required."
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
    install_redaction(config.auth_token)

    try:
        import mcp  # noqa: F401
    except ImportError:
        print(
            "nunchi-mcp-discord: install the 'mcp-discord' extra to run the server",
            file=sys.stderr,
        )
        return 2

    from . import _binding

    return _binding.serve(config)


if __name__ == "__main__":
    raise SystemExit(main())
