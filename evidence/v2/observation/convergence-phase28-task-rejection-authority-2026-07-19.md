# Phase 28 convergence — candidate-bound task truth and immutable rejections

**Date**: 2026-07-19
**Rejected source object**: `abad8d85e8150bfd2716ab77ebb3791827591bf1`
**Rejection record**: `review-2026-07-19-abad8d85-dual-rejection.md`
**Scope**: P28-H1 through P28-H4, stale scanner documentation, and selective
reconciliation of the valid product/evaluation mechanisms from parallel lineage
`3e38a70d634093a26ffbb6c460b9cf51fb81636b`
**Lifecycle authority**: correction evidence only; no candidate/handoff/acceptance authority

## Reproduction (T154 RED)

The focused governance/task-state command ran 77 tests and failed with 10
failures plus 4 errors before production correction:

- malformed `TASK002` and `T 002` checkbox rows remained invisible to the
  canonical parser;
- candidate-attempt policy binding was absent, so exact terminal graph and
  Phase 27 ancestry could not be enforced at the candidate commit;
- shared Slice 020 policy still expected T001–T153 and did not own the complete
  T107/T112/T119/T124/T131/T140/T146→T153→T160 supersession chain;
- rejection-history registration and immutable-recovery helpers were absent;
- the slice-owned task diagnostic still pinned T001–T153 and therefore rejected
  the real appended T154–T160 graph before reaching the sharper RED seams.

The durable dual-rejection record preserves the reviewers' disposable-clone
reproductions for malformed task invisibility, missing/extra candidate graphs,
stale shared supersession acceptance, erasable rejection evidence, and the
historical `80c1de2` byte rewrite.

## Corrections (T155–T158)

### P28-H1 — complete checkbox-shaped parsing and task-manifest authority

- every top-level `- [...]` row in a bound task manifest must parse as one
  canonical `- [ ]|[X]|[x] TNNN ...` task or the parser raises a hard error;
- `--task-manifest` now applies the exact shared Slice 020 policy instead of
  returning any sequential graph it can parse;
- the slice-owned task diagnostic imports the shared policy rather than carrying
  a second terminal/open/supersession authority table.

### P28-H2 — candidate-attempt-2 exact graph and lineage

- shared policy pins terminal T160 and source-controlled ACTIVE checkpoint sets;
- candidate attempt 2 and later must reference a commit that itself passes the
  exact T001–T160 `CONVERGED` task policy and literal completion checks;
- that candidate commit must descend rejected Phase 27 policy baseline
  `abad8d85e8150bfd2716ab77ebb3791827591bf1`;
- attempt 1 retains its historical graph semantics and is not retroactively
  reclassified by the Phase 28 policy.

### P28-H3 — one shared supersession authority

Shared lifecycle now owns the exact supersession mapping, validates every
historical gate as checked, requires its exact later successor, rejects absent or
non-increasing targets, and requires each historical block to retain durable
`not approved`, `unapproved`, or `remains rejected` semantics. The standalone
diagnostic consumes this same policy.

### P28-H4 — immutable rejection evidence with disclosed recovery baseline

Every `review-*-rejection.md` record under `evidence/v2/` is explicitly
registered. Unregistered additions, missing registered paths, working-tree
rewrites, historical rewrites, and deletions fail governance. Normal records are
byte-immutable from introduction and pinned to exact SHA-256 values. The historical
`review-2026-07-19-80c1de2-late-rejection.md` violation is not laundered away:
its exact bytes are pinned from recovery baseline `abad8d85`, and any later
change or deletion fails. The incident disclosure is separately hash-pinned.
The secret-scanner docstring now states the real all-path behavior, and an
executable regression confirms there is no fixture marker or source-line exemption.

## Selective parallel-lineage reconciliation (T159)

`3e38a70` diverges from `abad8d85` at
`22a0a1ab9a996e82ec625ce73e301023889209e4`; neither is an ancestor of the
other. Its `HANDOFF_READY`, candidate-attempt-2, and handoff records therefore
do not succeed the rejected governance lineage and were not imported. Four
exact read-only review artifacts were preserved instead:

- `review-2026-07-19-phase25-hermes-22a0a1a-rejection.md`;
- `review-2026-07-19-phase25-opus-22a0a1a.md`;
- `review-2026-07-19-phase26-hermes-2b10abb-rejection.md`;
- `review-2026-07-19-phase27-hermes-7c86440-approval.md`.

