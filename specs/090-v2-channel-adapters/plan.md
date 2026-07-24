# Implementation Plan: V2 Standalone Channel Adapters

**Branch**: `v2/channel-adapters` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/090-v2-channel-adapters/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-adapters-owner`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-adapters-owner-2026-07-24.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/090-v2-channel-adapters`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/090-v2-channel-adapters`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/adapters/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts and
establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/adapters/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/adapters/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/adapters/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Upstream dependencies**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`

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

Cut generic, standalone Discord, Matrix, and Telegram adapters over together to
the canonical V2 lifecycle. Each surface binds exact identity, preserves the
native facts it actually knows, represents unavailable capability honestly,
assembles bounded observation, invokes the attention engine once, permits one
logical classifier call on ordinary paths or zero classifier/model calls for
trusted bypass, and exposes a normal participant act-or-silence path without
send reclassification. Prove equivalence
with matched replay and exact installed entrypoints.

This planning baseline creates no product behavior.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: zero required dependencies for generic/core paths;
existing optional Discord/Matrix/Telegram client dependencies remain
surface-owned; no new required product dependency planned

**Storage**: per-adapter bounded observation or native history only; no shared
roster, handled ledger, or obligation queue

**Testing**: stdlib `unittest`, native surface fixtures, matched cross-adapter
replay, subprocess entrypoint tests, and bounded live probes

**Target Platform**: generic subprocess host plus standalone Discord, Matrix,
and Telegram adapters

**Project Type**: Python adapter library and CLI entrypoints

**Performance Goals**: hard event/byte limits, one attention-engine invocation
per routable trigger, exactly one logical classifier call on ordinary paths and
zero on trusted bypass, and measured per-surface latency/context size rather
than one invented universal threshold

**Constraints**: exact self, authoritative order, honest missing facts, no
semantic deterministic gate, trusted bypass only, no fabricated social result,
immutable singly owned receipt stages, no second judgment, atomic in-tree V2
cutover

**Scale/Scope**: four adapter families and their shipped entrypoints, each with
surface-specific capability evidence

## Constitution Check

- **PASS — model nuance**: adapters preserve facts; only `I-030A` interprets
  social meaning.
- **PASS — identity/observation**: exact bindings and honest capabilities are
  mandatory; no inferred roster exists.
- **PASS — attention/contribution**: one engine invocation with one logical
  classifier call on ordinary paths or zero on trusted bypass feeds one optional
  `I-040A` direct turn; send remains operational.
- **PASS — atomic parity**: every in-tree adapter migrates with no V1 bridge.
- **PASS — evidence**: matched deterministic replay plus per-surface installed
  probes are required; unit-only social claims are rejected.
- **PASS — control plane/ownership**: all executable artifacts target ordinary
  paths and one adapter lane owns them.
- **PASS — slice lifecycle gate**: product tasks remain dormant while the slice
  is `PLANNED` and program implementation authority is `NOT_GRANTED`.

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

### Produces

- No new public interface. The slice produces four adapter conformance
  implementations and a capability/equivalence matrix. Each adapter appends
  only an immutable `transport` stage for native outcomes it directly attests
  and preserves upstream observation, attention, and participant-host stages.
- Per-surface installed and scene evidence under `evidence/v2/adapters/`.

## Integration Strategy

**Integration order**: accept `010`–`040`; define matched native fixtures and
capability matrix; migrate shared adapter plumbing; migrate generic, Discord,
Matrix, and Telegram bindings independently within the owner lane; run matched
replay and installed probes; pass `100`; hand one commit to `110`.

**Worktree/branch**: `.worktrees/v2-channel-adapters/` on
`v2/channel-adapters` is an isolated, non-releaseable slice worktree that
consumes the exact accepted upstream commits for `010` through `040` recorded
in activation evidence. It creates no program integration or cutover artifact;
only slice `110` integrates.

**Handoff to**: `v2-security-owner`, then `v2-integrator`

