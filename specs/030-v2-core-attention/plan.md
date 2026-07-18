# Implementation Plan: V2 Core Attention

**Branch**: `v2/core-attention` | **Date**: 2026-07-18 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/030-v2-core-attention/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-core-owner`

**Assigned participant / source**: codex-session-1 — evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/030-v2-core-attention`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/attention/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts
and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/attention/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/attention/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/attention/slice-acceptance.md` (for
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

During authorized slice implementation, stage one participant-shaped V2
attention engine in the owned core and CLI seams without changing current V1
exports or behavior. It validates I-010A, emits I-010B and
immutable I-010E attention stages, governs suppression, preserves separately
auditable classifier- and margin-DEFER valves, returns trusted preattention-
disabled bypass without a model call, and keeps operational failure separate
with wake as the shared default. The exact handoff feeds 040 and later surface
slices; 110 alone owns atomic integration. This planning baseline creates no
product behavior.

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

**Performance Goals**: one logical model judgment per request; zero to two
trusted retries (at most three identical transport attempts); ordinary evidence
reports latency and serialized/token context cost without adding fields to the
closed I-010E attention-stage body. These metrics are descriptive/non-gating:
every record names elapsed time, serialized request/response bytes, provider-
reported input/output tokens or `unavailable`, attempt count, provider/model,
runtime, host/OS, and fixture/corpus identity; no local latency or token
threshold is claimed

**Constraints**: no V1 bridge or translation, no partial V2 publication,
deterministic social rule, hidden fallback, reply prose, request-controlled
operator policy, or send-time judgment

**Scale/Scope**: one engine interface, one CLI seam, one shared transition
policy, and one evidence-backed prompt/model configuration

## Planning Decisions

No open clarification items remain. The selected Vault design, accepted
I-010A/B/E contracts, constitution, and current ordinary-path V1 seams resolve
the slice's implementation choices without reopening product decisions.

### Green pre-cutover staging in the existing core and CLI seams

- **Decision**: Add non-current `evaluate_v2` and `attention-v2` entry points in
  `src/nunchi/core.py` and `src/nunchi/cli.py`, and add their V2-only support in
  `src/nunchi/classifiers.py`, `src/nunchi/models.py`, and
  `src/nunchi/schema.py` on the isolated slice branch. Keep current public
  `nunchi.evaluate`, `nunchi admit`, V1 internals, and the complete V1 baseline
  unchanged. Neither staging entry point may call or translate through V1. The
  owner packet gives slice 110 an exact deletion/publication delta that removes
  V1 and the temporary staging names while publishing I-030A atomically.
- **Rationale**: Program planning requires lane branches to be independently
  green while main remains V1 and slice 110 alone performs assembly/cutover.
  Additive, unreachable-from-current-runtime staging makes I-030A testable by
  downstream lanes without a compatibility bridge or a partially migrated
  public surface.
- **Alternatives considered**: Replacing V1 in place in slice 030 makes the
  mandated full baseline fail; changing current exports early makes V2 appear
  current; a V1-to-V2 adapter violates the selected boundary; a separate V2
  package conflicts with the program's owned `core.py`/`cli.py` interface paths.

### Contract authority and runtime validation

- **Decision**: Consume the accepted I-010A, I-010B, and I-010E schemas without
  editing them; add stdlib runtime validation and audit behavior only in the
  030-owned source seams.
- **Rationale**: Slice 010 owns the public contract, while slice 030 owns
  executable conformance and the I-030A core/CLI process behavior.
- **Alternatives considered**: Forking schema shapes locally or narrowing
  accepted contract cases in runtime code. Either would invent a competing
  contract and block downstream parity.

### One judgment and the dual-valve transition

- **Decision**: Make one participant-shaped classifier call when preattention
  is enabled, preserve classifier-DEFER and margin-DEFER as separate
  safety-widening routes, and keep margin retirement outside this slice's
  schema-cutover decision.
- **Rationale**: This matches the selected social-judgment boundary and keeps
  the protective margin until replay and downstream live evidence earn its
  retirement.
- **Alternatives considered**: Deterministic semantic suppression, a second
  classifier call, immediate margin removal, or treating DEFER as an error.
  Each contradicts the authority design or increases false-silence risk.

### Trusted recoverability capability

- **Decision**: I-030A receives recoverability eligibility as an explicit,
  trusted host capability alongside the selected effective attention policy.
  It is neither room-controlled I-010A data nor a classifier-visible field.
- **Rationale**: Recoverability is required before effective suppression, while
  the selected contract keeps host capability and continuation authority out of
  both the room request and classifier projection.
- **Alternatives considered**: Adding recoverability to I-010A, inferring it
  from coverage or aliases, or treating it as social policy. Each would fork the
  accepted contract or let untrusted/conversational data grant suppression.

### I-030A callable and CLI equivalence seam

- **Decision**: Stage the versioned callable
  `evaluate_v2(request, *, policy, recoverability, classifier_config,
  receipt_sink) -> AttentionDecisionV2`. The request is I-010A; the three
  configuration/capability inputs are host-trusted; recoverability is the exact
  `{participant_id, continuity_scope_id, eligible, source}` shape; the required
  host-owned sink is offered the exact I-010E attention-stage record when a
  valid request ID exists; and the return is I-010B. Sink failure is operational
  ERROR with wake default and never a false persistence claim. The exact staged
  command is `nunchi attention-v2 --config PATH`; stdin supplies only I-010A,
  while that one operator-owned JSON file supplies the other inputs. For
  identical normalized inputs, parsed CLI stdout and the callable return are
  field-for-field equal, and any offered attention receipt has the same
  body/writer; framing, diagnostics, and exit code are the only surface
  differences.
- **Runtime input contract**: `policy` is the selected
  `EffectiveAttentionPolicy` inventory and validation in spec FR-001;
  `recoverability` is the exact bound four-field capability there;
  `classifier_config` is its exact seven-field trusted provider configuration;
  and `receipt_sink` is the one-call synchronous `None`/exception protocol.
  Policy and recoverability participants bind exactly to I-010A `self`, and the
  recoverability scope binds exactly to I-010A `room.continuity_scope_id`.
  Callable inputs arrive normalized. The CLI file is the exact closed FR-001
  `{policy, recoverability, classifier_config, receipt_sink}` object; both the
  file and pre-existing receipt directory are opened descriptor-first without
  following symlinks, then verified as effective-user-owned regular file/
  directory with no group/other permission bits. Duplicate JSON keys reject,
  and there is no inline, flag, environment, or request fallback. Its exact
  receipt adapter is `{type: "exclusive-json-file", directory, source}` and
  descriptor-relative no-follow exclusive-creates the request-ID-hash file with
  mode `0600`, writes one canonical JSON line, flushes, file-fsyncs, closes, and
  directory-fsyncs; it never overwrites or retries. Exclusive-create collision
  reports `unknown` without touching the existing file; other pre-create open
  failure reports `not-persisted`. Post-create failure attempts descriptor-
  relative unlink plus directory fsync. Only successful cleanup
  reports `not-persisted`; cleanup or final-directory-fsync uncertainty reports
  `unknown`, and neither outcome claims persistence.
  Missing, duplicate, conflicting, unsafe, malformed, or room-supplied sources
  are configuration errors, never merged by implicit precedence. Credentials,
  configuration paths, and sink details never enter projection, stdout, stderr,
  logs, decisions, or receipts.
- **Rationale**: This closes the inter-component seam without inventing a new
  public schema or allowing room data to choose policy, provider, capability,
  credentials, or receipt ownership.
- **Alternatives considered**: A request-embedded policy, a CLI-only engine,
  returning a tuple outside I-010B, or allowing surface-specific audit fields.
  Each would fork the accepted contract or prevent exact parity.

### Retry and sparse-advice boundaries

- **Decision**: Require trusted `max_retries` explicitly and accept only `0..2`
  with no callable or CLI default;
  retry connection failures, timeout, `429`, and `5xx` with the identical
  payload/logical request ID, never other `4xx`, validation/configuration,
  malformed model output, or an already-complete model judgment. Exhaustion is
  operational ERROR. Prompt for at most two WAKE annotations of at most 240
  Unicode scalar values; require 100% deterministic/three-family adherence, but
  do not reject or truncate an otherwise I-010B-valid result solely for length
  or item count.
- **Rationale**: The retry limit makes “one logical judgment” reproducible;
  prompt/evidence enforcement preserves brief framing without locally narrowing
  the accepted I-010B schema.
- **Alternatives considered**: Unbounded/operator-arbitrary retry counts,
  retrying invalid output, a second-vote retry, or a local advice schema cap.
  These undermine bounded cost, single judgment, or contract ownership.

### Finite transition and social-evidence gates

- **Decision**: Exercise the exact 36-row transition domain in spec SC-002.
  Validate active-margin candidate-suppression evidence before routing. For a
  valid candidate `SUPPRESS`, apply exactly this first-match precedence:
  suppression disabled, recoverability unproven, active-margin uncertainty,
  then no valve. Candidate `WAKE` always uses `none`; classifier `DEFER` always
  uses `classifier-defer`. Each row freezes status, pair, margin status, valve,
  and override-cause oracles.
  Treat the required three-family social rates as descriptive/non-gating for
  030; missing runs/provenance, advice-criterion failure, or unsafe mechanical
  routing blocks handoff, while mistaken/missed suppression, wake-volume, and
  family-disagreement rates remain explicit limitations and cannot retire the
  margin.
- **Rationale**: A finite mechanics denominator supports a real zero-unsafe-row
  claim without pretending that a small stochastic sample proves social
  correctness.
- **Alternatives considered**: An open-ended “full” matrix, local stochastic
  pass thresholds, or treating mere execution as proof. Each is unreviewable or
  overclaims evidence.

### Advice evidence rubric

- **Decision**: Count/length and citation resolution are deterministic. For
  every WAKE advice item, `v2-core-owner` records the note, citations, Unicode
  scalar count, and binary findings for supplied-event grounding,
  attention-relevance explanation, absence of a proposed reply/first-person
  draft, and absence of an imperative telling the participant what to say or
  do. Handoff requires every field to pass across deterministic and required
  three-family records; the semantic fields are explicit owner adjudication,
  not runtime social rules.
- **Rationale**: This makes the evidence gate reproducible without narrowing
  I-010B or turning deterministic validation into a conversational judge.
- **Alternatives considered**: An undefined “brief” review, model self-grading,
  or runtime rejection based on semantic prose. None supplies an auditable
  owner decision within the accepted contract boundary.

### Receipt and performance evidence boundary

- **Decision**: Emit only the accepted closed I-010E attention-stage bodies.
  Record latency and serialized/token-cost measurements in the exact ordinary
  evaluation evidence targets, correlated by request ID where applicable, and
  never as undeclared I-010E fields.
- **Rationale**: Slice 030 must prove performance without forking the accepted
  receipt schema or weakening its `additionalProperties: false` boundary.
- **Alternatives considered**: Adding local receipt fields, hiding metrics in
  error detail, or omitting performance measurements. The first two violate the
  contract; the last would leave the performance goal unproven.

### Blocking accepted-contract mismatch

- **Decision**: Do not activate or implement while accepted I-010E lacks fields
  for the selected design's effective-policy source on ordinary/error outcomes
  and separately receipted `NO_WAKE` operational-failure policy. Return that
  incompatibility to `v2-contract-owner` for a versioned accepted resolution;
  then rerun this consumer's dependency acceptance and zero-blocker analysis.
  The later discovery is durably recorded without rewriting the earlier
  acceptance at
  `evidence/v2/attention/dependency-010-post-acceptance-blocker.md`.
- **Rationale**: I-010E's classifier and error bodies are closed. Local fields,
  an `error.detail` encoding convention, or misuse of classifier/margin fields
  would violate both the selected design and 010 ownership.
- **Alternatives considered**: Treating the accepted packet as sufficient,
  omitting the required provenance, or hiding it in free text. Each creates an
  implementation that cannot conform to the higher-authority selected design.

### Bypass, operational error, and CLI parity

- **Decision**: Return trusted preattention-disabled bypass with zero classifier
  calls, keep operational error as its own tagged branch, and expose the exact
  0/1/2/3 CLI process contract recorded below.
- **Rationale**: Bypass must not fabricate a model result, errors must not
  impersonate social judgments, and callable-core/CLI equivalence is the shared
  consumer seam.
- **Alternatives considered**: Converting bypass to WAKE, converting failures
  to a social disposition, or emitting diagnostics and response payloads on the
  same stream. These lose provenance or break deterministic host handling.

### Documentation ownership

- **Decision**: Update the 030-owned attention and evaluation references, record
  evidence-backed no-impact findings for exact unaffected files, and route one
  exact claim delta per shared or downstream-owned file.
- **Rationale**: Component truth can land with the slice while global current
  state remains integrator-owned until atomic cutover.
- **Alternatives considered**: Grouped path dispositions, generic directory
  review, premature global V2-current wording, or silent deferral. Each fails
  the documentation-freshness gate.

## Constitution Check

| Gate | Status | Planning evidence |
|---|---|---|
| Selected V2 boundary | PASS | Engine decides wake attention only and never composes a participant move. |
| Human-shaped judgment | PASS | One sparse participant-shaped model judgment owns every social suppression. |
| Truthful identity/observation | PASS | I-010A facts and unknowns are consumed without inventing roster or handled state. |
| Attention/contribution split | PASS | Engine returns attention; 040 and surface slices own normal participant turns. |
| Atomic parity contract | PASS | Non-current `evaluate_v2`/`attention-v2` stage I-030A without calling V1; the complete V1 baseline stays green, and 110 alone removes V1 and staging names while publishing I-030A in one atomic candidate. |
| Evidence before claims | PASS | Mechanics, replay, multi-model, canary, and margin evidence targets are separate. |
| Control-plane boundary | PASS | This directory contains planning Markdown only. |
| Single owner and slice lifecycle | PASS | `v2-core-owner` owns I-030A; tasks remain `DORMANT` while the slice is `PLANNED`. |
| Accepted receipt compatibility | BLOCKED | Accepted I-010E cannot represent selected effective-policy source and separately receipted `NO_WAKE`; versioned 010-owned resolution is required before READY. |

Post-design re-check: BLOCKED only on the accepted receipt incompatibility
above; the independently green staging strategy and exact CLI configuration/
sink surface resolve the local analysis findings. No `data-model.md`, local contract,
quickstart, schema, test, corpus, evidence, or product documentation is created
here.

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
participant-shaped classifier result or trusted bypass → trusted host
recoverability capability plus governed dual-valve route → tagged error and
immutable attention-stage receipt → replay/multi-model evidence plus
downstream canary protocol → downstream handoff.
Slice 020 runs in parallel; 040 begins only after both handoffs.

**Worktree/branch**: isolated worktree `.worktrees/v2-core-attention/` on branch
`v2/core-attention`

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
| JSON parsed; config missing/unreadable/unsafe/malformed, sink construction fails, or request schema invalid | Exactly one tagged `status: error` JSON value with honest receipt-persistence fact | No response payload | `3` |
| Provider/runtime/malformed-model or constructed-sink invocation failure | Exactly one tagged `status: error` JSON value with `not-persisted` or `unknown` when applicable | No response payload | `1` |
| Input unreadable or invalid JSON | Empty | Diagnostic only | `2` |

Precedence is fixed: unreadable/invalid stdin JSON wins and exits 2 without
loading config; after any JSON value is parsed, config security/shape and sink
construction precede request-schema validation, so config failure wins a
combined failure and exits 3. A valid sink records a schema/config error only
when a valid request ID is assignable; for a config error its `receipt_sink`
member must independently pass the closed security/shape checks. Otherwise no
receipt or ID is fabricated.

Core and CLI must also prove that host-only continuation handles, binding
tokens, cursors, and expiry values never enter the classifier projection. The
model may see factual coverage and expansion-availability booleans only; the
original bound I-010A continuation capability remains available downstream to
040. I-030A does not consume I-010D fetch request/page objects.

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

### Ordinary repository targets for authorized slice implementation

```text
src/nunchi/
├── core.py
├── cli.py
├── classifiers.py
├── models.py
└── schema.py

