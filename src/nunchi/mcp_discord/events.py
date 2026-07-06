"""Message events and the MCP notification contract.

The load-bearing rule of this transport: a MESSAGE_CREATE is dropped if and
only if it was authored by our own bot user. Every other author — human or
bot — is delivered. No content filtering, no transformation, no gate logic.

Notification contract (any MCP harness can consume this):

    method: "notifications/discord/message"
    params:
        guild_id       str | None   (None for DMs)
        channel_id     str
        message_id     str
        author_id      str
        author_name    str
        author_is_bot  bool
        content        str
        timestamp      str | None   (ISO 8601, as sent by Discord)

Snowflake IDs are strings to survive JSON consumers with 53-bit numbers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("nunchi.mcp_discord.events")

NOTIFICATION_METHOD = "notifications/discord/message"


@dataclass(frozen=True)
class MessageEvent:
    """One inbound Discord message, normalized for the MCP surface."""

    guild_id: str | None
    channel_id: str
    message_id: str
    author_id: str
    author_name: str
    author_is_bot: bool
    content: str
    timestamp: str | None


def message_event_from_create(data: dict) -> MessageEvent:
    """Normalize a MESSAGE_CREATE dispatch payload."""
    author = data.get("author") or {}
    guild_id = data.get("guild_id")
    return MessageEvent(
        guild_id=str(guild_id) if guild_id is not None else None,
        channel_id=str(data.get("channel_id", "")),
        message_id=str(data.get("id", "")),
        author_id=str(author.get("id", "")),
        author_name=str(author.get("username", "")),
        author_is_bot=bool(author.get("bot", False)),
        content=data.get("content") or "",
        timestamp=data.get("timestamp"),
    )


def _looks_content_stripped(data: dict) -> bool:
    """Empty content with no embeds/attachments/etc is the signature of a
    missing MESSAGE_CONTENT intent (legitimately empty messages carry one of
    these)."""
    return not (
        data.get("embeds")
        or data.get("attachments")
        or data.get("components")
        or data.get("sticker_items")
        or data.get("poll")
    )


def filter_message_create(data: dict, own_user_id: str | None) -> MessageEvent | None:
    """Drop ONLY self-authored messages; warn loudly on stripped content.

    Returns None for self-authored messages (author.id == our bot user id).
    Bot-authored messages from other bots are delivered — that is the point
    of this transport. Messages with empty content are still delivered, but
    when the emptiness looks like a missing MESSAGE_CONTENT intent a WARNING
    is logged with the remediation step.
    """
    event = message_event_from_create(data)
    if own_user_id is not None and event.author_id == str(own_user_id):
        return None
    if not event.content and _looks_content_stripped(data):
        logger.warning(
            "MESSAGE_CREATE %s in channel %s arrived with empty content and no "
            "embeds/attachments — the MESSAGE_CONTENT privileged intent is "
            "probably not enabled for this bot. Enable 'MESSAGE CONTENT INTENT' "
            "in the Discord Developer Portal (Bot -> Privileged Gateway Intents). "
            "Delivering the notification with empty content.",
            event.message_id,
            event.channel_id,
        )
    return event


def notification_params(event: MessageEvent) -> dict:
    """The exact params object for notifications/discord/message."""
    return {
        "guild_id": event.guild_id,
        "channel_id": event.channel_id,
        "message_id": event.message_id,
        "author_id": event.author_id,
        "author_name": event.author_name,
        "author_is_bot": event.author_is_bot,
        "content": event.content,
        "timestamp": event.timestamp,
    }
