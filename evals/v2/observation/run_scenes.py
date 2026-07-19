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
from copy import deepcopy
from pathlib import Path
from typing import Any

from nunchi.observation import (
    ContinuationError,
    ContinuationProvider,
    ObservationInputError,
    ObservationProvider,
    estimate_tokens,
    serialized_byte_size,
    validate_context_continuation,
)
from evals.v2.observation.capabilities.reference_provider import make_reference_provider
from evals.v2.observation.compare import compare_pages, compare_requests

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
        provider_kwargs = dict(ROOM_KWARGS)
        if "event_visibility" in case:
            provider_kwargs["event_visibility"] = case["event_visibility"]
        provider = ObservationProvider(**provider_kwargs)
        for event in case["events"]:
            provider.ingest({
                "delivery_id": f"delivery:{event['id']}", "disposition": "candidate-event",
                "authorized": True, "event": event, "actors": {},
            })
        failures = []
        try:
            request = provider.snapshot(
                trigger_event_id=case["trigger_event_id"],
                max_events=case["max_events"], max_bytes=case["max_bytes"],
                max_age_seconds=case.get("max_age_seconds"),
            )
        except ObservationInputError as exc:
            if case.get("expect") != "reject":
                failures.append(f"unexpected rejection: {exc}")
            expected_detail = case.get("expect_error_contains")
            if expected_detail and expected_detail not in str(exc):
                failures.append(
                    f"rejection detail {str(exc)!r} did not contain {expected_detail!r}"
                )
            rows.append({
                "scene_id": case["scene_id"],
                "case_id": case["case_id"],
                "title": case["title"],
                "result": "PASS" if not failures else "FAIL",
                "observed": "reject",
                "detail": "; ".join(failures) or str(exc),
                "configured_max_events": case["max_events"],
                "configured_max_bytes": case["max_bytes"],
                "receipt_byte_count": None,
                "included_event_ids": [],
                "event_visibility": None,
            })
            continue
        if case.get("expect") == "reject":
            failures.append("expected hard-cap rejection but snapshot was accepted")
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
        observed_event_visibility = request["coverage"].get("event_visibility")
        if "expect_event_visibility" in case and observed_event_visibility != case["expect_event_visibility"]:
            failures.append(
                f"event_visibility {observed_event_visibility!r} != expected {case['expect_event_visibility']!r}"
            )
        if "event_visibility" not in case and "event_visibility" in request["coverage"]:
            failures.append("event_visibility present in coverage but not configured on the provider")
        receipt = provider.build_observation_receipt(request)
        if receipt["body"]["byte_count"] > case["max_bytes"]:
            failures.append(
                f"accepted event bytes {receipt['body']['byte_count']} exceed hard max_bytes={case['max_bytes']}"
            )
        result = "PASS" if not failures else "FAIL"
        row = _snapshot_row(case, request, result=result, detail="; ".join(failures))
        row["observed"] = "accept"
        row["configured_max_events"] = case["max_events"]
        row["configured_max_bytes"] = case["max_bytes"]
        row["receipt_byte_count"] = receipt["body"]["byte_count"]
        row["included_event_ids"] = included_ids
        row["event_visibility"] = observed_event_visibility
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# continuation (T019 -> evidence/v2/observation/continuation.jsonl)
# ---------------------------------------------------------------------------


