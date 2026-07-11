# Feature Specification: V2 Security and Runtime Provenance

**Feature Branch**: `v2/security-provenance`

**Created**: 2026-07-11

**Status**: Planned for future Goal 2; not authorized for implementation

**Input**: User description: "Close the V2 security, governed-suppression,
operational-safety, credential, provenance, adversarial-evidence, and
residual-risk obligations after all component slices are ready."

**Authority source**: Aleph Vault PR 67 selected design at `bdd1ebb`,
contract-clarified by PR 68 at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-security-owner`

**Depends on**: `010`, `020`, `030`, `040`, `050`, `060`, `070`, `080`, `090`

**Feeds**: `110-v2-parity-cutover`

## Control-Plane Boundary *(mandatory)*

- This directory contains planning artifacts only.
- Product source, contracts, schemas, tests, fixtures, evaluations, evidence,
  runtime assets, and documentation MUST target ordinary repository paths.
- Goal 2 has not been authorized. Every task in this slice is a future task and
  MUST remain unexecuted until Zoe separately authorizes Goal 2 and all upstream
  handoffs are accepted.
- This slice MUST NOT implement V2 behavior, edit runtime code, create a
  machine-readable contract, execute a live probe, or accept residual risk
  during Goal 1.
- This slice does not invent social rules, a governance-profile library, a
  participant registry, or deterministic conversational suppression.

## Interface Summary *(mandatory)*

- **Consumes**:
  - `I-010A AttentionRequestV2@1`, `I-010B AttentionDecisionV2@1`,
    `I-010C ParticipantWakeV2@1`, `I-010D ContextContinuationV2@1`, and
    `I-010E AttentionReceiptV2@1` from slice `010`;
  - `I-020A ObservationProviderV2@1` from slice `020`;
  - `I-030A AttentionEngineV2@1` from slice `030`;
  - `I-040A ParticipantTurnHostV2@1` from slice `040`;
  - `I-050A DiscordEventSourceV2@1` from slice `050`;
  - implementation and evidence handoffs from `060` Hermes, `070` Claude Code,
    `080` Codex, and `090` channel adapters, each conforming to the applicable
    canonical interfaces above.
- **Produces**:
  - a V2 security assurance report covering suppression authorization,
    revocation, recoverability, operational send safety, credential boundaries,
    and installed-runtime provenance for slice `110`;
  - a V2 security readiness handoff containing the audited commit set, threat
    dispositions, adversarial evidence, accepted residual risk, commands,
    limitations, an evidence manifest, and exact canonical interface versions
    for slice `110`.
- **Integration handoff**: `v2-security-owner` hands one reviewed commit and the
  complete V2 security readiness handoff to `v2-integrator`. The integrator may
  reject it but MUST NOT silently redefine security policy or accept risk on
  the owner's behalf.

These are assurance/evidence handoffs, not product interfaces. The canonical
registry remains exactly `I-010A`–`I-050A`, and slice `010` remains the sole
owner of machine-readable V2 product schemas.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assure Governed Social Suppression (Priority: P1)

As a security reviewer, I can prove that the participant-shaped pre-attention
proxy implemented by the owning slices is explicitly authorized, inspectable,
revocable, and recoverable, and that a missing legitimacy condition cannot
become silent social suppression.

**Why this priority**: A false suppression removes the participant's chance to
attend the moment. This is the highest-risk branch in the selected design.

**Independent Test**: Replay authorization, revocation, restart, malformed
configuration, and unavailable-recoverability scenes. Suppression is possible
only when every legitimacy condition is established; all uncertainty wakes or
defers and all outcomes are separately receipted.

**Acceptance Scenarios**:

1. **Given** a valid participant binding, explicit proxy authorization,
   recoverable observation, and a confident model `SUPPRESS`, **When** the event
   is processed, **Then** the wake is suppressed and the authorization,
   decision, coverage, and recovery facts are recorded off-surface.
2. **Given** authorization is absent, expired, malformed, or revoked, **When** a
   model proposes `SUPPRESS`, **Then** the system wakes or defers and records why
   suppression was unavailable.
3. **Given** an event was suppressed before restart, **When** the assurance suite
   evaluates a later related event assembled within the declared retention
   horizon, **Then** the first
   event remains available through ordinary observation or a bound continuation
   without any handled/open social state.
4. **Given** revocation occurs while the room continues, **When** later events
   arrive, **Then** observation continues but no new social suppression is
   authorized until the operator explicitly restores it.
5. **Given** any governed-suppression scene fails, **When** the assurance owner
   records the finding, **Then** implementation returns to the owner of the
   failing contract, core, observation, transport, or surface and slice `100`
   re-audits the exact repaired commit rather than implementing the mitigation.
6. **Given** trusted operator configuration disables preattention, **When** the
   bypass route is exercised, **Then** it makes zero classifier calls, invokes
   the participant once with advice-free source `PREATTENTION_BYPASS`, records
   `classifier_not_invoked`, and contains no fabricated classifier/effective
   disposition or model evidence.

---

### User Story 2 - Assure Runtime and Send Boundaries (Priority: P1)

As a security reviewer and operator, I can prove that each owning surface keeps
credentials and executable configuration operator-owned, bounds sends
mechanically, and runs the intended V2 build rather than a stale wheel, hook, or
shim.

**Why this priority**: A correct source tree is not a secure or migrated system
when the installed runtime, credentials, or send path differs from it.

**Independent Test**: Exercise request-controlled endpoint/key attempts,
credential redaction, per-channel send limits, restart/reload, stale runtime
detection, and a known V2 probe on every upstream surface handoff.

**Acceptance Scenarios**:

1. **Given** room content or a request tries to set a provider endpoint, key,
   executable path, or participant identity, **When** it reaches any V2 surface,
   **Then** the override is rejected and no secret appears in schemas, receipts,
   logs, or participant context.
2. **Given** an admitted or error-fallback participant attempts repeated sends,
   **When** the configured channel limit is reached, **Then** the operational
   backstop blocks further sends without fabricating a social disposition.
3. **Given** source, installed package, hook, or configuration provenance does
   not match the intended candidate, **When** a migration probe runs, **Then**
   the surface is reported as not migrated and cannot enter parity integration.
4. **Given** the intended candidate has been installed and restarted, **When** a
   known V2 probe runs, **Then** the receipt identifies schema version, exact
   component/package provenance, effective configuration, and expected error
   and no-send behavior.
5. **Given** a request-correlated lifecycle is receipted, **When** assurance
   inspects its `observation`, `attention`, `participant-host`, and `transport`
   records, **Then** each immutable stage was appended only by the owner that
   directly attested it, no prior stage was mutated, no future stage was filled,
   and participant silence did not acquire a fabricated transport delivery.

---

### User Story 3 - Close Threats with Evidence (Priority: P2)

As the project owner and final integrator, we can inspect a complete V2 threat
model, adversarial results, mitigations, and explicit residual-risk decisions
before the candidate is allowed into final parity integration.

**Why this priority**: Documentation-only security claims and green unit tests
do not demonstrate resistance to hostile room content or installed-runtime
drift.

**Independent Test**: Run the committed V2 adversarial corpus across the selected
three-family attention matrix and every exact installed participant/runtime
configuration. Execute at least five independent repetitions per stochastic
model/scene/configuration cell, retain every attempt, trace every threat to a
mitigation and evidence record, and verify that every unmitigated risk has
explicit Zoe acceptance or blocks the handoff.

**Acceptance Scenarios**:

1. **Given** fake system text, fake governance, verdict spoofing, Unicode or
   Markdown smuggling, sentinel forgery, and hostile history, **When** the V2
   adversarial evaluation runs, **Then** the participant judges the social facts
   without granting room content operator authority and results are recorded
   without cherry-picking.
2. **Given** a threat lacks a built and tested mitigation, **When** readiness is
   reviewed, **Then** the handoff is blocked unless Zoe explicitly accepts a
   precise residual-risk statement.
3. **Given** all threats have evidence-backed dispositions, **When** the owner
   prepares the handoff, **Then** the bundle identifies exact commands, commits,
   interfaces, runtime provenance, results, limitations, and accepted risk.

### Edge Cases

- Authorization changes between model decision and route application.
- Revocation storage is unavailable or stale after restart.
- A surface can observe events but cannot guarantee the declared recovery
  horizon.
- The provider returns malformed output, times out, or exposes no confidence
  evidence.
- The participant chooses silence after `WAKE`, `DEFER`, trusted preattention
  bypass, or operational error.
- Room content or an untrusted request attempts to select bypass, forges
  `classifier_not_invoked`, or impersonates a receipt-stage owner.
- Credential-like text appears naturally in room content or adversarial
  fixtures and must not be mistaken for an operator secret.
- Installed source commit and package version agree while a stale hook or shim
  still runs.
- A send backstop is missing on one surface or reports its action as a social
  verdict.
- An upstream interface is absent, stale, or not the version declared in its
  handoff.
- A platform cannot provide one fact required by a scene; the absence remains
  explicit rather than synthesized.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The slice MUST audit explicit, inspectable, and revocable operator
  authorization for model social suppression without introducing room policy
  or a governance-profile library.
- **FR-002**: The slice MUST prove that `SUPPRESS` widens to `WAKE` or `DEFER`
  whenever authorization, recoverability, uncertainty handling, or required
  provenance is unavailable or invalid.
- **FR-003**: The slice MUST prove that suppressed observations remain
  recoverable within declared coverage and across the supported restart/backfill
  boundary, without outcome-derived social state.
- **FR-004**: The slice MUST audit that operational `ERROR`, send-backstop
  actions, and social dispositions remain separate in contracts, receipts,
  tests, and evidence.
- **FR-005**: The slice MUST audit default-on, per-channel operational send
  safety implemented by every sending surface without a second social classifier.
- **FR-006**: The slice MUST prove that room/request data cannot set provider
  credentials, endpoints, executable paths, participant identity, or other
  operator-owned runtime configuration.
- **FR-007**: The slice MUST audit secret redaction and storage boundaries for
  schemas, logs, receipts, evaluation output, evidence, and participant context.
- **FR-008**: The slice MUST reject any surface that does not prove intended commit/package identity,
  effective configuration, retired-hook absence, restart/reload, schema version,
  and a known live V2 probe before receiving a migrated status.
- **FR-009**: The V2 threat model MUST cover classifier and participant prompt
  injection, false suppression, governance poisoning, credential redirection,
  amplification, sentinels, logs/dashboards/receipts, privileged control
  surfaces, supply chain, and runtime drift.
- **FR-010**: Reusable adverse fixtures and runners MUST live under `evals/`,
  deterministic enforcement tests under `tests/`, live run records under
  `evidence/`, and security documentation under `docs/` or `SECURITY.md`.
- **FR-011**: Adversarial evidence MUST report the full selected matrix,
  repetitions, model/runtime identities, failures, and flicker. The attention
  matrix MUST contain Gemini 3.1 Flash Lite, GPT-5.5, and Qwen3 families from
  slice `030`, and each stochastic model/scene/configuration cell MUST run at
  least five independent repetitions with every attempt retained. A different
  matrix or repetition floor requires Zoe's explicit pre-registered approval
  before execution. Evidence MUST record exact provider/model IDs and timestamps
  and MUST NOT reduce stochastic behavior to an unreproducible single accuracy
  number.
- **FR-012**: Every threat MUST end in an evidence-backed mitigation or a
  precise residual-risk statement explicitly accepted by Zoe; otherwise the
  slice MUST block handoff to `110`.
- **FR-013**: The slice MUST consume and validate every handoff from `010`
  through `090` before security integration begins.
- **FR-014**: The slice MUST produce a V2 security readiness handoff with
  exact commit, verification commands/results, ordinary evidence paths,
  interface versions, runtime provenance, accepted residual risks, and known
  limitations, plus one manifest mapping every shared/security scene ID to its
  exact record and result.
- **FR-015**: The slice MUST name acceptance scenes and ordinary-path evidence
  requirements for authorization, revocation, restart recovery, credentials,
  send safety, stale runtime detection, live probes, adversarial content, and
  risk acceptance, and MUST audit the security-relevant obligation in every
  shared scene S01-S16 without taking final parity ownership from slice `110`.
- **FR-016**: The slice MUST preserve the SpecKit control-plane/product-artifact
  boundary and MUST NOT execute any task before explicit Goal 2 authorization.
- **FR-017**: When an assurance control fails, the slice MUST return a precise
  mitigation request to the accountable owner of the failing artifact, wait for
  an explicit repaired-commit handoff, and re-audit; it MUST NOT implement the
  product mitigation itself.
- **FR-018**: The slice MUST prove that only trusted operator configuration can
  produce `status: bypass` with cause `preattention-disabled`; every valid bypass
  MUST make zero classifier calls, route one advice-free
  `PREATTENTION_BYPASS` participant turn, record `classifier_not_invoked`, and
  contain no classifier/effective disposition, advice, reasons, audit, or model
  evidence. Any room/request-controlled bypass claim MUST fail closed as
  untrusted rather than gaining operator authority.
- **FR-019**: The slice MUST audit `I-010E` as immutable, append-only,
  request-correlated `observation`, `attention`, `participant-host`, and
  `transport` stages. Each stage owner MUST attest only its own execution, MUST
  NOT mutate prior records or fill future stages, and MUST leave unknown,
  unavailable, silence, and unobserved transport outcomes explicit.

### Key Entities

- **Suppression Authorization**: Operator-owned grant binding one participant,
  surface, proxy configuration, validity state, and revocation state; it is not
  room content or social policy.
- **Security Threat**: Stable threat identifier, trust boundary, affected
  surface, mitigation, deterministic evidence, live/adversarial evidence,
  residual risk, and disposition.
- **Runtime Provenance Record**: Intended and observed commit/package/schema,
  executable and hook identities, configuration fingerprint, restart status,
  probe result, timestamp, and surface.
- **Security Readiness Handoff**: Versioned bundle of upstream interface hashes,
  threat dispositions, commands, evidence references, accepted risk, and known
  limitations handed to slice `110`.
- **Security Evidence Manifest**: Mapping from `S01`-`S16`, `SEC-A`, `SEC-B`,
  and `SEC-C` to exact candidate commits, commands, record paths, attempts, and
  pass/block dispositions; consolidated records remain traceable through stable
  `scene_id`.
- **Receipt Stage Attestation**: Immutable request-correlated record naming one
  of the four canonical stages, its accountable writer, directly observed facts,
  and explicit unknown/unavailable values; it never certifies another owner's
  execution.
- **Mitigation Handback**: Threat/control finding, responsible owner lane,
  affected commit/interface, required evidence, repaired commit, and re-audit
  disposition; it is not a reverse dependency on slice `100`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of handed-off V2 surfaces refuse social suppression when any
  required authorization or recoverability condition is missing and record a
  wake/defer outcome instead.
- **SC-002**: Authorization and revocation acceptance scenes pass before and
  after restart on every surface that enables social suppression, with no loss
  of ordinary observation continuity.
- **SC-003**: 100% of sending surfaces pass repeated-send/backstop scenes while
  preserving separate operational and social telemetry.
- **SC-004**: 100% of request-controlled credential, endpoint, executable, and
  identity override attempts are rejected without secret material appearing in
  committed output.
- **SC-005**: Every surface has a committed provenance record and live V2 probe
  identifying the intended installed runtime before slice `110` accepts it.
- **SC-006**: Every enumerated threat has one traceable disposition: tested
  mitigation or explicit Zoe-accepted residual risk; the count of unexplained
  threats is zero.
- **SC-007**: The selected adversarial matrix completes with all failures and
  run-to-run variation reported across at least five retained attempts for every
  stochastic cell; every result is reproducible from committed runner/corpus
  versions, exact provider/model IDs, timestamps, and documented commands.
- **SC-008**: The V2 security readiness handoff is accepted by `v2-integrator`
  with zero unresolved CRITICAL/HIGH security or provenance findings.
- **SC-009**: 100% of trusted bypass probes make zero classifier calls, invoke
  one act-or-silence participant turn, carry no fabricated social result/advice,
  and reject every room/request-controlled bypass attempt.
- **SC-010**: 100% of audited receipt chains preserve request correlation and
  single-writer stage ownership with zero cross-stage mutation, speculative
  future-stage completion, or fabricated delivery for participant silence.

## Assumptions

- Slices `010` through `090` will hand off exact commits, interface versions,
  commands, evidence references, provenance notes, and limitations before this
  slice begins assurance execution.
- Operator authorization and credentials remain outside room-controlled data.
- The attention-model families are the slice-`030` selected Gemini 3.1 Flash
  Lite, GPT-5.5, and Qwen3 families. Exact provider/model IDs are pinned in each
  run record. Every stochastic model/scene/configuration cell runs at least five
  independent repetitions with all attempts retained unless Zoe explicitly
  approves a different pre-registered matrix before execution.
- The assurance worktree starts from the exact accepted slice-`010` contract/
  integration baseline commit. Slices `020`-`090` remain immutable handoff refs
  and installed artifacts in the audit manifest; slice `100` does not merge or
  rewrite them.
- Zoe alone may explicitly accept any residual risk that remains after
  evidence-backed mitigation review.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` only audited suppression-governance,
  operational-safety, provenance, accepted-risk, limitation, and evidence-grade
  deltas to `v2-integrator`.
