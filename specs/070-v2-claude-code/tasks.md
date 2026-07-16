---
description: "Slice delivery task plan for the V2 Claude Code harness (dormant until authorized)"
---

# Tasks: V2 Claude Code Harness

**Slice state**: `PLANNED`

**Execution status**: `DORMANT` while the slice remains `PLANNED`

**Program implementation authority**: `GRANTED`

**Assigned participant / source**: Station — evidence/governance/assignments/station-v2-claude-owner-2026-07-16.md

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/070-v2-claude-code`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Input**: `specs/070-v2-claude-code/spec.md` and `plan.md`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted `010`–`050` handoffs; `v2-claude-owner` active; assigned
participant and durable external assignment source declared above; zero
CRITICAL/HIGH analysis findings; and an isolated owner worktree

**Activation evidence**: `evidence/v2/claude-code/slice-activation.md`, written
only after every activation prerequisite is accepted; it copies and attests the
assignment declaration and all other prerequisite facts, establishing `READY`
before `ACTIVE` or any implementation checkbox

**Dependency evidence contract**: the activation record MUST preserve declared
order in `Accepted dependencies`, record ordered `Dependency commits` as
`slice=full-sha`, and record matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Candidate evidence**: `evidence/v2/claude-code/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/claude-code/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/claude-code/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Rejection / rework**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

**Accountable owner lane**: `v2-claude-owner`

**Integration handoff**: `v2-security-owner`, then `v2-integrator`

**Slice activation**: No checkbox may begin while the slice is `PLANNED` or
before valid activation evidence attests the accepted prerequisites above and
establishes `READY`. The assigned participant must then declare `ACTIVE` before
beginning the first checkbox. This planning baseline creates no product behavior
or implementation authority.

## Phase 1: Conformance and regression setup

- [ ] T001 Add failing canonical-interface, trusted-bypass, immutable request-correlated receipt-stage ownership, atomic-cutover, and no-V1-bridge assertions in `tests/v2/test_claude_code.py`
- [ ] T002 [P] Add bot, exact-self, native-relation, disposition, trusted/forged-bypass, cross-owner receipt-stage, evaluation-only meta-answer, and restart fixtures in `tests/fixtures/v2/claude_code/`
- [ ] T003 [P] Define Station scar and common participant-turn replay scenes in `evals/v2/claude_code/scenes.jsonl`

**Checkpoint**: all canonical interface versions and the accepted `I-050A`
mapping are pinned without copying upstream contracts.

## Phase 2: User Story 1 - Hear reactively (Priority: P1)

**Goal**: deliver exact authorized human and other-bot room facts without polling.

**Independent Test**: installed transport/hook fixtures fail before the patch and
pass only with reactive bot delivery and honest cold-wake capability.

- [ ] T004 [US1] Add failing allowlisted bot-delivery, exact-self, relation, and no-polling tests in `tests/v2/test_claude_code.py`
- [ ] T005 [US1] Rebase and constrain the allowlist-aware bot-message change in `integrations/claude-code/transport-patch/0001-allow-bot-messages-allowfrom.patch`
- [ ] T006 [US1] Migrate native notification parsing and exact Claude binding to `I-050A` in `integrations/claude-code/nunchi_prompt_gate.py`
- [ ] T007 [US1] Record patch base, digest, supported plugin version, and cold-wake limitation in `integrations/claude-code/transport-patch/README.md`

**Checkpoint**: CC-01 passes against the installed supported plugin path.

## Phase 3: User Story 2 - Preserve model nuance (Priority: P1)

**Goal**: assemble bounded facts, invoke the attention engine once, and make
exactly one participant-shaped classifier call for an ordinary trigger or zero
classifier/model calls for trusted bypass, with no deterministic social rule.

**Independent Test**: Station replay cases show literal facts at `I-030A` and no
hook rule for addressee, resolution, question, relevance, or class address.

- [ ] T008 [US2] Add failing `I-010A`, coverage, continuation, one-`I-030A`-invocation, ordinary one-logical-classifier-call, trusted-bypass zero-classifier-call/no-fabricated-result, untrusted-bypass rejection, immutable-stage, and Station regression tests in `tests/v2/test_claude_code.py`
- [ ] T009 [US2] Replace V1 payload/history assembly with `I-020A` and bounded `I-010A` in `integrations/claude-code/nunchi_prompt_gate.py`
- [ ] T010 [US2] Replace V1 verdict and fixed local margin routing with canonical `I-030A` plus tagged `I-010B` ok/bypass/error handling, preserving trusted bypass provenance and `classifier_not_invoked`, in `integrations/claude-code/nunchi_prompt_gate.py`
- [ ] T011 [US2] Remove deterministic social filters and preserve ordinary suppressed/self observations in `integrations/claude-code/nunchi_prompt_gate.py`
- [ ] T012 [US2] Add later-hearing and restart/capability replay expectations in `evals/v2/claude_code/recovery.jsonl`

