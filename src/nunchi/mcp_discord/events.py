"""Message events and the MCP notification contract.

The load-bearing rule of this transport: a MESSAGE_CREATE is dropped if and
only if it was authored by our own bot user. Every other author — human or
bot — is delivered. Plain Discord content is preserved; rich-only messages
get a tagged text fallback from embeds/components/attachments so downstream
admission does not mistake visible peer speech for an empty event. There is no
gate logic in this transport.

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
from typing import Any

logger = logging.getLogger("nunchi.mcp_discord.events")

NOTIFICATION_METHOD = "notifications/discord/message"
_MAX_NORMALIZED_CONTENT = 6000


def _append_text(parts: list[str], seen: set[str], value: Any, *, prefix: str = "") -> None:
    if not isinstance(value, str):
        return
    text = value.strip()
    if not text:
        return
    rendered = f"{prefix}{text}" if prefix else text
    if rendered not in seen:
        seen.add(rendered)
        parts.append(rendered)


def _component_text(component: Any, parts: list[str], seen: set[str]) -> None:
    if not isinstance(component, dict):
        return
    # Components V2 Text Display. Button labels are interaction chrome, not
    # conversational content, so they are intentionally excluded.
    if component.get("type") == 10:
        _append_text(parts, seen, component.get("content"))
    for child in component.get("components") or []:
        _component_text(child, parts, seen)


def message_text(data: dict) -> str:
    """Return plain content or a bounded text rendering of a rich-only message."""
    content = data.get("content")
    if isinstance(content, str) and content.strip():
        return content

    parts: list[str] = []
    seen: set[str] = set()
    for embed in data.get("embeds") or []:
        if not isinstance(embed, dict):
            continue
        author = embed.get("author") or {}
        _append_text(parts, seen, author.get("name") if isinstance(author, dict) else None)
        _append_text(parts, seen, embed.get("title"))
        _append_text(parts, seen, embed.get("description"))
        for field in embed.get("fields") or []:
            if not isinstance(field, dict):
                continue
            name = field.get("name") if isinstance(field.get("name"), str) else ""
            value = field.get("value")
            _append_text(parts, seen, value, prefix=f"{name.strip()}: " if name.strip() else "")
        footer = embed.get("footer") or {}
        _append_text(parts, seen, footer.get("text") if isinstance(footer, dict) else None)

    for component in data.get("components") or []:
        _component_text(component, parts, seen)

    for attachment in data.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        description = attachment.get("description")
        if isinstance(description, str) and description.strip():
            _append_text(parts, seen, description, prefix="[attachment] ")
        else:
            _append_text(parts, seen, attachment.get("filename"), prefix="[attachment] ")

    for sticker in data.get("sticker_items") or []:
        if isinstance(sticker, dict):
            _append_text(parts, seen, sticker.get("name"), prefix="[sticker] ")

    poll = data.get("poll") or {}
    if isinstance(poll, dict):
        question = poll.get("question") or {}
        if isinstance(question, dict):
            _append_text(parts, seen, question.get("text"), prefix="[poll] ")
        for answer in poll.get("answers") or []:
            media = answer.get("poll_media") if isinstance(answer, dict) else None
            if isinstance(media, dict):
                _append_text(parts, seen, media.get("text"), prefix="- ")

    if not parts:
        return ""
    rendered = "[Discord rich message]\n" + "\n".join(parts)
    if len(rendered) > _MAX_NORMALIZED_CONTENT:
        rendered = rendered[: _MAX_NORMALIZED_CONTENT - 3].rstrip() + "..."
    return rendered


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
        content=message_text(data),
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
