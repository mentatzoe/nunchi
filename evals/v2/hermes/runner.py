"""Deterministic, implementation-independent replay evidence for slice 060."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence


SOURCE_MODE = "repository-fixture"
EVIDENCE_MODE = "deterministic-replay"
REQUIRED_SCENARIO_IDS = (
    "HM060-INGRESS-AUTHORIZED",
    "HM060-INGRESS-UNBOUND",
    "HM060-IDENTITY-EXACT",
    "HM060-ATTENTION-SUPPRESS",
    "HM060-WAKE-MESSAGE",
    "HM060-DIRECT-SILENCE",
    "HM060-TIMEOUT-FAIL-CLOSED",
    "HM060-ERROR-FAIL-CLOSED",
    "HM060-MALFORMED-OUTPUT",
    "HM060-WORK-STALE",
    "HM060-WORK-REPLAYED",
    "HM060-ONE-ACTIVE-NEWEST-PENDING",
    "HM060-RESTART-INVALIDATES",
    "HM060-CANCEL-INVALIDATES",
    "HM060-RECEIPT-SENT",
    "HM060-RECEIPT-FAILED",
    "HM060-RECEIPT-UNKNOWN",
    "HM060-CAPABILITY-ALLOW",
    "HM060-CAPABILITY-DENY",
    "HM060-CAPABILITY-EXPIRY",
    "HM060-CAPABILITY-REPLAY",
    "HM060-ROUTE-DISCORD",
    "HM060-ROUTE-TELEGRAM",
)
FIXED_CAPABILITIES = frozenset(
    {
        "hermes.cron.create",
        "hermes.task.delegate",
        "workspace.file.patch",
        "workspace.file.write",
    }
)
_EXPECTED_CLAIMS = {"source_behavior": False, "installed": False, "live": False}
_MANIFEST_KEYS = {
    "schema_version",
    "slice",
    "mode",
    "source_mode",
    "evidence_mode",
    "evidence_claims",
    "description",
    "required_scenario_ids",
    "fixture_files",
    "scenarios",
}
_SCENARIO_KEYS = {"id", "fixture", "category", "requirements"}
_CASE_KEYS = {"scenario_id", "kind", "description", "input", "expected"}


class ReplayRunnerError(Exception):
    """Base class for expected, machine-reportable replay failures."""


class ManifestValidationError(ReplayRunnerError):
    """The manifest or fixture bundle is incomplete or malformed."""


class ReplayFailure(ReplayRunnerError):
    """A validated fixture did not replay to its declared expected result."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _require_exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        raise ManifestValidationError(
            f"{label} keys invalid: missing={missing!r}, unexpected={unexpected!r}"
        )


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ManifestValidationError(f"{label} must be a boolean")
    return value


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestValidationError(f"{label} must be a non-empty string")
    return value


def _load_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestValidationError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestValidationError(f"{label} must contain one JSON object")
    return value


def _resolve_fixture(manifest_path: Path, reference: str) -> tuple[Path, str]:
    relative, separator, case_id = reference.partition("#")
    if not separator or not relative or not case_id:
        raise ManifestValidationError(
            f"fixture reference must be '<relative-jsonl>#<scenario-id>': {reference!r}"
        )
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ManifestValidationError(f"fixture path must be relative: {relative!r}")
    root = manifest_path.parent.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManifestValidationError(f"fixture path escapes manifest directory: {relative!r}") from exc
    return resolved, case_id


