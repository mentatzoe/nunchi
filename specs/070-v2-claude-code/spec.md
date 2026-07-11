# Feature Specification: V2 Claude Code Harness

**Feature Branch**: `v2/claude-code`

**Created**: 2026-07-11

**Status**: Planned for future Goal 2; implementation is not authorized under Goal 1

**Input**: Plan Claude Code V2 live-room parity, including the Station false-silence regression, without implementation now.

**Authority source**: Aleph Vault selected design `bdd1ebb`, contract-clarified at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-claude-owner`

**Depends on**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`, `050-v2-discord-transport` for live room parity

**Feeds**: `100-v2-security-provenance`, `110-v2-parity-cutover`

## Control-Plane Boundary

- This directory contains planning artifacts only.
- Future Claude Code plugin/hook assets target `integrations/claude-code/`;
  deterministic tests and fixtures target `tests/`; replay material targets
  `evals/`; live records target `evidence/`; product documentation targets
  `docs/`.
- Product tasks require explicit Goal 2 authorization and accepted handoffs from
  slices `010` through `050`.
- This slice does not own shared schemas, attention, observation, participant-turn,
  or Discord event-source contracts and creates no new public interface.

## Interface Summary

- **Consumes**: `I-010A AttentionRequestV2@1`, `I-010B
  AttentionDecisionV2@1`, `I-010C ParticipantWakeV2@1`, `I-010D
  ContextContinuationV2@1`, `I-010E AttentionReceiptV2@1`, `I-020A
  ObservationProviderV2@1`, `I-030A AttentionEngineV2@1`, `I-040A
  ParticipantTurnHostV2@1`, and `I-050A DiscordEventSourceV2@1`.
- **Produces**: a Claude Code conformance implementation and evidence packet for
  those interfaces, including preservation of the immutable request-correlated
  `I-010E` stage chain; no new cross-slice public interface and no Claude-wrapper
  receipt stage that the wrapper cannot itself attest.
- **Integration handoff**: `v2-claude-owner` supplies exact plugin, transport
  patch, hook, Claude Code, Nunchi package, and configuration provenance with
  deterministic/live evidence and a complete CC/common-scene manifest to
  `v2-security-owner` and `v2-integrator`.

## User Scenarios & Testing

### User Story 1 - Hear the live Discord room reactively (Priority: P1)

Claude Code receives authorized human and other-bot room events through its
native reactive transport path, with exact identity and relations intact and no
polling loop.

**Why this priority**: The lived Claude/Station failure began with being deaf or
mechanically silenced in a room containing other agents.

**Independent Test**: Deliver allowlisted human and bot messages with replies,
mentions, and missing optional facts through the installed transport/hook; prove
reactive receipt, exact self handling, native ordering, and `I-050A` parity.

**Acceptance Scenarios**:

1. **Given** an allowlisted message from another bot, **When** the Claude Discord
   transport receives it, **Then** the message reaches observation with content
   and exact author facts rather than being dropped as “bot-authored.”
2. **Given** a transport notification, **When** Claude Code is eligible to
   receive it, **Then** processing is reactive and does not depend on polling the
   room.
3. **Given** an inactive-session or cold-wake limitation, **When** the scene is
   evaluated, **Then** capability and coverage are reported honestly rather than
   claiming a wake that the harness cannot perform.

---

### User Story 2 - Preserve model nuance before the Claude turn (Priority: P1)

Claude's participant-shaped pre-attention model receives truthful bounded facts
and alone decides social suppression; the hook does not encode a mention,
reply-obligation, or apparent-resolution algorithm.

**Why this priority**: Algorithmic gating silenced Claude/Station precisely when
the social situation required model nuance.

**Independent Test**: Replay the Station scars—referential mention, other
addressee, apparent resolution, soft class address, and ambiguous continuation—
and inspect the one `I-030A` call and resulting `I-010B`/`I-010E` records; then
route a trusted bypass through the same `I-030A` seam and prove the engine makes
zero classifier/model calls and fabricates no social result.

**Acceptance Scenarios**:

1. **Given** a message that names another participant while remaining relevant
   to Claude, **When** pre-attention runs, **Then** literal addressing facts reach
   the model and no deterministic rule silences the turn.
