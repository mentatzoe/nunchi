# Implementation Plan: V2 Contract

**Branch**: `v2/contract` | **Date**: 2026-07-11 (corpus-path and documentation-matrix refresh 2026-07-17; post-rejection R1/R2/R3 alignment to the clarified spec, same day; post-rejection R4/R5/R6 selected-design-fidelity alignment 2026-07-18) | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/010-v2-contract/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-contract-owner`

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-contract-owner-2026-07-23.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/010-v2-contract`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `ACCEPTED`

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

**Task manifest**: `python3 scripts/check_governance.py --task-manifest specs/010-v2-contract`

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
repository governance checks; the full offline baseline `python3 -m unittest`
must pass from the exact candidate commit and from the exact handoff packet
commit (the R1 rejection basis)

**Target Platform**: All in-tree core, CLI, adapter, and harness consumers

**Project Type**: Versioned library/CLI and inter-component contract

**Performance Goals**: Contract validation remains negligible beside a model
call (advisory, not gated: the full corpus dual-validator run is expected to
complete offline in well under a minute); fixture suites remain deterministic and offline

**Constraints**: Atomic V2 replacement; no V1 bridge; exact self binding; no
social ledger or reply prose; transition margin remains independently gated;
the legacy verdict confidence vector is optional on `status: ok` and required
exactly for a margin-active candidate `SUPPRESS` (FR-007); opaque continuation
authority never reaches the classifier; receipt stages are immutable and singly
written, with the stage-to-writer binding part of the public per-record
contract (FR-010); the selected design at `c834e8c` is the field-level naming
and shape authority for every `@1` interface, so schemas encode the selected
field inventory rather than a narrowed local shape (FR-014)

**Scale/Scope**: Five canonical interfaces consumed by ten downstream slices,
culminating in one final parity integration

This refresh follows the first candidate's rejection recorded at
`evidence/v2/contract/review-2026-07-17-v2-integrator.md` and the spec's
2026-07-17 clarification session. It aligns the I-010B and I-010E planning
summaries with the conditional FR-007 legacy-vector rule and closed FR-005
routing-audit set (R2) and the schema-expressible FR-010 per-record
stage-to-writer binding (R3), and names the exact R1 governance-fixture repair
target so the full offline baseline is green from the next handoff packet
commit. Rework lands only through the new bound delivery run; the rejected
attempt stream is preserved unchanged.

The attempt-2 candidate was in turn rejected at
`evidence/v2/contract/review-2026-07-17-v2-integrator-attempt-2.md`, and the
spec's 2026-07-18 clarification session encodes that decision: the five public
`@1` schemas must encode the selected design's field inventory rather than
narrowed local shapes (R4; FR-014); the corpus must carry
authority-conformance cases drawn from the selected design, which fail against
the narrowed attempt-2 shapes and pass after the schema repair (R4 rework
path; FR-012, SC-001); the delivered packet must name one identical exact
candidate commit across the lifecycle candidate entry, the handoff attempt
entry, the packet input, and the recorded corpus revision (R5; SC-005); and
the task graph must state execution status by reference to the slice
declarations and lifecycle evidence, never as a hard-coded state-specific
claim (R6; SC-005). This third refresh aligns the plan with those
clarifications. Rework again lands only through a new bound delivery run;
both rejected attempt streams are preserved unchanged.

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
| Documentation freshness | PASS | `README.md` and every known ordinary doc receive exactly one file-by-file `UPDATE`, `NO_IMPACT`, or `HANDOFF` row with owning task, accepting owner, and validation or exact delta; no generic directory rows. |

Post-design re-check: PASS. Interface summaries remain planning prose; no
`data-model.md`, `contracts/`, `quickstart.md`, schema, fixture, test, evidence,
or product documentation is created here. The documentation-impact matrix names
each reviewed ordinary document individually with a per-file disposition and
per-file validation or handoff delta. The 2026-07-17 post-rejection alignment
restates — and defers to — the clarified spec: the conditional FR-007 vector,
the closed FR-005 routing audit, and the schema-expressible FR-010
stage-to-writer binding introduce no new gate exposure. The 2026-07-18
attempt-2 alignment likewise defers to the clarified spec: FR-014
selected-design fidelity binds the schemas more tightly to the pinned higher
authority at `c834e8c`, and the R5/R6 packet-consistency rules constrain
evidence and task-graph wording only; no new gate exposure is introduced.

## Slice Interfaces

### Consumes

- Zoe-selected V2 technical design at Aleph Vault merge `c834e8c`; no upstream
  slice interface.

### Produces

- `I-010A AttentionRequestV2@1` at
  `schemas/v2/attention-request.schema.json`, encoding the selected field
  inventory (FR-014): the room platform/id/continuity-scope/name/kind facts
  and the actor map; the typed message, reaction, and membership event union
  with reaction `add`/`remove` operation and literal membership scope,
  subject actor, and optional causal actor; and the coverage facts
  (`has_more_before`, `has_more_after`, `has_gaps`, `truncated_by`,
  `continuity`, `has_restart_gap`, and optional per-event-type visibility).
  A generic event shape or collapsed coverage enums are contract defects,
  and the design's example attention request validates verbatim.
- `I-010B AttentionDecisionV2@2` (amended post-acceptance from `@1`; FR-005
  amendment A2) at
  `schemas/v2/attention-decision.schema.json`: `status: ok` carries one of the
  four allowed classifier/effective pairs; `reasons` retained as ok-branch
  audit material that never enters the participant turn; an optional legacy
  verdict confidence vector that is required exactly when the classifier
  disposition is `SUPPRESS` while the routing audit reports the margin
  `active` (FR-007, superseding the rejected every-ok-decision requirement);
  and a closed routing audit recording the applied valve (`none`,
  `classifier-defer`, `margin-defer`, or `policy-defer`), the override cause
  (`none`, `margin`, `suppression-disabled`, or `recoverability-unproven`),
  the margin status (`active` or `retired`), the effective margin when one
  applied, and the trusted margin source when present. `status: bypass`
  carries cause `preattention-disabled` and no classifier/effective
  disposition, and `status: error` remains operational. The public field
  names are the selected `routing_audit` and `legacy_verdict_confidences`,
  the classifier audit names the classifier with optional provider and
  model, and the request ID on a pre-validation error is optional (FR-014,
  superseding the rejected `routing`/`legacy_confidence` local shapes and
  the mandatory error request ID).
