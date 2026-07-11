# Existing Slice Specification: V2 Core Attention

**Feature Branch**: `v2/core-attention`

**Created**: 2026-07-11

**Slice state**: `PLANNED`

**Program implementation authority**: `NOT_GRANTED`

**Activation evidence**: `evidence/v2/attention/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/attention/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/attention/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/attention/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Input**: Replace the V1 move classifier with one participant-shaped pre-attention judgment, governed suppression, dual DEFER valves, separate operational error, and contract-equivalent callable core and CLI.

**Authority source**: Zoe-selected Aleph Vault design at `bdd1ebb`, contract-clarified in PR 68 at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-core-owner`

**Assigned participant / source**: UNASSIGNED — may be replaced during
planning, before implementation authority, only from a durable external
assignment source; activation evidence later copies and attests it when
establishing `READY`

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
  remain implementation truth until slice `110` performs final atomic
  integration.

## Interface Summary

- **Consumes**:
  - `I-010A AttentionRequestV2@1`
  - `I-010B AttentionDecisionV2@1`
  - `I-010E AttentionReceiptV2@1`
- **Produces**: `I-030A AttentionEngineV2@1` — one callable core plus
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
   **Then** optional advice is brief, non-authoritative, grounded in included
   events, and contains no drafted response.
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
and prove bypass and every operational failure remain tagged non-social branches
with their own immutable I-010E attention-stage records.

**Acceptance Scenarios**:

1. **Given** validation or classifier failure after a routable event exists,
   **When** the engine returns, **Then** status is `ERROR`, default host action
   is wake, and error detail remains off the room surface.
2. **Given** an explicit operator `NO_WAKE` error override, **When** an
   operational error occurs, **Then** it is separately sourced and receipted
   and never labeled model suppression.
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
- Preattention disabled as an explicit non-model bypass; social suppression disabled, recoverability unproven,
  expired policy, unavailable provider, timeout, invalid schema, and illegal
  classifier/effective disposition pairing.
- Host-only continuation handles, binding material, cursors, and expiry data
  must never appear in the classifier projection even when present in I-010A.
- Same-class address and apparent resolution scars must be judged socially by
  the model, never by deterministic mention/topology or corroboration code.

## Requirements

### Functional Requirements

- **FR-001**: The slice MUST implement `I-030A AttentionEngineV2@1` against the
  exact I-010A/B/E versions and MUST expose contract-equivalent callable-core
  and CLI results.
- **FR-002**: The model instruction MUST be participant-shaped, sparse, and
  limited to whether the supplied event is worth waking for now; it MUST NOT
  encode a speaker algorithm, response obligation rubric, or reply composition.
- **FR-003**: One valid request MUST produce one logical model judgment;
  provider transport retries MAY repeat delivery safely but MUST NOT create a
  second independent social decision.
- **FR-004**: The classifier disposition MUST be exactly `SUPPRESS`, `WAKE`, or
  `DEFER`; operational `ERROR` MUST remain a separate tagged response branch.
- **FR-005**: `WAKE` advice, when present, MUST be short, non-authoritative,
  grounded in named supplied event IDs, and free of reply prose; `SUPPRESS` and
  `DEFER` MUST carry no participant advice.
- **FR-006**: Social suppression MUST require exact participant authorization,
  recoverability eligibility supplied as trusted capability, cheap uncertainty,
  and inspectable/revocable operator delegation.
- **FR-007**: Effective policy, provider endpoint, credentials, model, budgets,
  error action, suppression enablement, transition margin, and configuration
  source MUST be operator-owned and MUST NOT be redirected by room input.
- **FR-008**: Direct classifier DEFER and margin-derived DEFER MUST be separately
  receipted; either may only widen attention, and the margin retains protective
  precedence until separately retired by evidence.
- **FR-009**: A candidate suppression while the margin is active MUST include
  the exact valid legacy confidence vector required by I-010B; missing or
  malformed evidence MUST produce operational error and wake fallback.
