---
description: "Slice delivery task list for blocking V2 security and provenance assurance (dormant until authorized)"
---

# Tasks: V2 Security and Runtime Provenance Assurance

**Slice state**: `PLANNED`

**Program implementation authority**: `NOT_GRANTED`

**Assigned participant / source**: `UNASSIGNED` — may be replaced during
planning, before implementation authority, only from a durable external
assignment source; activation evidence later copies and attests it when
establishing `READY`

**SpecKit binding**: `python3 scripts/run_slice_workflow.py run speckit specs/100-v2-security-provenance`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Input**: Existing slice design documents from `specs/100-v2-security-provenance/`

**Execution status**: `DORMANT` while the slice remains `PLANNED`

**Activation prerequisites**: the one valid complete
`evidence/governance/v2-implementation-authorization.md` enumerating exactly
slices `010` through `110`; accepted declared handoffs from slices `010` through `090`;
`v2-security-owner` active; assigned participant and durable external assignment
source declared above; zero CRITICAL/HIGH analysis findings; and an isolated
owner worktree

**Activation evidence**: `evidence/v2/security/slice-activation.md`, written only
after every activation prerequisite is accepted; it copies and attests the
assignment declaration and all other prerequisite facts, establishing `READY`
before `ACTIVE` or any implementation checkbox

