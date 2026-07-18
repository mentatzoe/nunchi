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
- This planning baseline creates no schema, prompt, classifier, provider call,
  CLI behavior, test, replay corpus, evidence, product documentation, or V2
  runtime behavior.
- The current V1 implementation and its `PASS / ACK / ASK / SPEAK` contract
  remain implementation truth through atomic integration and exact-main
  verification; V2 becomes current only when the program reaches
  `CUTOVER_VERIFIED` after final documentation validation.

### Readiness blocker discovered during planning analysis

The selected design at `c834e8c` requires the effective policy and its source
to be inspectable in receipts and an operator `NO_WAKE` override to be
separately receipted as operational failure policy. Accepted
`I-010E AttentionReceiptV2@1` has closed classifier and error bodies with no
field for those facts; only bypass has `policy_provenance`. Slice 030 cannot add
local fields, encode provenance in free-form error detail, or revise a 010-owned
contract. Until `v2-contract-owner` supplies a versioned accepted resolution
and this consumer separately accepts it, analysis cannot reach zero HIGH
findings, this slice remains `PLANNED`, activation evidence remains absent, and
all implementation tasks remain dormant. The post-acceptance discovery and its
lifecycle effect are recorded at
`evidence/v2/attention/dependency-010-post-acceptance-blocker.md`; the earlier
consumer acceptance record remains immutable.

## Interface Summary

- **Consumes**:
  - `I-010A AttentionRequestV2@1`
  - `I-010B AttentionDecisionV2@1`
  - `I-010E AttentionReceiptV2@1`
- **Produces**: `I-030A AttentionEngineV2@1` — the versioned
  `evaluate_v2(...)` callable plus the non-current `attention-v2` CLI command,
  contract-equivalent CLI implementing I-010A/B/E, participant-shaped
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
   and a valid margin that does not defer, **When** routing completes, **Then**
   effective `SUPPRESS` is allowed and fully receipted.
2. **Given** candidate `SUPPRESS` with margin uncertainty, disabled suppression,
   or unproven recoverability, **When** routing completes, **Then** effective
   disposition is `DEFER` with the exact valve and override cause.
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
2. **Given** an explicit operator `NO_WAKE` error override, **When** an
   operational error occurs, **Then** it is separately sourced and receipted
   and never labeled model suppression; this scenario is blocked by the
   accepted I-010E shape identified above and MUST NOT be implemented through a
   local extension or error-detail convention.
3. **Given** equivalent input and effective trusted configuration, **When** the
   core and CLI run, **Then** they produce contract-equivalent decisions and
   audit fields.
4. **Given** preattention is disabled by trusted configuration, **When** core
   and CLI run, **Then** both return the same bypass branch, make zero model
   calls, and route downstream with wake source `PREATTENTION_BYPASS`.

### Edge Cases

- Missing, extra, non-finite, or out-of-range legacy confidence values while
  the margin is active; a malformed candidate suppression becomes error.
- Advice on DEFER/SUPPRESS, advice citing unknown events, instruction-like
  advice, forged structured output in room text, or reply-bearing output.
- Provider retry versus a second logical social judgment; bounded transport
  retries do not authorize a second classifier decision.
- Request-controlled credentials, endpoint, model, limits, or suppression
  policy; trusted operator configuration must win and its source be receipted.
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
  configuration sources. A missing/unreadable/unsafe file, missing/extra key,
  duplicate key, or any nested validation failure is configuration `ERROR`;
  there is no source merge or precedence rule. Policy
  `participant_id` and recoverability `participant_id` MUST both equal
  `request.self.participant_id`; recoverability `continuity_scope_id` MUST equal
  `request.room.continuity_scope_id`; any mismatch is configuration `ERROR`.
  `receipt_sink` is exactly a synchronous
  `Callable[[AttentionReceiptV2], None]`: one normal `None` return means the
  offered record persisted, any raised exception means failure, and the engine
  neither retries nor calls the sink more than once for a request. The CLI
  adapts its closed `receipt_sink` object to that protocol by canonicalizing the
  attention record as UTF-8 JSON plus one newline and using descriptor-relative
  no-follow exclusive create for mode `0600` file
  `<sha256(request_id UTF-8)>.attention.json`; it never overwrites an existing
  record. Success requires complete write, flush, file `fsync`, close, and
  directory `fsync`. An exclusive-create collision raises a typed sink failure
  with persistence `unknown`: the engine neither overwrites nor assumes the
  existing file is its record. Any other open failure before creation is
  `not-persisted`. Any write/flush/fsync/close failure
  triggers descriptor-relative unlink of only the newly created file followed
  by directory `fsync`; only successful cleanup may report `not-persisted`.
  Cleanup/unlink/directory-fsync failure, or a final directory-fsync failure
  after the file was closed, reports persistence `unknown`. Neither failure
  outcome claims persistence, and the engine returns operational `ERROR` with
  the exact sink outcome in its off-surface error fact. The configuration file,
  credentials, filesystem path, and sink source never enter classifier input,
  stdout, stderr, decision data, or receipt body.
