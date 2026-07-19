# Slice 030 readiness blocker — program I-010E registry version

**Affected slice**: `030-v2-core-attention`

**Program**: `001-nunchi-v2-program`

**Status**: `OPEN`

**Severity**: `HIGH`

**Discovered by**: codex-session-1

**Discovered on**: 2026-07-19

**Accepted I-010E dependency commit**:
`817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Accepted I-010E version**: `AttentionReceiptV2@2`

**Resolution owner**: `v2-program-owner`

## Finding

Slice 030's exact dependency evidence, bound spec, plan, tasks, ordinary schema,
stdlib mirror, corpus, and contract documentation now consistently consume
accepted I-010E `AttentionReceiptV2@2`. The umbrella program plan's canonical
interface registry at `specs/001-nunchi-v2-program/plan.md` still declares
I-010E `AttentionReceiptV2@1`.

The slice owner may update only this slice's declarations and lifecycle
evidence. It must not silently rewrite the program owner's canonical registry.
The accepted amendment is not invalidated by the stale registry, but the
cross-artifact version conflict is a HIGH planning inconsistency and prevents a
zero-CRITICAL/HIGH readiness result.

Reproduction command after refreshing origin:

```sh
git fetch origin --prune
git show origin/v2/contract:specs/001-nunchi-v2-program/plan.md | rg 'I-010E'
```

At exact remote contract decision `30aba09f13a6752b4c24811da0d8ec772a9d9682`,
the command still reports `AttentionReceiptV2@1` in the program-owned row.

## Required resolution

The assigned `v2-program-owner` must update the umbrella interface registry to
I-010E `AttentionReceiptV2@2`, with the accepted amendment provenance, without
changing slice 030's consumer decision or fabricating any runtime fact. Slice
030 must then consume that program-owned update and rerun fresh bound analysis.

## Lifecycle effect

Slice 030 remains `PLANNED`; its implementation tasks remain `DORMANT` and no
activation record is written. This blocker prevents `READY` independently of
the separate I-010B zero-margin contract blocker.
