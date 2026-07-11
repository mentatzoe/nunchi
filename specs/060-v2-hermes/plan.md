# Implementation Plan: V2 Hermes Harness

**Branch**: `v2/hermes` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/060-v2-hermes/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-hermes-owner`

**Goal authorization**: Goal 1 planning only; product execution awaits explicit Goal 2 authorization

**Upstream dependencies**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`

## Summary

Migrate the Hermes plugin atomically to the canonical V2 interfaces. Bind every
profile to exact identity, assemble bounded truthful observation, call attention
once, and route only `I-010C` through `I-040A` so the participant acts directly
or stays silent. Prove multi-profile isolation and installed-runtime parity on
live Discord and Hermes-native Telegram surfaces.

## Technical Context

**Language/Version**: Python 3.11+ and the supported Hermes plugin runtime

**Primary Dependencies**: existing Hermes plugin APIs and the Nunchi package; no
new mandatory product dependency planned

**Storage**: profile-bound bounded observation and existing Hermes operational
state only; no social memory or roster

**Testing**: stdlib `unittest`, sandboxed plugin fixtures, replay evaluations,
multi-profile and installed-runtime live scenes

**Target Platform**: Hermes agent profiles using native shared-room transports

**Project Type**: agent-harness plugin integration

**Performance Goals**: one pre-attention call per candidate trigger, zero
participant inference for effective suppression, and recorded wake/context cost

**Constraints**: exact profile binding; one social judgment; direct-room-turn
instruction; evaluation-only meta-answer scoring; no send reclassification;
truthful surface capability

**Scale/Scope**: one or more Hermes profiles in the same Discord room plus a
Hermes Telegram parity scene

## Constitution Check

- **PASS — product boundary**: Hermes invokes participants but never composes on
  Nunchi's behalf or reallocates the floor.
- **PASS — identity/observation**: exact profile and transport bindings are
  separate from loose names; no inferred roster is planned.
- **PASS — attention/contribution**: one `I-030A` call feeds one optional
  `I-040A` turn; no second social gate exists.
- **PASS — atomic contract**: no V1 bridge or mixed Hermes request shape is
  planned.
- **PASS — control plane**: implementation, tests, evals, evidence, and docs all
  target ordinary paths.
- **PASS — ownership**: one Hermes lane owns its files; upstream owners retain
  shared interfaces.
- **PASS — Goal/evidence gates**: all tasks are dormant; live provenance and
  cross-surface scenes are mandatory before handoff.

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

The canonical machine-readable definitions remain upstream-owned at
`schemas/v2/attention-request.schema.json`,
`schemas/v2/attention-decision.schema.json`,
`schemas/v2/participant-wake.schema.json`,
`schemas/v2/context-continuation.schema.json`, and
`schemas/v2/attention-receipt.schema.json`; this consumer references and never
redefines them.

Shared schemas are planned under `schemas/v2/`; callable core/CLI behavior under
`src/nunchi/`; Hermes consumes them without redefining them.

### Produces

- No new public interface. The slice produces a Hermes implementation of
  `I-020A` and `I-040A`, preserves trusted `PREATTENTION_BYPASS`, and proves
  immutable I-010E stage ownership without flattening the lifecycle.
- Hermes-specific installation and capability documentation under
  `docs/integrations/hermes-v2.md`.
- Runtime/evidence handoff under `evidence/v2/hermes/`.

## Integration Strategy

**Integration order**: accept all four foundation handoffs; add failing Hermes
conformance scenes; migrate identity/observation; migrate attention routing and
participant turn; prove multi-profile/restart/live surfaces; pass slice `100`;
hand to `110`.

**Worktree/branch**: `.worktrees/v2-hermes/` on `v2/hermes`, based on the
accepted foundation integration commit

**Handoff to**: `v2-security-owner`, then `v2-integrator`

