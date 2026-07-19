# v2-integrator review — slice 010 amendment A2 revised candidate

**Slice**: `010-v2-contract`

**Original A2 candidate commit**:
`994df5606fac24b3dd1ba1201e4f0765e4e091a5`

**Revised A2 candidate commit**:
`22c249a1a2a3c8c142dfc4849fef689dc271b27b`

**Pre-amendment accepted decision**:
`30aba09f13a6752b4c24811da0d8ec772a9d9682`

**Amendment record**:
`evidence/v2/contract/amendment-A2-decision-margin-boundary.md`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-19

**Decision**: REJECTED

## Decision basis

Direct comparison with the Zoe-selected technical design at `c834e8c`
confirms that A2's substantive correction is exact. The design says an active
transition margin is finite within `[0,1]`; accepted I-010B `@1` alone narrowed
the lower boundary through `exclusiveMinimum: 0` and the matching stdlib
condition `0.0 < margin <= 1.0`. Candidate `994df56` changes those two checks
to the inclusive lower bound without changing the upper bound, another field,
a routing valve, an override cause, margin status, or the conditional
`margin_source` rule.

Independent Draft 2020-12 and stdlib probes agreed:

- `0`, `-0.0`, and `1` — valid / valid;
- `-0.000001`, `1.000001`, decoded `NaN`, and boolean `false` — invalid /
  invalid;
- a `margin-defer` audit missing `effective_margin` — invalid / invalid; and
- `effective_margin: 0` on a non-margin valve — invalid / invalid.

The added `DEC-AUTH-006` case and regenerated evidence therefore express the
selected boundary without broadening the numeric or cross-field contract.
Revised candidate `22c249a` correctly updates the public schema description to
I-010B `@2`, corrects the unchanged `legacy_verdict_confidences` comment, and
updates the decision test module docstring. One current contradiction remains.

### A2-R1 — stdlib mirror docstring retains the rejected `(0, 1]` domain

`_check_routing_audit` in `tests/v2/contract/schema_helpers.py` is the current
stdlib validation mirror for the public decision schema. Its executable check
now correctly accepts `0.0 <= margin <= 1.0`, and its emitted validation error
correctly names `[0, 1]`. Its own docstring still says:

> effective margin (finite, in (0, 1]) is then required

That is the exact lower-bound rule A2 exists to replace. It is not immutable
attempt evidence or completed historical task wording; it describes the live
validator changed by A2. The revised candidate's freshness sweep therefore
remains incomplete, and the same current adapter simultaneously implements and
documents different contract domains.

The focused correction is one line: change that docstring domain to
`[0, 1]`, rerun the recorded stack, and append a new exact A2 candidate for
separate review. Historical attempt/handoff evidence, completed task text, the
A1 record, and the program-owned registry should remain untouched.

## A1 and R7–R11 regression audit

Amendment A1 remains intact. A2 changes no attention-receipt schema,
receipt-body mirror, receipt corpus, or A1 decision evidence. I-010E `@2`'s
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

The recorded stack was reproduced against exact revised candidate `22c249a`:

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
  probes, candidate and freshness-correction diffs, and `git diff --check` —
  PASS.

Passing behavior does not make the contradictory live validator description
fresh for the exact versioned amendment candidate.

## Separate program-registry finding

The amendment record correctly flags the umbrella program interface registry
as a separate `v2-program-owner` responsibility and does not edit outside the
slice-010 lane. That ownership handling is correct and is not a reason for
this rejection.

## Lifecycle effect and rework path

This decision rejects only revised amendment A2 candidate
`22c249a1a2a3c8c142dfc4849fef689dc271b27b`. Slice 010's terminal attempt-6
acceptance remains intact, amendment A1 remains accepted as I-010E `@2`, and
accepted I-010B remains `@1`. This focused amendment rejection does not return
the accepted slice to `ACTIVE` or rewrite immutable prior decisions.

The `v2-contract-owner` should append the one-line correction as a new exact
A2 candidate and request separate `v2-integrator` re-review. Until acceptance,
consumers must not bind I-010B `@2` or treat slice 030's zero-margin blocker as
resolved.
