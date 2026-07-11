# Implementation Plan: Nunchi V2 End-to-End Parity

**Branch**: `chore/v2-execution-spine` | **Date**: 2026-07-11 | **Spec**: `spec.md`

**Input**: The selected Aleph Vault technical design at latest authority merge `c834e8c` (selection `bdd1ebb`, clarification PR 68)
and the requirements in this program specification.

**Program**: `001-nunchi-v2-program`

**Accountable owner lane**: `v2-program-owner`

**Goal authorization**: Goal 1 planning only; Goal 2 is not authorized

**Upstream dependencies**: Aleph Vault `c834e8c`; Constitution 2.1.0; the
ordinary-path V1 inventory and evidence baseline

## Summary

Prepare one implementation-ready V2 program without changing V2 product
behavior. The program fixes interface ownership in slice `010`, separates
truthful observation (`020`) from model pre-attention (`030`), joins them in the
normal participant-turn host (`040`), and then integrates transport, harness,
and adapter surfaces through independently owned lanes. Security/provenance
(`100`) audits every implementation lane, and parity/cutover (`110`) is the sole
final sink and integration owner.

The future product cutover is deliberately breaking and atomic. It replaces the
current V1 `PASS / ACK / ASK / SPEAK` lifecycle with participant-shaped
`SUPPRESS / WAKE / DEFER`, separate operational `ERROR`, compact factual
context, optional participant-owned expansion, and a direct act-or-silence
participant turn. It does not add a V1 bridge, a social ledger, or a send-time
social reclassification.

## Technical Context

**Language/Version**: Python `>=3.11`, matching `pyproject.toml`

**Primary Dependencies**: zero required runtime dependencies for the shared
core; existing optional surface dependencies remain surface-owned. Goal 2 may
change an optional dependency only through its owning slice and the integrator.

**Storage**: bounded in-memory or native-history-backed observation continuity;
no participant registry, social ledger, or obligation store

**Testing**: Python `unittest`, deterministic contract/integration tests,
committed replay corpora, live acceptance scenes, and installed-runtime probes

**Target Platform**: Python library and CLI; Hermes, Claude Code, Codex,
Discord-MCP, and in-tree standalone channel adapters

**Project Type**: library + CLI + adapter/harness integrations

**Performance Goals**: hard event/byte budgets on attention and participant
packets; receipts expose serialized bytes and model-specific token estimates;
defaults are selected from replay evidence rather than asserted here

**Constraints**: one logical pre-attention judgment; only a participant-shaped
model may socially suppress; uncertainty widens waking; exact transport facts
only for deterministic non-events; no send-time social classifier; operational
error wakes by default; no mixed V1/V2 in-tree state

**Scale/Scope**: eleven independently owned slices, nine canonical interfaces,
sixteen common acceptance scenes, and one final integration sink

## Constitution Check

*GATE: passed for Goal 1 planning; MUST be re-checked before Goal 2 and at every
slice handoff.*

| Principle | Program proof | State |
|---|---|---|
| I. Selected V2 boundary | The program plans pre-attention and direct participant turns without reply composition or floor allocation. | PASS |
| II. Human-shaped judgment | Only `I-030A` may issue social suppression; deterministic transport work is limited to exact non-events. | PASS |
| III. Truthful identity/observation | `020` owns exact self binding, native relations, bounded coverage, and honest continuation. | PASS |
| IV. Different owners | `030` decides attention; `040` invokes a normal participant turn; no send reclassification is planned. | PASS |
| V. Atomic parity | `110` is the sole cutover sink and rejects mixed V1/V2 consumers or translation bridges. | PASS |
| VI. Evidence before claims | Every slice binds shared scenes to deterministic, replay, live, and provenance evidence as appropriate. | PASS |
| VII. Control-plane only | This tree contains planning Markdown only; all future product artifacts target ordinary repository paths. | PASS |
| VIII. Single-owner slices | Each slice has one stable owner lane, explicit edges, isolated work, and an integrator handoff. | PASS |
| Documentation freshness | Every slice reviews `README.md`, updates owned docs, hands exact shared claim deltas to 110, and must pass a post-convergence reviewer gate. | PASS |

No constitutional violation or complexity exception is accepted.

## Dependency Graph and Execution Waves

```text
Wave 0: 010 contract
              |
Wave 1: 020 observation -----+----- 030 core attention
              |              |              |
Wave 2:       +---------- 040 participant wake
              |
              +---------- 050 Discord transport
                             |
Wave 3: 060 Hermes   070 Claude Code   080 Codex   090 adapters
              \             |              |          /
Wave 4:                       100 security/provenance
                                           |
Wave 5:                              110 parity/cutover
```

