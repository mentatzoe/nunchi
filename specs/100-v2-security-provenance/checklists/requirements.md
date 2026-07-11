# Specification Quality Checklist: V2 Security and Runtime Provenance

**Purpose**: Validate that the planned security/provenance slice requirements
are complete, unambiguous, measurable, traceable, lifecycle-aware, and
constitutionally bounded before analysis.

**Created**: 2026-07-11

**Slice specification**: [spec.md](../spec.md)

## Content and Boundary Quality

- [x] CHK001 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/100-v2-security-provenance`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010`–`090` handoffs, active `v2-security-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/security/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox while tasks remain dormant in `PLANNED`? [Clarity, Spec §Control-Plane Boundary; tasks.md]
- [x] CHK002 Are all product contracts, tests, evals, evidence, runtime assets, and documentation assigned to ordinary repository paths? [Completeness, Spec §FR-010]
- [x] CHK003 Is the prohibition on social heuristics, governance profiles, registries, ledgers, moderation, and composition explicit? [Scope, Spec §Explicit Exclusions]
- [x] CHK004 Is exactly one accountable owner named, with review and integration distinguished from ownership? [Consistency, Spec §Interface Summary]

## Requirement Completeness

- [x] CHK005 Are authorization, expiry, malformed state, revocation, inspection, recovery, and restart requirements all specified? [Completeness, Spec §FR-001–FR-003]
- [x] CHK006 Are operational errors, send backstops, and social dispositions required to remain distinct? [Completeness, Spec §FR-004–FR-005]
- [x] CHK007 Are credential, endpoint, executable, participant identity, redaction, and operator-control boundaries all covered? [Completeness, Spec §FR-006–FR-007]
- [x] CHK008 Does installed provenance include commit/package, hooks/shims, effective configuration, restart/reload, schema, and a known probe? [Completeness, Spec §FR-008]
- [x] CHK009 Does the threat inventory cover every named classifier, participant, control, credential, amplification, sink, supply-chain, and runtime-drift class? [Coverage, Spec §FR-009]
- [x] CHK010 Are the selected three attention-model families, exact runtime IDs/timestamps, at least five retained repetitions per stochastic cell, pre-registered override rule, failures, and flicker specified without a single-score shortcut? [Completeness, Spec §FR-011]
- [x] CHK011 Is every threat required to have mitigation evidence or explicit Zoe residual-risk acceptance? [Completeness, Spec §FR-012]

## Interface and Dependency Quality

- [x] CHK012 Are every canonical consumed interface `I-010A`–`I-050A` and every component handoff from `060`–`090` identified? [Traceability, Spec §Interface Summary]
- [x] CHK013 Are the security assurance report, audited provenance set, readiness handoff, and slice `110` consumer explicit without creating a parallel `I-*` registry? [Traceability, Spec §Interface Summary]
- [x] CHK014 Does the spec block work when an upstream handoff is absent, stale, or version-inconsistent rather than inventing a compatibility bridge? [Edge Case, Spec §FR-013]
- [x] CHK015 Is the handoff packet objectively specified with commit, commands/results, interface versions, evidence, provenance, risk, and limitations? [Measurability, Spec §FR-014]
- [x] CHK016 Is dependency direction only `010`–`090` → `100` → `110`, with no reverse dependency? [Consistency, Spec metadata]

## Scenario and Edge-Case Coverage

- [x] CHK017 Is the security-relevant obligation in every canonical S01-S16 scene represented without transferring final parity ownership from slice `110`? [Coverage, Spec §FR-015]
- [x] CHK018 Are race-like authorization changes, stale revocation, restart loss, malformed provider output, and missing surface capability addressed? [Edge Cases, Spec §Edge Cases]
- [x] CHK019 Is participant silence after wake/defer/bypass/error treated as valid rather than as a security failure? [Consistency, Spec §Edge Cases]
- [x] CHK020 Are secret-like room text and actual operator secrets distinguished without granting content authority? [Edge Case, Spec §Edge Cases]
- [x] CHK021 Is stale hook/shim detection covered even when source commit and package version appear correct? [Recovery, Spec §Edge Cases]

## Acceptance and Success-Criteria Quality

- [x] CHK022 Are all success criteria measurable as percentages, per-surface scene completion, traceable dispositions, or zero-blocker gates? [Measurability, Spec §SC-001–SC-010]
- [x] CHK023 Do success criteria require both deterministic mechanics and live/adversarial/provenance evidence? [Consistency, Spec §SC-002–SC-007]
- [x] CHK024 Is the difference between a green unit suite and security/social-quality evidence explicit? [Clarity, Spec §User Story 3]
- [x] CHK025 Does integrator acceptance require zero unresolved CRITICAL/HIGH security or provenance findings? [Acceptance Quality, Spec §SC-008]

## Review Result

- [x] CHK026 No `[NEEDS CLARIFICATION]` marker remains and all mandatory template sections are complete. [Readiness]
- [x] CHK027 Functional requirements, success criteria, acceptance scenes, interfaces, exclusions, and tasks are mutually traceable. [Consistency]
- [x] CHK028 Does the isolated, non-releaseable assurance worktree consume the exact accepted commits for `010`–`090` through immutable refs, without creating a program integration/cutover artifact that belongs only to slice `110`? [Integration, Plan §Integration Strategy]
- [x] CHK029 Does one evidence manifest resolve S01-S16 and SEC-A/SEC-B/SEC-C to exact candidate refs, commands, attempts, records, and dispositions? [Traceability, Spec §Security Evidence Manifest]
- [x] CHK030 Does the handoff require reusable assurance commands so slice `110` can rerun controls against the exact assembled candidate without making slice `100` an integrator? [Dependency, Plan §Owner Handoff]
- [x] CHK031 Does SEC-C prove trusted bypass makes zero classifier calls and invokes one advice-free act-or-silence turn without a fabricated social result, while rejecting room/request-controlled bypass claims? [Security, Spec §FR-018]
- [x] CHK032 Does SEC-C audit immutable request-correlated observation/attention/participant-host/transport records so each owner attests only its own stage and silence/unavailable outcomes are never fabricated? [Security, Spec §FR-019]
- [x] CHK033 Does documentation freshness inventory every exact known path, make stale security docs blocking, require each exact owned security-doc `UPDATE`, route shared/current `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]

- [x] CHK034 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- This checklist validates requirements writing, not implementation behavior.
- All items pass for planning. The one valid complete authorization record
  enumerating exactly slices `010` through `110` and the independent completed
  slice-activation attestation remain separate mandatory lifecycle gates.
