# Feature Specification: V2 Contract

**Feature Branch**: `v2/contract`

**Created**: 2026-07-11

**Status**: Planned for future Goal 2; no V2 implementation is authorized or present

**Input**: Define the atomic V2 request, decision, wake, continuation, and receipt contracts before any dependent implementation begins.

**Authority source**: Zoe-selected Aleph Vault design at `bdd1ebb`, contract-clarified in PR 68 at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-contract-owner`

**Depends on**: none

**Feeds**: `020`, `030`, `040`, `050`, `060`, `070`, `080`, `090`, `100`, `110`

## Control-Plane Boundary

- This directory contains planning artifacts only.
- Future Goal 2 product schemas belong under `schemas/v2/`, contract
  tests under `tests/v2/contract/`, evaluation material under `evals/v2/`,
  evidence under `evidence/v2/contract/`, and product contract documentation
  under `docs/contracts/`.
- Goal 1 does not create schemas, tests, evaluation assets, evidence, product
  documentation, or V2 runtime behavior.
- Until Zoe explicitly authorizes Goal 2, every task in this slice remains
  future work and the repository continues to implement V1.

## Interface Summary

- **Consumes**: the selected Aleph Vault V2 technical design; no upstream slice
  interface.
- **Produces**:
  - `I-010A AttentionRequestV2@1`
  - `I-010B AttentionDecisionV2@1`
  - `I-010C ParticipantWakeV2@1`
  - `I-010D ContextContinuationV2@1`
  - `I-010E AttentionReceiptV2@1`
- **Integration handoff**: `v2-contract-owner` lands and versions the ordinary
  schemas and their deterministic contract tests, then hands the exact commit,
  verification commands, interface inventory, and known limitations to all
  named downstream owners and `v2-integrator`. Dependent owners do not edit these
  contracts silently.

## User Scenarios & Testing

### User Story 1 - Exchange a Truthful Attention Request (Priority: P1)

A host can represent exact self binding, the room, observed and referenced
actors, an ordered factual event stream, one included trigger, honest coverage,
and optional bounded continuation without encoding a social conclusion.

**Why this priority**: Every observer and attention implementation depends on a
single unambiguous input contract; identity or event ambiguity recreates the
false-silence failure.

**Independent Test**: Validate representative requests and every invalid
identity, reference, order, coverage, budget, and prohibited-ledger case against
`I-010A`, without invoking a classifier or harness.

**Acceptance Scenarios**:

1. **Given** exact self binding and ordered native events with literal reply,
   actor-targeted mention, room-wide mention, reaction, and membership facts,
   **When** the request is validated, **Then** actor mention targets and
   `mentions_room` remain distinct and no alias proves authorship.
2. **Given** a trigger whose relation target is outside the bounded projection,
   **When** the request reports the unresolved relation and honest gap coverage,
   **Then** it remains valid without inventing the missing event.
3. **Given** a V1 envelope or a request containing `handled`, `open`, `owed`, or
   another social-ledger field, **When** it is validated as V2, **Then** it is
   rejected rather than translated.
4. **Given** a request with continuation capability, **When** the classifier
   projection is formed, **Then** it exposes coverage and expansion capability
   booleans but never the host-only handle, binding, cursor, or another opaque
   continuation secret.

---

### User Story 2 - Route an Auditable Attention Decision (Priority: P1)

A core or CLI consumer can distinguish model disposition, effective
disposition, uncertainty widening, a non-social preattention bypass, and
operational error without interpreting participant move labels or reply prose.

**Why this priority**: The clean cutover replaces the mixed V1 move vocabulary,
and suppression safety depends on a closed set of allowed transitions.

**Independent Test**: Validate every allowed and forbidden decision transition,
classifier audit shape, advice/evidence rule, legacy transition vector,
non-social bypass, and tagged operational error using the same corpus against
the portable schema and stdlib runtime validator.

**Acceptance Scenarios**:

1. **Given** classifier `SUPPRESS` with all required transition evidence,
   **When** the effective result remains `SUPPRESS`, **Then** the decision names
   the no-override route and contains no participant reply.
2. **Given** classifier `SUPPRESS` widened by the margin or delegation policy,
   **When** the response is validated, **Then** effective `DEFER` and its exact
   valve and override cause are preserved.
3. **Given** malformed output, an illegal disposition pairing, or an invalid
   legacy confidence vector, **When** validation runs, **Then** only the tagged
   `ERROR` branch is valid; no social suppression is fabricated.
4. **Given** trusted policy with preattention disabled, **When** the host-facing
   decision is formed, **Then** `status: bypass` with cause
   `preattention-disabled` is valid only without classifier/effective
   disposition, classifier audit, advice, reasons, or model evidence.

---

### User Story 3 - Hand a Normal Turn and Receipt Across Harnesses (Priority: P2)

A harness can receive one factual participant wake, optionally expand context
through a bound continuation, and record lifecycle telemetry without receiving
an admission meta-question or a social permission ledger.

**Why this priority**: Participant wake and receipt parity are the downstream
seams that prevent each harness from inventing its own lifecycle.

**Independent Test**: Validate wake packets, continuation requests/pages, and
receipts independently of any surface implementation, including valid silent
participant outcomes and binding failures.

**Acceptance Scenarios**:

1. **Given** effective `WAKE`, `DEFER`, error fallback, or preattention bypass,
   **When** a participant wake is formed, **Then** the source is explicit
   (`WAKE`, `DEFER`, `ERROR_FALLBACK`, or `PREATTENTION_BYPASS`) and facts remain
   separate from optional, evidence-grounded attention advice.
2. **Given** a continuation handle, **When** a fetch changes participant, room,
   continuity scope, or trigger binding, **Then** the request is rejected.
3. **Given** a participant that sends nothing after being woken, **When** the
   lifecycle receipts are appended, **Then** the immutable observation,
   attention, participant-host, and transport stage records remain correlated by
   request ID, and participant silence remains distinct from model suppression
   and host routing.

### Edge Cases

- Duplicate event IDs within one continuity scope; identical text with distinct
  native IDs; and timestamps that disagree with authoritative array order.
- Missing referenced actors, a trigger absent from `events`, unresolved
  relation targets, and transports that cannot know whether more events exist.
- Empty or non-positive budgets, out-of-range margins, non-finite confidence
  values, extra legacy confidence keys, expired continuation handles, and cursor
  reuse across bindings.
- Advice on `DEFER` or `SUPPRESS`, advice citing nonexistent events, and any
  reply-bearing or social-ledger field in a public contract.
- A bypass carrying classifier/effective disposition or advice; a
  `PREATTENTION_BYPASS` wake without a matching trusted bypass decision; or an
  attention receipt that fails to mark `classifier_not_invoked`.
- A continuation handle, binding, cursor, or opaque host secret appearing in the
  classifier projection even though expansion capability booleans may appear.
- A receipt writer mutating an earlier stage, filling a later owner's stage, or
  replacing unknown/unavailable with an invented outcome.
- Session-only continuity and unknown event visibility must remain explicit;
  neither is upgraded to restart-safe or unavailable by inference.

## Requirements

### Functional Requirements

- **FR-001**: The slice MUST define `I-010A AttentionRequestV2@1` as a
  versioned, closed contract containing exact self binding, room identity,
  observed/referenced actors, ordered factual events, one included trigger,
  honest coverage, and optional continuation.
- **FR-002**: Exact `self.actor_id` MUST be transport- or host-attested and
  separate from loose names, role, and description; loose descriptors MUST NOT
  establish authorship.
- **FR-003**: Event requirements MUST preserve authoritative array order,
  stable IDs, literal message/reply/thread/reaction/membership facts, distinct
  actor-targeted mention IDs and `mentions_room`, and explicitly unknown or
  unresolved platform facts.
- **FR-004**: Coverage and continuation requirements MUST bound event and byte
  access, expose truncation, gaps, visibility, and restart continuity honestly,
  and bind every fetch to participant, room, continuity scope, and trigger. The
  handle, binding, cursor, and opaque continuation metadata MUST be host-only;
  the classifier projection MAY receive coverage and expansion capability
  booleans but MUST NOT receive those host secrets.
- **FR-005**: The slice MUST define `I-010B AttentionDecisionV2@1` as a tagged
  host-facing union with `status: ok`, `status: bypass`, and `status: error`.
  The ok branch contains classifier/effective dispositions, grounded advice,
  evidence IDs, classifier audit, and routing audit; the bypass branch contains
  exactly cause `preattention-disabled` with no classifier or effective
  disposition; the error branch remains operational and separate.
- **FR-006**: Allowed successful disposition transitions MUST be limited to
  `SUPPRESS→SUPPRESS`, `SUPPRESS→DEFER`, `WAKE→WAKE`, and `DEFER→DEFER`; every
  other `status: ok` pairing MUST take the operational-error path. Bypass is not
  a successful disposition pairing and MUST NOT fabricate a model judgment.
- **FR-007**: While the protective transition margin is active, legacy verdict
  confidence evidence MUST contain exactly `PASS`, `ACK`, `ASK`, and `SPEAK`
  with finite values in `[0,1]`; malformed evidence MUST NOT support
  suppression.
- **FR-008**: The slice MUST define `I-010C ParticipantWakeV2@1` so facts,
  coverage, continuation, attention source, and optional advice remain
  separate, and no intermediate admission answer or composed reply is part of
  the contract. Its sources MUST include `WAKE`, `DEFER`, `ERROR_FALLBACK`, and
  non-social `PREATTENTION_BYPASS`; bypass carries no attention advice.
- **FR-009**: The slice MUST define `I-010D ContextContinuationV2@1` request and
  page shapes with bounded fetch, opaque cursor, authoritative order, exact
  merge identity, returned coverage, and binding validation. Handles, bindings,
  cursors, and fetch credentials remain host-only and are forbidden from the
  classifier projection.
- **FR-010**: The slice MUST define `I-010E AttentionReceiptV2@1` as immutable,
  append-only stage records for `observation`, `attention`, `participant-host`,
  and `transport`, correlated by request ID. Each owner appends only its own
  stage and MUST NOT mutate prior records or fill future stages. Unknown and
  unavailable remain explicit. The attention-stage record keeps classifier
  outcome, effective routing, policy provenance, and operational error separate;
  bypass records `classifier_not_invoked` and its trusted bypass provenance.
- **FR-011**: V2 contracts MUST reject V1 envelopes, reply-bearing fields,
  inferred-roster claims, and handled/open/owed/permission state; no V1
  translation bridge is permitted.
- **FR-012**: Every contract MUST have deterministic ordinary-path tests,
  acceptance scenes, evidence targets, version ownership, and a documented
  handoff; no product artifact may live in this slice directory. JSON Schema
  Draft 2020-12 is the portable test oracle through dev/test-only
  `jsonschema==4.26.0`; runtime validation remains explicit Python-stdlib code,
  and the same conformance corpus MUST exercise both validators.

### Key Entities

- **Self**: Stable participant identity plus one exact current-surface actor
  binding and optional loose descriptors.
- **Room and Actor**: The continuity scope and the observed/referenced cast,
  never an inferred full roster.
- **Event**: An ordered native factual observation with literal relations and
  no derived social status.
- **Coverage and Context Continuation**: Honest limits, omissions, visibility,
  continuity, and bounded expansion capability, with opaque fetch authority kept
  host-only.
- **Attention Decision**: Model proposal and effective route on `status: ok`, a
  non-social no-classifier `status: bypass`, or tagged operational error.
- **Participant Wake and Attention Receipt**: The normal-turn input and immutable
  correlated stage records, with observation, classifier/bypass, host,
  participant, and transport facts kept separate.

## Success Criteria

### Measurable Outcomes

- **SC-001**: One ordinary-path contract suite validates all five canonical
  interfaces and rejects 100% of enumerated invalid identity, reference,
  transition, bypass, confidence, host-secret leakage, binding, receipt-stage,
  reply-field, and social-ledger cases through both validators.
- **SC-002**: Every valid request fixture preserves the supplied event order and
  exact actor/event references byte-for-byte at the semantic field level.
- **SC-003**: Every `status: ok` decision fixture matches one of exactly four
  permitted classifier/effective pairs; every other ok pair validates only as
  operational error; and every bypass fixture has no classifier/effective
  disposition and cause exactly `preattention-disabled`.
- **SC-004**: Schema deletion or an incompatible interface edit causes a
  deterministic contract test failure before slices 020, 030, or 040 can
  integrate.
- **SC-005**: The owner handoff names all five interface versions, exact schema
  paths, validator versions and commands, scene-to-record manifest, receipt
  stage ownership, evidence references, and known limitations with no unresolved
  ownership ambiguity.
- **SC-006**: A repository-boundary check finds zero product schemas, tests,
  fixtures, evaluation assets, evidence, or product documentation under this
  SpecKit directory.

## Assumptions

- Goal 2 will retain Python 3.11+ and stdlib-only runtime constraints unless a
  separately authorized decision changes them.
- JSON Schema Draft 2020-12 is the portable machine-readable contract format
  planned for the ordinary `schemas/` path; generated language bindings are not
  required. `jsonschema==4.26.0` is test/dev-only and MUST NOT enter runtime
  dependencies; runtime validation remains explicit Python stdlib code.
- The uncertainty margin remains active at initial V2 cutover and is retired
  only by later evidence, not by this contract slice.
- Interface version `@1` is the first V2 execution version; breaking edits
  require an explicit owner handoff and dependent re-analysis.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` the exact accepted I-010A-E and
  breaking-cutover claim delta to `v2-integrator`; do not present partial V2 as
  current.
- **Affected ordinary docs**: `UPDATE` `docs/contracts/nunchi-v2.md`. `HANDOFF`
  exact supersession, interface-version, request/result, bypass, and ERROR
  deltas for `CHANGELOG.md`, `docs/STABILITY.md`, `docs/integration.md`,
  `docs/adapters.md`,
  `docs/contracts/channel-adapter-v1.md`, and
  `docs/architecture/v2-selected-design.md` to accepting
  `v2-integrator` for the atomic current-state update.
- **Handoff evidence**: `evidence/v2/contract/handoff.md` records both
  dispositions, exact reviewed paths, validation, reviewer, and accepted delta.

## Explicit Exclusions

- No V2 schema, test, evaluator, evidence, documentation, core, CLI, adapter,
  or harness implementation is created under Goal 1.
- No classifier prompt, social heuristic, context collector, provider call,
  participant invocation, transport integration, or deployment choreography.
- No V1 compatibility bridge and no decision about release numbering,
  promotion, or standalone-adapter release scope.
- Slices 020, 030, and 040 own their implementations and MUST request contract
  changes from `v2-contract-owner` rather than editing shared schemas directly.
