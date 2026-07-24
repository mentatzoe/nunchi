"""Configuration for the nunchi MCP Discord transport server.

All configuration comes from environment variables; the bot token is read
from NUNCHI_DISCORD_TOKEN only and must never surface anywhere else (see
:mod:`.hygiene`).

Required env vars:
    NUNCHI_DISCORD_TOKEN    Bot token (Discord Developer Portal -> Bot -> Token)
    NUNCHI_DISCORD_PARTICIPANT_ROUTES
        Closed JSON object mapping each participant ID to its numeric channels.

Optional env vars:
    NUNCHI_MCP_DISCORD_HOST                     Bind host (default: 127.0.0.1)
    NUNCHI_MCP_DISCORD_PORT                     Bind port (default: 3993)
    NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE            Notification queue bound (default: 256)
    NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS       Max sends per channel per window (default: 5)
    NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS  Backstop window in seconds (default: 10)
    NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS    Shutdown drain timeout (default: 10)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
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
    allowed_channel_ids: tuple[str, ...] = ()
    participant_ids: tuple[str, ...] = ()
    participant_routes: tuple[tuple[str, tuple[str, ...]], ...] = ()
    membership_room_ids: tuple[str, ...] = ()
    output_hmac_key: bytes = field(default=b"", repr=False)
    state_directory: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or not self.token:
            raise ValueError("Discord token must be non-empty")
        if not isinstance(self.host, str) or not self.host:
            raise ValueError("Discord MCP host must be non-empty")
        if len(self.output_hmac_key) < 32:
            raise ValueError("Discord output HMAC key must be at least 32 bytes")
        if not isinstance(self.state_directory, str) or not self.state_directory:
            raise ValueError("Discord state directory must be non-empty")
        if not 1 <= self.port <= 65_535:
            raise ValueError("Discord MCP port must be within 1..65535")
        for name in ("queue_maxsize", "backstop_max_sends"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("backstop_window_seconds", "drain_timeout_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive and finite")
        routes = dict(self.participant_routes)
        if (
            not routes
            or len(routes) != len(self.participant_routes)
            or any(not participant for participant in routes)
            or any(
                not rooms or any(not room.isdigit() for room in rooms)
                for rooms in routes.values()
            )
        ):
            raise ValueError("Discord participant routes must be non-empty and numeric")
        if tuple(routes) != self.participant_ids:
            raise ValueError("Discord participant IDs must exactly match route owners")
        route_rooms = {room for rooms in routes.values() for room in rooms}
        if route_rooms != set(self.allowed_channel_ids):
            raise ValueError("Discord allowed channels must exactly match routed channels")
        if any(room not in route_rooms for room in self.membership_room_ids):
            raise ValueError("Discord membership rooms must be routed channels")


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


def load_config(environ: Mapping[str, str]) -> Config:
    """Build a :class:`Config` from *environ*; raises RuntimeError on bad input."""
    try:
        raw_routes = json.loads(
            _require(environ, "NUNCHI_DISCORD_PARTICIPANT_ROUTES")
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"NUNCHI_DISCORD_PARTICIPANT_ROUTES is invalid JSON: {exc.msg}"
        ) from None
    if not isinstance(raw_routes, dict) or not raw_routes:
        raise RuntimeError(
            "NUNCHI_DISCORD_PARTICIPANT_ROUTES must be a non-empty JSON object"
        )
    routes: list[tuple[str, tuple[str, ...]]] = []
    for participant, raw_rooms in raw_routes.items():
        if not isinstance(participant, str) or not participant:
            raise RuntimeError("Discord participant route IDs must be non-empty strings")
        if not isinstance(raw_rooms, list):
            raise RuntimeError("each Discord participant route must be an array")
        rooms = tuple(
            dict.fromkeys(
                item.strip()
                for item in raw_rooms
                if isinstance(item, str) and item.strip()
            )
        )
        if len(rooms) != len(raw_rooms) or not rooms or any(not item.isdigit() for item in rooms):
            raise RuntimeError(
                "each Discord participant route must contain unique numeric channel strings"
            )
        routes.append((participant, rooms))
    participants = tuple(participant for participant, _ in routes)
    allowed = tuple(
        dict.fromkeys(room for _, rooms in routes for room in rooms)
    )
    membership_raw = environ.get("NUNCHI_DISCORD_MEMBERSHIP_ROOM_IDS", "").strip()
    membership = tuple(
        dict.fromkeys(item.strip() for item in membership_raw.split(",") if item.strip())
    ) or allowed
    if any(item not in allowed for item in membership):
        raise RuntimeError("membership room IDs must be a subset of allowed channel IDs")
    output_key = _require(environ, "NUNCHI_DISCORD_OUTPUT_HMAC_KEY").encode()
    if len(output_key) < 32:
        raise RuntimeError("NUNCHI_DISCORD_OUTPUT_HMAC_KEY must be at least 32 bytes")
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
        allowed_channel_ids=allowed,
        participant_ids=participants,
        participant_routes=tuple(routes),
        membership_room_ids=membership,
        output_hmac_key=output_key,
        state_directory=_require(environ, "NUNCHI_DISCORD_STATE_DIRECTORY"),
    )
