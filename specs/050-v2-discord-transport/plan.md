# Implementation Plan: V2 Discord Transport

**Branch**: `v2/discord-transport` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Existing slice specification from `specs/050-v2-discord-transport/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-transport-owner`

**Assigned participant / source**: devops — evidence/governance/assignments/devops-v2-transport-owner-2026-07-16.md

**SpecKit binding**: planning uses `python3 scripts/run_slice_workflow.py run nunchi-plan specs/050-v2-discord-transport`; delivery uses `python3 scripts/run_slice_workflow.py run speckit specs/050-v2-discord-transport`

**Read-only preflight**: performed atomically by the bound runner above; a paused run with an unchanged task graph resumes only with `python3 scripts/run_slice_workflow.py resume <run-id>`

**Slice state**: `PLANNED`

**Program implementation authority**: `NOT_GRANTED`

**Activation evidence**: `evidence/v2/discord-transport/slice-activation.md`
(written only after every readiness prerequisite is accepted; it attests those
facts and establishes `READY` before `ACTIVE`)

**Candidate evidence**: `evidence/v2/discord-transport/slice-candidate.md` (for
`CONVERGED`; absent while `PLANNED`)

**Handoff evidence**: `evidence/v2/discord-transport/slice-handoff.md` (for
`HANDOFF_READY`; absent while `PLANNED`)

**Acceptance evidence**: `evidence/v2/discord-transport/slice-acceptance.md`
(for `ACCEPTED`; absent while `PLANNED`)

**Upstream dependencies**: `010-v2-contract`, `020-v2-observation`

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

Cut the existing Discord gateway/MCP surface over to the V2 factual event and
bounded-continuation contract. Preserve bot-authored messages, exact native
relations, authoritative order, restart/backfill truth, operational send safety,
and runtime provenance while excluding every deterministic social inference.
This planning baseline creates no product behavior.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: existing optional Discord and MCP runtime dependencies;
Discord Gateway and REST APIs; no new required product dependency

**Storage**: bounded in-process observation plus native Discord history; any
restart checkpoint is operational state, never social memory

**Testing**: stdlib `unittest`, deterministic native-event fixtures, replay
evaluation, and bounded live Discord probes

**Target Platform**: long-running Discord gateway/MCP process on supported
Nunchi hosts

**Project Type**: Python package integration and MCP transport

**Performance Goals**: reactive delivery without polling; live evidence records
delivery latency and context byte/event sizes rather than asserting an unproven
global threshold

**Constraints**: privileged message-content capability where required; bot token
outside schemas; exact-self binding; hard event/byte caps; wake-source-agnostic
actions with zero transport/send-path classifier calls; immutable singly written
transport receipt stage; no semantic filter

**Scale/Scope**: one configured bot identity across its explicitly allowlisted
Discord rooms, with multiple human and bot actors per room

## Constitution Check

- **PASS — selected boundary**: transport supplies facts and continuity; it does
  not decide `SUPPRESS`, `WAKE`, or `DEFER`.
- **PASS — human-shaped judgment**: no mention/reply/resolution heuristic is
  planned.
- **PASS — truthful identity**: exact Discord IDs establish self and authorship;
  display names do not.
- **PASS — control plane**: all future executable artifacts target ordinary
  paths; this directory remains planning-only.
- **PASS — single owner**: `v2-transport-owner` owns all Discord-specific source
  files; slice `010` alone owns every machine-readable V2 schema.
- **PASS — slice lifecycle**: tasks remain `DORMANT` while the slice is
  `PLANNED`.
- **PASS — evidence**: deterministic, restart/backfill, security, and installed
  live records are required before handoff.

## Slice Interfaces

### Consumes

- `I-010A AttentionRequestV2@1` from slice `010`, planned under
  `schemas/v2/attention-request.schema.json`.
- `I-010D ContextContinuationV2@1` from slice `010`, planned under
  `schemas/v2/context-continuation.schema.json`.
