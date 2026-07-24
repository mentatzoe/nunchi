# Implementation Plan: V2 Codex Harness

**Branch**: `v2/codex` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/080-v2-codex/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-codex-owner`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-codex-owner-2026-07-24.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/080-v2-codex`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/080-v2-codex`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/codex/slice-activation.md` (written only
after every readiness prerequisite is accepted; it attests those facts and
establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/codex/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/codex/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/codex/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Upstream dependencies**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`, `050-v2-discord-transport`

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

Atomically migrate Codex's prompt hook, long-running room runner, persistent
session, plugin packaging, and send path to the canonical V2 lifecycle. Consume
I-050A reactively, route I-030A once (with zero classifier calls for trusted
preattention bypass), deliver one I-010C act-or-silence turn, preserve immutable
receipt stages, and remove the current send-time classifier and social permission state. Prove
the exact installed plugin/process in persistent and mixed-agent room scenes.

This planning baseline creates no product behavior.

## Technical Context

**Language/Version**: Python 3.11+ integration code and the supported Codex
CLI/plugin runtime

**Primary Dependencies**: existing Nunchi package, Codex hook/plugin APIs,
Codex CLI persistent-session capability, and `I-050A`; no new required product
dependency planned

**Storage**: room-bound Codex session identifier and bounded observation only;
no social permission, obligation, or handled state

**Testing**: stdlib `unittest`, hook/runner subprocess sandboxes, native fixtures,
replay/adversarial corpora, persistent-session and installed live-room probes

**Target Platform**: Codex CLI as a reactive Discord room participant through
the Nunchi plugin and shared Discord MCP event source

**Project Type**: agent-harness plugin, subprocess runner, and integration package

**Performance Goals**: reactive no-polling room receipt, one attention call per
unique trigger, no participant inference on effective suppression, and measured
participant packet/latency/cost receipts

**Constraints**: exact identity, event deduplication, bounded context, one social
judgment, persistent conversation without social state, no send-time re-gate

**Scale/Scope**: one or more Codex participants sharing Discord rooms with
humans, Hermes, and Claude Code

## Constitution Check

- **PASS — attention boundary**: `I-030A` decides only wake admission; Codex
  composes its own action in `I-040A`.
- **PASS — truth**: exact Discord/self/session facts remain separate from aliases
  and inferred conversation state.
- **PASS — one judgment**: prompt/runner deduplicate one attention call; send has
  operational safety only.
- **PASS — atomic contract**: all Codex paths move together with no V1 shim.
- **PASS — control plane**: code/tests/evals/evidence/docs target ordinary paths;
  this directory stays planning-only.
- **PASS — single owner**: one Codex lane owns all Codex-specific files and hands
  shared changes back to their owners.
- **PASS — slice lifecycle/evidence gate**: product tasks are dormant while the
  slice is `PLANNED`; activation, installed-process, and mixed-room evidence are
  mandatory.

## Slice Interfaces

### Consumes

- `I-010A AttentionRequestV2@1`
- `I-010B AttentionDecisionV2@1`
- `I-010C ParticipantWakeV2@1`
- `I-010D ContextContinuationV2@1`
- `I-010E AttentionReceiptV2@1`
- `I-020A ObservationProviderV2@1`
- `I-030A AttentionEngineV2@1`
- `I-040A ParticipantTurnHostV2@1`
- `I-050A DiscordEventSourceV2@1`

The canonical machine-readable definitions remain upstream-owned at
`schemas/v2/attention-request.schema.json`,
`schemas/v2/attention-decision.schema.json`,
`schemas/v2/participant-wake.schema.json`,
`schemas/v2/context-continuation.schema.json`, and
`schemas/v2/attention-receipt.schema.json`; this consumer references and never
redefines them.

### Produces

- No new public interface. The slice produces Codex conformance across prompt,
  runner, participant, session, plugin, and send paths.
- Installed/provenance and scene evidence under `evidence/v2/codex/`.

## Integration Strategy

**Integration order**: accept `010`–`050`; add failing cross-path conformance and
adversarial fixtures; migrate event/observation and deduplication; migrate one
attention/participant route; remove send re-gate/V1 residue; prove persistent and
mixed-room installed runtime; pass `100`; hand to `110`.

**Worktree/branch**: `.worktrees/v2-codex/` on `v2/codex` is an isolated,
non-releaseable slice worktree that consumes the exact accepted upstream
commits for `010` through `050` recorded in activation evidence. It creates no
program integration or cutover artifact; only slice `110` integrates.

**Handoff to**: `v2-security-owner`, then `v2-integrator`

**Conflict ownership**: `v2-codex-owner` alone changes Codex-specific
`src/nunchi/integrations/codex_*`, `integrations/codex/`, and verification paths;
`v2-transport-owner` owns `I-050A`; owners of slices `010`–`040` own their
shared interfaces;
`v2-integrator` resolves packaging/current-state-doc conflicts.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01/S02/CD-01 exact identity and native facts | Codex hook/runner | Exact actor/session binding wins over alias collision and native relations remain structured | `evidence/v2/codex/scene-results.jsonl` |
| S03/S15/CD-02 bounded persistent context | Codex session + continuation | Conversation resumes or gaps truthfully; independent caps prevent context bomb | `evidence/v2/codex/scene-results.jsonl` |
| S04/S05/CD-03 model-only suppression | Codex attention path | Station scars have no mechanical suppressor; suppression is governed/recoverable | `evidence/v2/codex/scene-results.jsonl` |
| S06–S10/CD-04 direct turn | Codex participant/send | Correct route, action/silence/error, dual DEFER, zero-call PREATTENTION_BYPASS, immutable stage ownership, and zero send-time social call | `evidence/v2/codex/scene-results.jsonl` |
| S11/CD-05 cross-path event deduplication | I-050A + hook/runner | One exact native trigger is processed once across Codex integration paths | `evidence/v2/codex/scene-results.jsonl` |
| S12/CD-06 installed provenance | Installed Codex plugin/process | Exact components, residue removal, restart, and schema-2 probe are recorded | `evidence/v2/codex/installed-runtime.md` |
| S14/S16/CD-07 mixed room/no ledger | Hermes + Claude + Codex + human | Codex stays present without all-talk/all-mute or social registry state | `evidence/v2/codex/scene-results.jsonl` |

Tests belong at `tests/v2/test_codex.py`, fixtures at
`tests/fixtures/v2/codex/`, and replay/adversarial inputs at `evals/v2/codex/`.

Every JSONL result row MUST contain canonical `scene_id` and Codex case ID.
`evidence/v2/codex/verification.md` is the exact scene-to-record/command
manifest, including bypass and immutable-stage assertions.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/080-v2-codex/
├── spec.md
├── plan.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/nunchi/integrations/codex_*.py
integrations/codex/
tests/v2/test_codex.py
tests/fixtures/v2/codex/
evals/v2/codex/
evidence/v2/codex/
docs/integrations/codex-v2.md
```

**Structure Decision**: migrate the existing package modules and distributable
plugin together; move all new run records to ordinary `evidence/v2/codex/` and
do not embed evidence in the integration package.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning story |
|---|---|---|
| Product implementation | `src/nunchi/integrations/codex_*.py`, `integrations/codex/` | US1–US3 |
| Shared contracts | consume the five files under `schemas/v2/`; no Codex-owned public schema | US1–US3 |
| Tests and fixtures | `tests/v2/test_codex.py`, `tests/fixtures/v2/codex/` | US1–US3 |
| Evaluation | `evals/v2/codex/` | US1–US3 |
| Evidence | `evidence/v2/codex/` | US1–US3 |
| Product docs | `docs/integrations/codex-v2.md` | US3 |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global Codex support/evidence state | `README.md` | `HANDOFF` | T022 / `v2-codex-owner` | Accepting owner: `v2-integrator`; replace bounded V1/outbound-regate claims with exact V2 session, no-social-send-gate, provenance, limitation, and evidence-grade wording at atomic cutover. |
| Codex V2 and existing operator guides | `docs/integrations/codex-v2.md`, `integrations/codex/README.md` | `UPDATE` | T022 / `v2-codex-owner` | Validate install/plugin/session/config, removal of the outbound social re-gate, residue/restart, links, examples, and probes against the installed candidate. |
| Shared integration/adapter/design/change state | `CHANGELOG.md`, `docs/adapters.md`, `docs/integration.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T022 / `v2-codex-owner` | Accepting owner: `v2-integrator`; apply the exact breaking Codex session, send-path, evidence-grade, limitation, and diagram delta at cutover. |
| Shared Discord transport configuration | `integrations/mcp-discord/README.md` | `HANDOFF` | T022 / `v2-codex-owner` | Accepting owner: `v2-transport-owner`; apply the exact accepted Codex V2 harness configuration and action-capability delta without changing transport ownership. |

The handoff must make removal of the V1 outbound social gate explicit; 110 owns
the corresponding global current-state update.

## Owner Handoff

The owner supplies exact commit, verification commands/results, consumed
interface versions, installed source/plugin/package/Codex/transport/process/model/
config provenance, persistent-session behavior, retired residue list, scene
evidence, effective limits, and known limitations. A source-only or send-regated
candidate is rejected.

## Complexity Tracking

No constitution violation or complexity exception is planned.
