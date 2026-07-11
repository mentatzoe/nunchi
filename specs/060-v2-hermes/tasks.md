---
description: "Future Goal 2 task plan for the V2 Hermes harness"
---

# Tasks: V2 Hermes Harness

**Execution status**: DORMANT. These tasks describe future Goal 2 work and MUST
NOT be executed under the current Goal 1.

**Input**: `specs/060-v2-hermes/spec.md` and `plan.md`

**Prerequisites**: explicit Goal 2 authorization; accepted `010`, `020`, `030`,
and `040` handoffs; zero CRITICAL/HIGH analysis findings; isolated worktree

**Accountable owner lane**: `v2-hermes-owner`

**Integration handoff**: `v2-security-owner`, then `v2-integrator`

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
- [ ] T014 [US3] Document V2 installation, profile isolation, configuration, restart, and probe procedures in `docs/integrations/hermes-v2.md`
- [ ] T015 [US3] Add multi-profile Discord and Telegram replay expectations in `evals/v2/hermes/live-scenes.jsonl`
- [ ] T016 [US3] Record one-profile, multi-profile, bypass, and restart scene results with mandatory `scene_id` and HM case ID in `evidence/v2/hermes/hermes-scenes.jsonl`
- [ ] T017 [US3] Record Telegram parity and unavailable-capability observations with mandatory `scene_id` and HM case ID in `evidence/v2/hermes/telegram-scenes.jsonl`

**Checkpoint**: HM-03 through HM-05 have committed evidence and no unsupported
surface parity claim.

## Phase 5: Provenance and handoff

- [ ] T018 Record exact installed plugin, Nunchi package, model, configuration source, process restart, and V2 probe in `evidence/v2/hermes/installed-runtime.md`
- [ ] T019 Publish the exact deterministic/live command and scene-to-record manifest for all S/HM IDs in `evidence/v2/hermes/verification.md`
- [ ] T020 Hand off commit, interface versions, commands/results, evidence, state-isolation shape, and limitations in `evidence/v2/hermes/handoff.md`

## Dependencies & Execution Order

- T001–T003 begin only after all four upstream handoffs are accepted.
- US1 establishes identity and observation before US2 participant routing.
- US3 starts only after HM-01 and HM-02 pass in the sandbox.
- Local provenance and T020 handoff feed slice `100`; assurance does not depend
  on a handoff that itself waits for assurance.
- Slice `110` consumes the committed T020 handoff only after slice `100` accepts
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
hearing/restart evidence supports the declared surface policy. Never infer
implementation authorization from this task list.
