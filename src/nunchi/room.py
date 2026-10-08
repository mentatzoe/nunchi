"""One participant in one room: the library's side, assembled once (#94 step 9d).

Around the agent's turn, every integration needs the same parts:

- the room log (observation);
- attention;
- the scheduler;
- the turn host with its commit point, memory and receipts;
- the delivery lane, so taking in a message never waits on a turn.

`Room` builds them from the shared config sections, the integration's
participant and its transport. Every harness then gets the same behavior, and
no integration wires the parts by hand (`docs/harness-guide.md`).

`room_guard` builds the one secret guard for the room from the same config,
and the host checks every action against it before anything leaves.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any

from .attention import (
    DEFAULT_API_KEY_ENV as ATTENTION_KEY_ENV,
    AttentionEngine,
    AttentionPolicy,
    ParticipantProfile,
    attention_model_from_config,
)
from .authorization import AuthorizationCoordinator, AuthorizationJournal, PinnedFilePolicySource
from .errors import ValidationError
from .observation import ObservationLimits, ObservationProvider, ParticipantBinding
from .participant import ConversationOpportunityScheduler, ParticipantTurnHost, Transport
from .participant_model import DEFAULT_API_KEY_ENV as PARTICIPANT_KEY_ENV
from .pipeline import AsyncDeliveryLane, DeliveryOutcome, NunchiV2Pipeline
from .receipts import ReceiptJournal
from .turn import SecretGuard

SHARED_SECTIONS = frozenset(
    {"schema_version", "binding", "profile", "attention", "limits", "state_directory"}
)
# "ack" configured Nunchi's own nod, removed in #94 step 7; an older config
# that still has it loads, and the setting is ignored.
SHARED_OPTIONAL = frozenset({"authorization", "ack"})
DEFAULT_PARTICIPANT_TIMEOUT_SECONDS = 300.0
# A config key with this ending names environment variables that hold secrets.
SECRET_ENV_SUFFIX = "_env"
# The variables the attention and participant models read their keys from
# when the config names none; always withheld.
DEFAULT_SECRET_ENV = (ATTENTION_KEY_ENV, PARTICIPANT_KEY_ENV)


@dataclass(frozen=True)
class RoomSettings:
    """The shared sections of an integration's config, checked once."""

    binding: ParticipantBinding
    profile: ParticipantProfile
    attention: AttentionPolicy
    attention_model: Mapping[str, Any] | None
    limits: ObservationLimits
    state_directory: Path
    authorization: Mapping[str, Any] | None = None
    # The integration's own sections, as written; the integration checks them.
    sections: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        label: str,
        sections: Iterable[str] = (),
        optional: Iterable[str] = (),
        authorization_keys: Iterable[str] = (),
    ) -> "RoomSettings":
        """Check the shared sections; ``sections`` are the integration's own.

        ``label`` names the integration in errors. ``authorization_keys`` are
        extra keys the integration allows in its authorization section.
        """

        own = set(sections)
        required = SHARED_SECTIONS | own
        allowed = required | SHARED_OPTIONAL | set(optional)
        if not isinstance(config, Mapping):
            raise ValidationError(f"{label} config must be an object")
        supplied = set(config)
        if required - supplied or supplied - allowed:
            raise ValidationError(f"{label} config has a missing or unexpected field")
        if config["schema_version"] != 2:
            raise ValidationError(f"{label} config is not V2")

        binding_raw = config["binding"]
        if not isinstance(binding_raw, Mapping):
            raise ValidationError(f"{label} binding must be an object")
        try:
            binding = ParticipantBinding(
                **{**binding_raw, "names": tuple(binding_raw.get("names", ()))}
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{label} binding is invalid: {exc}") from exc

        profile_raw = config["profile"]
        if not isinstance(profile_raw, Mapping) or set(profile_raw) != {"path", "sha256"}:
            raise ValidationError(f"{label} profile must contain exactly path and sha256")
        profile = ParticipantProfile.load(
            profile_raw["path"], expected_sha256=profile_raw["sha256"]
        )
        if (
            profile.participant_id != binding.participant_id
            or profile.actor_id != binding.actor_id
        ):
            raise ValidationError(f"{label} profile and exact transport self differ")

        attention_raw = config["attention"]
        if not isinstance(attention_raw, Mapping) or set(attention_raw) != {"policy", "model"}:
            raise ValidationError(f"{label} attention config must contain policy and model")
        policy_raw = attention_raw["policy"]
        if not isinstance(policy_raw, Mapping):
            raise ValidationError(f"{label} attention policy must be an object")
        try:
            policy = AttentionPolicy(**policy_raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{label} attention policy is invalid: {exc}") from exc
        model = attention_raw["model"]
        if model is not None and not isinstance(model, Mapping):
            raise ValidationError(f"{label} attention model must be an object or null")

        limits_raw = config["limits"]
        if not isinstance(limits_raw, Mapping):
            raise ValidationError(f"{label} limits must be an object")
        try:
            limits = ObservationLimits(**limits_raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{label} limits are invalid: {exc}") from exc

        state = config["state_directory"]
        if not isinstance(state, str) or not state:
            raise ValidationError(f"{label} state_directory must be a path")

        authorization = config.get("authorization")
        if authorization is not None:
            keys = {"policy_path", "policy_sha256"}
            if (
                not isinstance(authorization, Mapping)
                or not keys <= set(authorization)
                or set(authorization) - keys - set(authorization_keys)
            ):
                raise ValidationError(f"{label} authorization config has an invalid shape")

        return cls(
            binding=binding,
            profile=profile,
            attention=policy,
            attention_model=model,
            limits=limits,
            state_directory=Path(state),
            authorization=authorization,
            sections={name: config[name] for name in supplied - SHARED_SECTIONS - SHARED_OPTIONAL},
        )


def _env_names(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.endswith(SECRET_ENV_SUFFIX):
                if isinstance(item, str) and item:
                    yield item
                elif isinstance(item, (list, tuple)):
                    yield from (name for name in item if isinstance(name, str) and name)
            else:
                yield from _env_names(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _env_names(item)


def withheld_env_names(settings: "RoomSettings") -> list[str]:
    """The environment variables the config names as secrets.

    A key ending in ``_env`` names one variable, or a list of them, that holds
    a secret: an attention route's ``api_key_env``, a transport's
    ``output_key_env``, an integration's ``withhold_env``. The attention model,
    the integration's own sections and the authorization section are read, at
    any depth. Keep these variables out of the agent's environment.
    """

    names = [
        *_env_names(settings.attention_model or {}),
        *_env_names(dict(settings.sections)),
        *_env_names(settings.authorization or {}),
    ]
    return list(dict.fromkeys(names))


def room_guard(
    settings: "RoomSettings",
    *,
    transport: Any = None,
    values: Iterable[str] = (),
    patterns: Iterable[re.Pattern[str]] = (),
    environ: Mapping[str, str] | None = None,
) -> SecretGuard:
    """The one secret guard for a participant's room.

    It withholds:

    - the value of every variable `withheld_env_names` finds in the config,
      and of the default key variables a model reads when the config names
      none (`DEFAULT_SECRET_ENV`);
    - what the transport says it holds, from its optional
      ``withheld_values()``;
    - ``values``, which the integration adds, such as defaults its config
      leaves unnamed.

    It refuses the credential shapes the transport names in its optional
    ``credential_patterns()``, and ``patterns``. Values shorter than 12
    characters are ignored. Give the participant's turns a guard that holds
    at least this one, so the agent is told about a refusal and can answer
    again.
    """

    environ = os.environ if environ is None else environ
    names = dict.fromkeys([*withheld_env_names(settings), *DEFAULT_SECRET_ENV])
    held = [environ[name] for name in names if environ.get(name)]
    declared = getattr(transport, "withheld_values", None)
    if callable(declared):
        held += [value for value in declared() if isinstance(value, str) and value]
    shapes = getattr(transport, "credential_patterns", None)
    return SecretGuard(
        [*held, *values],
        [*(shapes() if callable(shapes) else ()), *patterns],
    )


class Room:
    """Everything the library owns for one participant in one room.

    The integration supplies three things:

    - ``participant``: what the turn host invokes for each turn, usually a
      ``nunchi.turn.TurnParticipant`` with the integration's driver;
    - ``transport``: what posts the committed action, or
      ``nunchi.turn.HarnessDelivery`` when the harness posts it itself;
    - ``event_visibility``: which kinds of room event its harness shows
      (``history-and-live``, ``live-only`` or ``unavailable``).

    The attention model comes from the settings with ``attention_kinds``
    (the model routes the integration installs), unless the integration
    passes its own, such as its harness's model. State lives in the settings'
    directory, in files named ``{state_prefix}receipts.jsonl``,
    ``{state_prefix}observations.jsonl`` and
    ``{state_prefix}authorization.jsonl``.

    ``guard`` is the room's secret guard (``room.guard``); without one the
    room builds it with `room_guard` from the settings and the transport.
    The host refuses any action that carries what it withholds, whatever the
    participant's turn did.
    """

    def __init__(
        self,
        settings: RoomSettings,
        *,
        participant: Any,
        transport: Transport,
        event_visibility: Mapping[str, str],
        state_prefix: str,
        attention_model: Any = None,
        attention_kinds: Mapping[str, Callable[..., Any]] | None = None,
        privileged_executors: Mapping[str, Any] | None = None,
        participant_timeout_seconds: float = DEFAULT_PARTICIPANT_TIMEOUT_SECONDS,
        guard: SecretGuard | None = None,
    ) -> None:
        self.settings = settings
        self.guard = guard if guard is not None else room_guard(settings, transport=transport)
        binding = settings.binding
        state = settings.state_directory
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.receipts = ReceiptJournal(state / f"{state_prefix}receipts.jsonl")
        self.observation = ObservationProvider(
            binding,
            limits=settings.limits,
            receipts=self.receipts,
            persistence_path=state / f"{state_prefix}observations.jsonl",
            event_visibility=event_visibility,
        )
        self.scheduler = ConversationOpportunityScheduler(
            f"{binding.participant_id}:{binding.continuity_scope_id}"
        )
        self.privileged: AuthorizationCoordinator | None = None
        if settings.authorization is not None:
            self.privileged = AuthorizationCoordinator(
                observation=self.observation,
                policy_source=PinnedFilePolicySource(
                    settings.authorization["policy_path"],
                    expected_sha256=settings.authorization["policy_sha256"],
                ),
                journal=AuthorizationJournal(state / f"{state_prefix}authorization.jsonl"),
                executors=privileged_executors or {},
            )
        if attention_model is None and settings.attention.preattention_enabled:
            if settings.attention_model is None:
                raise ValidationError("attention is enabled but no attention model is configured")
            attention_model = attention_model_from_config(
                settings.attention_model, host_kinds=attention_kinds
            )
        self.participant = participant
        self.transport = transport
        self.host = ParticipantTurnHost(
            observation=self.observation,
            participant=participant,
            transport=transport,
            scheduler=self.scheduler,
            receipts=self.receipts,
            privileged=self.privileged,
            participant_timeout_seconds=participant_timeout_seconds,
            guard=self.guard,
        )
        self.attention = AttentionEngine(
            profile=settings.profile,
            model=attention_model if settings.attention.preattention_enabled else None,
            policy=settings.attention,
            receipts=self.receipts,
        )
        self.pipeline = NunchiV2Pipeline(
            observation=self.observation,
            attention=self.attention,
            host=self.host,
            scheduler=self.scheduler,
        )
        self.lane = AsyncDeliveryLane(self.pipeline)

    def deliver(
        self,
        *,
        delivery_id: str,
        event: Mapping[str, Any] | None,
        actors: Mapping[str, Any] | None,
        authorized_route: bool = True,
    ) -> DeliveryOutcome:
        """Take in one room event without waiting for any turn it starts."""

        return self.lane.submit(
            delivery_id=delivery_id,
            event=event,
            actors=actors,
            authorized_route=authorized_route,
        )

    def drain(self, timeout: float | None = None) -> bool:
        """Wait until no turn is running; False if ``timeout`` passed first."""

        return self.lane.drain(timeout)

    def cancel(self) -> None:
        """Cancel the running turn and anything waiting."""

        self.lane.cancel()

    def restart(self) -> None:
        """The room connection restarted: nothing pending carries over."""

        self.lane.restart()

    @property
    def errors(self) -> tuple[str, ...]:
        return self.lane.errors