- `I-010C ParticipantWakeV2@1` at
  `schemas/v2/participant-wake.schema.json`, including non-social source
  `PREATTENTION_BYPASS` without advice. The wake packet materializes self,
  room, actors, events, trigger, coverage, optional host-only continuation
  authority for the woken participant, and a separate `attention` object
  (FR-014), not a wrapped classifier projection.
- `I-010D ContextContinuationV2@1` at
  `schemas/v2/context-continuation.schema.json`, defining the selected
  continuation capability (`handle_id`, exact `bound_to`, before/after/around
  fetch capabilities, per-fetch caps, optional expiry) with directional
  anchor-bearing fetch shapes and pages that carry room and continuity-scope
  identity, direction, anchor, actor map, and page binding (FR-014); handle,
  binding, cursor,
  expiry values, and fetch authority are host-only. The classifier projection receives coverage
  and expansion capability booleans only.
- `I-010E AttentionReceiptV2@2` (amended post-acceptance from `@1`; FR-010
  amendment A1) at `schemas/v2/attention-receipt.schema.json`, an immutable
  staged-record union for `observation`, `attention`, `participant-host`,
  and `transport`, correlated by request ID. Each stage owner appends only its stage, and the
  stage-to-writer binding is part of the public per-record contract: each stage
  names its single directly observing owner as writer, and a record attributing
  one stage to another stage's owner is invalid as a single document in both
  validators (FR-010, closing the rejected cross-owner attestation gap), in
  addition to the runtime stream-level ordering and immutability checks. Bypass
  attention records set `classifier_not_invoked` and carry trusted bypass
  provenance. Each stage carries the selected telemetry (FR-014): observation
  request/schema/trigger/continuity IDs, snapshot sizes, coverage, and
  included event IDs; attention classifier identity, evidence, and
  transition-valve facts or the bypass fact with trusted provenance;
  participant-host wake source, packet sizes, delivered event IDs, expansion
  calls, and invocation and `sent`/`silent`/`unknown` outcome; transport
  hygiene and routing/send facts.

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
adapter, honoring the FR-012 partition: schema-expressible cases assert
identical results from both validators; semantic/relational cases assert
through the runtime adapter with the oracle treatment fixed per class exactly
as spec FR-012 states — the four document-shaped relational classes
(cross-item ID uniqueness, timestamp-versus-order agreement, cross-document
advice citations, trigger membership) are oracle-expected-valid, because each
document is schema-valid in isolation, and the two behavioral/sequence classes
(fetch-time binding/expiry state, receipt-stage sequence rules) are
oracle-class-skipped, because there is no single document to validate — with
per-class counts asserted. No other class-to-treatment mapping is permitted.
Per the clarified FR-010, a single receipt record attributing its stage to
another stage's owner is a schema-expressible red case asserting identical
rejection from both validators; the runtime-adapter-only receipt-stage
sequence class covers the multi-record stream checks (canonical order, skipped
stages, earlier-stage mutation, request-ID correlation, and stream-level
writer ownership), where no single document exists to validate. The corpus
additionally carries the FR-014 authority-conformance cases drawn from the
selected design at `c834e8c`: the design's example attention request
validates verbatim as a schema-expressible valid case, and named cases cover
the complete typed event, coverage, continuation capability/fetch/page,
participant-wake, decision, and four-stage receipt field inventories. These
cases fail against the narrowed attempt-2 shapes and pass after the schema
repair; a corpus that is merely self-consistent with narrower schemas does
not establish conformance (SC-001), and a document the selected design
declares valid that either validator rejects is a contract defect, never
resolved by narrowing the corpus. The 010
handoff owns the schemas, corpus, oracle result, and adapter
contract; each runtime owner must make its adapter pass the same corpus before
its own handoff.

## Post-Rejection Planning Decisions (2026-07-17)

Rejection source: `evidence/v2/contract/review-2026-07-17-v2-integrator.md`
for candidate `81483ce017eb834c5ab533556fa64cd62a8cf2aa` at packet commit
`9f08124b43ba5beb73c50b876bde51e7b8a1633d`. Each blocker resolves to one
planning decision; the delivery tasks step appends the matching correction
tasks without rewriting completed history.

- **Decision (R2)**: I-010B makes the legacy verdict confidence vector
  optional on `status: ok`, required exactly for a candidate `SUPPRESS` whose
  routing audit reports the margin `active`, and closes the routing audit to
  the selected five-fact set with `reasons` retained as ok-branch audit
  material. **Rationale**: the selected design at `c834e8c` and the spec's
  2026-07-17 clarification session define this shape; the rejected schema
  required the vector on every ok decision and admitted only `route` and
  `override_cause`. **Alternatives considered**: keeping the every-ok-decision
  vector requirement — rejected by the integrator as unable to represent a
  valid `WAKE` without a legacy vector or a routing audit with
  `margin_status`.
- **Decision (R3)**: the I-010E stage-to-writer binding is encoded in the
  public per-record contract so a cross-owner record fails both the Draft
  2020-12 oracle and the individual stdlib validator, while stream-level
  ordering/immutability checks remain in addition. **Rationale**: the selected
  contract requires each immutable stage to be singly attested by its directly
  observing owner; owner enforcement that lived only in the stream validator
  accepted forged individual records. **Alternatives considered**:
  stream-only enforcement — rejected because a single forged document
  validated in isolation.
- **Decision (R1)**: repair the
  `tests/test_governance.py` activation-path fixture so it constructs its
  synthetic planning baseline independently of the repository's live slice
  state, then require the full offline baseline green from the exact handoff
  packet commit, not only the candidate commit. **Rationale**: the rejected
  packet commit failed `python3 -m unittest` because the fixture replaced only
  `PLANNED` declarations and inherited the live `HANDOFF_READY` records.
  **Alternatives considered**: rerunning the baseline only at the candidate
  commit — rejected; the handoff gate covers the packet commit itself.
  **Verifiable invariant, not a one-off description**: the fixture MUST
  replace every live slice declaration and lifecycle record it stages — not
  only `PLANNED` ones — so its synthetic baseline is independent of the
  repository's live slice state, and the named regression proof
  `tests.test_governance.GovernanceBoundaryTests.test_activation_fixture_is_independent_of_live_slice_state`
  MUST keep that baseline green while live slice declarations read `ACTIVE`
  or `HANDOFF_READY`; a partially decoupled fixture that passes only by
  coincidence of the current live state fails this proof.

