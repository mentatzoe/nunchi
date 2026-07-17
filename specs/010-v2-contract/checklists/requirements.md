# Specification Quality Checklist: V2 Contract

**Purpose**: Validate that the contract-slice requirements are complete, clear,
measurable, and bounded before slice activation is accepted

**Created**: 2026-07-11

**Slice specification**: [spec.md](../spec.md)

## Content and Boundary Quality

- [x] CHK001 Is the `PLANNED` slice distinguished explicitly from current V1 implementation truth — program authority `GRANTED` (recorded 2026-07-16) but tasks `DORMANT` until the slice is independently `READY`? [Clarity, Spec §Control-Plane Boundary]
- [x] CHK002 Are product schemas, tests, evals, evidence, and docs assigned only to ordinary repository paths? [Consistency, Spec §Control-Plane Boundary]
- [x] CHK003 Is exactly one accountable owner named, with a non-silent contract-change handoff? [Completeness, Spec §Interface Summary]
- [x] CHK004 Are implementation, classifier, collector, harness, release, and promotion work explicitly excluded? [Coverage, Spec §Explicit Exclusions]

## Interface Requirement Completeness

- [x] CHK005 Are all five canonical interface names, versions, consumers, and feeds stated consistently? [Traceability, Spec §Interface Summary, FR-001–FR-010]
- [x] CHK006 Are exact self binding and loose participant descriptors distinguished without ambiguity? [Clarity, Spec §FR-002]
- [x] CHK007 Are actor-targeted mentions distinct from `mentions_room`, and are event order, other literal relations, unresolved references, coverage, visibility, and restart limits specified? [Completeness, Spec §FR-003–FR-004]
- [x] CHK008 Are all four ok transitions, exact no-classifier preattention bypass, and malformed-evidence error outcome mutually exclusive? [Completeness, Spec §FR-005–FR-007]
- [x] CHK009 Are `PREATTENTION_BYPASS`, host-only continuation authority, classifier-safe expansion flags, and immutable singly owned receipt stages defined consistently? [Consistency, Spec §FR-008–FR-010]
- [x] CHK010 Are V1 translation, reply fields, inferred roster, and social-ledger state unambiguously forbidden? [Coverage, Spec §FR-011]

## Scenario and Edge-Case Coverage

- [x] CHK011 Do acceptance scenarios cover primary valid flows, bypass, invalid transitions, host-secret projection leaks, binding attacks, immutable staged receipts, unknown facts, and participant silence? [Coverage, Spec §User Scenarios & Testing]
- [x] CHK012 Are duplicate IDs, contradictory timestamps, omitted relation targets, non-finite values, expired/cross-bound continuation, bypass-field contamination, and cross-owner receipt mutation addressed? [Edge Case, Spec §Edge Cases]
- [x] CHK013 Is it explicit that advice cannot appear on DEFER/SUPPRESS, cite nonexistent events, or contain reply prose? [Security, Spec §Edge Cases, FR-005]

## Acceptance Criteria and Dependencies

- [x] CHK014 Do Draft 2020-12 and stdlib runtime adapters consume the same corpus under the exact offline `jsonschema==4.26.0` test command, with aggregate records carrying `scene_id` and a complete README manifest? [Measurability, Spec §SC-001–SC-006]
- [x] CHK015 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted declared dependencies (none), active `v2-contract-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/contract/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox? [Lifecycle, tasks.md §Slice activation]
- [x] CHK016 Does documentation freshness inventory every exact known affected path, require the owned contract-doc `UPDATE`, route exact shared/current `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK017 Does activation evidence require `Accepted dependencies: none`, `Dependency commits: none`, and `Dependency acceptance references: none`, while candidate/handoff evidence is append-only, rejection appends `REJECTED` and returns the same owner to `ACTIVE`, requires a new bound run rather than resume of the completed run, preserves every prior attempt, and convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- All items are checked because the specification presently satisfies these
  requirement-quality tests. They do not claim that any V2 schema or product
  behavior has been implemented.

## Formal Reviewer Gate (appended 2026-07-17)

**Purpose**: Requirement-quality gate for the formal reviewer covering scope,
parity, interface, evidence, documentation freshness, and control-plane
boundary requirements. These items test what the slice artifacts say — their
completeness, clarity, consistency, and measurability — not whether any
implementation works. They are appended unchecked for the reviewer's pass and
do not alter the checked baseline above.

### Scope Requirement Quality