**Conflict ownership**: `v2-adapters-owner` alone changes
`src/nunchi/adapters/` and adapter-specific verification paths; owners of
slices `010`–`040` retain their shared interfaces; `v2-transport-owner` retains
the independent MCP Discord source; `v2-integrator` owns final parity fixtures
and current-state docs.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01/AD-01 exact identity | Generic, Discord, Matrix, Telegram | Exact binding wins over alias collision on every surface | `evidence/v2/adapters/scene-results.jsonl` (`scene_id=AD-01`) |
| S02/S13/AD-02 native equivalence | All adapters | Equivalent facts normalize equally; unavailable facts remain explicit | `evidence/v2/adapters/scene-results.jsonl` (`scene_id=AD-02`) |
| S03/S15/AD-03 bounded context | All adapters | Trigger/relations/order/caps/gaps/continuation remain truthful per capability | `evidence/v2/adapters/scene-results.jsonl` (`scene_id=AD-03`) |
| S04/S05/AD-04 model-only suppression | All adapters | No semantic transport rule; governed suppression requires recoverability | `evidence/v2/adapters/scene-results.jsonl` (`scene_id=AD-04`) |
| S06–S10/AD-05 common lifecycle | All adapters | Every routable trigger invokes the engine once; ordinary paths make exactly one logical classifier call while trusted bypass makes zero, records `classifier_not_invoked`, and invokes one advice-free act-or-silence turn; direct action/silence, immutable stage ownership, and no send re-gate remain separate | `evidence/v2/adapters/scene-results.jsonl` (`scene_id=AD-05`) |
| S11/AD-06 hygiene | All adapters | Only exact duplicate/self/unroutable/unconstructable deterministic classes | `evidence/v2/adapters/scene-results.jsonl` (`scene_id=AD-06`) |
| S12/AD-07 installed entrypoints | Four shipped entrypoints | Exact package/executable/config/process, restart/residue, and V2 probe recorded | `evidence/v2/adapters/installed-runtime.md` |
| S16/AD-08 no registry/ledger | All adapters | Public/buffer/receipt/send state contains no inferred roster or social queue | `evidence/v2/adapters/scene-results.jsonl` (`scene_id=AD-08`) |
| S14/AD-09 mixed-room compatibility | Installed adapter entrypoints plus harness-independent participant-host probes shaped like the six pinned stages | Adapter lifecycle and native facts do not introduce polling, deterministic all-talk/all-mute, or contract drift; final live room behavior remains owned by `110` | `evidence/v2/adapters/mixed-room.jsonl` |

Tests belong at `tests/v2/test_channel_adapters.py`, native fixtures at
`tests/fixtures/v2/adapters/`, and matched reusable replay at
`evals/v2/channel_adapters/`.

`evidence/v2/adapters/manifest.json` maps every `AD-*` and applicable `S*` ID
to its exact record, command, candidate commit, and result. Consolidated JSONL
is valid only when every row carries its stable `scene_id`; bypass/receipt rows
also carry request ID, stage owner, trusted bypass provenance,
`classifier_not_invoked`, and classifier-call count. Meta-answer grading is
post-hoc evaluation and never a runtime output filter.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/090-v2-channel-adapters/
├── spec.md
├── plan.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/nunchi/adapters/
tests/v2/test_channel_adapters.py
tests/fixtures/v2/adapters/
evals/v2/channel_adapters/
evidence/v2/adapters/
  manifest.json
docs/adapters-v2.md
```

**Structure Decision**: evolve the current adapter package in place, with shared
adapter utilities owned by this one lane and unique verification/evidence paths.
No adapter product artifact lives under `specs/`.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning story |
|---|---|---|
| Product implementation | `src/nunchi/adapters/` | US1–US3 |
| Shared contracts | consume the five files under `schemas/v2/`; no adapter-owned public schema | US1–US3 |
| Tests and fixtures | `tests/v2/test_channel_adapters.py`, `tests/fixtures/v2/adapters/` | US1–US3 |
| Evaluation | `evals/v2/channel_adapters/` | US1–US3 |
| Evidence | `evidence/v2/adapters/`, including `manifest.json` | US1–US3 |
| Product docs | `docs/adapters-v2.md` | US3 |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global adapter support/evidence state | `README.md` | `HANDOFF` | T017 / `v2-adapters-owner` | Accepting owner: `v2-integrator`; replace V1/code-only claims with exact V2 installed entrypoints, capability differences, limitations, and evidence tiers at atomic cutover. |
| Cross-adapter V2 guide | `docs/adapters-v2.md` | `UPDATE` | T017 / `v2-adapters-owner` | Validate invocation, budgets, capability semantics, entrypoints, links, examples, and probes across installed adapters. |
| Existing adapter/current contract/integration/design/change state | `CHANGELOG.md`, `docs/adapters.md`, `docs/integration.md`, `docs/STABILITY.md`, `docs/contracts/channel-adapter-v1.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T017 / `v2-adapters-owner` | Accepting owner: `v2-integrator`; apply exact supersession, entrypoint, capability, limitation, evidence-tier, stability, and diagram deltas at atomic cutover. |

Adapter-specific truth lands with 090; shared current-state wording transfers to
110 as an exact accepted delta.

## Owner Handoff

The owner supplies one exact commit, verification commands/results, consumed
interface versions, generic/Discord/Matrix/Telegram capability matrix, matched
scene results, installed package/entrypoint/config/process provenance, effective
budgets/restart claims, trusted-bypass zero-classifier-call proof, immutable receipt-stage
ownership, AD-01 through AD-09 manifest coverage, unavailable facts, and known
limitations. The final
integrator rejects any remaining V1 adapter or invented parity claim.

## Complexity Tracking

No constitution violation or complexity exception is planned.
