# Implementation Plan: V2 Core Attention

**Branch**: `v2/core-attention` | **Date**: 2026-07-19 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/030-v2-core-attention/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-core-owner`

**Assigned participant / source**: codex-session-1 — evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/030-v2-core-attention`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

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

**Upstream dependencies**: `010-v2-contract`

**Dependency acceptance mapping**: activation evidence MUST preserve the
declared dependency order in `Accepted dependencies`, ordered
`Dependency commits` entries as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Rejection / rework contract**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

## Summary

During authorized slice implementation, stage one participant-shaped V2
attention engine in the owned core and CLI seams without changing current V1
exports or behavior. It validates I-010A, emits I-010B and
immutable I-010E attention stages, governs suppression, preserves separately
auditable classifier- and margin-DEFER valves, returns trusted preattention-
disabled bypass without a model call, and keeps operational failure separate
with wake as the shared default. The exact handoff feeds 040 and later surface
slices; 110 alone owns atomic integration. This planning baseline creates no
product behavior.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Python standard library, existing OpenAI-compatible
provider transport, and 010-owned V2 schemas

**Storage**: Stateless per-request engine plus off-surface receipt sinks owned
by hosts; no social state store

**Testing**: stdlib `unittest`, deterministic provider fixtures, replay corpus,
multi-model evaluation, and a preregistered downstream canary protocol

**Target Platform**: callable Python core and `nunchi` CLI consumed by all
in-tree harnesses and adapters

**Project Type**: library plus CLI

**Performance Goals**: one logical model judgment per request; zero to two
trusted retries (at most three identical transport attempts); ordinary evidence
reports latency and serialized/token context cost without adding fields to the
closed I-010E attention-stage body. These metrics are descriptive/non-gating:
every record names elapsed time, serialized request/response bytes, provider-
reported input/output tokens or `unavailable`, attempt count, provider/model,
runtime, host/OS, and fixture/corpus identity; no local latency or token
threshold is claimed

**Constraints**: no V1 bridge or translation, no partial V2 publication,
deterministic social rule, hidden fallback, reply prose, request-controlled
operator policy, or send-time judgment

**Scale/Scope**: one engine interface, one CLI seam, one shared transition
policy, and one evidence-backed prompt/model configuration

## Planning Decisions

