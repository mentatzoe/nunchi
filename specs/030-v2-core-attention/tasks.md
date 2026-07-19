# Tasks: V2 Core Attention

**Input**: `specs/030-v2-core-attention/spec.md` and `specs/030-v2-core-attention/plan.md`

**Slice state**: `PLANNED`

**Execution status**: `DORMANT` while the slice remains `PLANNED`

**Program implementation authority**: `GRANTED`

**Assigned participant / source**: codex-session-1 — evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md

The named assignment MUST remain a non-symlink durable record containing
exactly one `Assignee`, `Lane`, `Assigned by`, ISO `Assigned on`, and durable
`Authority reference`; a non-Zoe assigner additionally requires
`Delegated by: Zoe` and a durable `Delegation reference`. Assignment neither
grants program implementation authority nor establishes slice readiness or
activation.

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted declared dependency `010-v2-contract`; an assigned
participant and durable external assignment source declared above;
active `v2-core-owner`; completed fresh formal owner review at
`checklists/requirements.md` CHK165–CHK179, with CHK111–CHK164 retained as
history rather than reused for the final ownership, continuation, retry, and
sink-persistence clarification; zero scoped CRITICAL/HIGH analysis findings;
and an isolated owner worktree

**Resolved upstream findings**: Accepted I-010E `@2` at exact amendment
candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb` represents required
classifier policy provenance and the paired `NO_WAKE` operational-failure
override. This consumer independently accepted it at
`evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`; the original
consumer acceptance and post-acceptance blocker remain immutable history. No
task below may begin until the fresh bound analysis reports zero scoped CRITICAL/HIGH
findings and activation evidence establishes `READY`. Do not add local receipt
fields or encode provenance in `error.detail`.

Accepted I-010B `@2` at exact A2-R1 correction candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301` represents the selected inclusive
zero-width active-margin audit without changing another decision rule. This
consumer independently accepted it at
`evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`; the earlier
zero-margin blocker remains immutable history. No task below may begin until
fresh bound analysis reports zero scoped CRITICAL/HIGH findings and activation
evidence establishes `READY`.

**Open program-owner handoff**: the canonical program registry remains stale
for accepted I-010B/I-010E `@2`. It is recorded at
`evidence/v2/attention/program-interface-registry-I-010E-version-blocker.md`
and dispositioned at
`evidence/v2/attention/program-interface-registry-readiness-disposition.md` as
a non-blocking `v2-program-owner` handoff, not a dependency/task-graph finding.
This slice neither edits nor claims completion of that program artifact.

**Planning reconciliation result**: The spec, plan, and this task graph retain
the same 47-path documentation matrix (8 `UPDATE`, 17 `NO_IMPACT`, and 22
`HANDOFF`). `checklists/requirements.md` records both the completed prior
CHK087–CHK110 delta review and codex-session-1's fresh completed CHK111–CHK134
formal owner review from the earlier reconciled requirement text. The later
receipt-sink clarification has its own completed formal owner gate at
CHK135–CHK164; codex-session-1 reviewed all 30 items from the reconciled spec,
plan, and tasks with no unresolved finding before fresh analysis or activation.
The final scoped-finding reconciliation has a separate completed gate at
CHK165–CHK179; codex-session-1 reviewed those 15 items from the final
reconciled artifacts without reusing either prior review. This is control-plane
review, not an implementation checkbox.

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

**Documentation freshness**: `README.md` and all 47 exact ordinary paths in
`plan.md` §Documentation Impact and Freshness are blocking: 8 `UPDATE`, 17
`NO_IMPACT`, and 22 `HANDOFF`. `UPDATE` requires candidate-relative validation,
`NO_IMPACT` requires exact-path rationale and a reviewer in ordinary handoff
evidence, and `HANDOFF` requires the exact claim delta and accepting owner. No
candidate may reach owner handoff before the later workflow documentation-
freshness gate passes.

## Activation Gate (Prerequisite, Not an Implementation Checkbox)

Activation is deliberately outside the task manifest: no implementation task
may be checked to establish its own authority or readiness. Before `T001`, the
assigned `v2-core-owner` and the bound workflow MUST verify and freeze all of
the following in immutable `evidence/v2/attention/slice-activation.md`:

- the complete eleven-slice authorization record at
  `evidence/governance/v2-implementation-authorization.md`, which documents but
  does not grant authority;
