# Implementation Plan: V2 Claude Code Harness

**Branch**: `v2/claude-code` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/070-v2-claude-code/spec.md`

**Program**: `specs/001-nunchi-v2-program/`

**Accountable owner lane**: `v2-claude-owner`

**Goal authorization**: Goal 1 planning only; product execution awaits explicit Goal 2 authorization

**Upstream dependencies**: `010-v2-contract`, `020-v2-observation`, `030-v2-core-attention`, `040-v2-participant-wake`, `050-v2-discord-transport`

## Summary

Replace the current Claude Code V1 gate with one canonical V2 inbound flow:
reactive Discord event, exact identity, bounded observation, one canonical
attention-engine invocation, one participant-shaped classifier call on ordinary
paths or zero classifier/model calls for trusted preattention bypass, and
zero-or-one normal Claude act-or-silence turn. Retain the
allowlist-aware bot-message patch only with exact upstream provenance and prove
the Station regression, no-polling delivery, no second judgment, later hearing,
and installed-runtime parity.

## Technical Context

**Language/Version**: Python 3.11+ hook/patch support and the Goal 2-supported
Claude Code/plugin runtime

**Primary Dependencies**: existing Nunchi package, Claude Code hook contract,
supported Discord plugin source; no new required product dependency planned

**Storage**: bounded hook/session observation and host/native history only; no
social ledger or per-trigger send permission store

**Testing**: stdlib `unittest`, hook sandbox, native event fixtures, Station
replay corpus, installed plugin live-room scenes

**Target Platform**: Claude Code with the supported Discord room plugin/hook path

**Project Type**: agent-harness plugin and pre-inference hook integration

**Performance Goals**: reactive no-polling receipt, zero participant inference
on effective suppression, one participant inference on every waking route,
zero classifier/model inference on trusted bypass, with cost/latency recorded in
immutable request-correlated receipts

**Constraints**: bot-message allowlist, exact self, bounded packets, advice as
untrusted data, direct-room instruction, evaluation-only meta-answer scoring, no
send-time classifier, trusted bypass only, no fabricated social result, strict
receipt-stage ownership, honest cold-wake limits

**Scale/Scope**: one or more Claude Code participants sharing a Discord room with
humans and other agent families

## Constitution Check

- **PASS — model nuance**: only `I-030A` may socially suppress; Station scars are
  explicit regression scenes.
- **PASS — identity/observation**: exact native actor establishes self and all
  ordinary events remain eligible for later hearing.
- **PASS — participant ownership**: one waking route invokes `I-040A`; Claude
  acts directly or remains silent.
- **PASS — no second judgment**: send is operational only and has no social
  permission state.
- **PASS — atomic parity**: no V1 bridge or mixed Claude request shape is planned.
- **PASS — control plane/owner**: all executable targets are ordinary paths and
  one Claude lane owns them.
- **PASS — evidence/Goal gate**: all product tasks are dormant and installed
  plugin provenance plus live scenes are required.

## Slice Interfaces

### Consumes

- `I-010A AttentionRequestV2@1`
- `I-010B AttentionDecisionV2@1`
- `I-010C ParticipantWakeV2@1`
- `I-010D ContextContinuationV2@1`
- `I-010E AttentionReceiptV2@1`
- `I-020A ObservationProviderV2@1`
- `I-030A AttentionEngineV2@1`
- `I-040A ParticipantTurnHostV2@1`
- `I-050A DiscordEventSourceV2@1`

The canonical machine-readable definitions remain upstream-owned at
`schemas/v2/attention-request.schema.json`,
`schemas/v2/attention-decision.schema.json`,
`schemas/v2/participant-wake.schema.json`,
`schemas/v2/context-continuation.schema.json`, and
`schemas/v2/attention-receipt.schema.json`; this consumer references and never
redefines them.

### Produces

- No new public interface. The slice produces a Claude Code conformance
  implementation and `I-010E` evidence for the canonical registry. It preserves
  the immutable observation/attention/participant-host/transport chain and
  appends no stage unless the Claude integration directly owns and attests that
  execution.
- Installed plugin/patch/hook capability records under
  `evidence/v2/claude-code/`.

## Integration Strategy

**Integration order**: accept `010`–`050`; freeze installed plugin base and
`I-050A` mapping; write failing hook/Station scenes; migrate observation and
attention; migrate participant turn and remove V1/send re-gating; prove live
installed runtime; pass `100`; hand to `110`.

**Worktree/branch**: `.worktrees/v2-claude-code/` on `v2/claude-code`, based
on the accepted foundation plus Discord transport integration commit

**Handoff to**: `v2-security-owner`, then `v2-integrator`

**Conflict ownership**: `v2-claude-owner` alone changes
`integrations/claude-code/` and Claude-specific verification paths;
`v2-transport-owner` owns `I-050A`; foundation owners own shared interfaces;
`v2-integrator` owns cross-harness packaging/integration conflicts.

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| S01/S02/S14/CC-01 reactive bot hearing | Claude Code + Discord | Exact identity/native facts and allowlisted other-bot content arrive via reactive no-polling path | `evidence/v2/claude-code/reactive-bot-hearing.jsonl` |
| S04/S05/CC-02 Station scars | Hook sandbox + replay | Referential mention, other addressee, apparent resolution, and class address have no mechanical suppressor; suppression is governed | `evidence/v2/claude-code/scene-results.jsonl` (`scene_id=CC-02`) |
| S06–S10/CC-03 attention routing | Hook sandbox | Every routable trigger invokes the engine once; ordinary paths make one logical classifier call while trusted bypass makes zero and records `classifier_not_invoked`; zero/one participant turn and classifier/host/participant outcomes remain separate | `evidence/v2/claude-code/scene-results.jsonl` (`scene_id=CC-03`) |
| S06/S07/S10/S16/CC-04 direct act-or-silence | Live Claude room | WAKE or advice-free `PREATTENTION_BYPASS` invokes one normal turn; message/reaction/tool or silence addresses the room; post-hoc evaluation flags meta-answer while runtime has no prose filter, send re-gate, social ledger, fabricated social result, or cross-owner receipt mutation | `evidence/v2/claude-code/scene-results.jsonl` (`scene_id=CC-04`) |
| S03/S05/S15/CC-05 later hearing/restart | Claude transport/history | Earlier suppressed event remains available within bounded honest coverage and capability | `evidence/v2/claude-code/scene-results.jsonl` (`scene_id=CC-05`) |
| S12/CC-06 installed provenance | Installed Claude plugin/hook | Exact plugin base, patch, hook, Claude/Nunchi/model/config/interface versions accompany probe | `evidence/v2/claude-code/installed-runtime.md` |

Tests belong at `tests/v2/test_claude_code.py`, fixtures at
`tests/fixtures/v2/claude_code/`, and replay at `evals/v2/claude_code/`.

`evidence/v2/claude-code/manifest.json` maps every `CC-*` and applicable `S*`
ID to its exact record, command, candidate commit, and result. Consolidated JSONL
is valid only when each row carries its stable `scene_id`; bypass/receipt rows
also carry request ID, stage owner, trusted bypass provenance, and
`classifier_not_invoked`. Meta-answer scoring is post-hoc acceptance evaluation
and never a runtime output filter.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/070-v2-claude-code/
├── spec.md
├── plan.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
integrations/claude-code/
tests/v2/test_claude_code.py
tests/fixtures/v2/claude_code/
evals/v2/claude_code/
evidence/v2/claude-code/
  manifest.json
docs/integrations/claude-code-v2.md
```

