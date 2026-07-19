# Tasks: V2 Observation

**Input**: `specs/020-v2-observation/spec.md` and
`specs/020-v2-observation/plan.md`

**Slice state**: `ACTIVE`

**Execution status**: stated by reference rather than as a fixed transition claim —
unchecked tasks execute only inside this slice's bound `run speckit` run while
the transition-updated `Slice state` declaration above and immutable activation
evidence establish `ACTIVE`; they are `DORMANT` under every other established
state, including `PLANNED`

**Program implementation authority**: `GRANTED`

**Assigned participant / source**: Aleph — evidence/governance/assignments/aleph-v2-observation-owner-2026-07-16.md

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted declared dependency `010-v2-contract`; the
assigned participant and durable external assignment source declared above;
active `v2-observation-owner`; zero CRITICAL/HIGH analysis findings; and the
isolated `.worktrees/v2-observation/` worktree on `v2/observation`

**Activation evidence**: `evidence/v2/observation/slice-activation.md`, written
only after every activation prerequisite is accepted; it copies and attests the
assignment and dependency facts, exact interfaces/scenes/evidence/docs scope,
and the frozen initial task manifest, establishing `READY` before `ACTIVE` or
any implementation checkbox

**Task manifest**: before activation, run
`python3 scripts/check_governance.py --task-manifest specs/020-v2-observation`
and copy its exact `Initial task IDs` and `Initial tasks SHA256` into
`evidence/v2/observation/slice-activation.md`; copy the exact completed manifest
fields into each later candidate attempt

