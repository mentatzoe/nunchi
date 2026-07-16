# Implementation Plan: V2 Security and Runtime Provenance

**Branch**: `v2/security-provenance` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from
`specs/100-v2-security-provenance/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-security-owner`

**Assigned participant / source**: cc-session-blind — evidence/governance/assignments/cc-session-blind-v2-security-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/100-v2-security-provenance`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/100-v2-security-provenance`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `GRANTED`

**Activation evidence**: `evidence/v2/security/slice-activation.md` (written
only after every readiness prerequisite is accepted; it attests those facts and
establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/security/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/security/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/security/slice-acceptance.md` (for
`ACCEPTED`; absent while `PLANNED`)

**Upstream dependencies**: `010`, `020`, `030`, `040`, `050`, `060`, `070`,
`080`, `090`

**Dependency acceptance mapping**: activation evidence MUST preserve the
declared dependency order in `Accepted dependencies`, ordered
`Dependency commits` entries as `slice=full-sha`, and matching ordered
`Dependency acceptance references` as `slice=repo-relative-evidence-file`.

**Rejection / rework contract**: Candidate and handoff files are append-only attempt
streams after first use.
If convergence adds tasks, the slice stays `ACTIVE`; retain its immutable
activation and start a new bound `run speckit` for this slice. If a completed
handoff is rejected, append `REJECTED`, return to `ACTIVE`, and likewise start
a new bound run—never resume the completed run. Fixes requested by a paused
post-convergence gate may resume that same run only when the task graph is
unchanged. New candidate and handoff attempts append without rewriting history.

## Summary

Once validly activated after every contract, core, and surface slice hands off,
this blocking assurance slice audits the exact commits against governed suppression,
recoverability, send safety, credential, threat, adversarial, and installed-
runtime provenance obligations. It authors assurance tests/eval tooling,
evidence, the threat model, and audit handoffs. A failed control returns to the
named implementation owner; slice `100` re-audits the repaired commit and never
implements the mitigation. It then hands one readiness packet to the final
integrator.

This planning baseline authorizes no action and creates no product behavior.

## Technical Context

**Language/Version**: Python 3.11+ for assurance tooling and tests; existing
surface-native configuration/runtime formats remain owned by their slices

**Primary Dependencies**: Python standard library for assurance checks;
existing optional surface dependencies only; no runtime dependency or product
implementation is owned by this slice

**Storage**: Operator-owned configuration plus ordinary off-surface receipts
and append-only evidence files; no social state store

**Testing**: stdlib `unittest`, contract/integration tests under `tests/`,
reusable adverse replay under `evals/`, the slice-`030` selected Gemini 3.1
Flash Lite/GPT-5.5/Qwen3 attention families, at least five retained independent
repetitions per stochastic model/scene/configuration cell, and installed-runtime/
live records under `evidence/`

**Target Platform**: Core/CLI and all in-tree V2 adapter/harness surfaces handed
off by slices `060` through `090`

**Project Type**: Cross-repository assurance/evaluation lane for a Python
library/CLI with adapter and agent-harness integrations

**Performance Goals**: Operational safety and provenance add no unbounded room
history or extra social model judgment; trusted bypass adds zero classifier
calls; send backstops remain constant-space per configured channel window

**Constraints**: Zero new core runtime dependency; no deterministic social
heuristic; no secrets in request schemas or committed evidence; no mixed
operational/social verdict; bypass only from trusted operator configuration; no
fabricated social result; immutable singly owned receipt stages; no risk
acceptance by an agent

**Scale/Scope**: One security closure across all interfaces and surfaces from
`010` through `090`, feeding only final integration slice `110`

## Constitution Check

*GATE: Passes in `PLANNED`; must be re-checked at slice activation and before
the slice enters `ACTIVE`.*

- **Selected V2 boundary**: PASS. This slice audits attention suppression and
  operational boundaries; it does not implement them, compose replies, or
  allocate turns.
- **Human-shaped judgment**: PASS. No deterministic conversational suppressor is
  introduced; missing legitimacy widens attention.
- **Truthful identity/observation**: PASS. Authorization binds exact participant
  and surface facts and does not create a roster or social ledger.
- **Attention/contribution ownership**: PASS. Send safety is operational only
  and no second social judgment is allowed; trusted bypass still traverses the
  canonical attention-engine seam but skips the classifier/model judgment, then
  invokes a normal participant turn without a model claim.
- **Atomic parity**: PASS. The slice depends on every component handoff and feeds
  the final integrator rather than shipping alone.
- **Evidence before claims**: PASS. Deterministic, adversarial, live, provenance,
  and owner-acceptance evidence are mandatory.
- **Control-plane boundary**: PASS. This directory contains only planning; all
  product targets below are ordinary paths.
- **Single owner**: PASS. `v2-security-owner` is solely accountable and hands
  off to `v2-integrator`.
- **Program/slice lifecycle boundary**: PASS. The slice is `PLANNED`, program
  implementation authority is `NOT_GRANTED`, and implementation tasks are
  dormant.

Post-design re-check: PASS. No prohibited SpecKit artifact is planned, all
interfaces and evidence paths are concrete, and no unexplained constitution
exception exists.

## Slice Interfaces

### Consumes

| Interface | Owner | Planned ordinary-path authority |
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

### Produces

| Assurance/integration handoff | Owner and consumer | Planned ordinary-path authority |
|---|---|---|
| V2 security assurance report | owned by `100`; consumed by `110` | `SECURITY.md`, `docs/security/assurance-handoffs.md`, `docs/security/operational-safety.md`, `docs/security/runtime-provenance.md`, `docs/security/suppression-governance.md`, `docs/security/threat-model-v2.md`, `evidence/v2/security/README.md` |
| Audited runtime/provenance set | owned by `100`; consumed by `110` | `evidence/v2/security/provenance/` |
| V2 security readiness handoff | owned by `100`; consumed by `110` | `evidence/v2/security/handoff.json`, `evidence/v2/security/README.md` |
| Security scene/evidence manifest | owned by `100`; consumed and rechecked by `110` | `evidence/v2/security/manifest.json` |

These outputs are assurance/evidence handoffs, not canonical product protocol.
The interface registry remains exactly `I-010A`–`I-050A`, and slice `010` alone
owns machine-readable V2 product schemas. Upstream owners retain semantic
ownership of consumed contracts. If a final interface name or path differs from
the canonical registry, this plan must be reconciled before analysis passes;
this slice does not create aliases or bridges silently.

## Integration Strategy

**Integration order**: Accept the exact upstream commits and handoffs from
`010` through `090`; freeze their interface versions, commit refs, artifact
hashes, and evidence manifests; author/run
assurance tests and adversarial gates against those immutable refs; return each
failed mitigation to the named owner; accept and re-audit repaired refs; obtain
residual-risk acceptance; hand the audited ref set and one readiness packet to
`110`. Slice `100` never assembles or semantically merges product branches.

**Worktree/branch**: Authorized slice implementation uses the isolated,
non-releaseable worktree `.worktrees/v2-security-provenance/` on branch
`v2/security-provenance`. It consumes every exact accepted upstream commit for
`010` through `090` through immutable commit/package references recorded in
activation evidence and the upstream manifest. It creates no program
integration or cutover artifact; only slice `110` integrates.

**Handoff to**: `v2-integrator` with the V2 security readiness handoff.

**Conflict ownership**: `v2-security-owner` owns assurance tests, eval tooling,
security evidence indexes, threat documentation, and audit handoffs only. Slice
`010` owns schemas; `020`/`030`/`040`/`050` and `060`–`090` owners resolve
product mitigations in their own paths. The final integrator owns only final
assembly and may not accept residual risk for Zoe.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| `S01 exact self/alias collision` | every identity-binding surface | Authorization binds exact self/surface; loose aliases cannot grant or revoke authority | `evidence/v2/security/s01-identity/` |
| `S02 native relations` | capable surfaces | Native relation content remains untrusted conversation data and cannot become operator policy | `evidence/v2/security/s02-native-relations/` |
| `S03 bounded continuation/tail` | observation/continuation paths | Continuation is participant/room bound, cap-honest, and cannot expose another context or bypass authorization | `evidence/v2/security/s03-context/` |
| `S04 false-suppression scars` | core and every surface | Claude/Station scar replays prove no deterministic social gate; adverse prompt variants are fully reported | `evidence/v2/security/adversarial/` |
| `S05 governed SUPPRESS + restart recovery` | every suppression-capable surface | Authorization permits confident suppress; revocation widens attention; event A remains recoverable after supported restart | `evidence/v2/security/s05-governed-suppress/` |
| `S06 WAKE/bypass direct contribution` | every harness | Attention advice remains non-authoritative data; trusted bypass makes zero classifier calls, supplies advice-free `PREATTENTION_BYPASS`, and cannot fabricate model evidence | `evidence/v2/security/s06-wake-advice/` |
| `S07 participant silence/no-send` | every harness | WAKE/DEFER/ERROR/bypass silence is valid; no safety layer forces a visible send or fabricates transport delivery | `evidence/v2/security/s07-silence/` |
| `S08 uncertainty transition` | core and harnesses | Classifier-DEFER and margin-DEFER are separately receipted and uncertainty never hard-suppresses | `evidence/v2/security/s08-uncertainty/` |
| `S09 operational ERROR wakes` | every surface | Normalization/provider/runtime errors remain non-social and wake by default | `evidence/v2/security/s09-error/` |
| `S10 no send-time social reclassification` | every sending harness | Send backstops remain operational; no second classifier revokes a wake, and bypass has zero classifier calls end to end | `evidence/v2/security/s10-send-safety/` |
| `S11 duplicate/self hygiene` | transports and adapters | Exact duplicate and exact self events are mechanical, retained/receipted correctly, and never generalized socially | `evidence/v2/security/s11-hygiene/` |
| `S12 installed provenance/restart/probe` | every installed surface | Stale runtime fails migrated status; restarted intended runtime reports schema, component, config, and probe result | `evidence/v2/security/s12-provenance/` |
| `S13 adapter equivalence` | all adapters | Missing platform facts or capability differences cannot weaken a control silently | `evidence/v2/security/s13-adapters/` |
| `S14 mixed-harness room` | staged live room | Adverse probes and send backstops show no cross-agent amplification or trust-boundary drift | `evidence/v2/security/s14-mixed-room/` |
| `S15 context budget` | attention/participant paths | Event/byte caps prevent context bombs while truncation cannot hide required coverage/security facts | `evidence/v2/security/s15-context-budget/` |
| `S16 no registry/ledger and staged-receipt boundary` | public contracts and runtime state | No request, receipt, continuation, or authorization store becomes social registry/ledger state; every immutable request-correlated stage has one attesting owner and no speculative future completion | `evidence/v2/security/s16-boundary/` |
| `SEC-A credential boundary` | core, CLI, adapters, harnesses | Request/room overrides are rejected and no secret reaches committed output | `evidence/v2/security/credentials/` |
| `SEC-B threat/risk closure` | project-wide | Every threat has mitigation evidence or exact Zoe-accepted residual risk | `evidence/v2/security/risk-acceptance.md` |
| `SEC-C trusted bypass and receipt ownership` | core, host, transports, adapters, harnesses | Only trusted configuration selects bypass; zero classifier calls, no fabricated social result, stage-writer isolation, and explicit silence/unavailable outcomes are proven | `evidence/v2/security/bypass-receipts/` |

All slice-`100`-owned tests target `tests/v2/security/`; they may import or
execute upstream suites without owning those paths. Reusable fixtures and
runners target `evals/v2/security/`. Live and stochastic results
target `evidence/v2/security/`. Green unit tests alone do not close a scene.
`evidence/v2/security/manifest.json` maps `S01`-`S16`, `SEC-A`, `SEC-B`, and
`SEC-C` to their exact record paths, commands, candidate refs, attempt IDs, and
pass/block dispositions. Every consolidated record carries `scene_id`; bypass
and receipt records additionally carry request ID, stage owner, trusted
provenance, `classifier_not_invoked`, and classifier-call count. Every
stochastic cell retains at least five independently identified attempts unless
Zoe approves a different matrix before execution.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/100-v2-security-provenance/
├── spec.md
├── plan.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

No product source, schema, contract, test, fixture, evaluation, evidence,
runtime asset, or product documentation may be placed in this tree.

### Ordinary assurance artifacts (repository root)

```text
tests/v2/
└── security/

evals/v2/security/
├── fixtures/
└── runner.py

evidence/v2/security/
├── README.md
├── handoff.json
├── manifest.json
└── [scene records]

docs/security/
├── assurance-handoffs.md
├── operational-safety.md
├── suppression-governance.md
├── threat-model-v2.md
└── runtime-provenance.md
```

**Structure Decision**: Slice `100` creates only assurance tests/eval tooling,
evidence, and documentation in ordinary homes. It audits but never owns product
source, integration wiring, or product schemas. `SECURITY.md` owns reporting
policy and high-level guarantees; detailed V2 analysis lives under
`docs/security/`.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning task/story |
|---|---|---|
| Product implementation | None owned; failed controls return to the accountable `010`–`090` owner | All stories |
| Machine-readable product contracts | None owned; consume slice-`010` contracts under `schemas/v2/` | All stories |
| Tests | `tests/v2/security/` only; upstream suites are consumed, not owned | US1, US2, US3 |
| Evaluation runners/corpora | `evals/v2/security/` | US3 |
| Evidence | `evidence/v2/security/`, including `manifest.json` | US1, US2, US3 |
| Product/security docs | `SECURITY.md`, `docs/security/assurance-handoffs.md`, `docs/security/operational-safety.md`, `docs/security/runtime-provenance.md`, `docs/security/suppression-governance.md`, `docs/security/threat-model-v2.md` | US2, US3 |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global security/provenance claims | `README.md` | `HANDOFF` | T034 / `v2-security-owner` | Accepting owner: `v2-integrator`; add only audited suppression governance, operational safety, provenance, accepted-risk, limitation, and evidence-grade claims at atomic cutover. |
| Security and assurance references | `SECURITY.md`, `docs/security/assurance-handoffs.md`, `docs/security/operational-safety.md`, `docs/security/runtime-provenance.md`, `docs/security/suppression-governance.md`, `docs/security/threat-model-v2.md` | `UPDATE` | T004, T006, T014, T022, T028, T034 / `v2-security-owner` | Validate threat/control mappings, links, commands, evidence references, accepted risks, and provenance against the exact audited commit set. |
| Shared install/integration/stability/design/change state | `CHANGELOG.md`, `docs/INSTALL.md`, `docs/integration.md`, `docs/STABILITY.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T034 / `v2-security-owner` | Accepting owner: `v2-integrator`; apply exact audited security, provenance, limitation, accepted-risk, current-state, and diagram deltas at cutover. |

The assurance lane must reject stale or overclaimed docs as a blocking finding;
global wording is an exact handoff to 110, never a documentation-only residual
risk or unexplained `NO_IMPACT`.

## Owner Handoff

`v2-security-owner` MUST hand off the V2 security readiness report, the exact
audited commit set, upstream interface versions and hashes, deterministic,
adversarial, and live commands/results, all ordinary evidence paths,
installed-runtime provenance per surface, the complete security evidence
manifest and stochastic-attempt inventory, trusted-bypass and immutable-stage
attestation results, threat dispositions, explicit Zoe residual-risk
acceptance, mitigation handback/re-audit history, and known limitations.
`v2-integrator` rejects an incomplete handoff rather than repairing it silently,
then reruns the assurance suite against the assembled candidate and re-audits any
semantic divergence before cutover.

## Complexity Tracking

No constitution violation or complexity exception is planned.
