# Program Specification: Nunchi V2 End-to-End Parity

**Feature Branch**: `chore/v2-execution-spine`

**Created**: 2026-07-11

**Status**: Goal 1 planning complete; Goal 2 not yet authorized

**Input**: Establish one implementation-ready V2 program from the selected
Nunchi technical design without implementing V2 product behavior under Goal 1.

**Authority source**: Aleph Vault selected design PR 67 (`bdd1ebb`) and contract-clarification PR 68 (`c834e8c`)

**Umbrella program**: this directory

**Accountable owner lane**: `v2-program-owner`

**Depends on**: selected Vault design and Nunchi Constitution 2.1.0

**Feeds**: slices `010` through `110` and the separately commissioned Goal 2

## Control-Plane Boundary

- This directory and every child slice contain planning artifacts only.
- Goal 1 MUST NOT change V2 product behavior.
- Future product source targets `src/` or `integrations/`; contracts target
  `schemas/`; tests target `tests/`; reusable evaluation assets target `evals/`;
  run records target `evidence/`; documentation targets `docs/`.
- No build, test, evaluation, docs, packaging, release, or runtime command may
  depend on this program directory.
- Goal 2 is an explicit external authorization gate, not a task status.

## Interface Summary

- **Consumes**: selected Aleph Vault V2 technical design; current ordinary-path
  V1 implementation and evidence; Constitution 2.1.0.
- **Produces**: an acyclic slice graph, stable owner lanes, a shared interface
  registry, acceptance-scene catalog, integration order, and evidence contract.
- **Integration handoff**: `v2-program-owner` activates the named slice lanes;
  `v2-integrator` accepts their explicit handoffs and owns the atomic cutover.

## User Scenarios & Testing

### User Story 1 - Start one bounded owner lane without rediscovering the design (Priority: P1)

A Goal 2 implementer can select one slice, identify its one accountable owner,
see all prerequisites and interfaces, and begin work without re-litigating the
selected product flow or reading another slice's private context.

**Why this priority**: Detached ownership and competing interpretations caused
the previous parity failure.

**Independent Test**: Choose any slice from `010` through `110` and locate one
owner, complete upstream/downstream edges, consumed/produced interfaces,
ordinary target paths, acceptance scenes, and evidence paths in its spec/plan.

**Acceptance Scenarios**:

1. **Given** a slice ID, **When** an implementer reads its artifacts, **Then**
   exactly one owner lane and no unresolved ownership placeholder is present.
2. **Given** an interface change request owned elsewhere, **When** the slice
   owner encounters it, **Then** the plan identifies the owning lane and handoff
   rather than silently broadening scope.

---

### User Story 2 - Execute foundations and integrations in safe parallel waves (Priority: P1)

The program owner can sequence contract, observation, attention, wake,
transport, adapter, and harness work so independent lanes run in parallel only
after their real prerequisites land.

**Why this priority**: Parallelism without a shared contract previously created
locally correct but incompatible implementations.

**Independent Test**: Topologically sort the declared dependency graph and
verify each wave has no dependency on an unfinished slice and no two parallel
lanes own the same interface or shared integration file.

**Acceptance Scenarios**:

1. **Given** slice `010` is complete, **When** Wave 1 begins, **Then** `020` and
   `030` may proceed in parallel under different owners.
2. **Given** any foundation slice is incomplete, **When** a dependent harness
   lane requests activation, **Then** the program blocks that activation.

---

### User Story 3 - Integrate one atomic V2 lifecycle across every in-tree consumer (Priority: P1)

The final integrator can assemble one V2 contract and lifecycle across the core,
CLI, shared transport, Hermes, Claude Code, Codex, and standalone adapters
without a mixed-version repository or send-time social reclassification.

**Why this priority**: End-to-end parity, not a local component, is the final
success mode.

**Independent Test**: Inspect the final integration plan and prove every in-tree
consumer has a dependency edge, an installed-runtime probe, and the common
attention-to-normal-participant-turn scenes.

**Acceptance Scenarios**:

1. **Given** all owner handoffs, **When** `v2-integrator` assembles the cutover,
   **Then** no in-tree consumer uses V1 request or verdict semantics.
