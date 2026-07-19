# Existing Slice Specification: V2 Core Attention

**Feature Branch**: `v2/core-attention`

**Created**: 2026-07-11

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/attention/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/attention/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/attention/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/attention/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Input**: Stage one participant-shaped V2 pre-attention judgment, governed
suppression, dual DEFER valves, separate operational error, and contract-
equivalent callable core and CLI for slice-110 atomic publication while V1
remains the only current public behavior.

**Authority source**: Zoe-selected Aleph Vault design at `bdd1ebb`, contract-clarified in PR 68 at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-core-owner`

**Assigned participant / source**: codex-session-1 — evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md

The named assignment MUST be a non-symlink durable record containing exactly
one `Assignee`, `Lane`, `Assigned by`, ISO `Assigned on`, and durable
`Authority reference`; a non-Zoe assigner additionally requires
`Delegated by: Zoe` and a durable `Delegation reference`. Assignment neither grants program
implementation authority nor establishes slice readiness or activation.

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/030-v2-core-attention`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: `010-v2-contract`

**Dependency commits / acceptance references**: at readiness,
`slice-activation.md` MUST record `Accepted dependencies` in the declared order,
ordered `Dependency commits` as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Feeds**: `040`, `060`, `070`, `080`, `090`, `100`, `110`

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
- Authorized slice implementation targets `src/nunchi/`; deterministic tests
  target `tests/v2/attention/`, replay assets `evals/v2/attention/`, evidence
  `evidence/v2/attention/`, and product documentation `docs/attention/`.
- Conflicts MUST resolve in this order: the Zoe-selected Aleph Vault design at
  `c834e8c`; the constitution; `AGENTS.md` and `CLAUDE.md`; the umbrella and
  bound-slice control plane; then ordinary-path source, schemas, tests, evals,
  evidence, and docs for what is currently implemented and proven. Higher
  authority controls the selected target; ordinary-path artifacts control
  current implementation truth. A conflict requiring a selected-design change
  returns to Zoe and the owning lane rather than being decided inside slice 030.
- This planning baseline creates no schema, prompt, classifier, provider call,
  CLI behavior, test, replay corpus, evidence, product documentation, or V2
  runtime behavior.
- Build, test, evaluation, documentation, packaging, release, and runtime
  commands MUST NOT depend on `.specify/`, `specs/`, or either installed
  SpecKit skill tree.
- Program authority, assignment, dependency acceptance, slice lifecycle, and
  handoff/acceptance facts are repository governance only. They MUST NOT become
  runtime or conversation state, classifier input, receipt fields, a participant
  roster, a handled/open or obligation ledger, or a memory service.
- The current V1 implementation and its `PASS / ACK / ASK / SPEAK` contract
  remain implementation truth through atomic integration and exact-main
  verification; V2 becomes current only when the program reaches
  `CUTOVER_VERIFIED` after final documentation validation.

## Clarifications

### Session 2026-07-19

- Q: Does a receipt-sink invocation failure retain a previously trusted
  `NO_WAKE` override when the required override receipt did not persist? → A:
  No. Every receipt-sink invocation failure uses the shared `WAKE` default,
  regardless of the previously trusted policy, because the override cannot be
  durably receipted.
- Q: What delay does the bounded V2 transport retry use? → A: It waits a fixed
  0.5 seconds before attempt 2 and 1.0 second before attempt 3. It does not
  consume or honor provider `Retry-After`; success, a terminal non-retryable
  failure, and the final allowed failure never sleep.

### Resolved post-acceptance contract amendments and program handoff

The selected design at `c834e8c` requires the effective policy and its source
to be inspectable in receipts and an operator `NO_WAKE` override to be
separately receipted as operational failure policy. The deficiency discovered
against I-010E `@1` remains immutable historical evidence at
`evidence/v2/attention/dependency-010-post-acceptance-blocker.md`.

Slice 010 resolved it through accepted amendment A1: exact candidate
`817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`, exact candidate-record commit
`6296316fd415e85762860569289016a675ab5d2d`, and integrator decision commit
`30aba09f13a6752b4c24811da0d8ec772a9d9682`. I-010E
`AttentionReceiptV2@2` preserves the trusted-bypass body's required
`policy_provenance`, adds required classifier-outcome `policy_provenance`, and
represents the explicit error-policy override only as paired
`wake_action: "NO_WAKE"` plus `policy_provenance`; the default `WAKE` path
omits that pair. This consumer independently accepts the exact amendment at
`evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`. The earlier
consumer acceptance and blocker records are not rewritten.

