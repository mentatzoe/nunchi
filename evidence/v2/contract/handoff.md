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
