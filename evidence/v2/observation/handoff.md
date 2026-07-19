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

## Phase 11 convergence supersession (T054)

**Correction source**: `evidence/v2/observation/convergence-phase11-2026-07-19.md`,
finding F1 CRITICAL, reproduced live against the completed T001–T053
candidate tree at `77a94cf1f56e70d1f0a79631ee9efba0b6e74a62`, cited by
`specs/020-v2-observation/tasks.md` Phase 11.

This section appends a current-state supersession over the "Complete current
re-run" and "T053 final verification receipt" tables above. It does not edit
that historical text — T001–T053 remain exactly as originally recorded, per
the plan's Rejection/rework contract and the tasks.md Correction and
Rejection Preservation section.

### The defect and the fix

`ContinuationProvider.fetch`'s `around` branch derived `has_more_before`
from the fixed radius window boundary alone
(`has_more_before = around_window_start > 0`), ignoring cap-based
truncation of the ascending candidate scan at an index strictly before
`anchor_index`. Reproduction: 5 events `e1`–`e5`, anchor `e3` at index 2,
`max_events_per_fetch=6` (radius 3, `around_window_start=0`,
`around_window_end=5`), `max_bytes_per_fetch` sized to admit only `e1` —
the page served only `['e1']` yet reported `has_more_before: False` even
though `e2`, a genuine before-anchor event, was never served.

The fix tracks whether the cap-truncation index (`next_index`) landed
strictly before `anchor_index` and ORs that fact into `has_more_before`,
alongside the existing `around_window_start > 0` window-boundary check:

```python
cap_truncated_before_anchor = next_index is not None and next_index < anchor_index
has_more_before = around_window_start > 0 or cap_truncated_before_anchor
```

