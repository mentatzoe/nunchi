# Slice 020 handoff evidence — documentation dispositions and packet input

This file records the T028–T034 documentation dispositions and the T038
proposed handoff packet input for the first (and, at this writing, only)
delivery attempt of `020-v2-observation`. Append-only after first use per
the plan's rejection/rework contract.

## Documentation dispositions (T028–T034)

**Reviewer**: the assigned `v2-observation-owner` implementer, in the
implement step of the bound `run speckit` delivery for `020-v2-observation`.

**Reviewed on**: 2026-07-19, at the candidate tree described in "Proposed
handoff packet input" below.

**Candidate diff basis**: starting commit `fc60858a3810e2f53d9574cce1eb9589bd19b55b`
(the frozen activation commit, `evidence/v2/observation/slice-activation.md`)
to the working tree. The ordinary-path diff touches only
`src/nunchi/observation.py`, `tests/v2/observation/`, `evals/v2/observation/`,
`evidence/v2/observation/`, the one new `docs/observation/v2.md`, this
slice's own SpecKit planning artifacts, and one narrow test-infrastructure
fix in `tests/test_governance.py` (see "Known limitations"). No file under
`schemas/v2/`, `src/nunchi/core.py`, `src/nunchi/classifiers.py`, native
transport sources, or `integrations/**` is modified — this slice hands
every downstream delta below to its accepting owner rather than applying it.

**Inventory derivation**: per the plan's Documentation Impact and Freshness
matrix, the reviewed set is exactly `README.md`, `docs/observation/v2.md`,
`docs/contracts/nunchi-v2.md`, `CHANGELOG.md`, `docs/STABILITY.md`,
`docs/integration.md`, `docs/adapters.md`,
`docs/architecture/v2-selected-design.md`,
`integrations/mcp-discord/README.md`, `integrations/mcp-discord/DESIGN.md`,
`integrations/hermes/README.md`, `integrations/claude-code/README.md`, and
`integrations/codex/README.md` — matching the plan matrix and this slice's
declared **Documentation scope** one-to-one; there are no generic
directory rows.

### UPDATE (slice-owned) — T026, T027

| Reviewed path | Disposition | Result |
|---|---|---|
| `docs/observation/v2.md` | `UPDATE` (created) | Authored this delivery. Documents `I-020A` identity binding (FR-002), native-event ingestion and the three mechanical no-wake classes (FR-004), bounded trigger-first snapshot assembly with honest coverage (FR-006/FR-007), optional host-owned continuation (FR-008/FR-009), the singly-attested observation-stage receipt with no token field (FR-015), the evidence-only `utf8-bytes-ceil-div4@1` token-size proxy (FR-013), and the reference-variant/comparator reference-only boundary (FR-011/FR-012). Every one of its 6 Python examples executes successfully under `tests/v2/observation/test_docs.py` (`PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_docs`: 9 tests, OK, validated 2026-07-19). No Mermaid block is present — `N/A` per T034's instruction. All local links (`docs/contracts/nunchi-v2.md`, `evidence/v2/observation/README.md`, `evidence/v2/observation/handoff.md`) resolve and none targets a SpecKit-managed path. |

### NO_IMPACT (re-verified against this candidate's diff) — T034