- [x] CHK018 Is the split between this planning baseline's outputs (control-plane artifacts only) and authorized-implementation outputs (schemas, tests, evals, evidence, product docs) stated identically in spec, plan, and tasks, with no artifact class assigned to both sides? [Consistency, Spec §Control-Plane Boundary; Plan §Summary; Tasks §Notes]
- [x] CHK019 Is every item in the exclusions list traceable to a named later owner or decision (slices 020/030/040 ownership, release/promotion decisions), so a reviewer can distinguish "excluded and owned elsewhere" from "unplanned anywhere"? [Traceability, Spec §Explicit Exclusions]
- [x] CHK020 Are the downstream start conditions quantified the same way everywhere — 020/030 only after each consumer separately accepts the T019-derived packet, 040 additionally after the 020/030 handoffs — with no looser wording in the plan than in the task graph? [Consistency, Plan §Integration Strategy; Tasks §Dependencies & Execution Order]
- [x] CHK021 Is the procedure a dependent slice must follow to request a contract change specified beyond "explicit return handoff and re-analysis" — or is the required content of that return handoff unspecified? [Gap, Plan §Integration Strategy; Spec §Explicit Exclusions]

### Parity Requirement Quality

- [x] CHK022 Is dual-validator parity defined measurably — one corpus, each case loaded once, identical expected results through both the Draft 2020-12 oracle and the stdlib runtime adapter — with the baseline skip-accounting rule (explicit counted skips, no silent skips, loud failure only under the pinned offline command) stated consistently across spec, plan, and T001? [Measurability, Spec §FR-012; Plan §Contract validation commands; Tasks T001]
- [x] CHK023 Do the requirements pin how downstream runtime owners inherit the conformance corpus — which corpus revision, verified before each owner's own handoff, recorded where — or is cross-slice corpus versioning unaddressed? [Gap, Plan §Contract validation commands; Tasks §Dependencies & Execution Order]
- [x] CHK024 Is SC-002's "byte-for-byte at the semantic field level" internally coherent and objectively testable — do the requirements define what preservation means under JSON re-serialization (key order, whitespace, unicode escapes)? [Ambiguity, Spec §SC-002]
- [x] CHK025 Do the requirements keep parity-claim boundaries explicit — a green contract suite proves mechanics only, and the classifier-DEFER/margin-DEFER transition remains independently evidence-gated rather than a schema-compatibility fact? [Clarity, Tasks §Notes; Plan §Technical Context]
- [x] CHK026 Can the final integrator reject an interface mismatch deterministically from the written criteria alone — exact `@1` versions, exact `schemas/v2/` paths, and SC-004's deterministic failure on deletion or incompatible edit? [Measurability, Spec §SC-004; Plan §Produces]

### Interface Requirement Quality

- [x] CHK027 Does each of I-010A through I-010E appear with the same name, version, schema path, and owning task across the spec interface summary, plan produces list, and tasks T006/T009/T012–T014, with none missing or renamed? [Traceability, Spec §Interface Summary; Plan §Produces; Tasks T006–T014]
- [x] CHK028 Are breaking-edit rules for the `@1` versions complete — explicit owner handoff plus dependent re-analysis — and consistent with sole-owner editing of `schemas/v2/**` until handoff acceptance? [Consistency, Spec §Assumptions; Plan §Integration Strategy]
- [x] CHK029 Is the classifier projection's permitted content written as a closed enumeration (coverage and expansion capability booleans only), so any additional field is decidably a host-secret leak rather than arguably allowed? [Clarity, Spec §FR-004, §FR-009]
- [x] CHK030 Is the FR-013 cross-slice reference to the attention engine's advice contract (030 FR-005) exact enough — slice, requirement ID, and rule content restated locally — for a reviewer to detect drift between the two artifacts? [Traceability, Spec §FR-013]
- [x] CHK031 Is the decision union closed and mutually exclusive in writing — only `ok`/`bypass`/`error` statuses, branch-specific field sets that cannot co-occur, and bypass explicitly not a successful disposition pairing? [Completeness, Spec §FR-005–FR-006]
- [x] CHK032 Are receipt-stage writer obligations specified per stage — append only one's own stage, never mutate prior or fill future stages — together with explicit unknown/unavailable values, so a violating record is identifiable from the requirement text alone? [Completeness, Spec §FR-010]

### Evidence Requirement Quality