No slice-local clarification or accepted-dependency contract blocker remains.
Accepted I-010B `@2` now represents the selected zero-inclusive active margin
and is bound by this consumer at
`evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`. The umbrella
program's canonical interface registry nevertheless still declares I-010B and
I-010E as `@1`, while this bound slice correctly consumes their accepted `@2`
versions. The owner-scoped readiness disposition at
`evidence/v2/attention/program-interface-registry-readiness-disposition.md`
records that mismatch as a `NON_BLOCKING_HANDOFF` for this bound slice: it is
neither slice 030's dependency nor a finding in this slice's requirement/task
graph. `v2-program-owner` must still synchronize the canonical registry with
the accepted amendment provenance; `v2-core-owner` records but does not perform
or claim that program-owned edit. Fresh bound analysis independently reports
zero scoped CRITICAL/HIGH findings at
`evidence/v2/attention/analysis-2026-07-19.md`. A separate activation-boundary
failure remains open at
`evidence/v2/attention/dependency-010-amendment-A2-readiness-validator-blocker.md`:
the governance validator still compares dependency `010` with the original
pre-amendment handoff candidate rather than accepted A2 candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`. No immutable activation record may
be written and no `READY` or `ACTIVE` declaration may be made until that
program-level mismatch is resolved.

### Green pre-cutover staging in the existing core and CLI seams

- **Decision**: Add non-current `evaluate_v2` and `attention-v2` entry points in
  `src/nunchi/core.py` and `src/nunchi/cli.py`, and add their V2-only support in
  `src/nunchi/classifiers.py`, `src/nunchi/models.py`, and
  `src/nunchi/schema.py` on the isolated slice branch. Keep current public
  `nunchi.evaluate`, `nunchi admit`, V1 internals, and the complete V1 baseline
  unchanged. Neither staging entry point may call or translate through V1. The
  owner packet gives slice 110 this exact deletion/publication delta: in
  `src/nunchi/core.py`, `src/nunchi/cli.py`, `src/nunchi/classifiers.py`,
  `src/nunchi/models.py`, `src/nunchi/schema.py`, and
  `src/nunchi/__init__.py`, remove the V1 request/verdict handling,
  `require_pass_corroboration`, reply-bearing output, and hidden local
  fallbacks; publish I-030A as public `evaluate`/`admit`; and remove the
  temporary `evaluate_v2`/`attention-v2` names in the same atomic candidate.
- **Rationale**: Program planning requires lane branches to be independently
  green while main remains V1 and slice 110 alone performs assembly/cutover.
  Additive, unreachable-from-current-runtime staging makes I-030A testable by
  downstream lanes without a compatibility bridge or a partially migrated
  public surface.
- **Alternatives considered**: Replacing V1 in place in slice 030 makes the
  mandated full baseline fail; changing current exports early makes V2 appear
  current; a V1-to-V2 adapter violates the selected boundary; a separate V2
  package conflicts with the program's owned `core.py`/`cli.py` interface paths.

### Contract authority and runtime validation

- **Decision**: Consume the accepted I-010A, I-010B, and I-010E schemas without
  editing them; add stdlib runtime validation and audit behavior only in the
  030-owned source seams.
- **Rationale**: Slice 010 owns the public contract, while slice 030 owns
  executable conformance and the I-030A core/CLI process behavior.
- **Alternatives considered**: Forking schema shapes locally or narrowing
  accepted contract cases in runtime code. Either would invent a competing
  contract and block downstream parity.

### One judgment and the dual-valve transition

- **Decision**: Make one participant-shaped classifier call when preattention
  is enabled, preserve classifier-DEFER and margin-DEFER as separate
  safety-widening routes, and keep margin retirement outside this slice's
  schema-cutover decision.
- **Rationale**: This matches the selected social-judgment boundary and keeps
  the protective margin until replay and downstream live evidence earn its
  retirement.
- **Alternatives considered**: Deterministic semantic suppression, a second
  classifier call, immediate margin removal, or treating DEFER as an error.
  Each contradicts the authority design or increases false-silence risk.

### Trusted recoverability capability

- **Decision**: I-030A receives recoverability eligibility as an explicit,
  trusted host capability alongside the selected effective attention policy.
  It is neither room-controlled I-010A data nor a classifier-visible field.
- **Rationale**: Recoverability is required before effective suppression, while
  the selected contract keeps host capability and continuation authority out of
  both the room request and classifier projection.
- **Alternatives considered**: Adding recoverability to I-010A, inferring it
  from coverage or aliases, or treating it as social policy. Each would fork the
  accepted contract or let untrusted/conversational data grant suppression.

### I-030A callable and CLI equivalence seam

- **Decision**: Stage the versioned callable
  `evaluate_v2(request, *, policy, recoverability, classifier_config,
  receipt_sink) -> AttentionDecisionV2`. The request is I-010A; the three
  configuration/capability inputs are host-trusted; recoverability is the exact
  `{participant_id, continuity_scope_id, eligible, source}` shape; the required
  host-owned sink is offered the exact I-010E record with top-level
  `request_id`, `stage: "attention"`, `writer: "attention-engine"`, and the
  mutually exclusive classifier/error/bypass `body` when a valid request ID
  exists; “offered” means the sink is invoked once with that
  record, while “persisted” means the sink's durable-success protocol completed.
  A valid ID without an eligible securely constructed sink makes zero offers;
  sink-invocation failure is one offer with no persistence, operational ERROR,
  wake default, and no second attempt. The return is I-010B. The exact staged
  command is `nunchi attention-v2 --config PATH`; stdin supplies only I-010A,
  while that one operator-owned JSON file supplies the other inputs. For
  identical normalized inputs, parsed CLI stdout and the callable return are
  field-for-field equal, and any offered attention receipt has the same
  full record including body/writer; framing, diagnostics, and exit code are the only surface
  differences.
- **Runtime input contract**: `policy` is the selected
  `EffectiveAttentionPolicy` inventory and validation in spec FR-001;
  `recoverability` is the exact bound four-field capability there;
  `classifier_config` is its exact seven-field trusted provider configuration;
  and `receipt_sink` is the one-call synchronous `None`/exception protocol:
  normal `None` return proves `persisted`; the recognized engine-owned typed
  `ReceiptSinkPersistenceError` may carry only `not-persisted` or `unknown`;
  every unrecognized `Exception`, attribute lookalike, forged invalid typed
  member, or non-`None` return maps to `unknown`; and no raised path may claim
  persistence. The class is defined by I-030A in `src/nunchi/core.py`, validates
  a read-only member at construction, and is recognized with `isinstance`, so
  subclasses are recognized but wrappers and cause/context chains are not
  traversed. `BaseException` control flow propagates without an I-030A result;
  a catching host may route only by waking. Exception text and unrecognized
  attributes never become output, receipt, projection, or log data.
  A sink may raise typed `not-persisted` only for a closed-contract pre-write
  rejection whose semantics guarantee that no durable side effect occurred.
  Generic exceptions, unrecognized typed exceptions, ordinary timeout or
  cancellation exceptions, and every post-dispatch failure are `unknown`.
  `unknown` never authorizes a non-idempotent retry; every such path remains
  subject to the one-offer/no-second-offer rule. Host-control cancellation
  outside `Exception` remains the propagating `BaseException` case above.
  Policy and recoverability participants bind exactly to I-010A `self`, and the
  recoverability scope binds exactly to I-010A `room.continuity_scope_id`.
  Callable inputs arrive normalized. The CLI file is the exact closed FR-001
  `{policy, recoverability, classifier_config, receipt_sink}` object; both the
  file and pre-existing receipt directory are opened descriptor-first without
  following symlinks, then verified as effective-user-owned regular file/
  directory with no group/other permission bits. Duplicate JSON keys reject,
  and there is no inline, flag, environment, or request fallback. Its exact
  receipt adapter is `{type: "exclusive-json-file", directory, source}` and
  descriptor-relative no-follow exclusive-creates the request-ID-hash file with
  mode `0600`, writes one canonical JSON line, flushes, file-fsyncs, closes, and
  directory-fsyncs; it never overwrites or retries. Exclusive-create collision
  reports `unknown` without touching the existing file; other pre-create open
  failure reports `not-persisted` only when the failed exclusive-create
  operation guarantees that no file was created. Every post-create write,
  flush, file-fsync, close, cleanup, or final-directory-fsync failure reports
  `unknown`; descriptor-relative unlink plus directory fsync remains required
  best-effort cleanup but cannot downgrade a post-dispatch outcome to
  `not-persisted`.
  The adapter raises the recognized typed sink failure for those two outcomes;
  the core never trusts duck-typed exception attributes.
  Missing, duplicate, conflicting, unsafe, malformed, or room-supplied sources
  are configuration errors, never merged by implicit precedence. Credentials,
  configuration paths, and sink details never enter projection, stdout, stderr,
  logs, decisions, or receipts.
- **Rationale**: This closes the inter-component seam without inventing a new
  public schema or allowing room data to choose policy, provider, capability,
  credentials, or receipt ownership.
- **Alternatives considered**: A request-embedded policy, a CLI-only engine,
  returning a tuple outside I-010B, or allowing surface-specific audit fields.
  Each would fork the accepted contract or prevent exact parity.

### Receipt-sink exception recognition matrix

The deterministic contract denominator is exactly 23 cases: 12 callable-core
protocol cases plus 11 exclusive-file adapter cases. Each ordinary failure
replaces the pending result with `receipt-sink-failure`, appends the observed
`receipt_persistence` fact, makes no second offer, exposes no exception text,
and uses shared `WAKE`. A normal `None` return preserves the pre-sink result.

| Rows | Stimulus | Required classification |
|---|---|---|
| 1 | normal exact `None` return | `persisted`; preserve the pre-sink result |
| 2 | normal non-`None` return | protocol failure, `unknown` |
| 3–4 | exact `ReceiptSinkPersistenceError` with `not-persisted` / `unknown` | recognized member |
| 5–6 | subclass instance with `not-persisted` / `unknown` | recognized member via `isinstance` |
| 7 | other `Exception` | `unknown` |
| 8 | other `Exception` with lookalike `persistence` attribute | `unknown` |
| 9 | unrecognized wrapper whose inner error or cause/context is recognized | `unknown`; do not traverse |
| 10 | forged/altered recognized instance with an invalid member | `unknown` |
| 11 | sink attempts `ReceiptSinkPersistenceError("persisted")` and therefore raises constructor `ValueError` | unrecognized `Exception`, `unknown` |
| 12 | `BaseException` host-control/process interruption | propagate with no I-030A result; a catching host may route only by waking |
| 13 | exclusive-create collision | typed `unknown`; existing file untouched |
| 14 | other pre-create open failure | typed `not-persisted` |
| 15–18 | write / flush / file-`fsync` / close failure, each followed by successful unlink and directory-`fsync` | typed `unknown`; post-dispatch cleanup does not prove no durable side effect |
| 19–22 | the same four post-create failures, each with unlink or cleanup-directory-`fsync` uncertainty | typed `unknown` |
| 23 | final success-path directory-`fsync` failure after close | typed `unknown` |

T004 and T021 preserve this row numbering and expected classification. T027
requires all 23 deterministic cases, zero focused skips, candidate binding,
and the ordinary evidence record before claiming the sink protocol complete.
This matrix is I-030A `@1` runtime behavior only; it adds no I-010E field and
does not let the response or offered receipt attest its own persistence.

### Trusted attention-budget boundary

- **Decision**: Validate all six closed-policy budget members as positive
  integers. Slice 030 enforces only `attention_max_events` and
  `attention_max_bytes`: `participant_max_events`/`participant_max_bytes`
  belong to slice 040's participant-packet boundary, while
  `fetch_max_events`/`fetch_max_bytes` belong to slice 020's continuation-fetch
  boundary. I-030A does not invoke those downstream consumers, project the
  four values to the classifier, or use them to alter routing. Deterministic
  oracles reject each invalid value before bypass/provider use and prove that
  varying each field across valid positive integers leaves an otherwise
  identical I-030A result and offered attention receipt unchanged.
  After accepted I-010A and binding validation, but before bypass
  or provider routing, count every supplied event kind against
  `policy.attention_max_events` and measure the classifier-visible projection
  against `policy.attention_max_bytes`. The internal projection removes the
  complete host-only `continuation` object and inserts exactly
  `expansion_available: {before, after, around_event}`. Those strict booleans
  copy the three continuation `can_fetch_*` values or are all `false` when no
  continuation exists; every other I-010A field, including coverage, remains
  unchanged. I-030A treats the caller's accepted request and continuation as
  immutable: it builds a separate projection and never mutates or consumes the
  original. Callable evidence compares deep/canonical pre/post snapshots and
  proves the exact caller-held continuation remains available; CLI evidence
  retains a caller-side copy and proves byte/deep equality after evaluation.
  Slice 030 does not invoke the participant host. Projection bytes are the
  UTF-8 length of canonical JSON with
  sorted object keys, no insignificant whitespace, and direct non-ASCII
  characters; provider framing is excluded. Equality is valid. Optional I-010A
  `coverage.max_events` and `coverage.max_bytes` may be absent or no greater
  than the matching trusted caps; a larger declaration or actual overage is
  operational ERROR with zero classifier calls and the normal request-ID-
  bearing receipt rule. I-030A never truncates, reorders, reassembles, or
  recalculates coverage.
- **Rationale**: The one closed trusted policy remains completely validated,
  while each independently configurable budget is enforced only by the owner
  that materializes its data: 030 for attention projection, 040 for the
  participant packet, and 020 for context fetch. Allowing a stricter declared
  coverage budget preserves honest upstream truncation without requiring every
  adapter to assemble to the maximum allowed size.
- **Alternatives considered**: Silently truncating in core, requiring declared
  coverage limits to equal the trusted caps, accepting a looser declared limit
  when the current payload happens to fit, or measuring provider-specific
  request framing. These respectively steal 020 ownership, reject honest
  stricter assembly, permit untrusted widening, or make core/CLI parity depend
  on transport details.

### Retry and sparse-advice boundaries

- **Decision**: Require trusted `max_retries` explicitly and accept only `0..2`
  with no callable or CLI default. In the V2 stdlib provider seam,
  `urllib.error.HTTPError` is classified first: retry only `429` or status
  `500..599`. Also retry outer `urllib.error.URLError` without inspecting its
  `reason`, direct `socket.timeout`/`TimeoutError`, and `OSError` (including
  `ConnectionError`) raised during `urlopen` request execution. Never retry
  any other HTTP status, validation/configuration failure, JSON decoding or
  malformed model output, post-response failure, or an already-complete model
  judgment. Use the fixed deterministic schedule inherited from the existing
  stdlib seam: sleep 0.5 seconds before attempt 2 and 1.0 second before attempt
  3, ignore provider `Retry-After`, and never sleep after success, a terminal
  non-retryable failure, or the final allowed failure. Deterministic oracles
  cover HTTP `429`, `499`, `500`, `599`, and `600`; each named transport
  exception class; exact attempts/sleeps for `max_retries=0|1|2`; identical
  payload/logical request identity; immediate stop after success; and zero
  retries for non-retryable cases. Exhaustion is
  operational ERROR after the full trust boundary, so shared `WAKE` is the
  default, a validated and receiptable `NO_WAKE` policy may override it, and a
  failed override-receipt offer reverts to `WAKE`. Prompt for at most two WAKE annotations of at most 240
  Unicode scalar values; require 100% deterministic/three-family adherence, but
  do not reject or truncate an otherwise I-010B-valid result solely for length
  or item count.
- **Rationale**: The retry limit makes “one logical judgment” reproducible;
  prompt/evidence enforcement preserves brief framing without locally narrowing
  the accepted I-010B schema.
- **Alternatives considered**: Unbounded/operator-arbitrary retry counts,
  immediate retries, provider-controlled `Retry-After`, retrying invalid
  output, a second-vote retry, or a local advice schema cap. These undermine
  bounded deterministic cost, single judgment, or contract ownership.

### Finite transition and social-evidence gates

- **Decision**: Exercise the exact 36-row transition domain in spec SC-002.
  Validate active-margin candidate-suppression evidence before routing. For a
  valid candidate `SUPPRESS`, compute the retained valve exactly as
  `PASS - max(ACK, ASK, SPEAK) <= transition_defer_margin`; equality is
  inside-margin and a strictly greater difference is outside-margin. Apply
  exactly this first-match precedence: suppression disabled, recoverability
  unproven, active-margin uncertainty, then no valve. Candidate `WAKE` always
  uses `none`; classifier `DEFER` always uses `classifier-defer`. Each row
  freezes status, pair, margin status, valve, and override-cause oracles.
  Treat the required three-family social rates as descriptive/non-gating for
  030; missing runs/provenance, advice-criterion failure, or unsafe mechanical
  routing blocks handoff, while mistaken/missed suppression, wake-volume, and
  family-disagreement rates remain explicit limitations and cannot retire the
  margin.
- **Rationale**: The inclusive arithmetic preserves the existing V1 transition
  valve selected for temporary coexistence with classifier-DEFER. A finite
  mechanics denominator supports a real zero-unsafe-row claim without
  pretending that a small stochastic sample proves social correctness.
- **Alternatives considered**: An exclusive comparison, implementation-defined
  boundary behavior, an open-ended “full” matrix, local stochastic pass
  thresholds, or treating mere execution as proof. The first two silently alter
  the retained valve; the others are unreviewable or overclaim evidence.

### Advice evidence rubric

- **Decision**: Count/length and citation resolution are deterministic. For
  every WAKE advice item, `v2-core-owner` records the note, citations, Unicode
  scalar count, and binary findings for supplied-event grounding,
  attention-relevance explanation, absence of a proposed reply/first-person
  draft, and absence of an imperative telling the participant what to say or
  do. Citation resolution is the deterministic first field; the latter three
  semantic fields are explicitly adjudicated by `v2-core-owner`, not runtime
  social rules. Handoff requires every field to pass across deterministic and
  required three-family records.
- **Rationale**: This makes the evidence gate reproducible without narrowing
  I-010B or turning deterministic validation into a conversational judge.
- **Alternatives considered**: An undefined “brief” review, model self-grading,
  or runtime rejection based on semantic prose. None supplies an auditable
  owner decision within the accepted contract boundary.

### Receipt and performance evidence boundary

- **Decision**: Emit only the accepted closed I-010E attention-stage bodies.
  Record latency and serialized/token-cost measurements in the exact ordinary
  evaluation evidence targets, correlated by request ID where applicable, and
  never as undeclared I-010E fields.
- **Rationale**: Slice 030 must prove performance without forking the accepted
  receipt schema or weakening its `additionalProperties: false` boundary.
- **Alternatives considered**: Adding local receipt fields, hiding metrics in
  error detail, or omitting performance measurements. The first two violate the
  contract; the last would leave the performance goal unproven.

### Accepted contract amendment resolution

- **Decision**: Consume accepted I-010E `AttentionReceiptV2@2` at exact
  amendment candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`. Its
  trusted-bypass body requires `classifier_not_invoked: true`, cause
  `preattention-disabled`, and non-empty `policy_provenance`; its classifier-
  outcome body requires `policy_provenance`; its operational-error body
  represents only the explicit operator override as paired
  `wake_action: "NO_WAKE"` plus `policy_provenance`, with the shared default
  `WAKE` path omitting the pair. Bind that version through
  `evidence/v2/attention/dependency-010-amendment-A1-acceptance.md` while
  retaining the original `@1` acceptance and blocker as immutable history.
