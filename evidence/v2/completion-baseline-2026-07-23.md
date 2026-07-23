# Nunchi V2 completion baseline — 2026-07-23

This immutable audit records the inherited repository state from which the
completion goal in `docs/v2-completion-goal.md` proceeds. It is evidence, not a
mutable program-state registry and not lifecycle acceptance.

**Audited dependency-valid commit**: `0969319e6b28c27a25f9564ae4851c5cdfe31f0b`

**Audited branch**: `v2/contract`

**Recorded on**: `2026-07-23`

**Recorded by**: `v2-integrator`

## Derived lifecycle facts

Slice `010` is terminally `ACCEPTED` for its recorded candidate and the accepted
I-010E and I-010B amendments. The completion target's I-010F authorization seam
has no schema, corpus, or accepted amendment on this commit. No dependent may
treat planning prose or source from another branch as that missing contract.

Every slice `020` through `110` is `PLANNED` in its declaration. The ordinary
runtime, CLI, package version, adapters, and installed surfaces are V1.

An earlier aggregate at
`8e64746970f9910d03b372291c5aa173883e869f` combined unaccepted foundation and
downstream work. It was examined and rejected as the canonical integration
base. Its unique history and closed review records remain available for audit,
but no active branch, worktree, lifecycle declaration, or acceptance claim may
treat that aggregate as current progress. Future owners may reuse individual
ideas only after re-establishing exact dependency compatibility and evidence;
no sunk-cost presumption applies.

## Safe completion order

1. Close and accept every outstanding slice-010 contract amendment required by
   the completion goal, including the portable authorization seam.
2. Plan, implement, and accept slices `020` and `030` from the accepted
   contract successor.
3. Re-plan slice `040` against the accepted contracts so participant wake,
   coalesced conversation scheduling, and privileged-action authorization are
   one coherent shared-host boundary; then implement and accept it.
4. Only then activate the platform and reference-adapter slices whose declared
   dependencies are accepted. Reuse inherited code only after exact
   compatibility and evidence are established.
5. Complete security/provenance assurance, assemble slice `110`, freeze the
   candidate, conduct independent review, cut over atomically, and verify the
   exact `main` successor.

## Known inherited blockers

- The declared product version remains `0.2.0` while the final provenance
  contract requires V2 major versioning.
- I-010F has not been implemented or accepted.
- Slices `020` through `110` are planned, not implemented or accepted.
- The V2 deterministic provenance audit does not exist yet; creating it is
  slice-100 work after the product surfaces are assembled.
- Installed-runtime and live mixed-room V2 evidence does not exist for every
  supported surface.
- Downstream plans predate the live-freshness and provenance-bound
  authorization additions and must be refreshed only after their exact
  dependencies are accepted.
- Release, promotion, `CUTOVER_ACCEPTED`, and `CUTOVER_VERIFIED` have not
  occurred.

## Baseline verification

The preparation successor must keep this audit reproducible with:

```sh
python3 scripts/check_governance.py --check-cli
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

These commands prove the clean V1-current and governance baseline only. They do
not prove any V2 implementation, installed runtime, live behavior, or cutover.
