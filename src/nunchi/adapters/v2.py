"""Factual V2 event sources for generic, Matrix, and Telegram hosts."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any


def _unroutable(delivery_id: str, reason: str) -> dict[str, Any]:
    return {"delivery_id": delivery_id, "disposition": "unroutable", "reason": reason}


def _iso_millis(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def _iso_seconds(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


class GenericEventSourceV2:
    """Reference host source: identity/routing are constructor-bound, not text-derived."""

    def __init__(self, *, platform: str, room_id: str) -> None:
        if not isinstance(platform, str) or not platform or not isinstance(room_id, str) or not room_id:
            raise ValueError("generic V2 source binding is invalid")
        self.platform = platform
        self.room_id = room_id

    def native_input(
        self,
        *,
        delivery_id: str,
        event: dict[str, Any] | None,
        actors: dict[str, dict[str, Any]] | None = None,
        authorized: bool,
        routing_room_id: str,
    ) -> dict[str, Any]:
        if not isinstance(delivery_id, str) or not delivery_id:
            raise ValueError("delivery_id is required")
        if routing_room_id != self.room_id or authorized is not True:
            return _unroutable(delivery_id, "host delivery is outside the trusted room binding")
        if not isinstance(event, dict):
            return _unroutable(delivery_id, "host could not construct a native event")
        return {
            "delivery_id": delivery_id,
            "disposition": "candidate-event",
            "authorized": True,
            "event": copy.deepcopy(event),
            "actors": copy.deepcopy(actors or {}),
        }


class MatrixEventSourceV2:
    capabilities = {
        "message": "history-and-live",
        "reaction": "history-and-live",
        "membership": "history-and-live",
        "thread_root": "available-when-native-relation-present",
        "restart": "session-token-plus-bounded-history; full restart gap not proven",
    }

    def __init__(self, *, allowed_room_ids: frozenset[str]) -> None:
        if not isinstance(allowed_room_ids, frozenset) or not allowed_room_ids:
            raise ValueError("Matrix V2 requires a non-empty trusted room allowlist")
        self.allowed_room_ids = allowed_room_ids

    @staticmethod
    def actor_id(user_id: str) -> str:
        return f"matrix:user:{user_id}"

    @staticmethod
    def event_id(event_id: str) -> str:
        return f"matrix:event:{event_id}"

    def native_input(self, room_id: str, native: dict[str, Any]) -> dict[str, Any]:
        raw_id = native.get("event_id") if isinstance(native, dict) else None
        delivery_id = f"matrix:event:{raw_id or 'unavailable'}"
        if room_id not in self.allowed_room_ids:
            return _unroutable(delivery_id, "Matrix room is outside the trusted allowlist")
        if not isinstance(raw_id, str) or not raw_id:
            return _unroutable(delivery_id, "Matrix delivery lacks a native event ID")
        event_type = native.get("type")
        sender = native.get("sender")
        content = native.get("content") or {}
        if not isinstance(content, dict):
            return _unroutable(delivery_id, "Matrix delivery content is malformed")
        timestamp = _iso_millis(native.get("origin_server_ts"))
        actors: dict[str, dict[str, Any]] = {}

        if event_type == "m.room.message":
            if not isinstance(sender, str) or not sender:
                return _unroutable(delivery_id, "Matrix message lacks an exact sender")
            body = content.get("body")
            if content.get("msgtype") not in ("m.text", "m.notice") or not isinstance(body, str):
                return _unroutable(delivery_id, "Matrix delivery is not a constructable text event")
            mentions = content.get("m.mentions", {})
            if not isinstance(mentions, dict):
                return _unroutable(
                    delivery_id,
                    "Matrix message carries malformed native mentions",
                )
            user_ids = mentions.get("user_ids") or []
            room_mention = mentions.get("room", False)
            if (
                not isinstance(user_ids, list)
                or any(not isinstance(item, str) or not item for item in user_ids)
                or not isinstance(room_mention, bool)
            ):
                return _unroutable(delivery_id, "Matrix message carries malformed native mentions")
            mentioned = list(dict.fromkeys(self.actor_id(item) for item in user_ids))
            event: dict[str, Any] = {
                "id": self.event_id(raw_id),
                "type": "message",
                "author_id": self.actor_id(sender),
                "text": body,
                "mentioned_actor_ids": mentioned,
                "mentions_room": room_mention,
            }
            relates = content.get("m.relates_to", {})
            if not isinstance(relates, dict):
                return _unroutable(
                    delivery_id,
                    "Matrix message carries a malformed native relation",
                )
            reply = relates.get("m.in_reply_to", {})
            if not isinstance(reply, dict):
                return _unroutable(
                    delivery_id,
                    "Matrix message carries a malformed native reply",
                )
            if isinstance(reply.get("event_id"), str) and reply["event_id"]:
                event["reply_to_event_id"] = self.event_id(reply["event_id"])
            if relates.get("rel_type") == "m.thread" and isinstance(relates.get("event_id"), str) and relates["event_id"]:
                event["thread_root_event_id"] = self.event_id(relates["event_id"])
            actors[self.actor_id(sender)] = {"kind": "unknown"}
            for actor in mentioned:
                actors.setdefault(actor, {"kind": "unknown"})
        elif event_type == "m.reaction":
            relates = content.get("m.relates_to") or {}
            if (
                not isinstance(sender, str)
                or not sender
                or not isinstance(relates, dict)
                or relates.get("rel_type") != "m.annotation"
                or not isinstance(relates.get("event_id"), str)
                or not relates.get("event_id")
                or not isinstance(relates.get("key"), str)
                or not relates.get("key")
            ):
                return _unroutable(delivery_id, "Matrix reaction lacks exact native relation facts")
            event = {
                "id": self.event_id(raw_id),
                "type": "reaction",
                "author_id": self.actor_id(sender),
                "target_event_id": self.event_id(relates["event_id"]),
                "reaction": relates["key"],
                "operation": "add",
            }
            actors[self.actor_id(sender)] = {"kind": "unknown"}
        elif event_type == "m.room.member":
            subject = native.get("state_key")
            membership = content.get("membership")
            if not isinstance(subject, str) or not subject or membership not in ("join", "leave"):
                return _unroutable(delivery_id, "Matrix membership change is unavailable in the portable vocabulary")
            event = {
                "id": self.event_id(raw_id),
                "type": "membership",
                "scope": {"kind": "room", "id": room_id},
                "subject_actor_id": self.actor_id(subject),
                "change": membership,
            }
            if isinstance(sender, str) and sender:
                event["caused_by_actor_id"] = self.actor_id(sender)
                actors[self.actor_id(sender)] = {"kind": "unknown"}
            actors.setdefault(self.actor_id(subject), {"kind": "unknown"})
        else:
            return _unroutable(delivery_id, "Matrix event kind is unavailable to the V2 reference adapter")
        if timestamp is not None:
            event["timestamp"] = timestamp
        return {"delivery_id": delivery_id, "disposition": "candidate-event", "authorized": True, "event": event, "actors": actors}


class TelegramEventSourceV2:
    capabilities = {
        "message": "live-only",
        "reply": "available",
        "structured_user_mention": "available",
        "username_mention": "identity-unavailable",
        "reaction": "unavailable-without-prior-state-diff",
        "membership": "available-for-chat-member-updates",
        "history": "unavailable",
        "restart": "known-gap",
    }

    def __init__(self, *, allowed_chat_ids: frozenset[str]) -> None:
        if not isinstance(allowed_chat_ids, frozenset) or not allowed_chat_ids:
            raise ValueError("Telegram V2 requires a non-empty trusted chat allowlist")
        self.allowed_chat_ids = allowed_chat_ids

    @staticmethod
    def actor_id(user_id: object) -> str:
        return f"telegram:user:{user_id}"

    @staticmethod
    def message_id(chat_id: object, message_id: object) -> str:
        return f"telegram:message:{chat_id}:{message_id}"

    def native_input(self, update: dict[str, Any]) -> dict[str, Any]:
        update_id = update.get("update_id") if isinstance(update, dict) else None
        delivery_id = f"telegram:update:{update_id if isinstance(update_id, int) else 'unavailable'}"
        if isinstance(update_id, bool) or not isinstance(update_id, int):
            return _unroutable(delivery_id, "Telegram update lacks an exact update ID")
        message = update.get("message")
        if isinstance(message, dict):
            return self._message(delivery_id, message)
        membership = update.get("chat_member") or update.get("my_chat_member")
        if isinstance(membership, dict):
            return self._membership(delivery_id, membership)
        if "message_reaction" in update:
            return _unroutable(delivery_id, "Telegram reaction delta is unavailable without prior-state comparison")
        return _unroutable(delivery_id, "Telegram update kind is unavailable to the V2 reference adapter")

    def _message(self, delivery_id: str, message: dict[str, Any]) -> dict[str, Any]:
        chat = message.get("chat") or {}
        author = message.get("from") or {}
        chat_id = str(chat.get("id")) if chat.get("id") is not None else ""
        user_id = author.get("id")
        message_id = message.get("message_id")
        if chat_id not in self.allowed_chat_ids:
            return _unroutable(delivery_id, "Telegram chat is outside the trusted allowlist")
        if isinstance(user_id, bool) or not isinstance(user_id, int) or isinstance(message_id, bool) or not isinstance(message_id, int):
            return _unroutable(delivery_id, "Telegram message lacks exact chat, message, or actor identity")
        text = message.get("text", message.get("caption"))
        if not isinstance(text, str):
            return _unroutable(delivery_id, "Telegram message has no constructable text")
        entities = message.get("entities", [])
        if not isinstance(entities, list) or any(
            not isinstance(entity, dict) for entity in entities
        ):
            return _unroutable(
                delivery_id,
                "Telegram message carries malformed native entities",
            )
        mentioned: list[str] = []
        for entity in entities:
            if entity.get("type") == "text_mention":
                user = entity.get("user") or {}
                target = user.get("id") if isinstance(user, dict) else None
                if isinstance(target, int) and not isinstance(target, bool):
                    actor_id = self.actor_id(target)
                    if actor_id not in mentioned:
                        mentioned.append(actor_id)
        event: dict[str, Any] = {
            "id": self.message_id(chat_id, message_id),
            "type": "message",
            "author_id": self.actor_id(user_id),
            "text": text,
            "mentioned_actor_ids": mentioned,
            "mentions_room": False,
        }
        reply = message.get("reply_to_message")
        if reply is not None:
            if (
                not isinstance(reply, dict)
                or not isinstance(reply.get("message_id"), int)
                or isinstance(reply.get("message_id"), bool)
            ):
                return _unroutable(
                    delivery_id,
                    "Telegram message carries a malformed native reply",
                )
            event["reply_to_event_id"] = self.message_id(
                chat_id,
                reply["message_id"],
            )
        timestamp = _iso_seconds(message.get("date"))
        if timestamp is not None:
            event["timestamp"] = timestamp
        actors = {self.actor_id(user_id): {"kind": "bot" if author.get("is_bot") else "human"}}
        for target in mentioned:
            actors.setdefault(target, {"kind": "unknown"})
        return {"delivery_id": delivery_id, "disposition": "candidate-event", "authorized": True, "event": event, "actors": actors}

    def _membership(self, delivery_id: str, update: dict[str, Any]) -> dict[str, Any]:
        chat = update.get("chat") or {}
        caused_by = update.get("from") or {}
        member = update.get("new_chat_member") or {}
        subject = member.get("user") if isinstance(member, dict) else None
        subject = subject if isinstance(subject, dict) else {}
        chat_id = str(chat.get("id")) if chat.get("id") is not None else ""
        status = member.get("status") if isinstance(member, dict) else None
        change = "join" if status in ("member", "administrator", "creator") else "leave" if status in ("left", "kicked") else None
        if chat_id not in self.allowed_chat_ids:
            return _unroutable(delivery_id, "Telegram chat is outside the trusted allowlist")
        if (
            isinstance(subject.get("id"), bool)
            or not isinstance(subject.get("id"), int)
            or change is None
        ):
            return _unroutable(delivery_id, "Telegram membership change is unavailable in the portable vocabulary")
        event: dict[str, Any] = {
            "id": delivery_id,
            "type": "membership",
            "scope": {"kind": "room", "id": chat_id},
            "subject_actor_id": self.actor_id(subject["id"]),
            "change": change,
        }
        actors = {self.actor_id(subject["id"]): {"kind": "bot" if subject.get("is_bot") else "human"}}
        if (
            isinstance(caused_by.get("id"), int)
            and not isinstance(caused_by.get("id"), bool)
        ):
            event["caused_by_actor_id"] = self.actor_id(caused_by["id"])
            actors[self.actor_id(caused_by["id"])] = {"kind": "bot" if caused_by.get("is_bot") else "human"}
        timestamp = _iso_seconds(update.get("date"))
        if timestamp is not None:
            event["timestamp"] = timestamp
        return {"delivery_id": delivery_id, "disposition": "candidate-event", "authorized": True, "event": event, "actors": actors}


__all__ = ["GenericEventSourceV2", "MatrixEventSourceV2", "TelegramEventSourceV2"]
