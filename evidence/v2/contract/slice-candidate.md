# Candidate attempts (append-only)

## Attempt 1 — CONVERGED

**Slice**: `010-v2-contract`

**Status**: CONVERGED

**Candidate commit**: `81483ce017eb834c5ab533556fa64cd62a8cf2aa`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024

**Tasks SHA256**: bbbbc8114b0722239c842430a9f7e1a7a3bcaafbc011dcc0ce3180a7ee9e4be3

**Verification commands / results**: PASS — `python3 -m unittest` — 1208 tests, OK,
11 skipped (8 pre-existing + 3 counted oracle-absent classes per the FR-012
skip regime); `uv run --offline --with 'jsonschema==4.26.0' python -m
unittest discover -s tests/v2/contract -p 'test_*.py'` — 151 tests, OK, 0
skipped (full dual-validator corpus); `python3 scripts/check_governance.py`
— boundary OK; converge assessment — 0 missing / 0 partial / 0 contradicts /
0 unrequested, no tasks appended.

**Interface versions**: I-010A AttentionRequestV2@1, I-010B
AttentionDecisionV2@1, I-010C ParticipantWakeV2@1, I-010D
ContextContinuationV2@1, I-010E AttentionReceiptV2@1 — at the five exact
`schemas/v2/*.schema.json` paths.

**Evidence paths**: evidence/v2/contract/attention-request.jsonl,
evidence/v2/contract/attention-decision.jsonl,
evidence/v2/contract/downstream.jsonl, evidence/v2/contract/README.md,
evidence/v2/contract/checklist-adjudication.md,
evidence/v2/contract/handoff.md, evidence/v2/contract/slice-activation.md

**Known limitations**: semantic/relational invalid classes are
runtime-adapter-only per the FR-012 expressiveness partition (the Draft
2020-12 oracle cannot express them); plain-baseline runs skip the three
oracle-dependent classes with counted, asserted skips; downstream consumers
must pass the identical corpus revision named in the T019 packet before
their own handoffs; running the pinned uv command generates an untracked
`uv.lock` at the repo root (delete to restore a clean tree); schema $id
values use the placeholder domain `nunchi.invalid` pending any future
canonical-host decision (identifiers only, never dereferenced).

## Attempt 2 — CONVERGED

**Slice**: `010-v2-contract`

**Status**: CONVERGED

**Candidate commit**: `001fdf85acd5098264c4975559c97114aa7278af`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034

**Tasks SHA256**: 9a5ad119df63479e0eab20c66b91bd6909dbf063f73b247bd3a57c3f572a3a3f

**Verification commands / results**: PASS — `python3 -m unittest` — 1225 tests, OK,
11 skipped (8 pre-existing + 3 counted oracle-absent classes per the FR-012
skip regime); `uv run --offline --with 'jsonschema==4.26.0' python -m
unittest discover -s tests/v2/contract -p 'test_*.py'` — 167 tests, OK, 0
skipped (full dual-validator corpus including the attempt-2 conditional
FR-007, routing-audit cross-field, and per-record stage-to-writer cases);
`python3 scripts/check_governance.py` — boundary OK; the three attempt-1
rejection probes re-verified directly — a valid `WAKE` with routing
`margin_status` validates, a valid `WAKE` without a legacy vector validates,
a margin-active candidate `SUPPRESS` without the vector and a forged
cross-owner receipt record are both rejected by both validators; converge
assessment — 0 missing / 0 partial / 0 contradicts / 0 unrequested, no tasks
appended.

**Interface versions**: I-010A AttentionRequestV2@1, I-010B
AttentionDecisionV2@1, I-010C ParticipantWakeV2@1, I-010D
ContextContinuationV2@1, I-010E AttentionReceiptV2@1 — at the five exact
`schemas/v2/*.schema.json` paths (I-010B and I-010E reworked in place for
rejection findings R2 and R3; `@1` retained per the FR-011 pre-acceptance
rework rule).

**Evidence paths**: evidence/v2/contract/attention-request.jsonl,
evidence/v2/contract/attention-decision.jsonl,
evidence/v2/contract/downstream.jsonl, evidence/v2/contract/README.md,
evidence/v2/contract/checklist-adjudication.md,
evidence/v2/contract/handoff.md, evidence/v2/contract/slice-activation.md

**Known limitations**: semantic/relational invalid classes are
runtime-adapter-only per the FR-012 expressiveness partition (the Draft
2020-12 oracle cannot express them); plain-baseline runs skip the three
oracle-dependent classes with counted, asserted skips; downstream consumers
must pass the identical corpus revision named in the T034 packet input
before their own handoffs; running the pinned uv command generates an
untracked `uv.lock` at the repo root (delete to restore a clean tree);
schema $id values use the placeholder domain `nunchi.invalid` pending any
future canonical-host decision (identifiers only, never dereferenced).
