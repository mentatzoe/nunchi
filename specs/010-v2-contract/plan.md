# Implementation Plan: V2 Contract

**Branch**: `v2/contract` | **Date**: 2026-07-11 (corpus-path and documentation-matrix refresh 2026-07-17; post-rejection R1/R2/R3 alignment to the clarified spec, same day; post-rejection R4/R5/R6 selected-design-fidelity alignment 2026-07-18) | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/010-v2-contract/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-contract-owner`

**Assigned participant / source**: cc-session-1 — evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md

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
- `I-010B AttentionDecisionV2@1` at
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
- `I-010E AttentionReceiptV2@1` at
  `schemas/v2/attention-receipt.schema.json`, an immutable staged-record union
  for `observation`, `attention`, `participant-host`, and `transport`, correlated
  by request ID. Each stage owner appends only its stage, and the
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
