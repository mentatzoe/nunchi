# Specification Quality Checklist: V2 Contract

**Purpose**: Validate that the contract-slice requirements are complete, clear,
measurable, and bounded before slice activation is accepted

**Created**: 2026-07-11

**Slice specification**: [spec.md](../spec.md)

## Content and Boundary Quality

- [x] CHK001 Is the `PLANNED` slice distinguished explicitly from current V1 implementation truth — program authority `GRANTED` (recorded 2026-07-16) but tasks `DORMANT` until the slice is independently `READY`? [Clarity, Spec §Control-Plane Boundary]
- [x] CHK002 Are product schemas, tests, evals, evidence, and docs assigned only to ordinary repository paths? [Consistency, Spec §Control-Plane Boundary]
- [x] CHK003 Is exactly one accountable owner named, with a non-silent contract-change handoff? [Completeness, Spec §Interface Summary]
- [x] CHK004 Are implementation, classifier, collector, harness, release, and promotion work explicitly excluded? [Coverage, Spec §Explicit Exclusions]

## Interface Requirement Completeness

- [x] CHK005 Are all five canonical interface names, versions, consumers, and feeds stated consistently? [Traceability, Spec §Interface Summary, FR-001–FR-010]
- [x] CHK006 Are exact self binding and loose participant descriptors distinguished without ambiguity? [Clarity, Spec §FR-002]
- [x] CHK007 Are actor-targeted mentions distinct from `mentions_room`, and are event order, other literal relations, unresolved references, coverage, visibility, and restart limits specified? [Completeness, Spec §FR-003–FR-004]
- [x] CHK008 Are all four ok transitions, exact no-classifier preattention bypass, and malformed-evidence error outcome mutually exclusive? [Completeness, Spec §FR-005–FR-007]
- [x] CHK009 Are `PREATTENTION_BYPASS`, host-only continuation authority, classifier-safe expansion flags, and immutable singly owned receipt stages defined consistently? [Consistency, Spec §FR-008–FR-010]
- [x] CHK010 Are V1 translation, reply fields, inferred roster, and social-ledger state unambiguously forbidden? [Coverage, Spec §FR-011]

## Scenario and Edge-Case Coverage

- [x] CHK011 Do acceptance scenarios cover primary valid flows, bypass, invalid transitions, host-secret projection leaks, binding attacks, immutable staged receipts, unknown facts, and participant silence? [Coverage, Spec §User Scenarios & Testing]
- [x] CHK012 Are duplicate IDs, contradictory timestamps, omitted relation targets, non-finite values, expired/cross-bound continuation, bypass-field contamination, and cross-owner receipt mutation addressed? [Edge Case, Spec §Edge Cases]
- [x] CHK013 Is it explicit that advice cannot appear on DEFER/SUPPRESS, cite nonexistent events, or contain reply prose? [Security, Spec §Edge Cases, FR-005]

## Acceptance Criteria and Dependencies