- **Rationale**: The versioned 010-owned amendment resolves both selected-design
  obligations without a local field, free-text convention, or misuse of
  classifier identity or `routing_audit.margin_source`.
- **Alternatives considered**: Continuing to block after exact upstream
  acceptance, editing the schema in slice 030, omitting provenance, or hiding
  it in `error.detail`. Each either ignores current accepted contract truth or
  violates authority and ownership.

Amendment A1 remains accepted for exactly those receipt changes. It does not
itself resolve the later-discovered I-010B zero-margin conflict or update the
program owner's canonical interface registry.

- **Decision**: Consume accepted I-010B `AttentionDecisionV2@2` at exact A2-R1
  correction candidate `26a6b531fa146ba1f1f5fcd1c4d191041b141301`, bound by
  this consumer at
  `evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`. Its applied
  `routing_audit.effective_margin` domain is finite inclusive `[0,1]`; every
  other field, valve, pairing, and cross-field constraint is retained.
- **Rationale**: The versioned 010-owned amendment exactly resolves the
  selected-policy/decision-audit representation conflict and permits the
  retained inclusive transition at zero without a local schema edit or hidden
  special case.
- **Alternatives considered**: Rejecting design-valid zero, changing the
  inclusive comparison, omitting the applied audit, or widening I-010B inside
  slice 030. Each would contradict the selected design or dependency ownership.