**Candidate evidence**: `evidence/v2/observation/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/observation/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/observation/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Accountable owner lane**: `v2-observation-owner`

**Integration handoff**: `v2-wake-owner` (040), `v2-transport-owner` (050),
`v2-hermes-owner` (060), `v2-claude-owner` (070), `v2-codex-owner` (080),
`v2-adapters-owner` (090), `v2-security-owner` (100), and `v2-integrator`
(110)

**Tests**: deterministic contract/mechanics tests and reusable replay scenes
are required; tests must fail before the corresponding provider, continuation,
or reference behavior is accepted

## Upstream Handoff Inputs

The readiness review consumes the accepted `010-v2-contract` candidate
`bff6b463a44c1b9066fc654691042f9550da6c64`, packet commit
`39deb459c7fb18cf7d64dc0edaaaadcca39eae20`, append-only packet record
`evidence/v2/contract/slice-handoff.md`, and terminal acceptance record
`evidence/v2/contract/slice-acceptance.md`. Aleph's separate consumer decision
must be recorded under the observation evidence directory in an exact filename
containing `010`, such as
`evidence/v2/observation/dependency-acceptance-010.md`, and the immutable
activation record must map `010` to the accepted candidate and that consumer-
owned reference.

Implementation consumes these accepted contract files without modifying them:

- `schemas/v2/attention-request.schema.json` (`I-010A`)
- `schemas/v2/context-continuation.schema.json` (`I-010D`)
- `schemas/v2/attention-receipt.schema.json` (`I-010E` staged-record shape)
- `docs/contracts/nunchi-v2.md`
- `tests/v2/contract/schema_helpers.py`

`docs/contracts/nunchi-v2.md` is an evidence-backed `NO_IMPACT` disposition:
slice 020 consumes the accepted closed I-010A/I-010D/I-010E shapes and validates
the document without editing it. The accepted I-010E observation body has no
token field; token-size proxy results therefore live only in separate evidence
and the limitation is handed to `v2-contract-owner` and `v2-integrator`.

## Correction and Rejection Preservation

This is the initial dormant task graph; there is no slice-020 correction or
rejection record to append from. Once activation freezes this manifest, an
`ACTIVE` correction or recorded rejection must preserve every existing task and
checkbox exactly and append only new sequential tasks. Each appended phase and
task must cite the durable correction/review path and finding ID that requires
it. A convergence-added graph or completed-handoff rejection starts a new bound
`run speckit`; only a paused post-convergence fix with an unchanged graph may
resume its current run. Candidate and handoff attempts remain append-only.

## Phase 1: Shared Test and Replay Setup

**Purpose**: Create transport-neutral helpers used by every independently
testable story without adding a native surface binding.

- [X] T001 [P] Create reusable observation fixture, assertion, serialized-byte, and `utf8-bytes-ceil-div4@1` evidence-only token-size proxy helpers in `tests/v2/observation/helpers.py`; emit `estimator_id`, `estimated_tokens`, `serialized_bytes`, and `model_id: null`, and make no model-tokenizer claim
- [X] T002 [P] Create the authoritative-order native-shape replay loader in `evals/v2/observation/replay.py`
- [X] T003 [P] Create the capability-aware shared/reference observation comparator for downstream reuse in `evals/v2/observation/compare.py`
- [X] T004 [P] Create the exact-attempt-6 corpus loader and test driver for slice 020's own stdlib validation adapter, covering accepted I-010A, I-010D, and I-010E inputs while accounting explicitly for every case in the identical `bff6b463a44c1b9066fc654691042f9550da6c64` corpus revision, in `tests/v2/observation/contract_helpers.py`

**Checkpoint**: Tests and replay cases can describe accepted contract inputs,
native facts, budgets, and evidence rows without importing a native transport.

## Phase 2: Foundational Contract Tests

**Purpose**: Freeze the accepted upstream boundary before implementing any user
story.

**Critical**: This phase blocks every story implementation.

- [X] T005 Add red contract tests for exact accepted I-010A request output including its optional continuation capability, I-010D fetch-request/fetch-page documents through the separate host fetch seam, immutable observation-stage I-010E output with no token field, unknown later-stage facts, and rejection of contract drift in `tests/v2/observation/test_contract_inputs.py`

**Checkpoint**: The accepted 010 schemas fail against the still-missing I-020A
provider for the intended reasons; no 010-owned file has changed.

## Phase 3: User Story 1 - Native Facts and Exact Self (Priority: P1) MVP

**Goal**: Preserve exact transport-attested self identity, stable actors,
literal native relations, narrow transport hygiene, and outcome-neutral bounded
observation.

**Independent Test**: Native-shape fixtures preserve exact actor identity and
literal relations, distinguish actor-targeted from room-wide mentions, retain
self events without waking their author, and permit only exact duplicate,
exact-self, and transport-attested unroutable mechanical no-wake actions
without invoking an attention model or independently deciding routing.

### Tests for User Story 1

- [X] T006 [P] [US1] Add red provider tests for exact-self alias collisions, actor-targeted mentions, room-wide mentions, replies, threads, reactions, memberships, honest unavailable facts, authoritative order, exact delivery deduplication, and consumption of transport-attested `candidate-event`/`unroutable` inputs without independently deciding routing in `tests/v2/observation/test_provider.py`
- [X] T007 [P] [US1] Add red tests for outcome-neutral bounded retention, request correlation, singly attested immutable observation-stage receipts, and operational-error treatment after routable native-event construction in `tests/v2/observation/test_storage_and_receipt.py`

### Implementation for User Story 1

- [X] T008 [US1] Implement the I-020A provider boundary plus slice 020's stdlib-only I-010A/I-010E runtime-validation and serialization boundary in `src/nunchi/observation.py`
- [X] T009 [US1] Implement factual actor/event normalization with exact self binding, stable native order, distinct actor-targeted and room-wide mention facts, literal relations, and honest unknowns in `src/nunchi/observation.py`
- [X] T010 [US1] Implement bounded outcome-neutral retention and mechanical handling limited to exact delivery duplicate, exact-self retain-without-wake, and transport-attested `unroutable` cases in `src/nunchi/observation.py`; require routing/authorization provenance on `candidate-event` input and never derive it from payload content
- [X] T011 [P] [US1] Add exact-self, relation, unavailable-fact, transport-hygiene, operational-error, and no-social-ledger cases for S01, S02, S04, S11, and S16 in `evals/v2/observation/identity-and-hygiene/cases.jsonl`
- [X] T012 [US1] Run the US1 contract/provider/receipt suites and record request-correlated S01, S02, S04, S11, and S16 results with serialized sizes and mandatory `scene_id` values in `evidence/v2/observation/identity-and-hygiene.jsonl`

**Checkpoint**: User Story 1 passes independently and provides the factual
provider/retention seam used by later stories without claiming native-surface
conformance.

## Phase 4: User Story 2 - Bounded Snapshot and Expansion (Priority: P1)

**Goal**: Assemble trigger-first factual snapshots under hard limits and expose
truthful participant/room/scope/trigger-bound I-010A continuation capability
plus a separate I-010D fetch seam. Slice 030—not this slice—owns the
classifier-visible projection and redaction of opaque authority.

**Independent Test**: Multiple event/byte/age budgets and before/after/around
queries preserve authoritative order, trigger inclusion, fitting relation
closure, known gaps, exact-event deduplication, binding, expiry, cursors, and
operator caps; the provider emits only accepted I-010A/I-010D shapes and hands
their projection obligation to the slice-030 owner.

### Tests for User Story 2

- [X] T013 [US2] Add red hard-budget, relation-closure, coverage, accepted I-010A capability shape, I-010D fetch-document, continuation binding, expiry, cursor, authoritative-order, and exact-event deduplication tests in `tests/v2/observation/test_budget_and_continuation.py`; do not test slice-030 classifier projection behavior here

### Implementation for User Story 2

- [X] T014 [US2] Implement trigger-first snapshot assembly, fitting relation closure, nearby context fill, authoritative order, and honest event/byte/age truncation coverage in `src/nunchi/observation.py`
- [X] T015 [US2] Implement optional host-owned before/after/around continuation with an accepted I-010A capability plus a separate stdlib-validated I-010D request/page seam, participant/room/continuity/trigger binding, capped fetches, and exact merge deduplication in `src/nunchi/observation.py`; leave classifier projection/redaction to slice 030
- [X] T016 [P] [US2] Add S03/S15 event, byte, age, relation-fit, gap, accepted-I-010E byte, and separately labelled `utf8-bytes-ceil-div4@1` proxy matrices in `evals/v2/observation/budgets/cases.jsonl`
- [X] T017 [P] [US2] Add S03/S15 cross-binding, redirect, over-limit, expiry, cursor-replay, order, duplicate-content, and exact-event continuation attacks in `evals/v2/observation/continuation/cases.jsonl`
- [X] T018 [P] [US2] Run the budget matrix and record configured caps, serialized bytes, accepted-I-010E byte telemetry, separate `estimator_id`/`estimated_tokens`/`serialized_bytes`/`model_id: null` proxy evidence, included/omitted event IDs, relation outcomes, and mandatory S03/S15 `scene_id` values in `evidence/v2/observation/budget-sweep.jsonl`
- [X] T019 [P] [US2] Run the continuation attack matrix and record binding, accepted I-010A/I-010D shape, cap, expiry, cursor, order, coverage, and deduplication outcomes with mandatory S03/S15 `scene_id` values in `evidence/v2/observation/continuation.jsonl`; record projection/redaction as a slice-030 obligation, not a 020 result

**Checkpoint**: User Story 2 passes independently over the shared provider and
proves bounded assembly/expansion mechanics while leaving classifier-safe
projection/redaction explicitly unimplemented and owned by slice 030.

## Phase 5: User Story 3 - Recoverability and Comparison References (Priority: P2)

**Goal**: Supply reusable reference variants and a comparator that downstream
owners can apply to real surfaces without turning reference evidence into a
surface, restart-safety, suppression-eligibility, or parity claim.

**Independent Test**: Restart-safe, session-only, unknown, known-gap, live-only,
unavailable-event, and continuation capability variants produce the declared
recoverability outcome, while equivalent supplied facts/budgets/capabilities
compare equal except for explicitly unavailable native facts.

### Tests for User Story 3

- [X] T020 [P] [US3] Add red restart/backfill, outcome-neutral later-hearing, session-only, unknown, known-gap, and suppression-eligibility reference tests in `tests/v2/observation/test_recoverability.py`
- [X] T021 [P] [US3] Add red reference-equivalence and reusable downstream comparator-contract tests in `tests/v2/observation/test_equivalence.py`

### Implementation for User Story 3

- [X] T022 [P] [US3] Add restart-safe, session-only, unknown, known-gap, history/live visibility, unavailable-event, and continuation capability cases for S05/S13 in `evals/v2/observation/capabilities/cases.jsonl`
- [X] T023 [US3] Implement simulated restart/backfill and capability variants outside product runtime code in `evals/v2/observation/capabilities/reference_provider.py`
- [X] T024 [P] [US3] Run the reference recoverability suite and record exact content/actor retention, restart/backfill, ordinary later-hearing, capability, limitation, and eligibility outcomes for S05 in `evidence/v2/observation/s05-recoverability.jsonl`
- [X] T025 [P] [US3] Run the reference comparator and record normalized equivalence plus every capability-explained difference for S13 in `evidence/v2/observation/s13-equivalence.jsonl`

**Checkpoint**: User Story 3 passes independently as a reference contract;
every real-surface proof remains an explicit downstream obligation.

## Phase 6: Documentation Impact and Freshness with Exact Claim Handoffs

**Purpose**: Execute every exact documentation disposition before the candidate
can be handed off. Global/current-state and downstream-owner docs remain
handoffs; slice-owned observation documentation lands with this candidate.

- [X] T026 Create or update the owned `UPDATE` surface with evidence-proven I-020A identity, literal native relations, authoritative order, hard budgets, gaps/unknowns, outcome-neutral retention, continuation binding/authority, capability truth, reference-only limitations, links, and runnable examples in `docs/observation/v2.md`
- [X] T027 Add documentation truthfulness tests that execute every Python example and assert the documented contract versions, budget/coverage behavior, I-010A/I-010D ownership boundary, capability limits, accepted-I-010E token-field limitation, and reference-only claim boundary in `tests/v2/observation/test_docs.py`
- [X] T028 Record the `README.md` `HANDOFF` to accepting `v2-integrator`: at atomic cutover add only proven exact-self, literal-native-relation, trigger-first hard-budget, gap/unknown, outcome-neutral retention, and optional host-bound continuation claims while preserving V1-current wording until cutover verification, in `evidence/v2/observation/handoff.md`
- [X] T029 Record exact `HANDOFF` deltas to accepting `v2-integrator` for breaking I-020A/current-state wording in `CHANGELOG.md` and `docs/STABILITY.md`, request/identity/relation/order/budget/gap/continuation integration wording in `docs/integration.md` and `docs/adapters.md`, and the observation/host-only-continuation diagram boundary in `docs/architecture/v2-selected-design.md`; in the same `evidence/v2/observation/handoff.md`, hand I-010A expansion-availability input to `v2-attention-owner` while stating that slice 030 alone implements classifier-safe projection/redaction in `src/nunchi/core.py`
- [X] T030 Record exact I-020A identity/native-fact/order/budget/gap/continuation `HANDOFF` deltas for `integrations/mcp-discord/README.md` and `integrations/mcp-discord/DESIGN.md` to accepting `v2-transport-owner` in `evidence/v2/observation/handoff.md`
- [X] T031 Record the exact I-020A identity/native-fact/order/budget/gap/continuation `HANDOFF` delta for `integrations/hermes/README.md` to accepting `v2-hermes-owner` in `evidence/v2/observation/handoff.md`
- [X] T032 Record the exact I-020A identity/native-fact/order/budget/gap/continuation `HANDOFF` delta for `integrations/claude-code/README.md` to accepting `v2-claude-owner` in `evidence/v2/observation/handoff.md`
- [X] T033 Record the exact I-020A identity/native-fact/order/budget/gap/continuation `HANDOFF` delta for `integrations/codex/README.md` to accepting `v2-codex-owner` in `evidence/v2/observation/handoff.md`
- [X] T034 Run `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_docs` and `python3 scripts/check_governance.py --check-cli`, execute every command in `docs/observation/v2.md`, validate every local link, validate the evidence-backed `NO_IMPACT` disposition for `docs/contracts/nunchi-v2.md` against accepted I-010A/I-010D/I-010E, record `N/A` if the owned document has no Mermaid block or render every block if present, and record exact `UPDATE`/`NO_IMPACT`/`HANDOFF` paths, validation results, accepting owners, and reviewer in `evidence/v2/observation/handoff.md`

**Checkpoint**: The owned observation guide is updated and validated; every
other affected path has an exact delta, accepting owner, reviewer, and result
rather than a generic defer or premature current-state edit.

## Phase 7: Evidence Manifest, Verification, and Handoff Inputs

**Purpose**: Assemble exact ordinary-path inputs for convergence,
documentation freshness, and the owner handoff without fabricating those later
lifecycle decisions.

- [X] T035 Publish the scene-to-record/command manifest for S01, S02, S03, S04, S05, S11, S13, S15, and S16, I-020A capability rules, exact downstream comparator/recoverability obligations, the accepted-I-010E token-field limitation, the exact slice-030 classifier-projection handoff, and the reference-only suppression-eligibility boundary in `evidence/v2/observation/README.md`
- [X] T036 Run `PYTHONPATH=src python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'`, the observation replay/evaluation commands named in `evidence/v2/observation/README.md`, `PYTHONPATH=src python3 -m unittest`, `python3 -m evals.verdict_suite.runner --list`, and `python3 scripts/check_governance.py --check-cli`, then record exact commands, nonzero discovered test counts, results, candidate provenance, and any limitation in `evidence/v2/observation/handoff.md`
- [X] T037 Run slice 020's own stdlib runtime-validation adapter in `src/nunchi/observation.py` through the driver in `tests/v2/observation/contract_helpers.py` over the complete identical attempt-6 corpus revision `bff6b463a44c1b9066fc654691042f9550da6c64` (202 cases, including all seven runtime-adapter-only semantic/relational classes); validate consumed interfaces, explicitly account for non-consumed interface cases rather than silently skipping them, fail on corpus identity or expected-count drift, and record exact command, revision, per-class counts, and result in `evidence/v2/observation/handoff.md`
- [X] T038 Prepare the exact proposed owner-handoff input with candidate commit, upstream 010 candidate/packet references, completed task IDs and normalized task SHA256, I-020A version, consumed I-010A/I-010D/I-010E versions and schema paths, accepted-I-010E token-field limitation plus separate estimator provenance, shared/reference module paths, test/eval commands and results, exact attempt-6 downstream-adapter conformance result, evidence paths, all documentation dispositions/validation/reviewer records, the exact `v2-attention-owner` projection handoff, downstream comparator/recoverability/provenance obligations, recipients, and known limitations in `evidence/v2/observation/handoff.md`; later convergence, documentation-freshness, and handoff gates append lifecycle attempts and establish state

