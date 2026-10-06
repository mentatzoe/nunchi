"""One ordinary V2 path from native observation through action or silence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import threading
import time
from typing import Any

from .attention import AttentionEngine
from .attention_questions import top_move
from .observation import (
    ObservationProvider,
    ObservationResult,
    SnapshotUnavailable,
)
from .participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
    TransportResult,
    build_participant_wake,
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
class OpportunityPreparation:
    """Shared attention-to-participant boundary for one current opportunity."""

    anchor_event_id: str
    request: Mapping[str, Any] | None
    decision: Mapping[str, Any] | None
    effective_disposition: str | None
    wake: Mapping[str, Any] | None
    acknowledge: bool = False
    operational_error: str | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    observation: ObservationResult
    opportunities: tuple[OpportunityOutcome, ...]
    coalesced: bool


def prepare_opportunity(
    *,
    observation: ObservationProvider,
    attention: AttentionEngine,
    scheduler: ConversationOpportunityScheduler,
    token: Any,
    deadline: float,
    occasion: str | None = None,
) -> OpportunityPreparation | None:
    """Build one valid current participant opportunity or an explicit error.

    Snapshot assembly gets one bounded retry from the current observation
    seam. A recovered snapshot follows the ordinary operational-error policy
    and never calls the attention model.
    """

    if not scheduler.is_current(token):
        return None
    reconstructed = False
    try:
        request = observation.build_snapshot(token.anchor_event_id, occasion=occasion)
    except SnapshotUnavailable as first_error:
        reconstructed = True
        try:
            request = observation.build_snapshot(token.anchor_event_id, occasion=occasion)
        except SnapshotUnavailable as final_error:
            detail = (
                "attention snapshot unavailable after one reconstruction "
                f"attempt: {final_error or first_error}"
            )
            return OpportunityPreparation(
                anchor_event_id=token.anchor_event_id,
                request=None,
                decision=None,
                effective_disposition=None,
                wake=None,
                acknowledge=False,
                operational_error=detail,
            )
    if not scheduler.is_current(token):
        return None
    if reconstructed:
        decision = attention.operational_error(
            request,
            code="snapshot-reconstructed",
            detail="attention snapshot required one bounded reconstruction",
        )
    else:
        decision = attention.judge(
            request,
            cancel=token.cancel_event,
            deadline=deadline,
        )
    if not scheduler.is_current(token):
        return None
    if decision["status"] == "ok":
        effective = decision["effective_disposition"]
        admit = effective != "SUPPRESS"
        acknowledge = effective == "ACK"
    elif decision["status"] == "bypass":
        effective = "PREATTENTION_BYPASS"
        admit = True
        acknowledge = False
    else:
        admit = (
            attention.policy.error_action == "WAKE"
            and decision["error"]["code"] != "cancelled"
        )
        effective = "ERROR_FALLBACK" if admit else None
        acknowledge = False
    if not admit:
        return OpportunityPreparation(
            anchor_event_id=token.anchor_event_id,
            request=request,
            decision=decision,
            effective_disposition=effective,
            wake=None,
            acknowledge=False,
            operational_error=(
                decision["error"]["detail"]
                if decision["status"] == "error"
                else None
            ),
        )
    try:
        wake = build_participant_wake(
            observation,
            request,
            decision,
        )
    except Exception as exc:
        return OpportunityPreparation(
            anchor_event_id=token.anchor_event_id,
            request=request,
            decision=decision,
            effective_disposition=effective,
            wake=None,
            acknowledge=False,
            operational_error=f"participant wake unavailable: {exc}",
        )
    return OpportunityPreparation(
        anchor_event_id=token.anchor_event_id,
        request=request,
        decision=decision,
        effective_disposition=effective,
        wake=wake,
        acknowledge=acknowledge,
        operational_error=(
            decision["error"]["detail"]
            if decision["status"] == "error"
            else None
        ),
    )


# How long the room must stay quiet before Nunchi looks again at a moment
# judged as one to wait on (#94 step 6); 0 never looks again.
DEFAULT_LOOK_AGAIN_SECONDS = 300


class NunchiV2Pipeline:
    """Synchronous owner of one participant/room scheduling lane.

    Calls may arrive concurrently.  The first caller runs the active
    opportunity; later callers only replace the pending anchor after retaining
    their events.  The active caller then processes at most one fresh pending
    opportunity at a time.

    Looking again (``docs/behavior.md``): when a judgment's most likely move
    is to wait, for the addressee or for the speaker to finish, the pipeline
    arms one look again. A new message disarms it. If the room stays quiet
    for ``look_again_seconds``, ``look_again`` judges the same message again
    as a ``pause`` and the participant may get a turn with a fresh reading.
    It looks again once per quiet stretch.
    """

    def __init__(
        self,
        *,
        observation: ObservationProvider,
        attention: AttentionEngine,
        host: ParticipantTurnHost,
        scheduler: ConversationOpportunityScheduler,
        look_again_seconds: float = DEFAULT_LOOK_AGAIN_SECONDS,
    ) -> None:
        if host.observation is not observation:
            raise ValueError("host and pipeline must share one observation provider")
        if host.scheduler is not scheduler:
            raise ValueError("host and pipeline must share one scheduler")
        if attention.receipts is not observation.receipts or host.receipts is not observation.receipts:
            raise ValueError("all stages must share one request-correlated receipt journal")
        if (
            isinstance(look_again_seconds, bool)
            or not isinstance(look_again_seconds, (int, float))
            or look_again_seconds < 0
        ):
            raise ValueError("look_again_seconds must be a non-negative number")
        self.observation = observation
        self.attention = attention
        self.host = host
        self.scheduler = scheduler
        self.look_again_seconds = float(look_again_seconds)
        self._lifecycle_lock = threading.RLock()
        # (anchor event, monotonic time it is due) of the one armed look again.
        self._look_again: tuple[str, float] | None = None
        # The newest eligible event delivered: only it can be looked at again.
        self._newest_eligible: str | None = None

    def handle_delivery(
        self,
        *,
        delivery_id: str,
        event: Mapping[str, Any] | None,
        actors: Mapping[str, Any] | None,
        authorized_route: bool = True,
    ) -> DeliveryOutcome:
        observed, token = self.observe_and_offer(
            delivery_id=delivery_id,
            event=event,
            actors=actors,
            authorized_route=authorized_route,
        )
        if token is None:
            return DeliveryOutcome(
                observed,
                (),
                observed.wake_eligible and observed.audit.event_id is not None,
            )
        return DeliveryOutcome(
            observed,
            self.run_opportunities(token),
            False,
        )

    def observe_and_offer(
        self,
        *,
        delivery_id: str,
        event: Mapping[str, Any] | None,
        actors: Mapping[str, Any] | None,
        authorized_route: bool = True,
    ) -> tuple[ObservationResult, Any | None]:
        """Persist one delivery and atomically offer its eligible anchor."""
        observed = self.observation.observe(
            delivery_id=delivery_id,
            event=event,
            actors=actors,
            authorized_route=authorized_route,
        )
        if not observed.wake_eligible or observed.audit.event_id is None:
            return observed, None
        with self._lifecycle_lock:
            # Something new was said: the quiet a look again waits for is over.
            self._look_again = None
            self._newest_eligible = observed.audit.event_id
        return observed, self.scheduler.offer(observed.audit.event_id)

    def look_again_due(self) -> float | None:
        """Seconds until the armed look again is due, or None when none is armed."""

        with self._lifecycle_lock:
            if self._look_again is None:
                return None
            return self._look_again[1] - time.monotonic()

    def look_again(self, *, now: bool = False) -> tuple[OpportunityOutcome, ...] | None:
        """Judge the armed moment again after the room stayed quiet.

        Returns None when nothing is armed, it is not due yet (unless
        ``now``), or another opportunity is already running: the room is
        not quiet then, so the look again is dropped.
        """

        with self._lifecycle_lock:
            armed = self._look_again
            if armed is None or (not now and time.monotonic() < armed[1]):
                return None
            self._look_again = None
        token = self.scheduler.offer(armed[0], only_if_idle=True)
        if token is None:
            return None
        return self.run_opportunities(token, occasion="pause")

    def _arm_look_again(self, token: Any, decision: Mapping[str, Any], occasion: str | None) -> None:
        """Arm a look again after a judgment to wait; any other judgment disarms."""

        answers = decision.get("answers") if decision.get("status") == "ok" else None
        with self._lifecycle_lock:
            if (
                answers
                and occasion is None
                and self.look_again_seconds > 0
                and answers.get("conversation", 0) >= 0.5
                and top_move(answers) == "wait"
                # A message that arrived meanwhile is newer; the quiet is over.
                and token.anchor_event_id == self._newest_eligible
            ):
                self._look_again = (token.anchor_event_id, time.monotonic() + self.look_again_seconds)
            else:
                self._look_again = None

    def _stale_look_again(self, token: Any, occasion: str | None) -> bool:
        """A look again whose message is no longer the newest is not run."""

        with self._lifecycle_lock:
            return occasion is not None and token.anchor_event_id != self._newest_eligible

    def run_opportunities(
        self, token: Any, *, occasion: str | None = None
    ) -> tuple[OpportunityOutcome, ...]:
        """Run one active token and every newest-only successor it promotes.

        ``occasion`` applies to the first token only; its successors are new
        messages.
        """
        opportunities: list[OpportunityOutcome] = []
        while token is not None:
            if not self.scheduler.is_current(token):
                break
            if self._stale_look_again(token, occasion):
                # Something was said between the timer and the snapshot; the
                # newer message is judged instead.
                occasion = None
                token = self.scheduler.complete(token)
                continue
            deadline = time.monotonic() + self.host.host_timeout_seconds
            prepared = prepare_opportunity(
                observation=self.observation,
                attention=self.attention,
                scheduler=self.scheduler,
                token=token,
                deadline=deadline,
                occasion=occasion,
            )
            if prepared is None:
                break
            request = prepared.request
            decision = prepared.decision
            if request is not None and decision is not None:
                self._remember(request, decision)
                self._arm_look_again(token, decision, occasion)
            occasion = None
            if request is None or decision is None:
                opportunities.append(
                    OpportunityOutcome(
                        anchor_event_id=token.anchor_event_id,
                        request_id=None,
                        decision_status=None,
                        effective_disposition=None,
                        transport=None,
                        operational_error=prepared.operational_error,
                    )
                )
                token = self.scheduler.complete(token)
                continue
            transport = (
                self.host.acknowledge(
                    request=request,
                    decision=decision,
                    token=token,
                    deadline=deadline,
                )
                if prepared.acknowledge
                else self.host.run(
                    request=request,
                    decision=decision,
                    token=token,
                    error_wake=self.attention.policy.error_action == "WAKE",
                    deadline=deadline,
                )
                if prepared.wake is not None
                else None
            )
            if transport is not None and transport.delivery in ("sent", "unknown"):
                # The participant acted on the moment; there is nothing to
                # look again for.
                with self._lifecycle_lock:
                    if self._look_again is not None and self._look_again[0] == token.anchor_event_id:
                        self._look_again = None
            opportunities.append(
                OpportunityOutcome(
                    anchor_event_id=token.anchor_event_id,
                    request_id=request["request_id"],
                    decision_status=decision["status"],
                    effective_disposition=prepared.effective_disposition,
                    transport=transport,
                    operational_error=prepared.operational_error,
                )
            )
            token = self.scheduler.complete(token)
        return tuple(opportunities)

    def recall(self, event_id: str, *, timeout_seconds: float | None = None) -> Mapping[str, Any]:
        """Judge an already observed message for the participant's memory only.

        No turn follows: the answers only feed the threads the participant
        remembers. A host uses this for a message that was observed without
        being judged, such as the earlier messages of a replayed scene.
        Returns the decision, which may be an operational error.
        """

        request = self.observation.build_snapshot(event_id)
        seconds = self.host.host_timeout_seconds if timeout_seconds is None else timeout_seconds
        decision = self.attention.judge(request, deadline=time.monotonic() + seconds)
        self._remember(request, decision)
        return decision

    def _remember(self, request: Mapping[str, Any], decision: Mapping[str, Any]) -> None:
        """Keep what a judgment found about its message for the memory."""

        if decision.get("status") != "ok" or "answers" not in decision:
            return
        trigger = request["trigger_event_id"]
        event = next((item for item in request["events"] if item["id"] == trigger), None)
        if event is None or event.get("type") != "message":
            return
        self.host.memory.record_judgment(event_id=trigger, answers=decision["answers"])

    def cancel(self) -> None:
        with self._lifecycle_lock:
            self._look_again = None
        self.scheduler.cancel()
        privileged = self.host.privileged
        if privileged is not None and hasattr(privileged, "cancel"):
            privileged.cancel()

    def restart(self) -> None:
        """Invalidate active/pending work and discard ephemeral authority."""
        with self._lifecycle_lock:
            self._look_again = None
            self._newest_eligible = None
            self.scheduler.restart()
            self.observation.restart()
            self.host.memory.restart()
            privileged = self.host.privileged
            if privileged is not None and hasattr(privileged, "restart"):
                privileged.restart()


class AsyncDeliveryLane:
    """Non-blocking ingress with one active and one replaceable newest turn.

    Observation and scheduling happen synchronously under a short ingress
    lock. Participant work runs on one daemon worker, so native callbacks can
    continue retaining later conversation while the active turn is in flight.
    """

    def __init__(self, pipeline: NunchiV2Pipeline) -> None:
        self.pipeline = pipeline
        self._lock = threading.RLock()
        self._workers: set[threading.Thread] = set()
        self._idle = threading.Event()
        self._idle.set()
        self._errors: list[str] = []
        # The timer for the pipeline's armed look again, if any.
        self._look_again_timer: threading.Timer | None = None

    def submit(
        self,
        *,
        delivery_id: str,
        event: Mapping[str, Any] | None,
        actors: Mapping[str, Any] | None,
        authorized_route: bool = True,
    ) -> DeliveryOutcome:
        with self._lock:
            observed, token = self.pipeline.observe_and_offer(
                delivery_id=delivery_id,
                event=event,
                actors=actors,
                authorized_route=authorized_route,
            )
            coalesced = (
                token is None
                and observed.wake_eligible
                and observed.audit.event_id is not None
            )
            if token is not None:
                self._idle.clear()
                worker = threading.Thread(
                    target=self._run,
                    args=(token,),
                    name="nunchi-opportunity-lane",
                    daemon=True,
                )
                self._workers.add(worker)
                worker.start()
            return DeliveryOutcome(observed, (), coalesced)

    def _run(self, token: Any) -> None:
        try:
            self.pipeline.run_opportunities(token)
        except BaseException:
            self.pipeline.cancel()
            with self._lock:
                self._errors.append("opportunity worker failed")
        finally:
            with self._lock:
                self._workers.discard(threading.current_thread())
                if not self._workers:
                    self._idle.set()
            self._schedule_look_again()

    def _schedule_look_again(self) -> None:
        """Wake when the armed look again is due; a newer arming replaces it."""

        due = self.pipeline.look_again_due()
        with self._lock:
            if self._look_again_timer is not None:
                self._look_again_timer.cancel()
                self._look_again_timer = None
            if due is None:
                return
            timer = threading.Timer(max(0.0, due), self._fire_look_again)
            timer.daemon = True
            self._look_again_timer = timer
            timer.start()

    def _fire_look_again(self) -> None:
        with self._lock:
            self._look_again_timer = None
            self._idle.clear()
            worker = threading.current_thread()
            self._workers.add(worker)
        try:
            self.pipeline.look_again()
        except BaseException:
            self.pipeline.cancel()
            with self._lock:
                self._errors.append("look again failed")
        finally:
            with self._lock:
                self._workers.discard(worker)
                if not self._workers:
                    self._idle.set()
            # Messages that arrived during it may have armed a new one.
            self._schedule_look_again()

    def drain(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def _stop_look_again(self) -> None:
        with self._lock:
            if self._look_again_timer is not None:
                self._look_again_timer.cancel()
                self._look_again_timer = None

    def cancel(self) -> None:
        self._stop_look_again()
        self.pipeline.cancel()

    def restart(self) -> None:
        self._stop_look_again()
        self.pipeline.restart()

    @property
    def errors(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._errors)
