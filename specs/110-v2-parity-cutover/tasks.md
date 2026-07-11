---
description: "Future Goal 2 task list for V2 parity and atomic cutover"
---

# Tasks: V2 Parity and Atomic Cutover

**Input**: Design documents from `/specs/110-v2-parity-cutover/`

**Prerequisites**: `spec.md`, `plan.md`, zero CRITICAL/HIGH analysis findings,
accepted handoffs from slices `010` through `100`, and explicit Zoe Goal 2
authorization before T001 or any later task begins

**Accountable owner lane**: `v2-integrator`

**Integration handoff**: Umbrella program and Zoe; final sink with no downstream
implementation slice

**Goal state**: Future Goal 2 plan only. All tasks remain unexecuted under Goal 1.

**Tests**: Required. Atomicity and parity tests precede assembly/comparison;
installed-runtime and room evidence follow a deterministic green candidate.

## Phase 1: Setup and Handoff Admission

**Purpose**: Prove implementation authority, exact dependency readiness, and an
isolated non-releaseable integration workspace.

- [ ] T001 Record explicit Zoe Goal 2 authorization, `v2-integrator` activation, and zero CRITICAL/HIGH analysis result in `evidence/v2/parity/authorization.md`
- [ ] T002 Validate exact commits, canonical interfaces, commands/results, evidence, provenance, security disposition, and limitations from slices `010` through `100` and write `evidence/v2/parity/upstream-handoffs.json`
- [ ] T003 Create isolated worktree `.worktrees/v2-integration/` on branch `integration/v2` and record its non-releaseable base commit in `evidence/v2/parity/upstream-handoffs.json`

**Checkpoint**: Stop before assembly if Goal 2 is unauthorized, any owner lane is
inactive, any handoff is incomplete, or slice `100` has unaccepted residual risk.

---

## Phase 2: Foundational Manifest, Atomicity, and Scene Contracts

**Purpose**: Define the candidate manifest and failing checks that all user
stories depend on.

- [ ] T004 Define the integrated candidate manifest, scene/surface evidence manifest, trusted-bypass and immutable receipt-stage fields, parity evidence index, post-hoc participant-output grades, main-cutover record, and release-readiness artifact fields without creating a product schema in `docs/evaluations/v2-parity.md`
- [ ] T005 [P] Add canonical-interface, trusted-bypass, immutable request-correlated receipt-stage ownership, dependency-commit, and manifest validation tests in `tests/v2/parity/test_integration_manifest.py`
- [ ] T006 [P] Add V1 residue, translation bridge, mixed schema, retired hook/shim, second-social-gate, and SpecKit-dependency rejection tests in `tests/v2/parity/test_repository_atomicity.py`
- [ ] T007 [P] Add S01-S16 scene-manifest completeness, surface-applicability, stable-`scene_id`, mandatory bypass/receipt fields, post-hoc meta-answer/no-runtime-filter, and blocking-versus-native-capability disposition tests in `tests/v2/parity/test_scene_catalog.py`
- [ ] T008 [P] Add installed commit/package/config/schema/restart/probe result contract tests in `tests/v2/parity/test_surface_probe.py`

**Checkpoint**: The manifest and tests identify every dependency and shared
scene before any handoff commit is assembled.

---

## Phase 3: User Story 1 - Assemble One Atomic V2 Candidate (Priority: P1) 🎯 MVP

**Goal**: Produce one complete, non-mixed V2 candidate from exact accepted
handoffs without a V1 bridge or integrator-owned redesign.

**Independent Test**: Repository atomicity checks find exactly one canonical
interface version per contract, every in-tree consumer uses V2, all retired
paths are absent, and the candidate manifest matches the assembled commits.

### Implementation for User Story 1

