"""MCP tool contract: schemas and the executor (import-safe, no SDK).

Tool schemas are plain JSON-Schema dicts so any harness (and the token
hygiene test) can serialize them without the mcp SDK installed. The
:class:`ToolExecutor` validates arguments, enforces the send backstop, and
calls the REST client; :mod:`._binding` wraps it for the SDK.

Message-shaped results reuse the notification field names
(message_id/author_id/...), so a harness handles one shape everywhere.
"""

from __future__ import annotations

import logging
from typing import Protocol

from .events import message_addressing, message_text
from .ratelimit import SendBackstop
from .rest import DiscordRestError

logger = logging.getLogger("nunchi.mcp_discord.tools")

_MAX_CONTENT_LENGTH = 2000  # Discord's message content limit

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "send_message",
        "description": (
            "Send a message to a Discord channel. Content is posted verbatim "
            "(no transformation). Subject to a per-channel send backstop."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Target channel snowflake ID."},
                "content": {
                    "type": "string",
                    "maxLength": _MAX_CONTENT_LENGTH,
                    "description": "Message text (max 2000 chars).",
                },
            },
            "required": ["channel_id", "content"],
        },
    },
    {
        "name": "reply_message",
        "description": (
            "Reply to a specific message in a Discord channel (threaded "
            "message reference). Subject to the same send backstop."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel snowflake ID."},
                "message_id": {"type": "string", "description": "Message snowflake ID to reply to."},
                "content": {
                    "type": "string",
                    "maxLength": _MAX_CONTENT_LENGTH,
                    "description": "Reply text (max 2000 chars).",
                },
            },
            "required": ["channel_id", "message_id", "content"],
        },
    },
    {
        "name": "read_history",
        "description": (
            "Read recent messages from a Discord channel, newest first. "
            "Bot-authored messages are included."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel snowflake ID."},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 50,
                    "description": "How many messages to fetch (1-100).",
                },
                "before": {
                    "type": "string",
                    "description": "Only messages before this message snowflake ID.",
                },
            },
            "required": ["channel_id"],
        },
    },
]

TOOL_NAMES = frozenset(schema["name"] for schema in TOOL_SCHEMAS)


class RestLike(Protocol):
    """The REST surface the executor needs (real client or test fake)."""

    def create_message(
        self, channel_id: str, content: str, *, reply_to_message_id: str | None = None
    ) -> dict: ...

    def get_messages(
        self, channel_id: str, *, limit: int = 50, before: str | None = None
    ) -> list[dict]: ...


def shape_message(msg: dict) -> dict:
    """Normalize an API message object to the notification field names."""
    author = msg.get("author") or {}
    guild_id = msg.get("guild_id")
    shaped = {
        "guild_id": str(guild_id) if guild_id is not None else None,
        "channel_id": str(msg.get("channel_id", "")),
        "message_id": str(msg.get("id", "")),
        "author_id": str(author.get("id", "")),
        "author_name": str(author.get("username", "")),
        "author_is_bot": bool(author.get("bot", False)),
        "content": message_text(msg),
        "timestamp": msg.get("timestamp"),
    }
    shaped.update(message_addressing(msg))
    return shaped


def _snowflake(value: object) -> str | None:
    """Coerce to a snowflake string; None if invalid (guards URL paths)."""
    text = str(value).strip() if value is not None else ""
    return text if text.isdigit() else None


class ToolExecutor:
    """Validates and executes tool calls. Sync — run via asyncio.to_thread."""

    def __init__(self, rest: RestLike, backstop: SendBackstop) -> None:
        self._rest = rest
        self._backstop = backstop

    def call(self, name: str, arguments: dict) -> tuple[dict, bool]:
        """Returns (payload, ok). Error payloads carry an 'error' string."""
        try:
            if name == "send_message":
                return self._send(arguments, reply=False)
            if name == "reply_message":
                return self._send(arguments, reply=True)
            if name == "read_history":
                return self._history(arguments)
            return ({"error": f"unknown tool: {name}"}, False)
        except DiscordRestError as exc:
            return ({"error": str(exc)}, False)

    def _send(self, arguments: dict, *, reply: bool) -> tuple[dict, bool]:
        channel_id = _snowflake(arguments.get("channel_id"))
        if channel_id is None:
            return ({"error": "channel_id must be a numeric snowflake string"}, False)
        reply_to: str | None = None
        if reply:
            reply_to = _snowflake(arguments.get("message_id"))
            if reply_to is None:
                return ({"error": "message_id must be a numeric snowflake string"}, False)
        content = arguments.get("content")
        if not isinstance(content, str) or not content.strip():
            return ({"error": "content must be a non-empty string"}, False)
        if len(content) > _MAX_CONTENT_LENGTH:
            return (
                {"error": f"content exceeds Discord's {_MAX_CONTENT_LENGTH}-character limit"},
                False,
            )
        wait = self._backstop.try_acquire(channel_id)
        if wait > 0:
            logger.warning(
                "send backstop hit for channel %s (max %d per %.0fs)",
                channel_id, self._backstop.max_sends, self._backstop.window_seconds,
            )
            return (
                {
                    "error": (
                        f"send backstop exceeded for channel {channel_id} "
                        f"(max {self._backstop.max_sends} sends per "
                        f"{self._backstop.window_seconds:.0f}s); retry in {wait:.1f}s"
                    )
                },
                False,
            )
        created = self._rest.create_message(channel_id, content, reply_to_message_id=reply_to)
        return ({"message": shape_message(created)}, True)

    def _history(self, arguments: dict) -> tuple[dict, bool]:
        channel_id = _snowflake(arguments.get("channel_id"))
        if channel_id is None:
            return ({"error": "channel_id must be a numeric snowflake string"}, False)
        limit_raw = arguments.get("limit", 50)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return ({"error": "limit must be an integer between 1 and 100"}, False)
        if not 1 <= limit <= 100:
            return ({"error": "limit must be an integer between 1 and 100"}, False)
        before: str | None = None
        if arguments.get("before") is not None:
            before = _snowflake(arguments.get("before"))
            if before is None:
                return ({"error": "before must be a numeric snowflake string"}, False)
        messages = self._rest.get_messages(channel_id, limit=limit, before=before)
        return ({"messages": [shape_message(m) for m in messages]}, True)
