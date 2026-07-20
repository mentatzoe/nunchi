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
        mentioned_user_ids     list[str]
        reply_to_message_id    str | None
        reply_to_author_id     str | None
        reply_to_author_name   str | None
        reply_to_author_is_bot bool | None
        reply_to_content       str | None

Snowflake IDs are strings to survive JSON consumers with 53-bit numbers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("nunchi.mcp_discord.events")

NOTIFICATION_METHOD = "notifications/discord/message"
V2_NOTIFICATION_METHOD = "notifications/nunchi/v2/discord/event"
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


def message_addressing(data: dict) -> dict[str, Any]:
    """Normalize Discord mentions and reply context without changing content."""
    mentioned_user_ids: list[str] = []
    seen: set[str] = set()
    for mention in data.get("mentions") or []:
        if not isinstance(mention, dict):
            continue
        user_id = str(mention.get("id") or "").strip()
        if user_id.isdigit() and user_id not in seen:
            seen.add(user_id)
            mentioned_user_ids.append(user_id)

    reference = data.get("message_reference") or {}
    if not isinstance(reference, dict):
        reference = {}
    referenced = data.get("referenced_message")
    if not isinstance(referenced, dict):
        referenced = None
    referenced_author = referenced.get("author") if referenced else None
    if not isinstance(referenced_author, dict):
        referenced_author = None

    reply_to_message_id = reference.get("message_id")
    if reply_to_message_id is None and referenced is not None:
        reply_to_message_id = referenced.get("id")

    reply_author_id = (
        str(referenced_author.get("id") or "").strip()
        if referenced_author is not None
        else ""
    )
    reply_author_name = (
        str(referenced_author.get("username") or "").strip()
        if referenced_author is not None
        else ""
    )
    return {
        "mentioned_user_ids": mentioned_user_ids,
        "reply_to_message_id": (
            str(reply_to_message_id) if reply_to_message_id is not None else None
        ),
        "reply_to_author_id": reply_author_id or None,
        "reply_to_author_name": reply_author_name or None,
        "reply_to_author_is_bot": (
            bool(referenced_author.get("bot", False))
            if referenced_author is not None
            else None
        ),
        "reply_to_content": message_text(referenced) if referenced is not None else None,
    }


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
    mentioned_user_ids: tuple[str, ...]
    reply_to_message_id: str | None
    reply_to_author_id: str | None
    reply_to_author_name: str | None
    reply_to_author_is_bot: bool | None
    reply_to_content: str | None
    mentions_room: bool = False
    thread_root_message_id: str | None = None


@dataclass(frozen=True)
class ReactionEvent:
    """One gateway reaction event with transport-owned sequence identity."""

    guild_id: str | None
    channel_id: str
    message_id: str
    author_id: str
    author_name: str
    author_is_bot: bool | None
    reaction: str
    operation: str
    gateway_session_id: str
    gateway_sequence: int


def message_event_from_create(data: dict) -> MessageEvent:
    """Normalize a MESSAGE_CREATE dispatch payload."""
    author = data.get("author") or {}
    guild_id = data.get("guild_id")
    addressing = message_addressing(data)
    return MessageEvent(
        guild_id=str(guild_id) if guild_id is not None else None,
        channel_id=str(data.get("channel_id", "")),
        message_id=str(data.get("id", "")),
        author_id=str(author.get("id", "")),
        author_name=str(author.get("username", "")),
        author_is_bot=bool(author.get("bot", False)),
        content=message_text(data),
        timestamp=data.get("timestamp"),
        mentioned_user_ids=tuple(addressing["mentioned_user_ids"]),
        reply_to_message_id=addressing["reply_to_message_id"],
        reply_to_author_id=addressing["reply_to_author_id"],
        reply_to_author_name=addressing["reply_to_author_name"],
        reply_to_author_is_bot=addressing["reply_to_author_is_bot"],
        reply_to_content=addressing["reply_to_content"],
        mentions_room=bool(data.get("mention_everyone", False)),
        # Discord MESSAGE_CREATE does not ordinarily expose a thread root. A
        # trusted wrapper may supply one when it has channel/thread metadata;
        # absence remains honest unavailability.
        thread_root_message_id=(
            str(data["thread_root_message_id"])
            if data.get("thread_root_message_id") is not None
            else None
        ),
    )


