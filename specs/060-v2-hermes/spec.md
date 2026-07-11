# Feature Specification: V2 Hermes Harness

**Feature Branch**: `v2/hermes`

**Created**: 2026-07-11

**Status**: Planned for future Goal 2; implementation is not authorized under Goal 1

**Input**: Plan Hermes V2 participant-turn parity without changing current behavior now.

**Authority source**: Aleph Vault selected design `bdd1ebb`, contract-clarified at `c834e8c`

**Umbrella program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-hermes-owner`

**Depends on**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`

**Feeds**: `100-v2-security-provenance`, `110-v2-parity-cutover`

## Control-Plane Boundary

- This directory contains planning artifacts only.
- Future Hermes plugin code targets `integrations/hermes/`; tests and fixtures
  target `tests/`; replay material targets `evals/`; live records target
  `evidence/`; product documentation targets `docs/`.
- No task may begin until Goal 2 is explicitly authorized and slices `010`
  through `040` have supplied accepted versioned handoffs.
- This slice does not own the shared V2 schemas, attention model, observation
  algorithm, or participant-turn contract and creates no new public interface.

## Interface Summary

- **Consumes**: `I-010A AttentionRequestV2@1`, `I-010B
  AttentionDecisionV2@1`, `I-010C ParticipantWakeV2@1`, `I-010D
  ContextContinuationV2@1`, `I-010E AttentionReceiptV2@1`, `I-020A
  ObservationProviderV2@1`, `I-030A AttentionEngineV2@1`, and `I-040A
  ParticipantTurnHostV2@1`.
- **Produces**: a Hermes conformance implementation and evidence packet for the
  consumed interfaces; no new cross-slice public interface.
- **Integration handoff**: `v2-hermes-owner` hands an exact plugin commit,
  installed-profile provenance, commands/results, conformance evidence, and
  limitations to `v2-security-owner` and `v2-integrator`.

## User Scenarios & Testing

### User Story 1 - Observe as the exact Hermes participant (Priority: P1)

Each Hermes profile supplies its exact host identity and current transport actor
binding, then contributes truthful native room events to bounded observation.

**Why this priority**: Multiple participant profiles and loose class names must
not collapse into alias-based self detection or shared social state.

**Independent Test**: Run two Hermes profiles with overlapping loose names and
different native actor IDs; assert authorship, self-no-wake, mentions, replies,
and observation buffers remain bound to the exact profile and room.

**Acceptance Scenarios**:

1. **Given** two Hermes profiles named as the same class, **When** one authors a
   room event, **Then** only exact native binding establishes self-causation.
2. **Given** an event previously effective-`SUPPRESS`, **When** a later event is
   assembled within the declared horizon, **Then** the earlier event remains
   ordinarily observable without a suppression-derived ledger.
3. **Given** unavailable native membership or relation facts, **When** Hermes
   creates a request, **Then** coverage reports them as unavailable or unknown.

---

### User Story 2 - Wake into one normal Hermes participant turn (Priority: P1)

Hermes routes the one attention result into a normal participant turn that may
act naturally or end silently, without asking the participant to answer an
admission question.

**Why this priority**: Attention and contribution must have different owners;
the harness is responsible for preserving that handoff.

**Independent Test**: Feed valid `SUPPRESS`, `WAKE`, classifier-`DEFER`,
margin-`DEFER`, trusted preattention bypass, and operational-error results into
the plugin and inspect model-call count, participant invocation, supplied facts/
advice, tool actions, silence, and immutable receipt stages.

**Acceptance Scenarios**:

1. **Given** effective `SUPPRESS`, **When** Hermes routes it, **Then** no
   participant turn runs and the event remains observable later.
2. **Given** `WAKE`, either form of `DEFER`, trusted preattention bypass, or
   default error fallback, **When** Hermes routes it, **Then** exactly one normal
   participant turn receives `I-010C` facts and may send, react, use a tool, or
   end silently; bypass uses `PREATTENTION_BYPASS` and makes no model claim.
3. **Given** attention advice, **When** the participant is invoked, **Then** the
   advice remains separate untrusted annotation and cannot become an instruction
   or reply draft.

---

### User Story 3 - Prove multi-profile and installed-runtime parity (Priority: P2)

An operator can install the exact Hermes plugin, run several profiles in shared
rooms, restart them, and verify V2 lifecycle and provenance on Discord and a
Hermes-native Telegram surface.

**Why this priority**: Source-level success is insufficient; Hermes is a live
multi-agent validation surface.

**Independent Test**: Execute staged one-profile, multiple-profile,
multi-human-Discord, restart, and Telegram scenes against the installed runtime,
then compare receipts and participant outcomes with the common program catalog.

**Acceptance Scenarios**:

1. **Given** several Hermes participants and one human in Discord, **When** a
   soft class address arrives, **Then** the room avoids deterministic all-mute
   and all-speak behavior while every judgment stays participant-shaped.
2. **Given** a profile restart, **When** the declared recovery scene runs,
   **Then** coverage and later hearing match the actual profile/transport
   capability.
