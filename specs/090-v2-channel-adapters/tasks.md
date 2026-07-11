---
description: "Future Goal 2 task plan for V2 standalone channel adapters"
---

# Tasks: V2 Standalone Channel Adapters

**Execution status**: DORMANT. These tasks describe future Goal 2 work and MUST
NOT be executed under the current Goal 1.

**Input**: `specs/090-v2-channel-adapters/spec.md` and `plan.md`

**Prerequisites**: explicit Goal 2 authorization; accepted `010`–`040` handoffs;
zero CRITICAL/HIGH analysis findings; isolated owner worktree

**Accountable owner lane**: `v2-adapters-owner`

**Integration handoff**: `v2-security-owner`, then `v2-integrator`

## Phase 1: Matched conformance setup

- [ ] T001 Add failing canonical-interface, trusted-bypass, immutable request-correlated receipt-stage ownership, atomic-cutover, and no-V1-bridge assertions in `tests/v2/test_channel_adapters.py`
- [ ] T002 [P] Add matched generic, Discord, Matrix, and Telegram native fixture families, including trusted/forged-bypass and cross-owner-stage cases, in `tests/fixtures/v2/adapters/`
- [ ] T003 [P] Define reusable equivalent-fact, missing-capability, lifecycle, and no-ledger scenes in `evals/v2/channel_adapters/scenes.jsonl`

**Checkpoint**: all adapters pin accepted interfaces without copying shared
schemas or redefining common scene outcomes.

## Phase 2: User Story 1 - Preserve truthful native facts (Priority: P1)

**Goal**: normalize equivalent facts equivalently and missing facts honestly.

**Independent Test**: model-free comparison fails before migration and passes
only when exact identity, relations, ordering, coverage, and capability agree.

- [ ] T004 [US1] Add failing exact-binding, relation, ordering, capability, restart, and continuation comparison tests in `tests/v2/test_channel_adapters.py`
- [ ] T005 [US1] Centralize only factual adapter normalization and hard-budget helpers in `src/nunchi/adapters/__init__.py`
- [ ] T006 [P] [US1] Migrate generic host identity, event parsing, and bounded observation to `I-020A` in `src/nunchi/adapters/channel.py`
- [ ] T007 [P] [US1] Migrate standalone Discord native facts and capability reporting in `src/nunchi/adapters/discord.py`
- [ ] T008 [P] [US1] Migrate Matrix relations, reaction/membership scope, history, and capability reporting in `src/nunchi/adapters/matrix.py`
- [ ] T009 [P] [US1] Migrate Telegram identity, reply/reaction availability, history, and capability reporting in `src/nunchi/adapters/telegram.py`

**Checkpoint**: AD-01 through AD-03 and deterministic S13 pass without a model call.

## Phase 3: User Story 2 - Route one common lifecycle (Priority: P1)

**Goal**: invoke the attention engine once, permit one logical classifier call
for ordinary triggers or zero classifier/model calls for trusted bypass, and
invoke the common participant act-or-silence host without adapter-specific
social rules.

**Independent Test**: matched lifecycle fixtures produce the canonical call
counts, facts, routes, outcomes, and receipts on every adapter.

- [ ] T010 [US2] Add failing SUPPRESS/WAKE/dual-DEFER/error/PREATTENTION_BYPASS, one-engine-invocation, ordinary-one-logical-classifier-call/trusted-bypass-zero-classifier-call, untrusted-bypass rejection, no-fabricated-result, action/silence, evaluation-only meta-answer, no-runtime-prose-filter, request-correlation, single-writer-stage, and no-send-regate tests in `tests/v2/test_channel_adapters.py`
- [ ] T011 [US2] Replace V1 directive routing with canonical `I-030A` plus tagged `I-010B` ok/bypass/error handling, preserving trusted bypass provenance and `classifier_not_invoked`, in `src/nunchi/adapters/channel.py`
- [ ] T012 [US2] Deliver `I-010C`, including advice-free `PREATTENTION_BYPASS`, through one `I-040A` direct act-or-silence path while preserving upstream immutable stages in `src/nunchi/adapters/_responder.py`
- [ ] T013 [US2] Restrict deterministic send backstops to operational safety and append only adapter-attested immutable `transport` stages without fabricating a delivery for participant silence in `src/nunchi/adapters/_backstop.py`
- [ ] T014 [US2] Remove adapter-specific social verdict, addressee, resolution, and handled-state behavior in `src/nunchi/adapters/_responder.py`
- [ ] T015 [US2] Record matched Station-scar, disposition, participant-silence, and error replay in `evals/v2/channel_adapters/lifecycle.jsonl`

