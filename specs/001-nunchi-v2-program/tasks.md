# Tasks: Nunchi V2 End-to-End Parity Program

**Input**: `spec.md`, `plan.md`, and `research.md` in this control-plane
directory

**Governance-bootstrap prerequisites (`T001`–`T003`)**: the accepted 2026-07-11
planning baseline and, where `T001` records implementation authority, Zoe's
durable external grant. These tasks establish repository governance facts only;
they do not implement V2 product behavior or make a slice ready.

**Product-delivery prerequisites (`T004` onward)**: a valid external
complete implementation-authority record enumerating exactly slices `010`
through `110`; one assigned
participant with a durable assignment source; per-recipient acceptance of every
required upstream handoff; zero CRITICAL/HIGH slice-analysis findings; an
isolated worktree; and immutable ordinary-path slice-activation evidence that
establishes `READY` before the assigned participant moves the slice to `ACTIVE`

**Accountable owner lane**: `v2-program-owner`

**Integration handoff**: `v2-integrator`

**Declaration reset observation**: 2026-07-11 — program `READY`, authority
`NOT_GRANTED`, assignment `UNASSIGNED`; the values below are live declarations,
not the dated baseline

**Program state**: `READY`

**Program implementation authority**: `GRANTED`

**Assigned program participant / source (declaration)**: Zoe — evidence/governance/assignments/zoe-v2-program-owner-2026-07-16.md

**2026-07-11 reset baseline — slice state**: every slice `010` through `110` is
`PLANNED`; all product tasks below are dormant. Live facts derive from the
umbrella and bound-slice declarations plus immutable activation/acceptance
records and append-only candidate/handoff attempts, not this dated statement or
its checkboxes.

Program progress is `PLANNING -> READY -> DELIVERY -> INTEGRATION ->
CUTOVER_ACCEPTED -> CUTOVER_VERIFIED`. Each slice progresses independently as
`PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY -> ACCEPTED`.
Implementation authority is the separate fact `NOT_GRANTED | GRANTED`.
`v2-integrator` owns slice-level acceptance for `010`–`100`; Zoe owns
acceptance for `110`. Slice-level `ACCEPTED` never attests acceptance by every
consumer: each dependent owner must record its own acceptance of each exact
upstream commit and packet before that dependent becomes `READY`.

## Format

`[ID] [P?] [Story] Description`

- `[P]` means the task may run concurrently after all explicit dependencies.
- Product changes target ordinary repository paths only.
- Slice task files are the executable work queues for their one owner; this
  umbrella list governs activation, handoff, assurance, and atomic integration.
- The assigned `v2-program-owner` coordinates sequencing and verifies evidence;
  apart from the explicit global-authority synchronization in T003, it does not
  write another slice's declaration or lifecycle evidence. Each
  assigned slice participant writes that slice's declarations, activation,
  candidate, and handoff records. The assigned `v2-integrator` records every
  slice acceptance/rejection; for `110`, Zoe remains the decision owner. Each
  dependent recipient writes its own upstream acceptance. Only the assigned program participant writes umbrella program
  declarations and program-state transitions.
- A paused post-convergence gate may resume its bound run only while the task
  graph is unchanged. If convergence appends tasks, retain activation, remain
  `ACTIVE`, and start a new bound run for that slice. If a completed handoff is
  rejected, append `REJECTED`, return to `ACTIVE`, and likewise start a new
  bound run; never resume the completed run.
- State and lane occupancy are derived from the umbrella and bound-slice
  declarations plus immutable activation/acceptance records and append-only
  candidate/handoff attempt streams. This planning file is not a central mutable
  registry and MUST NOT become runtime or conversation state.

## Slice binding and activation contract

Before any slice workflow, the assigned participant MUST invoke the exact bound
runner command below. The runner atomically allowlists and preflights slices
`010`–`110`, verifies the required planning artifacts and SpecKit resolver
result, binds the workflow process, pins the run input and workflow digest, and
does not modify `.specify/feature.json`. Resume occurs only by run ID. Neither
workflow creates or replaces a feature.