**Conflict ownership**: `v2-hermes-owner` alone changes `integrations/hermes/`
and Hermes-specific test/eval/evidence/doc paths; foundation owners alone change
shared schemas and core interfaces; `v2-integrator` resolves shared packaging.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01/S14/S16/HM-01 exact multi-profile identity | Hermes sandbox | Same-class aliases never establish self; state stays profile-bound with no ledger | `evidence/v2/hermes/hermes-scenes.jsonl` |
| S06–S10/HM-02 disposition routing | Hermes sandbox | SUPPRESS invokes zero turns; WAKE/dual-DEFER/PREATTENTION_BYPASS/error invoke exactly one act-or-silence turn with immutable correlated stages; bypass invokes no classifier | `evidence/v2/hermes/hermes-scenes.jsonl` |
| S03/S05/S15/HM-03 later hearing and restart | Hermes + native history | Earlier suppressed event remains ordinarily available within bounded honest coverage | `evidence/v2/hermes/hermes-scenes.jsonl` |
| S02/S04/S14/HM-04 shared Discord room | n Hermes + one human | Native facts, class/referential scars, participant silence, and reactions preserve model nuance | `evidence/v2/hermes/hermes-scenes.jsonl` |
| S02/S13/HM-05 Telegram capability | Hermes Telegram | Equivalent available facts route equivalently; missing facts are explicit | `evidence/v2/hermes/telegram-scenes.jsonl` |
| S12/HM-06 installed provenance | Installed Hermes profiles | Exact plugin/package/model/config/interface identities accompany a V2 probe | `evidence/v2/hermes/installed-runtime.md` |

Deterministic tests belong at `tests/v2/test_hermes.py`, fixtures at
`tests/fixtures/v2/hermes/`, and reusable scenes at `evals/v2/hermes/`.

Every JSONL result row MUST contain canonical `scene_id` and Hermes case ID.
`evidence/v2/hermes/verification.md` is the exact scene-to-record/command
manifest, including bypass and receipt-stage ownership assertions.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/060-v2-hermes/
├── spec.md
├── plan.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
integrations/hermes/nunchi-gate/
tests/v2/test_hermes.py
tests/fixtures/v2/hermes/
evals/v2/hermes/
evidence/v2/hermes/
docs/integrations/hermes-v2.md
```

**Structure Decision**: evolve the existing Hermes plugin in place and isolate
all verification/evidence paths by surface. No product artifact is placed under
the slice directory.

## Ordinary Repository Targets

| Artifact class | Goal 2 target path(s) | Owning story |
|---|---|---|
| Product implementation | `integrations/hermes/nunchi-gate/` | US1–US3 |
| Shared contracts | consume `schemas/v2/`; no Hermes-owned public schema | US1–US2 |
| Tests and fixtures | `tests/v2/test_hermes.py`, `tests/fixtures/v2/hermes/` | US1–US3 |
| Evaluation | `evals/v2/hermes/` | US1–US3 |
| Evidence | `evidence/v2/hermes/` | US1–US3 |
| Product docs | `docs/integrations/hermes-v2.md` | US3 |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global Hermes support/evidence state | `README.md` | `HANDOFF` | T014 / `v2-hermes-owner` | Accepting owner: `v2-integrator`; replace V1/source-only claims with exact V2 lifecycle, capability, provenance, limitation, and evidence-grade wording at atomic cutover. |
| Hermes V2 integration guide | `docs/integrations/hermes-v2.md` | `UPDATE` | T014 / `v2-hermes-owner` | Validate install/config/profile isolation, restart, links, examples, and probes against the installed candidate. |
| Existing Hermes operator and patch docs | `integrations/hermes/README.md`, `docs/integrations/hermes-core-patch.md`, `docs/integrations/hermes-core-patch-test-plan.md` | `UPDATE` | T014 / `v2-hermes-owner` | Validate lifecycle, configuration, patch/runtime provenance, profile isolation, restart, examples, and installed probes. |
| Shared install/integration/adapter/design/change state | `CHANGELOG.md`, `docs/INSTALL.md`, `docs/adapters.md`, `docs/integration.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T014 / `v2-hermes-owner` | Accepting owner: `v2-integrator`; apply the exact breaking Hermes lifecycle, install/provenance, limitation, evidence-grade, and diagram delta at cutover. |

Slice 060 owns the integration guide and hands only cross-surface current-state
wording to 110 with an exact delta and accepting owner.

## Owner Handoff

The owner supplies exact commit and installed plugin/package provenance,
verification commands/results, consumed interface versions, multi-profile state
layout, effective configuration/model source, all evidence paths, surface
capability limits, and known limitations. `v2-integrator` may reject a locally
green plugin that does not match common scenes.

## Complexity Tracking

No constitution violation or complexity exception is planned.