Fresh bound analysis subsequently found a separate selected-design/I-010B
conflict: a zero-width active margin is permitted by the design but could not
be represented by accepted I-010B `@1`. The immutable discovery remains at
`evidence/v2/attention/dependency-010-amendment-A1-post-acceptance-zero-margin-blocker.md`.
Slice 010 resolved it through accepted amendment A2: exact correction candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301` and integrator decision commit
`d504310c61a93afbe57d4fe4ed05e93055c75555`. I-010B
`AttentionDecisionV2@2` accepts an applied `effective_margin` in inclusive
`[0,1]` without changing any other decision field or cross-field rule. This
consumer independently accepts that exact amendment at
`evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`; the prior
acceptance and blocker records remain immutable history.

The program-owned canonical interface registry remains stale for the accepted
I-010B/I-010E versions. That open program handoff is recorded at
`evidence/v2/attention/program-interface-registry-I-010E-version-blocker.md`
and dispositioned for this bound slice at
`evidence/v2/attention/program-interface-registry-readiness-disposition.md`.
It remains owned by `v2-program-owner` but is not a slice-030 dependency or a
CRITICAL/HIGH finding in this slice's requirements/task graph. Slice 030 remains
`PLANNED` and dormant until a fresh bound analysis reports zero scoped
CRITICAL/HIGH findings and activation evidence establishes `READY`.

## Interface Summary

- **Consumes**:
  - `I-010A AttentionRequestV2@1`
  - `I-010B AttentionDecisionV2@2`
  - `I-010E AttentionReceiptV2@2`
- **Produces**: `I-030A AttentionEngineV2@1` — the versioned
  `evaluate_v2(...)` callable, its `ReceiptSinkPersistenceError` protocol type,
  plus the non-current `attention-v2` CLI command, contract-equivalent CLI
  implementing I-010A/B/E, participant-shaped
  `SUPPRESS | WAKE(advice) | DEFER`, a non-social preattention-disabled
  `BYPASS`, separate `ERROR`, and the dual-valve uncertainty transition.
- **Integration handoff**: `v2-core-owner` hands the exact commit, interface
  version, prompt/model provenance, deterministic commands, replay and
  multi-model evidence, policy defaults, margin state, and known limitations to
  `v2-wake-owner`, every named downstream surface owner, and `v2-integrator`.
  Only `v2-contract-owner` may revise the consumed schemas.

## User Scenarios & Testing

### User Story 1 - Ask One Human-Shaped Attention Question (Priority: P1)

For one valid factual snapshot, Nunchi reads as the participant described in
`self` and makes one narrow judgment: whether this event is worth waking that
participant now.

**Why this priority**: Model nuance over clean facts is the product's reason to
exist; prescriptive social algorithms recreated the false-silence failure.

**Independent Test**: Run a deterministic provider transport and replay corpus
through both callable core and CLI, proving one logical judgment returns only a
valid I-010B outcome without reply prose or a participant move command.

**Acceptance Scenarios**:

1. **Given** a valid request the participant confidently would not want to
   attend, **When** an authorized model judges it, **Then** classifier
   disposition may be `SUPPRESS` and every cited reason/evidence ID refers to
   supplied facts.
2. **Given** a request worth attention, **When** the model returns `WAKE`,
   **Then** optional advice follows FR-005's sparse prompt/evidence criterion,
   is non-authoritative, grounded in included events, and contains no drafted
   response.
3. **Given** genuine uncertainty, **When** the model cannot confidently decide,
   **Then** it returns `DEFER`; no deterministic rule converts uncertainty into
   silence.
4. **Given** trusted effective configuration disables preattention, **When** a
   valid request enters the engine, **Then** status is `bypass`, cause is
   `preattention-disabled`, the classifier is not invoked, and no classifier or
   effective social disposition is fabricated.

---

### User Story 2 - Govern Suppression and Preserve Both DEFER Valves (Priority: P1)

An operator can delegate or revoke social suppression for one exact participant
binding, while direct classifier DEFER and the protective legacy-margin DEFER
remain distinct, observable, and one-way toward waking.

**Why this priority**: A suppression decision loses a conversational moment;
recoverability and cheap uncertainty are load-bearing legitimacy conditions.

**Independent Test**: Exhaust the disposition/policy/margin transition matrix
with deterministic model outputs and prove no policy, malformed vector, or
missing legitimacy condition can create or preserve an unsafe hard stop.

**Acceptance Scenarios**:

1. **Given** candidate `SUPPRESS`, proven recoverability, enabled delegation,
   and a valid active-margin vector where
   `PASS - max(ACK, ASK, SPEAK) > transition_defer_margin`, **When** routing
   completes, **Then** effective `SUPPRESS` is allowed and fully receipted.
2. **Given** candidate `SUPPRESS` with an inclusive active-margin result
   `PASS - max(ACK, ASK, SPEAK) <= transition_defer_margin`, disabled
   suppression, or unproven recoverability, **When** routing completes, **Then**
   effective disposition is `DEFER` with the exact valve and override cause.
3. **Given** classifier `DEFER`, **When** the margin is still active, **Then**
   classifier DEFER is honored independently and cannot be narrowed to
   suppression.

---

### User Story 3 - Bypass or Fail Operationally Through One Core/CLI Contract (Priority: P2)

A host receives the same tagged decision from the callable core and CLI, while
trusted preattention bypass and validation, provider, timeout, malformed-output,
and runtime failures stay separate from social dispositions. Operational errors
default toward participant wake; bypass wakes without pretending a model spoke.

**Why this priority**: Existing consumers disagree on error and DEFER behavior;
parity needs one audited seam before harness integration.

**Independent Test**: Submit the same valid, bypassed, and invalid inputs through
core and CLI, compare semantic outputs and exact stdout/stderr/exit behavior,
and prove bypass and every operational failure remain tagged non-social
branches. Emit an immutable I-010E attention-stage record whenever the parsed
request supplies a valid correlation ID; unreadable, invalid-JSON, and
pre-validation failures without an assignable request ID are explicitly
non-receiptable and MUST NOT fabricate one.

**Acceptance Scenarios**:

1. **Given** validation or classifier failure after a routable event exists,
   **When** the engine returns, **Then** status is `ERROR`, default host action
   is wake, and error detail remains off the room surface.
2. **Given** a fully validated, exactly request-bound trusted configuration
   explicitly selects `NO_WAKE`, **When** a later budget, provider, malformed-
   model, or runtime error remains receiptable, **Then** the override is
   separately sourced and receipted through I-010E `@2`'s paired
   `wake_action: "NO_WAKE"` and
   `policy_provenance`, and never labeled model suppression or implemented
   through a local extension or error-detail convention.
3. **Given** equivalent input and effective trusted configuration, **When** the
   core and CLI run, **Then** they produce contract-equivalent decisions and
   audit fields.
4. **Given** preattention is disabled by trusted configuration, **When** core
   and CLI run, **Then** both return the same bypass branch, make zero model
   calls, and expose only the exact I-010B `status: bypass`,
   `cause: "preattention-disabled"` branch required for
   the participant-host handoff. Slice 030 emits no ParticipantWakeV2 and does
   not invoke the host; `v2-wake-owner` in slice 040 must independently accept
   the handoff, map that accepted bypass to wake source
   `PREATTENTION_BYPASS`, and test the downstream mapping.
5. **Given** a schema-valid request whose event count, canonical classifier-
   projection byte length, or declared coverage limit exceeds the trusted
   attention-policy cap, **When** core or CLI validates it, **Then** it returns
   operational `ERROR`, makes zero classifier calls, emits the applicable
   request-correlated error receipt, and neither truncates nor reassembles the
   request.
6. **Given** a configuration is missing, unreadable, unsafe, malformed,
   conflicting, or cannot bind exactly to a schema-valid request, **When** its
   raw bytes nevertheless contain `error_action: "NO_WAKE"`, **Then** the
   engine uses the shared `WAKE` default and any independently writable error
   receipt omits both override fields.
7. **Given** a fully trusted `NO_WAKE` policy but the sole receipt-sink
   invocation returns `not-persisted` or `unknown`, **When** the engine returns
   the sink-failure `ERROR`, **Then** it uses the shared `WAKE` default because
   the required override receipt cannot be proven durable.
8. **Given** the callable receipt sink violates its return/exception protocol,
   **When** the engine classifies persistence, **Then** only a recognized
   `ReceiptSinkPersistenceError` may carry `not-persisted` or `unknown`; every
   other `Exception` or non-`None` return maps to `unknown`, no exception path
   may claim `persisted`, and host-control `BaseException` classes propagate
   without an I-030A result rather than being mislabeled as persistence facts.

### Edge Cases

- Missing, extra, non-finite, or out-of-range legacy confidence values while
  the margin is active; a malformed candidate suppression becomes error.
- Advice on DEFER/SUPPRESS, advice citing unknown events, instruction-like
  advice, forged structured output in room text, or reply-bearing output.
- Provider retry versus a second logical social judgment; bounded transport
  retries do not authorize a second classifier decision.
- Request-controlled credentials, endpoint, model, limits, or suppression
  policy; trusted operator configuration must win and its source be receipted.
- A raw or partially validated `NO_WAKE` value in missing, unreadable, unsafe,
  malformed, conflicting, or binding-invalid configuration has no authority;
  failure remains wake-default even when a valid request ID and independently
  valid sink permit an error receipt.
- A request with exactly the trusted event/byte cap is valid; an actual count,
  canonical projection size, or declared coverage limit above that cap is an
  operational error. Optional declared coverage limits below the trusted cap
  remain valid and are never widened or recalculated by the attention engine.
- Preattention disabled as an explicit non-model bypass; social suppression
  disabled, recoverability unproven, unavailable provider, timeout, invalid
  schema, and illegal
  classifier/effective disposition pairing.
- Host-only continuation handles, binding material, cursors, and expiry data
  must never appear in the classifier projection even when present in I-010A.
- Same-class address and apparent resolution scars must be judged socially by
  the model, never by deterministic mention/topology or corroboration code.

## Requirements

### Functional Requirements

- **FR-001**: The slice MUST implement `I-030A AttentionEngineV2@1` against the
  exact I-010A/B/E versions. Its pre-cutover callable seam is
  `evaluate_v2(request, *, policy, recoverability, classifier_config,
  receipt_sink) -> AttentionDecisionV2`: `request` is I-010A;
  `policy`, `recoverability`, and `classifier_config` are trusted host inputs;
  `recoverability` is exactly `{participant_id, continuity_scope_id, eligible,
  source}` with non-empty string bindings/source and boolean `eligible`;
  binding mismatch is configuration `ERROR`, while `eligible: false` can only
  widen candidate suppression to `DEFER`. `receipt_sink` is a required
  host-owned callable offered the exact I-010E attention-stage record when a
  valid request ID exists; sink failure returns operational `ERROR` with wake
  default and MUST NOT claim persistence. The return value is I-010B. The CLI
  obtains the same trusted inputs only from operator configuration, never room
  JSON. For identical normalized inputs, the parsed CLI stdout decision and
  callable return MUST be field-for-field equal; the offered attention receipt
  body and writer MUST be equal. CLI framing, diagnostics, and exit code are the
  only permitted surface differences.
  `policy` is the exact selected `EffectiveAttentionPolicy` object:
  `{participant_id, preattention_enabled, social_suppression_enabled,
  attention_max_events, attention_max_bytes, participant_max_events,
  participant_max_bytes, fetch_max_events, fetch_max_bytes, error_action,
  transition_defer_margin?, transition_defer_margin_source?, source}`. Its
  identifiers/source are non-empty strings, booleans are strict booleans, every
  limit is a positive integer, `error_action` is `WAKE | NO_WAKE`, and the two
  transition-margin members are either both absent (retired) or both present
  with a finite margin in `[0,1]` and non-empty source (active).
  Slice 030 validates `participant_max_events`, `participant_max_bytes`,
  `fetch_max_events`, and `fetch_max_bytes` only as required positive-integer
  members of the closed trusted policy; it MUST NOT enforce, transform, or use
  them to change I-030A routing. Participant packet cap enforcement belongs to
  slice 040, and continuation-fetch cap enforcement belongs to slice 020.
  Slice 030 neither invokes those consumers nor forwards those values to the
  classifier. For an otherwise identical request and policy, changing any of
  those four members between valid positive integers MUST NOT change the
  I-030A result or offered attention receipt; an invalid member makes the whole
  policy configuration `ERROR` before bypass or provider use.
  After I-010A schema validation and trusted binding validation, but before
  preattention bypass or any classifier call, I-030A MUST enforce the trusted
  attention budget. Every message, reaction, and membership event counts once;
  `len(request.events)` MUST be at most `policy.attention_max_events`. The
  classifier-visible projection is the I-010A request with host-only
  `continuation` authority removed. In its place the internal projection MUST
  contain exactly one top-level `expansion_available` object with exactly the
  boolean keys `before`, `after`, and `around_event`. When continuation is
  present those values copy `can_fetch_before`, `can_fetch_after`, and
  `can_fetch_around_event`; when continuation is absent all three are `false`.
  No handle, binding, cursor, expiry, fetch cap, or source is retained. Every
  other I-010A field, including factual `coverage`, is preserved unchanged.
  The projection byte length is computed before provider framing as UTF-8 JSON
  with object keys sorted, no insignificant whitespace, and non-ASCII
  characters emitted directly. That length MUST be at most
  `policy.attention_max_bytes`.
  Equality is valid. Optional `request.coverage.max_events` and
  `request.coverage.max_bytes` MAY be absent or lower than/equal to their
  matching trusted caps; either declaration above its matching trusted cap is
  an operational `ERROR` even when the supplied snapshot happens to fit.
  Any actual or declared overage makes zero classifier calls, is receipted as
  the normal I-010E `@2` error branch when a valid request ID and working sink
  exist, and MUST NOT cause I-030A to truncate, reorder, reassemble, or
  recalculate coverage. Slice 020 owns bounded observation assembly.
  `classifier_config` is exactly `{provider, endpoint, model, api_key?,
  timeout_seconds, max_retries, source}`: all present string fields are
  non-empty, timeout is positive and finite, `max_retries` is the FR-003
  integer, and `api_key` is never projected, logged, or receipted. The callable
  receives already-normalized trusted objects. The staged CLI command is
  exactly `nunchi attention-v2 --config PATH`: it accepts I-010A only on stdin
  and resolves all trusted inputs from that one operator-selected file. The
  file is a closed JSON object with exactly `policy`, `recoverability`,
  `classifier_config`, and `receipt_sink`; `receipt_sink` is exactly
  `{type: "exclusive-json-file", directory, source}` with a non-empty absolute
  `directory`, non-empty `source`, and no other members. `PATH` MUST be opened
  descriptor-first with no symlink following and then verified as a regular
  file owned by the effective user with no group/other permission bits. The
  receipt directory MUST already exist and be opened descriptor-first with no
  symlink following, then verified as a directory owned by the effective user
  with no group/other permission bits; all later receipt operations are
  relative to that held directory descriptor. JSON duplicate keys are invalid. No inline JSON,
  per-field flags, fallback environment variables, or request members are
  configuration sources. No config-derived value, including `receipt_sink`, is
  eligible until the outer configuration file itself passes descriptor
  security. A missing, unreadable, unsafe, symlinked, non-regular, invalid-JSON,
  or duplicate-key file therefore constructs no sink and emits no receipt. Once
  that source boundary passes and a duplicate-free JSON object exists, its
  closed `receipt_sink` member may be validated and securely constructed
  independently of failures in another nested member or the outer closed-shape
  check. A missing/extra key or any nested validation failure is configuration `ERROR`;
  there is no source merge or precedence rule. Policy
  `participant_id` and recoverability `participant_id` MUST both equal
  `request.self.participant_id`; recoverability `continuity_scope_id` MUST equal
  `request.room.continuity_scope_id`; any mismatch is configuration `ERROR`.
  An `error_action: NO_WAKE` override becomes trusted only after the complete
  configuration file has passed descriptor security, duplicate-key, closed-
  shape, nested-value, and single-source validation and after the accepted
  I-010A request has passed schema validation and all participant/scope bindings
  above. Missing, unreadable, unsafe, malformed, conflicting, request-invalid,
  or binding-invalid input therefore always uses the shared `WAKE` default;
  raw or partially validated `NO_WAKE` never grants silence authority. If such
  a failure occurs after the outer source boundary, has an assignable valid
  request ID, and has an independently valid securely constructed sink under
  the CLI precedence rules, its error receipt omits both `wake_action` and
  `policy_provenance`. Request-schema and binding failures may likewise use
  that already constructed sink. Otherwise the failure is non-receiptable and
  MUST NOT fabricate one. A fully validated and bound `NO_WAKE` policy applies
  to later trusted-budget, provider, timeout, malformed-model, or runtime errors
  only when the override can be offered through the required receipt. Every
  receipt-sink invocation failure instead uses the shared `WAKE` default because
  the override receipt did not persist; neither `not-persisted` nor `unknown`
  persistence retains silence authority.
  `receipt_sink` is exactly a synchronous
  `Callable[[AttentionReceiptV2], None]`: one normal `None` return means the
  offered record persisted, any raised exception means failure, and the engine
  neither retries nor calls the sink more than once for a request. The staged
  I-030A runtime defines `ReceiptSinkPersistenceError` in
  `src/nunchi/core.py` as its sole engine-owned typed sink-failure protocol.
  Its constructor accepts exactly `not-persisted` or `unknown`, exposes that
  value as a read-only `persistence` member, and rejects every other member.
  The engine recognizes the type and its subclasses with `isinstance`; it does
  not traverse a wrapper or `__cause__`/`__context__` chain. A recognized
  instance whose member was forged or altered outside the constructor maps to
  `unknown`. Every other `Exception`, including an exception that merely
  carries a lookalike attribute, maps conservatively to `unknown`, as does a
  normal non-`None` sink return. No exception may report `persisted`.
  `not-persisted` is valid only for a closed-contract pre-write rejection whose
  semantics guarantee that no durable side effect occurred. Generic
  exceptions, unrecognized typed exceptions, timeout/cancellation, and post-
  dispatch failures map to `unknown`. An `unknown` result MUST NOT trigger a
  non-idempotent retry; the one-offer/no-second-offer rule still applies.
  `BaseException` classes, including process termination, keyboard interrupt,
  and host cancellation outside `Exception`, are not converted into an I-030A
  decision or persistence fact: they propagate after the sole offer. A host
  that catches such control flow and converts it into participant routing MUST
  use wake, never silence. Exception text, attributes other than the validated
  member, wrapper/cause chains, paths, and credentials never enter projection,
  stdout, stderr, decisions, receipts, or logs. The CLI
  adapts its closed `receipt_sink` object to that protocol by canonicalizing the
  attention record as UTF-8 JSON plus one newline and using descriptor-relative
  no-follow exclusive create for mode `0600` file
  `<sha256(request_id UTF-8)>.attention.json`; it never overwrites an existing
  record. Success requires complete write, flush, file `fsync`, close, and
  directory `fsync`. An exclusive-create collision raises a typed sink failure
  with persistence `unknown`: the engine neither overwrites nor assumes the
  existing file is its record. Any other open failure before creation is
  `not-persisted` only when the failed exclusive-create operation guarantees
  that no file was created. Any write/flush/fsync/close failure triggers
  descriptor-relative unlink of only the newly created file followed by
  directory `fsync`, but every such post-dispatch failure reports `unknown`
  even when cleanup succeeds. Cleanup/unlink/directory-fsync failure, or a
  final directory-fsync failure after the file was closed, likewise reports
  persistence `unknown`. Neither failure
  outcome claims persistence, and the engine returns operational `ERROR` with
  the shared `WAKE` default and the exact sink outcome in its off-surface error
  fact. The configuration file,
  credentials, filesystem path, and sink source never enter classifier input,
  stdout, stderr, decision data, or receipt body.
  I-030A generates only these stable error-code/cause-detail pairs, while
  I-010B's schema-level `code` remains an open non-empty string:
  `configuration-error` / `trusted configuration invalid`,
  `request-validation-error` / `attention request invalid`,
  `attention-budget-error` / `attention budget exceeded`,
  `provider-timeout` / `attention provider timed out`,
  `provider-error` / `attention provider failed`,
  `malformed-model-output` / `classifier output invalid`,
  `invalid-transition` / `attention transition invalid`,
  `invalid-legacy-confidence` / `legacy confidence vector invalid`,
  `runtime-error` / `attention runtime failed`, and
  `receipt-sink-failure` / `attention receipt sink failed`.
  An offered I-010E error record uses the exact cause pair and cannot claim its
  own persistence. The returned I-010B error appends exactly
  `; receipt_persistence=<persisted|not-persisted|unknown>` to the safe cause
  detail after the one sink attempt. If that attempt fails, the returned error
  is the `receipt-sink-failure` pair with the observed `not-persisted` or
  `unknown` value; no second receipt attempt occurs. These fixed details MUST
  expose no path, credential, provider payload, configuration value, or receipt
  provenance.
- **FR-002**: The model instruction MUST tell the classifier to read the factual
  snapshot as the participant described by the request's classifier-safe
  `self` facts, not as a generic traffic controller, and decide only whether the
  supplied event is worth waking that participant for now. It MUST request
  `SUPPRESS` only when confident the participant would not want to attend,
  `WAKE` when they likely would, and `DEFER` when uncertain; it MUST require
  grounding in observed events and forbid invented missing facts and reply
  composition. This is the complete meaning of participant-shaped and sparse:
  the instruction MUST NOT add a speaker algorithm, address/topology rule,
  response-obligation rubric, or participant move command.
- **FR-003**: One valid request MUST produce one logical model judgment.
  Trusted `classifier_config.max_retries` is required and MUST be an integer
  from `0` through `2`, so one judgment has at most three transport attempts;
  neither callable nor CLI inserts a default.
  The V2 stdlib transport classifies `urllib.error.HTTPError` before the other
  request failures. Only HTTP `429`, any HTTP status from `500` through `599`,
  `urllib.error.URLError`, `socket.timeout`/`TimeoutError`, and an `OSError`
  (including `ConnectionError`) raised while `urlopen` is executing the request
  are retryable. A `URLError` is classified by its outer type without
  inspecting or trusting its `reason`. Every other HTTP status, configuration
  or request/schema validation failure, JSON decoding failure, malformed model
  output, and failure after a response has been obtained is non-retryable.
  The retry delay is fixed and deterministic: wait 0.5 seconds before attempt
  2 and 1.0 second before attempt 3, never honor provider `Retry-After`, and do
  not sleep after success, a terminal non-retryable failure, or the final
  allowed failure.
  Deterministic tests MUST cover HTTP `429`, `499`, `500`, `599`, and `600`;
  direct timeout, `URLError`, `ConnectionError`, and other request-execution
  `OSError`; exact attempt and sleep counts for `max_retries` `0`, `1`, and `2`;
  identical payload/request identity on every attempt; immediate stop after
  success; and zero retry for each non-retryable class.
  Every attempt reuses the same request payload and logical request ID and may
  not be treated as an independent social vote. Exhaustion returns operational
  `ERROR` and follows FR-011's later-provider-failure policy: shared default is
  `WAKE`; a fully validated, bound `NO_WAKE` policy applies only when its
  required override receipt can be offered; and any sink failure reverts to
  `WAKE`.
- **FR-004**: The classifier disposition MUST be exactly `SUPPRESS`, `WAKE`, or
  `DEFER`; operational `ERROR` MUST remain a separate tagged response branch.
- **FR-005**: `WAKE` advice, when present, MUST be non-authoritative, grounded
  in named supplied event IDs, and free of reply prose; `SUPPRESS` and `DEFER`
  MUST carry no participant advice. The prompt MUST request at most two sparse
  annotations of at most 240 Unicode scalar values each, and deterministic plus
  three-family evidence MUST report 100% adherence before handoff. Each WAKE
  advice item is recorded with its note, cited supplied event IDs, Unicode
  scalar count, and four owner-adjudicated binary rubric fields: citations all
  resolve to supplied events; the note describes why attention may matter; it
  contains no proposed reply quotation or first-person drafted response; and it
  contains no imperative telling the participant what to say or do. The
  first field is deterministic citation resolution. The assigned
  `v2-core-owner` is the recorded adjudicator for the remaining three semantic
  fields, and any failed field is a failed advice case. Count, length, and the
  first citation field are deterministic; the three semantic fields remain
  explicit human evidence, not a runtime social heuristic.
  These are prompt/evidence criteria only: runtime validation MUST NOT reject or
  truncate otherwise I-010B-valid advice solely for item count or length.
- **FR-006**: Social suppression MUST require exact participant authorization,
  recoverability eligibility supplied as the trusted, exactly bound FR-001
  capability, cheap uncertainty, and inspectable/revocable operator delegation.
  Here, cheap uncertainty means uncertainty returns classifier `DEFER` or
  `WAKE` and never effective suppression; inspectable means effective policy,
  model, and their sources are present in the allowed decision/receipt audit;
  revocable means trusted `social_suppression_enabled: false` widens candidate
  suppression to `DEFER` without changing transport delivery; and
  recoverability ineligibility likewise widens only to `DEFER`.
- **FR-007**: Effective policy, provider endpoint, credentials, model, budgets,
  error action, suppression enablement, transition margin, and configuration
  source MUST be operator-owned and MUST NOT be redirected by room input.
- **FR-008**: Direct classifier DEFER and margin-derived DEFER MUST be separately
  receipted; either may only widen attention, and the margin retains protective
  precedence until separately retired by evidence. Routing validation precedes
  policy: malformed/missing active-margin confidence on candidate `SUPPRESS`
  is `ERROR`. For a valid candidate `SUPPRESS`, active-margin uncertainty is
  exactly `PASS - max(ACK, ASK, SPEAK) <= transition_defer_margin`; equality is
  inside the margin and produces `margin-defer` / `margin`, while a strictly
  greater difference is outside the margin. First-match routing precedence is
  suppression disabled (`policy-defer` / `suppression-disabled`), then
  recoverability false (`policy-defer` / `recoverability-unproven`), then that
  active-margin uncertainty result, then no valve. Thus each matrix row has one
  exact audit oracle even when several widening conditions coexist. Candidate
  `WAKE` uses `none`; classifier `DEFER` uses `classifier-defer`; neither is
  narrowed by policy or margin. This preserves the selected existing-margin
  valve rather than inventing a new V2 threshold rule.
- **FR-009**: A candidate suppression while the margin is active MUST include
  the exact valid legacy confidence vector required by I-010B; missing or
  malformed evidence MUST produce operational error and wake fallback.
- **FR-010**: Deterministic policy MAY convert candidate `SUPPRESS` only to
  `DEFER`; it MUST NOT manufacture suppression or convert `WAKE`/`DEFER` to a
  hard stop.
- **FR-011**: Validation, provider, timeout, malformed-output, configuration,
  and runtime failures MUST return `ERROR`; shared default action is wake, with
  any explicit `NO_WAKE` operator override separately sourced and receipted.
  Only the fully validated, exactly request-bound trusted policy defined in
  FR-001 may exercise that override. Configuration, request-schema, or binding
  failure before that trust boundary MUST use the shared `WAKE` default even if
  raw or partially validated input contains `NO_WAKE`; any writable error
  receipt omits the override pair. A later budget/provider/runtime failure may
  use the already trusted override.
  Accepted I-010E `@2` represents that override only through paired
  `wake_action: "NO_WAKE"` and non-empty `policy_provenance`; the default wake
  path omits both fields, and `WAKE`, other actions, or incomplete pairs reject.
- **FR-012**: Whenever a parsed request supplies a valid request ID and an
  eligible host-owned receipt sink exists, the engine MUST **offer** exactly one
  immutable attention-stage I-010E record correlated by that ID: offer means one
  invocation of that sink with the record. The record keeps classifier
  disposition, effective disposition, valve, override cause, the policy/model
  provenance representable by the accepted branch, operational error, and
  classifier-not-invoked bypass provenance distinct. **Persisted** means the
  sole sink invocation completed its defined durable-success protocol; no
  response or offered record may claim its own persistence. Unreadable input,
  invalid JSON, pre-validation failure without an assignable request ID, or a
  path where no eligible sink can be securely constructed MUST make zero offers
  and MUST NOT invent either a record or correlation ID. Failure of the sole
  sink invocation means a record was offered but did not establish persistence:
  it MUST return operational `ERROR` with wake default and report
  `not-persisted` or `unknown` without a second offer. Latency and
  serialized/token-cost measurements MUST remain ordinary performance evidence,
  not extra fields inside the closed I-010E attention body. The engine MUST
  leave participant, send, and transport outcome facts to later stages and MUST
  NOT mutate an earlier observation-stage record.
  The trusted-bypass attention body is exactly
  `{classifier_not_invoked: true, cause: "preattention-disabled",
  policy_provenance: <non-empty string>}`. It MUST carry the trusted effective
  policy source even though no classifier ran, and it MUST NOT contain
  classifier disposition, effective disposition, classifier identity,
  evidence, routing-audit, or error members. Missing or empty bypass
  `policy_provenance` is invalid I-010E `@2` and MUST NOT be offered as a valid
  receipt.
  Accepted I-010E `@2` represents the selected design's broader
  effective-policy and `NO_WAKE` provenance requirements directly; neither may
  be hidden in I-010E `error.detail` or a local extension.
  The I-030A-owned `ReceiptSinkPersistenceError` changes no I-010E field or
  ownership rule. It is part of the still-unaccepted initial I-030A `@1`
  runtime seam, so this clarification does not bump I-030A; every downstream
  consumer receives and separately accepts that exact `@1` seam.
- **FR-013**: The isolated slice branch MUST stage I-030A as additive,
  non-current symbols inside the owned `src/nunchi/core.py`,
  `src/nunchi/cli.py`, `src/nunchi/classifiers.py`, `src/nunchi/models.py`, and
  `src/nunchi/schema.py` seams: `evaluate_v2` and `attention-v2` accept and emit only V2
  contracts and MUST NOT call, translate to, or fall back through V1. Existing
  public `nunchi.evaluate`, `nunchi admit`, and their V1 tests remain unchanged
  and green solely to preserve current behavior before cutover. The owner packet
  MUST give `v2-integrator` the exact slice-110 publication delta across
  `src/nunchi/core.py`, `src/nunchi/cli.py`, `src/nunchi/classifiers.py`,
  `src/nunchi/models.py`, `src/nunchi/schema.py`, and
  `src/nunchi/__init__.py`: remove V1 request/verdict handling,
  `require_pass_corroboration`, reply-bearing output, and hidden local
  fallbacks; publish I-030A as the public `evaluate`/`admit` behavior; and
  remove the temporary `evaluate_v2`/`attention-v2` staging names in the same
  atomic assembled candidate. This staging is not a V1-to-V2
  compatibility bridge and MUST NOT land on `main` or be documented as current
  behavior before slice 110.
- **FR-014**: Deterministic tests MUST prove mechanics and transition safety;
  committed replay, multi-model, false-suppression-scar, and preregistered
  downstream canary targets MUST be defined before social-quality or margin-
  retirement claims. The
  multi-model matrix MUST include the incumbent Gemini 3.1 Flash Lite family,
  frontier GPT-5.5 family, and open-weight Qwen3 family unless Zoe explicitly
  overrides the set; each run MUST record canonical scene and corpus/fixture
  identity, the exact provider model ID, provider, endpoint class, date,
  prompt/config identity, effective-policy source, invocation command, result,
  and any override provenance.
  Before the first provider call, T009 MUST commit the closed selection manifest
  `evals/v2/attention/model-selection.json`, mapping each required family to one
  exact provider model ID, provider, endpoint class, catalog/source evidence,
  selection date, and `v2-core-owner` review. T023 MUST refuse an absent,
  uncommitted, duplicate-family, extra-family, or result-mismatched selection.
  Any exact-ID change invalidates prior results and requires a new pre-run
  manifest commit; any family substitution still requires Zoe's durable
  decision. This freezes the Cartesian matrix before results rather than
  selecting a favorable model after execution.
  The exact required provider matrix is the Cartesian product of those three
  families and every committed case in
  `evals/v2/attention/suppression-scars/cases.jsonl`; each row MUST contain a
  unique `case_id`, canonical `scene_id`, contract-valid `request`, and
  preregistered owner label `expected_attention: ATTEND | NOT_ATTEND`. For each
  family, mistaken-suppression rate is effective `SUPPRESS` on `ATTEND` cases
  divided by all `ATTEND` cases; missed-suppression rate is non-`SUPPRESS` on
  `NOT_ATTEND` cases divided by all `NOT_ATTEND` cases; wake volume is
  non-`SUPPRESS` over all cases. Direct classifier `DEFER` and margin-derived
  `DEFER` are reported separately and both count as non-suppression/wake.
  Family disagreement is the number of case IDs with more than one distinct
  classifier disposition across the three valid family results divided by all
  case IDs. Missing or duplicate family/case results make the matrix incomplete
  rather than changing a denominator.
  This comparison is descriptive and non-gating for social-quality rates:
  mistaken suppressions, missed suppressions, wake volume, and family
  disagreement MUST be recorded and carried as limitations, but no local rate
  threshold authorizes social correctness or margin retirement. Handoff still
  blocks if a required family/corpus run is absent, provenance is incomplete,
  advice adherence is below FR-005's criterion, or mechanics fail to route an
  invalid/unsafe result to `DEFER` or operational `ERROR` as specified.
- **FR-015**: The owner MUST hand off the exact commit; consumed I-010A/B/E and
  produced I-030A versions plus its exact receipt-sink failure protocol;
  complete commands/results; prompt/model and
  effective-policy provenance; deterministic, replay, three-family, and
  false-suppression evidence; the preregistered downstream canary protocol;
  active-margin state; exact documentation dispositions, validations, reviewer,
  and routed deltas; rejected claims; known limitations; and the slice-110
  publication/deletion delta across `src/nunchi/core.py`,
  `src/nunchi/cli.py`, `src/nunchi/classifiers.py`, `src/nunchi/models.py`,
  `src/nunchi/schema.py`, and `src/nunchi/__init__.py`. The packet MUST name
  `v2-wake-owner`, the owners
  of slices `060` through `110`, and `v2-integrator` individually, and state
  that every dependent still owes separate acceptance of the exact commit and
  packet before its own activation. Delivery does not fabricate recipient
  acceptance or unavailable live participant evidence.
- **FR-016**: No product implementation, schema, test, corpus, evidence,
  runtime asset, or product documentation may be created under this SpecKit
  slice.
- **FR-017**: Trusted `preattention-disabled` configuration MUST return the
  I-010B `status: bypass` branch, make zero classifier calls, carry no
  classifier/effective disposition, and carry exactly
  `cause: "preattention-disabled"`;
  it MUST NOT be represented as WAKE, DEFER, ERROR, or model suppression.
  I-030A does not emit ParticipantWakeV2, identify its `wake_source`, or invoke
  the participant host. The slice-030 packet MUST hand the exact bypass branch
  to `v2-wake-owner`; slice 040 owns independently accepting it, mapping it to
  `PREATTENTION_BYPASS`, and proving that downstream mapping in an acceptance
  test.
- **FR-018**: The classifier projection MUST omit every opaque continuation
  handle, participant/room binding token, cursor, and expiry value. It MAY
  expose only factual coverage and booleans describing whether bounded
  expansion is available; the original I-010A continuation capability remains
  host-only and available to the later participant-host seam. I-030A does not
  consume I-010D fetch request/page objects.
- **FR-019**: For valid `ok` or `bypass` responses the CLI MUST write exactly
  one tagged JSON value to stdout, no response payload to stderr, and exit 0.
  Parsed requests that fail request-schema validation, configuration loading or
  validation, or secure sink construction MUST return tagged `status: error`
  JSON on stdout and exit 3. Provider/runtime/malformed-model
  failures MUST return tagged `status: error` JSON on stdout and exit 1.
  Unreadable input or invalid JSON, for which no request union can be formed,
  MUST write a diagnostic only to stderr, write nothing to stdout, and exit 2.
  These rules apply to the staged `attention-v2` command; existing V1 `admit`
  remains unchanged on the slice branch. After stdin forms a JSON value, the
  CLI applies this exact precedence: unreadable/invalid stdin JSON exits 2
  without loading config; after any JSON value is formed, configuration load,
  security checks, closed-shape validation, and sink construction run before
  request-schema validation, so a config failure wins over a simultaneous
  request-schema failure and exits 3. With a valid sink, later request-schema
  failure also exits 3 and is receipted only when the parsed request supplies a
  valid request ID. Request-schema, configuration, and binding failures cannot
  exercise `NO_WAKE` because the full trust boundary has not passed. A
  configuration error is likewise receipted only when its
  closed `receipt_sink` member independently validates and a valid request ID is
  assignable; that receipt omits both override fields. Otherwise no engine-owned
  sink exists. If no trusted sink can be constructed, the tagged error
  states persistence `not-persisted` and MUST NOT fabricate a receipt. A sink
  invocation failure after construction is operational/runtime exit 1 and
  reports the typed `not-persisted` or `unknown` outcome from FR-001.
- **FR-020**: Core/CLI tests MUST pass contract-valid requests containing
  sentinel continuation secrets and prove the classifier provider receives
  none of those host-only values. I-030A MUST treat the accepted request and
  its continuation object as caller-owned immutable input: evaluation neither
  mutates nor consumes it. Callable tests MUST compare a deep/canonical snapshot
  of the caller-held request before and after evaluation and prove the exact
  continuation capability remains present and available for later host use.
  CLI tests MUST retain a caller-side copy of the parsed input/capability and
  prove it remains byte/deep-equal after command evaluation while the provider
  projection contains no secret. Slice 030 does not itself invoke the host.

### Key Entities

- **Attention Engine**: Validates one I-010A request, runs one participant-shaped
  judgment, applies only safety-widening transition policy, and returns I-010B.
- **Effective Attention Policy**: Trusted operator configuration for delegation,
  budgets, error action, and the transition margin; never room social doctrine.
- **Attention Advice**: Optional evidence-grounded interpretation on WAKE only,
  with no instruction or reply authority.
- **Routing Audit and Receipt**: Distinct classifier, effective route, valve,
  override, bypass, provenance, and error facts in an immutable attention-stage
  record kept off-surface; performance measurements remain separate evidence.

## Success Criteria

### Measurable Outcomes

- **SC-001**: For every deterministic fixture, callable core and CLI produce
  field-for-field equal I-010B results and equal offered attention records for
  normalized inputs, using `evaluate_v2` and `attention-v2`, with only framing,
  diagnostics, and exit status allowed to differ. The applicable callable sink
  failure and CLI adapter fixtures preserve the plan's exact 23-row recognition
  matrix and expected persistence/wake outcome.
- **SC-002**: The exact 36-row classifier/effective transition matrix has zero
  invalid success pairs and zero cases where uncertainty or malformed evidence
  yields effective suppression. Its finite domain is: 16 `WAKE`/`DEFER` rows
  (`2` dispositions x suppression enabled/disabled x recoverability
  eligible/ineligible x margin active/retired), four retired-margin `SUPPRESS`
  rows (suppression x recoverability), and 16 active-margin `SUPPRESS` rows
  (suppression x recoverability x confidence class outside-margin,
  inside-margin, missing, or malformed). `inside-margin` means
  `PASS - max(ACK, ASK, SPEAK) <= transition_defer_margin`, including equality;
  `outside-margin` means the difference is strictly greater. Missing/malformed
  active-margin confidence always yields operational `ERROR`; policy may
  otherwise change only candidate `SUPPRESS` to effective `DEFER`. Every row
  records expected response status, classifier/effective pair when applicable,
  margin status, valve, and override cause using FR-008's validation and
  precedence order.
- **SC-003**: All forged advice, nonexistent evidence IDs, reply-bearing fields,
  request-controlled operator settings, invalid model output, non-`None` sink
  returns, lookalike persistence attributes, forbidden typed members, and
  forged invalid typed members are rejected or routed to the exact safe error
  path; no exception message or secret enters output or evidence.
- **SC-004**: False-suppression-scar replay contains no deterministic semantic
  suppressor and records model disposition, effective disposition, and
  participant-shaped rationale for every case.
- **SC-005**: Multi-model evaluation records distinguish direct classifier
  DEFER from margin DEFER and report mistaken suppressions, missed suppressions,
  wake volume, family disagreement, and FR-005 advice adherence separately.
  Those social-quality rates are descriptive/non-gating for slice 030; missing
  runs/provenance or an unsafe mechanics/advice result blocks handoff as defined
  by FR-014. A preregistered canary protocol assigns live participant/silence
  outcomes to the surface and final-integration owners; the 030 handoff does not
  depend on unavailable downstream behavior.
- **SC-006**: The protective margin is marked active at initial V2 handoff and
  cannot be retired by this slice without the separately required evidence and
  project-owner acceptance.
- **SC-007**: The handoff packet names exact I-030A and upstream versions,
  commands, evidence, effective configuration, prompt/model identity, margin
  state, and limitations with no downstream ownership ambiguity.
- **SC-008**: The exact candidate verification task records green results for
  `python3 scripts/check_governance.py --check-cli`, `python3 -m unittest`,
  `python3 -m unittest discover -s tests/v2/attention -p 'test_*.py'`,
  `python3 -m evals.v2.attention.runner --all`,
  `python3 -m evals.verdict_suite.runner --list`, and
  `git diff --check <activation-start>..HEAD`, with
  governance finding zero product artifacts under this slice directory.
  Latency, serialized request/response bytes, provider-reported input/output
  tokens (or explicit `unavailable`), attempt count, provider/model, runtime,
  host/OS, and fixture/corpus identity are mandatory descriptive fields. Slice
  030 sets no latency or token threshold and makes no performance pass claim
  beyond complete measurement; retry count remains mechanically bounded by
  FR-003. The focused suite and ordinary evidence MUST identify all 23
  receipt-sink matrix rows, their expected and observed classifications, the
  exact candidate, and zero skips. The full baseline MUST also prove that
  current V1 public exports,
  `admit`, adapters, and tests remain unchanged and green, while V2-specific
  tests prove the staging names never invoke or translate through V1. The
  activation record freezes the exact starting-commit root test/skip counts,
  the tracked pre-030 test-file inventory and content hash outside
  `tests/v2/attention/`, and the allowed slice diff roots. Candidate and packet
  verification MUST prove: that frozen pre-030 test tree is byte-identical; no
  adapter, harness, or 010-owned `schemas/v2/` contract path changed; the root
  test count equals the frozen activation root count plus the focused attention-
  suite count; root skips equal the frozen activation skip count;
  the focused suite has zero skips; and every changed path is one of the exact
  030-owned source, attention test/eval/evidence, or documentation paths in the
  plan. Any deleted/renamed pre-030 test, added skip, count mismatch, weakened test
  inventory, or out-of-scope path blocks convergence.

## Assumptions

- Slice 010 has landed accepted I-010A `@1`, amended I-010B `@2`, and amended I-010E
  `@2` before implementation begins.
- The existing standard-library OpenAI-compatible provider transport may be
  evolved without adding a runtime dependency.
- Initial V2 integration retains the protective margin; direct classifier
  DEFER evaluation can run live without narrowing safety.
- The selected three-family matrix is Gemini 3.1 Flash Lite, GPT-5.5, and
  Qwen3. Provider catalogs can change, so the committed pre-run
  `evals/v2/attention/model-selection.json` manifest pins the exact provider
  IDs and every run record must match it. Any exact-ID change requires a new
  pre-run manifest commit; any family substitution requires Zoe's durable
  decision.
- Slice 020 may develop in parallel and is not required to test I-030A because
  core tests can construct contract-valid I-010A fixtures directly.
- Slice 030 prepares but does not execute participant/live-room canaries;
  participant behavior does not exist until dependent slices land.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` exact I-030A disposition, bypass,
  operational ERROR, CLI, and dual-DEFER claim deltas to `v2-integrator`.
