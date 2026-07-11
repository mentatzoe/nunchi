# Tasks: V2 Core Attention

**Input**: `specs/030-v2-core-attention/spec.md` and `specs/030-v2-core-attention/plan.md`

**Prerequisites**: Accepted 010 handoff, zero CRITICAL/HIGH analysis findings,
active `v2-core-owner`, and explicit Goal 2 authorization

**Accountable owner lane**: `v2-core-owner`

**Integration handoff**: `v2-wake-owner`, owners of slices `060` through `110`,
and `v2-integrator`

**Goal boundary**: Every checkbox is future Goal 2 product work. No task may
begin under Goal 1.

**Tests**: Red deterministic contract/transition tests precede implementation;
replay/model evidence remains separate from unit mechanics; live participant
canaries belong to dependent surfaces and final integration.

## Phase 1: Test and Evaluation Harness

- [ ] T001 Create attention-engine test helpers in `tests/v2/attention/helpers.py`
- [ ] T002 [P] Add red core/CLI contract tests for exact tagged stdout, diagnostic stderr, exit 0/1/2/3, and immutable attention-stage receipt behavior in `tests/v2/attention/test_core_cli_contract.py`
- [ ] T003 [P] Add red transition-policy tests in `tests/v2/attention/test_transition_policy.py`
- [ ] T004 [P] Add red advice, bypass, error, and continuation-secret projection tests in `tests/v2/attention/test_advice_and_errors.py`
- [ ] T005 [P] Create V2 attention replay runner in `evals/v2/attention/runner.py`

## Phase 2: User Story 1 - Participant-Shaped Attention Judgment (Priority: P1)

**Goal**: Produce one valid classifier disposition from one factual I-010A
request without composition or deterministic social rules.

**Independent Test**: Deterministic provider fixtures and replay produce only
SUPPRESS/WAKE/DEFER with valid evidence/advice rules and one logical judgment.

- [ ] T006 [US1] Replace the V1 classifier output boundary with participant-shaped V2 output in `src/nunchi/classifiers.py`
- [ ] T007 [US1] Implement I-010A validation, classifier-safe projection, one-judgment orchestration, and zero-call trusted preattention bypass in `src/nunchi/core.py`
- [ ] T008 [US1] Implement V2 runtime models without reply-bearing fields in `src/nunchi/models.py`
- [ ] T009 [P] [US1] Add false-suppression-scar corpus in `evals/v2/attention/suppression-scars/cases.jsonl`
- [ ] T010 [US1] Record deterministic judgment and scar/no-ledger replay results with mandatory S04/S16 `scene_id` values in `evidence/v2/attention/s04-suppression-scars/results.jsonl`

## Phase 3: User Story 2 - Governed Suppression and Dual DEFER (Priority: P1)

**Goal**: Apply only trusted, safety-widening delegation and transition policy
while keeping classifier and margin deferrals distinct.

**Independent Test**: Exhaustive transition/policy fixtures prove missing
legitimacy or malformed evidence never produces effective suppression.

- [ ] T011 [US2] Implement trusted effective-attention policy validation in `src/nunchi/schema.py`
- [ ] T012 [US2] Implement the allowed disposition transition matrix in `src/nunchi/core.py`
- [ ] T013 [US2] Implement separate classifier-DEFER and margin-DEFER audit in `src/nunchi/models.py`
- [ ] T014 [P] [US2] Add governed-suppression matrix in `evals/v2/attention/governed-suppression/cases.jsonl`
- [ ] T015 [P] [US2] Add dual-valve replay and canary analysis in `evals/v2/attention/defer-transition/analyze.py`
- [ ] T016 [US2] Record governed-suppression results in `evidence/v2/attention/s05-governed-suppress.jsonl`
- [ ] T017 [US2] Record separate DEFER-valve results and active-margin status with mandatory S08 `scene_id` values in `evidence/v2/attention/s08-defer-transition/results.jsonl`

