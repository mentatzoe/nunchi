# Slice 030 Resolution — Accepted 010 Amendment A2 Dependency Validation

**Consumer slice**: `030-v2-core-attention`

**Upstream slice**: `010-v2-contract`

**Status**: RESOLVED

**Resolved on**: 2026-07-19

**Recorded by**: codex-session-1 (`v2-core-owner`)

**Superseded blocker**:
`evidence/v2/attention/dependency-010-amendment-A2-readiness-validator-blocker.md`

**Upstream prerequisite commit**:
`7e525cb09962b314ff2ffd287295bb9e86dd2c5d`

**Upstream resolution commit**:
`d4f8b95cd7635f02e2aee432f657f8da45913de6`

**Consumer merge commit**:
`4c1f65cbcd5a2ea9f9a08ecae3c63459bd3be3c6`

**Canonical amendment ledger**:
`evidence/v2/contract/slice-amendments.md`

**Effective dependency commit**:
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`

## Resolution

The canonical append-only slice-010 amendment ledger records accepted A1 and
A2 as an unbroken chain from terminal attempt-6 candidate
`bff6b463a44c1b9066fc654691042f9550da6c64` through A1 candidate
`817394d6cd4aa17fc47d7a89ebb8c8d974c595eb` to effective A2 candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`. It preserves the original
terminal lifecycle packet and decisions rather than rewriting them.

`scripts/check_governance.py` now validates every ledger record's identity,
acceptance status, unique amendment ID, commit existence and ancestry, prior-
effective chain, exact one-step interface version increase, integrator
acceptance, ISO date, and durable references. Its
`_effective_dependency_commit()` result replaces the stale terminal handoff
candidate only for downstream dependency validation.

Slice 030 merged the exact two-commit upstream lineage and retained its own
independent A2 acceptance. The activation boundary now accepts exactly:

```text
Accepted dependencies: 010
Dependency commits: 010=26a6b531fa146ba1f1f5fcd1c4d191041b141301
Dependency acceptance references: 010=evidence/v2/attention/dependency-010-amendment-A2-acceptance.md
```

Using the terminal pre-amendment candidate remains invalid, so the resolution
does not weaken exact-commit matching or reopen accepted slice 010.

## Verification

From `.worktrees/v2-core-attention/` on `v2/core-attention`:

```sh
git merge-base --is-ancestor 7e525cb09962b314ff2ffd287295bb9e86dd2c5d d4f8b95cd7635f02e2aee432f657f8da45913de6
python3 -m unittest tests.test_governance
python3 scripts/check_governance.py --check-cli
python3 scripts/check_governance.py --task-manifest specs/030-v2-core-attention
```

Results: the ancestry check passed; 72 governance tests passed; the complete
governance/CLI boundary passed at SpecKit 0.12.11 with the exact activation
mapping above; and the task manifest remains T001–T027 with no completed IDs
and unchanged SHA256
`d6bd19d5cfdc9c3a5f33b4e43493acadbfcea2d1c88b9c5edb4f6f4d3f4a6f2a`.

This resolution closes only the dependency-validation blocker. The separately
owned program interface-registry synchronization remains a non-blocking
handoff, and no implementation task, candidate, handoff, integration, cutover,
release, or promotion follows from this record.
