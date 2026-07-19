# Slice 010 post-acceptance amendment A2 — I-010B margin boundary

**Slice**: `010-v2-contract`

**Status**: `REJECTED` (independent `v2-integrator` review of revised candidate
`22c249a`; A2-R1 leaves one current stdlib-mirror contract description on the
rejected `(0, 1]` domain; accepted I-010B `@1` remains unchanged)

**Amended interface**: `I-010B AttentionDecisionV2` `@1` → `@2`

**Trigger**: discovered by `codex-session-1` during slice `030-v2-core-attention`'s
re-planning analysis, after slice 010's amendment A1 (`I-010E@2`) acceptance;
filed as `evidence/v2/attention/dependency-010-amendment-A1-post-acceptance-zero-margin-blocker.md`
in the slice-030 worktree.

**Amended by**: `v2-contract-owner` (cc-session-1)

**Amended on**: 2026-07-19

**Pre-amendment accepted state**: slice 010 remains `ACCEPTED` at attempt-6
candidate `bff6b463a44c1b9066fc654691042f9550da6c64`; amendment A1
(`I-010E@2`) is separately `ACCEPTED` at decision commit
`30aba09f13a6752b4c24811da0d8ec772a9d9682`. This record does not revoke
either; it documents a second, independent post-acceptance amendment within
the same owner lane.

## Independent verification of the trigger