The drawing is explanatory; the table below is normative.

| Slice | Accountable owner | Hard dependencies | Feeds |
|---|---|---|---|
| `010-v2-contract` | `v2-contract-owner` | none | `020`–`110` |
| `020-v2-observation` | `v2-observation-owner` | `010` | `040`–`110` |
| `030-v2-core-attention` | `v2-core-owner` | `010` | `040`, `060`–`110` |
| `040-v2-participant-wake` | `v2-wake-owner` | `010`, `020`, `030` | `060`–`110` |
| `050-v2-discord-transport` | `v2-transport-owner` | `010`, `020` | `070`, `080`, `100`, `110` |
| `060-v2-hermes` | `v2-hermes-owner` | `010`, `020`, `030`, `040` | `100`, `110` |
| `070-v2-claude-code` | `v2-claude-owner` | `010`, `020`, `030`, `040`, `050` | `100`, `110` |
| `080-v2-codex` | `v2-codex-owner` | `010`, `020`, `030`, `040`, `050` | `100`, `110` |
| `090-v2-channel-adapters` | `v2-adapters-owner` | `010`, `020`, `030`, `040` | `100`, `110` |
| `100-v2-security-provenance` | `v2-security-owner` | `010`–`090` | `110` |
| `110-v2-parity-cutover` | `v2-integrator` | `010`–`100` | final Goal 2 acceptance |

`020` and `030` may run in parallel after `010`. `040` and `050` may overlap
only after their listed dependencies. The four surface lanes in Wave 3 may run
in parallel in separate worktrees. `100` audits landed slice handoffs; it does
not silently co-own their implementations. `110` is the only final sink.

## Interface Registry

Interface names and versions below are canonical planning identities. Slice
`010` creates their machine-readable forms under `schemas/v2/` during Goal 2.
No control-plane file is a product contract.

| ID | Interface | Owning slice | Named consumers / purpose | Planned ordinary home |
|---|---|---|---|---|
| `I-010A` | `AttentionRequestV2@1` | `010` | `020`, `030`, `050`–`110` | `schemas/v2/attention-request.schema.json` |
| `I-010B` | `AttentionDecisionV2@1` | `010` | `030`, `040`, `060`–`110`; `status: ok` carries `SUPPRESS`, `WAKE(advice)`, or `DEFER`; trusted `status: bypass` carries only `preattention-disabled`; `ERROR` remains separate | `schemas/v2/attention-decision.schema.json` |
| `I-010C` | `ParticipantWakeV2@1` | `010` | `040`, `060`–`110`; includes `PREATTENTION_BYPASS` without classifier/effective disposition | `schemas/v2/participant-wake.schema.json` |
| `I-010D` | `ContextContinuationV2@1` | `010` | `020`, `040`, `050`–`110`; host-only handle/binding plus request/page forms; classifier sees coverage/capability booleans only | `schemas/v2/context-continuation.schema.json` |
| `I-010E` | `AttentionReceiptV2@1` | `010` | `020`–`110`; immutable request-correlated observation, attention, participant-host, and transport stage union; each owner appends only its own off-surface record | `schemas/v2/attention-receipt.schema.json` |
| `I-020A` | `ObservationProviderV2@1` | `020` | `040`–`110`; native events to bounded `I-010A` plus continuation | `src/nunchi/observation.py` |
| `I-030A` | `AttentionEngineV2@1` | `030` | `040`, `060`–`110`; callable core + CLI implementing `I-010A/B/E`, zero-call trusted bypass, classifier-safe projection, and the dual-valve transition | `src/nunchi/core.py`, `src/nunchi/cli.py` |
| `I-040A` | `ParticipantTurnHostV2@1` | `040` | `060`–`110`; wake, expansion, direct act-or-silence, no send reclassification | `src/nunchi/participant.py` |
| `I-050A` | `DiscordEventSourceV2@1` | `050` | `070`, `080`, `100`, `110`; Discord native observation and continuity | `src/nunchi/mcp_discord/` |

Public schemas MUST reject reply prose, inferred social-state fields, alias-based
self identity, and any successful transition outside the selected response
matrix. A change to `I-010*` belongs to `v2-contract-owner`; a consumer proposes
and waits for a versioned handoff rather than forking the contract.

## Integration Strategy

**Integration order**: contract schemas/tests (`010`) land first; observation
and core attention land after consuming that exact version; participant wake and
shared Discord transport land next; harness/adapter lanes consume those
handoffs; security/provenance audits exact candidate commits; `v2-integrator`
assembles all accepted commits, runs parity, replaces truthful docs, and performs
one atomic V2 cutover.

