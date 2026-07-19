# Slice 020 convergence review — Phase 17 exact-expiry boundary

**Date**: 2026-07-19
**Review object**: owner-side fail-closed boundary probe against immutable candidate `55620049a4abd63672951ea2bd221558846fe1df`
**Verdict**: REJECT candidate readiness

## S020-A5-01 — HIGH / security — capability serves at its exact expiry instant

Phase 16 made missing, malformed, naive, and later fetch times fail closed, but
`check_binding_expiry()` used `fetch_time > expires_at`. A direct probe with both
values equal to `2026-07-19T10:30:00Z` served event `e1`:

```text
EXACT_EXPIRY_RESULT=ACCEPT ['e1']
```

An `expires_at` instant is the first instant at which authority is no longer
valid. Equality must reject (`fetch_time >= expires_at`), reclaim the expired
handle, and have deterministic unit/eval evidence.

## Required correction

1. Add a RED exact-boundary test proving equality rejects and cleanup occurs.
2. Use exclusive expiry semantics, add a deterministic resource-safety case,
   regenerate evidence/manifest/handoff, and preserve all earlier behavior.
3. Rerun the complete matrix, bind the expanded task graph, and obtain a fresh
   immutable independent review before candidate attempt 2.

This record does not accept the slice or authorize integration, cutover,
deployment, release, or promotion.
