# Implementation Plan: V2 Parity and Atomic Cutover

**Branch**: `integration/v2` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/110-v2-parity-cutover/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-integrator`

**Assigned participant / source**: codex-session-2 — evidence/governance/assignments/codex-session-2-v2-integrator-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/110-v2-parity-cutover`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/110-v2-parity-cutover`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/parity/slice-activation.md` (written only
after every readiness prerequisite is accepted; it attests those facts and
establishes `READY` before `ACTIVE`)

**Candidate evidence**: append-only
`evidence/v2/parity/slice-candidate.md` attempts (latest valid attempt supports
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: append-only `evidence/v2/parity/slice-handoff.md`
`HANDOFF_READY` and `REJECTED` attempts (absent while `PLANNED`)

**Acceptance evidence**: immutable
`evidence/v2/parity/slice-acceptance.md` (for `ACCEPTED`; absent while
`PLANNED`)

**Rework execution**: Candidate and handoff files are append-only attempt
streams. If convergence adds tasks, this slice stays `ACTIVE`, retains its
immutable activation, and starts a new bound `run speckit`. If the completed
handoff is rejected, the recorder appends `REJECTED`, returns the slice to
`ACTIVE`, and the owner starts a new bound run—never resume the completed run.
A paused post-convergence gate may resume only for fixes that leave the task
graph unchanged; all later attempts append without rewriting history.

**Upstream dependencies**: `010`, `020`, `030`, `040`, `050`, `060`, `070`,
`080`, `090`, `100`

**Dependency commits**: ordered `010=<full-sha>` through `100=<full-sha>`, each
matching the upstream slice's immutable acceptance record

**Dependency acceptance references**: ordered consumer-owned
`010=evidence/v2/parity/dependency-010-acceptance.md` through
`100=evidence/v2/parity/dependency-100-acceptance.md`, with consumer/upstream,
commit, accepting participant/date, exact upstream `slice-acceptance.md`, and
durable-decision metadata

## Summary

Once validly activated, this final-sink slice admits only reviewed and
evidence-complete handoffs, assembles them on an isolated integration branch, rejects any mixed
V1/V2 or interface drift, and proposes one atomic V2 candidate. It then proves
equivalent normalization/routing/participant context across the CLI, transports,
adapters, and harnesses on their installed runtimes; runs the complete staged
room ladder; indexes S01-S16 evidence; and updates product/release truth without
performing promotion. The slice implementation task graph stops after preparing
the exact candidate and documentation/handoff inputs; later workflow gates
establish `CONVERGED` and `HANDOFF_READY`. Zoe's acceptance and the atomic
merge/post-merge verification are the separately governed umbrella program
tail; package release and promotion remain separate.

This planning baseline authorizes no action and creates no product behavior.

## Technical Context

**Language/Version**: Python 3.11+ core and tooling plus existing
surface-native integration formats

**Primary Dependencies**: Existing repository/runtime dependencies only; no new
core runtime dependency planned

**Storage**: Ordinary source/config files, deterministic fixtures, append-only
evidence, and installed-runtime provenance; no central room or participant store

**Testing**: stdlib `unittest`, repository atomicity/contract tests, reusable
parity replay under `evals/`, routing checks with injected validated decisions,
trusted-bypass routing checks with zero classifier calls and no injected social
result, post-hoc participant-output evaluation with no runtime prose filter,
installed surface probes, slice-`100` assurance rerun, and six pinned staged
live rooms

**Target Platform**: Core/CLI, Discord-MCP, Hermes, Claude Code, Codex, and every
in-tree standalone channel adapter; live evidence uses the six fixed S14 stages,
while any additional adapter capability is exercised through its declared live
or bounded probe without inventing unavailable facts

**Project Type**: Python library/CLI with transport, adapter, and agent-harness
integrations

**Performance Goals**: Bounded eager context and byte/event caps remain enforced;
no second social model call; parity runner records model-specific token estimates
without injecting unbounded history

**Constraints**: Atomic no-bridge cutover; exact canonical interface versions;
no invented platform facts; no deterministic social oracle; no runtime
participant-prose filter; trusted bypass only; no fabricated social result;
immutable singly owned request-correlated receipt stages; no social
registry/ledger; required lifecycle failures block cutover; no promotion; no
release claim without installed-runtime and mixed-room evidence

**Scale/Scope**: Eleven-slice program (`010`–`110`), all in-tree V2 consumers,
S01-S16, and one final integrated candidate/evidence/release-boundary packet

## Constitution Check

*GATE: Passes in `PLANNED`; must be re-checked at slice activation and before
the slice enters `ACTIVE`.*

- **Selected V2 boundary**: PASS. Integration preserves pre-attention and normal
  participant contribution ownership without adding orchestration.
- **Human-shaped judgment**: PASS. S04 and S05 explicitly reject deterministic
  social suppression and validate governed model judgment.
- **Truthful identity/observation**: PASS. S01-S03, S13, S15, and S16 cover exact
  identity, native facts, bounded context, and no registry/ledger.
- **Attention/contribution ownership**: PASS. S06-S10 cover direct action,
  silence, defer/error, and no send-time reclassification.
- **Atomic parity**: PASS. Every dependency is required and no mixed candidate
  may merge or release.
- **Evidence before claims**: PASS. Deterministic, replay, per-surface, security,
  provenance, live room, and docs truth evidence are mandatory.
- **Control-plane boundary**: PASS. This directory contains planning only; every
  product artifact has an ordinary target.
- **Single owner**: PASS. `v2-integrator` assembles but returns semantic changes
  and risk decisions to their accountable owners.
- **Program/slice lifecycle boundary**: PASS. The slice is `PLANNED`, program
  implementation authority is `NOT_GRANTED`, and implementation tasks are
  dormant.

Post-design re-check: PASS. All dependencies, canonical interfaces, S01-S16
scenes, evidence paths, and exclusions are explicit; no constitution exception
or product artifact under `specs/` is planned.

## Slice Interfaces

### Consumes

| Interface or handoff | Owner | Planned ordinary-path authority |
|---|---|---|
| `I-010A AttentionRequestV2@1` | `010` | `schemas/v2/attention-request.schema.json` |
| `I-010B AttentionDecisionV2@1` | `010` | `schemas/v2/attention-decision.schema.json` |
| `I-010C ParticipantWakeV2@1` | `010` | `schemas/v2/participant-wake.schema.json` |
| `I-010D ContextContinuationV2@1` | `010` | `schemas/v2/context-continuation.schema.json` |
| `I-010E AttentionReceiptV2@1` | `010` | `schemas/v2/attention-receipt.schema.json` |
| `I-020A ObservationProviderV2@1` | `020` | `src/nunchi/observation.py` |
| `I-030A AttentionEngineV2@1` | `030` | `src/nunchi/core.py`, `src/nunchi/cli.py` |
| `I-040A ParticipantTurnHostV2@1` | `040` | `src/nunchi/participant.py` |
| `I-050A DiscordEventSourceV2@1` | `050` | `src/nunchi/mcp_discord/` |
| Contract implementation/evidence handoff | `010` | `evidence/v2/contract/` |
| Observation implementation/evidence handoff | `020` | `evidence/v2/observation/` |
| Attention implementation/evidence handoff | `030` | `evidence/v2/attention/` |
| Participant-host implementation/evidence handoff | `040` | `evidence/v2/participant/` |
| Discord-transport implementation/evidence handoff | `050` | `evidence/v2/discord-transport/` |
| Hermes implementation/evidence handoff | `060` | `evidence/v2/hermes/` |
| Claude Code implementation/evidence handoff | `070` | `evidence/v2/claude-code/` |
| Codex implementation/evidence handoff | `080` | `evidence/v2/codex/` |
| Channel-adapter implementation/evidence handoff | `090` | `evidence/v2/adapters/` |
| V2 security assurance report and audited commit set | `100` | `evidence/v2/security/README.md` |
| V2 security readiness packet | `100` | `evidence/v2/security/handoff.json` |

### Produces and Feeds the Program Tail

| Integration artifact or program-tail record | Accountable writer | Planned ordinary-path authority |
|---|---|---|
| Integrated V2 candidate manifest | assigned `v2-integrator` | `evidence/v2/parity/integration-manifest.json` |
| V2 parity evidence index | assigned `v2-integrator` | `evidence/v2/README.md` |
| S01-S16 scene/surface evidence manifest | assigned `v2-integrator` | `evidence/v2/parity/manifest.json` |
| V2 release-readiness boundary | assigned `v2-integrator` | `docs/releases/v2-readiness.md` |
| Append-only slice candidate attempts, after convergence | assigned `v2-integrator` | `evidence/v2/parity/slice-candidate.md` |
| Append-only handoff/rejection attempts, after docs freshness | assigned `v2-integrator`; Zoe remains the rejection decision owner | `evidence/v2/parity/slice-handoff.md` |
| Exact slice acceptance | assigned `v2-integrator`, copying Zoe's decision with `Recorded by: v2-integrator` | `evidence/v2/parity/slice-acceptance.md` |
| Program cutover acceptance | assigned `v2-program-owner`, copying accepted Zoe decision with `Recorded by: v2-program-owner` | `evidence/v2/parity/cutover-acceptance.md` |
| Merged-main verification | assigned `v2-integrator`; verified by `v2-program-owner` | `evidence/v2/parity/post-merge-verification.md` |

These are integration/evidence artifacts, not product interfaces. This final
sink produces no interface consumed by slices `010`–`100`; defects are returned
as owner handbacks rather than reverse dependencies. The canonical interface
registry remains exactly `I-010A`–`I-050A`.

## Integration Strategy

**Integration order**: Verify that the one valid program implementation-
authority record enumerates exactly slices `010` through `110`, then apply
slice `110`'s independent readiness gate; accept `010` contracts, then
`020`/`030`, then `040`/`050`, then surface handoffs `060`–`090`, then
security/provenance `100`. Pin all commits/interfaces before assembly. Integrate
on a non-releaseable branch, run the atomicity suite after every merge, return
semantic conflicts to owners, rerun slice `100` assurance on the exact assembled
candidate, and re-audit every affected stochastic/live cell if semantic or
security hashes changed. Only after atomic assembly and assurance pass may
per-surface probes and S01-S16 evidence be adjudicated. After every gate passes,
the assigned integrator appends the slice candidate and handoff attempts and
stops slice implementation at `HANDOFF_READY`. The assigned integrator copies
Zoe's explicit decision for that exact packet into immutable slice acceptance;
on acceptance, the assigned program owner copies it only into program cutover
acceptance. Rejection instead appends an attributable `REJECTED`
decision to the handoff stream and returns the slice to `ACTIVE`; because the
handoff run completed, rework starts a new bound slice-`110` run and appends new
attempts without rewriting history. Only after acceptance does the umbrella program tail coordinate one atomic PR/merge
to main followed by verification of the merge SHA; it does not authorize package
release or promotion. Because the merge SHA cannot be known before merge, its
post-merge-verification record lands only through a product-neutral evidence
follow-up commit/PR with no source, schema, runtime, or behavior change. The
merged candidate remains `CUTOVER_ACCEPTED` with exact-main verification and
final current-state wording pending. That same docs/evidence-only follow-up
validates exact main, finalizes current-state documentation, and establishes
`CUTOVER_VERIFIED` only after both pass.

**Worktree/branch**: Authorized slice implementation uses isolated worktree
`.worktrees/v2-integration/` on branch `integration/v2`. Any temporary
mixed state remains confined there, is marked non-releaseable, and never merges
to main.

**Handoff to**: Umbrella program and Zoe for final candidate, explicit repository
cutover acceptance, and a separate release go/no-go; no downstream implementation
owner.

**Conflict ownership**: `v2-integrator` owns integration manifests, parity
runner/comparison, staged-room evidence index, and final docs/release
reconciliation. The originating owner resolves semantic changes to its
interface or component. `v2-security-owner` owns security risk disposition;
only Zoe accepts residual risk.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| `S01 exact self/alias collision` | all adapters/harnesses | Exact transport self wins; loose alias collision never proves authorship | `evidence/v2/parity/s01-identity/` |
| `S02 native relations` | capable surfaces | Mention, reply, reaction, and membership remain literal; unavailable facts remain unknown | `evidence/v2/parity/s02-native-relations/` |
| `S03 bounded continuation/tail` | all observation providers | Trigger, relation closure, coverage, continuation merge, and post-trigger tail remain ordered and bounded | `evidence/v2/parity/s03-context/` |
| `S04 false-suppression scars` | core and harnesses | Claude/Station scars reach model judgment; no deterministic semantic gate | `evidence/v2/parity/s04-suppression-scars/` |
| `S05 governed SUPPRESS + recovery` | suppression-capable surfaces | Authorized suppress is recoverable after restart; missing legitimacy widens attention | `evidence/v2/parity/s05-governed-suppress/` |
| `S06 WAKE/bypass direct contribution` | every harness | WAKE or trusted advice-free `PREATTENTION_BYPASS` receives one normal turn and contributes directly; bypass makes zero classifier calls and meta-answer grading occurs post-hoc without runtime filtering | `evidence/v2/parity/s06-wake-act/` |
| `S07 participant silence/no-send` | every harness | WAKE/DEFER/ERROR/bypass may end without a send; post-hoc grading distinguishes silence from a meta-answer without changing runtime output or fabricating transport delivery | `evidence/v2/parity/s07-silence/` |
| `S08 dual DEFER transition` | core and harnesses | Classifier and margin defer remain separate and uncertainty never hard-suppresses | `evidence/v2/parity/s08-defer-transition/` |
| `S09 operational ERROR wakes` | every surface | Operational failures remain separate and wake participant by default | `evidence/v2/parity/s09-error-fallback/` |
| `S10 no send-time social reclassification` | every sending harness | No second classifier or social permit state revokes a wake; trusted bypass has zero classifier calls end to end | `evidence/v2/parity/s10-single-judgment/` |
| `S11 duplicate/self hygiene` | transports/adapters | Exact duplicate and exact self are transport facts, retained and receipted correctly | `evidence/v2/parity/s11-transport-hygiene/` |
| `S12 installed provenance/restart/probe` | every installed surface | Exact candidate/config runs after restart and reports schema/probe result | `evidence/v2/provenance/` |
| `S13 normalized equivalence` | all adapters/harnesses | Equivalent facts produce equivalent observations and participant availability; routing parity injects validated decisions and never scores a socially correct verdict deterministically | `evidence/v2/parity/s13-adapters/` |
| `S14 mixed-harness room parity` | six pinned live stages | Hermes-only; Hermes+Claude; Hermes+Codex; full Hermes+Claude+Codex; multi-human Discord; and multi-human Telegram via Hermes pass required lifecycle outcomes without sustained all-speak/all-mute, deafness, polling dependence, or drift | `evidence/v2/live/s14-mixed-room/` |
| `S15 bounded budget/no bomb` | attention and participant paths | Selected event/byte budgets preserve required facts without full-history injection | `evidence/v2/parity/s15-context-budget/` |
| `S16 no registry/ledger and staged-receipt boundary` | public contracts/state | No roster inference, handled/open state, or obligation queue enters later judgment; immutable observation/attention/participant-host/transport records remain request-correlated and singly owned | `evidence/v2/parity/s16-no-ledger/` |

All slice-`110`-owned cross-surface tests target `tests/v2/parity/`.
Reusable parity fixtures/runners target `evals/v2/parity/`. Run records target
the canonical `evidence/v2/parity/`, `evidence/v2/provenance/`, and
`evidence/v2/live/` subtrees. Security evidence from `100` is referenced, not
copied or re-owned.
`evidence/v2/parity/manifest.json` maps every S01-S16/surface pair to its exact
record, command, candidate ref, stable `scene_id`, evidence grade, and
pass/block/capability-limitation disposition. Bypass and receipt rows also carry
request ID, stage owner, trusted bypass provenance, `classifier_not_invoked`,
and classifier-call count. A limitation is non-blocking only for a genuinely
unavailable native platform fact; required lifecycle failures remain blocking.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/110-v2-parity-cutover/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

No product source, schema, contract, test, fixture, evaluation, evidence,
runtime asset, or product documentation may be placed in this tree.

### Ordinary integration artifacts (repository root)

```text
scripts/
├── check_v2_atomicity.py
└── v2_surface_probe.py

tests/v2/
└── parity/
    ├── test_integration_manifest.py
    ├── test_repository_atomicity.py
    ├── test_scene_catalog.py
    ├── test_surface_parity.py
    └── test_surface_probe.py

evals/v2/parity/
├── fixtures/
├── meta_answer.py
├── scene_catalog.py
└── runner.py

evidence/v2/
├── README.md
├── parity/
│   ├── slice-candidate.md
│   ├── slice-handoff.md
│   ├── slice-acceptance.md
│   ├── integration-manifest.json
│   ├── manifest.json
│   ├── cutover-acceptance.md
│   ├── post-merge-verification.md
│   ├── security-recheck/
│   └── scene records
├── provenance/
└── live/s14-mixed-room/

docs/
├── evaluations/v2-parity.md
├── releases/v2-readiness.md
├── integration.md
└── STABILITY.md
```

**Structure Decision**: The integrator owns only assembly checks, shared scene
evaluation/comparison, final evidence indexing, and cross-product documentation
truth. Component code remains in its existing `src/` or `integrations/` home and
changes only through the accountable upstream owner.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning task/story |
|---|---|---|
| Product integration | accepted upstream paths under `src/` and `integrations/`; `scripts/check_v2_atomicity.py`, `scripts/v2_surface_probe.py` | US1, US2 |
| Machine-readable product contracts | None owned; consume slice-`010` contracts under `schemas/v2/` | All stories |
| Tests | `tests/v2/parity/` only | US1, US2 |
| Evaluation runners/corpora | `evals/v2/parity/` | US2, US3 |
| Evidence | `evidence/v2/README.md`, `evidence/v2/parity/` including `manifest.json`, `slice-candidate.md`, `slice-handoff.md`, `slice-acceptance.md`, `cutover-acceptance.md`, and `post-merge-verification.md`, `evidence/v2/provenance/`, `evidence/v2/live/` with references to upstream evidence | US1, US2, US3 plus umbrella program tail |
| Product/release docs | `README.md`, `CHANGELOG.md`, `docs/integration.md`, `docs/STABILITY.md`, `docs/evaluations/v2-parity.md`, `docs/releases/v2-readiness.md`, security docs by reference | US3 |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global current product/evidence state | `README.md` | `UPDATE` | T038 candidate + post-merge follow-up / `v2-integrator` | Reconcile every accepted upstream delta in the candidate while retaining truthful `CUTOVER_ACCEPTED`/verification-pending wording; finalize verified-current behavior, surfaces, limitations, and evidence grades only after exact-main checks. |
| Root guidance, change, and security state | `AGENTS.md`, `CLAUDE.md`, `CHANGELOG.md`, `SECURITY.md` | `UPDATE` | T038-T040 candidate + post-merge follow-up / `v2-integrator` | Record the accepted breaking candidate without claiming verified-current behavior, then validate and finalize current-state claims against the exact main SHA in the docs/evidence-only follow-up. |
| Shared current guides and V1 archive index | `docs/INSTALL.md`, `docs/STABILITY.md`, `docs/adapters.md`, `docs/integration.md`, `docs/architecture/v2-selected-design.md`, `docs/governance/execution-spine.md`, `docs/archive/v1/README.md` | `UPDATE` | T038-T040 / `v2-integrator` | Reconcile upstream deltas, change selected-design status, preserve historical truth, and validate links, Mermaid, examples, commands, install/version claims, and evidence grades. |
| Contract and evaluation transition | `docs/contracts/channel-adapter-v1.md`, `docs/contracts/nunchi-v2.md`, `docs/contracts/verdict-suite-data-model-v1.md`, `docs/contracts/verdict-suite-requirements-v1.md`, `docs/evaluations/verdict-suite.md`, `docs/evaluations/verdict-suite-runner.md`, `docs/evaluations/v2-parity.md` | `UPDATE` | T038-T040 / `v2-integrator` | Mark exact supersession/retention boundaries, preserve V1 scar evidence, and validate V2 parity commands, schemas, links, and truthfulness tests. |
| Component and integration guides | `docs/observation/v2.md`, `docs/attention/v2.md`, `docs/participant/v2.md`, `docs/adapters-v2.md`, `docs/integrations/discord-mcp-v2.md`, `docs/integrations/hermes-v2.md`, `docs/integrations/claude-code-v2.md`, `docs/integrations/codex-v2.md`, `docs/integrations/hermes-core-patch.md`, `docs/integrations/hermes-core-patch-test-plan.md` | `UPDATE` | T038 / `v2-integrator` | Validate every accepted component version, diagram, capability, limitation, install/probe command, and evidence reference against the atomic candidate. |
| Security and release boundary | `docs/security/assurance-handoffs.md`, `docs/security/operational-safety.md`, `docs/security/runtime-provenance.md`, `docs/security/suppression-governance.md`, `docs/security/threat-model-v2.md`, `docs/releases/v2-readiness.md` | `UPDATE` | T038-T040 / `v2-integrator` | Reconcile the accepted assurance packet, residual risks, provenance, release boundary, evidence links, and post-merge verification without making a promotion claim. |
| Installed-surface operator docs | `integrations/mcp-discord/README.md`, `integrations/mcp-discord/DESIGN.md`, `integrations/hermes/README.md`, `integrations/claude-code/README.md`, `integrations/claude-code/DEFER_EVAL.md`, `integrations/claude-code/transport-patch/README.md`, `integrations/codex/README.md` | `UPDATE` | T038 / `v2-integrator` | Validate installed bytes/config/process identity, native capability truth, restart/residue, lifecycle, links, examples, probes, and evidence grade for each surface. |

Because this slice changes global current behavior, `NO_IMPACT` and `HANDOFF`
are invalid for the rows above. T038 and T043 prepare the ordinary validation
and packet inputs; the separate post-convergence documentation-freshness gate
must pass before the `slice-handoff.md` attempt is appended. Candidate docs
must remain truthful about verification pending. After the atomic merge, exact-
main checks and final current-state documentation validation must pass together
in the docs/evidence-only follow-up before `CUTOVER_VERIFIED`.

## Owner Handoff

Each dependency owner MUST hand off exact commit, verification commands/results,
canonical interface versions, ordinary evidence, installed-runtime provenance,
and limitations. `v2-integrator` MUST return semantic defects to that owner and
record the resolution. The final slice handoff to Zoe and the umbrella program includes
the integrated candidate manifest, parity evidence index, release-readiness
boundary, exact candidate commit/package identities, all
commands/results, security readiness, failures/limitations, and an explicit
statement that promotion remains unaddressed. The assigned `v2-integrator`
appends candidate and handoff attempts to `slice-candidate.md` and
`slice-handoff.md` and stops at `HANDOFF_READY`. Zoe owns the external acceptance
decision; the assigned `v2-integrator` durably copies it into immutable
`slice-acceptance.md` or the append-only rejection stream, while the assigned
`v2-program-owner` copies an acceptance only into `cutover-acceptance.md`; rejection returns
to the handoff stream and returns the slice to `ACTIVE` without erasing the
attempt, then starts a new bound run rather than resuming the completed one. The umbrella program tail then owns the atomic PR/merge
and `post-merge-verification.md`; these are not slice implementation tasks or a
package-release handoff.

## Complexity Tracking

No constitution violation or complexity exception is planned.