## Dependencies and Execution Order

### Pre-task lifecycle dependencies

- Every task is dormant until Aleph separately accepts the exact 010 packet,
  records the consumer-owned dependency decision, the bound delivery workflow
  proves zero CRITICAL/HIGH findings and all readiness facts, immutable
  activation evidence freezes this manifest, and the slice declares `ACTIVE`.
- The accepted 010 candidate, packet, schemas, and contract helpers listed in
  **Upstream Handoff Inputs** are immutable inputs to every phase.

### Phase dependencies

- Phase 1 has no product-code dependency after activation.
- T005 depends on T004 and blocks every user story implementation.
- US1 tests T006/T007 must fail before T008-T010 are accepted; T012 requires
  T006-T011 to pass.
- US2 starts after the US1 provider/retention seam is stable; T013 must fail
  before T014/T015 are accepted; T018/T019 require their matching corpora and
  passing suite.
- US3 uses the completed US1/US2 provider, continuation, and comparator seams;
  T020/T021 must fail before T023 is accepted; T024/T025 require the matching
  capability cases and passing suites.
- Documentation tasks T026-T034 require the exact complete story behavior and
  evidence. T034 blocks the packet phase.
- T035 requires all scene evidence. T036 requires T026-T035. T037 requires the
  implemented runtime adapter plus T004 and T036 and blocks handoff. T038
  requires every prior task and supplies inputs to the later lifecycle gates.

