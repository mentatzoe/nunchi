"""Truth-preserving native normalization for V2 reference adapters."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..errors import ValidationError
from ..observation import ParticipantBinding
from ..v2_contracts import validate_canonical_event


@dataclass(frozen=True)
class NativeDelivery:
    delivery_id: str
    room_id: str | None
    event: dict[str, Any] | None
    actors: dict[str, dict[str, Any]]
    detail: str = ""


def _nes(value: Any, label: str) -> str:
    if not isinstance(value, (str, int)) or str(value) == "":
        raise ValidationError(f"{label} must be a stable non-empty native ID")
    return str(value)


def _actor(prefix: str, value: Any) -> str:
    return f"{prefix}:actor:{_nes(value, 'actor id')}"


def _event(prefix: str, kind: str, value: Any) -> str:
    return f"{prefix}:{kind}:{_nes(value, 'event id')}"


def normalize_generic(
    payload: Mapping[str, Any],
    binding: ParticipantBinding,
) -> NativeDelivery:
    if not isinstance(payload, Mapping):
        raise ValidationError("generic delivery must be an object")
    if set(payload) != {"delivery_id", "room_id", "event", "actors"}:
        raise ValidationError("generic delivery has an invalid closed shape")
    delivery_id = _nes(payload["delivery_id"], "delivery_id")
    room_id = _nes(payload["room_id"], "room_id")
    if payload["event"] is None:
        return NativeDelivery(delivery_id, room_id, None, {}, "unconstructable generic event")
    event = validate_canonical_event(payload["event"])
    if not isinstance(payload["actors"], Mapping):
        raise ValidationError("generic actors must be an object")
    actors = deepcopy(dict(payload["actors"]))
    return NativeDelivery(delivery_id, room_id, event, actors)


def normalize_discord_gateway(
    payload: Mapping[str, Any],
    binding: ParticipantBinding,
) -> NativeDelivery:
    if not isinstance(payload, Mapping):
        raise ValidationError("Discord gateway delivery must be an object")
    event_type = payload.get("t")
    sequence = payload.get("s")
    delivery_epoch = payload.get("delivery_epoch")
    occurrence = (
        f"{delivery_epoch}:{sequence}"
        if isinstance(delivery_epoch, str)
        and delivery_epoch
        and sequence is not None
        else None
    )
    data = payload.get("d")
    delivery_id = (
        f"discord:gateway:{occurrence or 'unknown'}:{event_type or 'unknown'}"
    )
    if not isinstance(data, Mapping):
        return NativeDelivery(delivery_id, None, None, {}, "Discord payload has no event data")
    room_id = str(data.get("channel_id") or data.get("room_id") or "")
    if event_type == "MESSAGE_CREATE":
        author = data.get("author")
        if not room_id or not isinstance(author, Mapping) or "id" not in author or "id" not in data:
            return NativeDelivery(delivery_id, room_id or None, None, {}, "message lacks native identity")
        author_id = _actor("discord", author["id"])
        actors = {
            author_id: {
                "display_name": str(
                    author.get("global_name")
                    or author.get("display_name")
                    or author.get("username")
                    or author["id"]
                ),
                "kind": "bot" if author.get("bot") is True else "human",
            }
        }
        mentioned = []
        for raw_actor in data.get("mentions", []):
            if not isinstance(raw_actor, Mapping) or "id" not in raw_actor:
                continue
            actor_id = _actor("discord", raw_actor["id"])
            if actor_id not in mentioned:
                mentioned.append(actor_id)
            actors[actor_id] = {
                "display_name": str(
                    raw_actor.get("global_name")
                    or raw_actor.get("display_name")
                    or raw_actor.get("username")
                    or raw_actor["id"]
                ),
                "kind": "bot" if raw_actor.get("bot") is True else "human",
            }
        reference = data.get("message_reference")
        reply_to = (
            _event("discord", "message", reference["message_id"])
            if isinstance(reference, Mapping) and reference.get("message_id")
            else None
        )
        thread = data.get("thread")
        thread_root = (
            _event("discord", "message", thread["id"])
            if isinstance(thread, Mapping) and thread.get("id")
            else None
        )
        canonical: dict[str, Any] = {
            "id": _event("discord", "message", data["id"]),
            "type": "message",
            "author_id": author_id,
            "text": str(data.get("content", "")),
            "mentioned_actor_ids": mentioned,
            "mentions_room": data.get("mention_everyone") is True,
        }
        if isinstance(data.get("timestamp"), str) and data["timestamp"]:
            canonical["timestamp"] = data["timestamp"]
        if reply_to:
            canonical["reply_to_event_id"] = reply_to
        if thread_root:
            canonical["thread_root_event_id"] = thread_root
        return NativeDelivery(
            f"{delivery_id}:{data['id']}",
            room_id,
            validate_canonical_event(canonical),
            actors,
        )
    if event_type in ("MESSAGE_REACTION_ADD", "MESSAGE_REACTION_REMOVE"):
        user_id = data.get("user_id")
        message_id = data.get("message_id")
        emoji = data.get("emoji")
        if not room_id or user_id is None or message_id is None or not isinstance(emoji, Mapping):
            return NativeDelivery(delivery_id, room_id or None, None, {}, "reaction lacks native identity")
        actor_id = _actor("discord", user_id)
        reaction = emoji.get("id") or emoji.get("name")
        if not reaction:
            return NativeDelivery(delivery_id, room_id, None, {}, "reaction lacks emoji")
        if occurrence is None:
            return NativeDelivery(
                delivery_id,
                room_id,
                None,
                {},
                "reaction lacks a stable delivery epoch and sequence",
            )
        event_id = (
            f"{event_type}:{user_id}:{message_id}:"
            f"{emoji.get('id') or emoji.get('name')}:{occurrence}"
        )
        canonical = {
            "id": _event("discord", "reaction", event_id),
            "type": "reaction",
            "author_id": actor_id,
            "target_event_id": _event("discord", "message", message_id),
            "reaction": str(reaction),
            "operation": "add" if event_type.endswith("ADD") else "remove",
        }
        return NativeDelivery(
            f"{delivery_id}:{event_id}",
            room_id,
            validate_canonical_event(canonical),
            {actor_id: {"kind": "unknown"}},
        )
    if event_type in ("GUILD_MEMBER_ADD", "GUILD_MEMBER_REMOVE"):
        user = data.get("user")
        guild_id = data.get("guild_id")
        if (
            not isinstance(user, Mapping)
            or user.get("id") is None
            or guild_id is None
            or occurrence is None
        ):
            return NativeDelivery(delivery_id, None, None, {}, "membership lacks native identity")
        actor_id = _actor("discord", user["id"])
        canonical = {
            "id": _event(
                "discord",
                "membership",
                f"{guild_id}:{user['id']}:{event_type}:{occurrence}",
            ),
            "type": "membership",
            "scope": {"kind": "space", "id": str(guild_id)},
            "subject_actor_id": actor_id,
            "change": "join" if event_type.endswith("ADD") else "leave",
        }
        return NativeDelivery(
            delivery_id,
            str(data.get("room_id") or guild_id),
            validate_canonical_event(canonical),
            {
                actor_id: {
                    "display_name": str(user.get("global_name") or user.get("username") or user["id"]),
                    "kind": "bot" if user.get("bot") is True else "human",
                }
            },
        )
    return NativeDelivery(delivery_id, room_id or None, None, {}, "unsupported Discord event class")


def normalize_matrix_event(
    payload: Mapping[str, Any],
    binding: ParticipantBinding,
) -> NativeDelivery:
    if not isinstance(payload, Mapping):
        raise ValidationError("Matrix delivery must be an object")
    room_id = str(payload.get("room_id") or "")
    event = payload.get("event", payload)
    if not isinstance(event, Mapping):
        return NativeDelivery("matrix:unknown", room_id or None, None, {}, "missing Matrix event")
    event_id = event.get("event_id")
    event_type = event.get("type")
    sender = event.get("sender")
    delivery_id = f"matrix:delivery:{event_id or 'unknown'}"
    if not event_id or not room_id:
        return NativeDelivery(delivery_id, room_id or None, None, {}, "Matrix event lacks room/event ID")
    if event_type == "m.room.message" and sender:
        actor_id = _actor("matrix", sender)
        content = event.get("content") if isinstance(event.get("content"), Mapping) else {}
        relates = content.get("m.relates_to") if isinstance(content.get("m.relates_to"), Mapping) else {}
        reply = relates.get("m.in_reply_to") if isinstance(relates.get("m.in_reply_to"), Mapping) else {}
        mentions = content.get("m.mentions") if isinstance(content.get("m.mentions"), Mapping) else {}
        mentioned = [_actor("matrix", item) for item in mentions.get("user_ids", []) if item]
        actors = {actor_id: {"display_name": str(sender), "kind": "unknown"}}
        for item in mentioned:
            actors.setdefault(item, {"kind": "unknown"})
        canonical: dict[str, Any] = {
            "id": _event("matrix", "event", event_id),
            "type": "message",
            "author_id": actor_id,
            "text": str(content.get("body", "")),
            "mentioned_actor_ids": mentioned,
            "mentions_room": content.get("m.mentions", {}).get("room") is True
            if isinstance(content.get("m.mentions"), Mapping)
            else False,
        }
        if reply.get("event_id"):
            canonical["reply_to_event_id"] = _event("matrix", "event", reply["event_id"])
        if isinstance(event.get("origin_server_ts"), int):
            canonical["timestamp"] = datetime.fromtimestamp(
                event["origin_server_ts"] / 1000,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z")
        return NativeDelivery(delivery_id, room_id, validate_canonical_event(canonical), actors)
    if event_type == "m.reaction" and sender:
        content = event.get("content") if isinstance(event.get("content"), Mapping) else {}
        relates = content.get("m.relates_to") if isinstance(content.get("m.relates_to"), Mapping) else {}
        if not relates.get("event_id") or relates.get("key") is None:
            return NativeDelivery(delivery_id, room_id, None, {}, "Matrix reaction lacks relation")
        actor_id = _actor("matrix", sender)
        canonical = {
            "id": _event("matrix", "event", event_id),
            "type": "reaction",
            "author_id": actor_id,
            "target_event_id": _event("matrix", "event", relates["event_id"]),
            "reaction": str(relates["key"]),
            "operation": "add",
        }
        return NativeDelivery(
            delivery_id,
            room_id,
            validate_canonical_event(canonical),
            {actor_id: {"display_name": str(sender), "kind": "unknown"}},
        )
    if event_type == "m.room.member":
        state_key = event.get("state_key")
        content = event.get("content") if isinstance(event.get("content"), Mapping) else {}
        membership = content.get("membership")
        if not state_key or membership not in ("join", "leave"):
            return NativeDelivery(delivery_id, room_id, None, {}, "Matrix membership is unsupported")
        subject = _actor("matrix", state_key)
        actors = {subject: {"display_name": str(content.get("displayname") or state_key), "kind": "unknown"}}
        canonical = {
            "id": _event("matrix", "event", event_id),
            "type": "membership",
            "scope": {"kind": "room", "id": room_id},
            "subject_actor_id": subject,
            "change": membership,
        }
        if sender:
            cause = _actor("matrix", sender)
            canonical["caused_by_actor_id"] = cause
            actors.setdefault(cause, {"display_name": str(sender), "kind": "unknown"})
        return NativeDelivery(delivery_id, room_id, validate_canonical_event(canonical), actors)
    return NativeDelivery(delivery_id, room_id, None, {}, "unsupported Matrix event class")


def normalize_telegram_update(
    payload: Mapping[str, Any],
    binding: ParticipantBinding,
) -> NativeDelivery:
    if not isinstance(payload, Mapping):
        raise ValidationError("Telegram update must be an object")
    update_id = payload.get("update_id")
    delivery_id = f"telegram:update:{update_id if update_id is not None else 'unknown'}"
    message = payload.get("message") or payload.get("channel_post")
    if isinstance(message, Mapping):
        chat = message.get("chat")
        author = message.get("from")
        message_id = message.get("message_id")
        if not isinstance(chat, Mapping) or not isinstance(author, Mapping) or message_id is None:
            return NativeDelivery(delivery_id, None, None, {}, "Telegram message lacks identity")
        room_id = str(chat.get("id", ""))
        author_id = _actor("telegram", author.get("id"))
        actors = {
            author_id: {
                "display_name": str(
                    author.get("username")
                    or " ".join(
                        part for part in (author.get("first_name"), author.get("last_name")) if part
                    )
                    or author.get("id")
                ),
                "kind": "bot" if author.get("is_bot") is True else "human",
            }
        }
        mentioned = []
        text = str(message.get("text") or message.get("caption") or "")
        for entity in [*message.get("entities", []), *message.get("caption_entities", [])]:
            if not isinstance(entity, Mapping):
                continue
            user = entity.get("user")
            if entity.get("type") == "text_mention" and isinstance(user, Mapping) and user.get("id") is not None:
                actor_id = _actor("telegram", user["id"])
                if actor_id not in mentioned:
                    mentioned.append(actor_id)
                actors[actor_id] = {
                    "display_name": str(user.get("username") or user.get("first_name") or user["id"]),
                    "kind": "bot" if user.get("is_bot") is True else "human",
                }
        canonical: dict[str, Any] = {
            "id": _event("telegram", "message", f"{room_id}:{message_id}"),
            "type": "message",
            "author_id": author_id,
            "text": text,
            "mentioned_actor_ids": mentioned,
            # Telegram has no native room-wide mention relation.
            "mentions_room": False,
        }
        if isinstance(message.get("date"), int):
            canonical["timestamp"] = datetime.fromtimestamp(
                message["date"], tz=timezone.utc
            ).isoformat().replace("+00:00", "Z")
        reply = message.get("reply_to_message")
        if isinstance(reply, Mapping) and reply.get("message_id") is not None:
            canonical["reply_to_event_id"] = _event(
                "telegram",
                "message",
                f"{room_id}:{reply['message_id']}",
            )
        return NativeDelivery(delivery_id, room_id, validate_canonical_event(canonical), actors)
    membership = payload.get("my_chat_member") or payload.get("chat_member")
    if isinstance(membership, Mapping):
        chat = membership.get("chat")
        subject = membership.get("new_chat_member")
        if not isinstance(chat, Mapping) or not isinstance(subject, Mapping):
            return NativeDelivery(delivery_id, None, None, {}, "Telegram membership lacks identity")
        user = subject.get("user")
        status = subject.get("status")
        if not isinstance(user, Mapping) or status not in ("member", "left", "kicked"):
            return NativeDelivery(delivery_id, str(chat.get("id", "")), None, {}, "unsupported membership")
        room_id = str(chat.get("id", ""))
        actor_id = _actor("telegram", user.get("id"))
        canonical = {
            "id": _event("telegram", "membership", f"{room_id}:{user.get('id')}:{update_id}"),
            "type": "membership",
            "scope": {"kind": "room", "id": room_id},
            "subject_actor_id": actor_id,
            "change": "join" if status == "member" else "leave",
        }
        return NativeDelivery(
            delivery_id,
            room_id,
            validate_canonical_event(canonical),
            {
                actor_id: {
                    "display_name": str(user.get("username") or user.get("first_name") or user.get("id")),
                    "kind": "bot" if user.get("is_bot") is True else "human",
                }
            },
        )
    return NativeDelivery(delivery_id, None, None, {}, "unsupported Telegram update class")


NORMALIZERS = {
    "channel": normalize_generic,
    "discord": normalize_discord_gateway,
    "matrix": normalize_matrix_event,
    "telegram": normalize_telegram_update,
}
