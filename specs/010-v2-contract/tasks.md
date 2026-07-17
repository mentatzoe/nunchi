# Tasks: V2 Contract

**Input**: `specs/010-v2-contract/spec.md` and `specs/010-v2-contract/plan.md`

**Slice state**: `PLANNED`

**Execution status**: `DORMANT` while the slice remains `PLANNED`

**Program implementation authority**: `GRANTED`

**Assigned participant / source**: cc-session-1 — evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted declared dependencies (none for this slice); an assigned
participant and durable external assignment source declared above;
active `v2-contract-owner`; zero CRITICAL/HIGH analysis findings; and an
isolated owner worktree

**Activation evidence**: `evidence/v2/contract/slice-activation.md`, written
only after every activation prerequisite is accepted; it copies and attests the
assignment declaration and all other prerequisite facts, establishing `READY`
before `ACTIVE` or any implementation checkbox

**Dependency evidence contract**: the activation record MUST use
`Accepted dependencies: none`, `Dependency commits: none`, and
`Dependency acceptance references: none`.

**Task manifest**: Run
`python3 scripts/check_governance.py --task-manifest specs/010-v2-contract`
and copy its exact `Initial task IDs` / `Initial tasks SHA256` into activation,
then its `Completed task IDs` / `Tasks SHA256` into each candidate attempt.

