"""Configuration for the nunchi MCP Discord transport server.

All configuration comes from environment variables; the bot token is read
from NUNCHI_DISCORD_TOKEN only and must never surface anywhere else (see
:mod:`.hygiene`).

Required env vars:
    NUNCHI_DISCORD_TOKEN                           Discord bot token
    NUNCHI_MCP_DISCORD_CHANNELS                 Comma-separated trusted channel IDs
    NUNCHI_MCP_DISCORD_AUTH_TOKEN               Separate bearer credential for MCP clients

Optional env vars:
    NUNCHI_MCP_DISCORD_BLOCKED_ACTORS           Comma-separated blocked user IDs
    NUNCHI_MCP_DISCORD_HOST                     Bind host (default: 127.0.0.1)
    NUNCHI_MCP_DISCORD_PORT                     Bind port (default: 3993)
    NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE            Notification queue bound (default: 256)
    NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS       Max sends per channel per window (default: 5)
    NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS  Backstop window in seconds (default: 10)
    NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS    Shutdown drain timeout (default: 10)
"""

from __future__ import annotations

import math
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
    """Server configuration. Both credentials are excluded from repr."""

    token: str = field(repr=False)
    auth_token: str = field(repr=False)
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    queue_maxsize: int = _DEFAULT_QUEUE_MAXSIZE
    backstop_max_sends: int = _DEFAULT_BACKSTOP_MAX_SENDS
    backstop_window_seconds: float = _DEFAULT_BACKSTOP_WINDOW_SECONDS
    drain_timeout_seconds: float = _DEFAULT_DRAIN_TIMEOUT_SECONDS
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


def _auth_token(environ: Mapping[str, str], discord_token: str) -> str:
    value = _require(environ, "NUNCHI_MCP_DISCORD_AUTH_TOKEN")
    if (
        len(value) < 32
        or len(value) > 4096
        or not value.isascii()
        or any(not 33 <= ord(character) <= 126 for character in value)
        or value == discord_token
    ):
        raise RuntimeError(
            "NUNCHI_MCP_DISCORD_AUTH_TOKEN must be a separate ASCII secret "
            "of at least 32 non-whitespace characters."
        )
    return value


def load_config(environ: Mapping[str, str]) -> Config:
    """Build a :class:`Config` from *environ*; raises RuntimeError on bad input."""
    if "NUNCHI_MCP_DISCORD_MODE" in environ:
        raise RuntimeError(
            "NUNCHI_MCP_DISCORD_MODE was removed; the server implements V2 only."
        )
    discord_token = _require(environ, "NUNCHI_DISCORD_TOKEN")
    channels = _snowflake_csv(environ, "NUNCHI_MCP_DISCORD_CHANNELS")
    blocked = _snowflake_csv(environ, "NUNCHI_MCP_DISCORD_BLOCKED_ACTORS")
    if not channels:
        raise RuntimeError("NUNCHI_MCP_DISCORD_CHANNELS is required.")
    config = Config(
        token=discord_token,
        auth_token=_auth_token(environ, discord_token),
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
        channels=channels,
        blocked_actors=blocked,
    )
    if (
        config.host not in ("127.0.0.1", "::1", "localhost")
        or not 1 <= config.port <= 65535
        or not 1 <= config.queue_maxsize <= 100000
        or not 1 <= config.backstop_max_sends <= 100000
        or not math.isfinite(config.backstop_window_seconds)
        or not 0 < config.backstop_window_seconds <= 86400
        or not math.isfinite(config.drain_timeout_seconds)
        or not 0 < config.drain_timeout_seconds <= 3600
    ):
        raise RuntimeError(
            "MCP Discord must bind to loopback and use valid runtime limits."
        )
    return config
