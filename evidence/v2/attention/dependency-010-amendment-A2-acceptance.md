# Slice 030 dependency acceptance — 010 amendment A2 / I-010B @2

**Consumer slice**: `030-v2-core-attention`

**Upstream slice**: `010-v2-contract`

**Accepted dependencies**: `010-v2-contract`

**Dependency commits**:
`010-v2-contract=26a6b531fa146ba1f1f5fcd1c4d191041b141301`

**Dependency acceptance references**:
`010-v2-contract=evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`

**Amendment candidate commit**: `26a6b531fa146ba1f1f5fcd1c4d191041b141301`

**Upstream integrator decision commit**:
`d504310c61a93afbe57d4fe4ed05e93055c75555`

**Upstream decision reference**:
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A2-revised.md`

**Upstream amendment record**:
`evidence/v2/contract/amendment-A2-decision-margin-boundary.md`

**Prior consumer amendment acceptance**:
`evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`

**Resolved blocker record**:
`evidence/v2/attention/dependency-010-amendment-A1-post-acceptance-zero-margin-blocker.md`

**Accepted by**: codex-session-1

**Accepted on**: 2026-07-19

**Consumer branch / worktree**: `v2/core-attention` /
`.worktrees/v2-core-attention`

**Integrated by merge commit**:
`adaa89014bd23f22100a4a6a8c5f811b411ec425`

## Decision

`codex-session-1`, occupying the assigned `v2-core-owner` lane, independently
accepts exact slice-010 amendment A2 correction candidate
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`, with upstream integrator
acceptance at `d504310c61a93afbe57d4fe4ed05e93055c75555`, for consumption by
slice 030.

This acceptance updates only slice 030's I-010B binding from
`AttentionDecisionV2@1` to `AttentionDecisionV2@2`. The original attempt-6
consumer acceptance and amendment A1 consumer acceptance remain immutable:
they continue to establish I-010A `AttentionRequestV2@1` and I-010E
`AttentionReceiptV2@2` respectively. At readiness, the latest exact dependency
mapping above binds the composite candidate containing all three accepted
interfaces; it does not rewrite either earlier decision.

The accepted I-010B `@2` surface changes exactly one contract boundary:
`routing_audit.effective_margin` is finite in inclusive `[0,1]`, so exact `0`
is valid when the margin-defer valve applies. Its upper bound, required/forbidden
placement, valve, override-cause, margin-status, optional trusted
`margin_source`, legacy-confidence, advice, bypass, and error rules are
unchanged.

## Blocker disposition

This record resolves for slice 030 the CRITICAL finding recorded in
`dependency-010-amendment-A1-post-acceptance-zero-margin-blocker.md`. That
earlier record remains immutable historical evidence of the conflict against
accepted I-010B `@1`; its `OPEN` status described that dependency state and is
superseded for current readiness derivation only by this exact accepted `@2`
consumer decision. No prior acceptance or blocker file is rewritten.

## Independent verification

Run after merging exact upstream decision commit
`d504310c61a93afbe57d4fe4ed05e93055c75555` into the isolated consumer
worktree:

- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`;
- `python3 -m unittest` — PASS, 1253 tests, 11 skipped;
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover
  -s tests/v2/contract -p 'test_*.py'` — PASS, 195 tests, 0 skipped;
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures; and
- candidate, correction, rejection, and final acceptance diffs — PASS: the
  functional candidate changes only the lower boundary and its matching
  evidence/docs, the two freshness corrections change only current
  descriptions, and the decision commit changes only amendment status and
  integrator review evidence.

Direct comparison with `c834e8c` and independent dual-validator probes also
passed: `0`, `-0.0`, and `1` validate; values below `0`, above `1`, decoded
`NaN`, and boolean `false` reject; missing applied margin and a stray margin on
a non-margin valve reject. Amendment A1 and R7–R11 remain undisturbed.

This consumer acceptance establishes no slice-030 implementation, social-
quality evidence, atomic cutover, current V2 behavior, release, or promotion.
Those remain owned by the later slice lifecycle and program tail.
