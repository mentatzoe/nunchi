# DEFER v1 — evaluation plan

DEFER v1 (`nunchi_defer.py`) is a **mechanism**, shipped **disabled**
(`NUNCHI_DEFER_MODEL` unset). This plan is the bar for turning it on: DEFER is
not "done" until there is evidence it improves real room behaviour — not merely
that it runs. (Aleph's requirement; the honest counter to "green tests = fixed".)

## Hypothesis

When a small, fast gate model lacks grounded confidence to suppress a socially
plausible turn, escalating that same envelope once to a stronger model reduces
**false silence** (over-PASS) without materially inflating **foam** (over-SPEAK)
or cost.

## Data (already collected tonight)

The gate receipts + room timeline of 2026-07-10 are the seed corpus — they carry
the disagreement signal DEFER targets: cases where the cheap gate PASSed a turn
the participant wanted to take (the "how's everyone" chain, the review/security
suppressions), plus correct restraints and natural cool-downs.

## Scene set (the acceptance behaviours, from the room)

1. room-addressed invitation → at least one real answer
2. soft move / joke → a visible light acknowledgment
3. peer disagreement → a divergent take can surface
4. no bid → silence still holds

## Method

For each labelled case, compare **cheap-only** vs **cheap + DEFER** on the same
immutable envelope, holding prompt + model fixed:

- **over-PASS rate** — should-surface cases silenced (primary; DEFER should lower it)
- **over-SPEAK rate** — should-stay-quiet cases surfaced (guardrail; must not balloon)
- **escalation rate** — fraction of turns that trigger DEFER (cost)
- **latency** — added round-trip on escalated turns only

Record per turn: cheap verdict + confidences, DEFER predicate, frontier verdict,
final outcome, delivery, and a later human/eval label — tied to one request-id /
envelope hash so cheap→escalate→final is auditable without prose.

## Calibration

Sweep `NUNCHI_DEFER_MARGIN`; pick the point that maximizes correct-surface while
bounding escalation rate. The current `0.25` default is a *placeholder*, not a
calibrated value.

## Ship gate

Enable `NUNCHI_DEFER_MODEL` in production **only** after the A/B shows net
over-PASS reduction with bounded over-SPEAK and cost on the scene set + the live
traces. Until then it is an opt-in experiment behind an env flag.