- **FR-002**: The model instruction MUST be participant-shaped, sparse, and
  limited to whether the supplied event is worth waking for now; it MUST NOT
  encode a speaker algorithm, response obligation rubric, or reply composition.
- **FR-003**: One valid request MUST produce one logical model judgment.
  Trusted `classifier_config.max_retries` is required and MUST be an integer
  from `0` through `2`, so one judgment has at most three transport attempts;
  neither callable nor CLI inserts a default.
  Only connection failures, timeouts, HTTP `429`, and HTTP `5xx` are retryable;
  schema/configuration errors, other `4xx`, and malformed model output are not.
  Every attempt reuses the same request payload and logical request ID and may
  not be treated as an independent social vote. Exhaustion returns operational
  `ERROR` with wake as the shared default.
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
  assigned `v2-core-owner` is the recorded adjudicator, and any failed field is
  a failed advice case. Count/length/citation checks are deterministic; the two
  semantic fields remain explicit human evidence, not a social heuristic.
  These are prompt/evidence criteria only: runtime validation MUST NOT reject or
  truncate otherwise I-010B-valid advice solely for item count or length.
- **FR-006**: Social suppression MUST require exact participant authorization,
  recoverability eligibility supplied as trusted capability, cheap uncertainty,
  and inspectable/revocable operator delegation.
- **FR-007**: Effective policy, provider endpoint, credentials, model, budgets,
  error action, suppression enablement, transition margin, and configuration
  source MUST be operator-owned and MUST NOT be redirected by room input.
- **FR-008**: Direct classifier DEFER and margin-derived DEFER MUST be separately
  receipted; either may only widen attention, and the margin retains protective
  precedence until separately retired by evidence. Routing validation precedes
  policy: malformed/missing active-margin confidence on candidate `SUPPRESS`
  is `ERROR`. For a valid candidate `SUPPRESS`, precedence is suppression
  disabled (`policy-defer` / `suppression-disabled`), then recoverability false
  (`policy-defer` / `recoverability-unproven`), then active margin uncertainty
  (`margin-defer` / `margin`), then no valve. Thus each matrix row has one exact
  audit oracle even when several widening conditions coexist. Candidate
  `WAKE` uses `none`; classifier `DEFER` uses `classifier-defer`; neither is
  narrowed by policy or margin.
- **FR-009**: A candidate suppression while the margin is active MUST include
  the exact valid legacy confidence vector required by I-010B; missing or
  malformed evidence MUST produce operational error and wake fallback.
- **FR-010**: Deterministic policy MAY convert candidate `SUPPRESS` only to
  `DEFER`; it MUST NOT manufacture suppression or convert `WAKE`/`DEFER` to a
  hard stop.
- **FR-011**: Validation, provider, timeout, malformed-output, configuration,
  and runtime failures MUST return `ERROR`; shared default action is wake, with
  any explicit `NO_WAKE` operator override separately sourced and receipted.
  The closed accepted I-010E error body cannot currently satisfy that selected
  requirement, so implementation is blocked pending the versioned 010-owned
  resolution described in the readiness blocker.