- **`UPDATE` inventory**: `docs/attention/v2.md`, `evidence/README.md`,
  `evidence/verdict-suite/README.md`, `evidence/v2/attention/README.md`,
  `docs/contracts/verdict-suite-data-model-v1.md`,
  `docs/contracts/verdict-suite-requirements-v1.md`,
  `docs/evaluations/verdict-suite.md`, and
  `docs/evaluations/verdict-suite-runner.md`, preserving V1 scar evidence while
  naming its V2 role. `docs/attention/v2.md` MUST document the fixed 0.5-second
  then 1.0-second retry cadence, ignored provider `Retry-After`, and every
  no-sleep terminal boundary alongside the retryable-failure taxonomy.
- **`NO_IMPACT` inventory**: `evidence/v2/contract/README.md`,
  `docs/archive/v1/README.md`,
  `docs/archive/v1/admission-classifier/contract.md`,
  `docs/archive/v1/admission-classifier/data-model.md`,
  `docs/archive/v1/admission-classifier/quickstart.md`,
  `docs/archive/v1/core-cli/contract.md`,
  `docs/archive/v1/core-cli/data-model.md`,
  `docs/archive/v1/core-cli/quickstart.md`, `docs/contracts/nunchi-v2.md`,
  `docs/governance/execution-spine.md`,
  `docs/integrations/hermes-core-patch.md`,
  `docs/integrations/hermes-core-patch-test-plan.md`,
  `integrations/claude-code/transport-patch/README.md`,
  `integrations/codex/nunchi-codex/.mcp.json`,
  `integrations/hermes/nunchi-gate/dashboard/manifest.json`,
  `integrations/mcp-discord/DESIGN.md`, and
  `integrations/mcp-discord/README.md`. Each path retains the exact per-file
  rationale in plan section Documentation Impact and Freshness; T025 MUST test
  that rationale against the candidate and record the reviewer and ordinary
  handoff evidence rather than treating this inventory as proof.