- `I-010E AttentionReceiptV2@1` from slice `010`, planned under
  `schemas/v2/attention-receipt.schema.json`; this slice may append only its
  immutable request-correlated `transport` stage.
- `I-020A ObservationProviderV2@1` from slice `020`, planned under
  `src/nunchi/observation.py`.

### Produces

- `I-050A DiscordEventSourceV2@1` event, history, and continuity source for
  slices `070`, `080`, `100`, and `110`, planned under
  `src/nunchi/mcp_discord/`.
- Discord observation source and continuation provider under
  `src/nunchi/mcp_discord/`.
- Capability/provenance records under `evidence/v2/discord-transport/`.
- Transport-attested I-010E stages for delivery, rejection, rate limit, retry, or
  operational failure; no observation, attention, or participant-host stage.

Machine-readable shared V2 types remain owned by slice `010`; this owner may
not redefine them or create a parallel surface schema. Operational send actions
remain implementation/safety outside the `I-050A` event-source contract.

## Integration Strategy

**Integration order**: accept frozen `010` schemas and `020` collector seam;
land Discord-specific contract/tests; implement receive and continuity; implement
send tools; hand off to Claude Code and Codex; pass assurance `100`; integrate in
`110`.

**Worktree/branch**: `.worktrees/v2-discord-transport/` on
`v2/discord-transport` is an isolated, non-releaseable slice worktree that
consumes the exact accepted upstream commits for `010` and `020` recorded in
activation evidence. It creates no program integration or cutover artifact;
only slice `110` integrates.

**Handoff to**: `v2-claude-owner`, `v2-codex-owner`,
`v2-security-owner`, then `v2-integrator`

**Conflict ownership**: `v2-contract-owner` alone changes shared V2 schemas;
`v2-transport-owner` alone changes `src/nunchi/mcp_discord/` and its unique
verification paths; `v2-integrator` owns shared packaging conflicts.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01/S02/DT-01 bot-authored delivery | Discord gateway/MCP | Authorized other-bot content and native relations are delivered; exact self is retained but not self-woken | `evidence/v2/discord-transport/scene-results.jsonl` (`scene_id=DT-01`) |
| S04/S11/DT-02 hygiene boundary | Discord gateway | Exact duplicate/self/unroutable cases are mechanical; referential mention and apparent resolution are not filtered | `evidence/v2/discord-transport/scene-results.jsonl` (`scene_id=DT-02`) |
| S03/S05/S15/DT-03 restart recovery | Gateway resume, REST history | Native IDs deduplicate, order survives, budgets hold, and recoverability is truthful | `evidence/v2/discord-transport/scene-results.jsonl` (`scene_id=DT-03`) |
| S03/S15/DT-04 bounded expansion | History/continuation | Before/around fetch remains bound and under declared caps with honest gaps | `evidence/v2/discord-transport/scene-results.jsonl` (`scene_id=DT-04`) |
| S06/S07/S10/S16/DT-05 operational actions and upstream bypass preservation | MCP send/reply/react/history | Trusted authorization and rate limits apply without social reclassification; action handling is wake-source-agnostic and has zero transport/send-path classifier calls; an upstream bypass attention stage is preserved rather than interpreted; transport writes only its immutable stage and no delivery outcome for participant silence | `evidence/v2/discord-transport/scene-results.jsonl` (`scene_id=DT-05`) |
| S12/S13/DT-06 installed probe | Deployed transport | Exact source/package/config provenance accompanies a live V2 receive/send probe and capability matrix | `evidence/v2/discord-transport/installed-runtime.md` |
| S14/DT-07 mixed-actor source | Installed Discord source with harness-independent Hermes/Claude/Codex/human actor probes | One shared Discord source delivers all authorized actor events without filtering peer agents; final participant behavior remains owned by `110` | `evidence/v2/discord-transport/mixed-room.jsonl` |

