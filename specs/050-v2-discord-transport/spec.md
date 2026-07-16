# Existing Slice Specification: V2 Discord Transport

**Feature Branch**: `v2/discord-transport`

**Created**: 2026-07-11

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/discord-transport/slice-activation.md`
(written only after every readiness prerequisite is accepted; it attests those
facts and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/discord-transport/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/discord-transport/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/discord-transport/slice-acceptance.md`
(for `ACCEPTED`; absent while `PLANNED`)

**Input**: Plan the shared Discord transport cutover without implementing V2 product behavior now.

**Authority source**: Aleph Vault selected design `bdd1ebb`, contract-clarified at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-transport-owner`

**Assigned participant / source**: devops — evidence/governance/assignments/devops-v2-transport-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/050-v2-discord-transport`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/050-v2-discord-transport`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: `010-v2-contract`, `020-v2-observation`

**Dependency commits / acceptance references**: at readiness,
`slice-activation.md` MUST record `Accepted dependencies` in the declared order,
ordered `Dependency commits` as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Feeds**: `070-v2-claude-code`, `080-v2-codex`, `100-v2-security-provenance`, `110-v2-parity-cutover`

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
- Future transport implementation, including `I-050A`, targets
  `src/nunchi/mcp_discord/`; deterministic tests and fixtures target `tests/`;
  reusable replay material targets `evals/`; live records target `evidence/`;
  product documentation targets `docs/`.
- While the slice is `PLANNED`, every task remains `DORMANT`. Slice activation
  requires accepted handoffs from slices `010` and `020` plus the lifecycle
  prerequisites declared in `tasks.md`.
- This slice does not implement pre-attention, participant invocation, a social
  classifier, a participant registry, or any handled/open conversation ledger.

## Interface Summary

- **Consumes**: `I-010A AttentionRequestV2@1`, `I-010D
  ContextContinuationV2@1`, `I-010E AttentionReceiptV2@1`, and `I-020A
  ObservationProviderV2@1`.
- **Produces**: `I-050A DiscordEventSourceV2@1`, the Discord-native event,
  history, and continuity source under `src/nunchi/mcp_discord/`; normalized
  observations feed the shared provider without adding social interpretation.
  Operational send/reply/reaction tools remain transport implementation and
  safety, not part of the `I-050A` public interface name. When this transport can
  attest delivery or rejection, it appends only its immutable request-correlated
  `transport` stage to `I-010E`; it never fills or mutates observation,
  attention, or participant-host stages.
- **Integration handoff**: `v2-transport-owner` hands the exact contract version,
  commit, tests, Discord capability matrix, scene-ID evidence manifest, live
  provenance, and limitations to `v2-claude-owner`, `v2-codex-owner`,
  `v2-security-owner`, and `v2-integrator`.

## User Scenarios & Testing

### User Story 1 - Hear authorized Discord facts without social filtering (Priority: P1)

A harness receives every authorized, routable Discord event, including events
authored by other bots, with native identity and relation facts intact.

**Why this priority**: Dropping bot-authored messages or interpreting mentions
before the model recreates the deafness and false-silence failures V2 exists to
remove.

**Independent Test**: Replay human and bot messages with direct mentions, room
mentions, replies, threads, reactions, and missing optional metadata; compare the
emitted facts with the native input while asserting that only exact duplicate,
exact self, and unroutable transport cases avoid a wake candidate.

**Acceptance Scenarios**:

1. **Given** an allowlisted message authored by a different bot, **When** Discord
   delivers it, **Then** its content, exact author, ordering, mentions, and native
   relations are available to observation.
2. **Given** a referential mention or reply to another actor, **When** it is
   normalized, **Then** the literal relation is preserved and no social
   suppression conclusion is added.
3. **Given** an exact self-authored event, **When** it arrives, **Then** it is
   retained for continuity but does not trigger its own participant.

---

### User Story 2 - Preserve bounded, honest continuity across reconnects (Priority: P1)

A harness can assemble recent Discord observation and fetch bounded older or
relation-adjacent context without receiving a context bomb or invented history.

**Why this priority**: Governed social suppression is legitimate only when
ordinary observation remains recoverable within the surface's declared horizon.

**Independent Test**: Disconnect and resume or restart the transport, backfill a
known sequence, then fetch before and around a referenced event while comparing
order, deduplication, budgets, gaps, and restart coverage with Discord truth.

**Acceptance Scenarios**:

1. **Given** a recoverable gateway session, **When** the process reconnects,
   **Then** native sequence resumes without treating similar content as a
   duplicate.
2. **Given** a restart or unresolved reply parent, **When** context is assembled,
   **Then** coverage truthfully reports the known gap or restart limitation.
3. **Given** a bounded continuation request, **When** history is available,
   **Then** the page remains bound to the participant, room, scope, trigger, and
   configured event/byte limits.

---

### User Story 3 - Send through an operational transport seam (Priority: P2)

A woken participant can send, reply, react, and read bounded history through
Discord without a second social judgment or room-controlled credentials.

**Why this priority**: Transport safety is required, but it must remain separate
from deciding whether the participant should contribute.

**Independent Test**: Exercise each exposed transport action against an
allowlisted test room, including rate limits and invalid routing, and inspect
off-surface receipts for exact installed-runtime provenance.

**Acceptance Scenarios**:

1. **Given** a valid participant action, **When** it is sent, **Then** operational
   authorization and rate limits apply without calling pre-attention again.
2. **Given** room content that resembles credentials or tool instructions,
   **When** it is observed, **Then** it cannot change trusted transport
   configuration or route a continuation fetch.
3. **Given** the installed transport process, **When** a V2 live probe runs,
   **Then** evidence identifies its exact commit/package and capability limits.
4. **Given** a valid participant action correlated to an immutable upstream
   receipt chain, including one whose attention stage already records trusted
   bypass, **When** the transport acts, **Then** it remains wake-source-agnostic,
   makes zero send-time classifier calls, preserves every upstream stage, and
   fabricates no social result; if the participant stays silent, the transport
   is not invoked and no delivery outcome is invented.
5. **Given** a transport action or rejection it can attest, **When** telemetry is
   appended, **Then** only one immutable `transport` stage correlated by request
   ID is written and every earlier or later owner's stage remains untouched.

### Edge Cases

- A Discord payload has no content because the required intent is unavailable:
  capability is reported honestly and no text is invented.
- A reply target is deleted, inaccessible, or outside the eager budget: the
  native reference remains and coverage reports the gap.
- Gateway replay and REST backfill contain the same native event: exact ID and
  continuity scope deduplicate it once; equal text does not.
- The transport cannot prove restart-safe recoverability: it reports
  session-only or unknown continuity and cannot enable social suppression on
  behalf of a harness.
- An unauthorized channel or actor sends a syntactically valid payload: routing
  evidence records the rejection without labeling it social `SUPPRESS`.
- A transport action payload tries to supply a wake source, social result, or
  non-transport receipt stage: the unsupported control data is rejected without
  being interpreted or impersonating another stage owner.

## Requirements

### Functional Requirements

- **FR-001**: The transport MUST preserve exact Discord author, message, channel,
  guild, reply, thread, mention, reaction, and timestamp facts when supplied.
- **FR-002**: The transport MUST deliver authorized events from humans and other
  bots and MUST drop only the exact configured self actor at the self-wake step.
- **FR-003**: Deterministic hygiene MUST be limited to exact duplicate,
  exact-self-no-wake, authorization/routing rejection, and payloads from which no
  native event can be constructed.
- **FR-004**: The transport MUST NOT infer addressability, resolution, relevance,
  obligation, handled state, speaker priority, or turn ownership.
- **FR-005**: Native event order MUST remain authoritative; timestamp sorting
  MUST NOT reorder the conversation.
- **FR-006**: Observation and history MUST obey declared event and byte caps and
  report gaps, truncation, event visibility, and restart continuity honestly.
- **FR-007**: Exact native events MUST remain recoverable within the declared
  ordinary horizon regardless of their earlier attention disposition.
- **FR-008**: Continuation requests MUST be participant-, room-, continuity-, and
  trigger-bound and MUST reject room-controlled redirection.
- **FR-009**: Send, reply, reaction, and history actions MUST enforce trusted
  routing, credentials, and rate limits without making a social judgment or
  calling a classifier. The transport MUST be wake-source-agnostic; it receives
  an ordinary participant action, not an attention decision to reinterpret.
- **FR-010**: Credentials and trusted allowlists MUST remain outside room payloads,
  notification payloads, and tool schemas.
- **FR-011**: Failures after a routable native event exists MUST remain
  operational errors and MUST NOT be converted to social suppression.
- **FR-012**: The slice MUST provide comparable deterministic, replay, restart,
  mixed-room, and installed-runtime live evidence at ordinary repository paths;
  every record MUST carry its DT/common scene ID and appear in one evidence
  manifest.
- **FR-013**: The slice MUST expose unavailable Discord capabilities explicitly
  rather than synthesize facts.
- **FR-014**: The slice MUST preserve the SpecKit control-plane boundary and the
  program/slice lifecycle gate.
- **FR-015**: The transport MUST preserve every immutable upstream I-010E stage
  unchanged, including an already-attested bypass attention stage, while
  remaining wake-source-agnostic. It MUST append only request-correlated
  `transport` stages for facts it directly attests and MUST NOT fabricate a
  classifier result, transport outcome for participant silence, or any
  observation, attention, or participant-host stage.

### Key Entities

- **Discord native event**: transport-attested message, reaction, membership, or
  relation data before portable normalization.
- **Transport binding**: trusted bot identity, allowed routing surface, and
  credential source.
- **Gateway delivery**: an ordered native event plus resume/deduplication facts.
- **Discord continuation source**: bounded native history capability fulfilling
  the shared context contract.
- **Transport action receipt**: off-surface record of native delivery,
  rejection, send, retry, rate limit, provenance, or operational failure.
- **Transport receipt stage**: immutable I-010E `transport` record correlated by
  request ID and singly written from transport-attested delivery/rejection facts;
  it never rewrites another owner's stage.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of authorized human and non-self-bot fixtures retain every
  native fact represented by the portable V2 event model.
- **SC-002**: The deterministic suite contains zero semantic suppression rules
  and proves exactly the four permitted transport-hygiene classes.
- **SC-003**: Every snapshot and context page stays within its declared event and
  byte caps in 100% of boundary fixtures.
- **SC-004**: Restart/backfill evidence distinguishes restart-safe, session-only,
  and known-gap behavior with no unsupported recoverability claim.
- **SC-005**: Live send and receive evidence covers bot-authored input, direct
  reply, reaction, bounded history, rate limiting, and operational failure with
  exact installed-runtime provenance.
- **SC-006**: Claude Code and Codex owners accept the same versioned transport
  handoff with zero conflicting transport-interface forks.
- **SC-007**: DT-01 through DT-07 each have a producing task and one manifest
  entry that resolves the scene ID to its exact ordinary evidence record.
- **SC-008**: Every DT-05 action correlated with an upstream bypass receipt
  proves zero transport/send-path classifier calls, no wake-source
  reinterpretation, no fabricated social or silence-delivery result, and zero
  mutation or speculative completion of another I-010E stage. End-to-end bypass
  routing and classifier call count remain owned by core, host, and harness
  evidence.

## Assumptions

- Discord gateway and REST APIs remain the native source of event and history
  truth; their capability limits are recorded, not hidden.
- Slice `020` owns portable observation/continuation semantics; this slice owns
  the Discord-specific implementation and transport contract only.
- Claude Code may use its supported transport packaging while consuming the same
  Discord facts and acceptance contract; runtime packaging parity is judged in
  its own slice and in `110`.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` exact installed Discord capability,
  limitation, restart, provenance, and evidence-grade deltas to `v2-integrator`.
