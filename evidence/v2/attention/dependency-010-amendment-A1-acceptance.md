# Slice 030 dependency acceptance — 010 amendment A1 / I-010E @2

**Consumer slice**: `030-v2-core-attention`

**Upstream slice**: `010-v2-contract`

**Accepted dependencies**: `010-v2-contract`

**Dependency commits**:
`010-v2-contract=817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Dependency acceptance references**:
`010-v2-contract=evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`

**Amendment candidate commit**: `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Amendment record commit**: `6296316fd415e85762860569289016a675ab5d2d`

**Upstream integrator decision commit**:
`30aba09f13a6752b4c24811da0d8ec772a9d9682`

**Upstream decision reference**:
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A1-revised.md`

**Upstream amendment record**:
`evidence/v2/contract/amendment-A1-receipt-policy-provenance.md`

**Prior consumer acceptance**:
`evidence/v2/attention/dependency-010-acceptance.md`

**Resolved blocker record**:
`evidence/v2/attention/dependency-010-post-acceptance-blocker.md`

**Accepted by**: codex-session-1

**Accepted on**: 2026-07-19

**Consumer branch / worktree**: `v2/core-attention` /
`.worktrees/v2-core-attention`

**Integrated by merge commit**:
`34ad565e149b749c078ab60a076cc79141551ec6`

## Decision

`codex-session-1`, occupying the assigned `v2-core-owner` lane, independently
accepts exact slice-010 amendment candidate
`817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`, with exact candidate-record commit
`6296316fd415e85762860569289016a675ab5d2d` and upstream integrator acceptance
at `30aba09f13a6752b4c24811da0d8ec772a9d9682`, for consumption by slice 030.

This acceptance updates only slice 030's I-010E binding from
`AttentionReceiptV2@1` to `AttentionReceiptV2@2`. The existing attempt-6
consumer acceptance remains immutable and continues to bind I-010A
`AttentionRequestV2@1` and I-010B `AttentionDecisionV2@1`; it is not overwritten
or treated as if it had contained the later amendment.

The accepted I-010E `@2` surface adds exactly:

- required non-empty `policy_provenance` on classifier-outcome attention
  receipts, matching the trusted-bypass provenance concept; and
- an optional error-body pair whose only valid action is
  `wake_action: "NO_WAKE"` with required non-empty `policy_provenance`, present
  exactly for the explicit operator override to the shared `WAKE` default and
  absent on the default path.

The schema and stdlib mirror reject `WAKE`, any other action, and either pair
member alone. The amendment therefore represents the selected design's
effective-policy provenance and separately receipted operational-error override
without adding local receipt fields, encoding provenance in `error.detail`,
misusing classifier identity or `routing_audit.margin_source`, changing I-010B,
or fabricating a social disposition.

## Blocker disposition

This record resolves for slice 030 the HIGH finding recorded in
`dependency-010-post-acceptance-blocker.md`. That earlier record remains
immutable historical evidence of the state discovered against I-010E `@1`;
its `OPEN` status described that candidate and is superseded for current
readiness derivation only by this exact accepted `@2` dependency record. The
original dependency acceptance and blocker files are not rewritten.

## Independent verification

Run after merging exact upstream decision commit
`30aba09f13a6752b4c24811da0d8ec772a9d9682` into the isolated consumer
worktree:

- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`;
- `python3 -m unittest` — PASS, 1252 tests, 11 skipped;
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover
  -s tests/v2/contract -p 'test_*.py'` — PASS, 194 tests, 0 skipped;
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures
  discovered; and
- candidate, record, and decision diffs — PASS: the A1-R1 candidate closes
  `wake_action` to `NO_WAKE`, record commit `6296316` changes only the candidate
  placeholder to its full SHA, and decision commit `30aba09` changes only the
  amendment status and integrator review evidence.

Direct comparison with the selected design at `c834e8c` and independent
dual-validator probes also passed: default error without the pair and paired
`NO_WAKE` validate; `WAKE`, an unknown action, and incomplete pairs reject.
R7–R11 remain cleared because the correction changes no request, decision,
continuation, or participant-wake schema and does not disturb their retained
runtime validation.

This consumer acceptance establishes no slice-030 social-quality evidence,
implementation completion, atomic cutover, current V2 behavior, release, or
promotion. Those remain owned by the later slice lifecycle and program tail.
