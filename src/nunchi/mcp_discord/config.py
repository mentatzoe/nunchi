"""Configuration for the nunchi MCP Discord transport server.

All configuration comes from environment variables; the bot token is read
from NUNCHI_DISCORD_TOKEN only and must never surface anywhere else (see
:mod:`.hygiene`).

Required env vars:
    NUNCHI_DISCORD_TOKEN    Bot token (Discord Developer Portal -> Bot -> Token)

Optional env vars:
    NUNCHI_MCP_DISCORD_MODE                     v1 (default) or v2
    NUNCHI_MCP_DISCORD_CHANNELS                 Required comma-separated channel IDs in v2
    NUNCHI_MCP_DISCORD_BLOCKED_ACTORS            Optional comma-separated user IDs in v2
    NUNCHI_MCP_DISCORD_HOST                     Bind host (default: 127.0.0.1)
    NUNCHI_MCP_DISCORD_PORT                     Bind port (default: 3993)
    NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE            Notification queue bound (default: 256)
    NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS       Max sends per channel per window (default: 5)
    NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS  Backstop window in seconds (default: 10)
    NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS    Shutdown drain timeout (default: 10)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 3993
_DEFAULT_QUEUE_MAXSIZE = 256
_DEFAULT_BACKSTOP_MAX_SENDS = 5
_DEFAULT_BACKSTOP_WINDOW_SECONDS = 10.0
_DEFAULT_DRAIN_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Config:
    """Server configuration. ``token`` is excluded from repr on purpose."""

    token: str = field(repr=False)
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    queue_maxsize: int = _DEFAULT_QUEUE_MAXSIZE
    backstop_max_sends: int = _DEFAULT_BACKSTOP_MAX_SENDS
    backstop_window_seconds: float = _DEFAULT_BACKSTOP_WINDOW_SECONDS
    drain_timeout_seconds: float = _DEFAULT_DRAIN_TIMEOUT_SECONDS
    mode: str = "v1"
    channels: frozenset[str] = frozenset()
    blocked_actors: frozenset[str] = frozenset()


def _require(environ: Mapping[str, str], name: str) -> str:
    val = environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name} is not set.")
    return val


def _get_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"Environment variable {name} must be an integer, got {raw!r}.") from None


def _get_float(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"Environment variable {name} must be a number, got {raw!r}.") from None


def _snowflake_csv(environ: Mapping[str, str], name: str) -> frozenset[str]:
    raw = environ.get(name, "").strip()
    if not raw:
        return frozenset()
    values = frozenset(part.strip() for part in raw.split(",") if part.strip())
    if any(not value.isdigit() for value in values):
        raise RuntimeError(f"Environment variable {name} must contain numeric snowflake IDs.")
    return values


def load_config(environ: Mapping[str, str]) -> Config:
    """Build a :class:`Config` from *environ*; raises RuntimeError on bad input."""
    mode = environ.get("NUNCHI_MCP_DISCORD_MODE", "v1").strip().lower() or "v1"
    if mode not in ("v1", "v2"):
        raise RuntimeError("Environment variable NUNCHI_MCP_DISCORD_MODE must be 'v1' or 'v2'.")
    channels = _snowflake_csv(environ, "NUNCHI_MCP_DISCORD_CHANNELS")
    blocked = _snowflake_csv(environ, "NUNCHI_MCP_DISCORD_BLOCKED_ACTORS")
    if mode == "v2" and not channels:
        raise RuntimeError("NUNCHI_MCP_DISCORD_CHANNELS is required in v2 mode.")
    return Config(
        token=_require(environ, "NUNCHI_DISCORD_TOKEN"),
        host=environ.get("NUNCHI_MCP_DISCORD_HOST", "").strip() or _DEFAULT_HOST,
        port=_get_int(environ, "NUNCHI_MCP_DISCORD_PORT", _DEFAULT_PORT),
        queue_maxsize=_get_int(environ, "NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE", _DEFAULT_QUEUE_MAXSIZE),
        backstop_max_sends=_get_int(
            environ, "NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS", _DEFAULT_BACKSTOP_MAX_SENDS
        ),
        backstop_window_seconds=_get_float(
            environ, "NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS", _DEFAULT_BACKSTOP_WINDOW_SECONDS
        ),
        drain_timeout_seconds=_get_float(
            environ, "NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS", _DEFAULT_DRAIN_TIMEOUT_SECONDS
        ),
        mode=mode,
        channels=channels,
        blocked_actors=blocked,
    )
