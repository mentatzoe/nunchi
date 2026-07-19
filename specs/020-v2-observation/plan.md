# Implementation Plan: V2 Observation

**Branch**: `v2/observation` | **Date**: 2026-07-11 (dependency-acceptance alignment to accepted 010 attempt-6, 2026-07-18; convergence-rework replanning and accepted I-010E `@2` amendment rebind, 2026-07-19; Phase 11 residual around-fetch truthfulness correction binding, 2026-07-19; Phase 11 (T054) implemented and closed, 2026-07-19; Phase 12 attempt-1 integrator-rejection rework bound, 2026-07-19; documentation-impact matrix split to one row per exact file with its single accepting owner, 2026-07-19) | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/020-v2-observation/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-observation-owner`

**Assigned participant / source**: Aleph — evidence/governance/assignments/aleph-v2-observation-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/020-v2-observation`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `ACTIVE`

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

This replanning pass additionally governs the convergence and independent
pre-review rework appended against the completed T001–T038 candidate: native
`reaction`/`membership` documentation coverage; the FR-004 exact-causation
self-event scope (`author_id` for authored events, `caused_by_actor_id` for
membership, never passive `subject_actor_id` alone); FR-007 `event_visibility`
propagation and evidence;
handoff-packet (`evidence/v2/observation/handoff.md`) accuracy, recipient, and
version freshness; direction-bound cursor replay; truthful side-specific
`around` coverage; and the accepted I-010E `@2` no-code consumer rebind. The
slice remains `ACTIVE`, retains its original activation, and proceeds through a
new bound run to a new candidate/handoff attempt per the Rejection/rework
contract above. Durable correction sources are
`evidence/v2/observation/convergence-2026-07-19.md` and
`evidence/v2/observation/pre-review-2026-07-19-sr-critic.md`.

A same-day post-T053 `/speckit-converge` re-run against the completed
T001–T053 tree found one residual CRITICAL defect, F1, in the Phase 10
(T049/T050) `around`-fetch side-coverage fix itself: `ContinuationProvider.fetch`
tracks the ascending-scan cap-truncation index (`next_index`) as an
after-side-only signal and derives `has_more_before` from the fixed radius
window boundary alone (`around_window_start > 0`); a per-fetch event/byte cap
that truncates the scan at a candidate index strictly before `anchor_index`
therefore still reports `has_more_before: False` even though a genuine
unserved before-anchor event exists. This was bound as Phase 11 (T054) in
`tasks.md`, unchecked and unimplemented as of the planning pass that recorded
it, and required tracking which side of `anchor_index` a cap actually
truncated at — in addition to, not instead of, the existing window-boundary
checks — before a new candidate could be proposed. The finding is durably
recorded at `evidence/v2/observation/convergence-phase11-2026-07-19.md`
against exact candidate commit `77a94cf1f56e70d1f0a79631ee9efba0b6e74a62`.

T054 is now implemented and closed: `has_more_before` ORs the
window-boundary check with a new `cap_truncated_before_anchor` term
(`next_index is not None and next_index < anchor_index`); `has_more_after`'s
formula is unchanged because any cap truncation within the ascending window
scan already always left the anchor-or-later portion unserved. A RED→GREEN
regression test, a matching adversarial eval case (`CONT-S03-007`), and a
complete rerun of the full T053 verification matrix are recorded in
`evidence/v2/observation/handoff.md`'s "Phase 11 convergence supersession
(T054)" section against final full-manifest task IDs T001–T054, SHA256
`b305267271aed22a83c98c3a95e8f967edfbe080115d9ee58d6a99eacaca4536`.

