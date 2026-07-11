# Tasks: V2 Observation

**Input**: `specs/020-v2-observation/spec.md` and `specs/020-v2-observation/plan.md`

**Slice state**: `PLANNED`

**Execution status**: `DORMANT` while the slice remains `PLANNED`

**Program implementation authority**: `NOT_GRANTED`

**Assigned participant / source**: UNASSIGNED — may be replaced during
planning, before implementation authority, only from a durable external
assignment source; activation evidence later copies and attests it when
establishing `READY`

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted declared dependency `010-v2-contract`; an assigned
participant and durable external assignment source declared above;
active `v2-observation-owner`; zero CRITICAL/HIGH analysis findings; and an
isolated owner worktree

**Activation evidence**: `evidence/v2/observation/slice-activation.md`, written
only after every activation prerequisite is accepted; it copies and attests the
assignment declaration and all other prerequisite facts, establishing `READY`
before `ACTIVE` or any implementation checkbox

**Dependency evidence contract**: the activation record MUST preserve declared
order in `Accepted dependencies`, record ordered `Dependency commits` as
`slice=full-sha`, and record matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Candidate evidence**: `evidence/v2/observation/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/observation/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/observation/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Rejection / rework**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

**Accountable owner lane**: `v2-observation-owner`

**Integration handoff**: owners of slices `040` through `110` and `v2-integrator`

**Slice activation**: No checkbox may begin while the slice is `PLANNED` or
before valid activation evidence attests the accepted prerequisites above and
establishes `READY`. The assigned participant must then declare `ACTIVE` before
beginning the first checkbox.

**Tests**: Deterministic tests and replay scenes are required before each
provider or continuity claim is accepted.

## Phase 1: Shared Test and Replay Harness

- [ ] T001 Create observation test helpers in `tests/v2/observation/helpers.py`
- [ ] T002 [P] Add native-shape replay loader in `evals/v2/observation/replay.py`
- [ ] T003 [P] Add shared/reference observation comparator for downstream reuse in `evals/v2/observation/compare.py`
- [ ] T004 [P] Add red shared-provider tests covering exact self, actor-targeted mentions, and distinct room-wide mentions in `tests/v2/observation/test_provider.py`
- [ ] T005 [P] Add red budget and continuation tests in `tests/v2/observation/test_budget_and_continuation.py`

## Phase 2: User Story 1 - Native Facts and Exact Self (Priority: P1)

**Goal**: Implement exact self binding, actor/event normalization, and narrowly
bounded transport hygiene.

**Independent Test**: Native-shape fixtures preserve exact actor identity and
literal structure; only duplicate, exact-self, and unroutable scenes avoid an
attention candidate.

- [ ] T006 [US1] Implement I-020A provider boundary and immutable observation-stage I-010E emission in `src/nunchi/observation.py`
- [ ] T007 [US1] Implement factual actor/event normalization with distinct actor-targeted and room-wide mention facts in `src/nunchi/observation.py`
- [ ] T008 [US1] Implement bounded outcome-neutral observation storage in `src/nunchi/observation.py`
- [ ] T009 [P] [US1] Add exact-self, actor-targeted mention, room-wide mention, and transport-hygiene reference cases in `evals/v2/observation/identity-and-hygiene/cases.jsonl`
- [ ] T010 [US1] Record exact-self, mention-distinction, and hygiene reference results with mandatory `scene_id` values for S01, S02, S04, S11, and S16 in `evidence/v2/observation/identity-and-hygiene.jsonl`

## Phase 3: User Story 2 - Bounded Snapshot and Expansion (Priority: P1)

**Goal**: Assemble budgeted requests and enforce bound continuation without a
context bomb or relation-loss concealment.

**Independent Test**: Multiple budget/fetch matrices stay within hard caps,
preserve trigger/order/fitting relations, and report every known omission.

- [ ] T011 [US2] Implement trigger-first bounded assembly in `src/nunchi/observation.py`
- [ ] T012 [US2] Implement bound before/after/around fetch in `src/nunchi/observation.py`
- [ ] T013 [P] [US2] Add budget sweep corpus in `evals/v2/observation/budgets/cases.jsonl`
- [ ] T014 [P] [US2] Add continuation attack corpus in `evals/v2/observation/continuation/cases.jsonl`
- [ ] T015 [US2] Record serialized-byte and estimated-token results with mandatory S03/S15 `scene_id` values in `evidence/v2/observation/budget-sweep.jsonl`
- [ ] T016 [US2] Record continuation binding and order results with mandatory S03/S15 `scene_id` values in `evidence/v2/observation/continuation.jsonl`

## Phase 4: User Story 3 - Recoverability and Comparison References (Priority: P2)

**Goal**: Prove the shared seam against reference capability/continuity variants
and provide a reusable comparison contract for later native bindings without
claiming that any real surface has passed it.

**Independent Test**: Simulated reference providers with equivalent native facts
normalize equivalently, and reference restart-safe claims fail unless simulated
backfill restores content and exact actor identity. Actual surfaces remain
downstream evidence obligations.

- [ ] T017 [P] [US3] Add continuity and capability variants in `evals/v2/observation/capabilities/cases.jsonl`
- [ ] T018 [P] [US3] Add red reference-provider recoverability tests in `tests/v2/observation/test_recoverability.py`
- [ ] T019 [P] [US3] Add red reference-equivalence and downstream comparator-contract tests in `tests/v2/observation/test_equivalence.py`
- [ ] T020 [US3] Implement simulated reference restart/backfill behavior outside product code in `evals/v2/observation/capabilities/reference_provider.py`
- [ ] T021 [US3] Record recoverability reference results in `evidence/v2/observation/s05-recoverability.jsonl`
- [ ] T022 [US3] Record capability-neutral equivalence results in `evidence/v2/observation/s13-equivalence.jsonl`

## Phase 5: Documentation and Packet Inputs

- [ ] T023 Prepare documentation-freshness inputs by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate each `UPDATE`, route every global and downstream `HANDOFF` delta (including `README.md`) to its accepting owner, and record all proposed documentation dispositions, paths, results, and reviewer in `evidence/v2/observation/handoff.md` for the later workflow gate
- [ ] T024 Publish the scene-to-record manifest, reference capability rules, and explicit downstream suppression-eligibility proof boundary in `evidence/v2/observation/README.md`
- [ ] T025 Prepare the proposed packet input with commit, commands, I-020A version, shared/reference modules, evidence, downstream comparator obligations, documentation dispositions/validation/reviewer, and limitations in `evidence/v2/observation/handoff.md`; the later convergence, documentation-freshness, and handoff gates—not this checkbox—establish lifecycle state

## Dependencies & Execution Order

- The accepted 010 schema commit is immutable input to every task.
- T001 precedes shared tests; T004/T005 must fail before T006–T012 are accepted.
- US1 supplies normalization and storage used by US2 and US3.
- T013 and T014 may proceed in parallel after the shared replay loader exists.
- T017–T019 may proceed in parallel after US1/US2 shared seams stabilize.
- T020 follows the red recoverability tests; T021/T022 require their respective
  suites; T025 requires all evidence and documentation.
- Downstream slices may bind native surfaces only after separately accepting
  and recording the lifecycle handoff packet derived from T025; each
  surface owner must rerun the comparator/recoverability contract, and 110 alone
  may make the final cross-surface claim.

## Parallel Opportunities

- T002–T005 target separate ordinary files.
- T017–T019 target separate ordinary test/eval paths.
- Recoverability and equivalence evidence may run concurrently once the shared
  provider is stable.

## Implementation Strategy

Build one factual provider first, then bounded expansion, then reference
recoverability and equivalence assets. Do not implement a native transport,
harness binding, or social behavior here. Downstream platforms that cannot prove
a fact or restart property must report an honest limitation, and reference
results must never be substituted for their installed-surface evidence.

## Notes

- No task edits 010-owned schemas, native transport sources, or 040/060–090
  harness and adapter entrypoints.
- No task creates a product artifact under a SpecKit-managed path.
- Outcome-neutral retention must be testable without a live classifier.
- Restart/backfill simulations live only in tests/evals; actual persistence and
  native-history behavior remain owned by downstream surfaces.
