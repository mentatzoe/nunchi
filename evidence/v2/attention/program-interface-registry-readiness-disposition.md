# Slice 030 disposition — program interface registry synchronization

**Affected slice**: `030-v2-core-attention`

**Program**: `001-nunchi-v2-program`

**Program finding status**: `OPEN` (owner handoff remains required)

**Slice-030 readiness disposition**: `NON_BLOCKING_HANDOFF`

**Recorded by**: codex-session-1

**Recorded on**: 2026-07-19

**Program resolution owner**: `v2-program-owner`

**Prior finding**:
`evidence/v2/attention/program-interface-registry-I-010E-version-blocker.md`

## Disposition

The prior record correctly found that the program-owned canonical interface
registry was stale after accepted post-terminal contract amendments. That
program fact remains open: the registry must now synchronize both accepted
I-010B `AttentionDecisionV2@2` and I-010E `AttentionReceiptV2@2`, with their
accepted amendment provenance.

The stale registry is not itself a slice-030 dependency or a slice-owner-
controlled artifact. Slice 030 depends only on terminally accepted
`010-v2-contract`, and this consumer has separately accepted the exact current
contract candidate at
`evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`, carrying
I-010A `@1`, I-010B `@2`, and I-010E `@2`. The bound slice spec, plan, tasks,
ordinary schemas, validator mirrors, corpora, evidence, and current contract
documentation can therefore agree on the exact consumed versions without
editing the program owner's registry or treating that registry as runtime
truth.

For slice-030 readiness analysis, the program mismatch is an explicit owner
handoff rather than a CRITICAL/HIGH finding in the bound slice's requirements,
coverage, or task graph. This later disposition supersedes only the prior
record's statement that registry synchronization independently prevented
slice-030 `READY`; it does not rewrite that immutable discovery, close the
program issue, or authorize this owner to edit the umbrella plan.

## Required program handoff

`v2-program-owner` must update the canonical interface registry in
`specs/001-nunchi-v2-program/plan.md` to the accepted I-010B `@2` and I-010E
`@2` versions and cite the exact amendment decisions. Slice 030 records that
handoff in its planning and later activation evidence but neither performs nor
claims the program-owned correction.