**Candidate evidence**: `evidence/v2/contract/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/contract/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/contract/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Rejection / rework**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

**Accountable owner lane**: `v2-contract-owner`

**Integration handoff**: all named downstream owners for slices `020` through
`110` and `v2-integrator`

**Slice activation**: No checkbox may begin while the slice is `PLANNED` or
before valid activation evidence attests the accepted prerequisites above and
establishes `READY`. The assigned participant must then declare `ACTIVE` before
beginning the first checkbox.

**Tests**: Contract tests are required and precede schema acceptance.

## Phase 1: Contract Harness

- [ ] T001 Create shared `Draft202012Validator` and stdlib-runtime corpus adapters — implementing the FR-012 expressiveness partition (dual-validator vs runtime-adapter-only case classes, per-class counts asserted) — pinned to dev/test-only `jsonschema==4.26.0` — the stdlib adapter always runs under the repo baseline; oracle absence yields explicit counted skips there and a loud failure only under the pinned dual-validator command — in `tests/v2/contract/schema_helpers.py`
- [ ] T002 [P] Add red request cases for exact identity (S01), actor mentions versus `mentions_room` (S02), duplicate event IDs and timestamp-versus-order disagreement (runtime-adapter-only) with the valid identical-text-distinct-ID case, classifier-safe continuation projection and bounded tail (S03), non-positive budgets (S15), and V1-envelope/reply-bearing/social-ledger rejection (S16, 010-V1) in `tests/v2/contract/test_attention_request.py`
- [ ] T003 [P] Add red ok/error/bypass decision cases — including forbidden classifier fields on `preattention-disabled` legacy-confidence-vector constraints (exactly the four `PASS`/`ACK`/`ASK`/`SPEAK` keys, finite values in [0,1], extra keys forbidden), and FR-013 advice red cases (advice on `DEFER`/`SUPPRESS`, advice citing nonexistent event IDs) — in `tests/v2/contract/test_attention_decision.py`
- [ ] T004 [P] Add red wake-source cases including advice-free `PREATTENTION_BYPASS` (010-Preattention-bypass), FR-013 advice-source violations, and non-positive participant budgets (S15) in `tests/v2/contract/test_participant_wake.py`
- [ ] T005 [P] Add red host-secret leakage, binding, immutable-stage, writer-ownership, and explicit unknown/unavailable cases in `tests/v2/contract/test_context_and_receipt.py`

## Phase 2: User Story 1 - Truthful Attention Request (Priority: P1)

**Goal**: Land `I-010A AttentionRequestV2@1` with exact identity, factual
events, honest coverage, and no social ledger.

**Independent Test**: `tests/v2/contract/test_attention_request.py` accepts
the valid scene matrix and rejects every enumerated identity, order, reference,
coverage, V1, and forbidden-field case.

- [ ] T006 [US1] Define `I-010A AttentionRequestV2@1` with distinct actor mentions, `mentions_room`, and host-only continuation metadata in `schemas/v2/attention-request.schema.json`
- [ ] T007 [P] [US1] Add request and classifier-projection conformance cases (S01, S02, S03) including duplicate-ID and timestamp-order relational red cases — proving opaque continuation fields never reach the classifier — plus V1-envelope and social-ledger red cases (S16, 010-V1), in `evals/v2/contract/attention-request/cases.jsonl`
- [ ] T008 [US1] Record exact-self (S01), native-relation (S02), bounded-context/gap (S03), budget (S15), projection, and S16/010-V1 rejection results with mandatory `scene_id` in `evidence/v2/contract/attention-request.jsonl`

## Phase 3: User Story 2 - Auditable Attention Decision (Priority: P1)

**Goal**: Land `I-010B AttentionDecisionV2@1` with the closed ok-transition
matrix, non-social preattention bypass, dual-valve audit, grounded advice, and
separate error branch.

**Independent Test**: `tests/v2/contract/test_attention_decision.py` proves only
four ok pairs validate, malformed transition evidence cannot support
suppression, and bypass validates only without a classifier/effective result.

- [ ] T009 [US2] Define `I-010B AttentionDecisionV2@1` ok/error/bypass union with exact `preattention-disabled` constraints in `schemas/v2/attention-decision.schema.json`
- [ ] T010 [P] [US2] Add — partitioned per FR-012 — transition (S09), governed-suppression (S05), dual-DEFER (S08), bypass (010-Preattention-bypass), malformed-output, FR-013 advice-rule, and reply-bearing/social-ledger rejection cases (S16) for both validators in `evals/v2/contract/attention-decision/cases.jsonl`
- [ ] T011 [US2] Record governed-suppression (S05), dual-DEFER (S08), transition/error (S09), bypass (010-Preattention-bypass), and S16 rejection results with mandatory `scene_id` in `evidence/v2/contract/attention-decision.jsonl`

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
- [ ] T015 [P] [US3] Add bypass wake (S06 contribution), participant-silence (S07), host-only binding, immutable receipt-stage, unknown/unavailable, and V1-envelope/reply-field/social-ledger rejection cases in `evals/v2/contract/downstream/cases.jsonl`
- [ ] T016 [US3] Record wake (S06), silence (S07), binding, staged-receipt, bypass-provenance (010-Preattention-bypass), and S16/010-V1 rejection results with mandatory `scene_id` in `evidence/v2/contract/downstream.jsonl`

## Phase 5: Documentation and Packet Inputs

- [ ] T017 Prepare documentation-freshness inputs by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate each `UPDATE`, re-verify each `NO_IMPACT` rationale against the exact candidate diff with its reviewed path, route each named `HANDOFF` delta (including `README.md`) to its accepting owner, and record all proposed documentation dispositions, paths, results, and reviewer in `evidence/v2/contract/handoff.md` for the later workflow gate
- [ ] T018 Run the exact offline dual-validator command, run `python3 scripts/check_governance.py` with no flags (boundary-only SC-006 verification; `--check-cli` is the separate pinned-CLI check), and create the S-ID-to-JSONL-record manifest covering all twelve scene rows (S01, S02, S03, S05, S06, S07, S08, S09, S15, S16, 010-Preattention-bypass, 010-V1) in `evidence/v2/contract/README.md`
- [ ] T019 Prepare the proposed packet input with the exact commit, commands, five interface versions and exact `schemas/v2/` paths, dual-validator pin/results over the shared corpus, staged-receipt writer map, scene-to-record evidence manifest, rejected-case inventory, migration/provenance notes, documentation dispositions/validation/reviewer, and known limitations in `evidence/v2/contract/handoff.md`; the later convergence, documentation-freshness, and handoff gates—not this checkbox—establish lifecycle state

## Dependencies & Execution Order

- T001 precedes T002–T005. Red tests T002–T005 may then proceed in parallel.
- US1 and US2 schema work may proceed in parallel after their red tests exist;
  neither edits the other's schema.
- US3 begins after the shared concepts used by I-010A and I-010B are stable.
- T017–T019 require all five interfaces, all Draft 2020-12 oracle checks, and
  every currently available stdlib runtime adapter check to pass. Each downstream
  runtime owner must close its adapter result over the identical corpus before
  its own handoff.
- Slices 020 and 030 may start implementation only after the lifecycle handoff
  packet derived from T019 is separately accepted and recorded by each consumer;
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
