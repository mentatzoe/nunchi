# Implementation Plan: V2 Core Attention

**Branch**: `v2/core-attention` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/030-v2-core-attention/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-core-owner`

**Goal authorization**: Goal 1 planning only; Goal 2 is not authorized

**Upstream dependencies**: `010-v2-contract`

## Summary

In future Goal 2, replace the V1 core and CLI on the slice branch with one
participant-shaped V2 attention engine. It validates I-010A, emits I-010B and
immutable I-010E attention stages, governs suppression, preserves separately
auditable classifier- and margin-DEFER valves, returns trusted preattention-
disabled bypass without a model call, and keeps operational failure separate
with wake as the shared default. The exact handoff feeds 040 and later surface
slices; 110 alone owns atomic integration. No product work is performed now.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Python standard library, existing OpenAI-compatible
provider transport, and 010-owned V2 schemas

**Storage**: Stateless per-request engine plus off-surface receipt sinks owned
by hosts; no social state store

**Testing**: stdlib `unittest`, deterministic provider fixtures, replay corpus,
multi-model evaluation, and a preregistered downstream canary protocol

**Target Platform**: callable Python core and `nunchi` CLI consumed by all
in-tree harnesses and adapters

**Project Type**: library plus CLI

**Performance Goals**: one logical model judgment per request; provider retries
remain bounded; receipts report latency and serialized/token context cost

**Constraints**: no V1 bridge, deterministic social rule, hidden fallback,
reply prose, request-controlled operator policy, or send-time judgment

**Scale/Scope**: one engine interface, one CLI seam, one shared transition
policy, and one evidence-backed prompt/model configuration

## Constitution Check

| Gate | Status | Planning evidence |
|---|---|---|
| Selected V2 boundary | PASS | Engine decides wake attention only and never composes a participant move. |
| Human-shaped judgment | PASS | One sparse participant-shaped model judgment owns every social suppression. |
| Truthful identity/observation | PASS | I-010A facts and unknowns are consumed without inventing roster or handled state. |
| Attention/contribution split | PASS | Engine returns attention; 040 and surface slices own normal participant turns. |
| Atomic parity contract | PASS | Core and CLI share I-030A with no V1 bridge; 110 owns final cutover. |
| Evidence before claims | PASS | Mechanics, replay, multi-model, canary, and margin evidence targets are separate. |
| Control-plane boundary | PASS | This directory contains planning Markdown only. |
| Single owner and Goal gate | PASS | `v2-core-owner` owns I-030A; every product task waits for Goal 2. |

Post-design re-check: PASS. No `data-model.md`, local contract, quickstart,
schema, test, corpus, evidence, or product documentation is created here.

## Slice Interfaces

### Consumes

- `I-010A AttentionRequestV2@1` at `schemas/v2/attention-request.schema.json`.
- `I-010B AttentionDecisionV2@1` at `schemas/v2/attention-decision.schema.json`.
- `I-010E AttentionReceiptV2@1` at `schemas/v2/attention-receipt.schema.json`.

### Produces

- `I-030A AttentionEngineV2@1` at `src/nunchi/core.py` and
  `src/nunchi/cli.py`, with provider/prompt support in
  `src/nunchi/classifiers.py` and runtime validation/audit support in the
  existing `src/nunchi/models.py` and `src/nunchi/schema.py` seams.

## Integration Strategy

**Integration order**: accepted 010 commit → red core/CLI contract tests →
participant-shaped classifier result or trusted bypass → governed dual-valve
route → tagged error and immutable attention-stage receipt → replay/multi-model
evidence plus downstream canary protocol → downstream handoff.
Slice 020 runs in parallel; 040 begins only after both handoffs.

**Worktree/branch**: future isolated worktree `.worktrees/v2-core-attention/` on
branch `v2/core-attention`

**Handoff to**: `v2-wake-owner`, owners of slices `060` through `110`, and
`v2-integrator`

**Conflict ownership**: 030 owns core, CLI, classifier prompt/provider, and
attention-policy files named here until handoff. It does not edit 010 schemas,
020 observation, 040 participant hosting, or surface integration files. 110
alone resolves final integration conflicts.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S04 False-suppression scars | Core replay | No deterministic semantic suppressor; model/effective decisions remain inspectable. | `evidence/v2/attention/s04-suppression-scars/results.jsonl` |
| S05 Governed suppression | Core policy matrix | Hard stop requires enabled delegation, recoverability, valid transition evidence, and revocable provenance. | `evidence/v2/attention/s05-governed-suppress.jsonl` |
| S06 WAKE/bypass contribution handoff | Core-neutral decision fixture | WAKE carries only grounded optional advice; trusted preattention-disabled bypass makes no model claim and supplies `PREATTENTION_BYPASS`. | `evidence/v2/attention/core-cli-parity.jsonl` |
| S08 Dual DEFER valves | Three-family replay | Classifier-DEFER and margin-DEFER remain separate; either only widens attention across incumbent Gemini 3.1 Flash Lite, frontier GPT-5.5, and open-weight Qwen3. Live canary execution is downstream. | `evidence/v2/attention/s08-defer-transition/results.jsonl` |
| S09 Operational error | Core and CLI | Every validation/provider/runtime failure remains ERROR with wake default and separate override audit. | `evidence/v2/attention/core-cli-parity.jsonl` |
| S16 No registry or ledger | Boundary and replay | Engine consumes no prior outcome, obligation, handled/open, roster, or permission state. | `evidence/v2/attention/s04-suppression-scars/results.jsonl` |
| 030-CLI Core/CLI parity | Core and CLI | Equivalent input/config yields equivalent tagged decision and audit. | `evidence/v2/attention/core-cli-parity.jsonl` |

Deterministic checks target `tests/v2/attention/`, replay and model-comparison
assets `evals/v2/attention/`, and run records `evidence/v2/attention/`.

Every aggregate JSONL row MUST carry its canonical `scene_id` (or
`030-CLI` for the slice-local contract scene). The manifest at
`evidence/v2/attention/README.md` maps scenes, records, commands, model runs,
and the downstream-owned canary protocol explicitly.
The three-family attempts live at
`evidence/v2/attention/model-comparison/results.jsonl`; the preregistered but
not-yet-executed protocol lives at
`evidence/v2/attention/defer-canary/protocol.md`.

## CLI Process Contract

| Input/result class | stdout | stderr | Exit |
|---|---|---|---|
| Valid request; `status: ok` or trusted `status: bypass` | Exactly one tagged JSON value | No response payload | `0` |
| JSON parsed; request schema invalid | Exactly one tagged `status: error` JSON value | No response payload | `3` |
| Provider/runtime/malformed-model failure | Exactly one tagged `status: error` JSON value | No response payload | `1` |
| Input unreadable or invalid JSON | Empty | Diagnostic only | `2` |

Core and CLI must also prove that host-only continuation handles, binding
tokens, cursors, and expiry values never enter the classifier projection. The
model may see factual coverage and expansion-availability booleans only; the
original bound I-010D capability remains available downstream to 040.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/030-v2-core-attention/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Ordinary repository targets for future Goal 2

```text
src/nunchi/
├── core.py
├── cli.py
├── classifiers.py
├── models.py
└── schema.py