2. **Given** uncertain conversational meaning, **When** the model cannot justify
   suppression, **Then** the effective route is `WAKE` or `DEFER`.
3. **Given** an earlier suppressed event, **When** later context is assembled
   within declared retention, **Then** the event remains normally hearable.
4. **Given** trusted `status: bypass` with cause `preattention-disabled`, **When**
   the hook routes the event, **Then** it makes zero classifier calls and
   preserves an attention stage marked `classifier_not_invoked` rather than
   constructing a classifier or effective disposition.

---

### User Story 3 - Act directly or stay silent in a normal Claude turn (Priority: P1)

After `WAKE`, either `DEFER`, trusted `PREATTENTION_BYPASS`, or default error
fallback, Claude receives one normal room turn and either contributes through
its usual tools or sends nothing.

**Why this priority**: Asking Claude whether it wants to contribute would produce
a meta-answer instead of participation; re-gating send would repeat the silence
failure.

**Independent Test**: Route every attention outcome through the hook and native
send path, including advice, continuation, message/reaction/tool action, silence,
and a deliberately induced meta-answer scored by evaluation rather than a
runtime prose filter.

**Acceptance Scenarios**:

1. **Given** effective `SUPPRESS`, **When** the hook routes it, **Then** no Claude
   participant turn runs and no user-visible diagnostic is emitted.
2. **Given** `WAKE`, `DEFER`, or error fallback, **When** Claude is invoked,
   **Then** it receives `I-010C` as facts plus non-authoritative attention data
   and responds to the room or ends silently.
3. **Given** a valid Claude send or no-send choice, **When** the turn finishes,
   **Then** no second social classifier or per-trigger permission gate runs.
4. **Given** trusted `status: bypass`, **When** Claude is invoked, **Then** it
   receives source `PREATTENTION_BYPASS` exactly once with no advice or fabricated
   social result and may act directly or end silently.

### Edge Cases

- The upstream Claude Discord plugin changes and the bot-message patch no longer
  applies: installation fails closed with explicit provenance rather than using
  an unreviewed fork silently.
- Claude Code is inactive when an event arrives: the harness records its actual
  cold-wake capability and does not describe an unobserved participant turn.
- Advice text resembles a system instruction or cites a nonexistent event: it
  remains untrusted, fails validation where applicable, and cannot gain authority.
- The participant answers the wake instruction instead of the room: acceptance
  evaluation marks a meta-answer failure even if a message was technically sent;
  the harness does not block or relabel the prose at runtime.
- A context handle is replayed in another session/room: exact binding rejects it.
- A social suppression is requested before restart-safe later hearing is proved:
  effective policy widens it to `DEFER` or direct wake.
- Room content or an untrusted hook payload claims bypass, or a Claude wrapper
  attempts to rewrite an earlier receipt stage: the claim is rejected and no
  stage owner is impersonated.

## Requirements

### Functional Requirements

- **FR-001**: Claude Code MUST consume the canonical registry interfaces exactly
  and MUST NOT retain a V1 request, verdict, or compatibility bridge.
- **FR-002**: Its Discord transport path MUST deliver allowlisted messages from
  humans and other bots and preserve facts equivalent to `I-050A`.
- **FR-003**: Room receipt MUST be reactive; a polling loop MUST NOT be the normal
  live wake mechanism.
- **FR-004**: Exact Claude participant and native actor binding MUST establish
  self; aliases, display names, and class labels MUST remain loose evidence.
- **FR-005**: The hook MUST build bounded `I-010A` through `I-020A` with honest
  coverage and optional `I-010D`, retaining all ordinary observations.
- **FR-006**: The Claude integration MUST invoke `I-030A` exactly once per
  authorized routable trigger. The engine MUST run one logical classifier
  judgment on an ordinary path and zero classifier/model calls for trusted
  `status: bypass` / `PREATTENTION_BYPASS`.
- **FR-007**: The hook MUST NOT contain deterministic rules for other addressees,
  apparent resolution, direct questions, relevance, reply obligation, class
  address, or turn ownership.
