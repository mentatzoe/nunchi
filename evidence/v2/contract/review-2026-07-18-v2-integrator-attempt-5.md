# v2-integrator review — slice 010 attempt-5 candidate rejection

**Slice**: `010-v2-contract`

**Candidate commit**: `1709c714717cd2735da2e9e08487fe8f02f2b930`

**Handoff packet commit**: `b9ccace4e35ec78f80f73c69d70184e39f99528b`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-18

**Decision**: REJECTED

## Decision basis

Attempt 5 closes the six concrete R10 findings from the attempt-4 rejection.
Direct probes confirm that an issued capability without `expires_at` passes;
missing or mistyped required caps and direction flags reject; equally
incomplete `bound_to` and `host_context` objects reject independently; and a
mixed timezone-aware/naive timestamp pair returns an error instead of raising.
R7, R8, and R9 remain cleared and unchanged. The packet command stack,
evidence inventory, and all 19 authority red-run counts reproduce exactly.

The candidate still cannot be accepted because an additional adversarial pass
found that the repaired fetch validator is not total over JSON-valid malformed
contract input. It records the public schema error and then performs unsafe
dictionary operations with the invalid value, raising `TypeError` instead of
returning validation errors. The same lookup also silently makes duplicate
issued handle identities last-write-wins, defeating a single exact binding.

### R11 — unsafe and ambiguous handle indexing after validation errors (HIGH)

The selected design at `c834e8c` defines `ContextFetch.handle_id` as a string
and `direction` as one of `before`, `after`, or `around`. It defines an issued
`ContextContinuation.handle_id` as a string and says the host-issued handle is
bound to the exact participant, room, continuity scope, and trigger. The
runtime adapter is responsible for rejecting malformed values and enforcing
that exact binding; a malformed fetch must not escape the validation path as
an exception.

`validate_continuation_fetch` first calls `validate_context_continuation`,
which correctly reports a non-string `handle_id` or invalid `direction`.
However, the function continues into:

- a dictionary comprehension keyed by every raw issued `handle_id`;
- `by_handle.get(request.get("handle_id"))`; and
- a direction-capability dictionary lookup keyed by the raw request
  `direction`.

JSON arrays and objects are unhashable Python values. Independent probes at
the exact candidate produced all of these uncaught failures:

- request `handle_id: []` — `TypeError: cannot use 'list' as a dict key`;
- request `handle_id: {}` — `TypeError: cannot use 'dict' as a dict key`;
- request `direction: []` — the same list-key `TypeError`;
- request `direction: {}` — the same dict-key `TypeError`;
- issued capability `handle_id: []` — the same list-key `TypeError`; and
- issued capability `handle_id: {}` — the same dict-key `TypeError`.

The standalone public-document adapter already returns the correct ordinary
validation messages (`handle_id` must be a non-empty string, and `direction`
must be one of the three selected values) for the first four inputs. The
exception therefore comes only from continuing after a known validation
failure, not from an inability to classify the malformed document.

A separate probe appended a second individually valid issued capability with
the same `handle_id` but a conflicting `bound_to`, then supplied the host
context matching the last entry. The function returned zero errors because
the dictionary comprehension silently overwrote the first capability. A
host-issued opaque handle cannot be exactly bound to two different contexts;
duplicate identities must reject rather than acquire order-dependent meaning.

The six new unit tests and seven new `binding-expiry` corpus cases exercise the
attempt-4 examples, but they keep `handle_id` and `direction` as valid strings
and never create a duplicate issued identity. The green suite therefore does
not reach either R11 path.

## Cleared prior blockers

- **R7 — CLEARED**: complete error objects, open string codes, and
  omission-only unknown timestamps remain correct.
- **R8 — CLEARED**: actor-map key and typed actor-reference integrity remain
  enforced by the landed relational partition.
- **R9 — CLEARED**: request and wake packets continue to share complete
  `Self` and `Room` validation.
- **R10 — CLEARED**: every issued state is checked against the selected
  capability shape; `host_context` is checked independently before equality;
  optional expiry is honored; mixed timezone forms return an error; and the
  original binding, direction, and cap comparisons remain effective for
  well-typed identities.

## Verification performed

- At packet commit `b9ccace4e35ec78f80f73c69d70184e39f99528b`:
  `python3 scripts/check_governance.py` — PASS,
  `governance boundary: OK (SpecKit 0.12.11)`.
- At the same packet commit:
  `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- At the same packet commit: `python3 -m unittest` — PASS, 1242 tests,
  11 skipped.
- At the same packet commit:
  `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 184 tests, 0 skipped.
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures
  discovered.
- `git diff --check` for attempt-4 rejection to candidate and candidate to
  packet — PASS.
- The packet commit changes only lifecycle evidence and SpecKit control-plane
  files after candidate commit `1709c714`; it changes no product schema,
  adapter, test, corpus, or product documentation.
- Landed evidence verification — PASS: 98 attention-request, 132
  attention-decision, and 164 downstream records carry all mandatory fields;
  all 394 records report `match: true`.
- Independent red-run reproduction used the exact five schemas from
  attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de`
  for the 14 carried authority cases and the exact schemas from attempt-3
  candidate commit `7f9e81460d570e078c4bcbacb138f81c1b291455`
  for the five later cases, under `jsonschema==4.26.0`. All 19 manifest counts
  matched exactly: request `26/40/36/31` plus `0/0`, decision `1/1/1/1` plus
  `0`, and downstream `1/1/6/4/3/4` plus `1/0`.
- Manual comparison with selected design `c834e8c` and the six exact
  attempt-4 probes — PASS.
- Additional malformed-identity, malformed-direction, and duplicate-handle
  probes — FAIL as R11 describes.

## Required rework path

The source owner must return the slice declarations to `ACTIVE` while
preserving all five candidate/handoff attempts and rejection records. The
next focused correction must:

1. stop fetch-time processing after public request-shape errors, or otherwise
   guard every lookup so malformed request values always return validation
   errors and never become dictionary keys;
2. build the issued-handle index only from validated non-empty string handle
   IDs, while retaining the errors from every malformed issued state;
3. reject duplicate issued handle IDs before lookup so one opaque handle can
   have only one exact capability and binding; and
4. add regression coverage for array/object request handle IDs and directions,
   array/object issued handle IDs, and duplicate conflicting handle bindings,
   then regenerate affected evidence and the manifest.

After that correction, append a new exact candidate and handoff packet for a
separate integrator review. R7 through R10 do not need redesign; their current
regression coverage should remain intact.