`has_more_after`'s formula (`next_index is not None or around_window_end <
len(events)`) did not change: any cap truncation within the ascending
window scan — whether the truncation index lands before, at, or after
`anchor_index` — always leaves at least the anchor-or-later portion of the
window unserved (the scan proceeds in ascending order from
`around_window_start`, so a truncation index `< anchor_index` means the
scan never even reached `anchor_index`), so `next_index is not None`
already implied `has_more_after` correctly in every case, including this
reproduction (`has_more_after: True` was already accurate before and after
the fix).

### T054 receipt

| Check | Result |
|---|---|
| RED regression test (pre-fix) | `test_around_fetch_cap_truncated_strictly_before_anchor_reports_has_more_before` in `tests/v2/observation/test_budget_and_continuation.py` — `AssertionError: False is not true` on `has_more_before` |
| GREEN regression test (post-fix) | Same test — passes; page serves `['e1']`, `has_more_before: True`, `has_more_after: True` |
| Existing `around` coverage unweakened | `test_truncated_around_fetch_reports_truthful_side_specific_coverage` and `test_untruncated_around_fetch_reports_no_more_on_either_side` (T049/T050) still pass unchanged |
| Adversarial eval case | `CONT-S03-007` in `evals/v2/observation/continuation/cases.jsonl`, result recorded in `evidence/v2/observation/continuation.jsonl` (`PASS`, `has_more_before: true`, `has_more_after: true`) |
| Documentation | No wording change owed in `docs/observation/v2.md` per `plan.md`'s Documentation Impact and Freshness row for T054 — the existing "`has_more_before`/`has_more_after` report honest boundary omission" claim already states the target truthful behavior this fix conforms to |

### Final full-manifest SHA (T001–T054)

| Manifest | Task IDs | SHA256 |
|---|---|---|
| Activation prefix (immutable) | T001–T038 | `c261de490e30e8e6c447dc5b204e463003f21cf38b69ca03c1895e58b00b6d31` (unchanged; see Phase 10 section above) |
| Final full manifest (this candidate) | T001–T054 | `b305267271aed22a83c98c3a95e8f967edfbe080115d9ee58d6a99eacaca4536`, via `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation`, run 2026-07-19 (supersedes the Phase 10 section's T001–T053 digest `a21f4b76259e60b044770b3b8f4af1240da30132c2ec4a81ee8c9f8bd43b3a9b`, which remains an accurate historical record of that intermediate manifest) |

### Complete T053-matrix re-run (2026-07-19, T001–T054 candidate tree)

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 100 tests, OK, 0 skipped (+1 over the Phase 10 table: T054's new regression test) |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 32 rows, 0 FAIL (`identity-and-hygiene.jsonl`: 9; `budget-sweep.jsonl`: 7; `continuation.jsonl`: 9 (+1, `CONT-S03-007`); `s05-recoverability.jsonl`: 4; `s13-equivalence.jsonl`: 3) |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK, 0 failures (202/202 corpus cases still accounted for; corpus revision unchanged) |
| `PYTHONPATH=src python3 -m unittest` (repository baseline, full suite) | 1349 tests, OK, 4 skipped in the owner-side convergence verification environment (+1 test over the Phase 10 table, exactly T054's new regression; no failures) |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixture(s) discovered (unchanged) |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | Full manifest T001–T054; SHA256 `b305267271aed22a83c98c3a95e8f967edfbe080115d9ee58d6a99eacaca4536` (see table above) |
| `git diff --check` | clean (no whitespace errors), exit 0 |

Every discovered test count above is nonzero. This table is the current
authoritative re-run result; the Phase 10 and T036 tables remain as accurate
historical records of their respective candidate trees and are not edited.

F1 CRITICAL is closed. The plan.md Constitution Check rows "Truthful
identity/observation" and "Evidence before claims", both marked
`BLOCKED (T054)`, return to `PASS` as of this candidate — see the
corresponding plan.md update accompanying this section.

## Phase 12 attempt-1 rejection supersession (T055–T059)

**Correction source**:
`evidence/v2/observation/review-2026-07-19-v2-integrator-attempt-1.md`,
findings H020-A1-01 HIGH and M020-A1-02 MEDIUM, cited by
`specs/020-v2-observation/tasks.md` Phase 12. Attempt 1 at
`7b00bcaa4a2b8af12b6eb71bf6d8b098f4cfeba7` remains rejected and its
records remain unchanged. This section is the append-only implementation and
evidence supersession for candidate attempt 2.

### RED reproductions

The Phase 12 tests were run before the product fixes. Eight focused tests
produced seven expected failures and one control pass:

- `test_around_cursor_progresses_without_overlap_and_exhausts` failed because
  page 2 repeated `['e2', 'e3']` instead of progressing to `['e4']`;
- `test_continuation_fetch_reports_byte_only_truncation` failed because the
  page reported `['events']` instead of `['bytes']`;
- `test_continuation_fetch_reports_both_truncation_causes` failed because the
  page reported `['events']` instead of `['events', 'bytes']`;
- `test_around_cursor_rejects_a_changed_anchor` failed because the minted
  cursor was not bound to its original anchor;
- `test_around_cursor_preserves_original_window_when_page_cap_changes` failed
  because a larger page cap widened the already-minted fixed window and served
  `['e4', 'e5']` instead of only the original window's remaining `['e4']`;
- `test_fetch_rejects_when_byte_cap_cannot_admit_the_next_event` failed because
  an empty page minted the same-index non-progress cursor;
- `test_around_cursor_preserves_event_identity_across_retention_shift` failed
  because bounded deque eviction shifted the stored numeric index and page 2
  served `['e5']` instead of the original window's remaining `['e4']`;
- `test_continuation_fetch_reports_event_only_truncation` passed as the control.

The pre-fix eval replay likewise returned 3 FAIL across 13 continuation rows,
with every other eval suite green. These receipts reproduce H020-A1-01 and
M020-A1-02 without weakening the existing direction-binding or coverage tests.

### Fix and focused GREEN receipts

`ContinuationProvider.fetch` now consumes a validated `around` cursor as the
next unserved index inside the original fixed anchor-bound window. The host
stores that opaque cursor's anchor and window bounds, rejects an anchor swap,
does not let a later page-cap change widen the minted window, and retains the
remaining event identities so deque eviction cannot retarget a cursor. Page 1 for
e1–e5 around anchor e3 serves `['e2', 'e3']`; replay of its cursor serves
`['e4']`, has no event overlap, and emits no further cursor. Before/after
pagination, handle/direction binding, authoritative order, expiry, and the
T054 side-specific coverage formula remain unchanged.

A byte cap that cannot admit even the next single authoritative event now
raises `ContinuationError` instead of returning an empty page with a cursor at
the same index. Therefore every cursor the provider actually mints either
advances or exhausts.

The fetch loop now records `event_cap_reached` and `byte_cap_exceeded`
independently at the exact candidate that stops the page. The stable
`coverage.truncated_by` order is therefore `['events']` for event-only,
`['bytes']` for byte-only, and `['events', 'bytes']` when both conditions are
simultaneously true.

Focused verification:

| Check | Result |
|---|---|
| Eight Phase 12 unit tests | 8 tests, OK; cursor progresses/exhausts, preserves anchor/window/event-identity binding across retention shifts, rejects a zero-progress byte cap, and all three truncation-cause shapes are exact |
| `CONT-S03-008` | PASS; page IDs `[['e2', 'e3'], ['e4']]`, no repeated cursor or event |
| `CONT-S03-009` | PASS; after e1 eviction shifts every retained index, page 2 still serves original remaining identity `['e4']` rather than `['e5']` |
| `CONT-S15-003` | PASS; `truncated_by: ['events']` |
| `CONT-S15-004` | PASS; `truncated_by: ['bytes']` |
| `CONT-S15-005` | PASS; `truncated_by: ['events', 'bytes']` |

### T059 final verification matrix

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 108 tests, OK, 0 skipped |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 37 rows, 0 FAIL (`identity-and-hygiene.jsonl`: 9; `budget-sweep.jsonl`: 7; `continuation.jsonl`: 14; `s05-recoverability.jsonl`: 4; `s13-equivalence.jsonl`: 3) |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; all 202 frozen attempt-6 cases accounted for (100 consumed, 102 explicitly non-consumed), zero mismatches |
| `PYTHONPATH=src python3 -m unittest` | 1357 tests, OK, 4 environment-dependent skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | Full append-only manifest T001–T059; SHA256 `48fce91126f6c1d0515f5e279c8deec28d1bb9b468e8a209426981acce9b7bff` |
| `git diff --check` | clean, exit 0 |

Every discovered test/eval/fixture count is nonzero. The 4 full-suite skips are
environment-dependent optional integrations, not Slice 020 failures. This
matrix supersedes the Phase 11 matrix for candidate attempt 2 while preserving
every earlier matrix as an accurate historical receipt.

**Non-blocking follow-up**: `ContinuationProvider` still retains issued
capabilities in `_capabilities`, minted cursor strings in each handle's
`_cursors` set, and the corresponding fixed-window bindings in
`_around_cursor_windows` (including remaining event identities) for the lifetime
of the in-memory provider. Phase 12 fixes cursor
progression and truthful cap attribution; it does not add expiry-driven cleanup
or a size bound to those bookkeeping collections, and this packet makes no
bounded-bookkeeping claim. Production host owners must add lifecycle pruning or
explicit limits before treating a long-lived provider as memory-bounded. This
is follow-up hardening, not an attempt-2 correctness blocker for the accepted
in-memory reference seam.

H020-A1-01 and M020-A1-02 are closed. The plan.md Constitution Check rows
"Truthful identity/observation" and "Evidence before claims" return to `PASS`.
This evidence authorizes convergence and candidate-attempt-2 preparation; it
does not accept the slice or authorize integration, cutover, deployment,
release, or promotion.

## Phase 13 evidence-manifest convergence supersession (T060)

A subsequent `/speckit-converge` pass found that the separate
`evidence/v2/observation/README.md` scene-to-record manifest still described the
original 28-row candidate even though the generated JSONL evidence had grown.
T060 corrects that manifest without changing product behavior:

| Evidence file | Verified scene counts | Rows | FAIL |
|---|---|---:|---:|
| `identity-and-hygiene.jsonl` | S01 2; S02 2; S04 2; S11 2; S16 1 | 9 | 0 |
| `budget-sweep.jsonl` | S03 3; S15 4 | 7 | 0 |
| `continuation.jsonl` | S03 9; S15 5 | 14 | 0 |
| `s05-recoverability.jsonl` | S05 4 | 4 | 0 |
| `s13-equivalence.jsonl` | S13 3 | 3 | 0 |
| **Total** | all nine applicable scenes | **37** | **0** |

The manifest now states those exact counts and remains reproducible with
`PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes`.

The final append-only task graph is T001–T060, all complete, with SHA256
`de7bbcf87e45b2d06d8685023b404c29f06e088930f7005296984ed33fd3c85d`
from `python3 scripts/check_governance.py --task-manifest
specs/020-v2-observation`. The T001–T059 digest in the T059 matrix remains an
accurate historical receipt for the graph immediately before convergence
appended T060.

T060 closes the evidence-manifest contradiction and permits another convergence
pass. It does not accept the slice or authorize integration, cutover,
deployment, release, or promotion.

## Phase 14 retention-safe before/after cursor supersession (T061–T065)

Independent convergence review of candidate `cd61dfd649b8f03f340b553ac3864183d42fe567`
found H020-A2-01 HIGH: `before` and `after` cursor tokens carried stale bounded-deque
positions. Owner-side RED reproduction proved `before` repeated `e3` after a one-event
retention shift and `after` skipped original next event `e4` to serve `e5`.

The provider now binds every cursor direction to its original direction, anchor, and
remaining event identities. Replay resolves those identities against the live event
index, fails closed when any original identity was evicted, and uses monotonic opaque
tokens so a shifted live index cannot repeat a cursor despite page progress. The
original remainder is closed at mint time: later arrivals are not silently admitted.

Focused receipts:

| Check | Result |
|---|---|
| T061/T062 RED | 2 tests, 2 failures: `before` did not raise after remainder eviction; `after` served `e5` instead of `e4` |
| T061/T062 GREEN | 2 tests, OK |
| `tests.v2.observation.test_budget_and_continuation` | 35 tests, OK |
| `CONT-S03-010` | PASS; after pages `[['e3'], ['e4'], ['e5']]`, excluding later `e6` |
| `CONT-S03-011` | PASS; before replay rejects after original remainder identity eviction |

Final verification matrix:

| Command | Result |
|---|---|
| `PYTHONPATH=src python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 110 tests, OK, 0 skipped |
| `PYTHONPATH=src python3 -m evals.v2.observation.run_scenes` | 5 suites, 39 rows, 0 FAIL (`identity-and-hygiene.jsonl`: 9; `budget-sweep.jsonl`: 7; `continuation.jsonl`: 16; `s05-recoverability.jsonl`: 4; `s13-equivalence.jsonl`: 3) |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; all 202 attempt-6 cases accounted for, zero mismatches |
| `PYTHONPATH=src python3 -m unittest` | 1359 tests, OK, 4 environment-dependent optional-integration skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | T001–T065 all complete; SHA256 `aa46ba303fe6f2d8a8642f590e19c597bd39bc6c736a71b4260f6976f2e857f4` |
| `git diff --check` | clean, exit 0 |

