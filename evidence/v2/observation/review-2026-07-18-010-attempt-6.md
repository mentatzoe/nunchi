# Slice 020 consumer review — slice 010 attempt 6

**Consumer slice**: `020-v2-observation`

**Upstream slice**: `010-v2-contract`

**Decision**: ACCEPTED — zero upstream packet or interface blockers

**Reviewed by**: Aleph

**Reviewed on**: 2026-07-18

**Candidate commit**: `bff6b463a44c1b9066fc654691042f9550da6c64`

**Handoff packet commit**: `39deb459c7fb18cf7d64dc0edaaaadcca39eae20`

**Terminal accepted lineage tip / slice 020 starting commit**: `fc60858a3810e2f53d9574cce1eb9589bd19b55b`

## Exact packet and authority

- Packet stream: `evidence/v2/contract/slice-handoff.md`, attempt 6.
- Terminal acceptance: `evidence/v2/contract/slice-acceptance.md`.
- Integrator decision: `evidence/v2/contract/review-2026-07-18-v2-integrator-attempt-6.md`.
- Packet inputs: `evidence/v2/contract/handoff.md` and `evidence/v2/contract/README.md`.
- Candidate, packet, and terminal acceptance are one ancestry chain. The consumed schema blobs are unchanged between the candidate, packet, and terminal accepted lineage tip.

## Accepted interfaces

- `I-010A AttentionRequestV2@1` — `schemas/v2/attention-request.schema.json`.
- `I-010D ContextContinuationV2@1` — `schemas/v2/context-continuation.schema.json`.
- Immutable observation-stage shape of `I-010E AttentionReceiptV2@1` — `schemas/v2/attention-receipt.schema.json`.

## Review findings and disposition

Two independent read-only packet audits found no blocker to consumer acceptance. One audit identified a load-bearing downstream obligation that was not explicit in the dormant slice-020 task graph: before its own handoff, slice 020 must pass its own stdlib runtime-validation adapter over the complete identical attempt-6 corpus revision, including all seven runtime-adapter-only semantic/relational classes. That obligation is now explicit in `specs/020-v2-observation/tasks.md` T004, T008, T015, T037, and T038 and is checked by CHK021.

The accepted I-010E schema is closed and has no token-estimate field. Slice 020 therefore accepts I-010E unchanged, keeps its deterministic token-size proxy in separate evidence only, and records this limitation for `v2-contract-owner` and `v2-integrator`; it does not invent a slice-local receipt field.

The accepted I-010D interface is the fetch-request/fetch-page document union. Slice 020 supplies a separate host-owned provider seam that consumes/produces those documents; it does not reinterpret I-010D itself as a provider.

## Carried obligation

Before slice 020 handoff, T037 must run slice 020's own stdlib runtime-validation adapter over the exact corpus revision at `bff6b463a44c1b9066fc654691042f9550da6c64`, account for all 202 cases and all seven runtime-adapter-only classes, fail on corpus identity or expected-count drift, and record exact command, counts, and result in `evidence/v2/observation/handoff.md`.

## Boundary

This review accepts only the exact upstream dependency. It does not establish slice 020 `READY` or `ACTIVE`, does not prove an observation provider exists, and does not change current V1 behavior, cutover, release, or promotion state.