| Slice | Stable owner lane | Hard dependencies | Bound delivery command | Activation evidence |
|---|---|---|---|---|
| `010-v2-contract` | `v2-contract-owner` | none | `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract` | `evidence/v2/contract/slice-activation.md` |
| `020-v2-observation` | `v2-observation-owner` | `010` | `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation` | `evidence/v2/observation/slice-activation.md` |
| `030-v2-core-attention` | `v2-core-owner` | `010` | `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention` | `evidence/v2/attention/slice-activation.md` |
| `040-v2-participant-wake` | `v2-wake-owner` | `010`, `020`, `030` | `python3 scripts/run_slice_workflow.py run speckit specs/040-v2-participant-wake` | `evidence/v2/participant/slice-activation.md` |
| `050-v2-discord-transport` | `v2-transport-owner` | `010`, `020` | `python3 scripts/run_slice_workflow.py run speckit specs/050-v2-discord-transport` | `evidence/v2/discord-transport/slice-activation.md` |
| `060-v2-hermes` | `v2-hermes-owner` | `010`, `020`, `030`, `040` | `python3 scripts/run_slice_workflow.py run speckit specs/060-v2-hermes` | `evidence/v2/hermes/slice-activation.md` |
| `070-v2-claude-code` | `v2-claude-owner` | `010`, `020`, `030`, `040`, `050` | `python3 scripts/run_slice_workflow.py run speckit specs/070-v2-claude-code` | `evidence/v2/claude-code/slice-activation.md` |
| `080-v2-codex` | `v2-codex-owner` | `010`, `020`, `030`, `040`, `050` | `python3 scripts/run_slice_workflow.py run speckit specs/080-v2-codex` | `evidence/v2/codex/slice-activation.md` |
| `090-v2-channel-adapters` | `v2-adapters-owner` | `010`, `020`, `030`, `040` | `python3 scripts/run_slice_workflow.py run speckit specs/090-v2-channel-adapters` | `evidence/v2/adapters/slice-activation.md` |
| `100-v2-security-provenance` | `v2-security-owner` | `010`–`090` | `python3 scripts/run_slice_workflow.py run speckit specs/100-v2-security-provenance` | `evidence/v2/security/slice-activation.md` |
| `110-v2-parity-cutover` | `v2-integrator` | `010`–`100` | `python3 scripts/run_slice_workflow.py run speckit specs/110-v2-parity-cutover` | `evidence/v2/parity/slice-activation.md` |

The table contains only stable bindings. A slice's live state and assigned
participant/source come from its own declaration, immutable
activation/acceptance evidence, and append-only candidate/handoff attempts; they
are deliberately not mirrored here.

Every slice uses the same stable lifecycle evidence names beside its activation
file:

- immutable `slice-activation.md` records every accepted prerequisite and establishes
  `READY` before `ACTIVE` work;
- append-only `slice-candidate.md` records every exact candidate attempt that
  reached `CONVERGED`;
- append-only `slice-handoff.md` records every exact packet that reached
  `HANDOFF_READY` and every attributable `REJECTED` decision; and
- immutable `slice-acceptance.md` records the named slice-level acceptance that reached
  `ACCEPTED`.

On rejection, `v2-integrator` appends `REJECTED`, exact candidate commit,
acceptance owner, ISO date, durable decision reference, and recorder to the
existing handoff stream. The source participant returns its slice declaration
to `ACTIVE` and starts a new bound run because the handed-off run is complete.
If convergence adds tasks, the slice also remains `ACTIVE` and starts a new
bound run with the original activation. Only paused post-convergence fixes with
an unchanged task graph resume their run. No rejected or superseded entry is
deleted or rewritten.

For slice `110`, program tail evidence additionally lives at
`evidence/v2/parity/cutover-acceptance.md` and
`evidence/v2/parity/post-merge-verification.md`. These files are immutable
evidence for declarations, not a central status registry.

Each activation record MUST identify the assigned participant and durable
assignment source, complete all-eleven-slice authorization record, canonical
accepted dependency IDs, ordered `slice=full-sha` Dependency commits, matching
ordered `slice=consumer-owned-evidence-file` Dependency acceptance references,
zero-blocker analysis result, the green full V1 baseline result at the
activation commit (FR-020), worktree and branch, starting commit,
consumed interface versions, acceptance/evidence obligations, and exact
documentation-freshness scope. Only then may the slice declare `READY`, and
only its assigned participant may move it to `ACTIVE`. Each dependency
reference file lives under the consumer evidence directory, includes the
upstream ID in its filename, and attests consumer/upstream, matching commit,
accepting participant/date, exact packet record, and durable decision. Slice
`010` records all three dependency fields as `none`; slice `110` requires every
upstream slice to be `ACCEPTED`.

