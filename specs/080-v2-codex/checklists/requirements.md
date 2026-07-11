# Requirements Quality Checklist: V2 Codex Harness

**Purpose**: Validate Codex event, session, one-judgment, participant-turn,
packaging, and evidence requirements before future implementation
**Created**: 2026-07-11
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Are all nine canonical consumed interfaces named with exact IDs and versions? [Completeness, Spec §Interface Summary]
- [x] CHK002 Are prompt hook, room runner, persistent session, participant turn, send path, plugin, MCP, receipts, and provenance all covered? [Completeness, Spec §FR-001–FR-015]
- [x] CHK003 Is the absence of a Codex-owned public contract explicit? [Scope, Control-Plane Boundary]

## Requirement Clarity and Consistency

- [x] CHK004 Is operational session continuity distinguished from social permission or handled state? [Clarity, Spec §FR-008–FR-009]
- [x] CHK005 Is one unique native trigger consistently limited to one attention route across prompt and runner paths, with zero classifier calls for trusted bypass? [Consistency, Spec §FR-005, §FR-012]
- [x] CHK006 Are operational send safety and prohibited social send reclassification clearly separated? [Clarity, Spec §FR-009–FR-010]
- [x] CHK007 Are classifier/bypass, effective route, host, participant, expansion, and transport outcomes preserved as immutable singly attested stages? [Consistency, Spec §FR-013]

## Acceptance Criteria Quality

- [x] CHK008 Can reactive fact parity be measured against all representable `I-050A` fields? [Measurability, Spec §SC-001]
- [x] CHK009 Can duplicate attention and send-time classifier calls be objectively counted? [Measurability, Spec §SC-002]
- [x] CHK010 Does every live migration claim require the complete installed component/provenance chain? [Acceptance Criteria, Spec §SC-006]

## Scenario and Edge-Case Coverage

- [x] CHK011 Are exact identity, duplicate reconnect, unreadable/stale session, and prompt/runner collision cases covered? [Coverage, Spec §US1; Edge Cases]
- [x] CHK012 Are SUPPRESS, WAKE, both DEFER sources, zero-call PREATTENTION_BYPASS, error, action, silence, evaluation-only meta-answer, and rejected-send cases covered without a runtime prose filter? [Coverage, Spec §US2]
- [x] CHK013 Are V1 residue, schema-2 probe, persistent conversation, and mixed-agent class address covered? [Coverage, Spec §US3]
- [x] CHK014 Are forged wake/receipt/continuation/send-permission inputs addressed as adversarial cases? [Coverage, Edge Cases]

## Dependencies, Ownership, and Boundary

- [x] CHK015 Are dependencies `010`–`050` and consumers `100`/`110` consistent across all artifacts? [Dependency]
- [x] CHK016 Does the Codex lane own only Codex-specific paths while shared transport and foundation interfaces stay upstream-owned? [Ownership, Plan §Integration Strategy]
- [x] CHK017 Are all future implementation, test, eval, evidence, and doc files assigned to ordinary paths, with no new evidence under `integrations/codex/`? [Boundary, Plan §Project Structure]
- [x] CHK018 Is Goal 2 an external explicit gate rather than a completed planning/task status? [Boundary, Control-Plane Boundary; tasks.md]

## Notes

- All requirements-quality items pass for planning readiness.
- This checklist does not claim the current Codex integration has removed its V1 send gate.