The evidence manifest now totals 39 rows: 9 + 7 + 16 + 4 + 3. The unbounded
in-memory cursor/capability bookkeeping limitation above remains explicit. At
this candidate it comprises `_capabilities`, `_cursors`, `_cursor_sequences`, and
`_cursor_windows`; Phase 14 changes correctness under retention, not lifecycle
pruning.

H020-A2-01 is closed. This evidence permits a fresh convergence and candidate-attempt-2
review; it does not accept the slice or authorize integration, cutover, deployment,
release, or promotion.

## Phase 15 bounded cursor lifecycle supersession (S020-A3-01)

The independent fail-closed review of superseded commit `cd61dfd` identified a
resource-security finding that remained applicable through `247e282`: every
minted cursor copied its full remaining-ID suffix and every consumed cursor was
retained. Owner reproduction over 500 events retained 498 cursor records with
124,251 event-ID references. The review's 2,000-event shape retained roughly
1,999,000 references. `evidence/v2/observation/convergence-phase15-2026-07-19.md`
preserves the rejection and required correction.

T066 first established four RED lifecycle/resource checks: missing shared-window
metadata, unsupported active-cursor and handle bounds/revocation, and absent
expiry cleanup. T067–T068 then changed only host-side implementation state:

- each sequence owns one immutable ordered event-ID tuple and each cursor stores
  only its next position plus direction/anchor/fixed-window binding;
- a validated incoming cursor is consumed atomically after response validation,
  with its map, set, and capability-list entries removed before its successor is
  registered;
- exhausted chains retain no cursor/window records and expose no stale
  capability `cursors` field;
- `ContinuationProvider` defaults to at most 64 issued handles and 16 active
  cursors per handle, both constructor-configurable positive integers;
- `revoke(handle_id)` idempotently releases every host-side collection for the
  handle, and an expired fetch rejects while reclaiming that handle;
- fresh sequences reject at the active-cursor bound, while following an active
  one-shot cursor may replace itself without increasing the bound.

The accepted I-010A/I-010D wire shapes are unchanged. Same token replay now has
explicit one-shot semantics: a consumed cursor rejects rather than accidentally
re-serving a page. Direction, anchor, immutable identity, fixed-window,
retention-eviction, cap, ordering, exact-dedup, and zero-progress guarantees all
remain enforced.

`CONT-S15-006` deterministically paginates `e5` through `e1` one event per page
and records `max_active_cursor_records=1`, `shared_window_object_count=1`, and
`exhausted_cursor_records=0`. A direct 2,000-event reproduction returned 1,999
pages with one active cursor, at most 1,999 retained event-ID references, zero
cursor records after exhaustion, and no capability cursor field: linear window
state instead of the rejected quadratic 1,999,000-reference shape.

Phase 15 verification matrix:

| Command | Result |
|---|---|
| Phase 15 four-test RED group on `058f4a5` | expected RED: 1 failure + 3 errors; missing lifecycle behavior confirmed |
| `PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_budget_and_continuation` | 39 tests, OK |
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 114 tests, OK, 0 skipped |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 40 rows, 0 FAIL (`identity-and-hygiene.jsonl`: 9; `budget-sweep.jsonl`: 7; `continuation.jsonl`: 17; `s05-recoverability.jsonl`: 4; `s13-equivalence.jsonl`: 3) |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; all 202 attempt-6 cases accounted for, zero mismatches |
| `PYTHONPATH=src python3 -m unittest` | 1363 tests, OK, 4 environment-dependent optional-integration skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| `ruff check src/nunchi/observation.py tests/v2/observation/test_budget_and_continuation.py evals/v2/observation/run_scenes.py` | clean, exit 0 |
| `uvx bandit -q -r src/nunchi/observation.py` | clean, exit 0; 0 findings after two LOW runtime `assert` uses were replaced with explicit fail-closed errors |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | T001–T070 all complete; SHA256 `f3125f49702a2b4b593f95fa68587859146dafb26f892f8129e3a17337022b99` |
| `git diff --check` | clean, exit 0 |

S020-A3-01 is closed locally. The previous Phase 12/14 unbounded-bookkeeping
paragraphs remain unchanged as append-only historical evidence and are
superseded by this section. This permits a fresh convergence and candidate
attempt-2 review; it does not accept the slice or authorize integration,
cutover, deployment, release, or promotion.