The first two new rejection records were registered in the immutable rejection
registry in the same successor tree. Their copied bytes match the source branch
exactly by SHA-256.

A focused 28-test reconciliation probe first failed with 10 failures and 2
errors on this lineage: selected nearby-event relations and continuation-page
relations were falsely gap-free; known restart loss remained evaluator-only;
`has_restart_gap` was not a provider input; and final S13 page mutations reached
the comparator with missing closed-page fields plus `next_cursor=null`. One
parallel receipt-copy test was then classified as duplicate coverage of the
stronger private-issued receipt authority and removed; the resulting
non-duplicate mechanism set is GREEN.

Carried mechanisms:

- relation closure/gap truth from every returned snapshot event and every
  continuation-page event, preserving actual event/byte truncation causes;
- normalized host-attested restart-gap truth on snapshots and pages;
- closed S13 page construction, mutation-before-validation, and cursor absence
  represented by field removal;
- deterministic reply-before-thread relation priority with a membership set
  used only for deduplication;
- five reconciled adversarial rows and the matching docs/evidence.

Preserved stronger `abad8d85` mechanisms instead of replacing them with the
parallel variants: private issued-document receipt attestation, permanent
fixed-memory continuation-handle non-reuse, candidate-bound governance, immutable
rejection/history controls, and the complete T001–T160 lifecycle policy.

## Moving-tree precommit rejection and repair

The read-only precommit review preserved at
`review-2026-07-19-phase28-precommit-moving-tree-rejection.md` rejected the
moving working tree. Its novel blocking finding proved that free-text
supersession semantics accepted `no longer remains rejected and is now approved`.
That exact attack was added as a RED regression, then the shared policy was
corrected to reject negated rejection language and positive approval assertions;
the focused policy/lifecycle/task-state group is GREEN. The review's stale
40-row adversarial artifact and stale receipt findings were independently
resolved by regenerating 39 non-duplicate rows and rerunning the final matrix.
The review grants no approval because its target moved; only a later immutable
object can receive an authoritative verdict.

## Preparation freeze and exact scan (T159)

**Preparation commit**: `901aaed47e8d7173df4a0a8788ed69e3cecdb44f`

**Tree**: `3c6599fec6c60d2f1e2b3f11afdfb6c767728804`

**Parent**: `6c3b89ef030cfa8bebdc5f206f899569e4e7c813`
**Exact activation-range scan**: CLEAN — base
`fc60858a3810e2f53d9574cce1eb9589bd19b55b`, head
`901aaed47e8d7173df4a0a8788ed69e3cecdb44f`, 90 changed files, 14,942
additions, four matchers.

| Command / lane | Result |
|---|---|
| full repository | 1,467 tests, OK; 4 optional-integration skips |
| Observation discovery | 207 tests, OK |
| governance + literal task-state group | 80 tests, OK |
| static secret-scanner group | 6 tests, OK |
| standard aggregate evidence | 53 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 9 equivalence) |
| Phase 18/23/25/26/28 adversarial evidence | 39 rows, 0 FAIL |
| attempt-6 corpus conformance | 6 tests, 202/202 cases accounted for, exact framed digest GREEN |
| executable docs | 14 tests, OK |
| verdict fixture inventory | 60 fixtures |
| Ruff over changed governance/task/scanner/product/eval/tests | clean |
| Bandit over changed governance/task/scanner/product/eval scripts | clean; 0 findings |
| governance CLI | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| task graph | T001–T160; normalized SHA-256 `7733ed9894f44a063db1a6dcad7c4c79f0d64256b2054c5041c92d3baff84d32` |
| literal task state after T159 closure | total 160; checked 158; superseded T107/T112/T119/T124/T131/T140/T146/T153; open T103/T160 |
| working-tree `git diff --check` | clean |

T159 closes through the two-step freeze: the preparation object above is fully
verified and exact-scanned, while this metadata successor binds that receipt.
The successor's own SHA, push, and post-commit scan must remain external because
a Git object cannot contain evidence of its own identity or publication. T103
and T160 remain review gates. Nothing here establishes `CONVERGED`,
`HANDOFF_READY`, acceptance, integration, deployment, release, promotion, or
cutover authority.