## Phase 1: Governance Bootstrap and Contract-Slice Readiness

**Purpose**: Independently document external authority and assign the program
participant as governance setup; then make only the contract slice independently
ready before product work.

- [x] T001 (Done 2026-07-16 — grant verified; aleph-vault decisions.md @ 554fc4f.) Confirm that Zoe's external V2 implementation decision exists and supplies the complete program, exact `010`–`110` scope, ISO date, full starting SHA, commissioned objective, and durable authority reference. This input check is independent of participant assignment and writes no repository authority or slice record.
- [x] T002 (Done 2026-07-16 — evidence/governance/assignments/zoe-v2-program-owner-2026-07-16.md and codex-session-2-v2-integrator-2026-07-16.md.) Have Zoe or the delegate named by a durable Zoe decision assign exactly one participant to `v2-program-owner` and exactly one participant to `v2-integrator`. Each assignment uses `<participant identity> — evidence/governance/assignments/<record>.md`, where the record contains `Assignee`, `Lane`, `Assigned by`, ISO `Assigned on`, and `Authority reference`, plus `Delegated by: Zoe` and `Delegation reference` for a non-Zoe assigner. The program participant writes only the umbrella assignment declaration; the integrator writes only slice `110`'s assignment declaration so it can serve as terminal acceptance recorder for slices `010`–`100` before integration begins. This early integrator assignment grants no implementation authority and does not make slice `110` ready or active. Do not staff other slices here: each remaining assignment is local and just-in-time. Reject a central assignment/state registry and do not create or pre-populate activation evidence.
- [x] T003 (Done 2026-07-16 — evidence/governance/v2-implementation-authorization.md incl. Recorded by; GRANTED synchronized across all eleven slices; governance + full baseline green.) After T001 and T002, have the assigned `v2-program-owner` durably copy Zoe's complete external grant into `evidence/governance/v2-implementation-authorization.md` with `Program: 001-nunchi-v2-program`, `Status: AUTHORIZED`, exact authorized slices `010` through `110`, `Authorized by: Zoe`, ISO authorization date, full starting SHA, commissioned objective, durable authority reference, `Recorded by: v2-program-owner`, and the required non-self-authorizing boundary sentence. Then verify it against Constitution 2.3.0, update the umbrella authority declaration to `GRANTED`, and mechanically synchronize only that same global `Program implementation authority: GRANTED` fact across all eleven slice declarations. This synchronization assigns no participant, activates no slice, changes no slice lifecycle state, and writes no slice evidence. Run `python3 scripts/check_governance.py --check-cli` and the full ordinary-path test baseline. Contract delivery is not blocked on staffing `020`–`100`.
- [ ] T004 Verify the existing durable assignment for `v2-contract-owner` (evidence/governance/assignments/); have that participant update only slice `010`'s local assignment declaration, run `python3 scripts/check_governance.py --task-manifest specs/010-v2-contract` for copy-ready task fields, and create `.worktrees/v2-contract/` on `v2/contract`. From that worktree start `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract`, retain its run ID, and use `python3 scripts/run_slice_workflow.py resume <run-id>` only after a paused post-convergence fix with an unchanged task graph. This persisted workflow is the sole delivery path; T005 and T006 are milestones inside it. T007 is the recipient's separate acceptance/rejection act after the run ends at `HANDOFF_READY`; rejection requires a new bound run. Have `v2-program-owner` verify first activation and advance only the umbrella from `READY` to `DELIVERY`.

**Checkpoint**: authority is external and explicitly recorded; the program and
contract and integrator participants have durable assignments; the integrator
can own terminal acceptance without activating slice `110`; later slice
staffing remains local and just-in-time; only contract work is active.

## Phase 2: Contract Foundation

**Purpose**: Land one product contract before dependents begin.

