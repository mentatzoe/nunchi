# Specification Quality Checklist: V2 Contract

**Purpose**: Validate that the future Goal 2 contract requirements are complete,
clear, measurable, and bounded before implementation planning is accepted

**Created**: 2026-07-11

**Feature**: [spec.md](../spec.md)

## Content and Boundary Quality

- [x] CHK001 Is the current V1 implementation distinguished explicitly from future Goal 2 V2 work? [Clarity, Spec §Control-Plane Boundary]
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
- [x] CHK015 Are dependency order, downstream owner lanes, interface ownership, and Goal 2 authorization prerequisites complete? [Dependency, Spec §Interface Summary, Assumptions]
- [x] CHK016 Does documentation freshness inventory every exact known affected path, require the owned contract-doc `UPDATE`, route exact shared/current `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

## Notes

- All items are checked because the specification presently satisfies these
  requirement-quality tests. They do not claim that any V2 schema or product
  behavior has been implemented.
