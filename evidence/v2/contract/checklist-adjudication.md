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