- the durable assignment at
  `evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md`,
  verified as a non-symlink record with exactly one occurrence of every
  required assignment field and any conditional Zoe-delegation fields
  described above, without treating assignment as authority or readiness;
- terminal acceptance of the exact `010-v2-contract` candidate plus this
  consumer's separate acceptance at
  `evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`, recorded as
  ordered `slice=full-sha` and `slice=repo-relative-evidence-file` mappings;
- zero scoped CRITICAL/HIGH analysis findings, including no unresolved spec/plan/task
  or documentation-disposition conflict; the spec, plan, and this task graph
  retain the same 47 exact documentation paths; CHK087–CHK110 retain the prior
  completed delta review, and codex-session-1 has completed fresh
  CHK111–CHK134 from the earlier reconciled requirement text; the separate
  CHK135–CHK164 receipt-sink delta gate remains historical evidence, and the
  separate CHK165–CHK179 final scoped-finding gate is complete from the latest
  reconciled artifacts with no unresolved ownership, continuation-retention,
  retry-taxonomy, sink-persistence, traceability, or documentation-disposition
  finding. That review confirmed the 47-path denominator remains complete. The
  zero-margin dependency finding must be superseded by the exact accepted A2
  consumer decision above, while the separate program-registry mismatch
  remains the recorded non-blocking owner handoff;
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
- [ ] T004 [P] Add red tests for the exact policy/recoverability/classifier-config shapes including required no-default `max_retries`, participant/scope binding mismatches, descriptor-first no-follow file/directory ownership and mode checks, missing/unsafe/symlink/broad-mode/invalid-JSON/duplicate-key/extra/conflicting trusted config, no config-derived sink before source security and duplicate-free parsing, independently secure sink use only after that boundary, raw/partial `NO_WAKE` rejected to wake default with no override receipt pair until complete config/request/binding trust, validated `NO_WAKE` applied to later receiptable budget/provider/runtime errors—including retry exhaustion—but never to a receipt-sink invocation failure, forbidden inline/environment/request sources, and the plan's exact numbered 23-case receipt-sink matrix: normal `None` → `persisted`; normal non-`None` → `unknown`; exact and subclass `ReceiptSinkPersistenceError` instances limited to `not-persisted`/`unknown`, with `not-persisted` permitted only for a closed-contract pre-write rejection that guarantees no durable side effect; unrecognized, attribute-lookalike, wrapper/cause-chained, forged-invalid-member, forbidden-`persisted` constructor, ordinary timeout/cancellation, and every post-dispatch failure → `unknown` without trusting or traversing arbitrary exception data; host-control `BaseException` propagation without an I-030A result; plus exclusive-create collision, other pre-create failure, write/flush/file-`fsync`/close failure with successful cleanup, the same failures with cleanup uncertainty, and final-directory-`fsync` uncertainty mapped to the exact typed adapter outcome. Prove every ordinary failure replaces the pending result with `receipt-sink-failure`, appends only the closed persistence fact, exposes no exception text/path/credential, uses shared `WAKE`, makes no second offer, and never retries `unknown`; then cover the closed I-030A code/detail mapping; HTTP `429`/`499`/`500`/`599`/`600`, `URLError`, direct timeout, `ConnectionError`, other request-execution `OSError`, exact `max_retries=0|1|2` attempt/sleep counts using fixed waits of 0.5 seconds before attempt 2 and 1.0 second before attempt 3, ignored `Retry-After`, no sleep after success/terminal/final failure, identical payload/request identity, stop-on-success, non-retryable post-response/malformed cases, and retry exhaustion with trusted `NO_WAKE` success and sink-failure fallback; bypass; error; exact `expansion_available: {before, after, around_event}` projection with false-without-continuation and copied flags otherwise; continuation-secret exclusion plus deep/canonical pre/post request equality and caller-held continuation availability; trusted attention-budget below/equal/above cases for actual event count and canonical projection bytes; absent/below/equal/above coverage declarations; every event kind; zero-call overage; no core truncation/reassembly; request-correlated error receipt; and the four-field advice rubric with prompt-only two-item/240-scalar criteria in `tests/v2/attention/test_advice_and_errors.py`
- [ ] T005 [P] Create the V2 attention aggregate runner in `evals/v2/attention/runner.py` so `python3 -m evals.v2.attention.runner --all` dispatches the exact `evals/v2/attention/defer-transition/analyze.py` file by filesystem path rather than importing the hyphenated directory as a package, includes its canonical S08 output in the aggregate result, and fails when that analyzer is not executed successfully

