# Slice 010 handoff evidence — documentation and packet inputs

This file records the T017 documentation dispositions and the T019 proposed
packet input. It is documentation/packet evidence for the workflow gates —
a different file from the lifecycle attempt stream `slice-handoff.md` — and
is append-only after first use: the packet section is appended after the
documentation section without rewriting it.

## Documentation dispositions (T017)

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Reviewed on**: 2026-07-17, in the implement step of bound run
`speckit-010-20260717T081350382670Z`

**Candidate diff basis**: `16cccb7..d01e5d2` plus this commit's
`docs/contracts/nunchi-v2.md` and evidence files. The ordinary-path diff
touches only `schemas/v2/`, `tests/v2/`, `evals/v2/contract/`,
`evidence/v2/contract/`, and the one new `docs/contracts/nunchi-v2.md`; no
file under `src/`, `scripts/`, `docs/governance/`, `docs/integrations/`,
`docs/evaluations/`, or the repository root documentation set is modified.
Verified with `git diff --name-only 16cccb7..HEAD`.

**Inventory**: per the plan's stated derivation, the reviewed set is
`README.md`, the root guidance documents, and every Markdown file under
`docs/**` except `docs/archive/` — 17 existing files plus the slice-created
`docs/contracts/nunchi-v2.md`, matching the plan matrix one-to-one. Every
row below names its exact reviewed path; there are no generic directory
rows.

### UPDATE (slice-owned)

| Reviewed path | Disposition | Result |
|---|---|---|
| `docs/contracts/nunchi-v2.md` | `UPDATE` (created) | Authored in this run. Validation: interface names/versions and exact schema paths match the five landed `schemas/v2/*.schema.json` files; ok/bypass/error separation, the closed four-pair transition matrix, FR-007 permanence, and the six FR-012 runtime-adapter-only semantic rules are documented as they are enforced by `tests/v2/contract/schema_helpers.py`; all four embedded JSON examples validate under both the pinned Draft 2020-12 oracle and the stdlib runtime adapter (validated 2026-07-17, 0 failures); all relative links resolve and none targets a SpecKit-managed path (`python3 scripts/check_governance.py`: OK). |

### HANDOFF (accepting owner: `v2-integrator`; applied only in the atomic candidate)

Each row routes its exact delta to `v2-integrator` for the atomic
current-state update. This slice does not present partial V2 as current;
the deltas below become true wording only at cutover.

| Reviewed path | Disposition | Exact routed delta |
|---|---|---|
| `README.md` | `HANDOFF` | Replace V1 verdict/request wording with the accepted I-010A–E and breaking-cutover wording, plus the exact pinned dual-validator test command (`uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`) and dev/test-only `jsonschema==4.26.0` dependency wording. |
| `CHANGELOG.md` | `HANDOFF` | Add the breaking-change entry naming I-010A–E `@1`, the five exact `schemas/v2/*.schema.json` paths, supersession of the V1 `PASS/ACK/ASK/SPEAK` request/verdict contract with no translation bridge, and the pinned dual-validator command. |
| `docs/STABILITY.md` | `HANDOFF` | Replace the V1 contract stability rows with the five `@1` interface versions and their breaking-cutover status; the classifier-DEFER/margin-DEFER transition stays described as independently evidence-gated, not schema compatibility. |
| `docs/integration.md` | `HANDOFF` | Replace V1 request/verdict flow wording with the request → decision (`ok`/`bypass`/`error`) → wake → continuation → receipt lifecycle, including the non-social `preattention-disabled` bypass and the tagged operational ERROR path. |
| `docs/adapters.md` | `HANDOFF` | Replace adapter-facing V1 envelope/verdict wording with I-010A request-construction and I-010E transport-stage receipt obligations, including honest unknown/unavailable capability wording. |
| `docs/contracts/channel-adapter-v1.md` | `HANDOFF` | Add the exact supersession notice naming I-010A–E `@1` and the atomic no-bridge cutover; the V1 body remains as a superseded historical reference. |
| `docs/architecture/v2-selected-design.md` | `HANDOFF` | Mark the five contract seams as landed at their exact `schemas/v2/` paths and align the request/decision/wake/receipt diagram labels with the `@1` interface names. |

### NO_IMPACT (re-verified against the exact candidate diff)

| Reviewed path | Disposition | Re-verification result |
|---|---|---|
| `docs/INSTALL.md` | `NO_IMPACT` | CONFIRMED — the candidate diff adds schemas, tests, evals, evidence, and one new doc only; no install flow or installed artifact changes; `jsonschema==4.26.0` appears only behind the pinned `uv run --offline --with` dev/test command and enters no runtime or install dependency (no `pyproject.toml`/packaging change in the diff). |
| `AGENTS.md` | `NO_IMPACT` | CONFIRMED — `python3 -m unittest` remains the green stdlib offline baseline at this tree (run 2026-07-17: 1208 tests, OK, 11 skipped — the 8 pre-existing V1 skips plus the 3 counted contract oracle-absence skips); the runtime stays dependency-free; its V2-program wording (V1 current until `CUTOVER_VERIFIED`) is unchanged by this additive diff. |
| `CLAUDE.md` | `NO_IMPACT` | CONFIRMED — the "standard-library runtime core" and `python3 -m unittest` claims stay accurate: the diff adds no runtime dependency and does not modify grounding sequence, governance commands, or workflow bindings. |
| `docs/contracts/verdict-suite-data-model-v1.md` | `NO_IMPACT` | CONFIRMED — no verdict-suite artifact changes in the diff; I-010B embeds the legacy `PASS`/`ACK`/`ASK`/`SPEAK` confidence-vector shape as transition evidence (FR-007) without touching the V1 verdict-suite data model. |
| `docs/contracts/verdict-suite-requirements-v1.md` | `NO_IMPACT` | CONFIRMED — same diff basis; no verdict-suite requirement file or claim changes. |
| `docs/evaluations/verdict-suite.md` | `NO_IMPACT` | CONFIRMED — the V1 corpus under `evals/verdict_suite/` is untouched by the diff; this slice adds `evals/v2/contract/` beside it; `python3 -m evals.verdict_suite.runner --list` still succeeds. |
| `docs/evaluations/verdict-suite-runner.md` | `NO_IMPACT` | CONFIRMED — the runner, its commands, and its outputs are untouched by the diff. |
| `docs/governance/execution-spine.md` | `NO_IMPACT` | CONFIRMED — the diff contains no change under `docs/governance/`, none to `scripts/check_governance.py` or its checks, and none to any documented governance command or gate. |
| `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | CONFIRMED — no Hermes surface file changes in the diff; the V2 migration delta for that surface is owned by the harness/adapter slices. |
| `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | CONFIRMED — same diff basis as the Hermes core patch row; no Hermes test-plan surface changes. |

**Result**: 1 `UPDATE` authored and validated; 7 `HANDOFF` deltas routed to
accepting owner `v2-integrator`; 10 `NO_IMPACT` rationales re-verified
CONFIRMED against the exact candidate diff. No row is unresolved.

## Proposed handoff packet input (T019)

Appended after the T017 documentation section without rewriting it. This
enumeration is authoritative for the SC-005 packet inventory; the later
convergence, documentation-freshness, and handoff gates — not the T019
checkbox — establish lifecycle state.

**Prepared by**: cc-session-1 (assigned `v2-contract-owner`), 2026-07-17,
in the implement step of bound run `speckit-010-20260717T081350382670Z`.

### Exact commit

`3ed8bb333a15d715237a9bc66468592e30886972` on branch `v2/contract`
(worktree `.worktrees/v2-contract/`). This tree contains all five schemas,
the contract test suite, the three corpora with authoritative per-class
counts, the aggregate evidence files, the scene manifest, and the
slice-owned contract documentation.

### Interface inventory (versions and exact paths)

| Interface | Version | Exact path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | `schemas/v2/attention-request.schema.json` |
| `I-010B AttentionDecisionV2` | `@1` | `schemas/v2/attention-decision.schema.json` |
| `I-010C ParticipantWakeV2` | `@1` | `schemas/v2/participant-wake.schema.json` |
| `I-010D ContextContinuationV2` | `@1` | `schemas/v2/context-continuation.schema.json` |
| `I-010E AttentionReceiptV2` | `@1` | `schemas/v2/attention-receipt.schema.json` |

Only `v2-contract-owner` edits `schemas/v2/**`; breaking edits land as
`@2` through an explicit owner handoff plus dependent re-analysis.

### Commands and results (2026-07-17, at the exact commit)

| Command | Result |
|---|---|
| `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'` | 151 tests, OK, 0 skipped (the sole complete dual-validator run) |
| `python3 -m unittest` (repository baseline, full suite) | 1208 tests, OK, 11 skipped (8 pre-existing V1 + 3 counted `baseline-oracle-absence`) |
| `python3 scripts/check_governance.py` (boundary-only, SC-006) | `governance boundary: OK (SpecKit 0.12.11)` |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence` | 72 + 94 + 122 records, 0 mismatched |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence` | all records carry the five mandatory fields |

### Dual-validator pin and results over the shared corpus

The Draft 2020-12 oracle is dev/test-only `jsonschema==4.26.0` (any other
version is treated as an absent oracle); the runtime side is the explicit
stdlib adapter in `tests/v2/contract/schema_helpers.py`. Both validators
consumed the identical decoded corpus (144 cases; 118 schema-expressible
with identical expected results from both validators, 26
runtime-adapter-only across the six semantic/relational classes with the
fixed per-class oracle treatment). Observed per-class partition counts and
both separately named skip regimes (`oracle-class-skip`: 16 cases;
`baseline-oracle-absence`: 128 oracle-side checks) are recorded in
`evidence/v2/contract/README.md` and match every corpus's authoritative
`expected-counts.json`.