**Worktree/branch**: each Goal 2 lane uses `.worktrees/v2-<slice>/` and branch
`v2/<slice>`. Shared assembly uses `.worktrees/v2-integration/` and
`integration/v2`. Main remains V1 until the final accepted cutover.

**Handoff to**: foundation owners hand to every named dependent and
`v2-integrator`; surface owners hand to `v2-security-owner` and
`v2-integrator`; assurance hands its blocking report to `v2-integrator`.

**Conflict ownership**: `010` alone owns `schemas/v2/`; each implementation lane
owns only the files named in its plan; `110` alone owns cross-surface fixtures,
cutover choreography, public current-state documentation, and the final
integration conflict resolution. A needed shared-file edit is requested from
its owner and handed back as a commit.

**Atomicity**: lane branches may be green independently, but no surface is
called migrated and no partial V2 state lands on main. The integration branch
must contain all in-tree consumers on one contract before acceptance.

## Common Acceptance Scenes and Evidence

The catalog is normative. Slice plans may add surface-specific scenes but may
not redefine these outcomes. Reusable inputs live under `evals/v2/`; executable
checks under `tests/v2/`; run records under `evidence/v2/`.

| Scene | Required outcome | Responsible slices | Final evidence target |
|---|---|---|---|
| `S01` Exact self and alias collision | Exact transport/host binding establishes self; a loose alias collision never establishes authorship. | `010`, `020`, `050`, `060`–`090`, `100`, `110` | `evidence/v2/parity/s01-identity/` |
| `S02` Native relations | Mentions, replies, reactions, membership, and unavailable capability remain literal, structured, and truthful. | `010`, `020`, `050`, `060`–`100`, `110` | `evidence/v2/parity/s02-native-relations/` |
| `S03` Bounded context and tail | Trigger, relation closure, caps, gaps, continuation, and already-observed post-trigger events behave honestly. | `010`, `020`, `040`, `050`–`100`, `110` | `evidence/v2/parity/s03-context/` |
| `S04` False-suppression scars | Referential mention, other addressee, apparent resolution, and class address never meet a deterministic social suppressor. | `020`, `030`, `050`–`100`, `110` | `evidence/v2/parity/s04-suppression-scars/` |
| `S05` Governed suppression | `SUPPRESS` requires enabled, inspectable, revocable delegation and proven recoverability including restart/backfill. | `010`, `020`, `030`, `050`–`100`, `110` | `evidence/v2/parity/s05-governed-suppress/` |
| `S06` WAKE/bypass contribution | A model `WAKE` or trusted `PREATTENTION_BYPASS` delivers a normal turn and the participant emits its actual room action, not an admission answer; bypass makes no model claim. | `010`, `030`, `040`, `060`–`100`, `110` | `evidence/v2/parity/s06-wake-act/` |
| `S07` Participant silence | `WAKE`, `DEFER`, preattention bypass, and error fallback may validly end with no room send. | `010`, `040`, `060`–`100`, `110` | `evidence/v2/parity/s07-silence/` |
| `S08` Dual DEFER valves | Classifier-DEFER and margin-DEFER are distinct, receipted, live in one direction of safety, and the margin retires only on evidence. | `010`, `030`, `060`–`100`, `110` | `evidence/v2/parity/s08-defer-transition/` |
| `S09` Operational error | Validation/provider/runtime failures remain `ERROR` and wake by default without fabricating a social verdict. | `010`, `030`, `040`, `060`–`100`, `110` | `evidence/v2/parity/s09-error-fallback/` |
| `S10` No send-time social gate | Participant action reaches operational send safety without another room judgment or social permission registry. | `040`, `060`–`100`, `110` | `evidence/v2/parity/s10-single-judgment/` |
| `S11` Transport hygiene | Exact duplicate, exact self event, and unroutable payload are the only deterministic no-wake classes and remain observable. | `020`, `050`, `090`, `100`, `110` | `evidence/v2/parity/s11-transport-hygiene/` |
| `S12` Installed provenance | Exact commit/wheel/config/process identity, restart/reload, retired residue removal, and a schema-2 probe are proven per surface. | `050`–`110` | `evidence/v2/provenance/` |
| `S13` Adapter equivalence | Equivalent available native facts normalize and route equivalently; genuine platform absence stays explicit. | `020`, `050`, `090`, `100`, `110` | `evidence/v2/parity/s13-adapters/` |
| `S14` Mixed-harness room | Hermes, Claude Code, and Codex share a room without all-talk, all-mute, polling dependence, or lifecycle drift. | `050`–`100`, `110` | `evidence/v2/live/s14-mixed-room/` |
| `S15` Context budget | Attention and participant packets respect independent byte/event caps without a full-history context bomb. | `010`, `020`, `040`, `050`–`100`, `110` | `evidence/v2/parity/s15-context-budget/` |
| `S16` No registry or ledger | Public boundaries, buffers, continuations, immutable receipt stages, and sends contain no roster inference, obligation queue, handled/open social state, or cross-owner mutable lifecycle record. | `010`–`110` | `evidence/v2/parity/s16-no-ledger/` |

