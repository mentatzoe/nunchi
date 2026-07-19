"""Simulated restart/backfill and capability reference variants (T023).

These reference variants live outside product runtime code (plan Sec.
"Structure Decision": "no simulated transport lifecycle is implemented in
the shared product module"). Each wraps a fresh
:class:`nunchi.observation.ObservationProvider` and adds only a
``simulate_restart()`` hook plus an honest declared continuity/visibility
capability — never a real persistence layer. FR-011: each downstream
surface must pass the restart/backfill scene itself before claiming
social-suppression eligibility; a reference pass proves the reusable
mechanics only.
"""

from __future__ import annotations

from typing import Any

from nunchi.observation import ObservationProvider


class ReferenceRoomState:
    """The backing log of native event inputs a reference variant may
    "persist" across a simulated restart. Test/eval-only — never product
    state."""

    def __init__(self) -> None:
        self.persisted: list[dict[str, Any]] = []


class ReferenceProvider:
    """Base reference variant: wraps one :class:`ObservationProvider` and
    records every ingested native input into ``room_state`` so a subclass
    can decide what a simulated restart recovers."""

    continuity: str = "unknown"
    backfill_fraction: float = 1.0
    """Fraction of persisted history a simulated restart recovers (1.0 =
    full backfill, 0.0 = none). Values between the two declare an honest
    known gap."""

    def __init__(self, room_state: ReferenceRoomState, **provider_kwargs: Any) -> None:
        self.room_state = room_state
        self._provider_kwargs = dict(provider_kwargs)
        self._provider_kwargs.setdefault("continuity", self.continuity)
        self.provider = ObservationProvider(**self._provider_kwargs)
        self.restart_count = 0
        self.known_gap_event_ids: set[str] = set()

    def ingest(self, native_event_input: dict[str, Any]) -> str:
        self.room_state.persisted.append(native_event_input)
        return self.provider.ingest(native_event_input)

    def snapshot(self, **kwargs: Any) -> dict:
        return self.provider.snapshot(**kwargs)

    def build_observation_receipt(self, request: dict) -> dict:
        return self.provider.build_observation_receipt(request)

    def simulate_restart(self) -> None:
        """Rebuild the provider and replay whatever this variant recovers."""
        self.restart_count += 1
        self.provider = ObservationProvider(**self._provider_kwargs)
        recovered_count = round(len(self.room_state.persisted) * self.backfill_fraction)
        recovered = self.room_state.persisted[:recovered_count]
        dropped = self.room_state.persisted[recovered_count:]
        self.known_gap_event_ids = {
            item["event"]["id"] for item in dropped if item.get("disposition") == "candidate-event"
        }
        for native_event_input in recovered:
            self.provider.ingest(native_event_input)


class RestartSafeReferenceProvider(ReferenceProvider):
    """Full backfill: every persisted event is recovered after restart."""

    continuity = "restart-safe"
    backfill_fraction = 1.0


class SessionOnlyReferenceProvider(ReferenceProvider):
    """No persistence: a simulated restart recovers nothing (an honest
    session gap, never upgraded to restart-safe by inference)."""

    continuity = "session-only"
    backfill_fraction = 0.0


class UnknownContinuityReferenceProvider(ReferenceProvider):
    """Continuity/restart-safety itself is unknown (host cannot attest
    either way); recovery behavior mirrors session-only but the coverage
    fact stays explicitly ``unknown``, never guessed."""

    continuity = "unknown"
    backfill_fraction = 0.0


class KnownGapReferenceProvider(ReferenceProvider):
    """Partial backfill: some prefix of history is recovered, and the
    dropped tail is reported as an honest known gap, not silently absent."""

    continuity = "restart-safe"
    backfill_fraction = 0.5


VARIANTS: dict[str, type[ReferenceProvider]] = {
    "restart-safe": RestartSafeReferenceProvider,
    "session-only": SessionOnlyReferenceProvider,
    "unknown": UnknownContinuityReferenceProvider,
    "known-gap": KnownGapReferenceProvider,
}


def make_reference_provider(variant: str, **provider_kwargs: Any) -> ReferenceProvider:
    if variant not in VARIANTS:
        raise ValueError(f"unknown reference variant {variant!r}; expected one of {sorted(VARIANTS)}")
    return VARIANTS[variant](ReferenceRoomState(), **provider_kwargs)