def _load_cases(path: Path) -> dict[str, dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestValidationError(f"cannot read fixture file {path}: {exc}") from exc
    cases: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise ManifestValidationError(f"blank fixture row at {path}:{line_number}")
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestValidationError(
                f"invalid JSON fixture at {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(case, dict):
            raise ManifestValidationError(f"fixture at {path}:{line_number} must be an object")
        _require_exact_keys(case, _CASE_KEYS, f"fixture at {path}:{line_number}")
        scenario_id = _require_str(case["scenario_id"], f"fixture at {path}:{line_number}.scenario_id")
        _require_str(case["kind"], f"fixture {scenario_id}.kind")
        _require_str(case["description"], f"fixture {scenario_id}.description")
        if not isinstance(case["input"], dict) or not isinstance(case["expected"], dict):
            raise ManifestValidationError(f"fixture {scenario_id} input and expected must be objects")
        if scenario_id in cases:
            raise ManifestValidationError(f"duplicate fixture scenario_id: {scenario_id}")
        case["_line"] = line_number
        cases[scenario_id] = case
    return cases


def _execute_ingress(data: Mapping[str, Any]) -> dict[str, Any]:
    authorized = _require_bool(data.get("authorized"), "ingress.authorized")
    bound = _require_bool(data.get("bound"), "ingress.bound")
    well_formed = _require_bool(data.get("well_formed"), "ingress.well_formed")
    admitted = authorized and bound and well_formed
    if not authorized:
        rejection = "unauthorized"
    elif not bound:
        rejection = "unbound-route"
    elif not well_formed:
        rejection = "malformed-event"
    else:
        rejection = "none"
    return {
        "admitted": admitted,
        "observation_count": int(admitted),
        "wake_eligible": admitted,
        "rejection": rejection,
    }


def _execute_identity(data: Mapping[str, Any]) -> dict[str, Any]:
    binding = _require_str(data.get("binding_actor_id"), "identity.binding_actor_id")
    aliases = data.get("self_aliases")
    events = data.get("events")
    if not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases):
        raise ManifestValidationError("identity.self_aliases must be an array of strings")
    if not isinstance(events, list) or not events:
        raise ManifestValidationError("identity.events must be a non-empty array")
    results = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ManifestValidationError(f"identity.events[{index}] must be an object")
        event_id = _require_str(event.get("id"), f"identity.events[{index}].id")
        actor_id = _require_str(event.get("actor_id"), f"identity.events[{index}].actor_id")
        display_name = _require_str(
            event.get("display_name"), f"identity.events[{index}].display_name"
        )
        exact_self = actor_id == binding
        results.append(
            {
                "id": event_id,
                "exact_self": exact_self,
                "alias_collision": display_name in aliases and not exact_self,
                "wake_eligible": not exact_self,
            }
        )
    return {"identity_basis": "exact-actor-id", "events": results}


def _execute_attention(data: Mapping[str, Any]) -> dict[str, Any]:
    disposition = _require_str(data.get("disposition"), "attention.disposition")
    participant_result = _require_str(
        data.get("participant_result"), "attention.participant_result"
    )
    if disposition not in {"SUPPRESS", "WAKE"}:
        raise ManifestValidationError(f"attention.disposition unsupported: {disposition}")
    if participant_result not in {"not-invoked", "message", "silence"}:
        raise ManifestValidationError(
            f"attention.participant_result unsupported: {participant_result}"
        )
    if disposition == "SUPPRESS":
        if participant_result != "not-invoked":
            raise ManifestValidationError("SUPPRESS fixture must use participant_result=not-invoked")
        participant_calls = 0
        outbound_calls = 0
        wake_source = "none"
        participant_outcome = "not-invoked"
    else:
        if participant_result == "not-invoked":
            raise ManifestValidationError("WAKE fixture must invoke the participant")
        participant_calls = 1
        outbound_calls = int(participant_result == "message")
        wake_source = "WAKE"
        participant_outcome = "sent" if participant_result == "message" else "silent"
    return {
        "attention_calls": 1,
        "effective_disposition": disposition,
        "wake_source": wake_source,
        "participant_calls": participant_calls,
        "participant_outcome": participant_outcome,
        "outbound_calls": outbound_calls,
        "send_time_classifier_calls": 0,
    }


def _execute_failure(data: Mapping[str, Any]) -> dict[str, Any]:
    stage = _require_str(data.get("stage"), "failure.stage")
    failure = _require_str(data.get("failure"), "failure.failure")
    current_snapshot = _require_bool(data.get("current_snapshot"), "failure.current_snapshot")
    if stage == "attention":
        if failure not in {"error", "malformed-output"}:
            raise ManifestValidationError(f"unsupported attention failure: {failure}")
        return {
            "attention_status": "error",
            "social_disposition": "none",
            "wake_source": "ERROR_FALLBACK" if current_snapshot else "none",
            "participant_calls": int(current_snapshot),
            "outbound_calls": 0,
            "fabricated_success": False,
        }
    if stage == "participant":
        if failure != "timeout":
            raise ManifestValidationError(f"unsupported participant failure: {failure}")
        return {
            "attention_status": "ok",
            "social_disposition": "WAKE",
            "wake_source": "WAKE",
            "participant_calls": 1,
            "outbound_calls": 0,
            "work_state": "invalidated",
            "late_result_can_dispatch": False,
        }
    raise ManifestValidationError(f"unsupported failure stage: {stage}")


def _execute_work(data: Mapping[str, Any]) -> dict[str, Any]:
    case = _require_str(data.get("case"), "work.case")
    if case == "stale":
        offered_generation = data.get("offered_generation")
        current_generation = data.get("current_generation")
        if not isinstance(offered_generation, int) or not isinstance(current_generation, int):
            raise ManifestValidationError("work generations must be integers")
        current = offered_generation == current_generation
        return {
            "current": current,
            "dispatch_calls": int(current),
            "reason": "current" if current else "stale-work",
        }
    if case == "replayed":
        consumed = _require_bool(data.get("consumed"), "work.consumed")
        return {
            "current": not consumed,
            "dispatch_calls": int(not consumed),
            "reason": "current" if not consumed else "replayed-work",
        }
    raise ManifestValidationError(f"unsupported work case: {case}")


def _execute_scheduler(data: Mapping[str, Any]) -> dict[str, Any]:
    offers = data.get("offers")
    if not isinstance(offers, list) or not offers or not all(isinstance(item, str) and item for item in offers):
        raise ManifestValidationError("scheduler.offers must be a non-empty array of strings")
    active = offers[0]
    pending: str | None = None
    dropped: list[str] = []
    max_active = 1
    for event_id in offers[1:]:
        if pending is not None:
            dropped.append(pending)
        pending = event_id
    processed = [active]
    if pending is not None:
        active = pending
        pending = None
        processed.append(active)
    return {
        "max_active": max_active,
        "processed": processed,
        "dropped_pending": dropped,
        "pending": pending,
    }


def _execute_lifecycle(data: Mapping[str, Any]) -> dict[str, Any]:
    action = _require_str(data.get("action"), "lifecycle.action")
    had_active = _require_bool(data.get("had_active"), "lifecycle.had_active")
    had_pending = _require_bool(data.get("had_pending"), "lifecycle.had_pending")
    if action not in {"restart", "cancel"}:
        raise ManifestValidationError(f"unsupported lifecycle action: {action}")
    return {
        "action": action,
        "active_invalidated": had_active,
        "pending_discarded": had_pending,
        "remaining_active": 0,
        "remaining_pending": 0,
        "outbound_calls": 0,
    }


def _execute_transport(data: Mapping[str, Any]) -> dict[str, Any]:
    native_result = _require_str(data.get("native_result"), "transport.native_result")
    exact_attestation = _require_bool(
        data.get("exact_attestation"), "transport.exact_attestation"
    )
    if native_result == "positive-ack" and exact_attestation:
        delivery = "sent"
    elif native_result == "negative-ack":
        delivery = "failed"
    elif native_result in {"timeout", "exception", "malformed-ack", "positive-ack"}:
        delivery = "unknown"
    else:
        raise ManifestValidationError(f"unsupported transport result: {native_result}")
    return {
        "participant_host_outcome_before_transport": "unknown",
        "transport_calls": 1,
        "delivery": delivery,
        "fabricated_success": False,
        "receipts": [
            {
                "stage": "participant-host",
                "writer": "participant-host",
                "outcome": "unknown",
            },
            {"stage": "transport", "writer": "transport", "delivery": delivery},
        ],
    }


def _execute_capability(data: Mapping[str, Any]) -> dict[str, Any]:
    capability = _require_str(data.get("capability"), "capability.capability")
    policy_allows = _require_bool(data.get("policy_allows"), "capability.policy_allows")
    binding_matches = _require_bool(data.get("binding_matches"), "capability.binding_matches")
    consumed = _require_bool(data.get("consumed"), "capability.consumed")
    now = data.get("now")
    expires_at = data.get("expires_at")
    if not isinstance(now, int) or not isinstance(expires_at, int):
        raise ManifestValidationError("capability.now and expires_at must be integers")
    if capability not in FIXED_CAPABILITIES:
        reason = "capability-not-fixed"
    elif consumed:
        reason = "replay-denied"
    elif now >= expires_at:
        reason = "expired"
    elif not policy_allows:
        reason = "policy-denied"
    elif not binding_matches:
        reason = "binding-mismatch"
    else:
        reason = "allowed"
    dispatch = reason == "allowed"
    return {
        "decision": "ALLOW" if dispatch else "DENY",
        "reason": reason,
        "effect_dispatch_calls": int(dispatch),
        "grant_consumed": dispatch or consumed,
    }


def _execute_route(data: Mapping[str, Any]) -> dict[str, Any]:
    platform = _require_str(data.get("platform"), "route.platform")
    if platform not in {"discord", "telegram"}:
        raise ManifestValidationError(f"unsupported route platform: {platform}")
    room_id = _require_str(data.get("room_id"), "route.room_id")
    actor_id = _require_str(data.get("actor_id"), "route.actor_id")
    self_actor_id = _require_str(data.get("self_actor_id"), "route.self_actor_id")
    message_id = _require_str(data.get("message_id"), "route.message_id")
    mentions_available = _require_bool(
        data.get("mentions_available"), "route.mentions_available"
    )
    reactions_available = _require_bool(
        data.get("reactions_available"), "route.reactions_available"
    )
    provided_mentions = data.get("provided_mention_actor_ids")
    if not isinstance(provided_mentions, list) or not all(
        isinstance(item, str) and item for item in provided_mentions
    ):
        raise ManifestValidationError("route.provided_mention_actor_ids must be strings")
    mentioned_actor_ids = (
        [f"{platform}:actor:{item}" for item in provided_mentions]
        if mentions_available
        else []
    )
    unavailable = []
    if not mentions_available:
        unavailable.append("mentions")
    if not reactions_available:
        unavailable.append("reactions")
    actors = sorted({f"{platform}:actor:{actor_id}", f"{platform}:actor:{self_actor_id}"})
    return {
        "route_key": [platform, room_id],
        "continuity_scope_id": f"{platform}:room:{room_id}",
        "event": {
            "id": f"{platform}:message:{message_id}",
            "author_id": f"{platform}:actor:{actor_id}",
            "mentioned_actor_ids": mentioned_actor_ids,
            "mentions_room": False,
        },
        "actors": actors,
        "coverage_unavailable": unavailable,
        "inferred_roster": False,
    }


_EXECUTORS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "ingress": _execute_ingress,
    "identity": _execute_identity,
    "attention": _execute_attention,
    "failure": _execute_failure,
    "work": _execute_work,
    "scheduler": _execute_scheduler,
    "lifecycle": _execute_lifecycle,
    "transport": _execute_transport,
    "capability": _execute_capability,
    "route": _execute_route,
}