- **FR-012**: Whenever a parsed request supplies a valid request ID, the engine
  MUST emit one immutable attention-stage I-010E record correlated by that ID
  that keeps classifier disposition, effective disposition, valve, override
  cause, the policy/model provenance representable by the accepted branch,
  operational error, and
  classifier-not-invoked bypass provenance distinct. Unreadable input, invalid
  JSON, and pre-validation failures without an assignable request ID MUST emit
  no I-010E record and MUST NOT invent a correlation ID. Failure of the receipt
  sink itself is likewise non-receiptable: it MUST return operational `ERROR`
  with wake default and explicitly report that no receipt persisted. Latency and
  serialized/token-cost measurements MUST remain ordinary performance evidence,
  not extra fields inside the closed I-010E attention body. The engine MUST
  leave participant, send, and transport outcome facts to later stages and MUST
  NOT mutate an earlier observation-stage record.
  This wording does not waive the selected design's broader effective-policy
  and `NO_WAKE` provenance requirement; the readiness blocker must be resolved
  upstream rather than hidden in I-010E `error.detail`.
- **FR-013**: The isolated slice branch MUST stage I-030A as additive,
  non-current symbols inside the owned `core.py`, `cli.py`, classifier, model,
  and validation seams: `evaluate_v2` and `attention-v2` accept and emit only V2
  contracts and MUST NOT call, translate to, or fall back through V1. Existing
  public `nunchi.evaluate`, `nunchi admit`, and their V1 tests remain unchanged
  and green solely to preserve current behavior before cutover. The owner packet
  MUST give `v2-integrator` the exact slice-110 publication delta: remove V1
  request/verdict handling, `require_pass_corroboration`, reply-bearing output,
  and hidden local fallbacks; publish I-030A as the public `evaluate`/`admit`
  behavior; and remove the temporary `evaluate_v2`/`attention-v2` staging names
  in the same atomic assembled candidate. This staging is not a V1-to-V2
  compatibility bridge and MUST NOT land on `main` or be documented as current
  behavior before slice 110.
- **FR-014**: Deterministic tests MUST prove mechanics and transition safety;
  committed replay, multi-model, false-suppression-scar, and preregistered
  downstream canary targets MUST be defined before social-quality or margin-
  retirement claims. The
  multi-model matrix MUST include the incumbent Gemini 3.1 Flash Lite family,
  frontier GPT-5.5 family, and open-weight Qwen3 family unless Zoe explicitly
  overrides the set; each run MUST record the exact provider model ID, provider,
  endpoint class, date, prompt/config identity, and any override provenance.
  This comparison is descriptive and non-gating for social-quality rates:
  mistaken suppressions, missed suppressions, wake volume, and family
  disagreement MUST be recorded and carried as limitations, but no local rate
  threshold authorizes social correctness or margin retirement. Handoff still
  blocks if a required family/corpus run is absent, provenance is incomplete,
  advice adherence is below FR-005's criterion, or mechanics fail to route an
  invalid/unsafe result to `DEFER` or operational `ERROR` as specified.
- **FR-015**: The owner MUST hand off the exact commit, I-030A version,
  commands/results, prompt/model and effective-policy provenance, evidence,
  margin status, and known limitations to every downstream owner.
- **FR-016**: No product implementation, schema, test, corpus, evidence,
  runtime asset, or product documentation may be created under this SpecKit
  slice.
- **FR-017**: Trusted `preattention-disabled` configuration MUST return the
  I-010B `status: bypass` branch, make zero classifier calls, carry no
  classifier/effective disposition, and identify downstream wake source
  `PREATTENTION_BYPASS`; it MUST NOT be represented as WAKE, DEFER, ERROR, or
  model suppression.
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
  valid request ID. A configuration error is likewise receipted only when its
  closed `receipt_sink` member independently validates and a valid request ID is
  assignable; otherwise no engine-owned sink exists. If no trusted sink can be constructed, the tagged error
  states persistence `not-persisted` and MUST NOT fabricate a receipt. A sink
  invocation failure after construction is operational/runtime exit 1 and
  reports the typed `not-persisted` or `unknown` outcome from FR-001.
- **FR-020**: Core/CLI tests MUST pass contract-valid requests containing
  sentinel continuation secrets and prove the classifier provider receives
  none of those host-only values while the downstream host can still receive
  the original bound continuation capability.

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
  diagnostics, and exit status allowed to differ.