### Parallel opportunities

- T002-T004 target independent setup files and may run in parallel after
  activation.
- T006/T007 and T011 target separate test/eval paths and may proceed in parallel
  after T005.
- T016/T017 may proceed in parallel; T018/T019 may run in parallel once the
  shared US2 implementation passes.
- T020-T022 may proceed in parallel; T024/T025 may run in parallel after T023.
- Documentation handoff tasks T028-T033 share one evidence file and therefore
  remain ordered even though their accepting owners differ.

## Parallel Examples

### User Story 1

After T005, prepare T006, T007, and T011 concurrently; then implement T008-T010
in order and converge their results in T012.

### User Story 2

After the red T013 result, implement T014/T015 in order while preparing T016
and T017 concurrently; run T018 and T019 concurrently after the code/corpora
stabilize.

### User Story 3

Prepare T020, T021, and T022 concurrently; implement T023 against those red
contracts, then run T024 and T025 concurrently.

## Implementation Strategy

The MVP is Phase 1, Phase 2, and User Story 1: one factual provider that proves
exact identity, native structure, narrow transport hygiene, immutable
observation-stage receipts, and outcome-neutral bounded retention. Continue
with bounded expansion, then reference recoverability/equivalence, and converge
one complete slice candidate. No intermediate story, reference provider, or
slice state authorizes a native-surface claim, integration, deployment,
release, promotion, or cutover.

## Handoff Input Contract

The proposed packet assembled by T038 is complete only when it names:

- the exact candidate commit and frozen/completed task manifests;
- the accepted 010 candidate and packet plus I-010A/I-010D/I-010E versions,
  the closed-I-010E token-field limitation, and separate estimator provenance;
- `src/nunchi/observation.py`, every shared/reference test and eval path, and
  every committed evidence path;
- reproducible commands and exact results;
- every exact documentation `UPDATE` or `HANDOFF`, validation result, accepting
  owner, and reviewer, including the `README.md` delta;
- capability, recoverability, comparator, installed-surface, and final-parity
  obligations for each of the eight declared downstream recipients —
  `v2-wake-owner` (040), `v2-transport-owner` (050), `v2-hermes-owner` (060),
  `v2-claude-owner` (070), `v2-codex-owner` (080), `v2-adapters-owner` (090),
  `v2-security-owner` (100), and `v2-integrator` (110) — matching the
  **Integration handoff** declaration above and `spec.md`'s declared `Feeds`
  list, plus slice 030's (`v2-core-owner`) sole classifier-safe
  projection/redaction ownership; and
- known limitations, especially that reference variants prove no real surface,
  restart-safe deployment, social-suppression eligibility, or cross-surface
  parity.

The bound workflow later appends the exact candidate and handoff lifecycle
records. The task checkbox alone does not establish `CONVERGED`,
`HANDOFF_READY`, or `ACCEPTED`.

## Notes

- No task edits 010-owned schemas, native transport sources, or 040/050/060-110
  integration entrypoints.
- No task creates a product artifact under a SpecKit-managed path.
- Outcome-neutral retention must be testable without a live classifier.
- Restart/backfill simulations live only in tests/evals; actual persistence and
  native-history behavior remain owned by downstream surfaces.
- No handoff task edits global current-state wording before its accepting owner
  applies the delta at the governed atomic cutover.

## Phase 8: Convergence

**Correction source**: `evidence/v2/observation/convergence-2026-07-19.md`
findings C020-01 HIGH, C020-02 HIGH, C020-03 HIGH, C020-04 MEDIUM,
C020-05 MEDIUM, and C020-06 LOW.

**Purpose**: Close gaps found by `/speckit-converge` between the accepted
spec/plan/tasks and the completed T001–T038 candidate. Appending these tasks
keeps the slice `ACTIVE`; per the Rejection/Rework contract and the
Correction and Rejection Preservation section above, completing them requires
a new bound `python3 scripts/run_slice_workflow.py run speckit
specs/020-v2-observation` run rather than resuming the completed T001–T038
delivery run.

- [X] T039 Document native `reaction` and `membership` event ingestion in `docs/observation/v2.md` — add a runnable example and description of literal relations (e.g. reaction `target_event_id`, membership operation) and honest-unavailability representation for both event kinds alongside the existing `message`-event coverage, and extend `tests/v2/observation/test_docs.py` to assert their presence, per FR-003 / plan.md Acceptance Scene S02 (partial)
- [X] T040 Add RED→GREEN coverage in `tests/v2/observation/test_provider.py` proving a membership event with `caused_by_actor_id == self.actor_id` is retained as `SELF_RETAINED_NO_WAKE`, while an event where self appears only as `subject_actor_id` remains ordinary `OBSERVED`; implement the exact-causation check in `src/nunchi/observation.py` and document the resolved scope in `docs/observation/v2.md`, per FR-004 and D020-01/M020-02 in `evidence/v2/observation/convergence-2026-07-19.md`
- [X] T041 Add RED→GREEN test/eval coverage proving configured `event_visibility` appears consistently in both `ObservationProvider.snapshot()` and `ContinuationProvider.fetch()` coverage (and is absent when unavailable); implement missing fetch propagation if the red test exposes it, then record exact outcomes in `evidence/v2/observation/budget-sweep.jsonl`, per FR-007 and M020-04 in `evidence/v2/observation/convergence-2026-07-19.md`
- [X] T042 Correct the inaccurate "four-line addition" diff-size claim for the `tests/test_governance.py` fix in `evidence/v2/observation/handoff.md`'s Known Limitations section to match the actual 9-insertion diff (`git diff --stat tests/test_governance.py`), per FR-013 / Constitution VI Evidence Before Claims (contradicts)
- [X] T043 Name `v2-wake-owner` (040), `v2-adapters-owner` (090), and `v2-security-owner` (100) as explicit recipients of the T038 handoff packet in `evidence/v2/observation/handoff.md`, consistent with `spec.md`'s declared `Feeds` list, per tasks.md Handoff Input Contract "recipients" element (partial)
- [X] T044 Explain the `restart-safe`/`session-only`/`unknown`/`known-gap` capability vocabulary (what each means and how a consumer should read a `known-gap` result) in `docs/observation/v2.md`'s reference-variant section, per FR-011 / plan.md T026 "capability truth" (partial)

