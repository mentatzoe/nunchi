# Specification Quality Checklist: V2 Parity and Atomic Cutover

**Purpose**: Validate that the future Goal 2 final-integration requirements are
complete, unambiguous, measurable, traceable, acyclic, and constitutionally
bounded before analysis.

**Created**: 2026-07-11

**Feature**: [spec.md](../spec.md)

## Content and Boundary Quality

- [x] CHK001 Is Goal 1 explicitly planning-only and is all assembly, probing, live-room, documentation, and release work reserved for separately authorized Goal 2? [Clarity, Spec §Control-Plane Boundary]
- [x] CHK002 Are all implementation, tests, evals, evidence, scripts, and product/release docs assigned to ordinary repository paths? [Completeness, Spec §FR-020]
- [x] CHK003 Is the final integrator prohibited from redesigning owned interfaces, accepting risk, adding a V1 bridge, or doing promotion? [Scope, Spec §Explicit Exclusions]
- [x] CHK004 Is `v2-integrator` the sole owner while upstream semantic ownership and Zoe decisions remain explicit? [Consistency, Spec §Interface Summary]

## Dependency and Interface Quality

- [x] CHK005 Are all dependencies `010` through `100` explicit and required before candidate assembly? [Completeness, Spec §FR-001]
- [x] CHK006 Are the exact canonical interfaces `I-010A`–`I-050A`, component handoffs `060`–`090`, and blocking slice-`100` assurance packet named without creating another interface family? [Traceability, Spec §Interface Summary]
- [x] CHK007 Are the candidate manifest, parity evidence index, and release-readiness boundary defined as integration artifacts with clear consumers and ordinary authorities? [Traceability, Spec §FR-019]
- [x] CHK008 Is the handoff manifest requirement measurable across commit, interface, package/schema/config, commands, evidence, provenance, and limitations? [Measurability, Spec §FR-002]
- [x] CHK009 Does the spec return semantic conflicts to upstream owners without making them reverse dependencies on slice `110`? [Consistency, Spec §FR-006]
- [x] CHK010 Is `110` clearly the final sink, with no output consumed by `010`–`100` and therefore no dependency cycle? [Dependency, Spec §FR-019]

## Atomic Cutover Requirement Quality

- [x] CHK011 Is every in-tree core, CLI, transport, adapter, and harness included in the atomic V2 cutover requirement? [Coverage, Spec §FR-003]
- [x] CHK012 Are V1 bridges, mixed requests, legacy move routing, retired hooks/shims, and second social classifiers all explicitly rejected? [Completeness, Spec §FR-004, FR-007]
- [x] CHK013 Is temporary mixed integration state confined to a non-releaseable worktree and barred from main? [Clarity, Spec §FR-005]
- [x] CHK014 Does the spec require the V1 stability/upgrade claim to change in the same atomic cutover? [Consistency, Spec §User Story 1]

## Parity and Scenario Coverage

- [x] CHK015 Are all shared acceptance scenes S01-S16 required and traceable to applicable surfaces/evidence? [Coverage, Spec §FR-008]
- [x] CHK016 Is parity defined across normalized observation, injected-validated-decision routing, participant factual availability, and receipts without a deterministic social-verdict oracle? [Clarity, Spec §FR-009]
- [x] CHK017 Are unavailable native platform facts explicitly represented and distinguished from integration defects? [Edge Case, Spec §FR-010]
- [x] CHK018 Are installed commit/package/config/schema, restart/reload, and known probe evidence required for every migrated surface? [Completeness, Spec §FR-011]
- [x] CHK019 Are direct contribution, reaction/acknowledgment, tool action, silence, error wake, and no second judgment all covered? [Coverage, Spec §FR-012]
- [x] CHK020 Is the dual classifier/margin DEFER transition kept separate from schema cutover? [Consistency, Spec §FR-013]
- [x] CHK021 Does S14 pin exactly Hermes-only, Hermes+Claude, Hermes+Codex, full mixed harness, multi-human Discord, and multi-human Telegram via Hermes? [Completeness, Spec §FR-014]
- [x] CHK022 Are context-budget/no-bomb and no-registry/ledger scenes represented rather than inferred from generic parity? [Coverage, Spec §S15-S16]

