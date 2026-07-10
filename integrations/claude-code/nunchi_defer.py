"""DEFER v1: escalate-on-uncertainty routing for the Claude Code gate.

The causal-permit fix stops the gate judging the *wrong* message. This handles
the other half of the over-suppression problem Zoe named: the gate judging the
*right* message but a small, fast model lacking the grounded confidence to
suppress a socially plausible turn — and hard-PASSing anyway. ("I've seen Fable
*want* to respond and the gate not allow it.")

DEFER is host-side routing, not a fifth public verdict (the `PASS|ACK|ASK|SPEAK`
enum is frozen per docs/STABILITY.md). When the cheap gate is about to suppress
an *ambiguous* bid, the host escalates the same immutable envelope once to a
stronger model and uses its ordinary four-way verdict. Hard constraints, from
the room (Aleph/Vigil):

- **Never a forced PASS on failure.** If the frontier model is unavailable or
  errors, DEFER *removes the veto* (fail open — the participant's own composed
  reply stands); it does not quietly become PASS. "Uncertain" must not decay
  into a slower silence.
- **Only on the uncertain cut.** A confident PASS is not escalated (no frontier
  cost on obvious turns).
- **Everything recorded.** cheap verdict + confidences → escalation → final
  verdict, so the disagreements become eval data, not invisible gate behaviour.

**v1 status:** this is the *mechanism*. The uncertainty threshold is a
hyperparameter, NOT yet calibrated — whether it improves real room behaviour is
the job of the paired eval arm (EVAL below / DEFER_EVAL.md), not a claim this
module makes. Disabled unless a frontier model is configured.
"""
from __future__ import annotations

import os
from typing import Any, Callable

_ALT_VERDICTS = ("SPEAK", "ACK", "ASK")


def defer_model() -> str:
    """The frontier model to escalate to, or '' (→ DEFER disabled)."""
    return (os.environ.get("NUNCHI_DEFER_MODEL") or "").strip()


def defer_margin() -> float:
    """PASS is 'uncertain' when a plausible alternative sits within this margin
    of it. Deliberately conservative default; calibration is the eval arm."""
    try:
        return float(os.environ.get("NUNCHI_DEFER_MARGIN") or 0.25)
    except ValueError:
        return 0.25


def is_uncertain(directive: dict, margin: float) -> bool:
    """True when the cheap gate is about to suppress an *ambiguous* social bid:
    the verdict is PASS but a plausible alternative is within `margin` of it."""
    if not isinstance(directive, dict) or directive.get("verdict") != "PASS":
        return False
    conf = directive.get("confidences")
    if not isinstance(conf, dict):
        return False
    try:
        pass_c = float(conf.get("PASS", 0.0))
        best_alt = max(float(conf.get(k, 0.0)) for k in _ALT_VERDICTS)
    except (TypeError, ValueError):
        return False
    return (pass_c - best_alt) < margin


def resolve(
    directive: dict,
    escalate: Callable[[str], dict],
    *,
    margin: float | None = None,
    model: str | None = None,
) -> tuple[dict, dict[str, Any]]:
    """Return ``(final_directive, meta)``.

    If DEFER is enabled (a frontier `model` is set) and the cheap `directive` is
    an uncertain PASS, call ``escalate(model)`` once and use its verdict. On any
    escalation failure, fail OPEN — return a non-suppressive directive so the
    participant's reply stands — never a forced PASS.
    """
    model = defer_model() if model is None else model
    margin = defer_margin() if margin is None else margin
    meta: dict[str, Any] = {
        "defer_enabled": bool(model),
        "defer_triggered": False,
        "cheap_verdict": directive.get("verdict") if isinstance(directive, dict) else None,
        "cheap_confidences": directive.get("confidences") if isinstance(directive, dict) else None,
    }
    if not model or not is_uncertain(directive, margin):
        return directive, meta

    meta["defer_triggered"] = True
    meta["defer_model"] = model
    try:
        frontier = escalate(model)
        if not isinstance(frontier, dict) or frontier.get("verdict") not in (
            "PASS", "ACK", "ASK", "SPEAK"
        ):
            raise ValueError("frontier returned no usable verdict")
    except Exception as exc:  # provider down / timeout / malformed
        meta["defer_error"] = str(exc)
        meta["fallback"] = "fail-open"
        # Remove the veto, do NOT force PASS: the composed reply stands.
        return (
            {
                "verdict": "SPEAK",
                "silent": False,
                "reasons": [
                    "defer: frontier adjudication unavailable — veto removed "
                    "(fail-open), the participant's reply stands"
                ],
                "confidences": {"PASS": 0.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0},
                "degraded": True,
            },
            meta,
        )
    meta["frontier_verdict"] = frontier.get("verdict")
    return frontier, meta