- **`HANDOFF` inventory**: `README.md`, `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`,
  `docs/INSTALL.md`, `docs/STABILITY.md`, `docs/adapters.md`,
  `docs/architecture/v2-selected-design.md`, `docs/contracts/channel-adapter-v1.md`,
  `docs/integration.md`, `examples/loader-snippet.md`,
  `examples/generic_host_demo.py`, `examples/read_the_room_demo.py`,
  `profiles/open-floor.md`, `integrations/claude-code/DEFER_EVAL.md`,
  `integrations/claude-code/README.md`, `integrations/claude-code/nunchi-gate.env.example`, `integrations/codex/README.md`,
  `integrations/codex/nunchi-codex/.codex-plugin/plugin.json`, `integrations/codex/nunchi-codex/hooks/hooks.json`,
  `integrations/hermes/README.md`, and `integrations/hermes/nunchi-gate/plugin.yaml`. Each path uses the exact claim delta and
  accepting owner in plan section Documentation Impact and Freshness:
  integrator-owned cross-surface files go to `v2-integrator`; Claude, Codex,
  and Hermes files go to their named surface owners. No `HANDOFF` row is a
  no-impact finding or a slice-owned documentation escape. The
  `docs/STABILITY.md` handoff MUST include that same closed deterministic retry
  contract as part of the accepted public I-030A stability promise.
- **Inventory invariant**: the spec, plan matrix, and T025 MUST retain the same
  47 exact paths and one disposition per path: 8 `UPDATE`, 17 `NO_IMPACT`, and
  22 `HANDOFF`.
- **Handoff evidence**: `evidence/v2/attention/handoff.md` records the exact
  reviewed paths, dispositions, delta, validation, and reviewer.

## Explicit Exclusions

- No V2 product behavior is implemented by this planning baseline.
- No native event collection, observation buffer, continuation provider,
  participant invocation, harness/adapter binding, send path, or final cutover.
- No margin retirement, release/version decision, promotion, or claim that unit
  tests establish social correctness.
- No deterministic mention, reply, topology, apparent-resolution, class-address,
  relevance, or completion-corroboration social rule.
- No program authority, assignment, dependency acceptance, lifecycle, handoff,
  or acceptance fact enters I-030A, I-010A/B/E, classifier input, operational
  receipts, runtime configuration, or any social-memory structure.
- No edits to 010-owned schemas; requested contract changes return to
  `v2-contract-owner`.
