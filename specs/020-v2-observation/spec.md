# Existing Slice Specification: V2 Observation

**Feature Branch**: `v2/observation`

**Created**: 2026-07-11

**Slice state**: `HANDOFF_READY`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/observation/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/observation/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/observation/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/observation/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Input**: Define shared normalization and bounded-observation mechanics plus
reusable reference scenes that every in-tree surface can bind and prove in its
own integration slice.

**Authority source**: Zoe-selected Aleph Vault design at `bdd1ebb`, contract-clarified in PR 68 at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-observation-owner`

**Assigned participant / source**: Aleph — evidence/governance/assignments/aleph-v2-observation-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/020-v2-observation`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: `010-v2-contract`

**Dependency commits / acceptance references**: at readiness,
`slice-activation.md` MUST record `Accepted dependencies` in the declared order,
ordered `Dependency commits` as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Feeds**: `040`, `050`, `060`, `070`, `080`, `090`, `100`, `110`

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
- Authorized slice implementation targets `src/nunchi/observation.py`; tests target
  `tests/v2/observation/`, reusable replay assets `evals/v2/observation/`, evidence
  `evidence/v2/observation/`, and documentation `docs/observation/`.
- This planning baseline creates no collector, buffer, continuation provider,
  adapter change, test, corpus, evidence, product documentation, or V2 runtime
  behavior.
- While the slice is `PLANNED`, every task remains `DORMANT`; the repository
  remains V1 until slice `110` performs the atomic cutover.

## Interface Summary

- **Consumes**:
  - `I-010A AttentionRequestV2@1`
  - `I-010D ContextContinuationV2@1`
  - the immutable staged-record shape of `I-010E AttentionReceiptV2@2`,
    accepted by this consumer in
    `evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`; the
    observation-stage definition is byte-for-byte unchanged from the
    previously accepted `@1`, while the amendment is confined to the
    separately owned attention-stage body
- **Produces**: `I-020A ObservationProviderV2@1` — native events and exact host
  bindings to a bounded `AttentionRequestV2`, plus a bound continuation seam
  only where the host can fulfill it honestly; and one immutable observation-
  stage I-010E record containing only facts this slice can attest.
- **Integration handoff**: `v2-observation-owner` lands the shared provider and
  reference replay/comparison assets, then hands the exact commit, capability
  requirements, commands, evidence, and limitations to every named downstream
  owner and `v2-integrator`. Slices 050 and 060–090 own native transport and
  surface bindings; slice 030 alone owns classifier-safe projection/redaction
  in `src/nunchi/core.py`; slice 040 owns only the common participant-turn host.

## User Scenarios & Testing

### User Story 1 - Preserve Native Facts and Exact Self (Priority: P1)

An adapter or harness can convert a native message, reaction, or membership
event into stable actors and literal relations while keeping exact current-
surface self binding separate from names and aliases.

**Why this priority**: Lossy identity and prose-flattened relations were direct
inputs to false suppression and cross-surface drift.

**Independent Test**: Replay equivalent transport-neutral native-fact fixtures
through the shared provider and compare actors, events, relations, trigger,
transport action, and unknown facts without invoking the attention model.

**Acceptance Scenarios**:

1. **Given** a display-name or alias collision with another actor, **When** the
   event is normalized, **Then** only the transport-attested actor ID establishes
   self authorship.
2. **Given** actor-targeted structured mentions, a room-wide mention, reply/
   thread parents, reactions, or native membership changes, **When** the
   platform exposes them, **Then** actor mention targets and room-wide mention
   status remain distinct literal facts rather than synthetic prose or social
   conclusions.
3. **Given** a platform that cannot expose a fact, **When** normalization runs,
   **Then** the capability remains unavailable or unknown rather than inferred.

---

### User Story 2 - Build a Bounded, Expandable Observation (Priority: P1)

A host can assemble a compact factual snapshot around the trigger under hard
event and byte caps, preserve exact relation closure where it fits, state every
known omission, and expose bounded continuation when available.

**Why this priority**: A fixed latest-N window loses structure, while full
history creates the context bomb the selected design rejects.

