---
description: "Future Goal 2 task plan for the V2 Discord transport"
---

# Tasks: V2 Discord Transport

**Execution status**: DORMANT. These tasks describe future Goal 2 work and MUST
NOT be executed under the current Goal 1.

**Input**: `specs/050-v2-discord-transport/spec.md` and `plan.md`

**Prerequisites**: explicit Goal 2 authorization; accepted `010` and `020`
handoffs; zero CRITICAL/HIGH analysis findings; isolated owner worktree

**Accountable owner lane**: `v2-transport-owner`

**Integration handoff**: `v2-claude-owner`, `v2-codex-owner`,
`v2-security-owner`, then `v2-integrator`

## Phase 1: Conformance and fixture setup

- [ ] T001 Add failing `I-050A DiscordEventSourceV2@1`, wake-source-agnostic action, immutable upstream-receipt preservation, request-correlated I-010E transport-stage ownership, and accepted upstream-version assertions in `tests/v2/test_discord_transport.py`
- [ ] T002 Add failing native-fact coverage for human, bot, reply, thread, mention, reaction, and missing-capability cases in `tests/v2/test_discord_transport.py`
- [ ] T003 [P] Add native Discord fixture families, including exact duplicate and exact-self cases, in `tests/fixtures/v2/discord/`

**Checkpoint**: `I-050A` expectations are reviewed without changing or copying
shared schemas owned by slice `010`.

## Phase 2: User Story 1 - Hear authorized Discord facts (Priority: P1)

**Goal**: deliver transport-attested native facts without semantic filtering.

**Independent Test**: the US1 fixture subset fails before implementation and
passes only when human and other-bot facts survive normalization unchanged.

- [ ] T004 [US1] Add failing gateway-order, bot-delivery, and native-relation tests in `tests/v2/test_discord_transport.py`
- [ ] T005 [US1] Implement V2 Discord native event construction and ordering in `src/nunchi/mcp_discord/events.py`
- [ ] T006 [US1] Restrict deterministic duplicate, self-no-wake, authorization, and unroutable hygiene in `src/nunchi/mcp_discord/hygiene.py`
- [ ] T007 [US1] Publish versioned reactive Discord notifications without credential leakage in `src/nunchi/mcp_discord/server.py`
- [ ] T008 [US1] Record referential-mention and apparent-resolution regression replay cases in `evals/v2/discord_transport/scenes.jsonl`

**Checkpoint**: DT-01 and DT-02 pass deterministically with no social rule in the
transport.

## Phase 3: User Story 2 - Preserve bounded continuity (Priority: P1)

**Goal**: expose truthful bounded observation, restart/backfill, and expansion.

**Independent Test**: restart and context-boundary fixtures prove order,
deduplication, binding, gaps, and hard budgets.

- [ ] T009 [US2] Add failing restart, backfill, unresolved-relation, and hard-budget tests in `tests/v2/test_discord_transport.py`
- [ ] T010 [US2] Implement gateway resume and restart coverage reporting in `src/nunchi/mcp_discord/gateway.py`
- [ ] T011 [US2] Implement bounded native-history and continuation fulfillment in `src/nunchi/mcp_discord/rest.py`
- [ ] T012 [US2] Integrate the shared observation source without a roster or social ledger in `src/nunchi/mcp_discord/runner.py`
- [ ] T013 [US2] Add restart and suppressed-event-later-heard replay scenarios in `evals/v2/discord_transport/recovery.jsonl`

**Checkpoint**: DT-03 and DT-04 establish only the recoverability level actually
proved by the transport.

## Phase 4: User Story 3 - Send operationally (Priority: P2)

**Goal**: expose safe participant actions with no second social judgment.

**Independent Test**: action tests cover allowlists, rate limits, malformed
routing, credential isolation, and the absence of a classifier call.

- [ ] T014 [US3] Add failing send/reply/react/history authorization, rate-limit, wake-source/social-result input rejection, zero transport/send-path classifier calls, unchanged upstream-bypass-stage, participant-silence-no-delivery, request-correlation, and immutable single-writer transport-stage tests in `tests/v2/test_discord_transport.py`
- [ ] T015 [US3] Implement V2 send, reply, reaction, and bounded-history tools plus only transport-attested immutable I-010E stage append in `src/nunchi/mcp_discord/tools.py`
- [ ] T016 [US3] Keep rate-limit and retry handling operational, wake-source-agnostic, and off-surface without fabricating social results or mutating observation/attention/participant-host stages in `src/nunchi/mcp_discord/ratelimit.py`
- [ ] T017 [US3] Complete documentation freshness by executing every exact row in `plan.md` §Documentation Impact and Freshness; validate the new and existing Discord-MCP `UPDATE` paths, route each shared/downstream `HANDOFF` delta (including `README.md`) to its accepting owner, and record all documentation dispositions, paths, results, and reviewer in `evidence/v2/discord-transport/handoff.md`

**Checkpoint**: DT-05 passes without pre-attention or per-trigger permission
state in the send path.

## Phase 5: Evidence and handoff

- [ ] T018 Run and commit DT-01 through DT-05 records, including mandatory S06/S07/S10 actions correlated to unchanged upstream bypass stages and immutable transport-stage cases, each with stable `scene_id`, request ID, transport stage owner, upstream-stage reference/hash, zero transport/send-path classifier-call count, and applicable S IDs, in `evidence/v2/discord-transport/scene-results.jsonl` without re-attesting upstream bypass provenance
- [ ] T019 Record exact installed commit/package, process configuration, restart, and live receive/send probe in `evidence/v2/discord-transport/installed-runtime.md`
- [ ] T020 Run DT-07 against the exact installed shared Discord source using harness-independent transport-attested Hermes, Claude Code, Codex, and human actor probes, then commit peer-delivery and no-filter evidence in `evidence/v2/discord-transport/mixed-room.jsonl` without depending on downstream harness implementations
- [ ] T021 Map DT-01 through DT-07 and applicable S IDs to exact records, commands, candidate commit, request ID, transport stage owner, immutable upstream-stage reference, transport/send-path classifier-call count, and result in `evidence/v2/discord-transport/manifest.json`
- [ ] T022 Hand off interface version, commit, commands/results, manifest, evidence, capability limits, documentation dispositions/validation/reviewer, and known gaps in `evidence/v2/discord-transport/handoff.md` only after documentation freshness passes

## Dependencies & Execution Order

- T001–T003 require accepted `010` and `020` interfaces.
- US1 begins after T001–T003; US2 may begin after the shared event construction
  in T005; US3 may begin after T001 and trusted routing are stable.
- Local evidence and T022 handoff require all story checkpoints, DT-07, and the
  complete evidence manifest, then
  feed slice `100`; only final migration/cutover acceptance waits for assurance.
- Slices `070` and `080` consume only the explicit T022 handoff, never an
  uncommitted transport worktree.

## Parallel Opportunities

- T003 fixture authoring can proceed independently once upstream versions are pinned.
- US1 fixture/replay authoring may proceed alongside implementation after the
  contract freezes.
- US3 tests can be prepared while US2 continuity work proceeds because they
  target different modules.

## Implementation Strategy

Implement transport facts first, continuity second, and participant actions
third. Stop after each checkpoint for owner review. Do not claim social quality
from transport tests, and do not merge into the atomic V2 cutover until the
assurance and parity owners accept the handoff.