- [x] CHK033 Does every scene row name a concrete ordinary evidence target and required observation, and does every scene ID cited by tasks T002–T018 (S01–S03, S05–S09, S15, S16, 010-Preattention-bypass, 010-V1) appear in the plan's scene table exactly once? [Traceability, Plan §Acceptance Scenes and Evidence; Tasks T002–T018]
- [x] CHK034 Are the mandatory aggregate-record fields (`scene_id`, stable `case_id`, validator identity, expected result, observed result) and the README manifest's coverage of all twelve scene rows stated measurably? [Measurability, Plan §Acceptance Scenes and Evidence; Tasks T018]
- [x] CHK035 Do spec SC-005, the plan owner-handoff section, and task T019 enumerate the same handoff-packet contents — or do items such as the rejected-case inventory, migration/provenance notes, and documentation dispositions appear in some lists but not others? [Conflict, Spec §SC-005; Plan §Owner Handoff; Tasks T019]
- [x] CHK036 Are lifecycle evidence artifacts (activation, candidate, handoff, acceptance) and contract-run evidence (JSONL results, README manifest) kept distinct, each with an exact ordinary path and writer, and none under a SpecKit-managed path? [Consistency, Spec §Control-Plane Boundary; Plan §Project Structure]
- [x] CHK037 Is the evidence-sufficiency rule explicit that a table entry or checked task box is not evidence — ordinary handoff evidence must record reviewed paths, rationale, commands, and results? [Clarity, Plan §Documentation Impact and Freshness; Constitution §VI]

### Documentation Freshness Requirement Quality

- [x] CHK038 Does every documentation-impact row carry exactly one disposition with an owning task, and either validation steps (`UPDATE`), a concrete rationale (`NO_IMPACT`), or an exact claim delta plus accepting owner (`HANDOFF`), with no directory wildcards or generic rows? [Completeness, Plan §Documentation Impact and Freshness]
- [x] CHK039 Are the `NO_IMPACT` rationales written so they can be re-verified against the exact candidate diff, with the re-verification obligation and its recording location (`evidence/v2/contract/handoff.md`) stated? [Measurability, Plan §Documentation Impact and Freshness]
- [x] CHK040 Is the `UPDATE`/`HANDOFF` split consistent with ownership — `UPDATE` only for the slice-owned `docs/contracts/nunchi-v2.md`, `HANDOFF` with accepting owner `v2-integrator` for integrator-owned current-state wording including `README.md`, and no `HANDOFF` for a slice-owned document? [Consistency, Plan §Documentation Impact and Freshness]
- [x] CHK041 Is the documentation freshness surface bounded in writing — `docs/archive/` excluded as dated history — so a reviewer can classify an unlisted document as either a matrix gap or legitimately out of scope? [Coverage, Plan §Documentation Impact and Freshness]
- [x] CHK042 Do the spec documentation-freshness section and the plan matrix agree on the affected-file inventory — every spec-named `HANDOFF`/`UPDATE` surface has exactly one matching plan row, and plan-only `NO_IMPACT` rows remain consistent with the spec's affected-docs claim? [Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

### Control-Plane Boundary Requirement Quality

