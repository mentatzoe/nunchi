# V2 Program Planning Readiness Checklist

**Purpose**: Prove the program planning baseline is `READY` without confusing
that state with implementation authority or individual slice readiness

**Created**: 2026-07-11

## Authority and Workflow

- [x] Aleph Vault PR 67 (`bdd1ebb`) and contract-clarification PR 68 (`c834e8c`) are merged and verified as the selected upstream authority.
- [x] Constitution 2.3.0, `AGENTS.md`, `CLAUDE.md`, repository docs, and active plans state the same authority order, program/slice lifecycle, external-authority boundary, append-only rework contract, and documentation-freshness gate.
- [x] Program progress (`PLANNING` through `CUTOVER_VERIFIED`), implementation authority (`NOT_GRANTED | GRANTED`), and slice progress (`PLANNED` through `ACCEPTED`) are separate facts.
- [x] The dated 2026-07-11 reset baseline is program `READY`, implementation authority `NOT_GRANTED`, and every slice `010`–`110` `PLANNED` and dormant; live facts derive from declarations, immutable activation/acceptance evidence, and append-only candidate/handoff attempts rather than this checklist.
- [x] SpecKit `0.12.11` is pinned in the repository and installed CLI.
- [x] Codex and Claude integrations are installed from the exact pin.
- [x] The planning-only workflow parses and contains no implementation step.
- [x] The delivery workflow binds and preflights one exact existing slice only through `scripts/run_slice_workflow.py`, resumes only a paused unchanged-task run by run ID, starts a new bound run after changed tasks or rejection, never creates or replaces a feature, and verifies its task artifacts.
- [x] The delivery workflow has separate implementation-authority and slice-readiness gates before implementation.
- [x] The delivery workflow has a documentation-freshness gate after convergence and before slice handoff.
- [x] `evidence/governance/v2-implementation-authorization.md` has an exact neutral schema for recording Zoe's external grant and explicit slice scope; the record cannot grant authority, readiness, cutover, release, or promotion.
- [x] Checked implementation tasks remain rejected until that one record enumerates exactly slices `010` through `110` and the bound slice's separate readiness gate passes.

## Control-Plane Boundary

- [x] Obsolete SpecKit installation and V1 planning artifacts are absent.
- [x] Existing product contracts, docs, tests, fixtures, evals, and evidence reside in ordinary paths.
- [x] Every managed program/slice directory contains planning Markdown only.
- [x] Executable product/build/test/eval/package/release/runtime paths do not depend on `.specify/` or `specs/`.
- [x] Disposable-copy validation proves ordinary tests and evaluation discovery survive removal of all managed paths before clean reinitialization.

## Program and Ownership

- [x] Exactly the umbrella plus slices `010`–`110` exist.
- [x] Every slice has one unique stable accountable owner lane.
- [x] Every slice declares its assigned participant/source (`UNASSIGNED` in the dated reset baseline), exact SpecKit binding, `PLANNED` reset state, and exact ordinary-path activation evidence path; durable assignments update declarations before activation evidence is written.
- [x] Every slice declares hard dependencies, feeds, ordinary targets, worktree/branch, and handoff recipient.
- [x] The dependency graph is acyclic and has `110` as its only final sink.
- [x] Parallel waves do not create shared contract or integration-file ownership.
- [x] State is derived from slice declarations, immutable activation/acceptance evidence, and append-only candidate/handoff attempt streams; there is no central mutable slice-state or assignment registry.
- [x] Only slice `110` may assemble and integrate the atomic cutover, carry Zoe's cutover acceptance, and verify the accepted merge.
- [x] `v2-integrator` owns slice-level acceptance for `010`–`100`, Zoe owns acceptance for `110`, and every dependent separately records its own upstream packet acceptance before `READY`.
- [x] Every dependent activation uses ordered `slice=full-sha` Dependency commits and matching consumer-owned Dependency acceptance reference files with consumer/upstream, commit, accepting participant/date, exact packet, and durable-decision metadata; `010` uses `none` and `110` requires every upstream slice to be `ACCEPTED`.
- [x] Every slice uses immutable `slice-activation.md` and `slice-acceptance.md` records plus append-only `slice-candidate.md` and `slice-handoff.md` attempt streams; activation/candidate evidence carries checker-generated task IDs and hashes, acceptance/rejection names `Recorded by: v2-integrator`, and slice `110` also names program-owner-recorded cutover acceptance plus the exact-main/final-docs post-merge record.
- [x] A handoff rejection appends an attributable `REJECTED` decision, returns the slice declaration to `ACTIVE`, preserves all earlier attempts, and starts a new bound run; convergence-added tasks do the same, while only paused post-convergence fixes with an unchanged task graph resume.

## Interfaces, Scenes, and Evidence

- [x] Interfaces `I-010A`–`I-050A` have exactly one owner and named consumers.
- [x] Every slice uses the canonical interface names and versions without a local fork.
- [x] Scenes `S01`–`S16` have named implementing slices and final parity ownership.
- [x] Every slice maps applicable scenes to exact ordinary test/eval/evidence targets.
- [x] Every slice defines a complete owner handoff packet and rejects unit-only social-quality claims.
- [x] Every slice reviews `README.md`, inventories exact known affected paths, updates its owned docs, hands exact shared-doc deltas to their accepting owners, and records validation/reviewer evidence before handoff.

## Analysis and Baseline

- [x] Clarification review finds no material unresolved choice.
- [x] Cross-artifact analysis finds zero CRITICAL or HIGH issues and no unresolved placeholders.
- [x] Repository governance tests and CLI boundary check pass.
- [x] Existing full test baseline passes without removed or weakened coverage.
- [x] Git diff and repository status review show no unrelated artifact included.

## Exit

- [x] Planning-baseline acceptance confirms no V2 product behavior was implemented.
- [x] At the dated 2026-07-11 reset baseline, the program is `READY`,
  implementation authority is `NOT_GRANTED`, and every slice is `PLANNED`,
  dormant, and unassigned; declarations and evidence supersede that baseline as
  delivery proceeds.
- [x] The repository is ready for Zoe to grant externally scoped implementation
  authority and for assigned participants to activate independently ready
  slices.

## Notes

- Checked items were validated against the complete generated slice set and the
  ordinary-path evidence record. They establish the planning baseline, not V2
  product completion, slice readiness, or implementation permission.