- **Affected ordinary docs**: `UPDATE` `SECURITY.md`,
  `docs/security/assurance-handoffs.md`,
  `docs/security/operational-safety.md`,
  `docs/security/runtime-provenance.md`,
  `docs/security/suppression-governance.md`, and
  `docs/security/threat-model-v2.md`. `HANDOFF` exact audited security,
  provenance, limitation, accepted-risk, current-state, and breaking-change
  deltas for `CHANGELOG.md`, `docs/INSTALL.md`, `docs/integration.md`,
  `docs/STABILITY.md`, and `docs/architecture/v2-selected-design.md` to
  accepting `v2-integrator`; stale or overclaimed documentation is blocking.
- **Handoff evidence**: `evidence/v2/security/integrator-handoff.md` records
  exact reviewed paths, dispositions, delta, validation, reviewer, and
  acceptance/rejection.

## Explicit Exclusions

- Implementing any V2 product behavior during Goal 1.
- Defining social relevance rules, mention/reply heuristics, reply obligations,
  a governance-profile library, or a participant registry.
- Reply composition, moderation, content safety, or tool-policy enforcement for
  the participant model.
- Replacing upstream slice-owned contracts or adapter behavior without an
  explicit owner handback.
- Implementing product mitigations or editing `src/`, `schemas/v2/`, or
  `integrations/`; slice `100` owns assurance tests/evals, evidence, threat
  documentation, and audit handoffs only.
- Final atomic integration, parity adjudication, release/version selection, or
  promotion; those belong to slice `110` or a later owner decision.
- Posting security claims, launch material, or community communications.