**Independent Test**: Run one recorded room through multiple event/byte/age
budgets and continuation queries, then assert authoritative order, hard limits,
trigger inclusion, relation/gap truth, exact deduplication, and bound fetches.

**Acceptance Scenarios**:

1. **Given** a relation target and nearby events that fit within hard caps,
   **When** the snapshot is assembled, **Then** trigger and exact relation
   closure are included before remaining nearby context.
2. **Given** a required relation target that cannot fit, **When** assembly
   completes, **Then** its literal reference remains, gap/truncation coverage is
   honest, and continuation can fetch around it only if supported.
3. **Given** a bound continuation, **When** the participant fetches before,
   after, or around an observed event, **Then** the returned page respects
   participant/room/scope/trigger binding, event and byte caps, authoritative
   order, and exact-event deduplication.

---

### User Story 3 - Supply Recoverability and Comparison Reference Scenes (Priority: P2)

Downstream transport and surface owners receive reusable scenes that state what
an observation implementation must retain, backfill, expose, and compare
without requiring an invented roster or social memory.

**Why this priority**: Governed suppression is legitimate only where later
hearing is recoverable, and local adapter success is insufficient for parity.

**Independent Test**: Run reference provider variants with restart-safe,
session-only, unavailable-event, and continuation capability declarations
through the shared replay/comparison tools and prove the expected observation
and limitation outcomes.

**Acceptance Scenarios**:

1. **Given** an event later tagged as hypothetically suppressed, **When** a
   subsequent event is assembled within the declared retention horizon, **Then**
   the earlier event remains available by ordinary snapshot or targeted fetch
   without special outcome-derived retention.
2. **Given** a provider claiming restart safety, **When** the reference
   restart/backfill scene is applied by a downstream owner, **Then** retained
   event content and actor identity must remain available; otherwise the claim
   fails and coverage must report session-only or a restart gap.
3. **Given** reference providers with equivalent native facts, budgets, and
   capability declarations, **When** the shared comparator runs, **Then** their
   normalized observations are equivalent except for explicitly unavailable
   capabilities; this result establishes the reusable comparison contract, not
   parity for an untested real surface.

### Edge Cases

- Exact duplicate delivery versus two distinct native events with identical
  content; exact self events are retained but do not wake their author.
- Authorized native events followed by normalization/schema failure must become
  operational error downstream, not an observation-level social suppression.
- A trigger delayed in a host queue may have already-observed later events;
  collectors never wait for hypothetical future speech.
- Relation closure cannot bypass hard event or byte caps; timestamps cannot
  reorder authoritative native sequence.
- Unknown history depth, live-only reactions, unresolved authors, expired
  continuation, cursor replay, restart gaps, and native history pagination.
- Suppressed and self-authored events follow the same bounded retention policy
  as every other observation; no result-specific queue or ledger is allowed.

## Requirements

### Functional Requirements

- **FR-001**: The slice MUST implement `I-020A ObservationProviderV2@1` against
  the exact 010 interface versions and MUST NOT alter shared contracts without
  an explicit contract-owner handoff.
- **FR-002**: Every provider MUST bind `self.actor_id` from a transport- or
  installation-attested identity and MUST NOT infer self from names, aliases,
  role, or message text.
- **FR-003**: Providers MUST normalize stable actors and ordered native message,
  reaction, and membership events with literal relations when available;
  actor-targeted mention IDs and room-wide mention status MUST remain distinct,
  and unavailable facts MUST be represented honestly.
- **FR-004**: Deterministic transport hygiene MUST be limited to exact delivery
  deduplication, retain-but-no-wake exact self events, and a transport-attested
  `unroutable` disposition proving that no authorized and routable native event
  can be constructed. The shared provider MAY compare exact delivery IDs and
  exact actor IDs, but MUST NOT independently decide transport authorization or
  routability. Exact self authorship/causation means `author_id == self.actor_id`
  for authored message/reaction events or `caused_by_actor_id == self.actor_id`
  for membership events. A membership event where self appears only as
  `subject_actor_id` remains `OBSERVED`: being acted upon is not self-causation.