- [ ] T009 [US1] Implement the repository-wide V2 atomicity and V1-residue checker in `scripts/check_v2_atomicity.py` after T006 fails as expected
- [ ] T010 [US1] Integrate accepted commits from slices `010`, `020`, `030`, `040`, and `050` and record exact commit/interface hashes in `evidence/v2/parity/integration-manifest.json`
- [ ] T011 [US1] Integrate accepted commits from slices `060`, `070`, `080`, `090`, and `100` and extend `evidence/v2/parity/integration-manifest.json` without changing owned semantics
- [ ] T012 [US1] Record every textual or semantic conflict, accountable owner, returned handback, and accepted resolution in `evidence/v2/parity/integration-conflicts.md`
- [ ] T013 [US1] Run `tests/v2/parity/test_integration_manifest.py`, `tests/v2/parity/test_repository_atomicity.py`, and `scripts/check_v2_atomicity.py` and record exact results in `evidence/v2/parity/atomicity-verification.txt`
- [ ] T014 [US1] Build and install the exact non-releaseable V2 candidate in the isolated integration environment and record package hashes and executable paths in `evidence/v2/parity/candidate-build.json`
- [ ] T015 [US1] Rerun slice `100`'s deterministic assurance and immutable-ref checks against the exact assembled candidate, compare security/semantic hashes with the audited set, return any divergence to its implementation owner and `v2-security-owner`, require their explicit repaired-ref/re-audit handoff for every affected stochastic/live cell before continuing, and record results in `evidence/v2/parity/security-recheck/README.md`

**Checkpoint**: The candidate remains off main and non-releaseable until US2 and
US3 evidence pass. Any mixed-version or unresolved owner conflict returns to the
owning slice.

---

## Phase 4: User Story 2 - Prove Surface Equivalence and Provenance (Priority: P1)

**Goal**: Prove S01-S13, S15, and S16 equivalence and exact installed-runtime
identity across every applicable adapter and harness.

**Independent Test**: The same canonical fixtures produce equivalent facts,
routing, participant availability, and receipts; every difference is an explicit
capability gap or a blocking defect; every live surface passes S12.

### Tests and Evaluation Assets for User Story 2

- [ ] T016 [P] [US2] Create canonical S01-S13, S15, and S16 native-event fixtures plus factual equivalence classes, injected validated attention decisions for ordinary routing, and trusted-bypass/forged-bypass/receipt-stage cases under `evals/v2/parity/fixtures/`
- [ ] T017 [P] [US2] Define the complete shared scene and surface applicability catalog, including stable `scene_id` and blocking/capability-limitation rules, in `evals/v2/parity/scene_catalog.py`
- [ ] T018 [US2] Implement deterministic cross-surface factual normalization, injected-decision routing mechanics for ordinary paths, zero-classifier-call trusted-bypass routing without an injected social result, participant availability, immutable stage-owner receipt checks, and capability-gap comparison in `evals/v2/parity/runner.py` after T007 fails, without encoding an expected social verdict
- [ ] T019 [US2] Implement installed candidate restart/reload and known-probe orchestration in `scripts/v2_surface_probe.py` after T008 fails as expected
- [ ] T020 [US2] Implement post-hoc participant-output grading for meta-answer failure, direct action, lightweight action, and valid silence in `evals/v2/parity/meta_answer.py` without exposing it to runtime send paths
- [ ] T021 [US2] Add end-to-end factual equivalence, injected-decision routing, trusted-bypass zero-call/no-fabricated-result, PREATTENTION_BYPASS act-or-silence, request-correlation, single-writer receipt-stage, participant-silence-no-delivery, post-hoc meta-answer, and no-runtime-prose-filter tests for CLI, transports, adapters, and harness boundaries in `tests/v2/parity/test_surface_parity.py`

### Per-Surface Verification for User Story 2

- [ ] T022 [US2] Run core/CLI S01-S13, S15, and S16 replay, including mandatory S06/S07/S10 bypass and receipt-stage cases, under `evidence/v2/parity/surfaces/core-cli/` plus S12 installed probe under `evidence/v2/provenance/core-cli/`
- [ ] T023 [US2] Run Hermes S01-S13, S15, and S16 replay, including mandatory S06/S07/S10 bypass and receipt-stage cases, under `evidence/v2/parity/surfaces/hermes/` plus S12 restart/probe under `evidence/v2/provenance/hermes/`
- [ ] T024 [US2] Run Claude Code S01-S13, S15, and S16 replay, including mandatory S06/S07/S10 bypass and receipt-stage cases, under `evidence/v2/parity/surfaces/claude-code/` plus S12 restart/probe under `evidence/v2/provenance/claude-code/`
- [ ] T025 [US2] Run Codex S01-S13, S15, and S16 replay, including mandatory S06/S07/S10 bypass and receipt-stage cases, under `evidence/v2/parity/surfaces/codex/` plus S12 restart/probe under `evidence/v2/provenance/codex/`
- [ ] T026 [US2] Run Discord-MCP and standalone channel-adapter applicable replays, including mandatory S06/S07/S10 bypass and receipt-stage cases where applicable, under `evidence/v2/parity/surfaces/transports-adapters/` plus S12 restart/probes under `evidence/v2/provenance/transports-adapters/`
- [ ] T027 [US2] Produce the factual cross-surface equivalence matrix, injected-decision routing comparison, trusted-bypass zero-call/no-fabricated-result results, immutable receipt-stage ownership, explicit platform capability gaps, blocking defects, flicker, and context-budget results in `evidence/v2/parity/s13-adapters/report.md` and `evidence/v2/parity/s15-context-budget/report.md`

