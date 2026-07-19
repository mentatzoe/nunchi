# Tasks: V2 Core Attention

**Input**: `specs/030-v2-core-attention/spec.md` and `specs/030-v2-core-attention/plan.md`

**Slice state**: `PLANNED`

**Execution status**: `DORMANT` while the slice remains `PLANNED`

**Program implementation authority**: `GRANTED`

**Assigned participant / source**: codex-session-1 — evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted declared dependency `010-v2-contract`; an assigned
participant and durable external assignment source declared above;
active `v2-core-owner`; zero CRITICAL/HIGH analysis findings; and an isolated
owner worktree

**Resolved upstream finding**: Accepted I-010E `@2` at exact amendment
candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb` represents required
classifier policy provenance and the paired `NO_WAKE` operational-failure
override. This consumer independently accepted it at
`evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`; the original
consumer acceptance and post-acceptance blocker remain immutable history. No
task below may begin until the fresh bound analysis reports zero CRITICAL/HIGH
findings and activation evidence establishes `READY`. Do not add local receipt
fields or encode provenance in `error.detail`.

**Activation evidence**: `evidence/v2/attention/slice-activation.md`, written
only after every activation prerequisite is accepted; it copies and attests the
assignment declaration and all other prerequisite facts, establishing `READY`
before `ACTIVE` or any implementation checkbox

**Dependency evidence contract**: the activation record MUST preserve declared
order in `Accepted dependencies`, record ordered `Dependency commits` as
`slice=full-sha`, and record matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Task manifest**: Run
`python3 scripts/check_governance.py --task-manifest specs/030-v2-core-attention`
and copy its exact `Initial task IDs` / `Initial tasks SHA256` into activation,
then its `Completed task IDs` / `Tasks SHA256` into each candidate attempt.
The immutable activation record retains the initial values; a convergence-
appended task graph is hashed only in its later candidate attempt and requires
a new bound delivery run.

**Candidate evidence**: `evidence/v2/attention/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/attention/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/attention/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Rejection / rework**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

**Accountable owner lane**: `v2-core-owner`

**Integration handoff**: `v2-wake-owner`, owners of slices `060` through `110`,
and `v2-integrator`

**Slice activation**: No checkbox may begin while the slice is `PLANNED` or
before valid activation evidence attests the accepted prerequisites above and
establishes `READY`. The assigned participant must then declare `ACTIVE` before
beginning the first checkbox.

**Tests**: Red deterministic contract/transition tests precede implementation;
replay/model evidence remains separate from unit mechanics; live participant
canaries belong to dependent surfaces and final integration.

**Documentation freshness**: `README.md` and every exact ordinary path in
`plan.md` §Documentation Impact and Freshness are blocking. `UPDATE` requires
candidate-relative validation, `NO_IMPACT` requires exact-path rationale and a
reviewer in ordinary handoff evidence, and `HANDOFF` requires the exact claim
delta and accepting owner. No candidate may reach owner handoff before the
later workflow documentation-freshness gate passes.

## Activation Gate (Prerequisite, Not an Implementation Checkbox)

Activation is deliberately outside the task manifest: no implementation task
may be checked to establish its own authority or readiness. Before `T001`, the
assigned `v2-core-owner` and the bound workflow MUST verify and freeze all of
the following in immutable `evidence/v2/attention/slice-activation.md`:

- the complete eleven-slice authorization record at
  `evidence/governance/v2-implementation-authorization.md`, which documents but
  does not grant authority;
- the durable assignment at
  `evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md`;
- terminal acceptance of the exact `010-v2-contract` candidate plus this
  consumer's separate acceptance at
  `evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`, recorded as
  ordered `slice=full-sha` and `slice=repo-relative-evidence-file` mappings;
- zero CRITICAL/HIGH analysis findings, including no unresolved spec/plan/task
  or documentation-disposition conflict;
- the isolated `.worktrees/v2-core-attention/` worktree on
  `v2/core-attention`, its full starting commit, and the green full ordinary-
  path baseline at that commit, freezing exact root test/skip counts, the ordered
  tracked pre-030 test-file inventory and content hash outside
  `tests/v2/attention/`, and the exact allowed 030 diff roots;