def _validate_manifest(
    manifest: dict[str, Any], manifest_path: Path, require_complete: bool
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    _require_exact_keys(manifest, _MANIFEST_KEYS, "manifest")
    if manifest["schema_version"] != 1:
        raise ManifestValidationError("manifest.schema_version must be exactly 1")
    if manifest["slice"] != "060-v2-hermes":
        raise ManifestValidationError("manifest.slice must be exactly '060-v2-hermes'")
    if manifest["mode"] != "replay":
        raise ManifestValidationError("manifest.mode must be exactly 'replay'")
    if manifest["source_mode"] != SOURCE_MODE:
        raise ManifestValidationError(
            f"manifest.source_mode must be exactly {SOURCE_MODE!r}; fixtures are not installed evidence"
        )
    if manifest["evidence_mode"] != EVIDENCE_MODE:
        raise ManifestValidationError(
            f"manifest.evidence_mode must be exactly {EVIDENCE_MODE!r}; fixtures are not live evidence"
        )
    if manifest["evidence_claims"] != _EXPECTED_CLAIMS:
        raise ManifestValidationError(
            "manifest.evidence_claims must deny source-behavior, installed, and live proof"
        )
    _require_str(manifest["description"], "manifest.description")

    required = manifest["required_scenario_ids"]
    if not isinstance(required, list) or not all(isinstance(item, str) and item for item in required):
        raise ManifestValidationError("manifest.required_scenario_ids must be an array of strings")
    if len(required) != len(set(required)):
        raise ManifestValidationError("manifest.required_scenario_ids contains duplicates")
    if require_complete:
        missing_from_required = sorted(set(REQUIRED_SCENARIO_IDS) - set(required))
        unexpected_required = sorted(set(required) - set(REQUIRED_SCENARIO_IDS))
        if missing_from_required or unexpected_required or required != list(REQUIRED_SCENARIO_IDS):
            raise ManifestValidationError(
                "manifest.required_scenario_ids is not the complete ordered slice-060 inventory: "
                f"missing={missing_from_required!r}, unexpected={unexpected_required!r}"
            )

    fixture_files = manifest["fixture_files"]
    if not isinstance(fixture_files, list) or not fixture_files:
        raise ManifestValidationError("manifest.fixture_files must be a non-empty array")
    resolved_files: dict[str, Path] = {}
    for item in fixture_files:
        relative = _require_str(item, "manifest.fixture_files item")
        path, fragment = _resolve_fixture(manifest_path, f"{relative}#inventory")
        if fragment != "inventory":  # Defensive: helper always returns the supplied fragment.
            raise AssertionError("unreachable")
        if relative in resolved_files:
            raise ManifestValidationError(f"duplicate fixture file: {relative}")
        resolved_files[relative] = path

    scenarios = manifest["scenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ManifestValidationError("manifest.scenarios must be a non-empty array")
    scenario_ids: list[str] = []
    scenario_records: list[dict[str, Any]] = []
    used_case_ids: set[str] = set()
    all_cases: dict[str, dict[str, Any]] = {}
    per_file_cases: dict[Path, dict[str, dict[str, Any]]] = {}
    for path in resolved_files.values():
        per_file_cases[path] = _load_cases(path)
        overlap = set(all_cases) & set(per_file_cases[path])
        if overlap:
            raise ManifestValidationError(f"scenario IDs duplicated across fixture files: {sorted(overlap)!r}")
        all_cases.update(per_file_cases[path])

    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ManifestValidationError(f"manifest.scenarios[{index}] must be an object")
        _require_exact_keys(scenario, _SCENARIO_KEYS, f"manifest.scenarios[{index}]")
        scenario_id = _require_str(scenario["id"], f"manifest.scenarios[{index}].id")
        category = _require_str(scenario["category"], f"manifest.scenarios[{index}].category")
        del category
        requirements = scenario["requirements"]
        if not isinstance(requirements, list) or not requirements or not all(
            isinstance(item, str) and item for item in requirements
        ):
            raise ManifestValidationError(
                f"manifest.scenarios[{index}].requirements must be a non-empty string array"
            )
        fixture_reference = _require_str(
            scenario["fixture"], f"manifest.scenarios[{index}].fixture"
        )
        fixture_path, case_id = _resolve_fixture(manifest_path, fixture_reference)
        if case_id != scenario_id:
            raise ManifestValidationError(
                f"scenario {scenario_id} fixture fragment must equal its scenario ID"
            )
        if fixture_path not in per_file_cases:
            raise ManifestValidationError(
                f"scenario {scenario_id} references undeclared fixture file {fixture_path.name!r}"
            )
        if case_id not in per_file_cases[fixture_path]:
            raise ManifestValidationError(
                f"scenario {scenario_id} fixture is absent from {fixture_path.name}"
            )
        scenario_ids.append(scenario_id)
        used_case_ids.add(case_id)
        scenario_records.append(
            {
                "id": scenario_id,
                "fixture": fixture_reference,
                "case": per_file_cases[fixture_path][case_id],
            }
        )

    if len(scenario_ids) != len(set(scenario_ids)):
        raise ManifestValidationError("manifest.scenarios contains duplicate IDs")
    missing_declared = sorted(set(required) - set(scenario_ids))
    undeclared = sorted(set(scenario_ids) - set(required))
    if missing_declared or undeclared:
        raise ManifestValidationError(
            f"manifest scenario inventory mismatch: missing={missing_declared!r}, unexpected={undeclared!r}"
        )
    if require_complete:
        missing = sorted(set(REQUIRED_SCENARIO_IDS) - set(scenario_ids))
        if missing:
            raise ManifestValidationError(f"required slice-060 scenario IDs absent: {missing!r}")
        if scenario_ids != list(REQUIRED_SCENARIO_IDS):
            raise ManifestValidationError(
                "manifest.scenarios must preserve the required deterministic order"
            )
    extra_cases = sorted(set(all_cases) - used_case_ids)
    if extra_cases:
        raise ManifestValidationError(f"unmanifested fixture scenarios present: {extra_cases!r}")
    return scenario_records, all_cases


def run_replay(manifest_path: str | Path, *, require_complete: bool = False) -> dict[str, Any]:
    path = Path(manifest_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ManifestValidationError(f"cannot read manifest {path}: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    manifest = _load_json_object(raw, f"manifest {path}")
    scenarios, _ = _validate_manifest(manifest, path, require_complete)

    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for scenario in scenarios:
        case = scenario["case"]
        executor = _EXECUTORS.get(case["kind"])
        if executor is None:
            raise ManifestValidationError(
                f"fixture {case['scenario_id']} has unsupported kind {case['kind']!r}"
            )
        actual = executor(case["input"])
        passed = actual == case["expected"]
        if not passed:
            failures.append(
                f"{case['scenario_id']}: expected={_canonical_json(case['expected'])} "
                f"actual={_canonical_json(actual)}"
            )
        results.append(
            {
                "scenario_id": case["scenario_id"],
                "status": "pass" if passed else "fail",
                "fixture_source": f"{scenario['fixture']}@line:{case['_line']}",
                "actual": actual,
            }
        )
    if failures:
        raise ReplayFailure("replay mismatch: " + "; ".join(failures))

    return {
        "schema_version": 1,
        "slice": manifest["slice"],
        "mode": "replay",
        "source_mode": SOURCE_MODE,
        "evidence_mode": EVIDENCE_MODE,
        "evidence_claims": dict(_EXPECTED_CLAIMS),
        "manifest": {
            "path": str(path),
            "digest_algorithm": "sha256",
            "sha256": digest,
            "byte_count": len(raw),
        },
        "summary": {
            "required": len(REQUIRED_SCENARIO_IDS),
            "declared": len(scenarios),
            "executed": len(results),
            "passed": len(results),
            "failed": 0,
        },
        "results": results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("replay",), required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_replay(args.manifest, require_complete=args.require_complete)
    except ReplayRunnerError as exc:
        manifest_record: dict[str, Any] = {"path": str(args.manifest)}
        try:
            raw = args.manifest.read_bytes()
        except OSError:
            pass
        else:
            manifest_record.update(
                {
                    "digest_algorithm": "sha256",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "byte_count": len(raw),
                }
            )
        error = {
            "schema_version": 1,
            "status": "error",
            "mode": "replay",
            "source_mode": SOURCE_MODE,
            "evidence_mode": EVIDENCE_MODE,
            "evidence_claims": dict(_EXPECTED_CLAIMS),
            "manifest": manifest_record,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        print(_canonical_json(error), file=sys.stderr)
        return 2
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
