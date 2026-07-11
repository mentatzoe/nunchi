# Requirements Quality Checklist: V2 Hermes Harness

**Purpose**: Validate identity, participant-turn, multi-profile, lifecycle, and
evidence requirements before authorized slice implementation
**Created**: 2026-07-11
**Slice specification**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Are exact profile identity, observation, attention routing, participant turn, continuation, receipts, and provenance all specified? [Completeness, Spec §FR-001–FR-013]
- [x] CHK002 Are all canonical consumed interfaces named with registry IDs and versions? [Completeness, Spec §Interface Summary]
- [x] CHK003 Is the absence of a Hermes-owned public interface explicit? [Scope, Spec §Control-Plane Boundary]

## Requirement Clarity and Consistency

- [x] CHK004 Is exact actor binding clearly separated from loose same-class names and aliases? [Clarity, Spec §FR-001; US1]
- [x] CHK005 Are classifier disposition, preattention bypass, effective routing, host invocation, participant outcome, and immutable receipt-stage ownership kept distinct throughout? [Consistency, Spec §FR-003–FR-010]
- [x] CHK006 Is “one normal participant turn” defined to allow message, reaction/tool action, or silence while keeping meta-answer failure evaluation-only? [Clarity, Spec §FR-005–FR-007]
- [x] CHK007 Do restart/recoverability requirements agree with the rule that unproved surfaces cannot socially suppress? [Consistency, Spec §FR-012; Edge Cases]

## Acceptance Criteria Quality

- [x] CHK008 Can invocation-count and no-second-judgment criteria be measured without inspecting planning completion? [Measurability, Spec §SC-002]
- [x] CHK009 Are every bypass, classifier, host, participant, and transport stage independently observable in evidence? [Acceptance Criteria, Spec §SC-003]
- [x] CHK010 Does every live parity claim require exact installed runtime and interface provenance? [Acceptance Criteria, Spec §SC-006]

## Scenario and Edge-Case Coverage

- [x] CHK011 Are same-class alias collision and cross-profile state leakage addressed? [Coverage, Spec §US1; Edge Cases]
- [x] CHK012 Are SUPPRESS, both DEFER sources, WAKE, zero-call PREATTENTION_BYPASS, operational error, advice, participant silence, and evaluation-only meta-answer failure covered without a runtime prose filter? [Coverage, Spec §US2]
- [x] CHK013 Are later hearing, restart, shared Discord, and Hermes Telegram scenarios defined? [Coverage, Spec §US3]
- [x] CHK014 Is bound context expansion across multiple profiles included as a security edge case? [Coverage, Spec §FR-008–FR-009]

## Dependencies, Ownership, and Boundary

- [x] CHK015 Are dependencies `010`–`040` and consumers `100`/`110` consistent across spec, plan, and tasks? [Dependency]
- [x] CHK016 Does `v2-hermes-owner` own only Hermes-specific paths while shared interface owners retain their files? [Ownership, Plan §Integration Strategy]
- [x] CHK017 Are all implementation tests, evals, evidence, docs, and plugin code assigned to ordinary repository paths? [Boundary, Plan §Ordinary Repository Targets]
- [x] CHK018 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/060-v2-hermes`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010`–`040` handoffs, active `v2-hermes-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/hermes/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox while tasks remain dormant in `PLANNED`? [Boundary, Control-Plane Boundary; tasks.md]
- [x] CHK019 Does documentation freshness inventory every exact known path, require new/existing Hermes operator and patch docs to `UPDATE`, route shared/current `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

- [x] CHK020 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- All requirements-quality items pass for planning readiness.
- This checklist does not assert that the Hermes implementation or live scenes exist.
