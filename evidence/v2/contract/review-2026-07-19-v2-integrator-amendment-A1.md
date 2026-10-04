# v2-integrator review — slice 010 amendment A1

**Slice**: `010-v2-contract`

**Amendment candidate commit**: `959e4ac6869ff38f19de29070696bb69be4fb36f`

**Amendment record**: `evidence/v2/contract/amendment-A1-receipt-policy-provenance.md`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-19

**Decision**: REJECTED

## Decision basis

Direct comparison with the Zoe-selected design at `c834e8c` confirms that A1
identifies the right contract gap and chooses the right interface boundary:

- classifier-outcome attention receipts need the effective policy's trusted
  provenance, using the same required non-empty `policy_provenance` field as
  the already accepted trusted-bypass body;
- an explicit operator `NO_WAKE` override to the shared operational-error
  `WAKE` default must be represented with its policy provenance on the separate
  error receipt, never as a social disposition; and
- general policy provenance belongs in I-010E receipts. I-010B's response audit
  remains scoped to routing/transition facts, including the conditional
  transition-margin source, so leaving I-010B at `@1` is correct.

The candidate cannot be accepted because its error-body schema is broader than
that selected design and broader than its own amendment record.

### A1-R1 — `wake_action: "WAKE"` is accepted as an override receipt (HIGH)

The selected design states that the shared operational-error default is
`WAKE`, that `NO_WAKE` is the explicit operator override to that default, and
that an override must be explicit, inspectable, and separately receipted. The
amendment record and schema comments therefore say the optional
`wake_action`/`policy_provenance` pair is present exactly when an explicit
override applied and absent for the default.

The candidate instead defines `wake_action` as `enum: ["WAKE", "NO_WAKE"]`.
Both the Draft 2020-12 schema and stdlib mirror consequently accept this body:

```json
{
  "error": {"code": "provider-failure", "detail": "timeout"},
  "wake_action": "WAKE",
  "policy_provenance": "trusted:profiles/default@2026-07"
}
```

That record asserts the presence of an operator override while naming the
unchanged shared default. It is not a selected operational state. The corpus
proves the intended `NO_WAKE` positive case and pair completeness, but has no
negative case for this extra `WAKE` member.

This is a closed public contract rather than a prose-only implementation rule,
so permitting the extra state is acceptance-blocking. The exact correction is
to make the override member `const: "NO_WAKE"` (with the equivalent stdlib
mirror), add a dual-validator negative unit/corpus case for `WAKE`, and
regenerate the affected evidence and counts. The default error body without the
pair and the `NO_WAKE` body with both fields should remain valid.

## R7–R11 regression audit

The amendment does not reopen the five previously cleared findings:

- **R7 — remains cleared**: error `code` stays an open non-empty string and
  `detail` remains required as a string in both decision and receipt contracts.
  The new finding concerns only A1's additional override discriminator.
- **R8 — remains cleared**: exact self/actor-map and typed actor-reference
  integrity code, schemas, and cases are unchanged.
- **R9 — remains cleared**: request and participant-wake still use the shared
  complete `Self`/`Room` validation; those schemas and validators are unchanged.
- **R10 — remains cleared**: issued capability shape, binding, direction, caps,
  optional expiry, and safe timestamp comparison are unchanged.
- **R11 — remains cleared**: malformed identities/directions and duplicate
  issued-handle ambiguity remain total and deterministically rejected.

The exact candidate changes no request, decision, continuation, or participant-
wake schema. In `schema_helpers.py`, its executable edits are confined to the
attention receipt body mirror and the corresponding canonical stage fixture.
The retained focused R7–R11 suite passed 58 tests under both validators.

## Verification performed

All amendment-record commands were reproduced from a detached worktree at the
exact candidate commit:

- `python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'` — PASS,
  193 tests, 3 skipped (`baseline-oracle-absence`).
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover
  -s tests/v2/contract -p 'test_*.py'` — PASS, 193 tests, 0 skipped.
- `python3 -m unittest` — PASS, 1251 tests, 11 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- `uv run --offline --with 'jsonschema==4.26.0' python -m
  tests.v2.contract.schema_helpers --write-evidence` — PASS: 98 request, 132
  decision, and 182 downstream records, 0 mismatched; regeneration produced no
  tracked evidence diff.
- `uv run --offline --with 'jsonschema==4.26.0' python -m
  tests.v2.contract.schema_helpers --verify-evidence` — PASS; every record
  carries the five mandatory fields.
- Independent scene-to-record comparison — PASS: 49 request, 66 decision, and
  91 downstream case IDs; 206/206 total, zero missing and zero spurious.
- Candidate diff and `git diff --check` — PASS.

Independent dual-validator probes returned:

- default error without the pair — valid / valid;
- `NO_WAKE` plus provenance — valid / valid;
- either pair member alone — invalid / invalid; and
- `WAKE` plus provenance — **valid / valid**, the A1-R1 failure above.

Non-blocking freshness note for the focused rework: the changed
`tests/v2/contract/test_context_and_receipt.py` module docstring still names
I-010E `@1` and should be updated to `@2` with the correction.

## Lifecycle effect and rework path

This decision rejects only amendment A1 candidate
`959e4ac6869ff38f19de29070696bb69be4fb36f`. It does not revoke slice 010's
terminal attempt-6 acceptance at I-010E `@1`, mutate that immutable acceptance,
or return the accepted slice to `ACTIVE`.

The `v2-contract-owner` should append a new, exact amendment candidate after
the focused A1-R1 correction and evidence regeneration. A separate
`v2-integrator` review is then required. Until that amendment is accepted,
dependent consumers must not bind to I-010E `@2` or treat the slice-030 blocker
as resolved.