- **FR-005**: No provider or buffer may interpret mentions, replies, apparent
  resolution, relevance, class address, turn ownership, or any conversational
  meaning as a deterministic suppression reason.
- **FR-006**: Snapshot assembly MUST include the trigger, then exact relation
  closure that fits, then nearby events, under independently configurable hard
  event, byte, and optional age limits while preserving authoritative order.
- **FR-007**: Coverage MUST report configured limits, known pre/post-trigger
  omission, gaps, truncation causes, continuity, restart gaps, and event-kind
  visibility without upgrading unknown facts.
- **FR-008**: A continuation provider MUST be optional, opaque to room data,
  bound to participant/room/continuity scope/trigger, capped by request and
  operator policy, and capable only of truthful before/after/around queries.
- **FR-009**: Returned pages MUST preserve authoritative order, merge actors by
  exact ID, deduplicate events only by continuity scope and event ID, and
  recalculate coverage for each page.
- **FR-010**: Observation retention MUST be bounded and outcome-neutral;
  previous attention results MUST NOT create special retention, handled/open
  state, a participant roster, response debt, or a speaker queue.
- **FR-011**: The slice MUST provide a reusable restart/recoverability scene and
  acceptance rule; each downstream surface must pass it before claiming social-
  suppression eligibility and must otherwise report its limitation.
- **FR-012**: The slice MUST provide reference provider variants and a reusable
  comparator proving that equivalent facts, budgets, and capability declarations
  normalize equivalently, with differences permitted only for honestly
  unavailable native facts. Slices 050 and 060–090 MUST apply that comparator to
  their real bindings; slice 110 alone owns the final cross-surface parity claim.
- **FR-013**: The owner MUST provide deterministic tests, replay corpora,
  serialized-byte measurements, separately labelled token-size proxy evidence,
  reference recoverability evidence, capability comparison rules, and complete
  downstream handoffs in ordinary paths. The slice-owned proxy is
  `utf8-bytes-ceil-div4@1`: `(serialized_utf8_bytes + 3) // 4`, recorded with
  `estimator_id`, `estimated_tokens`, `serialized_bytes`, and `model_id: null`.
  It is not represented as a provider/model tokenizer result. A downstream
  model-specific estimate MUST name its model, tokenizer, and versions.
- **FR-014**: No product code, test, corpus, fixture, evidence, runtime asset, or
  product documentation may be created in this SpecKit slice.
- **FR-015**: The provider MUST emit one immutable observation-stage I-010E
  record correlated by request ID. It MAY attest snapshot/coverage facts,
  configured and delivered budgets, event IDs, and bytes exactly as allowed by
  the accepted closed schema. It MUST NOT add estimated-token or other
  slice-local fields to I-010E; token-size proxy results live only in separate
  observation evidence. It MUST leave later attention, participant, and
  transport facts unknown and MUST NOT mutate or complete another owner's
  receipt stage. This accepted-contract limitation is recorded for
  `v2-contract-owner` and `v2-integrator`; slice 020 does not alter I-010E.

### Key Entities

- **Native Event Input**: Transport-attested input carrying a stable delivery
  identity, native sequence, exact self binding, and an explicit mechanical
  disposition of `candidate-event` or `unroutable`. `candidate-event` requires
  the native event plus the transport's authorization/routing provenance;
  `unroutable` requires the transport-owned proof and carries no candidate
  social event. The shared provider consumes these facts and never derives
  authorization or routing from payload prose.
- **Observation Buffer**: Bounded, outcome-neutral event continuity within one
  room scope; never social state.
- **Observation Provider**: Normalizes native facts and assembles
  `AttentionRequestV2` under explicit budgets.
- **Continuation Provider**: Host-owned, bound, bounded access to already
  observed or natively retrievable context.
- **Surface Capability Record**: Honest event visibility, continuity, backfill,
  and expansion support used for parity and suppression eligibility.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every exact-self collision variant in the shared/reference fixture
  matrix preserves the attested actor binding, with zero alias-derived
  authorship; real-surface conformance remains a downstream acceptance result.
