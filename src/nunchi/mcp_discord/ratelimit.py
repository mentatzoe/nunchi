"""Discord rate-limit guards.

Two layers, both enforced on every send:

- :class:`RateLimiter` — honors Discord's per-route buckets
  (X-RateLimit-Remaining / X-RateLimit-Reset-After) and 429 retry-after,
  including the global flag. Sits inside the REST client.
- :class:`SendBackstop` — a transport-local sliding-window cap on sends per
  channel (default on). This is a security guard, not a Discord mirror: it
  bounds the blast radius of a runaway harness regardless of what Discord
  would tolerate. Exceeding it fails the tool call with a retry-in hint; it
  never queues.

Clock and sleep are injectable so tests run offline and instantly.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Mapping


class RateLimiter:
    """Per-route bucket guard; used from worker threads (sync)."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleeper
        self._lock = threading.Lock()
        # route -> (remaining, reset_at monotonic)
        self._buckets: dict[str, tuple[int, float]] = {}
        self._global_until = 0.0

    def before_request(self, route: str) -> None:
        """Block until the route (and the global limit) permit a request."""
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._global_until - now)
            bucket = self._buckets.get(route)
            if bucket is not None:
                remaining, reset_at = bucket
                if remaining <= 0 and reset_at > now:
                    delay = max(delay, reset_at - now)
        if delay > 0:
            self._sleep(delay)

    def after_response(self, route: str, headers: Mapping[str, str]) -> None:
        """Record bucket state from response headers (lower-cased keys)."""
        remaining = headers.get("x-ratelimit-remaining")
        reset_after = headers.get("x-ratelimit-reset-after")
        if remaining is None or reset_after is None:
            return
        try:
            parsed = (int(float(remaining)), self._clock() + float(reset_after))
        except ValueError:
            return
        with self._lock:
            self._buckets[route] = parsed

    def note_retry_after(self, route: str, seconds: float, *, is_global: bool) -> None:
        """Record a 429's retry-after so the next attempt waits."""
        with self._lock:
            until = self._clock() + max(0.0, seconds)
            if is_global:
                self._global_until = max(self._global_until, until)
            else:
                self._buckets[route] = (0, until)


class SendBackstop:
    """Sliding-window cap: at most *max_sends* per channel per *window_seconds*."""

    def __init__(
        self,
        max_sends: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_sends = max_sends
        self.window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._sent: dict[str, deque[float]] = {}

    def try_acquire(self, channel_id: str) -> float:
        """Returns 0.0 and records the send if allowed; else seconds to wait."""
        with self._lock:
            now = self._clock()
            window = self._sent.setdefault(str(channel_id), deque())
            while window and window[0] <= now - self.window_seconds:
                window.popleft()
            if len(window) >= self.max_sends:
                if not window:  # max_sends == 0: sends are disabled outright
                    return self.window_seconds
                return (window[0] + self.window_seconds) - now
            window.append(now)
            return 0.0
