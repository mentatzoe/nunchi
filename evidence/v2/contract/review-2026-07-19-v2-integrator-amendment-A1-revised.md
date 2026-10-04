# v2-integrator re-review — slice 010 amendment A1 revised candidate

**Slice**: `010-v2-contract`

**Amendment candidate commit**: `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Amendment record commit**: `6296316fd415e85762860569289016a675ab5d2d`

**Amendment record**: `evidence/v2/contract/amendment-A1-receipt-policy-provenance.md`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-19

**Decision**: ACCEPTED

## Decision basis

The revised A1 candidate matches the Zoe-selected design at `c834e8c` without
broadening or narrowing it:

- every classifier-outcome attention receipt requires the same non-empty
  `policy_provenance` concept already used by the trusted-bypass receipt;
- the operational-error body keeps the shared `WAKE` default implicit through
  absence of override fields;
- the only separately receipted error-policy override is the paired
  `wake_action: "NO_WAKE"` plus non-empty `policy_provenance`;
- either field alone, `WAKE`, or another action rejects under both validators;
  and
- I-010B remains at `@1`: its response audit owns routing and transition-margin
  facts, while the selected general policy-provenance and operational-override
  requirements are explicitly receipt requirements owned by I-010E.

The original A1 additions and the A1-R1 correction therefore represent exactly
the missing selected-design facts. They do not create a social disposition,
reuse `error.detail`, classifier identity, or `margin_source`, or expose a
general policy library.

## A1-R1 closure

The rejection at
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A1.md`
required the override discriminator to close to `NO_WAKE`, a negative
dual-validator case for `WAKE`, regenerated evidence, and correction of the
stale test-module interface citation.

Candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb` completes all of that:

- the Draft 2020-12 schema uses `"wake_action": {"const": "NO_WAKE"}`;
- the stdlib mirror accepts only the identical string;
- unit test `test_error_override_wake_action_rejects_wake` and corpus case
  `DWN-S06-115` prove `WAKE` plus provenance invalid in both validators;
- the test module docstring cites I-010E `@2`; and
- `docs/contracts/nunchi-v2.md` now states the split interface inventory
  consistently in its title, field-authority sentence, table, and I-010E
  section.

Independent probes returned the same verdict under the stdlib mirror and
pinned Draft 2020-12 oracle:

- default error with neither override field — valid;
- `NO_WAKE` plus provenance — valid;
- `WAKE` plus provenance — invalid;
- another action plus provenance — invalid; and
- either member of the pair alone — invalid.

## R7–R11 regression audit

All five previously cleared findings remain closed:

- **R7**: decision and receipt errors still require the complete `{code,
  detail}` object; `code` remains an open non-empty string.
- **R8**: exact self/actor-map and typed actor-reference integrity are
  unchanged.
- **R9**: request and participant-wake retain shared complete `Self`/`Room`
  validation.
- **R10**: issued continuation shape, exact binding, direction, caps, optional
  expiry, and safe timestamp handling are unchanged.
- **R11**: malformed request/capability identities and directions, plus
  duplicate issued identities, remain total and deterministically rejected.

No request, decision, continuation, or participant-wake schema changes in the
focused correction. Its executable stdlib edit remains confined to the
attention receipt body mirror. The retained focused regression selection passed
59 tests under both validators.

## Verification performed

The amendment commands were reproduced from a detached worktree at the exact
candidate commit:

- `python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'` — PASS,
  194 tests, 3 skipped (`baseline-oracle-absence`).
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover
  -s tests/v2/contract -p 'test_*.py'` — PASS, 194 tests, 0 skipped.
- `python3 -m unittest` — PASS, 1252 tests, 11 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- `uv run --offline --with 'jsonschema==4.26.0' python -m
  tests.v2.contract.schema_helpers --write-evidence` — PASS: 98 request, 132
  decision, and 184 downstream records, 0 mismatched; regeneration produced no
  tracked evidence diff.
- `uv run --offline --with 'jsonschema==4.26.0' python -m
  tests.v2.contract.schema_helpers --verify-evidence` — PASS; every record
  carries the five mandatory fields.
- Independent scene-to-record comparison — PASS: 49 request, 66 decision, and
  92 downstream case IDs; 207/207 total, zero missing and zero spurious.
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures
  discovered.
- Candidate and candidate-to-record diffs plus `git diff --check` — PASS.

The trailing record commit
`6296316fd415e85762860569289016a675ab5d2d` changes only the amendment record's
`Revised candidate commit` value from its pre-commit placeholder to the exact
full candidate SHA. It changes no schema, validator, test, corpus, generated
evidence, or product documentation.

## Acceptance

Amendment A1 candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`
with record commit `6296316fd415e85762860569289016a675ab5d2d` is
accepted by `v2-integrator` as I-010E AttentionReceiptV2 `@2`.

This versioned amendment supplements rather than revokes slice 010's terminal
attempt-6 acceptance. It does not itself establish a dependent consumer's
acceptance, slice readiness, atomic cutover, current V2 behavior, release, or
promotion. Slice 030 and every other declared consumer must separately accept
and bind the exact amended interface before relying on it.
