# Phase 22 convergence — provider attestation and fail-closed input order

**Date**: 2026-07-19
**Slice**: `020-v2-observation`
**Correction source**: independent Codex review of exact object
`cd8917c56f0d051f52cdba68c177d45e7a9f1103`
**Status**: ACTIVE / BLOCKED

## Current-tree adjudication

The stale review was rerun against the post-Phase-21 object
`785bffdf95f303c830cd8f74ef4fe85f0cab4820`.

Live RED mechanisms:

```text
receipt_probe {'duplicate_calls': 'ACCEPT', 'fabricated': 'ACCEPT'}
timestamp_probe [('e1', '2026-07-19T00:00:02Z'),
                 ('e2', '2026-07-19T00:00:01Z')]
unroutable_probe {'outcome': 'unroutable', 'retained': 0,
                  'accepted': True}
constructor_probe {'snapshot': 'ObservationInputError', 'retained': 1}
```

1. The provider can emit multiple observation-stage receipts for one request
   and can attest a caller-fabricated request it never issued.
2. Runtime event order follows ingest order but ingest does not enforce the
   accepted non-decreasing parseable timestamp rule.
3. `unroutable` accepts candidate-only fields and silently drops the supplied
   event instead of rejecting the contradictory transport shape.
4. Invalid constructor identity/room/visibility facts can survive through
   ingest, poison retained state, and fail only during snapshot assembly.
5. T037 pins a 40-character revision label and counts cases but does not verify
   that the three corpus files match the accepted slice-010 bytes.

Already closed or non-live findings:

- the S13 comparator defect is closed by T109–T111;
- stale matrix counts are closed by the exact Phase 21 153/52/1402 matrix;
- the scanner now passes its exact `785bffd` range over 60 files and 8,789
  additions with no marker exemption;
- accepted base/candidate/packet and both Amendment-A1 upstream commits are all
  present in the real repository; their absence from the history-free archive
  was an archive-method artifact, not dependency drift.

## Required correction

1. Retain a bounded private copy of each provider-issued snapshot awaiting its
   observation receipt. Accept exactly one receipt for an exact issued request;
   reject duplicates, unknown IDs, and mutated/fabricated documents without
   consuming the rightful pending attestation.
2. Reject an authorized event whose parseable timestamp would make retained
   authoritative order decrease, before any provider state mutation.
3. Enforce the exact closed `unroutable` transport shape.
4. Validate constructor self/room/visibility facts before initializing mutable
   retained state.
5. Pin and verify a deterministic byte digest over the exact three accepted
   attempt-6 corpus files, with a mutation regression.
6. Rerun and preserve the complete matrix, exact scan, immutable candidate, and
   a fresh fail-closed review.

## Lifecycle effect

`785bffd` is rejected as the final candidate target. T106/T112 remain open and
Phase 22 T113–T119 bind the correction. The slice remains `ACTIVE`; nothing in
this record establishes `CONVERGED`, `HANDOFF_READY`, acceptance, integration,
deployment, release, promotion, or cutover authority.
