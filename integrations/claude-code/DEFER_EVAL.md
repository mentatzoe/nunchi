# DEFER — calibration and evaluation plan

DEFER ships **on by default** as part of the wake-time gate
(`nunchi_prompt_gate.py`): an *uncertain* PASS abstains instead of silencing,
handing the turn to the agent's own model with the gate's hesitation noted.
The mechanism is contract-tested (`tests/test_defer.py`); what is **not** yet
evidenced is the calibration — whether the default margin (0.25) draws the
line between "silence" and "your call" in the right place for real rooms.
This plan is the bar for calling the margin calibrated, and the honest counter
to "green tests = tuned".

DEFER is **abstention, not model routing**: no second classifier runs anywhere,
live or hidden. "Forward to the bigger model" means the agent itself — the
model already holding the room decides, and deciding *silence* is a success
case, not a failure of DEFER.

## Hypothesis

When a small fast gate lacks grounded confidence to suppress a socially
plausible bid, abstaining reduces **false silence** (over-PASS) without
materially inflating **foam** (over-SPEAK), because the agent's own model is a
better judge of ambiguous bids than a hard threshold. Abstention adds no gate
latency and no extra model call — the trade is purely over-SPEAK risk, bounded
by the agent's own judgment.

## Data

Receipts are self-labelling for this: every abstention is a
`defer-uncertain-pass` row (with the cheap verdict + confidences), every hard
block a `block-pass` row, every admit an `allow-*` row. The live room's
timeline (which turns actually got replies, which silences read as absence)
supplies the ground truth. The 2026-07-10 over-suppression incidents — the
"how's everyone" chain, the review/security suppressions — are the seed
regression set.

## Scene set (acceptance behaviours, from the room)

1. room-addressed invitation → at least one real answer
2. soft move / joke → a visible light acknowledgment
3. peer disagreement → a divergent take can surface
4. no bid → silence still holds

## Method

Replay recorded envelopes offline (same prompt, same model, fixed) and label
each with a stronger model as **should-surface** / **should-stay-quiet** —
the stronger model is an *offline judge over recorded cases only*, never a
live path. Then compare, per candidate margin:

- **over-PASS rate** — should-surface cases hard-blocked (primary; DEFER
  should lower it)
- **over-SPEAK rate** — should-stay-quiet cases that got surfaced after an
  abstention (guardrail; must stay bounded — this measures whether the agent's
  own judgment actually declines the bad ones)
- **abstention rate** — fraction of PASS verdicts that defer (how often the
  gate is punting; near 100% means the gate adds nothing, near 0% means DEFER
  is inert)

## Calibration

Sweep `NUNCHI_DEFER_MARGIN` over the labelled corpus; pick the point that
maximizes correct-surface while bounding over-SPEAK. Until that run is
committed as evidence, **0.25 is a placeholder, not a calibrated value** — say
so anywhere the margin is quoted.