- [x] CHK014 Do Draft 2020-12 and stdlib runtime adapters consume the same corpus under the exact offline `jsonschema==4.26.0` test command, with aggregate records carrying `scene_id` and a complete README manifest? [Measurability, Spec §SC-001–SC-006]
- [x] CHK015 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/010-v2-contract`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted declared dependencies (none), active `v2-contract-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/contract/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox? [Lifecycle, tasks.md §Slice activation]
- [x] CHK016 Does documentation freshness inventory every exact known affected path, require the owned contract-doc `UPDATE`, route exact shared/current `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK017 Does activation evidence require `Accepted dependencies: none`, `Dependency commits: none`, and `Dependency acceptance references: none`, while candidate/handoff evidence is append-only, rejection appends `REJECTED` and returns the same owner to `ACTIVE`, requires a new bound run rather than resume of the completed run, preserves every prior attempt, and convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- All items are checked because the specification presently satisfies these
  requirement-quality tests. They do not claim that any V2 schema or product
  behavior has been implemented.

## Formal Reviewer Gate (appended 2026-07-17)

**Purpose**: Requirement-quality gate for the formal reviewer covering scope,
parity, interface, evidence, documentation freshness, and control-plane
boundary requirements. These items test what the slice artifacts say — their
completeness, clarity, consistency, and measurability — not whether any
implementation works. They are appended unchecked for the reviewer's pass and
do not alter the checked baseline above.

### Scope Requirement Quality

- [ ] CHK018 Is the split between this planning baseline's outputs (control-plane artifacts only) and authorized-implementation outputs (schemas, tests, evals, evidence, product docs) stated identically in spec, plan, and tasks, with no artifact class assigned to both sides? [Consistency, Spec §Control-Plane Boundary; Plan §Summary; Tasks §Notes]
- [ ] CHK019 Is every item in the exclusions list traceable to a named later owner or decision (slices 020/030/040 ownership, release/promotion decisions), so a reviewer can distinguish "excluded and owned elsewhere" from "unplanned anywhere"? [Traceability, Spec §Explicit Exclusions]
- [ ] CHK020 Are the downstream start conditions quantified the same way everywhere — 020/030 only after each consumer separately accepts the T019-derived packet, 040 additionally after the 020/030 handoffs — with no looser wording in the plan than in the task graph? [Consistency, Plan §Integration Strategy; Tasks §Dependencies & Execution Order]
- [ ] CHK021 Is the procedure a dependent slice must follow to request a contract change specified beyond "explicit return handoff and re-analysis" — or is the required content of that return handoff unspecified? [Gap, Plan §Integration Strategy; Spec §Explicit Exclusions]

### Parity Requirement Quality

- [ ] CHK022 Is dual-validator parity defined measurably — one corpus, each case loaded once, identical expected results through both the Draft 2020-12 oracle and the stdlib runtime adapter — with the baseline skip-accounting rule (explicit counted skips, no silent skips, loud failure only under the pinned offline command) stated consistently across spec, plan, and T001? [Measurability, Spec §FR-012; Plan §Contract validation commands; Tasks T001]
- [ ] CHK023 Do the requirements pin how downstream runtime owners inherit the conformance corpus — which corpus revision, verified before each owner's own handoff, recorded where — or is cross-slice corpus versioning unaddressed? [Gap, Plan §Contract validation commands; Tasks §Dependencies & Execution Order]
- [ ] CHK024 Is SC-002's "byte-for-byte at the semantic field level" internally coherent and objectively testable — do the requirements define what preservation means under JSON re-serialization (key order, whitespace, unicode escapes)? [Ambiguity, Spec §SC-002]
- [ ] CHK025 Do the requirements keep parity-claim boundaries explicit — a green contract suite proves mechanics only, and the classifier-DEFER/margin-DEFER transition remains independently evidence-gated rather than a schema-compatibility fact? [Clarity, Tasks §Notes; Plan §Technical Context]
- [ ] CHK026 Can the final integrator reject an interface mismatch deterministically from the written criteria alone — exact `@1` versions, exact `schemas/v2/` paths, and SC-004's deterministic failure on deletion or incompatible edit? [Measurability, Spec §SC-004; Plan §Produces]

### Interface Requirement Quality

- [ ] CHK027 Does each of I-010A through I-010E appear with the same name, version, schema path, and owning task across the spec interface summary, plan produces list, and tasks T006/T009/T012–T014, with none missing or renamed? [Traceability, Spec §Interface Summary; Plan §Produces; Tasks T006–T014]
- [ ] CHK028 Are breaking-edit rules for the `@1` versions complete — explicit owner handoff plus dependent re-analysis — and consistent with sole-owner editing of `schemas/v2/**` until handoff acceptance? [Consistency, Spec §Assumptions; Plan §Integration Strategy]
- [ ] CHK029 Is the classifier projection's permitted content written as a closed enumeration (coverage and expansion capability booleans only), so any additional field is decidably a host-secret leak rather than arguably allowed? [Clarity, Spec §FR-004, §FR-009]
- [ ] CHK030 Is the FR-013 cross-slice reference to the attention engine's advice contract (030 FR-005) exact enough — slice, requirement ID, and rule content restated locally — for a reviewer to detect drift between the two artifacts? [Traceability, Spec §FR-013]
- [ ] CHK031 Is the decision union closed and mutually exclusive in writing — only `ok`/`bypass`/`error` statuses, branch-specific field sets that cannot co-occur, and bypass explicitly not a successful disposition pairing? [Completeness, Spec §FR-005–FR-006]
- [ ] CHK032 Are receipt-stage writer obligations specified per stage — append only one's own stage, never mutate prior or fill future stages — together with explicit unknown/unavailable values, so a violating record is identifiable from the requirement text alone? [Completeness, Spec §FR-010]

### Evidence Requirement Quality

- [ ] CHK033 Does every scene row name a concrete ordinary evidence target and required observation, and does every scene ID cited by tasks T002–T018 (S01–S03, S05–S09, S15, S16, 010-Preattention-bypass, 010-V1) appear in the plan's scene table exactly once? [Traceability, Plan §Acceptance Scenes and Evidence; Tasks T002–T018]
- [ ] CHK034 Are the mandatory aggregate-record fields (`scene_id`, stable `case_id`, validator identity, expected result, observed result) and the README manifest's coverage of all twelve scene rows stated measurably? [Measurability, Plan §Acceptance Scenes and Evidence; Tasks T018]
- [ ] CHK035 Do spec SC-005, the plan owner-handoff section, and task T019 enumerate the same handoff-packet contents — or do items such as the rejected-case inventory, migration/provenance notes, and documentation dispositions appear in some lists but not others? [Conflict, Spec §SC-005; Plan §Owner Handoff; Tasks T019]
- [ ] CHK036 Are lifecycle evidence artifacts (activation, candidate, handoff, acceptance) and contract-run evidence (JSONL results, README manifest) kept distinct, each with an exact ordinary path and writer, and none under a SpecKit-managed path? [Consistency, Spec §Control-Plane Boundary; Plan §Project Structure]
- [ ] CHK037 Is the evidence-sufficiency rule explicit that a table entry or checked task box is not evidence — ordinary handoff evidence must record reviewed paths, rationale, commands, and results? [Clarity, Plan §Documentation Impact and Freshness; Constitution §VI]

### Documentation Freshness Requirement Quality

- [ ] CHK038 Does every documentation-impact row carry exactly one disposition with an owning task, and either validation steps (`UPDATE`), a concrete rationale (`NO_IMPACT`), or an exact claim delta plus accepting owner (`HANDOFF`), with no directory wildcards or generic rows? [Completeness, Plan §Documentation Impact and Freshness]
- [ ] CHK039 Are the `NO_IMPACT` rationales written so they can be re-verified against the exact candidate diff, with the re-verification obligation and its recording location (`evidence/v2/contract/handoff.md`) stated? [Measurability, Plan §Documentation Impact and Freshness]
- [ ] CHK040 Is the `UPDATE`/`HANDOFF` split consistent with ownership — `UPDATE` only for the slice-owned `docs/contracts/nunchi-v2.md`, `HANDOFF` with accepting owner `v2-integrator` for integrator-owned current-state wording including `README.md`, and no `HANDOFF` for a slice-owned document? [Consistency, Plan §Documentation Impact and Freshness]
- [ ] CHK041 Is the documentation freshness surface bounded in writing — `docs/archive/` excluded as dated history — so a reviewer can classify an unlisted document as either a matrix gap or legitimately out of scope? [Coverage, Plan §Documentation Impact and Freshness]
- [ ] CHK042 Do the spec documentation-freshness section and the plan matrix agree on the affected-file inventory — every spec-named `HANDOFF`/`UPDATE` surface has exactly one matching plan row, and plan-only `NO_IMPACT` rows remain consistent with the spec's affected-docs claim? [Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

### Control-Plane Boundary Requirement Quality

- [ ] CHK043 Is the slice-directory inventory a written closed allowlist (spec.md, plan.md, tasks.md, checklists/requirements.md, "no other file or directory"), with the enforcing boundary check named by its exact flagless command in T018? [Measurability, Plan §Project Structure; Spec §SC-006; Tasks T018]
- [ ] CHK044 Are the constitutionally disabled SpecKit outputs (`data-model.md`, `contracts/`, `quickstart.md`) absent from every planned output list, with interface detail explicitly labeled a planning summary rather than an embedded product contract? [Consistency, Plan §Slice Interfaces; Constitution §VII]
- [ ] CHK045 Do the requirements keep governance lifecycle state (`PLANNED` through `ACCEPTED`) out of runtime, classifier, receipt, and social state — no contract field, fixture, or evidence record is required to carry slice-lifecycle facts? [Coverage, Spec §Control-Plane Boundary; Constitution §Program and Slice Lifecycle Gates]
- [ ] CHK046 Is the dev/test-only `jsonschema==4.26.0` constraint stated consistently at every dependency claim — spec assumptions, plan technical context, tasks notes, and the `docs/INSTALL.md` `NO_IMPACT` rationale — with no wording that permits it as a runtime or install dependency? [Consistency, Spec §Assumptions; Plan §Technical Context; Tasks §Notes]
