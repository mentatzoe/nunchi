# Tasks: V2 Participant Wake

**Input**: `specs/040-v2-participant-wake/spec.md` and `specs/040-v2-participant-wake/plan.md`

**Prerequisites**: Accepted 010, 020, and 030 handoffs; zero CRITICAL/HIGH
analysis findings; active `v2-wake-owner`; explicit Goal 2 authorization

**Accountable owner lane**: `v2-wake-owner`

**Integration handoff**: owners of slices `060` through `100` and
`v2-integrator`

**Goal boundary**: Every checkbox is future Goal 2 product work. No task may
begin under Goal 1.

**Tests**: Red deterministic routing, packet, participant, expansion, receipt,
and send call-count tests precede shared-host acceptance.

## Phase 1: Test and Replay Harness

- [ ] T001 Create participant-host test helpers in `tests/v2/participant/helpers.py`
- [ ] T002 [P] Add red SUPPRESS/WAKE/DEFER/PREATTENTION_BYPASS/ERROR routing, packet, invocation-count, and immutable-stage tests in `tests/v2/participant/test_routing_and_packet.py`
- [ ] T003 [P] Add red action/silence and meta-answer acceptance-evaluation tests in `tests/v2/participant/test_participant_outcomes.py`
- [ ] T004 [P] Add red expansion and send call-count tests in `tests/v2/participant/test_expansion_and_send.py`
- [ ] T005 [P] Create participant lifecycle replay runner in `evals/v2/participant/runner.py`

## Phase 2: User Story 1 - One Decision to One Turn (Priority: P1)

**Goal**: Route SUPPRESS, WAKE, DEFER, PREATTENTION_BYPASS, and ERROR without a second social
judgment and construct a valid independently budgeted wake packet.

**Independent Test**: Fake attention/observation inputs produce zero invocation
for SUPPRESS and exactly one correct-source participant invocation for every
waking branch.

- [ ] T006 [US1] Implement I-040A routing and invocation cardinality, including zero-model-call PREATTENTION_BYPASS routing, in `src/nunchi/participant.py`
- [ ] T007 [US1] Implement compact I-010C packet projection and independent budgets in `src/nunchi/participant.py`
- [ ] T008 [US1] Implement WAKE, DEFER, PREATTENTION_BYPASS, ERROR_FALLBACK, explicit NO_WAKE, and immutable participant-host stage separation in `src/nunchi/participant.py`
- [ ] T009 [P] [US1] Add all waking and non-waking sources to the routing and packet matrix in `evals/v2/participant/routing/cases.jsonl`
- [ ] T010 [US1] Record routing and packet results with mandatory S03/S15 `scene_id` values in `evidence/v2/participant/s03-routing-and-context.jsonl`

## Phase 3: User Story 2 - Direct Action or Silence (Priority: P1)

**Goal**: Invoke a normal decide-and-act participant turn whose valid result is
an actual room action or no-send, never an admission meta-answer.

**Independent Test**: Reference participants produce message, reaction, tool,
silence, malformed, and meta-answer outcomes with the required classifications.

- [ ] T011 [US2] Implement the framework-neutral participant callback and portable turn instruction in `src/nunchi/participant.py`
- [ ] T012 [US2] Implement message, reaction, tool, silence, unknown, and structurally invalid outcomes in `src/nunchi/participant.py`
- [ ] T013 [US2] Enforce untrusted advice and direct-room-turn instruction boundaries without semantically classifying participant output in `src/nunchi/participant.py`
- [ ] T014 [P] [US2] Add action and valid-silence reference participants in `evals/v2/participant/outcomes/participants.py`
- [ ] T015 [P] [US2] Add meta-answer acceptance and advice-red-team corpus in `evals/v2/participant/advice-and-meta/cases.jsonl`
- [ ] T016 [US2] Record WAKE/PREATTENTION_BYPASS action and every waking-source silence/error-fallback result with mandatory S06/S07/S09 `scene_id` values in `evidence/v2/participant/s06-s07-outcomes.jsonl`

## Phase 4: User Story 3 - Expansion and Non-Social Send (Priority: P2)

**Goal**: Expose bounded continuation and a recording operational send seam
without a second Nunchi call or social permission state.

**Independent Test**: Bound fetch and call-graph tests prove correct facts and
limits, one attention call total, and zero send-time social classification.

- [ ] T017 [US3] Implement I-010D/I-020A context expansion callback in `src/nunchi/participant.py`
- [ ] T018 [US3] Implement operational send capability reporting and invocation in `src/nunchi/participant.py`
- [ ] T019 [US3] Implement only the immutable I-010E participant-host stage for packet/expansion/participant/host-send facts, without mutating upstream stages or claiming transport delivery, in `src/nunchi/participant.py`
- [ ] T020 [P] [US3] Add bound expansion attack matrix in `evals/v2/participant/continuation/cases.jsonl`
- [ ] T021 [P] [US3] Add no-second-judgment call graph cases in `evals/v2/participant/send-path/cases.jsonl`
- [ ] T022 [US3] Record expansion, no-ledger, and send-path results with mandatory S10/S16 `scene_id` values in `evidence/v2/participant/s10-expansion-and-send.jsonl`

## Phase 5: Documentation and Handoff

- [ ] T023 Complete documentation freshness by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate each `UPDATE`, route every shared and downstream `HANDOFF` delta (including `README.md`) to its accepting owner, and record all documentation dispositions, paths, results, and reviewer in `evidence/v2/participant/handoff.md`
- [ ] T024 Run the full shared-host scene matrix and publish its exact scene-to-record command manifest in `evidence/v2/participant/README.md`
- [ ] T025 Record commit, commands, I-040A/upstream versions, instruction, callbacks, evidence, documentation dispositions/validation/reviewer, and limitations in `evidence/v2/participant/handoff.md`; handoff is blocked until documentation freshness passes

## Dependencies & Execution Order

- Exact accepted 010/020/030 commits and interface versions are immutable
  inputs to every task.
- T001 precedes deterministic tests; T002–T004 must fail before T006–T019 are
  accepted.
- US1 routing/packet semantics precede participant outcomes and expansion.
- T014/T015 may proceed in parallel after the participant callback shape is
  stable; T020/T021 may proceed in parallel after expansion/send seams exist.
- T025 requires every deterministic/replay record and documentation draft.
- Surface slices 060–090 and assurance slice 100 consume T025; 040 does not wait
  on them. Slice 110 alone integrates accepted candidates.

## Parallel Opportunities

- T002–T005 target separate ordinary paths.
- T014/T015 and T020/T021 are independent corpus families.
- Evidence rendering and documentation may overlap after the shared lifecycle
  is stable, but the handoff waits for both.

## Implementation Strategy

Make routing cardinality and packet truth correct first, then prove direct
action/silence, then add bounded expansion and operational send. Reject any
shortcut that asks the participant to answer admission or consults a social
classifier/permit at send time.

## Notes

- No task edits upstream interfaces or any native/surface integration file.
- No task creates a product artifact under a SpecKit-managed path.
- Shared-host evidence feeds later surface and security owners; it is not final
  parity evidence.
