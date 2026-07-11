# Tasks: V2 Contract

**Input**: `specs/010-v2-contract/spec.md` and `specs/010-v2-contract/plan.md`

**Prerequisites**: Zero CRITICAL/HIGH analysis findings, active
`v2-contract-owner`, and explicit Goal 2 authorization

**Accountable owner lane**: `v2-contract-owner`

**Integration handoff**: all named downstream owners for slices `020` through
`110` and `v2-integrator`

**Goal boundary**: Every checkbox below is future Goal 2 product work. All
tasks remain unchecked and MUST NOT begin under Goal 1.

**Tests**: Contract tests are required and precede schema acceptance.

## Phase 1: Contract Harness

- [ ] T001 Create shared `Draft202012Validator` and stdlib-runtime corpus adapters pinned to dev/test-only `jsonschema==4.26.0` in `tests/v2/contract/schema_helpers.py`
- [ ] T002 [P] Add red request cases for exact identity, actor mentions versus `mentions_room`, and classifier-safe continuation projection in `tests/v2/contract/test_attention_request.py`
- [ ] T003 [P] Add red ok/error/bypass decision cases, including forbidden classifier fields on `preattention-disabled`, in `tests/v2/contract/test_attention_decision.py`
- [ ] T004 [P] Add red wake-source cases including advice-free `PREATTENTION_BYPASS` in `tests/v2/contract/test_participant_wake.py`
- [ ] T005 [P] Add red host-secret leakage, binding, immutable-stage, writer-ownership, and explicit unknown/unavailable cases in `tests/v2/contract/test_context_and_receipt.py`

## Phase 2: User Story 1 - Truthful Attention Request (Priority: P1)

**Goal**: Land `I-010A AttentionRequestV2@1` with exact identity, factual
events, honest coverage, and no social ledger.

**Independent Test**: `tests/v2/contract/test_attention_request.py` accepts
the valid scene matrix and rejects every enumerated identity, order, reference,
coverage, V1, and forbidden-field case.

- [ ] T006 [US1] Define `I-010A AttentionRequestV2@1` with distinct actor mentions, `mentions_room`, and host-only continuation metadata in `schemas/v2/attention-request.schema.json`
- [ ] T007 [P] [US1] Add request and classifier-projection conformance cases, proving opaque continuation fields never reach the classifier, in `evals/v2/contract/attention-request/cases.jsonl`
- [ ] T008 [US1] Record exact-self, native-relation, gap, and projection results with mandatory `scene_id` in `evidence/v2/contract/attention-request.jsonl`

## Phase 3: User Story 2 - Auditable Attention Decision (Priority: P1)

**Goal**: Land `I-010B AttentionDecisionV2@1` with the closed ok-transition
matrix, non-social preattention bypass, dual-valve audit, grounded advice, and
separate error branch.

**Independent Test**: `tests/v2/contract/test_attention_decision.py` proves only
four ok pairs validate, malformed transition evidence cannot support
suppression, and bypass validates only without a classifier/effective result.

- [ ] T009 [US2] Define `I-010B AttentionDecisionV2@1` ok/error/bypass union with exact `preattention-disabled` constraints in `schemas/v2/attention-decision.schema.json`
- [ ] T010 [P] [US2] Add transition, bypass, and malformed-output cases for both validators in `evals/v2/contract/attention-decision/cases.jsonl`
- [ ] T011 [US2] Record transition, bypass, and error results with mandatory `scene_id` in `evidence/v2/contract/attention-decision.jsonl`

## Phase 4: User Story 3 - Participant Wake, Continuation, and Receipt (Priority: P2)

**Goal**: Land the three downstream contracts that keep factual wake delivery,
host-only bounded expansion, and immutable staged telemetry distinct.

**Independent Test**: Wake, continuation, and receipt contract tests validate
normal act-or-silence input including bypass, strict host-only handle binding,
and immutable singly written observation/attention/participant-host/transport
records correlated by request ID.

- [ ] T012 [P] [US3] Define `I-010C ParticipantWakeV2@1` with advice-free `PREATTENTION_BYPASS` in `schemas/v2/participant-wake.schema.json`
- [ ] T013 [P] [US3] Define host-only handle/binding/cursor semantics for `I-010D ContextContinuationV2@1` in `schemas/v2/context-continuation.schema.json`
- [ ] T014 [P] [US3] Define immutable request-correlated observation/attention/participant-host/transport stage records and bypass provenance for `I-010E AttentionReceiptV2@1` in `schemas/v2/attention-receipt.schema.json`
- [ ] T015 [P] [US3] Add bypass wake, host-only binding, immutable receipt-stage, and unknown/unavailable cases in `evals/v2/contract/downstream/cases.jsonl`
- [ ] T016 [US3] Record wake, binding, and staged-receipt results with mandatory `scene_id` in `evidence/v2/contract/downstream.jsonl`

## Phase 5: Documentation and Handoff

- [ ] T017 Complete documentation freshness by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate each `UPDATE`, route each named `HANDOFF` delta (including `README.md`) to its accepting owner, and record all documentation dispositions, paths, results, and reviewer in `evidence/v2/contract/handoff.md`
- [ ] T018 Run the exact offline dual-validator command and create the S-ID-to-JSONL-record manifest in `evidence/v2/contract/README.md`
- [ ] T019 Record exact commit, commands, interface versions, validator pin/results, receipt writer map, evidence manifest, provenance, documentation dispositions/validation/reviewer, and limitations in `evidence/v2/contract/handoff.md`; handoff is blocked until documentation freshness passes

## Dependencies & Execution Order

- T001 precedes T002–T005. Red tests T002–T005 may then proceed in parallel.
- US1 and US2 schema work may proceed in parallel after their red tests exist;
  neither edits the other's schema.
- US3 begins after the shared concepts used by I-010A and I-010B are stable.
- T017–T019 require all five interfaces, all Draft 2020-12 oracle checks, and
  every currently available stdlib runtime adapter check to pass. Each downstream
  runtime owner must close its adapter result over the identical corpus before
  its own handoff.
- Slices 020 and 030 may start implementation only after T019 is accepted;
  slice 040 additionally waits for their handoffs.

## Parallel Opportunities

- T002–T005 target separate test files.
- T007 and T010 target separate corpus directories.
- T012–T014 target separate schema files under the same sole owner.

## Implementation Strategy

First freeze the request and decision seams, then land downstream wake,
continuation, and receipt contracts. Stop on any unresolved contract ambiguity;
do not let a dependent implementation silently define the shared interface.

## Notes

- Only `v2-contract-owner` edits `schemas/v2/**` during this slice.
- No task creates a product artifact under `specs/` or `.specify/`.
- A green schema suite proves contract mechanics, not social judgment quality.
- `jsonschema==4.26.0` is available only to dev/test commands; shipped runtime
  validation remains explicit stdlib code.
