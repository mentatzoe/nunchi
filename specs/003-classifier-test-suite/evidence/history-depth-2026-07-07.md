# History-depth experiment — scrollback vs trigger-only (2026-07-07)

Quantifies what conversation history changes about gate judgment, using real
receipts from the 2026-07-05 multi-agent room session in which a regression
caused every hermes-side gate call to run with `history_len: 0` (trigger-only).
Those blind receipts are the baseline; this experiment re-runs a weighted
selection with a reconstructed 20-message scrollback window and diffs verdicts.

Room content is redacted here (organic personal conversation); triggers are
described by category. The un-redacted table lives in the operator's private
records.

## Method

- Window: 2026-07-05 20:00–23:59 UTC, one Discord channel, 73 blind receipts.
- Selection (21): all ACK/ASK verdicts (1), the 10 lowest-confidence-margin
  decisions, 5 SPEAK + 5 PASS controls (deterministic index-based sampling).
- Payloads rebuilt from debug-verbosity receipts; history injected as the 20
  room messages strictly before each trigger (from the room transcript).
- Gate: production model (gemini-3.1-flash-lite) via `nunchi-channel`.
- **Reproduction check passed**: 3 receipts re-run blind reproduced their
  original verdicts exactly, validating payload reconstruction.
- Any changed verdict re-run to 3 total; stability recorded. 33 gate calls total.

## Results

21/21 completed. **5 verdicts changed (24%)**; 4 of 5 flips stable at 3/3.

| direction | n | trigger category |
|---|---|---|
| SPEAK → PASS | 3 | peer-agent had already handled the moment (topic pivot already answered; lull already acknowledged; thread fully resolved) |
| ACK → PASS | 1 | conversation visibly closing — the nod was no longer warranted |
| PASS → SPEAK | 1 | collaborative story continuation: blind, a peer-bot fiction beat looks inert; with context the gate sees an active story circle expecting contribution |

Per-class change rate: PASS 1/5, SPEAK 3/15, ACK 1/1.

Flicker caveat: two additional near-boundary receipts were unstable across
runs without flipping (2/3 majorities). Boundary verdicts are distributions,
not points; the true flip rate is ±1 receipt.

## Interpretation

History depth changed roughly one decision in four, and **almost always toward
silence**: the blind gate over-spoke precisely in multi-agent peer exchanges
where another agent had already handled the moment — the failure mode history
is supposed to prevent. The single opposite flip is structurally distinct and
matches the 2026-07-05 field observation that collaborative-fiction scenes
starve under a blind gate. The ACK class appears to *require* session context
to be meaningful at all (1/1 flipped). Net attribution: ~4–5% of the window's
73 decisions were wrong for lack of history — modest, real, and directionally
consistent. This is the quantified case for the rolling-history change in this
branch.
