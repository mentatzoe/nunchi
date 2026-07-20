# Phase 23 convergence — permanent bounded request-ID uniqueness

**Date**: 2026-07-19
**Slice**: `020-v2-observation`
**Rejected target**: `d70f2fd006007a43a6303e66537327a48794e7ed`
**Status**: ACTIVE / BLOCKED

## Owner-review RED

The Phase 22 attestation registry bounded both pending and recently attested IDs
with an LRU. That introduced two correctness defects:

```text
{'reused_request_id': 'ACCEPT',
 'receipt_ids': ['r1', 'r2', 'r1'],
 'pending_overflow_returned_new': 'new',
 'older_issued_receipt': 'ObservationInputError'}
```

1. After `r1` aged out of the recent-attestation LRU, a new snapshot reused
   `r1` and emitted a second valid observation receipt for that correlation ID.
   This defeats stream-level request-ID uniqueness.
2. At the pending cap, snapshot issuance returned `new` after silently evicting
   the already-issued `old`; the provider could no longer emit the required
   observation receipt for every issued request.

The exact review object is therefore rejected before either in-flight reviewer
returns. Those reports remain useful review input but cannot approve a successor.

## Required correction

1. Add RED regressions for ID reuse after attested-LRU eviction and pending-cap
   behavior.
2. Preserve permanent per-provider request-ID non-reuse with fixed memory and no
   false negatives. A bounded Bloom-style bit filter may yield conservative
   false positives (fail closed) but a previously issued ID must always reject.
3. At the pending cap, reject the new snapshot before returning it; never evict
   an issued snapshot that still requires its one observation-stage receipt.
4. Keep the pending document and recent-attestation registries bounded; retain
   exact document/one-shot/mutation non-consumption behavior.
5. Rerun the complete matrix and exact whole-slice scan, freeze a new object,
   and obtain fresh independent fail-closed review.

## Lifecycle effect

T119 is superseded by T124. The slice remains `ACTIVE`; nothing here establishes
`CONVERGED`, `HANDOFF_READY`, acceptance, integration, deployment, release,
promotion, or cutover authority.