- consumed I-010A/B/E versions, produced I-030A, acceptance scenes, evidence
  targets, the exact documentation matrix, and the task-manifest fields above.

Only after that record establishes `READY` may the assigned participant declare
`ACTIVE`. Until then, every checkbox below remains dormant.

## Phase 1: Setup (Shared Test Infrastructure)

**Purpose**: Establish the reusable test seam used by every story.

- [ ] T001 Create the root-discoverable attention test package and helpers at `tests/v2/attention/__init__.py` and `tests/v2/attention/helpers.py`

## Phase 2: Foundational (Blocking Red Tests and Evaluation Harness)

**Purpose**: Freeze contract, transition, bypass, error, receipt, projection,
and replay expectations before implementation.

**BLOCKING**: T002–T004 must be observed red for the intended missing V2
behavior, and this phase must complete before any user-story implementation.

- [ ] T002 [P] Add red core/CLI contract tests for field-for-field `evaluate_v2`/`attention-v2` I-030A equivalence, exact tagged stdout, diagnostic stderr, exit 0/1/2/3, input-JSON → config/sink-construction → request-schema/binding → trusted-budget validation failure precedence, wake-default/no-override behavior before the complete trusted-policy boundary even when raw input contains `NO_WAKE`, the exact `--config PATH` closed file and exclusive receipt-directory adapter, the version-resolved policy/error receipt contract, one immutable attention-stage receipt when a valid request ID and sink exist, no fabricated receipt/ID on unreadable, invalid-JSON, unassignable, or unavailable-sink paths, and unchanged current V1 public exports/`admit` behavior in `tests/v2/attention/test_core_cli_contract.py`
- [ ] T003 [P] Add red transition-policy tests for the exact 36-row SC-002 domain, freezing the inclusive `PASS - max(ACK, ASK, SPEAK) <= transition_defer_margin` inside-margin rule (including equality), its strictly-greater outside-margin complement, response status, pair, margin status, valve, and override cause under FR-008's validation-first and suppression-disabled → recoverability-unproven → margin → none precedence in `tests/v2/attention/test_transition_policy.py`
- [ ] T004 [P] Add red tests for the exact policy/recoverability/classifier-config shapes including required no-default `max_retries`, participant/scope binding mismatches, descriptor-first no-follow file/directory ownership and mode checks, missing/unsafe/symlink/broad-mode/duplicate-key/extra/conflicting trusted config, raw/partial `NO_WAKE` rejected to wake default with no override receipt pair until complete config/request/binding trust, validated `NO_WAKE` applied to later budget/provider/runtime errors, forbidden inline/environment/request sources, synchronous receipt-sink success/failure/one-call protocol, descriptor-relative exclusive-create/no-overwrite/file-and-directory-fsync/cleanup plus exact `not-persisted`/`unknown` failure behavior—including collision → `unknown` without touching the existing file—bounded retry/exhaustion, bypass, error, continuation-secret projection, and trusted attention-budget cases for below/equal/above actual event count and canonical projection bytes, absent/below/equal/above coverage declarations, every event kind, zero-call overage, no core truncation/reassembly, and request-correlated error receipt, plus the recorded four-field owner advice rubric—including prompt-only two-item/240-scalar criteria without locally narrowing I-010B—in `tests/v2/attention/test_advice_and_errors.py`
- [ ] T005 [P] Create V2 attention replay runner in `evals/v2/attention/runner.py`

## Phase 3: User Story 1 - Participant-Shaped Attention Judgment (Priority: P1)

**Goal**: Produce one valid classifier disposition from one factual I-010A
request without composition or deterministic social rules.

**Independent Test**: Deterministic provider fixtures and replay produce only
SUPPRESS/WAKE/DEFER with valid evidence/advice rules and one logical judgment.

