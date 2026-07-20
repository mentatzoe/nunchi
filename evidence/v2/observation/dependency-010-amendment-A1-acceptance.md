# Slice 020 dependency acceptance — slice 010 amendment A1-R1

**Consumer slice**: `020-v2-observation`

**Upstream slice**: `010-v2-contract`

**Previously accepted upstream candidate**: `bff6b463a44c1b9066fc654691042f9550da6c64` (I-010A/I-010D/I-010E `@1` attempt 6)

**Amendment candidate commit**: `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Amendment record commit**: `6296316fd415e85762860569289016a675ab5d2d`

**Integrator acceptance commit**: `30aba09f13a6752b4c24811da0d8ec772a9d9682`

**Accepted amended interface**: I-010E AttentionReceiptV2@2

**Unchanged consumed interfaces**: I-010A AttentionRequestV2@1, I-010D ContextContinuationV2@1

**Accepted by**: Aleph (`v2-observation-owner`)

**Accepted on**: 2026-07-19

**Upstream decision reference**: `evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A1-revised.md`

**Upstream amendment reference**: `evidence/v2/contract/amendment-A1-receipt-policy-provenance.md`

**Decision**: ACCEPTED — compatible no-code version rebind for slice 020

## Independent consumer verification

The exact `schemas/v2/attention-receipt.schema.json` objects at the attempt-6 candidate and accepted amendment candidate were loaded with `git show`, parsed as JSON, canonicalized with sorted keys and compact separators, and compared definition-by-definition.

| Definition | Equal between `@1` and `@2`? | Canonical SHA256 |
|---|---|---|
| `observationBody` | YES | `2b8b50f77007d79a8bc682d8e3c6c7f093b14ce5ddea1d6b56a759303ccae687` |
| `participantHostBody` | YES | `1b5517850945c183bd629a9ef7e4af423a5460e43c6b3f8cdc75754541ca2e6b` |
| `transportBody` | YES | `821553467811c2d390b433170a85f78c97619361ceac580365ec5e478b2b0ef3` |
| `attentionBody` | NO (expected amendment scope) | `@1`: `76ba67905775a5fb8d64456da7b1f3c372a658d6b102108f5b2db0166a1e45b0`; `@2`: `fa04239abe3aa9423c6f6c8a58485a9595b06ac8bae9085e3f6b725f8e713cff` |

Slice 020 writes only the immutable observation-stage body and treats later stages as separately owned. Its written body is byte-for-byte structurally unchanged. The accepted `@2` amendment changes only `attentionBody`: required policy provenance for classifier outcomes and the closed `NO_WAKE` operational override pair. Therefore no slice-020 implementation edit is owed by the version change itself.

The consumer nevertheless binds the amended interface explicitly: `spec.md` and `plan.md` cite I-010E AttentionReceiptV2@2 from this decision onward. Completed T001–T038 history and the original attempt-6 dependency record remain unchanged; later handoff evidence must append the new version binding and must not present the historical `@1` packet as the current consumer version.

## Boundary

This record establishes dependency acceptance only. It does not establish completion of convergence tasks, slice-020 convergence, a lifecycle candidate, handoff readiness, current V2 behavior, cutover, release, or promotion.