## Phase 16 authority, event-instance, coverage, and retained-state supersession

The independent review pinned to `75ff65f` found six additional defects that
remained applicable after the Phase 15 resource fix at `dbe220d`:
S020-A4-01–03/A4-06 and H020-A4-04–05. Owner-side current-tip probes reproduced
all six: omitted/malformed fetch time served expiring authority; mutation of the
returned capability rewrote private binding/direction/caps; cursor provenance
contaminated the closed capability wire object; a reingested `e1` replaced the
original cursor instance; a final `after` page hid known later `e6`; and a
retention-three provider accumulated 100 delivery IDs and 100 actor records.
`evidence/v2/observation/convergence-phase16-2026-07-19.md` preserves the
rejection and correction requirements.

T071–T073 established the primary RED layer: 10 test methods produced 13
expected failures covering authority/expiry/wire isolation, replacement event
and anchor instances, later-arrival side coverage, and retained auxiliary state.
Three additional architectural probes each failed on their intended path before
GREEN: ingestion input aliasing, returned snapshot/page/receipt aliasing, and
late actor-schema validation that poisoned a delivery ID.

T074–T076 then changed private reference-provider state without altering any
accepted I-010A/I-010D/I-010E wire schema:

- `issue()` stores and returns separate deep copies; cursor provenance exists
  only in private host maps, so returned capabilities remain closed-schema clean;
- expiry is valid only when issuance and fetch timestamps parse as timezone-aware
  ISO-8601; absent, malformed, or naive fetch time rejects when expiry exists;
- accepted events receive monotonic host generations; capability triggers,
  cursor anchors, and immutable window entries bind `(event_id, generation)` and
  reject evicted/reingested replacements;
- cursor metadata carries snapshot generation plus immutable side-omission facts,
  so later accepted arrivals set final `has_more_after=true` without entering the
  original remainder;
- retained delivery IDs, event generations, and event-to-delivery mappings are
  removed with deque eviction; invalid events/actors commit no delivery state;
- actor facts are schema-validated before commit, unrelated supplied actors are
  ignored, and the registry is pruned to self plus actors referenced by retained
  events;
- accepted input events/actors and returned capabilities, snapshots, continuation
  pages, actors, and receipt coverage are copied across the authority boundary,
  preventing caller mutation of host state or source request documents.

T077 adds five adversarial resource/authority cases. The continuation evidence
now contains 22 rows, including `CONT-S15-007` fail-closed missing fetch time,
`CONT-S15-008` returned-authority isolation, `CONT-S03-012` replacement-instance
rejection, `CONT-S03-013` truthful later-arrival coverage, and `CONT-S15-009`
retention-coupled delivery/generation/actor counts. Together with the existing
resource case, every row is PASS.

A fresh 2,000-event one-event-per-page probe produced:

```text
pages:                              1999
max_active_cursor_records:             1
max_generation_bound_window_refs:   1999
exhausted_cursor_records:              0
returned_capability_wire_clean:      true
retained_delivery_ids:              2000
retained_event_generations:         2000
retained_actor_records:                2
```

The first two retained counts equal the configured 2,000-event buffer; they do
not grow with traversals. Actor state equals self plus the one retained author.

Phase 16 verification matrix:

| Command | Result |
|---|---|
| Primary Phase 16 RED group on `aa0da7a` | expected RED: 10 methods, 13 failures |
| Three focused alias/actor-validation RED probes | each failed on the intended missing isolation/early-validation behavior |
| `PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_budget_and_continuation` | 51 tests, OK |
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 126 tests, OK, 0 skipped |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 45 rows, 0 FAIL (`identity-and-hygiene.jsonl`: 9; `budget-sweep.jsonl`: 7; `continuation.jsonl`: 22; `s05-recoverability.jsonl`: 4; `s13-equivalence.jsonl`: 3) |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; all 202 attempt-6 cases accounted for, zero mismatches |
| `PYTHONPATH=src python3 -m unittest` | 1375 tests, OK, 4 environment-dependent optional-integration skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| `ruff check src/nunchi/observation.py tests/v2/observation/test_budget_and_continuation.py evals/v2/observation/run_scenes.py` | clean, exit 0 |
| `uvx bandit -q -r src/nunchi/observation.py` | clean, exit 0; 0 findings |
| static secret scan over the working diff | `STATIC_SCAN CLEAN` |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | T001–T079 all complete; SHA256 `ca4742489a32b6631a99b212c533be4bbbde44b79bf2c5749952d662eeaf5fd0` |
| `git diff --check` | clean, exit 0 |

S020-A4-01–03/A4-06 and H020-A4-04–05 are closed locally. All earlier attempt
records remain unchanged and are superseded only by appended sections. This
permits a fresh immutable convergence/candidate-attempt-2 review; it does not
accept the slice or authorize integration, cutover, deployment, release, or
promotion.

## Phase 17 exact-expiry boundary supersession (S020-A5-01)

After immutable Phase 16 candidate `55620049a4abd63672951ea2bd221558846fe1df`
was pushed, an owner-side fail-closed boundary probe proved that
`fetch_time == expires_at` still served event `e1`. The durable rejection and
direct probe are recorded in
`evidence/v2/observation/convergence-phase17-2026-07-19.md`.

T080 added
`test_exact_expiry_instant_rejects_and_reclaims_handle`; it failed RED because
no `ContinuationError` was raised. T081 changes the expiry predicate from `>`
to `>=`, making `expires_at` the first invalid authority instant. The isolated
test and the 52-test focused continuation suite are GREEN, and deterministic
case `CONT-S15-010` rejects exact equality before serving an event. Regenerated
evidence now contains 46 PASS rows and 0 FAIL: 9 identity and hygiene, 7 budget,
23 continuation, 4 recoverability, and 3 equivalence.

Phase 17 verification matrix:

