# Implementation Plan: V2 Observation

**Branch**: `v2/observation` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/020-v2-observation/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-observation-owner`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-observation-owner-2026-07-23.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/020-v2-observation`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/observation/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/observation/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/observation/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/observation/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Upstream dependencies**: `010-v2-contract`

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

During authorized slice implementation, implement the shared observation
provider that preserves exact identity and native structure, assembles bounded
factual attention requests, exposes controlled context expansion where
truthful, and supplies reusable recoverability/comparison scenes. Transport and
harness slices bind their native surfaces later. Slice 020 stops at a tested
I-020A handoff; 110 alone owns final parity and cutover. This planning baseline
creates no product behavior.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: standard library and 010-owned V2 schemas; transport
clients remain owned by downstream native-surface slices

**Storage**: bounded shared in-memory observation seam; native-history and
persistence behavior remain surface-owned, while restart/backfill variants are
simulated only in ordinary-path tests and evaluations

**Testing**: stdlib `unittest`, native-shape replay fixtures, reference-provider
comparison, budget tests, and simulated restart/backfill scenes

**Target Platform**: transport-neutral shared observation mechanics consumed by
generic channel, Matrix, Telegram, Discord, Discord-MCP, Hermes, Claude Code,
and Codex bindings in later slices

**Project Type**: shared library plus reference test/evaluation providers;
integration-specific providers belong to downstream slices

**Performance Goals**: hard event/byte caps on every projection and fetch;
serialized size and model-specific estimated token cost recorded in evidence

**Constraints**: no semantic deterministic gate, no inferred roster or social
ledger, authoritative order, outcome-neutral retention, honest unknowns

**Scale/Scope**: one shared provider implementation and reusable assembly,
continuation, recoverability, and comparison reference assets; no native-surface
parity claim

## Constitution Check

| Gate | Status | Planning evidence |
|---|---|---|
| Selected V2 boundary | PASS | Observation supplies facts only and owns no participant contribution. |
| Human-shaped judgment | PASS | Deterministic paths are limited to transport-proven non-events. |
| Truthful identity/observation | PASS | Exact self, native relations, bounded context, unknowns, and continuity are primary requirements. |
| Attention/contribution split | PASS | I-020A ends at request/continuation production and does not route participant turns. |
| Atomic parity contract | PASS | I-020A and its comparator define one shared seam; downstream slices prove each native binding and 110 proves final parity. |
| Evidence before claims | PASS | Shared/reference replay, budget, recoverability, restart, and capability evidence are distinct from downstream live-surface proof. |
| Control-plane boundary | PASS | Only four planning artifact types exist in this directory. |
| Single owner and slice lifecycle | PASS | `v2-observation-owner` owns I-020A; tasks remain `DORMANT` while the slice is `PLANNED`. |

Post-design re-check: PASS. No prohibited SpecKit output is planned.

## Slice Interfaces

### Consumes

- `I-010A AttentionRequestV2@1` from 010 at
  `schemas/v2/attention-request.schema.json`.
- `I-010D ContextContinuationV2@1` from 010 at
  `schemas/v2/context-continuation.schema.json`.
- The immutable staged-record shape of `I-010E AttentionReceiptV2@1` at
  `schemas/v2/attention-receipt.schema.json`.

### Produces

- `I-020A ObservationProviderV2@1` in future shared code at
  `src/nunchi/observation.py`, returning a bounded I-010A request and optional
  I-010D continuation provider, plus the observation-stage I-010E record for
  facts this slice can attest. Later owners append separately correlated,
  immutable stages; they never mutate this record.

## Integration Strategy

**Integration order**: 010 contract handoff → shared normalizer/buffer/assembler
→ continuation seam → reference replay/recoverability/comparison evidence
→ downstream handoff. Slice 030 can implement in parallel against I-010A;
050 and 060–090 bind and prove native surfaces only after accepting I-020A, and
110 owns the final comparison.

**Worktree/branch**: future isolated worktree `.worktrees/v2-observation/` on
branch `v2/observation`

**Handoff to**: owners of slices `040` through `110` and `v2-integrator`