3. **Given** an installed plugin, **When** a live V2 probe runs, **Then** receipt
   evidence identifies exact plugin, Nunchi package, model, configuration source,
   and schema/interface versions.

### Edge Cases

- Two profiles reuse a display name or alias: exact actor bindings keep identity
  and receipts separate.
- A profile lacks a native history seam: continuity is session-only or unknown
  and social suppression remains disabled until recoverability is proved.
- Hermes participant inference chooses silence after `WAKE`, `DEFER`,
  preattention bypass, or error fallback: this is a valid act-or-silence
  outcome, not a failed wake.
- A participant produces “yes, I want to contribute” instead of addressing the
  room: offline/live evaluation marks a meta-answer failure, but the harness does
  not inspect or block otherwise valid participant prose at runtime.
- One profile expands context: the handle cannot read another participant,
  room, continuity scope, or trigger.
- The plugin is packaged once for several profiles: runtime state must still be
  partitioned by exact profile/participant binding.

## Requirements

### Functional Requirements

- **FR-001**: Every Hermes profile MUST supply a stable participant ID and exact
  current-surface actor binding independently of loose names and roles.
- **FR-002**: Hermes MUST implement `I-020A` with bounded ordered events, honest
  coverage, optional bound continuation, and no roster or social ledger.
- **FR-003**: Hermes MUST call `I-030A` once per authorized routable trigger when
  preattention is enabled, route trusted `status: bypass` with zero classifier
  calls, and MUST NOT re-run a social judgment on send.
- **FR-004**: Effective `SUPPRESS` MUST stop only the current wake and MUST NOT
  remove the event from ordinary observation.
- **FR-005**: `WAKE`, either `DEFER`, `PREATTENTION_BYPASS`, and default
  operational error MUST invoke exactly one `I-040A` participant turn.
- **FR-006**: The participant turn MUST receive `I-010C` facts and attention
  annotation separately and MUST NOT be prompted for an intermediate yes/no
  admission answer; meta-answer detection remains evaluation-only.
- **FR-007**: Hermes MUST support direct participant message, reaction/tool
  action, and no-send outcomes through normal harness capability.
- **FR-008**: Context expansion MUST enforce `I-010D` binding and budgets without
  exposing the opaque handle to room control.
- **FR-009**: Multiple profiles MUST isolate observation, continuation, effective
  policy, receipts, and participant outcomes by exact binding.
- **FR-010**: Error details and I-010E stages MUST remain off the room surface.
  Hermes MUST preserve request correlation and immutable observation,
  attention, participant-host, and transport ownership, append only facts its
  native seam can attest, and never flatten or mutate another stage.
- **FR-011**: Effective delegation configuration and model/runtime provenance
  MUST be inspectable and independently recorded per profile.
- **FR-012**: Social suppression MUST remain disabled on any Hermes surface whose
  ordinary later-hearing and restart claim is unproved.
- **FR-013**: The slice MUST provide deterministic, replay, multi-profile,
  restart, Discord, Telegram, and installed-runtime evidence in ordinary paths.
- **FR-014**: The slice MUST preserve the control-plane boundary and must not
  implement any V2 behavior during Goal 1.

### Key Entities

- **Hermes profile binding**: stable participant identity, exact native actor,
  loose participant description, transport, and trusted configuration source.
- **Hermes observation source**: profile-bound implementation of `I-020A`.
- **Hermes participant turn**: one `I-040A` act-or-silence invocation.
- **Profile receipt stream**: off-surface `I-010E` records partitioned by exact
  profile binding.
- **Installed plugin provenance**: exact plugin/package/config/model identity used
  by a live scene.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of multi-profile identity fixtures use exact actor binding;
  alias collisions produce zero self-authorship claims.
- **SC-002**: Each routed attention disposition invokes the participant zero or
  one time exactly as specified, with zero send-time social classifier calls.
- **SC-003**: All participant outcomes—message/tool/reaction and silence—are
  separately staged without relabeling host, bypass, classifier, or transport
  outcomes.
- **SC-004**: The suppressed-event-later-heard scene passes within every surface's
  declared horizon before social suppression is enabled there.
- **SC-005**: Staged one-profile, multi-profile, restart, Discord, and Telegram
  scenes produce committed evidence or an explicit unavailable-capability record.
- **SC-006**: Every live Hermes parity claim cites exact installed plugin and
  Nunchi provenance plus the consumed interface versions.

## Assumptions

- Hermes supplies a native participant invocation and transport action path.
- Whether plugin code is shared or installed per profile is an implementation
  choice resolved by the first multi-profile scene; state isolation is mandatory
  either way.
- Surface-specific missing facts may differ, but equivalent facts must normalize
  and route equivalently.

## Explicit Exclusions

- Changes to shared schemas, classifier behavior, or the common participant-turn
  contract owned by slices `010`, `030`, and `040`.
- A central Hermes roster, obligation tracker, speaker queue, or shared handled
  state across profiles.
- Promotion, public release, or implementation/live deployment during Goal 1.
