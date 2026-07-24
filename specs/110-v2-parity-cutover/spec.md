# Existing Slice Specification: V2 Parity and Atomic Cutover

> **Reference only.** Product requirements and acceptance scenes remain useful.
> Historical workflow and lifecycle instructions are retired. Follow
> `docs/v2-delivery.md`.

**Feature Branch**: `integration/v2`

**Created**: 2026-07-11

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/parity/slice-activation.md` (written only
after every readiness prerequisite is accepted; it attests those facts and
establishes `READY` before `ACTIVE`)

**Candidate evidence**: append-only
`evidence/v2/parity/slice-candidate.md` attempts (latest valid attempt supports
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: append-only `evidence/v2/parity/slice-handoff.md`
`HANDOFF_READY` and `REJECTED` attempts (absent while `PLANNED`)

**Acceptance evidence**: immutable
`evidence/v2/parity/slice-acceptance.md` (for `ACCEPTED`; absent while
`PLANNED`)

**Rework execution**: Candidate and handoff files are append-only attempt
streams. If convergence adds tasks, this slice stays `ACTIVE`, retains its
immutable activation, and starts a new bound `run speckit`. If the completed
handoff is rejected, the recorder appends `REJECTED`, returns the slice to
`ACTIVE`, and the owner starts a new bound run—never resume the completed run.
A paused post-convergence gate may resume only for fixes that leave the task
graph unchanged; all later attempts append without rewriting history.

**Input**: User description: "Integrate every accepted V2 slice atomically,
prove installed-runtime and behavioral parity across adapters and harnesses,
run staged mixed-room scenes, commit the evidence bundle, and make product and
release documentation truthful without doing promotion."

**Authority source**: repository-owned `docs/architecture/v2-selected-design.md`
and `docs/contracts/nunchi-v2.md`; Aleph Vault `bdd1ebb`/`c834e8c` are provenance

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-integrator`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-integrator-2026-07-23.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/110-v2-parity-cutover`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/110-v2-parity-cutover`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: `010`, `020`, `030`, `040`, `050`, `060`, `070`, `080`, `090`, `100`

**Dependency commits**: activation MUST record the ordered mapping
`010=<full-sha>, 020=<full-sha>, 030=<full-sha>, 040=<full-sha>,
050=<full-sha>, 060=<full-sha>, 070=<full-sha>, 080=<full-sha>,
090=<full-sha>, 100=<full-sha>` from the exact accepted slice candidates

**Dependency acceptance references**: activation MUST record matching ordered
consumer-owned files `010=evidence/v2/parity/dependency-010-acceptance.md`
through `100=evidence/v2/parity/dependency-100-acceptance.md`; each file attests
the consumer, upstream slice/commit, accepting participant/date, exact upstream
`slice-acceptance.md`, and durable decision

**Feeds**: Final sink for the umbrella V2 program and input to a separate
release decision; no downstream implementation slice

## Control-Plane Boundary *(mandatory)*

- This directory contains planning artifacts only.
- Product source, contracts, schemas, tests, fixtures, evaluations, evidence,
  runtime assets, and documentation MUST target ordinary repository paths.
- This planning baseline creates no product behavior. Authorized slice
  implementation requires the one valid complete authorization record at
  `evidence/governance/v2-implementation-authorization.md` enumerating exactly
  slices `010` through `110`; slices `010` through `100` all in `ACCEPTED` with the
  ordered commit/reference mappings above; an
  active `v2-integrator`; an assigned participant and durable external
  assignment source declared above; zero CRITICAL/HIGH analysis findings; and
  an isolated worktree. Only after those facts are accepted does activation
  evidence attest them and establish `READY` before `ACTIVE`.
- This slice MUST NOT merge V2 code, change runtime behavior, run live room
  scenes, select or publish a release, or rewrite product documentation during
  planning or before valid slice activation.
- The final integrator assembles and adjudicates the selected design; it MUST
  NOT silently redesign an upstream interface, accept security risk for Zoe, or
  add a V1 bridge to make integration easier.

## Interface Summary *(mandatory)*

- **Consumes**:
  - `I-010A AttentionRequestV2@1`, `I-010B AttentionDecisionV2@1`,
    `I-010C ParticipantWakeV2@1`, `I-010D ContextContinuationV2@1`, and
    `I-010E AttentionReceiptV2@1` from slice `010`;
  - `I-020A ObservationProviderV2@1` from slice `020`;
  - `I-030A AttentionEngineV2@1` from slice `030`;
  - `I-040A ParticipantTurnHostV2@1` from slice `040`;
  - `I-050A DiscordEventSourceV2@1` from slice `050`;
  - reviewed implementation/evidence handoffs from `060` Hermes, `070` Claude
    Code, `080` Codex, and `090` channel adapters;
  - the blocking security assurance report, audited commit set, provenance
    records, risk dispositions, and readiness packet from slice `100`.
