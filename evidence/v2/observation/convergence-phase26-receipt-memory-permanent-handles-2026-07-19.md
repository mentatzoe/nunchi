# Phase 26 convergence — receipt memory and permanent handle authority

**Date**: 2026-07-19
**Slice**: `020-v2-observation`
**Rejected target**: `22a0a1ab9a996e82ec625ce73e301023889209e4`
**Tree**: `ea186b389424f761a1cc5cbac8faac32f8c28484`
**Parent**: `542afc693c25f0104302e6be97d2d310bdf66778`

## Exact-object rejection

A detached exact-SHA checkout of `22a0a1a` received the Phase 26 regression
module without modifying target source. Three deterministic mechanisms failed:

```text
receipt byte_count after caller mutation: 812
private issued byte_count: 118
uncopyable receipt request: accepted (expected ObservationInputError)
revoked generated handle ID: reissued (expected ContinuationError)
PHASE26_EXACT_22A_RED_EXIT=1
```

The receipt method compared caller-owned memory to the private pending document,
then re-read the caller's mutable events to compute the attestation. A mutation
after equality therefore changed the emitted receipt and consumed the rightful
pending authority. It also never attempted a complete input copy, so custom
copy failure could not fail closed.

Phase 25 rejected generated-ID collision only while a handle remained live. On
revocation, the ID left the live dictionary and could be generated again. With
matching bound context this revives the authority represented by an old opaque
capability. Live-overwrite prevention alone was therefore insufficient.

## Phase 26 correction

1. Deep-copy the complete receipt request before validation or field access;
   convert copy exceptions to `ObservationInputError` without state mutation.
2. Compare the stable caller copy to private pending authority, but construct
   every attested field from a fresh private copy of the provider-issued document.
3. Add one provider-owned 65,536-bit SHA-256 membership filter for every issued
   continuation handle ID. All wrappers share it; revoked IDs remain remembered.
4. Retry generated collisions at most 16 times, then reject. Bloom-filter false
   positives can reject only fresh issuance; they cannot admit reuse.
5. Preserve Phase 25's four adversarial rows and append fifteen Phase 26 rows for
   exact expiry presence, live/revoked collision, fixed-memory identity,
   provider-wide direct/concurrent caps, relation-gap variants, receipt mutation/
   copy failure, and timestamp-watermark retention.

## Local verification

| Check | Result |
|---|---|
| Phase 26 direct regression module | 15 tests, OK |
| issued-handle stress | 25,000 remembered IDs; 0 misses; filter stayed 8,192 bytes |
| Observation discovery | 197 tests, OK |
| full repository | 1,446 tests, OK; 4 optional skips |
| standard scene evidence | 53 rows, 0 FAIL (`9 + 7 + 24 + 4 + 9`) |
| adversarial evidence | 34 rows, 0 FAIL |
| governance suite | 64 tests, OK |
| corpus/docs/scanner/task bundle | 27 tests, OK |
| verdict fixtures | 60 discovered |
| slice task state | 146 total; 137 checked; 6 superseded; open `T103,T145,T146` |
| Ruff / Bandit / governance CLI / diff / reviewer artifact | clean |

The exact activation-range scanner and immutable-object receipts remain T145
work. This receipt grants no acceptance, `CONVERGED`, candidate, or handoff
authority.

## Lifecycle effect

Phase 25 review gate T140 is superseded, not completed. T146 is the sole final
whole-slice review gate after a new immutable T145 object exists. The slice
remains `ACTIVE`.