tests/v2/attention/
evals/v2/attention/
evidence/v2/attention/
docs/attention/v2.md
```

**Structure Decision**: Evolve the current shared core/CLI seams on an isolated
slice branch. Do not introduce an alternate V2 executable or compatibility
layer that could survive the atomic cutover.

## Ordinary Repository Targets

| Artifact class | Goal 2 target path(s) | Owning task/story |
|---|---|---|
| Attention engine | `src/nunchi/core.py`, `src/nunchi/classifiers.py` | US1, US2 |
| CLI/validation/audit | `src/nunchi/cli.py`, `src/nunchi/models.py`, `src/nunchi/schema.py` | US2, US3 |
| Tests | `tests/v2/attention/` | US1–US3 |
| Evaluation runners/corpora | `evals/v2/attention/` | US1–US3 |
| Evidence | `evidence/v2/attention/` | US1–US3 |
| Product documentation draft | `docs/attention/v2.md` | Cross-cutting; final truth owned by 110 |
| Shared schemas | `schemas/v2/` | Consumed; 010-owned |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global attention/CLI state | `README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; replace V1 verdict/CLI claims with accepted I-030A disposition, bypass, ERROR, and dual-DEFER behavior only at atomic cutover. |
| Attention/operator reference | `docs/attention/v2.md` | `UPDATE` | T025 / `v2-core-owner` | Validate policy, error/exit semantics, active margin, model provenance, links, and commands against the exact candidate. |
| Retained V1 scar/evaluation references | `docs/contracts/verdict-suite-data-model-v1.md`, `docs/contracts/verdict-suite-requirements-v1.md`, `docs/evaluations/verdict-suite.md`, `docs/evaluations/verdict-suite-runner.md` | `UPDATE` | T025 / `v2-core-owner` | Preserve V1 evidence semantics, name its exact V2 regression/transition role, link the V2 evaluation, and validate retained commands. |
| Shared change/current contract, install, integration, adapter, and design state | `CHANGELOG.md`, `docs/STABILITY.md`, `docs/integration.md`, `docs/INSTALL.md`, `docs/adapters.md`, `docs/contracts/channel-adapter-v1.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; apply exact breaking-change, disposition/result, CLI/error, bypass, dual-DEFER, supersession, model/config, and diagram deltas at cutover. |
| Downstream surface references | `integrations/mcp-discord/README.md`, `integrations/mcp-discord/DESIGN.md`, `integrations/hermes/README.md`, `integrations/claude-code/README.md`, `integrations/claude-code/DEFER_EVAL.md`, `integrations/codex/README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-transport-owner`, `v2-hermes-owner`, `v2-claude-owner`, and `v2-codex-owner`; apply the exact I-030A lifecycle, bypass, ERROR, and dual-DEFER delta in each owned guide. |

Global current-state claims remain integrator-owned; the component guide and
exact handoff delta are both required before 030 can converge.

## Owner Handoff

The owner must hand off the exact commit, I-030A and upstream interface
versions, complete commands/results, prompt and model identity, effective
operator configuration and source, margin state, deterministic/replay/multi-
model evidence (including exact provider IDs/provenance for the selected three-
family matrix or an explicit later Zoe override), the preregistered downstream
canary protocol, rejected claims, and known limitations. The handoff explicitly
does not claim live participant outcomes. Downstream review
does not silently transfer core ownership; 110 remains the sole final sink.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.