- **Produces**:
  - an integrated V2 candidate manifest containing the exact
    commit/package/schema/config set for the atomic repository candidate;
  - a V2 parity evidence index covering deterministic, replay, per-surface,
    installed-runtime, security, and staged-room evidence through stable scene
    IDs and one authoritative evidence manifest;
  - a V2 release-readiness boundary containing truthful version, upgrade,
    documentation, evidence, and limitation state for a separate decision; and
  - append-only slice candidate and handoff attempt streams for Zoe's separate
    repository-cutover decision; and
  - inputs to the umbrella program tail, which consumes the assigned
    integrator's slice-level copy and the assigned program owner's cutover-level
    copy of Zoe's exact-candidate decision and has the integrator record the atomic
    main merge and post-merge verification distinctly from release or promotion.
- **Integration handoff**: Each upstream owner hands its exact reviewed commit,
  commands/results, interface versions, evidence, provenance, and limitations
  to `v2-integrator`. The integrator returns semantic conflicts to the owning
  lane, assembles only accepted handoffs, and reports the final candidate to the
  umbrella program and project owner.

The outputs above are integration artifacts and evidence indexes, not product
interfaces. The canonical `I-*` registry remains exactly `I-010A`–`I-050A`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assemble One Atomic V2 Candidate (Priority: P1)

As the project owner, I receive one repository candidate in which the core,
CLI, transports, adapters, and harnesses all use the selected V2 request,
decision, wake, continuation, receipt, and lifecycle contracts, with no V1
translation bridge or mixed-version in-tree consumer.

**Why this priority**: A partially migrated repository recreates the detached
patchwork and makes every later parity result ambiguous.

**Independent Test**: Inspect and execute the repository-wide contract manifest
and V1-residue checks on the candidate. Every in-tree consumer uses canonical
V2 interfaces, retired hooks/shims are absent, and no publishable commit or
package contains a mixed contract.

**Acceptance Scenarios**:

1. **Given** all dependency handoffs are accepted, **When** the integration
   branch is assembled, **Then** its manifest pins one exact commit for every
   slice and one version for every canonical `I-010A`–`I-050A` interface.
2. **Given** any source, configuration, hook, test, or documentation path still
   invokes V1 or a send-time social reclassification, **When** atomicity checks
   run, **Then** the candidate is rejected and the finding returns to the owning
   slice.
3. **Given** all V2 slices are compatible, **When** the candidate is proposed
   for main, **Then** the integration lands as one non-mixed cutover and the
   public V1 stability claim is replaced in the same change.

---

### User Story 2 - Prove Surface Equivalence and Provenance (Priority: P1)

As an operator, I can run the same canonical scenes through the CLI, Hermes,
Claude Code, Codex, Discord-MCP, and standalone channel adapters and distinguish
real platform limitations from integration drift.

**Why this priority**: Local correctness is not Nunchi V2 success; equivalent
facts must yield equivalent observations, routing, and participant factual
availability on the actual installed runtimes.

**Independent Test**: Run S01-S13, S15, and S16 through each applicable surface,
including restart and a known live probe. Compare canonical factual outputs;
inject the same already-validated attention decisions when comparing routing
mechanics, and separately route trusted preattention bypass with no injected
social result and zero classifier calls, without defining a deterministic oracle
for the socially correct model verdict. Accept a difference only when the
platform's unavailable fact is explicitly declared.

**Acceptance Scenarios**:

1. **Given** equivalent native conversations, **When** each adapter/harness
   normalizes them, **Then** actors, event order, trigger, relations, coverage,
   and available continuation facts are equivalent or explicitly unknown.
2. **Given** the same validated attention result and factual wake input, **When**
   each harness routes it, **Then** `SUPPRESS`, `WAKE`, `DEFER`, and
   operational `ERROR` have the same lifecycle and no send-time classifier.
3. **Given** a surface has restarted with the intended build, **When** its V2
   probe runs, **Then** the evidence identifies exact commit/package/config,
   schema version, receipt, participant act-or-silence path, and transport send.