**Structure Decision**: evolve the current Claude Code hook and reviewed
transport patch in place; keep all evidence out of `integrations/` and all
product artifacts out of `specs/`.

## Ordinary Repository Targets

| Artifact class | Goal 2 target path(s) | Owning story |
|---|---|---|
| Product implementation | `integrations/claude-code/` | US1–US3 |
| Shared contracts | consume `schemas/v2/`; no Claude-owned public schema | US1–US3 |
| Tests and fixtures | `tests/v2/test_claude_code.py`, `tests/fixtures/v2/claude_code/` | US1–US3 |
| Evaluation | `evals/v2/claude_code/` | US2–US3 |
| Evidence | `evidence/v2/claude-code/`, including `manifest.json` | US1–US3 |
| Product docs | `docs/integrations/claude-code-v2.md` | US3 |

## Documentation Impact and Freshness

| Claim surface | Reviewed ordinary path(s) | Disposition | Owning task/lane | Validation or exact handoff delta |
|---|---|---|---|---|
| Global Claude support/evidence state | `README.md` | `HANDOFF` | T016 / `v2-claude-owner` | Accepting owner: `v2-integrator`; replace V1 hook/patch claims with exact reactive/cold-wake capability, single-judgment lifecycle, provenance, limits, and evidence grade at atomic cutover. |
| Claude Code V2 and existing operator docs | `docs/integrations/claude-code-v2.md`, `integrations/claude-code/README.md`, `integrations/claude-code/DEFER_EVAL.md`, `integrations/claude-code/transport-patch/README.md` | `UPDATE` | T007, T016 / `v2-claude-owner` | Validate install/config, dual-DEFER meaning, patch base/digest, restart, links, examples, and probes against the exact installed candidate. |
| Shared install/integration/adapter/design/change state | `CHANGELOG.md`, `docs/INSTALL.md`, `docs/adapters.md`, `docs/integration.md`, `docs/architecture/v2-selected-design.md` | `HANDOFF` | T016 / `v2-claude-owner` | Accepting owner: `v2-integrator`; apply the exact breaking Claude lifecycle, installation/residue, evidence-grade, limitation, and diagram delta at cutover. |

The owned guide/provenance docs update in this lane; root current-state wording
is an exact handoff to 110, not `NO_IMPACT`.

## Owner Handoff

The owner supplies exact commit, verification commands/results, consumed
interface versions, upstream plugin base and patch digest, installed hook/plugin/
Claude/Nunchi/model/config provenance, reactive/cold-wake capability, trusted
bypass zero-classifier-call proof, immutable receipt-stage ownership, all scene evidence,
CC-01 through CC-06 manifest coverage, effective limits, and known limitations. The final integrator may
reject source-green work without the installed live-room record.

## Complexity Tracking

No constitution violation or complexity exception is planned.