- [ ] T006 [US1] Add a V2-only participant-shaped classifier path, exact zero-to-two retry rules, and the sparse-advice prompt criteria in `src/nunchi/classifiers.py` without changing or calling the current V1 classifier path
- [ ] T007 [US1] Implement the exact staged I-030A `evaluate_v2(request, *, policy, recoverability, classifier_config, receipt_sink)` seam—including spec FR-001's complete trusted input shapes, exact participant/scope binding, source-conflict rejection, synchronous one-call sink protocol, operational sink-failure behavior, and actual/declared attention-budget enforcement before bypass/provider use—plus I-010A validation, canonical classifier-safe projection, one-judgment orchestration, and zero-call trusted preattention bypass in `src/nunchi/core.py`; it must not call or translate through V1 `evaluate`, truncate/reorder/reassemble input, or recalculate coverage
- [ ] T008 [US1] Add V2 runtime models without reply-bearing fields in `src/nunchi/models.py` while preserving current V1 models for the pre-cutover baseline
- [ ] T009 [P] [US1] Add false-suppression-scar corpus in `evals/v2/attention/suppression-scars/cases.jsonl`
- [ ] T010 [US1] Record deterministic judgment and scar/no-ledger replay results with mandatory S04/S16 `scene_id` values in `evidence/v2/attention/s04-suppression-scars/results.jsonl`

## Phase 4: User Story 2 - Governed Suppression and Dual DEFER (Priority: P1)

**Goal**: Apply only trusted, safety-widening delegation and transition policy
while keeping classifier and margin deferrals distinct.

**Independent Test**: Exhaustive transition/policy fixtures prove missing
legitimacy or malformed evidence never produces effective suppression.

- [ ] T011 [US2] Implement the closed trusted effective-attention policy, classifier configuration, and separately supplied recoverability-capability validation from spec FR-001—including positive limits, active/retired margin pairing, strict participant/scope binding, normalized single-source rules, secret non-disclosure, and the inclusive actual/declaration event and canonical-projection byte cap rules—in `src/nunchi/schema.py`
- [ ] T012 [US2] Implement the allowed disposition transition matrix in `src/nunchi/core.py`, preserving the exact inclusive active-margin comparison from FR-008
- [ ] T013 [US2] Implement separate classifier-DEFER and margin-DEFER audit in `src/nunchi/models.py`
- [ ] T014 [P] [US2] Add the exact 36-row governed-suppression matrix from SC-002, including explicit equality-boundary inside-margin and strictly-greater outside-margin cases, in `evals/v2/attention/governed-suppression/cases.jsonl`
- [ ] T015 [P] [US2] Add dual-valve replay and canary analysis in `evals/v2/attention/defer-transition/analyze.py`
- [ ] T016 [US2] Record governed-suppression results in `evidence/v2/attention/s05-governed-suppress.jsonl`
- [ ] T017 [US2] Record separate DEFER-valve results and active-margin status with mandatory S08 `scene_id` values in `evidence/v2/attention/s08-defer-transition/results.jsonl`

## Phase 5: User Story 3 - Error, Receipt, and CLI Parity (Priority: P2)

**Goal**: Expose one tagged core/CLI seam with separate operational error and
off-surface lifecycle audit.

**Independent Test**: Core and CLI outputs match for valid input; every invalid
or failed path returns ERROR and the correct wake-default/override audit.

- [ ] T018 [US3] Implement I-010B ok/bypass/error response validation and the version-resolved immutable attention-stage receipt contract only when a valid request ID exists, with wake default and no override fields before complete config/request/binding trust, selected effective-policy/`NO_WAKE` provenance for later failures represented only through the accepted 010-owned pair, no fabricated record for unassignable pre-validation or receipt-sink failures, and an explicit no-persistence error fact, in `src/nunchi/schema.py`
- [ ] T019 [US3] Add the non-current `attention-v2 --config PATH` command with the exact I-030A stdout/stderr and exit 0/1/2/3 process contract, fixed input/config/request failure precedence, descriptor-secure closed operator config loading, and exclusive JSON-file receipt adapter with typed persistence outcomes in `src/nunchi/cli.py`; leave current V1 `admit` unchanged
- [ ] T020 [US3] Prove `evaluate_v2` and `attention-v2` never call, translate through, or fall back to V1, keep current V1 request/verdict and `require_pass_corroboration` paths unchanged for the green lane baseline, and record the exact slice-110 deletion/publication delta in `evidence/v2/attention/handoff.md`
- [ ] T021 [P] [US3] Add core/CLI ok, preattention-bypass, request-ID-bearing and unassignable pre-validation, invalid-input, participant/scope mismatch, below/equal/above actual and declared attention budgets with zero-call/no-truncation oracles, raw/partial `NO_WAKE` across missing/unsafe/symlink/broad-mode/duplicate-key/extra/conflicting/binding-invalid config proving wake default and absent override pair, validated `NO_WAKE` on later errors, forbidden alternate trusted sources, exclusive receipt-file collision → `unknown` plus pre-create/post-create/write/fsync/cleanup persistence oracles, retry/exhaustion, provider/runtime, malformed-model, exact field-equivalence, version-resolved policy/error receipt, callable sink-failure, and canonical projection parity corpus in `evals/v2/attention/core-cli/cases.jsonl`
- [ ] T022 [US3] Record core/CLI parity, bypass handoff, and error-fallback results with mandatory S06/S09/`030-CLI` `scene_id` values in `evidence/v2/attention/core-cli-parity.jsonl`

