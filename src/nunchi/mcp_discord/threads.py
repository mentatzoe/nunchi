"""Which routed channel a thread belongs to.

A message in a thread carries only the thread's own id as its channel. The
thread belongs to a room when its parent channel is a routed one. Discord
answers that with one REST read per thread (``GET /channels/{id}``); the
answer does not change, so it is remembered.
"""

from __future__ import annotations

import asyncio
import threading
import time

from .rest import DiscordRestError

_THREAD_TYPES = frozenset({10, 11, 12})  # announcement, public and private threads
_MAX_REMEMBERED = 4096
# A lookup that failed is not tried again at once: while Discord's REST API is
# down, every message in a channel that is not routed would otherwise wait for
# its own failing request.
_FAILURE_MEMORY_SECONDS = 30.0
# How long the gateway's read loop waits for one lookup (``parent_within``).
_LOOKUP_WAIT_SECONDS = 3.0


class ThreadDirectory:
    """Maps a channel id to the routed channel it is a thread of."""

    def __init__(self, rest, routed: frozenset[str], *, clock=time.monotonic) -> None:
        self._rest = rest
        self._routed = routed
        self._clock = clock
        self._parents: dict[str, str | None] = {}
        self._failed: dict[str, tuple[float, int | None, str]] = {}
        self._lock = threading.Lock()

    def parent_of(self, channel_id: str) -> str | None:
        """The routed channel *channel_id* is a thread of, or None for any other channel.

        Raises ``DiscordRestError`` when Discord cannot say; the caller must not
        treat that as "not a thread".
        """

        if not channel_id.isdigit():
            return None  # not a snowflake: no channel, and never part of a URL path
        with self._lock:
            if channel_id in self._parents:
                return self._parents[channel_id]
            failure = self._failed.get(channel_id)
            if failure is not None and self._clock() - failure[0] < _FAILURE_MEMORY_SECONDS:
                raise DiscordRestError(failure[1], failure[2])
        try:
            channel = self._rest.get_channel(channel_id)
        except Exception as exc:  # whatever the failure, the next ask does not repeat it at once
            self._remember_failure(channel_id, getattr(exc, "status", None), str(exc) or type(exc).__name__)
            raise
        parent = str(channel.get("parent_id") or "")
        found = parent if channel.get("type") in _THREAD_TYPES and parent in self._routed else None
        with self._lock:
            if len(self._parents) >= _MAX_REMEMBERED:
                self._parents.clear()
            self._parents[channel_id] = found
            self._failed.pop(channel_id, None)
        return found

    async def parent_within(self, channel_id: str, seconds: float = _LOOKUP_WAIT_SECONDS) -> str | None:
        """``parent_of`` off the event loop, but never waiting longer than *seconds*.

        The gateway reads one socket in one loop: while it waits for Discord's
        REST API it reads nothing, heartbeat ACKs included. When the answer is
        late, say so as a failure (the caller declares a gap) and remember it,
        so the next message from this channel does not wait again; the lookup
        goes on in its worker thread and, when it ends, replaces that memory
        with its answer.
        """

        try:
            return await asyncio.wait_for(asyncio.to_thread(self.parent_of, channel_id), seconds)
        except asyncio.TimeoutError:
            if channel_id not in self._parents:
                self._remember_failure(channel_id, None, "the lookup is still pending")
            raise DiscordRestError(None, "the thread lookup is still pending") from None

    def _remember_failure(self, channel_id: str, status: int | None, detail: str) -> None:
        with self._lock:
            if len(self._failed) >= _MAX_REMEMBERED:
                self._failed.clear()
            self._failed[channel_id] = (self._clock(), status, detail)
