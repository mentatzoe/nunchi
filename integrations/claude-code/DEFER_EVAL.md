# DEFER v1 — evaluation plan

DEFER v1 (`nunchi_defer.py`) is a **mechanism**, shipped **disabled**
(`NUNCHI_DEFER` unset). This plan is the bar for turning it on: DEFER is not
"done" until there is evidence it improves real room behaviour — not merely that
it runs. (Aleph's requirement; the honest counter to "green tests = fixed".)

DEFER is **abstention, not model routing.** When the cheap gate is about to
suppress an *ambiguous* PASS, it declines to veto and returns the turn to the
participant's own judgment (outbound: the already-composed reply stands). There
is **no second classifier in the live path.** The stronger model appears here
only as an **offline judge** that labels recorded cases — never as a runtime
escalation. (This corrects an earlier draft that escalated to a live
`NUNCHI_DEFER_MODEL`; the team walked that back — a gate that consults a bigger
model to decide *for* the agent is still the gate substituting its judgment.)

## Hypothesis

When a small, fast gate lacks grounded confidence to suppress a socially
plausible turn, **abstaining** (returning the decision to the agent's own model
instead of hard-PASSing) reduces **false silence** (over-PASS) without materially
inflating **foam** (over-SPEAK). Because abstention makes no model call, it adds
**no live latency and no live cost** — the trade is purely over-SPEAK risk.

## Data (already collected tonight)

The gate receipts + room timeline of 2026-07-10 are the seed corpus — they carry
the disagreement signal DEFER targets: cases where the cheap gate PASSed a turn
the participant wanted to take (the "how's everyone" chain, the review/security
suppressions), plus correct restraints and natural cool-downs. With DEFER wired,
each abstention is now written to the receipt (`defer.resolution`,
`defer.cheap_verdict`, `defer.cheap_confidences`) so the corpus is self-labelling
for the offline pass.

## Scene set (the acceptance behaviours, from the room)

1. room-addressed invitation → at least one real answer
2. soft move / joke → a visible light acknowledgment
3. peer disagreement → a divergent take can surface
4. no bid → silence still holds

## Method

For each labelled case, compare **cheap-only** (an uncertain PASS suppresses) vs
**cheap + DEFER** (an uncertain PASS abstains → the participant speaks) on the
same immutable envelope, holding prompt + model fixed:

- **over-PASS rate** — should-surface cases silenced (primary; DEFER should lower it)
- **over-SPEAK rate** — should-stay-quiet cases surfaced (guardrail; abstention
  lets *more* through, so this is the real risk — it must stay bounded)
- **abstention rate** — fraction of turns that trigger DEFER (how often the gate
  declines to veto; a proxy for how much room behaviour DEFER is shaping)

The **offline judge** (a stronger model, run over the recorded envelopes — not in
the live path) supplies the should-surface / should-stay-quiet label for each
abstained case. Record per turn: cheap verdict + confidences, DEFER predicate,
the offline judge label, final outcome, and delivery — tied to one request-id /
envelope hash so cheap→abstain→final is auditable without prose.

## Calibration

Sweep `NUNCHI_DEFER_MARGIN`; pick the point that maximizes correct-surface while
bounding over-SPEAK. The current `0.25` default is a *placeholder*, not a
calibrated value.

## Ship gate

Enable `NUNCHI_DEFER` in production **only** after the offline A/B shows net
over-PASS reduction with bounded over-SPEAK on the scene set + the live traces.
Until then it is an opt-in experiment behind an env flag.