| Command | Result |
|---|---|
| Exact-boundary RED on `107f84b` | 1 intended failure: `ContinuationError` was not raised at `fetch_time == expires_at` |
| Exact-boundary GREEN | 1 test, OK; expired handle and cursor-window state reclaimed |
| `PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_budget_and_continuation` | 52 tests, OK |
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 127 tests, OK, 0 skipped |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 46 rows, 0 FAIL (9 identity; 7 budget; 23 continuation; 4 recoverability; 3 equivalence) |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; all 202 attempt-6 cases accounted for, zero mismatches |
| `PYTHONPATH=src python3 -m unittest` | 1376 tests, OK, 4 environment-dependent optional-integration skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| `ruff check src/nunchi/observation.py tests/v2/observation/test_budget_and_continuation.py evals/v2/observation/run_scenes.py` | clean, exit 0 |
| `uvx bandit -q -r src/nunchi/observation.py` | clean, exit 0; 0 findings |
| high-confidence static secret scan over the working diff | `STATIC_SECRET_SCAN CLEAN` |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | T001–T082 all complete; SHA256 `94e0ab99732a95c983dfdc587612e5bd516238ad64fddabd5adc63f0cd89c22d` |
| `git diff --check` | clean, exit 0 |

S020-A5-01 is closed locally. A fresh immutable review of the post-fix candidate
is still required before candidate attempt 2 can advance through the ordinary
lifecycle. This section does not accept the slice or authorize integration,
cutover, deployment, release, or promotion.

## Phase 18 packet-history correction (T097)

The Phase 11 statement above that “T001–T053 remain exactly as originally
recorded” is false when applied to this mutable packet file. Git-object history
shows non-prefix edits to earlier T036/T038 packet text across correction
passes. This appended correction supersedes that provenance claim without
rewriting it again.

The narrow lifecycle ledgers
`evidence/v2/observation/slice-candidate.md` and
`evidence/v2/observation/slice-handoff.md` remain append-only. This broader
`handoff.md` packet is mutable, append-superseded evidence: historical tables
remain useful as dated receipts, but neither their bytes nor every surrounding
claim can be described as immutable. Future verification must cite the current
superseding section and the relevant Git objects rather than infer append-only
history from this packet’s prose.

## Phase 18–19 immutable preparation receipt (T098–T103)

Late review
`evidence/v2/observation/review-2026-07-19-5562004-binding-rejection.md`
rejected exact commit `55620049a4abd63672951ea2bd221558846fe1df` for two HIGH
findings. Exact expiry was stale against Phase 17. The additional-property
host-context finding reproduced on the current tree: a context containing
`unexpected_tenant="other"` served event `e1`.

T100 pinned two RED failures: the additional-property context was accepted on a
fresh fetch and on a one-shot cursor replay. T101 now validates `host_context`
with `_check_continuation_binding`, preserves detailed field mismatch errors,
and requires complete dictionary equality with the issued closed `bound_to`
object. Missing, malformed, wrong-valued, and additional properties reject
before page or cursor state commits; the exact four-field context accepts.
T102 adds deterministic case `CONT-S15-011` and executable documentation.

Implementation commits:

- `84d161f93fe0d36dd502998ce03888993b2ba5ef` — hard bytes, origin merge
  identity, shared atomicity, linear replay, retention gaps, packet correction,
  exact host binding, evaluator/docs/evidence, and Phase 18/19 task graph;
- `1ac2ffe6836a9a674a9129364413d2c370082757` — explicit synthetic-secret
  fixture marker and its regression coverage.

The implementation staged-diff SHA256 before `84d161f` was
`178df3a740d157670c76365d87b569ac3f531a3a284a069565e975b4d5493fd6`.

