"""Shared installed runtime for generic, Discord, Matrix, and Telegram adapters."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, TextIO

from .. import __version__
from ..reactions import ReactionCapability
from ..errors import InputError, ValidationError
from ..participant import Transport, TransportResult
from ..participant_model import OpenAICompatibleParticipant
from ..pipeline import DeliveryOutcome
from ..room import DEFAULT_PARTICIPANT_TIMEOUT_SECONDS, Room, RoomSettings
from ..v2_contracts import INTERFACE_VERSIONS
from .model_apis import ATTENTION_KINDS
from .v2 import NORMALIZERS


CAPABILITIES = {
    "channel": {
        "ingress": ["message", "reaction", "membership"],
        "outbound": ["message", "reply", "reaction"],
        "history": "retained-bounded",
        "restart_continuity": "configured-state",
        "event_visibility": {
            "message": "history-and-live",
            "reaction": "history-and-live",
            "membership": "history-and-live",
        },
    },
    "discord": {
        "ingress": ["message", "reaction", "membership"],
        "outbound": ["message", "reply", "reaction"],
        "history": "retained-bounded",
        "restart_continuity": "retained-state-plus-live-gateway",
        "event_visibility": {
            "message": "history-and-live",
            "reaction": "history-and-live",
            "membership": "history-and-live",
        },
    },
    "matrix": {
        "ingress": ["message", "reaction", "membership"],
        "outbound": ["message", "reply", "reaction-add"],
        "history": "retained-bounded",
        "restart_continuity": "retained-state-plus-sync-token",
        "event_visibility": {
            "message": "history-and-live",
            "reaction": "history-and-live",
            "membership": "history-and-live",
            "room-wide-mention-relation": "unavailable",
        },
    },
    "telegram": {
        "ingress": ["message", "membership"],
        "outbound": ["message", "reply"],
        "history": "live-only",
        "restart_continuity": "update-offset-dependent",
        "event_visibility": {
            "message": "live-only",
            "reaction": "unavailable",
            "membership": "live-only",
            "room-wide-mention-relation": "unavailable",
        },
    },
}


def load_pinned_config(path: str | Path, expected_sha256: str) -> dict[str, Any]:
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValidationError("adapter config sha256 must be 64 lowercase hex characters")
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise InputError(f"could not read adapter config {source}: {exc}") from exc
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValidationError("adapter config bytes do not match trusted sha256 pin")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"adapter config is invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValidationError("adapter config must be an object")
    return data


class JsonLineTransport:
    """Host-attested generic outbound seam used by ``nunchi-channel``."""

    def __init__(self, output: TextIO | None = None) -> None:
        self.output = output or sys.stdout
        self.calls = 0

    def ordinary_action_capabilities(self) -> tuple[str, ...]:
        return ("message", "reply", "reaction")

    def reaction_capability(self) -> ReactionCapability:
        return ReactionCapability(
            supported=True,
            authenticated=True,
            operations=("add", "remove"),
            reactions=("*",),
            permissions_revision="generic-jsonl-v1",
        )

    def dispatch(self, *, action, wake) -> TransportResult:
        self.calls += 1
        envelope = {
            "schema_version": 2,
            "participant_id": wake["self"]["participant_id"],
            "platform": wake["room"]["platform"],
            "room_id": wake["room"]["id"],
            "action": deepcopy(dict(action)),
        }
        try:
            self.output.write(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n"
            )
            self.output.flush()
        except OSError as exc:
            return TransportResult("unknown", f"generic output acknowledgement lost: {exc}")
        return TransportResult("sent", "generic-jsonl")


class ReferenceAdapterRuntime:
    def __init__(
        self,
        *,
        surface: str,
        config: Mapping[str, Any],
        transport: Transport,
        privileged_executors: Mapping[str, Any] | None = None,
    ) -> None:
        if surface not in NORMALIZERS:
            raise ValidationError(f"unsupported V2 adapter surface {surface!r}")
        settings = RoomSettings.from_config(
            config,
            label="adapter",
            sections=("participant_model",),
            optional=("transport", "participant_timeout_seconds"),
        )
        self.binding = settings.binding
        if self.binding.platform != surface and not (
            surface == "channel" and self.binding.platform
        ):
            raise ValidationError("adapter surface and trusted platform binding differ")
        participant_raw = settings.sections["participant_model"]
        if not isinstance(participant_raw, Mapping):
            raise ValidationError("adapter participant_model must be an object")
        participant = OpenAICompatibleParticipant.from_trusted_config(
            profile=settings.profile,
            config=participant_raw,
            environment=os.environ,
        )
        stem = hashlib.sha256(
            f"{surface}\0{self.binding.participant_id}\0{self.binding.continuity_scope_id}".encode()
        ).hexdigest()[:24]
        self.room = Room(
            settings,
            participant=participant,
            transport=transport,
            event_visibility=CAPABILITIES[surface]["event_visibility"],
            state_prefix=f"{stem}.",
            attention_kinds=ATTENTION_KINDS,
            privileged_executors=privileged_executors,
            participant_timeout_seconds=settings.sections.get(
                "participant_timeout_seconds", DEFAULT_PARTICIPANT_TIMEOUT_SECONDS
            ),
        )
        self.surface = surface
        self.transport = transport
        self.pipeline = self.room.pipeline
        self.lane = self.room.lane

    def process(
        self,
        payload: Mapping[str, Any],
        *,
        live: bool = True,
    ) -> DeliveryOutcome:
        delivery = NORMALIZERS[self.surface](payload, self.binding)
        if not live:
            observed = self.pipeline.observation.observe(
                delivery_id=delivery.delivery_id,
                event=delivery.event,
                actors=delivery.actors,
                authorized_route=delivery.room_id == self.binding.room_id,
            )
            return DeliveryOutcome(observed, (), False)
        return self.pipeline.handle_delivery(
            delivery_id=delivery.delivery_id,
            event=delivery.event,
            actors=delivery.actors,
            authorized_route=delivery.room_id == self.binding.room_id,
        )

    def submit(
        self,
        payload: Mapping[str, Any],
        *,
        live: bool = True,
    ) -> DeliveryOutcome:
        """Retain native ingress promptly and schedule work off the callback."""
        delivery = NORMALIZERS[self.surface](payload, self.binding)
        if not live:
            observed = self.pipeline.observation.observe(
                delivery_id=delivery.delivery_id,
                event=delivery.event,
                actors=delivery.actors,
                authorized_route=delivery.room_id == self.binding.room_id,
            )
            return DeliveryOutcome(observed, (), False)
        return self.lane.submit(
            delivery_id=delivery.delivery_id,
            event=delivery.event,
            actors=delivery.actors,
            authorized_route=delivery.room_id == self.binding.room_id,
        )

    def drain(self, timeout: float | None = None) -> bool:
        return self.lane.drain(timeout)

    def probe(self) -> dict[str, Any]:
        return {
            "product": "nunchi",
            "product_version": __version__,
            "generation": 2,
            "surface": self.surface,
            "configured": True,
            "participant_id": self.binding.participant_id,
            "actor_id": self.binding.actor_id,
            "room_id": self.binding.room_id,
            "continuity_scope_id": self.binding.continuity_scope_id,
            "capabilities": deepcopy(CAPABILITIES[self.surface]),
            "interfaces": dict(INTERFACE_VERSIONS),
            "participant_turn_protocol_version": 1,
            "operator_schema_version": 1,
            "v1_fallback": False,
        }

    def restart(self) -> None:
        self.lane.restart()
