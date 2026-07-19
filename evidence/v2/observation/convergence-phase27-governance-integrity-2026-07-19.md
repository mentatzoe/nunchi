# Phase 27 convergence — lifecycle truth, scanner scope, and packet integrity

**Date**: 2026-07-19
**Rejected source object**: `a49313a5354259346e1089e759184b9f08735b37`
**Rejection record**: `review-2026-07-19-a49313a-governance-rejection.md`
**Scope**: HIGH-1 through HIGH-3 plus exact-range whitespace
**Lifecycle authority**: correction evidence only; no candidate/handoff/acceptance authority

## Reproduction (T147 RED)

Four independently written seams failed against exact rejected source behavior:

| Mechanism | RED result |
|---|---|
| Literal task oracle without caller-selected open policy | 5 errors: `evaluate_task_state()` still required arbitrary `allowed_open` |
| Shared lifecycle literal completion, exact terminal policy, recovery baseline | 3 errors: authority-bound helpers absent |
| Exact committed-range scanner over omitted lifecycle checker | expected finding returned `0`; scanner reported no changed in-scope file |
| Current packet/provenance | Phase 27 marker absent; stale packet test failed/error |

The durable rejection record additionally preserves the reviewer's exact false
`CONVERGED` disposable-clone probe, terminal-manifest bypasses, omitted-path
secret probe, and four historical non-prefix packet transitions.

## Corrections

### HIGH-1 — lifecycle/task truth

- shared canonical parsing now rejects every checkbox-shaped malformed task row;
- normalized task text still provides stable graph hashing;
- literal completed IDs are computed separately and printed separately;
- Slice 020 candidate/lifecycle validation binds exact T001–T153 identity and
  source-controlled ACTIVE open sets;
- all-checked ACTIVE, missing/extra terminal tasks, and arbitrary open tasks fail;
- obsolete T107/T112/T119/T124/T131/T140/T146 gates are literally checked only
  after their text explicitly names T153 supersession and says their object was
  not approved;
- the slice diagnostic has no `--allow-open` input and validates each exact
  supersession target.

Historical non-020 candidate streams retain their accepted legacy normalized
completion semantics; the new literal candidate rule applies to the explicitly
bound Slice 020 policy instead of retroactively invalidating their lifecycle.
READY activation state also remains governed by its frozen initial manifest;
current terminal policy starts at ACTIVE.

### HIGH-2 — scanner scope

`scripts/check_slice020_secrets.py` now scans every changed path in its explicit
committed base/head range. Synthetic generated-secret regression in
`scripts/check_slice020_task_state.py` returns one redacted finding with the exact
path and never prints the secret value.

### HIGH-3 — packet integrity

The historical rewrite is disclosed at
`handoff-history-integrity-incident-2026-07-19.md`, including all four non-prefix
transitions and baseline object/digest. `handoff.md` retains exact `a49313a` bytes
as its prefix and appends a Phase 27 authoritative correction. Shared governance
replays every change after `a49313a` and rejects any non-prefix revision or
working-tree rewrite.

The stale packet now names T153 as the sole review gate and preserves the real
`v2-core-owner` route in its current section. The three trailing-whitespace lines
in `review-2026-07-19-80c1de2-late-rejection.md` are clean.

## Staged verification and repair

Initial complete staging found four failures:

1. literal candidate completion was applied retroactively to a historical upstream
   candidate stream;
2. a READY-state dependency unit fixture was incorrectly subjected to the
   current ACTIVE Slice 020 terminal policy;
3. a missing/renumbered-terminal test asserted only one of two valid fail-closed
   diagnostics;
4. supersession validation ran after the open-set check and hid the sharper
   T146 error.

All four were repaired and their focused seven-test group passed.

The next staging pass produced:

| Command / lane | Result |
|---|---|
| full repository | 1,452 tests, OK; 4 optional-integration skips |
| Observation discovery | 200 tests, OK |
| governance + scanner + task-state group | 77 tests, OK |
| standard aggregate evidence | 53 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 9 equivalence) |
| Phase 18/23/25/26 adversarial evidence | 34 rows, 0 FAIL |
| attempt-6 corpus conformance | 6 tests, 202/202 cases accounted for, exact framed digest GREEN |
| executable docs | 14 tests, OK |
| Ruff | clean |
| expanded Bandit over governance/task/scanner scripts | 0 findings after exact fixed-argv `nosec` annotations; no shell invocation |
| governance CLI | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| task manifest | T001–T153; normalized SHA-256 `aa5d1bd80107457b7846117603d366a8dcfc83bf9418e38254753d7222386dbf` |
| literal task state before T152 closure | total 153, checked 150, superseded 7, open T103/T152/T153 |
| verdict fixture inventory | 60 |
| `git diff --check` | clean on the working delta |

After T152 closure, the final-tree rerun reproduced 1,452 full-repository tests
with 4 skips and the 77-test governance/static group, with clean Ruff, expanded
Bandit, governance CLI, and diff checks. Literal state was total 153, checked
151, seven explicitly superseded gates, and only T103/T153 open. The immutable
commit/tree/parent and exact all-path activation-range scan are bound in the
external review request immediately after freeze because an object cannot store
its own SHA or post-commit scan output. T103 and T153 remain open. This evidence does not establish
`CONVERGED`, `HANDOFF_READY`, acceptance, integration, deployment, release,
promotion, or cutover authority.