### Complete preparation matrix

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 146 tests, OK |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 47 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 3 equivalence) |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_phase18_adversarial` | 11 rows, 0 FAIL; N=64/128 cursor replay retained-deque visits 0/0 after initial window creation |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; 202/202 cases accounted for, zero mismatches |
| `PYTHONPATH=src python3 -m unittest` | 1395 tests, OK; 4 optional-integration skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| `ruff check ...` over all changed Python | clean, exit 0 |
| `uvx bandit -q -r src/nunchi/observation.py evals/v2/observation/run_phase18_adversarial.py scripts/check_slice020_secrets.py` | clean, exit 0; 0 findings |
| `python3 scripts/check_slice020_secrets.py --base 5e2380af3c9abda63ff55c61f3ef16491cd1776c --head 1ac2ffe6836a9a674a9129364413d2c370082757` | `SLICE020_SECRET_SCAN CLEAN`; 19 files, 1307 additions, 4 matchers |
| `python3 scripts/check_slice020_secrets.py --base fc60858a3810e2f53d9574cce1eb9589bd19b55b --head 1ac2ffe6836a9a674a9129364413d2c370082757` | `SLICE020_SECRET_SCAN CLEAN`; whole slice, 57 files, 8087 additions, 4 matchers |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | T001–T103 graph SHA256 `e0c0b49005566b2ab9c18e5789608d59eb416d324f4a9ec3c5aaa35c7a26b76e` |
| `git diff --check` | clean, exit 0 |

T083–T102 are locally complete. T103 remains BLOCKED pending commit/push of this
receipt and one fresh independent fail-closed review of the exact immutable
candidate. Nothing in this section accepts the slice or authorizes integration,
cutover, deployment, release, promotion, or candidate-attempt-2 handoff.

## Phase 20 scanner-bypass correction

Owner review of immutable preparation `cd8917c56f0d051f52cdba68c177d45e7a9f1103`
found that the scanner skipped every added line containing
`slice020-secret-fixture`, regardless of repository path or content. A direct
production-path probe returned zero findings for a matcher-shaped `API_KEY`
assignment carrying that marker. `cd8917c` is therefore rejected as a final
candidate target; the earlier CLEAN rows remain accurate outputs of a
bypassable scanner and do not authorize handoff.

T105 removes the marker exemption entirely. Synthetic keys are now assembled
at test runtime so no complete matcher-shaped token is stored as an added source
line. A dedicated regression proves marker text does not suppress a real
finding.

Phase 20 pre-commit matrix:

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_static_secret_scanner` | 4 tests, OK |
| marker-bypass direct GREEN probe | 1 finding, expected 1 |
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 147 tests, OK |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 47 rows, 0 FAIL |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_phase18_adversarial` | 11 rows, 0 FAIL |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; 202/202 accounted for |
| `PYTHONPATH=src python3 -m unittest` | 1396 tests, OK; 4 optional-integration skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| Ruff / production Bandit / governance / task manifest / `git diff --check` | clean |

T106 remains open until a new immutable commit is pushed and scanned over the
whole activation-to-candidate range. T107 and T103 remain open until a fresh
independent review of that exact object returns without blockers. This section
does not establish `CONVERGED`, `HANDOFF_READY`, acceptance, integration,
deployment, release, promotion, or cutover authority.

## Phase 21 comparator-completeness correction

Late immutable review of `f38a4fe4cf98fd4d63887e0baf735db7427298f6`
identified one current mechanism not covered by the earlier Phase 18 rejection:
the reusable comparator silently discarded authoritative event order,
one-sided event fields, actors, and almost all coverage state. The other four
HIGH findings in that review are closed by Phases 18–20; the complete
adjudication is preserved at
`evidence/v2/observation/review-2026-07-19-f38a4fe-late-rejection.md`.

Current-tree RED produced five intended failures. Before correction,
`compare_requests()` returned `equivalent: true` with no unexplained differences
for reversed order, a missing native event field, actor divergence, and
coverage/budget divergence; `compare_pages()` likewise ignored successor-cursor
presence and side coverage.

T110 now compares schema/self/room/actors, authoritative common-event order,
complete event shapes, trigger/anchor, all semantic coverage fields, direction,
continuation capability shape, and successor-cursor presence. Only request-local
correlation IDs, issued handle IDs, exact cursor bytes, and expiry-clock values
are opaque. Capability explanations must name unavailable event/actor IDs or
semantic paths; continuity differences are labelled as declared capability, and
one-sided facts remain unexplained.

Phase 21 matrix:

| Command | Result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_equivalence` | 11 tests, OK; five former false-equivalence mechanisms covered |
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 153 tests, OK |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 52 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 8 equivalence) |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_phase18_adversarial` | 11 rows, 0 FAIL |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK; 202/202 accounted for |
| `PYTHONPATH=src python3 -m unittest` | 1402 tests, OK; 4 optional-integration skips |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| expanded Ruff / production Bandit / governance / task manifest / `git diff --check` | clean |

T106/T112 remain open until this tree is committed, pushed, exact-scanned, and
freshly reviewed. T103/T107 remain historical convergence blockers folded into
that final review. Nothing here establishes `CONVERGED`, `HANDOFF_READY`,
acceptance, integration, deployment, release, promotion, or cutover authority.

## Phase 22 provider-attestation and input-order correction

Independent Codex review of `cd8917c56f0d051f52cdba68c177d45e7a9f1103`
reproduced receipt-authority, timestamp-order, contradictory-unroutable,
constructor-validation, and corpus-byte-identity gaps. The full rejection and
current adjudication are preserved in
`review-2026-07-19-cd8917c-codex-rejection.md` and
`convergence-phase22-provider-attestation-2026-07-19.md`.

Current-tree RED accepted duplicate and fabricated receipts, emitted decreasing
parseable timestamps, accepted `unroutable` with candidate-only fields, and
retained an event under invalid visibility before snapshot failed. T114–T117
close those mechanisms:

- a bounded private deep copy ties each issued snapshot to one exact receipt;
  duplicate, unknown, mutated, fabricated, and evicted requests fail closed;
- failed mutation does not consume the rightful pending attestation;
- decreasing parseable timestamps reject before state mutation, including
  regressions separated by undated events;
- `unroutable` accepts only `delivery_id`/`disposition`/`reason`;
- constructor self/room/visibility facts validate before mutable state exists;
- the exact accepted attempt-6 corpus is pinned by framed SHA-256
  `1ce18c9e9fc3b5aa820adcb1aad649c635fcb2ed64a7e644d4d5bba6aeb5d91f`,
  and a one-byte mutation regression proves drift detection.

The timestamp correction exposed one invalid stress fixture whose seconds field
became non-clock data after 59. The fixture now generates real monotonic UTC
timestamps with `datetime + timedelta`; the 64/128 linear-replay probe remains
unchanged in meaning.

Phase 22 matrix:

| Command | Result |
|---|---|
| focused receipt/provider/corpus modules | 40 tests, OK |
| Observation discovery | 164 tests, OK |
| aggregate scenes | 52 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 8 equivalence) |
| Phase 18 adversarial evaluator | 11 rows, 0 FAIL |
| attempt-6 corpus conformance | 6 tests, 202/202 accounted for, exact digest GREEN |
| full repository suite | 1413 tests, OK; 4 optional-integration skips |
| verdict fixture discovery | 60 fixtures |
| expanded Ruff / production Bandit / governance / task manifest / `git diff --check` / absent generated reviewer checklist | clean |

T119 remains open for fresh independent review of the exact immutable object.
T103/T107/T112 are historical review gates superseded by T119, not acceptance
claims. Nothing here establishes `CONVERGED`, `HANDOFF_READY`, acceptance,
integration, deployment, release, promotion, or cutover authority.

## Phase 23 permanent request-ID uniqueness correction

Owner adversarial review rejected `d70f2fd006007a43a6303e66537327a48794e7ed`
before its in-flight independent reviews returned. With
`max_pending_receipts=1`, the recent-attestation LRU forgot `r1` after `r2`,
allowing valid receipt IDs `r1`, `r2`, `r1`. Pending overflow also returned a
new snapshot after evicting an older issued request, making the older request's
required observation receipt impossible.

Phase 23 supersedes the Phase 22 overflow wording:

- each provider owns a fixed 65,536-bit SHA-256 membership filter (8,192 bytes,
  four positions per ID); once an ID is issued, all its bits remain set for the
  provider lifetime, so it cannot be reissued after diagnostic LRU eviction;
- the filter has no false negatives; collisions/saturation can conservatively
  reject a fresh ID but can never admit a duplicate;
- when pending attestations reach their explicit cap, a new snapshot rejects
  before return; every already-issued pending request remains exactly
  attestable once;
- pending exact documents and recent attested IDs remain separately bounded.

Direct GREEN probe:

```text
{'reused_request_id': 'ObservationInputError',
 'pending_overflow_new': 'ObservationInputError',
 'older_receipt': 'old',
 'filter_bytes': 8192}
