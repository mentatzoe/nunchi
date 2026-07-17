# Existing Slice Specification: V2 Contract

**Feature Branch**: `v2/contract`

**Created**: 2026-07-11

**Slice state**: `HANDOFF_READY`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/contract/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/contract/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/contract/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/contract/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Input**: Define the atomic V2 request, decision, wake, continuation, and receipt contracts before any dependent implementation begins.

**Authority source**: Zoe-selected Aleph Vault design at `bdd1ebb`, contract-clarified in PR 68 at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-contract-owner`

**Assigned participant / source**: cc-session-1 — evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/010-v2-contract`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: none

**Dependency commits / acceptance references**: activation evidence MUST use
`Accepted dependencies: none`, `Dependency commits: none`, and
`Dependency acceptance references: none`.

**Feeds**: `020`, `030`, `040`, `050`, `060`, `070`, `080`, `090`, `100`, `110`

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
- Authorized slice implementation places product schemas under `schemas/v2/`, contract
  tests under `tests/v2/contract/`, evaluation material under `evals/v2/`,
  evidence under `evidence/v2/contract/`, and product contract documentation
  under `docs/contracts/`.
- The rejection-R1 repair to the governance activation-path fixture in
  `tests/test_governance.py` is an in-scope ordinary rework output of this
  slice: it is repository test infrastructure at an ordinary path, named with
  its owning lane in plan §Ordinary Repository Targets and §Integration
  Strategy, and a reviewer applying this scope statement alone must classify
  that edit as in-scope for this slice's rework.
- This planning baseline creates no schemas, tests, evaluation assets,
  evidence, product documentation, or V2 runtime behavior.
- While the slice is `PLANNED`, every task remains `DORMANT` and the repository
  continues to implement V1.

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

## Clarifications

### Session 2026-07-17

- Q: Does `I-010B` require the legacy verdict confidence vector on every
  `status: ok` decision, or conditionally? → A: Per the selected design
  (`c834e8c`), the vector is optional on the ok branch and required exactly
  when the classifier disposition is `SUPPRESS` while the routing audit
  reports the margin `active`; this supersedes the earlier every-ok-decision
  requirement rejected in
  `evidence/v2/contract/review-2026-07-17-v2-integrator.md` (R2).
- Q: What must the `status: ok` routing audit contain? → A: The selected
  design's closed audit set — the applied valve (`none`, `classifier-defer`,
  `margin-defer`, or `policy-defer`), the override cause (`none`, `margin`,
  `suppression-disabled`, or `recoverability-unproven`), the margin status
  (`active` or `retired`), the effective margin when one applied, and the
  trusted margin source when present — plus `reasons` retained as ok-branch
  audit material that never enters the participant turn (a sibling ok-branch
  field, never a member of the routing-audit object) (R2).
- Q: Where is the receipt stage-to-writer binding enforced? → A: In the
  public per-record contract: each stage names its single directly observing
  owner as writer, a cross-owner record is invalid as a single document in
  both validators (schema-expressible), and the runtime stream-level
  ordering/immutability checks remain in addition (R3).

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
   disposition, classifier audit, reasons, evidence, legacy confidence
   vector, routing audit, or advice (the identical FR-005 exclusion set).

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
   separate from attention advice, which is present only on `WAKE`-source
   packets and always evidence-grounded (FR-013).
2. **Given** a continuation handle, **When** a fetch changes participant, room,
   continuity scope, or trigger binding, **Then** the request is rejected.
3. **Given** a participant that sends nothing after being woken, **When** the
   lifecycle receipts are appended, **Then** the immutable observation,
   attention, participant-host, and transport stage records remain correlated by
   request ID, and participant silence remains distinct from model suppression
   and host routing.

### Edge Cases

- Invalid (FR-003): duplicate event IDs within one request/continuity scope,
  and timestamps that disagree with authoritative array order. Valid but
  tricky: identical text with distinct native IDs. Non-finite confidence red
  cases use an encoded sentinel (string `"NaN"`/`"Infinity"`/`"-Infinity"` in the JSONL case
  envelope, decoded by the corpus loader) because strict JSON forbids
  non-finite literals.
