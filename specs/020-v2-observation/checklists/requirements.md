# Specification Quality Checklist: V2 Observation

**Purpose**: Validate the completeness and clarity of observation,
continuation, recoverability, lifecycle, and downstream-comparison requirements

**Created**: 2026-07-11

**Slice specification**: [spec.md](../spec.md)

## Scope and Ownership

- [x] CHK001 Is the `PLANNED` slice and its `GRANTED` program authority distinguished explicitly from current V1 implementation truth, with authorization itself granting neither `READY` nor `ACTIVE` and tasks remaining `DORMANT` until `READY`? [Clarity, Spec §Control-Plane Boundary]
- [x] CHK002 Are all product targets ordinary paths and all SpecKit-path product artifacts forbidden? [Consistency, Spec §Control-Plane Boundary, FR-014]
- [x] CHK003 Is `v2-observation-owner` the sole owner, with 010 and downstream 040–110 file boundaries and handoffs stated? [Completeness, Spec §Interface Summary, Explicit Exclusions]
- [x] CHK004 Are attention judgment, participant invocation, send safety, social ledgers, and release decisions excluded? [Coverage, Spec §Explicit Exclusions]

## Identity and Native-Fact Requirements

- [x] CHK005 Is exact self attestation distinguished clearly from loose names and aliases at I-020A and required downstream bindings? [Clarity, Spec §FR-002]
- [x] CHK006 Are native order, actor identity, actor-targeted mentions, distinct room-wide mentions, replies, threads, reactions, membership, and unavailable facts covered? [Completeness, Spec §FR-003]
- [x] CHK007 Are the only three deterministic transport-hygiene cases enumerated without a semantic catch-all? [Clarity, Spec §FR-004–FR-005]

## Budget, Continuation, and Continuity Requirements

- [x] CHK008 Are hard event/byte limits, relation priority, nearby fill, truncation, gaps, and coverage fields specified consistently? [Completeness, Spec §FR-006–FR-007]
- [x] CHK009 Are continuation binding, directions, caps, cursor behavior, order, exact dedupe, and page coverage defined? [Completeness, Spec §FR-008–FR-009]
- [x] CHK010 Is outcome-neutral bounded retention distinguished from a roster, registry, or social memory? [Clarity, Spec §FR-010]
- [x] CHK011 Are reference restart-safe results separated from each downstream surface's required recoverability and suppression-eligibility proof? [Measurability, Spec §FR-011]

## Scenario and Acceptance Quality

- [x] CHK012 Do scenarios cover alias collision, native structure, unresolved relations, queued post-trigger events, continuation attacks, restart gaps, and identical-content distinct events? [Coverage, Spec §User Scenarios & Testing, Edge Cases]
- [x] CHK013 Is the shared/reference comparator contract defined around equivalent facts and budgets while reserving real-surface and final parity claims for downstream slices and 110? [Consistency, Spec §FR-012]
- [x] CHK014 Can each slice success criterion be measured through shared/reference deterministic results without citing unit or simulated evidence as real-surface parity? [Acceptance Criteria, Spec §SC-001–SC-008]
- [x] CHK015 Are the accepted 010 dependency, I-020A output, 040–110 handoffs, and evidence obligations all traceable without making 020 the final integrator? [Dependency, Spec §Interface Summary, FR-001, FR-013]
- [x] CHK016 Is the observation owner limited to one immutable request-correlated observation stage, leaving future attention/participant/transport facts explicitly unknown? [Ownership, Spec §FR-015]
- [x] CHK017 Do aggregate evidence records require canonical scene IDs and an exact README scene-to-record manifest? [Traceability, Plan §Acceptance Scenes and Evidence]
- [x] CHK018 Does documentation freshness inventory every exact known affected path, require the observation-guide `UPDATE`, route global and downstream `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK019 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/020-v2-observation`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010-v2-contract`, active `v2-observation-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/observation/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox? [Lifecycle, tasks.md §Slice activation]

- [x] CHK020 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]
- [x] CHK021 Does the task graph explicitly require slice 020's own stdlib runtime-validation adapter to run over and account for the complete identical attempt-6 corpus revision `bff6b463a44c1b9066fc654691042f9550da6c64`, including all seven runtime-adapter-only semantic/relational classes, before 020 handoff? [Dependency, evidence/v2/contract/handoff.md §Corpus revision and downstream adapter obligation]

## Notes

- All requirement-quality items currently pass. Checked items validate the
  planning text only and do not claim an observation provider exists.