## Evidence, Documentation, and Release Quality

- [x] CHK023 Does the evidence bundle enumerate deterministic, replay, context, security, probe, parity, mixed-room, failure, flicker, and limitation records? [Completeness, Spec §FR-015]
- [x] CHK024 Are every live-stage transcript, receipt, provenance, redaction, post-hoc meta-answer grade, stop condition, and blocking-versus-native-capability disposition explicit? [Scenario Quality, Spec §User Story 3]
- [x] CHK025 Must product, security, evaluation, stability, upgrade, and release documentation match the same candidate and evidence grade? [Consistency, Spec §FR-016]
- [x] CHK026 Is the release boundary measurable by exact candidate/version, supported/reference scope, breaking upgrade, evidence, limitations, and decision owner? [Measurability, Spec §FR-017]
- [x] CHK027 Are promotion, launch copy, assets, posts, posting identity, and timing explicitly excluded from release readiness? [Scope, Spec §FR-018]

## Edge Cases and Success Criteria

- [x] CHK028 Are locally green but incompatible handoffs, shared-file conflicts, stale runtimes, capability gaps, continuation overlap, model flicker, and newly discovered live failures addressed? [Edge Cases, Spec §Edge Cases]
- [x] CHK029 Are all success criteria quantified by complete dependency/surface/scene coverage, zero residues/conflicts/blockers/cycles, exact documentation truth, assembled-candidate assurance, and post-merge verification? [Measurability, Spec §SC-001–SC-014]
- [x] CHK030 Is participant silence treated as valid and distinct from an all-mute systemic failure? [Clarity, Spec §User Scenarios]
- [x] CHK031 Is atomic repository cutover after explicit Zoe acceptance distinguished from package release and promotion? [Boundary, Spec §FR-022; Assumptions and Exclusions]

## Review Result

- [x] CHK032 No `[NEEDS CLARIFICATION]` marker remains and all mandatory template sections are complete. [Readiness]
- [x] CHK033 Functional requirements, success criteria, S01-S16 scenes, interfaces, exclusions, and strict T### tasks are mutually traceable. [Consistency]
- [x] CHK034 Does slice `110` rerun slice `100` assurance against the exact assembled candidate and return semantic divergence to its owner without creating a dependency cycle? [Security, Spec §FR-021]
- [x] CHK035 Does one scene/surface manifest resolve every S01-S16 requirement to exact refs, commands, records, grades, and dispositions through stable `scene_id` values? [Traceability, Spec §FR-008]
- [x] CHK036 Is meta-answer detection post-hoc acceptance evaluation with an explicit prohibition on runtime participant-prose filtering? [Boundary, Spec §FR-012]
- [x] CHK037 Do required S14 lifecycle failures block cutover while only genuinely unavailable native platform facts may be limitations? [Acceptance, Spec §FR-014]
- [x] CHK038 Does explicit Zoe repository-cutover acceptance gate one atomic product PR/merge plus post-merge verification and an evidence-only follow-up record? [Cutover, Spec §FR-022]
- [x] CHK039 Does parity prove trusted `PREATTENTION_BYPASS` makes zero classifier calls, invokes one advice-free act-or-silence turn, contains no fabricated social result, and is never treated as an injected verdict? [Contract, Spec §FR-023]
- [x] CHK040 Does parity prove immutable request-correlated observation/attention/participant-host/transport records have one attesting owner each, with silence and unavailable outcomes left explicit? [Contract, Spec §FR-024]

## Notes

- This checklist validates requirements writing, not implementation behavior.
- All items pass for planning. Goal 2 authorization and dependency handoff
  acceptance remain separate mandatory workflow gates.
