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
                "mention_user_ids": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string"},
                    "description": "Exact Discord user IDs permitted to ping; all other mentions are inert.",
                },
            },
            "required": ["channel_id", "content"],
            "additionalProperties": False,
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
                "mention_user_ids": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string"},
                },
            },
            "required": ["channel_id", "message_id", "content"],
            "additionalProperties": False,
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
            "additionalProperties": False,
        },
    },
    {
        "name": "add_reaction",
        "description": "Add one reaction to an exact message in an allowed Discord channel.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "channel_id": {"type": "string"},
                "message_id": {"type": "string"},
                "reaction": {"type": "string", "maxLength": 256}
            },
            "required": ["channel_id", "message_id", "reaction"]
        }
    },
]

V2_TOOL_SCHEMAS = TOOL_SCHEMAS
TOOL_NAMES = frozenset(schema["name"] for schema in TOOL_SCHEMAS)
V2_TOOL_NAMES = TOOL_NAMES


class RestLike(Protocol):
    """The REST surface the executor needs (real client or test fake)."""

    def create_message(
        self,
        channel_id: str,
        content: str,
        *,
        reply_to_message_id: str | None = None,
        allowed_mention_user_ids: tuple[str, ...] | None = None,
        fail_if_reply_missing: bool = False,
    ) -> dict: ...

    def get_messages(
        self, channel_id: str, *, limit: int = 50, before: str | None = None
    ) -> list[dict]: ...

    def create_reaction(
        self, channel_id: str, message_id: str, reaction: str
    ) -> None: ...


def shape_message(msg: dict) -> dict:
    """Normalize an API message object to the notification field names."""
    if not isinstance(msg, dict):
        raise ValueError("Discord message result is invalid")
    message_id = _snowflake(msg.get("id"))
    channel_id = _snowflake(msg.get("channel_id"))
    author = msg.get("author")
    if (
        message_id is None
        or channel_id is None
        or not isinstance(author, dict)
        or _snowflake(author.get("id")) is None
        or not isinstance(author.get("username", ""), str)
        or not isinstance(author.get("bot", False), bool)
    ):
        raise ValueError("Discord message result is invalid")
    guild_id = msg.get("guild_id")
    if guild_id is not None and _snowflake(guild_id) is None:
        raise ValueError("Discord message result is invalid")
    shaped = {
        "guild_id": str(guild_id) if guild_id is not None else None,
        "channel_id": channel_id,
        "message_id": message_id,
        "author_id": str(author.get("id", "")),
        "author_name": str(author.get("username", "")),
        "author_is_bot": bool(author.get("bot", False)),
        "content": message_text(msg),
        "timestamp": msg.get("timestamp"),
    }
    shaped.update(message_addressing(msg))
    return shaped


def _snowflake(value: object) -> str | None:
    """Return an exact JSON snowflake string; never coerce another type."""
    return value if isinstance(value, str) and value.isdigit() else None


