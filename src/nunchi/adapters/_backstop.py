"""Per-channel send backstop shared by the reference adapters.

:class:`SendBackstop` is a sliding-window cap on outbound sends — at most
``max_sends`` per channel per ``window_seconds`` (default 5 per 10 s,
default ON). This is a security guard against amplification loops, not a
platform rate-limit mirror: it bounds the blast radius of a runaway
responder loop regardless of what the platform would tolerate. When the cap
trips the adapter suppresses the send and writes a receipt with
``action: "rate-limited"``; sends are never queued.

Ported from the MCP Discord transport's ``SendBackstop``
(``src/nunchi/mcp_discord/ratelimit.py`` on the transport branch). The clock
is injectable so tests run offline and instantly.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Callable, Mapping

DEFAULT_MAX_SENDS = 5
DEFAULT_WINDOW_SECONDS = 10.0


class SendBackstop:
    """Sliding-window cap: at most *max_sends* per channel per *window_seconds*."""

    def __init__(
        self,
        max_sends: int = DEFAULT_MAX_SENDS,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
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


def backstop_from_env(prefix: str, environ: Mapping[str, str] | None = None) -> SendBackstop:
    """Build a :class:`SendBackstop` from operator env knobs.

    Reads ``<prefix>_BACKSTOP_MAX_SENDS`` and
    ``<prefix>_BACKSTOP_WINDOW_SECONDS``. Missing or malformed values fall
    back to the defaults (5 sends per 10 s), matching the lenient parsing of
    the other adapter env knobs. The backstop is always ON; operators can
    only tune its shape.
    """
    env: Mapping[str, str] = os.environ if environ is None else environ

    raw_max = str(env.get(f"{prefix}_BACKSTOP_MAX_SENDS", "") or "").strip()
    try:
        max_sends = int(raw_max) if raw_max else DEFAULT_MAX_SENDS
    except ValueError:
        max_sends = DEFAULT_MAX_SENDS

    raw_window = str(env.get(f"{prefix}_BACKSTOP_WINDOW_SECONDS", "") or "").strip()
    try:
        window_seconds = float(raw_window) if raw_window else DEFAULT_WINDOW_SECONDS
    except ValueError:
        window_seconds = DEFAULT_WINDOW_SECONDS

    return SendBackstop(max_sends, window_seconds)