- [ ] T005 [US1] Within T004's bound workflow run, reach its `implement` step and execute `010-v2-contract/tasks.md` under `v2-contract-owner`, creating schemas under `schemas/v2/` and contract tests under `tests/v2/contract/`; never invoke the task skill outside that run.
- [ ] T006 [US1] Continue the same bound run after implementation. Have the assigned `v2-contract-owner` verify the exact candidate, interface registry `I-010A`–`I-010E`, bypass branch, host-only continuation projection, immutable receipt-stage union, commands, scene evidence, and documentation dispositions. If convergence appends tasks, retain activation and start a new bound run; otherwise pass convergence before appending the candidate attempt and declaring `CONVERGED`, then pass documentation freshness and handoff before appending the packet attempt and declaring `HANDOFF_READY`. Resume only a paused post-convergence gate with an unchanged task graph. Have `v2-program-owner` verify without authoring slice evidence.
- [ ] T007 [US1] Have the assigned `v2-contract-owner` publish the exact `010` commit, interface versions, and packet for every declared downstream lane. The already-assigned `v2-integrator` reviews it now; on acceptance, that integrator writes `evidence/v2/contract/slice-acceptance.md` and the assigned `v2-contract-owner` declares slice `010` `ACCEPTED`. Each other dependent owner records its own consumer acceptance only after that lane is assigned during its just-in-time readiness work; terminal slice acceptance implies none of those consumer decisions. Have `v2-program-owner` verify the topology only.

**Checkpoint**: one accepted V2 contract commit exists; no consumer has invented
a local variant.

## Phase 3: Observation and Core Attention

**Purpose**: Build the two independent foundations against the accepted
contract.

- [ ] T008 [P] [US1] Verify the existing durable assignment for `v2-observation-owner` (evidence/governance/assignments/); have that participant update only slice `020`'s assignment, independently accept and record the exact `010` dependency, and create `.worktrees/v2-observation/` on `v2/observation`. There start `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation` and retain its bound run ID; T010 is an owner-controlled milestone in that run, while T012 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness without writing slice evidence.
- [ ] T009 [P] [US1] Verify the existing durable assignment for `v2-core-owner` (evidence/governance/assignments/); have that participant update only slice `030`'s assignment, independently accept and record the exact `010` dependency, and create `.worktrees/v2-core-attention/` on `v2/core-attention`. There start `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention` and retain its bound run ID; T011 is an owner-controlled milestone in that run, while T012 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness without writing slice evidence.
- [ ] T010 [US2] Within slice `020`'s bound run, complete implementation, verify that the candidate produces `I-020A ObservationProviderV2@1` with truthful immutable observation stages and no social registry, then continue that same run through convergence, documentation freshness, and handoff evidence to `HANDOFF_READY`. Have `v2-program-owner` verify rather than author records.
- [ ] T011 [US2] Within slice `030`'s bound run, complete implementation, verify `I-030A AttentionEngineV2@1`, one participant-shaped judgment, separate bypass/`ERROR`, host-only continuation secrecy, immutable attention stages, exact CLI process behavior, and the dual-valve transition, then continue that same run through convergence, documentation freshness, and handoff evidence to `HANDOFF_READY`. Have `v2-program-owner` verify rather than author records.
- [ ] T012 [US2] Have the assigned owners publish the exact commits, interface versions, packets, and documentation dispositions/deltas from `020` and `030` for every declared downstream lane. The already-assigned `v2-integrator` reviews them now; on acceptance, that integrator writes the applicable `evidence/v2/observation/slice-acceptance.md` or `evidence/v2/attention/slice-acceptance.md`, and the source owner declares its slice `ACCEPTED`. Each other dependent records its consumer acceptance only after its lane is assigned during just-in-time readiness. Have `v2-program-owner` verify the records only.

**Checkpoint**: observation and pre-attention are separately owned, independently
green, and contract-compatible.

## Phase 4: Participant Wake and Shared Discord Transport

**Purpose**: Complete the common participant lifecycle and Discord event source.