- Missing referenced actors, a trigger absent from `events`, unresolved
  relation targets, and transports that cannot know whether more events exist.
- Empty or non-positive budgets, out-of-range margins, non-finite confidence
  values, extra legacy confidence keys, expired continuation handles, and cursor
  reuse across bindings.
- Invalid (FR-007): a candidate `SUPPRESS` whose routing audit reports the
  margin `active` but that carries no legacy confidence vector. Valid: a
  `WAKE` or `DEFER` decision without the optional vector; equally valid: a
  `WAKE`, `DEFER`, or margin-retired `SUPPRESS` decision carrying a
  well-formed vector — presence never invalidates an ok decision.
- Invalid (FR-013/FR-011): advice on `DEFER` or `SUPPRESS`, advice citing
  nonexistent events, and any reply-bearing or social-ledger field in a public
  contract.
- A bypass carrying any member of the identical FR-005 exclusion set —
  classifier/effective disposition, classifier audit, reasons, evidence,
  legacy confidence vector, routing audit, or advice; a
  `PREATTENTION_BYPASS` wake without a matching trusted bypass decision; or an
  attention receipt that fails to mark `classifier_not_invoked`.
- A continuation handle, binding, cursor, or opaque host secret appearing in the
  classifier projection even though expansion capability booleans may appear.
- A receipt writer mutating an earlier stage, filling a later owner's stage, or
  replacing unknown/unavailable with an invented outcome; a single receipt
  record attributing its stage to another stage's owner is invalid on its own
  (FR-010), not merely at stream level.
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
  stable IDs that are unique within one request and continuity scope
  (duplicate event IDs reject), literal
  message/reply/thread/reaction/membership facts, distinct actor-targeted
  mention IDs and `mentions_room`, and explicitly unknown or unresolved
  platform facts.
- **FR-004**: Coverage and continuation requirements MUST bound event and byte
  access, expose truncation, gaps, visibility, and restart continuity honestly,
  and bind every fetch to participant, room, continuity scope, and trigger. The
  handle, binding, cursor, expiry values, and opaque continuation metadata MUST be host-only;
  the classifier projection MAY receive coverage and expansion capability
  booleans but MUST NOT receive those host secrets.
- **FR-005**: The slice MUST define `I-010B AttentionDecisionV2@1` as a tagged
  host-facing union with `status: ok`, `status: bypass`, and `status: error`.
  The ok branch contains classifier/effective dispositions, `WAKE`-only grounded advice (FR-013),
  reasons retained as audit material that never enters the participant turn,
  evidence IDs, classifier audit, optional legacy verdict confidence evidence
  (FR-007), and a closed routing audit recording the applied valve (`none`,
  `classifier-defer`, `margin-defer`, or `policy-defer`), the override cause
  (`none`, `margin`, `suppression-disabled`, or `recoverability-unproven`),
  the margin status (`active` or `retired`), the effective margin when one
  applied, and the trusted margin source when present. `reasons` is a
  required sibling ok-branch field — an array of audit strings, possibly
  empty — and never a member of the routing-audit object. The routing
  audit's conditional facts are closed per combination, not only per field:
  a margin counts as **applied** exactly when the applied valve is
  `margin-defer`, and exactly then the effective margin (a finite number in
  `(0, 1]`) MUST be present and is forbidden on every other valve; the
  trusted margin source counts as **present** only on a margin-applied
  decision whose margin width was supplied by a trusted source, so
  `margin_source` MAY appear only when the valve is `margin-defer` (optional
  there, because a margin may apply from local configuration without a
  trusted source) and is forbidden on every other valve. Valve and override
  cause pair exactly: valves `none` and `classifier-defer` require override
  cause `none`; valve `margin-defer` requires override cause `margin` and
  margin status `active` (a retired margin cannot apply); valve
  `policy-defer` requires override cause `suppression-disabled` or
  `recoverability-unproven`. The margin status is recorded on every ok
  decision. The bypass branch
  contains exactly cause `preattention-disabled` with no classifier or
  effective disposition, classifier audit, reasons, evidence, legacy
  confidence vector, routing audit, or advice; the error branch remains
  operational and separate.