Every scene needs deterministic mechanics tests where deterministic facts are at
issue. Social-quality and cross-surface claims additionally need committed
replay and/or live evidence; unit tests alone cannot close them.

`S14` is executed as a fixed ladder: Hermes-only; Hermes + Claude Code; Hermes
+ Codex; Hermes + Claude Code + Codex; multi-human Discord; and multi-human
Telegram through Hermes. Normative lifecycle failures block cutover. Only facts
that a platform genuinely cannot expose may be recorded as limitations.
Admission-style meta-answers are graded after the participant turn as acceptance
failures; they do not justify a new runtime semantic send filter.

## Project Structure

### Control-plane artifacts

```text
specs/
├── 001-nunchi-v2-program/
│   ├── spec.md
│   ├── plan.md
│   ├── research.md
│   ├── checklists/
│   └── tasks.md
├── 010-v2-contract/
├── 020-v2-observation/
├── 030-v2-core-attention/
├── 040-v2-participant-wake/
├── 050-v2-discord-transport/
├── 060-v2-hermes/
├── 070-v2-claude-code/
├── 080-v2-codex/
├── 090-v2-channel-adapters/
├── 100-v2-security-provenance/
└── 110-v2-parity-cutover/
```

Only planning Markdown belongs in that tree.

### Future ordinary product targets

```text
schemas/v2/                    # 010-owned machine contracts
src/nunchi/                    # shared contract, observation, core, CLI, wake host
src/nunchi/mcp_discord/        # shared Discord event source
src/nunchi/adapters/           # standalone adapter bindings
integrations/hermes/           # Hermes binding
integrations/claude-code/      # Claude Code binding
integrations/codex/            # Codex binding
tests/v2/                      # deterministic contract/integration/governance checks
evals/v2/                      # reusable replay corpora and runners
evidence/v2/                   # immutable run records and provenance
docs/                          # truthful product/integration/security/evaluation docs
```

## Ordinary Repository Targets

| Artifact class | Goal 2 target path(s) | Owning slice(s) |
|---|---|---|
| Product implementation | `src/nunchi/`, `integrations/` | `020`–`090` |
| Machine-readable contracts | `schemas/v2/` | `010` |
| Deterministic tests | `tests/v2/` | implementing slice; parity ownership in `110` |
| Evaluation runners/corpora | `evals/v2/` | `030`, `060`–`090`; parity ownership in `110` |
| Evidence | `evidence/v2/` | each slice for its run records; final index in `110` |
| Product and integration docs | `docs/` | implementing slice drafts; final truthful state in `110` |

## Program Documentation Freshness

Every implementing slice reviews `README.md` and its affected ordinary docs.
Known files are named exactly; generic directory scope is invalid. Goal 2 task
progress stays dormant until the separately granted objective is recorded at
`evidence/governance/v2-goal-2-authorization.md`, which documents but cannot
grant authorization.
Slices `010`–`100` use `UPDATE` for owned component guides and an exact
`HANDOFF` to `v2-integrator` for global current-state claim deltas. Slice `110`
must use `UPDATE` for `README.md` and all affected cross-surface docs; because
the atomic cutover changes current behavior, neither `NO_IMPACT` nor `HANDOFF`
is valid for that final global wording.

Each slice's ordinary handoff evidence records exact reviewed paths,
dispositions, validation results, reviewer, and—where applicable—the precise
delta and accepting owner. Planning checkboxes do not prove freshness. The full
workflow's post-convergence documentation gate reviews the exact candidate
before owner handoff.

## Owner Handoff Contract

Every slice owner hands off one packet containing:

1. the exact candidate commit and branch;
2. upstream interface versions consumed and produced;
3. reproducible commands and complete results;
4. deterministic test and replay paths;
5. live evidence and installed-runtime provenance where required;
6. acceptance-scene result matrix, including valid unavailable facts;
7. effective configuration and migration/residue notes;
8. documentation dispositions, exact reviewed paths, validation results,
   reviewer, and accepted shared-doc deltas; and
9. known limitations, residual risks, and any rejected claim.

An incomplete packet is not accepted. Reviewers challenge the packet but do not
silently take ownership. `v2-integrator` records acceptance or sends it back to
the named owner lane.

## Complexity Tracking

None. No constitutional exception is authorized.
