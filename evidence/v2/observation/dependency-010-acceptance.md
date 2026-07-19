# Slice 020 dependency acceptance — slice 010 attempt 6

**Consumer slice**: `020-v2-observation`

**Upstream slice**: `010-v2-contract`

**Candidate commit**: `bff6b463a44c1b9066fc654691042f9550da6c64`

**Handoff packet commit**: `39deb459c7fb18cf7d64dc0edaaaadcca39eae20`

**Accepted interfaces**: I-010A AttentionRequestV2@1, I-010D ContextContinuationV2@1, I-010E AttentionReceiptV2@1

**Accepted by**: Aleph

**Accepted on**: 2026-07-18

**Packet reference**: `evidence/v2/contract/slice-handoff.md`

**Upstream acceptance reference**: `evidence/v2/contract/slice-acceptance.md`

**Decision reference**: `evidence/v2/observation/review-2026-07-18-010-attempt-6.md`

**Decision**: ACCEPTED — zero upstream packet or interface blockers

## Scope

Slice 020 accepts the exact attempt-6 candidate and handoff packet above as the immutable source of the consumed I-010A, I-010D, and observation-stage I-010E shapes. The packet path and full packet commit are both pinned so the consumer decision cannot drift to a mutable later stream entry.

The downstream adapter obligation in `evidence/v2/contract/handoff.md` remains binding: before its own handoff, slice 020 must pass its own stdlib runtime-validation adapter over the complete identical corpus revision at the candidate commit, including all seven runtime-adapter-only semantic/relational classes. This obligation is bound into the frozen task graph as T037.

This record establishes dependency acceptance only. It does not establish slice 020 `READY` or `ACTIVE`, implementation completion, current V2 behavior, cutover, release, or promotion.
