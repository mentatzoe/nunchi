# Specification Quality Checklist: V2 Participant Wake

**Purpose**: Validate that participant-host requirements are complete, direct,
bounded, lifecycle-safe, and free of duplicate social judgment

**Created**: 2026-07-11

**Slice specification**: [spec.md](../spec.md)

## Scope and Ownership

- [x] CHK001 Is the `PLANNED` slice and its `NOT_GRANTED` program authority distinguished explicitly from current V1 implementation truth, with tasks `DORMANT` until `READY`? [Clarity, Spec §Control-Plane Boundary]
- [x] CHK002 Are all shared-host product artifacts assigned to ordinary paths only? [Consistency, Spec §Control-Plane Boundary, FR-016]
- [x] CHK003 Is `v2-wake-owner` the sole I-040A owner with complete 010/020/030 dependencies and 060–110 feeds? [Completeness, Spec §Interface Summary]
- [x] CHK004 Are native/surface integrations, attention judgment, schemas, assurance, and final cutover assigned to other owner lanes explicitly? [Coverage, Spec §Explicit Exclusions]

## Routing and Participant Requirements

- [x] CHK005 Are invocation cardinality and wake source requirements defined for SUPPRESS, WAKE, DEFER, PREATTENTION_BYPASS, ERROR_FALLBACK, and NO_WAKE override, including zero classifier calls on bypass? [Clarity, Spec §FR-002–FR-003]
- [x] CHK006 Are compact packet facts, independent budgets, relation/evidence priority, and delivered-fact receipts complete? [Completeness, Spec §FR-004–FR-005]
- [x] CHK007 Are advice trust, grounding, reply-prose, and instruction-authority boundaries unambiguous? [Security, Spec §FR-006]
- [x] CHK008 Does the direct act-or-silence requirement exclude an intermediate admission answer and include message, reaction, tool, and no-send outcomes? [Completeness, Spec §FR-007–FR-009]

## Expansion, Send, and Receipt Requirements

- [x] CHK009 Are continuation binding, caps, order, exact dedupe, coverage, and no-second-judgment behavior specified? [Completeness, Spec §FR-010]
- [x] CHK010 Is operational send safety distinguished from social reclassification and per-trigger permission state? [Clarity, Spec §FR-011]
- [x] CHK011 Is this owner limited to an immutable participant-host stage for wake source, packet, expansion, participant, host-send, and error facts without mutating observation/attention or claiming transport delivery? [Consistency, Spec §FR-012]
- [x] CHK012 Are unavailable expansion/send capabilities and unknown participant outcomes represented honestly? [Coverage, Spec §Edge Cases, Assumptions]

## Scenario and Acceptance Quality

- [x] CHK013 Do scenarios cover all common S03/S06/S07/S09/S10/S15/S16 outcomes, meta-answer failure, advice red-team, and continuation attacks? [Traceability, Spec §User Scenarios & Testing]
- [x] CHK014 Can every success criterion be measured by invocation count, schema-valid packet, result classification, fetch rejection, call graph, handoff, or boundary result? [Measurability, Spec §SC-001–SC-009]
- [x] CHK015 Is it explicit that local evidence feeds slices 060–100 while 110 alone owns final parity and atomic cutover? [Dependency, Spec §Interface Summary, Explicit Exclusions]
- [x] CHK016 Does documentation freshness inventory every exact known affected path, require the participant-guide `UPDATE`, route shared/downstream `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK017 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/040-v2-participant-wake`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010-v2-contract`, `020-v2-observation`, and `030-v2-core-attention`, active `v2-wake-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/participant/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox? [Lifecycle, tasks.md §Slice activation]

- [x] CHK018 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- All requirement-quality checks pass for the planning text. They do not claim
  that I-040A or any harness binding has been implemented.
