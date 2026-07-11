---

description: "Task list template for one existing Nunchi slice"
---

# Tasks: [EXISTING SLICE NAME]

**Input**: Existing slice design documents from `specs/[exact-slice]/`

**Prerequisites**: plan.md and spec.md (required), research.md when present,
zero CRITICAL/HIGH analysis findings, satisfied upstream slice dependencies,
one valid `evidence/governance/v2-implementation-authorization.md` enumerating
exactly slices `010` through `110`, an assigned participant, and accepted
slice-activation evidence before any product task begins

**Accountable owner lane**: [exactly one lane]

**Assigned participant / source**: [UNASSIGNED — awaiting durable external assignment source | participant — evidence/governance/assignments/<record>.md]

The non-symlink assignment record contains exactly one `Assignee`, `Lane`,
`Assigned by`, ISO `Assigned on`, and durable `Authority reference`; a non-Zoe
assigner also requires `Delegated by: Zoe` and a durable `Delegation
reference`. It may
precede authority but never grants authority or activates the slice. Do not
wait for unrelated slices to be assigned and do not create an assignment
registry.

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/[exact-slice]`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: [PLANNED initially; update through the canonical lifecycle]

**Program implementation authority**: [NOT_GRANTED | GRANTED with `evidence/governance/v2-implementation-authorization.md`]

**Activation evidence**: [evidence/v2/[slice]/slice-activation.md; written after all prerequisites are accepted to establish READY, before ACTIVE or any checked implementation task]

**Task manifest**: Run `python3 scripts/check_governance.py --task-manifest specs/[exact-slice]` and copy its exact `Initial task IDs` / `Initial tasks SHA256` into activation, then its `Completed task IDs` / `Tasks SHA256` into each candidate attempt.

**Candidate evidence**: [evidence/v2/[slice]/slice-candidate.md; required before CONVERGED]

**Handoff evidence**: [evidence/v2/[slice]/slice-handoff.md; required before HANDOFF_READY]

**Acceptance evidence**: [evidence/v2/[slice]/slice-acceptance.md; required before ACCEPTED]

Candidate and handoff files are append-only attempt streams. If convergence
adds tasks, retain activation, remain `ACTIVE`, and start a new bound
`run speckit`. A rejected completed handoff appends `REJECTED`, returns the
slice to `ACTIVE`, and also requires a new bound run; never resume that completed
run. A paused post-convergence gate may resume only for fixes that leave the
task graph unchanged. Append later candidate/handoff attempts without rewriting
history.

**Integration handoff**: [dependent owner or final integrator]

**Tests**: Product slices require red deterministic contract/mechanics tests,
replay or live evidence where the claim requires it, and an ordinary-path
scene-to-record command manifest. A unit-only social-quality claim is invalid.

**Documentation freshness**: Every implementation MUST execute the plan's exact
`README.md` and affected-doc dispositions. `NO_IMPACT` needs reviewed paths and
concrete rationale in ordinary handoff evidence; `HANDOFF` needs the exact delta
and accepting owner. Documentation is a blocking implementation task, not
optional polish.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions
- Product tasks MUST target ordinary paths (`src/`, `schemas/`, `tests/`,
  `evals/`, `evidence/`, `integrations/`, `scripts/`, or `docs/`), never
  `.specify/`, `specs/`, or a SpecKit skill directory.
- `specs/.../tasks.md` may describe product work but MUST NOT contain product
  artifacts or embedded executable payloads.
- Include exact documentation-disposition, validation, and handoff-evidence
  tasks before the final owner handoff.

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root
- **Contracts and schemas**: `schemas/` at repository root
- **Evaluation and evidence**: `evals/`, `evidence/` at repository root
- **Product documentation**: `docs/` at repository root
- **Web app**: `backend/src/`, `frontend/src/`
- **Mobile**: `api/src/`, `ios/src/` or `android/src/`
- Paths shown below assume single project - adjust based on plan.md structure

<!--
  ============================================================================
  IMPORTANT: The tasks below are SAMPLE TASKS for illustration purposes only.

  The /speckit-tasks command MUST replace these with actual tasks based on:
  - User stories from spec.md (with their priorities P1, P2, P3...)
  - Existing slice requirements from plan.md
  - Interface summaries and ordinary target paths from plan.md

  Tasks MUST be organized by user story so each story can be:
  - Implemented independently
  - Tested independently
  - Delivered as an MVP increment

  DO NOT keep these sample tasks in the generated tasks.md file.
  ============================================================================
-->

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create project structure per implementation plan
- [ ] T002 Initialize [language] project with [framework] dependencies
- [ ] T003 [P] Configure linting and formatting tools
- [ ] T004 Record the already-ACTIVE slice's exact implementation starting manifest under its ordinary evidence path; the external authorization and activation records document prerequisites but never grant authority

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

Examples of foundational tasks (adjust based on your project):

- [ ] T005 Create machine-readable shared contract in schemas/[name].json
- [ ] T006 [P] Add contract tests in tests/contract/test_[name].py
- [ ] T007 Create shared implementation boundary in src/[path].py
- [ ] T008 Configure error handling and off-surface telemetry in src/[path].py
- [ ] T009 Record installed-runtime provenance strategy in docs/[path].md

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T010 [P] [US1] Contract test for [endpoint] in tests/contract/test_[name].py
- [ ] T011 [P] [US1] Integration test for [user journey] in tests/integration/test_[name].py

### Implementation for User Story 1

- [ ] T012 [P] [US1] Create [Entity1] model in src/models/[entity1].py
- [ ] T013 [P] [US1] Create [Entity2] model in src/models/[entity2].py
- [ ] T014 [US1] Implement [Service] in src/services/[service].py (depends on T012, T013)
- [ ] T015 [US1] Implement [endpoint/feature] in src/[location]/[file].py
- [ ] T016 [US1] Add validation and error handling
- [ ] T017 [US1] Add logging for user story 1 operations

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 2 ⚠️

- [ ] T018 [P] [US2] Contract test for [endpoint] in tests/contract/test_[name].py
- [ ] T019 [P] [US2] Integration test for [user journey] in tests/integration/test_[name].py

### Implementation for User Story 2

- [ ] T020 [P] [US2] Create [Entity] model in src/models/[entity].py
- [ ] T021 [US2] Implement [Service] in src/services/[service].py
- [ ] T022 [US2] Implement [endpoint/feature] in src/[location]/[file].py
- [ ] T023 [US2] Integrate with User Story 1 components (if needed)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - [Title] (Priority: P3)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 3 ⚠️

- [ ] T024 [P] [US3] Contract test for [endpoint] in tests/contract/test_[name].py
- [ ] T025 [P] [US3] Integration test for [user journey] in tests/integration/test_[name].py

### Implementation for User Story 3

- [ ] T026 [P] [US3] Create [Entity] model in src/models/[entity].py
- [ ] T027 [US3] Implement [Service] in src/services/[service].py
- [ ] T028 [US3] Implement [endpoint/feature] in src/[location]/[file].py

**Checkpoint**: All user stories should now be independently functional

---

[Add more user story phases as needed, following the same pattern]

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] TXXX Execute every exact row in `plan.md` §Documentation Impact and Freshness, including each `UPDATE` in `README.md` and affected ordinary docs; reject generic directory scope and do not change integrator-owned current-state wording prematurely
- [ ] TXXX Validate affected documentation links, Mermaid diagrams, examples, commands, install/version claims, and truthfulness checks as applicable
- [ ] TXXX Record every `UPDATE`, `NO_IMPACT`, and `HANDOFF` disposition with exact reviewed paths, rationale or required delta, accepting owner, reviewer, and validation results in the slice's ordinary-path handoff evidence
- [ ] TXXX Code cleanup and refactoring
- [ ] TXXX Performance optimization across all stories
- [ ] TXXX [P] Additional unit tests (if requested) in tests/unit/
- [ ] TXXX Security hardening
- [ ] TXXX Run ordinary-path validation guide from docs/
- [ ] TXXX Commit required run records under evidence/
- [ ] TXXX Hand off commit, commands, evidence, interfaces, documentation disposition, and limitations to [owner lane] only after the documentation-freshness gate passes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete;
  documentation freshness blocks owner handoff

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - May integrate with US1 but should be independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - May integrate with US1/US2 but should be independently testable

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Documentation dispositions and validation before owner handoff
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Models within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all required tests for User Story 1 together:
Task: "Contract test for [endpoint] in tests/contract/test_[name].py"
Task: "Integration test for [user journey] in tests/integration/test_[name].py"

# Launch all models for User Story 1 together:
Task: "Create [Entity1] model in src/models/[entity1].py"
Task: "Create [Entity2] model in src/models/[entity2].py"
```

---

## Implementation Strategy

### Slice Candidate First

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Continue through the remaining planned stories; do not deploy or cut over

### Incremental Proof Within the Slice

1. Complete Setup + Foundational → slice foundation ready
2. Add User Story 1 → test independently → retain evidence
3. Add User Story 2 → test independently → retain evidence
4. Add User Story 3 → test independently → retain evidence
5. Converge one complete slice candidate, then use the governed handoff path

No story or intermediate slice state authorizes deployment, release, or
cutover. Only slice `110` integrates the complete accepted V2 set, and V2 cuts
over atomically after Zoe's decision.

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Delegated task A: User Story 1
   - Delegated task B: User Story 2
   - Delegated task C: User Story 3
3. One assigned slice participant remains accountable and converges all work;
   stories do not integrate or deploy independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
