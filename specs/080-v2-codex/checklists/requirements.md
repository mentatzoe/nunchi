# Requirements Quality Checklist: V2 Codex Harness

**Purpose**: Validate Codex event, session, one-judgment, participant-turn,
packaging, and evidence requirements before authorized slice implementation
**Created**: 2026-07-11
**Slice specification**: [spec.md](../spec.md)

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
- [x] CHK017 Are all implementation, test, eval, evidence, and doc files assigned to ordinary paths, with no new evidence under `integrations/codex/`? [Boundary, Plan §Project Structure]
- [x] CHK018 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/080-v2-codex`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010`–`050` handoffs, active `v2-codex-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/codex/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox while tasks remain dormant in `PLANNED`? [Boundary, Control-Plane Boundary; tasks.md]
- [x] CHK019 Does documentation freshness inventory every exact known path, require new/existing Codex operator guides to `UPDATE`, route shared/transport `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

- [x] CHK020 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- All requirements-quality items pass for planning readiness.
- This checklist does not claim the current Codex integration has removed its V1 send gate.