- [x] CHK043 Is the slice-directory inventory a written closed allowlist (spec.md, plan.md, tasks.md, checklists/requirements.md, "no other file or directory"), with the enforcing boundary check named by its exact flagless command in T018? [Measurability, Plan §Project Structure; Spec §SC-006; Tasks T018]
- [x] CHK044 Are the constitutionally disabled SpecKit outputs (`data-model.md`, `contracts/`, `quickstart.md`) absent from every planned output list, with interface detail explicitly labeled a planning summary rather than an embedded product contract? [Consistency, Plan §Slice Interfaces; Constitution §VII]
- [x] CHK045 Do the requirements keep governance lifecycle state (`PLANNED` through `ACCEPTED`) out of runtime, classifier, receipt, and social state — no contract field, fixture, or evidence record is required to carry slice-lifecycle facts? [Coverage, Spec §Control-Plane Boundary; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK046 Is the dev/test-only `jsonschema==4.26.0` constraint stated consistently at every dependency claim — spec assumptions, plan technical context, tasks notes, and the `docs/INSTALL.md` `NO_IMPACT` rationale — with no wording that permits it as a runtime or install dependency? [Consistency, Spec §Assumptions; Plan §Technical Context; Tasks §Notes]

## Formal Reviewer Gate — Post-Round-3 Delta Addendum (appended 2026-07-17)

**Reviewer adjudication (2026-07-17, cc-session-1)**: CHK018–CHK063
adjudicated against the artifacts at the slice-readiness gate of bound run
`speckit-010-20260717T003300631902Z`; per-item verdicts and evidence anchors
recorded in `evidence/v2/contract/checklist-adjudication.md`. CHK019's gap
(unnamed later owners in Explicit Exclusions) was fixed in the same readiness
commit before check-off; all other items were sustained as written.

**Purpose**: Extend the formal reviewer gate (CHK018–CHK046) to the artifacts
as amended after that gate was appended: the FR-012 validator-expressiveness
partition, the round-3 LOW resolutions (non-finite sentinel encoding, FR-003
uniqueness scope, the SC-002 semantic-field-level rewrite, FR-013 label-safe
advice keying), and the pinned task-manifest copy rule. These items test the
amended requirement text only — not any implementation — and are appended
unchecked for the reviewer's pass. Note: CHK024 quotes SC-002 wording
("byte-for-byte") that the round-3 amendment has since replaced; CHK054 tests
the current SC-002 text, and CHK024 should be adjudicated against the wording
it cites as historical context.

### Scope Requirement Quality (delta)

- [x] CHK047 Is the downstream obligation that every runtime owner must pass its adapter over the identical conformance corpus before its own handoff carried into the T019 packet contents (or another artifact a consumer must accept), rather than existing only as a floating sentence in the plan's validation section and task dependencies? [Gap, Plan §Contract validation commands; Tasks T019, §Dependencies & Execution Order]

### Parity Requirement Quality (delta)

- [x] CHK048 Do spec FR-012, the plan's contract-validation section, and T001 state the identical closed set of runtime-adapter-only case classes — or does the plan's five-item parenthetical (cross-item uniqueness, order agreement, cross-document citations, fetch-time state, stage sequences) omit `trigger membership` from the spec's six-class enumeration? [Conflict, Spec §FR-012; Plan §Contract validation commands; Tasks T001]
- [x] CHK049 For each runtime-adapter-only class, is the oracle-side treatment decided in writing — which classes the oracle validates as `expected: valid` versus which it skips by explicit class — or is the "expecting valid or skipping" choice left per-case to the implementer? [Ambiguity, Spec §FR-012; Plan §Contract validation commands]
- [x] CHK050 Is the authoritative source of the expected per-class case counts pinned — where the expectation is recorded, who updates it when the corpus grows, and what "asserted loudly" fails against — so the no-silent-shrink rule is objectively checkable rather than self-referential to whatever the corpus currently contains? [Measurability, Gap, Spec §FR-012, §SC-001; Tasks T001]
- [x] CHK051 Are the two distinct skip regimes — baseline-run oracle-absence skips (explicit counted skips under `python3 -m unittest`) and partition-class skips (oracle skipping semantic classes under the pinned dual-validator command) — separately named and separately counted, so one regime's expected skips cannot mask the other's missing cases? [Clarity, Plan §Contract validation commands; Tasks T001]
- [x] CHK052 Does every FR-012 semantic/relational class trace to at least one named red case in the task graph — in particular `trigger membership` (trigger absent from `events`) and `fetch-time binding/expiry state`, which appear in the class list and Edge Cases but are not named in the T002–T005/T007/T010/T015 case enumerations the way duplicate-ID and timestamp-order cases are? [Coverage, Gap, Spec §FR-012, §Edge Cases; Tasks T002–T005]
- [x] CHK053 Is the non-finite sentinel vocabulary complete and singly owned — the Edge Cases name string `"NaN"`/`"Infinity"` but not negative infinity, which FR-007's finite-`[0,1]` rule equally forbids — and is the decode responsibility (corpus loader) stated where the shared harness is specified (T001) so both validators receive identical decoded cases? [Completeness, Spec §Edge Cases, §FR-007; Tasks T001]
- [x] CHK054 Is SC-002's semantic-field-level equality decidable from the text — do "compare equal as exact strings/numbers" and preserved event-array order define number-comparison semantics under JSON parsing (e.g., `1.0` versus `1`, float round-trip) precisely enough that both validators and the fixture checks must reach the same verdict? [Measurability, Spec §SC-002]
- [x] CHK055 Is the performance goal "full corpus dual-validator run completes offline in under a minute on the reference machine" measurable — is the reference machine identified, and is any task assigned to observe the goal — or is it intentionally advisory? [Measurability, Plan §Performance Goals]

### Interface Requirement Quality (delta)

- [x] CHK056 Is the advice-presence key named identically at every statement — FR-013 keys I-010B advice to the classifier disposition `WAKE` and I-010C advice to `source: WAKE`, while FR-005 says only "`WAKE`-only grounded advice" and the US3 scenario says "`WAKE`-source packets" — so no reading permits advice keyed to the effective disposition instead? [Consistency, Spec §FR-005, §FR-013, §User Scenarios & Testing; Tasks T003–T004]
- [x] CHK057 Are the canonical receipt-stage order and the validity of partial sequences specified — FR-010's "prior records" and "future stages" presuppose an order over observation/attention/participant-host/transport, and scenes require in-flight and silence outcomes — so a reviewer can decide from the text whether a receipt lacking later stages is valid-in-progress or invalid? [Gap, Spec §FR-010, §FR-012, §Edge Cases]
- [x] CHK058 Is the evaluation locus of FR-003's continuity-scope ID uniqueness specified for the cross-document case — when a continuation page's events collide with the originating request's IDs, is rejection defined at fetch time, at merge identity, or both, and which runtime-adapter check owns it? [Clarity, Spec §FR-003, §FR-009, §FR-012]

### Evidence Requirement Quality (delta)

- [x] CHK059 Is the task-manifest copy rule complete and stated consistently in plan and tasks — exact field names (`Initial task IDs`/`Initial tasks SHA256` into activation; `Completed task IDs`/`Tasks SHA256` into each candidate attempt), plus which task-graph revision each later candidate attempt hashes after convergence appends tasks and a new bound run begins, while the immutable activation retains the initial values? [Completeness, Plan §Task manifest; Tasks §Task manifest, §Rejection / rework]
- [x] CHK060 Are the two writes to `evidence/v2/contract/handoff.md` (T017 documentation dispositions; T019 packet input) specified as compatible contributions to one file — ordering, no overwrite of the earlier content — and is its distinction from the lifecycle attempt stream `slice-handoff.md` stated at every mention of either file? [Consistency, Spec §Documentation Freshness; Tasks T017, T019]
- [x] CHK061 Is the plan's designation "T019's enumeration is authoritative" for the handoff packet visible from the spec side — can a reviewer applying SC-005 alone learn that T019 resolves any inventory divergence, or does the authority rule live only in the plan? [Consistency, Spec §SC-005; Plan §Owner Handoff; Tasks T019]

### Documentation Freshness Requirement Quality (delta)

- [x] CHK062 Does the `docs/contracts/nunchi-v2.md` `UPDATE` validation cover the runtime-adapter-only semantic rules — the row validates interface names/versions, bypass/error separation, links, and examples, but the FR-012 partition means the semantic/relational rules exist outside the schemas, so a contract doc validated only against the schemas would omit them for downstream implementers? [Gap, Plan §Documentation Impact and Freshness; Spec §FR-012]

### Control-Plane Boundary Requirement Quality (delta)

- [x] CHK063 Is ownership split cleanly between the spec-owned partition vocabulary (the closed class list in FR-012) and ordinary-path-owned case membership and per-class counts (tests/evals), so corpus growth never requires editing a SpecKit artifact and no per-case product data is embedded in this slice directory? [Clarity, Spec §FR-012, §Control-Plane Boundary; Tasks T001]

## Formal Reviewer Gate — Refresh Addendum (appended 2026-07-17, post-`e4ada5c`)

**Purpose**: Extend the formal reviewer gate to the artifacts as refreshed
after the adjudicated CHK047–CHK063 pass: the per-interface corpus directories
with their authoritative `expected-counts.json` files, the completed
file-by-file documentation-impact matrix, FR-012's fixed per-class oracle
treatment, FR-010's prefix-partial receipt rule, and FR-007's `@1` permanence
rule. These items test the refreshed requirement text only — scope, parity,
interface, evidence, documentation freshness, and control-plane boundary
quality — not any implementation. They are appended unchecked for the
reviewer's pass; adjudicated CHK verdicts above are not reopened.

### Scope Requirement Quality (refresh)

- [x] CHK064 Is the commit identifier a dependent consumer accepts named consistently — the plan's integration strategy has slices 020/030 "accept and record the tagged contract commit," while the spec interface summary and the T019 packet require only the exact commit — or does "tagged" introduce a git-tag obligation stated nowhere else? [Ambiguity, Plan §Integration Strategy; Spec §Interface Summary; Tasks T019]
- [x] CHK065 Now that the slice headers declare `ACTIVE`, do the artifacts state the current execution status anywhere, or only the `PLANNED`-conditioned dormancy rule ("`DORMANT` while the slice remains `PLANNED`"), leaving the status of tasks under `ACTIVE` implied rather than written? [Clarity, Tasks §header; Spec §Control-Plane Boundary]

### Parity Requirement Quality (refresh)

- [x] CHK066 Is the spec's fixed per-class oracle treatment (four document-shaped relational classes oracle-expected-valid; fetch-time binding/expiry state and receipt-stage sequence rules oracle-class-skipped) restated or explicitly deferred to in the plan's contract-validation section — or does the plan's looser "expecting valid or skipping by explicit class" wording still permit an implementer following the plan alone to choose a different class-to-treatment mapping? [Consistency, Spec §FR-012; Plan §Contract validation commands]
- [x] CHK067 Is the corpus-directory inventory itself asserted — exactly the three named directories `attention-request/`, `attention-decision/`, and `downstream/`, each with its own authoritative per-class `expected-counts.json` — so a wholly missing or unregistered corpus directory fails loudly rather than passing vacuously under per-directory count assertions that iterate only over directories found? [Gap, Plan §Acceptance Scenes and Evidence; Tasks T001, T007, T010, T015]

### Interface Requirement Quality (refresh)

- [x] CHK068 Is FR-007's permanence rule — the legacy-evidence field is required for the whole `@1` major version and its removal is a breaking `@2` edit — consistent with the Assumptions' breaking-edit contract (explicit owner handoff plus dependent re-analysis) and with the independently gated margin retirement, so no reading permits dropping the field at `@1` once margin evidence lands? [Consistency, Spec §FR-007, §Assumptions; Plan §Technical Context]
- [x] CHK069 Beyond declaring a prefix-partial receipt valid-in-progress, does FR-010 decide the remaining stage-sequence cases — a stage recorded out of canonical order, or a gapped set such as transport present without participant-host — so a reviewer can classify any stage combination as valid-in-progress or invalid from the requirement text alone? [Edge Case, Spec §FR-010]

### Evidence Requirement Quality (refresh)

- [x] CHK070 Do the evidence-recording tasks bind all five mandatory aggregate-record fields — the plan requires `scene_id`, stable `case_id`, validator identity, expected result, and observed result on every JSONL record, while T008, T011, and T016 name only `scene_id` as mandatory? [Consistency, Plan §Acceptance Scenes and Evidence; Tasks T008, T011, T016]
- [x] CHK071 Is the slice's scene-ID subset bounded in writing — the scene table and T018 cover S01–S03, S05–S09, S15, and S16 plus two slice-specific rows, but no artifact in this slice states where the absent umbrella scene IDs (S04, S10–S14) are owned — so a reviewer can distinguish "owned by another slice" from a coverage gap without leaving the slice? [Coverage, Gap, Plan §Acceptance Scenes and Evidence; Tasks T018]
- [x] CHK072 Do T018's twelve enumerated manifest rows and the plan's scene table contain the identical scene-ID set, and is the manifest obligation — each scene ID mapped to its JSONL file and record IDs, plus observed per-class partition counts and both skip-regime counts — stated measurably enough to reject an incomplete `evidence/v2/contract/README.md`? [Traceability, Measurability, Plan §Acceptance Scenes and Evidence; Tasks T018]

### Documentation Freshness Requirement Quality (refresh)

- [x] CHK073 With the matrix now file-by-file, does every spec-named documentation surface still have exactly one matching plan row with the same disposition, and do the ten plan-only `NO_IMPACT` rows remain consistent with the spec's affected-docs claim rather than contradicting it? [Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK074 Is each of the ten `NO_IMPACT` rationales written as candidate-diff-verifiable fact — for example `jsonschema==4.26.0` never entering runtime dependencies, or `python3 -m unittest` remaining the green offline baseline — rather than intention or opinion, so the required re-verification against the exact candidate diff can objectively pass or fail per row? [Measurability, Plan §Documentation Impact and Freshness]
- [x] CHK075 Does the matrix state how its file inventory was derived — a written claim of exhaustiveness over `README.md`, root guidance documents, and `docs/**` minus the excluded `docs/archive/` — so a reviewer can verify that no ordinary document was silently omitted, rather than only classifying the rows that are present? [Gap, Plan §Documentation Impact and Freshness]

### Control-Plane Boundary Requirement Quality (refresh)

- [x] CHK076 Is it explicit that the test suite and corpus embed their own copy of the FR-012 class vocabulary rather than reading it from the spec at run time, so no build or test path depends on a SpecKit-managed file even though the vocabulary is declared spec-owned? [Clarity, Tasks §Notes; Constitution §VII]

## Formal Reviewer Gate — Post-Rejection Alignment Addendum (appended 2026-07-17, post-`8fbc79d`)

**Purpose**: Extend the formal reviewer gate to the artifacts as amended after
the first candidate's rejection
(`evidence/v2/contract/review-2026-07-17-v2-integrator.md`, blockers R1–R3):
the spec's 2026-07-17 clarification session (conditional FR-007 legacy-vector
rule, closed FR-005 routing-audit set, schema-expressible per-record FR-010
stage-to-writer binding), the plan's §Post-Rejection Planning Decisions, the
two-commit baseline rule, and the governance-fixture repair target. These items
test the amended requirement text only — scope, parity, interface, evidence,
documentation freshness, and control-plane boundary quality — not any
implementation. They are appended unchecked for the reviewer's pass;
adjudicated CHK verdicts above are not reopened. Where an item cites a
completed task's text, the task is append-only history: the question is whether
the promised correction tasks supersede it in writing, never whether to rewrite
it.