**Checkpoint**: AD-04 through AD-06 pass across all adapter families.

## Phase 4: User Story 3 - Prove installed entrypoints (Priority: P2)

**Goal**: establish atomic V2 behavior and provenance for all shipped adapters.

**Independent Test**: exact installed entrypoints reject V1 payloads, accept V2
probes, and report per-surface capabilities/restart truth.

- [ ] T016 [US3] Add failing installed-entrypoint, V1-residue, configuration, and schema-2 probe tests in `tests/v2/test_channel_adapters.py`
- [ ] T017 [US3] Document generic and cross-adapter V2 invocation, budgets, capability semantics, and probes in `docs/adapters-v2.md`
- [ ] T018 [US3] Record matched generic/Discord/Matrix/Telegram AD-01 through AD-06 and AD-08 results, including mandatory S06/S07/S10 bypass and immutable-stage cases, each with stable `scene_id`, request ID, stage owner, trusted provenance, `classifier_not_invoked` where applicable, and applicable S IDs, in `evidence/v2/adapters/scene-results.jsonl`
- [ ] T019 [US3] Record exact installed package, entrypoints, config/process, restart/residue, and AD-07 V2 probes in `evidence/v2/adapters/installed-runtime.md`
- [ ] T020 [US3] Run AD-09 across installed adapter entrypoints with harness-independent participant-host probes shaped like all six pinned S14 stages, including multi-human Discord and multi-human Telegram facts, and commit compatibility evidence in `evidence/v2/adapters/mixed-room.jsonl` without depending on downstream live-harness work

**Checkpoint**: AD-07 proves all in-tree adapter entrypoints use one V2 lifecycle.

## Phase 5: Equivalence and handoff

- [ ] T021 Commit the per-surface fact/action/history/restart/continuation capability matrix in `evidence/v2/adapters/capability-matrix.md`
- [ ] T022 Map AD-01 through AD-09 and applicable S IDs to exact records, commands, candidate commit, request ID, stage owner, classifier-call count, and result in `evidence/v2/adapters/manifest.json`
- [ ] T023 Commit S01–S16 applicability and outcome index, including trusted-bypass zero-classifier-call/no-fabricated-result proof, immutable-stage ownership, post-hoc meta-answer grades, and confirmation that no runtime prose filter ran, in `evidence/v2/adapters/verification.md`
- [ ] T024 Hand off commit, interface versions, commands/results, manifest, evidence, capability differences, provenance, and limitations in `evidence/v2/adapters/handoff.md`

## Dependencies & Execution Order

- T001–T003 require accepted `010`–`040` handoffs.
- Shared model-free comparison establishes US1 before lifecycle migration in US2.
- Generic, Discord, Matrix, and Telegram module changes may proceed in parallel
  only under the same owner lane after shared utilities freeze.
- US3 waits for all four deterministic lifecycle paths.
- Live/bounded evidence and T024 handoff identify the exact candidate submitted
  to slice `100`; assurance consumes rather than precedes that local handoff.
- Slice `110` consumes the committed T024 handoff only after slice `100` accepts
  the candidate.

## Parallel Opportunities

- T002 and T003 target independent fixture/evaluation paths.
- T006–T009 touch separate adapter modules after T004/T005 establish the common
  contract and utilities.
- Per-surface installed probes may run independently but must identify the same
  package commit.

## Implementation Strategy

Prove native-fact equivalence first, route one shared lifecycle second, and prove
installed entrypoints third. Missing platform capability remains explicit; it is
never “fixed” by inventing facts. This task list does not authorize execution.
