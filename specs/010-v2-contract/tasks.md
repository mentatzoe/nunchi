# Tasks: V2 Contract

**Input**: `specs/010-v2-contract/spec.md` and `specs/010-v2-contract/plan.md`

**Slice state**: `ACTIVE`

**Execution status**: `EXECUTABLE` — the slice is `ACTIVE`, so unchecked
tasks execute only inside a bound `run speckit` run for this slice; tasks are
`DORMANT` whenever the slice state is `PLANNED` (statement added per CHK065)

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
Each candidate attempt hashes the task graph as it stands for that attempt
(including any convergence-appended tasks); the immutable activation record
retains the initial values unchanged.

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

- [X] T001 Create shared `Draft202012Validator` and stdlib-runtime corpus adapters — implementing the SC-002 preservation assertion (parsed semantic fields compare equal by exact token, event-array order preserved) and the FR-012 expressiveness partition with the spec's closed six-class runtime-adapter-only set (cross-item ID uniqueness, timestamp-versus-order agreement, cross-document advice citations, trigger membership, fetch-time binding/expiry state, receipt-stage sequence rules; every other case is schema-expressible and must yield identical results from both validators) — pinned to dev/test-only `jsonschema==4.26.0`; the corpus loader decodes non-finite sentinel strings (`"NaN"`, `"Infinity"`, `"-Infinity"`) once so both validators receive identical decoded cases, and asserts each corpus directory's per-class counts loudly against its authoritative `expected-counts.json` (updated in the same change as any corpus edit); the two skip regimes stay separately named and counted — baseline oracle-absence skips under `python3 -m unittest` versus explicit per-class oracle skips under the pinned dual-validator command; the stdlib adapter always runs under the repo baseline, and a missing oracle fails loudly only under the pinned command — in `tests/v2/contract/schema_helpers.py`
- [X] T002 [P] Add red request cases for exact identity (S01), actor mentions versus `mentions_room` (S02), duplicate event IDs, timestamp-versus-order disagreement, and trigger-membership violation (trigger absent from `events`) — all runtime-adapter-only — with the valid identical-text-distinct-ID case, classifier-safe continuation projection and bounded tail (S03), non-positive budgets (S15), and V1-envelope/reply-bearing/social-ledger rejection (S16, 010-V1) in `tests/v2/contract/test_attention_request.py`
- [X] T003 [P] Add red ok/error/bypass decision cases — forbidden classifier fields on `preattention-disabled`; legacy-confidence-vector constraints on every `status: ok` (exactly the four `PASS`/`ACK`/`ASK`/`SPEAK` keys, finite values in [0,1] including sentinel-decoded `"NaN"`/`"Infinity"`/`"-Infinity"` red cases, extra keys forbidden); and FR-013 advice red cases keyed to the classifier disposition (advice present when the classifier disposition is `DEFER` or `SUPPRESS`; advice citing nonexistent event IDs, runtime-adapter-only) — in `tests/v2/contract/test_attention_decision.py`
- [X] T004 [P] Add red wake-source cases including advice-free `PREATTENTION_BYPASS` (010-Preattention-bypass), FR-013 advice-source violations (advice on any non-`WAKE` `source`), and non-positive participant budgets (S15) in `tests/v2/contract/test_participant_wake.py`
- [X] T005 [P] Add red host-secret leakage, binding (fetch-time expired-handle rejection and cross-binding cursor reuse, runtime-adapter-only), continuity-scope duplicate-ID collision between a continuation page and its originating request (FR-003/FR-009, runtime-adapter-only), immutable-stage and writer-ownership (receipt-stage sequence rules, runtime-adapter-only), and explicit unknown/unavailable cases in `tests/v2/contract/test_context_and_receipt.py`

## Phase 2: User Story 1 - Truthful Attention Request (Priority: P1)

**Goal**: Land `I-010A AttentionRequestV2@1` with exact identity, factual
events, honest coverage, and no social ledger.