2. **Given** an unavailable platform fact, **When** parity is evaluated, **Then**
   the difference is represented as unavailable rather than invented.

---

### User Story 4 - Accept V2 only against evidence, not artifact completion (Priority: P2)

A reviewer can trace every product claim to deterministic tests, replay
evaluation, live acceptance scenes, and installed-runtime provenance in ordinary
repository locations.

**Why this priority**: Generated schemas, green unit tests, and completed task
lists previously created false confidence.

**Independent Test**: Select every program acceptance scene and locate its
responsible slice, deterministic check when applicable, live evidence target,
and final parity gate.

**Acceptance Scenarios**:

1. **Given** a green unit suite with no live room record, **When** a reviewer
   evaluates a social-parity claim, **Then** the claim remains incomplete.
2. **Given** a live surface probe, **When** it lacks exact installed commit or
   package provenance, **Then** the surface remains unverified.

### Edge Cases

- A runtime occupies two owner lanes: the program requires explicit handoff or
  separate work contexts; ownership never becomes shared implicitly.
- An upstream interface changes after dependent work begins: dependents pause,
  pin the prior version, or accept an explicit versioned handoff.
- A platform cannot supply a native relation: normalization records the missing
  capability and parity compares only equivalent available facts.
- A slice is code-green but misses a required scene or evidence record: the
  handoff is rejected.
- A workflow reaches implementation during Goal 1: the Goal 2 gate is rejected
  and the run aborts.
- A new product artifact appears under `specs/`: governance validation fails.

## Requirements

### Functional Requirements

- **FR-001**: The program MUST define exactly one umbrella and the bounded
  slices `010` through `110`.
- **FR-002**: Every slice MUST name exactly one stable accountable owner lane.
- **FR-003**: Every slice MUST list all hard dependencies and downstream feeds.
- **FR-004**: The dependency graph MUST be acyclic and topologically executable.
- **FR-005**: Every slice MUST identify the versioned interfaces it consumes
  and produces and the lane that owns each interface.
- **FR-006**: Every slice MUST list ordinary repository targets for future
  implementation, schemas, tests, evals, evidence, and docs.
- **FR-007**: Every slice MUST define an isolated worktree/branch strategy and
  an explicit handoff recipient.
- **FR-008**: Every slice MUST define independently testable acceptance scenes
  and ordinary-path evidence requirements.
- **FR-009**: The program MUST reserve V2 implementation for separately
  authorized Goal 2.
- **FR-010**: The program MUST prevent product assets and product workflow
  dependencies inside SpecKit-managed paths.
- **FR-011**: The program MUST use a breaking atomic V2 cutover with no V1
  translation bridge or mixed in-tree consumers.
- **FR-012**: The program MUST preserve the separate evidence-gated dual-valve
  uncertainty transition.
- **FR-013**: The program MUST include core, CLI, observation, wake, shared
  Discord transport, Hermes, Claude Code, Codex, and all in-tree standalone
  channel adapters in implementation parity.
- **FR-014**: The program MUST include security, governed-suppression controls,
  send safety, credential handling, and installed-runtime provenance as a
  blocking assurance slice.
- **FR-015**: The final parity slice MUST own cross-surface comparison, staged
  mixed-room scenes, evidence assembly, truthful docs, and atomic integration.
- **FR-016**: Promotion and outward launch work MUST remain out of scope.
- **FR-017**: Every handoff MUST include commit, commands/results, interface
  version, evidence paths, runtime provenance, and known limitations.
- **FR-018**: Analysis MUST have zero CRITICAL/HIGH findings before a slice may
  cross the Goal 2 implementation gate.
- **FR-019**: Green unit tests MUST NOT satisfy stochastic social-quality or
  live-parity evidence requirements by themselves.
- **FR-020**: The full existing V1 test baseline MUST remain green throughout
  Goal 1 and at Goal 2 entry.
- **FR-021**: Trusted preattention-disabled operation MUST be represented as a
  non-social bypass that invokes the participant without a classifier call or
  fabricated social disposition; it MUST NOT be collapsed into WAKE, DEFER,
  ERROR, or suppression.