tests/v2/attention/
├── __init__.py
├── helpers.py
├── test_advice_and_errors.py
├── test_core_cli_contract.py
└── test_transition_policy.py

evals/v2/attention/
├── runner.py
├── core-cli/cases.jsonl
├── defer-transition/analyze.py
├── governed-suppression/cases.jsonl
└── suppression-scars/cases.jsonl

evidence/v2/attention/
├── README.md
├── core-cli-parity.jsonl
├── defer-canary/protocol.md
├── handoff.md
├── model-comparison/results.jsonl
├── s04-suppression-scars/results.jsonl
├── s05-governed-suppress.jsonl
├── s08-defer-transition/results.jsonl
└── verification.md

docs/attention/v2.md
```

**Structure Decision**: Evolve the current shared core/CLI seams on an isolated
slice branch. Do not introduce an alternate V2 executable or compatibility
layer that could survive the atomic cutover.

## Ordinary Repository Targets

| Artifact class | Exact ordinary target path | Owning task/story |
|---|---|---|
| Attention orchestration | `src/nunchi/core.py` | T007, T012, T020 / US1–US3 |
| Classifier/provider/prompt | `src/nunchi/classifiers.py` | T006 / US1 |
| Runtime models and audit | `src/nunchi/models.py` | T008, T013 / US1–US2 |
| Runtime validation/policy | `src/nunchi/schema.py` | T011, T018 / US2–US3 |
| CLI process seam | `src/nunchi/cli.py` | T019 / US3 |
| Test package and helpers | `tests/v2/attention/__init__.py`, `tests/v2/attention/helpers.py` | T001 |
| Core/CLI contract tests | `tests/v2/attention/test_core_cli_contract.py` | T002 / US3 |
| Transition-policy tests | `tests/v2/attention/test_transition_policy.py` | T003 / US2 |
| Advice/bypass/error/projection tests | `tests/v2/attention/test_advice_and_errors.py` | T004 / US1–US3 |
| Replay runner | `evals/v2/attention/runner.py` | T005 / US1–US3 |
| Suppression-scar corpus | `evals/v2/attention/suppression-scars/cases.jsonl` | T009 / US1 |
| Governed-suppression corpus | `evals/v2/attention/governed-suppression/cases.jsonl` | T014 / US2 |
| DEFER analysis | `evals/v2/attention/defer-transition/analyze.py` | T015 / US2 |
| Core/CLI corpus | `evals/v2/attention/core-cli/cases.jsonl` | T021 / US3 |
| S04/S16 results | `evidence/v2/attention/s04-suppression-scars/results.jsonl` | T010 / US1 |
| S05 results | `evidence/v2/attention/s05-governed-suppress.jsonl` | T016 / US2 |
| S08 results | `evidence/v2/attention/s08-defer-transition/results.jsonl` | T017 / US2 |
| S06/S09/030-CLI parity results | `evidence/v2/attention/core-cli-parity.jsonl` | T022 / US3 |
| Three-family comparison | `evidence/v2/attention/model-comparison/results.jsonl` | T023 / cross-cutting |
| Downstream canary protocol | `evidence/v2/attention/defer-canary/protocol.md` | T024 / cross-cutting |
| Handoff packet input | `evidence/v2/attention/handoff.md` | T025–T026 / cross-cutting |
| Evidence/command manifest | `evidence/v2/attention/README.md` | T026 / cross-cutting |
| Candidate verification record | `evidence/v2/attention/verification.md` | T027 / cross-cutting |
| Attention/operator guide | `docs/attention/v2.md` | T025 / cross-cutting |
| V1 scar data-model reference | `docs/contracts/verdict-suite-data-model-v1.md` | T025 / cross-cutting |
| V1 scar requirements reference | `docs/contracts/verdict-suite-requirements-v1.md` | T025 / cross-cutting |
| V1 evaluation overview | `docs/evaluations/verdict-suite.md` | T025 / cross-cutting |
| V1 evaluation runner guide | `docs/evaluations/verdict-suite-runner.md` | T025 / cross-cutting |
| Consumed I-010A schema | `schemas/v2/attention-request.schema.json` | Read-only 010-owned dependency |
| Consumed I-010B schema | `schemas/v2/attention-decision.schema.json` | Read-only 010-owned dependency |
| Consumed I-010E schema | `schemas/v2/attention-receipt.schema.json` | Read-only 010-owned dependency |

## Candidate Verification Commands

T027 runs this exact baseline against the tested implementation tree and records
that tree's full parent commit in `evidence/v2/attention/verification.md`; any
failure blocks convergence:

```sh
python3 scripts/check_governance.py --check-cli
python3 -m unittest
python3 -m unittest discover -s tests/v2/attention -p 'test_*.py'
python3 -m evals.v2.attention.runner --all
python3 -m evals.verdict_suite.runner --list
git diff --check
```

Activation freezes the starting commit's exact root test/skip counts and the
ordered tracked pre-030 test-file inventory plus content hash outside
`tests/v2/attention/`, and the exact allowed 030 path set. T001's package marker
makes the attention suite visible to root discovery. At tested tree, candidate,
and packet commits, verification rejects any changed pre-030 test byte, adapter/
harness or 010-owned `schemas/v2/` contract edit, deleted or renamed pre-030
test, new skip, out-of-scope
path, or count mismatch. The focused suite must have zero skips, root skips must
equal the frozen activation skip count, and root count must equal the frozen
activation root count plus the focused attention-suite count.

The T027 commit contains that verification record but does not try to name its
own SHA. The later convergence gate designates the T027 commit as the lifecycle
candidate, reruns the same commands at that exact candidate, and records its SHA
and results in `slice-candidate.md` from a later packet commit. The handoff gate
reruns the full baseline at the packet commit and records that distinct packet
commit/results in `slice-handoff.md`; no file is required to name the commit
that contains itself. The three-family live provider attempts remain separately
recorded by T023 and are not hidden inside the deterministic baseline.

## Documentation Impact and Freshness

| Claim surface | Exact reviewed ordinary path | Disposition | Owning task/lane | Validation, rationale, or exact handoff delta |
|---|---|---|---|---|
| Global product and CLI state | `README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at atomic cutover replace V1 verdict/core/CLI claims and examples with accepted I-030A `SUPPRESS`/`WAKE`/`DEFER`, trusted bypass, separate ERROR, dual-valve, and 0/1/2/3 process behavior while preserving verification-pending wording. |
| Release history | `CHANGELOG.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; add the exact accepted 030 commit, breaking core/CLI contract delta, active-margin status, evidence links, and limitations in the atomic cutover entry. |
| Installation and executable claims | `docs/INSTALL.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; replace V1 `nunchi-channel`/configuration assumptions with the accepted V2 CLI, model/policy inputs, installed-runtime provenance, and no-V1-residue instructions at cutover. |
| Public stability contract | `docs/STABILITY.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; replace the V1 request/verdict/process promise with accepted I-010A/B/E plus I-030A, explicitly retaining the active transition margin and breaking-version boundary. |
| Cross-adapter reference | `docs/adapters.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; apply the exact common I-030A lifecycle, bypass/error routes, and dual-DEFER requirements to the cutover-wide adapter table without claiming unproven surface parity. |
| Selected-design diagrams | `docs/architecture/v2-selected-design.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at cutover update I-030A implementation/evidence status and diagram-linked claims from selected target to accepted verification-pending candidate, then to verified current only after post-merge proof. |
| V1 archive index | `docs/archive/v1/README.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the frozen archive index already says its children are historical and not current instructions; record exact review unchanged in `evidence/v2/attention/handoff.md`. |
| Archived V1 classifier contract | `docs/archive/v1/admission-classifier/contract.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner makes the V1 fields and commands archival evidence, not a V2 integration claim; record the review in handoff evidence. |
| Archived V1 classifier data model | `docs/archive/v1/admission-classifier/data-model.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner remains accurate after 030; record the review in handoff evidence. |
| Archived V1 classifier quickstart | `docs/archive/v1/admission-classifier/quickstart.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the archived-command warning prevents it from acting as current runnable guidance; preserve it unchanged and record the review. |
| Archived V1 core/CLI contract | `docs/archive/v1/core-cli/contract.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner keeps the replaced V1 process contract as evidence; record the review in handoff evidence. |
| Archived V1 core/CLI data model | `docs/archive/v1/core-cli/data-model.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the historical/superseded banner keeps the replaced V1 model as evidence; record the review in handoff evidence. |
| Archived V1 core/CLI quickstart | `docs/archive/v1/core-cli/quickstart.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the archived-command warning already prevents current-use ambiguity; record the review in handoff evidence. |
| Channel-adapter V1 contract | `docs/contracts/channel-adapter-v1.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; at atomic cutover mark the V1 gate/result contract superseded and route readers to the accepted V2 lifecycle and final adapter guidance. |
| Accepted V2 public contracts | `docs/contracts/nunchi-v2.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: slice 010 owns this already-current contract reference; 030 implements it without changing fields or its truthful V1-current caveat. Validate candidate conformance and record the unchanged finding. |
| V1 verdict-suite data model | `docs/contracts/verdict-suite-data-model-v1.md` | `UPDATE` | T025 / `v2-core-owner` | Preserve the V1 evidence schema, add its exact S04/S08 regression/transition role and V2 result links, then validate terminology and links against the candidate. |
| V1 verdict-suite requirements | `docs/contracts/verdict-suite-requirements-v1.md` | `UPDATE` | T025 / `v2-core-owner` | Preserve historical ground truth, map the applicable scars to S04/S16 and dual-valve evidence, and validate requirement/result links. |
| V1 verdict-suite runner guide | `docs/evaluations/verdict-suite-runner.md` | `UPDATE` | T025 / `v2-core-owner` | Keep V1 commands runnable, name their bounded regression role, add exact V2 runner/result commands, and validate every retained/new command. |
| V1 verdict-suite evidence guide | `docs/evaluations/verdict-suite.md` | `UPDATE` | T025 / `v2-core-owner` | Distinguish historical V1 quality evidence from 030 mechanics/social evidence, link exact S04/S05/S08/model-comparison records, and validate claims and links. |
| Governance execution guide | `docs/governance/execution-spine.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: 030 follows but does not change the already-current workflow/lifecycle contract; planning and later component implementation create no new governance rule. Record exact review in handoff evidence. |
| General integration guide | `docs/integration.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-integrator`; replace the V1 verdict, fail-policy, request, output, provider, and CLI wiring with accepted I-030A behavior only in the atomic cutover. |
| Hermes display-patch guide | `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the optional channel-scoped display override controls operational UI chatter, not attention judgment or I-030A; record the exact review unchanged. |
| Hermes display-patch test plan | `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: resolver and gateway-display checks are independent of the core attention contract; record the exact review unchanged. |
| Attention/operator reference | `docs/attention/v2.md` | `UPDATE` | T025 / `v2-core-owner` | Create the exact component guide; validate policy, bypass, error/exit semantics, active margin, prompt/model provenance, examples, links, and commands against the exact candidate without claiming atomic cutover. |
| Claude DEFER evaluation | `integrations/claude-code/DEFER_EVAL.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-claude-owner`; replace V1 uncertain-PASS terminology with the exact classifier-DEFER/margin-DEFER transition, reuse criteria, and downstream canary protocol after accepting I-030A. |
| Claude Code integration | `integrations/claude-code/README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-claude-owner`; migrate the V1 wake gate to I-030A, distinguish bypass/ERROR/DEFER, preserve one judgment and act-or-silence, and update config/evidence claims only with its surface candidate. |
| Claude transport patch | `integrations/claude-code/transport-patch/README.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the allowlisted peer-bot transport patch changes event delivery, not the attention engine contract; exact review remains downstream transport evidence and is recorded unchanged. |
| Codex integration | `integrations/codex/README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-codex-owner`; replace V1 verdict, inbound/outbound re-gate, receipt/config, and wake claims with accepted I-030A bypass/ERROR/dual-DEFER plus direct act-or-silence behavior in the Codex slice. |
| Hermes integration | `integrations/hermes/README.md` | `HANDOFF` | T025 / `v2-core-owner` | Accepting owner: `v2-hermes-owner`; replace V1 `nunchi-channel` verdict/fail-open/config/receipt semantics with accepted I-030A, bypass/ERROR, dual-DEFER, and immutable attention-stage facts in the Hermes slice. |
| Discord MCP design | `integrations/mcp-discord/DESIGN.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: the document correctly keeps the transport gate-neutral and assigns admission harness-side; I-030A changes no transport protocol or ownership. Record exact review unchanged. |
| Discord MCP operator guide | `integrations/mcp-discord/README.md` | `NO_IMPACT` | T025 / `v2-core-owner` | Rationale: token, SSE/MCP, routing, and send-backstop guidance remains transport-only and does not consume I-030A; record exact review unchanged. |

Global current-state claims remain integrator-owned; the component guide and
every exact handoff delta are required before 030 can converge. T025 records
the reviewer, validation result, and evidence-backed rationale for every
`NO_IMPACT` row in `evidence/v2/attention/handoff.md`; the later lifecycle gates
record exact candidate identity in `slice-candidate.md` and
`slice-handoff.md`. A bare matrix assertion is not documentation-freshness
evidence.

## Owner Handoff

The owner must hand off the exact commit, I-030A and upstream interface
versions, complete commands/results, prompt and model identity, effective
operator configuration and source, margin state, deterministic/replay/multi-
model evidence (including exact provider IDs/provenance for the selected three-
family matrix or an explicit later Zoe override), the preregistered downstream
canary protocol, rejected claims, and known limitations. The handoff explicitly
does not claim live participant outcomes. Downstream review
does not silently transfer core ownership; 110 remains the sole final sink.
The packet distinguishes (1) the tested implementation tree named by T027,
(2) the lifecycle candidate commit that contains `verification.md`, and (3) the
later handoff packet commit containing lifecycle records. Exact-candidate and
packet-commit baseline reruns are both required and recorded only from later
commits, so no self-referential SHA is embedded in its own tree.

## Complexity Tracking

No constitution violation or justified complexity exception is planned.