**Checkpoint**: A source-only, stale-runtime, or unexplained-difference surface
is not parity-ready and blocks the candidate.

---

## Phase 5: User Story 3 - Validate Mixed Room and Release Boundary (Priority: P2)

**Goal**: Prove S14 on staged real rooms, index S01-S16 evidence, and make all
product/release documentation truthful without performing promotion.

**Independent Test**: Every required stage has transcript, receipts, provenance,
failure/limitation summary, and reproducible commands; docs contain no claim
beyond the final candidate/evidence; release decision requires no launch asset.

### Staged Room Evidence for User Story 3

- [ ] T028 [US3] Document the exact six-stage S14 ladder, participant identities, scripts, immutable request-correlated receipt-stage capture/ownership, participant-silence-no-delivery rule, post-hoc meta-answer rubric, stop conditions, evidence capture, redaction, and the rule that required lifecycle failures block while only genuinely unavailable native facts may be limitations in `docs/evaluations/v2-parity.md`
- [ ] T029 [US3] Run the Hermes-only stage and commit transcript, stable scene IDs, post-hoc participant grades, receipts, runtime provenance, and summary under `evidence/v2/live/s14-mixed-room/01-hermes/`
- [ ] T030 [US3] Run Hermes plus Claude Code and commit peer-hearing, no-polling, attention, post-hoc participant action/silence grades, and provenance under `evidence/v2/live/s14-mixed-room/02-claude/`
- [ ] T031 [US3] Run Hermes plus Codex and commit persistent-session, attention, post-hoc participant action/silence grades, send, and provenance under `evidence/v2/live/s14-mixed-room/03-codex/`
- [ ] T032 [US3] Run the full Hermes plus Claude Code plus Codex room and commit loop, all-speak/all-mute, restart, error, post-hoc direct-contribution/meta-answer grades, and provenance under `evidence/v2/live/s14-mixed-room/04-full/`
- [ ] T033 [US3] Run the multi-human Discord stage and commit distinct-user identity, cross-user safety, participant outcome, native capability, and provenance evidence under `evidence/v2/live/s14-mixed-room/05-multi-human-discord/`
- [ ] T034 [US3] Run the multi-human Telegram-via-Hermes stage and commit identity, participant outcome, native capability, missing-fact, and provenance evidence under `evidence/v2/live/s14-mixed-room/06-multi-human-telegram/`
- [ ] T035 [US3] Return every required-lifecycle or receipt-stage-ownership S14 failure to its upstream owner as blocking, record only genuinely unavailable native platform facts as limitations, and reconcile all six stages in `evidence/v2/live/s14-mixed-room/README.md`

### Evidence and Documentation for User Story 3

- [ ] T036 [US3] Assemble the V2 parity evidence index with S01-S16, security recheck, provenance, commands, failures, flicker, and limitations in `evidence/v2/README.md`
- [ ] T037 [US3] Map every S01-S16/surface pair to exact candidate refs, commands, stable `scene_id`, request ID, stage owner, trusted bypass provenance, `classifier_not_invoked` and classifier-call count where applicable, record paths, post-hoc grades, evidence grade, and pass/block/native-capability disposition in `evidence/v2/parity/manifest.json`
- [ ] T038 [US3] Update current behavior, V2 upgrade, supported/reference surface, and evidence-grade claims in `README.md`, `docs/integration.md`, and `docs/STABILITY.md`
- [ ] T039 [US3] Update exact version/change history and breaking migration boundary in `CHANGELOG.md` and `docs/releases/v2-readiness.md`
- [ ] T040 [US3] Create the V2 release-readiness boundary with candidate identity, supported/reference scope, evidence bar, limitations, and Zoe go/no-go field in `docs/releases/v2-readiness.md` without adding promotion content

