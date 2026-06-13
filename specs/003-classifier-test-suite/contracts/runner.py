#!/usr/bin/env python3
"""Verdict Test Suite runner — entry point.

See ../quickstart.md for invocation. See ../data-model.md section 3 for output schemas.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow direct script invocation (`python specs/003-classifier-test-suite/contracts/runner.py`)
# by adding the contracts/ directory to sys.path and importing siblings without package prefix.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import adapters  # noqa: E402
import invariants  # noqa: E402
import loader  # noqa: E402
import report  # noqa: E402


DEFAULT_FIXTURES_ROOT = _HERE / "fixtures"

# Structural invariants applied when the fixture declares the FR (FR-020 is
# dispatched separately on the mock/contract path).
_INVARIANT_CHECKS = (
    ("FR-005", invariants.check_pass_requires_corroborating_context),
    ("FR-007", invariants.check_context_checked_completeness),
    ("FR-008", invariants.check_confidence_not_constant),
)


def _run_one_fixture(
    fixture, adapter, *, deterministic_time: bool
) -> tuple[dict, str, str | None, str | None]:
    """Run a single fixture; return (response, status, observed_verdict, failure_detail)."""
    # Verdict-surface contract fixtures use a MockAdapter driven by mock_adapter_output.
    if fixture.surface_contract == "typed-verdict" and fixture.mock_adapter_output is not None:
        mock = adapters.MockAdapter(fixture.mock_adapter_output)
        response = mock.classify(fixture.envelope)
        ok, detail = invariants.check_verdict_surface_typed(fixture, response)
        return response, ("pass" if ok else "fail"), None, detail

    # Real adapter call.
    t0 = time.perf_counter()
    response = adapter.classify(fixture.envelope)
    duration_ms = (time.perf_counter() - t0) * 1000.0
    if deterministic_time:
        duration_ms = 0.0

    if not response.get("ok"):
        status = "error"
        return response, status, None, response.get("error_detail")

    observed = response["verdict"]
    verdict_ok = observed in fixture.expected_verdicts
    detail = None
    # Special case: FR-006 negative-control expects "NOT (ASK at 0.85)" — encode as expected list lacking ASK
    # but accepting any non-ASK or low-confidence-ASK outcome via the fr_refs marker.
    if not verdict_ok and "FR-006" in fixture.fr_refs:
        confidence = response.get("confidences", {}).get(observed, 0.0)
        if observed != "ASK" or confidence < 0.85:
            verdict_ok = True
            detail = f"non-ASK fallthrough ok (FR-006); confidence={confidence}"
    if not verdict_ok:
        detail = (
            f"observed={observed} not in expected={list(fixture.expected_verdicts)}; "
            f"failure_mode={fixture.failure_mode}"
        )
        return response, "fail", observed, detail

    # A correct verdict alone is not enough: the fixture's declared structural
    # invariants must also hold for the fixture to pass.
    for fr_ref, check in _INVARIANT_CHECKS:
        if fr_ref in fixture.fr_refs:
            ok, invariant_detail = check(fixture, response)
            if not ok:
                return response, "fail", observed, invariant_detail
    return response, "pass", observed, detail


def _print_list(fixtures: list, stream) -> None:
    stream.write(f"{len(fixtures)} fixture(s) discovered:\n")
    for f in fixtures:
        ev = "[runtime]  " if f.evidence == "runtime" else "[predicted]"
        expected = "|".join(f.expected_verdicts)
        stream.write(
            f"  {ev}  {f.source_shape:8s}  {f.id:48s}  expected={expected:14s}  "
            f"FRs={','.join(f.fr_refs)}\n"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verdict-test-suite",
        description="Verdict Test Suite — see specs/003-classifier-test-suite/quickstart.md",
    )
    parser.add_argument(
        "--format",
        choices=["text", "jsonl"],
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--source",
        choices=["all", "multica", "discord", "contract"],
        default="all",
        help="filter fixtures by source pool (FR-019)",
    )
    parser.add_argument(
        "--adapter",
        default="subprocess",
        help="adapter spec: 'subprocess' | 'in-process' | 'custom:path:Class'",
    )
    parser.add_argument(
        "--cmd",
        default=None,
        help="explicit CLI command for subprocess adapter (overrides which())",
    )
    parser.add_argument(
        "--fixtures-root",
        default=str(DEFAULT_FIXTURES_ROOT),
        help="path to fixtures directory (default: bundled)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list discovered fixtures and exit",
    )
    parser.add_argument(
        "--deterministic-time",
        action="store_true",
        help="zero duration_ms in output (used by self-tests for byte-equality checks)",
    )
    args = parser.parse_args(argv)

    fixtures_root = Path(args.fixtures_root)
    try:
        fixtures = loader.discover_fixtures(
            fixtures_root, source=None if args.source == "all" else args.source
        )
    except loader.LoaderError as exc:
        print(f"loader error: {exc}", file=sys.stderr)
        return 2

    if args.list:
        _print_list(fixtures, sys.stdout)
        return 0

    if not fixtures:
        print("no fixtures discovered", file=sys.stderr)
        return 2

    try:
        adapter = adapters.make_adapter(args.adapter, cmd=args.cmd)
    except (ImportError, ValueError) as exc:
        print(f"adapter error: {exc}", file=sys.stderr)
        return 2

    records = []
    t0 = time.perf_counter()
    for fixture in fixtures:
        per_t0 = time.perf_counter()
        response, status, observed, detail = _run_one_fixture(
            fixture, adapter, deterministic_time=args.deterministic_time
        )
        duration_ms = (time.perf_counter() - per_t0) * 1000.0
        if args.deterministic_time:
            duration_ms = 0.0
        records.append(
            report.fixture_result_record(
                fixture=fixture,
                response=response,
                status=status,
                observed_verdict=observed,
                failure_detail=detail,
                adapter_name=adapter.name,
                duration_ms=duration_ms,
            )
        )
    total_ms = (time.perf_counter() - t0) * 1000.0
    if args.deterministic_time:
        total_ms = 0.0

    summary = report.summary_record(
        records,
        duration_ms=total_ms,
        adapter_name=adapter.name,
        classifier_commit=os.environ.get("TURNAWARE_CLASSIFIER_COMMIT"),
    )
    report.render(records, summary, args.format)

    return 0 if summary["fail_count"] == 0 and summary["error_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
