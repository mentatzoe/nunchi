"""Authenticated Hermes reaction facts and one exact native ACK effect.

AttentionEngine still owns ACK selection and capability widening. This module
only reads current platform permission facts and performs the one native
reaction those facts allow. It does not judge social meaning, and it does not
copy a second ACK policy.

The native call is awaited outside the shared scheduler lock and the room
runtime lock. The one opportunity deadline bounds that wait. A lost or late
result is unknown and is not retried.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
import logging
import threading
import time
from typing import Any

from nunchi.ack import (
    AckJournal,
    AckPolicy,
    ReactionCapability,
    UNAVAILABLE_REACTION_CAPABILITY,
)
from nunchi.participant import (
    OpportunityToken,
    TransportResult,
    participant_host_receipt_body,
)
from nunchi.receipts import ReceiptJournal

logger = logging.getLogger(__name__)

_ACK_EFFECT_PERMIT: ContextVar["AckEffectPermit | None"] = ContextVar(
    "nunchi_hermes_ack_effect_permit",
    default=None,
)


def unavailable(detail: str) -> ReactionCapability:
    """Return an unattested capability. Callers widen ACK to DEFER."""

    return ReactionCapability(
        supported=False,
        authenticated=False,
        permissions_revision="unavailable",
        detail=detail,
    )


def _revision(
    *,
    platform: str,
    bot_id: str,
    room_id: str,
    operations: tuple[str, ...],
    reactions: tuple[str, ...],
) -> str:
    payload = json.dumps(
        {
            "bot_id": bot_id,
            "operations": list(operations),
            "platform": platform,
            "reactions": list(reactions),
            "room_id": room_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _native_actor_id(actor_id: str, platform: str) -> str:
    prefix = f"{platform}:actor:"
    if not actor_id.startswith(prefix):
        return ""
    return actor_id[len(prefix):]


def _telegram_parent_chat(room_id: str) -> str:
    marker = ":topic:"
    if marker in room_id:
        return room_id.split(marker, 1)[0]
    return room_id


def _standard_telegram_reactions() -> tuple[str, ...] | None:
    """Return the installed Bot API reaction set, or None if it is unattested.

    An omitted ``available_reactions`` field means the platform's standard set,
    not every Unicode emoji. The default ACK emoji is not in that set, so a
    missing enumeration must not be treated as permission to use it.
    """

    try:
        from telegram.constants import ReactionEmoji
    except Exception:
        return None
    values = []
    for item in ReactionEmoji:
        text = getattr(item, "value", item)
        if isinstance(text, str) and text:
            values.append(text)
    return tuple(values) or None


def _emoji_list(raw: Any) -> tuple[str, ...] | None:
    if raw is None:
        return None
    if isinstance(raw, (str, bytes)):
        return None
    found: list[str] = []
    try:
        items = list(raw)
    except TypeError:
        return None
    for item in items:
        if isinstance(item, str) and item:
            found.append(item)
            continue
        if isinstance(item, Mapping):
            emoji = item.get("emoji")
        else:
            emoji = getattr(item, "emoji", None)
        if isinstance(emoji, str) and emoji:
            found.append(emoji)
            continue
        return None
    return tuple(found)


@dataclass
class AckEffectPermit:
    """Authority for exactly one native reaction call. Not a route bypass."""

    adapter: Any
    method: str
    emoji: str
    room_id: str
    native_message_id: str
    message: Any = None
    chat_id: str | None = None
    consumed: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def matches(self, adapter: Any, method: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> bool:
        if adapter is not self.adapter or method != self.method or self.consumed:
            return False
        if method == "_add_reaction":
            message = args[0] if args else kwargs.get("message")
            emoji = args[1] if len(args) > 1 else kwargs.get("emoji")
            channel_id = getattr(getattr(message, "channel", None), "id", None)
            message_id = getattr(message, "id", None)
            return (
                message is self.message
                and str(emoji) == self.emoji
                and str(channel_id) == self.room_id
                and str(message_id) == self.native_message_id
            )
        if method == "_set_reaction":
            chat_id = args[0] if args else kwargs.get("chat_id")
            message_id = args[1] if len(args) > 1 else kwargs.get("message_id")
            emoji = args[2] if len(args) > 2 else kwargs.get("emoji")
            return (
                self.chat_id is not None
                and str(chat_id) == self.chat_id
                and str(message_id) == self.native_message_id
                and str(emoji) == self.emoji
            )
        return False


def claim_ack_effect(
    adapter: Any,
    method: str,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> bool:
    """Consume the current task's permit only when the call is the exact ACK.

    Any other method, target, emoji, or adapter returns False so the existing
    effect guard keeps blocking it. A second exact call also returns False.
    """

    permit = _ACK_EFFECT_PERMIT.get()
    if permit is None:
        return False
    with permit._lock:
        if permit.consumed or not permit.matches(adapter, method, args, kwargs):
            return False
        permit.consumed = True
        return True


def discord_reaction_capability(
    adapter: Any,
    event: Any,
    *,
    room_id: str,
    actor_id: str,
) -> ReactionCapability:
    """Read discord.py permissions for the authenticated client bot and trigger.

    Permission facts come from the SDK channel object and the authenticated
    client user. Message text and display names are not consulted.
    """

    bot_id = _native_actor_id(actor_id, "discord")
    client = getattr(adapter, "_client", None)
    user = getattr(client, "user", None)
    authenticated_id = getattr(user, "id", None)
    if client is None or user is None or authenticated_id is None or not bot_id:
        return unavailable("Discord client bot is not authenticated")
    if str(authenticated_id) != bot_id:
        return unavailable("Discord client bot does not match the configured actor")
    if not callable(getattr(adapter, "_add_reaction", None)):
        return unavailable("shipped Discord reaction method is absent")
    message = getattr(event, "raw_message", None)
    channel = getattr(message, "channel", None)
    channel_id = getattr(channel, "id", None)
    if message is None or channel is None or channel_id is None:
        return unavailable("Discord trigger has no native message")
    if str(channel_id) != str(room_id):
        return unavailable("Discord trigger is not in the configured room")
    if not hasattr(message, "add_reaction"):
        return unavailable("Discord trigger cannot accept a native reaction")
    permissions_for = getattr(channel, "permissions_for", None)
    if not callable(permissions_for):
        return unavailable("Discord channel permissions are unattested")
    subject = _discord_permission_subject(client, channel, bot_id)
    if subject is None:
        return unavailable("Discord permission subject is not the authenticated bot")
    try:
        permissions = permissions_for(subject)
    except Exception:
        logger.debug("Discord permission probe failed", exc_info=True)
        return unavailable("Discord channel permissions could not be read")
    if permissions is None:
        return unavailable("Discord channel permissions are unattested")
    allowed = bool(
        getattr(permissions, "view_channel", False)
        and getattr(permissions, "read_message_history", False)
        and getattr(permissions, "add_reactions", False)
    )
    operations = ("add",) if allowed else ()
    reactions = ("*",) if allowed else ()
    detail = "" if allowed else "Discord room reaction permission is unavailable or denied"
    return ReactionCapability(
        supported=allowed,
        authenticated=True,
        operations=operations,
        reactions=reactions,
        permissions_revision=_revision(
            platform="discord",
            bot_id=bot_id,
            room_id=str(room_id),
            operations=operations,
            reactions=reactions,
        ),
        detail=detail,
    )


def _discord_permission_subject(client: Any, channel: Any, bot_id: str) -> Any:
    """Return the authenticated bot member, never the message author."""

    user = getattr(client, "user", None)
    guild = getattr(channel, "guild", None)
    me = getattr(guild, "me", None) if guild is not None else None
    if me is not None and str(getattr(me, "id", "")) == bot_id:
        return me
    get_member = getattr(guild, "get_member", None) if guild is not None else None
    if callable(get_member):
        try:
            member = get_member(getattr(user, "id", None))
        except Exception:
            member = None
        if member is not None and str(getattr(member, "id", "")) == bot_id:
            return member
    if user is not None and str(getattr(user, "id", "")) == bot_id:
        return user
    return None


async def telegram_reaction_capability(
    adapter: Any,
    *,
    room_id: str,
    actor_id: str,
    timeout: float | None,
) -> ReactionCapability:
    """Read authenticated available-reactions facts for the exact Telegram chat.

    A missing or failed getChat is unknown, not permission to use the default
    emoji. An explicit empty list is denial. An omitted field means only the
    installed standard reaction set, which does not include an arbitrary emoji.
    """

    bot_id = _native_actor_id(actor_id, "telegram")
    bot = getattr(adapter, "_bot", None)
    authenticated_id = getattr(bot, "id", None)
    if bot is None or authenticated_id is None or not bot_id:
        return unavailable("Telegram bot is not authenticated")
    if str(authenticated_id) != bot_id:
        return unavailable("Telegram bot does not match the configured actor")
    if not callable(getattr(adapter, "_set_reaction", None)):
        return unavailable("shipped Telegram set-reaction method is absent")
    if not callable(getattr(bot, "set_message_reaction", None)):
        return unavailable("Telegram setMessageReaction is not supported by this bot")
    reactions = await _telegram_available_reactions(
        bot,
        _telegram_parent_chat(room_id),
        timeout,
    )
    if reactions is None:
        return unavailable("Telegram available reactions are unattested")
    allowed = bool(reactions)
    operations = ("add",) if allowed else ()
    detail = "" if allowed else "Telegram chat allows no reactions"
    return ReactionCapability(
        supported=allowed,
        authenticated=True,
        operations=operations,
        reactions=reactions,
        permissions_revision=_revision(
            platform="telegram",
            bot_id=bot_id,
            room_id=str(room_id),
            operations=operations,
            reactions=reactions,
        ),
        detail=detail,
    )


async def _telegram_available_reactions(
    bot: Any,
    chat_id: str,
    timeout: float | None,
) -> tuple[str, ...] | None:
    get_chat = getattr(bot, "get_chat", None)
    if not callable(get_chat) or timeout is None or timeout <= 0:
        return None
    try:
        chat = await asyncio.wait_for(get_chat(chat_id), timeout=timeout)
    except Exception:
        logger.debug("Telegram getChat reaction probe failed", exc_info=True)
        return None
    if chat is None:
        return None
    if isinstance(chat, Mapping):
        if "available_reactions" not in chat:
            return _standard_telegram_reactions()
        raw = chat.get("available_reactions")
    else:
        if "available_reactions" not in getattr(chat, "__slots__", ()) and not hasattr(chat, "available_reactions"):
            return None
        raw = getattr(chat, "available_reactions", None)
    if raw is None:
        return _standard_telegram_reactions()
    return _emoji_list(raw)


async def probe_reaction_capability(
    adapter: Any,
    event: Any,
    *,
    platform: str,
    room_id: str,
    actor_id: str,
    timeout: float | None,
) -> ReactionCapability:
    try:
        if platform == "discord":
            return discord_reaction_capability(
                adapter,
                event,
                room_id=room_id,
                actor_id=actor_id,
            )
        if platform == "telegram":
            return await telegram_reaction_capability(
                adapter,
                room_id=room_id,
                actor_id=actor_id,
                timeout=timeout,
            )
    except Exception:
        logger.debug("Hermes reaction capability probe failed", exc_info=True)
        return unavailable("native reaction capability probe failed")
    return unavailable(f"Hermes platform {platform} has no attested reaction capability")


def _deadline_id(lifecycle_id: str, generation: int, deadline: float, revision: str) -> str:
    return hashlib.sha256(
        f"{lifecycle_id}\0{generation}\0{deadline:.9f}\0{revision}".encode("utf-8")
    ).hexdigest()


def _append_receipt(
    receipts: ReceiptJournal,
    *,
    request_id: str,
    stage: str,
    writer: str,
    body: Mapping[str, Any],
) -> None:
    receipts.append(
        {
            "request_id": request_id,
            "stage": stage,
            "writer": writer,
            "body": dict(body),
        },
        writer=writer,
    )


def _native_target(platform: str, event: Any, room_id: str) -> tuple[str, Any, str | None]:
    if platform == "discord":
        message = getattr(event, "raw_message", None)
        message_id = getattr(message, "id", None)
        if message is None or message_id is None:
            raise ValueError("Discord ACK trigger has no native message")
        return "_add_reaction", message, None
    if platform == "telegram":
        message_id = getattr(event, "message_id", None)
        if message_id in (None, ""):
            raise ValueError("Telegram ACK trigger has no native message id")
        return "_set_reaction", str(message_id), _telegram_parent_chat(room_id)
    raise ValueError(f"Hermes platform {platform} cannot dispatch ACK")


async def _await_native(
    call: Any,
    *,
    token: OpportunityToken,
    deadline: float,
) -> tuple[str, Any]:
    """Wait for one native call without holding scheduler or runtime locks.

    Returns ``("value", result)``, ``("late", None)``, or ``("lost", None)``.
    The call is started only by the caller, after cancel and deadline checks.
    """

    native = asyncio.create_task(call)
    remaining = deadline - time.monotonic()

    async def _watch() -> str:
        while not token.cancel_event.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                return "deadline"
            await asyncio.sleep(min(0.05, left))
        return "cancel"

    watcher = asyncio.create_task(_watch())
    try:
        if remaining <= 0 or token.cancel_event.is_set():
            native.cancel()
            return "late", None
        done, _pending = await asyncio.wait(
            {native, watcher},
            timeout=max(0.0, remaining),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if native in done and not native.cancelled():
            try:
                return "value", native.result()
            except asyncio.CancelledError:
                return "lost", None
            except Exception:
                logger.debug("Hermes ACK native call failed", exc_info=True)
                return "lost", None
        native.cancel()
        return "late", None
    finally:
        watcher.cancel()
        for task in (native, watcher):
            if not task.done():
                continue
            try:
                task.result()
            except BaseException:
                pass


async def dispatch_attention_ack(
    *,
    adapter: Any,
    event: Any,
    platform: str,
    room_id: str,
    actor_id: str,
    policy: AckPolicy,
    journal: AckJournal,
    receipts: ReceiptJournal,
    wake: Mapping[str, Any],
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    token: OpportunityToken,
    deadline: float,
    lifecycle_id: str,
) -> TransportResult:
    """Reserve one shared ACK and add exactly one native reaction.

    Social widening already happened in AttentionEngine. This function rechecks
    the bound permission revision, cancellation, and the one total deadline,
    then calls the shipped adapter method. It does not invoke a participant.
    """

    request_id = str(request["request_id"])
    ack = decision.get("ack") if isinstance(decision, Mapping) else None
    if not isinstance(ack, Mapping):
        result = TransportResult("unavailable", "ACK decision has no authority audit")
        _append_receipt(
            receipts,
            request_id=request_id,
            stage="participant-host",
            writer="participant-host",
            body=participant_host_receipt_body(
                wake,
                expansion_calls=0,
                invoked=False,
                outcome="unknown",
            ),
        )
        _append_receipt(
            receipts,
            request_id=request_id,
            stage="transport",
            writer="transport",
            body={"delivery": result.delivery, "detail": result.detail},
        )
        return result

    remaining = deadline - time.monotonic()
    try:
        current = await probe_reaction_capability(
            adapter,
            event,
            platform=platform,
            room_id=room_id,
            actor_id=actor_id,
            timeout=remaining if remaining > 0 else 0,
        )
    except Exception:
        current = UNAVAILABLE_REACTION_CAPABILITY
    mismatch = (
        not policy.enabled
        or ack.get("reaction") != policy.reaction
        or ack.get("policy_provenance") != policy.provenance
        or ack.get("permissions_revision") != current.permissions_revision
        or not current.allows(policy.reaction, "add")
        or token.cancel_event.is_set()
        or time.monotonic() >= deadline
    )
    if mismatch:
        detail = (
            "ACK cancelled before native dispatch"
            if token.cancel_event.is_set() or time.monotonic() >= deadline
            else "ACK authority changed before dispatch"
        )
        delivery = "failed" if "cancelled" in detail else "unavailable"
        result = TransportResult(delivery, detail)
        _append_receipt(
            receipts,
            request_id=request_id,
            stage="participant-host",
            writer="participant-host",
            body=participant_host_receipt_body(
                wake,
                expansion_calls=0,
                invoked=False,
                outcome="unknown",
            ),
        )
        _append_receipt(
            receipts,
            request_id=request_id,
            stage="transport",
            writer="transport",
            body={"delivery": result.delivery, "detail": result.detail},
        )
        return result

    try:
        method, native_target, chat_id = _native_target(platform, event, room_id)
    except ValueError as exc:
        result = TransportResult("unavailable", str(exc))
        _append_receipt(
            receipts,
            request_id=request_id,
            stage="participant-host",
            writer="participant-host",
            body=participant_host_receipt_body(
                wake,
                expansion_calls=0,
                invoked=False,
                outcome="unknown",
            ),
        )
        _append_receipt(
            receipts,
            request_id=request_id,
            stage="transport",
            writer="transport",
            body={"delivery": result.delivery, "detail": result.detail},
        )
        return result

    binding = {
        "request_id": request_id,
        "participant_id": wake["self"]["participant_id"],
        "actor_id": wake["self"]["actor_id"],
        "platform": wake["room"]["platform"],
        "room_id": wake["room"]["id"],
        "continuity_scope_id": wake["room"]["continuity_scope_id"],
        "target_event_id": wake["trigger_event_id"],
        "reaction": policy.reaction,
        "operation": "add",
        "opportunity_generation": token.generation,
        "lifecycle_id": lifecycle_id,
        "deadline_id": _deadline_id(
            lifecycle_id,
            token.generation,
            deadline,
            current.permissions_revision,
        ),
        "permissions_revision": current.permissions_revision,
    }
    ack_id, reserved = journal.reserve(binding)
    _append_receipt(
        receipts,
        request_id=request_id,
        stage="participant-host",
        writer="participant-host",
        body=participant_host_receipt_body(
            wake,
            expansion_calls=0,
            invoked=False,
            outcome="unknown",
        ),
    )
    if not reserved:
        result = TransportResult("unknown", "duplicate ACK was durably suppressed")
        _append_receipt(
            receipts,
            request_id=request_id,
            stage="transport",
            writer="transport",
            body={"delivery": result.delivery, "detail": result.detail},
        )
        return result

    result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
    try:
        remaining = deadline - time.monotonic()
        try:
            fresh = await probe_reaction_capability(
                adapter,
                event,
                platform=platform,
                room_id=room_id,
                actor_id=actor_id,
                timeout=remaining if remaining > 0 else 0,
            )
        except Exception:
            fresh = UNAVAILABLE_REACTION_CAPABILITY
        if (
            fresh.permissions_revision != binding["permissions_revision"]
            or not fresh.allows(policy.reaction, "add")
        ):
            result = TransportResult(
                "unavailable",
                "ACK authority changed at the native dispatch boundary",
            )
        elif token.cancel_event.is_set() or time.monotonic() >= deadline:
            result = TransportResult("failed", "ACK cancelled before native dispatch")
        else:
            permit = AckEffectPermit(
                adapter=adapter,
                method=method,
                emoji=policy.reaction,
                room_id=str(room_id),
                native_message_id=str(
                    getattr(native_target, "id", native_target)
                ),
                message=native_target if method == "_add_reaction" else None,
                chat_id=chat_id,
            )
            permit_token = _ACK_EFFECT_PERMIT.set(permit)
            try:
                native_method = getattr(adapter, method)
                if method == "_add_reaction":
                    call = native_method(native_target, policy.reaction)
                else:
                    call = native_method(chat_id, str(native_target), policy.reaction)
                kind, value = await _await_native(call, token=token, deadline=deadline)
            finally:
                _ACK_EFFECT_PERMIT.reset(permit_token)
            if kind == "value" and value is True and not token.cancel_event.is_set() and time.monotonic() < deadline:
                result = TransportResult(
                    "sent",
                    f"{platform}:reaction:{getattr(native_target, 'id', native_target)}",
                )
            elif kind == "value" and value is False:
                result = TransportResult("failed", "Hermes reaction method reported failure")
            elif kind == "late" or token.cancel_event.is_set() or time.monotonic() >= deadline:
                result = TransportResult(
                    "unknown",
                    "ACK acknowledgement arrived after the opportunity ended",
                )
            else:
                result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
    except Exception:
        result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
    finally:
        try:
            journal.settle(ack_id, delivery=result.delivery, detail=result.detail)
        except Exception:
            logger.exception("Nunchi could not settle the Hermes ACK journal")
            result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
        try:
            _append_receipt(
                receipts,
                request_id=request_id,
                stage="transport",
                writer="transport",
                body={"delivery": result.delivery, "detail": result.detail},
            )
        except Exception:
            logger.exception("Nunchi could not persist the Hermes ACK transport receipt")
    return result