## Phase 3: User Story 1 - Participant-Shaped Attention Judgment (Priority: P1)

**Goal**: Produce one valid classifier disposition from one factual I-010A
request without composition or deterministic social rules.

**Independent Test**: Deterministic provider fixtures and replay produce only
SUPPRESS/WAKE/DEFER with valid evidence/advice rules and one logical judgment.

- [ ] T006 [US1] Add a V2-only classifier path in `src/nunchi/classifiers.py` that reads the classifier-safe snapshot as the participant described by `self`, asks only whether the supplied event is worth waking that participant for now, requests `SUPPRESS` only when confident they would not want to attend, `WAKE` when they likely would, and `DEFER` when uncertain, requires grounding in observed events without invented missing facts or reply composition, forbids speaker/address/topology/obligation rules and participant-move commands, and enforces the exact zero-to-two retry rules: classify `HTTPError` first; retry only `429`, `500..599`, outer `URLError`, direct `socket.timeout`/`TimeoutError`, and request-execution `OSError` including `ConnectionError`; never inspect `URLError.reason`; never retry other statuses or post-response/validation/malformed-output failures; reuse identical payload/logical request identity; wait exactly 0.5 seconds before attempt 2 and 1.0 second before attempt 3; ignore `Retry-After`; and never sleep after success, terminal non-retryable failure, or final allowed failure. Enforce the sparse-advice prompt criteria and neither change nor call the current V1 classifier path
- [ ] T007 [US1] Implement the exact staged I-030A `evaluate_v2(request, *, policy, recoverability, classifier_config, receipt_sink)` seam and engine-owned `ReceiptSinkPersistenceError` in `src/nunchi/core.py`: validate a read-only `persistence` member limited to `not-persisted`/`unknown`; recognize exact instances and subclasses with `isinstance`; never traverse wrappers or cause/context chains; permit `not-persisted` only for a closed-contract pre-write rejection that guarantees no durable side effect; map forged invalid members, normal non-`None` returns, every unrecognized or attribute-lookalike `Exception`, ordinary timeout/cancellation, and every post-dispatch failure to `unknown`; propagate `BaseException` host-control flow after the sole offer without fabricating an I-030A result; expose no exception text or unvalidated attribute; never permit an exception to claim `persisted`; and make every ordinary sink failure use shared `WAKE` with no retry or second offer. Include spec FR-001's complete trusted input shapes, exact participant/scope binding, source-conflict rejection, actual/declared attention-budget enforcement before bypass/provider use, I-010A validation, the canonical classifier-safe projection that removes continuation and inserts only `expansion_available: {before, after, around_event}`, and immutable caller-input handling that leaves the original request and continuation deep/canonical-equal and available to its caller; implement one-judgment orchestration and the exact I-010B zero-call trusted preattention bypass only, without emitting ParticipantWakeV2 or invoking a host; do not call or translate through V1 `evaluate`, truncate/reorder/reassemble input, or recalculate coverage
- [ ] T008 [US1] Add V2 runtime models without reply-bearing fields in `src/nunchi/models.py` while preserving current V1 models for the pre-cutover baseline
- [ ] T009 [P] [US1] Add the exact false-suppression-scar and three-family provider corpus in `evals/v2/attention/suppression-scars/cases.jsonl`, with unique `case_id`, canonical `scene_id`, contract-valid `request`, and preregistered `expected_attention: ATTEND | NOT_ATTEND` on every row; before any provider call also commit closed `evals/v2/attention/model-selection.json`, mapping Gemini 3.1 Flash Lite, GPT-5.5, and Qwen3 one-to-one to exact provider model IDs plus provider, endpoint class, catalog/source evidence, selection date, and `v2-core-owner` review, with any exact-ID change requiring a new pre-run manifest commit and any family substitution requiring Zoe's durable decision
- [ ] T010 [US1] Record deterministic judgment and scar/no-ledger replay results with mandatory S04/S16 `scene_id` values in `evidence/v2/attention/s04-suppression-scars/results.jsonl`

## Phase 4: User Story 2 - Governed Suppression and Dual DEFER (Priority: P1)

**Goal**: Apply only trusted, safety-widening delegation and transition policy
while keeping classifier and margin deferrals distinct.

**Independent Test**: Exhaustive transition/policy fixtures prove missing
legitimacy or malformed evidence never produces effective suppression.

