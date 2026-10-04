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

## Attempt 3 — CONVERGED

**Slice**: `010-v2-contract`

**Status**: CONVERGED

**Candidate commit**: `7f9e81460d570e078c4bcbacb138f81c1b291455`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045, T046

**Tasks SHA256**: 3001cefc6fd5fba395e4db5d75151479c0bea9bf625a3b55dd2924ebfcff6db7

**Verification commands / results**: PASS — `python3 -m unittest` — 1222 tests, OK,
11 skipped (8 pre-existing + 3 counted oracle-absent classes per the FR-012
skip regime); `uv run --offline --with 'jsonschema==4.26.0' python -m
unittest discover -s tests/v2/contract -p 'test_*.py'` — 164 tests, OK, 0
skipped (full dual-validator corpus including all 14 FR-014
authority-conformance cases); `python3 scripts/check_governance.py` —
boundary OK; the design's own example attention request and every other
authority-conformance document verified verbatim/field-complete against
both validators (0 failures); converge assessment — 0 missing / 0 partial
/ 0 contradicts / 0 unrequested, no tasks appended beyond the T046
checklist-driven append already reflected above.

**Interface versions**: I-010A AttentionRequestV2@1, I-010B
AttentionDecisionV2@1, I-010C ParticipantWakeV2@1, I-010D
ContextContinuationV2@1, I-010E AttentionReceiptV2@1 — at the five exact
`schemas/v2/*.schema.json` paths (all five reworked in place to the
selected-design field inventory for rejection finding R4; `@1` retained
per the FR-011 pre-acceptance rework rule).

**Evidence paths**: evidence/v2/contract/attention-request.jsonl,
evidence/v2/contract/attention-decision.jsonl,
evidence/v2/contract/downstream.jsonl, evidence/v2/contract/README.md,
evidence/v2/contract/checklist-adjudication.md,
evidence/v2/contract/handoff.md, evidence/v2/contract/slice-activation.md

**Known limitations**: semantic/relational invalid classes are
runtime-adapter-only per the FR-012 expressiveness partition (the Draft
2020-12 oracle cannot express them); plain-baseline runs skip the three
oracle-dependent classes with counted, asserted skips; downstream consumers
must pass the identical corpus revision named in the T045 packet input
before their own handoffs; running the pinned uv command generates an
untracked `uv.lock` at the repo root (delete to restore a clean tree);
schema $id values use the placeholder domain `nunchi.invalid` pending any
future canonical-host decision (identifiers only, never dereferenced); the
`binding-expiry` invalid coverage narrows from 4 to 3 cases because
`ContextFetch` carries no inline binding field to cross-check under the
selected design (not a silent shrink — see the T045 packet's known
limitations); the classifier-facing redaction of `I-010A`'s optional
`continuation` field is enforced at the runtime layer, not the wire
schema.

## Attempt 4 — CONVERGED

**Slice**: `010-v2-contract`

**Status**: CONVERGED

**Candidate commit**: `0596d14c0579b0ad2530c4e273729dcc274f7034`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045, T046, T047

**Tasks SHA256**: 4898165698dc127779e5798af5292ca48fd648f69164c8cd95969aa7947d767b

**Verification commands / results**: PASS — `python3 -m unittest` — 1236
tests, OK, 11 skipped (8 pre-existing + 3 counted oracle-absent classes per
the FR-012 skip regime); `uv run --offline --with 'jsonschema==4.26.0'
python -m unittest discover -s tests/v2/contract -p 'test_*.py'` — 178
tests, OK, 0 skipped (full dual-validator corpus including the new
`actor-reference-integrity` class); `python3 scripts/check_governance.py
--check-cli` — boundary + CLI OK; each of the four rejection findings
re-verified directly against the fixed tree — `{code, detail}` both
required and `code` an open string on the decision and receipt error
bodies; a self or event actor reference absent from `actors` rejects on
both `AttentionRequestV2` and `ParticipantWakeV2`; the wake validator's
nested optional fields (`self.names`/`role`/`description`,
`room.name`/`room.kind`) now reject malformed values exactly like the
request validator; a fetch's host context mismatch, unauthorized
direction, or cap overrun against the issued capability rejects — converge
assessment — 0 missing / 0 partial / 0 contradicts / 0 unrequested beyond
the T047 append itself.