## Phase 4: User Story 3 - Error, Receipt, and CLI Parity (Priority: P2)

**Goal**: Expose one tagged core/CLI seam with separate operational error and
off-surface lifecycle audit.

**Independent Test**: Core and CLI outputs match for valid input; every invalid
or failed path returns ERROR and the correct wake-default/override audit.

- [ ] T018 [US3] Implement I-010B ok/bypass/error response validation and immutable attention-stage I-010E validation in `src/nunchi/schema.py`
- [ ] T019 [US3] Replace V1 CLI handling with the exact I-030A stdout/stderr and exit 0/1/2/3 process contract in `src/nunchi/cli.py`
- [ ] T020 [US3] Remove V1 request/verdict and `require_pass_corroboration` paths from `src/nunchi/core.py`
- [ ] T021 [P] [US3] Add core/CLI ok, preattention-bypass, validation, invalid-input, provider/runtime, malformed-model, and projection parity corpus in `evals/v2/attention/core-cli/cases.jsonl`
- [ ] T022 [US3] Record core/CLI parity, bypass handoff, and error-fallback results with mandatory S06/S09/`030-CLI` `scene_id` values in `evidence/v2/attention/core-cli-parity.jsonl`

## Phase 5: Social Evidence, Documentation, and Handoff

- [ ] T023 Run the incumbent Gemini 3.1 Flash Lite, frontier GPT-5.5, and open-weight Qwen3 comparison (or an explicit later Zoe override) and record every attempt with mandatory scene IDs, exact provider IDs, provider/endpoint, prompt/config, date, and results in `evidence/v2/attention/model-comparison/results.jsonl`
- [ ] T024 Preregister the downstream live DEFER canary scenes, metrics, stop/retirement rules, owners, and immutable result paths in `evidence/v2/attention/defer-canary/protocol.md`; do not execute participant/live-room canaries in slice 030
- [ ] T025 Complete documentation freshness by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate each V2/V1-evidence `UPDATE`, route every shared and downstream `HANDOFF` delta (including `README.md`) to its accepting owner, and record all documentation dispositions, paths, results, and reviewer in `evidence/v2/attention/handoff.md`
- [ ] T026 Publish the scene-to-record command manifest in `evidence/v2/attention/README.md` and record commit, commands, I-030A/upstream versions, model/policy provenance, canary protocol, evidence, active margin, documentation dispositions/validation/reviewer, and limitations in `evidence/v2/attention/handoff.md`; handoff is blocked until documentation freshness passes

## Dependencies & Execution Order

- The accepted 010 commit is immutable input to all tasks.
- T001 precedes deterministic tests; T002–T004 must fail before T006–T013 are
  accepted.
- US1 establishes the classifier/core boundary used by US2 and US3.
- T014 and T015 may proceed in parallel after transition semantics are stable.
- T019/T020 follow runtime response validation; T023 requires the complete
  engine and explicit permission for provider calls, while T024 specifies
  downstream evidence without requiring a participant implementation.
- T026 requires all deterministic, replay, model, protocol, and documentation
  outputs. Slice 040 and later consumers start only after accepting it; live
  participant outcomes are explicitly not a 030 handoff prerequisite.

## Parallel Opportunities

- T002–T005 target separate ordinary paths.
- T009, T014, T015, and T021 are distinct corpus families after their respective
  interface prerequisites.
- Model comparison preparation, downstream canary protocol, and documentation
  may overlap deterministic evidence; surfaces and 110 execute live canaries
  only after the dependent lifecycle exists.

## Implementation Strategy

Make the one-judgment classifier seam valid first, then add the safety-widening
transition, then expose error/receipt/CLI parity. Treat margin retirement as a
separate evidence decision and stop on any pressure to encode a deterministic
social shortcut.

## Notes

- No task edits 010 schemas, 020 observation, 040 participant host, or any
  surface integration.
- No task creates a product artifact under a SpecKit-managed path.
- Unit tests do not close social-quality or downstream live-canary requirements.
