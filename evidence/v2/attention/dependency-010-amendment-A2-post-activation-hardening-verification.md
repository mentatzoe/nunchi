# Slice 030 Post-Activation Verification — Hardened Amendment Ledger

**Consumer slice**: `030-v2-core-attention`

**Upstream slice**: `010-v2-contract`

**Result**: PASS — `READY` remains verified

**Verified by**: codex-session-1 (`v2-core-owner`)

**Verified on**: 2026-07-19

**Immutable activation commit**:
`f94bb57a75effdbef093cb997cbc285e2a2559a1`

**Activation reference**: `evidence/v2/attention/slice-activation.md`

**Initial ledger-validator commit**:
`d4f8b95cd7635f02e2aee432f657f8da45913de6`

**First hardening commit**:
`38db5db491b284c9685ae490cb8878d2bdcd97fa`

**First consumer hardening merge commit**:
`d37bbe09cc69a940dcb33a476055471daf399bae`

**Final hardening commit**:
`0969319e6b28c27a25f9564ae4851c5cdfe31f0b`

**Final consumer hardening merge commit**:
`82b6b1a5e60b7d86f00f69ad19304d0a11d9b55b`

**Effective dependency commit**:
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`

## Decision

The immutable slice-030 activation remains substantively and mechanically
valid under the hardened amendment-ledger validator. The stricter checker
derives the same exact effective dependency candidate with an empty error list,
and the complete governance boundary accepts the activation's existing
`010=26a6b531fa146ba1f1f5fcd1c4d191041b141301` mapping.

This record supplements rather than rewrites the activation and its earlier
resolution evidence. It confirms `READY`; it does not declare `ACTIVE`, start
T001, or authorize a candidate, handoff, integration, cutover, release, or
promotion.

## Independent Hardening Review

Exact commit `38db5db491b284c9685ae490cb8878d2bdcd97fa` is the first hardening
descendant of `d4f8b95cd7635f02e2aee432f657f8da45913de6`; exact commit
`0969319e6b28c27a25f9564ae4851c5cdfe31f0b` is its sole final-hardening
descendant merged for this verification. Both diffs change only
`scripts/check_governance.py` and `tests/test_governance.py`; the canonical
`evidence/v2/contract/slice-amendments.md` content is unchanged.

The owner independently confirmed that the hardened implementation:

1. includes `slice-amendments.md` in the lifecycle Git-history replay with
   append-only enforcement and requires prior terminal acceptance;
2. requires each amendment decision commit to descend from its candidate and
   verifies the amendment record at that exact decision commit says
   `Decision: ACCEPTED`, names the candidate, names `v2-integrator`, and carries
   a durable decision reference;
3. fails closed when a present ledger path is unsafe, unreadable, or contains
   no attested records; and
4. tracks each amended interface's effective version across the whole ledger,
   while also checking the human-readable current-effective-commit summary
   against the derived result;
5. validates the last current-effective-commit summary after an append-only
   future extension rather than incorrectly binding to an earlier retained
   summary; and
6. requires the amendment record's decision reference at the decision commit
   to equal the ledger field exactly and to name a file that existed at that
   exact decision commit.

## Commands and Results

Run from `.worktrees/v2-core-attention/` on `v2/core-attention` after merging
the exact hardened commit:

```sh
git merge-base --is-ancestor d4f8b95cd7635f02e2aee432f657f8da45913de6 38db5db491b284c9685ae490cb8878d2bdcd97fa
git merge-base --is-ancestor 38db5db491b284c9685ae490cb8878d2bdcd97fa 0969319e6b28c27a25f9564ae4851c5cdfe31f0b
PYTHONPATH=scripts python3 -c 'from pathlib import Path; import check_governance as c; print(c._effective_dependency_commit(Path(".").resolve(), "010-v2-contract", "bff6b463a44c1b9066fc654691042f9550da6c64"))'
python3 scripts/check_governance.py --check-cli
python3 scripts/check_governance.py --task-manifest specs/030-v2-core-attention
python3 -m unittest tests.test_governance
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
git diff --check
```

Results:

- both ancestry checks: PASS;
- direct hardened resolution:
  `('26a6b531fa146ba1f1f5fcd1c4d191041b141301', [])`;
- governance/CLI boundary: PASS at SpecKit 0.12.11;
- task manifest: T001–T027, no completed IDs, unchanged SHA256
  `d6bd19d5cfdc9c3a5f33b4e43493acadbfcea2d1c88b9c5edb4f6f4d3f4a6f2a`;
- final hardened governance unit suite: 79 passed;
- full repository suite: 1268 passed, 11 skipped, 0 failures;
- V1 verdict-suite discovery: 60 fixtures; and
- diff check: PASS.

The hardened upstream test change leaves the ordered tracked pre-030 inventory
at 59 files and changes its content hash, as expected, to
`748e6419503c562a38aa5f8fa30e8805c38193c5beb797730fd930eadecb9d7d`.
No slice-030 product file or implementation checkbox changed.
