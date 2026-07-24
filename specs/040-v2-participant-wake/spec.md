# Existing Slice Specification: V2 Participant Wake

> **Reference only.** Product requirements and interfaces remain useful.
> Historical workflow and lifecycle instructions are retired. Follow
> `docs/v2-delivery.md`.

**Feature Branch**: `v2/participant-wake`

**Created**: 2026-07-11

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/participant/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/participant/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/participant/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/participant/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Input**: Provide one shared participant-turn host that converts V2 attention routing into a compact normal act-or-silence turn with bound context expansion, no intermediate admission answer, and no send-time social reclassification.

**Authority source**: repository-owned `docs/architecture/v2-selected-design.md`
and `docs/contracts/nunchi-v2.md`; Aleph Vault `bdd1ebb`/`c834e8c` are provenance

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-wake-owner`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-wake-owner-2026-07-23.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/040-v2-participant-wake`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/040-v2-participant-wake`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`

**Dependency commits / acceptance references**: at readiness,
`slice-activation.md` MUST record `Accepted dependencies` in the declared order,
ordered `Dependency commits` as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Feeds**: `060`, `070`, `080`, `090`, `100`, `110`

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
- Authorized slice implementation targets shared participant-host code at
  `src/nunchi/participant.py`; deterministic tests target
  `tests/v2/participant/`, replay assets `evals/v2/participant/`, evidence
  `evidence/v2/participant/`, and product documentation `docs/participant/`.
- This planning baseline creates no participant host, prompt/instruction,
  context tool, send seam, harness binding, test, corpus, evidence, product
  documentation, or V2 runtime behavior.
- The repository remains V1 until slice 110 assembles every accepted owner
  handoff into one atomic V2 cutover.

## Interface Summary

- **Consumes**:
  - `I-010B AttentionDecisionV2@1`
  - `I-010C ParticipantWakeV2@1`
  - `I-010D ContextContinuationV2@1`
  - `I-010E AttentionReceiptV2@1`
  - `I-020A ObservationProviderV2@1`
  - `I-030A AttentionEngineV2@1`
- **Produces**: `I-040A ParticipantTurnHostV2@1` — wake packet plus truthful
  context expansion and one direct act-or-silence participant turn, with no
  intermediate admission response and no send-time social reclassification;
  it also emits its own immutable participant-host I-010E stage.
- **Integration handoff**: `v2-wake-owner` hands the exact commit, I-040A
  version, upstream interface pins, deterministic commands, replay evidence,
  participant instruction, context/send capability seams, and limitations to
  owners of slices 060–100 and `v2-integrator`. Those later slices bind actual
  harnesses; slice 110 alone owns parity assembly and cutover.

## User Scenarios & Testing

### User Story 1 - Route One Decision Into One Normal Turn (Priority: P1)

A harness-neutral host can obey one validated attention decision: `SUPPRESS`
stops the wake, while `WAKE`, `DEFER`, trusted preattention `BYPASS`, and default
operational-error fallback invoke the participant with one compact factual
I-010C packet.

**Why this priority**: The attention/contribution split fails if a host asks the
same social admission question again or disguises an error as a social result.

**Independent Test**: Inject each valid I-010B branch and a fake participant
callback, then assert invocation count, wake source, packet facts, outcome, and
receipt without any live adapter or model.

**Acceptance Scenarios**:

1. **Given** effective `SUPPRESS`, **When** the host routes the decision,
   **Then** the participant is not invoked and the result is recorded as model
   suppression rather than participant silence.
2. **Given** effective `WAKE` or `DEFER`, **When** the host routes the decision,
   **Then** exactly one participant turn receives the compact facts and the
   correct attention source.
3. **Given** operational `ERROR` with the shared default, **When** routing
   occurs, **Then** exactly one participant turn receives source
   `ERROR_FALLBACK`; error detail remains off the room surface.
4. **Given** `status: bypass` caused by trusted `preattention-disabled`
   configuration, **When** routing occurs, **Then** exactly one participant
   turn receives source `PREATTENTION_BYPASS` without a fabricated classifier
   or effective disposition.

---

### User Story 2 - Contribute Directly or End Without Sending (Priority: P1)

The woken participant responds to the room through its ordinary message,
reaction, or tool path when it has something to contribute, or ends the same
turn without a room send.

**Why this priority**: A meta-answer such as “yes, I want to contribute” wastes
the wake, while a second social send gate can silence a valid contribution.

**Independent Test**: Run fake participants that send a substantive message,
send a lightweight reaction, send a tool action, emit an admission meta-answer,
or end silently. Assert the host accepts structurally valid actions and silence,
while the acceptance evaluator flags the meta-answer as a failed participant
scene without adding a runtime semantic send gate.

**Acceptance Scenarios**:

1. **Given** a WAKE packet, **When** the participant chooses to contribute,
   **Then** the same turn emits the actual room action rather than an admission
   decision or drafted placeholder.
2. **Given** WAKE, DEFER, preattention bypass, or error fallback, **When** the
   participant has nothing useful to add, **Then** it can end without sending
   and the participant-host stage records silence, not suppression.