**Interface versions**: I-010A AttentionRequestV2@1, I-010B
AttentionDecisionV2@1, I-010C ParticipantWakeV2@1, I-010D
ContextContinuationV2@1, I-010E AttentionReceiptV2@1 — at the five exact
`schemas/v2/*.schema.json` paths (attention-decision, attention-receipt,
and attention-request reworked in place for rejection findings R7 and R8;
`@1` retained per the FR-011 pre-acceptance rework rule).

**Evidence paths**: evidence/v2/contract/attention-request.jsonl,
evidence/v2/contract/attention-decision.jsonl,
evidence/v2/contract/downstream.jsonl, evidence/v2/contract/README.md,
evidence/v2/contract/checklist-adjudication.md,
evidence/v2/contract/handoff.md, evidence/v2/contract/slice-activation.md

**Known limitations**: semantic/relational invalid classes are
runtime-adapter-only per the FR-012 expressiveness partition (the Draft
2020-12 oracle cannot express them), now including the new
`actor-reference-integrity` class; plain-baseline runs skip the three
oracle-dependent classes with counted, asserted skips; downstream consumers
must pass the identical corpus revision named in the T047 packet input
before their own handoffs; running the pinned uv command generates an
untracked `uv.lock` at the repo root (delete to restore a clean tree);
schema $id values use the placeholder domain `nunchi.invalid` pending any
future canonical-host decision (identifiers only, never dereferenced); the
`binding-expiry` invalid coverage widens from 3 to 7 cases because the
issued capability's exact binding, direction authorization, and per-fetch
caps are now checked explicitly (R10) rather than treating a known,
unexpired handle as correct by construction.

## Attempt 5 — CONVERGED

**Slice**: `010-v2-contract`

**Status**: CONVERGED

**Candidate commit**: `1709c714717cd2735da2e9e08487fe8f02f2b930`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045, T046, T047, T048

**Tasks SHA256**: a38f76059461ae286850fabbe3ce03426cc8bc6ee916391b272c325f40d3e19b

**Verification commands / results**: PASS — `python3 -m unittest` — 1242
tests, OK, 11 skipped (8 pre-existing + 3 counted oracle-absent classes per
the FR-012 skip regime); `uv run --offline --with 'jsonschema==4.26.0'
python -m unittest discover -s tests/v2/contract -p 'test_*.py'` — 184
tests, OK, 0 skipped; `python3 scripts/check_governance.py --check-cli` —
boundary + CLI OK; each of the six attempt-4 R10 probes re-verified
directly against the fixed tree — a missing/mistyped required capability
member (`bound_to` field, direction flag, or per-fetch cap) rejects instead
of being silently skipped; two equally incomplete `bound_to`/`host_context`
objects no longer pass by matching each other; an absent `expires_at`
validates (the selected member is optional); a mixed timezone-aware/naive
timestamp comparison returns a validation error instead of raising —
converge assessment — 0 missing / 0 partial / 0 contradicts / 0
unrequested beyond the T048 append itself.

**Interface versions**: I-010A AttentionRequestV2@1, I-010B
AttentionDecisionV2@1, I-010C ParticipantWakeV2@1, I-010D
ContextContinuationV2@1, I-010E AttentionReceiptV2@1 — at the five exact
`schemas/v2/*.schema.json` paths (no schema file changed this attempt;
R10 completion is entirely a `tests/v2/contract/schema_helpers.py` runtime-
adapter fix; `@1` retained per the FR-011 pre-acceptance rework rule).

