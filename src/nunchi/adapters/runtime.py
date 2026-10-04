"""Shared installed runtime for generic, Discord, Matrix, and Telegram adapters."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
from typing import Any, TextIO

from .. import __version__
from ..ack import AckJournal, AckPolicy, ReactionCapability
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
from ..pipeline import AsyncDeliveryLane, DeliveryOutcome, NunchiV2Pipeline
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


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class ChannelIngressAuthenticator:
    """Authenticate one generic native delivery before normalization."""

    def __init__(self, raw: Any) -> None:
        if not isinstance(raw, Mapping) or set(raw) != {"source_id", "hmac_key_env"}:
            raise ValidationError("generic channel ingress_auth has an invalid closed shape")
        source_id = raw["source_id"]
        key_env = raw["hmac_key_env"]
        if not isinstance(source_id, str) or not source_id:
            raise ValidationError("generic channel ingress source_id must be non-empty")
        if not isinstance(key_env, str) or not key_env:
            raise ValidationError("generic channel ingress hmac_key_env must be non-empty")
        key = os.environ.get(key_env)
        if key is None or len(key.encode("utf-8")) < 32:
            raise ValidationError(
                f"generic channel ingress key is absent or shorter than 32 bytes in {key_env}"
            )
        self.source_id = source_id
        self._key = key.encode("utf-8")

    def unwrap(self, envelope: Any) -> Mapping[str, Any]:
        if not isinstance(envelope, Mapping) or set(envelope) != {
            "payload",
            "authorization",
        }:
            raise ValidationError(
                "generic channel ingress requires one authenticated payload envelope"
            )
        payload = envelope["payload"]
        authorization = envelope["authorization"]
        if not isinstance(payload, Mapping):
            raise ValidationError("generic channel ingress payload must be an object")
        if not isinstance(authorization, Mapping) or set(authorization) != {
            "schema_version",
            "source_id",
            "payload_sha256",
            "mac",
        }:
            raise ValidationError("generic channel ingress authorization is malformed")
        if authorization["schema_version"] != 1:
            raise ValidationError("generic channel ingress authorization version is unsupported")
        if authorization["source_id"] != self.source_id:
            raise ValidationError("generic channel ingress source differs from trusted binding")
        payload_sha256 = hashlib.sha256(_canonical_json(payload)).hexdigest()
        if authorization["payload_sha256"] != payload_sha256:
            raise ValidationError("generic channel ingress payload digest differs")
        material = (
            b"nunchi.channel.ingress.v1\0"
            + self.source_id.encode("utf-8")
            + b"\0"
            + payload_sha256.encode("ascii")
        )
        expected = hmac.new(self._key, material, hashlib.sha256).hexdigest()
        supplied = authorization["mac"]
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
            raise ValidationError("generic channel ingress authentication failed")
        return payload


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
        required = {
            "schema_version",
            "binding",
            "profile",
            "attention",
            "limits",
            "state_directory",
        }
        optional = {
            "authorization",
            "transport",
            "participant_timeout_seconds",
            "ack",
            "ingress_auth",
        }
        participant_backends = set(config) & {"participant_model", "codex"}
        if (
            set(config) - (required | optional | {"participant_model", "codex"})
            or required - set(config)
            or len(participant_backends) != 1
        ):
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
        ingress_auth_raw = config.get("ingress_auth")
        if surface == "channel":
            if ingress_auth_raw is None:
                raise ValidationError(
                    "generic channel requires ingress_auth; use a native adapter when "
                    "the upstream source cannot sign canonical deliveries"
                )
            self.ingress_auth = ChannelIngressAuthenticator(ingress_auth_raw)
        else:
            if ingress_auth_raw is not None:
                raise ValidationError("native adapters do not accept generic ingress_auth")
            self.ingress_auth = None

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
        try:
            limits = ObservationLimits(**config["limits"])
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"adapter limits are invalid: {exc}") from exc
        state_directory = Path(config["state_directory"])
        state_directory.mkdir(parents=True, exist_ok=True)
        stem = hashlib.sha256(
            f"{surface}\0{self.binding.participant_id}\0{self.binding.continuity_scope_id}".encode()
        ).hexdigest()[:24]
        if "participant_model" in participant_backends:
            participant_raw = config["participant_model"]
            if not isinstance(participant_raw, Mapping):
                raise ValidationError("adapter participant_model must be an object")
            participant = OpenAICompatibleParticipant.from_trusted_config(
                profile=profile,
                config=participant_raw,
                environment=os.environ,
            )
            receipts = ReceiptJournal(state_directory / f"{stem}.receipts.jsonl")
            self.participant_backend = "openai-compatible"
        else:
            codex_raw = config["codex"]
            if not isinstance(codex_raw, Mapping):
                raise ValidationError("adapter codex config must be an object")
            # This local import avoids making the shared adapter layer depend on
            # a platform participant at module-import time.
            from ..integrations.codex_v2 import (  # noqa: PLC0415
                CodexParticipant,
                CodexTaskReceiptJournal,
            )

            participant = CodexParticipant(
                profile=profile,
                config=codex_raw,
                binding=self.binding,
                state_directory=state_directory / f"{stem}.codex",
            )
            receipts = CodexTaskReceiptJournal(
                state_directory / f"{stem}.receipts.jsonl",
                participant=participant,
            )
            self.participant_backend = "codex"
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
        try:
            ack_policy = AckPolicy(**dict(config.get("ack", {})))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"adapter ACK policy is invalid: {exc}") from exc
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
            ack_policy=ack_policy,
            ack_journal=AckJournal(state_directory / f"{stem}.acks.jsonl"),
            participant_timeout_seconds=config.get(
                "participant_timeout_seconds",
                300.0,
            ),
        )
        attention = AttentionEngine(
            profile=profile,
            model=model,
            policy=policy,
            receipts=receipts,
            ack_policy=ack_policy,
            reaction_capability_provider=host.reaction_capability,
        )
        self.surface = surface
        self.transport = transport
        self.participant = participant
        self.pipeline = NunchiV2Pipeline(
            observation=observation,
            attention=attention,
            host=host,
            scheduler=scheduler,
        )
        self.lane = AsyncDeliveryLane(self.pipeline)

    def process(
        self,
        payload: Mapping[str, Any],
        *,
        live: bool = True,
    ) -> DeliveryOutcome:
        delivery = self._normalize(payload)
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
        delivery = self._normalize(payload)
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

    def _normalize(self, payload: Mapping[str, Any]):
        if self.ingress_auth is not None:
            payload = self.ingress_auth.unwrap(payload)
        return NORMALIZERS[self.surface](payload, self.binding)

    def probe(self) -> dict[str, Any]:
        result = {
            "product": "nunchi",
            "product_version": __version__,
            "generation": 2,
            "surface": self.surface,
            "configured": True,
            "participant_id": self.binding.participant_id,
            "actor_id": self.binding.actor_id,
            "room_id": self.binding.room_id,
            "continuity_scope_id": self.binding.continuity_scope_id,
            "participant_backend": self.participant_backend,
            "ingress_authentication": (
                {
                    "mode": "hmac-sha256",
                    "source_id": self.ingress_auth.source_id,
                }
                if self.ingress_auth is not None
                else {"mode": "native-adapter"}
            ),
            "capabilities": deepcopy(CAPABILITIES[self.surface]),
            "interfaces": {
                "I-010A": 1,
                "I-010B": 3,
                "I-010C": 2,
                "I-010D": 1,
                "I-010E": 3,
                "I-010F": 1,
                "I-020A": 1,
                "I-030A": 2,
                "I-040A": 2,
            },
            "participant_turn_protocol_version": 1,
            "operator_schema_version": 1,
            "v1_fallback": False,
        }
        if self.participant_backend == "codex":
            result["codex"] = {
                "session_mode": self.participant.session_mode,
                "persistent_session": self.participant.session_mode == "persistent",
                "task_state": self.participant.session_status(),
                "runtime_identity": self.participant.runtime_status(),
                "capability_mode": self.participant.capability_mode,
            }
        return result

    def restart(self) -> None:
        self.lane.restart()