- **FR-006**: Allowed successful disposition transitions MUST be limited to
  `SUPPRESS→SUPPRESS`, `SUPPRESS→DEFER`, `WAKE→WAKE`, and `DEFER→DEFER`; every
  other `status: ok` pairing MUST take the operational-error path. The four
  permitted pairs map onto the applied valve exactly: `WAKE→WAKE` and
  `SUPPRESS→SUPPRESS` carry valve `none` (no widening valve applied; the
  classifier disposition stands), `DEFER→DEFER` carries valve
  `classifier-defer`, and `SUPPRESS→DEFER` carries valve `margin-defer` or
  `policy-defer`. Valve `none` therefore never co-occurs with a widened
  disposition: effective `DEFER` requires valve `classifier-defer`,
  `margin-defer`, or `policy-defer`. Bypass is not
  a successful disposition pairing and MUST NOT fabricate a model judgment.
- **FR-007**: Legacy verdict confidence evidence is optional on a
  `status: ok` decision and MUST be required exactly when the classifier
  disposition is `SUPPRESS` while the routing audit reports the margin
  `active`; a candidate suppression without that valid vector MUST NOT
  validate. The permissive side is symmetric and decidable: a well-formed
  vector MAY accompany any `status: ok` decision — `WAKE`, `DEFER`, or a
  margin-retired `SUPPRESS` — and its presence never invalidates the
  decision. When present the vector MUST contain exactly `PASS`, `ACK`,
  `ASK`, and `SPEAK` with finite values in `[0,1]`; malformed evidence MUST
  take the operational-error path and MUST NOT support suppression. The
  optional field, its exact four-key shape, and this conditional requirement
  are fixed for the `@1` major version: margin retirement flips only the
  reported margin status under later evidence per Constitution V and is not a
  schema edit, while removing or reshaping the field is a breaking `@2` edit.
- **FR-008**: The slice MUST define `I-010C ParticipantWakeV2@1` so facts,
  coverage, continuation, attention source, and optional advice remain
  separate, and no intermediate admission answer or composed reply is part of
  the contract. Its sources MUST include `WAKE`, `DEFER`, `ERROR_FALLBACK`, and
  non-social `PREATTENTION_BYPASS`; advice appears only on `WAKE`-source
  packets (FR-013), so bypass, `DEFER`, and `ERROR_FALLBACK` wakes carry none.
- **FR-009**: The slice MUST define `I-010D ContextContinuationV2@1` request and
  page shapes with bounded fetch, opaque cursor, authoritative order, exact
  merge identity, returned coverage, and binding validation; a continuation
  page whose event IDs collide with the originating request rejects at fetch
  time under the exact merge-identity rule. Handles, bindings,
  cursors, expiry values, and fetch credentials remain host-only and are
  forbidden from the classifier projection; an expired handle is rejected at
  fetch time as a binding-validation failure.
- **FR-010**: The slice MUST define `I-010E AttentionReceiptV2@1` as immutable,
  append-only stage records for `observation`, `attention`, `participant-host`,
  and `transport`, correlated by request ID, in that canonical order
  (observation → attention → participant-host → transport). A prefix-partial
  receipt — for example one awaiting its transport stage, or an S07 silence
  outcome ending at participant-host — is valid-in-progress. Each owner
  appends only its own stage and MUST NOT mutate prior records or fill future
  stages. The stage-to-writer binding is part of the public per-record
  contract, and its closed map is written here: the single directly
  observing owner for each stage is `observation` → `observation-provider`,
  `attention` → `attention-engine`, `participant-host` → `participant-host`,
  and `transport` → `transport`; that four-entry writer vocabulary is
  closed. A record attributing one stage to another stage's owner is
  invalid as a single document in both validators, independent of the
  runtime stream-level ordering and immutability checks. Unknown and
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
  and the same conformance corpus MUST exercise both validators. The corpus is
  partitioned by expressiveness: schema-expressible cases carry identical
  expected results for both validators; semantic and relational cases —
  cross-item ID uniqueness, timestamp-versus-order agreement, cross-document
  advice citations, trigger membership, fetch-time binding/expiry state, and
  receipt-stage sequence rules — are runtime-adapter-only. The oracle
  treatment is fixed per class: document-shaped relational cases (cross-item
  ID uniqueness, timestamp-versus-order agreement, cross-document advice
  citations, trigger membership) are oracle-expected-valid, because each
  document is schema-valid in isolation; behavioral and sequence classes
  (fetch-time binding/expiry state, receipt-stage sequence rules) are
  oracle-class-skipped, because there is no single document to validate.
  Per-class case counts MUST be asserted loudly so neither partition can
  silently shrink.