- [ ] T011 [US2] Implement the closed trusted effective-attention policy, classifier configuration, and separately supplied recoverability-capability validation from spec FR-001—including positive integer limits, accepted I-010B `@2` active margin `[0,1]`/retired pairing, strict participant/scope binding, normalized single-source rules, secret non-disclosure, and the inclusive actual/declaration event and canonical-projection byte cap rules—in `src/nunchi/schema.py`
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

- [ ] T018 [US3] Implement I-010B ok/bypass/error response validation and the version-resolved immutable attention-stage receipt contract only when a valid request ID and eligible host-owned sink exist, defining offer as the sole sink invocation and persistence as its durable-success protocol, with zero offers and no fabricated record when no ID or eligible securely constructed sink exists, wake default and no override fields before complete config/request/binding trust, selected effective-policy/`NO_WAKE` provenance for later receiptable failures represented only through the accepted 010-owned pair, the shared `WAKE` default for every sink-invocation failure, the exact stable I-030A code/cause-detail map and post-attempt `receipt_persistence` suffix, no self-persistence claim in an offered receipt, no false persistence claim after a failed offer, no exception/path/credential leakage, and no second sink attempt, in `src/nunchi/schema.py`
- [ ] T019 [US3] Add the non-current `attention-v2 --config PATH` command with the exact I-030A stdout/stderr and exit 0/1/2/3 process contract, fixed input/config/request failure precedence, descriptor-secure closed operator config loading, and descriptor-relative exclusive JSON-file receipt adapter in `src/nunchi/cli.py`; raise only the engine-owned typed sink failure with `unknown` for collision without touching the existing file, `not-persisted` only for another pre-create exclusive-open rejection whose semantics guarantee no file was created, and `unknown` for every write/flush/file-`fsync`/close, cleanup, or final-directory-`fsync` failure even when best-effort relative unlink plus directory `fsync` succeeds; never retry an `unknown` result and leave current V1 `admit` unchanged
- [ ] T020 [US3] Prove `evaluate_v2` and `attention-v2` never call, translate through, or fall back to V1, keep current V1 request/verdict and `require_pass_corroboration` paths unchanged for the green lane baseline, and record in `evidence/v2/attention/handoff.md` the exact slice-110 deletion/publication delta across `src/nunchi/core.py`, `src/nunchi/cli.py`, `src/nunchi/classifiers.py`, `src/nunchi/models.py`, `src/nunchi/schema.py`, and `src/nunchi/__init__.py`: remove V1 request/verdict handling, `require_pass_corroboration`, reply-bearing output, and hidden local fallbacks; publish I-030A as public `evaluate`/`admit`; and remove temporary `evaluate_v2`/`attention-v2` names in the same atomic candidate
- [ ] T021 [P] [US3] Add core/CLI ok, preattention-bypass, request-ID-bearing and unassignable pre-validation, invalid-input, participant/scope mismatch, below/equal/above actual and declared attention budgets with zero-call/no-truncation oracles, raw/partial `NO_WAKE` across missing/unsafe/symlink/broad-mode/invalid-JSON/duplicate-key/extra/conflicting/binding-invalid config proving wake default and absent override pair, zero config-directed writes before source security and duplicate-free parsing, validated `NO_WAKE` on later receiptable non-sink errors, forbidden alternate trusted sources, and all 23 plan-numbered receipt-sink cases with their exact callable/CLI classifications, one-offer/no-second-offer behavior, shared-`WAKE` rule, safe persistence suffix, exception-secrecy oracle, collision no-touch oracle, post-dispatch-unknown even after successful cleanup, no non-idempotent retry on `unknown`, and `BaseException` propagation boundary in `evals/v2/attention/core-cli/cases.jsonl`; also cover the complete stable I-030A error-code/detail mapping and sink-failure precedence; HTTP `429`/`499`/`500`/`599`/`600`, outer `URLError`, direct timeout, `ConnectionError`, other request-execution `OSError`, exact `max_retries=0|1|2` attempts/sleeps using the fixed 0.5-second/1.0-second schedule, ignored `Retry-After`, zero sleep after success/terminal/final failure, identity reuse, stop-after-success, non-retryable post-response/malformed cases, and exhaustion; provider/runtime and malformed-model outcomes; exact core/CLI field equivalence; version-resolved policy/error receipt; canonical `expansion_available` projection parity; and caller-retained pre/post byte/deep equality proving the original continuation remains unchanged and available while no secret enters provider input
- [ ] T022 [US3] Record core/CLI parity, exact I-010B `status: bypass`, `cause: "preattention-disabled"` plus zero-call handoff (without claiming ParticipantWakeV2 emission or host invocation), and error-fallback results with mandatory S06/S09/`030-CLI` `scene_id` values in `evidence/v2/attention/core-cli-parity.jsonl`; record the proposed slice-040 acceptance oracle that maps the accepted bypass branch to `PREATTENTION_BYPASS`