def _closed_arguments(
    arguments: dict,
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> bool:
    keys = set(arguments)
    return required.issubset(keys) and keys.issubset(required | optional)


class ToolExecutor:
    """Validates and executes tool calls. Sync — run via asyncio.to_thread."""

    def __init__(
        self,
        rest: RestLike,
        backstop: SendBackstop,
        *,
        allowed_channel_ids: frozenset[str],
    ) -> None:
        if (
            not isinstance(allowed_channel_ids, frozenset)
            or not allowed_channel_ids
            or any(_snowflake(value) != value for value in allowed_channel_ids)
        ):
            raise ValueError("Discord tool executor requires exact trusted channels")
        self._rest = rest
        self._backstop = backstop
        self._allowed_channel_ids = allowed_channel_ids

    def call(self, name: str, arguments: dict) -> tuple[dict, bool]:
        """Returns (payload, ok). Error payloads carry an 'error' string."""
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return ({"error": "tool call is invalid"}, False)
        try:
            if name == "send_message":
                return self._send(arguments, reply=False)
            if name == "reply_message":
                return self._send(arguments, reply=True)
            if name == "read_history":
                return self._history(arguments)
            if name == "add_reaction":
                return self._reaction(arguments)
            return ({"error": f"unknown tool: {name}"}, False)
        except DiscordRestError as exc:
            return (
                {
                    "error": (
                        f"Discord API request failed with status {exc.status}"
                        if exc.status is not None
                        else "Discord network request failed"
                    )
                },
                False,
            )
        except Exception:
            return ({"error": "Discord transport operation failed"}, False)

    def _send(self, arguments: dict, *, reply: bool) -> tuple[dict, bool]:
        required = {"channel_id", "content"}
        if reply:
            required.add("message_id")
        if not _closed_arguments(
            arguments,
            required=frozenset(required),
            optional=frozenset({"mention_user_ids"}),
        ):
            return ({"error": "message arguments do not match the closed tool contract"}, False)
        channel_id = _snowflake(arguments.get("channel_id"))
        if channel_id is None:
            return ({"error": "channel_id must be a numeric snowflake string"}, False)
        if channel_id not in self._allowed_channel_ids:
            return ({"error": "channel_id is outside the trusted allowlist"}, False)
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
        raw_mentions = arguments.get("mention_user_ids", [])
        if not isinstance(raw_mentions, list):
            return ({"error": "mention_user_ids must be an array of snowflake strings"}, False)
        mention_ids: list[str] = []
        seen_mentions: set[str] = set()
        for raw_id in raw_mentions:
            user_id = _snowflake(raw_id)
            if user_id is None:
                return ({"error": "mention_user_ids must contain snowflake strings"}, False)
            if user_id not in seen_mentions:
                seen_mentions.add(user_id)
                mention_ids.append(user_id)
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
        created = self._rest.create_message(
            channel_id,
            content,
            reply_to_message_id=reply_to,
            allowed_mention_user_ids=tuple(mention_ids),
            fail_if_reply_missing=reply,
        )
        return ({"message": shape_message(created)}, True)

    def _history(self, arguments: dict) -> tuple[dict, bool]:
        if not _closed_arguments(
            arguments,
            required=frozenset({"channel_id"}),
            optional=frozenset({"limit", "before"}),
        ):
            return ({"error": "history arguments do not match the closed tool contract"}, False)
        channel_id = _snowflake(arguments.get("channel_id"))
        if channel_id is None:
            return ({"error": "channel_id must be a numeric snowflake string"}, False)
        if channel_id not in self._allowed_channel_ids:
            return ({"error": "channel_id is outside the trusted allowlist"}, False)
        limit_raw = arguments.get("limit", 50)
        if isinstance(limit_raw, bool):
            return ({"error": "limit must be an integer between 1 and 100"}, False)
        if not isinstance(limit_raw, int):
            return ({"error": "limit must be an integer between 1 and 100"}, False)
        limit = limit_raw
        if not 1 <= limit <= 100:
            return ({"error": "limit must be an integer between 1 and 100"}, False)
        before: str | None = None
        if arguments.get("before") is not None:
            before = _snowflake(arguments.get("before"))
            if before is None:
                return ({"error": "before must be a numeric snowflake string"}, False)
        messages = self._rest.get_messages(channel_id, limit=limit, before=before)
        return ({"messages": [shape_message(m) for m in messages]}, True)

    def _reaction(self, arguments: dict) -> tuple[dict, bool]:
        if not _closed_arguments(
            arguments,
            required=frozenset({"channel_id", "message_id", "reaction"}),
        ):
            return ({"error": "reaction arguments do not match the closed tool contract"}, False)
        channel_id = _snowflake(arguments.get("channel_id"))
        message_id = _snowflake(arguments.get("message_id"))
        reaction = arguments.get("reaction")
        if channel_id is None or message_id is None:
            return ({"error": "channel_id and message_id must be numeric snowflake strings"}, False)
        if channel_id not in self._allowed_channel_ids:
            return ({"error": "channel_id is outside the trusted allowlist"}, False)
        if not isinstance(reaction, str) or not reaction or len(reaction) > 256:
            return ({"error": "reaction must be a non-empty string up to 256 characters"}, False)
        wait = self._backstop.try_acquire(channel_id)
        if wait > 0:
            return ({"error": "send backstop exceeded for channel"}, False)
        self._rest.create_reaction(channel_id, message_id, reaction)
        return ({"reaction": "sent", "message_id": message_id}, True)