The assigned `v2-integrator` rejected attempt 1 after independently
reproducing two continuation defects against candidate
`7b00bcaa4a2b8af12b6eb71bf6d8b098f4cfeba7`: an `around` fetch minted a
cursor but ignored it on replay, returning the same events and same cursor
forever (H020-A1-01 HIGH), and every capped continuation fetch reported
`truncated_by: ["events"]` even when a byte cap was the actual stop cause
(M020-A1-02 MEDIUM). The durable decision is
`evidence/v2/observation/review-2026-07-19-v2-integrator-attempt-1.md` and the
append-only rejection is in `evidence/v2/observation/slice-handoff.md`.
Phase 12 (T055–T059) is the complete correction owed before candidate attempt
2; the original activation is retained and the slice returns to `ACTIVE`.

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

**Performance Goals**: hard event/byte caps on every snapshot and fetch;
serialized UTF-8 size plus the deterministic, explicitly non-model-specific
`utf8-bytes-ceil-div4@1` token-size proxy recorded only in separate evidence as
`(serialized_utf8_bytes + 3) // 4`, with `estimator_id`, `estimated_tokens`,
`serialized_bytes`, and `model_id: null`

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
| Truthful identity/observation | BLOCKED (T061–T064) | Phase 12 made `around` identity-safe, but independent attempt-2 convergence review H020-A2-01 proved `before`/`after` cursor replay still consumes stale deque positions after retention shifts, causing duplicate or skipped events while claiming no gap. T061–T064 bind identity-preserving replay or fail-closed eviction behavior for every direction. |
| Attention/contribution split | PASS | I-020A ends at request/continuation production and does not route participant turns. |
| Atomic parity contract | PASS | I-020A and its comparator define one shared seam; downstream slices prove each native binding and 110 proves final parity. |
| Evidence before claims | BLOCKED (T061–T065) | The Phase 12 matrix remains accurate for its candidate, but H020-A2-01 invalidates convergence. T061–T065 require RED→GREEN retention-shift tests, deterministic eval evidence, regenerated exact row counts, and a fresh complete verification matrix before candidate-attempt-2 preparation. |
| Control-plane boundary | PASS | Only four planning artifact types exist in this directory. |
| Single owner and slice lifecycle | PASS | `v2-observation-owner` owns I-020A; the slice remains `ACTIVE` through correction and may advance only through a new candidate and independent handoff attempt. |

Post-design re-check: BLOCKED on H020-A2-01. T055–T060 remain complete and
historically accurate, but T061–T065 must make `before` and `after` cursor
replay identity-safe across retention shifts, regenerate evidence, and rerun
the complete matrix. Candidate attempt 2 and its handoff still require the
ordinary convergence/candidate/handoff lifecycle after those tasks are GREEN.

## Slice Interfaces

### Consumes

- `I-010A AttentionRequestV2@1` from 010 at
  `schemas/v2/attention-request.schema.json`.
- `I-010D ContextContinuationV2@1` from 010 at
  `schemas/v2/context-continuation.schema.json`.
