"""Shared V2 live-room runtime.

Transports attest and normalize native deliveries; this runtime records them,
coalesces live conversation opportunities, evaluates pre-attention once, and
hosts one direct participant act-or-silence turn.  It contains no platform
identity guesses and no conversational freshness heuristic.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .authorization import PrivilegedActionGuard
from .core import evaluate_v2
from .observation import OBSERVED, ObservationProvider
from .participant import ParticipantTurn, run_participant_turn
from .policy import OperatorPolicy
from .scheduling import ConversationOpportunity, ConversationOpportunityScheduler


class LiveRoomRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AcceptedDelivery:
    observation_disposition: str
    opportunity: ConversationOpportunity | None


class LiveRoomRuntime:
    """Compose the portable V2 lifecycle for one participant/room binding.

    ``accept`` is deliberately cheap and safe to call on the transport event
    loop.  A host starts one worker for a returned opportunity and calls
    ``drain`` there.  Events accepted while that worker is active replace only
    the newest pending anchor.
    """

    def __init__(
        self,
        *,
        observation: ObservationProvider,
        policy_loader: Callable[[], OperatorPolicy],
        receipt_sink: Callable[[dict[str, Any]], None],
        participant: Callable[[ParticipantTurn], Any],
        action_sink: Callable[[dict[str, Any]], Any] | None = None,
        correlated_action_sink: Callable[[str, dict[str, Any]], Any] | None = None,
        classifier_transport: Callable[[dict[str, Any], Any], Any] | None = None,
        scheduler: ConversationOpportunityScheduler | None = None,
        recover_current_history: Callable[[str], None] | None = None,
        continuation_fetch: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        authorization_guard: PrivilegedActionGuard | None = None,
        privileged_executors: Mapping[str, Callable[[Any], Any]] | None = None,
    ) -> None:
        if not isinstance(observation, ObservationProvider):
            raise LiveRoomRuntimeError("observation provider is invalid")
        if not all(callable(value) for value in (policy_loader, receipt_sink, participant)):
            raise LiveRoomRuntimeError("runtime callback is invalid")
        self.observation = observation
        self.policy_loader = policy_loader
        self.receipt_sink = receipt_sink
        self.participant = participant
        self.action_sink = action_sink
        self.correlated_action_sink = correlated_action_sink
        self.classifier_transport = classifier_transport
        self.scheduler = scheduler or ConversationOpportunityScheduler()
        self.recover_current_history = recover_current_history
        self.continuation_fetch = continuation_fetch
        self.authorization_guard = authorization_guard
        self.privileged_executors = privileged_executors

    def accept(self, native_event_input: dict[str, Any]) -> AcceptedDelivery:
        """Record one transport-attested delivery and maybe start live work."""
        disposition = self.observation.ingest(copy.deepcopy(native_event_input))
        opportunity = None
        if disposition == OBSERVED:
            event = native_event_input.get("event")
            event_id = event.get("id") if isinstance(event, dict) else None
            if not isinstance(event_id, str) or not event_id:
                # ``ingest`` already validated this; keep the host boundary
                # explicit if a hostile mutable mapping behaved inconsistently.
                raise LiveRoomRuntimeError("accepted event identity is unavailable")
            opportunity = self.scheduler.observe(
                participant_id=self.observation.participant_id,
                platform=self.observation.platform,
                room_id=self.observation.room_id,
                anchor_event_id=event_id,
            )
        return AcceptedDelivery(disposition, opportunity)

    def _policy(self) -> OperatorPolicy:
        policy = self.policy_loader()
        if not isinstance(policy, OperatorPolicy):
            raise LiveRoomRuntimeError("operator policy loader returned an invalid policy")
        if policy.attention.participant_id != self.observation.participant_id:
            raise LiveRoomRuntimeError("operator policy participant binding is invalid")
        if (
            policy.recoverability.participant_id != self.observation.participant_id
            or policy.recoverability.continuity_scope_id
            != self.observation.continuity_scope_id
        ):
            raise LiveRoomRuntimeError("recoverability policy binding is invalid")
        return policy

    def _attention_snapshot(
        self,
        opportunity: ConversationOpportunity,
        policy: OperatorPolicy,
    ) -> dict[str, Any]:
        arguments = {
            "trigger_event_id": opportunity.anchor_event_id,
            "max_events": policy.attention.attention_max_events,
            "max_bytes": policy.attention.attention_max_bytes,
        }
        try:
            return self.observation.snapshot(**arguments)
        except Exception as first_failure:
            if self.recover_current_history is None:
                raise LiveRoomRuntimeError("attention snapshot could not be assembled") from first_failure
            try:
                # Recovery is context-only.  The callback must not call this
                # runtime's scheduler or create wake work for backfilled items.
                self.recover_current_history(opportunity.anchor_event_id)
                return self.observation.snapshot(**arguments)
            except Exception as second_failure:
                raise LiveRoomRuntimeError(
                    "attention snapshot recovery did not produce a valid request"
                ) from second_failure

    def _process_one(self, opportunity: ConversationOpportunity) -> dict[str, Any]:
        try:
            policy = self._policy()
            request = self._attention_snapshot(opportunity, policy)
        except Exception:
            return {
                "status": "error",
                "error": "snapshot-unavailable",
                "anchor_event_id": opportunity.anchor_event_id,
                "participant_invoked": False,
            }

        try:
            observation_receipt = self.observation.build_observation_receipt(request)
            self.receipt_sink(copy.deepcopy(observation_receipt))
        except Exception:
            return {
                "status": "error",
                "error": "observation-receipt-persistence-unknown",
                "request_id": request["request_id"],
                "anchor_event_id": opportunity.anchor_event_id,
                "participant_invoked": False,
            }

        decision = evaluate_v2(
            request,
            policy=policy.attention,
            recoverability=policy.recoverability,
            classifier_config=policy.classifier,
            receipt_sink=self.receipt_sink,
            classifier_transport=self.classifier_transport,
        )
        if (
            decision.get("status") == "ok"
            and decision.get("effective_disposition") == "SUPPRESS"
        ):
            return {
                "status": "suppressed",
                "request_id": request["request_id"],
                "anchor_event_id": opportunity.anchor_event_id,
                "participant_invoked": False,
                "decision": copy.deepcopy(decision),
            }

        advice_evidence = tuple(
            dict.fromkeys(
                event_id
                for advice in decision.get("attention_advice", [])
                if isinstance(advice, dict)
                for event_id in advice.get("evidence_event_ids", [])
                if isinstance(event_id, str) and event_id
            )
        )
        try:
            participant_snapshot = self.observation.participant_snapshot(
                trigger_event_id=opportunity.anchor_event_id,
                request_id=request["request_id"],
                max_events=policy.attention.participant_max_events,
                max_bytes=policy.attention.participant_max_bytes,
                required_event_ids=advice_evidence,
            )
        except Exception:
            return {
                "status": "error",
                "error": "participant-snapshot-unavailable",
                "request_id": request["request_id"],
                "anchor_event_id": opportunity.anchor_event_id,
                "participant_invoked": False,
                "decision": copy.deepcopy(decision),
            }

        participant_result = run_participant_turn(
            participant_snapshot,
            decision,
            policy=policy.attention,
            participant=self.participant,
            receipt_sink=self.receipt_sink,
            action_sink=self.action_sink,
            correlated_action_sink=self.correlated_action_sink,
            continuation_fetch=self.continuation_fetch,
            authorization_guard=self.authorization_guard,
            privileged_executors=self.privileged_executors,
        )
        return {
            "status": participant_result["status"],
            "request_id": request["request_id"],
            "anchor_event_id": opportunity.anchor_event_id,
            "participant_invoked": participant_result["invoked"],
            "decision": copy.deepcopy(decision),
            "participant": participant_result,
        }

    def drain(self, opportunity: ConversationOpportunity) -> tuple[dict[str, Any], ...]:
        """Run exact active work and any one-at-a-time coalesced successors."""
        results: list[dict[str, Any]] = []
        current: ConversationOpportunity | None = opportunity
        while current is not None:
            try:
                result = self._process_one(current)
            except Exception:
                result = {
                    "status": "error",
                    "error": "runtime-failure",
                    "anchor_event_id": current.anchor_event_id,
                    "participant_invoked": False,
                }
            finally:
                next_opportunity = self.scheduler.complete(current)
            results.append(result)
            current = next_opportunity
        return tuple(results)

    def process_delivery(self, native_event_input: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        """Synchronous convenience for transports without an event loop."""
        accepted = self.accept(native_event_input)
        if accepted.opportunity is None:
            return ()
        return self.drain(accepted.opportunity)


__all__ = [
    "AcceptedDelivery",
    "LiveRoomRuntime",
    "LiveRoomRuntimeError",
]
