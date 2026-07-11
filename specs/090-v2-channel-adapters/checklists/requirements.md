# Requirements Quality Checklist: V2 Standalone Channel Adapters

**Purpose**: Validate native-fact equivalence, common lifecycle, capability,
entrypoint, and evidence requirements before future implementation
**Created**: 2026-07-11
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Are all eight consumed interfaces named with exact canonical IDs and versions? [Completeness, Spec §Interface Summary]
- [x] CHK002 Are generic, Discord, Matrix, and Telegram identity, facts, history, restart, continuation, lifecycle, send, and provenance covered? [Completeness, Spec §FR-001–FR-017]
- [x] CHK003 Is the absence of an adapter-owned public interface explicit? [Scope, Control-Plane Boundary]

## Requirement Clarity and Consistency

- [x] CHK004 Is parity defined as equivalence of available facts rather than identical platform capability? [Clarity, Spec §FR-004, §FR-012]
- [x] CHK005 Are exact native self binding and generic install-attested identity clearly distinguished from alias fallback? [Clarity, Spec §FR-002; Edge Cases]
- [x] CHK006 Are permitted transport non-events consistently closed against semantic adapter rules? [Consistency, Spec §FR-006–FR-007]
- [x] CHK007 Are participant action options allowed to differ while the act-or-silence lifecycle remains common? [Consistency, Spec §FR-009–FR-013]

## Acceptance Criteria Quality

- [x] CHK008 Can matched fact parity and every genuine platform difference be objectively enumerated? [Measurability, Spec §SC-001]
- [x] CHK009 Can attention and send-time social call counts be measured per unique trigger and adapter? [Measurability, Spec §SC-003]
- [x] CHK010 Does each adapter migration claim require exact installed package/entrypoint/config/process provenance? [Acceptance Criteria, Spec §SC-006]

## Scenario and Edge-Case Coverage

- [x] CHK011 Are alias collision, native relations, missing capability, generic synthetic identity, and platform membership-scope differences covered? [Coverage, Spec §US1; Edge Cases]
- [x] CHK012 Are SUPPRESS, WAKE, dual DEFER, PREATTENTION_BYPASS, error, participant action/silence, evaluation-only meta-answer, no-runtime-prose-filter, and operational send rejection covered? [Coverage, Spec §US2]
- [x] CHK013 Are all four installed entrypoints, V1 rejection, restart, and schema-2 probes covered? [Coverage, Spec §US3]
- [x] CHK014 Are malformed-after-routing error, live-only history, and unsupported reaction/tool cases explicitly addressed? [Coverage, Edge Cases]

## Dependencies, Ownership, and Boundary

- [x] CHK015 Are dependencies `010`–`040` and consumers `100`/`110` consistent across all artifacts? [Dependency]
- [x] CHK016 Does one adapter owner control shared adapter files while foundation, Discord-MCP, and final parity files remain with their owners? [Ownership, Plan §Integration Strategy]
- [x] CHK017 Are every future implementation, test, fixture, eval, evidence, and docs target in ordinary repository paths? [Boundary, Plan §Ordinary Repository Targets]
- [x] CHK018 Is Goal 2 authorization an explicit external prerequisite rather than a planning status? [Boundary, Control-Plane Boundary; tasks.md]
- [x] CHK019 Does AD-09 have a harness-independent producing task shaped like the six pinned live stages without adding a reverse dependency on downstream harnesses? [Coverage, Plan §AD-09; tasks.md]
- [x] CHK020 Does one manifest resolve AD-01 through AD-09 and common S IDs to exact evidence through stable `scene_id` values? [Traceability, Spec §FR-015; Plan §Acceptance Scenes]
- [x] CHK021 Does AD-05 prove trusted `PREATTENTION_BYPASS` makes zero classifier calls, invokes one advice-free act-or-silence turn, fabricates no social/silent-delivery result, and preserves immutable singly owned request-correlated receipt stages? [Contract, Spec §FR-008, FR-009, FR-017]
- [x] CHK022 Does documentation freshness inventory every exact known path, require the V2 adapter guide to `UPDATE`, route shared/current/supersession `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

## Notes

- All requirements-quality items pass for planning readiness.
- This checklist establishes planning clarity, not current V2 adapter behavior.