### Corpus revision and downstream adapter obligation

The shared conformance corpus revision is the exact commit above
(`3ed8bb333a15d715237a9bc66468592e30886972`), covering
`evals/v2/contract/attention-request/`,
`evals/v2/contract/attention-decision/`, and
`evals/v2/contract/downstream/` (each `cases.jsonl` plus
`expected-counts.json`). **Obligation**: each downstream runtime owner
must pass its own stdlib runtime-validation adapter over this identical
corpus revision — including the six runtime-adapter-only semantic rule
classes — before its own handoff.

### Staged-receipt writer map

| Stage | Sole appending owner |
|---|---|
| `observation` | `observation-provider` |
| `attention` | `attention-engine` |
| `participant-host` | `participant-host` |
| `transport` | `transport` |

Stages are immutable and append-only in canonical order; a prefix-partial
receipt is valid-in-progress; no writer mutates a prior record or fills
another owner's stage.

### Scene-to-record evidence manifest

`evidence/v2/contract/README.md` maps all twelve scene rows (S01, S02,
S03, S05, S06, S07, S08, S09, S15, S16, 010-Preattention-bypass, 010-V1)
to their JSONL files and record IDs, verified exhaustive and exact against
the 144 evidence cases.

### Rejected-case inventory

99 of the 144 corpus cases are expected-invalid red cases, every one
enumerated in its corpus `cases.jsonl` and present in the evidence files
and manifest: attention-request 26 (23 schema-expressible; 1 each
id-uniqueness, timestamp-order, trigger-membership), attention-decision 36
(35 schema-expressible; 1 advice-citation), downstream 37 (27
schema-expressible; 1 id-uniqueness; 4 binding-expiry; 5
receipt-sequence). They cover invalid identity, reference, order,
coverage, budget, transition, bypass-contamination, confidence,
host-secret leakage, binding/expiry, receipt-stage sequence, reply-field,
social-ledger, and V1-envelope cases; 100% reject (SC-001, 0 mismatches).

### Migration and provenance notes

- No V1 translation bridge exists or is permitted (FR-011): V1 envelopes,
  reply-bearing fields, inferred-roster claims, and
  handled/open/owed/permission state reject in every contract.
- V1 remains the current product until the atomic V2 merge is verified on
  `main`; these contracts create no V2 runtime behavior.
- `legacy_confidence` embeds the legacy `PASS`/`ACK`/`ASK`/`SPEAK` verdict
  vocabulary as transition evidence only; it is required on every
  `status: ok` decision for all of `@1`, and margin retirement remains
  independently evidence-gated.
- Provenance: implemented under program authority
  `evidence/governance/v2-implementation-authorization.md` (all eleven
  slices enumerated), activation
  `evidence/v2/contract/slice-activation.md` (`READY` at `16cccb7`),
  assignment `evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md`,
  within bound runs `speckit-010-20260717T003300631902Z` (analysis/
  readiness) and `speckit-010-20260717T081350382670Z` (delivery).
- Runtime provenance: Python 3.11+ stdlib-only runtime; `jsonschema==4.26.0`
  is dev/test-only behind the pinned offline command and never enters
  runtime dependencies.

### Documentation dispositions, validation, and reviewer

Recorded in full as the first section of this file (T017): 1 slice-owned
`UPDATE` authored and validated (`docs/contracts/nunchi-v2.md`), 7
`HANDOFF` deltas routed to accepting owner `v2-integrator`, 10 `NO_IMPACT`
rationales re-verified CONFIRMED against the exact candidate diff;
reviewer cc-session-1.

### Known limitations

- A green contract suite proves contract mechanics, not social judgment
  quality; social correctness claims require the downstream slices' replay
  and live acceptance scenes.
- The Draft 2020-12 oracle cannot express the six semantic/relational rule
  classes; they bind only through each consumer's stdlib adapter, so the
  downstream adapter obligation above is load-bearing, not advisory.
- Strict JSON cannot carry non-finite literals: corpus red cases use the
  reserved sentinel strings decoded once by the loader. An in-process
  non-finite float constructed by a consumer never appears on the wire, so
  runtime adapters must enforce the finite `[0, 1]` confidence rule
  themselves (the schema's contradictory-bounds clause covers only decoded
  instances).
- The pinned offline command requires `jsonschema==4.26.0` already present
  in the operator's uv cache; `--offline` fails rather than fetching.
