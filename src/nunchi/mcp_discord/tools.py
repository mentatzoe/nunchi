"""MCP tool contract: schemas and the executor (import-safe, no SDK).

Tool schemas are plain JSON-Schema dicts so any harness (and the token
hygiene test) can serialize them without the mcp SDK installed. The
:class:`ToolExecutor` validates arguments, enforces the send backstop, and
calls the REST client; :mod:`._binding` wraps it for the SDK.

Message-shaped results reuse the notification field names
(message_id/author_id/...), so a harness handles one shape everywhere.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Protocol

from .events import message_addressing, message_text
from .authorization import ToolAuthorizer
from .ratelimit import SendBackstop
from .rest import DiscordRestError

logger = logging.getLogger("nunchi.mcp_discord.tools")

_MAX_CONTENT_LENGTH = 2000  # Discord's message content limit

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "register_participant",
        "description": (
            "Authenticate this MCP session for one exact Nunchi V2 "
            "participant/channel route before notifications or tools are available."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "participant_id": {"type": "string"},
                "channel_id": {"type": "string"},
                "_nunchi_authorization": {"type": "object"},
            },
            "required": [
                "participant_id",
                "channel_id",
                "_nunchi_authorization",
            ],
        },
    },
    {
        "name": "send_message",
        "description": (
            "Send a message to a Discord channel. Content is posted verbatim "
            "(no transformation). Subject to a per-channel send backstop."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "channel_id": {"type": "string", "description": "Target channel snowflake ID."},
                "content": {
                    "type": "string",
                    "maxLength": _MAX_CONTENT_LENGTH,
                    "description": "Message text (max 2000 chars).",
                },
                "_nunchi_authorization": {"type": "object"},
            },
            "required": ["channel_id", "content", "_nunchi_authorization"],
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
            "additionalProperties": False,
            "properties": {
                "channel_id": {"type": "string", "description": "Channel snowflake ID."},
                "message_id": {"type": "string", "description": "Message snowflake ID to reply to."},
                "content": {
                    "type": "string",
                    "maxLength": _MAX_CONTENT_LENGTH,
                    "description": "Reply text (max 2000 chars).",
                },
                "_nunchi_authorization": {"type": "object"},
            },
            "required": ["channel_id", "message_id", "content", "_nunchi_authorization"],
        },
    },
    {
        "name": "add_reaction",
        "description": "Add this bot's reaction to one message through a one-use V2 host authorization.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "channel_id": {"type": "string"},
                "message_id": {"type": "string"},
                "reaction": {"type": "string"},
                "_nunchi_authorization": {"type": "object"},
            },
            "required": ["channel_id", "message_id", "reaction", "_nunchi_authorization"],
        },
    },
    {
        "name": "remove_reaction",
        "description": "Remove this bot's own reaction through a one-use V2 host authorization.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "channel_id": {"type": "string"},
                "message_id": {"type": "string"},
                "reaction": {"type": "string"},
                "_nunchi_authorization": {"type": "object"},
            },
            "required": ["channel_id", "message_id", "reaction", "_nunchi_authorization"],
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
            "additionalProperties": False,
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
                "_nunchi_authorization": {"type": "object"},
            },
            "required": ["channel_id", "_nunchi_authorization"],
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

    def add_reaction(self, channel_id: str, message_id: str, reaction: str) -> None: ...

    def remove_reaction(self, channel_id: str, message_id: str, reaction: str) -> None: ...


def shape_message(msg: object) -> dict:
    """Normalize an API message object to the notification field names."""
    data = dict(msg) if isinstance(msg, Mapping) else {}
    raw_author = data.get("author")
    author = raw_author if isinstance(raw_author, Mapping) else {}
    guild_id = data.get("guild_id")
    shaped = {
        "guild_id": str(guild_id) if guild_id is not None else None,
        "channel_id": str(data.get("channel_id", "")),
        "message_id": str(data.get("id", "")),
        "author_id": str(author.get("id", "")),
        "author_name": str(author.get("username", "")),
        "author_is_bot": bool(author.get("bot", False)),
        "content": message_text(data),
        "timestamp": data.get("timestamp"),
    }
    shaped.update(message_addressing(data))
    return shaped


def _snowflake(value: object) -> str | None:
    """Coerce to a snowflake string; None if invalid (guards URL paths)."""
    text = str(value).strip() if value is not None else ""
    return text if text.isdigit() else None


def _unknown_delivery(detail: str) -> tuple[dict, bool]:
    """Return a successful tool envelope whose native outcome is uncertain."""
    return (
        {
            "delivery": {
                "status": "unknown",
                "detail": detail,
            }
        },
        True,
    )


def _effect_failure_is_definitive(exc: DiscordRestError) -> bool:
    """Whether Discord explicitly rejected an effect without accepting it."""
    return isinstance(exc.status, int) and 400 <= exc.status < 500


def _message_acknowledgement_is_shapable(data: Mapping) -> bool:
    """Whether fields used for target attestation have trustworthy types."""
    author = data.get("author")
    if not isinstance(author, Mapping):
        return False
    if not isinstance(data.get("content"), str):
        return False
    mentions = data.get("mentions", [])
    if not isinstance(mentions, list) or not all(
        isinstance(item, Mapping) for item in mentions
    ):
        return False
    reference = data.get("message_reference")
    if reference is not None and not isinstance(reference, Mapping):
        return False
    referenced = data.get("referenced_message")
    if referenced is not None and not isinstance(referenced, Mapping):
        return False
    if isinstance(referenced, Mapping):
        referenced_author = referenced.get("author")
        if referenced_author is not None and not isinstance(
            referenced_author,
            Mapping,
        ):
            return False
    return True


class ToolExecutor:
    """Validates and executes tool calls. Sync — run via asyncio.to_thread."""

    def __init__(
        self,
        rest: RestLike,
        backstop: SendBackstop,
        *,
        authorizer: ToolAuthorizer,
    ) -> None:
        self._rest = rest
        self._backstop = backstop
        self._authorizer = authorizer

    def call(
        self,
        name: str,
        arguments: dict,
        *,
        expected_route: tuple[str, str] | None = None,
        expected_self_actor_id: str | None = None,
    ) -> tuple[dict, bool]:
        """Returns (payload, ok). Error payloads carry an 'error' string."""
        try:
            if not isinstance(arguments, dict):
                return ({"error": "tool arguments must be an object"}, False)
            expected_author_id = (
                expected_self_actor_id.removeprefix("discord:actor:")
                if (
                    isinstance(expected_self_actor_id, str)
                    and expected_self_actor_id.startswith("discord:actor:")
                    and expected_self_actor_id.removeprefix(
                        "discord:actor:"
                    ).isdigit()
                )
                else None
            )
            if name in {
                "send_message",
                "reply_message",
                "add_reaction",
                "remove_reaction",
            } and expected_author_id is None:
                return (
                    {"error": "authenticated Discord self identity is unavailable"},
                    False,
                )
            supplied = dict(arguments)
            authorization = supplied.pop("_nunchi_authorization", None)
            ok, error = self._authorizer.verify(
                authorization=authorization,
                tool=name,
                arguments=supplied,
                expected_participant_id=(
                    expected_route[0] if expected_route is not None else None
                ),
                expected_room_id=(
                    expected_route[1] if expected_route is not None else None
                ),
            )
            if not ok:
                return ({"error": error}, False)
            arguments = supplied
            if name == "send_message":
                return self._send(
                    arguments,
                    reply=False,
                    expected_author_id=expected_author_id,
                )
            if name == "reply_message":
                return self._send(
                    arguments,
                    reply=True,
                    expected_author_id=expected_author_id,
                )
            if name == "add_reaction":
                return self._reaction(arguments, remove=False)
            if name == "remove_reaction":
                return self._reaction(arguments, remove=True)
            if name == "read_history":
                return self._history(arguments)
            return ({"error": f"unknown tool: {name}"}, False)
        except DiscordRestError as exc:
            return ({"error": str(exc)}, False)

    def _reaction(self, arguments: dict, *, remove: bool) -> tuple[dict, bool]:
        channel_id = _snowflake(arguments.get("channel_id"))
        message_id = _snowflake(arguments.get("message_id"))
        reaction = arguments.get("reaction")
        if channel_id is None or message_id is None:
            return ({"error": "channel_id and message_id must be numeric snowflakes"}, False)
        if not isinstance(reaction, str) or not reaction.strip() or len(reaction) > 100:
            return ({"error": "reaction must be a non-empty bounded string"}, False)
        wait = self._backstop.try_acquire(channel_id)
        if wait > 0:
            return ({"error": f"send backstop exceeded; retry in {wait:.1f}s"}, False)
        try:
            if remove:
                self._rest.remove_reaction(channel_id, message_id, reaction)
            else:
                self._rest.add_reaction(channel_id, message_id, reaction)
        except DiscordRestError as exc:
            if _effect_failure_is_definitive(exc):
                raise
            return _unknown_delivery(
                "Discord reaction acknowledgement was lost or untrustworthy"
            )
        except Exception:
            return _unknown_delivery(
                "Discord reaction acknowledgement was lost or untrustworthy"
            )
        return (
            {
                "reaction": {
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "reaction": reaction,
                    "operation": "remove" if remove else "add",
                }
            },
            True,
        )

    def _send(
        self,
        arguments: dict,
        *,
        reply: bool,
        expected_author_id: str,
    ) -> tuple[dict, bool]:
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
        try:
            created = self._rest.create_message(
                channel_id,
                content,
                reply_to_message_id=reply_to,
            )
        except DiscordRestError as exc:
            if _effect_failure_is_definitive(exc):
                raise
            return _unknown_delivery(
                "Discord create-message acknowledgement was lost or untrustworthy"
            )
        except Exception:
            return _unknown_delivery(
                "Discord create-message acknowledgement was lost or untrustworthy"
            )
        try:
            created_data = dict(created) if isinstance(created, Mapping) else {}
            if not _message_acknowledgement_is_shapable(created_data):
                return _unknown_delivery(
                    "Discord create-message acknowledgement was malformed"
                )
            created_id = _snowflake(created_data.get("id"))
            created_channel = _snowflake(created_data.get("channel_id"))
            author = created_data["author"]
            author_id = _snowflake(author.get("id"))
            shaped = shape_message(created_data)
            acknowledged_reply = shaped.get("reply_to_message_id")
        except Exception:
            return _unknown_delivery(
                "Discord create-message acknowledgement was malformed"
            )
        if (
            created_id is None
            or created_channel != channel_id
            or author_id != expected_author_id
            or author.get("bot") is not True
            or shaped.get("content") != content
            or acknowledged_reply != reply_to
        ):
            return _unknown_delivery(
                "Discord create-message acknowledgement lacked "
                "target-attested message identity"
            )
        return ({"message": shaped}, True)

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
