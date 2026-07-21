"""Sans-IO Discord gateway protocol.

Pure state machine: feed decoded gateway payloads to
:meth:`GatewayProtocol.handle`, get back a list of actions (payloads to send,
events to dispatch, reconnect requests). No sockets, no clocks — the asyncio
shell lives in :mod:`.runner`, which makes disconnect/resume behavior fully
testable offline.

Intents: GUILD_MESSAGES | MESSAGE_CONTENT. MESSAGE_CONTENT is a *privileged*
intent — it must be enabled per bot in the Discord Developer Portal
(Applications -> your app -> Bot -> Privileged Gateway Intents -> MESSAGE
CONTENT INTENT), or the gateway closes the connection with code 4014 and
message content arrives empty on verified bots. See
``integrations/mcp-discord/README.md``.

Payloads carrying the token (IDENTIFY, RESUME) are never logged; the runner
logs opcodes and event names only (see :mod:`.hygiene`).
"""

from __future__ import annotations

import sys
import urllib.parse
from dataclasses import dataclass

GUILD_MESSAGES = 1 << 9
GUILD_MESSAGE_REACTIONS = 1 << 10
MESSAGE_CONTENT = 1 << 15
INTENTS = GUILD_MESSAGES | GUILD_MESSAGE_REACTIONS | MESSAGE_CONTENT
V2_INTENTS = INTENTS

DEFAULT_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
_GATEWAY_QUERY = "v=10&encoding=json"

# Gateway opcodes (client-relevant subset)
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RESUME = 6
OP_RECONNECT = 7
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

# Close codes that must not be retried (bad token, bad intents, ...)
_FATAL_CLOSE_CODES = frozenset({4004, 4010, 4011, 4012, 4013, 4014})
# Close codes after which the session is dead but a fresh IDENTIFY is fine
_IDENTIFY_CLOSE_CODES = frozenset({4007, 4009})

_CLOSE_HINTS = {
    4004: "authentication failed — check NUNCHI_DISCORD_TOKEN",
    4013: (
        "invalid intents — this build requests GUILD_MESSAGES | "
        "GUILD_MESSAGE_REACTIONS | MESSAGE_CONTENT"
    ),
    4014: (
        "disallowed intents — enable 'MESSAGE CONTENT INTENT' for this bot in the "
        "Discord Developer Portal (Bot -> Privileged Gateway Intents)"
    ),
}


def _gateway_url(value: object) -> str | None:
    """Bind credential-bearing gateway connections to Discord TLS origins."""

    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname
    if (
        parsed.scheme != "wss"
        or not isinstance(hostname, str)
        or not hostname.isascii()
        or not (
            hostname == "gateway.discord.gg"
            or hostname.endswith(".discord.gg")
        )
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.fragment
    ):
        return None
    if parsed.query:
        try:
            query = urllib.parse.parse_qs(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
            )
        except ValueError:
            return None
        if query != {"v": ["10"], "encoding": ["json"]}:
            return None
    authority = hostname if port is None else f"{hostname}:{port}"
    return f"wss://{authority}/?{_GATEWAY_QUERY}"


def _nonempty_ascii(value: object, *, maximum: int = 512) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and value.isascii()
        and all(33 <= ord(character) <= 126 for character in value)
    )


def _snowflake(value: object) -> str | None:
    return value if isinstance(value, str) and value.isdigit() else None


def classify_close(code: int | None) -> str:
    """Map a close code to a reconnect strategy: 'resume', 'identify', or 'fatal'."""
    if code in _FATAL_CLOSE_CODES:
        return "fatal"
    if code in _IDENTIFY_CLOSE_CODES:
        return "identify"
    return "resume"


def close_hint(code: int | None) -> str | None:
    """Operator-facing hint for a close code, if we have one."""
    return _CLOSE_HINTS.get(code) if code is not None else None


@dataclass(frozen=True)
class SendPayload:
    """Send this JSON payload over the gateway socket."""

    payload: dict


@dataclass(frozen=True)
class Dispatch:
    """A dispatch event to hand to the application layer."""

    event: str
    data: dict
    sequence: int | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class CloseAndReconnect:
    """Close the socket and reconnect; resume if ``resume`` is True."""

    resume: bool


Action = SendPayload | Dispatch | CloseAndReconnect


