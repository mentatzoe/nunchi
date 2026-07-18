# v2-integrator review — slice 010 attempt-6 candidate acceptance

**Slice**: `010-v2-contract`

**Candidate commit**: `bff6b463a44c1b9066fc654691042f9550da6c64`

**Handoff packet commit**: `39deb459c7fb18cf7d64dc0edaaaadcca39eae20`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-18

**Decision**: ACCEPTED

## Decision basis

Attempt 6 closes R11 from the attempt-5 rejection without regressing R7
through R10. Direct comparison with selected design `c834e8c`, independent
runtime probes, corpus inspection, evidence regeneration, and the complete
packet command stack found no remaining acceptance blocker.

`validate_continuation_fetch` now indexes only validated non-empty string
issued-handle identities. Malformed request identities and directions return
the public-document validation errors before any raw value is used as a
dictionary key. Duplicate issued identities are removed from the usable index
and reported as ambiguous, so one opaque handle cannot acquire order-dependent
or conflicting bindings.

The exact six exception probes from attempt 5 now return validation errors
without raising:

- array and object request `handle_id` values;
- array and object request `direction` values; and
- array and object issued-capability `handle_id` values.

The conflicting-duplicate probe also rejects. Additional probes covering an
empty request handle, an integer direction, a null issued handle, identical
duplicates, three duplicates, and a duplicate unrelated to the requested
handle all returned deterministic errors without exceptions. Valid unique
handles remain accepted, and list order no longer selects among duplicate
capabilities.

The six earlier R10 probes also remain correct: optional expiry absence
passes; missing/mistyped capability caps and direction flags reject; equally
incomplete `bound_to` and `host_context` objects reject independently; and
mixed timezone-aware/naive timestamps return a validation error rather than
raising. R7, R8, and R9 remain unchanged and cleared.

## Verification performed

- At packet commit `39deb459c7fb18cf7d64dc0edaaaadcca39eae20`:
  `python3 scripts/check_governance.py` — PASS,
  `governance boundary: OK (SpecKit 0.12.11)`.
- At the same packet commit:
  `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- At the same packet commit: `python3 -m unittest` — PASS, 1249 tests,
  11 skipped.
- At the same packet commit:
  `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 191 tests, 0 skipped.
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures
  discovered.
- `git diff --check` for attempt-5 rejection to candidate and candidate to
  packet — PASS.
- Independent evidence regeneration and verification — PASS: 98
  attention-request, 132 attention-decision, and 174 downstream records;
  all 404 records match and carry every mandatory field.
- Independent red-run reproduction used the exact five schemas from
  attempt-2 packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de`
  for the 14 carried authority cases and the exact schemas from attempt-3
  candidate commit `7f9e81460d570e078c4bcbacb138f81c1b291455`
  for the five later cases, under `jsonschema==4.26.0`. All 19 manifest counts
  matched exactly: request `26/40/36/31` plus `0/0`, decision `1/1/1/1` plus
  `0`, and downstream `1/1/6/4/3/4` plus `1/0`.
- Manual authority comparison with `c834e8c`, the six exact attempt-5
  exception probes, the duplicate-binding probe, additional malformed scalar
  and repeated-duplicate probes, and all six retained R10 probes — PASS.

## Scope and packet notes

The candidate changes only the runtime adapter, its tests and downstream
corpus, and slice control-plane state. The packet commit adds regenerated
aggregate downstream evidence, its manifest, and lifecycle/documentation
evidence; it changes no schema, adapter, test, corpus, or product contract
documentation after the candidate.

The attempt-6 documentation section uses the attempt-5 packet commit rather
than the later attempt-5 rejection commit as one diff base. That broader base
includes the prior rejection review and handoff history, but it omits no
attempt-6 candidate change and does not make either exact commit identity
ambiguous. This is non-blocking.

## Acceptance

Candidate `bff6b463a44c1b9066fc654691042f9550da6c64` with handoff packet
`39deb459c7fb18cf7d64dc0edaaaadcca39eae20` is accepted for slice
`010-v2-contract` by `v2-integrator`.

This acceptance is slice-level only. It does not attest per-consumer upstream
acceptance, atomic V2 cutover, current V2 behavior, release, or promotion.
Those remain owned by their documented downstream lanes and program tail.
