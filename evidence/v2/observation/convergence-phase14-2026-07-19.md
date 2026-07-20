# Slice 020 convergence review — attempt 2 retention-cursor finding

**Date**: 2026-07-19
**Candidate reviewed**: `cd61dfd649b8f03f340b553ac3864183d42fe567`
**Review mode**: independent, read-only convergence review followed by owner-side live reproduction
**Verdict**: REJECT

## H020-A2-01 — HIGH — before/after cursors are not retention-safe

`ContinuationProvider.fetch()` stores identity-bound remaining-event metadata for `around` cursors, but `before` and `after` replay parse a bare positional index from the cursor. The provider's event buffer is a bounded `deque`; eviction reindexes retained events between page mint and replay.

Owner-side deterministic reproduction on the exact candidate:

- `before`, anchor `e5`, page cap 2: page 1 served `['e3', 'e4']`; after appending `e6` evicted `e1`, cursor replay served `['e2', 'e3']`, duplicating `e3`.
- `after`, anchor `e2`, page cap 1: page 1 served `['e3']`; after appending `e6` evicted `e1`, cursor replay served `['e5']`, silently skipping the originally next event `e4`.

The page still declares `has_gaps: false`. This violates FR-007/FR-009, SC-002/SC-003, exact-event dedup, authoritative order, and truthful continuation coverage.

## Required correction

1. Add RED tests for both directions under retention index shift, including no overlap/skip and fail-closed behavior if a cursor's remaining original identity is evicted.
2. Bind `before`/`after` cursors to their original remaining event identities and anchor/direction, resolve those identities against the live index at replay, and reject if any are gone.
3. Add deterministic eval cases and regenerated evidence.
4. Rerun Observation, corpus, scene, full-suite, verdict, governance, task-manifest, and diff gates; append a superseding handoff receipt.

This review does not accept the slice or authorize integration, cutover, deployment, release, or promotion.
