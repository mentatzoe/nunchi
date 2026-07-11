# Tasks: Nunchi V2 End-to-End Parity Program

**Input**: `spec.md`, `plan.md`, and `research.md` in this control-plane
directory

**Prerequisites**: Goal 1 completion; zero CRITICAL/HIGH analysis findings;
explicit, separately recorded Goal 2 authorization; one active occupant for
each accountable owner lane; and satisfied upstream slice dependencies

**Accountable owner lane**: `v2-program-owner`

**Integration handoff**: `v2-integrator`

**Authorization state**: FUTURE GOAL 2 PLAN — no task below is authorized by
Goal 1 or by the existence of this file.

## Format

`[ID] [P?] [Story] Description`

- `[P]` means the task may run concurrently after all explicit dependencies.
- Product changes target ordinary repository paths only.
- Slice task files are the executable work queues for their one owner; this
  umbrella list governs activation, handoff, assurance, and atomic integration.

## Phase 1: Goal 2 Activation

**Purpose**: Establish authorization and accountability before product work.

- [ ] T001 Record Zoe's explicit Goal 2 objective and authorization outside task status, then have `v2-program-owner` verify it against Constitution 2.0.1.
- [ ] T002 Record one active work context for each stable owner lane and one for `v2-integrator`; reject duplicate or silently shared occupancy.
- [ ] T003 Run `python3 scripts/check_governance.py --check-cli` and the full ordinary-path test baseline before activating any slice.
- [ ] T004 Create the isolated `.worktrees/v2-contract/` worktree on branch `v2/contract` and activate only slice `010-v2-contract`.

**Checkpoint**: authorization is external and explicit; ownership is occupied;
only contract work is active.

## Phase 2: Contract Foundation

**Purpose**: Land one product contract before dependents begin.

- [ ] T005 [US1] Execute `010-v2-contract/tasks.md` under `v2-contract-owner`, creating schemas under `schemas/v2/` and contract tests under `tests/v2/contract/`.
- [ ] T006 [US1] Have `v2-program-owner` verify the `010` handoff packet, interface registry `I-010A`–`I-010E`, bypass branch, host-only continuation projection, immutable receipt-stage union, commands, and scene evidence; reject contract forks or embedded reply/social-ledger fields.
- [ ] T007 [US1] Hand the accepted exact `010` commit and interface versions to `v2-observation-owner`, `v2-core-owner`, and `v2-integrator`.

**Checkpoint**: one accepted V2 contract commit exists; no consumer has invented
a local variant.

## Phase 3: Observation and Core Attention

**Purpose**: Build the two independent foundations against the accepted
contract.

- [ ] T008 [P] [US1] Execute `020-v2-observation/tasks.md` in `.worktrees/v2-observation/` on `v2/observation` under `v2-observation-owner`.
- [ ] T009 [P] [US1] Execute `030-v2-core-attention/tasks.md` in `.worktrees/v2-core-attention/` on `v2/core-attention` under `v2-core-owner`.
- [ ] T010 [US2] Verify `020` produces `I-020A ObservationProviderV2@1` and immutable observation-stage records, preserves exact identity/native relations/budgets, and has no social inference or registry.
- [ ] T011 [US2] Verify `030` produces `I-030A AttentionEngineV2@1`, implements one participant-shaped judgment, keeps bypass/`ERROR` separate, strips host-only continuation authority from classifier input, emits immutable attention stages, honors the exact CLI process contract, and preserves the dual-valve transition.
- [ ] T012 [US2] Hand accepted exact commits and interface versions from `020` and `030` to `v2-wake-owner`, all named downstream consumers, and `v2-integrator`.

**Checkpoint**: observation and pre-attention are separately owned, independently
green, and contract-compatible.

## Phase 4: Participant Wake and Shared Discord Transport

**Purpose**: Complete the common participant lifecycle and Discord event source.

- [ ] T013 [P] [US2] Execute `040-v2-participant-wake/tasks.md` in `.worktrees/v2-participant-wake/` on `v2/participant-wake` under `v2-wake-owner` after `010`, `020`, and `030` are accepted.
- [ ] T014 [P] [US2] Execute `050-v2-discord-transport/tasks.md` in `.worktrees/v2-discord-transport/` on `v2/discord-transport` under `v2-transport-owner` after `010` and `020` are accepted.
- [ ] T015 [US3] Verify `040` produces `I-040A ParticipantTurnHostV2@1`, routes PREATTENTION_BYPASS without a model claim, emits immutable participant-host stages, exposes truthful context expansion, invokes a normal act-or-silence turn, and has no intermediate admission answer or send-time social gate.
- [ ] T016 [US3] Verify `050` produces `I-050A DiscordEventSourceV2@1` and immutable transport stages, limits deterministic no-wake to exact transport non-events, and proves continuity and native fact provenance.
- [ ] T017 [US3] Hand accepted exact `040` and `050` commits to their named surface owners and `v2-integrator`.

**Checkpoint**: common wake and shared Discord transport interfaces are accepted;
surface integrations may begin only where their full dependency sets are met.

## Phase 5: Surface Integrations

**Purpose**: Migrate independently owned consumers in parallel without contract
or shared-file drift.