**Dependency evidence contract**: the activation record MUST preserve declared
order in `Accepted dependencies`, record ordered `Dependency commits` as
`slice=full-sha`, and record matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Candidate evidence**: `evidence/v2/security/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/security/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/security/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Rejection / rework**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

**Accountable owner lane**: `v2-security-owner`

**Integration handoff**: `v2-integrator` / slice `110-v2-parity-cutover`

**Slice activation**: No checkbox may begin while the slice is `PLANNED` or
before valid activation evidence attests the accepted prerequisites above and
establishes `READY`. The assigned participant must then declare `ACTIVE` before
beginning the first checkbox. This planning baseline creates no product behavior
or implementation authority.

**Ownership boundary**: This lane owns assurance tests/eval tooling, evidence,
threat/security documentation, mitigation handbacks, and re-audit. Product
contracts, source, observation, core, wake, transport, harnesses, and adapters
remain owned by slices `010`–`090`.

## Phase 1: Activation Attestation and Audited-Commit Admission

- [ ] T001 Validate the readiness attestation in `evidence/v2/security/slice-activation.md`, including the one valid complete program implementation-authority record enumerating exactly slices `010` through `110`, accepted dependencies, active `v2-security-owner`, the assigned participant and durable assignment source, zero CRITICAL/HIGH analysis findings, and the isolated worktree; confirm that the record attests prerequisites and grants no authority
- [ ] T002 Validate the exact accepted commits/package refs, canonical `I-010A`–`I-050A` versions, evidence manifests, commands/results, provenance, and limitations from slices `010` through `090` in `evidence/v2/security/upstream-handoffs.json`
- [ ] T003 Verify `.worktrees/v2-security-provenance/` on branch `v2/security-provenance` is isolated and non-releaseable, consumes every exact accepted `010`–`090` commit only through immutable refs recorded in `evidence/v2/security/upstream-handoffs.json`, and creates no program integration or cutover artifact

**Checkpoint**: Stop if activation evidence is absent or invalid, or if any
handoff is incomplete, stale, or incompatible with the canonical registry.

---

## Phase 2: Foundational Assurance Contract and Threat Inventory

- [ ] T004 Define the V2 security assurance report, mitigation-handback record, re-audit disposition, and readiness packet fields in `docs/security/assurance-handoffs.md`
- [ ] T005 [P] Add canonical-interface, trusted-bypass, immutable request-correlated receipt-stage ownership, SEC-C manifest trusted-provenance/`classifier_not_invoked`/classifier-call-count field validation, audited-commit-set, handoff-completeness, and no-parallel-contract assurance tests in `tests/v2/security/test_handoffs.py`
- [ ] T006 Draft stable threat IDs, trust boundaries, threat-to-requirement mapping, mitigation bar, and residual-risk rule in `docs/security/threat-model-v2.md`
- [ ] T007 [P] Define reporting policy, supported security claims, and credential-disclosure guidance in `SECURITY.md`

**Checkpoint**: The assurance plan consumes rather than extends canonical
interfaces, and every threat has a stable ownerable finding shape.

---

## Phase 3: User Story 1 - Assure Governed Suppression (Priority: P1) 🎯 MVP

**Independent Test**: Exact upstream commits pass S04, S05, S08, and S16 before
and after revocation/restart; any failed control becomes an owner handback, not a
slice-`100` product patch.

- [ ] T008 [P] [US1] Add authorization, expiry, malformed-state, revocation, and inspection assurance tests in `tests/v2/security/test_suppression_authorization.py`
- [ ] T009 [P] [US1] Add event-A/event-B recovery, restart/backfill, continuation binding, and honest-coverage assurance tests in `tests/v2/security/test_suppression_recoverability.py`
- [ ] T010 [P] [US1] Add S01-S08 exact-binding, continuation-binding, Claude/Station scars, advice isolation, trusted-bypass zero-call/no-fabricated-result, valid bypass silence, uncertainty-widens-attention, and no-registry/no-ledger assurance scenes in `tests/v2/security/test_governed_suppression.py`
- [ ] T011 [US1] Run T008-T010 against the exact accepted commits and record governed-suppression commands, receipts, coverage, and failures under `evidence/v2/security/governed-suppression/` plus SEC-C trusted-bypass zero-call/no-fabricated-result records with stable `scene_id`, request ID, trusted provenance, and `classifier_not_invoked` under `evidence/v2/security/bypass-receipts/`
- [ ] T012 [US1] Return each failed governed-suppression control to its accountable `010`–`090` owner with affected commit/interface, required mitigation/evidence, and blocking status in `evidence/v2/security/mitigation-handbacks.md`
- [ ] T013 [US1] Accept explicit repaired-commit handoffs from named owners, re-run T008-T011, and record pass/reject dispositions in `evidence/v2/security/re-audit.jsonl`
- [ ] T014 [US1] Document the audited authorization, inspection, revocation, recovery, fail-wake/defer, and known-limitation contract in `docs/security/suppression-governance.md`

**Checkpoint**: Every suppression-capable surface passes or remains blocked;
slice `100` has not edited product source or schemas.

---

## Phase 4: User Story 2 - Assure Runtime, Credentials, and Send Safety (Priority: P1)

**Independent Test**: Exact surface commits reject request-controlled overrides,
redact secrets, separate operational/social telemetry, bound repeated sends, and
fail migrated status for stale wheel/hook/shim/config/process provenance.

- [ ] T015 [P] [US2] Add endpoint, key, executable, identity, redaction, and operator-control assurance tests in `tests/v2/security/test_credential_boundaries.py`
- [ ] T016 [P] [US2] Add repeated-send, error-fallback, bypass-zero-call, participant-silence-no-delivery, request-correlation, immutable single-writer stage, and operational/social-telemetry separation assurance tests in `tests/v2/security/test_operational_send_safety.py`
- [ ] T017 [P] [US2] Add stale wheel, commit, hook, shim, config, restart, and schema-2 probe assurance tests in `tests/v2/security/test_runtime_provenance.py`
- [ ] T018 [US2] Create the assurance-only installed-runtime probe orchestrator, including trusted bypass and four-stage receipt-attestation probes, in `evals/v2/security/runtime_probe.py`
- [ ] T019 [US2] Run T015-T018 against every exact handed-off surface commit, commit redacted provenance results under `evidence/v2/security/provenance/`, and commit SEC-C request-correlated single-writer stage/silence-no-delivery records with stable `scene_id` and stage owner under `evidence/v2/security/bypass-receipts/`
- [ ] T020 [US2] Return every failed credential, send-safety, or provenance control to the named surface/contract owner in `evidence/v2/security/mitigation-handbacks.md`
- [ ] T021 [US2] Re-audit explicit repaired commits and append pass/reject dispositions to `evidence/v2/security/re-audit.jsonl`
- [ ] T022 [US2] Document audited credential, send-safety, install identity, residue removal, restart, and probe requirements in `docs/security/operational-safety.md` and `docs/security/runtime-provenance.md`

**Checkpoint**: Every migrated surface has audited provenance and operational
safety or remains blocking; slice `100` has not wired a surface implementation.

---

## Phase 5: User Story 3 - Close Threats with Adversarial Evidence (Priority: P2)

**Independent Test**: The full adverse matrix is reproducible from committed
inputs, reports failures/flicker honestly, and leaves zero unexplained threats
or unresolved CRITICAL/HIGH findings.

- [ ] T023 [P] [US3] Add stable `scene_id` S01-S16 and SEC-C security variants covering fake authority, forged bypass/`classifier_not_invoked`, cross-owner receipt mutation, speculative future-stage fill, context-handle crossing, advice smuggling, system/governance/verdict/sentinel spoofing, Unicode/Markdown smuggling, hostile history, credential redirection, amplification, context bombs, and sink attacks under `evals/v2/security/fixtures/`
- [ ] T024 [P] [US3] Add loader, redaction, full-matrix, repetition, SEC-C manifest-field, and no-cherry-picking tests in `tests/v2/security/test_eval.py`
- [ ] T025 [US3] Implement the repeatable adverse matrix runner and manifest output in `evals/v2/security/runner.py` after T024 fails as expected
- [ ] T026 [US3] Run Gemini 3.1 Flash Lite, GPT-5.5, and Qwen3 attention families plus each exact installed participant/runtime configuration across every applicable S01-S16/SEC-C security scene for at least five independent repetitions per stochastic model/scene/configuration cell; retain every attempt with exact provider/model ID, timestamp, prompt/config, candidate ref, request ID, stage owner where applicable, and `scene_id` under `evidence/v2/security/adversarial/`, unless Zoe approved a different pre-registered matrix before execution
- [ ] T027 [US3] Return mitigation failures to named owners, accept repaired commits, and re-run affected matrix cells with dispositions in `evidence/v2/security/re-audit.jsonl`
- [ ] T028 [US3] Reconcile every threat to mitigation evidence or a precise pending residual-risk statement in `docs/security/threat-model-v2.md`
- [ ] T029 [US3] Obtain Zoe's explicit acceptance for each remaining residual risk and record only accepted decisions in `evidence/v2/security/risk-acceptance.md`

**Checkpoint**: Any unmitigated and unaccepted risk blocks readiness.

---

## Phase 6: Blocking Readiness Handoff

- [ ] T030 Map S01-S16, SEC-A, SEC-B, and SEC-C to exact candidate refs, commands, record paths, stable `scene_id`, request IDs, stage owners, trusted bypass provenance, `classifier_not_invoked`, classifier-call counts where applicable, stochastic attempt IDs, and pass/block dispositions in `evidence/v2/security/manifest.json`
- [ ] T031 Assemble the V2 security assurance report with audited commit set, canonical interfaces, trusted-bypass and immutable-stage results, commands/results, threat dispositions, mitigation handbacks/re-audits, evidence, provenance, accepted risk, limitations, and manifest coverage in `evidence/v2/security/README.md`
- [ ] T032 Assemble the machine-readable readiness packet referencing those ordinary records and the evidence manifest in `evidence/v2/security/handoff.json`
- [ ] T033 Run `python3 scripts/check_governance.py`, `python3 -m unittest`, and documented security assurance/eval commands and record exact results in `evidence/v2/security/final-verification.txt`
- [ ] T034 Re-run cross-artifact analysis and prepare documentation-freshness inputs by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate each exact security `UPDATE`, route each shared/current-state `HANDOFF` delta (including `README.md`) to its accepting owner, and record zero CRITICAL/HIGH findings plus all proposed documentation dispositions, paths, results, and reviewer in `evidence/v2/security/README.md` for the later workflow gate
- [ ] T035 Prepare the proposed packet input with the exact audited commit/ref set, reusable assurance commands, evidence manifest, V2 security readiness packet, and documentation dispositions in `evidence/v2/security/integrator-handoff.md`; do not record recipient acceptance or rejection in this owner task—the later convergence, documentation-freshness, handoff, and recipient-decision gates own those transitions

---

## Dependencies & Execution Order

- T001-T003 begin only after valid activation evidence establishes `READY`, the
  assigned participant declares `ACTIVE`, and `010`–`090` handoffs are
  accepted.
- T004-T007 block all assurance stories.
- US1 and US2 assurance tests may proceed in parallel against the same pinned
  commit set; owner repairs are explicit handbacks and re-audits.
- US3 depends on the latest accepted re-audited commit set from US1 and US2.
- T030-T035 require every threat/control to pass or have explicit Zoe-accepted
  residual risk.
- Slice `100` depends only on `010`–`090` and feeds `110`; mitigation handbacks
  do not make upstream slices depend on `100`, so the graph remains acyclic.

## Parallel Opportunities

- T005 and T007 may run in parallel.
- T008-T010 are independent assurance files.
- T015-T017 are independent assurance files.
- US1 and US2 may run in parallel under one accountable owner against the same
  immutable audited commit manifest.
- T023 and T024 may run in parallel after the threat catalog is stable.

## Implementation Strategy

1. Stop before T001 until valid activation evidence establishes `READY`, every
   declared prerequisite is accepted, and the assigned participant then
   declares `ACTIVE`.
2. Consume and freeze every exact accepted `010`–`090` commit/package as an
   immutable audited reference in the isolated, non-releaseable slice worktree;
   create no program integration or cutover artifact.
3. Author assurance tests/eval tooling and threat documentation only.
4. Return every failed mitigation to its named implementation owner.
5. Re-audit repaired commits; never implement the repair in slice `100`.
6. Obtain explicit residual-risk decisions.
7. Hand one blocking readiness packet, evidence manifest, reusable assurance
   commands, and audited ref set to `v2-integrator` for assembled-candidate rerun.

## Notes

- Every checkbox is authorized slice implementation; this planning file and its
  activation record grant no program implementation authority.
- `[P]` means distinct files and no dependency on an incomplete task.
- Product source, canonical schemas, and surface wiring are explicitly outside
  this lane.
