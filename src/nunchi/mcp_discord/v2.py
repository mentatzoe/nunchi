"""V2 Discord participant-action transport seam."""

from __future__ import annotations

import copy
import threading
from typing import Any, Callable, Protocol

from ..receipts import transport_receipt
from .ratelimit import SendBackstop
from .rest import DiscordRestError


class DiscordV2ActionError(RuntimeError):
    pass


class DiscordV2RestLike(Protocol):
    def create_message(
        self,
        channel_id: str,
        content: str,
        *,
        reply_to_message_id: str | None = None,
        allowed_mention_user_ids: tuple[str, ...] | None = None,
        fail_if_reply_missing: bool = False,
    ) -> dict: ...

    def create_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> None: ...


class MCPToolClientLike(Protocol):
    def call_tool(self, name: str, arguments: dict) -> dict: ...


def _snowflake(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if text.isdigit() else None


def _event_snowflake(value: object, prefix: str) -> str | None:
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    return _snowflake(value[len(prefix):])


def _actor_snowflake(value: object) -> str | None:
    return _event_snowflake(value, "discord:user:")


class DiscordActionSinkV2:
    """Send one request-correlated room action without social reclassification.

    The channel is bound at construction from trusted host configuration. Room
    content and participant output cannot redirect it. Discord allowed-mentions
    is closed by default; only exact ``mention_actor_ids`` are permitted to ping.
    """

    def __init__(
        self,
        *,
        channel_id: str,
        rest: DiscordV2RestLike,
        backstop: SendBackstop,
        receipt_sink: Callable[[dict[str, Any]], None],
    ) -> None:
        resolved_channel = _snowflake(channel_id)
        if resolved_channel is None:
            raise ValueError("Discord action channel must be an exact snowflake")
        if not callable(receipt_sink) or not isinstance(backstop, SendBackstop):
            raise ValueError("Discord action transport dependency is invalid")
        self.channel_id = resolved_channel
        self.rest = rest
        self.backstop = backstop
        self.receipt_sink = receipt_sink
        self._lock = threading.RLock()
        self._consumed_request_ids: set[str] = set()

    def _write(self, request_id: str, delivery: str, detail: str | None = None) -> None:
        self.receipt_sink(transport_receipt(request_id, delivery, detail=detail))

    def _fail(self, request_id: str, detail: str) -> None:
        try:
            self._write(request_id, "failed", detail)
        except Exception as exc:
            raise DiscordV2ActionError("Discord action and receipt status are unknown") from exc
        raise DiscordV2ActionError(f"Discord action failed: {detail}")

    def __call__(self, request_id: str, action: dict[str, Any]) -> None:
        if not isinstance(request_id, str) or not request_id:
            raise DiscordV2ActionError("Discord action request correlation is invalid")
        try:
            accepted = copy.deepcopy(action)
        except Exception as exc:
            raise DiscordV2ActionError("Discord action is invalid") from exc
        with self._lock:
            if request_id in self._consumed_request_ids:
                raise DiscordV2ActionError("Discord action request was already consumed")
            self._consumed_request_ids.add(request_id)

        kind = accepted.get("kind") if isinstance(accepted, dict) else None
        wait = self.backstop.try_acquire(self.channel_id)
        if wait > 0:
            self._fail(request_id, "send-backstop")
        try:
            if kind == "message":
                self._send_message(accepted)
            elif kind == "reaction":
                self._send_reaction(accepted)
            else:
                self._fail(request_id, "unsupported-action")
        except DiscordV2ActionError:
            raise
        except (DiscordRestError, OSError, ValueError):
            self._fail(request_id, "discord-api-failure")
        except Exception:
            self._fail(request_id, "transport-failure")
        try:
            self._write(request_id, "sent")
        except Exception as exc:
            raise DiscordV2ActionError("Discord send receipt persistence is unknown") from exc

    def _send_message(self, action: dict[str, Any]) -> None:
        content = action.get("content")
        if not isinstance(content, str) or not content or len(content) > 2000:
            raise ValueError("invalid content")
        reply_to = None
        if "reply_to_event_id" in action:
            reply_to = _event_snowflake(
                action.get("reply_to_event_id"),
                "discord:message:",
            )
            if reply_to is None:
                raise ValueError("invalid reply target")
        mention_ids: list[str] = []
        seen: set[str] = set()
        for actor_id in action.get("mention_actor_ids", []):
            user_id = _actor_snowflake(actor_id)
            if user_id is None:
                raise ValueError("invalid mention actor")
            if user_id not in seen:
                seen.add(user_id)
                mention_ids.append(user_id)
        self.rest.create_message(
            self.channel_id,
            content,
            reply_to_message_id=reply_to,
            allowed_mention_user_ids=tuple(mention_ids),
            fail_if_reply_missing=reply_to is not None,
        )

    def _send_reaction(self, action: dict[str, Any]) -> None:
        target = _event_snowflake(
            action.get("target_event_id"),
            "discord:message:",
        )
        reaction = action.get("reaction")
        if target is None or not isinstance(reaction, str) or not reaction:
            raise ValueError("invalid reaction")
        self.rest.create_reaction(self.channel_id, target, reaction)


class MCPDiscordActionSinkV2:
    """Request-correlated Discord action sink over the trusted local MCP server."""

    def __init__(
        self,
        *,
        channel_id: str,
        client: MCPToolClientLike,
        receipt_sink: Callable[[dict[str, Any]], None],
    ) -> None:
        resolved = _snowflake(channel_id)
        if resolved is None or not callable(receipt_sink):
            raise ValueError("Discord MCP action binding is invalid")
        self.channel_id = resolved
        self.client = client
        self.receipt_sink = receipt_sink
        self._lock = threading.RLock()
        self._consumed_request_ids: set[str] = set()

    def _receipt(self, request_id: str, delivery: str, detail: str | None = None) -> None:
        self.receipt_sink(transport_receipt(request_id, delivery, detail=detail))

    def __call__(self, request_id: str, action: dict[str, Any]) -> None:
        if not isinstance(request_id, str) or not request_id:
            raise DiscordV2ActionError("Discord MCP action correlation is invalid")
        with self._lock:
            if request_id in self._consumed_request_ids:
                raise DiscordV2ActionError("Discord MCP action request was already consumed")
            self._consumed_request_ids.add(request_id)
        try:
            accepted = copy.deepcopy(action)
            kind = accepted.get("kind") if isinstance(accepted, dict) else None
            if kind == "message":
                content = accepted.get("content")
                if not isinstance(content, str) or not content or len(content) > 2000:
                    raise ValueError("invalid message")
                arguments: dict[str, Any] = {
                    "channel_id": self.channel_id,
                    "content": content,
                }
                mentions: list[str] = []
                for actor_id in accepted.get("mention_actor_ids", []):
                    user_id = _actor_snowflake(actor_id)
                    if user_id is None:
                        raise ValueError("invalid mention")
                    if user_id not in mentions:
                        mentions.append(user_id)
                if mentions:
                    arguments["mention_user_ids"] = mentions
                reply = accepted.get("reply_to_event_id")
                if reply is None:
                    tool = "send_message"
                else:
                    reply_id = _event_snowflake(reply, "discord:message:")
                    if reply_id is None:
                        raise ValueError("invalid reply")
                    tool = "reply_message"
                    arguments["message_id"] = reply_id
                self.client.call_tool(tool, arguments)
            elif kind == "reaction":
                target = _event_snowflake(
                    accepted.get("target_event_id"),
                    "discord:message:",
                )
                reaction = accepted.get("reaction")
                if target is None or not isinstance(reaction, str) or not reaction:
                    raise ValueError("invalid reaction")
                self.client.call_tool(
                    "add_reaction",
                    {
                        "channel_id": self.channel_id,
                        "message_id": target,
                        "reaction": reaction,
                    },
                )
            else:
                raise ValueError("unsupported action")
        except Exception as exc:
            try:
                self._receipt(request_id, "failed", "mcp-discord-action-failure")
            except Exception as receipt_exc:
                raise DiscordV2ActionError(
                    "Discord MCP action and receipt status are unknown"
                ) from receipt_exc
            raise DiscordV2ActionError("Discord MCP action failed") from exc
        try:
            self._receipt(request_id, "sent")
        except Exception as exc:
            raise DiscordV2ActionError("Discord MCP send receipt persistence is unknown") from exc


__all__ = [
    "DiscordActionSinkV2",
    "MCPDiscordActionSinkV2",
    "DiscordV2ActionError",
    "transport_receipt",
]