def reaction_event_from_dispatch(
    data: dict,
    *,
    operation: str,
    gateway_session_id: str | None,
    gateway_sequence: int | None,
) -> ReactionEvent | None:
    """Normalize a Discord reaction dispatch or return unavailable honestly."""
    if operation not in ("add", "remove"):
        return None
    if not isinstance(gateway_session_id, str) or not gateway_session_id:
        return None
    if isinstance(gateway_sequence, bool) or not isinstance(gateway_sequence, int):
        return None
    emoji = data.get("emoji") or {}
    if not isinstance(emoji, dict):
        return None
    emoji_name = emoji.get("name")
    if not isinstance(emoji_name, str) or not emoji_name:
        return None
    emoji_id = _snowflake(emoji.get("id"))
    reaction = f"{emoji_name}:{emoji_id}" if emoji_id is not None else emoji_name
    member = data.get("member") or {}
    user = member.get("user") if isinstance(member, dict) else None
    if not isinstance(user, dict):
        user = {}
    author_name = user.get("username")
    return ReactionEvent(
        guild_id=(str(data["guild_id"]) if data.get("guild_id") is not None else None),
        channel_id=str(data.get("channel_id", "")),
        message_id=str(data.get("message_id", "")),
        author_id=str(data.get("user_id", "")),
        author_name=author_name if isinstance(author_name, str) else "",
        author_is_bot=(bool(user.get("bot")) if "bot" in user else None),
        reaction=reaction,
        operation=operation,
        gateway_session_id=gateway_session_id,
        gateway_sequence=gateway_sequence,
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


def filter_message_create(
    data: dict,
    own_user_id: str | None,
    *,
    retain_self: bool = False,
) -> MessageEvent | None:
    """Drop ONLY self-authored messages; warn loudly on stripped content.

    Returns None for self-authored messages (author.id == our bot user id).
    Bot-authored messages from other bots are delivered — that is the point
    of this transport. Messages with empty content are still delivered, but
    when the emptiness looks like a missing MESSAGE_CONTENT intent a WARNING
    is logged with the remediation step.
    """
    event = message_event_from_create(data)
    if (
        not retain_self
        and own_user_id is not None
        and event.author_id == str(own_user_id)
    ):
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
        "mentioned_user_ids": list(event.mentioned_user_ids),
        "reply_to_message_id": event.reply_to_message_id,
        "reply_to_author_id": event.reply_to_author_id,
        "reply_to_author_name": event.reply_to_author_name,
        "reply_to_author_is_bot": event.reply_to_author_is_bot,
        "reply_to_content": event.reply_to_content,
    }