**Independent Test**: `tests/v2/contract/test_attention_request.py` accepts
the valid scene matrix and rejects every enumerated identity, order, reference,
coverage, V1, and forbidden-field case.

- [X] T006 [US1] Define `I-010A AttentionRequestV2@1` with distinct actor mentions, `mentions_room`, and host-only continuation metadata in `schemas/v2/attention-request.schema.json`
- [X] T007 [P] [US1] Add request and classifier-projection conformance cases (S01, S02, S03) including duplicate-ID, timestamp-order, and trigger-membership relational red cases — proving opaque continuation fields never reach the classifier — plus V1-envelope and social-ledger red cases (S16, 010-V1), in `evals/v2/contract/attention-request/cases.jsonl` with its authoritative per-class `expected-counts.json` updated in the same change
- [X] T008 [US1] Record exact-self (S01), native-relation (S02), bounded-context/gap (S03), budget (S15), projection, and S16/010-V1 rejection results with mandatory `scene_id` in `evidence/v2/contract/attention-request.jsonl`

## Phase 3: User Story 2 - Auditable Attention Decision (Priority: P1)

**Goal**: Land `I-010B AttentionDecisionV2@1` with the closed ok-transition
matrix, non-social preattention bypass, dual-valve audit, grounded advice, and
separate error branch.

**Independent Test**: `tests/v2/contract/test_attention_decision.py` proves only
four ok pairs validate, malformed transition evidence cannot support
suppression, and bypass validates only without a classifier/effective result.

- [X] T009 [US2] Define `I-010B AttentionDecisionV2@1` ok/error/bypass union with exact `preattention-disabled` constraints in `schemas/v2/attention-decision.schema.json`
- [X] T010 [P] [US2] Add — partitioned per FR-012 — transition (S09), governed-suppression (S05), dual-DEFER (S08), bypass (010-Preattention-bypass), malformed-output, FR-013 advice-rule, and reply-bearing/social-ledger rejection cases (S16) for both validators in `evals/v2/contract/attention-decision/cases.jsonl` with its authoritative per-class `expected-counts.json` updated in the same change
- [X] T011 [US2] Record governed-suppression (S05), dual-DEFER (S08), transition/error (S09), bypass (010-Preattention-bypass), and S16 rejection results with mandatory `scene_id` in `evidence/v2/contract/attention-decision.jsonl`

## Phase 4: User Story 3 - Participant Wake, Continuation, and Receipt (Priority: P2)

**Goal**: Land the three downstream contracts that keep factual wake delivery,
host-only bounded expansion, and immutable staged telemetry distinct.

**Independent Test**: Wake, continuation, and receipt contract tests validate
normal act-or-silence input including bypass, strict host-only handle binding,
and immutable singly written observation/attention/participant-host/transport
records correlated by request ID.

- [X] T012 [P] [US3] Define `I-010C ParticipantWakeV2@1` with advice-free `PREATTENTION_BYPASS` in `schemas/v2/participant-wake.schema.json`
- [X] T013 [P] [US3] Define host-only handle/binding/cursor semantics for `I-010D ContextContinuationV2@1` in `schemas/v2/context-continuation.schema.json`
- [X] T014 [P] [US3] Define immutable request-correlated observation/attention/participant-host/transport stage records and bypass provenance for `I-010E AttentionReceiptV2@1` in `schemas/v2/attention-receipt.schema.json`
- [X] T015 [P] [US3] Add bypass wake (S06 contribution), participant-silence (S07), host-only binding — including expired-handle and cross-binding cursor-reuse fetch-time red cases and the continuation-page/originating-request duplicate-ID collision (runtime-adapter-only) — immutable receipt-stage, unknown/unavailable, and V1-envelope/reply-field/social-ledger rejection cases in `evals/v2/contract/downstream/cases.jsonl` with its authoritative per-class `expected-counts.json` updated in the same change
- [X] T016 [US3] Record wake (S06), silence (S07), binding, staged-receipt, bypass-provenance (010-Preattention-bypass), and S16/010-V1 rejection results with mandatory `scene_id` in `evidence/v2/contract/downstream.jsonl`