3. **Given** optional classifier advice containing instruction-like text,
   **When** the participant turn begins, **Then** advice remains untrusted data
   and cannot override the host instruction or require a response.

---

### User Story 3 - Expand Facts and Send Without Re-Judging the Room (Priority: P2)

During the normal turn, the participant can fetch bounded earlier/later/around
context where I-020A supports it, then send through deterministic operational
safety without another attention classifier or per-trigger social permit.

**Why this priority**: Compact context must remain useful without becoming a
context bomb, and the retired second-judgment failure must not return at send.

**Independent Test**: Exercise bound continuation and a recording send seam
with fake participants, then prove exact fetch binding/limits, delivered event
IDs, one attention judgment, zero send-time social calls, and separate host and
participant outcomes.

**Acceptance Scenarios**:

1. **Given** an omitted relation target and a valid continuation, **When** the
   participant fetches around that event, **Then** the host exposes the bounded
   page as additional facts without starting a new attention judgment.
2. **Given** a participant action after expansion, **When** the action reaches
   the send seam, **Then** only deterministic operational safety may run; no
   room classifier or social permission registry is consulted.
3. **Given** a harness that lacks context expansion or a send backstop, **When**
   capability is reported, **Then** it remains explicitly unavailable rather
   than simulated or claimed present.

### Edge Cases

- Illegal classifier/effective pairs, malformed wake packets, trigger absent
  from events, advice/evidence mismatch, and an observation provider failure
  between decision and participant invocation.
- Explicit operator `NO_WAKE` error override remains operational policy and
  cannot be reported as SUPPRESS or participant silence.
- Participant callback crashes, times out, returns malformed output, tries to
  echo an admission answer, sends multiple conflicting actions, or ends without
  an observable completion status.
- Continuation is absent, expired, cross-bound, over budget, cursor-invalid, or
  returns events already in the wake packet.
- A harness may deduplicate rendering against native participant context only
  if the receipt still names the facts actually available; an opaque reference
  cannot replace a materialized compact packet.
- A reaction or acknowledgment is a valid contribution class; participant
  silence after any waking source is also valid.

## Requirements

### Functional Requirements

- **FR-001**: The slice MUST implement `I-040A ParticipantTurnHostV2@1` against
  the accepted I-010B/C/D/E, I-020A, and I-030A versions without redefining any
  upstream interface.
- **FR-002**: Effective `SUPPRESS` MUST stop participant invocation; effective
  `WAKE` and `DEFER`, plus trusted I-010B `status: bypass`, MUST invoke exactly
  one normal participant turn. Bypass MUST carry source
  `PREATTENTION_BYPASS`, no classifier/effective disposition, and zero claim
  that an attention model ran.
- **FR-003**: Operational `ERROR` MUST remain separate and MUST invoke the
  participant by shared default with attention source `ERROR_FALLBACK`; any
  trusted operator `NO_WAKE` override MUST be separately sourced and receipted.
- **FR-004**: The participant turn MUST receive a materialized compact I-010C
  packet containing self, room, actors, ordered events, trigger, honest
  coverage, optional continuation, and attention source.
- **FR-005**: Participant packet event and byte budgets MUST be independent of
  attention-request budgets; trigger and fitting relation/evidence closure MUST
  survive truncation, and delivered event IDs/bytes/tokens MUST be receipted.
- **FR-006**: Attention advice MUST remain optional, non-authoritative,
  evidence-grounded classifier data; room events and advice MUST NOT gain host
  instruction authority or contain a composed reply.
- **FR-007**: The portable participant instruction MUST ask for a direct natural
  room contribution or silent end, not an intermediate yes/no or explanation of
  whether the participant wants to contribute.
- **FR-008**: One participant inference MUST emit the actual message, reaction,
  tool action, or no-send outcome. Acceptance evaluation MUST treat an
  admission meta-answer as a failed participant-turn scene, but the runtime host
  MUST NOT add a semantic classifier that blocks or reclassifies participant
  output.
- **FR-009**: WAKE, DEFER, PREATTENTION_BYPASS, and ERROR_FALLBACK followed by
  participant silence MUST all be valid and MUST remain distinct from model
  suppression.
- **FR-010**: Bound context expansion MUST use I-010D through I-020A, preserve
  binding/caps/order/exact deduplication/coverage, and MUST NOT invoke a second
  Nunchi attention judgment.
- **FR-011**: The send seam MUST perform no social reclassification and require
  no per-trigger social permission state; optional deterministic send safety
  MUST remain operational, capability-explicit, and separately receipted.
- **FR-012**: The host MUST emit one immutable participant-host I-010E stage
  correlated by request ID, containing wake source, delivered packet facts,
  expansion calls, participant invoked/not invoked, participant action/silence/
  unknown, host-side send-safety result, and host errors. It MUST reference but
  never rewrite observation or attention stages; transport delivery remains a
  later owner's separate stage.
