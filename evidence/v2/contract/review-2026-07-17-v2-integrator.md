# v2-integrator review — slice 010 candidate rejection

**Slice**: `010-v2-contract`

**Candidate commit**: `81483ce017eb834c5ab533556fa64cd62a8cf2aa`

**Handoff packet commit**: `9f08124b43ba5beb73c50b876bde51e7b8a1633d`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-17

**Decision**: REJECTED

## Decision basis

The candidate cannot be accepted until every blocker below is repaired in a
new bound slice-`010` delivery run. This report assesses the exact handoff
packet and its named code candidate. It does not change current product truth:
V1 remains current.

### R1 — full baseline fails at the handoff packet (CRITICAL)

From the exact packet commit, `python3 -m unittest` runs 1208 tests and fails
`tests.test_governance.GovernanceBoundaryTests.test_authorized_contract_slice_can_reach_active_end_to_end`.
The test fixture only replaces `PLANNED` state declarations before it writes a
synthetic activation. It therefore leaves the real `HANDOFF_READY` declarations
and lifecycle records in a contradictory synthetic fixture, which produces the
three errors that the latest handoff/candidate records are missing or do not
match.

This violates the required green full offline baseline for a slice handoff.
Make the fixture construct its intended planning baseline independently of the
repository's live slice state, then rerun the complete suite from the new
handoff packet.

### R2 — I-010B cannot represent the selected response contract (CRITICAL)

The selected V2 design makes the legacy confidence vector optional and requires
it for a candidate `SUPPRESS` only while the protective margin remains active.
It also requires the `ok` routing audit to record the valve, override cause,
margin status, effective margin when present, and trusted margin source, with
reasons retained as audit material.

`schemas/v2/attention-decision.schema.json` instead requires
`legacy_confidence` on every `status: "ok"` response and closes `routing` to
only `route` and `override_cause`; it admits neither `margin_status` nor the
other required audit facts, and has no `reasons` field. A Draft 2020-12 probe
therefore rejects both a valid `WAKE` with routing `margin_status` and a valid
`WAKE` without a legacy vector. Align I-010B, its corpus, dual validator,
documentation, and evidence with the selected design before resubmission.

### R3 — I-010E permits cross-owner receipt attestation (CRITICAL)

The public receipt schema accepts a record whose `stage` is `observation` and
whose `writer` is `transport`. The required owner map exists only in
`validate_receipt_stream`, while `validate_attention_receipt` and an ordinary
Draft 2020-12 schema validation accept the individual forged record.

The selected contract requires each immutable receipt stage to be singly
attested by its directly observing owner. Encode the stage-to-writer mapping in
the public schema and individual stdlib validator, add a negative corpus case,
and preserve the stream-level ordering/immutability checks.

## Verification performed

- `git diff --check main...v2/contract` — PASS.
- At `81483ce017eb834c5ab533556fa64cd62a8cf2aa`, after the pinned offline
  validator environment is prepared: `python3 -m unittest` — 1208 tests, OK,
  11 skipped; the dedicated dual-validator suite — 151 tests, OK, 0 skipped;
  `python3 scripts/check_governance.py` — PASS.
- At `9f08124b43ba5beb73c50b876bde51e7b8a1633d`:
  `python3 scripts/check_governance.py` — PASS; `python3 -m unittest` — FAIL,
  one failure as described in R1.
- The published V2 contract documentation preserves the truthful statement
  that V1 remains current; no documentation-current-state finding was made.

## Required rework path

The source owner must return the slice declarations to `ACTIVE` and start a
new bound `run speckit` for `specs/010-v2-contract`; the completed handoff run
must not be resumed. Preserve this rejection and the first candidate/handoff
attempts, then append a new candidate and handoff only after all blockers and
the full handoff-packet baseline are green.
