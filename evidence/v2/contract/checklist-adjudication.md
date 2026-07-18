# Reviewer adjudication — slice 010 formal checklist (CHK018–CHK063)

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`; adjudication
delegated to a read-only analysis agent and verified by the reviewer with
spot-checks of CHK024, CHK049, CHK052, CHK057 against the artifact text)

**Adjudicated on**: 2026-07-17, at the slice-readiness gate of bound run
`speckit-010-20260717T003300631902Z`

**Method**: each item answered strictly against the current spec.md, plan.md,
tasks.md, and checklists/requirements.md text; PASS only on explicit
satisfaction. CHK019 was the single OPEN verdict; its gap (Explicit Exclusions
lacked named later owners) was fixed in the readiness commit before check-off
and re-verified.

## Verdicts

CHK018 PASS — control-plane/ordinary split stated identically in spec, plan, tasks.
CHK019 PASS after fix — exclusions now name the later owner per concern (030 prompt/provider, 020 collector, 040 invocation, 050/060–090 transports, 110 deployment).
CHK020 PASS — per-consumer acceptance in plan §Integration Strategy and tasks §Dependencies.
CHK021 PASS — return-handoff contents enumerated in plan conflict-ownership.
CHK022 PASS — one corpus, both validators, loud skip accounting (FR-012/plan/T001).
CHK023 PASS — corpus revision pinned to exact commit in T019 packet.
CHK024 PASS — SC-002 semantic-field equality with serialization out of scope.
CHK025 PASS — green suite ≠ social correctness; margin independently evidence-gated.
CHK026 PASS — exact @1 versions/paths; SC-004 deterministic failure on edit/deletion.
CHK027 PASS — interface name/version/path/task consistent across all artifacts.
CHK028 PASS — breaking edits require owner handoff + re-analysis; sole-owner editing.
CHK029 PASS — classifier projection limited to coverage/expansion booleans.
CHK030 PASS — FR-013 restates 030 FR-005 locally for drift detection.
CHK031 PASS — closed ok/bypass/error union with branch-exclusive fields.
CHK032 PASS — stage owners append-only; unknown/unavailable explicit.
CHK033 PASS — twelve scene rows, each with observation and evidence target.
CHK034 PASS — five mandatory JSONL fields; T018 manifest covers all rows.
CHK035 PASS — packet enumerations aligned; T019 authoritative.
CHK036 PASS — lifecycle vs contract-run evidence distinct ordinary paths.
CHK037 PASS — table entries are claims; evidence records commands and results.
CHK038 PASS — one disposition/owner/validation per row; exact files only.
CHK039 PASS — NO_IMPACT rows re-verified against the exact candidate diff.
CHK040 PASS — UPDATE only slice-owned; HANDOFF rows carry accepting owner.
CHK041 PASS — docs/archive outside the freshness surface.
CHK042 PASS — spec-named surfaces match plan rows one-to-one.
CHK043 PASS — closed slice-directory allowlist; flagless governance check in T018.
CHK044 PASS — no data-model.md/contracts//quickstart.md anywhere.
CHK045 PASS — governance stays in planning artifacts; no lifecycle in contracts.
CHK046 PASS — jsonschema==4.26.0 dev/test-only everywhere it is named.
CHK047 PASS — downstream adapter obligation in T019 packet.
CHK048 PASS — identical closed six-class set in spec, plan, T001.
CHK049 PASS — per-class oracle treatment fixed (4 expected-valid, 2 class-skipped).
CHK050 PASS — per-class counts asserted against expected-counts.json.
CHK051 PASS — baseline oracle-absence skips separated from class skips; T018 records both.
CHK052 PASS — all six semantic classes trace to named red cases (T002/T005 spot-checked).
CHK053 PASS — "-Infinity" sentinel present; loader decodes once for both validators.
CHK054 PASS — number equality by exact decimal token; order preservation stated.
CHK055 PASS — performance goal explicitly advisory.
CHK056 PASS — advice keyed to classifier disposition WAKE / source WAKE only.
CHK057 PASS — canonical stage order with prefix-partial validity (S07 covered).
CHK058 PASS — fetch-time rejection locus under the merge-identity rule.
CHK059 PASS — task-manifest copy rule with per-attempt hashing.
CHK060 PASS — handoff.md append-only ordering; distinct from slice-handoff.md.
CHK061 PASS — SC-005 carries the T019-authoritative note.
CHK062 PASS — nunchi-v2.md validation covers the semantic rules.
CHK063 PASS — partition vocabulary control-plane; counts live in ordinary paths.

# Reviewer adjudication — post-e4ada5c refresh gate (CHK064–CHK076)

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Adjudicated on**: 2026-07-17, in the implement step of bound run
`speckit-010-20260717T081350382670Z` (T024)

**Method**: each item answered strictly against the refreshed spec.md
(`16cccb7` amendments), plan.md (`e4ada5c` refresh plus this commit's
fixes), tasks.md (`7e17db9` correction phase), and the landed correction
artifacts at `e52c9a4`/`cc2441e`. Sustained text gaps are fixed in the named
SpecKit artifact in the same commit as this record, before check-off.

## Verdicts

CHK064 SUSTAINED, fixed — plan §Integration Strategy said "tagged contract commit" while the spec interface summary and T019 require only the exact commit; reworded in this commit to "exact contract commit" with an explicit no-git-tag clarification, matching spec and packet.
CHK065 PASS after tasks refresh — the tasks header now carries an explicit "Execution status: EXECUTABLE" statement conditioned on the `ACTIVE` state (added at `7e17db9`); verified present alongside the retained `PLANNED`-dormancy rule.
CHK066 SUSTAINED, fixed — plan §Contract validation commands permitted "expecting valid or skipping by explicit class" without the class-to-treatment mapping; restated in this commit exactly per spec FR-012 (four document-shaped classes oracle-expected-valid, two behavioral/sequence classes oracle-class-skipped, no other mapping permitted).
CHK067 PASS via T020 — `assert_corpus_inventory()` runs on every corpus load and fails loudly on a wholly missing or unregistered corpus directory or a missing cases.jsonl/expected-counts.json; red-path tests cover all three failure shapes (landed at `e52c9a4`).
CHK068 PASS — FR-007 permanence (field required for all of `@1`; removal is a breaking `@2` edit), the Assumptions' breaking-edit contract (owner handoff + dependent re-analysis), and the independently gated margin retirement are mutually consistent; no reading permits dropping the field at `@1` once margin evidence lands, because retirement gates the margin policy, not the evidence field.
CHK069 PASS via T022 — the downstream corpus now names the complete refreshed FR-010 coverage: full canonical stream (DWN-S06-301), prefix-partials awaiting later stages (DWN-S06-302), awaiting-transport contributed prefix (DWN-S06-308, appended at `e52c9a4` with counts updated in the same change), S07 silence ending at participant-host (DWN-S07-301), out-of-order (DWN-S06-304), skipped-stage (DWN-S06-305), earlier-stage mutation (DWN-S06-303), cross-owner writer (DWN-S06-306), and uncorrelated request ID (DWN-S06-307), verified under the pinned dual-validator command.
CHK070 PASS via T021 — the shared evidence writer enforces all five mandatory fields (`scene_id`, `case_id`, validator identity, expected, observed) and refuses any record missing one; the landed attention-request (72), attention-decision (94), and downstream (122) records were re-verified conformant before T011/T016 check-off (landed at `e52c9a4`, ordering recorded at `cc2441e`).
CHK071 SUSTAINED, fixed — no artifact stated where the absent umbrella scenes are owned; plan §Acceptance Scenes and Evidence now records S04 and S10–S14 ownership per the program plan's parity scene table, so absence reads as ownership, not a coverage gap.
CHK072 PASS — T018's twelve enumerated rows and the plan scene table carry the identical scene-ID set (S01–S03, S05–S09, S15, S16, 010-Preattention-bypass, 010-V1), and the manifest obligation (scene ID to JSONL file and record IDs, observed per-class partition counts, both skip-regime counts, beside commands and results) is stated measurably enough to reject an incomplete README.
CHK073 PASS — every spec-named documentation surface has exactly one plan row with the same disposition (README HANDOFF; nunchi-v2 UPDATE; CHANGELOG/STABILITY/integration/adapters/channel-adapter-v1/v2-selected-design HANDOFF), and the ten `NO_IMPACT` rows cover documents the spec's affected-docs claim never names, so they complement rather than contradict it.
CHK074 SUSTAINED in part, fixed — nine rationales were already candidate-diff-verifiable facts; the execution-spine row's "the slice follows the documented spine" clause was intention, reworded in this commit to concrete diff-checkable facts (no change under `docs/governance/`, to the governance script/checks, or to any documented governance command or gate).
CHK075 SUSTAINED, fixed — the matrix now states its inventory derivation: exhaustive over README.md, root guidance documents, and docs/** minus docs/archive/, 17 existing files plus the slice-created contract doc matching the 18 rows one-to-one, with the re-derivation commands named.
CHK076 PASS via T023 — `scan_control_plane_references()` plus its covering test assert no file under the test or corpus trees references a SpecKit-managed control-plane path, and the FR-012 class vocabulary is asserted embedded in the harness, never read from a SpecKit file at build or test time (landed at `e52c9a4`).

# Reviewer adjudication — post-rejection gate, requirement-text items (T025)

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Adjudicated on**: 2026-07-17, in the implement step of bound run
`speckit-010-20260717T163451669036Z` (T025)

**Method**: each requirement-text item answered strictly against spec.md and
plan.md as amended after the rejection (`89aef07` clarifications, `8fbc79d`
plan alignment, `95b22a1` gate append, `274ebc9` task append); every
sustained text gap is fixed in the named SpecKit artifact in the same commit
as this record, before check-off. Implementation-dependent items (CHK078,
CHK080–CHK083, CHK092–CHK094, and CHK095's landed proof) are adjudicated by
the later T033 append, never here. This section is append-only; the
CHK018–CHK063 and CHK064–CHK076 adjudications above are never rewritten.

## Verdicts (requirement text)

CHK077 SUSTAINED, fixed — spec §Control-Plane Boundary enumerated only schemas/tests/evals/evidence/contract docs, so a spec-only reviewer would misclassify the R1 repair as out-of-scope; a new boundary bullet now states the `tests/test_governance.py` repair is an in-scope ordinary rework output of this slice, cross-referencing plan §Ordinary Repository Targets and §Integration Strategy.
CHK079 SUSTAINED, fixed — no artifact named the owning lane for the shared governance-infrastructure edit; plan §Integration Strategy now carries the ownership note: `v2-contract-owner` performs the `tests/test_governance.py` edit for this rework, `v2-integrator` reviews it at handoff, and no other lane edits the file during this slice.
CHK084 SUSTAINED, fixed — closure was enumerated per field but not per combination; spec FR-005 now defines margin **applied** (exactly valve `margin-defer`, which then requires the effective margin in `(0, 1]` and forbids it elsewhere), trusted-source **present** (`margin_source` only on a margin-applied decision, optional there, forbidden elsewhere), and the exact valve/override-cause pairings (`none`/`classifier-defer` ⇒ cause `none`; `margin-defer` ⇒ cause `margin` plus margin status `active`; `policy-defer` ⇒ cause `suppression-disabled` or `recoverability-unproven`); spec FR-006 now maps the four permitted transitions onto valves (`WAKE→WAKE`/`SUPPRESS→SUPPRESS` ⇒ `none`, `DEFER→DEFER` ⇒ `classifier-defer`, `SUPPRESS→DEFER` ⇒ `margin-defer` or `policy-defer`) and states valve `none` never co-occurs with a widened disposition.
CHK085 SUSTAINED, fixed — the clarification's "plus `reasons`" phrasing admitted an inside-the-audit reading; spec FR-005 now fixes `reasons` as a required sibling ok-branch field (an array of audit strings, possibly empty) that is never a member of the routing-audit object, and the §Clarifications answer carries the same parenthetical.
CHK086 SUSTAINED, fixed — US2 scenario 4 and the Edge Cases enumerated shorter exclusion lists than FR-005; both surfaces now state the identical seven-member FR-005 set (classifier/effective disposition, classifier audit, reasons, evidence, legacy confidence vector, routing audit, advice), each naming it as the identical FR-005 exclusion set.
CHK087 SUSTAINED, fixed — the "directly observing owner" mapping was deferred to the T019 packet item; spec FR-010 now writes the closed four-entry map (`observation` → `observation-provider`, `attention` → `attention-engine`, `participant-host` → `participant-host`, `transport` → `transport`) into requirement text, giving both validators a written rule to enforce a cross-owner record against.
CHK088 SUSTAINED, fixed — the Edge Cases blessed only absence; spec FR-007 now states the symmetric permissive side (a well-formed vector MAY accompany any ok decision — `WAKE`, `DEFER`, or a margin-retired `SUPPRESS` — and presence never invalidates), and the Edge Cases carry the matching valid enumeration.
CHK089 SUSTAINED, fixed — no artifact stated attempt rework semantics for contract-run evidence; plan §Acceptance Scenes and Evidence now writes them: aggregate JSONL files and the README manifest regenerate in place as current-attempt records (an unchanged file gets an explicit disposition in the manifest), `handoff.md` and `checklist-adjudication.md` append one section per attempt, lifecycle attempt streams append and never rewrite, and superseded attempt-one aggregates remain recoverable from git history at the rejected candidate commit. The same semantics are restated in tasks §Notes.
CHK090 SUSTAINED, fixed — SC-005 named "the exact commit" in the singular; spec SC-005 now defines **candidate commit** and **handoff packet commit** as distinct terms, each independently carrying the green full-offline-baseline obligation; T034 carries the definitions into the attempt-2 packet.
CHK091 PASS (consistency confirmation) — the appended `REJECTED` attempt in `evidence/v2/contract/slice-handoff.md` names the exact candidate commit `81483ce017eb834c5ab533556fa64cd62a8cf2aa` and the durable decision reference `evidence/v2/contract/review-2026-07-17-v2-integrator.md`, with rejecting owner and date; the binding the item asks for is verifiably in writing, not a bare status flip.
CHK095 SUSTAINED (text side fixed here; check-off deferred) — plan §Post-Rejection Planning Decisions, Decision R1 now restates the repair as a verifiable invariant (replace every live slice declaration and lifecycle record staged, not only `PLANNED` ones) with the named regression proof `test_activation_fixture_is_independent_of_live_slice_state` required green while live declarations read `ACTIVE` or `HANDOFF_READY`; the checklist item is checked only by the T033 append once T026 lands that proof on disk.
CHK096 PASS (consistency confirmation) — `specs/010-v2-contract/` still contains exactly `spec.md`, `plan.md`, `tasks.md`, and `checklists/requirements.md`; rejection analysis, decision rationale, and correction planning live in plan prose and ordinary evidence paths, and the review record itself lives at `evidence/v2/contract/review-2026-07-17-v2-integrator.md`, so the SC-006 boundary check passes without any carve-out (re-run flagless this commit: OK).

# Reviewer adjudication — post-rejection gate, implementation items (T033)

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Adjudicated on**: 2026-07-17, in the implement step of bound run
`speckit-010-20260717T163451669036Z` (T033)

**Method**: each implementation-dependent item verified against the landed
correction commits of this run — T025 `465d429`, T026 `b3cbb8f`, T027/T028
`4bc5d9b`, T029/T030 `747fc97`, T031 `36a6a3c`, T032 `ddba5c1` — with each
verdict citing its landed task, file, and record anchors. Each gate item is
checked off in the requirements checklist only with its fix verifiably on
disk. This section is append-only; the T025 text verdicts and all earlier
adjudications are never rewritten.

## Verdicts (implementation)

CHK078 PASS via the Phase 7 append — the promised correction-task content is written: tasks §Phase 7 (`274ebc9`) carries at least one traceable task per blocker with target files and red-case obligations — R1 → T026 (`tests/test_governance.py`, live-state regression proof), R2 → T027/T028 (`schemas/v2/attention-decision.schema.json`, decision corpus and red tests with the decisive conditional cases), R3 → T029/T030 (`schemas/v2/attention-receipt.schema.json`, `tests/v2/contract/schema_helpers.py`, downstream corpus reclassification) — plus the evidence/documentation/packet chain T031–T034, each citing its blocker, clarified requirement, or gate item.
CHK080 PASS via T025+T031 — spec SC-005 (`465d429`) defines candidate commit and handoff packet commit as distinct terms each carrying the green full-offline-baseline obligation, and `evidence/v2/contract/README.md` (`36a6a3c`) records the full `python3 -m unittest` result (1225 tests, OK, 11 skipped) as the run the exact candidate commit must reproduce, with the packet-commit rerun explicitly owed at the handoff gate; T034's packet carries both commits.
CHK081 PASS via T028 — the appended task text and the reworked `tests/v2/contract/test_attention_decision.py` (`4bc5d9b`) supersede T003's every-ok-decision framing in writing and land both decisive cases: margin-active candidate `SUPPRESS` without the vector red (corpus `DEC-S05-103`; test `test_margin_active_suppression_without_vector_rejects`) and `WAKE`/`DEFER` without the optional vector valid (corpus `DEC-S05-003`/`DEC-S05-004`; test `test_wake_and_defer_without_the_optional_vector_stay_valid`), with the sentinel-decoded non-finite reds re-keyed to the conditional rule.
CHK082 PASS via T030 — the partition move is operational and loud (`747fc97`): `DWN-S06-306` is named as the reclassified case (`receipt-sequence` → `schema-expressible`, payload now the review's forged `stage: observation`/`writer: transport` single document) with per-class deltas named in the corpus change and README (`schema-expressible` invalid 27→28; `receipt-sequence` invalid 5−1+1=5 via the appended stream-level case `DWN-S06-309`), `expected-counts.json` updated in the same change so the no-silent-shrink assertion trips loudly, and the covering red tests landed in `tests/v2/contract/test_context_and_receipt.py` (`ReceiptWriterBindingCases`).
CHK083 PASS via T028+T031 — the S05 evidence re-recording obligation is written and executed: `evidence/v2/contract/attention-decision.jsonl` was regenerated (`36a6a3c`, 122 records, 0 mismatched) under the reworked corpus reflecting the conditional FR-007 rule, and the README manifest names the attempt-2 corpus revision, per-class counts, and the CHK089 rework-disposition note, so the next candidate's S05 evidence is decidably the reworked corpus's.
CHK092 PASS via T032 — the attempt-2 documentation section in `evidence/v2/contract/handoff.md` (`ddba5c1`) re-executes every row of plan §Documentation Impact and Freshness against the attempt-2 candidate diff (1 UPDATE re-validated, 7 HANDOFF re-routed, 10 NO_IMPACT re-verified), appended without rewriting the attempt-1 sections.
CHK093 PASS via T026+T032 — the re-verification is sequenced after the R1 repair within the same candidate: T026 landed at `b3cbb8f` before the T032 review at `ddba5c1`, the section states the sequencing explicitly, and the `AGENTS.md` green-baseline claim was verified true post-repair (1225 tests, OK, 11 skipped) with the fixture-independence regression proof keeping it live-state-independent.
CHK094 PASS via T032 — the matrix row (aligned at `8fbc79d`) and the executed re-validation now enumerate the same targets: the `docs/contracts/nunchi-v2.md` UPDATE documents the conditional FR-007 vector rule, the closed routing-audit set with its cross-field rules, and the per-record FR-010 stage-to-writer binding alongside the five `@1` interfaces and the FR-012 runtime-adapter-only rules, validated against both validators (5 embedded examples, 0 failures).
CHK095 PASS via T025+T026 — the invariant is requirement text (plan §Post-Rejection Planning Decisions, Decision R1, `465d429`) and its named regression proof is landed and green (`tests.test_governance.GovernanceBoundaryTests.test_activation_fixture_is_independent_of_live_slice_state`, `b3cbb8f`): the staging helper replaces every live slice declaration regardless of state and removes any staged lifecycle record, and the proof holds the baseline green while live declarations read `ACTIVE` or `HANDOFF_READY`; the old non-normalizing behavior was demonstrated to fail it (75 errors), so a partially decoupled fixture cannot pass by coincidence.

# Reviewer adjudication — attempt-3 rework gate, requirement-text items (T035, T046)

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Adjudicated on**: 2026-07-18, by cc-session-1 working directly in the owner
worktree — not via a bound `run speckit` invocation. Three consecutive bound
runs for this rework failed on workflow-machinery defects unrelated to this
gate's substance (a governance lexical-token violation in the Phase 8 append,
then twice a nested-integration write-permission fault); Zoe directed this
session to complete the rework directly in the worktree and hand off the
result rather than continue restarting the bound-run machinery. The checklist
step of the second retried run appended CHK112–CHK121 against T035–T045's own
task text before the write fault was found, so this adjudication covers both
gates together.

**Method**: each requirement-text item (CHK097–CHK121) answered strictly
against spec.md, plan.md, and tasks.md as they stand at this commit; every
sustained text gap is fixed in the named artifact in this same commit, before
check-off. This section is append-only; every earlier adjudication above is
unchanged.

## Verdicts (requirement text, CHK097–CHK111)

CHK097 SUSTAINED, fixed — Phase 8 (landed `93f25a2`) appends T035–T045 naming at least one traceable task per blocker with target files and the decisive red-then-green obligation: R4 → T036–T041 (the five `schemas/v2/` files, the stdlib adapter, all three corpus families, naming the integrator's 41/16/13/11-error stdlib-adapter probes); R5 → T045 (single-valued commit identity); R6 → the already-reworded Execution status header (CHK106).
CHK098 PASS (consistency confirmation) — plan §Post-Rejection Planning Decisions, Decision R4 bounds the rework to the five `schemas/v2/` files, the stdlib runtime adapter, every corpus family, and the slice-owned contract doc; R5 bounds it to evidence/packet identity; R6 bounds it to task-graph wording only; §Constitution Check records no new violation or complexity exception from this rework, so a reviewer can classify any attempt-3 diff hunk against one of these three bounded surfaces.
CHK099 SUSTAINED, fixed — spec FR-012 now states authority-conformance cases are "a named manifest-counted class inside the schema-expressible partition, carrying the identical dual-validator expected-results treatment every schema-expressible case carries; they are never a fourth oracle-treatment class"; plan §Contract validation commands already stated "as a schema-expressible valid case" and §Acceptance Scenes and Evidence now carries the identical qualifier ("as schema-expressible valid cases... never a new partition class with its own oracle treatment") — the same fix closes CHK115.
CHK100 SUSTAINED, fixed — spec Edge Cases' FR-014 bullet now adds the missing decision-family representative document (a valid `WAKE` with a `margin-defer` routing audit; a valid `WAKE` without a legacy verdict confidence vector), so the Edge-Case list, FR-012's six-family coverage list, and the plan's per-family placement now name the same six families (request, coverage folded into the request example, continuation/fetch/page, participant-wake, decision, receipt) identically.
CHK101 SUSTAINED, fixed — T036–T038 (this commit) now name the exact attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de` as the red-run baseline in place of the unnamed "a named pre-repair tree"/no baseline at all, making the red-then-green obligation reproducible from the written task text alone; T042 records the result under the named `red_run_failing_count` manifest field (CHK119).
CHK102 PASS (consistency confirmation) — each plan §Produces bullet already cites "(FR-014)" at its own point of enumeration (I-010A, I-010B, I-010C, I-010D, I-010E each carry the citation immediately after their field-inventory detail), and FR-014 itself opens by naming `c834e8c` as "the field-level naming and shape authority for every `@1` interface"; the tie-break is therefore stated where each enumeration appears, by direct citation, not left to be inferred.
CHK103 SUSTAINED, fixed — spec FR-005 now states the complete error-branch field inventory: an `error` object with `code` and `detail`, an optional request ID (optional on both the pre-validation and post-validation branches, per T040's CHK117 fix below — not narrowed to the pre-validation case), and an optional classifier audit present only when the error occurred after classifier invocation.
CHK104 PASS (consistency confirmation) — spec §Clarifications (2026-07-18) already frames the named attempt-2 examples with "for example," and FR-014 restates "Local renames or narrowings — for example... — are contract defects," so a rename absent from the example list is already decidably a defect under the general rule, not exempted by omission.
CHK105 PASS (consistency confirmation) — plan §Owner Handoff already enumerates the four commit-identity locations identically (lifecycle candidate entry, handoff attempt entry, the packet input in `evidence/v2/contract/handoff.md`, and the recorded corpus revision) and already names the operational recording rule ("the actual handoff packet commit recorded in the same terms once it exists"); T045 carries the same obligation forward as the packet-input task.
CHK106 PASS (consistency confirmation) — the Execution status header (landed `93f25a2`) already opens with the referential rule ("stated by reference, never as a fixed state claim") and explicitly marks itself as never edited at a transition while the `Slice state` line above is the transition-updated declaration, closing the exact gap this item raised before this adjudication was written.
CHK107 PASS (consistency confirmation) — plan §Acceptance Scenes and Evidence's "Attempt rework semantics for contract-run evidence" paragraph is written as a general rule ("after a rejection changes the corpus or schemas, the aggregate JSONL files... regenerate in place as current-attempt records"), not scoped to one attempt, and already covers the unchanged-file disposition and the append-only `handoff.md`/`checklist-adjudication.md` rule for every later attempt.
CHK108 PASS (consistency confirmation, disposition per CHK112) — this item requires no spec/plan text fix; it closes entirely through T043's re-execution of the documentation matrix against the attempt-3 diff.
CHK109 PASS (consistency confirmation, disposition per CHK112) — this item requires no spec/plan text fix; it closes entirely through T043's re-scan of every routed `HANDOFF` delta against the repaired FR-014 shapes.
CHK110 PASS (consistency confirmation, disposition per CHK112) — this item requires no spec/plan text fix; it closes entirely through T042's manifest field `authority_source_commit: c834e8c` on each authority-flagged evidence record.
CHK111 PASS (consistency confirmation) — `specs/010-v2-contract/` still contains exactly `spec.md`, `plan.md`, `tasks.md`, and `checklists/requirements.md`; no new file was added under the slice directory by this rework (re-run flagless this commit: OK).

## Verdicts (requirement text, CHK112–CHK121)

CHK112 SUSTAINED, fixed — T035's own text (this commit) now carries an explicit disposition clause naming CHK108, CHK109, and CHK110 as items that require no spec/plan text fix and close entirely through T042–T044, so their absence from T035's per-item list is no longer misreadable as an unaddressed item.
CHK113 SUSTAINED, fixed — plan §Ordinary Repository Targets' "Contract tests" row now names `tests/v2/contract/schema_helpers.py` alongside `tests/v2/contract/test_*.py`, matching the file T012–T014, T020–T023, and T039–T041 all edit.
CHK114 SUSTAINED, fixed — T035's own text (this commit) now carries the decidable classification rule verbatim: a CHK item requires a landed text fix only when the cited section does not yet contain, verbatim, the wording the item's question describes as of this task graph's authoring commit, and requires only a consistency confirmation when that wording already exists — removing adjudicator discretion.
CHK115 SUSTAINED, fixed — closed by the same CHK099 fix above: plan §Acceptance Scenes and Evidence now carries the identical "schema-expressible" qualifier that §Contract validation commands already stated, so the two sections agree.
CHK116 SUSTAINED, fixed — T036, T037, and T038 (this commit) each now name the exact attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de` as the red-run baseline, replacing the unnamed "a named pre-repair tree" phrasing (T036) or the absent baseline reference (T037, T038).
CHK117 SUSTAINED, fixed — T040 (this commit) now states the request ID is optional on both the pre-validation and post-validation error branches, and spec FR-005 (this commit) states the same complete error-branch inventory (CHK103), so the post-validation case is no longer silently unaddressed.
CHK118 SUSTAINED, fixed — T039 (this commit) now reproduces FR-014's own event-union wording verbatim (typed message, reaction, and membership event union with reaction `add`/`remove` operation and literal membership scope, subject actor, and optional causal actor) instead of the locally invented "`kind: reply|thread`" and "universally required author/mention fields" phrasing that appears nowhere in FR-014; T041 (this commit) now names the continuation capability's full field list (`handle_id`, exact `bound_to`, before/after/around fetch capabilities, per-fetch caps, optional expiry) instead of the shortened paraphrase.
CHK119 SUSTAINED, fixed — T042 (this commit) now names the manifest field `red_run_failing_count`, recorded beside each family's green partition-count row in `evidence/v2/contract/README.md`, replacing the descriptive "beside the green results" phrase.
CHK120 SUSTAINED, fixed — T043 (this commit) now requires re-running the inventory-derivation check (`ls *.md` plus `find docs -name '*.md' | grep -v archive`) against the attempt-3 diff, in addition to re-validating the eighteen already-listed rows.
CHK121 SUSTAINED, fixed — T042 (this commit) now names the manifest field `authority_source_commit: c834e8c`, recorded on each authority-flagged record in `evidence/v2/contract/README.md`, replacing the descriptive "flagged... with its pinned provenance" phrase.

# Reviewer adjudication — attempt-3 rework gate, implementation items (T044)

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Adjudicated on**: 2026-07-18, directly in the `v2-contract-owner`
worktree, against the landed implementation commit `7f9e814`.

**Method**: each implementation-dependent CHK097–CHK111 item verified
against the landed correction commit of this attempt — `7f9e814`, which
carries T036–T043 (all five schema reworks, the stdlib adapter, all four
test files, all three corpora with the FR-014 authority-conformance class,
regenerated evidence, the reworked `docs/contracts/nunchi-v2.md`, and the
attempt-3 documentation dispositions) — with each verdict citing its
landed task, file, and record anchors. Each gate item is checked off in
the requirements checklist only with its fix verifiably on disk. This
section is append-only; every earlier adjudication above is unchanged.

## Verdicts (implementation)

CHK099 PASS via T036–T038+T042 — the authority-conformance class is not just described in text but actually landed as schema-expressible cases: `evals/v2/contract/{attention-request,attention-decision,downstream}/cases.jsonl` carry 14 `*-AUTH-*` cases inside the `schema-expressible` partition (never a separate partition value — `expected-counts.json` has no fourth class), and `evidence/v2/contract/README.md`'s authority table confirms all 14 pass under both validators at `7f9e814`.
CHK100 PASS via T036–T038 — the closed minimum authority-case inventory is landed identically to FR-012/FR-014/Edge Cases: request-family cases cover the example request, typed reaction, typed membership, and full coverage (`REQ-AUTH-001`–`004`); decision-family cases cover margin status, vector-optional WAKE, and both error-branch request-ID cases (`DEC-AUTH-001`–`004`); downstream-family cases cover the anchored fetch, identity-bearing page, materialized wake, and all three non-transport receipt stages (`DWN-AUTH-001`–`006`).
CHK101 PASS via T042 — the red-then-green obligation is decidable and recorded: `evidence/v2/contract/README.md`'s authority table names a `red_run_failing_count` for every case, measured by checking out the attempt-2 packet commit's schemas (`5383e9f3a5e9c20c08ab54395f4ff370128f03de`) into an isolated scratch tree and running each authority document through a real Draft 2020-12 validator built from those exact files — not a described obligation, an executed one — alongside the green result at `7f9e814` (`write-evidence`: 0 mismatched).
CHK102 PASS via T035's consistency confirmation (unchanged by implementation): each `schemas/v2/*.schema.json` file's description field and the plan §Produces bullet it mirrors both cite FR-014/`c834e8c` at the point of enumeration; landed schemas at `7f9e814` match this.
CHK103 PASS via T040 landed — `schemas/v2/attention-decision.schema.json`'s `error` `$def` requires exactly `code` with optional `detail`, and `classifier` is optional; `request_id` is a top-level optional property on the `error` variant, covering both pre- and post-validation branches identically (verified: `DEC-AUTH-003` and `DEC-AUTH-004` in the corpus exercise both cases, 0 validator errors at `7f9e814`).
CHK104 PASS via T035's consistency confirmation (unchanged by implementation).
CHK105 PASS via T035's consistency confirmation (unchanged by implementation); T045's packet input below carries the same single-valued commit identity forward.
CHK107 PASS via T042 — all three aggregate JSONL files were regenerated in place as current-attempt records (not selectively; R4 re-entered every corpus family, so `attention-request.jsonl` was re-recorded too, unlike the attempt-2 disposition), the manifest names the current attempt-3 counts, and no evidence file was left with a stale attempt-2 disposition.
CHK108 PASS via T043 — `docs/contracts/nunchi-v2.md`'s `UPDATE` was re-validated against the attempt-3 candidate diff (landed at `7f9e814`); all five embedded JSON examples verified against both validators, 0 failures.
CHK109 PASS via T043 — all seven `HANDOFF` rows were re-scanned against the R4 field renames; none embeds a superseded local field name or narrowed-shape claim (they reference interface IDs, versions, and paths only), so no row required editing.
CHK110 PASS via T042 — `evidence/v2/contract/README.md`'s authority table names `authority_source_commit: c834e8c` on every one of the 14 authority records, verifiable from the manifest alone with no build or test path reading the external design document at run time.
CHK111 PASS via re-running the SC-006 boundary check — `python3 scripts/check_governance.py` reports `governance boundary: OK` at `7f9e814`; `specs/010-v2-contract/` still contains exactly `spec.md`, `plan.md`, `tasks.md`, and `checklists/requirements.md`.
