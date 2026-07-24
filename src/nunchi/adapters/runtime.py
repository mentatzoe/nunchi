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
from ..attention import (
    AttentionEngine,
    AttentionPolicy,
    OpenAICompatibleAttentionModel,
    ParticipantProfile,
)
from ..authorization import (
    AuthorizationCoordinator,
    AuthorizationJournal,
    PinnedFilePolicySource,
)
from ..errors import InputError, ValidationError
from ..observation import ObservationLimits, ObservationProvider, ParticipantBinding
from ..participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
    Transport,
    TransportResult,
)
from ..participant_model import OpenAICompatibleParticipant
from ..pipeline import DeliveryOutcome, NunchiV2Pipeline
from ..receipts import ReceiptJournal
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


def _policy(raw: Any) -> AttentionPolicy:
    if not isinstance(raw, Mapping):
        raise ValidationError("adapter attention policy must be an object")
    try:
        return AttentionPolicy(**raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"adapter attention policy is invalid: {exc}") from exc


class JsonLineTransport:
    """Host-attested generic outbound seam used by ``nunchi-channel``."""

    def __init__(self, output: TextIO | None = None) -> None:
        self.output = output or sys.stdout
        self.calls = 0

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
        required = {
            "schema_version",
            "binding",
            "profile",
            "attention",
            "participant_model",
            "limits",
            "state_directory",
        }
        optional = {"authorization", "transport"}
        if set(config) - (required | optional) or required - set(config):
            raise ValidationError("adapter config has a missing or unexpected field")
        if config["schema_version"] != 2:
            raise ValidationError("adapter config schema_version must be 2")
        binding_raw = config["binding"]
        if not isinstance(binding_raw, Mapping):
            raise ValidationError("adapter binding must be an object")
        allowed_binding = {
            "participant_id",
            "actor_id",
            "platform",
            "room_id",
            "continuity_scope_id",
            "names",
            "role",
            "description",
            "room_name",
            "room_kind",
            "provenance",
        }
        if set(binding_raw) - allowed_binding:
            raise ValidationError("adapter binding has unexpected fields")
        try:
            self.binding = ParticipantBinding(
                **{
                    **binding_raw,
                    "names": tuple(binding_raw.get("names", ())),
                }
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"adapter binding is invalid: {exc}") from exc
        if self.binding.platform != surface and not (
            surface == "channel" and self.binding.platform
        ):
            raise ValidationError("adapter surface and trusted platform binding differ")

        profile_raw = config["profile"]
        if not isinstance(profile_raw, Mapping) or set(profile_raw) != {"path", "sha256"}:
            raise ValidationError("adapter profile must contain exactly path and sha256")
        profile = ParticipantProfile.load(
            profile_raw["path"],
            expected_sha256=profile_raw["sha256"],
        )
        if (
            profile.participant_id != self.binding.participant_id
            or profile.actor_id != self.binding.actor_id
        ):
            raise ValidationError("adapter profile does not match exact transport self binding")

        attention_raw = config["attention"]
        if not isinstance(attention_raw, Mapping) or set(attention_raw) != {"policy", "model"}:
            raise ValidationError("adapter attention config must contain policy and model")
        policy = _policy(attention_raw["policy"])
        model = (
            OpenAICompatibleAttentionModel.from_trusted_config(attention_raw["model"])
            if policy.preattention_enabled
            else None
        )
        participant_raw = config["participant_model"]
        if not isinstance(participant_raw, Mapping):
            raise ValidationError("adapter participant_model must be an object")
        participant = OpenAICompatibleParticipant.from_trusted_config(
            profile=profile,
            config=participant_raw,
            environment=os.environ,
        )
        try:
            limits = ObservationLimits(**config["limits"])
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"adapter limits are invalid: {exc}") from exc
        state_directory = Path(config["state_directory"])
        state_directory.mkdir(parents=True, exist_ok=True)
        stem = hashlib.sha256(
            f"{surface}\0{self.binding.participant_id}\0{self.binding.continuity_scope_id}".encode()
        ).hexdigest()[:24]
        receipts = ReceiptJournal(state_directory / f"{stem}.receipts.jsonl")
        observation = ObservationProvider(
            self.binding,
            limits=limits,
            receipts=receipts,
            persistence_path=state_directory / f"{stem}.observations.jsonl",
            event_visibility=CAPABILITIES[surface]["event_visibility"],
        )
        scheduler = ConversationOpportunityScheduler(
            f"{self.binding.participant_id}:{self.binding.continuity_scope_id}"
        )
        privileged = None
        authorization = config.get("authorization")
        if authorization is not None:
            if not isinstance(authorization, Mapping) or set(authorization) != {
                "policy_path",
                "policy_sha256",
            }:
                raise ValidationError("adapter authorization config has an invalid shape")
            policy_source = PinnedFilePolicySource(
                authorization["policy_path"],
                expected_sha256=authorization["policy_sha256"],
            )
            privileged = AuthorizationCoordinator(
                observation=observation,
                policy_source=policy_source,
                journal=AuthorizationJournal(
                    state_directory / f"{stem}.authorization.jsonl"
                ),
                executors=privileged_executors or {},
            )
        host = ParticipantTurnHost(
            observation=observation,
            participant=participant,
            transport=transport,
            scheduler=scheduler,
            receipts=receipts,
            privileged=privileged,
        )
        attention = AttentionEngine(
            profile=profile,
            model=model,
            policy=policy,
            receipts=receipts,
        )
        self.surface = surface
        self.transport = transport
        self.pipeline = NunchiV2Pipeline(
            observation=observation,
            attention=attention,
            host=host,
            scheduler=scheduler,
        )

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
            "interfaces": {
                "I-010A": 1,
                "I-010B": 2,
                "I-010C": 1,
                "I-010D": 1,
                "I-010E": 2,
                "I-010F": 1,
                "I-020A": 1,
                "I-030A": 1,
                "I-040A": 1,
            },
            "v1_fallback": False,
        }

    def restart(self) -> None:
        self.pipeline.restart()
