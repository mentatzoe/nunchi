# Zoe end-to-end ownership supersession — 2026-07-23

This record durably copies Zoe's external ownership decision from Codex task
`019f8ff1-46c7-7c60-b427-47bf82e06d7c`.

> Remove the session assignments to the slices, with the exception of the
> platform-specific implementation. They are superseeded by my instruction for
> you to own the end-to-end.

**Decision owner**: Zoe
**Decision date**: 2026-07-23
**Recorded by**: Codex
**Source task**: 019f8ff1-46c7-7c60-b427-47bf82e06d7c
**Authority reference**: Codex task `019f8ff1-46c7-7c60-b427-47bf82e06d7c` — Zoe's 2026-07-23 instruction
**Current Codex slices**: 010, 020, 030, 040, 050, 100, 110
**Retained platform slices**: 060, 070, 080, 090
**Program owner**: Zoe
**Current assignment records**: 010=evidence/governance/assignments/codex-v2-contract-owner-2026-07-23.md, 020=evidence/governance/assignments/codex-v2-observation-owner-2026-07-23.md, 030=evidence/governance/assignments/codex-v2-core-owner-2026-07-23.md, 040=evidence/governance/assignments/codex-v2-wake-owner-2026-07-23.md, 050=evidence/governance/assignments/codex-v2-transport-owner-2026-07-23.md, 100=evidence/governance/assignments/codex-v2-security-owner-2026-07-23.md, 110=evidence/governance/assignments/codex-v2-integrator-2026-07-23.md
**Retained assignment records**: 060=evidence/governance/assignments/sr-dev-v2-hermes-owner-2026-07-16.md, 070=evidence/governance/assignments/station-v2-claude-owner-2026-07-16.md, 080=evidence/governance/assignments/vigil-v2-codex-owner-2026-07-16.md, 090=evidence/governance/assignments/mid-dev-v2-adapters-owner-2026-07-16.md

The current participant for each shared foundation lane in slices `010`–`050`,
the security/provenance lane in slice `100`, and the integrator lane in slice
`110` is `Codex`. The corresponding 2026-07-16 assignment records remain
immutable historical evidence but no longer identify those lanes' current
occupant.

The platform-specific implementation assignments are retained without change:

- slice `060`, `v2-hermes-owner`: `sr-dev`
- slice `070`, `v2-claude-owner`: `Station`
- slice `080`, `v2-codex-owner`: `Vigil`
- slice `090`, `v2-adapters-owner`: `mid-dev`

Zoe remains the assigned `v2-program-owner`.

This ownership decision does not grant new implementation authority, make a
slice `READY` or `ACTIVE`, start or resume any workflow, waive dependency or
acceptance gates, authorize platform-specific work before its accepted
upstreams, or authorize cutover, release, or promotion. Every slice remains
bound by its declared lifecycle and exact dependency closure.

Planning, delivery, start, resume, and branch or worktree creation for slices
`060` and `070` are forbidden until every shared upstream slice `010` through
`050` is `ACCEPTED` and a fresh exact-subject readiness report has passed an
independent review. No earlier run or historical assignment bypasses this gate.

End-to-end ownership is accountability, not permission to self-review. For
every new slice `010`–`100` candidate, a separate non-author reviewer must
challenge the exact commit and packet before the assigned `v2-integrator`
accepts or rejects it. The `v2-integrator` retains and records that lifecycle
decision. Zoe remains the decision owner for slice `110` after its separate
final review gate.

This is an immutable one-time supersession decision, not a mutable assignment
registry or runtime product state.