## Phase 9: Plan-Correction — Downstream Handoff Recipient Naming Accuracy

**Correction source**: `evidence/v2/observation/convergence-2026-07-19.md`
findings P020-01 HIGH, A020-F1 HIGH, A020-F2 HIGH, and A020-F3 MEDIUM.

**Purpose**: Close the naming defect identified by the 2026-07-19 plan.md
replanning-pass correction to the Owner Handoff section, durably recorded as
P020-01 in the correction source above. No owner lane named
`v2-attention-owner` exists
anywhere in the repository — confirmed against `README.md`,
`specs/030-v2-core-attention/plan.md`, `specs/001-nunchi-v2-program/`, and
`docs/governance/execution-spine.md`; slice `030`'s only accountable owner
lane is `v2-core-owner`. T029 and T038's completed evidence/doc output
recorded the wrong name before this correction existed and remain unedited
per the Correction and Rejection Preservation contract above; this phase
appends the fix rather than rewriting that history.

- [X] T045 Add a red assertion in `tests/v2/observation/test_docs.py` that
  `docs/observation/v2.md`'s classifier-safe-projection/redaction paragraph
  (under "What this slice does not do") names the real `v2-core-owner` lane
  for the `I-010A` expansion-availability handoff to slice `030`, and never
  the nonexistent `v2-attention-owner` name; in the same red test, assert that
  `evidence/v2/observation/handoff.md` contains zero literal
  `v2-attention-owner` occurrences and names `v2-core-owner`, per P020-01 and
  A020-F2 in `evidence/v2/observation/convergence-2026-07-19.md`
- [X] T046 Fix the incorrect downstream-recipient lane name
  `v2-attention-owner` to the correct `v2-core-owner` in
  `docs/observation/v2.md` ("What this slice does not do" section) and
  `evidence/v2/observation/handoff.md` (`## Documentation dispositions
  (T028–T034)` → `### HANDOFF (accepting owner named per row...)` and
  `### Documentation dispositions, validation, and reviewer`), until T045
  passes, per P020-01 and A020-F2 in the correction source (no
  `v2-attention-owner` lane exists; slice 030's owner lane is
  `v2-core-owner` per `README.md` and `specs/030-v2-core-attention/plan.md`)

### Phase 9 dependencies

- T039 and T044 must complete before T045 begins because they share
  `docs/observation/v2.md`; T045 then must fail before T046 is accepted.
- T046 runs after T045 and after T043/T044 because it shares
  `evidence/v2/observation/handoff.md` and documentation-recipient content.

**Checkpoint**: `docs/observation/v2.md` and
`evidence/v2/observation/handoff.md` name only real, currently declared
owner lanes for every downstream handoff, and T045's regression assertion
prevents the wrong name from silently returning.

## Phase 10: Independent Pre-Review Rework and Accepted-Contract Rebind

**Correction sources**:
`evidence/v2/observation/pre-review-2026-07-19-sr-critic.md` and
`evidence/v2/observation/convergence-2026-07-19.md` findings H020-01 HIGH,
M020-01 through M020-04 MEDIUM, L020-01 LOW, and D020-01 RESOLVED. The accepted
upstream version rebind is recorded separately in
`evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`.

**Purpose**: Close the independently reproduced cursor defect, finish truthful
continuation coverage, supersede stale evidence claims without rewriting
historical records, and bind the accepted I-010E `@2` amendment before a new
candidate is proposed.

