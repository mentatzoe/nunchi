# v2-integrator review — slice 010 attempt-4 candidate rejection

**Slice**: `010-v2-contract`

**Candidate commit**: `0596d14c0579b0ad2530c4e273729dcc274f7034`

**Handoff packet commit**: `aa396ffebb552aeee91fd1b6a32a22538b2564c6`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-18

**Decision**: REJECTED

## Decision basis

Attempt 4 closes R7, R8, and R9 from the attempt-3 rejection. Direct schema
and adapter probes confirm the corrected complete operational-error object,
the open string error code, omission-only unknown timestamps, actor-reference
integrity, and shared nested `Self`/`Room` validation for requests and wake
packets. The 19 authority-conformance red-run counts are genuine, the corpus
and evidence inventories reconcile, and the complete packet verification
stack is green.

The candidate still cannot be accepted because R10 is only partially closed.
The new fetch checks compare a well-formed issued-state fixture with the host
context, requested direction, and requested budgets, but the runtime adapter
does not validate that the issued continuation is itself a complete, typed
capability from the selected design. It also changes the selected optional
expiry into a mandatory runtime field.

### R10 remains open — the issued continuation capability is not validated (HIGH)

The selected design at `c834e8c`, under **Trigger, coverage, and
continuation**, defines `ContextContinuation` with all of these required
members:

- non-empty handle identity;
- exact `bound_to` identity for participant, room, continuity scope, and
  trigger event;
- three boolean direction capabilities;
- positive integer event and byte caps.

The same selected shape declares `expires_at?: string`, so an issued
capability without an expiry is valid. The selected request example itself
demonstrates a complete continuation with no `expires_at` member.

`validate_continuation_fetch` does not pass each issued state through the
existing `_check_continuation` rules or an equivalent host-state validator.
Instead it reads individual fields opportunistically. Missing or mistyped
required members are therefore skipped by the binding, direction, and cap
comparisons. Conversely, it unconditionally parses `state.get("expires_at")`
and emits an error when the selected optional member is absent. Its timestamp
comparison can also raise rather than return a validation error when one
otherwise parseable timestamp has no UTC offset.

Independent probes against the exact candidate produced these outcomes:

- removing `expires_at` from an otherwise valid issued continuation returned
  one error, `fetch.issued.expires_at: must be an ISO 8601 timestamp`, although
  the selected field is optional;
- removing `max_events_per_fetch` returned zero errors;
- replacing `max_events_per_fetch` with the string `"20"` returned zero
  errors;
- removing `participant_id` from both `bound_to` and `host_context` returned
  zero errors, so two equally incomplete objects pass the equality check;
- replacing `can_fetch_before: true` with the string `"yes"` returned zero
  errors because truthiness substitutes for the required boolean type; and
- an offset-aware fetch time compared with the parseable offset-naive expiry
  `2026-07-17T02:00:00` raised an uncaught `TypeError`.

The eight landed `binding-expiry` cases all retain the same fully formed,
UTC-expiring issued-state fixture. The four new R10 cases alter only host
context, requested direction, or requested budgets, so they do prove those
comparisons for a valid capability but do not exercise the issued-state
contract. A dependency-free host using the adapter can therefore accept an
incomplete or wrongly typed capability, reject an authority-valid no-expiry
capability, or crash during validation.

## Cleared attempt-3 blockers

- **R7 — CLEARED**: both decision and receipt errors require string `code` and
  string `detail`; arbitrary string codes validate; explicit null event
  timestamps reject. Independent positive and negative probes agree with the
  selected design.
- **R8 — CLEARED**: the new `actor-reference-integrity` partition validates
  self and every typed-event actor reference against the actor map. Its nine
  cases cover the stated valid and invalid relationships.
- **R9 — CLEARED**: request and wake validation reuse `_check_self` and
  `_check_room`; a wake with malformed optional nested fields now produces the
  same two errors under the stdlib adapter as under Draft 2020-12.
- **R10 — PARTIALLY CLEARED**: exact host-context equality, direction
  authorization, and request-versus-cap comparisons work when the issued
  capability is already complete and well typed. The blocker above is the
  missing validation of that precondition and the incorrect expiry handling.

## Verification performed

- At packet commit `aa396ffebb552aeee91fd1b6a32a22538b2564c6`:
  `python3 scripts/check_governance.py` — PASS,
  `governance boundary: OK (SpecKit 0.12.11)`.
- At the same packet commit: `python3 -m unittest` — PASS, 1236 tests,
  11 skipped.
- At the same packet commit:
  `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 178 tests, 0 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- `git diff --check` for attempt-3 rejection to candidate and candidate to
  packet — PASS.
- The packet commit changes only lifecycle evidence and SpecKit control-plane
  files after candidate commit `0596d14`; it changes no product schema,
  adapter, test, corpus, or product documentation.
- Landed evidence verification — PASS: 98 attention-request, 132
  attention-decision, and 150 downstream records carry all mandatory fields;
  all 380 records report `match: true`.
- Independent red-run reproduction used the exact five schemas from
  attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de`
  for the 14 carried authority cases and the exact schemas from attempt-3
  candidate commit `7f9e81460d570e078c4bcbacb138f81c1b291455`
  for the five new cases, under `jsonschema==4.26.0`. All 19 manifest counts
  matched exactly: request `26/40/36/31` plus `0/0`, decision `1/1/1/1` plus
  `0`, and downstream `1/1/6/4/3/4` plus `1/0`.
- Manual comparison with the selected design at `c834e8c` and independent
  current-adapter probes — FAIL only as the remaining R10 defect describes.

## Required rework path

The source owner must return the slice declarations to `ACTIVE` while
preserving all four candidate/handoff attempts and rejection records. The
next correction must:

1. validate every issued handle state as the complete selected
   `ContextContinuation` capability, while allowing its host-only cursor list
   as separate state;
2. validate `host_context` independently as the exact closed four-field
   binding shape before comparing it with `bound_to`;
3. accept an absent `expires_at`, validate and compare it only when present,
   and turn incompatible/invalid timestamp forms into returned validation
   errors rather than exceptions; and
4. add binding-expiry corpus and unit cases for a valid no-expiry capability,
   missing/mistyped binding fields, missing/mistyped direction flags,
   missing/mistyped caps, and safe timestamp comparison, then regenerate the
   evidence and manifest.

After that focused correction, append a new exact candidate and handoff packet
for a separate integrator review. R7, R8, and R9 do not need another redesign;
their regression coverage should remain intact.
