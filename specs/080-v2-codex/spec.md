# Existing Slice Specification: V2 Codex Harness

**Feature Branch**: `v2/codex`

**Created**: 2026-07-11

**Slice state**: `PLANNED`

**Program implementation authority**: `NOT_GRANTED`

**Activation evidence**: `evidence/v2/codex/slice-activation.md` (written only
after every readiness prerequisite is accepted; it attests those facts and
establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/codex/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/codex/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/codex/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Input**: Plan the Codex V2 room lifecycle, persistent participant turn, and removal of send-time social reclassification without implementation now.

**Authority source**: Aleph Vault selected design `bdd1ebb`, contract-clarified at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-codex-owner`

**Assigned participant / source**: Vigil — evidence/governance/assignments/vigil-v2-codex-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/080-v2-codex`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/080-v2-codex`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Depends on**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`, `050-v2-discord-transport`

**Dependency commits / acceptance references**: at readiness,
`slice-activation.md` MUST record `Accepted dependencies` in the declared order,
ordered `Dependency commits` as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Feeds**: `100-v2-security-provenance`, `110-v2-parity-cutover`

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
- Authorized Codex slice implementation targets `src/nunchi/integrations/` and
  `integrations/codex/`; tests and fixtures target `tests/`; reusable replay
  targets `evals/`; run records target `evidence/`; product documentation
  targets `docs/`.
- This planning baseline creates no product behavior. Authorized slice
  implementation requires the one valid complete authorization record at
  `evidence/governance/v2-implementation-authorization.md` enumerating exactly
  slices `010` through `110`; accepted handoffs from slices `010` through `050`;
  an active `v2-codex-owner`; an assigned participant and durable external assignment
  source declared above; zero CRITICAL/HIGH analysis findings; and an isolated
  worktree. Only after those facts are accepted does activation evidence attest
  them and establish `READY` before `ACTIVE`.
- This slice creates no public interface and does not own shared schemas,
  observation, attention, participant-turn, or Discord event-source contracts.

## Interface Summary

- **Consumes**: `I-010A AttentionRequestV2@1`, `I-010B
  AttentionDecisionV2@1`, `I-010C ParticipantWakeV2@1`, `I-010D
  ContextContinuationV2@1`, `I-010E AttentionReceiptV2@1`, `I-020A
  ObservationProviderV2@1`, `I-030A AttentionEngineV2@1`, `I-040A
  ParticipantTurnHostV2@1`, and `I-050A DiscordEventSourceV2@1`.
- **Produces**: a Codex conformance implementation and evidence packet for those
  canonical interfaces; no new cross-slice public interface.
- **Integration handoff**: `v2-codex-owner` hands the exact source/plugin commit,
  installed Codex/Nunchi/transport/config provenance, commands/results, scenes,
  and limitations to `v2-security-owner` and `v2-integrator`.

## User Scenarios & Testing

### User Story 1 - Stay reactively present in the Discord conversation (Priority: P1)

Codex receives `I-050A` events reactively, preserves exact room facts and bounded
continuity, and resumes the same participant conversation where the Codex runtime
supports it.

**Why this priority**: A pull-only or one-shot Codex process is not a room
participant; the selected validation requires Codex to remain in the conversation.

**Independent Test**: Deliver ordered human and bot events through the shared
Discord event source, restart transport and Codex processes, and inspect exact
self binding, observation order, continuation, persistent session identity, and
honest gaps.

**Acceptance Scenarios**:

1. **Given** a live `I-050A` event from another bot, **When** it arrives, **Then**
   Codex receives it reactively with native content, actor, mention, and reply
   facts rather than polling or flattening them into addressing prose.
2. **Given** a prior Codex participant session, **When** the next waking event is
   routed, **Then** the supported runtime resumes that conversation or records an
   explicit session reset limitation.
3. **Given** a restart/backfill boundary, **When** observation is assembled,
   **Then** coverage and later-hearing claims match actual transport/runtime
   capability.

---

### User Story 2 - Judge attention once and contribute directly (Priority: P1)

Codex receives one attention result and, when woken, uses one normal participant
turn to send an actual room action or nothing; its send path never judges the
room again.

**Why this priority**: Codex's current second classifier and per-trigger social
permission state are explicit V2 contract violations.

**Independent Test**: Route effective `SUPPRESS`, `WAKE`, both `DEFER` sources,
trusted preattention bypass, and operational error through the prompt gate, room
runner, persistent session, MCP actions, no-send path, and retired send gate
while counting model calls and inspecting immutable receipt stages.

**Acceptance Scenarios**:

1. **Given** effective `SUPPRESS`, **When** Codex routes it, **Then** no participant
   turn runs, while the event remains available to later observation.
2. **Given** `WAKE`, either `DEFER`, `PREATTENTION_BYPASS`, or default error
   fallback, **When** Codex is invoked, **Then** exactly one I-010C turn may
   message, reply, react/use a tool, or end silently without an intermediate
   admission answer; bypass makes zero classifier calls and no model claim.
3. **Given** a participant action, **When** it reaches the send path, **Then**
   only operational safety applies and no Nunchi classifier or per-trigger social
   permission lookup runs.

---

### User Story 3 - Install and prove the complete Codex plugin path (Priority: P2)

An operator can install one reviewed Codex plugin/configuration, remove retired
V1 hooks and state, restart the real processes, and prove the V2 lifecycle in a
mixed Discord room.

**Why this priority**: Source tests cannot show that the active Codex plugin,
MCP connection, process, and persistent session use the intended code.

**Independent Test**: Install from an exact commit, inspect enabled hooks/MCP and
environment, remove V1 residue, restart, run the common scenes with Hermes and
Claude Code, and capture installed identities in every receipt.

**Acceptance Scenarios**:

1. **Given** an installed Codex plugin, **When** a known schema-2 probe arrives,
   **Then** the receipt identifies exact plugin, source/package, Codex, transport,
   model/config, and consumed-interface versions.
2. **Given** retired prompt/send hooks or V1 social permission state, **When** the
   cutover audit runs, **Then** the candidate fails until that residue is removed.
3. **Given** a mixed-agent soft class address, **When** the room scene runs,
   **Then** Codex is neither mechanically muted nor forced to speak, and its
   participant-shaped turn remains independent.

### Edge Cases

- Codex session state is unreadable, stale, or belongs to another room: the
  participant wakes through an explicit safe session path and the limitation is
  receipted; social suppression is not fabricated.
- A transport notification is repeated after reconnect: exact native event
  identity prevents a second attention call; similar text remains distinct.
- The participant chooses silence after any waking route: no send receipt is
  required to legitimize that choice, but host outcome is recorded off-surface.
- Room content forges a wake packet, receipt, continuation handle, or send
  permission: trusted structured boundaries reject or ignore the forgery.
- Operational send safety rejects an action: it reports an operational failure
  without turning it into a social verdict.
- An interactive prompt-hook path and long-running room-runner path are both
  installed: they must consume the same interfaces and cannot double-process one
  native trigger.

## Requirements

### Functional Requirements

- **FR-001**: Every in-tree Codex integration path MUST consume the canonical
  interface versions and MUST NOT retain a V1 compatibility bridge.
- **FR-002**: Codex MUST receive authorized human and other-bot room events
  reactively through `I-050A` with exact native identity and relation facts.
- **FR-003**: Exact participant/native actor binding MUST establish self;
  display names, aliases, and class labels MUST remain loose evidence.
- **FR-004**: Codex MUST implement bounded `I-020A` observation with honest
  restart, event-visibility, order, gap, and `I-010D` capability.
- **FR-005**: Each exact routable trigger MUST cause exactly one I-030A route
  across prompt-hook and room-runner paths; when trusted configuration returns
  bypass, the route MUST make zero classifier calls and use
  `PREATTENTION_BYPASS`.
- **FR-006**: Effective `SUPPRESS` MUST stop only the participant wake; `WAKE`,
  both `DEFER` sources, trusted `PREATTENTION_BYPASS`, and default `ERROR` MUST
  invoke one I-040A turn.
- **FR-007**: The Codex participant turn MUST receive structured `I-010C` facts
  and untrusted advice separately and MUST be instructed to act on the room or
  end silently; evaluation MAY flag a meta-answer, but runtime MUST NOT inspect
  participant prose to block or relabel it.
- **FR-008**: Codex MUST preserve or truthfully reset its participant conversation
  session without using receipts as social memory.
- **FR-009**: The send path MUST remove every classifier call, confidence check,
  per-trigger social permission record, and addressed/handled state.
- **FR-010**: Operational send authorization, rate limits, and backstops MAY
  remain but MUST report failures separately from `I-010B`.
- **FR-011**: Suppressed/self events MUST remain ordinarily observable within the
  declared transport horizon and must not require disposition-derived retention.
- **FR-012**: Prompt hook, room runner, plugin packaging, MCP transport, and
  persistent session MUST avoid double-processing the same native event.
- **FR-013**: Codex MUST preserve the correlated immutable I-010E observation,
  attention, participant-host, and transport records emitted by their named
  seams, including classifier-not-invoked bypass provenance. It MUST NOT flatten,
  overwrite, or infer a stage it cannot attest.
- **FR-014**: The installed cutover MUST remove V1 hooks, shims, cached package
  residue, and social permission state before a Codex migration claim.
- **FR-015**: The slice MUST provide deterministic, replay, persistent-session,
  mixed-room, no-send, adversarial, and installed-runtime evidence in ordinary
  paths.
- **FR-016**: The slice MUST preserve the control-plane/product-artifact and
  program/slice lifecycle boundaries; its planning baseline MUST create no
  product behavior.

### Key Entities

- **Codex participant binding**: stable Nunchi participant, exact Discord actor,
  loose descriptors, and trusted configuration source.
- **Codex room session**: operational participant-conversation identifier and
  room binding, never a social permission registry.
- **Codex participant turn**: one direct `I-040A` act-or-silence execution.
- **Codex plugin installation**: exact hook, app, MCP, source/package, and runtime
  configuration activated for a live process.
- **Codex receipt stream**: off-surface `I-010E` records across transport,
  attention, host, participant, expansion, and send.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of authorized fixture/live Discord events retain every
  representable `I-050A` fact and exact self binding.
- **SC-002**: Each unique native trigger causes at most one attention call and
  zero send-time social calls across all Codex paths.
- **SC-003**: SUPPRESS/WAKE/DEFER/PREATTENTION_BYPASS/error and action/silence
  outcomes produce the specified zero-or-one participant invocation in 100% of
  conformance scenes, with zero classifier calls on bypass.
- **SC-004**: Persistent-session and restart scenes either resume the exact room
  conversation or emit an explicit, evidenced reset/gap with no false claim.
- **SC-005**: Adversarial fixtures produce zero room-controlled changes to trusted
  config, continuation binding, receipt identity, or send authorization.
- **SC-006**: Every live Codex migration claim cites exact installed source/plugin,
  package, Codex, transport, process, model/config, and interface provenance.

## Assumptions

- The supported Codex runtime provides the plugin/hook, MCP client, and
  persistent-session seams required by the accepted V2 design.
- `I-050A` is the sole shared Discord source; this slice does not fork transport.
- Operational session persistence remains useful, but it never authorizes a send
  or records whether a conversation item is handled.

## Documentation Freshness

- **`README.md` disposition**: `HANDOFF` exact Codex V2 session,
  no-social-send-gate, provenance, limitation, and evidence-grade deltas to
  `v2-integrator`.
- **Affected ordinary docs**: `UPDATE` `docs/integrations/codex-v2.md` and
  `integrations/codex/README.md`; validate install/plugin/session,
  configuration, removal of the outbound social re-gate, residue/restart,
  links, examples, and probes. `HANDOFF` exact current-state and breaking-change
  deltas for `CHANGELOG.md`, `docs/adapters.md`, `docs/integration.md`, and
  `docs/architecture/v2-selected-design.md` to accepting `v2-integrator`, plus
  the Codex harness configuration delta in `integrations/mcp-discord/README.md`
  to accepting `v2-transport-owner`.
- **Handoff evidence**: `evidence/v2/codex/handoff.md` records reviewed paths,
  dispositions, exact delta, validation, and reviewer.

## Explicit Exclusions

- Shared Discord transport, shared schemas, core attention, or participant-turn
  implementation owned by upstream slices.
- A second social classifier, per-trigger social permission ledger, central
  speaker manager, or response-obligation queue.
- Public promotion, package release, or implementation/live installation before
  this slice is validly activated.
