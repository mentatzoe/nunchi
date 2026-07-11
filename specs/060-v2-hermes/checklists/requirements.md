# Requirements Quality Checklist: V2 Hermes Harness

**Purpose**: Validate identity, participant-turn, multi-profile, and evidence
requirements before future Goal 2 execution
**Created**: 2026-07-11
**Feature**: [spec.md](../spec.md)

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
- [x] CHK017 Are all future tests, evals, evidence, docs, and plugin code assigned to ordinary repository paths? [Boundary, Plan §Ordinary Repository Targets]
- [x] CHK018 Is Goal 2 authorization stated as an external gate rather than a task checkbox? [Boundary, Control-Plane Boundary; tasks.md]

## Notes

- All requirements-quality items pass for planning readiness.
- This checklist does not assert that the Hermes implementation or live scenes exist.