- **FR-022**: Lifecycle telemetry MUST use immutable, request-correlated
  observation, attention, participant-host, and transport receipt stages. Each
  owner may attest only its own stage and MUST NOT mutate another owner's facts.
- **FR-023**: Host-only continuation handles, binding tokens, cursors, and
  expiry values MUST remain outside the classifier projection; only factual
  coverage and expansion-availability booleans may cross that boundary.
- **FR-024**: Every implementation slice MUST review `README.md` and affected
  ordinary docs, execute exact `UPDATE`, evidence-backed `NO_IMPACT`, or
  owner-accepted `HANDOFF` dispositions, and pass documentation freshness
  before handoff.
- **FR-025**: Checked Goal 2 tasks MUST be rejected until Zoe's separately
  granted objective is recorded at
  `evidence/governance/v2-goal-2-authorization.md`; the record documents rather
  than grants authority, and a valid record MUST permit truthful task progress.

### Key Entities

- **Program**: umbrella authority, dependency graph, interface registry,
  integration waves, and final success contract.
- **Slice**: one bounded unit of implementation and evidence with one owner.
- **Owner lane**: stable accountable role occupied by one runtime or human work
  context at a time.
- **Interface**: versioned contract owned by one slice and consumed by named
  dependents.
- **Acceptance scene**: reproducible factual setup and expected lifecycle result.
- **Evidence requirement**: ordinary-path deterministic or live artifact needed
  to substantiate a claim.
- **Handoff packet**: commit and proof bundle transferred between owner lanes.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of the eleven slices name exactly one owner lane.
- **SC-002**: 100% of slices list dependencies, feeds, interfaces, integration
  strategy, acceptance scenes, and evidence targets.
- **SC-003**: The dependency graph has zero cycles and one final sink: `110`.
- **SC-004**: Every interface in the umbrella registry has one owning slice and
  at least one named consumer or final-integration purpose.
- **SC-005**: No file or directory prohibited by Constitution VII exists under
  `specs/`.
- **SC-006**: No executable build/test/eval/package/release/runtime path depends
  on `.specify/` or `specs/`.
- **SC-007**: Both installed workflows parse; `nunchi-plan` has zero
  implementation steps and `speckit` has a Goal 2 gate before implementation.
- **SC-008**: Both Codex and Claude integration manifests and the installed CLI
  report SpecKit `0.12.11`.
- **SC-009**: The pre-existing baseline remains 968 tests—960 passing and 8
  skipped; governance tests add coverage without removing or weakening an
  existing test.
- **SC-010**: Every common acceptance scene maps to at least one implementing
  slice and to final parity slice `110`.
- **SC-011**: There are zero unresolved placeholders, ownership gaps, dependency
  ambiguities, or CRITICAL/HIGH analysis findings at Goal 1 exit.
- **SC-012**: Removing managed paths in a disposable verification copy leaves
  ordinary tests and eval discovery runnable before fresh initialization.
- **SC-013**: Every slice has an exact README/docs disposition, validation task,
  ordinary handoff evidence target, and reviewer gate; slice `110` owns the
  mandatory global current-state update at atomic cutover.
- **SC-014**: Governance rejects a checked implementation task with no valid
  Goal 2 authorization record and accepts the same task state after a valid
  externally granted record exists.

## Assumptions

- Owner lane names are stable accountability identities; Goal 2 may assign a
  specific runtime or human without rewriting slice ownership.
- All in-tree consumers migrate even if their eventual release/product tier is
  decided later.
- The selected Vault design is complete enough for planning; this goal does not
  reopen product choices already selected by Zoe.
- V1 ordinary-path tests and evidence remain historical inputs, not V2 proof.

## Explicit Exclusions

- Any V2 source, schema, test, fixture, evaluation, runtime, deployment, or
  product-documentation implementation under Goal 1.
- A V1-to-V2 compatibility bridge or mixed-version in-tree repository.
- A handled/open ledger, inferred participant registry, central floor manager,
  deterministic social heuristic, or send-time social reclassification.
- Promotion, launch copy, community posting, or a package release promise.
