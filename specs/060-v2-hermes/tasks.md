---
description: "Slice delivery task plan for the V2 Hermes harness (dormant until authorized)"
---

# Tasks: V2 Hermes Harness

**Slice state**: `PLANNED`

**Execution status**: `DORMANT` while the slice remains `PLANNED`

**Program implementation authority**: `GRANTED`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-hermes-owner-2026-07-24.md

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/060-v2-hermes`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Input**: `specs/060-v2-hermes/spec.md` and `plan.md`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted `010`, `020`, `030`, and `040` handoffs;
`v2-hermes-owner` active; assigned participant and durable external assignment
source declared above; zero CRITICAL/HIGH analysis findings; and an isolated
worktree

**Activation evidence**: `evidence/v2/hermes/slice-activation.md`, written only
after every activation prerequisite is accepted; it copies and attests the
assignment declaration and all other prerequisite facts, establishing `READY`
before `ACTIVE` or any implementation checkbox

**Dependency evidence contract**: the activation record MUST preserve declared
order in `Accepted dependencies`, record ordered `Dependency commits` as
`slice=full-sha`, and record matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Candidate evidence**: `evidence/v2/hermes/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/hermes/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/hermes/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Rejection / rework**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

**Accountable owner lane**: `v2-hermes-owner`

**Integration handoff**: `v2-security-owner`, then `v2-integrator`

**Slice activation**: No checkbox may begin while the slice is `PLANNED` or
before valid activation evidence attests the accepted prerequisites above and
establishes `READY`. The assigned participant must then declare `ACTIVE` before
beginning the first checkbox. This planning baseline creates no product behavior
or implementation authority.

## Phase 1: Conformance setup

- [ ] T001 Add failing canonical-interface and no-V1-bridge assertions in `tests/v2/test_hermes.py`
- [ ] T002 [P] Add exact-profile, alias-collision, bypass/disposition, restart, immutable-stage, and act-or-silence fixtures in `tests/fixtures/v2/hermes/`
- [ ] T003 [P] Define reusable HM-01 through HM-05 scene inputs and expected observations in `evals/v2/hermes/scenes.jsonl`

**Checkpoint**: upstream interface versions are pinned without copying or
changing their schemas.

## Phase 2: User Story 1 - Observe as the exact profile (Priority: P1)

**Goal**: implement exact identity and bounded truthful observation per profile.

**Independent Test**: identity/observation fixtures fail before implementation
and pass with zero alias-derived authorship or cross-profile state leakage.

- [ ] T004 [US1] Add failing exact-binding, multi-profile isolation, and unavailable-fact tests in `tests/v2/test_hermes.py`
- [ ] T005 [US1] Migrate Hermes profile identity and trusted configuration resolution in `integrations/hermes/nunchi-gate/resolve.py`
- [ ] T006 [US1] Replace V1 profile history with profile-bound `I-020A` observation and honest coverage in `integrations/hermes/nunchi-gate/state.py`
- [ ] T007 [US1] Wire native Hermes events and continuation capability without a roster or social ledger in `integrations/hermes/nunchi-gate/__init__.py`

**Checkpoint**: HM-01 passes and every profile has an independent exact binding.

## Phase 3: User Story 2 - Route one normal participant turn (Priority: P1)

**Goal**: consume attention once and invoke zero or one direct act-or-silence turn.

**Independent Test**: all valid/invalid dispositions and participant outcomes
produce the canonical invocation count and separate receipt fields.

- [ ] T008 [US2] Add failing SUPPRESS/WAKE/DEFER/PREATTENTION_BYPASS/error, zero-call bypass, immutable-stage, advice-isolation, direct-turn-instruction, evaluation-only meta-answer, and no-second-judgment tests in `tests/v2/test_hermes.py`
- [ ] T009 [US2] Replace V1 verdict handling with canonical I-030A and I-010B ok/bypass/error routing in `integrations/hermes/nunchi-gate/resolve.py`
- [ ] T010 [US2] Deliver `I-010C` and bound expansion through one `I-040A` participant turn in `integrations/hermes/nunchi-gate/__init__.py`
- [ ] T011 [US2] Preserve correlated immutable observation/attention/participant-host/transport stages, including classifier-not-invoked bypass provenance, in `integrations/hermes/nunchi-gate/state.py`
- [ ] T012 [US2] Remove the V1 intermediate admission prompt and any send-time social permission behavior from `integrations/hermes/nunchi-gate/resolve.py`

**Checkpoint**: HM-02 passes, including valid participant silence after every
waking route.

## Phase 4: User Story 3 - Prove live multi-profile parity (Priority: P2)

**Goal**: establish installed Hermes behavior on shared Discord and Telegram.

**Independent Test**: staged live scenes cite installed identities and report
surface capability differences without invented facts.

- [ ] T013 [US3] Add failing restart and suppressed-event-later-heard conformance tests in `tests/v2/test_hermes.py`
- [ ] T014 [US3] Prepare documentation-freshness inputs by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate all new/existing Hermes `UPDATE` paths, route each shared `HANDOFF` delta (including `README.md`) to its accepting owner, and record all proposed documentation dispositions, paths, results, and reviewer in `evidence/v2/hermes/handoff.md` for the later workflow gate
- [ ] T015 [US3] Add multi-profile Discord and Telegram replay expectations in `evals/v2/hermes/live-scenes.jsonl`
- [ ] T016 [US3] Record one-profile, multi-profile, bypass, and restart scene results with mandatory `scene_id` and HM case ID in `evidence/v2/hermes/hermes-scenes.jsonl`
- [ ] T017 [US3] Record Telegram parity and unavailable-capability observations with mandatory `scene_id` and HM case ID in `evidence/v2/hermes/telegram-scenes.jsonl`

**Checkpoint**: HM-03 through HM-05 have committed evidence and no unsupported
surface parity claim.

## Phase 5: Provenance and Packet Inputs

- [ ] T018 Record exact installed plugin, Nunchi package, model, configuration source, process restart, and V2 probe in `evidence/v2/hermes/installed-runtime.md`
- [ ] T019 Publish the exact deterministic/live command and scene-to-record manifest for all S/HM IDs in `evidence/v2/hermes/verification.md`
- [ ] T020 Prepare the proposed packet input with commit, interface versions, commands/results, evidence, state-isolation shape, documentation dispositions/validation/reviewer, and limitations in `evidence/v2/hermes/handoff.md`; the later convergence, documentation-freshness, and handoff gates—not this checkbox—establish lifecycle state

## Dependencies & Execution Order

- T001–T003 begin only after activation evidence establishes `READY`, the
  assigned participant declares `ACTIVE`, and all four upstream handoffs are
  accepted.
- US1 establishes identity and observation before US2 participant routing.
- US3 starts only after HM-01 and HM-02 pass in the sandbox.
- Local provenance and the separately accepted lifecycle handoff packet derived
  from T020 feed slice `100`; assurance does not depend
  on a handoff that itself waits for assurance.
- Slice `110` consumes the terminally accepted slice candidate only after slice `100` accepts
  the candidate.

## Parallel Opportunities

- T002 and T003 target independent fixture/evaluation paths.
- After US1 stabilizes exact binding, US2 test authoring and US3 scene authoring
  may proceed in parallel without editing the same files.
- Discord and Telegram live evidence runs are independent but must use the same
  accepted plugin commit.

## Implementation Strategy

Land exact identity and observation first, then replace routing atomically, then
run multi-profile live scenes. Do not enable social suppression until later
hearing/restart evidence supports the declared surface policy. The activation
record attests readiness; it does not grant program implementation authority.