- [X] T047 Add RED regression tests in `tests/v2/observation/test_budget_and_continuation.py` and a named adversarial case in `evals/v2/observation/continuation/cases.jsonl` proving a cursor minted for `before` cannot be replayed as `after` (or vice versa) under the same handle and cannot return an event already served by the prior page, reproducing H020-01
- [X] T048 Make continuation cursors direction-bound in `src/nunchi/observation.py` (or reject an exact direction mismatch before page selection), preserve same-direction pagination, update serialized cursor evidence, and make T047 plus the complete continuation suite pass without weakening cross-handle/binding/expiry/cap checks
- [X] T049 Add RED tests in `tests/v2/observation/test_budget_and_continuation.py` for truncated `around` fetches that require truthful boolean `has_more_before` and `has_more_after` side coverage instead of two nulls, reproducing L020-01
- [X] T050 Implement truthful side-specific `around` coverage in `src/nunchi/observation.py`, update the matching continuation eval/evidence rows, and make T049 plus all existing before/after/around budget and ordering tests pass
- [X] T051 Append a superseding convergence section to `evidence/v2/observation/handoff.md` that distinguishes the immutable T001–T038 activation-prefix SHA from the final full-manifest SHA, replaces the stale 11-skip current claim with the exact re-run result without rewriting the historical T038 text, and cites M020-01/M020-03 plus the exact commands used
- [X] T052 Update current slice-owned documentation and handoff/evidence citations from I-010E `@1` to accepted I-010E `@2`, cite exact amendment candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`, integrator acceptance `30aba09f13a6752b4c24811da0d8ec772a9d9682`, and `evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`; preserve completed attempt-6 history and state explicitly that `observationBody` is unchanged and no implementation change was owed by the version rebind
- [X] T053 Run the complete observation tests, scene replay/evals, full repository suite, verdict fixture discovery, governance CLI, task-manifest check, and `git diff --check`; record exact nonzero counts/results and all T039–T052 correction receipts in the append-only current handoff section before convergence review

### Phase 10 dependencies

- T047 must fail before T048 is accepted; T049 must fail before T050 is
  accepted.
- T051 and T052 run after T039–T050 so their current-state evidence captures
  the complete correction tree rather than an intermediate manifest or result.
- T053 is last and blocks `/speckit-converge`.

**Checkpoint**: cross-direction cursor replay rejects without duplicate
delivery, all continuation coverage is truthful, I-010E `@2` is explicitly
consumer-bound, and the append-only handoff's current section matches every
re-runnable command and final task identity.

## Phase 11: Convergence

**Correction source**:
`evidence/v2/observation/convergence-phase11-2026-07-19.md`, finding F1
CRITICAL, reproduced live against the completed T001–T053 candidate tree at
`77a94cf1f56e70d1f0a79631ee9efba0b6e74a62`.

**Purpose**: Close a residual honesty defect in the Phase 10 (T049/T050)
"truthful side-specific `around` coverage" fix that neither its new unit test
nor its new eval case exercises.

- [X] T054 Fix a false-negative `has_more_before` in `ContinuationProvider.fetch`'s
  `around` branch in `src/nunchi/observation.py`: `has_more_before =
  around_window_start > 0` ignores cap-based truncation that lands at a
  candidate index strictly before `anchor_index`, so a per-fetch event/byte
  cap that cuts the scan off before reaching the anchor reports
  `has_more_before: False` even though an unserved before-anchor event
  remains (reproduced: 5 events e1–e5, anchor `e3` at index 2,
  `max_events_per_fetch=6` giving radius 3 and `around_window_start=0`,
  `max_bytes_per_fetch` sized to admit only `e1` — the page serves only
  `['e1']` yet reports `has_more_before: False` although `e2`, a genuine
  before-anchor event, was never served). Track whether the cap actually
  truncated the scan at a candidate index `< anchor_index` (before-side) or
  `>= anchor_index` (at-or-after-side), and OR that fact into
  `has_more_before`/`has_more_after` respectively, alongside the existing
  window-boundary checks (`around_window_start > 0` /
  `around_window_end < len(events)`). Add a RED→GREEN regression test in
  `tests/v2/observation/test_budget_and_continuation.py` reproducing the
  exact scenario above (a cap-truncation index strictly less than
  `anchor_index` while `around_window_start == 0`) and a matching
  adversarial case in `evals/v2/observation/continuation/cases.jsonl` with
  its result recorded in `evidence/v2/observation/continuation.jsonl`; append a
  Phase 11 supersession to `evidence/v2/observation/handoff.md` recording the
  final T001–T054 full-manifest SHA, the T054 receipt, and exact rerun results
  for the complete T053 verification matrix so the act of appending T054 does
  not leave the handoff stale, per FR-007, SC-002, Constitution III ("honest
  coverage and gap facts"), Constitution VI, and plan.md Acceptance Scene S03
  ("gaps are truthful") (contradicts)

### Phase 11 dependencies

- T054 must add a failing regression test before the fix, then pass it plus
  the complete existing continuation/budget suite (including T047–T050's
  cross-direction and side-specific coverage tests) without weakening any
  existing binding/expiry/cap/dedup check.

**Checkpoint**: every `around` fetch — truncated by window boundary, by cap
before the anchor, or by cap after the anchor — reports `has_more_before`/
`has_more_after` that match which side actually has unserved events.

## Phase 12: Attempt-1 Integrator Rejection — Continuation Progress and Cause Honesty

**Correction source**:
`evidence/v2/observation/review-2026-07-19-v2-integrator-attempt-1.md`, findings
H020-A1-01 HIGH and M020-A1-02 MEDIUM, against rejected candidate
`7b00bcaa4a2b8af12b6eb71bf6d8b098f4cfeba7`.

**Purpose**: ensure every minted continuation cursor progresses or exhausts,
and every capped page names the actual event/byte stop cause before candidate
attempt 2 is proposed.

- [X] T055 Add RED tests in `tests/v2/observation/test_budget_and_continuation.py`
  and a matching adversarial case in
  `evals/v2/observation/continuation/cases.jsonl` that fetch `around` e1–e5
  anchored at e3 with an event cap of 2, follow the minted same-handle,
  same-direction cursor, and reject any page-2 event overlap, repeated cursor,
  or failure to exhaust after the remaining fixed-window event, reproducing
  H020-A1-01
- [X] T056 Make `ContinuationProvider.fetch` consume a validated `around`
  cursor as the next scan position, preserve the original anchor-bound fixed
  window and authoritative ordering, emit no duplicate event IDs across the
  page sequence, and make T055 plus all existing direction-binding,
  before/after/around, cap, expiry, and coverage tests pass without weakening
  H020-01 or T054
- [X] T057 Add RED continuation-fetch tests and adversarial eval cases proving
  `coverage.truncated_by` reports exactly `events` for event-only truncation,
  exactly `bytes` for byte-only truncation, and both causes when both stop
  conditions are simultaneously true, reproducing M020-A1-02
- [X] T058 Track event-cap and byte-cap stop causes independently from
  `next_index` in `ContinuationProvider.fetch`, return their truthful stable
  cause list, and make T057 plus snapshot/continuation schema, budget, and
  evidence tests pass without changing accepted I-010D wire shape or cap
  enforcement
- [X] T059 Regenerate continuation and aggregate evidence, append an attempt-1
  rejection supersession to `evidence/v2/observation/handoff.md` with T055–T058
  RED→GREEN receipts and the final T001–T059 manifest identity, rerun the
  complete observation/corpus/eval/full-suite/verdict/governance/task-manifest/
  diff-check matrix, restore the two blocked `plan.md` constitution rows to
  PASS only on exact GREEN evidence, and record the existing unbounded
  bookkeeping sets as non-blocking follow-up scope rather than silently
  claiming they are bounded

### Phase 12 dependencies

- T055 must fail before T056 is accepted.
- T057 must fail before T058 is accepted.
- T056 and T058 may share one implementation pass only after both RED classes
  are captured; neither may weaken T047–T050 or T054.
- T059 closed Phase 12 and initially blocked `/speckit-converge`; convergence
  then appended T060, which now blocks candidate attempt 2 and handoff attempt 2.

**Checkpoint**: every continuation cursor progresses or exhausts, cap-cause
coverage names what actually stopped the page, all tasks through T059 are
complete, and the append-only evidence distinguishes rejected attempt 1 from
the new candidate tree before convergence.

## Phase 13: Convergence

**Correction source**: `/speckit-converge` re-run (2026-07-19) against the
completed T001–T059 candidate tree, found by direct row-count inspection of
the regenerated evidence files versus the separate manifest that describes
them.

**Purpose**: Close a stale scene-to-record manifest left behind when Phase 10
(T050), Phase 11 (T054), and Phase 12 (T055–T058) each appended new
`continuation.jsonl` rows (and Phase 10 appended a `budget-sweep.jsonl` row)
without updating the manifest's per-scene row counts or total.

- [X] T060 Regenerate the Scene-to-record manifest table in
  `evidence/v2/observation/README.md` and supersede the stale T059 aggregate
  matrix in `evidence/v2/observation/handoff.md` to match the current evidence
  files: correct `continuation.jsonl`'s stated `CONT-S03-*` count (4 rows) to
  the actual 9 (`CONT-S03-001`–`009`) and stated `CONT-S15-*` count (2 rows)
  to the actual 5 (`CONT-S15-001`–`005`); correct `budget-sweep.jsonl`'s stated
  `BUD-S15-*` count (3 rows) to the actual 4 (`BUD-S15-001`–`004`); and
  correct the stale 28/36-row totals to the actual 37-row total
  (`identity-and-hygiene.jsonl`: 9, `budget-sweep.jsonl`: 7,
  `continuation.jsonl`: 14, `s05-recoverability.jsonl`: 4,
  `s13-equivalence.jsonl`: 3); re-verify every other scene/file row count with
  exact JSONL `case_id` counting before recording the correction, per T035 /
  FR-013 (contradicts)

### Phase 13 dependencies

- T060 is evidence-manifest-only; it has no code, test, or corpus dependency
  and may run any time against the current evidence files.

**Checkpoint**: `evidence/v2/observation/README.md`'s Scene-to-record
manifest states exact, currently-reproducible row counts for every scene and
evidence file, matching `evidence/v2/observation/handoff.md`'s own
verification matrix.

## Phase 14: Attempt-2 Retention-Cursor Rework

**Correction source**:
`evidence/v2/observation/convergence-phase14-2026-07-19.md`, finding
H020-A2-01 HIGH.

**Purpose**: Make every paginated continuation direction preserve original
event identity across bounded-retention index shifts, rather than protecting
only `around` cursors.

- [X] T061 Add RED `before` cursor tests in
  `tests/v2/observation/test_budget_and_continuation.py` proving a retained
  anchor plus a one-event deque shift cannot duplicate an already served
  event, reorder the original remaining identities, or silently continue when
  any original remaining identity has been evicted, reproducing H020-A2-01
- [X] T062 Add RED `after` cursor tests in
  `tests/v2/observation/test_budget_and_continuation.py` proving a retained
  anchor plus a one-event deque shift serves the originally next event rather
  than the event now occupying the old numeric index, and fails closed when an
  original remaining identity is no longer retained, reproducing H020-A2-01
- [X] T063 Generalize continuation cursor metadata in
  `src/nunchi/observation.py` so `before`, `after`, and `around` all bind the
  original anchor, direction, and remaining event identities; resolve those
  identities against the live event index on replay; reject missing identities;
  preserve authoritative direction ordering, cap-cause reporting, exact-event
  dedup, and zero-progress protection; make T061–T062 and all existing tests pass
- [X] T064 Add deterministic `before` and `after` retention-shift and eviction
  cases to `evals/v2/observation/continuation/cases.jsonl`, extend
  `evals/v2/observation/run_scenes.py` only as needed to exercise them, and
  regenerate `evidence/v2/observation/continuation.jsonl` plus every aggregate
  evidence file without weakening T054–T060
- [X] T065 Update `evidence/v2/observation/README.md` and append a Phase 14
  supersession to `evidence/v2/observation/handoff.md`; rerun the complete
  Observation/corpus/eval/full-suite/verdict/governance/task-manifest/diff
  matrix; record final T001–T065 IDs/hash and exact evidence counts; keep the
  bounded bookkeeping limitation explicit; prepare candidate attempt 2 only
  if convergence appends no further task

### Phase 14 dependencies

- T061 and T062 are independent RED coverage and may run in parallel.
- T063 depends on T061–T062.
- T064 depends on T063 GREEN behavior.
- T065 is last and blocks convergence and candidate attempt 2.

**Checkpoint**: every continuation cursor direction is identity-bound across
retention shifts or fails closed on eviction; no page overlaps, skips, or
claims gap-free continuity after identity loss.

## Phase 15: Bounded Cursor Lifecycle and Resource Safety

**Correction source**:
`evidence/v2/observation/convergence-phase15-2026-07-19.md`, finding
S020-A3-01 HIGH/security.

**Purpose**: Preserve retention-safe immutable cursor identity without
quadratic or never-pruned host bookkeeping.

- [X] T066 Add RED tests in
  `tests/v2/observation/test_budget_and_continuation.py` proving a long
  one-event-per-page chain retains one shared immutable event-ID window and at
  most one active cursor for that sequence, consumed tokens reject as one-shot,
  and exhaustion releases the sequence's active cursor state
- [X] T067 Replace copied remaining-ID suffixes in
  `src/nunchi/observation.py` with a shared immutable ordered event-ID tuple plus
  next-position metadata, consume incoming tokens only after a page validates,
  and preserve all direction/anchor/fixed-window/retention/cap/order guarantees
- [X] T068 Add configurable global handle and per-handle active-cursor bounds,
  explicit host `revoke()` cleanup, and expiry-triggered handle cleanup to
  `ContinuationProvider`; add RED→GREEN tests for each rejection and cleanup
  path without changing accepted I-010A/I-010D wire shapes
- [X] T069 Add a deterministic bounded-resource continuation case to
  `evals/v2/observation/resource-safety/cases.jsonl`, extend
  `evals/v2/observation/run_scenes.py` to assert retained handle/cursor/window
  counts, and regenerate every aggregate evidence file plus the scene manifest
- [X] T070 Append a Phase 15 supersession to
  `evidence/v2/observation/handoff.md`, restore the Constitution Check rows to
  PASS only on exact GREEN evidence, rerun the complete
  Observation/corpus/eval/full-suite/verdict/Ruff/security/governance/
  task-manifest/diff matrix, and record the final T001–T070 task identity

### Phase 15 dependencies

- T066 and T068 RED coverage may be authored in parallel.
- T067 depends on T066 RED; T068 implementation follows its own RED coverage.
- T069 depends on T067–T068 GREEN behavior.
- T070 is last and blocks convergence and candidate attempt 2.

**Checkpoint**: cursor correctness state is linear in each immutable window,
active cursors and handles are explicitly bounded, consumed/exhausted/expired/
revoked state is reclaimed, and resource claims are evidence-backed.

## Phase 16: Authority Isolation, Event-Instance Identity, and Retained State

**Correction source**:
`evidence/v2/observation/convergence-phase16-2026-07-19.md`, findings
S020-A4-01–03, H020-A4-04–05, and S020-A4-06 HIGH.

**Purpose**: Make continuation authority fail closed, bind immutable event
instances rather than reusable IDs, report later known arrivals truthfully, and
couple all auxiliary observation state to bounded retention.

- [X] T071 Add RED authority tests proving absent/malformed fetch time and
  malformed/naive expiry reject when expiry exists; mutating the returned
  capability cannot alter internal binding/expiry/direction/caps; cursor minting
  never adds a closed-schema-forbidden field to the returned I-010A document
- [X] T072 Add RED event-instance and side-coverage tests proving an evicted and
  reingested ID cannot satisfy an original cursor remainder or anchor, and final
  `after`/retention-shifted `around` pages report known later arrivals through
  `has_more_after` without admitting them to the original remainder
- [X] T073 Add RED retained-state tests proving `_seen_delivery_ids`, event
  instance generations, and `_actors` remain bounded by retained events/self;
  unrelated actor facts and invalid candidate deliveries create no durable state
- [X] T074 Separate private continuation authority and cursor provenance from
  deep-copied returned wire documents; make issuance/fetch expiry validation
  parseable, timezone-aware, and fail closed; preserve expiry cleanup and all
  accepted I-010A/I-010D shapes
- [X] T075 Assign monotonic host generations to accepted retained events, bind
  cursor anchors/windows to `(event_id, generation)` pairs, reject replacement
  instances, and carry immutable snapshot-generation/side-omission facts through
  pagination while preserving one-shot bounded lifecycle behavior
- [X] T076 Couple retained delivery IDs, event generations, and actor facts to
  deque eviction; filter actor input to retained references/self; move delivery
  dedup commitment after successful validation; preserve ordinary retained
  duplicate and relation-resolution behavior
- [X] T077 Add deterministic authority, replacement-identity, later-arrival
  coverage, and retained-state cases under
  `evals/v2/observation/resource-safety/cases.jsonl`; extend the runner only as
  needed and regenerate every evidence aggregate plus the scene manifest
- [X] T078 Update `evidence/v2/observation/README.md` and append a Phase 16
  supersession to `evidence/v2/observation/handoff.md`; preserve all rejected
  attempt history unchanged and supersede only through new appended evidence
- [X] T079 Restore the Constitution Check rows to PASS only after the complete
  Observation/corpus/eval/full-suite/verdict/Ruff/static/governance/
  task-manifest/diff matrix is green; record T001–T079 identity and dispatch an
  immutable independent review before candidate attempt 2

### Phase 16 dependencies

- T071–T073 are independent RED groups and may be authored in parallel.
- T074 depends on T071 RED; T075 depends on T072 RED; T076 depends on T073 RED.
- T077 depends on T074–T076 GREEN behavior.
- T078 depends on regenerated T077 evidence.
- T079 is last and blocks convergence and candidate attempt 2.

**Checkpoint**: returned wire documents cannot rewrite authority, expiry fails
closed, cursor identity survives ID reuse, side coverage discloses later known
arrivals, and every host registry is bounded by explicit limits or retention.

## Phase 17: Exact Expiry Boundary

**Correction source**:
`evidence/v2/observation/convergence-phase17-2026-07-19.md`, finding
S020-A5-01 HIGH.

**Purpose**: Make `expires_at` the first invalid instant rather than serving
authority at exact equality.

- [X] T080 Add a RED exact-boundary test proving `fetch_time == expires_at`
  rejects and reclaims the handle
- [X] T081 Change expiry comparison to exclusive-authority semantics
  (`fetch_time >= expires_at`); add a deterministic resource-safety case,
  regenerate evidence/manifest, and append a Phase 17 handoff supersession
- [X] T082 Restore planning PASS only after the complete matrix is green; record
  the T001–T082 graph identity and obtain a fresh immutable independent review
  before candidate attempt 2

### Phase 17 dependencies

- T081 depends on T080 RED.
- T082 depends on T081 GREEN evidence and is the final convergence blocker.

**Checkpoint**: expiring authority rejects before serving any event when fetch
time is equal to or later than `expires_at`.

## Phase 18: Hard Snapshot Bytes, Origin Merge Identity, and Reproducible Static Evidence

**Correction source**:
`evidence/v2/observation/review-2026-07-19-candidate-2-preparation-rejection.md`,
two CRITICAL findings and one HIGH finding against `f38a4fe`.

**Purpose**: Make snapshot hard caps and cross-request merge identity true in
the implementation and make every static completion receipt reproducible.

- [ ] T083 Add RED tests proving a trigger larger than `max_bytes` rejects
  without returning an over-budget snapshot, and the budget evaluator cannot
  mark any row PASS when accepted event bytes exceed the configured cap
- [ ] T084 Fail closed before snapshot assembly when the mandatory trigger does
  not fit; update BUD-S15-001 to expect rejection, make the runner assert the
  cap invariant, and regenerate budget evidence
- [ ] T085 Add RED tests proving continuation issuance requires a private
  originating-request event-ID set and fetch rejects any page whose event IDs
  overlap that set before cursor state commits
- [ ] T086 Bind an immutable originating-request ID set to each handle, clean it
  up on revoke/expiry, enforce exact merge dedup without changing I-010A/I-010D
  wire shapes, update all host call sites/docs, and add deterministic adversarial
  continuation evidence
- [ ] T087 Add a committed, owner-scoped static secret scanner with documented
  high-confidence matchers and explicit `--base`/`--head` range; replace the
  unreproducible Phase 17 row with its exact invocation and output
- [ ] T088 Regenerate manifest/handoff evidence, restore planning PASS only
  after the complete matrix is green, record T001–T088 identity, and obtain a
  fresh immutable independent review before candidate attempt 2

### Phase 18 dependencies

- T083/T084, T085/T086, and T087 are independent correction lanes.
- T088 depends on T084, T086, and T087 GREEN evidence and is the final blocker.

**Checkpoint**: no accepted snapshot exceeds hard bytes, no continuation page
overlaps its originating request, and static completion evidence is exactly
reproducible from the candidate tree.