## Phase 6: Social Evidence, Documentation Validation, and Handoff Inputs

**Purpose**: Complete the non-unit evidence, execute the exact documentation
matrix, and assemble the reproducible owner packet. This phase blocks
convergence and handoff; it is not optional polish.

- [ ] T023 Refuse execution unless committed `evals/v2/attention/model-selection.json` is closed, one-to-one, and reviewed as required by T009, then run the exact Cartesian product of every committed `evals/v2/attention/suppression-scars/cases.jsonl` case and its three exact selected provider model IDs, rejecting any family/ID mismatch or post-result selection change, and record every attempt in `evidence/v2/attention/model-comparison/results.jsonl` with canonical `case_id`/`scene_id`, corpus and selection-manifest identity, `expected_attention`, exact provider model ID, provider, endpoint class, date, prompt/config identity, effective-policy source, invocation command, direct/effective dispositions, result, and any override provenance; for every WAKE advice item also record the note, cited supplied-event IDs, Unicode scalar count, deterministic citation-resolution field, and three owner-adjudicated semantic fields; compute mistaken suppression over all `ATTEND` cases, missed suppression over all `NOT_ATTEND` cases, wake volume over all cases, separate direct-DEFER and margin-DEFER counts, and family disagreement over all case IDs exactly as FR-014 defines; treat rates as descriptive/non-gating limitations, but block handoff on a missing/duplicate family-case result, incomplete provenance, failed advice field, or unsafe mechanical routing
- [ ] T024 Preregister the downstream live DEFER canary scenes, metrics, stop/retirement rules, owners, and immutable result paths in `evidence/v2/attention/defer-canary/protocol.md`; do not execute participant/live-room canaries in slice 030
- [ ] T025 Execute and validate all 47 exact rows in `plan.md` §Documentation Impact and Freshness—exactly 8 `UPDATE`, 17 `NO_IMPACT`, and 22 `HANDOFF`—and record candidate-relative results in `evidence/v2/attention/handoff.md`: `UPDATE` `evidence/README.md`, `evidence/verdict-suite/README.md`, `evidence/v2/attention/README.md`, `docs/attention/v2.md`, `docs/contracts/verdict-suite-data-model-v1.md`, `docs/contracts/verdict-suite-requirements-v1.md`, `docs/evaluations/verdict-suite.md`, and `docs/evaluations/verdict-suite-runner.md`, with `docs/attention/v2.md` and `evidence/v2/attention/README.md` explicitly documenting the typed/unrecognized receipt-sink taxonomy, all 23 evidence cases, shared-`WAKE` rule, candidate binding, and non-current boundary; route the exact `HANDOFF` delta and accepting owner for `README.md`, `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/INSTALL.md`, `docs/STABILITY.md`, `docs/adapters.md`, `docs/architecture/v2-selected-design.md`, `docs/contracts/channel-adapter-v1.md`, `docs/integration.md`, `examples/loader-snippet.md`, `examples/generic_host_demo.py`, `examples/read_the_room_demo.py`, `profiles/open-floor.md`, `integrations/claude-code/DEFER_EVAL.md`, `integrations/claude-code/README.md`, `integrations/claude-code/nunchi-gate.env.example`, `integrations/codex/README.md`, `integrations/codex/nunchi-codex/.codex-plugin/plugin.json`, `integrations/codex/nunchi-codex/hooks/hooks.json`, `integrations/hermes/README.md`, and `integrations/hermes/nunchi-gate/plugin.yaml`, including the exact host-visible receipt-sink exception delta wherever that accepted owner needs it; and record reviewer plus concrete candidate-specific rationale for `NO_IMPACT` on `evidence/v2/contract/README.md`, `docs/archive/v1/README.md`, `docs/archive/v1/admission-classifier/contract.md`, `docs/archive/v1/admission-classifier/data-model.md`, `docs/archive/v1/admission-classifier/quickstart.md`, `docs/archive/v1/core-cli/contract.md`, `docs/archive/v1/core-cli/data-model.md`, `docs/archive/v1/core-cli/quickstart.md`, `docs/contracts/nunchi-v2.md`, `docs/governance/execution-spine.md`, `docs/integrations/hermes-core-patch.md`, `docs/integrations/hermes-core-patch-test-plan.md`, `integrations/claude-code/transport-patch/README.md`, `integrations/codex/nunchi-codex/.mcp.json`, `integrations/hermes/nunchi-gate/dashboard/manifest.json`, `integrations/mcp-discord/DESIGN.md`, and `integrations/mcp-discord/README.md`, re-justifying the accepted-contract no-impact rows against I-030A ownership rather than inheriting a stale review; validate applicable links, Mermaid diagrams, callable examples, commands, CLI exits, configuration syntax/default claims, installed metadata, exception/persistence claims, evidence-grade/current-state boundaries, evidence links, and V1-current/V2-component truth without claiming atomic cutover or live participant results
- [ ] T026 Publish the scene-to-record command and evidence manifest in `evidence/v2/attention/README.md` and assemble the proposed owner packet inputs in `evidence/v2/attention/handoff.md`: complete commands/results; I-030A and consumed version-resolved I-010A/B/E versions; the exact `ReceiptSinkPersistenceError` construction/recognition boundary and 23-case result matrix; prompt/model and effective-policy provenance; all deterministic/replay/three-family records; downstream canary protocol; active-margin state; all 47 exact documentation dispositions/validations/reviewer findings and routed deltas from T025; rejected claims and limitations; the individually named recipients `v2-wake-owner`, `v2-hermes-owner`, `v2-claude-owner`, `v2-codex-owner`, `v2-adapters-owner`, `v2-security-owner`, and `v2-integrator`; each dependent's separate exact-commit/packet acceptance duty for the complete I-030A `@1` seam; exact accepted I-010B `status: bypass`, `cause: "preattention-disabled"` and zero-call evidence, with an explicit `v2-wake-owner`/slice-040 obligation to accept it independently, map it to ParticipantWakeV2 source `PREATTENTION_BYPASS`, and pass a downstream mapping test; an explicit statement that 030 emits no ParticipantWakeV2 and invokes no host; and the exact slice-110 delta across `src/nunchi/core.py`, `src/nunchi/cli.py`, `src/nunchi/classifiers.py`, `src/nunchi/models.py`, `src/nunchi/schema.py`, and `src/nunchi/__init__.py` that removes V1 request/verdict handling, `require_pass_corroboration`, reply-bearing output, hidden local fallbacks, and staging names while publishing I-030A as public `evaluate`/`admit`; distinguish the tested implementation tree, lifecycle candidate, and later packet commit, because the later convergence, documentation-freshness, and owner-handoff gates record exact candidate/packet commits and establish lifecycle state, never this checkbox
- [ ] T027 Run `python3 scripts/check_governance.py --check-cli`, `python3 -m unittest`, `python3 -m unittest discover -s tests/v2/attention -p 'test_*.py'`, `python3 -m evals.v2.attention.runner --all`, `python3 -m evals.verdict_suite.runner --list`, and `git diff --check <activation-start>..HEAD` against the tested implementation tree, resolving `<activation-start>` from immutable activation evidence; compare with activation and reject any changed pre-030 test byte/inventory, deleted or renamed pre-030 test, added skip, adapter/harness or 010-owned `schemas/v2/` contract edit, or path outside the exact 030-owned source/test/eval/evidence/docs set; require all 23 receipt-sink matrix cases with their exact numbered oracles, zero focused-suite skips, root skips equal the frozen activation skip count, and root test count equal the frozen activation root count plus focused count; record that parent commit, exact commands/results/counts/hashes, the 23/23 zero-skip receipt-sink result, candidate binding, descriptive elapsed/byte/token-or-unavailable/attempt/provider-model/runtime/host-OS/fixture fields, environment, and diff scope in `evidence/v2/attention/verification.md` without self-referencing the T027 commit; block convergence on any failure and require the later gates to rerun/record the same commit-range whitespace check and baseline at the lifecycle candidate and packet commits

## Post-Task Lifecycle Gates (Not Implementation Checkboxes)

After T001–T027 are complete, the bound workflow—not this task graph—must:

1. recompute `Completed task IDs` / `Tasks SHA256`, verify implementation,
   tests/evaluations, evidence, docs inputs, and limitations agree, then append
   the exact candidate attempt to `evidence/v2/attention/slice-candidate.md` to
   establish `CONVERGED`;
2. run the blocking documentation-freshness review against that exact candidate
   and all 47 T025 dispositions recorded in
   `evidence/v2/attention/handoff.md`;
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