The program-owned interface registry still requires I-010B/I-010E version
synchronization. That remains a named owner handoff and is not treated as
completed, but it does not gate this slice's exact dependency acceptance or
readiness analysis.

### Bypass, operational error, and CLI parity

- **Decision**: Return trusted preattention-disabled bypass with zero classifier
  calls. When a valid request ID and eligible sink exist, offer the exact
  I-010E `@2` attention body
  `{classifier_not_invoked: true, cause: "preattention-disabled",
  policy_provenance: <non-empty trusted policy source>}` with none of the
  mutually exclusive classifier-outcome or error fields. Keep operational
  error as its own tagged branch, and expose the exact
  0/1/2/3 CLI process contract recorded below. The shared wake default remains
  mandatory until the complete operator configuration is descriptor-secure,
  closed-shape and value valid, single-source, and exactly bound to a schema-
  valid request. No config-derived sink is eligible until the outer config file
  itself passes descriptor security and duplicate-free JSON parsing. Raw or
  partially validated `NO_WAKE` has no authority; only after that source
  boundary may a request-ID-bearing configuration/request/binding error be
  written through an independently secure sink, without the I-010E override
  pair. Missing, unreadable, unsafe, invalid-JSON, or duplicate-key config
  constructs no sink and emits no receipt. Once the
  trust boundary passes, `NO_WAKE` applies to later budget, provider, malformed-
  model, or runtime errors only when the required override receipt can be
  offered. Every sink-invocation failure uses the shared `WAKE` default because
  its override receipt did not persist; both `not-persisted` and `unknown`
  persistence outcomes reject silence authority.
- **Rationale**: Bypass must not fabricate a model result, errors must not
  impersonate social judgments, malformed configuration must not gain silence
  authority from one parseable member, and callable-core/CLI equivalence is the
  shared consumer seam.
- **Alternatives considered**: Converting bypass to WAKE, converting failures
  to a social disposition, honoring `NO_WAKE` before complete validation and
  binding, retaining `NO_WAKE` after its required receipt fails, or emitting
  diagnostics and response payloads on the same stream. These lose provenance,
  grant unreceipted silence authority, or break deterministic host handling.

### Documentation ownership

- **Decision**: Update the 030-owned attention and evaluation references, record
  evidence-backed no-impact findings for exact unaffected files, and route one
  exact claim delta per shared or downstream-owned file.
- **Rationale**: Component truth can land with the slice while global current
  state remains integrator-owned until atomic cutover.
- **Alternatives considered**: Grouped path dispositions, generic directory
  review, premature global V2-current wording, or silent deferral. Each fails
  the documentation-freshness gate.

## Constitution Check