4. **Given** a platform cannot supply a reaction, membership, reply, or history
   fact, **When** parity is compared, **Then** the difference is attributed to a
   declared capability gap rather than filled by inference.
5. **Given** trusted `status: bypass` with cause `preattention-disabled`, **When**
   each applicable harness routes it, **Then** it makes zero classifier calls,
   invokes one advice-free `PREATTENTION_BYPASS` act-or-silence turn, and emits
   no fabricated classifier/effective disposition or model evidence.
6. **Given** one request-correlated lifecycle, **When** receipts are compared,
   **Then** observation, attention, participant-host, and transport remain
   immutable separately owned stages; no writer mutates an earlier stage, fills
   a later owner's stage, or invents transport delivery for participant silence.

---

### User Story 3 - Validate the Mixed Room and Truthful Release Boundary (Priority: P2)

As the project owner, I can review staged mixed-harness and multi-human room
evidence plus a complete product documentation/release boundary before deciding
whether V2 is ready, without coupling that decision to promotion.

**Why this priority**: Offline equivalence must survive organic room timing,
silence, model variation, restarts, and real participant contribution before a
release claim is credible.

**Independent Test**: Run the pinned six-stage S14 ladder—Hermes-only;
Hermes+Claude Code; Hermes+Codex; full Hermes+Claude Code+Codex; multi-human
Discord; and multi-human Telegram via Hermes—with the complete S01-S16 catalog.
Index all deterministic/live/security evidence and audit every user document and
release claim against the exact integrated candidate.

**Acceptance Scenarios**:

1. **Given** the integrated candidate, **When** all six pinned room stages run,
   **Then** agents self-select without a sustained all-speak/all-mute, deafness,
   polling-dependence, or lifecycle-drift failure and every visible action or
   silence is traceable to off-surface evidence. A failed required lifecycle
   outcome blocks cutover; only a genuinely unavailable native platform fact may
   be recorded as a non-blocking capability limitation.
2. **Given** a woken participant, **When** it contributes, reacts, uses a tool,
   or ends silently, **Then** post-hoc acceptance evaluation grades any
   meta-admission answer as failure while the runtime neither filters nor
   relabels participant prose, and no second Nunchi judgment appears.
3. **Given** all evidence is indexed, **When** documentation is reviewed, **Then**
   current behavior, limitations, upgrade break, supported surfaces, security,
   evaluation method, and release boundary match the candidate exactly.
4. **Given** release readiness is proposed, **When** the project owner reviews
   the V2 release-readiness boundary, **Then** approval or rejection remains separate
   from launch copy, community posts, marketing assets, and promotion timing.

### Edge Cases

- An upstream handoff is locally green but its interface version or evidence
  conflicts with the umbrella contract.
- Two accepted handoffs edit the same shared file with different semantics.
- The integration branch is temporarily mixed while commits are assembled; it
  must remain non-releaseable and must not merge to main in that state.
- A stale installed wheel, hook, shim, process, or configuration passes source
  tests but fails the live probe.
- Equivalent surface inputs differ only because one platform lacks a native
  fact.
- A continuation returns overlapping or post-trigger events in a different
  transport order.
- The participant remains silent after `WAKE`, `DEFER`, trusted preattention
  bypass, or operational error.
- A model flickers between valid attention outcomes across repeated scenes.
- Room content or an untrusted surface input claims bypass, forges
  `classifier_not_invoked`, or impersonates a receipt-stage owner.
- The staged room exposes a failure not represented in the replay corpus.
- Security slice `100` has an unaccepted residual risk or stale provenance.
- Documentation claims a surface or release state not established by the final
  evidence bundle.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The slice MUST accept exact reviewed handoffs from every dependency
  `010` through `100` before final candidate assembly begins.
- **FR-002**: The integration manifest MUST bind every handoff commit, canonical
  interface version, package/schema version, verification result, evidence
  index, provenance record, and known limitation.
- **FR-003**: The candidate MUST move every in-tree core, CLI, transport,
  adapter, and harness consumer to the canonical V2 contracts atomically.
- **FR-004**: The candidate MUST contain no V1 translation bridge, mixed request
  version, legacy social move routing, or send-time social classifier path.
- **FR-005**: Intermediate integration state MUST remain isolated and explicitly
  non-releaseable; only the complete V2 candidate may be proposed for main.
- **FR-006**: Semantic conflicts MUST return to the accountable upstream owner;
  the integrator MUST NOT silently rewrite an owned interface or risk decision.