**Checkpoint**: Documentation truth and release readiness may be proposed; no
package is published and no promotion work is authorized by this checkpoint.

---

## Phase 6: Final Candidate Decision Packet

- [ ] T041 Run `python3 scripts/check_governance.py`, `python3 -m unittest`, the V2 atomicity checker, the full parity replay including trusted-bypass and immutable-stage controls, slice-`100` assembled-candidate assurance, and documented live-evidence audits and record exact results in `evidence/v2/parity/final-verification.txt`
- [ ] T042 Re-run cross-artifact and dependency analysis, prove zero CRITICAL/HIGH findings and zero cycles, and record the result in `evidence/v2/README.md`
- [ ] T043 Finalize the integrated candidate manifest, scene/surface manifest, parity evidence index, and release-readiness boundary and hand the exact candidate commit, package hashes, commands/results, evidence, security disposition, and limitations to Zoe in `evidence/v2/parity/final-handoff.md`
- [ ] T044 After Zoe records explicit repository-cutover acceptance in `evidence/v2/parity/final-handoff.md`, open or update one atomic `integration/v2` pull request to main, record its URL in `evidence/v2/parity/main-cutover.md` before the final branch update, and merge only the complete accepted candidate
- [ ] T045 Check out the resulting main merge SHA, rerun governance, the full baseline, V2 atomicity, parity, assurance, installed-provenance smoke, and docs-truth checks, then record the merge SHA and exact results in `evidence/v2/parity/main-cutover.md` through an evidence-only follow-up commit/PR containing no product, runtime, schema, or behavior change and without publishing or promoting a release

---

## Dependencies & Execution Order

- T001-T003 require explicit Goal 2 authorization and accepted slices
  `010`–`100`; no other task may begin first.
- T004-T008 form the foundation and block all user stories.
- US1 must produce a deterministic, non-releaseable atomic candidate and pass
  T015 assembled-candidate assurance before US2.
- US2 must prove installed surface equivalence before US3 live room work.
- US3 must close staged evidence and docs truth before final verification.
- T041-T043 depend on all stories and complete the candidate decision packet.
- T044 requires Zoe's explicit repository-cutover acceptance of T043; T045
  requires the resulting main merge SHA and completes the atomic repository
  cutover without authorizing package release or promotion.
- Slice `110` is the final sink. It consumes `010`–`100` and produces only final
  cutover, evidence, and release-decision artifacts; it feeds no upstream slice,
  so the graph is acyclic.

## Parallel Opportunities

- T005-T008 are distinct test files and may run in parallel after T004 scope is
  fixed.
- T016 and T017 may run in parallel.
- T022-T026 may run in parallel only after the exact candidate and probe tooling
  are stable and each surface operator is available.
- Documentation drafting in T038-T040 may begin from evidence indexes, but final
  wording waits for T035-T037.
- Live stages T029-T034 are deliberately sequential validation stages sharing
  one candidate and evidence discipline; the Claude and Codex stages are
  pairwise harness checks, not claims that each room is a strict superset of the
  prior one.

## Implementation Strategy

1. Stop at T001 until Zoe authorizes Goal 2.
2. Admit every exact handoff and freeze canonical versions.
3. Assemble and mechanically reject mixed V1/V2 state off main.
4. Rerun blocking security assurance on the exact assembled candidate.
5. Prove deterministic factual/routing parity and installed-runtime identity
   surface by surface without a social-verdict oracle.
6. Run the six-stage mixed-room ladder with post-hoc participant-output grading.
7. Index evidence and make docs/release boundary truthful.
8. Submit one final candidate packet, obtain explicit repository-cutover
   acceptance, merge atomically to main, and verify the merge SHA.
9. Leave package release and promotion to their separate decisions.

## Notes

- Every task is future Goal 2 work; creating this file grants no implementation
  or release authority.
- `[P]` means distinct files and no dependency on an incomplete task.
- Product artifacts remain in ordinary paths; `specs/110...` contains planning
  only.
- Promotion remains wholly excluded even if the release boundary is accepted.