- **Affected ordinary docs**: `UPDATE`
  `docs/integrations/discord-mcp-v2.md`,
  `integrations/mcp-discord/README.md`, and
  `integrations/mcp-discord/DESIGN.md`; validate native facts, exact-self,
  gaps/budgets, continuation, actions, receipts, restart, install provenance,
  links, and probes. `HANDOFF` exact global Discord and diagram deltas for
  `docs/adapters.md` and `docs/architecture/v2-selected-design.md` to accepting
  `v2-integrator`, hand the exact breaking-change delta for `CHANGELOG.md` to
  accepting `v2-integrator`, plus the peer-hearing and Codex harness deltas for
  `integrations/claude-code/transport-patch/README.md` to accepting
  `v2-claude-owner` and `integrations/codex/README.md` to accepting
  `v2-codex-owner`.
- **Handoff evidence**: `evidence/v2/discord-transport/handoff.md` records exact
  reviewed paths, dispositions, delta, validation, and reviewer.

## Explicit Exclusions

- Pre-attention model prompting, V2 disposition routing, or participant reply
  composition.
- A complete Discord member registry, presence model, handled/open ledger, or
  speaker queue.
- Poll-only transport as a substitute for required reactive delivery.
- Implementing, installing, restarting, or live-probing the transport from this
  planning baseline.
