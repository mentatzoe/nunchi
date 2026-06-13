"""JSONL + human-readable report rendering for the verdict test suite.

See ../data-model.md section 3 (runner result schemas).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from typing import Any, TextIO


def fixture_result_record(
    fixture,
    response: dict[str, Any],
    status: str,
    observed_verdict: str | None,
    failure_detail: str | None,
    adapter_name: str,
    duration_ms: float,
) -> dict[str, Any]:
    """Build the per-fixture JSONL line."""
    return {
        "kind": "fixture-result",
        "id": fixture.id,
        "source_shape": fixture.source_shape,
        "evidence": fixture.evidence,
        "expected_verdict": list(fixture.expected_verdicts),
        "observed_verdict": observed_verdict,
        "observed_confidence": (
            response.get("confidences", {}).get(observed_verdict)
            if observed_verdict and response.get("ok")
            else None
        ),
        "status": status,
        "failure_mode": fixture.failure_mode if status == "fail" else None,
        "failure_detail": failure_detail,
        "invariant": fixture.invariant,
        "adapter": adapter_name,
        "duration_ms": round(duration_ms, 2),
        "fr_refs": list(fixture.fr_refs),
        "sc_refs": list(fixture.sc_refs),
        "surface_contract": fixture.surface_contract,
    }


def summary_record(
    records: list[dict[str, Any]],
    duration_ms: float,
    adapter_name: str,
    classifier_commit: str | None = None,
) -> dict[str, Any]:
    """Build the final summary JSONL line."""
    pass_count = sum(1 for r in records if r["status"] == "pass")
    fail_count = sum(1 for r in records if r["status"] == "fail")
    error_count = sum(1 for r in records if r["status"] == "error")
    by_source: dict[str, Counter] = defaultdict(Counter)
    by_evidence: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        by_source[r["source_shape"]][r["status"]] += 1
        by_evidence[r["evidence"]][r["status"]] += 1
    return {
        "kind": "summary",
        "fixture_count": len(records),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "error_count": error_count,
        "by_source_shape": {k: dict(v) for k, v in by_source.items()},
        "by_evidence": {k: dict(v) for k, v in by_evidence.items()},
        "duration_ms": round(duration_ms, 2),
        "adapter": adapter_name,
        "classifier_commit": classifier_commit,
    }


def write_jsonl(records: list[dict[str, Any]], summary: dict[str, Any], stream: TextIO) -> None:
    for r in records:
        json.dump(r, stream, sort_keys=True)
        stream.write("\n")
    json.dump(summary, stream, sort_keys=True)
    stream.write("\n")


def _status_marker(status: str) -> str:
    return {"pass": " PASS", "fail": " FAIL", "error": "ERROR"}[status]


def _evidence_marker(evidence: str) -> str:
    return {"runtime": "[runtime]  ", "predicted": "[predicted]"}[evidence]


def write_human(records: list[dict[str, Any]], summary: dict[str, Any], stream: TextIO) -> None:
    """Human-readable report. FR-012: each failing line names fixture, expected,
    observed, and failure mode without requiring the reader to open the source.
    """
    stream.write(f"Verdict Test Suite — {summary['adapter']}\n")
    stream.write(f"{summary['fixture_count']} fixtures, {summary['pass_count']} pass, ")
    stream.write(f"{summary['fail_count']} fail, {summary['error_count']} error ")
    stream.write(f"in {summary['duration_ms']/1000:.2f}s\n")
    stream.write("-" * 80 + "\n")
    for r in records:
        marker = _status_marker(r["status"])
        ev = _evidence_marker(r["evidence"])
        src = r["source_shape"]
        expected = "|".join(r["expected_verdict"])
        observed = r["observed_verdict"] or "—"
        line = (
            f"  {marker}  {ev}  {src:8s}  {r['id']:48s}  "
            f"expected={expected:14s}  observed={observed}"
        )
        stream.write(line + "\n")
        if r["status"] != "pass" and r["failure_mode"]:
            stream.write(f"           ↳ failure_mode: {r['failure_mode']}\n")
        if r["status"] != "pass" and r.get("failure_detail"):
            stream.write(f"           ↳ detail:       {r['failure_detail']}\n")
    stream.write("-" * 80 + "\n")
    stream.write("By source_shape: ")
    for shape, counts in summary["by_source_shape"].items():
        stream.write(f"{shape}={counts} ")
    stream.write("\n")
    stream.write("By evidence:     ")
    for evidence, counts in summary["by_evidence"].items():
        stream.write(f"{evidence}={counts} ")
    stream.write("\n")


def render(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    output_format: str,
    stream: TextIO | None = None,
) -> None:
    out = stream or sys.stdout
    if output_format == "jsonl":
        write_jsonl(records, summary, out)
    elif output_format == "text":
        write_human(records, summary, out)
    else:
        raise ValueError(f"unknown output format: {output_format!r}")