| Gate | Status | Planning evidence |
|---|---|---|
| Selected V2 boundary | PASS | Engine decides wake attention only and never composes a participant move. |
| Human-shaped judgment | PASS | One sparse participant-shaped model judgment owns every social suppression. |
| Truthful identity/observation | PASS | I-010A facts and unknowns are consumed without inventing roster or handled state. |
| Attention/contribution split | PASS | Engine returns attention; 040 and surface slices own normal participant turns. |
| Atomic parity contract | PASS | Non-current `evaluate_v2`/`attention-v2` stage I-030A without calling V1; the complete V1 baseline stays green, and 110 alone removes V1 and staging names while publishing I-030A in one atomic candidate. |
| Evidence before claims | PASS | Mechanics, replay, multi-model, canary, and margin evidence targets are separate. |
| Control-plane boundary | PASS | This directory contains planning Markdown only. |
| Single owner and slice lifecycle | PASS | `v2-core-owner` owns I-030A; tasks execute only while the declaration and lifecycle evidence establish `ACTIVE`, and remain `DORMANT` at `PLANNED`. |
| Accepted receipt compatibility | PASS | Accepted I-010E `@2` requires classifier policy provenance and separately receipts only paired `NO_WAKE` plus provenance; this consumer accepted exact amendment candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`. |
| Selected zero-width margin / accepted I-010B | PASS | Accepted I-010B `@2` represents applied `effective_margin: 0`; this consumer accepted exact A2-R1 candidate `26a6b531fa146ba1f1f5fcd1c4d191041b141301`. |
| Program canonical interface registry | HANDOFF | `v2-program-owner` must synchronize I-010B/I-010E to accepted `@2`; the mismatch is explicitly scoped as a non-blocking owner handoff for slice 030 and is not claimed complete. |

Post-design re-check: PASS for the bound slice. Slice-owned contract questions
and exact dependency acceptance are resolved; the separately owned canonical
program-registry mismatch remains an explicit non-blocking handoff. Fresh bound
analysis is complete, but the separate dependency-validator mismatch recorded
at
`evidence/v2/attention/dependency-010-amendment-A2-readiness-validator-blocker.md`
prevents a truthful activation record and keeps the slice `PLANNED`.
Because this is a planning-only revision, no `data-model.md`, local contract,
quickstart, schema, test, corpus, evidence payload, or product documentation is
created here.

## Slice Interfaces

### Consumes

- `I-010A AttentionRequestV2@1` at `schemas/v2/attention-request.schema.json`.
- `I-010B AttentionDecisionV2@2` at `schemas/v2/attention-decision.schema.json`,
  accepted by this consumer at
  `evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`.
- `I-010E AttentionReceiptV2@2` at `schemas/v2/attention-receipt.schema.json`,
  accepted by this consumer at
  `evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`.

### Produces

- `I-030A AttentionEngineV2@1` at `src/nunchi/core.py` and
  `src/nunchi/cli.py`, with provider/prompt support in
  `src/nunchi/classifiers.py` and runtime validation/audit support in the
  existing `src/nunchi/models.py` and `src/nunchi/schema.py` seams. Its initial
  `@1` runtime surface includes `ReceiptSinkPersistenceError`; because I-030A
  has not yet been produced or accepted, this clarification is not a version
  bump and changes no 010-owned schema.

## Integration Strategy

**Integration order**: accepted 010 commit → red core/CLI contract tests →
participant-shaped classifier result or trusted bypass → trusted host
recoverability capability plus governed dual-valve route → tagged error and
immutable attention-stage receipt → replay/multi-model evidence plus
downstream canary protocol → downstream handoff.
Slice 020 runs in parallel; 040 begins only after both handoffs.

**Worktree/branch**: isolated worktree `.worktrees/v2-core-attention/` on branch
`v2/core-attention`

**Handoff to**: `v2-wake-owner`, `v2-hermes-owner`, `v2-claude-owner`,
`v2-codex-owner`, `v2-adapters-owner`, `v2-security-owner`, and
`v2-integrator`

**Conflict ownership**: 030 owns core, CLI, classifier prompt/provider, and
attention-policy files named here until handoff. It does not edit 010 schemas,
020 observation, 040 participant hosting, or surface integration files. 110
alone resolves final integration conflicts.

The bypass boundary is explicit: slice 030 proves only the accepted I-010B
`status: bypass`, `cause: "preattention-disabled"` branch and zero classifier
calls, plus the separately accepted I-010E `@2` bypass body
`classifier_not_invoked: true`, the same cause, and required non-empty trusted
`policy_provenance`. It emits no
ParticipantWakeV2 and invokes no participant host. The packet gives
`v2-wake-owner` the exact accepted branch; slice 040 must independently accept
it, map it to ParticipantWakeV2 wake source `PREATTENTION_BYPASS`, and pass a
downstream acceptance test for that mapping.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S04 False-suppression scars | Core replay | No deterministic semantic suppressor; model/effective decisions remain inspectable. | `evidence/v2/attention/s04-suppression-scars/results.jsonl` |
| S05 Governed suppression | Core policy matrix | Hard stop requires enabled delegation, recoverability, valid transition evidence, and revocable provenance. | `evidence/v2/attention/s05-governed-suppress.jsonl` |
| S06 WAKE/bypass contribution handoff | Core-neutral decision fixture | WAKE carries only grounded optional advice; trusted preattention-disabled input produces exact I-010B `status: bypass`, `cause: "preattention-disabled"` with zero model calls. The recorded handoff requires slice 040 to map the accepted branch to ParticipantWakeV2 source `PREATTENTION_BYPASS` and test that mapping; 030 emits no ParticipantWakeV2. | `evidence/v2/attention/core-cli-parity.jsonl` |
| S08 Dual DEFER valves | Three-family replay | Classifier-DEFER and margin-DEFER remain separate; either only widens attention across incumbent Gemini 3.1 Flash Lite, frontier GPT-5.5, and open-weight Qwen3. Live canary execution is downstream. | `evidence/v2/attention/s08-defer-transition/results.jsonl`; `evidence/v2/attention/model-comparison/results.jsonl` |
| S09 Operational error | Core and CLI | Every validation/provider/runtime failure remains ERROR with wake default and separate override audit. | `evidence/v2/attention/core-cli-parity.jsonl` |
| S16 No registry or ledger | Boundary and replay | Engine consumes no prior outcome, obligation, handled/open, roster, or permission state. | `evidence/v2/attention/s04-suppression-scars/results.jsonl` |
| 030-CLI Core/CLI parity | Core and CLI | Equivalent input/config yields equivalent tagged decision and audit. | `evidence/v2/attention/core-cli-parity.jsonl` |

Deterministic checks target `tests/v2/attention/`, replay and model-comparison
assets `evals/v2/attention/`, and run records `evidence/v2/attention/`.

Every aggregate JSONL row MUST carry its canonical `scene_id` (or
`030-CLI` for the slice-local contract scene). The manifest at
`evidence/v2/attention/README.md` maps scenes, records, commands, model runs,
and the downstream-owned canary protocol explicitly.
The three-family attempts live at
`evidence/v2/attention/model-comparison/results.jsonl`; the preregistered but
not-yet-executed protocol lives at
`evidence/v2/attention/defer-canary/protocol.md`.
`python3 -m evals.v2.attention.runner --all` dispatches the exact
`evals/v2/attention/defer-transition/analyze.py` file by filesystem path,
includes its S08 output in the aggregate result, and fails if that analyzer is
not executed successfully; the hyphenated evidence-family directory is not
treated as an importable Python package.

The exact model-comparison matrix is every committed row in
`evals/v2/attention/suppression-scars/cases.jsonl` crossed with the incumbent
Gemini 3.1 Flash Lite, frontier GPT-5.5, and open-weight Qwen3 families (unless
Zoe durably substitutes a family). Before any provider request, committed
`evals/v2/attention/model-selection.json` maps those three families one-to-one
to exact provider model IDs plus provider, endpoint class, catalog/source
evidence, selection date, and `v2-core-owner` review. A missing/uncommitted,
duplicate, extra, or result-mismatched mapping blocks execution; changing an
exact ID requires a new pre-run manifest commit and invalidates older results.
Each case preregisters `case_id`, canonical
`scene_id`, contract-valid `request`, and `expected_attention` as `ATTEND` or
`NOT_ATTEND`. Mistaken suppression is effective `SUPPRESS` over `ATTEND` cases;
missed suppression is non-`SUPPRESS` over `NOT_ATTEND` cases; wake volume is
non-`SUPPRESS` over all cases. Direct classifier DEFER and margin DEFER are
reported separately but both count as non-suppression. Family disagreement is
case IDs with more than one direct classifier disposition across the three
valid family results divided by all case IDs. Missing or duplicate family/case
results make the matrix incomplete and block handoff rather than changing a
denominator.

## CLI Process Contract

| Input/result class | stdout | stderr | Exit |
|---|---|---|---|
| Valid request; `status: ok` or trusted `status: bypass` | Exactly one tagged JSON value | No response payload | `0` |
| JSON parsed; config missing/unreadable/unsafe/malformed, sink construction fails, request schema invalid, or trusted attention-budget validation fails | Exactly one tagged `status: error` JSON value with honest receipt-persistence fact | No response payload | `3` |
| Provider/runtime/malformed-model or constructed-sink invocation failure | Exactly one tagged `status: error` JSON value with `not-persisted` or `unknown` when applicable | No response payload | `1` |
| Input unreadable or invalid JSON | Empty | Diagnostic only | `2` |

Precedence is fixed: unreadable/invalid stdin JSON wins and exits 2 without
loading config; after any JSON value is parsed, config security/shape and sink
construction precede request-schema validation, and trusted attention-budget
validation follows schema/binding validation before bypass or classifier use,
so config failure wins a combined failure and all such validation failures exit
3. Request-schema/configuration/binding failure precedes the full trusted-policy
boundary and therefore always uses wake default. A valid sink records such an
error only when a valid request ID is assignable. For a config error, the outer
config source must first pass descriptor security and duplicate-free JSON
parsing; only then may its `receipt_sink` member independently pass its closed
shape and directory-security checks. Missing, unreadable, unsafe, invalid-JSON,
or duplicate-key config never directs a write. The resulting default-path
receipt omits both override fields. Trusted-budget validation
occurs after the boundary and may therefore use a validated `NO_WAKE` policy.
Otherwise no receipt or ID is fabricated.

I-030A generates a stable, closed code/cause-detail set without narrowing the
schema-level open I-010B `code`: `configuration-error` / `trusted configuration
invalid`, `request-validation-error` / `attention request invalid`,
`attention-budget-error` / `attention budget exceeded`, `provider-timeout` /
`attention provider timed out`, `provider-error` / `attention provider failed`,
`malformed-model-output` / `classifier output invalid`, `invalid-transition` /
`attention transition invalid`, `invalid-legacy-confidence` / `legacy
confidence vector invalid`, `runtime-error` / `attention runtime failed`, and
`receipt-sink-failure` / `attention receipt sink failed`. An offered I-010E
error record carries only its exact cause pair because it cannot attest its own
persistence. After the sole sink attempt, the returned I-010B error appends
exactly `; receipt_persistence=<persisted|not-persisted|unknown>` to the safe
cause detail. A sink failure replaces the returned cause with
`receipt-sink-failure` and its observed non-persistence value; it never triggers
a second receipt attempt and always uses the shared `WAKE` default, even when
the previously validated policy selected `NO_WAKE`. No fixed detail exposes a
path, credential, provider payload, configuration value, or receipt provenance.

Core and CLI must also prove that host-only continuation handles, binding
tokens, cursors, and expiry values never enter the classifier projection. The
model sees the exact top-level
`expansion_available: {before, after, around_event}` strict-boolean object only;
all values are false without continuation and otherwise copy the three
continuation `can_fetch_*` flags. The original bound I-010A continuation
capability remains available downstream to 040 because I-030A neither mutates
nor consumes the caller-owned request. Core tests compare deep/canonical
snapshots before and after evaluation; CLI tests retain and compare a caller-
side byte/deep copy. I-030A does not invoke the host or consume I-010D fetch
request/page objects.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/030-v2-core-attention/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Ordinary repository targets for authorized slice implementation

```text
src/nunchi/
├── core.py
├── cli.py
├── classifiers.py
├── models.py
└── schema.py

tests/v2/attention/
├── __init__.py
├── helpers.py
├── test_advice_and_errors.py
├── test_core_cli_contract.py
└── test_transition_policy.py

evals/v2/attention/
├── runner.py
├── model-selection.json
├── core-cli/cases.jsonl
├── defer-transition/analyze.py
├── governed-suppression/cases.jsonl
└── suppression-scars/cases.jsonl