**Checkpoint**: CC-02, CC-03, and deterministic CC-05 pass.

## Phase 4: User Story 3 - Act directly or stay silent (Priority: P1)

**Goal**: deliver one `I-010C` turn and retain Claude's normal action/no-send path.

**Independent Test**: waking routes invoke one turn; effective suppression invokes
none; evaluation flags meta-answer without a runtime prose filter, and any
send-time social judgment is rejected.

- [ ] T013 [US3] Add failing advice-isolation, message/reaction/tool, silence, PREATTENTION_BYPASS act-or-silence, evaluation-only meta-answer, no-runtime-prose-filter, no-send-regate, request-correlation, and no-cross-owner-stage-mutation tests in `tests/v2/test_claude_code.py`
- [ ] T014 [US3] Deliver `I-010C` facts, including advice-free `PREATTENTION_BYPASS`, and optional bound `I-010D` expansion through one `I-040A` invocation while preserving upstream immutable stages in `integrations/claude-code/nunchi_prompt_gate.py`
- [ ] T015 [US3] Replace V1 environment examples with trusted V2 interface, budget, and delegation settings in `integrations/claude-code/nunchi-gate.env.example`
- [ ] T016 [US3] Prepare documentation-freshness inputs by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate all new/existing Claude `UPDATE` paths, route each shared `HANDOFF` delta (including `README.md`) to its accepting owner, and record all proposed documentation dispositions, paths, results, and reviewer in `evidence/v2/claude-code/handoff.md` for the later workflow gate

**Checkpoint**: CC-04 passes and the send path has no social reclassification.

## Phase 5: Live Evidence and Packet Inputs

- [ ] T017 Run CC-01 against the exact installed transport/hook and commit reactive allowlisted bot hearing, native-fact, and no-polling evidence in `evidence/v2/claude-code/reactive-bot-hearing.jsonl`
- [ ] T018 Run and commit CC-02 through CC-05 results, including mandatory S06/S07/S10 bypass and immutable-stage cases, each with stable `scene_id`, request ID, stage owner, trusted provenance, `classifier_not_invoked` where applicable, and applicable S IDs, in `evidence/v2/claude-code/scene-results.jsonl`
- [ ] T019 Record exact plugin base/patch, hook, Claude Code, Nunchi package, model/config, process restart, and CC-06 live V2 probe in `evidence/v2/claude-code/installed-runtime.md`
- [ ] T020 Map CC-01 through CC-06 and applicable S IDs to exact records, commands, candidate commit, request ID, stage owner, classifier-call count, and result in `evidence/v2/claude-code/manifest.json`
- [ ] T021 Index deterministic/live commands and CC-01 through CC-06 outcomes, including trusted-bypass zero-classifier-call/no-fabricated-result proof, immutable-stage ownership, post-hoc meta-answer grades, and confirmation that no runtime prose filter ran, in `evidence/v2/claude-code/verification.md`
- [ ] T022 Prepare the proposed packet input with commit, interface versions, commands/results, manifest, evidence, capabilities, effective limits, documentation dispositions/validation/reviewer, and limitations in `evidence/v2/claude-code/handoff.md`; the later convergence, documentation-freshness, and handoff gates—not this checkbox—establish lifecycle state

## Dependencies & Execution Order

- T001–T003 require activation evidence to establish `READY`, the assigned
  participant to declare `ACTIVE`, and accepted `010`–`050` interfaces.
- US1 establishes the live event source before US2 attention migration.
- US3 starts only after CC-02/CC-03 prove one canonical attention route.
- Live evidence and the proposed T022 packet input identify the exact candidate later submitted to slice
  `100`; assurance consumes rather than precedes that local handoff.
- Slice `110` consumes the terminally accepted slice candidate only after slice `100` accepts
  the candidate.

## Parallel Opportunities

- T002 and T003 target separate fixture/replay paths.
- Station replay authoring may proceed while transport patch provenance is
  prepared, but integration waits for accepted `I-050A` behavior.
- Installed-runtime documentation can be drafted while deterministic US3 tests
  are written; evidence values are filled only after live execution.

## Implementation Strategy

Prove hearing first, remove deterministic social behavior second, and deliver
the direct participant turn third. Stop on any unproved recoverability or plugin
provenance claim and widen attention rather than silently suppressing. The
activation record attests readiness; it does not grant program implementation
authority.