- The umbrella parity scenes S04 and S10 through S14 are owned by other
  slices (see the plan's scene-ownership note); this packet claims no
  coverage of them.
- The seven `HANDOFF` documentation deltas apply only in the atomic
  candidate; until cutover the affected documents intentionally retain
  their V1 current-state wording.

## Documentation dispositions — attempt 2 (T032)

Appended after the attempt-1 sections without rewriting them (CHK089).
This section re-executes every row of plan §Documentation Impact and
Freshness against the attempt-2 candidate diff (CHK092).

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Reviewed on**: 2026-07-17, in the implement step of bound run
`speckit-010-20260717T163451669036Z`

**Candidate diff basis**: the rework delta
`81483ce017eb834c5ab533556fa64cd62a8cf2aa..` this candidate (the rejected
attempt-1 candidate to the attempt-2 tree). Verified with
`git diff --name-only 81483ce...`: the ordinary-path delta touches only
`schemas/v2/attention-decision.schema.json`,
`schemas/v2/attention-receipt.schema.json`, `tests/v2/contract/`,
`tests/test_governance.py` (the owned R1 repair; plan §Integration
Strategy), `evals/v2/contract/attention-decision/`,
`evals/v2/contract/downstream/`, `evidence/v2/contract/`, and
`docs/contracts/nunchi-v2.md`, plus the slice's own SpecKit planning
artifacts. No file under `src/`, `scripts/`, `docs/governance/`,
`docs/integrations/`, `docs/evaluations/`, or the repository root
documentation set is modified.

### UPDATE (slice-owned), re-validated (CHK094)

| Reviewed path | Disposition | Result |
|---|---|---|
| `docs/contracts/nunchi-v2.md` | `UPDATE` (re-validated) | Reworked to the clarified shapes: the conditional FR-007 vector rule (optional on ok; required exactly for a margin-active candidate `SUPPRESS`; presence never invalidates; `@1` permanence restated for the conditional rule), the closed FR-005 routing-audit set with its cross-field rules (applied valve, override cause, margin status, effective margin exactly when the margin applied, trusted margin source only on a margin-applied decision), the required sibling `reasons` placement, and the per-record FR-010 stage-to-writer binding (forged single documents invalid in both validators, stream-level rules retained in addition) — alongside the five `@1` interfaces and the FR-012 runtime-adapter-only rules. All five embedded JSON examples (request, governed suppression, margin-widened deferral, bypass, silence receipt) validate under both the pinned Draft 2020-12 oracle and the stdlib runtime adapter (validated 2026-07-17, 0 failures); all relative links resolve and none targets a SpecKit-managed path. |

### HANDOFF (accepting owner: `v2-integrator`), re-routed

All seven attempt-1 `HANDOFF` rows re-verified and re-routed unchanged in
scope — `README.md`, `CHANGELOG.md`, `docs/STABILITY.md`,
`docs/integration.md`, `docs/adapters.md`,
`docs/contracts/channel-adapter-v1.md`,
`docs/architecture/v2-selected-design.md` — each still routing its exact
delta to `v2-integrator` for the atomic current-state update only. The
routed deltas now reference the clarified I-010B shape (conditional
FR-007 vector, closed valve-based routing audit) and the per-record
I-010E stage-to-writer binding wherever the attempt-1 delta named the
superseded shapes; the accepting owner and atomic-candidate-only
application are unchanged.

### NO_IMPACT, re-verified against the attempt-2 diff (CHK093 sequencing)

Re-verification is sequenced after the R1 repair (T026, landed at
`b3cbb8f`) within this same candidate, so the baseline-health claims are
checked against a tree where they are true.

| Reviewed path | Disposition | Re-verification result |
|---|---|---|
| `docs/INSTALL.md` | `NO_IMPACT` | CONFIRMED — the rework diff changes no install flow or installed artifact; `jsonschema==4.26.0` still appears only behind the pinned `uv run --offline --with` dev/test command (no packaging change in the diff). |
| `AGENTS.md` | `NO_IMPACT` | CONFIRMED — after the T026 repair, `python3 -m unittest` is the green stdlib offline baseline at this tree (run 2026-07-17, post-repair: 1225 tests, OK, 11 skipped — 8 pre-existing V1 plus 3 counted contract oracle-absence skips), and the fixture-independence regression proof keeps the claim true regardless of live slice state; the runtime stays dependency-free; the V2-program wording (V1 current until `CUTOVER_VERIFIED`) is unchanged. |
| `CLAUDE.md` | `NO_IMPACT` | CONFIRMED — the "standard-library runtime core" and `python3 -m unittest` claims stay accurate: the rework adds no runtime dependency and does not modify grounding sequence, governance commands, or workflow bindings. |
| `docs/contracts/verdict-suite-data-model-v1.md` | `NO_IMPACT` | CONFIRMED — no verdict-suite artifact changes in the diff; I-010B embeds the legacy `PASS`/`ACK`/`ASK`/`SPEAK` confidence-vector shape as optional, conditionally required transition evidence (FR-007 as clarified) without changing any verdict-suite artifact or claim. |
| `docs/contracts/verdict-suite-requirements-v1.md` | `NO_IMPACT` | CONFIRMED — same diff basis; no verdict-suite requirement file or claim changes. |
| `docs/evaluations/verdict-suite.md` | `NO_IMPACT` | CONFIRMED — the V1 corpus under `evals/verdict_suite/` is untouched by the rework diff; `python3 -m evals.verdict_suite.runner --list` still succeeds (60 fixtures discovered, 2026-07-17). |
| `docs/evaluations/verdict-suite-runner.md` | `NO_IMPACT` | CONFIRMED — the runner, its commands, and its outputs are untouched by the diff. |
| `docs/governance/execution-spine.md` | `NO_IMPACT` | CONFIRMED — the rework diff contains no change under `docs/governance/`, none to `scripts/check_governance.py` or its checks, and none to any documented governance command or gate; the R1 repair touches only the `tests/test_governance.py` fixture's synthetic baseline construction, which this doc does not document. |
| `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | CONFIRMED — no Hermes surface file changes in the rework diff. |
| `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | CONFIRMED — same diff basis as the Hermes core patch row. |

**Result (attempt 2)**: 1 `UPDATE` re-validated against the clarified
shapes; 7 `HANDOFF` deltas re-routed to accepting owner `v2-integrator`;
10 `NO_IMPACT` rationales re-verified CONFIRMED against the attempt-2
diff, with the baseline-health rows sequenced after the R1 repair. No row
is unresolved.

## Documentation dispositions — attempt 3 (T043)

Appended after the attempt-1 and attempt-2 sections without rewriting them
(CHK089, generalized by T035's CHK107 fix). This section re-executes every
row of plan §Documentation Impact and Freshness against the attempt-3
candidate diff (CHK108), re-scans every `HANDOFF` delta for a superseded
local field name or narrowed-shape claim (CHK109), and re-runs the
inventory-derivation check against this diff (CHK120).

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Reviewed on**: 2026-07-18, directly in the `v2-contract-owner` worktree
(not via a bound `run speckit` invocation).

**Inventory-derivation re-check (CHK120)**: `ls *.md` plus
`find docs -name '*.md' | grep -v archive` against the attempt-3 tree
yields the identical 18 files (4 root + 14 `docs/**`) as the attempt-2
inventory — no doc file was added or removed outside the eighteen
already-listed rows.

**Candidate diff basis**: `git diff --name-only
5383e9f3a5e9c20c08ab54395f4ff370128f03de..` (the rejected attempt-2 packet
commit to the attempt-3 tree). The ordinary-path delta touches only all
five `schemas/v2/*.schema.json` files, `tests/v2/contract/` (the stdlib
adapter and all four test files), `evals/v2/contract/{attention-request,
attention-decision,downstream}/`, `evidence/v2/contract/`, and
`docs/contracts/nunchi-v2.md`, plus the slice's own SpecKit planning
artifacts. No file under `src/`, `scripts/`, `docs/governance/`,
`docs/integrations/`, `docs/evaluations/`, or the repository root
documentation set is modified.

### UPDATE (slice-owned), re-validated (CHK108)

| Reviewed path | Disposition | Result |
|---|---|---|
| `docs/contracts/nunchi-v2.md` | `UPDATE` (re-validated) | Fully reworked to the R4 selected-design fidelity shapes: `schema_version: 2` replacing the invented `interface`/`version` envelope; the actor map; the typed message/reaction/membership event union; the full coverage field inventory; the representable (not forbidden) `continuation` capability with the classifier-facing redaction moved to runtime (FR-004 correction); `routing_audit`/`classifier`/`legacy_verdict_confidences`/`attention_advice` naming; the materialized wake packet; the bare `ContextFetch`/`ContextPage` shapes; and the reworked four-stage receipt telemetry (`schema_version` on observation, flattened bypass fields, `sent`/`silent`/`unknown` outcomes) — alongside the FR-012 authority-conformance corpus class and runtime-adapter-only rules. All five embedded JSON examples (the design's verbatim example request, governed suppression, margin-widened deferral, bypass, silence receipt) validate under both the pinned Draft 2020-12 oracle and the stdlib runtime adapter (validated 2026-07-18, 0 failures); all relative links resolve and none targets a SpecKit-managed path. |

### HANDOFF (accepting owner: `v2-integrator`), re-routed, re-scanned for superseded names (CHK109)

All seven attempt-1/attempt-2 `HANDOFF` rows re-verified and re-routed
unchanged in scope — `README.md`, `CHANGELOG.md`, `docs/STABILITY.md`,
`docs/integration.md`, `docs/adapters.md`,
`docs/contracts/channel-adapter-v1.md`,
`docs/architecture/v2-selected-design.md` — each still routing its exact
delta to `v2-integrator` for the atomic current-state update only. Each
row's delta text was scanned against the R4 field renames
(`routing`→`routing_audit`, `classifier_audit`→`classifier`,
`legacy_confidence`→`legacy_verdict_confidences`,
`advice`→`attention_advice`, dropped `interface`/`version` envelope): none
of the seven rows names a local field at that level of detail (they
reference interface IDs, versions, `schemas/v2/*.schema.json` paths,
statuses, and commands only), so none embeds a superseded name or
narrowed-shape claim; no row text requires editing. The accepting owner
and atomic-candidate-only application are unchanged.

### NO_IMPACT, re-verified against the attempt-3 diff

| Reviewed path | Disposition | Re-verification result |
|---|---|---|
| `docs/INSTALL.md` | `NO_IMPACT` | CONFIRMED — the R4 rework diff changes no install flow or installed artifact; `jsonschema==4.26.0` still appears only behind the pinned `uv run --offline --with` dev/test command. |
| `AGENTS.md` | `NO_IMPACT` | CONFIRMED — `python3 -m unittest` is the green stdlib offline baseline at this tree (run 2026-07-18, post-rework: 1222 tests, OK, 11 skipped — 8 pre-existing V1 plus 3 counted contract oracle-absence skips; the 1225→1222 delta is three deliberate test consolidations for fields removed by the primary-source correction, not a coverage loss); the runtime stays dependency-free; the V2-program wording (V1 current until `CUTOVER_VERIFIED`) is unchanged. |
| `CLAUDE.md` | `NO_IMPACT` | CONFIRMED — the "standard-library runtime core" and `python3 -m unittest` claims stay accurate: the rework adds no runtime dependency and does not modify grounding sequence, governance commands, or workflow bindings. |
| `docs/contracts/verdict-suite-data-model-v1.md` | `NO_IMPACT` | CONFIRMED — no verdict-suite artifact changes in the diff; I-010B's `legacy_verdict_confidences` still embeds the identical `PASS`/`ACK`/`ASK`/`SPEAK` four-key vocabulary as optional, conditionally required transition evidence (FR-007) — only the wrapping field name changed, not the verdict-suite claim. |
| `docs/contracts/verdict-suite-requirements-v1.md` | `NO_IMPACT` | CONFIRMED — same diff basis; no verdict-suite requirement file or claim changes. |
| `docs/evaluations/verdict-suite.md` | `NO_IMPACT` | CONFIRMED — the V1 corpus under `evals/verdict_suite/` is untouched by the rework diff. |
| `docs/evaluations/verdict-suite-runner.md` | `NO_IMPACT` | CONFIRMED — the runner, its commands, and its outputs are untouched by the diff. |
| `docs/governance/execution-spine.md` | `NO_IMPACT` | CONFIRMED — the rework diff contains no change under `docs/governance/`, none to `scripts/check_governance.py` or its checks, and none to any documented governance command or gate. |
| `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | CONFIRMED — no Hermes surface file changes in the rework diff. |
| `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | CONFIRMED — same diff basis as the Hermes core patch row. |

**Result (attempt 3)**: 1 `UPDATE` fully reworked to the R4 field
inventory; 7 `HANDOFF` deltas re-routed and re-scanned for superseded
names (none found); 10 `NO_IMPACT` rationales re-verified CONFIRMED
against the attempt-3 diff; inventory-derivation re-checked (18/18, no
drift). No row is unresolved.

## Proposed handoff packet input — attempt 3 (T045)

Appended after the attempt-3 documentation section, in the same
documentation-then-packet order as prior attempts, without rewriting any
earlier section. T019's enumeration remains authoritative for the SC-005
packet inventory; the later convergence, documentation-freshness, and
handoff gates — not the T045 checkbox — establish lifecycle state.
Verifying the task graph's referential execution-status wording (rejection
R6): the tasks.md header states status by reference to the `Slice state`
declaration and lifecycle evidence, never as a hard-coded claim, and
agrees with the slice declarations at this packet commit.

**Prepared by**: cc-session-1 (assigned `v2-contract-owner`), 2026-07-18,
directly in the `v2-contract-owner` worktree.

### The two defined commits (CHK090)

Per spec SC-005, the packet distinguishes two terms, each independently
carrying the green full-offline-baseline (`python3 -m unittest`)
obligation. Both terms name the identical exact commit throughout this
packet, the lifecycle candidate entry, and the recorded corpus revision
(rejection R5):

- **Candidate commit**: `7f9e81460d570e078c4bcbacb138f81c1b291455` on branch `v2/contract`
  (worktree `.worktrees/v2-contract/`) — the exact rework-complete code
  tree: all five schemas at their selected-design-fidelity shapes, the
  reworked stdlib adapter and contract test suite, the three corpora with
  authoritative per-class counts including the FR-014 authority-conformance
  class, the regenerated aggregate evidence and manifest, the completed
  CHK097–CHK121 adjudication, and the reworked slice-owned contract
  documentation. The full offline baseline recorded in
  `evidence/v2/contract/README.md` (1222 tests, OK, 11 skipped) is the run
  this commit must — and does — reproduce.
- **Handoff packet commit**: not yet pinned; recorded here in the same
  terms once it exists, per the T035-landed CHK105 operational rule
  (`evidence/v2/contract/handoff.md` records it — this file — at the
  handoff gate, since the packet commit cannot name itself from inside its
  own tree). The full offline baseline is owed as a rerun from that exact
  commit at the handoff gate (the R1 rejection basis; not discharged here).

### Interface inventory (versions and exact paths)

| Interface | Version | Exact path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | `schemas/v2/attention-request.schema.json` |
| `I-010B AttentionDecisionV2` | `@1` | `schemas/v2/attention-decision.schema.json` |
| `I-010C ParticipantWakeV2` | `@1` | `schemas/v2/participant-wake.schema.json` |
| `I-010D ContextContinuationV2` | `@1` | `schemas/v2/context-continuation.schema.json` |
| `I-010E AttentionReceiptV2` | `@1` | `schemas/v2/attention-receipt.schema.json` |

Only `v2-contract-owner` edits `schemas/v2/**`; breaking edits land as
`@2` through an explicit owner handoff plus dependent re-analysis. The
`@1` shapes are now the R4 selected-design-fidelity ones: `schema_version:
2` (not a local `interface`/`version` tag pair) on the request; the actor
map; the typed event union; the full coverage inventory; `routing_audit`/
`classifier`/`legacy_verdict_confidences`/`attention_advice` naming on the
decision; the materialized wake packet; the bare fetch-request/fetch-page
shapes; and the reworked four-stage receipt telemetry.

### Commands and results (2026-07-18, at the candidate commit's tree)

| Command | Result |
|---|---|
| `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'` | 164 tests, OK, 0 skipped (the sole complete dual-validator run) |
| `python3 -m unittest` (repository baseline, full suite) | 1222 tests, OK, 11 skipped (8 pre-existing V1 + 3 counted `baseline-oracle-absence`) |
| `python3 scripts/check_governance.py` (boundary-only, SC-006) | `governance boundary: OK (SpecKit 0.12.11)` |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence` | 80 + 130 + 134 records, 0 mismatched |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence` | all records carry the five mandatory fields |

### Dual-validator pin and post-rework results over the shared corpus

The Draft 2020-12 oracle is dev/test-only `jsonschema==4.26.0` (any other
version is treated as an absent oracle); the runtime side is the explicit
stdlib adapter in `tests/v2/contract/schema_helpers.py`. Both validators
consumed the identical decoded post-rework corpus (172 cases; 147
schema-expressible with identical expected results from both validators —
including 14 FR-014 authority-conformance cases and the reclassified
per-record cross-owner receipt case — and 25 runtime-adapter-only across
the six semantic/relational classes with the fixed per-class oracle
treatment). Observed per-class partition counts, the authority-class table
with its `authority_source_commit`/`red_run_failing_count` fields, and both
separately named skip regimes (`oracle-class-skip`: 15 cases;
`baseline-oracle-absence`: 157 oracle-side checks) are recorded in
`evidence/v2/contract/README.md` and match every corpus's authoritative
`expected-counts.json`.

### Corpus revision and downstream adapter obligation

The shared conformance corpus revision is the exact candidate commit above
(`7f9e81460d570e078c4bcbacb138f81c1b291455`), covering `evals/v2/contract/attention-request/` (re-recorded
this attempt — R4 re-enters every corpus family, so the attempt-2
unchanged disposition does not carry forward — 40 cases including 4
authority cases), `evals/v2/contract/attention-decision/` (reworked to the
selected naming, 65 cases including 4 authority cases), and
`evals/v2/contract/downstream/` (reworked, 67 cases including 6 authority
cases) — each `cases.jsonl` plus `expected-counts.json`. **Obligation
(unchanged)**: each downstream runtime owner must pass its own stdlib
runtime-validation adapter over this identical corpus revision — including
the six runtime-adapter-only semantic rule classes — before its own
handoff.

### Staged-receipt writer map (unchanged)

| Stage | Sole appending owner |
|---|---|
| `observation` | `observation-provider` |
| `attention` | `attention-engine` |
| `participant-host` | `participant-host` |
| `transport` | `transport` |

This closed map remains part of the public per-record contract (spec
FR-010): it is encoded in `schemas/v2/attention-receipt.schema.json` and
the individual stdlib validator, so a record attributing one stage to
another stage's owner is invalid as a single document in both validators.
Stages remain immutable and append-only in canonical order; a
prefix-partial receipt is valid-in-progress; the stream-level
canonical-order, skipped-stage, earlier-stage-mutation,
request-ID-correlation, and writer-ownership checks remain in the
runtime-adapter-only receipt-stage sequence class in addition.

### Scene-to-record evidence manifest (regenerated)

`evidence/v2/contract/README.md` (regenerated by T042 as the
current-attempt record) maps all twelve scene rows (S01, S02, S03, S05,
S06, S07, S08, S09, S15, S16, 010-Preattention-bypass, 010-V1) to their
JSONL files and record IDs, verified exhaustive and exact against the 172
post-rework evidence cases, names the authority-conformance class with its
`authority_source_commit`/`red_run_failing_count` fields, and names the
re-recorded disposition for every one of the three aggregate files
(unlike attempt 2, `attention-request.jsonl` is not unchanged this
attempt).

### Rejected-case inventory (updated)

108 of the 172 corpus cases are expected-invalid red cases, every one
enumerated in its corpus `cases.jsonl` and present in the evidence files
and manifest: attention-request 26 (23 schema-expressible; 1 each
id-uniqueness, timestamp-order, trigger-membership), attention-decision
45 (44 schema-expressible, including the conditional-FR-007 and
routing-audit cross-field reds; 1 advice-citation), downstream 37 (28
schema-expressible, including the reclassified per-record cross-owner
receipt case DWN-S06-306; 1 id-uniqueness; 3 binding-expiry — reduced from
4 because the fetch-request "changed binding" field no longer exists under
the selected design, CHK107 disposition; 5 receipt-sequence). They cover
invalid identity, reference, order, coverage, budget, transition,
routing-audit cross-field, conditional-confidence, bypass-contamination,
host-secret leakage, binding/expiry, receipt-stage sequence, per-record
cross-owner attestation, reply-field, social-ledger, and V1-envelope
cases; 100% reject (SC-001, 0 mismatches).

### Migration and provenance notes (CHK091)

- This is the attempt-3 packet following the rejection of candidate
  `001fdf85acd5098264c4975559c97114aa7278af` at packet commit
  `5383e9f3a5e9c20c08ab54395f4ff370128f03de`, recorded at
  `evidence/v2/contract/review-2026-07-17-v2-integrator-attempt-2.md` and
  bound into the appended `REJECTED` attempt in
  `evidence/v2/contract/slice-handoff.md`. Its three blockers are resolved
  in this candidate: **R4** — all five schemas, the stdlib adapter, and
  the corpus were reworked to the selected design's field-level naming and
  shape inventory; going beyond FR-014's own text summary to read the
  pinned design directly (`projects/shared/nunchi/technical-design.md` at
  `c834e8c` in the `aleph-vault` repository) surfaced an envelope-level
  defect (invented `interface`/`version` tags in place of the design's own
  `schema_version: 2`) that neither the attempt-1 nor attempt-2 integrator
  review had caught; **R5** — this packet names the identical exact
  candidate commit at every required statement (see "The two defined
  commits" above); **R6** — the task graph's Execution status header
  states status by reference, verified above.
- No V1 translation bridge exists or is permitted (FR-011): V1 envelopes,
  reply-bearing fields, inferred-roster claims, and
  handled/open/owed/permission state reject in every contract.
- V1 remains the current product until the atomic V2 merge is verified on
  `main`; these contracts create no V2 runtime behavior.
- `legacy_verdict_confidences` embeds the legacy `PASS`/`ACK`/`ASK`/`SPEAK`
  verdict vocabulary as transition evidence only; it is optional on
  `status: ok` and required exactly for a margin-active candidate
  `SUPPRESS` (FR-007); the optional field, its exact shape, and the
  conditional requirement are fixed for `@1`, and margin retirement
  remains independently evidence-gated.
- Provenance: implemented under program authority
  `evidence/governance/v2-implementation-authorization.md` (all eleven
  slices enumerated), activation
  `evidence/v2/contract/slice-activation.md` (`READY` at `16cccb7`),
  assignment `evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md`.
  This attempt was completed directly in the owner worktree rather than
  through a bound `run speckit` invocation: three consecutive bound-run
  attempts failed on workflow-machinery defects unrelated to this rework's
  substance (a governance lexical-token violation in the Phase 8 task-text
  append, then twice a nested-integration write-permission fault); Zoe
  directed completing the rework directly and handing off the result.
- Runtime provenance: Python 3.11+ stdlib-only runtime;
  `jsonschema==4.26.0` is dev/test-only behind the pinned offline command
  and never enters runtime dependencies.

### Documentation dispositions, validation, and reviewer

Recorded in full as the attempt-3 documentation section above (T043): 1
slice-owned `UPDATE` fully reworked to the R4 shapes
(`docs/contracts/nunchi-v2.md`), 7 `HANDOFF` deltas re-routed to accepting
owner `v2-integrator` and re-scanned for superseded field names (none
found), 10 `NO_IMPACT` rationales re-verified CONFIRMED against the
attempt-3 diff, and the inventory-derivation check re-run with no drift
(18/18); reviewer cc-session-1.

### Known limitations

- A green contract suite proves contract mechanics, not social judgment
  quality; social correctness claims require the downstream slices'
  replay and live acceptance scenes.
- The Draft 2020-12 oracle cannot express the six semantic/relational
  rule classes; they bind only through each consumer's stdlib adapter, so
  the downstream adapter obligation above is load-bearing, not advisory.
- With the per-record stage-to-writer binding schema-expressible, the
  stream-level writer-ownership check in `validate_receipt_stream` is
  reached only through its per-record validation of each stream record;
  the stream-level check is retained as defense-in-depth and the corpus
  keeps a red stream case (`DWN-S06-309`) covering it.
- Strict JSON cannot carry non-finite literals: corpus red cases use the
  reserved sentinel strings decoded once by the loader. An in-process
  non-finite float constructed by a consumer never appears on the wire,
  so runtime adapters must enforce the finite confidence and
  effective-margin rules themselves.
- The pinned offline command requires `jsonschema==4.26.0` already
  present in the operator's uv cache; `--offline` fails rather than
  fetching; running it generates an untracked `uv.lock` at the repo root
  (delete to restore a clean tree).
- Schema `$id` values use the placeholder domain `nunchi.invalid` pending
  any future canonical-host decision (identifiers only, never
  dereferenced).
- The umbrella parity scenes S04 and S10 through S14 are owned by other
  slices (see the plan's scene-ownership note); this packet claims no
  coverage of them.
- The seven `HANDOFF` documentation deltas apply only in the atomic
  candidate; until cutover the affected documents intentionally retain
  their V1 current-state wording.
- The handoff-packet-commit baseline rerun is owed at the handoff gate
  and cannot be discharged by this packet input (CHK080/CHK090).
- The fetch-request "changed binding" check present in attempt 2 was
  removed this attempt: `ContextFetch` carries no inline binding fields
  under the selected design, so there is no field to cross-check against
  a separately recorded binding; a known, unexpired `handle_id` is by
  construction the correct binding. This narrows `binding-expiry`'s
  invalid coverage from 4 to 3 cases (CHK107 disposition), not a silent
  shrink — the removed scenario is no longer representable.
- The classifier-facing host-secret redaction for `I-010A`'s optional
  `continuation` field is enforced at the runtime layer that constructs
  the model-facing projection, not by the wire schema (FR-004, corrected
  this attempt); a runtime adapter that skips this redaction step would
  leak host secrets to the classifier without the schema catching it.

## Proposed handoff packet input — attempt 2 (T034)

Appended after the attempt-2 documentation section, in the same
documentation-then-packet order as T017→T019, without rewriting any
earlier section. T019's enumeration remains authoritative for the SC-005
packet inventory; the later convergence, documentation-freshness, and
handoff gates — not the T034 checkbox — establish lifecycle state.

**Prepared by**: cc-session-1 (assigned `v2-contract-owner`), 2026-07-17,
in the implement step of bound run `speckit-010-20260717T163451669036Z`.

### The two defined commits (CHK090)

Per spec SC-005, the packet distinguishes two terms, each independently
carrying the green full-offline-baseline (`python3 -m unittest`)
obligation:

- **Candidate commit**:
  `2ab95be81e193d01b91ff078decfc586cf4bf357` on branch `v2/contract`
  (worktree `.worktrees/v2-contract/`) — the exact rework-complete code
  tree: all five schemas at their clarified shapes, the contract test
  suite, the three corpora with authoritative per-class counts, the
  regenerated aggregate evidence and manifest, the completed
  CHK077–CHK096 adjudication, and the slice-owned contract
  documentation. The full offline baseline recorded in
  `evidence/v2/contract/README.md` (1225 tests, OK, 11 skipped) is the
  run this commit must — and does — reproduce.
- **Handoff packet commit**: the exact commit at which this completed
  packet evidence is delivered, pinned when the handoff gate appends the
  attempt-2 `HANDOFF_READY` record to
  `evidence/v2/contract/slice-handoff.md`. The full offline baseline is
  rerun green from that exact commit at the handoff gate (the R1
  rejection basis; this obligation is owed there, not discharged here).

### Interface inventory (versions and exact paths)

| Interface | Version | Exact path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | `schemas/v2/attention-request.schema.json` |
| `I-010B AttentionDecisionV2` | `@1` | `schemas/v2/attention-decision.schema.json` |
| `I-010C ParticipantWakeV2` | `@1` | `schemas/v2/participant-wake.schema.json` |
| `I-010D ContextContinuationV2` | `@1` | `schemas/v2/context-continuation.schema.json` |
| `I-010E AttentionReceiptV2` | `@1` | `schemas/v2/attention-receipt.schema.json` |

Only `v2-contract-owner` edits `schemas/v2/**`; breaking edits land as
`@2` through an explicit owner handoff plus dependent re-analysis. The
`@1` shapes are the post-rejection clarified ones: I-010B carries the
conditional FR-007 legacy vector and the closed valve-based routing
audit; I-010E carries the per-record stage-to-writer binding.

### Commands and results (2026-07-17, at the candidate commit's tree)

| Command | Result |
|---|---|
| `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'` | 167 tests, OK, 0 skipped (the sole complete dual-validator run) |
| `python3 -m unittest` (repository baseline, full suite) | 1225 tests, OK, 11 skipped (8 pre-existing V1 + 3 counted `baseline-oracle-absence`) |
| `python3 scripts/check_governance.py` (boundary-only, SC-006) | `governance boundary: OK (SpecKit 0.12.11)` |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence` | 72 + 122 + 124 records, 0 mismatched |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence` | all records carry the five mandatory fields |

### Dual-validator pin and post-rework results over the shared corpus

The Draft 2020-12 oracle is dev/test-only `jsonschema==4.26.0` (any other
version is treated as an absent oracle); the runtime side is the explicit
stdlib adapter in `tests/v2/contract/schema_helpers.py`. Both validators
consumed the identical decoded post-rework corpus (159 cases; 133
schema-expressible with identical expected results from both validators —
including the reclassified per-record cross-owner receipt case — and 26
runtime-adapter-only across the six semantic/relational classes with the
fixed per-class oracle treatment). Observed per-class partition counts
and both separately named skip regimes (`oracle-class-skip`: 16 cases;
`baseline-oracle-absence`: 143 oracle-side checks) are recorded in
`evidence/v2/contract/README.md` and match every corpus's authoritative
`expected-counts.json`.

### Corpus revision and downstream adapter obligation

The shared conformance corpus revision is the exact candidate commit
above (`2ab95be81e193d01b91ff078decfc586cf4bf357`), covering
`evals/v2/contract/attention-request/` (unchanged by the rework),
`evals/v2/contract/attention-decision/` (reworked to the conditional
FR-007 shape, 61 cases), and `evals/v2/contract/downstream/`
(reclassified per R3, 62 cases) — each `cases.jsonl` plus
`expected-counts.json`. **Obligation (unchanged)**: each downstream
runtime owner must pass its own stdlib runtime-validation adapter over
this identical corpus revision — including the six runtime-adapter-only
semantic rule classes — before its own handoff.

### Staged-receipt writer map (reworked per R3)

| Stage | Sole appending owner |
|---|---|
| `observation` | `observation-provider` |
| `attention` | `attention-engine` |
| `participant-host` | `participant-host` |
| `transport` | `transport` |

This closed map is now part of the public per-record contract (spec
FR-010): it is encoded in `schemas/v2/attention-receipt.schema.json` and
the individual stdlib validator, so a record attributing one stage to
another stage's owner is invalid as a single document in both validators.
Stages remain immutable and append-only in canonical order; a
prefix-partial receipt is valid-in-progress; the stream-level
canonical-order, skipped-stage, earlier-stage-mutation,
request-ID-correlation, and writer-ownership checks remain in the
runtime-adapter-only receipt-stage sequence class in addition.

### Scene-to-record evidence manifest (regenerated)

`evidence/v2/contract/README.md` (regenerated by T031 as the
current-attempt record) maps all twelve scene rows (S01, S02, S03, S05,
S06, S07, S08, S09, S15, S16, 010-Preattention-bypass, 010-V1) to their
JSONL files and record IDs, verified exhaustive and exact against the 159
post-rework evidence cases, and names the unchanged-file disposition for
`attention-request.jsonl` and the T030 reclassification deltas.

### Rejected-case inventory (updated)

109 of the 159 corpus cases are expected-invalid red cases, every one
enumerated in its corpus `cases.jsonl` and present in the evidence files
and manifest: attention-request 26 (23 schema-expressible; 1 each
id-uniqueness, timestamp-order, trigger-membership), attention-decision
45 (44 schema-expressible, including the conditional-FR-007 and
routing-audit cross-field reds; 1 advice-citation), downstream 38 (28
schema-expressible, including the reclassified per-record cross-owner
receipt case DWN-S06-306; 1 id-uniqueness; 4 binding-expiry; 5
receipt-sequence). They cover invalid identity, reference, order,
coverage, budget, transition, routing-audit cross-field,
conditional-confidence, bypass-contamination, host-secret leakage,
binding/expiry, receipt-stage sequence, per-record cross-owner
attestation, reply-field, social-ledger, and V1-envelope cases; 100%
reject (SC-001, 0 mismatches).

### Migration and provenance notes (CHK091)

- This is the attempt-2 packet following the rejection of candidate
  `81483ce017eb834c5ab533556fa64cd62a8cf2aa` at packet commit
  `9f08124b43ba5beb73c50b876bde51e7b8a1633d`, recorded at
  `evidence/v2/contract/review-2026-07-17-v2-integrator.md` and bound
  into the appended `REJECTED` attempt in
  `evidence/v2/contract/slice-handoff.md`. Its three blockers are
  resolved in this candidate: **R1** — the governance activation fixture
  now builds its synthetic baseline independently of live slice state,
  with the named regression proof green (T026); **R2** — I-010B carries
  the selected design's optional/conditional legacy vector and closed
  routing audit, with corpus, dual-validator, documentation, and evidence
  aligned (T027/T028/T031/T032); **R3** — the I-010E stage-to-writer
  binding is encoded per record in the public schema and individual
  stdlib validator, with the negative corpus case reclassified as
  schema-expressible and stream-level checks preserved (T029/T030).
- No V1 translation bridge exists or is permitted (FR-011): V1 envelopes,
  reply-bearing fields, inferred-roster claims, and
  handled/open/owed/permission state reject in every contract.
- V1 remains the current product until the atomic V2 merge is verified on
  `main`; these contracts create no V2 runtime behavior.
- `legacy_confidence` embeds the legacy `PASS`/`ACK`/`ASK`/`SPEAK`
  verdict vocabulary as transition evidence only; it is optional on
  `status: ok` and required exactly for a margin-active candidate
  `SUPPRESS` (FR-007 as clarified); the optional field, its exact shape,
  and the conditional requirement are fixed for `@1`, and margin
  retirement remains independently evidence-gated.
- Provenance: implemented under program authority
  `evidence/governance/v2-implementation-authorization.md` (all eleven
  slices enumerated), activation
  `evidence/v2/contract/slice-activation.md` (`READY` at `16cccb7`),
  assignment `evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md`,
  within bound runs `speckit-010-20260717T003300631902Z`
  (analysis/readiness), `speckit-010-20260717T081350382670Z` (rejected
  attempt-1 delivery), and `speckit-010-20260717T163451669036Z` (this
  post-rejection delivery).
- Runtime provenance: Python 3.11+ stdlib-only runtime;
  `jsonschema==4.26.0` is dev/test-only behind the pinned offline command
  and never enters runtime dependencies.

### Documentation dispositions, validation, and reviewer

Recorded in full as the attempt-2 documentation section above (T032): 1
slice-owned `UPDATE` re-validated against the clarified shapes
(`docs/contracts/nunchi-v2.md`), 7 `HANDOFF` deltas re-routed to
accepting owner `v2-integrator`, 10 `NO_IMPACT` rationales re-verified
CONFIRMED against the attempt-2 diff with the baseline-health rows
sequenced after the R1 repair; reviewer cc-session-1.

### Known limitations

- A green contract suite proves contract mechanics, not social judgment
  quality; social correctness claims require the downstream slices'
  replay and live acceptance scenes.
- The Draft 2020-12 oracle cannot express the six semantic/relational
  rule classes; they bind only through each consumer's stdlib adapter, so
  the downstream adapter obligation above is load-bearing, not advisory.
- With the per-record stage-to-writer binding now schema-expressible, the
  stream-level writer-ownership check in `validate_receipt_stream` is
  reached only through its per-record validation of each stream record;
  the stream-level check is retained as defense-in-depth and the
  reclassified corpus keeps a red stream case (`DWN-S06-309`) covering it.
- Strict JSON cannot carry non-finite literals: corpus red cases use the
  reserved sentinel strings decoded once by the loader. An in-process
  non-finite float constructed by a consumer never appears on the wire,
  so runtime adapters must enforce the finite confidence and
  effective-margin rules themselves (the schema's contradictory-bounds
  clauses cover only decoded instances).
- The pinned offline command requires `jsonschema==4.26.0` already
  present in the operator's uv cache; `--offline` fails rather than
  fetching; running it generates an untracked `uv.lock` at the repo root
  (delete to restore a clean tree).
- Schema `$id` values use the placeholder domain `nunchi.invalid` pending
  any future canonical-host decision (identifiers only, never
  dereferenced).
- The umbrella parity scenes S04 and S10 through S14 are owned by other
  slices (see the plan's scene-ownership note); this packet claims no
  coverage of them.
- The seven `HANDOFF` documentation deltas apply only in the atomic
  candidate; until cutover the affected documents intentionally retain
  their V1 current-state wording.
- The handoff-packet-commit baseline rerun is owed at the handoff gate
  and cannot be discharged by this packet input (CHK080/CHK090).

## Documentation dispositions — attempt 4 (T047)

Appended after the attempt-1/2/3 sections without rewriting them. This
section re-executes every row of plan §Documentation Impact and Freshness
against the attempt-4 candidate diff.

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Reviewed on**: 2026-07-18, directly in the `v2-contract-owner` worktree
(not via a bound `run speckit` invocation, per the attempt-3 rejection's
required rework path).

**Candidate diff basis**: `git diff --name-only
6fa3996fd7cf92cd6157945245136a8c55cb69cc..0596d14c0579b0ad2530c4e273729dcc274f7034`
(the rejected attempt-3 packet commit to the attempt-4 candidate). The
ordinary-path delta touches only `schemas/v2/attention-decision.schema.json`,
`schemas/v2/attention-receipt.schema.json`,
`schemas/v2/attention-request.schema.json`, `tests/v2/contract/` (the
stdlib adapter and three test files), `evals/v2/contract/{attention-request,
attention-decision,downstream}/`, `evidence/v2/contract/` (the three
aggregate files, this file, and the append-only lifecycle streams), and
`docs/contracts/nunchi-v2.md`, plus the slice's own SpecKit planning
artifacts (`spec.md`, `plan.md`, `tasks.md`: `Slice state` transitions and
the new T047). No file under `src/`, `scripts/`, `docs/governance/`,
`docs/integrations/`, `docs/evaluations/`, or the repository root
documentation set is modified.

### UPDATE (slice-owned), re-validated

| Reviewed path | Disposition | Result |
|---|---|---|
| `docs/contracts/nunchi-v2.md` | `UPDATE` (re-validated) | Corrected for R7–R10: `error.code` documented as the authority's open string with required `detail` (not a locally narrowed enum with optional `detail`); unknown event timestamp documented as omission-only (the local `null` variant removed); the new `actor-reference-integrity` runtime-adapter-only rule documented (self and every typed event actor reference must resolve to a key in `actors`) alongside the existing five; the fetch-time binding/expiry rule corrected to require exact `bound_to` comparison against the host call context, direction authorization, and cap enforcement — replacing the retired "a known, unexpired handle is by construction bound correctly" claim; the partition-class table gains `actor-reference-integrity`. All five embedded JSON examples still validate under both the pinned Draft 2020-12 oracle and the stdlib runtime adapter (validated 2026-07-18, 0 failures); all relative links resolve and none targets a SpecKit-managed path. |

### HANDOFF (accepting owner: `v2-integrator`), re-routed

All seven attempt-1/2/3 `HANDOFF` rows re-verified and re-routed unchanged
in scope — `README.md`, `CHANGELOG.md`, `docs/STABILITY.md`,
`docs/integration.md`, `docs/adapters.md`,
`docs/contracts/channel-adapter-v1.md`,
`docs/architecture/v2-selected-design.md` — each still routing its exact
delta to `v2-integrator` for the atomic current-state update only. None of
the seven rows names a field-level detail R7–R10 touch (they reference
interface IDs, versions, `schemas/v2/*.schema.json` paths, statuses, and
commands only), so none requires text editing this attempt. The accepting
owner and atomic-candidate-only application are unchanged.

### NO_IMPACT, re-verified against the attempt-4 diff

| Reviewed path | Disposition | Re-verification result |
|---|---|---|
| `docs/INSTALL.md` | `NO_IMPACT` | CONFIRMED — the attempt-4 diff changes no install flow or installed artifact; `jsonschema==4.26.0` still appears only behind the pinned `uv run --offline --with` dev/test command. |
| `AGENTS.md` | `NO_IMPACT` | CONFIRMED — `python3 -m unittest` is the green stdlib offline baseline at this tree (run 2026-07-18, post-rework: 1236 tests, OK, 11 skipped — 8 pre-existing V1 plus 3 counted contract oracle-absence skips; the 1222→1236 delta is 14 new unit tests added for the R7/R8/R10 probes, not a coverage loss); the runtime stays dependency-free; the V2-program wording (V1 current until `CUTOVER_VERIFIED`) is unchanged. |
| `CLAUDE.md` | `NO_IMPACT` | CONFIRMED — the "standard-library runtime core" and `python3 -m unittest` claims stay accurate: the rework adds no runtime dependency and does not modify grounding sequence, governance commands, or workflow bindings. |
| `docs/contracts/verdict-suite-data-model-v1.md` | `NO_IMPACT` | CONFIRMED — no verdict-suite artifact changes in the diff. |
| `docs/contracts/verdict-suite-requirements-v1.md` | `NO_IMPACT` | CONFIRMED — same diff basis; no verdict-suite requirement file or claim changes. |
| `docs/evaluations/verdict-suite.md` | `NO_IMPACT` | CONFIRMED — the V1 corpus under `evals/verdict_suite/` is untouched by the diff. |
| `docs/evaluations/verdict-suite-runner.md` | `NO_IMPACT` | CONFIRMED — the runner, its commands, and its outputs are untouched by the diff. |
| `docs/governance/execution-spine.md` | `NO_IMPACT` | CONFIRMED — the diff contains no change under `docs/governance/`, none to `scripts/check_governance.py` or its checks, and none to any documented governance command or gate. |
| `docs/integrations/hermes-core-patch.md` | `NO_IMPACT` | CONFIRMED — no Hermes surface file changes in the diff. |
| `docs/integrations/hermes-core-patch-test-plan.md` | `NO_IMPACT` | CONFIRMED — same diff basis as the Hermes core patch row. |

**Result (attempt 4)**: 1 `UPDATE` corrected for R7–R10; 7 `HANDOFF` deltas
re-routed to accepting owner `v2-integrator` (none requiring text edits
this attempt); 10 `NO_IMPACT` rationales re-verified CONFIRMED against the
attempt-4 diff. No row is unresolved.

## Proposed handoff packet input — attempt 4 (T047)

Appended after the attempt-4 documentation section, in the same
documentation-then-packet order as prior attempts, without rewriting any
earlier section. T019's enumeration remains authoritative for the SC-005
packet inventory; the later convergence, documentation-freshness, and
handoff gates — not this checkbox — establish lifecycle state.

**Prepared by**: cc-session-1 (assigned `v2-contract-owner`), 2026-07-18,
directly in the `v2-contract-owner` worktree, per the attempt-3 rejection's
explicit required rework path and Zoe's direction not to restart
bound-workflow scaffolding for this correction.

### The two defined commits (CHK090)

Per spec SC-005, the packet distinguishes two terms, each independently
carrying the green full-offline-baseline (`python3 -m unittest`)
obligation. Both terms name the identical exact commit throughout this
packet, the lifecycle candidate entry, and the recorded corpus revision:

- **Candidate commit**: `0596d14c0579b0ad2530c4e273729dcc274f7034` on
  branch `v2/contract` (worktree `.worktrees/v2-contract/`) — the exact
  rework-complete code tree fixing rejection R7–R10: `error.code` as the
  authority's open string with required `detail` on the decision and
  receipt schemas and their stdlib mirrors; the nullable event `timestamp`
  removed; the new `actor-reference-integrity` runtime-adapter-only
  partition class enforcing self and every typed event actor reference
  against `actors`; the wake validator sharing `_check_self`/`_check_room`
  with the request validator; and `validate_continuation_fetch` checking
  exact binding, direction authorization, and cap enforcement against the
  issued capability. The full offline baseline recorded in
  `evidence/v2/contract/README.md` (1236 tests, OK, 11 skipped) is the run
  this commit must — and does — reproduce.
- **Handoff packet commit**: not yet pinned; recorded here in the same
  terms once it exists, per the established operational rule
  (`evidence/v2/contract/handoff.md` records it — this file — at the
  handoff gate, since the packet commit cannot name itself from inside its
  own tree). The full offline baseline is owed as a rerun from that exact
  commit at the handoff gate.

### Interface inventory (versions and exact paths)

| Interface | Version | Exact path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | `schemas/v2/attention-request.schema.json` |
| `I-010B AttentionDecisionV2` | `@1` | `schemas/v2/attention-decision.schema.json` |
| `I-010C ParticipantWakeV2` | `@1` | `schemas/v2/participant-wake.schema.json` |
| `I-010D ContextContinuationV2` | `@1` | `schemas/v2/context-continuation.schema.json` |
| `I-010E AttentionReceiptV2` | `@1` | `schemas/v2/attention-receipt.schema.json` |

Only `v2-contract-owner` edits `schemas/v2/**`; breaking edits land as
`@2` through an explicit owner handoff plus dependent re-analysis. The
`@1` shapes are now the R7–R10-corrected ones: `error.code` an open
non-empty string with required `detail` on `AttentionDecisionV2` and
`AttentionReceiptV2`; the event union's `timestamp` field with no `null`
variant on `AttentionRequestV2`; the actor map's `propertyNames` rejecting
an empty key.

### Commands and results (2026-07-18, at the candidate commit's tree)

| Command | Result |
|---|---|
| `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'` | 178 tests, OK, 0 skipped (the sole complete dual-validator run) |
| `python3 -m unittest` (repository baseline, full suite) | 1236 tests, OK, 11 skipped (8 pre-existing V1 + 3 counted `baseline-oracle-absence`) |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence` | 98 + 132 + 150 records, 0 mismatched |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence` | all records carry the five mandatory fields |

### Dual-validator pin and post-rework results over the shared corpus

The Draft 2020-12 oracle is dev/test-only `jsonschema==4.26.0` (any other
version is treated as an absent oracle); the runtime side is the explicit
stdlib adapter in `tests/v2/contract/schema_helpers.py`. Both validators
consumed the identical decoded post-rework corpus (190 cases; 152
schema-expressible with identical expected results from both validators —
including 19 FR-014 authority-conformance cases — and 38
runtime-adapter-only across the now-seven semantic/relational classes,
including the new `actor-reference-integrity` class, with the fixed
per-class oracle treatment). Observed per-class partition counts, the
authority-class table, and both separately named skip regimes
(`oracle-class-skip`: 19 cases; `baseline-oracle-absence`: 171 oracle-side
checks) are recorded in `evidence/v2/contract/README.md` and match every
corpus's authoritative `expected-counts.json`.

### Corpus revision and downstream adapter obligation

The shared conformance corpus revision is the exact candidate commit above
(`0596d14c0579b0ad2530c4e273729dcc274f7034`), covering
`evals/v2/contract/attention-request/` (49 cases, including 6 authority
cases and the new `actor-reference-integrity` class), `evals/v2/contract/
attention-decision/` (66 cases, including 5 authority cases), and
`evals/v2/contract/downstream/` (75 cases, including 8 authority cases and
the widened `binding-expiry`/new `actor-reference-integrity` classes) —
each `cases.jsonl` plus `expected-counts.json`. **Obligation (unchanged)**:
each downstream runtime owner must pass its own stdlib runtime-validation
adapter over this identical corpus revision — including all seven
runtime-adapter-only semantic rule classes — before its own handoff.

### Staged-receipt writer map (unchanged)

| Stage | Sole appending owner |
|---|---|
| `observation` | `observation-provider` |
| `attention` | `attention-engine` |
| `participant-host` | `participant-host` |
| `transport` | `transport` |

Unchanged this attempt; stages remain immutable and append-only in
canonical order.

### Scene-to-record evidence manifest (regenerated)

`evidence/v2/contract/README.md` (regenerated by T047 as the
current-attempt record) maps all twelve scene rows to their JSONL files
and record IDs, verified exhaustive and exact against the 190 post-rework
evidence cases (cross-checked case-ID-for-case-ID against the three
corpora; zero missing, zero spurious entries), names the authority class
with its `red_run_failing_count` field (measured against
`7f9e81460d570e078c4bcbacb138f81c1b291455` for the 5 new authority cases,
against `5383e9f3a5e9c20c08ab54395f4ff370128f03de` for the 14 carried
forward), and re-records all three aggregate files as current-attempt
records.

### Rejected-case inventory (updated)

Exactly 190 minus the schema-expressible-valid and relational-valid counts
are expected-invalid red cases; the exact per-corpus/per-class breakdown is
recorded in `evidence/v2/contract/README.md`'s partition-count table. New
this attempt: `actor-reference-integrity` (9 cases: 7 request, 2
downstream — 2 valid, 7 invalid) covering self/author/mention/reaction/
subject/causal-actor reference absence and one wake-packet parity case;
`binding-expiry` widens from 3 to 7 invalid cases covering host-context
mismatch, unauthorized direction, and both cap-overrun probes (R10); the
decision and downstream `schema-expressible` classes each gain one
missing-`detail` red case and one arbitrary-open-code green case (R7).

### Migration and provenance notes

- This is the attempt-4 packet following the rejection of candidate
  `7f9e81460d570e078c4bcbacb138f81c1b291455` at packet commit
  `6fa3996fd7cf92cd6157945245136a8c55cb69cc`, recorded at
  `evidence/v2/contract/review-2026-07-18-v2-integrator-attempt-3.md` and
  bound into the appended `REJECTED` attempt in
  `evidence/v2/contract/slice-handoff.md`. Its four blockers are resolved
  in this candidate: **R7** — `error.code`/`detail` and the event
  `timestamp` field now match the authority exactly; **R8** — actor-map
  reference integrity is enforced by a new runtime-adapter-only class with
  explicit valid/invalid corpus cases for every named reference kind; **R9**
  — the wake validator shares its self/room checks with the request
  validator instead of partially reimplementing them; **R10** — the issued
  continuation capability's exact binding, direction authorization, and
  per-fetch caps are checked explicitly against the host call context and
  the fetch request.
- No V1 translation bridge exists or is permitted (FR-011): V1 envelopes,
  reply-bearing fields, inferred-roster claims, and
  handled/open/owed/permission state reject in every contract.
- V1 remains the current product until the atomic V2 merge is verified on
  `main`; these contracts create no V2 runtime behavior.
- Provenance: implemented under program authority
  `evidence/governance/v2-implementation-authorization.md` (all eleven
  slices enumerated), activation
  `evidence/v2/contract/slice-activation.md` (`READY` at `16cccb7`),
  assignment `evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md`.
  This attempt was completed directly in the owner worktree rather than
  through a bound `run speckit` invocation, per the attempt-3 rejection's
  explicit required rework path ("do not restart bound-workflow
  scaffolding merely to perform the correction") and Zoe's direction for
  this attempt.
- Runtime provenance: Python 3.11+ stdlib-only runtime;
  `jsonschema==4.26.0` is dev/test-only behind the pinned offline command
  and never enters runtime dependencies.

### Documentation dispositions, validation, and reviewer

Recorded in full as the attempt-4 documentation section above: 1
slice-owned `UPDATE` corrected for R7–R10 (`docs/contracts/nunchi-v2.md`),
7 `HANDOFF` deltas re-routed to accepting owner `v2-integrator` (none
requiring text edits), 10 `NO_IMPACT` rationales re-verified CONFIRMED
against the attempt-4 diff; reviewer cc-session-1.

### Known limitations

- A green contract suite proves contract mechanics, not social judgment
  quality; social correctness claims require the downstream slices'
  replay and live acceptance scenes.
- The Draft 2020-12 oracle cannot express the seven semantic/relational
  rule classes; they bind only through each consumer's stdlib adapter, so
  the downstream adapter obligation above is load-bearing, not advisory.
- Strict JSON cannot carry non-finite literals: corpus red cases use the
  reserved sentinel strings decoded once by the loader.
- The pinned offline command requires `jsonschema==4.26.0` already
  present in the operator's uv cache; `--offline` fails rather than
  fetching; running it generates an untracked `uv.lock` at the repo root
  (delete to restore a clean tree).
- Schema `$id` values use the placeholder domain `nunchi.invalid` pending
  any future canonical-host decision (identifiers only, never
  dereferenced).
- The umbrella parity scenes S04 and S10 through S14 are owned by other
  slices; this packet claims no coverage of them.
- The seven `HANDOFF` documentation deltas apply only in the atomic
  candidate; until cutover the affected documents intentionally retain
  their V1 current-state wording.
- The handoff-packet-commit baseline rerun is owed at the handoff gate
  and cannot be discharged by this packet input.
- The five new authority-conformance cases (REQ-AUTH-005/006, DEC-AUTH-005,
  DWN-AUTH-007/008) are regression guards measured against the rejected
  attempt-3 candidate, not the original attempt-2 baseline; four show a
  `red_run_failing_count` of `0` because the attempt-3 defect was a false
  *accept* (too permissive) rather than a false *reject* — the absence of
  an error under the old schema is itself the measured defect, detailed in
  `evidence/v2/contract/README.md`.

## Documentation dispositions — attempt 5 (T048)

Appended after the attempt-1/2/3/4 sections without rewriting them. This
section re-executes every row of plan §Documentation Impact and Freshness
against the attempt-5 candidate diff.

**Reviewer**: cc-session-1 (assigned `v2-contract-owner`)

**Reviewed on**: 2026-07-18, directly in the `v2-contract-owner` worktree
(not via a bound `run speckit` invocation, per the attempt-3 and attempt-4
rejections' required rework paths).

**Candidate diff basis**: `git diff --name-only
c8a5c280f0600d3787ce1147f48a51a35a760e25..1709c714717cd2735da2e9e08487fe8f02f2b930`
(the rejected attempt-4 decision commit to the attempt-5 candidate). The
ordinary-path delta touches only `tests/v2/contract/schema_helpers.py`,
`tests/v2/contract/test_context_and_receipt.py`,
`evals/v2/contract/downstream/`, `evidence/v2/contract/downstream.jsonl`,
and `docs/contracts/nunchi-v2.md`, plus the slice's own SpecKit planning
artifacts (`Slice state` transitions and the new T048). No schema file, no
`src/`, `scripts/`, `docs/governance/`, `docs/integrations/`,
`docs/evaluations/`, or repository root documentation file is modified.

### UPDATE (slice-owned), re-validated

| Reviewed path | Disposition | Result |
|---|---|---|
| `docs/contracts/nunchi-v2.md` | `UPDATE` (re-validated) | Corrects the one remaining retired claim in the `I-010D` interface section ("a known, unexpired handle is by construction the correct binding") to match the R10-completed fetch-time rule already documented in the runtime-adapter-only rules list. All five embedded JSON examples still validate under both validators (validated 2026-07-18, 0 failures); all relative links resolve and none targets a SpecKit-managed path. |

### HANDOFF (accepting owner: `v2-integrator`), re-routed

All seven attempt-1/2/3/4 `HANDOFF` rows re-verified and re-routed
unchanged in scope; none names a field-level detail this attempt's R10
completion touches, so none requires text editing.

### NO_IMPACT, re-verified against the attempt-5 diff

All ten attempt-1/2/3/4 `NO_IMPACT` rows re-verified CONFIRMED against the
attempt-5 diff; `AGENTS.md`'s baseline-count claim re-verified at 1242
tests, OK, 11 skipped (the 1236→1242 delta is 6 new unit tests for the
R10-completion probes, not a coverage loss).

**Result (attempt 5)**: 1 `UPDATE` corrected for R10 completion; 7
`HANDOFF` deltas re-routed unchanged; 10 `NO_IMPACT` rationales
re-verified CONFIRMED. No row is unresolved.

## Proposed handoff packet input — attempt 5 (T048)

Appended after the attempt-5 documentation section, in the same
documentation-then-packet order as prior attempts, without rewriting any
earlier section.

**Prepared by**: cc-session-1 (assigned `v2-contract-owner`), 2026-07-18,
directly in the `v2-contract-owner` worktree, per the attempt-3 and
attempt-4 rejections' explicit required rework paths.

### The two defined commits

- **Candidate commit**: `1709c714717cd2735da2e9e08487fe8f02f2b930` on
  branch `v2/contract` (worktree `.worktrees/v2-contract/`) — the exact
  tree completing R10: `validate_continuation_fetch` validates every issued
  handle state as the complete selected `ContextContinuation` capability
  (via the existing `_check_continuation`), validates `host_context` as the
  same closed binding shape (via the existing `_check_continuation_binding`)
  before the exact-equality comparison, treats `expires_at` as optional,
  and returns a validation error instead of raising on an incomparable
  timestamp pair. R7, R8, and R9 are unchanged from the CLEARED attempt-4
  candidate. The full offline baseline recorded in
  `evidence/v2/contract/README.md` (1242 tests, OK, 11 skipped) is the run
  this commit must — and does — reproduce.
- **Handoff packet commit**: not yet pinned; recorded here once it exists,
  per the established operational rule.

### Interface inventory (versions and exact paths)

Unchanged from attempt 4 — no schema file is touched this attempt:

| Interface | Version | Exact path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | `schemas/v2/attention-request.schema.json` |
| `I-010B AttentionDecisionV2` | `@1` | `schemas/v2/attention-decision.schema.json` |
| `I-010C ParticipantWakeV2` | `@1` | `schemas/v2/participant-wake.schema.json` |
| `I-010D ContextContinuationV2` | `@1` | `schemas/v2/context-continuation.schema.json` |
| `I-010E AttentionReceiptV2` | `@1` | `schemas/v2/attention-receipt.schema.json` |

### Commands and results (2026-07-18, at the candidate commit's tree)

| Command | Result |
|---|---|
| `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'` | 184 tests, OK, 0 skipped (the sole complete dual-validator run) |
| `python3 -m unittest` (repository baseline, full suite) | 1242 tests, OK, 11 skipped (8 pre-existing V1 + 3 counted `baseline-oracle-absence`) |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence` | 98 + 132 + 164 records, 0 mismatched |
| `uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence` | all records carry the five mandatory fields |

### Dual-validator pin and results over the shared corpus

Both validators consumed the identical decoded post-rework corpus (197
cases; 152 schema-expressible — unchanged from attempt 4 — and 45
runtime-adapter-only across the seven semantic/relational classes, with
`binding-expiry` widening from 8 to 15). Observed per-class partition
counts and both separately named skip regimes (`oracle-class-skip`: 26
cases; `baseline-oracle-absence`: 171 oracle-side checks) are recorded in
`evidence/v2/contract/README.md` and match every corpus's authoritative
`expected-counts.json`.

### Corpus revision and downstream adapter obligation

The shared conformance corpus revision is the exact candidate commit above
(`1709c714717cd2735da2e9e08487fe8f02f2b930`); only
`evals/v2/contract/downstream/` changed this attempt (82 cases, up from
75). **Obligation (unchanged)**: each downstream runtime owner must pass
its own stdlib runtime-validation adapter over this identical corpus
revision before its own handoff.

### Scene-to-record evidence manifest (regenerated)

`evidence/v2/contract/README.md` (regenerated by T048) maps all twelve
scene rows to their JSONL files and record IDs, verified exhaustive and
exact against the 197 post-rework evidence cases (cross-checked
case-ID-for-case-ID against the three corpora; zero missing, zero spurious
entries).

### Migration and provenance notes

- This is the attempt-5 packet following the rejection of candidate
  `0596d14c0579b0ad2530c4e273729dcc274f7034` at packet commit
  `aa396ffebb552aeee91fd1b6a32a22538b2564c6`, recorded at
  `evidence/v2/contract/review-2026-07-18-v2-integrator-attempt-4.md` and
  bound into the appended `REJECTED` attempt in
  `evidence/v2/contract/slice-handoff.md`. R7, R8, and R9 were CLEARED by
  that review and needed no rework; its one remaining blocker is resolved
  in this candidate: **R10** — every issued handle state is now validated
  as the complete selected `ContextContinuation` capability, `host_context`
  is validated as the identical closed binding shape before comparison,
  the selected optional `expires_at` is honored, and a mixed-timezone
  timestamp comparison returns a validation error instead of raising.
- No V1 translation bridge exists or is permitted (FR-011). V1 remains the
  current product until the atomic V2 merge is verified on `main`.
- Provenance: implemented under program authority
  `evidence/governance/v2-implementation-authorization.md` (all eleven
  slices enumerated), activation
  `evidence/v2/contract/slice-activation.md` (`READY` at `16cccb7`),
  assignment `evidence/governance/assignments/cc-session-1-v2-contract-owner-2026-07-16.md`.
  This attempt was completed directly in the owner worktree rather than
  through a bound `run speckit` invocation, per the attempt-3 and
  attempt-4 rejections' explicit required rework paths.
- Runtime provenance: Python 3.11+ stdlib-only runtime;
  `jsonschema==4.26.0` is dev/test-only behind the pinned offline command
  and never enters runtime dependencies.

### Documentation dispositions, validation, and reviewer

Recorded in full as the attempt-5 documentation section above: 1
slice-owned `UPDATE` corrected for the retired-claim residue
(`docs/contracts/nunchi-v2.md`), 7 `HANDOFF` deltas re-routed unchanged,
10 `NO_IMPACT` rationales re-verified CONFIRMED; reviewer cc-session-1.

### Known limitations

- A green contract suite proves contract mechanics, not social judgment
  quality.
- The Draft 2020-12 oracle cannot express the seven semantic/relational
  rule classes; they bind only through each consumer's stdlib adapter.
- The pinned offline command requires `jsonschema==4.26.0` already
  present in the operator's uv cache; running it generates an untracked
  `uv.lock` at the repo root (delete to restore a clean tree).
- Schema `$id` values use the placeholder domain `nunchi.invalid`.
- The umbrella parity scenes S04 and S10 through S14 are owned by other
  slices; this packet claims no coverage of them.
- The seven `HANDOFF` documentation deltas apply only in the atomic
  candidate.
- The handoff-packet-commit baseline rerun is owed at the handoff gate
  and cannot be discharged by this packet input.