```

Phase 23 matrix:

| Command | Result |
|---|---|
| focused receipt/provider/corpus modules | 42 tests, OK |
| Observation discovery | 166 tests, OK |
| aggregate scenes | 52 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 8 equivalence) |
| Phase 18 adversarial evaluator | 11 rows, 0 FAIL |
| full repository suite | 1415 tests, OK; 4 optional-integration skips |
| verdict fixture discovery | 60 fixtures |
| expanded Ruff / production Bandit / governance / task manifest / `git diff --check` / absent generated reviewer checklist | clean |

T124 remains open for exact-object scan and fresh independent review. The
reviews already running against rejected `d70f2fd` are stale for approval and
may be used only as additional review input. Nothing here establishes
`CONVERGED`, `HANDOFF_READY`, acceptance, integration, deployment, release,
promotion, or cutover authority.

## Phase 24 caller-memory/resource/governance preparation receipt

Independent review rejected immutable candidate
`ff3c5a2e71bb05cdba644c3a95f5346ef82987bb`. The complete verdict is preserved
in `review-2026-07-19-ff3c5a2-rejection.md`. Phase 24 closes its current
caller-memory, early-resource, and governance-completion findings while retaining
the scanner correction and stale-candidate-matrix finding as explicit inputs.

Immutable preparation object:

- commit: `40bbb8c2d86237dfa200f8669fa536b5e263fb0f`;
- tree: `70a78aca94513b36b9c71b78cd57d14c3c29f80d`;
- parent/base for Phase 24: `80c1de2ed5941c1cc5d4e28ea3f13d84dc39b6d2`;
- pushed branch: `origin/v2/observation`, locally aligned and clean after push.

Phase 24 matrix:

| Command | Result |
|---|---|
| full repository suite | 1421 tests, OK; 4 optional-integration skips |
| Observation discovery | 170 tests, OK |
| governance suite | 66 tests, OK |
| aggregate scenes | 52 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 8 equivalence) |
| Phase 18/24 adversarial evaluator | 15 rows, 0 FAIL |
| attempt-6 corpus conformance | 6 tests, 202/202 accounted for, exact digest GREEN |
| verdict fixture discovery | 60 fixtures |
| Ruff / production Bandit / governance CLI / task manifest / docs / scanner regressions / `git diff --check` / absent generated reviewer checklist | clean |

Whole-slice committed-range scanner receipt:

```text
SLICE020_SECRET_SCAN CLEAN
base=fc60858a3810e2f53d9574cce1eb9589bd19b55b
head=40bbb8c2d86237dfa200f8669fa536b5e263fb0f
files=66 additions=9727 matchers=4
```

This append and the literal T106 completion check will create a small
receipt-only successor object. That exact successor must be rescanned and is the
only object eligible for the next independent whole-slice review. T131 remains
open until that review returns and every finding is adjudicated. Nothing here
establishes `CONVERGED`, `HANDOFF_READY`, acceptance, integration, deployment,
release, promotion, or cutover authority.

## Phase 25 continuation-authority, relation-gap, and timestamp correction

The late independent rejection of exact object
`80c1de2ed5941c1cc5d4e28ea3f13d84dc39b6d2` reported six HIGH mechanisms. Its
full report is preserved at
`evidence/v2/observation/review-2026-07-19-80c1de2-late-rejection.md`.
Current adjudication is:

1. caller-owned fetch TOCTOU — closed by Phase 24 private request/context copies;
2. caller-owned receipt TOCTOU — closed by Phase 24 exact private receipt copy;
3. shared governance completion misreporting — the attempted shared change was
   quarantined at `8f78ec5`; a slice-owned literal-state checker now reports
   checked, explicitly superseded, and open IDs without modifying that oracle;
4. expiry-presence comparator loss — closed by comparing
   `expires_at_present` while keeping exact clock values opaque;
5. parseable timestamp watermark erased by undated eviction — closed by one
   constant-size provider/continuity-lifetime monotonic watermark;
6. missing relation targets falsely gap-free — closed for unavailable and
   budget-excluded reply/thread/reaction targets with exact budget causes.

Separate Codex probes additionally found generated continuation-handle overwrite
and cross-wrapper capacity multiplication. Provider-owned shared continuation
state, identical wrapper-limit enforcement, collision retry, collision-exhaustion
rejection, and concurrent wrapper tests close those mechanisms. Codex's provider
blocked final report generation; its probes are review input, never approval.

Phase 25 RED included seven comparator/authority/gap failures and one timestamp-
eviction failure. Focused GREEN receipts include:

```text
Ran 31 tests in 0.020s — OK
SLICE020_TASK_STATE OK total=140 checked=132
superseded=T107,T112,T119,T124,T131 open=T103,T139,T140
```

Complete settled-tree matrix:

| Command | Result |
|---|---|
| Observation discovery | 182 tests, OK |
| aggregate scenes | 53 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 9 equivalence) |
| Phase 18/23/25 adversarial evaluator | 19 rows, 0 FAIL |
| attempt-6 corpus conformance | 6 tests, 202/202 accounted for, exact framed digest GREEN |
| executable docs | 13 tests, OK |
| full repository suite | 1431 tests, OK; 4 optional-integration skips |
| verdict fixture discovery | 60 fixtures |
| Ruff / production Bandit / scanner regressions / governance CLI / task manifest / slice-owned literal state / `git diff --check` / absent generated reviewer checklist | clean |

T139's complete matrix is settled; the immutable successor is exact-scanned
immediately after freeze. T103 and T140 remain open for the final exact-object
review and umbrella closure. No current statement claims
`CONVERGED`, `HANDOFF_READY`, acceptance, integration, deployment, release,
promotion, or cutover authority.

## Phase 27 authoritative packet correction

The historical append-only claim is false for this ordinary packet. Git replay
found four pre-recovery prefix rewrites, preserved without denial at
`evidence/v2/observation/handoff-history-integrity-incident-2026-07-19.md`.
The narrow lifecycle candidate/handoff streams remain the lifecycle authority.
Shared governance now enforces prefix-only extension of this file from exact
recovery baseline `a49313a5354259346e1089e759184b9f08735b37`; this section is
an append to that baseline, not another rewrite.

Independent governance review rejected exact Phase 26 object
`a49313a5354259346e1089e759184b9f08735b37` for three HIGH findings:

1. literal task completion was advisory and a false `CONVERGED` transition
   passed shared governance;
2. the claimed whole-range scanner omitted the slice-owned task checker and
   other changed control-plane paths;
3. this packet had been historically rewritten and ended at stale Phase 25
   gate T140 while the reviewed graph ended at T146.

The complete rejection is preserved at
`evidence/v2/observation/review-2026-07-19-a49313a-governance-rejection.md`.
Phase 27 closes those mechanisms by binding literal completion and exact T001–
T153 identity into shared lifecycle governance, distinguishing normalized graph
identity from completed IDs, truthfully closing prior review gates through T153
supersession, scanning every changed repository path in the committed range,
and enforcing append-only packet history from the recovery baseline.

Current downstream documentation routing remains unchanged and names the real
`v2-core-owner` for slice 030 plus `v2-wake-owner`, `v2-transport-owner`,
`v2-hermes-owner`, `v2-claude-owner`, `v2-codex-owner`, `v2-adapters-owner`,
`v2-security-owner`, and `v2-integrator` for their existing exact deltas.

### Phase 27 verification state

The RED reproductions and local correction receipts are recorded in
`evidence/v2/observation/convergence-phase27-governance-integrity-2026-07-19.md`.

| Command / control | Result |
|---|---|
| full repository | 1,452 tests, OK; 4 optional-integration skips |
| Observation discovery | 200 tests, OK |
| governance + scanner + literal-state group | 77 tests, OK |
| aggregate and adversarial evidence | 53 standard rows + 34 adversarial rows; 0 FAIL |
| attempt-6 corpus | 6 tests; 202/202 accounted for; exact framed digest GREEN |
| executable docs | 14 tests, OK |
| Ruff / expanded governance-script Bandit | clean; 0 findings |
| governance CLI | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| task graph | T001–T153; normalized SHA-256 `aa5d1bd80107457b7846117603d366a8dcfc83bf9418e38254753d7222386dbf` |
| literal task state | total 153; checked 151; superseded T107/T112/T119/T124/T131/T140/T146; open T103/T153 |
| verdict fixture inventory | 60 |
| final-tree `git diff --check` | clean |

T152 is complete. The immutable SHA/tree/parent and exact all-path
activation-range scan are bound externally immediately after freeze because a
Git object cannot contain its own identity or post-commit scanner receipt. T103
and T153 remain the only final review/umbrella gates. Nothing here establishes
`CONVERGED`, `HANDOFF_READY`, acceptance, integration, deployment, release,
promotion, or cutover authority.

## Phase 28 candidate-bound authority and selective lineage reconciliation (T154–T160)

**Date**: 2026-07-19
**Rejected source**: `abad8d85e8150bfd2716ab77ebb3791827591bf1`
**Parallel product source**: `3e38a70d634093a26ffbb6c460b9cf51fb81636b`
**Merge base**: `22a0a1ab9a996e82ec625ce73e301023889209e4`
**Current state**: `ACTIVE`; no candidate-attempt-2 or handoff authority

Two independent reviews rejected `abad8d85`; their combined exact findings are
preserved in `review-2026-07-19-abad8d85-dual-rejection.md`. Phase 28 closes the
reported task/candidate/supersession/rejection-history authority gaps while
preserving the disclosed historical `80c1de2` rewrite from recovery baseline
`abad8d85` rather than laundering it away.

`3e38a70` is not a descendant of the rejected governance lineage. Its
`HANDOFF_READY`, candidate-attempt-2, and handoff claims were therefore not
imported. Its exact Phase 25–27 review artifacts were preserved, and only the
validated product/evaluation mechanisms were carried: returned-event and
continuation relation-gap truth, normalized restart-gap truth, final mutated S13
page validation, deterministic relation priority, and matching tests/docs/eval
rows. The stronger private-issued receipt authority and permanent fixed-memory
handle non-reuse from the `abad8d85` lineage remain intact.

Pre-correction governance/task-state RED: 77 tests, 10 failures, 4 errors.
Selective-reconciliation RED: 28 tests, 10 failures, 2 errors. Both focused
commands are now GREEN. Final pre-freeze matrix after packet updates:

| Gate | Result |
|---|---|
| full repository | 1,467 tests, OK; 4 optional-integration skips |
| Observation discovery | 207 tests, OK |
| governance + literal task state | 80 tests, OK |
| static scanner | 6 tests, OK |
| aggregate evidence | 53 rows, 0 FAIL |
| adversarial evidence | 39 rows, 0 FAIL |
| corpus conformance | 6 tests; 202/202; exact framed digest GREEN |
| executable docs | 14 tests, OK |
| Ruff / expanded Bandit / governance CLI / diff check | clean |
| task graph | T001–T160; SHA-256 `7733ed9894f44a063db1a6dcad7c4c79f0d64256b2054c5041c92d3baff84d32` |
| literal task state | checked 157; open T103/T159/T160; eight historical review gates superseded |

T159 remains open until the final tree is reverified, frozen, pushed, and scanned
as an immutable object. T160 and T103 remain fresh exact-object review gates.
Nothing here establishes `CONVERGED`, `HANDOFF_READY`, acceptance, integration,
deployment, release, promotion, or cutover authority.

### Phase 28 moving-tree precommit rejection

The read-only working-tree review in
`review-2026-07-19-phase28-precommit-moving-tree-rejection.md` is preserved as a
rejection, not converted into approval. It found one novel authority defect:
supersession text could contain the required negative phrase while negating it
and asserting current approval. The exact attack is now a RED→GREEN regression;
shared policy rejects negated rejection language and positive approval
assertions. Its other stale-artifact/count findings were closed by regenerating
39 non-duplicate adversarial rows and rerunning the 1,467-test matrix. Because
the reviewed working tree moved, this verdict authorizes no lifecycle advance;
fresh review must target an immutable successor SHA.

### Phase 28 T159 preparation freeze and exact scan

**Preparation commit**: `901aaed47e8d7173df4a0a8788ed69e3cecdb44f`

**Tree**: `3c6599fec6c60d2f1e2b3f11afdfb6c767728804`

**Parent**: `6c3b89ef030cfa8bebdc5f206f899569e4e7c813`

The exact all-path scan from activation start
`fc60858a3810e2f53d9574cce1eb9589bd19b55b` through the preparation commit was
CLEAN across 90 changed files and 14,942 additions with all four matchers. T159
is closed in the metadata successor that binds this receipt. The successor's own
SHA, push, and post-commit scan are necessarily external receipts. T160 and T103
remain open; no candidate-attempt-2, handoff, acceptance, integration, release,
promotion, deployment, or cutover authority is established.

### Phase 28 second moving-tree rejection and T160 repair

The complete verdict is preserved at
`review-2026-07-19-phase28-second-precommit-moving-tree-rejection.md`; it grants
no approval. Its intermediate moving-tree/T159/diff observations were superseded
when `b427342571d4fbc8b86549dad6dfbe181d3a4608` was pushed, verified remote-exact,
and exact-scanned. Two newly demonstrated T160 blockers still applied to that
object: alternate CommonMark checkbox bullets bypassed the manifest parser, and
free-text rejection language admitted contradictory paraphrases. Both attacks
are now RED→GREEN regressions. The shared parser rejects every noncanonical
top-level `-`/`*`/`+` task-list row (including up to three leading spaces), and
each superseded gate requires exactly one structured
`Supersession disposition: REJECTED; authority: NONE.` line. T160 remains open
until a new immutable repair successor receives fresh exact-object reviews.