- **FR-013**: Advice validity follows the attention engine's contract (030
  FR-005: `SUPPRESS` and `DEFER` carry no participant advice). On the `I-010B`
  ok branch, `advice` MUST be present only when the classifier disposition is
  `WAKE`, and every advice evidence citation MUST reference an event ID
  supplied in the request; citations of nonexistent events are invalid. On
  `I-010C`, `advice` MUST be present only when `source` is `WAKE`; `DEFER`,
  `ERROR_FALLBACK`, and `PREATTENTION_BYPASS` wakes are advice-free because no
  classifier advice exists for those sources.

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
  reply-field, and social-ledger cases — schema-expressible cases through both
  validators with identical expected results, semantic/relational cases through
  the stdlib runtime adapter (FR-012 partition), with per-class counts
  asserted.
- **SC-002**: Every valid request fixture preserves the supplied event order and
  exact actor/event references at the semantic field level: parsed field
  values compare equal — strings as exact strings, numbers by exact decimal
  token (so `1` and `1.0` are distinct) — and event-array order is preserved;
  raw-byte serialization (key order, whitespace, unicode escapes) is out of
  scope.
- **SC-003**: Every `status: ok` decision fixture matches one of exactly four
  permitted classifier/effective pairs; every other ok pair validates only as
  operational error; and every bypass fixture has no classifier/effective
  disposition and cause exactly `preattention-disabled`.
- **SC-004**: Schema deletion or an incompatible interface edit causes a
  deterministic contract test failure before slices 020, 030, or 040 can
  integrate.
- **SC-005**: The owner handoff distinguishes and names two commits as
  distinct terms: the **candidate commit** — the exact code tree under
  review — and the **handoff packet commit** — the exact tree containing
  the completed packet evidence. The full offline baseline
  `python3 -m unittest` MUST be green from each of the two commits
  independently. The handoff further names all five interface
  versions and exact schema paths, validator versions/commands and results,
  scene-to-record manifest, receipt stage ownership, rejected-case inventory,
  migration/provenance notes, documentation dispositions/validation/reviewer,
  evidence references, and known limitations with no unresolved ownership
  ambiguity (T019's enumeration is the authoritative packet list).
- **SC-006**: A repository-boundary check finds zero product schemas, tests,
  fixtures, evaluation assets, evidence, or product documentation under this
  SpecKit directory.

## Assumptions

- Authorized slice implementation retains Python 3.11+ and stdlib-only runtime constraints unless a
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
  dispositions, exact reviewed paths, validation, reviewer, and accepted delta
  (documentation/packet inputs — a different file from the lifecycle attempt
  stream `slice-handoff.md` declared above).

## Explicit Exclusions

- No V2 schema, test, evaluator, evidence, documentation, core, CLI, adapter,
  or harness implementation is created by this planning baseline.
- No classifier prompt or provider call (slice `030` owns them), social
  heuristic (constitutionally excluded program-wide), context collector
  (slice `020`), participant invocation (slice `040`), transport integration
  (slice `050` for shared Discord; `060`–`090` for their surfaces), or
  deployment choreography (slice `110` and the separate release decision).
- No V1 compatibility bridge and no decision about release numbering,
  promotion, or standalone-adapter release scope.
- Slices 020, 030, and 040 own their implementations and MUST request contract
  changes from `v2-contract-owner` rather than editing shared schemas directly.
