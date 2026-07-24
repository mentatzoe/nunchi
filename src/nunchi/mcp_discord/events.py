"""Truth-preserving Discord text rendering and the shared V2 notification."""

from __future__ import annotations

from typing import Any

NOTIFICATION_METHOD = "notifications/nunchi/v2/discord-event"
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


def v2_notification_from_dispatch(
    event_type: str,
    data: dict,
    *,
    sequence: int | None,
    room_id: str | None = None,
) -> dict:
    """Build the closed shared V2 notification for one gateway dispatch.

    Self-authored messages are deliberately preserved.  Exact self is a
    participant-specific observation fact and only suppresses that
    participant's wake; the transport must not erase it for other consumers or
    later context.
    """
    from nunchi.adapters.v2 import normalize_discord_gateway
    from nunchi.observation import ParticipantBinding

    native = dict(data)
    if room_id is not None:
        native["room_id"] = room_id
    placeholder = ParticipantBinding(
        participant_id="transport",
        actor_id="discord:actor:transport",
        platform="discord",
        room_id=str(room_id or data.get("channel_id") or data.get("guild_id") or "unknown"),
        continuity_scope_id=f"discord:{room_id or data.get('channel_id') or data.get('guild_id') or 'unknown'}",
    )
    delivery = normalize_discord_gateway(
        {"t": event_type, "s": sequence, "d": native},
        placeholder,
    )
    return {
        "schema_version": 2,
        "delivery_id": delivery.delivery_id,
        "room_id": delivery.room_id,
        "event": delivery.event,
        "actors": delivery.actors,
        "continuity_gap": False,
    }