### Scope Requirement Quality (post-rejection)

- [x] CHK077 Is the R1 repair target (`tests/test_governance.py`) reconciled with the spec's scope statement — spec §Control-Plane Boundary enumerates schemas, contract tests under `tests/v2/contract/`, evals, evidence, and contract docs as this slice's ordinary outputs, while only the plan's §Ordinary Repository Targets adds the governance-fixture row — so a reviewer applying the spec alone would not classify that edit as out-of-scope for the slice? [Consistency, Gap, Spec §Control-Plane Boundary; Plan §Ordinary Repository Targets, §Post-Rejection Planning Decisions]
- [ ] CHK078 Are the promised correction tasks ("the delivery tasks step appends the matching correction tasks without rewriting completed history") specified precisely enough — at least one traceable task per blocker R1/R2/R3, with target files and red-case obligations — that a reviewer can judge the appended task graph complete against the three planning decisions, or does the current graph (ending at T024, appended for the earlier CHK064–CHK076 gate) leave the required correction-task content unwritten in every artifact? [Gap, Plan §Post-Rejection Planning Decisions; Tasks §Phase 6]
- [x] CHK079 Is ownership of the shared `tests/test_governance.py` edit stated — that file is repository governance infrastructure rather than the `schemas/v2/**`/`tests/v2/contract/` surface the sole-owner conflict rule covers, and no artifact names which lane owns the repair or how it is handed off — so the R1 fix cannot become an unowned cross-lane edit? [Gap, Plan §Integration Strategy, §Ordinary Repository Targets]