## Post-Rejection Planning Decisions (2026-07-18, attempt 2)

Rejection source:
`evidence/v2/contract/review-2026-07-17-v2-integrator-attempt-2.md` for
candidate `001fdf85acd5098264c4975559c97114aa7278af` at packet commit
`5383e9f3a5e9c20c08ab54395f4ff370128f03de`. Each blocker resolves to one
planning decision; the new bound delivery run appends the matching correction
tasks without rewriting completed history.

- **Decision (R4)**: all five `@1` schemas and the stdlib runtime adapter
  encode the selected design's field-level naming and shape inventory exactly
  as spec FR-014 enumerates it — the room facts and actor map; the typed
  message/reaction/membership event union; the selected coverage facts; the
  continuation capability with directional anchored fetch and
  identity-bearing pages; the materialized wake packet with a separate
  `attention` object; the decision field names `routing_audit` and
  `legacy_verdict_confidences` with a classifier audit naming the classifier
  with optional provider and model and an optional request ID on a
  pre-validation error; and the four receipt stages' telemetry — and the
  corpus gains the FR-012 authority-conformance cases, including the design's
  example attention request verbatim. **Rationale**: the selected design at
  `c834e8c` is the higher authority; the integrator's targeted stdlib-adapter
  probes showed representative selected-design documents rejected by the
  attempt-2 schemas, and a corpus self-consistent with the narrowed shapes
  establishes nothing. **Alternatives considered**: keeping the locally
  named/narrowed shapes and widening the corpus around them — rejected
  because the defect is in the contract; narrowing or bending the corpus can
  never resolve it (FR-014).
- **Decision (R5)**: the delivered packet pins one commit identity — the
  lifecycle candidate entry, the handoff attempt entry, the packet input in
  `evidence/v2/contract/handoff.md`, and the recorded corpus revision name
  the identical exact candidate commit, and the actual handoff packet commit
  is recorded in the same terms once it exists; a placeholder, future-valued,
  or divergent commit identity anywhere in a delivered packet blocks
  acceptance. **Rationale**: the attempt-2 packet named three incompatible
  commit identities; exact evidence identity is the acceptance boundary and
  cannot be inferred from tree similarity (SC-005). **Alternatives
  considered**: accepting byte-identical trees under differing commit names —
  rejected by the integrator; identity is per-commit, not per-tree.
- **Decision (R6)**: the task graph states execution status only by reference
  to the slice declarations and lifecycle evidence — never as a hard-coded
  state-specific claim that a later transition falsifies — so the task graph,
  declarations, and lifecycle evidence agree at every packet commit.
  **Rationale**: the attempt-2 packet shipped a task-graph claim that the
  slice was mid-implementation inside a handoff-ready packet, false at the
  packet commit and false again at every future handoff if left
  state-specific. **Alternatives considered**: re-editing a hard-coded state
  line at each transition — rejected as a recurring consistency hazard the
  referential wording removes permanently.

## Integration Strategy

**Integration order**: 010 lands first. Slices 020 and 030 each independently
accept and record the exact contract commit in parallel (per-consumer
acceptance references, never a shared acceptance; the accepted identifier is
the exact full commit named by the T019 packet — no git tag is required or
implied). Slice 040 begins only after 010, 020, and 030 have
landed their handoffs.

**Worktree/branch**: future isolated worktree `.worktrees/v2-contract/` on
branch `v2/contract`

**Handoff to**: all named downstream owners for slices `020` through `110` and
`v2-integrator`

**Conflict ownership**: only `v2-contract-owner` edits `schemas/v2/**` until
the handoff is accepted. A dependent slice proposes contract changes through
an explicit return handoff — naming the requesting slice and owner, the exact
schema paths and `@` versions, the proposed delta, the motivating scene or
failing case, and known impact on other consumers — followed by re-analysis.