## Phase 5: Documentation and Packet Inputs

- [X] T017 Prepare documentation-freshness inputs by executing every exact row in `plan.md` §Documentation Impact and Freshness; author and validate the slice-owned `UPDATE` `docs/contracts/nunchi-v2.md` so it documents the five `@1` interfaces and the FR-012 runtime-adapter-only semantic rules that live outside the schemas; re-verify each `NO_IMPACT` rationale against the exact candidate diff with its reviewed path, route each named `HANDOFF` delta (including `README.md`) to its accepting owner, and record all proposed documentation dispositions, paths, results, and reviewer as the first section of `evidence/v2/contract/handoff.md` (documentation/packet evidence, a different file from the lifecycle attempt stream `slice-handoff.md`) for the later workflow gate
- [X] T018 Run the exact offline dual-validator command, run `python3 scripts/check_governance.py` with no flags (boundary-only SC-006 verification; `--check-cli` is the separate pinned-CLI check), and create the S-ID-to-JSONL-record manifest covering all twelve scene rows (S01, S02, S03, S05, S06, S07, S08, S09, S15, S16, 010-Preattention-bypass, 010-V1) — recording the observed per-class partition counts and both skip-regime counts beside the commands and results — in `evidence/v2/contract/README.md`
- [X] T019 Prepare the proposed packet input with the exact commit, commands, five interface versions and exact `schemas/v2/` paths, dual-validator pin/results over the shared corpus, the corpus revision (that exact commit) with the downstream obligation that each runtime owner pass its stdlib adapter over the identical corpus before its own handoff, staged-receipt writer map, scene-to-record evidence manifest, rejected-case inventory, migration/provenance notes, documentation dispositions/validation/reviewer, and known limitations, appended to `evidence/v2/contract/handoff.md` after T017's documentation section without rewriting it; this enumeration is authoritative for the SC-005 packet inventory, and the later convergence, documentation-freshness, and handoff gates—not this checkbox—establish lifecycle state

## Phase 6: Post-Refresh Reviewer-Gate Corrections (appended 2026-07-17)

**Correction source**: the round-4 spec amendments (`16cccb7`: FR-012 fixed
per-class oracle treatment, FR-010 canonical-order and prefix-partial receipt
rule, FR-007 `@1` permanence), the plan refresh (`e4ada5c`: per-family corpus
directories, exact evidence-file enumeration, completed file-by-file
documentation matrix), and the appended formal-reviewer refresh gate
CHK064–CHK076 (`b1204f5`). This phase is strictly append-only: completed
tasks T001–T008 and all prior task text remain exactly as landed; the only
non-append change in this refresh is the header **Execution status** line,
which now states the `ACTIVE`-state rule the gate found implied (CHK065).
Every task below cites the checklist item(s) or amendment it traces to.

