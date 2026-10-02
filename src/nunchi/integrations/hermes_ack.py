"""Authenticated Hermes reaction facts and one exact native ACK effect.

AttentionEngine still owns ACK selection and capability widening. This module
only reads current platform permission facts and performs the one native
reaction those facts allow. It does not judge social meaning, and it does not
copy a second ACK policy.

The native call is awaited outside the shared scheduler lock and the room
runtime lock. Authority is consumed at the native method's entry, under the
scheduler lock and before the network await. A lost or late result is unknown
and is not retried. Journal and receipt writes run off the gateway loop. Lock
waits are bounded; active file I/O cannot be cancelled in Python and remains
owned until it actually finishes (including any uncertain-write rollback).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
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
    ConversationOpportunityScheduler,
    OpportunityToken,
    TransportResult,
    participant_host_receipt_body,
)
from nunchi.receipts import PersistenceError, ReceiptJournal

logger = logging.getLogger(__name__)

_ACK_EFFECT_PERMIT: ContextVar["AckEffectPermit | None"] = ContextVar(
    "nunchi_hermes_ack_effect_permit",
    default=None,
)
_PERSISTENCE_CLEANUP_SECONDS = 2.0
_OWNED_NATIVE: set[asyncio.Task[Any]] = set()
_OWNED_PERSISTENCE: set[Any] = set()
_OWNERSHIP_LOCK = threading.Lock()


class AckAuthorityClosed(Exception):
    """The call matched a permit whose opportunity may no longer commit."""


def ack_effects_quiescent() -> bool:
    """Return whether every ACK child and late writer has finished."""

    with _OWNERSHIP_LOCK:
        natives = {task for task in _OWNED_NATIVE if not task.done()}
        writers = {item for item in _OWNED_PERSISTENCE if not item.done()}
        _OWNED_NATIVE.clear()
        _OWNED_NATIVE.update(natives)
        _OWNED_PERSISTENCE.clear()
        _OWNED_PERSISTENCE.update(writers)
        return not natives and not writers


def _own_native(task: asyncio.Task[Any]) -> None:
    with _OWNERSHIP_LOCK:
        _OWNED_NATIVE.add(task)

    def _finished(done: asyncio.Task[Any]) -> None:
        _consume_task(done)
        with _OWNERSHIP_LOCK:
            _OWNED_NATIVE.discard(done)

    task.add_done_callback(_finished)


def _own_future(future: Any) -> None:
    with _OWNERSHIP_LOCK:
        _OWNED_PERSISTENCE.add(future)

    def _finished(done: Any) -> None:
        _consume_future(done)
        with _OWNERSHIP_LOCK:
            _OWNED_PERSISTENCE.discard(done)

    future.add_done_callback(_finished)


def _consume_task(task: asyncio.Task[Any]) -> None:
    if not task.done():
        return
    try:
        task.exception()
    except BaseException:
        pass


def _consume_future(future: Any) -> None:
    if not future.done():
        return
    try:
        future.exception()
    except BaseException:
        pass


async def drain_ack_ownership(timeout: float = _PERSISTENCE_CLEANUP_SECONDS + 0.5) -> bool:
    """Wait until owned ACK children and writers finish, without blocking the loop."""

    deadline = time.monotonic() + timeout
    while not ack_effects_quiescent():
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(0.01)
    return True


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
    scheduler: ConversationOpportunityScheduler | None = None
    token: OpportunityToken | None = None
    deadline: float = 0.0
    consumed: bool = False
    revoked: bool = False
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

    def revoke(self) -> None:
        """Refuse a later commit. Does not undo a call that already passed it."""

        with self._lock:
            self.revoked = True


def ack_effect_permit_present() -> bool:
    """Return whether this task has an ACK permit, valid or not."""

    return _ACK_EFFECT_PERMIT.get() is not None


def claim_ack_effect(
    adapter: Any,
    method: str,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> bool:
    """Consume the current task's permit only at the actual effect commit.

    No permit means there is no ACK context, so return False and let ordinary
    traffic fall through. A present permit that is spent, revoked, mismatched,
    or no longer current raises ``AckAuthorityClosed``. Returning False for
    that call would let the stock guard treat it as ordinary unconfigured
    traffic.
    """

    permit = _ACK_EFFECT_PERMIT.get()
    if permit is None:
        return False
    with permit._lock:
        if (
            permit.consumed
            or permit.revoked
            or not permit.matches(adapter, method, args, kwargs)
        ):
            raise AckAuthorityClosed("ACK effect authority does not allow this call")
        scheduler = permit.scheduler
        token = permit.token
        if (
            scheduler is None
            or token is None
            or not scheduler.authorize_effect_commit(token, deadline=permit.deadline)
        ):
            raise AckAuthorityClosed("ACK effect authority is no longer current")
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
    deadline: float | None = None,
) -> None:
    lock = receipts._lock
    held = False
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining < 0:
            remaining = 0
        if not lock.acquire(timeout=remaining):
            raise PersistenceError(
                "receipt journal lock was not acquired before the deadline"
            )
        held = True
    try:
        if deadline is not None and time.monotonic() >= deadline:
            raise PersistenceError("receipt persistence deadline exhausted")
        receipts.append(
            {
                "request_id": request_id,
                "stage": stage,
                "writer": writer,
                "body": dict(body),
            },
            writer=writer,
        )
    finally:
        if held:
            lock.release()


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


async def _off_loop(fn: Callable[[], Any], *, wait: float) -> Any:
    """Run one blocking persistence call off the gateway loop."""

    if wait <= 0:
        raise PersistenceError("ACK persistence deadline exhausted")
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, fn)
    try:
        return await asyncio.wait_for(asyncio.shield(future), wait)
    except TimeoutError as exc:
        _own_future(future)
        raise PersistenceError(
            "ACK persistence exceeded the opportunity deadline"
        ) from exc
    except asyncio.CancelledError:
        _own_future(future)
        raise
    except PersistenceError:
        _consume_future(future)
        raise


def _settle_quietly(
    journal: AckJournal,
    ack_id: str,
    *,
    delivery: str,
    detail: str,
    deadline: float,
) -> None:
    try:
        journal.settle(
            ack_id,
            delivery=delivery,
            detail=detail,
            deadline=deadline,
        )
    except PersistenceError:
        logger.warning("Hermes ACK settlement missed its absolute deadline")
    except Exception:
        logger.exception("Nunchi could not finish a late Hermes ACK settlement")


def _suppress_late_reservation(
    journal: AckJournal,
    binding: Mapping[str, Any],
    *,
    deadline: float,
) -> None:
    """Reserve after a refused dispatch, then settle failed. Never dispatch."""

    try:
        ack_id, reserved = journal.reserve(binding, deadline=deadline)
    except PersistenceError:
        logger.warning(
            "Hermes ACK reservation was not durable before the cleanup bound"
        )
        return
    if reserved:
        _settle_quietly(
            journal,
            ack_id,
            delivery="failed",
            detail="ACK reservation completed after dispatch was refused",
            deadline=deadline,
        )


async def _reserve_before_dispatch(
    journal: AckJournal,
    binding: Mapping[str, Any],
    *,
    deadline: float,
) -> tuple[str | None, str]:
    """Return ``(ack_id, status)`` with status reserved, duplicate, or refused.

    A refused reservation does not dispatch. If the lock lands after that
    refusal, the tracked worker settles it failed so replay cannot emit.
    """

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, "refused"
    cleanup_end = deadline + _PERSISTENCE_CLEANUP_SECONDS
    state: dict[str, Any] = {
        "abandoned": False,
        "ready": threading.Event(),
        "ack_id": None,
        "reserved": False,
        "error": None,
    }
    gate = threading.Lock()

    def attempt() -> None:
        try:
            ack_id, reserved = journal.reserve(binding, deadline=deadline)
        except PersistenceError as exc:
            with gate:
                abandoned = state["abandoned"]
                if not abandoned:
                    # Publish the error atomically with readiness: the observer
                    # must either own this failure's cleanup or leave it to us.
                    state["error"] = exc
                    state["ready"].set()
            if abandoned:
                _suppress_late_reservation(
                    journal,
                    binding,
                    deadline=cleanup_end,
                )
                state["ready"].set()
            return
        with gate:
            if state["abandoned"]:
                if reserved:
                    _settle_quietly(
                        journal,
                        ack_id,
                        delivery="failed",
                        detail="ACK reservation completed after dispatch was refused",
                        deadline=cleanup_end,
                    )
                state["ready"].set()
                return
            state["ack_id"] = ack_id
            state["reserved"] = reserved
            state["ready"].set()

    def cleanup_attempt() -> None:
        _suppress_late_reservation(journal, binding, deadline=cleanup_end)

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, attempt)
    try:
        completed = await asyncio.wait_for(
            asyncio.shield(asyncio.to_thread(state["ready"].wait, remaining)),
            remaining + 0.02,
        )
        if not completed:
            # threading.Event.wait times out by returning False, not raising.
            # The worker still owns a reservation attempt and must be abandoned
            # and tracked just as when the asyncio observer timer expires.
            raise TimeoutError
    except TimeoutError:
        with gate:
            cleanup_needed = state["error"] is not None
            if state["ready"].is_set() and not cleanup_needed:
                ack_id = state["ack_id"]
                reserved = bool(state["reserved"])
            else:
                state["abandoned"] = True
                ack_id = None
                reserved = False
        if ack_id is None:
            _own_future(future)
            if cleanup_needed:
                # A completed error cannot observe our abandonment itself.
                _own_future(loop.run_in_executor(None, cleanup_attempt))
            return None, "refused"
        _consume_future(future)
        return ack_id, "reserved" if reserved else "duplicate"
    except asyncio.CancelledError:
        with gate:
            state["abandoned"] = True
            cleanup_needed = state["error"] is not None
        _own_future(future)
        if cleanup_needed:
            _own_future(loop.run_in_executor(None, cleanup_attempt))
        raise
    _consume_future(future)
    if state["error"] is not None:
        with gate:
            state["abandoned"] = True
        cleanup = loop.run_in_executor(None, cleanup_attempt)
        _own_future(cleanup)
        return None, "refused"
    if not state["reserved"]:
        return state["ack_id"], "duplicate"
    return state["ack_id"], "reserved"


async def _settle_observed(
    journal: AckJournal,
    ack_id: str,
    result: TransportResult,
    *,
    deadline: float,
    abandoned: threading.Event | None = None,
) -> bool:
    """Settle off-loop, accepting only the requested durable outcome.

    Lock waits use an absolute budget. Active file I/O remains owned until it
    completes, and the journal withdraws writes that complete late/abandoned.
    """
    remaining = deadline - time.monotonic()
    cleanup_end = deadline + _PERSISTENCE_CLEANUP_SECONDS
    confirmed = threading.Event()
    abandoned = abandoned if abandoned is not None else threading.Event()
    ok = {"value": False}
    gate = threading.Lock()

    def confirm(actual: str) -> None:
        # No I/O under this gate: atomically choose confirmation or abandonment.
        with gate:
            if abandoned.is_set() or time.monotonic() >= deadline:
                raise PersistenceError("ACK confirmation arrived after abandonment")
            ok["value"] = actual == result.delivery
            confirmed.set()

    def abandon() -> bool:
        with gate:
            if not confirmed.is_set():
                abandoned.set()
            return bool(ok["value"])

    def attempt() -> None:
        try:
            if time.monotonic() < deadline:
                journal.settle(
                    ack_id, delivery=result.delivery, detail=result.detail,
                    deadline=deadline, abandoned=abandoned, confirm=confirm,
                )
        except PersistenceError:
            pass
        finally:
            confirmed.set()
        if not ok["value"]:
            _settle_quietly(
                journal, ack_id, delivery="unknown",
                detail="ACK dispatch acknowledgement was lost",
                deadline=cleanup_end,
            )

    future = asyncio.get_running_loop().run_in_executor(None, attempt)
    _own_future(future)
    if remaining <= 0:
        return abandon()
    try:
        await asyncio.wait_for(
            asyncio.shield(asyncio.to_thread(confirmed.wait, remaining)),
            remaining + 0.02,
        )
    except TimeoutError:
        return abandon()
    except asyncio.CancelledError:
        abandon()
        raise
    return abandon()


async def _write_receipt(
    receipts: ReceiptJournal,
    *,
    deadline: float,
    request_id: str,
    stage: str,
    writer: str,
    body: Mapping[str, Any],
    observe_completion: bool = False,
) -> bool:
    remaining = deadline - time.monotonic()
    wait = remaining if remaining > 0 else 0.05
    absolute = deadline if remaining > 0 else time.monotonic() + wait

    def attempt() -> None:
        _append_receipt(
            receipts,
            request_id=request_id,
            stage=stage,
            writer=writer,
            body=body,
            deadline=absolute,
        )

    try:
        if observe_completion:
            # Stage ordering depends on this exact write, not a second attempt.
            # Lock acquisition is bounded; active kernel I/O is not cancellable.
            future = asyncio.get_running_loop().run_in_executor(None, attempt)
            _own_future(future)
            await asyncio.shield(future)
        else:
            await _off_loop(attempt, wait=max(0.01, wait))
    except PersistenceError:
        logger.exception("Nunchi could not persist the Hermes ACK receipt")
        return False
    return True


async def _close_ack(
    journal: AckJournal,
    receipts: ReceiptJournal,
    ack_id: str,
    result: TransportResult,
    *,
    deadline: float,
    request_id: str,
    abandoned: threading.Event | None = None,
) -> TransportResult:
    """Observe one settlement and write one terminal receipt. Never retry effects."""

    cleanup_end = deadline + _PERSISTENCE_CLEANUP_SECONDS
    closed = result
    try:
        confirmed = await _settle_observed(
            journal,
            ack_id,
            result,
            deadline=deadline,
            abandoned=abandoned,
        )
        if not confirmed:
            closed = TransportResult(
                "unknown",
                "ACK dispatch acknowledgement was lost",
            )
    finally:
        await _write_receipt(
            receipts,
            deadline=cleanup_end,
            request_id=request_id,
            stage="transport",
            writer="transport",
            body={"delivery": closed.delivery, "detail": closed.detail},
            observe_completion=True,
        )
    return closed


async def _finish_owned(task: asyncio.Task[Any]) -> None:
    """Wait for a closure task without letting parent cancellation abandon it."""

    current = asyncio.current_task()
    try:
        while not task.done():
            if current is not None:
                while current.cancelling():
                    current.uncancel()
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if task.done() and not task.cancelled():
            try:
                task.result()
            except Exception:
                logger.exception("Nunchi could not close a cancelled Hermes ACK")
    finally:
        if task.done():
            _consume_task(task)
        else:
            _own_future(task)


async def _await_cancelled_closure(task: asyncio.Task[Any]) -> None:
    """Enter closure even if Python 3.11 still has a cancellation armed."""

    current = asyncio.current_task()
    while not task.done():
        if current is not None:
            while current.cancelling():
                current.uncancel()
        try:
            await _finish_owned(task)
            return
        except asyncio.CancelledError:
            continue
    await _finish_owned(task)


async def _stop_native(native: asyncio.Task[Any], permit: AckEffectPermit) -> None:
    """Cancel the child and revoke unused authority. A resistant child stays owned.

    Do not schedule another parent cancellation from here. On Python 3.11 that
    request stays armed after ``uncancel()`` and interrupts receipt closure.
    """

    permit.revoke()
    if native.done():
        _consume_task(native)
        return
    native.cancel()
    current = asyncio.current_task()
    if current is not None and current.cancelling():
        while current.cancelling():
            current.uncancel()
        try:
            await asyncio.wait({native}, timeout=0)
        except asyncio.CancelledError:
            while current.cancelling():
                current.uncancel()
        return
    await asyncio.wait({native}, timeout=0.05)
    _consume_task(native)


async def _await_native(
    call: Any,
    *,
    token: OpportunityToken,
    deadline: float,
    permit: AckEffectPermit,
) -> tuple[str, Any]:
    """Wait for one native call without holding scheduler or runtime locks.

    The child is owned until it terminates. Parent cancellation cancels that
    child and revokes authority that has not yet committed.
    """

    native = asyncio.create_task(call)
    _own_native(native)
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
            await _stop_native(native, permit)
            return "late", None
        done, _pending = await asyncio.wait(
            {native, watcher},
            timeout=max(0.0, remaining),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if native in done and not native.cancelled():
            try:
                return "value", native.result()
            except AckAuthorityClosed:
                return "rejected", None
            except asyncio.CancelledError:
                return "lost", None
            except Exception:
                logger.debug("Hermes ACK native call failed", exc_info=True)
                return "lost", None
        await _stop_native(native, permit)
        return "late", None
    except asyncio.CancelledError:
        await _stop_native(native, permit)
        raise
    finally:
        watcher.cancel()
        current = asyncio.current_task()
        if watcher.done():
            _consume_task(watcher)
        elif current is None or current.cancelling() == 0:
            await asyncio.wait({watcher}, timeout=0)
            if watcher.done():
                _consume_task(watcher)
            else:
                _own_native(watcher)
        else:
            _own_native(watcher)


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
    scheduler: ConversationOpportunityScheduler,
) -> TransportResult:
    """Reserve one shared ACK and add exactly one native reaction.

    Social widening already happened in AttentionEngine. This function rechecks
    the bound permission revision, cancellation, and the one total deadline,
    then calls the shipped adapter method. The permit consumes authority at
    native entry. Persistence waits off the gateway loop. It does not invoke
    a participant.
    """

    request_id = str(request["request_id"])

    async def _close(result: TransportResult) -> TransportResult:
        await _write_receipt(
            receipts,
            deadline=deadline,
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
        await _write_receipt(
            receipts,
            deadline=deadline,
            request_id=request_id,
            stage="transport",
            writer="transport",
            body={"delivery": result.delivery, "detail": result.detail},
        )
        return result

    ack = decision.get("ack") if isinstance(decision, Mapping) else None
    if not isinstance(ack, Mapping):
        return await _close(
            TransportResult("unavailable", "ACK decision has no authority audit")
        )

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
        return await _close(TransportResult(delivery, detail))

    try:
        method, native_target, chat_id = _native_target(platform, event, room_id)
    except ValueError as exc:
        return await _close(TransportResult("unavailable", str(exc)))

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
    async def prepare() -> tuple[str | None, str, bool]:
        ack_id, reservation = await _reserve_before_dispatch(
            journal, binding, deadline=deadline,
        )
        handoff = await _write_receipt(
            receipts,
            deadline=deadline,
            request_id=request_id,
            stage="participant-host",
            writer="participant-host",
            body=participant_host_receipt_body(
                wake, expansion_calls=0, invoked=False, outcome="unknown",
            ),
            observe_completion=True,
        )
        return ack_id, reservation, handoff

    # Preparation cannot dispatch. Keep its exact reservation and handoff write
    # alive across cancellation, including a cancellation racing completion.
    preparation = asyncio.create_task(prepare())
    _own_future(preparation)
    try:
        ack_id, reservation, handoff = await asyncio.shield(preparation)
    except asyncio.CancelledError:
        async def close_preparation() -> None:
            ack_id, reservation, _handoff = await preparation
            result = TransportResult("failed", "ACK cancelled before native dispatch")
            if ack_id is not None and reservation == "reserved":
                await _close_ack(
                    journal, receipts, ack_id, result,
                    deadline=deadline,
                    request_id=request_id,
                )
            else:
                await _write_receipt(
                    receipts, deadline=deadline + _PERSISTENCE_CLEANUP_SECONDS,
                    request_id=request_id, stage="transport", writer="transport",
                    body={"delivery": result.delivery, "detail": result.detail},
                    observe_completion=True,
                )

        closure = asyncio.create_task(close_preparation())
        _own_future(closure)
        await _await_cancelled_closure(closure)
        raise

    if reservation != "reserved" or not handoff:
        if reservation == "duplicate":
            result = TransportResult("unknown", "duplicate ACK was durably suppressed")
        elif reservation != "reserved":
            result = TransportResult("failed", "ACK reservation was not durable before dispatch")
        else:
            result = TransportResult("failed", "ACK handoff was not durable before native dispatch")

        async def close_refused() -> TransportResult:
            if ack_id is not None and reservation == "reserved":
                return await _close_ack(
                    journal, receipts, ack_id, result, deadline=deadline,
                    request_id=request_id,
                )
            await _write_receipt(
                receipts, deadline=deadline + _PERSISTENCE_CLEANUP_SECONDS,
                request_id=request_id, stage="transport", writer="transport",
                body={"delivery": result.delivery, "detail": result.detail},
                observe_completion=True,
            )
            return result

        closure = asyncio.create_task(close_refused())
        _own_future(closure)
        try:
            return await asyncio.shield(closure)
        except asyncio.CancelledError:
            await _await_cancelled_closure(closure)
            raise

    result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
    permit: AckEffectPermit | None = None
    cancelled_dispatch = False
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
                scheduler=scheduler,
                token=token,
                deadline=deadline,
            )
            permit_token = _ACK_EFFECT_PERMIT.set(permit)
            try:
                native_method = getattr(adapter, method)
                if method == "_add_reaction":
                    call = native_method(native_target, policy.reaction)
                else:
                    call = native_method(chat_id, str(native_target), policy.reaction)
                kind, value = await _await_native(
                    call,
                    token=token,
                    deadline=deadline,
                    permit=permit,
                )
            finally:
                _ACK_EFFECT_PERMIT.reset(permit_token)
            if kind == "rejected":
                result = TransportResult("failed", "ACK cancelled before native dispatch")
            elif (
                kind == "value"
                and value is True
                and not token.cancel_event.is_set()
                and time.monotonic() < deadline
            ):
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
    except asyncio.CancelledError:
        result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
        if permit is not None:
            permit.revoke()
        cancelled_dispatch = True
        raise
    except Exception:
        result = TransportResult("unknown", "ACK dispatch acknowledgement was lost")
    finally:
        if ack_id is not None:
            abandoned = threading.Event()

            # One finalization owns both persistence and the terminal receipt.
            # Never start a second write when cancellation races their completion.
            closure = asyncio.create_task(_close_ack(
                journal, receipts, ack_id, result, deadline=deadline,
                request_id=request_id, abandoned=abandoned,
            ))
            _own_future(closure)
            if cancelled_dispatch:
                await _await_cancelled_closure(closure)
            else:
                try:
                    result = await asyncio.shield(closure)
                except asyncio.CancelledError:
                    abandoned.set()
                    await _await_cancelled_closure(closure)
                    raise
    return result