- [ ] T018 [P] [US3] Execute `060-v2-hermes/tasks.md` in `.worktrees/v2-hermes/` on `v2/hermes` under `v2-hermes-owner`.
- [ ] T019 [P] [US3] Execute `070-v2-claude-code/tasks.md` in `.worktrees/v2-claude-code/` on `v2/claude-code` under `v2-claude-owner`.
- [ ] T020 [P] [US3] Execute `080-v2-codex/tasks.md` in `.worktrees/v2-codex/` on `v2/codex` under `v2-codex-owner`.
- [ ] T021 [P] [US3] Execute `090-v2-channel-adapters/tasks.md` in `.worktrees/v2-channel-adapters/` on `v2/channel-adapters` under `v2-adapters-owner`.
- [ ] T022 [US3] Verify every surface handoff uses the accepted interfaces, preserves preattention bypass and staged-receipt semantics, removes V1 lifecycle residue, proves direct act-or-silence behavior, and records honest unavailable platform facts.
- [ ] T023 [US4] Verify every surface handoff includes its installed-runtime commit/package/config/process provenance and live schema-2 probe under `evidence/v2/provenance/`.
- [ ] T024 [US3] Hand all accepted surface commits, scene matrices, evidence paths, and limitations to `v2-security-owner` and `v2-integrator`.

**Checkpoint**: every in-tree consumer has an accepted candidate handoff; main
still has not entered a mixed V1/V2 state.

## Phase 6: Blocking Security and Provenance Assurance

**Purpose**: Audit the exact integrated candidate rather than plans or local
claims.

- [ ] T025 [US4] Execute `100-v2-security-provenance/tasks.md` in `.worktrees/v2-security-provenance/` on `v2/security-provenance` under `v2-security-owner` against accepted commits from `010`–`090`.
- [ ] T026 [US4] Require tested mitigation for each threat by default; record any documentation-only residual risk only with Zoe's explicit acceptance under `docs/security/` and `evidence/v2/security/`.
- [ ] T027 [US4] Verify governed suppression, advice isolation, classifier projection secrecy, preattention bypass, immutable receipt-stage ownership, credentials, send safety, recoverability, restart behavior, and installed-runtime provenance against scenes `S01`–`S16`.
- [ ] T028 [US4] Hand the blocking assurance report, exact audited commit set, accepted limitations, and unresolved rejection list to `v2-integrator`; do not waive a failed blocking control.

**Checkpoint**: the candidate either has an accepted blocking assurance packet or
returns to its named owner; parity integration does not begin on a rejection.

## Phase 7: Parity Assembly and Atomic Cutover

**Purpose**: Establish the final success mode across all surfaces and land it
atomically.

- [ ] T029 [US3] Execute `110-v2-parity-cutover/tasks.md` in `.worktrees/v2-integration/` on `integration/v2` under `v2-integrator`, consuming the exact accepted commits from `010`–`100`.
- [ ] T030 [US4] Run the common replay corpus and acceptance scenes `S01`–`S16` across every applicable adapter/harness and record genuine capability differences under `evidence/v2/parity/`.
- [ ] T031 [US4] Run the fixed S14 ladder and staged mixed-room lifecycle, including suppression, both DEFER valves, preattention bypass, participant silence, operational error, restart, immutable receipt correlation, and no send-time reclassification.
- [ ] T032 [US4] Prove the integration branch contains no V1 contract consumer, compatibility bridge, obsolete hook/shim/config residue, registry/ledger field, or unproven runtime.
- [ ] T033 [US4] Run the full ordinary-path test/evaluation/boundary suite and assemble the final evidence index under `evidence/v2/README.md`.
- [ ] T034 [US3] Update current-state, stability, integration, security, evaluation, and migration documentation under `docs/` and `README.md` to describe only what the exact integrated evidence proves.
- [ ] T035 [US3] Present one atomic cutover commit and complete handoff packet for project-owner acceptance; do not merge a partial surface set or make a release/promotion claim.
- [ ] T036 [US3] After project-owner acceptance, merge the reviewed single atomic cutover PR to `main`, rerun all blocking checks on the resulting main commit, and record the PR, merge SHA, and results; package release and outward promotion remain separate decisions.

**Checkpoint**: Goal 2 is complete only when the accepted atomic V2 lifecycle is
merged to main and parity evidence is rerun against that exact merge. Package
release and promotion remain separate decisions.

## Dependencies and Parallel Opportunities

- `T001`–`T004` are sequential authorization/bootstrap gates.
- `T008` and `T009` may run in parallel after `T007`.
- `T013` depends on `T010`–`T012`; `T014` depends on the accepted `010` and
  `020` handoffs and may overlap `T013`.
- `T018`–`T021` may run in parallel only after each slice's complete dependency
  set is accepted.
- `T025` waits for `T024`; `T029` waits for an accepted `T028`.
- `T036` waits for explicit project-owner acceptance at `T035`; it merges the
  one assembled candidate and reverifies that exact main commit.
- No task authorizes two lanes to modify `schemas/v2/` or final integration
  files concurrently.

## Owner Handoff

Each activation and acceptance follows the handoff contract in `plan.md`.
Unchecked boxes are future work, not an “open conversation” ledger and not
evidence that a room message is owed a response.