Checked directly against the selected design at `c834e8c`
(`projects/shared/nunchi/technical-design.md`, "Effective delegation
policy" section), not taken on the consumer's word:

> *"All limits are positive integers. A transition margin, when active, is
> a finite number within `[0,1]`; its effective value and configuration
> source are included in the response audit and receipt."*

The domain is explicitly inclusive of both boundaries. The accepted `@1`
`routing_audit.effective_margin` used `exclusiveMinimum: 0` (schema) and a
matching `(0.0 < margin <= 1.0)` check (stdlib adapter) — both wrongly
excluding exactly `0`. Reproduced directly:

```sh
python3 -c 'from tests.v2.contract.schema_helpers import make_decision_ok, validate_attention_decision; d=make_decision_ok("SUPPRESS", "DEFER", "margin-defer"); d["routing_audit"]["effective_margin"]=0; print("\n".join(validate_attention_decision(d)))'
```

prints `routing_audit.effective_margin: must be a finite number within (0, 1]`
against the accepted `@1` tree — a genuine authority-vs-accepted-schema
divergence, not a consumer misreading. The domain used by the sibling
`confidence` `$def` in the same schema file (`$defs/confidence`, used for
`legacy_verdict_confidences`) is already correctly `minimum: 0` (inclusive);
`effective_margin` was the sole outlier.

## Decision

Scope the fix to exactly the boundary: change `effective_margin`'s
`exclusiveMinimum: 0` to `minimum: 0` in the schema, and the stdlib
adapter's matching comparison from `(0.0 < margin <= 1.0)` to
`(0.0 <= margin <= 1.0)`, with the error message corrected from `(0, 1]` to
`[0, 1]`. No other field, valve, or cross-field rule changes — the
margin-defer-only applicability, the `override_cause`/`margin_status`
pairing, and the conditional `margin_source` rule are all unaffected and
unchanged.

## Changed artifacts

- `schemas/v2/attention-decision.schema.json`: `routingAudit.effective_margin`
  bound changed `exclusiveMinimum: 0` → `minimum: 0`; `$comment` updated
  with the amendment citation.
- `tests/v2/contract/schema_helpers.py`: `_check_routing_audit`'s
  `effective_margin` range check and error message updated to match.
- `tests/v2/contract/test_attention_decision.py`: removed `0` from
  `test_out_of_range_effective_margin_rejects`'s negative cases; added
  `test_zero_effective_margin_validates`.
- `evals/v2/contract/attention-decision/cases.jsonl` (+1 schema-expressible
  case: `DEC-AUTH-006`, a margin-defer decision with `effective_margin: 0`)
  and `expected-counts.json`.
- `evidence/v2/contract/attention-decision.jsonl` and `README.md`
  regenerated as current-amendment records.
- `docs/contracts/nunchi-v2.md` (title, field-authority sentence, interface
  table, `I-010B` section) and `specs/010-v2-contract/{spec.md,plan.md}`
  (FR-005, FR-014, Produces list) updated to `@2` with the amendment cited.

## Verification performed

- `python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'` — PASS,
  195 tests, 3 skipped (`baseline-oracle-absence`).
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 195 tests, 0 skipped (the sole complete dual-validator run).
- `python3 -m unittest` (repository baseline, full suite) — PASS, 1253
  tests, 11 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence`
  — 98 + 134 + 184 records, 0 mismatched.
- `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence`
  — all records carry the five mandatory fields.
- The diff from the accepted attempt-6 candidate (plus amendment A1) touches
  only `schemas/v2/attention-decision.schema.json`, `tests/v2/contract/`,
  `evals/v2/contract/attention-decision/`, `evidence/v2/contract/`
  (aggregate + this record), `docs/contracts/nunchi-v2.md`, and
  `specs/010-v2-contract/{spec.md,plan.md}`. No other schema is modified.

## Downstream effect

- Slice `030-v2-core-attention` filed this trigger and must independently
  review and accept this exact new candidate, update its consumed `I-010B`
  version to `@2`, and rerun its zero-CRITICAL/HIGH planning analysis.
- No other slice has begun implementation against `I-010B` yet, so no
  further downstream migration is owed at this time.
- The umbrella program registry at `specs/001-nunchi-v2-program/plan.md`
  still cites `I-010E AttentionReceiptV2@1` as of amendment A1's acceptance
  commit `30aba09` (flagged separately by slice 030 as
  `evidence/v2/attention/program-interface-registry-I-010E-version-blocker.md`);
  it will need the same correction for both `I-010B@2` and `I-010E@2` once
  this amendment lands. That file is owned by `v2-program-owner`, not this
  slice; the correction is factual (citing the already-accepted version),
  not a design decision.

## Requested review

`v2-integrator` is asked to independently verify this amendment against
`c834e8c` — specifically, that the inclusive `[0,1]` domain is correct and
that neither this amendment nor amendment A1 disturbs the other's scope or
any of the R7–R11 findings already cleared — and record accept or reject
the same way as slice 010's prior candidate attempts.

## Freshness correction (pre-review)

**Flagged by**: Aleph (`v2-observation-owner`), cross-checking the pushed
candidate directly during program status alignment (Discord).

**Finding**: the schema file's own top-level `description` field (and one
`$comment`) still self-identified as `AttentionDecisionV2@1`, even though
the functional fix (the `effective_margin` bound) and every other file
(amendment record, contract docs, slice spec/plan) already say `@2`. The
canonical schema is contract truth, not wording — this is the same class
of miss as A1's own freshness note (the test module docstring caught only
after the first review pass).

**Correction**: `schemas/v2/attention-decision.schema.json`'s description
and the `legacy_verdict_confidences` `$comment` now correctly cite `@2`;
`tests/v2/contract/test_attention_decision.py`'s module docstring likewise.
A full sweep of every schema, adapter, test, and doc file for a stale
`@1` self-reference to either `I-010B` or `I-010E` found no further
misses. No functional change; full baseline and dual-validator suite
re-verified green (1253 / 195 tests).

## Integrator decision

**Decision**: `REJECTED`

**Reviewed candidate**: `22c249a1a2a3c8c142dfc4849fef689dc271b27b`

**Original A2 candidate**: `994df5606fac24b3dd1ba1201e4f0765e4e091a5`

**Rejected by**: `v2-integrator`

**Rejected on**: 2026-07-19

**Decision reference**:
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A2.md`

The executable boundary correction is authority-conformant and otherwise
scope-contained. The pre-review freshness commit fixes the schema's `@2`
self-description and the decision-test module, but the live stdlib mirror's
`_check_routing_audit` docstring still states that an applied effective margin
is finite in `(0, 1]`. That directly contradicts its corrected executable
`[0,1]` check and the selected design. The exact focused correction and full
independent verification are recorded in the decision reference. This
rejection does not revoke amendment A1's accepted I-010E `@2`, alter slice
010's terminal attempt-6 acceptance, or transfer the separate umbrella-
registry correction out of the `v2-program-owner` lane.

## A2-R1 correction (second revised candidate)

**Corrected by**: `v2-contract-owner` (cc-session-1)

**Corrected on**: 2026-07-19

**Exact fix**: `tests/v2/contract/schema_helpers.py`'s `_check_routing_audit`
function docstring said "effective margin (finite, in (0, 1]) is then
required" — the exact live executable rule A2 replaces, missed by the
first freshness sweep because it is a function docstring rather than the
module docstring or schema description already checked. Changed to
`[0, 1]`, citing the amendment. Full repository search confirmed no other
live schema, adapter, test, or doc file still names the rejected domain;
`evidence/v2/contract/checklist-adjudication.md`'s CHK084 entry correctly
retains its historical `(0, 1]` wording (an immutable record of what
FR-005 said at that past adjudication, not current live code) and is
intentionally left untouched.

**Verification (2026-07-19, post-correction tree)**: no functional change
— `python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'` PASS
(195 tests, 3 skipped); `uv run --offline --with 'jsonschema==4.26.0'
python -m unittest discover -s tests/v2/contract -p 'test_*.py'` PASS (195
tests, 0 skipped).

Requesting the same independent `v2-integrator` re-review.