def run_continuation_attacks() -> list[dict]:
    rows = []
    for case in [*_load("continuation"), *_load("resource-safety")]:
        provider_kwargs: dict[str, Any] = dict(ROOM_KWARGS)
        if "retention_max_events" in case:
            provider_kwargs["retention_max_events"] = case["retention_max_events"]
        provider = ObservationProvider(**provider_kwargs)
        for event in case["events"]:
            provider.ingest({
                "delivery_id": f"delivery:{event['id']}", "disposition": "candidate-event",
                "authorized": True, "event": event, "actors": {},
            })
        continuation = ContinuationProvider(provider)
        capability = continuation.issue(
            trigger_event_id=case["trigger_event_id"],
            originating_event_ids=case.get(
                "originating_event_ids", [case["trigger_event_id"]],
            ),
            **case["issue"],
        )
        internal_capability_before = deepcopy(
            continuation._capabilities[capability["handle_id"]]
        )
        if case.get("mutate_returned_capability"):
            capability["bound_to"]["room_id"] = "attacker-room"
            capability["can_fetch_after"] = True
            capability["max_events_per_fetch"] = 99
            if "expires_at" in capability:
                capability["expires_at"] = "2028-01-01T00:00:00Z"
        authority_unchanged = (
            continuation._capabilities[capability["handle_id"]]
            == internal_capability_before
        )
        host_context = dict(capability["bound_to"])
        host_context.update(case.get("host_context_override", {}))
        request = dict(case["fetch_request"], request_id=f"req-{case['case_id']}", handle_id=capability["handle_id"])

        def fetch_page(fetch_request: dict) -> dict:
            kwargs = {}
            if not case.get("omit_fetch_time"):
                kwargs["fetch_time"] = case.get("fetch_time", "2026-07-17T01:30:00Z")
            return continuation.fetch(
                fetch_request, host_context=host_context, **kwargs,
            )

        outcome = None
        detail = ""
        dedup_violation = False
        sequence_mismatch = False
        observed_has_more_before = None
        observed_has_more_after = None
        observed_final_has_more_after = None
        observed_truncated_by = None
        observed_page_event_ids: list[list[str]] = []
        observed_max_active_cursor_records = 0
        observed_window_object_ids: set[int] = set()
        try:
            page = fetch_page(request)
            outcome = "accept"
            observed_has_more_before = page["coverage"]["has_more_before"]
            observed_has_more_after = page["coverage"]["has_more_after"]
            observed_final_has_more_after = observed_has_more_after
            observed_truncated_by = page["coverage"]["truncated_by"]
            observed_page_event_ids.append([event["id"] for event in page["events"]])
            active_windows = continuation._cursor_windows[capability["handle_id"]]
            observed_max_active_cursor_records = max(
                observed_max_active_cursor_records, len(active_windows)
            )
            if "next_cursor" in page:
                observed_window_object_ids.add(
                    id(active_windows[page["next_cursor"]]["window_event_refs"])
                )
            if case["expect"] == "accept-then-paginate" and "next_cursor" in page:
                request2 = dict(request, request_id=f"req-{case['case_id']}-2", cursor=page["next_cursor"])
                page2 = fetch_page(request2)
                observed_page_event_ids.append([event["id"] for event in page2["events"]])
                observed_final_has_more_after = page2["coverage"]["has_more_after"]
                overlap = {e["id"] for e in page["events"]} & {e["id"] for e in page2["events"]}
                if overlap:
                    dedup_violation = True
                    detail = f"exact-event dedup violated: {overlap}"
                outcome = "accept-then-paginate"
            elif case["expect"] == "accept-then-paginate-until-exhausted":
                for event in case.get("between_page_events", []):
                    provider.ingest({
                        "delivery_id": f"delivery:{event['id']}",
                        "disposition": "candidate-event",
                        "authorized": True,
                        "event": event,
                        "actors": {},
                    })
                seen_event_ids = {event["id"] for event in page["events"]}
                seen_cursors: set[str] = set()
                current_page = page
                while "next_cursor" in current_page:
                    next_cursor = current_page["next_cursor"]
                    if next_cursor in seen_cursors:
                        sequence_mismatch = True
                        detail = f"non-progress cursor repeated: {next_cursor}"
                        break
                    seen_cursors.add(next_cursor)
                    request2 = dict(
                        request,
                        request_id=f"req-{case['case_id']}-{len(observed_page_event_ids) + 1}",
                        cursor=next_cursor,
                    )
                    current_page = fetch_page(request2)
                    observed_final_has_more_after = current_page["coverage"]["has_more_after"]
                    active_windows = continuation._cursor_windows[capability["handle_id"]]
                    observed_max_active_cursor_records = max(
                        observed_max_active_cursor_records, len(active_windows)
                    )
                    if "next_cursor" in current_page:
                        observed_window_object_ids.add(
                            id(active_windows[current_page["next_cursor"]]["window_event_refs"])
                        )
                    current_ids = [event["id"] for event in current_page["events"]]
                    overlap = seen_event_ids & set(current_ids)
                    if overlap:
                        dedup_violation = True
                        detail = f"exact-event dedup violated: {overlap}"
                        break
                    seen_event_ids.update(current_ids)
                    observed_page_event_ids.append(current_ids)
                    if len(observed_page_event_ids) > len(case["events"]) + 1:
                        sequence_mismatch = True
                        detail = "pagination did not exhaust within the finite event bound"
                        break
                outcome = "accept-then-paginate-until-exhausted"
            elif case["expect"] == "reject-on-pagination-after-retention-eviction":
                for event in case.get("between_page_events", []):
                    provider.ingest({
                        "delivery_id": f"delivery:{event['id']}",
                        "disposition": "candidate-event",
                        "authorized": True,
                        "event": event,
                        "actors": {},
                    })
                request2 = dict(
                    request,
                    request_id=f"req-{case['case_id']}-2",
                    cursor=page["next_cursor"],
                )
                try:
                    fetch_page(request2)
                    outcome = "accept-then-paginate"
                    detail = "retention-evicted cursor remainder was wrongly accepted"
                except ContinuationError as exc2:
                    outcome = "reject-on-pagination-after-retention-eviction"
                    detail = str(exc2)
            elif case["expect"] == "reject-on-second-fetch" and "next_cursor" in page:
                # H020-01 adversarial shape: the first fetch must succeed and
                # mint a cursor, then a *second* fetch replaying that cursor
                # under a different (case-supplied) direction must reject.
                request2 = dict(
                    case["second_fetch_request"],
                    request_id=f"req-{case['case_id']}-2",
                    handle_id=capability["handle_id"],
                    cursor=page["next_cursor"],
                )
                try:
                    fetch_page(request2)
                    outcome = "accept-then-paginate"  # second fetch wrongly succeeded
                    detail = "cross-direction cursor replay was wrongly accepted"
                except ContinuationError as exc2:
                    outcome = "reject-on-second-fetch"
                    detail = str(exc2)
        except ContinuationError as exc:
            outcome = "reject"
            detail = str(exc)

        coverage_mismatch = False
        if "expect_has_more_before" in case and observed_has_more_before != case["expect_has_more_before"]:
            coverage_mismatch = True
            detail = f"has_more_before {observed_has_more_before!r} != expected {case['expect_has_more_before']!r}"
        if "expect_has_more_after" in case and observed_has_more_after != case["expect_has_more_after"]:
            coverage_mismatch = True
            detail = (detail + "; " if detail else "") + (
                f"has_more_after {observed_has_more_after!r} != expected {case['expect_has_more_after']!r}"
            )
        if (
            "expect_final_has_more_after" in case
            and observed_final_has_more_after != case["expect_final_has_more_after"]
        ):
            coverage_mismatch = True
            detail = (detail + "; " if detail else "") + (
                f"final has_more_after {observed_final_has_more_after!r} != expected "
                f"{case['expect_final_has_more_after']!r}"
            )
        if "expect_truncated_by" in case and observed_truncated_by != case["expect_truncated_by"]:
            coverage_mismatch = True
            detail = (detail + "; " if detail else "") + (
                f"truncated_by {observed_truncated_by!r} != expected {case['expect_truncated_by']!r}"
            )
        if "expect_page_event_ids" in case and observed_page_event_ids != case["expect_page_event_ids"]:
            sequence_mismatch = True
            detail = (detail + "; " if detail else "") + (
                f"page event IDs {observed_page_event_ids!r} != expected {case['expect_page_event_ids']!r}"
            )
        exhausted_cursor_records = len(
            continuation._cursor_windows.get(capability["handle_id"], {})
        )
        if (
            "expect_max_active_cursor_records" in case
            and observed_max_active_cursor_records != case["expect_max_active_cursor_records"]
        ):
            sequence_mismatch = True
            detail = (detail + "; " if detail else "") + (
                f"max active cursor records {observed_max_active_cursor_records} != expected "
                f"{case['expect_max_active_cursor_records']}"
            )
        if (
            "expect_exhausted_cursor_records" in case
            and exhausted_cursor_records != case["expect_exhausted_cursor_records"]
        ):
            sequence_mismatch = True
            detail = (detail + "; " if detail else "") + (
                f"exhausted cursor records {exhausted_cursor_records} != expected "
                f"{case['expect_exhausted_cursor_records']}"
            )
        if (
            "expect_shared_window_objects" in case
            and len(observed_window_object_ids) != case["expect_shared_window_objects"]
        ):
            sequence_mismatch = True
            detail = (detail + "; " if detail else "") + (
                f"shared window object count {len(observed_window_object_ids)} != expected "
                f"{case['expect_shared_window_objects']}"
            )
        returned_capability_wire_clean = "cursors" not in capability
        retained_delivery_ids = len(provider._seen_delivery_ids)
        retained_event_generations = len(provider._event_generations)
        retained_actor_records = len(provider._actors)
        for field, observed in (
            ("expect_authority_unchanged", authority_unchanged),
            ("expect_returned_capability_wire_clean", returned_capability_wire_clean),
            ("expect_retained_delivery_ids", retained_delivery_ids),
            ("expect_retained_event_generations", retained_event_generations),
            ("expect_retained_actor_records", retained_actor_records),
        ):
            if field in case and observed != case[field]:
                sequence_mismatch = True
                detail = (detail + "; " if detail else "") + (
                    f"{field} observed {observed!r} != expected {case[field]!r}"
                )

        result = (
            "PASS"
            if outcome == case["expect"] and not dedup_violation and not coverage_mismatch and not sequence_mismatch
            else "FAIL"
        )
        row = {
            "scene_id": case["scene_id"], "case_id": case["case_id"], "title": case["title"],
            "result": result, "expected": case["expect"], "observed": outcome, "detail": detail,
            "handle_id": capability["handle_id"],
            "has_more_before": observed_has_more_before, "has_more_after": observed_has_more_after,
            "final_has_more_after": observed_final_has_more_after,
            "truncated_by": observed_truncated_by, "page_event_ids": observed_page_event_ids,
            "max_active_cursor_records": observed_max_active_cursor_records,
            "exhausted_cursor_records": exhausted_cursor_records,
            "shared_window_object_count": len(observed_window_object_ids),
            "authority_unchanged": authority_unchanged,
            "returned_capability_wire_clean": returned_capability_wire_clean,
            "retained_delivery_ids": retained_delivery_ids,
            "retained_event_generations": retained_event_generations,
            "retained_actor_records": retained_actor_records,
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
        if case.get("expect_gap_ids"):
            if request["coverage"]["has_gaps"] is not True:
                failures.append("known restart loss was not disclosed as a coverage gap")
            if request["coverage"]["has_restart_gap"] is not True:
                failures.append("known restart loss was not disclosed on has_restart_gap")
        if "expect_has_restart_gap" in case and request["coverage"]["has_restart_gap"] != case["expect_has_restart_gap"]:
            failures.append("has_restart_gap did not match expectation")
        if case.get("expect_gap_nonempty"):
            if request["coverage"]["has_gaps"] is not True:
                failures.append("expected known gap missing from normalized coverage")
            if request["coverage"]["has_restart_gap"] is not True:
                failures.append("expected restart gap missing from normalized coverage")
        result = "PASS" if not failures else "FAIL"
        row = _snapshot_row(case, request, result=result, detail="; ".join(failures))
        row["variant"] = case["variant"]
        row["restart_count"] = reference.restart_count
        row["known_gap_event_ids"] = sorted(reference.known_gap_event_ids)
        rows.append(row)
    return rows


def _apply_document_mutations(document: dict, mutations: list[dict]) -> None:
    """Apply deterministic evaluator-only mutations declared by an S13 case."""
    for mutation in mutations:
        path = mutation["path"]
        target: Any = document
        for component in path[:-1]:
            target = target[component]
        leaf = path[-1]
        if mutation.get("op") == "remove":
            if isinstance(target, list):
                target.pop(leaf)
            else:
                target.pop(leaf)
        elif isinstance(target, list):
            target[leaf] = mutation["value"]
        else:
            target[leaf] = mutation["value"]


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
        if case.get("reverse_right_events"):
            right["events"].reverse()
        _apply_document_mutations(left, case.get("left_mutations") or [])
        _apply_document_mutations(right, case.get("right_mutations") or [])
        right_capability = None
        if case.get("right_unavailable_event_ids"):
            right_capability = {"unavailable_event_ids": set(case["right_unavailable_event_ids"]), "reason": "reference-declared gap"}
        if case.get("document_kind") == "page":
            def page_from(request: dict, suffix: str) -> dict:
                return {
                    "request_id": f"page-{suffix}",
                    "handle_id": f"opaque-handle-{suffix}",
                    "room_id": request["room"]["id"],
                    "continuity_scope_id": request["room"]["continuity_scope_id"],
                    "direction": "after",
                    "anchor_event_id": case["trigger_event_id"],
                    "actors": request["actors"],
                    "events": request["events"],
                    "coverage": request["coverage"],
                    "next_cursor": f"opaque-cursor-{suffix}",
                }

            left = page_from(left, "left")
            right = page_from(right, "right")
            for page in (left, right):
                page_errors = validate_context_continuation(page)
                if page_errors:
                    raise ValueError(f"S13 synthesized invalid continuation page: {page_errors}")
            _apply_document_mutations(left, case.get("left_page_mutations") or [])
            _apply_document_mutations(right, case.get("right_page_mutations") or [])
            comparison = compare_pages(left, right, right_capability=right_capability)
        else:
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