- **SC-002**: Every budget fixture stays within configured event and serialized
  byte caps while retaining the trigger and reporting every omitted relation or
  truncation cause honestly.
- **SC-003**: Before/after/around fetch tests reject 100% of cross-binding,
  over-limit, expired-handle, and invalid-cursor cases.
- **SC-004**: Duplicate/self/unroutable transport scenes make no social model
  call, while every valid native event that later fails normalization is
  recorded as operational error rather than social suppression.
- **SC-005**: The reference recoverability matrix distinguishes restart-safe,
  session-only, unknown, and known-gap outcomes with zero ambiguous eligibility
  results; downstream live proof remains owned by the relevant surface slices.
- **SC-006**: The reference comparator reports zero unexplained differences
  between reference provider variants under equivalent fact, capability, and
  budget inputs; no real surface is called equivalent from this evidence alone.
- **SC-007**: The owner handoff identifies the exact I-020A version, shared and
  reference modules, comparison contract, commands, evidence, downstream proof
  obligations, and known limitations with no file-ownership ambiguity for
  slice 040 or any real-surface owner.
- **SC-008**: Governance validation finds zero product artifacts under this
  slice directory.

## Assumptions

- Slice 010 lands all consumed `@1` contracts before this slice may enter
  `READY`.
- Existing transports continue to be the source of authentication and routing
  truth; observation code does not become a transport or provider registry.
- Default eager/retention budgets are selected by replay evidence during
  authorized slice implementation, not guessed in this planning artifact.
- A surface may legitimately lack reactions, membership history, backfill, or
  continuation; parity requires honest representation, not fabrication.
- Reference provider results establish reusable mechanics only. They never
  substitute for installed-runtime evidence from a native surface binding.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` exact identity, native-relation,
  budget/gap, and continuation claim deltas to `v2-integrator` for atomic
  current-state wording.
- **Affected ordinary docs**: `UPDATE` `docs/observation/v2.md`. `HANDOFF` exact
  request, identity, native-relation, order, budget, gap, and continuation
  deltas for `CHANGELOG.md`, `docs/STABILITY.md`, `docs/integration.md`, `docs/adapters.md`, and
  `docs/architecture/v2-selected-design.md` to accepting `v2-integrator`.
  `NO_IMPACT` `docs/contracts/nunchi-v2.md`: it remains the accepted 010-owned
  contract description; slice 020 consumes I-010A/I-010D/I-010E without editing
  their closed shapes and validates that rationale before handoff.
  `HANDOFF` the same interface-specific delta for
  `integrations/mcp-discord/README.md` and
  `integrations/mcp-discord/DESIGN.md` to accepting `v2-transport-owner`,
  `integrations/hermes/README.md` to accepting `v2-hermes-owner`,
  `integrations/claude-code/README.md` to accepting `v2-claude-owner`, and
  `integrations/codex/README.md` to accepting `v2-codex-owner`.
- **Handoff evidence**: `evidence/v2/observation/handoff.md` records reviewed
  paths, dispositions, exact delta, validation, and reviewer.

## Explicit Exclusions

- No V2 product behavior is implemented by this planning baseline.
- No attention-model prompt, provider call, disposition transition, participant
  invocation, reply composition, send-time safety, or release decision.
- No complete participant roster, handled/open ledger, obligation queue,
  speaker allocation, or outcome-derived retention.
- No edits to 010-owned schemas; contract change requests return to
  `v2-contract-owner`.
- No classifier-safe projection/redaction implementation or tests; slice 030
  owns that behavior in `src/nunchi/core.py`. Slice 020 emits the accepted
  I-010A continuation capability and hands the projection obligation to 030.
- Native transport and harness bindings belong to slices 050 and 060–090;
  shared participant-turn hosting belongs to 040; final parity and cutover
  belong only to `110`/`v2-integrator`.
- No real-surface conformance, restart-safety, suppression-eligibility, or parity
  claim is completed by this slice's reference provider evidence.