- **FR-007**: Repository-wide deterministic checks MUST reject V1 residues,
  mismatched interface versions, missing surface consumers, stale hooks/shims,
  and product dependencies on SpecKit-managed paths.
- **FR-008**: The parity corpus MUST cover every shared acceptance scene S01-S16
  and identify which surfaces and evidence types apply to each scene. Every
  record MUST carry a stable `scene_id`, and one evidence manifest MUST map each
  scene/surface to exact commands, candidate refs, records, and disposition.
- **FR-009**: Equivalent platform facts MUST produce equivalent normalized
  observations, attention routing, participant factual availability, and
  receipts across all applicable adapters and harnesses. Deterministic routing
  parity MUST inject already-validated attention results and MUST NOT define or
  enforce a social-verdict oracle.
- **FR-010**: Platform differences MUST be represented as explicit unavailable
  capability or coverage, never inferred, silently dropped, or treated as a
  parity success without explanation.
- **FR-011**: Every installed surface MUST pass restart/reload and a known live
  V2 probe with exact commit/package/config/schema provenance before being
  included in the candidate.
- **FR-012**: Participant wake handling MUST support direct contribution,
  lightweight reaction/acknowledgment, tool action, and no-send without an
  intermediate meta-answer or second social judgment. Meta-answer detection MUST
  be post-hoc acceptance evaluation only; runtime MUST NOT inspect participant
  prose to block, rewrite, or relabel it.
- **FR-013**: Classifier-DEFER and margin-DEFER MUST remain separately receipted
  during their evidence-gated transition; schema cutover MUST NOT retire the
  margin without its separately agreed exit evidence.
- **FR-014**: The staged room ladder MUST cover exactly Hermes-only, Hermes plus
  Claude Code, Hermes plus Codex, the full Hermes plus Claude Code plus Codex
  room, multi-human Discord, and multi-human Telegram via Hermes, with committed
  transcripts, receipts, post-hoc outcome grades, and runtime provenance. A
  normative lifecycle failure blocks cutover; only genuinely unavailable native
  platform facts may be limitations.
- **FR-015**: The evidence bundle MUST index deterministic contracts, replay
  corpora, context budgets, security closure, per-surface probes, parity
  comparisons, staged-room runs, failures, flicker, and known limitations.
- **FR-016**: Product, integration, security, evaluation, stability, upgrade,
  and release documentation MUST be updated in the same atomic cutover and MUST
  distinguish evidence grades honestly.
- **FR-017**: The release boundary MUST identify the exact candidate/version,
  supported and reference surfaces, breaking upgrade, evidence bar, unresolved
  limitations, and go/no-go decision owner.
- **FR-018**: Release work MUST remain separate from promotion; this slice MUST
  NOT create or post launch copy, community messages, marketing assets, or a
  promotion schedule.
- **FR-019**: The slice MUST produce an integrated candidate manifest, parity
  evidence index, and release-readiness boundary without defining a new product
  interface or creating a downstream dependency back into slices `010`–`100`.
- **FR-020**: The slice MUST preserve the SpecKit control-plane/product-artifact
  and program/slice lifecycle boundaries. Its planning baseline MUST create no
  product behavior, and implementation MUST remain dormant until the slice is
  validly activated.
- **FR-021**: After assembly, the exact candidate MUST rerun slice `100`'s
  deterministic assurance suite and immutable-ref checks. Any semantic divergence
  from the audited set MUST return to the owning slice and trigger affected
  stochastic/live re-audit before parity continues.
- **FR-022**: After all slice gates pass, the assigned `v2-integrator` MUST
  append the exact candidate and handoff attempts and stop slice implementation at
  `HANDOFF_READY`. The umbrella program tail MUST require Zoe's durable
  exact-candidate acceptance, copied into slice evidence by the assigned
  `v2-integrator` and, on acceptance, into program cutover evidence only by
  `v2-program-owner`, before one atomic PR/merge to main. The merged candidate
  docs MUST remain truthful that V2 is `CUTOVER_ACCEPTED` with verification and
  final current-state wording pending; they MUST NOT claim verified-current
  behavior. The merged main
  SHA MUST pass post-merge governance, baseline, atomicity, parity, provenance,
  and docs-truth verification. The merge SHA, results, and final current-state
  documentation validation MUST land together in one docs/evidence-only
  follow-up commit/PR that changes no product source, schema, runtime, or
  behavior; only that complete follow-up establishes `CUTOVER_VERIFIED`.
  Package release and promotion remain separate decisions. If Zoe rejects the
  packet, the integrator MUST append her `REJECTED` decision to the handoff stream, the slice
  MUST return to `ACTIVE`, and the owner MUST start a new bound run rather than
  resume the completed delivery run. All later attempts MUST append without
  rewriting prior history.
