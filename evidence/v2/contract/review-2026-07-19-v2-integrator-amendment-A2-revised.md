# v2-integrator re-review — slice 010 amendment A2 revised candidate

**Slice**: `010-v2-contract`

**Original A2 candidate commit**:
`994df5606fac24b3dd1ba1201e4f0765e4e091a5`

**First revised A2 candidate commit**:
`22c249a1a2a3c8c142dfc4849fef689dc271b27b`

**A2-R1 correction candidate commit**:
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`

**Prior rejection decision**:
`0730fac388dc4f7286ba144fb633aea147f6df04`

**Amendment record**:
`evidence/v2/contract/amendment-A2-decision-margin-boundary.md`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-19

**Decision**: ACCEPTED

## Decision basis

The complete revised A2 candidate matches the Zoe-selected technical design at
`c834e8c` without broadening or narrowing it. The selected design says an
active transition margin is finite within `[0,1]`. I-010B `@2` now encodes that
inclusive domain identically in the Draft 2020-12 schema and stdlib mirror,
while preserving every other routing-audit field and cross-field constraint.

Independent probes agreed under both validators:

- `0`, `-0.0`, and `1` — valid / valid;
- `-0.000001`, `1.000001`, decoded `NaN`, and boolean `false` — invalid /
  invalid;
- a `margin-defer` audit missing `effective_margin` — invalid / invalid; and
- `effective_margin: 0` on a non-margin valve — invalid / invalid.

The correction changes no upper bound, disposition pair, valve, override
cause, margin-status rule, conditional `margin_source`, legacy-confidence
shape, advice rule, bypass shape, or error branch.

## A2-R1 closure and freshness sweep

The rejection at
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A2.md`
identified one remaining live contradiction: `_check_routing_audit` executed
the inclusive `[0,1]` check but its function docstring still stated `(0, 1]`.

Candidate `26a6b53` changes that current docstring to `[0, 1]` and explicitly
labels `(0, 1]` as the wrongly narrowed accepted-`@1` history. A repository
sweep confirms:

- the public schema identifies I-010B `AttentionDecisionV2@2` and the inclusive
  `[0,1]` A2 boundary;
- the stdlib executable check, validation error, and function docstring agree;
- the decision test module identifies `@2`;
- current spec, plan, contract guide, corpus, evidence manifest, and amendment
  record agree on `@2` and `[0,1]`; and
- remaining `(0, 1]` or I-010B `@1` mentions are explicit amendment history,
  immutable candidate/handoff/adjudication records, or completed historical
  task text. In particular, `checklist-adjudication.md` CHK084 truthfully
  preserves the FR-005 text adjudicated at that earlier commit and must not be
  rewritten.

A2-R1 is therefore closed without modifying immutable history or introducing a
functional change.

## A1 and R7–R11 regression audit

Amendment A1 remains intact. A2 changes no attention-receipt schema,
receipt-body mirror, receipt corpus, or A1 acceptance evidence. I-010E `@2`'s
required classifier policy provenance and paired `NO_WAKE` override remain
accepted and unchanged.

All five attempt-6 findings remain closed:

- **R7**: decision and receipt errors still require both `code` and `detail`;
  `code` remains an open non-empty string.
- **R8**: exact self/actor-map and typed actor-reference integrity are
  unchanged.
- **R9**: request and participant-wake retain the complete shared `Self` and
  `Room` shapes.
- **R10**: continuation shape, binding, direction, budgets, optional expiry,
  and safe timestamp comparison are unchanged.
- **R11**: malformed request/capability identities and directions plus
  duplicate issued handle identities remain total and deterministically
  rejected.

The retained focused R7–R11 selection passed 59 tests under both validator
environments.

## Verification performed

The complete recorded stack was reproduced against exact correction candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`:

- `python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'` — PASS,
  195 tests, 3 skipped (`baseline-oracle-absence`).
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover
  -s tests/v2/contract -p 'test_*.py'` — PASS, 195 tests, 0 skipped.
- `python3 -m unittest` — PASS, 1253 tests, 11 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- `uv run --offline --with 'jsonschema==4.26.0' python -m
  tests.v2.contract.schema_helpers --write-evidence` — PASS: 98 request, 134
  decision, and 184 downstream records, 0 mismatched; regeneration produced no
  tracked evidence diff.
- `uv run --offline --with 'jsonschema==4.26.0' python -m
  tests.v2.contract.schema_helpers --verify-evidence` — PASS; every record
  carries all five mandatory fields.
- Independent scene-to-record comparison — PASS: 49 request, 67 decision, and
  92 downstream case IDs; 208/208 total, zero missing and zero spurious.
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures.
- Direct authority extraction at `c834e8c`, independent boundary/cross-field
  probes, correction diff, full live-reference sweep, and `git diff --check` —
  PASS.

## Separate program-registry finding

The amendment record correctly leaves the umbrella program interface registry
to `v2-program-owner`. That registry must eventually cite accepted I-010B `@2`
and I-010E `@2`, but the separate program correction neither weakens nor
replaces this contract-amendment acceptance.

## Acceptance

Amendment A2 correction candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301` is accepted by `v2-integrator` as
I-010B AttentionDecisionV2 `@2`.

This versioned amendment supplements rather than revokes slice 010's terminal
attempt-6 acceptance and amendment A1. It does not itself establish a
dependent consumer's acceptance, slice readiness, atomic cutover, current V2
behavior, release, or promotion. Slice 030 and every other declared consumer
must separately accept and bind the exact amended interface before relying on
it.
