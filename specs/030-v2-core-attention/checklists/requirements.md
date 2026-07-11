# Specification Quality Checklist: V2 Core Attention

**Purpose**: Validate that the attention-engine requirements are complete,
human-shaped, measurable, lifecycle-safe, and integration-ready

**Created**: 2026-07-11

**Slice specification**: [spec.md](../spec.md)

## Scope and Ownership

- [x] CHK001 Is the `PLANNED` slice and its `NOT_GRANTED` program authority distinguished explicitly from current V1 implementation truth, with tasks `DORMANT` until `READY`? [Clarity, Spec §Control-Plane Boundary]
- [x] CHK002 Are all product, test, eval, evidence, and documentation targets ordinary paths? [Consistency, Spec §Control-Plane Boundary, FR-016]
- [x] CHK003 Is `v2-core-owner` the sole I-030A owner with complete upstream and downstream handoffs? [Completeness, Spec §Interface Summary]
- [x] CHK004 Are observation, participant hosting, surface integration, final cutover, release, and margin retirement excluded? [Coverage, Spec §Explicit Exclusions]

## Judgment and Transition Requirements

- [x] CHK005 Is the single attention question narrow, participant-shaped, and free of speaker-algorithm or reply-composition requirements? [Clarity, Spec §FR-002–FR-003]
- [x] CHK006 Are classifier dispositions, trusted no-classifier preattention bypass, and operational ERROR unambiguously separate? [Consistency, Spec §FR-004, FR-017]
- [x] CHK007 Are advice authority, grounding, allowed disposition, and reply-prose prohibitions complete? [Completeness, Spec §FR-005]
- [x] CHK008 Are all suppression-legitimacy conditions and trusted operator-policy boundaries specified? [Completeness, Spec §FR-006–FR-007]
- [x] CHK009 Are direct DEFER, margin DEFER, malformed confidence evidence, allowed widening, and margin-retirement boundaries clear? [Clarity, Spec §FR-008–FR-010]
- [x] CHK010 Are all validation/provider/timeout/config/runtime failures and the explicit NO_WAKE override defined without social relabeling? [Coverage, Spec §FR-011]

## Scenario, Security, and Evidence Coverage

- [x] CHK011 Do scenarios cover confident suppress, grounded wake advice, direct DEFER, margin DEFER, disabled delegation, trusted preattention bypass, unproven recovery, ERROR, and core/CLI parity? [Coverage, Spec §User Scenarios & Testing]
- [x] CHK012 Are forged output/advice, request-controlled configuration, provider retries, invalid transitions, host-secret projection leaks, same-class address, and apparent-resolution scars addressed? [Edge Case, Spec §Edge Cases]
- [x] CHK013 Is the immutable attention stage limited to classifier/bypass, effective route, valve, policy/model source, timing, and error without claiming downstream host/transport facts? [Completeness, Spec §FR-012]
- [x] CHK014 Are deterministic mechanics, replay, multi-model evidence, downstream canary protocol, and margin evidence distinguished so unit tests cannot overclaim social quality or create a dependency cycle? [Evidence, Spec §FR-014, SC-004–SC-006]
- [x] CHK015 Can every success criterion and handoff obligation be measured against a named ordinary artifact or result? [Measurability, Spec §SC-001–SC-008, FR-015]
- [x] CHK016 Is the exact CLI stdout/stderr/exit 0/1/2/3 process contract complete for valid, bypass, schema-invalid, operational, and unreadable inputs? [Completeness, Spec §FR-019]
- [x] CHK017 Are host-only continuation secrets excluded from classifier input while the bound capability remains available to the participant host? [Security, Spec §FR-018–FR-020]
- [x] CHK018 Does documentation freshness inventory every exact known affected path, require V2 and retained-V1 evaluation `UPDATE` rows, route shared/downstream `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK019 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010-v2-contract`, active `v2-core-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/attention/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox? [Lifecycle, tasks.md §Slice activation]

- [x] CHK020 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- All requirement-quality checks pass for the planning text. They do not claim
  that I-030A, V2 CLI behavior, or any social evidence exists yet.
