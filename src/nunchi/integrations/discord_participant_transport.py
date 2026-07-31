"""One shared Discord consumer transport for every V2 platform integration.

`docs/platform-v2.md` defines a single shared Discord consumer contract: verify
the pinned binding, submit through the authenticated session, and report `sent`
only when the tool payload attests the exact native room, self, content, reply
target, and new native identity.  Every other acknowledgement is `unknown`.

This module is that one implementation.  Platform wrappers import it rather
than maintaining private variants, so a Discord acknowledgement means the same
thing on every surface.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from ..errors import ValidationError
from ..ack import ReactionCapability
from ..mcp_discord.authorization import make_tool_authorization
from ..participant import TransportResult
from .mcp_client import StreamableMCPClient

__all__ = ["MCPDiscordTransport"]


class MCPDiscordTransport:
    def __init__(
        self,
        client: StreamableMCPClient,
        room_id: str,
        participant_id: str,
        actor_id: str,
        output_secret: bytes,
    ) -> None:
        if (
            not isinstance(actor_id, str)
            or not actor_id.startswith("discord:actor:")
            or not actor_id.removeprefix("discord:actor:").isdigit()
        ):
            raise ValidationError("Codex Discord transport actor binding is invalid")
        self.client = client
        self.room_id = room_id
        self.participant_id = participant_id
        self.actor_id = actor_id
        self.native_actor_id = actor_id.removeprefix("discord:actor:")
        self.output_secret = output_secret
        self._reaction_revision = hashlib.sha256(
            b"nunchi-discord-reaction-v1\0"
            + participant_id.encode()
            + b"\0"
            + room_id.encode()
            + b"\0"
            + actor_id.encode()
            + b"\0"
            + output_secret
        ).hexdigest()

    def ordinary_action_capabilities(self) -> tuple[str, ...]:
        return ("message", "reply", "reaction")

    def reaction_capability(self) -> ReactionCapability:
        return ReactionCapability(
            supported=True,
            authenticated=True,
            operations=("add", "remove"),
            reactions=("*",),
            permissions_revision=self._reaction_revision,
        )

    @staticmethod
    def _tool_payload(result: Any) -> tuple[Mapping[str, Any] | None, str]:
        if not isinstance(result, Mapping):
            return None, "unknown"
        if result.get("isError") is True:
            return None, "failed"
        if result.get("isError") is not False:
            return None, "unknown"
        content = result.get("content")
        if not isinstance(content, list) or len(content) != 1:
            return None, "unknown"
        item = content[0]
        if (
            not isinstance(item, Mapping)
            or item.get("type") != "text"
            or not isinstance(item.get("text"), str)
        ):
            return None, "unknown"
        try:
            payload = json.loads(item["text"])
        except json.JSONDecodeError:
            return None, "unknown"
        if not isinstance(payload, Mapping):
            return None, "unknown"
        return payload, "ok"

    def dispatch(self, *, action, wake) -> TransportResult:
        if wake["room"]["id"] != self.room_id:
            return TransportResult("failed", "Discord room binding changed before dispatch")
        if action["kind"] == "message":
            name = "send_message"
            arguments = {"channel_id": self.room_id, "content": action["text"]}
        elif action["kind"] == "reply":
            name = "reply_message"
            target = action["target_event_id"].removeprefix("discord:message:")
            arguments = {
                "channel_id": self.room_id,
                "message_id": target,
                "content": action["text"],
            }
        elif action["kind"] == "reaction":
            name = "add_reaction" if action["operation"] == "add" else "remove_reaction"
            arguments = {
                "channel_id": self.room_id,
                "message_id": action["target_event_id"].removeprefix("discord:message:"),
                "reaction": action["reaction"],
            }
        else:
            return TransportResult("unavailable", "Discord transport action is unsupported")
        arguments["_nunchi_authorization"] = make_tool_authorization(
            secret=self.output_secret,
            request_id=wake["request_id"],
            participant_id=self.participant_id,
            room_id=self.room_id,
            tool=name,
            arguments=arguments,
        )
        try:
            result = self.client.call_tool(name, arguments)
        except BaseException:
            return TransportResult("unknown", "Discord MCP acknowledgement was lost")
        payload, status = self._tool_payload(result)
        if status == "failed":
            return TransportResult("failed", "Discord MCP tool failed")
        if status != "ok" or payload is None:
            return TransportResult(
                "unknown",
                "Discord MCP acknowledgement was malformed or incomplete",
            )
        delivery = payload.get("delivery")
        if (
            isinstance(delivery, Mapping)
            and set(delivery) == {"status", "detail"}
            and delivery.get("status") == "unknown"
            and isinstance(delivery.get("detail"), str)
            and delivery["detail"]
        ):
            return TransportResult(
                "unknown",
                "Discord target acknowledgement did not confirm the effect",
            )
        if name in ("send_message", "reply_message"):
            if set(payload) != {"message"} or not isinstance(
                payload.get("message"), Mapping
            ):
                return TransportResult(
                    "unknown",
                    "Discord message acknowledgement has an invalid shape",
                )
            message = payload["message"]
            message_id = message.get("message_id")
            if (
                not isinstance(message_id, str)
                or not message_id.isdigit()
                or message.get("channel_id") != self.room_id
                or message.get("author_id") != self.native_actor_id
                or message.get("author_is_bot") is not True
                or message.get("content") != action["text"]
                or message.get("reply_to_message_id")
                != (
                    arguments["message_id"]
                    if name == "reply_message"
                    else None
                )
            ):
                return TransportResult(
                    "unknown",
                    "Discord message acknowledgement lacks exact native identity",
                )
            return TransportResult("sent", f"discord:message:{message_id}")
        expected_reaction = {
            "channel_id": self.room_id,
            "message_id": arguments["message_id"],
            "reaction": arguments["reaction"],
            "operation": "add" if name == "add_reaction" else "remove",
        }
        if payload != {"reaction": expected_reaction}:
            return TransportResult(
                "unknown",
                "Discord reaction acknowledgement lacks exact native identity",
            )
        return TransportResult(
            "sent",
            (
                f"discord:reaction:{arguments['message_id']}:"
                f"{arguments['reaction']}:{expected_reaction['operation']}"
            ),
        )