- [ ] T013 [P] [US2] After accepted `010`, `020`, and `030` packets exist, Verify the existing durable assignment for `v2-wake-owner` (evidence/governance/assignments/); have that participant update only slice `040`'s assignment, independently record every dependency acceptance, and create `.worktrees/v2-participant-wake/` on `v2/participant-wake`. There start `python3 scripts/run_slice_workflow.py run speckit specs/040-v2-participant-wake` and retain its bound run ID; T015 is an owner-controlled milestone in that run, while T017 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness only.
- [ ] T014 [P] [US2] After accepted `010` and `020` packets exist, Verify the existing durable assignment for `v2-transport-owner` (evidence/governance/assignments/); have that participant update only slice `050`'s assignment, independently record every dependency acceptance, and create `.worktrees/v2-discord-transport/` on `v2/discord-transport`. There start `python3 scripts/run_slice_workflow.py run speckit specs/050-v2-discord-transport` and retain its bound run ID; T016 is an owner-controlled milestone in that run, while T017 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness only.
- [ ] T015 [US3] Within slice `040`'s bound run, complete implementation and verify `I-040A ParticipantTurnHostV2@1`, advice-free bypass, immutable participant-host stages, truthful expansion, normal act-or-silence, and no admission meta-answer or send re-gate; then continue the same run through convergence, documentation freshness, and handoff to `HANDOFF_READY`. Have `v2-program-owner` verify only.
- [ ] T016 [US3] Within slice `050`'s bound run, complete implementation and verify `I-050A DiscordEventSourceV2@1`, immutable transport stages, deterministic handling limited to exact transport non-events, continuity, and native provenance; then continue the same run through convergence, documentation freshness, and handoff to `HANDOFF_READY`. Have `v2-program-owner` verify only.
- [ ] T017 [US3] Have the assigned source owners publish the exact `040` and `050` commits, packets, validated owned-doc updates, and README deltas for their declared downstream lanes. The already-assigned `v2-integrator` reviews them now; on acceptance, that integrator writes the applicable `evidence/v2/participant/slice-acceptance.md` or `evidence/v2/discord-transport/slice-acceptance.md`, and the source owner declares its slice `ACCEPTED`. Each other dependent records its consumer acceptance only after its lane is assigned during just-in-time readiness. Have `v2-program-owner` verify the records only.

**Checkpoint**: common wake and shared Discord transport interfaces are accepted;
surface integrations may begin only where their full dependency sets are met.

## Phase 5: Surface Integrations

**Purpose**: Migrate independently owned consumers in parallel without contract
or shared-file drift.

- [ ] T018 [P] [US3] Verify the existing durable assignment for `v2-hermes-owner` (evidence/governance/assignments/); have that participant update only slice `060`'s assignment, independently record every dependency acceptance, and create `.worktrees/v2-hermes/` on `v2/hermes`. There start `python3 scripts/run_slice_workflow.py run speckit specs/060-v2-hermes`, retain its bound run ID, and treat T022 and T023 as owner-controlled milestones in that run; T024 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness only.
- [ ] T019 [P] [US3] Verify the existing durable assignment for `v2-claude-owner` (evidence/governance/assignments/); have that participant update only slice `070`'s assignment, independently record every dependency acceptance, and create `.worktrees/v2-claude-code/` on `v2/claude-code`. There start `python3 scripts/run_slice_workflow.py run speckit specs/070-v2-claude-code`, retain its bound run ID, and treat T022 and T023 as owner-controlled milestones in that run; T024 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness only.
- [ ] T020 [P] [US3] Verify the existing durable assignment for `v2-codex-owner` (evidence/governance/assignments/); have that participant update only slice `080`'s assignment, independently record every dependency acceptance, and create `.worktrees/v2-codex/` on `v2/codex`. There start `python3 scripts/run_slice_workflow.py run speckit specs/080-v2-codex`, retain its bound run ID, and treat T022 and T023 as owner-controlled milestones in that run; T024 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness only.
- [ ] T021 [P] [US3] Verify the existing durable assignment for `v2-adapters-owner` (evidence/governance/assignments/); have that participant update only slice `090`'s assignment, independently record every dependency acceptance, and create `.worktrees/v2-channel-adapters/` on `v2/channel-adapters`. There start `python3 scripts/run_slice_workflow.py run speckit specs/090-v2-channel-adapters`, retain its bound run ID, and treat T022 and T023 as owner-controlled milestones in that run; T024 is separate recipient acceptance after handoff. Have `v2-program-owner` verify readiness only.
- [ ] T022 [US3] Verify every surface candidate uses the accepted interfaces, preserves preattention bypass and staged-receipt semantics, removes V1 lifecycle residue, proves direct act-or-silence behavior, and records honest unavailable platform facts.
- [ ] T023 [US4] Within each surface slice's bound run, finish implementation, verify installed-runtime commit/package/config/process provenance and a live schema-2 probe under `evidence/v2/provenance/`, then continue that same run through convergence, documentation freshness, and handoff to `HANDOFF_READY`. Have `v2-program-owner` verify rather than author records.
- [ ] T024 [US3] Have each assigned surface owner publish its exact commit, packet, scene matrix, evidence paths, documentation dispositions/validation/deltas, and limitations. The already-assigned `v2-integrator` reviews each now; on acceptance, that integrator writes the exact applicable `slice-acceptance.md`, and the source owner declares its slice `ACCEPTED`. Have `v2-program-owner` verify records only; this task does not act for `v2-security-owner`, whose slice `100` readiness work begins only at T025.

