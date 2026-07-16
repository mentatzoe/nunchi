# Implementation Plan: V2 Contract

**Branch**: `v2/contract` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/010-v2-contract/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-contract-owner`

**Assigned participant / source**: cc-session-1 — evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/010-v2-contract`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/contract/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/contract/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/contract/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/contract/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Upstream dependencies**: none

**Dependency acceptance mapping**: activation evidence MUST use
`Accepted dependencies: none`, `Dependency commits: none`, and
`Dependency acceptance references: none`.

**Rejection / rework contract**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

## Summary

During authorized slice implementation, define and land the five canonical V2
interfaces before any dependent product implementation: attention request,
attention decision, participant wake, context continuation, and attention
receipt. The schemas and tests will make the clean V2 cutover mechanically
unambiguous while preserving the selected human-shaped product boundary. This
planning baseline creates no product behavior.

## Technical Context

**Language/Version**: JSON Schema Draft 2020-12 plus Python 3.11+ contract tests

**Primary Dependencies**: Python standard library at runtime; dev/test-only
`jsonschema==4.26.0` as the Draft 2020-12 oracle; no new runtime dependency

**Storage**: Filesystem schemas and immutable/append-only evidence only

**Testing**: stdlib `unittest`, one deterministic conformance corpus run through
both `jsonschema==4.26.0` and the explicit stdlib runtime validator, and
repository governance checks

**Target Platform**: All in-tree core, CLI, adapter, and harness consumers

**Project Type**: Versioned library/CLI and inter-component contract

**Performance Goals**: Contract validation remains negligible beside a model
call (full corpus dual-validator run completes offline in under a minute on
the reference machine); fixture suites remain deterministic and offline

**Constraints**: Atomic V2 replacement; no V1 bridge; exact self binding; no
social ledger or reply prose; transition margin remains independently gated;
opaque continuation authority never reaches the classifier; receipt stages are
immutable and singly written

**Scale/Scope**: Five canonical interfaces consumed by ten downstream slices,
culminating in one final parity integration

## Constitution Check

| Gate | Status | Planning evidence |
|---|---|---|
| Selected V2 boundary | PASS | Interfaces describe pre-attention and normal participant wake, never composition or floor allocation. |
| Human-shaped judgment | PASS | Contracts carry facts and narrow dispositions; they encode no deterministic social rule. |
| Truthful identity/observation | PASS | Exact self binding, literal relations, coverage, gaps, and unknowns are required. |
| Attention/contribution ownership | PASS | Decision and participant-wake contracts are distinct and forbid an admission meta-answer. |
| Atomic parity contract | PASS | One versioned contract set feeds every in-tree consumer with no V1 bridge. |
| Evidence before claims | PASS | Future tests, fixtures, evidence, and owner handoff are concrete. |
| Control-plane boundary | PASS | This directory contains only spec, plan, tasks, and requirements checklist. |
| Single owner and slice lifecycle | PASS | `v2-contract-owner` is sole owner; tasks remain `DORMANT` while the slice is `PLANNED`. |

Post-design re-check: PASS. Interface summaries remain planning prose; no
`data-model.md`, `contracts/`, `quickstart.md`, schema, fixture, test, evidence,
or product documentation is created here.

## Slice Interfaces

### Consumes

- Zoe-selected V2 technical design at Aleph Vault merge `c834e8c`; no upstream
  slice interface.

### Produces

- `I-010A AttentionRequestV2@1` at
  `schemas/v2/attention-request.schema.json`.
- `I-010B AttentionDecisionV2@1` at
  `schemas/v2/attention-decision.schema.json`: `status: ok` carries one of the
  four allowed classifier/effective pairs, `status: bypass` carries cause
  `preattention-disabled` and no classifier/effective disposition, and
  `status: error` remains operational.
- `I-010C ParticipantWakeV2@1` at
  `schemas/v2/participant-wake.schema.json`, including non-social source
  `PREATTENTION_BYPASS` without advice.
- `I-010D ContextContinuationV2@1` at
  `schemas/v2/context-continuation.schema.json`; handle, binding, cursor, and
  fetch authority are host-only. The classifier projection receives coverage
  and expansion capability booleans only.
- `I-010E AttentionReceiptV2@1` at
  `schemas/v2/attention-receipt.schema.json`, an immutable staged-record union
  for `observation`, `attention`, `participant-host`, and `transport`, correlated
  by request ID. Each stage owner appends only its stage; bypass attention records
  set `classifier_not_invoked` and carry trusted bypass provenance.

These target paths are outputs of authorized slice implementation. Interface
details here are planning summaries only.

### Contract validation commands

The runtime package remains dependency-free. The exact dev/test-only offline
contract command is:

```sh
uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
```

The package must already be present in the operator's uv cache; `--offline`
MUST fail rather than access the network. Under the repository baseline
(`python3 -m unittest` without the oracle), the stdlib runtime-validation
adapter and its corpus MUST still run and pass; oracle-dependent cases are
skipped only under that baseline, with an explicit skip count asserted so
absence is loud, and the pinned command above remains the sole complete
dual-validator run. No silent skips. The suite loads each case once and
runs it through both the Draft 2020-12 oracle and the stdlib runtime-validation
adapter. The 010 handoff owns the schemas, corpus, oracle result, and adapter
contract; each runtime owner must make its adapter pass the same corpus before
its own handoff.

## Integration Strategy

**Integration order**: 010 lands first. Slices 020 and 030 consume the tagged
contract commit in parallel. Slice 040 begins only after 010, 020, and 030 have
landed their handoffs.

**Worktree/branch**: future isolated worktree `.worktrees/v2-contract/` on
branch `v2/contract`