**Shared governance-infrastructure edit (rejection R1)**:
`tests/test_governance.py` is repository governance infrastructure, not part
of the `schemas/v2/**`/`tests/v2/contract/` surface the sole-owner conflict
rule above covers. For this rework, `v2-contract-owner` performs that edit
itself, as an in-scope ordinary rework output of this slice (spec
§Control-Plane Boundary), and `v2-integrator` reviews the edit at handoff as
part of the packet; no other lane edits that file during this slice, so the
R1 fix cannot become an unowned cross-lane edit.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01 Exact self and alias collision | Contract fixtures | Alias collision never establishes authorship; exact actor binding remains decisive. | `evidence/v2/contract/attention-request.jsonl` |
| S02 Native relations | Contract fixtures | Actor-targeted mentions and `mentions_room` remain distinct; native order and other literal relations survive. | `evidence/v2/contract/attention-request.jsonl` |
| S03 Bounded context and tail | Request/continuation fixtures | Trigger, coverage, already-observed tail, host-only continuation, and classifier-safe expansion flags are representable without an eager history dump. | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| S05 Governed suppression | Decision fixtures | Suppression legitimacy follows the conditional FR-007 rule: a margin-active candidate `SUPPRESS` validates only with the valid legacy vector, a `WAKE` or `DEFER` without the optional vector stays valid, and policy widening remains explicit. | `evidence/v2/contract/attention-decision.jsonl` |
| S08 Dual DEFER valves | Decision fixtures | Classifier-DEFER and margin-DEFER remain distinct and separately auditable. | `evidence/v2/contract/attention-decision.jsonl` |
| S09 Operational error | Decision fixtures | Invalid transitions and malformed evidence validate only as tagged error. | `evidence/v2/contract/attention-decision.jsonl` |
| S06 WAKE/bypass contribution | Wake/receipt fixtures | WAKE and `PREATTENTION_BYPASS` wake packets validate with distinct attention sources (no advice on bypass), and a participant-host stage can record a direct contribution act tied to the same request ID. | `evidence/v2/contract/downstream.jsonl` |
| S07 Participant silence | Wake/receipt fixtures | An invoked participant that sends nothing is representable as a distinct staged outcome — separate from suppression and from non-invocation — with no handled/owed/obligation field validating anywhere. | `evidence/v2/contract/downstream.jsonl` |
| S15 Context budget | Request/wake fixtures | Independent attention and participant event/byte budgets are explicit and positive. | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| S16 No registry or ledger | All five interfaces | Reply-bearing and handled/open/owed/permission fields fail validation. | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/attention-decision.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| 010-Preattention-bypass | Decision/wake/receipt fixtures | Bypass invokes no classifier, produces `PREATTENTION_BYPASS`, and appends provenance without fabricating a social result. | `evidence/v2/contract/attention-decision.jsonl`, `evidence/v2/contract/downstream.jsonl` |
| 010-V1 Breaking rejection | CLI/core-neutral fixtures | V1 envelopes are rejected with no translation bridge. | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/downstream.jsonl` |

The six umbrella parity scenes absent from this table — written here in the
hyphenated form S-04 and S-10 through S-14 because this plan's literal scene
tokens are machine-derived into the activation enumeration — are owned by
other slices per the program plan's parity scene table in
`specs/001-nunchi-v2-program/plan.md`: false-suppression scars (S-04) by
slices `020`/`030`/`050`–`100`/`110`; no send-time social gate (S-10) by
`040`/`060`–`100`/`110`; transport hygiene (S-11) and adapter equivalence
(S-13) by `020`/`050`/`090`/`100`/`110`; installed provenance (S-12) by
`050`–`110`; and the mixed-harness room (S-14) by `050`–`100`/`110`. Slice
`010` contributes no row to them, so their absence here is scene ownership,
not a coverage gap.

Reusable corpus assets are partitioned per interface family at exactly
`evals/v2/contract/attention-request/`,
`evals/v2/contract/attention-decision/`, and `evals/v2/contract/downstream/`,
each holding `cases.jsonl` and its authoritative per-class
`expected-counts.json`; the `tests/v2/contract/` suite is the corpus runner;
deterministic
tests target `tests/v2/contract/`. Each family's `cases.jsonl` also carries
its named FR-014 authority-conformance cases — the selected design's example
attention request verbatim in the attention-request family, and complete
field-inventory cases in every family — recorded under the scene IDs the
family's rows above already carry, as schema-expressible valid cases counted
as their own class in `expected-counts.json` — never a new partition class
with its own oracle treatment — and flagged as authority cases in the
manifest so the class cannot silently shrink. Every aggregate JSONL evidence record MUST
contain `scene_id`, stable `case_id`, validator identity, expected result, and
observed result. `evidence/v2/contract/README.md` is the exact manifest mapping
each S ID and slice-specific scene to its JSONL file and record IDs. Evidence
records commands and results, not embedded product payloads in this plan.

Attempt rework semantics for contract-run evidence (the lifecycle streams'
append-only rule does not cover these files, so the rule is written here):
after a rejection changes the corpus or schemas, the aggregate JSONL files
(`attention-request.jsonl`, `attention-decision.jsonl`, `downstream.jsonl`)
and the manifest `evidence/v2/contract/README.md` regenerate in place as
current-attempt records; `evidence/v2/contract/handoff.md` and
`evidence/v2/contract/checklist-adjudication.md` append one section per
attempt and never rewrite an earlier attempt's sections; the lifecycle
candidate/handoff attempt streams (`slice-candidate.md`, `slice-handoff.md`)
append and never rewrite. A next packet therefore never cites attempt-one
aggregate results as current: the regenerated files are the current
attempt's records, an evidence file left unchanged by the rework is named
with an explicit disposition in the manifest, and superseded attempt-one
aggregate results remain recoverable from git history at the rejected
candidate commit.

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
├── __init__.py
├── schema_helpers.py
├── test_attention_request.py
├── test_attention_decision.py
├── test_participant_wake.py
└── test_context_and_receipt.py

evals/v2/contract/
├── attention-request/
│   ├── cases.jsonl
│   └── expected-counts.json
├── attention-decision/
│   ├── cases.jsonl
│   └── expected-counts.json
└── downstream/
    ├── cases.jsonl
    └── expected-counts.json

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
| Contract tests | `tests/v2/contract/test_*.py`, `tests/v2/contract/schema_helpers.py` | US1–US3 |
| Evaluation corpus (run by the tests/v2/contract suite) | `evals/v2/contract/attention-request/`, `evals/v2/contract/attention-decision/`, `evals/v2/contract/downstream/` (each: `cases.jsonl` + per-class `expected-counts.json`) | US1–US3 |
| Evidence | `evidence/v2/contract/attention-request.jsonl`, `evidence/v2/contract/attention-decision.jsonl`, `evidence/v2/contract/downstream.jsonl`, `evidence/v2/contract/README.md`, `evidence/v2/contract/handoff.md`, plus the declared lifecycle records | Cross-cutting |
| Product contract docs | `docs/contracts/nunchi-v2.md` | Cross-cutting |
| Governance-fixture repair (rejection R1) | `tests/test_governance.py` (synthetic activation baseline constructed independently of live slice state; invariant proven by the named live-state regression test in §Post-Rejection Planning Decisions, Decision R1) | Cross-cutting |
| Product implementation | none in this slice | Excluded |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global current contract | `README.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; replace V1 verdict/request wording with accepted I-010A-E and breaking-cutover wording, plus the exact new dual-validator test command and dev/test-only `jsonschema==4.26.0` dependency wording, only in the atomic candidate. |
| V2 contract reference | `docs/contracts/nunchi-v2.md` (created by this slice) | `UPDATE` | T017 / `v2-contract-owner` | Validate interface names/versions, bypass/error separation, the conditional FR-007 legacy-vector rule and closed routing-audit set, the per-record FR-010 stage-to-writer binding, the FR-012 runtime-adapter-only semantic rules, the FR-014 selected-design field inventory and authority-conformance corpus class, links, and examples against both validators. |
| Release/change history | `CHANGELOG.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; add the breaking-change entry naming I-010A-E `@1`, the five exact `schemas/v2/*.schema.json` paths, supersession of the V1 `PASS/ACK/ASK/SPEAK` request/verdict contract with no translation bridge, and the pinned dual-validator command, only in the atomic candidate. |
| Contract stability tiers | `docs/STABILITY.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; replace the V1 contract stability rows with the five `@1` interface versions and their breaking-cutover status, keeping the classifier-DEFER/margin-DEFER transition described as independently evidence-gated, not schema compatibility. |
| Integration lifecycle | `docs/integration.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; replace V1 request/verdict flow wording with the request → decision (`ok`/`bypass`/`error`) → wake → continuation → receipt lifecycle, including the non-social `preattention-disabled` bypass and the tagged operational ERROR path. |
| Adapter obligations | `docs/adapters.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; replace adapter-facing V1 envelope/verdict wording with I-010A request-construction and I-010E transport-stage receipt obligations, including honest unknown/unavailable capability wording. |
| V1 adapter contract | `docs/contracts/channel-adapter-v1.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; add the exact supersession notice naming I-010A-E `@1` and the atomic no-bridge cutover; the V1 body remains as a superseded historical reference. |
| Selected-design status | `docs/architecture/v2-selected-design.md` | `HANDOFF` | T017 / `v2-contract-owner` | Accepting owner: `v2-integrator`; mark the five contract seams as landed at their exact `schemas/v2/` paths and align the request/decision/wake/receipt diagram labels with the `@1` interface names. |
| Operator installation | `docs/INSTALL.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: install flow and installed artifacts are unchanged; this slice adds schemas, tests, evals, evidence, and one new doc only, and `jsonschema==4.26.0` stays dev/test-only behind the pinned `uv run --offline --with` command, never entering runtime or install dependencies. |
| Agent execution guidance | `AGENTS.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: its test and runtime claims remain true — `python3 -m unittest` stays the green stdlib offline baseline (oracle-dependent cases skip loudly with asserted counts), the runtime stays dependency-free, and its V2-program wording (V1 current until `CUTOVER_VERIFIED`) is unchanged by this additive slice; cutover-time current-state wording is owned by the atomic candidate, not this slice. |
| Claude execution guidance | `CLAUDE.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: its "standard-library runtime core" and `python3 -m unittest` claims remain accurate because `jsonschema==4.26.0` is dev/test-only behind the pinned offline command and never enters runtime dependencies; grounding sequence, governance commands, and workflow bindings are untouched by this slice. |
| Verdict-suite data model | `docs/contracts/verdict-suite-data-model-v1.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: the V1 verdict-suite data model remains current truth; I-010B embeds the legacy `PASS`/`ACK`/`ASK`/`SPEAK` confidence-vector shape as optional, conditionally required transition evidence (FR-007) without changing any verdict-suite artifact or claim. |
| Verdict-suite requirements | `docs/contracts/verdict-suite-requirements-v1.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: same basis as the verdict-suite data-model row; no verdict-suite requirement changes in this slice. |
| Verdict-suite evaluation | `docs/evaluations/verdict-suite.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: the V1 corpus and its claims are untouched; this slice adds `evals/v2/contract/` beside it without changing verdict-suite behavior. |
| Verdict-suite runner | `docs/evaluations/verdict-suite-runner.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: the runner, its commands, and its outputs are untouched by this slice. |
| Governance execution spine | `docs/governance/execution-spine.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: the candidate diff contains no change under `docs/governance/`, no change to `scripts/check_governance.py` or its checks, and no change to any documented governance command or gate; the rejection-R1 repair touches only the `tests/test_governance.py` fixture's synthetic baseline construction, which this doc does not document, so its claims stay verifiably true against the diff. |
| Hermes core patch | `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: the V1 Hermes integration doc remains current; its V2 migration delta is owned by the harness/adapter slices that change that surface, not by the contract slice. |
| Hermes patch test plan | `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | T017 / `v2-contract-owner` | Rationale: same basis as the Hermes core patch row; no Hermes surface changes in this slice. |

**Inventory derivation**: the reviewed set is exhaustive over `README.md`,
the root guidance documents (`AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`), and
every Markdown file under `docs/**` excluding the dated historical records
under `docs/archive/`. At the 2026-07-18 refresh that inventory is 18 files —
17 pre-existing plus the slice-created `docs/contracts/nunchi-v2.md`, which
now exists in the worktree from the prior attempts' authorized
implementation — matching the 18 rows above one-to-one; a reviewer can
re-derive it with
`ls *.md` plus `find docs -name '*.md' | grep -v archive` and verify no
ordinary document is silently omitted.

`HANDOFF` preserves slice 110's ownership of global current-state wording; it
is not a no-impact finding. Documents under `docs/archive/` are dated
historical records outside the freshness surface and receive no row. Every
`NO_IMPACT` row above must be re-verified against the exact candidate diff and
recorded with its reviewed path and concrete rationale in
`evidence/v2/contract/handoff.md`; the table entry alone is not evidence. The
exact candidate cannot hand off until every row's validation or delta is
recorded in ordinary handoff evidence.

## Owner Handoff

`v2-contract-owner` must hand off the exact commit, five interface versions and
paths, Draft/runtime validator results over the same corpus, exact offline
command, scene-to-record evidence manifest, staged-receipt writer map,
rejected-case inventory, migration/provenance notes, documentation
dispositions/validation/reviewer, and known limitations (T019's enumeration
is authoritative).
Per SC-005 the packet distinguishes and names the candidate commit and the
handoff packet commit as distinct terms, with the full offline baseline
`python3 -m unittest` green from each of the two commits independently, and
commit identity is single-valued: the lifecycle candidate entry, the handoff
attempt entry, the packet input in `evidence/v2/contract/handoff.md`, and the
recorded corpus revision name the identical exact candidate commit, with the
actual handoff packet commit recorded in the same terms once it exists; a
placeholder or divergent identity in a delivered packet blocks acceptance
(R5). The task graph's execution-status wording must agree with the slice
declarations and lifecycle evidence at the packet commit by stating status by
reference, never as a hard-coded state-specific claim (R6).
Acceptance by a dependent owner does not transfer schema ownership.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.

## Post-Acceptance Amendment A3 Plan — I-010F Privileged Action Authorization

This section is the only A3 planning delta. It supplements the accepted slice
without reopening or re-planning its terminal delivery. The slice remains
`ACCEPTED`; `I-010A` through `I-010E`, completed tasks T001–T049,
`slice-activation.md`, `slice-candidate.md`, `slice-handoff.md`,
`slice-acceptance.md`, amendment A1, amendment A2, and the accepted-amendment
ledger remain immutable. No product artifact is created during planning.

### Amendment binding and technical context

| Binding fact | Fixed A3 value |
|---|---|
| Amendment | `A3` |
| Stable owner lane | `v2-contract-owner` |
| Current assigned participant / source | Codex — `evidence/governance/assignments/codex-v2-contract-owner-2026-07-23.md` |
| Interface delta | `I-010F PrivilegedActionAuthorizationV2 @0 -> @1` |
| Prior effective commit | `26a6b531fa146ba1f1f5fcd1c4d191041b141301` |
| Prior effective packet | `evidence/v2/contract/amendment-A2-decision-margin-boundary.md` |
| Delivery branch/worktree | `v2/contract-a3` in `.worktrees/v2-contract-a3/`; the later bound delivery run records its exact clean starting commit |
| Runtime constraint | Python 3.11+ standard library; no new runtime dependency |
| Portable contract | JSON Schema Draft 2020-12 at one exact ordinary path |
| Validation | Explicit stdlib validator plus dev/test-only `jsonschema==4.26.0`, using the same committed corpus |
| Lifecycle result | Amendment `HANDOFF_READY` only; `v2-integrator` separately accepts or rejects the exact candidate and packet |

The candidate and its recorded clean starting commit must both descend from the
prior effective commit. The candidate diff from that starting commit must stay
inside the fixed amendment scope below. Acceptance alone may append one A3
entry to `evidence/v2/contract/slice-amendments.md`; the delivering owner does
not edit that ledger, self-accept the amendment, or change the terminal slice
state.

### Research decisions

- **Decision — one closed authorization union**: `I-010F@1` is one closed
  tagged union covering the host-facing authorization request, immutable
  decision, host-only approval challenge, and authenticated approval
  completion facts. **Rationale**: one portable seam must correlate the exact
  proposal with every later decision while keeping policy and approval
  authority outside the participant and room. **Alternatives considered**:
  unrelated request and decision documents without an exact correlation
  binding — rejected because they permit cross-action substitution.
- **Decision — canonical digest object**: the exact proposed operation is
  represented by a closed digest object containing algorithm `sha256`, a
  64-character lowercase hexadecimal value, and a non-empty
  canonicalization-profile ID. The operation bytes remain host-only.
  **Rationale**: the digest is useless across hosts unless the byte
  canonicalization is explicit. **Alternatives considered**: a bare hash
  string or embedding the operation — rejected for ambiguity and secret or
  payload leakage.
- **Decision — requester is derived, never asserted by room input**: the
  proposal carries the exact origin event and scope; the guard-facing decision
  carries the requester derived from trusted observations. A participant- or
  room-supplied requester identity never validates as authorization evidence.
  **Rationale**: transport provenance, not names, roles, mentions, replies,
  quotes, or model claims, establishes the requester. **Alternatives
  considered**: accepting a requester field from the proposed action —
  rejected as an authority-confusion path.
- **Decision — no bearer allow**: `ALLOW`, `DENY`, and `APPROVAL_REQUIRED` are
  immutable digest-bound decisions, not reusable tokens. An allow is usable
  only by the host for its exact action ID, digest, requester, participant,
  origin, capability, scope, policy provenance, and validity interval, and is
  consumed at the first effect-commit point. **Rationale**: a copied decision
  must never authorize another action. **Alternatives considered**: a reusable
  capability or approval token exposed to the participant — rejected by the
  selected security boundary.
- **Decision — approval remains host-only and authenticated**:
  `APPROVAL_REQUIRED` binds a bounded, expiring challenge to the exact action,
  approver set, and policy. Approval completion records an authenticated exact
  approver and requires a fresh policy, revocation, expiry, scope, and digest
  recheck before a new one-use allow. **Rationale**: ordinary room text,
  reactions, quotes, copied challenges, and model assertions cannot approve an
  effect. **Alternatives considered**: treating conversational approval as
  authority — rejected.

No `NEEDS CLARIFICATION` remains for A3.

### Entity, state, and validation plan

The portable schema plans these closed entities without embedding an operation,
credential, policy file, approval secret, or room authorization roster:

- **Authorization request**: unique action ID; participant ID; exact origin
  event ID; capability; platform, room, continuity-scope, participant, and
  resource scope; the canonical digest object; and non-secret correlation
  metadata.
- **Derived requester**: exact transport-attested actor ID plus the trusted
  origin-event and scope binding used to derive it.
- **Authorization decision**: action and decision IDs; the same exact digest
  and binding; derived requester; `ALLOW`, `DENY`, or
  `APPROVAL_REQUIRED`; a closed reason code; trusted policy provenance;
  evaluation time; expiry/revocation facts; and the authorization path
  (`direct-policy` or `authenticated-approval`) where applicable.
- **Approval challenge and completion**: host-only challenge reference,
  exact bound action/digest/requester/capability/scope, exact approver set,
  expiry, authenticated approver attestation, and recheck outcome. These facts
  remain off the participant and classifier surfaces.

The only authorization motion is proposal to `ALLOW`, `DENY`, or
`APPROVAL_REQUIRED`; an authenticated approval completion may yield a new
digest-identical `ALLOW` after recheck, otherwise it yields `DENY`.
Expiry, revocation, restart, cancellation before effect commit, replay,
capacity exhaustion, unknown persistence, or any binding mismatch yields zero
execution. The schema proves document shape; deterministic semantic tests
prove correlation, binding, transition, replay, and one-use rules at this
contract boundary. Slice `040` later owns the executing guard and coordinator.

The dual-validator corpus must include valid direct allow, deny, approval
required, and authenticated-approval completion records plus adversarial cases
for forged requester identity, alias/role/mention/quote authority, room or
cross-room policy text, missing or malformed digest fields, unknown
canonicalization profile, action/digest/capability/scope/origin substitution,
expired or revoked policy, copied/ordinary-text approval, wrong approver,
challenge replay, decision replay, cross-participant reuse, and unexpected
fields. Runtime-only sequences must prove an allow cannot be reused and an
approval completion cannot authorize changed bytes.

### Fixed amendment scope

The A3 record's `Fixed scope paths` must contain the following exact managed
planning paths and ordinary paths. The managed paths remain control plane only:
this planning step appends only `plan.md`; the later tasks step may append only
the A3 task delta to `tasks.md`; and no product artifact may be created under
`specs/`.

| Artifact | Exact path |
|---|---|
| Existing A3 requirements/clarification section | `specs/010-v2-contract/spec.md` |
| This labelled A3 plan section | `specs/010-v2-contract/plan.md` |
| Append-only A3 task delta | `specs/010-v2-contract/tasks.md` |
| Portable schema | `schemas/v2/privileged-action-authorization.schema.json` |
| Shared stdlib contract adapter and corpus runner | `tests/v2/contract/schema_helpers.py` |
| Focused deterministic tests | `tests/v2/contract/test_privileged_action_authorization.py` |
| Reusable adversarial corpus | `evals/v2/contract/privileged-action-authorization/cases.jsonl` |
| Authoritative corpus counts | `evals/v2/contract/privileged-action-authorization/expected-counts.json` |
| Regenerated S18 contract evidence | `evidence/v2/contract/privileged-action-authorization.jsonl` |
| Regenerated contract evidence manifest | `evidence/v2/contract/README.md` |
| Single append-only A3 initialization/candidate/handoff/decision packet | `evidence/v2/contract/amendment-A3-privileged-action-authorization.md` |
| Portable contract reference | `docs/contracts/nunchi-v2.md` |
| Operator and integrator security guide | `docs/security/privileged-action-authorization.md` |

The accepted-amendment record is initialized before implementation with its
constitutionally required metadata, exact task IDs/hash, this exact fixed
scope, analysis result, branch, and worktree. Candidate, verification,
evidence, documentation, limitations, and `HANDOFF_READY` facts append to that
same record. The terminal candidate and handoff streams and the A1/A2 records
are not A3 packet targets.

### Planned amendment task manifest

The next bound `speckit.tasks` step appends exactly these unchecked tasks after
completed T049, without editing completed task history:

| Planned ID | A3 task |
|---|---|
| T050 | Verify the current owner assignment, exact predecessor/packet, clean descendant starting commit, zero-blocker analysis, immutable terminal/A1/A2 hashes, and initialize the full A3 amendment record with the final normalized A3 task hash before implementation. |
| T051 | Define the closed `I-010F@1` schema and extend the stdlib validator for exact digest, origin/requester, capability/scope/policy, expiry/revocation, decision, and host-only approval bindings. |
| T052 | Add the exact focused test and corpus files, including dual-validator conformance and deterministic adversarial correlation, replay, approval, and one-use cases. |
| T053 | Run and regenerate the S18 contract evidence and manifest at the exact candidate tree, with stable case IDs, validator identities, expected/observed results, and per-class counts. |
| T054 | Update the two owner-controlled docs, validate their schema/examples/commands, and record every file-by-file `UPDATE`, `NO_IMPACT`, and `HANDOFF` result in the A3 packet. |
| T055 | Run the focused dual-validator command, full offline baseline, governance/CLI checks, eval discovery, boundary/immutability/diff checks, freeze the exact candidate, and append the candidate plus amendment `HANDOFF_READY` packet for separate integrator review. |

The normalized digest cannot be written truthfully until `speckit.tasks`
materializes this delta. That step must pin the exact T050–T055 manifest and
write its normalized SHA256 into the A3 record before T051 begins; later task
mutation requires a fresh bound amendment run.

### Acceptance scene, evidence, and commands

| Scene | Required A3 contract observation | Ordinary evidence target |
|---|---|---|
| `S18` Provenance-bound privileged action | Exact transport-derived requester, origin, participant, capability, scope, policy, expiry/revocation, digest, and authenticated approval stay correlated; room/model assertions, copied approval, replay, substitution, or unknown persistence never validate an allow for execution. | `evidence/v2/contract/privileged-action-authorization.jsonl` and `evidence/v2/contract/README.md` |

The later delivery records exact results for:

```sh
uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
python3 -m unittest
python3 scripts/check_governance.py --check-cli
python3 -m evals.verdict_suite.runner --list
git diff --check
```

It also records a focused standard-library test command for
`tests.v2.contract.test_privileged_action_authorization`, verifies the control
plane contains no product artifact, verifies the candidate diff is contained
by the fixed scope, and proves the terminal lifecycle files plus accepted A1/A2
records are byte-for-byte unchanged.

### A3 README/docs impact matrix

This matrix is exact over `README.md`, the root guidance/change documents,
the new A3 security guide, and every current non-archived Markdown file under
`docs/`. Each path has one disposition; no row names a directory or wildcard.

| Exact path | Disposition | Owner / accepting owner | Validation, rationale, or exact handoff delta |
|---|---|---|---|
| `AGENTS.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | Rationale: the repository guidance already defines accepted-amendment mode, A3's complete record schema, control-plane separation, and lifecycle ownership; A3 changes no execution rule or product claim in this file. |
| `CHANGELOG.md` | `HANDOFF` | T054 / `v2-contract-owner`; accepts: `v2-integrator` | After A3 acceptance, add one unreleased entry naming I-010F@1, its exact schema path, effective commit, and packet; state that this is an accepted contract prerequisite, not current V2 runtime behavior, cutover, release, or promotion. |
| `CLAUDE.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | Rationale: A3 follows the existing direct in-wrapper skill-dispatch, accepted-amendment, stdlib runtime, and bound-workflow rules; its candidate requires no further Claude execution-guidance change. |
| `README.md` | `HANDOFF` | T054 / `v2-contract-owner`; accepts: `v2-integrator` | After A3 acceptance, replace only the audited-baseline claim that I-010F is missing with the exact accepted A3 effective commit and packet; retain V1 as current, retain downstream lifecycle truth, and do not imply cutover, release, or promotion. |
| `docs/INSTALL.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | A3 adds no runtime dependency, package, install step, configuration key, or executable surface; `jsonschema==4.26.0` remains dev/test-only in the existing offline validation command. |
| `docs/STABILITY.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | This document describes the current V1 public surface. A3 is an unintegrated V2 contract amendment and changes no current stability promise or package interface. |
| `docs/adapters.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | No adapter implements I-010F in slice 010. Adapter-specific privileged-action enforcement remains owned by slices 040 and 060–110 after they accept the exact A3 packet. |
| `docs/architecture/v2-selected-design.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | The selected design already fixes the action/origin/capability/scope/digest, transport-derived requester, policy recheck, approval, replay, and no-bearer boundary; A3 implements that authority without changing it. |
| `docs/contracts/channel-adapter-v1.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | The historical/current V1 adapter contract remains unchanged; A3 adds no bridge and no adapter runtime behavior. |
| `docs/contracts/nunchi-v2.md` | `UPDATE` | T054 / `v2-contract-owner` | Add I-010F@1 at its exact schema path; replace the planned-completion placeholder with lifecycle-truthful A3 candidate/acceptance wording; document every union member, digest profile, host-only field, semantic rule, adversarial class, version, and runnable dual-validator command; validate links and examples against both validators. |
| `docs/contracts/verdict-suite-data-model-v1.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | I-010F carries no V1 verdict-suite envelope, verdict, confidence, fixture, or runner field. |
| `docs/contracts/verdict-suite-requirements-v1.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | A3 neither changes the V1 verdict-suite requirements nor uses that suite as authorization evidence. |
| `docs/evaluations/verdict-suite-runner.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | The existing V1 verdict runner, inputs, commands, and outputs are untouched; A3 uses the separate contract corpus runner. |
| `docs/evaluations/verdict-suite.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | The social-verdict corpus and evidence claims remain unchanged and cannot establish privileged-action authority. |
| `docs/governance/execution-spine.md` | `HANDOFF` | T054 / `v2-contract-owner`; accepts: `v2-program-owner` | After integrator acceptance and the A3 ledger append, replace the statement that A3 is the next missing amendment with the exact accepted effective commit/packet and retain the rule that each downstream owner must separately accept that binding. |
| `docs/integration.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | A3 defines a portable contract only; the current V1 integration commands and behavior remain truthful until later component delivery and atomic cutover. |
| `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | The Hermes V1 patch test plan has no I-010F consumer; Hermes authorization integration and proof belong to its later bound slice. |
| `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | The Hermes V1 patch description remains current and receives no partial V2 authorization claim. |
| `docs/security/privileged-action-authorization.md` | `UPDATE` | T054 / `v2-contract-owner` | Create the exact contract-level trust-boundary guide: protected assets, trusted inputs, host-only data, digest canonicalization, decision/approval state, safe defaults, replay/expiry/revocation behavior, unsupported third-party bypasses, examples, limitations, and focused validation commands. |
| `docs/v2-completion-goal.md` | `NO_IMPACT` | T054 / `v2-contract-owner` | The completion goal already requires the exact provenance, scope, policy, digest, authenticated approval, one-use, restart, and effect-commit properties; A3 supplies one prerequisite contract without weakening or declaring the goal complete. |

Every `NO_IMPACT` rationale must be rechecked against the exact A3 candidate
diff and copied into the ordinary A3 packet. `HANDOFF` is valid only after the
named accepting owner records the exact claim delta at the correct lifecycle
boundary; it is not evidence that the target already changed. Documentation
freshness cannot pass until both `UPDATE` files and every row's validation or
handoff delta are recorded against the exact candidate.

### Limitations and downstream compatibility

- A3 defines and validates the portable contract only. It does not implement
  slice 040's privileged-action guard, load policy, authenticate an operator
  surface, retain pending proposals, execute an effect, or make an arbitrary
  third-party tool safe.
- Schema validity alone does not attest a transport event, policy, approval,
  persistence result, or effect. The stdlib semantic validator proves only the
  contract-bound deterministic rules for supplied trusted facts; runtime and
  live provenance remain downstream obligations.
- I-010A through I-010E remain byte-for-byte and version-identical. A future
  digest algorithm or incompatible canonicalization change requires another
  explicit versioned amendment.
- At amendment `HANDOFF_READY`, A2 remains the effective dependency. Rejection
  preserves A2 and requires a fresh bound run. Only integrator acceptance plus
  one chained ledger entry establishes I-010F@1 as effective.
- After acceptance, every slice `020`–`110` must independently accept the same
  exact A3 commit and packet before its readiness gate. Any already activated
  consumer would have to stop using its candidate until exact-successor
  compatibility is re-attested; current declarations leave those slices
  `PLANNED`.
- A3 does not make V2 current, complete, integrated, cut over, verified,
  released, or promoted.

### Planning gate status

The semantic constitution gates below pass, but the current mechanical
governance gate is **BLOCKED**. `scripts/check_governance.py` derives the
historical activation's `Interfaces` and `Acceptance scenes` sets by scanning
the entire current plan. It therefore requires immutable
`evidence/v2/contract/slice-activation.md` to be rewritten with A3's new
interface and S18 scene, contrary to accepted-amendment mode. The observed
errors are:

- activation interfaces must enumerate A3's new interface from the bound plan;
- activation scenes must enumerate S18 from the bound plan.

Do not rewrite the activation or hide the amendment identifiers to satisfy
that check. Before A3 delivery can start, the governance validator needs a
separately authorized amendment-aware rule that compares terminal activation
only with the terminal plan scope and validates the A3 interface/scene against
the append-only A3 record and task delta.

### Amendment constitution re-check

| Gate | A3 result |
|---|---|
| Selected product boundary | PASS — authorization remains deterministic execution safety and never becomes social attention judgment. |
| Truthful identity and authority | PASS — requester derives from the exact trusted origin event; aliases, room text, model claims, and copied approvals carry no authority. |
| Atomic contract parity | PASS — one versioned ordinary-path seam is planned for every later consumer; no V1 bridge or local consumer fork is permitted. |
| Evidence before claims | PASS — exact schema, tests, corpus, evidence, docs, commands, and limitations are planned without claiming implementation or acceptance. |
| Control-plane boundary | PASS — only this existing `plan.md` changes during planning; all product and evidence artifacts are future exact ordinary paths. |
| Single-owner lifecycle | PASS — the stable owner lane delivers only A3 to `HANDOFF_READY`; the separate integrator decision and ledger append are not fabricated. |
| Documentation freshness | PASS — `README.md`, both affected owner-controlled documents, and every current ordinary doc receive one exact file-level disposition. |
| Mechanical governance closure | BLOCKED — the checker conflates the appended amendment scope with immutable terminal activation metadata. |

Post-design re-check: BLOCKED on the amendment-aware governance defect above.
The A3 plan introduces no constitution exception and no unresolved
clarification.
