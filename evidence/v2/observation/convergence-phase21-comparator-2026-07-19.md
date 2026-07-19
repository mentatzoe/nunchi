# Phase 21 convergence — complete semantic comparator

**Date**: 2026-07-19
**Slice**: `020-v2-observation`
**Correction source**:
`evidence/v2/observation/review-2026-07-19-f38a4fe-late-rejection.md`,
HIGH H4
**Status**: ACTIVE / BLOCKED

## Current-tree RED reproduction

Against the post-Phase-20 implementation, `compare_requests()` returned
`equivalent: true` with an empty `unexplained` list for every case below:

```text
reversed_authoritative_order {'equivalent': True, 'unexplained': []}
one_sided_native_fact {'equivalent': True, 'unexplained': []}
coverage_divergence {'equivalent': True, 'unexplained': []}
actor_divergence {'equivalent': True, 'unexplained': []}
```

The mechanism is direct:

- converting event lists into dictionaries discards authoritative order;
- iterating only the intersection of event keys ignores one-sided fields;
- comparing only `coverage.continuity` ignores caps, gaps, truncation, side
  availability, and visibility;
- actor maps are never compared.

This contradicts the comparator's own promise to classify every semantic
difference and leaves SC-006 evidence underpowered.

## Required correction

1. Define the intentionally request-local/opaque fields excluded from parity
   (`request_id`, capability handle IDs, exact cursor tokens, and expiry clocks).
2. Compare schema/self/room/actors, authoritative event order, complete common
   event shapes, trigger/anchor, all semantic coverage fields, capability shape,
   direction, and next-cursor presence.
3. Preserve explicit capability-gap explanations for declared unavailable event
   or actor identities and declared continuity differences; no silent one-sided
   fact may be explained.
4. Add unit and S13 evaluator cases for order, one-sided event facts, actors,
   coverage, continuation pages, and request-local opaque IDs.
5. Regenerate S13 evidence, rerun the complete matrix and exact scanner, freeze
   and push a new object, and obtain fresh independent review.

## Lifecycle effect

No Phase 20 object may become candidate attempt 2. T103/T107 remain open and
T108–T112 bind this correction. The slice remains `ACTIVE`; nothing here
establishes `CONVERGED`, `HANDOFF_READY`, acceptance, integration, deployment,
release, promotion, or cutover authority.