- The immutable staged-record shape of `I-010E AttentionReceiptV2@2` at
  `schemas/v2/attention-receipt.schema.json`, accepted at exact amendment
  candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb` / integrator decision
  `30aba09f13a6752b4c24811da0d8ec772a9d9682` in
  `evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`. The
  consumer comparison proves `observationBody` unchanged from accepted `@1`
  (canonical SHA256
  `2b8b50f77007d79a8bc682d8e3c6c7f093b14ce5ddea1d6b56a759303ccae687`),
  so this is an explicit no-code version rebind; only the separately owned
  `attentionBody` changed.

### Produces

- `I-020A ObservationProviderV2@1` in future shared code at
  `src/nunchi/observation.py`, returning a bounded I-010A request whose optional
  continuation field carries the accepted capability shape, plus the
  observation-stage I-010E record for facts this slice can attest. Its separate
  host-owned fetch seam consumes I-010D fetch-request documents and returns
  I-010D fetch-page documents; I-010D is not itself a provider. Later owners
  append separately correlated, immutable stages; they never mutate this
  record. Token-size proxy results remain separate evidence because accepted
  I-010E is closed and contains no token field.

## Integration Strategy

**Integration order**: 010 contract handoff → shared normalizer/buffer/assembler
→ continuation seam → reference replay/recoverability/comparison evidence
→ downstream handoff. Slice 030 can implement in parallel against I-010A and
alone owns classifier-safe projection/redaction in `src/nunchi/core.py`;
050 and 060–090 bind and prove native surfaces only after accepting I-020A, and
110 owns the final comparison.

**Worktree/branch**: future isolated worktree `.worktrees/v2-observation/` on
branch `v2/observation`

**Handoff to**: `v2-wake-owner` (040), `v2-transport-owner` (050),
`v2-hermes-owner` (060), `v2-claude-owner` (070), `v2-codex-owner` (080),
`v2-adapters-owner` (090), `v2-security-owner` (100), and `v2-integrator`
(110) — the exact set matching spec.md's declared `Feeds` list, never a
generic "owners of slices 040 through 110" reference

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
| S15 Context budget | Shared assembler | Snapshot and fetch hard caps are enforced with accepted I-010E byte telemetry; the separately labelled `utf8-bytes-ceil-div4@1` proxy is evidence only and makes no model-tokenizer claim. | `evidence/v2/observation/budget-sweep.jsonl`, `evidence/v2/observation/continuation.jsonl` |
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
| Global context/identity description | `README.md` | `HANDOFF` | T028, T034 / `v2-observation-owner` | Accepting owner: `v2-integrator`; add only evidence-proven exact-self, native-relation, budget, gap, and continuation claims at atomic cutover. |
| Observation reference | `docs/observation/v2.md` | `UPDATE` | T026, T027, T034, T039, T040, T044, T046, T052 / `v2-observation-owner`; T054 and T055–T059 reviewed as evidence-backed `NO_IMPACT` for this path / `v2-observation-owner` | Validate budgets, continuation authority, diagrams/links, and runnable examples against the accepted provider; explicitly cover `message`, `reaction`, and `membership` native event examples with honest-unavailability representation (T039); document the resolved exact-causation self-membership scope, `caused_by_actor_id == self.actor_id` retained versus passive `subject_actor_id` observed (T040); explain the `restart-safe`/`session-only`/`unknown`/`known-gap` capability vocabulary for reference-variant consumers (T044); correct the "What this slice does not do" section to name the real `v2-core-owner` lane rather than the nonexistent `v2-attention-owner` (T046); update the I-010E version citation from `@1` to accepted `@2`, noting `observationBody` is unchanged (T052); and Phase 11's T054 (`src/nunchi/observation.py`, `tests/v2/observation/test_budget_and_continuation.py`, `evals/v2/observation/continuation/cases.jsonl`, `evidence/v2/observation/continuation.jsonl`, `evidence/v2/observation/handoff.md`) needs no wording change here — the existing "`has_more_before`/`has_more_after` report honest boundary omission" claim already states the target truthful behavior; T054 only brings the implementation into conformance with it and carries its own evidence delta in `handoff.md`'s Phase 11 supersession, not in this document. Phase 12's T055–T058 (same implementation file plus the same test/eval/evidence paths) likewise need no wording change here: this document's "Optional continuation" example demonstrates only a single `before` fetch and never depicts `around` cursor replay, so it makes no claim H020-A1-01 contradicts, and its existing general "`coverage.truncated_by` names every limit that actually excluded a candidate" claim (line 158) already states the truthful per-cause target M020-A1-02 requires — T055–T058 bring the implementation into conformance with both existing claims and carry their own RED→GREEN evidence delta in `handoff.md`'s attempt-1 rejection supersession (T059), not in this document; T059 itself is an evidence/handoff-only task with no doc wording of its own. |
| Accepted 010 contract reference | `docs/contracts/nunchi-v2.md` | `NO_IMPACT` | T034 plus 2026-07-19 dependency rebind / `v2-observation-owner` | Evidence-backed rationale: slice 020 consumes I-010A@1/I-010D@1 and accepted I-010E@2; `evidence/v2/observation/dependency-010-amendment-A1-acceptance.md` proves the observation-stage definition byte-for-byte unchanged while the amendment affects only the separately owned attention stage. The slice-owned implementation needs no code change, but current handoff/docs citations must name `@2`. |
| Shared changelog | `CHANGELOG.md` | `HANDOFF` | T029, T034 / `v2-observation-owner` | Accepting owner: `v2-integrator`; apply the exact breaking I-020A/current-state wording delta at cutover. |
| Shared stability notice | `docs/STABILITY.md` | `HANDOFF` | T029, T034 / `v2-observation-owner` | Accepting owner: `v2-integrator`; apply the exact breaking I-020A/current-state wording delta at cutover. |
| Shared integration guide | `docs/integration.md` | `HANDOFF` | T029, T034 / `v2-observation-owner` | Accepting owner: `v2-integrator`; apply the exact request/identity/relation/order/budget/gap/continuation integration wording delta at cutover. |
| Shared adapter guide | `docs/adapters.md` | `HANDOFF` | T029, T034 / `v2-observation-owner` | Accepting owner: `v2-integrator`; apply the exact request/identity/relation/order/budget/gap/continuation integration wording delta at cutover. |
| Shared architecture diagram | `docs/architecture/v2-selected-design.md` | `HANDOFF` | T029, T034 / `v2-observation-owner` | Accepting owner: `v2-integrator`; apply the exact observation/host-only-continuation diagram-boundary delta at cutover. |
| MCP-Discord surface guide | `integrations/mcp-discord/README.md` | `HANDOFF` | T030, T034 / `v2-observation-owner` | Accepting owner: `v2-transport-owner`; apply the exact I-020A identity/native-fact/order/budget/gap/continuation delta. |
| MCP-Discord design guide | `integrations/mcp-discord/DESIGN.md` | `HANDOFF` | T030, T034 / `v2-observation-owner` | Accepting owner: `v2-transport-owner`; apply the exact I-020A identity/native-fact/order/budget/gap/continuation delta. |
| Hermes surface guide | `integrations/hermes/README.md` | `HANDOFF` | T031, T034 / `v2-observation-owner` | Accepting owner: `v2-hermes-owner`; apply the exact I-020A identity/native-fact/order/budget/gap/continuation delta. |
| Claude Code surface guide | `integrations/claude-code/README.md` | `HANDOFF` | T032, T034 / `v2-observation-owner` | Accepting owner: `v2-claude-owner`; apply the exact I-020A identity/native-fact/order/budget/gap/continuation delta. |
| Codex surface guide | `integrations/codex/README.md` | `HANDOFF` | T033, T034 / `v2-observation-owner` | Accepting owner: `v2-codex-owner`; apply the exact I-020A identity/native-fact/order/budget/gap/continuation delta. |

The README handoff is an owned future delta, not `NO_IMPACT`; slice 020 must
land and validate its own reference before handoff.

## Owner Handoff

The handoff must include exact commit, I-020A version, shared module, capability
requirements, budget evidence, deterministic/recoverability commands and
reference results, comparator contract, suppression-eligibility limitations,
the accepted-I-010E token-field limitation, and explicit downstream proof
instructions. It MUST name every recipient exactly — `v2-wake-owner` (040),
`v2-transport-owner` (050), `v2-hermes-owner` (060), `v2-claude-owner` (070),
`v2-codex-owner` (080), `v2-adapters-owner` (090), `v2-security-owner` (100),
and `v2-integrator` (110) — matching spec.md's declared `Feeds` list, never a
partial or generic subset. It MUST also hand the I-010A expansion-availability
input to `v2-core-owner` (030, the umbrella-registered accountable owner lane
for `030-v2-core-attention`) while leaving classifier-safe projection/
redaction wholly owned by that same slice 030. It MUST state that no actual
surface, restart-safety, or parity claim was completed by reference variants.
Review does not transfer normalization ownership silently; 110 remains the sole
final integration sink.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.
