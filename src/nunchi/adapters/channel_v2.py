"""Generic JSON-lines V2 adapter over the shared live-room runtime."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO

from ..integrations.subprocess_participant_v2 import SubprocessParticipantV2
from ..observation import ObservationProvider
from ..policy import OperatorPolicySource
from ..receipts import ReloadingPolicyReceiptSink, transport_receipt
from ..runtime import LiveRoomRuntime
from .v2 import GenericEventSourceV2


class GenericAdapterV2Error(RuntimeError):
    pass


def _strict_json(raw: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite")),
    )


class JSONLinesActionSinkV2:
    """Deliver exact participant actions to one host stream without rejudging."""

    def __init__(
        self,
        *,
        stream: TextIO,
        receipt_sink: Callable[[dict[str, Any]], Any],
        max_request_ids: int = 4096,
    ) -> None:
        if not hasattr(stream, "write") or not callable(receipt_sink):
            raise ValueError("generic action sink dependency is invalid")
        if (
            isinstance(max_request_ids, bool)
            or not isinstance(max_request_ids, int)
            or not 1 <= max_request_ids <= 100000
        ):
            raise ValueError("generic action sink limit is invalid")
        self.stream = stream
        self.receipt_sink = receipt_sink
        self.max_request_ids = max_request_ids
        self._consumed: set[str] = set()
        self._lock = threading.RLock()

    def __call__(self, request_id: str, action: dict[str, Any]) -> None:
        if not isinstance(request_id, str) or not request_id:
            raise GenericAdapterV2Error("generic action correlation is invalid")
        with self._lock:
            if request_id in self._consumed:
                raise GenericAdapterV2Error("generic action was already delivered")
            if len(self._consumed) >= self.max_request_ids:
                raise GenericAdapterV2Error("generic action capacity is exhausted")
            self._consumed.add(request_id)
            try:
                payload = json.dumps(
                    {
                        "type": "action",
                        "schema_version": 2,
                        "request_id": request_id,
                        "action": copy.deepcopy(action),
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                self.stream.write(payload + "\n")
                self.stream.flush()
            except Exception as exc:
                try:
                    returned = self.receipt_sink(
                        transport_receipt(
                            request_id,
                            "unknown",
                            detail="generic-output-failure",
                        )
                    )
                    if returned is not None:
                        raise GenericAdapterV2Error(
                            "generic action receipt persistence is unknown"
                        )
                except Exception as receipt_exc:
                    raise GenericAdapterV2Error(
                        "generic action and receipt status are unknown"
                    ) from receipt_exc
                raise GenericAdapterV2Error("generic action delivery failed") from exc
            try:
                returned = self.receipt_sink(transport_receipt(request_id, "sent"))
            except Exception as exc:
                raise GenericAdapterV2Error(
                    "generic action receipt persistence is unknown"
                ) from exc
            if returned is not None:
                raise GenericAdapterV2Error(
                    "generic action receipt persistence is unknown"
                )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nunchi-channel",
        description=(
            "Run a host-attested JSON-lines surface through Nunchi V2. "
            "Participant command arguments must come last."
        ),
    )
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--participant-actor-id", required=True)
    parser.add_argument("--participant-name", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--continuity-scope-id", required=True)
    parser.add_argument(
        "--continuity",
        choices=("restart-safe", "session-only", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--restart-gap",
        choices=("true", "false", "unknown"),
        default="unknown",
    )
    parser.add_argument("--participant-workspace", type=Path)
    parser.add_argument("--participant-timeout", type=float, default=120)
    parser.add_argument("--participant-env", action="append", default=[])
    parser.add_argument("--silent-participant", action="store_true")
    parser.add_argument("--participant-command", nargs=argparse.REMAINDER)
    return parser


def _restart_gap(value: str) -> bool | None:
    return {"true": True, "false": False, "unknown": None}[value]


def _native_document(value: Any) -> dict[str, Any]:
    required = {"delivery_id", "authorized", "routing_room_id", "event"}
    allowed = required | {"actors"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - allowed:
        raise GenericAdapterV2Error("generic native input is invalid")
    if not isinstance(value["authorized"], bool):
        raise GenericAdapterV2Error("generic native authorization fact is invalid")
    return copy.deepcopy(value)


def build_runtime(
    arguments: argparse.Namespace,
    *,
    output: TextIO,
) -> tuple[LiveRoomRuntime, GenericEventSourceV2, ReloadingPolicyReceiptSink]:
    source = OperatorPolicySource(arguments.policy)
    policy = source.load()
    if (
        policy.attention.participant_id != arguments.participant_id
        or policy.recoverability.participant_id != arguments.participant_id
        or policy.recoverability.continuity_scope_id
        != arguments.continuity_scope_id
    ):
        raise GenericAdapterV2Error("generic adapter policy binding is invalid")
    restart_gap = _restart_gap(arguments.restart_gap)
    if policy.recoverability.eligible and (
        arguments.continuity != "restart-safe" or restart_gap is not False
    ):
        raise GenericAdapterV2Error(
            "suppression recoverability contradicts generic host capabilities"
        )
    receipt_sink = ReloadingPolicyReceiptSink(source.load)
    if arguments.silent_participant:
        if arguments.participant_command:
            raise GenericAdapterV2Error("participant mode is ambiguous")
        participant = lambda _turn: None
    else:
        if not arguments.participant_command:
            raise GenericAdapterV2Error("participant command is required")
        if arguments.participant_workspace is None:
            raise GenericAdapterV2Error("participant workspace is required")
        participant = SubprocessParticipantV2(
            command=arguments.participant_command,
            workspace=arguments.participant_workspace,
            timeout_seconds=arguments.participant_timeout,
            pass_env=tuple(arguments.participant_env),
        )
    provider = ObservationProvider(
        participant_id=arguments.participant_id,
        actor_id=arguments.participant_actor_id,
        names=[arguments.participant_name],
        role="participant",
        platform=arguments.platform,
        room_id=arguments.room_id,
        room_kind="group",
        continuity_scope_id=arguments.continuity_scope_id,
        continuity=arguments.continuity,
        has_restart_gap=restart_gap,
        event_visibility={
            "message": "live-only",
            "reaction": "live-only",
            "membership": "live-only",
        },
    )
    action_sink = JSONLinesActionSinkV2(stream=output, receipt_sink=receipt_sink)
    runtime = LiveRoomRuntime(
        observation=provider,
        policy_loader=source.load,
        receipt_sink=receipt_sink,
        participant=participant,
        correlated_action_sink=action_sink,
    )
    return runtime, GenericEventSourceV2(
        platform=arguments.platform,
        room_id=arguments.room_id,
    ), receipt_sink


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        runtime, source, receipt_sink = build_runtime(arguments, output=sys.stdout)
    except Exception:
        print("generic V2 adapter configuration is invalid", file=sys.stderr)
        return 2
    failed = False
    try:
        for line_number, raw in enumerate(sys.stdin, start=1):
            if not raw.strip():
                continue
            try:
                native = _native_document(_strict_json(raw))
                normalized = source.native_input(**native)
                results = runtime.process_delivery(normalized)
                record = {
                    "type": "delivery-result",
                    "schema_version": 2,
                    "delivery_id": normalized["delivery_id"],
                    "normalized_disposition": normalized["disposition"],
                    "runtime_results": results,
                }
            except Exception:
                failed = True
                record = {
                    "type": "delivery-error",
                    "schema_version": 2,
                    "line": line_number,
                    "error": "invalid-or-failed-native-delivery",
                }
            sys.stdout.write(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            )
            sys.stdout.flush()
    finally:
        receipt_sink.close()
    return 1 if failed else 0


__all__ = [
    "GenericAdapterV2Error",
    "JSONLinesActionSinkV2",
    "build_runtime",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
