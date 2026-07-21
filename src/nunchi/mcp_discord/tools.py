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
import json
from typing import Callable, Protocol

from .events import message_addressing, message_text
from .continuation import DiscordHistoryContinuations
from .ratelimit import SendBackstop
from .rest import DiscordRestError

logger = logging.getLogger("nunchi.mcp_discord.tools")

_MAX_CONTENT_LENGTH = 2000  # Discord's message content limit

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "subscribe_events",
        "description": (
            "Register this authenticated MCP session for the exact process-bound "
            "participant/room stream and return the backfill/live barrier."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
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
            "properties": {
                "channel_id": {"type": "string", "description": "Target channel snowflake ID."},
                "request_id": {"type": "string", "description": "Immutable V2 action correlation ID."},
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
            "required": ["request_id", "channel_id", "content"],
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
                "request_id": {"type": "string", "description": "Immutable V2 action correlation ID."},
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
            "required": ["request_id", "channel_id", "message_id", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_history",
        "description": (
            "Fetch one bounded, participant/room/trigger-bound I-010D page."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "handle_id": {"type": "string"},
                "direction": {"const": "before"},
                "max_events": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                },
                "max_bytes": {"type": "integer", "minimum": 1},
                "anchor_event_id": {"type": "string"},
                "cursor": {
                    "type": "string",
                    "description": "Opaque continuation cursor from a prior page.",
                },
            },
            "required": ["request_id", "handle_id", "direction", "max_events", "max_bytes"],
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
                "request_id": {"type": "string"},
                "message_id": {"type": "string"},
                "reaction": {"type": "string", "maxLength": 256}
            },
            "required": ["request_id", "channel_id", "message_id", "reaction"]
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
        nonce: str | None = None,
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
    mentions_room = msg.get("mention_everyone", False)
    timestamp = msg.get("timestamp")
    mentions = msg.get("mentions", [])
    reference = msg.get("message_reference")
    referenced = msg.get("referenced_message")
    if (
        (guild_id is not None and _snowflake(guild_id) is None)
        or not isinstance(mentions_room, bool)
        or (timestamp is not None and not isinstance(timestamp, str))
        or not isinstance(mentions, list)
        or any(
            not isinstance(mention, dict)
            or _snowflake(mention.get("id")) is None
            for mention in mentions
        )
        or (reference is not None and not isinstance(reference, dict))
        or (
            isinstance(reference, dict)
            and reference.get("message_id") is not None
            and _snowflake(reference.get("message_id")) is None
        )
        or (referenced is not None and not isinstance(referenced, dict))
    ):
        raise ValueError("Discord message result is invalid")
    if isinstance(referenced, dict):
        referenced_author = referenced.get("author")
        if (
            _snowflake(referenced.get("id")) is None
            or (
                referenced_author is not None
                and (
                    not isinstance(referenced_author, dict)
                    or _snowflake(referenced_author.get("id")) is None
                    or not isinstance(referenced_author.get("username", ""), str)
                    or not isinstance(referenced_author.get("bot", False), bool)
                )
            )
        ):
            raise ValueError("Discord message result is invalid")
    shaped = {
        "guild_id": guild_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "author_id": author["id"],
        "author_name": author.get("username", ""),
        "author_is_bot": author.get("bot", False),
        "content": message_text(msg),
        "timestamp": timestamp,
        "mentions_room": mentions_room,
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
        action_claim: Callable[[str], None] | None = None,
        continuations: DiscordHistoryContinuations | None = None,
    ) -> None:
        if (
            not isinstance(allowed_channel_ids, frozenset)
            or len(allowed_channel_ids) != 1
            or any(_snowflake(value) != value for value in allowed_channel_ids)
            or not callable(action_claim)
            or not isinstance(continuations, DiscordHistoryContinuations)
        ):
            raise ValueError(
                "Discord tool executor requires one exact trusted room and durable action claims"
            )
        self._rest = rest
        self._backstop = backstop
        self._allowed_channel_ids = allowed_channel_ids
        self._channel_id = next(iter(allowed_channel_ids))
        self._action_claim = action_claim
        self._continuations = continuations

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

    def bootstrap_history(
        self,
        *,
        max_events: int = 100,
        max_bytes: int = 32768,
    ) -> dict:
        """Return bounded startup history after the live session is registered.

        This is deliberately not a standalone room-controlled tool.  The MCP
        binding invokes it only as part of ``subscribe_events``, after the
        session has entered the live registry, closing the backfill/live race.
        Participant-requested expansion remains exclusively I-010D-bound via
        ``read_history``.
        """
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
            or not 1 <= max_events <= 100
            or isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or not 1 <= max_bytes <= 32768
        ):
            raise ValueError("bootstrap history budget is invalid")
        messages = self._rest.get_messages(
            self._channel_id,
            limit=max_events,
        )
        selected: list[dict] = []
        total_bytes = 0
        for raw in messages:
            message = shape_message(raw)
            if message["channel_id"] != self._channel_id:
                raise ValueError("Discord history response crossed the bound room")
            encoded_size = len(
                json.dumps(
                    message,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if total_bytes + encoded_size > max_bytes:
                break
            selected.append(message)
            total_bytes += encoded_size
        return {
            "messages": selected,
            "coverage": {
                "max_events": max_events,
                "max_bytes": max_bytes,
                "returned_events": len(selected),
                "returned_bytes": total_bytes,
                "truncated": len(selected) < len(messages),
            },
        }

    def _send(self, arguments: dict, *, reply: bool) -> tuple[dict, bool]:
        required = {"request_id", "channel_id", "content"}
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
        request_id = arguments.get("request_id")
        if (
            not isinstance(request_id, str)
            or not request_id
            or len(request_id) > 512
        ):
            return ({"error": "request_id must be a non-empty V2 correlation ID"}, False)
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
        try:
            assert self._action_claim is not None
            self._action_claim(request_id)
        except Exception:
            return ({"error": "request_id was already consumed or could not be reserved"}, False)
        created = self._rest.create_message(
            channel_id,
            content,
            reply_to_message_id=reply_to,
            allowed_mention_user_ids=tuple(mention_ids),
            fail_if_reply_missing=reply,
            nonce=request_id,
        )
        shaped = shape_message(created)
        if shaped["channel_id"] != channel_id:
            return ({"error": "Discord response crossed the bound room"}, False)
        return ({"request_id": request_id, "message": shaped}, True)

    def _history(self, arguments: dict) -> tuple[dict, bool]:
        try:
            assert self._continuations is not None
            handle, before = self._continuations.verify_request(arguments)
        except Exception:
            return ({"error": "history continuation request is invalid"}, False)
        limit = arguments["max_events"]
        messages = self._rest.get_messages(
            self._channel_id,
            limit=limit,
            before=before,
        )
        shaped = [shape_message(message) for message in messages]
        if any(message["channel_id"] != self._channel_id for message in shaped):
            return ({"error": "Discord history response crossed the bound room"}, False)
        selected_newest_first: list[dict] = []
        total_bytes = 0
        truncated_by_bytes = False
        for message in shaped:
            event = self._history_event(message)
            event_bytes = len(
                json.dumps(
                    event,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if total_bytes + event_bytes > arguments["max_bytes"]:
                truncated_by_bytes = True
                break
            selected_newest_first.append(message)
            total_bytes += event_bytes
        if messages and not selected_newest_first:
            return ({"error": "history byte budget cannot admit one event"}, False)
        events = [
            self._history_event(message)
            for message in reversed(selected_newest_first)
        ]
        actors: dict[str, dict] = {}
        for event, message in zip(events, reversed(selected_newest_first)):
            actors[event["author_id"]] = {
                "display_name": message["author_name"],
                "kind": "bot" if message["author_is_bot"] else "human",
            }
            for actor_id in event["mentioned_actor_ids"]:
                actors.setdefault(actor_id, {})
        has_more = truncated_by_bytes or len(messages) == limit
        page = {
            "request_id": arguments["request_id"],
            "handle_id": arguments["handle_id"],
            "room_id": self._channel_id,
            "continuity_scope_id": handle["continuity_scope_id"],
            "direction": "before",
            "anchor_event_id": handle["trigger_event_id"],
            "actors": actors,
            "events": events,
            "coverage": {
                "has_more_before": has_more,
                "has_more_after": None,
                "has_gaps": False,
                "truncated_by": ["bytes"] if truncated_by_bytes else [],
                "continuity": "restart-safe",
                "has_restart_gap": False,
                "max_events": arguments["max_events"],
                "max_bytes": arguments["max_bytes"],
            },
        }
        if has_more and selected_newest_first:
            page["next_cursor"] = self._continuations.cursor(
                arguments["handle_id"],
                selected_newest_first[-1]["message_id"],
            )
        return (page, True)

    @staticmethod
    def _history_event(message: dict) -> dict:
        event = {
            "id": f"discord:message:{message['message_id']}",
            "type": "message",
            "author_id": f"discord:user:{message['author_id']}",
            "text": message["content"],
            "mentioned_actor_ids": [
                f"discord:user:{user_id}"
                for user_id in message["mentioned_user_ids"]
            ],
            "mentions_room": message["mentions_room"],
        }
        if message["timestamp"]:
            event["timestamp"] = message["timestamp"]
        if message["reply_to_message_id"]:
            event["reply_to_event_id"] = (
                f"discord:message:{message['reply_to_message_id']}"
            )
        return event

    def _reaction(self, arguments: dict) -> tuple[dict, bool]:
        if not _closed_arguments(
            arguments,
            required=frozenset({"request_id", "channel_id", "message_id", "reaction"}),
        ):
            return ({"error": "reaction arguments do not match the closed tool contract"}, False)
        channel_id = _snowflake(arguments.get("channel_id"))
        message_id = _snowflake(arguments.get("message_id"))
        reaction = arguments.get("reaction")
        if channel_id is None or message_id is None:
            return ({"error": "channel_id and message_id must be numeric snowflake strings"}, False)
        if channel_id not in self._allowed_channel_ids:
            return ({"error": "channel_id is outside the trusted allowlist"}, False)
        request_id = arguments.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 512:
            return ({"error": "request_id must be a non-empty V2 correlation ID"}, False)
        if not isinstance(reaction, str) or not reaction or len(reaction) > 256:
            return ({"error": "reaction must be a non-empty string up to 256 characters"}, False)
        wait = self._backstop.try_acquire(channel_id)
        if wait > 0:
            return ({"error": "send backstop exceeded for channel"}, False)
        try:
            assert self._action_claim is not None
            self._action_claim(request_id)
        except Exception:
            return ({"error": "request_id was already consumed or could not be reserved"}, False)
        self._rest.create_reaction(channel_id, message_id, reaction)
        return (
            {
                "request_id": request_id,
                "channel_id": channel_id,
                "reaction": "sent",
                "message_id": message_id,
            },
            True,
        )