### Parity Requirement Quality (post-rejection)

- [ ] CHK080 Is the R1 two-commit baseline obligation — `python3 -m unittest` green from the exact candidate commit and from the exact handoff packet commit — carried into an owned task and a named evidence target, or does it exist only in the plan's Testing field and rejection-decision prose while T018's command/result recording and the SC-005/T019 packet enumeration never mention the baseline result at the packet commit? [Gap, Plan §Technical Context, §Post-Rejection Planning Decisions; Spec §SC-005; Tasks T018–T019]
- [ ] CHK081 Does any task state the conditional FR-007 rule, or only the superseded framing — completed T003 still reads "legacy-confidence-vector constraints on every `status: ok`" and is preserved append-only — so until the promised correction task lands, no task names the two decisive cases (margin-active candidate `SUPPRESS` without the vector red; `WAKE`/`DEFER` without the optional vector valid)? [Conflict, Gap, Spec §FR-007, §Edge Cases; Tasks T003; Plan §Post-Rejection Planning Decisions]
- [ ] CHK082 Is the partition move of the cross-owner receipt case specified operationally — the per-record stage-to-writer red case is now schema-expressible with identical rejection asserted from both validators, while stream-level writer ownership stays in the runtime-adapter-only receipt-stage sequence class — including which existing corpus cases and per-class `expected-counts.json` entries must be reclassified, so the no-silent-shrink assertion fails loudly during the move instead of masking it? [Measurability, Gap, Spec §FR-010, §FR-012; Plan §Contract validation commands; Tasks T005, T022]
- [ ] CHK083 After R2 reshapes I-010B, is it decidable which corpus revision the S05 governed-suppression evidence must reflect for the next candidate — the plan scene row now states the conditional rule, while completed T010/T011 cite S05 as recorded under the rejected shape and remain checked — or is the re-recording obligation for the affected decision corpus and evidence unwritten? [Consistency, Gap, Plan §Acceptance Scenes and Evidence; Tasks T010–T011]