- **SC-002**: The exact 36-row classifier/effective transition matrix has zero
  invalid success pairs and zero cases where uncertainty or malformed evidence
  yields effective suppression. Its finite domain is: 16 `WAKE`/`DEFER` rows
  (`2` dispositions x suppression enabled/disabled x recoverability
  eligible/ineligible x margin active/retired), four retired-margin `SUPPRESS`
  rows (suppression x recoverability), and 16 active-margin `SUPPRESS` rows
  (suppression x recoverability x confidence class outside-margin,
  inside-margin, missing, or malformed). Missing/malformed active-margin
  confidence always yields operational `ERROR`; policy may otherwise change
  only candidate `SUPPRESS` to effective `DEFER`. Every row records expected
  response status, classifier/effective pair when applicable, margin status,
  valve, and override cause using FR-008's validation and precedence order.
- **SC-003**: All forged advice, nonexistent evidence IDs, reply-bearing fields,
  request-controlled operator settings, and invalid model output are rejected
  or routed to operational error.
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
  `python3 -m evals.verdict_suite.runner --list`, and `git diff --check`, with
  governance finding zero product artifacts under this slice directory.
  Latency, serialized request/response bytes, provider-reported input/output
  tokens (or explicit `unavailable`), attempt count, provider/model, runtime,
  host/OS, and fixture/corpus identity are mandatory descriptive fields. Slice
  030 sets no latency or token threshold and makes no performance pass claim
  beyond complete measurement; retry count remains mechanically bounded by
  FR-003. The full baseline MUST also prove that current V1 public exports,
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

- Slice 010 lands accepted I-010A/B/E `@1` schemas before implementation begins.
- The existing standard-library OpenAI-compatible provider transport may be
  evolved without adding a runtime dependency.
- Initial V2 integration retains the protective margin; direct classifier
  DEFER evaluation can run live without narrowing safety.
- The selected three-family matrix is Gemini 3.1 Flash Lite, GPT-5.5, and
  Qwen3. Provider catalogs can change, so run records—not this plan—pin exact
  provider IDs; any later family substitution requires an explicit Zoe decision
  recorded with the evidence.
- Slice 020 may develop in parallel and is not required to test I-030A because
  core tests can construct contract-valid I-010A fixtures directly.
- Slice 030 prepares but does not execute participant/live-room canaries;
  participant behavior does not exist until dependent slices land.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` exact I-030A disposition, bypass,
  operational ERROR, CLI, and dual-DEFER claim deltas to `v2-integrator`.
- **Affected ordinary docs**: `UPDATE` `docs/attention/v2.md`,
  `docs/contracts/verdict-suite-data-model-v1.md`,
  `docs/contracts/verdict-suite-requirements-v1.md`,
  `docs/evaluations/verdict-suite.md`, and
  `docs/evaluations/verdict-suite-runner.md`, preserving V1 scar evidence while
  naming its V2 role. `HANDOFF` exact result, CLI/error, disposition, bypass,
  dual-DEFER, and supersession deltas for `CHANGELOG.md`, `docs/STABILITY.md`,
  `docs/integration.md`, `docs/INSTALL.md`, `docs/adapters.md`,
  `docs/contracts/channel-adapter-v1.md`, and
  `docs/architecture/v2-selected-design.md` to accepting `v2-integrator`.
  `NO_IMPACT` `integrations/mcp-discord/README.md` and
  `integrations/mcp-discord/DESIGN.md`: both remain gate-neutral transport
  references and do not consume I-030A; the exact candidate-specific rationale
  and reviewer are recorded in ordinary handoff evidence. `HANDOFF` the
  surface-specific lifecycle delta for `integrations/hermes/README.md` to
  accepting `v2-hermes-owner`,
  `integrations/claude-code/README.md` and
  `integrations/claude-code/DEFER_EVAL.md` to accepting `v2-claude-owner`, and
  `integrations/codex/README.md` to accepting `v2-codex-owner`.
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
- No edits to 010-owned schemas; requested contract changes return to
  `v2-contract-owner`.