- **FR-008**: Effective `SUPPRESS` MUST stop only the participant wake; `WAKE`,
  both `DEFER` sources, trusted `PREATTENTION_BYPASS`, and default error MUST
  invoke one `I-040A` turn. Bypass MUST carry no classifier/effective
  disposition or advice and MUST NOT be relabeled as a social verdict.
- **FR-009**: The Claude turn MUST receive `I-010C` facts separately from
  untrusted advice and MUST be instructed to address the room or end silently,
  not to report an admission decision; evaluation MAY flag a meta-answer, but
  runtime MUST NOT add a prose classifier or output filter.
- **FR-010**: Claude's send path MUST contain no second social judgment or
  per-trigger social permission state.
- **FR-011**: Suppressed and self-authored events MUST remain eligible for later
  observation and bound expansion within declared capability.
- **FR-012**: Cold-wake, history, restart, event-visibility, reaction, and send
  capabilities MUST be stated and evidenced honestly.
- **FR-013**: The transport patch and installed plugin/hook/package/runtime MUST
  have exact source and configuration provenance.
- **FR-014**: The slice MUST cover deterministic, Station-regression, replay,
  reactive no-polling bot-hearing, live-room, no-send, and installed-runtime
  evidence in ordinary paths; every record MUST carry its CC/common scene ID and
  be resolved by one evidence manifest.
- **FR-015**: The slice MUST preserve the control-plane and Goal 1/Goal 2 boundary.
- **FR-016**: The Claude integration MUST preserve immutable, request-correlated
  `I-010E` observation, attention, participant-host, and transport stages. It
  MUST NOT mutate an upstream stage, fill a future stage, or append a stage for
  execution it does not directly own and attest; bypass evidence MUST retain
  trusted provenance and `classifier_not_invoked`.

### Key Entities

- **Claude participant binding**: install/session identity plus exact Discord actor
  and loose participant description.
- **Inbound hook event**: native reactive room event delivered before the normal
  participant inference.
- **Claude participant turn**: one `I-040A` act-or-silence inference using
  `I-010C`.
- **Transport patch provenance**: exact upstream base, patch digest, installation,
  and compatibility result.
- **Claude receipt chain**: request-correlated immutable `I-010E` observation,
  attention, participant-host, and transport records kept off the room surface;
  the Claude wrapper preserves them and never impersonates another stage owner.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of allowlisted human and other-bot live/fixture messages reach
  observation with all representable `I-050A` facts.
- **SC-002**: The Station regression set has zero deterministic semantic filters;
  every social suppression in evidence originates from the participant-shaped
  model.
- **SC-003**: Every authorized routable trigger produces exactly one `I-030A`
  invocation; every ordinary path has one logical classifier judgment, every
  trusted bypass has zero classifier/model calls, and every path has zero
  send-time social calls.
- **SC-004**: SUPPRESS/WAKE/DEFER/PREATTENTION_BYPASS/error and
  message/reaction/tool/silence outcomes route and receipt separately in 100%
  of conformance scenes.
- **SC-005**: Live evidence demonstrates reactive no-polling delivery and states
  inactive-session/restart limitations without unsupported claims.
- **SC-006**: Every Claude parity claim cites exact plugin, patch, hook, Claude
  Code, Nunchi package, model/config, and consumed-interface provenance.
- **SC-007**: CC-01 through CC-06 each have a producing task and one manifest
  entry that resolves the scene ID to its exact ordinary evidence record.
- **SC-008**: Every bypass record proves `classifier_not_invoked`, no fabricated
  social result/advice, one act-or-silence invocation, and zero mutation or
  speculative completion of another owner's `I-010E` stage.

## Assumptions

- Claude Code retains a pre-inference hook capable of blocking an inbound turn
  and a native participant/tool path for accepted turns.
- `I-050A` is the parity contract even if Claude's supported transport packaging
  differs from the shared MCP process used by Codex.
- Cold-start wake may remain limited; truthful capability and effective policy
  are required rather than an invented guarantee.

## Explicit Exclusions

- Ownership of shared Discord transport, shared schemas, attention behavior, or
  participant-turn interfaces.
- A central speaker manager, deterministic addressing algorithm, obligation
  ledger, or participant roster.
- Kilo or other harness integrations, public promotion, or any Goal 1 product
  implementation/live installation.
