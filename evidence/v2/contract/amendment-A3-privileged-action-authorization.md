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

## Convergence checkpoint — 2026-07-24

**Amendment phase**: CONVERGED

**Implementation result**: COMPLETE — `I-010F@1` schema, deterministic flow
validator, S18 corpus, generated evidence, ordinary-path documentation, and
explicit execution/persistence limitations agree.

**Verification result**: PASS — focused authorization tests (20 tests, 1
explicit baseline-oracle skip); stdlib contract suite (215 tests, 4 explicit
baseline-oracle skips); pinned offline dual-validator suite (215 tests, 0
skipped); full repository baseline; governance/CLI check; evaluation discovery;
evidence verification; and `git diff --check` all passed.

**Independent review**: COMPLETE — the review findings on missing host-only
challenge, final-decision/recheck correlation, stale decision and recheck
revocation timestamps, approval ordering, and challenge-policy provenance were
fixed with focused regressions. The latest targeted re-review confirmed the
approval-recheck freshness repair.

**Acceptance state**: PENDING — A3 is not yet an effective dependency. A
separate exact handoff packet and `v2-integrator` acceptance remain required.

## Exact handoff packet — 2026-07-24

**Amendment phase**: HANDOFF_READY

**Amendment candidate commit**: 42ae9cab6a3ff6d51b51f47a00e37888e13285f1

**Candidate scope verification**: PASS — the diff from immutable A3 starting
commit `d538004b83f9b0f1215a3775043d7ffb44e9b9ea` to the candidate changes
exactly the fifteen fixed-scope paths listed above. Zoe's ownership commit is
merged after this candidate and is not represented as A3 product scope.

**Tasks complete**: YES — T050, T051, T052, T053, T054, and T055 are literally
checked in the candidate's bound task graph; its normalized A3 task manifest
matches SHA256 `7786d2616df7233a313efb694ca58dd9ff07676e4e1bfdb111574dde5966e0a2`.

**Verification commands / results**: PASS — `python3 -m unittest
tests.v2.contract.test_privileged_action_authorization -q` (20 tests, 1
explicit baseline-oracle skip); `python3 -m unittest discover -s
tests/v2/contract -p 'test_*.py'` (215 tests, 4 explicit baseline-oracle
skips); `uv run --offline --isolated --no-project --with
'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p
'test_*.py'` (215 tests, 0 skipped); the matching isolated evidence verifier
(98 + 134 + 184 + 52 records, all mandatory fields); `python3 -m unittest`
(PASS); `python3 scripts/check_governance.py --check-cli` (PASS);
`python3 -m evals.verdict_suite.runner --list` (60 fixtures); and `git diff
--check` (PASS).

**Independent review**: PASS — independent read-only review found and drove
focused fixes for the missing host-only challenge; final decision/recheck
correlation; stale decision and approval-recheck revocation facts; approval
ordering; and challenge-policy provenance. The final targeted re-review
confirmed the approval-recheck freshness repair. The candidate's A3 product
paths retain those reviewed bytes.

**Evidence paths**: `schemas/v2/privileged-action-authorization.schema.json`,
`tests/v2/contract/schema_helpers.py`,
`tests/v2/contract/test_privileged_action_authorization.py`,
`evals/v2/contract/privileged-action-authorization/cases.jsonl`,
`evals/v2/contract/privileged-action-authorization/expected-counts.json`,
`evidence/v2/contract/privileged-action-authorization.jsonl`,
`evidence/v2/contract/README.md`,
`docs/contracts/nunchi-v2.md`, and
`docs/security/privileged-action-authorization.md`.

**Known limitations**: I-010F is a portable contract and deterministic
validator, not a policy store, approval UI, authenticated operator session,
pending-state store, effect executor, or bearer grant; it does not establish
native-event authenticity, operator authentication, durable persistence, or
one actual effect; slice 040 still owns execution-time recheck, cancellation,
one-use consumption, persistence, and effect commitment; and A3 remains
ineffective until separate integrator acceptance.