evidence/
├── README.md
├── verdict-suite/README.md
└── v2/attention/
    ├── README.md
    ├── core-cli-parity.jsonl
    ├── defer-canary/protocol.md
    ├── handoff.md
    ├── model-comparison/results.jsonl
    ├── s04-suppression-scars/results.jsonl
    ├── s05-governed-suppress.jsonl
    ├── s08-defer-transition/results.jsonl
    └── verification.md

docs/
├── attention/v2.md
├── contracts/verdict-suite-data-model-v1.md
├── contracts/verdict-suite-requirements-v1.md
├── evaluations/verdict-suite.md
└── evaluations/verdict-suite-runner.md
```

**Structure Decision**: Evolve the current shared core/CLI seams on an isolated
slice branch. Do not introduce an alternate V2 executable or compatibility
layer that could survive the atomic cutover.

## Ordinary Repository Targets

| Artifact class | Exact ordinary target path | Owning task/story |
|---|---|---|
| Attention orchestration | `src/nunchi/core.py` | T007, T012 / US1–US2 |
| Classifier/provider/prompt | `src/nunchi/classifiers.py` | T006 / US1 |
| Runtime models and audit | `src/nunchi/models.py` | T008, T013 / US1–US2 |
| Runtime validation/policy | `src/nunchi/schema.py` | T011, T018 / US2–US3 |
| CLI process seam | `src/nunchi/cli.py` | T019 / US3 |
| Test package and helpers | `tests/v2/attention/__init__.py`, `tests/v2/attention/helpers.py` | T001 |
| Core/CLI contract tests | `tests/v2/attention/test_core_cli_contract.py` | T002 / US3 |
| Transition-policy tests | `tests/v2/attention/test_transition_policy.py` | T003 / US2 |
| Advice/bypass/error/projection tests | `tests/v2/attention/test_advice_and_errors.py` | T004 / US1–US3 |
| Replay runner | `evals/v2/attention/runner.py` | T005 / US1–US3 |
| Suppression-scar corpus and exact pre-run model selection | `evals/v2/attention/suppression-scars/cases.jsonl`, `evals/v2/attention/model-selection.json` | T009 / US1 |
| Governed-suppression corpus | `evals/v2/attention/governed-suppression/cases.jsonl` | T014 / US2 |
| DEFER analysis | `evals/v2/attention/defer-transition/analyze.py` | T015 / US2 |
| Core/CLI corpus | `evals/v2/attention/core-cli/cases.jsonl` | T021 / US3 |
| S04/S16 results | `evidence/v2/attention/s04-suppression-scars/results.jsonl` | T010 / US1 |
| S05 results | `evidence/v2/attention/s05-governed-suppress.jsonl` | T016 / US2 |
| S08 results | `evidence/v2/attention/s08-defer-transition/results.jsonl` | T017 / US2 |
| S06/S09/030-CLI parity results | `evidence/v2/attention/core-cli-parity.jsonl` | T022 / US3 |
| Three-family comparison | `evidence/v2/attention/model-comparison/results.jsonl` | T023 / cross-cutting |
| Downstream canary protocol | `evidence/v2/attention/defer-canary/protocol.md` | T024 / cross-cutting |
| Handoff packet input | `evidence/v2/attention/handoff.md` | T020, T025–T026 / US3 and cross-cutting |
| Evidence/command manifest | `evidence/v2/attention/README.md` | T026 / cross-cutting |
| Candidate verification record | `evidence/v2/attention/verification.md` | T027 / cross-cutting |
| Global evidence index documentation | `evidence/README.md` | T025 / cross-cutting |
| V1 evidence index documentation | `evidence/verdict-suite/README.md` | T025 / cross-cutting |
| Attention/operator guide | `docs/attention/v2.md` | T025 / cross-cutting |
| V1 scar data-model reference | `docs/contracts/verdict-suite-data-model-v1.md` | T025 / cross-cutting |
| V1 scar requirements reference | `docs/contracts/verdict-suite-requirements-v1.md` | T025 / cross-cutting |
| V1 evaluation overview | `docs/evaluations/verdict-suite.md` | T025 / cross-cutting |
| V1 evaluation runner guide | `docs/evaluations/verdict-suite-runner.md` | T025 / cross-cutting |
| Consumed I-010A schema | `schemas/v2/attention-request.schema.json` | Read-only 010-owned dependency |
| Consumed I-010B schema | `schemas/v2/attention-decision.schema.json` | Read-only 010-owned dependency |
| Consumed I-010E schema | `schemas/v2/attention-receipt.schema.json` | Read-only 010-owned dependency |

## Candidate Verification Commands

T027 runs this exact baseline against the tested implementation tree and records
that tree's full parent commit in `evidence/v2/attention/verification.md`; any
failure blocks convergence:

```sh
python3 scripts/check_governance.py --check-cli
python3 -m unittest
python3 -m unittest discover -s tests/v2/attention -p 'test_*.py'
python3 -m evals.v2.attention.runner --all
python3 -m evals.verdict_suite.runner --list
git diff --check <activation-start>..HEAD
```

Here `<activation-start>` is the full immutable starting commit copied from
`evidence/v2/attention/slice-activation.md`; candidate and packet reruns use
that same commit as the lower bound so committed whitespace defects are visible.
Activation freezes the starting commit's exact root test/skip counts and the
ordered tracked pre-030 test-file inventory plus content hash outside
`tests/v2/attention/`, and the exact allowed 030 path set. T001's package marker
makes the attention suite visible to root discovery. At tested tree, candidate,
and packet commits, the commit-range whitespace check and verification reject
any changed pre-030 test byte, adapter/
harness or 010-owned `schemas/v2/` contract edit, deleted or renamed pre-030
test, new skip, out-of-scope
path, or count mismatch. The focused suite must have zero skips, root skips must
equal the frozen activation skip count, and root count must equal the frozen
activation root count plus the focused attention-suite count.

The T027 commit contains that verification record but does not try to name its
own SHA. The later convergence gate designates the T027 commit as the lifecycle
candidate, reruns the same commands at that exact candidate, and records its SHA
and results in `slice-candidate.md` from a later packet commit. The handoff gate
reruns the full baseline at the packet commit and records that distinct packet
commit/results in `slice-handoff.md`; no file is required to name the commit
that contains itself. The three-family live provider attempts remain separately
recorded by T023 and are not hidden inside the deterministic baseline.

## Documentation Impact and Freshness

| Claim surface | Exact reviewed ordinary path | Disposition | Owning task/lane | Validation, rationale, or exact handoff delta |
|---|---|---|---|---|
| Global product and CLI state | `README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at atomic cutover replace V1 verdict/core/CLI claims and examples with accepted I-030A `SUPPRESS`/`WAKE`/`DEFER`, trusted bypass, separate ERROR, dual-valve, 0/1/2/3 process behavior, and the closed receipt-sink persistence-failure rule while preserving verification-pending wording. |
| Repository agent guidance | `AGENTS.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; in the atomic candidate replace the V1-implementation/current-command claims with state-aware accepted-V2/verification-pending guidance, preserve the governance and owner boundaries, and make the eventual `CUTOVER_VERIFIED` current-state interpretation explicit without requiring a product-code edit. |
| Claude execution guidance | `CLAUDE.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; in the atomic candidate replace V1 runtime/config/CLI smoke guidance with accepted I-030A, trusted bypass, ERROR, receipt-sink typed/unrecognized failure handling, and 0/1/2/3 commands while preserving verification-pending wording and the exact-main gate. |
| Global evidence index | `evidence/README.md` | `UPDATE` | T025 / `v2-core-owner` | Add the exact `evidence/v2/attention/` component-record scope, commands/manifest link, evidence grade, candidate binding, and explicit non-cutover/non-current boundary while preserving the immutable/history rules; validate every link and claim against the candidate. |
| V1 verdict-suite evidence index | `evidence/verdict-suite/README.md` | `UPDATE` | T025 / `v2-core-owner` | Preserve every historical V1 run record and reproduction boundary, add the exact 030 scar/transition role and V2 result links, and validate current-classifier wording and commands without presenting V1 evidence as V2 social proof. |
| Slice-030 evidence and command manifest | `evidence/v2/attention/README.md` | `UPDATE` | T025–T026 / `v2-core-owner` | Create the exact scene-to-record and command manifest with candidate binding, consumed/produced interface versions, the 23-row receipt-sink classification evidence, deterministic/replay/model evidence links, evidence grades, rejected claims, and explicit non-current/non-cutover limitations; validate every command, path, link, count, and claim against the exact candidate and packet. |
| Accepted contract evidence manifest | `evidence/v2/contract/README.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale re-reviewed after the sink clarification: the 010-owned manifest records accepted I-010B/I-010E `@2` schema provenance and commands, while `ReceiptSinkPersistenceError` is an I-030A-only runtime protocol with no 010 field or ownership change. Validate versions and links, then record the unchanged review in handoff evidence. |
| Release history | `CHANGELOG.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; add the exact accepted 030 commit, breaking core/CLI and receipt-sink exception contract delta, active-margin status, evidence links, and limitations in the atomic cutover entry. |
| Installation and executable claims | `docs/INSTALL.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; replace V1 `nunchi-channel`/configuration assumptions with the accepted V2 CLI, model/policy inputs, installed-runtime provenance, and no-V1-residue instructions at cutover. |
| Public stability contract | `docs/STABILITY.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; replace the V1 request/verdict/process promise with accepted I-010A/B/E plus I-030A, including the host-visible `ReceiptSinkPersistenceError` recognition boundary and the closed 0.5-second/1.0-second retry cadence that ignores provider `Retry-After` and never sleeps after success or a terminal/final failure, while retaining the active transition margin and breaking-version boundary. |
| Cross-adapter reference | `docs/adapters.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; apply the exact common I-030A lifecycle, bypass/error routes, dual-DEFER requirements, and sink failure-to-wake mapping to the cutover-wide adapter table without claiming unproven surface parity. |
| Selected-design diagrams | `docs/architecture/v2-selected-design.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at cutover update I-030A implementation/evidence status and diagram-linked claims from selected target to accepted verification-pending candidate, then to verified current only after post-merge proof. |
| V1 archive index | `docs/archive/v1/README.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the frozen archive index already says its children are historical and not current instructions; record exact review unchanged in the attention handoff evidence. |
| Archived V1 classifier contract | `docs/archive/v1/admission-classifier/contract.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner makes the V1 fields and commands archival evidence, not a V2 integration claim; record the review in handoff evidence. |
| Archived V1 classifier data model | `docs/archive/v1/admission-classifier/data-model.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner remains accurate after 030; record the review in handoff evidence. |
| Archived V1 classifier quickstart | `docs/archive/v1/admission-classifier/quickstart.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the archived-command warning prevents it from acting as current runnable guidance; preserve it unchanged and record the review. |
| Archived V1 core/CLI contract | `docs/archive/v1/core-cli/contract.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner keeps the replaced V1 process contract as evidence; record the review in handoff evidence. |
| Archived V1 core/CLI data model | `docs/archive/v1/core-cli/data-model.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner keeps the replaced V1 model as evidence; record the review in handoff evidence. |
| Archived V1 core/CLI quickstart | `docs/archive/v1/core-cli/quickstart.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the archived-command warning already prevents current-use ambiguity; record the review in handoff evidence. |
| Channel-adapter V1 contract | `docs/contracts/channel-adapter-v1.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at atomic cutover mark the V1 gate/result contract superseded and route readers to the accepted V2 lifecycle and final adapter guidance. |
| Accepted V2 public contracts | `docs/contracts/nunchi-v2.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale re-reviewed after the sink clarification: slice 010 owns this schema reference, while the host-visible typed failure belongs only to the I-030A runtime seam and changes no I-010A/B/E field or truthful V1-current caveat. Validate candidate conformance and record the unchanged finding. |
| V1 verdict-suite data model | `docs/contracts/verdict-suite-data-model-v1.md` | `UPDATE` | T025 / `v2-core-owner` | Preserve the V1 evidence schema, add its exact S04/S08 regression/transition role and V2 result links, then validate terminology and links against the candidate. |
| V1 verdict-suite requirements | `docs/contracts/verdict-suite-requirements-v1.md` | `UPDATE` | T025 / `v2-core-owner` | Preserve historical ground truth, map the applicable scars to S04/S16 and dual-valve evidence, and validate requirement/result links. |
| V1 verdict-suite runner guide | `docs/evaluations/verdict-suite-runner.md` | `UPDATE` | T025 / `v2-core-owner` | Keep V1 commands runnable, name their bounded regression role, add exact V2 runner/result commands, and validate every retained/new command. |
| V1 verdict-suite evidence guide | `docs/evaluations/verdict-suite.md` | `UPDATE` | T025 / `v2-core-owner` | Distinguish historical V1 quality evidence from 030 mechanics/social evidence, link exact S04/S05/S08/model-comparison records, and validate claims and links. |
| Governance execution guide | `docs/governance/execution-spine.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: 030 follows but does not change the already-current workflow/lifecycle contract; planning and later component implementation create no new governance rule. Record exact review in handoff evidence. |
| General integration guide | `docs/integration.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; replace the V1 verdict, fail-policy, request, output, provider, and CLI wiring with accepted I-030A behavior, including the exact `ReceiptSinkPersistenceError`/unrecognized exception protocol and shared-wake fallback, only in the atomic cutover. |
| Generic loader example | `examples/loader-snippet.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at atomic cutover replace `nunchi-channel`, environment-test-result, V1 request/verdict/run-shape, fail-policy, and silent-token instructions with the accepted V2 operator config, I-010A stdin, I-030A tagged result/exit behavior, typed sink failure example, unrecognized-failure wake fallback, trusted bypass/ERROR, and direct act-or-silence flow; validate the example end to end. |
| Generic host runnable demo | `examples/generic_host_demo.py` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at atomic cutover replace the V1 adapter, PASS/ACK/ASK/SPEAK fixture, fail-open, `silent`/sentinel, and run-shape flow with accepted I-010A/I-030A configuration, tagged result, receipt-sink failure handling, and direct act-or-silence behavior; execute both offline and configured-provider paths with the assembled candidate. |
| Read-the-room runnable demo | `examples/read_the_room_demo.py` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at atomic cutover replace the V1 adapter, verdict/silent-pass sentinel, loose agent identity, and pinned PASS fixture with accepted exact-self I-010A, I-030A result/bypass/ERROR behavior, and direct act-or-silence routing; execute both offline and configured-provider paths with the assembled candidate. |
| Open-floor V1 profile | `profiles/open-floor.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; remove this PASS/ACK/ASK/SPEAK and `pinned_rules` profile from the current product and all current links in the atomic cutover, because I-010A/I-030A accepts no governance-profile input and the sparse participant-shaped prompt must not become a deterministic social rulebook. Git history remains the V1 record. |
| Hermes display-patch guide | `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the optional channel-scoped display override controls operational UI chatter, not attention judgment or I-030A; record the exact review unchanged. |
| Hermes display-patch test plan | `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: resolver and gateway-display checks are independent of the core attention contract; record the exact review unchanged. |
| Attention/operator reference | `docs/attention/v2.md` | `UPDATE` | T025 / `v2-core-owner` | Create the exact component guide; document the typed/unrecognized/non-`None`/`BaseException` sink taxonomy, 23-row evidence denominator, shared-wake rule, policy, bypass, error/exit semantics, the fixed 0.5-second/1.0-second retry cadence, ignored provider `Retry-After`, no-sleep terminal boundaries, active margin, prompt/model provenance, examples, links, and commands against the exact candidate without claiming atomic cutover. |
| Claude DEFER evaluation | `integrations/claude-code/DEFER_EVAL.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-claude-owner`; replace V1 uncertain-PASS terminology with the exact classifier-DEFER/margin-DEFER transition, reuse criteria, and downstream canary protocol after accepting I-030A. |
| Claude Code integration | `integrations/claude-code/README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-claude-owner`; migrate the V1 wake gate to I-030A, distinguish bypass/ERROR/DEFER, bind its host sink to the typed/unrecognized failure and shared-wake protocol, preserve one judgment and act-or-silence, and update config/evidence claims only with its surface candidate. |
| Claude operator configuration example | `integrations/claude-code/nunchi-gate.env.example` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-claude-owner`; replace V1 fail-open wrapper, loose identity/peer-roster, and `nunchi-channel` assumptions with the accepted V2 descriptor-secure operator-policy source, exact-self binding, I-030A CLI, and surface-owned migration guidance. Validate the runnable example with the Claude slice candidate. |
| Claude transport patch | `integrations/claude-code/transport-patch/README.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the allowlisted peer-bot transport patch changes event delivery, not the attention engine contract; exact review remains downstream transport evidence and is recorded unchanged. |
| Codex integration | `integrations/codex/README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-codex-owner`; replace V1 verdict, inbound/outbound re-gate, receipt/config, and wake claims with accepted I-030A bypass/ERROR/dual-DEFER, typed/unrecognized sink failure handling, and direct act-or-silence behavior in the Codex slice. |
| Codex MCP wiring | `integrations/codex/nunchi-codex/.mcp.json` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the plugin-local MCP server/tool wiring contains no V1 verdict, I-030A field, schema version, policy/default, or receipt-body claim; the generic `get_nunchi_receipts` tool name remains valid. Validate JSON and installed wiring, then record the candidate-specific unchanged review. |
| Codex plugin metadata | `integrations/codex/nunchi-codex/.codex-plugin/plugin.json` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-codex-owner`; replace the public wake-and-send gating and outbound-send-guard descriptions with the accepted one-judgment wake admission plus direct act-or-silence lifecycle. Validate JSON, plugin metadata, and installed descriptions with the Codex slice candidate. |
| Codex hook manifest | `integrations/codex/nunchi-codex/hooks/hooks.json` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-codex-owner`; replace the V1 prompt-admission plus `PreToolUse` send-gate topology with the accepted single preattention judgment and direct act-or-silence lifecycle, removing send-time social reclassification. Validate manifest syntax and installed hook behavior with the Codex slice candidate. |
| Hermes integration | `integrations/hermes/README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-hermes-owner`; replace V1 `nunchi-channel` verdict/fail-open/config/receipt semantics with accepted I-030A, bypass/ERROR, dual-DEFER, typed/unrecognized sink failure handling, and immutable attention-stage facts in the Hermes slice. |
| Hermes dashboard manifest | `integrations/hermes/nunchi-gate/dashboard/manifest.json` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the generic runtime-configuration and receipt-log-viewer metadata names no V1 verdict, field, CLI, policy, or current schema version and remains truthful for the downstream V2 migration. Validate JSON syntax and record the candidate-specific unchanged review. |
| Hermes plugin manifest description | `integrations/hermes/nunchi-gate/plugin.yaml` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-hermes-owner`; replace the public PASS/ACK/ASK/SPEAK and `nunchi-channel` description with the accepted I-030A wake/suppress/defer, bypass, and operational-error lifecycle when the Hermes surface migrates. Validate manifest syntax and installed metadata with that candidate. |
| Discord MCP design | `integrations/mcp-discord/DESIGN.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the document correctly keeps the transport gate-neutral and assigns admission harness-side; I-030A changes no transport protocol or ownership. Record exact review unchanged. |
| Discord MCP operator guide | `integrations/mcp-discord/README.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: token, SSE/MCP, routing, and send-backstop guidance remains transport-only and does not consume I-030A; record exact review unchanged. |

