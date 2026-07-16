# Implementation Plan: V2 Participant Wake

**Branch**: `v2/participant-wake` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/040-v2-participant-wake/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-wake-owner`

**Assigned participant / source**: architect — evidence/governance/assignments/architect-v2-wake-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/040-v2-participant-wake`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/040-v2-participant-wake`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/participant/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/participant/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/participant/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/participant/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Upstream dependencies**: `010-v2-contract`, `020-v2-observation`,
`030-v2-core-attention`

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

During authorized slice implementation, implement the common I-040A participant-turn host at
`src/nunchi/participant.py`. It obeys one attention result, builds an
independently budgeted factual wake packet, routes trusted preattention bypass
without a model claim, exposes bound expansion, invokes one direct act-or-
silence turn, emits an immutable participant-host receipt stage, and keeps send
safety free of social reclassification. It hands a framework-neutral lifecycle to surface slices;
100 later audits it and 110 alone integrates/cuts over. This planning baseline
creates no product behavior.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Python standard library and accepted I-010B/C/D/E,
I-020A, and I-030A interfaces; no new runtime dependency

**Storage**: no social state; host-local transient wake/expansion state and
off-surface receipt output only

**Testing**: stdlib `unittest`, fake participant callbacks, reference replay,
call-count assertions, and later surface/live evidence in downstream slices

**Target Platform**: framework-neutral shared host consumed by Hermes, Claude
Code, Codex, and standalone adapter integration slices

**Project Type**: shared library lifecycle seam

**Performance Goals**: one attention judgment and at most one participant
inference per routed event; independent packet caps; bounded context fetch

**Constraints**: no meta-answer, composition by Nunchi, second social judgment,
social send permission, context bomb, outcome ledger, or final parity claim

**Scale/Scope**: one shared host interface and reference participant/context/
send callbacks, consumed by independently owned surface integrations

## Constitution Check

| Gate | Status | Planning evidence |
|---|---|---|
| Selected V2 boundary | PASS | Host routes attention and normal turns; Nunchi composes no reply. |
| Human-shaped judgment | PASS | Host obeys I-030A and introduces no deterministic social interpretation. |
| Truthful identity/observation | PASS | I-010C/I-020A facts, coverage, budgets, and bound expansion remain intact. |
| Attention/contribution split | PASS | One wake leads directly to actual action or silence; no admission meta-answer. |
| Atomic parity contract | PASS | I-040A is shared; surface slices bind it and 110 alone owns cutover. |
| Evidence before claims | PASS | Call-count, replay, packet, expansion, silence, and handoff evidence are concrete. |
| Control-plane boundary | PASS | This directory contains only planning Markdown. |
| Single owner and slice lifecycle | PASS | `v2-wake-owner` owns I-040A; tasks remain `DORMANT` while the slice is `PLANNED`. |

Post-design re-check: PASS. No prohibited design or product artifact is placed
in this directory.

## Slice Interfaces

### Consumes

- `I-010B AttentionDecisionV2@1` at `schemas/v2/attention-decision.schema.json`.
- `I-010C ParticipantWakeV2@1` at `schemas/v2/participant-wake.schema.json`.
- `I-010D ContextContinuationV2@1` at
  `schemas/v2/context-continuation.schema.json`.
- `I-010E AttentionReceiptV2@1` at `schemas/v2/attention-receipt.schema.json`.
- `I-020A ObservationProviderV2@1` at `src/nunchi/observation.py`.
- `I-030A AttentionEngineV2@1` at `src/nunchi/core.py` and
  `src/nunchi/cli.py`.

### Produces

- `I-040A ParticipantTurnHostV2@1` at `src/nunchi/participant.py`.

## Integration Strategy

**Integration order**: accept exact 010/020/030 commits → red routing/packet/
participant/expansion/send tests → shared host → replay/call-count evidence →
060–100 handoff. Surface owners bind the host independently; 100 audits their
exact candidates; 110 is the sole final sink.

**Worktree/branch**: future isolated worktree
`.worktrees/v2-participant-wake/` on branch `v2/participant-wake`

**Handoff to**: owners of slices `060` through `100` and `v2-integrator`

**Conflict ownership**: 040 alone owns `src/nunchi/participant.py` until
handoff. It does not edit 010 schemas, 020 observation, 030 core/CLI, native
transport, or surface integration files. Downstream binding changes stay in
their surface slices; 110 resolves final integration conflicts.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S03 Bounded context and tail | Shared host fixtures | Wake packet materializes trigger/relations/facts under independent caps and exposes honest continuation. | `evidence/v2/participant/s03-routing-and-context.jsonl` |
| S06 WAKE/bypass contribution | Fake participant host | WAKE or PREATTENTION_BYPASS invokes once and emits the actual message/reaction/tool action; acceptance evaluation flags a meta-answer without adding a runtime send gate. | `evidence/v2/participant/s06-s07-outcomes.jsonl` |
| S07 Participant silence | Fake participant host | WAKE, DEFER, PREATTENTION_BYPASS, and ERROR_FALLBACK may each end silently with distinct stages. | `evidence/v2/participant/s06-s07-outcomes.jsonl` |
| S09 Operational error | Shared host fixtures | ERROR wakes by default; explicit NO_WAKE remains separately sourced operational policy. | `evidence/v2/participant/s06-s07-outcomes.jsonl` |
| S10 No send-time social gate | Recording send seam | One attention call total (zero for bypass); send uses no classifier or social permit state. | `evidence/v2/participant/s10-expansion-and-send.jsonl` |
| S15 Context budget | Packet/fetch matrix | Attention and participant caps remain independent; delivered bytes/events/tokens are receipted. | `evidence/v2/participant/s03-routing-and-context.jsonl` |
| S16 No registry or ledger | Boundary/call graph | No roster inference, outcome replay, handled/open state, or permission registry appears. | `evidence/v2/participant/s10-expansion-and-send.jsonl` |

Deterministic checks target `tests/v2/participant/`, reusable reference scenes
`evals/v2/participant/`, and run records `evidence/v2/participant/`. Surface
and installed-runtime evidence remains owned by slices 060–100 and 110.

Every aggregate JSONL row MUST carry a canonical `scene_id`. The manifest at
`evidence/v2/participant/README.md` maps each applicable scene to exact records
and commands, and distinguishes this slice's participant-host stage from later
transport delivery stages.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/040-v2-participant-wake/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Ordinary repository targets for authorized slice implementation

```text
src/nunchi/participant.py
tests/v2/participant/
evals/v2/participant/
evidence/v2/participant/
docs/participant/v2.md
```

**Structure Decision**: One framework-neutral module owns participant routing,
packet delivery, expansion, and action/silence outcome semantics. It exposes
callbacks rather than importing any one agent harness.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning task/story |
|---|---|---|
| Shared participant host | `src/nunchi/participant.py` | US1–US3 |
| Tests | `tests/v2/participant/` | US1–US3 |
| Evaluation runners/corpora | `evals/v2/participant/` | US1–US3 |
| Evidence | `evidence/v2/participant/` | US1–US3 |
| Product documentation draft | `docs/participant/v2.md` | Cross-cutting; final truth owned by 110 |
| Surface bindings | `integrations/`, `src/nunchi/adapters/` | Excluded; 060–090-owned |
| Shared schemas/core/observation | `schemas/v2/`, `src/nunchi/core.py`, `src/nunchi/observation.py` | Consumed; upstream-owned |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global participant lifecycle | `README.md` | `HANDOFF` | T023 / `v2-wake-owner` | Accepting owner: `v2-integrator`; describe accepted direct act-or-silence, valid silence, expansion, and no send-time social gate only in the atomic candidate. |
| Participant-host reference | `docs/participant/v2.md` | `UPDATE` | T023 / `v2-wake-owner` | Validate lifecycle diagrams, action/silence examples, expansion limits, links, and no-reclassification commands against the candidate. |
| Shared change/current contract/integration/adapter/design state | `CHANGELOG.md`, `docs/STABILITY.md`, `docs/integration.md`, `docs/adapters.md`, `docs/contracts/channel-adapter-v1.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T023 / `v2-wake-owner` | Accepting owner: `v2-integrator`; apply exact breaking-change, wake-source, act-or-silence, expansion, receipt, no-reclassification, and diagram deltas at cutover. |
| Downstream surface references | `integrations/mcp-discord/README.md`, `integrations/mcp-discord/DESIGN.md`, `integrations/hermes/README.md`, `integrations/claude-code/README.md`, `integrations/claude-code/DEFER_EVAL.md`, `integrations/claude-code/transport-patch/README.md`, `integrations/codex/README.md` | `HANDOFF` | T023 / `v2-wake-owner` | Accepting owner: `v2-transport-owner`, `v2-hermes-owner`, `v2-claude-owner`, and `v2-codex-owner`; apply the exact I-040A wake, expansion, receipt, participant-silence, and send-path delta. |

The component guide lands with the slice; global current-state wording is an
exact accepted handoff to 110 rather than a generic deferral.

## Owner Handoff

The owner must hand off exact commit, I-040A and upstream versions, complete
commands/results, participant instruction, callback/capability contracts,
packet/fetch/call-count evidence, valid-silence and meta-answer results,
immutable stage ownership, preattention-bypass behavior, operational send
limitations, and rejected claims. The packet feeds surface
owners and 100 assurance; it does not wait on 100 or make a parity claim. Slice
110 remains the only final integrator.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.