## Phase 6: Social Evidence, Documentation Validation, and Handoff Inputs

**Purpose**: Complete the non-unit evidence, execute the exact documentation
matrix, and assemble the reproducible owner packet. This phase blocks
convergence and handoff; it is not optional polish.

- [ ] T023 Run the incumbent Gemini 3.1 Flash Lite, frontier GPT-5.5, and open-weight Qwen3 comparison (or an explicit later Zoe override) and record every attempt with mandatory scene IDs, exact provider IDs, provider/endpoint, prompt/config, date, the note/citations/scalar count and four binary FR-005 owner-adjudication fields for every WAKE advice item, mistaken/missed suppressions, wake volume, family disagreement, and results in `evidence/v2/attention/model-comparison/results.jsonl`; treat social rates as descriptive/non-gating limitations, but block handoff on a missing family/corpus/provenance record, any failed advice-rubric field, or unsafe mechanical routing
- [ ] T024 Preregister the downstream live DEFER canary scenes, metrics, stop/retirement rules, owners, and immutable result paths in `evidence/v2/attention/defer-canary/protocol.md`; do not execute participant/live-room canaries in slice 030
- [ ] T025 Execute and validate every exact row in `plan.md` §Documentation Impact and Freshness and record candidate-relative results in `evidence/v2/attention/handoff.md`: `UPDATE` `docs/attention/v2.md`, `docs/contracts/verdict-suite-data-model-v1.md`, `docs/contracts/verdict-suite-requirements-v1.md`, `docs/evaluations/verdict-suite.md`, and `docs/evaluations/verdict-suite-runner.md`; route the exact `HANDOFF` delta and accepting owner for `README.md`, `CHANGELOG.md`, `docs/INSTALL.md`, `docs/STABILITY.md`, `docs/adapters.md`, `docs/architecture/v2-selected-design.md`, `docs/contracts/channel-adapter-v1.md`, `docs/integration.md`, `integrations/claude-code/DEFER_EVAL.md`, `integrations/claude-code/README.md`, `integrations/codex/README.md`, and `integrations/hermes/README.md`; and record reviewer plus concrete candidate-specific rationale for `NO_IMPACT` on `docs/archive/v1/README.md`, `docs/archive/v1/admission-classifier/contract.md`, `docs/archive/v1/admission-classifier/data-model.md`, `docs/archive/v1/admission-classifier/quickstart.md`, `docs/archive/v1/core-cli/contract.md`, `docs/archive/v1/core-cli/data-model.md`, `docs/archive/v1/core-cli/quickstart.md`, `docs/contracts/nunchi-v2.md`, `docs/governance/execution-spine.md`, `docs/integrations/hermes-core-patch.md`, `docs/integrations/hermes-core-patch-test-plan.md`, `integrations/claude-code/transport-patch/README.md`, `integrations/mcp-discord/DESIGN.md`, and `integrations/mcp-discord/README.md`; validate applicable links, Mermaid diagrams, examples, commands, CLI exits, install/version claims, evidence links, and V1-current/V2-component truth without claiming atomic cutover or live participant results
- [ ] T026 Publish the scene-to-record command and evidence manifest in `evidence/v2/attention/README.md` and assemble the proposed owner packet inputs in `evidence/v2/attention/handoff.md`: complete commands/results, I-030A and consumed version-resolved I-010A/B/E versions, prompt/model and effective-policy provenance, all deterministic/replay/three-family records, downstream canary protocol, active-margin state, exact documentation dispositions/validation/reviewer and routed deltas from T025, rejected claims, limitations, every named downstream recipient, the exact slice-110 delta that removes V1 and staging names while publishing I-030A, and the three distinct commit roles (tested implementation tree, lifecycle candidate, later packet commit); the later convergence, documentation-freshness, and owner-handoff gates record exact candidate/packet commits and establish lifecycle state, never this checkbox
- [ ] T027 Run `python3 scripts/check_governance.py --check-cli`, `python3 -m unittest`, `python3 -m unittest discover -s tests/v2/attention -p 'test_*.py'`, `python3 -m evals.v2.attention.runner --all`, `python3 -m evals.verdict_suite.runner --list`, and `git diff --check` against the tested implementation tree; compare with activation and reject any changed pre-030 test byte/inventory, deleted or renamed pre-030 test, added skip, adapter/harness or 010-owned `schemas/v2/` contract edit, or path outside the exact 030-owned source/test/eval/evidence/docs set; require zero focused-suite skips, root skips equal the frozen activation skip count, and root test count equal the frozen activation root count plus focused count; record that parent commit, exact commands/results/counts/hashes, descriptive elapsed/byte/token-or-unavailable/attempt/provider-model/runtime/host-OS/fixture fields, environment, and diff scope in `evidence/v2/attention/verification.md` without self-referencing the T027 commit; block convergence on any failure and require the later gates to rerun/record the same baseline at the lifecycle candidate and packet commits

