# Existing Slice Specification: [SLICE NAME]

**Slice Branch**: `[canonical branch from umbrella]`

**Created**: [DATE]

**Status**: Draft

**Input**: User description: "$ARGUMENTS"

**Authority source**: [Aleph Vault selected design/decision link]

**Umbrella program**: [program directory]

**Accountable owner lane**: [exactly one owner lane]

**Assigned participant / source**: [UNASSIGNED — awaiting durable external assignment source | participant — evidence/governance/assignments/<record>.md]

The non-symlink assignment record MUST contain exactly one `Assignee`, `Lane`,
`Assigned by`, ISO `Assigned on`, and durable `Authority reference`. A non-Zoe
assigner additionally requires `Delegated by: Zoe` and a durable `Delegation
reference`. Assignment may precede implementation authority; it does not grant
authority or activate the slice.

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run nunchi-plan specs/[exact-slice]` for planning, or `python3 scripts/run_slice_workflow.py run speckit specs/[exact-slice]` for delivery

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: [PLANNED | READY | ACTIVE | CONVERGED | HANDOFF_READY | ACCEPTED]

**Program implementation authority**: [NOT_GRANTED | GRANTED with `evidence/governance/v2-implementation-authorization.md`]

**Activation evidence**: [`evidence/v2/[slice]/slice-activation.md`; written after prerequisites are accepted to establish READY, before ACTIVE]

**Candidate evidence**: [`evidence/v2/[slice]/slice-candidate.md`; required for CONVERGED]

**Handoff evidence**: [`evidence/v2/[slice]/slice-handoff.md`; required for HANDOFF_READY]

**Acceptance evidence**: [`evidence/v2/[slice]/slice-acceptance.md`; required for ACCEPTED]

**Rework execution**: [convergence-added tasks and rejected completed handoffs
start a new bound `run speckit`; paused post-convergence fixes resume only when
the task graph is unchanged; activation is retained and attempt streams append]

**Depends on**: [slice ids or none]

**Dependency commits / acceptance references**: [ordered `slice=full-sha` and
`slice=repo-relative-evidence-reference` mappings; `none` when dependency-free]

**Feeds**: [dependent slice ids or final integration]

## Control-Plane Boundary *(mandatory)*

- This directory contains planning artifacts only.
- Product source, contracts, schemas, tests, fixtures, evaluations, evidence,
  runtime assets, and documentation MUST target ordinary repository paths.
- Unless the one complete authorization record enumerates exactly slices `010`
  through `110` and every independent readiness prerequisite for this slice is
  satisfied, this slice MUST remain `PLANNED` and dormant.
- State the exact product behavior that is out of scope for this slice.

## Interface Summary *(mandatory)*

- **Consumes**: [named/versioned interfaces and owning slices]
- **Produces**: [named/versioned interfaces and dependent slices]
- **Integration handoff**: [owner lane and required handoff evidence]

## Documentation Freshness *(mandatory)*

- **`README.md` disposition**: [`UPDATE` | `NO_IMPACT` with concrete rationale |
  `HANDOFF` with exact claim delta and accepting owner]
- **Affected ordinary docs**: [exact `docs/` or other ordinary documentation
  paths, each with `UPDATE`, `NO_IMPACT`, or `HANDOFF`]
- **Validation**: [links, Mermaid, examples, commands, truthfulness tests, or
  other checks appropriate to the claims]
- **Handoff evidence**: [ordinary-path evidence record that will contain exact
  reviewed paths, dispositions, rationale/delta, reviewer, and results]

Every implementation MUST review `README.md`. `NO_IMPACT` requires exact paths
and rationale in ordinary handoff evidence. `HANDOFF` is valid only for shared
or integrator-owned documentation and MUST name the accepting owner and exact
required change. Generic directories or wildcards do not replace exact file
paths when the affected documents are already known.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE inside this slice.
  Nunchi slices are not independently deployable products: only slice 110 may
  integrate the complete accepted V2 set, and V2 cuts over atomically.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Proven independently in the slice's ordinary evidence
  - Handed to the designated acceptance owner without deployment
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 3 - [Brief Title] (Priority: P3)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when [boundary condition]?
- How does system handle [error scenario]?
- What happens when an upstream interface is absent, stale, or at the wrong version?
- What platform facts are unavailable and must remain explicitly unknown?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]
- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g., "log all security events"]
- **FR-006**: The slice MUST name acceptance scenes and ordinary-path evidence requirements.
- **FR-007**: The slice MUST preserve the control-plane/product-artifact boundary.
- **FR-008**: Every aggregate evidence record MUST carry a stable scene/case ID and appear in an exact ordinary-path manifest.
- **FR-009**: The slice MUST execute and evidence its `README.md` and affected-docs freshness dispositions before handoff.

*Example of marking unclear requirements:*

- **FR-010**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]
- **FR-011**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

### Key Entities *(include if the slice involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]
- **SC-005**: Every affected documentation claim is updated and validated, or has a reviewed evidence-backed `NO_IMPACT`/`HANDOFF` disposition.

## Assumptions

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right assumptions based on reasonable defaults
  chosen when the slice description did not specify certain details.
-->

- [Assumption about target users, e.g., "Users have stable internet connectivity"]
- [Assumption about scope boundaries, e.g., "Mobile support is out of scope for v1"]
- [Assumption about data/environment, e.g., "Existing authentication system will be reused"]
- [Dependency on existing system/service, e.g., "Requires access to the existing user profile API"]

## Explicit Exclusions

- [Product behavior, component, migration bridge, or release claim intentionally excluded]
- [Any work reserved for another owner lane]