Deterministic coverage belongs in `tests/v2/test_discord_transport.py`; native
fixtures belong in `tests/fixtures/v2/discord/`; reusable replay belongs in
`evals/v2/discord_transport/`.

`evidence/v2/discord-transport/manifest.json` is the authoritative evidence
map. It maps each `DT-*` ID and applicable `S*` IDs to the exact record path,
candidate commit, command, and result; a consolidated JSONL record is valid only
when every row carries its stable `scene_id` and bypass/receipt cases identify
the immutable upstream attention-stage reference, zero transport/send-path
classifier-call count, request correlation, stage owner, and the singly written
transport stage without re-attesting upstream classifier facts.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/050-v2-discord-transport/
├── spec.md
├── plan.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/nunchi/mcp_discord/
tests/v2/test_discord_transport.py
tests/fixtures/v2/discord/
evals/v2/discord_transport/
evidence/v2/discord-transport/
  manifest.json
docs/integrations/discord-mcp-v2.md
```

**Structure Decision**: evolve the existing `src/nunchi/mcp_discord/` package;
keep surface-specific fixtures, replay, evidence, and docs in unique
ordinary paths so parallel harness lanes do not collide.

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning story |
|---|---|---|
| Product implementation | `src/nunchi/mcp_discord/` | US1–US3 |
| Shared contracts | consume slice `010` files under `schemas/v2/`; no transport-owned schema | US1–US2 |
| Tests and fixtures | `tests/v2/test_discord_transport.py`, `tests/fixtures/v2/discord/` | US1–US3 |
| Evaluation | `evals/v2/discord_transport/` | US1–US2 |
| Evidence | `evidence/v2/discord-transport/`, including `manifest.json` | US1–US3 |
| Product docs | `docs/integrations/discord-mcp-v2.md` | US3 |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global Discord capability/status | `README.md` | `HANDOFF` | T017 / `v2-transport-owner` | Accepting owner: `v2-integrator`; replace historical/source-only claims with exact installed V2 capabilities, limitations, restart evidence, and proof tier at atomic cutover. |
| Discord-MCP V2 guide | `docs/integrations/discord-mcp-v2.md` | `UPDATE` | T017 / `v2-transport-owner` | Validate install commands, native capability truth, restart/continuation claims, links, and probes against installed provenance. |
| Existing Discord-MCP operator/design docs | `integrations/mcp-discord/README.md`, `integrations/mcp-discord/DESIGN.md` | `UPDATE` | T017 / `v2-transport-owner` | Validate native facts, exact-self, gaps/budgets, continuation, actions, receipts, restart, install provenance, links, and probes against I-050A. |
| Shared change/adapter/design status | `CHANGELOG.md`, `docs/adapters.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T017 / `v2-transport-owner` | Accepting owner: `v2-integrator`; apply the exact breaking-change, installed Discord capability, limitation, evidence-grade, and diagram delta at cutover. |
| Downstream peer-hearing/Codex transport wording | `integrations/claude-code/transport-patch/README.md`, `integrations/codex/README.md` | `HANDOFF` | T017 / `v2-transport-owner` | Accepting owner: `v2-claude-owner` and `v2-codex-owner`; apply the exact peer-hearing, native-event, action-capability, and transport-provenance delta. |

The transport owner updates its guide and hands global status wording to 110;
neither row may be closed by a bare `NO_IMPACT` claim.

## Owner Handoff

The owner hands off the exact commit, commands and results, `I-050A
DiscordEventSourceV2@1`, Discord capability matrix, deterministic and live evidence paths,
installed process provenance, manifest coverage for DT-01 through DT-07,
wake-source-agnostic action/zero-send-time-classifier evidence, unchanged
upstream-bypass receipt proof, receipt-stage writer ownership,
effective limits, credential-source description, restart/recoverability claim,
and known limitations. Review does not transfer ownership silently.

## Complexity Tracking

No constitution violation or complexity exception is planned.
