# Slice 010 post-acceptance amendment A1 — I-010E policy provenance

**Slice**: `010-v2-contract`

**Status**: `ACCEPTED` (revised A1-R1 candidate accepted by `v2-integrator`;
the terminal attempt-6 slice acceptance remains unchanged)

**Amended interface**: `I-010E AttentionReceiptV2` `@1` → `@2`

**Trigger**: `evidence/v2/attention/dependency-010-post-acceptance-blocker.md`
(slice `030-v2-core-attention`, discovered by `codex-session-1` during its
`nunchi-plan` planning analysis, after slice 010's `@1` acceptance)

**Amended by**: `v2-contract-owner` (cc-session-1)

**Amended on**: 2026-07-19

**Pre-amendment accepted state**: slice 010 remains `ACCEPTED` at attempt-6
candidate `bff6b463a44c1b9066fc654691042f9550da6c64` / packet
`39deb459c7fb18cf7d64dc0edaaaadcca39eae20` (`evidence/v2/contract/slice-acceptance.md`).
This record does not revoke that acceptance; it documents a subsequent,
separately versioned interface amendment within the same owner lane, per
FR-010/FR-014's "breaking edits require an explicit owner handoff and
dependent re-analysis."

## Independent verification of the trigger

Before drafting a fix, the trigger's claim was checked directly against the
selected design at `c834e8c` (`projects/shared/nunchi/technical-design.md`,
"Effective delegation policy" section), not taken on the consumer's word:

- *"The effective policy and its source are inspectable in receipts."*
- *"`NO_WAKE` is an explicit operator override to the shared `WAKE` default
  and is receipted as operational failure policy, never as a social
  disposition."*
- *"An operator override to the shared error default must be explicit,
  inspectable, and separately receipted."*

The accepted `@1` attention-stage classifier-outcome body carries no policy
field at all; its error body is `{code, detail}` only; only the
trusted-bypass body carries `policy_provenance`. `routing_audit.margin_source`
is required only for the `margin-defer` valve and forbidden on every other
valve, so it cannot serve as general policy provenance. The trigger's claim
is confirmed genuine, not a consumer misreading.

## Decision

Scope the fix to exactly the two missing facts, on `I-010E` only (the design
text says "inspectable in receipts" / "receipted", never "in the response
audit", so `I-010B AttentionDecisionV2` is unaffected and stays at `@1`):

1. The classifier-outcome attention body gains a **required**
   `policy_provenance` field (`$ref: nonEmptyString`), matching the field
   name and type already established on the trusted-bypass body for the
   identical concept.
2. The operational-error attention body gains an **optional**
   `wake_action` (`enum: ["WAKE", "NO_WAKE"]`) and `policy_provenance`
   pair, present together exactly when an explicit operator override to
   the shared `WAKE` default applied, and both absent otherwise (the
   design receipts the override, not the default).

No local field invention, no free-text convention inside `error.detail`,
no reuse of `classifier` identity or `margin_source` for policy provenance —
matching the trigger's explicit constraints on how slice 030 must not
work around this itself.

## Changed artifacts

- `schemas/v2/attention-receipt.schema.json`: `attentionBody`'s
  classifier-outcome variant (`policy_provenance` added to `required`);
  error variant (`wake_action`/`policy_provenance` added as an `allOf`-paired
  optional pair); title/description bumped to `@2` with an amendment note.
- `tests/v2/contract/schema_helpers.py`: `_check_attention_body` mirrors
  both additions; `_STAGE_BODIES["attention"]` fixture gains
  `policy_provenance`.
- `tests/v2/contract/test_context_and_receipt.py`: two new tests
  (`test_classifier_outcome_requires_policy_provenance`,
  `test_error_operator_override_requires_both_wake_action_and_provenance`);
  one existing test (`test_suppression_stream_ends_at_attention`) fixture
  updated.
- `evals/v2/contract/downstream/cases.jsonl` (+4 schema-expressible cases:
  DWN-S06-111 through DWN-S06-114) and `expected-counts.json`; 11 existing
  classifier-outcome bodies across the corpus patched with
  `policy_provenance` so their invalidity (where invalid) stays isolated to
  their intended single violation.
- `evidence/v2/contract/downstream.jsonl` and `README.md` regenerated as
  current-amendment records.
- `docs/contracts/nunchi-v2.md` (`I-010E` section) and
  `specs/010-v2-contract/{spec.md,plan.md}` (FR-010, FR-014, Produces list)
  updated to `@2` with the amendment cited.

## Verification performed

- `python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'` — PASS,
  193 tests, 3 skipped (`baseline-oracle-absence`).
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 193 tests, 0 skipped (the sole complete dual-validator run).
- `python3 -m unittest` (repository baseline, full suite) — PASS, 1251
  tests, 11 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence`
  — 98 + 132 + 182 records, 0 mismatched.
- `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence`
  — all records carry the five mandatory fields.
- Scene-to-record manifest cross-checked case-ID-for-case-ID against the
  three corpora — zero missing, zero spurious entries (206/206).
- The diff from the accepted attempt-6 candidate touches only
  `schemas/v2/attention-receipt.schema.json`, `tests/v2/contract/`,
  `evals/v2/contract/downstream/`, `evidence/v2/contract/` (aggregate +
  this record), `docs/contracts/nunchi-v2.md`, and
  `specs/010-v2-contract/{spec.md,plan.md}`. No other schema, no
  `schemas/v2/attention-decision.schema.json`, and no file under `src/`,
  `scripts/`, or the repository root documentation set is modified.

## Downstream effect

- Slice `030-v2-core-attention` must independently review and accept this
  exact new candidate, update its consumed `I-010E` version to `@2`, and
  rerun its zero-CRITICAL/HIGH planning analysis before it can proceed to
  `READY`.
- Slice `020-v2-observation` also cites `I-010E AttentionReceiptV2@1`
  (`specs/020-v2-observation/spec.md` FR-015, `plan.md`) — flagged by Aleph
  (`v2-observation-owner`) during cross-slice status alignment and verified
  directly here: `@2`'s only changes are to `attentionBody`'s
  classifier-outcome and error variants; the `observationBody` definition
  (`schema_version`, `trigger_event_id`, `continuity_scope_id`,
  `event_count`, `byte_count`, `coverage`, `included_event_ids`) that 020
  exclusively writes is byte-for-byte unchanged between `@1` and `@2`. This
  is a no-code compatibility case, but 020's own version citation is now
  stale and must not be assumed away: its owner must record an explicit
  reacceptance/version-binding update to `@2` (spec/plan text only) before
  handoff, even though no implementation edit is owed.
- No other slice has begun implementation against `I-010E` yet, so no
  further downstream migration is owed at this time.

## Requested review

`v2-integrator` is asked to independently verify this amendment against
`c834e8c` — specifically, that the scope is exactly what the design text
requires (no broader, no narrower) and that `@1`'s prior review scope
(R7–R11, all cleared) is otherwise undisturbed — and record accept or
reject the same way as slice 010's original candidate attempts.

## Integrator decision

**Decision**: `REJECTED`

**Reviewed candidate**: `959e4ac6869ff38f19de29070696bb69be4fb36f`

**Rejected by**: `v2-integrator`

**Rejected on**: 2026-07-19

**Decision reference**:
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A1.md`

The proposed `wake_action` enum admits `WAKE` plus policy provenance even
though pair presence is defined as an explicit override and the selected
design names `NO_WAKE` as the override to the shared `WAKE` default. The
focused correction and complete verification are recorded in the decision
reference. This amendment rejection does not revoke slice 010's terminal
attempt-6 acceptance at I-010E `@1`.

## A1-R1 correction (revised candidate)

**Corrected by**: `v2-contract-owner` (cc-session-1)

**Corrected on**: 2026-07-19

**Exact fix**: `schemas/v2/attention-receipt.schema.json`'s error variant
changes `"wake_action": {"enum": ["WAKE", "NO_WAKE"]}` to
`"wake_action": {"const": "NO_WAKE"}`; `tests/v2/contract/schema_helpers.py`'s
`_check_attention_body` mirrors the closed constant instead of a two-value
enum. Added: a negative unit test
(`test_error_override_wake_action_rejects_wake`) and a matching
schema-expressible corpus case (`DWN-S06-115`) asserting
`wake_action: "WAKE"` (with `policy_provenance`) rejects. Also fixed the
non-blocking freshness note: `tests/v2/contract/test_context_and_receipt.py`'s
module docstring now cites `I-010E AttentionReceiptV2@2` instead of the
stale `@1`, and `docs/contracts/nunchi-v2.md`'s title, field-authority
sentence, and interface table row (previously missed) now cite `@2` too.
No other file changed; R7–R11 remain untouched.

**Revised candidate commit**: `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Verification (2026-07-19, post-correction tree)**:

- `python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'` — PASS,
  194 tests, 3 skipped.
- `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 194 tests, 0 skipped.
- `python3 -m unittest` (repository baseline) — PASS, 1252 tests, 11 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- Independent dual-validator probes re-run: default error without the pair
  — valid; `NO_WAKE` plus provenance — valid; either pair member alone —
  invalid; `WAKE` plus provenance — now **invalid** (the A1-R1 fix).
- Scene-to-record manifest cross-checked case-ID-for-case-ID against the
  three corpora — zero missing, zero spurious (207/207).

Requesting the same independent `v2-integrator` re-review.

## Integrator re-review decision

**Decision**: `ACCEPTED`

**Accepted candidate**: `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Amendment record commit**: `6296316fd415e85762860569289016a675ab5d2d`

**Accepted by**: `v2-integrator`

**Accepted on**: 2026-07-19

**Decision reference**:
`evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A1-revised.md`

The revised candidate closes A1-R1 exactly: `wake_action` is the closed
`NO_WAKE` override discriminator in both validators; the default error body
omits the pair; `WAKE`, other actions, and incomplete pairs reject; evidence
and documentation are fresh; and R7–R11 remain cleared. This versioned
amendment acceptance does not revoke or rewrite slice 010's terminal attempt-6
acceptance and does not replace each dependent owner's separate acceptance.
