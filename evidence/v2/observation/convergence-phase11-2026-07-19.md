# Slice 020 Phase 11 convergence finding — 2026-07-19

**Slice**: `020-v2-observation`

**Source candidate commit**: `77a94cf1f56e70d1f0a79631ee9efba0b6e74a62`

**Source workflow run**: `speckit-020-20260719T041443044304Z`

**Finding**: F1 — CRITICAL — false-negative before-side coverage under cap-truncated `around` fetch

**Disposition**: append T054 while the slice remains `ACTIVE`; do not propose a candidate until the task is complete and independently converged.

## Reproduction

With ordered events `e1`–`e5`, anchor `e3` at index 2, `max_events_per_fetch=6` (radius 3, so `around_window_start == 0`), and a byte cap admitting only `e1`, the `around` scan serves `['e1']` and stops at an index strictly before the anchor. Event `e2` remains an unserved before-anchor event, but the Phase 10 implementation reports `has_more_before: false` because it derives that flag only from `around_window_start > 0` and treats cap truncation as an after-side signal.

This contradicts FR-007, SC-002, Constitution III's requirement for honest coverage/gap facts, and Acceptance Scene S03.

## Required correction

T054 must:

1. add a failing regression test for this exact cap-before-anchor case;
2. track the side of the anchor where cap truncation occurs and OR that fact into the corresponding `has_more_before`/`has_more_after` window-boundary result;
3. add a matching adversarial continuation eval and evidence row;
4. rerun the complete verification matrix; and
5. append a Phase 11 handoff supersession with the final T001–T054 manifest identity and exact results.

## Documentation disposition

`docs/observation/v2.md`: `NO_IMPACT` for T054. The existing guide already states the required truthful `has_more_before`/`has_more_after` behavior; T054 brings code and evidence into conformance without changing that public claim.

## Boundary

This record is correction provenance only. It does not mark T054 complete, establish convergence, create or accept a candidate/handoff, or authorize integration, cutover, deployment, release, or promotion.