- **FR-013**: The host MUST be harness-neutral and expose callback/capability
  seams that slices 060–090 can bind without changing the shared lifecycle.
- **FR-014**: Deterministic tests and replay scenes MUST cover suppression,
  WAKE action, preattention bypass, lightweight action, all valid silence
  sources, ERROR fallback, context expansion, meta-answer failure, immutable
  stage ownership, and absence of send reclassification.
- **FR-015**: The owner MUST hand off exact commit, I-040A/upstream versions,
  commands/results, participant instruction, capability seams, evidence, and
  limitations to slices 060–100 and `v2-integrator`.
- **FR-016**: No product implementation, schema, test, corpus, evidence,
  runtime asset, or product documentation may be created under this SpecKit
  slice.

### Key Entities

- **Participant Turn Host**: Routes one attention result, invokes at most one
  normal participant turn, exposes optional expansion, and records outcome.
- **Participant Callback**: Harness-owned inference/action seam that produces an
  actual room action or no-send, never a second admission verdict.
- **Context Expansion Capability**: Optional bound access to I-020A through
  I-010D during the participant turn.
- **Operational Send Capability**: Optional deterministic safety seam that does
  not interpret conversation or grant social permission.
- **Participant Outcome**: Sent action, silent end, contract failure, or unknown
  host outcome, distinct from attention and routing.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Routing fixtures invoke the participant zero times for effective
  SUPPRESS and exactly once for WAKE, DEFER, PREATTENTION_BYPASS, and default
  ERROR fallback; bypass makes zero attention-model calls.
- **SC-002**: Every produced wake packet validates as I-010C, stays within its
  independent event/byte budget, includes the trigger, and receipts all facts
  actually made available.
- **SC-003**: Message, reaction, tool-action, and no-send reference participants
  produce the expected distinct outcome, while 100% of admission meta-answers
  fail the acceptance scene without a second runtime social judgment.
- **SC-004**: Continuation tests reject all cross-binding, expired, over-limit,
  and invalid-cursor requests and add zero second attention judgments.
- **SC-005**: Static and dynamic call-count checks find zero social classifier
  calls and zero social permission-registry lookups on the send path.
- **SC-006**: WAKE+silence, DEFER+silence, PREATTENTION_BYPASS+silence, and
  ERROR_FALLBACK+silence remain valid, separately staged outcomes in
  deterministic and replay results.
- **SC-007**: Every downstream surface owner can bind the shared host using the
  documented callbacks/capabilities without changing I-040A lifecycle
  semantics; final parity proof remains owned by 110.
- **SC-008**: The handoff packet and security-assurance feed contain exact
  versions, commands, evidence, instruction/capability details, and limitations
  with no unresolved ownership ambiguity.
- **SC-009**: Governance validation finds zero product artifacts under this
  slice directory.

## Assumptions

- Slices 010, 020, and 030 land accepted handoffs before implementation begins.
- The shared host can use a callable participant callback without depending on
  one agent framework; surface slices own runtime-specific adaptation.
- A participant outcome may be unknown on harnesses that cannot attest send or
  silence; the shared contract reports unknown rather than inventing success.
- Operational send backstop capability differs by harness and is not required
  to pretend universal parity.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` the exact direct act-or-silence,
  expansion, valid-silence, and no-send-reclassification claim delta to
  `v2-integrator`.
- **Affected ordinary docs**: `UPDATE` `docs/participant/v2.md`. `HANDOFF` exact
  wake-source, act-or-silence, expansion, receipt, and no-reclassification
  deltas for `CHANGELOG.md`, `docs/STABILITY.md`, `docs/integration.md`, `docs/adapters.md`,
  `docs/contracts/channel-adapter-v1.md`, and
  `docs/architecture/v2-selected-design.md` to accepting `v2-integrator`.
  `HANDOFF` surface-specific deltas for `integrations/mcp-discord/README.md` and
  `integrations/mcp-discord/DESIGN.md` to accepting `v2-transport-owner`,
  `integrations/hermes/README.md` to accepting `v2-hermes-owner`,
  `integrations/claude-code/README.md`,
  `integrations/claude-code/DEFER_EVAL.md`, and
  `integrations/claude-code/transport-patch/README.md` to accepting
  `v2-claude-owner`, and `integrations/codex/README.md` to accepting
  `v2-codex-owner`.
- **Handoff evidence**: `evidence/v2/participant/handoff.md` records reviewed
  paths, dispositions, exact delta, validation, and reviewer.

## Explicit Exclusions

- No V2 product behavior is implemented by this planning baseline.
- No native transport, platform observation binding, Hermes/Claude/Codex/
  standalone-adapter integration, installed-runtime probe, or live-room cutover.
- No attention-model or policy decision, schema change, reply composition,
  second social classifier, social permission registry, or handled/open ledger.
- No final parity claim: slice 100 owns blocking assurance and slice 110/
  `v2-integrator` alone owns cross-surface assembly and atomic cutover.
- No edits to upstream-owned contract, observation, or core interfaces; changes
  return to their named owners through explicit handoff.