**Checkpoint**: every in-tree consumer has an accepted candidate handoff; main
still has not entered a mixed V1/V2 state.

## Phase 6: Blocking Security and Provenance Assurance

**Purpose**: Audit the exact integrated candidate rather than plans or local
claims.

- [ ] T025 [US4] After accepted commits from `010`–`090`, Verify the existing durable assignment for `v2-security-owner` (evidence/governance/assignments/); have that participant update only slice `100`'s assignment, independently review every required upstream packet, record the ordered full-SHA and consumer-owned acceptance references, and create `.worktrees/v2-security-provenance/` on `v2/security-provenance`. There start `python3 scripts/run_slice_workflow.py run speckit specs/100-v2-security-provenance`, retain its bound run ID, and treat T026, T027, and the owner-controlled handoff portion of T028 as milestones in that run; T028's acceptance/rejection tail is the recipient's separate act after handoff. Have `v2-program-owner` verify readiness only.
- [ ] T026 [US4] Require tested mitigation for each threat by default; record any documentation-only residual risk only with Zoe's explicit acceptance in `docs/security/threat-model-v2.md` and the exact corresponding `evidence/v2/security/manifest.json` record.
- [ ] T027 [US4] Verify governed suppression, advice isolation, classifier projection secrecy, preattention bypass, immutable receipt-stage ownership, credentials, send safety, recoverability, restart behavior, and installed-runtime provenance against scenes `S01`–`S16`.
- [ ] T028 [US4] Within slice `100`'s bound run, finish implementation and pass convergence for the exact blocking-assurance candidate, then continue that same run through documentation freshness and handoff to `HANDOFF_READY`. Present the report, audited commit set, documentation dispositions/deltas, limitations, and rejection list to `v2-integrator`. Only that integrator writes immutable slice acceptance or appends rejection; on rejection, `v2-security-owner` declares `ACTIVE` and starts a new bound run rather than resuming the completed one. Have `v2-program-owner` verify only, and do not waive a failed control, stale docs, or rewritten attempt.

**Checkpoint**: the candidate either has an accepted blocking assurance packet or
returns to its named owner; parity integration does not begin on a rejection.

## Phase 7: Parity Assembly and Atomic Cutover

**Purpose**: Establish the final success mode across all surfaces and land it
atomically.