Matrix scope audit (2026-07-19): the 47 unique rows above enumerate all 45
known affected current ordinary documentation/evidence/configuration/example claim
surfaces and the future slice-owned `docs/attention/v2.md` and
`evidence/v2/attention/README.md` individually: 8
`UPDATE`, 17 `NO_IMPACT`, and 22 `HANDOFF`. Every disposition is attached to one exact file;
no grouped multi-file disposition substitutes for an exact path. The bound
specification, dormant T025, and formal requirements checklist retain this same
47-path inventory and disposition count.

Receipt-sink clarification re-review (2026-07-19): the disposition denominator
remains 47 / 8 / 17 / 22. Exactly 12 rows need an exception-protocol claim
delta and now state it above: `README.md`, `CLAUDE.md`,
`evidence/v2/attention/README.md`, `CHANGELOG.md`, `docs/STABILITY.md`,
`docs/adapters.md`, `docs/integration.md`, `examples/loader-snippet.md`,
`docs/attention/v2.md`, `integrations/claude-code/README.md`,
`integrations/codex/README.md`, and `integrations/hermes/README.md`. The other
six `UPDATE` rows remain evidence-index or historical verdict-suite surfaces,
so their existing candidate-relative deltas already cover every claim they
own. All 17 `NO_IMPACT` rows were re-reviewed; in particular the two 010-owned
contract references now state why an I-030A runtime exception does not alter
them. The other twelve `HANDOFF` rows govern lifecycle, installation/configuration,
architecture, V1 retirement, policy profiles, evaluation, or installed
metadata that neither exposes nor consumes the callable sink exception; their
existing exact deltas therefore remain complete. Every conclusion is still
retested against the exact candidate and recorded by T025 rather than inherited
as documentation-freshness proof.

