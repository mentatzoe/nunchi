# Existing Slice Specification: V2 Standalone Channel Adapters

**Feature Branch**: `v2/channel-adapters`

**Created**: 2026-07-11

**Slice state**: `PLANNED`

**Program implementation authority**: `NOT_GRANTED`

**Activation evidence**: `evidence/v2/adapters/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts and
establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/adapters/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/adapters/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/adapters/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Input**: Plan atomic V2 parity for the generic, Discord, Matrix, and Telegram standalone adapters without implementation now.

**Authority source**: Aleph Vault selected design `bdd1ebb`, contract-clarified at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-adapters-owner`

**Assigned participant / source**: `UNASSIGNED` — may be replaced during
planning, before implementation authority, only from a durable external
assignment source; activation evidence later copies and attests it when
establishing `READY`

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/090-v2-channel-adapters`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/090-v2-channel-adapters`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`

**Dependency commits / acceptance references**: at readiness,
`slice-activation.md` MUST record `Accepted dependencies` in the declared order,
ordered `Dependency commits` as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Feeds**: `100-v2-security-provenance`, `110-v2-parity-cutover`

**Rejection / rework evidence**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

## Control-Plane Boundary

- This directory contains planning artifacts only.
- Authorized slice implementation targets `src/nunchi/adapters/`; deterministic
  tests and native fixtures target `tests/`; reusable cross-adapter replay
  targets `evals/`; per-surface run records target `evidence/`; product
  documentation targets `docs/`.
- This planning baseline creates no product behavior. Authorized slice
  implementation requires the one valid complete authorization record at
  `evidence/governance/v2-implementation-authorization.md` enumerating exactly
  slices `010` through `110`; accepted handoffs from slices `010` through `040`;
  an active `v2-adapters-owner`; an assigned participant and durable external assignment
  source declared above; zero CRITICAL/HIGH analysis findings; and an isolated
  worktree. Only after those facts are accepted does activation evidence attest
  them and establish `READY` before `ACTIVE`.
- This slice creates no public interface and does not own shared schemas, core
  attention, observation semantics, or participant-turn behavior.

## Interface Summary

- **Consumes**: `I-010A AttentionRequestV2@1`, `I-010B
  AttentionDecisionV2@1`, `I-010C ParticipantWakeV2@1`, `I-010D
  ContextContinuationV2@1`, `I-010E AttentionReceiptV2@1`, `I-020A
  ObservationProviderV2@1`, `I-030A AttentionEngineV2@1`, and `I-040A
  ParticipantTurnHostV2@1`.
- **Produces**: generic, standalone Discord, Matrix, and Telegram conformance
  implementations plus a cross-adapter capability/evidence packet, including
  adapter-owned immutable `I-010E` transport stages for native outcomes each
  adapter directly attests; no new cross-slice public interface.
- **Integration handoff**: `v2-adapters-owner` supplies one exact commit,
  per-entrypoint installed provenance, commands/results, capability matrix,
  equivalent-scene evidence, a complete AD/common-scene manifest, and limitations
  to `v2-security-owner` and `v2-integrator`.

## User Scenarios & Testing

### User Story 1 - Preserve the facts each platform actually knows (Priority: P1)

Generic, Discord, Matrix, and Telegram inputs normalize equivalent native facts
equivalently while representing unavailable identity, relation, reaction,
membership, history, and restart capability honestly.

**Why this priority**: Adapter parity depends on preserving platform truth, not
flattening it into prose or inventing a universal feature set.

**Independent Test**: Feed matched native conversations and platform-specific
missing-capability variants through each adapter; compare `I-010A` actors,
events, order, trigger, coverage, and continuation without invoking the model.

**Acceptance Scenarios**:

1. **Given** equivalent direct mention and reply facts on two surfaces, **When**
   each adapter normalizes them, **Then** the portable observation is equivalent.
2. **Given** a platform that cannot retrieve a relation or event kind, **When**
   it normalizes the event, **Then** coverage states unknown/unavailable instead
   of inventing the fact.
3. **Given** display-name or alias collision, **When** an adapter binds self,
   **Then** only transport/host-attested actor identity establishes authorship.

---

### User Story 2 - Route one common attention-to-participant lifecycle (Priority: P1)

Every standalone adapter calls the common attention engine once. The engine
makes one logical classifier call for an ordinary trigger or zero
classifier/model calls for trusted bypass, then the adapter routes the result
through the common direct act-or-silence participant host without a
surface-specific social algorithm or second send judgment.

**Why this priority**: Existing adapters must not remain on V1 or implement four
different interpretations of who should speak.

**Independent Test**: Run the same SUPPRESS/WAKE/dual-DEFER/error/bypass and
message/reaction/tool/silence scenes through each adapter against a stubbed
participant host, then compare call counts, factual availability, and immutable
request-correlated receipt stages.

**Acceptance Scenarios**:

1. **Given** effective `SUPPRESS`, **When** any adapter routes it, **Then** it
   invokes no participant turn but retains the event under ordinary observation.
2. **Given** a waking route, **When** any adapter invokes the participant, **Then**
   exactly one `I-010C` turn is instructed to address the room and may act or end
   silently; any meta-answer is an evaluation failure, not a runtime output filter.
3. **Given** a participant send, **When** the adapter applies its backstop, **Then**
   only operational surface safety applies and no social reclassification runs.
4. **Given** trusted `status: bypass` with cause `preattention-disabled`, **When**
   any adapter routes it, **Then** it calls no classifier, invokes one
   advice-free `PREATTENTION_BYPASS` act-or-silence turn, and fabricates no
   classifier/effective disposition.

---

### User Story 3 - Prove adapter and installed-entrypoint parity (Priority: P2)

An operator can invoke each shipped standalone entrypoint from an exact package,
run its supported live/bounded scene, and compare only equivalent available facts
under one V2 lifecycle.

**Why this priority**: In-tree adapters cannot remain ambiguous V1 consumers,
even if their eventual release tier is decided later.

**Independent Test**: Install an exact candidate wheel, invoke generic,
Discord, Matrix, and Telegram entrypoints, restart where applicable, run matched
scenes, and record schema/interface versions plus honest capability differences.

**Acceptance Scenarios**:

1. **Given** all in-tree adapter entrypoints, **When** the atomic cutover audit
   runs, **Then** none accepts or emits V1 request/verdict semantics.
2. **Given** matched native facts, **When** attention and participant routing are
   compared, **Then** outcomes and factual availability are equivalent modulo
   explicitly unavailable platform facts.
3. **Given** an installed entrypoint, **When** a V2 probe runs, **Then** evidence
   identifies exact wheel/commit, executable, configuration, process, surface,
   and consumed-interface versions.

### Edge Cases

- A generic host supplies no native platform account: it must provide an
  install-attested namespace-qualified actor ID, not an alias fallback.
- Discord standalone and shared Discord-MCP observe equivalent events: parity
  compares facts without forcing these independent components to share runtime.
- Matrix membership scope differs from Telegram chat membership: each stays
  literal and is not normalized into a fictitious universal roster.
- A platform's history is live-only or unavailable after restart: coverage and
  social-suppression eligibility reflect that limitation.
- An adapter receives malformed data after it can construct a routable native
  event: the result is operational error/wake default, not fail-silent.
- A responder lacks a reaction/tool capability: participant action options and
  evidence state the absence rather than simulating a message.
- Room content or an untrusted adapter payload claims bypass, or an adapter
  attempts to rewrite an observation, attention, or participant-host receipt:
  the claim is rejected and the adapter never impersonates another stage owner.

## Requirements

### Functional Requirements

- **FR-001**: All four in-tree standalone adapters MUST consume the exact
  canonical V2 interfaces and MUST NOT retain a V1 translation bridge.
- **FR-002**: Every adapter MUST bind self through transport/host-attested actor
  identity and MUST NOT use aliases or display names as authorship proof.
- **FR-003**: Every adapter MUST preserve native event order, actors, mentions,
  replies/threads, reactions, membership changes, and timestamps when available.
- **FR-004**: Unavailable platform facts MUST remain explicitly unavailable,
  unknown, unresolved, or gap-marked; adapters MUST NOT invent parity.
- **FR-005**: Every adapter MUST implement bounded `I-020A` observation with
  honest coverage and `I-010D` only where it can fulfill expansion truthfully.
- **FR-006**: Deterministic no-wake MUST be limited to exact duplicate,
  exact-self-no-wake, authorization/routing rejection, and unconstructable native
  payloads.
- **FR-007**: No adapter MAY infer addressee, relevance, resolution, obligation,
  handled state, speaker priority, or turn ownership.
- **FR-008**: Every exact routable trigger MUST invoke `I-030A` exactly once.
  The engine MUST make exactly one logical classifier call on an ordinary path
  and zero classifier/model calls for trusted `status: bypass` /
  `PREATTENTION_BYPASS`.
- **FR-009**: Effective `SUPPRESS` MUST stop only the wake; `WAKE`, both `DEFER`
  sources, trusted `PREATTENTION_BYPASS`, and default `ERROR` MUST invoke one
  `I-040A` act-or-silence turn with a direct-room instruction; bypass MUST carry
  no advice or social result, and meta-answer scoring is evaluation-only and
  MUST NOT become an adapter prose filter.
- **FR-010**: Participant facts, advice, actions, silence, and operational errors
  MUST remain distinct and conform to `I-010C`/`I-010E`.
- **FR-011**: Surface responders and send backstops MUST NOT re-run a social
  judgment or require per-trigger social permission state.
- **FR-012**: Equivalent available native facts MUST produce equivalent portable
  observations, routing, and participant factual availability across adapters.
- **FR-013**: Generic, Discord, Matrix, and Telegram differences in history,
  restart, event visibility, continuation, reaction, and send capability MUST be
  documented and evidenced per surface.
- **FR-014**: Every shipped adapter entrypoint MUST have exact installed
  wheel/commit/executable/config/process provenance and a live or bounded V2 probe.
- **FR-015**: The slice MUST provide deterministic, native-fixture, cross-adapter
  replay, surface probe, restart, mixed-room compatibility, and provenance
  evidence in ordinary paths; every record MUST carry its AD/common scene ID and
  be resolved by one evidence manifest.
- **FR-016**: The slice MUST preserve the control-plane/product-artifact and
  program/slice lifecycle boundaries; its planning baseline MUST create no
  product behavior.
- **FR-017**: Each adapter MUST preserve immutable, request-correlated `I-010E`
  observation, attention, participant-host, and transport stages. It MAY append
  only the `transport` stage for a native delivery, rejection, or operational
  result it directly owns and attests; it MUST NOT mutate prior stages, fill a
  future stage, or fabricate a transport outcome when the participant stays
  silent. Bypass evidence MUST retain trusted provenance and
  `classifier_not_invoked` in the attention stage.

### Key Entities

- **Adapter binding**: platform/host identity, exact self actor, room continuity
  scope, loose participant description, and trusted configuration.
- **Native capability profile**: facts and actions the surface can provide live,
  through history, or not at all.
- **Portable observation**: adapter-produced `I-010A` plus honest coverage and
  optional `I-010D` via `I-020A`.
- **Adapter participant turn**: surface-specific implementation of `I-040A` with
  normal action or silence.
- **Adapter provenance record**: exact installed package, entrypoint, config,
  process, surface, and interface versions.
- **Adapter transport receipt stage**: immutable request-correlated `I-010E`
  record for the native delivery/rejection/operational fact that one adapter
  directly attests, with every other owner's stage preserved unchanged.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of matched facts normalize identically across applicable
  adapters; every difference maps to an explicit native capability absence.
- **SC-002**: Alias-collision fixtures establish zero false self-authorship claims
  across all four adapter families.
- **SC-003**: Each unique routable trigger causes exactly one attention-engine
  invocation; each ordinary path causes exactly one logical classifier call,
  each trusted bypass causes zero classifier/model calls, and every adapter
  causes zero send-time social calls.
- **SC-004**: Every disposition, PREATTENTION_BYPASS, and action/silence outcome
  routes according to the common lifecycle in 100% of conformance scenes.
- **SC-005**: Each surface has committed restart/event-visibility/continuation
  evidence or an explicit unavailable-capability record.
- **SC-006**: Generic, Discord, Matrix, and Telegram migration claims each cite
  exact installed package/entrypoint/config/process and interface provenance.
- **SC-007**: AD-01 through AD-09 each have a producing task and one manifest
  entry that resolves the scene ID to its exact ordinary evidence record.
- **SC-008**: Every adapter bypass case proves zero classifier calls, one
  act-or-silence invocation, no fabricated social or silent-delivery result, and
  no mutation or speculative completion of another owner's `I-010E` stage.

## Assumptions

- Standalone adapters remain in-tree consumers for atomic V2 cutover regardless
  of later release-tier decisions.
- The generic adapter can require an install-attested synthetic actor binding
  when no native account exists.
- Cross-adapter parity compares equivalent facts and lifecycle, not identical
  transport features.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` exact installed adapter entrypoints,
  capability differences, limitations, and evidence-grade deltas to
  `v2-integrator`.
- **Affected ordinary docs**: `UPDATE` `docs/adapters-v2.md` and validate
  invocation, budgets, capability semantics, entrypoints, links, examples, and
  probes across installed adapters. `HANDOFF` exact current-state,
  supersession, stability, and breaking-change deltas for `CHANGELOG.md`,
  `docs/adapters.md`, `docs/integration.md`, `docs/STABILITY.md`,
  `docs/contracts/channel-adapter-v1.md`, and
  `docs/architecture/v2-selected-design.md` to accepting `v2-integrator`.
- **Handoff evidence**: `evidence/v2/adapters/handoff.md` records reviewed
  paths, dispositions, exact delta, validation, and reviewer.

## Explicit Exclusions

- Ownership of `schemas/v2/`, core attention, common observation semantics,
  participant-turn host, or shared Discord-MCP source.
- A universal participant roster, floor manager, handled/open ledger, or
  adapter-specific deterministic social policy.
- Promotion, release-tier decisions, or implementation/live probing before this
  slice is validly activated.
