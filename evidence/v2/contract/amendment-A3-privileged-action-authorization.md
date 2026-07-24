# Slice 010 post-acceptance amendment A3 — privileged action authorization

**Slice**: 010-v2-contract

**Amendment ID**: A3

**Amended interface**: I-010F

**Prior interface version**: @0

**New interface version**: @1

**Prior effective commit**: 26a6b531fa146ba1f1f5fcd1c4d191041b141301

**Prior effective packet**: evidence/v2/contract/amendment-A2-decision-margin-boundary.md

**Starting commit**: d538004b83f9b0f1215a3775043d7ffb44e9b9ea

**Owner lane**: v2-contract-owner

**Assigned participant / source**: Codex — evidence/governance/assignments/codex-v2-contract-owner-2026-07-23.md

**Fixed scope paths**: `specs/010-v2-contract/spec.md`, `specs/010-v2-contract/plan.md`, `specs/010-v2-contract/tasks.md`, `schemas/v2/privileged-action-authorization.schema.json`, `tests/v2/contract/schema_helpers.py`, `tests/v2/contract/test_privileged_action_authorization.py`, `evals/v2/contract/privileged-action-authorization/cases.jsonl`, `evals/v2/contract/privileged-action-authorization/expected-counts.json`, `evidence/v2/contract/amendment-A3-privileged-action-authorization.md`, `evidence/v2/contract/privileged-action-authorization.jsonl`, `evidence/v2/contract/README.md`, `docs/contracts/nunchi-v2.md`, `docs/security/privileged-action-authorization.md`, `scripts/check_governance.py`, `tests/test_governance.py`

**Amendment task IDs**: T050, T051, T052, T053, T054, T055

**Amendment tasks SHA256**: 7786d2616df7233a313efb694ca58dd9ff07676e4e1bfdb111574dde5966e0a2

**Analysis result**: PASS — zero CRITICAL/HIGH findings

**Branch**: v2/contract-a3

**Worktree**: .worktrees/v2-contract-a3/

**Amendment phase**: ACTIVE

## Scope and safety boundary

This record adds the `I-010F@1` contract seam only. It does not reopen
I-010A–E, make A3 effective, start any downstream slice, execute an operation,
load a policy, authenticate an operator, retain a pending approval, or provide
a bearer grant. The candidate must be separately reviewed and accepted by
`v2-integrator`; until then A2 remains the effective slice-010 dependency.

The schema and deterministic corpus bind exact supplied facts. Slice `040`
still owns host-side origin resolution, policy and revocation recheck,
persistence, cancellation, one-use consumption, and effect execution.