- [X] T020 Assert the closed on-disk corpus inventory at load time in `tests/v2/contract/schema_helpers.py` — the set of subdirectories of `evals/v2/contract/` must equal exactly the registered `CORPUS_NAMES` (`attention-request`, `attention-decision`, `downstream`), each holding `cases.jsonl` and its authoritative `expected-counts.json`, so a wholly missing or unregistered corpus directory fails loudly rather than passing vacuously — with a red-path helper test beside the existing helper cases in `tests/v2/contract/test_attention_request.py` (CHK067)
- [X] T021 Enforce all five mandatory aggregate-record fields (`scene_id`, stable `case_id`, validator identity, expected result, observed result) in the shared evidence writer in `tests/v2/contract/schema_helpers.py`, refusing any record missing one, and re-verify the landed `evidence/v2/contract/attention-request.jsonl` and the in-flight `evidence/v2/contract/attention-decision.jsonl` and `evidence/v2/contract/downstream.jsonl` against the enforced shape before T011/T016 are checked (CHK070; plan §Acceptance Scenes and Evidence)
- [X] T022 [P] Verify under the pinned dual-validator command that `evals/v2/contract/downstream/cases.jsonl` names the complete refreshed FR-010 receipt-sequence coverage — full canonical observation→attention→participant-host→transport stream valid; prefix-partial valid-in-progress (awaiting-transport, and the S07 silence outcome ending at participant-host); out-of-canonical-order red; skipped-stage red; earlier-stage mutation red; cross-owner writer red; uncorrelated request-ID red — appending any missing case with `expected-counts.json` updated in the same change (CHK069; FR-010 as amended at `16cccb7`)
- [X] T023 Add the control-plane read-boundary enforcement — a scanner helper in `tests/v2/contract/schema_helpers.py` plus its covering test beside the existing helper cases in `tests/v2/contract/test_attention_request.py` asserting that no file under `tests/v2/contract/` or `evals/v2/contract/` references a SpecKit-managed control-plane path (the slice-specification tree or the SpecKit configuration tree; the literal forbidden prefixes are embedded in the test itself), making explicit that the suite embeds its own copy of the FR-012 class vocabulary and no build or test path reads a SpecKit-managed file (CHK076)
- [X] T024 Adjudicate CHK064–CHK076 against the refreshed artifacts and append per-item verdicts with evidence anchors to `evidence/v2/contract/checklist-adjudication.md` (append-only; the CHK018–CHK063 adjudication is never rewritten); for each sustained text gap, land the fix in the named SpecKit artifact in the same commit before check-off — CHK064 "tagged contract commit" wording in plan §Integration Strategy; CHK065 execution-status statement (fixed in this tasks refresh — verify and record); CHK066 restating or explicitly deferring to the spec's fixed per-class oracle treatment in plan §Contract validation commands; CHK071 a written ownership note for the absent umbrella scene IDs (S04, S10–S14); CHK073–CHK075 documentation-matrix consistency, per-row verifiability, and the written derivation/exhaustiveness claim in plan §Documentation Impact and Freshness — citing T020 (CHK067), T021 (CHK070), T022 (CHK069), and T023 (CHK076) as landed evidence, and recording CHK068 and CHK072 as consistency confirmations

## Phase 7: Post-Rejection Correction (appended 2026-07-17)

**Correction source**: the v2-integrator rejection of candidate
`81483ce017eb834c5ab533556fa64cd62a8cf2aa` at packet commit
`9f08124b43ba5beb73c50b876bde51e7b8a1633d`, recorded at
`evidence/v2/contract/review-2026-07-17-v2-integrator.md` (blockers R1–R3);
the spec's 2026-07-17 clarification session landed at `89aef07` (conditional
FR-007 legacy-vector rule, closed FR-005 routing-audit set, schema-expressible
per-record FR-010 stage-to-writer binding); the plan's §Post-Rejection
Planning Decisions landed at `8fbc79d`; and the post-rejection formal reviewer
gate CHK077–CHK096 appended at `95b22a1`. This phase is strictly append-only:
completed tasks T001–T024, all prior task text, and every attempt-1 evidence
record remain exactly as landed, and this refresh changes no header line.
Every task below cites the blocker, clarified requirement, or checklist
item(s) it traces to.