**Conflict ownership**: 020 alone owns `src/nunchi/observation.py` until
handoff. It does not edit 010 schemas, native transport sources, harness
entrypoints, participant invocation, or send paths. Slices 050 and 060–090 own
their bindings, and 110 owns final integration conflict resolution.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01 Exact self and alias collision | Shared provider fixtures | Exact attested self wins; names never establish authorship. | `evidence/v2/observation/identity-and-hygiene.jsonl` |
| S02 Native relations | Shared provider fixtures | Actor-targeted mentions and room-wide mention status remain distinct; reply/thread, reaction, and membership facts survive when supplied; absence stays honest. | `evidence/v2/observation/identity-and-hygiene.jsonl` |
| S03 Bounded context and tail | Shared assembler | Trigger, fitting relation closure, already-observed tail, bytes/events, and gaps are truthful. | `evidence/v2/observation/budget-sweep.jsonl`, `evidence/v2/observation/continuation.jsonl` |
| S04 False-suppression scars | Shared provider fixtures | Referential mention, apparent resolution, other addressee, and class address never enter deterministic transport hygiene. | `evidence/v2/observation/identity-and-hygiene.jsonl` |
| S05 Governed suppression recoverability | Reference continuity variants | Earlier events remain ordinarily available under claimed continuity; unsupported eligibility is explicit. | `evidence/v2/observation/s05-recoverability.jsonl` |
| S11 Transport hygiene | Shared provider fixtures | Exact duplicate, exact self, and unroutable are the only mechanical no-wake classes. | `evidence/v2/observation/identity-and-hygiene.jsonl` |
| S13 Adapter equivalence | Capability-neutral reference variants | Equivalent supplied facts normalize equivalently and capability-only differences are explained; real adapters must rerun this contract downstream. | `evidence/v2/observation/s13-equivalence.jsonl` |
| S15 Context budget | Shared assembler | Attention projection and fetch hard caps are enforced with byte/token receipts. | `evidence/v2/observation/budget-sweep.jsonl`, `evidence/v2/observation/continuation.jsonl` |
| S16 No registry or ledger | Buffer/continuation fixtures | No roster inference, outcome registry, obligation queue, or handled/open state is created. | `evidence/v2/observation/identity-and-hygiene.jsonl` |

Reusable native fixtures and comparison tools target `evals/v2/observation/`;
deterministic tests target `tests/v2/observation/`.

Every aggregate JSONL row MUST carry a canonical `scene_id`. The manifest at
`evidence/v2/observation/README.md` maps every applicable scene to its exact
records and commands, so aggregation never makes scene coverage implicit.

These records prove the shared seam and reference variants only. Slices 050 and
060–090 own actual native binding evidence, and slice 110 owns the final
cross-surface equivalence result. A reference pass cannot be cited as proof for
an installed surface.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/020-v2-observation/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Ordinary repository targets for authorized slice implementation

```text
src/nunchi/observation.py
tests/v2/observation/
evals/v2/observation/
evidence/v2/observation/
docs/observation/v2.md
```

**Structure Decision**: Shared observation mechanics live in the umbrella-
registered `src/nunchi/observation.py`. Native transport and harness bindings
are deliberately left to slices 050 and 060–090, avoiding file co-ownership.
Reference restart/backfill state and capability variants live under `tests/v2/`
and `evals/v2/`; no simulated transport lifecycle is implemented in the shared
product module.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning task/story |
|---|---|---|
| Shared implementation | `src/nunchi/observation.py` | US1–US2; consumed by US3 references |
| Native/surface bindings | none; owned by `050`, `060`–`090` | Excluded |
| Tests | `tests/v2/observation/` | US1–US3 |
| Replay runners/corpora | `evals/v2/observation/` | US1–US3 |
| Evidence | `evidence/v2/observation/` | US1–US3 |
| Product documentation | `docs/observation/v2.md` | Cross-cutting |
| Shared schemas | `schemas/v2/` | Consumed; 010-owned |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global context/identity description | `README.md` | `HANDOFF` | T023 / `v2-observation-owner` | Accepting owner: `v2-integrator`; add only evidence-proven exact-self, native-relation, budget, gap, and continuation claims at atomic cutover. |
| Observation reference | `docs/observation/v2.md` | `UPDATE` | T023 / `v2-observation-owner` | Validate budgets, capability truth, continuation authority, diagrams/links, and runnable examples against the accepted provider. |
| Shared change/current contract/integration/design | `CHANGELOG.md`, `docs/STABILITY.md`, `docs/integration.md`, `docs/adapters.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T023 / `v2-observation-owner` | Accepting owner: `v2-integrator`; apply exact breaking-change, request, identity, relation, order, budget, gap, continuation, and diagram deltas at cutover. |
| Downstream surface references | `integrations/mcp-discord/README.md`, `integrations/mcp-discord/DESIGN.md`, `integrations/hermes/README.md`, `integrations/claude-code/README.md`, `integrations/codex/README.md` | `HANDOFF` | T023 / `v2-observation-owner` | Accepting owner: `v2-transport-owner`, `v2-hermes-owner`, `v2-claude-owner`, and `v2-codex-owner`; apply the exact I-020A identity/native-fact/budget/gap/continuation delta in each owned guide. |

The README handoff is an owned future delta, not `NO_IMPACT`; slice 020 must
land and validate its own reference before handoff.

## Owner Handoff

The handoff must include exact commit, I-020A version, shared module, capability
requirements, budget evidence, deterministic/recoverability commands and
reference results, comparator contract, suppression-eligibility limitations,
and explicit downstream proof instructions. It MUST state that no actual
surface, restart-safety, or parity claim was completed by reference variants.
Review does not transfer normalization ownership silently; 110 remains the sole
final integration sink.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.