- [ ] T029 [US3] After every slice `010`–`100` is `ACCEPTED`, verify the existing durable `v2-integrator` assignment from T002, independently record every exact accepted commit/reference for slice `110`, and create `.worktrees/v2-integration/` on `integration/v2`. There start `python3 scripts/run_slice_workflow.py run speckit specs/110-v2-parity-cutover`, retain its bound run ID, and treat T030–T034 plus the owner-controlled handoff portion of T035 as milestones in that sole delivery/integration run. T035's Zoe decision and program copy occur only after that run ends at `HANDOFF_READY`. Have `v2-program-owner` verify first activation and advance only the umbrella declaration to `INTEGRATION`.
- [ ] T030 [US4] Run the common replay corpus and acceptance scenes `S01`–`S16` across every applicable adapter/harness and record genuine capability differences under `evidence/v2/parity/`.
- [ ] T031 [US4] Run the fixed S14 ladder and staged mixed-room lifecycle, including suppression, both DEFER valves, preattention bypass, participant silence, operational error, restart, immutable receipt correlation, and no send-time reclassification.
- [ ] T032 [US4] Prove the integration branch contains no V1 contract consumer, compatibility bridge, obsolete hook/shim/config residue, registry/ledger field, or unproven runtime.
- [ ] T033 [US4] Run the full ordinary-path test/evaluation/boundary suite and assemble the final evidence index under `evidence/v2/README.md`.
- [ ] T034 [US3] Have the assigned `v2-integrator` execute every exact `UPDATE` row in slice `110`'s §Documentation Impact and Freshness matrix, including `README.md` and every named root/shared/contract/evaluation/component/security/release/installed-surface file; reconcile every accepted upstream delta, preserve truthful verification-pending wording, and prepare exact validation results for links, Mermaid, examples, commands, install/version claims, and truthfulness tests against the candidate. This completes ordinary implementation inputs only; it does not write lifecycle evidence or advance state. Have `v2-program-owner` verify scope and results without authoring slice artifacts.
- [ ] T035 [US3] Within slice `110`'s bound run, finish implementation and pass convergence, documentation freshness, and handoff to `HANDOFF_READY` before presenting that exact packet to Zoe. Zoe alone owns acceptance or rejection. The assigned `v2-integrator` durably copies Zoe's decision into immutable slice acceptance or the append-only rejection stream, then declares `ACCEPTED` or returns to `ACTIVE`. Rejection requires a new bound slice-`110` run and never resumes the completed run. On acceptance only, `v2-program-owner` copies the decision into program cutover acceptance and advances the umbrella to `CUTOVER_ACCEPTED`; the program owner writes no slice evidence. Do not erase an attempt, merge a partial set, or make a release/promotion claim.
- [ ] T036 [US3] After Zoe's recorded acceptance, have the assigned `v2-integrator` merge the reviewed single atomic cutover PR to `main`, retaining truthful `CUTOVER_ACCEPTED`/verification-pending docs. Rerun every blocking check on the resulting exact main commit, finalize and validate verified-current documentation, and land one docs/evidence-only follow-up that changes no product source, schema, runtime, or behavior. Its `evidence/v2/parity/post-merge-verification.md` records `Program`, `Status`, full `Accepted candidate commit`, full `Merged candidate commit`, `Main ref: refs/heads/main`, matching full `Main commit`, ISO `Verified on`, passing `Verification commands / results`, exact `Evidence paths`, `Documentation freshness: PASS`, and full `Documentation commit`. Have `v2-program-owner` independently verify that complete record and advance only the umbrella program declaration to `CUTOVER_VERIFIED`. Package release and outward promotion remain separate decisions.

**Checkpoint**: the V2 program reaches `CUTOVER_VERIFIED` only when the accepted
atomic lifecycle is merged to main and parity evidence is rerun against that
exact merge, with final current-state documentation validated in the same docs/
evidence-only follow-up. Package release and promotion remain separate decisions.

## Dependencies and Parallel Opportunities

- `T001` and `T002` are independent governance prerequisites: assignment may
  precede authority during planning. `T003` requires both and performs only the
  authorized global-fact synchronization and verification; none implements
  product behavior. `T004` is the first product-delivery activation and requires
  authority plus every contract-slice readiness fact.
- `T008` and `T009` may run in parallel after `T007`.
- `T013` depends on `T010`–`T012`; `T014` depends on the accepted `010` and
  `020` handoffs and may overlap `T013`.
- `T018`–`T021` may run in parallel only after each slice's complete dependency
  set is accepted.
- `T025` waits for `T024`; `T029` waits for an accepted `T028`.
- `T036` waits for Zoe's explicit acceptance at `T035`; it merges the
  one assembled candidate and reverifies that exact main commit.
- No task authorizes two lanes to modify `schemas/v2/` or final integration
  files concurrently.

## Owner Handoff

Each activation and acceptance follows the handoff contract in `plan.md`.
Unchecked boxes are future work, not an “open conversation” ledger and not
evidence that a room message is owed a response.