### Interface Requirement Quality (post-rejection)

- [x] CHK084 Are the routing audit's two conditional facts decidable from the text — exactly when a margin "applied" (requiring the effective margin) and when a trusted margin source counts as "present" — and are legal cross-field combinations written (whether valve `margin-defer` forces override cause `margin`, whether valve `none` may co-occur with effective `DEFER`, and how the four valve values map onto FR-006's four permitted transitions), or is closure enumerated per field but never per combination? [Clarity, Gap, Spec §FR-005, §FR-006]
- [x] CHK085 Is the placement of `reasons` unambiguous — FR-005 and the plan's produces list carry it as a sibling ok-branch field, while the clarification answer describes the closed audit set "plus `reasons`" — so no schema author can read the clarification as putting `reasons` inside the routing-audit object? [Ambiguity, Spec §Clarifications, §FR-005; Plan §Produces]
- [x] CHK086 Is the bypass exclusion set stated identically at every surface — FR-005 excludes classifier/effective disposition, classifier audit, reasons, evidence, legacy confidence vector, routing audit, and advice, while US2 scenario 4 and the Edge Cases enumerate shorter lists — so no reading permits a bypass carrying a routing audit or legacy vector merely because a scenario omits them? [Consistency, Spec §FR-005, §User Scenarios & Testing, §Edge Cases]
- [x] CHK087 Does the schema-expressible FR-010 binding rest on a written stage-to-writer mapping — which single owner is the "directly observing owner" for each of observation, attention, participant-host, and transport, and the closed writer vocabulary — or is that mapping deferred to the T019 "staged-receipt writer map" packet item, leaving both validators without requirement text to enforce a cross-owner record against? [Gap, Spec §FR-010; Plan §Produces, §Owner Handoff]
- [x] CHK088 Is the permissive side of FR-007 decidable — "optional on a `status: ok` decision" must mean a valid vector may accompany `WAKE`, `DEFER`, or a margin-retired `SUPPRESS` without invalidating them — or do the Edge Cases bless only absence ("Valid: a `WAKE` or `DEFER` decision without the optional vector"), leaving present-but-not-required cases to implementer judgment? [Clarity, Spec §FR-007, §Edge Cases]

