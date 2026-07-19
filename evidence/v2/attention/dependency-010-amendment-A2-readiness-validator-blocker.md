# Slice 030 Readiness Blocker — Accepted 010 Amendment A2 vs Lifecycle Validator

**Consumer slice**: `030-v2-core-attention`

**Upstream slice**: `010-v2-contract`

**Status**: OPEN

**Severity**: CRITICAL

**Recorded by**: codex-session-1 (`v2-core-owner`)

**Recorded on**: 2026-07-19

**Exact accepted dependency candidate**:
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`

**Consumer acceptance**:
`evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`

**Upstream integrator decision commit**:
`d504310c61a93afbe57d4fe4ed05e93055c75555`

**Upstream decision reference**:
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A2-revised.md`

**Resolution owner**: `v2-program-owner`, coordinating with
`v2-integrator` / `v2-contract-owner` if the resolution changes upstream
lifecycle evidence rather than the program validator

## Finding

Slice 030 independently accepted exact accepted amendment A2 candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`, which carries I-010A @1,
I-010B @2, and I-010E @2. Its readiness activation must therefore use:

```text
Accepted dependencies: 010
Dependency commits: 010=26a6b531fa146ba1f1f5fcd1c4d191041b141301
Dependency acceptance references: 010=evidence/v2/attention/dependency-010-amendment-A2-acceptance.md
```

After all other activation metadata was normalized to the repository's exact
required format, `python3 scripts/check_governance.py --check-cli` rejected that
truthful mapping with exactly:

```text
ERROR: evidence/v2/attention/slice-activation.md: dependency 010 commit must match evidence/v2/contract/slice-handoff.md
```

The validator reads the last lifecycle record from
`evidence/v2/contract/slice-handoff.md`. That append-only stream ends at the
original attempt-6 pre-amendment candidate
`bff6b463a44c1b9066fc654691042f9550da6c64`; neither accepted amendment A1 nor
accepted amendment A2 appended a new lifecycle record there. The validator
therefore rejects the exact current dependency candidate and would accept only
the superseded I-010B/I-010E @1 candidate mapping.

Recording `010=bff6b463a44c1b9066fc654691042f9550da6c64` would make the mechanical
comparison pass but would falsely bind slice 030 to the pre-amendment contract
and contradict the consumer's exact A1/A2 acceptances. This owner will not use
that workaround.

## Independent Reproduction

The activation draft itself was intentionally not retained: an immutable
activation record may exist only after every prerequisite passes. The failure
was reproduced from the isolated `.worktrees/v2-core-attention/` worktree on
branch `v2/core-attention` by staging the exact metadata above and running:

```sh
python3 scripts/check_governance.py --check-cli
rg -n '^\*\*Candidate commit\*\*:' evidence/v2/contract/slice-handoff.md
git merge-base --is-ancestor bff6b463a44c1b9066fc654691042f9550da6c64 26a6b531fa146ba1f1f5fcd1c4d191041b141301
```

The first command produced only the mismatch above after all other activation
metadata errors were corrected. The second shows the last upstream handoff
candidate is `bff6b463a44c1b9066fc654691042f9550da6c64`. The third exits zero,
confirming accepted amendment A2 is a descendant of that original candidate,
not the same candidate.

## Scope and Required Resolution

This finding does not reopen the content of accepted amendments A1 or A2, the
consumer's independent decisions, or the fresh planning analysis. It is also
separate from the already recorded non-blocking stale program interface
registry: the registry text does not participate in this failing comparison.

Resolution must make the governance boundary recognize the exact accepted
post-terminal amendment candidate without weakening exact-commit matching,
rewriting prior immutable records, or assigning the pre-amendment candidate to
the consumer. Valid resolution shapes include an authorized append-only
upstream lifecycle representation for accepted amendments or an authorized
validator rule that derives the current accepted dependency from durable
amendment decisions. The owning program/integration lanes must select and
record that governance rule.

Until then, slice 030 remains `PLANNED`; T001–T027 remain unchecked and dormant;
`evidence/v2/attention/slice-activation.md` remains absent; and no product
implementation begins.
