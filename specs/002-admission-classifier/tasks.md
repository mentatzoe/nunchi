# Tasks: Admission Classifier Completion

**Input**: Design documents from `/specs/002-admission-classifier/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/admission-classifier.md, quickstart.md, checklists/admission-classifier.md

**Tests**: Required. The feature specification requires product classifier path evidence plus deterministic provider-fixture evidence for known false ACK/PASS cases, representative PASS/ACK/ASK/SPEAK, invalid classifier configuration, public CLI/core equivalence, and public install/CLI smoke.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the 002 feature branch without changing product behavior.

- [x] T001 Verify branch `002-admission-classifier` and active feature pointer in `.specify/feature.json`, `AGENTS.md`, and `CLAUDE.md`
- [x] T002 [P] Verify Python package/test baseline with `python -m unittest` from repository root
- [x] T003 [P] Review existing 001 CLI/core contract files in `src/turnaware/` and `tests/` to confirm compatibility baseline before edits

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared model/schema/classifier plumbing required by every story. No user-story behavior is complete until this phase is done.

- [x] T004 Add classifier selection fields (`classifier`, `classifier_config`) to request parsing/model validation in `src/turnaware/models.py` and `src/turnaware/schema.py`
- [x] T005 Add machine-readable `classifier` identity to successful admission results in `src/turnaware/models.py` and `src/turnaware/schema.py`
- [x] T006 Create classifier registry with product/default path, provider/model configuration, fixture-provider test evidence, and invalid-classifier errors in `src/turnaware/classifiers.py`
- [x] T007 Refactor `src/turnaware/core.py` so `evaluate()` delegates verdict choice through the classifier registry instead of inline substring-only classification
- [x] T008 Wire CLI flags `--classifier` and `--classifier-config` into `src/turnaware/cli.py`, with CLI classifier taking precedence over envelope classifier

**Checkpoint**: Shared classifier path/configuration boundary exists for CLI and core; story-specific tests may now target behavior.

---

## Phase 3: User Story 1 - Host selects an auditable classifier path (Priority: P1) 🎯 MVP

**Goal**: A host can use the product/default classifier path, every successful result names the selected classifier/provider/model, and `deterministic` is not exposed as a selectable classifier.

**Independent Test**: Evaluate valid envelopes through default product selection, explicit product CLI selection, envelope selection, CLI precedence, and deterministic fixture-provider output; every successful result includes classifier/provider/model identity and valid PASS/ACK/ASK/SPEAK result fields. If the product path is unavailable, default selection fails clearly and does not use local/deterministic fallback.

### Tests for User Story 1

> **NOTE: Write these tests FIRST and confirm they fail before implementation where behavior is missing.**

- [x] T009 [P] [US1] Add fixture with envelope-level classifier selection in `tests/fixtures/speak_with_classifier.json`
- [x] T010 [P] [US1] Add fixture for CLI-vs-envelope classifier precedence in `tests/fixtures/speak_cli_precedence.json`
- [x] T011 [US1] Add core tests for product/default classifier identity, unsupported deterministic classifier path, fixture-provider output, and envelope classifier identity in `tests/test_core.py`
- [x] T012 [US1] Add CLI tests for default product classifier, rejected `--classifier deterministic`, CLI-over-envelope precedence, and no silent fallback when product config is unavailable in `tests/test_cli.py`

### Implementation for User Story 1

- [x] T013 [US1] Implement default classifier selection as the product classifier path in `src/turnaware/classifiers.py` and `src/turnaware/core.py`; keep deterministic evidence as a fixture provider rather than a classifier path
- [x] T014 [US1] Implement envelope classifier selection in request validation in `src/turnaware/schema.py`
- [x] T015 [US1] Implement CLI classifier/config override precedence in `src/turnaware/cli.py`
- [x] T016 [US1] Ensure all successful result payloads include `classifier` in `src/turnaware/models.py`
- [x] T017 [US1] Run `python -m unittest tests.test_core tests.test_cli` and verify US1 passes independently

**Checkpoint**: User Story 1 is fully functional and testable independently.

---

## Phase 4: User Story 2 - Reviewer verifies known false verdicts are rejected (Priority: P2)

**Goal**: Product classifier behavior and deterministic provider-fixture evidence reject the known false ACK and false PASS cases while preserving a legitimate PASS path.

**Independent Test**: Run adversarial fixtures through the product classifier path with deterministic fixture-provider results, asserting expected verdicts, reasons, confidence shape, and checked-context evidence.

### Tests for User Story 2

> **NOTE: Write these tests FIRST and confirm they fail before implementation where behavior is missing.**

- [x] T018 [P] [US2] Add known false ACK fixture `tests/fixtures/false_ack_comment_back.json` expecting `SPEAK`, not `ACK`
- [x] T019 [P] [US2] Add known false PASS fixture `tests/fixtures/false_pass_contradicted_done.json` expecting non-PASS with contradiction checked
- [x] T020 [P] [US2] Add no-corroborating-context PASS-risk fixture `tests/fixtures/false_pass_no_corroboration.json`
- [x] T021 [US2] Add adversarial classifier tests for false ACK/PASS/no-corroboration cases in `tests/test_classifiers.py`
- [x] T022 [US2] Add confidence/context-truth assertions for adversarial cases in `tests/test_core.py`

### Implementation for User Story 2

- [x] T023 [US2] Implement assignment-vs-acknowledgement handling in `src/turnaware/classifiers.py` so `comment back with results` plus work assignment returns `SPEAK`
- [x] T024 [US2] Implement contradiction-aware PASS handling in `src/turnaware/classifiers.py` so resolved-looking triggers cannot short-circuit contradictory missing-work context
- [x] T025 [US2] Implement legitimate PASS handling only when inspected context corroborates completion in `src/turnaware/classifiers.py`
- [x] T026 [US2] Adjust confidence distributions/reasons in `src/turnaware/classifiers.py` so conflict/uncertainty is visible rather than a fixed high-confidence template
- [x] T027 [US2] Run `python -m unittest tests.test_classifiers tests.test_core` and verify US2 passes independently

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase 5: User Story 3 - Maintainer preserves the CLI/core contract while improving judgement (Priority: P3)

**Goal**: Public CLI and callable core stay contract-equivalent, installable, admission-only, and documented truthfully.

**Independent Test**: Run all provider-fixture scenarios through CLI and core, compare contract-equivalent result fields, verify invalid classifier failures, and complete quickstart install/CLI smoke.

### Tests for User Story 3

> **NOTE: Write these tests FIRST and confirm they fail before implementation where behavior is missing.**

- [x] T028 [P] [US3] Add invalid classifier fixture `tests/fixtures/invalid_classifier.json`
- [x] T029 [US3] Add schema tests for classifier field validation, invalid config failure, and forbidden reply fields in `tests/test_schema.py`
- [x] T030 [US3] Add CLI/core equivalence tests over PASS/ACK/ASK/SPEAK and adversarial fixtures in `tests/test_cli.py`
- [x] T031 [US3] Add CLI invalid classifier test asserting non-zero exit, clear stderr, and no successful stdout result in `tests/test_cli.py`

### Implementation for User Story 3

- [x] T032 [US3] Implement invalid classifier/config errors with no silent fallback in `src/turnaware/classifiers.py`, `src/turnaware/errors.py`, and `src/turnaware/cli.py`
- [x] T033 [US3] Ensure `context_checked` only names inspected supplied references in `src/turnaware/classifiers.py` and `src/turnaware/schema.py`
- [x] T034 [US3] Ensure callable core and CLI emit contract-equivalent JSON fields for the provider-fixture set in `src/turnaware/core.py` and `src/turnaware/cli.py`
- [x] T035 [US3] Update `README.md` only with verified classifier-selection usage and no adapter/launch/marketing claims
- [x] T036 [US3] Run `python -m unittest` and verify all tests pass

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Verification

**Purpose**: Final fake-done review and public install evidence.

- [x] T037 Run quickstart install smoke in a clean virtual environment from `specs/002-admission-classifier/quickstart.md`
- [x] T038 Run CLI evidence commands for product/default classifier/provider identity, rejected deterministic classifier, false ACK, false PASS, and invalid classifier cases from `specs/002-admission-classifier/quickstart.md`
- [x] T039 Review successful result payloads for absence of `message`, `reply`, `draft`, `content`, or other ordinary visible participation prose fields
- [x] T040 Review diff against `origin/main` to confirm adapters, Discord/cc-connect integration, broad benchmarks, launch claims, and marketing copy remain out of scope
- [x] T041 Commit the SpecKit artifacts and implementation on branch `002-admission-classifier`
- [x] T042 Open PR for TUR-11 and include evidence for tests, quickstart install, adversarial fixtures, classifier identity, and fake-done scope review

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundation; MVP path.
- **User Story 2 (Phase 4)**: Depends on Foundation and uses US1 classifier identity path for audit output.
- **User Story 3 (Phase 5)**: Depends on US1/US2 behavior for full equivalence evidence.
- **Polish (Phase 6)**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational; establishes classifier selection/audit path.
- **US2 (P2)**: Can start after Foundational but must preserve US1 result shape.
- **US3 (P3)**: Requires US1/US2 fixture set for full CLI/core equivalence and invalid-config evidence.

### Parallel Opportunities

- T002 and T003 can run in parallel after T001.
- T009 and T010 can run in parallel.
- T018, T019, and T020 can run in parallel.
- T028 can run in parallel with T029 once US1/US2 fixture conventions are settled.
- Source edits to `classifiers.py`, `cli.py`, and test fixture JSON can be parallelized only when file ownership is explicit; tasks touching the same file should be sequential.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete US1 tests T009-T012 and implementation T013-T016.
3. Validate with T017 before continuing.

### Incremental Delivery

1. Add classifier selection/audit identity (US1).
2. Add adversarial judgement fixes and deterministic provider-fixture evidence (US2).
3. Add CLI/core equivalence for product/default path, invalid classifier failure, docs, and public install evidence (US3 + Polish).

### Completion Summary

- Total tasks: 42
- User Story 1 tasks: 9
- User Story 2 tasks: 10
- User Story 3 tasks: 9
- Polish/final verification tasks: 6
- Suggested MVP scope: complete through T017 before claiming selected classifier path/audit identity works; do not claim product classifier completion until the provider-backed product/default path and deterministic provider-fixture evidence are verified.