class GatewayProtocol:
    """Tracks one bot account's gateway session across (re)connections."""

    def __init__(self, token: str, intents: int = INTENTS) -> None:
        self._token = token
        self._intents = intents
        self.session_id: str | None = None
        self.resume_gateway_url: str | None = None
        self.seq: int | None = None
        self.own_user_id: str | None = None
        self.heartbeat_interval_ms: int | None = None
        self.ready = False
        self._awaiting_ack = False

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    @property
    def can_resume(self) -> bool:
        return self.session_id is not None and self.seq is not None

    def connect_url(self) -> str:
        """URL for the next connection (resume URL when resuming)."""
        if self.can_resume and self.resume_gateway_url:
            return self.resume_gateway_url
        return DEFAULT_GATEWAY_URL

    def on_connection_open(self) -> None:
        """Reset per-connection state (session/resume state is preserved)."""
        self.heartbeat_interval_ms = None
        self.ready = False
        self._awaiting_ack = False

    def invalidate_session(self) -> None:
        """Forget the resumable session (next HELLO triggers IDENTIFY)."""
        self.session_id = None
        self.resume_gateway_url = None
        self.seq = None
        self.own_user_id = None
        self.ready = False

    # ------------------------------------------------------------------ #
    # Heartbeat bookkeeping (timing lives in the runner)
    # ------------------------------------------------------------------ #

    def heartbeat_payload(self) -> dict:
        return {"op": OP_HEARTBEAT, "d": self.seq}

    def mark_heartbeat_sent(self) -> None:
        self._awaiting_ack = True

    def heartbeat_overdue(self) -> bool:
        """True if the previous heartbeat was never ACKed (zombie connection)."""
        return self._awaiting_ack

    # ------------------------------------------------------------------ #
    # Payload handling
    # ------------------------------------------------------------------ #

    def handle(self, payload: dict) -> list[Action]:
        if not isinstance(payload, dict):
            return []
        op = payload.get("op")
        if isinstance(op, bool) or not isinstance(op, int):
            return []
        if op == OP_HELLO:
            data = payload.get("d")
            interval = data.get("heartbeat_interval") if isinstance(data, dict) else None
            if (
                isinstance(interval, bool)
                or not isinstance(interval, int)
                or interval < 1
            ):
                self.invalidate_session()
                return [CloseAndReconnect(resume=False)]
            self.heartbeat_interval_ms = interval
            if self.can_resume:
                return [SendPayload(self._resume_payload())]
            return [SendPayload(self._identify_payload())]
        if op == OP_HEARTBEAT:
            return [SendPayload(self.heartbeat_payload())]
        if op == OP_HEARTBEAT_ACK:
            self._awaiting_ack = False
            return []
        if op == OP_RECONNECT:
            return [CloseAndReconnect(resume=True)]
        if op == OP_INVALID_SESSION:
            resumable = payload.get("d")
            if not isinstance(resumable, bool):
                self.invalidate_session()
                return [CloseAndReconnect(resume=False)]
            if resumable and not self.can_resume:
                self.invalidate_session()
                return [CloseAndReconnect(resume=False)]
            if not resumable:
                self.invalidate_session()
            return [CloseAndReconnect(resume=resumable)]
        if op == OP_DISPATCH:
            return self._handle_dispatch(payload)
        return []

    def _handle_dispatch(self, payload: dict) -> list[Action]:
        seq = payload.get("s")
        event = payload.get("t")
        data = payload.get("d")
        if (
            isinstance(seq, bool)
            or not isinstance(seq, int)
            or seq < 0
            or not isinstance(event, str)
            or not event
            or not isinstance(data, dict)
            or (self.seq is not None and seq <= self.seq)
        ):
            self.invalidate_session()
            return [CloseAndReconnect(resume=False)]
        self.seq = seq
        if event == "READY":
            session_id = data.get("session_id")
            resume_gateway_url = _gateway_url(data.get("resume_gateway_url"))
            user = data.get("user")
            own_user_id = (
                _snowflake(user.get("id")) if isinstance(user, dict) else None
            )
            if (
                not _nonempty_ascii(session_id)
                or resume_gateway_url is None
                or own_user_id is None
            ):
                self.invalidate_session()
                self.own_user_id = None
                return [CloseAndReconnect(resume=False)]
            self.session_id = session_id
            self.resume_gateway_url = resume_gateway_url
            self.own_user_id = own_user_id
            self.ready = True
            return []
        if event == "RESUMED":
            if (
                not _nonempty_ascii(self.session_id)
                or self.resume_gateway_url is None
                or _snowflake(self.own_user_id) is None
            ):
                self.invalidate_session()
                self.own_user_id = None
                return [CloseAndReconnect(resume=False)]
            self.ready = True
            return []
        if event in (
            "MESSAGE_CREATE",
            "MESSAGE_REACTION_ADD",
            "MESSAGE_REACTION_REMOVE",
        ):
            if not self.ready or _snowflake(self.own_user_id) is None:
                self.invalidate_session()
                self.own_user_id = None
                return [CloseAndReconnect(resume=False)]
            return [Dispatch(event, data, sequence=self.seq, session_id=self.session_id)]
        return []

    # ------------------------------------------------------------------ #
    # Auth payloads — these carry the token; never log them.
    # ------------------------------------------------------------------ #

    def _identify_payload(self) -> dict:
        return {
            "op": OP_IDENTIFY,
            "d": {
                "token": self._token,
                "intents": self._intents,
                "properties": {
                    "os": sys.platform,
                    "browser": "nunchi-mcp-discord",
                    "device": "nunchi-mcp-discord",
                },
            },
        }

    def _resume_payload(self) -> dict:
        return {
            "op": OP_RESUME,
            "d": {
                "token": self._token,
                "session_id": self.session_id,
                "seq": self.seq,
            },
        }