- **FR-010**: Deterministic policy MAY convert candidate `SUPPRESS` only to
  `DEFER`; it MUST NOT manufacture suppression or convert `WAKE`/`DEFER` to a
  hard stop.
- **FR-011**: Validation, provider, timeout, malformed-output, configuration,
  and runtime failures MUST return `ERROR`; shared default action is wake, with
  any explicit `NO_WAKE` operator override separately sourced and receipted.
- **FR-012**: The engine MUST emit one immutable attention-stage I-010E record
  correlated by request ID that keeps classifier disposition, effective
  disposition, valve, override cause, policy/model provenance, timings,
  operational error, and classifier-not-invoked bypass provenance distinct.
  It MUST leave participant, send, and transport outcome facts to later stages
  and MUST NOT mutate an earlier observation-stage record.
- **FR-013**: The V2 core branch MUST remove V1 request/verdict handling,
  `require_pass_corroboration`, reply-bearing output, and any hidden local
  classifier fallback; it MUST NOT add a compatibility bridge.
- **FR-014**: Deterministic tests MUST prove mechanics and transition safety;
  committed replay, multi-model, false-suppression-scar, and preregistered
  downstream canary targets MUST be defined before social-quality or margin-
  retirement claims. The
  multi-model matrix MUST include the incumbent Gemini 3.1 Flash Lite family,
  frontier GPT-5.5 family, and open-weight Qwen3 family unless Zoe explicitly
  overrides the set; each run MUST record the exact provider model ID, provider,
  endpoint class, date, prompt/config identity, and any override provenance.
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
  expansion is available; I-010D remains host-only for the participant turn.
- **FR-019**: For valid `ok` or `bypass` responses the CLI MUST write exactly
  one tagged JSON value to stdout, no response payload to stderr, and exit 0.
  Parsed requests that fail request-schema validation MUST return tagged
  `status: error` JSON on stdout and exit 3. Provider/runtime/malformed-model
  failures MUST return tagged `status: error` JSON on stdout and exit 1.
  Unreadable input or invalid JSON, for which no request union can be formed,
  MUST write a diagnostic only to stderr, write nothing to stdout, and exit 2.
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
  override, bypass, provenance, timing, and error facts in an immutable
  attention-stage record kept off-surface.

## Success Criteria

### Measurable Outcomes

- **SC-001**: For every deterministic fixture, callable core and CLI produce
  semantically equivalent I-010B results and the documented CLI exit behavior.
- **SC-002**: The full classifier/effective transition matrix has zero invalid
  success pairs and zero cases where uncertainty or malformed evidence yields
  effective suppression.
- **SC-003**: All forged advice, nonexistent evidence IDs, reply-bearing fields,
  request-controlled operator settings, and invalid model output are rejected
  or routed to operational error.
- **SC-004**: False-suppression-scar replay contains no deterministic semantic
  suppressor and records model disposition, effective disposition, and
  participant-shaped rationale for every case.
- **SC-005**: Multi-model evaluation records distinguish direct classifier
  DEFER from margin DEFER and report mistaken suppressions, missed suppressions,
  and wake volume separately. A preregistered canary protocol assigns live
  participant/silence outcomes to the surface and final-integration owners; the
  030 handoff does not depend on unavailable downstream behavior.
- **SC-006**: The protective margin is marked active at initial V2 handoff and
  cannot be retired by this slice without the separately required evidence and
  project-owner acceptance.
- **SC-007**: The handoff packet names exact I-030A and upstream versions,
  commands, evidence, effective configuration, prompt/model identity, margin
  state, and limitations with no downstream ownership ambiguity.
- **SC-008**: Governance validation finds zero product artifacts under this
  slice directory.

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
  `HANDOFF` the surface-specific lifecycle delta for
  `integrations/mcp-discord/README.md` and
  `integrations/mcp-discord/DESIGN.md` to accepting `v2-transport-owner`,
  `integrations/hermes/README.md` to accepting `v2-hermes-owner`,
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
