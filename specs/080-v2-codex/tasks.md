---
description: "Future Goal 2 task plan for the V2 Codex harness"
---

# Tasks: V2 Codex Harness

**Execution status**: DORMANT. These tasks describe future Goal 2 work and MUST
NOT be executed under the current Goal 1.

**Input**: `specs/080-v2-codex/spec.md` and `plan.md`

**Prerequisites**: explicit Goal 2 authorization; accepted `010`–`050` handoffs;
zero CRITICAL/HIGH analysis findings; isolated owner worktree

**Accountable owner lane**: `v2-codex-owner`

**Integration handoff**: `v2-security-owner`, then `v2-integrator`

## Phase 1: Cross-path conformance setup

- [ ] T001 Add failing canonical-interface, atomic-cutover, and prompt/runner single-processing assertions in `tests/v2/test_codex.py`
- [ ] T002 [P] Add native event, exact-self, session, bypass/disposition, immutable-stage, action/silence, and forged-control fixtures in `tests/fixtures/v2/codex/`
- [ ] T003 [P] Define reusable Codex attention, persistent-session, and mixed-room scenes in `evals/v2/codex/scenes.jsonl`

**Checkpoint**: all accepted interfaces are pinned and no local contract/schema
copy is created.

## Phase 2: User Story 1 - Stay in the conversation (Priority: P1)

**Goal**: consume reactive Discord events with bounded persistent context.

**Independent Test**: event/session/restart fixtures fail before implementation
and pass only with one native trigger, exact binding, and truthful resume/gaps.

- [ ] T004 [US1] Add failing `I-050A`, ordering, deduplication, exact-binding, session-resume, and restart tests in `tests/v2/test_codex.py`
- [ ] T005 [US1] Migrate shared Discord event consumption and cross-path native-ID deduplication in `src/nunchi/integrations/codex_room_runner.py`
- [ ] T006 [US1] Replace prompt-tag prose reconstruction with canonical event facts in `src/nunchi/integrations/codex_prompt_gate.py`
- [ ] T007 [US1] Keep room-bound persistent conversation state operational and remove social fields in `src/nunchi/integrations/codex_runtime_state.py`
- [ ] T008 [US1] Expose bounded `I-020A` observation and `I-010D` expansion in `src/nunchi/integrations/codex_room_runner.py`

**Checkpoint**: CD-01, CD-02, and CD-05 pass without polling or double processing.

## Phase 3: User Story 2 - Judge once and act directly (Priority: P1)

**Goal**: route one attention result into zero or one normal Codex turn.

**Independent Test**: every disposition and participant outcome has the expected
model-call count, host action, send behavior, and separate receipt fields.

- [ ] T009 [US2] Add failing SUPPRESS/WAKE/dual-DEFER/PREATTENTION_BYPASS/error, zero-call bypass, immutable-stage, advice, action/silence, evaluation-only meta-answer, no-runtime-prose-filter, and no-send-regate tests in `tests/v2/test_codex.py`
- [ ] T010 [US2] Replace V1 verdict routing with canonical I-030A and I-010B ok/bypass/error handling in `src/nunchi/integrations/codex_prompt_gate.py`
- [ ] T011 [US2] Build and deliver `I-010C` through one `I-040A` act-or-silence turn in `src/nunchi/integrations/codex_room_runner.py`
- [ ] T012 [US2] Remove the send-time classifier and per-trigger social permission behavior in `src/nunchi/integrations/codex_send_gate.py`
- [ ] T013 [US2] Preserve correlated immutable observation/attention/participant-host/transport records, including classifier-not-invoked bypass provenance, in `src/nunchi/integrations/codex_runtime_state.py`
- [ ] T014 [US2] Add Station-scar, dual-valve, error, and no-ledger adversarial replay in `evals/v2/codex/adversarial.jsonl`

**Checkpoint**: CD-03 and CD-04 pass with zero send-time social calls.

## Phase 4: User Story 3 - Install and prove Codex (Priority: P2)

**Goal**: package, configure, restart, and live-probe the exact V2 Codex path.

**Independent Test**: installed plugin/process evidence identifies all active
components and proves retired V1 residue absent before mixed-room claims.

- [ ] T015 [US3] Add failing plugin bundle, hook/MCP configuration, and retired-residue tests in `tests/v2/test_codex.py`
- [ ] T016 [US3] Cut the distributable plugin configuration over to V2 hooks and `I-050A` in `integrations/codex/nunchi-codex/.mcp.json`
- [ ] T017 [US3] Update the packaged prompt hook wrapper to the exact V2 implementation in `integrations/codex/nunchi_prompt_gate_codex.py`
- [ ] T018 [US3] Update the room runner wrapper to the exact packaged V2 implementation in `integrations/codex/nunchi_room_runner.py`
- [ ] T019 [US3] Replace the packaged social send gate with an operational-only backstop in `integrations/codex/nunchi_send_gate_codex.py`
- [ ] T020 [US3] Migrate trusted V2 configuration controls and remove social-permission settings in `src/nunchi/integrations/codex_config_app.py`
- [ ] T021 [US3] Update the packaged configuration-app wrapper to the exact V2 implementation in `integrations/codex/nunchi_config_app.py`
- [ ] T022 [US3] Complete documentation freshness by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate all new/existing Codex `UPDATE` paths, route each shared/transport `HANDOFF` delta (including `README.md`) to its accepting owner, and record all documentation dispositions, paths, results, and reviewer in `evidence/v2/codex/handoff.md`

**Checkpoint**: deterministic packaging and installed-runtime prerequisites for
CD-06/CD-07 pass.

## Phase 5: Live evidence and handoff

- [ ] T023 Run and commit Codex persistent-session, bypass/disposition, immutable-stage, action/silence, adversarial, and mixed-room results with mandatory `scene_id` and CD case ID in `evidence/v2/codex/scene-results.jsonl`
- [ ] T024 Record exact source/plugin/package/Codex/transport/process/model/config identities, residue removal, restart, and schema-2 probe in `evidence/v2/codex/installed-runtime.md`
- [ ] T025 Publish the exact command and scene-to-record manifest for applicable S01–S16/CD outcomes in `evidence/v2/codex/verification.md`
- [ ] T026 Hand off commit, interface versions, commands/results, evidence, session/capability limits, documentation dispositions/validation/reviewer, and known gaps in `evidence/v2/codex/handoff.md` only after documentation freshness passes

## Dependencies & Execution Order

- T001–T003 require accepted `010`–`050` handoffs.
- US1 must establish one exact event/session path before US2 changes routing.
- US3 packaging begins after deterministic CD-03/CD-04 success.
- Live evidence and T026 handoff identify the exact candidate submitted to slice
  `100`; assurance consumes rather than precedes that local handoff.
- Slice `110` consumes the committed T026 handoff only after slice `100` accepts
  the candidate.

## Parallel Opportunities

- T002 and T003 target distinct fixture/evaluation paths.
- After event deduplication freezes, US2 test authoring and US3 bundle test
  authoring may proceed in parallel.
- Persistent-session and adversarial replay evidence can run independently but
  must identify the same candidate commit.

## Implementation Strategy

Unify input/session paths first, replace attention and participant routing second,
retire send re-gating third, and prove the installed plugin last. No task may
execute until Goal 2 is explicitly authorized.
