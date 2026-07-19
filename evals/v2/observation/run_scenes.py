"""Runner for the four eval case corpora (T012, T018, T019, T024, T025).

Replays each ``cases.jsonl`` scene through :class:`ObservationProvider` /
:class:`ContinuationProvider` / the reference variants, asserts every
declared expectation, and returns one evidence row per case (mandatory
``scene_id``, serialized sizes, and the separately labelled
``utf8-bytes-ceil-div4@1`` token-size proxy — never written onto any
receipt body).

Invoke as a script to regenerate the aggregate evidence files:

    PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nunchi.observation import (
    ContinuationError,
    ContinuationProvider,
    ObservationProvider,
    estimate_tokens,
    serialized_byte_size,
)
from evals.v2.observation.capabilities.reference_provider import make_reference_provider
from evals.v2.observation.compare import compare_requests

REPO_ROOT = Path(__file__).resolve().parents[3]
EVALS_DIR = REPO_ROOT / "evals" / "v2" / "observation"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "v2" / "observation"

ROOM_KWARGS = dict(
    participant_id="vigil",
    actor_id="discord:9001",
    platform="discord",
    room_id="42",
    continuity_scope_id="discord:room:42#2026-07",
)


def _load(name: str) -> list[dict[str, Any]]:
    path = EVALS_DIR / name / "cases.jsonl"
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _snapshot_row(case: dict, request: dict, *, result: str, detail: str = "") -> dict:
    row = {
        "scene_id": case["scene_id"],
        "case_id": case["case_id"],
        "title": case["title"],
        "result": result,
        "request_id": request["request_id"],
        "event_count": len(request["events"]),
        "serialized_bytes": serialized_byte_size(request),
    }
    row["token_proxy"] = estimate_tokens(row["serialized_bytes"])
    if detail:
        row["detail"] = detail
    return row


# ---------------------------------------------------------------------------
# identity-and-hygiene (T012 -> evidence/v2/observation/identity-and-hygiene.jsonl)
# ---------------------------------------------------------------------------


def run_identity_and_hygiene() -> list[dict]:
    rows = []
    for case in _load("identity-and-hygiene"):
        provider = ObservationProvider(**ROOM_KWARGS)
        failures = []
        for step in case["steps"]:
            expect = step.pop("expect_disposition")
            outcome = provider.ingest(step)
            if outcome != expect:
                failures.append(f"expected disposition {expect!r}, got {outcome!r}")
        request = provider.snapshot(trigger_event_id=case["trigger_event_id"], max_events=50, max_bytes=65536)
        receipt = provider.build_observation_receipt(request)
        result = "PASS" if not failures else "FAIL"
        row = _snapshot_row(case, request, result=result, detail="; ".join(failures))
        row["receipt_stage"] = receipt["stage"]
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# budgets (T018 -> evidence/v2/observation/budget-sweep.jsonl)
# ---------------------------------------------------------------------------


def run_budget_sweep() -> list[dict]:
    rows = []
    for case in _load("budgets"):
        provider = ObservationProvider(**ROOM_KWARGS)
        for event in case["events"]:
            provider.ingest({
                "delivery_id": f"delivery:{event['id']}", "disposition": "candidate-event",
                "authorized": True, "event": event, "actors": {},
            })
        request = provider.snapshot(
            trigger_event_id=case["trigger_event_id"],
            max_events=case["max_events"], max_bytes=case["max_bytes"],
            max_age_seconds=case.get("max_age_seconds"),
        )
        failures = []
        truncated_by = set(request["coverage"]["truncated_by"])
        if "expect_truncated_by" in case and truncated_by != set(case["expect_truncated_by"]):
            failures.append(f"truncated_by {sorted(truncated_by)} != expected {case['expect_truncated_by']}")
        included_ids = [event["id"] for event in request["events"]]
        if "expect_included_event_ids" in case and set(included_ids) != set(case["expect_included_event_ids"]):
            failures.append(f"included {included_ids} != expected {case['expect_included_event_ids']}")
        if "expect_excluded_event_ids" in case:
            overlap = set(included_ids) & set(case["expect_excluded_event_ids"])
            if overlap:
                failures.append(f"expected-excluded ids present: {overlap}")
        receipt = provider.build_observation_receipt(request)
        result = "PASS" if not failures else "FAIL"
        row = _snapshot_row(case, request, result=result, detail="; ".join(failures))
        row["configured_max_events"] = case["max_events"]
        row["configured_max_bytes"] = case["max_bytes"]
        row["receipt_byte_count"] = receipt["body"]["byte_count"]
        row["included_event_ids"] = included_ids
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# continuation (T019 -> evidence/v2/observation/continuation.jsonl)
# ---------------------------------------------------------------------------


def run_continuation_attacks() -> list[dict]:
    rows = []
    for case in _load("continuation"):
        provider = ObservationProvider(**ROOM_KWARGS)
        for event in case["events"]:
            provider.ingest({
                "delivery_id": f"delivery:{event['id']}", "disposition": "candidate-event",
                "authorized": True, "event": event, "actors": {},
            })
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(trigger_event_id=case["trigger_event_id"], **case["issue"])
        host_context = dict(capability["bound_to"])
        host_context.update(case.get("host_context_override", {}))
        request = dict(case["fetch_request"], request_id=f"req-{case['case_id']}", handle_id=capability["handle_id"])

        outcome = None
        detail = ""
        dedup_violation = False
        try:
            page = continuation.fetch(request, host_context=host_context, fetch_time=case.get("fetch_time", "2026-07-17T01:30:00Z"))
            outcome = "accept"
            if case["expect"] == "accept-then-paginate" and "next_cursor" in page:
                request2 = dict(request, request_id=f"req-{case['case_id']}-2", cursor=page["next_cursor"])
                page2 = continuation.fetch(request2, host_context=host_context, fetch_time=case.get("fetch_time", "2026-07-17T01:30:00Z"))
                overlap = {e["id"] for e in page["events"]} & {e["id"] for e in page2["events"]}
                if overlap:
                    dedup_violation = True
                    detail = f"exact-event dedup violated: {overlap}"
                outcome = "accept-then-paginate"
        except ContinuationError as exc:
            outcome = "reject"
            detail = str(exc)

        result = "PASS" if outcome == case["expect"] and not dedup_violation else "FAIL"
        row = {
            "scene_id": case["scene_id"], "case_id": case["case_id"], "title": case["title"],
            "result": result, "expected": case["expect"], "observed": outcome, "detail": detail,
            "handle_id": capability["handle_id"],
        }
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# capabilities (T024 -> s05-recoverability.jsonl, T025 -> s13-equivalence.jsonl)
# ---------------------------------------------------------------------------


def run_recoverability() -> list[dict]:
    rows = []
    for case in _load("capabilities"):
        if case["scene_id"] != "S05":
            continue
        reference = make_reference_provider(case["variant"], **ROOM_KWARGS)
        for event in case["events_before_restart"]:
            reference.ingest({
                "delivery_id": f"delivery:{event['id']}", "disposition": "candidate-event",
                "authorized": True, "event": event, "actors": {},
            })
        reference.simulate_restart()
        for event in case["events_after_restart"]:
            reference.ingest({
                "delivery_id": f"delivery:{event['id']}", "disposition": "candidate-event",
                "authorized": True, "event": event, "actors": {},
            })
        request = reference.snapshot(trigger_event_id=case["trigger_event_id"], max_events=50, max_bytes=65536)
        failures = []
        if request["coverage"]["continuity"] != case["expect_continuity"]:
            failures.append(f"continuity {request['coverage']['continuity']!r} != {case['expect_continuity']!r}")
        included_ids = {event["id"] for event in request["events"]}
        for retained in case.get("expect_retained_ids", []):
            if retained not in included_ids:
                failures.append(f"expected retained id {retained!r} missing")
        for gapped in case.get("expect_gap_ids", []):
            if gapped not in reference.known_gap_event_ids:
                failures.append(f"expected known-gap id {gapped!r} not reported as a gap")
        if "expect_has_restart_gap" in case and request["coverage"]["has_restart_gap"] != case["expect_has_restart_gap"]:
            failures.append("has_restart_gap did not match expectation")
        if case.get("expect_gap_nonempty") and not reference.known_gap_event_ids:
            failures.append("expected a non-empty known gap")
        result = "PASS" if not failures else "FAIL"
        row = _snapshot_row(case, request, result=result, detail="; ".join(failures))
        row["variant"] = case["variant"]
        row["restart_count"] = reference.restart_count
        row["known_gap_event_ids"] = sorted(reference.known_gap_event_ids)
        rows.append(row)
    return rows


def run_equivalence() -> list[dict]:
    rows = []
    for case in _load("capabilities"):
        if case["scene_id"] != "S13":
            continue
        def build(events):
            provider = ObservationProvider(**ROOM_KWARGS)
            for event in events:
                provider.ingest({
                    "delivery_id": f"delivery:{event['id']}", "disposition": "candidate-event",
                    "authorized": True, "event": event, "actors": {},
                })
            return provider.snapshot(trigger_event_id=case["trigger_event_id"], max_events=50, max_bytes=65536)

        left = build(case["left_events"])
        right = build(case["right_events"])
        right_capability = None
        if case.get("right_unavailable_event_ids"):
            right_capability = {"unavailable_event_ids": set(case["right_unavailable_event_ids"]), "reason": "reference-declared gap"}
        comparison = compare_requests(left, right, right_capability=right_capability)
        result = "PASS" if comparison["equivalent"] == case["expect_equivalent"] else "FAIL"
        rows.append({
            "scene_id": case["scene_id"], "case_id": case["case_id"], "title": case["title"],
            "result": result, "equivalent": comparison["equivalent"],
            "unexplained": comparison["unexplained"], "explained": comparison["explained"],
        })
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    suites = {
        "identity-and-hygiene.jsonl": run_identity_and_hygiene(),
        "budget-sweep.jsonl": run_budget_sweep(),
        "continuation.jsonl": run_continuation_attacks(),
        "s05-recoverability.jsonl": run_recoverability(),
        "s13-equivalence.jsonl": run_equivalence(),
    }
    total_fail = 0
    for filename, rows in suites.items():
        write_jsonl(EVIDENCE_DIR / filename, rows)
        failures = [row for row in rows if row["result"] == "FAIL"]
        total_fail += len(failures)
        print(f"{filename}: {len(rows)} rows, {len(failures)} FAIL")
    if total_fail:
        raise SystemExit(f"{total_fail} eval case(s) failed")


if __name__ == "__main__":
    main()
