"""Structural-invariant helpers for FR-005 / FR-007 / FR-008 / FR-020.

Each helper takes the fixture + the adapter response and returns
(passed: bool, observed_detail: str).
"""

from __future__ import annotations

from typing import Any


def check_pass_requires_corroborating_context(
    fixture, response: dict[str, Any]
) -> tuple[bool, str]:
    """FR-005: a PASS verdict from a trigger with empty context is a violation."""
    if not response.get("ok"):
        return False, f"adapter error: {response.get('error_detail', 'unknown')}"
    verdict = response["verdict"]
    if verdict == "PASS" and not fixture.envelope.get("context"):
        return False, "PASS produced from trigger alone with empty context (FR-005)"
    return True, f"verdict={verdict}; context_size={len(fixture.envelope.get('context', []))}"


def check_context_checked_completeness(
    fixture, response: dict[str, Any]
) -> tuple[bool, str]:
    """FR-007: audit field MUST reflect every consulted item, not just the first match.

    Heuristic check: if the envelope has N context items and N > 1, the
    `context_checked` field must contain at least 2 entries (one for trigger
    + at least one context item). A response that only contains the trigger
    in `context_checked` despite multiple context items violates the invariant.
    """
    if not response.get("ok"):
        return False, f"adapter error: {response.get('error_detail', 'unknown')}"
    context = fixture.envelope.get("context", [])
    checked = response.get("context_checked", [])
    if len(context) >= 1 and len(checked) < 1 + len(context):
        return False, (
            f"context_checked has {len(checked)} entries but envelope has "
            f"{len(context)} context items + 1 trigger; classifier stopped at first match (FR-007)"
        )
    return True, f"context_checked={len(checked)}; envelope_context={len(context)}"


def check_confidence_not_constant(
    fixture, response: dict[str, Any], baseline_confidence: float = 0.85
) -> tuple[bool, str]:
    """FR-008: when two verdicts have plausible support, the winner's confidence
    MUST be below a clean-baseline confidence (default 0.85).
    """
    if not response.get("ok"):
        return False, f"adapter error: {response.get('error_detail', 'unknown')}"
    verdict = response["verdict"]
    confidences = response.get("confidences", {})
    winner_confidence = confidences.get(verdict)
    if winner_confidence is None:
        return False, f"confidences mapping missing winner verdict {verdict!r}"
    if winner_confidence >= baseline_confidence:
        return False, (
            f"winner confidence {winner_confidence} >= baseline {baseline_confidence}; "
            f"confidence is constant (FR-008)"
        )
    return True, f"winner_confidence={winner_confidence} < baseline={baseline_confidence}"


def check_verdict_surface_typed(
    fixture, response: dict[str, Any]
) -> tuple[bool, str]:
    """FR-020 negative-case helper: assert that the adapter REJECTED a
    sentinel-leak output (positive case: fixture asserts the leak is caught).
    """
    if response.get("ok"):
        return False, (
            "expected adapter to reject malformed sentinel as contract violation "
            "but it produced an ok=True verdict (FR-020 / SC-011)"
        )
    if response.get("error_kind") != "sentinel-leak":
        return False, (
            f"adapter rejected output but as {response.get('error_kind')!r}, "
            f"not as 'sentinel-leak' (FR-020 / SC-011)"
        )
    return True, f"sentinel-leak correctly identified: {response.get('error_detail', '')[:120]}"