Completeness correction (2026-07-19): the final sweep added the two runnable V1
Python demos as exact integrator handoffs and the plugin-local `.mcp.json` as a
candidate-revalidated `NO_IMPACT`. This is the source of the final 47-path
denominator; no earlier 44-path count remains current.

Global current-state claims remain integrator-owned; the component guide and
every exact handoff delta are required before 030 can converge. T025 records
the reviewer, validation result, and evidence-backed rationale for every
`NO_IMPACT` row in `evidence/v2/attention/handoff.md`; the later lifecycle gates
record exact candidate identity in `slice-candidate.md` and
`slice-handoff.md`. A bare matrix assertion is not documentation-freshness
evidence.

## Owner Handoff

The owner must hand off the exact commit, I-030A and upstream interface
versions, complete commands/results, prompt and model identity, effective
operator configuration and source, margin state, deterministic/replay/multi-
model evidence (including exact provider IDs/provenance for the selected three-
family matrix or an explicit later Zoe override), the preregistered downstream
canary protocol, rejected claims, and known limitations. It carries exact
I-010B `status: bypass`, `cause: "preattention-disabled"` plus zero-call evidence for independent
acceptance by `v2-wake-owner`; the accepting slice-040 test must map that branch
to ParticipantWakeV2 wake source `PREATTENTION_BYPASS`. Slice 030 neither emits
ParticipantWakeV2 nor claims that downstream test complete. It also carries the
exact slice-110 ordinary-path publication delta from the staging decision:
remove V1 request/verdict handling, `require_pass_corroboration`, reply-bearing
output, and hidden fallbacks; publish I-030A as public `evaluate`/`admit`; and
remove `evaluate_v2`/`attention-v2` atomically across the six named source
files. The handoff explicitly does not claim live participant outcomes.
Downstream review
does not silently transfer core ownership; 110 remains the sole final sink.
The packet distinguishes (1) the tested implementation tree named by T027,
(2) the lifecycle candidate commit that contains `verification.md`, and (3) the
later handoff packet commit containing lifecycle records. Exact-candidate and
packet-commit baseline reruns are both required and recorded only from later
commits, so no self-referential SHA is embedded in its own tree.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.
