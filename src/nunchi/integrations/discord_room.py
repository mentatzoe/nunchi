"""The room connection every library-hosted integration shares (#94 step 9e).

A library-hosted harness (Claude Code, Codex) leaves the room to Nunchi: the
shared Discord transport (`nunchi.mcp_discord`) delivers each event, and Nunchi
posts through it. This module is that connection, once: it registers the
participant with the transport and checks its attestation, validates each
notification, hands events to the `Room`, marks a continuity gap when the
stream is uncertain, and reconnects. An integration builds its `Room` with
`DiscordRoomConnection.transport`, attaches the room, and calls `serve`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
import sys
import threading
import time
from typing import Any
import urllib.error

from ..errors import ValidationError
from ..mcp_discord.authorization import make_tool_authorization
from ..mcp_discord.events import NOTIFICATION_METHOD
from ..observation import ParticipantBinding
from ..pipeline import DeliveryOutcome
from ..v2_contracts import validate_canonical_event
from .discord_participant_transport import MCPDiscordTransport
from .mcp_client import StreamableMCPClient

TRANSPORT_KEYS = frozenset({"url", "timeout_seconds", "output_key_env"})
_NOTIFICATION_KEYS = frozenset(
    {
        "schema_version",
        "delivery_id",
        "room_id",
        "event",
        "actors",
        "continuity_gap",
        "target_participant_id",
        "transport_self_actor_id",
    }
)
_MAX_RECONNECT_SECONDS = 30.0


def output_secret(transport: Any, *, label: str, environ: Mapping[str, str] | None = None) -> bytes:
    """The key that authorizes this participant's posts, from the environment."""

    if not isinstance(transport, Mapping):
        raise ValidationError(f"{label} transport config must be an object")
    env_name = transport.get("output_key_env")
    if not isinstance(env_name, str) or not env_name:
        raise ValidationError(f"{label} transport output_key_env must be non-empty")
    value = (os.environ if environ is None else environ).get(env_name)
    if value is None or len(value.encode()) < 32:
        raise ValidationError(
            f"{label} transport output authorization key is absent or short in {env_name}"
        )
    return value.encode()


def transport_client(transport: Any, *, label: str) -> StreamableMCPClient:
    """The client for the shared transport the config names."""

    if not isinstance(transport, Mapping) or set(transport) != TRANSPORT_KEYS:
        raise ValidationError(f"{label} shared transport config is invalid")
    return StreamableMCPClient(
        str(transport["url"]), timeout_seconds=float(transport["timeout_seconds"])
    )


class DiscordRoomConnection:
    """One participant's room on the shared Discord transport.

    ``transport`` posts the room actions the host commits; build the `Room`
    with it, then `attach` the room. ``label`` names the integration in log
    lines, and ``surface`` in the ids of the gaps it records.
    """

    def __init__(
        self,
        *,
        client: StreamableMCPClient,
        binding: ParticipantBinding,
        secret: bytes,
        label: str,
        surface: str,
    ) -> None:
        self.client = client
        self.binding = binding
        self.secret = secret
        self.label = label
        self.surface = surface
        self.transport = MCPDiscordTransport(
            client, binding.room_id, binding.participant_id, binding.actor_id, secret
        )
        self.room: Any = None

    def attach(self, room: Any) -> None:
        self.room = room

    def handle(self, params: Mapping[str, Any]) -> DeliveryOutcome:
        """One notification from the shared transport: an event, or a gap."""

        if not isinstance(params, Mapping) or set(params) != _NOTIFICATION_KEYS:
            raise ValidationError("shared Discord notification has an invalid V2 shape")
        if params["schema_version"] != 2:
            raise ValidationError("shared Discord notification is not V2")
        if not isinstance(params["continuity_gap"], bool):
            raise ValidationError("shared Discord continuity_gap must be a boolean")
        if params["target_participant_id"] != self.binding.participant_id:
            raise ValidationError("shared Discord notification targets another participant")
        if params["transport_self_actor_id"] != self.binding.actor_id:
            raise ValidationError("authenticated Discord self differs from exact binding")
        if str(params["room_id"]) != self.binding.room_id:
            raise ValidationError("shared Discord notification targets another room")
        room = self._room()
        if params["continuity_gap"]:
            if params["event"] is not None or params["actors"] != {}:
                raise ValidationError("Discord gap notification cannot fabricate event facts")
            room.cancel()
            observed = room.observation.mark_continuity_gap(
                delivery_id=str(params["delivery_id"]),
                detail="shared Discord transport declared a bounded queue gap",
            )
            return DeliveryOutcome(observed, (), False)
        event = validate_canonical_event(params["event"]) if params["event"] is not None else None
        return room.deliver(
            delivery_id=params["delivery_id"],
            event=event,
            actors=params["actors"],
            authorized_route=True,
        )

    def register(self) -> None:
        """Register the participant with the transport and check its attestation."""

        arguments = {
            "participant_id": self.binding.participant_id,
            "channel_id": self.binding.room_id,
        }
        supplied = {
            **arguments,
            "_nunchi_authorization": make_tool_authorization(
                secret=self.secret,
                request_id=f"transport-registration-{time.time_ns()}",
                participant_id=self.binding.participant_id,
                room_id=self.binding.room_id,
                tool="register_participant",
                arguments=arguments,
            ),
        }
        result = self.client.call_tool("register_participant", supplied)
        if not isinstance(result, Mapping) or result.get("isError") is True:
            raise RuntimeError("shared Discord participant registration failed")
        content = result.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise RuntimeError("shared Discord registration returned an invalid result")
        item = content[0]
        text = item.get("text") if isinstance(item, Mapping) else None
        if not isinstance(text, str):
            raise RuntimeError("shared Discord registration omitted its attestation")
        try:
            attestation = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("shared Discord registration attestation is malformed") from exc
        if attestation != {
            "registered": True,
            "participant_id": self.binding.participant_id,
            "room_id": self.binding.room_id,
            "transport_self_actor_id": self.binding.actor_id,
        }:
            raise RuntimeError("shared Discord registration attestation binding differs")

    def interrupted(self) -> None:
        """The stream is uncertain: cancel running work and record the gap."""

        room = self._room()
        room.cancel()
        room.observation.mark_continuity_gap(
            delivery_id=f"discord:{self.surface}-stream-gap:{time.time_ns()}",
            detail="shared Discord notification stream continuity is uncertain",
        )

    def serve(
        self,
        *,
        stop: threading.Event | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Connect, register and hand every event to the room; reconnect on errors.

        Runs until ``stop`` is set (checked between connections), or forever.
        """

        delay = 1.0
        while stop is None or not stop.is_set():
            try:
                self.client.connect()
                self.register()
                for method, params in self.client.notifications():
                    if method == NOTIFICATION_METHOD:
                        self.handle(params)
                    if stop is not None and stop.is_set():
                        break
                self.interrupted()
                delay = 1.0
            except (urllib.error.URLError, RuntimeError, OSError):
                self.interrupted()
                print(
                    f"{self.label} shared transport reconnect after operational error",
                    file=sys.stderr,
                )
                sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_SECONDS)

    def _room(self) -> Any:
        if self.room is None:
            raise RuntimeError("attach the room before the connection serves it")
        return self.room
