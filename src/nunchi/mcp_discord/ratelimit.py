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

import math
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
        # Discord bucket identity -> (remaining, reset_at monotonic).
        self._buckets: dict[str, tuple[int, float]] = {}
        self._route_buckets: dict[str, str] = {}
        self._global_until = 0.0

    def before_request(self, route: str) -> None:
        """Block until the route (and the global limit) permit a request."""
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._global_until - now)
            bucket_key = self._route_buckets.get(route, f"route:{route}")
            bucket = self._buckets.get(bucket_key)
            clear_bucket: tuple[int, float] | None = None
            if bucket is not None:
                remaining, reset_at = bucket
                if reset_at <= now:
                    self._buckets.pop(bucket_key, None)
                elif remaining <= 0:
                    delay = max(delay, reset_at - now)
                    clear_bucket = bucket
                elif delay == 0:
                    # Reserve capacity while holding the lock so two worker
                    # threads cannot both consume the last remaining slot.
                    self._buckets[bucket_key] = (remaining - 1, reset_at)
            clear_global = self._global_until > now and delay > 0
        if delay > 0:
            self._sleep(delay)
            with self._lock:
                if clear_bucket is not None and self._buckets.get(bucket_key) == clear_bucket:
                    self._buckets.pop(bucket_key, None)
                if clear_global:
                    self._global_until = 0.0

    def after_response(self, route: str, headers: Mapping[str, str]) -> None:
        """Record bucket state from response headers (lower-cased keys)."""
        remaining = headers.get("x-ratelimit-remaining")
        reset_after = headers.get("x-ratelimit-reset-after")
        if remaining is None or reset_after is None:
            return
        try:
            parsed_remaining = float(remaining)
            parsed_reset = float(reset_after)
            if (
                not math.isfinite(parsed_remaining)
                or not math.isfinite(parsed_reset)
                or parsed_remaining < 0
                or parsed_reset < 0
                or parsed_reset > 86400
            ):
                return
            parsed = (int(parsed_remaining), self._clock() + parsed_reset)
        except (TypeError, ValueError, OverflowError):
            return
        with self._lock:
            bucket_id = headers.get("x-ratelimit-bucket")
            if isinstance(bucket_id, str) and bucket_id and len(bucket_id) <= 512:
                bucket_key = f"discord:{bucket_id}"
                self._route_buckets[route] = bucket_key
            else:
                bucket_key = self._route_buckets.get(route, f"route:{route}")
            self._buckets[bucket_key] = parsed

    def note_retry_after(self, route: str, seconds: float, *, is_global: bool) -> None:
        """Record a 429's retry-after so the next attempt waits."""
        if not math.isfinite(seconds) or seconds < 0 or seconds > 300:
            seconds = 1.0
        with self._lock:
            until = self._clock() + max(0.0, seconds)
            if is_global:
                self._global_until = max(self._global_until, until)
            else:
                bucket_key = self._route_buckets.get(route, f"route:{route}")
                self._buckets[bucket_key] = (0, until)


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
