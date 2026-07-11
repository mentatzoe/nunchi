# Requirements Quality Checklist: V2 Claude Code Harness

**Purpose**: Validate Claude hearing, model-nuance, participant-turn, and live
provenance requirements before future implementation
**Created**: 2026-07-11
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Are all nine canonical consumed interfaces named with exact IDs and versions? [Completeness, Spec §Interface Summary]
- [x] CHK002 Are reactive transport, exact identity, observation, attention, participant turn, continuation, receipts, and provenance all specified? [Completeness, Spec §FR-001–FR-016]
- [x] CHK003 Is the absence of any Claude-owned public interface explicit? [Scope, Control-Plane Boundary]

## Requirement Clarity and Consistency

- [x] CHK004 Is reactive no-polling delivery distinguished from unsupported cold-start wake? [Clarity, Spec §FR-003, §FR-012]
- [x] CHK005 Are exact self binding and loose Claude/class names consistently separated? [Consistency, Spec §FR-004]
- [x] CHK006 Is the prohibition on deterministic addressee/resolution/relevance rules exhaustive enough to cover the Station failure? [Clarity, Spec §FR-007]
- [x] CHK007 Are attention advice, room facts, participant instruction, and participant output kept as separate authority classes? [Consistency, Spec §FR-009]

## Acceptance Criteria Quality

- [x] CHK008 Can bot-hearing parity be measured against representable `I-050A` facts? [Measurability, Spec §SC-001]
- [x] CHK009 Can one engine invocation, ordinary-trigger one logical classifier call, trusted-bypass zero classifier calls, and no-send-regate behavior be objectively counted? [Measurability, Spec §SC-003]
- [x] CHK010 Does installed-runtime provenance enumerate every plugin/hook/package/model/config component needed to support a live claim? [Acceptance Criteria, Spec §SC-006]

## Scenario and Edge-Case Coverage

- [x] CHK011 Are other-bot, exact-self, no-polling, inactive-session, and patch-drift scenarios covered? [Coverage, Spec §US1; Edge Cases]
- [x] CHK012 Are referential mention, other addressee, apparent resolution, soft class address, and ambiguity scars covered? [Coverage, Spec §US2]
- [x] CHK013 Are SUPPRESS, WAKE, both DEFER sources, PREATTENTION_BYPASS, error, advice, expansion, direct action, silence, and evaluation-only meta-answer failure covered without a runtime prose filter? [Coverage, Spec §US3]
- [x] CHK014 Are later-hearing, restart, nonexistent-evidence advice, and cross-room handle replay addressed? [Coverage, Spec §FR-011–FR-012; Edge Cases]

## Dependencies, Ownership, and Boundary

- [x] CHK015 Are dependencies `010`–`050` and assurance/parity consumers consistent across all four artifacts? [Dependency]
- [x] CHK016 Does the Claude lane own only Claude-specific paths while transport/foundation owners retain their interfaces? [Ownership, Plan §Integration Strategy]
- [x] CHK017 Are all future product, test, eval, evidence, and documentation artifacts assigned to ordinary paths? [Boundary, Plan §Ordinary Repository Targets]
- [x] CHK018 Is Goal 2 authorization external and explicit rather than implied by completed planning? [Boundary, Control-Plane Boundary; tasks.md]
- [x] CHK019 Does CC-01 have an explicit installed reactive bot-hearing/no-polling evidence task rather than only an index entry? [Coverage, Plan §CC-01; tasks.md]
- [x] CHK020 Does one manifest resolve CC-01 through CC-06 and common S IDs to exact evidence while meta-answer grading remains post-hoc and outside runtime? [Traceability, Spec §FR-014; Plan §Acceptance Scenes]
- [x] CHK021 Do CC-03/CC-04 prove trusted `PREATTENTION_BYPASS` makes zero classifier calls, invokes one act-or-silence turn without fabricated social data, and preserves immutable singly owned request-correlated receipt stages? [Contract, Spec §FR-006, FR-008, FR-016]

## Notes

- All requirements-quality items pass for planning readiness.
- Passing this checklist does not establish that Claude Code currently implements V2.