def _snowflake(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if text.isdigit() else None


def _discord_actor_id(user_id: str) -> str:
    return f"discord:user:{user_id}"


def _discord_message_id(message_id: str) -> str:
    return f"discord:message:{message_id}"


class DiscordEventSourceV2:
    """Trusted I-050A message projection for an exact channel allowlist.

    Construction binds routing policy outside room content.  ``native_input``
    returns the closed input accepted by :class:`ObservationProvider`; display
    names are descriptive actor facts only and never identity or authority.
    """

    def __init__(
        self,
        *,
        allowed_channel_ids: frozenset[str],
        blocked_actor_ids: frozenset[str] = frozenset(),
    ) -> None:
        if not isinstance(allowed_channel_ids, frozenset) or not allowed_channel_ids:
            raise ValueError("Discord V2 requires a non-empty trusted channel allowlist")
        if any(_snowflake(value) != value for value in allowed_channel_ids):
            raise ValueError("Discord channel allowlist must contain exact snowflake strings")
        if not isinstance(blocked_actor_ids, frozenset) or any(
            _snowflake(value) != value for value in blocked_actor_ids
        ):
            raise ValueError("Discord blocked actors must be exact snowflake strings")
        self.allowed_channel_ids = allowed_channel_ids
        self.blocked_actor_ids = blocked_actor_ids

    @staticmethod
    def _unroutable(delivery_id: str, reason: str) -> dict:
        return {
            "delivery_id": delivery_id,
            "disposition": "unroutable",
            "reason": reason,
        }

    def native_input(self, event: MessageEvent | ReactionEvent) -> dict:
        if isinstance(event, ReactionEvent):
            return self._reaction_native_input(event)
        if not isinstance(event, MessageEvent):
            raise TypeError("Discord event source requires a transport event")
        raw_delivery = f"discord:message:{event.message_id or 'unavailable'}"
        message_id = _snowflake(event.message_id)
        channel_id = _snowflake(event.channel_id)
        author_id = _snowflake(event.author_id)
        if message_id is None or channel_id is None or author_id is None:
            return self._unroutable(
                raw_delivery,
                "Discord delivery lacked an exact native message, channel, or author ID",
            )
        delivery_id = _discord_message_id(message_id)
        if channel_id not in self.allowed_channel_ids:
            return self._unroutable(
                delivery_id,
                "Discord channel is outside the trusted routing allowlist",
            )
        if author_id in self.blocked_actor_ids:
            return self._unroutable(
                delivery_id,
                "Discord actor is outside the trusted routing policy",
            )

        mentioned_ids: list[str] = []
        seen_mentions: set[str] = set()
        for raw_id in event.mentioned_user_ids:
            mention_id = _snowflake(raw_id)
            if mention_id is None:
                return self._unroutable(
                    delivery_id,
                    "Discord delivery carried a malformed native mention ID",
                )
            actor_id = _discord_actor_id(mention_id)
            if actor_id not in seen_mentions:
                seen_mentions.add(actor_id)
                mentioned_ids.append(actor_id)

        portable_event: dict[str, Any] = {
            "id": delivery_id,
            "type": "message",
            "author_id": _discord_actor_id(author_id),
            "text": event.content,
            "mentioned_actor_ids": mentioned_ids,
            "mentions_room": event.mentions_room,
        }
        if isinstance(event.timestamp, str) and event.timestamp:
            portable_event["timestamp"] = event.timestamp
        if event.reply_to_message_id is not None:
            reply_id = _snowflake(event.reply_to_message_id)
            if reply_id is None:
                return self._unroutable(
                    delivery_id,
                    "Discord delivery carried a malformed native reply ID",
                )
            portable_event["reply_to_event_id"] = _discord_message_id(reply_id)
        if event.thread_root_message_id is not None:
            thread_root_id = _snowflake(event.thread_root_message_id)
            if thread_root_id is None:
                return self._unroutable(
                    delivery_id,
                    "Discord delivery carried a malformed native thread root ID",
                )
            portable_event["thread_root_event_id"] = _discord_message_id(thread_root_id)

        actors: dict[str, dict[str, Any]] = {
            _discord_actor_id(author_id): {
                "display_name": event.author_name,
                "kind": "bot" if event.author_is_bot else "human",
            }
        }
        for actor_id in mentioned_ids:
            actors.setdefault(actor_id, {})
        return {
            "delivery_id": delivery_id,
            "disposition": "candidate-event",
            "authorized": True,
            "event": portable_event,
            "actors": actors,
        }

    def _reaction_native_input(self, event: ReactionEvent) -> dict:
        channel_id = _snowflake(event.channel_id)
        message_id = _snowflake(event.message_id)
        author_id = _snowflake(event.author_id)
        event_id = (
            f"discord:reaction:{event.gateway_session_id}:{event.gateway_sequence}"
        )
        if channel_id is None or message_id is None or author_id is None:
            return self._unroutable(
                event_id,
                "Discord reaction lacked an exact channel, message, or actor ID",
            )
        if channel_id not in self.allowed_channel_ids:
            return self._unroutable(
                event_id,
                "Discord channel is outside the trusted routing allowlist",
            )
        if author_id in self.blocked_actor_ids:
            return self._unroutable(
                event_id,
                "Discord actor is outside the trusted routing policy",
            )
        actor: dict[str, Any] = {}
        if event.author_name:
            actor["display_name"] = event.author_name
        if event.author_is_bot is not None:
            actor["kind"] = "bot" if event.author_is_bot else "human"
        return {
            "delivery_id": event_id,
            "disposition": "candidate-event",
            "authorized": True,
            "event": {
                "id": event_id,
                "type": "reaction",
                "author_id": _discord_actor_id(author_id),
                "target_event_id": _discord_message_id(message_id),
                "reaction": event.reaction,
                "operation": event.operation,
            },
            "actors": {_discord_actor_id(author_id): actor},
        }

    def notification_params(self, event: MessageEvent | ReactionEvent) -> dict[str, Any]:
        """Versioned credential-free reactive notification for V2 consumers."""
        return {
            "schema_version": 2,
            "platform": "discord",
            "guild_id": event.guild_id,
            "channel_id": event.channel_id,
            "native_input": self.native_input(event),
        }