**Evidence paths**: evidence/v2/contract/attention-request.jsonl,
evidence/v2/contract/attention-decision.jsonl,
evidence/v2/contract/downstream.jsonl, evidence/v2/contract/README.md,
evidence/v2/contract/checklist-adjudication.md,
evidence/v2/contract/handoff.md, evidence/v2/contract/slice-activation.md

**Known limitations**: semantic/relational invalid classes are
runtime-adapter-only per the FR-012 expressiveness partition (the Draft
2020-12 oracle cannot express them); plain-baseline runs skip the three
oracle-dependent classes with counted, asserted skips; downstream consumers
must pass the identical corpus revision named in the T048 packet input
before their own handoffs; running the pinned uv command generates an
untracked `uv.lock` at the repo root (delete to restore a clean tree);
schema $id values use the placeholder domain `nunchi.invalid` pending any
future canonical-host decision (identifiers only, never dereferenced); the
`binding-expiry` invalid coverage widens from 7 to 13 cases this attempt
because every issued handle state is now validated as the complete
selected `ContextContinuation` capability rather than read opportunistically
field-by-field.

## Attempt 6 — CONVERGED

**Slice**: `010-v2-contract`

**Status**: CONVERGED

**Candidate commit**: `bff6b463a44c1b9066fc654691042f9550da6c64`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045, T046, T047, T048, T049

**Tasks SHA256**: aab8dbc3d648255e3600ce1c3e6d602e3eb161875923c484358a5997b259c9b8

**Verification commands / results**: PASS — `python3 -m unittest` — 1249
tests, OK, 11 skipped (8 pre-existing + 3 counted oracle-absent classes per
the FR-012 skip regime); `uv run --offline --with 'jsonschema==4.26.0'
python -m unittest discover -s tests/v2/contract -p 'test_*.py'` — 191
tests, OK, 0 skipped; `python3 scripts/check_governance.py --check-cli` —
boundary + CLI OK; each of the six attempt-5 R11 probes re-verified
directly against the fixed tree — an array/object request `handle_id` or
`direction`, and an array/object issued `handle_id`, all return a
validation error instead of raising `TypeError`; a duplicate issued
`handle_id` with a conflicting `bound_to` rejects rather than resolving
last-write-wins — converge assessment — 0 missing / 0 partial / 0
contradicts / 0 unrequested beyond the T049 append itself.

**Interface versions**: I-010A AttentionRequestV2@1, I-010B
AttentionDecisionV2@1, I-010C ParticipantWakeV2@1, I-010D
ContextContinuationV2@1, I-010E AttentionReceiptV2@1 — at the five exact
`schemas/v2/*.schema.json` paths (no schema file changed this attempt; R11
is entirely a `tests/v2/contract/schema_helpers.py` runtime-adapter fix;
`@1` retained per the FR-011 pre-acceptance rework rule).

**Evidence paths**: evidence/v2/contract/attention-request.jsonl,
evidence/v2/contract/attention-decision.jsonl,
evidence/v2/contract/downstream.jsonl, evidence/v2/contract/README.md,
evidence/v2/contract/checklist-adjudication.md,
evidence/v2/contract/handoff.md, evidence/v2/contract/slice-activation.md

**Known limitations**: semantic/relational invalid classes are
runtime-adapter-only per the FR-012 expressiveness partition (the Draft
2020-12 oracle cannot express them); plain-baseline runs skip the three
oracle-dependent classes with counted, asserted skips; downstream consumers
must pass the identical corpus revision named in the T049 packet input
before their own handoffs; running the pinned uv command generates an
untracked `uv.lock` at the repo root (delete to restore a clean tree);
schema $id values use the placeholder domain `nunchi.invalid` pending any
future canonical-host decision (identifiers only, never dereferenced); the
`binding-expiry` invalid coverage widens from 13 to 18 cases this attempt
because a malformed or duplicate handle identity now returns a validation
error at every lookup site instead of only being caught for well-typed,
unique identities.