## Post-Task Lifecycle Gates (Not Implementation Checkboxes)

After T001–T027 are complete, the bound workflow—not this task graph—must:

1. recompute `Completed task IDs` / `Tasks SHA256`, verify implementation,
   tests/evaluations, evidence, docs inputs, and limitations agree, then append
   the exact candidate attempt to `evidence/v2/attention/slice-candidate.md` to
   establish `CONVERGED`;
2. run the blocking documentation-freshness review against that exact candidate
   and the T025 record in `evidence/v2/attention/handoff.md`;
3. only on documentation PASS, append the complete packet attempt to
   `evidence/v2/attention/slice-handoff.md`, name every downstream recipient and
   `v2-integrator`, and establish `HANDOFF_READY`;
4. stop before acceptance: only `v2-integrator` may accept or reject the exact
   slice candidate, and every dependent separately records its own acceptance.

## Dependencies & Execution Order

- The activation gate above precedes T001 and is never satisfied by checking a
  task box; every task remains dormant until the slice is `ACTIVE`.
- The accepted 010 commit is immutable input to all tasks.
- T001 precedes deterministic tests; the foundational T002–T005 phase blocks
  user-story implementation, and T002–T004 must fail for the intended missing
  V2 behavior before T006–T013 are accepted.
- US1 establishes the classifier/core boundary used by US2 and US3.
- T014 and T015 may proceed in parallel after transition semantics are stable.
- T019/T020 follow runtime response validation; T023 requires the complete
  engine and explicit permission for provider calls, while T024 specifies
  downstream evidence without requiring a participant implementation.
- T026 requires all deterministic, replay, model, protocol, and documentation
  outputs; T027 then verifies the exact candidate baseline and both precede the
  separate convergence, documentation-freshness, and
  owner-handoff gates. Slice 040 and later consumers start only after separately
  accepting and recording the lifecycle handoff packet derived from it; live
  participant outcomes are explicitly not a 030 handoff prerequisite.

## Parallel Opportunities

- T002–T005 target separate ordinary paths.
- T009, T014, T015, and T021 are distinct corpus families after their respective
  interface prerequisites.
- Model comparison preparation, downstream canary protocol, and documentation
  may overlap deterministic evidence; surfaces and 110 execute live canaries
  only after the dependent lifecycle exists.

## Implementation Strategy

Make the one-judgment classifier seam valid first, then add the safety-widening
transition, then expose error/receipt/CLI parity. Treat margin retirement as a
separate evidence decision and stop on any pressure to encode a deterministic
social shortcut.

## Notes

- No task edits 010 schemas, 020 observation, 040 participant host, or any
  surface integration.
- No task creates a product artifact under a SpecKit-managed path.
- Unit tests do not close social-quality or downstream live-canary requirements.
- No task performs slice acceptance, atomic integration, cutover, release, or
  promotion.