- [X] T025 Adjudicate the post-rejection gate's requirement-text items against the amended artifacts and, for each sustained text gap, land the fix in the named SpecKit artifact in the same commit before check-off — CHK077 an explicit spec §Control-Plane Boundary statement that the R1 repair in `tests/test_governance.py` is an in-scope ordinary rework output of this slice; CHK079 a written ownership note in plan §Integration Strategy that `v2-contract-owner` performs that shared governance-infrastructure edit for this rework with `v2-integrator` review at handoff; CHK084 the routing audit's cross-field rules in spec FR-005/FR-006 (when a margin counts as "applied" requiring the effective margin, when the trusted source is "present", and the valve/override-cause/transition legality combinations); CHK085 `reasons` fixed as a sibling ok-branch field never inside the routing-audit object; CHK086 one identical bypass exclusion set at every spec surface; CHK087 the closed stage-to-writer map written into spec FR-010 (`observation` → `observation-provider`, `attention` → `attention-engine`, `participant-host` → `participant-host`, `transport` → `transport`); CHK088 the permissive FR-007 side (a valid vector accompanying `WAKE`, `DEFER`, or a margin-retired `SUPPRESS` stays valid); CHK089 written attempt-2 evidence rework semantics (aggregate JSONL and the README manifest regenerate as current-attempt records; `handoff.md` and `checklist-adjudication.md` append per attempt; lifecycle attempt streams never rewrite); CHK090 "candidate commit" and "handoff packet commit" defined as distinct terms each carrying the green full-baseline obligation; CHK095 the R1 repair restated as a verifiable invariant with its named regression proof — appending the per-item text verdicts with evidence anchors to `evidence/v2/contract/checklist-adjudication.md` (append-only; earlier adjudications are never rewritten) and recording CHK091 (the appended `REJECTED` attempt already names the exact review record and candidate commit) and CHK096 (no new slice-directory file) as consistency confirmations
- [X] T026 [P] Repair the governance activation-path fixture (rejection R1; plan §Post-Rejection Planning Decisions, Decision R1) so `tests.test_governance.GovernanceBoundaryTests.test_authorized_contract_slice_can_reach_active_end_to_end` constructs its synthetic planning baseline independently of the repository's live slice state — replacing every live slice declaration and lifecycle record it stages, not only `PLANNED` ones — and add the CHK095 regression proof beside it in `tests/test_governance.py`: a case asserting the fixture's baseline stays green while live slice declarations are `ACTIVE` or `HANDOFF_READY`, then verify the full `python3 -m unittest` baseline green from the working tree
- [X] T027 [P] Rework `I-010B AttentionDecisionV2@1` in `schemas/v2/attention-decision.schema.json` to the clarified shape (rejection R2; FR-005/FR-007 as clarified at `89aef07`): the legacy verdict confidence vector optional on `status: ok` and required exactly when the classifier disposition is `SUPPRESS` while the routing audit reports the margin `active`; the closed routing audit recording the applied valve, override cause, margin status, effective margin when one applied, and trusted margin source when present, encoding the T025-landed CHK084 cross-field rules; `reasons` as a sibling ok-branch audit field; and the bypass branch excluding the full FR-005 set — so the review's two Draft 2020-12 probes (a valid `WAKE` with routing `margin_status`; a valid `WAKE` without a legacy vector) both validate
- [X] T028 [P] Rework the decision corpus and red tests to the conditional rule (rejection R2; CHK081, CHK083, CHK086, CHK088): in `evals/v2/contract/attention-decision/cases.jsonl` with its authoritative per-class `expected-counts.json` updated in the same change, add the decisive cases — margin-active candidate `SUPPRESS` without the vector red; `WAKE` and `DEFER` without the optional vector valid; `WAKE`, `DEFER`, and margin-retired `SUPPRESS` carrying a valid vector valid; illegal routing-audit cross-field combinations red per the T025 rules; bypass carrying a routing audit or legacy vector red — and supersede in writing T003's every-ok-decision framing in `tests/v2/contract/test_attention_decision.py` by re-keying its legacy-confidence red cases (including the sentinel-decoded non-finite ones) to the conditional FR-007 rule
- [X] T029 [P] Encode the per-record stage-to-writer binding (rejection R3; FR-010 as clarified at `89aef07`; CHK087) in `schemas/v2/attention-receipt.schema.json` per the T025-written closed map so a record attributing one stage to another stage's owner — including the review's forged `stage: observation` / `writer: transport` document — is invalid as a single document, and enforce the identical map in the individual stdlib validator `validate_attention_receipt` in `tests/v2/contract/schema_helpers.py`, while `validate_receipt_stream` retains the stream-level canonical-order, skipped-stage, earlier-stage-mutation, request-ID-correlation, and writer-ownership checks unchanged
- [X] T030 [P] Reclassify the cross-owner receipt case operationally (rejection R3; CHK082): in `evals/v2/contract/downstream/cases.jsonl` with its authoritative per-class `expected-counts.json` updated in the same change, move the per-record cross-owner red case into the schema-expressible partition asserting identical rejection from both validators, keep the multi-record stream checks in the runtime-adapter-only receipt-stage sequence class, and name each reclassified case and per-class count delta so the no-silent-shrink assertion trips loudly during the move rather than masking it, with the covering red test in `tests/v2/contract/test_context_and_receipt.py`
- [X] T031 Regenerate the attempt-2 aggregate evidence under the reworked corpus per the T025-landed CHK089 semantics: re-record `evidence/v2/contract/attention-decision.jsonl` (S05 governed suppression under the conditional FR-007 rule per CHK083, dual-DEFER S08, transition/error S09, bypass, S16) and `evidence/v2/contract/downstream.jsonl` (receipt stage/writer cases, S06, S07, binding, S15, S16, 010-V1) as current-attempt records through the T021-enforced five-field writer, record the disposition of the unchanged `evidence/v2/contract/attention-request.jsonl` explicitly, then refresh the twelve-scene manifest with post-rework per-class partition counts and both skip-regime counts in `evidence/v2/contract/README.md`, recording the exact pinned dual-validator command, the flagless governance check, and the full `python3 -m unittest` baseline result — the run whose green result the exact candidate commit must reproduce, with the packet-commit rerun owed at the handoff gate (CHK080) — beside the commands
- [ ] T032 Re-execute every row of plan §Documentation Impact and Freshness against the attempt-2 candidate diff (CHK092): re-validate the `UPDATE` `docs/contracts/nunchi-v2.md` so it documents the conditional FR-007 vector rule, the closed routing-audit set, and the per-record FR-010 stage-to-writer binding alongside the five `@1` interfaces and the FR-012 runtime-adapter-only rules (CHK094); re-verify each `NO_IMPACT` rationale sequenced after the T026 repair so the `AGENTS.md` green-baseline claim is true at the verified commit (CHK093); re-route each named `HANDOFF` delta including `README.md` to its accepting owner; and append the attempt-2 documentation section to `evidence/v2/contract/handoff.md` without rewriting the attempt-1 sections
- [ ] T033 Complete the CHK077–CHK096 adjudication by appending the implementation-cited verdicts to `evidence/v2/contract/checklist-adjudication.md` (append-only; T025's text verdicts and all earlier adjudications are never rewritten): CHK078 fixed by this Phase 7 append; CHK080 via T031's recorded baseline obligation; CHK081 and CHK083 via T028 and T031; CHK082 via T030; CHK092–CHK094 via T032; CHK095 via T026's landed regression proof — each verdict citing its landed task, file, and record anchors, and checking off each gate item in the requirements checklist only when its fix is verifiably on disk
- [ ] T034 Append the attempt-2 proposed packet input to `evidence/v2/contract/handoff.md` after T032's documentation section, per T019's authoritative SC-005 enumeration: both defined commits (the exact candidate commit and the handoff packet commit, each carrying the green full-offline-baseline obligation per CHK090, the packet-commit run performed at the handoff gate), the five interface versions and exact `schemas/v2/` paths, the reworked staged-receipt writer map, the dual-validator pin and post-rework results over the shared corpus, the corpus revision with the unchanged downstream adapter obligation, the regenerated scene-to-record manifest, the updated rejected-case inventory, migration/provenance notes naming `evidence/v2/contract/review-2026-07-17-v2-integrator.md` and its three resolved blockers (CHK091), documentation dispositions/validation/reviewer from T032, and known limitations — the later convergence, documentation-freshness, and handoff gates, not this checkbox, establish lifecycle state

## Dependencies & Execution Order

- T001 precedes T002–T005. Red tests T002–T005 may then proceed in parallel.
- US1 and US2 schema work may proceed in parallel after their red tests exist;
  neither edits the other's schema.
- US3 begins after the shared concepts used by I-010A and I-010B are stable.
- T017–T019 require all five interfaces, all Draft 2020-12 oracle checks, and
  every currently available stdlib runtime adapter check to pass. T017 precedes
  T019: both write `evidence/v2/contract/handoff.md` append-only, documentation
  section first, packet section second. Each downstream runtime owner must
  close its adapter result over the identical corpus revision named in the T019
  packet before its own handoff.
- Slices 020 and 030 may start implementation only after the lifecycle handoff
  packet derived from T019 is separately accepted and recorded by each consumer;
  slice 040 additionally waits for their handoffs.
- Correction phase: T020 precedes T021, which precedes T023 (all three edit
  `tests/v2/contract/schema_helpers.py`); T022 runs in parallel once T015's
  corpus artifacts exist. T020–T023 precede T024. T024 precedes T017, because
  a sustained CHK073–CHK075 gap amends the documentation-matrix rows T017
  executes; T020–T022 precede T018, so the manifest records post-correction
  partition and skip counts. The appended tasks add no new documentation
  surface: T017's existing row-by-row execution already covers the refreshed
  matrix, including the `AGENTS.md` and `CLAUDE.md` `NO_IMPACT` rows added at
  `e4ada5c`.
- Rejection-rework phase: T025 precedes T027 and T029 (their schema shapes
  encode the CHK084 cross-field rules and CHK087 writer map T025 lands) and
  precedes T033. T026 has no file overlap with any other chain and may run
  throughout. T027 precedes T028's green dual-validator check-off and T029
  precedes T030's (red cases may be authored first). T026–T030 precede T031;
  T031 precedes T032 (the CHK093 sequencing puts `NO_IMPACT` re-verification
  after the R1 repair); T025–T032 precede T033; T032 and T033 precede T034.
  The attempt-2 sections of `evidence/v2/contract/handoff.md` append in the
  same documentation-then-packet order as T017→T019, after the attempt-1
  sections and never rewriting them.

## Parallel Opportunities

- T002–T005 target separate test files.
- T007, T010, and T015 target separate corpus directories, each owning its own
  `cases.jsonl` and per-class `expected-counts.json`.
- T012–T014 target separate schema files under the same sole owner.
- T022 (downstream corpus) is parallel to the T020→T021→T023 harness chain;
  T024 waits for all four.
- T026 (governance fixture) is parallel to both rework families; the
  decision family (T027→T028) and the receipt family (T029→T030) touch
  disjoint schema files, corpus directories, and test files and run in
  parallel with each other after T025.

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
- The FR-012 partition class vocabulary is spec-owned; case membership and
  per-class expected counts live only in ordinary paths
  (`tests/v2/contract/`, `evals/v2/contract/*/expected-counts.json`), so corpus
  growth never edits a SpecKit artifact.
- Phase 6 is the append-only correction for the post-`e4ada5c` reviewer
  refresh gate: completed history (checked tasks, evidence records, prior
  attempt streams) is preserved unchanged, and every appended task is
  traceable to its named correction source.
- Phase 7 is the append-only correction for the v2-integrator rejection of
  candidate `81483ce017eb834c5ab533556fa64cd62a8cf2aa`: completed history
  (checked tasks, attempt-1 evidence sections, the rejected candidate and
  handoff attempts) is preserved unchanged, this refresh edits no header
  line, and every appended task traces to blocker R1/R2/R3, a requirement
  clarified at `89aef07`, or a CHK077–CHK096 gate item.
- Attempt-2 evidence semantics (CHK089, written by T025): the aggregate JSONL
  files and the README manifest regenerate as current-attempt records;
  `evidence/v2/contract/handoff.md` and
  `evidence/v2/contract/checklist-adjudication.md` append per attempt; the
  lifecycle candidate/handoff attempt streams append and never rewrite.
- The closed stage-to-writer vocabulary is `observation` →
  `observation-provider`, `attention` → `attention-engine`,
  `participant-host` → `participant-host`, `transport` → `transport`; T025
  writes it into spec FR-010 and T029 encodes it in the public schema and the
  individual stdlib validator.