- **FR-023**: Trusted `status: bypass` with cause `preattention-disabled` MUST
  make zero classifier calls on every applicable surface and MUST invoke one
  normal participant turn with advice-free source `PREATTENTION_BYPASS`. Parity
  MUST reject room/request-controlled bypass, any fabricated
  classifier/effective disposition, advice, audit, reasons, or model evidence,
  and any attempt to treat bypass as an injected social verdict.
- **FR-024**: Parity MUST validate `I-010E` as immutable, append-only,
  request-correlated `observation`, `attention`, `participant-host`, and
  `transport` stages. Each owner MUST attest only its own execution, MUST NOT
  mutate prior records or fill future stages, and MUST leave unknown,
  unavailable, participant silence, and unobserved delivery explicit.

### Key Entities

- **Integration Manifest**: Exact mapping of slice ID/owner, commit, canonical
  interfaces, package/schema/config identities, verification results, evidence,
  and limitations for one candidate.
- **Surface Capability Declaration**: Facts a surface can observe, facts it
  cannot supply, restart/backfill/continuation semantics, and installed probe
  status.
- **Parity Observation**: Scene, surface, normalized facts, attention routing,
  participant availability, receipt, expected equivalence class, explained
  differences, and evidence reference.
- **Parity Evidence Bundle**: Versioned index over all deterministic, replay,
  security, live-probe, and mixed-room evidence for the candidate.
- **Scene/Surface Evidence Manifest**: Stable `scene_id` mapping from every
  S01-S16/surface requirement to exact candidate refs, commands, records,
  post-hoc grades, evidence grade, and pass/block/native-capability disposition.
- **Lifecycle Stage Attestation**: Request-correlated parity record that names
  each canonical receipt stage, accountable writer, directly observed facts,
  and explicit unknown/unavailable values without certifying another owner's
  execution.
- **Release Boundary**: Candidate/version, component/surface tier, breaking
  upgrade, readiness evidence, limitations, and decision state, explicitly
  excluding promotion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of in-tree V2 consumers in the candidate use the same
  canonical interface versions, and repository checks find zero V1 bridge or
  mixed-version paths.
- **SC-002**: 100% of dependencies `010`–`100` have accepted handoff packets and
  exact commits in the integration manifest; unresolved semantic conflicts are
  zero before candidate acceptance.
- **SC-003**: Every applicable surface passes S01-S13, S15, and S16 deterministic
  or replay comparison, with every difference classified as an explicit
  platform capability gap or a blocking defect and with zero deterministic
  expected-social-verdict oracle.
- **SC-004**: Every installed surface passes S12 restart/provenance/probe against
  the exact candidate before it is represented as migrated.
- **SC-005**: All six pinned S14 stages have committed transcripts, receipts,
  provenance, and post-hoc grades; every normative lifecycle outcome passes and
  every non-blocking limitation is a genuinely unavailable platform fact.
- **SC-006**: S06, S07, S09, and S10 demonstrate direct contribution,
  lightweight action, silence, error wake, and no send-time reclassification on
  every harness, with meta-answer failures detected post-hoc and zero runtime
  participant-prose filter.
- **SC-007**: The V2 parity evidence index covers 100% of required S01-S16
  scenes, security closure, context-budget results, and per-surface probes with
  reproducible commands, and the scene/surface manifest has zero unresolved or
  dangling record reference.
- **SC-008**: A documentation audit finds zero statement that exceeds the final
  candidate's implementation or evidence grade.
- **SC-009**: The V2 release-readiness boundary can receive a project-owner go/no-go
  decision without any promotion artifact or posting decision being required.
- **SC-010**: Final analysis and integration review report zero unresolved
  CRITICAL/HIGH findings and zero dependency cycles.
- **SC-011**: The assembled candidate passes the slice-`100` deterministic
  assurance rerun; every changed semantic/security hash has a recorded owner
  re-audit before cutover.
- **SC-012**: One Zoe-accepted atomic PR lands the complete candidate on main and
  the recorded merge SHA passes the full post-merge verification set without
  publishing or promoting a release.
- **SC-013**: 100% of trusted bypass probes make zero classifier calls, invoke
  one advice-free act-or-silence participant turn, contain no fabricated social
  result, and reject every room/request-controlled bypass claim.