**Acceptance owner**: v2-integrator

**Acceptance state**: PENDING — this packet requests separate acceptance or
rejection of exactly `42ae9cab6a3ff6d51b51f47a00e37888e13285f1`.

### Documentation freshness — PASS

| Exact path | Disposition | Exact result or routed delta |
|---|---|---|
| `docs/contracts/nunchi-v2.md` | UPDATE | Documents I-010F@1's four closed members, exact binding/digest boundary, approval/recheck rules, limitations, and verified offline command; states implementation complete with acceptance pending, without claiming runtime behavior. |
| `docs/security/privileged-action-authorization.md` | UPDATE | Documents protected assets, host-only authority, safe defaults, replay/expiry/revocation behavior, and limits; its command and claims match the deterministic validator. |
| `evidence/v2/contract/README.md` | UPDATE | Regenerated A3 evidence manifest records the exact corpus counts, validator treatment, commands, and implementation/acceptance boundary. |
| `CHANGELOG.md` | HANDOFF to `v2-integrator` | After acceptance, add an unreleased I-010F@1 entry naming its schema, exact effective commit, and packet; do not claim current V2 runtime, cutover, release, or promotion. |
| `README.md` | HANDOFF to `v2-integrator` | After acceptance, replace only the audited-baseline claim that I-010F is missing with the exact accepted effective commit and packet; retain V1 as current. |
| `docs/governance/execution-spine.md` | HANDOFF to `v2-program-owner` | After ledger acceptance, replace the statement that A3 is the next missing amendment with its exact accepted effective commit and packet; retain each downstream owner's separate acceptance obligation. |
| `AGENTS.md` | NO_IMPACT | Existing accepted-amendment, control-plane, and lifecycle rules already cover A3; no product claim or execution rule changes here. |
| `CLAUDE.md` | NO_IMPACT | A3 changes no Claude execution guidance, runtime dependency, or workflow binding. |
| `docs/INSTALL.md` | NO_IMPACT | No runtime dependency, install step, configuration key, or executable surface changes; JSON Schema remains test-only. |
| `docs/STABILITY.md` | NO_IMPACT | It describes the current V1 public surface; A3 changes no current stability promise. |
| `docs/adapters.md` | NO_IMPACT | No adapter implements I-010F here; enforcement remains owned by slices 040 and 060–110 after acceptance. |
| `docs/architecture/v2-selected-design.md` | NO_IMPACT | The selected design already defines this authorization boundary; A3 implements it without changing selected design. |
| `docs/contracts/channel-adapter-v1.md` | NO_IMPACT | The V1 adapter contract and no-bridge boundary are unchanged. |
| `docs/contracts/verdict-suite-data-model-v1.md` | NO_IMPACT | I-010F carries no V1 verdict-suite field. |
| `docs/contracts/verdict-suite-requirements-v1.md` | NO_IMPACT | A3 neither changes V1 verdict requirements nor uses that suite as authorization evidence. |
| `docs/evaluations/verdict-suite-runner.md` | NO_IMPACT | The V1 runner, inputs, commands, and outputs are unchanged. |
| `docs/evaluations/verdict-suite.md` | NO_IMPACT | The social-verdict corpus remains unchanged and cannot establish privileged-action authority. |
| `docs/integration.md` | NO_IMPACT | A3 is a portable contract only; current V1 integration behavior remains truthful. |
| `docs/integrations/hermes-core-patch-test-plan.md` | NO_IMPACT | No Hermes consumer is implemented by A3. |
| `docs/integrations/hermes-core-patch.md` | NO_IMPACT | The V1 Hermes patch receives no partial V2 authorization claim. |
| `docs/v2-completion-goal.md` | NO_IMPACT | The completion goal already requires these boundaries; A3 supplies one prerequisite without declaring the goal complete. |