| Reviewed path | Disposition | Re-verification result |
|---|---|---|
| `docs/contracts/nunchi-v2.md` | `NO_IMPACT` | CONFIRMED — this slice consumes the accepted, closed `I-010A`/`I-010D` shapes exactly as documented (§"I-010A AttentionRequestV2@1", §"I-010D ContextContinuationV2@1") and the immutable observation-stage body of `I-010E` (documented at this upstream file's current heading §"I-010E AttentionReceiptV2@1"; this slice's own consumed version is the accepted amendment `AttentionReceiptV2@2` per T052 below — the amendment changes only the separately owned `attentionBody`, and `dependency-010-amendment-A1-acceptance.md` proves `observationBody` byte-for-byte unchanged, so the upstream heading's literal `@1` text does not misdescribe the observation-stage shape this slice mirrors). This slice edits none of `schemas/v2/`. `src/nunchi/observation.py`'s own stdlib validation adapter mirrors these three schemas field-for-field (validated by 202/202 attempt-6 corpus cases accounted for below, T037) and the accepted `I-010E` observation body's closed field set (`schema_version`, `trigger_event_id`, `continuity_scope_id`, `event_count`, `byte_count`, `coverage`, `included_event_ids`) — with no token field — matches this document's §"I-010E" table exactly; `ObservationProvider.build_observation_receipt` never adds an estimated-token field (`tests/v2/observation/test_contract_inputs.py::TestAttentionReceiptContract::test_observation_body_carries_no_token_field`). |

### HANDOFF (accepting owner named per row; applied only at the owner's own atomic candidate) — T028–T033

Each row routes its exact delta to its accepting owner. This slice does
not present partial V2 as current V1-current-state wording; every delta
below becomes true wording only when its accepting owner applies it at
their own atomic candidate (for `README.md`/`CHANGELOG.md`/
`docs/STABILITY.md`/`docs/integration.md`/`docs/adapters.md`/
`docs/architecture/v2-selected-design.md`, that is `v2-integrator`'s slice
`110` atomic cutover).

| Reviewed path | Disposition | Accepting owner | Exact routed delta |
|---|---|---|---|
| `README.md` | `HANDOFF` | `v2-integrator` | At atomic cutover, add only evidence-proven claims: exact-self binding decisive over alias collisions (FR-002); literal native message/reaction/membership relations with actor-targeted mentions distinct from room-wide mentions (FR-003); trigger-first hard event/byte/optional-age budgets with honest `truncated_by`/`has_more_before`/`has_more_after`/`has_gaps` coverage (FR-006/FR-007); outcome-neutral bounded retention with zero roster/ledger/obligation-queue state (FR-010); and optional host-bound `before`/`after`/`around` continuation with per-fetch caps and exact-event dedup (FR-008/FR-009). Preserve existing V1-current wording verbatim until `CUTOVER_VERIFIED`. |
| `CHANGELOG.md` | `HANDOFF` | `v2-integrator` | Add a breaking-change entry naming `I-020A ObservationProviderV2@1` at `src/nunchi/observation.py`, its consumed `I-010A`/`I-010D` `@1` and `I-010E` `@2` versions (T052: accepted amendment candidate `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`, integrator acceptance `30aba09f13a6752b4c24811da0d8ec772a9d9682`, observation body unchanged), and the accepted-`I-010E`-closed token-field limitation (token-size proxy evidence lives only under `evidence/v2/observation/*.jsonl`, never on the wire receipt). |
| `docs/STABILITY.md` | `HANDOFF` | `v2-integrator` | Add `I-020A`'s stability status (breaking-cutover, not yet current) alongside the existing `I-010A`–`I-010E` rows; state that `continuation` capability redaction for classifier-facing projection is owned entirely by slice `030`, not this interface. |
| `docs/integration.md` | `HANDOFF` | `v2-integrator` | Replace V1 envelope-construction wording with `I-020A` request/identity/relation/order/budget/gap/continuation integration wording: how a native-surface adapter constructs `candidate-event`/`unroutable` native inputs, the three mechanical no-wake dispositions, and how to read `coverage`. |
| `docs/adapters.md` | `HANDOFF` | `v2-integrator` | Add the adapter-facing obligation to supply `authorized`/`reason` transport provenance explicitly (never inferred from payload content) and to run each adapter's own conformance corpus against `I-020A`'s consumed interfaces before claiming parity. |
| `docs/architecture/v2-selected-design.md` | `HANDOFF` | `v2-integrator` | Mark the `I-020A` observation seam as landed at `src/nunchi/observation.py`; align the observation-stage box in the request/decision/wake/receipt diagrams with this document's field names; add the host-only continuation-authority boundary (never in the classifier-visible projection) to the diagram notes. |
| `integrations/mcp-discord/README.md` | `HANDOFF` | `v2-transport-owner` | Add the exact `I-020A` identity/native-fact/order/budget/gap/continuation delta once slice `050` binds this transport's native events to `candidate-event`/`unroutable` inputs and runs its own conformance pass against `I-020A`. |
| `integrations/mcp-discord/DESIGN.md` | `HANDOFF` | `v2-transport-owner` | Same delta as the README row, at the design-record level: document how Discord's native reply/thread/reaction/membership facts map onto this slice's typed event union. |
| `integrations/hermes/README.md` | `HANDOFF` | `v2-hermes-owner` | Add the exact `I-020A` identity/native-fact/order/budget/gap/continuation delta once slice `060` binds Hermes's native channel events to this provider. |
| `integrations/claude-code/README.md` | `HANDOFF` | `v2-claude-owner` | Add the exact `I-020A` identity/native-fact/order/budget/gap/continuation delta once slice `070` binds Claude Code's native turn events to this provider. |
| `integrations/codex/README.md` | `HANDOFF` | `v2-codex-owner` | Add the exact `I-020A` identity/native-fact/order/budget/gap/continuation delta once slice `080` binds Codex's native room events to this provider. |

Additionally, per plan §"Owner Handoff": the `I-010A` expansion-availability
(`continuation`) input is handed to `v2-core-owner` (slice `030`)
unchanged. Slice `030` alone implements classifier-safe projection/
redaction of `continuation` down to coverage plus expansion-capability
booleans in `src/nunchi/core.py` (docs/contracts/nunchi-v2.md §"I-010A",
"The classifier-facing host-secret exclusion... is enforced where the
classifier is actually invoked"); this slice performs no such redaction
itself because it never invokes a classifier.

**Result**: 1 `UPDATE` authored and validated; 1 `NO_IMPACT` rationale
re-verified CONFIRMED; 11 `HANDOFF` deltas routed to their five accepting
owners. No row is unresolved.

## Verification commands and results (T036)

Run 2026-07-19 at the candidate tree (working tree atop starting commit
`fc60858a3810e2f53d9574cce1eb9589bd19b55b`; see "Proposed handoff packet
input" for the exact candidate commit once committed).

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 84 tests, OK, 0 skipped |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 28 rows, 0 FAIL (`identity-and-hygiene.jsonl`: 9; `budget-sweep.jsonl`: 6; `continuation.jsonl`: 6; `s05-recoverability.jsonl`: 4; `s13-equivalence.jsonl`: 3) |
| `PYTHONPATH=src python3 -m unittest` (repository baseline, full suite) | 1333 tests, OK, 11 skipped (the pre-existing baseline skips; unchanged from the 1249-test activation baseline plus this slice's 84 added tests) |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered (unchanged from the activation baseline) |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |

Every discovered test count above is nonzero.

## Attempt-6 corpus conformance (T037)

**Command**: `PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance`

**Result**: 5 tests, OK, 0 failures.

**Corpus revision**: the exact, identical attempt-6 corpus at commit
`bff6b463a44c1b9066fc654691042f9550da6c64` (the accepted `010-v2-contract`
candidate; `evidence/v2/observation/dependency-010-acceptance.md`),
covering `evals/v2/contract/attention-request/` (49 cases),
`evals/v2/contract/attention-decision/` (66 cases), and
`evals/v2/contract/downstream/` (87 cases) — 202 cases total, read-only
via a driver in `tests/v2/observation/contract_helpers.py` independent of
`tests/v2/contract/schema_helpers.py` (010-owned test code), per FR-013's
"own" adapter requirement.

**Consumed vs. non-consumed accounting**: 100 cases exercise slice 020's
own `I-010A`/`I-010D`/`I-010E` stdlib validation adapter
(`src/nunchi/observation.py`); 102 cases are explicitly accounted for as
non-consumed (`I-010B AttentionDecisionV2` and `I-010C ParticipantWakeV2`,
which this slice never implements) rather than silently skipped. Every one
of the 100 consumed cases' observed result (`valid`/`invalid`) matches its
corpus-declared `expected` result — 0 mismatches.

All seven runtime-adapter-only semantic/relational classes are present and
accounted for:

| Class | Consumed | Non-consumed |
|---|---|---|
| `schema-expressible` | 54 | 98 |
| `id-uniqueness` | 4 | 0 |
| `timestamp-order` | 2 | 0 |
| `advice-citation` | 0 | 2 |
| `trigger-membership` | 2 | 0 |
| `actor-reference-integrity` | 7 | 2 |
| `binding-expiry` | 20 | 0 |
| `receipt-sequence` | 11 | 0 |

`advice-citation` is entirely non-consumed: every case in the corpus
exercises `I-010B`'s `attention_advice` or `I-010C`'s `attention.advice`,
neither owned by this slice. `actor-reference-integrity`'s 2 non-consumed
cases are on `participant-wake`-schema documents (`I-010C`); this slice's
own 7 consumed cases are on `attention-request`-schema documents
(`I-010A`). For `attention-receipt`-schema (`I-010E`) records, this slice
validates the envelope and the closed stage-to-writer binding on every
record, and the observation-stage body in full, but never the
`attention`/`participant-host`/`transport` stage bodies — those belong to
their own writers (FR-015); 9 corpus cases whose expected result turns
solely on a non-observation-stage body defect are accordingly non-consumed
rather than mis-scored against a rule this slice does not own.

Two real defects were found and fixed in `check_binding_expiry` while
achieving this result: (1) comparing an issued capability's `bound_to`
fields pointwise against `host_context` missed the case where both sides
independently omitted the same required field; the fix validates the
issued capability's own shape (closed-object, required fields, positive
per-fetch caps) before any binding comparison. (2) a naive/timezone-aware
`fetch_time`/`expires_at` pair was silently normalized to UTC rather than
rejected; the fix detects mixed timezone-awareness and returns a validation
error instead of raising or silently coercing. A third, pre-existing
robustness gap (unhashable `list`/`dict` `handle_id` values crashing the
adapter instead of returning a validation error) was also fixed.

## Proposed handoff packet input (T038)

Prepared by the assigned `v2-observation-owner` implementer, 2026-07-19, in
the implement step of the bound `run speckit` delivery for
`020-v2-observation`.

### Candidate commit

Not yet pinned in this record: this packet input is prepared directly in
the working tree atop starting commit
`fc60858a3810e2f53d9574cce1eb9589bd19b55b` (`evidence/v2/observation/slice-activation.md`).
The exact candidate commit is recorded here once the implementer or Zoe
commits this tree; the full offline baseline above (`PYTHONPATH=src
python3 -m unittest`: 1333 tests, OK, 11 skipped) is the run that commit
must — and does, in the working tree — reproduce.

### Upstream 010 references

- Accepted candidate: `bff6b463a44c1b9066fc654691042f9550da6c64` (I-010A/I-010D/I-010E `@1` attempt 6)
- Packet commit: `39deb459c7fb18cf7d64dc0edaaaadcca39eae20`
- Packet record: `evidence/v2/contract/slice-handoff.md`
- Terminal acceptance: `evidence/v2/contract/slice-acceptance.md`
- This slice's consumer-owned acceptance decision:
  `evidence/v2/observation/dependency-010-acceptance.md`
- T052: accepted `I-010E AttentionReceiptV2@2` amendment (no-code version
  rebind, `observationBody` unchanged) — amendment candidate
  `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`, integrator acceptance
  `30aba09f13a6752b4c24811da0d8ec772a9d9682`, this slice's consumer
  acceptance `evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`

### Completed task manifest

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008,
T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020,
T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032,
T033, T034, T035, T036, T037, T038

**Tasks SHA256**: `c261de490e30e8e6c447dc5b204e463003f21cf38b69ca03c1895e58b00b6d31`
(identical to the frozen **Initial tasks SHA256** in
`evidence/v2/observation/slice-activation.md` — no convergence-appended
task, verified via `python3 scripts/check_governance.py --task-manifest
specs/020-v2-observation`).

### Interface inventory

| Interface | Version | Role | Exact path |
|---|---|---|---|
| `I-020A ObservationProviderV2` | `@1` (this slice's own, unversioned by 010) | Produced | `src/nunchi/observation.py` |
| `I-010A AttentionRequestV2` | `@1` | Consumed | `schemas/v2/attention-request.schema.json` |
| `I-010D ContextContinuationV2` | `@1` | Consumed | `schemas/v2/context-continuation.schema.json` |
| `I-010E AttentionReceiptV2` | `@2` (immutable staged-record shape only; T052 version rebind — see below) | Consumed | `schemas/v2/attention-receipt.schema.json` |

Only `v2-observation-owner` edits `src/nunchi/observation.py` until
handoff; only `v2-contract-owner` edits `schemas/v2/**`.

**T052 — I-010E `@1` to `@2` version rebind (no-code)**: this slice now
cites the accepted `I-010E AttentionReceiptV2@2` amendment — candidate
`817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`, integrator acceptance
`30aba09f13a6752b4c24811da0d8ec772a9d9682`,
`evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`. That
record's independent canonical-SHA256 comparison proves `observationBody`
is byte-for-byte unchanged between `@1` and `@2`; only the separately
owned `attentionBody` changed (required policy provenance for classifier
outcomes and the closed `NO_WAKE` operational override pair). No
`src/nunchi/observation.py` implementation edit is owed by this version
change — the completed T001–T038 candidate already mirrors the unchanged
observation-stage body field-for-field, and the entire T001–T038 history
and the original attempt-6 dependency record remain unedited per the
Correction and Rejection Preservation contract.

**Accepted-I-010E token-field limitation**: the accepted `I-010E`
observation body is closed with no token field (docs/contracts/nunchi-v2.md
§"I-010E AttentionReceiptV2@1" — this is the exact current heading text in
that 010-owned, NO_IMPACT file; see the NO_IMPACT row above for why this
heading's literal `@1` does not conflict with this slice's `@2` binding).
Token-size proxy results (the slice-owned `utf8-bytes-ceil-div4@1`
estimator: `(serialized_utf8_bytes + 3) // 4`, paired with
`estimator_id`/`estimated_tokens`/`serialized_bytes`/`model_id: null`)
therefore live only in separate evidence (`evidence/v2/observation/*.jsonl`,
e.g. every row's `token_proxy` field) and are never written onto the wire
receipt. This limitation is handed to `v2-contract-owner` and
`v2-integrator`; this slice does not itself alter `I-010E`.

### Shared and reference module paths

| Path | Role |
|---|---|
| `src/nunchi/observation.py` | Product: `I-020A` provider, `ContinuationProvider`, own I-010A/I-010D/I-010E stdlib validation adapter, runtime-adapter-only relational checks, token-size proxy |
| `tests/v2/observation/helpers.py` | Shared test fixtures (T001) |
| `evals/v2/observation/replay.py` | Reusable native-shape replay loader (T002) |
| `evals/v2/observation/compare.py` | Capability-aware reference comparator (T003) |
| `tests/v2/observation/contract_helpers.py` | Own attempt-6 corpus driver (T004) |
| `evals/v2/observation/capabilities/reference_provider.py` | Reference restart/backfill/capability variants (T023) — outside product runtime |
| `evals/v2/observation/run_scenes.py` | Eval-case runner producing the aggregate evidence below |

### Test/eval commands and results

See "Verification commands and results (T036)" and "Attempt-6 corpus
conformance (T037)" above; reproduced here by reference, not restated, to
avoid drift between two copies of the same numbers.

### Evidence paths

- `evidence/v2/observation/identity-and-hygiene.jsonl` (S01, S02, S04, S11, S16 — 9 rows)
- `evidence/v2/observation/budget-sweep.jsonl` (S03, S15 — 6 rows)
- `evidence/v2/observation/continuation.jsonl` (S03, S15 — 6 rows)
- `evidence/v2/observation/s05-recoverability.jsonl` (S05 — 4 rows)
- `evidence/v2/observation/s13-equivalence.jsonl` (S13 — 3 rows)
- `evidence/v2/observation/README.md` (scene-to-record manifest, T035)
- `evidence/v2/observation/handoff.md` (this file)

### Documentation dispositions, validation, and reviewer

Recorded in full above (T028–T034): 1 slice-owned `UPDATE` authored and
validated (`docs/observation/v2.md`), 1 `NO_IMPACT` rationale re-verified
CONFIRMED (`docs/contracts/nunchi-v2.md`), 11 `HANDOFF` deltas routed to
five accepting owners (`v2-integrator` ×6, `v2-transport-owner` ×2,
`v2-hermes-owner` ×1, `v2-claude-owner` ×1, `v2-codex-owner` ×1), plus the
separate `v2-core-owner` continuation-input handoff. Reviewer: the
assigned `v2-observation-owner` implementer.

### Downstream comparator/recoverability/provenance obligations

Recipients (per T043/L3, matching spec.md's declared `Feeds: 040, 050, 060,
070, 080, 090, 100, 110` one-to-one — never a partial or generic subset):
`v2-wake-owner` (040), `v2-transport-owner` (050), `v2-hermes-owner` (060),
`v2-claude-owner` (070), `v2-codex-owner` (080), `v2-adapters-owner` (090),
`v2-security-owner` (100), and `v2-integrator` (110).

- `v2-transport-owner` (050), `v2-hermes-owner` (060), `v2-claude-owner`
  (070), `v2-codex-owner` (080), and `v2-adapters-owner` (090) must each run
  their own real transport binding against `evals/v2/observation/replay.py`,
  `evals/v2/observation/compare.py`, and the restart/backfill reference
  scene (`evals/v2/observation/capabilities/reference_provider.py`) before
  claiming social-suppression eligibility or real-surface parity for that
  surface (FR-011, FR-012). A reference pass recorded by this slice proves
  reusable mechanics only — never an installed-surface claim.
- Slice `030` (`v2-core-owner`) alone implements classifier-safe
  projection/redaction of the `I-010A` `continuation` field in
  `src/nunchi/core.py`; this slice hands the unredacted
  expansion-availability input unchanged (P020-01/T046: an earlier revision
  of this record misnamed this recipient as a nonexistent lane; the correct
  and only name is `v2-core-owner`).
- `v2-wake-owner` (040) owns only the common participant-turn host; it
  consumes this provider's snapshot/receipt outputs without altering them.
- `v2-security-owner` (100) consumes this provider's transport-hygiene and
  authorization-provenance facts (FR-004, FR-010) for its own security
  review of downstream bindings; this slice performs no security
  determination itself.
- `v2-integrator` (110) alone owns the final cross-surface parity claim and
  the one atomic cutover merge.

### Known limitations

- Reference recoverability/equivalence evidence
  (`s05-recoverability.jsonl`, `s13-equivalence.jsonl`) proves the reusable
  restart/backfill and comparator mechanics only; it establishes no
  real-surface conformance, restart-safety, suppression-eligibility, or
  cross-surface parity claim for any installed transport (FR-011, FR-012;
  restated in `docs/observation/v2.md` §"Reference variants and the
  comparator").
- The eval case corpora under `evals/v2/observation/{identity-and-hygiene,
  budgets,continuation,capabilities}/cases.jsonl` are a representative,
  not exhaustive, scene set (9 + 6 + 6 + 7 = 28 cases across the nine
  assigned acceptance scenes); they are smaller than slice 010's
  adversarial contract corpus because this slice's acceptance scenes are
  behavioral (provider/continuation mechanics), not a wire-format
  conformance surface with an oracle to cross-validate against.
- This packet fixes one narrow, out-of-lane test-infrastructure gap in
  `tests/test_governance.py`
  (`_stage_synthetic_active_contract_baseline`): the synthetic
  ACTIVE-slice-010 fixture neutralized every sibling slice's declared
  `**Slice state**` to `PLANNED` but did not reset already-checked task
  boxes in the copied `tasks.md` bodies, so this slice's own legitimate
  T001–T025 completion (checked while the real repository correctly
  declares `ACTIVE`, backed by real evidence) tripped a false positive in
  `test_activation_fixture_is_independent_of_live_slice_state` and
  `test_authorized_contract_slice_can_reach_active_end_to_end` once copied
  verbatim into that isolated fixture alongside a forced `PLANNED` label.
  The fix (resetting checked task boxes for every non-under-test slice
  when the fixture forces it to `PLANNED`) restores the fixture's own
  documented invariant ("independent of live slice state... not only
  `PLANNED` ones") without changing governance policy; `git diff --stat
  fc60858a..418432a -- tests/test_governance.py` is a 9-insertion addition
  confined to that one helper (corrected here per C020-04/T042; the
  originally recorded "four-line addition" claim was inaccurate — see the
  Phase 10 convergence supersession below). This is shared governance test
  infrastructure outside
  `v2-observation-owner`'s file ownership (`src/nunchi/observation.py`,
  `tests/v2/observation/`, `evals/v2/observation/`,
  `evidence/v2/observation/`, `docs/observation/`); it is flagged here for
  `v2-integrator`/governance-tooling review rather than silently folded
  into the observation-slice diff. `PYTHONPATH=src python3 -m unittest`
  is green (1333 tests, OK, 11 skipped) with the fix applied.
- `ObservationProvider`'s bounded retention (`retention_max_events`,
  default 2000) is a constructor default, not a replay-derived budget; the
  plan's "Assumptions" section notes default eager/retention budgets are
  selected by replay evidence during implementation — this default is a
  starting point for downstream owners to tune against their own real
  traffic, not a claimed-optimal value.
- The `around`-direction continuation fetch radius
  (`max(1, cap_events // 2)`) is a simple symmetric-window heuristic; it
  is exercised by `test_around_fetch_requires_anchor` but not swept across
  every event-density scenario a real transport may present.

## Phase 10 convergence supersession (T051)

**Correction sources**: `evidence/v2/observation/pre-review-2026-07-19-sr-critic.md`
findings M020-01 and M020-03, cited by `specs/020-v2-observation/tasks.md`
Phase 10.

This section appends a current-state supersession over the "Verification
commands and results (T036)" and "Proposed handoff packet input (T038)"
sections above. It does not edit that historical text — T001–T038 remain
exactly as originally recorded, per the plan's Rejection/rework contract
and the tasks.md Correction and Rejection Preservation section.

### Two distinct task-manifest SHAs (M020-01)

Convergence (Phase 8), the plan-correction (Phase 9), and this independent
pre-review rework (Phase 10) appended T039–T053 to `tasks.md` after the
original T001–T038 candidate was prepared. Two SHA256 digests are both
valid and refer to different, non-conflicting things:

| Manifest | Task IDs | SHA256 | Where recorded |
|---|---|---|---|
| Activation prefix (immutable) | T001–T038 | `c261de490e30e8e6c447dc5b204e463003f21cf38b69ca03c1895e58b00b6d31` | `evidence/v2/observation/slice-activation.md` (**Initial tasks SHA256**); reproduced unchanged in the "Completed task manifest" section above |
| Final full manifest (this candidate) | T001–T053 | `a21f4b76259e60b044770b3b8f4af1240da30132c2ec4a81ee8c9f8bd43b3a9b` | This section, via `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation`, run 2026-07-19 |

The governance task-manifest digest is computed over each task line's ID
and text with its checkbox state normalized out (`check_governance.py`
`_task_entries`), so it is stable regardless of which boxes are checked;
both digests above were verified stable across multiple runs at this
candidate tree. The activation-prefix SHA remains the correct citation for
what `slice-activation.md` froze at `READY`; the full-manifest SHA above is
the correct citation for what this current candidate completes. Neither
supersedes the other — they describe different, correctly-scoped subsets
of the same append-only task graph. The T038-era claim that "Tasks SHA256
... is identical to the frozen Initial tasks SHA256" is now scoped to
T001–T038 only and does not extend to T039–T053; this section is the
current citation for the complete manifest.

### Full-suite skip count (M020-03)

**Command**: `PYTHONPATH=src python3 -m unittest` (repository baseline, full suite)

**Result (2026-07-19, this candidate tree)**: 1348 tests, OK, 11 skipped.

This supersedes the T036/T038-era claim of "1333 tests, OK, 11 skipped" —
the test count increases by 15 (1333 → 1348), exactly the tests added by
T039 (3 documentation-truthfulness assertions in `test_docs.py`), T040 (3),
T041 (4), T045 (1), T047 (2), and T049 (2); 0 net change from
T042/T043/T044/T046/T048/T050/T052, which are evidence/doc/implementation-only
with no new test method. The skip count coincidentally still reads 11 in this
environment, but per the independent pre-review's own reproduction
(`evidence/v2/observation/pre-review-2026-07-19-sr-critic.md`, "4
skipped" in an isolated scratch clone at the same commit), the skip count
is environment-dependent, not a fixed code fact: `PYTHONPATH=src python3
-m unittest -v` shows the 11 skips in this environment are all
optional-dependency absences (`mcp` extra not installed: 2;
`discord.py` not installed: 3; `mcp` SDK not installed: 3; `jsonschema`
not importable, gating three `evals.v2.contract` oracle-side checks: 3),
none of which is owned by or specific to this slice. Any future citation
of this number should state the environment (installed optional
dependencies) it was reproduced in rather than asserting one universal
count.

### Complete current re-run (2026-07-19, this candidate tree)

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 99 tests, OK, 0 skipped |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 31 rows, 0 FAIL (`identity-and-hygiene.jsonl`: 9; `budget-sweep.jsonl`: 7; `continuation.jsonl`: 8; `s05-recoverability.jsonl`: 4; `s13-equivalence.jsonl`: 3) |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK, 0 failures (202/202 corpus cases still accounted for; corpus revision unchanged) |
| `PYTHONPATH=src python3 -m unittest` (repository baseline, full suite) | 1348 tests, OK, 11 skipped (see "Full-suite skip count" above) |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixture(s) discovered (unchanged from the activation/T036 baseline) |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | Full manifest T001–T053; SHA256 `a21f4b76259e60b044770b3b8f4af1240da30132c2ec4a81ee8c9f8bd43b3a9b` (see table above) |
| `git diff --check` | clean (no whitespace errors), exit 0 |

Every discovered test count above is nonzero. This table, not the T036
table, is the current authoritative re-run result; the T036 table remains
as an accurate historical record of the T001–T038 candidate's own
verification and is not edited.

### T039–T052 correction receipts

| Task | Correction closed | Verified by |
|---|---|---|
| T039 | C020-01 (reaction/membership documentation gap) | `test_documents_reaction_event_structure`, `test_documents_membership_event_structure`, `test_documents_honest_unavailability_for_reaction_and_membership` in `tests/v2/observation/test_docs.py` |
| T040 | C020-02 / D020-01 / M020-02 (self-membership causation scope) | `TestSelfCausedMembership` (3 tests) in `tests/v2/observation/test_provider.py` |
| T041 | C020-03 / M020-04 (`event_visibility` propagation) | `TestEventVisibilityCoverage` (4 tests) in `tests/v2/observation/test_budget_and_continuation.py`; `BUD-S15-004` in `evidence/v2/observation/budget-sweep.jsonl` |
| T042 | C020-04 (inaccurate diff-size claim) | "Known limitations" above now cites `git diff --stat fc60858a..418432a -- tests/test_governance.py` (9 insertions) |
| T043 | C020-05 / L3 (incomplete handoff recipients) | "Downstream comparator/recoverability/provenance obligations" above names all eight recipients |
| T044 | C020-06 / L4 (capability vocabulary too thin) | `docs/observation/v2.md` §"Reference variants and the comparator" |
| T045/T046 | P020-01 / A020-F2 (nonexistent downstream owner lane name) | `test_names_real_v2_core_owner_lane_for_projection_handoff_not_nonexistent_lane` in `tests/v2/observation/test_docs.py`; zero remaining occurrences of the wrong lane name in this file or `docs/observation/v2.md` |
| T047/T048 | H020-01 (cross-direction cursor replay) | `test_cross_direction_cursor_replay_rejects`, `test_same_direction_cursor_replay_still_paginates` in `tests/v2/observation/test_budget_and_continuation.py`; `CONT-S03-005` in `evidence/v2/observation/continuation.jsonl` |
| T049/T050 | L020-01 (truncated `around` two-null coverage) | `test_truncated_around_fetch_reports_truthful_side_specific_coverage`, `test_untruncated_around_fetch_reports_no_more_on_either_side` in `tests/v2/observation/test_budget_and_continuation.py`; `CONT-S03-006` in `evidence/v2/observation/continuation.jsonl` |
| T051 | M020-01 / M020-03 (this section) | This section |
| T052 | Accepted I-010E `@1`→`@2` version rebind | "Interface inventory" and "Upstream 010 references" above; `docs/observation/v2.md` §"The observation-stage receipt" |

All eleven Phase 8/9/10 findings (C020-01 through C020-06, P020-01,
A020-F1 through A020-F3, H020-01, M020-01 through M020-04, L020-01) are
closed as of this section. T053 performs the final complete verification
pass and records its own receipt before this candidate proceeds to
`/speckit-converge`.

### T053 final verification receipt

**Run**: 2026-07-19, at this candidate tree, after T051's own edit to this
file (re-run to confirm T051's addition introduced no regression — the
first pass caught and fixed one such regression: T051's correction-receipts
table had briefly reintroduced a literal occurrence of the wrong lane name
that T045's own red assertion correctly caught; corrected in place before
this receipt, per the Correction and Rejection Preservation contract this
is a same-run fix, not a new append-worthy defect since T051 had not yet
been checked complete).

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 99 tests, OK, 0 skipped |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 31 rows, 0 FAIL |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK, 0 failures |
| `PYTHONPATH=src python3 -m unittest` (repository baseline, full suite) | 1348 tests, OK, 11 skipped (unchanged from the "Complete current re-run" table above; reproduced twice) |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixture(s) discovered |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | SHA256 `a21f4b76259e60b044770b3b8f4af1240da30132c2ec4a81ee8c9f8bd43b3a9b` (identical to the "Complete current re-run" table above — the digest is checkbox-state-independent, so marking T051/T053 `[X]` does not change it) |
| `git diff --check` | clean (no whitespace errors), exit 0 |

Every discovered test count above is nonzero and reproduces the "Complete
current re-run" table exactly. All T039–T052 correction receipts above are
verified current. This candidate is ready for `/speckit-converge`.
