# Requirements Quality Checklist: V2 Claude Code Harness

**Purpose**: Validate Claude hearing, model-nuance, participant-turn, and live
provenance requirements before authorized slice implementation
**Created**: 2026-07-11
**Slice specification**: [spec.md](../spec.md)

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
- [x] CHK017 Are all implementation, test, eval, evidence, and documentation artifacts assigned to ordinary paths? [Boundary, Plan §Ordinary Repository Targets]
- [x] CHK018 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/070-v2-claude-code`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010`–`050` handoffs, active `v2-claude-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/claude-code/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox while tasks remain dormant in `PLANNED`? [Boundary, Control-Plane Boundary; tasks.md]
- [x] CHK019 Does CC-01 have an explicit installed reactive bot-hearing/no-polling evidence task rather than only an index entry? [Coverage, Plan §CC-01; tasks.md]
- [x] CHK020 Does one manifest resolve CC-01 through CC-06 and common S IDs to exact evidence while meta-answer grading remains post-hoc and outside runtime? [Traceability, Spec §FR-014; Plan §Acceptance Scenes]
- [x] CHK021 Do CC-03/CC-04 prove trusted `PREATTENTION_BYPASS` makes zero classifier calls, invokes one act-or-silence turn without fabricated social data, and preserves immutable singly owned request-correlated receipt stages? [Contract, Spec §FR-006, FR-008, FR-016]
- [x] CHK022 Does documentation freshness inventory every exact known path, require all new/existing Claude and patch docs to `UPDATE`, route shared/current `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

- [x] CHK023 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- All requirements-quality items pass for planning readiness.
- Passing this checklist does not establish that Claude Code currently implements V2.
