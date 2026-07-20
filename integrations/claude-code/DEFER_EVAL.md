# DEFER in the Claude Code V2 integration

V2 has two distinct DEFER sources, and this integration adds no third:

1. **Classifier-DEFER** — the participant-shaped model itself returns
   `DEFER`: it cannot justify suppression and widens attention. Routed as
   `effective_disposition: DEFER` with valve `classifier-defer`.
2. **Margin-DEFER** — the model returned `SUPPRESS`, but its legacy
   confidence vector shows the suppression margin inside the operator's
   `transition_defer_margin`, or suppression is disabled/unproven for this
   scope. Routed as `classifier_disposition: SUPPRESS` with
   `effective_disposition: DEFER` and valve `margin-defer` (or
   `policy-defer`).

Both wake the participant with `attention.source: DEFER`; neither injects
advice. The distinction lives in the decision's `routing_audit` and receipts,
never in the participant's instruction. DEFER is abstention toward hearing —
it is not model routing and not a request for the participant to report an
admission decision.

## Where the margin lives now

The V1 gate's `NUNCHI_DEFER` / `NUNCHI_DEFER_MARGIN` environment switches are
gone. The margin is `attention.transition_defer_margin` in the operator policy
JSON, with `transition_defer_margin_source` recording its provenance. It is
trusted operator configuration: room content and model output cannot change
it, and every attention receipt carries the policy provenance that was in
force.

The historical V1 default (`0.25`) was a placeholder, never a calibrated
value. The current operator value is likewise uncalibrated until the
evaluation below runs; the honest state is "chosen, provenance-recorded, not
yet calibrated".

## Evaluation plan

Deterministic routing distinctness is already enforced by
`tests/v2/test_claude_code.py`
(`test_classifier_defer_and_margin_defer_route_distinctly`). Calibration is a
replay evaluation, not a runtime feature:

1. Replay the Station scar corpus (`evals/v2/claude_code/scenes.jsonl`) and
   live-room captures against candidate margins.
2. Count, per margin: suppressions converted to DEFER (cost: extra wakes) and
   false suppressions surviving (cost: silence — the regression class).
3. Prefer the smallest margin whose replayed false-suppression count is zero;
   record the chosen value and its evidence in the policy's
   `transition_defer_margin_source` and in `evidence/v2/claude-code/`.

False suppression remains the highest-risk branch; when in doubt the margin
stays wide.
