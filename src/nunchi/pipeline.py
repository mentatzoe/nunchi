"""One ordinary V2 path from native observation through action or silence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import threading
from typing import Any

from .attention import AttentionEngine
from .observation import ObservationProvider, ObservationResult, SnapshotUnavailable
from .participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
    TransportResult,
)


@dataclass(frozen=True)
class OpportunityOutcome:
    anchor_event_id: str
    request_id: str | None
    decision_status: str | None
    effective_disposition: str | None
    transport: TransportResult | None
    operational_error: str | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    observation: ObservationResult
    opportunities: tuple[OpportunityOutcome, ...]
    coalesced: bool


class NunchiV2Pipeline:
    """Synchronous owner of one participant/room scheduling lane.

    Calls may arrive concurrently.  The first caller runs the active
    opportunity; later callers only replace the pending anchor after retaining
    their events.  The active caller then processes at most one fresh pending
    opportunity at a time.
    """

    def __init__(
        self,
        *,
        observation: ObservationProvider,
        attention: AttentionEngine,
        host: ParticipantTurnHost,
        scheduler: ConversationOpportunityScheduler,
    ) -> None:
        if host.observation is not observation:
            raise ValueError("host and pipeline must share one observation provider")
        if host.scheduler is not scheduler:
            raise ValueError("host and pipeline must share one scheduler")
        if attention.receipts is not observation.receipts or host.receipts is not observation.receipts:
            raise ValueError("all stages must share one request-correlated receipt journal")
        self.observation = observation
        self.attention = attention
        self.host = host
        self.scheduler = scheduler
        self._lifecycle_lock = threading.RLock()

    def handle_delivery(
        self,
        *,
        delivery_id: str,
        event: Mapping[str, Any] | None,
        actors: Mapping[str, Any] | None,
        authorized_route: bool = True,
    ) -> DeliveryOutcome:
        observed = self.observation.observe(
            delivery_id=delivery_id,
            event=event,
            actors=actors,
            authorized_route=authorized_route,
        )
        if not observed.wake_eligible or observed.audit.event_id is None:
            return DeliveryOutcome(observed, (), False)
        token = self.scheduler.offer(observed.audit.event_id)
        if token is None:
            return DeliveryOutcome(observed, (), True)

        opportunities: list[OpportunityOutcome] = []
        while token is not None:
            if not self.scheduler.is_current(token):
                break
            try:
                request = self.observation.build_snapshot(token.anchor_event_id)
            except SnapshotUnavailable as exc:
                opportunities.append(
                    OpportunityOutcome(
                        anchor_event_id=token.anchor_event_id,
                        request_id=None,
                        decision_status=None,
                        effective_disposition=None,
                        transport=None,
                        operational_error=str(exc),
                    )
                )
                token = self.scheduler.complete(token)
                continue
            if not self.scheduler.is_current(token):
                break
            decision = self.attention.judge(
                request,
                cancel=token.cancel_event,
            )
            transport = self.host.run(
                request=request,
                decision=decision,
                token=token,
                error_wake=self.attention.policy.error_action == "WAKE",
            )
            effective = (
                decision.get("effective_disposition")
                if decision["status"] == "ok"
                else "PREATTENTION_BYPASS"
                if decision["status"] == "bypass"
                else "ERROR_FALLBACK"
                if self.attention.policy.error_action == "WAKE"
                else None
            )
            opportunities.append(
                OpportunityOutcome(
                    anchor_event_id=token.anchor_event_id,
                    request_id=request["request_id"],
                    decision_status=decision["status"],
                    effective_disposition=effective,
                    transport=transport,
                    operational_error=(
                        decision["error"]["detail"]
                        if decision["status"] == "error"
                        else None
                    ),
                )
            )
            token = self.scheduler.complete(token)
        return DeliveryOutcome(observed, tuple(opportunities), False)

    def cancel(self) -> None:
        self.scheduler.cancel()

    def restart(self) -> None:
        """Invalidate active/pending work and discard ephemeral authority."""
        with self._lifecycle_lock:
            self.scheduler.restart()
            self.observation.restart()
            privileged = self.host.privileged
            if privileged is not None and hasattr(privileged, "restart"):
                privileged.restart()