### Evidence Requirement Quality (post-rejection)

- [x] CHK089 Are rework semantics for contract-run evidence written — the lifecycle candidate/handoff streams are append-only by rule, but nothing states whether `evidence/v2/contract/*.jsonl`, the README manifest, and the two sections of `handoff.md` are regenerated, appended, or superseded for the next candidate attempt after R2/R3 change the corpus — so the next packet cannot cite attempt-one results as current? [Gap, Plan §Acceptance Scenes and Evidence; Spec §Documentation Freshness; Tasks T017–T019]
- [x] CHK090 Are "candidate commit" and "handoff packet commit" defined as distinct terms with their respective green obligations — the rejection distinguishes candidate `81483ce…` from packet commit `9f08124…`, and R1 hinges on that difference — while SC-005 and T019 name only "the exact commit" in the singular? [Ambiguity, Plan §Post-Rejection Planning Decisions; Spec §SC-005; Tasks T019]
- [x] CHK091 Does requirement text bind the rejection record to the attempt stream — the plan cites `evidence/v2/contract/review-2026-07-17-v2-integrator.md` as the rejection source, and the rework rule requires appending `REJECTED` with the exact candidate and durable decision — so a reviewer can verify in writing that the appended attempt names that exact review record and candidate commit rather than a bare status flip? [Traceability, Plan §Post-Rejection Planning Decisions; Spec §Rejection / rework evidence; Tasks §Rejection / rework]

### Documentation Freshness Requirement Quality (post-rejection)

- [ ] CHK092 Is re-execution of the documentation dispositions for the new candidate explicitly required — completed T017 validated `docs/contracts/nunchi-v2.md` and re-verified every `NO_IMPACT` rationale against the rejected candidate's diff and remains checked — or does the matrix's "re-verified against the exact candidate diff" rule lack an appended task making that happen for the next attempt? [Gap, Plan §Documentation Impact and Freshness, §Post-Rejection Planning Decisions; Tasks T017]
- [ ] CHK093 Are baseline-health `NO_IMPACT` rationales sequenced verifiably — `AGENTS.md`'s "`python3 -m unittest` stays the green stdlib offline baseline" was false at the rejected packet commit and becomes true only after the R1 repair lands — so the required re-verification is ordered after the repair within the same candidate rather than checked against a commit where the claim fails? [Consistency, Measurability, Plan §Documentation Impact and Freshness, §Post-Rejection Planning Decisions]
- [ ] CHK094 Do the matrix row and T017's task text enumerate the same validation targets for the `docs/contracts/nunchi-v2.md` `UPDATE` — the row now names the conditional FR-007 vector rule, the closed routing-audit set, and the per-record FR-010 stage-to-writer binding, while T017's text (written before R2/R3) names only the five `@1` interfaces and the FR-012 runtime-adapter-only rules — so the doc cannot revalidate against the superseded shapes? [Consistency, Gap, Plan §Documentation Impact and Freshness; Tasks T017]

### Control-Plane Boundary Requirement Quality (post-rejection)

- [ ] CHK095 Is the R1 repair stated as a verifiable boundary invariant — "constructs its synthetic planning baseline independently of the repository's live slice state" — with a named regression proof (the baseline stays green while live slices are `ACTIVE` or `HANDOFF_READY`), or is it a one-off description under which a partially decoupled fixture could pass again by coincidence of the current live state? [Measurability, Plan §Post-Rejection Planning Decisions, §Ordinary Repository Targets]
- [x] CHK096 Do the post-rejection additions keep the slice directory's closed allowlist intact — rejection analysis, decision rationale, and correction planning live in plan prose and ordinary evidence paths, with no new file under the slice directory and the review record itself under `evidence/v2/contract/` — so the SC-006 boundary check still passes without a carve-out? [Consistency, Plan §Project Structure; Spec §SC-006, §Control-Plane Boundary]