- **SC-014**: 100% of audited lifecycle receipt chains preserve request
  correlation and single-writer stage ownership with zero cross-stage mutation,
  speculative future-stage completion, or fabricated delivery for participant
  silence.

## Assumptions

- Every upstream slice will use the canonical interface IDs defined by the
  umbrella program and will hand off one reviewable commit plus evidence.
- The live-room surface set is fixed to the six stages in FR-014. All in-tree
  adapters remain contract-parity participants; genuine inability to provide a
  native fact is represented through the capability contract, not by silently
  dropping a required stage.
- Platform facts genuinely unavailable from a native API may differ when the
  capability gap is explicit and tested.
- A release/version go decision remains Zoe's; successful integration does not
  itself publish a package or authorize promotion.

## Documentation Freshness

- **`README.md` disposition**: `UPDATE`; reconcile every accepted upstream
  claim delta and describe only behavior, surfaces, limitations, and evidence
  grades proven by the exact atomic candidate.
- **Affected ordinary docs**: `UPDATE` root current-state and governance
  guidance in `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`, and `SECURITY.md`;
  shared/current guides in `docs/INSTALL.md`, `docs/STABILITY.md`,
  `docs/adapters.md`, `docs/integration.md`,
  `docs/architecture/v2-selected-design.md`,
  `docs/governance/execution-spine.md`, and `docs/archive/v1/README.md`;
  contract/evaluation transition docs in
  `docs/contracts/channel-adapter-v1.md`, `docs/contracts/nunchi-v2.md`,
  `docs/contracts/verdict-suite-data-model-v1.md`,
  `docs/contracts/verdict-suite-requirements-v1.md`,
  `docs/evaluations/verdict-suite.md`,
  `docs/evaluations/verdict-suite-runner.md`, and
  `docs/evaluations/v2-parity.md`; component guides in
  `docs/observation/v2.md`, `docs/attention/v2.md`,
  `docs/participant/v2.md`, `docs/adapters-v2.md`,
  `docs/integrations/discord-mcp-v2.md`,
  `docs/integrations/hermes-v2.md`,
  `docs/integrations/claude-code-v2.md`,
  `docs/integrations/codex-v2.md`,
  `docs/integrations/hermes-core-patch.md`, and
  `docs/integrations/hermes-core-patch-test-plan.md`; exact security/release
  files `docs/security/assurance-handoffs.md`,
  `docs/security/operational-safety.md`,
  `docs/security/runtime-provenance.md`,
  `docs/security/suppression-governance.md`,
  `docs/security/threat-model-v2.md`, and
  `docs/releases/v2-readiness.md`; and installed-surface docs
  `integrations/mcp-discord/README.md`,
  `integrations/mcp-discord/DESIGN.md`, `integrations/hermes/README.md`,
  `integrations/claude-code/README.md`,
  `integrations/claude-code/DEFER_EVAL.md`,
  `integrations/claude-code/transport-patch/README.md`, and
  `integrations/codex/README.md`. Validate links, Mermaid, examples, commands,
  install/version claims, evidence references, and truthfulness tests.
- **Handoff evidence**: `evidence/v2/parity/slice-candidate.md` and
  `evidence/v2/parity/slice-handoff.md` record the exact reviewed candidate,
  paths, validation, and reviewer before slice implementation stops at
  `HANDOFF_READY`. The assigned integrator copies Zoe's acceptance into
  `evidence/v2/parity/slice-acceptance.md`; the assigned program owner copies it
  into `evidence/v2/parity/cutover-acceptance.md`. The umbrella program tail records
  the accepted and merged candidate commits, `refs/heads/main`, exact main SHA,
  passing verification, evidence paths, documentation freshness, and final
  documentation commit in `evidence/v2/parity/post-merge-verification.md`.
- Because this slice changes global current behavior, `NO_IMPACT` and `HANDOFF`
  are invalid for the rows above.

## Explicit Exclusions

- Implementing or integrating any V2 product behavior before valid slice
  activation.
- Adding new product behavior, social policy, deterministic conversation
  heuristics, a registry/ledger, or a V1 compatibility bridge in the integrator
  slice.
- Silently repairing or redefining an upstream owner's contract, evidence, or
  security disposition.
- Treating green unit tests, a single model run, or source-only checks as parity
  or installed-runtime evidence.
- Promotion, launch copy, marketing/demo assets, community posts, posting
  identity, launch order, or promotion timing.
- Publishing a release without the separate project-owner go decision required
  by the V2 release-readiness boundary.
