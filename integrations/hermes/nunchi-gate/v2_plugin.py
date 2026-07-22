"""Hermes 0.19.0 plugin boundary for the Nunchi V2 adapter.

The public plugin callbacks are intentionally thin.  Canonical identity,
observation, scheduling, and ticket rendering live in :mod:`v2_runtime`; this
module owns Hermes hook/middleware calling conventions and fail-closed effect
handling.
"""

from __future__ import annotations

import asyncio
import contextvars
import copy
import functools
import hashlib
import importlib.util
import inspect
import json
import logging
import os
import sys
import threading
import uuid
import weakref
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


logger = logging.getLogger(__name__)


def _load_runtime_module():
    existing = sys.modules.get("nunchi_hermes_v2_runtime")
    if existing is not None:
        return existing
    path = Path(__file__).with_name("v2_runtime.py")
    spec = importlib.util.spec_from_file_location("nunchi_hermes_v2_runtime", path)
    if spec is None or spec.loader is None:
        raise ImportError("Hermes V2 runtime module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_v2 = _load_runtime_module()
HermesV2BoundaryError = _v2.HermesV2BoundaryError

_NON_PRIVILEGED_TOOLS = frozenset({"web_search", "web_extract"})

# Installed plugins are loaded by file path; resolve the sibling runtime before
# importing candidate-package services from the checkout injected by the loader.
from nunchi.authorization import (  # noqa: E402
    PrivilegedActionCoordinator,
    PrivilegedActionGuard,
    canonical_action_digest,
)
from nunchi.core import evaluate_v2  # noqa: E402
from nunchi.participant import build_participant_wake  # noqa: E402
from nunchi.policy import OperatorPolicy, OperatorPolicySource  # noqa: E402
from nunchi.receipts import (  # noqa: E402
    ReloadingPolicyAuthorizationSink,
    ReloadingPolicyReceiptSink,
    transport_receipt,
)


@dataclass(frozen=True)
class OpportunityEvaluation:
    status: str
    binding: Any
    opportunity: Any
    request: dict[str, Any]
    decision: dict[str, Any]
    participant_snapshot: dict[str, Any] | None
    packet: dict[str, Any] | None
    receipt_sink: Callable[[dict[str, Any]], None]
    promoted: Any = None
    policy_identity: str | None = None
    policy_fingerprint: str | None = None
    policy_loader: Callable[[], OperatorPolicy] | None = None


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    evaluation: OpportunityEvaluation | None = None


@dataclass(frozen=True)
class HostDelivery:
    event: Any
    gateway: Any
    session_key: str
    participant_id: str
    policy_loader: Callable[[], OperatorPolicy]
    receipt_sink: Callable[[dict[str, Any]], None]
    classifier_transport: Callable[[dict[str, Any], Any], Any] | None
    redispatch: Callable[[Any, Any], None] | None
    policy_identity: str | None = None


@dataclass(frozen=True)
class AcceptedHostDelivery:
    binding: Any
    opportunity: Any
    host: HostDelivery


class _DeliveryCancellation:
    """Serialize executor cancellation against stage-and-redispatch commit."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.cancelled = False
        self.completed = False


def _operator_policy_fingerprint(policy: OperatorPolicy) -> str:
    if not isinstance(policy, OperatorPolicy):
        raise HermesV2BoundaryError("operator policy is invalid")
    return hashlib.sha256(repr(policy).encode("utf-8")).hexdigest()


class HermesV2Controller:
    """Process-local owner of exact bindings and one-use participant tickets."""

    def __init__(
        self,
        *,
        participant_id: str,
        max_participants: int = 64,
        max_pending_authorizations: int = 128,
        authorization_sink_factory: Callable[[Callable[[], OperatorPolicy]], Any] = ReloadingPolicyAuthorizationSink,
    ) -> None:
        if not isinstance(max_participants, int) or max_participants < 1:
            raise HermesV2BoundaryError("participant registry limit is invalid")
        if not callable(authorization_sink_factory):
            raise HermesV2BoundaryError("authorization sink factory is invalid")
        if (
            isinstance(max_pending_authorizations, bool)
            or not isinstance(max_pending_authorizations, int)
            or not 1 <= max_pending_authorizations <= 10000
        ):
            raise HermesV2BoundaryError("pending authorization limit is invalid")
        self.max_participants = max_participants
        self.max_pending_authorizations = max_pending_authorizations
        self._default_participant = str(participant_id)
        self.registry = _v2.BindingRegistry(participant_id=participant_id)
        self._registries = {participant_id: self.registry}
        self.tickets = _v2.TurnTicketStore()
        self._tool_session: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "nunchi_hermes_v2_tool_session", default=None
        )
        self._transport_session: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "nunchi_hermes_v2_transport_session", default=None
        )
        self._output_collection: contextvars.ContextVar[dict[str, Any] | None] = (
            contextvars.ContextVar("nunchi_hermes_v2_output_collection", default=None)
        )
        self._lock = threading.RLock()
        self._turns: dict[str, OpportunityEvaluation] = {}
        self._host_deliveries: dict[tuple[str, Any, str], HostDelivery] = {}
        self._control_output_boundaries: dict[str, int] = {}
        self._authorization_sink_factory = authorization_sink_factory
        self._participant_receipts: dict[str, OpportunityEvaluation] = {}
        self._pending_authorizations: dict[str, tuple[Any, Any]] = {}
        self._pending_authorization_reservations = 0

    def registry_for(self, participant_id: str):
        participant = str(participant_id).strip()
        if not participant:
            raise HermesV2BoundaryError("configured participant is unavailable")
        with self._lock:
            registry = self._registries.get(participant)
            if registry is None:
                if len(self._registries) >= self.max_participants:
                    evictable = next(
                        (
                            candidate
                            for candidate, candidate_registry
                            in self._registries.items()
                            if candidate != self._default_participant
                            and candidate_registry.idle()
                        ),
                        None,
                    )
                    if evictable is None:
                        raise HermesV2BoundaryError(
                            "participant registry is full of active participants"
                        )
                    self._registries.pop(evictable, None)
                registry = _v2.BindingRegistry(participant_id=participant)
                self._registries[participant] = registry
            return registry

    @staticmethod
    def _host_delivery_key(binding: Any, event_id: str) -> tuple[str, Any, str]:
        return (
            str(binding.observation.participant_id),
            binding.key,
            str(event_id),
        )

    def _prune_host_deliveries(self, binding: Any) -> None:
        retained = set()
        for row in binding.scheduler.snapshot():
            for field in ("active_anchor_event_id", "pending_anchor_event_id"):
                event_id = row.get(field)
                if isinstance(event_id, str) and event_id:
                    retained.add(event_id)
        with self._lock:
            for delivery_key in tuple(self._host_deliveries):
                participant_id, key, event_id = delivery_key
                if (
                    participant_id == binding.observation.participant_id
                    and key == binding.key
                    and event_id not in retained
                ):
                    self._host_deliveries.pop(delivery_key, None)

    def _drop_host_delivery(self, binding: Any, event_id: str) -> None:
        with self._lock:
            self._host_deliveries.pop(
                self._host_delivery_key(binding, event_id), None
            )

    def process_delivery(
        self,
        *,
        event: Any,
        gateway: Any,
        session_key: str,
        participant_id: str,
        policy_loader: Callable[[], OperatorPolicy],
        receipt_sink: Callable[[dict[str, Any]], None],
        classifier_transport: Callable[[dict[str, Any], Any], Any] | None = None,
        redispatch: Callable[[Any, Any], None] | None = None,
        policy_identity: str | None = None,
        schedule: bool = True,
    ) -> DeliveryResult:
        """Project, retain, judge, and (on WAKE/DEFER) stage one Hermes turn."""
        accepted = self.accept_delivery(
            event=event,
            gateway=gateway,
            session_key=session_key,
            participant_id=participant_id,
            policy_loader=policy_loader,
            receipt_sink=receipt_sink,
            classifier_transport=classifier_transport,
            redispatch=redispatch,
            policy_identity=policy_identity,
            schedule=schedule,
        )
        if accepted.opportunity is None:
            return DeliveryResult("observed")
        return self.evaluate_delivery(accepted)

    def accept_delivery(
        self,
        *,
        event: Any,
        gateway: Any,
        session_key: str,
        participant_id: str,
        policy_loader: Callable[[], OperatorPolicy],
        receipt_sink: Callable[[dict[str, Any]], None],
        classifier_transport: Callable[[dict[str, Any], Any], Any] | None = None,
        redispatch: Callable[[Any, Any], None] | None = None,
        policy_identity: str | None = None,
        schedule: bool = True,
    ) -> AcceptedHostDelivery:
        """Synchronously retain a native event and reserve scheduler order."""
        key = _v2.resolve_binding_key(event, gateway)
        native_input = _v2.project_native_event(event, key)
        event_id = native_input["event"]["id"]
        host = HostDelivery(
            event=event,
            gateway=gateway,
            session_key=session_key,
            participant_id=participant_id,
            policy_loader=policy_loader,
            receipt_sink=receipt_sink,
            classifier_transport=classifier_transport,
            redispatch=redispatch,
            policy_identity=(
                str(Path(policy_identity).expanduser().resolve())
                if policy_identity else None
            ),
        )
        binding = self.registry_for(participant_id).get_or_create(key)
        if schedule:
            with self._lock:
                self._host_deliveries[
                    self._host_delivery_key(binding, event_id)
                ] = host
            accepted = binding.accept(native_input)
        else:
            accepted = binding.accept_context(native_input)
        self._prune_host_deliveries(binding)
        return AcceptedHostDelivery(binding, accepted.opportunity, host)

    def evaluate_delivery(
        self,
        accepted: AcceptedHostDelivery,
        *,
        cancellation: _DeliveryCancellation | None = None,
    ) -> DeliveryResult:
        if accepted.opportunity is None:
            return DeliveryResult("observed")
        try:
            evaluation = self.evaluate_opportunity(
                binding=accepted.binding,
                opportunity=accepted.opportunity,
                policy_loader=accepted.host.policy_loader,
                receipt_sink=accepted.host.receipt_sink,
                classifier_transport=accepted.host.classifier_transport,
                policy_identity=accepted.host.policy_identity,
                complete_scheduler=cancellation is None,
            )
        except BaseException:
            if cancellation is None:
                self.fail_delivery(accepted)
            else:
                with cancellation.lock:
                    if not cancellation.cancelled:
                        self.fail_delivery(accepted)
            raise
        if evaluation.status == "wake":
            if cancellation is None:
                self.stage_turn(
                    evaluation=evaluation,
                    session_key=accepted.host.session_key,
                )
            else:
                with cancellation.lock:
                    if cancellation.cancelled:
                        return DeliveryResult("cancelled", evaluation)
                    self.stage_turn(
                        evaluation=evaluation,
                        session_key=accepted.host.session_key,
                    )
        else:
            if cancellation is not None:
                with cancellation.lock:
                    if cancellation.cancelled:
                        return DeliveryResult("cancelled", evaluation)
                    promoted = accepted.binding.scheduler.complete(
                        accepted.opportunity
                    )
                    cancellation.completed = True
                evaluation = replace(evaluation, promoted=promoted)
            self._drop_host_delivery(
                accepted.binding, accepted.opportunity.anchor_event_id
            )
            if evaluation.promoted is not None:
                self._promote(accepted.binding, evaluation.promoted)
        return DeliveryResult(evaluation.status, evaluation)

    def fail_delivery(
        self,
        accepted: AcceptedHostDelivery,
        *,
        discard_pending: bool = False,
    ) -> None:
        if accepted.opportunity is not None:
            promoted = accepted.binding.scheduler.complete(accepted.opportunity)
            self._drop_host_delivery(
                accepted.binding, accepted.opportunity.anchor_event_id
            )
            if discard_pending:
                while promoted is not None:
                    self._drop_host_delivery(
                        accepted.binding, promoted.anchor_event_id
                    )
                    promoted = accepted.binding.scheduler.complete(promoted)
                self._prune_host_deliveries(accepted.binding)
                return
            if promoted is not None:
                self._promote(accepted.binding, promoted)

    def cancel_delivery(
        self,
        accepted: AcceptedHostDelivery,
        cancellation: _DeliveryCancellation,
        *,
        discard_pending: bool = False,
    ) -> None:
        """Cancel once without racing an already completed non-wake generation."""
        with cancellation.lock:
            if cancellation.cancelled:
                return
            cancellation.cancelled = True
            if cancellation.completed:
                return
            session_key = accepted.host.session_key
            if self.is_ticketed(session_key):
                self.abort_participant_turn(
                    session_key, discard_pending=discard_pending
                )
            else:
                self.fail_delivery(accepted, discard_pending=discard_pending)

    def evaluate_opportunity(
        self,
        *,
        binding: Any,
        opportunity: Any,
        policy_loader: Callable[[], OperatorPolicy],
        receipt_sink: Callable[[dict[str, Any]], None],
        classifier_transport: Callable[[dict[str, Any], Any], Any] | None = None,
        policy_identity: str | None = None,
        complete_scheduler: bool = True,
    ) -> OpportunityEvaluation:
        """Evaluate one scheduler-issued opportunity exactly once."""
        if opportunity is None:
            raise HermesV2BoundaryError("conversation opportunity is unavailable")
        policy = policy_loader()
        if not isinstance(policy, OperatorPolicy):
            raise HermesV2BoundaryError("operator policy is invalid")
        if policy.attention.participant_id != binding.observation.participant_id:
            raise HermesV2BoundaryError("operator policy participant binding is invalid")
        if (
            policy.recoverability.participant_id != binding.observation.participant_id
            or policy.recoverability.continuity_scope_id
            != binding.observation.continuity_scope_id
        ):
            raise HermesV2BoundaryError("operator policy continuity binding is invalid")
        policy_fingerprint = _operator_policy_fingerprint(policy)

        request = binding.observation.snapshot(
            trigger_event_id=opportunity.anchor_event_id,
            max_events=policy.attention.attention_max_events,
            max_bytes=policy.attention.attention_max_bytes,
        )
        self._persist_receipt(
            receipt_sink,
            binding.observation.build_observation_receipt(request),
            stage="observation",
        )
        decision = evaluate_v2(
            request,
            policy=policy.attention,
            recoverability=policy.recoverability,
            classifier_config=policy.classifier,
            receipt_sink=receipt_sink,
            classifier_transport=classifier_transport,
        )
        if (
            decision.get("status") == "ok"
            and decision.get("effective_disposition") == "SUPPRESS"
        ):
            promoted = (
                binding.scheduler.complete(opportunity)
                if complete_scheduler
                else None
            )
            return OpportunityEvaluation(
                "suppressed", binding, opportunity, copy.deepcopy(request),
                copy.deepcopy(decision), None, None, receipt_sink,
                promoted=promoted,
                policy_identity=policy_identity,
                policy_fingerprint=policy_fingerprint,
            )
        cited = tuple(
            dict.fromkeys(
                event_id
                for advice in decision.get("attention_advice", [])
                if isinstance(advice, dict)
                for event_id in advice.get("evidence_event_ids", [])
                if isinstance(event_id, str) and event_id
            )
        )
        participant_snapshot = binding.observation.participant_snapshot(
            trigger_event_id=opportunity.anchor_event_id,
            request_id=request["request_id"],
            max_events=policy.attention.participant_max_events,
            max_bytes=policy.attention.participant_max_bytes,
            required_event_ids=cited,
        )
        packet = build_participant_wake(
            participant_snapshot, decision, policy=policy.attention
        )
        if decision.get("status") == "error" and policy.attention.error_action == "NO_WAKE":
            evaluation = OpportunityEvaluation(
                "no-wake", binding, opportunity, copy.deepcopy(request),
                copy.deepcopy(decision), copy.deepcopy(participant_snapshot),
                copy.deepcopy(packet), receipt_sink,
                policy_identity=policy_identity,
                policy_fingerprint=policy_fingerprint,
            )
            self._persist_receipt(
                receipt_sink,
                self._participant_receipt(
                    evaluation, outcome="unknown", invoked=False
                ),
                stage="participant-host",
            )
            promoted = (
                binding.scheduler.complete(opportunity)
                if complete_scheduler
                else None
            )
            return OpportunityEvaluation(
                "no-wake", binding, opportunity, copy.deepcopy(request),
                copy.deepcopy(decision), copy.deepcopy(participant_snapshot),
                copy.deepcopy(packet), receipt_sink,
                promoted=promoted,
                policy_identity=policy_identity,
                policy_fingerprint=policy_fingerprint,
            )
        return OpportunityEvaluation(
            "wake", binding, opportunity, copy.deepcopy(request),
            copy.deepcopy(decision), copy.deepcopy(participant_snapshot),
            copy.deepcopy(packet), receipt_sink,
            policy_identity=policy_identity,
            policy_fingerprint=policy_fingerprint,
            policy_loader=policy_loader,
        )

    def stage_turn(
        self,
        *,
        evaluation: OpportunityEvaluation,
        session_key: str,
    ):
        if not isinstance(evaluation, OpportunityEvaluation) or evaluation.status != "wake":
            raise HermesV2BoundaryError("only a waking evaluation can stage a turn")
        assert evaluation.packet is not None
        with self._lock:
            if self._control_output_boundaries.get(session_key, 0):
                raise HermesV2BoundaryError(
                    "Hermes turn cannot stage during control output"
                )
            if session_key in self._turns:
                raise HermesV2BoundaryError("Hermes session already has a staged turn")
            ticket = self.tickets.issue(
                event_id=evaluation.packet["trigger_event_id"],
                session_key=session_key,
                packet=evaluation.packet,
            )
            self._turns[session_key] = evaluation
            return ticket

    @staticmethod
    def _persist_receipt(
        receipt_sink: Callable[[dict[str, Any]], None],
        receipt: dict[str, Any],
        *,
        stage: str,
    ) -> None:
        returned = receipt_sink(copy.deepcopy(receipt))
        if returned is not None:
            raise HermesV2BoundaryError(
                f"{stage} receipt persistence is unknown"
            )

    @staticmethod
    def _participant_receipt(
        evaluation: OpportunityEvaluation,
        *,
        outcome: str,
        invoked: bool = True,
    ) -> dict[str, Any]:
        assert evaluation.packet is not None
        packet = evaluation.packet
        return {
            "request_id": packet["request_id"],
            "stage": "participant-host",
            "writer": "participant-host",
            "body": {
                "wake_source": packet["attention"]["source"],
                "packet_event_count": len(packet["events"]),
                "packet_byte_count": len(
                    json.dumps(
                        packet, ensure_ascii=False, allow_nan=False,
                        sort_keys=True, separators=(",", ":"),
                    ).encode("utf-8")
                ),
                "delivered_event_ids": [event["id"] for event in packet["events"]],
                "expansion_calls": 0,
                "invoked": invoked,
                "outcome": outcome,
            },
        }

    def _persist_participant_receipt_once(
        self,
        session_key: str,
        evaluation: OpportunityEvaluation,
        *,
        outcome: str,
    ) -> None:
        with self._lock:
            if self._turns.get(session_key) is not evaluation:
                raise HermesV2BoundaryError("Hermes turn provenance expired")
            if self._participant_receipts.get(session_key) is evaluation:
                return
            self._persist_receipt(
                evaluation.receipt_sink,
                self._participant_receipt(evaluation, outcome=outcome),
                stage="participant-host",
            )
            self._participant_receipts[session_key] = evaluation

    def _prepare_tool_effect(
        self, session_key: str, evaluation: OpportunityEvaluation
    ) -> None:
        self._persist_participant_receipt_once(
            session_key, evaluation, outcome="unknown"
        )
        self.set_transport_session(session_key)

    def complete_participant_turn(self, session_key: str, response: Any) -> dict[str, Any] | None:
        with self._lock:
            evaluation = self._turns.get(session_key)
        if evaluation is None:
            raise HermesV2BoundaryError("Hermes turn is not Nunchi-ticketed")
        if response is None or response == "":
            action = None
            outcome = "silent"
        elif isinstance(response, str):
            action = {"kind": "message", "content": response}
            outcome = "unknown"
        elif isinstance(response, dict) and response.get("kind") == "message":
            if (
                set(response) - {"kind", "content", "reply_to_event_id", "mention_actor_ids"}
                or not isinstance(response.get("content"), str)
                or not response["content"]
            ):
                raise HermesV2BoundaryError("Hermes participant message is invalid")
            action = copy.deepcopy(response)
            outcome = "unknown"
        elif isinstance(response, dict) and response.get("kind") == "reaction":
            if set(response) != {"kind", "target_event_id", "reaction"} or not all(
                isinstance(response.get(field), str) and response[field]
                for field in ("target_event_id", "reaction")
            ):
                raise HermesV2BoundaryError("Hermes participant reaction is invalid")
            action = copy.deepcopy(response)
            outcome = "unknown"
        else:
            raise HermesV2BoundaryError("Hermes participant outcome is unsupported")
        already_persisted = False
        with self._lock:
            already_persisted = self._participant_receipts.get(session_key) is evaluation
        try:
            self._persist_participant_receipt_once(
                session_key, evaluation, outcome=outcome
            )
        except BaseException:
            self._finish_turn(session_key, evaluation)
            raise
        if action is None and already_persisted:
            # A tool/reaction effect already supplied this turn's concrete action.
            # Keep transport ownership alive until the enclosing process wrapper
            # records that effect's delivery result.
            action = {"kind": "tool"}
        elif action is None:
            self._finish_turn(session_key, evaluation)
        return action

    def complete_transport(
        self,
        session_key: str,
        *,
        delivery: str,
        detail: str | None = None,
        expected_evaluation: OpportunityEvaluation | None = None,
    ):
        with self._lock:
            evaluation = self._turns.get(session_key)
            if (
                expected_evaluation is not None
                and evaluation is not expected_evaluation
            ):
                return None
        if evaluation is None:
            raise HermesV2BoundaryError("Hermes transport is not Nunchi-ticketed")
        try:
            self._persist_receipt(
                evaluation.receipt_sink,
                transport_receipt(
                    evaluation.request["request_id"], delivery, detail=detail
                ),
                stage="transport",
            )
        finally:
            promoted = self._finish_turn(session_key, evaluation)
        return promoted

    def _finish_turn(
        self,
        session_key: str,
        evaluation: OpportunityEvaluation,
        *,
        promote_pending: bool = True,
    ):
        with self._lock:
            if self._turns.get(session_key) is not evaluation:
                return None
            self._turns.pop(session_key, None)
            self._participant_receipts.pop(session_key, None)
            self.tickets.complete_session(session_key)
        self._tool_session.set(None)
        promoted = evaluation.binding.scheduler.complete(evaluation.opportunity)
        self._drop_host_delivery(
            evaluation.binding, evaluation.opportunity.anchor_event_id
        )
        if not promote_pending:
            while promoted is not None:
                self._drop_host_delivery(
                    evaluation.binding, promoted.anchor_event_id
                )
                promoted = evaluation.binding.scheduler.complete(promoted)
            self._prune_host_deliveries(evaluation.binding)
            return None
        if promoted is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                self._promote(evaluation.binding, promoted)
            else:
                loop.run_in_executor(
                    None, self._promote, evaluation.binding, promoted
                )
        return promoted

    def _promote(self, binding: Any, opportunity: Any) -> DeliveryResult:
        with self._lock:
            host = self._host_deliveries.get(
                self._host_delivery_key(binding, opportunity.anchor_event_id)
            )
        if host is None:
            binding.scheduler.complete(opportunity)
            return DeliveryResult("dropped")
        staged = False
        try:
            evaluation = self.evaluate_opportunity(
                binding=binding,
                opportunity=opportunity,
                policy_loader=host.policy_loader,
                receipt_sink=host.receipt_sink,
                classifier_transport=host.classifier_transport,
                policy_identity=host.policy_identity,
            )
            if evaluation.status == "wake":
                self.stage_turn(evaluation=evaluation, session_key=host.session_key)
                staged = True
                if callable(host.redispatch):
                    host.redispatch(host.event, host.gateway)
            else:
                self._drop_host_delivery(binding, opportunity.anchor_event_id)
                if evaluation.promoted is not None:
                    self._promote(binding, evaluation.promoted)
            return DeliveryResult(evaluation.status, evaluation)
        except BaseException:
            if staged:
                self.abort_participant_turn(host.session_key)
                return DeliveryResult("error")
            try:
                promoted = binding.scheduler.complete(opportunity)
            except Exception:
                promoted = None
            self._drop_host_delivery(binding, opportunity.anchor_event_id)
            if promoted is not None:
                self._promote(binding, promoted)
            return DeliveryResult("error")

    def attest_participant_turn(
        self,
        *,
        session_key: str,
        event: Any,
        source: Any,
        gateway: Any,
        config: dict[str, Any],
    ) -> None:
        with self._lock:
            evaluation = self._turns.get(str(session_key))
        if evaluation is None:
            raise HermesV2BoundaryError("Hermes turn is not Nunchi-ticketed")
        if str(config.get("participant_id") or "").strip() != str(
            evaluation.binding.observation.participant_id
        ):
            raise HermesV2BoundaryError("configured participant changed after admission")

        current_source = source
        normalizer = getattr(gateway, "_normalize_source_for_session_key", None)
        if callable(normalizer):
            current_source = normalizer(source)
        current_event = copy.copy(event)
        current_event.source = current_source
        current_event_id = _canonical_event_id(current_event)
        packet_event_id = (
            evaluation.packet.get("trigger_event_id")
            if isinstance(evaluation.packet, dict)
            else None
        )
        if current_event_id is None or current_event_id != packet_event_id:
            raise HermesV2BoundaryError("participant trigger changed after admission")
        current_key = _v2.resolve_binding_key(current_event, gateway)
        if current_key != evaluation.binding.key:
            raise HermesV2BoundaryError("authenticated binding changed after admission")
        session_resolver = getattr(gateway, "_session_key_for_source", None)
        if not callable(session_resolver) or str(
            session_resolver(current_source) or ""
        ) != str(session_key):
            raise HermesV2BoundaryError("Hermes session changed after admission")

        if evaluation.policy_identity is not None:
            current_path = str(
                Path(str(config.get("policy_path") or "")).expanduser().resolve()
            )
            if current_path != evaluation.policy_identity:
                raise HermesV2BoundaryError("operator policy source changed after admission")
            current_policy = OperatorPolicySource(current_path).load()
            if (
                _operator_policy_fingerprint(current_policy)
                != evaluation.policy_fingerprint
            ):
                raise HermesV2BoundaryError("operator policy changed after admission")

        runtime_resolver = getattr(gateway, "_resolve_session_agent_runtime", None)
        if callable(runtime_resolver):
            resolved_runtime = runtime_resolver(
                source=current_source,
                session_key=str(session_key),
                user_config=None,
            )
            if not isinstance(resolved_runtime, tuple) or len(resolved_runtime) != 2:
                raise HermesV2BoundaryError(
                    "effective Hermes session runtime is unavailable"
                )
            runtime = resolved_runtime[1]
            if str((runtime or {}).get("api_mode") or "").strip().lower() == (
                "codex_app_server"
            ):
                raise HermesV2BoundaryError(
                    "effective Hermes session runtime bypasses tool authorization"
                )

    def pre_llm_call(self, *, session_key: str | None) -> dict[str, str] | None:
        if not session_key:
            return None
        context = self.tickets.context_for_session(session_key)
        return {"context": context} if context else None

    def bind_tool_session(self, session_key: str):
        if not self.tickets.context_for_session(session_key):
            raise HermesV2BoundaryError("Hermes turn has no Nunchi wake ticket")
        return self._tool_session.set(session_key)

    def reset_tool_session(self, token: contextvars.Token) -> None:
        self._tool_session.reset(token)

    def is_ticketed(self, session_key: str) -> bool:
        with self._lock:
            return session_key in self._turns and bool(
                self.tickets.context_for_session(session_key)
            )

    def evaluation_for_session(
        self, session_key: str
    ) -> OpportunityEvaluation | None:
        with self._lock:
            evaluation = self._turns.get(session_key)
            if evaluation is None or not self.tickets.context_for_session(session_key):
                return None
            return evaluation

    def begin_control_output(
        self, session_key: str
    ) -> tuple[bool, OpportunityEvaluation | None]:
        """Acquire a session barrier before any control I/O can race staging."""
        with self._lock:
            count = self._control_output_boundaries.get(session_key, 0)
            evaluation = self._turns.get(session_key)
            self._control_output_boundaries[session_key] = count + 1
            return True, evaluation

    def finish_control_output(self, session_key: str) -> None:
        with self._lock:
            count = self._control_output_boundaries.get(session_key, 0)
            if count <= 1:
                self._control_output_boundaries.pop(session_key, None)
            else:
                self._control_output_boundaries[session_key] = count - 1

    def control_output_active(self, session_key: str) -> bool:
        with self._lock:
            return self._control_output_boundaries.get(session_key, 0) > 0

    def set_transport_session(self, session_key: str) -> None:
        if not self.is_ticketed(session_key):
            raise HermesV2BoundaryError("Hermes transport has no Nunchi turn")
        self._transport_session.set(session_key)

    def current_transport_session(self) -> str | None:
        return self._transport_session.get()

    def clear_transport_session(self) -> None:
        self._transport_session.set(None)

    def begin_output_collection(self, session_key: str, *, guard_only: bool = False):
        with self._lock:
            evaluation = self._turns.get(session_key)
            if not guard_only and (
                evaluation is None
                or not self.tickets.context_for_session(session_key)
            ):
                return None
        return self._output_collection.set(
            {
                "session_key": session_key,
                "attempts": [],
                "guard_only": guard_only,
                "evaluation": evaluation,
            }
        )

    def suppress_host_telemetry(self) -> bool:
        return self._output_collection.get() is not None

    def record_output_attempt(
        self, *, result: Any = None, error: BaseException | None = None
    ) -> None:
        collection = self._output_collection.get()
        session_key = self.current_transport_session()
        if collection is None or not session_key:
            return
        if collection.get("session_key") != session_key:
            raise HermesV2BoundaryError("Hermes transport session crossed output scopes")
        if error is not None:
            status = "unknown"
        else:
            success = getattr(result, "success", None)
            if isinstance(success, bool):
                status = "sent" if success else "failed"
            elif isinstance(result, bool):
                status = "sent" if result else "failed"
            else:
                status = "unknown"
        collection["attempts"].append(status)

    def assert_terminal_output_allowed(self) -> None:
        collection = self._output_collection.get()
        if collection is not None and self.current_transport_session() is None:
            raise HermesV2BoundaryError(
                "platform output preceded the participant-host receipt"
            )

    def finish_output_collection(
        self,
        token: contextvars.Token | None,
        *,
        defer_receipt: bool = False,
    ) -> tuple[
        str, str, str | None, OpportunityEvaluation
    ] | None:
        if token is None:
            return
        collection = self._output_collection.get()
        try:
            if not isinstance(collection, dict):
                return
            if collection.get("guard_only") is True:
                return
            session_key = str(collection.get("session_key") or "")
            evaluation = collection.get("evaluation")
            if not session_key or self.current_transport_session() != session_key:
                return
            if not isinstance(evaluation, OpportunityEvaluation):
                return
            attempt_values = collection.get("attempts")
            attempts = (
                tuple(attempt_values)
                if isinstance(attempt_values, (list, tuple))
                else ()
            )
            if attempts and all(status == "sent" for status in attempts):
                delivery, detail = "sent", None
            elif "failed" in attempts and "sent" not in attempts and "unknown" not in attempts:
                delivery, detail = "failed", "terminal output rejected"
            else:
                delivery, detail = "unknown", "terminal output was not wholly attested"
            if defer_receipt:
                return session_key, delivery, detail, evaluation
            self.complete_transport(
                session_key,
                delivery=delivery,
                detail=detail,
                expected_evaluation=evaluation,
            )
            self.clear_transport_session()
            return None
        finally:
            self._output_collection.reset(token)

    def abort_participant_turn(
        self,
        session_key: str,
        *,
        discard_pending: bool = False,
        invoked: bool = False,
        expected_evaluation: OpportunityEvaluation | None = None,
    ) -> None:
        with self._lock:
            evaluation = self._turns.get(session_key)
        if evaluation is None or (
            expected_evaluation is not None
            and evaluation is not expected_evaluation
        ):
            return
        try:
            with self._lock:
                already_persisted = (
                    self._participant_receipts.get(session_key) is evaluation
                )
            if not already_persisted:
                self._persist_receipt(
                    evaluation.receipt_sink,
                    self._participant_receipt(
                        evaluation, outcome="unknown", invoked=invoked
                    ),
                    stage="participant-host",
                )
        finally:
            self._finish_turn(
                session_key,
                evaluation,
                promote_pending=not discard_pending,
            )

    @staticmethod
    def _invoke_tool(
        next_call: Callable[..., Any], arguments: dict[str, Any]
    ) -> Any:
        try:
            signature = inspect.signature(next_call)
            signature.bind(arguments)
        except (TypeError, ValueError):
            return next_call()
        return next_call(arguments)

    @staticmethod
    def _close_authorization_sink(sink: Any) -> None:
        close = getattr(sink, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _reaction_scope(
        platform: str, room_id: str
    ) -> tuple[set[str], str]:
        parts = room_id.split(":")
        if platform == "discord":
            if len(parts) == 3 and parts[:2] == ["discord", "channel"]:
                native_target = parts[2]
            elif len(parts) == 4 and parts[:2] == ["discord", "thread"]:
                native_target = parts[3]
            else:
                raise HermesV2BoundaryError("Discord reaction room is invalid")
            return {room_id, f"discord:{native_target}"}, "discord:message:"
        if platform == "telegram":
            if len(parts) == 3 and parts[:2] == ["telegram", "chat"]:
                chat_id = parts[2]
                target = f"telegram:{chat_id}"
            elif (
                len(parts) == 5
                and parts[:2] == ["telegram", "chat"]
                and parts[3] == "topic"
            ):
                chat_id = parts[2]
                target = f"telegram:{chat_id}:{parts[4]}"
            else:
                raise HermesV2BoundaryError("Telegram reaction room is invalid")
            return {room_id, target}, f"telegram:message:{chat_id}:"
        raise HermesV2BoundaryError("reaction platform is unsupported")

    @staticmethod
    def _privileged_action(
        evaluation: OpportunityEvaluation,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if evaluation.packet is None:
            raise HermesV2BoundaryError("participant packet is unavailable")
        packet = evaluation.packet
        room = packet.get("room")
        self_facts = packet.get("self")
        if not isinstance(room, dict) or not isinstance(self_facts, dict):
            raise HermesV2BoundaryError("participant scope is unavailable")
        platform = room.get("platform")
        room_id = room.get("id")
        participant_id = self_facts.get("participant_id")
        if (
            not isinstance(platform, str)
            or not platform
            or not isinstance(room_id, str)
            or not room_id
            or not isinstance(participant_id, str)
            or not participant_id
        ):
            raise HermesV2BoundaryError("participant scope is unavailable")

        capability: str
        impact = "mutation"
        resource: dict[str, str]
        if tool_name == "write_file":
            path = arguments.get("path")
            if not isinstance(path, str) or not path:
                raise HermesV2BoundaryError("write_file path is invalid")
            capability = "workspace.file.write"
            resource = {"kind": "workspace-file", "id": path}
        elif tool_name == "delete_file":
            path = arguments.get("path")
            if not isinstance(path, str) or not path:
                raise HermesV2BoundaryError("delete_file path is invalid")
            capability = "workspace.file.delete"
            impact = "destructive"
            resource = {"kind": "workspace-file", "id": path}
        elif tool_name == "terminal":
            command = arguments.get("command")
            if not isinstance(command, str) or not command:
                raise HermesV2BoundaryError("terminal command is invalid")
            capability = "host.command.execute"
            resource = {
                "kind": "host-command",
                "id": canonical_action_digest(command),
            }
        elif tool_name == "send_message" and arguments.get("action") in {
            "react", "unreact"
        }:
            target = arguments.get("target")
            allowed_targets, event_prefix = HermesV2Controller._reaction_scope(
                platform, room_id
            )
            if target not in allowed_targets:
                raise HermesV2BoundaryError("cross-room reaction is forbidden")
            message_id = arguments.get("message_id")
            if (
                not isinstance(message_id, str)
                or not message_id
                or ":" in message_id
            ):
                raise HermesV2BoundaryError("reaction message ID is invalid")
            event_id = f"{event_prefix}{message_id}"
            event_ids = {
                event.get("id")
                for event in packet.get("events", [])
                if isinstance(event, dict)
            }
            if event_id not in event_ids:
                raise HermesV2BoundaryError("reaction target is outside the turn snapshot")
            capability = (
                "room.reaction.add"
                if arguments["action"] == "react"
                else "room.reaction.remove"
            )
            resource = {"kind": "room-message", "id": event_id}
        else:
            raise HermesV2BoundaryError(
                f"tool {tool_name!r} has no accepted Nunchi capability mapping"
            )

        operation = {
            "tool_name": tool_name,
            "arguments": copy.deepcopy(arguments),
        }
        request = {
            "kind": "authorization-request",
            "schema_version": 2,
            "action_id": f"hermes-{uuid.uuid4().hex}",
            "action_digest": canonical_action_digest(operation),
            "origin_event_id": packet["trigger_event_id"],
            "capability": capability,
            "scope": {
                "platform": platform,
                "room_id": room_id,
                "participant_id": participant_id,
                "resource": resource,
            },
            "impact": impact,
        }
        return {
            "kind": "privileged",
            "authorization_request": request,
            "operation": operation,
        }

    def _prune_pending_authorizations(self) -> None:
        with self._lock:
            snapshot = tuple(self._pending_authorizations.items())
        stale_sinks = []
        for challenge_id, pending in snapshot:
            coordinator, sink = pending
            if coordinator.pending_for_operator():
                continue
            with self._lock:
                if self._pending_authorizations.get(challenge_id) is pending:
                    self._pending_authorizations.pop(challenge_id, None)
                    stale_sinks.append(sink)
        for sink in stale_sinks:
            self._close_authorization_sink(sink)

    def pending_authorizations(self) -> tuple[dict[str, Any], ...]:
        self._prune_pending_authorizations()
        with self._lock:
            pending = tuple(self._pending_authorizations.values())
        return tuple(
            row
            for coordinator, _sink in pending
            for row in coordinator.pending_for_operator()
        )

    def complete_authenticated_approval(self, approval: Any) -> dict[str, Any]:
        if not isinstance(approval, dict):
            raise HermesV2BoundaryError("authenticated approval is invalid")
        challenge_id = approval.get("challenge_id")
        if not isinstance(challenge_id, str) or not challenge_id:
            raise HermesV2BoundaryError("authenticated approval is invalid")
        with self._lock:
            pending = self._pending_authorizations.get(challenge_id)
        if pending is None:
            raise HermesV2BoundaryError("approval challenge is unavailable")
        coordinator, sink = pending
        try:
            result = coordinator.complete_authenticated_approval(approval)
        finally:
            with self._lock:
                self._pending_authorizations.pop(challenge_id, None)
            self._close_authorization_sink(sink)
        return result

    def tool_execution(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        next_call: Callable[..., Any],
    ) -> Any:
        """Execute one explicitly classified tool under turn-bound ownership."""
        session_key = self._tool_session.get()
        if session_key is None:
            return self._invoke_tool(next_call, arguments)
        if not self.tickets.context_for_session(session_key):
            raise HermesV2BoundaryError("Nunchi turn provenance expired")
        with self._lock:
            evaluation = self._turns.get(session_key)
        if evaluation is None:
            raise HermesV2BoundaryError("Nunchi turn provenance expired")
        if not isinstance(tool_name, str) or not isinstance(arguments, dict):
            raise HermesV2BoundaryError("Hermes tool call is malformed")

        if tool_name in _NON_PRIVILEGED_TOOLS:
            self._prepare_tool_effect(session_key, evaluation)
            try:
                result = self._invoke_tool(next_call, arguments)
            except BaseException as failure:
                self.record_output_attempt(error=failure)
                raise
            self.record_output_attempt(result=result)
            return result

        if evaluation.policy_loader is None:
            raise HermesV2BoundaryError("authorization policy source is unavailable")
        action = self._privileged_action(
            evaluation, tool_name=tool_name, arguments=arguments
        )
        self._prune_pending_authorizations()
        with self._lock:
            if (
                len(self._pending_authorizations)
                + self._pending_authorization_reservations
                >= self.max_pending_authorizations
            ):
                raise HermesV2BoundaryError(
                    "pending authorization capacity is exhausted"
                )
            self._pending_authorization_reservations += 1
        capacity_reserved = True
        authorization_sink = None
        retain_authorization_sink = False
        try:
            authorization_sink = self._authorization_sink_factory(
                evaluation.policy_loader
            )
            result_box: dict[str, Any] = {}

            def execute(_operation: Any) -> None:
                # Direct proposals already call this via before_execute. Delayed
                # approvals do not, so the stored executor must enforce the same
                # immutable pre-effect receipt immediately before dispatch.
                self._prepare_tool_effect(session_key, evaluation)
                result_box["value"] = self._invoke_tool(next_call, arguments)

            capability = action["authorization_request"]["capability"]
            coordinator = PrivilegedActionCoordinator(
                PrivilegedActionGuard(evaluation.policy_loader),
                executors={capability: execute},
                audit_sink=authorization_sink,
            )
            try:
                coordinated = coordinator.propose(
                    action,
                    evaluation.participant_snapshot,
                    before_execute=lambda: self._prepare_tool_effect(
                        session_key, evaluation
                    ),
                )
            except BaseException as failure:
                self.record_output_attempt(error=failure)
                raise

            execution = coordinated["execution"]
            if execution == "executed":
                self.record_output_attempt(result=result_box.get("value"))
                return result_box.get("value")

            if execution == "pending":
                challenge = coordinated["authorization"]["approval_challenge"]
                with self._lock:
                    self._pending_authorizations[challenge["challenge_id"]] = (
                        coordinator,
                        authorization_sink,
                    )
                    self._pending_authorization_reservations -= 1
                    capacity_reserved = False
                    retain_authorization_sink = True
                raise HermesV2BoundaryError(
                    "privileged action requires authenticated approval; room prose is not approval"
                )

            raise HermesV2BoundaryError("privileged action was denied")
        finally:
            if capacity_reserved:
                with self._lock:
                    self._pending_authorization_reservations -= 1
            if authorization_sink is not None and not retain_authorization_sink:
                self._close_authorization_sink(authorization_sink)


_CONTROLLER = HermesV2Controller(
    participant_id=os.environ.get("NUNCHI_HERMES_PARTICIPANT_ID", "hermes")
)
_CONFIG_LOADER: Callable[[Any, Any], dict[str, Any]] | None = None
_CLASSIFIER_TRANSPORT: Callable[[dict[str, Any], Any], Any] | None = None
_RECEIPT_SINK_FACTORY: Callable[[Callable[[], OperatorPolicy]], Callable[[dict[str, Any]], None]] = (
    ReloadingPolicyReceiptSink
)
_SCHEDULE_REDISPATCH: Callable[[Any, Any], None] | None = None
_RECEIPT_SINKS: dict[tuple[str, str], Callable[[dict[str, Any]], None]] = {}
_RECEIPT_SINKS_LOCK = threading.RLock()


def _close_receipt_sinks() -> None:
    with _RECEIPT_SINKS_LOCK:
        sinks = tuple(_RECEIPT_SINKS.values())
        _RECEIPT_SINKS.clear()
    for sink in sinks:
        close = getattr(sink, "close", None)
        if callable(close):
            close()


def _receipt_sink_for(
    *, profile: str, policy_path: str,
    policy_loader: Callable[[], OperatorPolicy],
) -> Callable[[dict[str, Any]], None]:
    key = (profile, policy_path)
    with _RECEIPT_SINKS_LOCK:
        sink = _RECEIPT_SINKS.get(key)
        if sink is not None:
            return sink
        stale_keys = [
            stale_key for stale_key in _RECEIPT_SINKS
            if stale_key[0] == profile and stale_key != key
        ]
        stale_sinks = [_RECEIPT_SINKS.pop(stale_key) for stale_key in stale_keys]
        sink = _RECEIPT_SINK_FACTORY(policy_loader)
        _RECEIPT_SINKS[key] = sink
    for stale in stale_sinks:
        close = getattr(stale, "close", None)
        if callable(close):
            close()
    return sink


def configure(
    *,
    config_loader: Callable[[Any, Any], dict[str, Any]],
    participant_id: str,
    classifier_transport: Callable[[dict[str, Any], Any], Any] | None = None,
    receipt_sink_factory: Callable[
        [Callable[[], OperatorPolicy]], Callable[[dict[str, Any]], None]
    ] = ReloadingPolicyReceiptSink,
    schedule_redispatch: Callable[[Any, Any], None] | None = None,
) -> None:
    """Bind profile-aware host dependencies before plugin registration."""
    if not callable(config_loader):
        raise HermesV2BoundaryError("Hermes V2 config loader is invalid")
    if not isinstance(participant_id, str) or not participant_id.strip():
        raise HermesV2BoundaryError("Hermes V2 participant_id is required")
    global _CONTROLLER, _CONFIG_LOADER, _CLASSIFIER_TRANSPORT
    global _RECEIPT_SINK_FACTORY, _SCHEDULE_REDISPATCH
    _close_receipt_sinks()
    _CONTROLLER = HermesV2Controller(participant_id=participant_id.strip())
    _CONFIG_LOADER = config_loader
    _CLASSIFIER_TRANSPORT = classifier_transport
    _RECEIPT_SINK_FACTORY = receipt_sink_factory
    _SCHEDULE_REDISPATCH = schedule_redispatch


def _values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(part).strip() for part in value if str(part).strip()}
    return set()


def _config_in_scope(config: dict[str, Any], event: Any) -> bool:
    if config.get("enabled") is not True or config.get("api_version") != 2:
        return False
    if config.get("streaming") is not False:
        return False
    if config.get("_host_streaming_disabled") is not True:
        return False
    if config.get("_host_effect_runtime_supported") is not True:
        return False
    source = getattr(event, "source", None)
    platform = str(getattr(getattr(source, "platform", None), "value", ""))
    platforms = _values(config.get("platforms"))
    if "*" not in platforms and platform not in platforms:
        return False
    channels = _values(config.get("channels"))
    chat_id = getattr(source, "chat_id", None)
    parent_chat_id = getattr(source, "parent_chat_id", None)
    thread_id = getattr(source, "thread_id", None)
    if platform == "telegram":
        channel_ids = {str(chat_id)} if chat_id is not None and str(chat_id) else set()
        if chat_id is not None and thread_id is not None:
            channel_ids.add(f"telegram:chat:{chat_id}:topic:{thread_id}")
    else:
        channel_ids = {
            str(value)
            for value in (chat_id, parent_chat_id, thread_id)
            if value is not None and str(value)
        }
    return "*" in channels or bool(channels & channel_ids)


def _gateway_for_adapter(adapter: Any) -> Any:
    handler = getattr(adapter, "_message_handler", None)
    gateway = getattr(handler, "__self__", None)
    if gateway is not None:
        return gateway
    for cell in getattr(handler, "__closure__", ()) or ():
        try:
            candidate = cell.cell_contents
        except ValueError:
            continue
        if callable(getattr(candidate, "_session_key_for_source", None)):
            return candidate
    return None


def _event_in_scope(event: Any, gateway: Any) -> bool | None:
    if _CONFIG_LOADER is None or gateway is None:
        return None
    try:
        config = _CONFIG_LOADER(event, gateway)
        return isinstance(config, dict) and _config_in_scope(config, event)
    except Exception:
        return None


def _session_key_from_context(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    try:
        from gateway.session_context import get_session_env

        value = get_session_env("HERMES_SESSION_KEY")
    except Exception:
        value = None
    return str(value) if value else None


def _canonical_event_id(event: Any) -> str | None:
    source = getattr(event, "source", None)
    platform = getattr(getattr(source, "platform", None), "value", None)
    message_id = getattr(event, "message_id", None)
    if platform == "discord" and message_id:
        return f"discord:message:{message_id}"
    if platform == "telegram" and message_id and source is not None:
        return f"telegram:message:{getattr(source, 'chat_id', '')}:{message_id}"
    return None


def _control_command_name(event: Any) -> str | None:
    """Return an installed-Hermes command that bypasses an active session."""
    try:
        base_module = __import__("gateway.platforms.base", fromlist=["*"])
        base_module.coerce_plaintext_gateway_command(event)
    except Exception:
        pass
    getter = getattr(event, "get_command", None)
    command = getter() if callable(getter) else None
    if not command:
        text = str(getattr(event, "text", "") or "")
        if text.startswith("/"):
            command = text.split(maxsplit=1)[0][1:].lower().split("@", 1)[0]
    if not command:
        return None
    try:
        command_module = __import__("hermes_cli.commands", fromlist=["*"])
        return (
            str(command)
            if command_module.should_bypass_active_session(str(command))
            else None
        )
    except Exception:
        # The candidate's standalone stdlib harness intentionally has no Hermes
        # package on sys.path. In an active plugin process the import is pinned;
        # if it is unavailable, treating slash input as control is fail-closed.
        return str(command)


def _session_key_for_event(adapter: Any, event: Any) -> str | None:
    gateway = _gateway_for_adapter(adapter)
    resolver = getattr(gateway, "_session_key_for_source", None)
    source = getattr(event, "source", None)
    if not callable(resolver) or source is None:
        return None
    session_key = str(resolver(source) or "")
    return session_key or None


def _ticketed_session_for_event(adapter: Any, event: Any) -> str | None:
    session_key = _session_key_for_event(adapter, event)
    if session_key is None or not _CONTROLLER.is_ticketed(session_key):
        return None
    return session_key


async def _begin_control_output(adapter: Any, event: Any) -> str | None:
    """Barrier staging and close an admitted turn before control output."""
    if _control_command_name(event) is None:
        return None
    session_key = _session_key_for_event(adapter, event)
    if session_key is None:
        return None
    acquired, evaluation = _CONTROLLER.begin_control_output(session_key)
    if not acquired:
        return None
    try:
        if evaluation is not None:
            await asyncio.to_thread(
                _CONTROLLER.abort_participant_turn,
                session_key,
                discard_pending=True,
                expected_evaluation=evaluation,
            )
    except BaseException:
        _CONTROLLER.finish_control_output(session_key)
        raise
    return session_key


async def _run_turn_cleanup(
    function: Callable[..., Any],
    *args: Any,
    in_flight: BaseException | None = None,
    **kwargs: Any,
) -> Any:
    """Do blocking cleanup without replacing an in-flight task cancellation."""
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except BaseException:
        if isinstance(in_flight, asyncio.CancelledError):
            logger.exception(
                "Hermes V2 cleanup failed while preserving task cancellation"
            )
            return None
        raise


_DISCORD_RAW_ADAPTERS: weakref.WeakSet[Any] = weakref.WeakSet()
_DISCORD_NO_AUTO_THREAD: contextvars.ContextVar[frozenset[str]] = (
    contextvars.ContextVar("nunchi_hermes_v2_no_auto_thread", default=frozenset())
)


def _discord_message_should_be_context(
    adapter: Any, message: Any, discord_module: Any
) -> bool:
    """Mirror the pinned Discord filters only far enough to identify non-turn context."""
    client = getattr(adapter, "_client", None)
    self_user = getattr(client, "user", None)
    author = getattr(message, "author", None)
    if self_user is None or author is None:
        return False
    message_types = getattr(discord_module, "MessageType", None)
    if getattr(message, "type", None) not in {
        getattr(message_types, "default", None),
        getattr(message_types, "reply", None),
    }:
        return False
    if author == self_user or str(getattr(author, "id", "")) == str(
        getattr(self_user, "id", "")
    ):
        return True

    channel = getattr(message, "channel", None)
    guild = getattr(message, "guild", None)
    dm_cls = getattr(discord_module, "DMChannel", None)
    is_dm = guild is None or (
        isinstance(dm_cls, type) and isinstance(channel, dm_cls)
    )
    if bool(getattr(author, "bot", False)):
        allow_bots = os.getenv("DISCORD_ALLOW_BOTS", "none").lower().strip()
        self_mentioned = bool(adapter._self_is_explicitly_mentioned(message))
        if allow_bots == "none" or (
            allow_bots == "mentions" and not self_mentioned
        ):
            return False
        if adapter._discord_bots_require_inline_mention():
            raw_mention = getattr(adapter, "_self_is_raw_mentioned", None)
            if not callable(raw_mention) or not bool(raw_mention(message)):
                return False
    else:
        channel_ids = None
        if not is_dm:
            channel_ids = {str(getattr(channel, "id", ""))}
            parent = adapter._get_parent_channel_id(channel)
            if parent:
                channel_ids.add(str(parent))
        if not adapter._is_allowed_user(
            str(getattr(author, "id", "")), author,
            guild=guild, is_dm=is_dm, channel_ids=channel_ids,
        ):
            return False
    if is_dm:
        return False

    parent_id = adapter._get_parent_channel_id(channel)
    channel_keys = adapter._discord_channel_keys(message, parent_id)
    allowed_raw = os.getenv("DISCORD_ALLOWED_CHANNELS", "")
    if allowed_raw:
        allowed = {part.strip() for part in allowed_raw.split(",") if part.strip()}
        if "*" not in allowed and not (channel_keys & allowed):
            return False
    ignored = {
        part.strip()
        for part in os.getenv("DISCORD_IGNORED_CHANNELS", "").split(",")
        if part.strip()
    }
    if "*" in ignored or bool(channel_keys & ignored):
        return False

    self_mentioned = bool(adapter._self_is_explicitly_mentioned(message))
    mentions = tuple(getattr(message, "mentions", ()) or ())
    other_bots = any(
        bool(getattr(mention, "bot", False))
        and str(getattr(mention, "id", ""))
        != str(getattr(self_user, "id", ""))
        for mention in mentions
    )
    if other_bots and not self_mentioned:
        return True
    free = adapter._discord_free_response_channels()
    is_free = "*" in free or bool(channel_keys & free)
    if mentions and not self_mentioned and not other_bots:
        ignore_no_mention = os.getenv(
            "DISCORD_IGNORE_NO_MENTION", "true"
        ).lower() in {"true", "1", "yes"}
        if ignore_no_mention and not is_free:
            return True
    thread_cls = getattr(discord_module, "Thread", None)
    is_thread = isinstance(thread_cls, type) and isinstance(channel, thread_cls)
    thread_id = str(getattr(channel, "id", "")) if is_thread else None
    in_bot_thread = (
        is_thread
        and thread_id in getattr(adapter, "_threads", ())
        and not adapter._discord_thread_require_mention()
    )
    return bool(
        adapter._discord_require_mention()
        and not is_free
        and not in_bot_thread
        and not self_mentioned
    )


def _discord_context_event(adapter: Any, message: Any, discord_module: Any) -> Any:
    channel = message.channel
    guild = getattr(message, "guild", None)
    dm_cls = getattr(discord_module, "DMChannel", None)
    thread_cls = getattr(discord_module, "Thread", None)
    is_dm = guild is None or (
        isinstance(dm_cls, type) and isinstance(channel, dm_cls)
    )
    is_thread = isinstance(thread_cls, type) and isinstance(channel, thread_cls)
    parent_id = adapter._get_parent_channel_id(channel) if is_thread else None
    thread_id = str(channel.id) if is_thread else None
    self_user = getattr(getattr(adapter, "_client", None), "user", None)
    authenticated_self = self_user is not None and message.author == self_user
    native_is_bot = getattr(message.author, "bot", False)
    if type(native_is_bot) is not bool:
        raise HermesV2BoundaryError("Discord context author bot flag is invalid")
    role_authorized = False
    if not authenticated_self and not native_is_bot and bool(
        getattr(adapter, "_allowed_role_ids", set())
    ):
        allowed_user = getattr(adapter, "_is_allowed_user", None)
        if callable(allowed_user):
            channel_ids = None if is_dm else {str(channel.id)}
            if channel_ids is not None and parent_id:
                channel_ids.add(str(parent_id))
            role_authorized = allowed_user(
                str(message.author.id),
                message.author,
                guild=guild,
                is_dm=is_dm,
                channel_ids=channel_ids,
            ) is True
    source = adapter.build_source(
        chat_id=str(channel.id),
        chat_name=getattr(channel, "name", str(channel.id)),
        chat_type="dm" if is_dm else "thread" if is_thread else "group",
        user_id=str(message.author.id),
        user_name=getattr(
            message.author, "display_name", getattr(message.author, "name", "")
        ),
        thread_id=thread_id,
        is_bot=native_is_bot,
        guild_id=str(guild.id) if guild is not None else None,
        parent_chat_id=parent_id,
        message_id=str(message.id),
        role_authorized=role_authorized,
    )
    reference = getattr(message, "reference", None)
    reply_id = getattr(reference, "message_id", None) if reference else None
    return SimpleNamespace(
        text=str(getattr(message, "content", "") or ""),
        source=source,
        raw_message=message,
        message_id=str(message.id),
        reply_to_message_id=str(reply_id) if reply_id is not None else None,
        timestamp=getattr(message, "created_at", None),
        internal=False,
        _nunchi_authenticated_self=authenticated_self,
    )


def _gateway_authorizes_event(event: Any, gateway: Any) -> bool:
    authorize = getattr(gateway, "_is_user_authorized", None)
    source = getattr(event, "source", None)
    if not callable(authorize) or source is None:
        return False
    if getattr(event, "_nunchi_authenticated_self", False) is True:
        try:
            binding = _v2.resolve_binding_key(event, gateway)
            source_user_id = getattr(source, "user_id", None)
            source_is_bot = getattr(source, "is_bot", None)
        except Exception:
            return False
        if (
            isinstance(source_user_id, str)
            and source_user_id
            and source_is_bot is True
            and binding.platform == "discord"
            and binding.self_actor_id == f"discord:user:{source_user_id}"
        ):
            return True
        return False
    try:
        decision = authorize(source)
    except Exception:
        return False
    return decision is True


def _retain_transport_context(event: Any, gateway: Any) -> None:
    if _CONFIG_LOADER is None or gateway is None:
        return
    if not _gateway_authorizes_event(event, gateway):
        return
    try:
        config = _CONFIG_LOADER(event, gateway)
    except Exception:
        return
    if not isinstance(config, dict) or not _config_in_scope(config, event):
        return
    participant_id = str(config.get("participant_id", "")).strip()
    policy_path = str(config.get("policy_path", "")).strip()
    session_resolver = getattr(gateway, "_session_key_for_source", None)
    if not participant_id or not policy_path or not callable(session_resolver):
        return
    session_key = str(session_resolver(event.source) or "")
    if not session_key:
        return
    policy_source = OperatorPolicySource(policy_path)
    policy_loader = policy_source.load
    receipt_sink = _receipt_sink_for(
        profile=str(getattr(event.source, "profile", "") or ""),
        policy_path=policy_path,
        policy_loader=policy_loader,
    )
    try:
        _CONTROLLER.accept_delivery(
            event=event,
            gateway=gateway,
            session_key=session_key,
            participant_id=participant_id,
            policy_loader=policy_loader,
            receipt_sink=receipt_sink,
            classifier_transport=_CLASSIFIER_TRANSPORT,
            schedule=False,
        )
    except Exception:
        return


def install_discord_control_guard(adapter_cls: Any) -> bool:
    """Close active Nunchi turns before native Discord interaction output."""
    original_name = "_nunchi_v2_original_check_slash_authorization"
    original = adapter_cls.__dict__.get(original_name)
    if not callable(original):
        original = adapter_cls.__dict__.get("_check_slash_authorization")
        if callable(original):
            setattr(adapter_cls, original_name, original)
    if not callable(original):
        return False
    typed_original: Any = original

    async def wrapped_check(self, interaction, command_text):
        evaluate = getattr(self, "_evaluate_slash_authorization", None)
        allowed = False
        if callable(evaluate):
            decision = evaluate(interaction)
            allowed = bool(
                isinstance(decision, tuple) and decision and decision[0] is True
            )
        build_event = getattr(self, "_build_slash_event", None)
        if not callable(build_event):
            raise HermesV2BoundaryError(
                "Discord slash event projection is unavailable"
            )
        event = build_event(interaction, command_text)
        boundary = None
        if allowed:
            boundary = await _begin_control_output(self, event)
        elif _ticketed_session_for_event(self, event) is not None:
            # Do not let an unauthorized interaction emit its rejection
            # inside another participant's admitted output boundary.
            return False
        try:
            return await typed_original(self, interaction, command_text)
        finally:
            if boundary is not None:
                _CONTROLLER.finish_control_output(boundary)

    setattr(adapter_cls, "_check_slash_authorization", wrapped_check)
    return True

def install_discord_raw_observer(
    *, adapter_cls: Any, bot_cls: Any, discord_module: Any
) -> bool:
    """Retain exact raw Discord context before Hermes' response filters."""
    init_original_name = "_nunchi_v2_original_init_for_raw_observation"
    original_init = adapter_cls.__dict__.get(init_original_name)
    if not callable(original_init):
        original_init = adapter_cls.__dict__.get("__init__")
        if callable(original_init):
            setattr(adapter_cls, init_original_name, original_init)
    if not callable(original_init):
        return False
    typed_init: Any = original_init

    def wrapped_init(self, *args, **kwargs):
        typed_init(self, *args, **kwargs)
        _DISCORD_RAW_ADAPTERS.add(self)

    setattr(adapter_cls, "__init__", wrapped_init)

    free_original_name = "_nunchi_v2_original_free_response_channels"
    free_original = adapter_cls.__dict__.get(free_original_name)
    if not callable(free_original):
        free_original = adapter_cls.__dict__.get("_discord_free_response_channels")
        if callable(free_original):
            setattr(adapter_cls, free_original_name, free_original)
    if callable(free_original):
        typed_free_original: Any = free_original

        def wrapped_free_channels(self):
            return set(typed_free_original(self)) | set(
                _DISCORD_NO_AUTO_THREAD.get()
            )

        setattr(
            adapter_cls, "_discord_free_response_channels", wrapped_free_channels
        )

    handle_original_name = "_nunchi_v2_original_handle_message"
    handle_original = adapter_cls.__dict__.get(handle_original_name)
    if not callable(handle_original):
        handle_original = adapter_cls.__dict__.get("_handle_message")
        if callable(handle_original):
            setattr(adapter_cls, handle_original_name, handle_original)
    if callable(handle_original):
        typed_handle_original: Any = handle_original

        async def wrapped_handle_message(self, message, *args, **kwargs):
            if not hasattr(message, "_nunchi_v2_raw_content"):
                setattr(
                    message,
                    "_nunchi_v2_raw_content",
                    str(getattr(message, "content", "") or ""),
                )
            prior = getattr(self, "_nunchi_v2_raw_tail", None)
            if prior is not None:
                try:
                    await asyncio.shield(prior)
                except (asyncio.CancelledError, Exception):
                    pass
            gateway = _gateway_for_adapter(self)
            event = _discord_context_event(self, message, discord_module)
            channel_id = str(
                getattr(getattr(message, "channel", None), "id", "")
            )
            skip_thread = bool(
                channel_id
                and self._self_is_explicitly_mentioned(message)
                and _event_in_scope(event, gateway)
            )
            token = _DISCORD_NO_AUTO_THREAD.set(
                frozenset({channel_id}) if skip_thread else frozenset()
            )
            try:
                return await typed_handle_original(self, message, *args, **kwargs)
            finally:
                _DISCORD_NO_AUTO_THREAD.reset(token)

        setattr(adapter_cls, "_handle_message", wrapped_handle_message)

    dispatch_original_name = "_nunchi_v2_original_dispatch_for_raw_observation"
    original_dispatch = bot_cls.__dict__.get(dispatch_original_name)
    if not callable(original_dispatch):
        original_dispatch = getattr(bot_cls, "dispatch", None)
        if callable(original_dispatch):
            setattr(bot_cls, dispatch_original_name, original_dispatch)
    if not callable(original_dispatch):
        return False
    typed_dispatch: Any = original_dispatch

    def wrapped_dispatch(self, event_name, *args, **kwargs):
        if event_name == "message" and args:
            message = args[0]
            if not hasattr(message, "_nunchi_v2_raw_content"):
                setattr(
                    message,
                    "_nunchi_v2_raw_content",
                    str(getattr(message, "content", "") or ""),
                )
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                for adapter in tuple(_DISCORD_RAW_ADAPTERS):
                    if getattr(adapter, "_client", None) is not self:
                        continue
                    if not _discord_message_should_be_context(
                        adapter, message, discord_module
                    ):
                        continue
                    gateway = _gateway_for_adapter(adapter)
                    if gateway is None:
                        continue
                    event = _discord_context_event(adapter, message, discord_module)
                    if not _gateway_authorizes_event(event, gateway):
                        continue
                    previous = getattr(
                        adapter, "_nunchi_v2_raw_tail", None
                    )

                    async def retain_after_prior(
                        prior=previous,
                        retained_event=event,
                        retained_gateway=gateway,
                    ):
                        if prior is not None:
                            try:
                                await asyncio.shield(prior)
                            except (asyncio.CancelledError, Exception):
                                pass
                        await asyncio.to_thread(
                            _retain_transport_context,
                            retained_event,
                            retained_gateway,
                        )

                    task = loop.create_task(retain_after_prior())
                    setattr(adapter, "_nunchi_v2_raw_tail", task)
                    tasks = getattr(adapter, "_nunchi_v2_raw_tasks", None)
                    if tasks is None:
                        tasks = set()
                        setattr(adapter, "_nunchi_v2_raw_tasks", tasks)
                    tasks.add(task)
                    background = getattr(adapter, "_background_tasks", None)
                    if isinstance(background, set):
                        background.add(task)

                    def raw_done(done, *, owner=adapter, owned=tasks):
                        owned.discard(done)
                        owner_background = getattr(
                            owner, "_background_tasks", None
                        )
                        if isinstance(owner_background, set):
                            owner_background.discard(done)
                        if getattr(owner, "_nunchi_v2_raw_tail", None) is done:
                            setattr(owner, "_nunchi_v2_raw_tail", None)
                        try:
                            done.result()
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            logger.exception(
                                "Hermes V2 raw Discord retention failed"
                            )

                    task.add_done_callback(raw_done)
        return typed_dispatch(self, event_name, *args, **kwargs)

    setattr(bot_cls, "dispatch", wrapped_dispatch)
    return bool(
        hasattr(adapter_cls, handle_original_name)
        and hasattr(adapter_cls, free_original_name)
        and hasattr(bot_cls, dispatch_original_name)
    )


def install_telegram_exact_text(adapter_cls: Any) -> bool:
    """Bypass lossy Hermes text batching for scoped Telegram V2 events."""
    original_name = "_nunchi_v2_original_enqueue_text_event"
    original = adapter_cls.__dict__.get(original_name)
    if not callable(original):
        original = adapter_cls.__dict__.get("_enqueue_text_event")
        if callable(original):
            setattr(adapter_cls, original_name, original)
    if not callable(original):
        return False
    typed_original: Any = original

    def wrapped_enqueue(self, event):
        should_drop = getattr(self, "_should_drop_delayed_delivery", None)
        if not callable(should_drop):
            raise HermesV2BoundaryError(
                "Telegram delayed-delivery fence is unavailable"
            )
        if should_drop():
            return None
        apply_topic_recovery = getattr(self, "_apply_topic_recovery", None)
        if not callable(apply_topic_recovery):
            raise HermesV2BoundaryError(
                "Telegram topic-recovery seam is unavailable"
            )
        apply_topic_recovery(event)
        gateway = _gateway_for_adapter(self)
        scope = _event_in_scope(event, gateway)
        if scope is None:
            raise HermesV2BoundaryError(
                "Hermes V2 configuration scope is unavailable"
            )
        if scope is False:
            return typed_original(self, event)
        handle_message = getattr(self, "handle_message", None)
        if not callable(handle_message):
            raise HermesV2BoundaryError(
                "Telegram exact-event dispatch seam is unavailable"
            )
        typed_handle_message: Any = handle_message

        async def dispatch_exact_event() -> Any:
            if should_drop():
                return None
            return await typed_handle_message(event)

        task = asyncio.create_task(dispatch_exact_event())
        background = getattr(self, "_background_tasks", None)
        if isinstance(background, set):
            background.add(task)
            task.add_done_callback(background.discard)

        def exact_event_done(done):
            try:
                done.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Hermes V2 Telegram exact-event dispatch failed")

        task.add_done_callback(exact_event_done)
        return None

    setattr(adapter_cls, "_enqueue_text_event", wrapped_enqueue)
    return True


def install_host_wrappers(*, runner_cls: Any = None, adapter_cls: Any = None) -> dict[str, bool]:
    """Install the narrow version-pinned whole-turn and final-send seams."""
    if runner_cls is None:
        try:
            from gateway.run import GatewayRunner as runner_cls
        except Exception:
            runner_cls = None
    if adapter_cls is None:
        try:
            from gateway.platforms.base import BasePlatformAdapter as adapter_cls
        except Exception:
            adapter_cls = None

    installed = {"participant_turn": False, "transport": False}
    if runner_cls is not None:
        original_name = "_nunchi_v2_original_handle_message_with_agent"
        original = getattr(runner_cls, original_name, None)
        if not callable(original):
            original = getattr(runner_cls, "_handle_message_with_agent", None)
            if callable(original):
                setattr(runner_cls, original_name, original)
        if callable(original):
            runner_original: Any = original

            async def wrapped_turn(self, event, source, session_key, generation, *args, **kwargs):
                key = str(session_key)
                entry_evaluation = _CONTROLLER.evaluation_for_session(key)
                if entry_evaluation is None:
                    return await runner_original(
                        self, event, source, session_key, generation, *args, **kwargs
                    )
                try:
                    config = await asyncio.to_thread(
                        _CONFIG_LOADER, event, self
                    ) if _CONFIG_LOADER is not None else None
                    if not isinstance(config, dict) or not _config_in_scope(
                        config, event
                    ):
                        raise HermesV2BoundaryError(
                            "Hermes V2 host configuration changed after admission"
                        )
                    await asyncio.to_thread(
                        _CONTROLLER.attest_participant_turn,
                        session_key=key,
                        event=event,
                        source=source,
                        gateway=self,
                        config=config,
                    )
                except BaseException as failure:
                    await _run_turn_cleanup(
                        _CONTROLLER.abort_participant_turn,
                        key,
                        expected_evaluation=entry_evaluation,
                        in_flight=failure,
                    )
                    raise
                token = _CONTROLLER.bind_tool_session(key)
                try:
                    response = await runner_original(
                        self, event, source, session_key, generation, *args, **kwargs
                    )
                except BaseException as failure:
                    _CONTROLLER.reset_tool_session(token)
                    await _run_turn_cleanup(
                        _CONTROLLER.abort_participant_turn,
                        key,
                        invoked=True,
                        expected_evaluation=entry_evaluation,
                        in_flight=failure,
                    )
                    raise
                _CONTROLLER.reset_tool_session(token)
                action = await asyncio.to_thread(
                    _CONTROLLER.complete_participant_turn, key, response
                )
                if action is not None:
                    _CONTROLLER.set_transport_session(key)
                return response

            setattr(runner_cls, "_handle_message_with_agent", wrapped_turn)
        installed["participant_turn"] = all(
            hasattr(runner_cls, name)
            for name in (
                original_name,
                "_adapter_for_source",
                "_session_key_for_source",
                "_normalize_source_for_session_key",
                "_resolve_session_agent_runtime",
            )
        )

    if adapter_cls is not None:
        handle_original_name = "_nunchi_v2_original_handle_message_for_control"
        handle_original = adapter_cls.__dict__.get(handle_original_name)
        if not callable(handle_original):
            handle_original = adapter_cls.__dict__.get("handle_message")
            if callable(handle_original):
                setattr(adapter_cls, handle_original_name, handle_original)
        if callable(handle_original):
            typed_handle_original: Any = handle_original

            async def wrapped_handle_message(self, event, *args, **kwargs):
                boundary = await _begin_control_output(self, event)
                owner_before = (
                    getattr(self, "_session_tasks", {}).get(boundary)
                    if boundary is not None
                    else None
                )
                try:
                    result = await typed_handle_original(
                        self, event, *args, **kwargs
                    )
                except BaseException:
                    if boundary is not None:
                        _CONTROLLER.finish_control_output(boundary)
                    raise
                if boundary is None:
                    return result
                owner = getattr(self, "_session_tasks", {}).get(boundary)
                if owner is None or owner is owner_before or owner.done():
                    _CONTROLLER.finish_control_output(boundary)
                    return result

                def finish_spawned_control(_done):
                    _CONTROLLER.finish_control_output(boundary)

                try:
                    owner.add_done_callback(finish_spawned_control)
                except BaseException:
                    _CONTROLLER.finish_control_output(boundary)
                    raise
                return result

            setattr(adapter_cls, "handle_message", wrapped_handle_message)

        busy_original_name = "_nunchi_v2_original_set_busy_session_handler"
        busy_original = adapter_cls.__dict__.get(busy_original_name)
        if not callable(busy_original):
            busy_original = adapter_cls.__dict__.get("set_busy_session_handler")
            if callable(busy_original):
                setattr(adapter_cls, busy_original_name, busy_original)
        if callable(busy_original):
            typed_busy_original: Any = busy_original

            def wrapped_set_busy_handler(self, fallback_handler):
                typed_fallback_handler: Any = fallback_handler

                async def nunchi_first(event, session_key):
                    gateway = _gateway_for_adapter(self)
                    event_id = _canonical_event_id(event)
                    if (
                        gateway is not None
                        and event_id is not None
                        and _CONTROLLER.tickets.has_dispatch(
                            event_id, str(session_key)
                        )
                    ):
                        owner = getattr(self, "_session_tasks", {}).get(
                            str(session_key)
                        )
                        delayed = getattr(
                            self, "_nunchi_v2_delayed_dispatches", None
                        )
                        if delayed is None:
                            delayed = set()
                            setattr(self, "_nunchi_v2_delayed_dispatches", delayed)
                        dispatch_key = (event_id, str(session_key))
                        if dispatch_key not in delayed:
                            delayed.add(dispatch_key)

                            async def dispatch_after_owner():
                                try:
                                    if owner is not None:
                                        try:
                                            await asyncio.shield(owner)
                                        except (asyncio.CancelledError, Exception):
                                            pass
                                    handle_message: Any = getattr(
                                        self, "handle_message"
                                    )
                                    accepted = await handle_message(event)
                                    if accepted is False:
                                        await asyncio.to_thread(
                                            _CONTROLLER.abort_participant_turn,
                                            str(session_key),
                                        )
                                except BaseException:
                                    await asyncio.to_thread(
                                        _CONTROLLER.abort_participant_turn,
                                        str(session_key),
                                    )
                                    raise
                                finally:
                                    delayed.discard(dispatch_key)

                            task = asyncio.create_task(dispatch_after_owner())
                            background = getattr(self, "_background_tasks", None)
                            if isinstance(background, set):
                                background.add(task)
                                task.add_done_callback(background.discard)
                        return True
                    if gateway is not None:
                        result = on_pre_gateway_dispatch(
                            event=event, gateway=gateway
                        )
                        if isinstance(result, dict) and result.get("action") == "skip":
                            return True
                    if callable(typed_fallback_handler):
                        return bool(
                            await typed_fallback_handler(event, session_key)
                        )
                    return False

                return typed_busy_original(self, nunchi_first)

            setattr(
                adapter_cls,
                "set_busy_session_handler",
                wrapped_set_busy_handler,
            )

        process_original_name = "_nunchi_v2_original_process_message_background"
        process_original = adapter_cls.__dict__.get(process_original_name)
        if not callable(process_original):
            process_original = adapter_cls.__dict__.get(
                "_process_message_background"
            )
            if callable(process_original):
                setattr(adapter_cls, process_original_name, process_original)
        if callable(process_original):
            typed_process_original: Any = process_original

            async def wrapped_process(self, event, session_key, *args, **kwargs):
                key = str(session_key)
                gateway = _gateway_for_adapter(self)
                entry_evaluation = _CONTROLLER.evaluation_for_session(key)
                control_output = (
                    _control_command_name(event) is not None
                    and _CONTROLLER.control_output_active(key)
                )
                guard_only = (
                    entry_evaluation is None
                    and _event_in_scope(event, gateway) is True
                    and not control_output
                )
                token = _CONTROLLER.begin_output_collection(
                    key, guard_only=guard_only
                )
                try:
                    return await typed_process_original(
                        self, event, session_key, *args, **kwargs
                    )
                finally:
                    in_flight = sys.exc_info()[1]
                    completion = _CONTROLLER.finish_output_collection(
                        token, defer_receipt=True
                    )
                    if completion is not None:
                        (
                            completion_key,
                            delivery,
                            detail,
                            completion_evaluation,
                        ) = completion
                        try:
                            await _run_turn_cleanup(
                                _CONTROLLER.complete_transport,
                                completion_key,
                                delivery=delivery,
                                detail=detail,
                                expected_evaluation=completion_evaluation,
                                in_flight=in_flight,
                            )
                        finally:
                            _CONTROLLER.clear_transport_session()
                    if entry_evaluation is not None:
                        await _run_turn_cleanup(
                            _CONTROLLER.abort_participant_turn,
                            key,
                            discard_pending=True,
                            expected_evaluation=entry_evaluation,
                            in_flight=in_flight,
                        )

            setattr(adapter_cls, "_process_message_background", wrapped_process)

        send_wrapped = False
        output_method_names = (
            "send",
            "edit_message",
            "delete_message",
            "_send_with_retry",
            "send_or_update_status",
            "send_multiple_images",
            "play_tts",
            "play_in_voice_channel",
            "send_voice",
            "send_image_file",
            "send_image",
            "send_animation",
            "send_video",
            "send_document",
            "send_draft",
            "send_private_notice",
            "send_exec_approval",
            "send_slash_confirm",
            "send_clarify",
            "send_update_prompt",
            "send_model_picker",
        )
        for method_name in output_method_names:
            original_name = f"_nunchi_v2_original_{method_name.lstrip('_')}"
            original = adapter_cls.__dict__.get(original_name)
            if not callable(original):
                original = adapter_cls.__dict__.get(method_name)
                if callable(original):
                    setattr(adapter_cls, original_name, original)
            if not callable(original):
                continue
            typed_output_original: Any = original

            def make_output_wrapper(adapter_original):
                async def wrapped_output(self, *args, **kwargs):
                    _CONTROLLER.assert_terminal_output_allowed()
                    try:
                        result = await adapter_original(self, *args, **kwargs)
                    except BaseException as exc:
                        _CONTROLLER.record_output_attempt(error=exc)
                        raise
                    _CONTROLLER.record_output_attempt(result=result)
                    return result

                return wrapped_output

            setattr(
                adapter_cls,
                method_name,
                make_output_wrapper(typed_output_original),
            )
            send_wrapped = True

        for method_name in (
            "send_typing",
            "stop_typing",
            "on_processing_start",
            "on_processing_complete",
            "play_ack_in_voice",
        ):
            original_name = f"_nunchi_v2_original_{method_name}"
            original = adapter_cls.__dict__.get(original_name)
            if not callable(original):
                original = adapter_cls.__dict__.get(method_name)
                if callable(original):
                    setattr(adapter_cls, original_name, original)
            if not callable(original):
                continue
            typed_telemetry_original: Any = original

            def make_telemetry_wrapper(adapter_original):
                async def wrapped_telemetry(self, *args, **kwargs):
                    if _CONTROLLER.suppress_host_telemetry():
                        return None
                    return await adapter_original(self, *args, **kwargs)

                return wrapped_telemetry

            setattr(
                adapter_cls,
                method_name,
                make_telemetry_wrapper(typed_telemetry_original),
            )
        concrete_output_methods = tuple(
            name
            for name in output_method_names
            if callable(adapter_cls.__dict__.get(name))
        )
        installed["transport"] = bool(
            hasattr(adapter_cls, process_original_name)
            and send_wrapped
            and all(
                hasattr(
                    adapter_cls,
                    f"_nunchi_v2_original_{name.lstrip('_')}",
                )
                for name in concrete_output_methods
            )
        )
    return installed


def on_pre_gateway_dispatch(event: Any, gateway: Any = None, **_: Any):
    """Retain one native event and stage at most one ordinary Hermes turn."""
    if bool(getattr(event, "internal", False)):
        return None
    text = str(getattr(event, "text", "") or "")
    if text.lstrip().startswith("/"):
        return None
    source = getattr(event, "source", None)
    event_id = _canonical_event_id(event)
    if _CONFIG_LOADER is None or gateway is None:
        return {"action": "skip", "reason": "nunchi:v2-policy-unavailable"}
    authorize = getattr(gateway, "_is_user_authorized", None)
    if not callable(authorize):
        return {"action": "skip", "reason": "nunchi:v2-host-incompatible"}
    session_resolver = getattr(gateway, "_session_key_for_source", None)
    if not callable(session_resolver):
        return {"action": "skip", "reason": "nunchi:v2-host-incompatible"}
    session_key = str(session_resolver(source) or "")
    if not session_key:
        return {"action": "skip", "reason": "nunchi:v2-host-incompatible"}
    reserved_dispatch = bool(
        event_id and _CONTROLLER.tickets.has_dispatch(event_id, session_key)
    )

    def abort_reserved_dispatch() -> None:
        if not reserved_dispatch:
            return
        try:
            _CONTROLLER.abort_participant_turn(
                session_key, discard_pending=True
            )
        except Exception:
            logger.exception(
                "Hermes V2 reserved dispatch cleanup failed closed"
            )

    try:
        authorized = authorize(source)
    except Exception:
        abort_reserved_dispatch()
        return {"action": "skip", "reason": "nunchi:v2-authorization-error"}
    if authorized is False:
        # Preserve Hermes' own pairing/unauthorized behavior without retaining
        # untrusted text in Nunchi observation state. A reserved Nunchi
        # redispatch is different: it must be withdrawn before host dispatch.
        if reserved_dispatch:
            abort_reserved_dispatch()
            return {
                "action": "skip",
                "reason": "nunchi:v2-authorization-revoked",
            }
        return None
    if authorized is not True:
        abort_reserved_dispatch()
        return {"action": "skip", "reason": "nunchi:v2-authorization-error"}
    # A second, host-owned redispatch consumes one ticket bound to both the
    # native event and this exact Hermes profile/session.
    if reserved_dispatch:
        if _CONTROLLER.tickets.consume_dispatch(event_id, session_key) is None:
            return {"action": "skip", "reason": "nunchi:v2-ticket-expired"}
        return None
    try:
        config = _CONFIG_LOADER(event, gateway)
    except Exception:
        return {"action": "skip", "reason": "nunchi:v2-config-error"}
    if not isinstance(config, dict) or not _config_in_scope(config, event):
        return None
    participant_id = str(config.get("participant_id", "")).strip()
    policy_path = str(config.get("policy_path", "")).strip()
    if not participant_id or not policy_path:
        return {"action": "skip", "reason": "nunchi:v2-policy-unavailable"}
    policy_source = OperatorPolicySource(policy_path)
    policy_loader = policy_source.load
    try:
        receipt_sink = _receipt_sink_for(
            profile=str(getattr(source, "profile", "") or ""),
            policy_path=policy_path,
            policy_loader=policy_loader,
        )
    except Exception:
        return {"action": "skip", "reason": "nunchi:v2-receipt-error"}
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None
    delivery_cancellation = _DeliveryCancellation()
    redispatch_callback: Any = _SCHEDULE_REDISPATCH
    host_redispatch: Callable[[Any, Any], None] | None = None
    if callable(redispatch_callback):
        if running_loop is None:
            def direct_redispatch(redispatch_event, redispatch_gateway) -> None:
                with delivery_cancellation.lock:
                    if not delivery_cancellation.cancelled:
                        redispatch_callback(redispatch_event, redispatch_gateway)
            host_redispatch = direct_redispatch
        else:
            def thread_safe_redispatch(redispatch_event, redispatch_gateway):
                def redispatch_if_current() -> None:
                    with delivery_cancellation.lock:
                        if not delivery_cancellation.cancelled:
                            redispatch_callback(
                                redispatch_event, redispatch_gateway
                            )

                running_loop.call_soon_threadsafe(
                    redispatch_if_current,
                )
            host_redispatch = thread_safe_redispatch
    try:
        accepted = _CONTROLLER.accept_delivery(
            event=event,
            gateway=gateway,
            session_key=session_key,
            participant_id=participant_id,
            policy_loader=policy_loader,
            receipt_sink=receipt_sink,
            classifier_transport=_CLASSIFIER_TRANSPORT,
            redispatch=host_redispatch,
            policy_identity=policy_path,
        )
    except Exception:
        return {"action": "skip", "reason": "nunchi:v2-error"}
    if accepted.opportunity is None:
        return {"action": "skip", "reason": "nunchi:v2-observed"}

    def evaluate_and_redispatch() -> None:
        try:
            result = _CONTROLLER.evaluate_delivery(
                accepted,
                cancellation=delivery_cancellation,
            )
        except Exception:
            # evaluate_delivery owns scheduler/ticket finalization. Repeating it
            # here can complete the same exact generation twice and escape into
            # Hermes' fail-open plugin hook boundary.
            return
        if result.status == "wake" and callable(accepted.host.redispatch):
            with delivery_cancellation.lock:
                if delivery_cancellation.cancelled:
                    if _CONTROLLER.is_ticketed(session_key):
                        _CONTROLLER.abort_participant_turn(
                            session_key, discard_pending=True
                        )
                    return
                try:
                    accepted.host.redispatch(event, gateway)
                except BaseException:
                    _CONTROLLER.abort_participant_turn(session_key)

    if running_loop is None:
        evaluate_and_redispatch()
    else:
        worker_future = running_loop.run_in_executor(None, evaluate_and_redispatch)
        adapter_resolver = getattr(gateway, "_adapter_for_source", None)
        adapter = adapter_resolver(source) if callable(adapter_resolver) else None
        background = getattr(adapter, "_background_tasks", None)

        def cancel_evaluation() -> None:
            _CONTROLLER.cancel_delivery(
                accepted, delivery_cancellation, discard_pending=True
            )

        async def track_worker_lifetime() -> None:
            cancellation_requested = False
            while True:
                try:
                    await asyncio.shield(worker_future)
                    break
                except asyncio.CancelledError:
                    cancellation_requested = True
                    cancel_evaluation()
                    if worker_future.done():
                        break
                    continue
                except Exception:
                    cancel_evaluation()
                    if cancellation_requested:
                        raise asyncio.CancelledError
                    return
            if cancellation_requested:
                try:
                    worker_future.result()
                except Exception:
                    pass
                raise asyncio.CancelledError

        tracked_future = running_loop.create_task(track_worker_lifetime())
        if isinstance(background, set):
            background.add(tracked_future)

        def evaluation_done(done):
            if isinstance(background, set):
                background.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                cancel_evaluation()

        tracked_future.add_done_callback(evaluation_done)
    return {"action": "skip", "reason": "nunchi:v2-attention"}


def on_pre_llm_call(*, session_key: str | None = None, **_: Any):
    return _CONTROLLER.pre_llm_call(
        session_key=_session_key_from_context(session_key)
    )


def install_reaction_bridge(
    adapter_cls: Any,
    *,
    platform: str,
    reaction_factory: Callable[[str], Any] | None = None,
) -> bool:
    """Expose Hermes' live reaction protocol on pinned Discord/Telegram adapters."""
    if platform == "discord":

        async def fetch_message(adapter: Any, chat_id: str, message_id: str) -> Any:
            client = getattr(adapter, "_client", None)
            if client is None:
                raise HermesV2BoundaryError("Discord reaction client is unavailable")
            channel_id = int(chat_id)
            native_message_id = int(message_id)
            channel = client.get_channel(channel_id)
            if channel is None:
                channel = await client.fetch_channel(channel_id)
            return await channel.fetch_message(native_message_id)

        async def add_reaction(
            adapter: Any, *, chat_id: str, emoji: str, message_id: str
        ) -> bool:
            message = await fetch_message(adapter, chat_id, message_id)
            await message.add_reaction(emoji)
            return True

        async def remove_reaction(
            adapter: Any, *, chat_id: str, message_id: str
        ) -> bool:
            message = await fetch_message(adapter, chat_id, message_id)
            client = getattr(adapter, "_client", None)
            actor = getattr(client, "user", None)
            if actor is None:
                raise HermesV2BoundaryError("Discord reaction actor is unavailable")
            removed = False
            for reaction in tuple(getattr(message, "reactions", ())):
                if getattr(reaction, "me", False) is True:
                    await message.remove_reaction(reaction.emoji, actor)
                    removed = True
            return removed

    elif platform == "telegram":
        if reaction_factory is None:

            def default_factory(emoji: str) -> Any:
                telegram_module = __import__(
                    "telegram", fromlist=["ReactionTypeEmoji"]
                )
                return telegram_module.ReactionTypeEmoji(emoji)

            resolved_factory: Callable[[str], Any] = default_factory
        else:
            resolved_factory = reaction_factory

        def bot_for(adapter: Any) -> Any:
            app = getattr(adapter, "_app", None)
            bot = getattr(app, "bot", None) or getattr(adapter, "_bot", None)
            if bot is None or not callable(getattr(bot, "set_message_reaction", None)):
                raise HermesV2BoundaryError("Telegram reaction bot is unavailable")
            return bot

        async def add_reaction(
            adapter: Any, *, chat_id: str, emoji: str, message_id: str
        ) -> bool:
            bot = bot_for(adapter)
            await bot.set_message_reaction(
                chat_id=int(chat_id),
                message_id=int(message_id),
                reaction=[resolved_factory(emoji)],
            )
            return True

        async def remove_reaction(
            adapter: Any, *, chat_id: str, message_id: str
        ) -> bool:
            bot = bot_for(adapter)
            await bot.set_message_reaction(
                chat_id=int(chat_id), message_id=int(message_id), reaction=[]
            )
            return True

    else:
        return False

    setattr(adapter_cls, "add_reaction", add_reaction)
    setattr(adapter_cls, "remove_reaction", remove_reaction)
    return True


def on_tool_execution(
    *,
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    arguments: dict[str, Any] | None = None,
    next_call: Callable[..., Any],
    **_: Any,
):
    payload = args if isinstance(args, dict) else arguments if isinstance(arguments, dict) else {}
    downstream_started = False

    @functools.wraps(next_call)
    def tracked_next_call(*call_args, **call_kwargs):
        nonlocal downstream_started
        downstream_started = True
        return next_call(*call_args, **call_kwargs)

    try:
        return _CONTROLLER.tool_execution(
            tool_name=tool_name,
            arguments=payload,
            next_call=tracked_next_call,
        )
    except HermesV2BoundaryError as exc:
        # Hermes execution middleware is fail-open when callbacks raise before
        # next_call. Return a terminal denial value instead of throwing.
        return json.dumps(
            {
                "error": "nunchi-v2-authorization-required",
                "detail": str(exc),
            },
            sort_keys=True,
        )
    except Exception as exc:
        if downstream_started:
            raise
        # Installed Hermes retries downstream execution when middleware raises
        # before next_call. Every operational failure is therefore a terminal
        # fail-closed result at this public callback boundary.
        logger.exception("Hermes V2 tool execution failed closed")
        return json.dumps(
            {
                "error": "nunchi-v2-execution-failed",
                "detail": str(exc),
            },
            sort_keys=True,
        )


def _load_platform_module(module_name: str) -> Any:
    return __import__(module_name, fromlist=["*"])


def _load_host_classes() -> tuple[type, type]:
    gateway_module = _load_platform_module("gateway.run")
    base_module = _load_platform_module("gateway.platforms.base")
    return gateway_module.GatewayRunner, base_module.BasePlatformAdapter


def _restore_class_snapshots(snapshots: list[tuple[type, dict[str, Any]]]) -> None:
    failures = []
    for host_class, before in reversed(snapshots):
        current = dict(host_class.__dict__)
        for name in current.keys() - before.keys():
            try:
                delattr(host_class, name)
            except Exception as exc:
                failures.append((host_class.__name__, name, exc))
        for name, value in before.items():
            if host_class.__dict__.get(name) is value:
                continue
            try:
                setattr(host_class, name, value)
            except Exception as exc:
                failures.append((host_class.__name__, name, exc))
    if failures:
        detail = ", ".join(f"{owner}.{name}" for owner, name, _ in failures)
        raise HermesV2BoundaryError(
            f"Hermes V2 host-wrapper rollback failed for {detail}"
        ) from failures[0][2]


CallbackRegistrySnapshot = tuple[
    dict[str, list[Any]],
    dict[str, tuple[list[Any], tuple[Any, ...]]],
]


def _snapshot_callback_registry(registry: Any) -> CallbackRegistrySnapshot:
    if not isinstance(registry, dict):
        raise HermesV2BoundaryError("Hermes callback registry is unavailable")
    snapshot: dict[str, tuple[list[Any], tuple[Any, ...]]] = {}
    for name, callbacks in registry.items():
        if not isinstance(name, str) or not isinstance(callbacks, list):
            raise HermesV2BoundaryError(
                "Hermes callback registry shape is unsupported"
            )
        snapshot[name] = (callbacks, tuple(callbacks))
    return registry, snapshot


def _snapshot_callback_registries(
    ctx: Any,
) -> tuple[CallbackRegistrySnapshot, CallbackRegistrySnapshot]:
    manager = getattr(ctx, "_manager", None)
    if manager is None:
        raise HermesV2BoundaryError("Hermes plugin manager is unavailable")
    return (
        _snapshot_callback_registry(getattr(manager, "_hooks", None)),
        _snapshot_callback_registry(getattr(manager, "_middleware", None)),
    )


def _restore_callback_registry(snapshot: CallbackRegistrySnapshot) -> None:
    registry, before = snapshot
    for name in tuple(registry):
        if name not in before:
            del registry[name]
    for name, (original_list, callbacks) in before.items():
        original_list[:] = callbacks
        registry[name] = original_list


def _restore_callback_registries(
    snapshots: tuple[CallbackRegistrySnapshot, CallbackRegistrySnapshot],
) -> None:
    for snapshot in snapshots:
        _restore_callback_registry(snapshot)


def register(ctx: Any) -> None:
    register_hook = getattr(ctx, "register_hook", None)
    register_middleware = getattr(ctx, "register_middleware", None)
    if not callable(register_hook) or not callable(register_middleware):
        raise HermesV2BoundaryError(
            "Hermes 0.19.0 hooks and tool_execution middleware are required"
        )
    try:
        runner_cls, base_adapter_cls = _load_host_classes()
    except Exception as exc:
        raise HermesV2BoundaryError(
            "Hermes 0.19.0 host classes are unavailable"
        ) from exc
    platform_modules = []
    for module_name, class_name in (
        ("plugins.platforms.discord.adapter", "DiscordAdapter"),
        ("plugins.platforms.telegram.adapter", "TelegramAdapter"),
    ):
        try:
            module = _load_platform_module(module_name)
            platform_adapter_cls = getattr(module, class_name)
        except Exception as exc:
            raise HermesV2BoundaryError(
                f"Hermes 0.19.0 {class_name} is unavailable"
            ) from exc
        platform_modules.append((module, class_name, platform_adapter_cls))

    try:
        callback_snapshots = _snapshot_callback_registries(ctx)
    except Exception as exc:
        raise HermesV2BoundaryError(
            "Hermes 0.19.0 callback rollback surface is unavailable"
        ) from exc

    host_classes = [runner_cls, base_adapter_cls]
    for module, class_name, platform_adapter_cls in platform_modules:
        host_classes.append(platform_adapter_cls)
        if class_name == "DiscordAdapter":
            host_classes.append(module.commands.Bot)
    snapshots = []
    seen_classes = set()
    for host_class in host_classes:
        if id(host_class) in seen_classes:
            continue
        seen_classes.add(id(host_class))
        snapshots.append((host_class, dict(host_class.__dict__)))

    try:
        base_wrappers = install_host_wrappers(
            runner_cls=runner_cls,
            adapter_cls=base_adapter_cls,
        )
        if not all(base_wrappers.values()):
            raise HermesV2BoundaryError(
                "Hermes 0.19.0 participant and transport wrappers are required"
            )
        for module, class_name, platform_adapter_cls in platform_modules:
            platform_wrappers = install_host_wrappers(
                runner_cls=type("_NunchiNoRunner", (), {}),
                adapter_cls=platform_adapter_cls,
            )
            if not platform_wrappers["transport"]:
                raise HermesV2BoundaryError(
                    f"Hermes 0.19.0 {class_name} output wrappers are required"
                )
            platform = (
                "discord" if class_name == "DiscordAdapter" else "telegram"
            )
            if not install_reaction_bridge(platform_adapter_cls, platform=platform):
                raise HermesV2BoundaryError(
                    f"Hermes 0.19.0 {class_name} reaction bridge is required"
                )
            if class_name == "DiscordAdapter":
                if not install_discord_control_guard(platform_adapter_cls):
                    raise HermesV2BoundaryError(
                        "Hermes 0.19.0 Discord control guard is required"
                    )
                if not install_discord_raw_observer(
                    adapter_cls=platform_adapter_cls,
                    bot_cls=module.commands.Bot,
                    discord_module=module.discord,
                ):
                    raise HermesV2BoundaryError(
                        "Hermes 0.19.0 Discord raw observer is required"
                    )
            elif not install_telegram_exact_text(platform_adapter_cls):
                raise HermesV2BoundaryError(
                    "Hermes 0.19.0 Telegram exact-event dispatch is required"
                )
        register_hook("pre_gateway_dispatch", on_pre_gateway_dispatch)
        register_hook("pre_llm_call", on_pre_llm_call)
        register_middleware("tool_execution", on_tool_execution)
    except BaseException:
        rollback_error: BaseException | None = None
        try:
            _restore_callback_registries(callback_snapshots)
        except BaseException as exc:
            rollback_error = exc
        try:
            _restore_class_snapshots(snapshots)
        except BaseException as exc:
            if rollback_error is None:
                rollback_error = exc
        if rollback_error is not None:
            raise HermesV2BoundaryError(
                "Hermes V2 registration rollback was incomplete"
            ) from rollback_error
        raise


__all__ = [
    "HermesV2Controller",
    "configure",
    "install_discord_control_guard",
    "install_discord_raw_observer",
    "install_host_wrappers",
    "install_reaction_bridge",
    "on_pre_gateway_dispatch",
    "on_pre_llm_call",
    "on_tool_execution",
    "register",
]