**Handoff to**: all named downstream owners for slices `020` through `110` and
`v2-integrator`

**Conflict ownership**: only `v2-contract-owner` edits `schemas/v2/**` until
the handoff is accepted. A dependent slice proposes
contract changes through an explicit return handoff and re-analysis.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01 Exact self and alias collision | Contract fixtures | Alias collision never establishes authorship; exact actor binding remains decisive. | `evidence/v2/contract/attention-request.jsonl` |
| S02 Native relations | Contract fixtures | Actor-targeted mentions and `mentions_room` remain distinct; native order and other literal relations survive. | `evidence/v2/contract/attention-request.jsonl` |
| S03 Bounded context and tail | Request/continuation fixtures | Trigger, coverage, already-observed tail, host-only continuation, and classifier-safe expansion flags are representable without an eager history dump. | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| S05 Governed suppression | Decision fixtures | Suppression legitimacy and policy widening are explicit; missing legitimacy cannot validate a hard stop. | `evidence/v2/contract/attention-decision.jsonl` |
| S08 Dual DEFER valves | Decision fixtures | Classifier-DEFER and margin-DEFER remain distinct and separately auditable. | `evidence/v2/contract/attention-decision.jsonl` |
| S09 Operational error | Decision fixtures | Invalid transitions and malformed evidence validate only as tagged error. | `evidence/v2/contract/attention-decision.jsonl` |
| S06 WAKE/bypass contribution | Wake/receipt fixtures | WAKE and `PREATTENTION_BYPASS` wake packets validate with distinct attention sources (no advice on bypass), and a participant-host stage can record a direct contribution act tied to the same request ID. | `evidence/v2/contract/downstream.jsonl` |
| S07 Participant silence | Wake/receipt fixtures | An invoked participant that sends nothing is representable as a distinct staged outcome — separate from suppression and from non-invocation — with no handled/owed/obligation field validating anywhere. | `evidence/v2/contract/downstream.jsonl` |
| S15 Context budget | Request/wake fixtures | Independent attention and participant event/byte budgets are explicit and positive. | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| S16 No registry or ledger | All five interfaces | Reply-bearing and handled/open/owed/permission fields fail validation. | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/attention-decision.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| 010-Preattention bypass | Decision/wake/receipt fixtures | Bypass invokes no classifier, produces `PREATTENTION_BYPASS`, and appends provenance without fabricating a social result. | `evidence/v2/contract/attention-decision.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| 010-V1 Breaking rejection | CLI/core-neutral fixtures | V1 envelopes are rejected with no translation bridge. | `evidence/v2/contract/attention-request.jsonl` |

Reusable fixtures and their runner target `evals/v2/contract/`; deterministic
tests target `tests/v2/contract/`. Every aggregate JSONL evidence record MUST
contain `scene_id`, stable `case_id`, validator identity, expected result, and
observed result. `evidence/v2/contract/README.md` is the exact manifest mapping
each S ID and slice-specific scene to its JSONL file and record IDs. Evidence
records commands and results, not embedded product payloads in this plan.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/010-v2-contract/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

No other file or directory is permitted in this slice.

### Ordinary repository targets for authorized slice implementation

```text
schemas/v2/
├── attention-request.schema.json
├── attention-decision.schema.json
├── participant-wake.schema.json
├── context-continuation.schema.json
└── attention-receipt.schema.json

tests/v2/contract/
├── schema_helpers.py
├── test_attention_request.py
├── test_attention_decision.py
├── test_participant_wake.py
└── test_context_and_receipt.py

evals/v2/contract/
docs/contracts/
└── nunchi-v2.md

evidence/v2/contract/
```

**Structure Decision**: The contract owner controls one ordinary schema
namespace. Tests, reusable fixture/evaluation assets, evidence, and product
documentation remain separately addressable ordinary artifacts.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning task/story |
|---|---|---|
| Machine-readable contracts | `schemas/v2/*.schema.json` | US1–US3 |
| Contract tests | `tests/v2/contract/test_*.py` | US1–US3 |
| Evaluation runner/corpus | `evals/v2/contract/` | US1–US3 |
| Evidence | `evidence/v2/contract/` | Cross-cutting |
| Product contract docs | `docs/contracts/nunchi-v2.md` | Cross-cutting |
| Product implementation | none in this slice | Excluded |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global current contract | `README.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; replace V1 verdict/request wording with accepted I-010A-E and breaking-cutover wording, plus the exact new dual-validator test command and dev/test-only `jsonschema==4.26.0` dependency wording, only in the atomic candidate. |
| V2 contract reference | `docs/contracts/nunchi-v2.md` (created by this slice) | `UPDATE` | T017 / `v2-contract-owner` | Validate interface names/versions, bypass/error separation, links, and examples against both validators. |
| Existing change, contract, integration, adapter, stability, and selected-design status | `CHANGELOG.md`, `docs/STABILITY.md`, `docs/integration.md`, `docs/adapters.md`, `docs/contracts/channel-adapter-v1.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; apply the exact breaking-change, supersession, interface-version, request/result, bypass, ERROR, and diagram delta at atomic cutover. |

`HANDOFF` preserves slice 110's ownership of global current-state wording; it
is not a no-impact finding. The exact candidate cannot hand off until both rows
and every exact path's validation/delta are recorded in ordinary handoff evidence.

## Owner Handoff

`v2-contract-owner` must hand off the exact commit, five interface versions and
paths, Draft/runtime validator results over the same corpus, exact offline
command, scene-to-record evidence manifest, staged-receipt writer map,
rejected-case inventory, migration/provenance notes, and known limitations.
Acceptance by a dependent owner does not transfer schema ownership.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.
