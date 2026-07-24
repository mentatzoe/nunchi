# Tasks: V2 Contract

**Input**: `specs/010-v2-contract/spec.md` and `specs/010-v2-contract/plan.md`

**Slice state**: `ACCEPTED`

**Execution status**: stated by reference, never as a fixed state claim —
unchecked tasks execute only inside a bound `run speckit` run for this slice
while the transition-updated `Slice state` declaration above and the lifecycle
evidence (`evidence/v2/contract/slice-activation.md` plus the append-only
candidate/handoff attempt streams) establish the slice `ACTIVE`, and are
`DORMANT` under any other established state, including `PLANNED` (CHK065 rule
retained; reworded referentially per Decision R6/CHK106 — this line is never
edited at a transition, while the `Slice state` line above is the declaration
that is)

**Program implementation authority**: `GRANTED`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-contract-owner-2026-07-23.md

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
- [X] T032 Re-execute every row of plan §Documentation Impact and Freshness against the attempt-2 candidate diff (CHK092): re-validate the `UPDATE` `docs/contracts/nunchi-v2.md` so it documents the conditional FR-007 vector rule, the closed routing-audit set, and the per-record FR-010 stage-to-writer binding alongside the five `@1` interfaces and the FR-012 runtime-adapter-only rules (CHK094); re-verify each `NO_IMPACT` rationale sequenced after the T026 repair so the `AGENTS.md` green-baseline claim is true at the verified commit (CHK093); re-route each named `HANDOFF` delta including `README.md` to its accepting owner; and append the attempt-2 documentation section to `evidence/v2/contract/handoff.md` without rewriting the attempt-1 sections
- [X] T033 Complete the CHK077–CHK096 adjudication by appending the implementation-cited verdicts to `evidence/v2/contract/checklist-adjudication.md` (append-only; T025's text verdicts and all earlier adjudications are never rewritten): CHK078 fixed by this Phase 7 append; CHK080 via T031's recorded baseline obligation; CHK081 and CHK083 via T028 and T031; CHK082 via T030; CHK092–CHK094 via T032; CHK095 via T026's landed regression proof — each verdict citing its landed task, file, and record anchors, and checking off each gate item in the requirements checklist only when its fix is verifiably on disk
- [X] T034 Append the attempt-2 proposed packet input to `evidence/v2/contract/handoff.md` after T032's documentation section, per T019's authoritative SC-005 enumeration: both defined commits (the exact candidate commit and the handoff packet commit, each carrying the green full-offline-baseline obligation per CHK090, the packet-commit run performed at the handoff gate), the five interface versions and exact `schemas/v2/` paths, the reworked staged-receipt writer map, the dual-validator pin and post-rework results over the shared corpus, the corpus revision with the unchanged downstream adapter obligation, the regenerated scene-to-record manifest, the updated rejected-case inventory, migration/provenance notes naming `evidence/v2/contract/review-2026-07-17-v2-integrator.md` and its three resolved blockers (CHK091), documentation dispositions/validation/reviewer from T032, and known limitations — the later convergence, documentation-freshness, and handoff gates, not this checkbox, establish lifecycle state

## Phase 8: Post-Rejection Correction — Selected-Design Fidelity (appended 2026-07-18)

**Correction source**: the v2-integrator rejection of the attempt-2 candidate
`001fdf85acd5098264c4975559c97114aa7278af` at packet commit
`5383e9f3a5e9c20c08ab54395f4ff370128f03de`, recorded at
`evidence/v2/contract/review-2026-07-17-v2-integrator-attempt-2.md` (blockers
R4–R6); the spec's 2026-07-18 clarification session landed at `a183469`
(FR-014 selected-design field-inventory fidelity, the FR-012
authority-conformance corpus class, SC-005 single-valued commit identity, and
the referential execution-status rule); the plan's §Post-Rejection Planning
Decisions (2026-07-18, attempt 2) landed at `6d1fdeb`; and the appended
formal reviewer gate CHK097–CHK111 landed at `b395acf`. This phase is
strictly append-only: completed tasks T001–T034, all prior task text, both
rejected candidate/handoff attempt streams, and every prior evidence record
remain exactly as landed. The only non-append change in this refresh is the
header **Execution status** line, reworded from the hard-coded state-specific
claim to the referential statement Decision R6 requires (CHK106). Every task
below cites the blocker, clarified requirement, or checklist item(s) it
traces to.

- [X] T035 Adjudicate the attempt-2 rejection gate's requirement-text items against the amended artifacts and, for each sustained text gap, land the fix in the named SpecKit artifact in the same commit before check-off — CHK099 the authority-conformance class's partition placement written unambiguously (a named manifest-count class inside the schema-expressible partition with dual-validator treatment and identical expected results, never a new partition class with its own oracle treatment) in plan §Contract validation commands and §Acceptance Scenes and Evidence; CHK100 the closed minimum authority-case inventory stated identically across spec FR-012, FR-014, the §Edge Cases representative-document list, and the plan's per-family placement; CHK101 the red-then-green obligation made decidable (the attempt-3 packet evidences both the recorded red run of the authority cases against the attempt-2 schemas at a named pre-repair tree and the green results at the exact candidate commit) in spec FR-012 or plan §Contract validation commands; CHK102 the `c834e8c` tie-break stated where the spec FR-014 and plan §Produces enumerations appear, so neither local list is read as the narrower or wider authority; CHK103 the remaining error-branch inventory either enumerated or explicitly deferred to the selected design in spec FR-005/FR-014, including whether a post-validation error carries the request ID; CHK104 the narrowing-defect rule written as general (any local rename or narrowing is a contract defect adjudicated against the design's field inventory; the named attempt-2 examples are illustrative, not exhaustive) in spec §Clarifications (2026-07-18)/FR-014; CHK105 the four commit-identity locations enumerated identically at every statement and the operational recording rule for the handoff packet commit (which file and attempt entry record it once it exists, given the packet commit cannot name itself from inside its own tree) landed in plan §Owner Handoff; CHK107 the per-attempt evidence rework semantics generalized to every later attempt (aggregate JSONL files and the README manifest regenerate as current-attempt records, `handoff.md` and `checklist-adjudication.md` append one section per attempt, an evidence file left unchanged receives an explicit manifest disposition, and attempt 3 re-records `evidence/v2/contract/attention-request.jsonl` because R4 re-enters every corpus family) in plan §Acceptance Scenes and Evidence; CHK112 the disposition, added to this task's own text, that CHK108, CHK109, and CHK110 require no spec/plan text fix and close entirely through the T042–T044 implementation/evidence tasks, so their absence from this per-item list is not read as an unaddressed item; CHK114 the decidable classification rule, added to this task's own text, that a CHK item requires a landed text fix only when the cited spec/plan section does not yet contain, verbatim, the wording the item's question describes as of this task graph's authoring commit, and requires only a consistency confirmation when that exact wording already exists at that commit — removing adjudicator discretion from the classification — appending the per-item text verdicts with evidence anchors to `evidence/v2/contract/checklist-adjudication.md` (append-only; earlier adjudications are never rewritten) and recording CHK097 and CHK106 (fixed by this Phase 8 append and the reworded referential header — verify and record), CHK098 (the plan's decision text bounds the rework surface — verify against §Post-Rejection Planning Decisions and §Constitution Check), and CHK111 (no new slice-directory file) as consistency confirmations
- [X] T036 [P] Author the FR-014 authority-conformance cases for the attention-request family (rejection R4; FR-012/FR-014 as clarified at `a183469`; CHK099, CHK100): in `evals/v2/contract/attention-request/cases.jsonl` with its authoritative `expected-counts.json` updated in the same change, add — under the family's existing scene IDs, counted and flagged as the named authority class per the T035-landed CHK099 placement — the selected design's example attention request verbatim (the integrator probe that produced 41 stdlib-adapter errors) as a schema-expressible valid case, plus named valid cases covering the complete room platform/id/continuity-scope/name/kind facts and actor map, the typed message, reaction (`add`/`remove` operation), and membership (literal scope, subject actor, optional causal actor) event union, and the full coverage facts (`has_more_before`, `has_more_after`, `has_gaps`, `truncated_by`, `continuity`, `has_restart_gap`, and per-event-type visibility); record the decisive red run of these cases against the attempt-2 schemas at the exact attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de` (the rejected pre-repair tree) per the T035-landed CHK101 rule before T039 lands any schema edit
- [X] T037 [P] Author the FR-014 authority-conformance cases for the attention-decision family (rejection R4; CHK100): in `evals/v2/contract/attention-decision/cases.jsonl` with its authoritative `expected-counts.json` updated in the same change, add — under existing scene IDs, in the T035-landed authority class — named valid cases covering the selected decision inventory (`routing_audit`, `legacy_verdict_confidences`, a classifier audit naming the classifier with optional provider and model, and an error branch whose request ID is optional on a pre-validation error), including the review's two Draft 2020-12 probes (a valid `WAKE` with routing-audit margin status; a valid `WAKE` without a legacy vector) restated under the selected names, and record their decisive red run against the attempt-2 schemas at the exact attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de` (the rejected pre-repair tree) per the T035-landed CHK101 rule before T040 lands any schema edit
- [X] T038 [P] Author the FR-014 authority-conformance cases for the downstream family (rejection R4; CHK100): in `evals/v2/contract/downstream/cases.jsonl` with its authoritative `expected-counts.json` updated in the same change, add — under existing scene IDs, in the T035-landed authority class — the selected directional anchored fetch (the rejected `ContextFetch` probe) and continuation capability (`handle_id`, exact `bound_to`, before/after/around fetch capabilities, per-fetch caps, optional expiry) with identity-bearing page cases (room and continuity-scope identity, direction, anchor, actor map, page binding); the selected materialized wake packet (the 16-error `ParticipantWake` probe: self, room, actors, events, trigger, coverage, optional host-only continuation authority, separate `attention` object); and four-stage receipt telemetry cases including the integrator's observation (13-error) and participant-host (11-error) probes plus attention and transport stage cases, and record their decisive red run against the attempt-2 schemas at the exact attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de` (the rejected pre-repair tree) per the T035-landed CHK101 rule before T041 lands any schema edit
- [X] T039 Rework `I-010A AttentionRequestV2@1` to the selected field inventory (rejection R4; FR-014; plan §Produces): encode in `schemas/v2/attention-request.schema.json` the room platform/id/continuity-scope/name/kind facts and actor map, and the typed message, reaction, and membership event union with reaction `add`/`remove` operation and literal membership scope, subject actor, and optional causal actor (FR-014, replacing the generic event shape), and the selected coverage facts (replacing the collapsed coverage enums); update the stdlib request adapter in `tests/v2/contract/schema_helpers.py` to the same inventory; rework the existing narrowed-shape cases in `evals/v2/contract/attention-request/cases.jsonl` (its `expected-counts.json` updated in the same change) and the red tests in `tests/v2/contract/test_attention_request.py` to the selected shapes while preserving every S01/S02/S03/S15/S16/010-V1 obligation and the classifier-safe projection rule; and verify the T036 authority cases — including the design's example request verbatim — pass under both the pinned dual-validator command and the stdlib adapter
- [X] T040 Rework `I-010B AttentionDecisionV2@1` to the selected names and shapes (rejection R4; FR-014 superseding the local `routing`/`legacy_confidence` shapes; CHK103, CHK104): rename and reshape in `schemas/v2/attention-decision.schema.json` to `routing_audit` and `legacy_verdict_confidences`, a classifier audit naming the classifier with optional provider and model, and the request ID optional on both the pre-validation and post-validation error branches per the T035-landed CHK103 rule (the request ID's optionality is not narrowed to the pre-validation case alone) — carrying forward unchanged, under the selected names, the conditional FR-007 vector rule, the CHK084 routing-audit cross-field rules, the FR-013 advice keying, and the closed bypass exclusion set; update the stdlib decision adapter in `tests/v2/contract/schema_helpers.py`; re-key `tests/v2/contract/test_attention_decision.py` and the existing cases in `evals/v2/contract/attention-decision/cases.jsonl` (its `expected-counts.json` updated in the same change) to the selected names; and verify the T037 authority cases and both restated review probes pass under both validators
- [X] T041 Rework `I-010C`, `I-010D`, and `I-010E` to the selected shapes (rejection R4; FR-014): in `schemas/v2/participant-wake.schema.json` materialize the wake packet — self, room, actors, events, trigger, coverage, optional host-only continuation authority, and a separate `attention` object, not a wrapped classifier projection — preserving advice-free non-`WAKE` sources; in `schemas/v2/context-continuation.schema.json` define the selected continuation capability (`handle_id`, exact `bound_to`, before/after/around fetch capabilities, per-fetch caps, and optional expiry), the directional anchor-bearing fetch, and the identity-bearing page while keeping handle, binding, cursor, expiry, and fetch authority host-only; in `schemas/v2/attention-receipt.schema.json` add each stage's selected telemetry (observation request/schema/trigger/continuity IDs, snapshot sizes, coverage, and included event IDs; attention classifier identity, evidence, and transition-valve facts or the bypass fact with trusted provenance; participant-host wake source, packet sizes, delivered event IDs, expansion calls, and invocation and `sent`/`silent`/`unknown` outcome; transport hygiene and routing/send facts) while keeping the per-record stage-to-writer binding and the stream-level order/immutability checks unchanged; update the three stdlib adapters in `tests/v2/contract/schema_helpers.py`; rework the existing cases in `evals/v2/contract/downstream/cases.jsonl` (its `expected-counts.json` updated in the same change) and the red tests in `tests/v2/contract/test_participant_wake.py` and `tests/v2/contract/test_context_and_receipt.py` to the selected shapes preserving every S06/S07/binding/receipt-stage/S15/S16/010-V1 obligation; and verify the T038 authority cases pass under both validators
- [X] T042 Regenerate the attempt-3 aggregate evidence under the repaired schemas per the T035-generalized CHK107 semantics: re-record all three of `evidence/v2/contract/attention-request.jsonl` (re-recorded this attempt — the attempt-2 unchanged disposition does not carry forward because R4 re-enters every corpus family), `evidence/v2/contract/attention-decision.jsonl`, and `evidence/v2/contract/downstream.jsonl` as current-attempt records through the T021-enforced five-field writer; refresh the twelve-scene manifest in `evidence/v2/contract/README.md` with post-repair per-class partition counts, the authority class flagged with a named manifest field `authority_source_commit: c834e8c` on each authority-flagged record (CHK110, CHK121), both skip-regime counts, and the recorded CHK101 red-run identity with a named manifest field `red_run_failing_count` recorded beside each family's green partition-count row (CHK119); and record the exact pinned dual-validator command, the flagless governance check, and the full `python3 -m unittest` baseline result — the run whose green result the exact candidate commit must reproduce, with the packet-commit rerun owed at the handoff gate
- [X] T043 Re-execute every row of plan §Documentation Impact and Freshness against the attempt-3 candidate diff (CHK108): first re-run the inventory-derivation check (`ls *.md` plus `find docs -name '*.md' | grep -v archive`) against the attempt-3 diff so a doc file added or removed outside the eighteen already-listed rows has a detecting step (CHK120); re-validate the `UPDATE` `docs/contracts/nunchi-v2.md` so it documents the FR-014 selected field inventory and the authority-conformance corpus class alongside the five `@1` interfaces, the conditional FR-007 rule and closed routing-audit set under their selected names, the per-record FR-010 stage-to-writer binding, and the FR-012 runtime-adapter-only rules; re-verify each `NO_IMPACT` rationale against the attempt-3 diff; re-scan every routed `HANDOFF` delta so no row embeds a superseded local field name or narrowed-shape claim (CHK109) and re-route each, including `README.md`, to its accepting owner; and append the attempt-3 documentation section to `evidence/v2/contract/handoff.md` without rewriting the attempt-1 or attempt-2 sections
- [X] T044 Complete the CHK097–CHK111 adjudication by appending the implementation-cited verdicts to `evidence/v2/contract/checklist-adjudication.md` (append-only; T035's text verdicts and all earlier adjudications are never rewritten): CHK097 and CHK106 via this Phase 8 append and the reworded referential header; CHK098 by classifying every attempt-3 diff hunk against the bounded rework surface; CHK099–CHK101 via the T036–T038 landed authority classes and recorded red runs; CHK102–CHK104 via the T035 text fixes and the T039–T041 landed schemas; CHK105 via the T035-landed operational rule and T045's packet obligation; CHK107 via T042's regenerated records and explicit dispositions; CHK108–CHK109 via T043; CHK110 via T042's flagged manifest provenance; CHK111 by re-running the SC-006 boundary check — each verdict citing its landed task, file, and record anchors, and checking off each gate item in the requirements checklist only when its fix is verifiably on disk
- [X] T045 Append the attempt-3 proposed packet input to `evidence/v2/contract/handoff.md` after T043's documentation section, per T019's authoritative SC-005 enumeration as amended at `a183469`: single-valued commit identity (rejection R5) — the lifecycle candidate entry, the handoff attempt entry, this packet input, and the recorded corpus revision name the identical exact candidate commit, the actual handoff packet commit is recorded per the T035-landed CHK105 operational rule once it exists, and no placeholder, future-valued, or divergent identity appears anywhere in the delivered packet — with both defined commits carrying the green full-offline-baseline obligation (the packet-commit run performed at the handoff gate); the five interface versions and exact `schemas/v2/` paths; the staged-receipt writer map; the dual-validator pin and post-repair results over the shared corpus including the authority-class results and the CHK101 red-run record; the corpus revision with the unchanged downstream adapter obligation; the regenerated scene-to-record manifest; the updated rejected-case inventory; migration/provenance notes naming `evidence/v2/contract/review-2026-07-17-v2-integrator-attempt-2.md` and its three resolved blockers R4–R6; documentation dispositions/validation/reviewer from T043; and known limitations — verifying the task graph's referential execution-status wording agrees with the slice declarations and lifecycle evidence at the packet commit (rejection R6) — the later convergence, documentation-freshness, and handoff gates, not this checkbox, establish lifecycle state

## Phase 9: Task-Graph Text-Fidelity Correction (appended 2026-07-18, post-CHK112–CHK121)

**Correction source**: the formal reviewer's task-graph text-fidelity
addendum CHK112–CHK121, appended to
`specs/010-v2-contract/checklists/requirements.md` after `93f25a2` under
"Formal Reviewer Gate — Attempt-3 Task-Graph Addendum." That gate tests only
the written text of Phase 8's T035–T045 and the plan sections they cite —
completeness, clarity, consistency, and measurability as an instruction set —
never whether T035–T045 have been executed; the still-pending CHK097–CHK111
gate and T035's disposition of it are untouched and not reopened here. This
phase is strictly append-only at the level of completed history: tasks
T001–T034 remain checked and exactly as landed, and no evidence record or
attempt stream is rewritten. Because CHK112–CHK121 target the still-unchecked
text of T035–T043 and one plan.md table row — none of it completed history —
this phase's single task lands its fixes directly into those pending lines
and the cited plan section when executed, rather than layering a second
adjudication task above unrelated artifacts. Every fix below cites the exact
CHK item it closes.

- [X] T046 Adjudicate CHK112–CHK121 against the Phase 8 task-graph text and
  the plan sections it cites and, for each sustained gap, land the fix in the
  named artifact in the same commit before check-off — CHK112 add a
  disposition clause to T035 stating that CHK108, CHK109, and CHK110 require
  no spec/plan text fix and close entirely through the T042–T044
  implementation/evidence tasks, so their absence from T035's per-item list
  is not read as an unaddressed item; CHK113 add
  `tests/v2/contract/schema_helpers.py` to plan §Ordinary Repository
  Targets' "Contract tests" row alongside `tests/v2/contract/test_*.py`, so
  the shared adapter file T012–T014, T020–T023, and T039–T041 all edit has a
  matching artifact-class row; CHK114 add a decidable classification rule to
  T035's adjudication clause — a CHK item requires a landed text fix when the
  cited spec/plan section does not yet contain, verbatim, the wording the
  item's question describes as of this task graph's authoring commit; it
  requires only a consistency confirmation when that exact wording already
  exists at that commit — removing adjudicator discretion from the
  classification; CHK116 reword T036, T037, and T038 so each names the exact
  attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de` (the
  rejected pre-repair tree) as the red-run baseline in place of "a named
  pre-repair tree," so the red-then-green obligation is reproducible from the
  written instruction alone; CHK117 reword T040 so its request-ID clause
  defers the complete pre-validation and post-validation error-branch
  inventory — not only the pre-validation half — to the T035-landed CHK103
  rule, so T040 cannot be read as fixing "optional on a pre-validation error"
  as the whole rule while leaving the post-validation case silently
  unaddressed; CHK118 reword T039's event-union clause to drop the locally
  introduced `kind: reply|thread` and "universally required author/mention
  fields" phrasing — neither appears in FR-014's enumeration — replacing it
  with FR-014's own typed message/reaction/membership wording verbatim, and
  expand T041's continuation-capability clause to name `handle_id`, exact
  `bound_to`, before/after/around fetch capabilities, per-fetch caps, and
  optional expiry in full rather than the shortened "selected continuation
  capability" paraphrase, so no task carries a field-level claim FR-014 does
  not itself make; CHK119 reword T042 so the CHK101 red-run per-family
  failing counts are named as a specific manifest field —
  `red_run_failing_count` recorded beside each family's green partition-count
  row in the twelve-scene manifest table in `evidence/v2/contract/README.md`
  — replacing the descriptive "beside the green results" phrase; CHK120 add
  a clause to T043 requiring the inventory-derivation check (`ls *.md` plus
  `find docs -name '*.md' | grep -v archive`) to be re-run against the
  attempt-3 diff in addition to re-validating the eighteen already-listed
  rows, so a doc file added or removed outside those paths has a detecting
  task; CHK121 reword T042 so the authority-case provenance flag is a named
  manifest field — `authority_source_commit: c834e8c` recorded on each
  authority-flagged record in `evidence/v2/contract/README.md` — replacing
  the descriptive "flagged... with its pinned provenance" phrase — appending
  the per-item text verdicts with evidence anchors to
  `evidence/v2/contract/checklist-adjudication.md` (append-only; T025's and
  T035's text verdicts and all earlier adjudications are never rewritten),
  recording CHK115 (T035's CHK099 disposition already names both plan
  §Contract validation commands and §Acceptance Scenes and Evidence as
  needing the identical schema-expressible-partition wording, so the
  alignment this item asks for is already scoped by an existing fix
  commitment; no separate fix required here) as a consistency confirmation,
  and checking off each gate item in the requirements checklist only when its
  fix is verifiably on disk.

## Phase 10: Attempt-3 Rejection Rework (R7–R10)

**Correction source**: `evidence/v2/contract/review-2026-07-18-v2-integrator-attempt-3.md`,
rejecting candidate `7f9e81460d570e078c4bcbacb138f81c1b291455` on four
uncovered contract/runtime defects (R7 CRITICAL, R8 CRITICAL, R9 HIGH, R10
HIGH). Per the decision's required rework path and Zoe's direction for this
attempt, this phase performs the correction by direct edit rather than a new
bound `run speckit`; completed history — checked tasks T001–T046, every
evidence record, and all three rejected candidate/handoff attempt streams —
is preserved unchanged.

- [X] T047 Fix rejection R7–R10 against the exact findings in
  `review-2026-07-18-v2-integrator-attempt-3.md` and, for each, land the fix
  in the named artifact in the same commit before check-off — R7 encode
  `error.code` as the authority's open non-empty string (removing the local
  five-value enum and the `ERROR_KINDS` constant) and require `detail`
  (`required: ["code", "detail"]`) in `schemas/v2/attention-decision.schema.json`'s
  and `schemas/v2/attention-receipt.schema.json`'s error variants and their
  stdlib mirrors in `tests/v2/contract/schema_helpers.py`
  (`_validate_decision_error`, `_check_attention_body`); remove the locally
  added nullable event `timestamp` (`oneOf` with `const: null`) from
  `schemas/v2/attention-request.schema.json`'s three typed-event definitions
  and the matching `is not None` adapter branches, since the authority
  represents unknown timestamp by omission only; rework every corpus case,
  red test (`test_attention_decision.py`, `test_attention_request.py`,
  `test_context_and_receipt.py`), and `docs/contracts/nunchi-v2.md` passage
  that assumed the closed enum, the optional `detail`, or the nullable
  timestamp. R8 add `check_actor_reference_integrity` to
  `tests/v2/contract/schema_helpers.py` as a new document-shaped relational
  FR-012 partition class `actor-reference-integrity` (oracle-expected-valid,
  alongside `id-uniqueness`/`timestamp-order`/`advice-citation`/
  `trigger-membership`) enforcing that `self.actor_id` and every typed
  event's actor reference (`author_id`, `mentioned_actor_ids`,
  `subject_actor_id`, `caused_by_actor_id`) resolve to a key in `actors`; add
  `propertyNames` to `attention-request.schema.json`'s `actorMap` def
  (schema-expressible empty-key rejection) and the matching `_check_actor_map`
  adapter check; fix the `_BASE_REQUEST` fixture and
  `test_valid_request_with_alias_collision_stays_valid`, both of which
  omitted the self actor from its own `actors` map; add named valid/invalid
  corpus cases for self, author, mention, reaction, subject, and
  causal-actor references in `evals/v2/contract/attention-request/cases.jsonl`
  and `evals/v2/contract/downstream/cases.jsonl` with `expected-counts.json`
  updated in the same change. R9 extract `_check_self`/`_check_room` shared
  helper functions in `tests/v2/contract/schema_helpers.py` covering every
  nested optional field (`self.names`/`role`/`description`,
  `room.name`/`room.kind`) and call them from both
  `validate_attention_request` and `validate_participant_wake` in place of
  the wake validator's partial reimplementation; add negative oracle/adapter
  parity cases for the previously-uncovered nested fields. R10 extend
  `validate_continuation_fetch`'s `issued` handle-state shape and the
  `make_fetch_payload` fixture with the full issued continuation capability
  (`bound_to`, `can_fetch_before`/`can_fetch_after`/`can_fetch_around_event`,
  `max_events_per_fetch`/`max_bytes_per_fetch`) and a `host_context` field
  carrying the host's actual call context; compare `host_context` against
  the capability's exact `bound_to`, check the requested `direction` against
  its per-direction flag, and check the requested `max_events`/`max_bytes`
  against the issued caps — replacing the retired "a known, unexpired handle
  is by construction bound correctly" claim in the adapter docstring, spec
  FR-004, and `docs/contracts/nunchi-v2.md`; add binding-mismatch,
  unauthorized-direction, and both cap-overrun red cases to
  `evals/v2/contract/downstream/cases.jsonl` (`binding-expiry` partition)
  and `tests/v2/contract/test_context_and_receipt.py`. After all four fixes
  land: amend spec FR-002/FR-003/FR-004/FR-012 and the Edge Cases list for
  the corrected contract; regenerate all three aggregate evidence files and
  the README manifest through the T021-enforced five-field writer; append
  the attempt-4 documentation section to `evidence/v2/contract/handoff.md`;
  and return the header **Slice state** to `ACTIVE` on this same commit.

## Phase 11: Attempt-4 Rejection Rework (R10 completion)

**Correction source**: `evidence/v2/contract/review-2026-07-18-v2-integrator-attempt-4.md`,
rejecting candidate `0596d14c0579b0ad2530c4e273729dcc274f7034` at packet
`aa396ffebb552aeee91fd1b6a32a22538b2564c6`. R7, R8, and R9 are CLEARED by
that review and need no rework; R10 is only PARTIALLY CLEARED — the new
fetch checks compare a well-formed issued-state fixture correctly, but the
adapter never validates that the issued state is itself a complete, typed
`ContextContinuation` capability, and mishandles the selected optional
`expires_at`. Per the decision's required rework path, this phase performs
the correction by direct edit rather than a new bound `run speckit`;
completed history — checked tasks T001–T047, every evidence record, and all
four rejected candidate/handoff attempt streams — is preserved unchanged.

- [X] T048 Complete R10 against the exact findings in
  `review-2026-07-18-v2-integrator-attempt-4.md`: in
  `tests/v2/contract/schema_helpers.py`, make `validate_continuation_fetch`
  pass every issued handle state (minus its host-only `cursors` list)
  through the existing `_check_continuation` capability validator, so a
  missing or mistyped `handle_id`/`bound_to`/`can_fetch_before`/
  `can_fetch_after`/`can_fetch_around_event`/`max_events_per_fetch`/
  `max_bytes_per_fetch` rejects instead of being silently skipped by the
  binding/direction/cap comparisons; validate `host_context` through the
  existing `_check_continuation_binding` validator as the same closed
  four-field shape before comparing it against `bound_to` for exact
  equality, so two equally incomplete objects cannot pass by matching each
  other; only parse and compare `expires_at` when the key is present
  (the selected design's own member is optional — its absence is valid,
  not a missing-timestamp error); and wrap the `fetch_time`-versus-
  `expires_at` comparison so a `TypeError` from mixed timezone-aware/naive
  values returns a validation error instead of raising. Add the six named
  unit probes to `tests/v2/contract/test_context_and_receipt.py`
  (`FetchTimeBindingCases`) and the matching valid-no-expiry plus six
  invalid `binding-expiry` corpus cases (missing/mistyped binding field,
  missing/mistyped direction flag, missing/mistyped cap, mixed-timezone
  comparison) to `evals/v2/contract/downstream/cases.jsonl` with
  `expected-counts.json` updated in the same change; correct the retired
  "a known, unexpired handle is by construction bound correctly" claim
  remaining in `docs/contracts/nunchi-v2.md`'s `I-010D` section (the
  runtime-adapter-only rules list was already corrected by T047); regenerate
  all three aggregate evidence files and the README manifest through the
  T021-enforced five-field writer; append the attempt-5 documentation
  section to `evidence/v2/contract/handoff.md`; and return the header
  **Slice state** to `ACTIVE` on this same commit.

## Phase 12: Attempt-5 Rejection Rework (R11)

**Correction source**: `evidence/v2/contract/review-2026-07-18-v2-integrator-attempt-5.md`,
rejecting candidate `1709c714717cd2735da2e9e08487fe8f02f2b930` at packet
`b9ccace4e35ec78f80f73c69d70184e39f99528b`. R7 through R10 are CLEARED by
that review and need no rework. It found one new defect: a malformed
(unhashable) or duplicate `handle_id`/`direction` in the request or an
issued state raises `TypeError` from a bare dictionary-key operation
instead of returning a validation error, and a duplicate issued
`handle_id` with a conflicting `bound_to` silently resolves last-write-wins
instead of rejecting. Per the decision's required rework path, this phase
performs the correction by direct edit rather than a new bound
`run speckit`; completed history — checked tasks T001–T048, every evidence
record, and all five rejected candidate/handoff attempt streams — is
preserved unchanged.

- [X] T049 Fix R11 against the exact findings in
  `review-2026-07-18-v2-integrator-attempt-5.md`: in
  `tests/v2/contract/schema_helpers.py`, make `validate_continuation_fetch`
  build its issued-handle index from only validated non-empty string
  `handle_id` values (never an array/object), track and reject a duplicate
  `handle_id` across issued states (removing it from the index rather than
  silently keeping the last-seen capability), and return early — without
  ever using the raw value as a dictionary key — the moment the request's
  own `handle_id` is not a non-empty string or its `direction` is not one
  of the three selected values (`validate_context_continuation` already
  reports the correct message for both). Add the seven named unit probes to
  `tests/v2/contract/test_context_and_receipt.py` (`FetchTimeBindingCases`:
  array/object request `handle_id`, array/object request `direction`,
  array/object issued `handle_id`, duplicate conflicting `handle_id`) and
  the matching five invalid `binding-expiry` corpus cases to
  `evals/v2/contract/downstream/cases.jsonl` with `expected-counts.json`
  updated in the same change; regenerate all three aggregate evidence files
  and the README manifest through the T021-enforced five-field writer;
  append the attempt-6 documentation section to
  `evidence/v2/contract/handoff.md`; and return the header **Slice state**
  to `ACTIVE` on this same commit.

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
- Selected-design-fidelity phase: T035 precedes the check-off of T036–T038
  (their class placement and red-run recording follow the T035-landed CHK099
  and CHK101 rules; case authoring may begin earlier) and precedes T044.
  T036 precedes T039, T037 precedes T040, and T038 precedes T041 — each
  family's authority cases are recorded red before that family's schema
  repair lands. T039, T040, and T041 serialize in that order on the shared
  `tests/v2/contract/schema_helpers.py`; their schema, corpus, and test
  targets are otherwise disjoint. T036–T041 precede T042; T042 precedes
  T043 (documentation re-validates against the repaired shapes and recorded
  results); T035–T043 precede T044; T043 and T044 precede T045. The
  attempt-3 sections of `evidence/v2/contract/handoff.md` append in the
  same documentation-then-packet order as prior attempts, after the
  attempt-2 sections and never rewriting them.
- Task-graph text-fidelity phase: T046 corrects the still-unchecked text of
  T035, T036, T037, T038, T039, T040, T041, T042, and T043, plus one plan.md
  row, before any of them may be worked. Its task ID is highest in
  authorship order, but its execution precedes T035–T045 entirely — this
  override is stated explicitly because CHK112 asks that the disposition of
  CHK108–CHK110 be explicit in this section too: those three items require
  no spec/plan text fix and close entirely through T042–T044, not through
  T046 or T035. T046 has no other upstream dependency and blocks nothing
  outside Phase 8.
- Rejection-rework phase (attempt 3 → 4): T047 has no upstream dependency
  within this task graph — its four fixes (R7, R8, R9, R10) target disjoint
  schema/adapter/corpus/test surfaces within `schemas/v2/attention-decision
  .schema.json`, `schemas/v2/attention-receipt.schema.json`,
  `schemas/v2/attention-request.schema.json`, and
  `tests/v2/contract/schema_helpers.py`, and may be worked in any order —
  but its evidence-regeneration and `Slice state` sub-steps run last, after
  all four fixes land and the full dual-validator baseline is green.
- Rejection-rework phase (attempt 4 → 5): T048 depends on T047 (it edits the
  same `validate_continuation_fetch` function T047 introduced) and has no
  other upstream dependency; its evidence-regeneration and `Slice state`
  sub-steps run last, after the full dual-validator baseline is green.
- Rejection-rework phase (attempt 5 → 6): T049 depends on T048 (it edits the
  same `validate_continuation_fetch` function) and has no other upstream
  dependency; its evidence-regeneration and `Slice state` sub-steps run
  last, after the full dual-validator baseline is green.

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
- T036–T038 target separate corpus directories and run in parallel once the
  T035-landed CHK099/CHK101 rules exist; the schema-repair chain
  T039→T040→T041 serializes on `tests/v2/contract/schema_helpers.py` while
  remaining disjoint from the T036–T038 authoring surfaces.

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
- Phase 8 is the append-only correction for the v2-integrator rejection of
  the attempt-2 candidate `001fdf85acd5098264c4975559c97114aa7278af` at
  packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de` (blockers R4–R6):
  completed history — checked tasks, both rejected attempt streams, and all
  prior evidence sections — is preserved unchanged; the single non-append
  change in this refresh is the header **Execution status** line, reworded
  to the referential form Decision R6 and CHK106 require; and every appended
  task traces to blocker R4/R5/R6, a requirement clarified at `a183469`, or
  a CHK097–CHK111 gate item.
- Authority-conformance cases are embedded ordinary-path corpus copies with
  pinned provenance — drawn from the selected design at `c834e8c`, recorded
  under existing scene IDs, counted as their own named class within the
  schema-expressible partition, and flagged as authority cases in the
  manifest — so the verbatim claim is verifiable from repository artifacts
  alone and no build or test path reads the design document or a
  SpecKit-managed path at run time (CHK110).
- Attempt-3 evidence semantics (CHK107, generalized in writing by T035):
  every attempt regenerates all aggregate JSONL files and the README
  manifest as current-attempt records, appends one section per attempt to
  `evidence/v2/contract/handoff.md` and
  `evidence/v2/contract/checklist-adjudication.md`, and gives any evidence
  file left unchanged an explicit manifest disposition; attempt 3 re-records
  `evidence/v2/contract/attention-request.jsonl` because R4 re-enters every
  corpus family.
- Phase 9 is the append-only correction for the task-graph text-fidelity gate
  CHK112–CHK121: completed history (checked tasks T001–T034, every evidence
  record, both rejected attempt streams) is preserved unchanged; T046 is the
  sole appended task, and its execution amends the still-pending text of
  T035–T038, T039, T041, T042, and T043 plus plan §Ordinary Repository
  Targets — none of it completed history — rather than adding new
  implementation surface; every fix traces to a named CHK112–CHK121 item.
- Phase 10 is the rework for the v2-integrator rejection of the attempt-3
  candidate `7f9e81460d570e078c4bcbacb138f81c1b291455` at packet commit
  `6fa3996fd7cf92cd6157945245136a8c55cb69cc` (blockers R7–R10): completed
  history — checked tasks T001–T046, all three rejected attempt streams, and
  every prior evidence section — is preserved unchanged. Per the decision's
  required rework path, this phase corrects the artifacts directly rather
  than restarting bound-workflow scaffolding; the header **Slice state** line
  returns to `ACTIVE` on the same commit as T047's fixes, and a new attempt-4
  candidate/handoff entry is appended once verification is green.
- Attempt-4 evidence semantics (T047): the same per-attempt regeneration
  rule as attempts 2 and 3 applies — all three aggregate JSONL files and the
  README manifest regenerate as current-attempt records, and
  `evidence/v2/contract/handoff.md` and
  `evidence/v2/contract/checklist-adjudication.md` append a new section
  without rewriting the attempt-1/2/3 sections.
- Phase 11 is the rework for the v2-integrator rejection of the attempt-4
  candidate `0596d14c0579b0ad2530c4e273729dcc274f7034` at packet commit
  `aa396ffebb552aeee91fd1b6a32a22538b2564c6` (R10 partially cleared): R7,
  R8, and R9 are CLEARED and need no rework; completed history — checked
  tasks T001–T047, all four rejected attempt streams, and every prior
  evidence section — is preserved unchanged. The header **Slice state**
  line returns to `ACTIVE` on the same commit as T048's fix, and a new
  attempt-5 candidate/handoff entry is appended once verification is green.
- Attempt-5 evidence semantics (T048): the same per-attempt regeneration
  rule applies — all three aggregate JSONL files and the README manifest
  regenerate as current-attempt records, and `evidence/v2/contract/
  handoff.md` appends a new section without rewriting the attempt-1/2/3/4
  sections.
- Phase 12 is the rework for the v2-integrator rejection of the attempt-5
  candidate `1709c714717cd2735da2e9e08487fe8f02f2b930` at packet commit
  `b9ccace4e35ec78f80f73c69d70184e39f99528b` (R11): R7 through R10 are
  CLEARED and need no rework; completed history — checked tasks
  T001–T048, all five rejected attempt streams, and every prior evidence
  section — is preserved unchanged. The header **Slice state** line
  returns to `ACTIVE` on the same commit as T049's fix, and a new
  attempt-6 candidate/handoff entry is appended once verification is
  green.
- Attempt-6 evidence semantics (T049): the same per-attempt regeneration
  rule applies — all three aggregate JSONL files and the README manifest
  regenerate as current-attempt records, and `evidence/v2/contract/
  handoff.md` appends a new section without rewriting the attempt-1/2/3/4/5
  sections.

## Phase 13: Post-Acceptance Amendment A3 — Privileged Action Authorization

This bounded successor adds only `I-010F PrivilegedActionAuthorizationV2@1`.
It does not reopen I-010A–E, implement an executor, or start any dependent
slice. The amendment record remains append-only and A2 remains effective until
`v2-integrator` accepts A3's exact successor.

- [X] T050 Record the immutable A3 predecessor, assignment, fixed scope, task
  manifest, and zero-blocker analysis in
  `evidence/v2/contract/amendment-A3-privileged-action-authorization.md`.
- [X] T051 Define the closed `I-010F@1` schema and its stdlib validator for
  exact digest, trusted requester/origin, capability/scope, policy,
  expiry/revocation/persistence, decision, and host-only approval facts.
- [X] T052 Add the focused S18 tests and corpus: dual-validator document
  conformance plus runtime-only correlation, substitution, approval, replay,
  expiry, revocation, and one-use boundary cases.
- [X] T053 Regenerate the A3 evidence and manifest at the exact candidate tree
  with stable case IDs, validator identities, expected/observed results, and
  authoritative per-class counts.
- [X] T054 Update `docs/contracts/nunchi-v2.md` and create
  `docs/security/privileged-action-authorization.md`, including the explicit
  execution and persistence limitations.
- [X] T055 Run the focused dual-validator command, full offline baseline,
  governance/CLI checks, and eval discovery; then prepare the exact candidate
  and A3 packet for separate `v2-integrator` review.

## A3 Dependencies & Execution Order

T050 precedes T051. T051 precedes T052. T052 precedes T053 and T054; T053 and
T054 precede T055. No downstream slice starts until separate A3 acceptance
records its exact effective commit and packet.
