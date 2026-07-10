"""DEFER v1: gate *abstention*, not model routing.

The causal-permit fix stops the gate judging the *wrong* message. DEFER handles
the other half Zoe named: the gate judging the *right* message but a small, fast
model lacking the grounded confidence to suppress a socially plausible turn — and
hard-PASSing anyway.

The corrected shape (Zoe's proposal; team-unanimous, walking back an earlier
"escalate to a second classifier" drift):

> When the cheap gate is about to suppress an *ambiguous* bid, it **abstains**
> and returns judgment to the agent's **own main model** — the thing already
> holding the continuity, identity, and (outbound) the composed reply. It may
> still choose silence. The gate declines to veto; it does **not** manufacture a
> reply, and it does **not** consult a second classifier in the live path.

Aleph's line is the standard: *a gate may silence only when it knows enough to
silence; otherwise it gets out of the agent's way.* PASS must be earned; DEFER is
an abstention from suppression, **not a weaker PASS**.

This module implements the **outbound** case (the participant has already
composed): an uncertain PASS becomes a fail-open — the composed reply stands.
The stronger model belongs **offline** as an evaluator over recorded DEFER
cases (``DEFER_EVAL.md``), never in the live path.

Disabled unless ``NUNCHI_DEFER`` is truthy.
"""
from __future__ import annotations

import os
from typing import Any

_ALT_VERDICTS = ("SPEAK", "ACK", "ASK")


def defer_enabled() -> bool:
    return (os.environ.get("NUNCHI_DEFER") or "").strip().lower() in {"1", "true", "on", "yes"}


def defer_margin() -> float:
    """PASS is 'uncertain' when a plausible alternative sits within this margin
    of it. Placeholder default; calibration is the eval arm, not a claim."""
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
    *,
    margin: float | None = None,
    enabled: bool | None = None,
) -> tuple[dict, dict[str, Any]]:
    """Outbound DEFER. Return ``(final_directive, meta)``.

    If enabled and the cheap `directive` is an uncertain PASS, **abstain**: return
    a non-suppressive directive so the participant's already-composed reply
    stands. No model call, no frontier verdict — the gate just declines to veto
    a turn it cannot confidently silence. Anything else passes through unchanged.
    """
    enabled = defer_enabled() if enabled is None else enabled
    margin = defer_margin() if margin is None else margin
    meta: dict[str, Any] = {
        "defer_enabled": bool(enabled),
        "defer_triggered": False,
        "cheap_verdict": directive.get("verdict") if isinstance(directive, dict) else None,
        "cheap_confidences": directive.get("confidences") if isinstance(directive, dict) else None,
    }
    if not enabled or not is_uncertain(directive, margin):
        return directive, meta

    meta["defer_triggered"] = True
    meta["resolution"] = "abstain-return-to-participant"
    # Abstain from suppression: the participant chose to compose this reply, and
    # a gate that cannot confidently silence must not veto it. This does not
    # manufacture speech — it declines to prevent it.
    return (
        {
            "verdict": "SPEAK",
            "silent": False,
            "reasons": [
                "defer: gate uncertain — abstained from suppression; "
                "returned to the participant's own judgment"
            ],
            "confidences": {"PASS": 0.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0},
            "degraded": True,
        },
        meta,
    )
